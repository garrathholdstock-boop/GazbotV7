#!/usr/bin/env python3
"""What do the states ACTUALLY separate on? (brief task 4)

For each fitted model: per-state TRAIN means of every candidate feature (not only the ones the
model was given), plus an F-ratio = between-state variance / within-state variance on TRAIN.
A feature with F near 1 is carried but does no work - the desk's 'config field read by nothing'.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

ALL_F = ["d2", "d4", "d8", "d12", "d16", "er2", "er4", "er8", "er12", "er16", "vr", "vz", "sp"]
out = []
for bar in (5, 15):
    g = R.load_bars(bar)
    for K in (3, 4, 5):
        for fs in ("base", "full"):
            M = R.Model(bar, K, fs, g=g)
            trm = g.sess.isin(M.TR).values
            for f in ALL_F:
                v = M.feat[f]
                ok = trm & np.isfinite(v)
                gm = v[ok].mean(); tot = v[ok].var()
                bw, wi, rowmeans = 0.0, 0.0, {}
                for k in range(K):
                    m = ok & (M.state == k)
                    if m.sum() < 20:
                        continue
                    rowmeans[M.name[k]] = rowmeans.get(M.name[k], []) + [v[m].mean()]
                    bw += m.sum() * (v[m].mean() - gm) ** 2
                    wi += m.sum() * v[m].var()
                out.append(dict(bar=bar, K=K, fset=fs, feature=f,
                                used=f in R.FEATURE_SETS[fs],
                                F=round(float(bw / max(wi, 1e-9) * (ok.sum() - K) / (K - 1)), 1),
                                spread_sd=round(float(np.sqrt(bw / ok.sum()) /
                                                      max(np.sqrt(tot), 1e-9)), 3),
                                **{k: round(float(np.mean(v2)), 3) for k, v2 in rowmeans.items()}))
        del_ = None
    del g
D = pd.DataFrame(out)
D.to_csv(f"{R.ART}/tables/feature_separation.csv", index=False)
for (bar, K, fs), s in D.groupby(["bar", "K", "fset"]):
    print(f"\n--- {bar}-min, {K} states, feature set '{fs}'  "
          f"(F = between/within on TRAIN; 'used' = given to the GMM)")
    print(s.drop(columns=["bar", "K", "fset"]).sort_values("F", ascending=False)
           .to_string(index=False))
