"""v3 - controls for the v2 result. Three things v2 could not settle:
  (1) CHRONOLOGICAL SPLIT: first half of sessions vs second half (no re-fitting; same band/state).
  (2) WITHIN-HOUR SHUFFLE CONTROL: shuffle the minute-to-minute returns inside each hour. This keeps
      the hour's volatility and its |net move| distribution but destroys path order. If the fade
      still pays on shuffled paths, its profit is a GEOMETRY artefact of a short-gamma payoff, not
      predictability. This is the better control the addendum asked for (a 5-way label permutation
      is not available here; this randomises WITHIN session).
  (3) SKEW: a short-gamma mean is not a safe mean. Report worst hour and 5th percentile.
"""
import duckdb, glob, numpy as np, pandas as pd
GB="/home/alphabot/gazbot7"; VPP=2.0; FRIC=1.25
rng=np.random.default_rng(11)
con=duckdb.connect()
files=sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
rows=[f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close from read_parquet('{f}')" for f in files]
df=con.execute(f"""
 with a as ({' union all '.join(rows)}),
 t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
 v as (select d,exp,count(*) vv from t group by 1,2),
 fr as (select d,exp from (select *,row_number() over (partition by d order by vv desc) rn from v) where rn=1)
 select t.ts,t.d,t.open,t.high,t.low,t.close from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
df["h"]=pd.to_datetime(df.ts,unit="s",utc=True).dt.hour
G={}; meta=[]
for (d,h),g in df[df.h.between(12,19)].groupby([df.d,df.h]):
    if len(g)<50: continue
    G[(d,h)]=g[["open","close"]].to_numpy(); meta.append(dict(d=d,h=h,rng=g.high.max()-g.low.min()))
M=pd.DataFrame(meta); M["prev_rng"]=M.groupby("d").rng.shift(1)
K=M.dropna(subset=["prev_rng"]).query("h>=13").copy()
cuts=K.prev_rng.quantile([1/3,2/3]).values
K["st"]=np.where(K.prev_rng<cuts[0],"LOW",np.where(K.prev_rng>cuts[1],"HIGH","MID"))

def repl(arr,band):
    o=arr[0,1]; pos=0; entry=0.0; pnl=0.0; rt=0
    for i in range(1,len(arr)-1):
        px=arr[i,1]; want=1 if px>o+band else (-1 if px<o-band else pos)
        if want!=pos:
            fill=arr[i+1,0]
            if pos!=0: pnl+=pos*(fill-entry); rt+=1
            pos=want; entry=fill
    if pos!=0: pnl+=pos*(arr[-1,1]-entry); rt+=1
    return pnl-rt*FRIC

def shuffled(arr):
    c=arr[:,1]; r=np.diff(c); rng.shuffle(r)
    nc=np.concatenate([[c[0]],c[0]+np.cumsum(r)])
    no=np.concatenate([[arr[0,0]],nc[:-1]])   # next-open == prior close on a shuffled path
    return np.column_stack([no,nc])

BAND=10
K["p"]=[repl(G[(r.d,r.h)],BAND) for _,r in K.iterrows()]
K["fade"]=-K.p
days=np.sort(K.d.unique()); half=days[len(days)//2]
print(f"BAND={BAND}pt  friction={FRIC}pt/RT  sessions={len(days)}  split at {half}\n")
for st in ("LOW","MID","HIGH"):
    s=K[K.st==st]
    for lab,sub in (("ALL",s),("H1",s[s.d<half]),("H2",s[s.d>=half])):
        v=sub.fade.values
        t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
        print(f"{st:5s} {lab:3s} n={len(v):4d} days={sub.d.nunique():3d} fade mean={v.mean():7.2f}pt "
              f"(${v.mean()*VPP:7.2f}) t={t:5.2f} median={np.median(v):7.2f} "
              f"p5={np.percentile(v,5):8.2f} worst={v.min():8.2f}")
    print()
# shuffle control on HIGH only
sh=K[K.st=="HIGH"]
reps=[]
for _ in range(40):
    vals=[-repl(shuffled(G[(r.d,r.h)]),BAND) for _,r in sh.iterrows()]
    reps.append(np.mean(vals))
reps=np.array(reps)
real=sh.fade.mean()
print(f"WITHIN-HOUR SHUFFLE CONTROL (HIGH state, 40 reps x n={len(sh)}):")
print(f"  real fade mean = {real:.2f}pt   shuffled mean = {reps.mean():.2f}pt "
      f"(sd {reps.std(ddof=1):.2f}, range {reps.min():.2f}..{reps.max():.2f})")
print(f"  real - shuffled = {real-reps.mean():.2f}pt = {(real-reps.mean())/reps.std(ddof=1):.1f} control sd")
K[["d","h","st","p","fade"]].to_csv(f"{GB}/reports/regime_2026-09-12/literature/fade_band10_hours.csv",index=False)
