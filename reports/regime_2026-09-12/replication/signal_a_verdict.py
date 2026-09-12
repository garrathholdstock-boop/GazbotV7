#!/usr/bin/env python3
"""SIGNAL A — harness sanity check, diagnostics, and time-of-day-matched controls."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, fit_gmm, predict, tstat, day_block_bootstrap, splits, REP
from signal_b_grid import featspec, label
from signal_a_rth import indicators, markov_p12, run, LO, HI, BAR, HOLD

F = 1.25


def main():
    df = load_1min(); g = bars(df, BAR, LO, HI)
    TR, VA, TE = splits(g.sess.values); trs = g.sess.isin(TR).values
    vz, atr = indicators(g)
    atr_ref = float(np.nanmedian(atr[trs]))
    sess = g.sess.values; cl = g.close.values; op = g.open.values
    fh = open(f"{REP}/signal_a_verdict.txt", "w")
    W = lambda s="": (print(s), fh.write(s + "\n"))

    # ── 0. HARNESS SANITY: unconditional 13-bar long from every RTH bar ──
    W("0. HARNESS SANITY CHECK — unconditional 13-bar (65m) long from EVERY RTH 5-min bar")
    ok = np.arange(len(g) - HOLD)
    ok = ok[sess[ok] == sess[ok + HOLD]]
    unc = cl[ok + HOLD] - op[ok + 1]
    W(f"   n={len(unc)}  gross mean={unc.mean():+.3f}pt  sd={unc.std(ddof=1):.1f}  "
      f"t={tstat(unc):+.2f}   net@1.25={unc.mean()-F:+.3f}pt")
    W("   -> the tape's own unconditional 65-min drift. Any signal must beat THIS, not zero.\n")
    tod = pd.DataFrame({"m": g.m.values[ok], "r": unc}).groupby("m").r.agg(["size", "mean"])
    W("   unconditional 65m drift by entry minute-of-day (ET):")
    W("   " + "  ".join(f"{int(m//60):02d}:{int(m%60):02d}={v:+.1f}"
                        for m, v in tod["mean"].items() if int(m) % 30 == 0))
    W("")

    # ── 1. per-spec state stats + signal diagnostics ──
    specs = [("F1dir", "Lret", "atr25", 3, "FREQUENCY-MATCHED (0.37 vs paper 0.717 sig/s)"),
             ("F2diract", "Lret", "atr25", 6, "BEST-t of the grid"),
             ("F3desk", "Lret", "none", 0, "largest-n, no pullback layer")]
    for feat, rule, pb, life, tag in specs:
        X = featspec(g, feat); fin = np.isfinite(X).all(axis=1)
        M = fit_gmm(X[trs & fin], 3); st = predict(X, M)
        mp, mr = label(g, X, st, trs, rule)
        R = np.array([mp.get(s, -1) for s in st])
        W(f"=== {feat}/{rule}/{pb}/life{life}  — {tag} ===")
        r = np.zeros(len(g)); r[1:] = cl[1:] - cl[:-1]
        for k in sorted(mp, key=lambda k: mp[k]):
            m = trs & (st == k)
            W(f"   comp {k} -> R{mp[k]}  share {100*m.sum()/trs.sum():>4.0f}%  "
              f"mean bar ret {np.nanmean(r[m]):+6.2f}pt  mean |ret| {np.nanmean(np.abs(r[m])):5.2f}")
        p12 = markov_p12(R)
        a = R == 1; b = np.isfinite(p12) & (p12 > 0.15); c = np.isfinite(vz) & (vz > 0.5)
        W(f"   condition hit rates: (a) R1 {100*a.mean():.1f}%  (b) P(1->2)>0.15 "
          f"{100*b.mean():.1f}%  (c) volz>0.5 {100*c.mean():.1f}%  ALL THREE "
          f"{100*(a&b&c).mean():.2f}%")
        sig, t0 = run(g, R, vz, atr, pb, life, atr_ref)
        if len(t0) < 20:
            W("   too few trades\n"); continue
        pt = t0.gross.values - F
        W(f"   signals={sig}  fills={len(t0)}  mean={pt.mean():+.2f}pt  t={tstat(pt):+.2f}  "
          f"win={100*(pt>0).mean():.0f}%  @2.0pt friction={pt.mean()-0.75:+.2f}pt")
        lo, hi, p0 = day_block_bootstrap(t0.assign(pt=pt))
        W(f"   (c) day-block bootstrap 95% CI [{lo:+.2f},{hi:+.2f}]  P(<=0)={p0:.3f}  "
          f"{'EXCLUDES ZERO' if lo>0 else 'INCLUDES ZERO -> FAILS (c)'}")
        # time-of-day + session matched random-entry control (vectorised)
        smask = a & b & c
        sig_m = g.m.values[smask]; sig_s = sess[smask]
        rng = np.random.default_rng(5)
        allm = g.m.values
        valid = np.zeros(len(g), bool)
        vi = np.arange(len(g) - HOLD - 1)
        vi = vi[sess[vi] == sess[vi + HOLD]]
        valid[vi] = True
        pool = {}
        for mm in np.unique(sig_m):
            idx = np.where((allm == mm) & valid)[0]
            pool[mm] = (idx, sess[idx])
        means = []
        for _ in range(500):
            acc = []
            for mm, sX in zip(sig_m, sig_s):
                idx, ids = pool[mm]
                keep = idx[ids != sX]
                if len(keep) == 0:
                    continue
                j = keep[rng.integers(len(keep))]
                acc.append(cl[j + HOLD] - op[j + 1] - F)
            if len(acc) >= 20:
                means.append(np.mean(acc))
        m4 = np.array(means)
        W(f"   (b) TIME-OF-DAY-MATCHED control (same minute-of-day, different session, "
          f"{len(m4)} draws): mean={m4.mean():+.2f} sd={m4.std(ddof=1):.2f} "
          f"p(ctrl>=real)={(m4>=pt.mean()).mean():.3f} "
          f"gap={(pt.mean()-m4.mean())/max(m4.std(ddof=1),1e-9):+.2f}sd -> "
          f"{'PASSES' if pt.mean()>m4.mean()+m4.std(ddof=1) else 'FAILS'}")
        W("")
    fh.close()


if __name__ == "__main__":
    raise SystemExit(main())
