#!/usr/bin/env python3
"""S03 — per-MINUTE MNQ order-book features for ONE UTC day, from the B2 long-format parquet.

HYGIENE (mandatory, both documented pathologies):
  * CROSSED/LOCKED snapshots (ask0 <= bid0) are dropped.
  * FROZEN-FEED minutes: any minute in which ask0 price takes only ONE distinct value is
    dropped whole. (The documented incident: ask1p stuck at 30151.75 for 200,708 consecutive
    snapshots / 19.6h.)
  * A MISSING RUNG IS UNKNOWN, NEVER ZERO. Depth is built by ARITHMETIC ADDITION of the three
    rungs, so an absent rung propagates NULL and the snapshot drops out of depth3 — it is never
    silently summed as a shallower book, which is exactly how you manufacture the liquidity
    hole you are hunting.

CAUSALITY: this file produces per-minute rows keyed by the minute's START ts. Minute m covers
[m, m+60). Downstream, a decision taken at time T may only read minutes with m + 60 <= T.

OFI = Cont/Kukanov/Stoikov, snapshot to snapshot at the touch:
  e_n = 1{Pb_n>=Pb_n-1}*Qb_n - 1{Pb_n<=Pb_n-1}*Qb_n-1 - 1{Pa_n<=Pa_n-1}*Qa_n + 1{Pa_n>=Pa_n-1}*Qa_n-1
A lag across a gap is meaningless, so e_n is NULL unless the previous snapshot is within 2s.
"""
import sys, os, duckdb
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
day, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "500MB",
                             "threads": "2"})
Q = f"""
with raw as (
  select ts_ms, side, level, price, size from read_parquet('{src}')
  where symbol='MNQ' and level<=2
),
snap as (
  select ts_ms,
    max(case when side='bid' and level=0 then price end) b0p,
    max(case when side='bid' and level=0 then size  end) b0s,
    max(case when side='bid' and level=1 then size  end) b1s,
    max(case when side='bid' and level=2 then size  end) b2s,
    max(case when side='bid' and level=2 then price end) b2p,
    max(case when side='ask' and level=0 then price end) a0p,
    max(case when side='ask' and level=0 then size  end) a0s,
    max(case when side='ask' and level=1 then size  end) a1s,
    max(case when side='ask' and level=2 then size  end) a2s,
    max(case when side='ask' and level=2 then price end) a2p
  from raw group by ts_ms
),
ok as (  -- crossed / locked removed
  select * from snap where b0p is not null and a0p is not null and a0p > b0p
),
fr as (  -- frozen-feed minutes removed whole
  select (ts_ms - ts_ms % 60000) m from ok group by 1 having count(distinct a0p) = 1
),
cl as (
  select o.* from ok o where (o.ts_ms - o.ts_ms % 60000) not in (select m from fr)
),
lg as (
  select *,
    lag(ts_ms) over w pt, lag(b0p) over w pb0p, lag(b0s) over w pb0s,
    lag(a0p) over w pa0p, lag(a0s) over w pa0s
  from cl window w as (order by ts_ms)
),
e as (
  select ts_ms, b0p, a0p, b0s, a0s,
    (b0s + b1s + b2s) as db3, (a0s + a1s + a2s) as da3,
    (b0p - b2p) as bdepth_px, (a2p - a0p) as adepth_px,
    (a0p - b0p) as spread,
    case when pt is not null and ts_ms - pt <= 2000 then
      (case when b0p >= pb0p then b0s else 0 end) - (case when b0p <= pb0p then pb0s else 0 end)
      - (case when a0p <= pa0p then a0s else 0 end) + (case when a0p >= pa0p then pa0s else 0 end)
    end as ofi,
    case when pt is not null and (b0p<>pb0p or a0p<>pa0p or b0s<>pb0s or a0s<>pa0s)
         then 1 else 0 end as chg
  from lg
)
select
  cast((ts_ms - ts_ms % 60000)/1000 as bigint) as m,
  count(*)                              as n_snap,
  sum(chg)                              as n_chg,
  count(ofi)                            as n_ofi,
  sum(ofi)                              as ofi_sum,
  avg(db3)                              as db3_mean,
  avg(da3)                              as da3_mean,
  avg(b0s)                              as b0s_mean,
  avg(a0s)                              as a0s_mean,
  avg(spread)                           as spread_mean,
  -- book SHAPE: how far you must walk in PRICE to cover 3 rungs (big = sparse/gappy book)
  avg(bdepth_px)                        as bslope_px,
  avg(adepth_px)                        as aslope_px,
  -- the LAST snapshot inside the minute (the only one usable for a decision at m+60)
  arg_max(db3, ts_ms)                   as db3_last,
  arg_max(da3, ts_ms)                   as da3_last,
  arg_max(b0s, ts_ms)                   as b0s_last,
  arg_max(a0s, ts_ms)                   as a0s_last,
  arg_max((b0p+a0p)/2.0, ts_ms)         as mid_last,
  arg_max(spread, ts_ms)                as spread_last
from e group by 1 order by 1
"""
con.execute(f"copy ({Q}) to '{dst}' (format parquet)")
n = con.execute(f"select count(*), sum(n_snap) from read_parquet('{dst}')").fetchone()
print(f"{day} minutes={n[0]} snaps={n[1]}")
