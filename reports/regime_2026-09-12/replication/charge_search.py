#!/usr/bin/env python3
"""THE SEARCH CHARGE.

Re-score EVERY construction in the search against a session-permuted outcome: a trade taken at
slot k of session s is paid the return the SAME execution variant would have earned at slot k of
a randomly chosen OTHER session. Time-of-day structure, execution mechanics and the return
distribution are all preserved; only the link between the regime labels and the outcome is cut.

The statistic that matters is the MAX t OVER THE WHOLE SEARCH, drawn from this null. That is what
a search of this size is worth by chance.
"""
from __future__ import annotations
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, splits, REP, tstat
from spec_search import featspec, ret_all_simple, ret_all_pullback, F

SIG = sys.argv[1]
DRAWS = int(sys.argv[2]) if len(sys.argv) > 2 else 100
if SIG == "B":
    LO, HI, BAR, HOLD = 180, 510, 15, 4
else:
    LO, HI, BAR, HOLD = 570, 960, 5, 13


def main():
    df = load_1min(); g = bars(df, BAR, LO, HI).reset_index(drop=True)
    TR, VA, TE = splits(g.sess.values); trs = g.sess.isin(TR).values
    _, atr, vz = featspec(g, "F2diract")
    atr_ref = float(np.nanmedian(atr[trs]))
    R = pd.read_csv(f"{REP}/spec_search_{SIG}.csv")
    masks = np.load(f"{REP}/spec_masks_{SIG}.npy")
    print("cells", len(R), "masks", masks.shape)

    # ret_all per execution variant, keyed exactly as the csv's `exec` column
    RET = {}
    for ex in R["exec"].unique():
        p = ex.split("/")
        if SIG == "B":
            RET[ex] = ret_all_simple(g, HOLD, 0)
        else:
            mode, life, anchor = p[0], int(p[1]), p[2]
            RET[ex] = (ret_all_simple(g, HOLD, 0) if mode == "none"
                       else ret_all_pullback(g, atr, atr_ref, HOLD, mode, life, anchor))

    # session x slot index matrix
    sess = g.sess.values; slot = g.slot.values
    us = pd.unique(pd.Series(sess)); si = {s: i for i, s in enumerate(us)}
    nsl = int(slot.max()) + 1
    IDX = np.full((len(us), nsl), -1, dtype=np.int64)
    for i in range(len(g)):
        IDX[si[sess[i]], slot[i]] = i
    srow = np.array([si[s] for s in sess]); scol = slot.astype(int)

    cells = [np.where(masks[i])[0].astype(np.int32) for i in range(len(R))]
    exarr = R["exec"].values
    rng = np.random.default_rng(101)
    maxt, maxm, maxgap = [], [], []
    for d in range(DRAWS):
        perm = rng.permutation(len(us))
        # placebo return for bar i = ret at (perm[session(i)], slot(i))
        PL = {}
        for ex, r in RET.items():
            j = IDX[perm[srow], scol]
            pl = np.where(j >= 0, r[np.maximum(j, 0)], np.nan)
            PL[ex] = pl
        bt, bm = -99., -99.
        for ci, idx in enumerate(cells):
            v = PL[exarr[ci]][idx]
            v = v[np.isfinite(v)]
            if len(v) < 25:
                continue
            t = tstat(v)
            if t > bt: bt = t
            if v.mean() > bm: bm = v.mean()
        maxt.append(bt); maxm.append(bm)
        if (d + 1) % 20 == 0:
            print(f"  draw {d+1}/{DRAWS}  running max-t 95pct="
                  f"{np.percentile(maxt, 95):.2f}")
    maxt = np.array(maxt); maxm = np.array(maxm)
    np.save(f"{REP}/charge_maxt_{SIG}.npy", maxt)
    PAPER = 5.83 if SIG=="A" else 5.15
    real_t = R["t"].max(); real_m = R["mean"].max()
    out = (f"SEARCH CHARGE — signal {SIG}\n"
           f"constructions searched: {len(R)}\n"
           f"placebo draws: {DRAWS} (session-permuted outcome, execution + time-of-day preserved)\n\n"
           f"BEST-OF-SEARCH under the null:  max t  mean {maxt.mean():.2f}  sd {maxt.std(ddof=1):.2f}  "
           f"median {np.median(maxt):.2f}  95th pct {np.percentile(maxt,95):.2f}  "
           f"max {maxt.max():.2f}\n"
           f"BEST-OF-SEARCH under the null:  max mean pt  median {np.median(maxm):.2f}  "
           f"95th pct {np.percentile(maxm,95):.2f}\n\n"
           f"OBSERVED best t in the real search: {real_t:.2f}\n"
           f"OBSERVED best mean in the real search: {real_m:.2f} pt\n"
           f"SEARCH-CHARGED p-value for the best cell: p = {(maxt >= real_t).mean():.3f}  "
           f"(fraction of placebo searches whose BEST cell beat it)\n\n"
           f"*** P(a PURE-NOISE search of this size yields a best cell with t >= the paper's "
           f"{PAPER}) = {(maxt >= PAPER).mean():.3f}\n"
           f"*** P(noise search best t >= 2.0, the paper's own bar) = {(maxt >= 2.0).mean():.3f}\n")
    print(out)
    open(f"{REP}/search_charge_{SIG}.txt", "w").write(out)


if __name__ == "__main__":
    raise SystemExit(main())
