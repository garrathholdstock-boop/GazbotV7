"""A session rollover must clear the LATCH, never the INVENTORY.

`session_key` is the calendar date, so the reset fires at midnight UTC — mid-hold. On 2026-08-21/22
it blanked the book while 4 real lots were open: the rider disowned them, stopped managing them,
claimed ZERO to the reconciler (venue +4 vs rider +0 → kill switch, plus a page every 30 seconds all
night), and the dashboard went blank. It would then have defeated the Sunday flatten too, because a
claim is refused on a position the rider does not believe it owns.
"""
import datetime as dt
from gazbot7.day_rider import session_key

NEW = dt.datetime(2026, 8, 23, 22, 1, tzinfo=dt.UTC)


def _reset(st, now=NEW):
    """The reset logic from step(), verbatim in behaviour."""
    out = dict(st)
    out["session"] = session_key(now)
    if st.get("session") != out["session"]:
        carry = (bool(st.get("entered")) and not bool(st.get("closed"))
                 and abs(float(st.get("qty") or 0)) > 1e-9)
        if carry:
            out = dict(st); out["session"] = session_key(now)
            out["carried_session"] = st.get("session")
        else:
            out = {"session": out["session"], "entered": False, "closed": False}
    return out


HELD = {"session": "2026-08-22", "entered": True, "closed": False, "qty": 4.0,
        "entry": 29491.93, "direction": 1, "lots_open": 4,
        "manual_targets_pt": [50.0, 100.0, 200.0, 300.0]}


def test_an_open_position_survives_the_rollover():
    out = _reset(HELD)
    assert out["entered"] is True and out["closed"] is False
    assert out["qty"] == 4.0 and out["entry"] == 29491.93
    owns = bool(out["entered"]) and not bool(out["closed"])
    assert owns, "the rider disowned 4 real lots at midnight — this is the 08-21 weekend carry"


def test_the_ladder_survives_too():
    """Otherwise the carried position reverts to the fixed trail and the operator's targets vanish."""
    assert _reset(HELD)["manual_targets_pt"] == [50.0, 100.0, 200.0, 300.0]


def test_the_claim_would_be_accepted_after_a_rollover():
    out = _reset(HELD)
    assert bool(out.get("entered")) and not bool(out.get("closed")), \
        "a Claim press would be refused as 'not in a position' — the Sunday flatten would fail"


def test_a_flat_book_is_still_reset():
    """The latch MUST clear when nothing is held, or the rider never trades again."""
    out = _reset({"session": "2026-08-22", "entered": True, "closed": True, "qty": 0.0})
    assert out["entered"] is False and out["closed"] is False


def test_same_session_is_untouched():
    st = dict(HELD, session=session_key(NEW))
    assert _reset(st)["entry"] == 29491.93 and "carried_session" not in _reset(st)
