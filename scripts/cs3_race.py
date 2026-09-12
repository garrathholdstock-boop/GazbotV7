"""On-the-fly first-touch race for target/stop pairs the event table never precomputed.

The cs2 event table baked races for tp in (2..12) x sp in (3..10). The operator asked for ~0.5R/1R
banking and the measured drift is ~1.3pt, so the interesting cells are TIGHTER than that grid. This
races them on the real tick tape with the identical convention:

  entry  = first tick at/after the 5s bar CLOSE, crossed 1 tick adverse   (already in E.entry)
  target = limit at entry -/+ tp        -> filled at tp, no extra slip
  stop   = stop-market at entry +/- sp  -> filled 1 tick BEYOND the trigger
  horizon 900s; a leg still open at the horizon is marked OPEN and carried at its mark, never predicted
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from gf_cs_lib import ticks
from cs2_common import VPP, FEE, SLIP_STOP_PT

HOR_S = 900
_TT = {}

def _tt(day):
    if day not in _TT:
        _TT[day] = ticks(day)
    return _TT[day]

def race_day(g, tp, sp):
    """g = event rows for ONE day, sorted by dts, carrying .entry and .side."""
    tt, pp = _tt(g.date.iloc[0])
    dts = g.dts.values.astype(float)
    fill = g.entry.values.astype(float)
    sh = (g.side.values == "SHORT")
    a = np.searchsorted(tt, dts, side="left")
    b = np.searchsorted(tt, dts + HOR_S, side="right")
    res = np.zeros(len(g)); dur = np.full(len(g), np.nan); kind = np.full(len(g), "OPEN", dtype=object)
    for k in range(len(g)):
        if not np.isfinite(fill[k]) or b[k] <= a[k]:
            kind[k] = "NOFILL"; continue
        seg = pp[a[k]:b[k]]
        if sh[k]:
            hit_t = seg <= fill[k] - tp; hit_s = seg >= fill[k] + sp
        else:
            hit_t = seg >= fill[k] + tp; hit_s = seg <= fill[k] - sp
        it = int(np.argmax(hit_t)) if hit_t.any() else -1
        is_ = int(np.argmax(hit_s)) if hit_s.any() else -1
        if it < 0 and is_ < 0:
            res[k] = (seg[-1] - fill[k]) * (-1 if sh[k] else 1); kind[k] = "OPEN"
            dur[k] = (tt[b[k] - 1] - tt[a[k]])
        elif is_ < 0 or (it >= 0 and it <= is_):
            res[k] = tp; kind[k] = "TARGET"; dur[k] = tt[a[k] + it] - tt[a[k]]
        else:
            res[k] = -sp; kind[k] = "STOP"; dur[k] = tt[a[k] + is_] - tt[a[k]]
    return res, kind, dur

def sequential_live(g, tp, sp):
    """One slot, no overlap, races computed live. Returns taken rows with $ P&L."""
    g = g.sort_values("dts")
    res, kind, dur = race_day(g, tp, sp)
    t = g.dts.values.astype(float)
    take = np.zeros(len(g), bool); free_at = -1e18
    for i in range(len(g)):
        if kind[i] == "NOFILL" or t[i] < free_at:
            continue
        take[i] = True
        free_at = t[i] + (dur[i] if np.isfinite(dur[i]) else float(HOR_S))
    o = g[take].copy()
    k = kind[take]; r = res[take]
    pts = np.where(k == "STOP", -(sp + SLIP_STOP_PT), r)
    o["usd"] = pts * VPP - FEE
    o["kind"] = k
    return o
