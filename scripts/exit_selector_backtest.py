#!/usr/bin/env python3
"""REGIME-DRIVEN EXIT SELECTOR — backtest (operator 2026-07-27).

Question: should the desk choose the exit by regime — ride a CHANDELIER when the router reads an
ALIGNED TREND (capture the flush, e.g. today's −563pt down-leg), scalp a fixed 2R in CHOP (bank
before give-back)? Compares three books on the SAME realised entries, tick-honest:
  FIXED-SCALP   : every trade exits scalp-2R (1-ATR stop / 2R target)
  FIXED-CHAND   : every trade exits a vol-adaptive chandelier (+ native 1-ATR stop)
  ADAPTIVE      : aligned-trend → chandelier ; chop / counter-trend → scalp-2R
Regime@entry is the LIVE direction_router signal (its exact replay + current 0.20/30 thresholds).
Reprice reuses the desk's exit deciders on capture.db 250ms ticks. Fees $1.50/RT, $2/pt.

⚠ tick window ≈ 07-20..27 (one week, ONE real trend day = today) → illustrative, not a proof.

  PYTHONPATH=src .venv/bin/python scripts/exit_selector_backtest.py
"""
from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import direction_router as dr  # noqa: E402
from gazbot7.deciders import Position, chandelier_start_k, exit_chandelier, exit_scalp  # noqa: E402

CAP = "/home/alphabot/gazbot7/data/capture.db"
DB = "/home/alphabot/gazbot7/data/gazbot7.db"
VPP = 2.0
FEE = 1.50
MAX_HOLD_S = 120 * 60


def replay_exit(kind, side, entry_px, atr, ticks):
    """Step scalp or chandelier over post-entry ticks → exit price. Mirrors gate_backtest_tickhonest."""
    peak = 0.0
    k = chandelier_start_k(atr)
    for ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        if kind == "chandelier":
            r = (exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
                 or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))   # native 1-ATR stop only
        else:
            r = exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)
        if r:
            return px
    return ticks[-1][1]


def pnl_usd(side, entry_px, exit_px, qty):
    pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
    return pts * VPP * qty - FEE * qty


def main():
    con = duckdb.connect()
    con.execute(f"ATTACH '{CAP}' AS c (TYPE sqlite, READ_ONLY)")
    con.execute(f"ATTACH '{DB}' AS g (TYPE sqlite, READ_ONLY)")

    # realised entries in the tick window
    trades = con.execute("""
        SELECT id, gate, side, entry_price, qty, epoch(opened_at::TIMESTAMPTZ) t0,
               strftime(opened_at::TIMESTAMPTZ,'%Y-%m-%d') d
        FROM g.trades WHERE symbol='MNQ' AND opened_at::TIMESTAMPTZ >= TIMESTAMP '2026-07-20'
          AND exit_reason NOT IN ('ADOPT_FLATTEN','RECONCILED_CLOSE') ORDER BY opened_at""").fetchall()

    # per-day bars for the router regime replay (cache) + atr reconstruction
    daybars: dict = {}

    def day_bounds(t0):
        now = dt.datetime.fromtimestamp(t0, dt.UTC)
        s = dr.pnl.paris_day_start_utc(now)
        t = dt.datetime.fromisoformat(s).timestamp() if isinstance(s, str) else s.timestamp()
        return t

    def load_day(t_day_start):
        if t_day_start in daybars:
            return daybars[t_day_start]
        rows = con.execute(f"""SELECT (bar_ts-bar_ts%60) m, arg_max(close,bar_ts) cl, max(high) hi, min(low) lo
            FROM c.bars WHERE symbol='MNQ' AND timeframe='5s'
              AND bar_ts>={t_day_start-1800} AND bar_ts<{t_day_start+86400} GROUP BY 1 ORDER BY 1""").fetchall()
        mins = [r[0] for r in rows]
        marks = dr.replay_marks(mins, [r[1] for r in rows], int(t_day_start), int(t_day_start+86400)) if len(mins) > dr.WINDOW else []
        daybars[t_day_start] = (rows, marks)
        return daybars[t_day_start]

    def regime_at(marks, t):
        st = "CHOP"
        for mt, s, _e, _n in marks:
            if mt <= t:
                st = s
            else:
                break
        return st

    def atr_at(rows, t):
        ctx = [r for r in rows if t - 1800 <= r[0] <= t]
        return sum(r[2]-r[3] for r in ctx) / len(ctx) if len(ctx) >= 6 else 0.0

    books = defaultdict(lambda: defaultdict(float))     # scope -> {scalp, chand, adaptive}
    per_gate = defaultdict(lambda: defaultdict(float))
    n_aligned = n_total = 0

    for (tid, gate, side, ep, qty, t0, d) in trades:
        rows, marks = load_day(day_bounds(t0))
        atr = atr_at(rows, t0)
        if atr <= 0:
            continue
        ticks = con.execute(f"""SELECT ts_ms, price FROM c.ticks WHERE symbol='MNQ'
            AND ts_ms>={int(t0*1000)} AND ts_ms<={int((t0+MAX_HOLD_S)*1000)} ORDER BY ts_ms""").fetchall()
        ticks = [(t, p) for t, p in ticks]
        if len(ticks) < 2:
            continue
        reg = regime_at(marks, t0)
        aligned = (side == "SHORT" and reg == "TREND_DOWN") or (side == "LONG" and reg == "TREND_UP")
        q = qty or 1
        sx = replay_exit("scalp", side, ep, atr, ticks[1:])
        cx = replay_exit("chandelier", side, ep, atr, ticks[1:])
        p_scalp = pnl_usd(side, ep, sx, q)
        p_chand = pnl_usd(side, ep, cx, q)
        p_adapt = p_chand if aligned else p_scalp
        n_total += 1
        n_aligned += aligned
        for scope in ("ALL", "TODAY" if d == "2026-07-27" else "PRIOR"):
            books[scope]["scalp"] += p_scalp
            books[scope]["chand"] += p_chand
            books[scope]["adaptive"] += p_adapt
        per_gate[gate]["scalp"] += p_scalp
        per_gate[gate]["chand"] += p_chand
        per_gate[gate]["adaptive"] += p_adapt
    con.close()

    print(f"REGIME-DRIVEN EXIT SELECTOR — {n_total} realised entries repriced (07-20..27, {n_aligned} aligned-trend)")
    print(f"router: ER>={dr.ER_TREND} |net|>={dr.NET_MIN} · rule: aligned-trend→chandelier, else→scalp-2R\n")
    print(f"{'scope':>7} {'FIXED-SCALP':>12} {'FIXED-CHAND':>12} {'ADAPTIVE':>12}   winner")
    for scope in ("ALL", "PRIOR", "TODAY"):
        b = books[scope]
        best = max(b, key=b.get)
        print(f"{scope:>7} {b['scalp']:>+12.0f} {b['chand']:>+12.0f} {b['adaptive']:>+12.0f}   {best.upper()}")
    print(f"\n{'gate':18} {'scalp':>8} {'chand':>8} {'adaptive':>9}")
    for gate, b in sorted(per_gate.items(), key=lambda x: -x[1]['adaptive']):
        print(f"{gate:18} {b['scalp']:>+8.0f} {b['chand']:>+8.0f} {b['adaptive']:>+9.0f}")


if __name__ == "__main__":
    main()
