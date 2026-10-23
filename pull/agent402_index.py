"""Agent402's public seller index: its Base router verdict for every Base payTo it lists.

Agent402 (agent402.tools) publishes an x402 seller index at /api/index (keyless, paged). For each
seller origin it gives the Base payTo addresses from the seller's own 402 answers and the router's
verdict on Base (routerDispatchByChain.base.reason). One verdict, `settlement_self_funded`, means
the seller's settlement history without payments made with USDC the seller had sent the payer is
below the router's floor (see the index's own legend). Agent402 writes these verdicts; ChainWard
does not.

Every page is saved as downloaded under --raw (untrusted data, not executed); the parsed table,
payTo addresses and verdicts only, goes to --out.

  python -I pull/agent402_index.py --raw data/raw/agent402 --out data/raw/agent402/base_verdicts.csv

The full table stays out of the repository (it is a copy of a third party's index); src/market_summary.py
commits only the rows for payees in the market population (results/market_agent402_comparison.csv).
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

URL = "https://agent402.tools/api/index?page={page}&limit=250"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "onchain-collusion-evidence (research; one pass)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw = Path(args.raw)
    raw.mkdir(parents=True, exist_ok=True)
    page, last = 0, None
    while last is None or page <= last:
        path = raw / f"index_page_{page:03d}.json"
        if not path.exists():
            path.write_bytes(fetch(URL.format(page=page)))
            time.sleep(2.0)
        d = json.loads(path.read_text())
        last = int(d["lastPage"])
        page += 1
    rows, as_of = {}, set()
    for path in sorted(raw.glob("index_page_*.json")):
        d = json.loads(path.read_text())
        as_of.add(d.get("asOf"))
        for s in d.get("sellers", []):
            base = (s.get("routerDispatchByChain") or {}).get("base") or {}
            verdict = base.get("reason") if isinstance(base, dict) else None
            payto = set()
            for net, v in (s.get("payTosByNetwork") or {}).items():
                if net in ("eip155:8453", "base"):
                    payto |= {a.lower() for a in (v or []) if isinstance(a, str) and a.startswith("0x")}
            for net, v in (s.get("payToByNetwork") or {}).items():
                if net in ("eip155:8453", "base") and isinstance(v, str) and v.startswith("0x"):
                    payto.add(v.lower())
            for a in payto:
                r = rows.setdefault(a, {"payto": a, "origins": 0, "verdicts": set()})
                r["origins"] += 1
                if verdict:
                    r["verdicts"].add(verdict)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["payto", "origins_listing_it", "base_verdicts", "settlement_self_funded", "index_as_of"])
        for a in sorted(rows):
            r = rows[a]
            w.writerow([a, r["origins"], ";".join(sorted(r["verdicts"])), int("settlement_self_funded" in r["verdicts"]),
                        ";".join(sorted(x for x in as_of if x))])
    print(f"{page} pages, {len(rows)} Base payTo addresses, as of {sorted(x for x in as_of if x)[:1]}..{sorted(x for x in as_of if x)[-1:]}")


if __name__ == "__main__":
    main()
