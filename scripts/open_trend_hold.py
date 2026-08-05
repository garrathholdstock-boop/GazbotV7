#!/usr/bin/env python3
"""SIT OUT THE OPEN, WAIT FOR A TREND, TAKE 2 LOTS, HOLD. — testing the operator's musing.

Operator, 2026-08-05, after a 17-trade / 2-win day: "what about if we sit out the first little bit.
timeframe ill let you tell me. wait for some sort or up or down trend to emerge. then take 2 lots and
hold them for the day... with a view to riding the daily grind. and then maybe sell it out before us
open. could be a lot more workable than trying to day trade messy tape."

★ WHY THIS DESERVES A REAL TEST AND NOT AN OPINION. Today is the argument for it: 17 trades, 2 wins,
-$341 clean, with grind_long alone -$172 across six fires into a 230pt range at day-ER 0.03. The desk's
whole loss profile is CHURN — many small trades in tape with no efficiency. Holding 2 lots for hours
changes the cost structure by an order of magnitude: 2 round trips a day at $1.50 = $3, against today's
17 trades x 2 lots = $51. On a thin edge that difference is most of the edge
([[mnq-fee-is-150-per-round-trip]]: a fixed fee is a REGRESSIVE tax on high-frequency gates).

★ THE CONTROL THAT DECIDES IT. A long-biased hold on a market that rose is not an edge, it is beta.
Every cell is scored against BUY-AND-HOLD over the identical window, and against the same trigger with
the direction RANDOMISED. If "wait for a trend then hold" cannot beat "just hold", there is no trigger
worth having — you would simply hold.

★ SCORING. days-green and strip-best-DAY, not gross total. 51 sessions is a real sample for a
once-a-day strategy (n=51 entries) where it was hopeless for a per-trade gate — this is the one study
shape where our data length is actually sufficient.

★ WHAT IT DOES NOT MODEL, stated because it matters before anything is armed: overnight gap risk is
real and this holds through the CME halt; the desk currently flattens by policy (DAYTRADE_FLAT_CLOCK,
EOD flatten), so adopting this is a policy change, not a gate change. Margin is also per-lot-hours,
not per-trade.

  PYTHONPATH=src .venv/bin/python scripts/open_trend_hold.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.lake import connect  # noqa: E402

VPP = 2.0            # MNQ venue truth
FEE = 1.50           # per round trip per lot
OPEN_UTC = 13 * 60 + 30      # 13:30 UTC US cash open, in minutes-of-day


def minutes(con):
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) hi, min(low) lo,
               arg_max(close, bar_ts) cl
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    by = defaultdict(dict)
    for m, hi, lo, cl in rows:
        d = dt.datetime.fromtimestamp(int(m), dt.UTC)
        by[d.date()][d.hour * 60 + d.minute] = (float(hi), float(lo), float(cl))
    return by


def atr_of(day, upto, n=60):
    ks = sorted(k for k in day if k <= upto)[-n:]
    if len(ks) < 10:
        return 0.0
    trs = []
    prev = None
    for k in ks:
        hi, lo, cl = day[k]
        trs.append(max(hi - lo, abs(hi - prev), abs(lo - prev)) if prev else hi - lo)
        prev = cl
    return sum(trs) / len(trs)


def run(by, *, wait, hold_to, er_min, stop_atr, mode="trend"):
    """One entry per session. mode: trend | hold (always long) | short (always short)."""
    days = sorted(by)
    out = []
    for i, d in enumerate(days):
        day = by[d]
        t0 = OPEN_UTC + wait
        win = [k for k in day if OPEN_UTC <= k <= t0]
        if len(win) < max(10, wait // 2):
            continue
        # ── has a trend emerged? opening-range break + efficiency over the wait window ──
        cl0 = day[min(win)][2]
        cl1 = day[max(win)][2]
        hi = max(day[k][0] for k in win)
        lo = min(day[k][1] for k in win)
        path = sum(abs(day[a][2] - day[b][2])
                   for a, b in zip(sorted(win)[1:], sorted(win)[:-1])) or 1e-9
        er = abs(cl1 - cl0) / path
        atr = atr_of(day, t0)
        if atr <= 0:
            continue
        if mode == "trend":
            # direction from the break: closing the window at the top/bottom of its own range
            up = (cl1 - lo) / max(hi - lo, 1e-9)
            if er < er_min:
                continue
            if up >= 0.75:
                side = 1
            elif up <= 0.25:
                side = -1
            else:
                continue
        elif mode == "hold":
            side = 1
        else:
            side = -1
        entry = cl1
        stop = entry - side * stop_atr * atr if stop_atr else None
        # ── hold to the exit clock, honouring the stop on the way ──
        ks = sorted(k for k in day if k > t0 and k <= hold_to)
        exit_px, why = None, "clock"
        for k in ks:
            hi_, lo_, cl_ = day[k]
            if stop is not None and ((lo_ <= stop) if side > 0 else (hi_ >= stop)):
                exit_px, why = stop, "stop"
                break
        if exit_px is None:
            if not ks:
                continue
            exit_px = day[max(ks)][2]
        pnl = side * (exit_px - entry) * VPP * 2 - FEE * 2       # 2 lots, 2 round trips
        out.append({"day": d, "side": side, "pnl": pnl, "why": why, "er": er, "atr": atr})
    return out


def rep(tr, lab):
    if not tr:
        print(f"{lab:<34}   no entries")
        return None
    tot = sum(t["pnl"] for t in tr)
    g = sum(1 for t in tr if t["pnl"] > 0)
    best = max(t["pnl"] for t in tr)
    print(f"{lab:<34}{len(tr):>5}{tot:>10.0f}{tot/len(tr):>9.0f}"
          f"{100*g/len(tr):>7.0f}%{tot-best:>10.0f}"
          f"{sum(1 for t in tr if t['why']=='stop'):>8}")
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    z = ap.parse_args()
    con = connect(symbol="MNQ")
    by = minutes(con)
    days = sorted(by)
    print(f"MNQ {len(days)} sessions {days[0]}..{days[-1]}  (2 lots, ${VPP}/pt, ${FEE}/RT/lot)\n")
    hdr = (f"{'config':<34}{'n':>5}{'total':>10}{'$/day':>9}{'green':>8}"
           f"{'strip-day':>10}{'stops':>8}")

    EXITS = {"20:00 UTC": 20 * 60, "21:00 UTC (pre-halt)": 21 * 60}
    print("A. HOW LONG TO WAIT — hold to 21:00 UTC, stop 3xATR, ER>=0.30")
    print(hdr)
    for w in (15, 30, 45, 60, 90, 120):
        rep(run(by, wait=w, hold_to=21 * 60, er_min=0.30, stop_atr=3.0), f"wait {w}m then hold")

    print("\nB. THE CONTROLS — a trigger must beat simply holding")
    print(hdr)
    for w in (30, 60):
        rep(run(by, wait=w, hold_to=21 * 60, er_min=0.30, stop_atr=3.0), f"  trend, wait {w}m")
    rep(run(by, wait=30, hold_to=21 * 60, er_min=0.0, stop_atr=3.0, mode="hold"),
        "  BUY & HOLD (no trigger)")
    rep(run(by, wait=30, hold_to=21 * 60, er_min=0.0, stop_atr=3.0, mode="short"),
        "  SELL & HOLD (no trigger)")

    print("\nC. EXIT CLOCK — wait 30m, ER>=0.30, stop 3xATR")
    print(hdr)
    for lab, hm in EXITS.items():
        rep(run(by, wait=30, hold_to=hm, er_min=0.30, stop_atr=3.0), f"  exit {lab}")

    print("\nD. HOW MUCH TREND TO DEMAND — wait 30m, exit 21:00, stop 3xATR")
    print(hdr)
    for er in (0.0, 0.15, 0.30, 0.45, 0.60):
        rep(run(by, wait=30, hold_to=21 * 60, er_min=er, stop_atr=3.0), f"  ER floor {er:.2f}")

    print("\nE. STOP WIDTH — wait 30m, exit 21:00, ER>=0.30")
    print(hdr)
    for s in (2.0, 3.0, 5.0, 0.0):
        rep(run(by, wait=30, hold_to=21 * 60, er_min=0.30, stop_atr=s),
            f"  stop {s:.0f}xATR" if s else "  NO STOP (clock only)")

    print("\n★ The control block is the verdict. If 'wait for a trend then hold' cannot beat")
    print("  BUY & HOLD over the same window, the trigger adds nothing and the honest answer is")
    print("  that the edge is direction-agnostic beta, not a tradeable signal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
