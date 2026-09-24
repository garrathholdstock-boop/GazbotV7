#!/usr/bin/env python3
"""Does HIGH PULSE + DEEPLY ONE-WAY FLOW correspond with a decent run? (2026-09-24)

Operator: "run analysis for me on when pulse is up and flow is deeply one way does jt correspond
with a decent run".

★ METHOD, and the traps it is built to avoid:
  1. ⚠⚠ MFE IS NOT A WIN RATE. "How far did it go" ignores whether the STOP came first. Every cell
     below is a RACE: from the signal minute's close, walking 5s bars forward, did price touch
     +R before -R in the FLOW'S OWN DIRECTION? That is the only question a trader can act on, and
     the un-raced version once inflated a gate's win rate 29% -> 78% and shipped a loser live.
  2. ⚠⚠ MINUTES INSIDE A SESSION ARE NOT INDEPENDENT DRAWS. Consecutive minutes share overlapping
     forward windows and one trending afternoon supplies hundreds of correlated "observations".
     Intervals here are DAY-CLUSTERED bootstraps; a per-observation CI on this data is inflated
     roughly tenfold and would declare a winner out of noise.
  3. ⚠ THE CONTROL MUST BE STATED. The base rate is every US-hour minute, raced the same way. A
     cell only means something against that, never on its own.
  4. ⚠ `aggressor` lives only in `ticks`, pruned at FIVE DAYS. This can never be widened backwards.

Usage:  PYTHONPATH=src .venv/bin/python scripts/surge_analysis.py [--r 10] [--horizon 15]
"""
import argparse
import sqlite3
import sys

import numpy as np
import pandas as pd

GB = "/home/alphabot/gazbot7"


