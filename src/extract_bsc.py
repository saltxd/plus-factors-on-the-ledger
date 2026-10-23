"""Build the per-case evidence tables for the BNB Chain cases (TermiX hires during Set and Earn).

Stage "orders": parse the escrow pull into orders, check daily hire counts against the
published decode, rebuild the two rings from their published descriptions, and write the
list of agent ids whose owner must be looked up (pull/bsc_termix_pull.py owners).
Stage "cases": with owners in place, write data/cases/<case>/ in the same format as Base.

Market mapping (BNB Chain evidence is the market's own payment graph):
  payee        the agent's owner (ERC-8004 ownerOf at the window's last block). On a sample of
               settlement receipts the escrow paid exactly this wallet (see data/bsc_validation.json).
  payment      a TermiX order created during the window for an agent the payee owns:
               payer = buyer, value = budget, time = creation.
  hire edge    every order settled in lookback + window is a transfer buyer -> payee of
               0.98 x budget at settlement time. The escrow itself is never a node.
  graph        hire edges only. Plain USDC/USDT transfers on BNB Chain could not be pulled at
               the allowed pace from keyless endpoints (topic-filtered token queries are capped
               at under 1,000 blocks), so funding from exchanges or direct transfers is not seen.
  hub          a wallet with >= 1000 distinct counterparties in the hire graph.

Pseudonyms: the decodes describe the two rings without listing their wallets, so no output of
this script names them. Every ring wallet appears as ring48-01 .. ring48-48 or group14-01 ..
group14-14, numbered in ascending order of its lowercase address, in every case id, directory
name, table and JSON file written here, wherever it occurs (also as another case's payer).
Only the raw pull (data/raw/bsc) and the in-memory joins use the addresses. The raw pull is
not committed, because it holds these wallet lists; pull/bsc_termix_pull.py re-pulls it.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

from cases import expand, load_registry, window_bounds

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "bsc"
log = logging.getLogger("extract_bsc")

T_CREATED = "0xac4801e0cf6c58578da06571bd840e030ab529c0ca954375ff4e7b45086fef7c"
T_SETTLED = "0xdd533cd5141138294c3af311a217f94675d6ab3f45a7eee05943a2d51058e1a7"
D0_BLOCK, SE_FIRST, SE_LAST = 122313771, 125000755, 126344213
RING_ID_RANGE = (REDACTED, REDACTED)
GROUP14_EXAMPLE_TX = "REDACTED"
PUBLISHED_DAILY_HIRES = {"2026-10-01": 448, "2026-10-02": 4176, "2026-10-03": 2580, "2026-10-04": 1139, "2026-10-05": 638, "2026-10-06": 697, "2026-10-07": 647}
FEE = 0.02
HUB_DEGREE = 1000
K_MAX = 6


def read_tsv(pattern: str, names: list[str]) -> pd.DataFrame:
    files = sorted(RAW.glob(pattern))
    frames = [pd.read_csv(f, sep="\t", header=None, names=names, dtype=str) for f in files if f.stat().st_size > 20]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=names)


class Clock:
    """BSC block -> unix time, linear between anchor blocks fetched every 50,000 blocks."""

    def __init__(self) -> None:
        a = read_tsv("anchors_*.tsv.gz", ["block", "ts"]).astype(int).drop_duplicates().sort_values("block")
        self.b, self.t = a["block"].to_numpy(dtype=float), a["ts"].to_numpy(dtype=float)

    def ts(self, blocks) -> np.ndarray:
        return np.round(np.interp(np.asarray(blocks, dtype=float), self.b, self.t)).astype(np.int64)


def load_orders(clock: Clock) -> pd.DataFrame:
    esc = read_tsv("escrow/escrow_*.tsv.gz", ["block", "txi", "li", "tx", "address", "topics", "data"])
    esc["t0"] = esc["topics"].str.slice(0, 66)
    cr = esc[esc["t0"] == T_CREATED].copy()
    tp = cr["topics"].str.split(";", expand=True)
    cr["order_id"] = tp[1]
    cr["buyer"] = ("0x" + tp[2].str.slice(-40)).str.lower()
    cr["agent_id"] = tp[3].apply(lambda h: int(h, 16))
    cr["budget"] = cr["data"].apply(lambda d: int(d[2 + 64 : 2 + 128], 16) / 1e18)
    cr["created_block"] = cr["block"].astype(int)
    cr["created_tx"] = cr["tx"]
    cr = cr.drop_duplicates("order_id")
    st = esc[esc["t0"] == T_SETTLED].copy()
    st["order_id"] = st["topics"].str.split(";").str[1]
    st = st.drop_duplicates("order_id")[["order_id", "tx", "block"]].rename(columns={"tx": "settle_tx", "block": "settled_block"})
    orders = cr[["order_id", "buyer", "agent_id", "budget", "created_block", "created_tx", "address"]].merge(st, on="order_id", how="left")
    orders["created_ts"] = clock.ts(orders["created_block"])
    sb = orders["settled_block"].fillna(-1).astype(int)
    orders["settled_block"] = sb
    orders["settled_ts"] = np.where(sb > 0, clock.ts(sb.clip(lower=D0_BLOCK)), -1)
    log.info("orders: %d created in pull, %d settled in pull", len(orders), int((sb > 0).sum()))
    return orders


def validate(orders: pd.DataFrame) -> dict:
    se = orders[(orders["created_block"] >= SE_FIRST) & (orders["created_block"] <= SE_LAST)]
    day = pd.to_datetime(se["created_ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    lb = orders[orders["created_block"] < SE_FIRST]
    lb_day = pd.to_datetime(lb["created_ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d").value_counts().sort_index()
    disc = []
    for f in sorted((RAW / "escrow").glob("discrepancies.jsonl")):
        disc += [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    return {
        "se_hires_by_day_ours": day.value_counts().sort_index().to_dict(),
        "se_hires_by_day_published": PUBLISHED_DAILY_HIRES,
        "se_total_ours": int(len(se)),
        "se_total_published": int(sum(PUBLISHED_DAILY_HIRES.values())),
        "lookback_orders_by_day": lb_day.to_dict(),
        "lookback_published_note": "set-and-earn-week-one: 1,938 to 7,249 BSC orders a day from Sep 20 to Sep 28",
        "double_query_disagreements": disc,
    }


def se_orders(orders: pd.DataFrame) -> pd.DataFrame:
    return orders[(orders["created_block"] >= SE_FIRST) & (orders["created_block"] <= SE_LAST)]


def rebuild_ring48(orders: pd.DataFrame, owner: dict[int, str]) -> dict:
    """The decode's description: agents with ids REDACTED..REDACTED (registered Sep 4), each hired during
    the window only by owners of other agents in the set, whose owners hire no agent outside it.
    Candidates are window hires of in-range agents by owners of in-range agents; the ring is the union
    of the candidates' connected hire components that are closed (no window hire in or out)."""
    se = se_orders(orders).copy()
    se["payee"] = se["agent_id"].map(owner)
    lo, hi = RING_ID_RANGE
    in_range = {a for a in owner if lo <= a <= hi and owner[a]}
    owners_in_range = {owner[a] for a in in_range}
    cand = se[se["agent_id"].isin(in_range) & se["buyer"].isin(owners_in_range)]
    wallets = set(cand["buyer"]) | set(cand["payee"])
    adj: dict[str, set[str]] = defaultdict(set)
    for b, p in zip(cand["buyer"], cand["payee"]):
        adj[b].add(p)
        adj[p].add(b)
    seen: set[str] = set()
    comps = []
    for w in sorted(wallets):
        if w in seen:
            continue
        stack, comp = [w], set()
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.add(x)
            stack.extend(adj[x] - seen)
        comps.append(comp)
    closed, other = [], []
    for comp in comps:
        n_out = int((se["buyer"].isin(comp) & ~se["payee"].isin(comp)).sum())
        n_in = int((~se["buyer"].isin(comp) & se["payee"].isin(comp)).sum())
        (closed if n_out == 0 and n_in == 0 else other).append((comp, n_in, n_out))
    ring_wallets = sorted(set().union(*[c for c, _, _ in closed])) if closed else []
    r = se[se["buyer"].isin(ring_wallets) & se["payee"].isin(ring_wallets)]
    days = pd.to_datetime(r["created_ts"], unit="s", utc=True).dt.strftime("%m-%d").value_counts().sort_index().to_dict()
    return {
        "payees": ring_wallets,
        "agents": sorted(r["agent_id"].unique().tolist()),
        "n_payees": len(ring_wallets),
        "closed_component_sizes": sorted((len(c) for c, _, _ in closed), reverse=True),
        "excluded_open_components": [{"size": len(c), "hires_in": i, "hires_out": o_} for c, i, o_ in other],
        "candidate_wallets": len(wallets),
        "orders": int(len(r)),
        "orders_unsettled": int((r["settled_block"] <= 0).sum()),
        "orders_by_day": days,
    }


