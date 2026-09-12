#!/usr/bin/env python3
"""Two jobs.

(1) THE ADDENDUM'S CONTROL, DONE PROPERLY. For the best Line-1 directional cell, a BLOCK-LEVEL
    sign flip: entries are 1 minute apart but held h minutes, so trades inside the same h-minute
    window are near-duplicates and flipping signs per-trade understates the control's spread.
    Here the sign is randomised per h-minute block, preserving the overlap structure.

(2) THE ONE CONDITIONING TEST THAT IS NOT SPECIAL PLEADING. MNQ/MGC contemporaneous coupling
    TRIPLED over the year (0.19 -> 0.45). A dislocation trade can only work while the two are
    actually coupled, and coupling is knowable in advance. Condition on a CAUSAL trailing-20-
    SESSION lag-0 correlation (sessions strictly BEFORE the trading session), split at the TRAIN
    median. Pre-specified cells only: 5. No further search.
"""
import duckdb, numpy as np, pandas as pd, json, sys
sys.path.insert(0,"/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag")
from harness import *
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag"
con=duckdb.connect(config={'memory_limit':'600MB','threads':2})
df=con.execute(f"select ts,sday,q_o,q_c,g_o,g_c,q_r,g_r,(ts%86400) sec from '{OUT}/panel_1min.parquet' order by ts").df()
sp=json.load(open(f"{OUT}/03_splits.json"))
df['split']=np.where(df.sday<=sp['train'][1],'train',np.where(df.sday<=sp['validate'][1],'validate','test'))
US=(df.sec>=13*3600+30*60)&(df.sec<=20*3600+40*60)
d=df[US].reset_index(drop=True); sd=d.sday.values

