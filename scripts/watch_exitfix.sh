#!/bin/bash
# Pings once when the exit-fix arm finishes all ten holdout days, so he does not have to ask.
# ⚠ anchored on the interpreter path — a bash script must never match its own pgrep pattern.
cd /home/alphabot/gazbot7
while true; do
  n=$(ls reports/sim_week_recursive/exitfix_hold_*.json 2>/dev/null | wc -l)
  if [ "$n" -ge 10 ]; then
    PYTHONPATH=src .venv/bin/python scripts/paired_arm.py --report-only \
      > reports/paired_arm/final.txt 2>&1
    PYTHONPATH=src .venv/bin/python - <<'PY'
import sys, datetime as dt, time
sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7.notify import notify, in_quiet_hours
txt = open("/home/alphabot/gazbot7/reports/paired_arm/final.txt").read()
keep = [l for l in txt.splitlines()
        if any(k in l for k in ("PAIRED ON", "median_hold", "premature_pct", "capture_pct",
                                "usd_per_day", "worst_day", "frozen predictions"))]
msg = "EXIT-FIX ARM DONE — champion's rules, one clause changed\n" + "\n".join(keep[:10])
while in_quiet_hours(dt.datetime.now(dt.UTC)):
    time.sleep(300)
notify(msg, critical=False, mark=False, weekend_ok=True)
print("sent")
PY
    break
  fi
  pgrep -f '[.]venv/bin/python -u scripts/paired_arm.py' >/dev/null || { sleep 600;
    pgrep -f '[.]venv/bin/python -u scripts/paired_arm.py' >/dev/null || break; }
  sleep 300
done
