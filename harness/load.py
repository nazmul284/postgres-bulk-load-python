"""Load one pandas DataFrame into Postgres with one method; print a JSON result line.

usage: python load.py <method> <n_rows> <rep>
Every method starts from the same in-memory pandas DataFrame (seeded), loads it into the
same freshly created table, and is timed from the start of the load call to commit,
including any conversion the method needs. A 1,000-row warm-up runs first.
"""
import io, json, resource, sys, time
import numpy as np, pandas as pd

DSN = "host=localhost port=5499 user=bench dbname=load"
URL = "postgresql+psycopg://bench@localhost:5499/load"
COLS = ["id", "created_at", "user_id", "amount", "category", "note", "is_active"]
DDL = """DROP TABLE IF EXISTS events;
CREATE TABLE events (id bigint, created_at timestamp, user_id integer, amount double precision,
                     category text, note text, is_active boolean)"""

def make(n, seed=7):
    rng = np.random.default_rng(seed)
    cats = np.array(["books", "games", "music", "food", "tools", "garden", "toys", "sport", "home", "auto"])
    letters = np.frombuffer(b"abcdefghijklmnopqrstuvwxyz", dtype="S1")
    notes = rng.choice(letters, size=(n, 16)).view("S16").ravel().astype(str)
    return pd.DataFrame({
        "id": np.arange(n, dtype="int64"),
        "created_at": pd.Timestamp("2026-01-01") + pd.to_timedelta(rng.integers(0, 86400 * 270, n), unit="s"),
        "user_id": rng.integers(1, 200_000, n, dtype="int32"),
        "amount": np.round(rng.gamma(2.0, 30.0, n), 2),
        "category": cats[rng.integers(0, len(cats), n)],
        "note": notes,
        "is_active": rng.random(n) < 0.8,
    })

def reset():
    import psycopg
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(DDL)

# ---------------------------------------------------------------- methods
def to_sql_default(df):
    from sqlalchemy import create_engine
    eng = create_engine(URL)
    df.to_sql("events", eng, if_exists="append", index=False)
    eng.dispose()

def to_sql_multi(df):
    from sqlalchemy import create_engine
    eng = create_engine(URL)
    df.to_sql("events", eng, if_exists="append", index=False, method="multi", chunksize=1000)
    eng.dispose()

def psycopg_executemany(df):
    import psycopg
    rows = list(df.itertuples(index=False, name=None))
    with psycopg.connect(DSN) as c, c.cursor() as cur:
        cur.executemany(f"INSERT INTO events ({','.join(COLS)}) VALUES ({','.join(['%s'] * len(COLS))})", rows)

def psycopg_copy_rows(df):
    import psycopg
    with psycopg.connect(DSN) as c, c.cursor() as cur:
        with cur.copy(f"COPY events ({','.join(COLS)}) FROM STDIN") as cp:
            for row in df.itertuples(index=False, name=None):
                cp.write_row(row)

def copy_csv(df):
    import psycopg
    buf = io.StringIO()
    df.to_csv(buf, header=False, index=False)
    data = buf.getvalue()
    with psycopg.connect(DSN) as c, c.cursor() as cur:
        with cur.copy(f"COPY events ({','.join(COLS)}) FROM STDIN WITH (FORMAT csv)") as cp:
            for i in range(0, len(data), 1 << 20):
                cp.write(data[i:i + (1 << 20)])

def adbc_ingest(df):
    import pyarrow as pa
    import adbc_driver_postgresql.dbapi as adbc
    t = pa.Table.from_pandas(df, preserve_index=False)
    with adbc.connect(f"postgresql://bench@localhost:5499/load") as c:
        with c.cursor() as cur:
            cur.adbc_ingest("events", t, mode="append")
        c.commit()

def polars_adbc(df):
    import polars as pl
    pl.from_pandas(df).write_database("events", "postgresql://bench@localhost:5499/load",
                                      engine="adbc", if_table_exists="append")

def duckdb_postgres(df):
    import duckdb
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute("ATTACH 'host=localhost port=5499 user=bench dbname=load' AS pg (TYPE postgres)")
    con.register("src", df)
    con.execute("INSERT INTO pg.public.events SELECT * FROM src")
    con.close()

METHODS = {f.__name__: f for f in (to_sql_default, to_sql_multi, psycopg_executemany, psycopg_copy_rows,
                                   copy_csv, adbc_ingest, polars_adbc, duckdb_postgres)}

def verify(n):
    import psycopg
    with psycopg.connect(DSN) as c:
        cnt, sid, samt, nnull = c.execute("select count(*), sum(id), round(sum(amount)::numeric, 2), "
                                          "count(*) filter (where note is null or created_at is null) from events").fetchone()
    return {"count_ok": cnt == n, "sum_id_ok": int(sid or 0) == n * (n - 1) // 2, "sum_amount": float(samt or 0), "nulls": nnull}

if __name__ == "__main__":
    method, n, rep = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    f = METHODS[method]
    df = make(n)
    reset(); f(df.head(1000))                       # warm-up: imports, connection, extension load
    reset()
    import gc, threading, psutil
    gc.collect()
    proc = psutil.Process()
    base = proc.memory_info().rss; peak = [base]; done = threading.Event()
    def sample():                                   # RSS every 5 ms while the load runs
        while not done.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss); time.sleep(0.005)
    th = threading.Thread(target=sample, daemon=True); th.start()
    t0 = time.perf_counter(); f(df); dt = time.perf_counter() - t0
    done.set(); th.join()
    expected_amount = round(float(df["amount"].sum()), 2)
    v = verify(n)
    v["amount_ok"] = abs(v.pop("sum_amount") - expected_amount) < 0.05 * max(1, n / 1e6)
    print(json.dumps({"method": method, "n": n, "rep": rep, "seconds": round(dt, 3),
                      "rows_per_s": round(n / dt), "extra_peak_mb": round((peak[0] - base) / 2**20, 1), **v}))
