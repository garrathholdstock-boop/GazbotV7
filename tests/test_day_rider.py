"""Day-rider unit tests — the PURE parts, which is where the money logic lives.

The venue/order path is not unit-testable without a broker, so the safety-critical arithmetic is
factored out (trail_level, enabled, session rollover) and pinned here. Every one of these is a
failure mode that would have cost money silently rather than raising.
"""
import datetime as dt
import json

from gazbot7 import day_rider as dr


def test_trail_not_armed_until_ahead():
    # ★ THE TRAIL MUST NOT EXIST BEFORE +150. Every day in the sample trades back through its entry
    # within a minute or two (31 of 31), so a trail live from the start is stopped out on noise —
    # measured: a naked 50pt trail returned -$882 against +$13,257 for the armed version.
    assert dr.trail_level(1, 100.0, 100.0) is None
    assert dr.trail_level(1, 100.0, 100.0 + dr.ARM_PT - 1) is None
    assert dr.trail_level(-1, 100.0, 100.0 - dr.ARM_PT + 1) is None


def test_trail_arms_and_tracks_the_peak():
    lvl = dr.trail_level(1, 100.0, 100.0 + dr.ARM_PT)
    assert lvl == 100.0 + dr.ARM_PT - dr.TRAIL_PT
    # it ratchets with a new peak and NEVER loosens
    assert dr.trail_level(1, 100.0, 400.0) == 300.0
    assert dr.trail_level(1, 100.0, 400.0) > dr.trail_level(1, 100.0, 300.0)


def test_trail_is_symmetric_for_shorts():
    # 10 of 18 directional days were DOWN — a long-only trail would silently mismanage half of them.
    assert dr.trail_level(-1, 100.0, 100.0 - dr.ARM_PT) == 100.0 - dr.ARM_PT + dr.TRAIL_PT


def test_switch_defaults_off_when_missing_or_broken(tmp_path, monkeypatch):
    # An order-placing service must never default ON. A missing or garbled switch means OFF.
    monkeypatch.setattr(dr, "SWITCH", str(tmp_path / "nope.env"))
    assert dr.enabled() is False
    p = tmp_path / "s.env"
    p.write_text("garbage\n")
    monkeypatch.setattr(dr, "SWITCH", str(p))
    assert dr.enabled() is False
    p.write_text("day_rider=off\n")
    assert dr.enabled() is False
    p.write_text("# comment\nday_rider=on\n")
    assert dr.enabled() is True


def test_state_roundtrip_is_atomic_and_stamps_heartbeat(tmp_path, monkeypatch):
    # The watchdog flattens on a stale heartbeat, so every save MUST stamp it — a save that forgot
    # would get the position flattened out from under a healthy service.
    monkeypatch.setattr(dr, "STATE", str(tmp_path / "st.json"))
    dr.save_state({"session": "2026-08-06", "entered": True})
    got = dr.load_state()
    assert got["entered"] is True
    assert "heartbeat" in got
    dt.datetime.fromisoformat(got["heartbeat"])      # parses, so the watchdog can compare it


def test_venue_stop_is_wider_than_the_deepest_recovery():
    # The deepest drawdown that still won in the 31-session sample was 511pt. The venue stop is
    # last-resort insurance, NOT a trading stop: if it is ever tight enough to fire on a live trade
    # it will be killing winners (a 400pt stop cost $3,451 and worsened the worst day).
    assert dr.VENUE_STOP_PT > 511


def test_entry_cutoff_covers_every_validated_detection():
    # All 31 backtested detections landed 13:38-14:09. The cutoff must sit AFTER the latest of those
    # (or the strategy would refuse trades it was validated on) and BEFORE the close (or it would take
    # entries the backtest has no examples of, then hold them into the hard flat).
    assert dr.ENTRY_CUTOFF_MIN > 14 * 60 + 9
    assert dr.ENTRY_CUTOFF_MIN < 21 * 60


def test_exit_ask_only_when_ahead_and_reversed():
    atr = 20.0
    # never ahead => never ask. A trade that never worked has nothing to protect, and paging the
    # operator about noise near the entry trains them to ignore the alert.
    assert dr.should_ask_exit(1, 100.0, 100.0, 90.0, atr) is False
    # ahead but only a small pullback => no ask
    assert dr.should_ask_exit(1, 100.0, 300.0, 290.0, atr) is False
    # ahead and reversed >= 2xATR off the peak => ask
    assert dr.should_ask_exit(1, 100.0, 300.0, 300.0 - 2 * atr, atr) is True
    # symmetric for shorts (10 of 18 directional days were DOWN)
    assert dr.should_ask_exit(-1, 300.0, 100.0, 100.0 + 2 * atr, atr) is True
    # unmeasurable ATR must never trigger — 'I cannot measure' is not 'it reversed'
    assert dr.should_ask_exit(1, 100.0, 300.0, 200.0, 0.0) is False


