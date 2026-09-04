"""A breach may not be confirmed until every desk has REWRITTEN its claim.

★★★ THE 2026-09-03T16:42:10Z FALSE KILL. The operator's manual claim closed a SHORT 4 at the venue.
The day-rider writes its state once a MINUTE, so for the next few seconds the books still said
`rider -4` against a venue of 0. The reconciler's two-read confirmation sampled the VENUE twice, six
seconds apart, found the same `unaccounted +4` both times, called it confirmed and STOPPED BOTH
DESKS for a position that no longer existed.

The guard was blind to the exact race it was built to catch: it re-sampled the venue, and the stale
side was the CLAIM. Both reads are drawn from the same unchanged file, so agreement between them
proves nothing at all.

The cost was not just the kill. `day_rider=off` also takes down the 20:40Z hard flat and every Claim
button, and this service never re-arms anything by design — so the operator's BUY button was dead
for four hours and nothing said why.

⚠ THE KILL IS NOT WEAKENED. A real orphan survives the desks' next write and is killed one tick
later (~60-90s). Nothing can be OPENED in the meantime: deskrecon.may_place_order() already refuses
every new order while the invariant fails, kill file or not.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "desk_reconcile", "/home/alphabot/gazbot7/scripts/desk_reconcile.py")
dr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dr)


def test_the_0903_false_kill_is_refused():
    """THE REGRESSION CASE. Same imbalance, and the rider has not rewritten its state."""
    first = {"rider": "2026-09-03T16:41:57+00:00", "tournament": "2026-09-03T16:42:09.9+00:00"}
    # six seconds later: the tournament wrote again (~1s cycle), the rider did NOT (60s cycle)
    now = {"rider": "2026-09-03T16:41:57+00:00", "tournament": "2026-09-03T16:42:15.9+00:00"}
    ok, why = dr.require_fresh_claims(first, now)
    assert ok is False, "a kill was confirmed while the rider's book had not caught up"
    assert "rider" in why


def test_a_real_orphan_confirms_once_both_desks_have_written():
    """The kill still fires — one rider cycle later, against claims that are genuinely current."""
    first = {"rider": "2026-09-03T16:41:57+00:00", "tournament": "2026-09-03T16:42:09+00:00"}
    now = {"rider": "2026-09-03T16:42:57+00:00", "tournament": "2026-09-03T16:43:09+00:00"}
    ok, why = dr.require_fresh_claims(first, now)
    assert ok is True, f"a persisting orphan must still stop both desks: {why}"


def test_one_desk_advancing_is_not_enough():
    """The tournament writes every second; letting it alone satisfy the gate restores the bug."""
    first = {"rider": "2026-09-03T16:41:57+00:00", "tournament": "2026-09-03T16:42:09+00:00"}
    now = {"rider": "2026-09-03T16:41:57+00:00", "tournament": "2026-09-03T16:43:09+00:00"}
    assert dr.require_fresh_claims(first, now)[0] is False


def test_an_unreadable_stamp_never_counts_as_advanced():
    """FAIL-CLOSED on the kill: no write-stamp means we cannot prove the book caught up."""
    first = {"rider": "2026-09-03T16:41:57+00:00", "tournament": "2026-09-03T16:42:09+00:00"}
    assert dr.require_fresh_claims(first, {"rider": "", "tournament": ""})[0] is False


def test_claim_stamps_reads_the_real_writers():
    """The stamps must come from the files the desks actually write, with the keys they use."""
    st = dr.claim_stamps()
    assert set(st) == {"rider", "tournament"}
    # both desks are live on this box; a persistently empty stamp means the key or path is wrong
    assert st["rider"] and st["tournament"], f"write-stamps not being read: {st}"


def test_pending_store_roundtrips_and_clears(tmp_path):
    """⚠ Redirected at a tmp path: a test that wrote the REAL store could clobber a live pending
    breach and hand the next tick a free confirmation."""
    real, dr.PENDING = dr.PENDING, str(tmp_path / "pending.json")
    try:
        dr.save_pending({"unaccounted": 4.0, "stamps": {"rider": "x", "tournament": "y"}})
        assert dr.load_pending().get("unaccounted") == 4.0
        dr.clear_pending()
        assert dr.load_pending() == {}
    finally:
        dr.PENDING = real
