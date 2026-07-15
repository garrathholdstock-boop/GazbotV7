"""S4 — the MNQ session calendar (America/New_York, DST-safe)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from gazbot7 import session

ET = ZoneInfo("America/New_York")
# 2026-07-13 Mon, -15 Wed, -17 Fri, -18 Sat, -19 Sun (confirmed)


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def test_open_during_weekday_session():
    assert session.is_open(_et(2026, 7, 15, 12, 0))   # Wed midday
    assert session.is_open(_et(2026, 7, 15, 2, 0))    # Wed overnight
    assert session.is_open(_et(2026, 7, 17, 12, 0))   # Fri daytime


def test_daily_maintenance_halt_closed():
    assert not session.is_open(_et(2026, 7, 15, 17, 30))  # inside 17:00–18:00 ET halt


def test_weekend_boundaries():
    assert not session.is_open(_et(2026, 7, 17, 18, 0))   # Fri after 17:00 → weekend
    assert not session.is_open(_et(2026, 7, 18, 12, 0))   # Saturday
    assert not session.is_open(_et(2026, 7, 19, 12, 0))   # Sunday before reopen
    assert session.is_open(_et(2026, 7, 19, 19, 0))       # Sunday after 18:00 reopen


def test_no_open_window():
    assert session.in_no_open_window(_et(2026, 7, 15, 16, 45))       # 15 min before close
    assert not session.in_no_open_window(_et(2026, 7, 15, 16, 30))   # 30 min before
    assert not session.in_no_open_window(_et(2026, 7, 15, 12, 0))    # midday


def test_should_flatten_near_close_only():
    assert session.should_flatten(_et(2026, 7, 15, 16, 57))          # 3 min before close
    assert not session.should_flatten(_et(2026, 7, 15, 16, 45))      # 15 min (> 5)


def test_minutes_to_next_close_rolls_to_tomorrow_in_evening():
    m = session.minutes_to_next_close(_et(2026, 7, 15, 20, 0))  # Wed 20:00 → Thu 17:00 ET
    assert m is not None and 20 * 60 < m < 22 * 60
    assert session.minutes_to_next_close(_et(2026, 7, 18, 12, 0)) is None  # closed
