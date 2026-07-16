"""D6 — decider library: features, thrust, reversal_grab, exits."""

from __future__ import annotations

from gazbot7.deciders import (
    REVERSAL_SHORT_VARIANTS,
    Bar,
    Features,
    Position,
    compute_features,
    exit_absorption,
    exit_adverse_cut,
    exit_chandelier,
    exit_scalp,
    gate_reversal_grab,
    gate_thrust,
)


def _feat(**kw) -> Features:
    base = dict(
        price=100.0, atr=4.0, atr_pct=0.05, vwap=90.0, vwap_slope_atr=0.2,
        ext_atr=3.0, net_atr_5=-0.6, vol_surge=True, n_bars=20,
    )
    base.update(kw)
    return Features(**base)


def test_compute_features_uptrend():
    bars = [Bar(i, 100 + i, 100 + i + 1, 99 + i, 100 + i, 10) for i in range(20)]
    bars[-1] = Bar(19, 119, 121, 118, 120, 40)  # last bar pushes up on 4x volume
    f = compute_features(bars)
    assert f.atr > 0
    assert f.net_atr_5 > 0  # price rose over the last 5 bars
    assert f.vol_surge is True
    assert f.ext_atr > 0  # price above the window VWAP in an uptrend


# ── thrust ──
def test_thrust_long():
    assert gate_thrust(_feat(net_atr_5=2.0, vol_surge=True)).side == "LONG"


def test_thrust_short():
    assert gate_thrust(_feat(net_atr_5=-2.0, vol_surge=True)).side == "SHORT"


def test_thrust_needs_magnitude_and_volume():
    assert gate_thrust(_feat(net_atr_5=1.0, vol_surge=True)) is None  # below thr
    assert gate_thrust(_feat(net_atr_5=2.0, vol_surge=False)) is None  # no vol surge


def test_thrust_amplitude_floor():
    # a strong, vol-confirmed thrust on THIN tape (atr_pct below the floor) is skipped;
    # V5's MOMENTUM_AMP_FLOOR — noise below ~0.04% (0.0004 fraction), edge above it
    assert gate_thrust(_feat(net_atr_5=2.0, vol_surge=True, atr_pct=0.0002), amp_floor=0.0004) is None
    assert gate_thrust(_feat(net_atr_5=2.0, vol_surge=True, atr_pct=0.0006), amp_floor=0.0004).side == "LONG"


# ── reversal_grab ──
def test_reversal_fires_when_extended_and_turning():
    e = gate_reversal_grab(_feat(ext_atr=3.0, net_atr_5=-0.6), turn_atr=0.5)
    assert e is not None and e.side == "SHORT" and e.gate == "reversal_grab"


def test_reversal_needs_extension():
    assert gate_reversal_grab(_feat(ext_atr=1.0, net_atr_5=-0.6), turn_atr=0.5) is None


def test_reversal_needs_the_turn():
    assert gate_reversal_grab(_feat(ext_atr=3.0, net_atr_5=-0.3), turn_atr=0.5) is None


def test_reversal_regime_guard():
    assert gate_reversal_grab(_feat(atr_pct=0.12)) is None  # chaotic vol
    assert gate_reversal_grab(_feat(vwap_slope_atr=1.5)) is None  # strong grind


def test_reversal_flow_filter():
    # flow_min=50 requires net-SELL >= 50
    assert gate_reversal_grab(_feat(), turn_atr=0.25, flow_min=50, tape_net=-30) is None
    assert gate_reversal_grab(_feat(), turn_atr=0.25, flow_min=50, tape_net=-60) is not None


def test_reversal_session_gate():
    assert gate_reversal_grab(_feat(), require_rth=True, in_rth=False) is None
    assert gate_reversal_grab(_feat(), require_rth=True, in_rth=True) is not None


def test_variant_slate():
    assert len(REVERSAL_SHORT_VARIANTS) == 5
    assert all("turn_atr" in cfg for cfg in REVERSAL_SHORT_VARIANTS.values())
    # every variant is callable through the gate
    for cfg in REVERSAL_SHORT_VARIANTS.values():
        gate_reversal_grab(_feat(), tape_net=-100, **cfg)  # no raise


# ── exits ──
def test_scalp_long_stop_and_target():
    p = Position("LONG", 100.0, 4.0)
    assert exit_scalp(p, 95.0) == "STOP"  # <= 96
    assert exit_scalp(p, 109.0) == "TARGET"  # >= 108 (2R)
    assert exit_scalp(p, 100.0) is None


def test_scalp_short_stop_and_target():
    p = Position("SHORT", 100.0, 4.0)
    assert exit_scalp(p, 105.0) == "STOP"  # >= 104
    assert exit_scalp(p, 91.0) == "TARGET"  # <= 92 (2R)


def test_adverse_cut_only_when_never_green():
    p_flat = Position("SHORT", 100.0, 4.0, peak_favorable=0.0)
    assert exit_adverse_cut(p_flat, 107.0) == "ADVERSE_CUT"  # 7 adverse >= 6, never green
    p_wasgreen = Position("SHORT", 100.0, 4.0, peak_favorable=3.0)  # peak 0.75R
    assert exit_adverse_cut(p_wasgreen, 107.0) is None


def test_absorption_cut_short():
    p = Position("SHORT", 100.0, 4.0)
    assert exit_absorption(p, tape_net=-60, window_price_delta=0.5) == "ABSORPTION_CUT"
    assert exit_absorption(p, tape_net=-60, window_price_delta=-2.0) is None  # price DID fall


# ── exit_chandelier — the tightening ATR momentum profit exit ─────────────────
def test_chandelier_banks_a_big_winner_on_giveback():
    # LONG entry 100, ATR 4, peak +20 (5R). k=max(0.5,3.5-0.75*5)=0.5 → give-back 2pt.
    pos = Position("LONG", 100.0, 4.0, 20.0)
    assert exit_chandelier(pos, 117.0) == "CHANDELIER"  # fav 17 <= peak20 - 2
    assert exit_chandelier(pos, 119.0) is None          # fav 19 still running


def test_chandelier_dormant_below_2R():
    # peak +4 (1R): give-back (2.75·ATR=11) is wider than the peak → only fireable
    # at a loss, which the loss-floor forbids. Native stop owns this trade.
    pos = Position("LONG", 100.0, 4.0, 4.0)
    assert exit_chandelier(pos, 103.0) is None
    assert exit_chandelier(pos, 99.0) is None


def test_chandelier_never_exits_at_a_loss():
    pos = Position("LONG", 100.0, 4.0, 20.0)
    assert exit_chandelier(pos, 95.0) is None  # underwater → never


def test_chandelier_tightens_with_peak():
    # peak +12 (3R): k=max(0.5,3.5-0.75*3)=1.25 → give-back 5pt, exit when fav<=7.
    pos = Position("LONG", 100.0, 4.0, 12.0)
    assert exit_chandelier(pos, 106.9) == "CHANDELIER"  # fav 6.9 <= 7
    assert exit_chandelier(pos, 108.0) is None          # fav 8 > 7


def test_chandelier_short_mirror():
    pos = Position("SHORT", 100.0, 4.0, 20.0)  # price fell to 80 at peak (fav +20)
    assert exit_chandelier(pos, 83.0) == "CHANDELIER"   # fav 17 <= 18
    assert exit_chandelier(pos, 81.0) is None           # fav 19 still running


def test_chandelier_dormant_before_any_green():
    pos = Position("LONG", 100.0, 4.0, 0.0)  # never went green
    assert exit_chandelier(pos, 105.0) is None
