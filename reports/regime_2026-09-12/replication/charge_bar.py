#!/usr/bin/env python3
"""Charge THE BAR, not just the best cell.

Our filter is: (a) mean>0 at 1.25pt, (b) beats the same-entry control by >1 control sd,
(c) session-clustered t >= 1.96, (d) positive in TRAIN, VALIDATE and TEST. Applied to a search
of N constructions, how many cells pass BY CHANCE? Re-run the identical filter on the
session-permuted outcome and count survivors per placebo search."""
from __future__ import annotations
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, splits, REP
from spec_search import featspec, ret_all_simple, ret_all_pullback

SIG = sys.argv[1]; DRAWS = int(sys.argv[2]) if len(sys.argv) > 2 else 60
LO, HI, BAR, HOLD = (180, 510, 15, 4) if SIG == "B" else (570, 960, 5, 13)


def main():
    df = load_1min(); g = bars(df, BAR, LO, HI).reset_index(drop=True)
    TR, VA, TE = splits(g.sess.values); trs = g.sess.isin(TR).values
    _, atr, vz = featspec(g, "F2diract"); atr_ref = float(np.nanmedian(atr[trs]))
    R = pd.read_csv(f"{REP}/spec_search_{SIG}.csv")
    masks = np.load(f"{REP}/spec_masks_{SIG}.npy")
    sess = g.sess.values; slot = g.slot.values
    us = pd.unique(pd.Series(sess)); si = {s: i for i, s in enumerate(us)}
    nsl = int(slot.max()) + 1
    IDX = np.full((len(us), nsl), -1, np.int64)
    for i in range(len(g)):
        IDX[si[sess[i]], slot[i]] = i
    srow = np.array([si[s] for s in sess]); scol = slot.astype(int)
    codes = srow
    per = np.zeros(len(g), np.int8)
    per[pd.Series(sess).isin(VA).values] = 1
    per[pd.Series(sess).isin(TE).values] = 2

    RET = {}
    for ex in R["exec"].unique():
        p = ex.split("/")
        RET[ex] = (ret_all_simple(g, HOLD, 0) if (SIG == "B" or p[0] == "none")
                   else ret_all_pullback(g, atr, atr_ref, HOLD, p[0], int(p[1]), p[2]))
    cells = [np.where(masks[i])[0].astype(np.int32) for i in range(len(R))]
    exarr = R["exec"].values
    rng = np.random.default_rng(7)
    surv = []
    for d in range(DRAWS):
        perm = rng.permutation(len(us))
        j = IDX[perm[srow], scol]
        PL = {ex: np.where(j >= 0, r[np.maximum(j, 0)], np.nan) for ex, r in RET.items()}
        # per-session mean/var of each permuted ret, for the control
        ST = {}
        for ex, r in PL.items():
            ok = np.isfinite(r)
            s_ = codes[ok]; v_ = r[ok]
            cnt = np.bincount(s_, minlength=len(us))
            sm = np.bincount(s_, weights=v_, minlength=len(us))
            sq = np.bincount(s_, weights=v_ ** 2, minlength=len(us))
            mu = np.where(cnt > 0, sm / np.maximum(cnt, 1), np.nan)
            va = np.where(cnt > 1, sq / np.maximum(cnt, 1) - mu ** 2, 0.0)
            ST[ex] = (mu, np.maximum(va, 0))
        k = 0
        for ci, idx in enumerate(cells):
            r = PL[exarr[ci]]
            v = r[idx]; fin = np.isfinite(v)
            v = v[fin]; ii = idx[fin]
            n = len(v)
            if n < 25:
                continue
            m = v.mean()
            if m <= 0:
                continue
            sc = codes[ii]
            mu, va = ST[exarr[ci]]
            cnt = np.bincount(sc, minlength=len(us))
            cm = (cnt * np.nan_to_num(mu)).sum() / n
            csd = np.sqrt((cnt * va).sum()) / n
            if not (csd > 0 and (m - cm) / csd > 1):
                continue
            gs = np.bincount(sc, weights=v, minlength=len(us))
            kk = (cnt > 0).sum()
            se = np.sqrt(((gs[cnt > 0] - n * m / kk) ** 2).sum()) / n
            if not (se > 0 and m / se >= 1.96):
                continue
            pr = per[ii]
            if not all((pr == q).sum() >= 10 and v[pr == q].mean() > 0 for q in (0, 1, 2)):
                continue
            k += 1
        surv.append(k)
        if (d + 1) % 10 == 0:
            print(f"  draw {d+1}/{DRAWS}: survivors so far median {np.median(surv):.0f}")
    surv = np.array(surv)
    real = {"A": 8, "B": 26}[SIG]
    out = (f"BAR CHARGE — signal {SIG}\n"
           f"constructions: {len(R)}   placebo searches: {DRAWS}\n"
           f"cells passing (a)+(b)+(c)+(d) under the NULL: mean {surv.mean():.1f}  "
           f"median {np.median(surv):.0f}  90th pct {np.percentile(surv,90):.0f}  max {surv.max()}\n"
           f"cells passing on the REAL tape: {real}\n"
           f"p(null search yields >= {real} survivors) = {(surv >= real).mean():.3f}\n")
    print(out)
    open(f"{REP}/bar_charge_{SIG}.txt", "w").write(out)


if __name__ == "__main__":
    raise SystemExit(main())
