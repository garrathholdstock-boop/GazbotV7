"""Tape freshness must age on MARKET time, not wall-clock.

★★2026-08-15. capture.db and depth.db are written by the TAPE, so when the venue is shut there is
nothing to write. A flat "expect < 2h" therefore fires every weekend, for two days, on the same
Telegram channel that carries naked-position alarms. It did exactly that this Saturday —

    ⚠ GAZBOT DATA/BACKUP — live tape capture.db not written for 9h (expect <2h)
                         | L2 depth depth.db not written for 15h (expect <2h)

— with all four capture services ACTIVE and depth.db's last write 12 minutes after the Friday close.
Nothing was wrong. An alarm that fires on schedule when nothing is wrong is not a safety net, it is
training to ignore the channel.

⚠ THE POINT OF THESE TESTS is that the fix is NOT a suppression. Only the hours the market was SHUT
are forgiven; a genuine death during trading hours must still be caught on the weekend, and
test_a_real_friday_death_is_still_caught_on_saturday is the one that matters.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from data_inventory import _last_market_ts  # noqa: E402

H = 3600.0


def ts(*a):
    return dt.datetime(*a, tzinfo=dt.UTC).timestamp()


def last(*a):
    return dt.datetime.fromtimestamp(_last_market_ts(ts(*a)), dt.UTC)


def test_the_weekend_rebases_to_the_friday_close():
    """CME shuts Fri 21:00Z and reopens Sun 22:00Z."""
    assert last(2026, 8, 15, 12, 46).strftime("%a %H") == "Fri 20"     # Saturday lunchtime
    assert last(2026, 8, 16, 12, 0).strftime("%a %H") == "Fri 20"      # Sunday lunchtime
    assert last(2026, 8, 14, 23, 0).strftime("%a %H") == "Fri 20"      # Friday, after the close


def test_an_open_market_is_its_own_reference():
    for when in ((2026, 8, 12, 15, 0), (2026, 8, 16, 23, 0), (2026, 8, 13, 3, 0)):
        assert _last_market_ts(ts(*when)) == ts(*when)


def test_the_daily_halt_is_forgiven_too():
    """21:00-22:00Z Mon-Thu is a real halt — one hour of no tape every weekday night."""
    assert last(2026, 8, 12, 21, 30).strftime("%a %H") == "Wed 20"


def test_a_real_friday_death_is_still_caught_on_saturday():
    """★ THE TEST THAT MATTERS. If capture stopped at Friday 10:00, Saturday must still report it
    stale — measured to the Friday 21:00 close, not to Saturday lunchtime. Forgiving the shut hours
    must not forgive the trading ones."""
    died = ts(2026, 8, 14, 10, 0)                       # Friday mid-session
    now = ts(2026, 8, 15, 12, 46)                       # Saturday lunchtime
    age_h = max(0.0, (_last_market_ts(now) - died) / H)
    assert age_h > 2, "a mid-session death must still breach the 2h tape threshold on a weekend"
    assert 10 < age_h < 12, f"should measure ~11h to the Friday close, got {age_h:.1f}h"


def test_a_healthy_close_reads_as_zero_not_as_days():
    """depth.db's real mtime: 12 minutes AFTER the Friday close. Its age must floor at 0, never go
    negative and never accumulate weekend hours."""
    wrote = ts(2026, 8, 14, 21, 12)
    for now in (ts(2026, 8, 15, 12, 46), ts(2026, 8, 16, 20, 0)):
        assert max(0.0, (_last_market_ts(now) - wrote) / H) == 0.0


def test_the_tape_files_are_the_ones_on_the_market_clock():
    """Only the tape ages on market time. The trade record and shadow book are written by the desk
    and by nightly jobs, so they must keep wall-clock ageing or a dead writer would hide all weekend."""
    from data_inventory import LOCAL
    by = {label.split()[0] + " " + label.split()[1]: mc for label, _p, _m, mc in
          [(l, p, m, mc) for l, p, m, mc in LOCAL]}
    flags = {l.strip(): mc for l, _p, _m, mc in LOCAL}
    assert any("capture.db" in l and mc for l, mc in flags.items())
    assert any("depth.db" in l and mc for l, mc in flags.items())
    assert all(not mc for l, mc in flags.items() if "gazbot7.db" in l or "shadow.db" in l)
