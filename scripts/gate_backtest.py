#!/usr/bin/env python3
"""Backtest the tournament's Features-based gates over the V5 archive tape, then apply an
ER (efficiency) gate to the REVERSION gates and compare.

HONEST CAVEATS (read first): bar-CLOSE fills — no tick/wick stops, so this is OPTIMISTIC
(understates losses, the desk's sims-on-tick lesson); one regime (Jun–Jul, mostly low-vol
summer); a LEAD, not a verdict. The tick-honest version is the Friday laboratory / shadow
repricer. This is a RELATIVE read: natural vs ER-gated, same fills both ways.

  PYTHONPATH=src python scripts/gate_backtest.py                       # archive 1m, 30 days
"""

from __future__ import annotations

import argparse
import sqlite3

from gazbot7.deciders import (
    Bar,
    Position,
    chandelier_start_k,
    compute_features,
    exit_chandelier,
    exit_scalp,
    gate_grind,
    gate_reversal_grab,
    gate_thrust,
)

# the 4 Features-based tournament gates (footprint gates run separately — need ticks+L2)
GATES = [
    ("grind_long", "grind", "LONG", "chandelier", "momentum"),
    ("thrust_short", "thrust", "SHORT", "chandelier", "momentum"),
    ("rgv_long", "reversal_grab", "LONG", "scalp", "reversion"),
    ("rgv_short", "reversal_grab", "SHORT", "scalp", "reversion"),
]
ER_GATE = 0.18


def load_days(db, tf):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    tbl = "bars" if "capture" in db else "bar_history"
    rows = c.execute(
        f"SELECT bar_ts,open,high,low,close,volume,date(bar_ts,'unixepoch') d "
        f"FROM {tbl} WHERE symbol='MNQ' AND timeframe=? ORDER BY bar_ts", (tf,)).fetchall()
    c.close()
    days: dict = {}
    for r in rows:
        days.setdefault(r["d"], []).append(
            Bar(r["bar_ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]))
    return days


def er_of(window):
    cl = [b.close for b in window]
    if len(cl) < 6:
        return 1.0
    tot = sum(abs(cl[i] - cl[i - 1]) for i in range(1, len(cl))) or 1
    return abs(cl[-1] - cl[0]) / tot


def _fires(kind, side, f):
    if kind == "grind":
        e = gate_grind(f, tape_net=0.0, slope_min=0.4, fast_slope=True)
    elif kind == "reversal_grab":
        e = gate_reversal_grab(f, side=side, ext_min=2.0, turn_atr=0.15, fast_slope=True,
                               fast_turn=True, atr_min=13.0, tape_net=0.0, in_rth=True)
    elif kind == "thrust":
        e = gate_thrust(f, thr=1.5, amp_floor=0.0004)
    else:
        e = None
    return e is not None and e.side == side


def _exit(op, px, exit_kind):
    if op["s"] == "LONG":
        op["peak"] = max(op["peak"], px - op["e"])
    else:
        op["peak"] = max(op["peak"], op["e"] - px)
    pos = Position(op["s"], op["e"], op["atr"], op["peak"])
    if exit_kind == "chandelier":
        return (exit_chandelier(pos, px, start_k=op["k"], min_k=0.5, tighten=0.75)
                or exit_scalp(pos, px, target_r=99.0, stop_atr_mult=1.0))
    return exit_scalp(pos, px, target_r=2.0, stop_atr_mult=1.0)


def backtest(days, er_window=30):
    trades: dict = {g[0]: [] for g in GATES}   # gate -> list of (pnl, er_at_entry)
    for _day, bars in days.items():
        opens: dict = {}
        for i in range(len(bars)):
            w = bars[max(0, i - 59):i + 1]
            if len(w) < 6:
                continue
            f = compute_features(w)
            px = f.price
            for tag, kind, side, exit_kind, _style in GATES:
                op = opens.get(tag)
                if op is not None and _exit(op, px, exit_kind):
                    g = (px - op["e"]) if op["s"] == "LONG" else (op["e"] - px)
                    trades[tag].append((g * 2 - 1.5, op["er"]))
                    opens[tag] = None
                    op = None
                if op is None and _fires(kind, side, f):
                    opens[tag] = {"s": side, "e": px, "atr": f.atr, "peak": 0.0,
                                  "k": chandelier_start_k(f.atr),
                                  "er": er_of(bars[max(0, i - er_window):i + 1])}
    return trades


def _sum(ts):
    return round(sum(p for p, _ in ts), 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/home/alphabot/alphabot2/data/alphabot.db")
    ap.add_argument("--tf", default="1m")
    a = ap.parse_args()
    days = load_days(a.db, a.tf)
    print(f"{len(days)} trading days, {sum(len(b) for b in days.values()):,} bars ({a.tf}) — "
          f"{min(days)} → {max(days)}\n")
    trades = backtest(days)

    print(f"ER<{ER_GATE} gate = bar entries fired in chop (only trade a gate when ER >= {ER_GATE}).\n")
    print(f"{'GATE':16} {'style':10} {'N':>4} {'win%':>5} {'NATURAL':>9}  {'ER-GATED':>9}  barred")
    tot = {"nat": 0.0, "mom_gated": 0.0, "rev_gated": 0.0}
    for tag, _k, _s, _x, st in GATES:
        ts = trades[tag]
        n = len(ts)
        wins = sum(1 for p, _ in ts if p > 0)
        nat = _sum(ts)
        kept = [(p, e) for p, e in ts if e >= ER_GATE]
        gated = _sum(kept)
        barred_n = n - len(kept)
        tot["nat"] += nat
        tot["mom_gated"] += gated if st == "momentum" else nat
        tot["rev_gated"] += gated if st == "reversion" else nat
        print(f"{tag:16} {st:10} {n:>4} {round(100*wins/n) if n else 0:>4}% ${nat:>+8.0f}  ${gated:>+8.0f}  "
              f"{barred_n} (${round(nat-gated):+.0f})")
    print(f"\nTOTAL natural (no ER gate) ........ ${tot['nat']:>+8.0f}")
    print(f"ER-gate MOMENTUM only (grind/thrust) ${tot['mom_gated']:>+8.0f}  "
          f"({'ADDS' if tot['mom_gated']>tot['nat'] else 'costs'} ${tot['mom_gated']-tot['nat']:+.0f})")
    print(f"ER-gate REVERSION only (rgv) ...... ${tot['rev_gated']:>+8.0f}  "
          f"({'adds' if tot['rev_gated']>tot['nat'] else 'COSTS'} ${tot['rev_gated']-tot['nat']:+.0f})")
    print("\n⚠ bar-close fills (optimistic — no tick/wick stops), NO conviction/risk-sizing/give-back "
          "(the live desk HAS these) · one regime · a LEAD not a verdict.")


if __name__ == "__main__":
    main()
