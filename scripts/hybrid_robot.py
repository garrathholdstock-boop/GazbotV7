#!/usr/bin/env python
"""GAZBOT V8 ROBO v1.03 — THE HYBRID (E89): Claude S1b calls the entries, the frozen detector gives the leg, the rider does the rest.
v1.03 (2026-10-26, operator, E115): + MIL CAP — at most MIL_CAP (2) claims per MIL; then no new press until the detector confirms the next MIL.

Declared in reports/recursive_loop/E89_change.txt. It deploys E81-E88; it changes none of their rules.

Every 5 min inside 02:00Z-13:30Z it asks Claude (BRIEF_V2, empty rule set, self-aware page) what it would do against a SIMULATED
book of its own. A simulated ENTER becomes a REAL press only if (1) its side equals the frozen detector's direction at decision
time - 60s, (2) the decision is at/after 05:00 Europe/Paris, (3) the rider is demonstrably flat. The press is the rider's own BUY
file with all four lots out at +37.5pt; the rider does venue-first, booking, the ladder and the 20:40Z hard flat.

⚠⚠⚠ IT HAS NO BROKER CALL. It writes two request files and nothing else of the desk's: the one the dashboard's BUY/SELL button writes,
and (since 2026-10-19, operator: "Auto flatten") the one his Claim button writes when Claude calls EXIT while the rider really holds
that side - the rider executes it through its own ownership check. `hybrid_exit_live=off` in hybrid_robot.env turns that back into a
text-only alert. Do not add a broker call here.
⚠ Every press is also snapshotted into operator_reads.jsonl by gazbot7-capture-read-buy.path; data/hybrid_robot.jsonl is the list
to EXCLUDE from any operator-read fitting.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time

GB = "/home/alphabot/gazbot7"
sys.path.insert(0, f"{GB}/scripts")
sys.path.insert(0, f"{GB}/src")
import leg_robot as L  # noqa: E402  the frozen detector, the veto and the rider gate — imported, not copied
import sim_week_recursive as S  # noqa: E402  the brief, the page, the parser and the fill model — imported, not copied

from gazbot7 import fills_pnl as FP  # noqa: E402  the BROKER's executions, the lock's second book

UTC = dt.timezone.utc
ROBOT = "GazBot V8 Robo"
VERSION = "1.03"
PREV_VERSION = "1.02"            # sessions before MILCAP_FROM ran v1.02 (+LOCK from LOCK_FROM); the nightly labels them by date, never by this constant
LINE = "v2"
QTY = 4
TARGETS = "75,75,75,75"          # $ per lot at $2/pt = all four lots out at +37.5pt
START_AFTER = dt.datetime(2026, 10, 14, 14, 55, tzinfo=UTC)   # E90: lowered from 22:00Z for the one-off afternoon run
EXT_KEY = "2026-10-14"           # E90: this ONE session only runs to EXT_END_MIN instead of 13:30Z (unreplayed, labelled)
EXT_END_MIN = 19 * 60 + 55       # last decision 19:50Z, sim book closed 19:55Z; the rider's own flat is 20:40Z
STOP_AFTER = dt.datetime(2026, 10, 30, 21, 0, tzinfo=UTC)
STEP_S = S.STEP_MIN * 60
MAX_LATE_S = 90                  # a tick that starts later than this after its boundary is a different decision
RECONCILE_SIM = True             # 2026-10-14: drop Claude's sim position when the real desk is flat; UNREPLAYED behaviour
LOCK_USD = 1000.0                # v1.02+LOCK (operator, 2026-10-14): once the day's P&L (realised + open) has touched this, no NEW entries
LOCK_FROM = "2026-10-15"         # first session the lock applies to; earlier sessions are v1.02 / v1.02-EXT and never pooled with it
LEDGER = f"{GB}/data/gazbot7.db"
MIL_CAP = 2                      # v1.03 (E115, operator 2026-10-26): "We can stop at 2 claims on 1 MIL. But then we wait for next mil to be confirmed."
MILCAP_FROM = "2026-10-26"       # first session the cap applies to (live from the first tick after deployment, ~07:50Z that day)
PV = 2.0                         # MNQ $ per point per lot
PRESS_MAX_AGE_S = 240            # decision -> press; older than this the entry is stale (call latency included)
FEED_STALE_S = 180
ALARM_STREAK = 3
POISON_RATE = S.POISON_RATE
DETECTOR_SHA = L.DETECTOR_SHA

SWITCH = f"{GB}/data/hybrid_robot.env"
LEG_SWITCH = L.SWITCH
CLAIM_FILE = f"{GB}/data/day_rider_claim.txt"
BUY_FILE = L.BUY_FILE
STATE_FILE = f"{GB}/data/hybrid_robot_state.json"
LOG_FILE = f"{GB}/data/hybrid_robot.jsonl"
DAYLOG = f"{GB}/reports/hybrid_robot"
CAPTURE = f"{GB}/data/capture.db"


def _enc(o):
    if isinstance(o, dt.datetime):
        return {"__dt__": o.isoformat()}
    raise TypeError(type(o))


def _dec(d: dict):
    return dt.datetime.fromisoformat(d["__dt__"]) if "__dt__" in d else d


def load_state(key: str) -> dict:
    try:
        st = json.load(open(STATE_FILE), object_hook=_dec)
    except Exception:
        st = {}
    if st.get("key") != key:       # a new session never inherits a simulated position (the day_rider `closed`-latch lesson)
        st = {"key": key, "pos": None, "done": [], "calls": 0, "errors": 0, "streak": 0, "alarmed": False,
              "last_op": 0, "presses": [], "closed_out": False, "partial_from": None, "decisions": 0}
    return st


def save_state(st: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1, default=_enc)
    os.replace(tmp, STATE_FILE)


def log(rec: dict) -> None:
    rec = {"robot": ROBOT, "version": VERSION, **rec}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def write_claim(now: dt.datetime) -> str:
    """The operator's own Claim button, flatten-all. Skipped if a request is already waiting."""
    if os.path.exists(CLAIM_FILE):
        return "ALREADY_PENDING"
    with open(CLAIM_FILE, "w") as f:
        f.write(f"{now.isoformat()}|src=hybrid_claude_exit")
    return "WRITTEN"


