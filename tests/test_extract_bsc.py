"""The BNB Chain extraction never writes a ring wallet's address: checks on made-up wallets."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extract_bsc import pseudonymize, ring_aliases  # noqa: E402

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


def test_committed_ring_files_use_pseudonyms_only():
    rings = json.loads((ROOT / "data" / "bsc_rings.json").read_text())
    for name, n in (("ring48", 48), ("group14", 14)):
        assert rings[name]["payees"] == [f"{name}-{i:02d}" for i in range(1, n + 1)]
    dirs = [p.name for p in (ROOT / "data" / "cases").iterdir() if p.name.startswith(("F08-", "F09-"))]
    assert len(dirs) == 62 and all(re.fullmatch(r"F0[89]-se-(ring48|group14)__(ring48|group14)-\d\d__SE", d) for d in dirs)
