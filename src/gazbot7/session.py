"""GAZBOT V7 — the MNQ session calendar (S4). One source of session truth.

Imported by strategy (the no-open gate), core (session-end flatten + reject), and
the EOD-flatten timer, so none of them can drift on when the market is open. MNQ
trades CME Globex: Sunday 18:00 ET through Friday 17:00 ET, with a daily
maintenance halt 17:00–18:00 ET. All arithmetic is in America/New_York so DST is
handled by the zone, never a hardcoded UTC offset (V5 ate a DST 60-min mis-fire).

The operator's cardinal rule is FLAT before the daily 17:00 ET close, every day,
autonomously — so entries stop ``no_open`` minutes before it and any straggler is
flattened by the independent systemd timer (with core's in-loop check as a
backstop). Pure functions of an aware datetime; fully tested. Clean-room.
"""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
DAILY_CLOSE = dtime(17, 0)  # CME Globex daily halt begins (ET)
DAILY_OPEN = dtime(18, 0)   # reopen (ET)


def _et(now: datetime) -> datetime:
    return now.astimezone(_ET)


def is_open(now: datetime) -> bool:
    """Is MNQ trading at this instant?"""
    et = _et(now)
    wd = et.weekday()  # Mon=0 … Sun=6
    t = et.time()
    if wd == 5:  # Saturday — closed all day
        return False
    if wd == 6:  # Sunday — closed until the 18:00 ET reopen
        return t >= DAILY_OPEN
    if wd == 4 and t >= DAILY_CLOSE:  # Friday 17:00 ET → weekend
        return False
    if DAILY_CLOSE <= t < DAILY_OPEN:  # daily maintenance halt
        return False
    return True


def minutes_to_next_close(now: datetime) -> float | None:
    """Minutes until the next 17:00 ET close while open (today's if we're before it,
    else tomorrow's for the evening/overnight session). None when closed."""
    if not is_open(now):
        return None
    et = _et(now)
    day = et.date()
    if et.time() >= DAILY_CLOSE:  # evening session (≥18:00) → next close is tomorrow
        close_dt = datetime.combine(day + timedelta(days=1), DAILY_CLOSE, tzinfo=_ET)
    else:
        close_dt = datetime.combine(day, DAILY_CLOSE, tzinfo=_ET)
    return (close_dt - et).total_seconds() / 60.0


def in_no_open_window(now: datetime, minutes_before: float = 20.0) -> bool:
    """Within ``minutes_before`` of the 17:00 ET close — suppress NEW entries."""
    m = minutes_to_next_close(now)
    return m is not None and m <= minutes_before


def should_flatten(now: datetime, minutes_before: float = 5.0) -> bool:
    """The in-loop session-end flatten backstop: inside the final ``minutes_before``
    before the close (the systemd timer is the primary, process-independent path)."""
    m = minutes_to_next_close(now)
    return m is not None and m <= minutes_before
