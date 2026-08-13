"""Does the counter-trend LONG reclaim edge HOLD at real n? The ER>=0.35 long won 3/3 in down-trends
(the only non-beta part). It's rare at F=300. Loosen the flow threshold F to generate MORE counter-
trend long-reclaim instances and test whether "trapped-seller reclaim LONG, against a DOWN-trend,
ER>=0.35" still wins ~65%+. Holds at n=20+ = real edge to shadow; decays to 50% = the 3/3 was luck.

Reports, per F: the ER>=0.35 LONG trades split by trend dir; focus = DOWN-trend (counter-trend) longs.

  PYTHONPATH=src python scripts/trap_reclaim_ct.py
"""
from __future__ import annotations
import numpy as np
import duckdb
import pandas as pd
CAP="/home/alphabot/gazbot7/data/capture.db"
SINCE,UNTIL="2026-07-19 22:00:00","2026-07-24 21:00:00"
FLW,STOP,TGT,RECLAIM,CAP_S,COOL,ERG=60,40.0,30.0,6.0,900,60,0.35
FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE,VPP=5.0,2.0. $5.00 is 3.3x the real
# $1.50 commission. An over-charged fee never looks wrong: it silently kills marginal edges and
# reports a confident NULL. Any conclusion this script produced before today used $5/RT — RE-RUN IT.
FS=[120,150,200,250,300]
def main():
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    fdf=con.execute(f"""SELECT CAST(ts_ms/1000 AS BIGINT) s, SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net,
        arg_max(price,ts_ms) px FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max())
    flow=np.zeros(s1-s0+1); price=np.full(s1-s0+1,np.nan); ix=(fdf.s.values-s0).astype(int)
    flow[ix]=fdf.net.values; price[ix]=fdf.px.values; price=pd.Series(price).ffill().values
    nf=np.convolve(flow,np.ones(FLW),"full")[:len(flow)]; secs=np.arange(s0,s1+1)
    hi60=pd.Series(price).rolling(FLW,min_periods=1).max().values; lo60=pd.Series(price).rolling(FLW,min_periods=1).min().values
    tk=con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float)
    bdf=con.execute(f"""WITH b AS (SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo-2400} AND bar_ts<{hi} GROUP BY 1) SELECT m,cl FROM b ORDER BY m""").df()
    con.close()
    mins=bdf.m.values.astype(np.int64); cls=bdf.cl.values.astype(float); idx={int(m):i for i,m in enumerate(mins)}
    def er_net(ts):
        i=idx.get(int((ts//1000)-((ts//1000)%60)))
        if i is None or i<30: return None,None
        seg=cls[i-30:i+1]; tot=np.abs(np.diff(seg)).sum()
        return (abs(seg[-1]-seg[0])/tot if tot>0 else 0.0), float(seg[-1]-seg[0])
    def scalp(ei,d):
        ep,et,j=tpx[ei],int(tts[ei]),ei+1
        while j<len(tts):
            px,t=tpx[j],int(tts[j]); fav=(px-ep)*d
            if -fav>=STOP: return -STOP*VPP-FEE
            if fav>=TGT: return TGT*VPP-FEE
            if t-et>=CAP_S*1000: return fav*VPP-FEE
            j+=1
        return (tpx[-1]-ep)*d*VPP-FEE
    print(f"COUNTER-TREND LONG RECLAIM — hold-at-n test (ER>={ERG}, LONG only, by trend dir)\n")
    print(f"  {'F':>5}{'LONG total':>12}{'in UP-trend':>22}{'in DOWN-trend (counter)':>26}")
    for Fth in FS:
        L=[]; busy=-1
        for s in range(s0+59,s1,60):
            i=s-s0
            if i<0 or i>=len(secs) or s<busy: continue
            d=0
            if nf[i]<=-Fth and price[i]>=hi60[i]-RECLAIM: d=1.0
            elif nf[i]>=Fth and price[i]<=lo60[i]+RECLAIM: d=-1.0
            if d!=0:
                ei=int(np.searchsorted(tts,(s+1)*1000,"left"))
                if ei>=len(tts): break
                er,net30=er_net(int(tts[ei]))
                if d>0 and er is not None and er>=ERG:
                    L.append((scalp(ei,d),net30))
                busy=s+COOL
        up=[p for p,nm in L if nm>0]; dn=[p for p,nm in L if nm<=0]
        def q(a): 
            return f"{len(a)}tr ${sum(a):+.0f} {100*sum(1 for x in a if x>0)/len(a) if a else 0:.0f}%w"
        print(f"  {Fth:>5}{len(L):>12}{q(up):>22}{q(dn):>26}")
    print("\n(watch the DOWN-trend (counter-trend) column as F loosens & n grows: win% holding ~65%+ = real "
          "reclaim edge; sliding to ~50% = the 3/3 was luck. ⚠ 1wk in-sample.)")
if __name__=="__main__": main()
