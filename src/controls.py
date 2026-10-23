"""Controls for the frozen rule.

1. Positive control: inject a synthetic seller-funded ring with known parameters into the real
   payment graph of a market the decodes did not label coordinated, and record whether the frozen
   rule flags it. Parameters: the ring's share of the seller's volume (phi), the route the
   seller's money takes to the ring's payers, 5 ring payers, 10 random seeds per setting.
     direct        seller -> ring payer -> seller
     relay2        seller -> relay -> ring payer -> seller
     relay4        three relays (4 hops, the reach limit)
     relay5        four relays (5 hops, one beyond the reach limit)
     via_hub       seller -> an exchange-like hub -> ring payer (hubs are not followed)
     common_funder one outside wallet the seller never paid funds the 5 payers (parallel
                   conduct: a shared funder and no loop; a rule built on loops should not flag it)
2. Negative control: each payer's payment times circularly shifted inside the window, so any
   timing dependence is destroyed while amounts, payers and the graph stay as they were.
3. Permutation test: every way of choosing which test families are "coordinated" (keeping
   their number), scored with the frozen rule; the share that does at least as well as the real
   labels is an exact p-value for the test result.
"""

from __future__ import annotations

import itertools
import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from features import CaseData, compute_features
from rules import apply_rule, family_weights, metrics
from run_features import load_case

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("controls")

PHIS = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
ROUTES = {"direct": 1, "relay2": 2, "relay4": 4, "relay5": 5, "via_hub": None, "common_funder": None}
N_RING = 5
SEEDS = range(10)
MAX_PAYMENTS_PER_PAYER = 300


def inject(cd: CaseData, phi: float, route: str, seed: int, m: int = N_RING) -> CaseData:
    rng = np.random.default_rng(seed)
    pay = cd.payments
    V = float(pay["value"].sum())
    R = phi / (1.0 - phi) * V
    budget = R / m
    amounts = pay["value"].to_numpy(dtype=float)
    hops = ROUTES[route]
    six_h = 6 * 3600
    new_pay, new_inf, new_out, reach = [], [], [], dict(cd.payer_reach)
    order0 = int(cd.payer_inflows["order"].max()) + 1 if len(cd.payer_inflows) else 0
    for j in range(m):
        payer = f"syn{seed}_{route}_{j}"
        tf = int(rng.integers(cd.t0, max(cd.t0 + 1, cd.t1 - six_h)))
        typical = float(np.median(amounts)) if len(amounts) else 1.0
        n = int(min(MAX_PAYMENTS_PER_PAYER, max(1, math.ceil(budget / max(typical, 1e-9)))))
        a = rng.choice(amounts, size=n) if len(amounts) else np.ones(n)
        a = a * (budget / a.sum())
        times = np.sort(tf + rng.integers(30, six_h, size=n))
        times = np.minimum(times, cd.t1 - 1)
        new_pay += [(payer, float(x), int(t)) for x, t in zip(a, times)]
        if route == "common_funder":
            src, src_hops, is_hub, is_seller = f"syn{seed}_outside_funder", -1, 0, 0
        elif route == "via_hub":
            src, src_hops, is_hub, is_seller = "syn_hub", -1, 1, 0
            new_out.append(("syn_hub", budget, tf))
        else:
            src = cd.meta.get("payee", "seller") if hops == 1 else f"syn{seed}_{route}_{j}_relay{hops - 1}"
            src_hops, is_hub, is_seller = hops - 1, 0, int(hops == 1)
            first_hop = payer if hops == 1 else f"syn{seed}_{route}_{j}_relay1"
            new_out.append((first_hop, budget, tf - 60 * (hops - 1)))
        new_inf.append((payer, src, budget, tf, order0 + j, src_hops, 0, is_hub, is_seller))
        reach[payer] = hops if route not in ("via_hub", "common_funder") else None
    p2 = pd.concat([pay[["payer", "value", "ts"]], pd.DataFrame(new_pay, columns=["payer", "value", "ts"])], ignore_index=True)
    cols = ["payer", "src", "value", "ts", "order", "src_hops", "src_is_payer", "src_is_hub", "src_is_seller"]
    i2 = pd.concat([cd.payer_inflows[cols], pd.DataFrame(new_inf, columns=cols)], ignore_index=True)
    o2 = pd.concat([cd.seller_outflows[["dst", "value", "ts"]], pd.DataFrame(new_out, columns=["dst", "value", "ts"])], ignore_index=True)
    return CaseData(cd.case_id, p2, i2, o2, reach, cd.t0, cd.t1, cd.meta)


def shuffle_times(cd: CaseData, seed: int) -> CaseData:
    rng = np.random.default_rng(seed)
    p = cd.payments.copy()
    span = cd.t1 - cd.t0
    offs = {b: int(rng.integers(0, span)) for b in p["payer"].unique()}
    p["ts"] = cd.t0 + ((p["ts"] - cd.t0 + p["payer"].map(offs)) % span)
    return CaseData(cd.case_id, p, cd.payer_inflows, cd.seller_outflows, cd.payer_reach, cd.t0, cd.t1, cd.meta)


def _inject_one_case(args: tuple) -> list[dict]:
    case_dir, case_id, label, half = args
    cd = load_case(case_dir)
    rows = []
    for route in ROUTES:
        for phi in PHIS:
            for seed in SEEDS:
                f = compute_features(inject(cd, phi, route, seed), n_null=20)
                rows.append({"base_case": case_id, "base_label": label, "half": half, "route": route, "phi": phi, "seed": seed, **f})
    return rows


