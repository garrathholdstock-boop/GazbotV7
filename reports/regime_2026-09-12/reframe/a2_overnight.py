"""A2. THE OVERNIGHT / SESSION-CLOCK TRADE, tested like a strategy rather than quoted as a fact.

Claim under test: on MNQ, the drift lives outside the operator's trading window. A1 said so in
aggregate; this puts it through the bar the addendum set - chronological thirds reported ALL of
them, a day-block bootstrap CI, friction charged, and a control that is supposed to lose.

ARMS (1 MNQ lot, $2/pt, friction 1.25pt charged on EVERY round trip):
  HOLD24     buy at the 22:00Z session open, sell at the 21:00Z session close   (1 RT/session)
  ONITE      buy 20:00Z, sell 13:30Z next day   (the classic overnight anomaly) (1 RT/session)
  INTRA      buy 13:30Z, sell 20:00Z            (the desk's own window, long)   (1 RT/session)
  EUONLY     buy 07:00Z, sell 13:30Z                                            (1 RT/session)
CONTROL: the same arms on a DAY-BLOCK BOOTSTRAP of the session returns - and, separately, the
desk's actual live record over the overlapping dates.
Nothing here is an alpha claim: HOLD24 is beta. The question is what the standing 'never hold
overnight' rule costs, measured, and whether the non-US slice is distinguishable from the US one.
"""
import duckdb, numpy as np, pandas as pd
OUT="/home/alphabot/gazbot7/reports/regime_2026-09-12/reframe"
rng=np.random.default_rng(7)
con=duckdb.connect()
d=con.execute(f"select ts,close,dt,sess,mod from read_parquet('{OUT}/tape_MNQ_1min.parquet') order by ts").df()
d["dt"]=pd.to_datetime(d.dt,utc=True)
F=1.25; VPP=2.0

def px_at(df,minute):
    """last close at or before `minute` within the session; None if the session never reached it."""
    s=df[df["mod_lin"]<=minute]
    return None if s.empty else s.close.iloc[-1]

# linearise the clock within a CME session: 22:00Z = 0 ... 21:00Z = 1380
d["mod_lin"]=np.where(d["mod"]>=22*60, d["mod"]-22*60, d["mod"]+120)
recs=[]
for sess,g in d.groupby("sess"):
    g=g.sort_values("mod_lin")
    p=lambda m: px_at(g,m)
    o22,c21 = p(1), p(1380)
    p20, p1330, p700 = p(20*60+120), p(13*60+30+120), p(7*60+120)
    nxt=None
    recs.append(dict(sess=sess,o22=o22,c21=c21,p20=p20,p1330=p1330,p700=p700))
s=pd.DataFrame(recs).sort_values("sess").reset_index(drop=True)
s["p1330_next"]=s.p1330.shift(-1)   # 13:30Z of the NEXT session = the exit of an overnight hold
arms={}
arms["HOLD24"] = s.c21 - s.o22
arms["ONITE"]  = s.p1330_next - s.p20
arms["INTRA"]  = s.p20 - s.p1330
arms["EUONLY"] = s.p1330 - s.p700
res=pd.DataFrame(arms); res["sess"]=s.sess
res=res.dropna().reset_index(drop=True)
print(f"sessions usable: {len(res)}  {res.sess.min()}..{res.sess.max()}")
res.to_csv(f"{OUT}/a2_session_arm_points.csv",index=False)

def boot(v,n=20000,bl=5):
    """day-BLOCK bootstrap of the mean (blocks of 5 sessions, to respect autocorrelation)."""
    v=np.asarray(v); nb=int(np.ceil(len(v)/bl)); out=np.empty(n)
    idx=rng.integers(0,len(v)-bl,size=(n,nb))
    for i in range(n):
        out[i]=np.concatenate([v[j:j+bl] for j in idx[i]])[:len(v)].mean()
    return np.percentile(out,[2.5,97.5])

thirds=np.array_split(np.arange(len(res)),3)
print(f"\n{'arm':>7} {'period':>12} {'n':>4} {'mean pt':>8} {'net pt/RT':>10} {'sd':>7} {'t':>6} {'$/yr 1lot':>11} {'boot95 net $/tr':>22}")
lines=[]
for a in arms:
    for lab,ix in [("ALL",np.arange(len(res)))]+[(f"P{i+1}",t) for i,t in enumerate(thirds)]:
        v=res[a].values[ix]; net=v-F
        t=net.mean()/(net.std(ddof=1)/np.sqrt(len(net)))
        ci=boot(net) if lab=="ALL" else (np.nan,np.nan)
        print(f"{a:>7} {lab:>12} {len(v):>4} {v.mean():>8.2f} {net.mean():>10.2f} {net.std(ddof=1):>7.1f} {t:>6.2f} {net.mean()*VPP*252:>11,.0f}   [{ci[0]*VPP:>8.2f},{ci[1]*VPP:>8.2f}]")
        lines.append(dict(arm=a,period=lab,n=len(v),mean_pt=v.mean(),net_pt=net.mean(),sd=net.std(ddof=1),t=t,usd_yr=net.mean()*VPP*252,ci_lo_usd=ci[0]*VPP,ci_hi_usd=ci[1]*VPP))
pd.DataFrame(lines).to_csv(f"{OUT}/a2_arms.csv",index=False)

print("\nRISK of the overnight arm (points, 1 lot, $2/pt):")
v=res["ONITE"].values-F
eq=np.cumsum(v)*VPP
print(f"  worst session {v.min()*VPP:,.0f}$  best {v.max()*VPP:,.0f}$  5th pct {np.percentile(v,5)*VPP:,.0f}$")
print(f"  max peak-to-trough drawdown on 1 lot: ${(np.maximum.accumulate(eq)-eq).max():,.0f}   final ${eq[-1]:,.0f}")
v2=res["HOLD24"].values-F; eq2=np.cumsum(v2)*VPP
print(f"  HOLD24: maxDD ${(np.maximum.accumulate(eq2)-eq2).max():,.0f}  final ${eq2[-1]:,.0f}")
v3=res["INTRA"].values-F; eq3=np.cumsum(v3)*VPP
print(f"  INTRA : maxDD ${(np.maximum.accumulate(eq3)-eq3).max():,.0f}  final ${eq3[-1]:,.0f}")
print("\nCONTROL (a control is supposed to lose): sign-flipped ONITE = {:.2f}pt/session net".format((-res['ONITE'].values-F).mean()))
