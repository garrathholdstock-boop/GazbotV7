"""A BUY pressed while the rider HOLDS must be refused LOUDLY — never swallowed.

★★★ THE SILENCE. `step()` returns on every path of the MANAGE block, so while the rider held a
position the manual-entry check (section 3) was never reached. The request was not refused, not
consumed and not reported: it sat in the file and aged out after BUY_MAX_AGE_S while the dashboard
had already answered "requested". A button that reports success and does nothing.

★ OPERATOR'S CALL, asked directly on 2026-09-03 — ADD LOTS or REFUSE LOUDLY: **"refuse loudly"**.
So: place nothing, CONSUME the request (an unread file is what made it silent), and page critical.

⚠ SELL is refused here too. This is the ENTRY button; the exit is the Claim buttons, which size from
our own book behind the ownership check. One control that means "open" or "close" depending on state
is how a shared netted account gets an exit sized by an entry path.
"""
import datetime as dt
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import gazbot7.day_rider as dr


class _Notes:
    """⚠ NOT a list subclass. `day_rider` guards every send with `if notify:`, and an EMPTY list is
    FALSY — a list-based spy silently records nothing and the test passes against a mute build."""

    def __init__(self):
        self.sent = []

    def __call__(self, msg, critical=False):
        self.sent.append((msg, critical))


def _write_buy(tmp_path, side="BUY", qty=4, when=None):
    f = tmp_path / "day_rider_buy.txt"
    when = when or dt.datetime.now(dt.UTC)
    f.write_text(f"{when.isoformat()}|{side}|{qty}|100,200,400,600\n")
    dr.BUY_FILE = str(f)
    return f


HELD = {"entered": True, "closed": False, "direction": -1, "qty": 4.0, "entry": 29553.25}


def test_a_buy_while_holding_is_refused_and_the_request_is_consumed(tmp_path):
    f = _write_buy(tmp_path)
    out, notes = dict(HELD), _Notes()
    assert dr.refuse_buy_while_holding(out, notes, where="managing an open position") is True
    assert not f.exists(), "the request was left on disk — it can fire later, which is the old bug"
    assert len(notes.sent) == 1 and notes.sent[0][1] is True, "a refusal the operator cannot see is the bug"
    msg = notes.sent[0][0]
    assert "REFUSED" in msg and "NOTHING WAS PLACED" in msg
    assert "4" in msg and "SHORT" in msg, f"the refusal must say what is already held: {msg}"
    assert out["buy_refused"]["side"] == "BUY" and out["buy_refused"]["qty"] == 4


def test_sell_while_holding_is_refused_too(tmp_path):
    _write_buy(tmp_path, side="SELL", qty=2)
    out, notes = dict(HELD), _Notes()
    assert dr.refuse_buy_while_holding(out, notes, where="managing an open position") is True
    assert "SELL" in notes.sent[0][0] and "Claim" in notes.sent[0][0], "must point the exit at the Claim buttons"


def test_no_request_means_no_noise(tmp_path):
    dr.BUY_FILE = str(tmp_path / "absent.txt")
    out, notes = dict(HELD), _Notes()
    assert dr.refuse_buy_while_holding(out, notes, where="x") is False
    assert notes.sent == [], "steady state must be silent so a change is loud"


def test_an_expired_request_is_not_reported_as_a_refusal(tmp_path):
    """An aged-out press was never going to fire; announcing it would be noise about nothing."""
    old = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=dr.BUY_MAX_AGE_S + 60)
    f = _write_buy(tmp_path, when=old)
    out, notes = dict(HELD), _Notes()
    assert dr.refuse_buy_while_holding(out, notes, where="x") is False
    assert notes.sent == []
    assert not f.exists(), "buy_requested() must still clear an expired request"


def test_both_return_paths_answer_the_press():
    """★ THE REGRESSION GUARD. Both branches that RETURN while holding must call the refusal —
    otherwise the press is swallowed exactly as before, and no behavioural test would show it."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    manage = src.index('if abs(net) > 1e-9 and st.get("entered") and not st.get("closed"):')
    assert "refuse_buy_while_holding" in src[manage:manage + 800], (
        "the MANAGE block returns on every path — without the refusal a press made while holding "
        "is never seen at all")
    torn = src.index("elif owns_position:")
    assert "refuse_buy_while_holding" in src[torn:torn + 800], (
        "the book/venue-mismatch branch returns too and swallowed the press the same way")
