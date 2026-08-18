"""rider_w5 must carry the 120-minute cap its own spec and its own lab engine enforce.

★★★2026-08-18. The Friday spec is "BOARD(w=5, k=2.0), 13:00-20:00Z, stop 3.0xATR, target 6.0xATR,
120min, floors OFF" and gf_rider_engine caps every race (`i1 = min(n, i0 + cap_min * 12)`). The
shipped variant had time_cap_s=0.0 — NO CLOCK.

With a 3xATR stop, a 6xATR target and ONE POSITION AT A TIME, an uncapped trade holds until one of
them prints and blocks re-entry for the rest of the session. On 08-18 the gate was true on 32
minutes and produced ONE trade, against NINE on 08-17 when every hold happened to close inside an
hour. This is the SECOND constraint this arm shipped without — the 15-minute cooldown was the first,
and its own comment already said "every number quoted for this leg came from the CONSTRAINED
version". Both are now restored.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.shadow import default_slate  # noqa: E402


def _w5():
    return [v for v in default_slate() if v.name == "rider_w5"][0]


def test_the_120_minute_cap_is_present():
    assert _w5().time_cap_s == 120 * 60, "the lab capped every race at cap_min; the arm must too"


def test_the_other_constraint_is_still_there_too():
    """Restoring one and losing the other would just move the bug."""
    assert _w5().params.get("cooldown_min") == 15


def test_the_graded_shape_is_unchanged():
    """The cap must not be smuggled in alongside a quiet change to the measured cell."""
    v = _w5()
    assert v.stop_atr_mult == 3.0
    assert v.target_r == 2.0                      # 2.0R on a 3xATR stop = the spec's 6.0xATR
    assert v.chandelier is False                  # every chandelier variant tested RED
    assert "rvol_min" not in v.params and "atr_pr_min" not in v.params   # floors OFF for w=5
    assert v.params["hh_lo"] == 13.0 and v.params["hh_hi"] == 20.0


def test_every_capped_arm_declares_a_positive_cap():
    """A 0.0 cap on an arm whose research capped it is the defect — catch the next one generically."""
    for v in default_slate():
        if v.time_cap_s:
            assert v.time_cap_s > 0, v.name
