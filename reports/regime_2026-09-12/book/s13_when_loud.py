#!/usr/bin/env python3
"""S13 — THE LAST PLACE DIRECTION COULD HIDE.

S12 proved the book DOES say 'when': depth falls to 0.767x its matched control before the
largest legs, monotone in leg size. S06 proved it says nothing about 'which way' on average.
The remaining question is CONDITIONAL: at the moments when the book is loudly signalling
'when' — when depth has genuinely withdrawn — does its ASYMMETRY then pick the side?

If direction exists anywhere in this data, it is here. n ~ 14,000 minutes per tercile, so this
is a well-powered test, not a 68-event island.

CAUSAL: the withdrawal state and the asymmetry are both measured over minute m; the target is
the move from the END of minute m forward.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
W = "/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad"
rng = np.random.default_rng(13)
con = duckdb.connect(config={"temp_directory": f"{GB}/data/duckdb_tmp", "memory_limit": "800MB"})
def boot(v, s, n=4000):
    ss, inv = np.unique(s, return_inverse=True)
    S = np.bincount(inv, weights=v, minlength=len(ss)); N = np.bincount(inv, minlength=len(ss)).astype(float)
    p = rng.integers(0, len(ss), size=(n, len(ss)))
    return np.percentile(S[p].sum(1)/N[p].sum(1), [2.5, 97.5])
m = con.execute(f"""select b.m, b.mid_last, b.db3_mean, b.da3_mean, b.b0s_mean, b.a0s_mean,
       b.db3_last, b.da3_last, b.ofi_sum, t.buyv, t.sellv
       from read_parquet('{W}/bookfeat/*.parquet') b
       left join read_parquet('{W}/tickfeat/*.parquet') t on b.m=t.m order by b.m""").df()
m["slot"] = ((m.m % 86400)//900).astype(int)
m["sess"] = pd.to_datetime(m.m+7200, unit="s", utc=True).dt.date
m["depth"] = m.db3_mean + m.da3_mean
eps = 1e-9
m["imb3"]   = (m.db3_mean - m.da3_mean)/(m.db3_mean + m.da3_mean + eps)
m["imb3_L"] = (m.db3_last - m.da3_last)/(m.db3_last + m.da3_last + eps)
m["imbT"]   = (m.b0s_mean - m.a0s_mean)/(m.b0s_mean + m.a0s_mean + eps)
m["ofi_n"]  = m.ofi_sum/(m.depth + eps)
m["tsi"]    = (m.buyv - m.sellv)/(m.buyv + m.sellv + eps)
# withdrawal state = depth relative to its own time-of-day control (leave-one-out by construction
# is unnecessary here: the control is a 44k-minute slot mean, one minute cannot move it)
m["wd"] = m.depth / m.slot.map(m.groupby("slot")["depth"].mean())
q = m.wd.quantile([1/3, 2/3]).values
m["terc"] = np.where(m.wd <= q[0], "1 THIN (withdrawn)",
             np.where(m.wd <= q[1], "2 normal", "3 THICK"))
for k in (5, 15, 60):
    f = m.mid_last.shift(-k) - m.mid_last
    m[f"f{k}"] = f.where((m.m.shift(-k) - m.m) == 60*k)
rows = []
for feat in ["imb3", "imb3_L", "imbT", "ofi_n", "tsi"]:
    for k in (5, 15, 60):
        for terc in ["1 THIN (withdrawn)", "2 normal", "3 THICK"]:
            s = m[(m.terc == terc)][[feat, f"f{k}", "sess"]].dropna()
            if len(s) < 200: continue
            x, y = s[feat].values, s[f"f{k}"].values
            r = np.corrcoef(x, y)[0, 1]
            t = r*np.sqrt((len(x)-2)/max(1-r*r, 1e-12))
            nz = (x != 0) & (y != 0)
            hit = (np.sign(x[nz]) == np.sign(y[nz])).mean()
            hv = (np.sign(x[nz]) == np.sign(y[nz])).astype(float)
            lo, hi = boot(hv, s.sess.values[nz])
            rows.append(dict(feature=feat, horizon=f"+{k}min", depth_tercile=terc, n=len(x),
                             r=round(r, 4), t_per_obs=round(t, 2), hit=round(hit, 4),
                             hit_lo=round(lo, 4), hit_hi=round(hi, 4),
                             dayblock_sig=bool(lo > .5 or hi < .5)))
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/s13_when_loud.csv", index=False)
sig = R[R.dayblock_sig]
txt = ["S13 — directional hit rate of each book feature, SPLIT BY whether the book has withdrawn.",
       f"depth terciles of wd = depth / its time-of-day mean: cuts at {q[0]:.3f} and {q[1]:.3f}",
       "", R.to_string(index=False), "",
       f"cells whose day-block 95% CI on the hit rate EXCLUDES 0.500: {len(sig)} of {len(R)}",
       (sig.to_string(index=False) if len(sig) else "  (none)"),
       "", f"hit rate range across all {len(R)} cells: {R.hit.min():.4f} .. {R.hit.max():.4f}"]
txt = "\n".join(txt); open(f"{OUT}/s13_when_loud.txt", "w").write(txt+"\n"); print(txt)
