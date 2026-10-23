#!/bin/bash
# The order the analysis was run in. Steps 1-3 and the hub-threshold extractions in step 6
# need the raw Base pull (data/raw/base_mac, about 4.5 GB, i.e. 4.2 GiB, gzipped) and the
# DuckDB file built from it; everything else runs from the committed per-case tables.
# The BNB Chain per-case tables come from src/extract_bsc.py on a re-pulled raw BNB Chain pull,
# which the repo does not include (README, Reproduce, step 3).
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
$PY src/controls.py --which boundary
$PY src/extract_base.py --db data/base.duckdb --out data/cases_h300 --hub 300 --k 6 --memory 14GB --threads 10
$PY src/extract_base.py --db data/base.duckdb --out data/cases_h3000 --hub 3000 --k 6 --memory 14GB --threads 10
$PY src/sensitivity.py
# Optional, and not run for the report: a market-level check on TermiX's Base escrow
# $PY src/extract_termix_base.py --db data/base.duckdb --raw $RAW --sample 300
# $PY src/market_check.py
$PY src/report.py
