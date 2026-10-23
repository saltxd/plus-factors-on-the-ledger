"""Blinded spot-check of the frozen rule on Base payees the published decodes did not examine.

Added Oct 23 to 24, 2026, after the freeze (plan: cases/market_plan.md, section 3).

  draw     eligible payee-weeks -> 25 flagged and 15 unflagged distinct payees (seed 20261024),
           shuffled into S01..S40. Writes the blinded list results/spotcheck_sample.csv and the key
           (stratum per sample) to --sealed, outside the repository, until the verdicts are committed.
  unblind  joins the committed verdict files with the key and the market features
           -> results/spotcheck_unblinded.csv, results/spotcheck_summary.json

  python src/spotcheck.py draw --features <market features csv> --sealed <dir>
  python src/spotcheck.py unblind --features results/market_base_features.csv --key <dir>/spotcheck_key.csv
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261024
N_FLAGGED, N_UNFLAGGED, TOP_EXCLUDED = 25, 15, 30
WINDOW_DATES = {"W1": ("2026-09-15", "2026-09-22", 51320527, 51622926), "W2": ("2026-09-22", "2026-09-29", 51622927, 51925326),
                "W3": ("2026-09-29", "2026-10-06", 51925327, 52227726), "W4": ("2026-10-06", "2026-10-13", 52227727, 52530126)}


def examined_payees(pop: pd.DataFrame) -> set[str]:
    """Payees printed in a decode (full or prefix), registered as a case, or in a window's top 30."""
    toks = [t.strip() for t in (ROOT / "data" / "decode_printed_hex.txt").read_text().split() if t.strip()]
    reg = yaml.safe_load((ROOT / "cases" / "cases.yaml").read_text())
    for fam in reg["families"]:
        for e in fam["payees"]:
            a = e["address"] if isinstance(e, dict) else e
            if a.startswith("prefix:"):
                toks.append(a.split(":", 1)[1].lower())
            elif a.startswith("0x"):
                toks.append(a.lower())
    out = {p for p in pop["payee"].unique() if any(p.startswith(t) for t in toks)}
    out |= set(pop.loc[pop["rank"] <= TOP_EXCLUDED, "payee"])
    return out


def eligible(features: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    thr = frozen["rule"]["threshold"]
    f = features[["payee", "window", "loop_share"]].copy()
    f["flag"] = f["loop_share"] >= thr
    ex = examined_payees(pop)
    units = pop[["window", "payee", "rank", "x402_volume"]].merge(f, on=["payee", "window"], how="inner")
    units["examined"] = units["payee"].isin(ex)
    return units


def draw(features_csv: Path, sealed: Path) -> None:
    pop = pd.read_csv(ROOT / "results" / "market_base_population.csv")
    feats = pd.read_csv(features_csv)
    units = eligible(feats, pop)
    el = units[~units["examined"] & units["loop_share"].notna()]
    rng = np.random.default_rng(SEED)
    picks = []
    fl = sorted(el.loc[el["flag"], "payee"].unique())
    for i in sorted(rng.choice(len(fl), size=min(N_FLAGGED, len(fl)), replace=False)):
        p = fl[i]
        weeks = sorted(el.loc[el["flag"] & (el["payee"] == p), "window"])
        picks.append((p, weeks[int(rng.integers(len(weeks)))], "flagged"))
    taken = {p for p, _, _ in picks}
    un = sorted(set(el.loc[~el["flag"], "payee"]) - taken)
    for i in sorted(rng.choice(len(un), size=min(N_UNFLAGGED, len(un)), replace=False)):
        p = un[i]
        weeks = sorted(el.loc[~el["flag"] & (el["payee"] == p), "window"])
        picks.append((p, weeks[int(rng.integers(len(weeks)))], "unflagged"))
    order = rng.permutation(len(picks))
    rows = []
    for k, j in enumerate(order, 1):
        p, w, stratum = picks[j]
        d = WINDOW_DATES[w]
        rows.append({"sample_id": f"S{k:02d}", "payee": p, "window": w, "window_start_utc": d[0], "window_end_utc": d[1],
                     "first_block": d[2], "last_block": d[3], "stratum": stratum})
    df = pd.DataFrame(rows)
    sealed.mkdir(parents=True, exist_ok=True)
    df.to_csv(sealed / "spotcheck_key.csv", index=False)
    df.drop(columns=["stratum"]).to_csv(ROOT / "results" / "spotcheck_sample.csv", index=False)
    meta = {"eligible_payee_weeks": int(len(el)), "eligible_payees": int(el["payee"].nunique()),
            "eligible_flagged_payees": len(fl), "eligible_unflagged_payees": len(un) + len(taken & set(el.loc[~el["flag"], "payee"])),
            "examined_payees_excluded": int(units.loc[units["examined"], "payee"].nunique()), "drawn": len(df), "seed": SEED}
    (sealed / "spotcheck_draw_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"drew {len(df)} payees into results/spotcheck_sample.csv; key and counts in {sealed}")


def exact_ci(k: int, n: int, a: float = 0.05) -> list[float]:
    """Clopper-Pearson interval without scipy: invert the binomial tail by bisection."""
    def cdf(x: int, p: float) -> float:
        return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, x + 1))

    def solve(f, lo=0.0, hi=1.0):
        for _ in range(100):
            mid = (lo + hi) / 2
            if f(mid):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: 1 - cdf(k - 1, p) < a / 2)
    upper = 1.0 if k == n else solve(lambda p: cdf(k, p) > a / 2)
    return [lower, upper]


