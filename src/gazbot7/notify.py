"""GAZBOT V7 — operator alerts with tiers + quiet hours (S9).

Two tiers, enforced in code (V5 left quiet-hours to sweep convention and it never
held):

* **critical** — safety/CRIT (naked, drift, flatten-incomplete, a monitor CRIT).
  ALWAYS sends, any hour. Silence is never worth a naked position.
* **routine** — heartbeats / status. Suppressed 22:00–06:00 Paris so a 3am buzz
  doesn't cry wolf; the safety tier is the override.

Delivery is the alphabot2 ``notify_operator.py`` (one Telegram channel), fired via
subprocess and fail-quiet — an alerting outage must never break the caller. The
send is injectable so the gating logic is tested without touching Telegram.
Clean-room.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_PARIS = ZoneInfo("Europe/Paris")
# ★★★2026-08-20 THE ALARM CHAIN NOW LIVES IN gazbot7. It used to run the RETIRED alphabot2 tree's
# python, its notify_operator.py and its .env — so deleting a tree CLAUDE.md calls "RETIRED" would
# have silenced EVERY alert on this desk (reconcile breaches, naked positions, the peak watch) while
# notify() kept returning True. The audit found it; this closes it.
# The old paths remain as a FALLBACK, so this change cannot itself cause an outage: if the local
# copy is missing we still deliver exactly as before.
import sys as _sys

_GB = "/home/alphabot/gazbot7"
_PY = f"{_GB}/.venv/bin/python"
_SCRIPT = f"{_GB}/scripts/notify_operator.py"
_ENVFILE = f"{_GB}/data/.notify_env"          # TELEGRAM_TOKEN/CHAT, mode 600, gitignored
_LEGACY_PY = "/home/alphabot/alphabot2/.venv/bin/python"
_LEGACY_SCRIPT = "/home/alphabot/alphabot2/scripts/notify_operator.py"


# ── WEEKEND QUIET (2026-09-26) ────────────────────────────────────────────────────────────────
# ★★★ Operator, after a Saturday of alarms: "everything should be off on weekends except
# notifications about reports."
# ⚠⚠⚠ AND THE CARVE-OUT IS NOT NEGOTIABLE: SUPPRESS ONLY WHILE THE DESK IS FLAT. On 2026-08-21 four
# naked lots went through the halt into the weekend and cost -$2,149; a weekend gag that silenced
# THAT would be the worst thing in this file. So the rule is not "it is Saturday, be quiet" — it is
# "there is nothing at risk, so be quiet", which is a different and safe statement.
# ⚠ AND IT FAILS OPEN. If we cannot READ the position, we do not know it is flat, and not knowing is
# not flat — so it sends. Every error path here speaks rather than swallows.
_WEEKEND_STATE = "/home/alphabot/gazbot7/data/desk_reconcile_state.json"
_WEEKEND_RIDER = "/home/alphabot/gazbot7/data/day_rider_state.json"


def venue_shut_for_the_weekend(now: datetime) -> bool:
    """Fri 21:00Z (the CME halt) → Sun 22:00Z (the reopen). Nothing trades in that window."""
    wd, hhmm = now.weekday(), now.hour * 60 + now.minute
    if wd == 5:                                  # Saturday, all of it
        return True
    if wd == 4 and hhmm >= 21 * 60:              # Friday from the halt
        return True
    if wd == 6 and hhmm < 22 * 60:               # Sunday until the reopen
        return True
    return False


def desk_is_flat_and_verified() -> bool:
    """TRUE only when a FRESH venue read says zero AND our own book agrees.

    ⚠ Four ways to return False, and all of them mean "speak": stale read, unverified read, a venue
    position, or our book holding. "IBKR IS THE TRUTH" cuts both ways here — the venue alone is not
    enough if our own book thinks it holds something, because that disagreement is itself an alarm.
    """
    try:
        import json as _j
        import os as _os
        import time as _t
        if _t.time() - _os.path.getmtime(_WEEKEND_STATE) > 300:
            return False                          # stale is not evidence of flat
        r = (_j.load(open(_WEEKEND_STATE)) or {}).get("read1") or {}
        if r.get("ok") is not True or (r.get("venue") or 0) != 0:
            return False
        rs = _j.load(open(_WEEKEND_RIDER)) or {}
        if not rs.get("closed") and float(rs.get("qty") or 0) != 0:
            return False
        return True
    except Exception:
        return False                              # cannot tell => not flat => send


def in_quiet_hours(now: datetime) -> bool:
    """22:00–06:00 Paris — the routine-suppression window (safety overrides it)."""
    h = now.astimezone(_PARIS).hour
    return h >= 22 or h < 6


def _load_env() -> dict:
    """TELEGRAM_TOKEN/CHAT from our own file. Never raises — a missing file falls back to legacy.

    ★★★2026-08-21 THIS SWALLOWED A TOTAL ALARM OUTAGE. The file was written mode 600 root:root
    while EVERY desk service (day-rider, tournament, shadow, md, web) runs as `alphabot`. The open()
    raised PermissionError, `except Exception: pass` ate it, and the sender then printed
    "TELEGRAM_TOKEN/CHAT_ID not configured" and exited 1 — into a caller that returned True anyway.
    Five services could not page for ~12 hours and NOTHING reported it. The rider crashed, the
    account failed to reconcile and the kill switch fired; the operator found out by pressing a
    button that did nothing.

    ⚠ MISSING and UNREADABLE ARE DIFFERENT FAULTS. Missing is the documented legacy-fallback path.
    Unreadable means the credentials are RIGHT THERE and we are the wrong user — always a
    misconfiguration, never normal, so it is stated on stderr where the journal keeps it. Still
    never raises: an alarm must not be able to abort the caller that is trying to alarm.
    """
    import os as _os
    env = {}
    if not _os.path.exists(_ENVFILE):
        return env
    try:
        with open(_ENVFILE) as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as exc:
        print(f"NOTIFY: {_ENVFILE} exists but is UNREADABLE by uid {_os.getuid()} ({exc}) — "
              f"alerts from this process WILL NOT DELIVER. Fix ownership.", file=_sys.stderr)
    return env


def _subprocess_send(message: str) -> bool:
    """Deliver via OUR copy; fall back to the legacy tree so this change cannot cause an outage.

    ★2026-08-21 RETURNS TRUE ONLY ON DELIVERY. It used to return True on DISPATCH without reading
    the sender's returncode — so `notify()` reported success while the sender was exiting 1 for want
    of credentials it could not read. "The alarm IS the mitigation" (operator, on credential expiry)
    is only true if the alarm can tell you it failed. A non-zero sender now falls through to legacy,
    and if nothing delivers this says so on stderr and returns False.
    """
    import os as _os
    if _os.path.exists(_SCRIPT) and _os.path.exists(_PY):
        try:
            r = subprocess.run([_PY, _SCRIPT, message], check=False, timeout=15, cwd=_GB,
                               env={**_os.environ, **_load_env()})
            if r.returncode == 0:
                return True
            print(f"NOTIFY: primary sender exited {r.returncode} — trying legacy", file=_sys.stderr)
        except Exception as exc:
            print(f"NOTIFY: primary sender raised ({exc}) — trying legacy", file=_sys.stderr)
    try:
        r = subprocess.run([_LEGACY_PY, _LEGACY_SCRIPT, message], check=False, timeout=15,
                           cwd="/home/alphabot/alphabot2")
        if r.returncode == 0:
            return True
    except Exception:
        pass
    print(f"NOTIFY: ALERT NOT DELIVERED by any sender: {message[:120]!r}", file=_sys.stderr)
    return False


#: ★★★2026-09-24 THE ONE-GLANCE MARKER. The operator receives ~10 Telegrams a day and 85% of them
#: are informational; the four that can actually cost him money total under one a day and were
#: buried underneath. Operator: "a lot are old and not useful. theres going to be several that i
#: really need so we need to make sure theyre useful so i dont ignore."
#: A red circle on every CRITICAL alert makes the ones that demand a decision separable from the
#: ones that are just telling him something — without reading a word.
#: ⚠ APPLIED HERE, IN ONE PLACE, not at 46 call sites. A marker added per-caller drifts the moment
#: someone adds the 47th, and then the absence of a mark means nothing.
#: ⚠⚠⚠ 2026-09-24, SAME DAY, CORRECTED: `critical` was doing TWO JOBS and they are not the same
#: question. "Does this matter at 3am?" (bypass quiet hours) is NOT "is this the one to look at?"
#: (wear the mark). `rider_peak_watch` sends all four of its alerts `critical=True` — correctly,
#: because his position can still be open at 20:00Z when quiet hours start and a rung he cannot see
#: is a rung that cannot be claimed — and that alone is ~63 messages a day. Within hours of shipping
#: it, the marker was on 98% routine traffic and meant nothing, which is precisely the failure the
#: comment above warns about, arrived at from the other direction.
#: **So the two jobs are now separate flags**: `critical` = bypasses quiet hours · `mark` = wears the
#: circle, DEFAULTING TO `critical` so all 56 existing call sites are unchanged.
#: ★ THE RULE FOR `mark=False`: the circle marks the START of something that needs him — an episode
#: opening, a fault beginning — never its CONTINUATION. Being told six more times about a position
#: he has already been told to watch is not news.
CRITICAL_MARK = "🔴 "


def notify(message: str, *, critical: bool = False, mark: bool | None = None,
           weekend_ok: bool = False, now: datetime | None = None, send=None) -> bool:
    """Send an operator alert. Returns True if sent. Fail-quiet.

    `critical` — bypass quiet hours. "This matters at 3am."
    `mark`     — wear CRITICAL_MARK. "This is the one to look at."
                 Defaults to `critical`; pass False for an alert that must reach him at any hour
                 but is the CONTINUATION of something he has already been told about.

    ⚠ A routine alert can never be marked: if it is not worth waking him for, the circle would be
    claiming an urgency the quiet-hours rule itself denies.
    """
    now = now or datetime.now(UTC)
    # ★★★ WEEKEND QUIET, and it OUTRANKS `critical` — a critical alert about a desk that is shut and
    # flat is still noise, and it was the 🔴 ones that woke him on a Saturday.
    # ⚠ `weekend_ok=True` is for the report chain, which is the one thing he asked to keep.
    if not weekend_ok and venue_shut_for_the_weekend(now) and desk_is_flat_and_verified():
        return False
    if not critical and in_quiet_hours(now):
        return False
    if mark is None:
        mark = critical
    # ⚠ Never double-mark: a caller that already prefixed it (or a retry of the same text) must not
    # accumulate circles.
    if mark and critical and not message.startswith(CRITICAL_MARK):
        message = CRITICAL_MARK + message
    return (send or _subprocess_send)(message)


# ── repeat suppression ────────────────────────────────────────────────────────
# ★★2026-08-14 A CORRECT DECISION ANNOUNCED ON EVERY TICK IS AN OUTAGE OF THE ALARM CHANNEL.
# The day-rider stands down when the venue holds a position it did not open — the right call, and
# the whole point of the 08-06 ownership gate. But the branch that says so is reached on EVERY tick
# outside the rider's window (`mod < OPEN_UTC_MIN` is true all morning), so with the tournament
# legitimately short the operator got the same message every minute for hours, while the desk
# reconciler was independently confirming `venue -2 = tournament -2 + rider +0, unaccounted +0`.
#
# That is not a noisy nicety: Telegram is where CRITICAL desk alarms land. Training the operator to
# swipe past this message trains them to swipe past a naked position. Steady state must be silent so
# that CHANGE is loud.
#
# ⚠ THIS LAYER FAILS **OPEN**. Every error path sends. A dedupe store that suppressed an alarm
# because its own JSON was corrupt would be exactly the instrument-that-reports-healthy failure this
# desk keeps meeting — the alarm would be lost and nothing would say so.

import json as _json
import os as _os

_DEDUPE_PATH = "/home/alphabot/gazbot7/data/notify_dedupe.json"


def _dedupe_load(path: str) -> dict:
    try:
        with open(path) as fh:
            d = _json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def dedupe_ok(key: str, message: str, *, cooldown_s: float = 3600.0,
              now: datetime | None = None, path: str | None = None) -> bool:
    """Should this (key, message) be sent now? Records the send when it returns True.

    Sends when the key is new, when the MESSAGE TEXT changed (so a position going -2 → -4 alarms
    immediately rather than hiding behind the cooldown), or when `cooldown_s` has elapsed. The
    message-change rule is what makes this safe to use on alarms that carry live numbers.

    ⚠ Returns True on ANY failure — see the note above. Suppression is only ever the result of a
    successful, positive check that the same thing was already said recently.

    Note it records the INTENT to send. `notify()` may still drop a routine alert in quiet hours;
    the cooldown then expires normally and the next tick retries, which is the desired behaviour for
    a steady-state condition.
    """
    # ★ Resolve the path at CALL time, never as a default arg — a default binds at def
    # time, so a test (or a redirected data dir) could not override it and would silently
    # read and write the PRODUCTION store. Same trap already caught in deskrecon.
    path = path or _DEDUPE_PATH
    try:
        now = now or datetime.now(UTC)
        ts = now.timestamp()
        store = _dedupe_load(path)
        prev = store.get(key)
        if isinstance(prev, dict) and prev.get("message") == message:
            last = float(prev.get("ts") or 0.0)
            if 0.0 <= ts - last < float(cooldown_s):
                return False                      # same thing, said recently — stay quiet
        store[key] = {"ts": ts, "message": message}
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            _json.dump(store, fh, indent=1, sort_keys=True)
        _os.replace(tmp, path)                    # atomic — a torn file would fail open next tick
        return True
    except Exception:
        return True                               # FAIL OPEN. Never lose an alarm to bookkeeping.


def dedupe_clear(key: str, *, path: str | None = None) -> None:
    """Forget `key`, so the condition re-arms and alarms immediately if it returns.

    Call this the moment the condition RESOLVES. Without it a condition that clears and comes back
    inside the cooldown would be silently swallowed — the cooldown is meant to suppress a continuing
    state, never a new occurrence of one.
    """
    path = path or _DEDUPE_PATH
    try:
        store = _dedupe_load(path)
        if key in store:
            del store[key]
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                _json.dump(store, fh, indent=1, sort_keys=True)
            _os.replace(tmp, path)
    except Exception:
        pass
