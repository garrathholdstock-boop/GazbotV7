#!/usr/bin/env python
"""LEG TRACKER (read-only): where GBV8 Robo's frozen detector is RIGHT NOW between confirmed turns.

Shows the dashboard strip: current leg direction/age/size, the running extreme, the retrace so far against the
11xATR confirm trigger, the price at which the robot would act, and why it would or would not act.
It reuses leg_robot's own series/ATR/constants and replays DF.zigzag's loop only to expose its FINAL state; the replay's
pivots are checked against DF.zigzag every run and a mismatch publishes status TRACKER_MISMATCH instead of a number.
READ-ONLY: writes data/leg_tracker.json and the static web file. No order path, no switch, no request file, does not touch
the robot's state or log.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
import leg_robot as R  # noqa: E402
import hybrid_robot as H  # noqa: E402  v1.02 is the robot that is live; the strip reports ITS gate, not the (off) leg robot's

DF = R.DF
UTC = dt.timezone.utc
OUT = f"{GB}/data/leg_tracker.json"
WEB = f"{GB}/src/gazbot7/web_static/leg_tracker_web.json"


def replay(bars, atr):
    """DF.zigzag's loop, returning pivots AND the live state (dirn, ext, ext_i, last_px)."""
    cl = [b[3] for b in bars]
    dirn = 1 if cl[30] > cl[0] else -1
    ext, ei, last_px = cl[0], 0, cl[0]
    piv = []
    for i in range(1, len(bars)):
        c = cl[i]
        if dirn * (c - ext) > 0:
            ext, ei = c, i
        elif dirn * (ext - c) >= R.K * atr[i]:
            piv.append((bars[ei][0], ext, -dirn, bars[i][0], c))
            last_px, dirn, ext, ei = ext, -dirn, c, i
    return piv, dict(dirn=dirn, ext=ext, ei=ei, last_px=last_px)


def _atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


LOOK_OFFSET_S = 20   # the hybrid timer fires at :20 past every 5-minute mark (OnCalendar ...:00/5:20)
LOOK_STEP_S = H.STEP_S


