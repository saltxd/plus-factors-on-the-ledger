"""Unit tests for the evidence features on small hand-built cases."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from features import CaseData, compute_features, loop_share, outside_funding_share, payer_hhi, shared_funder_share, timing_coupling  # noqa: E402

T0, T1 = 1_000_000, 1_000_000 + 7 * 86400


def mk(payments, inflows, outflows, reach):
    p = pd.DataFrame(payments, columns=["payer", "value", "ts"])
    i = pd.DataFrame(inflows, columns=["payer", "src", "value", "ts", "order", "src_hops", "src_is_payer", "src_is_hub", "src_is_seller"])
    o = pd.DataFrame(outflows, columns=["dst", "value", "ts"])
    return CaseData("t", p, i, o, reach, T0, T1)


def test_seller_funded_buyers_are_a_loop():
    # seller S funds b1, b2 directly; b3 is funded from an exchange
    pay = [("b1", 10, T0 + 100), ("b2", 10, T0 + 200), ("b3", 20, T0 + 300)]
    inf = [
        ("b1", "S", 10, T0 + 50, 1, 1, 0, 0, 1),
        ("b2", "S", 10, T0 + 60, 2, 1, 0, 0, 1),
        ("b3", "EX", 20, T0 + 70, 3, -1, 0, 1, 0),
    ]
    out = [("b1", 10, T0 + 50), ("b2", 10, T0 + 60)]
    cd = mk(pay, inf, out, {"b1": 1, "b2": 1, "b3": None})
    assert loop_share(cd) == pytest.approx(0.5)
    assert outside_funding_share(cd) == pytest.approx(0.5)
    # S first-funded two payers: shared funder share = 20 / 40
    assert shared_funder_share(cd) == pytest.approx(0.5)
    # the exchange funded one payer only, so nothing else is shared
    assert shared_funder_share(cd, nonhub=True) == pytest.approx(0.5)


def test_hub_funder_not_shared_in_nonhub_variant():
    pay = [("b1", 10, T0 + 100), ("b2", 10, T0 + 200)]
    inf = [("b1", "EX", 10, T0 + 50, 1, -1, 0, 1, 0), ("b2", "EX", 10, T0 + 60, 2, -1, 0, 1, 0)]
    cd = mk(pay, inf, [], {"b1": None, "b2": None})
    assert shared_funder_share(cd) == pytest.approx(1.0)
    assert shared_funder_share(cd, nonhub=True) == pytest.approx(0.0)
    assert loop_share(cd) == 0.0
    assert outside_funding_share(cd) == pytest.approx(1.0)


def test_hhi_single_payer():
    cd = mk([("b1", 5, T0 + 1), ("b1", 5, T0 + 2)], [], [], {"b1": None})
    assert payer_hhi(cd) == pytest.approx(1.0)
    assert outside_funding_share(cd) == 1.0  # no inflows seen: money held before the lookback


def test_timing_coupling_detects_payments_after_seller_outflows():
    rng = np.random.default_rng(1)
    out_times = np.sort(rng.integers(T0, T1 - 4000, size=40))
    pay = [(f"b{i % 8}", 1.0, int(t + rng.integers(60, 900))) for i, t in enumerate(out_times)]
    out = [("x", 1.0, int(t)) for t in out_times]
    cd = mk(pay, [], out, {})
    tc = timing_coupling(cd, n_null=100)
    assert tc > 0.5
    # unrelated timing: payments at random times
    pay2 = [(f"b{i % 8}", 1.0, int(t)) for i, t in enumerate(rng.integers(T0, T1, size=40))]
    cd2 = mk(pay2, [], out, {})
    assert abs(timing_coupling(cd2, n_null=100)) < 0.2


def test_compute_features_runs():
    pay = [("b1", 10, T0 + 100), ("b2", 10, T0 + 200)]
    inf = [("b1", "S", 10, T0 + 50, 1, 1, 0, 0, 1), ("b2", "b1", 10, T0 + 60, 2, 2, 1, 0, 0)]
    cd = mk(pay, inf, [("b1", 10, T0 + 50)], {"b1": 1, "b2": 2})
    f = compute_features(cd, n_null=20)
    assert f["loop_share"] == pytest.approx(1.0)
    assert f["loop_share_1hop"] == pytest.approx(0.5)
    assert f["outside_funding_share"] == pytest.approx(0.0)


def test_injected_ring_moves_loop_share_by_phi():
    from controls import inject, shuffle_times

    rng = np.random.default_rng(3)
    pay = [(f"b{i % 20}", float(rng.uniform(0.5, 2.0)), int(T0 + rng.integers(0, T1 - T0))) for i in range(400)]
    inf = [(f"b{i}", f"ex{i % 3}", 50.0, T0 + 10 * i, i, -1, 0, 1, 0) for i in range(20)]
    cd = mk(pay, inf, [("owner", 100.0, T0 + 5000)], {f"b{i}": None for i in range(20)})
    cd.meta = {"payee": "S"}
    base = compute_features(cd, n_null=10)
    assert base["loop_share"] == 0.0
    for route, expect_loop in (("direct", True), ("relay4", True), ("relay5", False), ("via_hub", False), ("common_funder", False)):
        f = compute_features(inject(cd, 0.2, route, seed=1), n_null=10)
        if expect_loop:
            assert f["loop_share"] == pytest.approx(0.2, abs=1e-6), route
        else:
            assert f["loop_share"] == pytest.approx(0.0, abs=1e-9), route
    cf = compute_features(inject(cd, 0.2, "common_funder", seed=1), n_null=10)
    assert cf["shared_funder_share_nonhub"] >= 0.2 - 1e-9
    sh = shuffle_times(cd, 5)
    assert sorted(sh.payments["value"]) == sorted(cd.payments["value"])
    assert sh.payments["ts"].between(T0, T1 - 1).all()
