# Spot-check: the prompt each judge received

Added Oct 23, 2026, after the freeze. Committed with the blinded sample list, before either judge
started. Two separate AI agent sessions (judge A and judge B) received this text, identical except
for the output path, and nothing else from this project: no feature values, flags, rule, results
or the stratum of any sample.

---

You are an independent judge in a blinded spot-check of on-chain payment evidence. Work only from
the chain data and tools described below.

1. Read `$HOME/Forge/onchain-collusion-evidence/cases/spotcheck_judge_protocol.md` and
   follow it exactly. It defines the question and the three verdicts (coordinated, independent,
   unclear).
2. The list to judge is `$HOME/Forge/onchain-collusion-evidence/results/spotcheck_sample.csv`:
   40 rows (sample_id, payee, window and its dates and blocks). Judge every row.
3. Tools: from the directory `$HOME/Forge/onchain-collusion-evidence`, run
   `.venv/bin/python scripts/spotcheck_tools.py ...` (read its docstring with `--help` or by
   reading that one file). Start each sample with `dossier <payee> <window>`, then follow the
   money with `inflows`, `outflows`, `degree`, `paid`, `between` or `sql` as needed. Public explorer
   pages (for example `https://base.blockscout.com/api/v2/addresses/<address>`) are allowed for
   contract names and history before Sep 1, at most 2 requests a second, no keys.
4. Do not open any other file in that repository or on this machine (no README, report, results
   other than the sample list, cases other than the protocol, src, data, logs, git history), and do
   not use any ChainWard decode, check, board or label. Do not contact anyone, sign up for anything,
   post or pay.
5. Write your verdicts as a CSV to `<OUTPUT PATH>` with the header
   `sample_id,verdict,est_coordinated_share,confidence,reasoning` (one row per sample, reasoning in
   double quotes, no line breaks inside it). Write the file progressively so work is not lost.
6. Give each sample a fair look; there is no quota for any verdict, and "unclear" is a valid
   answer when the evidence does not settle it.
7. When done, reply with the number of verdicts of each kind and any tool problems.

Output paths: judge A `/tmp/cw_judge_a/verdicts.csv`, judge B `/tmp/cw_judge_b/verdicts.csv`.
