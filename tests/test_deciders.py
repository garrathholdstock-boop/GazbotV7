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
    gate_capitulation,
    gate_grind,
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


# ── reversal_grab LONG mirror (2026-07-16) ────────────────────────────────────
def test_reversal_long_fires_below_and_turning_up():
    e = gate_reversal_grab(_feat(ext_atr=-3.0, net_atr_5=0.6), side="LONG", turn_atr=0.5)
    assert e is not None and e.side == "LONG" and e.gate == "reversal_grab"


def test_reversal_long_needs_below_extension():
    assert gate_reversal_grab(_feat(ext_atr=-1.0, net_atr_5=0.6), side="LONG", turn_atr=0.5) is None


def test_reversal_long_needs_the_up_turn():
    assert gate_reversal_grab(_feat(ext_atr=-3.0, net_atr_5=0.3), side="LONG", turn_atr=0.5) is None


def test_reversal_long_flow_filter_wants_net_buy():
    assert gate_reversal_grab(_feat(ext_atr=-3.0, net_atr_5=0.6), side="LONG", flow_min=50, tape_net=30) is None
    assert gate_reversal_grab(_feat(ext_atr=-3.0, net_atr_5=0.6), side="LONG", flow_min=50, tape_net=60) is not None


def test_reversal_short_still_default_side():
    # side defaults SHORT — the original behaviour is unchanged
    assert gate_reversal_grab(_feat(ext_atr=3.0, net_atr_5=-0.6), turn_atr=0.5).side == "SHORT"


# ── gate_thrust slope_align — with-trend-only filter (2026-07-16) ─────────────
def test_thrust_slope_align_passes_with_trend():
    # LONG burst in an up-slope, SHORT burst in a down-slope — both aligned, both fire
    assert gate_thrust(_feat(net_atr_5=2.0, vwap_slope_atr=0.5), slope_align=True).side == "LONG"
    assert gate_thrust(_feat(net_atr_5=-2.0, vwap_slope_atr=-0.5), slope_align=True).side == "SHORT"


def test_thrust_slope_align_vetoes_counter_trend():
    # LONG burst into a down-slope / SHORT burst into an up-slope — counter-trend, vetoed
    assert gate_thrust(_feat(net_atr_5=2.0, vwap_slope_atr=-0.5), slope_align=True) is None
    assert gate_thrust(_feat(net_atr_5=-2.0, vwap_slope_atr=0.5), slope_align=True) is None


def test_thrust_slope_align_vetoes_flat():
    assert gate_thrust(_feat(net_atr_5=2.0, vwap_slope_atr=0.0), slope_align=True) is None


def test_thrust_slope_align_off_ignores_slope():
    # default (off) — a counter-trend burst still fires, unchanged behaviour
    assert gate_thrust(_feat(net_atr_5=2.0, vwap_slope_atr=-0.5)).side == "LONG"


# ── gate_thrust fast (2-bar impulse) trigger (2026-07-16) ─────────────────────
def test_thrust_fast_fires_on_2bar_when_5bar_is_flat():
    f = _feat(net_atr_2=2.0, net_atr_5=0.3, vwap_slope_atr=0.5, vol_surge=True)
    assert gate_thrust(f, fast=True).side == "LONG"   # sharp 2-bar impulse fires
    assert gate_thrust(f, fast=False) is None          # 5-bar too small → normal wouldn't


def test_thrust_fast_respects_alignment():
    up_into_down = _feat(net_atr_2=2.0, net_atr_5=0.0, vwap_slope_atr=-0.5, vol_surge=True)
    assert gate_thrust(up_into_down, fast=True, slope_align=True) is None  # counter-trend vetoed
    with_trend = _feat(net_atr_2=-2.0, net_atr_5=0.0, vwap_slope_atr=-0.5, vol_surge=True)
    assert gate_thrust(with_trend, fast=True, slope_align=True).side == "SHORT"


# ── gate_capitulation — tape-footprint flush-and-flip fade (2026-07-16) ────────
def test_capitulation_fades_a_down_flush():
    # sell climax (800 vs 100 base = 8×, 94% dom) + price fell (cap_dpx<0) → fade LONG
    e = gate_capitulation(_feat(), cap_sell=800, cap_buy=50, cap_base=100, cap_dpx=-5.0, climax_min=3, dom_min=0.7)
    assert e.side == "LONG" and e.gate == "capitulation"


