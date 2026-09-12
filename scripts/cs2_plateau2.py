"""CHOP-SCALP step 6b — the plateau re-run with the extreme definition held CONSTANT.

Separates the two things the first pass confounded: the LOOKBACK L, and whether the bar must
CLOSE at the extreme (f_extC) or merely WICK it (f_extH).
"""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, load_events
from cs2_sweep import sequential

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
EXITS = [(t, s) for t in (5.0, 6.0, 8.0, 10.0, 12.0) for s in (6.0, 8.0, 10.0)]

rows = []
for defn in ("H", "C"):
    for L in (10, 15, 20, 30):
        for k in (0.0, 3.0, 4.0, 5.0):
            m = CHOP & (d[f"f_ext{defn}{L}"] > 0) & (d.f_mv20 >= k)
            if m.sum() < 15:
                rows.append(dict(defn=defn, L=L, k=k, events=int(m.sum()), cells=0,
                                 pos=0, med_ptr=np.nan, max_ptr=np.nan, med_n=np.nan)); continue
            ptrs, ns = [], []
            for tp, sp in EXITS:
                parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in d[m].groupby("date")]
                o = pd.concat(parts, ignore_index=True)
                if len(o) < 12:
                    continue
                ptrs.append(o.usd.mean()); ns.append(len(o))
            if not ptrs:
                continue
            rows.append(dict(defn=defn, L=L, k=k, events=int(m.sum()), cells=len(ptrs),
                             pos=int((np.array(ptrs) > 0).sum()),
                             med_ptr=round(float(np.median(ptrs)), 3),
                             max_ptr=round(float(np.max(ptrs)), 3), med_n=int(np.median(ns))))
P = pd.DataFrame(rows)
P.to_csv(f"{OUT}/plateau2.csv", index=False)
print("defn H = the WICK touched the trailing L-min extreme;  defn C = the bar CLOSED at it")
print(P.to_string(index=False))
