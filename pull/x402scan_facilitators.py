"""Read x402scan's public list of facilitator addresses on Base, pinned to one commit.

x402scan (github.com/Merit-Systems/x402scan) keeps one TypeScript file per facilitator in
packages/external/facilitators/src/facilitators/; each lists the addresses that submit that
facilitator's settlements, per network. This script downloads every file at the pinned commit
and writes the Base addresses to data/x402scan_facilitators_base.csv (address, facilitator file).
The file is parsed as text; nothing downloaded is executed.

  python pull/x402scan_facilitators.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "Merit-Systems/x402scan"
COMMIT = "f205fbe6fa96924adecb3619e5bf6edbf1e1e697"
DIR = "packages/external/facilitators/src/facilitators"
log = logging.getLogger("x402scan_facilitators")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "onchain-collusion-evidence"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def base_addresses(ts: str) -> list[str]:
    """Addresses inside the `[Network.BASE]: [ ... ]` block of one facilitator file."""
    out: list[str] = []
    for m in re.finditer(r"\[Network\.BASE\]\s*:\s*\[", ts):
        depth, i = 1, m.end()
        while i < len(ts) and depth:
            depth += {"[": 1, "]": -1}.get(ts[i], 0)
            i += 1
        out += [a.lower() for a in re.findall(r"address:\s*'(0x[0-9a-fA-F]{40})'", ts[m.end() : i])]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "x402scan_facilitators_base.csv"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    listing = json.loads(fetch(f"https://api.github.com/repos/{REPO}/contents/{DIR}?ref={COMMIT}"))
    rows = []
    for item in sorted(listing, key=lambda x: x["name"]):
        if not item["name"].endswith(".ts") or item["name"] == "index.ts":
            continue
        ts = fetch(f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{DIR}/{item['name']}").decode()
        for a in base_addresses(ts):
            rows.append((a, item["name"][:-3]))
        time.sleep(0.5)
    rows = sorted(set(rows))
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["address", "facilitator"])
        w.writerows(rows)
    log.info("%d Base addresses from %d facilitator files at %s", len(rows), len({r[1] for r in rows}), COMMIT[:7])


if __name__ == "__main__":
    main()
