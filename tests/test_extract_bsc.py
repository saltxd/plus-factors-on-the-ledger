"""The BNB Chain extraction never writes a ring wallet's address: checks on made-up wallets."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from extract_bsc import pseudonymize, redact, ring_aliases  # noqa: E402

A, B, C, D = ("0x" + c * 40 for c in "dcba")


def test_aliases_follow_address_order_and_are_zero_padded():
    rings = {"ring48": {"payees": [A, B, C]}, "group14": {"payees": [D]}}
    assert ring_aliases(rings) == {C: "ring48-01", B: "ring48-02", A: "ring48-03", D: "group14-01"}


def test_missing_group_gets_no_aliases():
    assert ring_aliases({"ring48": {"payees": [A]}, "group14": {"error": "example transaction not found"}}) == {A: "ring48-01"}


def test_pseudonymize_reaches_nested_values_and_keys():
    alias = {A: "ring48-01", D: "group14-01"}
    obj = {"payees": [A, "0x" + "e" * 40], "hires_out": [{"buyer": D, "agent_id": 1}], A: 3, "n": 2.5}
    assert pseudonymize(obj, alias) == {"payees": ["ring48-01", "0x" + "e" * 40], "hires_out": [{"buyer": "group14-01", "agent_id": 1}],
                                        "ring48-01": 3, "n": 2.5}


def test_redact_replaces_ring_agents_and_ring_hashes_only():
    obj = {"agents": [7, 8], "agent_id": 7, "other_agent": {"agent_id": 9}, "settle_tx": "0x" + "ab" * 32, "tx": "0x" + "cd" * 32}
    out = redact(obj, {7}, {"0x" + "ab" * 32})
    assert out == {"agents": ["REDACTED", 8], "agent_id": "REDACTED", "other_agent": {"agent_id": 9}, "settle_tx": "REDACTED", "tx": "0x" + "cd" * 32}


def test_committed_ring_files_use_pseudonyms_only():
    rings = json.loads((ROOT / "data" / "bsc_rings.json").read_text())
    for name, n in (("ring48", 48), ("group14", 14)):
        assert rings[name]["payees"] == [f"{name}-{i:02d}" for i in range(1, n + 1)]
        assert rings[name]["agents"] == ["REDACTED"] * n


def test_ring_cases_have_no_committed_tables_and_are_carried_over():
    committed = [p.name for p in (ROOT / "data" / "cases").iterdir() if (p / "meta.json").exists()]
    assert not [d for d in committed if d.startswith(("F08-", "F09-"))]
    carried = pd.read_csv(ROOT / "data" / "withheld" / "case_features.csv")
    ring = carried[carried["family"].isin(["F08-se-ring48", "F09-se-group14"])]
    assert len(ring) == 62 and ring["payee"].str.fullmatch(r"(ring48|group14)-\d\d").all()
    assert not set(carried["case_id"].str.replace("|", "__", regex=False)) & set(committed)
    feats = pd.read_csv(ROOT / "results" / "case_features.csv")
    assert set(carried["case_id"]) <= set(feats["case_id"])


def test_committed_case_tables_hold_no_ring_wallet():
    for d in (ROOT / "data").glob("cases*/*"):
        if d.parent.name == "cases_private" or not (d / "meta.json").exists():  # local, not committed
            continue
        for t, cols in (("payments", ["payer"]), ("payer_inflows", ["payer", "src"]), ("seller_outflows", ["dst"]), ("payer_reach", ["payer"])):
            df = pd.read_csv(d / f"{t}.csv.gz", dtype=str)
            for c in cols:
                assert not df[c].str.fullmatch(r"(ring48|group14)-\d\d").fillna(False).any(), (d.name, t, c)
