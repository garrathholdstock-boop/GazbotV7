#!/usr/bin/env python3
"""Telegram the recursive loop's verdict — the HOLDOUT curve, never the training curve."""
import json, os, sys, time, datetime as dt
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.notify import notify, in_quiet_hours      # noqa: E402
H = "/home/alphabot/gazbot7/reports/recursive_loop/history.json"
if not os.path.exists(H):
    print("no history"); raise SystemExit(0)
h = json.load(open(H))
won = [x for x in h if x["met"]]
L = [("★★★ IT NAILED IT — holdout cleared all four bars on iteration "
      f"{won[-1]['iter']}" if won else f"🔁 RECURSIVE LOOP — {len(h)} iteration(s), bar not met")]
for x in h:
    L.append(f"it{x['iter']}: train ${x['train']['net_usd']:+,.0f} | HOLDOUT "
             f"${x['holdout']['net_usd']:+,.0f} side {x['holdout']['side_accuracy']} "
             f"cap {x['holdout']['capture']} {x['holdout']['trades_per_day']}/day"
             + ("  ★MET" if x["met"] else ""))
L += ["", "⚠ READ THE HOLDOUT. A rising train line with a flat holdout is memorising the week, not "
          "learning the method. His own bar: side 0.85-0.88, capture 0.23-0.41, 8-15 entries."]
msg = "\n".join(L)
held = False
while in_quiet_hours(dt.datetime.now(dt.UTC)):
    held = True; time.sleep(300)
if held: msg += "\n(held until after quiet hours)"
print(f"sent={notify(msg, critical=False, mark=False, weekend_ok=True)}\n{msg}")
