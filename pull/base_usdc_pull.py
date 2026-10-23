"""Pull every USDC Transfer and AuthorizationUsed log on Base, plus every log of
TermiX's Base USDC escrow, for a block range, from any Base archive RPC.

Written for the Apart AI Collusion Research Sprint (Oct 23-25, 2026).

Output (one set of files per segment of SEGMENT blocks, tab separated, gzip):
  transfers_<a>_<b>.tsv.gz  block, tx_index, log_index, from, to, value (USDC base units, 6 decimals)
  auth_<a>_<b>.tsv.gz       block, tx_index, log_index, authorizer, nonce   (EIP-3009 AuthorizationUsed)
  escrow_<a>_<b>.tsv.gz     block, tx_index, log_index, tx_hash, topics (';'-joined), data
A segment is written to a .part file and renamed when complete, so a crashed run
resumes at the first missing segment.

Usage:
  python base_usdc_pull.py --rpc http://localhost:8545 --start 50715727 --end 52530126 --out DIR
  [--max-rps 1.0] [--segment 50000]

The RPC caps eth_getLogs at 20,000 results; chunk size adapts to stay under it.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path

USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TERMIX_ESCROW_BASE = "0xc3d963e0856a2c2d6f75c83c1355f680fd8f9f10"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
AUTH_USED = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"

log = logging.getLogger("pull")


class RangeTooLarge(Exception):
    def __init__(self, suggested_end: int | None):
        self.suggested_end = suggested_end


def rpc_call(url: str, method: str, params: list, timeout: int = 900) -> object:
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read())
    if "error" in res:
        msg = str(res["error"].get("message", res["error"]))
        # reth: "query exceeds max results 20000, retry with the range a-b";
        # Tenderly's gateway answers "invalid params" when a range returns too many logs
        if "exceeds max results" in msg or "too many" in msg.lower() or msg == "invalid params":
            m = re.search(r"range (\d+)-(\d+)", msg)
            raise RangeTooLarge(int(m.group(2)) if m else None)
        raise RuntimeError(msg)
    return res["result"]


class Pacer:
    """Keeps requests at or below max_rps."""

    def __init__(self, max_rps: float):
        self.min_gap = 1.0 / max_rps
        self.last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self.last
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self.last = time.monotonic()


def get_logs(url: str, pacer: Pacer, a: int, b: int) -> list[dict]:
    flt = {"address": [USDC, TERMIX_ESCROW_BASE], "fromBlock": hex(a), "toBlock": hex(b)}
    for attempt in range(8):
        pacer.wait()
        try:
            return rpc_call(url, "eth_getLogs", [flt])  # type: ignore[return-value]
        except RangeTooLarge:
            raise
        except Exception as exc:  # network hiccup, node busy or provider rate limit
            log.warning("retry %d-%d attempt %d: %s", a, b, attempt, exc)
            time.sleep(90 if "429" in str(exc) else min(60, 5 * (attempt + 1)))
    raise RuntimeError(f"failed {a}-{b}")


COVERAGE_LOG: Path | None = None


def covered_logs(url: str, pacer: Pacer, a: int, b: int, require: bool) -> list[dict]:
    """eth_getLogs for [a, b]; with require=True every block must carry at least one USDC log.
    Some load-balanced public endpoints answer from a backend that returns nothing for a range.
    A block can legitimately have no USDC transfer, so an answer is also accepted when two
    non-empty answers in a row miss exactly the same blocks."""
    if not require:
        return get_logs(url, pacer, a, b)
    prev_missing = None
    for attempt in range(8):
        logs = get_logs(url, pacer, a, b)
        have = {int(lg["blockNumber"], 16) for lg in logs if lg["address"].lower() == USDC}
        missing = set(range(a, b + 1)) - have
        if not missing:
            return logs
        if logs and prev_missing is not None and missing == prev_missing:
            if COVERAGE_LOG:
                with open(COVERAGE_LOG, "a") as fh:
                    fh.write(json.dumps({"from": a, "to": b, "blocks_without_usdc_logs": sorted(missing)}) + "\n")
            return logs
        prev_missing = missing if logs else None
        log.info("coverage retry %d-%d: %d of %d blocks missing", a, b, len(missing), b - a + 1)
        time.sleep(2)
    raise RuntimeError(f"no complete answer for {a}-{b}")


def pull_segment(url: str, pacer: Pacer, a: int, b: int, out: Path, require_coverage: bool = False) -> dict:
    names = {k: out / f"{k}_{a}_{b}.tsv.gz" for k in ("transfers", "auth", "escrow")}
    parts = {k: Path(str(p) + ".part") for k, p in names.items()}
    fh = {k: gzip.open(p, "wt", compresslevel=5) for k, p in parts.items()}
    counts = {"transfers": 0, "auth": 0, "escrow": 0, "calls": 0}
    chunk = 150
    cur = a
    while cur <= b:
        end = min(cur + chunk - 1, b)
        try:
            logs = covered_logs(url, pacer, cur, end, require_coverage)
        except RangeTooLarge as exc:
            new_end = exc.suggested_end if exc.suggested_end and exc.suggested_end < end else cur + max(1, (end - cur) // 2)
            chunk = max(1, new_end - cur + 1)
            continue
        counts["calls"] += 1
        for lg in logs:
            addr = lg["address"].lower()
            blk = int(lg["blockNumber"], 16)
            txi = int(lg["transactionIndex"], 16)
            li = int(lg["logIndex"], 16)
            topics = lg["topics"]
            if addr == USDC:
                if not topics:
                    continue
                t0 = topics[0]
                if t0 == TRANSFER and len(topics) == 3:
                    val = int(lg["data"], 16) if lg["data"] not in ("0x", "") else 0
                    fh["transfers"].write(f"{blk}\t{txi}\t{li}\t0x{topics[1][-40:]}\t0x{topics[2][-40:]}\t{val}\n")
                    counts["transfers"] += 1
                elif t0 == AUTH_USED and len(topics) == 3:
                    fh["auth"].write(f"{blk}\t{txi}\t{li}\t0x{topics[1][-40:]}\t{topics[2]}\n")
                    counts["auth"] += 1
            elif addr == TERMIX_ESCROW_BASE:
                fh["escrow"].write(f"{blk}\t{txi}\t{li}\t{lg['transactionHash']}\t{';'.join(topics)}\t{lg['data']}\n")
                counts["escrow"] += 1
        n = len(logs)
        # aim for about 14,000 logs per call
        if n < 7000:
            chunk = min(int(chunk * 1.5) + 1, 2000)
        elif n > 16000:
            chunk = max(1, int(chunk * 0.75))
        cur = end + 1
    for k in fh:
        fh[k].close()
        os.replace(parts[k], names[k])
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--segment", type=int, default=50000)
    ap.add_argument("--max-rps", type=float, default=1.0)
    ap.add_argument("--reverse", action="store_true", help="process segments from the end backwards")
    ap.add_argument("--require-coverage", action="store_true", help="retry answers that skip blocks (public endpoints)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pacer = Pacer(args.max_rps)
    global COVERAGE_LOG
    COVERAGE_LOG = out / "coverage_exceptions.jsonl"
    segments = []
    a = args.start
    while a <= args.end:
        segments.append((a, min(a + args.segment - 1, args.end)))
        a += args.segment
    if args.reverse:
        segments.reverse()
    for seg_start, seg_end in segments:
        done = all((out / f"{k}_{seg_start}_{seg_end}.tsv.gz").exists() for k in ("transfers", "auth", "escrow"))
        if done:
            log.info("skip %d-%d (done)", seg_start, seg_end)
        else:
            t = time.time()
            c = pull_segment(args.rpc, pacer, seg_start, seg_end, out, args.require_coverage)
            log.info("segment %d-%d %s in %.0fs", seg_start, seg_end, c, time.time() - t)
            with open(out / "manifest.jsonl", "a") as mf:
                mf.write(json.dumps({"start": seg_start, "end": seg_end, **c, "secs": round(time.time() - t), "rpc": args.rpc}) + "\n")
    log.info("DONE %d-%d", args.start, args.end)


if __name__ == "__main__":
    main()
