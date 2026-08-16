"""BUILD #3 — the router's leakage detector, which reported $0 while money leaked.

Two faults were alleged. The narrow universe was already fixed by adding exhaustion_short to UP_OFF
on 08-15 (MANAGED = DOWN_OFF | UP_OFF | CHOP_OFF, so it is now all six gates). The two that were NOT:

★★ IT COULD NOT SEE A SINGLE TRADE. `trades.gate` holds the SLOT TAG ('exhaustion_short_A') since
the dual-slot scale-out went live 2026-07-29; `MANAGED` holds BASE names. `g in MANAGED` therefore
matched nothing from the current book, and the detector printed a confident $0 on 08-11, 08-12 and
08-13 — days the desk demonstrably lost money.

★ IT SCORED THE GATE, NOT THE ROUTER. Every managed-gate loser counted, so a gate losing in a regime
the router correctly left it ON in was booked as router failure. The desk's standing rule is that no
rule lets the router bench a gate that is simply bleeding.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7 import direction_router as dr           # noqa: E402
from gazbot7.tournament import _base                 # noqa: E402


def test_the_universe_is_every_gate_the_router_controls():
    assert dr.MANAGED == dr.DOWN_OFF | dr.UP_OFF | dr.CHOP_OFF
    assert "exhaustion_short" in dr.MANAGED, "the gate the -$241 leaked through must be in scope"
    assert len(dr.MANAGED) == 6, sorted(dr.MANAGED)


def test_slot_tags_resolve_to_base_gates():
    """The regression for the three-week blindness: a slot tag must land inside MANAGED."""
    for tag in ("exhaustion_short_A", "exhaustion_short_B", "grind_long_A", "abs_veto_short_B"):
        assert _base(tag) in dr.MANAGED, f"{tag} would be invisible to the detector"
    assert _base("exhaustion_short") == "exhaustion_short", "a bare gate name must pass through"


def test_leakage_means_the_ROUTERS_rule_said_OFF():
    """Rebuilt here rather than imported: the predicate lives inside main() in the script."""
    CHOP_EXEMPT = {"abs_veto_short"}

    def should_be_off(gate, regime):
        if regime == "TREND_UP":
            return gate in dr.UP_OFF
        if regime == "TREND_DOWN":
            return gate in dr.DOWN_OFF
        if regime == "CHOP":
            return gate in dr.CHOP_OFF and gate not in CHOP_EXEMPT
        return False

    # the 08-12 case the detector now catches: a short fader firing into a confirmed up-trend
    assert should_be_off("exhaustion_short", "TREND_UP")
    # ... and the case it must NOT call leakage: the same gate in chop, where its rule says ON
    assert not should_be_off("exhaustion_short", "CHOP")
    # momentum in chop IS benched by rule
    assert should_be_off("grind_long", "CHOP")
    # ⚠ except the carve-out — abs_veto_short is exempt from the chop bench by operator decision
    assert not should_be_off("abs_veto_short", "CHOP"), \
        "flagging the exempt gate would argue nightly for benching what the evidence says to keep"
    # an unknown/flat regime benches nothing
    assert not should_be_off("grind_long", "FLAT")
