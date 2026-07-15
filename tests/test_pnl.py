"""S7 — the single realized-P&L source: net, sign-aware, Paris-day."""

from __future__ import annotations

from datetime import UTC, datetime

from gazbot7 import pnl
from gazbot7.store import open_store, record_trade


def _trade(store, side, p, closed_at, exit_exec):
    record_trade(store, symbol="MNQ", side=side, qty=1, entry_price=100.0, exit_price=101.0,
                 opened_at="2026-07-15T13:00:00+00:00", closed_at=closed_at,
                 pnl_usd=p, fees_usd=1.5, exit_reason="X", exit_exec_id=exit_exec)


def test_realized_is_signed_sum():
    s = open_store(":memory:")
    _trade(s, "LONG", 18.5, "2026-07-15T14:00:00+00:00", "x1")
    _trade(s, "SHORT", -12.0, "2026-07-15T15:00:00+00:00", "x2")  # a short LOSS is negative
    pnl_usd, n, wins = pnl.realized(s, "MNQ")
    assert pnl_usd == 6.5 and n == 2 and wins == 1


def test_day_filters_to_paris_day():
    s = open_store(":memory:")
    # Paris day of 2026-07-15 starts 2026-07-14T22:00Z (CEST). A trade closed
    # before that boundary is a prior day and excluded.
    _trade(s, "LONG", 100.0, "2026-07-14T20:00:00+00:00", "old")   # prior Paris day
    _trade(s, "LONG", 5.0, "2026-07-15T09:00:00+00:00", "today")   # today
    now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    pnl_usd, n, _w = pnl.day(s, "MNQ", now)
    assert pnl_usd == 5.0 and n == 1  # only today's trade counts
