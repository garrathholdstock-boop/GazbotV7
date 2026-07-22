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
from datetime import UTC, datetime

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
_SOFT_SERVICES = ("gazbot7-shadow", "gazbot7-web")
_RESTART_STORM = 3   # NRestarts >= this since boot = flapping


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
    storms = [f"{n}×{svc[n]['restarts']}" for n in watched if svc[n]["restarts"] >= _RESTART_STORM]
    if storms:
        status = _worst(status, WARN)
        notes.append("restart-storm: " + ",".join(storms))
    desk = _DESK_PRIMARY if svc[_DESK_PRIMARY]["active"] else ("core+strategy (reverted)" if desk_up else "NONE")
    detail = f"all up · desk={desk}" if status == OK else "; ".join(notes)
    return {"status": status, "detail": detail, "restarts": {n: v["restarts"] for n, v in svc.items()}}


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
    detail = f"capture OK (5s {bar_age:.0f}s, tick {tick_age:.0f}s)" if status == OK else "; ".join(notes)
    return {"status": status, "detail": detail, "bar_age": round(bar_age, 1),
            "tick_age": round(tick_age, 1), "market_open": market_open}


def check_execution(store, now: datetime) -> dict:
    since = (now.timestamp() - 1800)
    since_iso = datetime.fromtimestamp(since, UTC).isoformat()
    v = monitor.execution_health(store, since_iso=since_iso)
    return {"status": v.status, "detail": v.detail,
            "submitted": v.submitted, "fills": v.fills, "rejects": v.rejects}


def check_position(store, core: dict) -> dict:
    """VENUE-TRUTH protection gate, read from core's freshly-written ``protection`` block
    (2026-07-17 lesson: 'held' is not 'protected' — a stop-less position bled for 3h reading
    OK). Multi-slot tournament: ``protection.slots`` each carry a ``stop_coid`` (a live venue
    order) — a held slot without one is NAKED. Also handles the retired single-position shape
    (``protection.verified``) for a revert. Reads core-health only — NOT the ``open_position``
    table (the tournament's truth is per-slot, so that table is empty here by design)."""
    flat = bool(core.get("flat", True))
    prot = core.get("protection") if isinstance(core.get("protection"), dict) else {}
    slots = prot.get("slots") or []
    held = (not flat) or bool(slots) or bool(prot.get("held"))
    if not held:
        return {"status": OK, "detail": "flat"}
    # held → gate on protection. 'can't verify' is never 'safe'.
    unver = prot.get("unverified_cycles") or 0
    if unver:
        return {"status": CRIT, "held": True,
                "detail": f"held but venue snapshot UNVERIFIABLE {unver} cycles — CHECK IBKR / flatten"}
    if prot.get("verified") is False:              # single-position shape (reverted desk)
        return {"status": CRIT, "held": True,
                "detail": "held but protection NOT verified — CHECK IBKR / flatten"}
    naked = [str(s.get("gate")) for s in slots if not s.get("stop_coid")]   # tournament per-slot
    if naked:
        return {"status": CRIT, "held": True,
                "detail": f"NAKED slot(s) {', '.join(naked)} — no stop resting; CHECK IBKR / flatten"}
    if slots:
        desc = ", ".join(f"{s.get('gate')} {s.get('side')} {s.get('qty'):g}" for s in slots)
        return {"status": OK, "held": True, "detail": f"holding {len(slots)} slot(s): {desc} — all protected"}
    return {"status": OK, "held": True, "detail": "holding — protected"}


def check_killswitch(cfg: RunConfig, store, core: dict, now: datetime) -> dict:
    day_pnl, day_n, day_w = pnl.day(store, cfg.symbol, now)
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
    return {"status": status, "detail": detail, "day_pnl": day_pnl, "day_trades": day_n,
            "day_wins": day_w, "loss_streak": streak}


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
            "position": check_position(store, core),
            "killswitch": check_killswitch(cfg, store, core, now),
            "recording": check_recording(cfg, store, now),
            "shadow": check_shadow(cfg, now),
            "storage": check_storage(cfg),
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
