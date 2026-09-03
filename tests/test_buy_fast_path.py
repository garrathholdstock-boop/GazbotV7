"""The manual-entry fast path: edge-triggered, pointed at the right file, and the tick still the floor.

★2026-09-03. The claim button was cut from up to 60s to 0.02s on 2026-08-19 and the ENTRY button was
left behind — the fast path existed for the exit only. The operator pressed BUY on that morning's
compression-break alert and his press could have waited a full minute for an order to exist, on a
tape that then moved 42.5pt in 23 minutes. Measured after this unit: a write reaches a COMPLETED
rider tick in 1.35s, twice, with the write deliberately made at :46 so no `*:*:05` timer tick could
be mistaken for it.

These pin the two properties that are worse to get wrong than the latency was.
"""
import pathlib

UNIT = pathlib.Path(__file__).parent.parent / "ops" / "systemd" / "gazbot7-day-rider-buy.path"


def test_the_trigger_is_edge_not_level():
    """★ THE HAZARD. `buy_requested()` is age-bounded at BUY_MAX_AGE_S = 5 MINUTES, so a request the
    rider declines to act on can legitimately sit on disk that long — and it demonstrably does:
    while a position is open the `owns_position` branch is taken and the request is never read.
    PathExists is LEVEL-triggered and would restart the rider in a tight loop for those five minutes
    against the shared IB gateway."""
    txt = UNIT.read_text()
    assert "PathModified=" in txt
    assert "PathExists=" not in txt, "level-triggered: an unread request would loop the rider"
    assert "PathExistsGlob=" not in txt


def test_it_triggers_the_real_rider_and_adds_no_second_order_path():
    """The fast path changes WHEN the rider reads the request, never WHO places the order.
    venue_first_ok(), the ownership check and the booking path all stay inside the rider — a button
    that reached the broker directly is how 2026-08-06 halted the desk for 11 minutes."""
    txt = UNIT.read_text()
    assert "Unit=gazbot7-day-rider.service" in txt
    assert "ExecStart" not in txt, "a .path unit must not run anything of its own"


def test_the_watched_file_is_the_one_the_endpoint_writes():
    """A fast path pointed at the wrong filename is an instrument reporting healthy about something
    it never checks — this desk's most common failure, and invisible until the day it matters."""
    import re
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
    from gazbot7.day_rider import BUY_FILE
    watched = re.search(r"PathModified=(\S+)", UNIT.read_text()).group(1)
    assert watched == BUY_FILE, f"watching {watched} but the rider reads {BUY_FILE}"


def test_it_does_not_watch_the_claim_file():
    """One unit per button. The claim path has its own, with its own 15-minute orphan reasoning;
    merging them would make either unit's name a lie about what it triggers on."""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
    from gazbot7.day_rider import CLAIM_FILE
    assert CLAIM_FILE not in UNIT.read_text()


def test_the_timer_remains_the_floor():
    """A fast lane over a working road. If this unit is dead, the press must still be picked up on
    the next `*:*:05` tick exactly as before."""
    assert "floor" in UNIT.read_text().lower()
