#!/usr/bin/env python3
"""DID THE NIGHT'S MACHINERY ACTUALLY RUN? Asked in the MORNING, by a DIFFERENT PROCESS.

★★★2026-09-26, AND THIS IS THE SECOND ATTEMPT AT ONE IDEA. The audit's finding 7 was that
`nightly_supervisor` spoke only on faults, so a clean night and a DEAD SUPERVISOR produced identical
silence. The first fix made it send unconditionally — and that fix DID NOT WORK, for a reason worth
writing down:

    the supervisor fires at 21:40 UTC = 23:40 Paris (22:40 in winter), and quiet hours are
    22:00-06:00 Paris. The all-clear was correctly `critical=False`, so `notify()` suppressed it
    EVERY NIGHT OF THE YEAR. Verified by probe across CEST and CET. The bug's replacement produced
    byte-identical silence to the bug.

★★ THE DEEPER ERROR WAS THE DESIGN, NOT THE TIMESTAMP. "The supervisor tells you it is alive" cannot
work when the supervisor is the thing that died: a process cannot report its own absence. Making it
shout through quiet hours would only have traded one failure for a 23:40 buzz every night, which is
the cry-wolf problem quiet hours exist to prevent — and the operator has said plainly that most of
his ~10 Telegrams a day are already noise.

So the check is INVERTED and moved. This job runs at **06:05 Paris, just after quiet hours end**, and
asks a question about SOMEONE ELSE: did `nightly_supervisor` leave a fresh verdict on disk? It is a
different process, on a different timer, at a different hour — so the supervisor's death is now
detectable by something that is not the supervisor.

★ WHAT IT SENDS, and why the fault case is the loud one:
  · no file, or a file older than MAX_AGE_H → **critical**. The supervisor did not run. This is the
    case the whole instrument exists for and it is the only one that pages hard.
  · faults recorded → repeats them (they already paged at 21:40 in real time; this is the record he
    reads with coffee, and a repeat is cheap next to a missed one).
  · clean → ONE quiet line. Routine, unmarked, and deliberately boring: he should be able to ignore
    it on any given morning and notice its absence over several.

⚠ IT NEEDS NO QUIET-HOURS BYPASS, and that is the point of the hour. Nothing here argues for a new
exemption in `notify()`; adding one would have re-coupled the flags the 09-24 split separated.
⚠ READ-ONLY. It reads one JSON file and sends one message. No switch, no order path, no repair.

  PYTHONPATH=src .venv/bin/python scripts/overnight_allclear.py [--json] [--quiet]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
VERDICT = f"{GB}/data/nightly_supervisor.json"
#: A supervisor verdict older than this means last night's run did not happen. It fires at 21:40Z
#: and this reads at ~04:05/05:05Z, so a healthy file is ~7h old; 12h catches a skipped night
#: without tripping on an ordinary clock shift or a slow run.
MAX_AGE_H = 12.0


def assess(now: dt.datetime, path: str = VERDICT) -> tuple[str, str, bool]:
    """(status, message, critical). Pure enough to test without a clock or a broker.

    ⚠ MISSING and STALE are the SAME verdict on purpose: both mean "last night was not verified",
    and distinguishing them would only add a branch that says the same thing.
    """
    try:
        age_h = (now.timestamp() - os.path.getmtime(path)) / 3600.0
    except Exception:
        return ("MISSING",
                "🆘 THE NIGHTLY SUPERVISOR DID NOT RUN — no verdict on disk at all. Nothing "
                "verified the timers, the services or the router overnight, and nothing repaired "
                "anything. Check `systemctl status gazbot7-nightly-supervisor`.", True)
    if age_h > MAX_AGE_H:
        return ("STALE",
                f"🆘 THE NIGHTLY SUPERVISOR DID NOT RUN LAST NIGHT — its verdict is {age_h:.1f}h "
                f"old (expected ~7h). Nothing verified the machinery overnight. Check "
                f"`systemctl status gazbot7-nightly-supervisor`.", True)
    try:
        with open(path) as fh:
            v = json.load(fh) or {}
    except Exception as e:
        return ("UNREADABLE",
                f"🆘 THE NIGHTLY SUPERVISOR'S VERDICT IS UNREADABLE ({type(e).__name__}) — treat "
                f"last night as unverified.", True)
    faults = v.get("faults") or []
    repaired = v.get("repaired") or []
    declined = v.get("declined_repairs") or []
    if faults:
        body = " | ".join(str(f) for f in faults)
        if repaired:
            body += f" || REPAIRED: {', '.join(map(str, repaired))}"
        if declined:
            body += f" || NOT repaired: {', '.join(map(str, declined))}"
        return ("FAULT", f"⚠ LAST NIGHT — {body}", True)
    extra = ""
    if repaired:
        extra += f" · repaired {', '.join(map(str, repaired))}"
    ra = v.get("router_aborts_today")
    if ra is not None:
        extra += f" · router aborts {ra}"
    return ("OK", f"✅ Last night verified clean — timers fired, services up, router deciding"
                  f"{extra}.", False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="assess and print; never send")
    a = ap.parse_args()
    now = dt.datetime.now(dt.UTC)
    status, msg, critical = assess(now)
    if a.json:
        print(json.dumps({"ts": now.isoformat(), "status": status, "critical": critical,
                          "message": msg}, indent=1))
    else:
        print(f"{status}: {msg}")
    if not a.quiet:
        try:
            from gazbot7.notify import notify
            # ⚠ mark=False on the clean line: it is a heartbeat, and marking it would put the circle
            # on 365 messages a year — exactly the dilution the 09-24 rule exists to stop. The
            # MISSING/STALE case reaches MARK_ALWAYS through "NIGHTLY SUPERVISOR" on its own.
            notify(msg, critical=critical, mark=None if critical else False)
        except Exception:
            pass
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
