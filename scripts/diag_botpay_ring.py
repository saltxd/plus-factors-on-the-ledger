"""Post hoc diagnostic, added after unblinding the spot-check (Oct 23, 2026): how much of the Base
market's flagged payee count is one ring, and why the rule stops flagging it in W4.

[D4] prints BotPay's root wallet (0x8736ae11...). A payee-week counts as paid by the ring when
more than half of its payment value comes from payers that received USDC from that root or from a
wallet the root paid (in lookback plus window, from the committed per-payee tables). For the W4
payee-weeks of that kind, the reach walk is rerun with K = 6 (src/extract_base.py unchanged, on a
scratch database that reads data/base.duckdb read-only) to measure where their main payer sits.
Only aggregate counts are written, to results/market_botpay_ring_posthoc.json; no wallet is listed.

  python scripts/diag_botpay_ring.py
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import extract_base as eb  # noqa: E402
import market_base as mb  # noqa: E402
from cases import Case  # noqa: E402

ROOT_WALLET = "0x8736ae11c1f3c6eba0a023baa455b2372fca2aab"
THRESHOLD = 0.4235


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    c0 = duckdb.connect(str(ROOT / "data" / "base.duckdb"), read_only=True)
    funded = {r[0] for r in c0.execute("SELECT DISTINCT dst FROM tr WHERE src = ? AND val > 0", [ROOT_WALLET]).fetchall()} | {ROOT_WALLET}
    c0.close()
    feats = pd.read_csv(ROOT / "results" / "market_base_features.csv")
    share = {}
    for d in sorted((ROOT / "data" / "market" / "base").iterdir()):
        if not (d / "meta.json").exists():
            continue
        m = json.loads((d / "meta.json").read_text())
        inf = pd.read_csv(d / "payer_inflows.csv.gz")
        pay = pd.read_csv(d / "payments.csv.gz")
        v = pay.groupby("payer")["value"].sum()
        ring_payers = inf[inf["src"].isin(funded)]["payer"].unique()
        share[(m["payee"], m["window"])] = float(v[v.index.isin(ring_payers)].sum() / v.sum()) if v.sum() > 0 else 0.0
    feats["ring_share"] = [share[(p, w)] for p, w in zip(feats["payee"], feats["window"])]
    feats["flag"] = feats["loop_share"] >= THRESHOLD
    ring = feats[feats["ring_share"] > 0.5]
    out = {"root_wallet_printed_in": "x402-top-ten-self-funded [D4]", "wallets_the_root_paid": len(funded) - 1,
           "ring_payee_weeks": int(len(ring)), "ring_payees": int(ring["payee"].nunique()),
           "ring_payees_flagged_some_week": int(ring[ring["flag"]]["payee"].nunique()),
           "flagged_payees_all": int(feats[feats["flag"]]["payee"].nunique()), "flagged_payee_weeks_all": int(feats["flag"].sum()),
           "ring_volume": float(ring["volume"].sum()), "market_volume": float(feats["volume"].sum()),
           "by_window": {w: {"payee_weeks": int(len(g)), "flagged": int(g["flag"].sum())} for w, g in ring.groupby("window")}}
    w4 = sorted(ring[ring["window"] == "W4"]["payee"])
    if w4:
        scratch = ROOT / "data" / "scratch" / "diag_k6.duckdb"
        cases = ROOT / "data" / "scratch" / "diag_k6_cases"
        con = mb.connect(scratch, "6GB", 6)
        bounds = eb.extract_window(con, "W4", w4, 1000, 6)
        hops = []
        for p in w4:
            case = Case(case_id=f"DIAG|{p}|W4", family="DIAG", chain="base", market="x402", label="diag", y=-1, payee=p, window="W4", half="diag")
            eb.write_case(con, case, p, cases, bounds, 1000, 6)
            r = pd.read_csv(cases / f"DIAG__{p}__W4" / "payer_reach.csv.gz")
            pay = pd.read_csv(cases / f"DIAG__{p}__W4" / "payments.csv.gz")
            r["value"] = r["payer"].map(pay.groupby("payer")["value"].sum())
            h = r.sort_values("value", ascending=False).iloc[0]["hops"]
            hops.append("not reached by 6" if pd.isna(h) else int(h))
        con.close()
        shutil.rmtree(cases, ignore_errors=True)
        for p in (scratch, scratch.with_suffix(".duckdb.wal")):
            p.unlink(missing_ok=True)
        out["w4_main_payer_hop_at_k6"] = {str(k): int(v) for k, v in pd.Series(hops).value_counts().items()}
    (ROOT / "results" / "market_botpay_ring_posthoc.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
