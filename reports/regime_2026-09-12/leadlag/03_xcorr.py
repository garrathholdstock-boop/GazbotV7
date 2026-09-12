#!/usr/bin/env python3
"""LINE 1 (descriptive): MNQ<->MGC cross-correlation at lags -30..+30 minutes.

Convention: XC(k) = corr( r_MGC(t), r_MNQ(t+k) ).   k>0  => GOLD LEADS NASDAQ by k minutes.
                                                    k<0  => NASDAQ LEADS GOLD.
Reported separately for train/validate/test (chronological 40/30/30 by session) so a lag that is
only in one period is visible as such. Also reported for ALL hours and for US hours only.
"""
import duckdb, numpy as np, pandas as pd, json, os
REPO="/home/alphabot/gazbot7"; OUT=f"{REPO}/reports/regime_2026-09-12/leadlag"
con=duckdb.connect(config={'memory_limit':'600MB','threads':2})
df=con.execute(f"""select ts, sday, q_r, g_r, q_dp, g_dp, q_v, g_v, q_c, g_c,
   (ts%86400) as sec_of_day from '{OUT}/panel_1min.parquet' order by ts""").df()

sdays=np.sort(df.sday.unique()); n=len(sdays)
i1,i2=int(n*0.40), int(n*0.70)
SPLIT={'train':set(sdays[:i1]),'validate':set(sdays[i1:i2]),'test':set(sdays[i2:])}
json.dump({k:[int(min(v)),int(max(v)),len(v)] for k,v in SPLIT.items()},
          open(f"{OUT}/03_splits.json","w"), indent=2)
print("splits (sessions):", {k:len(v) for k,v in SPLIT.items()})
print("split dates:", {k: (str(pd.to_datetime(min(v)*86400,unit='s').date()),
                           str(pd.to_datetime(max(v)*86400,unit='s').date())) for k,v in SPLIT.items()})

df['split']=np.select([df.sday.isin(SPLIT['train']),df.sday.isin(SPLIT['validate'])],
                      ['train','validate'],default='test')
US = (df.sec_of_day>=13*3600+30*60) & (df.sec_of_day<=20*3600+40*60)

def xcorr(sub, maxlag=30):
    """corr(g_r(t), q_r(t+k)). Only pairs inside the same session are used."""
    out={}
    g=sub.g_r.values; q=sub.q_r.values; s=sub.sday.values; t=sub.ts.values
    for k in range(-maxlag, maxlag+1):
        if k>=0: a=g[:len(g)-k] if k else g; b=q[k:]; sa=s[:len(s)-k] if k else s; sb=s[k:]; ta=t[:len(t)-k] if k else t; tb=t[k:]
        else:    a=g[-k:]; b=q[:len(q)+k]; sa=s[-k:]; sb=s[:len(s)+k]; ta=t[-k:]; tb=t[:len(t)+k]
        m=(sa==sb)&np.isfinite(a)&np.isfinite(b)&((tb-ta)==k*60)
        if m.sum()<200: out[k]=(np.nan,0); continue
        out[k]=(float(np.corrcoef(a[m],b[m])[0,1]), int(m.sum()))
    return out

rows=[]
for scope,mask in [('all_hours', pd.Series(True,index=df.index)), ('us_hours', US)]:
    for sp in ['train','validate','test']:
        sub=df[mask & (df.split==sp)]
        xc=xcorr(sub)
        for k,(r,nn) in xc.items():
            rows.append(dict(scope=scope, split=sp, lag_min=k, corr=r, n=nn))
res=pd.DataFrame(rows); res.to_csv(f"{OUT}/03_xcorr.csv", index=False)

piv=res.pivot_table(index=['scope','lag_min'],columns='split',values='corr')[['train','validate','test']]
sel=piv.loc[(slice(None), list(range(-6,7))),:]
print("\n=== XC(k)=corr(r_MGC(t), r_MNQ(t+k)); k>0 gold leads ===")
print(sel.round(4).to_string())
print("\n=== max |corr| at non-zero lag, by scope/split ===")
nz=res[res.lag_min!=0].dropna()
print(nz.loc[nz.assign(a=nz["corr"].abs()).groupby(["scope","split"])["a"].idxmax()].to_string(index=False))
print("\n=== lag-0 contemporaneous ===")
print(res[res.lag_min==0].to_string(index=False))
