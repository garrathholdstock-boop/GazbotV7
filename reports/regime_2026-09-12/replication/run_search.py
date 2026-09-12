#!/usr/bin/env python3
"""Driver: exhaustive spec search for BOTH signals, with controls, search charge and a
prior-period holdout that took no part in any fit or any search."""
from __future__ import annotations
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/reports/regime_2026-09-12/replication")
from lib import load_1min, bars, fit_gmm, predict, tstat, splits, REP
from spec_search import (F, FEATS, KS, LABELS, SEEDS, featspec, make_map, to_R,
                         ret_all_simple, ret_all_pullback, holdout_1min)

SIG = sys.argv[1] if len(sys.argv) > 1 else "B"
if SIG == "B":
    LO, HI, BAR, HOLD = 180, 510, 15, 4
    TRANS = ["strict", "loose", "simple"]
    EXEC = [("simple", 0)]
else:
    LO, HI, BAR, HOLD = 570, 960, 5, 13
    TRANS = ["conf"]
    EXEC = [("none", 0, 0, "entry"),
            ("fix25", 3, 0, "entry"), ("fix25", 6, 0, "entry"),
            ("atr25", 3, 0, "entry"), ("atr25", 6, 0, "entry"),
            ("fix25", 3, 0, "signal"), ("atr25", 3, 0, "signal"),
            ("fix25", 6, 0, "signal"), ("atr25", 6, 0, "signal"),
            ("none", 0, 0, "signal")]


def markov_p12(R, win=200):
    n = len(R)
    f1 = (R[:-1] == 1).astype(float); t2 = ((R[:-1] == 1) & (R[1:] == 2)).astype(float)
    a = pd.Series(f1).rolling(win, min_periods=50).sum().values
    b = pd.Series(t2).rolling(win, min_periods=50).sum().values
    p = np.full(n, np.nan); p[1:] = np.where(a > 0, b / np.maximum(a, 1e-9), 0.0)
    return p


def masks_for(R, vz, rule):
    n = len(R)
    m = np.zeros(n, bool)
    if rule == "conf":
        p = markov_p12(R)
        m = (R == 1) & np.isfinite(p) & (p > .15) & np.isfinite(vz) & (vz > .5)
        return m
    R1 = np.roll(R, 1); R2 = np.roll(R, 2)
    base = (R == 2); base[:3] = False
    if rule == "strict":
        return base & (R1 == 0) & (R2 != 1)
    if rule == "loose":
        return base & ((R1 == 0) | (R2 == 0)) & (R1 != 1) & (R2 != 1)
    if rule == "simple":
        return base & (R1 != 2) & (R1 != 1) & (R2 != 1)
    raise ValueError(rule)


