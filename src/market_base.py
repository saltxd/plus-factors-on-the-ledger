"""Whole-market run of the frozen rule on Base: every x402 payee in W1 to W4 above the floor.

Added Oct 23 to 24, 2026, after the freeze (plan: cases/market_plan.md, section 1). The rule,
the extraction (src/extract_base.py) and the features (src/features.py) are used unchanged;
this file only decides which payees enter and runs them.

Stages
  candidates  per window: every payment under the frozen definition (EIP-3009, direct or through a
              same-transaction proxy); a contract that forwards an authorised transfer in the same
              transaction is a proxy, and the payment counts for its final recipient. Candidates are
              payees with at least FLOOR_USD of such payments. Writes the transactions whose sender
              must be read: all of a candidate's payment transactions when it has at most
              MAX_EXACT_TX of them, else MAX_EXACT_TX draws of its payments with probability
              proportional to value (data/market/sender_draws.csv.gz)
              -> data/raw/base_senders/pairs_candidates.txt.gz (pull/base_tx_senders.py --pairs)
  population  x402 volume per candidate (payments whose transaction a listed facilitator sent; for a
              sampled candidate, its payment volume times the share of draws a facilitator sent);
              candidates with at least FLOOR_USD of x402 volume enter
              -> results/market_base_population.csv
  extract     src/extract_base.py extract_window + write_case for the population, in batches
              -> <out>/<case dir>/ (payments, payer_inflows, seller_outflows, payer_reach, meta.json)
  features    src/features.py compute_features for every extracted payee (20 timing-null draws)
              -> <features csv>

The raw data is read through views in a scratch DuckDB file that attaches data/base.duckdb
read-only, so the base data cannot change.

  python src/market_base.py population
  python src/market_base.py extract --out <dir>
  python src/market_base.py features --cases <dir> --csv <file>
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import extract_base as eb
from cases import Case, load_registry, window_bounds

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("market_base")
FLOOR_USD = 10.0
MAX_EXACT_TX = 1000
DRAW_SEED = 20261023
WINDOWS = ["W1", "W2", "W3", "W4"]
BANDS = [(10.0, 100.0, "$10-100"), (100.0, 1000.0, "$100-1k"), (1000.0, float("inf"), ">=$1k")]


def connect(scratch: Path, memory: str = "8GB", threads: int = 8) -> duckdb.DuckDBPyConnection:
    """A scratch database whose tr / auth are views over data/base.duckdb, attached read-only."""
    scratch.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(scratch))
    con.execute(f"SET memory_limit='{memory}'; SET threads={threads}; SET preserve_insertion_order=false")
    con.execute(f"ATTACH '{ROOT / 'data' / 'base.duckdb'}' AS b (READ_ONLY)")
    con.execute("CREATE OR REPLACE VIEW tr AS SELECT * FROM b.tr")
    con.execute("CREATE OR REPLACE VIEW auth AS SELECT * FROM b.auth")
    for w in WINDOWS:
        con.execute(f"CREATE TABLE IF NOT EXISTS deg_{w} AS SELECT * FROM b.deg_{w}")
    return con


def load_senders(con: duckdb.DuckDBPyConnection, empty: bool = False) -> None:
    src = ROOT / "data" / "raw" / "base_senders"
    if empty:
        con.execute("CREATE OR REPLACE TABLE senders (block INTEGER, txi INTEGER, frm VARCHAR, dst VARCHAR)")
    else:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE senders AS
            SELECT DISTINCT * FROM read_csv('{src}/senders_*.tsv.gz', delim='\t', header=false,
                columns={{'block':'INTEGER','txi':'INTEGER','frm':'VARCHAR','dst':'VARCHAR'}})
            """
        )
    con.execute(
        f"CREATE OR REPLACE TABLE facilitators AS SELECT lower(address) AS a, facilitator FROM read_csv('{ROOT / 'data' / 'x402scan_facilitators_base.csv'}')"
    )


