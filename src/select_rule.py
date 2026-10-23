"""Choose the decision rule on the development half only and write results/frozen_rule.json.

Only rows with half == "dev" are read. The chosen rule is then committed to git before
src/evaluate.py looks at the test half; the commit hash is recorded in results/results.md.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from features import FEATURES, K_HOPS, LAG_COUPLING, LAG_RELAY, N_NULL
from rules import describe, search

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("select_rule")

# Features whose evidence the decodes did not use to assign labels (see cases.yaml label_basis
# and README). A second rule restricted to them is reported to show what survives without the
# circular part.
NON_CIRCULAR = ["payer_hhi", "timing_coupling", "relay_share"]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = pd.read_csv(ROOT / "results" / "case_features.csv")
    dev = df[df["half"] == "dev"].reset_index(drop=True)
    log.info("dev: %d cases, %d families, %d coordinated cases", len(dev), dev["family"].nunique(), int(dev["y"].sum()))
    board = search(dev, FEATURES, pairs=True, top=40)
    board_nc = search(dev, NON_CIRCULAR, pairs=True, top=10)
    singles = search(dev, FEATURES, pairs=False, top=200)
    best_single = {}
    for r in singles:
        f = r["rule"]["feature"]
        if f not in best_single:
            best_single[f] = r
    chosen = board[0]
    out = {
        "frozen_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selection": "family-weighted balanced accuracy on the development half; ties: fewer features, larger margin, name",
        "settings": {"K_HOPS": K_HOPS, "LAG_COUPLING_s": LAG_COUPLING, "LAG_RELAY_s": LAG_RELAY, "N_NULL": N_NULL, "lookback_days": 14, "hub_min_counterparties": 1000},
        "dev_cases": int(len(dev)),
        "dev_families": int(dev["family"].nunique()),
        "rule": chosen["rule"],
        "rule_text": describe(chosen["rule"]),
        "dev_metrics": {k: v for k, v in chosen.items() if k.startswith("dev_")},
        "non_circular_rule": board_nc[0]["rule"],
        "non_circular_rule_text": describe(board_nc[0]["rule"]),
        "non_circular_dev_metrics": {k: v for k, v in board_nc[0].items() if k.startswith("dev_")},
        "best_single_feature_rules": {f: {"rule_text": describe(r["rule"]), "rule": r["rule"], **{k: v for k, v in r.items() if k.startswith("dev_")}} for f, r in best_single.items()},
        "leaderboard": [{"rule_text": describe(r["rule"]), "margin": r["margin"], **{k: v for k, v in r.items() if k.startswith("dev_")}} for r in board],
    }
    (ROOT / "results" / "frozen_rule.json").write_text(json.dumps(out, indent=2) + "\n")
    log.info("chosen: %s %s", out["rule_text"], out["dev_metrics"])
    log.info("non-circular: %s %s", out["non_circular_rule_text"], out["non_circular_dev_metrics"])


if __name__ == "__main__":
    main()
