#!/usr/bin/env python3
"""WIDE lock-chandelier lock_r SWEEP (operator 2026-07-29: "$180→$59 is terrible, at $180 it should
bite in hard"). The live wide exit locks tight only at lock_r=6R — most wins peak below that and give
back the full 3.5xATR trail. This reprices the ALIGNED (wide-mode) faithful shadow SHORT entries over
the FULL tick path (not the 120s shadow cap) under exit_chandelier_lock with varying lock_r, to find
the threshold that banks the medium wins without shaking out the monsters. + native 1-ATR stop.
Fees $1.50/RT, $2/pt.  PYTHONPATH=src .venv/bin/python scripts/lockr_giveback_sweep.py
"""
from __future__ import annotations
import datetime as dt, sys
from collections import namedtuple
import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr
from gazbot7.slot_strategy import SlotStrategy
from gazbot7.deciders import Position, efficiency_ratio, exit_chandelier_lock, exit_scalp

CAP="/home/alphabot/gazbot7/data/capture.db"; SH="/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE, MAXH = 2.0, 1.50, 120*60
Bar=namedtuple("Bar","close")
START_K = 3.5
# (lock_r, lock_k) candidates — vary WHEN it locks and HOW tight after. Current live = (6.0, 0.5).
CONFIGS = [(6.0,0.5),(4.0,1.5),(4.0,1.0),(3.0,1.5),(3.0,2.0),(5.0,1.0),(2.5,2.0),(3.0,1.0)]


def ride(entry, atr, lock_r, lock_k, ticks):
    peak = 0.0
    for ts, px in ticks:
        fav = entry - px
        peak = max(peak, fav)
        pos = Position("SHORT", entry, atr, peak)
        if exit_chandelier_lock(pos, px, start_k=START_K, lock_r=lock_r, lock_k=lock_k):
            return (entry-px)*VPP - FEE, peak
        if exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0):   # native 1-ATR stop
            return (entry-px)*VPP - FEE, peak
    return (entry-ticks[-1][1])*VPP - FEE, peak


def main():
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)"); con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    rows=con.execute("""SELECT CAST(entry_ts AS BIGINT) t0, entry_price FROM s.shadow_trades
        WHERE strategy='exhaustion_rev' AND side='SHORT' AND exit_price IS NOT NULL ORDER BY entry_ts""").fetchall()
    daybars={}
    def bars_upto(t0):
        s=dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0,dt.UTC)); ds=int(dt.datetime.fromisoformat(s).timestamp() if isinstance(s,str) else s.timestamp())
        if ds not in daybars:
            daybars[ds]=con.execute(f"SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1").fetchall()
        return daybars[ds]
    # aligned (wide-mode) subset only
    fires=[]
    for (t0, ep) in rows:
        rws=bars_upto(t0); atrctx=[r for r in rws if t0-1800<=r[0]<=t0]
        if len(atrctx)<6: continue
        atr=sum(r[2]-r[3] for r in atrctx)/len(atrctx)
        bars=[Bar(cl) for m,cl,hi,lo in rws if m<=t0]
        if len(bars)<6 or SlotStrategy._regime_mode("SHORT",bars)!="wide" or atr<=0: continue
        tk=con.execute(f"SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>{t0*1000} AND ts_ms<={ (t0+MAXH)*1000} ORDER BY ts_ms").fetchall()
        if len(tk)>=2: fires.append((ep, atr, tk))
    con.close()
    # how many trades peaked in the "usual big run" $120-180 band, and 100+?
    peaks_all = []
    for (ep, atr, tk) in fires:
        _, pk = ride(ep, atr, 6.0, 0.5, tk); peaks_all.append(pk*VPP)
    n_big = sum(1 for x in peaks_all if x >= 100)
    print(f"\nWIDE lock-chandelier config sweep — {len(fires)} ALIGNED shadow SHORT entries, full-path reprice")
    print(f"(start_k {START_K}; {n_big} trades peaked >=$100, {sum(1 for x in peaks_all if 120<=x<=180)} in the $120-180 band; unicorns >$300: {sum(1 for x in peaks_all if x>300)})\n")
    print(f"{'lock_r':>7}{'lock_k':>7}{'total$':>9}{'ex-unicorn$':>12}{'capt% (>=$100pk)':>17}{'banked>=100':>12}")
    for (lr, lk) in CONFIGS:
        tot=0.0; capt_big=[]; banked_big=0
        per=[]
        for (ep, atr, tk) in fires:
            p, peak = ride(ep, atr, lr, lk, tk); tot+=p; per.append((p,peak*VPP))
        ex_uni = sum(p for p,pk in per if pk<=300)                 # drop unicorn-peak trades
        for p,pk in per:
            if pk>=100:
                capt_big.append(max(0.0,(p+FEE))/pk); banked_big += p>=100
        cb = 100*sum(capt_big)/len(capt_big) if capt_big else 0
        star="  <-- LIVE" if (lr,lk)==(6.0,0.5) else ""
        print(f"{lr:>7.1f}{lk:>7.1f}{tot:>+9.0f}{ex_uni:>+12.0f}{cb:>16.0f}%{banked_big:>12}{star}")
    print("\ncapt%(>=$100pk) = of trades that PEAKED >=$100, how much banked. banked>=100 = how many of those actually closed >=$100.")
    print("If $324 is a unicorn, EX-UNICORN total + capt% on the real big runs are the honest metrics.")


if __name__=="__main__":
    main()
