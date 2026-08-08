#!/usr/bin/env python3
"""RGV_SHORT rehab v2 — SINGLE-POSITION sequential sim (the honest first-to-fire count).

v1 let the gate re-fire every minute even while a position was open, which STACKED 3
near-identical fires on one fast move (07-31 14:56-58) and inflated the edge. The live
tournament holds ONE position and re-arms only after it EXITS. This sim replays that:
take a fire, reprice its exit on ticks, block new fires until exit_ts, then continue.
Segmented by regime x alignment x time-of-day. Sweeps exit R per regime.

  PYTHONPATH=src .venv/bin/python scripts/rehab_rgv_short_seq.py
"""
from __future__ import annotations
import sys, itertools
from collections import defaultdict
import duckdb
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (Bar, Position, compute_features, efficiency_ratio,
                              gate_reversal_grab, exit_scalp, exit_chandelier_lock)

CAP="/home/alphabot/gazbot7/data/capture.db"; VPP,FEE,CAP_MIN=2.0,1.5,60
LIVE_BASE=dict(ext_min=1.5,turn_atr=0.25,flow_min=None,atr_min=20.0,fast_slope=False,fast_turn=False)
con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
rows=con.execute("""WITH b AS (SELECT (bar_ts-bar_ts%60) m, arg_min(open,bar_ts) o, max(high) h,
      min(low) l, arg_max(close,bar_ts) cl, SUM(volume) v FROM c.bars
      WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1)
      SELECT m,o,h,l,cl,v,strftime(to_timestamp(m),'%m-%d') d FROM b ORDER BY m""").fetchall()
flow=con.execute("""SELECT (ts_ms//60000)*60 m, COALESCE(SUM(CASE WHEN aggressor='buy' THEN size
      WHEN aggressor='sell' THEN -size END),0) net FROM c.ticks WHERE symbol='MNQ' GROUP BY 1""").fetchall()
tape_net={m:n for m,n in flow}
days=defaultdict(list)
for m,o,h,lo,cl,v,d in rows: days[d].append((m,Bar(m,o,h,lo,cl,v)))
# only days with tick coverage
mint=con.execute("SELECT MIN(ts_ms) FROM c.ticks WHERE symbol='MNQ'").fetchone()[0]//1000
lean={d:(bl[-1][1].close-bl[0][1].close) for d,bl in days.items()}
tickc={}
def ticks(m):
    if m in tickc: return tickc[m]
    t=con.execute(f"""SELECT ts_ms,price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={(m+60)*1000}
        AND ts_ms<{(m+60+CAP_MIN*60)*1000} ORDER BY ts_ms""").fetchall(); tickc[m]=t; return t
def rep_scalp(m,atr,tr,sm=1.0):
    t=ticks(m)
    if len(t)<3: return None
    entry=t[0][1]; peak=0.0; xpx=t[-1][1]; xts=t[-1][0]; rs="MAXHOLD"
    for ts,px in t[1:]:
        peak=max(peak,entry-px)
        r=exit_scalp(Position("SHORT",entry,atr,peak),px,target_r=tr,stop_atr_mult=sm)
        if r: xpx,xts,rs=px,ts,r; break
    return entry,(entry-xpx)*VPP-FEE,rs,xts//1000
def rep_chand(m,atr,sk=3.5,lr=6.0,lk=0.5):
    t=ticks(m)
    if len(t)<3: return None
    entry=t[0][1]; peak=0.0; xpx=t[-1][1]; xts=t[-1][0]; rs="MAXHOLD"
    for ts,px in t[1:]:
        peak=max(peak,entry-px)
        if px>=entry+atr: xpx,xts,rs=px,ts,"STOP"; break
        r=exit_chandelier_lock(Position("SHORT",entry,atr,peak),px,start_k=sk,lock_r=lr,lock_k=lk)
        if r: xpx,xts,rs=px,ts,r; break
    return entry,(entry-xpx)*VPP-FEE,rs,xts//1000

def regime(atr,er):
    if atr>=38: return "violent"
    if er>=0.45: return "clean-trend"
    if er>=0.30: return "building"
    if atr<14 or er<0.10: return "dead-chop"
    return "normal-chop"
def align(l):
    return "aligned(DOWN)" if l<=-30 else ("counter(UP)" if l>=30 else "flat")

def sim(base, exit_fn, tag):
    """sequential single-position; returns list of dicts."""
    out=[]
    for d,bl in days.items():
        if bl[-1][0] < mint: continue  # no ticks that day
        bars=[b for _m,b in bl]; busy=-1
        for i in range(len(bars)):
            m=bl[i][0]
            if m<busy or m<mint: continue
            w=bars[max(0,i-59):i+1]
            if len(w)<6: continue
            f=compute_features(w); tn=tape_net.get(m-m%60,0.0)
            e=gate_reversal_grab(f,side="SHORT",tape_net=tn,in_rth=True,**base)
            if e is None: continue
            r=exit_fn(m,f.atr)
            if r is None: continue
            entry,pnl,rs,xts=r
            er=efficiency_ratio(w)
            utc=(m%86400)//60; rth=13*60+30<=utc<20*60
            out.append(dict(d=d,m=m,atr=f.atr,er=er,pnl=pnl,rs=rs,
                            seg=regime(f.atr,er),al=align(lean[d]),
                            tod="US" if rth else "ON",lean=lean[d]))
            busy=xts+1  # re-arm only after the position exits (first-to-fire)
    return out

