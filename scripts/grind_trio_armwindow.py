#!/usr/bin/env python3
"""GRIND — the BREAK TRIO scored the way it is actually USED: as a once-a-session ARMING event.

The first version of this test asked "does the trio pass at the signal minute", which is the wrong
question: `open_hour_watch.py` arms ONCE per session and the gate then stays armed for the rest of
the day (the router may bench it again, but the watcher never re-arms). So the honest model is:

    scan the session minute by minute → the FIRST minute the trio passes is the ARM TIME
    → grind's fires from that minute to the end of the day are the ones the desk would have taken.

Trio legs (open_hour_watch.TREND_ER / TREND_ATR + the session-extreme test):
    last-hour ER >= 0.35 · last-hour ATR >= 18pt · price TAKES a new session extreme.

  PYTHONPATH=src:scripts .venv/bin/python scripts/grind_trio_armwindow.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.lake import connect  # noqa: E402

TREND_ER, TREND_ATR = 0.35, 18.0
SCAN_FROM, SCAN_TO = 13 * 60, 21 * 60      # the watcher's US-session window, UTC minutes

T = json.load(open("/tmp/grind_trades.json"))
con = connect()
rows = con.execute(
    "SELECT (bar_ts//60)*60 AS m, max(high) h, min(low) l, arg_max(close, bar_ts) c "
    "FROM bars WHERE symbol='MNQ' AND timeframe='5s' GROUP BY 1 ORDER BY 1").fetchall()
BY = collections.defaultdict(list)
for m, h, l, c in rows:
    BY[dt.datetime.utcfromtimestamp(m).strftime("%Y-%m-%d")].append((m, h, l, c))


def atr14(w):
    trs = []
    for k in range(1, len(w)):
        hi, lo, pc = w[k][1], w[k][2], w[k - 1][3]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return sum(trs[-14:]) / min(14, len(trs)) if trs else 0.0


arm = {}
for d, bs in BY.items():
    hi = lo = None
    for i, (m, h, l, c) in enumerate(bs):
        hi = h if hi is None else max(hi, h)
        lo = l if lo is None else min(lo, l)
        mod = dt.datetime.utcfromtimestamp(m).hour * 60 + dt.datetime.utcfromtimestamp(m).minute
        if not (SCAN_FROM <= mod <= SCAN_TO) or i < 60:
            continue
        w = bs[i - 59:i + 1]
        cl = [b[3] for b in w]
        path = sum(abs(cl[k] - cl[k - 1]) for k in range(1, len(cl))) or 1
        er = abs(cl[-1] - cl[0]) / path
        a = atr14(w)
        new_ext = (c >= hi - 0.25) or (c <= lo + 0.25)
        if er >= TREND_ER and a >= TREND_ATR and new_ext:
            arm[d] = m
            break

days = sorted({t["day"] for t in T})
print(f"THE BREAK TRIO AS A ONCE-A-SESSION ARM · scan 13:00-21:00 UTC · {len(BY)} tape-days")
print(f"trio ever passed on {len(arm)} of {len(BY)} tape-days "
      f"({len([d for d in days if d in arm])} of the {len(days)} days grind actually signalled)\n")

kept, dropped = [], []
for t in T:
    (kept if (t["day"] in arm and t["ts"] >= arm[t["day"]]) else dropped).append(t)


def line(tag, sel):
    if not sel:
        print(f"  {tag:38s} n=  0")
        return
    net = sum(x["usd"] for x in sel)
    print(f"  {tag:38s} n={len(sel):4d}  net=${net:>9,.0f}  $/tr={net/len(sel):>7.1f}  "
          f"win={100*sum(1 for x in sel if x['usd']>0)/len(sel):4.1f}%")


line("BASE — every grind fire", T)
line("ARMED by the trio (fires after arm)", kept)
line("BENCHED by the trio (never armed)", dropped)

print("\nper-day: arm time vs what grind's fires were worth that day")
byday = collections.defaultdict(list)
for t in T:
    byday[t["day"]].append(t)
for d in sorted(byday):
    fires = byday[d]
    a = arm.get(d)
    at = dt.datetime.utcfromtimestamp(a).strftime("%H:%M") if a else "  —  "
    after = [x for x in fires if a and x["ts"] >= a]
    before = [x for x in fires if not a or x["ts"] < a]
    print(f"  {d}  trio arms {at}  fires={len(fires):2d}  "
          f"day=${sum(x['usd'] for x in fires):>8,.0f}   "
          f"armed n={len(after):2d} ${sum(x['usd'] for x in after):>8,.0f}   "
          f"missed n={len(before):2d} ${sum(x['usd'] for x in before):>8,.0f}")
