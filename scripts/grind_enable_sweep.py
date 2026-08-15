#!/usr/bin/env python3
"""GRIND ENABLE-MECHANISM — the SWEEP. Every threshold is an operator guess until it is swept,
so each mechanism is scanned across its whole range and judged on PLATEAU vs spike, with
strip-3 / leave-one-day-out / placebo attached to every cell.

Reads /tmp/grind_trades.json (written by grind_enable_mechanism.py).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import random
import statistics
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

T = json.load(open("/tmp/grind_trades.json"))
random.seed(20260814)


def day_context():
    con = connect()
    rows = con.execute(
        "SELECT (bar_ts//60)*60 AS m, arg_min(open, bar_ts) o, max(high) h, min(low) l, "
        "arg_max(close, bar_ts) c FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
        "GROUP BY 1 ORDER BY 1").fetchall()
    days = collections.defaultdict(list)
    for m, o, h, lo, c in rows:
        days[dt.datetime.utcfromtimestamp(m).strftime("%Y-%m-%d")].append((m, o, h, lo, c))
    ctx = {}
    for d, bs in days.items():
        run, opens = {}, bs[0][1]
        hi = lo = bs[0][4]
        absmove, prev = 0.0, bs[0][4]
        for m, o, h, l, c in bs:
            hi, lo = max(hi, h), min(lo, l)
            absmove += abs(c - prev)
            prev = c
            run[m] = (abs(c - opens) / absmove if absmove else 0.0, hi - lo, c - opens)
        ctx[d] = run
    return ctx


CTX = day_context()
for t in T:
    ser, srange, snet = CTX[t["day"]].get((t["ts"] // 60) * 60, (0.0, 0.0, 0.0))
    t["ses_er"], t["ses_range_atr"], t["ses_net"] = ser, srange / t["atr"], snet
    t["break60"] = t["px"] >= t["hi60"] - 0.25
    t["pos60"] = (t["px"] - t["lo60"]) / max(1e-9, t["hi60"] - t["lo60"])


ALL = sum(t["usd"] for t in T)


def score(keep, label, placebo=True):
    rows = [t for t in T if keep(t)]
    n = len(rows)
    if n == 0:
        return f"  {label:26s} n=  0"
    net = sum(r["usd"] for r in rows)
    win = 100 * sum(1 for r in rows if r["usd"] > 0) / n
    byday = collections.defaultdict(float)
    for r in rows:
        byday[r["day"]] += r["usd"]
    lodo = min(net - v for v in byday.values())
    strip3 = net - sum(sorted((r["usd"] for r in rows), reverse=True)[:3])
    beat = ""
    if placebo and n < len(T):
        draws = [sum(x["usd"] for x in random.sample(T, n)) for _ in range(400)]
        beat = f"{sum(1 for d in draws if d >= net):3d}/400"
    big10 = sorted(T, key=lambda r: -r["usd"])[:10]
    kept10 = sum(1 for r in big10 if keep(r))
    return (f"  {label:26s} n={n:4d}  net=${net:>9,.0f}  $/tr={net/n:>7.1f}  win={win:4.1f}%  "
            f"strip3=${strip3:>8,.0f}  LODOworst=${lodo:>8,.0f}  top10kept={kept10:2d}  placebo≥{beat}")


print("=" * 130)
print(f"BASE: n={len(T)} net=${ALL:,.0f}  ({len({t['day'] for t in T})} tick-days)")
print("=" * 130)

print("\n(a) TREND-DAY-ONLY — arm only once the SESSION SO FAR has proven efficient (causal)")
for th in [0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12]:
    print(score(lambda t, th=th: t["ses_er"] >= th, f"ses_ER >= {th:.2f}"))

print("\n(a2) TREND-DAY-ONLY — arm only once the day's RANGE has expanded (causal)")
for th in [2, 3, 4, 5, 6, 8, 10]:
    print(score(lambda t, th=th: t["ses_range_atr"] >= th, f"ses_range >= {th}xATR"))

print("\n(b) ENTRY TREND-CONFIRMATION — 15-min impulse in the trade's direction")
for k in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]:
    print(score(lambda t, k=k: t["net15"] >= k * t["atr"], f"net15 >= {k:.2f}xATR"))

print("\n(b2) ENTRY TREND-CONFIRMATION — position in the 60-min range (a break-confirm)")
for k in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
    print(score(lambda t, k=k: t["pos60"] >= k, f"pos in 60m range >= {k:.1f}"))

print("\n(b3) ENTRY VETO — skip when the 30-min net is AGAINST the long (the chop-churn veto)")
for k in [-1.0, -0.5, -0.25, 0.0, 0.25, 0.5]:
    print(score(lambda t, k=k: t["net30"] >= k * t["atr"], f"net30 >= {k:+.2f}xATR"))

print("\n(c) ER FLOOR AT ENTRY — the mechanism named in the lead (NOT deployed: ER_FLOOR is {})")
for th in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]:
    print(score(lambda t, th=th: t["er30"] >= th, f"ER30 >= {th:.2f}"))

print("\n(d) THE DEPLOYED LEVER — raise the ATR floor (what is ACTUALLY in force today)")
for th in [22, 24, 26, 28, 30, 34, 38]:
    print(score(lambda t, th=th: t["atr"] >= th, f"ATR >= {th}"))

print("\nCOMBINATION — the best-scoring day-arm with the best-scoring entry-confirm")
print(score(lambda t: t["ses_range_atr"] >= 4 and t["net15"] >= 0.2 * t["atr"],
            "range>=4xATR & net15>=0.2"))
print(score(lambda t: t["atr"] >= 26 and t["net15"] >= 0.2 * t["atr"], "ATR>=26 & net15>=0.2"))
print(score(lambda t: t["atr"] >= 26 and t["ses_range_atr"] >= 4, "ATR>=26 & range>=4xATR"))

print("\nWHERE THE MONEY IS — the base book's 10 best and 10 worst fires")
for r in sorted(T, key=lambda r: -r["usd"])[:10]:
    print(f"  +  {r['day']} {dt.datetime.utcfromtimestamp(r['ts']).strftime('%H:%M')}  "
          f"${r['usd']:>8,.1f}  ATR={r['atr']:5.1f} ER30={r['er30']:.2f} net15={r['net15']:+6.1f} "
          f"sesER={r['ses_er']:.2f} rng={r['ses_range_atr']:4.1f}xATR  mfe={r['mfe_r']:.1f}R  {r['xb']}")
for r in sorted(T, key=lambda r: r["usd"])[:10]:
    print(f"  -  {r['day']} {dt.datetime.utcfromtimestamp(r['ts']).strftime('%H:%M')}  "
          f"${r['usd']:>8,.1f}  ATR={r['atr']:5.1f} ER30={r['er30']:.2f} net15={r['net15']:+6.1f} "
          f"sesER={r['ses_er']:.2f} rng={r['ses_range_atr']:4.1f}xATR  mfe={r['mfe_r']:.1f}R  {r['xb']}")
