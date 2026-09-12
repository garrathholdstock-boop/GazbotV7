#!/usr/bin/env python3
"""ARMED TIME AND CHURN for 2026-08-31 -> 2026-09-04, on the same definitions Part 1 §3/§10 use.

★ WHY IT IS NOT JUST THE ROUTER LOG. gate_switches.env has THREE writers — the router,
reactivate_gates.py and the open-hour watcher — and the router's trial log only records its OWN
writes. Counting armed time off the router log alone returns 7.89 gate-hours for this week and
misses the fact that exhaustion_short took a live trade at 09-03 22:59:53Z, inside an armed window
the router log does not contain. That window came from reactivate_gates, which fires at Paris
midnight (22:00Z) and re-arms every gate whose 1-day off has expired, except the HOLD set.

So both writers are replayed here, in time order, and the state machine is the union:
  · reactivate_gates 22:00Z Mon-Thu   arms abs_veto_short, capitulation_long, exhaustion_short
    (abs_veto_long and grind_long are MOMENTUM start-benched per MONDAY #2; rgv_short is HELD)
  · the router's own `changed:` dicts, from data/router_trial_log.txt
  · Friday 22:00Z is VENUE SHUT — reactivate_gates logs "already all off, nothing to do"

Denominator: 6 gates x 118 elapsed hours (Mon 00:00Z -> Fri 22:00Z) = 708 gate-hours, the same
denominator Part 1 §3 fixed in REV3. Not 720; the week is 118 hours, not 120.

  PYTHONPATH=src .venv/bin/python scripts/rev2_armed_time_w36.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import re
import subprocess

GB = "/home/alphabot/gazbot7"
OUT = f"{GB}/reports/friday_v7/sections/rev2_armed_time_w36.json"
GATES = ("grind_long", "capitulation_long", "abs_veto_long", "exhaustion_short",
         "abs_veto_short", "rgv_short")
T0 = dt.datetime(2026, 8, 31, 0, 0, tzinfo=dt.UTC)
T1 = dt.datetime(2026, 9, 4, 22, 0, tzinfo=dt.UTC)


def router_events():
    txt = pathlib.Path(f"{GB}/data/router_trial_log.txt").read_text(errors="replace")
    out = []
    for b in re.split(r"(?m)^(?=\d{4}-\d{2}-\d{2}T)", txt):
        m = re.match(r"(\S+) \| \w+ \| \w+ \| changed: ([^|]*)\|", b)
        if not m:
            continue
        ch = m.group(2).strip()
        if not ch.startswith("{"):
            continue
        try:
            d = eval(ch)                      # the router writes a python dict repr
        except Exception:
            continue
        t = dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        for g, v in d.items():
            out.append((t, g, v, "router"))
    return out


def reactivate_events():
    """From the unit's own journal, not from the script's constants — the HOLD set has changed
    three times this month and a constant read at render time is not what ran that night."""
    j = subprocess.run(["journalctl", "-u", "gazbot7-gate-reactivate", "--since", "2026-08-29",
                        "--no-pager", "-o", "short-iso"], capture_output=True, text=True).stdout
    out = []
    for ln in j.splitlines():
        if "auto-reactivated at Paris midnight" not in ln:
            continue
        ts = dt.datetime.fromisoformat(ln.split()[0])
        armed = ln.split("expired):", 1)[1].split("|")[0]
        for g in re.findall(r"[a-z_]+", armed):
            if g in GATES:
                out.append((ts.astimezone(dt.UTC), g, "on", "reactivate_gates"))
    return out


def main() -> int:
    ev = sorted([e for e in router_events() + reactivate_events() if T0 <= e[0] < T1])
    state = {g: False for g in GATES}         # the desk is benched-by-default
    since = {}
    armed = collections.defaultdict(float)
    changes = 0
    for t, g, v, who in ev:
        on = v == "on"
        if on == state[g]:                    # a WRITE that is not a CHANGE — Part 1 §10's rule
            continue
        changes += 1
        state[g] = on
        if on:
            since[g] = t
        else:
            armed[g] += (t - since.pop(g, t)).total_seconds()
    for g, t0 in since.items():
        armed[g] += (T1 - t0).total_seconds()

    hours = (T1 - T0).total_seconds() / 3600
    tot = sum(armed.values()) / 3600
    res = dict(window=[T0.isoformat(), T1.isoformat()], elapsed_hours=hours,
               gate_hours_available=6 * hours,
               armed_hours={g: round(armed[g] / 3600, 2) for g in GATES},
               armed_total_hours=round(tot, 2),
               duty_pct=round(100 * tot / (6 * hours), 2),
               value_changes=changes, churn_per_hour=round(changes / hours, 3),
               writers=collections.Counter(w for *_, w in ev))
    print(f"window {T0:%Y-%m-%d %H:%M} -> {T1:%Y-%m-%d %H:%M}Z  ({hours:.0f}h, "
          f"{6*hours:.0f} gate-hours available)")
    for g in GATES:
        print(f"  {g:20s} {armed[g]/3600:6.2f}h  ({100*armed[g]/3600/hours:5.2f}% duty)")
    print(f"  {'TOTAL':20s} {tot:6.2f}h  = {res['duty_pct']}% of available gate-time")
    print(f"  value changes {changes} = {res['churn_per_hour']}/hour   writers {dict(res['writers'])}")
    pathlib.Path(OUT).write_text(json.dumps(res, indent=1, default=str))
    print("->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
