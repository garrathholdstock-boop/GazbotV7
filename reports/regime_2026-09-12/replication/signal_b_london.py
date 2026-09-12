#!/usr/bin/env python3
"""LONDON SESSION SIGNAL B (R0 -> R2) — replication on GAZBOT V7's MNQ lake.

Paper: 289 trades, +5.77pt net (2.0pt friction), t=5.15, 64.7% win, PF 2.42, Sharpe 5.09,
perm p<0.001, 1-bar delay reverses to t=-3.56.
"""
from __future__ import annotations
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import (load_1min, bars, features, fit_gmm, predict, name_states, tstat,
                 day_block_bootstrap, splits, FRICTION, REP, GUESSES)

LO, HI, BAR = 180, 510, 15          # 03:00-08:30 ET, 15-min bars
HOLD = 4                            # 4 x 15min = 60 minutes


def build_trades(state, g, mapping, delay=0, loose=False):
    """state: component ids; mapping: component -> R-number."""
    R = np.array([mapping.get(s, -1) for s in state])
    sess = g.sess.values; op = g.open.values; cl = g.close.values
    slot = g.slot.values
    out = []
    for i in range(3, len(g) - (HOLD + 1 + delay)):
        if R[i] != 2:
            continue
        if sess[i] != sess[i-1] or sess[i] != sess[i-2]:
            continue
        if loose:
            # came from R0 in the prior two bars with no R1 contamination
            if 0 not in (R[i-1], R[i-2]) or 1 in (R[i-1], R[i-2]):
                continue
        else:
            if R[i-1] != 0 or R[i-2] == 1:      # GUESS[G10]
                continue
        e = i + 1 + delay                        # entry bar (its OPEN)
        x = e + HOLD - 1                         # exit at this bar's CLOSE = entry+60min
        if x >= len(g) or sess[e] != sess[i] or sess[x] != sess[i]:
            continue
        out.append((sess[i], slot[i], op[e], cl[x], cl[x] - op[e]))
    return pd.DataFrame(out, columns=["sess", "slot", "entry", "exit", "gross"])


def report(tr, fric, TR, VA, TE, title, fh):
    def blk(d):
        if d is None or len(d) == 0:
            return "     0       -       -       -"
        pt = d.gross.values - fric
        return f"{len(d):>6}{pt.mean():>8.2f}{tstat(pt):>8.2f}{100*(pt>0).mean():>7.0f}%"
    line = f"{title:<34}"
    for P in (TR, VA, TE, None):
        d = tr if P is None else tr[tr.sess.isin(P)]
        line += "  " + blk(d)
    print(line); fh.write(line + "\n")


