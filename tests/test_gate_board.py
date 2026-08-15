"""The pooled sat-out run-catcher — `gate_board`, and its wiring into the shadow book.

★★2026-08-15. From the weekend hunt: the census found 68 MNQ runs >=1.5xATR in the week to 08-14,
we were on EIGHT and sat out SIXTY worth $8,025 of ceiling. 59 of the 60 were boardable a median
seven minutes in with 93% of the move still ahead.

★★★ THE TEST THAT MATTERS IS test_the_shadow_book_can_actually_express_it. `ShadowSim._entry` ends
in `else: e = None`, so a variant naming a gate kind the sim does not know records NOTHING, silently,
forever — you would see an armed variant with zero trades and no error anywhere. The MGC hunt found
exactly that blocker for its own gates. Arming a variant without proving the dispatch reaches it is
how a shadow arm becomes a four-week no-op.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.deciders import Features, gate_board  # noqa: E402


def F(net5=2.5, **kw):
    d = dict(price=29000.0, atr=30.0, atr_pct=0.1, vwap=29000.0, vwap_slope_atr=0.0,
             ext_atr=0.0, net_atr_5=net5, vol_surge=False, n_bars=99)
    d.update(kw)
    return Features(**d)


def test_it_takes_the_direction_the_move_is_already_going():
    """It predicts nothing — the move picks the side."""
    assert gate_board(F(net5=+2.5), utc_hour=15.0).side == "LONG"
    assert gate_board(F(net5=-2.5), utc_hour=15.0).side == "SHORT"


def test_below_k_is_no_signal():
    assert gate_board(F(net5=1.0), utc_hour=15.0) is None
    assert gate_board(F(net5=-1.0), utc_hour=15.0) is None


def test_the_session_window_carries_the_whole_edge():
    """Unfiltered the edge is $2.15/trade and strips to -$4; inside 13:00-20:00Z it is $33.44/trade,
    PF 1.52, strip-3 +$6,758. Overnight is -$197 over 603 fires. A same-size RANDOM cut scores
    $1.19/trade (p95 $5.89), so the clock is doing the work, not luck."""
    for h in (13.0, 15.5, 19.99):
        assert gate_board(F(), utc_hour=h) is not None
    for h in (0.0, 12.99, 20.0, 23.5):
        assert gate_board(F(), utc_hour=h) is None


def test_a_missing_clock_trades_NOTHING():
    """★ FAIL CLOSED. The session filter IS the strategy, so a caller that forgets to pass the hour
    must trade nothing rather than trade around the clock. utc_hour defaults to -1.0 for this reason."""
    assert gate_board(F()) is None


def test_the_shadow_book_can_actually_express_it():
    """★★★ The silent-no-op guard. `_entry` ends in `else: e = None`, so an unknown gate kind records
    nothing and reports no error. Prove the dispatch reaches gate_board and that the CLOCK arrives
    from `ts` — Features carries no hour, so a wiring that forgot it would fail closed on every bar
    and look identical to 'the signal never fired'."""
    import inspect

    from gazbot7 import shadow
    src = inspect.getsource(shadow.ShadowSim._entry)
    assert 'v.gate == "board"' in src, "the sim cannot dispatch 'board' — the variant would be a no-op"
    assert "utc_hour=" in src and "ts % 86400" in src, "the clock must come from ts"
    names = [v.name for v in shadow.default_slate()]
    assert "rider_w5" in names, "armed variant missing from the slate"
    v = [x for x in shadow.default_slate() if x.name == "rider_w5"][0]
    assert v.gate == "board" and v.symbol == "MNQ"
    assert v.stop_atr_mult == 3.0, "the 3xATR stop is the strategy — median adverse excursion is 3.00R"
    assert v.chandelier is False, "every chandelier variant tested RED"
    assert "rvol_min" not in v.params and "atr_pr_min" not in v.params, \
        "floors help w=10 and HURT w=5 ($4,841 -> $2,833) — they must not be copied across"
