"""The claim fast path must be EDGE-triggered, and the 60s tick must remain the floor.

★2026-08-19. The operator's manual claims are the best exits in the book — three of them took $726
in 23 minutes on the day this was written — but the button wrote a flag the rider only read on its
next `*:*:05` tick, so a press could wait up to 60 seconds before an order existed. Measured gap on
the day: tracked peak 29458.75, claim filled 29470.75 = 12pt = $48.

Two properties are pinned here because getting either wrong is worse than the latency was.
"""
import pathlib

UNIT = pathlib.Path(__file__).parent.parent / "ops" / "systemd" / "gazbot7-day-rider-claim.path"


def test_the_trigger_is_edge_not_level():
    """★ THE HAZARD. `claim_requested()` documents an orphan: a tick can exit by hard-flat or venue
    stop before the claim branch is reached, "leaving the file behind with nothing to consume it"
    for up to CLAIM_MAX_AGE_S = 15 minutes. PathExists is LEVEL-triggered and would restart the
    rider in a tight loop for that whole quarter of an hour, hammering the shared IB gateway.
    Observed live: after a trigger with the rider closed, the flag was still on disk."""
    txt = UNIT.read_text()
    assert "PathModified=" in txt
    assert "PathExists=" not in txt, "level-triggered: an orphaned flag would loop the rider"
    assert "PathExistsGlob=" not in txt


def test_it_triggers_the_real_rider_and_adds_no_second_order_path():
    """The fast path changes WHEN the rider reads the flag, never WHO places the order. Every
    ownership check, venue-first gate and stop cancellation stays inside the rider — a button that
    reached the broker directly is how 2026-08-06 halted the desk for 11 minutes."""
    txt = UNIT.read_text()
    assert "Unit=gazbot7-day-rider.service" in txt
    assert "ExecStart" not in txt, "a .path unit must not run anything of its own"


def test_the_watched_file_is_the_one_the_endpoint_writes():
    """A fast path pointed at the wrong filename is an instrument reporting healthy about something
    it never checks — this desk's most common failure."""
    import re
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
    from gazbot7.day_rider import CLAIM_FILE
    watched = re.search(r"PathModified=(\S+)", UNIT.read_text()).group(1)
    assert watched == CLAIM_FILE, f"watching {watched} but the rider reads {CLAIM_FILE}"


def test_the_timer_remains_the_floor():
    """A fast lane over a working road, never a replacement for it. If this unit is dead the claim
    must still be picked up on the next tick."""
    txt = UNIT.read_text()
    assert "floor" in txt.lower() and "fallback" not in txt.split("[Path]")[1]
