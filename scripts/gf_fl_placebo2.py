#!/usr/bin/env python3
"""FLOW-LED greenfield — STEP 7: THE PLACEBO THE FIRST ONE WAS NOT.

The step-4 placebo slid the signal series 20-240 minutes. On the US-session book that is a confounded
test: sliding a 13:45 signal by two hours moves it out of the US session entirely, so it partly
measures "is the US session better than the overnight" rather than "is the flow filter better than
nothing". The p=0.035 it produced is therefore too kind, and it has to be redone properly.

Two honest placebos, both holding the session and the trading day FIXED:

  A. MATCHED-MINUTE  — for each real trade, a random OTHER minute in the same session on the same
     day, same direction. Same count, same day mix, same clock window. This asks: is the MOMENT
     special, or is any US minute as good?

  B. FILTER-PERMUTATION — the strongest one. Take every 15-minute-range BREAK in the US session
     (461 of them) and draw, at random, as many as the flow filter actually selected (189). Repeat
     200 times. This asks the exact question the gate claims to answer: does the >=2-sigma flow
     event pick BETTER breaks than a coin does?

Writes reports/friday_v7/sections/fl/placebo2.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("GF_FL_TICK_CACHE", "40")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_fl_ablate2 import variant  # noqa: E402
from gf_fl_cands import load_feat, run  # noqa: E402

DIR = "/home/alphabot/gazbot7/reports/friday_v7/sections/fl"
OUT = f"{DIR}/placebo2.json"
EXIT = dict(stop_k=1.5, targ_k=3.0, hold=60)
SESSION = "US"
DRAWS = 200


def main():
    df = load_feat()
    real = [s for s in variant(df, "BRK_FLOWAGREE", z=2.0) if s["session"] == SESSION]
    allbrk = [s for s in variant(df, "BRK_NONE") if s["session"] == SESSION]
    rt, rsc = run("REAL", real, **EXIT)
    _, bsc = run("ALLBREAKS", allbrk, **EXIT)
    print("real:", rsc, flush=True)
    print("all US breaks:", bsc, flush=True)
    res = {"real": rsc, "all_us_breaks": bsc}

    rng = np.random.default_rng(20260815)

    # ── A. matched-minute placebo ────────────────────────────────────────────────────────────
    pool = df[(df["session"] == SESSION) & df["atr15"].notna()]
    by_day = {d: g for d, g in pool.groupby("day")}
    per_day = {}
    for s in real:
        per_day[s["day"]] = per_day.get(s["day"], 0) + 1
    dirs = np.array([s["dir"] for s in real])
    nets_a = []
    for _ in range(DRAWS):
        fs = []
        for d, k in per_day.items():
            g = by_day.get(d)
            if g is None or len(g) < k:
                continue
            pick = g.sample(k, random_state=int(rng.integers(1e9)))
            for _, r in pick.iterrows():
                fs.append({"ts": int(r["ts"]), "day": r["day"], "dir": int(rng.choice(dirs)),
                           "atr": float(r["atr15"]), "regime": r["regime"], "session": r["session"],
                           "er": float(r["er15"]), "fz": 0.0, "ext": 0.0})
        _, sc = run("A", fs, **EXIT)
        nets_a.append(sc["net"])
    a = np.array(nets_a, float)

    # ── B. filter-permutation placebo ────────────────────────────────────────────────────────
    k = len(real)
    nets_b = []
    for _ in range(DRAWS):
        idx = rng.choice(len(allbrk), size=min(k, len(allbrk)), replace=False)
        fs = [allbrk[i] for i in sorted(idx)]
        _, sc = run("B", fs, **EXIT)
        nets_b.append(sc["net"])
    b = np.array(nets_b, float)

    for key, arr in (("matched_minute", a), ("filter_permutation", b)):
        res[key] = {
            "draws": int(len(arr)), "real_net": rsc["net"],
            "fake_net_mean": round(float(arr.mean()), 2),
            "fake_net_median": round(float(np.median(arr)), 2),
            "fake_net_p90": round(float(np.percentile(arr, 90)), 2),
            "fake_pct_positive": round(100 * float((arr > 0).mean()), 1),
            "pctile_of_real": round(100 * float((arr < rsc["net"]).mean()), 1),
            "p_value_one_sided": round(float((arr >= rsc["net"]).mean()), 4)}
        print(key, res[key], flush=True)

    json.dump(res, open(OUT, "w"), indent=1)
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
