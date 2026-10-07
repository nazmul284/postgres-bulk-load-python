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

# ---- follow-up experiments (results/extras.jsonl)
ex = [json.loads(l) for l in (R / "extras.jsonl").open()] if (R / "extras.jsonl").exists() else []
if ex:
    L2 = ["to_sql chunksize sweep, 200,000 rows (2 runs: median seconds, max extra MB)", "",
          f"{'method':22}{'chunksize':>11}{'seconds':>10}{'extra MB':>10}", f"{'-'*21:22}{'-'*9:>11}{'-'*7:>10}{'-'*8:>10}"]
    for m, cs in (("multi", 100), ("multi", 1000), ("multi", 5000), ("multi", 9000), ("default", None), ("default", 10000)):
        rr = [e for e in ex if e["exp"] == "chunks" and e["method"] == m and e["chunksize"] == cs]
        lab = "method='multi'" if m == "multi" else "default"
        L2.append(f"{lab:22}{(str(cs) if cs else 'None'):>11}{st.median(r['seconds'] for r in rr):>10.2f}{max(r['extra_mb'] for r in rr):>10.0f}")
    L2 += ["", "", "Same 1M rows into a table with a primary key and two indexes (median of 2, seconds)", "",
           f"{'method':26}{'no indexes':>12}{'pk + 2 idx':>12}{'slowdown':>10}", f"{'-'*25:26}{'-'*10:>12}{'-'*10:>12}{'-'*8:>10}"]
    for m in ("duckdb_postgres", "adbc_ingest", "psycopg_copy_rows", "copy_csv", "to_sql_default"):
        a = st.median(e["seconds"] for e in ex if e["exp"] == "indexes" and e["method"] == m and e["table"] == "no indexes")
        b = st.median(e["seconds"] for e in ex if e["exp"] == "indexes" and e["method"] == m and e["table"] != "no indexes")
        L2.append(f"{LAB[m]:26}{a:>12.2f}{b:>12.2f}{b / a:>9.1f}x")
    lt = [e for e in ex if e["exp"] == "load_then_index"]
    L2.append(f"{'ADBC, then build indexes':26}{'':>12}{st.median(e['total_s'] for e in lt):>12.2f}")
    (R / "tables_extras.txt").write_text("\n".join(L2) + "\n"); print("\n".join(L2))

stm = json.loads((R / "statements.json").read_text())
L3 = ["What each method sends to Postgres for 1,000 rows (from the server log)", "",
      f"{'method':24}{'statements':>12}  {'wire format':<22}", f"{'-'*23:24}{'-'*10:>12}  {'-'*20:<22}"]
for m, n, fmt in (("to_sql_default", "1,000", "INSERT per row"), ("psycopg_executemany", "1,000", "INSERT per row"),
                  ("to_sql_multi", "1", "INSERT, 7,000 params"), ("psycopg_copy_rows", "1", "COPY, text"),
                  ("copy_csv", "1", "COPY, CSV"), ("adbc_ingest", "1", "COPY, binary"), ("polars_adbc", "1", "COPY, binary"),
                  ("duckdb_postgres", "1", "COPY, binary")):
    assert m in stm
    L3.append(f"{LAB[m]:24}{n:>12}  {fmt:<22}")
(R / "tables_wire.txt").write_text("\n".join(L3) + "\n"); print("\n".join(L3))
