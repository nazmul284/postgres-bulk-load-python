"""Bar chart of load time at 1M rows. usage: uv run --with matplotlib python charts.py <out.png>"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
s = json.loads((Path(__file__).resolve().parent.parent / "results" / "summary.json").read_text())["1000000"]
LAB = {"to_sql_default": "pandas to_sql()", "to_sql_multi": "to_sql(method='multi')", "psycopg_executemany": "psycopg executemany",
       "psycopg_copy_rows": "psycopg COPY, row by row", "copy_csv": "COPY from a CSV buffer", "adbc_ingest": "ADBC adbc_ingest",
       "polars_adbc": "Polars write_database", "duckdb_postgres": "DuckDB postgres extension"}
order = sorted(s, key=lambda m: s[m]["median_s"])
fig, ax = plt.subplots(figsize=(10, 5.4), dpi=200)
for i, m in enumerate(order[::-1]):
    v = s[m]; c = "#c2410c" if m == "to_sql_multi" else ("#9ca3af" if m in ("to_sql_default", "psycopg_executemany") else "#0f766e")
    ax.barh(i, v["median_s"], color=c, height=0.62, zorder=2)
    ax.plot([v["min_s"], v["max_s"]], [i, i], color="#111827", lw=1, zorder=3)
    ax.text(v["max_s"] + 0.8, i, f"{v['median_s']:.2f} s", va="center", fontsize=9.5, color="#1f2328")
ax.set_yticks(range(len(order)), [LAB[m] for m in order[::-1]], fontsize=10.5)
ax.set_xlim(0, 72); ax.set_xlabel("seconds to load 1,000,000 rows (median of 5; line = min to max)", fontsize=10, color="#6b7280")
for sp in ("top", "right", "left"): ax.spines[sp].set_visible(False)
ax.tick_params(axis="y", length=0); ax.tick_params(axis="x", colors="#6b7280"); ax.grid(axis="x", color="#eeeeee", zorder=0)
fig.text(0.02, 0.96, "The 'faster' to_sql option was 4x slower. ADBC and DuckDB were up to 20x faster.", fontsize=13.5, weight="bold", color="#1f2328")
fig.text(0.02, 0.915, "Same pandas DataFrame, same Postgres 16 table, every row count and checksum verified", fontsize=10, color="#6b7280")
fig.text(0.02, 0.012, "Apple M2, 8 GB · Postgres 16.15 local · pandas 3.0.6, SQLAlchemy 2.1.3, psycopg 3.3.6, ADBC 1.12.0, DuckDB 1.5.6, Polars 2.0.0 · "
         "github.com/nazmul284/postgres-bulk-load-python", fontsize=6.6, color="#6b7280")
fig.subplots_adjust(left=0.26, right=0.97, top=0.87, bottom=0.13)
fig.savefig(sys.argv[1], facecolor="white"); print("ok")
