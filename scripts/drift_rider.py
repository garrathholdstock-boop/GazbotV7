#!/usr/bin/env python3
"""DRIFT RIDER — wait until the TAPE declares a direction, take 2 lots, hold to the next US open.

Operator, 2026-08-05, correcting my first attempt: "its nothing to do with waiting a certain amount of
time. its waiting until the tape finally says ok we have an upward drift today. so buy long. or
inversely. tape going south today. buy short. if tapes doing nothing. stay out. you get me? and hold it
all day until close to us open and sell at the highest position we can achieve. nothing to do with time."

★ MY FIRST VERSION WAS WRONG AND THIS IS THE FIX. `open_trend_hold.py` forced an entry at a fixed clock
offset (13:45, 14:00, ...) and required the day to have declared itself by exactly that minute. That is
a TIME trigger wearing a trend costume: it both missed days that declared later and forced entries on
days that never declared at all. n collapsed to 3-17 and every positive cell died on strip-best-day.
Here there is NO clock on the entry. Each minute is asked one question — "has the tape declared?" — and
the first YES enters. A session that never says yes takes NO TRADE, which is the operator's third case
and the one a fixed-time design cannot express.

★ WHAT "THE TAPE HAS DECLARED" MEANS, measurably. Two conditions together, both from the desk's own
vocabulary, evaluated on the session so far and therefore CAUSAL (never the finished day):
  ROUNDTRIP  |net| / range >= R — the session has GONE somewhere rather than round-tripped. This is
             the discriminator untradeable.py validates (07-29/30 green vs 07-31 untradeable) and it
             is the one that separates today (0.92, a clean trend) from a 646pt range for -1pt.
  DISTANCE   |net| >= D ATR — it has gone somewhere BIG enough to be worth a lot, not 8 points of
             drift that technically round-trips cleanly.
Direction is the sign of net. No prediction is involved — that is the point. The tape has already
declared; we are following, not forecasting.

★ THE EXIT IS "THE HIGHEST WE CAN ACHIEVE", WHICH IS A TRAIL, NOT A PEAK. You cannot sell the actual
high without hindsight, and a backtest that does is lying. So: hold with a chandelier trail and a hard
flat before the next US cash open. The trail is what converts "hold it all day" into a real exit rule.

★ CONTROLS DECIDE IT. Buy-and-hold and sell-and-hold over the identical windows, plus the same entries
with direction RANDOMISED. If waiting for the declaration cannot beat simply holding, the declaration
adds nothing.

  PYTHONPATH=src .venv/bin/python scripts/drift_rider.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.lake import connect  # noqa: E402

VPP = 2.0
FEE = 1.50
OPEN_M = 13 * 60 + 30          # 13:30 UTC US cash open
FLAT_BY = 13 * 60 + 15         # flat by 13:15 UTC next day — "close to us open"


def load(con):
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) hi, min(low) lo,
               arg_max(close, bar_ts) cl
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    return [(int(m), float(h), float(lo), float(c)) for m, h, lo, c in rows]


def sessions(bars):
    """Group into TRADING sessions keyed by the US-open day: 13:30 UTC -> next 13:15 UTC.
    That is the operator's own cycle — enter after today's open, flat before tomorrow's."""
    out = defaultdict(list)
    for ts, hi, lo, cl in bars:
        d = dt.datetime.fromtimestamp(ts, dt.UTC)
        mod = d.hour * 60 + d.minute
        key = d.date() if mod >= OPEN_M else (d - dt.timedelta(days=1)).date()
        out[key].append((ts, hi, lo, cl, mod))
    return out


