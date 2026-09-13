"""THE DAILY LOSS LIMIT MAY ONLY EVER BENCH. This is what keeps that true.

A protective mechanism that can also ENABLE something is not a protection, it is a second trading
system with a safety-shaped name. This desk has already been bitten by the inverse — a cross-desk
kill that disarmed the desk it was protecting and took the operator's claim buttons with it — so the
limit is deliberately one-directional AND self-clearing: gate-reactivate arms every `off` gate at
22:00Z, so a bench lasts one session and needs no human release.
"""
import datetime as dt
import os
import re

SRC = os.path.join(os.path.dirname(__file__), "..", "scripts", "daily_loss_limit.py")


def _src():
    with open(SRC) as fh:
        return fh.read()


def test_it_never_writes_on():
    """The whole safety property, asserted against the source."""
    s = _src()
    assert '"on"' not in s and "'on'" not in s and "=on" not in s, \
        "the loss limit must never be able to arm a gate"
    assert "=off" in s


def test_it_has_no_order_path_and_flattens_nothing():
    s = _src().lower()
    for forbidden in ("placeorder", "place_order", "ib_async", "ib_insync", "flatten",
                      "day_rider_claim", "day_rider_buy", "desk_kill", "marketorder"):
        assert forbidden not in s, f"the loss limit must not reference {forbidden}"


def test_the_level_is_frozen_and_named():
    s = _src()
    assert re.search(r"LIMIT_USD\s*=\s*250\.0", s), "the registered level is $250 and is frozen"
    assert "restarts the forward count at zero" in s, "the freeze must be stated where it is set"


def test_the_session_boundary_is_the_2200z_reopen_not_midnight():
    """★ The bug this test exists to prevent: a limit that resets at MIDNIGHT would clear itself in
    the middle of a losing overnight session — the one moment it must not. A CME session starts at
    the 22:00Z reopen, so 23:00Z Tuesday and 14:00Z Wednesday are the SAME session."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("dll", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    def sess_of(h, d=15):
        now = dt.datetime(2026, 9, d, h, 0, tzinfo=dt.UTC)
        start = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if now.hour < 22:
            start -= dt.timedelta(days=1)
        return start

    assert sess_of(23, 15) == dt.datetime(2026, 9, 15, 22, 0, tzinfo=dt.UTC)
    assert sess_of(14, 16) == dt.datetime(2026, 9, 15, 22, 0, tzinfo=dt.UTC), \
        "23:00Z Tue and 14:00Z Wed must resolve to the SAME session"
    assert sess_of(21, 16) == dt.datetime(2026, 9, 15, 22, 0, tzinfo=dt.UTC)
    assert sess_of(22, 16) == dt.datetime(2026, 9, 16, 22, 0, tzinfo=dt.UTC), \
        "22:00Z is the boundary: a new session begins"


def test_it_fires_once_per_session_not_once_per_tick():
    """It runs every couple of minutes; without the latch it would rewrite the switch file (and
    re-page) on every tick for the rest of the session."""
    s = _src()
    assert "fired" in s and "prev.get(\"session\") == sess" in s


def test_it_is_atomic_and_leaves_unknown_lines_alone():
    """gate_switches.env carries operator comments and a header. A rewrite that dropped them, or a
    torn write mid-read by the tournament, would be far worse than the loss it prevents."""
    s = _src()
    assert "os.replace(" in s, "the switch write must be atomic"
    assert "else:\n            out.append(ln)" in s, "non-gate lines must be preserved verbatim"
