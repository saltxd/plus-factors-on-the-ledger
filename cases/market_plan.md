# Whole-market run, spot-check and end-to-end positive control: plan

Added Oct 23, 2026 (about 16:00 UTC), after the freeze (commit `f99f40e`) and after the
test-half results. Written before any feature, flag or count of the market populations below
was computed. The frozen rule (`loop_share >= 0.4235`, K = 4, hub >= 1,000 counterparties,
14-day lookback, `results/frozen_rule.json`) and the code that computes it are not changed; the
test-half results stay as they are. Everything here is new work of Oct 23 to 24, 2026.

## 1. Base: every x402 payee in W1 to W4

- **x402 payment.** A payment under the frozen definition (a USDC transfer into the payee inside
  the window that the payer authorised with EIP-3009, directly or through a contract that forwards
  it in the same transaction) whose transaction was sent by an address on x402scan's public Base
  facilitator list at commit `f205fbe` (`packages/external/facilitators`, read by
  `pull/x402scan_facilitators.py`). This is the definition the decodes used. Transaction senders
  are read from ChainWard's node for every transaction with an `AuthorizationUsed` log in W1 to W4
  (`pull/base_tx_senders.py`).
- **Payee.** The final recipient. A contract that forwards an authorised transfer in the same
  transaction (the frozen forwarding rule: 50% to 100% of the amount, later in the log order) is a
  proxy, not a payee, and the payment counts for the wallet it forwards to.
- **Floor: $10 of x402 volume in the window,** chosen before any population count. Reasons:
  below about $10 a week (about 1,250 payments at the median x402 price of $0.008 in [D1]) a payee
  is mostly a developer test or dust, where a loop share describes a few dollars; leaderboards and
  rewards, the reason to fake demand, rank sellers by volume; and every payee needs its own reach
  walk. Results are also reported in bands: $10 to $100, $100 to $1,000, $1,000 and more.
- **Excluded up front:** payees that are themselves on the facilitator list. Payments with
  payer = payee are dropped, as in the frozen extraction.
- **Features:** `src/extract_base.py` and `src/features.py` unchanged (payments are all EIP-3009
  payments into the payee, as frozen, K = 4, hub >= 1,000). Timing features use 20 null draws
  instead of 200 (the primary rule uses no timing). A payee whose reach walk hits the 200,000
  cap before hop 4 is reported; its loop share is then a lower bound.
- **Reported:** payee-weeks and distinct payees flagged; share of x402 volume flagged, per window
  and pooled; by volume band; share of the top 10 and top 50 payees' volume flagged in each window
  (ranked by x402 volume over the 7 days, as x402scan and Agent402 rank sellers); share of the
  USDC on Agent402's published top ten of Oct 13, 01:19 UTC ([D4], close to W4) that the rule
  flags in W4. The same numbers for the frozen non-circular rule and for outside funding share are
  reported as secondary.

## 2. BNB Chain: every Set and Earn payee

Every ERC-8004 owner (read at block 126,344,213) of an agent with a TermiX order created in the
SE window (Oct 1 to 8), no floor; payments, hire graph, K = 4 and hub >= 1,000 as in
`src/extract_bsc.py`. Reported: payees flagged and share of order-budget volume flagged. The 62 ring
wallets appear only as `ring48-NN` / `group14-NN`; agent ids and order ids are not written for
any payee. No public leaderboard of Set and Earn exists that we know of, so none is used.

## 3. Blinded spot-check (Base)

BNB Chain is left out: the only BNB Chain evidence here is the hire graph the rule itself reads,
so a judge could only re-derive the rule.

- **Eligible:** Base payee-weeks from section 1 whose payee the published decodes did not examine:
  not printed in full or by an 8-hex-digit prefix in any of the seven decodes [D1] to [D7] or in
  `cases/cases.yaml`, and not in the top 30 by x402 volume in any window (the decodes traced the
  top sellers of their weeks).
