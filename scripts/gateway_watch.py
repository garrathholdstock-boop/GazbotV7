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
# ★★2026-09-24 60s WAS TOO SLOW TO SEE IT COMING. On the 18:05 wedge the accept queue went
# 34 -> 38 -> 42 in TWO SAMPLES, and the operator found out by pressing FLATTEN and watching
# nothing happen. A climb of ~4/minute deserves a look more often than once a minute.
POLL_S = float(os.environ.get("GW_POLL_S", "15"))

# ── THE BLIND-AND-HOLDING PATH (2026-09-24) ──────────────────────────────────────────────────
# ★★★ Operator, after the 18:05 wedge: "you need to build something that makes that never happen
# again. we need to be constantly monitoring it. alarming and then auto restarting. us not knowing
# is unacceptable."
# ⚠⚠⚠ THE STANDING RULE — never restart while a position is open — EXISTS BECAUSE A RESTART BLINDS
# EVERY CONSUMER FOR ~15s. That cost is real when the desk can still trade. IT IS ZERO WHEN THE
# DESK IS ALREADY BLIND. If the rider cannot reach the venue and is holding, there is NO order path
# to protect: his FLATTEN does nothing, the ladder does nothing, the 20:40 hard flat would do
# nothing. A restart is then the only action that can improve the situation and cannot worsen it.
# ⚠ So this is a NARROW exception, not a relaxation: blind AND holding AND sustained. A healthy
# desk holding a position is still never restarted, and a stale rider state still counts as
# "cannot tell", which counts as "do not act".
BLIND_S = float(os.environ.get("GW_BLIND_S", "45"))       # sustained blindness before acting
REQ_S = float(os.environ.get("GW_REQ_S", "45"))           # an unread press this old is a dead path
BLIND_COOLDOWN_S = float(os.environ.get("GW_BLIND_COOLDOWN_S", "600"))
# ⚠ A CAP, NOT JUST A COOLDOWN. If restarting does not fix it, the fault is not the gateway and
# looping on it makes things worse — page and STOP, the backfill-health pattern.
BLIND_MAX = int(os.environ.get("GW_BLIND_MAX", "3"))
RIDER_STALE_S = 180.0
CLAIM = f"{GB}/data/day_rider_claim.txt"
BUY = f"{GB}/data/day_rider_buy.txt"


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


def blind_and_holding() -> tuple[bool, str]:
    """TRUE only when we can SEE that the rider holds AND cannot reach the venue.

    ⚠ A STALE STATE IS "CANNOT TELL", WHICH IS "DO NOT ACT". Never inferred from silence.
    ⚠ We act on venue_ok == False, never on a missing or True value. `venue_ok` is known to go
      STALE-TRUE on the rider's early-return path (it read true for 2h once while the heartbeat
      advanced), and that failure mode points the safe way here: a stale True means we decline.
    """
    try:
        age = time.time() - os.path.getmtime(RIDER)
        if age > RIDER_STALE_S:
            return False, f"rider state is {age:.0f}s old — cannot tell, not acting"
        with open(RIDER) as fh:
            st = json.load(fh)
    except Exception as e:
        return False, f"cannot read the rider state ({type(e).__name__}) — not acting"
    q = float(st.get("qty") or 0)
    if not q or st.get("closed"):
        return False, "flat"
    if st.get("venue_ok") is False:
        return True, f"holds {q:g} lot(s) and venue_ok=false"
    return False, f"holds {q:g} lot(s) but the venue is reachable"


def unread_request() -> tuple[bool, str]:
    """An operator press the rider has not consumed. ⚠ THIS IS THE THING HE ACTUALLY CARES ABOUT —
    not "is the gateway healthy" but "did my button do anything". The rider DELETES a request when
    it acts on it, so `exists and old` IS unread. No heartbeat, nothing that can go stale the
    wrong way. ⚠ READ-ONLY: it never consumes, clears or rewrites a request."""
    for path, what in ((CLAIM, "CLAIM"), (BUY, "BUY")):
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            continue
        if age >= REQ_S:
            return True, f"his {what} has sat unread for {age:.0f}s"
    return False, ""


