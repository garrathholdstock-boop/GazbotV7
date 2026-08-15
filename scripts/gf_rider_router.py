#!/usr/bin/env python3
"""GF RIDER · STEP 4 — the arm/bench rule in the LIVE ROUTER'S vocabulary, plus a hard validation.

The router speaks in ER / ATR / structure-break / session / the untradeable meter. A finding that
cannot be said in those words cannot be shipped, so this translates the survivor and then prices the
translation — including an honest leave-one-WEEK-out, because a 9-week study with one bad week needs
to show what happens when any single week is removed.

Ends with a TICK-LEVEL VALIDATION of the exit racer: three trades re-priced by hand off raw ticks
from the lake, to prove the 5-second racer is not flattering itself.

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_router.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.lake import connect  # noqa: E402
from gf_rider_engine import (FEE, SLIP, VPP, Racer, by, line, placebo,  # noqa: E402
                             run_trades, stat, strip_best)
from gf_rider_signals import signals  # noqa: E402
from gf_rider_tape import build  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
pd.set_option("display.width", 250)
W, K = 10, 2.0
EXIT = dict(stop_a=3.0, targ_a=6.0, cap_min=120)
R: dict = {}


def hdr(t):
    print("\n" + "=" * 118 + f"\n  {t}\n" + "=" * 118)


def main():
    m1, s5 = build()
    racer = Racer(s5)
    sig = signals(m1, W, K)
    us = sig[sig["tod"] != "overnight"].reset_index(drop=True)

    hdr("4 · THE ARM / BENCH RULE — swept, not guessed. Each floor is causal (trailing only).")
    rows = []
    print(f"  {'rule':<34s} {'n':>5s} {'net$':>9s} {'$/tr':>8s} {'win%':>6s} {'strip3$':>9s} "
          f"{'placebo p95':>12s}  verdict")
    RULES = {
        "no floor (session only)":      lambda d: d["ts"] > 0,
        "ATR >= 8pt":                   lambda d: d["atr"] >= 8,
        "ATR >= 10pt":                  lambda d: d["atr"] >= 10,
        "ATR >= 12pt":                  lambda d: d["atr"] >= 12,
        "ATR >= 14pt":                  lambda d: d["atr"] >= 14,
        "ATR >= 16pt":                  lambda d: d["atr"] >= 16,
        "atr_pr >= 0.40":               lambda d: d["atr_pr"] >= 0.40,
        "atr_pr >= 0.50":               lambda d: d["atr_pr"] >= 0.50,
        "atr_pr >= 0.60":               lambda d: d["atr_pr"] >= 0.60,
        "rvol >= 1.0":                  lambda d: d["rvol"] >= 1.0,
        "rvol >= 1.2":                  lambda d: d["rvol"] >= 1.2,
        "rvol>=1.0 & atr_pr>=0.40":     lambda d: (d["rvol"] >= 1.0) & (d["atr_pr"] >= 0.40),
        "rvol>=1.0 & ATR>=10pt":        lambda d: (d["rvol"] >= 1.0) & (d["atr"] >= 10),
    }
    for nm, fn in RULES.items():
        sub = us[fn(us)].reset_index(drop=True)
        t = run_trades(racer, sub, **EXIT)
        if len(t) < 25:
            print(f"  {nm:<34s} n={len(t)} — too thin")
            continue
        s0, pl = stat(t), placebo(racer, us, len(sub), 15, **EXIT)
        ok = s0["per"] > pl["per_p95"]
        rows.append(dict(rule=nm, **s0, strip3=strip_best(t, 3), plac_p95=pl["per_p95"], beats=ok))
        print(f"  {nm:<34s} {s0['n']:>5d} {s0['net']:>9,.0f} {s0['per']:>8.2f} {s0['win']:>6.1f} "
              f"{strip_best(t,3):>9,.0f} {pl['per_p95']:>12.2f}  "
              f"{'BEATS placebo' if ok else 'fails placebo'}")
    R["router_rules"] = rows

    # ── the chosen rule, and leave-one-WEEK-out ────────────────────────────────────────────────
    chosen = us[(us["rvol"] >= 1.0) & (us["atr_pr"] >= 0.40)].reset_index(drop=True)
    tr = run_trades(racer, chosen, **EXIT)
    hdr("LEAVE-ONE-WEEK-OUT — a 9-week study with one bad week has to survive losing ANY week")
    tr = tr.copy()
    tr["wk"] = tr["day"].map(lambda d: pd.Timestamp(d).strftime("%G-W%V"))
    tot = tr["net"].sum()
    print(line("chosen rule: US session + rvol>=1.0 + atr_pr>=0.40", stat(tr),
               f"strip3=${strip_best(tr,3):,.0f}"))
    print()
    loo = []
    for w, g in tr.groupby("wk"):
        loo.append(dict(week=w, n=len(g), week_net=round(g["net"].sum(), 0),
                        without=round(tot - g["net"].sum(), 0),
                        per_without=round((tot - g["net"].sum()) / (len(tr) - len(g)), 2)))
    loo = pd.DataFrame(loo).sort_values("without")
    print(loo.to_string(index=False))
    print(f"\n  worst leave-one-week-out net = ${loo['without'].min():,.0f} "
          f"({'still GREEN' if loo['without'].min() > 0 else 'goes RED'}); "
          f"green weeks {int((loo['week_net']>0).sum())} of {len(loo)}")
    R["loo_week"] = loo.to_dict("records")

    print("\n  by regime — the HOME segment, which is where the expectancy is quoted:")
    print(by(tr, "regime").to_string(index=False))
    home = tr[tr["regime"].isin(["violent-whipsaw", "clean-trend"])]
    print(line("\n  HOME (violent-whipsaw + clean-trend)", stat(home),
               f"strip3=${strip_best(home,3):,.0f}"))
    away = tr[~tr["regime"].isin(["violent-whipsaw", "clean-trend"])]
    print(line("  AWAY (the three chop buckets)", stat(away)))
    R["home"] = stat(home)
    R["away"] = stat(away)

    # ── tick-level validation of the racer ─────────────────────────────────────────────────────
    hdr("VALIDATION — re-price three trades by hand off RAW TICKS. The racer must not flatter itself.")
    con = connect(symbol="MNQ")
    sample = tr.sort_values("net").iloc[[0, len(tr)//2, -1]]
    ok = True
    for r in sample.itertuples():
        atr = float(r.atr)
        stop_pt, targ_pt = 3.0 * atr, 6.0 * atr
        t0, t1 = int(r.ts), int(r.ts) + 120 * 60
        q = con.execute(
            "SELECT ts_ms//1000 AS t, price FROM ticks WHERE ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
            [t0 * 1000, t1 * 1000]).df()
        if not len(q):
            print(f"  {r.day} {r.hh:.2f}  side={r.side:+d}  — no tick tape for this day "
                  f"(5s bars only); cannot hand-check")
            continue
        e = float(r.entry_px)
        fav = (q["price"] - e) * r.side
        adv = -fav
        hs = np.nonzero((adv >= stop_pt).to_numpy())[0]
        ht = np.nonzero((fav >= targ_pt).to_numpy())[0]
        si = hs[0] if len(hs) else 10**9
        ti = ht[0] if len(ht) else 10**9
        if si <= ti and si < 10**9:
            why, px = "STOP", e - r.side * stop_pt
        elif ti < 10**9:
            why, px = "TARGET", e + r.side * targ_pt
        else:
            why, px = "TIME_CAP", float(q["price"].iloc[-1])
        net = ((px - e) * r.side - SLIP) * VPP - FEE
        match = (why == r.why)
        ok &= bool(match)
        print(f"  {r.day} {r.hh:5.2f} side={r.side:+d} atr={atr:5.1f}  "
              f"5s-racer: {r.why:<9s} ${r.net:>8.2f}   tick-truth: {why:<9s} ${net:>8.2f}   "
              f"{'MATCH' if match else 'DIFFER'}")
    print(f"\n  racer verdict: {'consistent with the raw ticks' if ok else 'DIVERGES — see above'}")
    con.close()

    tr.to_pickle("/home/alphabot/gazbot7/data/gf_rider/tr_router.pkl")
    json.dump(R, open(f"{OUT}/gf_rider_router.json", "w"), indent=1, default=str)
    print(f"\n→ {OUT}/gf_rider_router.json")


if __name__ == "__main__":
    main()
