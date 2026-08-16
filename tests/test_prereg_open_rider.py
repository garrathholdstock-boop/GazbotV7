"""BUILD #7 — the pre-registered Open Rider day filter, protected from being tuned.

Part 2 §5 REFUTED the searched day-classifier: given a small sample and many candidate features,
something always separates good days from bad and it does not survive forward. Pre-registration is
the only honest instrument left — it fixes the hypothesis BEFORE the data.

That only works if the registration cannot quietly move. These tests are the lock: change the
threshold, the feature, or the horizon, and the suite fails and says why.
"""
import json
import os

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "prereg_open_rider.json")


def _reg():
    with open(PATH) as f:
        return json.load(f)


def test_the_registration_is_exactly_what_was_registered():
    """⚠ IF THIS FAILS, DO NOT UPDATE THE TEST TO MATCH THE FILE. The whole value of a
    pre-registration is that it is fixed in advance; a test edited to fit a moved threshold turns
    the instrument back into the searched version it replaced. Restart the 60 sessions instead."""
    r = _reg()
    assert r["feature"] == "ATR14_at_1300Z"
    assert r["threshold_pt"] == 9.5
    assert r["measured_at_utc"] == "13:00"
    assert r["instrument"] == "MNQ"
    assert r["sessions_required"] == 60
    assert r["registered_on"] == "2026-08-16"


def test_it_is_ONE_feature():
    """The refuted version searched many. One is the design, not a starting point."""
    r = _reg()
    assert isinstance(r["feature"], str), "a list of features is the thing that was refuted"


def test_no_verdict_before_the_horizon():
    r = _reg()
    if r["sessions_elapsed"] < r["sessions_required"]:
        assert r["verdict"] is None, \
            f"a verdict at n={r['sessions_elapsed']} of {r['sessions_required']} is the exact " \
            f"error this design exists to prevent"


def test_the_excluded_sessions_are_recorded_too():
    """The sessions the filter turns OFF are half the test — recording only the traded ones would
    measure the rider, not the filter."""
    r = _reg()
    assert any("EXCLUDES" in x for x in r["rules_of_engagement"])
