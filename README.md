# On-chain collusion evidence

What should count as convincing evidence that AI agents collude? This repo tests
candidate evidence on live agent markets where every payment is public: x402
pay-per-request payments on Base, and agent hiring through TermiX's escrow on BNB
Chain during BNB Chain's Set and Earn campaign. Case labels come from ChainWard's
published on-chain decodes. The same evidence is computed for every case from raw
chain data, a decision rule is chosen on a development half, frozen in a commit, and
then scored on a held-out test half, with a positive control (a synthetic ring
injected into a real market) and negative controls.

Entry to the Apart AI Collusion Research Sprint (Oct 23 to 25, 2026), research
question 2.3 ("What should count as convincing evidence of collusion?").

Results: `results/results.md` (generated from the result files by `src/report.py`).
In short: on 10 held-out case families the frozen rule `loop_share >= 0.4235`
(chosen on 10 development families, commit `81c736c`) had a family-weighted
true-positive rate of 0.84 and false-positive rate of 0.20 (balanced accuracy 0.82,
bootstrap 95% interval 0.56 to 1.00, exact permutation p = 0.024). Closed loops and
the absence of outside money separated coordinated from independent demand; a shared
funder, payer concentration and timing did not.

## Layout

| Path | What it is |
|---|---|
| `cases/cases.yaml` | Case registry: payee, window, label, source decode, quote, and what evidence the decode used |
| `cases/split.json` | Development / test assignment by case family (seeded, committed before any feature was computed) |
| `pull/` | Data pulls from public chain endpoints |
| `src/` | Extraction, features, rule search, evaluation, controls, report |
| `tests/` | Unit tests for the features and the ring injection |
| `data/cases/` | Per-case evidence tables (the input of every feature), committed |
| `data/*.json` | Pull verification, BNB Chain validation against published counts, ring reconstruction |
| `results/` | Case table, frozen rule, test metrics, controls, figures, `results.md` |

## Method

### Unit of analysis

