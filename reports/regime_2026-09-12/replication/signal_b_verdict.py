#!/usr/bin/env python3
"""SIGNAL B — controls and verdict on the two cells that can be picked WITHOUT looking at P&L:
   (i) FREQUENCY-MATCHED: the construction whose trades/session is closest to the paper's
       289/947 = 0.305.  Frequency is the only construction diagnostic the paper reports, so
       this is a selection rule that never touches the outcome.
   (ii) BEST-t, reported only to show the ceiling of a deliberately overfit pick.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, fit_gmm, predict, tstat, day_block_bootstrap, splits, REP
from signal_b_grid import featspec, label, trades, LO, HI, BAR, HOLD

F = 1.25
PAPER_RATE = 289 / 947


def states_for(g, trs, feat, K, rule):
    X = featspec(g, feat); fin = np.isfinite(X).all(axis=1)
    M = fit_gmm(X[trs & fin], K); st = predict(X, M)
    mp, _ = label(g, X, st, trs, rule)
    return st, np.array([mp.get(s, -1) for s in st]), mp


def controls(g, st, mp, loose, tag, W, seed=17):
    rng = np.random.default_rng(seed)
    R = np.array([mp.get(s, -1) for s in st])
    real = trades(g, R, 0, loose)
    rpt = real.gross.values - F
    W(f"\n--- {tag} ---")
    W(f"REAL n={len(real)} ({len(real)/g.sess.nunique():.3f}/session; paper {PAPER_RATE:.3f}) "
      f"mean={rpt.mean():+.2f}pt t={tstat(rpt):+.2f} win={100*(rpt>0).mean():.1f}% "
      f"PF={rpt[rpt>0].sum()/max(-rpt[rpt<0].sum(),1e-9):.2f} "
      f"Sharpe(per-trade ann. n/a)={rpt.mean()/max(rpt.std(ddof=1),1e-9):.3f}")
    lo, hi, p0 = day_block_bootstrap(real.assign(pt=rpt))
    W(f"(c) day-block bootstrap 95% CI [{lo:+.2f},{hi:+.2f}]pt  P(<=0)={p0:.3f}  "
      f"{'EXCLUDES ZERO' if lo>0 else 'INCLUDES ZERO -> FAILS (c)'}")
    # C2 within-session label rotation
    starts = {}
    for i, s in enumerate(g.sess.values):
        starts.setdefault(s, []).append(i)
    means = []
    for _ in range(1000):
        st2 = st.copy()
        for s, ii in starts.items():
            a = np.array(ii); k = rng.integers(1, max(len(a), 2))
            st2[a] = st[a[(np.arange(len(a)) + k) % len(a)]]
        t = trades(g, np.array([mp.get(x, -1) for x in st2]), 0, loose)
        if len(t) >= 10:
            means.append((t.gross.values - F).mean())
    m2 = np.array(means)
    W(f"(b) C2 within-session LABEL-ROTATION control: mean={m2.mean():+.2f} sd={m2.std(ddof=1):.2f} "
      f"p(ctrl>=real)={(m2>=rpt.mean()).mean():.4f}  gap={(rpt.mean()-m2.mean())/m2.std(ddof=1):+.2f}sd "
      f"-> {'PASSES' if rpt.mean()>m2.mean()+m2.std(ddof=1) else 'FAILS'}")
    # C3 random entry, same n/session
    per = real.groupby("sess").size().to_dict()
    sess_arr = g.sess.values; op, cl = g.open.values, g.close.values
    elig = {s: [i for i in ii if i+HOLD < len(g) and sess_arr[i+HOLD] == s and i >= 3]
            for s, ii in starts.items()}
    m3 = []
    for _ in range(1000):
        acc = []
        for s, k in per.items():
            e = elig.get(s, [])
            if not e: continue
            for i in rng.choice(e, size=min(k, len(e)), replace=False):
                acc.append(cl[i+HOLD] - op[i+1] - F)
        if len(acc) >= 10:
            m3.append(np.mean(acc))
    m3 = np.array(m3)
    W(f"(b) C3 RANDOM-ENTRY control (same n/session, same hold, long): mean={m3.mean():+.2f} "
      f"sd={m3.std(ddof=1):.2f} p(ctrl>=real)={(m3>=rpt.mean()).mean():.4f} "
      f"gap={(rpt.mean()-m3.mean())/m3.std(ddof=1):+.2f}sd "
      f"-> {'PASSES' if rpt.mean()>m3.mean()+m3.std(ddof=1) else 'FAILS'}")
    # 1-bar delay
    t1 = trades(g, R, 1, loose)
    p1 = t1.gross.values - F
    W(f"1-BAR-DELAY: n={len(t1)} mean={p1.mean():+.2f} t={tstat(p1):+.2f}  "
      f"(paper: +5.15 -> -3.56, a SIGN REVERSAL). Here: {tstat(rpt):+.2f} -> {tstat(p1):+.2f} "
      f"= {'reversal' if tstat(rpt)*tstat(p1) < 0 else 'NO reversal'}")
    return real


def main():
    df = load_1min(); g = bars(df, BAR, LO, HI)
    TR, VA, TE = splits(g.sess.values); trs = g.sess.isin(TR).values
    fh = open(f"{REP}/signal_b_verdict.txt", "w")
    W = lambda s="": (print(s), fh.write(s + "\n"))
    W("SIGNAL B — CONTROLS AND VERDICT")
    W(f"paper trade rate {PAPER_RATE:.3f}/session; this lake has {g.sess.nunique()} London sessions")
    for tag, feat, K, rule, loose in [
        ("FREQUENCY-MATCHED  F3desk/K3/Lret/loose", "F3desk", 3, "Lret", True),
        ("BEST-t (overfit pick) F1dir/K3/Lret/loose", "F1dir", 3, "Lret", True),
        ("PRIMARY pre-spec    F2diract/K3/Lact/strict", "F2diract", 3, "Lact", False)]:
        st, R, mp = states_for(g, trs, feat, K, rule)
        controls(g, st, mp, loose, tag, W)
    fh.close()


if __name__ == "__main__":
    raise SystemExit(main())
