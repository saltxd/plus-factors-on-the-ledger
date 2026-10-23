"""How the frozen rule's test result moves when the evidence settings change.

  reach depth K = 1..6          (results/sensitivity_features.csv from run_features --sensitivity)
  hub threshold 300 / 3000      (data/cases_h300, data/cases_h3000 from extract_base --hub)

The rule itself is not re-chosen: the frozen thresholds are applied to features computed
under each setting. Writes results/sensitivity.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from features import K_HOPS, compute_features
from rules import apply_rule, family_weights, metrics
from run_features import load_case, meta_cols

ROOT = Path(__file__).resolve().parents[1]


def score(df: pd.DataFrame, rule: dict, half: str) -> dict:
    part = df[df["half"] == half].reset_index(drop=True)
    pred = apply_rule(part, rule)
    m = metrics(pred, part["y"].to_numpy(), family_weights(part))
    return {f"{half}_{k}": v for k, v in m.items()}


def main() -> None:
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    rows = []
    sens = ROOT / "results" / "sensitivity_features.csv"
    if sens.exists():
        s = pd.read_csv(sens)
        for k, g in s.groupby("k"):
            for name in ("rule", "non_circular_rule"):
                rows.append({"setting": f"K={k}", "rule": name, **score(g, frozen[name], "dev"), **score(g, frozen[name], "test")})
    for hub in (300, 3000):
        d = ROOT / "data" / f"cases_h{hub}"
        if not d.exists():
            continue
        feats = []
        for c in sorted(p for p in d.iterdir() if (p / "meta.json").exists()):
            cd = load_case(c)
            feats.append({**meta_cols(cd.meta), **compute_features(cd, k=K_HOPS, n_null=20)})
        g = pd.DataFrame(feats)
        # BNB Chain cases use the hire graph, where no wallet is near either threshold; they
        # are carried over unchanged so every setting is scored on the same cases
        main = pd.read_csv(ROOT / "results" / "case_features.csv")
        g = pd.concat([g, main[main["chain"] == "bsc"]], ignore_index=True)
        g.to_csv(ROOT / "results" / f"sensitivity_features_h{hub}.csv", index=False, float_format="%.6g")
        for name in ("rule", "non_circular_rule"):
            rows.append({"setting": f"hub>={hub}", "rule": name, **score(g, frozen[name], "dev"), **score(g, frozen[name], "test")})
    pd.DataFrame(rows).to_csv(ROOT / "results" / "sensitivity.csv", index=False, float_format="%.4f")
    print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    main()
