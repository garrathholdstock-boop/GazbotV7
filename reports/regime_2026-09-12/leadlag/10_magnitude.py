#!/usr/bin/env python3
"""LINE 2, the half that is NOT direction. This desk can already forecast MAGNITUDE
(P(60pt move) 9%-77% by ATR and volume). So the honest cross-instrument question is:

    does GOLD's pre-US state improve the forecast of the MNQ US SESSION'S RANGE
    beyond MNQ's own pre-US state?

A = log(MNQ pre-US range) + log(MNQ pre-US volume)     <- incumbent, MNQ's own tape
C = A + log(MGC pre-US range) + log(MGC pre-US volume) <- adds gold
Coefficients fit on TRAIN ONLY; scored by OUT-OF-SAMPLE R^2 on validate and test.
Direction-free, so nothing here is a trade on its own: it is a gate/ATR-floor input.
"""
import pandas as pd, numpy as np, json
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag"
D=pd.read_csv(f"{OUT}/06_daily_features.csv")
D['q_us_rng']=np.nan
import duckdb
con=duckdb.connect(config={'memory_limit':'600MB','threads':2})
rng=con.execute(f"""select sday,
  max(case when (ts%86400) between 13*3600+30*60 and 20*3600+40*60 then q_h end)
 -min(case when (ts%86400) between 13*3600+30*60 and 20*3600+40*60 then q_l end) as q_us_rng,
  max(case when (ts%86400) between 13*3600+30*60 and 20*3600+40*60 then g_h end)
 -min(case when (ts%86400) between 13*3600+30*60 and 20*3600+40*60 then g_l end) as g_us_rng
 from '{OUT}/panel_1min.parquet' group by 1""").df()
D=D.drop(columns=['q_us_rng']).merge(rng,on='sday',how='left')
D=D[(D.q_pre_rng>0)&(D.g_pre_rng>0)&(D.q_us_rng>0)&(D.q_pre_vol>0)&(D.g_pre_vol>0)&(D.g_us_rng>0)].copy()
y=np.log(D.q_us_rng.values)
X={'A':np.column_stack([np.ones(len(D)),np.log(D.q_pre_rng),np.log(D.q_pre_vol)]),
   'C':np.column_stack([np.ones(len(D)),np.log(D.q_pre_rng),np.log(D.q_pre_vol),np.log(D.g_pre_rng),np.log(D.g_pre_vol)]),
   'B':np.column_stack([np.ones(len(D)),np.log(D.g_pre_rng),np.log(D.g_pre_vol)])}
tr=(D.split=='train').values
res=[]
for nm,M in X.items():
    b=np.linalg.lstsq(M[tr],y[tr],rcond=None)[0]
    for spl in ['train','validate','test']:
        m=(D.split==spl).values
        pred=M[m]@b; resid=y[m]-pred
        ybar=y[tr].mean()
        r2=1-np.sum(resid**2)/np.sum((y[m]-ybar)**2)
        res.append(dict(model=nm,split=spl,n=int(m.sum()),oos_r2=round(float(r2),4),
                        rmse_log=round(float(np.sqrt(np.mean(resid**2))),4)))
R=pd.DataFrame(res); R.to_csv(f"{OUT}/10_magnitude.csv",index=False)
print("=== OUT-OF-SAMPLE R^2 of log(MNQ US-session range), coefficients fit on TRAIN only ===")
print(R.pivot_table(index='model',columns='split',values='oos_r2').reindex(columns=['train','validate','test']).to_string())
print()
bC=np.linalg.lstsq(X['C'][tr],y[tr],rcond=None)[0]
print("C coefficients [const, log MNQ pre-range, log MNQ pre-vol, log MGC pre-range, log MGC pre-vol]:")
print(np.round(bC,4))
# paired OOS squared-error test C vs A on validate+test
bA=np.linalg.lstsq(X['A'][tr],y[tr],rcond=None)[0]
oos=~tr
dA=(y[oos]-X['A'][oos]@bA)**2; dC=(y[oos]-X['C'][oos]@bC)**2
diff=dA-dC
print(f"\nPaired OOS squared-error improvement from adding gold (validate+test, n={oos.sum()}): "
      f"mean={diff.mean():.5f}  t={diff.mean()/(diff.std(ddof=1)/np.sqrt(len(diff))):.2f}")
# and the actual desk-usable framing: P(MNQ US range > 60pt)
thr=60.0
print(f"\n=== desk framing: P(MNQ US-session range > {thr:.0f}pt) by GOLD pre-US range quartile (train-defined) ===")
qs=np.quantile(D.g_pre_rng[tr],[.25,.5,.75])
D['gq']=np.digitize(D.g_pre_rng,qs)
print(D.groupby(['split','gq']).apply(lambda g: pd.Series({'n':len(g),'P_gt60':round(float((g.q_us_rng>thr).mean()),3),
     'median_mnq_us_rng':round(float(g.q_us_rng.median()),1)}), include_groups=False).to_string())
print(f"\n=== same, by MNQ's OWN pre-US range quartile (the incumbent) ===")
qs2=np.quantile(D.q_pre_rng[tr],[.25,.5,.75]); D['qq']=np.digitize(D.q_pre_rng,qs2)
print(D.groupby(['split','qq']).apply(lambda g: pd.Series({'n':len(g),'P_gt60':round(float((g.q_us_rng>thr).mean()),3),
     'median_mnq_us_rng':round(float(g.q_us_rng.median()),1)}), include_groups=False).to_string())
