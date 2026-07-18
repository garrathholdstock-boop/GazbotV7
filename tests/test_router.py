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


def test_engine_map_momentum_only_with_the_trend():
    # momentum rides a trend, only in its direction
    assert engine_aligned("thrust", "LONG", TREND_UP)
    assert engine_aligned("thrust", "SHORT", TREND_DOWN)
    assert not engine_aligned("thrust", "SHORT", TREND_UP)   # fading up-trend
    assert not engine_aligned("thrust", "LONG", TREND_DOWN)  # fading down-trend
    assert not engine_aligned("thrust", "LONG", CHOP)        # momentum stood down in chop


def test_engine_map_reversion_only_in_chop():
    assert engine_aligned("reversal_grab", "LONG", CHOP)
    assert engine_aligned("capitulation", "SHORT", CHOP)
    assert not engine_aligned("reversal_grab", "LONG", TREND_UP)   # fading into trend
    assert not engine_aligned("reversal_grab", "SHORT", TREND_DOWN)


def test_unknown_engine_is_never_credited():
    # an unmapped gate is stood down in every regime — never a false routed credit
    for reg in (TREND_UP, TREND_DOWN, CHOP, DEAD):
        assert not engine_aligned("mystery", "LONG", reg)


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
