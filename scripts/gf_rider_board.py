#!/usr/bin/env python3
"""GF RIDER · STEP 1 — BOARD IT LATE. How much of a run is left once it has PROVEN itself?

The census says we sat out 60 MNQ runs worth $8,024 of one-lot ceiling. Predicting a run START is
already a banked NULL on 22.6M ticks, so this step does not try. It asks the only question a rider
actually needs answered:

    for each of the 60 runs, at what point could we have KNOWN, and what was LEFT after that point?

On gold this week the same shape fired inside 5 of 5 top runs at a median 19 minutes in with ~80% of
the move still ahead. This establishes the MNQ curve — as a DISTRIBUTION, never an average, because
an average over a bimodal "half of them are dead on arrival" population is a lie.

    PYTHONPATH=src .venv/bin/python scripts/gf_rider_board.py
"""
from __future__ import annotations

import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gf_rider_engine import Racer  # noqa: E402
from gf_rider_tape import build  # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/friday_v7/sections"
CENSUS = f"{OUT}/census_stdout.txt"
YEAR = 2026


def sat_out_runs() -> pd.DataFrame:
    """Parse the FROZEN census. Never re-run run_census.py — the snapshot must not drift."""
    rows = []
    pat = re.compile(r"^(\d\d)-(\d\d) (\d\d):(\d\d)\s+(UP|DN)\s+([+-]?\d+)\s+(\d+)\s+(\S+)")
    for ln in open(CENSUS):
        m = pat.match(ln.strip())
        if not m:
            continue
        mo, da, hh, mi, d, mv, ceil, us = m.groups()
        ts = int(pd.Timestamp(f"{YEAR}-{mo}-{da} {hh}:{mi}:00", tz="UTC").timestamp())
        rows.append(dict(ts=ts, label=f"{mo}-{da} {hh}:{mi}", dirn=1 if d == "UP" else -1,
                         move=int(mv), ceil=int(ceil), us=us,
                         cluster=ln.strip().split()[-1]))
    df = pd.DataFrame(rows)
    return df[df["us"] == "sat"].reset_index(drop=True)


def board_curve(m1: pd.DataFrame, racer: Racer, runs: pd.DataFrame,
                w: int, k: float, horizon_min: int = 60) -> pd.DataFrame:
    """For each run: first CAUSAL trigger inside the run window, and what was left after it.

    Trigger = at the close of minute t, |net over the last w minutes| >= k * ATR(t), signed the way
    the tape is going. Fill at the OPEN of minute t+1 — the rule never sees the bar it fills on.
    """
    ts = m1["ts"].to_numpy(np.int64)
    out = []
    for r in runs.itertuples():
        lo, hi = r.ts, r.ts + 900
        sl = m1[(m1["ts"] >= lo) & (m1["ts"] <= hi)]
        if not len(sl):
            out.append(dict(label=r.label, fired=False, why="no tape"))
            continue
        net = sl[f"net{w}"]
        trig = sl[(net.abs() >= k * sl["atr"]) & (np.sign(net) == r.dirn)]
        if not len(trig):
            out.append(dict(label=r.label, move=r.move, ceil=r.ceil, cluster=r.cluster,
                            fired=False, why="never triggered inside the run"))
            continue
        t = trig.iloc[0]
        j = int(np.searchsorted(ts, t["ts"] + 60))
        if j >= len(ts):
            out.append(dict(label=r.label, fired=False, why="trigger on the last bar"))
            continue
        entry = float(m1["o"].iloc[j])
        run_c0 = float(sl["c"].iloc[0])
        i0, i1 = racer.idx(int(m1["ts"].iloc[j])), racer.idx(r.ts + 900)
        i2 = racer.idx(int(m1["ts"].iloc[j]) + horizon_min * 60)
        def excursion(a, b):
            if b <= a:
                return 0.0, 0.0
            hh, ll = racer.h[a:b].max(), racer.l[a:b].min()
            return ((hh - entry, entry - ll) if r.dirn > 0 else (entry - ll, hh - entry))
        left_run, adv_run = excursion(i0, max(i1, i0 + 1))
        left_hor, adv_hor = excursion(i0, i2)
        already = (entry - run_c0) * r.dirn
        out.append(dict(
            label=r.label, cluster=r.cluster, move=r.move, ceil=r.ceil, fired=True,
            mins_in=int((t["ts"] + 60 - r.ts) / 60), atr=round(float(t["atr"]), 2),
            already=round(already, 1),
            left_run=round(left_run, 1), left_hor=round(left_hor, 1),
            adv_run=round(adv_run, 1), adv_hor=round(adv_hor, 1),
            pct_left=round(100 * left_hor / max(abs(r.move), 1), 1),
            r_left=round(left_hor / float(t["atr"]), 2) if t["atr"] > 0 else np.nan,
            r_adv=round(adv_hor / float(t["atr"]), 2) if t["atr"] > 0 else np.nan))
    return pd.DataFrame(out)


