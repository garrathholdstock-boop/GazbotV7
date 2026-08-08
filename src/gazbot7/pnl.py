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


# ★★2026-08-07 TWO DESKS, TWO P&Ls (operator: "day rider will destroy it. needs to be isolated").
# The DAY RIDER is a separate strategy on its own service and clientId, holding for HOURS with no
# stop — a single trade swings hundreds of dollars. Blended into the tournament's number it drowns
# 20+ scalps: on 08-07 the desk made +$227 across 23 trades while the day-rider ran ~-$975 on ONE.
# One number cannot answer "is the desk working?" and "is the day-rider working?" at the same time.
# Filtering here rather than at ~20 call sites for the same reason the data_quality clause lives
# here — this module is the single P&L source, and that is the invariant worth protecting.
DAY_RIDER_GATE_PREFIX = "day_rider"


def realized(store, symbol: str, *, since_iso: str | None = None,
             desk: str | None = None) -> tuple[float, int, int]:
    """Net-of-fees realized P&L (sign-aware), trade count, win count — for trades
    closed at/after ``since_iso`` (default all-time).

    ``desk`` selects which book: ``"tournament"`` excludes day-rider rows, ``"day_rider"`` keeps
    only those, ``None`` (default) is everything — the pre-existing behaviour, so no current caller
    changes meaning until it opts in. Attribution is by gate prefix, which is how the day-rider
    already names its rows (``day_rider_crossdesk`` etc.)."""
    # ★2026-08-05 EXCLUDE data_quality-flagged rows AT THE SOURCE.
    # The flag was added this morning (rows 538/539 — the two abs_veto_short lots the MD_STREAM bug
    # sized with 1,848-point stops, -$255.50) and NOT ONE of the ~20 trade-table consumers filtered it.
    # So the open-hour watcher reported abs_veto_short at -$387.50 when the true figure was -$132.00
    # and recommended a bench on a number 3x too large. That is the SAME mistake as the original bug:
    # a field was added and the CONSUMERS were not audited (md-stream-multi-symbol-filter).
    # Fixed here rather than at 20 call sites because this module is the single P&L source — the
    # docstring's own invariant. `data_quality IS NULL` is the normal case, so every unflagged row
    # behaves exactly as before and no existing figure moves except the two corrupt ones.
    # ⚠ AND IT MUST TOLERATE THE COLUMN NOT EXISTING. Adding the clause unconditionally broke 8 tests
    # instantly (their fixtures build `trades` without it) — and would equally break a fresh deployment
    # or any older database. A P&L source that throws is worse than one that over-counts two rows, so
    # the clause is applied only when the column is actually present.
    placeholders = ",".join("?" * len(_CLEANUP_REASONS))
    has_dq = any(r[1] == "data_quality"
                 for r in store.execute("PRAGMA table_info(trades)").fetchall())
    q = f"SELECT pnl_usd FROM trades WHERE symbol=? AND exit_reason NOT IN ({placeholders})"
    if has_dq:
        q += " AND data_quality IS NULL"
    args: list = [symbol, *_CLEANUP_REASONS]
    if desk == "tournament":
        q += " AND (gate IS NULL OR gate NOT LIKE ?)"
        args.append(f"{DAY_RIDER_GATE_PREFIX}%")
    elif desk == "day_rider":
        q += " AND gate LIKE ?"
        args.append(f"{DAY_RIDER_GATE_PREFIX}%")
    if since_iso is not None:
        q += " AND closed_at>=?"
        args.append(since_iso)
    rows = store.execute(q, args).fetchall()
    pnl = round(sum(r[0] for r in rows), 2)
    return pnl, len(rows), sum(1 for r in rows if r[0] > 0)


def day(store, symbol: str, now: datetime, *, desk: str | None = None) -> tuple[float, int, int]:
    """Realized P&L / trades / wins for the current Paris day. See ``realized`` for ``desk``."""
    return realized(store, symbol, since_iso=paris_day_start_utc(now), desk=desk)
