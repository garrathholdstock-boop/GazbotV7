#!/usr/bin/env python3
"""ONE TRADE PER DAY, HELD TO THE CLOSE — the fundable version of "kill the target".

The overlapping version (every entry held to 20:40) is an accounting artefact: it needs 14 lots on a
median day and 78 at peak, is unfundable on 13 of 43 days, and its 666 "trades" are ~43 day-bets
scaled up. THIS takes ONE position per day, which is fundable, matches the literature's
one-decision-a-day convergence, and makes each trade an independent observation.

TWO POPULATIONS, because 43 days cannot resolve anything:
  (1) THE LIVE ENTRIES  - the first entry of each session from the real trade record, 43 days.
  (2) THE LONG TAPE     - the first drift-confirmed entry of each session over 2,656 sessions of
                          NQ 1-minute, 2015-2025, using the REAL detector replayed causally
                          (validated against the driftlab record: 232 agree, 0 disagree).

CONTROL: the same entries at the same bars with the SIDE REVERSED. It cannot move the entry
population, so any difference is direction and nothing else.
COST: 1.25pt all-in per round trip, charged on every trade.
"""
from __future__ import annotations
import sqlite3, sys
import numpy as np, pandas as pd

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
GB = "/home/alphabot/gazbot7"
COST_PT, VPP = 1.25, 2.0
FLAT_S = 20 * 3600 + 40 * 60
rng = np.random.default_rng(17)


def ci(x):
    x = np.asarray(x, float)
    idx = rng.integers(0, len(x), size=(10000, len(x)))
    b = x[idx].mean(axis=1)
    return x.mean(), np.percentile(b, 2.5), np.percentile(b, 97.5)


def sweep(pnl_by_stop, label, n_days):
    print(f"\n  {label}  ({n_days} sessions, one trade each)")
    print(f"{'stop':>8}{'pt/day':>10}{'95% CI':>22}{'flipped':>10}{'EDGE':>9}{'$/day':>9}{'win%':>7}")
    for s, (real, flip) in pnl_by_stop.items():
        m, lo, hi = ci(real)
        fm = np.mean(flip)
        tag = "" if lo > 0 else "  spans 0"
        print(f"{s:>7}p{m:>10.2f}   [{lo:>+7.2f},{hi:>+7.2f}]{fm:>10.2f}{(m-fm)/2:>9.2f}"
              f"{m*VPP:>9.0f}{100*np.mean(np.asarray(real) > 0):>6.0f}%{tag}")


def live():
    t = sqlite3.connect(f"file:{GB}/data/gazbot7.db?mode=ro", uri=True)
    tr = pd.read_sql("select side,entry_price,opened_at from trades where closed_at is not null "
                     "and qty=1", t)
    tr["dt"] = pd.to_datetime(tr.opened_at, format="mixed", utc=True)
    tr["day"] = tr.dt.dt.date
    tr["t0"] = tr.dt.dt.tz_localize(None).astype("datetime64[s]").astype("int64")
    first = tr.sort_values("t0").groupby("day").first().reset_index()
    c = sqlite3.connect(f"file:{GB}/data/capture.db?mode=ro", uri=True)
    b = pd.read_sql("select bar_ts,high,low,close from bars where symbol='MNQ' and timeframe='5s'"
                    " order by bar_ts", c)
    ts, hi, lo, cl = b.bar_ts.values, b.high.values, b.low.values, b.close.values
    out = {}
    for stop in (15, 30, 60, 120, 10**9):
        real, flip = [], []
        for _, r in first.iterrows():
            a = np.searchsorted(ts, r.t0); day0 = (r.t0 // 86400) * 86400
            z = np.searchsorted(ts, day0 + FLAT_S, side="right")
            if z - a < 2: continue
            e = r.entry_price; long = str(r.side).upper().startswith(("B", "L"))
            for sgn, bucket in ((1, real), (-1, flip)):
                up = long if sgn > 0 else not long
                adv = (e - lo[a:z]) if up else (hi[a:z] - e)
                if stop < 10**8 and (adv >= stop).any():
                    bucket.append(-stop - COST_PT)
                else:
                    mv = (cl[z-1] - e) if up else (e - cl[z-1])
                    bucket.append(mv - COST_PT)
        out["none" if stop > 10**8 else stop] = (real, flip)
    sweep(out, "(1) LIVE ENTRIES — first trade of each session", len(out[30][0]))


def longtape():
    from bt_cut_flip_long import sessions, entry_of
    df = sessions("nq_long")
    ent = []
    for day, g in df.groupby("d", sort=True):
        e = entry_of(g)
        if e: ent.append((day, g, e[0], e[1]))
    print(f"\n  long tape: {len(ent)} sessions with a causal drift confirmation")
    out = {}
    for stop in (15, 30, 60, 120, 10**9):
        real, flip = [], []
        for day, g, t0, side in ent:
            s = g[(g.ts > t0) & (g.sec <= FLAT_S)]
            if len(s) < 30: continue
            e = s.open.values[0]; h, l, c2 = s.high.values, s.low.values, s.close.values
            for sgn, bucket in ((1, real), (-1, flip)):
                sd = side * sgn
                adv = (e - l) if sd > 0 else (h - e)
                if stop < 10**8 and (adv >= stop).any():
                    bucket.append(-stop - COST_PT)
                else:
                    bucket.append(sd * (c2[-1] - e) - COST_PT)
        out["none" if stop > 10**8 else stop] = (real, flip)
    sweep(out, "(2) LONG TAPE — first drift-confirmed entry, 2015-2025", len(out[30][0]))


if __name__ == "__main__":
    print(f"ONE TRADE PER DAY, HELD TO 20:40Z · no target · {COST_PT}pt all-in charged")
    live(); longtape()
