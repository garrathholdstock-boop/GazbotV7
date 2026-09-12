"""GF6 — the London PM fix natural experiment.

The clock sweep put its only split-half-stable short at 14:00-14:30 UTC. The LBMA PM gold fix is
15:00 LONDON time, which is 14:00 UTC while Britain is on BST and 15:00 UTC while it is on GMT. So
if what I have found is the fix, the effect must MOVE BY AN HOUR when London's clocks change, and
that is a test no amount of curve-fitting can fake: the boundary is set by an act of parliament, not
by anything in the price.

  BST in this sample: 2025-10-01 .. 2025-10-25  and  2026-03-29 .. 2026-09-04
  GMT in this sample: 2025-10-26 .. 2026-03-28
"""
from __future__ import annotations
import numpy as np, pandas as pd
import gf6_mgc_gate as G
from gf6_mgc_verdict import _walk

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"
BST = [("2025-10-01", "2025-10-25"), ("2026-03-29", "2026-09-04")]

def is_bst(sday):
    return any(a <= sday <= b for a, b in BST)

def series(d, hhmm, side, stop_k, cap):
    v, dd = [], []
    for sd, g in d.groupby("sday"):
        g = g.reset_index(drop=True)
        k = g.index[g.hhmm == hhmm]
        if not len(k): continue
        r = _walk(g, [int(k[0])], side, stop_k, cap)
        if r: v.append(r[0]); dd.append(sd)
    return pd.Series(v, index=dd)

def stat(s):
    if len(s) < 20: return dict(n=len(s), per=np.nan, strip3=np.nan, win=np.nan)
    o = s.sort_values(ascending=False).index
    return dict(n=len(s), per=float(s.mean()), med=float(s.median()),
                win=float((s > 0).mean()), strip3=float(s[~s.index.isin(o[:3])].mean()))

if __name__ == "__main__":
    d = G.frame()
    rows = []
    for hhmm in (13*60, 13*60+30, 14*60, 14*60+30, 15*60, 15*60+30, 16*60):
        for side, sn in ((-1, "SHORT"), (+1, "LONG")):
            s = series(d, hhmm, side, 7.0, 480)
            bst = s[[is_bst(x) for x in s.index]]
            gmt = s[[not is_bst(x) for x in s.index]]
            rows.append(dict(t=f"{hhmm//60:02d}:{hhmm%60:02d}", side=sn,
                             **{f"all_{k}": v for k, v in stat(s).items()},
                             **{f"BST_{k}": v for k, v in stat(bst).items()},
                             **{f"GMT_{k}": v for k, v in stat(gmt).items()}))
    r = pd.DataFrame(rows)
    r.to_csv(f"{OUT}/fix_dst.csv", index=False)
    pd.set_option("display.width", 260)
    for sn in ("SHORT", "LONG"):
        print(f"\n===== {sn} one lot at a fixed UTC time, 7xATR stop, 8h cap =====")
        g = r[r.side == sn]
        print(g[["t", "all_n", "all_per", "all_strip3", "BST_n", "BST_per", "BST_strip3",
                 "GMT_n", "GMT_per", "GMT_strip3"]].round(2).to_string(index=False))
    print("\nfix hypothesis: SHORT should be strongest at 14:00 UTC on BST days and at 15:00 UTC on GMT days")
