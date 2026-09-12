"""CHOP-SCALP 2026-08-29 — HARNESS VALIDATION. A backtester that can only print losses is not
evidence of anything, so before the verdict stands the machinery has to be shown to work.

Three controls, all through the IDENTICAL race / cost model / one-slot sequencing:

  ORACLE      side chosen by the SIGN of the realised 60s move. Look-ahead by construction; it MUST
              come back large and positive. If it does not, the fee model or the race is broken.
              (A backward/oracle shift is a leak-check that must WIN -- only forward shifts are placebos.)
  ANTI-ORACLE the same, sign flipped. Must come back large and NEGATIVE, symmetrically.
  TREND-CONT  a real, non-look-ahead rule on its home tape: on TREND-daytype days, trade WITH a
              60s thrust through a 10-min extreme. This is the honest positive control.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, VPP, FEE, load_events
from cs3_race import sequential_live
from gf_cs_lib import ticks

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
d = load_events()
days_meta = pd.read_csv(f"{OUT}/regime_days.csv")
TREND_DAYS = sorted(set(days_meta[days_meta.daytype == "TREND"].date) & set(d.date))
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
print(f"[trend daytype days] {len(TREND_DAYS)}  {TREND_DAYS}")

# realised 60s move (raw, unsigned) for every event
mv = np.full(len(d), np.nan)
for day, g in d.groupby("date"):
    tt, pp = ticks(day)
    i0 = np.searchsorted(tt, g.dts.values, side="left")
    i1 = np.searchsorted(tt, g.dts.values + 60, side="left")
    ok = (i0 < len(tt)) & (i1 < len(tt)) & (i1 > i0)
    mv[g.index.values] = np.where(ok, pp[np.clip(i1, 0, len(pp)-1)] - pp[np.clip(i0, 0, len(pp)-1)], np.nan)
d["fwd60"] = mv

def run(frame, mask, tp, sp):
    sub = frame[mask]
    if not len(sub): return None
    return pd.concat([sequential_live(g, tp, sp) for _, g in sub.groupby("date")], ignore_index=True)

def S(o, lab):
    if o is None or not len(o): return None
    return dict(label=lab, n=len(o), net=round(float(o.usd.sum()), 2),
                ptr=round(float(o.usd.mean()), 3), win=round(float((o.usd > 0).mean()), 3))

res = {}
print(f"\n{'control':44s} {'tp/sp':>9s} {'n':>5s} {'net':>10s} {'$/tr':>8s} {'win':>6s}")
print("-" * 88)

# ---- ORACLE / ANTI-ORACLE on chop tape ---------------------------------------------
for lab, flip in (("ORACLE  side = sign of realised 60s move", False),
                  ("ANTI-ORACLE  the same, sign flipped", True)):
    o1 = d.copy()
    want_long = (o1.fwd60 > 0) if not flip else (o1.fwd60 < 0)
    newside = np.where(want_long, "LONG", "SHORT")
    # re-cross the spread for whichever side we now take, off the raw print
    raw = d.entry.values + np.where(d.side.values == "SHORT", 0.25, -0.25)
    o1["entry"] = raw + np.where(newside == "LONG", 0.25, -0.25)
    o1["side"] = newside
    m = CHOP & np.isfinite(o1.fwd60)
    for tp, sp in ((5.0, 5.0),):
        s = S(run(o1, m, tp, sp), lab)
        if s: print(f"{lab:44s} {f'{tp}/{sp}':>9s} {s['n']:>5d} {s['net']:>10,.2f} {s['ptr']:>8.2f} {s['win']:>6.0%}")
        res[lab] = s

# ---- honest positive control: trend continuation on trend days ----------------------
lab = "TREND-CONT  with the break, on TREND days"
dc = d.copy()
dc["side"] = np.where(d.side.values == "SHORT", "LONG", "SHORT")
raw = d.entry.values + np.where(d.side.values == "SHORT", 0.25, -0.25)
dc["entry"] = raw + np.where(dc.side.values == "LONG", 0.25, -0.25)
m = dc.date.isin(TREND_DAYS) & (~CHOP) & (dc.f_mv60 <= -4.0)
print(f"  [trend-cont events] {int(m.sum())}")
rows = []
for tp, sp in [(6.0, 5.0), (8.0, 5.0), (10.0, 6.0), (12.0, 8.0), (16.0, 10.0), (20.0, 10.0)]:
    s = S(run(dc, m, tp, sp), lab)
    if not s: continue
    rows.append(dict(tp=tp, sp=sp, **{k: s[k] for k in ("n", "net", "ptr", "win")}))
    print(f"{lab:44s} {f'{tp}/{sp}':>9s} {s['n']:>5d} {s['net']:>10,.2f} {s['ptr']:>8.2f} {s['win']:>6.0%}")
res[lab] = rows
if rows:
    R = pd.DataFrame(rows)
    print(f"\n  TREND-CONT positive cells: {int((R.ptr>0).sum())}/{len(R)}  "
          f"median ${R.ptr.median():.3f}/tr  best ${R.ptr.max():.3f}/tr")
    res["trend_cont_summary"] = dict(cells=len(R), pos=int((R.ptr > 0).sum()),
                                     med=round(float(R.ptr.median()), 3), best=round(float(R.ptr.max()), 3))
json.dump(res, open(f"{OUT3}/control.json", "w"), indent=1)
print(f"\n[wrote] {OUT3}/control.json")
