"""Pins the stop-width A/B invariants (★2026-08-04).

The experiment is only meaningful if the two arms differ in EXACTLY ONE variable. The failure mode is
silent and plausible-looking, so it is pinned rather than trusted: exit_scalp puts the target at
`target_r * (stop_atr_mult * atr)`, so raising the stop to 2.0 also doubles the profit target unless
decouple_target undoes it. A drift here would produce a tidy-looking result for a different experiment.
"""
from __future__ import annotations

import pytest

from gazbot7.deciders import Position, exit_scalp
from gazbot7.shadow import ShadowVariant, _eff_target_r, default_slate

VPP = 2.0
# ★2026-08-15 THE TRIM retired sw_grind_* (stop width on grind: answered, every rung negative) and
# sw_absL_* (too slow to settle). These invariants now guard the arms that SURVIVED — the abs_veto
# short quartet. Do not re-add a name here without re-arming it in default_slate: the parametrisation
# is derived from the live slate below precisely so the two cannot drift apart again.
PAIRS = ["absS_A", "absS_B"]


def _slate():
    return {v.name: v for v in default_slate()}


def test_both_arms_exist_for_every_pair():
    s = _slate()
    for p in PAIRS:
        assert f"sw_{p}_k10" in s, f"control arm missing for {p}"
        assert f"sw_{p}_k20" in s, f"test arm missing for {p}"


@pytest.mark.parametrize("pair", PAIRS)
@pytest.mark.parametrize("atr", [8.0, 15.0, 21.9, 22.0, 30.0, 45.0])
def test_arms_differ_only_in_stop_width(pair, atr):
    """THE core invariant: same target in POINTS at every ATR, 2x the stop. Both sides of the
    clip_atr_split boundary are checked because the clip changes which target formula applies."""
    s = _slate()
    a, b = s[f"sw_{pair}_k10"], s[f"sw_{pair}_k20"]

    assert a.stop_atr_mult == 1.0 and b.stop_atr_mult == 2.0
    assert b.stop_atr_mult == 2.0 * a.stop_atr_mult

    # everything that is not the stop must match
    for f in ("gate", "params", "side", "confirm_s", "target_r", "qty", "chandelier", "chand_lock",
              "chand_start_k", "lock_r", "lock_k", "clip_atr_split", "clip_a_usd", "clip_b_r",
              "clip_b_floor_usd", "decouple_target"):
        assert getattr(a, f) == getattr(b, f), f"{pair}: {f} differs between arms"

    if a.chandelier:
        return   # chandelier arms have no R-target to compare
    # the target, in POINTS, must be identical despite the different stop
    ta = _eff_target_r(a, atr, VPP) * a.stop_atr_mult * atr
    tb = _eff_target_r(b, atr, VPP) * b.stop_atr_mult * atr
    assert ta == pytest.approx(tb), f"{pair} @ATR{atr}: target moved with the stop ({ta} vs {tb})"


@pytest.mark.parametrize("pair", PAIRS)
def test_wider_stop_actually_stops_later(pair):
    """The stop must really be twice as far — the decoupling must not accidentally neutralise it."""
    s = _slate()
    a, b = s[f"sw_{pair}_k10"], s[f"sw_{pair}_k20"]
    atr, entry = 20.0, 29000.0
    pos_a = Position("LONG" if a.side != "SHORT" else "SHORT", entry, atr, 0.0)
    # a price 1.5 ATR offside: stops the 1.0x arm, must NOT stop the 2.0x arm
    px = entry - 1.5 * atr if pos_a.side == "LONG" else entry + 1.5 * atr
    ra = exit_scalp(pos_a, px, target_r=_eff_target_r(a, atr, VPP), stop_atr_mult=1.0)
    rb = exit_scalp(pos_a, px, target_r=_eff_target_r(b, atr, VPP), stop_atr_mult=2.0)
    assert ra == "STOP", f"{pair}: 1.0x arm should stop at 1.5 ATR offside"
    assert rb != "STOP", f"{pair}: 2.0x arm should still be alive at 1.5 ATR offside"


def test_decouple_is_opt_in_so_legacy_variants_are_untouched():
    """Every pre-existing variant must keep the old coupled behaviour — this change must not
    retroactively alter sims that have been accumulating history."""
    # sw_ = stop-width A/B, cx_ = clip A/B. Both are NEW arms built to use decoupling deliberately;
    # the guard is about not retroactively altering variants that have been accumulating history.
    for v in default_slate():
        if not v.name.startswith(("sw_", "cx_")):
            assert v.decouple_target is False, f"{v.name} unexpectedly decoupled"
            assert _eff_target_r(v, 17.0, VPP) == v.target_r


