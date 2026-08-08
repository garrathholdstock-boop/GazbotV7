#!/usr/bin/env python3
"""PROFIT-PROGRESSIVE TRAIL backtest — MOMENTUM gates (operator 2026-07-29: "chandeliers bite based
on $ profit; give-back shrinks as the run grows — but only for MOMENTUM. Faders need a tight exit.").

Momentum rides the trend, so it wants a trail that breathes early then tightens as the run grows in R
(fixes tonight's give-backs: abs_veto_long $204->$19, grind_long $208->$23). Faders bank the snap-back
(tested separately = tight wins). Sample: faithful MOMENTUM shadow entries (abs_veto/grind/thrust/cb),
both sides, repriced over the FULL forward tick path + native 1-ATR stop.
⚠ full-path reprice inflates peaks on trend days -> honest metrics are TOTAL-ex-top-unicorn and
CAPTURE% on the $80-200 'real big run' band. Fees $1.50/RT, $2/pt.
  PYTHONPATH=src .venv/bin/python scripts/progressive_trail_sweep.py
"""
from __future__ import annotations
import datetime as dt, sys
from collections import namedtuple
import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr
CAP="/home/alphabot/gazbot7/data/capture.db"; SH="/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE, MAXH = 2.0, 1.50, 120*60
MOMENTUM = ('abs_veto_55s','abs_veto_50s','abs_veto_60s','grind_fast','thrust_short_raw',
            'thrust_aligned','thrust_fast','thrust_cont','cb_thrust','thrust_loose')

CONFIGS = {
  "WIDE-LOCK (live)":  [(0,3.5),(6,0.5)],
  "PROG-A 3.5/1.5/.75":[(0,3.5),(2,1.5),(4,0.75)],
  "PROG-B 3.0/1.5/.5": [(0,3.0),(2,1.5),(4,0.5)],
  "PROG-C 3.5/1.0/.5": [(0,3.5),(3,1.0),(5,0.5)],
  "PROG-D 3.0/1.0":    [(0,3.0),(3,1.0)],
  "PROG-E 2.5/1.0/.5": [(0,2.5),(2,1.0),(4,0.5)],
  "FIXED tight 1.5":   [(0,1.5)],
}


def kfor(peak_r, bands):
    k = bands[0][1]
    for r_th, kk in bands:
        if peak_r >= r_th: k = kk
        else: break
    return k


def reprice(side, entry, atr, bands, ticks):
    peak = 0.0
    for ts, px in ticks:
        stop_hit = (px <= entry - atr) if side == "LONG" else (px >= entry + atr)
        if stop_hit:
            return -atr*VPP - FEE, peak
        fav = (px - entry) if side == "LONG" else (entry - px)
        peak = max(peak, fav)
        if fav > 0:
            gb = kfor(peak/atr, bands)*atr
            if fav <= peak - gb:
                return fav*VPP - FEE, peak    # exit at current fav (approx; peak-gb ~ current)
    last = ticks[-1][1]
    fav = (last - entry) if side == "LONG" else (entry - last)
    return fav*VPP - FEE, peak


def main():
    con=duckdb.connect(); con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)"); con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    q = "SELECT CAST(entry_ts AS BIGINT) t0, side, entry_price FROM s.shadow_trades WHERE strategy IN {} AND exit_price IS NOT NULL ORDER BY entry_ts".format(MOMENTUM)
    rows=con.execute(q).fetchall()
    daybars={}
    def atr_at(t0):
        s=dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0,dt.UTC)); ds=int(dt.datetime.fromisoformat(s).timestamp() if isinstance(s,str) else s.timestamp())
        if ds not in daybars:
            daybars[ds]=con.execute(f"SELECT (bar_ts-bar_ts%60) m, max(high) hi, min(low) lo FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1").fetchall()
        ctx=[r for r in daybars[ds] if t0-1800<=r[0]<=t0]
        return sum(r[1]-r[2] for r in ctx)/len(ctx) if len(ctx)>=6 else 0
    fires=[]
    for (t0, side, ep) in rows:
        atr=atr_at(t0)
        if atr<=0: continue
        tk=con.execute(f"SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ' AND ts_ms>{t0*1000} AND ts_ms<={(t0+MAXH)*1000} ORDER BY ts_ms").fetchall()
        if len(tk)>=2: fires.append((side, ep, atr, tk))
    con.close()

    print(f"\nPROFIT-PROGRESSIVE TRAIL — MOMENTUM — {len(fires)} faithful momentum shadow entries, full-path reprice\n")
    print(f"{'config':>20}{'total$':>9}{'ex-uni$':>9}{'capt%$80-200':>13}{'banked>=100':>12}{'avg_gaveback':>13}")
    for name, bands in CONFIGS.items():
        per=[]
        for (side, ep, atr, tk) in fires:
            p, peak = reprice(side, ep, atr, bands, tk); per.append((p, peak*VPP))
        tot=sum(p for p,_ in per); topuni=max(pk for _,pk in per)
        ex=sum(p for p,pk in per if pk<topuni)
        band=[(p,pk) for p,pk in per if 80<=pk<=200]
        cb=100*sum(max(0,p+FEE)/pk for p,pk in band)/len(band) if band else 0
        banked=sum(1 for p,pk in per if p>=100)
        big=[pk-p for p,pk in per if pk>=100]; gb=sum(big)/len(big) if big else 0
        star="  <-- LIVE" if name.startswith("WIDE-LOCK") else ""
        print(f"{name:>20}{tot:>+9.0f}{ex:>+9.0f}{cb:>12.0f}%{banked:>12}{gb:>+13.0f}{star}")
    nb=sum(1 for (side,ep,atr,tk) in fires if 80<= max(((px-ep) if side=='LONG' else (ep-px)) for _,px in tk)*VPP <=200)
    print(f"\n({nb} entries peaked in the $80-200 band. Winner = best capt% on $80-200 runs + best ex-unicorn total.)")


if __name__=="__main__":
    main()
