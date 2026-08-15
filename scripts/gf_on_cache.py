#!/usr/bin/env python3
"""OPEN-NEWS greenfield — build a local cache of the tape the hunt needs, so every later sweep is
fast and reads the SAME frozen bytes (no sliding-window drift between candidates).

Writes to data/cache_gf_on/:
   bars5s.parquet   every 5s bar we hold  (v5 2026-06-25 -> hot 2026-08-14)
   ticks_win.parquet  every TRADE TICK inside 12:30-16:00Z (the hunt window + an hour of runway)
   book_win.parquet   L1-3 book snapshots inside the same window (11 days only)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

OUT = "/home/alphabot/gazbot7/data/cache_gf_on"
os.makedirs(OUT, exist_ok=True)

con = connect(symbol="MNQ")

print("bars…")
con.execute(f"""COPY (
    SELECT bar_ts, open, high, low, close, volume, src,
           strftime(to_timestamp(bar_ts),'%Y-%m-%d') AS d,
           CAST(strftime(to_timestamp(bar_ts),'%H') AS INT)*3600
         + CAST(strftime(to_timestamp(bar_ts),'%M') AS INT)*60
         + CAST(strftime(to_timestamp(bar_ts),'%S') AS INT) AS sod
    FROM bars WHERE timeframe='5s' ORDER BY bar_ts
) TO '{OUT}/bars5s.parquet' (FORMAT parquet)""")
print(con.execute(f"SELECT count(*), min(d), max(d) FROM read_parquet('{OUT}/bars5s.parquet')").fetchall())

print("ticks (12:30-16:00Z)…")
con.execute(f"""COPY (
    SELECT ts_ms, price, size, aggressor, src,
           strftime(to_timestamp(ts_ms/1000),'%Y-%m-%d') AS d,
           CAST(strftime(to_timestamp(ts_ms/1000),'%H') AS INT)*3600
         + CAST(strftime(to_timestamp(ts_ms/1000),'%M') AS INT)*60
         + CAST(strftime(to_timestamp(ts_ms/1000),'%S') AS INT) AS sod
    FROM ticks
    WHERE CAST(strftime(to_timestamp(ts_ms/1000),'%H') AS INT) BETWEEN 12 AND 15
      AND NOT (CAST(strftime(to_timestamp(ts_ms/1000),'%H') AS INT)=12
               AND CAST(strftime(to_timestamp(ts_ms/1000),'%M') AS INT)<30)
    ORDER BY ts_ms
) TO '{OUT}/ticks_win.parquet' (FORMAT parquet)""")
print(con.execute(f"SELECT count(*), min(d), max(d), count(DISTINCT d) FROM read_parquet('{OUT}/ticks_win.parquet')").fetchall())

print("book (12:30-16:00Z, L1-3)…")
try:
    con.execute(f"""COPY (
        SELECT ts_ms, side, level, price, size,
               strftime(to_timestamp(ts_ms/1000),'%Y-%m-%d') AS d,
               CAST(strftime(to_timestamp(ts_ms/1000),'%H') AS INT)*3600
             + CAST(strftime(to_timestamp(ts_ms/1000),'%M') AS INT)*60
             + CAST(strftime(to_timestamp(ts_ms/1000),'%S') AS INT) AS sod
        FROM book
        WHERE level<=3
          AND CAST(strftime(to_timestamp(ts_ms/1000),'%H') AS INT) BETWEEN 12 AND 15
          AND NOT (CAST(strftime(to_timestamp(ts_ms/1000),'%H') AS INT)=12
                   AND CAST(strftime(to_timestamp(ts_ms/1000),'%M') AS INT)<30)
        ORDER BY ts_ms
    ) TO '{OUT}/book_win.parquet' (FORMAT parquet)""")
    print(con.execute(f"SELECT count(*), min(d), max(d), count(DISTINCT d) FROM read_parquet('{OUT}/book_win.parquet')").fetchall())
except Exception as e:
    print("book skipped:", e)
