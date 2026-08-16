"""BUILD #16 — the quiet-tape clip stands down on a range-break ignition.

The clip exists because quiet tape does not pay a full R-target. A range break is the one quiet setup
that CAN run, so clipping it may be cutting the exact move the clip was never aimed at.

★ BRK IS THE REPORT'S DEFINITION, NOT MINE (gf_chop_scalp §2, the regime taxonomy): "block closes
outside the prior 2h high/low". A hand-rolled break test would make this arm answer a different
question from the one that was asked.
"""
from gazbot7.shadow import ShadowVariant, _brk_2h, _eff_target_r, default_slate

VPP = 2.0


class _B:
    def __init__(self, h, l):
        self.high, self.low = h, l


def _bars(n=130, hi=100.0, lo=90.0):
    return [_B(hi, lo) for _ in range(n)]


def test_brk_excludes_the_current_bar():
    """A bar cannot break a level it is itself setting — the same circularity detect_break() guards."""
    bars = _bars()
    assert _brk_2h(bars, 101.0) is True
    assert _brk_2h(bars, 89.0) is True
    assert _brk_2h(bars, 95.0) is False


def test_brk_needs_history_and_claims_nothing_without_it():
    assert _brk_2h([], 100.0) is False
    assert _brk_2h(_bars(n=10), 999.0) is False, "too little history must not assert a break"


def test_the_standdown_restores_the_FULL_target_only_on_a_break():
    v = next(x for x in default_slate() if x.name == "cx_clip_brk_standdown")
    clipped = _eff_target_r(v, 15.0, VPP, brk=False)
    full = _eff_target_r(v, 15.0, VPP, brk=True)
    assert full == v.target_r, "a range-break ignition must keep the full R-target"
    assert clipped < full, "and a non-break must still be clipped"


def test_the_control_is_the_clip_AS_IT_RUNS_LIVE():
    a = next(x for x in default_slate() if x.name == "cx_clip_brk_live")
    b = next(x for x in default_slate() if x.name == "cx_clip_brk_standdown")
    assert a.clip_standdown_on_brk is False and b.clip_standdown_on_brk is True
    for f in ("gate", "side", "target_r", "stop_atr_mult", "clip_atr_split", "clip_a_usd", "atr_max"):
        assert getattr(a, f) == getattr(b, f), f"{f} differs — the pair must vary ONLY in the stand-down"
    assert a.atr_max == 22.0, "both must run only where the clip is actually live"


def test_the_live_arm_is_never_stood_down_even_on_a_break():
    a = next(x for x in default_slate() if x.name == "cx_clip_brk_live")
    assert _eff_target_r(a, 15.0, VPP, brk=True) == _eff_target_r(a, 15.0, VPP, brk=False)


def test_no_other_arm_stands_down():
    for v in default_slate():
        if v.name != "cx_clip_brk_standdown":
            assert v.clip_standdown_on_brk is False, f"{v.name} unexpectedly stands the clip down"


def test_brk_is_stamped_at_ENTRY_not_recomputed_at_exit():
    """Recomputing later reads a different 2h window and could flip the answer mid-trade."""
    import inspect

    from gazbot7.shadow import ShadowSim
    src = inspect.getsource(ShadowSim._open_pos)
    assert "_brk_2h" in src and "brk=brk" in src
