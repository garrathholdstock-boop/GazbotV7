"""Zarattini, Aziz & Barbon (2025) "Beat the Market" NOISE-AREA intraday momentum, implemented on
MNQ 1-min with THIS DESK'S friction (1.25pt/RT). Rules taken verbatim from the paper (sec 2):

  move[t-i, 9:30->HH:MM] = |Close[t-i,HH:MM]/Open[t-i,9:30] - 1|
  sigma[t,HH:MM]         = mean of that over the previous 14 sessions
  Upper = max(Open[t,9:30], Close[t-1,16:00]) * (1 + sigma)
  Lower = min(Open[t,9:30], Close[t-1,16:00]) * (1 - sigma)
  Decisions ONLY at HH:00 and HH:30. Long if price > Upper, short if price < Lower, flat otherwise
  is NOT a rule - the paper holds until the CLOSE or an opposite-boundary crossover (which reverses).
  Fills at the NEXT minute's open (no look-ahead on the decision price).
  1 lot, no vol-target leverage: we want points per trade, not a levered equity curve.

CONTROLS (the 2026-09-12 bar): day-block bootstrap over sessions; a PLACEBO that uses the same
machinery with the sigma band taken from a RANDOM other session (destroys the magnitude
conditioning while keeping the time-of-day structure and the tape).
"""
import duckdb, glob, numpy as np, pandas as pd
GB="/home/alphabot/gazbot7"; VPP=2.0; FRIC=1.25
rng=np.random.default_rng(23)
con=duckdb.connect()
files=sorted(glob.glob(f"{GB}/data/backfill/MNQ_*_1min.parquet"))
rows=[f"select '{f.split('_')[-2]}' exp, ts,open,high,low,close,volume from read_parquet('{f}')" for f in files]
df=con.execute(f"""
 with a as ({' union all '.join(rows)}),
 t as (select *, cast(to_timestamp(ts) at time zone 'UTC' as date) d from a),
 v as (select d,exp,sum(volume) vv from t group by 1,2),
 fr as (select d,exp from (select *,row_number() over (partition by d order by vv desc) rn from v) where rn=1)
 select t.ts,t.open,t.high,t.low,t.close from t join fr on t.d=fr.d and t.exp=fr.exp order by t.ts""").df()
et=pd.to_datetime(df.ts,unit="s",utc=True).dt.tz_convert("America/New_York")
df["et"]=et; df["sess"]=et.dt.date; df["hm"]=et.dt.hour*60+et.dt.minute
R=df[(df.hm>=570)&(df.hm<=960)].copy()              # 09:30..16:00 ET
sess=sorted(R.sess.unique())
byses={s:g.reset_index(drop=True) for s,g in R.groupby("sess")}
byses={s:g for s,g in byses.items() if len(g)>330 and g.hm.iloc[0]<=571}
sess=[s for s in sess if s in byses]
print("sessions with full RTH:",len(sess),sess[0],"..",sess[-1])

# per-session |move from open| profile by minute-of-session
prof={}
for s in sess:
    g=byses[s]; o=g.open.iloc[0]
    prof[s]=pd.Series((g.close/o-1).abs().values, index=g.hm.values)
prevclose={sess[i]:byses[sess[i-1]].close.iloc[-1] for i in range(1,len(sess))}

def run(session_list, band_source=None):
    trades=[]
    for i,s in enumerate(session_list):
        if i<14 or s not in prevclose: continue
        hist=[prof[x] for x in session_list[i-14:i]]
        src=s if band_source is None else band_source[s]
        if band_source is not None:
            j=session_list.index(src)
            if j<14: continue
            hist=[prof[x] for x in session_list[j-14:j]]
        sig=pd.concat(hist,axis=1).mean(axis=1)
        g=byses[s]; o=g.open.iloc[0]; pc=prevclose[s]
        up=max(o,pc)*(1+sig); lo=min(o,pc)*(1-sig)
        hm=g.hm.values; cl=g.close.values; op=g.open.values
        pos=0; entry=0.0; ent_hm=None
        for k in range(len(g)-1):
            m=hm[k]
            if m%30 or m<600 or m>=960: continue     # decisions on the half hour, 10:00..15:30
            if m not in up.index: continue
            px=cl[k]; want=1 if px>up[m] else (-1 if px<lo[m] else pos)
            if want!=pos:
                fill=op[k+1]
                if pos!=0:
                    trades.append(dict(s=s,side=pos,pt=pos*(fill-entry)-FRIC,hm=ent_hm))
                if want!=0: entry=fill; ent_hm=m
                pos=want
        if pos!=0:
            trades.append(dict(s=s,side=pos,pt=pos*(cl[-1]-entry)-FRIC,hm=ent_hm))
    return pd.DataFrame(trades)

T=run(sess)
def report(T,label):
    v=T.pt.values
    if len(v)==0: print(label,"no trades"); return
    t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
    wr=(v>0).mean(); win=v[v>0].mean(); loss=-v[v<=0].mean()
    ud=np.unique(T.s.values); idx={d:np.where(T.s.values==d)[0] for d in ud}
    bs=np.array([np.concatenate([v[idx[d]] for d in rng.choice(ud,len(ud),replace=True)]).mean()
                 for _ in range(4000)])
    print(f"{label:22s} n={len(v):4d} days={len(ud):3d} mean={v.mean():7.2f}pt (${v.mean()*VPP:7.2f}) "
          f"t={t:5.2f} CI[{np.percentile(bs,2.5):7.2f},{np.percentile(bs,97.5):7.2f}] "
          f"win={wr:.3f} payoff={win/loss if loss else float('nan'):.2f} total=${v.sum()*VPP:,.0f}")
report(T,"NOISE-AREA all")
h=sorted(T.s.unique()); mid=h[len(h)//2]
report(T[T.s<mid],"  first half")
report(T[T.s>=mid],"  second half")
for side,lab in ((1,"  longs"),(-1,"  shorts")): report(T[T.side==side],lab)
# PLACEBO: band from a random other session's history
for rep in range(3):
    perm={s:sess[rng.integers(14,len(sess))] for s in sess}
    report(run(sess,perm),f"PLACEBO band #{rep+1}")
T.to_csv(f"{GB}/reports/regime_2026-09-12/literature/noisearea_mnq_trades.csv",index=False)