One payee (an x402 seller's payTo address, or the owner wallet of a hired agent) in
one window. The question for each case: is the payee's measured demand coordinated
with the payee (self-funded, or money circulating inside a closed group), or does it
come from payers acting independently?

### Labels

`C` coordinated, `I` independent, `N` no loop found (a weak negative the decodes
explicitly say is not a clearance), `L` linked but no loop (a strong common link such
as one wallet funding many buyers, which the decodes explicitly did not count as
coordination). Detection target: `C` against everything else. Each family records the
decode quote and the evidence the decode used (`label_basis`), so the circularity of
each feature can be checked.

### Data

- **Base**: every USDC `Transfer` and `AuthorizationUsed` log (EIP-3009) on Base from
  2026-09-01 00:00 to 2026-10-12 23:59:59 UTC (blocks 50,715,727 to 52,530,126),
  about 160 million transfers, from ChainWard's own reth node and, for part of the
  range, two public endpoints (Tenderly's Base gateway and Pocket's Base endpoint),
  at most 2 requests a second per endpoint. Each segment's source is in the pull
  manifests; a seeded sample of ranges is re-read from a second endpoint and compared
  row by row (`data/verify_base_pull*.json`).
- **BNB Chain**: every log of TermiX's two escrows from 2026-09-17 to 2026-10-08
  (blocks 122,313,771 to 126,344,213), each chunk queried twice and merged, and
  ERC-8004 `ownerOf` for every agent hired. Daily hire counts are checked against the
  published decode (`data/bsc_validation.json`). Plain USDC/USDT transfers could not
  be pulled on BNB Chain at the allowed pace from keyless endpoints, so BNB Chain
  evidence is the market's own hire graph.

### Definitions (fixed before any case was scored)

- **Window** 7 days (see `cases/cases.yaml`); **lookback** 14 days before it.
- **Payment** (Base): a USDC transfer into the payee inside the window that the payer
  authorised with EIP-3009, directly or through a facilitator proxy that forwards it in
  the same transaction. (BNB Chain): a TermiX order created for the payee's agent.
- **Forwarding**: a transfer X -> Z that follows Y -> X in the same transaction with
  0.5 (Y -> X) <= (X -> Z) <= (Y -> X) is treated as Y -> Z.
- **Hub**: an address with at least 1,000 distinct counterparties (non-zero USDC
  transfers, either direction) in lookback + window. Hubs are not walked through:
  exchanges, routers, bridges and custodial accounts break the trail.
- **Reach set**: wallets reachable from the payee through non-hub wallets in at most
  K = 4 transfers in lookback + window (BNB Chain: through hires).

Features, per case (code: `src/features.py`):

| Feature | Definition |
|---|---|
| `loop_share` | share of payment value from payers in the payee's reach set |
| `loop_share_1hop` | same, payers the payee paid directly |
| `shared_funder_share` | share of payment value from the payers behind the most common first funder (first non-zero inflow in lookback + window), counting only funders of 2+ payers |
| `shared_funder_share_nonhub` | same, hubs never count as shared funders |
| `payer_hhi` | Herfindahl index of payment value across payers |
| `outside_funding_share` | share of the value flowing into payers that comes from outside {payee, payers, reach set}; 1 when payers received nothing |
| `timing_coupling` | share of payments made within 1 hour after any transfer out of the payee, minus the same share when each payer's payment times are circularly shifted inside the window (mean of 200 shifts) |
| `relay_share` | share of payments made within 10 minutes after the payer received money, minus the circular-shift null |
| `pair_reciprocity_timing` (exploratory) | share of payments made within 1 hour after the payee sent money to that same payer, minus the null; added after the debug run, never in the rule search |
| `payer_synchrony` (exploratory) | share of payments within 10 minutes of a payment by a different payer, minus the null; same status |

### Protocol

1. Case registry and split committed first (`cases/`).
2. Features computed for all cases; test-half values not printed.
3. Rule chosen on the development half only (`src/select_rule.py`): every single-feature
   threshold and every two-feature AND / OR rule, scored by family-weighted balanced
   accuracy (each case family weighs 1); ties go to fewer features, then a wider margin.
   A second rule restricted to features the decodes did not use for labelling is
   chosen the same way, and so is the best threshold for every single feature.
4. `results/frozen_rule.json` committed; the commit hash is in `results/results.md`.
5. Test-half scoring (`src/evaluate.py`), bootstrap over families, exact permutation test.
6. Controls (`src/controls.py`): ring injection into real benign markets (pre-set grid, plus a
   fine grid near the threshold added afterwards), timing shuffle, exact permutation test.

Deviations from this plan are listed in `results/results.md`. Hypotheses written before
any feature was computed: `cases/hypotheses.md`.

## Reproduce

Python 3.12, `pip install -r requirements.txt`.

```bash
# 1. Base pull (any Base archive endpoint with logs for Sep 1 to Oct 12, 2026)
python pull/base_usdc_pull.py --rpc <URL> --start 50715727 --end 52530126 --out data/raw/base
# 2. Base per-case tables (DuckDB; about 10 GB of disk)
python src/extract_base.py --db base.duckdb --raw data/raw/base --load
python src/extract_base.py --db base.duckdb --out data/cases
# 3. BNB Chain pulls and per-case tables
python pull/bsc_termix_pull.py anchors --start 122313771 --end 126344213 --seg 50000
python pull/bsc_termix_pull.py escrow --start 122313771 --end 126344213
python src/extract_bsc.py --stage orders
python pull/bsc_termix_pull.py owners --ids data/raw/bsc/agents.txt --block 126344213
python src/extract_bsc.py --stage cases
# 4. From the committed per-case tables onward (no chain access needed)
python src/run_features.py --sensitivity
python src/select_rule.py      # development half only
python src/evaluate.py
python src/controls.py
python src/controls.py --which boundary
python src/sensitivity.py      # after extract_base.py --hub 300 / --hub 3000 into data/cases_h300, data/cases_h3000
python src/report.py
pytest tests/
```

Steps 4 onward run from `data/cases/`, which is committed, so the results can be
checked without re-pulling the chain.

## Preexisting work

Everything in this repo was written during the sprint (from Oct 23, 2026, 00:00 UTC)
unless listed here. The following existed before the sprint and is used, not
re-created:

- **ChainWard's published decodes** (chainward.ai/decodes), written Sep 27 to Oct 13,
  2026: `x402-on-base`, `x402-on-base-two-weeks-later`, `x402-closed-six`,
  `x402-top-ten-self-funded`, `set-and-earn-week-one`, `set-and-earn-week-one-closed`,
  `termix-on-chain`. They are the source of every case label in `cases/cases.yaml`.
  Their analysis scripts and data are not used; this repo re-pulls the chain.
- **ChainWard's hire check and seller-demand check** (paid API endpoints, Oct 2026).
  They are not used to compute anything here. Several decodes used them, which is
  recorded in each family's `label_basis`.
- **ChainWard's Base node** (cw-sentinel), a reth history node, used only as a data
  source; any Base archive endpoint returns the same logs.

Nothing here uses private label sets, tip clusters or the paid wallet lists that
accompany some decodes. Cases are wallets and contracts only.

AI assistance: the code and analysis in this repo were written with an AI coding agent.
