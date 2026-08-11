#!/usr/bin/env python3
"""ROUTER WATCH — DURABLE. Runs router_watch.py forever and gives its events a consumer
that survives a session ending.

★ WHY THIS EXISTS (operator, 2026-08-11: "make the watcher durable").
`router_watch.py` was only ever run under a chat Monitor: each event woke Claude in-chat
and Claude decided. That means between sessions NOTHING consumed its events, and during a
session the operator spotted the US-open reversal before the desk did. The durable 5-min
tick is the desk's floor; this is the FAST LANE on top of it, and now it runs with or
without a session.

★ WHAT IT DOES WITH AN EVENT — deliberately only two things, neither of them clever:
  · CRITICAL health events (⚠HALT / ⚠NAKED / ⚠FEED-STALE / ⚠AUDIT-STALE) -> text the
    operator immediately. These are the ones where five minutes of waiting is the damage.
  · REGIME / BREAK / BLEED events -> trigger ONE out-of-band run of the existing durable
    tick, so a real regime change is judged within ~30s instead of waiting up to 5 minutes.

★★ WHAT IT DOES NOT DO, AND MUST NOT. It NEVER writes gate_switches.env and never makes a
routing decision of its own. It only asks the existing tick to run early. Every fail-safe
that makes the tick safe — the JSON parse guard, PINNED, benching-only, the O_EXCL lock on
gate_switches.env — stays exactly where it is, in one place. A second thing that could move
switches is how you get two routers fighting, which is the failure this whole architecture
was built to avoid.

★ THE CHURN GUARD IS THE LOAD-BEARING PART. Today's bad-call ledger records four flips on
one gate in 55 minutes, and an event-triggered tick is a machine for making that worse: the
tape emits events fastest exactly when it is choppiest. So triggers are rate-limited three
ways — a minimum gap, an hourly ceiling, and a refusal to run while a tick is already
running. When the ceiling bites it SAYS SO in the log rather than dropping events silently,
because a silent cap reads as "nothing happened" (the no-silent-caps rule).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

GB = "/home/alphabot/gazbot7"
PY = f"{GB}/.venv/bin/python"
WATCH = f"{GB}/scripts/router_watch.py"
TICK = f"{GB}/scripts/router_tick_durable.py"
LOG = f"{GB}/data/router_watch_events.log"
TICK_LOCK = f"{GB}/data/router_tick_running.lock"

# Rate limits. MIN_GAP is the dominant one: a regime change that is real is still real 4
# minutes later, and the 5-min timer is always underneath as the floor.
MIN_GAP_S = 240          # never trigger two out-of-band ticks closer than this
MAX_PER_HOUR = 6         # ceiling; the timer still ticks 12x/hour regardless
STALE_LOCK_S = 300       # a tick that ran longer than this is dead, not running

# Event routing. Matched as substrings against the emitted line — verified against every
# emit() in router_watch.py, because a key that matches nothing fails SILENTLY and this
# whole service would look healthy while doing nothing.
CRITICAL = ("⚠HALT", "⚠NAKED", "⚠FEED-STALE", "⚠AUDIT-STALE",
            "⚠DESK-MISMATCH", "⚠DAY-RIDER STALE-FLAT", "DAY-RIDER BLEED")
TRIGGER = ("BREAK↑", "BREAK↓", "REGIME→TREND", "REGIME→CHOP", "WALL-OF-STOP", "BLEED")
# ⚠ REGIME→MIXED is deliberately NOT a trigger. It is the "no longer definite" state — the
# absence of a regime, not the arrival of one — and arming on the absence of a signal is the
# lapsed-bench error the ledger has billed five times. The 5-min timer picks it up anyway.
# ⚠ NEW-DAY is log-only: bookkeeping, not tape.
# ★★ NO DAY-RIDER EVENT TRIGGERS A ROUTER TICK, and that is deliberate. The tick moves
# gate_switches.env, which controls TOURNAMENT gates only — it has no authority over the day
# rider whatsoever (separate service, own clientId, own switch in day_rider.env). Firing a
# tick because the RIDER is bleeding would spend a routing decision on the wrong desk and
# churn gates that have nothing to do with it. Rider events go to the OPERATOR, who is the
# only one who can act on them (the Claim-profit button, or day_rider.env).
# DAY-RIDER ENTERED / CLOSED / NO-DETECT are log-only: worth a record, not worth a 3am text.
WATCH_ERROR = "⚠WATCH-ERROR"
WATCH_ERROR_NOTIFY_GAP_S = 3600   # the watcher failing is worth ONE text an hour, not one a poll


def now_s() -> float:
    return time.time()


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def notify(msg: str, critical: bool = False) -> None:
    """Text the operator. Never let a notify failure kill the watcher — a watcher that dies
    because Telegram is down is worse than a missed text."""
    try:
        subprocess.run(
            [PY, "-c", "import sys; from gazbot7.notify import notify; "
                       "notify(sys.argv[1], critical=sys.argv[2]=='1')", msg, "1" if critical else "0"],
            cwd=GB, env={**os.environ, "PYTHONPATH": "src"},
            capture_output=True, timeout=30,
        )
    except Exception as e:
        log(f"NOTIFY-FAILED {e}")


def tick_running() -> bool:
    """True if a router tick is in flight. Stale locks are cleared rather than trusted —
    an unreleased lock file must not wedge the fast lane shut forever."""
    try:
        age = time.time() - os.path.getmtime(TICK_LOCK)
    except FileNotFoundError:
        return False
    except Exception:
        return True                      # unreadable -> assume running, fail safe
    if age > STALE_LOCK_S:
        try:
            os.remove(TICK_LOCK)
            log(f"cleared stale tick lock ({age:.0f}s old)")
        except Exception:
            pass
        return False
    return True


def run_tick(why: str) -> None:
    open(TICK_LOCK, "w").close()
    try:
        r = subprocess.run([PY, TICK], cwd=GB, capture_output=True, text=True, timeout=280,
                           env={**os.environ, "HOME": "/root",
                                "PATH": "/root/.local/bin:/usr/local/bin:/usr/bin:/bin"})
        log(f"TICK-DONE rc={r.returncode} ({why})")
    except subprocess.TimeoutExpired:
        log(f"TICK-TIMEOUT after 280s ({why}) — the 5-min timer still covers the desk")
    except Exception as e:
        log(f"TICK-FAILED {e} ({why})")
    finally:
        try:
            os.remove(TICK_LOCK)
        except Exception:
            pass


def main() -> int:
    log("WATCH-DURABLE START — fast lane armed; the 5-min timer remains the floor")
    fired: list[float] = []
    last = 0.0
    errs, last_err_notify = 0, 0.0
    # Unbuffered child, stderr merged in: a traceback from the watcher must reach this log
    # rather than vanishing. Silence is not success.
    proc = subprocess.Popen([PY, "-u", WATCH], cwd=GB, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            env={**os.environ, "PYTHONPATH": "src"})
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            log(f"EVENT {line}")

            # The WATCHER'S OWN failures. Emitted from its poll-loop exception handler, so
            # they can repeat every poll — but a watcher quietly erroring forever is exactly
            # the dead-instrument failure this desk keeps re-learning, so it must not be
            # log-only either. One text an hour: loud enough to notice, too rare to ignore.
            if WATCH_ERROR in line:
                errs += 1
                if now_s() - last_err_notify > WATCH_ERROR_NOTIFY_GAP_S:
                    last_err_notify = now_s()
                    notify(f"GAZBOT ROUTER WATCH degraded — {errs} watch-errors, latest: "
                           f"{line[:160]}. Events may be MISSING; the 5-min tick still runs.",
                           critical=True)
                    log(f"  -> operator notified (watch degraded, {errs} errors)")
                continue

            if any(k in line for k in CRITICAL):
                notify(f"GAZBOT ROUTER WATCH — {line}", critical=True)
                log("  -> operator notified (critical)")
                continue

            if not any(k in line for k in TRIGGER):
                continue                                  # WATCH START and the like

            now = time.time()
            fired = [t for t in fired if now - t < 3600]
            if now - last < MIN_GAP_S:
                log(f"  -> tick SUPPRESSED: {MIN_GAP_S - (now - last):.0f}s left on the "
                    f"{MIN_GAP_S}s gap (the 5-min timer still covers this)")
            elif len(fired) >= MAX_PER_HOUR:
                log(f"  -> tick SUPPRESSED: hourly ceiling {MAX_PER_HOUR} reached — this is "
                    f"a CHOPPY hour emitting events fast, exactly when extra ticks churn most")
            elif tick_running():
                log("  -> tick SUPPRESSED: a router tick is already in flight")
            else:
                last, _ = now, fired.append(now)
                log(f"  -> triggering out-of-band router tick ({len(fired)}/{MAX_PER_HOUR} this hour)")
                run_tick(line[:120])
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
    rc = proc.wait()
    log(f"WATCH-DURABLE EXIT — child rc={rc} (systemd will restart)")
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
