#!/usr/bin/env python3
"""THE UNREAD-REQUEST ALARM — page when the operator's button reaches nobody.

★★★ WHY (2026-09-17). The operator pressed Claim at 05:39:31 on a 4-lot LONG that was +$262. The
gateway's accept queue had been full since 00:40, so every NEW connection hung while every
already-open one kept working — the rider timed out 244 consecutive times, exited 0 each time, and
wrote a FRESH HEARTBEAT every minute. systemd green, sweep green, dashboard green. The claim sat
unread for 27 minutes, EXPIRED at CLAIM_MAX_AGE_S (15 min), and by the time he found it himself the
position was -$316. Nothing in the desk was watching the one thing that mattered: THE PRESS ITSELF.

★★ THIS WATCHES THE REQUEST, NOT THE SERVICE. Every other instrument here asks "is the rider
alive?" and gets a truthful yes. This asks the only question the operator cares about — "did my
button DO anything?" — and that question has exactly one honest source: the file still being there.
The rider DELETES a request when it consumes it, so `exists and old` IS unread. There is no
inference, no heartbeat, no liveness proxy that can go stale in the wrong direction.

⚠⚠ IT ALSO CATCHES A KNOWN-OPEN BUG. `day_rider.py` takes the `owns_position` branch (:978) before
`buy_requested()` (:1017), so A BUY PRESSED WHILE THE RIDER HOLDS IS NEVER READ — it ages out in
silence while the dashboard says "requested". That defect is documented and deliberately not fixed
(the fix touches the live order path). Until it is, this is what makes it audible.

⚠⚠⚠ READ-ONLY. It does not consume, clear, rewrite or create a request file, and it places no
order. A second reader that disposed of a request would silently EAT THE OPERATOR'S PRESS — the
same hazard capture_operator_read.py is built around. tests/test_request_watch.py asserts this
against the SOURCE.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

DATA = "/home/alphabot/gazbot7/data"
LOG = os.path.join(DATA, "request_watch.log")

# The rider ticks every 60s and the fast path is ~1.4s, so 120s is already several missed cycles —
# late enough that a slow tick is not an alarm, early enough to beat CLAIM_MAX_AGE_S (15 min) by a
# wide margin. The whole point is to page while the press is still LIVE and can still be re-made.
WARN_AGE_S = float(os.environ.get("REQUEST_WARN_AGE_S", "120"))

# ⚠ Ages, not names: what matters is how long the operator has been waiting, per button.
REQUESTS = (
    ("day_rider_claim.txt", "CLAIM", 15 * 60),   # CLAIM_MAX_AGE_S
    ("day_rider_buy.txt", "BUY/SELL", 5 * 60),   # BUY_MAX_AGE_S
)


def log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line)


def age_of(path: str) -> float | None:
    """Seconds since the request was WRITTEN, from its own ISO stamp — not from mtime.

    ⚠ The stamp is the operator's press time and mtime is the filesystem's; they diverge whenever
    anything touches the file (the buy path's ExecStartPre copies it). The press is what we are
    timing, so read the press. Falls back to mtime only if the content is unreadable, because a
    malformed request that nobody can consume is still a stuck request worth paging about.
    """
    try:
        raw = open(os.path.join(DATA, path)).read().strip()
    except FileNotFoundError:
        return None                      # consumed (or never pressed) — the healthy case
    except Exception:
        raw = ""
    stamp = raw.partition("|")[0].strip()
    try:
        return (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(stamp)).total_seconds()
    except Exception:
        try:
            return dt.datetime.now(dt.UTC).timestamp() - os.path.getmtime(os.path.join(DATA, path))
        except Exception:
            return None


def main() -> int:
    stuck = []
    for path, label, expiry in REQUESTS:
        age = age_of(path)
        if age is None or age < WARN_AGE_S:
            continue
        # ⚠ Say whether the press can still be honoured. "Your button did nothing" and "your button
        # did nothing AND has now expired" are different messages and demand different actions.
        dead = age > expiry
        stuck.append(
            f"{label} pressed {age/60:.0f} min ago and STILL UNREAD"
            + (f" — it has EXPIRED (limit {expiry//60} min), so it will NEVER fire. RE-PRESS."
               if dead else
               f" — it expires in {(expiry-age)/60:.0f} min.")
        )
    if not stuck:
        log("ok — no unread requests")
        return 0

    why = []
    try:                                  # name the likeliest cause rather than make him hunt
        import json
        st = json.load(open(os.path.join(DATA, "day_rider_state.json")))
        if not st.get("venue_ok"):
            why.append(f"the rider CANNOT REACH THE BROKER ({str(st.get('note'))[:60]})")
        if st.get("qty") and not st.get("closed"):
            why.append(f"it holds {st.get('qty')} lot(s)")
    except Exception:
        pass
    msg = ("⚠⚠ DAY RIDER: " + " · ".join(stuck)
           + (" — likely because " + " and ".join(why) if why else "")
           + ". The position is UNMANAGED until this clears.")
    log(msg)
    try:
        from gazbot7.notify import dedupe_ok, notify
        # Key on the SITUATION, not the text: a claim stuck for 3 min and the same claim stuck for
        # 9 min are the same outage and must not page twice a minute. Dedupe FAILS OPEN.
        if dedupe_ok("request_watch.stuck", msg, cooldown_s=600):
            notify(msg, critical=True)
    except Exception as e:
        log(f"NOTIFY FAILED: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
