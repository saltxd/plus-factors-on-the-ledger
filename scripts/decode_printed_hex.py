"""Every hex token the seven published decodes print: full addresses and 8-to-39-digit prefixes.

Used only to keep payees the decodes examined out of the spot-check sample (cases/market_plan.md,
section 3). A payee counts as printed when its address equals a printed 40-digit token or starts
with a shorter one. Transaction hashes (64 digits) are skipped; their printed prefixes are kept,
which can only exclude more payees. Reads the decodes' published markdown from a ChainWard
checkout and writes data/decode_printed_hex.txt.

One BNB Chain decode prints four of the 62 ring wallets as examples. The list is written for Base
payees, and the repository names ring wallets only by pseudonym, so tokens matching a ring wallet
are dropped (rebuilt from the raw BNB Chain pull, which must be present); the sampler checks that
no ring wallet is a Base payee in the population, so dropping them changes nothing.

  python scripts/decode_printed_hex.py --decodes ~/Forge/chainward/deliverables
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SLUGS = ["x402-on-base", "x402-on-base-two-weeks-later", "x402-closed-six", "x402-top-ten-self-funded",
         "set-and-earn-week-one", "set-and-earn-week-one-closed", "termix-on-chain"]


def tokens(text: str) -> set[str]:
    out = set()
    for m in re.finditer(r"0x([0-9a-fA-F]+)", text):
        h = m.group(1).lower()
        if len(h) >= 64:
            continue
        if len(h) >= 8:
            out.add("0x" + h[:40])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decodes", required=True)
    ap.add_argument("--out", default=str(ROOT / "data" / "decode_printed_hex.txt"))
    args = ap.parse_args()
    found: set[str] = set()
    for s in SLUGS:
        found |= tokens((Path(args.decodes) / s / "decode.md").read_text())
    import logging

    import extract_bsc as xb

    logging.disable(logging.INFO)
    orders = xb.load_orders(xb.Clock())
    owner = xb.load_owners()
    ring = set(xb.ring_aliases({"ring48": xb.rebuild_ring48(orders, owner), "group14": xb.rebuild_group14(orders, owner)}))
    if len(ring) != 62:
        raise SystemExit("could not rebuild the 62 ring wallets; the raw BNB Chain pull is needed")
    dropped = {t for t in found if any(a.startswith(t) for a in ring)}
    kept = found - dropped
    Path(args.out).write_text("".join(f"{t}\n" for t in sorted(kept)))
    print(f"{len(kept)} tokens kept ({sum(len(t) == 42 for t in kept)} full addresses) from {len(SLUGS)} decodes; "
          f"{len(dropped)} tokens matching a ring wallet dropped")


if __name__ == "__main__":
    main()