def exit_alert(pos: dict, px: float, why: str, clock) -> tuple[str, str]:
    """Claude called EXIT while the rider really holds the same side: ask the rider to flatten (unless hybrid_exit_live=off) and text him
    either way. Returns (alert, claim). A fault here must never stop the robot."""
    claim = "NO"
    try:
        rs = L.load_json(L.RIDER_STATE)
        if not rs or rs.get("closed") or not rs.get("entered"):
            return "NOT_LIVE", claim
        ld = 1 if float(rs.get("direction") or 0) > 0 else -1
        if ld != pos["dir"]:
            return "OPPOSITE_SIDE", claim
        n = abs(float(rs.get("venue_net") or 0)) if rs.get("venue_ok") is True else float(rs.get("lots_open") or 0)
        entry = float(rs["entry"])
        now = clock()
        mins = int((now.timestamp() - _epoch(rs["entered_at"])) / 60)
        pnl = ld * (px - entry) * n * PV
        side = "LONG" if ld > 0 else "SHORT"
        auto = L.read_switch(SWITCH, "hybrid_exit_live")
        if auto:
            try:
                claim = write_claim(now)
            except Exception as e:
                claim = f"CLAIM_FAULT_{type(e).__name__}"
        asked = claim in ("WRITTEN", "ALREADY_PENDING")
        if asked:
            tail = "FLATTEN REQUESTED - THE RIDER IS CLOSING IT NOW"
        elif auto:
            tail = "AUTO-FLATTEN FAILED - FLATTEN IT YOURSELF NOW"
        else:
            tail = "THE LIVE POSITION IS STILL OPEN - FLATTEN IT YOURSELF IF YOU AGREE"
        msg = (f"\U0001F6A8\U0001F534\U0001F6A8 CLAUDE EXIT CALLED \U0001F6A8\U0001F534\U0001F6A8\n"
               f"LIVE {side} {n:g} @ {entry:.2f} - LAST {px:.2f} - OPEN {'+' if pnl >= 0 else '-'}${abs(pnl):,.0f} - HELD {mins} MIN\n"
               f"CLAUDE SAYS: {(why or '').upper()[:160]}\n"
               f"{tail}\n"
               f"\U0001F6A8\U0001F534\U0001F6A8 CLAUDE EXIT CALLED \U0001F6A8\U0001F534\U0001F6A8")
        from gazbot7.notify import notify
        return ("SENT" if notify(msg, critical=True, mark=False, weekend_ok=True) else "NOT_SENT"), claim
    except Exception as e:
        return f"ALERT_FAULT_{type(e).__name__}", claim


