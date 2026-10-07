"""Main run: 1M rows x 8 methods x 5 reps, interleaved by rep. Scale check: 10M rows x 5 methods x 2 reps.
Appends one JSON line per run to results/runs.jsonl; skips runs already recorded."""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")
ALL = ["to_sql_default", "to_sql_multi", "psycopg_executemany", "psycopg_copy_rows", "copy_csv",
       "adbc_ingest", "polars_adbc", "duckdb_postgres"]
FAST = ["psycopg_copy_rows", "copy_csv", "adbc_ingest", "polars_adbc", "duckdb_postgres"]
plan = [(m, 1_000_000, r) for r in range(1, 6) for m in ALL] + [(m, 10_000_000, r) for r in range(1, 3) for m in FAST]
out = ROOT / "results" / "runs.jsonl"
done = {(j["method"], j["n"], j["rep"]) for j in map(json.loads, out.open())} if out.exists() else set()
for m, n, r in plan:
    if (m, n, r) in done:
        continue
    p = subprocess.run([PY, str(ROOT / "harness" / "load.py"), m, str(n), str(r)], capture_output=True, text=True)
    line = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else json.dumps({"method": m, "n": n, "rep": r, "error": p.stderr[-300:]})
    with out.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)
