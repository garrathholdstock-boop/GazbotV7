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
