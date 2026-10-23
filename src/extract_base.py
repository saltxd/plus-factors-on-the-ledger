"""Build the per-case evidence tables for the Base (x402) cases from the raw USDC pull.

Runs next to the raw pull (DuckDB, a few GB of disk). For every Base case it writes
data/cases/<case dir>/ with payments, payer_inflows, seller_outflows, payer_reach (csv.gz)
and meta.json, the inputs of src/features.py.

Definitions used here (see README "Method"):
  payment       a USDC transfer into the payee inside the window that the payer authorised with
                EIP-3009 (AuthorizationUsed by the sender in the same transaction), or a transfer
                into the payee from a contract that, earlier in the same transaction, received at
                least that amount from an EIP-3009 authoriser (a facilitator proxy); the authoriser
                is the payer.
  data range    lookback (14 days before the window) + window.
  hub           an address with at least H distinct counterparties (non-zero USDC transfers, either
                direction) in the data range.
  forwarding    a transfer X -> Z that follows, in the same transaction, a transfer Y -> X with
                0.5 * (Y -> X) <= (X -> Z) <= (Y -> X). X is passed through (facilitator proxies,
                routers); the money is treated as going from Y to Z.
  reach set     wallets reachable from the payee through non-hub wallets in at most K transfers in
                the data range, passing through forwarders.
  resolved src  the sender of an inflow, or, when the inflow is a forwarded leg, the wallet that
                paid the forwarder.

Usage (on the node):
  python src/extract_base.py --db base.duckdb --raw data/base --load
  python src/extract_base.py --db base.duckdb --out data/cases --hub 1000 --k 4
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import duckdb

from cases import LOOKBACK_DAYS, base_block_at, base_ts, expand, load_registry, window_bounds

log = logging.getLogger("extract_base")
CAP_VISITED = 200_000


def load(con: duckdb.DuckDBPyConnection, raw: Path) -> None:
    t = time.time()
    # files are named by start block, so reading them in glob order keeps the table in block
    # order, which lets DuckDB skip row groups on block-range filters
    con.execute("SET preserve_insertion_order=true")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE tr AS
        SELECT * FROM read_csv('{raw}/transfers_*.tsv.gz', delim='\t', header=false,
            columns={{'block':'INTEGER','txi':'INTEGER','li':'INTEGER','src':'VARCHAR','dst':'VARCHAR','val':'HUGEINT'}})
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE auth AS
        SELECT * FROM read_csv('{raw}/auth_*.tsv.gz', delim='\t', header=false,
            columns={{'block':'INTEGER','txi':'INTEGER','li':'INTEGER','authorizer':'VARCHAR','nonce':'VARCHAR'}})
        """
    )
    n = con.execute("SELECT count(*), min(block), max(block), count(DISTINCT block) FROM tr").fetchone()
    a = con.execute("SELECT count(*) FROM auth").fetchone()
    log.info("loaded tr=%s auth=%s in %.0fs", n, a, time.time() - t)


