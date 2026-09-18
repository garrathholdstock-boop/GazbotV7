"""THE PRE-EVENT ALERT — it says WHEN, and it must never say WHICH WAY.

★★★ THE TRADE IT EXISTS FOR (2026-09-16). FOMC decision 18:00Z. He held LONG 4 through it and
bought AGAIN at 18:52 — T+52, with the slide still running to its low at T+85 — for -$1,272 on one
trade. The day was -$833; without it, +$439. *"if i knew the fed was making a decision i probably
wouldve held off and waited."*

⚠⚠ THE FAILURE MODE THESE TESTS GUARD. His loss was a DIRECTION error. An alert that implied a
side would have cost him more, not less — every direction study on this desk comes back ~50/50
([[break-then-join-direction-is-a-coin]]). So the message must carry the measured SIZE of the move
and the explicit disclaimer, and must never carry a side.
"""
import datetime as dt
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import event_alert as ea

SRC = "/home/alphabot/gazbot7/scripts/event_alert.py"


def _fake_event(minutes_out, kind="FOMC"):
    t = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=minutes_out)
    return [{"date": t.date().isoformat(), "kind": kind, "name": "FOMC decision",
             "utc": t.isoformat(), "confirmed": True, "in_hours": minutes_out / 60}]


def _run(monkeypatch, tmp_path, minutes_out, kind="FOMC"):
    sent = []
    monkeypatch.setattr(ea, "LOG", str(tmp_path / "a.log"))
    monkeypatch.setattr(ea, "STATE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(ea.ec, "upcoming", lambda **k: _fake_event(minutes_out, kind))
    import gazbot7.notify as n
    monkeypatch.setattr(n, "notify", lambda m, **kw: sent.append(m))
    monkeypatch.setattr(n, "dedupe_ok", lambda *a, **kw: True)
    ea.main()
    return sent


def test_it_pages_at_T_minus_60(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, 55)


def test_it_pages_at_T_minus_15(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, 12)


def test_it_is_SILENT_between_the_bands_and_far_out(monkeypatch, tmp_path):
    """⚠ Steady state must be silent so CHANGE is loud. Paging every 5 min for an hour is how a
    critical channel becomes wallpaper — this desk already learned that the expensive way."""
    for mins in (300, 40, 30, 20, 3):
        assert not _run(monkeypatch, tmp_path, mins), f"it paged at T-{mins}"


def test_the_bands_are_WIDER_than_the_timer_tick():
    """★ THE SILENT-FAILURE GUARD. The timer runs every 5 min; a band narrower than that can fall
    between two runs and never fire at all — an alarm that exists and never pages."""
    for hi, lo, label in ea.BANDS:
        assert hi - lo >= 6, f"band {label} is {hi-lo} min wide against a 5-min tick"


def test_the_message_carries_the_MEASURED_size_never_a_direction(monkeypatch, tmp_path):
    msg = _run(monkeypatch, tmp_path, 12)[0]
    assert "WHEN, NOT WHICH WAY" in msg
    assert "2.7-3.5x" in msg, "the page must carry OUR measured impact, not folklore"
    for side in (" BUY ", " SELL ", "go long", "go short", "expect a", "likely to"):
        assert side.lower() not in msg.lower(), f"the alert implied a side: {side!r}"


def test_it_names_the_open_position(monkeypatch, tmp_path):
    """★ At T-15 the question stops being 'trade or not' and becomes 'flat or not'."""
    import json
    p = tmp_path / "st.json"
    p.write_text(json.dumps({"qty": 4.0, "entry": 29433.0, "direction": 1, "closed": False}))
    monkeypatch.setattr(ea, "STATE", str(p))
    sent = []
    monkeypatch.setattr(ea, "LOG", str(tmp_path / "a.log"))
    monkeypatch.setattr(ea.ec, "upcoming", lambda **k: _fake_event(12))
    import gazbot7.notify as n
    monkeypatch.setattr(n, "notify", lambda m, **kw: sent.append(m))
    monkeypatch.setattr(n, "dedupe_ok", lambda *a, **kw: True)
    ea.main()
    assert "YOU ARE LONG 4 @ 29433.0" in sent[0]


def test_the_uncertainty_is_stated_not_buried(monkeypatch, tmp_path):
    """⚠ 5 event days, split chosen after seeing it. PROMISING, NOT PROVEN — and the page says so,
    because a number he stands aside on has to carry its own error bar."""
    msg = _run(monkeypatch, tmp_path, 12)[0]
    assert "5 days only" in msg and "not proven" in msg


def test_it_holds_no_order_path():
    """⚠⚠⚠ READ-ONLY, asserted against the SOURCE."""
    src = open(SRC).read()
    for banned in ("placeOrder", "MarketOrder", "LimitOrder", "connectAsync", "IB()",
                   "gate_switches", "day_rider_claim", "day_rider_buy"):
        assert banned not in src, f"the alert reached for {banned}"


def test_dedupe_is_keyed_on_the_event_not_the_text():
    """⚠ The minute count changes every tick and dedupe re-sends on ANY text change — keying on the
    message would page every 5 minutes for the whole hour."""
    src = open(SRC).read()
    assert 'dedupe_ok(f"event_alert.{e[\'date\']}.{e[\'kind\']}.{label}"' in src
