"""Prevalence of the frozen rule over the whole market, and its agreement with Agent402's index.

Added Oct 23 to 24, 2026, after the freeze (plan: cases/market_plan.md, sections 1, 2 and 4).
Reads the population and feature tables written by src/market_base.py and src/market_bsc.py,
Agent402's published top ten of Oct 13 (data/agent402_board_2026-10-13.csv, the table printed in
[D4]) and Agent402's index verdicts (data/raw/agent402/base_verdicts.csv, pull/agent402_index.py).
Writes results/market_summary.json.

  python src/market_summary.py --features results/market_base_features.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from rules import apply_rule

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
# ChainWard's own published weekly x402 totals and loop tiers (decodes D1 and D2); context only
DECODE_WEEKS = {
    "W1": {"x402_usd": 128252.0, "x402_usd_as_published": 128977.37, "verified_loops_share_min": 0.468,
           "round_trip_share": 0.234, "source": "x402-on-base-two-weeks-later (same method), x402-on-base"},
    "W2": {"x402_usd": 232810.0, "verified_loops_share_min": 0.257, "round_trip_share": 0.232, "source": "x402-on-base-two-weeks-later"},
    "W3": {"x402_usd": 109151.0, "verified_loops_share_min": 0.406, "round_trip_share": 0.071, "source": "x402-on-base-two-weeks-later"},
}


def flags(df: pd.DataFrame, frozen: dict) -> pd.DataFrame:
    df = df.copy()
    df["flag_primary"] = apply_rule(df, frozen["rule"])
    df["flag_non_circular"] = apply_rule(df, frozen["non_circular_rule"])
    df["flag_outside_funding"] = apply_rule(df, frozen["best_single_feature_rules"]["outside_funding_share"]["rule"])
    return df


def shares(g: pd.DataFrame, vol: str) -> dict:
    out = {"payee_weeks": int(len(g)), "volume": float(g[vol].sum())}
    for f in ("flag_primary", "flag_non_circular", "flag_outside_funding"):
        out[f] = {"count": int(g[f].sum()), "share": float(g[f].mean()) if len(g) else None,
                  "volume": float(g.loc[g[f], vol].sum()), "volume_share": float(g.loc[g[f], vol].sum() / g[vol].sum()) if len(g) else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default=str(RES / "market_base_features.csv"))
    ap.add_argument("--out", default=str(RES), help="where market_summary.json and market_agent402_comparison.csv go")
    a = ap.parse_args()
    out_dir = Path(a.out)
    frozen = json.loads((RES / "frozen_rule.json").read_text())
    pop = pd.read_csv(RES / "market_base_population.csv")
    feats = pd.read_csv(a.features)
    base = pop.merge(feats.drop(columns=["volume"], errors="ignore"), on=["payee", "window"], how="left", validate="one_to_one")
    missing = base["loop_share"].isna()
    base = flags(base[~missing], frozen)
    hop_cap = base["reach_by_hop"].map(lambda s: max((h for h, _ in json.loads(s)), default=0) if isinstance(s, str) else 0)
    out: dict = {"base": {"floor_usd": 10.0, "payee_weeks_in_population": int(len(pop)), "without_features": int(missing.sum()),
                          "distinct_payees": int(base["payee"].nunique()),
                          "reach_capped": int(base["reach_capped"].sum()), "reach_capped_before_hop4": int((base["reach_capped"] & (hop_cap < 4)).sum()),
                          "pooled": shares(base, "x402_volume"), "by_window": {}, "by_band": {}, "top": {}}}
    for w, g in base.groupby("window"):
        out["base"]["by_window"][w] = shares(g, "x402_volume")
        out["base"]["by_window"][w]["decode_reference"] = DECODE_WEEKS.get(w)
        top = g.sort_values("x402_volume", ascending=False).iloc[0]
        rest = g[g["payee"] != top["payee"]]
        out["base"]["by_window"][w]["largest_payee"] = {
            "payee": top["payee"], "x402_volume": float(top["x402_volume"]), "share_of_window": float(top["x402_volume"] / g["x402_volume"].sum()),
            "n_payments": int(top["n_payments"]), "flag_primary": bool(top["flag_primary"]),
            "volume_share_flagged_without_it": float(rest.loc[rest["flag_primary"], "x402_volume"].sum() / rest["x402_volume"].sum())}
    for b, g in base.groupby("band"):
        out["base"]["by_band"][b] = shares(g, "x402_volume")
    for n in (10, 50):
        g = base[base["rank"] <= n]
        out["base"]["top"][f"top{n}"] = {"pooled": shares(g, "x402_volume"),
                                          "by_window": {w: shares(gg, "x402_volume") for w, gg in g.groupby("window")}}
    flagged_payees = base.groupby("payee")["flag_primary"].any()
    out["base"]["distinct_payees_flagged_any_week"] = int(flagged_payees.sum())
    # Agent402's published top ten of Oct 13, 01:19 UTC (7 days, close to W4)
    board = pd.read_csv(ROOT / "data" / "agent402_board_2026-10-13.csv")
    w4 = base[base["window"] == "W4"].set_index("payee")
    board["in_population_w4"] = board["payto"].isin(w4.index)
    board["flag_primary_w4"] = board["payto"].map(w4["flag_primary"]).fillna(False).astype(bool)
    board["x402_volume_w4"] = board["payto"].map(w4["x402_volume"])
    out["agent402_board_2026_10_13"] = {
        "rows": board[["rank", "payto", "board_usdc", "x402_volume_w4", "flag_primary_w4"]].to_dict("records"),
        "board_usdc": float(board["board_usdc"].sum()),
        "flagged_board_usdc": float(board.loc[board["flag_primary_w4"], "board_usdc"].sum()),
        "flagged_share_of_board_usdc": float(board.loc[board["flag_primary_w4"], "board_usdc"].sum() / board["board_usdc"].sum()),
        "flagged_ranks": board.loc[board["flag_primary_w4"], "rank"].tolist(),
    }
    # Agent402's index: settlement_self_funded verdict vs the rule (any week)
    idx = pd.read_csv(ROOT / "data" / "raw" / "agent402" / "base_verdicts.csv")
    idx = idx[idx["base_verdicts"].fillna("").str.contains("settlement_")]
    m = pd.DataFrame({"payee": flagged_payees.index, "rule_flag_any_week": flagged_payees.values}).merge(
        idx[["payto", "base_verdicts", "settlement_self_funded"]], left_on="payee", right_on="payto", how="inner")
    m["agent402_self_funded"] = m["settlement_self_funded"].astype(bool)
    ct = pd.crosstab(m["rule_flag_any_week"], m["agent402_self_funded"])
    out["agent402_index"] = {
        "index_as_of": sorted(set(";".join(pd.read_csv(ROOT / "data" / "raw" / "agent402" / "base_verdicts.csv")["index_as_of"].dropna()).split(";")))[:2],
        "market_payees_with_a_settlement_verdict": int(len(m)),
        "crosstab_rule_by_agent402": {f"rule_{bool(r)}": {f"agent402_self_funded_{bool(c)}": int(ct.loc[r, c]) if (r in ct.index and c in ct.columns) else 0
                                                        for c in (False, True)} for r in (False, True)},
    }
    m[["payee", "rule_flag_any_week", "agent402_self_funded", "base_verdicts"]].sort_values("payee").to_csv(out_dir / "market_agent402_comparison.csv", index=False)
    # BNB Chain
    bsc = pd.read_csv(RES / "market_bsc_features.csv")
    bsc = flags(bsc, frozen)
    out["bsc"] = {"pooled": shares(bsc, "volume"), "ring_wallets": shares(bsc[bsc["ring_wallet"]], "volume"),
                  "other_payees": shares(bsc[~bsc["ring_wallet"]], "volume"),
                  "decode_reference": {"share_of_budgets_from_wallets_classed_cycling_and_linked": 0.901, "source": "set-and-earn-week-one-closed",
                                       "note": "ChainWard's own published class (timing and funding links), not the rule's evidence"}}
    (out_dir / "market_summary.json").write_text(json.dumps(out, indent=2, default=float) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "agent402_board_2026_10_13"}, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
