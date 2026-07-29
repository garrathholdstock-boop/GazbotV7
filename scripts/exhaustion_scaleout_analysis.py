#!/usr/bin/env python3
"""exhaustion_short SCALE-OUT — FAITHFUL-ATR (operator 2026-07-29: "run the exact config, reconcile
the ATR, recommend best R take-profit for lot 1, wide chandelier handles lot 2").

★ ATR RECONCILED: the live desk computes entry_atr via deciders._atr = ATR(14) TRUE-RANGE on
1-MINUTE bars (NOT the avg-5s-range my first pass used — that was ~2.5x too small). This imports the
REAL _atr + real exits so R-multiples match the live desk.

Config = the exact ask: base_size 2. LOT A takes profit at a fixed target_R (sweep to recommend the
best). LOT B rides the LIVE wide lock-chandelier (start_k 3.5 / lock_r 6 / lock_k 0.5) to catch the
fat tail; after Lot A banks, Lot B's stop → breakeven (free runner). 1-ATR native loss stop on both.

  PYTHONPATH=src .venv/bin/python scripts/exhaustion_scaleout_analysis.py
"""
from __future__ import annotations
import datetime as dt
import statistics
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Bar, Position, _atr, exit_chandelier_lock, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"; DB = "/home/alphabot/gazbot7/data/gazbot7.db"
SH = "/home/alphabot/gazbot7/data/shadow.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 90 * 60
TARGET_RS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def exit_wide(side, ep, atr, ticks):
    peak = 0.0
    for _ts, px in ticks:
        fav = (ep - px) if side == "SHORT" else (px - ep)
        if fav > peak: peak = fav
        pos = Position(side, ep, atr, peak)
        if exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5) \
           or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0):
            return px, peak
    return ticks[-1][1], peak


def exit_scaleout(side, ep, atr, ticks, target_r):
    """LOT A @ target_r fixed TP (or 1-ATR stop). LOT B wide lock-chandelier; BE stop after A banks."""
    tgt = target_r * atr; stop1 = atr; peak = 0.0
    a_px = b_px = None; a_banked = False
    for _ts, px in ticks:
        fav = (ep - px) if side == "SHORT" else (px - ep)
        adverse = -fav
        if fav > peak: peak = fav
        pos = Position(side, ep, atr, peak)
        if a_px is None:
            if fav >= tgt:
                a_px = ep - tgt if side == "SHORT" else ep + tgt; a_banked = True
            elif adverse >= stop1:
                a_px = ep + stop1 if side == "SHORT" else ep - stop1
        if b_px is None:
            trail = exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
            hit_stop = (not a_banked and adverse >= stop1)          # native 1-ATR until A banks
            hit_be = (a_banked and fav <= 0)                        # breakeven after A banks
            if trail or hit_stop or hit_be:
                b_px = px if (trail or hit_be) else (ep + stop1 if side == "SHORT" else ep - stop1)
        if a_px is not None and b_px is not None: break
    last = ticks[-1][1]
    a_px = a_px if a_px is not None else last
    b_px = b_px if b_px is not None else last
    pa = (ep - a_px) if side == "SHORT" else (a_px - ep)
    pb = (ep - b_px) if side == "SHORT" else (b_px - ep)
    return pa, pb, peak


