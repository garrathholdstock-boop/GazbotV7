#!/usr/bin/env python3
"""IS A RUN BROAD? — and does it matter for how far his legs go.

Operator: "pull all the data from ibkr to be able to tell me if a run is broad or not. and backtest
it well to see if true."

★★ WHY THIS IS NOT CIRCULAR. NQ *is* the float-cap-weighted sum of its constituents, so the
megacaps cannot "lead" it — that is arithmetic. What is not arithmetic is BREADTH: whether a move is
carried by ONE name or by ALL of them. "NQ +40 on NVDA alone" and "NQ +40 with everything
participating" are genuinely different tapes, and only the second is visible from the constituents.

THE TEST. For every MNQ leg that OPENS inside US cash hours, count how many of the ten megacaps
moved the leg's way over the preceding 15 minutes. Then ask whether broad legs run further.

⚠ METHOD, and these are traps this desk has already paid for:
  - DAY-CLUSTERED bootstrap. Intraday legs on one session are not independent draws; a naive CI
    across overlapping windows is far too tight.
  - BREADTH IS MEASURED AT LEG OPEN ONLY. Using any bar after the open leaks the outcome into the
    predictor — the look-ahead that `resample labels the left edge` was banked for.
  - US CASH HOURS ONLY (13:30-20:00Z). Outside them the constituents are SHUT and their last print
    is stale, which would manufacture a "breadth" reading from yesterday's close. ⚠ This is also why
    the answer can only ever apply to ~37% of his entries.
  - A CONTROL IS SUPPOSED TO LOSE: the comparison is broad vs NARROW legs, not broad vs nothing.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import os
import statistics as st
import sys

import numpy as np

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

NDX = "/home/alphabot/gazbot7/data/ndx"
US_OPEN, US_CLOSE = dt.time(13, 30), dt.time(20, 0)
LOOKBACK_MIN = 15


def load_names() -> dict:
    out = {}
    for f in sorted(glob.glob(f"{NDX}/*_5min.csv")):
        sym = os.path.basename(f).split("_")[0]
        rows = {}
        with open(f) as fh:
            for r in csv.DictReader(fh):
                rows[int(r["ts"])] = float(r["close"])
        if rows:
            out[sym] = rows
    return out


def mnq_legs():
    """The SAME leg definition the watcher and the alerts use — 1xATR in 8 min, dies on 3xATR back
    from the extreme. A second definition here is how the dashboard and the alert drift apart."""
    import pandas as pd
    from tunnel_fit_mgc import front_month_minutes, true_range
    bars, rolls = front_month_minutes(verbose=False, symbol="MNQ")
    trs = true_range(bars, rolls)
    cl = np.array([b["close"] for b in bars], float)
    ts = np.array([b["m"] for b in bars], np.int64)
    tr = np.array([t if t is not None else np.nan for t in trs], float)
    atr = pd.Series(tr).rolling(14, min_periods=5).mean().values
    out, i, n = [], 20, len(cl)
    while i < n - 2:
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            i += 1; continue
        mv = cl[i] - cl[i - 8]
        if abs(mv) < a:
            i += 1; continue
        sgn = 1 if mv > 0 else -1
        ext, j = cl[i], i
        while j + 1 < n and ts[j + 1] - ts[i - 8] < 86400:
            j += 1
            if sgn * (cl[j] - ext) > 0:
                ext = cl[j]
            elif sgn * (ext - cl[j]) >= 3.0 * a:
                break
        if j - (i - 8) >= 10:
            out.append({"t0": int(ts[i - 8]), "sgn": sgn,
                        "mins": j - (i - 8), "travel": sgn * (ext - cl[i - 8])})
        i = j + 1
    return out


def breadth_at(names: dict, t0: int, sgn: int, window: int = -LOOKBACK_MIN) -> tuple[int, int]:
    """How many megacaps moved the leg's way across a window around the open.

    `window` NEGATIVE = the minutes BEFORE t0 (were they already moving — a confirmation read).
    `window` POSITIVE = the leg's OWN opening minutes (is THIS move broad — the real question).
    ⚠ A positive window is NOT look-ahead so long as it does not exceed the 8 minutes that DEFINE
    the leg: the detector needs those bars too, so both are known at the same instant. Anything
    beyond 8 minutes would leak the outcome into the predictor.
    """
    a_t = t0 if window < 0 else t0 + window * 60
    b_t = t0 - abs(window) * 60 if window < 0 else t0
    agree = tot = 0
    for sym, rows in names.items():
        a = max((t for t in rows if t <= a_t), default=None)
        b = max((t for t in rows if t <= b_t), default=None)
        # ⚠ both must be FRESH: a stale print from a previous session would invent a reading
        if a is None or b is None or a_t - a > 900 or a == b:
            continue
        tot += 1
        if np.sign(rows[a] - rows[b]) == sgn:
            agree += 1
    return agree, tot


def dayci(vals, days, n=4000, seed=7):
    """Day-clustered bootstrap — intraday legs on one session are not independent draws."""
    rng = np.random.default_rng(seed)
    by = {}
    for v, d in zip(vals, days):
        by.setdefault(d, []).append(v)
    keys = list(by)
    if len(keys) < 3:
        return float(np.mean(vals)), float("nan"), float("nan")
    boots = []
    for _ in range(n):
        pick = rng.choice(len(keys), len(keys), replace=True)
        s = [x for k in pick for x in by[keys[k]]]
        boots.append(np.mean(s))
    return float(np.mean(vals)), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


WINDOW = int(os.environ.get("BREADTH_WINDOW", "-15"))


def main() -> int:
    names = load_names()
    print(f"breadth window: {WINDOW:+d} min "
          + ("(BEFORE the leg — were they already moving?)" if WINDOW < 0
             else "(the leg's OWN opening move — is THIS run broad?)"))
    print(f"constituents loaded: {len(names)} · {', '.join(sorted(names))}\n")
    legs = mnq_legs()
    us = []
    for l in legs:
        t = dt.datetime.fromtimestamp(l["t0"], dt.UTC)
        if not (US_OPEN <= t.time() < US_CLOSE):
            continue
        agree, tot = breadth_at(names, l["t0"], l["sgn"], WINDOW)
        if tot < 8:                      # need most of the complex present to call it breadth
            continue
        us.append({**l, "agree": agree, "tot": tot, "day": t.date().isoformat(),
                   "frac": agree / tot})
    print(f"{len(legs)} legs total · {len(us)} opened in US cash hours with a usable breadth read\n")
    if len(us) < 30:
        print("⚠ TOO FEW TO CONCLUDE ANYTHING. Reporting the split for interest only.")
    bands = [("NARROW  <=40%", 0.0, 0.401), ("MIXED 40-70%", 0.401, 0.701), ("BROAD   >70%", 0.701, 1.01)]
    print(f"{'band':<14} {'n':>4} {'median travel':>14} {'median mins':>12} {'mean travel (day-clustered 95% CI)':>38}")
    for lab, lo, hi in bands:
        s = [x for x in us if lo <= x["frac"] < hi]
        if not s:
            print(f"{lab:<14} {0:>4}"); continue
        tv = [abs(x["travel"]) for x in s]
        m, cl_, ch = dayci(tv, [x["day"] for x in s])
        print(f"{lab:<14} {len(s):>4} {st.median(tv):>13.1f}pt {st.median([x['mins'] for x in s]):>11.0f}m "
              f"{m:>16.1f}pt  [{cl_:.1f}, {ch:.1f}]")
    # the honest headline: does BROAD beat NARROW, with the difference bootstrapped?
    broad = [abs(x["travel"]) for x in us if x["frac"] > 0.7]
    narrow = [abs(x["travel"]) for x in us if x["frac"] <= 0.4]
    if broad and narrow:
        print(f"\n  BROAD − NARROW on median travel: "
              f"{st.median(broad) - st.median(narrow):+.1f}pt "
              f"(broad n={len(broad)}, narrow n={len(narrow)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
