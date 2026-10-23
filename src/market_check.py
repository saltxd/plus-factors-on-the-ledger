"""Apply the frozen rules to the sampled TermiX Base payees and compare the share of market
volume they flag with the decode's published aggregate (99.23% of fees, Aug 31 - Sep 29, from
wallets that hire each other). Writes results/market_termix_base.json and .csv.

The sample is volume-weighted without replacement, so the volume share is estimated with a
Hajek-style ratio over the sample and a bootstrap interval (B = 2000).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from features import K_HOPS, compute_features
from rules import apply_rule
from run_features import load_case, meta_cols

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = {"share_of_fees_from_cycling_wallets_last_30_days": 0.9923, "window": "2026-08-31..2026-09-29", "source": "termix-on-chain"}


def main() -> None:
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    d = ROOT / "data" / "market" / "termix_base_W1"
    pop = json.loads((d / "population.json").read_text())
    rows = []
    for c in sorted(p for p in d.iterdir() if (p / "meta.json").exists()):
        cd = load_case(c)
        rows.append({**meta_cols(cd.meta), **compute_features(cd, k=K_HOPS, n_null=50)})
    df = pd.DataFrame(rows)
    df["flag_primary"] = apply_rule(df, frozen["rule"])
    df["flag_non_circular"] = apply_rule(df, frozen["non_circular_rule"])
    df.to_csv(ROOT / "results" / "market_termix_base.csv", index=False, float_format="%.6g")
    rng = np.random.default_rng(11)
    mult = pop["multiplicity"]
    df["draws"] = df["payee"].map(mult).fillna(0).astype(int)
    draws = np.repeat(np.arange(len(df)), df["draws"].to_numpy())  # one entry per draw
    out = {"population": {k: v for k, v in pop.items() if k != "multiplicity"}, "distinct_payees_extracted": int(len(df)),
           "draws_with_features": int(len(draws)), "published": PUBLISHED}
    for col in ("flag_primary", "flag_non_circular"):
        flags = df[col].to_numpy(dtype=float)[draws]
        boots = [float(rng.choice(flags, size=len(flags), replace=True).mean()) for _ in range(2000)]
        out[col] = {"estimated_share_of_volume_flagged": float(flags.mean()),
                    "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                    "estimator": "mean flag over draws made with probability proportional to volume (Hansen-Hurwitz)"}
    (ROOT / "results" / "market_termix_base.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
