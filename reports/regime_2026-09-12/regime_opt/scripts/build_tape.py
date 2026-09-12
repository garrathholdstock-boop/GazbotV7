#!/usr/bin/env python3
"""Cache the front-month MNQ 1-min tape once so every later run is cheap.

Front month = the expiry with the most volume on that calendar date (same rule as
scripts/bt_regime_transition.py). Output: mnq_1min_front.parquet in the artifact dir.
"""
import duckdb, glob, os

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/regime_2026-09-12/regime_opt/mnq_1min_front.parquet"

files = sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
rows = [f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume "
        f"from read_parquet('{f}')" for f in files]
con = duckdb.connect()
con.execute(f"""
 copy (
  with a as ({' union all '.join(rows)}),
  t as (select *, cast(to_timestamp(ts) as date) d from a),
  v as (select d,exp,sum(volume) vv from t group by 1,2),
  fr as (select d,exp from (select *,row_number() over
         (partition by d order by vv desc) rn from v) where rn=1)
  select t.ts,t.open,t.high,t.low,t.close,t.volume
  from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts
 ) to '{OUT}' (format parquet)""")
n, a, b = con.execute(f"select count(*),min(ts),max(ts) from read_parquet('{OUT}')").fetchone()
import datetime as dt
print(f"rows={n}  {dt.datetime.fromtimestamp(a,dt.UTC)} -> {dt.datetime.fromtimestamp(b,dt.UTC)}")
print(f"size={os.path.getsize(OUT)/1e6:.1f}MB -> {OUT}")
