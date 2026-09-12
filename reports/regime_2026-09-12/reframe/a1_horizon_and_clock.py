"""A1. Two cheap, decisive measurements on the MNQ lake (240 CME sessions, 2025-09-14..2026-08-18).

(i)  HORIZON vs FRICTION. Friction is paid ONCE per trade and is ~1.25pt ($1.50/RT = 0.75pt, plus
     one 0.25pt tick crossed = 1.00pt; 1.25pt is the desk's stated measured cost). The QUESTION the
     desk has never put a number on: what fraction of the available move does that cost eat at each
     holding period? An edge does not have to get better; the denominator can get bigger.
(ii) WHERE THE INDEX ACTUALLY MOVES. Decompose the 240-session point change into the operator's
     own clock buckets. He is flat 20:40Z->next open by standing rule, and entry-blocked 00-07Z.
     If the drift lives where he is not, that rule is not a safety policy, it is the position.
All numbers in MNQ POINTS; $2.00/pt/contract.
"""
import duckdb, numpy as np, pandas as pd
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/reframe"
con=duckdb.connect()
d=con.execute(f"select * from read_parquet('{OUT}/tape_MNQ_1min.parquet') order by ts").df()
d["dt"]=pd.to_datetime(d.dt,utc=True)
print(f"tape: {len(d)} 1-min bars, {d.sess.nunique()} sessions, {d.dt.min().date()}..{d.dt.max().date()}")
F=1.25
print("\n=== (i) HOLDING HORIZON vs 1.25pt FRICTION  (MNQ points) ===")
print(f"{'horizon':>10} {'n':>7} {'med|move|':>10} {'mean|move|':>11} {'p75':>8} {'fric % of med':>14} {'ann.turns':>10} {'fric/yr $':>10}")
c=d.close.values
rows=[]
for h,lab in [(1,'1 min'),(5,'5 min'),(15,'15 min'),(30,'30 min'),(60,'60 min'),(120,'2 h'),(390,'1 RTH day'),(1380,'1 cal day'),(6900,'1 week')]:
    if h>=len(c): continue
    mv=np.abs(c[h:]-c[:-h])
    med=np.median(mv); mean=mv.mean(); p75=np.percentile(mv,75)
    # annual turns if you held exactly this long over the 23h CME day, 252 days
    turns=252*1380/h
    rows.append((lab,len(mv),med,mean,p75,100*F/med,turns,turns*F*2.0))
    print(f"{lab:>10} {len(mv):>7} {med:>10.2f} {mean:>11.2f} {p75:>8.2f} {100*F/med:>13.1f}% {turns:>10.0f} {turns*F*2.0:>10,.0f}")
pd.DataFrame(rows,columns=["horizon","n","median_abs_move_pt","mean_abs_move_pt","p75_pt","friction_pct_of_median","annual_turns","annual_friction_usd_1lot"]).to_csv(f"{OUT}/a1_horizon.csv",index=False)

print("\n=== (ii) WHERE THE 240 SESSIONS' POINTS WERE MADE (MNQ points, 1 lot) ===")
# bucket every minute bar's close-to-close change by UTC clock
d["chg"]=d.close.diff()
d=d.iloc[1:].copy()
# drop cross-session joins (the 21:00-22:00Z CME halt)
d.loc[d.dt.diff().dt.total_seconds()>300,"chg"]=np.nan
def bucket(m):
    if 22*60<=m or m<7*60: return "ASIA 22:00-07:00Z (desk entry-BLOCKED)"
    if 7*60<=m<13*60+30: return "EU   07:00-13:30Z"
    if 13*60+30<=m<20*60+40: return "US   13:30-20:40Z (desk's window)"
    return "LATE 20:40-21:00Z (flat by rule)"
d["bk"]=d["mod"].map(bucket)
g=d.groupby("bk").chg.agg(["sum","count",lambda s:s.abs().sum()])
g.columns=["net_points","minutes","gross_abs_points"]
g["net_usd_1lot"]=g.net_points*2.0
g["share_of_movement"]=100*g.gross_abs_points/g.gross_abs_points.sum()
print(g.round(1).to_string())
print(f"\nTOTAL net over the 240 sessions: {d.chg.sum():.1f} pt = ${d.chg.sum()*2.0:,.0f} on ONE lot")
g.round(3).to_csv(f"{OUT}/a1_clock_buckets.csv")

# per-session, so we can bootstrap
ps=d.pivot_table(index="sess",columns="bk",values="chg",aggfunc="sum").fillna(0.0)
ps.to_csv(f"{OUT}/a1_session_bucket_points.csv")
print("\nper-session mean / sd / t (day-clustered, n=%d sessions):"%len(ps))
for cc in ps.columns:
    v=ps[cc].values; t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
    print(f"  {cc:<42} mean {v.mean():>7.2f}pt  sd {v.std(ddof=1):>7.2f}  t={t:>5.2f}  ${v.mean()*2.0*252:>9,.0f}/yr 1 lot")
