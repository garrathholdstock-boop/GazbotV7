"""GF6 RULE 3 — the full exit matrix on every candidate entry, reported as a grid.

Four families, as the scope demands:
  (a) TIGHT-R SCALP     target_r 0.5 / 0.75 / 1.0 / 1.5 / 2.0 against a matched stop
  (b) WIDE CHANDELIER   arm 1/2/3 x ATR, trail 1/2/3 x ATR, wide enough to ride a gold grind
  (c) NAKED + CLOCK     no target, wide stop, flat at a hard time cap  (what the 08-14 work said
                        gold wants: board once, hold wide, flat at a clock)
  (d) DUAL SLOT         Lot A on the tightest profitable scalp + Lot B on the best chandelier,
                        which is the shape live MNQ actually runs
"""
from __future__ import annotations
import itertools, sys
import numpy as np, pandas as pd
import gf6_mgc_gate as G

OUT = "/home/alphabot/gazbot7/reports/friday_v7/gf6"

ENTRIES = {
    "revS_US_fadeup":  ("US",     "up", -1),
    "momL_LDN_goup":   ("LONDON", "up", +1),
    "momS_ASIA_godn":  ("ASIA",   "dn", -1),
    "revL_LDN_fadedn": ("LONDON", "dn", +1),
    "revL_US_fadedn":  ("US",     "dn", +1),
    "momS_US_godn":    ("US",     "dn", -1),
}

def grid(d, key):
    sess, trig, side = ENTRIES[key]
    rows = []
    for stop_k, tr in itertools.product((1.0, 2.0, 3.0), (0.5, 0.75, 1.0, 1.5, 2.0)):
        t = G.backtest(d, sess, trig, side, stop_k=stop_k, target_r=tr, cap=240)
        rows.append(dict(family="scalp", cfg=f"stop{stop_k}xATR targ{tr}R", **G.summarise(t)))
    for arm, trail in itertools.product((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)):
        t = G.backtest(d, sess, trig, side, stop_k=3.0, arm_k=arm, trail_k=trail, cap=480)
        rows.append(dict(family="chandelier", cfg=f"arm{arm} trail{trail} stop3xATR", **G.summarise(t)))
    for stop_k, cap in itertools.product((2.0, 3.0, 5.0), (60, 120, 240, 480)):
        t = G.backtest(d, sess, trig, side, stop_k=stop_k, cap=cap)
        rows.append(dict(family="naked+clock", cfg=f"stop{stop_k}xATR cap{cap}m", **G.summarise(t)))
    r = pd.DataFrame(rows)
    r["cand"] = key
    return r

if __name__ == "__main__":
    d = G.frame()
    keys = sys.argv[1:] or list(ENTRIES)
    allr = []
    for k in keys:
        r = grid(d, k); allr.append(r)
        pd.set_option("display.width", 250)
        print(f"\n########## {k} ##########")
        print(r[["family", "cfg", "n", "days", "net", "per", "med", "win", "held",
                 "strip_best3", "strip_day3"]].round(2).to_string(index=False))
    pd.concat(allr).to_csv(f"{OUT}/exitgrid.csv", index=False)
