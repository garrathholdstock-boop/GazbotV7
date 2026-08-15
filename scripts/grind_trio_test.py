#!/usr/bin/env python3
"""GRIND — SCORE THE ARMING MECHANISM THAT IS ACTUALLY DEPLOYED (the BREAK TRIO).

The standing lead asks whether grind should be enabled by (a) trend-day-only, (b) its own entry
trend-confirm, or (c) "the current ER-0.35 floor". (c) does not exist as a gate filter —
`deciders.ER_FLOOR` is `{}`. Where 0.35 DOES live is `scripts/open_hour_watch.py`'s BREAK TRIO,
the once-a-session arming test:

    last-hour ER >= 0.35   AND   last-hour ATR >= 18pt   AND   a NEW session extreme is TAKEN

So this scores the trio itself, leg by leg, against the tick-honest grind book — the honest
version of question (c), plus the two legs measured separately so we can see which one binds.

  PYTHONPATH=src:scripts .venv/bin/python scripts/grind_trio_test.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import random
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

TREND_ER, TREND_ATR = 0.35, 18.0
T = json.load(open("/tmp/grind_trades.json"))
random.seed(20260814)

con = connect()
rows = con.execute(
    "SELECT (bar_ts//60)*60 AS m, max(high) h, min(low) l, arg_max(close, bar_ts) c "
    "FROM bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1 ORDER BY 1").fetchall()
BY = collections.defaultdict(list)
for m, h, l, c in rows:
    BY[dt.datetime.utcfromtimestamp(m).strftime("%Y-%m-%d")].append((m, h, l, c))

IDX = {d: {m: i for i, (m, _h, _l, _c) in enumerate(bs)} for d, bs in BY.items()}

for t in T:
    bs = BY[t["day"]]
    i = IDX[t["day"]][(t["ts"] // 60) * 60]
    w = bs[max(0, i - 59):i + 1]
    cl = [b[3] for b in w]
    path = sum(abs(cl[k] - cl[k - 1]) for k in range(1, len(cl))) or 1
    t["er60"] = abs(cl[-1] - cl[0]) / path
    sofar = bs[:i + 1]
    t["ses_hi"] = max(b[1] for b in sofar)
    t["ses_lo"] = min(b[2] for b in sofar)
    t["new_extreme"] = t["px"] >= t["ses_hi"] - 0.25


def rep(tag, sel):
    n = len(sel)
    if not n:
        print(f"  {tag:44s} n=  0  — the mechanism never lets grind fire at all")
        return
    net = sum(x["usd"] for x in sel)
    byday = collections.defaultdict(float)
    for x in sel:
        byday[x["day"]] += x["usd"]
    strip3 = net - sum(sorted((x["usd"] for x in sel), reverse=True)[:3])
    top10 = sorted(T, key=lambda r: -r["usd"])[:10]
    keeps = sum(1 for x in top10 if x in sel)
    draws = [sum(x["usd"] for x in random.sample(T, n)) for _ in range(400)]
    beat = sum(1 for d in draws if d >= net)
    print(f"  {tag:44s} n={n:4d}  net=${net:>9,.0f}  $/tr={net/n:>7.1f}  "
          f"win={100*sum(1 for x in sel if x['usd']>0)/n:4.1f}%  strip3=${strip3:>8,.0f}  "
          f"top10kept={keeps:2d}  placebo≥{beat:3d}/400")


print("=" * 118)
print(f"THE BREAK TRIO AS GRIND'S ENABLE MECHANISM — tick-honest live-managed book, "
      f"n={len(T)} fires over {len({t['day'] for t in T})} days")
print("=" * 118)
rep("BASE — every fire (ATR>=22 only)", T)
rep("leg 1 alone: last-hr ER >= 0.35", [t for t in T if t["er60"] >= TREND_ER])
rep("leg 2 alone: last-hr ATR >= 18", [t for t in T if t["atr"] >= TREND_ATR])
rep("leg 3 alone: new session extreme", [t for t in T if t["new_extreme"]])
rep("FULL TRIO (all three legs)",
    [t for t in T if t["er60"] >= TREND_ER and t["atr"] >= TREND_ATR and t["new_extreme"]])
rep("trio minus the ER leg (ATR + extreme)",
    [t for t in T if t["atr"] >= TREND_ATR and t["new_extreme"]])
rep("trio with ER >= 0.20 instead of 0.35",
    [t for t in T if t["er60"] >= 0.20 and t["atr"] >= TREND_ATR and t["new_extreme"]])

print("\nER-60 SWEEP inside the trio (ATR>=18 + new extreme held constant)")
for er in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
    rep(f"  trio, ER >= {er:.2f}",
        [t for t in T if t["er60"] >= er and t["atr"] >= TREND_ATR and t["new_extreme"]])

print("\nTHE VETO ARM for comparison (no ER anywhere): "
      "skip a long fighting a 30-min down-move")
rep("net30 >= -1.0xATR", [t for t in T if t["net30"] >= -1.0 * t["atr"]])
rep("net30 >= -1.0xATR AND in the top 40% of the hour",
    [t for t in T if t["net30"] >= -1.0 * t["atr"]
     and (t["px"] - t["lo60"]) / max(1e-9, t["hi60"] - t["lo60"]) >= 0.6])
