#!/usr/bin/env python3
"""COMMIT DETECTOR — can the directional day be called LIVE, at 13:36, without knowing the ending?

Operator, 2026-08-05: "how certain are we of detecting the position. analyse and confirm."

★ THE PRIZE, established by scripts/drift_rider.py's per-day table: 18 of 39 MNQ sessions are
directional (roundtrip>=0.50), median move 478pt, and at the moment each one COMMITTED there was still
a median 416pt on the table — ~90% of the move. That is ~$1,666 per day and ~$31,871 total on 2 lots.
Both directions (8 UP / 10 DOWN), and nine of the eighteen commit between 13:31 and 13:42.

★ WHAT WAS HINDSIGHT AND WHAT WAS NOT. That table defined commitment as "net passed 50pt AND never
returned to the open". The second half looks at the future, which is why its measured adverse excursion
(median 43pt) was absurdly small — it selected exactly the moments that do not retrace. That number was
circular and is not used here.

★★ BUT ONLY HALF OF IT WAS HINDSIGHT, AND THAT IS THE WHOLE IDEA. "net >= T points from the open, and
price has not traded back through the open SINCE" is entirely computable at minute t from the past. The
live rule keeps the causal half and drops the clairvoyant half. And it comes with its own stop, for free
and structurally: IF PRICE RETURNS TO THE OPEN, THE THESIS IS DEAD. That is the generous,
chop-absorbing stop the operator asked for — it is not an ATR multiple picked from a sweep, it is the
level at which the day's own claim to a direction fails.

★ THE HONEST DENOMINATOR IS ALL 39 SESSIONS. The 21 days that go nowhere are the false positives and
they must be in the sample; testing a detector only on the days it was meant to catch is how a 46%
base rate turns into a fantasy. Every figure below includes them.

★ AND IT IS CONTROLLED. Same fires, direction replaced by always-long, always-short and coin-flips
across several seeds. If following the declared side does not beat the flips, the detector is timing,
not direction — that is what killed the first two attempts and it must be shown, not assumed.

  PYTHONPATH=src .venv/bin/python scripts/commit_detector.py
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

VPP, FEE = 2.0, 1.50
OPEN_M, FLAT_BY = 13 * 60 + 30, 13 * 60 + 15


def load(con):
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) hi, min(low) lo,
               arg_max(close, bar_ts) cl
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    out = defaultdict(list)
    for m, hi, lo, cl in rows:
        d = dt.datetime.fromtimestamp(int(m), dt.UTC)
        mod = d.hour * 60 + d.minute
        key = d.date() if mod >= OPEN_M else (d - dt.timedelta(days=1)).date()
        out[key].append((int(m), float(hi), float(lo), float(cl), mod))
    return out


def trade_day(rows, thr, *, mode="follow", rnd=None, allow_reentry=True, buffer_pt=0.0):
    """Walk the session ONCE, forward, using only the past. Returns a list of trades.

    ENTRY  |close - open| >= thr, and price has not traded back through the open since it first
           crossed thr in that direction. Direction = the sign of the move. No forecast.
    STOP   price trades back through the open (+/- buffer). The day's own thesis has failed.
    EXIT   flat before the next US cash open.
    """
    o = rows[0][3]
    out = []
    armed_side = 0
    entry = None
    for i, (ts, hi, lo, cl, mod) in enumerate(rows):
        if entry is not None:
            side, epx, stop = entry
            hit = (lo <= stop) if side > 0 else (hi >= stop)
            if hit:
                out.append({"side": side, "pnl": side * (stop - epx) * VPP * 2 - FEE * 2,
                            "why": "stop", "mod": mod})
                entry = None
                armed_side = 0 if allow_reentry else side
                continue
            if FLAT_BY <= mod < OPEN_M:
                out.append({"side": side, "pnl": side * (cl - epx) * VPP * 2 - FEE * 2,
                            "why": "flat-clock", "mod": mod})
                entry = None
                break
            continue
        net = cl - o
        if abs(net) < thr:
            continue
        side = 1 if net > 0 else -1
        if side == armed_side:
            continue                       # already tried this side and stopped; wait for the other
        if mode == "long":
            side = 1
        elif mode == "short":
            side = -1
        elif mode == "rand":
            side = rnd.choice((1, -1))
        # ★ THE STOP MUST SIT ON THE ADVERSE SIDE OF THE ENTRY, ALWAYS.
        # First version used the literal open level. For the FOLLOW direction that is correct — price
        # is above the open on a long, so the open is below = adverse. But a CONTROL that forces the
        # opposite side puts the open ABOVE a long entry, turning the "stop" into a target that fills
        # instantly for a guaranteed profit: the control printed 9,046 fires and $12,035,131 of pure
        # artefact. Risk distance is kept identical (the distance to the open, which is what the rule
        # structurally risks) but always placed where it can actually lose.
        risk = abs(cl - o) + buffer_pt
        entry = (side, cl, cl - side * risk)
        out.append({"open_at": mod})
        out[-1] = {"_open": True, "side": side, "epx": cl, "mod": mod}
    # position still open at the end of the data
    if entry is not None:
        side, epx, _stop = entry
        out.append({"side": side, "pnl": side * (rows[-1][3] - epx) * VPP * 2 - FEE * 2,
                    "why": "eod", "mod": rows[-1][4]})
    return [t for t in out if not t.get("_open")], [t for t in out if t.get("_open")]


def run(sess, thr, *, mode="follow", seed=1, buffer_pt=0.0):
    rnd = random.Random(seed)
    closed, opens, per_day = [], [], []
    for day in sorted(sess):
        rows = sorted(sess[day], key=lambda x: x[0])
        if len(rows) < 240:
            continue
        c, o_ = trade_day(rows, thr, mode=mode, rnd=rnd, buffer_pt=buffer_pt)
        closed += c
        opens += o_
        per_day.append({"day": day, "pnl": sum(t["pnl"] for t in c), "n": len(c),
                        "first": min((t["mod"] for t in o_), default=None)})
    return closed, opens, per_day


def rep(closed, per_day, lab):
    if not closed:
        print(f"{lab:<28}   no fires")
        return None
    tot = sum(t["pnl"] for t in closed)
    traded = [d for d in per_day if d["n"]]
    g = sum(1 for d in traded if d["pnl"] > 0)
    bestday = max((d["pnl"] for d in traded), default=0)
    firsts = sorted(d["first"] for d in traded if d["first"] is not None)
    med = firsts[len(firsts) // 2] if firsts else 0
    stops = sum(1 for t in closed if t["why"] == "stop")
    print(f"{lab:<28}{len(closed):>5}{len(traded):>5}{tot:>9.0f}{100*g/max(len(traded),1):>7.0f}%"
          f"{tot-bestday:>10.0f}{100*stops/len(closed):>8.0f}%   {med//60:02d}:{med%60:02d}")
    return tot


HDR = (f"{'config':<28}{'fires':>5}{'days':>5}{'total':>9}{'green':>8}"
       f"{'strip-day':>10}{'stopped':>8}   med-1st")


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    sess = load(connect(symbol="MNQ"))
    n_all = sum(1 for d in sess if len(sess[d]) >= 240)
    print(f"MNQ {n_all} sessions — ALL of them, including the ~54% that go nowhere.")
    print("ENTRY |net from open| >= T, no return to open since. STOP price returns to open.")
    print("EXIT before next US open. 2 lots. Fully causal — nothing looks forward.\n")

    print("A. THE THRESHOLD — how far must it move before we believe it?")
    print(HDR)
    for thr in (30, 50, 75, 100, 150, 200):
        c, o, p = run(sess, thr)
        rep(c, p, f"  net >= {thr}pt")

    print("\nB. CONTROLS — identical fires, direction replaced")
    print(HDR)
    c, o, p = run(sess, 75)
    base = rep(c, p, "  FOLLOW the tape")
    for m, lab in (("long", "  always LONG"), ("short", "  always SHORT")):
        c2, o2, p2 = run(sess, 75, mode=m)
        rep(c2, p2, lab)
    rs = []
    for s in (1, 2, 3, 4, 5):
        c2, o2, p2 = run(sess, 75, mode="rand", seed=s)
        rs.append(rep(c2, p2, f"  RANDOM (seed {s})"))
    rs = [x for x in rs if x is not None]
    if rs and base is not None:
        print(f"\n  random mean ${statistics.mean(rs):.0f}  sd ${statistics.pstdev(rs):.0f}  "
              f"-> FOLLOW at ${base:.0f} is {(base-statistics.mean(rs))/(statistics.pstdev(rs) or 1):+.2f} sd")
        print("  ★ THIS IS THE VERDICT. Under ~+1.5 sd the detector is not calling direction.")

    print("\nC. A BUFFER BELOW THE OPEN — does giving the stop room help?")
    print(HDR)
    for b in (0, 25, 50):
        c2, o2, p2 = run(sess, 75, buffer_pt=b)
        rep(c2, p2, f"  stop = open -{b}pt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