def main():
    df = load_1min()
    g = bars(df, BAR, LO, HI)
    X, atr, vz = features(g)
    TR, VA, TE = splits(g.sess.values)
    fin = np.isfinite(X).all(axis=1)
    trm = g.sess.isin(TR).values & fin
    M = fit_gmm(X[trm], 3)
    st = predict(X, M)
    mapping, stats = name_states(g, X, st, g.sess.isin(TR).values)

    fh = open(f"{REP}/signal_b_results.txt", "w")
    W = lambda s="": (print(s), fh.write(s + "\n"))
    W("LONDON SESSION SIGNAL B (R0->R2) — replication")
    W(f"tape: {g.sess.nunique()} London sessions, {len(g)} 15-min bars, "
      f"{g.sess.min()} .. {g.sess.max()}  (03:00-08:30 ET, DST-aware)")
    W(f"split: TRAIN {len(TR)} sess / VALIDATE {len(VA)} / TEST {len(TE)}  (40/30/30 chronological)")
    W("")
    W("GMM fitted on TRAIN London bars only, applied unchanged. K=3 [G2]. States named by "
      "TRAIN statistics [G3]:")
    W(f"{'comp':>5}{'R#':>4}{'share':>8}{'mean ret':>10}{'drift4/ATR':>12}{'effic4':>9}"
      f"{'log rng/ATR':>13}{'vol z':>8}  name")
    NAMES = {0: "R0 Bearish Chop", 1: "R1 Active Flow", 2: "R2 Bullish Drift"}
    for k in sorted(stats, key=lambda k: mapping[k]):
        s = stats[k]
        W(f"{k:>5}{mapping[k]:>4}{100*s['share']:>7.0f}%{s['mean_ret']:>10.2f}"
          f"{s['drift4']:>12.2f}{s['eff']:>9.2f}{s['act_range']:>13.2f}{s['act_vol']:>8.2f}  "
          f"{NAMES[mapping[k]]}")
    W("")

    variants = {}
    for loose in (False, True):
        for delay in (0, 1):
            variants[(loose, delay)] = build_trades(st, g, mapping, delay=delay, loose=loose)

    real = variants[(False, 0)]
    for fname, fric in FRICTION.items():
        W(f"\n=== friction {fname} ===")
        W(f"{'variant':<34}" + "".join(f"{p:>31}" for p in ("TRAIN", "VALIDATE", "TEST", "ALL")))
        W(f"{'':<34}" + "".join(f"{'n':>8}{'net pt':>8}{'t':>8}{'win':>8}" for _ in range(4)))
        report(variants[(False, 0)], fric, TR, VA, TE, "PRIMARY  R0->R2 clean, entry+0", fh)
        report(variants[(False, 1)], fric, TR, VA, TE, "1-BAR DELAY (paper: destroys it)", fh)
        report(variants[(True, 0)], fric, TR, VA, TE, "loose 'from R0 in prior 2' [G10]", fh)
        report(variants[(True, 1)], fric, TR, VA, TE, "loose + 1-bar delay", fh)

    # ── controls on the PRIMARY variant ──
    W("\n\n=== CONTROLS (primary variant, all sessions, desk friction 1.25pt) ===")
    fric = FRICTION["desk_1.25pt"]
    rpt = real.gross.values - fric
    W(f"REAL: n={len(real)}  mean={rpt.mean():+.2f}pt  t={tstat(rpt):.2f}  "
      f"win={100*(rpt>0).mean():.1f}%  "
      f"PF={rpt[rpt>0].sum()/max(-rpt[rpt<0].sum(),1e-9):.2f}")

    lo, hi, p0 = day_block_bootstrap(real.assign(pt=rpt))
    W(f"(c) DAY-BLOCK BOOTSTRAP 95% CI on mean net: [{lo:+.2f}, {hi:+.2f}]pt   "
      f"P(mean<=0)={p0:.3f}   {'EXCLUDES ZERO' if lo > 0 else 'INCLUDES ZERO -> FAILS (c)'}")

    rng = np.random.default_rng(11)
    # C1 label permutation (the coarse control the addendum criticises)
    perms = [p for p in [(0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0)]]
    vals = []
    inv = {v: k for k, v in mapping.items()}
    for p in perms:
        m2 = {inv[i]: p[i] for i in range(3)}
        t = build_trades(st, g, m2)
        if len(t) >= 30:
            vals.append((t.gross.values - fric).mean())
    W(f"C1 label-permutation control (5 draws): mean={np.mean(vals):+.2f}pt "
      f"sd={np.std(vals, ddof=1):.2f}  n_cells={len(vals)}")

    # C2 within-session circular rotation of the state sequence
    idx = np.arange(len(g)); means = []; ns = []
    sess_arr = g.sess.values
    starts = {}
    for i, s in enumerate(sess_arr):
        starts.setdefault(s, []).append(i)
    for d in range(1000):
        st2 = st.copy()
        for s, ii in starts.items():
            k = rng.integers(1, max(len(ii), 2))
            st2[ii] = st[np.array(ii)[(np.arange(len(ii)) + k) % len(ii)]]
        t = build_trades(st2, g, mapping)
        if len(t) >= 20:
            means.append((t.gross.values - fric).mean()); ns.append(len(t))
    means = np.array(means)
    W(f"C2 within-session LABEL-ROTATION control ({len(means)} draws, median n={int(np.median(ns))}): "
      f"mean={means.mean():+.2f}pt sd={means.std(ddof=1):.2f}   "
      f"p(control>=real)={(means >= rpt.mean()).mean():.4f}")
    W(f"   real beats control by {(rpt.mean()-means.mean())/max(means.std(ddof=1),1e-9):.2f} control-sd "
      f"-> {'PASSES (b)' if rpt.mean() > means.mean() + means.std(ddof=1) else 'FAILS (b)'}")

    # C3 random-entry control: same trades/session, random eligible entry bar, same hold
    per_sess = real.groupby("sess").size().to_dict()
    elig = {s: [i for i in ii if i + HOLD < len(g) and sess_arr[i + HOLD] == s and i - 3 >= 0]
            for s, ii in starts.items()}
    op, cl = g.open.values, g.close.values
    means3 = []
    for d in range(1000):
        acc = []
        for s, k in per_sess.items():
            e = elig.get(s, [])
            if not e:
                continue
            pick = rng.choice(e, size=min(k, len(e)), replace=False)
            for i in pick:
                acc.append(cl[i + HOLD] - op[i + 1] - fric)
        if len(acc) >= 20:
            means3.append(np.mean(acc))
    means3 = np.array(means3)
    W(f"C3 RANDOM-ENTRY control ({len(means3)} draws, same n/session, same 60m hold, long): "
      f"mean={means3.mean():+.2f}pt sd={means3.std(ddof=1):.2f}   "
      f"p(control>=real)={(means3 >= rpt.mean()).mean():.4f}")
    W(f"   real beats control by {(rpt.mean()-means3.mean())/max(means3.std(ddof=1),1e-9):.2f} control-sd "
      f"-> {'PASSES (b)' if rpt.mean() > means3.mean() + means3.std(ddof=1) else 'FAILS (b)'}")

    real.assign(net_125=rpt).to_csv(f"{REP}/signal_b_trades.csv", index=False)
    W(f"\ntrades written to {REP}/signal_b_trades.csv")
    fh.close()


if __name__ == "__main__":
    raise SystemExit(main())
