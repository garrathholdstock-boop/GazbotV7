#!/usr/bin/env python3
"""GF RIDER · STEP 3 — THEN FILTER. Every cut causal, every cut placebo-controlled.

The known failure mode, not a surprise: BOARD fires on ordinary tape too. Step 2 priced it across a
wide stop x target grid and the POOLED tape is a coin — but one split was positive in all 24 (w,k)
cells: the US session. So the cuts get tested properly here.

★ THE RULES OF THIS STEP, which the desk has been burned by ignoring:
  1. A filter may only read information available BEFORE the fill. Every column used comes from the
     signal bar's CLOSE or earlier.
  2. Every cut is measured against a PLACEBO that discards the same NUMBER of fires at random. A
     filter that keeps 40 of 100 must beat a coin that keeps 40 of 100 — otherwise it "worked" by
     trading less, which any random rule does for free.
  3. Every cut reports what it COSTS in forgone winners, not only what it saves.

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_filter.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_rider_board import sat_out_runs  # noqa: E402
from gf_rider_engine import (Racer, by, cost_stress, line, loo_days, placebo,  # noqa: E402
                             run_trades, stat, strip_best)
from gf_rider_signals import signals  # noqa: E402
from gf_rider_tape import build  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
pd.set_option("display.width", 250)
W, K = 10, 2.0                      # reach 58/60 sat-out runs; see gf_rider_entry.py for the sweep
BASE = dict(stop_a=3.0, targ_a=6.0, cap_min=120)
R: dict = {}


def hdr(t):
    print("\n" + "=" * 118 + f"\n  {t}\n" + "=" * 118)


def main():
    m1, s5 = build()
    racer = Racer(s5)
    runs = sat_out_runs()
    sessions = m1["day"].nunique()
    sig = signals(m1, W, K)
    hdr(f"STEP 3 · FILTER — BOARD(w={W}, k={K}) · {sessions} sessions · {len(sig):,} raw fires")

    # ── 3a. the exit plateau ON THE US SESSION, where step 2 said the money is ────────────────
    us = sig[sig["tod"] != "overnight"].reset_index(drop=True)
    on = sig[sig["tod"] == "overnight"].reset_index(drop=True)
    print(f"\nfires: US 13:00-20:00Z {len(us):,}  ·  overnight {len(on):,}")

    hdr("3a · STOP x TARGET again, US SESSION ONLY — is the optimum a SHELF or one lucky cell?")
    STOPS, TARGS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0], [2.0, 3.0, 4.0, 6.0, 8.0, np.inf]
    print("   cell = $/trade (n)\n")
    print("  stop\\targ " + "".join(f"{('HOLD' if not np.isfinite(t) else f'{t:.0f}R'):>15s}" for t in TARGS))
    plateau, cells = {}, {}
    for s in STOPS:
        row = f"  {s:>4.1f}xATR "
        for t in TARGS:
            tr = run_trades(racer, us, stop_a=s, targ_a=t, cap_min=120)
            cells[(s, t)] = tr
            st = stat(tr)
            plateau[f"{s}_{t}"] = st
            row += f"{st['per']:>9.2f}({st['n']:>3d})"
        print(row)
    npos = sum(1 for v in plateau.values() if v["per"] > 0)
    print(f"\n  positive cells: {npos} of {len(plateau)}  "
          f"— a shelf is robustness, a single green square in a red field is a curve-fit")
    R["plateau_us"] = plateau

    hdr("3b · THE OVERNIGHT CUT — the first filter, and it is just the clock")
    tr_all = run_trades(racer, sig, **BASE)
    tr_us = run_trades(racer, us, **BASE)
    tr_on = run_trades(racer, on, **BASE)
    print(line("ALL fires (no filter)", stat(tr_all), f"strip-3=${strip_best(tr_all,3):,.0f}"))
    print(line("US session only", stat(tr_us), f"strip-3=${strip_best(tr_us,3):,.0f}"))
    print(line("overnight only", stat(tr_on), f"strip-3=${strip_best(tr_on,3):,.0f}"))
    keep = len(tr_us) / max(len(tr_all), 1)
    print(f"\n  the cut keeps {100*keep:.0f}% of the fires. PLACEBO — keep the same NUMBER at random:")
    pl = placebo(racer, sig, len(us), 25, **BASE)
    print(f"    {pl}")
    print(f"    US-session actual ${stat(tr_us)['per']:.2f}/tr  vs  placebo mean "
          f"${pl.get('per_mean', 0):.2f}/tr (p95 ${pl.get('per_p95', 0):.2f})")
    R["overnight_cut"] = dict(all=stat(tr_all), us=stat(tr_us), on=stat(tr_on), placebo=pl)

    print("\n  what the cut COSTS — the winners it throws away:")
    wins_lost = tr_on[tr_on["net"] > 0]
    print(f"    overnight fires binned: {len(tr_on)} trades, of which {len(wins_lost)} winners "
          f"worth ${wins_lost['net'].sum():,.0f}; the losers it avoids are "
          f"${-tr_on[tr_on['net']<=0]['net'].sum():,.0f}. Net saved ${-tr_on['net'].sum():,.0f}.")
    print("\n  by hour of day (UTC), all fires, to show the cut is not a two-hour artefact:")
    tr_all["hr"] = (tr_all["hh"] // 1).astype(int)
    print(by(tr_all, "hr").sort_values("k").to_string(index=False))

    # ── 3c. single-filter table, each placebo-controlled ──────────────────────────────────────
    hdr("3c · EVERY OTHER CAUSAL CUT, one at a time, on top of the US-session base")
    base_st = stat(tr_us)
    print(line("BASE = US session only", base_st))
    print()
    FILTERS = {
        "ATR percentile >= 0.50":   lambda d: d["atr_pr"] >= 0.50,
        "ATR percentile >= 0.70":   lambda d: d["atr_pr"] >= 0.70,
        "ATR >= 8pt (absolute)":    lambda d: d["atr"] >= 8.0,
        "ATR >= 12pt (absolute)":   lambda d: d["atr"] >= 12.0,
        "ER15 >= 0.15":             lambda d: d["er15"] >= 0.15,
        "ER15 >= 0.25":             lambda d: d["er15"] >= 0.25,
        "ER30 >= 0.15":             lambda d: d["er30"] >= 0.15,
        "rvol >= 1.0":              lambda d: d["rvol"] >= 1.0,
        "rvol >= 1.5":              lambda d: d["rvol"] >= 1.5,
        "extension cap ext<=3xATR": lambda d: d["ext_r"] <= 3.0,
        "extension cap ext<=4xATR": lambda d: d["ext_r"] <= 4.0,
        "pullback >= 0.25xATR":     lambda d: d["pull_r"] >= 0.25,
        "pullback >= 0.5xATR":      lambda d: d["pull_r"] >= 0.5,
        "structure break (30m)":    lambda d: d["prove_r"] >= 2.5,
        "flow aligned (flow days)": lambda d: d["flow_align"].fillna(False).astype(bool),
    }
    frows = []
    for name, fn in FILTERS.items():
        sub = us[fn(us)].reset_index(drop=True)
        if len(sub) < 20:
            print(f"  {name:<28s} — only {len(sub)} fires, not scoreable")
            continue
        tr = run_trades(racer, sub, **BASE)
        st = stat(tr)
        if st["n"] < 20:
            print(f"  {name:<28s} — only {st['n']} trades, not scoreable")
            continue
        pl = placebo(racer, us, len(sub), 15, **BASE)
        # what it costs: winners in the BASE book that this filter would have removed
        kept_ts = set(tr["ts"])
        lost = tr_us[~tr_us["ts"].isin(kept_ts)]
        lost_w = lost[lost["net"] > 0]
        frows.append(dict(filt=name, n=st["n"], net=st["net"], per=st["per"], win=st["win"],
                          pf=st["pf"], strip3=strip_best(tr, 3),
                          plac_per=pl.get("per_mean", np.nan), plac_p95=pl.get("per_p95", np.nan),
                          beats_placebo=st["per"] > pl.get("per_p95", 1e9),
                          lost_winners=len(lost_w), lost_win_usd=round(lost_w["net"].sum(), 0)))
        f = frows[-1]
        print(f"  {name:<28s} n={st['n']:>4d} net=${st['net']:>7,.0f} ${st['per']:>7.2f}/tr "
              f"{st['win']:>5.1f}%w  strip3=${f['strip3']:>7,.0f}  "
              f"placebo ${f['plac_per']:>6.2f} (p95 ${f['plac_p95']:>6.2f}) "
              f"{'BEATS' if f['beats_placebo'] else 'fails':>5s}  "
              f"cost: {f['lost_winners']:>3d} winners / ${f["lost_win_usd"]:>7,.0f}")
    R["filters"] = frows
    json.dump(R, open(f"{OUT}/gf_rider_filter.json", "w"), indent=1, default=str)
    us.to_pickle("/home/alphabot/gazbot7/data/gf_rider/sig_us.pkl")
    sig.to_pickle("/home/alphabot/gazbot7/data/gf_rider/sig_all.pkl")
    print(f"\n→ {OUT}/gf_rider_filter.json")


if __name__ == "__main__":
    main()
