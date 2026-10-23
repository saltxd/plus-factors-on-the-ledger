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
(chosen on 10 development families, commit `f99f40e`) had a family-weighted
true-positive rate of 0.84 and false-positive rate of 0.20 (balanced accuracy 0.82,
bootstrap 95% interval 0.56 to 1.00, exact permutation p = 0.024). Here, money
returning to the seller and buyers without outside money separated coordinated from
independent demand, and a shared funder, payer concentration and timing did not. The
labels rest partly on the same funding evidence: a rule on the features they did not
use scored 0.67 (p = 0.14).

**Added after the freeze (Oct 23 to 24, 2026).** The frozen rule and its code are
unchanged; the plan was committed before any of these values was computed
(`cases/market_plan.md`). Run on every x402 payee on Base with at least $10 of x402
payments in a week (750 payee-weeks, 431 payees, W1 to W4), the rule flags 258
payee-weeks (34%) and 29.5% of the x402 volume; on every Set and Earn payee on BNB Chain
(9,131), 1,276 payees and 14.6% of order budgets. In a blinded spot-check of 40 payees
no decode had examined, two AI judges called 22 and 20 of the 25 flagged payees
coordinated and 4 of the 15 unflagged ones; the three flagged payees both judges called
independent had sent their payers small refunds. Post hoc, 48 of the 135 flagged payees
are wallets of one ring, BotPay's. A synthetic ring written into the raw transfer data
came out of the real extraction exactly as designed in 90 of 90 runs
(`results/positive_control_e2e_summary.json`). Details in the last section of
`results/results.md` and in Section 5 of the report.

## History note

On Oct 23, 2026 the history of this repository was rewritten three times, the first
two before it was first published and the third after: to replace 62 BNB Chain wallet addresses, the
members of the two rebuilt rings, with the pseudonyms `ring48-01` to `ring48-48` and
`group14-01` to `group14-14` (and local home-directory paths with `$HOME`); to remove
from every commit the raw BNB Chain pull (`data/raw/bsc/`) and a draft of the
submission form; and to remove from every commit the per-transaction tables of the
cases that contain a ring wallet and redact, everywhere else, the ring wallets' agent
ids, order ids and transaction hashes, any of which finds a ring wallet on the public
ERC-8004 registry or an explorer. The published decodes describe these rings without
listing them (one names four members as hiring examples), and the raw pull contains
wallet lists our decodes chose not to publish. The third rewrite dropped the tables of
63 cases (the 62 ring cases and one F20 case with a ring wallet among its payers; 315
files) and 6 lines of `data/decode_printed_hex.txt` (printed prefixes of ring
transactions), and wrote `REDACTED` for 124 ring agent ids in `data/bsc_rings.json`
and `data/cases/extract_bsc_summary.json`, for the hash and agent of 2 of the 30
sampled settlements (`data/bsc_settle_sample.csv`, `data/bsc_validation.json`), and for
the agent-id range and the example transaction the decodes print (`cases/cases.yaml`,
`src/extract_bsc.py`). Commit times are unchanged; commit IDs changed, and the freeze
commit is now `f99f40eb42b69b7d90dcf76305db08a6b42f92d2` (first `81c736c`, then
`4037a54` and `b28bded` between the rewrites).

## Layout

