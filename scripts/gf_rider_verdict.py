#!/usr/bin/env python3
"""GF RIDER · the verdict pass — the tight variant, the week-by-week ledger, and WHY the census
week failed. Plus the run chart the operator asks for (real price path, entries and exits marked).

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_verdict.py
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
W, K = 10, 2.0
EXIT = dict(stop_a=3.0, targ_a=6.0, cap_min=120)
R: dict = {}


def hdr(t):
    print("\n" + "=" * 118 + f"\n  {t}\n" + "=" * 118)


def week_of(d: str) -> str:
    return pd.Timestamp(d).strftime("%G-W%V")


def main():
    m1, s5 = build()
    racer = Racer(s5)
    runs = sat_out_runs()
    sig = signals(m1, W, K)
    us = sig[sig["tod"] != "overnight"].reset_index(drop=True)
    tight = us[us["hh"] < 15.0].reset_index(drop=True)

    tr_us = run_trades(racer, us, **EXIT)
    tr_tt = run_trades(racer, tight, **EXIT)

    hdr("THE TIGHT VARIANT — RIDER_OPEN: same rule, 13:00-15:00Z only (the US cash open)")
    print(line("RIDER_ALL  (13:00-20:00Z)", stat(tr_us), f"strip3=${strip_best(tr_us,3):,.0f}"))
    print(line("RIDER_OPEN (13:00-15:00Z)", stat(tr_tt), f"strip3=${strip_best(tr_tt,3):,.0f}"))
    print(f"\n  RIDER_OPEN keeps {100*len(tr_tt)/len(tr_us):.0f}% of the trades and "
          f"{100*tr_tt['net'].sum()/tr_us['net'].sum():.0f}% of the money.")
    for nm, t in (("RIDER_ALL", tr_us), ("RIDER_OPEN", tr_tt)):
        print(f"\n{nm} · BY REGIME\n" + by(t, "regime").to_string(index=False))
        print(f"{nm} · BY SIDE\n" + by(t, "side").to_string(index=False))
    R["tight"] = dict(all=stat(tr_us), open=stat(tr_tt),
                      open_strip3=strip_best(tr_tt, 3),
                      open_regime=by(tr_tt, "regime").to_dict("records"))

    hdr("THE WEEK-BY-WEEK LEDGER — is the census week an outlier, or is the edge decaying?")
    for nm, t in (("RIDER_ALL", tr_us), ("RIDER_OPEN", tr_tt)):
        t = t.copy()
        t["wk"] = t["day"].map(week_of)
        w = by(t, "wk").sort_values("k")
        w["atr"] = [round(float(t[t["wk"] == k]["atr"].median()), 1) for k in w["k"]]
        print(f"\n{nm}\n" + w.to_string(index=False))
        R[f"weeks_{nm}"] = w.to_dict("records")

    hdr("WHY THE CENSUS WEEK (08-10..08-14) CAME OUT FLAT — the diagnosis, not an excuse")
    wk = tr_us[tr_us["day"] >= "2026-08-10"]
    wkt = tr_tt[tr_tt["day"] >= "2026-08-10"]
    print(line("RIDER_ALL, census week", stat(wk)))
    print(line("RIDER_OPEN, census week", stat(wkt)))

    print("\n  1) THE WEEK WAS THE QUIETEST ON THE TAPE. Median 1-min ATR by week:")
    a = m1.copy()
    a["wk"] = a["day"].map(week_of)
    print(a.groupby("wk")["atr"].median().round(2).to_string())

    print("\n  2) THE RIDER'S HOME REGIMES BARELY OCCURRED. Share of US-session minutes by regime:")
    us_min = m1[(m1["hh"] >= 13.0) & (m1["hh"] < 20.0)].copy()
    us_min["wk"] = us_min["day"].map(week_of)
    mix = (us_min.groupby(["wk", "regime"]).size().unstack(fill_value=0))
    mix = (100 * mix.div(mix.sum(axis=1), axis=0)).round(1)
    print(mix.to_string())

    print("\n  3) THE 13:30Z ATR SPIKE. Entries taken in the 13:30-14:00Z window carry an ATR")
    print("     computed over a trailing 30 minutes that CONTAINS the opening burst, so the stop is")
    print("     sized off a number the following tape does not sustain. Those fires, all sessions:")
    for t, nm in ((tr_us, "RIDER_ALL"), (tr_tt, "RIDER_OPEN")):
        sp = t[(t["hh"] >= 13.5) & (t["hh"] < 14.0)]
        rest = t[~((t["hh"] >= 13.5) & (t["hh"] < 14.0))]
        print(line(f"  {nm} 13:30-14:00Z fires", stat(sp)))
        print(line(f"  {nm} everything else", stat(rest)))
    R["spike"] = dict(all_spike=stat(tr_us[(tr_us["hh"] >= 13.5) & (tr_us["hh"] < 14.0)]),
                      all_rest=stat(tr_us[~((tr_us["hh"] >= 13.5) & (tr_us["hh"] < 14.0))]))

    hdr("THE 13:30 CARVE-OUT — a causal cut (it is the clock), placebo-controlled like the rest")
    v = us[~((us["hh"] >= 13.5) & (us["hh"] < 14.0))].reset_index(drop=True)
    tr_v = run_trades(racer, v, **EXIT)
    pl = placebo(racer, us, len(v), 20, **EXIT)
    print(line("RIDER_ALL minus 13:30-14:00Z", stat(tr_v), f"strip3=${strip_best(tr_v,3):,.0f}"))
    print(f"  placebo (same count at random): mean ${pl['per_mean']}/tr p95 ${pl['per_p95']}/tr "
          f"— {'BEATS' if stat(tr_v)['per'] > pl['per_p95'] else 'fails'}")
    wv = tr_v[tr_v["day"] >= "2026-08-10"]
    print(line("  ... in the census week", stat(wv)))
    lost = tr_us[~tr_us["ts"].isin(set(tr_v["ts"]))]
    print(f"  cost of the carve-out: {len(lost[lost['net']>0])} winners worth "
          f"${lost[lost['net']>0]['net'].sum():,.0f} forgone")
    R["carveout"] = dict(stat=stat(tr_v), placebo=pl, week=stat(wv),
                         strip3=strip_best(tr_v, 3))

    hdr("BIG-MOVES-CAUGHT — against the exact 60 runs the census proved we missed")
    for nm, t in (("RIDER_ALL", wk), ("RIDER_OPEN", wkt), ("RIDER_ALL minus 13:30", wv)):
        c, cn = [], 0.0
        for r in runs.itertuples():
            ov = t[(t["ts"] <= r.ts + 900) & (t["ts"] + t["held_s"] >= r.ts) & (t["side"] == r.dirn)]
            if len(ov):
                c.append(r.label)
                cn += ov["net"].sum()
        print(f"  {nm:<24s} {len(c):>2d}/60 runs boarded · ${cn:>8,.0f} banked on them · "
              f"total week ${t['net'].sum():>8,.0f}")
        R[f"caught_{nm}"] = dict(n=len(c), net=round(cn, 0), labels=c)

    tr_v.to_pickle("/home/alphabot/gazbot7/data/gf_rider/tr_carveout.pkl")
    tr_tt.to_pickle("/home/alphabot/gazbot7/data/gf_rider/tr_open.pkl")
    json.dump(R, open(f"{OUT}/gf_rider_verdict.json", "w"), indent=1, default=str)
    print(f"\n→ {OUT}/gf_rider_verdict.json")


if __name__ == "__main__":
    main()
