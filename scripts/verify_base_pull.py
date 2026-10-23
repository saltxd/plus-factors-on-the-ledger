"""Cross-check stored Base segments against a reference endpoint, row by row.

For every stored segment listed in the given manifests (the segments pulled from public
endpoints), pick --per-segment random 40-block ranges (seeded), re-read every USDC Transfer
and AuthorizationUsed log in each range from the reference endpoint (ChainWard's node, through
an SSH tunnel), and compare the rows exactly.

  ssh -N -L 18545:localhost:8545 cw-sentinel &
  python scripts/verify_base_pull.py --raw data/raw/base_mac --ref http://localhost:18545 \
      --manifest data/raw/base_mac/manifest.jsonl --out data/verify_base_public_segments.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import time
import urllib.request
from pathlib import Path

USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
AUTH_USED = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"


def call(url: str, flt: dict) -> list[dict]:
    body = json.dumps({"jsonrpc": "2.0", "method": "eth_getLogs", "params": [flt], "id": 1}).encode()
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "collusion-evidence-research"})
            res = json.loads(urllib.request.urlopen(req, timeout=300).read())
            if "error" in res:
                raise RuntimeError(res["error"])
            return res["result"]
        except Exception as exc:  # noqa: BLE001
            time.sleep(60 if "429" in str(exc) else 5 * (attempt + 1))
    raise RuntimeError(f"failed {flt}")


def stored(raw: Path, s: int, e: int, a: int, b: int) -> tuple[set, set]:
    tr, au = set(), set()
    with gzip.open(raw / f"transfers_{s}_{e}.tsv.gz", "rt") as fh:
        for line in fh:
            blk, _txi, li, src, dst, val = line.rstrip("\n").split("\t")
            if a <= int(blk) <= b:
                tr.add((int(blk), int(li), src, dst, int(val)))
    with gzip.open(raw / f"auth_{s}_{e}.tsv.gz", "rt") as fh:
        for line in fh:
            blk, _txi, li, who, _nonce = line.rstrip("\n").split("\t")
            if a <= int(blk) <= b:
                au.add((int(blk), int(li), who))
    return tr, au


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--manifest", nargs="+", required=True)
    ap.add_argument("--per-segment", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20261023)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw = Path(args.raw)
    rng = random.Random(args.seed)
    segs = []
    for m in args.manifest:
        for line in Path(m).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if (raw / f"transfers_{r['start']}_{r['end']}.tsv.gz").exists():
                    segs.append(r)
    results = []
    for seg in sorted(segs, key=lambda r: r["start"]):
        for _ in range(args.per_segment):
            a = rng.randrange(seg["start"], seg["end"] - 39)
            b = a + 39
            logs = call(args.ref, {"address": USDC, "topics": [[TRANSFER, AUTH_USED]], "fromBlock": hex(a), "toBlock": hex(b)})
            tr, au = set(), set()
            for lg in logs:
                t = lg["topics"]
                if t[0] == TRANSFER and len(t) == 3:
                    val = int(lg["data"], 16) if lg["data"] not in ("0x", "") else 0
                    tr.add((int(lg["blockNumber"], 16), int(lg["logIndex"], 16), "0x" + t[1][-40:], "0x" + t[2][-40:], val))
                elif t[0] == AUTH_USED and len(t) == 3:
                    au.add((int(lg["blockNumber"], 16), int(lg["logIndex"], 16), "0x" + t[1][-40:]))
            st_tr, st_au = stored(raw, seg["start"], seg["end"], a, b)
            r = {"segment": [seg["start"], seg["end"]], "source": seg.get("rpc"), "from": a, "to": b,
                 "transfers_stored": len(st_tr), "transfers_reference": len(tr), "auth_stored": len(st_au), "auth_reference": len(au),
                 "match": st_tr == tr and st_au == au}
            results.append(r)
            print(json.dumps(r), flush=True)
            time.sleep(0.6)
    summary = {"reference": args.ref, "ranges": len(results), "segments": len(segs), "all_match": all(r["match"] for r in results), "results": results}
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n")
    print("all match:", summary["all_match"], "ranges:", len(results))


if __name__ == "__main__":
    main()
