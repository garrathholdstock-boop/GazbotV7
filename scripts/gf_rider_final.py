#!/usr/bin/env python3
"""GF RIDER · STEPS 4 & 5 — the survivor's full battery, its router rule, and the honest prize.

Takes the one candidate that came through steps 1-3 and tries to kill it with everything the desk
has: strip-the-best, leave-one-day-out, both-halves, a true out-of-sample leg that sits entirely
BEFORE the census week, cost stress, long/short symmetry, a shuffled-direction null, and the
entry/exit parameter plateaus. Then prices the prize twice — ORACLE (perfect filtering, cheats) and
CAUSAL (what a rule that only sees the past could have taken).

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_final.py
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
from gf_rider_engine import (FEE, SLIP, VPP, Racer, by, cost_stress, line,  # noqa: E402
                             loo_days, placebo, run_trades, stat, strip_best)
from gf_rider_signals import signals  # noqa: E402
from gf_rider_tape import build  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
pd.set_option("display.width", 250)

W, K = 10, 2.0
EXIT = dict(stop_a=3.0, targ_a=6.0, cap_min=120)
CENSUS_WEEK = ("2026-08-10", "2026-08-14")
R: dict = {}


def hdr(t):
    print("\n" + "=" * 118 + f"\n  {t}\n" + "=" * 118)


def us_only(sig):
    return sig[sig["tod"] != "overnight"].reset_index(drop=True)


def main():
    m1, s5 = build()
    racer = Racer(s5)
    runs = sat_out_runs()
    sig = signals(m1, W, K)
    us = us_only(sig)
    tr = run_trades(racer, us, **EXIT)
    hdr(f"THE SURVIVOR — RIDER_ALL: BOARD(w={W}, k={K}xATR) · US session 13:00-20:00Z · "
        f"stop 3.0xATR / target 6.0xATR / 120min cap")
    print(line("headline", stat(tr)))
    R["headline"] = stat(tr)

    # ── 4a. per-regime and per-session-half: the HOME segments ────────────────────────────────
    hdr("4a · WHERE IT LIVES — per regime, per hour, per side. Never a blanket cross-tape number.")
    print("BY REGIME\n" + by(tr, "regime").to_string(index=False))
    tr["hr"] = tr["hh"].astype(int)
    print("\nBY HOUR (UTC)\n" + by(tr, "hr").sort_values("k").to_string(index=False))
    print("\nBY SIDE (long/short symmetry — an edge on one side only is half a finding)\n"
          + by(tr, "side").to_string(index=False))
    print("\nEXIT MIX\n" + by(tr, "why").to_string(index=False))
    R["regime"] = by(tr, "regime").to_dict("records")
    R["hour"] = by(tr, "hr").to_dict("records")
    R["side"] = by(tr, "side").to_dict("records")

    # ── 4b. the robustness battery ─────────────────────────────────────────────────────────────
    hdr("4b · THE BATTERY — every named test that is allowed to kill it")
    tot = tr["net"].sum()
    b = {}
    b["strip_best_1"] = strip_best(tr, 1)
    b["strip_best_3"] = strip_best(tr, 3)
    b["strip_best_5"] = strip_best(tr, 5)
    b["strip_best_third"] = strip_best(tr, len(tr) // 3)
    print(f"  strip the best 1 trade   ${b['strip_best_1']:>9,.0f}   (of ${tot:,.0f})")
    print(f"  strip the best 3 trades  ${b['strip_best_3']:>9,.0f}")
    print(f"  strip the best 5 trades  ${b['strip_best_5']:>9,.0f}")
    print(f"  strip the best THIRD     ${b['strip_best_third']:>9,.0f}   "
          f"({len(tr)//3} of {len(tr)} trades removed)")

    loo = loo_days(tr)
    print(f"\n  leave-one-day-out: {len(loo)} sessions, "
          f"net without the best-contributing day = ${loo['without'].min():,.0f}, "
          f"worst-case still {'GREEN' if loo['without'].min() > 0 else 'RED'}")
    print(loo.head(5).to_string(index=False))
    b["loo_min"] = float(loo["without"].min())
    b["loo_green_days"] = int((loo["day_net"] > 0).sum())
    b["loo_days"] = int(len(loo))
    print(f"  green sessions: {b['loo_green_days']} of {b['loo_days']}")

    days = sorted(tr["day"].unique())
    h1, h2 = days[:len(days)//2], days[len(days)//2:]
    for nm, dd in (("first half", h1), ("second half", h2)):
        print(line(f"  {nm} ({dd[0]}..{dd[-1]})", stat(tr[tr['day'].isin(dd)])))
        b[nm.replace(" ", "_")] = stat(tr[tr["day"].isin(dd)])

    # OOS leg: everything BEFORE the census week is one sample, the census week is the other
    pre = tr[tr["day"] < CENSUS_WEEK[0]]
    wk = tr[(tr["day"] >= CENSUS_WEEK[0]) & (tr["day"] <= CENSUS_WEEK[1])]
    print("\n  ★ THE OOS LEG — the rule was shaped on the census week's question, so the 39 sessions")
    print("    BEFORE 08-10 are the out-of-sample test, and they are the bigger sample:")
    print(line("  pre-census-week (OOS)", stat(pre)))
    print(line("  the census week itself", stat(wk)))
    b["oos_pre"], b["census_week"] = stat(pre), stat(wk)

    print(line("\n  cost stress x2 (all-in $5.00/RT)", cost_stress(tr, 2.0)))
    print(line("  cost stress x3 (all-in $7.50/RT)", cost_stress(tr, 3.0)))
    b["cost_x2"], b["cost_x3"] = cost_stress(tr, 2.0), cost_stress(tr, 3.0)

    # shuffled-direction null: same entries, coin-flip side
    rng = np.random.default_rng(11)
    nulls = []
    for i in range(20):
        s = us.copy()
        s["side"] = rng.choice([-1, 1], size=len(s))
        nulls.append(run_trades(racer, s, **EXIT)["net"].mean())
    print(f"\n  shuffled-direction null (same entries, coin-flip side, 20 reps): "
          f"mean ${np.mean(nulls):.2f}/tr, p95 ${np.percentile(nulls,95):.2f}/tr "
          f"vs actual ${stat(tr)['per']:.2f}/tr")
    b["shuffle_null_mean"] = round(float(np.mean(nulls)), 2)
    b["shuffle_null_p95"] = round(float(np.percentile(nulls, 95)), 2)

    pl = placebo(racer, sig, len(us), 25, **EXIT)
    b["placebo"] = pl
    print(f"  placebo (discard the same NUMBER at random, 25 reps): mean ${pl['per_mean']}/tr, "
          f"p95 ${pl['per_p95']}/tr vs actual ${stat(tr)['per']:.2f}/tr")
    R["battery"] = b

    # ── 4c. parameter plateaus ─────────────────────────────────────────────────────────────────
    hdr("4c · PARAMETER PLATEAUS — is this a shelf or a spike? (edge only at one cell = curve-fit)")
    print("ENTRY (w, k), exit held at 3.0/6R, US session only:\n")
    print(f"  {'w':>3s} {'k':>4s} {'n':>5s} {'net$':>9s} {'$/tr':>8s} {'win%':>6s} {'strip3$':>9s}")
    ent = []
    for w in (5, 10, 15, 20, 30):
        for k in (1.5, 2.0, 2.5, 3.0, 4.0):
            s = us_only(signals(m1, w, k))
            t = run_trades(racer, s, **EXIT)
            st = stat(t)
            if st["n"] < 25:
                continue
            ent.append(dict(w=w, k=k, **st, strip3=strip_best(t, 3)))
            print(f"  {w:>3d} {k:>4.1f} {st['n']:>5d} {st['net']:>9,.0f} {st['per']:>8.2f} "
                  f"{st['win']:>6.1f} {strip_best(t,3):>9,.0f}")
    R["entry_plateau"] = ent
    print(f"\n  positive $/trade in {sum(1 for e in ent if e['per']>0)} of {len(ent)} entry cells")

    print("\nEXIT (stop, target), entry held at BOARD(10, 2.0), US session only:\n")
    print(f"  {'stop':>5s} {'targ':>6s} {'n':>5s} {'net$':>9s} {'$/tr':>8s} {'strip3$':>9s}")
    ex = []
    for s_ in (2.0, 2.5, 3.0, 3.5, 4.0):
        for t_ in (3.0, 4.0, 5.0, 6.0, 8.0):
            t = run_trades(racer, us, stop_a=s_, targ_a=t_, cap_min=120)
            st = stat(t)
            ex.append(dict(stop=s_, targ=t_, **st, strip3=strip_best(t, 3)))
            print(f"  {s_:>5.1f} {t_:>6.1f} {st['n']:>5d} {st['net']:>9,.0f} {st['per']:>8.2f} "
                  f"{strip_best(t,3):>9,.0f}")
    R["exit_plateau"] = ex
    print(f"\n  positive $/trade in {sum(1 for e in ex if e['per']>0)} of {len(ex)} exit cells")

    # ── 4d. stacked filters, each with its own placebo ─────────────────────────────────────────
    hdr("4d · STACKING — does anything on top of the clock survive its OWN placebo?")
    stacks = {
        "US only (the survivor)":       lambda d: d["ts"] > 0,
        "US + rvol>=1.0":               lambda d: d["rvol"] >= 1.0,
        "US + ATR>=12pt":               lambda d: d["atr"] >= 12.0,
        "US + atr_pr>=0.50":            lambda d: d["atr_pr"] >= 0.50,
        "US + rvol>=1.0 + ATR>=12pt":   lambda d: (d["rvol"] >= 1.0) & (d["atr"] >= 12.0),
        "US 13-15Z only (the open)":    lambda d: d["hh"] < 15.0,
        "US 13-15Z + rvol>=1.0":        lambda d: (d["hh"] < 15.0) & (d["rvol"] >= 1.0),
    }
    st_rows = []
    for nm, fn in stacks.items():
        sub = us[fn(us)].reset_index(drop=True)
        t = run_trades(racer, sub, **EXIT)
        if len(t) < 20:
            print(f"  {nm:<30s} n={len(t)} — too thin to score")
            continue
        pl = placebo(racer, us, len(sub), 15, **EXIT)
        s0 = stat(t)
        st_rows.append(dict(stack=nm, **s0, strip3=strip_best(t, 3),
                            plac=pl["per_mean"], plac_p95=pl["per_p95"],
                            beats=bool(s0["per"] > pl["per_p95"])))
        print(f"  {nm:<30s} n={s0['n']:>4d} net=${s0['net']:>7,.0f} ${s0['per']:>7.2f}/tr "
              f"strip3=${strip_best(t,3):>7,.0f}  placebo p95 ${pl['per_p95']:>6.2f} "
              f"{'BEATS' if s0['per'] > pl['per_p95'] else 'fails'}")
    R["stacks"] = st_rows

    # ── 5. THE PRIZE ───────────────────────────────────────────────────────────────────────────
    hdr("5 · SIZING THE PRIZE — oracle vs causal, on the census week's 60 sat-out runs")
    wk_sig = us[(us["day"] >= CENSUS_WEEK[0]) & (us["day"] <= CENSUS_WEEK[1])]
    wk_tr = run_trades(racer, wk_sig, **EXIT)
    ceiling = int(runs["ceil"].sum())

    # big-moves-caught: a sat-out run counts as CAUGHT if a rider trade was open, correctly signed,
    # at any point inside the run's own 15-minute window.
    caught, caught_net = [], 0.0
    for r in runs.itertuples():
        ov = wk_tr[(wk_tr["ts"] <= r.ts + 900) & (wk_tr["ts"] + wk_tr["held_s"] >= r.ts)
                   & (wk_tr["side"] == r.dirn)]
        if len(ov):
            caught.append(r.label)
            caught_net += ov["net"].sum()
    print(f"  census-week sat-out runs: {len(runs)}   ceiling ${ceiling:,}")
    print(f"  RIDER trades in the census week (US session): n={len(wk_tr)}, "
          f"net ${wk_tr['net'].sum():,.0f}")
    print(f"  big-moves-caught: {len(caught)}/{len(runs)}  "
          f"(${caught_net:,.0f} banked on the trades that overlapped a sat-out run)")
    print(f"  fraction of the ${ceiling:,} ceiling taken: "
          f"{100*wk_tr['net'].sum()/ceiling:.1f}% (all rider trades) / "
          f"{100*caught_net/ceiling:.1f}% (only the run-overlapping ones)")

    # ORACLE: the same entries, but keep only the fires that turned out to win. Cheats by
    # construction — it is the ceiling of ANY filter built on this entry, not an achievable number.
    orc = tr[tr["net"] > 0]
    orc_wk = wk_tr[wk_tr["net"] > 0]
    print(f"\n  ORACLE bound (perfect filtering of the SAME entries — cheats, cannot be traded):")
    print(f"    whole tape  n={len(orc)} net ${orc['net'].sum():,.0f} "
          f"(${orc['net'].sum()/len(days):,.0f}/session over {len(days)} sessions)")
    print(f"    census week n={len(orc_wk)} net ${orc_wk['net'].sum():,.0f}")
    print(f"\n  CAUSAL result (the rule as specified, nothing hindsight):")
    print(f"    whole tape  n={len(tr)} net ${tot:,.0f} "
          f"(${tot/len(days):,.0f}/session, ${tot/len(days)*5:,.0f}/week equivalent)")
    print(f"    census week n={len(wk_tr)} net ${wk_tr['net'].sum():,.0f}")
    R["prize"] = dict(ceiling=ceiling, week_n=int(len(wk_tr)),
                      week_net=round(float(wk_tr["net"].sum()), 0),
                      caught=len(caught), caught_labels=caught, caught_net=round(caught_net, 0),
                      oracle_all=round(float(orc["net"].sum()), 0),
                      oracle_week=round(float(orc_wk["net"].sum()), 0),
                      per_session=round(tot / len(days), 0), sessions=len(days))

    print("\n  census-week trade-by-trade:")
    cols = ["day", "hh", "side", "regime", "atr", "entry_px", "exit_px", "why", "held_s", "pts", "net"]
    print(wk_tr[cols].to_string(index=False))

    tr.to_pickle("/home/alphabot/gazbot7/data/gf_rider/tr_final.pkl")
    wk_tr.to_pickle("/home/alphabot/gazbot7/data/gf_rider/tr_week.pkl")
    json.dump(R, open(f"{OUT}/gf_rider_final.json", "w"), indent=1, default=str)
    print(f"\n→ {OUT}/gf_rider_final.json")


if __name__ == "__main__":
    main()
