"""THE "LOOKED AND PASSED" BUTTON — the negative example, and it must be unable to trade.

★★★ THE GAP IT CLOSES (2026-09-18). Every record in operator_reads.jsonl is a "yes". You cannot
learn a decision boundary from one side of it, and that is exactly why 119 calibrations failed to
reproduce his judgement — every one reverse-engineered from the OUTCOME, because nobody had ever
recorded the times he looked and did nothing.

⚠⚠⚠ THE SAFETY PROPERTY IS STRUCTURAL, NOT A CHECK. It writes `operator_pass.txt`, a filename the
day rider has never heard of. The button cannot place an order however it is pressed, replayed or
aged — there is no code path from that file to the broker.
"""
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

from gazbot7 import web

RIDER = "/home/alphabot/gazbot7/src/gazbot7/day_rider.py"
CAP = "/home/alphabot/gazbot7/scripts/capture_operator_read.py"
JS = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.js"
HTML = "/home/alphabot/gazbot7/src/gazbot7/web_static/app.html"


def test_the_rider_has_never_heard_of_the_pass_file():
    """★★★ THE WHOLE SAFETY ARGUMENT. If the rider ever reads this filename, the button becomes an
    order path and this test is the only thing that would notice."""
    src = open(RIDER).read()
    assert "operator_pass" not in src, (
        "day_rider now references operator_pass.txt — the PASS button has become an order path")


def test_it_writes_the_pass_file_and_places_nothing(tmp_path):
    out = web.operator_pass_post(json.dumps({"note": "choppy, no thanks"}).encode(), str(tmp_path))
    assert out["ok"] is True
    body = (tmp_path / "operator_pass.txt").read_text()
    assert "|PASS|" in body and "choppy, no thanks" in body
    # nothing that any order path reads may have been created
    assert not (tmp_path / "day_rider_buy.txt").exists()
    assert not (tmp_path / "day_rider_claim.txt").exists()


def test_it_needs_no_PIN(tmp_path):
    """⚠ The PIN on BUY/SELL guards an ORDER. This places none, and friction that makes him skip
    recording a pass defeats the point — the sample IS the product."""
    assert web.operator_pass_post(b"{}", str(tmp_path))["ok"] is True


def test_a_malformed_body_still_records(tmp_path):
    """⚠ A pass lost to a JSON error is a data point gone forever; there is no retry from a human
    who has already moved on."""
    assert web.operator_pass_post(b"not json at all", str(tmp_path))["ok"] is True
    assert (tmp_path / "operator_pass.txt").exists()


def test_the_note_cannot_break_the_record_format(tmp_path):
    """⚠ The file is pipe-delimited and the parser partitions on '|' — a note containing one would
    truncate or corrupt the stamp downstream."""
    web.operator_pass_post(json.dumps({"note": "a|b\nc" * 80}).encode(), str(tmp_path))
    body = (tmp_path / "operator_pass.txt").read_text()
    assert body.count("|") == 2, f"note leaked a delimiter: {body[:120]}"
    assert "\n" not in body


def test_the_capture_script_knows_the_pass_kind():
    src = open(CAP).read()
    assert '"pass": f"{GB}/data/operator_pass.txt"' in src
    assert '"pass": "/run/gazbot7_press_pass.txt"' in src


def test_the_path_unit_is_PathModified_not_PathExists():
    """⚠⚠ Nothing ever CONSUMES a pass file, so PathExists would re-trigger continuously and
    manufacture a stream of presses he never made — poisoning the very dataset this builds."""
    # ⚠ Read DIRECTIVES, not comments. The unit's own comment explains why PathExists is wrong, and
    # a naive substring check fails on that explanation — a test that trips over its own
    # documentation. This is the third time that shape has appeared; assert the settings.
    lines = [l.strip() for l in
             open("/home/alphabot/gazbot7/ops/systemd/gazbot7-capture-read-pass.path")
             if l.strip() and not l.strip().startswith("#")]
    assert any(l.startswith("PathModified=") for l in lines), "the unit does not watch on modify"
    assert not any(l.startswith("PathExists") for l in lines), (
        "PathExists would re-trigger forever — nothing consumes a pass file")


def test_the_button_asks_for_no_pin_and_no_confirm():
    js = open(JS).read()
    i = js.index('$("pass-btn")')
    block = js[i:i + 1400]
    assert "api/control/pass" in block
    assert "window.prompt" not in block, "the PASS button asks for a PIN — friction loses the sample"
    assert "window.confirm" not in block, "the PASS button asks for confirmation"
    assert 'fetch("api/control/pass"' in block, "leading-slash URL would resolve off /v7/ and 404"


def test_the_button_exists_in_the_page_with_a_note_field():
    h = open(HTML).read()
    assert 'id="pass-btn"' in h and 'id="pass-note"' in h
    assert "Places no order" in h, "the button must say plainly that it trades nothing"
