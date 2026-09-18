#!/usr/bin/env python3
"""THE PRE-EVENT ALERT — tell him BEFORE the tape moves for a reason that is not the tape.

★★★ THE EVENT IT IS BUILT FOR (2026-09-16). FOMC decision at 18:00Z. He held LONG 4 through it,
then bought AGAIN at 18:52 — T+52, with the slide still running to its low at T+85 — and lost
$1,272 on that one trade. The day was -$833; without it, +$439. His words: *"if i knew the fed was
making a decision i probably wouldve held off and waited."*

★★ WHAT IT SAYS, AND WHAT IT REFUSES TO SAY. It reports (a) that an event is coming, (b) how far
the tape ACTUALLY moved on our own measured event windows, and (c) his own event-day record. It
NEVER says which way. Every direction study on this desk is a coin, and his loss was a direction
error — an alert that implied a side would have cost him more, not less.

★ TWO PAGES: T-60 and T-15. T-60 is "decide whether to be in this at all" — the decision he said he
would have made. T-15 is the last call, and it names the position if one is open, because that is
the moment the choice becomes "flat or not" rather than "trade or not".

⚠⚠⚠ READ-ONLY. It places no order, benches no gate and touches no request file. His event-day
record is -$1,518 over 12 entries against +$1,076 over 67 ordinary ones, but that is FIVE DAYS and
the split was chosen after seeing it — PROMISING, NOT PROVEN, and nowhere near a switch.
tests/test_event_alert.py asserts the no-order-path against the SOURCE.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

import event_calendar as ec  # noqa: E402

LOG = "/home/alphabot/gazbot7/data/event_alert.log"
STATE = "/home/alphabot/gazbot7/data/day_rider_state.json"
# ⚠ The timer runs every 5 min, so each band must be WIDER than the tick or a page can fall between
# two runs and never fire. 60->50 and 15->8 both span at least one tick with room to spare.
BANDS = ((60, 50, "T-60"), (15, 8, "T-15"))


def log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line)


def position_line() -> str:
    """Name the open position, because at T-15 the question stops being 'trade or not'."""
    try:
        with open(STATE) as fh:
            st = json.load(fh)
        if st.get("qty") and not st.get("closed"):
            d = "LONG" if int(st.get("direction") or 0) > 0 else "SHORT"
            return (f" ⚠ YOU ARE {d} {st['qty']:g} @ {st.get('entry')} RIGHT NOW"
                    f" — and there is no trail behind it.")
    except Exception:
        pass
    return ""


def main() -> int:
    now = dt.datetime.now(dt.UTC)
    fired = 0
    for e in ec.upcoming(days=1):
        mins = (dt.datetime.fromisoformat(e["utc"]) - now).total_seconds() / 60.0
        for hi, lo, label in BANDS:
            if not (lo <= mins <= hi):
                continue
            paris = dt.datetime.fromisoformat(e["utc"]).astimezone(ec.PARIS).strftime("%H:%M")
            msg = (f"📅 {label}: {e['name']} at {paris} Paris "
                   f"({dt.datetime.fromisoformat(e['utc']).strftime('%H:%M')}Z), "
                   f"in {mins:.0f} min."
                   + position_line()
                   + f" MEASURED ON OUR OWN TAPE: {ec.IMPACT.get(e['kind'], 'not measured')}."
                   + " Your event-day record is -$1,518 over 12 entries vs +$1,076 over 67 ordinary"
                     " sessions (5 days only — indicative, not proven)."
                   + " ⚠ THIS SAYS WHEN, NOT WHICH WAY — direction round any trigger measures ~50/50.")
            try:
                from gazbot7.notify import dedupe_ok, notify
                # Key on the EVENT AND THE BAND, not the text: the minute count changes every tick
                # and dedupe re-sends on any change, which is how an alarm becomes wallpaper.
                if dedupe_ok(f"event_alert.{e['date']}.{e['kind']}.{label}", msg, cooldown_s=3600):
                    notify(msg, critical=True)
                    fired += 1
                    log(f"PAGED {label} {e['kind']} {e['name']}")
            except Exception as exc:
                log(f"NOTIFY FAILED: {type(exc).__name__}: {exc}")
    if not fired:
        nxt = ec.upcoming(days=3)
        log("ok — nothing in a band" + (f" · next: {nxt[0]['name']} in {nxt[0]['in_hours']:.1f}h"
                                        if nxt else " · nothing in 3 days"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
