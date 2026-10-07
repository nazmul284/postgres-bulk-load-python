#!/bin/bash
# One round at 1M rows with nothing else running, to measure how much the concurrent
# benchmark affected the main runs. Writes results/runs_clean.jsonl.
cd "$(dirname "$0")/.."
: > results/runs_clean.jsonl
for m in to_sql_default to_sql_multi psycopg_executemany psycopg_copy_rows copy_csv adbc_ingest polars_adbc duckdb_postgres; do
  .venv/bin/python harness/load.py $m 1000000 6 | tail -1 >> results/runs_clean.jsonl
done
cat results/runs_clean.jsonl | cut -c1-110