def page(msg: str, critical: bool = False) -> None:
    """Non-critical by default; never buzzes him in quiet hours. critical=True bypasses them (a persisting ledger/broker mismatch). A paging fault must not crash the robot."""
    try:
        from gazbot7.notify import notify, in_quiet_hours
        if critical:
            notify(msg, critical=True, mark=False, weekend_ok=True)
        elif not in_quiet_hours(dt.datetime.now(UTC)):
            notify(msg, critical=False, mark=False, weekend_ok=True)
    except Exception:
        pass


def session_key(now: dt.datetime) -> str:
    return L.session_day(now).isoformat()


def live_bars(key: str, now_epoch: int):
    """Minute bars (ts, high, low, close) from 22:00Z the evening before, same table/anchor as S.load_day; never past now."""
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
    con = sqlite3.connect(f"file:{CAPTURE}?mode=ro", uri=True)
    rows = con.execute("SELECT bar_ts, high, low, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
                       "AND bar_ts >= ? AND bar_ts <= ? ORDER BY bar_ts", (d0 - 2 * 3600, now_epoch)).fetchall()
    con.close()
    agg: dict = {}
    for ts, h, l, c in rows:
        m = (ts // 60) * 60
        a = agg.setdefault(m, [h, l, c])
        a[0] = max(a[0], h); a[1] = min(a[1], l); a[2] = c
    return [(m, float(v[0]), float(v[1]), float(v[2])) for m, v in sorted(agg.items())]


def preflight() -> str | None:
    if not os.access(S.CLAUDE, os.X_OK):
        return f"the claude binary is not executable at {S.CLAUDE}"
    if L.detector_sha() != DETECTOR_SHA:
        return "the frozen detector changed (sha mismatch)"
    return None


def det_dir(turns: list, t: int) -> int:
    """Direction of the last confirmed turn that was knowable at t (cts + 60 <= t); 0 if none. Causal by construction."""
    cur = 0
    for _piv_ts, _piv_px, nd, cts, _cpx in turns:
        if cts + 60 <= t:
            cur = nd
    return cur


def milcap_enabled(key: str) -> bool:
    """On unless data/hybrid_robot.env carries `hybrid_milcap_off_for=<session key>` for THIS session - a one-day release that expires by itself
    (operator 2026-10-26: "Release the 2 cap per mil just for today")."""
    try:
        return not any(ln.strip() == f"hybrid_milcap_off_for={key}" for ln in open(SWITCH))
    except Exception:
        return True


def mil_pivot(turns: list, t: int) -> tuple | None:
    """(pivot_ts, direction) of the detector's current MIL: the last confirmed turn knowable at t (cts + 60 <= t); None if none."""
    cur = None
    for piv_ts, _piv_px, nd, cts, _cpx in turns:
        if cts + 60 <= t:
            cur = (int(piv_ts), int(nd))
    return cur


def mil_claims(key: str, pivot_ts: int, dirn: int) -> int:
    """Claims already taken on this MIL this session: rider entries in the ledger (gate=day_rider; robot or manual; EXCLUDE/BADFILL
    lots removed), grouped by opened_at, on the MIL's side, opened at/after its pivot (and inside this session), net P&L > 0.
    With all four lots out at +37.5 a claim is an entry whose lots closed in profit. Raises if the ledger cannot be read."""
    lo = max(int(pivot_ts), int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp()) - 2 * 3600)
    side = "LONG" if dirn > 0 else "SHORT"
    con = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT opened_at, side, pnl_usd, data_quality FROM trades WHERE gate='day_rider' AND opened_at >= ?",
                           (dt.datetime.fromtimestamp(lo, UTC).isoformat(),)).fetchall()
    finally:
        con.close()
    net: dict = {}
    for opened, sd, pnl, q in rows:
        if sd != side or (q or "").startswith(("EXCLUDE", "BADFILL")):
            continue
        net[opened] = net.get(opened, 0.0) + float(pnl or 0)
    return sum(1 for v in net.values() if v > 0)


