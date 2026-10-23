"""Assign case families to a development half and a test half.

Run once, before any feature is computed. Families (not single cases) are split,
so weekly repeats of one seller and the members of one ring never straddle the halves.
Stratified by (coordinated yes/no, chain). Within each stratum the families are
shuffled with a fixed seed and dealt alternately, starting with a seeded coin flip.

    python scripts/make_split.py  ->  cases/split.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import yaml

SEED = 20261023  # sprint start date, fixed before any data was read
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    reg = yaml.safe_load((ROOT / "cases" / "cases.yaml").read_text())
    strata: dict[tuple[int, str], list[str]] = {}
    for fam in reg["families"]:
        y = 1 if fam["label"] == "C" else 0
        strata.setdefault((y, fam["chain"]), []).append(fam["family"])
    rng = random.Random(SEED)
    assign: dict[str, str] = {}
    for key in sorted(strata):
        fams = sorted(strata[key])
        rng.shuffle(fams)
        first = "dev" if rng.random() < 0.5 else "test"
        other = "test" if first == "dev" else "dev"
        for i, f in enumerate(fams):
            assign[f] = first if i % 2 == 0 else other
    out = {
        "seed": SEED,
        "method": "stratified by (coordinated, chain); seeded shuffle; alternate deal starting with a seeded coin flip",
        "assignment": dict(sorted(assign.items())),
        "counts": {
            half: {
                "families": sum(1 for v in assign.values() if v == half),
                "coordinated_families": sum(
                    1 for f in reg["families"] if assign[f["family"]] == half and f["label"] == "C"
                ),
            }
            for half in ("dev", "test")
        },
    }
    (ROOT / "cases" / "split.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
