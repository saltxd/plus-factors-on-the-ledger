"""Read-only tools for the spot-check judges (cases/spotcheck_judge_protocol.md).

Every query reads data/base.duckdb (opened read-only): every USDC transfer on Base from
2026-09-01 00:00 to 2026-10-12 23:59:59 UTC (table tr: block, txi, li, src, dst, val in
micro-USDC, so 1 USDC = 1,000,000) and every EIP-3009 AuthorizationUsed log (table auth: block,
txi, li, authorizer, nonce). Base blocks are 2 seconds apart; block 50,715,727 is
2026-09-01 00:00:01 UTC. Nothing here computes or prints any feature, flag or rule.

  python scripts/spotcheck_tools.py window W2
  python scripts/spotcheck_tools.py dossier <payee> <window>
  python scripts/spotcheck_tools.py inflows <address> <window> [--top 15]
  python scripts/spotcheck_tools.py outflows <address> <window> [--top 15]
  python scripts/spotcheck_tools.py degree <address> [<address> ...] --window <window>
  python scripts/spotcheck_tools.py paid <payer> <window>
  python scripts/spotcheck_tools.py between <address_a> <address_b> <window>
  python scripts/spotcheck_tools.py sql "<read-only query>"

"Data range" is the 14 days before the window plus the window. A payment is a USDC transfer into
the payee inside the window that the payer authorised with EIP-3009, directly or through a
contract that forwards it in the same transaction (the payer is then the authoriser).
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REF_BLOCK, REF_TS = 50715727, 1788220801
WINDOWS = {
    "W1": ("2026-09-15", "2026-09-22", 51320527, 51622926),
    "W2": ("2026-09-22", "2026-09-29", 51622927, 51925326),
    "W3": ("2026-09-29", "2026-10-06", 51925327, 52227726),
    "W4": ("2026-10-06", "2026-10-13", 52227727, 52530126),
}
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 44)


def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(str(ROOT / "data" / "base.duckdb"), read_only=True)
    c.execute("SET threads=4; SET memory_limit='3GB'")
    return c


def bounds(w: str) -> tuple[int, int, int]:
    """(first block of the data range, first block of the window, last block of the window)."""
    _, _, w0, w1 = WINDOWS[w]
    return max(REF_BLOCK, w0 - 14 * 86400 // 2), w0, w1


def when(block: int) -> str:
    return dt.datetime.fromtimestamp(REF_TS + 2 * (int(block) - REF_BLOCK), dt.timezone.utc).strftime("%m-%d %H:%M")


def short(a: str) -> str:
    return a[:10] if isinstance(a, str) and a.startswith("0x") else str(a)


def payments(c: duckdb.DuckDBPyConnection, payee: str, w0: int, w1: int) -> pd.DataFrame:
    payee = payee.lower()
    return c.execute(
        f"""
        WITH cand AS (SELECT * FROM tr WHERE block BETWEEN {w0} AND {w1} AND dst = ? AND val > 0 AND src != dst),
        direct AS (
            SELECT DISTINCT c.src AS payer, c.val, c.block, c.txi, c.li FROM cand c
            JOIN auth a ON a.block = c.block AND a.txi = c.txi AND a.authorizer = c.src WHERE a.block BETWEEN {w0} AND {w1}
        ),
        pass AS (
            SELECT arg_max(t1.src, t1.li) AS payer, c.val, c.block, c.txi, c.li FROM cand c
            JOIN tr t1 ON t1.block = c.block AND t1.txi = c.txi AND t1.dst = c.src AND t1.li < c.li AND t1.val >= c.val AND c.val * 2 >= t1.val
            JOIN auth a ON a.block = t1.block AND a.txi = t1.txi AND a.authorizer = t1.src
            WHERE t1.block BETWEEN {w0} AND {w1} AND a.block BETWEEN {w0} AND {w1}
              AND NOT EXISTS (SELECT 1 FROM direct d WHERE d.block = c.block AND d.li = c.li)
            GROUP BY c.val, c.block, c.txi, c.li
        )
        SELECT payer, val / 1e6 AS usdc, block, txi, li FROM (SELECT * FROM direct UNION ALL SELECT * FROM pass) WHERE payer != ?
        ORDER BY block, li
        """,
        [payee, payee],
    ).df()


def degrees(c: duckdb.DuckDBPyConnection, addrs: list[str], d0: int, w1: int) -> dict[str, int]:
    """Distinct counterparties (non-zero transfers, either direction) in the data range."""
    if not addrs:
        return {}
    c.execute("CREATE OR REPLACE TEMP TABLE q AS SELECT unnest(?) AS a", [sorted(set(a.lower() for a in addrs))])
    rows = c.execute(
        f"""
        WITH e AS (
            SELECT t.src AS a, t.dst AS o FROM tr t SEMI JOIN q ON q.a = t.src WHERE t.block BETWEEN {d0} AND {w1} AND t.val > 0 AND t.src != t.dst
            UNION
            SELECT t.dst AS a, t.src AS o FROM tr t SEMI JOIN q ON q.a = t.dst WHERE t.block BETWEEN {d0} AND {w1} AND t.val > 0 AND t.src != t.dst
        )
        SELECT a, count(DISTINCT o) FROM e GROUP BY a
        """
    ).fetchall()
    return {a: int(n) for a, n in rows}


def flows(c: duckdb.DuckDBPyConnection, addrs: list[str], d0: int, w1: int, direction: str) -> pd.DataFrame:
    """Transfers into (direction='in') or out of ('out') each address in the data range, grouped by counterparty."""
    c.execute("CREATE OR REPLACE TEMP TABLE q AS SELECT unnest(?) AS a", [sorted(set(a.lower() for a in addrs))])
    me, other = ("dst", "src") if direction == "in" else ("src", "dst")
    return c.execute(
        f"""
        SELECT t.{me} AS addr, t.{other} AS counterparty, sum(t.val) / 1e6 AS usdc, count(*) AS n, min(t.block) AS first_block, max(t.block) AS last_block
        FROM tr t SEMI JOIN q ON q.a = t.{me}
        WHERE t.block BETWEEN {d0} AND {w1} AND t.val > 0 AND t.src != t.dst
        GROUP BY 1, 2 ORDER BY addr, usdc DESC
        """
    ).df()


def cmd_dossier(payee: str, w: str, top: int) -> None:
    payee = payee.lower()
    c = con()
    d0, w0, w1 = bounds(w)
    print(f"payee {payee}, window {w} ({WINDOWS[w][0]} to {WINDOWS[w][1]} UTC, blocks {w0:,}-{w1:,}); data range from block {d0:,} ({when(d0)})")
    pay = payments(c, payee, w0, w1)
    if pay.empty:
        print("no payments in the window")
        return
    by = pay.groupby("payer").agg(usdc=("usdc", "sum"), n=("usdc", "size"), first=("block", "min"), last=("block", "max")).sort_values("usdc", ascending=False)
    tot = by["usdc"].sum()
    print(f"\n1. PAYMENTS: {len(pay):,} payments, {tot:,.4f} USDC, from {len(by):,} payers; amounts min {pay.usdc.min():.4g}, median {pay.usdc.median():.4g}, max {pay.usdc.max():.4g}; "
          f"{pay['block'].map(lambda b: when(b)[:5]).nunique()} active days")
    tp = by.head(top).copy()
    tp["share"] = tp["usdc"] / tot
    payers = list(by.index)
    # other payees each top payer paid by EIP-3009 in the window
    c.execute("CREATE OR REPLACE TEMP TABLE tpq AS SELECT unnest(?) AS a", [list(tp.index)])
    other = c.execute(
        f"""
        SELECT t.src AS payer, t.dst AS paid, sum(t.val)/1e6 AS usdc FROM tr t SEMI JOIN tpq ON tpq.a = t.src
        JOIN auth a ON a.block = t.block AND a.txi = t.txi AND a.authorizer = t.src
        WHERE t.block BETWEEN {w0} AND {w1} AND a.block BETWEEN {w0} AND {w1} AND t.val > 0 AND t.dst != ? AND t.src != t.dst
        GROUP BY 1, 2
        """,
        [payee],
    ).df()
    inf = flows(c, list(tp.index), d0, w1, "in")
    outf = flows(c, list(tp.index), d0, w1, "out")
    src_deg = degrees(c, list(inf.groupby("addr").head(3)["counterparty"]), d0, w1)
    pset = set(payers)
    print(f"\n2. TOP {len(tp)} PAYERS (of {len(by)}; together {tp['share'].sum():.1%} of the value)")
    for p, r in tp.iterrows():
        o = other[other["payer"] == p].sort_values("usdc", ascending=False)
        print(f"\n  payer {p}: {r['usdc']:,.4f} USDC ({r['share']:.1%}) in {int(r['n'])} payments, {when(r['first'])} to {when(r['last'])}")
        print(f"    also paid by EIP-3009 in the window: {len(o)} other payees"
              + (", top: " + ", ".join(f"{short(x)} {v:,.2f}" for x, v in zip(o['paid'][:3], o['usdc'][:3])) if len(o) else ""))
        i = inf[inf["addr"] == p]
        print(f"    USDC into it in the data range: {i['usdc'].sum():,.4f} from {len(i)} sources")
        for _, s in i.head(3).iterrows():
            tag = " <- THE PAYEE" if s["counterparty"] == payee else (" (another payer of this payee)" if s["counterparty"] in pset else "")
            print(f"      from {s['counterparty']}: {s['usdc']:,.4f} in {int(s['n'])} transfers ({when(s['first_block'])} to {when(s['last_block'])}), "
                  f"source has {src_deg.get(s['counterparty'], 0):,} counterparties{tag}")
        first = c.execute(f"SELECT src, val/1e6, block FROM tr WHERE dst = ? AND val > 0 AND block BETWEEN {REF_BLOCK} AND {w1} ORDER BY block, li LIMIT 1", [p]).fetchone()
        if first:
            print(f"    first USDC it received in the data (from Sep 1): {first[1]:,.4f} from {first[0]} at {when(first[2])}")
        oo = outf[(outf["addr"] == p) & (outf["counterparty"] != payee)]
        print(f"    USDC out of it to others than the payee in the data range: {oo['usdc'].sum():,.4f} to {len(oo)} addresses"
              + (", top: " + ", ".join(f"{short(x)} {v:,.2f}" for x, v in zip(oo['counterparty'][:3], oo['usdc'][:3])) if len(oo) else ""))
    # the payee's own outflows and their next hop
    so = flows(c, [payee], d0, w1, "out")
    print(f"\n3. PAYEE'S OUTFLOWS in the data range: {so['usdc'].sum():,.4f} USDC to {len(so)} addresses")
    if len(so):
        top_dst = so.head(top)
        dd = degrees(c, list(top_dst["counterparty"]), d0, w1)
        nxt = flows(c, list(top_dst["counterparty"]), d0, w1, "out")
        for _, r in top_dst.iterrows():
            tag = " (A PAYER of this payee)" if r["counterparty"] in pset else ""
            print(f"  to {r['counterparty']}: {r['usdc']:,.4f} in {int(r['n'])} transfers ({when(r['first_block'])} to {when(r['last_block'])}), "
                  f"{dd.get(r['counterparty'], 0):,} counterparties{tag}")
            n2 = nxt[nxt["addr"] == r["counterparty"]]
            npay = n2[n2["counterparty"].isin(pset)]
            print(f"     it sent on {n2['usdc'].sum():,.4f} to {len(n2)} addresses, of which {len(npay)} are payers of this payee ({npay['usdc'].sum():,.4f})"
                  + (", top: " + ", ".join(f"{short(x)} {v:,.2f}" for x, v in zip(n2['counterparty'][:3], n2['usdc'][:3])) if len(n2) else ""))
    si = flows(c, [payee], d0, w1, "in")
    pay_keys = set(pay["payer"])
    si_other = si[~si["counterparty"].isin(pay_keys)]
    print(f"\n4. PAYEE'S OTHER INFLOWS (from addresses that are not its payers this week) in the data range: {si_other['usdc'].sum():,.4f} USDC from {len(si_other)} addresses"
          + (", top: " + ", ".join(f"{short(x)} {v:,.2f}" for x, v in zip(si_other['counterparty'][:5], si_other['usdc'][:5])) if len(si_other) else ""))


def cmd_flows(addr: str, w: str, top: int, direction: str) -> None:
    c = con()
    d0, _, w1 = bounds(w)
    f = flows(c, [addr], d0, w1, direction).head(top)
    deg = degrees(c, list(f["counterparty"]), d0, w1)
    f["counterparty_degree"] = f["counterparty"].map(deg)
    f["first"] = f["first_block"].map(when)
    f["last"] = f["last_block"].map(when)
    print(f"USDC {'into' if direction == 'in' else 'out of'} {addr.lower()} in the data range of {w} (blocks {d0:,}-{w1:,}), top {top} counterparties")
    print(f[["counterparty", "usdc", "n", "first", "last", "counterparty_degree"]].to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("window"); s.add_argument("window")
    s = sub.add_parser("dossier"); s.add_argument("payee"); s.add_argument("window"); s.add_argument("--top", type=int, default=10)
    for name in ("inflows", "outflows"):
        s = sub.add_parser(name); s.add_argument("address"); s.add_argument("window"); s.add_argument("--top", type=int, default=15)
    s = sub.add_parser("degree"); s.add_argument("addresses", nargs="+"); s.add_argument("--window", required=True)
    s = sub.add_parser("paid"); s.add_argument("payer"); s.add_argument("window")
    s = sub.add_parser("between"); s.add_argument("a"); s.add_argument("b"); s.add_argument("window")
    s = sub.add_parser("sql"); s.add_argument("query")
    a = ap.parse_args()
    if a.cmd == "window":
        d0, w0, w1 = bounds(a.window)
        print(f"{a.window}: {WINDOWS[a.window][0]} 00:00 to {WINDOWS[a.window][1]} 00:00 UTC, blocks {w0:,}-{w1:,}; data range starts at block {d0:,} ({when(d0)})")
    elif a.cmd == "dossier":
        cmd_dossier(a.payee, a.window, a.top)
    elif a.cmd in ("inflows", "outflows"):
        cmd_flows(a.address, a.window, a.top, "in" if a.cmd == "inflows" else "out")
    elif a.cmd == "degree":
        d0, _, w1 = bounds(a.window)
        for k, v in sorted(degrees(con(), a.addresses, d0, w1).items()):
            print(k, v)
    elif a.cmd == "paid":
        c = con()
        _, w0, w1 = bounds(a.window)
        df = c.execute(
            f"""
            SELECT t.dst AS payee, sum(t.val)/1e6 AS usdc, count(*) AS n FROM tr t
            JOIN auth au ON au.block = t.block AND au.txi = t.txi AND au.authorizer = t.src
            WHERE t.block BETWEEN {w0} AND {w1} AND au.block BETWEEN {w0} AND {w1} AND t.src = ? AND t.val > 0 AND t.src != t.dst
            GROUP BY 1 ORDER BY usdc DESC
            """,
            [a.payer.lower()],
        ).df()
        print(f"EIP-3009 transfers authorised by {a.payer.lower()} in {a.window} (direct recipients; a facilitator proxy may forward them on)")
        print(df.to_string(index=False))
    elif a.cmd == "between":
        c = con()
        d0, _, w1 = bounds(a.window)
        x, y = a.a.lower(), a.b.lower()
        df = c.execute(
            f"SELECT block, src, dst, val/1e6 AS usdc FROM tr WHERE block BETWEEN {d0} AND {w1} AND ((src = ? AND dst = ?) OR (src = ? AND dst = ?)) ORDER BY block, li",
            [x, y, y, x],
        ).df()
        df["time"] = df["block"].map(when)
        print(df.to_string(index=False) if len(df) else "no transfers between them in the data range")
    elif a.cmd == "sql":
        q = a.query.strip().rstrip(";")
        if not q.lower().startswith(("select", "with")):
            raise SystemExit("read-only SELECT / WITH queries only")
        print(con().execute(q).df().to_string(index=False))


if __name__ == "__main__":
    main()
