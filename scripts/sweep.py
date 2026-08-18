#!/usr/bin/env python3
"""GAZBOT V7 — the maintenance-sweep collector.

Deterministic, read-only health readout for the three-service desk. A cron
prompt runs this, reads the JSON, and (a) buzzes the operator on CRIT / degraded
gateway, (b) sends a curated heartbeat in waking hours, (c) does bounded fixes
from the V7 allowlist. Keeping the facts in a tested script (not the prompt)
means the heartbeat is honest and cheap — no false "desk running" when it isn't.

This is the BROAD periodic sweep, distinct from ``monitor.py`` (the tight
10-min fills-based execution-wedge alarm, which this reuses for the exec line).
VENUE-TRUTH-FIRST: the script trusts core's own freshly-written health/position
truth; it never second-guesses the venue from the store. Clean-room.

    python scripts/sweep.py            # human report + JSON footer
    python scripts/sweep.py --json     # JSON only (for the cron to parse)
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import monitor, pnl, session  # noqa: E402
from gazbot7.config import RunConfig  # noqa: E402

OK, WARN, CRIT = "OK", "WARN", "CRIT"
_RANK = {OK: 0, WARN: 1, CRIT: 2}

# md (feed) + gateway (shared IBKR link) are always-on infra. The DESK is the
# multi-slot tournament (2026-07-21 cutover) — it REPLACED core+strategy, which are now
# the retired revert target (intentionally inactive; not a fault). The sweep treats the
# desk as up when the tournament is active OR (a revert) both legacy services are active.
_CRIT_SERVICES = ("gazbot7-md", "alphabot-gateway")   # always-on infra
_DESK_PRIMARY = "gazbot7-tournament"                   # the live desk
_DESK_LEGACY = ("gazbot7-core", "gazbot7-strategy")    # retired single-position desk (revert target)
# ★2026-08-04 gazbot7-depth-capture added. It ran for three weeks as alphabot-depth-capture in the
# retired V5 tree where NOTHING swept it — a silent death would have stopped the 20-day book history
# that every L2 study depends on, and no check would have fired. SOFT because the desk trades fine
# without it (no gate reads depth yet); it is research/verification input, not the order path.
_SOFT_SERVICES = ("gazbot7-shadow", "gazbot7-web", "gazbot7-depth-capture")
# ★★2026-08-14 RESTARTS ARE COUNTED IN A WINDOW, NOT SINCE BOOT.
# `NRestarts` is CUMULATIVE and never self-resets, so comparing it to a fixed threshold meant that
# once the desk tripped it, sweep WARNed forever and the number only ever grew. That is not a flap
# detector, it is a monotonic counter with an alarm bolted on — and a monitor that is permanently
# amber is a monitor you stop reading. It tripped on the NIGHTLY IBKR GATEWAY RESET: the tournament
# watchdog-aborts and self-heals at ~04:32-04:46 UTC every night (Error 1100 lost -> SIGABRT ->
# Error 1102 restored -> clean start, ~4 min), which is benign because the desk is always flat then
# (Asia block refuses entries + max_hold 120min). Seven of eight restarts in the week to 08-14 were
# that. See [[nightly-ibkr-gateway-reset-restarts-the-desk]].
#
# A WINDOW makes the check mean what its name says: real flapping is a restart LOOP (systemd's
# RestartSec puts dozens in an hour), while the nightly reset contributes at most 2. It also
# SELF-CLEARS an hour later instead of needing a human `systemctl reset-failed`.
_RESTART_STORM = 3          # restarts INSIDE the window = flapping
_RESTART_WINDOW_MIN = 60
DEPTH_PATH = os.environ.get("DEPTH_DB", "/home/alphabot/gazbot7/data/depth.db")


def _worst(*s: str) -> str:
    return max(s, key=lambda x: _RANK.get(x, 0)) if s else OK


def _svc(name: str) -> dict:
    try:
        out = subprocess.run(
            ["systemctl", "show", name, "-p", "ActiveState", "-p", "NRestarts"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        return {"active": kv.get("ActiveState") == "active",
                "state": kv.get("ActiveState", "?"),
                "restarts": int(kv.get("NRestarts", "0") or 0)}
    except Exception as e:  # systemctl absent / timeout — report, don't crash
        return {"active": False, "state": f"err:{e}", "restarts": 0}


def _restarts_recent(name: str, minutes: int = _RESTART_WINDOW_MIN) -> int | None:
    """How many times systemd restarted `name` in the last `minutes`.

    Returns None if the journal cannot be read — the CALLER must then fall back to the cumulative
    counter rather than reporting zero. Returning 0 on an unreadable journal would turn a monitoring
    outage into a clean bill of health, which is the failure this desk keeps meeting
    ([[an-instrument-that-reports-healthy-about-something-it-does-not-check]]).
    """
    try:
        r = subprocess.run(
            ["journalctl", "-u", name, "--since", f"-{int(minutes)}min", "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return None
        return sum(1 for ln in r.stdout.splitlines() if "Scheduled restart job" in ln)
    except Exception:
        return None


def _conn(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path, timeout=5)
    c.row_factory = sqlite3.Row
    return c


# ── sections ──────────────────────────────────────────────────────────────────
def check_services() -> dict:
    names = (*_CRIT_SERVICES, _DESK_PRIMARY, *_DESK_LEGACY, *_SOFT_SERVICES)
    svc = {n: _svc(n) for n in names}
    status = OK
    notes = []
    for n in _CRIT_SERVICES:
        if not svc[n]["active"]:
            status = CRIT
            notes.append(f"{n} {svc[n]['state']}")
    # the desk: tournament (primary) OR the legacy core+strategy (a revert) must be up.
    # core/strategy alone being inactive is EXPECTED post-cutover — not a fault.
    desk_up = svc[_DESK_PRIMARY]["active"] or all(svc[n]["active"] for n in _DESK_LEGACY)
    if not desk_up:
        status = CRIT
        notes.append("NO DESK running (tournament + core/strategy all inactive)")
    for n in _SOFT_SERVICES:
        if not svc[n]["active"]:
            status = _worst(status, WARN)
            notes.append(f"{n} {svc[n]['state']}")
    # only storm on services that are SUPPOSED to run (skip the intentionally-off legacy desk)
    watched = {*_CRIT_SERVICES, _DESK_PRIMARY, *_SOFT_SERVICES}
    recent = {n: _restarts_recent(n) for n in sorted(watched)}
    storms, degraded = [], []
    for n in sorted(watched):
        got = recent[n]
        if got is None:
            # journal unreadable → fall back to the cumulative counter so we never go silent, but
            # SAY SO, because that number cannot self-clear and will read as a permanent storm.
            if svc[n]["restarts"] >= _RESTART_STORM:
                degraded.append(f"{n}×{svc[n]['restarts']} cumulative")
        elif got >= _RESTART_STORM:
            storms.append(f"{n}×{got}")
    if storms:
        status = _worst(status, WARN)
        notes.append(f"restart-storm (last {_RESTART_WINDOW_MIN}min): " + ",".join(storms))
    if degraded:
        status = _worst(status, WARN)
        notes.append("restart-count DEGRADED, journal unreadable: " + ",".join(degraded))
    desk = _DESK_PRIMARY if svc[_DESK_PRIMARY]["active"] else ("core+strategy (reverted)" if desk_up else "NONE")
    detail = f"all up · desk={desk}" if status == OK else "; ".join(notes)
    return {"status": status, "detail": detail,
            "restarts": {n: v["restarts"] for n, v in svc.items()},   # cumulative, kept for history
            "restarts_recent": recent,
            "restart_window_min": _RESTART_WINDOW_MIN}


def check_core(cfg: RunConfig, now: datetime) -> dict:
    """core_health.json is the pre-flight gate — its freshness + conn state gate
    every downstream signal and every auto-fix."""
    path = os.path.join(os.path.dirname(cfg.store_path), "core_health.json")
    try:
        h = json.loads(open(path).read())
    except Exception as e:
        return {"status": CRIT, "detail": f"core_health unreadable ({e}) — core down?",
                "preflight_ok": False}
    try:
        age = (now - datetime.fromisoformat(h["ts"])).total_seconds()
    except Exception:
        age = 1e9
    conn_ok = h.get("conn") == "HEALTHY" and h.get("healthy") is True
    halted = bool(h.get("halted"))
    fresh = age <= 180
    # the audit-loop tell: the safety spine (max-hold/stop-breach/naked) runs in a SEPARATE loop
    # from the main heartbeat. On 2026-07-22 it died silently while the heartbeat stayed green and a
    # position rode 153min past max-hold. audit_age_s is how long since it last COMPLETED a cycle —
    # stale (while live) = the auditor is dead/hung even though hb looks fine. CRIT.
    audit_age = h.get("audit_age_s")
    audit_stale = bool(h.get("place_live") and audit_age is not None and audit_age > 30)
    status = OK
    notes = []
    if not fresh:
        status = CRIT
        notes.append(f"heartbeat STALE {age:.0f}s (core hung/down)")
    if not conn_ok:
        status = CRIT
        notes.append(f"gateway conn={h.get('conn')} healthy={h.get('healthy')}")
    if audit_stale:
        status = CRIT
        notes.append(f"AUDIT LOOP STALE {audit_age:.0f}s (safety spine dead — max-hold/stop-breach NOT running)")
    # ★★2026-08-16 — A TURNING LOOP IS NOT A WORKING ONE. On `drift` the audit loop skips its ENTIRE
    # safety block (max-hold, naked-audit, re-protect, stop-breach, exit watchdog) while still
    # COMPLETING its cycle — so audit_age_s stays green and this section passed clean throughout the
    # whole 08-06 incident. audit_age_s answers "is the loop alive"; safety_skipped_cycles answers
    # "did the work inside it run", and only the first was ever published. CRIT while HOLDING,
    # because an open position with no max-hold and no stop-breach check is the state that produced
    # a naked short.
    skipped = h.get("safety_skipped_cycles") or 0
    if skipped and not h.get("flat", True):
        status = CRIT
        notes.append(f"SAFETY BLOCK SKIPPED {skipped} cycles while HOLDING (drift — max-hold / "
                     f"naked-audit / stop-breach ALL inactive; audit_age is green but meaningless)")
    elif skipped:
        status = _worst(status, WARN)
        notes.append(f"safety block skipped {skipped} cycles (drift, desk flat)")
    if halted:
        status = _worst(status, WARN)
        notes.append("desk HALTED (kill-switch)")
    detail = (f"HEALTHY, {'flat' if h.get('flat') else 'HOLDING'}, live={h.get('place_live')}, "
              f"hb {age:.0f}s, audit {audit_age if audit_age is not None else 'n/a'}s") if status == OK else "; ".join(notes)
    # pre-flight is clean only when the heartbeat is fresh, the gateway is healthy, AND the audit
    # loop is live (a dead auditor = positions unmanaged, so downstream signals can't be trusted)
    return {"status": status, "detail": detail, "preflight_ok": fresh and conn_ok and not audit_stale,
            "flat": bool(h.get("flat", True)), "halted": halted,
            "protection": h.get("protection")}


def check_capture(cfg: RunConfig, now: datetime) -> dict:
    market_open = session.is_open(now)
    try:
        cap = _conn(cfg.capture_path)
        bar_ts = cap.execute(
            "SELECT max(bar_ts) FROM bars WHERE symbol=? AND timeframe='5s'", (cfg.symbol,)
        ).fetchone()[0]
        tick_ms = cap.execute(
            "SELECT max(ts_ms) FROM ticks WHERE symbol=?", (cfg.symbol,)
        ).fetchone()[0]
        cap.close()
    except Exception as e:
        return {"status": WARN, "detail": f"capture read error: {e}"}
    now_s = now.timestamp()
    bar_age = now_s - bar_ts if bar_ts else 1e9
    tick_age = now_s - tick_ms / 1000 if tick_ms else 1e9
    if not market_open:
        return {"status": OK, "detail": f"MARKET CLOSED (5s {bar_age:.0f}s, tick {tick_age:.0f}s)",
                "bar_age": round(bar_age, 1), "tick_age": round(tick_age, 1)}
    status, notes = OK, []
    # the feed-break tell: ticks flowing but the 5s farm dropped (reqRealTimeBars) →
    # gateway restart territory (flag; the cron decides, restart is flag-and-wait)
    if tick_age <= 30 and bar_age > 120:
        status = CRIT
        notes.append(f"5s STALE {bar_age:.0f}s while ticks live {tick_age:.0f}s — farm drop (GATEWAY)")
    elif bar_age > 120:
        status = _worst(status, WARN)
        notes.append(f"5s bars stale {bar_age:.0f}s")
    if tick_age > 60:
        status = _worst(status, WARN)
        notes.append(f"ticks stale {tick_age:.0f}s")
    # ★2026-08-04 L2 DEPTH FRESHNESS. An ACTIVE gazbot7-depth-capture unit is not proof it is
    # capturing — the same trap as the router's full-roster pin, which logged "no change" for 411 ticks
    # while doing nothing. So check the DATA, not the process: depth_capture dedups a static book and
    # flushes every 1s, so a genuinely live MNQ book should never be more than a few seconds behind
    # during a session. WARN only — no gate reads depth yet, so a gap costs research, not trades.
    depth_age = None
    try:
        dcon = sqlite3.connect(f"file:{DEPTH_PATH}?mode=ro", uri=True, timeout=2.0)
        try:
            r = dcon.execute("SELECT max(ts_ms) FROM depth_snap WHERE symbol=?", (cfg.symbol,)).fetchone()
        finally:
            dcon.close()
        if r and r[0]:
            depth_age = now_s - r[0] / 1000
            if depth_age > 120:
                status = _worst(status, WARN)
                notes.append(f"L2 depth stale {depth_age:.0f}s")
        else:
            status = _worst(status, WARN)
            notes.append("L2 depth: no rows for symbol")
    except Exception as e:
        status = _worst(status, WARN)
        notes.append(f"L2 depth unreadable: {e}")
    d_txt = f", L2 {depth_age:.0f}s" if depth_age is not None else ", L2 n/a"
    detail = (f"capture OK (5s {bar_age:.0f}s, tick {tick_age:.0f}s{d_txt})"
              if status == OK else "; ".join(notes))
    return {"status": status, "detail": detail, "bar_age": round(bar_age, 1),
            "tick_age": round(tick_age, 1), "market_open": market_open,
            "depth_age": round(depth_age, 1) if depth_age is not None else None}


def check_execution(store, now: datetime) -> dict:
    since = (now.timestamp() - 1800)
    since_iso = datetime.fromtimestamp(since, UTC).isoformat()
    v = monitor.execution_health(store, since_iso=since_iso)
    return {"status": v.status, "detail": v.detail,
            "submitted": v.submitted, "fills": v.fills, "rejects": v.rejects}


# ── the DAY RIDER is a SECOND desk and core_health.json knows nothing about it ──
DR_HB_STALE_S = 180        # 3 ticks missed; the watchdog acts at 2, so this is not trigger-happy
DR_FLAT_UTC_MIN = 20 * 60 + 40     # day_rider.FLAT_UTC_MIN — hard flat, never held overnight
# The flatten FIRES at 20:40 and needs a few seconds to fill, so grade it overdue only after
# three ticks have had their chance. Without this the sweep CRITs at 20:40:30 on a flatten
# that is working normally — a false alarm on a schedule, which is how alarms get ignored.
DR_OVERDUE_UTC_MIN = DR_FLAT_UTC_MIN + 3


def _day_rider_position(cfg, now) -> dict | None:
    """The day rider's open position, or None if it holds nothing.

    ★2026-08-10. The sweep read core_health.json only — the TOURNAMENT's truth —
    and so printed "flat" while the day rider sat SHORT 2 lots, 30pt offside, with
    an unarmed trail. The dashboard was given this surface on 08-07 for exactly
    this reason ("a live position with no surface is how 08-06 stayed invisible
    for hours"); the 3-hourly health check never got it. Same blind spot, quieter
    place.

    Fail-soft by design: any error returns None and the caller renders the
    tournament verdict exactly as before, so a garbled state file can never blank
    the position check. The cost is that an unreadable file reads as "no day-rider
    position" — acceptable only because the heartbeat check below catches a rider
    that has actually stopped.
    """
    if cfg is None:
        return None
    try:
        path = os.path.join(os.path.dirname(cfg.store_path), "day_rider_state.json")
        with open(path) as fh:
            d = json.load(fh)
    except Exception:
        return None
    if not d.get("entered") or d.get("closed"):
        return None
    try:
        qty = abs(float(d.get("qty") or 0))
        direction = int(d.get("direction") or 0)
    except Exception:
        return None
    if qty <= 0 or direction not in (-1, 1):
        return None
    out = {"side": "LONG" if direction > 0 else "SHORT", "qty": qty,
           "entry": d.get("entry"), "ahead_pt": d.get("ahead_pt"),
           # An UNARMED trail is not protection. The 600pt venue stop is
           # last-resort insurance by the strategy's own documentation, so it must
           # not be reported as a working protective stop.
           "trail": d.get("trail"), "protected": bool(d.get("trail"))}
    hb = d.get("heartbeat")
    age = None
    if hb and now is not None:
        try:
            age = (now - datetime.fromisoformat(hb)).total_seconds()
        except Exception:
            age = None
    out["hb_age_s"] = round(age, 1) if age is not None else None
    out["stale"] = bool(age is not None and age > DR_HB_STALE_S)
    # Past its own hard flat and still holding: the standing rule is NEVER hold
    # overnight, and after 21:00Z the venue is shut and nothing can be done.
    mins = (now.hour * 60 + now.minute) if now is not None else None
    out["overdue"] = bool(mins is not None and mins >= DR_OVERDUE_UTC_MIN)
    return out


def _merge_day_rider(verdict: dict, dr: dict | None) -> dict:
    """Fold the day rider into the tournament's position verdict, worst-status wins.

    ★ WHAT IS AND IS NOT AN ALARM HERE. Riding with an UNARMED trail is the
    strategy working as designed — the trail arms at 4xATR and a losing trade may
    never reach it. Grading that CRIT would paint the sweep red on ordinary days
    and train the operator to ignore it, the same reasoning that keeps the dirty-
    tree check at WARN. So a normal ride reports OK and simply states, honestly,
    that the only backstop is the 600pt venue stop.

    Two things ARE alarms, and neither was visible anywhere before:
      · a STALE heartbeat while holding — a live position whose manager has
        stopped ticking is the 08-06 shape exactly;
      · still holding past the 20:40Z hard flat — the standing rule is NEVER hold
        overnight, and after 21:00Z the venue is shut.
    """
    if not dr:
        return verdict
    pos = f"day_rider {dr['side']} {dr['qty']:g}"
    if dr.get("entry"):
        pos += f" @ {dr['entry']:g}"
    if dr.get("ahead_pt") is not None:
        pos += f" ({dr['ahead_pt']:+g}pt)"
    if dr.get("overdue"):
        st, note = CRIT, "STILL HOLDING past the 20:40Z hard flat — CHECK IBKR / flatten"
    elif dr.get("stale"):
        st, note = CRIT, f"heartbeat STALE {dr['hb_age_s']:.0f}s while holding — rider may be dead"
    elif dr.get("protected"):
        st, note = OK, f"trail armed @ {dr['trail']:g}"
    else:
        st, note = OK, "trail NOT armed — only the 600pt venue stop behind it"
    out = dict(verdict)
    out["day_rider"] = dict(dr)
    out["held"] = True
    out["detail"] = f"{verdict['detail']} · {pos} — {note}"
    if (st, verdict.get("status")) != (OK, OK):
        out["status"] = CRIT if CRIT in (st, verdict.get("status")) else WARN
    return out


def check_position(store, core: dict, cfg=None, now=None) -> dict:
    """VENUE-TRUTH protection gate, read from core's freshly-written ``protection`` block
    (2026-07-17 lesson: 'held' is not 'protected' — a stop-less position bled for 3h reading
    OK). Multi-slot tournament: ``protection.slots`` each carry a ``stop_coid`` (a live venue
    order) — a held slot without one is NAKED. Also handles the retired single-position shape
    (``protection.verified``) for a revert. Reads core-health only — NOT the ``open_position``
    table (the tournament's truth is per-slot, so that table is empty here by design)."""
    dr = _day_rider_position(cfg, now)
    flat = bool(core.get("flat", True))
    prot = core.get("protection") if isinstance(core.get("protection"), dict) else {}
    slots = prot.get("slots") or []
    held = (not flat) or bool(slots) or bool(prot.get("held"))
    if not held:
        # The tournament is flat. The DESK is only flat if the day rider is too.
        if dr:
            return _merge_day_rider({"status": OK, "detail": "tournament flat"}, dr)
        return {"status": OK, "detail": "flat"}
    # held → gate on protection. 'can't verify' is never 'safe'.
    unver = prot.get("unverified_cycles") or 0
    if unver:
        return _merge_day_rider({"status": CRIT, "held": True,
                "detail": f"held but venue snapshot UNVERIFIABLE {unver} cycles — CHECK IBKR / flatten"}, dr)
    if prot.get("verified") is False:              # single-position shape (reverted desk)
        return _merge_day_rider({"status": CRIT, "held": True,
                "detail": "held but protection NOT verified — CHECK IBKR / flatten"}, dr)
    naked = [str(s.get("gate")) for s in slots if not s.get("stop_coid")]   # tournament per-slot
    if naked:
        return _merge_day_rider({"status": CRIT, "held": True,
                "detail": f"NAKED slot(s) {', '.join(naked)} — no stop resting; CHECK IBKR / flatten"}, dr)
    if slots:
        desc = ", ".join(f"{s.get('gate')} {s.get('side')} {s.get('qty'):g}" for s in slots)
        return _merge_day_rider(
            {"status": OK, "held": True, "detail": f"holding {len(slots)} slot(s): {desc} — all protected"}, dr)
    return _merge_day_rider({"status": OK, "held": True, "detail": "holding — protected"}, dr)


def check_killswitch(cfg: RunConfig, store, core: dict, now: datetime) -> dict:
    # ★2026-08-07 TWO DESKS, TWO NUMBERS. The killswitch and the "is the desk working?" question are
    # about the TOURNAMENT's book; the day-rider is a separate strategy whose single multi-hour trade
    # can swing more than 20 scalps combined and would otherwise mask the desk entirely.
    day_pnl, day_n, day_w = pnl.day(store, cfg.symbol, now, desk="tournament")
    dr_pnl, dr_n, dr_w = pnl.day(store, cfg.symbol, now, desk="day_rider")
    tail = store.execute(
        "SELECT pnl_usd FROM trades WHERE symbol=? AND exit_reason NOT IN ('ADOPT_FLATTEN') "
        "ORDER BY id DESC LIMIT 20", (cfg.symbol,)
    ).fetchall()
    streak = 0
    for r in tail:
        if r[0] < 0:
            streak += 1
        else:
            break
    status, notes = OK, []
    if core.get("halted"):
        status = WARN
        notes.append("HALTED")
    if cfg.max_daily_loss_usd and day_pnl <= -cfg.max_daily_loss_usd:
        status = _worst(status, WARN)
        notes.append(f"day P&L ${day_pnl} at/over -${cfg.max_daily_loss_usd} cap")
    if cfg.loss_streak_halt and streak >= cfg.loss_streak_halt:
        status = _worst(status, WARN)
        notes.append(f"loss streak {streak} >= {cfg.loss_streak_halt}")
    detail = (f"day ${day_pnl} ({day_w}/{day_n}W), streak {streak} — headroom OK"
              if status == OK else "; ".join(notes))
    if dr_n:
        detail += f" | DAY-RIDER ${dr_pnl} ({dr_w}/{dr_n})"
    return {"status": status, "day_rider_pnl": dr_pnl, "day_rider_trades": dr_n,
            "detail": detail, "day_pnl": day_pnl, "day_trades": day_n,
            "day_wins": day_w, "loss_streak": streak}


def check_book_vs_fills(store, now: datetime, *, days: int = 3) -> dict:
    """Does the trade ledger match what IBKR actually executed?

    ★★2026-08-14. `trades` is what we BELIEVE happened, `fills` is what the venue SAYS happened, and
    until now nothing compared them — so the two were wrong together twice (08-13's +$1,551 of
    profit from orders that sold 8 lots the desk did not own; 08-14's rider booking a computed exit
    price 0.75pt off the fill). [[ibkr-is-truth-never-trust-our-books]] is only enforceable if
    something actually checks.

    WARN, never CRIT — deliberately, and for the same reason `check_config_committed` is a WARN: a
    recording fault is not an order-path fault. Nothing is naked and no position is at risk; the
    P&L we reason from is wrong, which is serious for DECISIONS and not for SAFETY.

    Unverifiable desk-days (no execution record, or a position carried across the boundary) are
    reported but never scored as faults — and never as clean either.
    """
    from gazbot7.bookrecon import reconcile
    try:
        trades = store.execute(
            "SELECT date(closed_at), gate, pnl_usd, data_quality FROM trades "
            "WHERE closed_at >= date('now', ?)", (f"-{days} day",)).fetchall()
        fills = store.execute(
            "SELECT date(exec_time), order_id, side, qty, price FROM fills "
            "WHERE exec_time >= date('now', ?)", (f"-{days} day",)).fetchall()
    except Exception as e:
        # A check that cannot run must SAY SO, not return OK.
        return {"status": WARN, "detail": f"could not read the ledger/fills: {e}"}

    verdicts = reconcile([tuple(r) for r in trades], [tuple(r) for r in fills])
    faults = [v for v in verdicts if v.is_fault]
    unver = [v for v in verdicts if v.is_unverifiable]
    status = WARN if faults else OK
    if faults:
        detail = "; ".join(f"{v.day} {v.desk} book vs venue {v.divergence:+,.2f}" for v in faults[:4])
    else:
        detail = f"{len(verdicts) - len(unver)} desk-day(s) reconcile exactly"
        if unver:
            detail += f" · {len(unver)} unverifiable ({unver[0].status.lower()}) — not the same as clean"
    return {"status": status, "detail": detail,
            "days": days,
            "faults": [{"day": v.day, "desk": v.desk, "booked": v.booked, "venue": v.venue,
                        "divergence": v.divergence} for v in faults],
            "unverifiable": [{"day": v.day, "desk": v.desk, "why": v.status} for v in unver]}


# ★2026-08-18 how far OUTSIDE the visible 10-deep ladder a fill must land before it is a finding,
# and how much timestamp slop to allow when matching a fill to a book snapshot.
_FILL_BOOK_TOL_PT = 2.0
# ⚠ 2s, because the DAY RIDER'S OWN FILLS CARRY SECOND-ROUNDED exec_time while the tournament's
# carry microseconds. Matching a second-rounded stamp to a 250ms snapshot needs slop, and the slop
# must be spent making the check HARDER to trip, never easier — see the max()/min() below.
_FILL_BOOK_WINDOW_MS = 2000


def check_fill_vs_book(store, now: datetime, *, hours: int = 24,
                       depth_path: str = DEPTH_PATH) -> dict:
    """Did any fill land OUTSIDE the whole visible order book?

    ★★2026-08-18. The day rider's TRAIL exit filled two lots at 29579.50 and 29609.00 — 29.5pt
    apart — while the L2 ladder showed best ask 29580.50 with 3 lots and the DEEPEST of ten levels
    at 29582.75. A 2-lot buy cannot walk to 29609; that is ~$57 on one lot, and the operator found
    it by watching the screen. `book_vs_fills` could never catch it: the book and the venue AGREE
    here — we booked exactly the bad price we got. Agreement is not quality.

    ⚠ CONSERVATIVE BY CONSTRUCTION — it must not cry wolf on a shared alarm channel. A fill is only
    flagged if it sits beyond the deepest visible level in EVERY snapshot in its window: for a BUY,
    `price > max(ask10p)`; for a SELL, `price < min(bid10p)`. Timestamp slop therefore makes the
    test stricter, never looser, so a mis-stamped fill cannot manufacture a finding.

    ⚠ MULTI-SYMBOL. depth_snap carries MNQ and MGC; every read filters `symbol`
    ([[md-stream-multi-symbol-filter]] — folding MGC into MNQ once put ATR at 1848 against a true 15).

    ⚠ NO BOOK IS NOT CLEAN. depth capture starts 2026-07-21 and covers MNQ/MGC only, so older or
    other-symbol fills are UNVERIFIABLE and reported as such — the `book_vs_fills` precedent.

    WARN, never CRIT: this is execution QUALITY. Nothing is naked and no position is at risk.

    ⚠ UNVERIFIABLE ALSO WARNS, which is stricter than `book_vs_fills` (where it only annotates).
    Deliberate: that check looks back DAYS and legitimately meets old days with no execution record,
    whereas this one looks back 24h, so a fill with no book snapshot means depth capture DIED inside
    the last day. "I could not check this" must not render as a green light — that is the desk's
    single most repeated failure ([[an-instrument-that-reports-healthy-about-something-it-does-not-check]]).
    """
    since = (now - timedelta(hours=hours)).isoformat()
    try:
        fills = store.execute(
            "SELECT exec_id, order_id, symbol, side, qty, price, exec_time FROM fills "
            "WHERE exec_time >= ? ORDER BY exec_time", (since,)).fetchall()
    except Exception as e:
        return {"status": WARN, "detail": f"could not read fills: {e}"}
    if not fills:
        return {"status": OK, "detail": f"no fills in {hours}h", "checked": 0}
    if not os.path.exists(depth_path):
        return {"status": WARN, "checked": 0,
                "detail": f"{len(fills)} fill(s) UNVERIFIABLE — no depth.db at {depth_path}"}
    findings, unver = [], 0
    d = sqlite3.connect(f"file:{depth_path}?mode=ro", uri=True)
    try:
        for exec_id, order_id, sym, side, qty, price, ts in fills:
            try:
                t_ms = int(datetime.fromisoformat(ts).timestamp() * 1000)
            except Exception:
                unver += 1
                continue
            row = d.execute(
                "SELECT MAX(ask10p), MIN(bid10p), MIN(ask1p), MAX(bid1p), COUNT(*) FROM depth_snap "
                "WHERE symbol=? AND ts_ms BETWEEN ? AND ?",
                (sym, t_ms - _FILL_BOOK_WINDOW_MS, t_ms + _FILL_BOOK_WINDOW_MS)).fetchone()
            if not row or not row[4] or row[0] is None or row[1] is None:
                unver += 1
                continue
            worst_ask, worst_bid, best_ask, best_bid = row[0], row[1], row[2], row[3]
            if side == "BUY":
                excess = float(price) - float(worst_ask)
                ref = worst_ask
            else:
                excess = float(worst_bid) - float(price)
                ref = worst_bid
            if excess > _FILL_BOOK_TOL_PT:
                vpp = 2.0 if sym == "MNQ" else (10.0 if sym == "MGC" else 2.0)
                findings.append({"exec_id": exec_id, "order_id": order_id, "symbol": sym,
                                 "side": side, "qty": float(qty), "price": float(price),
                                 "deepest_visible": float(ref), "excess_pt": round(excess, 2),
                                 "est_cost_usd": round(excess * float(qty) * vpp, 2),
                                 "inside_touch": float(best_ask if side == "BUY" else best_bid),
                                 "at": ts})
    finally:
        d.close()
    checked = len(fills) - unver
    if findings:
        w = max(findings, key=lambda f: f["excess_pt"])
        detail = (f"{len(findings)} of {checked} fill(s) landed OUTSIDE the visible book — worst "
                  f"{w['order_id']} {w['side']} {w['qty']:g} @ {w['price']:.2f} vs deepest "
                  f"{w['deepest_visible']:.2f} ({w['excess_pt']:+.2f}pt, ~${w['est_cost_usd']:.0f})")
        status = WARN
    else:
        detail = f"{checked} fill(s) all inside the visible book"
        status = OK
    if unver:
        status = _worst(status, WARN)
        detail += (f" · {unver} UNVERIFIABLE (no book snapshot in ±"
                   f"{_FILL_BOOK_WINDOW_MS}ms) — not the same as clean; is depth capture alive?")
    return {"status": status, "detail": detail, "checked": checked,
            "unverifiable": unver, "findings": findings[:8]}


def check_shadow_arms(cfg: RunConfig, now: datetime) -> dict:
    """An ARMED shadow slate that recorded NOTHING through a session the tape ran is a finding.

    ★★★2026-08-18. `gazbot7-shadow-mgc` recorded ZERO sims for three days. The service was `active`
    with NRestarts=0, burning 1h45m of CPU, logging nothing and raising nothing; the feed was
    delivering MGC bars at the correct cadence; and the gate replayed 459 fires on the same week of
    tape. It stepped the sim zero times because the step was gated on the bar COUNT growing, and the
    ring is a pre-warmed fixed-size deque. Nothing noticed for three days — and `check_shadow`
    reported OK the whole time, because it counts sims in the MNQ store and gold has its OWN store
    that nothing looked at ([[an-instrument-that-reports-healthy-about-something-it-does-not-check]]).

    ⚠ ONLY JUDGED ON A DAY THE TAPE ACTUALLY RAN. A weekend, a holiday or a feed outage legitimately
    produces zero sims, and alarming then is how a channel gets ignored. No bars for that symbol in
    the window → SKIPPED and reported as such, never scored clean and never scored a fault.

    ⚠ It deliberately judges the SLATE, not the arm. Individual arms are legitimately slow-firing
    (a level_break gate can go days), and per-arm silence is the classify-before-ranking problem, not
    an alarm. A whole armed slate silent for a session is a mechanism failure.
    """
    day_end = pnl.paris_day_start_utc(now)
    day_start = pnl.paris_day_start_utc(datetime.fromisoformat(day_end) - timedelta(seconds=1))
    try:
        from gazbot7.shadow import default_slate, mgc_slate
    except Exception as e:
        return {"status": WARN, "detail": f"cannot load the slates: {e}"}
    books = [("MNQ shadow", cfg.shadow_store_path, len(default_slate()), cfg.symbol),
             ("MGC shadow", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                         "data", "shadow_mgc.db"), len(mgc_slate()), "MGC")]
    rows, faults, skipped = [], [], []
    for label, path, armed, sym in books:
        if not armed:
            continue
        if not os.path.exists(path):
            skipped.append(f"{label} (no store)")
            continue
        try:
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            n = c.execute("SELECT COUNT(*) FROM shadow_trades WHERE entry_ts>=? AND entry_ts<?",
                          (int(datetime.fromisoformat(day_start).timestamp()),
                           int(datetime.fromisoformat(day_end).timestamp()))).fetchone()[0]
            c.close()
        except Exception as e:
            skipped.append(f"{label} (unreadable: {str(e)[:40]})")
            continue
        # did the tape even run for this symbol that session?
        try:
            cap = sqlite3.connect(f"file:{cfg.capture_path}?mode=ro", uri=True)
            bars = cap.execute("SELECT COUNT(*) FROM bars WHERE symbol=? AND bar_ts>=? AND bar_ts<?",
                               (sym, int(datetime.fromisoformat(day_start).timestamp()),
                                int(datetime.fromisoformat(day_end).timestamp()))).fetchone()[0]
            cap.close()
        except Exception:
            bars = 0
        rows.append({"book": label, "armed": armed, "sims": n, "tape_bars": bars})
        if bars < 500:
            skipped.append(f"{label} (tape did not run: {bars} bars)")
        elif n == 0:
            faults.append(f"{label}: {armed} arms ARMED, {n} sims on a session with {bars:,} bars "
                          f"— the slate is not firing at all")
    if faults:
        return {"status": WARN, "detail": " · ".join(faults), "books": rows, "skipped": skipped}
    live = "; ".join(f"{r['book']} {r['sims']} sims/{r['armed']} arms" for r in rows) or "none"
    detail = f"session {day_start[:10]}: {live}"
    if skipped:
        detail += f" · SKIPPED {', '.join(skipped)} — not the same as clean"
    return {"status": OK, "detail": detail, "books": rows, "skipped": skipped}


def check_recording(cfg: RunConfig, store, now: datetime) -> dict:
    since_iso = pnl.paris_day_start_utc(now)
    n = store.execute("SELECT count(*) FROM trades WHERE symbol=? AND closed_at>=?",
                      (cfg.symbol, since_iso)).fetchone()[0]
    # V7 has NO backfill path (D3) — any reconstructed row is an anomaly worth a look
    anomalous = store.execute(
        "SELECT count(*) FROM trades WHERE closed_at>=? AND exit_reason LIKE '%RECONSTRUCT%'",
        (since_iso,)).fetchone()[0]
    if anomalous:
        return {"status": WARN, "detail": f"{anomalous} reconstructed/backfill rows today "
                "(V7 has no backfill path — investigate)", "today_trades": n}
    return {"status": OK, "detail": f"{n} trades today, all real-time (no backfill)",
            "today_trades": n}


def check_shadow(cfg: RunConfig, now: datetime) -> dict:
    try:
        sh = _conn(cfg.shadow_store_path)
        total = sh.execute("SELECT count(*) FROM shadow_trades").fetchone()[0]
        scored = sh.execute("SELECT count(*) FROM shadow_real").fetchone()[0]
        last = sh.execute("SELECT max(exit_ts) FROM shadow_trades").fetchone()[0]
        sh.close()
    except Exception as e:
        return {"status": WARN, "detail": f"shadow read error: {e}"}
    unscored = total - scored
    last_age = (now.timestamp() - last) if last else None
    status, notes = OK, []
    if unscored > 20:  # repricer falling behind → the honest number stops updating
        status = WARN
        notes.append(f"{unscored} unscored (repricer behind)")
    age_str = f"{last_age/60:.0f}m" if last_age is not None else "n/a"
    detail = f"{total} sims, {scored} scored, last {age_str} ago" if status == OK else "; ".join(notes)
    return {"status": status, "detail": detail, "total": total, "scored": scored, "unscored": unscored}


def check_storage(cfg: RunConfig) -> dict:
    status, notes, sizes = OK, [], {}
    for label, path in [("live", cfg.store_path), ("capture", cfg.capture_path),
                        ("shadow", cfg.shadow_store_path)]:
        for suffix in ("", "-wal"):
            p = path + suffix
            if os.path.exists(p):
                mb = os.path.getsize(p) / 1e6
                sizes[label + suffix] = round(mb, 1)
                if suffix == "-wal" and mb > 500:
                    status = _worst(status, WARN)
                    notes.append(f"{label} WAL {mb:.0f}MB (checkpoint stalled?)")
    try:
        du = shutil.disk_usage(os.path.dirname(os.path.abspath(cfg.store_path)))
        pct = du.used / du.total * 100
        sizes["disk_pct"] = round(pct, 1)
        if pct > 85:
            status = _worst(status, WARN)
            notes.append(f"disk {pct:.0f}% full")
    except Exception:
        pass
    detail = f"dbs {sizes} — OK" if status == OK else "; ".join(notes)
    return {"status": status, "detail": detail, "sizes": sizes}


# ── driver ──────────────────────────────────────────────────────────────────
_LIVE_BEHAVIOUR_PATHS = (
    "data/exit_overrides.json",       # the exit ladder — untracked once, and 07-31→08-02 is gone
    "src/gazbot7/deciders.py",        # ATR/ER floors, ceilings, bands
    "src/gazbot7/slot_strategy.py",   # the slate: gates, entry params, sizing
    "src/gazbot7/multislot_core.py",  # the order path and every safety branch
)
# ★2026-08-16 how long a local-only commit may sit before it is a finding. A commit-then-push in the
# same breath is the desk's normal flow, so anything still unpushed a DAY later was not "in progress".
_UNPUSHED_GRACE_H = 24.0


def _ahead_of_remote(repo: str) -> dict:
    """★2026-08-16 Commits made HERE that were never pushed. **Deliberately makes no network call.**

    Found the hard way: `refactor/three-service` was **207 commits / 18 days** ahead of origin — the
    router being made permanent, the 08-06 shared-account fixes, the whole 08-13 "the books lied"
    order-path rework and DECISION §362 existed on this box ONLY. B2 backs up `gazbot7.db`,
    `shadow.db` and configs; it does not back up the source tree. On a 7.5GB box with three logged
    OOM kills, that is the entire desk one disk away from gone. `check_config_committed` read OK
    green throughout, because it asked "is it committed?" and never "did it leave the building?"
    ([[an-instrument-that-reports-healthy-about-something-it-does-not-check]]).

    `@{u}` is the LOCAL remote-tracking ref, which git advances on a successful push — so this
    measures "committed on this box, never pushed from it" with no fetch. A network call in a check
    that runs 8x/day is a hang risk, and the failure being guarded is local by construction.
    ⚠ It cannot see a push made from ANOTHER machine (the ref would be stale). On a single-box desk
    that can only over-report, never under-report — the safe direction for an alarm to be wrong in.
    """
    def _git(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, timeout=10)
    up = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if up.returncode != 0:
        br = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "?"
        # No upstream is WORSE than being ahead, not better: nothing on this branch can ever leave.
        return {"ahead": None, "upstream": None,
                "detail": f"branch '{br}' has NO UPSTREAM — nothing committed here can be pushed"}
    upstream = up.stdout.strip()
    rev = _git("rev-list", "--count", "@{u}..HEAD")
    if rev.returncode != 0:
        return {"ahead": None, "upstream": upstream,
                "detail": f"ahead-count failed: {rev.stderr.strip()[:100]}"}
    ahead = int(rev.stdout.strip() or 0)
    if ahead == 0:
        return {"ahead": 0, "upstream": upstream, "oldest_h": 0.0}
    # Age of the OLDEST unpushed commit. The NEWEST would reset the clock on every commit, so the
    # alarm would never fire on a branch worked on daily — which is exactly this branch.
    # ⚠ min(), NOT the last line of `git log`. Log order is the DAG, and commit dates are not
    # monotonic along it: one rebase, cherry-pick or amended date puts an old commit on top of a new
    # one and the last line is then not the oldest. Caught by the 18-day fixture, which read 2.0h.
    stamps = [int(s) for s in _git("log", "--format=%ct", "@{u}..HEAD").stdout.split()]
    oldest_h = ((datetime.now(UTC).timestamp() - min(stamps)) / 3600.0) if stamps else 0.0
    return {"ahead": ahead, "upstream": upstream, "oldest_h": round(oldest_h, 1)}


def check_config_committed(repo: str = "/home/alphabot/gazbot7") -> dict:
    """★2026-08-08 (SATURDAY #7). Uncommitted live behaviour is now a finding, not a silent note.

    `config_journal.jsonl` has stamped `exit_overrides_uncommitted: true` at every startup since
    08-04 and NOTHING consumed it, while five live behaviours existed only as working-tree edits.
    An uncommitted change cannot be diffed, reverted or attributed — exactly what made the
    07-31→08-02 exit ladder unrecoverable, which is the incident the journal was built for.

    WARN, not CRIT, deliberately: a dirty tree is a bookkeeping failure, not an order-path failure,
    and a CRIT here would train the operator to ignore a red sweep on a desk that is trading fine
    ([[pipeline-health-monitor-the-mechanism]] — every alarm must mean something).
    """
    try:
        out = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain", "--", *_LIVE_BEHAVIOUR_PATHS],
            capture_output=True, text=True, timeout=10)
        head = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "?"
        if out.returncode != 0:
            return {"status": WARN, "dirty": None,
                    "detail": f"git status failed: {out.stderr.strip()[:120]}"}
        dirty = [ln[3:].strip() for ln in out.stdout.splitlines() if ln.strip()]

        # ★2026-08-16 committed is only half of safe — see _ahead_of_remote.
        push = _ahead_of_remote(repo)
        n, age = push.get("ahead"), push.get("oldest_h") or 0.0
        if n is None:
            push_bad = push.get("detail", "push state unknown")
        elif n and age >= _UNPUSHED_GRACE_H:
            push_bad = (f"{n} commit(s) COMMITTED BUT NEVER PUSHED to {push['upstream']}, oldest "
                        f"{age / 24:.1f}d — this box is the only copy of them")
        else:
            push_bad = None

        base = {"dirty": dirty, "head": head, "ahead_of_remote": n,
                "upstream": push.get("upstream"), "unpushed_oldest_h": push.get("oldest_h")}
        notes = []
        if dirty:
            notes.append(f"{len(dirty)} live-behaviour file(s) UNCOMMITTED @ {head}: "
                         f"{', '.join(dirty)} — cannot be diffed, reverted or attributed")
        if push_bad:
            notes.append(push_bad)
        if notes:
            return {**base, "status": WARN, "detail": " · ".join(notes)}
        # The green light now asserts BOTH, and says so — a health line that names only what it
        # checked is how "all committed" read as safe for 18 days.
        pushed = f"pushed @ {head}" if n == 0 else f"{n} unpushed (<{_UNPUSHED_GRACE_H:.0f}h, ok)"
        return {**base, "status": OK,
                "detail": f"live-behaviour files all committed · {pushed}"}
    except Exception as e:
        return {"status": WARN, "dirty": None, "ahead_of_remote": None,
                "detail": f"config-committed check failed: {e}"}


