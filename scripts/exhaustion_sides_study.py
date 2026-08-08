#!/usr/bin/env python3
"""EXHAUSTION LONG vs SHORT study — from FAITHFUL shadow data (operator 2026-07-28).
Correction: exhaustion_rev shadow records BOTH sides (the signal is two-sided); my earlier
"exhaustion_short" run conflated them. Here I split properly. Entries are the shadow's own live
tick-loop fires (faithful — no offline footprint reconstruction), repriced under the LIVE adaptive
exit; regime/ER from capture BARS (reliable). shadow stores entry_atr → faithful ride reprice.

For a LONG: wide=long-in-UPtrend=ALIGNED (ride) · mid=long-in-DOWNtrend=COUNTER · tight=chop.
For a SHORT: wide=short-in-DOWNtrend=ALIGNED · mid=short-in-UPtrend=COUNTER · tight=chop.
Fees $1.50/RT, $2/pt, 120min hold. ⚠ ~1 week capture / one regime; offline ATR reconstruction.

  PYTHONPATH=src .venv/bin/python scripts/exhaustion_sides_study.py
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict, namedtuple

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.slot_strategy import SlotStrategy  # noqa: E402
from gazbot7.deciders import (  # noqa: E402
    Position, efficiency_ratio, exit_chandelier, exit_chandelier_lock, exit_fixed, exit_scalp,
)

CAP = "/home/alphabot/gazbot7/data/capture.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 120 * 60
Bar = namedtuple("Bar", "close")


def band(er):
    return "chop(<.08)" if er < 0.08 else ("mixed(.08-.18)" if er < 0.18 else "trend(>=.18)")


def replay(book, side, ep, atr, mode, ticks):
    peak = 0.0
    for ts, px in ticks:
        fav = (px - ep) if side == "LONG" else (ep - px)
        peak = max(peak, fav)
        pos = Position(side, ep, atr, peak)
        if book == "NATIVE":
            r = exit_fixed(pos, px, stop_pt=8.0, target_pt=12.0)
        else:
            if mode == "wide":
                r = exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
            else:
                k = 2.0 if mode == "mid" else 1.5
                r = "CHANDELIER" if exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75) else None
            r = r or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0)
        if r:
            return px
    return ticks[-1][1]


def pnl(side, ep, xp):
    return ((xp - ep) if side == "LONG" else (ep - xp)) * VPP - FEE


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{SH}' AS s (TYPE sqlite, READ_ONLY)")
    rows = con.execute("""
        SELECT CAST(entry_ts AS DOUBLE) t0, side, entry_price, entry_atr
        FROM s.shadow_trades WHERE strategy='exhaustion_rev' AND exit_price IS NOT NULL
          AND entry_atr > 0 ORDER BY entry_ts""").fetchall()
    lo = con.execute("SELECT min(bar_ts) FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'").fetchone()[0]
    daybars: dict = {}

    def bars_upto(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        sday = dr.pnl.paris_day_start_utc(now)
        ds = int(dt.datetime.fromisoformat(sday).timestamp() if isinstance(sday, str) else sday.timestamp())
        if ds not in daybars:
            daybars[ds] = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
                  AND bar_ts>={ds-1800} AND bar_ts<{ds+86400} GROUP BY 1 ORDER BY 1""").fetchall()
        return [Bar(cl) for (m, cl) in daybars[ds] if m <= t0]

    # per side: band -> {nat,adp,n,wadp}, mode -> {adp,n,w}
    B = {"LONG": defaultdict(lambda: {"nat": 0.0, "adp": 0.0, "n": 0, "w": 0}),
         "SHORT": defaultdict(lambda: {"nat": 0.0, "adp": 0.0, "n": 0, "w": 0})}
    M = {"LONG": defaultdict(lambda: {"adp": 0.0, "n": 0, "w": 0}),
         "SHORT": defaultdict(lambda: {"adp": 0.0, "n": 0, "w": 0})}
    skip = 0
    for (t0, side, ep, atr) in rows:
        if t0 < lo:
            skip += 1; continue
        bars = bars_upto(t0)
        if len(bars) < 6:
            skip += 1; continue
        er = efficiency_ratio(bars)
        mode = SlotStrategy._regime_mode(side, bars)
        ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>{int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2:
            skip += 1; continue
        pn = pnl(side, ep, replay("NATIVE", side, ep, atr, mode, ticks))
        pa = pnl(side, ep, replay("ADAPTIVE", side, ep, atr, mode, ticks))
        b = band(er)
        B[side][b]["nat"] += pn; B[side][b]["adp"] += pa; B[side][b]["n"] += 1; B[side][b]["w"] += pa > 0
        M[side][mode]["adp"] += pa; M[side][mode]["n"] += 1; M[side][mode]["w"] += pa > 0

    for side in ("LONG", "SHORT"):
        n = sum(v["n"] for v in B[side].values())
        anchor = "  ← THE STUDY (never traded/tuned)" if side == "LONG" else "  ← anchor"
        print(f"\n═══ exhaustion {side}  —  {n} faithful shadow trades{anchor}")
        print(f"  {'ER band':>16}{'n':>5}{'NATIVE$':>10}{'ADAPTIVE$':>11}{'adp win%':>10}")
        for b in ["chop(<.08)", "mixed(.08-.18)", "trend(>=.18)"]:
            v = B[side][b]
            if v["n"]:
                print(f"  {b:>16}{v['n']:>5}{v['nat']:>+10.0f}{v['adp']:>+11.0f}{100*v['w']/v['n']:>9.0f}%")
        na = sum(v["nat"] for v in B[side].values()); aa = sum(v["adp"] for v in B[side].values())
        print(f"  {'TOTAL':>16}{n:>5}{na:>+10.0f}{aa:>+11.0f}")
        al = "long-in-UPtrend" if side == "LONG" else "short-in-DOWNtrend"
        co = "long-in-DOWNtrend" if side == "LONG" else "short-in-UPtrend"
        print(f"  by ALIGNMENT (adaptive):  wide={al}(aligned) · mid={co}(COUNTER) · tight=chop")
        for m in ("wide", "mid", "tight"):
            v = M[side][m]
            if v["n"]:
                print(f"    {m:>6} n={v['n']:>3}  {v['adp']:>+8.0f}  {100*v['w']//max(v['n'],1):>3}%w  avg {v['adp']/v['n']:+.1f}")
    print(f"\n  ({skip} skipped: pre-capture or no ticks)")


if __name__ == "__main__":
    main()
