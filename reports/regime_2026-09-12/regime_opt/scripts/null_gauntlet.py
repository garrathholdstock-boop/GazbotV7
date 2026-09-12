#!/usr/bin/env python3
"""THE CLOSING TEST - run the SAME selection-then-gauntlet procedure inside each null world.

Two GRID A cells cleared all three bars. But they were chosen as the best of 5,040. The only
honest question left is: when the same 5,040-cell search is run on a world where the state
series has been rotated away from price, does its winner ALSO clear all three bars?

Procedure, identical in every world:
  1. take that world's best cell by net among cells with n >= 250 (so the winner is not a
     20-trade fluke),
  2. rebuild it, and put it through the same gauntlet: three periods, day-blocked SIGN-FLIP
     twin on identical bars, day-block bootstrap CI.
Survivors in the null worlds are, by construction, false positives.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

FRIC = 1.25; NMIN = 250
WINDOWS = {"ALL": None, "LDN": (480, 810), "RTH": (810, 1200),
           "OPEN": (810, 960), "EUUS": (480, 1200)}
A = pd.read_csv(f"{R.ART}/tables/grid_a_all.csv")
A = A[A.n >= NMIN]
best = A.sort_values("net", ascending=False).groupby("world").head(1).sort_values("world")
print(f"BEST CELL PER WORLD (n >= {NMIN}) out of {len(A)//7} eligible cells each")
print(best[["world", "bar", "states", "fset", "clean", "win", "hold_min", "n", "net", "t",
            "TR", "VA", "TE"]].round(2).to_string(index=False))

def shifted_view(M, sh):
    g = M.g; ss = sorted(g.sess.unique()); pos = {s: k for k, s in enumerate(ss)}
    sidx = np.array([pos[s] for s in g.sess.values])
    key = pd.DataFrame({"s": sidx, "r": np.arange(len(g))}); key["rk"] = key.groupby("s").cumcount()
    tgt = key.copy(); tgt["s"] = (tgt.s + sh) % len(ss)
    m = key.merge(tgt, on=["s", "rk"], how="left", suffixes=("", "_t"))
    src = m["r_t"].values; good = ~np.isnan(src)
    return good, np.where(good, np.nan_to_num(src, nan=0).astype(int), 0)

rows = []
gc = {}
for _, r in best.iterrows():
    if r.bar not in gc:
        gc = {r.bar: R.load_bars(int(r.bar))}
    M = R.Model(int(r.bar), int(r.states), r.fset, g=gc[r.bar])
    orig = (M.state, M.lab, M.sign, M.tp)
    if r.world != "REAL":
        sh = int(r.world.replace("NULL", ""))
        good, src = shifted_view(M, sh)
        M.state = np.where(good, orig[0][src], -1); M.lab = np.where(good, orig[1][src], "NA")
        M.sign = np.where(good, orig[2][src], 0);   M.tp = np.where(good, orig[3][src], np.nan)
    idx = R.signals(M, clean=int(r.clean), win=WINDOWS[r.win])
    T = R.trades(M, idx, hold=int(r.hold_min // r.bar), friction=FRIC)
    ps = R.period_stats(T, M)
    sc = R.sign_control(T, draws=4000, block="day", friction=FRIC)
    lo, mid, hi = R.day_block_boot(T, friction=FRIC, draws=4000)
    M.state, M.lab, M.sign, M.tp = orig
    rows.append(dict(world=r.world, cell=f"{int(r.bar)}m/{int(r.states)}/{r.fset}/"
                     f"c{int(r.clean)}/{r.win}/{int(r.hold_min)}m", n=len(T), net=mid,
                     TR=ps["TRAIN"]["mean"], VA=ps["VALIDATE"]["mean"], TE=ps["TEST"]["mean"],
                     twin_sd=sc["sd"], edge_sd=(mid - sc["mean"]) / sc["sd"], p=sc["p"],
                     lo=lo, hi=hi,
                     a=mid > 0, b=(mid - sc["mean"]) > sc["sd"], c=lo > 0,
                     three=(ps["TRAIN"]["mean"] > 0 and ps["VALIDATE"]["mean"] > 0
                            and ps["TEST"]["mean"] > 0)))
D = pd.DataFrame(rows)
D["ALL_BARS"] = D.a & D.b & D.c
D.to_csv(f"{R.ART}/tables/null_gauntlet.csv", index=False)
pd.set_option("display.width", 240)
print("\nTHE SAME GAUNTLET, APPLIED TO EACH WORLD'S OWN WINNER")
print(D.round(2).to_string(index=False))
nn = D[D.world != "REAL"]
print(f"\nNULL worlds whose winner clears all three bars: {int(nn.ALL_BARS.sum())} of {len(nn)}")
print(f"NULL worlds whose winner is positive in all three periods: {int(nn.three.sum())} of {len(nn)}")
print(f"REAL winner clears all three bars: {bool(D[D.world=='REAL'].ALL_BARS.iloc[0])}")
