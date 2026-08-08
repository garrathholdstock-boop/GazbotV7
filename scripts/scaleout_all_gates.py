#!/usr/bin/env python3
"""UNIFIED SCALE-OUT for ALL gates (operator 2026-07-29: "Lot A + Lot B is THE solution, get rid of
all other profit exits, real numbers, be thorough, all gates").

Proposal: every gate's profit exit = LOT A @ target_R fixed TP + LOT B wide lock-chandelier
(+ breakeven-after-partial), native 1-ATR stop owns the loss. Replaces fixed/scalp/regime exits.

FAITHFUL: reprices every REAL entry this week (all gates) tick-by-tick through the ACTUAL deciders
exits. ATR = _atr(ATR-14 TR, 1-min). Regime@entry via the live direction_router marks. $2/pt, $1.50/RT.
2-lot basis (Lot A 1 + Lot B 1) for BOTH baseline and scale-out so they compare apples-to-apples.

VALIDATION: for the adaptive-era trades (07-28+, current regime-chandelier), prints baseline-reprice
vs ACTUAL realized — if they track, the model is faithful and the scale-out numbers are trustworthy.

  PYTHONPATH=src .venv/bin/python scripts/scaleout_all_gates.py
"""
from __future__ import annotations
import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Bar, Position, _atr, exit_chandelier, exit_chandelier_lock, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"; DB = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP, FEE, MAX_HOLD_S = 2.0, 1.50, 90 * 60
TARGET_RS = [1.5, 2.0, 2.5, 3.0]


def _stop(side, ep, atr, adverse):
    return adverse >= atr   # 1-ATR native loss


def baseline_adaptive(side, ep, atr, prices, mode):
    """CURRENT exit: regime chandelier — aligned→wide lock / counter→k2.0 / chop→k1.5. 1 lot."""
    peak = 0.0
    for px in prices:
        fav = (ep - px) if side == "SHORT" else (px - ep); adv = -fav
        if fav > peak: peak = fav
        pos = Position(side, ep, atr, peak)
        if mode == "wide":
            hit = exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
        else:
            k = 1.5 if mode == "tight" else 2.0
            hit = exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
        if hit or _stop(side, ep, atr, adv):
            xp = px if hit else (ep + atr if side == "SHORT" else ep - atr)
            return ((ep-xp) if side == "SHORT" else (xp-ep)) * VPP - FEE
    last = prices[-1]
    return ((ep-last) if side == "SHORT" else (last-ep)) * VPP - FEE


def scaleout(side, ep, atr, prices, target_r):
    """LOT A @ target_r TP + LOT B wide lock-chandelier + BE-after-partial. Returns (pa,pb)."""
    tgt = target_r * atr; peak = 0.0; a_px = b_px = None; a_bank = False
    for px in prices:
        fav = (ep - px) if side == "SHORT" else (px - ep); adv = -fav
        if fav > peak: peak = fav
        pos = Position(side, ep, atr, peak)
        if a_px is None:
            if fav >= tgt: a_px = ep - tgt if side == "SHORT" else ep + tgt; a_bank = True
            elif adv >= atr: a_px = ep + atr if side == "SHORT" else ep - atr
        if b_px is None:
            trail = exit_chandelier_lock(pos, px, start_k=3.5, lock_r=6.0, lock_k=0.5)
            if trail or (not a_bank and adv >= atr) or (a_bank and fav <= 0):
                b_px = px if (trail or (a_bank and fav <= 0)) else (ep + atr if side == "SHORT" else ep - atr)
        if a_px is not None and b_px is not None: break
    last = prices[-1]
    a_px = a_px if a_px is not None else last; b_px = b_px if b_px is not None else last
    pa = ((ep-a_px) if side == "SHORT" else (a_px-ep)) * VPP - FEE
    pb = ((ep-b_px) if side == "SHORT" else (b_px-ep)) * VPP - FEE
    return pa, pb


