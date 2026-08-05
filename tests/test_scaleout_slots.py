"""Dual-slot SCALE-OUT slate (2026-07-29 operator): every gate → two 1-lot sub-slots that both
fire on the same signal — Lot A a fixed-R scalp (guaranteed floor), Lot B a chandelier (the tail).
Big-run gates: A@2.5R + B wide lock-chandelier. Faders: A@1.5R + B tight k1.5 chandelier."""

from __future__ import annotations

import pytest

from gazbot7 import slot_strategy as _ss
from gazbot7.deciders import NIPC_FLAT_BY_S, NIPC_HOLD_CAP_S, Features
from gazbot7.slot_strategy import SlotStrategy, scaleout_slots
from gazbot7.slotbook import SlotBook
from gazbot7.tournament import _base

VPP = 2.0
_BASES = {"grind_long", "capitulation_long", "abs_veto_long", "rgv_short", "exhaustion_short", "abs_veto_short"}
_BIG = {"grind_long", "abs_veto_short", "abs_veto_long", "exhaustion_short"}


def _by_tag():
    return {s.tag: s for s in scaleout_slots()}


@pytest.fixture
def defaults(monkeypatch):
    """★2026-08-01 (audit FIX): the built-in-DEFAULT tests below used to call scaleout_slots()
    straight, which reads the OPERATOR'S LIVE data/exit_overrides.json off an absolute path. They
    therefore asserted the built-in default while measuring the live override, and had been RED at
    HEAD (abs_veto_long carries an override, so Lot A was 1.5R not 2.5R) — a pre-existing failure
    that masked today's. Point the loader at a path that cannot exist so "default" means default.
    The live file gets its own explicit test (test_live_exit_overrides_produce_the_intended_slate).
    Revert: delete the fixture and its uses."""
    monkeypatch.setattr(_ss, "_EXIT_OVERRIDES_PATH", "/nonexistent/exit_overrides.json")
    return {s.tag: s for s in scaleout_slots()}


def test_slate_is_12_sub_slots_two_per_base_gate():
    specs = scaleout_slots()
    assert len(specs) == 16   # ★2026-08-01: 8 base gates × 2 sub-slots (+ nipc_long / nipc_short)
    tags = {s.tag for s in specs}
    for base in _BASES:
        assert f"{base}_A" in tags and f"{base}_B" in tags


def test_big_run_gates_A_is_2p5R_scalp_B_is_wide_lock_chandelier(defaults):
    for base in _BIG:
        a, b = defaults[f"{base}_A"], defaults[f"{base}_B"]
        assert a.exit == "scalp" and a.target_r == 2.5 and a.base_size == 1
        assert b.exit == "chandelier_lock" and b.lock_r == 6.0 and b.lock_k == 0.5 and b.chandelier_start_k == 3.5
        assert b.base_size == 1


def test_fader_gates_A_is_1p5R_scalp_B_is_tight_k1p5_chandelier(defaults):
    for base in ("rgv_short", "capitulation_long"):
        a, b = defaults[f"{base}_A"], defaults[f"{base}_B"]
        assert a.exit == "scalp" and a.target_r == 1.5
        assert b.exit == "chandelier" and b.chandelier_start_k == 1.5 and b.vol_adaptive_chandelier is False


def test_nipc_falls_back_to_its_PROVEN_pair_not_the_BIG_RUN_or_FADER_default(defaults):
    # ★2026-08-01: nipc is in NEITHER _BIG_RUN nor the fader default, so without _FIXED_PAIR a
    # missing/corrupt override file would silently give it A@1.5R + a TIGHT CHANDELIER Lot B —
    # and the lab explicitly falsified a trailing Lot B here. Assert the fail-safe floor holds.
    for base in ("nipc_long", "nipc_short"):
        a, b = defaults[f"{base}_A"], defaults[f"{base}_B"]
        assert (a.exit, a.target_r) == ("scalp", 2.0)
        assert (b.exit, b.target_r) == ("scalp", 2.5)   # fixed R, NOT a chandelier


