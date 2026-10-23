"""Decision rules over case features, family-weighted metrics, and the search used on the
development half.

A rule is a JSON-able dict:
  {"type": "single", "feature": f, "direction": +1|-1, "threshold": t}
      flags a case when direction * value >= direction * t  (a missing value never flags)
  {"type": "and" | "or", "terms": [single, single]}

Family weighting: every case family carries total weight 1, split equally across its cases,
so a ring with 18 weekly cases counts as much as a seller with one.
"""

from __future__ import annotations

import itertools
from typing import Iterable

import numpy as np
import pandas as pd

from features import DIRECTION, FEATURES


def family_weights(df: pd.DataFrame) -> np.ndarray:
    counts = df.groupby("family")["case_id"].transform("count").to_numpy(dtype=float)
    return 1.0 / counts


def apply_single(df: pd.DataFrame, term: dict) -> np.ndarray:
    x = df[term["feature"]].to_numpy(dtype=float)
    d = term["direction"]
    with np.errstate(invalid="ignore"):
        out = d * x >= d * term["threshold"]
    return np.where(np.isnan(x), False, out)


def apply_rule(df: pd.DataFrame, rule: dict) -> np.ndarray:
    if rule["type"] == "single":
        return apply_single(df, rule)
    parts = [apply_single(df, t) for t in rule["terms"]]
    return np.logical_and(*parts) if rule["type"] == "and" else np.logical_or(*parts)


def metrics(pred: np.ndarray, y: np.ndarray, w: np.ndarray | None = None) -> dict:
    w = np.ones_like(y, dtype=float) if w is None else w
    pos, neg = y == 1, y == 0
    tpr = float((w * pred * pos).sum() / (w * pos).sum()) if pos.any() else float("nan")
    fpr = float((w * pred * neg).sum() / (w * neg).sum()) if neg.any() else float("nan")
    return {"tpr": tpr, "fpr": fpr, "balanced_accuracy": 0.5 * (tpr + (1 - fpr))}


def weighted_auc(score: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    """Probability that a random positive outscores a random negative (ties count half),
    with cases weighted by w. Missing scores are dropped."""
    ok = ~np.isnan(score)
    s, yy, ww = score[ok], y[ok], w[ok]
    sp, wp = s[yy == 1], ww[yy == 1]
    sn, wn = s[yy == 0], ww[yy == 0]
    if len(sp) == 0 or len(sn) == 0:
        return float("nan")
    gt = (sp[:, None] > sn[None, :]).astype(float) + 0.5 * (sp[:, None] == sn[None, :])
    return float((wp[:, None] * wn[None, :] * gt).sum() / (wp.sum() * wn.sum()))


def candidate_thresholds(x: np.ndarray) -> list[float]:
    v = np.unique(x[~np.isnan(x)])
    if len(v) == 0:
        return []
    mids = list((v[:-1] + v[1:]) / 2)
    return [float(v[0] - 1e-9)] + [float(m) for m in mids] + [float(v[-1] + 1e-9)]


def term_margin(x: np.ndarray, t: float, scale: float) -> float:
    v = x[~np.isnan(x)]
    if len(v) == 0:
        return 0.0
    return float(np.min(np.abs(v - t)) / scale) if scale > 0 else 0.0


def search(dev: pd.DataFrame, features: Iterable[str] = FEATURES, pairs: bool = True, top: int = 25) -> list[dict]:
    """Every single-feature rule and every two-feature AND / OR rule, scored by family-weighted
    balanced accuracy on dev. Ties: fewer features, then larger margin (distance from the
    threshold to the nearest dev value, as a share of that feature's dev range), then name."""
    features = list(features)
    y = dev["y"].to_numpy()
    w = family_weights(dev)
    X = {f: dev[f].to_numpy(dtype=float) for f in features}
    scale = {f: float(np.nanmax(X[f]) - np.nanmin(X[f])) if np.isfinite(X[f]).any() else 1.0 for f in features}
    singles = []
    for f in features:
        for t in candidate_thresholds(X[f]):
            term = {"type": "single", "feature": f, "direction": DIRECTION[f], "threshold": t}
            pred = apply_single(dev, term)
            m = metrics(pred, y, w)
            singles.append((term, pred, m, term_margin(X[f], t, scale[f])))
    scored = [(m["balanced_accuracy"], -1, mg, term["feature"], term, m) for term, _, m, mg in singles]
    if pairs:
        by_feature: dict[str, list] = {}
        for item in singles:
            by_feature.setdefault(item[0]["feature"], []).append(item)
        for f1, f2 in itertools.combinations(features, 2):
            for (t1, p1, _, m1), (t2, p2, _, m2) in itertools.product(by_feature.get(f1, []), by_feature.get(f2, [])):
                for op, pred in (("and", p1 & p2), ("or", p1 | p2)):
                    m = metrics(pred, y, w)
                    rule = {"type": op, "terms": [t1, t2]}
                    scored.append((m["balanced_accuracy"], -2, min(m1, m2), f"{op}:{f1}+{f2}", rule, m))
    scored.sort(key=lambda s: (-s[0], -s[1], -s[2], s[3]))
    out = []
    for ba, nfeat, mg, name, rule, m in scored[:top]:
        out.append({"rule": rule, "name": name, "n_features": -nfeat, "margin": mg, **{f"dev_{k}": v for k, v in m.items()}})
    return out


def describe(rule: dict) -> str:
    def one(t: dict) -> str:
        op = ">=" if t["direction"] > 0 else "<="
        return f"{t['feature']} {op} {t['threshold']:.4g}"

    if rule["type"] == "single":
        return one(rule)
    return f" {rule['type'].upper()} ".join(one(t) for t in rule["terms"])
