#!/usr/bin/env python3
"""S11 — WHY THE POSITIVE CONTROL DID NOT FIRE. Is 'depth falls to 0.72x before a leg' an
ANTICIPATION or a CONSUMPTION?

S10 measured depth in the 5 minutes STRICTLY BEFORE a leg and got 0.98x (ns) where the desk's
prior result is 0.72x (t=-12.45). The brief itself names the suspect: an earlier study measured
book features in a +/-2 MINUTE WINDOW AROUND a pivot and 'could not separate "thin book let
price move" from "the move consumed the book"'.

So: run the identical feature, the identical legs and the identical matched control at a
sequence of window offsets that march across the event. If the ratio is ~1.0 before and dives
only once the window contains the move, the 0.72x is the move eating the book — it is a
DESCRIPTION of the leg, not a precursor of it, and nothing causal can be built on it.
"""
import duckdb, numpy as np, pandas as pd
GB = "/home/alphabot/gazbot7"; OUT = f"{GB}/reports/regime_2026-09-12/book"
W = "/tmp/claude-0/-root/7d23ea02-1a64-45f1-9faa-faa8101cea4d/scratchpad"
rng = np.random.default_rng(11)
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
m["touch"] = m.b0s_mean + m.a0s_mean
fw = m.mid_last.shift(-10) - m.mid_last
bw = m.mid_last - m.mid_last.shift(10)
cont = (m.m.diff(1) == 60) & (m.m.shift(-10) - m.m == 600) & (m.m - m.m.shift(10) == 600)
TH = 20
leg = (cont & (fw.abs() >= TH) & (bw.abs() < TH/2)).fillna(False)

rows = []
for f in ("depth", "touch"):
    # matched time-of-day control built on NON-leg minutes only
    cm = m.loc[cont & ~leg].groupby("slot")[f].mean()
    base = m.slot.map(cm)
    # windows marching across the event: (-5,-1) is strictly before, (0,+4) contains the move
    for a, b, name in [(-10, -6, "[-10,-6] before"), (-5, -1, "[-5,-1] STRICTLY BEFORE"),
                       (-2, 2, "[-2,+2] STRADDLING the event"), (0, 4, "[0,+4] DURING the move"),
                       (5, 9, "[+5,+9] after"), (10, 14, "[+10,+14] after")]:
        win = sum(m[f].shift(-k) for k in range(a, b+1)) / (b-a+1)
        ratio = (win / base)[leg]
        ok = ratio.notna() & np.isfinite(ratio)
        v = ratio[ok].values; ss = m.loc[ok[ok].index, "sess"].values
        lo, hi = boot(v, ss)
        rows.append(dict(feature=f, window=name, n=len(v), ratio=round(v.mean(), 4),
                         lo=round(lo, 3), hi=round(hi, 3), sig=bool(hi < 1 or lo > 1)))
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/s11_before_vs_during.csv", index=False)
txt = [f"S11 — the same legs (|10-min move| >= {TH}pt after a quiet 10 min, n={int(leg.sum())}, "
       f"{m.loc[leg,'sess'].nunique()} sessions), the same matched time-of-day control,",
       "the window marched across the event. Ratio < 1 = thinner than control.", "",
       R.to_string(index=False)]
txt = "\n".join(txt); open(f"{OUT}/s11_before_vs_during.txt", "w").write(txt+"\n"); print(txt)
