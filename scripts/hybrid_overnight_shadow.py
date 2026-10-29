#!/usr/bin/env python
"""E127 OVERNIGHT SHADOW (operator 2026-10-28: "we will shadow from 2300 to 0300 to see what we miss"). LOG ONLY - presses NOTHING.

Every 5 min from the session open (22:00Z, 23:00 Paris this week) to the live window start (02:00Z), ask Claude the LIVE prompt (Desk Brief,
real desk book, LIVE STATE) with the window stated as opening at 22:00Z; if it says ENTER with the detector's MIL, ask 4 more ballots (5 votes,
need 3). Logged to data/hybrid_overnight_shadow.jsonl, prompt saved to data/hybrid_prompts/<session>_overnight.jsonl. The near-miss report
prices the would-be entries one position at a time and shows whether one would still be open at 02:00Z (blocking the live desk).

This module never writes the BUY file, the claim file or the robot's state: it calls only desk_prompt, S.ask, ask_ballots and det_dir.
Switch `hybrid_overnight_shadow=on` in data/hybrid_robot.env.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
import hybrid_robot as H  # noqa: E402
import leg_robot as L  # noqa: E402

UTC = dt.timezone.utc
LOG = f"{GB}/data/hybrid_overnight_shadow.jsonl"
START_MIN, END_MIN = 22 * 60, 2 * 60      # 22:00Z (session open) .. 02:00Z (live window start), across midnight
ENTRY_FROM = "22:00Z (the session open, the evening before)"


def in_window(t: dt.datetime) -> bool:
    m = t.hour * 60 + t.minute
    return m >= START_MIN or m < END_MIN


def page_bars(now_epoch: int) -> list:
    """minute bars of the last 8 hours from the capture (the new session alone has too few bars early on), never past now"""
    con = sqlite3.connect(f"file:{H.CAPTURE}?mode=ro", uri=True)
    rows = con.execute("SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= ? AND bar_ts <= ? ORDER BY bar_ts",
                       (now_epoch - 8 * 3600, now_epoch)).fetchall()
    con.close()
    agg: dict = {}
    for ts, h, l, c in rows:
        a = agg.setdefault((ts // 60) * 60, [h, l, c])
        a[0] = max(a[0], h); a[1] = min(a[1], l); a[2] = c
    return [(m, float(v[0]), float(v[1]), float(v[2])) for m, v in sorted(agg.items())]


def tick(now: dt.datetime, ask=None, ballots=None) -> dict | None:
    ask = ask or H.S.ask
    ballots = ballots or H.ask_ballots
    if not in_window(now) or not L.read_switch(H.SWITCH, "hybrid_overnight_shadow") or not L.read_switch(H.SWITCH, "hybrid_robot"):
        return None
    now_ts = int(now.timestamp())
    op = now_ts - now_ts % H.STEP_S
    key = H.session_key(now)
    upto = [b for b in page_bars(now_ts) if b[0] + 60 <= op]
    if len(upto) < 60:
        return None
    series = [b for b in L.series_for(L.session_day(now)) if b[0] + 60 <= now_ts - L.SETTLE_S]
    turns = L.confirmed_turns(series) if len(series) >= 200 else []
    rec = {"at": now.isoformat(), "event": "OVERNIGHT_SHADOW", "session": key, "decision_ts": dt.datetime.fromtimestamp(op, UTC).isoformat(),
           "px": upto[-1][3], "version": H.VERSION}
    try:
        prompt, stamp, _ = H.desk_prompt(key, op, upto, upto[-1][3], now_ts, turns, entry_from=ENTRY_FROM)
        rec["brief"] = stamp
        t = time.time(); d = ask(prompt)
        rec.update({"action": d.get("action", "WAIT"), "conf": d.get("confidence"), "reason": (d.get("reason") or "")[:300],
                    "error": d.get("error"), "latency_s": round(time.time() - t, 1), "detector_dir": H.det_dir(turns, op - 60)})
        H.save_prompt(key + "_overnight", op, prompt)
        act = rec["action"]
        if act in ("ENTER_LONG", "ENTER_SHORT") and (1 if act == "ENTER_LONG" else -1) == rec["detector_dir"]:
            left = int(op + H.VOTE_DEADLINE_S - time.time())
            if left >= H.VOTE_MIN_S:
                more = ballots(prompt, 4, timeout=min(H.VOTE_TIMEOUT_S, left))
                agree = sum(1 for b in [d] + more if b.get("action") == act and not b.get("error"))
                need = H.votes_need(5)
                rec["votes"] = {"n": 5, "need": need, "agree": agree, "ballots": [act] + [b.get("action") for b in more],
                                "errors": sum(1 for b in more if b.get("error"))}
                rec["would_press"] = agree >= need
            else:
                rec["votes"] = {"no_time": left}; rec["would_press"] = False
        else:
            rec["would_press"] = False
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    with open(LOG, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec


if __name__ == "__main__":
    r = tick(dt.datetime.now(UTC))
    print(json.dumps(r, default=str) if r else "outside the overnight window / switch off")
