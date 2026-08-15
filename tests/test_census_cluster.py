"""The run-census cluster labels must describe the TAPE, not the clock.

★★2026-08-15. `cluster()` used to open with `if 13 <= hour < 15: return "OPEN/NEWS"`, before any
footprint test. That is not a classifier, it is a clock wearing a label: it is true on 100% of the
bars inside its own window, and the greenfield hunt measured it STEALING 31 of 94 in-window runs
from VACUUM and FLOW-LED. A textbook stop-run at 13:40 was filed as "OPEN/NEWS" and never reached
the hunt that might have caught it. The hunt's own words: "fixing that one line is worth more to
next week's hunt than any gate on this page."

The window is real (3.31x run lift) and is KEPT — as the fallback for a run with no footprint, where
"it happened at the US open" is the most informative thing we can say. It just no longer outranks
evidence.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from run_census import cluster  # noqa: E402

UP, DOWN = +40.0, -40.0
STRONG = 3.0          # flow z-score comfortably past FLOW_Z


def test_a_footprint_inside_the_window_keeps_its_footprint():
    """THE BUG. Both of these are unambiguous tape events that happen to occur at 13:xx."""
    assert cluster(13, -500, UP, 0.1, STRONG) == "VACUUM", "flow fought the move — that is a VACUUM"
    assert cluster(14, +500, UP, 0.1, STRONG) == "FLOW-LED", "flow drove the move — that is FLOW-LED"


def test_the_same_footprints_outside_the_window_are_unchanged():
    """Guards against 'fixing' it by breaking the footprint tests instead."""
    assert cluster(10, -500, UP, 0.1, STRONG) == "VACUUM"
    assert cluster(20, +500, DOWN, 0.1, STRONG) == "VACUUM"
    assert cluster(3, -500, DOWN, 0.1, STRONG) == "FLOW-LED"


def test_the_window_still_labels_a_run_with_no_footprint():
    """The window is KEPT, not deleted — it is the densest ignition window on the tape (3.31x run
    lift) and is the best thing we can say when the tape says nothing."""
    assert cluster(13, None, UP, 0.1, None) == "OPEN/NEWS"
    assert cluster(14, 10, UP, 0.1, 0.2) == "OPEN/NEWS", "weak flow is no footprint"


def test_no_footprint_and_outside_the_window_is_UNCLASS():
    assert cluster(10, None, UP, 0.1, None) == "UNCLASS"
    assert cluster(10, 10, UP, 0.1, 0.2) == "UNCLASS"


def test_vol_expansion_still_outranks_the_window():
    """VOL-EXPANSION is also a tape fact and must also beat the clock."""
    assert cluster(13, None, UP, 0.9, None) == "VOL-EXPANSION"
    assert cluster(10, None, UP, 0.9, None) == "VOL-EXPANSION"


def test_the_clock_is_not_the_first_test_anymore():
    """A source-level guard: this bug is a single line in the wrong PLACE, so it can be
    reintroduced by a well-meaning edit that looks harmless in review."""
    import inspect

    import run_census
    src = inspect.getsource(run_census.cluster)
    body = src.split('"""')[-1]                       # past the docstring
    i_clock = body.find("13 <= hour")
    i_flow = body.find("FLOW-LED")
    assert i_clock > i_flow > 0, "the session-window test must come AFTER the footprint tests"
