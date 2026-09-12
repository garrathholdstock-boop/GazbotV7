#!/usr/bin/env python3
"""ROUTER BLACKOUT CENSUS — one window, one population, one tick list.

★ WHY (2026-08-30, Rev 3). The same outage was counted three ways and no section reconciled them:
  card / scorecard   43 ticks aborted, 3h35m blind, 31 session-limit, 12 "Monday gateway"
  Part 2.6 §7        47 ticks / 235 minutes over five windows, one of them SATURDAY 08-29
  Part 1 §10         44 five-minute slots produced no tick, 3h40m silent, a 55-min Monday gateway
Three populations were being mixed: ABORTED ticks, SILENT slots, and the CME maintenance skip
which is BY DESIGN. This prints all three against ONE window and shows they add up.

CANONICAL WINDOW: the Paris trading week, Sun 2026-08-23 22:00:00Z inclusive -> Fri 2026-08-28
22:00:00Z exclusive — the same boundary scripts/rev2_router_tick_census.py adopted and the one
Part 2.6's Paris-day P&L table already uses. A Saturday window is OUTSIDE this week; it is
reported separately rather than folded in.

  python3 scripts/rev3_router_blackout.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

TRIAL = pathlib.Path("/home/alphabot/gazbot7/data/router_trial_log.txt")
HEADLESS = pathlib.Path("/home/alphabot/gazbot7/data/router_headless.log")
OUT = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/sections/rev3_blackout.json")

TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z")
W0 = dt.datetime(2026, 8, 23, 22, tzinfo=dt.UTC)
W1 = dt.datetime(2026, 8, 28, 22, tzinfo=dt.UTC)
TICK_MIN = 5


def stamps(path):
    out = []
    for line in path.read_text(errors="replace").splitlines():
        m = TS.match(line)
        if m:
            out.append((dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.UTC),
                        line))
    return out


def cause(line: str) -> str:
    low = line.lower()
    if "session limit" in low:
        return "LLM session limit"
    if "529" in line and "overloaded" in low:
        return "LLM API 529 overloaded"
    if "invocation failed" in low:
        return "claude invocation failed"
    if "no json" in low:
        return "no JSON in output (other)"
    return "other"


def main() -> int:
    head_all, trial_all = stamps(HEADLESS), stamps(TRIAL)
    head = [(t, l) for t, l in head_all if W0 <= t < W1]
    trial = [(t, l) for t, l in trial_all if W0 <= t < W1]

    nslots = int((W1 - W0).total_seconds() // (TICK_MIN * 60))
    hslot = {i: [] for i in range(nslots)}
    tslot = {i: [] for i in range(nslots)}
    for t, l in head:
        hslot[int((t - W0).total_seconds() // (TICK_MIN * 60))].append(l)
    for t, l in trial:
        tslot[int((t - W0).total_seconds() // (TICK_MIN * 60))].append(l)

    silent = [i for i in range(nslots) if not tslot[i]]
    aborted = [i for i in silent if any("ABORT" in l for l in hslot[i])]
    skipped = [i for i in silent if any("skip:" in l for l in hslot[i])]
    unexplained = [i for i in silent if i not in set(aborted) | set(skipped)]
    no_head = [i for i in range(nslots) if not hslot[i]]

    ab = sorted((t, l) for t, l in head if "ABORT" in l)
    by_cause = {}
    for t, l in ab:
        by_cause[cause(l)] = by_cause.get(cause(l), 0) + 1

    # contiguous outage windows: consecutive aborted ticks with <= 10 min between them
    runs, cur = [], [ab[0]] if ab else []
    for p, q in zip(ab, ab[1:]):
        if (q[0] - p[0]).total_seconds() <= 600:
            cur.append(q)
        else:
            runs.append(cur)
            cur = [q]
    if cur:
        runs.append(cur)

    res = {
        "window": {"start": W0.isoformat(), "end": W1.isoformat(),
                   "label": "Paris trading week, Sun 22:00Z -> Fri 22:00Z"},
        "snapshot": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "slots_total": nslots,
        "slots_with_no_headless_line": len(no_head),
        "trial_ticks": len(trial),
        "silent_slots": len(silent),
        "silent_minutes": len(silent) * TICK_MIN,
        "aborted_ticks": len(aborted),
        "aborted_minutes": len(aborted) * TICK_MIN,
        "cme_skip_ticks": len(skipped),
        "cme_skip_minutes": len(skipped) * TICK_MIN,
        "unexplained_slots": len(unexplained),
        "abort_causes": by_cause,
        "outage_windows": [
            {"start": r[0][0].strftime("%a %m-%d %H:%MZ"),
             "end": (r[-1][0] + dt.timedelta(minutes=TICK_MIN)).strftime("%H:%MZ"),
             "ticks": len(r), "minutes": len(r) * TICK_MIN, "cause": cause(r[0][1])}
            for r in runs],
        "abort_tick_list": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t, _ in ab],
    }

    # what sits OUTSIDE this week, so Part 2.6's five-window list is explained not hidden
    sat0 = dt.datetime(2026, 8, 28, 22, tzinfo=dt.UTC)
    sat1 = dt.datetime(2026, 8, 30, tzinfo=dt.UTC)
    out_wk = [(t, l) for t, l in head_all if sat0 <= t < sat1 and "ABORT" in l]
    res["outside_the_week"] = {
        "window": "Fri 08-28 22:00Z -> Sun 08-30 00:00Z (the weekend, NOT the report week)",
        "aborted_ticks": len(out_wk),
        "minutes": len(out_wk) * TICK_MIN,
    }

    OUT.write_text(json.dumps(res, indent=1))
    print(f"{res['slots_total']} five-minute slots; {res['trial_ticks']} produced a decision.")
    print(f"{res['silent_slots']} silent = {res['aborted_ticks']} ABORT ({res['aborted_minutes']}m) "
          f"+ {res['cme_skip_ticks']} CME skip ({res['cme_skip_minutes']}m) "
          f"+ {res['unexplained_slots']} unexplained")
    print("causes:", by_cause)
    for w in res["outage_windows"]:
        print(f"  {w['start']} -> {w['end']}  {w['ticks']:2} ticks {w['minutes']:3}m  {w['cause']}")
    print("outside the week:", res["outside_the_week"])
    print("->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
