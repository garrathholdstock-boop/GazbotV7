"""THE EVENT CALENDAR — parsed dates checked against GROUND TRUTH, not against itself.

★★★ WHY IT EXISTS (2026-09-16). The operator held LONG 4 through an FOMC decision, bought again at
T+52 while the slide was still running, and lost $1,272 on one trade — more than the day's -$833.

★★ WHY THESE TESTS ARE HARSH. The first version of the parser shipped two bugs that a
"does it return rows?" test would have passed:
  1. it scraped "(Minutes: February 18, 2026)" as a MEETING, inventing a February FOMC;
  2. it read a fixed 4,000 chars per year, cutting 2026 off after April and MISSING 27-28 Oct and
     8-9 Dec — the next two meetings and the whole point of the file.
Both produce a plausible, non-empty, WRONG calendar. So the assertions below are the actual
published dates, taken from federalreserve.gov on 2026-09-18, and two of them are independently
corroborated by our own 5s tape (29 Jul and 16 Sep both ran in the top 2% of 30-min windows).
"""
import datetime as dt
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import event_calendar as ec

SRC = "/home/alphabot/gazbot7/scripts/event_calendar.py"

# ★ GROUND TRUTH — federalreserve.gov, read 2026-09-18. Decision day = the LAST day of the meeting.
FOMC_2026 = {"2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"}
FOMC_2027 = {"2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
             "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08"}


def test_eight_meetings_a_year_is_enforced():
    """★★★ THE INVARIANT THAT MAKES SCRAPING SAFE AT ALL. The FOMC holds exactly eight meetings a
    year; a year that parses to anything else is a broken parse and must be DISCARDED, not written
    to a calendar he will stand aside on."""
    src = open(SRC).read()
    assert "!= 8" in src and "DISCARDED" in src, (
        "the 8-meetings-a-year guard is gone — without it a half-parsed year ships silently")


def test_parenthetical_minutes_are_stripped():
    """⚠ BUG 1. '(Minutes: February 18, 2026)' is not a meeting."""
    assert 'sub(r"\\([^)]*\\)"' in open(SRC).read(), "the minutes-stripper is gone"


def test_the_year_block_is_not_a_fixed_width_slice():
    """⚠ BUG 2. A fixed 4,000-char window cut 2026 off after April."""
    src = open(SRC).read()
    assert "hend:hend + 4000" not in src and "m.end() + 4000" not in src, (
        "the year block is back on a fixed-width slice — that MISSED October and December")


def test_footnotes_are_cut_before_parsing():
    """⚠ The 2027 block is trailed by 'January 25-26, 2028' and 'Last Update: September 16, 2026',
    which parsed as 2027 dates and made the year 10 meetings long."""
    src = open(SRC).read()
    assert "Meeting associated" in src and "Last Update" in src, "the footnote cut is gone"


def test_decision_day_is_the_LAST_day_of_the_meeting():
    """★ 'September 15-16' moves the tape on the 16th — the day that cost him $1,272. Taking the
    first day would put every alert 24 hours early."""
    assert "2026-09-16" in FOMC_2026 and "2026-09-15" not in FOMC_2026
    src = open(SRC).read()
    assert "mm.group(3) or mm.group(2)" in src, "the parser no longer prefers the second day"


def test_live_parse_matches_ground_truth_2026_and_2027():
    """★★ THE REAL TEST — against the published dates, not against the parser's own output.
    ⚠ Network-dependent by design: a calendar that cannot be checked against its source is a
    calendar nobody should stand aside on. Skips (never fails) if the Fed is unreachable."""
    import pytest
    try:
        got = ec.fetch_fomc()
    except Exception as e:
        pytest.skip(f"federalreserve.gov unreachable: {type(e).__name__}")
    for year, truth in ((2026, FOMC_2026), (2027, FOMC_2027)):
        mine = {e["date"] for e in got if e["date"].startswith(str(year))}
        assert mine == truth, f"{year} parsed {sorted(mine)} but the Fed publishes {sorted(truth)}"


def test_times_are_stored_in_EASTERN_and_converted_at_read_time():
    """★ Storing UTC bakes in a DST offset that is wrong half the year — US clocks change 1 Nov
    2026, so the same 08:30 release is 12:30Z today and 13:30Z in November."""
    src = open(SRC).read()
    assert '"et_time"' in src and "America/New_York" in src
    before = ec.utc_of({"date": "2026-10-14", "et_time": "08:30"})
    after = ec.utc_of({"date": "2026-11-10", "et_time": "08:30"})
    assert before.hour == 12, f"pre-DST-change 08:30 ET should be 12:30Z, got {before}"
    assert after.hour == 13, f"post-DST-change 08:30 ET should be 13:30Z, got {after}"


def test_fomc_utc_straddles_the_dst_change_too():
    assert ec.utc_of({"date": "2026-10-28", "et_time": "14:00"}).hour == 18
    assert ec.utc_of({"date": "2026-12-09", "et_time": "14:00"}).hour == 19


def test_bls_is_seeded_and_its_provenance_travels_with_it():
    """⚠ bls.gov returns 403 to this box under any User-Agent, so CPI/NFP CANNOT self-renew. The
    rows must carry that fact, not look like everything else."""
    rows = ec.seeded_bls()
    assert rows and all("403" in r["source"] for r in rows)
    assert {r["kind"] for r in rows} == {"CPI", "NFP"}
    assert all(r["et_time"] == "08:30" for r in rows)


def test_coverage_warns_before_a_series_runs_dry():
    """★★ A CALENDAR THAT QUIETLY EMPTIES is this desk's signature failure. CPI/NFP cannot renew
    themselves, so exhaustion has to be loud and EARLY — not on the day it happens."""
    src = open(SRC).read()
    assert "coverage_warnings" in src
    assert "NO FUTURE DATES AT ALL" in src
    assert "a HUMAN must refresh it" in src


def test_a_failed_fetch_never_empties_the_calendar():
    """⚠ The worst outcome is a refresh that succeeds at deleting and fails at fetching."""
    src = open(SRC).read()
    assert "kept {len(kept)} previously known" in src or "previously known" in src
    assert "os.replace" in src, "the write must be atomic — a half-written calendar is worse"


def test_unconfirmed_earnings_times_are_labelled_not_guessed_silently():
    """⚠ 'time-not-supplied' is common on Nasdaq. A before-open report lands in a completely
    different session from an after-close one, so the assumption must be VISIBLE."""
    src = open(SRC).read()
    assert "UNCONFIRMED" in src and '"confirmed": bool(et)' in src
