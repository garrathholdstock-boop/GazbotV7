#!/usr/bin/env python3
"""REV2 — ONE tick census for the router week, so two sections stop printing three numbers.

WHY. The 08-28 report gave three values for the same quantity: Part 1 §5 "1,390 ticks in the week
window", Part 2.6 §7.1 "1,380 ticks in the trial log, Mon-Fri", Part 2.6 §7.2 WEEK row "1,382".
That denominator sits under the 1.2% switch rate, the 0.18 changes/hour thrash read and the
43-abort blackout arithmetic — and this week's whole thesis is that instruments disagree silently.

They disagreed for two reasons, and BOTH are real:
  1. WINDOW. Sun 22:00Z->Fri 22:00Z (the Paris trading week, which is the boundary Part 2.6's own
     day table uses) is not the same as Mon 00:00Z->Sat 00:00Z, which is not the same as the CME
     week Sun 22:00Z->Fri 21:00Z. They differ by a few ticks, and nobody printed which was meant.
  2. SNAPSHOT. The router keeps ticking while the report is written, so a count taken at 22:34Z and
     one taken at 23:13Z are different counts of a growing file.

So a census is only a number if it names its WINDOW and its SNAPSHOT. This prints both.

CANONICAL WINDOW: the PARIS TRADING WEEK, Sun 2026-08-23 22:00:00Z inclusive to Fri 2026-08-28
22:00:00Z exclusive. Chosen because it is the desk's own day boundary and the one Part 2.6's
Paris-day P&L table already uses, so the tick counts and the money line up row for row.

  python3 scripts/rev2_router_tick_census.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

TRIAL = pathlib.Path("/home/alphabot/gazbot7/data/router_trial_log.txt")
HEADLESS = pathlib.Path("/home/alphabot/gazbot7/data/router_headless.log")
OUT = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/sections/rev2_router_ticks.json")

TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z")
W0 = dt.datetime(2026, 8, 23, 22, tzinfo=dt.UTC)     # Paris Monday begins
W1 = dt.datetime(2026, 8, 28, 22, tzinfo=dt.UTC)     # Paris Friday ends
DAYS = ["Mon 08-24", "Tue 08-25", "Wed 08-26", "Thu 08-27", "Fri 08-28"]


def stamps(path: pathlib.Path):
    out = []
    for line in path.read_text(errors="replace").splitlines():
        m = TS.match(line)
        if m:
            out.append((dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
                        .replace(tzinfo=dt.UTC), line))
    return out


def paris_day(t: dt.datetime) -> int | None:
    """Index into DAYS, or None if outside the week. A Paris day runs 22:00Z -> 22:00Z."""
    if not (W0 <= t < W1):
        return None
    return int((t - W0).total_seconds() // 86400)


def main() -> int:
    trial, head = stamps(TRIAL), stamps(HEADLESS)
    snap = dt.datetime.now(dt.UTC).replace(microsecond=0)

    per = [dict(day=d, trial=0, headless=0, aborts=0, skips=0) for d in DAYS]
    for t, _ in trial:
        i = paris_day(t)
        if i is not None:
            per[i]["trial"] += 1
    for t, line in head:
        i = paris_day(t)
        if i is None:
            continue
        per[i]["headless"] += 1
        if "ABORT" in line:
            per[i]["aborts"] += 1
        if "skip:" in line:
            per[i]["skips"] += 1

    tot = {k: sum(d[k] for d in per) for k in ("trial", "headless", "aborts", "skips")}

    # the two OTHER windows people used, printed so the Rev1 numbers are explained not hidden
    def n(a, b):
        return sum(1 for t, _ in trial if a <= t < b)
    alts = {
        "paris_week_sun2200z_to_fri2200z": n(W0, W1),
        "utc_mon0000z_to_sat0000z": n(dt.datetime(2026, 8, 24, tzinfo=dt.UTC),
                                      dt.datetime(2026, 8, 29, tzinfo=dt.UTC)),
        "cme_week_sun2200z_to_fri2100z": n(dt.datetime(2026, 8, 23, 22, tzinfo=dt.UTC),
                                           dt.datetime(2026, 8, 28, 21, tzinfo=dt.UTC)),
    }

    res = dict(window=dict(start=W0.isoformat(), end=W1.isoformat(),
                           label="Paris trading week, Sun 22:00Z -> Fri 22:00Z"),
               snapshot=snap.isoformat(), per_day=per, week=tot,
               alternative_windows=alts,
               trial_log_lines_total=len(trial), headless_lines_total=len(head))
    print(json.dumps(res, indent=2))
    OUT.write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