def build_hubs(con: duckdb.DuckDBPyConnection, w: str, d0: int, d1: int) -> None:
    t = time.time()
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS deg_{w} AS
        WITH pairs AS (
            SELECT DISTINCT src, dst FROM tr WHERE block BETWEEN {d0} AND {d1} AND val > 0 AND src != dst
        ), e AS (
            SELECT src AS a, dst AS c FROM pairs UNION SELECT dst AS a, src AS c FROM pairs
        )
        SELECT a, count(*) AS d FROM e GROUP BY a HAVING count(*) >= 300
        """
    )
    n = con.execute(f"SELECT count(*) FROM deg_{w}").fetchone()[0]
    log.info("deg_%s: %d addresses with >=300 counterparties (%.0fs)", w, n, time.time() - t)


def resolve_prefix(con: duckdb.DuckDBPyConnection, prefix: str, w0: int, w1: int) -> str:
    rows = con.execute(
        f"""
        SELECT DISTINCT t.dst FROM tr t JOIN auth a ON a.block = t.block AND a.txi = t.txi AND a.authorizer = t.src
        WHERE t.block BETWEEN {w0} AND {w1} AND t.dst LIKE '{prefix.lower()}%'
        """
    ).fetchall()
    if len(rows) != 1:
        raise SystemExit(f"prefix {prefix} resolves to {len(rows)} payees in blocks {w0}-{w1}: {rows}")
    return rows[0][0]


def extract_window(con: duckdb.DuckDBPyConnection, w: str, payees: list[str], hub: int, k: int, override: dict | None = None,
                   payments_builder=None) -> dict:
    """payments_builder(con, w0, w1), when given, creates TEMP TABLE payments(payee, payer, val, block,
    txi, li, via) itself (used for markets whose payments are not EIP-3009 transfers)."""
    if override:
        t0, t1, w0, w1, d0, d1 = (override[x] for x in ("t0", "t1", "w0", "w1", "d0", "d1"))
    else:
        reg = load_registry()
        t0, t1, w0, w1 = window_bounds(reg, w)
        d0 = base_block_at(t0 - LOOKBACK_DAYS * 86400)
        d1 = w1
    build_hubs(con, w, d0, d1)
    con.execute(f"CREATE OR REPLACE TEMP TABLE hubs AS SELECT a FROM deg_{w} WHERE d >= {hub}")
    con.execute("CREATE OR REPLACE TEMP TABLE payees AS SELECT unnest(?) AS payee", [payees])

    # ---- payments
    t = time.time()
    if payments_builder is not None:
        payments_builder(con, w0, w1)
    else:
        _x402_payments(con, w0, w1)
    con.execute("DELETE FROM payments WHERE payer = payee")
    npay = con.execute("SELECT payee, count(*), sum(val)/1e6, count(DISTINCT payer) FROM payments GROUP BY payee").fetchall()
    log.info("%s payments (%.0fs): %d payees", w, time.time() - t, len(npay))
    if len(npay) <= 60:
        log.info("%s payments: %s", w, npay)
    return _reach_and_flows(con, w, k, t0, t1, w0, w1, d0, d1)


def _x402_payments(con: duckdb.DuckDBPyConnection, w0: int, w1: int) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE cand AS
        SELECT t.* FROM tr t WHERE t.block BETWEEN {w0} AND {w1} AND t.val > 0
          AND t.dst IN (SELECT payee FROM payees) AND t.src != t.dst
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE pay_direct AS
        SELECT DISTINCT c.dst AS payee, c.src AS payer, c.val, c.block, c.txi, c.li, 'direct' AS via
        FROM cand c JOIN auth a ON a.block = c.block AND a.txi = c.txi AND a.authorizer = c.src
        WHERE a.block BETWEEN {w0} AND {w1}
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE pay_pass AS
        SELECT c.dst AS payee, arg_max(t1.src, t1.li) AS payer, c.val, c.block, c.txi, c.li, 'passthrough' AS via
        FROM cand c
        JOIN tr t1 ON t1.block = c.block AND t1.txi = c.txi AND t1.dst = c.src AND t1.li < c.li
            AND t1.val >= c.val AND c.val * 2 >= t1.val
        JOIN auth a ON a.block = t1.block AND a.txi = t1.txi AND a.authorizer = t1.src
        WHERE t1.block BETWEEN {w0} AND {w1} AND a.block BETWEEN {w0} AND {w1}
          AND NOT EXISTS (SELECT 1 FROM pay_direct d WHERE d.block = c.block AND d.li = c.li)
        GROUP BY c.dst, c.val, c.block, c.txi, c.li
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE payments AS
        SELECT * FROM pay_direct UNION ALL SELECT * FROM pay_pass
        """
    )


