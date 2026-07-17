"""Session direction circuit breaker (prototype) — the governor state machine.

The threshold logic is what the operator cares about: NOT hard-and-fast (a both-win
day trips nothing), a min probe sample before any veto, and a re-arm when the
stood-down side's phantom book recovers.
"""

from __future__ import annotations

from gazbot7.cb import BreakerConfig, SessionDirectionBreaker
from gazbot7.deciders import Bar
from gazbot7.store import open_store


def _brk(**kw):
    return SessionDirectionBreaker(open_store(":memory:"), cfg=BreakerConfig(**kw))


def test_veto_needs_both_thresholds_AND_the_probe_minimum():
    b = _brk(n_min=3, loss_usd=80, win_usd=80)
    L, S = b._legs["LONG"], b._legs["SHORT"]
    L.cum, L.n, S.cum, S.n = -120, 2, 150, 3   # longs deep down but only 2 probes
    b._update_governor()
    assert not L.veto                           # min sample not met → no veto yet
    L.n = 3                                      # the 3rd (losing) long lands
    b._update_governor()
    assert L.veto and not S.veto                 # now it arms — longs stood down, shorts live


def test_both_sides_winning_trips_nothing():
    b = _brk(n_min=3, loss_usd=80, win_usd=80)
    L, S = b._legs["LONG"], b._legs["SHORT"]
    L.cum, L.n, S.cum, S.n = 140, 4, 160, 4      # a both-win day
    b._update_governor()
    assert not L.veto and not S.veto             # nobody is losing → threshold, not hard/fast


def test_a_shallow_loss_does_not_trip():
    b = _brk(n_min=3, loss_usd=80, win_usd=80)
    L, S = b._legs["LONG"], b._legs["SHORT"]
    L.cum, L.n, S.cum, S.n = -30, 4, 120, 4      # loser only −$30, under the floor
    b._update_governor()
    assert not L.veto


def test_dropped_side_rearms_when_its_phantom_book_recovers():
    b = _brk(n_min=3, loss_usd=80, win_usd=80, rearm_usd=120)
    L, S = b._legs["LONG"], b._legs["SHORT"]
    L.cum, L.n, S.cum, S.n = -120, 3, 150, 3
    b._update_governor()
    assert L.veto
    L.veto_cum = 130                             # the stood-down longs' phantom book recovers
    b._update_governor()
    assert not L.veto and L.veto_cum == 0.0      # we were (now) wrong → switch longs back on


def test_close_routes_live_vs_phantom_to_the_right_book():
    b = _brk()
    b._legs["LONG"].open = dict(side="LONG", entry_price=100.0, entry_atr=4.0,
                                entry_ts=1000, peak=0.0, live=True)
    b._close_leg("LONG", b._legs["LONG"], 105.0, 1060, "CHANDELIER")     # a LIVE winner
    b._legs["SHORT"].open = dict(side="SHORT", entry_price=100.0, entry_atr=4.0,
                                 entry_ts=2000, peak=0.0, live=False)
    b._close_leg("SHORT", b._legs["SHORT"], 90.0, 2060, "CHANDELIER")    # a PHANTOM (vetoed) winner
    strategies = {r[0] for r in b._store.execute("SELECT strategy FROM shadow_trades")}
    assert strategies == {"cb_thrust", "cb_thrust_dropped"}
    assert b._legs["LONG"].n == 1 and b._legs["LONG"].cum > 0     # live → the governed scoreboard
    assert b._legs["SHORT"].n == 0 and b._legs["SHORT"].veto_cum > 0  # phantom → only the re-arm book


def test_new_session_rearms_both_sides():
    b = _brk()
    b._legs["LONG"].veto = True
    b._legs["LONG"].cum, b._legs["LONG"].n = -200, 5

    def flat(base):
        return [Bar(base + i, 100.0, 100.5, 99.5, 100.0, 10) for i in range(15)]

    b.on_bars(flat(86400))          # day 1 — establishes the session, no reset
    assert b._legs["LONG"].veto     # state carried through the day
    b.on_bars(flat(2 * 86400))      # a new UTC day → reset
    assert not b._legs["LONG"].veto and b._legs["LONG"].cum == 0.0 and b._legs["LONG"].n == 0
