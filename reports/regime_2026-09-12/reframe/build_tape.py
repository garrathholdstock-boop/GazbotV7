"""Build the canonical MNQ + MGC front-month 1-min tape ONCE, cache to parquet.
Loader copied from scripts/bt_regime_transition.py::tape (front month per DATE by volume)."""
import glob, duckdb, pandas as pd, sys
GB="/home/alphabot/gazbot7"; OUT=f"{GB}/reports/regime_2026-09-12/reframe"
def tape(sym):
    con=duckdb.connect()
    files=sorted(glob.glob(f"{GB}/data/backfill/{sym}_*_1min.parquet"))
    rows=[f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume from read_parquet('{f}')" for f in files]
    df=con.execute(f"""
     with a as ({' union all '.join(rows)}),
     t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
     v as (select d,exp,sum(volume) vv from t group by 1,2),
     fr as (select d,exp from (select *,row_number() over (partition by d order by vv desc) rn from v) where rn=1)
     select t.ts,t.open,t.high,t.low,t.close,t.volume from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
    con.close(); return df
for sym in ("MNQ","MGC"):
    d=tape(sym)
    d["dt"]=pd.to_datetime(d.ts,unit="s",utc=True)
    # CME session = 22:00Z prev day -> 21:00Z. Session date keyed by (dt + 2h).date  (same as bt_regime_transition)
    d["sess"]=(d.dt+pd.Timedelta(hours=2)).dt.date
    d["mod"]=d.dt.dt.hour*60+d.dt.dt.minute
    duckdb.connect().execute(f"copy (select * from d) to '{OUT}/tape_{sym}_1min.parquet' (format parquet)")
    print(sym,len(d),d.sess.nunique(),"sessions",d.dt.min(),d.dt.max())
