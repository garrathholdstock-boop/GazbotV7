"""S9 — operator alert tiers + quiet hours (in code, not by convention)."""

from __future__ import annotations

from datetime import UTC, datetime

from gazbot7 import notify


def _at(hour_utc):
    return datetime(2026, 7, 15, hour_utc, 0, tzinfo=UTC)


def test_quiet_hours_paris():
    # 22:00–06:00 Paris. In July Paris is UTC+2, so 21:00 UTC = 23:00 Paris (quiet),
    # 12:00 UTC = 14:00 Paris (awake).
    assert notify.in_quiet_hours(_at(21)) is True    # 23:00 Paris
    assert notify.in_quiet_hours(_at(1)) is True     # 03:00 Paris
    assert notify.in_quiet_hours(_at(12)) is False   # 14:00 Paris


def test_routine_suppressed_in_quiet_hours():
    sent = []
    ok = notify.notify("heartbeat", critical=False, now=_at(1), send=sent.append)
    assert ok is False and sent == []  # routine at 03:00 Paris → not sent


def test_critical_always_sends():
    sent = []
    ok = notify.notify("NAKED", critical=True, now=_at(1), send=lambda m: (sent.append(m), True)[1])
    assert ok is True and sent == ["NAKED"]  # safety overrides quiet hours


def test_routine_sends_when_awake():
    sent = []
    ok = notify.notify("heartbeat", critical=False, now=_at(12), send=lambda m: (sent.append(m), True)[1])
    assert ok is True and sent == ["heartbeat"]


def test_sd_notify_noop_without_systemd(monkeypatch):
    from gazbot7.sdnotify import sd_notify
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert sd_notify("WATCHDOG=1") is False  # standalone/tests unaffected
