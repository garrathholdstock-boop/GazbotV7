"""CHOP-SCALP step 6 — the one survivor's parameter plateau, and does the BOOK add anything?

CT13 = fade a NEW 30-MIN extreme on chop tape that arrived on a >=4pt 20-second thrust.
It is the only candidate whose frictionless median is positive. Everything here is the
robustness battery: plateau vs step, book ablation, IS/OOS, leave-one-day-out,
strip-the-best, placebo direction and label shuffle.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, SLIP_STOP_PT, load_events, IS_DAYS, OOS_DAYS, WEEK
from cs2_sweep import sequential

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))

def sel(L, spike, extra=None):
    m = CHOP & (d[f"f_ext{L}"] > 0) & (d.f_mv20 >= spike)
    return m if extra is None else (m & extra)

def evaluate(mask, tp, sp, days=None):
    sub = d[mask] if days is None else d[mask & d.date.isin(days)]
    if len(sub) == 0:
        return None
    parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in sub.groupby("date")]
    o = pd.concat(parts, ignore_index=True)
    return o if len(o) else None

def S(o):
    if o is None or len(o) == 0:
        return dict(n=0, net=0.0, ptr=0.0, win=0.0, days=0, open=0)
    return dict(n=len(o), net=round(float(o.usd.sum()), 2), ptr=round(float(o.usd.mean()), 3),
                win=round(float((o.usd > 0).mean()), 3), days=int(o.date.nunique()),
                open=int((o.kind == "OPEN").sum()))

TPS = [(t, s) for t in (3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0) for s in (4.0, 5.0, 6.0, 8.0, 10.0)]
res = {}

# ---------------- 1. parameter plateau over (L, spike, tp, sp)
print("=== 1. PARAMETER PLATEAU — CT13 family (L = extreme lookback, k = 20s thrust floor) ===")
rows = []
for L in (15, 20, 30):
    for k in (0.0, 2.0, 3.0, 4.0, 5.0, 6.0):
        m = sel(L, k)
        if m.sum() < 15:
            continue
        for tp, sp in TPS:
            o = evaluate(m, tp, sp)
            if o is None or len(o) < 15:
                continue
            s = S(o); s.update(L=L, k=k, tp=tp, sp=sp)
            rows.append(s)
P = pd.DataFrame(rows)
P.to_csv(f"{OUT}/ct13_plateau.csv", index=False)
print(f"cells={len(P)}  positive={int((P.ptr>0).sum())} ({(P.ptr>0).mean():.1%})")
print(P.groupby(["L", "k"]).agg(cells=("ptr", "size"), pos=("ptr", lambda s: int((s > 0).sum())),
                                med_ptr=("ptr", "median"), max_ptr=("ptr", "max"),
                                med_n=("n", "median")).round(3).to_string())
print("\ntop 12 cells:")
print(P.sort_values("ptr", ascending=False).head(12).to_string(index=False))
res["plateau"] = {"cells": len(P), "pos": int((P.ptr > 0).sum())}

# ---------------- 2. the BOOK ablation — the operator's actual question
print("\n=== 2. BOOK ABLATION on the CT13 base (L=30, k=4) — does L2 add anything? ===")
base = sel(30, 4.0)
BOOK = {
    "base (no book term)":            None,
    "+ wall1 >= 1.5 (absorption)":    d.f_wall1 >= 1.5,
    "+ wall5 >= 1.3":                 d.f_wall5 >= 1.3,
    "+ wall5 <= 1.0 (INVERSE)":       d.f_wall5 <= 1.0,
    "+ support draining (d20<0)":     d.f_supp_drain > 0,
    "+ wall building (d20>0)":        d.f_wall_build > 0,
    "+ 41ms refill above median":     d.f_refill >= d.f_refill[CHOP].median(),
    "+ 41ms pull above median":       d.f_pull >= d.f_pull[CHOP].median(),
    "+ aggressor delta >= 100":       d.f_agg20 >= 100,
    "+ aggressor frac >= 0.2":        d.f_aggfrac20 >= 0.2,
    "+ 10-deep imbalance > 0":        d.f_imb > 0,
    "+ vwap-flat <= 0.5 ATR":         d.f_vwap_flat <= 0.5,
}
ab = []
for lab, ex in BOOK.items():
    m = base if ex is None else (base & ex)
    best = None
    for tp, sp in TPS:
        o = evaluate(m, tp, sp)
        if o is None or len(o) < 12:
            continue
        s = S(o); s.update(tp=tp, sp=sp)
        if best is None or s["ptr"] > best["ptr"]:
            best = s
    # the honest number is the MEDIAN over the grid, not the max
    ptrs = []
    for tp, sp in TPS:
        o = evaluate(m, tp, sp)
        if o is not None and len(o) >= 12:
            ptrs.append(o.usd.mean())
    ab.append({"term": lab, "events": int(m.sum()),
               "med_ptr": round(float(np.median(ptrs)), 3) if ptrs else None,
               "pos_cells": int((np.array(ptrs) > 0).sum()) if ptrs else 0,
               "cells": len(ptrs),
               "best_ptr": best["ptr"] if best else None, "best_n": best["n"] if best else None,
               "best_tp": best["tp"] if best else None, "best_sp": best["sp"] if best else None})
A = pd.DataFrame(ab)
A.to_csv(f"{OUT}/ct13_book_ablation.csv", index=False)
print(A.to_string(index=False))
res["book_ablation"] = ab
json.dump(res, open(f"{OUT}/ct13.json", "w"), indent=1)