def dist(s: pd.Series, name: str) -> str:
    q = s.dropna().quantile([.1, .25, .5, .75, .9])
    return (f"  {name:<22s} n={s.notna().sum():>3d}  p10={q.iloc[0]:>7.1f}  p25={q.iloc[1]:>7.1f}  "
            f"MED={q.iloc[2]:>7.1f}  p75={q.iloc[3]:>7.1f}  p90={q.iloc[4]:>7.1f}")


def main():
    m1, s5 = build()
    racer = Racer(s5)
    runs = sat_out_runs()
    print(f"═══ STEP 1 · BOARD IT LATE — {len(runs)} sat-out MNQ runs, "
          f"${runs['ceil'].sum():,} of one-lot ceiling ═══\n")
    print(f"tape: {m1['day'].nunique()} sessions {m1['day'].min()}..{m1['day'].max()}\n")

    res = {}
    print("── DETECTOR GRID: does a 'the move has proven itself' trigger fire INSIDE the run? ──")
    print("   (w = lookback minutes, k = multiples of the 1-min ATR the move must have covered)\n")
    print(f"  {'w':>3s} {'k':>4s}  {'fired':>5s}/{len(runs):<3d} {'med mins-in':>11s} "
          f"{'med % left':>10s} {'med R left':>10s} {'med R adverse':>13s}")
    grid = []
    for w in (5, 10, 15):
        for k in (1.0, 1.5, 2.0, 2.5, 3.0):
            c = board_curve(m1, racer, runs, w, k)
            f = c[c["fired"]]
            grid.append(dict(w=w, k=k, fired=len(f), n=len(runs),
                             mins=f["mins_in"].median() if len(f) else np.nan,
                             pct=f["pct_left"].median() if len(f) else np.nan,
                             rleft=f["r_left"].median() if len(f) else np.nan,
                             radv=f["r_adv"].median() if len(f) else np.nan))
            g = grid[-1]
            print(f"  {w:>3d} {k:>4.1f}  {len(f):>5d}      {g['mins']:>11.0f} "
                  f"{g['pct']:>10.1f} {g['rleft']:>10.2f} {g['radv']:>13.2f}")
            res[f"w{w}_k{k}"] = g

    # the headline configuration: the one that boards the MOST runs while still leaving something
    W, K = 10, 1.5
    print(f"\n── THE CURVE, in full, for w={W} k={K} ──\n")
    c = board_curve(m1, racer, runs, W, K)
    f = c[c["fired"]].copy()
    print(f"  boarded {len(f)} of {len(runs)} sat-out runs "
          f"({100*len(f)/len(runs):.0f}%); missed {len(c)-len(f)}\n")
    print(dist(f["mins_in"], "minutes into the run"))
    print(dist(f["already"], "points ALREADY gone"))
    print(dist(f["left_run"], "points left (run end)"))
    print(dist(f["left_hor"], "points left (+60min)"))
    print(dist(f["adv_hor"], "points AGAINST first"))
    print(dist(f["pct_left"], "% of the run left"))
    print(dist(f["r_left"], "R left (ATR units)"))
    print(dist(f["r_adv"], "R against (ATR units)"))

    print("\n── EVERY BOARDED RUN, worst-to-best on what was left ──\n")
    cols = ["label", "cluster", "move", "ceil", "mins_in", "atr", "already",
            "left_run", "left_hor", "adv_hor", "pct_left", "r_left", "r_adv"]
    print(f.sort_values("r_left")[cols].to_string(index=False))
    miss = c[~c["fired"]]
    if len(miss):
        print(f"\n── NEVER BOARDED ({len(miss)}) ──")
        print(miss[["label", "move", "ceil", "why"]].to_string(index=False))

    print("\n── THE KILLER STATISTIC: how many boarded runs have enough left to PAY? ──")
    print("   (cost is $2.50 all-in = 1.25pt; a trade needs materially more than that)\n")
    for thr in (5, 10, 15, 20, 30, 50):
        n = (f["left_hor"] >= thr).sum()
        print(f"  >= {thr:>3d}pt left after boarding:  {n:>3d} / {len(f)}  ({100*n/len(f):>4.0f}%)")

    json.dump(dict(grid=res, curve=f.to_dict("records"),
                   missed=miss[["label", "why"]].to_dict("records"),
                   n_runs=int(len(runs)), ceiling=int(runs["ceil"].sum())),
              open(f"{OUT}/gf_rider_board.json", "w"), indent=1, default=str)
    f.to_pickle("/home/alphabot/gazbot7/data/gf_rider/board.pkl")
    print(f"\n→ {OUT}/gf_rider_board.json")


if __name__ == "__main__":
    main()