def mil_state(key: str, turns: list, op: int) -> dict | None:
    """The MIL the decision belongs to and its claims so far; claims None = the ledger could not be read (the cap then FAILS CLOSED)."""
    p = mil_pivot(turns, op - 60)
    if p is None:
        return None
    out = {"pivot": dt.datetime.fromtimestamp(p[0], UTC).isoformat(), "dir": p[1], "cap": MIL_CAP}
    try:
        out["claims"] = mil_claims(key, p[0], p[1])
    except Exception as e:
        out["claims"], out["error"] = None, repr(e)[:200]
    return out


def write_press(now: dt.datetime, side: str) -> str:
    line = f"{now.isoformat()}|{side}|{QTY}|{TARGETS}\n"
    with open(BUY_FILE, "w") as f:
        f.write(line)
    return line.strip()


def write_day(st: dict) -> dict:
    os.makedirs(DAYLOG, exist_ok=True)
    calls, errs = st["calls"], st["errors"]
    rate = (errs / calls) if calls else 1.0
    rec = {"robot": ROBOT, "version": VERSION, "day": st["key"], "partial_from": st.get("partial_from"),
           "claude_sim_trades": st["done"], "claude_sim_net_usd": round(sum(t["pnl_usd"] for t in st["done"]), 2),
           "presses": st["presses"], "sim_reconciled": st.get("reconciled", []), "calls": calls, "errors": errs, "error_rate": round(rate, 4),
           "poisoned": rate > POISON_RATE, "brief_sha": S.hashlib.sha256(S.brief_for(LINE).encode()).hexdigest()[:16]}
    json.dump(rec, open(f"{DAYLOG}/{st['key']}.json", "w"), indent=1, default=str)
    return rec


def ext_text(key: str, op: int, text: str) -> str:
    """E90: on the extension session only, tell Claude the true end of ITS window; otherwise the page says the window is over."""
    if key != EXT_KEY:
        return text
    m = dt.datetime.fromtimestamp(op, UTC)
    left = EXT_END_MIN - (m.hour * 60 + m.minute)
    text = re.sub(r"⏱ -?\d+ minutes left in the window", f"⏱ {left} minutes left in the window", text)
    return text.replace("13:30Z", f"{EXT_END_MIN // 60:02d}:{EXT_END_MIN % 60:02d}Z")


def _epoch(s) -> float:
    d = dt.datetime.fromisoformat(str(s))
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp()


def lock_enabled() -> bool:
    """On unless data/hybrid_robot.env carries hybrid_lock=off — the operator's lever for the trial."""
    try:
        return not any(ln.strip().lower() == "hybrid_lock=off" for ln in open(SWITCH))
    except Exception:
        return True


def equity_path(rows: list, live: dict | None, bars: list) -> list:
    """The day's marked equity at each bar close: closed lots' net P&L once closed, open lots marked to the bar.

    rows: ledger dicts (side, qty, entry_price, opened_at, closed_at, pnl_usd); live: the rider's still-open lots
    ({dir, entry, qty, since}) or None; bars: [(close_ts, close)] ascending. Fees on open marks are ignored.
    """
    prep = [(_epoch(r["opened_at"]), _epoch(r["closed_at"]), 1 if r["side"] == "LONG" else -1, float(r["qty"]),
             float(r["entry_price"]), float(r["pnl_usd"])) for r in rows]
    out = []
    for t, c in bars:
        eq = 0.0
        for o, cl, d, q, e, p in prep:
            if cl <= t:
                eq += p
            elif o <= t:
                eq += d * (c - e) * q * PV
        if live and live["since"] <= t:
            eq += live["dir"] * (c - live["entry"]) * live["qty"] * PV
        out.append((t, eq))
    return out


