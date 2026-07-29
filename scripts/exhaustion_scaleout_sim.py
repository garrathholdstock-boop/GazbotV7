#!/usr/bin/env python3
"""exhaustion_short SCALE-OUT week SIM (operator 2026-07-29): Lot A @ 2.5R fixed TP + Lot B wide
lock-chandelier + breakeven-after-partial + 1-ATR native stop. Per-trade, this week (07-27→now),
vs what the desk ACTUALLY banked. base_size=2 (Lot A 1 lot, Lot B 1 lot). Faithful ATR (ATR-14 TR
1-min), real deciders exits, $2/pt, $1.50/RT.

HONESTY: Lot A (2.5R) is FAITHFUL (peak-based). Lot B (wide) is a tick-reprice MODEL — the live wide
give-back can run a touch worse; treat Lot B as an estimate, Lot A as solid.

  PYTHONPATH=src .venv/bin/python scripts/exhaustion_scaleout_sim.py [partial_R]   (default 2.5)
"""
from __future__ import annotations
import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Bar, Position, _atr, exit_chandelier_lock, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"; DB = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 90 * 60
PARTIAL_R = float(sys.argv[1]) if len(sys.argv) > 1 else 2.5


def scaleout(side, ep, atr, prices, target_r):
    tgt = target_r * atr; stp = atr; peak = 0.0
    a_px = b_px = None; a_banked = False
    for px in prices:
        fav = (ep - px) if side == "SHORT" else (px - ep); adverse = -fav
        if fav > peak: peak = fav
        pos = Position(side, ep, atr, peak)
        if a_px is None:
            if fav >= tgt: a_px = ep - tgt if side == "SHORT" else ep + tgt; a_banked = True
            elif adverse >= stp: a_px = ep + stp if side == "SHORT" else ep - stp
        if b_px is None:
            trail = exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
            hit_stop = (not a_banked and adverse >= stp)
            hit_be = (a_banked and fav <= 0)
            if trail or hit_stop or hit_be:
                b_px = px if (trail or hit_be) else (ep + stp if side == "SHORT" else ep - stp)
        if a_px is not None and b_px is not None: break
    last = prices[-1]
    a_px = a_px if a_px is not None else last; b_px = b_px if b_px is not None else last
    pa = ((ep-a_px) if side == "SHORT" else (a_px-ep)) * VPP - FEE
    pb = ((ep-b_px) if side == "SHORT" else (b_px-ep)) * VPP - FEE
    return pa, pb, peak*VPP, a_banked


def main():
    con = duckdb.connect()
    for a, p in [("c", CAP), ("g", DB)]:
        con.execute(f"ATTACH '{p}' AS {a} (TYPE sqlite, READ_ONLY)")
    daycache: dict = {}

    def bars_for(t0):
        ss = dr.pnl.paris_day_start_utc(dt.datetime.fromtimestamp(t0, dt.UTC))
        ds = dt.datetime.fromisoformat(ss).timestamp() if isinstance(ss, str) else ss.timestamp()
        if ds not in daycache:
            rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
                FROM c.bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts>={ds-3600} AND bar_ts<{ds+86400}
                GROUP BY 1 ORDER BY 1""").fetchall()
            daycache[ds] = [Bar(ts=r[0], open=r[1], high=r[2], low=r[3], close=r[1], volume=0.0) for r in rows]
        return daycache[ds]

    trades = con.execute("""SELECT side, entry_price, epoch(opened_at::TIMESTAMPTZ) t0,
           strftime(opened_at::TIMESTAMPTZ,'%m-%d %H:%M') d, pnl_usd, qty FROM g.trades
        WHERE symbol='MNQ' AND gate='exhaustion_short' AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-27'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()

    print(f"exhaustion_short — SCALE-OUT SIM this week: Lot A @ {PARTIAL_R}R + Lot B wide (2 lots)\n")
    print(f"{'when':>12} | {'peak$/lot':>9} | {'ACTUAL$':>8} | {'LotA':>6} | {'LotB':>6} | {'SCALEOUT$':>9} | {'Δ vs actual':>11}")
    print("-"*86)
    act_sum = so_sum = a_sum = b_sum = 0.0; nbank = 0; n = 0
    for (side, ep, t0, d, rz, qty) in trades:
        mb = [b for b in bars_for(t0) if b.ts <= t0]
        if len(mb) < 15: continue
        atr = _atr(mb, n=14)
        if atr <= 0: continue
        ticks = con.execute(f"""SELECT price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2: continue
        prices = [p[0] for p in ticks[1:]]
        pa, pb, peak_usd, banked = scaleout(side, ep, atr, prices, PARTIAL_R)
        so = pa + pb
        act_sum += rz; so_sum += so; a_sum += pa; b_sum += pb; n += 1
        if banked: nbank += 1
        mark = "" if banked else "  (no TP)"
        print(f"{d:>12} | {peak_usd:>+9.0f} | {rz:>+8.0f} | {pa:>+6.0f} | {pb:>+6.0f} | {so:>+9.0f} | {so-rz:>+11.0f}{mark}")
    print("-"*86)
    print(f"\nWEEK TOTALS ({n} trades):")
    print(f"  ACTUAL (what the desk banked, mostly 1-lot):   ${act_sum:>+7.0f}")
    print(f"  SCALE-OUT SIM (Lot A {PARTIAL_R}R + Lot B wide, 2-lot): ${so_sum:>+7.0f}   (Lot A ${a_sum:+.0f} guaranteed + Lot B ${b_sum:+.0f} tail)")
    print(f"  → Lot A banked its {PARTIAL_R}R TP on {nbank}/{n} = {100*nbank/n:.0f}% of trades")
    print(f"\n  NOTE: ACTUAL was mostly 1-lot; SIM is 2-lot — so compare SHAPE/give-back capture, not raw totals.")
    print(f"        Lot A (${a_sum:+.0f}) is FAITHFUL (peak-based). Lot B (${b_sum:+.0f}) is a wide-reprice MODEL (live give-back can run worse).")
    con.close()


if __name__ == "__main__":
    main()
