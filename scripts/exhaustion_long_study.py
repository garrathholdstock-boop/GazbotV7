#!/usr/bin/env python3
"""EXHAUSTION_LONG study (operator 2026-07-28: "show me the exh long study"). The LONG side of the
footprint gate has NEVER traded or been in shadow — this is the first real model. Mirror of the short:
heavy SELL flow absorbed into a BID wall (sellers exhausted) → go LONG. Aligned in UP-trends (ride),
counter in DOWN-trends (bleed) — the exact mirror of the short's counter-trend finding.

Detection done right this time: the signal is episodic (net>=400 in a sliding 20s window ~28x/day),
so a coarse walk misses it. Here: DuckDB computes a SLIDING trailing-20s net at 1s resolution, filters
candidate moments, dedupes by the 120s hold, then evaluates the REAL exhaustion_signal (footprint_summary
+ price_move<=2 + wall) at each. SHORT is run identically as a VALIDATION anchor (should ~match the
known 224-shadow / live profile). Reprice tick-honest: NATIVE 8/12 + LIVE adaptive (by _regime_mode).
capture.db Jul 20-28 (~1wk, good book). Fees $1.50/RT, $2/pt. ⚠ offline ATR reconstruction; one regime.

  PYTHONPATH=src .venv/bin/python scripts/exhaustion_long_study.py
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from collections import defaultdict, namedtuple

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.footprint import exhaustion_signal, footprint_summary  # noqa: E402
from gazbot7.slot_strategy import SlotStrategy  # noqa: E402
from gazbot7.deciders import (  # noqa: E402
    Position, efficiency_ratio, exit_chandelier, exit_chandelier_lock, exit_fixed, exit_scalp,
)

CAP = "/home/alphabot/gazbot7/data/capture.db"
VPP, FEE, HOLD_S, MAX_HOLD_S = 2.0, 1.50, 120, 120 * 60
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


def candidates(con, sign):
    """Sliding trailing-20s net at 1s resolution → moments where sign*net20>=400, deduped by 120s hold."""
    rows = con.execute(f"""
        WITH s AS (SELECT (ts_ms/1000) sec,
                     sum(CASE WHEN aggressor='buy' THEN size WHEN aggressor='sell' THEN -size ELSE 0 END) n1
                   FROM c.ticks WHERE symbol='MNQ' GROUP BY 1),
             w AS (SELECT sec, sum(n1) OVER (ORDER BY sec RANGE BETWEEN 19 PRECEDING AND CURRENT ROW) net20 FROM s)
        SELECT sec*1000 ts_ms FROM w WHERE {sign}*net20 >= 400 ORDER BY sec""").fetchall()
    out, last = [], -1e18
    for (ts,) in rows:
        if ts - last >= HOLD_S * 1000:
            out.append(int(ts)); last = ts
    return out


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    cap = sqlite3.connect(f"file:{CAP}?mode=ro", uri=True)  # for footprint_summary (reads ticks/book)
    cap.row_factory = sqlite3.Row
    daybars: dict = {}

    def bars_upto(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        sday = dr.pnl.paris_day_start_utc(now)
        ds = int(dt.datetime.fromisoformat(sday).timestamp() if isinstance(sday, str) else sday.timestamp())
        if ds not in daybars:
            daybars[ds] = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-1800} AND bar_ts<{ds+86400}
                GROUP BY 1 ORDER BY 1""").fetchall()
        return daybars[ds]

    def atr_at(rows, t):
        ctx = [r for r in rows if t - 1800 <= r[0] <= t]
        return sum(r[2]-r[3] for r in ctx) / len(ctx) if len(ctx) >= 6 else 0.0

    results = {}
    for want_side, sign in [("LONG", -1), ("SHORT", 1)]:
        cands = candidates(con, sign)
        fires = 0
        bb = defaultdict(lambda: {"nat": 0.0, "adp": 0.0, "n": 0, "w": 0})
        bm = defaultdict(lambda: {"adp": 0.0, "n": 0, "w": 0})
        for ts in cands:
            fp = footprint_summary(cap, "MNQ", ts)
            sig = exhaustion_signal(fp["net_signed"], fp["price_move_pt"], fp["bid1_size"], fp["ask1_size"],
                                    fp["bid1_price"], fp["ask1_price"])
            if sig is None or sig[0] != want_side:
                continue
            ep = sig[1]
            t_s = ts / 1000.0   # bars/atr are in seconds; footprint + ticks use ts (ms)
            rows = bars_upto(t_s)
            atr = atr_at(rows, t_s)
            if atr <= 0:
                continue
            bars = [Bar(cl) for (m, cl, hi, lo) in rows if m <= t_s]
            if len(bars) < 6:
                continue
            ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
                AND ts_ms>{ts} AND ts_ms<={ts + MAX_HOLD_S*1000} ORDER BY ts_ms""").fetchall()
            if len(ticks) < 2:
                continue
            er = efficiency_ratio(bars)
            mode = SlotStrategy._regime_mode(want_side, bars)
            pn = pnl(want_side, ep, replay("NATIVE", want_side, ep, atr, mode, ticks))
            pa = pnl(want_side, ep, replay("ADAPTIVE", want_side, ep, atr, mode, ticks))
            fires += 1
            b = band(er)
            bb[b]["nat"] += pn; bb[b]["adp"] += pa; bb[b]["n"] += 1; bb[b]["w"] += pa > 0
            bm[mode]["adp"] += pa; bm[mode]["n"] += 1; bm[mode]["w"] += pa > 0
        results[want_side] = (len(cands), fires, bb, bm)

    for side in ("LONG", "SHORT"):
        ncand, fires, bb, bm = results[side]
        tag = "  ← THE STUDY" if side == "LONG" else "  ← validation anchor (cf 224 shadow / 48 live)"
        print(f"\n═══ exhaustion_{side}  —  {ncand} candidate episodes → {fires} actual fires{tag}")
        if not fires:
            print("   (no fires)"); continue
        print(f"  {'ER band':>16}{'n':>5}{'NATIVE$':>10}{'ADAPTIVE$':>11}{'adp win%':>10}")
        for b in ["chop(<.08)", "mixed(.08-.18)", "trend(>=.18)"]:
            v = bb[b]
            if v["n"]:
                print(f"  {b:>16}{v['n']:>5}{v['nat']:>+10.0f}{v['adp']:>+11.0f}{100*v['w']/v['n']:>9.0f}%")
        na = sum(v["nat"] for v in bb.values()); aa = sum(v["adp"] for v in bb.values())
        print(f"  {'TOTAL':>16}{fires:>5}{na:>+10.0f}{aa:>+11.0f}")
        print(f"  by alignment (adaptive): " + " · ".join(
            f"{m}({bm[m]['n']}) {bm[m]['adp']:+.0f}@{100*bm[m]['w']//max(bm[m]['n'],1)}%w" for m in ("wide", "mid", "tight") if bm[m]["n"]))
        print(f"    (LONG: wide=long-in-uptrend=ALIGNED · mid=long-in-downtrend=COUNTER · tight=chop)")


if __name__ == "__main__":
    main()
