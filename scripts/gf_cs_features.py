"""CHOP-DAY SCALP — Step 2: the 5-second feature tape.

One row per 5 seconds per day, joining
  * 5s bars            -> price / high / low / volume
  * trade ticks        -> aggressor delta (the footprint), signed volume
  * depth_snap (10dp)  -> the resting book on both sides, 250ms sampled

and deriving everything the L2 chop-turn gate needs: trailing ATR, a trailing-30m
VWAP and its slope (the "is it actually ranging" test), position inside the trailing
30m range, and the book-side ratios plus their 30s trend (absorbing vs depleting).

Strictly TRAILING — every window looks backwards only.  Written per-day to
reports/friday_v7/sections/cs/feat/<day>.parquet
"""
from __future__ import annotations

import os
import sys

from gazbot7.lake import connect

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs/feat"

DAYS = ["2026-07-16", "2026-07-17", "2026-07-24",
        "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31",
        "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
        "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]

# 5s buckets per window
W1M, W5M, W30M, W60M = 12, 60, 360, 720

SQL = """
WITH
b AS (   -- 5s bars, one row per bucket
    SELECT bar_ts AS t, open, high, low, close, volume
    FROM bars
    WHERE symbol='MNQ' AND timeframe='5s'
      AND bar_ts >= {lo} AND bar_ts < {hi}
),
tk AS (  -- aggressor delta per 5s bucket, from the trade tape
    SELECT ts_ms/1000 - (ts_ms/1000) % 5 AS t,
           sum(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) AS dlt,
           sum(size) AS tvol,
           count(*)  AS nticks,
           arg_max(price, ts_ms) AS tpx
    FROM ticks
    WHERE symbol='MNQ' AND ts_ms >= {lo}*1000 AND ts_ms < {hi}*1000
    GROUP BY 1
),
dp AS (  -- last 10-deep snapshot in each 5s bucket
    SELECT ts_ms/1000 - (ts_ms/1000) % 5 AS t,
           arg_max(bid1s+bid2s+bid3s+bid4s+bid5s, ts_ms) AS bid5,
           arg_max(ask1s+ask2s+ask3s+ask4s+ask5s, ts_ms) AS ask5,
           arg_max(bid1s+bid2s+bid3s+bid4s+bid5s+bid6s+bid7s+bid8s+bid9s+bid10s, ts_ms) AS bid10,
           arg_max(ask1s+ask2s+ask3s+ask4s+ask5s+ask6s+ask7s+ask8s+ask9s+ask10s, ts_ms) AS ask10,
           arg_max(bid1s, ts_ms) AS bid1s,
           arg_max(ask1s, ts_ms) AS ask1s,
           arg_max(bid1p, ts_ms) AS bid1p,
           arg_max(ask1p, ts_ms) AS ask1p,
           count(*) AS nsnap
    FROM depth
    WHERE symbol='MNQ' AND ts_ms >= {lo}*1000 AND ts_ms < {hi}*1000
    GROUP BY 1
),
j AS (
    SELECT b.t, b.open, b.high, b.low, b.close, b.volume,
           coalesce(tk.dlt,0) AS dlt, coalesce(tk.tvol,0) AS tvol,
           coalesce(tk.nticks,0) AS nticks,
           dp.bid5, dp.ask5, dp.bid10, dp.ask10, dp.bid1s, dp.ask1s,
           dp.bid1p, dp.ask1p, coalesce(dp.nsnap,0) AS nsnap
    FROM b LEFT JOIN tk USING (t) LEFT JOIN dp USING (t)
),
m1 AS (  -- 1-minute true range, for a bar-honest ATR
    SELECT t - t % 60 AS m, max(high) AS mh, min(low) AS ml, arg_max(close,t) AS mc
    FROM j GROUP BY 1
),
m1b AS (
    SELECT m, mh, ml, mc, lag(mc) OVER (ORDER BY m) AS pmc FROM m1
),
m1tr AS (
    SELECT m, mc,
           greatest(mh-ml, abs(mh-coalesce(pmc,mc)), abs(ml-coalesce(pmc,mc))) AS tr,
           abs(mc - lag(mc) OVER (ORDER BY m)) AS step
    FROM m1b
),
m1r AS (
    SELECT m, mc,
           avg(tr)   OVER (ORDER BY m ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS atr20,
           sum(step) OVER (ORDER BY m ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS path30,
           abs(mc - lag(mc,30) OVER (ORDER BY m))                                AS disp30
    FROM m1tr
),
f AS (
    SELECT j.*,
           m1r.atr20,
           CASE WHEN m1r.path30 > 0 THEN m1r.disp30 / m1r.path30 END AS er30,
           -- trailing 30m VWAP and the slope of it over the last 10 minutes
           sum(j.close * j.volume) OVER w30 / nullif(sum(j.volume) OVER w30, 0) AS vwap30,
           max(j.high) OVER w30 AS hi30,
           min(j.low)  OVER w30 AS lo30,
           max(j.high) OVER w60 AS hi60,
           min(j.low)  OVER w60 AS lo60,
           sum(j.dlt)  OVER w30s AS dlt30s,
           sum(j.dlt)  OVER w60s AS dlt60s,
           sum(j.tvol) OVER w60s AS tvol60s,
           sum(j.tvol) OVER w30 AS tvol30m,
           j.close - lag(j.close, 6)  OVER (ORDER BY j.t) AS mv30s,
           j.close - lag(j.close, 12) OVER (ORDER BY j.t) AS mv60s,
           j.bid5  - lag(j.bid5, 6)  OVER (ORDER BY j.t) AS dbid5_30s,
           j.ask5  - lag(j.ask5, 6)  OVER (ORDER BY j.t) AS dask5_30s,
           avg(j.bid5) OVER w5m AS bid5_5m,
           avg(j.ask5) OVER w5m AS ask5_5m
    -- ★ the LAST COMPLETED minute, not the one this bucket sits inside.  Joining on
    -- the current minute leaks up to 55 seconds of future into atr20 and er30, and
    -- er30 is the strongest separator in the whole study.
    FROM j LEFT JOIN m1r ON m1r.m = j.t - j.t % 60 - 60
    WINDOW w30  AS (ORDER BY j.t ROWS BETWEEN 359 PRECEDING AND CURRENT ROW),
           w60  AS (ORDER BY j.t ROWS BETWEEN 719 PRECEDING AND CURRENT ROW),
           w5m  AS (ORDER BY j.t ROWS BETWEEN  59 PRECEDING AND CURRENT ROW),
           w30s AS (ORDER BY j.t ROWS BETWEEN   5 PRECEDING AND CURRENT ROW),
           w60s AS (ORDER BY j.t ROWS BETWEEN  11 PRECEDING AND CURRENT ROW)
)
SELECT *,
       lag(vwap30, 120) OVER (ORDER BY t) AS vwap30_10m
FROM f
ORDER BY t
"""


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    con = connect()
    only = sys.argv[1:] or DAYS
    for day in only:
        lo = f"epoch(TIMESTAMP '{day} 00:00:00')"
        hi = f"epoch(TIMESTAMP '{day} 00:00:00' + INTERVAL 1 DAY)"
        q = SQL.format(lo=lo, hi=hi)
        con.execute(f"COPY ({q}) TO '{OUT}/{day}.parquet' (FORMAT PARQUET)")
        n = con.execute(f"SELECT count(*), sum(nsnap>0), sum(nticks>0) "
                        f"FROM '{OUT}/{day}.parquet'").fetchone()
        print(f"{day}  rows={n[0]:6d}  with_book={n[1]:6d}  with_ticks={n[2]:6d}", flush=True)


if __name__ == "__main__":
    main()
