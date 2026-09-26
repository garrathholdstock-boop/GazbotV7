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
#
# ★★★2026-09-26 AUDIT — THIS LIST HAD NOT GROWN SINCE 2026-08-13 AND EVERY SAFETY WATCHER BUILT
# SINCE WAS MISSING FROM IT. gateway-watch (the wedge detector, which has cost $364 and $2,149
# when absent), step-away (his away-guard), web (his BUTTONS), tgbot (phone control),
# rider-peak-watch (his eyes) — all ran unwatched. `Restart=always` covers a CRASH; it does not
# cover a unit stopped by hand, one systemd has given up on after StartLimitBurst, or one that is
# running and wedged. Nothing paged if any of them was simply down.
# ⚠ Each entry is a unit whose ABSENCE costs money or costs him a decision. A watcher nobody
# watches is [[an-instrument-that-reports-healthy-about-something-it-does-not-check]] one level up.
REQUIRED_SERVICES = [
    # the desks and the feed
    "gazbot7-tournament", "gazbot7-md", "gazbot7-shadow",
    "gazbot7-depth-capture", "gazbot7-router-watch",
    # ★ the safety watchers — added 2026-09-26
    "gazbot7-gateway-watch",       # the wedge detector; its absence is measured in hours blind
    "gazbot7-step-away",           # writes his claim when he is away; armed means nothing if down
    # ★ his own controls — if these are down he has no hands, and nothing said so
    "gazbot7-web",                 # the dashboard AND the BUY/SELL/CLAIM buttons
    "gazbot7-tgbot",               # phone control
    # ★ his eyes
    "gazbot7-rider-peak-watch", "gazbot7-leg-watch", "gazbot7-breadth-watch",
]

# (unit, max hours since last fire). Only frequent timers — a weekly one has not "failed" by not
# having run today.
# ★★2026-09-26 AUDIT — IT CHECKED THE ROUTER EVERY 0.25h AND NEVER CHECKED THE RECONCILER. The
# four added below are the ones whose silence is most expensive: the 30-second cross-desk
# invariant, the only risk rule, the alarm that watches whether his BUTTON landed, and the
# watchdog that flattens a position nobody is managing.
TIMER_FRESHNESS = {
    "gazbot7-router-tick.timer": 0.25,
    "gazbot7-router-health.timer": 0.5,
    "gazbot7-day-rider.timer": 0.1,
    "gazbot7-monitor.timer": 1.0,
    "gazbot7-claude-job@sweep.timer": 6.0,
    # ★ added 2026-09-26
    "gazbot7-desk-reconcile.timer": 0.1,      # every 30s — THE safety layer
    "gazbot7-daily-loss-limit.timer": 0.25,   # every 2min — the only risk rule that runs
    "gazbot7-request-watch.timer": 0.1,       # every 60s — did his press land
    "gazbot7-day-rider-watchdog.timer": 0.25, # every 2min — flattens an unmanaged position
    # ★2026-09-26, added by the review of the audit's own work: the commit that fixed "no safety
    # watcher is watched" installed THREE new timers and watched none of them, which is the same
    # omission one iteration later. equity-guard is the only thing reading the money; book-recon is
    # the only thing reconciling it daily; overnight-allclear is what makes the supervisor's own
    # death detectable, so its silence is the most expensive of the three.
    "gazbot7-equity-guard.timer": 0.25,       # every 2min — the account reader
    "gazbot7-book-recon.timer": 30.0,         # daily 21:34Z — book vs broker
    "gazbot7-overnight-allclear.timer": 30.0, # daily 06:05 Paris — did the supervisor run
    "gazbot7-deadman.timer": 0.5,             # every 5min — the off-box heartbeat
}
JOB_MAX_AGE_H = {"sweep": 6, "hour-watch": 26, "ledger-review": 6, "nightly-review": 30}