def test_nipc_time_rails_survive_the_scaleout_rewrite():
    # ★2026-08-01: max_hold_s / flat_by_utc_s are new SlotSpec fields — the scale-out slate rewrites
    # Lot A/B via `replace`, and a field it forgot to carry would silently drop NIPC's 20-min cap and
    # its 15:30 UTC flat. (target_r on the capitulation base IS silently dropped that way.)
    d = _by_tag()
    for tag in ("nipc_long_A", "nipc_long_B", "nipc_short_A", "nipc_short_B"):
        assert d[tag].max_hold_s == NIPC_HOLD_CAP_S == 1200
        assert d[tag].flat_by_utc_s == NIPC_FLAT_BY_S == 55800   # 15:30 UTC
        assert d[tag].kind == "nipc" and d[tag].base_size == 1 and d[tag].risk_budget_usd == 0.0
    # and no OTHER gate picked up a time rail
    for tag, s in d.items():
        if s.kind != "nipc":
            assert s.max_hold_s == 0.0 and s.flat_by_utc_s == 0.0


def test_live_exit_overrides_produce_the_intended_slate():
    """★2026-08-01: the LIVE data/exit_overrides.json, asserted as deployed config (this is the file
    the running desk reads at slate build). Change the file → change this test, deliberately."""
    d = _by_tag()
    exp = {
        # ★2026-08-02: capitulation dropped OUT of exit_overrides.json when the 08-01 flip=False/1.0R
        # change was withdrawn (its "78% win" was an MFE stat, not a win rate — the ordering-correct
        # number is 29%). It now falls back to the built-in FADER default: A@1.5R + B tight-k1.5.
        "capitulation_long_A": ("scalp", 1.5), "capitulation_long_B": ("chandelier", None),
        "exhaustion_short_A": ("scalp", 0.75), "exhaustion_short_B": ("chandelier", None),
        "abs_veto_long_A": ("scalp", 1.0), "abs_veto_long_B": ("scalp", 1.5),
        "abs_veto_short_A": ("scalp", 1.5), "abs_veto_short_B": ("scalp", 2.5),
        "nipc_long_A": ("scalp", 2.0), "nipc_long_B": ("scalp", 2.5),
        "nipc_short_A": ("scalp", 2.0), "nipc_short_B": ("scalp", 2.5),
        # no override → built-in BIG-RUN default
        "grind_long_A": ("scalp", 2.5), "grind_long_B": ("chandelier_lock", None),
        "rgv_short_A": ("scalp", 1.5), "rgv_short_B": ("chandelier", None),
    }
    for tag, (ex, tr) in exp.items():
        assert d[tag].exit == ex, tag
        if tr is not None:
            assert d[tag].target_r == tr, tag
    # "tight" really is a k1.5 non-vol-adaptive chandelier (the file's documented contract)
    for tag in ("capitulation_long_B", "exhaustion_short_B"):
        assert d[tag].chandelier_start_k == 1.5 and d[tag].vol_adaptive_chandelier is False


def test_capitulation_base_target_r_is_SILENTLY_DROPPED_by_the_scaleout_slate():
    """REGRESSION GUARD documenting a live trap that is STILL REAL after the 08-02 revert.
    A `target_r` set on a base spec in tournament_slots() reaches NOTHING under the scaleout slate:
    scaleout_slots() rewrites Lot A's target_r (from exit_overrides.json, or the BIG-RUN/FADER
    default) and turns Lot B into a chandelier. The base value is inert.

    ★2026-08-01 this bit for real — capitulation's re-derived target only 'landed' because the
    override file separately carried it, and even then on HALF the position. ★2026-08-02 the base is
    back to 2.0R and the override is gone, so the gap is now 2.0 (base) vs 1.5 (what actually runs) —
    same trap, different numbers. If this ever fails because the base started mattering, good: delete
    the guard. Until then, never tune a scaleout gate by editing base target_r."""
    base = {s.tag: s for s in _ss.tournament_slots()}["capitulation_long"]
    assert base.target_r == 2.0 and base.exit == "scalp"
    d = _by_tag()
    assert d["capitulation_long_B"].exit == "chandelier"    # Lot B ignores target_r entirely
    assert d["capitulation_long_A"].target_r == 1.5         # the FADER default — NOT the base's 2.0
    assert d["capitulation_long_A"].target_r != base.target_r   # the trap, asserted explicitly


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
