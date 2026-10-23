"""Tests for the whole-market run, the spot-check sampler and the end-to-end positive control
(added Oct 23 to 24, 2026, after the freeze), on made-up wallets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import market_base as mb  # noqa: E402
import positive_control_e2e as pce  # noqa: E402
from spotcheck import exact_ci  # noqa: E402

PAYER, PROXY, SELLER, OTHER, FAC, NOTFAC = ("0x" + c * 40 for c in "abcdef")


def toy_con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE TABLE tr (block INTEGER, txi INTEGER, li INTEGER, src VARCHAR, dst VARCHAR, val HUGEINT)")
    con.execute("CREATE TABLE auth (block INTEGER, txi INTEGER, li INTEGER, authorizer VARCHAR, nonce VARCHAR)")
    con.execute("CREATE TABLE senders (block INTEGER, txi INTEGER, frm VARCHAR, dst VARCHAR)")
    con.execute("CREATE TABLE facilitators (a VARCHAR, facilitator VARCHAR)")
    con.execute("INSERT INTO facilitators VALUES (?, 'f')", [FAC])
    rows = [
        # tx (10, 1): direct EIP-3009 payment PAYER -> SELLER, sent by a listed facilitator
        (10, 1, 1, PAYER, SELLER, 2_000_000),
        # tx (11, 2): PAYER -> PROXY authorised, PROXY forwards 99% to SELLER in the same transaction
        (11, 2, 1, PAYER, PROXY, 1_000_000), (11, 2, 2, PROXY, SELLER, 990_000),
        # tx (12, 3): direct payment PAYER -> OTHER sent by an unlisted address
        (12, 3, 1, PAYER, OTHER, 5_000_000),
    ]
    con.executemany("INSERT INTO tr VALUES (?, ?, ?, ?, ?, ?)", rows)
    con.executemany("INSERT INTO auth VALUES (?, ?, 0, ?, 'n')", [(10, 1, PAYER), (11, 2, PAYER), (12, 3, PAYER)])
    con.executemany("INSERT INTO senders VALUES (?, ?, ?, '')", [(10, 1, FAC), (11, 2, FAC), (12, 3, NOTFAC)])
    return con


def test_window_payments_credits_the_final_recipient_and_marks_x402():
    con = toy_con()
    mb.window_payments(con, 0, 100)
    m = con.execute("SELECT payee, payer, val, via, forwarded, x402 FROM mpay ORDER BY block, li").df()
    # the proxy's own receipt is marked forwarded; the seller gets the passthrough payment
    proxy = m[m["payee"] == PROXY].iloc[0]
    assert bool(proxy["forwarded"]) and proxy["via"] == "direct"
    seller = m[m["payee"] == SELLER].sort_values("via")
    assert list(seller["via"]) == ["direct", "passthrough"]
    assert set(seller["payer"]) == {PAYER} and seller["x402"].all()
    other = m[m["payee"] == OTHER].iloc[0]
    assert not bool(other["x402"])


def test_exact_ci_matches_known_clopper_pearson_values():
    lo, hi = exact_ci(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.30850, abs=1e-4)
    lo, hi = exact_ci(5, 10)
    assert lo == pytest.approx(0.18709, abs=1e-4) and hi == pytest.approx(0.81291, abs=1e-4)


@pytest.mark.parametrize("route,chain_len", [("direct", 1), ("relay3", 3), ("relay4", 4), ("relay5", 5)])
def test_e2e_ring_funding_chain_has_the_designed_length(route, chain_len):
    amounts = np.array([0.5, 1.0, 2.0])
    trs, aus, info = pce.ring_rows(SELLER, "W4", route, 0.3, amounts, 100.0, OTHER, seed=3)
    payers = {a[3] for a in aus}
    assert len(payers) == pce.N_RING
    pay = [t for t in trs if t[4] == SELLER and t[3] in payers]
    assert len(pay) == len(aus)
    fund = [t for t in trs if not (t[4] == SELLER and t[3] in payers)]
    assert len(fund) == chain_len * pce.N_RING
    # the ring carries share phi of the seller's payment value, up to rounding to micro-USDC
    assert info["phi_actual"] == pytest.approx(0.3, abs=1e-6)
    assert all(t[1] >= pce.TXI0 for t in trs)


def test_e2e_forwarder_route_is_one_transaction():
    trs, _, _ = pce.ring_rows(SELLER, "W4", "via_forwarder", 0.3, np.array([1.0]), 100.0, OTHER, seed=4)
    legs = [t for t in trs if t[3] == SELLER or t[3] == OTHER]
    for t in [t for t in legs if t[3] == SELLER]:
        fwd = [u for u in legs if u[3] == OTHER and u[0] == t[0] and u[1] == t[1] and u[2] > t[2]]
        assert fwd and fwd[0][5] == t[5]


def test_committed_market_tables_name_ring_wallets_by_pseudonym_only():
    p = ROOT / "results" / "market_bsc_features.csv"
    if not p.exists():
        pytest.skip("market run not committed yet")
    df = pd.read_csv(p)
    assert not any(re.search(r"agent|order", c) for c in df.columns)
    ring = df[df["ring_wallet"]]
    assert len(ring) == 62 and ring["payee"].str.fullmatch(r"(ring48|group14)-\d\d").all()
    assert df.loc[~df["ring_wallet"], "payee"].str.fullmatch(r"0x[0-9a-f]{40}").all()
