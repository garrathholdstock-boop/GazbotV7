"""abs_veto promotion (2026-07-25) — roster + 55s-veto polarity + side-filter.

Guards the live promotion of the two single-sided abs_veto gates (thrust + 55s
absorption-veto) that replaced thrust_short + rgv_long. The veto *loop* lives in
tournament.run() (an async loop, not unit-testable in isolation), but its two
load-bearing pieces are pure and tested here: (1) the roster wiring, (2) the
exit_absorption veto polarity, (3) the automatic side-filter in _gate_fires.
"""
from gazbot7 import deciders as d
from gazbot7.deciders import Features, Position, exit_absorption
from gazbot7.slot_strategy import SlotStrategy, tournament_slots


def _feat(net5: float) -> Features:
    """A minimal Features that fires gate_thrust in the sign of net5 (thr 1.5,
    amp_floor 0.0004, require_vol)."""
    return Features(price=20000.0, atr=20.0, atr_pct=0.001, vwap=20000.0,
                    vwap_slope_atr=0.0, ext_atr=0.0, net_atr_5=net5, vol_surge=True,
                    n_bars=30, net_atr_2=net5, vwap_slope_fast=0.0)


def test_roster_promotion():
    tags = [s.tag for s in tournament_slots()]
    assert tags.count("abs_veto_long") == 1 and tags.count("abs_veto_short") == 1
    assert "rgv_long" not in tags and "thrust_short" not in tags and "exhaustion_short" in tags  # rgv_long swapped back OUT 07-25 for the rehabbed exhaustion
    assert len(tags) == 6   # ★2026-08-15: nipc retired from the roster (was 8)
    assert not [t for t in tags if t.startswith("nipc")], "nipc must not be back on the roster"
    by = {s.tag: s for s in tournament_slots()}
    for t, side in (("abs_veto_long", "LONG"), ("abs_veto_short", "SHORT")):
        assert by[t].kind == "thrust" and by[t].side == side
        assert by[t].exit == "scalp" and by[t].base_size == 1
        assert by[t].params == {"thr": 1.5, "amp_floor": 0.0004}


def test_veto_constants():
    assert d.VETO_GATES == frozenset({"abs_veto_long", "abs_veto_short"})
    assert d.VETO_SECS == 55 and d.VETO_MAX_SECS == 75 and d.VETO_FLOW_MIN == 50.0
    # ★2026-08-01: the per-side chop-floor is GONE on BOTH sides — abs_veto_long's ER floor and
    # abs_veto_short's ATR-16 floor were re-derived as blocking profitable populations
    # (abs_veto_short: +$137/28sig blocked, strip-3 -$197, LODO -$11.02 = "not proven", deleted
    # rather than tuned). abs_veto now runs entirely UNGATED on regime; the 55s absorption veto is
    # its only entry filter. [was: ER_FLOOR abs_veto_long 0.20, ATR_FLOOR abs_veto_short 16.0]
    assert "abs_veto_long" not in d.ER_FLOOR and "abs_veto_short" not in d.ER_FLOOR
    assert "abs_veto_short" not in d.ATR_FLOOR and "abs_veto_long" not in d.ATR_FLOOR
    # momentum floor only — never fader ceiling / confirm path, and thrust_short is retired
    assert not (d.VETO_GATES & (set(d.ER_CEIL) | d.CONFIRM_GATES))
    assert "thrust_short" not in d.ER_FLOOR and "thrust_short" not in d.ATR_FLOOR


def test_veto_polarity():
    """exit_absorption fires (→ VETO) when heavy flow OUR way FAILED to move price."""
    fm = d.VETO_FLOW_MIN
    # LONG: heavy BUY (+flow) that did NOT lift price (dpx<=0) = fakeout → veto
    assert exit_absorption(Position("LONG", 0, 0, 0), tape_net=fm + 10, window_price_delta=-1.0) is not None
    # LONG: heavy BUY that DID lift price = clean thrust → NOT vetoed (would OPEN)
    assert exit_absorption(Position("LONG", 0, 0, 0), tape_net=fm + 10, window_price_delta=+3.0) is None
    # SHORT: heavy SELL (-flow) that did NOT drop price = fakeout → veto
    assert exit_absorption(Position("SHORT", 0, 0, 0), tape_net=-(fm + 10), window_price_delta=+1.0) is not None
    # SHORT: heavy SELL that DID drop price = clean thrust → NOT vetoed
    assert exit_absorption(Position("SHORT", 0, 0, 0), tape_net=-(fm + 10), window_price_delta=-3.0) is None
    # weak flow (below floor) never counts as absorption
    assert exit_absorption(Position("LONG", 0, 0, 0), tape_net=fm - 10, window_price_delta=-1.0) is None


def test_side_filter():
    """_gate_fires drops the wrong-direction thrust: abs_veto_long only on a LONG
    thrust, abs_veto_short only on a SHORT thrust."""
    strat = SlotStrategy(tournament_slots(), value_per_point=2.0)
    by = {s.tag: s for s in tournament_slots()}
    long_thrust, short_thrust = _feat(+2.0), _feat(-2.0)
    assert strat._gate_fires(by["abs_veto_long"], long_thrust, 0.0, {}) is True
    assert strat._gate_fires(by["abs_veto_long"], short_thrust, 0.0, {}) is False
    assert strat._gate_fires(by["abs_veto_short"], short_thrust, 0.0, {}) is True
    assert strat._gate_fires(by["abs_veto_short"], long_thrust, 0.0, {}) is False
