"""Per-contract regime router — the classifier + engine map + counterfactual.

Shadow-first: the router never submits. What matters here is that the reactive read
labels the regime it's IN (no look-ahead), the engine map benches the wrong engine
(momentum in chop / against trend; reversion in a trend), and the counterfactual sums
only the aligned trades so the routed-vs-actual number is honest and reproducible.
"""

from __future__ import annotations

from gazbot7.deciders import Bar
from gazbot7.router import (
    CHOP,
    DEAD,
    MOMENTUM,
    REVERSION,
    TREND_DOWN,
    TREND_UP,
    RouterCfg,
    classify_regime,
    engine_aligned,
    engine_class_of,
    move_dir_at,
    move_direction,
    regime_at,
)
from gazbot7.deciders import compute_features


def _bars(closes: list[float], ts0: int = 1_000_000, vol: float = 100.0) -> list[Bar]:
    # flat OHLC around close with a little range so ATR > 0
    return [Bar(ts0 + i * 5, c, c + 1, c - 1, c, vol) for i, c in enumerate(closes)]


def test_classify_reads_the_regime_it_is_in_not_the_next():
    up = compute_features(_bars([100 + i * 0.5 for i in range(60)]))
    dn = compute_features(_bars([100 - i * 0.5 for i in range(60)]))
    flat = compute_features(_bars([100 + (0.2 if i % 2 else -0.2) for i in range(60)]))
    assert classify_regime(up) == TREND_UP
    assert classify_regime(dn) == TREND_DOWN
    assert classify_regime(flat) == CHOP


def test_dead_regime_when_atr_pct_below_floor():
    # truly flat bars (zero range) → atr 0 → atr% 0, below any positive floor
    flat_bars = [Bar(1_000_000 + i * 5, 100.0, 100.0, 100.0, 100.0, 100.0) for i in range(60)]
    flat = compute_features(flat_bars)
    assert classify_regime(flat, RouterCfg(atr_pct_dead=0.001)) == DEAD
    # floor disabled (default) never returns DEAD
    assert classify_regime(flat) in (CHOP, TREND_UP, TREND_DOWN)


def test_engine_class_mapping():
    assert engine_class_of("thrust") == MOMENTUM
    assert engine_class_of("grind") == MOMENTUM
    assert engine_class_of("reversal_grab") == REVERSION
    assert engine_class_of("capitulation") == REVERSION
    assert engine_class_of("nonsense") is None


def test_momentum_ungated_by_default_keeps_every_winner():
    # DEFAULT: momentum eligible in any regime, any direction — its trigger self-selects.
    # This is the tune that keeps the counter-trend momentum winners.
    for reg in (TREND_UP, TREND_DOWN, CHOP):
        for md in (-1, 0, 1):
            assert engine_aligned("thrust", "LONG", reg, move_dir=md)
            assert engine_aligned("grind", "SHORT", reg, move_dir=md)


def test_fade_guard_when_enabled_judges_on_the_fast_move():
    # with the guard ON, momentum must be WITH the fast move (or flat)
    ON = dict(momentum_needs_move=True)
    assert engine_aligned("thrust", "LONG", TREND_UP, move_dir=1, **ON)
    assert engine_aligned("thrust", "SHORT", TREND_UP, move_dir=-1, **ON)   # early reversal, kept
    assert engine_aligned("thrust", "LONG", CHOP, move_dir=0, **ON)         # flat → trigger self-selects
    assert not engine_aligned("thrust", "SHORT", TREND_UP, move_dir=1, **ON)   # real fade → benched
    assert not engine_aligned("thrust", "LONG", TREND_DOWN, move_dir=-1, **ON)  # real fade → benched


def test_counter_move_flags_only_momentum_against_the_fast_move():
    from gazbot7.router import counter_move
    assert counter_move("thrust", "SHORT", 1)      # short into a rising move
    assert counter_move("grind", "LONG", -1)       # long into a falling move
    assert not counter_move("thrust", "LONG", 1)   # with the move
    assert not counter_move("thrust", "LONG", 0)   # flat move → not a fade
    assert not counter_move("reversal_grab", "SHORT", 1)  # reversion is not momentum


def test_engine_map_reversion_only_in_chop_ignores_move_dir():
    assert engine_aligned("reversal_grab", "LONG", CHOP, move_dir=1)
    assert engine_aligned("capitulation", "SHORT", CHOP, move_dir=-1)
    assert not engine_aligned("reversal_grab", "LONG", TREND_UP, move_dir=0)   # fading into trend
    assert not engine_aligned("reversal_grab", "SHORT", TREND_DOWN, move_dir=0)


def test_unknown_engine_is_never_credited():
    # an unmapped gate is stood down in every regime — never a false routed credit
    for reg in (TREND_UP, TREND_DOWN, CHOP, DEAD):
        assert not engine_aligned("mystery", "LONG", reg, move_dir=1)


def test_regime_at_uses_only_bars_up_to_entry():
    # up-trend then a hard reversal down AFTER the entry ts. The read at the entry must
    # see only the up-trend — no look-ahead into the reversal.
    up = [100 + i * 0.5 for i in range(60)]
    entry_ts = 1_000_000 + 59 * 5
    down_after = [130 - i * 0.8 for i in range(60)]
    bars = _bars(up) + _bars(down_after, ts0=entry_ts + 5)
    assert regime_at(bars, entry_ts) == TREND_UP


def test_regime_at_too_few_bars_returns_none():
    assert regime_at(_bars([100, 101, 102]), 1_000_050) is None


def test_move_direction_reads_the_fast_slope():
    up = compute_features(_bars([100 + i * 0.4 for i in range(60)]))
    dn = compute_features(_bars([100 - i * 0.4 for i in range(60)]))
    flat = compute_features(_bars([100 + (0.1 if i % 2 else -0.1) for i in range(60)]))
    assert move_direction(up) == 1
    assert move_direction(dn) == -1
    assert move_direction(flat) == 0


def test_move_dir_at_uses_only_bars_up_to_entry():
    # up into the entry, then a fast reversal down after — the read at entry sees only up
    up = [100 + i * 0.4 for i in range(60)]
    entry_ts = 1_000_000 + 59 * 5
    down_after = [124 - i * 0.6 for i in range(60)]
    bars = _bars(up) + _bars(down_after, ts0=entry_ts + 5)
    assert move_dir_at(bars, entry_ts) == 1


def test_move_dir_at_too_few_bars_is_flat():
    assert move_dir_at(_bars([100, 101, 102]), 1_000_050) == 0
