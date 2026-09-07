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


# ─────────────────────────────────────────────────────────────────────────────
# ★★★ THE 2026-09-06/07 SILENT DISARM. The case above has a mirror image, and it had NO COVERAGE
# — which is exactly why it shipped. `require_fresh_claims` was never the problem the second time:
# the KILL COULD NOT REACH IT. In main(), the "position-change race" branch fired whenever
# `confirmed` was False, and on a genuine persisting breach that is EVERY tick, because
# confirmation deliberately waits for a second sighting. So the pending record written microseconds
# earlier was wiped on the same tick, forever, and sighting two never arrived.
#
# Live cost: at the 2026-09-06T22:00Z reopen the account went to SHORT 40 against a book claiming
# LONG 4 — unaccounted -44. For eight hours both venue reads agreed on -44 and the service logged
# "treated as a position-change race" each time. It reported a race while looking at a settled
# breach, and no alarm ever escalated.
#
# ⚠ These drive the REAL main() with the venue and the clock faked — not a replica of its logic.
# A test that re-implemented the branch would have passed against the bug.
# ─────────────────────────────────────────────────────────────────────────────
import json


class _R:
    """A deskrecon.reconcile() result: the breach shape, with nothing else stubbed."""

    def __init__(self, unaccounted):
        self.unaccounted = float(unaccounted)
        self.breach = abs(self.unaccounted) > 0.5
        self.ok = not self.breach
        self.reasons = ["faked breach"] if self.breach else []

    def summary(self):
        return f"venue -40 = tournament +0 + rider +4 -> unaccounted {self.unaccounted:+g}"


def _run_one_tick(monkeypatch, tmp_path, *, unaccounted1, unaccounted2, stamps):
    """One full invocation of the real main() against a faked venue. Returns (rc, state, calls)."""
    calls = {"benched": [], "pages": []}

    async def fake_snapshot(cfg):
        fake_snapshot.n += 1
        return (-40.0, [])
    fake_snapshot.n = 0

    seq = iter([_R(unaccounted1), _R(unaccounted2)])
    monkeypatch.setattr(dr, "venue_snapshot", fake_snapshot)
    monkeypatch.setattr(dr.deskrecon, "reconcile", lambda net: next(seq))
    monkeypatch.setattr(dr, "orphan_stops", lambda net, orders: [])
    monkeypatch.setattr(dr, "claim_stamps", lambda: dict(stamps))
    monkeypatch.setattr(dr, "SECOND_READ_DELAY_S", 0.0)
    monkeypatch.setattr(dr, "STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(dr, "PENDING", str(tmp_path / "pending.json"))
    monkeypatch.setattr(dr, "bench_everything",
                        lambda reason: calls["benched"].append(reason) or ["STOPPED BOTH DESKS"])
    monkeypatch.setattr(dr, "page",
                        lambda msg, critical=True, **kw: calls["pages"].append((critical, msg)))
    monkeypatch.setattr(sys, "argv", ["desk_reconcile"])

    rc = dr.main()
    with open(str(tmp_path / "state.json")) as fh:
        return rc, json.load(fh), calls


def test_a_persisting_agreed_breach_keeps_its_pending_record(monkeypatch, tmp_path):
    """TICK ONE. Both reads agree on -44. This must be RECORDED, not thrown away as a race.

    The bug: `elif r1.breach:` ran here and called clear_pending(), so this assertion failed on
    every one of the ~960 ticks the -44 was live.
    """
    stamps = {"rider": "2026-09-07T06:00:00+00:00", "tournament": "2026-09-07T06:00:00+00:00"}
    rc, state, calls = _run_one_tick(monkeypatch, tmp_path,
                                     unaccounted1=-44.0, unaccounted2=-44.0, stamps=stamps)
    pend = json.loads((tmp_path / "pending.json").read_text())
    assert pend.get("unaccounted") == -44.0, (
        "an agreed, persisting breach was discarded as a position-change race — "
        "the kill can never reach a second sighting")
    assert state["confirmed"] is False, "one sighting must never kill"
    assert state.get("note") != "not confirmed on the second read — treated as a position-change race"
    assert rc == 1


def test_the_next_tick_confirms_that_breach_and_stops_both_desks(monkeypatch, tmp_path):
    """TICK TWO, ~30s later, both desks having rewritten their claims. THE KILL MUST FIRE."""
    t1 = {"rider": "2026-09-07T06:00:00+00:00", "tournament": "2026-09-07T06:00:00+00:00"}
    _run_one_tick(monkeypatch, tmp_path, unaccounted1=-44.0, unaccounted2=-44.0, stamps=t1)

    t2 = {"rider": "2026-09-07T06:01:00+00:00", "tournament": "2026-09-07T06:00:30+00:00"}
    rc, state, calls = _run_one_tick(monkeypatch, tmp_path,
                                     unaccounted1=-44.0, unaccounted2=-44.0, stamps=t2)
    assert state["confirmed"] is True, f"a twice-seen, claim-fresh breach did not kill: {state}"
    assert calls["benched"], "confirmed but nothing was stopped"
    assert any(critical for critical, _ in calls["pages"]), "a confirmed breach must page CRITICAL"
    assert not (tmp_path / "pending.json").exists(), "pending must clear on the kill"


def test_a_genuine_second_read_disagreement_is_still_treated_as_a_race(monkeypatch, tmp_path):
    """THE FIX MUST NOT WEAKEN THE 09-03 GUARD. Reads that DISAGREE are a fill in flight, and the
    pending record must still be dropped so no later imbalance inherits a free first sighting."""
    stamps = {"rider": "2026-09-07T06:00:00+00:00", "tournament": "2026-09-07T06:00:00+00:00"}
    rc, state, calls = _run_one_tick(monkeypatch, tmp_path,
                                     unaccounted1=-44.0, unaccounted2=0.0, stamps=stamps)
    assert state["confirmed"] is False
    assert not (tmp_path / "pending.json").exists(), \
        "a real race must not leave a pending record behind"
    assert calls["benched"] == []
