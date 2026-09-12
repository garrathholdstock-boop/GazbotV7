"""Movement-2 idle-gate lab — PREP. Builds the per-second tape/book/bar caches the
replay needs, once, from capture.db (census window is strictly inside its 5-day tick
window: ticks 08-24 00:00 .. 08-28 21:00 UTC)."""
import os, duckdb

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/m2"
CAP = "/home/alphabot/gazbot7/data/capture.db"
LO = "2026-08-23 21:00:00"   # a little before the census window start
HI = "2026-08-28 23:30:00"

con = duckdb.connect()
con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
lo_ms = con.execute(f"select epoch_ms(TIMESTAMP '{LO}')").fetchone()[0]
hi_ms = con.execute(f"select epoch_ms(TIMESTAMP '{HI}')").fetchone()[0]

# ── 1) raw ticks (price path for tick-honest exits) ───────────────────────────
con.execute(f"""COPY (
  SELECT ts_ms, price, size, aggressor FROM c.ticks
  WHERE symbol='MNQ' AND ts_ms BETWEEN {lo_ms} AND {hi_ms} ORDER BY ts_ms
) TO '{OUT}/ticks.parquet' (FORMAT parquet)""")

# ── 2) per-second tape aggregate (buy/sell vol, first/last px) ────────────────
# bucket s = floor(ts_ms/1000); every rolling window used by the live code is a whole
# number of seconds, so second-buckets reproduce them exactly at a 1Hz decision clock.
con.execute(f"""COPY (
  SELECT (ts_ms // 1000)::BIGINT s,
         SUM(CASE WHEN aggressor='buy'  THEN size ELSE 0 END) buy_v,
         SUM(CASE WHEN aggressor='sell' THEN size ELSE 0 END) sell_v,
         SUM(size) tot_v, COUNT(*) n,
         arg_min(price, ts_ms) first_px, arg_max(price, ts_ms) last_px
  FROM c.ticks WHERE symbol='MNQ' AND ts_ms BETWEEN {lo_ms} AND {hi_ms}
  GROUP BY 1 ORDER BY 1
) TO '{OUT}/tape_sec.parquet' (FORMAT parquet)""")

# ── 3) per-second L1 book snapshot (last level-1 bid/ask at or before each second) ─
con.execute(f"""COPY (
  SELECT (ts_ms // 1000)::BIGINT s,
         arg_max(CASE WHEN side='bid' THEN price END, CASE WHEN side='bid' THEN ts_ms END) bid_px,
         arg_max(CASE WHEN side='bid' THEN size  END, CASE WHEN side='bid' THEN ts_ms END) bid_sz,
         arg_max(CASE WHEN side='ask' THEN price END, CASE WHEN side='ask' THEN ts_ms END) ask_px,
         arg_max(CASE WHEN side='ask' THEN size  END, CASE WHEN side='ask' THEN ts_ms END) ask_sz
  FROM c.book WHERE symbol='MNQ' AND level=1 AND ts_ms BETWEEN {lo_ms} AND {hi_ms}
  GROUP BY 1 ORDER BY 1
) TO '{OUT}/book1_sec.parquet' (FORMAT parquet)""")

# ── 4) 1-minute bars folded from the 5s stream (integer floor — never bar_ts/60) ──
con.execute(f"""COPY (
  SELECT (bar_ts - bar_ts % 60)::BIGINT m,
         arg_min(open, bar_ts) o, MAX(high) h, MIN(low) l, arg_max(close, bar_ts) cl, SUM(volume) v
  FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
    AND bar_ts BETWEEN {lo_ms//1000 - 7200} AND {hi_ms//1000}
  GROUP BY 1 ORDER BY 1
) TO '{OUT}/bars1m.parquet' (FORMAT parquet)""")

for f in ("ticks", "tape_sec", "book1_sec", "bars1m"):
    n = con.execute(f"select count(*) from '{OUT}/{f}.parquet'").fetchone()[0]
    print(f, n, os.path.getsize(f"{OUT}/{f}.parquet"))
