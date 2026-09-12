#!/usr/bin/env python3
"""Build per-session FRONT-MONTH 1-min series for MNQ and MGC from data/backfill/*_1min.parquet.

House rule: 22% of the gold year in data/tape/bars/MGC/backfill_1min.parquet is the WRONG
(dying/back) contract. So we never use that file. We pick, for EACH session date, the expiry
whose volume on that date is highest, and take only that expiry's bars for that session.

Session date (CME): bars from 22:00Z belong to the NEXT calendar day's session.
  session_epoch_day = (ts + 7200) // 86400     <-- integer division, deliberate (DuckDB '/' is FLOAT)
"""
import duckdb, glob, os, sys, json

REPO = "/home/alphabot/gazbot7"
OUT = f"{REPO}/reports/regime_2026-09-12/leadlag"
os.makedirs(OUT, exist_ok=True)
con = duckdb.connect()

def build(sym):
    files = sorted(glob.glob(f"{REPO}/data/backfill/{sym}_2*_1min.parquet"))
    parts = []
    for f in files:
        exp = os.path.basename(f).split("_")[1]
        parts.append(f"select '{exp}' as expiry, ts, open, high, low, close, volume from '{f}'")
    allq = " union all ".join(parts)
    con.execute(f"create or replace view raw_{sym} as {allq}")
    # per (session_day, expiry) volume
    con.execute(f"""
      create or replace table vol_{sym} as
      select (ts + 7200) // 86400 as sday, expiry, sum(volume) v, count(*) n
      from raw_{sym} group by 1,2
    """)
    # winner = max volume that day
    con.execute(f"""
      create or replace table win_{sym} as
      select sday, expiry, v, n from (
        select *, row_number() over (partition by sday order by v desc, expiry asc) rn
        from vol_{sym}
      ) where rn = 1
    """)
    con.execute(f"""
      create or replace table front_{sym} as
      select r.ts, r.open, r.high, r.low, r.close, r.volume, w.expiry, w.sday
      from raw_{sym} r join win_{sym} w
        on (r.ts + 7200)//86400 = w.sday and r.expiry = w.expiry
      order by r.ts
    """)
    con.execute(f"copy front_{sym} to '{OUT}/front_{sym}_1min.parquet' (format parquet)")
    # diagnostics: how much of the naive all-expiry pile is NOT the front month
    tot = con.execute(f"select sum(v) from vol_{sym}").fetchone()[0]
    fro = con.execute(f"select sum(v) from win_{sym}").fetchone()[0]
    nrows_raw = con.execute(f"select count(*) from raw_{sym}").fetchone()[0]
    nrows_front = con.execute(f"select count(*) from front_{sym}").fetchone()[0]
    rng = con.execute(f"select min(to_timestamp(ts))::date, max(to_timestamp(ts))::date, count(distinct sday) from front_{sym}").fetchone()
    d = dict(symbol=sym, rows_all_expiries=nrows_raw, rows_front=nrows_front,
             pct_rows_dropped=round(100*(1-nrows_front/nrows_raw),2),
             vol_all=tot, vol_front=fro, pct_vol_in_nonfront=round(100*(1-fro/tot),2),
             first=str(rng[0]), last=str(rng[1]), sessions=rng[2])
    con.execute(f"copy (select sday, to_timestamp(sday*86400)::date as session_date, expiry, v as volume, n as bars from win_{sym} order by sday) "
                f"to '{OUT}/front_map_{sym}.csv' (header, delimiter ',')")
    return d

res = [build("MNQ"), build("MGC")]
with open(f"{OUT}/01_front_build.json","w") as fh: json.dump(res, fh, indent=2)
for r in res: print(json.dumps(r))
