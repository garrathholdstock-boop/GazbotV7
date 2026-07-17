"""D8 — honest tick repricer: far-touch fills, stop/target on ticks, R-leg scored."""

from __future__ import annotations

from gazbot7.capture import open_capture, record_quote
from gazbot7.repricer import Quote, reprice, reprice_pending
from gazbot7.store import open_store, record_shadow_trade

VPP, FEE = 2.0, 1.5


def _trade(side="LONG", entry_atr=4.0, target_r=2.0, stop_atr_mult=1.0, qty=1.0):
    return {"side": side, "entry_atr": entry_atr, "target_r": target_r,
            "stop_atr_mult": stop_atr_mult, "qty": qty}


def test_long_target_far_touch():
    # entry at ask 100; stop 96, target 108. A quote with mid >= 108 → exit at bid.
    quotes = [Quote(0, 99.5, 100.0), Quote(1, 108.0, 108.5)]  # mid 108.25 >= 108
    pnl, status = reprice(_trade(), quotes, value_per_point=VPP, fee_rt=FEE)
    assert status == "filled"
    assert pnl == (108.0 - 100.0) * VPP - FEE  # entry ask 100, exit bid 108 → +14.5


def test_long_stop():
    quotes = [Quote(0, 99.5, 100.0), Quote(1, 95.5, 96.0)]  # mid 95.75 <= stop 96
    pnl, _ = reprice(_trade(), quotes, value_per_point=VPP, fee_rt=FEE)
    assert pnl == (95.5 - 100.0) * VPP - FEE  # -10.5 (a real loss, honest)


def test_short_target():
    quotes = [Quote(0, 100.0, 100.5), Quote(1, 91.5, 92.0)]  # entry bid 100; target 92
    pnl, _ = reprice(_trade("SHORT"), quotes, value_per_point=VPP, fee_rt=FEE)
    assert pnl == (100.0 - 92.0) * VPP - FEE  # +14.5 (exit ask 92)


def test_session_exit_when_never_hit():
    quotes = [Quote(0, 99.5, 100.0), Quote(1, 100.5, 101.0)]  # drifts, no stop/target
    pnl, status = reprice(_trade(), quotes, value_per_point=VPP, fee_rt=FEE)
    assert status == "filled"  # closed at the last touch, still a real number


def test_r_target_leg_is_scored_not_blank():
    # THE V5 FIX: an rtarget/scalp strategy reprices to a real number, never blank.
    pnl, status = reprice(_trade(target_r=2.0), [Quote(0, 99.5, 100.0), Quote(1, 108.0, 108.5)],
                          value_per_point=VPP, fee_rt=FEE)
    assert pnl is not None and status == "filled"


def test_reprice_pending_writes_shadow_real():
    # REALISTIC UNITS: entry_ts/exit_ts are minute-aligned bar starts in SECONDS;
    # quotes.ts_ms is MILLISECONDS. The signal fires at the bar CLOSE (entry_ts+60),
    # so quotes must sit at/after (entry_ts+60)*1000. (This guards the seconds-vs-ms
    # 1000× bug that scored every live trade `no_data`.)
    store = open_store(":memory:")
    cap = open_capture(":memory:")
    entry_ts, exit_ts = 1_784_185_260, 1_784_185_320  # unix seconds, 1 min apart
    close_ms = (entry_ts + 60) * 1000                  # bar close = signal time
    record_quote(cap, "MNQ", close_ms, 99.5, 100.0, 5, 5)          # far-touch entry ask=100
    record_quote(cap, "MNQ", close_ms + 30_000, 108.0, 108.5, 5, 5)  # hits target
    record_quote(cap, "MNQ", close_ms + 180_000, 108.0, 108.5, 5, 5)  # tail captured → window complete
    cap.commit()
    tid = record_shadow_trade(
        store, strategy="t1", symbol="MNQ", side="LONG", qty=1,
        entry_ts=entry_ts, entry_price=100.0, entry_atr=4.0, target_r=2.0, stop_atr_mult=1.0,
        exit_ts=exit_ts, exit_price=108.0, exit_reason="TARGET", ceiling_pnl=16.0,
    )
    n = reprice_pending(store, cap, value_per_point=VPP, fee_rt=FEE)
    assert n == 1
    row = store.execute("SELECT real_pnl, fill_status FROM shadow_real WHERE trade_id=?", (tid,)).fetchone()
    assert row["fill_status"] == "filled"        # scored on ticks, NOT no_data
    assert row["real_pnl"] == (108.0 - 100.0) * VPP - FEE  # honest, < the 16.0 ceiling


