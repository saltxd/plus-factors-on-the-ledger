"""Market-level check on a market not used anywhere in rule selection: TermiX's Base escrow.

The termix-on-chain decode published an aggregate, not wallet labels: 99.23% of TermiX's
fees in Aug 31 - Sep 29 came from wallets that hire each other. Here a seeded,
volume-weighted random sample of the payees paid through the Base USDC escrow during W1
(Sep 15-21) is extracted with the same reach walk as the x402 cases, so the frozen rule
can be applied and the share of the market's volume it flags compared with the published
share. Nothing from this step feeds the rule.

Market mapping (same as BNB Chain, but with the full USDC graph available):
  payment     a TermiX order created during the window for an agent the payee was paid for:
              payer = buyer, value = budget, time = creation.
  hire edge   each order settled in lookback + window becomes buyer -> payee (the wallet the
              escrow paid in the settlement transaction), value = payout. Transfers into and out
              of the escrow itself are dropped from the graph (the escrow pays out in a later
              transaction, so it would otherwise be a hub that cuts every trail).

  python src/extract_termix_base.py --db base.duckdb --raw data/raw/base --sample 300
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import duckdb
import numpy as np

import extract_base as eb
from cases import LOOKBACK_DAYS, Case, base_block_at, load_registry, window_bounds

log = logging.getLogger("termix_base")
ESCROW = "0xc3d963e0856a2c2d6f75c83c1355f680fd8f9f10"
FEE_SAFE = "0x1095ded95cb6e81c01204f7a94950dd559195e42"
T_CREATED = "0xac4801e0cf6c58578da06571bd840e030ab529c0ca954375ff4e7b45086fef7c"
T_SETTLED = "0xdd533cd5141138294c3af311a217f94675d6ab3f45a7eee05943a2d51058e1a7"


def build_orders(con: duckdb.DuckDBPyConnection, raw: Path) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TABLE esc_raw AS SELECT * FROM read_csv('{raw}/escrow_*.tsv.gz', delim='\t', header=false,
            columns={{'block':'INTEGER','txi':'INTEGER','li':'INTEGER','tx':'VARCHAR','topics':'VARCHAR','data':'VARCHAR'}})
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE t_created AS
        SELECT split_part(topics, ';', 2) AS order_id,
               '0x' || right(split_part(topics, ';', 3), 40) AS buyer,
               split_part(topics, ';', 4) AS agent_hex,
               block, txi, li,
               ('0x' || substr(data, 67, 64))::HUGEINT AS budget_raw
        FROM esc_raw WHERE starts_with(topics, '{T_CREATED}')
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE t_settled AS
        SELECT split_part(topics, ';', 2) AS order_id, block, txi FROM esc_raw WHERE starts_with(topics, '{T_SETTLED}')
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE t_payout AS
        SELECT s.order_id, s.block, s.txi, arg_max(t.dst, t.val) AS payee, max(t.val) AS payout
        FROM t_settled s JOIN tr t ON t.block = s.block AND t.txi = s.txi AND t.src = '{ESCROW}' AND t.dst != '{FEE_SAFE}'
        GROUP BY s.order_id, s.block, s.txi
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE t_orders AS
        SELECT c.order_id, c.buyer, c.agent_hex, c.block AS created_block, c.budget_raw,
               p.block AS settled_block, p.txi AS settled_txi, p.payee, p.payout
        FROM t_created c LEFT JOIN t_payout p USING (order_id)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE t_agent_payee AS
        SELECT agent_hex, arg_max(payee, settled_block) AS payee FROM t_orders WHERE payee IS NOT NULL GROUP BY agent_hex
        """
    )
    n = con.execute("SELECT count(*), count(payee), count(DISTINCT buyer), count(DISTINCT payee) FROM t_orders").fetchone()
    log.info("TermiX Base orders: %s (orders, settled with payee, buyers, payees)", n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", default="data/market/termix_base_W1")
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20261023)
    ap.add_argument("--window", default="W1")
    ap.add_argument("--memory", default="5GB")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    con = duckdb.connect(args.db)
    con.execute(f"SET memory_limit='{args.memory}'; SET threads=6; SET preserve_insertion_order=false")
    build_orders(con, Path(args.raw))
    reg = load_registry()
    t0, t1, w0, w1 = window_bounds(reg, args.window)
    d0 = base_block_at(t0 - LOOKBACK_DAYS * 86400)
    # payees of the window, weighted by order volume; seeded volume-weighted sample without replacement
    vol = con.execute(
        f"""
        SELECT ap.payee, sum(o.budget_raw)::DOUBLE / 1e6 AS v FROM t_orders o JOIN t_agent_payee ap USING (agent_hex)
        WHERE o.created_block BETWEEN {w0} AND {w1} GROUP BY ap.payee ORDER BY ap.payee
        """
    ).fetchall()
    payees = np.array([p for p, _ in vol])
    v = np.array([x for _, x in vol], dtype=float)
    rng = np.random.default_rng(args.seed)
    # draws with replacement, probability proportional to volume: the mean of a 0/1 flag over the
    # draws is an unbiased estimate of the flagged share of volume (Hansen-Hurwitz)
    draws = rng.choice(payees, size=args.sample, replace=True, p=v / v.sum()).tolist()
    mult = {p: draws.count(p) for p in sorted(set(draws))}
    pick = sorted(mult)
    log.info("window %s: %d payees, $%.0f of orders; %d draws, %d distinct payees", args.window, len(payees), v.sum(), len(draws), len(pick))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "population.json").write_text(json.dumps({"window": args.window, "payees": len(payees), "volume": float(v.sum()),
                                                     "draws": len(draws), "distinct": len(pick), "seed": args.seed,
                                                     "design": "with replacement, probability proportional to order volume in window",
                                                     "multiplicity": mult}, indent=2) + "\n")
    # graph: every USDC transfer except those touching the escrow, plus hire edges
    con.execute(
        f"""
        CREATE OR REPLACE TABLE hire_edges AS
        SELECT settled_block AS block, settled_txi AS txi, -1 AS li, buyer AS src, payee AS dst, payout AS val
        FROM t_orders WHERE payee IS NOT NULL AND settled_block BETWEEN {d0} AND {w1}
        """
    )
    con.execute("ALTER TABLE tr RENAME TO tr_usdc")
    try:
        con.execute(
            f"""
            CREATE OR REPLACE VIEW tr AS
            SELECT * FROM tr_usdc WHERE src != '{ESCROW}' AND dst != '{ESCROW}'
            UNION ALL SELECT * FROM hire_edges
            """
        )

        def payments_builder(c: duckdb.DuckDBPyConnection, a: int, b: int) -> None:
            c.execute(
                f"""
                CREATE OR REPLACE TEMP TABLE payments AS
                SELECT ap.payee, o.buyer AS payer, o.budget_raw AS val, o.created_block AS block, -1 AS txi, -1 AS li, 'termix-order' AS via
                FROM t_orders o JOIN t_agent_payee ap USING (agent_hex)
                WHERE o.created_block BETWEEN {a} AND {b} AND ap.payee IN (SELECT payee FROM payees)
                """
            )

        bounds = eb.extract_window(con, f"T{args.window}", pick, 1000, 4, payments_builder=payments_builder)
        for p in pick:
            case = Case(case_id=f"MARKET-termix-base|{p}|{args.window}", family="MARKET-termix-base", chain="base", market="termix-base",
                        label="market", y=-1, payee=p, window=args.window, half="market")
            eb.write_case(con, case, p, out, bounds, 1000, 4)
    finally:
        con.execute("DROP VIEW IF EXISTS tr")
        con.execute("ALTER TABLE tr_usdc RENAME TO tr")


if __name__ == "__main__":
    main()