def next_look(now: dt.datetime) -> tuple[int | None, str]:
    """Epoch of the hybrid's next scheduled look, or (None, why). Mirrors hybrid_robot.step's own early exits."""
    if not R.read_switch(H.SWITCH, "hybrid_robot"):
        return None, "OFF"
    if R.read_switch(H.LEG_SWITCH, "leg_robot"):
        return None, "OFF"
    t = (int(now.timestamp()) // LOOK_STEP_S) * LOOK_STEP_S + LOOK_OFFSET_S
    if t < now.timestamp():
        t += LOOK_STEP_S
    for _ in range(7 * 24 * 12):
        at = dt.datetime.fromtimestamp(t, UTC)
        if at >= H.STOP_AFTER:
            return None, "DONE"
        if at >= H.START_AFTER and at.weekday() < 5:
            key = H.session_key(at)
            d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
            win_end = H.EXT_END_MIN if key == H.EXT_KEY else H.S.WIN_END_MIN
            if H.S.WIN_START_MIN <= (t - d0) // 60 < win_end:
                return t, "RUN"
        t += LOOK_STEP_S
    return None, "CLOSED"


def last_entry_call(limit_bytes: int = 600_000) -> dict | None:
    """The most recent real (non-dry) Claude ENTER_* call that reached the gate chain, and whether it was pressed."""
    try:
        with open(H.LOG_FILE, "rb") as f:
            start = max(0, os.path.getsize(H.LOG_FILE) - limit_bytes)
            f.seek(start)
            lines = f.read().decode(errors="ignore").splitlines()
        for ln in reversed(lines[1:] if start else lines):
            if not ln.startswith("{"):
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("event") == "DECISION" and not r.get("dry") and str(r.get("action", "")).startswith("ENTER_") and r.get("entry_action"):
                ea = str(r["entry_action"])
                return {"decision_ts": r.get("decision_ts"), "at": r.get("at"), "action": r["action"],
                        "side": "BUY" if r["action"] == "ENTER_LONG" else "SELL",
                        "entry_action": ea, "taken": ea.startswith("PRESS_"), "reason": (r.get("reason") or "")[:160]}
    except Exception:
        pass
    return None


def snapshot(now: dt.datetime) -> dict:
    now_ts = int(now.timestamp())
    out = {"updated": now.isoformat(), "robot": H.ROBOT, "version": H.VERSION, "mode": "hybrid", "k_atr": R.K, "status": None}
    out["next_look_ts"], out["look_state"] = next_look(now)   # set before any early return: the clock does not need bars
    out["last_entry_call"] = last_entry_call()
    day = R.session_day(now)
    bars = [b for b in R.series_for(day) if b[0] + 60 <= now_ts - R.SETTLE_S]
    if len(bars) < 200:
        out["status"] = "NO_BARS"; return out
    feed_age = now_ts - (bars[-1][0] + 60)
    out["feed_age_s"] = feed_age
    atr = DF.atr14(bars)
    piv, s = replay(bars, atr)
    if [tuple(p) for p in piv] != [tuple(p) for p in DF.zigzag(bars, atr, lambda leg, a: R.K * a)]:
        out["status"] = "TRACKER_MISMATCH"; return out
    d = s["dirn"]; px = bars[-1][3]; a = atr[-1]; trig = R.K * a
    ext_ts = bars[s["ei"]][0]
    retrace = d * (s["ext"] - px)
    leg_start = piv[-1] if piv else None
    out.update({
        "dir": d, "dir_name": "UP" if d > 0 else "DOWN", "next_side": "SELL" if d > 0 else "BUY",
        "price": px, "atr14": round(a, 2), "trigger_pts": round(trig, 1),
        "extreme_px": s["ext"], "extreme_ts": ext_ts, "extreme_age_min": round((bars[-1][0] + 60 - ext_ts) / 60),
        "retrace_pts": round(retrace, 1), "retrace_pct": round(100 * retrace / trig, 1),
        "trigger_px": round(s["ext"] - d * trig, 2),
        "leg_pivot_px": s["last_px"], "leg_size_pts": round(d * (s["ext"] - s["last_px"]), 1),
        "leg_confirmed_ts": leg_start[3] if leg_start else None,
        "leg_age_min": round((bars[-1][0] + 60 - leg_start[3]) / 60) if leg_start else None,
        "recent_turns": [{"confirm_ts": p[3], "pivot_ts": p[0], "pivot_px": p[1], "new_dir": p[2]} for p in piv[-6:]],
    })
    # recent completed legs: pivot-to-pivot size and duration
    legs = []
    for p0, p1 in zip(piv[-7:-1], piv[-6:]):
        legs.append({"dir": p0[2], "start_ts": p0[0], "end_ts": p1[0], "pts": round(abs(p1[1] - p0[1])), "min": round((p1[0] - p0[0]) / 60)})
    out["recent_legs"] = legs
    # why the robot would / would not act on a confirm now
    cutoff = H.veto_cutoff(now_ts)                 # v1.06: the hybrid's veto (None when lifted)
    rider = R.load_json(R.RIDER_STATE)
    rg = R.rider_gate(now)   # the robot's OWN gate, so the strip says what it will really do
    d0 = int(dt.datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
    key = H.session_key(now)
    mod = (now_ts - d0) // 60
    win_end = H.EXT_END_MIN if key == H.EXT_KEY else H.S.WIN_END_MIN
    if not R.read_switch(H.SWITCH, "hybrid_robot"):
        gate = "SWITCH_OFF"
    elif now < H.START_AFTER or now >= H.STOP_AFTER:
        gate = "OUTSIDE_RUN_WINDOW"
    elif feed_age > R.FEED_STALE_S:
        gate = "FEED_STALE"
    elif rg == "HOLDING":
        gate = "IN_TRADE"
    elif rg is not None:
        gate = "RIDER_" + rg
    elif cutoff is not None and now_ts < cutoff - 60:
        gate = "VETO_ACTIVE"
    elif not (H.S.WIN_START_MIN <= mod < win_end):
        gate = "ENTRY_WINDOW_CLOSED"
    else:
        gate = "ARMED_WAITING"
    out["allowed_side"] = "BUY" if d > 0 else "SELL"      # the hybrid presses only entries WITH the detector's leg
    out["window_end_hhmm_utc"] = f"{win_end // 60:02d}:{win_end % 60:02d}"
    try:
        with open(H.LOG_FILE, "rb") as f:
            start = max(0, os.path.getsize(H.LOG_FILE) - 20000)
            f.seek(start)
            lines = f.read().decode(errors="ignore").splitlines()
            recs = [json.loads(x) for x in (lines[1:] if start else lines) if x.startswith("{")]
        last = [r for r in recs if r.get("event") == "DECISION"][-1]
        out["last_call"] = {k: last.get(k) for k in ("decision_ts", "action", "entry_action", "reason")}
        out["last_call"]["reason"] = (out["last_call"]["reason"] or "")[:160]
    except Exception:
        out["last_call"] = None
    out["gate"] = gate
    out["veto_cutoff_ts"] = cutoff
    out["veto_cutoff_hhmm_paris"] = "05:00" if cutoff is not None else None
    out["status"] = "OK"
    return out


def rider_pos():
    """Open rider position's entry time/price, so the chart can mark the moment of the buy. None when flat."""
    try:
        with open(f"{GB}/data/day_rider_state.json") as f:
            d = json.load(f)
        if d.get("entered") and not d.get("closed") and d.get("entered_at") and d.get("entry"):
            return {"entered_at": d["entered_at"], "entry": float(d["entry"]),
                    "direction": d.get("direction"), "qty": d.get("qty")}
    except Exception:
        pass
    return None


def main() -> int:
    now = dt.datetime.now(UTC)
    try:
        snap = snapshot(now)
        snap["rider_pos"] = rider_pos()
    except Exception as e:  # a tracker fault must say so, never look like a quiet market
        snap = {"updated": now.isoformat(), "status": "ERROR", "error": repr(e)}
    _atomic(OUT, snap)
    _atomic(WEB, snap)
    print(json.dumps({k: snap.get(k) for k in ("status", "gate", "dir_name", "retrace_pct", "trigger_px")}))
    return 0 if snap["status"] in ("OK", "NO_BARS") else 1


if __name__ == "__main__":
    sys.exit(main())
