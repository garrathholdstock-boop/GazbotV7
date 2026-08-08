#!/usr/bin/env python3
"""TICK-HONEST rehab reconstruction for capitulation_long (flush-and-flip LONG fader).

Entry is decided EXACTLY as live: completed 1-min bars (MinuteBars(60), the desk's
bar_lookback) -> compute_features for atr/ER + the aggressor-tape footprint
(capitulation_tape, short_s=20/base_s=180) recomputed every 5s -> gate_capitulation.
The EXIT is repriced on the real 250ms trade TICKS (first-touch), each candidate exit.
Single-position, first-to-fire (re-arm only after the open position exits).

Data: data/capture.db  (MNQ 5s bars + aggressor ticks; tick coverage 07-23 22:00 ->
07-31 21:00 UTC). $2/pt, $1.50/RT-contract. Regime-SEGMENTED per operator's 07-31 rule.
"""
from __future__ import annotations
import sqlite3, sys, datetime as dt
import numpy as np
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (Bar, compute_features, gate_capitulation, Position,
                              chandelier_start_k, exit_chandelier, exit_scalp, exit_fixed,
                              efficiency_ratio)
from collections import deque

VPP, FEE = 2.0, 1.5
DB = "/home/alphabot/gazbot7/data/capture.db"

# ---- load ticks into numpy (fast footprint + exit replay) ----
def load():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    trows = c.execute("SELECT ts_ms,price,size,aggressor FROM ticks WHERE symbol='MNQ' ORDER BY ts_ms").fetchall()
    ts = np.array([r[0] for r in trows], dtype=np.int64)
    px = np.array([r[1] for r in trows], dtype=np.float64)
    sz = np.array([r[2] for r in trows], dtype=np.float64)
    ag = np.array([1 if r[3]=="buy" else (-1 if r[3]=="sell" else 0) for r in trows], dtype=np.int8)
    brows = c.execute("SELECT bar_ts,open,high,low,close,volume FROM bars WHERE symbol='MNQ' AND timeframe='5s' ORDER BY bar_ts").fetchall()
    c.close()
    # cumulative sums for O(1) footprint windows
    cum_all = np.concatenate([[0.0], np.cumsum(sz)])
    cum_sell = np.concatenate([[0.0], np.cumsum(np.where(ag==-1, sz, 0.0))])
    cum_buy  = np.concatenate([[0.0], np.cumsum(np.where(ag==1, sz, 0.0))])
    return ts, px, sz, ag, cum_all, cum_sell, cum_buy, brows

TS=PX=SZ=AG=CUM_ALL=CUM_SELL=CUM_BUY=BARS=None
def init():
    global TS,PX,SZ,AG,CUM_ALL,CUM_SELL,CUM_BUY,BARS
    TS,PX,SZ,AG,CUM_ALL,CUM_SELL,CUM_BUY,BARS = load()

def footprint(now_ms, short_s=20, base_s=180):
    lo = now_ms - base_s*1000; short_cut = now_ms - short_s*1000; half_cut = now_ms - (short_s*1000)//2
    i_lo = int(np.searchsorted(TS, lo, "left"))
    i_short = int(np.searchsorted(TS, short_cut, "left"))
    i_half = int(np.searchsorted(TS, half_cut, "left"))
    i_now = int(np.searchsorted(TS, now_ms, "right"))
    if i_now <= i_short:   # no ticks in short window
        return 0.0,0.0,0.0,0.0,False
    base_tot = CUM_ALL[i_short]-CUM_ALL[i_lo]
    sell = CUM_SELL[i_now]-CUM_SELL[i_short]
    buy  = CUM_BUY[i_now]-CUM_BUY[i_short]
    dpx = PX[i_now-1]-PX[i_short]
    half_sell = CUM_SELL[i_now]-CUM_SELL[i_half]
    half_buy  = CUM_BUY[i_now]-CUM_BUY[i_half]
    windows = max(1.0,(base_s-short_s)/short_s)
    return sell, buy, base_tot/windows, dpx, (half_buy>half_sell)

def replay_exit(exit_cfg, entry_px, atr, i_entry):
    """Step ticks from i_entry; return (exit_px, exit_ms, reason)."""
    peak=0.0; k=chandelier_start_k(atr)
    kind=exit_cfg["kind"]
    n=len(TS)
    for j in range(i_entry, n):
        px=PX[j]
        fav = px-entry_px  # LONG
        if fav>peak: peak=fav
        pos=Position("LONG", entry_px, atr, peak)
        if kind=="scalp":
            r=exit_scalp(pos, px, target_r=exit_cfg["r"], stop_atr_mult=1.0)
        elif kind=="chandelier":
            r=(exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
               or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))
        elif kind=="fixed":
            r=exit_fixed(pos, px, stop_pt=exit_cfg["stop"], target_pt=exit_cfg["tgt"])
        else:
            r=None
        if r:
            return px, int(TS[j]), r
        # 60-min max-hold backstop
        if TS[j]-TS[i_entry] > 60*60000:
            return px, int(TS[j]), "MAXHOLD"
    return PX[n-1], int(TS[n-1]), "EOD"

