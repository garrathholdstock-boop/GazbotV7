#!/usr/bin/env python3
"""MGC DAY RIDER — how reliable is picking a direction and having it HOLD for the day?

    PYTHONPATH=src .venv/bin/python scripts/mgc_day_rider_study.py [--sweep]

Operator, 2026-08-14: *"what about day rider for mgc. one trade a day. look at all the data we have.
how reliable is picking a direction and it stays that way for a big portion of the day? remember i
watch intently the us session so i can claim profit."*

★ WHY THIS IS THE RIGHT SHAPE FOR GOLD, and it comes from today's measurement rather than from
porting MNQ. `mgc_run_catcher.py` found gold's big moves are **grinds, not thrusts** — the top 5 runs
of the week have a median ER of 0.23 and four of five last 2-12 HOURS. A trailing exit is shaken out
of that (oracle ceiling $83/wk); a wide stop held for hours is not (~$346/wk). "Board once, hold
wide, flat at a clock" is the DAY-RIDER shape, and gold's anatomy asks for it.

★ IT USES THE REAL DETECTOR. `gazbot7.drift.compute` is the exact function the live MNQ rider runs —
called here, not re-implemented. A hand-rolled copy of a live detector drifts from it silently and
then the study is measuring something the desk does not do ([[day-rider-closed-latch-consumes-session]]).

★ THE CONTROL THAT MATTERS. Every previous gold direction study died against the best CONSTANT, not
against a coinflip: "always SHORT" was right 53.7% of the time on a downward-drifting sample, so a
signal at 55% is worth +1.3pp, not +5pp. This prints always-LONG and always-SHORT on the same days,
and any rule must beat the better of them to mean anything.

★ THE OPERATOR WATCHES AND CLAIMS, so MFE is reported as prominently as the final. A day that runs
+$400 and closes flat is a LOSS to an unattended trail and a WIN to a watching operator — those are
different questions and this prints both.

MGC is $10/pt (NOT MNQ's $2); fee $1.50/RT. Session 13:30 UTC open → 20:40 UTC flat, the live
rider's own clock, so "never hold overnight" is preserved by construction.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from gazbot7 import drift  # noqa: E402
from mgc_session_anchor import load, minute_bars  # noqa: E402

VPP, FEE_RT, LOTS = 10.0, 1.50, 2
OPEN_MIN, FLAT_MIN = 13 * 60 + 30, 20 * 60 + 40


def sessions(m: pd.DataFrame):
    """Yield (day, session_minute_bars) for the 13:30→20:40 UTC window."""
    for day, dm in m.groupby(m.index.date):
        s = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=OPEN_MIN)
        e = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=FLAT_MIN)
        w = dm.loc[s:e]
        if len(w) >= 60:
            yield day, w


def detect(win: pd.DataFrame, upto_min: int):
    """Run the LIVE detector on the first `upto_min` minutes of the session."""
    head = win.iloc[:upto_min]
    if len(head) < 15:
        return None
    bars = [(int(ts.value // 10**9), r["high"], r["low"], r["close"])
            for ts, r in head.iterrows()]
    r = drift.compute(bars)
    # ★★ GATE ON `confirmed`, NOT `ok`. `ok` means only "enough data to say anything at all"
    # (drift.py:63); `confirmed` is the field that means THE SIGNAL FIRED — ER>=0.15 AND RT>=0.45.
    # The first version of this study gated on `ok` and therefore entered EVERY session regardless
    # of the thresholds: it reported 16/16 days firing on rows showing eff 0.01 / rt 0.04, and a
    # +12.5pp "edge" that was really just "trade gold every day". Calling the real detector is not
    # enough — you have to read its CONTRACT. ⚠ `direction` is likewise a STRING ("UP"/"DOWN"/"").
    if not r.confirmed or not r.direction:
        return None
    return r


def outcome(win: pd.DataFrame, entry_i: int, side: int) -> dict:
    """From entry to the 20:40 flat: final, best (MFE) and worst (MAE), in dollars for LOTS lots."""
    seg = win.iloc[entry_i:]
    if len(seg) < 5:
        return {}
    e = float(seg["close"].iloc[0])
    mfe = float((side * (seg["high"].max() - e)) if side > 0 else side * (seg["low"].min() - e))
    mae = float((side * (seg["low"].min() - e)) if side > 0 else side * (seg["high"].max() - e))
    fin = float(side * (seg["close"].iloc[-1] - e))
    gross = LOTS * VPP
    return {"entry": e, "final_pt": fin, "mfe_pt": mfe, "mae_pt": mae,
            "final$": fin * gross - FEE_RT * LOTS,
            "mfe$": mfe * gross - FEE_RT * LOTS,
            "mae$": mae * gross}


def study(m: pd.DataFrame, upto_min: int) -> pd.DataFrame:
    rows = []
    for day, win in sessions(m):
        r = detect(win, upto_min)
        base = {"day": str(day), "fired": r is not None}
        if r is not None:
            sd = 1 if r.direction == "UP" else -1
            o = outcome(win, min(upto_min, len(win) - 1), sd)
            base.update({"dir": sd, "eff": round(r.efficiency, 3),
                         "rt": round(r.roundtrip, 3), **o})
        # constants on the SAME session, entered at the same minute
        for nm, sd in (("always_long", 1), ("always_short", -1)):
            oc = outcome(win, min(upto_min, len(win) - 1), sd)
            base[f"{nm}$"] = oc.get("final$", np.nan)
        rows.append(base)
    return pd.DataFrame(rows)


def report(df: pd.DataFrame, upto_min: int, verbose=True) -> dict:
    f = df[df.fired]
    n_days, n_fire = len(df), len(f)
    if not n_fire:
        print(f"  detect @+{upto_min}m: fired on 0 of {n_days} days")
        return {}
    hit = (f["final$"] > 0).mean() * 100
    al = df["always_long$"].dropna()
    ash = df["always_short$"].dropna()
    best_const = max(al.sum(), ash.sum())
    best_const_hit = max((al > 0).mean(), (ash > 0).mean()) * 100

    if verbose:
        print(f"  {'day':<12}{'dir':>4}{'eff':>6}{'rt':>6}{'final$':>10}{'MFE$':>10}{'MAE$':>10}")
        for _, r in f.iterrows():
            print(f"  {r['day']:<12}{'UP' if r['dir']>0 else 'DN':>4}{r['eff']:>6.2f}{r['rt']:>6.2f}"
                  f"{r['final$']:>10.2f}{r['mfe$']:>10.2f}{r['mae$']:>10.2f}")
    print(f"\n  DETECT @+{upto_min}m · {n_fire}/{n_days} days fired ({n_fire/n_days:.0%})")
    print(f"    direction held to the flat : {hit:.1f}% of fired days")
    print(f"    total final                : ${f['final$'].sum():>9.2f}   "
          f"median ${f['final$'].median():>8.2f}")
    print(f"    ★ MFE (what a WATCHING operator could claim): "
          f"total ${f['mfe$'].sum():>9.2f}  median ${f['mfe$'].median():>8.2f}")
    print(f"    worst adverse excursion    : ${f['mae$'].min():>9.2f}  "
          f"median ${f['mae$'].median():>8.2f}")
    print(f"    CONTROL best constant      : ${best_const:>9.2f} ({best_const_hit:.1f}% of days) "
          f"— always_long ${al.sum():.0f} / always_short ${ash.sum():.0f}")
    edge = hit - best_const_hit
    print(f"    ⇒ direction edge over the best constant: {edge:+.1f}pp")
    return {"n": n_fire, "hit": hit, "final": f["final$"].sum(), "mfe": f["mfe$"].sum(),
            "edge_pp": edge}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    a = ap.parse_args()
    bars, _ticks = load()
    m = minute_bars(bars)
    print(f"  MGC {m.index.min():%Y-%m-%d} .. {m.index.max():%Y-%m-%d} · "
          f"{m.index.normalize().nunique()} days · ${VPP:.0f}/pt · {LOTS} lots · "
          f"session {OPEN_MIN//60}:{OPEN_MIN%60:02d}→{FLAT_MIN//60}:{FLAT_MIN%60:02d} UTC")
    print(f"  detector: gazbot7.drift.compute (the LIVE one) — ER>={drift.ER_MIN}, RT>={drift.RT_MIN}\n")

    if not a.sweep:
        report(study(m, 60), 60)
    else:
        print("  ═══ how long to wait before calling the direction? ═══")
        for k in (30, 45, 60, 90, 120):
            report(study(m, k), k, verbose=False)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
