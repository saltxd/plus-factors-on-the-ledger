"""Debug run of the Base extraction on a partial pull (one day of W2)."""
import json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import duckdb
import extract_base as eb
from cases import base_ts, expand

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
raw = Path(sys.argv[1]); db = sys.argv[2]; out = Path(sys.argv[3])
con = duckdb.connect(db)
con.execute("SET memory_limit='5GB'; SET threads=6; SET preserve_insertion_order=false")
if not con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='tr'").fetchone()[0]:
    tmp = raw.parent / "debug_raw"; tmp.mkdir(exist_ok=True)
    for f in raw.glob("*_5162292*_*.tsv.gz"):
        (tmp / f.name).unlink(missing_ok=True); (tmp / f.name).symlink_to(f.resolve())
    for f in raw.glob("*_5167292*_*.tsv.gz"):
        (tmp / f.name).unlink(missing_ok=True); (tmp / f.name).symlink_to(f.resolve())
    eb.load(con, tmp)
ov = {"w0": 51672927, "w1": 51722926, "d0": 51622927, "d1": 51722926}
ov["t0"], ov["t1"] = base_ts(ov["w0"]), base_ts(ov["w1"]) + 2
cases = [c for c in expand() if c.window == "W2" and c.chain == "base"]
payees = sorted({c.payee for c in cases})
bounds = eb.extract_window(con, "W2dbg", payees, 1000, 4, override=ov)
for c in cases:
    m = eb.write_case(con, c, c.payee, out, bounds, 1000, 4)
    print(json.dumps({k: m.get(k) for k in ("case_id", "n_payments", "n_payers", "volume", "reach_by_hop", "via_counts", "dropped")}))