| Path | What it is |
|---|---|
| `cases/cases.yaml` | Case registry: payee, window, label, source decode, quote, and what evidence the decode used |
| `cases/split.json` | Development / test assignment by case family (seeded, committed before any feature was computed) |
| `pull/` | Data pulls from public chain endpoints |
| `src/` | Extraction, features, rule search, evaluation, controls, report |
| `tests/` | Unit tests for the features, the ring injection and the BNB Chain pseudonyms |
| `data/cases/` | Per-case evidence tables (the input of every feature), committed except for the 63 withheld cases (see Data) |
| `data/withheld/`, `src/withheld.py` | Case-level rows of the withheld cases (features, sensitivity, controls), used when their tables are absent |
| `data/*.json`, `data/bsc_settle_sample.csv` | Pull verification, BNB Chain validation against published counts and on 30 sampled settlements, ring reconstruction (ring wallets under pseudonyms) |
| `results/` | Case table, frozen rule, test metrics, controls, figures, `results.md` |
| `cases/market_plan.md`, `cases/spotcheck_judge_*.md` | Added after the freeze: plan for the whole-market run, spot-check and end-to-end control; the judges' protocol and prompt |
| `src/market_base.py`, `src/market_bsc.py`, `src/market_summary.py` | Added after the freeze: whole-market populations, the frozen extraction and features over them, prevalence |
| `src/spotcheck.py`, `scripts/spotcheck_tools.py` | Added after the freeze: blinded spot-check draw and unblinding; the judges' read-only tools |
| `src/positive_control_e2e.py`, `src/fig_reach_walk.py` | Added after the freeze: synthetic rings through the raw data and the real extraction; the reach-walk figure |
| `pull/x402scan_facilitators.py`, `pull/base_tx_senders.py`, `pull/agent402_index.py` | Added after the freeze: x402scan's facilitator list at commit `f205fbe`, transaction senders from the node, Agent402's public index |
| `results/market_*`, `results/spotcheck_*`, `results/positive_control_e2e*`, `results/fig_reach_walk.png` | Added after the freeze: outputs of the above |
| `data/x402scan_facilitators_base.csv`, `data/agent402_board_2026-10-13.csv`, `data/decode_printed_hex.txt` | Added after the freeze: x402scan's Base facilitator list (commit `f205fbe`), Agent402's Oct 13 top ten as printed in the top-ten decode, and the hex tokens the published decodes print (spot-check exclusions) |
| `scripts/diag_botpay_ring.py` | Added after unblinding: post hoc count of flagged payees paid by one ring |

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
  row by row (`data/verify_base_public_segments.json`).
- **BNB Chain**: every log of TermiX's two escrows from 2026-09-17 to 2026-10-08
  (blocks 122,313,771 to 126,344,213), each chunk queried twice and merged, and
  ERC-8004 `ownerOf` for every agent hired. Daily hire counts are checked against the
  published decode (`data/bsc_validation.json`). Plain USDC/USDT transfers could not
  be pulled on BNB Chain at the allowed pace from keyless endpoints, so BNB Chain
  evidence is the market's own hire graph. The raw BNB Chain pull is not included in
  this repository: it contains wallet lists our decodes chose not to publish (the
  members of the two rings). `pull/bsc_termix_pull.py` re-pulls it (Reproduce, step 3).
  Of the 64 BNB Chain cases, one has its per-transaction tables committed. The tables
  of the 62 ring cases, and of one other case with a ring wallet among its payers, are
  not included: an agent id, an order id, a transaction hash, or the block and time of
  a ring hire is enough to find a ring wallet on the public registry or an explorer.
  Their case-level features, and the controls computed from their tables, are
  committed in `data/withheld/`, and the pipeline uses them when the tables are absent.
  `src/extract_bsc.py` rebuilds those tables from a re-pull into `data/cases_private/`
  (not committed), with the ring wallets under the same pseudonyms.

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
any feature was computed: `cases/hypotheses.md`. Commit times are local to this repository
and not externally timestamped.

### After the freeze (added Oct 23 to 24, 2026)

Planned in `cases/market_plan.md` (commit `eae4f78`, amended once in `ee4f211` for node
load, both before any market value was computed). Nothing here feeds back into the frozen
rule.

- **Whole market, Base.** An x402 payment is a payment as defined above whose transaction
  was sent by an address on x402scan's public facilitator list (commit `f205fbe`, 128 Base
  addresses, the list the decodes used); senders come from ChainWard's node. Every payee
  with at least $10 of x402 payments in a window enters (floor set before any count:
  below it, payees are mostly developer tests and dust); facilitators are excluded and a
  proxy that forwards a payment in the same transaction credits its final recipient. The
  frozen extraction and features run unchanged.
- **Whole market, BNB Chain.** Every owner of an agent hired on TermiX in the Set and Earn
  window, no floor, built exactly as the case tables (`src/market_bsc.py` reproduces the
  loop, funding and concentration features of the 64 BNB Chain cases exactly).
  Ring wallets appear only as `ring48-NN` / `group14-NN`; no agent or order ids are written.