def rebuild_group14(orders: pd.DataFrame, owner: dict[int, str]) -> dict:
    """Closure from the decode's example hire: add the owners of agents that members hired, and
    the buyers of agents that members own, over window hires of at least $2 (the decode notes one
    $1 hire out), until nothing changes."""
    se = se_orders(orders).copy()
    se["payee"] = se["agent_id"].map(owner)
    ex = se[se["created_tx"] == GROUP14_EXAMPLE_TX]
    if ex.empty:
        return {"error": "example transaction not found in the pull"}
    big = se[se["budget"] >= 2]
    members = {ex.iloc[0]["buyer"], ex.iloc[0]["payee"]}
    while True:
        add = set(big[big["buyer"].isin(members)]["payee"].dropna()) | set(big[big["payee"].isin(members)]["buyer"])
        if add <= members:
            break
        members |= add
        if len(members) > 500:
            break
    m = sorted(members)
    inside = se[se["buyer"].isin(m) & se["payee"].isin(m)]
    out_h = se[se["buyer"].isin(m) & ~se["payee"].isin(m)]
    in_h = se[~se["buyer"].isin(m) & se["payee"].isin(m)]
    days = pd.to_datetime(inside["created_ts"], unit="s", utc=True).dt.strftime("%m-%d").value_counts().sort_index().to_dict()
    return {"payees": m, "n_wallets": len(m), "orders_inside": int(len(inside)), "orders_by_day": days,
            "budget_range_inside": [float(inside["budget"].min()), float(inside["budget"].max())] if len(inside) else None,
            "hires_out": out_h[["buyer", "agent_id", "budget"]].to_dict("records"), "hires_in": int(len(in_h)),
            "agents": sorted(se[se["payee"].isin(m)]["agent_id"].unique().tolist())}