# ---------- (1) block-level sign-flip control ----------
sig=rolling_sig(d.g_c.values, sd, 30)
e=fwd_open(d.q_o.values,sd,1); x=fwd_open(d.q_o.values,sd,61)
base=np.isfinite(sig)&np.isfinite(e)&np.isfinite(x)
cut=np.quantile(np.abs(sig)[base&(d.split.values=='train')],0.80)
sel=base&(np.abs(sig)>cut)
blk=np.zeros(len(d),dtype=np.int64)
pos=pd.Series(np.arange(len(d))).groupby(sd).cumcount().values
blk=sd.astype(np.int64)*100000 + (pos//60)          # integer division, deliberate
rng=np.random.default_rng(23); out=[]
for spl in ['train','validate','test']:
    m=sel&(d.split.values==spl)
    R=x[m]-e[m]; S=np.sign(sig[m]); B=blk[m]; DD=sd[m]
    real=np.nanmean(S*R-FRICTION['MNQ'])
    p_long=float((S>0).mean())
    ub,binv=np.unique(B,return_inverse=True)
    fl=[]
    for _ in range(400):
        bs=np.where(rng.random(len(ub))<p_long,1.0,-1.0)
        fl.append(float(np.nanmean(bs[binv]*R-FRICTION['MNQ'])))
    mean,lo,hi=day_block_boot(S*R-FRICTION['MNQ'],DD,n_boot=4000)
    out.append(dict(split=spl,n=int(m.sum()),n_blocks=len(ub),real_pt=round(real,2),
        blockflip_mean=round(float(np.mean(fl)),2),blockflip_sd=round(float(np.std(fl,ddof=1)),2),
        sd_units=round((real-float(np.mean(fl)))/float(np.std(fl,ddof=1)),2),
        db_ci=f"[{lo:.1f},{hi:.1f}]"))
C1=pd.DataFrame(out); C1.to_csv(f"{OUT}/09_blockflip.csv",index=False)
print("=== (1) MGC->MNQ k=30 h=60 top20, US hours: BLOCK-level sign-flip control ===")
print(C1.to_string(index=False))

# ---------- (2) causal trailing-20-session coupling ----------
per=df[US].groupby('sday').apply(lambda g: np.corrcoef(g.q_r.dropna(), g.g_r.reindex(g.q_r.dropna().index))[0,1]
                                 if g.q_r.notna().sum()>100 else np.nan, include_groups=False)
per=per.replace([np.inf,-np.inf],np.nan)
coup=per.shift(1).rolling(20,min_periods=15).mean()      # STRICTLY prior sessions
cmap=coup.to_dict()
d['coup']=[cmap.get(s,np.nan) for s in sd]
med=float(np.nanmedian(d.coup[d.split=='train']))
print(f"\n=== (2) trailing-20-session coupling: train median = {med:.3f}; "
      f"range {np.nanmin(d.coup):.2f} .. {np.nanmax(d.coup):.2f} ===")
per.to_csv(f"{OUT}/09_daily_coupling.csv")

dq=(2.0*d.q_c).diff(); dg=(10.0*d.g_c).diff(); s2=pd.Series(sd)
same=(s2.values==s2.shift(1).values); dq[~same]=np.nan; dg[~same]=np.nan
trm=(d.split.values=='train')&np.isfinite(dq)&np.isfinite(dg)
beta=float(np.polyfit(dg[trm],dq[trm],1)[0])
Sp=2.0*d.q_c.values-beta*10.0*d.g_c.values; grp=pd.Series(Sp).groupby(sd)
rows=[]
CELLS=[('spread',60,30),('spread',60,60),('spread',120,30),('spread',120,60)]
for _,w,h in CELLS:
    mu=grp.transform(lambda x:x.rolling(w,min_periods=w).mean()).values
    sg=grp.transform(lambda x:x.rolling(w,min_periods=w).std()).values
    z=(Sp-mu)/sg
    qo=pd.Series(d.q_o.values); go=pd.Series(d.g_o.values)
    def f(xx,off):
        v=xx.shift(-off).copy(); v[s2.values!=s2.shift(-off).values]=np.nan; return v.values
    qe,qx=f(qo,1),f(qo,1+h); ge,gx=f(go,1),f(go,1+h)
    sg2=np.where(z<-2.5,1.0,np.where(z>2.5,-1.0,0.0))
    bs=np.isfinite(z)&np.isfinite(qe)&np.isfinite(qx)&np.isfinite(ge)&np.isfinite(gx)&(sg2!=0)&np.isfinite(d.coup.values)
    for bucket,bm in [('coupling_HIGH',d.coup.values>med),('coupling_LOW',d.coup.values<=med)]:
        for spl in ['train','validate','test','POOLED']:
            m=bs&bm&((d.split.values==spl) if spl!='POOLED' else True)
            if m.sum()<150: continue
            p=sg2[m]*2.0*(qx[m]-qe[m]) - sg2[m]*beta*10.0*(gx[m]-ge[m]) - 7.00
            mean,lo,hi=day_block_boot(p,sd[m],n_boot=3000)
            rows.append(dict(cell=f"spread_w{w}_h{h}_z2.5",bucket=bucket,split=spl,n=int(m.sum()),
                hit=round(float(np.mean(p+7.0>0)),3),usd=round(mean,2),ci=f"[{lo:.1f},{hi:.1f}]"))
# the directional cell too
for bucket,bm in [('coupling_HIGH',d.coup.values>med),('coupling_LOW',d.coup.values<=med)]:
    for spl in ['train','validate','test','POOLED']:
        m=sel&bm&np.isfinite(d.coup.values)&((d.split.values==spl) if spl!='POOLED' else True)
        if m.sum()<150: continue
        p=np.sign(sig[m])*(x[m]-e[m])-FRICTION['MNQ']
        mean,lo,hi=day_block_boot(p,sd[m],n_boot=3000)
        rows.append(dict(cell="dir_MGC->MNQ_k30_h60_top20",bucket=bucket,split=spl,n=int(m.sum()),
            hit=round(float(np.mean(np.sign(sig[m])*(x[m]-e[m])>0)),3),usd=round(mean*2.0,2),ci=f"[{lo*2:.1f},{hi*2:.1f}]"))
C2=pd.DataFrame(rows); C2.to_csv(f"{OUT}/09_conditioned.csv",index=False)
pd.set_option('display.width',260)
print(C2.pivot_table(index=['cell','bucket'],columns='split',values='usd').reindex(columns=['train','validate','test','POOLED']).round(2).to_string())
print("\n--- POOLED rows with CIs ---")
print(C2[C2.split=='POOLED'].to_string(index=False))