def test_approval_is_token_matched(tmp_path, monkeypatch):
    # ★ Replay protection. Without token matching, a /sell typed at 20:00 sits on disk and flattens
    # tomorrow's fresh position — approving a trade that did not exist when it was typed.
    import json as _j
    f = tmp_path / "ap.json"
    monkeypatch.setattr(dr, "APPROVAL_FILE", str(f))
    f.write_text(_j.dumps({"token": "2026-08-06:111", "decision": "sell"}))
    assert dr.read_approval("2026-08-06:111") == "sell"
    assert dr.read_approval("2026-08-07:999") is None      # different session => ignored
    f.write_text("not json")
    assert dr.read_approval("2026-08-06:111") is None      # unreadable => no decision, never a sell


def test_bot_refuses_when_nothing_pending(tmp_path):
    # A stray /sell must not be able to close a healthy position that is not asking to exit.
    from gazbot7 import telegram_bot as tb
    st = tmp_path / "st.json"
    st.write_text('{"entered": true}')
    msg = tb.day_rider_decision("sell", state_path=str(st), approval_path=str(tmp_path / "a.json"))
    assert "Nothing pending" in msg


def test_save_state_defaults_venue_ok_false(tmp_path, monkeypatch):
    # ★ The heartbeat is a claim that someone is managing the position. A caller that forgets to set
    # venue_ok must default to NOT-managed, so the watchdog errs toward flattening rather than toward
    # trusting a service that never reached the broker.
    monkeypatch.setattr(dr, "STATE", str(tmp_path / "st.json"))
    dr.save_state({"session": "2026-08-06"})
    assert dr.load_state()["venue_ok"] is False


def test_flat_clock_leaves_a_retry_window_before_the_halt():
    # ★ The original 21:00 flat WAS the CME halt — no market to fill into and no retry window, which
    # is the one failure mode that breaks "never hold overnight". The flat clock must sit strictly
    # before the halt, with enough minute-ticks left to retry a failed flatten.
    assert dr.FLAT_UTC_MIN < dr.HALT_UTC_MIN
    assert dr.HALT_UTC_MIN - dr.FLAT_UTC_MIN >= 15      # >=15 automatic retries at a 1-min cadence
    # and it must still be after the entry cutoff, or entries could never be managed to a close
    assert dr.FLAT_UTC_MIN > dr.ENTRY_CUTOFF_MIN


def test_nipc_regime_buckets_and_filter():
    # The live filter and scripts/nipc_replay.py MUST share one definition — the replay validates the
    # filter, so a divergence would mean validating something the desk does not run.
    from gazbot7.deciders import nipc_bad_regime, nipc_regime
    assert nipc_regime(15, 0.20) == "dead-chop"
    assert nipc_regime(15, 0.60) == "clean-trend"
    assert nipc_regime(20, 0.40) == "in-between-building"
    assert nipc_regime(30, 0.20) == "violent-whipsaw"
    assert nipc_regime(20, 0.20) == "normal-chop"
    # blocked: the three buckets that lose or contribute nothing
    assert nipc_bad_regime(15, 0.20) is True      # dead-chop
    assert nipc_bad_regime(30, 0.20) is True      # violent-whipsaw — the biggest drag
    assert nipc_bad_regime(20, 0.20) is True      # normal-chop
    # allowed: the two that pay
    assert nipc_bad_regime(20, 0.40) is False     # in-between-building
    assert nipc_bad_regime(15, 0.60) is False     # clean-trend


def test_asia_block_window_and_semantics():
    """★2026-08-05 'bench asia permanently'. Shadow n=1840 at -$3.17/trade, the worst block.
    Note the operator's original framing ('don't trade until the US open') was REFUTED: pre-open is
    -$1.75/tr vs the US session's -$1.93. It is Asia specifically, not 'pre-open'."""
    from datetime import UTC, datetime
    from gazbot7 import session
    for h in (0, 3, 6):
        assert session.in_asia_block(datetime(2026, 8, 6, h, 30, tzinfo=UTC)) is True
    for h in (7, 12, 13, 20, 22, 23):      # London, US and the post-halt reopen all stay tradeable
        assert session.in_asia_block(datetime(2026, 8, 6, h, 30, tzinfo=UTC)) is False
    # and the day-rider is unaffected — it only ever trades 13:38-20:40
    from gazbot7 import day_rider as dr
    assert dr.ENTRY_CUTOFF_MIN > 7 * 60
    assert dr.FLAT_UTC_MIN > 7 * 60


# ── 2026-08-07 ATR-SCALED TRAIL ───────────────────────────────────────────────────────────────
# A FIXED +150pt arm is a threshold a losing trade can never reach: on 08-07 the live rider sat
# -252pt and the trail never armed, so it rode to the clock. Backtest over 35 detected sessions:
# 2xATR trail armed at 4xATR = $7,341 vs $3,732 for the fixed rule, on identical entries.

def test_atr_trail_arms_on_atr_not_a_fixed_point_count():
    from gazbot7.day_rider import trail_level
    # ATR 20 -> arms at 4x20 = 80pt ahead, well before the old fixed 150pt bar
    assert trail_level(1, 100.0, 179.0, 20.0) is None          # 79pt ahead — not yet
    tl = trail_level(1, 100.0, 181.0, 20.0)                    # 81pt ahead — armed
    assert tl is not None and tl == 181.0 - 2.0 * 20.0         # trails 2xATR off the peak


