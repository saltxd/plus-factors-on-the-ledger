"""Compute the evidence features for every extracted case.

Reads data/cases/<case>/ (payments, payer_inflows, seller_outflows, payer_reach, meta.json)
and writes results/case_features.csv (primary settings) and, with --sensitivity,
results/sensitivity_features.csv (reach depth K = 1..6).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from features import K_HOPS, CaseData, compute_features

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("run_features")


def load_case(d: Path) -> CaseData:
    meta = json.loads((d / "meta.json").read_text())
    pay = pd.read_csv(d / "payments.csv.gz")
    inf = pd.read_csv(d / "payer_inflows.csv.gz")
    out = pd.read_csv(d / "seller_outflows.csv.gz")
    reach_df = pd.read_csv(d / "payer_reach.csv.gz")
    for col in ("payer",):
        pay[col] = pay[col].str.lower()
        inf[col] = inf[col].str.lower()
    reach = {
        str(r.payer).lower(): (None if pd.isna(r.hops) else int(r.hops)) for r in reach_df.itertuples(index=False)
    }
    if inf.empty:
        inf = pd.DataFrame(columns=["payer", "src", "value", "ts", "order", "src_hops", "src_is_payer", "src_is_hub", "src_is_seller"])
    return CaseData(meta["case_id"], pay, inf, out, reach, int(meta["t0"]), int(meta["t1"]), meta)


def meta_cols(meta: dict) -> dict:
    keys = ["case_id", "family", "label", "y", "half", "chain", "window", "payee", "contested"]
    row = {k: meta.get(k) for k in keys}
    row["contested"] = bool(meta.get("contested", False))
    row["reach_capped"] = bool(meta.get("reach_capped", False))
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(ROOT / "data" / "cases"))
    ap.add_argument("--out", default=str(ROOT / "results"))
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--n-null", type=int, default=200)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rows, sens = [], []
    for d in sorted(p for p in Path(args.cases).iterdir() if (p / "meta.json").exists()):
        cd = load_case(d)
        f = compute_features(cd, k=K_HOPS, n_null=args.n_null)
        rows.append({**meta_cols(cd.meta), **f})
        if args.sensitivity:
            for k in range(1, 7):
                fk = compute_features(cd, k=k, n_null=20)
                sens.append({**meta_cols(cd.meta), "k": k, **fk})
        # test-half feature values stay out of the log until the rule is frozen
        if cd.meta.get("half") == "dev":
            log.info("%s %s", cd.case_id, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()})
        else:
            log.info("%s (test half, values not shown)", cd.case_id)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows).sort_values(["half", "family", "case_id"])
    df.to_csv(out / "case_features.csv", index=False, float_format="%.6g")
    if sens:
        pd.DataFrame(sens).to_csv(out / "sensitivity_features.csv", index=False, float_format="%.6g")
    log.info("wrote %d cases", len(df))


if __name__ == "__main__":
    main()
