#!/bin/bash
# The order the analysis was run in. Steps 1-3 need the raw Base pull (data/raw/base_mac,
# about 2.5 GB); everything after step 3 runs from the committed per-case tables.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
RAW=data/raw/base_mac

# 1. the raw pull covers every block, with no thin segment
$PY scripts/check_coverage.py --raw $RAW --start 50715727 --end 52530126
# 2. load into DuckDB
$PY src/extract_base.py --db data/base.duckdb --raw $RAW --load --memory 14GB --threads 10
# 3. per-case tables (reach recorded to 6 hops; the primary features use K = 4)
$PY src/extract_base.py --db data/base.duckdb --out data/cases --hub 1000 --k 6 --memory 14GB --threads 10
# 4. features (test-half values are not printed)
$PY src/run_features.py --sensitivity
# 5. choose the rule on the development half, then commit results/frozen_rule.json
$PY src/select_rule.py
# git add results/frozen_rule.json && git commit -m "Freeze decision rule"   (done by hand)
# 6. test-half evaluation, controls, sensitivity, report
$PY src/evaluate.py
$PY src/controls.py
$PY src/extract_base.py --db data/base.duckdb --out data/cases_h300 --hub 300 --k 6 --memory 14GB --threads 10
$PY src/extract_base.py --db data/base.duckdb --out data/cases_h3000 --hub 3000 --k 6 --memory 14GB --threads 10
$PY src/sensitivity.py
$PY src/extract_termix_base.py --db data/base.duckdb --raw $RAW --sample 300
$PY src/market_check.py
$PY src/report.py
