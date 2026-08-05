#!/usr/bin/env python3
"""DAY RIDER — buy at the detection point, ride to the Paris close, sell when price stalls at VWAP.

Operator, 2026-08-05, specifying it properly: "we buy at day detection point. 2 lots. and we sell at
the highest point towards the 23hr paris close. obviously hard to know what this is. but if price starts
hovering around vwap we market sell."

★ THIS SUPERSEDES THE OVERNIGHT VERSIONS, AND IT FIXES A BUG BY DESIGN. commit_detector /
commit_volume / confirm_sweep all held to 13:15 the NEXT day. Their exit loops skipped pre-decision
bars with `if mod <= T: continue` — and every overnight bar has a MINUTE-OF-DAY numerically smaller
than T (01:00 = 60 vs T = 820), so all ~795 overnight minutes were skipped and those positions held
all night WITH THE STOP NEVER EVALUATED. That is why "hold to next open" printed $8,118 against
$1,610 for a same-day exit: it was not overnight edge, it was an unstoppable position. Flat by 21:00
UTC removes the whole class of error — there is no overnight to mis-handle.

★ 23:00 PARIS = 21:00 UTC in summer, which is also the CME daily maintenance halt. Flat before it is
the correct desk behaviour anyway, so the operator's exit clock and the venue's agree.

★ THE VWAP STALL IS THE REAL IDEA AND IT IS WHAT WAS MISSING. A fixed clock sells at an arbitrary
minute. "Hovering around VWAP" sells when the trend has stopped paying: on a genuine trend day price
runs away from VWAP and stays away, so a return to it is the thesis expiring. Two readings are tested —
a single TOUCH of VWAP, and true HOVERING (inside k x ATR of VWAP for M consecutive minutes), which is
the stricter and more literal reading of what the operator described.

★ PEAK CAPTURE IS REPORTED, because "sell at the highest point" cannot be done without hindsight and
the honest question is how close a rule gets. peak% = what fraction of the best available excursion
the exit actually banked.

  PYTHONPATH=src .venv/bin/python scripts/day_rider.py
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
OPEN_M = 13 * 60 + 30
CLOSE_M = 21 * 60            # 23:00 Paris = 21:00 UTC = the CME halt


def load():
    con = connect(symbol="MNQ")
    rows = con.execute("""
        SELECT CAST(bar_ts/60 AS BIGINT)*60 m, max(high) hi, min(low) lo,
               arg_max(close, bar_ts) cl, sum(volume) v
        FROM bars WHERE timeframe='5s' GROUP BY 1 ORDER BY 1""").fetchall()
    sess = defaultdict(list)
    for m, hi, lo, cl, v in rows:
        d = dt.datetime.fromtimestamp(int(m), dt.UTC)
        mod = d.hour * 60 + d.minute
        if OPEN_M <= mod <= CLOSE_M:            # ★ intraday only — no overnight, no wrap, no bug
            sess[d.date()].append((int(m), float(hi), float(lo), float(cl), mod, float(v or 0)))
    return sess


def run(sess, days, *, decide=10, er_min=0.15, rt_min=0.45, stop_pt=150,
        exit_rule="hover", hov_k=0.5, hov_min=5, mode="follow", seed=1):
    rnd = random.Random(seed)
    byday, whys, peaks = {}, defaultdict(int), []
    for d in days:
        rows = sorted(sess[d])
        if len(rows) < 240:
            continue
        o = rows[0][3]
        T = OPEN_M + decide
        seg = [x for x in rows if x[4] <= T]
        if len(seg) < 10:
            continue
        net = seg[-1][3] - o
        rng = max(x[1] for x in seg) - min(x[2] for x in seg)
        path = sum(abs(seg[j][3] - seg[j - 1][3]) for j in range(1, len(seg))) or 1e-9
        if rng <= 0 or abs(net) / path < er_min or abs(net) / rng < rt_min:
            continue
        sd = 1 if net > 0 else -1
        if mode == "long":
            sd = 1
        elif mode == "short":
            sd = -1
        elif mode == "rand":
            sd = rnd.choice((1, -1))
        ei = len(seg) - 1
        epx = seg[-1][3]
        stop = epx - sd * stop_pt
        # rolling VWAP anchored at the US open, and ATR, both causal
        pv = sum(x[3] * x[5] for x in seg)
        vv = sum(x[5] for x in seg) or 1e-9
        trs = [max(seg[j][1] - seg[j][2], abs(seg[j][1] - seg[j - 1][3]),
                   abs(seg[j][2] - seg[j - 1][3])) for j in range(1, len(seg))]
        atr = (sum(trs) / len(trs)) if trs else 20.0
        best = epx
        hov = 0
        exit_px, why = None, None
        for ts, hi, lo, cl, mod, v in rows[ei + 1:]:
            pv += cl * v
            vv += v
            vwap = pv / vv
            best = max(best, hi) if sd > 0 else min(best, lo)
            if (lo <= stop) if sd > 0 else (hi >= stop):
                exit_px, why = stop, "stop"
                break
            if exit_rule == "touch" and ((lo <= vwap) if sd > 0 else (hi >= vwap)):
                exit_px, why = vwap, "vwap touch"
                break
            if exit_rule == "hover":
                # HOVERING: price sitting inside k*ATR of VWAP for M consecutive minutes = the
                # trend has stopped running away from fair value, which is the thesis expiring.
                hov = hov + 1 if abs(cl - vwap) <= hov_k * atr else 0
                if hov >= hov_min:
                    exit_px, why = cl, "vwap hover"
                    break
            if mod >= CLOSE_M:
                exit_px, why = cl, "21:00 close"
                break
        if exit_px is None:
            exit_px, why = rows[-1][3], "21:00 close"
        pnl = sd * (exit_px - epx) * VPP * 2 - FEE * 2
        byday[d] = pnl
        whys[why] += 1
        avail = sd * (best - epx)
        if avail > 0:
            peaks.append(max(0.0, sd * (exit_px - epx)) / avail)
    return byday, whys, peaks


def rep(b, w, p, lab):
    if not b:
        print(f"{lab:<26}   no fires")
        return None
    t = sum(b.values())
    dd = sorted(b.values(), reverse=True)
    g = sum(1 for v in b.values() if v > 0)
    pk = 100 * statistics.mean(p) if p else 0
    print(f"{lab:<26}{len(b):>5}{t:>9.0f}{t/len(b):>8.0f}{100*g/len(b):>6.0f}%"
          f"{t-sum(dd[:3]):>9.0f}{pk:>8.0f}%")
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    sess = load()
    days = sorted(d for d in sess if len(sess[d]) >= 240)
    print(f"MNQ {len(days)} sessions, intraday only 13:30-21:00 UTC (= 23:00 Paris / CME halt).")
    print("Entry: open+10min if efficiency>=0.15 and roundtrip>=0.45, direction of net, 2 lots.\n")
    print(f"{'exit rule':<26}{'days':>5}{'total':>9}{'$/day':>8}{'green':>7}{'strip3':>9}{'peak%':>8}")
    cands = {}
    b, w, p = run(sess, days, exit_rule="clock")
    cands["clock"] = (rep(b, w, p, "21:00 clock only"), dict(exit_rule="clock"))
    b, w, p = run(sess, days, exit_rule="touch")
    cands["touch"] = (rep(b, w, p, "sell on VWAP touch"), dict(exit_rule="touch"))
    for k in (0.3, 0.5, 0.8):
        for mn in (3, 5, 10):
            b, w, p = run(sess, days, exit_rule="hover", hov_k=k, hov_min=mn)
            cands[f"h{k}_{mn}"] = (rep(b, w, p, f"hover <{k}xATR for {mn}min"),
                                   dict(exit_rule="hover", hov_k=k, hov_min=mn))
    print("\npeak% = share of the best available move the exit actually banked ('sell the high'")
    print("        is impossible without hindsight; this is how close each rule gets).")

    nm, (tot, kw) = max(((k, v) for k, v in cands.items() if v[0] is not None),
                        key=lambda kv: kv[1][0])
    print(f"\n=== BATTERY on the best exit ({nm}) ===")
    b, w, p = run(sess, days, **kw)
    dd = sorted(b.values(), reverse=True)
    s3 = tot - sum(dd[:3])
    print("  exit reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(w.items())))
    rs = [sum(run(sess, days, mode="rand", seed=s, **kw)[0].values()) for s in range(1, 31)]
    m, sd = statistics.mean(rs), statistics.pstdev(rs)
    beat = sum(1 for x in rs if x >= tot)
    h1, h2 = days[:len(days)//2], days[len(days)//2:]
    t1 = sum(run(sess, h1, **kw)[0].values())
    t2 = sum(run(sess, h2, **kw)[0].values())
    tl = sum(run(sess, days, mode="long", **kw)[0].values())
    ts_ = sum(run(sess, days, mode="short", **kw)[0].values())
    print(f"  total ${tot:.0f}  strip1 ${tot-dd[0]:.0f}  strip3 ${s3:.0f}")
    print(f"  random mean ${m:.0f} sd ${sd:.0f} -> {(tot-m)/(sd or 1):+.2f} sd, beaten by {beat}/30")
    print(f"  halves ${t1:.0f} / ${t2:.0f}   always LONG ${tl:.0f}  SHORT ${ts_:.0f}")
    ok = [("strip-best-3 positive", s3 > 0), ("beaten by <=1 of 30", beat <= 1),
          ("both halves positive", t1 > 0 and t2 > 0),
          ("beats both constants", tot > tl and tot > ts_)]
    print()
    for lab, v in ok:
        print(f"  [{'PASS' if v else 'FAIL'}] {lab}")
    print(f"\n  {'CONFIRMED' if all(v for _, v in ok) else 'NOT CONFIRMED'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