def sh(*cmd: str, timeout: int = 20) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def supervisor_message(faults: list[str], repaired: list[str], declined: list[str],
                       flat: bool, router_aborts: int | None = None) -> tuple[str, bool, bool]:
    """(text, critical, mark) for the nightly message. ALWAYS returns one — never None.

    ★★★2026-09-26 IT NOW SPEAKS EVERY NIGHT, CLEAN OR NOT, SO SILENCE IS THE ALARM. Before this
    it sent only `if faults or repaired`, which made a clean night and a DEAD SUPERVISOR produce
    byte-identical output: nothing. Nothing else on the box checks this job — it is the thing that
    checks the others — and there is no off-box watcher, so its own death was undetectable by
    construction. Operator, 2026-09-26: "so we never dont know something is happening in the
    background."

    ⚠ The all-clear is deliberately NOT critical and NOT marked. It must not bypass quiet hours and
    must never wear 🔴: it is a heartbeat he should be able to ignore on any one night and notice
    the absence of across several — the opposite urgency to a fault.
    ⚠ Weekend quiet still holds it, and that is correct: while the venue is shut and the desk is
    verified flat there is nothing to be silent ABOUT, so a missing Saturday line is not evidence.
    A missing weekday line is.
    """
    tail = ""
    if repaired:
        tail += f" || REPAIRED: {', '.join(repaired)}"
    if declined:
        tail += f" || NOT repaired: {', '.join(declined)}"
    if faults:
        return (f"⚠ GAZBOT NIGHTLY SUPERVISOR — {' | '.join(faults)}{tail}"[:900], True, True)
    # ⚠⚠⚠ 2026-09-26, CORRECTED THE SAME DAY BY AN ADVERSARIAL REVIEW OF MY OWN FIX.
    # The all-clear used to be SENT from here. It never arrived once: this job fires 21:40 UTC =
    # 23:40 Paris (22:40 CET) and quiet hours are 22:00-06:00 Paris, so a correctly non-critical
    # heartbeat was suppressed EVERY NIGHT OF THE YEAR — byte-identical silence to the bug it
    # replaced, with a test pinning it in place.
    # The design error was deeper than the timestamp: A PROCESS CANNOT REPORT ITS OWN ABSENCE.
    # "The supervisor tells you it is alive" fails precisely when the supervisor is what died.
    # So the clean-night line moved to `scripts/overnight_allclear.py` — a DIFFERENT process, on a
    # DIFFERENT timer, at 06:05 Paris just after quiet hours end — which reads the verdict this job
    # leaves on disk and pages CRITICAL if it is missing or stale. Faults still page from here, in
    # real time, and they are critical so quiet hours never touched them.
    body = (f"all clear — {len(REQUIRED_SERVICES)} services up, {len(TIMER_FRESHNESS)} timers "
            f"fired, router deciding, flat={flat}")
    # ★2026-09-26 the router's own availability, so isolated ABORTs (finding 16) have somewhere to
    # be seen. A handful a day is ordinary CLI flakiness on a benching-only router and is NOT a
    # fault; a rising number is the tell that the credential is going, which has cost 10.5h before.
    if router_aborts is not None:
        body += f" · router aborts today {router_aborts}"
    return (f"✅ GAZBOT NIGHTLY SUPERVISOR — {body}{tail}"[:900], False, False)


def timer_is_dormant(unit: str, max_h: float) -> tuple[bool, str]:
    """Is this timer simply NOT DUE, rather than failing to fire?

    ★★2026-09-26 "OLD" IS NOT "STALE" IF THE SCHEDULE NEVER CALLED FOR IT. This supervisor runs
    EVERY night (`*-*-*`) while several timers it checks are weekday-only — `claude-job@sweep` is
    `Mon-Fri`. So on Saturday and Sunday nights sweep's last trigger was legitimately 24-48h old
    against a 6h expectation, and this raised a CRITICAL fault for a timer working exactly as
    designed: TWO FALSE CRITICALS EVERY WEEKEND, which is how a real one gets ignored.

    ⚠ SYSTEMD IS THE AUTHORITY ON ITS OWN CALENDAR. Do not re-parse OnCalendar here — that is a
    second implementation of a schedule and it would drift from the first. If the NEXT elapse is
    further away than the freshness window, the timer is dormant, not stale.

    ⚠ FAILS LOUD. An unreadable or absent next-elapse returns False, because "I cannot tell
    whether it was due" must never read as "it was not due".
    """
    nxt = sh("systemctl", "show", unit, "-p", "NextElapseUSecRealtime", "--value")
    if nxt in ("0", "n/a", ""):
        return False, nxt
    ts = sh("date", "-d", nxt, "+%s")
    if not ts.isdigit():
        return False, nxt
    return ((int(ts) - time.time()) / 3600 > max_h), nxt


