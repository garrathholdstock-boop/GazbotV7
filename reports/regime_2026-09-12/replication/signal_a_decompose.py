#!/usr/bin/env python3
"""SIGNAL A — condition decomposition and K sweep.
Question for the operator: forget the paper's packaging — does ANY of the three confluence
conditions carry forward information on this tape, measured against a time-of-day-matched
control rather than against zero?"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, fit_gmm, predict, tstat, splits, REP
from signal_b_grid import featspec, label
from signal_a_rth import indicators, markov_p12, LO, HI, BAR, HOLD

F = 1.25


def tod_control(g, sess, cl, op, mask, valid, draws=400, seed=5):
    rng = np.random.default_rng(seed)
    allm = g.m.values
    sig_m, sig_s = allm[mask], sess[mask]
    pool = {mm: (np.where((allm == mm) & valid)[0],) for mm in np.unique(sig_m)}
    pool = {mm: (i[0], sess[i[0]]) for mm, i in pool.items()}
    out = []
    for _ in range(draws):
        acc = []
        for mm, sX in zip(sig_m, sig_s):
            idx, ids = pool[mm]; keep = idx[ids != sX]
            if len(keep):
                j = keep[rng.integers(len(keep))]
                acc.append(cl[j + HOLD] - op[j + 1] - F)
        if len(acc) >= 20:
            out.append(np.mean(acc))
    return np.array(out)


def main():
    df = load_1min(); g = bars(df, BAR, LO, HI)
    TR, VA, TE = splits(g.sess.values); trs = g.sess.isin(TR).values
    vz, atr = indicators(g)
    sess, cl, op = g.sess.values, g.close.values, g.open.values
    valid = np.zeros(len(g), bool)
    vi = np.arange(len(g) - HOLD - 1); vi = vi[sess[vi] == sess[vi + HOLD]]
    valid[vi] = True
    fwd = np.full(len(g), np.nan); fwd[vi] = cl[vi + HOLD] - op[vi + 1]

    fh = open(f"{REP}/signal_a_decompose.txt", "w")
    W = lambda s="": (print(s), fh.write(s + "\n"))
    W("SIGNAL A — CONDITION DECOMPOSITION (13-bar/65-min long, net @1.25pt, entry next bar open)")
    W("judged against a TIME-OF-DAY-MATCHED control, not against zero\n")

    W("--- K sweep, feature spec F2diract, labelling Lret ---")
    W(f"{'K':>3}{'R1 share':>10}{'(b) hit':>9}{'ALL3':>8}{'n':>7}{'net pt':>9}{'t':>7}"
      f"{'ctrl mean':>11}{'gap sd':>9}")
    X = featspec(g, "F2diract"); fin = np.isfinite(X).all(axis=1)
    for K in (2, 3, 4, 5, 6):
        M = fit_gmm(X[trs & fin], K); st = predict(X, M)
        r = np.zeros(len(g)); r[1:] = cl[1:] - cl[:-1]
        ks = sorted(set(st[trs & (st >= 0)]))
        mr = {k: float(np.nanmean(r[trs & (st == k)])) for k in ks}
        o = sorted(ks, key=lambda k: mr[k])
        mp = {o[0]: 0, o[-1]: 2}
        for k in o[1:-1]:
            mp[k] = 1
        R = np.array([mp.get(s, -1) for s in st])
        p12 = markov_p12(R)
        a = R == 1; b = np.isfinite(p12) & (p12 > .15); c = np.isfinite(vz) & (vz > .5)
        m = a & b & c & valid
        if m.sum() < 30:
            W(f"{K:>3}{100*a.mean():>9.0f}%{100*b.mean():>8.0f}%{100*(a&b&c).mean():>7.1f}%"
              f"{m.sum():>7}   (too few)"); continue
        pt = fwd[m] - F
        ctl = tod_control(g, sess, cl, op, m, valid)
        W(f"{K:>3}{100*a.mean():>9.0f}%{100*b.mean():>8.0f}%{100*(a&b&c).mean():>7.1f}%"
          f"{m.sum():>7}{pt.mean():>9.2f}{tstat(pt):>7.2f}{ctl.mean():>11.2f}"
          f"{(pt.mean()-ctl.mean())/max(ctl.std(ddof=1),1e-9):>9.2f}")

    W("\n--- single conditions and pairs (F2diract/Lret/K=3) ---")
    M = fit_gmm(X[trs & fin], 3); st = predict(X, M)
    mp, _ = label(g, X, st, trs, "Lret")
    R = np.array([mp.get(s, -1) for s in st])
    p12 = markov_p12(R)
    conds = {
        "(a) state == R1 Active Flow": R == 1,
        "(a') state == R2 Bullish Drift": R == 2,
        "(b) rolling P(R1->R2) > 0.15": np.isfinite(p12) & (p12 > .15),
        "(c) 50-bar volume z > 0.5": np.isfinite(vz) & (vz > .5),
        "(c') volume z > 1.5": np.isfinite(vz) & (vz > 1.5),
        "(a)+(c)": (R == 1) & np.isfinite(vz) & (vz > .5),
        "(a)+(b)+(c)  THE SIGNAL": (R == 1) & np.isfinite(p12) & (p12 > .15) & np.isfinite(vz) & (vz > .5),
        "ALL BARS (baseline)": np.ones(len(g), bool),
    }
    W(f"{'condition':<34}{'n':>7}{'net pt':>9}{'t':>7}{'win%':>7}{'ctrl mean':>11}"
      f"{'gap (sd)':>10}{'verdict':>10}")
    for nm, msk in conds.items():
        m = msk & valid
        if m.sum() < 30:
            continue
        pt = fwd[m] - F
        ctl = tod_control(g, sess, cl, op, m, valid)
        gap = (pt.mean() - ctl.mean()) / max(ctl.std(ddof=1), 1e-9)
        W(f"{nm:<34}{m.sum():>7}{pt.mean():>9.2f}{tstat(pt):>7.2f}"
          f"{100*(pt>0).mean():>6.0f}%{ctl.mean():>11.2f}{gap:>10.2f}"
          f"{('  BEATS' if gap > 1 else '    no'):>10}")
    W("\nnote: the time-of-day control has n equal to the condition's own n, so its sd is the")
    W("honest yardstick for a gap. 'BEATS' means real > control mean + 1 control sd.")
    fh.close()


if __name__ == "__main__":
    raise SystemExit(main())
