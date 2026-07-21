"""Tournament runner — the pure `step` decision helper's freshness gating."""
from __future__ import annotations

from gazbot7.agg import MinuteBars
from gazbot7.config import RunConfig
from gazbot7.slot_strategy import SlotStrategy, grind_long_short_slots, tournament_slots
from gazbot7.slotbook import SlotBook
from gazbot7.tournament import _ensure_live_cfg, step


def _setup():
    mb = MinuteBars(60)
    sb = SlotBook(["grind_long", "grind_short"], value_per_point=2.0, fee_rt=1.5)
    strat = SlotStrategy(grind_long_short_slots(), value_per_point=2.0)
    return strat, mb, sb


def test_step_stale_tape_returns_empty():
    strat, mb, sb = _setup()
    assert step(strat, mb, {"ts_ms": 0, "net_flow": 0.0}, sb, 1_000_000) == []


def test_step_no_fresh_bars_returns_empty():
    strat, mb, sb = _setup()
    now = 1_000_000_000_000
    # fresh tape, but the MinuteBars is empty → not fresh / < 6 bars → no decision
    assert step(strat, mb, {"ts_ms": now, "net_flow": 0.0, "last": 29000.0}, sb, now) == []


def test_grind_long_short_slots_shape():
    specs = grind_long_short_slots()
    assert [s.tag for s in specs] == ["grind_long", "grind_short"]
    assert [s.side for s in specs] == ["LONG", "SHORT"]


def test_tournament_slate_is_three_long_three_short_distinct():
    specs = tournament_slots()
    assert [s.tag for s in specs] == ["rgv_long", "grind_long", "capitulation_long",
                                      "thrust_short", "rgv_short", "exhaustion_short"]
    assert sum(s.side == "LONG" for s in specs) == 3
    assert sum(s.side == "SHORT" for s in specs) == 3
    assert {s.kind for s in specs} == {"reversal_grab", "grind", "thrust", "capitulation", "exhaustion"}


def test_live_run_coerces_cfg_place_live():
    # the silent no-trade bug: a live run must lift cfg.place_live so the core places orders
    assert _ensure_live_cfg(RunConfig(place_live=False), True).place_live is True
    assert _ensure_live_cfg(RunConfig(place_live=False), False).place_live is False  # dry-run untouched
    assert _ensure_live_cfg(RunConfig(place_live=True), True).place_live is True
