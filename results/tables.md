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
