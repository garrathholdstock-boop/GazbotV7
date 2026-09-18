#!/usr/bin/env python3
"""THE GATEWAY WATCH — measure the leak every minute, and restart on the CLIMB, not the wedge.

★★★ THE CONDITION. IB Gateway leaves sockets in CLOSE-WAIT: the client has gone, the gateway never
closes its end. They accumulate until the listener's 50-slot accept queue fills (`LISTEN 51/50`),
and then the signature failure — CONNECTIONS ALREADY OPEN KEEP WORKING PERFECTLY while every NEW one
hangs. The tournament, the feed and depth capture are long-lived and fine; the rider, the watchdog
and the reconciler open a fresh connection per cycle and get nothing. Every health light stays green.

Measured 2026-09-18: 25 episodes, TEN of the last SEVENTEEN DAYS, ~33 hours blind. On 2026-09-17 one
caught the operator holding 4 lots and ate the Claim he pressed at +$262.

★★ WHAT HAS BEEN RULED OUT, so nobody re-chases it:
      market-data subscriptions  NO — L2 flowing 13.3M rows/day, zero 354/10089/10090 anywhere
      a rogue client             NO — clientId 97 is our own depth_capture, 81 our backfill
      connectivity loss to IBKR  NO — all 46 Error 1100s are the known 04:40 nightly reset
      a per-connection leak      NO — CLOSE-WAIT sits at 0 after a restart under normal churn
    WHAT REMAINS: 18 of 25 episodes start 18:00-00:00Z, the window where driftlab (21:02), backfill
    (22:05, every expiry with includeExpired=True) and the overnight research all hammer historical
    data. `Connection reset by peer` is consistent with IBKR PACING VIOLATIONS. STILL A HYPOTHESIS —
    which is exactly why this logs a minute-by-minute series instead of assuming.

⚠⚠⚠ IT WILL NOT RESTART WHILE A POSITION IS OPEN. A restart blinds every consumer for ~15s, and
doing that to a naked 4-lot position to fix a problem that has not yet bitten would be the cure
causing the disease. Flat-only, and it says so when it declines.
⚠ COOLDOWN, because a restart that does not clear the condition must not become a restart LOOP —
the thing that takes the desk down is never the first restart, it is the fourth.

  PYTHONPATH=src .venv/bin/python scripts/gateway_watch.py [--once] [--no-act]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/alphabot/gazbot7/src")

GB = "/home/alphabot/gazbot7"
SERIES = f"{GB}/data/gateway_watch.jsonl"      # the measurement — one line a minute, forever
LOG = f"{GB}/data/gateway_watch.log"
STATE = f"{GB}/data/gateway_watch_state.json"
RIDER = f"{GB}/data/day_rider_state.json"
PORT = 4002
BACKLOG = 50                                    # the listener's queue depth — the thing that fills
TRIP = int(os.environ.get("GW_TRIP", "30"))     # 30 of 50: acting on the CLIMB, not the wedge
COOLDOWN_S = float(os.environ.get("GW_COOLDOWN_S", "3600"))
POLL_S = 60.0


def log(m: str) -> None:
    line = f"{dt.datetime.now(dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} {m}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def sample() -> dict:
    """CLOSE-WAIT count and the accept queue. ⚠ Both, because they are different things: CLOSE-WAIT
    is the leak accumulating, the accept queue filling is the moment it becomes an outage."""
    out = {"ts": dt.datetime.now(dt.UTC).isoformat(), "close_wait": None,
           "acceptq": None, "backlog": None, "established": None}
    try:
        tn = subprocess.run(["ss", "-tn"], capture_output=True, text=True, timeout=15).stdout
        out["close_wait"] = sum(1 for l in tn.splitlines()
                                if "CLOSE-WAIT" in l and f":{PORT}" in l)
        out["established"] = sum(1 for l in tn.splitlines()
                                 if "ESTAB" in l and f":{PORT}" in l)
        ltn = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=15).stdout
        for l in ltn.splitlines():
            if f":{PORT}" in l:
                p = l.split()
                out["acceptq"], out["backlog"] = int(p[1]), int(p[2])
                break
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    # ★ what was RUNNING at the time — the whole point of the series is to find the trigger
    try:
        ps = subprocess.run(["ps", "-eo", "cmd"], capture_output=True, text=True, timeout=15).stdout
        out["jobs"] = sorted({j for j in ("backfill_history", "driftlab", "overnight",
                                          "run_census", "nightly", "depth_capture")
                              if j in ps})
    except Exception:
        pass
    return out


def desk_is_flat() -> tuple[bool, str]:
    """⚠⚠ A restart blinds every consumer for ~15s. Doing that to an open position to fix a problem
    that has not yet bitten would be the cure causing the disease."""
    try:
        with open(RIDER) as fh:
            st = json.load(fh)
        q = float(st.get("qty") or 0)
        if q and not st.get("closed"):
            return False, f"day_rider holds {q:g} lot(s)"
    except Exception as e:
        # ⚠ CANNOT READ = CANNOT ACT. Not knowing is not the same as flat.
        return False, f"cannot read the rider state ({type(e).__name__}) — refusing to act blind"
    return True, "flat"


def read_state() -> dict:
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def restart(reason: str, s: dict) -> None:
    log(f"RESTARTING THE GATEWAY: {reason}")
    r = subprocess.run(["docker", "restart", "alphabot-gateway"],
                       capture_output=True, text=True, timeout=180)
    ok = r.returncode == 0
    with open(STATE, "w") as fh:
        json.dump({"last_restart": dt.datetime.now(dt.UTC).isoformat(),
                   "reason": reason, "ok": ok, "sample": s}, fh)
    log(f"restart {'OK' if ok else 'FAILED rc=' + str(r.returncode)}")
    try:
        from gazbot7.notify import notify
        notify(f"🔁 GATEWAY RESTARTED automatically — {reason}. The desk was FLAT. "
               f"This is the CLOSE-WAIT leak that has wedged the gateway on 10 of the last 17 days; "
               f"acting on the climb turns a 2-6 hour blind window into ~15 seconds. "
               f"{'Restart succeeded.' if ok else '⚠ RESTART FAILED — CHECK THE GATEWAY BY HAND.'}",
               critical=not ok)
    except Exception:
        pass


def main() -> int:
    once = "--once" in sys.argv
    act = "--no-act" not in sys.argv
    if not once:
        log(f"gateway_watch up · trip {TRIP}/{BACKLOG} · cooldown {COOLDOWN_S/60:.0f}m · "
            f"act={act} · FLAT-ONLY")
    while True:
        s = sample()
        try:
            with open(SERIES, "a") as fh:
                fh.write(json.dumps(s) + "\n")
        except Exception:
            pass
        cw, aq = s.get("close_wait"), s.get("acceptq")
        if cw is not None and cw >= TRIP:
            st = read_state()
            last = st.get("last_restart")
            age = 1e9
            if last:
                try:
                    age = (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(last)).total_seconds()
                except Exception:
                    pass
            flat, why = desk_is_flat()
            if not act:
                log(f"would restart (CLOSE-WAIT {cw}/{BACKLOG}) — --no-act")
            elif age < COOLDOWN_S:
                log(f"CLOSE-WAIT {cw} but last restart was {age/60:.0f}m ago — cooling down")
            elif not flat:
                # ⚠ SAY SO. A guard that declines in silence is a guard nobody knows they lack.
                log(f"⚠ CLOSE-WAIT {cw}/{BACKLOG} and climbing, but NOT RESTARTING: {why}")
            else:
                restart(f"CLOSE-WAIT {cw}/{BACKLOG}, accept queue {aq}", s)
        elif cw:
            log(f"close_wait={cw} acceptq={aq}/{s.get('backlog')} estab={s.get('established')}"
                + (f" jobs={','.join(s['jobs'])}" if s.get("jobs") else ""))
        if once:
            print(json.dumps(s, indent=1))
            return 0
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
