"""The rider exits on the LADDER, the operator's hands, or the 20:40 clock. Nothing else.

Operator, 2026-09-11: "turn all exits and stops for day rider off except the 4 levels of take
profit. the rest is up to me to do manually."

*** THE TRADE THAT ENDED THE TRAIL, and it was not a tuning failure - the level never existed.
LONG 4 @ 29320.25. The peak 29397.50 printed in the 12:30:00 bar, putting the trail at 29384.36
(peak - 2xATR 6.57). The NEXT 5-second bar low was 29268.25: 116 points through the trail in under
thirty seconds, 29244.25 by 12:31:00. The rider polls once a MINUTE, so it never sold at 29384 - it
woke, saw price far below, and sent a MARKET order that filled 29255.25 / 29226.00. By 12:32:30 the
tape was back at 29303.

    trail level      29384.36   (+64 vs entry)
    actual fills     29255.25, 29226.00   (and 29240.75 on the lot before)
    give-up          ~130-158 points BELOW the level the rule named

!! A POLLED LEVEL IS NOT A STOP. It does not exit at its level; it exits wherever price is on the
   next tick, which on a fast tape is the bottom of the move. No arming multiple or trail width
   fixes that, so this is a switch, not a retune.

WHAT THESE TESTS PIN: that the trail cannot fire, that the ladder and the manual paths are
untouched, and - the part worth more than the rest - that the 20:40 hard flat SURVIVES. "Turn all
exits off" and "NEVER HOLD OVERNIGHT. EVER." are both standing operator instructions, and the
second is the one that keeps a naked stopless position from crossing the halt.
"""
import io
import re

import pytest

import sys
sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import day_rider as dr  # noqa: E402

SRC = "/home/alphabot/gazbot7/src/gazbot7/day_rider.py"


def _src():
    return io.open(SRC, encoding="utf-8").read()


# ── the trail cannot fire ────────────────────────────────────────────────────

def test_the_trail_switch_is_off():
    assert dr.USE_TRAIL_EXIT is False, "the trail is live again - was that deliberate?"


def test_no_stop_is_placed_at_the_broker():
    """Unchanged since 08-20, asserted here so "all stops off" is verified, not assumed."""
    assert dr.PLACE_VENUE_STOP is False


@pytest.mark.parametrize("d,entry,peak,atr", [
    (1, 29320.25, 29397.50, 6.57),    # THE 2026-09-11 TRADE, exactly
    (1, 29000.00, 29200.00, 10.0),    # 200pt ahead - would have armed comfortably
    (-1, 29400.00, 29100.00, 10.0),   # the short side
    (1, 29000.00, 29400.00, 0.0),     # no frozen ATR -> the fixed 150pt fallback rule
])
def test_the_live_path_produces_no_trail_however_far_ahead_it_is(d, entry, peak, atr):
    """THE REGRESSION CASE. The live call site must yield None, so nothing downstream can fire.

    Mirrors `tl = trail_level(...) if USE_TRAIL_EXIT else None` at the single call site. Both
    fallback rules are covered: a missing frozen ATR silently switches trail_level() to the fixed
    150pt rule, and an exit that came back through THAT path would be just as unwanted.
    """
    tl = dr.trail_level(d, entry, peak, atr) if dr.USE_TRAIL_EXIT else None
    assert tl is None, f"a trail level came back ({tl}) - the rider can exit on its own again"


def test_the_gate_is_at_the_call_site_so_the_arithmetic_stays_tested():
    """trail_level() must stay PURE, as its docstring promises.

    Gating inside it broke all six of its arithmetic tests - the tell that it was the wrong place.
    Those tests are what will still guard the rule on the day the operator switches it back on, so
    the function must keep computing a real level when asked directly.
    """
    assert dr.trail_level(1, 29000.0, 29400.0, 10.0) is not None, (
        "trail_level() is no longer pure - its own tests can no longer guard the rule")
    assert re.search(r"tl\s*=\s*trail_level\([^)]*\)\s*if\s+USE_TRAIL_EXIT\s+else\s+None", _src()), (
        "the live call site no longer gates on USE_TRAIL_EXIT")


def test_the_readout_does_not_claim_the_trail_is_merely_unarmed():
    '''"not armed" implies a level is coming that never will - the 08-13 readout-lied bug reborn.'''
    assert "NO TRAIL" in _src(), "the state note still reports the trail as pending"


# ── what must SURVIVE ────────────────────────────────────────────────────────

def test_the_2040_hard_flat_survives():
    """!! THE ONE THAT MATTERS. "NEVER HOLD OVERNIGHT. EVER." is absolute, and with no trail and no
    stop this clock is the ONLY thing standing between a naked 4-lot position and the halt.

    It is not a discretionary exit and was never in scope for "turn the exits off"; if it is ever
    removed, that must be a deliberate, separate operator decision - not a side effect of this one.
    """
    assert dr.FLAT_UTC_MIN == 20 * 60 + 40, "the hard flat moved off 20:40Z"
    assert dr.hard_flat_window(dr.FLAT_UTC_MIN) is True, "the hard flat no longer fires at 20:40Z"
    assert 'out["exit_reason"] = "CLOCK_FLAT"' in _src(), "the CLOCK_FLAT exit path is gone"


def test_the_four_take_profit_levels_survive():
    """The ladder IS the exit now. Four levels, cascading, per-lot."""
    assert 'out["exit_reason"] = "LADDER_COMPLETE"' in _src(), "the ladder completion path is gone"
    src = _src()
    assert "targets_done" in src and "manual_targets_pt" in src


def test_the_operators_own_exits_survive():
    """The claim buttons and the SELL button are HIS hands - the desk's best-evidenced exit."""
    src = _src()
    assert 'out["exit_reason"] = "MANUAL_CLAIM"' in src, "the claim path is gone"
    assert 'out["exit_reason"] = "OPERATOR_SELL"' in src, "the manual SELL path is gone"


def test_the_reversal_ASK_survives_because_it_never_sells():
    """should_ask_exit() only ever RAISES A QUESTION - default is hold, max three pushes, never an
    auto-sell. Keeping it is what makes "the rest is up to me" workable: it is how a genuine
    reversal reaches the operator instead of passing unnoticed. It is not an exit and so was not
    switched off; pinned here so that stays a conscious choice.
    """
    assert hasattr(dr, "should_ask_exit")
    assert dr.should_ask_exit(1, 29000.0, 29400.0, 29380.0, 10.0) is True, (
        "a 2xATR reversal from the peak no longer reaches the operator")
    src = _src()
    assert "EXIT_ASK_MAX_PUSHES" in src and "never escalate to a sell" in src