def test_clip_applies_below_split_only():
    v = ShadowVariant("t", "thrust", {}, target_r=2.5, decouple_target=True,
                      clip_atr_split=22.0, clip_a_usd=40.0)
    # below the split: the $40 cash clip wins -> 20pt at $2/pt
    assert _eff_target_r(v, 10.0, VPP) * 10.0 == pytest.approx(20.0)
    # at/above the split: back to the R-target
    assert _eff_target_r(v, 30.0, VPP) * 30.0 == pytest.approx(2.5 * 30.0)


# ── CLIP A/B (★2026-08-04) ──────────────────────────────────────────────────────────────────────
# ★2026-08-15 cx_absLA and cx_absSB retired (see RETIRED_2026_08_15); the grindA pair survives
# because it validates the LIVE quiet-tape clip.
CLIP_PAIRS = ["grindA"]


@pytest.mark.parametrize("pair", CLIP_PAIRS)
def test_clip_arms_differ_only_in_the_clip(pair):
    s = _slate()
    a, b = s[f"cx_{pair}_live"], s[f"cx_{pair}_clip"]
    for f in ("gate", "params", "side", "confirm_s", "target_r", "qty", "stop_atr_mult",
              "atr_max", "chandelier", "decouple_target"):
        assert getattr(a, f) == getattr(b, f), f"{pair}: {f} differs — not a clean A/B"
    assert a.clip_atr_split == 0.0, "the LIVE arm must carry no clip"
    assert b.clip_atr_split == 22.0, "the CLIP arm must carry the clip"


@pytest.mark.parametrize("pair", CLIP_PAIRS)
def test_clip_arm_actually_changes_the_target(pair):
    """A clip that never bites would make the A/B a null test that looks like a real one."""
    s = _slate()
    a, b = s[f"cx_{pair}_live"], s[f"cx_{pair}_clip"]
    diffs = 0
    for atr in (9.0, 12.0, 16.0, 21.0):
        ta = _eff_target_r(a, atr, VPP) * a.stop_atr_mult * atr
        tb = _eff_target_r(b, atr, VPP) * b.stop_atr_mult * atr
        if abs(ta - tb) > 1e-9:
            diffs += 1
    assert diffs >= 3, f"{pair}: clip barely changes the target — the A/B would measure nothing"


@pytest.mark.parametrize("pair", CLIP_PAIRS)
def test_clip_arms_are_restricted_to_the_regime_under_test(pair):
    """Above atr_split the clip is inactive, so entries there are identical and pure noise in the
    delta. Both arms must carry the same ceiling or one arm gets trades the other cannot."""
    s = _slate()
    a, b = s[f"cx_{pair}_live"], s[f"cx_{pair}_clip"]
    assert a.atr_max == b.atr_max == 22.0


def test_atr_max_is_opt_in_so_legacy_variants_are_unrestricted():
    for v in default_slate():
        if not v.name.startswith("cx_"):
            assert v.atr_max == 0.0, f"{v.name} unexpectedly regime-restricted"



def test_the_parametrisation_matches_the_LIVE_slate():
    """The invariants above are only worth anything if they cover what is actually armed.

    These lists were hand-written and the slate was trimmed underneath them, which is how a suite
    ends up asserting hard about arms that no longer exist — and, worse, silently NOT asserting
    about arms that do. This test is the interlock: if someone re-arms or retires a stop-width or
    clip arm without touching PAIRS/CLIP_PAIRS, it fails here rather than going unnoticed.
    """
    from gazbot7.shadow import default_slate

    live = {v.name for v in default_slate()}
    assert {f"sw_{p}_k{k}" for p in PAIRS for k in (10, 20)} <= live, \
        "PAIRS names an arm that is no longer in the slate"
    assert {f"cx_{p}_{s}" for p in CLIP_PAIRS for s in ("clip", "live")} <= live, \
        "CLIP_PAIRS names an arm that is no longer in the slate"
    # and nothing armed is left unguarded
    armed_sw = {v.name.rsplit("_k", 1)[0].removeprefix("sw_")
                for v in default_slate() if v.name.startswith("sw_")}
    assert armed_sw == set(PAIRS), f"stop-width arms not covered by PAIRS: {armed_sw ^ set(PAIRS)}"
