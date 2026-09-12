#!/usr/bin/env python3
"""LINE 1, second form: the contemporaneous correlation is 0.45 and RISING. So even with no
lead-lag there could be a tradeable DISLOCATION -- MNQ cheap/rich against what gold is doing,
mean-reverting over the next h minutes.

Spread in DOLLARS (the two contracts have near-identical notional: MNQ ~$2x25,000 = $50k,
MGC ~$10x4,500 = $45k):   S(t) = 2.0*MNQ_close(t) - beta*10.0*MGC_close(t)
beta = OLS slope of MNQ dollar-returns on MGC dollar-returns, estimated on TRAIN ONLY.
z(t) = (S(t) - mean_w(t)) / sd_w(t), both over the trailing w minutes, both ending at t. Causal.
Entry at the OPEN of t+1 in both legs; exit at the OPEN of t+1+h.
Cost: hedged pair = $2.50 (MNQ) + $4.50 (MGC) = $7.00 per round turn. MNQ-only leg = $2.50.
"""
import duckdb, numpy as np, pandas as pd, json, sys
sys.path.insert(0,"/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag")
from harness import day_block_boot
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag"
con=duckdb.connect(config={'memory_limit':'600MB','threads':2})
df=con.execute(f"select ts,sday,q_o,q_c,g_o,g_c,(ts%86400) sec from '{OUT}/panel_1min.parquet' order by ts").df()
sp=json.load(open(f"{OUT}/03_splits.json"))
df['split']=np.where(df.sday<=sp['train'][1],'train',np.where(df.sday<=sp['validate'][1],'validate','test'))
US=(df.sec>=13*3600+30*60)&(df.sec<=20*3600+40*60)
d=df[US].reset_index(drop=True); sd=d.sday.values

s=pd.Series(sd)
dq=(2.0*d.q_c).diff(); dg=(10.0*d.g_c).diff()
same=(s.values==s.shift(1).values); dq[~same]=np.nan; dg[~same]=np.nan
tr=(d.split.values=='train')&np.isfinite(dq)&np.isfinite(dg)
beta=float(np.polyfit(dg[tr],dq[tr],1)[0])
print(f"train beta (MNQ$ per MGC$) = {beta:.4f}  (n={tr.sum()})  R2={np.corrcoef(dg[tr],dq[tr])[0,1]**2:.4f}")

S=2.0*d.q_c.values - beta*10.0*d.g_c.values
Sser=pd.Series(S); grp=Sser.groupby(sd)
COST_PAIR=7.00; COST_MNQ=2.50
rows=[]
for w in [30,60,120]:
    mu=grp.transform(lambda x: x.rolling(w,min_periods=w).mean()).values
    sg=grp.transform(lambda x: x.rolling(w,min_periods=w).std()).values
    z=(S-mu)/sg
    for h in [5,15,30,60]:
        qo=pd.Series(d.q_o.values); go=pd.Series(d.g_o.values); ss=pd.Series(sd)
        def f(x,off):
            v=x.shift(-off).copy(); v[ss.values!=ss.shift(-off).values]=np.nan; return v.values
        q_e,q_x=f(qo,1),f(qo,1+h); g_e,g_x=f(go,1),f(go,1+h)
        for zt in [1.5,2.5]:
            sig=np.where(z<-zt,1.0,np.where(z>zt,-1.0,0.0))   # z<0 => MNQ cheap vs gold => long MNQ
            base=np.isfinite(z)&np.isfinite(q_e)&np.isfinite(q_x)&np.isfinite(g_e)&np.isfinite(g_x)&(sig!=0)
            for spl in ['train','validate','test']:
                m=base&(d.split.values==spl)
                if m.sum()<200: continue
                mnq_leg=sig[m]*2.0*(q_x[m]-q_e[m])
                gld_leg=-sig[m]*beta*10.0*(g_x[m]-g_e[m])
                for nm,p,c in [('hedged_pair',mnq_leg+gld_leg,COST_PAIR),('mnq_only',mnq_leg,COST_MNQ)]:
                    pn=p-c
                    mean,lo,hi=day_block_boot(pn,sd[m],n_boot=3000)
                    rows.append(dict(book=nm,w=w,h=h,z=zt,split=spl,n=int(m.sum()),
                        hit=round(float(np.mean(p>0)),4),usd=round(mean,3),ci_lo=round(lo,2),ci_hi=round(hi,2),
                        gross_usd=round(float(np.nanmean(p)),3)))
R=pd.DataFrame(rows); R.to_csv(f"{OUT}/08_spread.csv",index=False)
pd.set_option('display.width',260)
print("\n=== hedged pair, mean $/round-turn net of $7.00 ===")
print(R[R.book=='hedged_pair'].pivot_table(index=['w','h','z'],columns='split',values='usd').reindex(columns=['train','validate','test']).round(2).to_string())
print("\n=== MNQ-only leg, mean $/round-turn net of $2.50 ===")
print(R[R.book=='mnq_only'].pivot_table(index=['w','h','z'],columns='split',values='usd').reindex(columns=['train','validate','test']).round(2).to_string())
print("\n=== cells whose day-block CI excludes zero on the upside ===")
w=R[R.ci_lo>0]; print(w.to_string(index=False) if len(w) else "  NONE")
print("\ncells tested:",len(R),"| positive on train:",int(((R.split=='train')&(R.usd>0)).sum()),"of",int((R.split=='train').sum()))