def desk_is_flat() -> tuple[bool, str]:
    """Repair only when flat. A restart re-adopts slots from the ledger; doing that while holding is
    exactly the risk CLAUDE.md warns about.

    ★★★2026-09-26 THIS READ `core_health.flat`, WHICH IS TOURNAMENT-SCOPED. It counts this desk's
    own slots and knows nothing about the day-rider — so it called the desk flat while the venue
    held 4 rider lots (08-21, 811 of 817 router ticks). This gate decides whether it is safe to
    RESTART SERVICES, so believing it meant: if the 20:40Z flat ever failed and the rider was still
    holding, the supervisor would restart services on top of a live naked position and log that the
    desk was flat.
    Now it reads `desk_flat`, which is tournament AND rider, published by the same writer.
    ⚠ FAIL-CLOSED ON AN OLD FILE: if `desk_flat` is absent the tournament has not yet been
    restarted onto the code that publishes it, and the honest answer is "cannot tell", which must
    mean NOT flat. Declining a repair costs a night; restarting onto a naked position costs money.
    """
    try:
        h = json.load(open(f"{GB}/data/core_health.json"))
    except Exception as e:
        return False, f"core_health unreadable ({e}) — treating as NOT flat"
    if "desk_flat" not in h:
        return False, ("core_health has no desk_flat field (tournament not yet restarted onto the "
                       "2026-09-26 code) — treating as NOT flat rather than trusting the "
                       "tournament-scoped `flat`")
    return bool(h.get("desk_flat")), (f"desk_flat={h.get('desk_flat')} "
                                      f"({h.get('desk_flat_note')}) halted={h.get('halted')}")

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
    detail["router_aborts_today"] = rhj.get("aborts_today")
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
        if age_h <= max_h:
            continue
        # ★★2026-09-26 "OLD" IS NOT "STALE" IF THE SCHEDULE NEVER CALLED FOR IT. This supervisor
        # runs EVERY night (`*-*-*`) while some timers it checks are weekday-only — e.g.
        # claude-job@sweep is `Mon-Fri`. So on Saturday and Sunday nights sweep's last trigger was
        # legitimately 24-48h ago against a 6h expectation, and this raised a CRITICAL fault for a
        # timer working exactly as designed. TWO FALSE CRITICALS EVERY WEEKEND, which is precisely
        # how a real one gets ignored.
        # ⚠ SYSTEMD IS THE AUTHORITY ON ITS OWN CALENDAR — do not re-parse OnCalendar here; that
        # is a second implementation of a schedule and it would drift. If the NEXT elapse is
        # further away than the freshness window, the timer is DORMANT BY SCHEDULE, not stale.
        # ⚠ FAILS LOUD: an unreadable or absent next-elapse falls through to the stale branch,
        # because "I cannot tell whether it was due" must not read as "it was not due".
        dormant, nxt = timer_is_dormant(unit, max_h)
        if dormant:
            notes.append(f"{unit} last fired {age_h:.1f}h ago but is DORMANT BY SCHEDULE "
                         f"(next elapse {nxt}) — not due, not stale")
            continue
        stale.append(f"{unit} last fired {age_h:.1f}h ago (expected within {max_h}h)")
    if stale:
        faults.append("TIMERS ACTIVE BUT NOT FIRING: " + "; ".join(stale))
    detail["stale_timers"] = stale

    # ★★★2026-09-26 THE THIRD INSTANCE OF THIS BUG CLASS, SO IT GETS A CHECK.
    # A data file created by ROOT that the service which APPENDS to it (User=alphabot) then cannot
    # write. Twice already:
    #   · 08-21 `data/.notify_env` written 600 root:root → FIVE services could not page for ~12h
    #     while the rider crashed mid-flatten and the cross-desk kill fired. Sweep read green.
    #   · 09-26 `data/equity_guard.jsonl` created by a root test run → the brand-new account reader
    #     logged "series write failed: PermissionError" every 2 minutes for 25 minutes. The
    #     measurement the job exists for was not accumulating, and only a soak caught it.
    # ⚠ The signature is the desk's signature: the job RUNS, exits 0, and cannot record.
    #
    # ⚠⚠ APPEND-ONLY FILES, AND ONLY THOSE — this list was WRONG on its first cut and flagged seven
    # files that were perfectly fine. The distinction is the write PATTERN, not the ownership:
    #   · tmp + os.replace (every state/json writer here) needs DIRECTORY write, so a root-owned
    #     target is harmless — verified by running tgbot's exact write pattern as alphabot against
    #     gate_switches.env: it SUCCEEDED. Flagging those would have produced 7 nightly false faults,
    #     which is how a real one gets ignored.
    #   · open(path, "a") needs FILE write. That is the case that actually broke, twice.
    # Each entry is (file, the unix user of the service that APPENDS to it).
    APPEND_WRITERS = (
        ("equity_guard.jsonl", "alphabot"),      # gazbot7-equity-guard
        ("equity_guard.log", "alphabot"),
        ("deadman.log", "alphabot"),             # gazbot7-deadman
        ("gateway_watch.jsonl", "root"),         # gazbot7-gateway-watch runs as root (docker restart)
        ("gateway_watch.log", "root"),
        ("router_headless.log", "root"),         # gazbot7-router-tick
        ("router_trial_log.txt", "root"),
        ("operator_reads.jsonl", "root"),        # gazbot7-capture-read-*
    )
    bad_owner = []
    try:
        import pwd
        for rel, user in APPEND_WRITERS:
            fp = f"{GB}/data/{rel}"
            if not os.path.exists(fp):
                continue                          # not yet created is not a fault
            try:
                uid = pwd.getpwnam(user).pw_uid
            except KeyError:
                continue
            if uid == 0:
                continue                          # root bypasses file permissions
            st = os.stat(fp)
            ok = (st.st_uid == uid and st.st_mode & 0o200) or (st.st_mode & 0o002)
            if not ok:
                bad_owner.append(f"{rel} needs append by {user} but is uid {st.st_uid} "
                                 f"mode {oct(st.st_mode & 0o777)}")
    except Exception as e:
        notes.append(f"could not check append-file ownership ({type(e).__name__})")
    if bad_owner:
        faults.append("APPEND-ONLY FILES NOT WRITABLE BY THEIR SERVICE (the 08-21 shape): "
                      + "; ".join(bad_owner))
    detail["unwritable_files"] = bad_owner

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
            # ★2026-09-26 the same dormancy rule as the timer check above, for the same reason: a
            # weekday-only job has not "stopped" by not having run on a Saturday. Asked of the
            # job's own TIMER, so the two checks cannot disagree about one schedule.
            dormant, nxt = timer_is_dormant(f"gazbot7-claude-job@{name}.timer", max_h)
            if age_h > max_h and dormant:
                notes.append(f"JOB {name} last ran {age_h:.1f}h ago but its timer is DORMANT BY "
                             f"SCHEDULE (next {nxt}) — not due, not stopped")
            elif age_h > max_h:
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
           # ★2026-09-26 carried into the file so scripts/overnight_allclear.py can report it in
           # the morning line — the router's own availability, where its TREND is visible.
           "router_aborts_today": detail.get("router_aborts_today"),
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

    # ★ Faults and repairs page from here IN REAL TIME (critical, so quiet hours never gated them).
    # The CLEAN-night line is deliberately NOT sent from here — see supervisor_message(). It is
    # delivered at 06:05 Paris by scripts/overnight_allclear.py, which reads the verdict file
    # written just above and pages critical if it is missing or stale.
    if not a.dry_run and (faults or repaired):
        try:
            from gazbot7.notify import notify
            text, critical, mark = supervisor_message(faults, repaired, declined, flat,
                                                      detail.get("router_aborts_today"))
            notify(text, critical=critical, mark=mark)
        except Exception:
            pass
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
