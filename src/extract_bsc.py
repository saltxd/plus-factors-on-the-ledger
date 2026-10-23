"""Build the per-case evidence tables for the BNB Chain cases (TermiX hires during Set and Earn).

Stage 1 (--stage orders): parse the escrow pull into orders, validate daily hire counts
against the published decode, rebuild the two rings from their published descriptions,
and write the wallet list for the stablecoin-transfer pull.
Stage 2 (--stage cases): with the transfer pull and account lookups in place, write
data/cases/<case>/ in the same format as the Base cases.

Market mapping
  payment      a TermiX order created during the window for the case agent: payer = buyer,
               value = budget (USD), time = creation.
  hire edge    a settled order is a transfer buyer -> payee (the wallet the escrow paid),
               value = payout, time = settlement. The escrow itself is never a node.
  graph        hire edges for every order settled in lookback + window, plus every USDC/USDT
               transfer into or out of the case wallets (payees and their payers). Transfers
               of other wallets were not pulled, so the reach walk continues only through
               hire edges and the case wallets' own transfers (a stated limitation).
  hub          >= 1000 distinct counterparties in that graph, or, for an address whose
               transfers were not pulled, a contract or an account with >= 100,000 sent
               transactions.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from cases import LOOKBACK_DAYS, expand, load_registry, window_bounds

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "bsc"
log = logging.getLogger("extract_bsc")

ESCROWS = {"0x6a52ba4c84b348faeae13ddc7a97b4f6af23913c", "0xce02f987d8b8af694e13c8a843db9c77cabf544c"}
FEE_SAFE = "0x1095ded95cb6e81c01204f7a94950dd559195e42"
T_CREATED = "0xac4801e0cf6c58578da06571bd840e030ab529c0ca954375ff4e7b45086fef7c"
T_SETTLED = "0xdd533cd5141138294c3af311a217f94675d6ab3f45a7eee05943a2d51058e1a7"
D0_BLOCK, SE_FIRST, SE_LAST = 122313771, 125000755, 126344213
RING_ID_RANGE = (REDACTED, REDACTED)
GROUP14_EXAMPLE_TX = "REDACTED"
PUBLISHED_DAILY_HIRES = {"2026-10-01": 448, "2026-10-02": 4176, "2026-10-03": 2580, "2026-10-04": 1139, "2026-10-05": 638, "2026-10-06": 697, "2026-10-07": 647}
HUB_DEGREE = 1000
HUB_NONCE = 100_000
K_MAX = 6


def read_tsv(pattern: str, names: list[str]) -> pd.DataFrame:
    files = sorted(RAW.glob(pattern))
    frames = [pd.read_csv(f, sep="\t", header=None, names=names, dtype=str) for f in files if f.stat().st_size > 20]
    if not frames:
        return pd.DataFrame(columns=names)
    return pd.concat(frames, ignore_index=True)


class Clock:
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
    cr["buyer"] = "0x" + tp[2].str.slice(-40)
    cr["agent_id"] = tp[3].apply(lambda h: int(h, 16))
    cr["budget"] = cr["data"].apply(lambda d: int(d[2 + 64 : 2 + 128], 16) / 1e18)
    cr["created_block"] = cr["block"].astype(int)
    cr = cr.drop_duplicates("order_id")
    st = esc[esc["t0"] == T_SETTLED].copy()
    st["order_id"] = st["topics"].str.split(";").str[1]
    st = st.drop_duplicates("order_id")[["order_id", "tx", "block"]].rename(columns={"tx": "settle_tx", "block": "settled_block"})
    out = read_tsv("escrow_out/escrowout_*.tsv.gz", ["block", "txi", "li", "tx", "token", "src", "dst", "value"])
    out = out[~out["dst"].str.lower().isin(ESCROWS | {FEE_SAFE})].copy()
    out["value"] = out["value"].astype(float) / 1e18
    # payout = the largest non-fee transfer out of an escrow in the settlement transaction
    payout = out.sort_values("value").groupby("tx").tail(1)[["tx", "dst", "value"]].rename(columns={"tx": "settle_tx", "dst": "payee", "value": "payout"})
    n_per_tx = st.groupby("settle_tx")["order_id"].count()
    multi = set(n_per_tx[n_per_tx > 1].index)
    orders = cr[["order_id", "buyer", "agent_id", "budget", "created_block"]].merge(st, on="order_id", how="left")
    orders = orders.merge(payout[~payout["settle_tx"].isin(multi)], on="settle_tx", how="left")
    orders["created_ts"] = clock.ts(orders["created_block"])
    sb = orders["settled_block"].fillna(-1).astype(int)
    orders["settled_ts"] = np.where(sb > 0, clock.ts(sb.clip(lower=D0_BLOCK)), -1)
    orders["buyer"] = orders["buyer"].str.lower()
    orders["payee"] = orders["payee"].str.lower()
    log.info("orders: %d created, %d settled with payee, %d settle txs with several orders", len(orders), orders["payee"].notna().sum(), len(multi))
    return orders


def agent_payees(orders: pd.DataFrame) -> dict[int, str]:
    s = orders.dropna(subset=["payee"]).sort_values("settled_block")
    return s.groupby("agent_id")["payee"].last().to_dict()


def validate(orders: pd.DataFrame) -> dict:
    se = orders[(orders["created_block"] >= SE_FIRST) & (orders["created_block"] <= SE_LAST)]
    day = pd.to_datetime(se["created_ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    ours = day.value_counts().sort_index().to_dict()
    lb = orders[orders["created_block"] < SE_FIRST]
    lb_day = pd.to_datetime(lb["created_ts"], unit="s", utc=True).dt.strftime("%Y-%m-%d").value_counts().sort_index().to_dict()
    return {
        "se_hires_by_day_ours": ours,
        "se_hires_by_day_published": PUBLISHED_DAILY_HIRES,
        "se_total_ours": int(len(se)),
        "se_total_published": 10325,
        "lookback_orders_by_day": lb_day,
        "published_lookback_note": "set-and-earn-week-one: 1,938 to 7,249 BSC orders a day from Sep 20 to Sep 28",
    }


def rebuild_rings(orders: pd.DataFrame, payee_of: dict[int, str]) -> dict:
    se = orders[(orders["created_block"] >= SE_FIRST) & (orders["created_block"] <= SE_LAST)]
    lo, hi = RING_ID_RANGE
    in_range = {a: p for a, p in payee_of.items() if lo <= a <= hi}
    owners = set(in_range.values())
    r = se[se["agent_id"].between(lo, hi) & se["buyer"].isin(owners)]
    ring_agents = sorted(r["agent_id"].unique().tolist())
    # closure check: ring wallets hiring outside the ring, outsiders hiring ring agents
    ring_owners = {in_range[a] for a in ring_agents}
    out_hires = se[se["buyer"].isin(ring_owners) & ~se["agent_id"].isin(ring_agents)]
    in_hires = se[se["agent_id"].isin(ring_agents) & ~se["buyer"].isin(ring_owners)]
    ring = {
        "agents": ring_agents,
        "payees": sorted(ring_owners),
        "n_agents": len(ring_agents),
        "orders": int(len(r)),
        "hires_by_ring_wallets_outside_ring": int(len(out_hires)),
        "hires_of_ring_agents_by_outsiders": int(len(in_hires)),
    }
    # group of 14: wallets joined through $20-$30 window hires on Oct 1, 4 and 6, starting from the example
    ex = orders[orders.get("created_tx", pd.Series(dtype=str)) == GROUP14_EXAMPLE_TX] if "created_tx" in orders else pd.DataFrame()
    return {"ring48": ring, "group14_example": ex.to_dict("records")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["orders", "cases"], required=True)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clock = Clock()
    orders = load_orders(clock)
    payee_of = agent_payees(orders)
    val = validate(orders)
    (ROOT / "data" / "bsc_validation.json").write_text(json.dumps(val, indent=2) + "\n")
    log.info("validation: %s", json.dumps(val)[:600])
    rings = rebuild_rings(orders, payee_of)
    (ROOT / "data" / "bsc_rings.json").write_text(json.dumps(rings, indent=2, default=str) + "\n")
    log.info("ring48: %s", {k: v for k, v in rings["ring48"].items() if k not in ("agents", "payees")})


if __name__ == "__main__":
    main()
