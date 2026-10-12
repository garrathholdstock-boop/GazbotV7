import duckdb, numpy as np, pickle, datetime as dt
R="/home/alphabot/gazbot7/data/tape/bars/"
def load(path_expr, t0, t1):
    q=f"select bar_ts,open,high,low,close,volume from read_parquet({path_expr}) where timeframe='1min' and bar_ts>={t0} and bar_ts<{t1} order by bar_ts"
    a=np.array(duckdb.connect().execute(q).fetchall(),dtype=np.float64); return a
def sessions(a):
    day=((a[:,0]+7200)//86400).astype(np.int64); ok=((a[:,0]+7200)%86400)<23*3600
    a=a[ok]; day=day[ok]; out={}
    idx=np.flatnonzero(np.diff(day))+1; parts=np.split(np.arange(len(a)),idx)
    for p in parts:
        d=int(day[p[0]]); out[d]=a[p]
    return out
def build(name, path_expr, t0, t1):
    a=load(path_expr,t0,t1); S=sessions(a)
    days=sorted(S); rng={d:S[d][:,2].max()-S[d][:,3].min() for d in days}
    rows=[]
    for i,d in enumerate(days):
        s=S[d]; ts=s[:,0]; mod=(ts%86400)
        win=(mod>=6*3600)&(mod<20*3600+2400)
        prev=[rng[x] for x in days[max(0,i-20):i]]
        Sd=float(np.mean(prev)) if len(prev)>=10 else np.nan
        c=s[:,4]; jump=np.nanmax(np.abs(np.diff(c))/c[:-1]) if len(c)>1 else 0
        rows.append(dict(day=d,date=dt.datetime.fromtimestamp(d*86400,dt.timezone.utc).date().isoformat(),n=len(s),nwin=int(win.sum()),S=Sd,jump=float(jump)))
    pickle.dump(dict(sess=S,meta=rows),open(f"sess_{name}.pkl","wb"))
    return rows
if __name__=="__main__":
    t0=int(dt.datetime(2014,11,1,tzinfo=dt.timezone.utc).timestamp()); t1=int(dt.datetime(2025,7,26,tzinfo=dt.timezone.utc).timestamp())
    m=build("NQ",f"'{R}NQ/20*.parquet'",t0,t1)
    import collections
    print("NQ sessions",len(m), "nwin<600:",sum(r['nwin']<600 for r in m),"jump>1.5%:",sum(r['jump']>0.015 for r in m),"S nan:",sum(np.isnan(r['S']) for r in m))
    t0=int(dt.datetime(2025,9,1,tzinfo=dt.timezone.utc).timestamp()); t1=int(dt.datetime(2026,9,1,tzinfo=dt.timezone.utc).timestamp())
    m=build("MNQ",f"'{R}MNQ/backfill_1min.parquet'",t0,t1)
    print("MNQ sessions",len(m),"nwin<600:",sum(r['nwin']<600 for r in m),"jump>1.5%:",sum(r['jump']>0.015 for r in m))
    print(m[0],m[-1])
