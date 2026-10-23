<div class="tbl">

Table E1: The frozen rule on the whole market, by weekly x402 volume, by weekly rank and by kind of BNB Chain payee (`results/market_summary.json`); Base bands are by x402 volume in the week. The last column is the share of volume the frozen `outside_funding_share <= 0.7537` flags.

| Payees | Payee-weeks | Volume | Flagged | Volume flagged | Outside-funding rule |
|---|---|---|---|---|---|
| Base, $10 to $100 | 548 | $16,147 | 179 (33%) | 35.9% | 32.3% |
| Base, $100 to $1,000 | 135 | $40,006 | 46 (34%) | 32.1% | 40.6% |
| Base, $1,000 or more | 67 | $618,791 | 33 (49%) | 29.2% | 29.2% |
| Base, weekly top 10 | 40 | $545,058 | 21 (52%) | 25.3% | 25.3% |
| Base, weekly top 50 | 200 | $658,402 | 80 (40%) | 29.4% | 29.9% |
| Base, all | 750 | $674,944 | 258 (34%) | 29.5% | 29.9% |
| BNB Chain, ring wallets | 62 | $5,534 | 62 (100%) | 100.0% | 100.0% |
| BNB Chain, others | 9,069 | $489,890 | 1,214 (13%) | 13.6% | 19.5% |
| BNB Chain, all | 9,131 | $495,424 | 1,276 (14%) | 14.6% | 20.4% |

</div>

<div class="tbl">

Table E2: End-to-end positive control (`results/positive_control_e2e.csv`): three markets, five ring shares per route; b is each market's loop share measured by the same pipeline with no ring.

| Route | Designed distance | Measured (all ring payers) | Expected loop share | Runs | Largest error | Flag as predicted |
|---|---|---|---|---|---|---|
| seller to payer | hop 1 | hop 1 | φ + (1 − φ)·b | 15 | 1.1e-16 | 15 of 15 |
| two relays | hop 3 | hop 3 | φ + (1 − φ)·b | 15 | 1.1e-16 | 15 of 15 |
| three relays | hop 4 | hop 4 | φ + (1 − φ)·b | 15 | 1.1e-16 | 15 of 15 |
| four relays | hop 5 | hop 5 | (1 − φ)·b | 15 | 5.6e-17 | 15 of 15 |
| via a hub, two transactions | not reached | not reached | (1 − φ)·b | 15 | 2.8e-17 | 15 of 15 |
| forwarded by the hub, one transaction | hop 1 | hop 1 | φ + (1 − φ)·b | 15 | 5.6e-17 | 15 of 15 |

</div>

<div class="pagebreak"></div>

<div class="appendix-table">

Table E3: The 40 spot-check payees after unblinding (`results/spotcheck_unblinded.csv`, which also holds every reasoning). Judge columns: C coordinated, I independent, U unclear, then the judge's estimated coordinated share.

| Sample | Payee | Week | Rule | Loop share | Outside funding | Judge A | Judge B |
|---|---|---|---|---|---|---|---|
| S01 | 0x4ad9fcc1 | W2 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S02 | 0x6bab1d63 | W3 | flag | 1.00 | 0.95 | I 0.00 | I 0.00 |
| S03 | 0x0bd02144 | W2 | flag | 1.00 | 0.55 | I 0.00 | I 0.00 |
| S04 | 0x7f629403 | W2 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S05 | 0x1c656644 | W2 | flag | 1.00 | 0.76 | C 1.00 | C 1.00 |
| S06 | 0x836be278 | W4 | no | 0.00 | 1.00 | U | U |
| S07 | 0xbc5bafda | W3 | no | 0.00 | 1.00 | C 1.00 | C 1.00 |
| S08 | 0x837c40e2 | W3 | flag | 0.90 | 0.54 | C 0.70 | C 0.70 |
| S09 | 0xd593832c | W3 | flag | 0.96 | 0.91 | C 0.95 | C 0.95 |
| S10 | 0x85af15f3 | W1 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S11 | 0x768d3897 | W1 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S12 | 0xb7c76e6a | W1 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S13 | 0xe6dab093 | W1 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S14 | 0xd8ba61a0 | W4 | flag | 1.00 | 0.27 | C 1.00 | C 1.00 |
| S15 | 0xce668a6e | W1 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S16 | 0x17d38086 | W1 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S17 | 0xaf6ee95c | W4 | no | 0.00 | 0.00 | C 1.00 | C 1.00 |
| S18 | 0x0a84297d | W3 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S19 | 0x33e59490 | W1 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S20 | 0x788b4ca1 | W1 | flag | 1.00 | 0.90 | C 0.97 | C 0.98 |
| S21 | 0x4df66b6c | W2 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S22 | 0x4cd50150 | W1 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S23 | 0xc34f3d05 | W1 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S24 | 0x07e079b1 | W1 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S25 | 0x430a232c | W3 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S26 | 0xf1cbc619 | W1 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S27 | 0x8060f6e3 | W3 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S28 | 0x434ca49f | W1 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S29 | 0x3a876a77 | W3 | flag | 1.00 | 0.00 | C 1.00 | C 1.00 |
| S30 | 0x91410228 | W1 | flag | 0.69 | 0.48 | C 0.69 | C 0.69 |
| S31 | 0x96368628 | W4 | flag | 0.92 | 0.23 | C 0.90 | C 0.92 |
| S32 | 0x8aab9a6d | W3 | flag | 0.94 | 0.84 | C 0.94 | C 0.94 |
| S33 | 0x6454a645 | W4 | flag | 1.00 | 0.12 | C 0.95 | C 0.94 |
| S34 | 0xf3ecfe1d | W3 | flag | 1.00 | 0.99 | C 1.00 | U |
| S35 | 0x0748cc42 | W3 | no | 0.00 | 1.00 | C 1.00 | C 1.00 |
| S36 | 0xeb931657 | W2 | no | 0.00 | 1.00 | I 0.00 | I 0.00 |
| S37 | 0x4f180b77 | W1 | flag | 1.00 | 0.86 | I 0.00 | I 0.00 |
| S38 | 0x5976376b | W3 | flag | 0.88 | 0.99 | C 0.88 | U |
| S39 | 0xb13b783a | W4 | no | 0.00 | 0.00 | C 1.00 | C 1.00 |
| S40 | 0x0440383b | W3 | flag | 0.91 | 0.86 | C 0.50 | C 0.50 |

</div>
