"""Trap-Reclaim scalp (VACUUM top25 'mirage', F300/S40/T30/W60/RECLAIM6) — apply the filter battery.
Fade heavy trapped flow: heavy SELL flow (nf<=-F) but price reclaiming the 60s-high (close>=hi60-RECLAIM)
= shorts trapped -> LONG; mirror -> SHORT. Scalp TGT30/STOP40, 15-min cap, cooldown. Tick-honest.
RAW + long/short split (the short-beta test) + ER bands + ATR bands (isolate bleed). Reports the split
because the report flagged this as short-beta to a -1316pt week.

  PYTHONPATH=src python scripts/trap_reclaim_sweep.py
"""
from __future__ import annotations
import numpy as np
import duckdb
CAP="/home/alphabot/gazbot7/data/capture.db"
SINCE,UNTIL="2026-07-19 22:00:00","2026-07-24 21:00:00"
FLW,F,STOP,TGT,RECLAIM,CAP_S,COOL=60,300.0,40.0,30.0,6.0,900,60
FEE,VPP=5.0,2.0
def main():
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    fdf=con.execute(f"""SELECT CAST(ts_ms/1000 AS BIGINT) s, SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net,
        arg_max(price,ts_ms) px FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max())
    flow=np.zeros(s1-s0+1); price=np.full(s1-s0+1,np.nan)
    ix=(fdf.s.values-s0).astype(int); flow[ix]=fdf.net.values; price[ix]=fdf.px.values
    price=__import__("pandas").Series(price).ffill().values
    nf=np.convolve(flow,np.ones(FLW),"full")[:len(flow)]                  # trailing 60s flow
    secs=np.arange(s0,s1+1)
    hi60=__import__("pandas").Series(price).rolling(FLW,min_periods=1).max().values
    lo60=__import__("pandas").Series(price).rolling(FLW,min_periods=1).min().values
    tk=con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} ORDER BY ts_ms""").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float)
    bdf=con.execute(f"""WITH b AS (SELECT (bar_ts-bar_ts%60) m, max(high) h, min(low) l, arg_max(close,bar_ts) cl FROM c.bars
        WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={lo-2400} AND bar_ts<{hi} GROUP BY 1) SELECT m,h,l,cl FROM b ORDER BY m""").df()
    con.close()
    mins=bdf.m.values.astype(np.int64); cls,hh,ll=bdf.cl.values.astype(float),bdf.h.values.astype(float),bdf.l.values.astype(float)
    idx={int(m):i for i,m in enumerate(mins)}; trr=np.zeros(len(mins))
    for i in range(1,len(mins)): trr[i]=max(hh[i]-ll[i],abs(hh[i]-cls[i-1]),abs(ll[i]-cls[i-1]))
    def er_atr(ts):
        i=idx.get(int((ts//1000)-((ts//1000)%60)))
        if i is None or i<30: return None,None
        seg=cls[i-30:i+1]; tot=np.abs(np.diff(seg)).sum()
        er=abs(seg[-1]-seg[0])/tot if tot>0 else 0.0
        atr=float(trr[i-13:i+1].mean()) if i>=14 else None
        net30=float(seg[-1]-seg[0])          # signed 30-min move = trend direction
        return er,atr,net30
    def scalp(ei,d):
        ep,et,j=tpx[ei],int(tts[ei]),ei+1
        while j<len(tts):
            px,t=tpx[j],int(tts[j]); fav=(px-ep)*d
            if -fav>=STOP: return -STOP*VPP-FEE
            if fav>=TGT: return TGT*VPP-FEE
            if t-et>=CAP_S*1000: return fav*VPP-FEE
            j+=1
        return (tpx[-1]-ep)*d*VPP-FEE
    trades=[]; busy_until=-1
    for s in range(s0+59, s1, 60):                                # evaluate at each 1-min bar close
        i=s-s0
        if i<0 or i>=len(secs) or s<busy_until: continue
        d=0
        if nf[i]<=-F and price[i]>=hi60[i]-RECLAIM: d=1.0         # sellers trapped, price reclaims high -> LONG
        elif nf[i]>=F and price[i]<=lo60[i]+RECLAIM: d=-1.0       # buyers trapped, price reclaims low -> SHORT
        if d!=0:
            ei=int(np.searchsorted(tts,(s+1)*1000,"left"))
            if ei>=len(tts): break
            pnl=scalp(ei,d); er,atr,net30=er_atr(int(tts[ei]))
            trades.append({"d":d,"pnl":pnl,"er":er,"atr":atr,"ts":int(tts[ei]),"net30":net30})
            busy_until=s+COOL
    def st(rows):
        n=len(rows); net=sum(r["pnl"] for r in rows); w=100*sum(1 for r in rows if r["pnl"]>0)/n if n else 0
        return n,net,w
    n,net,w=st(trades)
    print(f"TRAP-RECLAIM SCALP reconstruction — {n}tr · net ${net:+.0f} · {w:.0f}%w   (report: 274 / +$2110 / 62%)\n")
    L=[t for t in trades if t["d"]>0]; S=[t for t in trades if t["d"]<0]
    for lbl,g in [("LONG",L),("SHORT",S)]:
        gn,gnet,gw=st(g); print(f"  {lbl:>6}: {gn}tr · ${gnet:+.0f} · {gw:.0f}%w  {'<- short beta to the -1316pt week?' if lbl=='SHORT' else ''}")
    print("\n── ER bands (isolate bleed) ──   " + f"{'band':>10}{'tr':>5}{'net$':>8}{'$/tr':>7}{'win%':>6}")
    have=[t for t in trades if t["er"] is not None]
    for a,b in [(0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,1)]:
        g=[t for t in have if a<=t["er"]<b]
        if not g: continue
        gn,gnet,gw=st(g); print(f"  {f'{a:.1f}-{b:.1f}':>26}{gn:>5}${gnet:>+7.0f}${gnet/gn:>+6.1f}{gw:>5.0f}%")
    print("\n── ATR bands (isolate bleed) ──  " + f"{'band':>10}{'tr':>5}{'net$':>8}{'$/tr':>7}{'win%':>6}")
    ha=[t for t in trades if t["atr"] is not None]
    for a,b in [(0,12),(12,16),(16,20),(20,25),(25,99)]:
        g=[t for t in ha if a<=t["atr"]<b]
        if not g: continue
        gn,gnet,gw=st(g); print(f"  {f'{a}-{b}':>26}{gn:>5}${gnet:>+7.0f}${gnet/gn:>+6.1f}{gw:>5.0f}%")
    # ── INTERROGATE the ER>=0.4 sliver ──
    import datetime as _dt
    sl=[t for t in have if t["er"]>=0.4]
    def _s(rows): 
        n=len(rows); net=sum(r["pnl"] for r in rows); w=100*sum(1 for r in rows if r["pnl"]>0)/n if n else 0
        return n,net,w
    n,net,w=_s(sl)
    print(f"\n════ INTERROGATE ER>=0.4 sliver ({n}tr · ${net:+.0f} · {w:.0f}%w) ════")
    print("  the trades:")
    for t in sorted(sl,key=lambda x:x["ts"]):
        tm=_dt.datetime.fromtimestamp(t["ts"]/1000,_dt.UTC).strftime("%m-%d %H:%M")
        print(f"    {tm}  {'LONG ' if t['d']>0 else 'SHORT'}  ER {t['er']:.2f}  ATR {t['atr']:.0f}  ${t['pnl']:+.0f}")
    print("\n  strip-best (fluke test):")
    srt=sorted([t['pnl'] for t in sl])
    for k in [0,1,2,3,5]:
        kept=srt[:len(srt)-k] if k else srt
        print(f"    strip best {k}: {len(kept)}tr · ${sum(kept):+.0f}"+("  <- gone" if sum(kept)<0 else ""))
    print("\n  long/short split:")
    for lbl,g in [("LONG",[t for t in sl if t['d']>0]),("SHORT",[t for t in sl if t['d']<0])]:
        gn,gnet,gw=_s(g); print(f"    {lbl}: {gn}tr · ${gnet:+.0f} · {gw:.0f}%w")
    print("\n  per-day:")
    days={}
    for t in sl:
        dd=_dt.datetime.fromtimestamp(t["ts"]/1000,_dt.UTC).strftime("%m-%d"); days.setdefault(dd,[]).append(t["pnl"])
    for dd in sorted(days): print(f"    {dd}: {len(days[dd])}tr · ${sum(days[dd]):+.0f}")
    print("\n  ER-floor knife-edge (is 0.4 special?):")
    for fl in [0.25,0.30,0.35,0.40,0.45,0.50]:
        g=[t for t in have if t["er"]>=fl]; gn,gnet,gw=_s(g)
        print(f"    ER>={fl:.2f}: {gn}tr · ${gnet:+.0f} · ${gnet/gn if gn else 0:+.1f}/tr · {gw:.0f}%w")
    # ── BETA vs EDGE: are the ER>=0.35 LONG wins across trend directions, or all up-trends? ──
    core=[t for t in have if t["er"]>=0.35 and t["net30"] is not None]
    print("\n  ═══ BETA-vs-EDGE (ER>=0.35 trades, by side x concurrent 30-min trend dir) ═══")
    for side,dv in [("LONG",1.0),("SHORT",-1.0)]:
        g=[t for t in core if t["d"]==dv]
        up=[t for t in g if t["net30"]>0]; dn=[t for t in g if t["net30"]<=0]
        def q(rows): 
            n=len(rows); return f"{n}tr ${sum(r['pnl'] for r in rows):+.0f} {100*sum(1 for r in rows if r['pnl']>0)/n if n else 0:.0f}%w"
        print(f"    {side}: in UP-trend {q(up)}  |  in DOWN-trend {q(dn)}")
    print("    (if the winning side only wins WITH the trend = beta we already get from grind. "
          "if it wins in BOTH trend directions = a real reclaim edge.)")
    print("\n(key test: does ANY ER/ATR band isolate a positive edge that survives on the LONG side too? "
          "if only SHORT is green it's just down-week beta, not an edge. next: strip-best + flip-week. 1wk in-sample.)")
if __name__=="__main__": main()
