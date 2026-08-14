#!/usr/bin/env python3
"""Derive GOLD-NATIVE drift thresholds from gold's own tape. Stop using MNQ's numbers.

    PYTHONPATH=src .venv/bin/python scripts/mgc_drift_thresholds.py [--apply]

Operator, 2026-08-14: *"why are you using mnq thresholds? dont be lazy. analyse the tape for every
day we have and derive actual mgc thresholds."*

He is right, and it is the exact mistake the MGC brief forbids ("gates INVENTED FRESH — no porting or
re-tuning any of the six MNQ gates"). `drift.ER_MIN = 0.15` and `RT_MIN = 0.45` were calibrated on
MNQ, an instrument with roughly TEN TIMES gold's ATR (15-25pt vs 1.6-2.9pt). A threshold on a
*ratio* is not automatically transferable just because the ratio is dimensionless: efficiency and
roundtrip both depend on how an instrument's path fills its range, and that is instrument-specific
microstructure.

★★ HOW THESE ARE DERIVED, AND WHY NOT BY SWEEPING P&L. Fitting a threshold to maximise return on 16
gold days is how you manufacture a result — this desk has repeatedly found that the best of N cells
on a thin sample is exactly what chance produces. So the derivation is DISTRIBUTIONAL and P&L is
never consulted:

    1. Measure MNQ's own distribution of (efficiency, roundtrip) at the same point in the session.
    2. Find what PERCENTILE MNQ's live 0.15 / 0.45 occupy in it — i.e. how selective the live desk
       has actually chosen to be, expressed as "how unusual must this day be?"
    3. Read gold's value at THAT SAME PERCENTILE.

The transferable quantity is the SELECTIVITY, not the number. This asks "what counts as unusually
directional *for this instrument*", which is the question the MNQ constants were an answer to.

★ Then, and only then, `--apply` re-runs the day-rider study at the derived thresholds and prints a
sensitivity grid — because a derived point sitting on a PLATEAU is trustworthy and one sitting on a
SPIKE is noise ([[mcl-different-beast-gate-sweep]]: a spiky grid means fluke).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from gazbot7 import drift, lake  # noqa: E402
from mgc_session_anchor import minute_bars  # noqa: E402

OPEN_MIN, FLAT_MIN = 13 * 60 + 30, 20 * 60 + 40
DETECT_MIN = 60


def load_symbol(sym: str) -> pd.DataFrame:
    con = lake.connect(symbol=sym)
    b = con.execute(f"SELECT bar_ts, open, high, low, close FROM bars WHERE symbol='{sym}' "
                    f"ORDER BY bar_ts").df()
    b["ts"] = pd.to_datetime(b["bar_ts"], unit="s", utc=True)
    return minute_bars(b)


def session_metrics(m: pd.DataFrame, detect_min: int = DETECT_MIN) -> pd.DataFrame:
    """(efficiency, roundtrip, atr, net) at +detect_min for every session, via the REAL compute()."""
    rows = []
    for day, dm in m.groupby(m.index.date):
        s = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=OPEN_MIN)
        e = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=FLAT_MIN)
        w = dm.loc[s:e]
        if len(w) < detect_min:
            continue
        head = w.iloc[:detect_min]
        bars = [(int(ts.value // 10**9), r["high"], r["low"], r["close"])
                for ts, r in head.iterrows()]
        r = drift.compute(bars)
        if not r.ok:
            continue
        rows.append({"day": str(day), "eff": r.efficiency, "rt": r.roundtrip,
                     "atr": r.atr, "net_pt": abs(r.net_pt), "range_pt": r.range_pt})
    return pd.DataFrame(rows)


def pct_of(series: pd.Series, value: float) -> float:
    """What percentile does `value` occupy in this distribution?"""
    return float((series <= value).mean() * 100)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    print("  Deriving gold-native drift thresholds. P&L is NOT consulted here.\n")
    out = {}
    for sym in ("MNQ", "MGC"):
        m = load_symbol(sym)
        d = session_metrics(m)
        out[sym] = d
        print(f"  {sym}: {len(d)} sessions with >= {DETECT_MIN}m of tape "
              f"({m.index.min():%Y-%m-%d}..{m.index.max():%Y-%m-%d})")
        for col, lbl in (("eff", "efficiency"), ("rt", "roundtrip"), ("atr", "ATR pt")):
            q = d[col].quantile([.25, .5, .75, .9]).round(3).tolist()
            print(f"    {lbl:<11} p25={q[0]:<7} p50={q[1]:<7} p75={q[2]:<7} p90={q[3]}")
        print()

    mnq, mgc = out["MNQ"], out["MGC"]
    if mnq.empty or mgc.empty:
        print("  insufficient data")
        return 1

    print("  ═══ WHAT SELECTIVITY DO THE LIVE MNQ CONSTANTS ENCODE? ═══")
    er_pct = pct_of(mnq["eff"], drift.ER_MIN)
    rt_pct = pct_of(mnq["rt"], drift.RT_MIN)
    print(f"    ER_MIN {drift.ER_MIN}  sits at MNQ's p{er_pct:.0f}  → it admits the top "
          f"{100-er_pct:.0f}% of MNQ sessions")
    print(f"    RT_MIN {drift.RT_MIN}  sits at MNQ's p{rt_pct:.0f}  → it admits the top "
          f"{100-rt_pct:.0f}% of MNQ sessions")

    er_gold = float(mgc["eff"].quantile(er_pct / 100))
    rt_gold = float(mgc["rt"].quantile(rt_pct / 100))
    print(f"\n  ═══ THE SAME SELECTIVITY, READ OFF GOLD'S OWN DISTRIBUTION ═══")
    print(f"    MGC ER_MIN = p{er_pct:.0f} of gold efficiency  = {er_gold:.3f}   "
          f"(MNQ's number was {drift.ER_MIN})")
    print(f"    MGC RT_MIN = p{rt_pct:.0f} of gold roundtrip   = {rt_gold:.3f}   "
          f"(MNQ's number was {drift.RT_MIN})")
    for lbl, mine, theirs in (("efficiency", er_gold, drift.ER_MIN), ("roundtrip", rt_gold, drift.RT_MIN)):
        d = "LOOSER" if mine < theirs else "TIGHTER"
        print(f"    → gold's {lbl} floor is {d} than MNQ's by {abs(mine-theirs):.3f}")

    print(f"\n    Using MNQ's numbers on gold admits "
          f"{((mgc['eff'] >= drift.ER_MIN) & (mgc['rt'] >= drift.RT_MIN)).mean()*100:.0f}% of gold "
          f"sessions; the derived pair admits "
          f"{((mgc['eff'] >= er_gold) & (mgc['rt'] >= rt_gold)).mean()*100:.0f}% — "
          f"MNQ's target selectivity is "
          f"{((mnq['eff'] >= drift.ER_MIN) & (mnq['rt'] >= drift.RT_MIN)).mean()*100:.0f}% on MNQ.")

    if a.apply:
        import mgc_day_rider_study as S
        m = load_symbol("MGC")
        print("\n  ═══ SENSITIVITY: is the derived point a PLATEAU or a SPIKE? ═══")
        print(f"  {'ER':>6}{'RT':>6}{'fired':>7}{'held%':>7}{'final$':>10}{'MFE$':>10}")
        base_er, base_rt = drift.ER_MIN, drift.RT_MIN
        try:
            for er in sorted({round(er_gold * k, 3) for k in (0.6, 0.8, 1.0, 1.2, 1.5)}):
                for rt in sorted({round(rt_gold * k, 3) for k in (0.8, 1.0, 1.2)}):
                    drift.ER_MIN, drift.RT_MIN = er, rt
                    df = S.study(m, DETECT_MIN)
                    f = df[df.fired]
                    if not len(f):
                        print(f"  {er:>6.3f}{rt:>6.3f}{0:>7}{'—':>7}{'—':>10}{'—':>10}")
                        continue
                    mark = "  ← derived" if abs(er - er_gold) < 1e-9 and abs(rt - rt_gold) < 1e-9 else ""
                    print(f"  {er:>6.3f}{rt:>6.3f}{len(f):>7}"
                          f"{(f['final$'] > 0).mean()*100:>7.1f}{f['final$'].sum():>10.2f}"
                          f"{f['mfe$'].sum():>10.2f}{mark}")
        finally:
            drift.ER_MIN, drift.RT_MIN = base_er, base_rt   # never leave the live module mutated
        print("\n  ⚠ read the GRID, not the best cell. A plateau of adjacent positive cells is a"
              "\n    finding; a lone spike beside negatives is noise, whatever its number.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
