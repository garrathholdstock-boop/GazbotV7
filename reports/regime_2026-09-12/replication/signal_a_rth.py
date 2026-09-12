#!/usr/bin/env python3
"""RTH CONFLUENCE SIGNAL (ATR-adaptive) — replication grid.

Paper 5.1: fires when, on a completed 5-min RTH bar, (a) GMM label == R1 'Active Flow',
(b) rolling 200-bar Markov transition prob to R2 > 0.15, (c) rolling 50-bar volume z > 0.5.
Entry on a 25-point ATR-scaled PULLBACK from the signal bar close. Exit at bar 13.
Reported: 538 in-sample signals, +15.77pt @ h13, t=5.83, 61.0% win, WF OOS t=3.11 / n=196 /
+11.82pt, perm p<0.001.
"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, fit_gmm, predict, tstat, day_block_bootstrap, splits, REP
from signal_b_grid import featspec, label

LO, HI, BAR = 570, 960, 5           # 09:30-16:00 ET
HOLD = 13                           # exit at bar 13 after ENTRY [G8]
PB_WIN = 3                          # limit lifetime in bars [G7]


def indicators(g):
    v = g.volume.values.astype(float)
    vm = pd.Series(v).rolling(50, min_periods=20).mean().values
    vs = pd.Series(v).rolling(50, min_periods=20).std(ddof=1).values
    vz = (v - vm) / np.maximum(vs, 1e-9)                                    # [G5]
    tr = np.maximum(g.high.values - g.low.values, .25)
    atr = pd.Series(tr).rolling(20, min_periods=5).mean().values
    return vz, atr


def markov_p12(R, win=200):
    """Causal rolling P(R1 -> R2) over the trailing `win` bars. [G4]"""
    n = len(R)
    from1 = (R[:-1] == 1).astype(float)
    to2 = ((R[:-1] == 1) & (R[1:] == 2)).astype(float)
    a = pd.Series(from1).rolling(win, min_periods=50).sum().values
    b = pd.Series(to2).rolling(win, min_periods=50).sum().values
    p = np.full(n, np.nan)
    p[1:] = np.where(a > 0, b / np.maximum(a, 1e-9), 0.0)   # known at the close of bar i
    return p


def run(g, R, vz, atr, pb_mode, pb_win, atr_ref, exit_anchor="entry", delay=0,
        pmin=0.15, vmin=0.5):
    sess = g.sess.values; op = g.open.values; cl = g.close.values; lo = g.low.values
    p12 = markov_p12(R)
    sig, out = 0, []
    for i in range(1, len(g) - (HOLD + 2 + delay)):
        if R[i] != 1 or not np.isfinite(p12[i]) or p12[i] <= pmin:
            continue
        if not np.isfinite(vz[i]) or vz[i] <= vmin:
            continue
        sig += 1
        if pb_mode == "none":
            e = i + 1 + delay
            if sess[e] != sess[i]:
                continue
            px = op[e]
        else:
            d = 25.0 if pb_mode == "fix25" else 25.0 * atr[i] / atr_ref          # [G6]
            lim = cl[i] - d
            e = None
            for j in range(i + 1 + delay, min(i + 1 + delay + pb_win, len(g))):
                if sess[j] != sess[i]:
                    break
                if lo[j] <= lim:
                    e = j; break
            if e is None:
                continue
            px = min(lim, op[e])          # filled at the limit, or better on a gap-through
        x = (e if exit_anchor == "entry" else i) + HOLD
        if x >= len(g) or sess[x] != sess[i]:
            # cap at the session's last bar
            last = np.searchsorted(sess, sess[i], side="right") - 1
            x = last
            if x <= e:
                continue
        out.append((sess[i], px, cl[x], cl[x] - px))
    return sig, pd.DataFrame(out, columns=["sess", "entry", "exit", "gross"])


def main():
    df = load_1min(); g = bars(df, BAR, LO, HI)
    TR, VA, TE = splits(g.sess.values); trs = g.sess.isin(TR).values
    vz, atr = indicators(g)
    atr_ref = float(np.nanmedian(atr[trs]))
    fh = open(f"{REP}/signal_a_grid.txt", "w")
    W = lambda s="": (print(s), fh.write(s + "\n"))
    W("RTH CONFLUENCE SIGNAL — replication grid")
    W(f"{g.sess.nunique()} RTH sessions, {len(g)} 5-min bars (09:30-16:00 ET, DST-aware), "
      f"TRAIN {len(TR)}/VAL {len(VA)}/TEST {len(TE)} sessions")
    W(f"TRAIN median ATR20(5m) = {atr_ref:.2f}pt (the ATR-scaling reference [G6])")
    W(f"PAPER: 538 in-sample signals over ~750 days = 0.717 sig/session; +15.77pt, t=5.83, "
      f"61.0% win; OOS n=196, +11.82pt, t=3.11\n")
    F = 1.25
    rows = []
    W(f"{'feat':<9}{'lbl':>5}{'pullback':>10}{'life':>5}{'sig':>6}{'sig/s':>7}" +
      "".join(f"{p:>22}" for p in ("TRAIN", "VALIDATE", "TEST", "ALL")))
    W(f"{'':<42}" + "".join(f"{'n':>6}{'net':>6}{'t':>5}{'w%':>5}" for _ in range(4)))
    for feat in ("F1dir", "F2diract", "F3desk"):
        X = featspec(g, feat); fin = np.isfinite(X).all(axis=1)
        M = fit_gmm(X[trs & fin], 3); st = predict(X, M)
        for rule in ("Lret", "Lact"):
            mp, _ = label(g, X, st, trs, rule)
            R = np.array([mp.get(s, -1) for s in st])
            for pb in ("atr25", "fix25", "none"):
                for life in ((3, 6) if pb != "none" else (0,)):
                    sig, t0 = run(g, R, vz, atr, pb, life, atr_ref)
                    line = (f"{feat:<9}{rule:>5}{pb:>10}{life:>5}{sig:>6}"
                            f"{sig/g.sess.nunique():>7.2f}")
                    for P in (TR, VA, TE, None):
                        d = t0 if P is None else t0[t0.sess.isin(P)]
                        if len(d) == 0:
                            line += f"{0:>6}{'-':>6}{'-':>5}{'-':>5}"
                        else:
                            pt = d.gross.values - F
                            line += (f"{len(d):>6}{pt.mean():>6.2f}{tstat(pt):>5.2f}"
                                     f"{100*(pt>0).mean():>5.0f}")
                    W(line)
                    if len(t0) >= 30:
                        pt = t0.gross.values - F
                        rows.append(dict(feat=feat, rule=rule, pb=pb, life=life, sig=sig,
                                         sig_per_sess=sig/g.sess.nunique(), n=len(t0),
                                         mean=pt.mean(), t=tstat(pt)))
    R2 = pd.DataFrame(rows)
    R2.to_csv(f"{REP}/signal_a_grid.csv", index=False)
    W("")
    W(f"cells with n>=30: {len(R2)}  positive mean: {(R2['mean']>0).sum()}  "
      f"t>=2: {(R2['t']>=2).sum()}  t<=-2: {(R2['t']<=-2).sum()}  "
      f"grid mean of means: {R2['mean'].mean():+.2f}pt")
    if len(R2):
        R2["freq_err"] = (R2.sig_per_sess - 0.717).abs()
        fm = R2.loc[R2.freq_err.idxmin()]
        W(f"\nFREQUENCY-MATCHED cell (paper 0.717 sig/session): {fm.feat}/{fm.rule}/{fm.pb}/"
          f"life{int(fm.life)} -> {fm.sig_per_sess:.2f} sig/s, n={int(fm.n)}, "
          f"mean={fm['mean']:+.2f}pt, t={fm['t']:+.2f}")
        bt = R2.loc[R2['t'].idxmax()]
        W(f"BEST-t cell: {bt.feat}/{bt.rule}/{bt.pb}/life{int(bt.life)} -> n={int(bt.n)}, "
          f"mean={bt['mean']:+.2f}pt, t={bt['t']:+.2f}")
    fh.close()


if __name__ == "__main__":
    raise SystemExit(main())
