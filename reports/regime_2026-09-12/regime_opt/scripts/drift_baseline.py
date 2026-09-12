#!/usr/bin/env python3
"""HOW MUCH DOES THIS LAKE PAY A LONG FOR DOING NOTHING?

A sibling agent measured +11.25 pt/trade (sd 4.66) for a 60-minute random-time LONDON long on
this lake. GO FIND THE PRICE YOURSELF: re-measured here on the same front-month tape this study
uses, every bar in the window, day-block CI, 1.25pt friction.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import regimelab as R, numpy as np, pandas as pd

WINDOWS = {"ALL": None, "LDN": (480, 810), "RTH": (810, 1200),
           "OPEN": (810, 960), "EUUS": (480, 1200)}
g = R.load_bars(15)
cl, op, sess, mod = g.close.values, g.open.values, g.sess.values, g["mod"].values
rows = []
for wn, w in WINDOWS.items():
    for hm in (30, 60, 90, 120, 180):
        h = hm // 15
        i = np.arange(1, len(g) - h - 1)
        ok = sess[i] == sess[i + h]
        if w:
            ok &= (mod[i] >= w[0]) & (mod[i] < w[1])
        i = i[ok]
        if len(i) < 100:
            continue
        pnl = (cl[i + h] - op[i + 1]) - 1.25
        T = pd.DataFrame({"sess": sess[i], "gross": cl[i + h] - op[i + 1], "pt": pnl,
                          "side": 1, "i": i})
        lo, mid, hi = R.day_block_boot(T, friction=1.25, draws=3000)
        rows.append(dict(window=wn, hold_min=hm, n=len(i), always_long=mid,
                         lo=lo, hi=hi, sd_per_trade=pnl.std(ddof=1),
                         day_sd=(hi - lo) / 3.92))
D = pd.DataFrame(rows)
D.to_csv(f"{R.ART}/tables/drift_baseline.csv", index=False)
print("ALWAYS-LONG AT EVERY BAR IN THE WINDOW · 1.25pt friction · day-block 95% CI")
print(D.round(2).to_string(index=False))
print(f"\ntape: MNQ {cl[0]:.0f} -> {cl[-1]:.0f} over {len(set(sess))} sessions "
      f"({100*(cl[-1]/cl[0]-1):.0f}%)")
print("per-session mean drift:", round(float((cl[-1]-cl[0])/len(set(sess))), 2), "pt")