- **Draw** (`src/spotcheck.py`, seed 20261024): 25 distinct payees from the eligible payee-weeks the
  frozen rule flags and 15 distinct payees from the eligible payee-weeks it does not flag (each
  payee once, with one of its weeks of that stratum drawn at random; a payee drawn as flagged is
  not drawn again as unflagged). If a stratum has fewer payees, all are taken. The 40 are shuffled
  into one list `S01` to `S40`; the stratum key is kept out of the repository until the verdicts
  are committed.
- **Judges:** two separate AI agent sessions with no access to features, flags, the rule or the
  key. Each gets only the list and read-only tools over the same chain data
  (`scripts/spotcheck_tools.py`: every USDC transfer and EIP-3009 authorisation on Base, Sep 1 to
  Oct 12), plus public explorer pages at most 2 requests a second, and follows
  `cases/spotcheck_judge_protocol.md`. Each records, per payee: verdict (coordinated /
  independent / unclear), an estimated share of the week's payment value that came from the
  payee's own money or a closed group, confidence and reasoning. Both verdict files are committed
  before the key is joined.
- **Reported:** of flagged payees, the share each judge calls coordinated (exact binomial 95%
  interval); of unflagged payees, the share called coordinated (misses); agreement between the
  judges; every verdict next to the rule's output and, after unblinding, the feature values.

## 4. A public label source ChainWard did not write

Agent402's public index (`agent402.tools/api/index`, read on Oct 23) carries a Base router verdict
`settlement_self_funded`: the seller's settlement history without payments made with USDC the
seller had sent the payer is below its floor. For payees in section 1 that the index lists by
Base payTo, the rule's flag (in any week) is compared with that verdict. It is a different
measure (one hop, first in first out, history to Oct 23) over a different period, so this is
agreement, not accuracy.

## 5. End-to-end positive control

The pre-sprint positive control set each ring payer's hop distance by hand, so it did not test
the reach walk. Here synthetic rows go into the transfer and authorisation data the extraction
reads, and `src/extract_base.py` and `src/features.py` run unchanged.

- **Markets:** three cases the rule does not flag, chosen by label and size: F10-clashofcoins W1
  (I, 132 payers), F12-stableenrich W1 (I, 121 payers), F16-cheaptokens W4 (N, 11 payers, the
  one with a non-zero baseline loop share).
- **Ring:** 5 synthetic payers paying the seller by EIP-3009 (a synthetic `AuthorizationUsed` row
  per payment), amounts drawn from the market's own payments and scaled so the ring carries share
  phi of the window's payment value; funding transfers in separate transactions inside lookback
  plus window.
- **Routes:** direct (seller to payer, hop 1); relay3 (two relays, hop 3); relay4 (three relays,
  hop 4, the limit); relay5 (four relays, hop 5); via_hub (seller to a real address with at least
  1,000 counterparties, then that address to the payer in a later transaction; not reached); via_forwarder
  (the same real address forwards the seller's transfer to the payer in the same transaction; the
  forwarding rule passes it through, hop 1).
- **phi:** 0.1, 0.3, 0.5, and phi* - 0.02 and phi* + 0.02 with phi* = (0.4235 - b) / (1 - b), b the
  market's loop share measured by the same pipeline with no ring.
- **Expected:** loop share phi + (1 - phi) b on reached routes and (1 - phi) b on relay5 and
  via_hub; hop distance as designed; the flag flips between phi* - 0.02 and phi* + 0.02 on reached
  routes. Reported: measured against expected for every run, and every discrepancy.
- **The base data is never changed.** The synthetic rows live in a separate scratch database that
  reads `data/base.duckdb` read-only through views (`tr` = real rows plus synthetic rows); the
  scratch database is deleted after the run, and the row counts of `data/base.duckdb` are checked
  before and after.

## 6. Reach-walk diagram

A figure generated by code (`src/fig_reach_walk.py`, `results/fig_reach_walk.png`) from the
committed case tables, with worked examples: X Pay's payers one transfer from its payTo, and
BotPay's five hops, one beyond the reach limit.
