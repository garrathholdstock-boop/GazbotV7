#!/usr/bin/env python3
"""GRID B - Mesfin's entry/exit refinements, on structures chosen by TRAIN ONLY.

Structure selection uses the TRAIN-period mean of GRID A cells and nothing else, so VALIDATE
and TEST stay clean for the refinements themselves.

REFINEMENTS TESTED (all four are from the two signals that passed in Mesfin 2026):
  vz_min   volume z-score floor on the signal bar      None / 0.5 / 1.0
  tp_min   rolling-200-bar causal Markov P(prev->cur)  None / 0.15
  pull     ATR-scaled pullback limit entry (2 bars)    0 / 0.35 ATR   (unfilled = no trade)
  exit     fixed time  /  state-reversion capped at the same hold
Same shifted-world null as GRID A.
"""
import sys, os, time, itertools
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

ART = R.ART; FRIC = 1.25
HOLDS = [30, 45, 60, 75, 90, 120, 150, 180]
WINDOWS = {"ALL": None, "LDN": (480, 810), "RTH": (810, 1200),
           "OPEN": (810, 960), "EUUS": (480, 1200)}
SHIFTS = [-53, -37, -23, 17, 31, 47]
VZ = [None, 0.5, 1.0]; TP = [None, 0.15]; PULL = [0.0, 0.35]; EXIT = ["time", "revert"]
NSTRUCT = 8

A = pd.read_csv(f"{ART}/tables/grid_a_all.csv")
A = A[(A.world == "REAL") & (A.TR_n >= 150)]
sel = (A.groupby(["bar", "states", "fset", "clean", "win"])
         .agg(TR=("TR", "mean"), cells=("TR", "size")).reset_index()
         .sort_values("TR", ascending=False).head(NSTRUCT))
sel.to_csv(f"{ART}/tables/grid_b_structures.csv", index=False)
print("STRUCTURES CARRIED TO GRID B - ranked by TRAIN-period mean only")
print(sel.round(3).to_string(index=False), flush=True)

def shifted_view(M, sh):
    g = M.g
    ss = sorted(g.sess.unique()); pos = {s: k for k, s in enumerate(ss)}
    sidx = np.array([pos[s] for s in g.sess.values])
    key = pd.DataFrame({"s": sidx, "r": np.arange(len(g))}); key["rk"] = key.groupby("s").cumcount()
    tgt = key.copy(); tgt["s"] = (tgt.s + sh) % len(ss)
    m = key.merge(tgt, on=["s", "rk"], how="left", suffixes=("", "_t"))
    src = m["r_t"].values; good = ~np.isnan(src)
    return good, np.where(good, np.nan_to_num(src, nan=0).astype(int), 0)

def cells(M, clean, wn, tag, rows):
    for vz, tp in itertools.product(VZ, TP):
        idx = R.signals(M, clean=clean, win=WINDOWS[wn], vz_min=vz, tp_min=tp)
        if len(idx) < 80:
            continue
        for hm in HOLDS:
            if hm % M.bar:
                continue
            hold = hm // M.bar
            for pull, ex in itertools.product(PULL, EXIT):
                T = R.trades(M, idx, hold=hold, friction=FRIC, exit_mode=ex,
                             hold_cap=hold, pull=pull)
                if len(T) < 100:
                    continue
                ps = R.period_stats(T, M); sd = T.gross.std(ddof=1)
                rows.append(dict(world=tag, bar=M.bar, states=M.K, fset=M.fset, clean=clean,
                                 win=wn, hold_min=hm, vz=vz if vz else 0, tp=tp if tp else 0,
                                 pull=pull, exit=ex, n=len(T),
                                 gross=float(T.gross.mean()), gross_sd=float(sd),
                                 net=float(T.gross.mean() - FRIC),
                                 t=float((T.gross.mean() - FRIC) / (sd / np.sqrt(len(T)))),
                                 bars=float(T.bars.mean()),
                                 TR_n=ps["TRAIN"]["n"], TR=ps["TRAIN"]["mean"],
                                 VA_n=ps["VALIDATE"]["n"], VA=ps["VALIDATE"]["mean"],
                                 TE_n=ps["TEST"]["n"], TE=ps["TEST"]["mean"]))

rows, t0 = [], time.time()
gcache = {}
for (bar, K, fs), sub in sel.groupby(["bar", "states", "fset"]):
    if bar not in gcache:
        gcache = {bar: R.load_bars(bar)}
    M = R.Model(bar, K, fs, g=gcache[bar])
    orig = (M.state, M.lab, M.sign, M.tp)
    for _, r in sub.iterrows():
        cells(M, int(r.clean), r.win, "REAL", rows)
        for sh in SHIFTS:
            good, src = shifted_view(M, sh)
            M.state = np.where(good, orig[0][src], -1); M.lab = np.where(good, orig[1][src], "NA")
            M.sign = np.where(good, orig[2][src], 0);   M.tp = np.where(good, orig[3][src], np.nan)
            cells(M, int(r.clean), r.win, f"NULL{sh}", rows)
        M.state, M.lab, M.sign, M.tp = orig
    print(f"  {bar}m K={K} {fs} rows={len(rows)} {time.time()-t0:.0f}s", flush=True)
D = pd.DataFrame(rows); D.to_csv(f"{ART}/tables/grid_b_all.csv", index=False)
print(f"TOTAL {len(D)} rows, real {int((D.world=='REAL').sum())}  ({time.time()-t0:.0f}s)")
