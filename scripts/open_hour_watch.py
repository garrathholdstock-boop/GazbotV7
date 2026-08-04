#!/usr/bin/env python3
"""US-OPEN HOUR WATCHER — a headless agent reading the tape EVERY MINUTE for the first hour.

Operator, 2026-08-04: "you need to setup a daily cron to have an agent monitoring the tape for the
first hour of the us open every minute. if i am asking you to do things it will distract from you
looking at the tape... and the agent interrupts you with any things that need changing".

★ WHY THIS EXISTS. On 2026-08-04 the tape broke out at ~13:35 (last-hr ER 0.02->0.40, ATR 10->21, new
day high, bias UP +559) and grind_long — the ALIGNED trend-rider — stayed benched for 17 minutes while I
was answering a question about NIPC. The 5-min durable tick DID see the break and declined anyway,
reasoning "its own book is the day's worst and one hour is not n" — which is wrong on a trend day,
because the day aggregate was dominated by the morning dead chop. The open hour is where the day is
won or lost and it is exactly when the operator is most likely to be talking to me. So the watching
must not depend on my attention.

★★ ALERT-ONLY. IT MUST NEVER WRITE gate_switches.env.
`gazbot7-router-tick.timer` already owns that file every 5 minutes. A second writer is the "two
routers" hazard CLAUDE.md warns about explicitly — two processes racing on the same switches, each
undoing the other. So this agent is READ-ONLY: it reads the tape and, if something needs changing,
writes a line to ALERTS. The live session tails that file and is interrupted in-chat; the operator gets
a Telegram push on anything critical. A human (or the session) then acts. One writer, many watchers.

★ DEDUPED. A minute-cadence watcher that re-alerts the same condition 60 times is worse than useless —
it trains everyone to ignore it. Each alert is fingerprinted and only a CHANGED fingerprint fires. The
heartbeat still records every tick to the run log so a dead watcher is visible.

★ FAIL-SAFE. Any error, timeout or unparseable answer => NO alert and a logged skip. It cannot halt the
desk, cannot move a switch, and cannot page on its own malfunction beyond one log line.

Window: 13:30-14:30 UTC weekdays (US equity open + first hour). Outside it, exits immediately, so the
timer can be dumb.

  PYTHONPATH=src .venv/bin/python scripts/open_hour_watch.py [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
CLAUDE = "/root/.local/bin/claude"
ALERTS = f"{GB}/data/open_hour_alerts.log"     # the session tails THIS -> in-chat interrupt
RUNLOG = f"{GB}/data/open_hour_watch.log"      # heartbeat: every tick, so a dead watcher is visible
STATE = f"{GB}/data/open_hour_state.json"      # last alert fingerprint (dedup)
OPEN_FROM, OPEN_TO = (13, 30), (14, 30)        # UTC


def sh(cmd: str, timeout: int = 60) -> str:
    env = {**os.environ, "PYTHONPATH": "src"}
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout, cwd=GB, env=env).stdout
    except Exception as e:
        return f"(read failed: {e})"


def in_window(now: dt.datetime) -> bool:
    if now.weekday() > 4:
        return False
    hm = (now.hour, now.minute)
    return OPEN_FROM <= hm < OPEN_TO


PROMPT = """You are watching the GAZBOT V7 MNQ desk during the FIRST HOUR of the US open. You are a
READ-ONLY watcher: you cannot change anything. Your only job is to decide whether something needs
CHANGING RIGHT NOW and, if so, say what — a human acts on it within a minute or two.

Reply with STRICT JSON only:
{"action":"NONE"|"ALERT","urgency":"info"|"act"|"critical","what":"<the change needed, one line>","why":"<the evidence, one line>"}

Use action NONE unless there is something specific to DO. A running commentary is noise; an alert that
merely restates the tape will be ignored and will make the next real alert less likely to be read.

