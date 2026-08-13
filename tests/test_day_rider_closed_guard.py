"""The manage-block guard must respect the `closed` latch.

★ REGRESSION TEST FOR A LIVE INCIDENT (2026-08-13). The guard was
`abs(net) > 1e-9 and st.get("entered")` — no `closed` check — and `net` is the SHARED ACCOUNT net.
After the operator claimed the day-rider's LONG at 14:26 (booked once, correctly), the tournament
opened its own shorts at 15:53. That made `net` non-zero, `entered` was still true for the session,
and the rider re-entered the manage path on a position it had already closed: it re-evaluated the
stale trail against the ORIGINAL entry/peak and booked a phantom exit every minute — four rows,
$1,551 of profit that never existed.

The test is written against the STATE SHAPE rather than the whole async tick, because the bug was
purely in the predicate. If the predicate is right, the branch cannot run on a closed position no
matter what the other desk is doing.
"""


def manage_should_run(net: float, st: dict) -> bool:
    """Mirror of day_rider.py's section-2 guard. Kept in lockstep with the source line."""
    return abs(net) > 1e-9 and bool(st.get("entered")) and not bool(st.get("closed"))


CLAIMED = {"entered": True, "closed": True, "qty": 2.0, "direction": 1, "entry": 30024.25}
RIDING = {"entered": True, "closed": False, "qty": 2.0, "direction": 1, "entry": 30024.25}
IDLE = {"entered": False, "closed": False}


def test_the_incident_does_not_recur():
    # The exact 15:53 condition: our position is CLOSED, but the tournament is short 2 on the
    # shared account so the venue net reads -2. The manage block must NOT run.
    assert manage_should_run(-2.0, CLAIMED) is False
    # ...and it must stay false however large the other desk's position gets.
    for other in (-4.0, -6.0, -8.0, 6.0):
        assert manage_should_run(other, CLAIMED) is False, other


def test_a_genuinely_open_position_is_still_managed():
    # The guard must not over-correct: while we really are riding, the block has to run or the
    # trail never fires and the 20:40 flat becomes the only exit.
    assert manage_should_run(2.0, RIDING) is True
    # Our own 2 lots netted against a tournament short still leaves us holding — the block must run
    # so the trail is evaluated. (Direction and size come from our own book inside the block, which
    # is why a misleading net is safe there but was NOT safe in the guard.)
    assert manage_should_run(-1.0, RIDING) is True


def test_no_position_and_flat_venue_do_nothing():
    assert manage_should_run(0.0, RIDING) is False
    assert manage_should_run(0.0, CLAIMED) is False
    assert manage_should_run(-2.0, IDLE) is False


def test_guard_matches_the_source_line():
    """Fails loudly if the predicate in day_rider.py drifts from the mirror above."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    assert 'if abs(net) > 1e-9 and st.get("entered") and not st.get("closed"):' in src, (
        "the section-2 manage guard changed — update manage_should_run() and re-check the "
        "2026-08-13 phantom-rebook incident cannot recur")