ESCROWS = {"0x6a52ba4c84b348faeae13ddc7a97b4f6af23913c", "0xce02f987d8b8af694e13c8a843db9c77cabf544c"}
FEE_SAFE = "0x1095ded95cb6e81c01204f7a94950dd559195e42"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def validate_payees(owner: dict[int, str]) -> dict:
    """On a seeded sample of settlement transactions (data/bsc_settle_sample.csv; their receipts
    come from pull/bsc_termix_pull.py receipts), compare the wallet the escrow paid (largest
    non-fee stablecoin transfer out of an escrow) with ERC-8004 ownerOf(agent)."""
    sample = pd.read_csv(ROOT / "data" / "bsc_settle_sample.csv")
    rec = read_tsv("receipts_settle_sample.tsv.gz", ["block", "txi", "li", "tx", "address", "topics", "data"])
    rows = []
    for r in sample.itertuples(index=False):
        logs = rec[rec["tx"] == r.settle_tx]
        paid = []
        for lg in logs.itertuples(index=False):
            t = lg.topics.split(";")
            if t[0] == TRANSFER and len(t) == 3:
                src, dst = "0x" + t[1][-40:], "0x" + t[2][-40:]
                if src in ESCROWS and dst not in ESCROWS and dst != FEE_SAFE:
                    paid.append((int(lg.data, 16), dst))
        recipient = max(paid)[1] if paid else None
        rows.append({"settle_tx": r.settle_tx, "agent_id": int(r.agent_id), "paid_to": recipient,
                     "owner_of": owner.get(int(r.agent_id)), "match": recipient is not None and recipient == owner.get(int(r.agent_id))})
    return {"sampled": len(rows), "matched": int(sum(x["match"] for x in rows)), "rows": rows}


