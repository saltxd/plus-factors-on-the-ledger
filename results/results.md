# Results

Every number below is read from the files in this folder by `src/report.py`.

## In plain words

- **The test.** 123 cases (a payee in a 7-day window) from 20 case families on Base x402 and BNB Chain's TermiX escrow, labelled by ChainWard's published decodes. A rule was chosen on 10 development families, frozen in commit `81c736c`, then scored on 10 held-out families (5 coordinated).
- **The frozen rule** is `loop_share >= 0.4235`: flag a payee when at least 42% of its payment value comes from payers that its own money reached within 4 transfers (not counting exchanges and other hubs).
- **On the test half** it caught 38 of 42 coordinated cases and flagged 1 of 6 others: family-weighted true-positive rate 0.84, false-positive rate 0.20, balanced accuracy 0.82 (bootstrap 95% interval 0.56 to 1.00, 10 families).
- **Misses:** 4 test cases, all F04-botpay's main payTo in its four weeks. Its payers sit five transfers from the payTo, one beyond the reach limit, as written in hypothesis H5 before scoring. At K = 5 their loop share is at least 0.999 in every week.
- **False positive:** F15-losbeto (W4, label N). One payer carried 97% of its payment value ($158.79); in lookback + window the seller sent that same wallet $406.17. The decode read the seller's outflows as payouts. By the ledger the payee and its main payer pay each other; what the payments were for is not on-chain.
- **The other plus factor held up too.** Outside funding share alone (frozen threshold from dev) scored balanced accuracy 0.90 on the test half (TPR 1.00, FPR 0.20); its family-weighted AUC is 1.00 over all cases.
- **Parallel conduct did not separate.** Over all cases the family-weighted AUC was 0.63 for a shared first funder, 0.47 for payer concentration, 0.61 for spending money the moment it arrives and 0.70 for timing coupling, against 0.97 for loop share and 1.00 for outside funding share.
- **Without the circular evidence** (only features the decodes did not use for labelling), the frozen rule `timing_coupling >= -0.001939 AND relay_share >= 0.09579` scored balanced accuracy 0.67 on the test half (TPR 0.54, FPR 0.20).
- **Positive control.** A synthetic seller-funded ring (5 payers, 10 seeds per setting) injected into 12 real markets the rule does not flag was flagged in 100% of runs at half the seller's volume and in 0% of runs at 30% or less, whenever the seller's money reached it within 4 hops (the cut-off is where loop share crosses the threshold: 32% to 42% of volume, depending on the market's existing loop share). Routed over 5 hops or through an exchange-like hub it was never flagged at any size (0% of runs), and five payers funded by one outside wallet with no loop, parallel conduct, were never flagged either (0%).
- **Timing shuffle (negative control).** Circularly shifting each payer's payment times inside the window took the coordinated cases' mean timing coupling from 0.36 to -0.02, and the timing rule's flag rate on them from 0.50 to 0.00; the primary rule, which uses no timing, flagged exactly the same cases. The timing signal is real, but it is weak and its frozen thresholds sit inside the null's sampling noise (its outputs move when the number of null draws changes, see Sensitivity).
- **Chance.** Of the 252 ways to pick 5 coordinated families out of the 10 test families, 2.4% score at least as well under the frozen rule as the real labels (exact permutation p-value).

## The frozen rule

Chosen by `src/select_rule.py` on the development half only (75 cases, 10 families), frozen in commit `81c736c503c333311cb03b2ef4ef29a7b7149548`. Selection: every single-feature threshold and every two-feature AND / OR rule over the eight pre-registered features, scored by family-weighted balanced accuracy; ties went to fewer features, then the widest margin. On dev the primary rule scored balanced accuracy 1.00; all 40 rules kept on the leaderboard in `frozen_rule.json` also scored 1.00 on dev, so the tie-break (fewest features, widest margin) decided. The margin rule put the threshold midway between the dev cases, which all sat near 0 or near 1; partial rings were not in the development set, which is why the positive control finds the cut-off near 42%.

## Errors

- false negative: F04-botpay W1 payee `0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908` (C), loop share 0.000, outside funding share 0.000, payers 298.
- false negative: F04-botpay W2 payee `0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908` (C), loop share 0.000, outside funding share 0.001, payers 346.
- false negative: F04-botpay W3 payee `0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908` (C), loop share 0.000, outside funding share 0.001, payers 346.
- false negative: F04-botpay W4 payee `0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908` (C), loop share 0.001, outside funding share 0.054, payers 346.
- false positive: F15-losbeto W4 payee `0xd5ba9711a3d052846a3695c70e7fcb8b3168fe7d` (N), loop share 0.974, outside funding share 0.625, payers 13.

## Data checks

- Base pull: 157,753,459 USDC transfers, blocks 50,715,727 to 52,530,126, no gaps and no thin segments (`data/base_pull_coverage.json`). 24 segments came from public endpoints; 72 random 40-block ranges in them were re-read from ChainWard's node and all matched row for row (`data/verify_base_public_segments.json`). Three segments from one endpoint were discarded as incomplete and re-pulled (`data/base_pull_discarded_segments.jsonl`).
- BNB Chain pull: 10,325 TermiX hires in the Set and Earn window against 10,325 published; 7 of 7 daily counts equal. Each chunk was queried twice: 0 disagreements. On 30 sampled settlements the escrow paid the agent's ERC-8004 owner 30 times.
- Rings rebuilt from the decode's published description: 48 wallets in closed groups of 24, 12, 12, 218 orders of which 216 settled (published: 48 wallets, 218 orders, 216 settled); the second group has 14 wallets, 38 hires inside on 10-01, 10-04, 10-06, 0 hires in and 1 out (published: 14 wallets, no hire in, one $1 hire out).

## Sensitivity

Primary rule, frozen threshold, features recomputed under each setting. K=1: test TPR 0.59, FPR 0.20; K=2: test TPR 0.59, FPR 0.20; K=3: test TPR 0.80, FPR 0.20; K=4: test TPR 0.84, FPR 0.20; K=5: test TPR 1.00, FPR 0.20; K=6: test TPR 1.00, FPR 0.40; hub>=300: test TPR 0.84, FPR 0.20; hub>=3000: test TPR 0.84, FPR 0.20.

### Frozen rules on the test half

| rule | text | dev BA (fw) | test TPR (fw) | test FPR (fw) | test BA (fw) | test BA 95% CI | test TP/FN/FP/TN (cases) |
|---|---|---|---|---|---|---|---|
| primary | loop_share >= 0.4235 | 1.00 | 0.84 | 0.20 | 0.82 | [0.56, 1.00] | 38/4/1/5 |
| non_circular | timing_coupling >= -0.001939 AND relay_share >= 0.09579 | 0.93 | 0.54 | 0.20 | 0.67 | [0.40, 0.91] | 17/25/1/5 |
| single:loop_share | loop_share >= 0.4235 | 1.00 | 0.84 | 0.20 | 0.82 | [0.56, 1.00] | 38/4/1/5 |
| single:outside_funding_share | outside_funding_share <= 0.7537 | 1.00 | 1.00 | 0.20 | 0.90 | [0.70, 1.00] | 42/0/1/5 |
| single:loop_share_1hop | loop_share_1hop >= 0.125 | 1.00 | 0.59 | 0.20 | 0.69 | [0.40, 0.98] | 33/9/1/5 |
| single:timing_coupling | timing_coupling >= 0.04143 | 0.84 | 0.59 | 0.20 | 0.70 | [0.44, 0.91] | 17/25/1/5 |
| single:shared_funder_share_nonhub | shared_funder_share_nonhub >= 0.6354 | 0.75 | 0.20 | 0.00 | 0.60 | [0.50, 0.80] | 2/40/0/6 |
| single:shared_funder_share | shared_funder_share >= 0.8571 | 0.75 | 0.20 | 0.00 | 0.60 | [0.50, 0.80] | 2/40/0/6 |
| single:payer_hhi | payer_hhi >= 0.01951 | 0.75 | 0.58 | 1.00 | 0.29 | [0.13, 0.45] | 35/7/6/0 |
| single:relay_share | relay_share >= 0.09579 | 0.72 | 0.64 | 0.40 | 0.62 | [0.33, 0.88] | 26/16/2/4 |

### Errors of the primary rule (both halves)

| half | error | family | window | payee | label | n_payers | loop_share | shared_funder_share | payer_hhi | outside_funding_share |
|---|---|---|---|---|---|---|---|---|---|---|
| test | false negative | F04-botpay | W1 | 0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908 | C | 298 | 0.00 | 0.09 | 0.02 | 0.00 |
| test | false negative | F04-botpay | W2 | 0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908 | C | 346 | 0.00 | 0.10 | 0.00 | 0.00 |
| test | false negative | F04-botpay | W3 | 0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908 | C | 346 | 0.00 | 0.06 | 0.01 | 0.00 |
| test | false negative | F04-botpay | W4 | 0x159be9e316bc5fac8ce05aec4eaae46e8f8a4908 | C | 346 | 0.00 | 0.07 | 0.01 | 0.05 |
| test | false positive | F15-losbeto | W4 | 0xd5ba9711a3d052846a3695c70e7fcb8b3168fe7d | N | 13 | 0.97 | 0.00 | 0.95 | 0.62 |

### Single-feature AUC, family-weighted (* exploratory)

| feature | dev | test | all |
|---|---|---|---|
| Loop share (K=4) | 1.00 | 0.91 | 0.97 |
| Loop share (1 hop) | 1.00 | 0.74 | 0.87 |
| Outside funding share | 1.00 | 1.00 | 1.00 |
| Pair reciprocity timing* | 0.84 | 0.51 | 0.66 |
| Payer concentration (HHI) | 0.71 | 0.21 | 0.47 |
| Payer synchrony* | 0.67 | 0.40 | 0.49 |
| Relay share | 0.61 | 0.57 | 0.61 |
| Shared first funder | 0.58 | 0.74 | 0.63 |
| Shared funder, hubs excluded | 0.58 | 0.82 | 0.71 |
| Timing coupling | 0.83 | 0.62 | 0.70 |

### Exact permutation test on the test half

| rule | test families | coordinated | label assignments | observed BA | p |
|---|---|---|---|---|---|
| primary | 10 | 5 | 252 | 0.820 | 0.024 |
| non_circular | 10 | 5 | 252 | 0.668 | 0.143 |

### Positive control: share of injection runs the primary rule flags, by route and ring share

12 base markets x 10 seeds per cell; excluded because the rule already flags their real data: F15-losbeto|0xd5ba9711a3d052846a3695c70e7fcb8b3168fe7d|W4.

| route | 0.2% | 0.5% | 1.0% | 2.0% | 5.0% | 10.0% | 20.0% | 30.0% | 50.0% |
|---|---|---|---|---|---|---|---|---|---|
| direct | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| relay2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| relay4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| relay5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| via_hub | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| common_funder | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

### Positive control near the threshold (supplementary fine grid, added after the pre-set grid ran)

Share of base markets flagged. A ring is flagged exactly when its share passes (threshold - b) / (1 - b), b = the market's existing loop share: 31.5% to 42.4% across the 12 base markets.

| route | 30% | 35% | 38% | 40% | 41% | 42% | 43% | 44% | 45% | 50% |
|---|---|---|---|---|---|---|---|---|---|---|
| direct | 0.00 | 0.08 | 0.08 | 0.17 | 0.17 | 0.17 | 1.00 | 1.00 | 1.00 | 1.00 |
| relay4 | 0.00 | 0.08 | 0.08 | 0.17 | 0.17 | 0.17 | 1.00 | 1.00 | 1.00 | 1.00 |

### Negative control: mean timing features, real vs circularly shifted payment times

| data | coordinated | timing_coupling | relay_share | pair_reciprocity_timing | payer_synchrony |
|---|---|---|---|---|---|
| real timing | 0 | 0.040 | 0.324 | 0.026 | -0.003 |
| real timing | 1 | 0.358 | 0.408 | 0.140 | -0.021 |
| times shuffled | 0 | -0.004 | -0.000 | -0.003 | 0.003 |
| times shuffled | 1 | -0.017 | -0.002 | -0.004 | 0.000 |

### Sensitivity of the frozen rules

Features recomputed under each setting with 20 timing-null draws (200 in the main run); the timing rule's numbers differ from the main run at every setting because its thresholds sit inside the null's sampling noise.

| setting | rule | dev_tpr | dev_fpr | dev_balanced_accuracy | test_tpr | test_fpr | test_balanced_accuracy |
|---|---|---|---|---|---|---|---|
| K=1 | rule | 0.99 | 0.00 | 0.99 | 0.59 | 0.20 | 0.69 |
| K=1 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |
| K=2 | rule | 0.99 | 0.00 | 0.99 | 0.59 | 0.20 | 0.69 |
| K=2 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |
| K=3 | rule | 1.00 | 0.00 | 1.00 | 0.80 | 0.20 | 0.80 |
| K=3 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |
| K=4 | rule | 1.00 | 0.00 | 1.00 | 0.84 | 0.20 | 0.82 |
| K=4 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |
| K=5 | rule | 1.00 | 0.00 | 1.00 | 1.00 | 0.20 | 0.90 |
| K=5 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |
| K=6 | rule | 1.00 | 0.00 | 1.00 | 1.00 | 0.40 | 0.80 |
| K=6 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |
| hub>=300 | rule | 1.00 | 0.00 | 1.00 | 0.84 | 0.20 | 0.82 |
| hub>=300 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |
| hub>=3000 | rule | 1.00 | 0.00 | 1.00 | 0.84 | 0.20 | 0.82 |
| hub>=3000 | non_circular_rule | 0.88 | 0.08 | 0.90 | 0.53 | 0.20 | 0.66 |

## Figures

![Every feature by label, both halves; the line is the frozen threshold.](fig1_features_by_label.png)

*Every feature by label, both halves; the line is the frozen threshold.*

![Positive control: detection of an injected ring by its share of the seller's volume.](fig2_positive_control.png)

*Positive control: detection of an injected ring by its share of the seller's volume.*

![Single-feature AUC on each half.](fig3_feature_auc.png)

*Single-feature AUC on each half.*

![Timing features with real and shuffled payment times.](fig4_timing_shuffle.png)

*Timing features with real and shuffled payment times.*

