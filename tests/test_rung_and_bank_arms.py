"""BUILD #13 (the MED-TREND rung) and BUILD #18 (bank Lot A at a fixed +20 points).

Both add a NEW field to ShadowVariant, and both are the kind of thing that fails silently: an ER band
that is never applied turns a per-rung result into a blanket one, and a fixed-points target expressed
as an R-multiple quietly reintroduces the ATR scaling the hypothesis denies.

⚠ The er_min/er_max check calls efficiency_ratio, which shadow.py does NOT import globally. The first
version relied on a module-level name that was not there — the fourth NameError of this class in one
day, and the reason these tests exercise the path rather than reading it.
"""
from gazbot7.shadow import ShadowVariant, _eff_target_r, default_slate

VPP = 2.0


def _by(name):
    return next(v for v in default_slate() if v.name == name)


# ── BUILD #18 ───────────────────────────────────────────────────────────────────────────────────
def test_a_fixed_points_target_does_NOT_scale_with_ATR():
    """The entire hypothesis. If this scales, the arm is testing an R-multiple wearing a points label."""
    v = ShadowVariant("t", "grind", {}, target_pt=20.0, stop_atr_mult=1.0, qty=1.0)
    for atr in (8.0, 20.0, 45.0):
        tr = _eff_target_r(v, atr, VPP)
        assert abs(tr * v.stop_atr_mult * atr - 20.0) < 1e-9, f"target moved at ATR {atr}"


def test_target_pt_falls_back_rather_than_inventing_a_conversion():
    v = ShadowVariant("t", "grind", {}, target_pt=20.0, target_r=2.5, stop_atr_mult=1.0)
    assert _eff_target_r(v, 0.0, VPP) == 2.5, "no usable ATR -> no honest points conversion"


def test_the_bank_arm_ships_with_its_control():
    """+$219.50 but -$45.00 stripped of its best three — thin enough that an uncontrolled arm would
    tell us nothing. The control is the live Lot A target on the same entries."""
    a, c = _by("bank20_grindA"), _by("bank20_grindA_ctl")
    assert a.target_pt == 20.0 and c.target_pt == 0.0
    assert a.gate == c.gate and a.side == c.side and a.params == c.params
    assert c.target_r == 2.5, "the control must be the LIVE Lot A target"


def test_every_legacy_arm_is_untouched_by_target_pt():
    for v in default_slate():
        if not v.name.startswith("bank20"):
            assert v.target_pt == 0.0, f"{v.name} unexpectedly has a points target"


# ── BUILD #13 ───────────────────────────────────────────────────────────────────────────────────
def test_the_rung_arms_carry_their_OWN_band():
    """A rung's numbers without its band is the proposal averaged over regimes it was never graded
    in — which is how a per-regime result gets quietly converted into a blanket one.
    MED-TREND is ER30 in [0.30, 0.50) per exit_ladder_lab_v2's classifier."""
    for n in ("rung_grindA_med_05", "rung_grindB_med_10", "rung_grindA_med_live"):
        v = _by(n)
        assert (v.er_min, v.er_max) == (0.30, 0.50), f"{n} is not banded to MED-TREND"


def test_the_rung_ships_with_a_SAME_BAND_control():
    """Otherwise the rung and the ladder are confounded: a difference could be either."""
    a, c = _by("rung_grindA_med_05"), _by("rung_grindA_med_live")
    assert (a.er_min, a.er_max) == (c.er_min, c.er_max)
    assert a.target_r == 0.5 and c.target_r == 2.5


def test_the_ER_BAND_IS_ACTUALLY_APPLIED_at_entry():
    """The silent-failure guard. A band that is declared but never evaluated leaves the arm running
    everywhere, and its result would read as the rung's."""
    import inspect

    from gazbot7.shadow import ShadowSim
    src = inspect.getsource(ShadowSim._entry)
    assert "er_min" in src and "er_max" in src, "the band must be tested at entry, not just declared"
    assert "efficiency_ratio" in src, "and it must use the same ER the rung classifier uses"


def test_no_legacy_arm_has_a_band():
    for v in default_slate():
        if not v.name.startswith("rung_"):
            assert (v.er_min, v.er_max) == (0.0, 0.0), f"{v.name} unexpectedly ER-restricted"
