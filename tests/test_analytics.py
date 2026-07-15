"""D9 — DuckDB analytics layer: shadow summary + cross-DB (V7 + archive) attach."""

from __future__ import annotations

from gazbot7.analytics import desk_pnl_by_day, open_analytics, shadow_summary
from gazbot7.store import (
    open_store,
    record_shadow_real,
    record_shadow_trade,
    record_trade,
)


def _checkpoint(store):
    store.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    store.commit()


def test_shadow_summary_over_real_pnl(tmp_path):
    p = tmp_path / "v7.db"
    store = open_store(p)
    tid = record_shadow_trade(
        store, strategy="rg_short_050", symbol="MNQ", side="SHORT", qty=1,
        entry_ts=1, entry_price=100, entry_atr=4, target_r=2, stop_atr_mult=1,
        exit_ts=2, exit_price=92, exit_reason="TARGET", ceiling_pnl=16.0,
    )
    record_shadow_real(store, trade_id=tid, strategy="rg_short_050", symbol="MNQ",
                       real_pnl=14.5, fill_status="filled", repriced_at="now")
    _checkpoint(store)
    con = open_analytics(p)
    rows = shadow_summary(con)
    assert len(rows) == 1
    assert rows[0][0] == "rg_short_050" and rows[0][2] == 14.5  # scored on real_pnl, not ceiling


def test_desk_pnl_by_day(tmp_path):
    p = tmp_path / "v7.db"
    store = open_store(p)
    record_trade(store, symbol="MNQ", side="LONG", qty=1, entry_price=100, exit_price=105,
                 opened_at="2026-07-15T13:00:00+00:00", closed_at="2026-07-15T13:05:00+00:00",
                 pnl_usd=8.5, fees_usd=1.5, exit_reason="TARGET", exit_exec_id="x1")
    _checkpoint(store)
    con = open_analytics(p)
    (row,) = desk_pnl_by_day(con)
    assert row[0] == "2026-07-15" and row[2] == 8.5


def test_cross_db_archive_attach(tmp_path):
    # V7 present + a frozen archive attached read-only in one session
    v7 = tmp_path / "v7.db"
    archive = tmp_path / "archive.db"
    s7 = open_store(v7)
    sa = open_store(archive)
    record_trade(sa, symbol="MNQ", side="SHORT", qty=1, entry_price=100, exit_price=95,
                 opened_at="2026-06-01T10:00:00+00:00", closed_at="2026-06-01T10:02:00+00:00",
                 pnl_usd=8.5, fees_usd=1.5, exit_reason="TARGET", exit_exec_id="a1")
    _checkpoint(s7)
    _checkpoint(sa)
    con = open_analytics(v7, v5_archive=archive)
    n = con.execute("SELECT COUNT(*) FROM v5.trades").fetchone()[0]
    assert n == 1  # the archive's past is queryable alongside V7's present
