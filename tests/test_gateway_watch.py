"""THE GATEWAY WATCH — restart on the climb, and NEVER on an open position.

★★ THE CONDITION (measured 2026-09-18): IB Gateway leaks sockets in CLOSE-WAIT until the 50-slot
accept queue fills. Connections already open keep working while every NEW one hangs — so every
health light stays green while the rider, the watchdog and the reconciler go blind. 25 episodes,
ten of the last seventeen days, ~33 hours. One ate a Claim pressed on a +$262 position.
"""
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import gateway_watch as gw

SRC = "/home/alphabot/gazbot7/scripts/gateway_watch.py"


def test_it_refuses_to_restart_while_a_position_is_open(tmp_path, monkeypatch):
    """⚠⚠⚠ THE SAFETY PROPERTY. A restart blinds every consumer for ~15s. Doing that to a naked
    4-lot position to fix something that has not yet bitten is the cure causing the disease."""
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"qty": 4.0, "closed": False}))
    monkeypatch.setattr(gw, "RIDER", str(p))
    flat, why = gw.desk_is_flat()
    assert flat is False and "4" in why


def test_an_unreadable_state_is_NOT_treated_as_flat(tmp_path, monkeypatch):
    """⚠⚠ NOT KNOWING IS NOT THE SAME AS FLAT. A missing or corrupt state file must block the
    restart, not wave it through — that is the instrument-reports-healthy failure in miniature."""
    monkeypatch.setattr(gw, "RIDER", str(tmp_path / "does-not-exist.json"))
    flat, why = gw.desk_is_flat()
    assert flat is False and "blind" in why.lower()


def test_a_closed_position_is_flat(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"qty": 4.0, "closed": True}))
    monkeypatch.setattr(gw, "RIDER", str(p))
    assert gw.desk_is_flat()[0] is True


def test_it_trips_on_the_CLIMB_not_the_wedge():
    """★ The queue is 50. Tripping AT 50 means acting after the outage has already started."""
    assert gw.TRIP < gw.BACKLOG, "the trip point is not below the backlog — that is too late"
    assert gw.TRIP >= 20, "too twitchy: a transient handful of CLOSE-WAIT is normal"


def test_there_is_a_cooldown():
    """⚠ A restart that does not clear the condition must not become a restart LOOP. The thing that
    takes a desk down is never the first restart, it is the fourth."""
    assert gw.COOLDOWN_S >= 1800
    assert "cooling down" in open(SRC).read()


def test_declining_is_LOUD():
    """⚠ A guard that declines in silence is a guard nobody knows they lack."""
    src = open(SRC).read()
    assert "NOT RESTARTING" in src


def test_it_records_which_jobs_were_running():
    """★★ THE WHOLE POINT OF THE SERIES. 18 of 25 episodes start 18:00-00:00Z, where driftlab,
    backfill and the overnight research all hammer historical data. That is a HYPOTHESIS; this
    logs the evidence to settle it rather than assuming."""
    src = open(SRC).read()
    for job in ("backfill_history", "driftlab", "overnight"):
        assert job in src, f"the series does not record whether {job} was running"
    s = gw.sample()
    assert "close_wait" in s and "acceptq" in s and "ts" in s


def test_it_samples_both_the_leak_and_the_outage():
    """⚠ CLOSE-WAIT is the leak ACCUMULATING; the accept queue filling is the moment it becomes an
    outage. Logging only one of them loses the lead time that makes this worth running."""
    s = gw.sample()
    assert s["close_wait"] is not None and s["acceptq"] is not None and s["backlog"] == 50


def test_the_ruled_out_causes_are_written_down():
    """★ So nobody re-chases them. Four hypotheses were eliminated with evidence on 2026-09-18."""
    src = open(SRC).read()
    for gone in ("subscriptions", "rogue client", "nightly reset", "per-connection leak"):
        assert gone.split()[0].lower() in src.lower()