def main():
    con = duckdb.connect()
    for a, p in [("c", CAP), ("g", DB), ("s", SH)]:
        con.execute(f"ATTACH '{p}' AS {a} (TYPE sqlite, READ_ONLY)")
    daycache: dict = {}

    def load_day(t0):
        ss = dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0, dt.UTC))
        ds = dt.datetime.fromisoformat(ss).timestamp() if isinstance(ss, str) else ss.timestamp()
        if ds not in daycache:
            rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-3600} AND bar_ts<{ds+86400}
                GROUP BY 1 ORDER BY 1""").fetchall()
            marks = dr.replay_marks([r[0] for r in rows], [r[1] for r in rows], int(ds), int(ds+86400)) if len(rows) > dr.WINDOW else []
            # faithful 1-min Bars for _atr (high/low/close per minute)
            bars = [Bar(ts=r[0], open=r[1], high=r[2], low=r[3], close=r[1], volume=0.0) for r in rows]
            daycache[ds] = (rows, marks, bars)
        return daycache[ds]

    def build(fires):
        out = []
        for (side, ep, qty, t0) in fires:
            rows, marks, bars = load_day(t0)
            mbars = [b for b in bars if b.ts <= t0]
            if len(mbars) < 15: continue
            atr = _atr(mbars, n=14)                    # ★ FAITHFUL: ATR(14) TR on 1-min bars
            if atr <= 0: continue
            ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
                AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
            if len(ticks) < 2: continue
            st = "CHOP"
            for mt, sm, _e, _n in marks:
                if mt <= t0: st = sm
                else: break
            if side == "SHORT" and st == "TREND_DOWN":
                out.append((atr, ep, side, ticks[1:]))
        return out

    fires = build(con.execute("""SELECT 'SHORT', entry_price, 1, CAST(entry_ts AS BIGINT) FROM s.shadow_trades
        WHERE strategy='exhaustion_rev' AND side='SHORT' AND exit_price IS NOT NULL ORDER BY entry_ts""").fetchall())
    print(f"SHADOW exhaustion_rev: {len(fires)} ALIGNED-trend fires  (FAITHFUL ATR: ATR-14 TR on 1-min bars)\n")

    atrs = [f[0] for f in fires]
    print(f"entry_atr sanity (should be ~30-45 like the live desk's 41): median {statistics.median(atrs):.1f}, range {min(atrs):.0f}-{max(atrs):.0f}")
    peaks_r = []
    for (atr, ep, side, ticks) in fires:
        peak = 0.0
        for _t, px in ticks:
            fav = (ep - px) if side == "SHORT" else (px - ep)
            if fav > peak: peak = fav
        peaks_r.append(peak / atr)
    winners = [r for r in peaks_r if r >= 1.0]
    print(f"MFE (faithful): winners median {statistics.median(winners):.1f}R · 90th pct {sorted(peaks_r)[int(.9*len(peaks_r))]:.1f}R · max {max(peaks_r):.1f}R\n")

    live_tot = 0.0; live_kept = []
    for (atr, ep, side, ticks) in fires:
        xp, peak = exit_wide(side, ep, atr, ticks)
        pts = (ep - xp) if side == "SHORT" else (xp - ep)
        live_tot += pts * VPP * 2 - 2*FEE
        if peak > 0: live_kept.append(max(0.0, pts)/peak)
    print(f"LIVE (2 lots both wide): ${live_tot:+.0f} · {100*sum(live_kept)/len(live_kept):.0f}% of peak kept (the give-back)\n")

    print("SCALE-OUT — LOT A @ target_R (fixed TP) + LOT B wide chandelier + BE-after-partial:")
    print(f"  {'A target_R':>11} | {'total$':>8} | {'vs LIVE':>8} | {'%peak kept':>10} | {'lotA banked$':>12} | {'lotB (tail)$':>12}")
    print("  " + "-"*78)
    best = None
    for tr in TARGET_RS:
        tot = 0.0; kept = []; aB = 0.0; bB = 0.0
        for (atr, ep, side, ticks) in fires:
            pa, pb, peak = exit_scaleout(side, ep, atr, ticks, tr)
            tot += (pa + pb) * VPP - 2*FEE
            aB += pa * VPP - FEE; bB += pb * VPP - FEE
            if peak > 0: kept.append(max(0.0, (pa+pb)/2)/peak)
        if best is None or tot > best[1]: best = (tr, tot, aB, bB)
        print(f"  {tr:>11.1f} | {tot:>+8.0f} | {tot-live_tot:>+8.0f} | {100*sum(kept)/len(kept):>9.0f}% | {aB:>+12.0f} | {bB:>+12.0f}")
    print("  " + "-"*78)
    tr, tt, aB, bB = best
    print(f"\n  ★ BEST first-lot TP: {tr}R = ${tt:+.0f} total (vs LIVE ${live_tot:+.0f}, {tt-live_tot:+.0f}); "
          f"Lot A banks ${aB:+.0f} guaranteed, Lot B tail ${bB:+.0f}")
    print(f"  In $ terms at median ATR {statistics.median(atrs):.0f}: a {tr}R first-lot TP ≈ +${tr*statistics.median(atrs)*VPP:.0f}/lot banked.")
    con.close()


if __name__ == "__main__":
    main()
