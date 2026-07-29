"""Dual-slot SCALE-OUT slate (2026-07-29 operator): every gate → two 1-lot sub-slots that both
fire on the same signal — Lot A a fixed-R scalp (guaranteed floor), Lot B a chandelier (the tail).
Big-run gates: A@2.5R + B wide lock-chandelier. Faders: A@1.5R + B tight k1.5 chandelier."""

from __future__ import annotations

from gazbot7.deciders import Features
from gazbot7.slot_strategy import SlotStrategy, scaleout_slots
from gazbot7.slotbook import SlotBook
from gazbot7.tournament import _base

VPP = 2.0
_BASES = {"grind_long", "capitulation_long", "abs_veto_long", "rgv_short", "exhaustion_short", "abs_veto_short"}
_BIG = {"grind_long", "abs_veto_short", "abs_veto_long", "exhaustion_short"}


def _by_tag():
    return {s.tag: s for s in scaleout_slots()}


def test_slate_is_12_sub_slots_two_per_base_gate():
    specs = scaleout_slots()
    assert len(specs) == 12
    tags = {s.tag for s in specs}
    for base in _BASES:
        assert f"{base}_A" in tags and f"{base}_B" in tags


def test_big_run_gates_A_is_2p5R_scalp_B_is_wide_lock_chandelier():
    d = _by_tag()
    for base in _BIG:
        a, b = d[f"{base}_A"], d[f"{base}_B"]
        assert a.exit == "scalp" and a.target_r == 2.5 and a.base_size == 1
        assert b.exit == "chandelier_lock" and b.lock_r == 6.0 and b.lock_k == 0.5 and b.chandelier_start_k == 3.5
        assert b.base_size == 1


def test_fader_gates_A_is_1p5R_scalp_B_is_tight_k1p5_chandelier():
    d = _by_tag()
    for base in ("rgv_short", "capitulation_long"):
        a, b = d[f"{base}_A"], d[f"{base}_B"]
        assert a.exit == "scalp" and a.target_r == 1.5
        assert b.exit == "chandelier" and b.chandelier_start_k == 1.5 and b.vol_adaptive_chandelier is False


def test_sub_slots_inherit_base_entry_config_and_disable_adaptive():
    d = _by_tag()
    # exhaustion keeps its counter-regime entry veto on BOTH lots; adaptive_exit off (explicit exit wins)
    for tag in ("exhaustion_short_A", "exhaustion_short_B"):
        assert d[tag].veto_counter_regime is True
        assert d[tag].adaptive_exit is False
        assert d[tag].kind == "exhaustion" and d[tag].side == "SHORT"
    # thrust params + side inherited; giveback off; flat sizing 1 lot each
    for tag in ("abs_veto_short_A", "abs_veto_short_B"):
        assert d[tag].params.get("thr") == 1.5 and d[tag].side == "SHORT"
        assert d[tag].sizing == "flat" and d[tag].base_size == 1 and d[tag].giveback_enabled is False


def test_base_helper_strips_suffix_for_benching_and_veto():
    assert _base("exhaustion_short_A") == "exhaustion_short"
    assert _base("abs_veto_long_B") == "abs_veto_long"
    assert _base("exhaustion_short") == "exhaustion_short"   # non-dual tag unchanged
    assert _base("") == ""


def test_a_base_name_bench_disables_BOTH_sub_slots():
    # the tournament disables an OPEN when its slot OR its base is in the switch set
    disabled = {"exhaustion_short"}              # operator/trial benches by BASE name
    for tag in ("exhaustion_short_A", "exhaustion_short_B"):
        assert (tag in disabled) or (_base(tag) in disabled)
    # a granular tag-level bench hits only that lot
    disabled = {"exhaustion_short_A"}
    assert ("exhaustion_short_A" in disabled) or (_base("exhaustion_short_A") in disabled)
    assert not (("exhaustion_short_B" in disabled) or (_base("exhaustion_short_B") in disabled))


def test_one_signal_opens_BOTH_lots_of_that_gate():
    specs = scaleout_slots()
    book = SlotBook([s.tag for s in specs], value_per_point=VPP, fee_rt=1.5)
    strat = SlotStrategy(specs, value_per_point=VPP)
    f = Features(price=29000.0, atr=20.0, atr_pct=20.0/29000, vwap=29000.0-1.0*20, vwap_slope_atr=0.5,
                 ext_atr=1.0, net_atr_5=0.0, vol_surge=False, n_bars=60, net_atr_2=0.0, vwap_slope_fast=0.5)
    opens = [i for i in strat.decide(f, 29000.0, [], book, tape_net=100.0) if i["action"] == "OPEN"]
    slots = {i["slot"] for i in opens}
    # grind LONG signal opens BOTH grind_long sub-lots and NO short/other-long lots
    assert "grind_long_A" in slots and "grind_long_B" in slots
    assert not any(s.startswith("grind_short") or s.startswith("rgv_short") for s in slots)
