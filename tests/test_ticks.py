"""S1 — tick rounding: the Error-110 fix. Directional + float-noise-safe."""

from __future__ import annotations

from gazbot7.ticks import DEFAULT_TICK, round_stop, round_to_tick, tick_for


def test_tick_for():
    assert tick_for("MNQ") == 0.25
    assert tick_for("MGC") == 0.10
    assert tick_for("NOPE") == DEFAULT_TICK


def test_round_to_tick_modes():
    assert round_to_tick(29478.214, 0.25, mode="floor") == 29478.0
    assert round_to_tick(29478.214, 0.25, mode="ceil") == 29478.25
    assert round_to_tick(29478.13, 0.25, mode="nearest") == 29478.25
    assert round_to_tick(29478.11, 0.25, mode="nearest") == 29478.0


def test_round_stop_directional():
    # the exact price that got rejected today (29478.214 on 0.25 grid)
    # SELL stop (long protection, below entry) → floor, further away
    assert round_stop(29478.214, 0.25, closing_side="SELL") == 29478.0
    # BUY stop (short protection, above entry) → ceil, further away
    assert round_stop(29478.214, 0.25, closing_side="BUY") == 29478.25


def test_float_noise_safe():
    # 2907.3 is exactly 29073 ticks of 0.1, but 2907.3/0.1 == 29072.9999.. in fp —
    # a naive floor would drop a whole tick (the V5 scar). The de-noise prevents it.
    assert round_to_tick(2907.3, 0.10, mode="floor") == 2907.3
    assert round_stop(2907.3, 0.10, closing_side="SELL") == 2907.3


def test_already_on_grid_is_idempotent():
    assert round_stop(29478.0, 0.25, closing_side="SELL") == 29478.0
    assert round_stop(29478.25, 0.25, closing_side="BUY") == 29478.25
