"""Summarise results/runs.jsonl into results/summary.json and print fixed-width tables."""
import json, statistics as st
from pathlib import Path
R = Path(__file__).resolve().parent.parent / "results"
runs = [json.loads(l) for l in (R / "runs.jsonl").open() if "error" not in l]
LAB = {"to_sql_default": "pandas to_sql()", "to_sql_multi": "to_sql(method='multi')",
       "psycopg_executemany": "psycopg executemany", "psycopg_copy_rows": "psycopg COPY write_row",
       "copy_csv": "COPY from to_csv buffer", "adbc_ingest": "ADBC adbc_ingest",
       "polars_adbc": "Polars write_database", "duckdb_postgres": "DuckDB postgres ext"}
summ = {}
for n in sorted({r["n"] for r in runs}):
    rows = {}
    for m in LAB:
        rs = [r for r in runs if r["n"] == n and r["method"] == m]
        if not rs: continue
        s = [r["seconds"] for r in rs]; mem = [r["extra_peak_mb"] for r in rs]
        rows[m] = {"reps": len(rs), "median_s": round(st.median(s), 3), "min_s": min(s), "max_s": max(s),
                   "rows_per_s": round(n / st.median(s)), "median_mb": round(st.median(mem)), "min_mb": min(mem), "max_mb": max(mem),
                   "all_verified": all(r["count_ok"] and r["sum_id_ok"] and r["amount_ok"] and r["nulls"] == 0 for r in rs)}
    summ[n] = rows
(R / "summary.json").write_text(json.dumps(summ, indent=1))
base = summ[1_000_000]["to_sql_default"]["median_s"]
lines = ["1,000,000 rows from a pandas DataFrame, median of 5 runs", "",
         f"{'method':26}{'seconds':>9}{'rows/s':>11}{'vs to_sql':>13}{'extra MB':>10}",
         f"{'-'*25:26}{'-'*7:>9}{'-'*9:>11}{'-'*11:>13}{'-'*8:>10}"]
for m, v in sorted(summ[1_000_000].items(), key=lambda kv: kv[1]["median_s"], reverse=True):
    sp = base / v["median_s"]
    lines.append(f"{LAB[m]:26}{v['median_s']:>9.2f}{v['rows_per_s']:>11,}{(f'{sp:.1f}x' if sp >= 1 else f'{1/sp:.1f}x slower'):>13}{v['median_mb']:>10}")
if 10_000_000 in summ:
    lines += ["", "", "10,000,000 rows, median of 2 runs", "",
              f"{'method':26}{'seconds':>9}{'rows/s':>11}{'extra MB':>10}",
              f"{'-'*25:26}{'-'*7:>9}{'-'*11:>13}{'-'*8:>10}"]
    for m, v in sorted(summ[10_000_000].items(), key=lambda kv: kv[1]["median_s"], reverse=True):
        lines.append(f"{LAB[m]:26}{v['median_s']:>9.2f}{v['rows_per_s']:>11,}{v['median_mb']:>10}")
(R / "tables.txt").write_text("\n".join(lines) + "\n"); print("\n".join(lines))
print("all verified:", all(v["all_verified"] for d in summ.values() for v in d.values()))
