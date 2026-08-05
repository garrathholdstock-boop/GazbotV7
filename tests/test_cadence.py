"""★2026-08-03 — the shared cadence contract. Decisions at 1s, exits at 250ms, everywhere."""
import pytest
from gazbot7.cadence import BAR_S, DECISION_MS, EXEC_MS, assert_matches_live, describe, downsample


def test_the_asymmetry_is_deliberate():
    """Entries are limited by when WE look; stops by when the VENUE fills. Not the same number."""
    assert DECISION_MS == 1000            # md.py tape_interval_s = 1.0
    assert EXEC_MS == 250                 # capture tick cadence
    assert DECISION_MS > EXEC_MS, "we act slower than the market hits us — that is the whole point"


def test_downsample_returns_the_last_print_per_bucket():
    """A 1s poll sees whatever the tape showed at that instant — not the mean, not the extreme."""
    prints = [(1000, 10.0), (1200, 99.0), (1900, 11.0), (2100, 12.0), (2900, 13.0)]
    assert downsample(prints, 1000) == [(1900, 11.0), (2900, 13.0)]


def test_downsample_deletes_the_intrabucket_spike():
    """THE bug this module exists to prevent. A 99.0 spike inside the second is invisible to a 1s
    poll — correct for an ENTRY (we could not have acted on it) and catastrophic for a STOP
    (the venue would have filled us). Racing a stop over downsampled prints hides real losses."""
    prints = [(1000, 10.0), (1500, 99.0), (1999, 10.0)]
    seen = downsample(prints, 1000)
    assert 99.0 not in [p for _, p in seen]
    assert 99.0 in [p for _, p in prints]      # still there in the raw stream, where stops must race


def test_downsample_zero_is_a_passthrough():
    prints = [(1, 1.0), (2, 2.0)]
    assert downsample(prints, 0) == prints


def test_downsample_handles_empty_and_unsorted():
    assert downsample([], 1000) == []
    out = downsample([(2500, 5.0), (1500, 4.0)], 1000)
    assert [t for t, _ in out] == [1500, 2500]          # sorted by bucket


def test_assert_matches_live_is_the_drift_guard():
    assert_matches_live(DECISION_MS, EXEC_MS)            # the desk's own values pass
    with pytest.raises(ValueError, match="cadence mismatch"):
        assert_matches_live(250, 250)                    # a tick-rate harness must fail loudly
    with pytest.raises(ValueError, match="cadence mismatch"):
        assert_matches_live(60_000, 250)                 # shadow's 1-minute decisions must fail too


def test_describe_names_all_three():
    d = describe()
    assert "1000ms" in d and "250ms" in d and f"{BAR_S}s" in d


def test_live_desk_really_publishes_at_decision_ms():
    """Guard against the desk changing under us: md.py's default must match DECISION_MS."""
    import inspect

    from gazbot7 import md
    sig = inspect.signature(md.run)
    assert sig.parameters["tape_interval_s"].default * 1000 == DECISION_MS
