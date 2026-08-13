"""The venue-first gate on the day-rider's order paths.

★ The scenario is the real one from 2026-08-13 at 15:53: the rider's own state says CLOSED, the
tournament holds shorts, and lots at the venue belong to nobody. Before this gate existed, the trail
path sized an exit off the stale book and sold 2 lots a minute — four times — opening a naked 8-lot
short. The gate must refuse.

The hard-flat exemption is tested too, because getting THAT wrong is worse than the bug: refusing to
flatten at 20:40 because the books disagree would turn a bookkeeping fault into an overnight
position, against the operator's absolute rule.
"""
import json
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import day_rider, deskrecon  # noqa: E402

NOW = datetime.now(UTC)
SHORT2 = [{"gate": "abs_veto_short_A", "side": "SHORT", "qty": 1.0},
          {"gate": "abs_veto_short_B", "side": "SHORT", "qty": 1.0}]


def _scene(tmp_path, tourn_slots, rider):
    st = tmp_path / "status.json"
    st.write_text(json.dumps({"ts": (NOW - timedelta(seconds=1)).isoformat(),
                              "protection": {"slots": tourn_slots}}))
    drs = tmp_path / "day_rider_state.json"
    rider = dict(rider, heartbeat=(NOW - timedelta(seconds=5)).isoformat())
    drs.write_text(json.dumps(rider))
    deskrecon.STATUS, deskrecon.DR_STATE = str(st), str(drs)
    deskrecon.KILL = str(tmp_path / "no_kill.json")


def test_gate_refuses_the_0813_trail_exit(tmp_path):
    # rider CLOSED, tournament -2, venue -8 → 6 lots unowned. No order may be placed.
    _scene(tmp_path, SHORT2, {"entered": True, "closed": True, "qty": 2.0, "direction": 1})
    pages = []

    # The real notify takes `critical=`; a one-arg fake would raise inside the helper's
    # except-block and silently record nothing — which is how this test first "passed" the refusal
    # but saw no page. Match the real signature.
    def fake_notify(msg, critical=False):
        pages.append((msg, critical))

    assert day_rider.venue_first_ok(-8.0, "exit on TRAIL", fake_notify) is False
    assert pages, "a refusal must page — a silent refusal is indistinguishable from idleness"
    msg, critical = pages[0]
    assert "REFUSED" in msg and "TRAIL" in msg and critical is True


def test_gate_allows_a_reconciled_account(tmp_path):
    # rider long 2, tournament short 2, venue 0 → everything accounted for.
    _scene(tmp_path, SHORT2, {"entered": True, "closed": False, "qty": 2.0, "direction": 1})
    assert day_rider.venue_first_ok(0.0, "exit on TRAIL", None) is True


def test_gate_refuses_entry_when_unaccounted(tmp_path):
    _scene(tmp_path, [], {"entered": False, "closed": False})
    assert day_rider.venue_first_ok(-3.0, "ENTER 2 lots", None) is False


def test_gate_refuses_while_a_kill_is_active(tmp_path):
    _scene(tmp_path, SHORT2, {"entered": True, "closed": False, "qty": 2.0, "direction": 1})
    k = tmp_path / "kill.json"
    k.write_text(json.dumps({"active": True, "reason": "test breach"}))
    deskrecon.KILL = str(k)
    assert day_rider.venue_first_ok(0.0, "exit on TRAIL", None) is False


def test_gate_never_breaks_trading_if_it_throws(tmp_path):
    """A broken GATE must not stop a desk — deskrecon's own service is what alarms. Point the
    module at nonsense and confirm the helper still returns True rather than raising."""
    deskrecon.STATUS = "/nonexistent/status.json"
    deskrecon.DR_STATE = "/nonexistent/rider.json"
    deskrecon.KILL = "/nonexistent/kill.json"
    # unreadable claims => may_place_order returns False (blocked, correctly) but must not raise
    assert day_rider.venue_first_ok(0.0, "exit on TRAIL", None) in (True, False)


def test_hard_flat_path_is_not_gated():
    """The 20:40 flatten must never consult the gate as a veto.

    Asserted on the SOURCE, because the exemption is a property of where the call is not. If someone
    later wraps the hard-flat placeOrder in venue_first_ok(), this fails and explains why.
    """
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    flat_block = src.split("THE HARD FLAT IS DELIBERATELY")[1].split("# ★ VERIFY")[0]
    # Anchor on CODE, not prose. Splitting mid-comment leaves that comment's tail as the first line
    # with its leading '#' already consumed, so a startswith('#') stripper misses it and the test
    # fails on correct source. Take from the first real statement instead.
    code = flat_block[flat_block.index("try:"):]
    assert "venue_first_ok" not in code, (
        "the 20:40 hard flat must NOT be gated — refusing to flatten because the books disagree "
        "turns a bookkeeping fault into an overnight position, which is strictly worse")
    assert "may_place_order" in flat_block, "it should still CHECK and page, just not refuse"
