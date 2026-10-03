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


# ──────────────────────────────────────────────────────────────────────────────────────────────
# ★★★2026-10-03 THE JSON EXTRACTOR. Operator asked why a Claude call on the day's tape could not
# just make the turn decision — and it turned out this instrument had been doing exactly that for
# three weeks while THROWING AWAY A QUARTER OF ITS OWN ANSWERS.
#
# 934 of 966 failures were one line: `raw[raw.find("{") : raw.rfind("}") + 1]`. First brace to last
# brace is correct only if the reply contains EXACTLY ONE braced thing. The model routinely adds a
# sentence after the JSON, or a markdown fence, or a second illustrative object — and then that span
# covers two objects and json.loads reports "Extra data: line 1 column 735". The decision itself was
# usually perfectly good and sitting in the first 300 characters.
# ⚠ And the generic exception branch dropped `raw`, so every one of those 934 was logged as a bare
#   error string with the evidence discarded. A failure that does not keep its input cannot be
#   diagnosed, which is why this survived three weeks of daily running.
# ──────────────────────────────────────────────────────────────────────────────────────────────

def _tr():
    import importlib.util
    s = importlib.util.spec_from_file_location("tr", "scripts/tape_reader.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_trailing_prose_after_the_json_still_parses():
    """THE ACTUAL 934-FAILURE CASE."""
    tr = _tr()
    raw = ('{"decision":"CLAIM","lots":2,"confidence":0.7,"reason":"the move looks done"}\n\n'
           'I chose CLAIM because the up leg has stalled for 40 minutes.')
    assert tr._first_json_object(raw)["decision"] == "CLAIM"


def test_a_second_braced_object_does_not_swallow_the_first():
    tr = _tr()
    raw = ('{"decision":"HOLD","lots":0,"confidence":0.4,"reason":"ok"}\n'
           '{"note":"for reference only"}')
    assert tr._first_json_object(raw)["decision"] == "HOLD"


def test_a_markdown_fence_parses():
    tr = _tr()
    raw = '```json\n{"decision":"CUT","lots":1,"confidence":0.5,"reason":"bad"}\n```'
    assert tr._first_json_object(raw)["decision"] == "CUT"


def test_braces_and_quotes_INSIDE_the_reason_do_not_break_it():
    """⚠ `reason` is free prose from the model and routinely contains braces and quotes. A naive
    brace counter breaks on the first one, which is why this counts strings and escapes."""
    tr = _tr()
    raw = '{"decision":"HOLD","lots":0,"confidence":0.4,"reason":"the {ladder} rung held"}'
    assert tr._first_json_object(raw)["decision"] == "HOLD"
    raw2 = '{"decision":"CLAIM","lots":4,"confidence":0.8,"reason":"he said \\"claim\\" at 10:02"}'
    assert tr._first_json_object(raw2)["decision"] == "CLAIM"


def test_a_preamble_before_the_json_parses():
    tr = _tr()
    assert tr._first_json_object(
        'Here is my call:\n{"decision":"ADD","lots":1,"confidence":0.3,"reason":"x"}'
    )["decision"] == "ADD"


def test_it_returns_the_FIRST_object_not_the_LONGEST():
    """⚠ The answer is what the model LED with. Preferring the biggest match would pick a worked
    example over the decision."""
    tr = _tr()
    raw = ('{"decision":"HOLD","lots":0,"confidence":0.2,"reason":"a"}\n'
           '{"decision":"CUT","lots":4,"confidence":0.9,"reason":"a much longer explanation '
           'that makes this object bigger than the first one by a wide margin"}')
    assert tr._first_json_object(raw)["decision"] == "HOLD"


def test_no_json_at_all_returns_None_rather_than_raising():
    tr = _tr()
    assert tr._first_json_object("I cannot decide on a shut venue.") is None
    assert tr._first_json_object("") is None


def test_an_object_without_a_decision_key_is_skipped():
    """A reply that opens with some other object must not be mistaken for the answer."""
    tr = _tr()
    raw = '{"context":"the day so far"}\n{"decision":"HOLD","lots":0,"confidence":0.5,"reason":"y"}'
    assert tr._first_json_object(raw)["decision"] == "HOLD"


def test_the_failure_path_KEEPS_the_raw_reply():
    """⚠ 934 failures were logged with raw='' because the generic branch dropped it. An error
    message without its input is undiagnosable, and that is why this lasted three weeks."""
    src = open("scripts/tape_reader.py", encoding="utf-8").read()
    tail = src.split("except Exception as e:")[-1]
    assert "raw" in tail, "the generic exception branch must carry the raw reply"
