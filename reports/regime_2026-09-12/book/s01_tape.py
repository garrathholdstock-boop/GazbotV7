#!/usr/bin/env python3
"""S01 — build the MNQ 1-min tape that OVERLAPS the book window, and prove it matches
the tape bt_regime_transition.py was fitted on.

WHY THIS EXISTS: data/backfill/MNQ_*_1min.parquet — the tape the regime study uses — ENDS
2026-08-18. The order book (B2) runs 2026-07-31 -> 2026-09-11. Using the backfill alone would
give ~13 overlap sessions. capture.db has MNQ 5s bars 2026-07-15 -> 2026-09-11, covering the
whole book window. But [the lab's tape is not production's tape]: before substituting it I
MEASURE the two against each other on their overlap.
"""
import duckdb, numpy as np, pandas as pd, glob, datetime as dt, os
GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/regime_2026-09-12/book"
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp"})
con.execute(f"attach '{GB}/data/capture.db' as c (type sqlite, read_only)")

# ---- capture 5s -> 1min.  ⚠ DuckDB '/' is FLOAT: use modulo, never bar_ts/60*60.
cap = con.execute("""
 select (bar_ts - bar_ts % 60) as ts,
        arg_min(open, bar_ts) open, max(high) high, min(low) low,
        arg_max(close, bar_ts) as "close", sum(volume) volume, count(*) n5
 from c.bars where symbol='MNQ' and timeframe='5s'
 group by 1 order by 1""").df()
con.execute(f"copy (select * from cap) to '{OUT}/tape_capture_1min.parquet' (format parquet)")

# ---- backfill tape, exactly as bt_regime_transition.tape() resolves it (front month by volume)
files = sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
rows = [f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume from read_parquet('{f}')"
        for f in files]
bf = con.execute(f"""
 with a as ({' union all '.join(rows)}),
 t as (select *, cast(to_timestamp(ts) as date) d from a),
 v as (select d,exp,sum(volume) vv from t group by 1,2),
 fr as (select d,exp from (select *,row_number() over
        (partition by d order by vv desc) rn from v) where rn=1)
 select t.ts,t.open,t.high,t.low,t.close,t.volume from t join fr on t.d=fr.d and t.exp=fr.exp
 order by t.ts""").df()

j = bf.merge(cap, on="ts", suffixes=("_bf", "_cap"), how="inner")
d = (j.close_cap - j.close_bf)
lines = []
lines.append(f"backfill 1min : {len(bf):>8} bars  {dt.datetime.utcfromtimestamp(bf.ts.min())} -> {dt.datetime.utcfromtimestamp(bf.ts.max())}")
lines.append(f"capture  1min : {len(cap):>8} bars  {dt.datetime.utcfromtimestamp(cap.ts.min())} -> {dt.datetime.utcfromtimestamp(cap.ts.max())}")
lines.append(f"overlap       : {len(j):>8} bars")
lines.append(f"close diff    : mean {d.mean():+.4f}  sd {d.std():.4f}  |d|>0.25pt {100*(d.abs()>0.25).mean():.2f}%  max|d| {d.abs().max():.2f}")
r = np.corrcoef(j.close_bf.diff().fillna(0), j.close_cap.diff().fillna(0))[0, 1]
lines.append(f"1-min return correlation (bf vs cap): {r:.6f}")
# per-day bar counts on capture, to see which sessions are complete
cap["day"] = pd.to_datetime(cap.ts, unit="s", utc=True).dt.date
pc = cap.groupby("day").size()
lines.append(f"\ncapture bars/day (a full 23h CME day = 1380 1-min bars):")
for k, v in pc.items():
    lines.append(f"  {k}  {v}")
txt = "\n".join(lines)
open(f"{OUT}/s01_tape_check.txt", "w").write(txt + "\n")
print(txt)