def _notify(msg: str, *, critical: bool = False) -> None:
    """⚠ The alarm must never be able to abort the watchdog that is trying to alarm."""
    try:
        from gazbot7.notify import notify as _n
        _n(msg, critical=critical)
    except Exception as e:
        log(f"notify failed: {type(e).__name__}: {e}")


def dedupe_ok(key: str, sig: str, cooldown_s: float) -> bool:
    try:
        from gazbot7.notify import dedupe_ok as _d
        return _d(key, sig, cooldown_s=cooldown_s)
    except Exception:
        return True                      # ⚠ FAIL OPEN. A broken dedupe must never eat an alarm.


def _age(iso) -> float:
    """Seconds since an ISO stamp. ⚠ Absent or unparseable => INFINITY, i.e. "no recent restart",
    which lets the guard ACT. A cooldown that fails closed would silently disarm the watchdog."""
    if not iso:
        return float("inf")
    try:
        return (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(iso)).total_seconds()
    except Exception:
        return float("inf")


def write_state(d: dict) -> None:
    """MERGE, never replace. ⚠⚠ restart() used to json.dump a fresh dict over this file, which
    would have wiped `blind_restarts` on every restart and made the cap unreachable — the guard
    would have looped forever while appearing to count. Found while wiring the cap, not after."""
    try:
        cur = read_state()
        cur.update(d)
        tmp = STATE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(cur, fh, indent=1)
        os.replace(tmp, STATE)
    except Exception as e:
        log(f"state write failed: {type(e).__name__}: {e}")


