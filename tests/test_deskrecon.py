"""The cross-desk invariant: venue == tournament + rider.

Fixtures reproduce the 2026-08-13 incident exactly, because that is the case this module exists to
catch: the rider had CLOSED its position, the tournament held shorts, and eight lots at the venue
belonged to nobody while every per-desk guard read healthy.
"""
import json
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import deskrecon as dr  # noqa: E402

NOW = datetime(2026, 8, 13, 15, 56, 0, tzinfo=UTC)


def _write(tmp_path, tourn_slots, rider, tourn_age_s=1, rider_age_s=5):
    st = tmp_path / "status.json"
    st.write_text(json.dumps({
        "ts": (NOW - timedelta(seconds=tourn_age_s)).isoformat(),
        "protection": {"slots": tourn_slots}}))
    drs = tmp_path / "day_rider_state.json"
    rider = dict(rider)
    rider["heartbeat"] = (NOW - timedelta(seconds=rider_age_s)).isoformat()
    drs.write_text(json.dumps(rider))
    dr.STATUS, dr.DR_STATE = str(st), str(drs)


SHORT2 = [{"gate": "abs_veto_short_A", "side": "SHORT", "qty": 1.0},
          {"gate": "abs_veto_short_B", "side": "SHORT", "qty": 1.0}]
RIDER_CLOSED = {"entered": True, "closed": True, "qty": 2.0, "direction": 1}
RIDER_LONG2 = {"entered": True, "closed": False, "qty": 2.0, "direction": 1}


def test_the_0813_incident_is_a_confirmed_breach(tmp_path):
    # Venue -8. Tournament claims -2. Rider claims nothing (closed). Six lots belong to nobody.
    _write(tmp_path, SHORT2, RIDER_CLOSED)
    r = dr.reconcile(-8.0, NOW)
    assert r.breach is True and r.ok is False
    assert r.tournament == -2.0 and r.rider == 0.0
    assert r.unaccounted == -6.0
    assert "belong to NO desk" in " ".join(r.reasons)


def test_a_healthy_shared_account_reconciles(tmp_path):
    # Rider long 2, tournament short 2 → venue nets to 0 and everything is accounted for.
    _write(tmp_path, SHORT2, RIDER_LONG2)
    r = dr.reconcile(0.0, NOW)
    assert r.ok is True and r.breach is False and r.unaccounted == 0.0


def test_rider_long_alone(tmp_path):
    _write(tmp_path, [], RIDER_LONG2)
    r = dr.reconcile(2.0, NOW)
    assert r.ok is True and r.unaccounted == 0.0


def test_closed_rider_claims_zero_not_qty(tmp_path):
    # The 08-13 bug in one assertion: `entered` is true but `closed` is too, so the claim is ZERO.
    _write(tmp_path, [], RIDER_CLOSED)
    claim, why = dr.rider_claim(NOW)
    assert claim == 0.0 and why.startswith("ok")


def test_stale_claims_block_but_do_not_kill(tmp_path):
    # A dead writer must not be read as "flat" — that is how a naked position looks idle. It blocks
    # new orders (ok False) but must NOT raise a breach, or a slow file would kill the desk.
    _write(tmp_path, SHORT2, RIDER_CLOSED, tourn_age_s=9999)
    r = dr.reconcile(-2.0, NOW)
    assert r.ok is False and r.breach is False
    assert r.tournament is None
    assert "STALE" in " ".join(r.reasons)


def test_no_venue_read_blocks_but_does_not_kill(tmp_path):
    _write(tmp_path, SHORT2, RIDER_CLOSED)
    r = dr.reconcile(None, NOW)
    assert r.ok is False and r.breach is False
    assert "no venue read" in " ".join(r.reasons)


def test_unparseable_slot_is_unknown_not_zero(tmp_path):
    _write(tmp_path, [{"gate": "x", "side": "SIDEWAYS", "qty": 1.0}], RIDER_CLOSED)
    claim, why = dr.tournament_claim(NOW)
    assert claim is None and "unparseable" in why


def test_may_place_order_gates_on_the_invariant(tmp_path):
    dr.KILL = str(tmp_path / "nokill.json")
    _write(tmp_path, SHORT2, RIDER_CLOSED)
    ok, why = dr.may_place_order(-8.0, NOW)
    assert ok is False and "NO desk" in why
    _write(tmp_path, SHORT2, RIDER_LONG2)
    ok, why = dr.may_place_order(0.0, NOW)
    assert ok is True


def test_kill_file_is_fail_closed(tmp_path):
    k = tmp_path / "desk_kill.json"
    dr.KILL = str(k)
    _write(tmp_path, SHORT2, RIDER_LONG2)
    assert dr.may_place_order(0.0, NOW)[0] is True     # reconciles, no kill
    k.write_text("{ this is not json")
    active, why = dr.kill_active(str(k))
    assert active is True and "unreadable" in why
    assert dr.may_place_order(0.0, NOW)[0] is False    # kill wins over a clean reconcile