def main():
    con = duckdb.connect()
    for a, p in [("c", CAP), ("g", DB)]:
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
            bars = [Bar(ts=r[0], open=r[1], high=r[2], low=r[3], close=r[1], volume=0.0) for r in rows]
            daycache[ds] = (marks, bars)
        return daycache[ds]

    trades = con.execute("""SELECT gate, side, entry_price, epoch(opened_at::TIMESTAMPTZ) t0,
           substr(strftime(opened_at::TIMESTAMPTZ,'%m-%d'),1,5) d, pnl_usd, qty FROM g.trades
        WHERE symbol='MNQ' AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-27'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()

    recs = []
    for (gate, side, ep, t0, d, rz, qty) in trades:
        marks, bars = load_day(t0)
        mb = [b for b in bars if b.ts <= t0]
        if len(mb) < 15: continue
        atr = _atr(mb, n=14)
        if atr <= 0: continue
        ticks = con.execute(f"""SELECT price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        if len(ticks) < 2: continue
        prices = [p[0] for p in ticks[1:]]
        st = "CHOP"
        for mt, sm, _e, _n in marks:
            if mt <= t0: st = sm
            else: break
        aligned = (side == "SHORT" and st == "TREND_DOWN") or (side == "LONG" and st == "TREND_UP")
        counter = (side == "SHORT" and st == "TREND_UP") or (side == "LONG" and st == "TREND_DOWN")
        mode = "wide" if aligned else "mid" if counter else "tight"
        recs.append((gate, side, ep, atr, prices, d, rz, qty or 1, mode))

    # VALIDATION: adaptive-era (07-28+) baseline reprice vs actual realized (per lot)
    val = [(r[6]/r[7], baseline_adaptive(r[1], r[2], r[3], r[4], r[8])) for r in recs if r[5] >= "07-28"]
    if val:
        act = sum(a for a, _ in val); mdl = sum(m for _, m in val)
        print(f"VALIDATION (07-28+ adaptive-era, {len(val)} trades, per-lot): actual ${act:+.0f} vs baseline-model ${mdl:+.0f}"
              f"  → model is {'FAITHFUL' if abs(mdl-act) < max(150, .4*abs(act)+150) else 'OFF — treat numbers with caution'}\n")

    gates = sorted(set(r[0] for r in recs))
    print(f"{len(recs)} entries this week, {len(gates)} gates. BASELINE (current regime-chandelier, 2-lot) vs SCALE-OUT (Lot A@R + Lot B wide, 2-lot):\n")
    print(f"{'gate':>17} | {'n':>3} | {'BASELINE$':>9} | " + " | ".join(f'A@{r}R'.rjust(8) for r in TARGET_RS))
    print("-"*(34 + 12*len(TARGET_RS)))
    desk_base = 0.0; desk_so = {r: 0.0 for r in TARGET_RS}
    for g in gates:
        gr = [r for r in recs if r[0] == g]
        base = sum(2*baseline_adaptive(r[1], r[2], r[3], r[4], r[8]) for r in gr)
        desk_base += base
        row = f"{g:>17} | {len(gr):>3} | {base:>+9.0f} | "
        cells = []
        for R in TARGET_RS:
            tot = 0.0
            for r in gr:
                pa, pb = scaleout(r[1], r[2], r[3], r[4], R); tot += pa + pb
            desk_so[R] += tot
            cells.append(f"{tot:>+8.0f}")
        print(row + " | ".join(cells))
    print("-"*(34 + 12*len(TARGET_RS)))
    row = f"{'DESK TOTAL':>17} | {len(recs):>3} | {desk_base:>+9.0f} | "
    print(row + " | ".join(f"{desk_so[R]:>+8.0f}" for R in TARGET_RS))
    bestR = max(TARGET_RS, key=lambda R: desk_so[R])
    print(f"\n★ Best desk-wide scale-out R: {bestR}R = ${desk_so[bestR]:+.0f} vs current ${desk_base:+.0f} ({desk_so[bestR]-desk_base:+.0f})")
    print("  (per-gate: pick each gate's own best column above — some gates may prefer a different R)")
    con.close()


if __name__ == "__main__":
    main()
