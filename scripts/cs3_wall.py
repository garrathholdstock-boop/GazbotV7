"""CHOP-SCALP 2026-08-29 — the operator's LEAD HYPOTHESIS, re-tested on fresh tape.

"At the price extreme require the FAR SIDE to be ABSORBING/DEPLETING."

The 2026-08-25 study reported that requiring an absorbing wall HURTS the fade, in two independent
tests. That was one window. This re-runs BOTH tests split ORIGINAL (07-31..08-24) vs NEW
(08-25..08-28) so the claim is a replication, not a single read.

Test A -- FRICTIONLESS DRIFT. No target, no stop, no fee: where is price 60s after the turn,
signed to the fade? This asks whether the SIGNAL has direction, independent of any exit choice.
Test B -- COSTED. The candidate's median $/trade across its whole 48-cell target/stop grid.

⚠ FEE $1.50/round trip, MNQ $2.00/pt.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, load_events
from cs2_sweep import sequential, GRID

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
ORIG = ["2026-07-31"] + [f"2026-08-{d:02d}" for d in (3,4,5,6,7,10,11,12,13,14,17,18,19,20,21,24)]
NEW  = ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))

# ---- Test A: frictionless 60s drift, signed to the fade -----------------------------
# r_2.0_10.0 etc are barrier races; for pure drift use the 15-min OPEN mark on the widest cell.
# Cleaner: recompute from the event's own forward race at a very wide symmetric band is not
# available, so use the widest recorded pair (12/10) and take only the OPEN rows -> biased.
# Instead: drift is measured from the raw tick tape.
from gf_cs_lib import ticks
def drift60(sub):
    out = []
    for day, g in sub.groupby("date"):
        tt, pp = ticks(day)
        for r in g.itertuples():
            i0 = np.searchsorted(tt, r.dts, side="left")
            i1 = np.searchsorted(tt, r.dts + 60, side="left")
            if i0 >= len(tt) or i1 >= len(tt) or i1 <= i0:
                continue
            mv = pp[i1] - pp[i0]
            out.append(-mv if r.side == "SHORT" else mv)   # + = the fade won
    return np.array(out)

TERMS = {
 "no book term (control)":       None,
 "wall1 >= 1.5  (ABSORBING)":    d.f_wall1 >= 1.5,
 "wall5 >= 1.3  (ABSORBING)":    d.f_wall5 >= 1.3,
 "wall5 <= 1.0  (INVERSE: thin)": d.f_wall5 <= 1.0,
 "support draining 20s":         d.f_supp_drain > 0,
 "wall building 20s":            d.f_wall_build > 0,
 "41ms refill >= median":        d.f_refill >= d.f_refill[CHOP].median(),
 "41ms pull >= median":          d.f_pull >= d.f_pull[CHOP].median(),
 "10-deep imbalance > 0":        d.f_imb > 0,
}

print("=== TEST A — FRICTIONLESS 60s DRIFT on chop tape, signed to the fade (pt) ===")
print(f"{'book term':32s} {'window':6s} {'n':>6s} {'mean_pt':>9s} {'t':>7s} {'median':>8s}")
print("-" * 74)
resA = {}
for lab, ex in TERMS.items():
    m = CHOP if ex is None else (CHOP & ex)
    row = {}
    for tag, days in (("ORIG", ORIG), ("NEW", NEW)):
        x = drift60(d[m & d.date.isin(days)])
        if len(x) < 20:
            print(f"{lab:32s} {tag:6s} {len(x):>6d}   (n too small)"); row[tag] = None; continue
        t = float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
        row[tag] = dict(n=len(x), mean=round(float(x.mean()), 4), t=round(t, 3),
                        med=round(float(np.median(x)), 3))
        print(f"{lab:32s} {tag:6s} {len(x):>6d} {x.mean():>9.4f} {t:>7.2f} {np.median(x):>8.3f}")
    resA[lab] = row

# ---- Test B: costed, median over the whole grid ------------------------------------
print("\n=== TEST B — COSTED median $/trade over the 48-cell grid ===")
print(f"{'book term':32s} {'window':6s} {'events':>7s} {'med$/tr':>9s} {'pos cells':>10s} {'best$':>8s}")
print("-" * 78)
resB = {}
for lab, ex in TERMS.items():
    m = CHOP if ex is None else (CHOP & ex)
    row = {}
    for tag, days in (("ORIG", ORIG), ("NEW", NEW)):
        mm = m & d.date.isin(days)
        if mm.sum() < 15:
            row[tag] = None; print(f"{lab:32s} {tag:6s} {int(mm.sum()):>7d}   (too few events)"); continue
        ptrs = []
        for tp, sp in GRID:
            sub = d[mm]
            parts = [sequential(g.sort_values("dts"), tp, sp) for _, g in sub.groupby("date")]
            o = pd.concat(parts, ignore_index=True)
            if len(o) >= 10:
                ptrs.append(float(o.usd.mean()))
        if not ptrs:
            row[tag] = None; continue
        row[tag] = dict(events=int(mm.sum()), med=round(float(np.median(ptrs)), 3),
                        pos=int((np.array(ptrs) > 0).sum()), cells=len(ptrs),
                        best=round(float(max(ptrs)), 3))
        print(f"{lab:32s} {tag:6s} {int(mm.sum()):>7d} {np.median(ptrs):>9.3f} "
              f"{int((np.array(ptrs)>0).sum()):>4d}/{len(ptrs):<5d} {max(ptrs):>8.3f}")
    resB[lab] = row

json.dump({"drift60": resA, "costed": resB}, open(f"{OUT3}/wall.json", "w"), indent=1)
print(f"\n[wrote] {OUT3}/wall.json")
