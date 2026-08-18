"""The DATA/BACKUP alarm must dedupe on the SITUATION, not on the message text.

★★2026-08-18. The operator: "i am still getting these errors on telegram regularly. why havent you
fixed yet — gold shadow shadow_mgc.db not written for 42h". The underlying fault was real by then
(the gold shadow was genuinely dead), but the ALARM was re-paging every 4-hourly scan for one
unchanged fact, because the message carries a live age that increments each run and
`notify.dedupe_ok()` deliberately re-sends when the text changes.

A correct alarm repeated forever is still an alarm outage — it trains the operator to swipe past the
channel that carries naked-position alerts.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.notify import dedupe_clear, dedupe_ok  # noqa: E402

KEY = "test.data_inventory.faults"


def sig(faults):
    """The signature data_inventory builds: digits masked, order-independent."""
    return " | ".join(sorted(re.sub(r"[\d,.]+", "#", f) for f in faults))


def _f(hours):
    return [f"gold shadow    shadow_mgc.db not written for {hours}h (expect <30h)"]


def test_the_raw_message_defeats_dedupe_which_is_why_the_signature_exists(tmp_path):
    """★ THE ACTUAL BUG. Same fault, ticking age -> different text -> sends every single scan."""
    p = str(tmp_path / "d.json")
    assert dedupe_ok(KEY, _f(38)[0], cooldown_s=3600, path=p) is True
    assert dedupe_ok(KEY, _f(42)[0], cooldown_s=3600, path=p) is True, \
        "the ticking age makes every scan a 'new' message — this is the defect"


def test_the_signature_suppresses_an_unchanged_fault(tmp_path):
    p = str(tmp_path / "d.json")
    assert dedupe_ok(KEY, sig(_f(38)), cooldown_s=12 * 3600, path=p) is True
    for h in (42, 46, 50, 54):
        assert dedupe_ok(KEY, sig(_f(h)), cooldown_s=12 * 3600, path=p) is False, \
            f"{h}h is the SAME fault — it must stay quiet"


def test_a_genuinely_new_fault_pages_immediately(tmp_path):
    """A second source failing changes the situation and must NOT hide behind the cooldown."""
    p = str(tmp_path / "d.json")
    assert dedupe_ok(KEY, sig(_f(42)), cooldown_s=12 * 3600, path=p) is True
    two = _f(46) + ["trade record   gazbot7.db not written for 80h (expect <72h)"]
    assert dedupe_ok(KEY, sig(two), cooldown_s=12 * 3600, path=p) is True


def test_clear_on_resolve_re_arms_it(tmp_path):
    """A fault that heals and returns inside the cooldown must alarm again, not be swallowed."""
    p = str(tmp_path / "d.json")
    assert dedupe_ok(KEY, sig(_f(42)), cooldown_s=12 * 3600, path=p) is True
    assert dedupe_ok(KEY, sig(_f(46)), cooldown_s=12 * 3600, path=p) is False
    dedupe_clear(KEY, path=p)                       # the scan came back clean
    assert dedupe_ok(KEY, sig(_f(50)), cooldown_s=12 * 3600, path=p) is True


def test_it_fails_OPEN_on_a_corrupt_store(tmp_path):
    """★ Suppression must only ever follow a SUCCESSFUL positive check. A broken dedupe file must
    never eat an alarm — that is the instrument-reports-healthy failure in its purest form."""
    p = str(tmp_path / "corrupt.json")
    open(p, "w").write("{ this is not json")
    assert dedupe_ok(KEY, sig(_f(42)), cooldown_s=12 * 3600, path=p) is True


def test_signature_is_order_independent(tmp_path):
    a = sig(["alpha not written for 5h", "beta not written for 9h"])
    b = sig(["beta not written for 12h", "alpha not written for 40h"])
    assert a == b, "the same SET of faulting sources is the same situation"