def day_equity(key: str, now_ts: int) -> dict:
    """Has the rider's day touched +LOCK_USD? Read-only: the ledger (gate=day_rider, flagged rows excluded), the rider state, the 5s tape."""
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
    lo = d0 - 2 * 3600
    con = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    try:
        rows = [dict(zip(("side", "qty", "entry_price", "opened_at", "closed_at", "pnl_usd", "data_quality"), r)) for r in con.execute(
            "SELECT side, qty, entry_price, opened_at, closed_at, pnl_usd, data_quality FROM trades "
            "WHERE gate='day_rider' AND closed_at >= ?", (dt.datetime.fromtimestamp(lo, UTC).isoformat(),))]
    finally:
        con.close()
    rows = [r for r in rows if not (r["data_quality"] or "").startswith(("EXCLUDE", "BADFILL"))]
    rs = L.load_json(L.RIDER_STATE)
    live = None
    if rs.get("session") == key and rs.get("entered") and not rs.get("closed"):
        n = abs(float(rs.get("venue_net") or 0)) if rs.get("venue_ok") is True else float(rs.get("lots_open") or 0)
        if n and rs.get("entry") is not None and rs.get("entered_at"):
            live = {"dir": 1 if float(rs.get("direction") or 0) > 0 else -1, "entry": float(rs["entry"]), "qty": n,
                    "since": _epoch(rs["entered_at"])}
    con = sqlite3.connect(f"file:{CAPTURE}?mode=ro", uri=True)
    try:
        bars = [(int(t) + 5, float(c)) for t, c in con.execute(
            "SELECT bar_ts, close FROM bars WHERE symbol='MNQ' AND timeframe='5s' AND bar_ts >= ? AND bar_ts + 5 <= ? ORDER BY bar_ts", (lo, now_ts))]
    finally:
        con.close()
    path = equity_path(rows, live, bars)
    touch = next((t for t, e in path if e >= LOCK_USD), None)
    peak = max(path, key=lambda x: x[1]) if path else (None, 0.0)
    return {"now": round(path[-1][1], 2) if path else 0.0, "peak": round(peak[1], 2), "peak_ts": peak[0], "touch_ts": touch, "bars": len(path)}


