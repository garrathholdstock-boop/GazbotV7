#!/usr/bin/env python3
"""Canonical MNQ 1-min tape: front month PER DATE by volume, from data/backfill/.

Writes reports/regime_2026-09-12/replication/mnq_1min_canon.parquet
Columns: ts (epoch s, bar START, UTC), open,high,low,close,volume, exp, et (America/New_York)
"""
import glob, duckdb, pandas as pd, numpy as np

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/regime_2026-09-12/replication/mnq_1min_canon.parquet"

def build():
    con = duckdb.connect()
    files = sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
    rows = [f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume "
            f"from read_parquet('{f}')" for f in files]
    df = con.execute(f"""
     with a as ({' union all '.join(rows)}),
     t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
     v as (select d,exp,sum(volume) vv from t group by 1,2),
     fr as (select d,exp from (select *,row_number() over
            (partition by d order by vv desc) rn from v) where rn=1)
     select t.ts,t.open,t.high,t.low,t.close,t.volume,t.exp
     from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
    df = df.drop_duplicates(subset=["ts"]).reset_index(drop=True)
    dt = pd.to_datetime(df.ts, unit="s", utc=True)
    df["et"] = dt.dt.tz_convert("America/New_York")
    return df

if __name__ == "__main__":
    df = build()
    duckdb.connect().execute("copy (select * from df) to '%s' (format parquet)" % OUT)
    print("rows", len(df), "dates", df.et.dt.date.nunique())
    print("span", df.et.min(), "->", df.et.max())
    # roll audit: close-to-close jump across the date boundary per contract change
    d = df.groupby(df.et.dt.date).agg(exp=("exp","first"), c=("close","last"), o=("open","first"))
    d["prevc"] = d.c.shift(1); d["prevexp"] = d.exp.shift(1)
    d["gap"] = d.o - d.prevc
    big = d[(d.gap.abs() > 100)]
    print("\ndate-boundary open-vs-prev-close gaps > 100pt:", len(big))
    print(big.to_string())
    print("\nroll dates (exp changes):")
    print(d[d.exp != d.prevexp].to_string())
