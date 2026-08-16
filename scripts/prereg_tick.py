#!/usr/bin/env python3
"""Append one session to the Open Rider PRE-REGISTRATION (BUILD #7). Run nightly.

    PYTHONPATH=src .venv/bin/python scripts/prereg_tick.py [--date YYYY-MM-DD]

★★2026-08-16 — WITHOUT THIS THE REGISTRATION IS A DEAD FILE. An audit found data/prereg_open_rider.json
had no writer and no reader: nothing measured ATR14@1300Z, nothing appended to `sessions`, nothing
incremented `sessions_elapsed`. After 60 sessions it would still have read `sessions: []`, with a
passing test giving it a green light. That is the desk's signature failure — config carried and read
by nothing — inside the very instrument built to answer a question honestly.

★ IT RECORDS EVERY SESSION, INCLUDING THE ONES THE FILTER EXCLUDES. The file's own rules say so, and
it is the whole design: the excluded days are half the test. Recording only the traded ones would
measure the rider, not the filter.

⚠ IT DOES NOT TRADE, GATE, OR RECOMMEND ANYTHING. It writes down what happened. The verdict is not
due for 60 sessions and the file's `verdict` stays null until then — a test enforces that.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys

GB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(GB, "src"))

REG = os.path.join(GB, "data", "prereg_open_rider.json")
CAP = os.path.join(GB, "data", "capture.db")
DB = os.path.join(GB, "data", "gazbot7.db")


def atr14_at(cap_path: str, symbol: str, at_s: int) -> float | None:
    """ATR-14 over 1-minute bars ending at `at_s`. None if the window is short — never a guess."""
    try:
        c = sqlite3.connect(f"file:{cap_path}?mode=ro", uri=True, timeout=5.0)
        rows = c.execute(
            "SELECT (bar_ts - bar_ts % 60) m, MAX(high) hi, MIN(low) lo FROM bars "
            "WHERE symbol=? AND timeframe='5s' AND bar_ts>=? AND bar_ts<=? GROUP BY 1 ORDER BY 1",
            (symbol, at_s - 20 * 60, at_s)).fetchall()
        c.close()
    except Exception:
        return None
    if len(rows) < 14:
        return None
    rng = [r[1] - r[2] for r in rows[-14:]]
    return round(sum(rng) / len(rng), 2)


def rider_pnl(db: str, day: str) -> tuple[int, float] | tuple[None, None]:
    """(trades, pnl) for the day rider on `day`, or (None, None) if unreadable."""
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
        r = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl_usd),0) FROM trades "
            "WHERE substr(opened_at,1,10)=? AND data_quality IS NULL AND gate LIKE '%rider%'",
            (day,)).fetchone()
        c.close()
        return int(r[0]), round(float(r[1]), 2)
    except Exception:
        return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    a = ap.parse_args()
    day = a.date or dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")

    with open(REG) as f:
        reg = json.load(f)

    if any(s.get("date") == day for s in reg["sessions"]):
        print(f"prereg: {day} already recorded — no double-count")
        return 0

    wd = dt.date.fromisoformat(day).weekday()
    if wd >= 5:
        print(f"prereg: {day} is a weekend — not a session")
        return 0

    # ⚠⚠ NEVER RECORD A SESSION BEFORE THE REGISTRATION DATE. A pre-registration that accepts
    # backfill is just a search with extra steps — the whole claim is that the hypothesis was fixed
    # BEFORE the data. I tripped this myself while testing: --date 2026-08-14 happily wrote a row
    # dated two days before the rule was written down.
    if day < reg["registered_on"]:
        print(f"prereg: REFUSED {day} — before registered_on {reg['registered_on']}. "
              f"Backfilling a pre-registration destroys the only property it has.")
        return 1

    at = int(dt.datetime.fromisoformat(f"{day}T13:00:00+00:00").timestamp())
    atr = atr14_at(CAP, reg.get("instrument", "MNQ"), at)
    n, pnl = rider_pnl(DB, day)

    # ⚠ A MISSING ATR IS RECORDED AS null AND DOES NOT COUNT AS A SESSION. Guessing it, or silently
    # treating "no tape" as "below threshold", would put a fabricated row into a pre-registration —
    # the one artifact whose entire value is that it was not touched after the fact.
    row = {"date": day, "atr14_1300z": atr,
           "passes_filter": (atr is not None and atr >= reg["threshold_pt"]),
           "rider_trades": n, "rider_pnl": pnl,
           "counted": atr is not None}
    reg["sessions"].append(row)
    reg["sessions_elapsed"] = sum(1 for s in reg["sessions"] if s.get("counted"))

    tmp = REG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=2)
    os.replace(tmp, REG)

    print(f"prereg {day}: ATR14@1300Z={atr} threshold={reg['threshold_pt']} "
          f"passes={row['passes_filter']} rider={n} trades ${pnl} · "
          f"{reg['sessions_elapsed']}/{reg['sessions_required']} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
