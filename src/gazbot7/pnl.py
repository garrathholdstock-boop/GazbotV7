"""GAZBOT V7 — the single realized-P&L source (S7).

One function computes desk P&L; every surface (web, kill-switches, monitor) calls
it, so they cannot disagree — V5 bled weeks on four surfaces each summing trades a
different way. ``trades.pnl_usd`` is recorded net-of-fees and signed at write time
(tracker.py), so realized P&L is a plain sign-aware SUM. "Today" is the Paris day
on ``closed_at`` — the desk's day convention, DST-correct. Pure over the store;
a test asserts this is the only place that sums pnl_usd. Clean-room.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_PARIS = ZoneInfo("Europe/Paris")
_UTC = ZoneInfo("UTC")
# reconcile/cleanup exits are not strategy trades — excluded from desk P&L
# (V5's CANONICAL_DESK_WHERE did the same for its reconcile artifacts).
_CLEANUP_REASONS = ("ADOPT_FLATTEN",)


def paris_day_start_utc(now: datetime) -> str:
    """ISO-UTC instant of the current Paris midnight (the desk's day boundary)."""
    start = now.astimezone(_PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(_UTC).isoformat()


def paris_week_start_utc(now: datetime) -> str:
    """ISO-UTC instant of the current Paris week's Monday-midnight (the desk's week
    boundary — used by the scoreboard's week-to-date winner/loser expectancy block)."""
    from datetime import timedelta
    local = now.astimezone(_PARIS)
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(_UTC).isoformat()


def realized(store, symbol: str, *, since_iso: str | None = None) -> tuple[float, int, int]:
    """Net-of-fees realized P&L (sign-aware), trade count, win count — for trades
    closed at/after ``since_iso`` (default all-time)."""
    placeholders = ",".join("?" * len(_CLEANUP_REASONS))
    q = f"SELECT pnl_usd FROM trades WHERE symbol=? AND exit_reason NOT IN ({placeholders})"
    args: list = [symbol, *_CLEANUP_REASONS]
    if since_iso is not None:
        q += " AND closed_at>=?"
        args.append(since_iso)
    rows = store.execute(q, args).fetchall()
    pnl = round(sum(r[0] for r in rows), 2)
    return pnl, len(rows), sum(1 for r in rows if r[0] > 0)


def day(store, symbol: str, now: datetime) -> tuple[float, int, int]:
    """Realized P&L / trades / wins for the current Paris day."""
    return realized(store, symbol, since_iso=paris_day_start_utc(now))