def main():
    df = load_1min(); g = bars(df, BAR, LO, HI).reset_index(drop=True)
    TR, VA, TE = splits(g.sess.values)
    trs = g.sess.isin(TR).values
    sess = g.sess.values
    codes, uniq = pd.factorize(pd.Series(sess))
    nsess = len(uniq)
    _, atr, vz = featspec(g, "F2diract")
    atr_ref = float(np.nanmedian(atr[trs]))

    # holdout tape (prior period, never fitted, never searched)
    hd = holdout_1min(); gh = bars(hd, BAR, LO, HI).reset_index(drop=True)
    _, atrh, vzh = featspec(gh, "F2diract")
    sessh = gh.sess.values

    # execution variants -> ret_all
    RET, RETH, tags = {}, {}, []
    if SIG == "B":
        for delay in (0, 1):
            RET[("simple", delay)] = ret_all_simple(g, HOLD, delay)
            RETH[("simple", delay)] = ret_all_simple(gh, HOLD, delay)
        tags = [("simple", 0)]
    else:
        for (mode, life, delay, anchor) in EXEC:
            key = (mode, life, anchor)
            RET[key] = (ret_all_simple(g, HOLD, 0) if mode == "none"
                        else ret_all_pullback(g, atr, atr_ref, HOLD, mode, life, anchor))
            RETH[key] = (ret_all_simple(gh, HOLD, 0) if mode == "none"
                         else ret_all_pullback(gh, atrh, atr_ref, HOLD, mode, life, anchor))
            tags.append(key)
        RET[("none", 0, "delay1")] = ret_all_simple(g, HOLD, 1)

    # per-session stats of each ret_all, for the closed-form same-entry control
    STATS = {}
    for k, r in RET.items():
        d = pd.DataFrame({"s": sess, "v": r}).dropna()
        gg = d.groupby("s").v.agg(["mean", "std", "size"])
        STATS[k] = {s: (row["mean"], row["std"] if np.isfinite(row["std"]) else 0.0, row["size"])
                    for s, row in gg.iterrows()}

    rows = []
    cell_masks = []
    print(f"signal {SIG}: enumerating {len(FEATS)}x{len(KS)}x{len(LABELS)}x{len(SEEDS)} "
          f"state configs x {len(TRANS)} trans x {len(tags)} exec")
    for feat in FEATS:
        X, _, _ = featspec(g, feat)
        Xh, _, _ = featspec(gh, feat)
        fin = np.isfinite(X).all(axis=1)
        actA, drA = np.log(np.maximum(g.high.values - g.low.values, .25) / atr), None
        r4 = np.zeros(len(g)); r4[4:] = g.close.values[4:] - g.close.values[:-4]
        drA = r4 / atr
        for K in KS:
            for seed in SEEDS:
                M = fit_gmm(X[trs & fin], K, seed=seed)
                st = predict(X, M); sth = predict(Xh, M)
                for lab in LABELS:
                    mp = make_map(g, actA, drA, st, trs, K, lab)
                    if mp is None:
                        continue
                    R = to_R(st, mp); Rh = to_R(sth, mp)
                    for tr_rule in TRANS:
                        m = masks_for(R, vz, tr_rule)
                        mh = masks_for(Rh, vzh, tr_rule)
                        for key in tags:
                            ret = RET[key]
                            mm = m & np.isfinite(ret)
                            n = int(mm.sum())
                            if n < 25:
                                continue
                            v = ret[mm]
                            mean = float(v.mean()); t = tstat(v)
                            sc = codes[mm]
                            gsum = pd.Series(v).groupby(sc).sum()
                            kk = len(gsum)
                            se_cl = (np.sqrt(((gsum.values - n * mean / kk) ** 2).sum()) / n
                                     if kk > 1 else np.nan)
                            t_cl = mean / se_cl if se_cl and se_cl > 0 else np.nan
                            # closed-form same-entry control
                            cnt = pd.Series(sess[mm]).value_counts().to_dict()
                            S = STATS[key]; num = 0.0; var = 0.0
                            for s_, k_ in cnt.items():
                                if s_ in S:
                                    num += k_ * S[s_][0]; var += k_ * (S[s_][1] ** 2)
                            cm = num / n; csd = np.sqrt(var) / n
                            gap = (mean - cm) / csd if csd > 0 else np.nan
                            per = {}
                            for pn, P in (("tr", TR), ("va", VA), ("te", TE)):
                                sel = mm & pd.Series(sess).isin(P).values
                                vv = ret[sel]
                                per[pn + "_n"] = int(sel.sum())
                                per[pn + "_m"] = float(vv.mean()) if sel.sum() >= 10 else np.nan
                                per[pn + "_t"] = tstat(vv) if sel.sum() >= 10 else np.nan
                            # holdout
                            reth = RETH[key]; mhh = mh & np.isfinite(reth)
                            hn = int(mhh.sum())
                            per["ho_n"] = hn
                            per["ho_m"] = float(reth[mhh].mean()) if hn >= 10 else np.nan
                            per["ho_t"] = tstat(reth[mhh]) if hn >= 10 else np.nan
                            rows.append(dict(feat=feat, K=K, seed=seed, lab=lab, tr=tr_rule,
                                             exec="/".join(map(str, key)), n=n, mean=mean,
                                             t=t, t_cl=t_cl, ctrl=cm, ctrl_sd=csd, gap=gap, **per))
                            cell_masks.append(mm)
    R2 = pd.DataFrame(rows)
    R2.to_csv(f"{REP}/spec_search_{SIG}.csv", index=False)
    np.save(f"{REP}/spec_masks_{SIG}.npy", np.array(cell_masks))
    print(f"cells: {len(R2)}")
    print(R2[["n", "mean", "t", "t_cl", "gap"]].describe().to_string())


if __name__ == "__main__":
    raise SystemExit(main())