WHAT WARRANTS AN ALERT — judge on the evidence in front of you, not on a checklist:
* An ALIGNED momentum gate is benched while a REAL break is underway. A real break needs all three:
  ER climbing and sustained (not one blip), vol expanding, and structure (new extreme / range break).
  ★ Do NOT accept "its full-day book is red" as a reason it should stay benched — on a trend day that
  aggregate is dominated by earlier chop. Segregate by the BREAK window. This exact error cost 17
  minutes of a +559pt trend day on 2026-08-04.
* A gate is armed into a regime that is demonstrably paying it nothing — a wall of STOPs, or a fader
  armed against a confirmed directional day.
* A counter-trend gate is armed while a clean, efficient trend runs against it.
* Position/health trouble: not flat when it should be, naked, halted, capture stale, a restart storm.
* The quiet-tape CLIP is capping profit on a trending day (ATR just under the atr_split boundary caps
  Lot A at a cash figure while the tape is running).

DELIBERATELY NOT YOUR JOB: retuning R multiples, proposing new gates, or second-guessing a bench that
has a stated standing reason. Read the switches file's comments — a gate benched for a verdicted reason
(rgv_short) or pinned after a failed acceptance replay (nipc) should NOT be alerted on.

CONTEXT:
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore the time window")
    a = ap.parse_args()

    now = dt.datetime.now(dt.UTC)
    if not a.force and not in_window(now):
        return 0

    desk = sh(f"{PY} scripts/desk_view.py", timeout=120)
    recent = sh(f"{PY} scripts/recent_trades.py", timeout=60)
    if "DAY BIAS" not in desk:
        with open(RUNLOG, "a") as fh:
            fh.write(f"{now:%Y-%m-%dT%H:%M:%SZ} SKIP desk read failed\n")
        return 0

    ctx = f"{desk}\n\n=== RECENT TRADES ===\n{recent}\n"
    if a.dry_run:
        print(ctx[:3000])
        return 0

    try:
        r = subprocess.run([CLAUDE, "-p", PROMPT + ctx, "--allowedTools", ""],
                           capture_output=True, text=True, timeout=200,
                           env={**os.environ, "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"})
        raw = (r.stdout or "").strip()
        s, e = raw.find("{"), raw.rfind("}")
        v = json.loads(raw[s:e + 1])
    except Exception as ex:
        with open(RUNLOG, "a") as fh:
            fh.write(f"{now:%Y-%m-%dT%H:%M:%SZ} SKIP verdict failed: {ex}\n")
        return 0

    act = str(v.get("action", "NONE")).upper()
    urg = str(v.get("urgency", "info")).lower()
    what, why = str(v.get("what", ""))[:300], str(v.get("why", ""))[:300]
    with open(RUNLOG, "a") as fh:
        fh.write(f"{now:%Y-%m-%dT%H:%M:%SZ} {act} {urg} {what}\n")

    if act != "ALERT" or not what:
        return 0

    # ── dedup: only a CHANGED alert fires, else a minute cadence produces 60 identical pages ──
    fp = hashlib.sha256(f"{urg}|{what}".encode()).hexdigest()[:12]
    prev = None
    try:
        prev = json.load(open(STATE)).get("fp")
    except Exception:
        pass
    if fp == prev:
        return 0
    try:
        json.dump({"fp": fp, "ts": now.isoformat(timespec="seconds")}, open(STATE, "w"))
    except Exception:
        pass

    line = f"{now:%H:%M:%S}Z OPEN-HOUR [{urg.upper()}] {what} — {why}"
    with open(ALERTS, "a") as fh:      # the session's Monitor tails this => in-chat interrupt
        fh.write(line + "\n")
    if urg in ("act", "critical"):
        try:
            subprocess.run([PY, "-c",
                            "import sys; from gazbot7.notify import notify; notify(sys.argv[1], critical=%s)"
                            % (urg == "critical"), f"OPEN-HOUR: {what} ({why})"],
                           cwd=GB, env={**os.environ, "PYTHONPATH": "src"}, timeout=30)
        except Exception:
            pass
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
