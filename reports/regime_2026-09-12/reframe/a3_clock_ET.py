"""A3. A1+A2 REDONE IN America/New_York, because the first pass was WRONG for half the sample.

★ THE BUG THE FIRST PASS HAD, recorded because it is the kind this desk keeps making: I keyed the
  CME session and the session buckets off FIXED UTC minutes. The CME day is 18:00-17:00 LOCAL, so
  under EST it runs 23:00Z-22:00Z and under EDT 22:00Z-21:00Z. 88 of 240 sessions started an hour
  later than my key assumed and 157 ended an hour later, so 'the US session' silently meant 08:30-
  15:40 ET for part of the year. Every number below is recomputed on the exchange's own clock.

BUCKETS (America/New_York, CME trade date 18:00->17:00):
  ASIA  18:00-02:00   EU 02:00-09:30   US 09:30-16:00 (cash RTH)   LATE 16:00-17:00
ARMS, 1 MNQ lot, $2/pt, 1.25pt friction charged per round trip:
  ONITE  16:00 ET -> 09:30 ET next trade date        INTRA 09:30 -> 16:00 ET
  HOLD24 18:00 ET -> 17:00 ET                        EUONLY 02:00 -> 09:30 ET
"""
import duckdb, numpy as np, pandas as pd
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/reframe"
rng=np.random.default_rng(7); F=1.25; VPP=2.0
con=duckdb.connect()
d=con.execute(f"select ts,close from read_parquet('{OUT}/tape_MNQ_1min.parquet') order by ts").df()
d["et"]=pd.to_datetime(d.ts,unit="s",utc=True).dt.tz_convert("America/New_York")
d["min_et"]=d.et.dt.hour*60+d.et.dt.minute
# CME trade date: bars at/after 18:00 ET belong to the NEXT calendar date
d["tdate"]=np.where(d.min_et>=18*60,(d.et+pd.Timedelta(days=1)).dt.date,d.et.dt.date)
# minutes since 18:00 ET
d["mlin"]=np.where(d.min_et>=18*60,d.min_et-18*60,d.min_et+360)
print(f"tape {len(d)} bars  {d.tdate.min()}..{d.tdate.max()}  trade-dates {d.tdate.nunique()}")
cov=d.groupby("tdate").mlin.agg(["min","max","count"])
print("coverage: mlin min/max/count percentiles\n",cov.describe().round(0).to_string())

# ---- (i) bucket decomposition
d["chg"]=d.close.diff()
d.loc[d.ts.diff()>300,"chg"]=np.nan
def bk(m):  # m = minutes since 18:00 ET
    if m< 8*60:   return "1 ASIA  18:00-02:00 ET"
    if m<15*60+30:return "2 EU    02:00-09:30 ET"
    if m<22*60:   return "3 US    09:30-16:00 ET  <- the desk's window"
    return "4 LATE  16:00-17:00 ET"
d["bk"]=d.mlin.map(bk)
g=d.groupby("bk").chg.agg(net_points="sum",minutes="count",gross_abs=lambda s:s.abs().sum())
g["net_usd_1lot"]=g.net_points*VPP; g["pct_of_movement"]=100*g.gross_abs/g.gross_abs.sum()
print("\n=== WHERE MNQ'S POINTS WERE MADE, 240 CME sessions, exchange clock ===")
print(g.round(1).to_string()); print(f"TOTAL {d.chg.sum():.1f} pt = ${d.chg.sum()*VPP:,.0f} on one lot")
g.round(3).to_csv(f"{OUT}/a3_clock_buckets_ET.csv")
ps=d.pivot_table(index="tdate",columns="bk",values="chg",aggfunc="sum")
print(f"\nper-session, n={len(ps)} trade dates:")
for c in ps.columns:
    v=ps[c].dropna().values; t=v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))
    print(f"  {c:<40} n={len(v):>3} mean {v.mean():>7.2f}pt sd {v.std(ddof=1):>6.1f} t={t:>5.2f}  ${v.mean()*VPP*252:>8,.0f}/yr 1lot")