def positive_control(frozen: dict, cases_dir: Path, feats: pd.DataFrame) -> pd.DataFrame:
    """Base markets: every case the decodes did not label coordinated or linked (I, N) with at
    least 5 payers, both chains and both halves (the rule is frozen; this measures sensitivity)."""
    from multiprocessing import Pool

    base = feats[(feats["y"] == 0) & (feats["label"].isin(["I", "N"])) & (feats["n_payers"] >= 5)]
    jobs = [(cases_dir / r["case_id"].replace("|", "__"), r["case_id"], r["label"], r["half"]) for _, r in base.iterrows()]
    rows: list[dict] = []
    with Pool(min(8, max(1, len(jobs)))) as pool:
        for part in pool.imap_unordered(_inject_one_case, jobs):
            rows.extend(part)
            log.info("positive control done for %s", part[0]["base_case"] if part else "?")
    df = pd.DataFrame(rows)
    df["flag_primary"] = apply_rule(df, frozen["rule"])
    df["flag_non_circular"] = apply_rule(df, frozen["non_circular_rule"])
    return df


def negative_control(frozen: dict, cases_dir: Path, feats: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in feats.iterrows():
        cd = load_case(cases_dir / r["case_id"].replace("|", "__"))
        for seed in range(3):
            f = compute_features(shuffle_times(cd, 1000 + seed), n_null=50)
            rows.append({"case_id": r["case_id"], "family": r["family"], "label": r["label"], "y": r["y"], "half": r["half"], "seed": seed, **f})
    df = pd.DataFrame(rows)
    df["flag_primary"] = apply_rule(df, frozen["rule"])
    df["flag_non_circular"] = apply_rule(df, frozen["non_circular_rule"])
    return df


def permutation_test(frozen_rule: dict, feats: pd.DataFrame, half: str = "test") -> dict:
    part = feats[feats["half"] == half].reset_index(drop=True)
    pred = apply_rule(part, frozen_rule)
    w = family_weights(part)
    fams = sorted(part["family"].unique())
    fam_y = part.groupby("family")["y"].max()
    k = int(fam_y.sum())
    observed = metrics(pred, part["y"].to_numpy(), w)["balanced_accuracy"]
    scores = []
    for pos in itertools.combinations(fams, k):
        yy = part["family"].isin(pos).astype(int).to_numpy()
        scores.append(metrics(pred, yy, w)["balanced_accuracy"])
    scores = np.array(scores)
    return {
        "half": half,
        "families": len(fams),
        "coordinated_families": k,
        "label_assignments": int(len(scores)),
        "observed_balanced_accuracy": float(observed),
        "p_value": float((scores >= observed - 1e-12).mean()),
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--which", nargs="*", default=["positive", "negative", "permutation"])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    feats = pd.read_csv(ROOT / "results" / "case_features.csv")
    cases_dir = ROOT / "data" / "cases"
    out = ROOT / "results"
    if "positive" in args.which:
        pc = positive_control(frozen, cases_dir, feats)
        pc.to_csv(out / "positive_control.csv", index=False, float_format="%.6g")
        summ = pc.groupby(["route", "phi"])[["flag_primary", "flag_non_circular"]].mean().reset_index()
        summ.to_csv(out / "positive_control_summary.csv", index=False, float_format="%.4f")
        log.info("positive control summary:\n%s", summ.to_string())
    if "negative" in args.which:
        nc = negative_control(frozen, cases_dir, feats)
        nc.to_csv(out / "negative_control_timing_shuffle.csv", index=False, float_format="%.6g")
    if "boundary" in args.which:
        bc = boundary_check(frozen, cases_dir, feats)
        bc.to_csv(out / "positive_control_boundary.csv", index=False, float_format="%.6g")
        log.info("boundary:\n%s", bc.pivot_table(index="route", columns="phi", values="flag_primary", aggfunc="mean").to_string())
    if "permutation" in args.which:
        res = {
            "primary": permutation_test(frozen["rule"], feats, "test"),
            "non_circular": permutation_test(frozen["non_circular_rule"], feats, "test"),
        }
        (out / "permutation_test.json").write_text(json.dumps(res, indent=2) + "\n")
        log.info("permutation: %s", res)



def boundary_check(frozen: dict, cases_dir: Path, feats: pd.DataFrame) -> pd.DataFrame:
    """Supplement to the pre-set grid, added after it ran: the grid jumps from 30% to 50%, so the
    loop share of an injected ring (direct and 4-hop routes) is computed on a fine grid around the
    frozen threshold. Loop share is deterministic in the ring's share phi: phi + (1 - phi) * base."""
    from features import loop_share

    base = feats[(feats["y"] == 0) & (feats["label"].isin(["I", "N"])) & (feats["n_payers"] >= 5)].reset_index(drop=True)
    base = base[~apply_rule(base, frozen["rule"])]
    rows = []
    for _, r in base.iterrows():
        cd = load_case(cases_dir / r["case_id"].replace("|", "__"))
        b = float(r["loop_share"])
        for route in ("direct", "relay4"):
            for phi in [0.30, 0.35, 0.38, 0.40, 0.41, 0.42, 0.43, 0.44, 0.45, 0.50]:
                ls = loop_share(inject(cd, phi, route, seed=0))
                rows.append({"base_case": r["case_id"], "route": route, "phi": phi, "base_loop_share": b, "loop_share": ls,
                             "flag_primary": bool(apply_rule(pd.DataFrame([{"loop_share": ls}]), frozen["rule"])[0]),
                             "analytic_min_phi": (frozen["rule"]["threshold"] - b) / (1 - b)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()
