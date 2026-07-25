"""Unified V5-archive + V7-capture MNQ tape loader for FULL-WINDOW backtests (07-05..07-24, ~3wk).
Stitches ticks.db.trade_tick [start, cutover) UNION capture.db.ticks [cutover, end], cutover = the first
capture.db tick (~07-15), so no double-count. Provides per-second flow+price, trailing-W flow (nf),
60s hi/lo, the raw tick array (for tick-honest exits), and 1-min OHLC -> ER(30)/ATR(14)/net30 per min.
Plus a shared battery() so every lead gets the IDENTICAL filter suite.

  import sys; sys.path.insert(0,'/home/alphabot/gazbot7/scripts'); import archive_data as A
  D = A.load()          # D.secs, D.flow, D.price, D.nf, D.hi60, D.lo60, D.tts, D.tpx, D.er_for, D.atr_for, D.net30_for
  A.battery(trades)     # trades = list of {pnl,d,er,atr,net30,ts}
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import duckdb
from types import SimpleNamespace
TICKS="/home/alphabot/alphabot2/data/ticks.db"; CAP="/home/alphabot/gazbot7/data/capture.db"

def load(since="2026-07-05 22:00:00", until="2026-07-24 21:00:00", flw=60):
    con=duckdb.connect(); con.execute(f"ATTACH '{TICKS}' AS a (TYPE sqlite, READ_ONLY)"); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    lo=int(con.execute(f"SELECT epoch(TIMESTAMP '{since}')").fetchone()[0]); hi=int(con.execute(f"SELECT epoch(TIMESTAMP '{until}')").fetchone()[0])
    cut=int(con.execute("SELECT min(ts_ms) FROM c.ticks WHERE symbol='MNQ'").fetchone()[0])  # ms
    con.execute(f"""CREATE TABLE u AS
      SELECT ts_ms, price, size, aggressor FROM a.trade_tick WHERE symbol='MNQ' AND ts_ms>={lo*1000} AND ts_ms<{cut}
      UNION ALL
      SELECT ts_ms, price, size, aggressor FROM c.ticks WHERE symbol='MNQ' AND ts_ms>={cut} AND ts_ms<{hi*1000}""")
    n=con.execute("SELECT COUNT(*), min(ts_ms), max(ts_ms) FROM u").fetchone()
    fdf=con.execute("""SELECT CAST(ts_ms/1000 AS BIGINT) s,
        SUM(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) net, arg_max(price,ts_ms) px
        FROM u GROUP BY s ORDER BY s""").df()
    s0,s1=int(fdf.s.min()),int(fdf.s.max())
    flow=np.zeros(s1-s0+1); price=np.full(s1-s0+1,np.nan); ix=(fdf.s.values-s0).astype(int)
    flow[ix]=fdf.net.values; price[ix]=fdf.px.values; price=pd.Series(price).ffill().bfill().values
    nf=np.convolve(flow,np.ones(flw),"full")[:len(flow)]
    hi60=pd.Series(price).rolling(flw,min_periods=1).max().values; lo60=pd.Series(price).rolling(flw,min_periods=1).min().values
    tk=con.execute("SELECT ts_ms, price FROM u ORDER BY ts_ms").df()
    tts,tpx=tk.ts_ms.values.astype(np.int64),tk.price.values.astype(float)
    b=con.execute("""SELECT (CAST(ts_ms/1000 AS BIGINT)-CAST(ts_ms/1000 AS BIGINT)%60) m,
        arg_min(price,ts_ms) o, max(price) h, min(price) l, arg_max(price,ts_ms) cl, COUNT(*) v
        FROM u GROUP BY 1 ORDER BY 1""").df()
    con.close()
    mins=b.m.values.astype(np.int64); cls=b.cl.values.astype(float); hh=b.h.values.astype(float); ll=b.l.values.astype(float); vv=b.v.values.astype(float)
    idx={int(m):i for i,m in enumerate(mins)}; trr=np.zeros(len(mins))
    for i in range(1,len(mins)): trr[i]=max(hh[i]-ll[i],abs(hh[i]-cls[i-1]),abs(ll[i]-cls[i-1]))
    er_at,atr_at,net30_at={},{},{}
    for i in range(len(mins)):
        if i>=30:
            seg=cls[i-30:i+1]; tot=np.abs(np.diff(seg)).sum()
            er_at[int(mins[i])]=abs(seg[-1]-seg[0])/tot if tot>0 else 0.0; net30_at[int(mins[i])]=float(seg[-1]-seg[0])
        if i>=14: atr_at[int(mins[i])]=float(trr[i-13:i+1].mean())
    def _m(ts): return int((ts//1000)-((ts//1000)%60))
    D=SimpleNamespace(s0=s0,s1=s1,secs=np.arange(s0,s1+1),flow=flow,price=price,nf=nf,hi60=hi60,lo60=lo60,
        tts=tts,tpx=tpx,mins=mins,cls=cls,hh=hh,ll=ll,vv=vv,idx=idx,
        er_for=lambda ts:er_at.get(_m(ts)),atr_for=lambda ts:atr_at.get(_m(ts)),net30_for=lambda ts:net30_at.get(_m(ts)),
        n_ticks=n[0], span=(str(pd.to_datetime(n[1],unit='ms')),str(pd.to_datetime(n[2],unit='ms'))),
        cutover=str(pd.to_datetime(cut,unit='ms')))
    return D

def _st(rows):
    n=len(rows); net=sum(r["pnl"] for r in rows); w=100*sum(1 for r in rows if r["pnl"]>0)/n if n else 0
    return n,net,w

def battery(trades, label="gate"):
    """The identical filter suite: RAW, long/short, ER/ATR bands, strip-best, beta-vs-edge."""
    n,net,w=_st(trades)
    print(f"── {label}: RAW {n}tr ${net:+.0f} {w:.0f}%w")
    for lbl,g in [("LONG",[t for t in trades if t.get('d',1)>0]),("SHORT",[t for t in trades if t.get('d',1)<0])]:
        gn,gnet,gw=_st(g); print(f"     {lbl}: {gn}tr ${gnet:+.0f} {gw:.0f}%w")
    have=[t for t in trades if t.get("er") is not None]
    print("   ER bands:", " ".join(f"[{a:.1f}-{b:.1f}]${_st([t for t in have if a<=t['er']<b])[1]:+.0f}/{_st([t for t in have if a<=t['er']<b])[0]}"
        for a,b in [(0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,9)]))
    ha=[t for t in trades if t.get("atr") is not None]
    print("   ATR bands:", " ".join(f"[{a}-{b}]${_st([t for t in ha if a<=t['atr']<b])[1]:+.0f}/{_st([t for t in ha if a<=t['atr']<b])[0]}"
        for a,b in [(0,12),(12,16),(16,20),(20,25),(25,99)]))
    srt=sorted(t["pnl"] for t in trades)
    print("   strip-best:", " ".join(f"s{k}:${sum(srt[:len(srt)-k] if k else srt):+.0f}" for k in [0,1,2,3,5]))
    core=[t for t in have if t.get("net30") is not None and t["er"]>=0.35]
    for side,dv in [("LONG",1.0),("SHORT",-1.0)]:
        g=[t for t in core if t.get('d',1)==dv]; up=[t for t in g if t["net30"]>0]; dn=[t for t in g if t["net30"]<=0]
        print(f"   beta ER>=.35 {side}: UP {_st(up)[0]}tr ${_st(up)[1]:+.0f} {_st(up)[2]:.0f}%  DOWN {_st(dn)[0]}tr ${_st(dn)[1]:+.0f} {_st(dn)[2]:.0f}%")
