"""VACUUM greenfield graves — reconstruct TWO signals + run the FULL filter battery on each.

Reuses the machinery of trap_reclaim_sweep.py: per-second signed aggressor flow + rolling window,
tick array for tick-honest scalp exits, 5s->1min bars for ER(30)/ATR(14)/net30. READ-ONLY on capture.db.

GATE 1 "Absorption Fade" (gf_full_VACUUM)  best cfg F150/P8/STOP25/TGT90, 15m cap, 15m cooldown.
  LONG  when net60<=-F and disp60>=-P     (heavy 60s SELL flow, price refused to fall -> fade UP)
  SHORT when net60>=+F and disp60<=+P
  reported: n=245, net +$1496, win 44%.

GATE 2 "Trapped-Flow Reversal" (gf_top15_VACUUM)  base W60/F200/H6/STOP25/TGT45, 10m cap, CD=180, trigger ON.
  LONG-loaded  when nf<=-F and disp>=-H ; enter LONG only when price BREAKS ABOVE the window high.
  SHORT-loaded when nf>=+F and disp<=+H ; enter SHORT only when price BREAKS BELOW the window low.
  direction = AGAINST the trapped flow.  reported base: n=89, net -$1040, win 35%.

  .venv/bin/python scripts/grave_vacuum.py
"""
from __future__ import annotations
import numpy as np, pandas as pd, duckdb
CAP="/home/alphabot/gazbot7/data/capture.db"
SINCE,UNTIL="2026-07-19 22:00:00","2026-07-24 21:00:00"
FEE,VPP=5.0,2.0
W=60  # both gates use a 60s window

