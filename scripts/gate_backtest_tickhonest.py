#!/usr/bin/env python3
"""TICK-HONEST ER backtest for the 4 Features tournament gates — the proper test.

The bar-close `gate_backtest.py` is OPTIMISTIC (exits at bar close, never gets stopped intrabar —
the wick illusion the desk forbids). This one is honest: the ENTRY is still decided on the 1-min
bar signal (exactly how the live gate fires), but the EXIT is repriced on the real TRADE TICKS —
each gate's ACTUAL exit run tick-by-tick (chandelier + native 1-ATR stop for momentum; 2R scalp +
1-ATR stop for reversion), first-touch. Entry = first tick after the signal bar closes.

Then the same per-gate ER floor/ceiling scan, so the thresholds come from honest fills.
Data: V5 tick archive (ticks.db) — so coverage = the tick window (~Jul 5–17, ~9 trading days),
SHORTER than the 30-day bar basis but REAL. CAVEAT: a 60-min max-hold backstop (no session-end
model); entry/exit at the touch tick (honest, mild slippage ignored).

  PYTHONPATH=src:scripts python scripts/gate_backtest_tickhonest.py
"""

from __future__ import annotations

import datetime as dt
import sys

import duckdb

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.deciders import (  # noqa: E402
    Position,
    chandelier_start_k,
    compute_features,
    exit_chandelier,
    exit_scalp,
)

import gate_backtest as gb  # noqa: E402

TICKS = "/home/alphabot/alphabot2/data/ticks.db"
CAP_MIN = 60          # max-hold backstop (min) — bounds the tick window per trade
GRID = [0.05, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40]
VPP, FEE = 2.0, 1.5
STYLE = {"grind_long": "momentum", "thrust_short": "momentum",
         "rgv_long": "reversion", "rgv_short": "reversion"}


def replay_exit(exit_kind, side, entry_px, atr, ticks):
    """Step the gate's real exit over the post-entry ticks; return (exit_px, exit_ms)."""
    peak = 0.0
    k = chandelier_start_k(atr)
    for ts, px in ticks:
        fav = (px - entry_px) if side == "LONG" else (entry_px - px)
        if fav > peak:
            peak = fav
        pos = Position(side, entry_px, atr, peak)
        if exit_kind == "chandelier":
            r = (exit_chandelier(pos, px, start_k=k, min_k=0.5, tighten=0.75)
                 or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))  # native 1-ATR stop
        else:
            r = exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)
        if r:
            return px, ts
    return ticks[-1][1], ticks[-1][0]     # timed out → last tick (max-hold / session backstop)


def backtest_tick(days, con):
    trades = {g[0]: [] for g in gb.GATES}
    skipped = 0
    for _day, bars in days.items():
        next_ok = {g[0]: 0 for g in gb.GATES}     # per-gate one-position-at-a-time (ms)
        for i in range(len(bars)):
            w = bars[max(0, i - 59):i + 1]
            if len(w) < 6:
                continue
            f = compute_features(w)
            decision_ms = (bars[i].ts + 60) * 1000     # enter at the signal bar's close
            er = gb.er_of(bars[max(0, i - 30):i + 1])
            for tag, kind, side, exit_kind, _style in gb.GATES:
                if decision_ms <= next_ok[tag] or not gb._fires(kind, side, f):
                    continue
                ticks = con.execute(
                    "SELECT ts_ms, price FROM tick WHERE ts_ms > ? AND ts_ms <= ? ORDER BY ts_ms",
                    [decision_ms, decision_ms + CAP_MIN * 60000]).fetchall()
                if len(ticks) < 2:                     # outside the tick window → not a real fill
                    skipped += 1
                    continue
                entry_ms, entry_px = ticks[0]
                exit_px, exit_ms = replay_exit(exit_kind, side, entry_px, f.atr, ticks[1:])
                g = ((exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)) * VPP - FEE
                trades[tag].append((g, er))
                next_ok[tag] = exit_ms
    return trades, skipped


def bands(trades):
    """Per-0.1-ER-band breakdown: {band_idx: [net, n, wins]} — the direct 'where do losers sit' view."""
    b = {}
    for p, er in trades:
        k = min(int(er / 0.1), 9)
        d = b.setdefault(k, [0.0, 0, 0])
        d[0] += p
        d[1] += 1
        d[2] += p > 0
    return b


def scan(trades, style):
    nat = round(sum(p for p, _ in trades))
    curve = [(c, len([p for p, er in trades if (er >= c if style == "momentum" else er <= c)]),
              round(sum(p for p, er in trades if (er >= c if style == "momentum" else er <= c))))
             for c in GRID]
    best = max((x for x in curve if x[1] >= 15), key=lambda x: x[2], default=None)   # >=15 kept
    return nat, curve, best


def main():
    days = gb.load_days("/home/alphabot/alphabot2/data/alphabot.db", "1m")
    con = duckdb.connect()
    con.execute(f"ATTACH '{TICKS}' AS tk (TYPE sqlite, READ_ONLY)")
    con.execute("CREATE TABLE tick AS SELECT ts_ms, price FROM tk.trade_tick WHERE symbol='MNQ'")
    con.execute("CREATE INDEX ix ON tick(ts_ms)")
    span = con.execute("SELECT min(ts_ms), max(ts_ms) FROM tick").fetchone()
    print("TICK-HONEST ER backtest (entry on 1-min signal, exit repriced on real ticks)")
    print(f"tick coverage {dt.datetime.fromtimestamp(span[0]/1000, dt.UTC).date()} → "
          f"{dt.datetime.fromtimestamp(span[1]/1000, dt.UTC).date()}\n")

    trades, skipped = backtest_tick(days, con)

    # ── WHERE THE LOSERS SIT — per-0.1-ER-band net/win, each gate on its own ──
    print("PER-BAND (where the money is made/lost by ER-at-entry) — tick-honest:\n")
    for tag, _k, _s, _x, _st in gb.GATES:
        b = bands(trades[tag])
        print(f"{tag:13} ({STYLE[tag]}, nat ${round(sum(p for p,_ in trades[tag])):+}):")
        for k in sorted(b):
            net, n, w = b[k]
            flag = "   <<< bleeds here" if net < 0 else ""
            print(f"    ER {k/10:.1f}-{k/10+0.1:.1f}  {n:>3}tr  {round(100*w/n):>3}% win  ${round(net):>+6}{flag}")
        print()

    # ── cumulative floor/ceiling scan (threshold chooser) ──
    print("CUMULATIVE floor/ceiling scan (total P&L kept at each cut):")
    kind = {"momentum": "floor≥", "reversion": "ceil≤"}
    for tag, _k, _s, _x, _st in gb.GATES:
        style = STYLE[tag]
        nat, curve, best = scan(trades[tag], style)
        cells = "  ".join(f"{kind[style]}{c:.2f}:${net:>+5}({n})" for c, n, net in curve)
        star = (f"  ★ best {kind[style]}{best[0]:.2f} → ${best[2]:+} ({best[1]}tr, +${best[2]-nat} vs nat)"
                if best and best[2] > nat else "  ★ natural best / no gate helps")
        print(f"{tag:13} {style:9} N={len(trades[tag]):>3} nat=${nat:>+5} | {cells}{star}")
    print(f"\n(skipped {skipped} signals outside the tick window) · exit = each gate's REAL exit on "
          f"ticks, first-touch · {CAP_MIN}-min max-hold backstop · ★ needs >=15 trades retained.")


if __name__ == "__main__":
    main()