def test_sentinel_quotes_never_poison_a_fill():
    # IBKR's no-quote SENTINEL (-1.0) is NOT NULL, so the old filter let it through
    # and priced winners as ~-$58k ((−1−entry)·vpp). It must be dropped entirely.
    store = open_store(":memory:"); cap = open_capture(":memory:")
    ets, xts = 1_784_185_260, 1_784_185_320
    cms = (ets + 60) * 1000
    hi = (xts + 60) * 1000 + 120_000
    record_quote(cap, "MNQ", cms, 99.5, 100.0, 5, 5)            # clean entry far-touch (ask 100)
    record_quote(cap, "MNQ", cms + 20_000, -1.0, -1.0, 0, 0)    # SENTINEL mid-window
    record_quote(cap, "MNQ", cms + 40_000, 103.5, 104.0, 5, 5)  # clean drift, no stop/target
    record_quote(cap, "MNQ", hi, 103.0, 103.5, 5, 5)            # clean quote AT hi → window complete
    cap.commit()
    record_shadow_trade(store, strategy="t", symbol="MNQ", side="LONG", qty=1,
        entry_ts=ets, entry_price=100.0, entry_atr=4.0, target_r=2.0, stop_atr_mult=1.0,
        exit_ts=xts, exit_price=104.0, exit_reason="SESSION", ceiling_pnl=8.0)
    n = reprice_pending(store, cap, value_per_point=VPP, fee_rt=FEE)
    row = store.execute("SELECT real_pnl, fill_status FROM shadow_real").fetchone()
    assert n == 1 and row["fill_status"] == "filled"
    assert row["real_pnl"] == (103.0 - 100.0) * VPP - FEE  # last CLEAN touch, NOT a -58k sentinel


def test_truncated_window_is_deferred_not_frozen():
    # the poison was FROZEN because a session-close hold was scored before its tail
    # was captured. Now a trade whose window outruns captured data is DEFERRED.
    store = open_store(":memory:"); cap = open_capture(":memory:")
    ets, xts = 1_784_185_260, 1_784_185_320
    cms = (ets + 60) * 1000
    record_quote(cap, "MNQ", cms, 99.5, 100.0, 5, 5)  # only an entry tick; window tail NOT captured
    cap.commit()
    record_shadow_trade(store, strategy="t", symbol="MNQ", side="LONG", qty=1,
        entry_ts=ets, entry_price=100.0, entry_atr=4.0, target_r=2.0, stop_atr_mult=1.0,
        exit_ts=xts, exit_price=100.0, exit_reason="SESSION", ceiling_pnl=0.0)
    n = reprice_pending(store, cap, value_per_point=VPP, fee_rt=FEE)
    assert n == 0  # deferred, not frozen on a partial window
    assert store.execute("SELECT COUNT(*) FROM shadow_real").fetchone()[0] == 0


def test_reprice_pending_no_data_when_quotes_predate_signal():
    # a trade whose quotes only exist BEFORE the bar closed → no honest fill
    store = open_store(":memory:")
    cap = open_capture(":memory:")
    entry_ts = 1_784_185_260
    record_quote(cap, "MNQ", entry_ts * 1000, 99.5, 100.0, 5, 5)  # minute start, pre-signal
    # capture has advanced PAST the window (else the new guard would defer, not score):
    # this proves 'no usable in-window quote' → no_data, not 'window not captured yet'.
    record_quote(cap, "MNQ", entry_ts * 1000 + 200_000, 100.0, 100.5, 5, 5)
    cap.commit()
    record_shadow_trade(
        store, strategy="t1", symbol="MNQ", side="LONG", qty=1,
        entry_ts=entry_ts, entry_price=100.0, entry_atr=4.0, target_r=2.0, stop_atr_mult=1.0,
        exit_ts=entry_ts, exit_price=100.0, exit_reason="STOP", ceiling_pnl=0.0,
    )
    reprice_pending(store, cap, value_per_point=VPP, fee_rt=FEE)
    row = store.execute("SELECT fill_status FROM shadow_real").fetchone()
    assert row["fill_status"] == "no_data"  # nothing at/after the bar close


