# Hypotheses, written before any feature was computed

Written Oct 23, 2026 (about 06:55 UTC), after the case registry and split were committed
and before the full data pull finished. The only data seen at this point: a one-day
debug slice (Sep 22-24 Base blocks) used to test the extraction code, which showed
payment counts and reach-set sizes for the W2 cases, and that BotPay's payers sit five
transfers from its payTo (payTo -> contract -> root -> funders -> buyers -> payers), one
beyond the K = 4 reach limit. No feature value was computed on it.

Framing: antitrust's plus-factors doctrine says parallel conduct is lawful on its own and
inferring agreement needs additional evidence. On a payment ledger, "parallel conduct" is
similar behaviour (the same funder, the same amounts, the same timing, a few payers); a
"plus factor" is behaviour that only makes sense under coordination, above all paying
fees to move your own money in a circle.

- **H1 (plus factor).** `loop_share` separates coordinated from other cases on the test half.
  Expected strong, and partly circular: most decodes reached their label by tracing loops.
- **H2 (parallel conduct, common infrastructure).** A rule on `shared_funder_share` alone
  flags the "linked, no loop" cases (one wallet seeding many buyers; buyers funded through an
  on-ramp), so its false-positive rate on L cases is high. Excluding hubs
  (`shared_funder_share_nonhub`) lowers it but does not remove it (AX1's seeder is not a hub).
- **H3 (parallel conduct, concentration).** A rule on `payer_hhi` flags concentrated but
  independent demand (a seller with eight payers; single-payment payTos), so concentration
  alone is not evidence.
- **H4 (timing).** `timing_coupling` carries signal the decodes did not use, weaker than
  `loop_share`. `relay_share` is confounded by checkout flows, where a wallet is funded
  and pays at once without any coordination.
- **H5 (blind spots).** Loop evidence misses loops routed through hubs (exchanges,
  custodial accounts) and loops longer than K hops; BotPay is expected to be a false negative
  at K = 4.
- **Positive control.** An injected seller-funded ring is flagged once its share of the
  seller's volume passes the frozen threshold (minus the seller's existing loop share) when
  the seller's money reaches it within K hops through non-hub wallets, and is not flagged at
  any size when routed through a hub or over more than K hops. A ring of payers funded by one
  outside wallet with no loop (parallel conduct) is not flagged by a loop-based rule.
- **Category (c), talk without action.** Payment ledgers carry no messages, so this sprint
  cannot test collusive talk directly. The closest available analogue is a visible link
  without coordinated payments (the L cases); the prediction for them is H2.
