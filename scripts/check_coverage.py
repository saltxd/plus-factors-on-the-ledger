"""Check that the raw Base pull covers the whole block range with no gaps or thin segments.

  python scripts/check_coverage.py --raw data/raw/base --start 50715727 --end 52530126
Writes <raw>/coverage.json: one row per segment with its row count and transfers per block.
A segment with fewer than --min-per-block transfers per block is flagged (an endpoint that
answered from a backend missing logs produced 8 to 12 per block against 70 to 100 elsewhere).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--min-per-block", type=float, default=40.0)
    args = ap.parse_args()
    raw = Path(args.raw)
    segs = []
    for f in sorted(raw.glob("transfers_*.tsv.gz")):
        a, b = (int(x) for x in f.name.split(".")[0].split("_")[1:3])
        h = hashlib.sha256()
        n = 0
        with gzip.open(f, "rb") as fh:
            for line in fh:
                n += 1
                h.update(line)
        segs.append({"file": f.name, "start": a, "end": b, "rows": n, "per_block": round(n / (b - a + 1), 2), "sha256_rows": h.hexdigest()})
    segs.sort(key=lambda s: s["start"])
    gaps, cur = [], args.start
    for s in segs:
        if s["start"] > cur:
            gaps.append([cur, s["start"] - 1])
        cur = max(cur, s["end"] + 1)
    if cur <= args.end:
        gaps.append([cur, args.end])
    thin = [s["file"] for s in segs if s["per_block"] < args.min_per_block]
    out = {"segments": segs, "gaps": gaps, "thin_segments": thin, "total_rows": sum(s["rows"] for s in segs), "ok": not gaps and not thin}
    (raw / "coverage.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "segments"}, indent=2))


if __name__ == "__main__":
    main()