def read_state() -> dict:
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def restart(reason: str, s: dict, blind: bool = False) -> None:
    log(f"RESTARTING THE GATEWAY: {reason}")
    r = subprocess.run(["docker", "restart", "alphabot-gateway"],
                       capture_output=True, text=True, timeout=180)
    ok = r.returncode == 0
    write_state({"last_restart": dt.datetime.now(dt.UTC).isoformat(),
                 "reason": reason, "ok": ok, "sample": s})
    log(f"restart {'OK' if ok else 'FAILED rc=' + str(r.returncode)}")
    try:
        from gazbot7.notify import notify
        if blind:
            notify(f"🔁 GATEWAY RESTARTED WHILE YOU WERE HOLDING — {reason}.\n"
                   f"⚠ This is the NARROW exception: the desk was ALREADY BLIND, so there was no "
                   f"order path to protect — your FLATTEN, the ladder and the 20:40 flat were all "
                   f"doing nothing. A restart could only improve it.\n"
                   f"CHECK YOUR POSITION. The rider re-reads an unconsumed request, so a press "
                   f"made in the last 15 min should still execute.", critical=True)
            return
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
        # ⚠ READ ONCE, AT THE TOP. `st` used to be loaded only inside the CLOSE-WAIT branch, and
        # the blind path below runs OUTSIDE it — deliberately, because the 18:05 wedge had the
        # rider blind and his FLATTEN unread while CLOSE-WAIT was still climbing through the trip.
        st = read_state()
        if cw is not None and cw >= TRIP:
            age = _age(st.get("last_restart"))
            flat, why = desk_is_flat()
            if not act:
                log(f"would restart (CLOSE-WAIT {cw}/{BACKLOG}) — --no-act")
            elif age < COOLDOWN_S:
                log(f"CLOSE-WAIT {cw} but last restart was {age/60:.0f}m ago — cooling down")
            elif not flat:
                # ⚠⚠⚠2026-09-24 IT USED TO SAY SO ONLY TO A LOG FILE NOBODY READS, and that is
                # exactly how the 18:05 wedge reached him: he found out by pressing FLATTEN and
                # watching nothing happen, while this line had been written three times. Operator:
                # "us not knowing is unacceptable." A guard that declines in silence is a guard
                # nobody knows they lack — so the DECLINE now pages.
                log(f"⚠ CLOSE-WAIT {cw}/{BACKLOG} and climbing, but NOT RESTARTING: {why}")
                _sig = f"gw_declined {cw >= TRIP}"
                if dedupe_ok("gateway_watch.declined", _sig, cooldown_s=900.0):
                    _notify(f"⚠⚠ GATEWAY IS FILLING UP AND I CANNOT FIX IT — CLOSE-WAIT {cw}/"
                           f"{BACKLOG}, accept queue {aq}/{BACKLOG}.\n"
                           f"Not restarting because: {why}.\n"
                           f"⚠ Open connections keep working while NEW ones hang, so every light "
                           f"stays green. If a button stops responding, this is why. "
                           f"Flatten while you still can, or say the word and I restart it.",
                           critical=True)
            else:
                restart(f"CLOSE-WAIT {cw}/{BACKLOG}, accept queue {aq}", s)
        elif cw:
            log(f"close_wait={cw} acceptq={aq}/{s.get('backlog')} estab={s.get('established')}"
                + (f" jobs={','.join(s['jobs'])}" if s.get("jobs") else ""))

        # ── THE BLIND-AND-HOLDING PATH ───────────────────────────────────────────────────────
        # ⚠⚠⚠ Deliberately OUTSIDE the CLOSE-WAIT branch. The 18:05 wedge had the rider blind and
        # his FLATTEN unread while CLOSE-WAIT was still climbing THROUGH the trip point — waiting
        # for a socket threshold to be crossed would have kept the desk dark for another minute.
        # The thing that matters is not "is the gateway sick", it is "can he get out".
        blind, bwhy = blind_and_holding()
        unread, uwhy = unread_request()
        if blind or unread:
            if st.get("blind_since") is None:
                st["blind_since"] = dt.datetime.now(dt.UTC).isoformat()
                write_state(st)
                log(f"BLIND/UNREAD begins: {bwhy or uwhy}")
            held = (dt.datetime.now(dt.UTC)
                    - dt.datetime.fromisoformat(st["blind_since"])).total_seconds()
            nres = int(st.get("blind_restarts") or 0)
            bage = _age(st.get("last_blind_restart"))
            trigger = (blind and held >= BLIND_S) or unread
            if not trigger:
                log(f"blind {held:.0f}s (acting at {BLIND_S:.0f}s) — {bwhy or uwhy}")
            elif not act:
                log(f"would restart (BLIND) — --no-act")
            elif nres >= BLIND_MAX:
                # ⚠ IF RESTARTING DID NOT FIX IT, THE FAULT IS NOT THE GATEWAY. Page and STOP —
                # the thing that takes a desk down is never the first restart, it is the fourth.
                if dedupe_ok("gateway_watch.blind_capped", "capped", cooldown_s=1800.0):
                    _notify(f"🆘 DESK BLIND AND HOLDING, AND I HAVE STOPPED RESTARTING — "
                           f"{nres} attempts already and it came back. {bwhy or uwhy}. "
                           f"This is not the gateway. MANUAL INTERVENTION NEEDED.", critical=True)
            elif bage < BLIND_COOLDOWN_S:
                log(f"blind but last blind-restart was {bage/60:.0f}m ago — cooling down")
            else:
                _notify(f"⚠⚠⚠ DESK IS BLIND AND HOLDING — {bwhy or uwhy}. Your presses are not "
                       f"reaching the broker. RESTARTING THE GATEWAY NOW.", critical=True)
                st["blind_restarts"] = nres + 1
                st["last_blind_restart"] = dt.datetime.now(dt.UTC).isoformat()
                write_state(st)
                restart(f"{bwhy or uwhy} (blind for {held:.0f}s)", s, blind=True)
        elif st.get("blind_since"):
            log("blind/unread cleared")
            st["blind_since"] = None
            write_state(st)
        if once:
            print(json.dumps(s, indent=1))
            return 0
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main())
