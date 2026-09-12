"""CHOP-SCALP step 5b — is it a COST problem or a SIGN problem? And where did CT4 go?"""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, SLIP_STOP_PT, load_events
from cs2_sweep import F, CANDS, GRID, sequential

d = load_events()
chop = d.regime.isin(("CHOP", "DEAD_CHOP"))
print(f"[chop events] {chop.sum()} of {len(d)}")
print("\n=== how many events survive each filter (before any exit) ===")
for n in CANDS:
    m = F(d, n)
    print(f"  {n:22s} n={int(m.sum()):5d}   per day={m.sum()/d.date.nunique():6.1f}")

print("\n=== FRICTIONLESS vs COSTED — the sign test (fees and slip set to zero) ===")
rows = []
for name in ("CT0_NAIVE", "CT1_VWAPFLAT", "CT2_WALL", "CT2b_WALL5", "CT4_EXH_LITERAL",
             "CT5_STALL", "CT6_ANTIWALL", "CT7_SPIKE", "CT10_DEEPEXT", "CT13_DEEP_SPIKE", "AT0_ALLTAPE"):
    m = F(d, name)
    if m.sum() < 10:
        rows.append({"cand": name, "cells": 0, "note": f"only {int(m.sum())} events — no grid"}); continue
    fr = []; co = []
    for tp, sp in GRID:
        parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in d[m].groupby("date")]
        o = pd.concat(parts, ignore_index=True)
        if len(o) < 10:
            continue
        pts_c = np.where(o.kind == "STOP", -(sp + SLIP_STOP_PT), o[f"r_{tp}_{sp}"])
        pts_f = np.where(o.kind == "STOP", -sp, o[f"r_{tp}_{sp}"])
        co.append((pts_c * VPP - FEE).mean())
        fr.append((pts_f * VPP).mean())
    rows.append({"cand": name, "cells": len(co),
                 "med_costed": round(float(np.median(co)), 3), "pos_costed": int((np.array(co) > 0).sum()),
                 "med_frictionless": round(float(np.median(fr)), 3), "pos_frictionless": int((np.array(fr) > 0).sum()),
                 "max_frictionless": round(float(np.max(fr)), 3)})
print(pd.DataFrame(rows).to_string(index=False))
