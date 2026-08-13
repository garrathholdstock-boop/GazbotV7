#!/usr/bin/env python3
"""ROUTER HEALTH — does the durable router actually DECIDE anything?

★ WHY THIS EXISTS (2026-08-13). The router no-opped for 125 consecutive ticks — 02:40→13:00Z, TEN
AND A HALF HOURS straight through London and into the US open — because the headless `claude -p`
call could not authenticate:

    ABORT: no JSON in output -> no change | raw='Failed to authenticate: OAuth session expired...'

Every indicator stayed green the whole time. `systemctl status` said active/enabled. The service
exited 0/SUCCESS every five minutes. `sweep.py` reported nothing. `PINNED` was empty. The desk sat
frozen on a 02:30Z switch state and nothing anywhere said so, because THE FAIL-SAFE IS
INDISTINGUISHABLE FROM A QUIET TAPE: a parse failure writes "no change", and so does a genuinely
calm market.

Nothing else watches this. `router_watch_durable.py` relays `router_watch.py`, which reads the TAPE
and the DESK — never the router's own output. So the one component whose silence means "the desk is
unmanaged" had no monitor at all. This is that monitor.

★ IT CHECKS FOUR THINGS, all cheap and all read-only:
  1. ABORT STREAK    — N consecutive ABORT ticks. Credential expiry is now the #1 failure mode.
  2. SILENCE         — no line written in ~16 min when the tick runs every 5.
  3. FULL-ROSTER PIN — a PINNED set covering every gate makes every tick a silent no-op that still
                       logs "no change". 411 ticks / 36h went unnoticed that way on 07-31.
  4. TIMER DEAD      — the unit itself disabled or inactive.

★ THE OPERATOR DECLINED AN API KEY (2026-08-13) and re-logs in by hand, so this alarm IS the
mitigation, not a backstop to one. It must be loud and it must be durable — a session-bound version
would die exactly when the session dies, which is when it is most needed.

★ EDGE-TRIGGERED, WITH A SLOW RE-NAG. Paging every 5 minutes for 10 hours would train the operator
to swipe it away, which is the failure `open_hour_watch.py`'s docstring warns about. So: page once on
entering a bad state, re-nag hourly while it persists (silence must not read as "fixed"), and page
once on recovery so the all-clear is explicit.

  PYTHONPATH=src scripts/router_health_check.py [--json] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
HLOG = f"{GB}/data/router_headless.log"
TICK = f"{GB}/scripts/router_tick_durable.py"
STATE = f"{GB}/data/router_health_state.json"

ABORT_STREAK_ALARM = 3        # 3 x 5min = the desk has been frozen ~15 min
SILENT_MAX_S = 16 * 60        # tick is every 5 min; 16 min means ~3 missed
RENAG_S = 3600                # re-nag hourly while still broken
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z")


def parse_tail(lines: list[str]) -> tuple[int, float | None, str]:
    """(consecutive ABORTs at the tail, epoch of the last line, last line).

    Pure so it is testable without a live desk. Counts backwards from the newest line, because what
    matters is whether the router is aborting NOW — an ABORT streak that already recovered is
    history, not an alarm.
    """
    streak, last_ts, last = 0, None, ""
    for ln in reversed([x for x in lines if x.strip()]):
        if not last:
            last = ln.strip()
            m = TS_RE.match(ln)
            if m:
                last_ts = time.mktime(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")) - time.timezone
        if "ABORT:" in ln:
            streak += 1
        else:
            break
    return streak, last_ts, last


def pin_is_full_roster() -> bool:
    """A PINNED set covering every gate makes `valid` permanently empty — every tick a silent
    no-op. Read the tick's own module rather than re-deriving the roster here; a second copy of
    the gate list is a second thing to drift."""
    try:
        sys.path.insert(0, f"{GB}/scripts")
        import importlib.util
        spec = importlib.util.spec_from_file_location("_rtd", TICK)
        mod = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
        spec.loader.exec_module(mod)                          # type: ignore[union-attr]
        pinned, gates = set(getattr(mod, "PINNED", set())), set(getattr(mod, "GATES", []))
        return bool(gates) and pinned >= gates
    except Exception:
        return False      # fail-quiet: never alarm on our own import trouble


def timer_ok() -> tuple[bool, str]:
    try:
        act = subprocess.run(["systemctl", "is-active", "gazbot7-router-tick.timer"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        en = subprocess.run(["systemctl", "is-enabled", "gazbot7-router-tick.timer"],
                            capture_output=True, text=True, timeout=10).stdout.strip()
        return (act == "active" and en == "enabled"), f"active={act} enabled={en}"
    except Exception as e:
        return True, f"check failed: {e}"     # do not alarm on a systemctl hiccup


def assess() -> tuple[list[str], dict]:
    """Returns (faults, detail). Empty faults = healthy."""
    faults: list[str] = []
    try:
        with open(HLOG) as fh:
            lines = fh.readlines()[-50:]
    except Exception as e:
        return ([f"cannot read router_headless.log: {e}"], {})

    streak, last_ts, last = parse_tail(lines)
    age = (time.time() - last_ts) if last_ts else None

    if streak >= ABORT_STREAK_ALARM:
        faults.append(f"ABORT STREAK {streak} consecutive ticks — the router is deciding NOTHING "
                      f"and the desk is FROZEN on its last switch state. Almost certainly an "
                      f"expired login: run `claude` and /login on the box. Last: {last[:160]}")
    if age is not None and age > SILENT_MAX_S:
        faults.append(f"SILENT {age/60:.0f} min since the last tick (expected every 5). "
                      f"Check gazbot7-router-tick.timer.")
    if pin_is_full_roster():
        faults.append("FULL-ROSTER PIN — PINNED covers every gate, so every tick is a silent "
                      "no-op that still logs 'no change'. Shrink PINNED in router_tick_durable.py.")
    ok, tdetail = timer_ok()
    if not ok:
        faults.append(f"TIMER NOT HEALTHY — gazbot7-router-tick.timer {tdetail}")

    return faults, {"abort_streak": streak, "last_line_age_s": round(age) if age else None,
                    "last_line": last[:200], "timer": tdetail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="assess and print, never page")
    a = ap.parse_args()

    faults, detail = assess()
    now = time.time()
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    was_bad = bool(st.get("bad"))
    last_page = float(st.get("last_page") or 0)

    if a.json:
        print(json.dumps({"faults": faults, **detail}, indent=2))
    else:
        print(("HEALTHY — " if not faults else f"{len(faults)} FAULT(S) — ") +
              json.dumps(detail))
        for f in faults:
            print(f"  ! {f}")

    if a.dry_run:
        return 1 if faults else 0

    def page(msg: str, critical: bool = True) -> None:
        try:
            from gazbot7.notify import notify
            notify(msg, critical=critical)
        except Exception:
            pass

    if faults and (not was_bad or now - last_page > RENAG_S):
        page("⚠ GAZBOT ROUTER HEALTH — " + " | ".join(faults)[:800])
        last_page = now
    elif was_bad and not faults:
        page(f"GAZBOT ROUTER HEALTH recovered — ticks are producing decisions again. "
             f"Last: {detail.get('last_line', '')[:160]}", critical=False)

    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"bad": bool(faults), "last_page": last_page,
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "faults": faults, **detail}, fh)
    os.replace(tmp, STATE)
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
