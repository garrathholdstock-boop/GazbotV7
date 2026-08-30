"""A venue failure during the flatten window must PAGE. Regression for the weekend carry.

2026-08-21: the gateway wedged and day_rider's exception handler logged 100 consecutive
TimeoutErrors across the entire 20:40-21:00 flatten window, silently. Four naked lots went through
the CME halt and into the weekend. "Fail closed" is correct for TRADING and catastrophic for
FLATTENING: the safe direction there is to shout. Nothing else covers it — the reconciler cannot
read the venue either, so it reports "IBKR truth unavailable" rather than a breach.
"""
import asyncio, datetime as dt, types, pytest
from gazbot7 import day_rider as D

FLAT, HALT = D.FLAT_UTC_MIN, D.HALT_UTC_MIN


class Boom:
    def __getattr__(self, n): raise TimeoutError()


def _step(mod, state, monkeypatch, sent):
    async def dead_venue(cfg): raise TimeoutError()
    monkeypatch.setattr(D, "_venue", dead_venue)
    monkeypatch.setattr(D, "enabled", lambda: True)
    monkeypatch.setattr(D, "load_state", lambda: dict(state))
    monkeypatch.setattr(D, "save_state", lambda o: None)
    monkeypatch.setattr(D, "dedupe_ok", lambda *a, **k: True, raising=False)
    import gazbot7.notify as N
    monkeypatch.setattr(N, "dedupe_ok", lambda *a, **k: True)
    now = dt.datetime(2026, 8, 21, mod // 60, mod % 60, tzinfo=dt.UTC)

    class FrozenDT(dt.datetime):
        @classmethod
        def now(cls, tz=None): return now
    monkeypatch.setattr(D.dt, "datetime", FrozenDT)
    cfg = types.SimpleNamespace(capture_path="/dev/null", symbol="MNQ")
    return asyncio.run(D.step(cfg, notify=lambda m, **k: sent.append((m, k))))


def _held_state(session=None):
    d = {"entered": True, "closed": False, "qty": 4.0, "entry": 29491.93, "direction": 1}
    if session is not None:
        d["session"] = session
    return d


HELD = _held_state()   # NO session key -> step() resets it, exactly like a midnight rollover


@pytest.mark.parametrize("mod", [FLAT, FLAT + 5, HALT - 1, HALT + 10])
def test_a_dead_venue_holding_a_position_pages(mod, monkeypatch):
    sent = []
    out = _step(mod, HELD, monkeypatch, sent)
    assert sent, f"minute {mod//60:02d}:{mod%60:02d} — CANNOT FLATTEN and said NOTHING"
    msg, kw = sent[0]
    assert kw.get("critical") is True, "an unflattenable position is not a routine alert"
    assert "CANNOT FLATTEN" in msg
    assert out.get("flatten_blocked") is True


def test_past_the_halt_the_alert_says_overnight(monkeypatch):
    sent = []
    _step(HALT + 10, HELD, monkeypatch, sent)
    assert "going overnight" in sent[0][0]


@pytest.mark.parametrize("mod", [9 * 60, 13 * 60 + 30, FLAT - 1])
def test_before_the_flatten_window_a_dead_venue_does_not_page(mod, monkeypatch):
    """Outside the window a broken read is an ordinary retry — pre-open outages must not cry wolf."""
    sent = []
    _step(mod, HELD, monkeypatch, sent)
    assert not sent, "paged for a routine pre-window venue error"


def test_flat_and_dead_does_not_page(monkeypatch):
    """No position, no overnight risk — the gateway being down is the watchdog's business."""
    sent = []
    _step(FLAT + 5, {"entered": False, "closed": True, "qty": 0.0}, monkeypatch, sent)
    assert not sent


def test_the_alarm_survives_a_session_rollover(monkeypatch):
    """★ THE CASE THAT ACTUALLY HAPPENED. step() wipes `entered` when the session key changes, and
    the 08-21 carry crossed midnight while 4 lots were open — so an alarm reading only the live
    dict falls silent at the exact moment the position becomes an overnight one. It must also read
    the pre-reset book."""
    sent = []
    out = _step(HALT + 10, _held_state(session="STALE-SESSION"), monkeypatch, sent)
    assert sent, "went quiet across the rollover — this is the weekend carry, undetected"
    assert "4.0 lots" in sent[0][0] and "29491.93" in sent[0][0], \
        "alarm fired but could not say WHAT is held"


def test_a_current_session_still_pages(monkeypatch):
    import datetime as _dt
    sent = []
    now = _dt.datetime(2026, 8, 21, (HALT + 10) // 60, (HALT + 10) % 60, tzinfo=_dt.UTC)
    _step(HALT + 10, _held_state(session=D.session_key(now)), monkeypatch, sent)
    assert sent