def window_payments(con: duckdb.DuckDBPyConnection, w0: int, w1: int) -> None:
    """Every payment in the window under the frozen definition, for every recipient at once, with
    the transaction's sender. Same SQL logic as extract_base._x402_payments, without the payee filter.
    TEMP TABLE mpay(payee, payer, val, block, txi, li, via, frm, x402)."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE atx AS SELECT DISTINCT block, txi FROM auth WHERE block BETWEEN {w0} AND {w1}
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE wt AS
        SELECT t.* FROM tr t SEMI JOIN atx USING (block, txi)
        WHERE t.block BETWEEN {w0} AND {w1} AND t.val > 0 AND t.src != t.dst
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE m_direct AS
        SELECT DISTINCT c.dst AS payee, c.src AS payer, c.val, c.block, c.txi, c.li, 'direct' AS via
        FROM wt c JOIN auth a ON a.block = c.block AND a.txi = c.txi AND a.authorizer = c.src
        WHERE a.block BETWEEN {w0} AND {w1}
        """
    )
    # a direct payment its recipient forwards in the same transaction (the frozen forwarding rule)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE m_forwarded AS
        SELECT DISTINCT d.block, d.li FROM m_direct d JOIN wt c
          ON c.block = d.block AND c.txi = d.txi AND c.src = d.payee AND c.li > d.li
         AND c.val <= d.val AND c.val * 2 >= d.val
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE m_pass AS
        SELECT c.dst AS payee, arg_max(t1.src, t1.li) AS payer, c.val, c.block, c.txi, c.li, 'passthrough' AS via
        FROM wt c
        JOIN wt t1 ON t1.block = c.block AND t1.txi = c.txi AND t1.dst = c.src AND t1.li < c.li
            AND t1.val >= c.val AND c.val * 2 >= t1.val
        JOIN auth a ON a.block = t1.block AND a.txi = t1.txi AND a.authorizer = t1.src
        WHERE a.block BETWEEN {w0} AND {w1}
          AND NOT EXISTS (SELECT 1 FROM m_direct d WHERE d.block = c.block AND d.li = c.li)
        GROUP BY c.dst, c.val, c.block, c.txi, c.li
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE mpay AS
        WITH u AS (
            SELECT d.*, (f.block IS NOT NULL) AS forwarded FROM m_direct d LEFT JOIN m_forwarded f ON f.block = d.block AND f.li = d.li
            UNION ALL
            SELECT p.*, false AS forwarded FROM m_pass p
        )
        SELECT u.*, s.frm, (s.frm IN (SELECT a FROM facilitators)) AS x402
        FROM u LEFT JOIN senders s ON s.block = u.block AND s.txi = u.txi
        WHERE u.payer != u.payee
        """
    )


CAND_SQL = f"""
    SELECT payee, sum(val)/1e6 AS eip3009_volume, count(*) AS eip3009_payments, count(DISTINCT payer) AS eip3009_payers,
           count(DISTINCT (block, txi)) AS eip3009_txs
    FROM mpay WHERE NOT forwarded AND payee NOT IN (SELECT a FROM facilitators)
    GROUP BY payee HAVING sum(val)/1e6 >= {FLOOR_USD}