def run(sess, *, rt_min, dist_atr, atr_n=60, trail_k=0.0, mode="drift", seed=1):
    rnd = random.Random(seed)
    res = []
    for day in sorted(sess):
        rows = sorted(sess[day])
        if len(rows) < 240:
            continue
        # ── walk forward; the FIRST minute the tape has declared is the entry. No clock. ──
        entry = side = ei = None
        for i in range(30, len(rows)):
            ts, hi, lo, cl, mod = rows[i]
            seg = rows[:i + 1]
            o = seg[0][3]
            net = cl - o
            rng = max(x[1] for x in seg) - min(x[2] for x in seg)
            if rng <= 0:
                continue
            w = seg[-atr_n:]
            trs = [max(w[j][1] - w[j][2], abs(w[j][1] - w[j - 1][3]), abs(w[j][2] - w[j - 1][3]))
                   for j in range(1, len(w))]
            atr = sum(trs) / len(trs) if trs else 0.0
            if atr <= 0:
                continue
            if mode == "drift":
                if abs(net) / rng >= rt_min and abs(net) >= dist_atr * atr:
                    entry, side, ei = cl, (1 if net > 0 else -1), i
                    break
            else:                       # controls enter at the same bar the drift rule would have
                if abs(net) / rng >= rt_min and abs(net) >= dist_atr * atr:
                    entry, ei = cl, i
                    side = 1 if mode == "long" else (-1 if mode == "short"
                                                     else rnd.choice((1, -1)))
                    break
        if entry is None:
            res.append({"day": day, "traded": False, "pnl": 0.0})
            continue
        # ── hold: chandelier trail (the honest form of "sell the highest we can achieve") ──
        best = entry
        exit_px, why = None, "flat-clock"
        for ts, hi, lo, cl, mod in rows[ei + 1:]:
            if side > 0:
                best = max(best, hi)
            else:
                best = min(best, lo)
            if trail_k:
                tr = best - side * trail_k * atr
                if (lo <= tr) if side > 0 else (hi >= tr):
                    exit_px, why = tr, "trail"
                    break
            if mod >= FLAT_BY and mod < OPEN_M:
                exit_px, why = cl, "flat-clock"
                break
        if exit_px is None:
            exit_px = rows[-1][3]
        pnl = side * (exit_px - entry) * VPP * 2 - FEE * 2
        res.append({"day": day, "traded": True, "side": side, "pnl": pnl, "why": why,
                    "entry_mod": rows[ei][4]})
    return res


def rep(res, lab):
    t = [r for r in res if r["traded"]]
    if not t:
        print(f"{lab:<32}   no entries")
        return None
    tot = sum(r["pnl"] for r in t)
    g = sum(1 for r in t if r["pnl"] > 0)
    best = max(r["pnl"] for r in t)
    hrs = sorted(r["entry_mod"] for r in t)
    med = hrs[len(hrs) // 2]
    print(f"{lab:<32}{len(t):>4}/{len(res):<4}{tot:>9.0f}{tot/len(t):>9.0f}"
          f"{100*g/len(t):>7.0f}%{tot-best:>10.0f}   {med//60:02d}:{med%60:02d}")
    return tot


HDR = (f"{'config':<32}{'n/days':>9}{'total':>9}{'$/trade':>9}{'green':>8}"
       f"{'strip-1':>10}   med-entry")


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    con = connect(symbol="MNQ")
    sess = sessions(load(con))
    print(f"MNQ {len(sess)} sessions (13:30 UTC -> next 13:15 UTC), 2 lots, ${VPP}/pt\n")

    print("A. HOW MUCH DECLARATION TO DEMAND  (trail 3xATR)")
    print(HDR)
    for rt in (0.40, 0.55, 0.70):
        for dm in (1.0, 2.0, 3.0):
            rep(run(sess, rt_min=rt, dist_atr=dm, trail_k=3.0),
                f"  roundtrip>={rt:.2f} dist>={dm:.0f}ATR")

    print("\nB. CONTROLS — same entry bars, direction replaced")
    print(HDR)
    base = dict(rt_min=0.55, dist_atr=2.0, trail_k=3.0)
    rep(run(sess, **base), "  DRIFT (follow the tape)")
    rep(run(sess, mode="long", **base), "  always LONG")
    rep(run(sess, mode="short", **base), "  always SHORT")
    for s in (1, 2, 3):
        rep(run(sess, mode="rand", seed=s, **base), f"  RANDOM direction (seed {s})")

    print("\nC. THE TRAIL — how to 'sell the highest we can achieve'")
    print(HDR)
    for k in (0.0, 2.0, 3.0, 5.0):
        rep(run(sess, rt_min=0.55, dist_atr=2.0, trail_k=k),
            f"  trail {k:.0f}xATR" if k else "  no trail (hold to clock)")

    print("\n★ If DRIFT does not beat always-LONG, always-SHORT and RANDOM on the SAME entry bars,")
    print("  the declaration rule is picking timing, not direction, and should be said so plainly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
