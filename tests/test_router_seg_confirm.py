"""SATURDAY #1 — the router's direction-confirmation state machine, pinned.

The hysteresis lived inline in the tick body and was therefore unpinned, which is how the 08-11
flicker bug reached production: five confirmed UP reads undone by ONE marginal tick, benching
abs_veto_short at 01:00 and re-arming it at 01:30. These tests exist so a timing change cannot
quietly become a different rule.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from router_tick_durable import seg_confirm  # noqa: E402

HOLD = 3


def _chain(raws, hold=HOLD, fresh=True):
    """Feed a sequence of raw reads through the machine, returning every state."""
    st, out = None, []
    for r in raws:
        st = seg_confirm(st, r, fresh if st is not None else False, hold)
        out.append(st)
    return out


def test_entering_a_direction_costs_exactly_HOLD_agreeing_ticks():
    s = _chain(["UP", "UP", "UP"])
    assert [x["agree"] for x in s] == [1, 2, 3]
    assert [x["conf"] for x in s] == [False, False, True], \
        "a direction must NOT be confirmed before HOLD consecutive agreeing ticks"


def test_a_broken_chain_restarts_the_count():
    s = _chain(["UP", "UP", "FLAT", "UP", "UP"])
    assert [x["agree"] for x in s] == [1, 2, 1, 1, 2]
    assert not any(x["conf"] for x in s), "two runs of two must not add up to a confirmation"


def test_leaving_a_confirmed_direction_ALSO_costs_HOLD_ticks():
    """The symmetry is the whole point — this is the 08-11 bug's regression test."""
    s = _chain(["UP", "UP", "UP", "DOWN", "DOWN", "DOWN"])
    assert s[2]["conf"] and s[2]["dir"] == "UP"
    assert s[3]["dir"] == "UP" and s[3]["held"], "dissent 1 must HOLD the confirmed direction"
    assert s[4]["dir"] == "UP" and s[4]["held"], "dissent 2 must still hold at HOLD=3"
    assert s[5]["dir"] == "DOWN" and not s[5]["conf"], \
        "the HOLD-th dissent releases — and the NEW direction is not itself confirmed yet"


def test_a_single_dissent_does_not_flip_a_confirmed_direction():
    s = _chain(["UP", "UP", "UP", "DOWN", "UP"])
    assert s[3]["held"] and s[3]["dir"] == "UP"
    assert s[4]["dir"] == "UP", "the marginal tick must be absorbed, not acted on"


def test_a_STALE_previous_tick_cannot_be_chained_from():
    """A gap in the ticks means the chain is broken; confirmation must start again."""
    st = seg_confirm({"dir": "UP", "conf": True, "dissent": 0, "agree": 3}, "UP",
                     False, HOLD)          # fresh=False -> the previous tick is too old
    assert st["agree"] == 1 and not st["conf"]


def test_FLAT_never_confirms_no_matter_how_long_it_persists():
    s = _chain(["FLAT"] * 6)
    assert not any(x["conf"] for x in s), "FLAT is the absence of a direction, not a direction"


def test_HOLD_2_reproduces_the_PREVIOUS_behaviour():
    """The change must be a parameter, not a rewrite — HOLD=2 is what ran until 2026-08-16."""
    s = _chain(["UP", "UP"], hold=2)
    assert s[1]["conf"], "at HOLD=2 two agreeing ticks confirmed, and must still"
    s2 = _chain(["UP", "UP", "DOWN", "DOWN"], hold=2)
    assert s2[2]["held"] and s2[3]["dir"] == "DOWN"


def test_the_live_constants_are_what_SATURDAY_1_ASKED_FOR():
    """Pins the shipped values so a later edit is a deliberate act, not a drift."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "scripts", "router_tick_durable.py")).read()
    assert "SEG_WINDOW_MIN = 45" in src, "window must be 45 min (was 60)"
    assert "SEG_HOLD = 3" in src, "hold must be 3 ticks (was 2)"
    assert "SEG_NET_MIN = 40.0" in src
