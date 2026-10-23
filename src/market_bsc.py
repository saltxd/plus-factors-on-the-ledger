"""Whole-market run of the frozen rule on BNB Chain: every Set and Earn payee on TermiX.

Added Oct 23 to 24, 2026, after the freeze (plan: cases/market_plan.md, section 2). Every
ERC-8004 owner of an agent with a TermiX order created in the SE window is a payee, with no floor.
The per-payee tables are built exactly as src/extract_bsc.py builds a case (same hire graph, hubs,
reach to K_MAX hops, payer inflows, seller outflows), the ring wallets are replaced by their
pseudonyms before any feature is computed (as in the committed case tables), and src/features.py
computes the features. Nothing is written per payee; the output is one row per payee with the
payee's address, or its pseudonym for the 62 ring wallets, and no agent or order ids.

  python src/market_bsc.py            # needs the raw BNB Chain pull in data/raw/bsc
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict, deque
from pathlib import Path

import pandas as pd

import extract_bsc as xb
from cases import load_registry, window_bounds
from features import CaseData, compute_features
from rules import apply_rule

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("market_bsc")


def build_graph(orders: pd.DataFrame, owner: dict[int, str]):
    o = orders.copy()
    o["payee"] = o["agent_id"].map(owner)
    settled = o[(o["settled_block"] > 0) & o["payee"].notna()]
    adj: dict[str, set[str]] = defaultdict(set)
    nbrs: dict[str, set[str]] = defaultdict(set)
    for b, p in zip(settled["buyer"], settled["payee"]):
        if b != p:
            adj[b].add(p)
            nbrs[b].add(p)
            nbrs[p].add(b)
    hubs = {w for w, n in nbrs.items() if len(n) >= xb.HUB_DEGREE}
    return o, settled, adj, hubs


def reach_from(src: str, adj: dict[str, set[str]], hubs: set[str]) -> dict[str, int]:
    """Same walk as extract_bsc.build_cases.reach_from."""
    dist = {src: 0}
    q = deque([src])
    while q:
        u = q.popleft()
        if dist[u] >= xb.K_MAX:
            continue
        for v in adj.get(u, ()):
            if v not in dist and v not in hubs:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def payee_case(p: str, se: pd.DataFrame, o: pd.DataFrame, settled: pd.DataFrame, adj, hubs, alias: dict[str, str],
               t0: int, t1: int, w1: int) -> CaseData:
    """The tables extract_bsc.build_cases writes for one payee, with the same column formulas."""
    pay = se[se["payee"] == p]
    dist = reach_from(p, adj, hubs)
    payers = sorted(pay["buyer"].unique())
    pset = set(payers)
    pay_t = pd.DataFrame({"payer": pay["buyer"], "value": pay["budget"], "ts": pay["created_ts"]})
    inf = settled[settled["payee"].isin(pset)]
    inf_t = pd.DataFrame({
        "payer": inf["payee"], "src": inf["buyer"], "value": inf["budget"] * (1 - xb.FEE),
        "ts": inf["settled_ts"], "order": inf["settled_block"].astype("int64") * 1_000_000,
        "src_hops": [dist.get(s, -1) for s in inf["buyer"]],
        "src_is_payer": inf["buyer"].isin(pset).astype(int), "src_is_hub": inf["buyer"].isin(hubs).astype(int),
        "src_is_seller": (inf["buyer"] == p).astype(int)})
    outs = o[(o["buyer"] == p) & (o["created_block"] >= xb.D0_BLOCK) & (o["created_block"] <= w1)]
    out_t = pd.DataFrame({"dst": outs["payee"].fillna("unknown-owner"), "value": outs["budget"], "ts": outs["created_ts"]})
    reach = {alias.get(b, b): dist.get(b) for b in payers}
    for t, cols in ((pay_t, ["payer"]), (inf_t, ["payer", "src"]), (out_t, ["dst"])):
        for col in cols:
            t[col] = t[col].map(lambda x: alias.get(x, x))
    pay_t = pay_t.sort_values("ts").reset_index(drop=True)
    inf_t = inf_t.sort_values("order").reset_index(drop=True)
    out_t = out_t.sort_values("ts").reset_index(drop=True)
    for t in (pay_t, inf_t):
        t["payer"] = t["payer"].str.lower()
    meta = {"payee": alias.get(p, p), "is_ring_wallet": p in alias}
    return CaseData(f"MARKET-bsc|{alias.get(p, p)}|SE", pay_t, inf_t, out_t, reach, t0, t1, meta)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "results" / "market_bsc_features.csv"))
    ap.add_argument("--n-null", type=int, default=20)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clock = xb.Clock()
    orders = xb.load_orders(clock)
    owner = xb.load_owners()
    rings = {"ring48": xb.rebuild_ring48(orders, owner), "group14": xb.rebuild_group14(orders, owner)}
    alias = xb.ring_aliases(rings)
    if len(alias) != 62:
        raise SystemExit(f"expected 62 ring wallets, got {len(alias)}")
    reg = load_registry()
    t0, t1, w0, w1 = window_bounds(reg, "SE")
    o, settled, adj, hubs = build_graph(orders, owner)
    se = o[(o["created_block"] >= w0) & (o["created_block"] <= w1)]
    no_owner = se[se["payee"].isna()]
    se = se[se["payee"].notna()]
    payees = sorted(se["payee"].unique())
    log.info("SE window: %d orders with an owner (%d without), %d payees, %d hubs", len(se), len(no_owner), len(payees), len(hubs))
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    rows = []
    for i, p in enumerate(payees):
        cd = payee_case(p, se, o, settled, adj, hubs, alias, t0, t1, w1)
        f = compute_features(cd, k=4, n_null=args.n_null)
        rows.append({"payee": cd.meta["payee"], "ring_wallet": cd.meta["is_ring_wallet"], **f})
        if (i + 1) % 1000 == 0:
            log.info("%d / %d payees", i + 1, len(payees))
    df = pd.DataFrame(rows)
    df["flag_primary"] = apply_rule(df, frozen["rule"])
    df["flag_non_circular"] = apply_rule(df, frozen["non_circular_rule"])
    df["flag_outside_funding"] = apply_rule(df, frozen["best_single_feature_rules"]["outside_funding_share"]["rule"])
    leaked = set(df["payee"]) & set(alias)
    if leaked:
        raise SystemExit("a ring wallet address reached the output")
    df.sort_values(["volume", "payee"], ascending=[False, True]).to_csv(args.csv, index=False, float_format="%.6g")
    summ = {"orders_with_owner": int(len(se)), "orders_without_owner": int(len(no_owner)), "payees": int(len(df)),
            "volume": float(df["volume"].sum()), "flagged": int(df["flag_primary"].sum()),
            "flagged_volume": float(df.loc[df["flag_primary"], "volume"].sum())}
    log.info("summary: %s", summ)


if __name__ == "__main__":
    main()
