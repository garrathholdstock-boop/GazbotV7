#!/usr/bin/env python3
"""CONFIRMATION DELAY vs GIVEBACK — how long should we wait before believing the break?

Operator, 2026-08-05: "what about we wait 60 minutes after we think its a trend to confirm. surely
thats enough? we obviously give back $. do a sweep on the number of minutes we need to confirm vs the
giveback to find 1. if its possible and 2. the best combination minimising give back."

★ WHY THIS IS THE RIGHT QUESTION TO ASK NOW. The Market Profile initial-balance extension is the first
signal in this whole line of work with a real DIRECTION edge: +3.88 sd against 30 random-direction
seeds, beaten by 0 of 30, and it beats always-long and always-short by ~$12,000. It still nets only
$441, because the stop sits at the opposite side of the IB — it is right about direction and hands the
money back. So the problem has moved from "can we call it" to "how do we hold it", and confirmation
delay is the cleanest lever: it should kill the false breaks that cause the stop-outs.

★ THE TRADE-OFF IS REAL AND BOTH SIDES ARE MEASURED HERE, which is what the operator asked for:
    GAIN  waiting discards breaks that fail inside the window — fewer stop-outs
    COST  waiting means entering later, so part of the move is already gone (the GIVEBACK column)
There must be an optimum, and it is an empirical question, not a matter of taste.

★ CONFIRMATION IS DEFINED AS "STILL INTACT", not "gone further". At T+N price must still be beyond the
IB edge it broke. Requiring further extension would be a second momentum bet layered on the first and
would confound the test.

★★ PRE-REGISTERED BAR, unchanged from commit_volume.py so results stay comparable across ~25
configurations already tried. All four or it is a failure:
    1. strip-best-3 days positive
    2. beaten by <= 1 of 30 random-direction seeds
    3. both sample halves positive
    4. beats always-long and always-short

  PYTHONPATH=src .venv/bin/python scripts/confirm_sweep.py
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
OPEN_M, IB_END, FLAT_BY = 13 * 60 + 30, 14 * 60 + 30, 13 * 60 + 15


def load():
    con = connect(symbol="MNQ")
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) hi, min(low) lo,
               arg_max(close, bar_ts) cl
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    sess = defaultdict(list)
    for m, hi, lo, cl in rows:
        d = dt.datetime.fromtimestamp(int(m), dt.UTC)
        mod = d.hour * 60 + d.minute
        k = d.date() if mod >= OPEN_M else (d - dt.timedelta(days=1)).date()
        sess[k].append((int(m), float(hi), float(lo), float(cl), mod))
    return sess


def go(sess, days, *, wait, ib_ratio=1.20, stop_mode="ib", stop_pt=0.0,
       mode="follow", seed=1):
    """Signal = tight-IB range extension. Then WAIT `wait` minutes and require it still intact."""
    rnd = random.Random(seed)
    byday, gives = {}, []
    ib = {}
    for d in days:
        r = [x for x in sorted(sess[d]) if OPEN_M <= x[4] <= IB_END]
        if len(r) >= 30:
            ib[d] = (max(x[1] for x in r), min(x[2] for x in r))
    dl = [d for d in days if d in ib]
    for di, d in enumerate(dl):
        prior = [p for p in dl[max(0, di - 10):di] if p in ib]
        if len(prior) < 3:
            continue
        ibh, ibl = ib[d]
        ref = statistics.median([ib[p][0] - ib[p][1] for p in prior])
        if ref <= 0 or (ibh - ibl) / ref > ib_ratio:
            continue
        rows = sorted(sess[d])
        # 1. find the break
        sig = None
        for ts, hi, lo, cl, mod in rows:
            if mod <= IB_END:
                continue
            if hi > ibh:
                sig = (1, ibh, mod)
                break
            if lo < ibl:
                sig = (-1, ibl, mod)
                break
        if sig is None:
            continue
        sd0, lvl, sig_mod = sig
        # 2. WAIT, then require it STILL INTACT (not further — that would be a second bet)
        ent = None
        for ts, hi, lo, cl, mod in rows:
            if mod < sig_mod + wait:
                continue
            if (cl > lvl) if sd0 > 0 else (cl < lvl):
                sd = sd0
                if mode == "long":
                    sd = 1
                elif mode == "short":
                    sd = -1
                elif mode == "rand":
                    sd = rnd.choice((1, -1))
                stop = (ibl if sd0 > 0 else ibh) if stop_mode == "ib" else cl - sd * stop_pt
                ent = (sd, cl, stop)
                gives.append(sd0 * (cl - lvl))     # GIVEBACK: points conceded by waiting
            break                                   # one look, at T+wait — no re-trying all day
        if ent is None:
            continue
        sd, epx, stop = ent
        dp = None
        for ts, hi, lo, cl, mod in rows:
            if mod <= sig_mod + wait:
                continue
            if (lo <= stop) if sd > 0 else (hi >= stop):
                dp = sd * (stop - epx) * VPP * 2 - FEE * 2
                break
            if FLAT_BY <= mod < OPEN_M:
                dp = sd * (cl - epx) * VPP * 2 - FEE * 2
                break
        if dp is None:
            dp = sd * (rows[-1][3] - epx) * VPP * 2 - FEE * 2
        byday[d] = dp
    return byday, gives


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    sess = load()
    days = sorted(d for d in sess if len(sess[d]) >= 240)
    print(f"MNQ {len(days)} sessions. Signal = tight-IB extension. Then wait N min and require the")
    print("break STILL INTACT. Stop = opposite IB side. 2 lots. Flat before the next US open.\n")
    print(f"{'wait':>6}{'days':>6}{'total':>9}{'$/day':>8}{'green':>7}"
          f"{'strip3':>9}{'med giveback':>14}")
    best = None
    for w in (0, 5, 15, 30, 45, 60, 90, 120):
        b, gv = go(sess, days, wait=w)
        if not b:
            print(f"{w:>5}m   no fires")
            continue
        t = sum(b.values())
        dd = sorted(b.values(), reverse=True)
        s3 = t - sum(dd[:3])
        g = sum(1 for v in b.values() if v > 0)
        gvm = statistics.median(gv) if gv else 0.0
        print(f"{w:>5}m{len(b):>6}{t:>9.0f}{t/len(b):>8.0f}{100*g/len(b):>6.0f}%"
              f"{s3:>9.0f}{gvm:>11.0f}pt")
        if best is None or t > best[1]:
            best = (w, t, b)

    print("\n★ GIVEBACK is the points already gone at the moment we finally enter — the cost of")
    print("  waiting, measured rather than assumed.")

    if not best:
        print("\nno cell fired — VERDICT: FAIL")
        return 0
    w, tot, b = best
    print(f"\n=== FULL BATTERY on wait={w}m ===")
    dd = sorted(b.values(), reverse=True)
    s3 = tot - sum(dd[:3])
    rs = [sum(go(sess, days, wait=w, mode="rand", seed=s)[0].values()) for s in range(1, 31)]
    m, sd = statistics.mean(rs), statistics.pstdev(rs)
    beat = sum(1 for x in rs if x >= tot)
    h1, h2 = days[:len(days)//2], days[len(days)//2:]
    t1 = sum(go(sess, h1, wait=w)[0].values())
    t2 = sum(go(sess, h2, wait=w)[0].values())
    tl = sum(go(sess, days, wait=w, mode="long")[0].values())
    ts_ = sum(go(sess, days, wait=w, mode="short")[0].values())
    print(f"  total ${tot:.0f}  strip1 ${tot-dd[0]:.0f}  strip3 ${s3:.0f}")
    print(f"  random mean ${m:.0f} sd ${sd:.0f} -> {(tot-m)/(sd or 1):+.2f} sd, beaten by {beat}/30")
    print(f"  halves ${t1:.0f} / ${t2:.0f}    always LONG ${tl:.0f}  SHORT ${ts_:.0f}")
    ok = [("strip-best-3 positive", s3 > 0), ("beaten by <=1 of 30", beat <= 1),
          ("both halves positive", t1 > 0 and t2 > 0),
          ("beats both constants", tot > tl and tot > ts_)]
    print()
    for lab, v in ok:
        print(f"  [{'PASS' if v else 'FAIL'}] {lab}")
    print(f"\n  {'CONFIRMED' if all(v for _, v in ok) else 'NOT CONFIRMED'}")

    print(f"\n=== and does a TIGHTER stop help, now that confirmation filters the breaks? ===")
    print(f"{'stop':>10}{'days':>6}{'total':>9}{'green':>7}{'strip3':>9}")
    for sp in (0, 50, 75, 100, 150):
        b2, _ = go(sess, days, wait=w, stop_mode=("ib" if sp == 0 else "pt"), stop_pt=sp)
        if not b2:
            continue
        t2_ = sum(b2.values())
        dd2 = sorted(b2.values(), reverse=True)
        g2 = sum(1 for v in b2.values() if v > 0)
        lab = "opposite IB" if sp == 0 else f"{sp}pt"
        print(f"{lab:>10}{len(b2):>6}{t2_:>9.0f}{100*g2/len(b2):>6.0f}%{t2_-sum(dd2[:3]):>9.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
