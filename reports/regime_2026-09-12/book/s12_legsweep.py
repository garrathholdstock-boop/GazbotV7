#!/usr/bin/env python3
"""S12 — how selective must a 'leg' be before the book thins? And how much of the prior
t=-12.45 is a per-observation standard error on 31 correlated sessions?

Reports BOTH: the naive per-observation t (what a study gets if it treats 4,000 minutes from
31 days as 4,000 independent draws) and the day-block bootstrap CI (what those 31 days can
actually support). If they disagree by ~an order of magnitude, that IS the explanation.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
W = "/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad"
rng = np.random.default_rng(12)
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})
def boot(v, s, n=4000):
    ss, inv = np.unique(s, return_inverse=True)
    S = np.bincount(inv, weights=v, minlength=len(ss)); N = np.bincount(inv, minlength=len(ss)).astype(float)
    p = rng.integers(0, len(ss), size=(n, len(ss)))
    return np.percentile(S[p].sum(1)/N[p].sum(1), [2.5, 97.5])
m = con.execute(f"""select m, mid_last, db3_mean, da3_mean, b0s_mean, a0s_mean
                    from read_parquet('{W}/bookfeat/*.parquet') order by m""").df()
m["slot"] = ((m.m % 86400)//900).astype(int)
m["sess"] = pd.to_datetime(m.m+7200, unit="s", utc=True).dt.date
m["depth"] = m.db3_mean + m.da3_mean
fw = m.mid_last.shift(-10) - m.mid_last; bw = m.mid_last - m.mid_last.shift(10)
cont = (m.m.diff(1) == 60) & (m.m.shift(-10) - m.m == 600) & (m.m - m.m.shift(10) == 600)
rows = []
for TH in (10, 20, 30, 40, 60, 80, 120):
    leg = (cont & (fw.abs() >= TH) & (bw.abs() < TH/2)).fillna(False)
    if leg.sum() < 40: continue
    for ctl_name in ("time-of-day matched", "SESSION matched (day mean)", "GLOBAL mean (wrong)"):
        if ctl_name.startswith("time"):
            base = m.slot.map(m.loc[cont & ~leg].groupby("slot")["depth"].mean())
        elif ctl_name.startswith("SESSION"):
            base = m.sess.map(m.loc[cont & ~leg].groupby("sess")["depth"].mean())
        else:
            base = pd.Series(m.loc[cont & ~leg, "depth"].mean(), index=m.index)
        pre = m.depth.rolling(5).mean().shift(1)
        ratio = (pre/base)[leg]
        ok = ratio.notna() & np.isfinite(ratio)
        v = ratio[ok].values; ss = m.loc[ok[ok].index, "sess"].values
        t_naive = (v.mean()-1)/(v.std(ddof=1)/np.sqrt(len(v)))
        lo, hi = boot(v, ss)
        rows.append(dict(leg_thresh_pt=TH, n_legs=len(v), control=ctl_name,
                         pre_depth_ratio=round(v.mean(), 4), t_per_observation=round(t_naive, 2),
                         dayblock_lo=round(lo, 3), dayblock_hi=round(hi, 3),
                         dayblock_sig=bool(hi < 1 or lo > 1)))
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/s12_legsweep.csv", index=False)
txt = ["S12 — PRE-leg 3-level depth vs three different controls, across leg selectivity.",
       "The prior desk number to reproduce is 0.72x at t=-12.45.", "", R.to_string(index=False)]
txt = "\n".join(txt); open(f"{OUT}/s12_legsweep.txt", "w").write(txt+"\n"); print(txt)
