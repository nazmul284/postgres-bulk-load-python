"""Two follow-ups to the main run. Appends JSON lines to results/extras.jsonl.

  chunks:  to_sql(method='multi') at chunksize 100 / 1,000 / 5,000 / 9,000, and the default
           insert path at chunksize None / 10,000, 200,000 rows, 2 runs each
  indexes: the main methods into a table with a primary key and two secondary indexes, 1M rows, 2 runs each
"""
import json, sys, time, gc, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import load
from load import make, DSN, URL

OUT = Path(__file__).resolve().parent.parent / "results" / "extras.jsonl"
DDL_IDX = load.DDL + "; ALTER TABLE events ADD PRIMARY KEY (id); CREATE INDEX ON events (user_id); CREATE INDEX ON events (created_at)"

def timed(fn, df, ddl):
    import psycopg, psutil
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(ddl)
    fn(df.head(1000))
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(ddl)
    gc.collect(); proc = psutil.Process(); base = proc.memory_info().rss; peak = [base]; done = threading.Event()
    def sample():
        while not done.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss); time.sleep(0.005)
    th = threading.Thread(target=sample, daemon=True); th.start()
    t0 = time.perf_counter(); fn(df); dt = time.perf_counter() - t0; done.set(); th.join()
    with psycopg.connect(DSN) as c:
        ok = c.execute("select count(*) from events").fetchone()[0] == len(df)
    return round(dt, 3), round((peak[0] - base) / 2**20, 1), ok

def to_sql_chunks(method, chunksize):
    def f(df):
        from sqlalchemy import create_engine
        eng = create_engine(URL); df.to_sql("events", eng, if_exists="append", index=False, method=method, chunksize=chunksize); eng.dispose()
    return f

def emit(rec):
    with OUT.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec), flush=True)

if __name__ == "__main__":
    what = sys.argv[1]
    if what == "chunks":
        df = make(200_000)
        for rep in (1, 2):
            for method, cs in (("multi", 100), ("multi", 1000), ("multi", 5000), ("multi", 9000), (None, None), (None, 10000)):
                s, mb, ok = timed(to_sql_chunks(method, cs), df, load.DDL)
                emit({"exp": "chunks", "method": method or "default", "chunksize": cs, "n": len(df), "rep": rep, "seconds": s, "extra_mb": mb, "ok": ok})
    if what == "indexes":
        df = make(1_000_000)
        for rep in (1, 2):
            for name in ("to_sql_default", "copy_csv", "adbc_ingest", "duckdb_postgres", "psycopg_copy_rows"):
                for ddl, lab in ((load.DDL, "no indexes"), (DDL_IDX, "pk + 2 indexes")):
                    s, mb, ok = timed(load.METHODS[name], df, ddl)
                    emit({"exp": "indexes", "method": name, "table": lab, "n": len(df), "rep": rep, "seconds": s, "extra_mb": mb, "ok": ok})

def load_then_index(df):
    """ADBC into a bare table, then add the primary key and both indexes; returns (load s, index s)."""
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(load.DDL)
    t0 = time.perf_counter(); load.adbc_ingest(df); t1 = time.perf_counter()
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("ALTER TABLE events ADD PRIMARY KEY (id)"); c.execute("CREATE INDEX ON events (user_id)"); c.execute("CREATE INDEX ON events (created_at)")
    t2 = time.perf_counter()
    return round(t1 - t0, 3), round(t2 - t1, 3)

if __name__ == "__main__" and sys.argv[1] == "load_then_index":
    df = make(1_000_000); load.reset(); load.adbc_ingest(df.head(1000))
    for rep in (1, 2):
        a, b = load_then_index(df)
        emit({"exp": "load_then_index", "method": "adbc_ingest", "n": len(df), "rep": rep, "load_s": a, "index_s": b, "total_s": round(a + b, 3)})
