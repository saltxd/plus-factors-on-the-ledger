"""Expand the case registry (cases/cases.yaml) into one row per (payee, window)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOOKBACK_DAYS = 14

# Base: 2-second blocks; block 50,715,727 has timestamp 1788220801 (2026-09-01 00:00:01 UTC)
BASE_REF_BLOCK = 50715727
BASE_REF_TS = 1788220801


def base_ts(block: int) -> int:
    return BASE_REF_TS + 2 * (block - BASE_REF_BLOCK)


def base_block_at(ts: int) -> int:
    """First Base block with timestamp >= ts."""
    return BASE_REF_BLOCK + max(0, -(-(ts - BASE_REF_TS) // 2))


@dataclass
class Case:
    case_id: str
    family: str
    chain: str
    market: str
    label: str
    y: int
    payee: str
    window: str
    half: str
    contested: bool = False


def load_registry() -> dict:
    return yaml.safe_load((ROOT / "cases" / "cases.yaml").read_text())


def load_split() -> dict[str, str]:
    return json.loads((ROOT / "cases" / "split.json").read_text())["assignment"]


def expand(registry: dict | None = None, split: dict[str, str] | None = None) -> list[Case]:
    reg = registry or load_registry()
    sp = split or load_split()
    out: list[Case] = []
    for fam in reg["families"]:
        wl = fam.get("window_labels", {})
        for entry in fam["payees"]:
            if isinstance(entry, dict):
                addr, wins = entry["address"], entry.get("windows", fam["windows"])
            else:
                addr, wins = entry, fam["windows"]
            for w in wins:
                label = wl.get(w, fam["label"])
                out.append(
                    Case(
                        case_id=f"{fam['family']}|{addr.lower()}|{w}",
                        family=fam["family"],
                        chain=fam["chain"],
                        market=fam["market"],
                        label=label,
                        y=1 if label == "C" else 0,
                        payee=addr.lower(),
                        window=w,
                        half=sp[fam["family"]],
                        contested=bool(fam.get("contested", False)),
                    )
                )
    return out


def window_bounds(reg: dict, w: str) -> tuple[int, int, int, int]:
    """(t0, t1, first_block, last_block) for a window; t1 is exclusive."""
    from datetime import datetime

    win = reg["windows"][w]
    t0 = int(datetime.fromisoformat(win["start"].replace("Z", "+00:00")).timestamp())
    t1 = int(datetime.fromisoformat(win["end"].replace("Z", "+00:00")).timestamp())
    return t0, t1, int(win["first_block"]), int(win["last_block"])
