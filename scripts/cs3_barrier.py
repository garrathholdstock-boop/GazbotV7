"""CHOP-SCALP 2026-08-29 — THE COST BARRIER, and a NECESSARY-CONDITION scan.

Every costed candidate in this study, in both windows, is negative in all 48 target/stop cells.
That pattern says the problem is not the exit grid -- it is that the SIGNAL is smaller than the
FRICTION. So measure the two quantities directly and compare them.

FRICTION per round trip, MNQ, stated in POINTS so it can be compared with drift:
    fee   $1.50 / $2.00 per point                    = 0.750 pt
    entry we cross the spread, 1 tick               = 0.250 pt
    exit  target = limit (0) .. stop = 1 tick (0.25) = 0.000-0.250 pt
    ------------------------------------------------------------------
    floor 1.000 pt   ceiling 1.250 pt

A chop-turn filter is only WORTH COSTING if its frictionless forward drift clears ~1.0 pt. This
scans every book/tape/geometry feature at five thresholds and four horizons and asks: does ANY of
them get there with a usable n?  Then it runs the same scan on SHUFFLED features so the best real
number is judged against the best a null can manufacture from the identical search.
"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
from cs2_common import OUT, load_events
from gf_cs_lib import ticks

OUT3 = "/home/alphabot/gazbot7/reports/friday_v7/sections/cs3"
VPP, FEE, TICK = 2.00, 1.50, 0.25
FRICTION_PT_LO = FEE / VPP + TICK              # 1.00 pt
FRICTION_PT_HI = FEE / VPP + TICK + TICK       # 1.25 pt

d = load_events()
CHOP = d.regime.isin(("CHOP", "DEAD_CHOP"))
c = d[CHOP].copy().reset_index(drop=True)
print(f"[chop events] {len(c):,} over {c.date.nunique()} days")

# ---- forward drift at several horizons, signed to the fade, computed once ------------
HORIZONS = (30, 60, 120, 300)
TT = {day: ticks(day) for day in sorted(c.date.unique())}
for H in HORIZONS:
    out = np.full(len(c), np.nan)
    for day, g in c.groupby("date"):
        tt, pp = TT[day]
        i0 = np.searchsorted(tt, g.dts.values, side="left")
        i1 = np.searchsorted(tt, g.dts.values + H, side="left")
        ok = (i0 < len(tt)) & (i1 < len(tt)) & (i1 > i0)
        mv = np.where(ok, pp[np.clip(i1, 0, len(pp) - 1)] - pp[np.clip(i0, 0, len(pp) - 1)], np.nan)
        out[g.index.values] = np.where(g.side.values == "SHORT", -mv, mv)
    c[f"drift{H}"] = out
print("[drift] control means, signed to the fade (pt):",
      {H: round(float(c[f'drift{H}'].mean()), 4) for H in HORIZONS})

FEATS = ["f_wall1", "f_wall5", "f_wall10", "f_imb", "f_wall_build", "f_supp_drain",
         "f_wall5_build", "f_supp5_drain", "f_refill", "f_pull", "f_refill_net", "f_l1ratio",
         "f_agg20", "f_agg60", "f_stall20", "f_stall60", "f_aggfrac20", "f_aggfrac60",
         "f_mv20", "f_mv60", "f_ext_atr", "f_vwap_slope", "f_vwap_flat", "f_rangepos",
         "f_extC30", "f_extH20", "f_extH15", "f_extC15", "atr14", "er30", "er15", "vol20"]
FEATS = [f for f in FEATS if f in c.columns]
QS = [0.50, 0.70, 0.80, 0.90, 0.95]

def scan(frame, cols, hor):
    """Best (feature, direction, quantile) by mean drift, subject to n >= NMIN."""
    NMIN = 50
    best, rows = None, []
    y = frame[f"drift{hor}"].values
    good = np.isfinite(y)
    for f in cols:
        x = frame[f].values.astype(float)
        for q in QS:
            thr = np.nanquantile(x, q)
            for direc in ("hi", "lo"):
                m = (x >= thr) if direc == "hi" else (x <= np.nanquantile(x, 1 - q))
                m = m & good & np.isfinite(x)
                n = int(m.sum())
                if n < NMIN:
                    continue
                mu = float(y[m].mean())
                t = mu / (y[m].std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
                rows.append((f, direc, q, n, mu, t))
                if best is None or mu > best[4]:
                    best = (f, direc, q, n, mu, t)
    return best, rows

print(f"\n=== NECESSARY-CONDITION SCAN — best frictionless drift any single filter can buy ===")
print(f"    friction to beat: {FRICTION_PT_LO:.2f}-{FRICTION_PT_HI:.2f} pt per round trip")
print(f"{'hor':>4s} {'feature':>16s} {'dir':>4s} {'q':>5s} {'n':>6s} {'drift_pt':>9s} {'t':>7s} {'vs friction':>12s}")
print("-" * 74)
real = {}
allrows = {}
for H in HORIZONS:
    b, rows = scan(c, FEATS, H)
    allrows[H] = rows
    real[H] = dict(feature=b[0], dir=b[1], q=b[2], n=b[3], drift=round(b[4], 4), t=round(b[5], 3))
    print(f"{H:>4d} {b[0]:>16s} {b[1]:>4s} {b[2]:>5.2f} {b[3]:>6d} {b[4]:>9.4f} {b[5]:>7.2f} "
          f"{b[4]/FRICTION_PT_LO:>11.1%}")

# ---- the same search, handed to the NULL --------------------------------------------
# Shuffle every feature WITHIN each day (destroys the feature->future link, keeps the day's
# drift distribution and each feature's marginal). The null gets the identical 5x2x|F| search.
print(f"\n=== MATCHED NULL — the identical search on within-day SHUFFLED features ===")
rng = np.random.default_rng(20260829)
NDRAW = 200
null = {}
for H in HORIZONS:
    bests = []
    for _ in range(NDRAW):
        s = c.copy()
        for f in FEATS:
            s[f] = s.groupby("date")[f].transform(lambda v: rng.permutation(v.values))
        b, _ = scan(s, FEATS, H)
        bests.append(b[4])
    bests = np.array(bests)
    p = float((bests >= real[H]["drift"]).mean())
    null[H] = dict(mean=round(float(bests.mean()), 4), p50=round(float(np.median(bests)), 4),
                   p95=round(float(np.quantile(bests, 0.95)), 4), draws=NDRAW,
                   p_null_beats_real=round(p, 4))
    print(f"  h={H:>3d}s  real best={real[H]['drift']:.4f}pt   "
          f"null best: mean={bests.mean():.4f} p50={np.median(bests):.4f} p95={np.quantile(bests,0.95):.4f}   "
          f"p(null >= real) = {p:.3f}")

json.dump({"friction_pt": [FRICTION_PT_LO, FRICTION_PT_HI],
           "control_drift": {str(H): round(float(c[f'drift{H}'].mean()), 4) for H in HORIZONS},
           "real_best": {str(k): v for k, v in real.items()},
           "matched_null": {str(k): v for k, v in null.items()},
           "n_chop_events": int(len(c)), "n_days": int(c.date.nunique()),
           "search_size": len(FEATS) * len(QS) * 2},
          open(f"{OUT3}/barrier.json", "w"), indent=1)
print(f"\n[search size] {len(FEATS)} features x {len(QS)} quantiles x 2 directions = "
      f"{len(FEATS)*len(QS)*2} cells per horizon")
print(f"[wrote] {OUT3}/barrier.json")
