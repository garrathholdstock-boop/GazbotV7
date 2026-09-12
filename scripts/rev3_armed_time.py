#!/usr/bin/env python3
"""ARMED TIME — one number per gate, with its CUT-OFF stated.

★ WHY (2026-08-30, Rev 3). The report printed three armed times for the same gate and two for
the desk, and never said where the clock stopped:
   Part 1 §3 table   capitulation_long 22h31m (18.8%)   all six 26h25m (3.7% of 720 gate-hours)
   Part 1 §3 prose / card row   17h45m   ·   plays.json  20h31m (17.10%)   desk 24h31m (3.40%)
The gap is the window that was still OPEN when the report rendered (capitulation_long went on at
Fri 22:00:00Z and never came off). "Armed time" is not a number until you say when you stopped
counting, so this prints BOTH cut-offs from ONE replay.

HOW. There is no per-tick record of switch STATE anywhere on the box — the router logs `changed:`
(a WRITE), reactivate_gates logs its arms to the systemd journal, and open_hour_watch is a third
writer. So the state is REPLAYED forward from a known start:
   START  Mon 2026-08-24 00:00:00Z, all six OFF — the 2026-08-20 operator stand-down, confirmed
          from the other side by reactivate_gates logging HELD (not auto-armed) for all six at
          22:00Z on Mon and Tue.
   EVENTS router_trial_log.txt `changed: {...}` + the gate-reactivate journal's arm lines.
⚠ HONEST LIMIT, stated rather than hidden: a write nobody logged is invisible to this replay, and
the router's own log under-reports (it is a timer, and a tick that ABORTs writes no line at all —
43 of them this week). Treat these as the best available reconstruction, not a venue record.

  python3 scripts/rev3_armed_time.py
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import re
import subprocess

TRIAL = pathlib.Path("/home/alphabot/gazbot7/data/router_trial_log.txt")
OUT = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/sections/rev3_armed_time.json")

GATES = ["grind_long", "capitulation_long", "abs_veto_long",
         "rgv_short", "exhaustion_short", "abs_veto_short"]

W0 = dt.datetime(2026, 8, 24, 0, 0, tzinfo=dt.UTC)      # Monday 00:00Z
W1 = dt.datetime(2026, 8, 28, 22, 0, tzinfo=dt.UTC)     # Friday 22:00Z — the week's own boundary
RENDER = dt.datetime(2026, 8, 29, 1, 52, tzinfo=dt.UTC)  # the Rev2 render stamp

TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z")
CH = re.compile(r"changed:\s*(\{[^}]*\})")


def events():
    ev = []
    for line in TRIAL.read_text(errors="replace").splitlines():
        m, c = TS.match(line), CH.search(line)
        if not (m and c):
            continue
        t = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.UTC)
        try:
            d = ast.literal_eval(c.group(1))
        except Exception:
            continue
        if isinstance(d, dict):
            ev.append((t, {k: v for k, v in d.items() if k in GATES}, "router"))

    out = subprocess.run(["journalctl", "-u", "gazbot7-gate-reactivate", "--no-pager",
                          "-o", "short-iso", "--since", "2026-08-23"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "gates auto-reactivated" not in line:
            continue
        t = dt.datetime.fromisoformat(line.split(maxsplit=1)[0]).astimezone(dt.UTC)
        armed = line.split("expired):", 1)[1].split("|")[0]
        d = {g: "on" for g in GATES if g in armed}
        if d:
            ev.append((t, d, "reactivate_gates"))
    # ★ THE THIRD WRITER. open-hour-watch.service's unit file says "ALERT-ONLY, must NEVER write
    # gate_switches.env" and its code writes it anyway — it ARMED abs_veto_short at 16:24:00Z on
    # Friday and stamped the file header saying so. Its arms appear in NO other log, which is why
    # a replay built from the router's log alone loses 33 minutes of a gate's only real window.
    for line in pathlib.Path("/home/alphabot/gazbot7/data/open_hour_watch.log").read_text(
            errors="replace").splitlines():
        m = TS.match(line)
        if not (m and "ARMED " in line):
            continue
        t = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.UTC)
        d = {g: "on" for g in GATES if f"ARMED {g}" in line}
        if d:
            ev.append((t, d, "open_hour_watch"))

    ev.sort(key=lambda x: x[0])
    return ev


def fmt(sec):
    return f"{int(sec // 3600)}h {int(sec % 3600 // 60):02d}m"


def main() -> int:
    ev = [e for e in events() if W0 <= e[0] < RENDER]
    res = {"start": W0.isoformat(), "start_state": "all six OFF (2026-08-20 operator stand-down)",
           "events_replayed": len(ev), "cutoffs": {}}

    for label, cut in (("week boundary — Fri 2026-08-28 22:00:00Z", W1),
                       ("render time — Sat 2026-08-29 01:52Z", RENDER)):
        state = {g: False for g in GATES}
        since = {g: None for g in GATES}
        armed = {g: 0.0 for g in GATES}
        windows = {g: [] for g in GATES}
        n_changes = n_on = n_off = 0
        for t, d, _src in ev:
            if t >= cut:
                break
            for g, v in d.items():
                on = (str(v).lower() == "on")
                if on and not state[g]:
                    state[g], since[g] = True, t
                    n_changes += 1
                    n_on += 1
                elif (not on) and state[g]:
                    n_changes += 1
                    n_off += 1
                    armed[g] += (t - since[g]).total_seconds()
                    windows[g].append(f"{since[g]:%a %H:%M}→{t:%H:%M}")
                    state[g], since[g] = False, None
        for g in GATES:
            if state[g]:
                armed[g] += (cut - since[g]).total_seconds()
                windows[g].append(f"{since[g]:%a %H:%M}→{cut:%a %H:%M} (still on at the cut)")
        tot = sum(armed.values())
        hours = (cut - W0).total_seconds() / 3600
        res.setdefault("churn", {})[label] = {
            "definition": "a CHANGE is a gate's replayed state flipping value (not a WRITE); "
                          "denominator is elapsed clock hours over the whole window",
            "changes": n_changes, "arms": n_on, "benches": n_off,
            "per_hour": round(n_changes / hours, 3),
            "changes_that_produced_a_trade": None,
        }
        res["cutoffs"][label] = {
            "cut": cut.isoformat(),
            "elapsed_h": round(hours, 2),
            "gate_hours_available": round(hours * len(GATES), 1),
            "per_gate": {g: {"armed": fmt(armed[g]), "seconds": int(armed[g]),
                             "duty_pct": round(100 * armed[g] / (hours * 3600), 2),
                             "windows": windows[g]} for g in GATES},
            "desk_armed": fmt(tot),
            "desk_seconds": int(tot),
            "desk_pct_of_gate_hours": round(100 * tot / (hours * 3600 * len(GATES)), 2),
        }

    OUT.write_text(json.dumps(res, indent=1))
    for label, v in res["churn"].items():
        print(f"CHURN {label}: {v['changes']} value changes ({v['arms']} arms / {v['benches']} "
              f"benches) = {v['per_hour']}/hour")
    for label, v in res["cutoffs"].items():
        print(f"\n=== {label}  ({v['elapsed_h']}h elapsed, {v['gate_hours_available']} gate-hours)")
        for g in GATES:
            p = v["per_gate"][g]
            print(f"  {g:20} {p['armed']:>9}  {p['duty_pct']:>6.2f}%  {' · '.join(p['windows'])[:90]}")
        print(f"  {'ALL SIX':20} {v['desk_armed']:>9}  {v['desk_pct_of_gate_hours']:>6.2f}% of gate-hours")
    print("\n->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
