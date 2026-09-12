#!/usr/bin/env python3
"""GRID A - the structural sweep, with its own EMPIRICAL NULL built from the same grid.

DIMENSIONS (pre-declared; the cell count is the headline, not a footnote):
  bar     5, 10, 15, 30 minutes
  states  3, 4, 5
  feature base / drift / base_vol / base_vz / base_sp / full
  clean   0 (any transition) or 2 (no target state in the prior 2 bars - Mesfin's Signal B rule)
  window  ALL / LONDON 08:00-13:30Z / RTH 13:30-20:00Z / US-OPEN 13:30-16:00Z / EU+US 08:00-20:00Z
  hold    30..180 minutes (only whole numbers of bars)
Exit is fixed time, entry is next bar's open, friction 1.25pt. Refinements are GRID B.

★ THE NULL. The same grid is re-run on SHIFTED worlds: the fitted state sequence is rotated by
  whole sessions against price. Persistence, transition frequency and the diurnal shape of the
  entries all survive; only the alignment between a state and the price it was fitted on dies.
  This is a far finer control than permuting 3 labels 5 ways - it does not move CHOP onto a
  drift state, so the entry POPULATION is preserved, which the 09-11 permutation control was
  criticised for. Whatever the real grid's best cell scores, the null grids say what the same
  search returns when there is nothing there.
"""
import sys, os, time, itertools, json
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

ART = R.ART
FRIC = 1.25
BARS = [5, 10, 15, 30]
STATES = [3, 4, 5]
FSETS = ["base", "drift", "base_vol", "base_vz", "base_sp", "full"]
CLEANS = [0, 2]
HOLDS = [30, 45, 60, 75, 90, 120, 150, 180]
WINDOWS = {"ALL": None, "LDN": (480, 810), "RTH": (810, 1200),
           "OPEN": (810, 960), "EUUS": (480, 1200)}
SHIFTS = [-53, -37, -23, 17, 31, 47]        # whole-session rotations for the null

def shifted_view(M, sh):
    g = M.g
    ss = sorted(g.sess.unique()); pos = {s: k for k, s in enumerate(ss)}
    sidx = np.array([pos[s] for s in g.sess.values])
    key = pd.DataFrame({"s": sidx, "r": np.arange(len(g))})
    key["rk"] = key.groupby("s").cumcount()
    tgt = key.copy(); tgt["s"] = (tgt.s + sh) % len(ss)
    m = key.merge(tgt, on=["s", "rk"], how="left", suffixes=("", "_t"))
    src = m["r_t"].values
    good = ~np.isnan(src)
    src = np.where(good, np.nan_to_num(src, nan=0).astype(int), 0)
    return good, src

def run_cells(M, tag, rows):
    for clean, wn in itertools.product(CLEANS, WINDOWS):
        idx = R.signals(M, clean=clean, win=WINDOWS[wn])
        if len(idx) < 80:
            continue
        for hm in HOLDS:
            if hm % M.bar:
                continue
            hold = hm // M.bar
            if hold < 1:
                continue
            T = R.trades(M, idx, hold=hold, friction=FRIC)
            if len(T) < 100:
                continue
            ps = R.period_stats(T, M)
            sd = T.gross.std(ddof=1)
            rows.append(dict(world=tag, bar=M.bar, states=M.K, fset=M.fset, clean=clean,
                             win=wn, hold_min=hm, n=len(T),
                             gross=float(T.gross.mean()), gross_sd=float(sd),
                             net=float(T.gross.mean() - FRIC),
                             t=float((T.gross.mean() - FRIC) / (sd / np.sqrt(len(T)))),
                             TR_n=ps["TRAIN"]["n"], TR=ps["TRAIN"]["mean"],
                             VA_n=ps["VALIDATE"]["n"], VA=ps["VALIDATE"]["mean"],
                             TE_n=ps["TEST"]["n"], TE=ps["TEST"]["mean"]))

def main():
    rows, t0 = [], time.time()
    cache = {}
    for bar in BARS:
        g = R.load_bars(bar)
        for K, fs in itertools.product(STATES, FSETS):
            M = R.Model(bar, K, fs, g=g)
            run_cells(M, "REAL", rows)
            orig = (M.state, M.lab, M.sign, M.tp)
            for sh in SHIFTS:
                good, src = shifted_view(M, sh)
                M.state = np.where(good, orig[0][src], -1)
                M.lab = np.where(good, orig[1][src], "NA")
                M.sign = np.where(good, orig[2][src], 0)
                M.tp = np.where(good, orig[3][src], np.nan)
                run_cells(M, f"NULL{sh}", rows)
            M.state, M.lab, M.sign, M.tp = orig
            print(f"  {bar:>3}m K={K} {fs:<9} cells={len(rows):>6} {time.time()-t0:>7.0f}s",
                  flush=True)
        del g
    D = pd.DataFrame(rows)
    D.to_csv(f"{ART}/tables/grid_a_all.csv", index=False)
    print(f"\nTOTAL ROWS {len(D)}  ({time.time()-t0:.0f}s)")
    print(D.world.value_counts().to_string())
main()
