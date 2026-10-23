"""End-to-end positive control: synthetic rings in the transfer data, the real extraction and features.

Added Oct 23 to 24, 2026, after the freeze (plan: cases/market_plan.md, section 5). The positive
control in src/controls.py edits the per-case tables and sets each ring payer's hop distance by
hand, so it never runs the reach walk. Here a seller-funded ring is written as USDC transfers and
EIP-3009 authorisations into the data that src/extract_base.py reads; extract_window and write_case
then run unchanged (K = 6, as for the committed case tables), and src/features.py computes the
features (K = 4).

The synthetic rows live in tables of a scratch DuckDB file whose `tr` and `auth` are views over
data/base.duckdb (attached read-only) plus those tables. The base data is therefore never written;
its row counts are checked before and after, and the scratch file is deleted at the end.

Hub status: the hub table is copied from data/base.duckdb. The ring adds counterparties only to the
seller and to the hub address used by two routes (already a hub), and to new synthetic wallets, so
no hub status can change as long as the seller stays below 1,000 - RING_CP counterparties, which is
asserted.

  python src/positive_control_e2e.py
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import extract_base as eb
from cases import Case, LOOKBACK_DAYS, base_block_at, load_registry, window_bounds
from features import compute_features, loop_share
from rules import apply_rule
from run_features import load_case

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("pc_e2e")
MARKETS = [("F10-clashofcoins", "0x93862e5b2b1fa10a01772e7e9ca7cdc7deb5ca25", "W1"),
           ("F12-stableenrich", "0x325bdf6f7efab24a2210c48c1b64cab2eae1d430", "W1"),
           ("F16-cheaptokens", "0x213c8d7434e2ae7aa1c392767c5120778d413215", "W4")]
ROUTES = {"direct": 1, "relay3": 3, "relay4": 4, "relay5": 5, "via_hub": None, "via_forwarder": 1}
BASE_PHIS = [0.1, 0.3, 0.5]
N_RING = 5
MAX_PAYMENTS_PER_PAYER = 300
TXI0 = 900_000  # synthetic transaction indexes start here; no Base block has this many transactions
RING_CP = 2 * N_RING + 5
K_EXTRACT = 6


def connect(scratch: Path) -> duckdb.DuckDBPyConnection:
    scratch.parent.mkdir(parents=True, exist_ok=True)
    for p in (scratch, scratch.with_suffix(".duckdb.wal")):
        p.unlink(missing_ok=True)
    con = duckdb.connect(str(scratch))
    con.execute("SET memory_limit='6GB'; SET threads=6; SET preserve_insertion_order=false")
    con.execute(f"ATTACH '{ROOT / 'data' / 'base.duckdb'}' AS b (READ_ONLY)")
    con.execute("CREATE TABLE syn_tr (block INTEGER, txi INTEGER, li INTEGER, src VARCHAR, dst VARCHAR, val HUGEINT)")
    con.execute("CREATE TABLE syn_auth (block INTEGER, txi INTEGER, li INTEGER, authorizer VARCHAR, nonce VARCHAR)")
    con.execute("CREATE VIEW tr AS SELECT * FROM b.tr UNION ALL SELECT * FROM syn_tr")
    con.execute("CREATE VIEW auth AS SELECT * FROM b.auth UNION ALL SELECT * FROM syn_auth")
    for w in ("W1", "W2", "W3", "W4"):
        con.execute(f"CREATE TABLE deg_{w} AS SELECT * FROM b.deg_{w}")
    return con


def base_counts(con: duckdb.DuckDBPyConnection) -> dict:
    return {"tr": con.execute("SELECT count(*) FROM b.tr").fetchone()[0], "auth": con.execute("SELECT count(*) FROM b.auth").fetchone()[0]}


def run_case(con: duckdb.DuckDBPyConnection, family: str, payee: str, w: str, out: Path) -> tuple[dict, Path]:
    bounds = eb.extract_window(con, w, [payee], 1000, K_EXTRACT)
    case = Case(case_id=f"{family}|{payee}|{w}", family=family, chain="base", market="x402", label="pc", y=-1,
                payee=payee, window=w, half="pc")
    shutil.rmtree(out / case.case_id.replace("|", "__"), ignore_errors=True)
    eb.write_case(con, case, payee, out, bounds, 1000, K_EXTRACT)
    return bounds, out / case.case_id.replace("|", "__")


def ring_rows(payee: str, w: str, route: str, phi: float, amounts: np.ndarray, V: float, hub: str, seed: int) -> tuple[list, list, dict]:
    """Synthetic transfers and authorisations for one ring; values in micro-USDC."""
    reg = load_registry()
    t0, _, w0, w1 = window_bounds(reg, w)
    d0 = base_block_at(t0 - LOOKBACK_DAYS * 86400)
    rng = np.random.default_rng(seed)
    R = phi / (1.0 - phi) * V
    budget = R / N_RING
    tr, au = [], []
    txi = TXI0
    injected = 0
    hops = ROUTES[route]
    typical = float(np.median(amounts))
    for j in range(N_RING):
        payer = f"0x5e{seed:06x}{j:02x}{'ab' * 15}"[:42]
        n = int(min(MAX_PAYMENTS_PER_PAYER, max(1, math.ceil(budget / max(typical, 1e-9)))))
        a = rng.choice(amounts, size=n)
        a = np.maximum(1, np.round(a * (budget / a.sum()) * 1e6)).astype(np.int64)
        pay_blocks = np.sort(rng.integers(w0 + 2000, w1, size=n))
        fund = int(a.sum())
        fb = int(rng.integers(d0, w0 - 2000))  # funding inside the lookback, one transaction per hop
        if route == "via_forwarder":
            tr += [(fb, txi, 0, payee, hub, fund), (fb, txi, 1, hub, payer, fund)]
            txi += 1
        elif route == "via_hub":
            tr += [(fb, txi, 0, payee, hub, fund), (fb + 5, txi + 1, 0, hub, payer, fund)]
            txi += 2
        else:
            chain = [payee] + [f"0x5f{seed:06x}{j:02x}{k:02x}{'cd' * 14}"[:42] for k in range(1, hops)] + [payer]
            for k in range(len(chain) - 1):
                tr.append((fb + 5 * k, txi, 0, chain[k], chain[k + 1], fund))
                txi += 1
        for b, v in zip(pay_blocks, a):
            au.append((int(b), txi, 0, payer, f"syn{seed}-{txi}"))
            tr.append((int(b), txi, 1, payer, payee, int(v)))
            txi += 1
        injected += fund
    return tr, au, {"ring_payers": N_RING, "injected_value": injected / 1e6, "phi_actual": (injected / 1e6) / (injected / 1e6 + V)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scratch = ROOT / "data" / "scratch" / "pc_e2e.duckdb"
    out = ROOT / "data" / "scratch" / "pc_e2e_cases"
    out.mkdir(parents=True, exist_ok=True)
    frozen = json.loads((ROOT / "results" / "frozen_rule.json").read_text())
    thr = frozen["rule"]["threshold"]
    committed = pd.read_csv(ROOT / "results" / "case_features.csv").set_index("case_id")
    base_file = ROOT / "data" / "base.duckdb"
    stat0 = (base_file.stat().st_size, base_file.stat().st_mtime_ns)
    con = connect(scratch)
    counts0 = base_counts(con)
    rows = []
    for mi, (family, payee, w) in enumerate(MARKETS):
        t = time.time()
        con.execute("DELETE FROM syn_tr; DELETE FROM syn_auth")
        _, d = run_case(con, family, payee, w, out / "baseline")
        cd0 = load_case(d)
        V = float(cd0.payments["value"].sum())
        b = loop_share(cd0)
        ref = committed.loc[f"{family}|{payee}|{w}", "loop_share"]
        deg = con.execute(f"SELECT d FROM deg_{w} WHERE a = ?", [payee]).fetchone()
        if deg and deg[0] >= 1000 - RING_CP and deg[0] < 1000:
            raise SystemExit(f"{family}: seller degree {deg[0]} too close to the hub threshold")
        hub = con.execute(f"SELECT a FROM deg_{w} WHERE d >= 1000 ORDER BY d DESC, a LIMIT 1").fetchone()[0]
        phi_star = (thr - b) / (1 - b)
        phis = BASE_PHIS + [round(phi_star - 0.02, 4), round(phi_star + 0.02, 4)]
        amounts = cd0.payments["value"].to_numpy(dtype=float)
        log.info("%s: baseline loop share %.6f (committed %.6f), volume %.2f, phi* %.4f, hub %s", family, b, ref, V, phi_star, hub)
        rows.append({"market": family, "window": w, "route": "none", "phi_target": 0.0, "phi_actual": 0.0, "baseline_b": b,
                     "committed_b": float(ref), "expected_loop_share": float(ref), "measured_loop_share": b, "designed_hop": None,
                     "ring_hops_measured": "", "ring_payments_injected": 0, "ring_payments_extracted": 0,
                     "expected_flag": bool(ref >= thr), "measured_flag": bool(b >= thr)})
        for ri, route in enumerate(ROUTES):
            for pi, phi in enumerate(phis):
                seed = 1000 * mi + 100 * ri + pi
                con.execute("DELETE FROM syn_tr; DELETE FROM syn_auth")
                trs, aus, info = ring_rows(payee, w, route, phi, amounts, V, hub, seed)
                con.executemany("INSERT INTO syn_tr VALUES (?, ?, ?, ?, ?, ?)", trs)
                con.executemany("INSERT INTO syn_auth VALUES (?, ?, ?, ?, ?)", aus)
                _, d = run_case(con, family, payee, w, out / f"{route}_{phi:.4f}")
                cd = load_case(d)
                f = compute_features(cd, k=4, n_null=20)
                ring = sorted({a[3] for a in aus})
                hops = {r: cd.payer_reach.get(r) for r in ring}
                reached = ROUTES[route] is not None and ROUTES[route] <= 4  # K = 4
                pa = info["phi_actual"]
                exp = pa + (1 - pa) * b if reached else (1 - pa) * b
                n_extracted = int(cd.payments["payer"].isin(ring).sum())
                rows.append({"market": family, "window": w, "route": route, "phi_target": phi, "phi_actual": pa, "baseline_b": b,
                             "committed_b": float(ref), "expected_loop_share": exp, "measured_loop_share": f["loop_share"],
                             "designed_hop": ROUTES[route], "ring_hops_measured": ";".join("none" if hops[r] is None else str(hops[r]) for r in ring),
                             "ring_payments_injected": len(aus), "ring_payments_extracted": n_extracted,
                             "outside_funding_share": f["outside_funding_share"],
                             "expected_flag": bool(exp >= thr), "measured_flag": bool(f["loop_share"] >= thr)})
                log.info("%s %s phi=%.4f: expected %.6f measured %.6f hops %s", family, route, phi, exp, f["loop_share"], sorted(set(hops.values()), key=str))
        log.info("%s done in %.0fs", family, time.time() - t)
    con.execute("DELETE FROM syn_tr; DELETE FROM syn_auth")
    counts1 = base_counts(con)
    con.close()
    for p in (scratch, scratch.with_suffix(".duckdb.wal")):
        p.unlink(missing_ok=True)
    shutil.rmtree(out, ignore_errors=True)
    stat1 = (base_file.stat().st_size, base_file.stat().st_mtime_ns)
    df = pd.DataFrame(rows)
    df["abs_error"] = (df["measured_loop_share"] - df["expected_loop_share"]).abs()
    df.to_csv(ROOT / "results" / "positive_control_e2e.csv", index=False, float_format="%.8g")
    runs = df[df["route"] != "none"]
    summ = {
        "markets": [m[0] for m in MARKETS], "runs": int(len(runs)), "max_abs_error": float(runs["abs_error"].max()),
        "flag_matches_expected": int((runs["expected_flag"] == runs["measured_flag"]).sum()),
        "hops_as_designed": int(sum(
            all((h == "none" if r.designed_hop is None or (isinstance(r.designed_hop, float) and math.isnan(r.designed_hop)) else h == str(int(r.designed_hop)))
                for h in r.ring_hops_measured.split(";"))
            for r in runs.itertuples())),
        "ring_payments_all_extracted": bool((runs["ring_payments_injected"] == runs["ring_payments_extracted"]).all()),
        # results/case_features.csv keeps 6 significant digits
        "baseline_matches_committed": bool((df[df["route"] == "none"]["measured_loop_share"] - df[df["route"] == "none"]["committed_b"]).abs().max() < 1e-6),
        "base_row_counts_before": counts0, "base_row_counts_after": counts1,
        "base_file_unchanged": stat0 == stat1, "scratch_deleted": not scratch.exists(),
    }
    (ROOT / "results" / "positive_control_e2e_summary.json").write_text(json.dumps(summ, indent=2) + "\n")
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
