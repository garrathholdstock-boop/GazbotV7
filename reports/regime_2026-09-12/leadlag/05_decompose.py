#!/usr/bin/env python3
"""Decompose the headline TRAIN cells. The question is never "did this make points" but
"did the SIGN OF THE OTHER INSTRUMENT'S MOVE carry the information".

Three controls, all on the IDENTICAL entry minutes (this is the fix for the addendum's complaint
that a label permutation changes the entry population):
  LONG      : always long, same minutes, same holding period  -> pure drift/beta benchmark
  SIGNFLIP  : same minutes, position sign drawn at random with the SAME long-fraction as the real
              rule -> isolates directional information from timing
  TIMESHUF  : within-session permutation of the signal -> timing control (entry population changes)
"""
import duckdb, numpy as np, pandas as pd, json, sys
sys.path.insert(0,"/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag")
from harness import *
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag"
con=duckdb.connect(config={'memory_limit':'600MB','threads':2})
df=con.execute(f"select ts,sday,q_o,q_c,g_o,g_c,(ts%86400) sec from '{OUT}/panel_1min.parquet' order by ts").df()
sp=json.load(open(f"{OUT}/03_splits.json"))
def split_of(s): return 'train' if s<=sp['train'][1] else ('validate' if s<=sp['validate'][1] else 'test')
df['split']=[split_of(s) for s in df.sday.values]
US=(df.sec>=13*3600+30*60)&(df.sec<=20*3600+40*60)

CELLS=[('MGC->MNQ',30,60,'top20'),('MGC->MNQ',60,60,'top20'),('MGC->MNQ',60,30,'top20'),
       ('MGC->MNQ',30,60,'all'),('MGC->MNQ',60,60,'all'),('MGC->MNQ',15,60,'top20'),
       ('MNQ->MGC',30,60,'top20'),('MNQ->MGC',60,60,'top20')]
sub=df[US].reset_index(drop=True); sd=sub.sday.values
rows=[]
rng=np.random.default_rng(3)
for pair,k,h,thr in CELLS:
    sigcol,entrycol,inst = ('g_c','q_o','MNQ') if pair=='MGC->MNQ' else ('q_c','g_o','MGC')
    sig=rolling_sig(sub[sigcol].values, sd, k)
    e=fwd_open(sub[entrycol].values, sd, 1); x=fwd_open(sub[entrycol].values, sd, 1+h)
    base=np.isfinite(sig)&np.isfinite(e)&np.isfinite(x)
    tr=sub.split.values=='train'
    cut=np.quantile(np.abs(sig)[base&tr],0.80) if thr=='top20' else -1.0
    sel=base&(np.abs(sig)>cut)
    for spl in ['train','validate','test']:
        m=sel&(sub.split.values==spl)
        if m.sum()<200: continue
        S=sig[m]; E=e[m]; X=x[m]; D=sd[m]; R=X-E
        d=np.sign(S); longfrac=float((d>0).mean())
        real=d*R-FRICTION[inst]
        lng =R-FRICTION[inst]
        # SIGNFLIP: 200 reps, same minutes, random sign at the same long fraction
        fl=[]
        for _ in range(200):
            dd=np.where(rng.random(len(R))<longfrac,1.0,-1.0)
            fl.append(float(np.nanmean(dd*R-FRICTION[inst])))
        mr,lo,hi=day_block_boot(real,D)
        ml,llo,lhi=day_block_boot(lng,D)
        hit=float(np.nanmean((d*R)>0))
        rows.append(dict(pair=pair,k=k,h=h,thr=thr,split=spl,n=int(m.sum()),long_frac=round(longfrac,3),
            real_pt=round(mr,3), real_ci=f"[{lo:.2f},{hi:.2f}]",
            always_long_pt=round(ml,3), long_ci=f"[{llo:.2f},{lhi:.2f}]",
            signflip_mean=round(float(np.mean(fl)),3), signflip_sd=round(float(np.std(fl,ddof=1)),3),
            real_minus_flip=round(mr-float(np.mean(fl)),3),
            flip_sd_units=round((mr-float(np.mean(fl)))/float(np.std(fl,ddof=1)),2),
            hit_rate=round(hit,4), real_usd=round(mr*DOLLARS[inst],2)))
res=pd.DataFrame(rows); res.to_csv(f"{OUT}/05_decompose.csv",index=False)
pd.set_option('display.width',250)
print(res.to_string(index=False))
