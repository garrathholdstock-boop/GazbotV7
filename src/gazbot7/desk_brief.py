"""THE DESK BRIEF - what Claude reads on every live decision (E119). Rules: docs/CLAUDE.md "THE DESK BRIEF IS GOSPEL".

Four layers, assembled per call:
  1. STRATEGY    config/desk_brief/strategy.md   - the operator's current instruction (versioned, CHANGELOG.md)
  2. MECHANICS   generated here from the robot's constants - never hand-written, so it cannot drift from the code
  3. EXPERIENCE  config/desk_brief/experience.md - dated lessons, each citing its study (versioned)
  4. LIVE STATE  computed per call by the caller (claims on this MIL, day P&L / lock, minutes to the US open)
The caller appends "=== THE TAPE ===" and the page. Pure functions; reads only the three files under config/desk_brief.
"""
from __future__ import annotations

import hashlib
import os
import re

GB = "/home/alphabot/gazbot7"
DIR = os.environ.get("GAZBOT7_DESK_BRIEF_DIR", f"{GB}/config/desk_brief")


def _read(name: str) -> str:
    with open(os.path.join(DIR, name), encoding="utf-8") as f:
        return f.read().strip()


def version() -> str:
    m = re.search(r"^VERSION:\s*(\S+)", _read("CHANGELOG.md"), re.M)
    if not m:
        raise ValueError("config/desk_brief/CHANGELOG.md has no 'VERSION:' line")
    return m.group(1)


def mechanics(m: dict) -> str:
    """DESK MECHANICS from the robot's constants. Required keys: target_pts, lots, usd_per_pt, fee_usd, win_usd, flat_utc, us_open_utc,
    window_start_utc, window_end_utc, veto, detector, exit_live, lock_usd, mil_cap."""
    lines = [
        "DESK MECHANICS (generated from the robot's code - this is exactly how the desk works today)",
        f"  - When you call ENTER, the robot buys/sells {m['lots']} MNQ only if the trend detector's current leg ({m['detector']}) points the same way,",
        f"    {m['veto']}, and the desk is flat. Otherwise your call is logged and nothing is traded.",
        f"  - The position then has ONE exit: all {m['lots']} lots close at +{m['target_pts']:g} points from the fill (= +${m['win_usd']:,.0f} after fees).",
        f"    There is NO stop. If +{m['target_pts']:g} is not reached, the position is held until it is flattened at {m['flat_utc']}, through the whole",
        f"    US cash session (opens {m['us_open_utc']}), whatever the loss.",
        ("  - Your EXIT and HOLD answers are recorded in your own book but DO NOT close the real position." if not m["exit_live"] else
         "  - Your EXIT closes the real position."),
        f"  - You are asked between {m['window_start_utc']} and {m['window_end_utc']}. The window ending does NOT close the real position; only +{m['target_pts']:g} or {m['flat_utc']} does.",
        f"  - After the desk's day has touched +${m['lock_usd']:,.0f}, no new entries are made that day.",
        f"  - At most {m['mil_cap']} claims (+{m['target_pts']:g} wins) per leg: after the {m['mil_cap']}{'nd' if m['mil_cap'] == 2 else 'th'} claim on a leg the robot makes no new entry until the detector confirms the next leg.",
        f"  - So every entry is a bet that the move reaches +{m['target_pts']:g} BEFORE it turns. A win pays +${m['win_usd']:,.0f}; an entry that stalls and turns can cost",
        "    $1,500-$4,500 by 20:40Z. One bad entry erases five to fifteen good ones.",
    ]
    return "\n".join(lines)


def state_block(s: dict | None) -> str:
    """LIVE STATE for this call. Keys (all optional): now_utc, mins_to_us_open, mil_dir, mil_claims, mil_cap, day_usd, lock_usd, locked, holding."""
    if not s:
        return ""
    L = ["LIVE STATE (this decision)"]
    if s.get("now_utc"):
        L.append(f"  - Time {s['now_utc']}. US cash open in {s['mins_to_us_open']} min: an entry made now that has not paid by then rides the US session.")
    if s.get("mil_dir") is not None:
        side = "UP" if s["mil_dir"] > 0 else "DOWN"
        L.append(f"  - Current detector leg: {side}. Claims already taken on it today: {s.get('mil_claims', 0)} of {s.get('mil_cap')}.")
    if s.get("day_usd") is not None:
        L.append(f"  - Desk day so far: {s['day_usd']:+,.0f} USD (no new entries once it touches +{s.get('lock_usd', 0):,.0f}).")
    if s.get("holding"):
        L.append("  - The desk is HOLDING a position now: a new ENTER cannot be traded until it closes.")
    return "\n".join(L)


def build(mech: dict, state: dict | None = None) -> tuple[str, dict]:
    """(brief text, stamp). stamp = {version, static_sha}; static_sha covers strategy + mechanics + experience (not the per-call state)."""
    static = "\n\n".join([_read("strategy.md"), mechanics(mech), _read("experience.md")])
    text = static + ("\n\n" + state_block(state) if state else "")
    return text, {"version": version(), "static_sha": hashlib.sha256(static.encode()).hexdigest()[:12]}


def mechanics_from_robot(H) -> dict:
    """The mechanics dict from the live robot module (scripts/hybrid_robot.py), so the brief always says what the code does."""
    tgt = float(H.TARGETS.split(",")[0]) / H.PV
    return {"target_pts": tgt, "lots": H.QTY, "usd_per_pt": H.PV, "fee_usd": 1.5 * H.QTY,
            "win_usd": tgt * H.PV * H.QTY - 1.5 * H.QTY, "flat_utc": "20:40Z", "us_open_utc": "13:30Z",
            "window_start_utc": f"{H.S.WIN_START_MIN // 60:02d}:{H.S.WIN_START_MIN % 60:02d}Z",
            "window_end_utc": f"{H.S.WIN_END_MIN // 60:02d}:{H.S.WIN_END_MIN % 60:02d}Z",
            "veto": f"the time is after {H.L.VETO_PARIS_HOUR:02d}:00 Paris",
            "detector": f"zigzag K={H.L.K} x ATR14, 1-min closes", "exit_live": H.L.read_switch(H.SWITCH, "hybrid_exit_live"), "lock_usd": H.LOCK_USD, "mil_cap": H.MIL_CAP}
