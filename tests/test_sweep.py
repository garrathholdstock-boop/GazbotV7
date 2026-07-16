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
    cfg = RunConfig()
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


def test_position_flat_agreement_is_ok():
    store = open_store(":memory:")
    r = sweep.check_position(store, {"flat": True})
    assert r["status"] == "OK"


def test_position_drift_when_core_flat_but_store_holds():
    store = open_store(":memory:")
    store.execute(
        "INSERT INTO open_position (symbol, side, qty, entry_price, entry_atr, opened_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)", ("MNQ", "LONG", 1, 100.0, 2.0, NOW.isoformat(), NOW.isoformat()))
    store.commit()
    r = sweep.check_position(store, {"flat": True})
    assert r["status"] == "WARN"
    assert "drift" in r["detail"]


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
    assert set(report["sections"]) == {
        "services", "core", "capture", "execution", "position",
        "killswitch", "recording", "shadow", "storage"}
    assert report["overall"] in ("OK", "WARN", "CRIT")
    assert report["preflight_ok"] is False  # no core_health.json in tmp_path
