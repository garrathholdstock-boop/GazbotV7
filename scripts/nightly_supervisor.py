#!/usr/bin/env python3
"""NIGHTLY SUPERVISOR — verify the machinery, repair only what is genuinely wedged.

★ WHY (operator, 2026-08-13): "cant python do a full desk reboot every night ... and re-arm all crons
and watchers?" The honest answer was no, and this is what to build instead.

TWO THINGS THE REBOOT IDEA COULD NOT DO, and one it should not:
 * It could not re-arm the session crons. Those lived only in a running Claude process's memory —
   no file, no socket — so nothing external could recreate them. The fix was to stop having a
   session layer that matters: they are systemd timers now (gazbot7-claude-job@*).
 * It would not have prevented the outage that prompted it. On 2026-08-13 the router no-opped for
   10.5h on an expired OAuth token. A nightly restart would have restarted a healthy desk and handed
   the router the same dead token. That needed an ALARM (gazbot7-router-health), not a reboot.
 * And it should not blanket-restart: re-adopting slots, dropping IB connections and re-reading state
   every night adds risk without removing any. CLAUDE.md already calls restarting a live desk to
   install something "the wrong trade".

So this VERIFIES loudly and repairs narrowly. It restarts a unit only when that unit is enabled and
genuinely not running, and only when the desk is FLAT.

★ TIMING — 21:40 UTC, and the choice matters. 21:00-22:00 UTC is the CME halt: no market, and the
desk is flat (EOD flatten 16:53 New York, day-rider hard flat 20:40). It sits after the 21:30 nightly
audit so claim_audit.json is fresh. It is deliberately NOT the operator's suggested Paris midnight —
22:00 UTC is the REOPEN, and it is already the busiest minute on the calendar
(gazbot7-gate-reactivate arms every benched gate then). Repairing into that is asking for trouble.

★ WHAT IT CHECKS — every layer that can fail silently:
 1. The ROUTER is deciding (not an ABORT streak, not a stale log, not a full-roster PIN).
 2. Every enabled gazbot7 timer is active, and the frequent ones have actually fired recently.
    An `enabled` timer that has not fired is the exact shape of a silent failure.
 3. The desk services that must be running, are.
 4. Every claude job has a recent, successful run record — a job that silently stopped running is
    invisible otherwise, because absence produces no error.
 5. The tape-mirror/prune INTERLOCK: prune may not delete a day the mirror has not verified. If the
    mirror stalls, capture.db grows — growth you notice, a silent hole in the tape you do not.

★ NO SILENT CAPS. Everything it decides not to repair, it says.

  PYTHONPATH=src scripts/nightly_supervisor.py [--json] [--dry-run]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"

# Units that must be RUNNING continuously. Deliberately not gazbot7-core / gazbot7-strategy: both
# are disabled and have never started (vestigial), and treating them as required would manufacture
# a nightly false alarm — the same false comfort sweep.py gives when it reports "restarts core: 0"
# for a unit that has never run.
REQUIRED_SERVICES = ["gazbot7-tournament", "gazbot7-md", "gazbot7-shadow",
                     "gazbot7-depth-capture", "gazbot7-router-watch"]

# (unit, max hours since last fire). Only frequent timers — a weekly one has not "failed" by not
# having run today.
TIMER_FRESHNESS = {
    "gazbot7-router-tick.timer": 0.25,
    "gazbot7-router-health.timer": 0.5,
    "gazbot7-day-rider.timer": 0.1,
    "gazbot7-monitor.timer": 1.0,
    "gazbot7-claude-job@sweep.timer": 6.0,
}
JOB_MAX_AGE_H = {"sweep": 6, "hour-watch": 26, "ledger-review": 6, "nightly-review": 30}


def sh(*cmd: str, timeout: int = 20) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def desk_is_flat() -> tuple[bool, str]:
    """Repair only when flat. A restart re-adopts slots from the ledger; doing that while holding is
    how the 08-06 class of incident starts."""
    try:
        h = json.load(open(f"{GB}/data/core_health.json"))
        return bool(h.get("flat")), f"flat={h.get('flat')} halted={h.get('halted')}"
    except Exception as e:
        return False, f"core_health unreadable ({e}) — treating as NOT flat"


def check() -> tuple[list[str], list[str], dict]:
    """(faults, notes, detail)."""
    faults: list[str] = []
    notes: list[str] = []
    detail: dict = {}

    # 1. the router actually decides
    rh = sh(PY, f"{GB}/scripts/router_health_check.py", "--json", "--dry-run", timeout=60)
    try:
        rhj = json.loads(rh) if rh.strip().startswith("{") else {}
    except Exception:
        rhj = {}
    detail["router"] = rhj
    for f in rhj.get("faults", []):
        faults.append(f"ROUTER: {f}")

    # 2. enabled timers are active, and frequent ones have fired
    dead = []
    for line in sh("systemctl", "list-unit-files", "gazbot7-*.timer", "--no-legend").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "enabled":
            if sh("systemctl", "is-active", parts[0]) != "active":
                dead.append(parts[0])
    if dead:
        faults.append(f"TIMERS enabled but NOT active: {', '.join(dead)}")
    detail["dead_timers"] = dead

    # ★ "enabled and active" is NOT "working" — that is the whole lesson of 2026-08-13, where an
    # active/enabled router timer fired 125 times and decided nothing. So check that each frequent
    # timer has ACTUALLY TRIGGERED recently. Uses LastTriggerUSec (machine-readable, monotonic-safe)
    # rather than scraping the human "3min ago" column of list-timers, which is locale- and
    # width-dependent and was silently un-parseable in the first cut of this function.
    stale = []
    for unit, max_h in TIMER_FRESHNESS.items():
        # ★ Existence and never-fired look IDENTICAL through LastTriggerUSec: systemd returns an
        # EMPTY value for a loaded timer that has not yet triggered, and also for a unit that does
        # not exist. Conflating them made this report a brand-new timer as "unit not found" — a
        # false CRITICAL on the very night it was installed. LoadState separates them.
        if sh("systemctl", "show", unit, "-p", "LoadState", "--value") != "loaded":
            stale.append(f"{unit} (unit NOT FOUND — was it removed?)")
            continue
        raw = sh("systemctl", "show", unit, "-p", "LastTriggerUSec", "--value")
        if raw in ("0", "n/a", ""):
            # Never triggered since boot. Benign for a just-installed timer, so say which it is
            # rather than paging — a false nightly alarm is how a real one gets ignored.
            notes.append(f"{unit} has never triggered (newly installed?)")
            continue
        ts = sh("date", "-d", raw, "+%s")
        if not ts.isdigit():
            notes.append(f"{unit} LastTriggerUSec unparseable: {raw!r}")
            continue
        age_h = (time.time() - int(ts)) / 3600
        if age_h > max_h:
            stale.append(f"{unit} last fired {age_h:.1f}h ago (expected within {max_h}h)")
    if stale:
        faults.append("TIMERS ACTIVE BUT NOT FIRING: " + "; ".join(stale))
    detail["stale_timers"] = stale

    # 3. services that must be up
    down = [s for s in REQUIRED_SERVICES if sh("systemctl", "is-active", s) != "active"]
    if down:
        faults.append(f"SERVICES down: {', '.join(down)}")
    detail["services_down"] = down

    # 4. claude jobs have recent successful runs — a job that silently stopped leaves no error,
    #    only an absence, which is why this checks the run RECORD rather than the unit.
    now = time.time()
    for path in sorted(glob.glob(f"{GB}/data/claude_jobs/*.json")):
        name = os.path.basename(path)[:-5]
        max_h = JOB_MAX_AGE_H.get(name)
        if not max_h:
            continue
        try:
            rec = json.load(open(path))
            age_h = (now - os.path.getmtime(path)) / 3600
            if age_h > max_h:
                faults.append(f"JOB {name} last ran {age_h:.1f}h ago (expected within {max_h}h)")
            elif not rec.get("ok"):
                faults.append(f"JOB {name} last run FAILED rc={rec.get('rc')}")
        except Exception as e:
            notes.append(f"job record {name} unreadable: {e}")
    missing = [n for n in JOB_MAX_AGE_H if not os.path.exists(f"{GB}/data/claude_jobs/{n}.json")]
    if missing:
        notes.append(f"jobs with no run record yet (newly installed?): {', '.join(missing)}")

    # 5. the tape-mirror / prune INTERLOCK. If the mirror stalls the prune correctly stops too, and
    #    capture.db grows instead of losing data — so growth is the SYMPTOM to watch, not the fault.
    try:
        man = json.load(open(f"{GB}/data/tape/_manifest.json"))
        vs = man.get("verified", {})
        newest = max((v.get("at", "") for v in vs.values()), default="")
        detail["mirror_verified_days"] = len(vs)
        detail["mirror_newest"] = newest
        age_h = (now - os.path.getmtime(f"{GB}/data/tape/_manifest.json")) / 3600
        if age_h > 30:
            faults.append(f"TAPE MIRROR manifest {age_h:.0f}h old — if the mirror has stalled the "
                          f"prune is correctly blocked and capture.db will GROW. Check "
                          f"gazbot7-tape-mirror.timer.")
    except Exception as e:
        notes.append(f"tape manifest unreadable: {e}")
    try:
        gb = os.path.getsize(f"{GB}/data/capture.db") / 1e9
        detail["capture_gb"] = round(gb, 2)
        if gb > 12:
            faults.append(f"capture.db is {gb:.1f}GB — the prune may be blocked by a stalled mirror.")
    except Exception:
        pass

    return faults, notes, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="never repair, never page")
    a = ap.parse_args()

    faults, notes, detail = check()
    flat, flat_why = desk_is_flat()
    repaired: list[str] = []
    declined: list[str] = []

    # REPAIR: narrow on purpose. Only a service that must be up and is not, and only when flat.
    for svc in detail.get("services_down", []):
        if a.dry_run:
            declined.append(f"{svc} (dry-run)")
        elif not flat:
            declined.append(f"{svc} (desk NOT flat: {flat_why} — restarting could re-adopt slots)")
        else:
            sh("systemctl", "restart", svc, timeout=60)
            time.sleep(3)
            ok = sh("systemctl", "is-active", svc) == "active"
            (repaired if ok else declined).append(f"{svc}{'' if ok else ' (restart FAILED)'}")

    out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "faults": faults, "notes": notes, "repaired": repaired,
           "declined_repairs": declined, "flat": flat, **detail}
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{'OK' if not faults else str(len(faults)) + ' FAULT(S)'} · flat={flat} · "
              f"repaired={repaired or '-'} · declined={declined or '-'}")
        for f in faults:
            print(f"  ! {f}")
        for n in notes:
            print(f"  · {n}")

    try:
        with open(f"{GB}/data/nightly_supervisor.json", "w") as fh:
            json.dump(out, fh, indent=1)
    except Exception:
        pass

    if not a.dry_run and (faults or repaired):
        try:
            from gazbot7.notify import notify
            head = "⚠ GAZBOT NIGHTLY SUPERVISOR"
            body = " | ".join(faults) if faults else "all checks passed"
            if repaired:
                body += f" || REPAIRED: {', '.join(repaired)}"
            if declined:
                body += f" || NOT repaired: {', '.join(declined)}"
            notify(f"{head} — {body}"[:900], critical=bool(faults))
        except Exception:
            pass
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
