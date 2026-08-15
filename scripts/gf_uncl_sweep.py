#!/usr/bin/env python3
"""GF UNCLASS — STEP 2b/3: the ENTRY sweep, the FILTERS (each placebo-controlled), and the battery.

STEP 2 found the only positive shelf on the UNCLASS-eligible tape sits in the ASIA session
(00:00-06:00 UTC) with a WIDE stop and a FAR target — the same shape three other studies landed on
this week. Everything here tries to kill it.

  2b  ENTRY SWEEP      w x k, on the home segment. A plateau is an edge; a spike is a curve-fit.
  3   FILTERS          one causal cut at a time, each against a PLACEBO that discards the SAME
                       NUMBER of fires at random (a filter that only trades less is not a filter).
  4   BATTERY          placebo, shuffled-direction null, strip-3-best, leave-one-day-out,
                       leave-one-week-out, OOS leg, long/short symmetry, cost stress, per-regime.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_sweep.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gf_rider_engine import (Racer, run_trades, stat, line, by, strip_best, loo_days,  # noqa: E402
                             placebo, cost_stress)
from gf_rider_tape import build                                    # noqa: E402
from gf_uncl_ride import signals, segment                          # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CACHE = "/home/alphabot/gazbot7/data/gf_uncl"
HOME = "ASIA"
STOP, TARG, CAP = 2.5, 6.0, 120
OUT = {}


def main():
    os.makedirs(CACHE, exist_ok=True)
    m1, s5 = build()
    racer = Racer(s5)
    EX = dict(stop_a=STOP, targ_a=TARG, cap_min=CAP)

    # ══ 2b — ENTRY SWEEP on the home segment ═══════════════════════════════════════════════════
    print(f"══ 2b — ENTRY SWEEP on {HOME}, exit fixed at stop={STOP} targ={TARG} cap={CAP} ══")
    print("   (a PLATEAU across neighbouring cells is an edge; a lone spike is a curve fit)")
    sw = []
    print(f"   {'w\\k':<6}" + "".join(f"{k:>16}" for k in (1.0, 1.5, 2.0, 2.5, 3.0)))
    for w in (5, 10, 15, 20, 30):
        cells = []
        for k in (1.0, 1.5, 2.0, 2.5, 3.0):
            s = signals(m1, w, k)
            s = s[s.seg == HOME]
            t = run_trades(racer, s, **EX)
            st = stat(t)
            cells.append(f"${st['net']:>7,.0f}({st['n']:>3d})")
            sw.append(dict(w=w, k=k, **st))
        print(f"   {w:<6}" + "".join(f"{c:>16}" for c in cells))
    SW = pd.DataFrame(sw)
    OUT["entry_sweep"] = SW.to_dict("records")
    pos = (SW.net > 0).sum()
    print(f"   -> {pos}/{len(SW)} entry cells positive")
    OUT["entry_cells_positive"] = f"{pos}/{len(SW)}"

    # the shipping entry
    W, K = 10, 2.0
    sig_all = signals(m1, W, K)
    sig = sig_all[sig_all.seg == HOME].reset_index(drop=True)
    base = run_trades(racer, sig, **EX)
    print("\n" + line(f"BASE {HOME} w={W} k={K} {STOP}/{TARG}", stat(base)))
    OUT["base"] = stat(base)

    # ══ 3 — FILTERS, each with its own placebo ════════════════════════════════════════════════
    print(f"\n══ 3 — CAUSAL FILTERS on {HOME}, each vs a placebo that discards the SAME COUNT at random ══")
    cuts = {
        "rvol >= 1.0 (volume at/above its 30m mean)": sig.rvol >= 1.0,
        "rvol >= 1.3": sig.rvol >= 1.3,
        "atr_pr >= 0.40 (ATR in the upper 60% of 6h)": sig.atr_pr >= 0.40,
        "atr_pr >= 0.60": sig.atr_pr >= 0.60,
        "atr_pr <= 0.60 (do NOT chase an already-hot tape)": sig.atr_pr <= 0.60,
        "er15 >= 0.15 (the move is efficient)": sig.er15 >= 0.15,
        "er15 <= 0.15 (the move is NOT yet efficient)": sig.er15 <= 0.15,
        "atr >= 8pt (absolute vol floor, cross-session)": sig.atr >= 8.0,
        "atr >= 10pt": sig.atr >= 10.0,
        "SHORT only": sig.side < 0,
        "LONG only": sig.side > 0,
        "flow agrees with the thrust": (np.sign(sig.flow15.fillna(0)) == sig.side) & sig.has_flow,
        "00:00-03:00 only": sig.hh < 3,
        "03:00-06:00 only": sig.hh >= 3,
        "Mon-Thu (dow<4)": pd.to_datetime(sig.day).dt.dayofweek < 4,
    }
    frows = []
    for name, mask in cuts.items():
        s = sig[mask.values]
        if len(s) < 15:
            print(f"   {name:<52} n={len(s):<4} SKIPPED (n<15)")
            continue
        t = run_trades(racer, s, **EX)
        st = stat(t)
        pl = placebo(racer, sig, len(s), 200, **EX)
        verdict = "BEATS placebo p95" if st["per"] > pl["per_p95"] else "fails placebo"
        print(f"   {name:<52} n={st['n']:<4} net=${st['net']:>7,.0f} {st['win']:>5.1f}%w "
              f"${st['per']:>7.2f}/tr | placebo mean ${pl['per_mean']:>6.2f} p95 ${pl['per_p95']:>6.2f} -> {verdict}")
        frows.append(dict(cut=name, **st, pl_mean=pl["per_mean"], pl_p95=pl["per_p95"],
                          beats=st["per"] > pl["per_p95"]))
    OUT["filters"] = frows

    # ══ 4 — THE BATTERY ═══════════════════════════════════════════════════════════════════════
    print("\n══ 4 — THE BATTERY on the UNFILTERED home-segment rider ══")
    b = base

    # placebo on the entry itself: keep the same COUNT of fires, chosen at random from all eligible
    # ASIA minutes (not just thrust minutes) -> "is the thrust doing the work, or the session is?"
    allmin = m1[(segment(m1.hh) == HOME) & m1.atr.notna()].copy()
    allmin["side"] = np.where(np.arange(len(allmin)) % 2 == 0, 1, -1)   # deterministic 50/50
    allmin["entry"] = allmin["o"].shift(-1)
    allmin["ts_fill"] = allmin["ts"].shift(-1)
    pool = allmin[(allmin.ts_fill == allmin.ts + 60) & allmin.entry.notna()].copy()
    pool["ts"] = pool["ts_fill"].astype("int64")
    pool = pool[["ts", "side", "entry", "atr", "day"]].reset_index(drop=True)
    pl_any = placebo(racer, pool, len(b), 200, **EX)
    print(f"   PLACEBO  random ASIA minutes, random side, same n : "
          f"${pl_any['per_mean']:.2f}/tr mean, p95 ${pl_any['per_p95']:.2f}  (actual ${stat(b)['per']:.2f})")
    OUT["placebo_random_minute"] = pl_any

    # shuffled-direction null: the SAME entry timestamps, side flipped by a fixed alternating pattern
    sh = sig.copy()
    sh["side"] = np.where(np.arange(len(sh)) % 2 == 0, 1, -1)
    tsh = run_trades(racer, sh, **EX)
    print("   " + line("SHUFFLED-DIRECTION null", stat(tsh)))
    OUT["shuffled_direction"] = stat(tsh)

    # SHIFTED-SIGNAL placebo: keep every rule, move the signal series 30 minutes later
    shf = sig.copy()
    shf["ts"] = shf["ts"] + 1800
    ent = m1.set_index("ts")["o"]
    shf["entry"] = shf["ts"].map(ent)
    shf = shf[shf.entry.notna()]
    tsf = run_trades(racer, shf, **EX)
    print("   " + line("SHIFTED +30min (fake signal)", stat(tsf)))
    OUT["shift30"] = stat(tsf)

    print(f"   STRIP-3-BEST                          ${strip_best(b, 3):>8,.0f}  (from ${b.net.sum():,.0f})")
    print(f"   STRIP-5-BEST                          ${strip_best(b, 5):>8,.0f}")
    OUT["strip3"], OUT["strip5"] = strip_best(b, 3), strip_best(b, 5)

    lo = loo_days(b)
    print(f"   LEAVE-ONE-DAY-OUT worst               ${lo.iloc[0]['without']:>8,.0f}  "
          f"(dropping {lo.iloc[0]['day']}, which made ${lo.iloc[0]['day_net']:,.0f} on {lo.iloc[0]['n_day']:.0f} trades)")
    OUT["lodo_worst"] = lo.iloc[0].to_dict()

    b = b.copy()
    b["wk"] = pd.to_datetime(b["day"]).dt.strftime("%G-W%V")
    wk = b.groupby("wk").agg(n=("net", "size"), net=("net", "sum")).round(0)
    wk["without"] = (b.net.sum() - wk.net).round(0)
    print("\n   PER-ISO-WEEK ledger (and leave-one-week-out):")
    print(wk.to_string())
    OUT["weeks"] = wk.reset_index().to_dict("records")

    # OOS: everything before the lake starts (the V5 archive leg) vs the V7 leg
    cut = "2026-07-16"
    ins, oos = b[b.day >= cut], b[b.day < cut]
    print("\n   " + line(f"IN-SAMPLE  {cut}..", stat(ins)))
    print("   " + line(f"OOS (V5 archive leg, pre-{cut})", stat(oos)))
    OUT["oos"] = dict(ins=stat(ins), oos=stat(oos))

    print("\n   " + line("LONG only", stat(b[b.side > 0])))
    print("   " + line("SHORT only", stat(b[b.side < 0])))
    OUT["sides"] = dict(long=stat(b[b.side > 0]), short=stat(b[b.side < 0]))

    for m in (2.0, 3.0):
        print("   " + line(f"COST STRESS x{m:g} round trip", cost_stress(b, m)))
        OUT[f"cost_x{m:g}"] = cost_stress(b, m)

    print("\n   by REGIME (home segment only):")
    print(by(b, "regime").to_string(index=False))
    OUT["by_regime"] = by(b, "regime").to_dict("records")
    print("\n   by EXIT REASON:")
    print(by(b, "why").to_string(index=False))
    OUT["by_why"] = by(b, "why").to_dict("records")

    b.to_pickle(f"{CACHE}/base_trades.pkl")
    sig_all.to_pickle(f"{CACHE}/sig_all.pkl")
    json.dump(OUT, open(f"{SEC}/gf_uncl_sweep.json", "w"), indent=1, default=float)
    print(f"\n-> {SEC}/gf_uncl_sweep.json")


if __name__ == "__main__":
    main()
