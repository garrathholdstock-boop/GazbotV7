#!/usr/bin/env python3
"""GIVE-BACK STUDY — stage 1: build the unified MNQ TICK tape + 1-min bars.

Sources (both raw trade ticks, ~250 ms):
  * /home/alphabot/alphabot2/data/ticks.db  trade_tick  MNQ  2026-07-05 .. 2026-07-17
  * /home/alphabot/gazbot7/data/capture.db  ticks       MNQ  2026-07-23 .. 2026-07-31
There is a hard GAP 07-18..07-22 (no tick capture anywhere) — days in the gap are simply
absent from the study; they are NOT bar-replayed, because every exit decision here has to
be made on ticks (desk rule: 250 ms ticks, never 1-minute bars, for exits).

Writes scratchpad/mfe_ticks.parquet  (ts_ms, price, sz, signed)  — the exec tape
        scratchpad/mfe_bars1m.parquet (ts, o, h, l, c, v, net)    — the signal tape

The 1-min bars are built FROM the same ticks, which is what the live desk does (agg.MinuteBars
folds the tape), so signals and fills come off one consistent tape.

  ./.venv/bin/python scripts/mfe_tape.py
"""
from __future__ import annotations

import os

import duckdb

ARCH = "/home/alphabot/alphabot2/data/ticks.db"
CAP = "/home/alphabot/gazbot7/data/capture.db"
OUT = "/home/alphabot/gazbot7/scratchpad"
SYM = "MNQ"

os.makedirs(OUT, exist_ok=True)
con = duckdb.connect()
con.execute("PRAGMA threads=4")
con.execute(f"ATTACH '{ARCH}' AS a (TYPE sqlite, READ_ONLY)")
con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")

# capture.db is authoritative wherever it exists; the archive fills in the earlier fortnight.
cut = con.execute(f"SELECT min(ts_ms) FROM c.ticks WHERE symbol='{SYM}'").fetchone()[0]
print("capture ticks start", cut)

con.execute(f"""
CREATE TABLE tape AS
SELECT ts_ms, price,
       CAST(size AS DOUBLE) AS sz,
       CASE aggressor WHEN 'buy' THEN CAST(size AS DOUBLE)
                      WHEN 'sell' THEN -CAST(size AS DOUBLE) ELSE 0.0 END AS signed
FROM a.trade_tick WHERE symbol='{SYM}' AND ts_ms < {cut}
UNION ALL
SELECT ts_ms, price,
       CAST(size AS DOUBLE) AS sz,
       CASE aggressor WHEN 'buy' THEN CAST(size AS DOUBLE)
                      WHEN 'sell' THEN -CAST(size AS DOUBLE) ELSE 0.0 END AS signed
FROM c.ticks WHERE symbol='{SYM}' AND ts_ms >= {cut}
ORDER BY ts_ms
""")
n, lo, hi = con.execute("SELECT count(*), min(ts_ms), max(ts_ms) FROM tape").fetchone()
print(f"unified tape {n:,} ticks  {lo} .. {hi}")

con.execute(f"COPY (SELECT * FROM tape ORDER BY ts_ms) TO '{OUT}/mfe_ticks.parquet' (FORMAT parquet)")

# ── 1-minute bars folded from the SAME ticks (matches agg.MinuteBars) ─────────────────
con.execute(f"""
COPY (
  SELECT CAST(ts_ms/60000 AS BIGINT)*60 AS ts,
         arg_min(price, ts_ms) AS o, max(price) AS h, min(price) AS l,
         arg_max(price, ts_ms) AS c, sum(sz) AS v, sum(signed) AS net
  FROM tape GROUP BY 1 ORDER BY 1
) TO '{OUT}/mfe_bars1m.parquet' (FORMAT parquet)
""")
b = con.execute(f"SELECT count(*), min(ts), max(ts) FROM '{OUT}/mfe_bars1m.parquet'").fetchone()
print(f"1m bars {b[0]:,}  {b[1]} .. {b[2]}")

days = con.execute("""
  SELECT strftime(to_timestamp(ts_ms/1000), '%Y-%m-%d') AS d, count(*) n,
         min(strftime(to_timestamp(ts_ms/1000),'%H:%M')) f,
         max(strftime(to_timestamp(ts_ms/1000),'%H:%M')) l
  FROM tape GROUP BY 1 ORDER BY 1
""").df()
print(days.to_string())
print("wrote", OUT)
