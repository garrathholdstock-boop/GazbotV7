#!/usr/bin/env python3
"""STAGE 0 - the friction sensitivity curve, and the POWER FLOOR of this design.

Task 1 of the brief: re-run the incumbent (15-min, 3 states, base features) across
0.75 / 1.00 / 1.25 / 1.50 / 2.00 points of round-trip friction, every cell, all three periods.

Task 0 (mine, added because it decides whether any of this can conclude anything): what is the
standard deviation of a single trade, and therefore the SMALLEST edge this sample could ever
resolve? A design that cannot see a 1.5pt edge cannot report one either way.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

ART = R.ART
M = R.Model(15, 3, "base")
M.describe().to_csv(f"{ART}/tables/stage0_states.csv", index=False)
print("STATE TABLE (TRAIN only, named from mean signed 8-bar drift in ATR units)")
print(M.describe().to_string(index=False), "\n")

rows, power = [], []
for clean in (2, 0):
    idx = R.signals(M, clean=clean)
    for hold in (2, 3, 4, 5, 6, 8, 10, 12):
        T = R.trades(M, idx, hold=hold, friction=0.0)   # friction applied later
        if len(T) < 60:
            continue
        sd = T.gross.std(ddof=1)
        se = sd / np.sqrt(len(T))
        power.append(dict(hold_min=hold * 15, clean=bool(clean), n=len(T),
                          gross_mean=T.gross.mean(), gross_sd=sd, se=se,
                          mde_95=1.96 * se,                       # min detectable edge, 2-sided
                          n_for_1p5=int((1.96 * sd / 1.5) ** 2)))
        for f in R.FRICTIONS:
            ps = R.period_stats(T, M, friction=f)
            rows.append(dict(hold_min=hold * 15, clean=bool(clean), friction=f, n=len(T),
                             ALL=T.gross.mean() - f,
                             **{f"{p}_n": ps[p]["n"] for p in ps},
                             **{f"{p}_mean": ps[p]["mean"] for p in ps},
                             **{f"{p}_t": ps[p]["t"] for p in ps}))

P = pd.DataFrame(power); P.to_csv(f"{ART}/tables/stage0_power.csv", index=False)
print("POWER FLOOR - one trade's spread against the edge we are hunting")
print(P.round(2).to_string(index=False), "\n")

D = pd.DataFrame(rows); D.to_csv(f"{ART}/tables/stage0_friction_curve.csv", index=False)
print("FRICTION SENSITIVITY - incumbent 15-min / 3-state / base features, net points per trade")
piv = D.pivot_table(index=["hold_min", "clean"], columns="friction", values="ALL")
print(piv.round(2).to_string(), "\n")
print("  the same cells, ALL THREE PERIODS, at this desk's measured 1.25pt")
sub = D[D.friction == 1.25][["hold_min", "clean", "TRAIN_n", "TRAIN_mean", "TRAIN_t",
                             "VALIDATE_n", "VALIDATE_mean", "VALIDATE_t",
                             "TEST_n", "TEST_mean", "TEST_t", "ALL"]]
print(sub.round(2).to_string(index=False))

# where does the ALL-sample number cross zero?
print("\n  BREAK-EVEN FRICTION (the friction at which each cell's ALL-sample net = 0) = gross edge")
be = D[D.friction == 1.25].assign(gross=lambda x: x.ALL + 1.25)[["hold_min", "clean", "n", "gross"]]
print(be.round(2).to_string(index=False))
be.to_csv(f"{ART}/tables/stage0_gross_edge.csv", index=False)
