"""Conviction sizing — Efficiency Ratio + the 0/1/2 lot ladder for the grind go-live."""
from __future__ import annotations

from gazbot7.deciders import Bar
from gazbot7.sizing import conviction_lots, efficiency_ratio


def _bars(closes):
    return [Bar(1000 + i * 60, c, c + 1, c - 1, c, 100) for i, c in enumerate(closes)]


def test_efficiency_ratio_high_on_a_clean_trend():
    er = efficiency_ratio(_bars([100 + i for i in range(30)]))   # straight line up
    assert er > 0.95


def test_efficiency_ratio_low_on_chop():
    er = efficiency_ratio(_bars([100 + (1 if i % 2 else -1) for i in range(30)]))  # zig-zag, no net
    assert er < 0.1


def test_efficiency_ratio_too_few_bars_is_zero():
    assert efficiency_ratio(_bars([100, 101, 102])) == 0.0


def test_conviction_ladder_base2_skips_chop_halves_marginal_fulls_trend():
    assert conviction_lots(0.10, base=2) == 0    # chop → skip
    assert conviction_lots(0.35, base=2) == 1    # marginal → half
    assert conviction_lots(0.60, base=2) == 2    # clean trend → full
    # boundaries: lo inclusive-of-1, hi inclusive-of-full
    assert conviction_lots(0.25, base=2) == 1
    assert conviction_lots(0.45, base=2) == 2


def test_conviction_base1_is_a_gate_only():
    assert conviction_lots(0.10, base=1) == 0    # chop → skip
    assert conviction_lots(0.35, base=1) == 1    # marginal → 1 (no upsize room)
    assert conviction_lots(0.60, base=1) == 1
