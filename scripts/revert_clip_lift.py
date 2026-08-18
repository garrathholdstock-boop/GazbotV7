#!/usr/bin/env python3
"""RESTORE THE QUIET-TAPE CLIP — expires an intraday clip LIFT at the daily maintenance halt.

Operator, 2026-08-04: "lift the clip for grind while the trend holds".

★ WHY THIS EXISTS RATHER THAN A COMMENT SAYING "REMEMBER TO PUT IT BACK".
"While the trend holds" is a condition, and a condition nothing evaluates is just a hope. Today alone
this desk has been bitten three times by an instruction that lived only in prose: NIPC was re-armed by
the 22:00 job because its bench was written as a COMMENT; the abs_veto_short carve-out survived past its
own stated expiry because the expiry was a sentence, not a check; and a stale carve-out body left in the
router prompt contradicted its own replacement for one tick. So the lift gets a MECHANISM.

POLICY, deliberately copied from gate_switches.env: an intraday change lasts ONE DAY. reactivate_gates.py
re-arms every benched gate at the Paris-midnight reopen precisely so no intraday bench silently becomes
permanent; a clip lift is the same class of change and gets the same treatment. If the trend is still
there tomorrow, lifting it again is one command — and it will be a DECISION, made on tomorrow's tape,
rather than yesterday's exception quietly still running.

WHEN: 21:15 UTC, inside the CME index-futures maintenance halt (21:00-22:00), so the desk is flat and
the required tournament restart costs nothing.

IDEMPOTENT: if the clip is already present it does nothing and says so. Safe to run any number of times.
FAIL-SAFE: any error leaves the file untouched and logs. It never edits gate_switches.env.

  PYTHONPATH=src .venv/bin/python scripts/revert_clip_lift.py [--check] [--no-restart]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import subprocess
import sys

GB = "/home/alphabot/gazbot7"
OVR = f"{GB}/data/exit_overrides.json"
LOG = f"{GB}/data/router_trial_log.txt"
# The standard clip, identical to what every other clipped gate carries.
CLIP = {"atr_split": 22, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}}
# Gates that are SUPPOSED to carry the clip. nipc is deliberately exempt (its own 20-min cap +
# 15:30 flat make a cash clip meaningless) and is NOT restored here.
# ★★2026-08-18 exhaustion_short REMOVED — this roster was STALE and the job "restored" a clip that
# had been deliberately removed. d6a0e88 shipped the wide-stop cell (1.0 -> 1.5xATR, both lots scalp
# 2.0R) and that GRADED cell has no clip; tests/test_exh_wide_stop.py pins it: "the graded cell had
# no clip, so leaving it on would ship a config the grid never measured — silently, and only on
# quiet days". On 08-16 21:15 this job put it back and restarted the tournament, so the desk ran an
# unmeasured cell live on its only armed short, biting exactly when ATR < 22.
# ⚠ THE LESSON IS THE ROSTER, NOT THE CLIP: a daily "restore to standard" job is only as correct as
# its list of what standard IS. When a gate's graded config CHANGES, this tuple must change with it.
CLIPPED = ("grind_long", "capitulation_long",
           "abs_veto_long", "abs_veto_short", "rgv_short")


def log(msg: str) -> None:
    try:
        with open(LOG, "a") as fh:
            fh.write(f"{dt.datetime.now(dt.UTC):%FT%TZ} | clip-revert | {msg}\n")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, change nothing")
    ap.add_argument("--no-restart", action="store_true")
    a = ap.parse_args()
    try:
        d = json.loads(open(OVR).read(), object_pairs_hook=collections.OrderedDict)
    except Exception as e:
        log(f"ABORT unreadable overrides: {e}")
        print(f"ABORT: {e}")
        return 0                                   # never fail the host timer

    missing = [g for g in CLIPPED if g in d and "atr_split" not in d[g]]
    if not missing:
        print("clip present on every clipped gate — nothing to do")
        return 0
    print(f"clip LIFTED on: {', '.join(missing)}")
    if a.check:
        return 0

    for g in missing:
        d[g].update(json.loads(json.dumps(CLIP)))
    try:
        open(OVR, "w").write(json.dumps(d, indent=2) + "\n")
    except Exception as e:
        log(f"ABORT write failed: {e}")
        print(f"ABORT: {e}")
        return 0
    log(f"RESTORED the quiet-tape clip on {', '.join(missing)} (daily expiry of an intraday lift). "
        f"Policy: an intraday exit-override change lasts ONE DAY, same as a gate bench. Re-lift "
        f"tomorrow only as a fresh decision on tomorrow's tape.")
    print(f"restored clip on {', '.join(missing)}")

    if not a.no_restart:
        # Config is read at startup, so the restore needs a restart. We are inside the halt: flat.
        try:
            subprocess.run(["systemctl", "restart", "gazbot7-tournament"], timeout=90, check=False)
            print("gazbot7-tournament restarted (config takes effect at startup)")
        except Exception as e:
            log(f"WARN restart failed, clip restored on disk but NOT loaded: {e}")
            print(f"WARN restart failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
