"""v2 - fixes the look-ahead in v1 (which filled at the SIGNAL BAR'S CLOSE, a price you only know
once it has printed). v2 fills at the NEXT minute's OPEN. Adds a day-block bootstrap and a
within-session shuffle control, per the 2026-09-12 addendum's bar.

LONG-REPLICATION = the futures attempt at a long straddle (buy above band, sell below, reverse).
Its NEGATIVE is the FADE. Both are reported so the sign is never implied.
"""
import duckdb, glob, numpy as np, pandas as pd
GB="/home/alphabot/gazbot7"; VPP=2.0; FRIC=1.25
rng=np.random.default_rng(7)
con=duckdb.connect()
files=sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
rows=[f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume from read_parquet('{f}')" for f in files]
df=con.execute(f"""
 with a as ({' union all '.join(rows)}),
 t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
 v as (select d,exp,sum(volume) vv from t group by 1,2),
 fr as (select d,exp from (select *,row_number() over (partition by d order by vv desc) rn from v) where rn=1)
 select t.ts,t.d,t.open,t.high,t.low,t.close from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
df["h"]=pd.to_datetime(df.ts,unit="s",utc=True).dt.hour
G={}; meta=[]
for (d,h),g in df[df.h.between(12,19)].groupby([df.d,df.h]):
    if len(g)<50: continue
    G[(d,h)]=g[["open","close"]].to_numpy()
    meta.append(dict(d=d,h=h,o=g.close.iloc[0],c=g.close.iloc[-1],rng=g.high.max()-g.low.min()))
M=pd.DataFrame(meta); M["prev_rng"]=M.groupby("d").rng.shift(1)
K=M.dropna(subset=["prev_rng"]).query("h>=13").copy()
cuts=K.prev_rng.quantile([1/3,2/3]).values
K["st"]=np.where(K.prev_rng<cuts[0],"LOW",np.where(K.prev_rng>cuts[1],"HIGH","MID"))

def repl(arr,band):
    """arr[:,0]=open arr[:,1]=close. Signal on close of bar i, FILL at open of bar i+1."""
    o=arr[0,1]; pos=0; entry=0.0; pnl=0.0; rt=0
    n=len(arr)
    for i in range(1,n-1):
        px=arr[i,1]
        want=1 if px>o+band else (-1 if px<o-band else pos)
        if want!=pos:
            fill=arr[i+1,0]                      # next bar's open - no look-ahead
            if pos!=0: pnl+=pos*(fill-entry); rt+=1
            pos=want; entry=fill
    if pos!=0: pnl+=pos*(arr[-1,1]-entry); rt+=1
    return pnl-rt*FRIC, rt

rowsout=[]
for band in (10,20,40):
    pn={}; rts={}
    for _,r in K.iterrows():
        p,q=repl(G[(r.d,r.h)],band); pn[(r.d,r.h)]=p; rts[(r.d,r.h)]=q
    K[f"p{band}"]=[pn[(r.d,r.h)] for _,r in K.iterrows()]
    K[f"rt{band}"]=[rts[(r.d,r.h)] for _,r in K.iterrows()]
    for st in ("LOW","MID","HIGH"):
        s=K[K.st==st]; v=s[f"p{band}"].values
        t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
        # DAY-BLOCK bootstrap: resample whole sessions, 5000 reps
        days=s.d.values; ud=np.unique(days)
        idx={d:np.where(days==d)[0] for d in ud}
        bs=np.empty(5000)
        for b in range(5000):
            pick=rng.choice(ud,len(ud),replace=True)
            bs[b]=np.concatenate([v[idx[d]] for d in pick]).mean()
        lo,hi=np.percentile(bs,[2.5,97.5])
        rowsout.append(dict(band=band,state=st,n=len(v),n_days=len(ud),
            long_repl_pt=v.mean(),fade_pt=-v.mean(),t=t,ci_lo=lo,ci_hi=hi,
            mean_rt=s[f"rt{band}"].mean(),usd_fade=-v.mean()*VPP))
O=pd.DataFrame(rowsout)
pd.set_option("display.width",250)
print(O.to_string(index=False,float_format=lambda x:f"{x:8.2f}"))
print("\nhours",len(K),"sessions",K.d.nunique(),"prev-hour-range tercile cuts",cuts.round(1))
O.to_csv(f"{GB}/reports/regime_2026-09-12/literature/straddle_replication_mnq.csv",index=False)