def ring_aliases(rings: dict) -> dict[str, str]:
    """Address -> pseudonym for the wallets of both rebuilt rings (see the module docstring)."""
    alias: dict[str, str] = {}
    for name in ("ring48", "group14"):
        for i, addr in enumerate(sorted(rings[name].get("payees", [])), 1):
            alias[addr] = f"{name}-{i:02d}"
    return alias


def pseudonymize(obj, alias: dict[str, str]):
    """Replace every string that is a ring wallet's address, anywhere in a JSON-like object."""
    if isinstance(obj, str):
        return alias.get(obj, obj)
    if isinstance(obj, dict):
        return {pseudonymize(k, alias): pseudonymize(v, alias) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [pseudonymize(v, alias) for v in obj]
    return obj


def load_owners() -> dict[int, str]:
    o = read_tsv(f"owners_agents_{SE_LAST}.tsv.gz", ["agent_id", "owner"])
    return {int(a): (w.lower() if w.startswith("0x") else None) for a, w in zip(o["agent_id"], o["owner"])}


def build_cases(orders: pd.DataFrame, owner: dict[int, str], rings: dict, alias: dict[str, str]) -> list[dict]:
    reg = load_registry()
    t0, t1, w0, w1 = window_bounds(reg, "SE")
    o = orders.copy()
    o["payee"] = o["agent_id"].map(owner)
    settled = o[(o["settled_block"] > 0) & o["payee"].notna()]
    # hire graph (money moved): buyer -> payee
    adj: dict[str, set[str]] = defaultdict(set)
    nbrs: dict[str, set[str]] = defaultdict(set)
    for b, p in zip(settled["buyer"], settled["payee"]):
        if b != p:
            adj[b].add(p)
            nbrs[b].add(p)
            nbrs[p].add(b)
    hubs = {w for w, n in nbrs.items() if len(n) >= HUB_DEGREE}
    log.info("hire graph: %d wallets, %d edges, %d hubs", len(nbrs), sum(len(v) for v in adj.values()), len(hubs))

    def reach_from(src: str) -> dict[str, int]:
        dist = {src: 0}
        q = deque([src])
        while q:
            u = q.popleft()
            if dist[u] >= K_MAX:
                continue
            for v in adj.get(u, ()):
                if v not in dist and v not in hubs:
                    dist[v] = dist[u] + 1
                    q.append(v)
        return dist

    se = o[(o["created_block"] >= w0) & (o["created_block"] <= w1)]
    payee_sets = {
        "F08-se-ring48": rings["ring48"]["payees"],
        "F09-se-group14": rings["group14"].get("payees", []),
    }
    out = []
    cases = [c for c in expand(reg) if c.chain == "bsc"]
    for c in cases:
        payees = payee_sets.get(c.family) if c.payee.startswith("reconstruct:") else [c.payee]
        for p in payees:
            case_id = f"{c.family}|{alias.get(p, p)}|{c.window}"
            d = ROOT / "data" / "cases" / case_id.replace("|", "__")
            pay = se[se["payee"] == p]
            if pay.empty:
                out.append({"case_id": case_id, "dropped": "no payments in window"})
                continue
            d.mkdir(parents=True, exist_ok=True)
            dist = reach_from(p)
            payers = sorted(pay["buyer"].unique())
            pset = set(payers)
            pay_t = pd.DataFrame({"payer": pay["buyer"], "value": pay["budget"], "ts": pay["created_ts"], "block": pay["created_block"],
                                  "order_id": pay["order_id"], "agent_id": pay["agent_id"], "via": "termix-order"})
            inf = settled[settled["payee"].isin(pset)]
            inf_t = pd.DataFrame({
                "payer": inf["payee"], "src": inf["buyer"], "raw_src": "termix-escrow", "value": inf["budget"] * (1 - FEE),
                "ts": inf["settled_ts"], "order": inf["settled_block"].astype("int64") * 1_000_000,
                "src_hops": [dist.get(s, -1) for s in inf["buyer"]],
                "src_is_payer": inf["buyer"].isin(pset).astype(int), "src_is_hub": inf["buyer"].isin(hubs).astype(int),
                "src_is_seller": (inf["buyer"] == p).astype(int)})
            outs = o[(o["buyer"] == p) & (o["created_block"] >= D0_BLOCK) & (o["created_block"] <= w1)]
            out_t = pd.DataFrame({"dst": outs["payee"].fillna("unknown-owner"), "value": outs["budget"], "ts": outs["created_ts"], "block": outs["created_block"],
                                  "dst_is_hub": outs["payee"].isin(hubs).astype(int)})
            reach_t = pd.DataFrame({"payer": payers, "hops": [dist.get(b) for b in payers]})
            for t, cols in ((pay_t, ["payer"]), (inf_t, ["payer", "src"]), (out_t, ["dst"]), (reach_t, ["payer"])):
                for col in cols:
                    t[col] = t[col].map(lambda x: alias.get(x, x))
            pay_t.sort_values("ts").to_csv(d / "payments.csv.gz", index=False)
            inf_t.sort_values("order").to_csv(d / "payer_inflows.csv.gz", index=False)
            out_t.sort_values("ts").to_csv(d / "seller_outflows.csv.gz", index=False)
            reach_t.to_csv(d / "payer_reach.csv.gz", index=False)
            hop_counts = pd.Series(list(dist.values())).value_counts().sort_index()
            meta = {
                "case_id": case_id, "family": c.family, "label": c.label, "y": c.y, "half": c.half, "payee": alias.get(p, p), "window": c.window,
                "chain": "bsc", "market": c.market, "contested": c.contested, "t0": t0, "t1": t1, "window_blocks": [w0, w1],
                "data_blocks": [D0_BLOCK, w1], "hub_threshold": HUB_DEGREE, "k": K_MAX, "graph": "termix hire graph only",
                "reach_by_hop": [[int(h), int(n)] for h, n in hop_counts.items()], "reach_capped": False,
                "n_payments": int(len(pay_t)), "n_payers": len(payers), "volume": float(pay_t["value"].sum()),
                "agents": sorted(pay["agent_id"].unique().tolist()),
            }
            (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
            out.append(meta)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["orders", "cases"], required=True)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clock = Clock()
    orders = load_orders(clock)
    if args.stage == "orders":
        val = validate(orders)
        (ROOT / "data" / "bsc_validation.json").write_text(json.dumps(val, indent=2) + "\n")
        ids = sorted(orders["agent_id"].unique().tolist())
        (RAW / "agents.txt").write_text("\n".join(str(i) for i in ids) + "\n")
        log.info("validation: ours %s vs published %s; %d agent ids to look up", val["se_hires_by_day_ours"], PUBLISHED_DAILY_HIRES, len(ids))
        return
    owner = load_owners()
    val = json.loads((ROOT / "data" / "bsc_validation.json").read_text())
    val["payee_is_owner_sample"] = validate_payees(owner)
    rings = {"ring48": rebuild_ring48(orders, owner), "group14": rebuild_group14(orders, owner)}
    alias = ring_aliases(rings)
    (ROOT / "data" / "bsc_validation.json").write_text(json.dumps(pseudonymize(val, alias), indent=2) + "\n")
    log.info("payee == ownerOf on sample: %d of %d", val["payee_is_owner_sample"]["matched"], val["payee_is_owner_sample"]["sampled"])
    shown = pseudonymize(rings, alias)
    (ROOT / "data" / "bsc_rings.json").write_text(json.dumps(shown, indent=2, default=str) + "\n")
    log.info("ring48: %s", {k: v for k, v in shown["ring48"].items() if k not in ("agents", "payees")})
    log.info("group14: %s", {k: v for k, v in shown["group14"].items() if k not in ("agents", "payees")})
    summary = build_cases(orders, owner, rings, alias)
    (ROOT / "data" / "cases" / "extract_bsc_summary.json").write_text(json.dumps(pseudonymize(summary, alias), indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
