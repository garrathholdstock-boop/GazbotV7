"""THE DESK BRIEF - what Claude reads on every live decision (E119). Rules: docs/CLAUDE.md "THE DESK BRIEF IS GOSPEL".

Four layers, assembled per call:
  1. STRATEGY    config/desk_brief/strategy.md   - the operator's current instruction (versioned, CHANGELOG.md); {TARGET_PTS}/{WIN_USD} are
                 filled from the robot, never typed
  2. MECHANICS   generated here from the robot's constants and today's switches - never hand-written, so it cannot drift from the code
  3. EXPERIENCE  config/desk_brief/experience.md - dated lessons, each citing its study (versioned)
  4. LIVE STATE  per call: the REAL desk book (trades today, open position, realised + open P&L), the detector filter, claims on this
                 leg, minutes to the US open
The caller appends "=== THE TAPE ===" and the page. Pure functions; reads only the files under config/desk_brief.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re

GB = "/home/alphabot/gazbot7"
DIR = os.environ.get("GAZBOT7_DESK_BRIEF_DIR", f"{GB}/config/desk_brief")
UTC = dt.timezone.utc


def _read(name: str) -> str:
    with open(os.path.join(DIR, name), encoding="utf-8") as f:
        return f.read().strip()


def version() -> str:
    m = re.search(r"^VERSION:\s*(\S+)", _read("CHANGELOG.md"), re.M)
    if not m:
        raise ValueError("config/desk_brief/CHANGELOG.md has no 'VERSION:' line")
    return m.group(1)


def _hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}Z"


def mechanics(m: dict) -> str:
    """DESK MECHANICS. Keys: target_pts, lots, win_usd, flat_utc, us_open_utc, window_start_utc, window_end_utc, veto_utc, exit_live,
    lock_usd, mil_cap (None = released for this session)."""
    cap = (f"  - At most {m['mil_cap']} claims (+{m['target_pts']:g} wins) per MIL: after {m['mil_cap']} claims on a MIL the robot trades no "
           "new entry until the detector confirms the next MIL." if m["mil_cap"] else
           "  - Today the operator has released the per-leg claim cap: entries are not limited by claims on a leg.")
    exit_line = ("  - Your EXIT closes the real position." if m["exit_live"] else
                 "  - Your EXIT does NOT close the real position. While the desk really holds that side it sends the operator an urgent text with your\n"
                 "    reason, and he decides. Call EXIT only when the leg you joined has clearly reversed - never because the trade is red. Otherwise HOLD.")
    return "\n".join([
        "DESK MECHANICS (generated from the robot's code and today's switches - this is exactly how the desk works today)",
        "  - MIL = the trend detector's current major intraday leg (its direction and start are in LIVE STATE). The page's 'legs' are finer chart",
        "    swings, not the MIL. The robot trades your ENTER only in the MIL's direction, only if",
        f"    the time is {m['veto_utc']} or later today, and only if the desk is flat. Otherwise your call is logged and nothing is traded.",
        "    The MIL's direction is a FILTER, not a signal: if price is not driving that way on the page, WAIT.",
        f"  - A traded entry is {m['lots']} {m.get('symbol', 'MNQ')} with ONE exit: all {m['lots']} lots close at +{m['target_pts']:g} points from the fill (+${m['win_usd']:,.0f} after fees).",
        (f"    There is NO stop. If +{m['target_pts']:g} is not reached the position is held until it is flattened at {m['flat_utc']}, through the whole US"
         if not m.get("stop_armed") else f"    A venue stop is armed. If +{m['target_pts']:g} is not reached first, the stop or the {m['flat_utc']} flat closes it, through the US"),
        f"    cash session (opens {m['us_open_utc']}).",
        exit_line,
        f"  - You are asked {m['window_start_utc']}-{m['window_end_utc']}. That window is only when you may ENTER; it does not close the real position.",
        f"  - Day lock: once the desk's day (realised + open) has touched +${m['lock_usd']:,.0f}, no new entries are traded that day.",
        cap,
    ])


def state_block(s: dict | None) -> str:
    """LIVE STATE. Keys (optional): now_utc, mins_to_us_open, mil_dir (None/0 = no detector leg), mil_claims, mil_cap,
    trades [{t, side, entry, status, mark_pts, to_target_pts}], day_usd (realised + open), lock_usd."""
    if not s:
        return ""
    L = ["LIVE STATE (this decision - the REAL desk, not a simulation)"]
    if s.get("now_utc"):
        if s["mins_to_us_open"] >= 120:             # D4: a big number read as "long exposure" made Claude wait all morning (10-27)
            L.append(f"  - Time {s['now_utc']}. US cash open in {s['mins_to_us_open']} min: PLENTY of time - the typical winner pays in about 2 hours,"
                     " so time left is not a reason to wait now.")
        else:
            L.append(f"  - Time {s['now_utc']}. US cash open in {s['mins_to_us_open']} min: LITTLE time left - an entry made now that has not paid"
                     " by then rides the US session.")
    if s.get("before_veto"):
        L.append(f"  - Before {s['before_veto']}: no entry can be traded now.")
    if s.get("mil_dir"):
        side = "UP" if s["mil_dir"] > 0 else "DOWN"
        since = f" since {s['mil_since']}" if s.get("mil_since") else ""
        L.append(f"  - MIL: {side}{since}. The robot will only trade an ENTER in that direction.")
        n, cap = s.get("mil_claims", 0), s.get("mil_cap")
        if cap and n >= cap:
            L.append(f"  - Cap reached on this MIL ({n} claims): no entry can be traded until the detector confirms the next MIL.")
        elif cap and n:
            L.append(f"  - {n} claim already taken on this MIL; the robot stops trading it after {cap}.")
    else:
        L.append("  - The detector has no confirmed MIL: no entry can be traded now.")
    tr = s.get("trades") or []
    if tr:
        L.append("  - The desk's real trades today:")
        for x in tr:
            if x["status"] == "OPEN":
                L.append(f"      {x['t']}Z {x['side']} at {x['entry']:.2f}: OPEN, now {x['mark_pts']:+.1f} pt, {x['to_target_pts']:.1f} pt from the target")
            else:
                L.append(f"      {x['t']}Z {x['side']} at {x['entry']:.2f}: {x['status']}")
    else:
        L.append("  - The desk has taken no trade today.")
    if s.get("day_usd") is not None:
        L.append(f"  - Desk day so far (realised + open): {s['day_usd']:+,.0f} USD.")
    return "\n".join(L)


def build(mech: dict, state: dict | None = None) -> tuple[str, dict]:
    """(brief text, stamp). stamp = {version, static_sha}; static_sha covers strategy + mechanics + experience (not the per-call state)."""
    strategy = _read("strategy.md").replace("{TARGET_PTS}", f"{mech['target_pts']:g}").replace("{WIN_USD}", f"{mech['win_usd']:,.0f}")
    sym = mech.get("symbol", "MNQ")
    if sym != "MNQ":                                       # research replays on another instrument (E122): the MNQ-only facts are replaced, never kept
        name = mech.get("instrument_name", sym)
        strategy = strategy.replace("an MNQ futures desk", f"an {sym} ({name}) futures desk")
        a = strategy.index("     On the desk's record"); b = strategy.index("  2. Then money")
        strategy = (strategy[:a] + f"     The desk has no track record on {sym} yet - this is its first look at it. On MNQ the same setup hit the target on\n"
                    f"     most entries and lost big on a few; every entry has the same lopsided payoff (+${mech['win_usd']:,.0f} or, rarely, a large loss),\n"
                    "     so the payoff alone is never a reason to wait.\n" + strategy[b:])
    if re.search(r"\{[A-Z_]+\}", strategy):
        raise ValueError("strategy.md has an unfilled template field")
    exp = _read("experience.md")
    if sym != "MNQ":
        exp = exp.replace("WHAT THE DESK HAS LEARNED", f"WHAT THE DESK HAS LEARNED ON MNQ (points below are MNQ points; {sym} is new)", 1)
    static = "\n\n".join([strategy, mechanics(mech), exp])
    text = static + ("\n\n" + state_block(state) if state else "")
    return text, {"version": version(), "static_sha": hashlib.sha256(static.encode()).hexdigest()[:12]}


def mechanics_from_robot(H, key: str) -> dict:
    """The mechanics for session `key` from the live robot module (scripts/hybrid_robot.py) - target, lots, lock, cap (and today's
    release switch), veto (in UTC for that date), window, flat time - so the brief always says what the code does."""
    from gazbot7 import day_rider as R
    tgt = float(H.TARGETS.split(",")[0]) / H.PV
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
    cut = (H.veto_cutoff if hasattr(H, "veto_cutoff") else H.L.veto_cutoff)(d0 + 12 * 3600)   # v1.06: None when the hybrid has lifted the veto
    return {"target_pts": tgt, "lots": H.QTY, "win_usd": tgt * H.PV * H.QTY - 1.5 * H.QTY,
            "flat_utc": _hm(R.FLAT_UTC_MIN), "us_open_utc": _hm(H.S.WIN_END_MIN),
            "window_start_utc": _hm(H.S.WIN_START_MIN), "window_end_utc": _hm(H.S.WIN_END_MIN),
            "veto_utc": dt.datetime.fromtimestamp(cut, UTC).strftime("%H:%MZ") if cut else _hm(H.S.WIN_START_MIN),
            "exit_live": H.L.read_switch(H.SWITCH, "hybrid_exit_live"), "lock_usd": H.LOCK_USD, "stop_armed": R._venue_stop_armed(),
            "mil_cap": H.MIL_CAP if (key >= H.MILCAP_FROM and H.milcap_enabled(key)) else None}
