"""The V7 maintenance-sweep collector — the store-driven classifiers.

The systemctl/file-reading sections (services, core) are thin I/O shells tested
live; here we pin the logic that turns DB truth into a health verdict."""

from __future__ import annotations

from datetime import UTC, datetime

from gazbot7.config import RunConfig
from gazbot7.store import open_store

import scripts.sweep as sweep


NOW = datetime(2026, 7, 16, 16, 0, tzinfo=UTC)


def _seed_trade(store, pnl, *, reason="ABSORPTION_CUT", closed=None, symbol="MNQ"):
    store.execute(
        "INSERT INTO trades (symbol, side, qty, entry_price, exit_price, opened_at, "
        "closed_at, pnl_usd, fees_usd, exit_reason, gate) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (symbol, "LONG", 1, 100.0, 100.0, closed or NOW.isoformat(),
         closed or NOW.isoformat(), pnl, 1.5, reason, "thrust"),
    )
    store.commit()


def test_worst_ranks_crit_over_warn_over_ok():
    assert sweep._worst("OK", "WARN", "OK") == "WARN"
    assert sweep._worst("OK", "WARN", "CRIT") == "CRIT"
    assert sweep._worst() == "OK"


def test_killswitch_flags_four_loss_streak():
    cfg = RunConfig(loss_streak_halt=4)  # explicit — the live default is 0 (off, paper tuning)
    store = open_store(":memory:")
    for _ in range(4):
        _seed_trade(store, -6.0)
    r = sweep.check_killswitch(cfg, store, {"halted": False}, NOW)
    assert r["status"] == "WARN"
    assert r["loss_streak"] == 4
    assert "loss streak" in r["detail"]


def test_killswitch_ok_when_streak_broken_by_a_win():
    cfg = RunConfig()
    store = open_store(":memory:")
    _seed_trade(store, -6.0)
    _seed_trade(store, -6.0)
    _seed_trade(store, +10.0)  # most recent is a win → streak 0
    r = sweep.check_killswitch(cfg, store, {"halted": False}, NOW)
    assert r["status"] == "OK"
    assert r["loss_streak"] == 0


def test_killswitch_excludes_cleanup_from_streak():
    cfg = RunConfig()
    store = open_store(":memory:")
    for _ in range(3):
        _seed_trade(store, -6.0)
    _seed_trade(store, -449.0, reason="ADOPT_FLATTEN")  # the orphan cleanup — must NOT count
    r = sweep.check_killswitch(cfg, store, {"halted": False}, NOW)
    assert r["loss_streak"] == 3          # cleanup skipped, only 3 real losers
    assert r["status"] == "OK"            # 3 < halt threshold 4
    assert r["day_pnl"] == -18.0          # cleanup excluded from day P&L too


def test_killswitch_flags_daily_loss_cap():
    cfg = RunConfig(max_daily_loss_usd=20.0, loss_streak_halt=0)
    store = open_store(":memory:")
    _seed_trade(store, -25.0)
    r = sweep.check_killswitch(cfg, store, {"halted": False}, NOW)
    assert r["status"] == "WARN"
    assert "cap" in r["detail"]


def test_recording_flags_backfill_anomaly():
    cfg = RunConfig()
    store = open_store(":memory:")
    _seed_trade(store, -6.0, reason="RECONSTRUCTED_BACKFILL")
    r = sweep.check_recording(cfg, store, NOW)
    assert r["status"] == "WARN"
    assert "backfill" in r["detail"].lower()


def test_recording_ok_for_realtime_rows():
    cfg = RunConfig()
    store = open_store(":memory:")
    _seed_trade(store, -6.0)
    _seed_trade(store, +4.0)
    r = sweep.check_recording(cfg, store, NOW)
    assert r["status"] == "OK"
    assert r["today_trades"] == 2


def _fake_svc(active_set):
    def _svc(n):
        on = n in active_set
        return {"active": on, "state": "active" if on else "inactive", "restarts": 0}
    return _svc


def test_services_tournament_is_the_desk_core_strategy_inactive_ok(monkeypatch):
    # THE cutover fix: core/strategy intentionally inactive is NOT a fault when tournament runs
    active = {"gazbot7-md", "alphabot-gateway", "gazbot7-tournament", "gazbot7-shadow", "gazbot7-web",
              "gazbot7-depth-capture"}
    monkeypatch.setattr(sweep, "_svc", _fake_svc(active))
    r = sweep.check_services()
    assert r["status"] == "OK" and "tournament" in r["detail"]


def test_depth_capture_down_is_WARN_never_CRIT(monkeypatch):
    """★2026-08-04 pins the SEVERITY of the new L2 capture, because getting this wrong cuts both ways.
    The desk trades fine without depth (no gate reads it yet), so a dead capturer must never CRIT and
    page as if the order path were down. But it must not be silent either — it ran three weeks in the
    retired V5 tree where nothing swept it, and a silent death would have quietly stopped the 20-day
    book history every L2 study depends on."""
    active = {"gazbot7-md", "alphabot-gateway", "gazbot7-tournament", "gazbot7-shadow", "gazbot7-web"}
    monkeypatch.setattr(sweep, "_svc", _fake_svc(active))   # depth-capture absent
    r = sweep.check_services()
    assert r["status"] == "WARN", "depth capture down must WARN, not CRIT (desk trades without it)"
    assert "gazbot7-depth-capture" in r["detail"], "…but it must be NAMED, not silently tolerated"


