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


def test_every_market_written_file_is_on_the_market_clock():
    """★2026-08-17 REVERSED, because the reason for the old assertion was FALSE.

    This test used to assert gazbot7.db and shadow.db must stay on wall-clock, "written by the desk
    and by nightly jobs, so a dead writer would hide all weekend". The desk disproved it:
    `gazbot7-backup` is a WAL checkpoint + `VACUUM INTO` a SEPARATE file. It READS gazbot7.db and
    moves its mtime only when there is WAL to checkpoint — i.e. only when the desk TRADED. It ran
    and Finished on 08-15, 08-16 and 08-17 while the mtime sat at 08-15 03:30, and the operator was
    paged for "53h" on a Monday morning with nothing whatsoever wrong.

    Only `_manifest.json` is genuinely written by a daily job (tape-mirror, 21:05, every day
    including weekends), so it alone keeps wall-clock ageing — there a missed write IS a dead timer.
    """
    from data_inventory import LOCAL
    flags = {label.strip(): mc for label, _p, _m, mc in LOCAL}
    for name in ("capture.db", "depth.db", "gazbot7.db", "shadow.db", "shadow_mgc.db"):
        assert any(name in lb and mc for lb, mc in flags.items()), f"{name} must be on the market clock"
    assert all(not mc for lb, mc in flags.items() if "_manifest.json" in lb)


def test_the_weekend_stays_forgiven_after_the_market_reopens():
    """★ THE REGRESSION THIS FIX EXISTS FOR. `_last_market_ts` forgives shut hours only while you
    are still inside the closed window; once Monday opens it returns `now` and the whole weekend
    lands back in the age. Real numbers from the page: written Sat 03:30, read Mon 08:48."""
    from data_inventory import _market_hours_between
    wrote = ts(2026, 8, 15, 3, 30)                      # Saturday — market shut
    now = ts(2026, 8, 17, 8, 48)                        # Monday morning — market OPEN
    assert (now - wrote) / H > 53                       # wall-clock: what paged the operator
    assert (_last_market_ts(now) - wrote) / H > 53      # the OLD market-clock: no help at all
    open_h = _market_hours_between(wrote, now)
    assert 10 < open_h < 12, f"only Sun 22:00 -> Mon 08:48 is open time, got {open_h:.1f}h"
    assert open_h < 30, "must not breach the shadow-book threshold"
    assert open_h < 72, "must not breach the trade-record threshold"


def test_open_hours_still_accrue_at_full_rate_during_trading():
    """★ THE PROPERTY THAT MUST NOT BE LOST. Forgiving shut hours must not forgive trading ones."""
    from data_inventory import _market_hours_between
    died = ts(2026, 8, 14, 10, 0)                       # Friday mid-session
    for now, lo, hi in ((ts(2026, 8, 15, 12, 46), 10, 12),   # Saturday: measures to the Fri close
                        (ts(2026, 8, 16, 20, 0), 10, 12),    # Sunday, pre-reopen: still ~11h
                        (ts(2026, 8, 17, 8, 48), 21, 23)):   # Monday: +10.8h of real trading
        got = _market_hours_between(died, now)
        assert lo < got < hi, f"at {now}: expected {lo}-{hi}h, got {got:.1f}h"
        assert got > 2, "a mid-session death must always breach the 2h tape threshold"


def test_a_healthy_close_reads_as_zero_open_hours():
    """depth.db's real mtime: 12 min AFTER the Friday close. Zero open hours until the reopen."""
    from data_inventory import _market_hours_between
    wrote = ts(2026, 8, 14, 21, 12)
    assert _market_hours_between(wrote, ts(2026, 8, 15, 12, 46)) == 0.0
    assert _market_hours_between(wrote, ts(2026, 8, 16, 20, 0)) == 0.0
    assert _market_hours_between(wrote, ts(2026, 8, 16, 23, 0)) > 0.9   # reopened at 22:00
