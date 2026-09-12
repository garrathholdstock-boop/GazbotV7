"""CHOP-SCALP step 4 — does the BOOK separate a turn that reverts from one that continues?

Model-free. No exits, no fees. For every candidate turn on CHOP-classified tape, race the tick
tape to a symmetric first-touch and ask each feature: does the top decile revert more than the
bottom decile? Reported as p(revert), lift, and a two-proportion z. This is the test the whole
section turns on — if the book is a null here, no exit grid can rescue it.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, load_events

d = load_events()
print(f"[events] {len(d)} on {d.date.nunique()} days   regime: {d.regime.value_counts().to_dict()}")
CHOP = d.regime.isin(["CHOP", "DEAD_CHOP"])
print(f"[chop-tape events] {CHOP.sum()}")

FEATS = [c for c in d.columns if c.startswith("f_")]
GRIDS = [(4.0, 4.0), (6.0, 6.0), (8.0, 8.0)]

def z2(p1, n1, p2, n2):
    if min(n1, n2) < 20:
        return float("nan")
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = (p * (1 - p) * (1 / n1 + 1 / n2)) ** 0.5
    return (p1 - p2) / se if se > 0 else float("nan")

rows = []
for tp, sp in GRIDS:
    k = d[f"k_{tp}_{sp}"]
    res = pd.DataFrame({"win": (k == "TARGET").astype(float), "res": k.isin(["TARGET", "STOP"])})
    for pop, mask in (("CHOP", CHOP), ("ALL", pd.Series(True, index=d.index))):
        m = mask & res.res
        base = res.win[m].mean(); nb = int(m.sum())
        rows.append({"grid": f"{tp}/{sp}", "popn": pop, "feat": "(base rate)", "n_hi": nb,
                     "p_hi": round(base, 4), "n_lo": nb, "p_lo": round(base, 4), "lift": 0.0, "z": 0.0})
        for f in FEATS:
            v = d[f][m]
            if v.notna().sum() < 100 or v.nunique() < 5:
                continue
            q_hi, q_lo = v.quantile(0.80), v.quantile(0.20)
            hi = m & (d[f] >= q_hi); lo = m & (d[f] <= q_lo)
            p1, n1 = res.win[hi].mean(), int(hi.sum())
            p0, n0 = res.win[lo].mean(), int(lo.sum())
            rows.append({"grid": f"{tp}/{sp}", "popn": pop, "feat": f, "n_hi": n1, "p_hi": round(p1, 4),
                         "n_lo": n0, "p_lo": round(p0, 4), "lift": round(p1 - base, 4),
                         "z": round(z2(p1, n1, p0, n0), 2)})
R = pd.DataFrame(rows)
R.to_csv(f"{OUT}/sep.csv", index=False)
for pop in ("CHOP", "ALL"):
    for g in ["4.0/4.0", "6.0/6.0", "8.0/8.0"]:
        s = R[(R.popn == pop) & (R.grid == g)].sort_values("z", ascending=False)
        print(f"\n=== {pop}  grid {g}  (base {s[s.feat=='(base rate)'].p_hi.iloc[0]:.3f}, n={s[s.feat=='(base rate)'].n_hi.iloc[0]}) ===")
        print(s[s.feat != "(base rate)"].head(8).to_string(index=False))
        print("  ... worst:")
        print(s[s.feat != "(base rate)"].tail(4).to_string(index=False))