ps.to_csv(f"{OUT}/a3_session_bucket_points_ET.csv")

# ---- (ii) arms
def at(g,m):
    s=g[g.mlin<=m]
    return np.nan if s.empty else s.close.iloc[-1]
rows=[]
for td,gg in d.groupby("tdate"):
    gg=gg.sort_values("mlin")
    rows.append(dict(tdate=td,o1800=at(gg,1),c1700=at(gg,1380),p1600=at(gg,22*60),
                     p0930=at(gg,15*60+30),p0200=at(gg,8*60)))
s=pd.DataFrame(rows).sort_values("tdate").reset_index(drop=True)
s["p0930_next"]=s.p0930.shift(-1)
A={"HOLD24":s.c1700-s.o1800,"ONITE":s.p0930_next-s.p1600,"INTRA":s.p1600-s.p0930,"EUONLY":s.p0930-s.p0200}
res=pd.DataFrame(A); res["tdate"]=s.tdate
n_before=len(res); res=res.dropna().reset_index(drop=True)
print(f"\nusable trade dates for the arms: {len(res)} of {n_before}   {res.tdate.min()}..{res.tdate.max()}")
res.to_csv(f"{OUT}/a3_session_arm_points_ET.csv",index=False)
def boot(v,n=20000,bl=5):
    v=np.asarray(v); nb=int(np.ceil(len(v)/bl)); out=np.empty(n)
    idx=rng.integers(0,max(1,len(v)-bl),size=(n,nb))
    for i in range(n): out[i]=np.concatenate([v[j:j+bl] for j in idx[i]])[:len(v)].mean()
    return np.percentile(out,[2.5,97.5])
thirds=np.array_split(np.arange(len(res)),3)
print(f"\n{'arm':>7} {'period':>6} {'n':>4} {'gross pt':>9} {'net pt':>8} {'sd':>7} {'t':>6} {'$/yr 1lot':>10} {'dayblock 95% CI $/trade':>26}")
out=[]
for a in A:
    for lab,ix in [("ALL",np.arange(len(res)))]+[(f"P{i+1}",t) for i,t in enumerate(thirds)]:
        v=res[a].values[ix]; net=v-F; t=net.mean()/(net.std(ddof=1)/np.sqrt(len(net)))
        lo,hi=boot(net) if lab=="ALL" else (np.nan,np.nan)
        print(f"{a:>7} {lab:>6} {len(v):>4} {v.mean():>9.2f} {net.mean():>8.2f} {net.std(ddof=1):>7.1f} {t:>6.2f} {net.mean()*VPP*252:>10,.0f}   [{lo*VPP:>9.2f},{hi*VPP:>9.2f}]")
        out.append(dict(arm=a,period=lab,n=len(v),gross_pt=v.mean(),net_pt=net.mean(),sd=net.std(ddof=1),t=t,usd_per_yr_1lot=net.mean()*VPP*252,ci_lo_usd=lo*VPP,ci_hi_usd=hi*VPP))
pd.DataFrame(out).to_csv(f"{OUT}/a3_arms_ET.csv",index=False)
print("\nCONTROLS (each is supposed to lose):")
for a in A:
    v=-res[a].values-F
    print(f"  sign-flipped {a:<7} {v.mean():>8.2f} pt/session net")
print("\nRISK, 1 lot:")
for a in ["ONITE","INTRA","HOLD24"]:
    v=res[a].values-F; eq=np.cumsum(v)*VPP
    print(f"  {a:<7} final ${eq[-1]:>8,.0f}  maxDD ${(np.maximum.accumulate(eq)-eq).max():>7,.0f}  worst day ${v.min()*VPP:>7,.0f}  5th pct ${np.percentile(v,5)*VPP:>7,.0f}  win% {100*(v>0).mean():.0f}")
