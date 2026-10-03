#!/usr/bin/env python3
"""Telegram the 17-18 Sept recreate result against HIS OWN numbers on the same days.

⚠ Side-accuracy and leg capture, not P&L — the simulator is confined to 06:00-13:30Z and on
2026-09-18 that window held only 36% of his money (his +$434 came at 13:55, +$338 at 02:37,
+$414 at 04:50). It cannot match his total on that day even reading the day perfectly, so comparing
totals would be comparing two different questions. 09-17 was 88% in-window and is the fairer test.
⚠ weekend_ok=True or Saturday's filter drops it; no critical=True because a backtest result does not
matter at 3am. Holds past quiet hours if it lands there.
"""
import json, os, sys, time, datetime as dt
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.notify import notify, in_quiet_hours      # noqa: E402

OUT = "/home/alphabot/gazbot7/reports/sim_week_recursive"
HIS = {"2026-09-17": (1478, 8, "7 of 8", "41%"), "2026-09-18": (1546, 15, "13 of 15", "23%")}

L = ["🧪 RECREATE 17-18 SEPT — his two best days, shape-first context"]
for d, (hp, hn, hside, hcap) in HIS.items():
    f = f"{OUT}/v2_both_w1_{d}.json"
    if not os.path.exists(f):
        L.append(f"{d}: no result written")
        continue
    r = json.load(open(f))
    t = r["trades"]
    L.append(f"{d}: ${r['net_usd']:+,.0f} over {len(t)} trades   "
             f"(he made ${hp:+,} over {hn}, side {hside}, captured {hcap})")
    if t:
        L.append(f"   longest hold {max(x['held_min'] for x in t):.0f}min · "
                 f"biggest trade {max(abs(x['points']) for x in t):.0f}pt")
L += ["", "⚠ judge the SIDE and the CAPTURE, not the total — the sim is capped at 06:00-13:30Z and "
          "on 09-18 that window held only 36% of his money.",
      "detail: reports/sim_week_recursive/"]
msg = "\n".join(L)

held = False
while in_quiet_hours(dt.datetime.now(dt.UTC)):
    held = True
    time.sleep(300)
if held:
    msg += "\n(held until after quiet hours)"
print(f"sent={notify(msg, critical=False, mark=False, weekend_ok=True)}\n{msg}")