def run_sim(entry_params, exit_cfg, atr_floor=10.0):
    """First-to-fire single-position sim. entry_params: climax_min,dom_min,require_flip."""
    mb=deque(maxlen=60)   # completed 1-min bars
    cur=None
    next_ok=0
    trades=[]
    for (bt,o,h,l,cl,v) in BARS:
        # fold 5s bar -> minute bars
        m=(bt//60)*60
        if cur is None or m>cur["min"]:
            if cur is not None:
                mb.append(Bar(cur["min"],cur["o"],cur["h"],cur["l"],cur["c"],cur["v"]))
            cur={"min":m,"o":o,"h":h,"l":l,"c":cl,"v":v}
        elif m==cur["min"]:
            cur["h"]=max(cur["h"],h); cur["l"]=min(cur["l"],l); cur["c"]=cl; cur["v"]+=v
        now_ms=(bt+5)*1000
        if now_ms<=next_ok: continue
        bars=list(mb)
        if len(bars)<6: continue
        f=compute_features(bars)
        if f.atr < atr_floor: continue
        er=efficiency_ratio(bars)
        cs,cb,cbase,cdpx,cflip=footprint(now_ms)
        e=gate_capitulation(f, cap_sell=cs, cap_buy=cb, cap_base=cbase, cap_dpx=cdpx,
                            cap_flip=cflip, **entry_params)
        if e is None or e.side!="LONG": continue
        # entry = first tick after now_ms
        i_entry=int(np.searchsorted(TS, now_ms, "right"))
        if i_entry>=len(TS)-1: continue
        entry_px=PX[i_entry]
        ex_px,ex_ms,reason=replay_exit(exit_cfg, entry_px, f.atr, i_entry+1)
        pnl=(ex_px-entry_px)*VPP-FEE   # 1 lot base
        trades.append(dict(entry_ms=now_ms, entry_px=float(entry_px), exit_px=float(ex_px),
                           exit_ms=ex_ms, reason=reason, pnl=pnl, atr=f.atr, er=er,
                           net5=f.net_atr_5, net30=f.net30_pt, ext=f.ext_atr))
        next_ok=ex_ms
    return trades

# ---- regime classifier (operator's segmentation) ----
def regime(t):
    atr=t["atr"]; er=t["er"]
    # range-break proxy: |net30| in ATR units
    brk=abs(t["net30"])/atr if atr>0 else 0
    if atr<12 and er<0.20: return "dead-chop"
    if atr>=25 and er<0.30: return "violent-whipsaw"
    if er>=0.50: return "clean-trend"
    if er>=0.30: return "building"
    return "normal-chop"

def tod(t):
    h=dt.datetime.fromtimestamp(t["entry_ms"]/1000, dt.UTC)
    mins=h.hour*60+h.minute
    return "US" if (13*60+30)<=mins<20*60 else "ON"  # US cash 13:30-20:00 UTC else overnight/pre

def summarize(trades, label=""):
    n=len(trades); net=sum(t["pnl"] for t in trades); w=sum(1 for t in trades if t["pnl"]>0)
    pt = net/n if n else 0
    return f"{label:28} n={n:>3} net=${net:>+7.0f} win={100*w/n if n else 0:>3.0f}% $/tr={pt:>+6.1f}"

def day(t): return dt.datetime.fromtimestamp(t["entry_ms"]/1000, dt.UTC).strftime("%m-%d")

def seg_report(trades, keyfn, title):
    from collections import defaultdict
    d=defaultdict(list)
    for t in trades: d[keyfn(t)].append(t)
    print(f"-- {title} --")
    for k in sorted(d):
        print("   "+summarize(d[k], str(k)))

def strip_best(trades, k):
    s=sorted(trades, key=lambda t:t["pnl"], reverse=True)
    rest=s[k:]
    return sum(t["pnl"] for t in rest), len(rest)

def lodo(trades):
    days=sorted(set(day(t) for t in trades))
    out=[]
    for dd in days:
        rest=[t for t in trades if day(t)!=dd]
        out.append((dd, sum(t["pnl"] for t in rest), len(rest)))
    return out

if __name__=="__main__":
    init()
    print(f"ticks {len(TS):,}  5s-bars {len(BARS):,}  coverage "
          f"{dt.datetime.fromtimestamp(TS[0]/1000,dt.UTC)} -> {dt.datetime.fromtimestamp(TS[-1]/1000,dt.UTC)}\n")
    LIVE=dict(climax_min=2.5, dom_min=0.6, require_flip=True)
    LOOSE=dict(climax_min=2.5, dom_min=0.6, require_flip=False)

    print("=== EXIT SWEEP (LIVE entry: climax2.5/dom0.6/flip=True, ATR>=10, single-lot) ===")
    for r in [0.5,1.0,1.5,2.0,2.5,3.0]:
        print(summarize(run_sim(LIVE, dict(kind="scalp",r=r)), f"flip scalp {r}R"))
    print(summarize(run_sim(LIVE, dict(kind="chandelier")), "flip chandelier"))
    print(summarize(run_sim(LIVE, dict(kind="fixed",stop=8,tgt=12)), "flip fixed 8/12"))
    print(summarize(run_sim(LIVE, dict(kind="fixed",stop=6,tgt=9)), "flip fixed 6/9"))

    print("\n=== require_flip FALSE (loose, fade the climax itself) ===")
    for r in [1.0,1.5,2.0,2.5]:
        print(summarize(run_sim(LOOSE, dict(kind="scalp",r=r)), f"loose scalp {r}R"))
    print(summarize(run_sim(LOOSE, dict(kind="chandelier")), "loose chandelier"))

    print("\n=== climax/dom sweep (flip=True, scalp 2R, ATR>=10) ===")
    for cm in [2.0,2.5,3.0,3.5]:
        for dm in [0.6,0.7,0.8]:
            tr=run_sim(dict(climax_min=cm,dom_min=dm,require_flip=True), dict(kind="scalp",r=2.0))
            print(summarize(tr, f"climax{cm}/dom{dm}"))

    print("\n=== ATR floor sweep (LIVE flip, scalp 2R) ===")
    for af in [0,10,14,18,22]:
        print(summarize(run_sim(LIVE, dict(kind="scalp",r=2.0), atr_floor=af), f"ATR>={af}"))

    # ---- pick the reference book: LIVE flip scalp 2R ----
    REF=run_sim(LIVE, dict(kind="scalp",r=2.0))
    print("\n=== REFERENCE BOOK (LIVE flip scalp 2R) — every trade ===")
    for t in sorted(REF, key=lambda x:x["entry_ms"]):
        print(f"   {dt.datetime.fromtimestamp(t['entry_ms']/1000,dt.UTC).strftime('%m-%d %H:%M')} "
              f"{tod(t)} {regime(t):16} atr={t['atr']:4.1f} er={t['er']:.2f} net30={t['net30']:+6.1f} "
              f"{t['reason']:9} ${t['pnl']:+6.1f}")

    print()
    seg_report(REF, regime, "BY REGIME (LIVE flip scalp 2R)")
    seg_report(REF, tod, "BY TIME-OF-DAY")
    seg_report(REF, day, "BY DAY")

    print("\n=== ROBUSTNESS (REF book) ===")
    net=sum(t['pnl'] for t in REF)
    print(f"   full: ${net:+.0f} n={len(REF)}")
    for k in [1,2,3]:
        s,n=strip_best(REF,k); print(f"   strip-best-{k}: ${s:+.0f} (n={n})")
    for dd,s,n in lodo(REF):
        print(f"   LODO drop {dd}: ${s:+.0f} (n={n})")

    print("\n=== FILTER: fade CHOP only (bench building/clean-trend/violent) ===")
    chop=[t for t in REF if regime(t) in ("dead-chop","normal-chop")]
    print("   "+summarize(chop,"chop-only REF-2R"))
    for k in [1,2]:
        s,n=strip_best(chop,k); print(f"   strip-best-{k}: ${s:+.0f} (n={n})")
    seg_report(chop, day, "chop-only BY DAY")

    print("\n=== PER-REGIME R-SWEEP (prove/deny the fader cheat-sheet R guess) ===")
    for r in [0.5,1.0,1.5,2.0,2.5,3.0]:
        tr=run_sim(LIVE, dict(kind="scalp",r=r))
        from collections import defaultdict
        d=defaultdict(list)
        for t in tr: d[regime(t)].append(t)
        parts=[]
        for reg in ["dead-chop","normal-chop","building","clean-trend","violent-whipsaw"]:
            g=d.get(reg,[])
            if g: parts.append(f"{reg[:4]}:${sum(x['pnl'] for x in g):+.0f}(n{len(g)})")
        print(f"   {r}R  "+"  ".join(parts))
