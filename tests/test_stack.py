"""The risk-weighted always-on stack — circuit breaker (loss cap, not timing), inverse-vol
weighting, and the diversification multiplier that quantifies the anti-correlation free lunch.
"""
from __future__ import annotations

from gazbot7.stack import (combine, day_circuit_breaker, diversification_multiplier,
                           inverse_vol_weights, max_drawdown, sharpe)


def test_circuit_breaker_never_touches_a_winning_day():
    # a day that only climbs never gives back → full P&L kept
    assert day_circuit_breaker([50, 40, 30, 20], max_giveback=100) == 140


def test_circuit_breaker_caps_a_bleed_day_and_stands_down_the_rest():
    # +100 peak, then bleeds; once giveback hits 100 it stops and ignores the rest
    day = [100, -60, -50, -500, -500]   # peak +100, at -50 cum=-10 (gb 110≥100) → stop
    capped = day_circuit_breaker(day, max_giveback=100)
    assert capped == -10           # stopped after the -50, the two -500s never taken
    assert capped > sum(day)       # strictly better than riding the whole bleed


def test_circuit_breaker_from_open_is_a_flat_floor():
    # a day that only loses, never a positive peak → caps at ~ -max_giveback
    assert day_circuit_breaker([-40, -40, -40, -40], max_giveback=100) == -120  # stops when gb≥100


def test_inverse_vol_gives_the_calmer_gate_more_weight():
    w = inverse_vol_weights({"calm": [10, 12, 8, 11], "wild": [100, -80, 90, -70]})
    assert w["calm"] > w["wild"]
    assert abs(w["calm"] + w["wild"] - 1.0) < 1e-9


def test_diversification_multiplier_rewards_anti_correlation():
    # two perfectly anti-correlated equal-weight gates → the free lunch is maximal
    anti = {"a": [1, -1, 1, -1, 1], "b": [-1, 1, -1, 1, -1]}
    ew = {"a": 0.5, "b": 0.5}
    idm_anti = diversification_multiplier(anti, ew)
    # identical (perfectly correlated) gates → no diversification, IDM ≈ 1
    same = {"a": [1, -1, 1, -1, 1], "b": [1, -1, 1, -1, 1]}
    idm_same = diversification_multiplier(same, ew)
    assert idm_anti > idm_same
    assert abs(idm_same - 1.0) < 1e-6


def test_combine_and_metrics():
    s = {"a": [10, -5, 8, -3], "b": [-4, 9, -2, 7]}
    w = {"a": 0.5, "b": 0.5}
    c = combine(s, w)
    assert c == [3.0, 2.0, 3.0, 2.0]        # anti-correlated → a smooth combined curve
    assert sharpe(c) > 0
    assert max_drawdown(c) == 0.0           # monotone-up equity → no drawdown
    assert max_drawdown([10, -30, 5]) == -30
