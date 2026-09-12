#!/usr/bin/env python3
"""SIGNAL B — the full grid of reasonable constructions.

The paper's Section 5.2 is ONE paragraph and specifies neither the GMM features, nor K, nor how
fitted components map to R0/R1/R2.  Rather than pick one and call it 'the' replication, every
plausible construction is run and ALL are reported.  Picking the best cell afterwards is the
overfit the paper itself warns about, so the grid is judged as a grid.
"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import (load_1min, bars, fit_gmm, predict, tstat, day_block_bootstrap, splits, REP)

LO, HI, BAR, HOLD = 180, 510, 15, 4


def featspec(g, which):
    c = g.close.values.astype(float); hi = g.high.values.astype(float)
    lo = g.low.values.astype(float); v = g.volume.values.astype(float)
    n = len(c); tr = np.maximum(hi - lo, .25)
    atr = pd.Series(tr).rolling(20, min_periods=5).mean().values
    def ret(k):
        r = np.zeros(n); r[k:] = c[k:] - c[:-k]; return r
    step = np.abs(np.diff(c, prepend=c[0]))
    def er(k):
        p = pd.Series(step).rolling(k, min_periods=2).sum().values
        return np.abs(ret(k)) / np.maximum(p, 1e-6)
    vm = pd.Series(v).rolling(50, min_periods=10).mean().values
    vs = pd.Series(v).rolling(50, min_periods=10).std(ddof=1).values
    vz = (v - vm) / np.maximum(vs, 1e-9)
    A = np.maximum(atr, 1e-6)
    if which == "F1dir":      # direction + efficiency only
        return np.column_stack([ret(1)/A, ret(4)/A, er(4)])
    if which == "F2diract":   # direction + efficiency + activity (range & volume)
        return np.column_stack([ret(1)/A, ret(4)/A, er(4), np.log(tr/A), vz])
    if which == "F3desk":     # the desk's existing bt_regime_transition.py features
        return np.column_stack([ret(4)/A, ret(8)/A, er(4), er(8)])
    raise ValueError(which)


def label(g, X, st, trmask, rule):
    r = np.zeros(len(g)); r[1:] = g.close.values[1:] - g.close.values[:-1]
    ks = sorted(set(st[trmask & (st >= 0)]))
    mr = {k: float(np.nanmean(r[trmask & (st == k)])) for k in ks}
    if rule == "Lret":        # R0 = most bearish, R2 = most bullish, R1 = the middle
        o = sorted(ks, key=lambda k: mr[k])
        return {o[0]: 0, o[1]: 1, o[2]: 2}, mr
    if rule == "Lact":        # R1 = the most ACTIVE state; the rest split by mean return
        act = {k: float(np.nanmean(np.log(np.maximum(g.high.values-g.low.values, .25))[trmask & (st == k)]))
               for k in ks}
        a1 = max(act, key=act.get)
        rest = sorted([k for k in ks if k != a1], key=lambda k: mr[k])
        return {rest[0]: 0, a1: 1, rest[-1]: 2}, mr
    raise ValueError(rule)


def trades(g, R, delay, loose):
    sess = g.sess.values; op = g.open.values; cl = g.close.values
    out = []
    for i in range(3, len(g) - (HOLD + 1 + delay)):
        if R[i] != 2 or sess[i] != sess[i-2]:
            continue
        if loose:
            if 0 not in (R[i-1], R[i-2]) or 1 in (R[i-1], R[i-2]):
                continue
        else:
            if R[i-1] != 0 or R[i-2] == 1:
                continue
        e = i + 1 + delay; x = e + HOLD - 1
        if x >= len(g) or sess[e] != sess[i] or sess[x] != sess[i]:
            continue
        out.append((sess[i], cl[x] - op[e]))
    return pd.DataFrame(out, columns=["sess", "gross"])


def main():
    df = load_1min()
    g = bars(df, BAR, LO, HI)
    TR, VA, TE = splits(g.sess.values)
    trs = g.sess.isin(TR).values
    fh = open(f"{REP}/signal_b_grid.txt", "w")
    W = lambda s="": (print(s), fh.write(s + "\n"))
    W("SIGNAL B GRID — every reasonable construction of the paper's underdetermined recipe")
    W(f"240 London sessions (03:00-08:30 ET, DST-aware), 15-min bars, hold 60m, entry next bar open")
    W("friction = this desk's measured 1.25pt.  PAPER: n=289, +5.77pt, t=+5.15, "
      "1-bar-delay t=-3.56\n")
    W(f"{'features':<9}{'K':>3}{'labels':>7}{'rule':>7}" +
      "".join(f"{p:>24}" for p in ("TRAIN", "VALIDATE", "TEST", "ALL")) + f"{'delay+1 ALL':>22}")
    W(f"{'':<26}" + "".join(f"{'n':>6}{'net':>7}{'t':>6}{'w%':>5}" for _ in range(4)) +
      f"{'n':>6}{'net':>7}{'t':>6}")
    F = 1.25
    rows = []
    for feat in ("F1dir", "F2diract", "F3desk"):
        X = featspec(g, feat)
        fin = np.isfinite(X).all(axis=1)
        for K in (3, 4):
            M = fit_gmm(X[trs & fin], K)
            st = predict(X, M)
            for rule in ("Lret", "Lact"):
                if K == 4 and rule == "Lact":
                    continue
                if K == 4:
                    # R0/R1/R2 = the 3 states by mean return with the 4th folded into 'other'
                    r = np.zeros(len(g)); r[1:] = g.close.values[1:]-g.close.values[:-1]
                    ks = sorted(set(st[trs & (st >= 0)]))
                    mr = {k: float(np.nanmean(r[trs & (st == k)])) for k in ks}
                    o = sorted(ks, key=lambda k: mr[k])
                    mp = {o[0]: 0, o[-1]: 2}
                    for k in o[1:-1]:
                        mp[k] = 1
                else:
                    mp, mr = label(g, X, st, trs, rule)
                R = np.array([mp.get(s, -1) for s in st])
                for loose in (False, True):
                    t0 = trades(g, R, 0, loose)
                    t1 = trades(g, R, 1, loose)
                    line = f"{feat:<9}{K:>3}{rule:>7}{'loose' if loose else 'strict':>7}"
                    for P in (TR, VA, TE, None):
                        d = t0 if P is None else t0[t0.sess.isin(P)]
                        if len(d) == 0:
                            line += f"{0:>6}{'-':>7}{'-':>6}{'-':>5}"
                        else:
                            pt = d.gross.values - F
                            line += f"{len(d):>6}{pt.mean():>7.2f}{tstat(pt):>6.2f}{100*(pt>0).mean():>5.0f}"
                    if len(t1):
                        p1 = t1.gross.values - F
                        line += f"{len(t1):>6}{p1.mean():>7.2f}{tstat(p1):>6.2f}"
                    else:
                        line += f"{0:>6}{'-':>7}{'-':>6}"
                    W(line)
                    if len(t0) >= 25:
                        pt = t0.gross.values - F
                        rows.append(dict(feat=feat, K=K, rule=rule, loose=loose, n=len(t0),
                                         mean=pt.mean(), t=tstat(pt),
                                         d1n=len(t1),
                                         d1t=tstat(t1.gross.values - F) if len(t1) else np.nan))
    W("")
    R = pd.DataFrame(rows)
    W(f"cells with n>=25: {len(R)}   positive mean: {(R['mean']>0).sum()}   "
      f"t>=2.0: {(R['t']>=2).sum()}   t<=-2.0: {(R['t']<=-2).sum()}")
    W(f"grid mean of cell means: {R['mean'].mean():+.2f}pt   best cell: "
      f"{R.loc[R['t'].idxmax()].to_dict() if len(R) else 'none'}")
    W("\nPAPER'S DIAGNOSTIC: the 1-bar delay should REVERSE a faithful replication.")
    W(f"cells where real t>0 AND delay t<0: {int(((R['t']>0)&(R['d1t']<0)).sum())} of {len(R)}")
    R.to_csv(f"{REP}/signal_b_grid.csv", index=False)
    fh.close()


if __name__ == "__main__":
    raise SystemExit(main())
