#!/usr/bin/env python3
"""STEP AWAY — "I'm going into a meeting. Look after this."

Operator, 2026-09-18: *"so if im watching it but then i meed to go into a meeting. i arm those and
then know it will take care of itself snd i wont lose heaps."*

★★★ WHY ARM-WHEN-AWAY AND NOT ALWAYS-ON. Measured over his last 49 entries (MAE from the 5s tape):

    armed ALWAYS                   49 entries · 20 fire · net +$3,352
    armed while he is WATCHING     37 entries · 11 fire · net    +$95   <- worthless
    armed while he is AWAY (>=90m) 12 entries ·  9 fire · net +$3,257   <- nearly all of it

Always-on is not merely useless when he is present, it is EXPENSIVE: it turns his +$819 of 09-16
and his +$623 of 09-15 into -$200 apiece. The value is entirely in the trades nobody was watching —
which is the same finding as the hold-time table (over-8h holds: 0 winners from 4, -$6,612).

★★ IT NEVER TOUCHES THE BROKER. On breach it writes `day_rider_claim.txt` — THE SAME FILE HIS OWN
CLAIM BUTTON WRITES — and the rider acts on its own cycle through its own ownership check, picked up
by the existing inotify fast path in ~0.02s. That indirection is the whole design: a button that
reached the broker directly is how 2026-08-06 happened, when a flatten fired without checking whose
position it was and took the tournament's with it.
⚠ It therefore CANNOT open, size, reverse or add. The worst a bug here can do is close a position
early. The worst its ABSENCE can do is -$2,656, which is what 2026-09-10 actually cost.

⚠⚠ ONE-SHOT, AND IT NEVER SURVIVES THE SESSION. It disarms the moment it fires (the position is
gone; a still-armed killer would fire again against the NEXT one) and it disarms at the 22:00Z
reopen, so an arming he forgot on Friday cannot flatten Monday's trade seconds after it opens. That
is the CLAIM_MAX_AGE_S lesson, which exists because exactly that shape of bug was reasoned about.

⚠ NOT PRE-REGISTERED. The $200 came from him and tests well on 49 entries — which is precisely the
shape of number this desk pre-registers before trusting. Treat the level as HIS CHOICE, not as a
fitted optimum, and do not tune it.

  PYTHONPATH=src .venv/bin/python scripts/step_away.py          # the watcher
  PYTHONPATH=src .venv/bin/python scripts/step_away.py --status
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

from rider_peak_watch import open_pnl                     # noqa: E402  pure function, no order path

GB = "/home/alphabot/gazbot7"
STATE = f"{GB}/data/step_away.json"
RIDER = f"{GB}/data/day_rider_state.json"
CLAIM = f"{GB}/data/day_rider_claim.txt"
CAP = f"{GB}/data/capture.db"
LOG = f"{GB}/data/step_away.log"
POLL_S = 2.0            # 1-2Hz is the right order: the trigger is ~25pt on 4 lots and the claim
                        # fast path lands in 0.02s, so the tick is not the binding constraint.
STALE_PX_S = 90.0       # a price older than this is not a price


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {m}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def session_key(now: dt.datetime | None = None) -> str:
    """★ The session is the 22:00Z REOPEN, never the calendar day — the same boundary the daily
    loss limit uses. A midnight key would roll over mid-session, the one moment it must not."""
    now = now or dt.datetime.now(dt.UTC)
    d = now.date() if now.hour >= 22 else (now - dt.timedelta(days=1)).date()
    return d.isoformat()


def read_state() -> dict:
    try:
        with open(STATE) as fh:
            st = json.load(fh)
    except Exception:
        return {"armed": False}
    # ⚠ An arming NEVER survives the reopen.
    if st.get("armed") and st.get("session") != session_key():
        log(f"disarmed: armed in session {st.get('session')}, now {session_key()}")
        st = {"armed": False, "note": "expired at the 22:00Z reopen"}
        write_state(st)
    return st


def write_state(st: dict) -> None:
    tmp = STATE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(st, fh, indent=1)
    os.replace(tmp, STATE)          # atomic: a half-written arming is worse than none


def last_price() -> tuple[float | None, float]:
    try:
        c = sqlite3.connect(CAP)
        r = c.execute("select bar_ts, close from bars where symbol='MNQ' and timeframe='5s' "
                      "order by bar_ts desc limit 1").fetchone()
        c.close()
        if not r:
            return None, 1e9
        return float(r[1]), time.time() - float(r[0])
    except Exception:
        return None, 1e9


def fire(reason: str, pnl: float, st: dict) -> None:
    """Write the claim the operator's own button writes. Nothing else."""
    stamp = dt.datetime.now(dt.UTC).isoformat()
    try:
        with open(CLAIM, "w") as fh:
            fh.write(stamp)                  # a BARE stamp means ALL — see claim_requested()
    except Exception as e:
        log(f"⚠ COULD NOT WRITE THE CLAIM: {type(e).__name__}: {e} — POSITION STILL OPEN")
        return
    # ⚠ Disarm FIRST-CLASS: a killer left armed would fire again against the next position.
    write_state({"armed": False, "fired_at": stamp, "fired_pnl": round(pnl, 2),
                 "limit_usd": st.get("limit_usd"), "reason": reason})
    log(f"FIRED: {reason} at open P&L {pnl:+.0f} (limit {st.get('limit_usd')}) — claim written")
    try:
        from gazbot7.notify import notify
        notify(f"🛡 STEP AWAY FIRED — open P&L hit {pnl:+.0f} against your "
               f"${st.get('limit_usd')} limit. Flatten requested; the rider executes it through its "
               f"own ownership check. The guard is now DISARMED.", critical=True)
    except Exception:
        pass


def main() -> int:
    if "--status" in sys.argv:
        print(json.dumps(read_state(), indent=1))
        return 0
    log(f"step_away up · poll {POLL_S}s · READ-ONLY (writes a claim request, never an order)")
    last_note = None
    while True:
        try:
            st = read_state()
            if not st.get("armed"):
                time.sleep(POLL_S)
                continue
            try:
                with open(RIDER) as fh:
                    rs = json.load(fh)
            except Exception:
                time.sleep(POLL_S)
                continue
            qty = float(rs.get("qty") or 0)
            if not qty or rs.get("closed"):
                time.sleep(POLL_S)
                continue
            px, age = last_price()
            # ⚠ A STALE PRICE MUST NOT TRIGGER. Acting on a dead feed is how a guard becomes the
            # hazard — and a shut venue and a broken feed produce the same silence.
            if px is None or age > STALE_PX_S:
                if last_note != "stale":
                    log(f"holding: price is {age:.0f}s old — not acting on a stale feed")
                    last_note = "stale"
                time.sleep(POLL_S)
                continue
            last_note = None
            pnl = open_pnl(px, float(rs.get("entry") or 0), int(rs.get("direction") or 0), qty)
            lim = float(st.get("limit_usd") or 200)
            if pnl <= -abs(lim):
                fire("loss limit", pnl, st)
            elif st.get("take_profit_usd") and pnl >= float(st["take_profit_usd"]):
                fire("take profit", pnl, st)
        except Exception as e:
            log(f"loop error (continuing): {type(e).__name__}: {e}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