# ---------------------------------------------------------------- shared data load
def load():
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{SINCE}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{UNTIL}')").fetchone()[0])
    fdf=con.execute(f"""SELECT CAST(ts_ms/1000 AS BIGINT) s, SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net,
        arg_max(price,ts_ms) px FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{hi*1000} GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max())
    flow=np.zeros(s1-s0+1); price=np.full(s1-s0+1,np.nan)
    ix=(fdf.s.values-s0).astype(int); flow[ix]=fdf.net.values; price[ix]=fdf.px.values
    price=pd.Series(price).ffill().values
    nf=np.convolve(flow,np.ones(W),"full")[:len(flow)]                    # trailing 60s signed flow
    disp=np.full(len(price),np.nan); disp[W:]=price[W:]-price[:-W]        # price[t]-price[t-60]
    hi_prior=pd.Series(price).rolling(W,min_periods=1).max().shift(1).values  # window high, prior 60s (excl now)
    lo_prior=pd.Series(price).rolling(W,min_periods=1).min().shift(1).values
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
        if i is None or i<30: return None,None,None
        seg=cls[i-30:i+1]; tot=np.abs(np.diff(seg)).sum()
        er=abs(seg[-1]-seg[0])/tot if tot>0 else 0.0
        atr=float(trr[i-13:i+1].mean()) if i>=14 else None
        net30=float(seg[-1]-seg[0])
        return er,atr,net30
    return dict(s0=s0,s1=s1,flow=flow,price=price,nf=nf,disp=disp,hi_prior=hi_prior,lo_prior=lo_prior,
                tts=tts,tpx=tpx,er_atr=er_atr)

# ---------------------------------------------------------------- tick-honest scalp exit
def make_scalp(tts,tpx,STOP,TGT,CAP_S):
    def scalp(ei,d):
        ep,et,j=tpx[ei],int(tts[ei]),ei+1
        while j<len(tts):
            px,t=tpx[j],int(tts[j]); fav=(px-ep)*d
            if -fav>=STOP: return -STOP*VPP-FEE,"stop"        # stop checked before target (conservative)
            if fav>=TGT: return TGT*VPP-FEE,"tgt"
            if t-et>=CAP_S*1000: return fav*VPP-FEE,"cap"
            j+=1
        return (tpx[-1]-ep)*d*VPP-FEE,"eod"
    return scalp

# ---------------------------------------------------------------- signal engines
def run_gate1(D,F,P,STOP,TGT,CAP_S,COOL):
    s0,s1,nf,price,disp=D["s0"],D["s1"],D["nf"],D["price"],D["disp"]
    tts,tpx,er_atr=D["tts"],D["tpx"],D["er_atr"]
    scalp=make_scalp(tts,tpx,STOP,TGT,CAP_S)
    trades=[]; busy_until=-1
    for s in range(s0+59,s1,60):
        i=s-s0
        if i<W or s<busy_until: continue
        n60,dsp=nf[i],disp[i]
        if np.isnan(dsp): continue
        d=0
        if n60<=-F and dsp>=-P: d=1.0
        elif n60>=F and dsp<=P: d=-1.0
        if d!=0:
            ei=int(np.searchsorted(tts,(s+1)*1000,"left"))
            if ei>=len(tts): break
            pnl,rsn=scalp(ei,d); er,atr,net30=er_atr(int(tts[ei]))
            trades.append(dict(d=d,pnl=pnl,rsn=rsn,er=er,atr=atr,net30=net30,ts=int(tts[ei])))
            busy_until=s+COOL
    return trades

def run_gate2(D,F,H,STOP,TGT,CAP_S,CD):
    s0,s1,nf,price,disp=D["s0"],D["s1"],D["nf"],D["price"],D["disp"]
    hi_prior,lo_prior=D["hi_prior"],D["lo_prior"]
    tts,tpx,er_atr=D["tts"],D["tpx"],D["er_atr"]
    scalp=make_scalp(tts,tpx,STOP,TGT,CAP_S)
    trades=[]; busy_until=-1
    for s in range(s0+59,s1,60):
        i=s-s0
        if i<W or s<busy_until: continue
        n60,dsp,px=nf[i],disp[i],price[i]
        if np.isnan(dsp) or np.isnan(hi_prior[i]) or np.isnan(lo_prior[i]): continue
        d=0
        # LONG-loaded (sellers hammering, price refused to fall) AND break ABOVE window high
        if n60<=-F and dsp>=-H and px>hi_prior[i]: d=1.0
        # SHORT-loaded (buyers hammering, price refused to rise) AND break BELOW window low
        elif n60>=F and dsp<=H and px<lo_prior[i]: d=-1.0
        if d!=0:
            ei=int(np.searchsorted(tts,(s+1)*1000,"left"))
            if ei>=len(tts): break
            pnl,rsn=scalp(ei,d); er,atr,net30=er_atr(int(tts[ei]))
            trades.append(dict(d=d,pnl=pnl,rsn=rsn,er=er,atr=atr,net30=net30,ts=int(tts[ei])))
            busy_until=s+CD
    return trades

# ---------------------------------------------------------------- battery helpers
def st(rows):
    n=len(rows); net=sum(r["pnl"] for r in rows); w=100*sum(1 for r in rows if r["pnl"]>0)/n if n else 0
    return n,net,w
def line(rows):
    n,net,w=st(rows); return f"{n}tr  ${net:+.0f}  ${net/n if n else 0:+.1f}/tr  {w:.0f}%w"

def battery(name,trades,reported):
    print("\n"+"="*78); print(f"  GATE — {name}"); print("="*78)
    # 1 RAW + exit-mix + validation
    n,net,w=st(trades)
    mix={}
    for r in trades: mix[r["rsn"]]=mix.get(r["rsn"],0)+1
    rn,rnet,rw=reported
    print(f"\n[1] RAW   {line(trades)}")
    print(f"    exit-mix: "+"  ".join(f"{k}={v}" for k,v in sorted(mix.items())))
    print(f"    REPORTED: {rn}tr  ${rnet:+.0f}  {rw:.0f}%w")
    dn=n-rn; dnet=net-rnet
    print(f"    VALIDATION: dn={dn:+d} d$={dnet:+.0f}  -> "
          + ("MATCH (±ok)" if abs(dn)<=max(15,0.12*rn) and abs(dnet)<=max(400,0.35*abs(rnet)) else "DIVERGE (note: faithful rebuild can land the other side of a curve-fit knife-edge)"))
    # 2 LONG vs SHORT
    L=[t for t in trades if t["d"]>0]; S=[t for t in trades if t["d"]<0]
    print(f"\n[2] SIDE  LONG  {line(L)}\n          SHORT {line(S)}")
    # 3 ER bands
    have=[t for t in trades if t["er"] is not None]
    print(f"\n[3] ER bands  (looking for a green band / where's the bleed)")
    best_er=None
    for a,b in [(0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,1.01)]:
        g=[t for t in have if a<=t["er"]<b]
        if not g: continue
        n2,net2,w2=st(g); print(f"      ER {a:.1f}-{b:.1f} : {line(g)}")
        if best_er is None or net2>best_er[1]: best_er=(f"{a:.1f}-{b:.1f}",net2,g,a)
    # 4 ATR bands
    ha=[t for t in trades if t["atr"] is not None]
    print(f"\n[4] ATR bands")
    for a,b in [(0,12),(12,16),(16,20),(20,25),(25,999)]:
        g=[t for t in ha if a<=t["atr"]<b]
        if not g: continue
        print(f"      ATR {a}-{b} : {line(g)}")
    # 5 strip-best on the FULL set
    print(f"\n[5] strip-best (fluke test, full set)")
    srt=sorted(t["pnl"] for t in trades)
    for k in [0,1,2,3,5]:
        kept=srt[:len(srt)-k] if k else srt
        print(f"      strip {k}: {len(kept)}tr  ${sum(kept):+.0f}"+("  <- underwater" if sum(kept)<0 else ""))
    # 6 beta vs edge
    core=[t for t in trades if t["net30"] is not None]
    print(f"\n[6] BETA-vs-EDGE  (side x concurrent 30-min trend dir = net30 sign)")
    for side,dv in [("LONG",1.0),("SHORT",-1.0)]:
        g=[t for t in core if t["d"]==dv]
        up=[t for t in g if t["net30"]>0]; dn=[t for t in g if t["net30"]<=0]
        print(f"      {side}: UP-trend {line(up)}  |  DOWN-trend {line(dn)}")
    print(f"      (winning side green in BOTH dirs = edge; green only with-trend = beta)")
    return best_er,have

def hold_at_n(name,D,runner,base_kwargs,fkey,fgrid,best_er,have):
    """[7] hold-at-n: loosen F (grow n) and loosen the ER floor; does any green HOLD or decay to ~50%?"""
    print(f"\n[7] HOLD-AT-N  (loosen trigger to grow n; does profit HOLD or decay to ~50/n-collapse?)")
    print(f"    F-sweep ({fkey}):")
    for f in fgrid:
        kw=dict(base_kwargs); kw[fkey]=f
        tr=runner(D,**kw); print(f"      {fkey}={f:>4}: {line(tr)}")
    # ER-floor sweep on the base set
    print(f"    ER-floor sweep (base set):")
    for fl in [0.0,0.1,0.2,0.3,0.4,0.5]:
        g=[t for t in have if t["er"]>=fl]
        if not g: print(f"      ER>={fl:.1f}: (none)"); continue
        print(f"      ER>={fl:.1f}: {line(g)}")
    if best_er is not None:
        lbl,bnet,bg,ba=best_er
        print(f"    best ER band was {lbl} (${bnet:+.0f}); strip-best on that band:")
        srt=sorted(t["pnl"] for t in bg)
        for k in [0,1,2,3]:
            kept=srt[:len(srt)-k] if k else srt
            print(f"        strip {k}: {len(kept)}tr  ${sum(kept):+.0f}"+("  <- underwater" if sum(kept)<0 else ""))

# ---------------------------------------------------------------- main
def main():
    print("Loading capture.db (READ-ONLY)  window", SINCE, "->", UNTIL)
    D=load()
    print(f"  seconds {D['s0']}..{D['s1']}  ({(D['s1']-D['s0'])/3600:.1f}h)  ticks={len(D['tts']):,}")

    # ===== GATE 1 — Absorption Fade  F150/P8/STOP25/TGT90 =====
    g1=run_gate1(D,F=150,P=8,STOP=25,TGT=90,CAP_S=900,COOL=900)
    best_er1,have1=battery("Absorption Fade  F150/P8/STOP25/TGT90  (15m cap, 15m cd)",g1,(245,1496,44))
    hold_at_n("Absorption Fade",D,run_gate1,
              dict(P=8,STOP=25,TGT=90,CAP_S=900,COOL=900),"F",
              [110,130,140,150,160,180,220,300],best_er1,have1)

    # ===== GATE 2 — Trapped-Flow Reversal  W60/F200/H6/STOP25/TGT45, trigger ON, CD180 =====
    g2=run_gate2(D,F=200,H=6,STOP=25,TGT=45,CAP_S=600,CD=180)
    best_er2,have2=battery("Trapped-Flow Reversal  F200/H6/STOP25/TGT45  (10m cap, cd180, trigger ON)",g2,(89,-1040,35))
    hold_at_n("Trapped-Flow Reversal",D,run_gate2,
              dict(H=6,STOP=25,TGT=45,CAP_S=600,CD=180),"F",
              [100,150,200,250,300,350,450,600],best_er2,have2)

if __name__=="__main__": main()