def summ(ps):
    n=len(ps);
    if not n: return (0,0,0,0)
    return (n,round(sum(ps),0),round(sum(ps)/n,1),round(100*sum(1 for p in ps if p>0)/n))

rep=[];
def P(*a):
    s=" ".join(str(x) for x in a); rep.append(s); print(s)

P("="*88); P("RGV_SHORT rehab v2 — SINGLE-POSITION first-to-fire (honest count)")
P("tick tape from", (con.execute("SELECT strftime(to_timestamp(MIN(ts_ms)/1000),'%m-%d %H:%M') FROM c.ticks WHERE symbol='MNQ'").fetchone()[0]))
P("LIVE base:",LIVE_BASE); P("="*88)

for TR in [1.5,2.0,2.5]:
    f=sim(LIVE_BASE, lambda m,a,tr=TR: rep_scalp(m,a,tr), f"scalp{TR}")
    n,net,ev,w=summ([x['pnl'] for x in f])
    P(f"\n### LIVE base, scalp {TR}R — {n} fires, net {net:+.0f}, ${ev:+.1f}/tr, {w}%w")
    for keyname,keyfn in [("regime",lambda x:x['seg']),("align",lambda x:x['al']),
                          ("regime/align",lambda x:x['seg']+"/"+x['al'])]:
        b=defaultdict(list)
        for x in f: b[keyfn(x)].append(x['pnl'])
        P(f"  by {keyname}:")
        for k in sorted(b):
            nn,nt,ee,ww=summ(b[k]); P(f"     {k:<26} n={nn:<3} net={nt:+.0f} ${ee:+.1f}/tr {ww}%w")

# chandelier on LIVE base
f=sim(LIVE_BASE, rep_chand, "chand")
n,net,ev,w=summ([x['pnl'] for x in f])
P(f"\n### LIVE base, chandelier_lock — {n} fires, net {net:+.0f}, ${ev:+.1f}/tr, {w}%w")
b=defaultdict(list)
for x in f: b[x['seg']+"/"+x['al']].append(x['pnl'])
for k in sorted(b):
    nn,nt,ee,ww=summ(b[k]); P(f"     {k:<26} n={nn:<3} net={nt:+.0f} ${ee:+.1f}/tr {ww}%w")

# per-day (scalp 2R, single-pos) + robustness
f=sim(LIVE_BASE, lambda m,a: rep_scalp(m,a,2.0), "s2")
P(f"\n### PER-DAY (scalp 2R single-pos) + fire detail")
byday=defaultdict(list)
for x in f: byday[x['d']].append(x)
for d in sorted(byday):
    xs=byday[d]; nn,nt,ee,ww=summ([x['pnl'] for x in xs])
    P(f"  {d} lean={lean[d]:+.0f}: n={nn} net={nt:+.0f} {ww}%w  | "+
      " ".join(f"{x['seg'][:4]}/{x['al'][:3]}:{x['pnl']:+.0f}" for x in xs))
allp=[x['pnl'] for x in f]; n,net,ev,w=summ(allp)
P(f"  TOTAL: n={n} net={net:+.0f} ${ev:+.1f}/tr {w}%w")
sp=sorted(allp)
P(f"  strip best1={sum(sp[:-1]):+.0f} best3={sum(sp[:-3]):+.0f} | worst-day-removed(LODO):")
for d in sorted(byday):
    rem=[x['pnl'] for dd in byday if dd!=d for x in byday[dd]]
    P(f"     -{d}: {sum(rem):+.0f}")

# home-regime only, R sweep
P(f"\n### HOME regime (normal-chop+dead-chop+building), R sweep, single-pos")
for TR in [1.0,1.5,2.0,2.5,3.0]:
    f=sim(LIVE_BASE, lambda m,a,tr=TR: rep_scalp(m,a,tr), f"h{TR}")
    home=[x['pnl'] for x in f if x['seg'] in ("normal-chop","dead-chop","building")]
    n,net,ev,w=summ(home); P(f"  scalp {TR}R: n={n} net={net:+.0f} ${ev:+.1f}/tr {w}%w")
f=sim(LIVE_BASE, rep_chand, "hc")
home=[x['pnl'] for x in f if x['seg'] in ("normal-chop","dead-chop","building")]
n,net,ev,w=summ(home); P(f"  chand:     n={n} net={net:+.0f} ${ev:+.1f}/tr {w}%w")
con.close(); P("\nDONE")
