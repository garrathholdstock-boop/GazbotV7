#!/usr/bin/env python3
"""S09 — THE 'WHEN' TEST, which is also the POSITIVE CONTROL for everything above.

A directional null is only worth reading if the pipeline that produced it can detect a book
effect that is known to exist. This desk has already measured one: at the start of directional
legs, 3-level depth falls to 0.72x its matched control and touch size to 0.79x. If MY features,
MY hygiene and MY matched controls recover that shape at regime transitions, then the same
pipeline reporting ~0.50 on direction is reporting a property of the market, not a dead feature.

MATCHED CONTROL: every transition window is compared against the SAME 15-minute-of-day slot in
the OTHER sessions (leave-one-out), never a day median — depth is 38 overnight and 76 at 18:00Z,
so a day median would compare an afternoon transition against its own overnight.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
rng = np.random.default_rng(7)
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})
d = con.execute(f"select * from read_parquet('{OUT}/s05_decision_features.parquet')").df()
tr = pd.read_csv(f"{OUT}/s02_transitions_bookwindow.csv")
d = d.merge(tr[["bt", "side", "clean"]], on="bt", how="left")
d["is_tr"] = d.side.notna()

def boot(v, s, n=4000):
    ss, inv = np.unique(s, return_inverse=True)
    S = np.bincount(inv, weights=v, minlength=len(ss)); N = np.bincount(inv, minlength=len(ss)).astype(float)
    p = rng.integers(0, len(ss), size=(n, len(ss)))
    return np.percentile(S[p].sum(1)/N[p].sum(1), [2.5, 97.5])

LEVEL = ["depth", "b0s", "a0s", "spread", "qint", "depth_tr", "trade_sz", "vol"]
d["b0s"] = d.b0s; d["a0s"] = d.a0s; d["spread"] = d.spd
rows = []
for f in LEVEL:
    if f not in d: continue
    z = f + "_ztod"
    if z not in d:   # build the leave-one-out time-of-day control for the extras
        gg = d.groupby("slot")[f]
        n_, tot, sq = gg.transform("count"), gg.transform("sum"), gg.transform(lambda x: (x**2).sum())
        m = (tot-d[f])/(n_-1); v = (sq-d[f]**2)/(n_-1) - m**2
        d[z] = (d[f]-m)/(np.sqrt(v.clip(lower=0))+1e-9)
        d[f+"_ratio"] = d[f]/m
    else:
        gg = d.groupby("slot")[f]
        n_, tot = gg.transform("count"), gg.transform("sum")
        d[f+"_ratio"] = d[f]/((tot-d[f])/(n_-1))
    for scope, mask in (("transition", d.is_tr), ("clean transition", d.is_tr & (d.clean == True))):
        s = d[mask & d[z].notna()]
        c = d[~d.is_tr & d[z].notna()]
        if len(s) < 50: continue
        lo, hi = boot(s[z].values, s.sess.values)
        rows.append(dict(feature=f, scope=scope, n=len(s),
                         tr_mean=round(s[f].mean(), 3), ctl_mean=round(c[f].mean(), 3),
                         ratio_to_matched_control=round(s[f+"_ratio"].mean(), 4),
                         z_vs_matched=round(s[z].mean(), 4),
                         z_lo=round(lo, 3), z_hi=round(hi, 3),
                         sig=bool(lo > 0 or hi < 0)))
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/s09_when.csv", index=False)
txt = ["S09 — book state in the 15 minutes BEFORE a regime transition, vs the SAME 15-min-of-day",
       "slot in the OTHER sessions (leave-one-out). z is in control-sd units; CI is day-block.",
       "POSITIVE CONTROL: the desk's prior finding is depth ~0.72x and touch ~0.79x at the start",
       "of directional legs. If this pipeline cannot see that, its directional null is worthless.",
       "", R.to_string(index=False)]
txt = "\n".join(txt); open(f"{OUT}/s09_when.txt", "w").write(txt+"\n"); print(txt)