def test_capitulation_fades_an_up_thrust():
    e = gate_capitulation(_feat(), cap_buy=800, cap_sell=50, cap_base=100, cap_dpx=5.0, climax_min=3, dom_min=0.7)
    assert e.side == "SHORT"


def test_capitulation_needs_price_to_have_moved():
    # climax present but price flat (cap_dpx 0) → no fade (which way?)
    assert gate_capitulation(_feat(), cap_sell=800, cap_buy=50, cap_base=100, cap_dpx=0.0) is None


def test_capitulation_needs_the_climax():
    assert gate_capitulation(_feat(), cap_sell=200, cap_buy=50, cap_base=100, cap_dpx=-5.0, climax_min=3) is None


def test_capitulation_needs_dominance():
    assert gate_capitulation(_feat(), cap_sell=400, cap_buy=400, cap_base=50, cap_dpx=-5.0, dom_min=0.7) is None


def test_capitulation_require_flip():
    assert gate_capitulation(_feat(), cap_sell=800, cap_buy=50, cap_base=100, cap_dpx=-5.0,
                             require_flip=True, cap_flip=False) is None
    assert gate_capitulation(_feat(), cap_sell=800, cap_buy=50, cap_base=100, cap_dpx=-5.0,
                             require_flip=True, cap_flip=True).side == "LONG"


# ── gate_grind — trend-continuation ride (2026-07-16) ─────────────────────────
def test_grind_rides_an_uptrend():
    f = _feat(vwap_slope_atr=0.8, ext_atr=1.5)  # established up-slope, riding above VWAP
    assert gate_grind(f).side == "LONG"


def test_grind_rides_a_downtrend():
    assert gate_grind(_feat(vwap_slope_atr=-0.8, ext_atr=-1.5)).side == "SHORT"


def test_grind_needs_an_established_slope():
    assert gate_grind(_feat(vwap_slope_atr=0.2, ext_atr=1.5), slope_min=0.5) is None


def test_grind_skips_when_exhausted_or_wrong_side_of_vwap():
    assert gate_grind(_feat(vwap_slope_atr=0.8, ext_atr=5.0)) is None    # over-extended
    assert gate_grind(_feat(vwap_slope_atr=0.8, ext_atr=-1.0)) is None   # below VWAP in an up-slope


def test_grind_flow_confirm():
    f = _feat(vwap_slope_atr=0.8, ext_atr=1.5)
    assert gate_grind(f, flow_min=50, tape_net=10) is None       # not enough net buy
    assert gate_grind(f, flow_min=50, tape_net=80).side == "LONG"


# ── fast-slope rewire (2026-07-16) ────────────────────────────────────────────
def test_features_has_fast_slope():
    bars = [Bar(i, 100+i*0.5, 100+i*0.5+0.3, 100+i*0.5-0.3, 100+i*0.5, 10) for i in range(20)]
    assert compute_features(bars).vwap_slope_fast > 0  # rising → positive fast slope


def test_grind_fast_uses_short_slope():
    # 60-bar slope flat but fast slope up → grind_fast goes LONG, plain grind doesn't
    f = _feat(vwap_slope_atr=0.1, vwap_slope_fast=0.8, ext_atr=1.5)
    assert gate_grind(f, slope_min=0.4, fast_slope=True).side == "LONG"
    assert gate_grind(f, slope_min=0.4, fast_slope=False) is None


def test_rg_long_fast_fires_where_slow_slope_vetoes():
    # a reversal: 60-bar slope steep (would veto) but fast slope flat; extended below,
    # fast 2-bar up-turn → rg_long_fast fires; the plain gate is vetoed.
    f = _feat(vwap_slope_atr=-1.25, vwap_slope_fast=-0.5, ext_atr=-2.8, net_atr_2=0.5, net_atr_5=-1.0)
    assert gate_reversal_grab(f, side="LONG", ext_min=2.0, turn_atr=0.15, fast_slope=True, fast_turn=True).side == "LONG"
    assert gate_reversal_grab(f, side="LONG", ext_min=2.0, turn_atr=0.15) is None  # slow slope vetoes
