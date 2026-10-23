"""Cross-check the stored Base pull against a second endpoint.

Picks random 40-block ranges across the pulled span (seeded), re-reads every USDC Transfer
and AuthorizationUsed log in each range from an endpoint other than the one that produced
the stored segment, and compares the rows exactly. Writes data/verify_base_pull.json.

  python scripts/verify_base_pull.py --raw data/raw/base_mac --rpc-a <endpoint> --rpc-b <endpoint> --n 30
The node is reached through an SSH tunnel (ssh -L 18545:localhost:8545 cw-sentinel).
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
ROOT = Path(__file__).resolve().parents[1]


def call(url: str, flt: dict) -> list[dict]:
    body = json.dumps({"jsonrpc": "2.0", "method": "eth_getLogs", "params": [flt], "id": 1}).encode()
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "collusion-evidence-research"})
            res = json.loads(urllib.request.urlopen(req, timeout=120).read())
            if "error" in res:
                raise RuntimeError(res["error"])
            return res["result"]
        except Exception as exc:  # noqa: BLE001
            time.sleep(60 if "429" in str(exc) else 5 * (attempt + 1))
    raise RuntimeError(f"failed {flt}")


def stored_rows(raw: Path, a: int, b: int) -> tuple[set, set, str]:
    seg = None
    for f in raw.glob("transfers_*.tsv.gz"):
        s, e = (int(x) for x in f.name.split(".")[0].split("_")[1:3])
        if s <= a and b <= e:
            seg = (s, e)
    if seg is None:
        raise SystemExit(f"no stored segment covers {a}-{b}")
    s, e = seg
    tr, au = set(), set()
    with gzip.open(raw / f"transfers_{s}_{e}.tsv.gz", "rt") as fh:
        for line in fh:
            blk, txi, li, src, dst, val = line.rstrip("\n").split("\t")
            if a <= int(blk) <= b:
                tr.add((int(blk), int(li), src, dst, int(val)))
    with gzip.open(raw / f"auth_{s}_{e}.tsv.gz", "rt") as fh:
        for line in fh:
            blk, txi, li, who, nonce = line.rstrip("\n").split("\t")
            if a <= int(blk) <= b:
                au.add((int(blk), int(li), who))
    return tr, au, f"{s}_{e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--rpc", required=True, nargs="+", help="endpoints to compare against, used in turn")
    ap.add_argument("--start", type=int, default=50715727)
    ap.add_argument("--end", type=int, default=52530126)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261023)
    ap.add_argument("--out", default=str(ROOT / "data" / "verify_base_pull.json"))
    args = ap.parse_args()
    raw = Path(args.raw)
    rng = random.Random(args.seed)
    results = []
    for i in range(args.n):
        a = rng.randrange(args.start, args.end - 40)
        b = a + 39
        url = args.rpc[i % len(args.rpc)]
        logs = call(url, {"address": USDC, "topics": [[TRANSFER, AUTH_USED]], "fromBlock": hex(a), "toBlock": hex(b)})
        tr, au = set(), set()
        for lg in logs:
            t = lg["topics"]
            if t[0] == TRANSFER and len(t) == 3:
                val = int(lg["data"], 16) if lg["data"] not in ("0x", "") else 0
                tr.add((int(lg["blockNumber"], 16), int(lg["logIndex"], 16), "0x" + t[1][-40:], "0x" + t[2][-40:], val))
            elif t[0] == AUTH_USED and len(t) == 3:
                au.add((int(lg["blockNumber"], 16), int(lg["logIndex"], 16), "0x" + t[1][-40:]))
        st_tr, st_au, seg = stored_rows(raw, a, b)
        r = {"from": a, "to": b, "segment": seg, "endpoint": url, "transfers_stored": len(st_tr), "transfers_reread": len(tr),
             "auth_stored": len(st_au), "auth_reread": len(au), "match": st_tr == tr and st_au == au}
        results.append(r)
        print(json.dumps(r), flush=True)
        time.sleep(1.0)
    summary = {"ranges": len(results), "all_match": all(r["match"] for r in results), "results": results}
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n")
    print("all match:", summary["all_match"])


if __name__ == "__main__":
    main()
