"""A NEW entry freezes a real ATR, so its trail runs on 4 x ATR rather than the fixed 150pt.

★★2026-09-04, operator: *"do the atr one for new entries only"*. `drift_read` is anchored to the
13:30 UTC cash open and returns atr 0.0 outside it, so an entry made then froze `arm_atr` at 0 and
`trail_level` fell back to the FIXED 150pt rule. At the measured ~7pt tape ATR that is **~29pt vs
150pt** — the trail armed five times later than the backtested rule intends.

★★★ ONE DEFINITION OF "THE RIDER'S ATR", AND THIS IS THE TEST THAT KEEPS IT THAT WAY.
`last_tape_atr` calls `drift.compute()` rather than re-deriving the formula, because `trail_level`'s
own docstring warns that scaling the trail off a differently-defined number is the live/lab
divergence this desk keeps getting bitten by. The equivalence below is asserted on real capture data
at five independent times.

⚠ NEW ENTRIES ONLY. `arm_atr` is frozen at entry and the manage path carries it forward untouched —
an open position keeps the rule it was opened under.
"""
import datetime as dt
import sqlite3
import sys

import pytest

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import gazbot7.day_rider as dr
from gazbot7.drift import _minute_bars, compute

CAP = "/home/alphabot/gazbot7/data/capture.db"
SRC = "/home/alphabot/gazbot7/src/gazbot7/day_rider.py"
# A US session inside capture's 5s retention. ⚠ NOT "today" and NOT wall-clock derived — a test that
# reads the clock fails only between 00-07 UTC, which this desk has already been bitten by 37 times.
DAY = dt.datetime(2026, 9, 3, tzinfo=dt.UTC)


def _drift_atr_to(t: dt.datetime) -> float:
    """drift's ATR over its own window (13:30 -> t), computed with drift's own code."""
    start = t.replace(hour=13, minute=30, second=0, microsecond=0)
    with sqlite3.connect(f"file:{CAP}?mode=ro", uri=True) as c:
        rows = c.execute(
            "SELECT bar_ts,high,low,close FROM bars WHERE symbol='MNQ' AND timeframe='5s' "
            "AND bar_ts>=? AND bar_ts<=? ORDER BY bar_ts",
            (int(start.timestamp()), int(t.timestamp()))).fetchall()
    if not rows:
        pytest.skip("capture no longer retains this session (5s tier is pruned to 5 days)")
    return compute(_minute_bars([(r[0], float(r[1]), float(r[2]), float(r[3])) for r in rows])).atr


@pytest.mark.parametrize("hh,mm", [(14, 30), (15, 0), (16, 30), (19, 0), (20, 30)])
def test_the_tape_atr_is_the_same_number_drift_computes(hh, mm):
    t = DAY.replace(hour=hh, minute=mm)
    expected = _drift_atr_to(t)
    got = dr.last_tape_atr(CAP, "MNQ", now_ts=t.timestamp())
    assert expected > 0 and abs(expected - got) < 1e-9, (
        f"two definitions of the rider's ATR have appeared: drift {expected} vs tape {got}")


def test_the_window_is_bounded_at_BOTH_ends():
    """★ A BUG CAUGHT WHILE WRITING THIS TEST. Without an upper bound a past `now_ts` silently reads
    TODAY's rows, and the first version of the equivalence check passed for the wrong reason —
    returning an identical ATR for three different times of day."""
    a = dr.last_tape_atr(CAP, "MNQ", now_ts=DAY.replace(hour=15).timestamp())
    b = dr.last_tape_atr(CAP, "MNQ", now_ts=DAY.replace(hour=19).timestamp())
    assert a != b, "the query is unbounded above — every timestamp reads the latest rows"


def test_a_stale_tape_prices_nothing():
    """Refuse, never guess — an absence of tape is not a measurement of it.

    ⚠ The first version of this test also asserted that a FUTURE timestamp returns 0.0. It cannot:
    the query is bounded at `now`, so the newest row is never ahead of it. The guard that claimed to
    cover that case was unreachable and was deleted rather than left as false comfort."""
    assert dr.last_tape_atr(CAP, "MNQ", max_age_s=1) == 0.0, "a halted feed must refuse"
    # a window that predates capture's 5s retention has no rows at all
    old = dt.datetime(2020, 1, 2, 15, 0, tzinfo=dt.UTC)
    assert dr.last_tape_atr(CAP, "MNQ", now_ts=old.timestamp()) == 0.0
    assert dr.last_tape_atr("/nonexistent/capture.db", "MNQ") == 0.0


def test_the_atr_reference_prefers_drift_and_falls_back_to_the_tape():
    import types
    cfg = types.SimpleNamespace(capture_path=CAP, symbol="MNQ")
    assert dr.entry_atr_reference(types.SimpleNamespace(atr=12.5), cfg) == 12.5
    blind = dr.entry_atr_reference(types.SimpleNamespace(atr=0.0), cfg)
    assert blind > 0, "an entry outside US hours would still freeze arm_atr at 0"


def test_only_the_ENTRY_paths_write_arm_atr():
    """★ THE SAFETY PROPERTY. An OPEN position must keep the rule it was opened under."""
    src = open(SRC).read()
    writes = [ln.strip() for ln in src.splitlines()
              if "arm_atr=" in ln or 'out["arm_atr"]' in ln]
    assert len(writes) == 3, f"unexpected arm_atr writes: {writes}"
    assert sum("arm_atr=round(_atr, 2)" in w for w in writes) == 2, (
        "both ENTRY sites must freeze the referenced ATR")
    assert any('out["arm_atr"] = arm_atr' in w for w in writes), (
        "the manage path must carry arm_atr forward UNTOUCHED — recomputing it mid-position would "
        "change the trail rule under an open trade")


def test_the_atr_arm_is_much_earlier_than_the_fixed_fallback():
    """The point of the change, in numbers."""
    atr = dr.last_tape_atr(CAP, "MNQ", now_ts=DAY.replace(hour=19).timestamp())
    assert dr.ARM_ATR_MULT * atr < dr.ARM_PT / 3, (
        f"4 x ATR ({dr.ARM_ATR_MULT * atr:.0f}pt) should be far earlier than the fixed "
        f"{dr.ARM_PT:.0f}pt this replaces")
