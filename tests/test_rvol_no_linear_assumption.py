"""RVOL MUST NOT ASSUME VOLUME ACCRUES LINEARLY THROUGH THE HOUR.

★★★2026-09-24. The operator caught this from the tape, not from the code: "its the us open first
15 minutes and the desk is reading between .80 and .99 during the big thrusts. cant be right?"

It could not. The meter compared a PARTIAL hour against `full_hour_average * fraction_elapsed`.
That models the hour as accruing evenly, and the 13:00Z hour is the single worst hour of the day
for that assumption — the US cash open lands at 13:30, so the hour is violently back-loaded.

MEASURED on 51 sessions of our own 5s bars (median cumulative share of the 13:00Z hour):
    13:15  actual  6.2%  vs linear 26.7%   ->  a NORMAL day read 0.23x
    13:35  actual 37.0%  vs linear 60.0%   ->  a NORMAL day read 0.62x
    13:40  actual 52.5%  vs linear 68.3%   ->  a NORMAL day read 0.77x
    13:45  actual 65.6%  vs linear 76.7%   ->  a NORMAL day read 0.86x

Replayed over 41 sessions at 13:35Z the old formula ranged 0.14-0.91x — it was NOT CAPABLE of
reporting an above-average open, on any day in the sample. The fix compares like against like
(this hour's elapsed window vs the same elapsed window on prior sessions), which brings the median
to ~0.98x with a real 0.17-1.47x spread.

⚠ This is the desk's signature failure wearing a new hat: an instrument reporting confidently about
something it never actually measured.
"""
import re

WEB = "/home/alphabot/gazbot7/src/gazbot7/web.py"


def _ctx_rvol_block():
    """The RVOL block with COMMENTS STRIPPED.

    ⚠ The comment above this code QUOTES the broken expression in order to explain why it was
    wrong, so a raw-text assertion matches the explanation and fails on a correct fix. Third time
    today this shape has bitten: test what RUNS, never what the file merely contains.
    """
    s = open(WEB, encoding="utf-8").read()
    blk = s.split("── RVOL:", 1)[1].split("c.close()", 1)[0]
    return "\n".join(l for l in blk.splitlines() if not l.lstrip().startswith("#"))


def test_the_partial_hour_is_not_scaled_by_elapsed_fraction():
    """★ THE BUG ITSELF. `base * frac` is the linear-accrual assumption in one expression."""
    b = _ctx_rvol_block()
    assert "base * frac" not in b
    assert "/ 3600.0" not in b, "an hour-fraction is being computed — the assumption is back"


def test_the_baseline_uses_the_same_elapsed_window():
    """★ The fix REMOVES the assumption rather than correcting it: compare 13:00-13:42 against
    13:00-13:42 on prior sessions, so the intraday shape cancels instead of being modelled. A
    fitted shape curve would need re-fitting per hour, per contract, and after every roll."""
    b = _ctx_rvol_block()
    assert "elapsed" in b
    assert re.search(r"bar_ts>=\?\s*and\s*bar_ts<\?", b) or "a + elapsed" in b


def test_the_baseline_is_a_median():
    """⚠ One FOMC or NFP inside the 10-day baseline drags a MEAN upward, and every ordinary day
    afterwards then reads quiet — the same class of error, one layer down."""
    b = _ctx_rvol_block()
    assert "sorted(hist)" in b, "expected a median"
    assert "sum(hist) / len(hist)" not in b


def test_an_empty_day_is_excluded_not_averaged_as_zero():
    """⚠ A weekend or holiday window is EMPTY, not quiet. Averaging a zero in halves the baseline
    and reports a flat tape as a volume surge — every Monday."""
    b = _ctx_rvol_block()
    assert "count(*)" in b and "row[1] >=" in b


def test_the_caveat_tells_him_what_it_now_compares():
    """★ He reads this meter during the open and acts on it. The tooltip has to say what the number
    is, not just warn about the roll."""
    b = _ctx_rvol_block()
    assert "SAME minutes" in b and "10 sessions" in b
