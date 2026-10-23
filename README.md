# On-chain collusion evidence

What should count as convincing evidence that AI agents collude? This repo tests
candidate evidence on live agent markets where every payment is public: x402
pay-per-request payments on Base, and agent hiring through TermiX's escrow on BNB
Chain during the Set and Earn campaign. Cases and their labels come from ChainWard's
published on-chain decodes. The same evidence is computed for every case from raw
chain data, a decision rule is chosen on a development half, frozen in a commit,
and then scored on a held-out test half.

Entry to the Apart AI Collusion Research Sprint (Oct 23 to 25, 2026), research
question 2.3.

Status: work in progress during the sprint. See `results/results.md` when present.

## Layout

| Path | What it is |
|---|---|
| `cases/cases.yaml` | Case registry: payee, window, label, source decode and quote, what evidence the decode used |
| `cases/split.json` | Development / test assignment by case family (seeded, made before any feature was computed) |
| `pull/` | Data pulls from public chain RPCs |
| `src/` | Feature computation, rule selection, controls |
| `data/` | Per-case extracts small enough to commit, with hashes of the raw pulls |
| `results/` | Case table, frozen rule, test metrics, controls, `results.md` |

## Preexisting work

Everything in this repo was written during the sprint (from Oct 23, 2026, 00:00 UTC)
unless listed here. The following existed before the sprint and is used, not
re-created:

- **ChainWard's published decodes** (chainward.ai/decodes), written Sep 27 to Oct 13, 2026:
  `x402-on-base`, `x402-on-base-two-weeks-later`, `x402-closed-six`,
  `x402-top-ten-self-funded`, `set-and-earn-week-one`, `set-and-earn-week-one-closed`,
  `termix-on-chain`. They are the source of every case label in `cases/cases.yaml`.
  Their analysis scripts and data are not used here; this repo re-pulls the chain.
- **ChainWard's hire check and seller-demand check** (paid API endpoints, Oct 2026).
  They are not used to compute anything here. Several decodes used them, so where a
  label came from that check it is marked in `label_basis`.
- **ChainWard's Base node** (cw-sentinel), a reth history node. It is only a data
  source; any Base archive RPC gives the same logs.

Nothing here uses private label sets, tip clusters or the paid wallet lists that
accompany some decodes.

## Reproduce

Requires Python 3.12 and `pip install -r requirements.txt`.

1. Pull Base USDC logs (any Base archive RPC with full logs for Sep 1 to Oct 12, 2026):
   `python pull/base_usdc_pull.py --rpc <URL> --start 50715727 --end 52530126 --out data/raw/base`
2. Further steps are added as the pipeline is built.
