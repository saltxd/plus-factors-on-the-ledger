"""Transaction senders for every Base transaction that consumed a USDC EIP-3009 authorisation.

The raw pull holds logs only, and an x402 settlement is identified by who sent the transaction
(a facilitator address). For each distinct (block, transaction index) with an AuthorizationUsed
log in the block range, this reads eth_getTransactionByBlockNumberAndIndex and writes
data/raw/base_senders/senders_<first>_<last>.tsv.gz with block, txi, from, to.

Against ChainWard's own node it runs unpaced; against a keyless public endpoint use --rps 2 --batch 5.
Over an SSH tunnel the node answers about 300 transactions a second, on the node itself about
10,000, so the pairs can be exported first and the script run on the node (standard library only):

  python pull/base_tx_senders.py --export-pairs --start 51320527 --end 51622926       # writes pairs_<first>_<last>.txt.gz
  python3 base_tx_senders.py --pairs pairs_51320527_51622926.txt.gz --rpc http://localhost:8545 --out .   # on the node
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("base_tx_senders")


def rpc_batch(url: str, pairs: list[tuple[int, int]], retries: int = 5) -> list[tuple[int, int, str | None, str | None]]:
    body = json.dumps([
        {"jsonrpc": "2.0", "id": i, "method": "eth_getTransactionByBlockNumberAndIndex", "params": [hex(b), hex(x)]}
        for i, (b, x) in enumerate(pairs)
    ]).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=120).read())
            by_id = {r["id"]: r.get("result") for r in res}
            if len(by_id) != len(pairs):
                raise ValueError(f"{len(by_id)} answers for {len(pairs)} requests")
            out = []
            for i, (b, x) in enumerate(pairs):
                tx = by_id[i]
                out.append((b, x, tx["from"].lower() if tx else None, (tx.get("to") or "").lower() if tx else None))
            return out
        except Exception as e:  # noqa: BLE001 - retried, then raised
            log.warning("batch at block %d failed (%s), retry %d", pairs[0][0], e, attempt + 1)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"batch at block {pairs[0][0]} failed {retries} times")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "base.duckdb"))
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--batch", type=int, default=250)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--rps", type=float, default=0.0, help="requests per second per worker (0 = unpaced)")
    ap.add_argument("--out", default=str(ROOT / "data" / "raw" / "base_senders"))
    ap.add_argument("--pairs", help="gzipped 'block txi' lines instead of reading the DuckDB file")
    ap.add_argument("--export-pairs", action="store_true", help="only write the pairs file and stop")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"senders_{args.start}_{args.end}.tsv.gz"
    if path.exists():
        log.info("%s exists, skipping", path)
        return
    if args.pairs:
        with gzip.open(args.pairs, "rt") as f:
            pairs = [tuple(int(v) for v in line.split()) for line in f if line.strip()]
    else:
        import duckdb

        con = duckdb.connect(args.db, read_only=True)
        pairs = con.execute(
            f"SELECT DISTINCT block, txi FROM auth WHERE block BETWEEN {args.start} AND {args.end} ORDER BY block, txi"
        ).fetchall()
        con.close()
    if args.export_pairs:
        pp = out / f"pairs_{args.start}_{args.end}.txt.gz"
        with gzip.open(pp, "wt") as f:
            f.writelines(f"{b} {x}\n" for b, x in pairs)
        log.info("wrote %s (%d pairs)", pp, len(pairs))
        return
    log.info("%d transactions with an AuthorizationUsed log in %d..%d", len(pairs), args.start, args.end)
    chunks = [pairs[i : i + args.batch] for i in range(0, len(pairs), args.batch)]
    t0, done, missing = time.time(), 0, 0
    tmp = path.with_suffix(".part")

    def run(chunk: list[tuple[int, int]]) -> list:
        if args.rps > 0:
            time.sleep(1.0 / args.rps)
        return rpc_batch(args.rpc, chunk)

    with gzip.open(tmp, "wt") as f, ThreadPoolExecutor(args.workers) as ex:
        for rows in ex.map(run, chunks):
            for b, x, frm, to in rows:
                missing += frm is None
                f.write(f"{b}\t{x}\t{frm or ''}\t{to or ''}\n")
            done += len(rows)
            if done % 100_000 < args.batch:
                log.info("%d / %d (%.0f/s), %d missing", done, len(pairs), done / (time.time() - t0), missing)
    tmp.rename(path)
    log.info("wrote %s: %d transactions, %d missing, %.0fs", path, done, missing, time.time() - t0)


if __name__ == "__main__":
    main()
