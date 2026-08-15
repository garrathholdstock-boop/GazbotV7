#!/usr/bin/env python3
"""GF RIDER · STEP 2 — THE EXIT IS PROBABLY THE GAME. Sweep stop x target WIDE before judging.

Three independent results this week said the same thing: a tight or trailing exit gets shaken out of
a move that grinds, and the SAME entries with a wide stop and a far target make money.
exhaustion_short went -$158 as traded to +$5,243 on identical entries purely on the exit. So no
entry is allowed to be called a failure here until it has been priced across a wide grid.

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_exit.py

Everything is per-regime AND per-time-of-day, never a blanket cross-tape number.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_rider_engine import Racer, by, line, run_trades, stat, strip_best  # noqa: E402
from gf_rider_signals import signals  # noqa: E402
from gf_rider_tape import build  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
pd.set_option("display.width", 250)


def main():
    m1, s5 = build()
    racer = Racer(s5)
    sig = signals(m1, 10, 1.5)
    print(f"═══ STEP 2 · EXIT SWEEP — BOARD(w=10, k=1.5) on {m1['day'].nunique()} sessions ═══\n")
    print(f"raw fires: {len(sig):,}  ({len(sig)/m1['day'].nunique():.0f}/session)  "
          f"long {(sig['side']>0).sum():,} / short {(sig['side']<0).sum():,}")
    print(f"regime mix of fires:\n{sig['regime'].value_counts().to_string()}\n")

    res = {}

    # ── the grid ────────────────────────────────────────────────────────────────────────────────
    STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    TARGS = [1.5, 2.0, 3.0, 4.0, 6.0, 8.0, np.inf]
    CAP = 120
    print(f"── STOP x TARGET, all fires pooled, time cap {CAP}min, $1.50/RT + 0.25pt/side ──")
    print("   cell = net $ (n trades)\n")
    grid, cache = {}, {}
    hdr = "  stop\\targ " + "".join(f"{('HOLD' if not np.isfinite(t) else f'{t:.1f}R'):>14s}" for t in TARGS)
    print(hdr)
    for s in STOPS:
        row = f"  {s:>4.1f}xATR "
        for t in TARGS:
            tr = run_trades(racer, sig, stop_a=s, targ_a=t, cap_min=CAP)
            cache[(s, t)] = tr
            st = stat(tr)
            grid[f"{s}_{t}"] = st
            row += f"{st['net']:>8,.0f}({st['n']:>3d})"
        print(row)

    print("\n── the same grid, $ PER TRADE (the judging metric — never win%) ──\n")
    print(hdr)
    for s in STOPS:
        row = f"  {s:>4.1f}xATR "
        for t in TARGS:
            st = stat(cache[(s, t)])
            row += f"{st['per']:>10.2f}    "
        print(row)

    # ── the plateau test: is the optimum a broad shelf or a single lucky cell? ──
    best = max(grid.items(), key=lambda kv: kv[1]["per"] if kv[1]["n"] >= 40 else -1e9)
    print(f"\n── best cell by $/trade with n>=40: {best[0]}  {best[1]}")
    pos = sum(1 for v in grid.values() if v["per"] > 0)
    print(f"   cells with positive $/trade: {pos} of {len(grid)} "
          f"— a broad shelf is a plateau, one green cell in a red field is a fit\n")

    # ── trailing / chandelier variants against the flat grid ────────────────────────────────────
    print("── TRAILING & HOLD VARIANTS (the 'does a trail beat a far target' question) ──\n")
    variants = {
        "flat 3.0 stop / 6R target":      dict(stop_a=3.0, targ_a=6.0, cap_min=CAP),
        "flat 3.0 stop / HOLD to cap":    dict(stop_a=3.0, targ_a=np.inf, cap_min=CAP),
        "flat 4.0 stop / HOLD to cap":    dict(stop_a=4.0, targ_a=np.inf, cap_min=CAP),
        "chand arm2 trail1.5":            dict(stop_a=3.0, targ_a=np.inf, cap_min=CAP, arm_a=2.0, trail_a=1.5),
        "chand arm3 trail2":              dict(stop_a=3.0, targ_a=np.inf, cap_min=CAP, arm_a=3.0, trail_a=2.0),
        "chand arm4 trail2":              dict(stop_a=3.0, targ_a=np.inf, cap_min=CAP, arm_a=4.0, trail_a=2.0),
        "chand arm4 trail3":              dict(stop_a=4.0, targ_a=np.inf, cap_min=CAP, arm_a=4.0, trail_a=3.0),
        "BE at 2R + 3.0 stop / HOLD":     dict(stop_a=3.0, targ_a=np.inf, cap_min=CAP, be_a=2.0),
        "tight 1.0 stop / 2R (the desk)": dict(stop_a=1.0, targ_a=2.0, cap_min=CAP),
        "hold 30min hard":                dict(stop_a=99.0, targ_a=np.inf, cap_min=30),
        "hold 60min hard":                dict(stop_a=99.0, targ_a=np.inf, cap_min=60),
    }
    vres = {}
    for name, kw in variants.items():
        tr = run_trades(racer, sig, **kw)
        vres[name] = dict(stat(tr), strip3=strip_best(tr, 3))
        cache[name] = tr
        print(line(name, vres[name], f"strip-3=${vres[name]['strip3']:,.0f}"))

    # ── per-regime and per-time-of-day for the leaders ──────────────────────────────────────────
    lead = sorted([k for k in vres if vres[k]["n"] >= 40], key=lambda k: -vres[k]["per"])[:4]
    for name in lead:
        tr = cache[name]
        print(f"\n── {name} · BY REGIME ──")
        print(by(tr, "regime").to_string(index=False))
        print(f"── {name} · BY TIME OF DAY ──")
        print(by(tr, "tod").to_string(index=False))
        print(f"── {name} · BY SIDE ──")
        print(by(tr, "side").to_string(index=False))
        print(f"── {name} · EXIT MIX ──")
        print(by(tr, "why").to_string(index=False))

    json.dump(dict(grid=grid, variants=vres,
                   n_fires=int(len(sig)), sessions=int(m1["day"].nunique())),
              open(f"{OUT}/gf_rider_exit.json", "w"), indent=1, default=str)
    for name in lead:
        cache[name].to_pickle(f"/home/alphabot/gazbot7/data/gf_rider/"
                              f"tr_{name.replace(' ', '_').replace('/', '-')}.pkl")
    print(f"\n→ {OUT}/gf_rider_exit.json")


if __name__ == "__main__":
    main()