def run_sweep(cfg: RunConfig | None = None, now: datetime | None = None) -> dict:
    cfg = cfg or RunConfig()
    now = now or datetime.now(UTC)
    store = _conn(cfg.store_path)
    try:
        services = check_services()
        core = check_core(cfg, now)
        sections = {
            "services": services,
            "core": core,
            "capture": check_capture(cfg, now),
            "execution": check_execution(store, now),
            "position": check_position(store, core, cfg, now),
            "killswitch": check_killswitch(cfg, store, core, now),
            "recording": check_recording(cfg, store, now),
            "book_vs_fills": check_book_vs_fills(store, now),
            "fill_vs_book": check_fill_vs_book(store, now),
            "shadow_arms": check_shadow_arms(cfg, now),
            "shadow": check_shadow(cfg, now),
            "storage": check_storage(cfg),
            "config": check_config_committed(),
        }
    finally:
        store.close()
    overall = _worst(*(s["status"] for s in sections.values()))
    return {"ts": now.isoformat(), "overall": overall,
            "preflight_ok": bool(core.get("preflight_ok")), "sections": sections}


def _render(report: dict) -> str:
    lines = [f"GAZBOT V7 sweep — {report['overall']}  (preflight {'OK' if report['preflight_ok'] else 'FAIL'})",
             f"  {report['ts']}"]
    for name, s in report["sections"].items():
        mark = {"OK": "✓", "WARN": "▲", "CRIT": "✗"}.get(s["status"], "?")
        lines.append(f"  {mark} {name:<11} {s['detail']}")
    return "\n".join(lines)


def main() -> int:
    report = run_sweep()
    if "--json" in sys.argv:
        print(json.dumps(report))
    else:
        print(_render(report))
        print("\nJSON " + json.dumps(report))
    # exit code mirrors severity so a cron can branch on it too (0 OK, 1 WARN, 2 CRIT)
    return _RANK.get(report["overall"], 0)


if __name__ == "__main__":
    raise SystemExit(main())
