"""Tournament runner — the pure `step` decision helper's freshness gating."""
from __future__ import annotations

from gazbot7.agg import MinuteBars
from gazbot7.slot_strategy import SlotStrategy, grind_long_short_slots
from gazbot7.slotbook import SlotBook
from gazbot7.tournament import step


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
