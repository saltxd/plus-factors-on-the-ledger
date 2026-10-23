"""Case-level rows of the withheld cases, for runs without their per-transaction tables.

A case whose tables contain a ring wallet (the 62 ring cases, and one other BNB Chain case with
ring wallets among its payers) is withheld: src/extract_bsc.py writes its tables to
data/cases_private/, which is not committed, because the agent ids, order ids, blocks and times in
them are enough to look the ring wallets up on a public explorer. What the analysis computes from
those tables is committed in data/withheld/ instead, as rows of the same result files:

  case_features.csv                    rows of results/case_features.csv
  sensitivity_features.csv             rows of results/sensitivity_features.csv (K = 1 to 6)
  negative_control_timing_shuffle.csv  rows of the timing-shuffle control
  positive_control.csv                 ring injections into a withheld base market
  positive_control_boundary.csv        the fine grid near the threshold for that market

src/run_features.py and src/controls.py compute a case from its tables when they are present
(data/cases or data/cases_private) and take its rows from here otherwise, so a run from the
committed data gives the committed results. After a full run with the private tables,
`python src/withheld.py` rewrites these files from results/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "cases"
PRIVATE = ROOT / "data" / "cases_private"
WITHHELD = ROOT / "data" / "withheld"
FILES = {
    "case_features.csv": "case_id",
    "sensitivity_features.csv": "case_id",
    "negative_control_timing_shuffle.csv": "case_id",
    "positive_control.csv": "base_case",
    "positive_control_boundary.csv": "base_case",
}


def dir_name(case_id: str) -> str:
    return case_id.replace("|", "__")


def case_dir(case_id: str) -> Path | None:
    """The case's table directory, committed or private, or None when its tables are absent."""
    for base in (CASES, PRIVATE):
        d = base / dir_name(case_id)
        if (d / "meta.json").exists():
            return d
    return None


def carried(name: str) -> pd.DataFrame:
    """Committed rows of the withheld cases for one result file (empty if there are none)."""
    p = WITHHELD / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=[FILES[name]])


def withheld_ids() -> set[str]:
    return set(carried("case_features.csv")["case_id"])


def main() -> None:
    ids = {__import__("json").loads((d / "meta.json").read_text())["case_id"] for d in PRIVATE.iterdir() if (d / "meta.json").exists()}
    if not ids:
        raise SystemExit("data/cases_private/ is empty: run src/extract_bsc.py --stage cases on the raw BNB Chain pull first")
    WITHHELD.mkdir(parents=True, exist_ok=True)
    for name, key in FILES.items():
        res = pd.read_csv(ROOT / "results" / name)
        part = res[res[key].isin(ids)]
        part.to_csv(WITHHELD / name, index=False, float_format="%.6g")
        print(f"{name}: {len(part)} rows for {part[key].nunique()} withheld cases")


if __name__ == "__main__":
    main()
