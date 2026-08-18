#!/usr/bin/env python3
"""BACKFILL WATCHDOG — is the history pull alive AND producing, and self-heal if not.

Operator, 2026-08-18: "i would love to wake up and this is done and we have the data".
That outcome must not depend on a chat session surviving the night, so this is a systemd timer.

★ IT CHECKS PRODUCTION, NOT LIVENESS. A process that is running and writing nothing is the exact
failure this desk keeps meeting — a service was `active` with NRestarts=0, burning CPU, and had
never once been capable of firing. So "alive" is not the test: parquet COUNT and log GROWTH are.

Verdicts:
  WORKING      producing files, or legitimately paused because a desk holds a position
  IDLE-OK      finished and nothing left to fetch (entitlement ceiling reached) — the success case
  STALLED      running, but no new file and no new log line for STALL_MIN — restart once
  DEAD         not running, budget remains, work outstanding — restart
  BLOCKED      restarted twice and still nothing — page, do not loop
"""
from __future__ import annotations
import datetime as dt
import glob
import json
import os
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/src")
OUT = f"{GB}/data/backfill"
LOG = f"{OUT}/run.log"
STATE = f"{OUT}/_watchdog.json"
UNIT = "gazbot7-backfill.service"
STALL_MIN = 25            # > the 90s request timeout + a full per-day contract leg
MAX_RESTARTS = 2          # then stop and page — a restart loop is not a fix
WINDOW = (22, 7)          # only act between 22:00 and 07:00 UTC; outside that the desk trades


def _sh(*a):
    return subprocess.run(a, capture_output=True, text=True, timeout=20).stdout.strip()


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"restarts": 0, "last_files": -1, "last_log": 0, "last_change": 0}


def save(d):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=1)
    os.replace(tmp, STATE)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(dt.UTC)
    st = load()
    files = len(glob.glob(f"{OUT}/*.parquet"))
    logsz = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    active = _sh("systemctl", "is-active", UNIT) in ("active", "activating")
    ts = int(now.timestamp())

    progressed = files != st.get("last_files") or logsz != st.get("last_log")
    if progressed:
        st["last_change"] = ts
    since = (ts - st.get("last_change", ts)) / 60.0

    # a desk holding a position is a LEGITIMATE pause, not a stall — the pull yields on purpose
    try:
        flat = json.load(open(f"{GB}/data/core_health.json")).get("flat", False)
        r = json.load(open(f"{GB}/data/day_rider_state.json"))
        busy = (not flat) or (bool(r.get("entered")) and not bool(r.get("closed")))
    except Exception:
        busy = False

    in_window = now.hour >= WINDOW[0] or now.hour < WINDOW[1]
    verdict, action = "WORKING", "none"

    if busy and active:
        verdict = "WORKING (yielded — a desk holds a position)"
    elif active and since > STALL_MIN:
        verdict = f"STALLED — no new file or log line for {since:.0f}min"
        if in_window and st["restarts"] < MAX_RESTARTS:
            _sh("systemctl", "restart", UNIT)
            st["restarts"] += 1
            action = f"restarted ({st['restarts']}/{MAX_RESTARTS})"
        elif st["restarts"] >= MAX_RESTARTS:
            verdict, action = "BLOCKED", "paging — restarts exhausted"
    elif not active:
        # finished. Distinguish "nothing left to fetch" from "died with work outstanding".
        tail = ""
        try:
            tail = open(LOG).read()[-400:]
        except Exception:
            pass
        if "done:" in tail:
            verdict, action = f"IDLE-OK — completed, {files} parquet files", "none"
        elif in_window and st["restarts"] < MAX_RESTARTS:
            verdict = "DEAD — exited without completing"
            _sh("systemctl", "start", UNIT)
            st["restarts"] += 1
            action = f"started ({st['restarts']}/{MAX_RESTARTS})"
        elif st["restarts"] >= MAX_RESTARTS:
            verdict, action = "BLOCKED", "paging — restarts exhausted"
        else:
            verdict = "idle (outside the 22:00-07:00 window)"

    st.update(last_files=files, last_log=logsz)
    save(st)
    line = (f"{now:%H:%M}Z files={files} log={logsz}B active={active} "
            f"quiet={since:.0f}min -> {verdict}" + (f" | {action}" if action != "none" else ""))
    print(line, flush=True)

    if verdict.startswith("BLOCKED"):
        try:
            from gazbot7.notify import dedupe_ok, notify
            if dedupe_ok("backfill.blocked", "backfill blocked", cooldown_s=6 * 3600):
                notify(f"⚠ GAZBOT BACKFILL BLOCKED — {files} files, {since:.0f}min quiet, "
                       f"{st['restarts']} restarts spent. Needs a human.", critical=True)
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
