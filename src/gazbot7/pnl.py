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


def paris_day_start_utc(now: datetime) -> str:
    """ISO-UTC instant of the current Paris midnight (the desk's day boundary)."""
    start = now.astimezone(_PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(_UTC).isoformat()


def realized(store, symbol: str, *, since_iso: str | None = None) -> tuple[float, int, int]:
    """Net-of-fees realized P&L (sign-aware), trade count, win count — for trades
    closed at/after ``since_iso`` (default all-time)."""
    q = "SELECT pnl_usd FROM trades WHERE symbol=?"
    args: list = [symbol]
    if since_iso is not None:
        q += " AND closed_at>=?"
        args.append(since_iso)
    rows = store.execute(q, args).fetchall()
    pnl = round(sum(r[0] for r in rows), 2)
    return pnl, len(rows), sum(1 for r in rows if r[0] > 0)


def day(store, symbol: str, now: datetime) -> tuple[float, int, int]:
    """Realized P&L / trades / wins for the current Paris day."""
    return realized(store, symbol, since_iso=paris_day_start_utc(now))
