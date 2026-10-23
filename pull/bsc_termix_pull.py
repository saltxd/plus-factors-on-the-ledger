"""Pull TermiX escrow activity and stablecoin transfers on BNB Chain (BSC) from a
keyless public RPC, paced to at most --max-rps requests per second.

Written for the Apart AI Collusion Research Sprint (Oct 23-25, 2026).

Subcommands
  blocks     find the first block at or after each UTC timestamp given (binary search)
  anchors    block timestamps every --seg blocks (for interpolation)
  escrow     every log of TermiX's two BSC escrows
  escrowout  every USDC/USDT transfer out of the two escrows (payouts, fees, refunds)
  transfers  every USDC/USDT transfer into or out of the wallets listed in --wallets
  accounts   nonce and code size of the addresses listed in --wallets, at --block
  owners     ERC-8004 ownerOf(agentId) for the ids in --ids, at --block (batches of 5)
  receipts   all logs of the transactions in --txs (validation sample)

Output is tab-separated, one gzip file per pulled chunk range, resumable.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USDC_BSC = "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d"
USDT_BSC = "0x55d398326f99059ff775485246999027b3197955"
ESCROW_USDC = "0x6a52ba4c84b348faeae13ddc7a97b4f6af23913c"
ESCROW_USDT = "0xce02f987d8b8af694e13c8a843db9c77cabf544c"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

log = logging.getLogger("bsc")


def pad(addr: str) -> str:
    return "0x" + "0" * 24 + addr.lower()[2:]


class Client:
    def __init__(self, url: str, max_rps: float):
        self.url = url
        self.min_gap = 1.0 / max_rps
        self.last = 0.0
        self.calls = 0

    def call(self, method: str, params: list, tries: int = 8) -> object:
        body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
        for attempt in range(tries):
            gap = time.monotonic() - self.last
            if gap < self.min_gap:
                time.sleep(self.min_gap - gap)
            self.last = time.monotonic()
            self.calls += 1
            try:
                req = urllib.request.Request(
                    self.url, data=body, headers={"Content-Type": "application/json", "User-Agent": "collusion-evidence-research"}
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    res = json.loads(resp.read())
                if "error" in res:
                    raise RuntimeError(str(res["error"])[:300])
                return res["result"]
            except Exception as exc:
                log.warning("%s attempt %d failed: %s", method, attempt, exc)
                if "429" in str(exc):
                    time.sleep(90)  # the provider's rate-limit window
                else:
                    time.sleep(min(60, 3 * (attempt + 1)))
        raise RuntimeError(f"{method} failed after {tries} tries")


def _batch(self: Client, calls: list[tuple[str, list]], tries: int = 8) -> list:
    body = json.dumps([{"jsonrpc": "2.0", "method": m, "params": p, "id": i} for i, (m, p) in enumerate(calls)]).encode()
    for attempt in range(tries):
        gap = time.monotonic() - self.last
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self.last = time.monotonic()
        self.calls += 1
        try:
            req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json", "User-Agent": "collusion-evidence-research"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                res = json.loads(resp.read())
            if not isinstance(res, list) or len(res) != len(calls):
                raise RuntimeError(f"bad batch response: {str(res)[:200]}")
            res = sorted(res, key=lambda x: x["id"])
            errs = [x["error"] for x in res if "error" in x]
            if errs:
                raise RuntimeError(str(errs[0])[:200])
            return [x["result"] for x in res]
        except Exception as exc:
            log.warning("batch attempt %d failed: %s", attempt, exc)
            time.sleep(90 if "429" in str(exc) else min(60, 3 * (attempt + 1)))
    raise RuntimeError("batch failed")


Client.batch = _batch  # type: ignore[attr-defined]
REGISTRY = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"


def block_ts(c: Client, n: int) -> int:
    # load-balanced public endpoints sometimes answer null for a block another backend has
    for _ in range(6):
        blk = c.call("eth_getBlockByNumber", [hex(n), False])
        if blk:
            return int(blk["timestamp"], 16)  # type: ignore[index]
        time.sleep(2)
    raise RuntimeError(f"block {n} not served")


def first_block_at(c: Client, ts: int, lo: int, hi: int) -> int:
    """Smallest block number with timestamp >= ts, searching in [lo, hi]."""
    while lo < hi:
        mid = (lo + hi) // 2
        if block_ts(c, mid) >= ts:
            hi = mid
        else:
            lo = mid + 1
    return lo


DISCREPANCIES: list[dict] = []
QUERIES_PER_CHUNK = 2  # load-balanced public endpoints can answer from a backend missing blocks


def _key(lg: dict) -> tuple[str, str]:
    return (lg["transactionHash"], lg["logIndex"])


def get_logs_range(c: Client, flt: dict, a: int, b: int, step: int) -> list[dict]:
    """Every chunk is queried QUERIES_PER_CHUNK times and the answers are merged; any
    disagreement is recorded (and written to discrepancies.jsonl by the caller)."""
    out: list[dict] = []
    cur = a
    while cur <= b:
        end = min(cur + step - 1, b)
        answers = []
        try:
            for _ in range(QUERIES_PER_CHUNK):
                answers.append(c.call("eth_getLogs", [{**flt, "fromBlock": hex(cur), "toBlock": hex(end)}], tries=4))
        except RuntimeError:
            if end > cur:
                step = max(1, step // 2)
                log.info("shrinking step to %d at %d", step, cur)
                continue
            raise
        merged = {}
        for ans in answers:
            for lg in ans:  # type: ignore[union-attr]
                merged[_key(lg)] = lg
        sizes = [len(x) for x in answers]  # type: ignore[arg-type]
        if len(set(sizes)) > 1 or len(merged) != sizes[0]:
            DISCREPANCIES.append({"from": cur, "to": end, "sizes": sizes, "merged": len(merged)})
            log.warning("disagreement %d-%d sizes %s merged %d", cur, end, sizes, len(merged))
        out.extend(sorted(merged.values(), key=lambda lg: (int(lg["blockNumber"], 16), int(lg["logIndex"], 16))))
        cur = end + 1
    return out


def write_rows(path: Path, rows: list[str]) -> None:
    tmp = Path(str(path) + ".part")
    with gzip.open(tmp, "wt") as fh:
        fh.writelines(rows)
    os.replace(tmp, path)


def pull_chunked(c: Client, flt: dict, start: int, end: int, out: Path, prefix: str, seg: int, step: int, fmt) -> None:
    out.mkdir(parents=True, exist_ok=True)
    a = start
    while a <= end:
        b = min(a + seg - 1, end)
        path = out / f"{prefix}_{a}_{b}.tsv.gz"
        if not path.exists():
            t = time.time()
            logs = get_logs_range(c, flt, a, b, step)
            write_rows(path, [fmt(lg) for lg in logs])
            log.info("%s %d-%d: %d logs in %.0fs (calls so far %d)", prefix, a, b, len(logs), time.time() - t, c.calls)
            if DISCREPANCIES:
                with open(out / "discrepancies.jsonl", "a") as fh:
                    for d in DISCREPANCIES:
                        fh.write(json.dumps({"prefix": prefix, **d}) + "\n")
                DISCREPANCIES.clear()
        a = b + 1


def fmt_raw(lg: dict) -> str:
    return (
        f"{int(lg['blockNumber'], 16)}\t{int(lg['transactionIndex'], 16)}\t{int(lg['logIndex'], 16)}\t"
        f"{lg['transactionHash']}\t{lg['address'].lower()}\t{';'.join(lg['topics'])}\t{lg['data']}\n"
    )


def fmt_transfer(lg: dict) -> str:
    t = lg["topics"]
    val = int(lg["data"], 16) if lg["data"] not in ("0x", "") else 0
    return (
        f"{int(lg['blockNumber'], 16)}\t{int(lg['transactionIndex'], 16)}\t{int(lg['logIndex'], 16)}\t"
        f"{lg['transactionHash']}\t{lg['address'].lower()}\t0x{t[1][-40:]}\t0x{t[2][-40:]}\t{val}\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["blocks", "anchors", "escrow", "escrowout", "transfers", "accounts", "owners", "receipts"])
    ap.add_argument("--rpc", default="https://bsc.api.pocket.network")
    ap.add_argument("--max-rps", type=float, default=1.5)
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--out", default="data/raw/bsc")
    ap.add_argument("--wallets", help="file with one address per line")
    ap.add_argument("--block", type=int)
    ap.add_argument("--times", nargs="*", default=[])
    ap.add_argument("--seg", type=int, default=100000)
    ap.add_argument("--step", type=int, default=5000)
    ap.add_argument("--batch", type=int, default=100)
    ap.add_argument("--ids", help="file with one ERC-8004 agent id per line")
    ap.add_argument("--txs", help="file with one transaction hash per line")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    c = Client(args.rpc, args.max_rps)
    out = Path(args.out)

    if args.cmd == "blocks":
        head = int(c.call("eth_blockNumber", []), 16)  # type: ignore[arg-type]
        res = {}
        for iso in args.times:
            ts = int(datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
            res[iso] = first_block_at(c, ts, 120_000_000, head - 2000)
            log.info("%s -> %d", iso, res[iso])
        out.mkdir(parents=True, exist_ok=True)
        (out / "blocks.json").write_text(json.dumps(res, indent=2) + "\n")
        print(json.dumps(res, indent=2))

    elif args.cmd == "anchors":
        # block timestamps every --seg blocks, for linear interpolation (BSC blocks are 0.45 s apart)
        rows = []
        for b in list(range(args.start, args.end + 1, args.seg)) + [args.end]:
            rows.append(f"{b}\t{block_ts(c, b)}\n")
        out.mkdir(parents=True, exist_ok=True)
        write_rows(out / f"anchors_{args.start}_{args.end}.tsv.gz", rows)
        log.info("anchors: %d", len(rows))

    elif args.cmd == "escrow":
        pull_chunked(c, {"address": [ESCROW_USDC, ESCROW_USDT]}, args.start, args.end, out / "escrow", "escrow", args.seg, args.step, fmt_raw)

    elif args.cmd == "escrowout":
        flt = {"address": [USDC_BSC, USDT_BSC], "topics": [TRANSFER, [pad(ESCROW_USDC), pad(ESCROW_USDT)]]}
        pull_chunked(c, flt, args.start, args.end, out / "escrow_out", "escrowout", args.seg, args.step, fmt_transfer)

    elif args.cmd == "transfers":
        wallets = sorted({w.strip().lower() for w in Path(args.wallets).read_text().split() if w.strip()})
        tag = Path(args.wallets).stem
        for i in range(0, len(wallets), args.batch):
            group = [pad(w) for w in wallets[i : i + args.batch]]
            sub = out / "transfers" / tag / f"b{i // args.batch:03d}"
            pull_chunked(c, {"address": [USDC_BSC, USDT_BSC], "topics": [TRANSFER, group]}, args.start, args.end, sub, "out", args.seg, args.step, fmt_transfer)
            pull_chunked(c, {"address": [USDC_BSC, USDT_BSC], "topics": [TRANSFER, None, group]}, args.start, args.end, sub, "in", args.seg, args.step, fmt_transfer)

    elif args.cmd == "owners":
        # ownerOf(agentId) on the BSC ERC-8004 identity registry at --block, JSON-RPC batches of 5
        ids = [int(x) for x in Path(args.ids).read_text().split()]
        path = out / f"owners_{Path(args.ids).stem}_{args.block}.tsv.gz"
        done: dict[int, str] = {}
        partial = Path(str(path) + ".partial.tsv")
        if partial.exists():
            for line in partial.read_text().splitlines():
                a, o = line.split("\t")
                done[int(a)] = o
        todo = [i for i in ids if i not in done]
        with open(partial, "a") as fh:
            for i in range(0, len(todo), 5):
                group = todo[i : i + 5]
                res = c.batch([("eth_call", [{"to": REGISTRY, "data": "0x6352211e" + format(a, "064x")}, hex(args.block)]) for a in group])
                for a, r in zip(group, res):
                    owner = ("0x" + r[-40:]) if isinstance(r, str) and len(r) >= 42 else "ERROR"
                    fh.write(f"{a}\t{owner}\n")
                    done[a] = owner
                if (i // 5) % 200 == 0:
                    log.info("owners %d/%d", len(done), len(ids))
        write_rows(path, [f"{a}\t{o}\n" for a, o in sorted(done.items())])
        log.info("owners written: %d", len(done))

    elif args.cmd == "receipts":
        txs = [t.strip() for t in Path(args.txs).read_text().split() if t.strip()]
        rows = []
        for tx in txs:
            r = c.call("eth_getTransactionReceipt", [tx])
            for lg in r["logs"]:  # type: ignore[index]
                rows.append(fmt_raw(lg))
        write_rows(out / f"receipts_{Path(args.txs).stem}.tsv.gz", rows)
        log.info("receipts: %d logs from %d txs", len(rows), len(txs))

    elif args.cmd == "accounts":
        wallets = sorted({w.strip().lower() for w in Path(args.wallets).read_text().split() if w.strip()})
        rows = []
        for w in wallets:
            nonce = int(c.call("eth_getTransactionCount", [w, hex(args.block)]), 16)  # type: ignore[arg-type]
            code = c.call("eth_getCode", [w, hex(args.block)])
            rows.append(f"{w}\t{nonce}\t{(len(code) - 2) // 2}\n")  # type: ignore[arg-type]
        out.mkdir(parents=True, exist_ok=True)
        write_rows(out / f"accounts_{Path(args.wallets).stem}.tsv.gz", rows)
        log.info("accounts: %d", len(rows))


if __name__ == "__main__":
    main()
