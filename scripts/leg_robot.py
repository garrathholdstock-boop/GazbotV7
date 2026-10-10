#!/usr/bin/env python
"""GAZBOT V8 ROBO v1.00 — THE LEG ROBOT (E15, arm H since E29) — frozen detector v1 + the H 4-lot profit-take ladder (12.5/25/37.5/50pt), pressed through the rider's own BUY file.

Declared in reports/recursive_loop/E15_change.txt. It deploys the E6/E7/E14 rules; it changes none of them.

⚠⚠⚠ IT HAS NO ORDER PATH. It writes ONE request file — the one the dashboard's BUY/SELL button writes —
and the rider (src/gazbot7/day_rider.py) does everything else: venue_first_ok, ownership, booking, the
per-lot ladder, the 20:40Z hard flat. Do not add a broker call here.
⚠ Flat-only. While the rider (or the operator's hand) holds, a turn is skipped and logged, like the sim.
⚠ Every press is also snapshotted into operator_reads.jsonl by gazbot7-capture-read-buy.path; the robot's
own log (data/leg_robot.jsonl) is the list to EXCLUDE from any operator-read fitting.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import json
import os
import sys
import time
from zoneinfo import ZoneInfo

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
import mil_detector_fit as DF  # noqa: E402
import mil_labels as ML  # noqa: E402

UTC = dt.timezone.utc
ROBOT = "GazBot V8 Robo"
VERSION = "1.00"   # v1.00 = detector v1 + 05:00 Paris veto + H ladder; each fine-tune bumps it (1.01, 1.02...) and gets an E-declaration
K = 11
WARM_DAYS = 4
ENTRY_END_MIN = 19 * 60 + 40
QTY = 4
ARM = "H"
ARMS = {"H": "25,50,75,100", "F": "100,100,100,100"}
DETECTOR_SHA = "af0ace53e6dc9faa"
START_AFTER = dt.datetime(2026, 10, 11, 22, 0, tzinfo=UTC)
STOP_AFTER = dt.datetime(2026, 10, 30, 21, 0, tzinfo=UTC)
VETO_PARIS_HOUR = 5
FRESH_S = 150
FEED_STALE_S = 180
HEARTBEAT_MAX_S = 120
SETTLE_S = 5

SWITCH = f"{GB}/data/leg_robot.env"
RIDER_SWITCH = f"{GB}/data/day_rider.env"
RIDER_STATE = f"{GB}/data/day_rider_state.json"
BUY_FILE = f"{GB}/data/day_rider_buy.txt"
STATE_FILE = f"{GB}/data/leg_robot_state.json"
LOG_FILE = f"{GB}/data/leg_robot.jsonl"


def detector_sha() -> str:
    return hashlib.sha256((inspect.getsource(DF.atr14) + inspect.getsource(DF.zigzag)).encode()).hexdigest()[:16]


def session_day(now: dt.datetime) -> dt.date:
    d = now.astimezone(UTC).date()
    return d + dt.timedelta(days=1) if now.astimezone(UTC).hour >= 22 else d


def veto_cutoff(ct: int) -> int | None:
    if VETO_PARIS_HOUR is None:
        return None
    sd = session_day(dt.datetime.fromtimestamp(ct, UTC))
    return int(dt.datetime(sd.year, sd.month, sd.day, VETO_PARIS_HOUR, tzinfo=ZoneInfo("Europe/Paris")).timestamp())


def series_for(day: dt.date) -> list:
    allb, seen = [], set()
    for k in range(WARM_DAYS, -1, -1):
        for b in ML.minute_bars((day - dt.timedelta(days=k)).isoformat()):
            if b[0] not in seen:
                seen.add(b[0]); allb.append(b)
    allb.sort()
    return allb


def confirmed_turns(bars: list) -> list:
    return DF.zigzag(bars, DF.atr14(bars), lambda leg, a: K * a)


def read_switch(path: str, key: str) -> bool:
    try:
        for ln in open(path):
            ln = ln.strip()
            if ln.startswith(key + "="):
                return ln.split("=", 1)[1].strip().lower() == "on"
    except Exception:
        pass
    return False


def load_json(path: str) -> dict:
    try:
        return json.load(open(path))
    except Exception:
        return {}


def log(rec: dict) -> None:
    rec = {"robot": ROBOT, "version": VERSION, **rec}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def iso(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, UTC).isoformat()


def rider_gate(now: dt.datetime) -> str | None:
    """None if the rider is demonstrably flat and able to take an entry, else the refusal reason."""
    if not read_switch(RIDER_SWITCH, "day_rider"):
        return "RIDER_OFF"
    st = load_json(RIDER_STATE)
    if not st:
        return "RIDER_STATE_UNREADABLE"
    try:
        hb = (now - dt.datetime.fromisoformat(st["heartbeat"])).total_seconds()
    except Exception:
        return "RIDER_HEARTBEAT_UNREADABLE"
    if hb > HEARTBEAT_MAX_S:
        return f"RIDER_HEARTBEAT_STALE_{int(hb)}s"
    if st.get("entered") or float(st.get("lots_open") or 0) != 0:
        return "HOLDING"
    if st.get("blind_holding"):
        return "RIDER_BLIND"
    if st.get("venue_ok") is not True:
        return "VENUE_NOT_OK"
    if abs(float(st.get("venue_net") or 0)) > 0.01:
        return f"VENUE_NOT_FLAT_{st.get('venue_net')}"
    if os.path.exists(BUY_FILE):
        return "REQUEST_ALREADY_PENDING"
    return None


def write_press(now: dt.datetime, side: str) -> str:
    line = f"{now.isoformat()}|{side}|{QTY}|{ARMS[ARM]}\n"
    with open(BUY_FILE, "w") as f:
        f.write(line)
    return line.strip()


def step(now: dt.datetime, dry: bool = False, sleep=time.sleep) -> dict:
    now_ts = int(now.timestamp())
    out = {"at": now.isoformat(), "status": None}
    st = load_json(STATE_FILE)

    def done(status, **kw):
        out["status"] = status; out.update(kw)
        st.update({"heartbeat": now.isoformat(), "last_status": status, "arm": ARM, "qty": QTY})
        if not dry:
            json.dump(st, open(STATE_FILE, "w"), indent=1)
        return out

    if not read_switch(SWITCH, "leg_robot"):
        return done("SWITCH_OFF")
    if now < START_AFTER:
        return done("WAITING_START")
    if now >= STOP_AFTER:
        return done("PAST_STOP_AFTER")
    if detector_sha() != DETECTOR_SHA:
        log({"at": now.isoformat(), "event": "REFUSED_DETECTOR_CHANGED", "sha": detector_sha()})
        return done("DETECTOR_CHANGED")

    day = session_day(now)
    bars = [b for b in series_for(day) if b[0] + 60 <= now_ts - SETTLE_S]
    if len(bars) < 200:
        return done("NO_BARS")
    age = now_ts - (bars[-1][0] + 60)
    if age > FEED_STALE_S:
        return done("FEED_STALE", feed_age_s=age)

    turns = confirmed_turns(bars)
    last = st.get("last_confirm_ts")
    if last is None:
        st["last_confirm_ts"] = turns[-1][3] if turns else 0
        log({"at": now.isoformat(), "event": "INIT", "last_confirm_ts": st["last_confirm_ts"], "turns_seen": len(turns)})
        return done("INIT")

    d0 = int(dt.datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
    new = [t for t in turns if t[3] > last]
    out["new_turns"] = len(new)
    pressed = None
    for piv_ts, piv_px, nd, cts, cpx in new:
        ct = cts + 60
        rec = {"at": now.isoformat(), "event": "SIGNAL", "confirm_ts": iso(cts), "decision_ts": iso(ct),
               "pivot_ts": iso(piv_ts), "pivot_px": piv_px, "confirm_px": cpx, "new_dir": nd,
               "signal_age_s": now_ts - ct, "arm": ARM, "dry": dry}
        if pressed:
            rec["action"] = "SKIPPED_HOLDING_SAME_TICK"
        elif now_ts - ct > FRESH_S:
            rec["action"] = "STALE_NOT_ENTERED"
        elif ct > d0 + ENTRY_END_MIN * 60:
            rec["action"] = "OUT_OF_ENTRY_WINDOW"
        elif (cut := veto_cutoff(ct)) is not None and ct < cut:
            rec["action"] = "VETOED_BEFORE_05_PARIS"
            rec["veto_cutoff"] = iso(cut)
            rec["would_be"] = "BUY" if nd > 0 else "SELL"
        else:
            why = rider_gate(now)
            if why:
                rec["action"] = "SKIPPED_" + why
            else:
                side = "BUY" if nd > 0 else "SELL"
                rec["action"] = "PRESS_" + side
                if not dry:
                    rec["request"] = write_press(now, side)
                pressed = (side, rec)
        log(rec) if not dry else out.setdefault("signals", []).append(rec)
        st["last_confirm_ts"] = cts
        out["last_signal"] = rec
    if pressed and not dry:
        for _ in range(8):
            sleep(1)
            if not os.path.exists(BUY_FILE):
                break
        after = load_json(RIDER_STATE)
        res = {"at": dt.datetime.now(UTC).isoformat(), "event": "PRESS_RESULT",
               "request_consumed": not os.path.exists(BUY_FILE),
               "rider_entered": after.get("entered"), "rider_entry": after.get("entry"),
               "rider_targets_usd": after.get("manual_targets_usd"), "rider_note": after.get("note")}
        log(res); out["press_result"] = res
    return done("PRESSED" if pressed else "OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry", action="store_true", help="decide and print; write no request, log or state")
    ap.add_argument("--at", help="ISO time (dry runs only)")
    a = ap.parse_args()
    now = dt.datetime.fromisoformat(a.at) if a.at else dt.datetime.now(UTC)
    if a.at and not a.dry:
        print("--at requires --dry"); return 2
    try:
        r = step(now, dry=a.dry)
    except Exception as e:
        log({"at": now.isoformat(), "event": "ERROR", "error": repr(e)})
        print("ERROR", repr(e)); return 1
    print(json.dumps(r, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
