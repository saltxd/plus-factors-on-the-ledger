# Spot-check judge protocol

Added Oct 23, 2026, after the freeze; written before the spot-check sample was drawn
(`cases/market_plan.md`, section 3). Each judge receives this file, the sample list and the tools
below, nothing else.

## The question

For each payee and week in the list: was the money that paid this x402 payee in that week
coordinated with the payee, or did it come from payers acting independently?

- **coordinated**: a material part of the week's payment value came from money the payee itself
  supplied (the payee funded the payers, directly or through wallets it funds), or from a closed
  group of wallets that pay each other, or the payee paid the payers back on net. A developer
  paying its own endpoint from a wallet it funded counts here too.
- **independent**: the payers' money came from outside the payee's orbit (exchanges, bridges,
  on-ramps, unrelated wallets), and no money path from the payee to the payers carries a material
  part of the payments.
- **unclear**: the evidence does not settle it, for example money that passes through a
  high-throughput account that could be a shared service, funding older than the data, or a trail
  that leaves USDC on Base.

The units are wallets. One operator with many wallets and several operators acting together look
the same on a ledger, and both count as coordinated here. Do not guess who runs a wallet.

## What to record, per sample

`sample_id, verdict, est_coordinated_share, confidence, reasoning`

- `est_coordinated_share`: your estimate, 0 to 1, of the share of the week's payment value that
  came from the payee's own money or a closed group; blank if you cannot estimate it.
- `confidence`: low, medium or high.
- `reasoning`: two to four sentences naming the key wallets (address prefixes), amounts and the
  money path you found or did not find.

Judge each sample on its own evidence; there is no quota for any verdict.

## Data and tools

- `scripts/spotcheck_tools.py` (run with the repository's `.venv/bin/python`): read-only queries
  over every USDC transfer and EIP-3009 authorisation on Base from Sep 1 to Oct 12, 2026
  (`data/base.duckdb`). `dossier` gives an overview of a payee-week; `inflows`, `outflows`,
  `degree`, `paid` and `sql` let you follow money further. Payments into a payee are the USDC
  transfers its payers authorised (EIP-3009), including those forwarded by a facilitator's proxy
  contract in the same transaction.
- Public explorer pages for contract names and older history (for example
  `https://base.blockscout.com/api/v2/addresses/<address>`), at most 2 requests a second, no API
  keys.

## Rules

- Use on-chain evidence only. Do not open anything else in this repository (README.md, report/,
  results/, cases/ other than this file, src/, data/ other than through the tools), any ChainWard
  decode, check, board or label, or any other file on this machine about these wallets.
- Do not contact anyone, sign up for anything, post anything or pay anything.
- Write your verdicts only to the file you were given.