def step(now: dt.datetime, dry: bool = False, fake: str | None = None, sleep=time.sleep,
         clock=lambda: dt.datetime.now(UTC)) -> dict:
    now_ts = int(now.timestamp())
    key = session_key(now)
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
    mod = (now_ts - d0) // 60
    out = {"at": now.isoformat(), "session": key, "window_min": mod, "status": None}
    st = load_state(key)

    def done(status, **kw):
        out["status"] = status; out.update(kw)
        if not dry and status not in ("SWITCH_OFF", "WEEKEND", "OUTSIDE_WINDOW", "WAITING_START", "PAST_STOP_AFTER"):
            st["heartbeat"] = now.isoformat(); st["last_status"] = status
            save_state(st)
        return out

    if not L.read_switch(SWITCH, "hybrid_robot"):
        return done("SWITCH_OFF")
    if now < START_AFTER:
        return done("WAITING_START")
    if now >= STOP_AFTER:
        return done("PAST_STOP_AFTER")
    if now.weekday() >= 5:
        return done("WEEKEND")
    if L.read_switch(LEG_SWITCH, "leg_robot"):
        if not st["alarmed"] and not dry:
            st["alarmed"] = True
            page(f"⚠ HYBRID ROBOT v{VERSION} REFUSED: leg_robot is ON too — two robots on one rider's BUY file. Turn one off.")
        log({"at": now.isoformat(), "event": "REFUSED_LEG_ROBOT_ON"}) if not dry else None
        return done("LEG_ROBOT_ON_CONFLICT")
    fault = preflight()
    if fault:
        if not st["alarmed"] and not dry:
            st["alarmed"] = True
            page(f"⚠ HYBRID ROBOT v{VERSION} CANNOT RUN — {fault}\nsession {key}. Nothing is at risk; no entries will be made.")
        return done("PREFLIGHT_FAILED", fault=fault)

    # ── past the window: close the simulated book once and write the day ──────────────────────────
    win_end = EXT_END_MIN if key == EXT_KEY else S.WIN_END_MIN
    if mod >= win_end:
        if mod >= 20 * 60 or st["closed_out"] or (st["decisions"] == 0 and st["calls"] == 0):
            return done("OUTSIDE_WINDOW")
        bars = live_bars(key, now_ts)
        if st["pos"] and bars:
            last = [b for b in bars if b[0] <= d0 + win_end * 60][-1]
            st["done"].append(S._close(st["pos"], last[3], last[0], "WINDOW_CLOSE_1330Z" if win_end == S.WIN_END_MIN else "WINDOW_CLOSE_EXT"))
            st["pos"] = None
        st["closed_out"] = True
        if dry:
            return done("DAY_CLOSE_DRY")
        rec = write_day(st)
        log({"at": now.isoformat(), "event": "DAY_WRITTEN", **{k: rec[k] for k in
             ("day", "claude_sim_net_usd", "calls", "errors", "error_rate", "poisoned", "partial_from")},
             "presses": len(rec["presses"])})
        return done("DAY_WRITTEN", day=rec["day"], poisoned=rec["poisoned"])
    if mod < S.WIN_START_MIN:
        return done("OUTSIDE_WINDOW")

    # ── the decision boundary this tick belongs to ────────────────────────────────────────────────
    op = now_ts - (now_ts - d0) % STEP_S
    if now_ts - op > MAX_LATE_S:
        return done("LATE_TICK", late_s=now_ts - op)
    if op <= st["last_op"]:
        return done("ALREADY_DECIDED", op=op)

    allbars = live_bars(key, now_ts)
    if not allbars:
        return done("NO_BARS")
    feed_age = now_ts - (allbars[-1][0] + 5)
    if feed_age > FEED_STALE_S:
        st["stale_n"] = st.get("stale_n", 0) + 1
        if st["stale_n"] == ALARM_STREAK and not dry:
            page(f"⚠ HYBRID ROBOT v{VERSION}: tape is {feed_age}s stale for {ALARM_STREAK} ticks — declining to decide on a dead feed.")
        return done("FEED_STALE", feed_age_s=feed_age)
    st["stale_n"] = 0
    if key >= LOCK_FROM and lock_enabled():            # v1.02+LOCK: the day has touched +LOCK_USD → no new entries, no Claude call, rest of the session
        if not st.get("lock"):
            try:
                eq = day_equity(key, now_ts)
            except Exception as e:                      # fail OPEN but LOUD: a lock that cannot check must not look like a lock that checked
                eq = None
                if not dry:
                    log({"at": now.isoformat(), "event": "LOCK_CHECK_ERROR", "error": repr(e)})
                    if not st.get("lock_err_paged"):
                        st["lock_err_paged"] = True
                        page(f"⚠ HYBRID ROBOT v{VERSION}+LOCK: cannot read the day's P&L ({e!r}) — the +${LOCK_USD:,.0f} lock is NOT protecting this session.")
            if eq and eq["touch_ts"] is not None:
                # ★2026-10-22 second book: the ledger says +$1000, but do the BROKER's executions agree? Phantom booked
                # profit (the double-booked exit) must not latch a lock. Fails toward latching when fills are unreadable.
                trusted, xc = FP.ledger_trust(LEDGER, key)
                if not trusted:
                    st["lock_xcheck_n"] = st.get("lock_xcheck_n", 0) + 1
                    if not dry:
                        log({"at": now.isoformat(), "event": "LOCK_WITHHELD_LEDGER_MISMATCH", "n": st["lock_xcheck_n"], **xc})
                        page(f"⚠ HYBRID ROBOT v{VERSION}+LOCK: the day's ledger shows +${LOCK_USD:,.0f} but the broker's executions show only "
                             f"{xc['fills']:+,.0f} (ledger {xc['ledger']:+,.0f}, gap {xc['diff']:+,.0f}). Lock NOT latched - "
                             "phantom booking? Check trades/fills.", critical=st["lock_xcheck_n"] >= 2)
                    eq = None
                else:
                    st["lock_xcheck_n"] = 0
                    if xc.get("unverified") and not dry:
                        log({"at": now.isoformat(), "event": "LOCK_XCHECK_UNVERIFIED", "why": xc["unverified"]})
            if eq and eq["touch_ts"] is not None:
                st["lock"] = {"at": now.isoformat(), "limit": LOCK_USD, "touched_at": dt.datetime.fromtimestamp(eq["touch_ts"], UTC).isoformat(),
                              "equity_now": eq["now"], "peak": eq["peak"], "decision_ts": dt.datetime.fromtimestamp(op, UTC).isoformat()}
                if not dry:
                    log({"at": now.isoformat(), "event": "DAY_LOCK", **st["lock"]})
                    page(f"🔒 HYBRID ROBOT v{VERSION}+LOCK: the day touched +${LOCK_USD:,.0f} at {st['lock']['touched_at'][11:16]}Z (now {eq['now']:+,.0f}, peak {eq['peak']:+,.0f}). "
                         "No new entries for the rest of this session. Any open position keeps riding.")
        if st.get("lock"):
            st["last_op"] = op
            return done("DAY_LOCKED", lock=st["lock"])
    upto = [b for b in allbars if b[0] + 60 <= op]          # CLOSED bars as of the decision time, nothing newer
    if len(upto) < 60:
        return done("NO_BARS", bars=len(upto))
    S._assert_causal(upto, op)
    px = upto[-1][3]
    if st["partial_from"] is None and st["decisions"] == 0 and mod > S.WIN_START_MIN + S.STEP_MIN:
        st["partial_from"] = dt.datetime.fromtimestamp(op, UTC).isoformat()

    # ── reconcile Claude's simulated book with the real desk BEFORE he is asked (operator, 2026-10-14) ──
    # Claude's sim book used to live on its own: an entry that was never pressed (skipped by the gate, vetoed,
    # against the leg, or fully harvested by the rider's ladder) left it "long/short" while the desk was flat, so he
    # answered HOLD and the desk could not re-enter. If the rider is demonstrably flat, the sim position is dropped
    # (NOT booked: it never traded) so he sees "flat" and may call an entry. Any other rider state (holding, blind,
    # stale, venue not ok, request pending) is "unknown" and leaves the sim book alone.
    reconciled = None
    if RECONCILE_SIM and st["pos"] and L.rider_gate(now if dry else clock()) is None:
        gone = st["pos"]
        reconciled = {"decision_ts": dt.datetime.fromtimestamp(op, UTC).isoformat(), "side": "BUY" if gone["dir"] > 0 else "SELL",
                      "sim_entry": gone["entry"], "sim_opened": gone["opened"].isoformat() if isinstance(gone["opened"], dt.datetime) else str(gone["opened"]),
                      "px": px, "real": "FLAT"}
        st["pos"] = None
        st.setdefault("reconciled", []).append(reconciled)
        if not dry:
            log({"at": now.isoformat(), "event": "SIM_RECONCILED", **reconciled})

    pos = st["pos"]
    if pos:                                                # exactly run_day's bookkeeping of the simulated position's peak
        pos["peak"] = max(pos["peak"], pos["dir"] * (px - pos["entry"]))
        seg = [b[3] for b in upto if pos["last_ts"] < b[0] <= op]
        if seg:
            pos["peak_1m"] = max(pos["peak_1m"], max(pos["dir"] * (c - pos["entry"]) for c in seg))
        pos["last_ts"] = op
        pos["peak"] = max(pos["peak"], pos["peak_1m"])

    t_call = time.time()
    if fake is not None:
        d = {"action": fake, "reason": "FAKE (dry run)", "confidence": None}
    else:
        d = S.ask(ext_text(key, op, S.brief_for(LINE) + "\n\n=== THE TAPE ===\n"
                  + S.context(upto, op, pos, "", st["done"], True, band=False, leg_list=False, mil=False, card=False)))
    latency = round(time.time() - t_call, 1)
    act = d.get("action", "WAIT")
    if fake is None:
        st["calls"] += 1
        if d.get("error"):
            st["errors"] += 1; st["streak"] += 1
        else:
            st["streak"] = 0
        if st["streak"] == ALARM_STREAK and not st["alarmed"] and not dry:
            st["alarmed"] = True
            page(f"⚠ HYBRID ROBOT v{VERSION} IS FAILING EVERY CALL — {st['streak']} in a row\n{d.get('error')}\n"
                 f"session {key}, {st['errors']}/{st['calls']} calls errored. No entries are being made. Nothing is at risk.")
    st["decisions"] += 1
    st["last_op"] = op
    rec = {"at": now.isoformat(), "event": "DECISION", "decision_ts": dt.datetime.fromtimestamp(op, UTC).isoformat(),
           "px": px, "action": act, "conf": d.get("confidence"), "reason": (d.get("reason") or "")[:300],
           "error": d.get("error"), "sim_holding": bool(pos), "latency_s": latency, "dry": dry}
    if reconciled:
        rec["sim_reconciled"] = True
    out["decision"] = rec

    pressed = None
    if pos is None and act in ("ENTER_LONG", "ENTER_SHORT"):
        dirn = 1 if act == "ENTER_LONG" else -1
        st["pos"] = {"dir": dirn, "entry": px + dirn * S.HALF_SPREAD_PT, "peak": 0.0, "peak_1m": 0.0, "last_ts": op,
                     "opened": dt.datetime.fromtimestamp(op, UTC), "reason": (d.get("reason") or "")[:200]}
        side = "BUY" if dirn > 0 else "SELL"
        series = [b for b in L.series_for(L.session_day(now)) if b[0] + 60 <= now_ts - L.SETTLE_S]
        turns = L.confirmed_turns(series) if len(series) >= 200 else []
        dd = det_dir(turns, op - 60)
        mil = mil_state(key, turns, op) if key >= MILCAP_FROM and dd == dirn and milcap_enabled(key) else None
        if mil:
            rec["mil"] = mil
        cut = L.veto_cutoff(op)
        rec["candidate"] = side
        rec["detector_dir"] = dd
        rec["veto_cutoff"] = dt.datetime.fromtimestamp(cut, UTC).isoformat() if cut else None
        if dd != dirn:
            rec["entry_action"] = "NOT_WITH_LEG" if dd else "NO_DETECTOR_LEG"
        elif cut is not None and op < cut:
            rec["entry_action"] = "VETOED_BEFORE_05_PARIS"
        elif mil and (mil["claims"] is None or mil["claims"] >= MIL_CAP):       # v1.03: 2 claims on this MIL -> wait for the next MIL
            rec["entry_action"] = "MIL_CAP_UNREADABLE" if mil["claims"] is None else f"MIL_CAP_{MIL_CAP}_CLAIMS"
            if mil["claims"] is None and not dry and not st.get("milcap_err_paged"):
                st["milcap_err_paged"] = True
                page(f"⚠ HYBRID ROBOT v{VERSION}: cannot read the ledger to count claims on this MIL ({mil.get('error')}) - the MIL cap FAILS CLOSED: "
                     "no new entries until it can count again.")
        elif (cnow := (now if dry else clock())).timestamp() - op > PRESS_MAX_AGE_S:
            rec["entry_action"] = "STALE_NOT_ENTERED"
        elif (why := L.rider_gate(cnow)):
            rec["entry_action"] = "SKIPPED_" + why
        else:
            rec["entry_action"] = "PRESS_" + side
            if not dry:
                rec["request"] = write_press(cnow, side)
            pressed = (side, rec)
    elif st["pos"] and act == "EXIT":
        if not dry:
            rec["exit_alert"], rec["exit_claim"] = exit_alert(st["pos"], px, rec.get("reason"), clock)
        st["done"].append(S._close(st["pos"], px, op, "CLAUDE_EXIT"))
        st["pos"] = None

    if dry:
        return done("DRY_DECISION", entry_action=rec.get("entry_action"))
    log(rec)
    if pressed:
        for _ in range(8):
            sleep(1)
            if not os.path.exists(BUY_FILE):
                break
        after = L.load_json(L.RIDER_STATE)
        res = {"at": clock().isoformat(), "event": "PRESS_RESULT",
               "request_consumed": not os.path.exists(BUY_FILE), "rider_entered": after.get("entered"),
               "rider_entry": after.get("entry"), "rider_targets_usd": after.get("manual_targets_usd"),
               "rider_note": after.get("note")}
        log(res); out["press_result"] = res
        st["presses"].append({"decision_ts": rec["decision_ts"], "side": pressed[0], "request": rec.get("request"),
                              "consumed": res["request_consumed"], "entry": res["rider_entry"]})
    return done("PRESSED" if pressed else "OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry", action="store_true", help="decide and print; write no request, log or state")
    ap.add_argument("--at", help="ISO time (dry runs only)")
    ap.add_argument("--fake", help="dry runs only: replace Claude's answer (WAIT / ENTER_LONG / ENTER_SHORT / EXIT)")
    a = ap.parse_args()
    if (a.at or a.fake) and not a.dry:
        print("--at / --fake require --dry"); return 2
    now = dt.datetime.fromisoformat(a.at) if a.at else dt.datetime.now(UTC)
    try:
        r = step(now, dry=a.dry, fake=a.fake)
    except Exception as e:
        log({"at": now.isoformat(), "event": "ERROR", "error": repr(e)})
        print("ERROR", repr(e)); return 1
    print(json.dumps(r, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
