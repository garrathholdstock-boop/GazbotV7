"""The benched rgv_short gate must have a shadow twin, and the twin must not drift from it.

★★★2026-08-18. Operator: "why doesnt router arm rgv short on days like today". It has been off
since a STANDING 07-31 VERDICT — "benched for the week, verdicted SHADOW (11 fires, -$142, negative
at every exit rung)" — which the router still quotes on every tick eighteen days later. Meanwhile the
rg_short_* twins were all retired on 08-15, so the gate could neither trade nor be shadowed: no live
evidence, no counterfactual, an n=11 verdict frozen in place.

[[never-kill-a-lead-that-has-a-glimmer]]: every lead ends LIVE / SHADOW / PARKED / REFUTED.
"Benched with nothing watching" is not one of the four, and this test is what keeps it out of limbo.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.shadow import default_slate  # noqa: E402
from gazbot7.slot_strategy import _RGV_SHORT, scaleout_slots  # noqa: E402

NAME = "rgv_short_live_mirror"


def _mirror():
    m = [v for v in default_slate() if v.name == NAME]
    assert m, f"{NAME} is not armed — the bench on rgv_short is unpriced again"
    return m[0]


def test_the_benched_gate_has_a_twin():
    assert _mirror().gate == "reversal_grab"


def test_entry_params_track_the_LIVE_gate_and_cannot_drift():
    """★ THE ONE THAT MATTERS. A mirror that COPIES the dict stops mirroring the moment the live
    gate is retuned — the same two-surfaces drift that put the wrong sim number on the dashboard.
    This asserts identity with the live source, not equality with a snapshot."""
    assert _mirror().params == {"side": "SHORT", **_RGV_SHORT}


def test_the_exit_matches_the_RESOLVED_live_lot_A():
    """★ THE ONE THAT ALREADY EARNED ITS KEEP. The mirror was first written at 2.0R by reading
    SlotSpec("rgv_short", ... target_r=2.0) in SOURCE. scaleout_slots() RESOLVES to rgv_short_A at
    1.5R plus a chandelier B at 2.0, so source-reading shadowed an exit the desk does not run.
    CLAUDE.md trap #3: verify via scaleout_slots(), never source."""
    a = [s for s in scaleout_slots() if s.tag == "rgv_short_A"]
    assert a, "live rgv_short_A vanished from the slate"
    m = _mirror()
    assert m.target_r == a[0].target_r == 1.5
    assert m.stop_atr_mult == a[0].stop_atr_mult


def test_lot_B_is_knowingly_not_mirrored():
    """Lot B rides a chandelier. Mirroring only A is a CHOICE, and the arm must not be read as the
    whole gate's P&L — pin it so a future reader cannot mistake one leg for two."""
    b = [s for s in scaleout_slots() if s.tag == "rgv_short_B"]
    assert b and b[0].exit == "chandelier"
    assert _mirror().chandelier is False


def test_it_is_short_only():
    """A two-sided mirror would price a bench that does not exist on the long side."""
    assert _mirror().params["side"] == "SHORT"


def test_it_carries_the_live_atr_floor():
    """atr_min 20.0 is the 07-25 rehab. Mirroring without it would shadow a different gate."""
    assert _mirror().params["atr_min"] == 20.0


def test_it_has_a_permanent_registry_number():
    """It must be referable by number on the board, not render as '#?' in a group called '?'."""
    import json
    reg = json.load(open(os.path.join(os.path.dirname(__file__), "..",
                                      "data", "sim_registry.json")))["ids"]
    assert NAME in reg and isinstance(reg[NAME], int)


def test_the_dashboard_can_name_it():
    page = open(os.path.join(os.path.dirname(__file__), "..", "src", "gazbot7",
                             "web_static", "shadow.html"), encoding="utf-8").read()
    assert f"{NAME}:{{n:" in page, "no META entry — it would render in the '?' family"