def test_atr_trail_scales_with_volatility():
    """The whole point: the same point-move arms on a quiet day and not on a violent one."""
    from gazbot7.day_rider import trail_level
    quiet, violent = 10.0, 50.0
    assert trail_level(1, 100.0, 145.0, quiet) is not None      # 45pt ahead vs 4x10=40 -> armed
    assert trail_level(1, 100.0, 145.0, violent) is None        # same move vs 4x50=200 -> not armed


def test_atr_trail_falls_back_to_fixed_when_frozen_atr_missing():
    """Old state files / restarts / no atr must keep the previous behaviour, never crash."""
    from gazbot7.day_rider import ARM_PT, TRAIL_PT, trail_level
    assert trail_level(1, 100.0, 100.0 + ARM_PT - 1, 0.0) is None
    assert trail_level(1, 100.0, 100.0 + ARM_PT + 1, 0.0) == (100.0 + ARM_PT + 1) - TRAIL_PT


def test_atr_trail_mirrors_for_a_short():
    from gazbot7.day_rider import trail_level
    tl = trail_level(-1, 100.0, 100.0 - 81.0, 20.0)            # 81pt ahead on a short
    assert tl is not None and tl == 19.0 + 2.0 * 20.0          # trail sits ABOVE the peak


# ── the "not mine" alarm is said ONCE, not on every tick ─────────────────────
def _unowned_rig(tmp_path, monkeypatch, net=-2.0):
    """A rider tick that finds an unowned position on the venue, with every I/O redirected."""
    import asyncio

    from gazbot7 import notify as _notify

    monkeypatch.setattr(dr, "STATE", str(tmp_path / "rider.json"))
    monkeypatch.setattr(_notify, "_DEDUPE_PATH", str(tmp_path / "dedupe.json"))
    monkeypatch.setattr(dr, "enabled", lambda: True)

    class _IB:
        def disconnect(self):
            pass

    async def _venue(_cfg):
        return _IB(), object()

    async def _net(_ib, _sym):
        return _net.value
    _net.value = net

    monkeypatch.setattr(dr, "_venue", _venue)
    monkeypatch.setattr(dr, "_net_position", _net)

    sent = []
    # 08:00 UTC — before OPEN_UTC_MIN, so the stand-down branch is reached, exactly as it is on
    # every real tick all morning.
    when = dt.datetime(2026, 8, 14, 8, 0, tzinfo=dt.UTC)

    def tick(minutes=0, net_now=None):
        if net_now is not None:
            _net.value = net_now
        asyncio.run(dr.step(dr.RunConfig(), now=when + dt.timedelta(minutes=minutes),
                            notify=lambda m, **k: sent.append(m)))
    return tick, sent


def test_unowned_position_alarms_once_not_every_tick(tmp_path, monkeypatch):
    """★★2026-08-14 THE OPERATOR-FACING BUG. Standing down is CORRECT, but this branch is reached on
    every tick outside the rider's window, so it repeated on Telegram for hours while desk_reconcile
    independently confirmed the account was fully accounted for. Telegram is where CRITICAL alarms
    land — steady state must be silent so that change is loud."""
    tick, sent = _unowned_rig(tmp_path, monkeypatch)
    for m in range(30):                      # half an hour of 60s ticks
        tick(m)
    assert len(sent) == 1, f"the stand-down alarm repeated {len(sent)}x over 30 ticks"
    assert "NOT mine" in sent[0] and "NOT flattening" in sent[0]


def test_a_resize_stays_quiet_but_a_direction_flip_speaks(tmp_path, monkeypatch):
    """The signature carries direction + ownership, never magnitude: the tournament scales in and
    out all session and the rider's decision is identical at -1 or -2 (size correctness is the
    reconciler's job). Observed live at 12:12Z, where keying on the message re-alarmed on -2 -> -1."""
    tick, sent = _unowned_rig(tmp_path, monkeypatch, net=-2.0)
    tick(0)
    tick(1, net_now=-1.0)                    # tournament closed a lot
    tick(2, net_now=-4.0)                    # ...and opened two more
    assert len(sent) == 1, f"a resize re-alarmed: {sent}"
    tick(3, net_now=+2.0)                    # a FLIP is genuinely different news
    assert len(sent) == 2


def test_going_flat_rearms_so_the_next_occurrence_is_not_swallowed(tmp_path, monkeypatch):
    """A cooldown must suppress a CONTINUING state, never a fresh occurrence of one."""
    tick, sent = _unowned_rig(tmp_path, monkeypatch, net=-2.0)
    tick(0)
    assert len(sent) == 1
    tick(1, net_now=0.0)                     # venue flat -> condition resolved, key cleared
    assert len(sent) == 1                    # nothing to say about a flat venue
    tick(2, net_now=-2.0)                    # it came back: this is NEW, and must be heard
    assert len(sent) == 2, "a new occurrence was swallowed by the running cooldown"