def test_reprice_chandelier_rides_not_2r_target():
    # target_r=0 sentinel → the repricer rides the chandelier, banking far more than a 2R scalp
    store = open_store(":memory:"); cap = open_capture(":memory:")
    ets = 1_784_185_260; cms = (ets + 60) * 1000
    record_quote(cap, "MNQ", cms, 99.5, 100.0, 5, 5)              # entry far-touch ask 100
    record_quote(cap, "MNQ", cms + 10_000, 119.5, 120.0, 5, 5)   # runs +20 (5R)
    record_quote(cap, "MNQ", cms + 20_000, 116.5, 117.0, 5, 5)   # gives back → chandelier banks
    record_quote(cap, "MNQ", cms + 180_000, 116.5, 117.0, 5, 5)  # tail captured → window complete
    cap.commit()
    record_shadow_trade(store, strategy="c1", symbol="MNQ", side="LONG", qty=1,
                        entry_ts=ets, entry_price=100.0, entry_atr=4.0, target_r=0.0, stop_atr_mult=1.0,
                        exit_ts=ets + 60, exit_price=117.0, exit_reason="CHANDELIER", ceiling_pnl=0.0)
    reprice_pending(store, cap, value_per_point=VPP, fee_rt=FEE)
    row = store.execute("SELECT real_pnl, fill_status FROM shadow_real").fetchone()
    assert row["fill_status"] == "filled"
    assert row["real_pnl"] > 25  # rode ~+16.5pt = ~$31, far past a 2R (+8) scalp


# A run to +6 (peak_r 1.5 on atr 4) then a full reversal back to entry. A TIGHTER
# start_k banks the run near the peak; the live 3.5 never tightens enough at peak_r
# 1.5 and gives it all back — the 07-17 +$224→+$88 give-back, in miniature.
_CHAND_TRADE = {"side": "LONG", "entry_atr": 4.0, "target_r": 0.0, "stop_atr_mult": 1.0, "qty": 1.0}
_CHAND_QUOTES = [Quote(0, 99.5, 100.0), Quote(1, 105.5, 106.5), Quote(2, 101.5, 102.5),
                 Quote(3, 100.0, 101.0), Quote(4, 99.5, 100.5)]


def test_chandelier_params_are_honored_per_variant():
    # THE A/B GUARD: a tighter start_k MUST be replayed as tighter — else chand_k20 is
    # silently scored at the 3.5 default and the whole board comparison is a lie.
    tight, _ = reprice(_CHAND_TRADE, _CHAND_QUOTES, value_per_point=VPP, fee_rt=FEE, chand=(2.0, 0.5, 0.75))
    loose, _ = reprice(_CHAND_TRADE, _CHAND_QUOTES, value_per_point=VPP, fee_rt=FEE, chand=(3.5, 0.5, 0.75))
    assert tight == (101.5 - 100.0) * VPP - FEE  # k20 fired at q2, locked the run near peak → +1.5
    assert loose < 0                             # k35 gave the run back to a loss on the reversal
    assert tight > loose


def test_chandelier_default_matches_the_live_3_5():
    # chand=None must equal the live default, so untouched variants (grind_fast, …) are unchanged.
    d, _ = reprice(_CHAND_TRADE, _CHAND_QUOTES, value_per_point=VPP, fee_rt=FEE)
    e, _ = reprice(_CHAND_TRADE, _CHAND_QUOTES, value_per_point=VPP, fee_rt=FEE, chand=(3.5, 0.5, 0.75))
    assert d == e