"""


def candidates(con: duckdb.DuckDBPyConnection) -> None:
    """Candidates and the transactions whose sender must be read (see the module docstring)."""
    import numpy as np

    reg = load_registry()
    load_senders(con, empty=True)
    pairs: set[tuple[int, int]] = set()
    draws_out = []
    for wi, w in enumerate(WINDOWS):
        _, _, w0, w1 = window_bounds(reg, w)
        window_payments(con, w0, w1)
        cand = con.execute(CAND_SQL).df()
        small = cand[cand["eip3009_txs"] <= MAX_EXACT_TX]["payee"].tolist()
        big = sorted(cand[cand["eip3009_txs"] > MAX_EXACT_TX]["payee"].tolist())
        con.execute("CREATE OR REPLACE TEMP TABLE sel AS SELECT unnest(?) AS payee", [small])
        pairs |= set(con.execute("SELECT DISTINCT block, txi FROM mpay SEMI JOIN sel USING (payee) WHERE NOT forwarded").fetchall())
        rng = np.random.default_rng(DRAW_SEED + wi)
        for p in big:
            pay = con.execute(
                "SELECT block, txi, li, val::DOUBLE AS val FROM mpay WHERE payee = ? AND NOT forwarded ORDER BY block, li", [p]
            ).df()
            idx = rng.choice(len(pay), size=MAX_EXACT_TX, replace=True, p=(pay["val"] / pay["val"].sum()).to_numpy())
            d = pay.iloc[idx].assign(window=w, payee=p)
            draws_out.append(d)
            pairs |= set(zip(d["block"].astype(int), d["txi"].astype(int)))
        log.info("%s: %d candidates, %d with every sender read, %d sampled; %d transactions so far", w, len(cand), len(small), len(big), len(pairs))
    out = ROOT / "data" / "market"
    out.mkdir(parents=True, exist_ok=True)
    pd.concat(draws_out, ignore_index=True)[["window", "payee", "block", "txi", "li", "val"]].to_csv(out / "sender_draws.csv.gz", index=False)
    pp = ROOT / "data" / "raw" / "base_senders" / "pairs_candidates.txt.gz"
    import gzip

    with gzip.open(pp, "wt") as f:
        f.writelines(f"{b} {x}\n" for b, x in sorted(pairs))
    log.info("wrote %s: %d transactions", pp, len(pairs))


def population(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    reg = load_registry()
    load_senders(con)
    draws = pd.read_csv(ROOT / "data" / "market" / "sender_draws.csv.gz")
    snd = con.execute("SELECT block, txi, frm, (frm IN (SELECT a FROM facilitators)) AS fac FROM senders").df()
    draws = draws.merge(snd, on=["block", "txi"], how="left")
    if draws["frm"].isna().any():
        raise SystemExit(f"{int(draws['frm'].isna().sum())} drawn transactions have no sender")
    share = draws.groupby(["window", "payee"])["fac"].mean()
    rows = []
    for w in WINDOWS:
        t = time.time()
        _, _, w0, w1 = window_bounds(reg, w)
        window_payments(con, w0, w1)
        cand = con.execute(CAND_SQL).df()
        exact = con.execute(
            """
            SELECT payee, sum(CASE WHEN x402 THEN val ELSE 0 END)/1e6 AS x402_volume, sum(x402::INT) AS x402_payments,
                   count(DISTINCT CASE WHEN x402 THEN payer END) AS x402_payers, count(*) - count(frm) AS no_sender
            FROM mpay WHERE NOT forwarded GROUP BY payee
            """
        ).df()
        c = cand.merge(exact, on="payee", how="left")
        big = c["eip3009_txs"] > MAX_EXACT_TX
        if (c.loc[~big, "no_sender"] > 0).any():
            raise SystemExit(f"{w}: candidates with unread senders: {c.loc[~big & (c['no_sender'] > 0), 'payee'].tolist()[:5]}")
        s_ = share.xs(w, level="window") if w in share.index.get_level_values(0) else pd.Series(dtype=float)
        c["x402_share_of_value"] = np.where(big, c["payee"].map(s_), c["x402_volume"] / c["eip3009_volume"])
        c.loc[big, "x402_volume"] = c.loc[big, "eip3009_volume"] * c.loc[big, "x402_share_of_value"]
        c.loc[big, ["x402_payments", "x402_payers"]] = np.nan
        c["x402_estimated"] = big
        c["window"] = w
        rows.append(c[c["x402_volume"] >= FLOOR_USD])
        log.info("%s: %d candidates, %d in population, x402 volume %.2f (%.0fs)", w, len(c), int((c["x402_volume"] >= FLOOR_USD).sum()),
                 float(c.loc[c["x402_volume"] >= FLOOR_USD, "x402_volume"].sum()), time.time() - t)
    pop = pd.concat(rows, ignore_index=True)
    pop["rank"] = pop.groupby("window")["x402_volume"].rank(method="first", ascending=False).astype(int)
    pop["band"] = pd.cut(pop["x402_volume"], [b[0] for b in BANDS] + [float("inf")], labels=[b[2] for b in BANDS], right=False).astype(str)
    cols = ["window", "rank", "payee", "band", "x402_volume", "x402_estimated", "x402_share_of_value", "x402_payments", "x402_payers",
            "eip3009_volume", "eip3009_payments", "eip3009_payers", "eip3009_txs"]
    return pop.sort_values(["window", "rank"])[cols]


def extract(con: duckdb.DuckDBPyConnection, pop: pd.DataFrame, out: Path, batch: int, windows: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for w in windows:
        payees = sorted(pop[pop["window"] == w]["payee"])
        todo = [p for p in payees if not (out / f"MARKET-base__{p}__{w}" / "meta.json").exists()]
        log.info("%s: %d payees, %d to extract", w, len(payees), len(todo))
        for i in range(0, len(todo), batch):
            part = todo[i : i + batch]
            t = time.time()
            bounds = eb.extract_window(con, w, part, 1000, 4)
            for p in part:
                case = Case(case_id=f"MARKET-base|{p}|{w}", family="MARKET-base", chain="base", market="x402", label="market",
                            y=-1, payee=p, window=w, half="market")
                eb.write_case(con, case, p, out, bounds, 1000, 4)
            log.info("%s batch %d-%d done in %.0fs", w, i, i + len(part), time.time() - t)


def features(cases: Path, csv: Path, n_null: int = 20) -> pd.DataFrame:
    from features import compute_features
    from run_features import load_case, meta_cols

    rows = []
    for d in sorted(p for p in cases.iterdir() if (p / "meta.json").exists()):
        cd = load_case(d)
        meta = cd.meta
        row = {**meta_cols(meta), "reach_by_hop": json.dumps(meta.get("reach_by_hop")), **compute_features(cd, k=4, n_null=n_null)}
        rows.append(row)
    df = pd.DataFrame(rows)
    csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv, index=False, float_format="%.6g")
    log.info("features for %d payee-weeks -> %s", len(df), csv)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["candidates", "population", "extract", "features"])
    ap.add_argument("--scratch", default=str(ROOT / "data" / "scratch" / "market.duckdb"))
    ap.add_argument("--out", default=str(ROOT / "data" / "market" / "base"))
    ap.add_argument("--cases", default=str(ROOT / "data" / "market" / "base"))
    ap.add_argument("--csv", default=str(ROOT / "data" / "market" / "base_features.csv"))
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--windows", nargs="*", default=WINDOWS)
    ap.add_argument("--memory", default="8GB")
    ap.add_argument("--threads", type=int, default=8)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.stage == "features":
        features(Path(args.cases), Path(args.csv))
        return
    con = connect(Path(args.scratch), args.memory, args.threads)
    if args.stage == "candidates":
        candidates(con)
    elif args.stage == "population":
        pop = population(con)
        pop.to_csv(ROOT / "results" / "market_base_population.csv", index=False, float_format="%.6f")
        log.info("population: %s", pop.groupby("window").agg(payees=("payee", "size"), volume=("x402_volume", "sum")).to_dict())
    else:
        pop = pd.read_csv(ROOT / "results" / "market_base_population.csv")
        extract(con, pop, Path(args.out), args.batch, args.windows)


if __name__ == "__main__":
    main()
