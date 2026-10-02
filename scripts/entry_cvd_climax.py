#!/usr/bin/env python3
"""THE OPERATOR'S ENTRY RULE, MEASURED — the CVD climax roll-off.

★★★ Phase 0 / Experiment #2 of docs/SCOPE_RECURSIVE_TRADING_LOOP.md.

⚠⚠ WHY THIS EXISTS SEPARATELY FROM turn_measure.py. That harness refuted the PRICE-ONLY turn
retrace: entered at the fire, a symmetric race is a coin across 24 cells. But that is NOT the
operator's rule. His is:

    "once its run a lot and cvd and peice are birh lushinf hard right ill claim.
     and wait for the turn."

Two conditions, not one — price extended AND **aggression pinned hard in the direction of the run**
(the climax) — then enter the other way as CVD rolls OFF the extreme. The price-only study ignored
the CVD half entirely, which is the half he actually watches. Refuting one and claiming the other
fell with it would be the [[agreement-is-not-independence]] error in reverse.

HIS RULE AS SHIPPED IN THE GAUGE HE READ: position of session-cumulative CVD within its ROLLING
180-MINUTE range, 0-100. Trigger = reach >= HI, then cross back below LO. On 2026-09-29 that fired
31 times over 6 sessions with price falling a median 42.1pt afterwards — a directional result, and
the only entry evidence on this desk that is not a coin. This re-measures it on **74 sessions**.

⚠ METHOD, and the traps it is built against:
  · the gauge is replicated from `web.cvd_meter`'s DEFINITION (session anchor 22:00Z, level is
    cumulative, only the SCALE rolls over 180min) rather than re-invented;
  · the decision uses only bars/ticks up to that minute — no peak reading, no future bar;
  · the verdict is a SYMMETRIC RACE (+N before -N on bar highs/lows), because
    [[mfe-is-not-a-win-rate]] and on a symmetric race 50% IS zero;
  · a CONTROL arm fires at random minutes matched for count and session, because
    [[a-control-is-supposed-to-lose]] and a trigger must beat showing up at random;
  · both sides are reported per threshold cell so the search can be charged.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

WINDOW_MIN = 180          # the gauge's rolling scale, as shipped in web.cvd_meter
SESSION_ANCHOR_H = 22     # 22:00Z, the same anchor as the dashboard's session high/low/VWAP
RACE_MIN = 120            # 2h, the same forward window the turn study used


def load(sessions: int):
    """Per-minute (session, minute, close, high, low, cvd_level) from the lake.

    ⚠ ONE QUERY, aggregated in DuckDB — [[duckdb-pandas-for-analytics]]; a python row-loop over
    76M ticks would take hours. ⚠ `aggressor` is LOWERCASE in this table; comparing to 'BUY'
    returns exactly 0 for every row and looks like a clean null.
    """
    from gazbot7.lake import connect
    con = connect()
    q = f"""
    WITH t AS (
        SELECT
            CAST((ts_ms / 1000 - {SESSION_ANCHOR_H} * 3600) / 86400 AS INT) AS sess,
            CAST(ts_ms / 60000 AS INT)                                      AS minute,
            SUM(CASE WHEN aggressor = 'buy'  THEN size
                     WHEN aggressor = 'sell' THEN -size ELSE 0 END)         AS net
        FROM ticks WHERE symbol = 'MNQ' GROUP BY 1, 2
    ), b AS (
        SELECT CAST(bar_ts / 60 AS INT) AS minute,
               MAX(high) h, MIN(low) l, ARG_MAX(close, bar_ts) c
        FROM bars WHERE symbol = 'MNQ' GROUP BY 1
    )
    SELECT t.sess, t.minute, b.c, b.h, b.l,
           SUM(t.net) OVER (PARTITION BY t.sess ORDER BY t.minute) AS cvd
    FROM t JOIN b ON b.minute = t.minute
    ORDER BY t.sess, t.minute
    """
    rows = con.execute(q).fetchall()
    by: dict[int, list] = {}
    for sess, minute, c, h, l, cvd in rows:
        if c is None:
            continue
        by.setdefault(int(sess), []).append((int(minute), float(c), float(h), float(l), float(cvd)))
    out = [(s, v) for s, v in sorted(by.items()) if len(v) >= 300]
    return out[-sessions:] if sessions else out


def gauge(series):
    """CVD position 0-100 within its ROLLING 180-min range, exactly as the dashboard showed it.

    ⚠ Returns None while the window holds no spread — a 'position in a range' is undefined when the
    range is zero, which is the same warm-up fault the gap study had to amend for.
    """
    out = []
    for i in range(len(series)):
        lo_i = max(0, i - WINDOW_MIN + 1)
        win = [x[4] for x in series[lo_i:i + 1]]
        hi, lo = max(win), min(win)
        out.append(None if hi <= lo else 100.0 * (series[i][4] - lo) / (hi - lo))
    return out


def race(series, i, direction, n_pt):
    """Does +n_pt arrive before -n_pt, entering at close[i] in `direction`? 1 / 0 / None."""
    entry = series[i][1]
    for j in range(i + 1, min(i + 1 + RACE_MIN, len(series))):
        _m, _c, h, l, _v = series[j]
        fav = (h - entry) if direction > 0 else (entry - l)
        adv = (entry - l) if direction > 0 else (h - entry)
        if fav >= n_pt:
            return 1
        if adv >= n_pt:
            return 0
    return None


def triggers(series, g, hi: float, lo: float):
    """Climax then roll-off. Returns [(index, new_direction)].

    Pinned HIGH = buyers have been maximally aggressive = the UP move is climaxing, so the roll-off
    is a SHORT. Pinned LOW is the mirror. ⚠ This is the operator's reading and it is the inverse of
    the naive one; the desk measured the same inversion at leg scale (CVD agreed with the NEW
    direction at only 4 of 26 turns).
    """
    out, armed_hi, armed_lo = [], False, False
    for i, v in enumerate(g):
        if v is None:
            continue
        if v >= hi:
            armed_hi, armed_lo = True, False
        elif v <= 100 - hi:
            armed_lo, armed_hi = True, False
        elif armed_hi and v < lo:
            out.append((i, -1)); armed_hi = False
        elif armed_lo and v > 100 - lo:
            out.append((i, +1)); armed_lo = False
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=74)
    ap.add_argument("--hi", default="90,95")
    ap.add_argument("--lo", default="85,90")
    ap.add_argument("--targets", default="25,50,75")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    sess = load(a.sessions)
    print(f"sessions with aggressor + bars: {len(sess)}")
    print(f"gauge = CVD position in its rolling {WINDOW_MIN}min range, session anchored "
          f"{SESSION_ANCHOR_H}:00Z — the same definition he read")
    print(f"race = +N before -N on bar highs/lows within {RACE_MIN}min. 50% IS ZERO.\n")

    rng = random.Random(20261002)
    results = {}
    for hi in [float(x) for x in a.hi.split(",")]:
        for lo in [float(x) for x in a.lo.split(",")]:
            if lo >= hi:
                continue
            fires, ctrl = [], []
            for _s, series in sess:
                g = gauge(series)
                t = triggers(series, g, hi, lo)
                fires += [(series, i, d) for i, d in t]
                # CONTROL: same count, same session, random minute, random side
                for _ in t:
                    j = rng.randrange(WINDOW_MIN, len(series) - 1)
                    ctrl.append((series, j, rng.choice((-1, 1))))
            cells = {}
            for npt in [float(x) for x in a.targets.split(",")]:
                w = [race(s, i, d, npt) for s, i, d in fires]
                cw = [race(s, i, d, npt) for s, i, d in ctrl]
                w = [x for x in w if x is not None]
                cw = [x for x in cw if x is not None]
                cells[npt] = {"n": len(w), "rule": round(100 * sum(w) / len(w), 1) if w else None,
                              "control": round(100 * sum(cw) / len(cw), 1) if cw else None}
            rate = len(fires) / len(sess)
            results[f"{hi:.0f}/{lo:.0f}"] = {"fires_per_session": round(rate, 2),
                                             "fires": len(fires), "cells": cells}
            print(f"  climax>={hi:.0f} roll-off<{lo:.0f}   {len(fires)} fires "
                  f"({rate:.2f}/session)")
            for npt, c in cells.items():
                edge = (c["rule"] - c["control"]) if (c["rule"] and c["control"]) else None
                print(f"      +/-{npt:>5.0f}pt   rule {str(c['rule']):>5}%   "
                      f"control {str(c['control']):>5}%   edge "
                      f"{('%+.1f' % edge) if edge is not None else ' n/a'}pp   n={c['n']}")
            print()
    if a.json:
        print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
