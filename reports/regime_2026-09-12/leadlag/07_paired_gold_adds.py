#!/usr/bin/env python3
"""LINE 2/3 DECIDING TEST — "does GOLD ADD ANYTHING?"

The only rules that looked alive at session scale were driven by MNQ's OWN pre-US move. So the
cross-instrument question is not "does C make money" but the pre-registered-thinning question
"does C beat A", where
    A = follow MNQ's own pre-US (22:00->13:30Z) move        <- the incumbent / control
    B = follow MGC's own pre-US move                        <- gold alone
    C = follow the risk-on composite  -(MGC_z - MNQ_z)      <- both
Paired, per session, so friction cancels exactly and the pairing removes the market move.
"""
import pandas as pd, numpy as np, json, sys
sys.path.insert(0,"/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag")
from harness import day_block_boot, FRICTION
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag"
D=pd.read_csv(f"{OUT}/06_daily_features.csv")
qsd=(D.q_eu_c-D.q_asia_o)[D.split=='train'].std(); gsd=(D.g_eu_c-D.g_asia_o)[D.split=='train'].std()
A=(D.q_eu_c-D.q_asia_o).values; B=(D.g_eu_c-D.g_asia_o).values
C=-(B/gsd - A/qsd)
H={'us_60m':(D.q_us_60-D.q_us_o).values,'us_120m':(D.q_us_120-D.q_us_o).values,'us_full':(D.q_us_c-D.q_us_o).values}
rows=[]
for hn,hv in H.items():
    ok=np.isfinite(hv)&np.isfinite(A)&np.isfinite(B)
    for spl in ['train','validate','test','POOLED']:
        m=ok&((D.split.values==spl) if spl!='POOLED' else True)
        if m.sum()<25: continue
        pA=np.sign(A[m])*hv[m]-FRICTION['MNQ']; pB=np.sign(B[m])*hv[m]-FRICTION['MNQ']; pC=np.sign(C[m])*hv[m]-FRICTION['MNQ']
        d=pC-pA
        md,lo,hi=day_block_boot(d, D.sday.values[m], n_boot=6000)
        agree=float((np.sign(A[m])==np.sign(C[m])).mean())
        rows.append(dict(horizon=hn,split=spl,n=int(m.sum()),
            A_pt=round(np.nanmean(pA),2),B_pt=round(np.nanmean(pB),2),C_pt=round(np.nanmean(pC),2),
            C_minus_A=round(md,2), ci=f"[{lo:.1f},{hi:.1f}]",
            t_paired=round(md/(np.nanstd(d,ddof=1)/np.sqrt(np.isfinite(d).sum())),2),
            pct_sessions_C_agrees_A=round(agree,3),
            n_disagree=int((np.sign(A[m])!=np.sign(C[m])).sum())))
R=pd.DataFrame(rows); R.to_csv(f"{OUT}/07_paired.csv",index=False)
pd.set_option('display.width',260); print(R.to_string(index=False))

# where they DISAGREE is the only place gold can pay. Score just those sessions.
print("\n=== the sessions where the gold leg FLIPS the MNQ-only call (that is gold's whole claim) ===")
out=[]
for hn,hv in H.items():
    ok=np.isfinite(hv)&np.isfinite(A)&np.isfinite(B)
    for spl in ['train','validate','test','POOLED']:
        m=ok&(np.sign(A)!=np.sign(C))&((D.split.values==spl) if spl!='POOLED' else True)
        if m.sum()<10: continue
        p=np.sign(C[m])*hv[m]-FRICTION['MNQ']
        mean,lo,hi=day_block_boot(p,D.sday.values[m],n_boot=6000)
        out.append(dict(horizon=hn,split=spl,n=int(m.sum()),hit=round(float(np.mean(np.sign(C[m])*hv[m]>0)),3),
                        net_pt=round(mean,2),ci=f"[{lo:.1f},{hi:.1f}]"))
O=pd.DataFrame(out); O.to_csv(f"{OUT}/07_disagree.csv",index=False); print(O.to_string(index=False))