def test_services_crit_when_no_desk_at_all(monkeypatch):
    monkeypatch.setattr(sweep, "_svc", _fake_svc({"gazbot7-md", "alphabot-gateway"}))  # infra up, no desk
    r = sweep.check_services()
    assert r["status"] == "CRIT" and "NO DESK" in r["detail"]


def test_services_ok_on_reverted_legacy_desk(monkeypatch):
    # a revert: tournament down but core+strategy up → still a valid desk
    active = {"gazbot7-md", "alphabot-gateway", "gazbot7-core", "gazbot7-strategy", "gazbot7-shadow",
              "gazbot7-web", "gazbot7-depth-capture"}
    monkeypatch.setattr(sweep, "_svc", _fake_svc(active))
    r = sweep.check_services()
    assert r["status"] == "OK" and "reverted" in r["detail"]


def test_position_flat_is_ok():
    store = open_store(":memory:")
    r = sweep.check_position(store, {"flat": True})
    assert r["status"] == "OK"


def test_position_held_and_protected_is_ok():
    # tournament shape: per-slot protection with a live stop_coid
    store = open_store(":memory:")
    core = {"flat": False, "protection": {"held": True, "unverified_cycles": 0,
            "slots": [{"gate": "grind_long", "side": "LONG", "qty": 1, "stop_coid": "stp-1"}]}}
    r = sweep.check_position(store, core)
    assert r["status"] == "OK" and r["held"] is True


def test_position_naked_slot_is_crit():
    store = open_store(":memory:")
    core = {"flat": False, "protection": {"held": True, "unverified_cycles": 0,
            "slots": [{"gate": "grind_long", "side": "LONG", "qty": 1, "stop_coid": None}]}}
    r = sweep.check_position(store, core)
    assert r["status"] == "CRIT" and "NAKED" in r["detail"]


def test_position_unverified_is_crit():
    store = open_store(":memory:")
    core = {"flat": False, "protection": {"held": True, "unverified_cycles": 3, "slots": []}}
    r = sweep.check_position(store, core)
    assert r["status"] == "CRIT" and "UNVERIFIABLE" in r["detail"]


def _write_health(tmp_path, **over):
    import json
    from dataclasses import replace
    h = {"ts": NOW.isoformat(), "conn": "HEALTHY", "healthy": True, "place_live": True,
         "flat": True, "halted": False,
         "protection": {"held": False, "slots": [], "unverified_cycles": 0}, "audit_age_s": 2.0}
    h.update(over)
    (tmp_path / "core_health.json").write_text(json.dumps(h))
    return replace(RunConfig(), store_path=str(tmp_path / "live.db"))


def test_core_crit_on_stale_audit_loop(tmp_path):
    # 2026-07-22 hardening: a dead safety loop (max-hold/stop-breach) while the heartbeat stays green
    cfg = _write_health(tmp_path, audit_age_s=120.0)
    r = sweep.check_core(cfg, NOW)
    assert r["status"] == "CRIT" and "AUDIT LOOP STALE" in r["detail"]
    assert r["preflight_ok"] is False


def test_core_ok_with_fresh_audit_loop(tmp_path):
    cfg = _write_health(tmp_path, audit_age_s=3.0)
    r = sweep.check_core(cfg, NOW)
    assert r["status"] == "OK" and r["preflight_ok"] is True


def test_core_audit_none_does_not_crit(tmp_path):
    # a dry / pre-start desk (loop hasn't run → audit_age None) must NOT false-CRIT
    cfg = _write_health(tmp_path, audit_age_s=None, place_live=False)
    r = sweep.check_core(cfg, NOW)
    assert r["status"] == "OK"


def test_run_sweep_smoke_produces_all_sections(tmp_path):
    # a fully isolated desk: empty stores, no core_health file → core CRIT, but
    # the driver must still return every section and a coherent overall verdict.
    cfg = RunConfig(
        store_path=str(tmp_path / "live.db"),
        capture_path=str(tmp_path / "capture.db"),
        shadow_store_path=str(tmp_path / "shadow.db"),
    )
    open_store(cfg.store_path).close()
    from gazbot7.capture import open_capture
    open_capture(cfg.capture_path).close()
    open_store(cfg.shadow_store_path).close()
    report = sweep.run_sweep(cfg, NOW)
    # ★2026-08-08 + "config" (SATURDAY #7): uncommitted live-behaviour files are now a finding.
    assert set(report["sections"]) == {
        "services", "core", "capture", "execution", "position",
        "killswitch", "recording", "shadow", "storage", "config"}
    assert report["overall"] in ("OK", "WARN", "CRIT")
    assert report["preflight_ok"] is False  # no core_health.json in tmp_path