def unblind(features_csv: Path, key_csv: Path) -> None:
    key = pd.read_csv(key_csv)
    feats = pd.read_csv(features_csv)
    v = pd.read_csv(ROOT / "results" / "spotcheck_verdicts.csv")
    df = key.merge(v, on=["sample_id", "payee", "window"], how="left")
    cols = ["payee", "window", "n_payers", "volume", "loop_share", "loop_share_1hop", "outside_funding_share", "shared_funder_share",
            "payer_hhi", "reach_capped"]
    df = df.merge(feats[cols], on=["payee", "window"], how="left")
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    df["flag_primary"] = df["loop_share"] >= frozen["rule"]["threshold"]
    if not (df["flag_primary"] == (df["stratum"] == "flagged")).all():
        raise SystemExit("key and features disagree")
    judges = sorted(c.split("verdict_", 1)[1] for c in v.columns if c.startswith("verdict_"))
    summ = {"judges": judges, "n": int(len(df)), "flagged": int(df["flag_primary"].sum()), "unflagged": int((~df["flag_primary"]).sum())}
    for j in judges:
        col = f"verdict_{j}"
        for stratum, sub in (("flagged", df[df["flag_primary"]]), ("unflagged", df[~df["flag_primary"]])):
            k = int((sub[col] == "coordinated").sum())
            n = len(sub)
            summ[f"{j}_{stratum}"] = {"coordinated": k, "independent": int((sub[col] == "independent").sum()),
                                      "unclear": int((sub[col] == "unclear").sum()), "n": n,
                                      "share_coordinated": k / n if n else None, "ci95": exact_ci(k, n) if n else None}
        agree = ((df[col] == "coordinated") & df["flag_primary"]) | ((df[col] == "independent") & ~df["flag_primary"])
        summ[f"{j}_agrees_with_rule"] = int(agree.sum())
        summ[f"{j}_unclear"] = int((df[col] == "unclear").sum())
    if len(judges) >= 2:
        a, b = (f"verdict_{judges[0]}", f"verdict_{judges[1]}")
        summ["judges_agree"] = int((df[a] == df[b]).sum())
        both = df[(df[a] == df[b]) & (df[a] != "unclear")]
        summ["consensus_n"] = int(len(both))
        summ["consensus_agrees_with_rule"] = int((((both[a] == "coordinated") & both["flag_primary"]) |
                                                  ((both[a] == "independent") & ~both["flag_primary"])).sum())
        for stratum, sub in (("flagged", both[both["flag_primary"]]), ("unflagged", both[~both["flag_primary"]])):
            k = int((sub[a] == "coordinated").sum())
            summ[f"consensus_{stratum}"] = {"coordinated": k, "n": int(len(sub)), "ci95": exact_ci(k, len(sub)) if len(sub) else None}
    df.sort_values("sample_id").to_csv(ROOT / "results" / "spotcheck_unblinded.csv", index=False, float_format="%.4g")
    (ROOT / "results" / "spotcheck_summary.json").write_text(json.dumps(summ, indent=2) + "\n")
    print(json.dumps(summ, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["draw", "unblind"])
    ap.add_argument("--features", required=True)
    ap.add_argument("--sealed")
    ap.add_argument("--key")
    a = ap.parse_args()
    if a.stage == "draw":
        draw(Path(a.features), Path(a.sealed))
    else:
        unblind(Path(a.features), Path(a.key))


if __name__ == "__main__":
    main()
