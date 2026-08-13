"""Trap-reclaim LONG — OUT-OF-SAMPLE validation on the V5 archive (ticks.db, 07-05..07-17), a separate
fortnight from the original 07-19..07-24 test. Same signal (F300/RECLAIM6, ER>=0.35, LONG), same
tick-honest scalp exit (TGT30/STOP40, 15min cap). The counter-trend (DOWN-trend) long reclaim was 3/3
in the original week; does it HOLD on a different 2 weeks with more instances? Bars derived from the
trade ticks. Reports the long side split by concurrent 30-min trend direction (the beta-vs-edge test).

  PYTHONPATH=src python scripts/trap_reclaim_oos.py
"""
from __future__ import annotations
import numpy as np
import duckdb
import pandas as pd
TDB="/home/alphabot/alphabot2/data/ticks.db"
FLW,F,STOP,TGT,RECLAIM,CAP_S,COOL,ERG=60,300.0,40.0,30.0,6.0,900,60,0.35
FEE, VPP = 1.50, 2.0   # ★2026-08-13 COST FIX — was FEE,VPP=5.0,2.0. $5.00 is 3.3x the real
# $1.50 commission. An over-charged fee never looks wrong: it silently kills marginal edges and
# reports a confident NULL. Any conclusion this script produced before today used $5/RT — RE-RUN IT.
def main():
    con=duckdb.connect(); con.execute(f"ATTACH '{TDB}' AS a (TYPE sqlite, READ_ONLY)")
    span=con.execute("SELECT min(ts_ms),max(ts_ms),COUNT(*) FROM a.trade_tick WHERE symbol='MNQ'").fetchone()
    lo,hi=int(span[0]//1000),int(span[1]//1000)
    print(f"OOS window: {pd.to_datetime(lo,unit='s')} -> {pd.to_datetime(hi,unit='s')} ({span[2]:,} MNQ trade ticks)\n")
    # per-second flow + last price
    fdf=con.execute("""SELECT CAST(ts_ms/1000 AS BIGINT) s,
        SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net,
        arg_max(price,ts_ms) px FROM a.trade_tick WHERE symbol='MNQ' GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max())
    flow=np.zeros(s1-s0+1); price=np.full(s1-s0+1,np.nan); ix=(fdf.s.values-s0).astype(int)
    flow[ix]=fdf.net.values; price[ix]=fdf.px.values; price=pd.Series(price).ffill().bfill().values
    nf=np.convolve(flow,np.ones(FLW),"full")[:len(flow)]; secs=np.arange(s0,s1+1)
    hi60=pd.Series(price).rolling(FLW,min_periods=1).max().values; lo60=pd.Series(price).rolling(FLW,min_periods=1).min().values
    # tick array for exits
    tk=con.execute("SELECT ts_ms, price FROM a.trade_tick WHERE symbol='MNQ' ORDER BY ts_ms").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float)
    # 1-min OHLC bars from trade ticks -> ER(30) + ATR(14) + net30
    b=con.execute("""SELECT (CAST(ts_ms/1000 AS BIGINT) - CAST(ts_ms/1000 AS BIGINT)%60) m,
        arg_min(price,ts_ms) o, max(price) h, min(price) l, arg_max(price,ts_ms) cl
        FROM a.trade_tick WHERE symbol='MNQ' GROUP BY 1 ORDER BY 1""").df()
    con.close()
    mins=b.m.values.astype(np.int64); cls=b.cl.values.astype(float); hh=b.h.values.astype(float); ll=b.l.values.astype(float)
    idx={int(m):i for i,m in enumerate(mins)}; trr=np.zeros(len(mins))
    for i in range(1,len(mins)): trr[i]=max(hh[i]-ll[i],abs(hh[i]-cls[i-1]),abs(ll[i]-cls[i-1]))
    def er_net(ts):
        i=idx.get(int((ts//1000)-((ts//1000)%60)))
        if i is None or i<30: return None,None,None
        seg=cls[i-30:i+1]; tot=np.abs(np.diff(seg)).sum()
        er=abs(seg[-1]-seg[0])/tot if tot>0 else 0.0
        atr=float(trr[i-13:i+1].mean()) if i>=14 else None
        return er,atr,float(seg[-1]-seg[0])
    def scalp(ei,d):
        ep,et,j=tpx[ei],int(tts[ei]),ei+1
        while j<len(tts):
            px,t=tpx[j],int(tts[j]); fav=(px-ep)*d
            if -fav>=STOP: return -STOP*VPP-FEE
            if fav>=TGT: return TGT*VPP-FEE
            if t-et>=CAP_S*1000: return fav*VPP-FEE
            j+=1
        return (tpx[-1]-ep)*d*VPP-FEE
    L=[]; busy=-1
    for s in range(s0+59,s1,60):
        i=s-s0
        if i<0 or i>=len(secs) or s<busy: continue
        # LONG only: sellers trapped (heavy sell flow) + price reclaims 60s high
        if nf[i]<=-F and price[i]>=hi60[i]-RECLAIM:
            ei=int(np.searchsorted(tts,(s+1)*1000,"left"))
            if ei>=len(tts): break
            er,atr,net30=er_net(int(tts[ei]))
            if er is not None and er>=ERG:
                L.append({"pnl":scalp(ei,1.0),"net30":net30,"er":er})
            busy=s+COOL
    def q(rows): 
        n=len(rows); return f"{n}tr ${sum(r['pnl'] for r in rows):+.0f} {100*sum(1 for r in rows if r['pnl']>0)/n if n else 0:.0f}%w"
    up=[t for t in L if t["net30"]>0]; dn=[t for t in L if t["net30"]<=0]
    print(f"TRAP-RECLAIM LONG, ER>={ERG}, OUT-OF-SAMPLE (F={F:.0f}):")
    print(f"  ALL LONG:        {q(L)}")
    print(f"  in UP-trend:     {q(up)}   (grind beta)")
    print(f"  in DOWN-trend:   {q(dn)}   <<< the counter-trend reclaim — was 3/3 +$165 in the original week")
    print("\n  strip-best on the counter-trend (down-trend) longs:")
    srt=sorted([t['pnl'] for t in dn])
    for k in [0,1,2,3,5]:
        kept=srt[:len(srt)-k] if k else srt
        print(f"    strip {k}: {len(kept)}tr ${sum(kept):+.0f}")
    print("\n(HOLD test: if DOWN-trend longs win ~65%+ over this SEPARATE fortnight with real n = the "
          "reclaim edge is REAL (my earlier F-loosen kill was unfair). ~50% = the 3/3 was luck. OOS = honest.)")
if __name__=="__main__": main()
