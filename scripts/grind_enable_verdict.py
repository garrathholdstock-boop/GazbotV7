#!/usr/bin/env python3
"""GRIND ENABLE-MECHANISM — score the four arms on the tick-honest book from
`grind_enable_mechanism.py` (/tmp/grind_trades.json).

ARMS
  BASE  deployed today: ATR>=22 + router on/off, no ER floor, no entry confirm
  (a)   TREND-DAY-ONLY — a day-level permission window, computed CAUSALLY (the day's tape
        BEFORE the entry only: session-so-far efficiency + range vs its own ATR)
  (b)   ENTRY TREND-CONFIRMATION — a per-signal directional confirm (15-min net >= k*ATR and
        price making a new 60-min high)
  (c)   ER>=0.35 floor at entry (the mechanism the lead names — and which is NOT deployed)

Every arm is scored per REGIME and per TIME-OF-DAY, then robustness-tested: leave-one-day-out,
strip-the-3-best-trades, and a placebo (drop the same NUMBER of trades at random).
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


# ── day-level CAUSAL context ────────────────────────────────────────────────────────────
def day_context():
    """For each day+minute, the session-so-far efficiency and range/ATR — all backward-looking."""
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
        run = {}
        opens = bs[0][1]
        hi = lo = bs[0][4]
        absmove = 0.0
        prev = bs[0][4]
        for m, o, h, l, c in bs:
            hi, lo = max(hi, h), min(lo, l)
            absmove += abs(c - prev)
            prev = c
            net = c - opens
            run[m] = (abs(net) / absmove if absmove else 0.0, hi - lo, net)
        ctx[d] = run
    return ctx


CTX = day_context()
for t in T:
    d, m = t["day"], (t["ts"] // 60) * 60
    ses_er, ses_range, ses_net = CTX[d].get(m, (0.0, 0.0, 0.0))
    t["ses_er"] = ses_er              # session-so-far efficiency (causal)
    t["ses_range_atr"] = ses_range / t["atr"] if t["atr"] else 0.0
    t["ses_net"] = ses_net
    t["break60"] = t["px"] >= t["hi60"] - 0.25     # at/through the 60-min high
    t["conf15"] = t["net15"] >= 0.5 * t["atr"]


# ── regime segmentation (ATR level + ER + range-break, per the standing discipline) ─────
ATRS = sorted(t["atr"] for t in T)
ATR_HI = ATRS[int(0.75 * len(ATRS))]


def regime(t):
    if t["er30"] >= 0.35:
        return "clean-trend"
    if t["atr"] >= ATR_HI and t["er30"] < 0.15:
        return "violent-whipsaw"
    if t["er30"] < 0.10:
        return "dead-chop"
    if t["er30"] < 0.20:
        return "normal-chop"
    return "in-between"


for t in T:
    t["regime"] = regime(t)
    t["tod"] = "US 13:30-21:00" if 13 <= t["hour"] < 21 else "overnight/pre-open"


def stat(rows):
    if not rows:
        return dict(n=0, net=0.0, per=0.0, win=0.0)
    net = sum(r["usd"] for r in rows)
    return dict(n=len(rows), net=net, per=net / len(rows),
                win=100 * sum(1 for r in rows if r["usd"] > 0) / len(rows))


def line(tag, rows, base_n=None):
    s = stat(rows)
    extra = f"  ({100*s['n']/base_n:.0f}% of base)" if base_n else ""
    print(f"  {tag:34s} n={s['n']:4d}  net=${s['net']:>9,.2f}  $/tr={s['per']:>7.2f}  "
          f"win={s['win']:4.1f}%{extra}")


# ── the arms ────────────────────────────────────────────────────────────────────────────
def arm_base(t):
    return True


def arm_trendday(t, er=0.18):
    return t["ses_er"] >= er


def arm_confirm(t):
    return t["conf15"] and t["break60"]


def arm_erfloor(t, er=0.35):
    return t["er30"] >= er


ARMS = [("BASE (deployed ATR>=22)", arm_base),
        ("(a) trend-day-only ses_ER>=0.18", arm_trendday),
        ("(b) entry confirm net15>=0.5ATR + 60m break", arm_confirm),
        ("(c) ER>=0.35 floor at entry", arm_erfloor)]

print("=" * 104)
print(f"GRIND_LONG — tick-honest live-managed book · n={len(T)} fires · "
      f"{len({t['day'] for t in T})} tick-days · {min(t['day'] for t in T)}..{max(t['day'] for t in T)}")
print("=" * 104)
for tag, fn in ARMS:
    line(tag, [t for t in T if fn(t)], base_n=len(T))

print("\nPER-REGIME (each arm scored only where it is ON)")
regs = ["dead-chop", "normal-chop", "in-between", "clean-trend", "violent-whipsaw"]
print(f"  {'regime':18s}" + "".join(f"{tag.split()[0]:>26s}" for tag, _ in ARMS))
for rg in regs:
    cells = []
    for tag, fn in ARMS:
        s = stat([t for t in T if t["regime"] == rg and fn(t)])
        cells.append(f"n={s['n']:3d} ${s['net']:>8,.0f} {s['per']:>7.1f}")
    print(f"  {rg:18s}" + "".join(f"{c:>26s}" for c in cells))

print("\nPER TIME-OF-DAY")
for tod in ["overnight/pre-open", "US 13:30-21:00"]:
    print(f"  --- {tod} ---")
    for tag, fn in ARMS:
        line(tag, [t for t in T if t["tod"] == tod and fn(t)])

print("\nROBUSTNESS")
for tag, fn in ARMS:
    rows = [t for t in T if fn(t)]
    if not rows:
        continue
    net = sum(r["usd"] for r in rows)
    byday = collections.defaultdict(float)
    for r in rows:
        byday[r["day"]] += r["usd"]
    lodo = [net - v for v in byday.values()]
    strip3 = net - sum(sorted((r["usd"] for r in rows), reverse=True)[:3])
    green = sum(1 for v in byday.values() if v > 0)
    print(f"  {tag:44s} net=${net:>9,.2f}  LODO worst=${min(lodo):>9,.2f} best=${max(lodo):>9,.2f}  "
          f"strip-3=${strip3:>9,.2f}  green-days {green}/{len(byday)}")

print("\nPLACEBO — drop the same NUMBER of trades at random (1000 draws)")
for tag, fn in ARMS[1:]:
    kept = [t for t in T if fn(t)]
    k = len(kept)
    real = sum(r["usd"] for r in kept)
    draws = []
    for _ in range(1000):
        draws.append(sum(r["usd"] for r in random.sample(T, k)))
    beat = sum(1 for d in draws if d >= real)
    print(f"  {tag:44s} keeps {k:3d}/{len(T)}  real=${real:>9,.2f}  "
          f"random median=${statistics.median(draws):>9,.2f}  beaten by {beat}/1000 random subsets")

print("\nWHAT EACH ARM DROPS (the fake-filter guard — does it keep the winners?)")
big = sorted(T, key=lambda r: -r["usd"])[:10]
print(f"  the 10 best fires carry ${sum(r['usd'] for r in big):,.2f} of the base's "
      f"${sum(r['usd'] for r in T):,.2f}")
for tag, fn in ARMS[1:]:
    kept = sum(1 for r in big if fn(r))
    print(f"  {tag:44s} keeps {kept}/10 of them")

print("\nDAY TABLE (base book, by day)")
byday = collections.defaultdict(list)
for t in T:
    byday[t["day"]].append(t)
for d in sorted(byday):
    rows = byday[d]
    cells = []
    for tag, fn in ARMS:
        s = stat([r for r in rows if fn(r)])
        cells.append(f"{s['n']:2d}/${s['net']:>8,.0f}")
    ses = max(r["ses_er"] for r in rows)
    print(f"  {d}  sesER_max={ses:.2f}  " + "  ".join(cells))
