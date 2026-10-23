"""Score the frozen rules on the test half (and, for reference, on dev).

Writes results/predictions.csv, results/test_metrics.json, results/errors.csv and
results/feature_auc.csv. Variance: bootstrap over test families (resampled within
each class, B = 5000), and per-case spread in the case table.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from features import DIRECTION, EXPLORATORY_FEATURES, FEATURES
from rules import apply_rule, family_weights, metrics, weighted_auc

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("evaluate")
B = 5000


def bootstrap(df: pd.DataFrame, pred: np.ndarray, seed: int = 7) -> dict:
    """Resample families with replacement, separately for coordinated and other families,
    and recompute family-weighted metrics."""
    rng = np.random.default_rng(seed)
    fam = df["family"].to_numpy()
    y = df["y"].to_numpy()
    fam_y = df.groupby("family")["y"].max()
    pos_f = fam_y[fam_y == 1].index.to_numpy()
    neg_f = fam_y[fam_y == 0].index.to_numpy()
    idx_by_f = {f: np.flatnonzero(fam == f) for f in df["family"].unique()}
    stats = {"tpr": [], "fpr": [], "balanced_accuracy": []}
    for _ in range(B):
        picks = list(rng.choice(pos_f, len(pos_f))) + list(rng.choice(neg_f, len(neg_f)))
        rows, w = [], []
        for f in picks:
            ix = idx_by_f[f]
            rows.extend(ix)
            w.extend([1.0 / len(ix)] * len(ix))
        rows = np.array(rows)
        m = metrics(pred[rows], y[rows], np.array(w))
        for k in stats:
            stats[k].append(m[k])
    return {k: {"ci95": [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))], "sd": float(np.nanstd(v))} for k, v in stats.items()}


def evaluate_rule(df: pd.DataFrame, rule: dict) -> dict:
    out = {}
    for half in ("dev", "test", "all"):
        part = df if half == "all" else df[df["half"] == half]
        part = part.reset_index(drop=True)
        pred = apply_rule(part, rule)
        y = part["y"].to_numpy()
        res = {
            "cases": int(len(part)),
            "families": int(part["family"].nunique()),
            "family_weighted": metrics(pred, y, family_weights(part)),
            "case_level": metrics(pred, y),
            "confusion_cases": {
                "tp": int((pred & (y == 1)).sum()),
                "fn": int((~pred & (y == 1)).sum()),
                "fp": int((pred & (y == 0)).sum()),
                "tn": int((~pred & (y == 0)).sum()),
            },
        }
        if half == "test":
            res["bootstrap_family_weighted"] = bootstrap(part, pred)
        out[half] = res
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = pd.read_csv(ROOT / "results" / "case_features.csv")
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    rules = {"primary": frozen["rule"], "non_circular": frozen["non_circular_rule"]}
    for f, r in frozen["best_single_feature_rules"].items():
        rules[f"single:{f}"] = r["rule"]
    results = {name: {"rule": r, **evaluate_rule(df, r)} for name, r in rules.items()}

    df = df.copy()
    df["flag_primary"] = apply_rule(df, frozen["rule"])
    df["flag_non_circular"] = apply_rule(df, frozen["non_circular_rule"])
    df.to_csv(ROOT / "results" / "predictions.csv", index=False, float_format="%.6g")
    err = df[(df["flag_primary"] & (df["y"] == 0)) | (~df["flag_primary"] & (df["y"] == 1))]
    err = err.assign(error=np.where(err["y"] == 0, "false positive", "false negative"))
    err.to_csv(ROOT / "results" / "errors.csv", index=False, float_format="%.6g")

    auc_rows = []
    for half in ("dev", "test", "all"):
        part = df if half == "all" else df[df["half"] == half]
        part = part.reset_index(drop=True)
        w = family_weights(part)
        for f in FEATURES + EXPLORATORY_FEATURES:
            s = DIRECTION[f] * part[f].to_numpy(dtype=float)
            auc_rows.append({"half": half, "feature": f, "exploratory": f in EXPLORATORY_FEATURES,
                             "auc_family_weighted": weighted_auc(s, part["y"].to_numpy(), w),
                             "auc_case_level": weighted_auc(s, part["y"].to_numpy(), np.ones(len(part)))})
    pd.DataFrame(auc_rows).to_csv(ROOT / "results" / "feature_auc.csv", index=False, float_format="%.4f")
    (ROOT / "results" / "test_metrics.json").write_text(json.dumps(results, indent=2) + "\n")
    p = results["primary"]["test"]
    log.info("primary on test: %s cases=%d fw=%s case=%s", frozen["rule_text"], p["cases"], p["family_weighted"], p["case_level"])


if __name__ == "__main__":
    main()