def _reach_and_flows(con: duckdb.DuckDBPyConnection, w: str, k: int, t0: int, t1: int, w0: int, w1: int, d0: int, d1: int) -> dict:
    # ---- forward reach from each payee (batched BFS)
    t = time.time()
    con.execute("CREATE OR REPLACE TEMP TABLE visited AS SELECT payee AS ck, payee AS node, 0 AS hop FROM payees")
    con.execute("CREATE OR REPLACE TEMP TABLE frontier AS SELECT ck, node FROM visited")
    con.execute("CREATE OR REPLACE TEMP TABLE capped (ck VARCHAR)")
    for hop in range(1, k + 1):
        # transfers out of the frontier; a transfer that its recipient forwards within the same
        # transaction (50-100% of the amount, later in the log order) counts as a transfer to the
        # final recipient, so facilitator proxies and routers are passed through, not visited
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE e1 AS
            SELECT f.ck, f.node AS u, t.block, t.txi, t.li, t.dst AS x, t.val
            FROM frontier f JOIN tr t ON t.src = f.node
            WHERE t.block BETWEEN {d0} AND {d1} AND t.val > 0
            """
        )
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE fwd AS
            SELECT e1.ck, e1.u, e1.block, e1.li, t2.dst AS z
            FROM e1 JOIN tr t2 ON t2.block = e1.block AND t2.txi = e1.txi AND t2.src = e1.x AND t2.li > e1.li
            WHERE t2.block BETWEEN {d0} AND {d1} AND t2.val > 0 AND t2.val <= e1.val AND t2.val * 2 >= e1.val
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE nxt AS
            SELECT DISTINCT e1.ck, e1.x AS node FROM e1
            WHERE e1.x NOT IN (SELECT a FROM hubs)
              AND NOT EXISTS (SELECT 1 FROM fwd WHERE fwd.ck = e1.ck AND fwd.block = e1.block AND fwd.li = e1.li)
            UNION
            SELECT DISTINCT fwd.ck, fwd.z AS node FROM fwd
            WHERE fwd.z NOT IN (SELECT a FROM hubs) AND fwd.z != fwd.u
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE newn AS
            SELECT n.ck, n.node FROM nxt n
            WHERE NOT EXISTS (SELECT 1 FROM visited v WHERE v.ck = n.ck AND v.node = n.node)
              AND n.ck NOT IN (SELECT ck FROM capped)
            """
        )
        con.execute(f"INSERT INTO visited SELECT ck, node, {hop} FROM newn")
        con.execute(
            f"INSERT INTO capped SELECT ck FROM visited GROUP BY ck HAVING count(*) > {CAP_VISITED} EXCEPT SELECT ck FROM capped"
        )
        con.execute("CREATE OR REPLACE TEMP TABLE frontier AS SELECT ck, node FROM newn WHERE ck NOT IN (SELECT ck FROM capped)")
        sizes = con.execute("SELECT count(*) FROM newn").fetchone()[0]
        log.info("%s hop %d: %d new nodes (%.0fs)", w, hop, sizes, time.time() - t)

    # ---- payer inflows with same-transaction resolution through hubs
    t = time.time()
    con.execute("CREATE OR REPLACE TEMP TABLE case_payers AS SELECT DISTINCT payee AS ck, payer FROM payments")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE pin AS
        SELECT cp.ck, t.dst AS payer, t.src AS raw_src, t.val, t.block, t.txi, t.li
        FROM case_payers cp JOIN tr t ON t.dst = cp.payer
        WHERE t.block BETWEEN {d0} AND {d1} AND t.val > 0 AND t.src != t.dst
        """
    )
    # an inflow forwarded by an intermediary in the same transaction is credited to whoever paid
    # the intermediary (same 50-100% rule as the reach walk)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE pin_via AS
        SELECT p.ck, p.payer, p.block, p.li, arg_max(t1.src, t1.li) AS via_src
        FROM pin p JOIN tr t1 ON t1.block = p.block AND t1.txi = p.txi AND t1.dst = p.raw_src AND t1.li < p.li
        WHERE t1.block BETWEEN {d0} AND {d1}
          AND t1.val >= p.val AND p.val * 2 >= t1.val AND t1.src != p.payer
        GROUP BY p.ck, p.payer, p.block, p.li
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE pin_res AS
        SELECT p.ck, p.payer, p.raw_src, coalesce(v.via_src, p.raw_src) AS src, p.val, p.block, p.txi, p.li
        FROM pin p LEFT JOIN pin_via v ON v.ck = p.ck AND v.payer = p.payer AND v.block = p.block AND v.li = p.li
        """
    )
    log.info("%s payer inflows: %d rows (%.0fs)", w, con.execute("SELECT count(*) FROM pin_res").fetchone()[0], time.time() - t)

    # ---- seller outflows
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE sout AS
        SELECT p.payee AS ck, t.dst, t.val, t.block, t.txi, t.li, (t.dst IN (SELECT a FROM hubs)) AS dst_is_hub
        FROM payees p JOIN tr t ON t.src = p.payee
        WHERE t.block BETWEEN {d0} AND {d1} AND t.val > 0
        """
    )
    return {"t0": t0, "t1": t1, "w0": w0, "w1": w1, "d0": d0, "d1": d1}


def write_case(con: duckdb.DuckDBPyConnection, case, payee: str, out: Path, bounds: dict, hub: int, k: int) -> dict:
    d = out / case.case_id.replace("|", "__")
    d.mkdir(parents=True, exist_ok=True)
    ts = f"({base_ts(0)} + 2 * block)"  # base_ts(0) + 2*block == base timestamp
    pay = con.execute(
        f"SELECT payer, val/1e6 AS value, {ts} AS ts, block, txi, li, via FROM payments WHERE payee = ? ORDER BY block, li", [payee]
    ).df()
    if pay.empty:
        return {"case_id": case.case_id, "payee": payee, "dropped": "no payments in window"}
    reach = con.execute(
        "SELECT cp.payer, min(v.hop) AS hops FROM case_payers cp LEFT JOIN visited v ON v.ck = cp.ck AND v.node = cp.payer "
        "WHERE cp.ck = ? GROUP BY cp.payer ORDER BY cp.payer",
        [payee],
    ).df()
    inflows = con.execute(
        f"""
        SELECT r.payer, r.src, r.raw_src, r.val/1e6 AS value, {ts.replace('block', 'r.block')} AS ts,
               r.block::BIGINT * 1000000 + r.li AS "order", r.block, r.txi, r.li,
               coalesce((SELECT min(v.hop) FROM visited v WHERE v.ck = r.ck AND v.node = r.src), -1) AS src_hops,
               (r.src IN (SELECT payer FROM case_payers c WHERE c.ck = r.ck))::INT AS src_is_payer,
               (r.src IN (SELECT a FROM hubs))::INT AS src_is_hub,
               (r.src = r.ck)::INT AS src_is_seller
        FROM pin_res r WHERE r.ck = ? ORDER BY r.block, r.li
        """,
        [payee],
    ).df()
    outflows = con.execute(
        f"SELECT dst, val/1e6 AS value, {ts} AS ts, block, txi, li, dst_is_hub::INT AS dst_is_hub FROM sout WHERE ck = ? ORDER BY block, li",
        [payee],
    ).df()
    pay.to_csv(d / "payments.csv.gz", index=False)
    reach.to_csv(d / "payer_reach.csv.gz", index=False)
    inflows.to_csv(d / "payer_inflows.csv.gz", index=False)
    outflows.to_csv(d / "seller_outflows.csv.gz", index=False)
    vsize = con.execute("SELECT hop, count(*) FROM visited WHERE ck = ? GROUP BY hop ORDER BY hop", [payee]).fetchall()
    capped = con.execute("SELECT count(*) FROM capped WHERE ck = ?", [payee]).fetchone()[0] > 0
    meta = {
        "case_id": case.case_id,
        "family": case.family,
        "label": case.label,
        "y": case.y,
        "half": case.half,
        "payee": payee,
        "window": case.window,
        "chain": "base",
        "market": case.market,
        "contested": case.contested,
        "t0": bounds["t0"],
        "t1": bounds["t1"],
        "window_blocks": [bounds["w0"], bounds["w1"]],
        "data_blocks": [bounds["d0"], bounds["d1"]],
        "hub_threshold": hub,
        "k": k,
        "reach_by_hop": vsize,
        "reach_capped": bool(capped),
        "n_payments": int(len(pay)),
        "n_payers": int(pay["payer"].nunique()),
        "volume": float(pay["value"].sum()),
        "via_counts": pay["via"].value_counts().to_dict(),
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--raw")
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--out", default="data/cases")
    ap.add_argument("--hub", type=int, default=1000)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--windows", nargs="*", default=["W1", "W2", "W3", "W4"])
    ap.add_argument("--memory", default="6GB")
    ap.add_argument("--threads", type=int, default=6)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    con = duckdb.connect(args.db)
    con.execute(f"SET memory_limit='{args.memory}'; SET threads={args.threads}; SET preserve_insertion_order=false")
    if args.load:
        load(con, Path(args.raw))
        return
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    cases = [c for c in expand(reg) if c.chain == "base"]
    summary = []
    for w in args.windows:
        wc = [c for c in cases if c.window == w]
        if not wc:
            continue
        _, _, w0, w1 = window_bounds(reg, w)
        resolved = {}
        for c in wc:
            resolved[c.case_id] = resolve_prefix(con, c.payee.split(":", 1)[1], w0, w1) if c.payee.startswith("prefix:") else c.payee
            if c.payee.startswith("prefix:"):
                log.info("resolved %s -> %s", c.payee, resolved[c.case_id])
        bounds = extract_window(con, w, sorted(set(resolved.values())), args.hub, args.k)
        for c in wc:
            m = write_case(con, c, resolved[c.case_id], out, bounds, args.hub, args.k)
            summary.append(m)
            log.info("case %s: %s", c.case_id, {k_: m.get(k_) for k_ in ("n_payments", "n_payers", "volume", "dropped")})
    (out / f"extract_base_summary_h{args.hub}_k{args.k}.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
