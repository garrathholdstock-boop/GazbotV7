#!/usr/bin/env python3
"""S06 — THE INSTRUMENT CHECK, run BEFORE any null is allowed to be reported.

[an instrument that reports healthy about what it never checks] is this desk's #1 failure mode.
If I am going to say "OFI carries no direction at 60 minutes", I must first show that my OFI
is a WORKING OFI — i.e. that it reproduces the one thing Cont/Kukanov/Stoikov actually claim:
contemporaneous and very-short-horizon price impact. If it fails here, my null means nothing
about the market and everything about my code.

n is ~44,000 minutes, so this probe has ~4x the power of the 15-min tests and ~11x the power
of the transition test. It is also the HORIZON-DECAY measurement: the same statistic at
1 / 5 / 15 / 60 minutes.

CAUSAL THROUGHOUT: OFI over minute m predicts mid at (m+60+k*60) minus mid at (m+60).
Minute m ends at m+60; nothing from after m is in the feature.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
W = "/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad"
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})
d = con.execute(f"""
 select b.m, b.ofi_sum, b.mid_last, b.db3_mean, b.da3_mean, b.b0s_mean, b.a0s_mean,
        b.db3_last, b.da3_last, b.n_ofi, t.buyv, t.sellv
 from read_parquet('{W}/bookfeat/*.parquet') b
 left join read_parquet('{W}/tickfeat/*.parquet') t on b.m=t.m
 order by b.m""").df()
d["sess"] = pd.to_datetime(d.m + 7200, unit="s", utc=True).dt.date   # 22:00Z session boundary
eps = 1e-9
d["ofi_n"]  = d.ofi_sum / (d.db3_mean + d.da3_mean + eps)
d["imb3_L"] = (d.db3_last - d.da3_last) / (d.db3_last + d.da3_last + eps)
d["imbT"]   = (d.b0s_mean - d.a0s_mean) / (d.b0s_mean + d.a0s_mean + eps)
d["tsi"]    = (d.buyv - d.sellv) / (d.buyv + d.sellv + eps)

# contemporaneous move of minute m itself (the CKS regression target — NOT a forecast)
d["dmid_same"] = d.mid_last - d.mid_last.shift(1)
gap = d.m.diff() != 60
d.loc[gap, "dmid_same"] = np.nan
for k in (1, 5, 15, 60):
    fwd = d.mid_last.shift(-k) - d.mid_last
    ok = (d.m.shift(-k) - d.m) == 60*k
    d[f"f{k}"] = fwd.where(ok)

rows = []
for feat in ["ofi_n", "imb3_L", "imbT", "tsi"]:
    for tgt, lbl in [("dmid_same", "SAME minute (contemporaneous)"),
                     ("f1", "+1 min"), ("f5", "+5 min"), ("f15", "+15 min"), ("f60", "+60 min")]:
        s = d[[feat, tgt, "sess"]].dropna()
        if len(s) < 100: continue
        x, y = s[feat].values, s[tgt].values
        r = np.corrcoef(x, y)[0, 1]
        t = r*np.sqrt((len(x)-2)/max(1-r*r, 1e-12))
        hit = ((np.sign(x) == np.sign(y)) & (x != 0) & (y != 0)).sum() / max(((x != 0) & (y != 0)).sum(), 1)
        rows.append(dict(feature=feat, target=lbl, n=len(x), r=round(r, 4), t=round(t, 2),
                         hit=round(hit, 4)))
R = pd.DataFrame(rows)
R.to_csv(f"{OUT}/s06_ofi_anchor.csv", index=False)
txt = ["S06 INSTRUMENT CHECK — per-MINUTE, n~44k. Does my book carry direction AT ALL, and over",
       "what horizon? 'SAME minute' is the Cont/Kukanov/Stoikov contemporaneous regression and is",
       "NOT tradeable — it is the proof that the feature is correctly constructed.", "",
       R.to_string(index=False)]
txt = "\n".join(txt); open(f"{OUT}/s06_ofi_anchor.txt", "w").write(txt+"\n"); print(txt)
