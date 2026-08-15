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


def test_rider_w5_carries_its_backtest_cooldown():
    """★★2026-08-15. gf_rider_engine.run_trades ran ONE POSITION AT A TIME with a 15-MINUTE cooldown
    after every exit (`busy_until = r.ts + held + cooldown_min * 60`). That is why 337 signals a
    session collapse to ~6 trades — and every number quoted for this leg (+$4,841, $19.29/tr) came
    from the constrained version. Shipped without it, the shadow fires far more often than the thing
    that was measured, so the forward record would not be testing the strategy at all."""
    from gazbot7.shadow import default_slate
    v = [x for x in default_slate() if x.name == "rider_w5"][0]
    assert v.params.get("cooldown_min") == 15


def test_every_gate_with_a_researched_cooldown_declares_it_EXPLICITLY():
    """★★★ THE REGRESSION GUARD, and it exists because I caused this bug twice in one day.

    Both new gates shipped without the cooldown their backtest ran under, each time because the pure
    gate function takes no such kwarg so passing it would raise. The fix moved enforcement into
    ShadowSim._entry, keyed on the variant DECLARING `cooldown_min` — and that refactor immediately
    dropped the gold cooldown again, because it had been relying on a default.

    So: no defaults. A gate whose research used a cooldown must say so in its own params, where it
    is visible in the slate and cannot be lost to a refactor."""
    from gazbot7.shadow import default_slate, mgc_slate
    need = {"rider_w5": 15, "mgc_holebreak_fade_long": 45, "mgc_holebreak_fade_short": 45}
    have = {v.name: v.params.get("cooldown_min")
            for v in list(default_slate()) + list(mgc_slate()) if v.name in need}
    assert have == need, f"a researched cooldown went missing: {have} != {need}"


def test_the_cooldown_is_enforced_centrally_and_armed_at_the_exit():
    import inspect

    from gazbot7 import shadow
    entry = inspect.getsource(shadow.ShadowSim._entry)
    rec = inspect.getsource(shadow.ShadowSim._record)
    assert "_cool_until" in entry, "not enforced before dispatch"
    assert "_cool_until" in rec, "not armed at the exit — the research measures it from the CLOSE"
    # the pure gates must never receive it: they take no such kwarg and would raise
    assert 'k != "cooldown_min"' in entry
