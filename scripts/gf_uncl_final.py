#!/usr/bin/env python3
"""GF UNCLASS — STEP 5: the shipping candidate, the DECAY question, the escalation, the router.

The battery left one open wound: a monotone per-week decay ($1,758 in W26 down to ~$0 in W32/W33).
Before anything is shipped that has to be resolved — is it decay, or is it the ABSOLUTE volatility
floor the pooled study said was missing (the percentile vocabulary re-baselines every 6h and
structurally cannot see a quiet week)?

Then the operator's escalation: the full sat-out UNCLASS set -> top-15 -> top-10, to find the SIZE
THRESHOLD at which a footprint becomes tradeable, if any. And finally the router rule.

    PYTHONPATH=src .venv/bin/python scripts/gf_uncl_final.py
"""
from __future__ import annotations

import datetime as dt
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
from gf_uncl_members import census_rows                            # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
STOP, TARG, CAP = 2.5, 6.0, 120
OUT = {}


def wk(t):
    return pd.to_datetime(t["day"]).dt.strftime("%G-W%V")


def main():
    m1, s5 = build()
    racer = Racer(s5)
    EX = dict(stop_a=STOP, targ_a=TARG, cap_min=CAP)
    sig_all = signals(m1, 10, 2.0)

    # ══ A. IS IT DECAY, OR IS IT A MISSING ABSOLUTE VOL FLOOR? ════════════════════════════════
    print("══ A. THE DECAY QUESTION — per-week $/trade against that week's ASIA volatility ══")
    asia = sig_all[sig_all.seg == "ASIA"].reset_index(drop=True)
    base = run_trades(racer, asia, **EX)
    base["wk"] = wk(base)
    am = m1[segment(m1.hh) == "ASIA"].copy()
    am["wk"] = pd.to_datetime(am["day"]).dt.strftime("%G-W%V")
    vol = am.groupby("wk")["atr"].median().rename("asia_atr")
    t = base.groupby("wk").agg(n=("net", "size"), net=("net", "sum"), per=("net", "mean")).join(vol)
    print(t.round(2).to_string())
    c = t[["per", "asia_atr"]].corr().iloc[0, 1]
    print(f"   corr($/trade, that week's median ASIA ATR) = {c:+.2f}  (n={len(t)} weeks)")
    OUT["weeks_vs_vol"] = t.reset_index().round(3).to_dict("records")
    OUT["corr_per_vs_atr"] = round(float(c), 3)

    # ══ B. THE CANDIDATE — absolute ATR floor + "do not chase an already-hot tape" ════════════
    print("\n══ B. THE SHIPPING CANDIDATE — ASIA + absolute ATR floor + atr_pr cap ══")
    variants = {
        "UNCL-RIDER raw (ASIA only)": asia,
        "+ atr >= 8pt": asia[asia.atr >= 8],
        "+ atr >= 8pt + atr_pr <= 0.60": asia[(asia.atr >= 8) & (asia.atr_pr <= 0.60)],
        "+ atr >= 10pt + atr_pr <= 0.60": asia[(asia.atr >= 10) & (asia.atr_pr <= 0.60)],
        "+ atr >= 8pt + 00:00-03:00": asia[(asia.atr >= 8) & (asia.hh < 3)],
    }
    keep = {}
    for name, s in variants.items():
        tr = run_trades(racer, s, **EX)
        if not len(tr):
            continue
        tr["wk"] = wk(tr)
        st = stat(tr)
        w = tr.groupby("wk")["net"].sum()
        red = (w < 0).sum()
        print(line(name, st, f"strip3=${strip_best(tr,3):>7,.0f}  red-weeks={red}/{len(w)}  "
                             f"worst-week=${w.min():>7,.0f}"))
        keep[name] = tr
        OUT.setdefault("variants", []).append(dict(name=name, **st, strip3=strip_best(tr, 3),
                                                   red_weeks=int(red), n_weeks=int(len(w)),
                                                   worst_week=float(w.min())))

    CAND = "+ atr >= 8pt + atr_pr <= 0.60"
    cand = keep[CAND]
    print(f"\n   candidate = {CAND}")
    print("   per-week:")
    cw = cand.groupby("wk").agg(n=("net", "size"), net=("net", "sum"), per=("net", "mean")).round(2)
    print(cw.to_string())
    OUT["cand_weeks"] = cw.reset_index().to_dict("records")

    # placebo on the FILTERED candidate: same count, drawn from the raw ASIA fires
    pl = placebo(racer, asia, len(cand), 200, **EX)
    print(f"   placebo (same n drawn at random from the raw ASIA fires): mean ${pl['per_mean']:.2f} "
          f"p95 ${pl['per_p95']:.2f}   actual ${stat(cand)['per']:.2f}")
    OUT["cand_placebo"] = pl

    # shifted-signal placebo on the candidate
    sh = asia[(asia.atr >= 8) & (asia.atr_pr <= 0.60)].copy()
    sh["ts"] = sh["ts"] + 1800
    sh["entry"] = sh["ts"].map(m1.set_index("ts")["o"])
    sh = sh[sh.entry.notna()]
    tsh = run_trades(racer, sh, **EX)
    print("   " + line("SHIFTED +30min on the candidate", stat(tsh)))
    OUT["cand_shift30"] = stat(tsh)
    for mins in (10, 60, 120):
        s2 = asia[(asia.atr >= 8) & (asia.atr_pr <= 0.60)].copy()
        s2["ts"] = s2["ts"] + mins * 60
        s2["entry"] = s2["ts"].map(m1.set_index("ts")["o"])
        s2 = s2[s2.entry.notna()]
        print("   " + line(f"SHIFTED +{mins}min", stat(run_trades(racer, s2, **EX))))
        OUT[f"cand_shift{mins}"] = stat(run_trades(racer, s2, **EX))

    print("\n   " + line("LONG", stat(cand[cand.side > 0])))
    print("   " + line("SHORT", stat(cand[cand.side < 0])))
    lo = loo_days(cand)
    print(f"   LODO worst: ${lo.iloc[0]['without']:,.0f} (drop {lo.iloc[0]['day']})")
    for m in (2.0, 3.0):
        print("   " + line(f"COST x{m:g}", cost_stress(cand, m)))
    OUT["cand"] = dict(stat=stat(cand), long=stat(cand[cand.side > 0]), short=stat(cand[cand.side < 0]),
                       lodo_worst=float(lo.iloc[0]["without"]), strip3=strip_best(cand, 3),
                       cost_x2=cost_stress(cand, 2.0), cost_x3=cost_stress(cand, 3.0))

    # ══ C. DOES THE SAME POLICY REVIVE THE GRAVES? ════════════════════════════════════════════
    print("\n══ C. the same filter applied to the segments that were graves ══")
    for seg in ("EUROPE", "US-PM", "LATE"):
        s = sig_all[(sig_all.seg == seg) & (sig_all.atr >= 8) & (sig_all.atr_pr <= 0.60)]
        if len(s) < 20:
            continue
        tr = run_trades(racer, s, **EX)
        print("   " + line(f"{seg} + same floors", stat(tr), f"strip3=${strip_best(tr,3):>7,.0f}"))
        OUT.setdefault("graves", []).append(dict(seg=seg, **stat(tr), strip3=strip_best(tr, 3)))

    # ══ D. THE ESCALATION — does a footprint appear as the runs get BIGGER? ══════════════════
    print("\n══ D. ESCALATION — big-moves-caught on the sat-out UNCLASS runs, by size band ══")
    cr = census_rows()
    U = cr[(cr.cl == "UNCLASS") & (cr.us == "sat out")].copy()
    U["absmv"] = U["move"].abs()
    U = U.sort_values("absmv", ascending=False).reset_index(drop=True)
    # what the rider ACTUALLY did around each run: any trade opened in [start-5min, start+15min]
    allsig = sig_all[(sig_all.atr >= 8) & (sig_all.atr_pr <= 0.60)]
    allt = run_trades(racer, allsig, **EX)          # all eligible hours, floors on
    rows = []
    for r in U.itertuples():
        near = allt[(allt.ts >= r.ts - 300) & (allt.ts <= r.ts + 900)]
        aligned = near[near.side == (1 if r.move > 0 else -1)]
        rows.append(dict(tm=r.tm, absmv=r.absmv, ceil=r.ceil, n_near=len(near),
                         n_aligned=len(aligned), net=float(aligned.net.sum()) if len(aligned) else 0.0,
                         boarded=len(aligned) > 0))
    B = pd.DataFrame(rows)
    for band, sub in (("ALL 34", B), ("top-25", B.head(25)), ("top-15", B.head(15)),
                      ("top-10", B.head(10)), ("top-5", B.head(5))):
        print(f"   {band:<8} boarded {sub.boarded.sum():>2}/{len(sub)}  net ${sub.net.sum():>8,.0f}  "
              f"ceiling ${sub.ceil.sum():>6,.0f}  capture {100*sub.net.sum()/sub.ceil.sum():>5.1f}%")
        OUT.setdefault("escalation", []).append(dict(band=band, boarded=int(sub.boarded.sum()),
                                                     of=len(sub), net=float(sub.net.sum()),
                                                     ceil=float(sub.ceil.sum())))
    print("\n   run-by-run:")
    print(B.round(1).to_string(index=False))
    OUT["runs"] = B.to_dict("records")

    # ══ E. THE CENSUS WEEK ITSELF ═════════════════════════════════════════════════════════════
    print("\n══ E. THE CENSUS WEEK (2026-08-09..08-14) ══")
    cwk = cand[cand.day >= "2026-08-09"]
    print("   " + line("candidate, census week", stat(cwk)))
    allwk = allt[allt.day >= "2026-08-09"]
    print("   " + line("all eligible hours, floors on, census week", stat(allwk)))
    OUT["census_week"] = dict(cand=stat(cwk), all_eligible=stat(allwk))

    json.dump(OUT, open(f"{SEC}/gf_uncl_final.json", "w"), indent=1, default=float)
    print(f"\n-> {SEC}/gf_uncl_final.json")


if __name__ == "__main__":
    main()
