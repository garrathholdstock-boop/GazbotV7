#!/usr/bin/env python3
"""LINE 3: SESSION HANDOFFS. Does the Asia block (00-07Z) or the Europe block (07-13Z), in EITHER
instrument, predict the DIRECTION of the MNQ US session?

One trade per session, so no overlap: the honest control is a per-session sign flip, and the
bootstrap is an ordinary session bootstrap (which is the day-block bootstrap at block size 1).

CAUSAL: every feature ends at or before 13:29:59Z close. Entry is the OPEN of the 13:30Z bar.
"""
import duckdb, numpy as np, pandas as pd, json, sys
sys.path.insert(0,"/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag")
from harness import *
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/leadlag"
con=duckdb.connect(config={'memory_limit':'600MB','threads':2})

# --- daily feature table, all boundaries integer-second, integer division only ---
D=con.execute(f"""
with p as (select *, (ts%86400) as sec from '{OUT}/panel_1min.parquet'),
agg as (
 select sday,
  -- ASIA 00:00-06:59Z
  max(case when sec=0        then q_o end)                                as q_asia_o,
  max(case when sec=6*3600+3540 then q_c end)                             as q_asia_c,
  max(case when sec=0        then g_o end)                                as g_asia_o,
  max(case when sec=6*3600+3540 then g_c end)                             as g_asia_c,
  -- EUROPE 07:00-13:29Z
  max(case when sec=7*3600   then q_o end)                                as q_eu_o,
  max(case when sec=13*3600+29*60 then q_c end)                           as q_eu_c,
  max(case when sec=7*3600   then g_o end)                                as g_eu_o,
  max(case when sec=13*3600+29*60 then g_c end)                           as g_eu_c,
  -- US 13:30 -> 20:40Z  (entry OPEN 13:30, exits at 14:30 / 15:30 / 20:40)
  max(case when sec=13*3600+30*60 then q_o end)                           as q_us_o,
  max(case when sec=14*3600+30*60 then q_o end)                           as q_us_60,
  max(case when sec=15*3600+30*60 then q_o end)                           as q_us_120,
  max(case when sec=20*3600+40*60 then q_o end)                           as q_us_c,
  max(case when sec=13*3600+30*60 then g_o end)                           as g_us_o,
  max(case when sec=20*3600+40*60 then g_o end)                           as g_us_c,
  -- realised range of the pre-US part, for the vol-state line of enquiry
  max(case when sec< 13*3600+30*60 then q_h end)-min(case when sec<13*3600+30*60 then q_l end) as q_pre_rng,
  max(case when sec< 13*3600+30*60 then g_h end)-min(case when sec<13*3600+30*60 then g_l end) as g_pre_rng,
  sum(case when sec< 13*3600+30*60 then q_v else 0 end)                   as q_pre_vol,
  sum(case when sec< 13*3600+30*60 then g_v else 0 end)                   as g_pre_vol
 from (select sday, sec, q_o,q_c,q_h,q_l,q_v, g_o,g_c,g_h,g_l,g_v from p) group by sday)
select * from agg order by sday
""").df()
D=D.dropna(subset=['q_us_o','q_us_c','q_asia_o','q_asia_c','q_eu_o','q_eu_c','g_asia_o','g_asia_c','g_eu_o','g_eu_c']).reset_index(drop=True)
sp=json.load(open(f"{OUT}/03_splits.json"))
D['split']=np.where(D.sday<=sp['train'][1],'train',np.where(D.sday<=sp['validate'][1],'validate','test'))
D['date']=pd.to_datetime(D.sday*86400,unit='s').dt.date

F={
 'MNQ_asia' : D.q_asia_c-D.q_asia_o,
 'MNQ_eu'   : D.q_eu_c  -D.q_eu_o,
 'MNQ_pre'  : D.q_eu_c  -D.q_asia_o,
 'MGC_asia' : D.g_asia_c-D.g_asia_o,
 'MGC_eu'   : D.g_eu_c  -D.g_eu_o,
 'MGC_pre'  : D.g_eu_c  -D.g_asia_o,
 # risk-on/risk-off proxy: gold up while nasdaq down = risk-off. z-scored by each leg's own
 # train-period sd so the difference is dimensionless.
}
qsd=(D.q_eu_c-D.q_asia_o)[D.split=='train'].std(); gsd=(D.g_eu_c-D.g_asia_o)[D.split=='train'].std()
F['RISKOFF_pre']= -((D.g_eu_c-D.g_asia_o)/gsd - (D.q_eu_c-D.q_asia_o)/qsd)   # +ve = risk-ON
HOR={'us_60m':(D.q_us_60-D.q_us_o),'us_120m':(D.q_us_120-D.q_us_o),'us_full':(D.q_us_c-D.q_us_o)}

rng=np.random.default_rng(5)
rows=[]
for fn,fv in F.items():
    for hn,hv in HOR.items():
        for side,mult in [('follow',1.0),('fade',-1.0)]:
            for spl in ['train','validate','test']:
                m=(D.split==spl).values & np.isfinite(fv.values) & np.isfinite(hv.values) & (np.sign(fv.values)!=0)
                if m.sum()<25: continue
                pnl = mult*np.sign(fv.values[m])*hv.values[m] - FRICTION['MNQ']
                mean,lo,hi=day_block_boot(pnl, D.sday.values[m], n_boot=4000)
                # per-session sign-flip control (exact for a 1-trade-per-day rule)
                p_long=float((mult*np.sign(fv.values[m])>0).mean())
                fl=[float(np.mean(np.where(rng.random(m.sum())<p_long,1,-1)*hv.values[m]-FRICTION['MNQ'])) for _ in range(500)]
                rows.append(dict(feature=fn,horizon=hn,side=side,split=spl,n=int(m.sum()),
                    hit=round(float(np.mean(mult*np.sign(fv.values[m])*hv.values[m]>0)),4),
                    net_pt=round(mean,3), ci_lo=round(lo,2), ci_hi=round(hi,2),
                    flip_mean=round(float(np.mean(fl)),3), flip_sd=round(float(np.std(fl,ddof=1)),3),
                    sd_units=round((mean-float(np.mean(fl)))/float(np.std(fl,ddof=1)),2),
                    net_usd=round(mean*2.0,2)))
R=pd.DataFrame(rows); R.to_csv(f"{OUT}/06_handoff.csv",index=False)
D.to_csv(f"{OUT}/06_daily_features.csv",index=False)
pd.set_option('display.width',250)
print("sessions:",len(D), D.split.value_counts().to_dict())
print("\n=== FOLLOW rules only (fade is the mirror), all three splits ===")
print(R[R.side=='follow'].pivot_table(index=['feature','horizon'],columns='split',values=['hit','net_pt'])
        .reindex(columns=['train','validate','test'],level=1).round(3).to_string())
print("\n=== any cell whose 95% session-bootstrap CI excludes zero ===")
w=R[(R.ci_lo>0)]
print(w.to_string(index=False) if len(w) else "  NONE")
