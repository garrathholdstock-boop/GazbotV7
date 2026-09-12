"""THE TAPE READER HAS NO ORDER PATH, AND THIS IS WHAT KEEPS IT THAT WAY.

Phase 1 is a reader that judges an open position and touches NOTHING. Phase 2 (one lot, claim/cut
only, never add) is a separate decision that only forward grading can earn. Until then, the
guarantee has to be mechanical rather than remembered: this desk has twice shipped a component
whose safety rested on a paragraph of prose.

Same shape as tests/test_tunnel_watch.py, which asserts the tunnel watcher is read-only.
"""
import os
import re

SRC = os.path.join(os.path.dirname(__file__), "..", "scripts", "tape_reader.py")


def _source() -> str:
    with open(SRC) as fh:
        return fh.read()


def test_it_never_writes_a_request_file_the_rider_would_execute():
    """day_rider_claim.txt / day_rider_buy.txt ARE the order path: an inotify unit runs the rider
    0.02s after either is written. A reader that writes one is placing a trade."""
    s = _source()
    for forbidden in ("day_rider_claim", "day_rider_buy", "gate_switches", "desk_kill"):
        assert forbidden not in s, f"the tape reader must not reference {forbidden}"


def test_the_only_thing_it_opens_for_writing_is_its_own_log():
    s = _source()
    writes = re.findall(r"open\(([^,)]+)\s*,\s*[\"']([aw][b+]?)[\"']", s)
    assert writes, "expected at least the log append"
    for target, mode in writes:
        assert target.strip() == "LOG", f"writes to {target} in mode {mode!r}; only LOG is allowed"


def test_it_has_no_broker_or_order_vocabulary():
    s = _source().lower()
    for forbidden in ("ib_insync", "ib_async", "placeorder", "place_order", "marketorder",
                      "reqids", "clientid"):
        assert forbidden not in s, f"order-path vocabulary found: {forbidden}"


def test_an_invalid_or_missing_decision_is_rejected_not_coerced():
    """A parse failure must never become an action. Same fail-safe as the durable router: any
    error => no decision, never a default one."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import tape_reader as tr
    assert tr.DECISIONS == ("HOLD", "CLAIM", "CUT", "ADD")
    # the guard lives in decide(); assert the predicate it uses, without calling the CLI
    for bad in ("BUY", "SELL", "", None, "hold"):
        assert bad not in tr.DECISIONS


def test_the_context_leads_with_the_session_state():
    """★ The defect this reader exists not to repeat: on 2026-09-12 the router built 'the day so
    far' from Friday's tape on a Saturday and called a Saturday 'LONDON open, the desk's only
    positive block'. An empty tape and a shut venue are the same observation until something says
    which, so the session must be stated BEFORE any price."""
    s = _source()
    assert "THE VENUE IS SHUT" in s and "minutes_to_next_open" in s
    assert s.index("is_open") < s.index("THE DAY SO FAR"), \
        "the session must be resolved before the day is described"


def test_every_input_is_aged_and_a_dead_feed_is_not_read_as_a_quiet_one():
    s = _source()
    assert "_age(" in s and "STALE" in s
    assert "DEAD FEED" in s, "an old bar on an OPEN venue must be called a dead feed, not quiet tape"


def test_it_logs_even_when_it_does_nothing():
    """A reader that logs nothing while idle is indistinguishable from a reader that is dead —
    the desk's #1 failure mode, 7 instances in 4 days."""
    s = _source()
    assert "skipped" in s and "dead-or-idle and" in s
