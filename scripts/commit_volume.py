#!/usr/bin/env python3
"""COMMIT DETECTOR + VOLUME — is a real commitment distinguishable by PARTICIPATION?

Operator, 2026-08-05: "yes run volume."

★ WHERE THIS SITS. The prize is established and survives every test so far: 18 of 39 MNQ sessions are
directional, the median one still has 416pt available at the moment it commits (~90% of the move),
commits cluster 13:31-13:42, both directions, ~$31,871 total on 2 lots (drift_rider.py's day table).
What is NOT established is calling it LIVE. Every price-only detector fails the same way — 72-86% of
fires are false, because "moved 75pt from the open" cannot separate a commitment from a chop cross that
comes back. commit_detector.py's best version reached +1.61 sd and then failed all three robustness
tests: two days were 49% of the result, 3 of 30 coin flips beat it, and the first half of the sample
lost money.

★ WHY VOLUME IS THE RIGHT NEXT LEVER AND NOT JUST ANOTHER THRESHOLD. Every detector so far reads price
alone — distance, path efficiency, clock. Volume is a DIFFERENT INFORMATION SOURCE: a genuine
directional commitment should carry participation, and a drift across a level in thin tape should not.
It is also sitting unused in the bars table, which is the cheapest untried thing on the list.

★★ PRE-REGISTERED PASS BAR, FIXED BEFORE LOOKING AT ANY OUTPUT. I have now tried roughly twenty
configurations across four scripts. At that many looks a +1.6 sd result is expected by chance, so the
bar has to be set in advance and in writing or it is meaningless:

    1. strip-best-3-days must stay POSITIVE  (the previous best went to -$2,513)
    2. beaten by <= 1 of 30 random-direction seeds  (previous: 3 of 30)
    3. BOTH sample halves positive              (previous: first half -$972)
    4. and it must beat always-LONG and always-SHORT

Anything less is reported as a FAILURE, however good the headline looks. All four, or it is nothing.

★ RVOL IS COMPUTED CAUSALLY. The same-clock-window volume baseline uses ONLY PRIOR SESSIONS — using the
full sample's average would leak the future into a live decision.

  PYTHONPATH=src .venv/bin/python scripts/commit_volume.py
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
WIN = (OPEN_M, 14 * 60 + 30)


def load(con):
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) hi, min(low) lo,
               arg_max(close, bar_ts) cl, sum(volume) v
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    out = defaultdict(list)
    for m, hi, lo, cl, v in rows:
        d = dt.datetime.fromtimestamp(int(m), dt.UTC)
        mod = d.hour * 60 + d.minute
        key = d.date() if mod >= OPEN_M else (d - dt.timedelta(days=1)).date()
        out[key].append((int(m), float(hi), float(lo), float(cl), mod, float(v or 0)))
    return out


def baselines(sess, days):
    """Cumulative volume from the open to each minute-of-day, per session — for a causal RVOL."""
    cum = {}
    for d in days:
        rows = sorted(sess[d], key=lambda x: x[0])
        c, tot = {}, 0.0
        for _ts, _h, _l, _c, mod, v in rows:
            if mod >= OPEN_M or mod < FLAT_BY:
                tot += v
                c[mod] = tot
        cum[d] = c
    return cum


def go(sess, days, cum, *, thr, er_min, rvol_min, mode="follow", seed=1):
    rnd = random.Random(seed)
    byday = {}
    for di, day in enumerate(days):
        rows = sorted(sess[day], key=lambda x: x[0])
        if len(rows) < 240:
            continue
        prior = days[max(0, di - 10):di]          # ★ ONLY prior sessions — no leakage
        o = rows[0][3]
        ent, used, dp = None, set(), []
        volsum = 0.0
        for i, (ts, hi, lo, cl, mod, v) in enumerate(rows):
            volsum += v
            if ent is not None:
                sd, epx, stp = ent
                if (lo <= stp) if sd > 0 else (hi >= stp):
                    dp.append(sd * (stp - epx) * VPP * 2 - FEE * 2)
                    ent = None
                    continue
                if FLAT_BY <= mod < OPEN_M:
                    dp.append(sd * (cl - epx) * VPP * 2 - FEE * 2)
                    ent = None
                    break
                continue
            net = cl - o
            if abs(net) < thr or not (WIN[0] <= mod <= WIN[1]):
                continue
            seg = rows[:i + 1]
            path = sum(abs(seg[j][3] - seg[j - 1][3]) for j in range(1, len(seg))) or 1e-9
            if abs(net) / path < er_min:
                continue
            if rvol_min:
                ref = [cum[p][mod] for p in prior if mod in cum.get(p, {}) and cum[p][mod] > 0]
                if len(ref) < 3:
                    continue
                if volsum / statistics.median(ref) < rvol_min:
                    continue
            sd = 1 if net > 0 else -1
            if sd in used:
                continue
            used.add(sd)
            if mode == "long":
                sd = 1
            elif mode == "short":
                sd = -1
            elif mode == "rand":
                sd = rnd.choice((1, -1))
            ent = (sd, cl, cl - sd * abs(cl - o))
        if ent is not None:
            sd, epx, _ = ent
            dp.append(sd * (rows[-1][3] - epx) * VPP * 2 - FEE * 2)
        if dp:
            byday[day] = sum(dp)
    return byday


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    sess = load(connect(symbol="MNQ"))
    days = sorted(d for d in sess if len(sess[d]) >= 240)
    cum = baselines(sess, days)
    print(f"MNQ {len(days)} sessions. RVOL = cumulative volume since the open vs the MEDIAN of the")
    print("same clock minute over the previous 10 sessions. Causal. 2 lots, stop = distance to open.\n")
    print("★ PASS BAR, FIXED IN ADVANCE: strip-best-3 positive AND beaten by <=1 of 30 seeds AND both")
    print("  halves positive AND beats always-long/always-short. All four, or it is a failure.\n")

    print(f"{'config':<30}{'days':>6}{'total':>9}{'green':>7}{'strip3':>9}")
    best = None
    for rv in (0.0, 1.0, 1.15, 1.3, 1.5):
        r = go(sess, days, cum, thr=75, er_min=0.20, rvol_min=rv)
        if not r:
            print(f"  RVOL >= {rv:.2f}                   no fires")
            continue
        t = sum(r.values())
        dd = sorted(r.values(), reverse=True)
        s3 = t - sum(dd[:3])
        g = sum(1 for v in r.values() if v > 0)
        print(f"  RVOL >= {rv:<22.2f}{len(r):>6}{t:>9.0f}{100*g/len(r):>6.0f}%{s3:>9.0f}")
        if best is None or t > best[1]:
            best = (rv, t, r)

    if not best:
        print("\nno cell fired — VERDICT: FAIL")
        return 0
    rv, tot, r = best
    print(f"\n=== FULL BATTERY on the best cell (RVOL >= {rv:.2f}) ===")
    dd = sorted(r.values(), reverse=True)
    s1, s2, s3 = tot - dd[0], tot - sum(dd[:2]), tot - sum(dd[:3])
    print(f"  total ${tot:.0f} | strip1 ${s1:.0f} | strip2 ${s2:.0f} | strip3 ${s3:.0f}")
    rs = [sum(go(sess, days, cum, thr=75, er_min=0.20, rvol_min=rv,
                 mode="rand", seed=s).values()) for s in range(1, 31)]
    m, sd = statistics.mean(rs), statistics.pstdev(rs)
    beaten = sum(1 for x in rs if x >= tot)
    print(f"  random mean ${m:.0f} sd ${sd:.0f} -> {(tot-m)/(sd or 1):+.2f} sd, beaten by {beaten}/30")
    h1, h2 = days[:len(days)//2], days[len(days)//2:]
    t1 = sum(go(sess, h1, cum, thr=75, er_min=0.20, rvol_min=rv).values())
    t2 = sum(go(sess, h2, cum, thr=75, er_min=0.20, rvol_min=rv).values())
    print(f"  first half ${t1:.0f} | second half ${t2:.0f}")
    tl = sum(go(sess, days, cum, thr=75, er_min=0.20, rvol_min=rv, mode="long").values())
    ts_ = sum(go(sess, days, cum, thr=75, er_min=0.20, rvol_min=rv, mode="short").values())
    print(f"  always LONG ${tl:.0f} | always SHORT ${ts_:.0f}")

    ok = [("strip-best-3 positive", s3 > 0), ("beaten by <=1 of 30", beaten <= 1),
          ("both halves positive", t1 > 0 and t2 > 0),
          ("beats both constants", tot > tl and tot > ts_)]
    print("\n=== VERDICT AGAINST THE PRE-REGISTERED BAR ===")
    for lab, v in ok:
        print(f"  [{'PASS' if v else 'FAIL'}] {lab}")
    print(f"\n  {'CONFIRMED' if all(v for _, v in ok) else 'NOT CONFIRMED'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
