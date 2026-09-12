#!/usr/bin/env python3
"""LINE 1 (causal): does a k-minute move in one instrument predict the next h minutes of the other?

Grid, run on TRAIN only for SELECTION, then the surviving cells are confirmed on VALIDATE and TEST.
Every cell also gets: a within-session shuffled twin (20 reps) and a day-block bootstrap CI.
"""
import duckdb, numpy as np, pandas as pd, json, sys, os
sys.path.insert(0,"/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag")
from harness import *
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag"
con=duckdb.connect(config={'memory_limit':'600MB','threads':2})
df=con.execute(f"""select ts, sday, q_o, q_c, g_o, g_c, (ts%86400) sec from '{OUT}/panel_1min.parquet' order by ts""").df()
sp=json.load(open(f"{OUT}/03_splits.json"))
def split_of(s):
    if s<=sp['train'][1]: return 'train'
    if s<=sp['validate'][1]: return 'validate'
    return 'test'
df['split']=[split_of(s) for s in df.sday.values]

KS=[1,5,15,30,60]; HS=[5,15,30,60]
PAIRS=[('MGC->MNQ','g_c','q_o','MNQ'), ('MNQ->MGC','q_c','g_o','MGC')]
SCOPES={'us_hours': (df.sec>=13*3600+30*60)&(df.sec<=20*3600+40*60), 'all_hours': pd.Series(True,index=df.index)}

# precompute 20 within-session index permutations per scope (reused for every cell)
PERM={}
rng=np.random.default_rng(11)
for sc,mask in SCOPES.items():
    sub=df[mask]
    idx_by_day=[g.values for _,g in pd.Series(np.arange(len(sub))).groupby(sub.sday.values)]
    reps=[]
    for _ in range(20):
        p=np.arange(len(sub))
        for ix in idx_by_day:
            q=ix.copy(); rng.shuffle(q); p[ix]=q
        reps.append(p)
    PERM[sc]=reps

rows=[]
for sc,mask in SCOPES.items():
    sub=df[mask].reset_index(drop=True)
    sd=sub.sday.values
    for name,sigcol,entrycol,inst in PAIRS:
        for k in KS:
            sig=rolling_sig(sub[sigcol].values, sd, k)
            for h in HS:
                e=fwd_open(sub[entrycol].values, sd, 1)
                x=fwd_open(sub[entrycol].values, sd, 1+h)
                base=np.isfinite(sig)&np.isfinite(e)&np.isfinite(x)
                for thr_name,q in [('all',0.0),('top20',0.80)]:
                    tr=sub.split.values=='train'
                    absv=np.abs(sig)[base&tr]
                    cut=np.quantile(absv,q) if q>0 and len(absv)>100 else -1.0
                    sel=base&(np.abs(sig)>cut)
                    for spl in ['train','validate','test']:
                        m=sel&(sub.split.values==spl)
                        if m.sum()<200: continue
                        p=trade_pnl(sig[m], e[m], x[m], inst)
                        mean,lo,hi=day_block_boot(p, sd[m])
                        r=dict(scope=sc,pair=name,k=k,h=h,thr=thr_name,split=spl,n=int(np.isfinite(p).sum()),
                               mean_pt=mean, ci_lo=lo, ci_hi=hi, mean_usd=mean*DOLLARS[inst] if mean==mean else np.nan)
                        if spl=='train':
                            tw=[]
                            for pidx in PERM[sc]:
                                sg=sig[pidx]
                                mm=np.isfinite(sg)&np.isfinite(e)&np.isfinite(x)&(np.abs(sg)>cut)&(sub.split.values==spl)
                                if mm.sum()<100: continue
                                pp=trade_pnl(sg[mm], e[mm], x[mm], inst)
                                tw.append(np.nanmean(pp))
                            r['twin_mean']=float(np.mean(tw)) if tw else np.nan
                            r['twin_sd']=float(np.std(tw,ddof=1)) if len(tw)>1 else np.nan
                            r['edge_over_twin']=r['mean_pt']-r['twin_mean'] if tw else np.nan
                            r['edge_in_twin_sd']=(r['edge_over_twin']/r['twin_sd']) if tw and r['twin_sd']>0 else np.nan
                        rows.append(r)
res=pd.DataFrame(rows)
res.to_csv(f"{OUT}/04_grid.csv", index=False)
tr=res[res.split=='train'].copy()
print("TRAIN cells:",len(tr),"| cells with mean_pt>0:",int((tr.mean_pt>0).sum()))
print("\n=== TRAIN cells sorted by net points, top 12 ===")
print(tr.sort_values('mean_pt',ascending=False).head(12)[['scope','pair','k','h','thr','n','mean_pt','ci_lo','ci_hi','twin_mean','twin_sd','edge_in_twin_sd']].round(4).to_string(index=False))
print("\n=== TRAIN cells whose bootstrap CI excludes zero on the UPSIDE ===")
w=tr[(tr.ci_lo>0)]
print(w[['scope','pair','k','h','thr','n','mean_pt','ci_lo','ci_hi','edge_in_twin_sd']].round(4).to_string(index=False) if len(w) else "  NONE")
