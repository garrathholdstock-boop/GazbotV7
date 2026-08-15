#!/usr/bin/env python3
"""MGC DAY RIDER — the ER x RT SENSITIVITY GRID (Friday 2026-08-14 re-derivation).

The day-rider study runs ONE threshold pair (the live MNQ constants). The question that decides
whether a result is a fluke or a structure is what happens in the CELLS AROUND it: a peak with
cliffs on both sides is a fit; a plateau where every neighbouring cell is also positive is a
structure. This sweeps ER_MIN x RT_MIN around gold's own derived pair and prints all cells.

★ The thresholds swept here were DERIVED distributionally (mgc_drift_thresholds.py), not fitted to
P&L. This grid is the sensitivity check on that derivation, not the search that produced it.

★ Every cell is scored against the SAME control — the best CONSTANT (always_long / always_short) on
the same days. Gold drifted; a coinflip is not the bar.

  PYTHONPATH=src .venv/bin/python scripts/mgc_day_rider_grid.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from gazbot7 import drift  # noqa: E402
from mgc_day_rider_study import outcome, sessions  # noqa: E402
from mgc_session_anchor import load, minute_bars  # noqa: E402

UPTO = 60           # decide at +60 min (13:30 -> 14:30 UTC)
ER_GRID = [0.093, 0.109, 0.124, 0.140, 0.155]
RT_GRID = [0.350, 0.417, 0.480]


def cell(m, er_min, rt_min, upto=UPTO):
    fired, always_l, always_s = [], [], []
    for _day, win in sessions(m):
        head = win.iloc[:upto]
        if len(head) < 15:
            continue
        bars = [(int(ts.value // 10**9), r["high"], r["low"], r["close"]) for ts, r in head.iterrows()]
        r = drift.compute(bars)
        i = min(upto, len(win) - 1)
        always_l.append(outcome(win, i, 1).get("final$", np.nan))
        always_s.append(outcome(win, i, -1).get("final$", np.nan))
        # re-apply the thresholds ourselves so the LIVE detector stays untouched: `confirmed` is
        # ER>=ER_MIN and RT>=RT_MIN, and both metrics are on the read.
        if not r.ok or not r.direction:
            continue
        if r.efficiency < er_min or r.roundtrip < rt_min:
            continue
        sd = 1 if r.direction == "UP" else -1
        o = outcome(win, i, sd)
        if o:
            fired.append(o)
    if not fired:
        return None
    fin = [f["final$"] for f in fired]
    mfe = [f["mfe$"] for f in fired]
    al, ash = np.nansum(always_l), np.nansum(always_s)
    best = max(al, ash)
    n_days = len([1 for _ in sessions(m)])
    return dict(n=len(fired), days=n_days, held=100 * sum(1 for f in fin if f > 0) / len(fin),
                total=sum(fin), median=float(np.median(fin)), mfe=sum(mfe),
                med_mfe=float(np.median(mfe)), best_const=best, al=al, ash=ash,
                worst=min(fin), strip_best=sum(fin) - max(fin))


def main():
    bars, _ticks = load()
    m = minute_bars(bars)
    days = list(sessions(m))
    print(f"  MGC day rider — ER x RT sensitivity grid · decide at +{UPTO}m · "
          f"{len(days)} sessions · $10/pt · 2 lots · flat 20:40Z")
    ctl = cell(m, 0.0, 0.0)
    print(f"  CONTROL best constant on the same days: ${ctl['best_const']:,.0f} "
          f"(always_long ${ctl['al']:,.0f} / always_short ${ctl['ash']:,.0f})\n")
    print(f"  {'ER_MIN':>7}{'RT_MIN':>8}{'fires':>7}{'held%':>8}{'final$':>11}{'median$':>10}"
          f"{'MFE$':>10}{'strip-best$':>13}{'worst day$':>12}")
    pos = tot = 0
    for er in ER_GRID:
        for rt in RT_GRID:
            c = cell(m, er, rt)
            tot += 1
            if c is None:
                print(f"  {er:>7.3f}{rt:>8.3f}      0")
                continue
            pos += 1 if c["total"] > 0 else 0
            print(f"  {er:>7.3f}{rt:>8.3f}{c['n']:>7d}{c['held']:>8.1f}{c['total']:>11,.0f}"
                  f"{c['median']:>10,.0f}{c['mfe']:>10,.0f}{c['strip_best']:>13,.0f}"
                  f"{c['worst']:>12,.0f}")
    print(f"\n  {pos} of {tot} cells positive — a plateau is the evidence; the peak cell is not.")


if __name__ == "__main__":
    main()