- **Blinded spot-check.** 25 flagged and 15 unflagged Base payees the decodes did not
  examine (not printed in a decode, not a case, never in a week's top 30), drawn with seed
  20261024 and shuffled; two separate AI agent sessions judged each from on-chain evidence
  with read-only tools (`scripts/spotcheck_tools.py`), without seeing features, flags, the
  rule or the stratum. Verdicts were committed before the key was joined.
- **Public labels ChainWard did not write.** Agent402's seller index (read Oct 23) marks
  some Base sellers `settlement_self_funded`; the rule is compared with it on the payees
  both cover (`results/market_agent402_comparison.csv`). The full index stays out of the
  repository.
- **End-to-end positive control.** Synthetic transfers and EIP-3009 authorisations for a
  seller-funded ring are written into the data the extraction reads (a scratch database
  over the base data, opened read-only) for three benign markets, six routes and five ring
  shares, and `src/extract_base.py` and `src/features.py` run unchanged.

## Reproduce

Python 3.12, `pip install -r requirements.txt`.

```bash
# 1. Base pull (any Base archive endpoint with logs for Sep 1 to Oct 12, 2026)
python pull/base_usdc_pull.py --rpc <URL> --start 50715727 --end 52530126 --out data/raw/base
# 2. Base per-case tables (DuckDB; about 10 GB of disk)
python src/extract_base.py --db base.duckdb --raw data/raw/base --load
python src/extract_base.py --db base.duckdb --out data/cases --hub 1000 --k 6   # reach to 6 hops for the K = 5, 6 sensitivity
# 3. BNB Chain pulls (not included in the repo, see Data) and per-case tables. First write
#    data/raw/bsc/ring_spec.json from the decodes: the 48-wallet ring's agent-id range
#    (set-and-earn-week-one) and the 14-wallet group's example hire (set-and-earn-week-one-closed),
#    as {"ring48_agent_id_range": [first, last], "group14_example_tx": "0x..."}
python pull/bsc_termix_pull.py anchors --start 122313771 --end 126344213 --seg 50000
python pull/bsc_termix_pull.py escrow --start 122313771 --end 126344213
python src/extract_bsc.py --stage orders
python pull/bsc_termix_pull.py owners --ids data/raw/bsc/agents.txt --block 126344213
tail -n +2 data/bsc_settle_sample.csv | cut -d, -f1 > data/raw/bsc/settle_sample.txt
python pull/bsc_termix_pull.py receipts --txs data/raw/bsc/settle_sample.txt
python src/extract_bsc.py --stage cases
# 4. From the committed per-case tables and data/withheld onward (no chain access needed)
python src/run_features.py --sensitivity
python src/select_rule.py      # development half only
python src/evaluate.py
python src/controls.py
python src/controls.py --which boundary
python src/sensitivity.py      # after extract_base.py --hub 300 --k 6 / --hub 3000 --k 6 into data/cases_h300, data/cases_h3000
python src/report.py
pytest tests/
# 5. Added after the freeze (needs the DuckDB file, ChainWard's node or another Base archive
#    endpoint for transaction senders, and the raw BNB Chain pull)
python pull/x402scan_facilitators.py
python src/market_base.py candidates
python pull/base_tx_senders.py --pairs data/raw/base_senders/pairs_candidates.txt.gz --rpc <URL> --start 51320527 --end 52530126
python src/market_base.py population
python src/market_base.py extract
python src/market_base.py features --csv results/market_base_features.csv
python src/market_bsc.py
python -I pull/agent402_index.py --raw data/raw/agent402 --out data/raw/agent402/base_verdicts.csv
python src/market_summary.py
python src/spotcheck.py unblind --features results/market_base_features.csv --key results/spotcheck_key.csv
python scripts/diag_botpay_ring.py   # post hoc, after unblinding
python src/positive_control_e2e.py
python src/fig_reach_walk.py
python src/report.py
```

Steps 4 onward run from `data/cases/` and `data/withheld/`, which are committed, so
the results can be checked without re-pulling the chain; run that way they give the
committed results exactly, with the withheld cases carried over. With the withheld
tables rebuilt from a re-pull, they give the same frozen rules, figures, tables and
numbers, with one exception: for one development case (F20-se-clear-outside, agent
352475) the exploratory `payer_synchrony`, which no rule uses, comes out -0.021
instead of -0.023, and timing values in the controls run on that case move by similar
noise without changing any flag. The timing nulls give each payer its random shift in
sorted order of the payer IDs, and one of that case's payers, a 14-wallet-group member, sorts in a
different place than the address it replaced. After such a run, `python
src/withheld.py` refreshes `data/withheld/` from `results/`.

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
accompany some decodes. Cases are wallets and contracts only. Third-party public data used
after the freeze: x402scan's facilitator list (github.com/Merit-Systems/x402scan at
commit `f205fbe`) and Agent402's public seller index (agent402.tools, read Oct 23, 2026).
One BNB Chain decode (`set-and-earn-week-one`) prints four of the 62 ring wallets as hiring
examples; the repository still names all 62 only by pseudonym, with none of their agent ids,
order ids or transactions.

AI assistance: the code and analysis in this repo were written with an AI coding agent.