def load(cap):
    c = sqlite3.connect(f"file:{cap}?mode=ro", uri=True)
    t = pd.read_sql("SELECT ts_ms,size,aggressor FROM ticks WHERE symbol='MNQ'", c)
    b = pd.read_sql("SELECT bar_ts,close,high,low,volume FROM bars WHERE symbol='MNQ' "
                    "AND timeframe='5s' ORDER BY bar_ts", c)
    c.close()
    t["m"] = (t.ts_ms // 60000) * 60
    # ⚠ NEUTRAL EXCLUDED, NEVER SPLIT — 13% of the tape. Pro-rating it would manufacture imbalance
    # out of trades where nobody crossed the spread.
    piv = (t[t.aggressor.isin(["buy", "sell"])]
           .pivot_table(index="m", columns="aggressor", values="size", aggfunc="sum")
           .fillna(0.0))
    for col in ("buy", "sell"):
        if col not in piv:
            piv[col] = 0.0
    piv["flow"] = (piv.buy - piv.sell) / (piv.buy + piv.sell).replace(0, np.nan)
    b["m"] = (b.bar_ts // 60) * 60
    mv = b.groupby("m").volume.sum().rename("vol")
    mc = b.groupby("m").close.last().rename("close")
    g = pd.concat([piv["flow"], mv, mc], axis=1).dropna(subset=["vol", "close"]).reset_index()
    g["dt"] = pd.to_datetime(g["m"], unit="s", utc=True)
    g["d"] = g.dt.dt.date
    g = g[(g.dt.dt.hour >= 13) & (g.dt.dt.hour < 20)].copy()      # US hours, the tape it was set on
    # PULSE — this minute vs the MEDIAN of the previous 15 of the SAME session. No cross-day term.
    g["pulse"] = g.vol / g.groupby("d").vol.transform(
        lambda s: s.shift(1).rolling(15, min_periods=8).median())
    return g.dropna(subset=["pulse", "flow"]), b


def race(bars, t0, close0, d, r, horizon_min):
    """+R before -R, in direction d, walking 5s bars. Returns 1 win / 0 loss / None undecided."""
    w = bars[(bars.bar_ts > t0) & (bars.bar_ts <= t0 + horizon_min * 60)]
    if w.empty:
        return None
    up = (w.high.values - close0) * d
    dn = (w.low.values - close0) * d
    hit_t = np.argmax(up >= r) if (up >= r).any() else None
    hit_s = np.argmax(dn <= -r) if (dn <= -r).any() else None
    if hit_t is None and hit_s is None:
        return None                       # ⚠ UNDECIDED IS NOT A WIN. Reported separately.
    if hit_s is None:
        return 1
    if hit_t is None:
        return 0
    # ⚠ Same 5s bar touching both is genuinely ambiguous at this resolution — drop it rather than
    # award it to the side that flatters the result.
    return None if hit_t == hit_s else (1 if hit_t < hit_s else 0)


def boot(df, col, n=4000, seed=7):
    """Day-clustered bootstrap: resample DAYS, not rows."""
    rng = np.random.default_rng(seed)
    days = df.d.unique()
    if len(days) < 2:
        return (np.nan, np.nan)
    by = {d: df[df.d == d][col].values for d in days}
    out = []
    for _ in range(n):
        pick = rng.choice(days, len(days), replace=True)
        v = np.concatenate([by[d] for d in pick])
        if len(v):
            out.append(np.nanmean(v))
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))) if out else (np.nan,)*2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", type=float, default=10.0, help="race target/stop in points")
    ap.add_argument("--horizon", type=int, default=15, help="minutes to resolve the race")
    ap.add_argument("--cap", default=f"{GB}/data/capture.db")
    a = ap.parse_args()

    g, bars = load(a.cap)
    g["dir"] = np.sign(g.flow).replace(0, np.nan)
    g = g.dropna(subset=["dir"])
    g["win"] = [race(bars, m, c, d, a.r, a.horizon)
                for m, c, d in zip(g["m"], g["close"], g["dir"])]
    dec = g.dropna(subset=["win"]).copy()
    dec["win"] = dec["win"].astype(float)

    print(f"MNQ · US hours · {g.d.nunique()} sessions · {len(g):,} minutes "
          f"({len(dec):,} races decided, {len(g)-len(dec):,} undecided inside {a.horizon}m)")
    print(f"RACE: from the minute's close, ±{a.r:.0f}pt in the FLOW's direction, {a.horizon}m limit\n")
    base = dec.win.mean()
    lo, hi = boot(dec, "win")
    print(f"{'CONTROL — every US-hour minute':<42} n={len(dec):>5}  {100*base:>5.1f}%  "
          f"[{100*lo:.1f}, {100*hi:.1f}]\n")

    pb = [(0, 1.0, "pulse <1.0"), (1.0, 1.5, "pulse 1.0-1.5"),
          (1.5, 2.0, "pulse 1.5-2.0"), (2.0, 99, "pulse >2.0")]
    fb = [(0, .10, "|flow| <.10"), (.10, .20, "|flow| .10-.20"),
          (.20, .30, "|flow| .20-.30"), (.30, 1.01, "|flow| >.30  DEEP")]
    print(f"{'cell':<42} {'n':>6} {'win%':>7}  {'95% CI (day-clustered)':>24}")
    print("-" * 84)
    for f0, f1, fl in fb:
        for p0, p1, pl in pb:
            x = dec[(dec.pulse >= p0) & (dec.pulse < p1)
                    & (dec.flow.abs() >= f0) & (dec.flow.abs() < f1)]
            if len(x) < 25:
                print(f"{fl+' · '+pl:<42} {len(x):>6}  (too few to read)")
                continue
            lo, hi = boot(x, "win")
            flag = "  <<" if (lo > base * 100 / 100 and lo > base) else ""
            print(f"{fl+' · '+pl:<42} {len(x):>6} {100*x.win.mean():>6.1f}% "
                  f"  [{100*lo:>5.1f}, {100*hi:>5.1f}]{flag}")
        print()
    # the headline cell he asked about
    hot = dec[(dec.pulse >= 1.5) & (dec.flow.abs() >= 0.30)]
    if len(hot) >= 25:
        lo, hi = boot(hot, "win")
        print(f"HIS CELL — pulse>=1.5 AND |flow|>=.30:  n={len(hot)}  "
              f"{100*hot.win.mean():.1f}%  [{100*lo:.1f}, {100*hi:.1f}]  vs control {100*base:.1f}%")
        print("⚠ Overlaps the control's own sample and sits on "
              f"{hot.d.nunique()} distinct sessions — that, not n, is the real sample size.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
