"""strategy — the decision half: gate → OPEN intent, managed exits → CLOSE intent,
plus the freshness stand-down and the one-in-flight-intent guard. Pure logic; no
sockets — state is fed via the on_* methods and decide() is driven with an
explicit clock."""

from __future__ import annotations

from gazbot7.config import RunConfig
from gazbot7.strategy import Strategy


def _bar(ts, o, h, l, c, v):
    return {"symbol": "MNQ", "tf": "5s", "ts": ts, "o": o, "h": h, "l": l, "c": c, "v": v, "closed": True}


def _thrust_up(end_ts=2000):
    """20 bars ending at end_ts: 15 flat @100 then 5 up-bars of +0.7 (clears thr)."""
    msgs = []
    ts = end_ts - 19 * 5
    for _ in range(15):
        msgs.append(_bar(ts, 100.0, 100.5, 99.5, 100.0, 10)); ts += 5
    px = 100.0
    for j in range(5):
        px += 0.7
        vol = 40 if j == 4 else 10
        msgs.append(_bar(ts, px - 0.7, max(px, px - 0.7) + 0.2, min(px, px - 0.7) - 0.2, px, vol)); ts += 5
    return msgs, end_ts


def _strat(**kw):
    cfg = RunConfig(gate="thrust", gate_params={"thr": 1.5}, **kw)
    return Strategy(cfg)


def _load(s, end_ts=2000):
    msgs, last = _thrust_up(end_ts)
    for m in msgs:
        s.on_bar(m)
    return last


def _tape(now_ms, last, **kw):
    return {"ts_ms": now_ms - 100, "net_flow": kw.get("net_flow", 0.0),
            "win_price_delta": kw.get("wpd", 0.0), "last": last, "in_rth": True}


def test_fires_open_when_flat_and_gate_triggers():
    s = _strat()
    end = _load(s)
    now = end * 1000 + 100
    s.on_tape(_tape(now, 103.5))
    intent = s.decide(now)
    assert intent is not None
    assert intent["action"] == "OPEN" and intent["side"] == "LONG" and intent["gate"] == "thrust"
    assert intent["meta"]["entry_atr"] > 0


def test_stands_down_when_tape_stale():
    s = _strat()
    end = _load(s)
    now = end * 1000 + 100
    s.on_tape({"ts_ms": now - 20_000, "net_flow": 0, "win_price_delta": 0, "last": 103.5, "in_rth": True})
    assert s.decide(now) is None  # tape 20s stale → stand down


def test_stands_down_when_bars_stale():
    s = _strat()
    end = _load(s)
    now = end * 1000 + 100_000  # 100s since the last bar
    s.on_tape(_tape(now, 103.5))
    assert s.decide(now) is None  # bars stale (farm drop) → stand down


def test_one_in_flight_intent_guard():
    s = _strat()
    end = _load(s)
    now = end * 1000 + 100
    s.on_tape(_tape(now, 103.5))
    assert s.decide(now)["action"] == "OPEN"
    s.on_tape(_tape(now + 1000, 103.6))
    assert s.decide(now + 1000) is None  # pending OPEN, still flat → no duplicate


def test_pending_clears_on_core_held_then_manages_target():
    s = _strat(target_r=2.0)
    end = _load(s)
    now = end * 1000 + 100
    s.on_tape(_tape(now, 103.5))
    assert s.decide(now)["action"] == "OPEN"          # sends OPEN, pending
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 2.0})  # confirms → clears
    s.on_tape(_tape(now + 2000, 110.0))               # well past 2R target (100 + 2·2)
    intent = s.decide(now + 2000)
    assert intent["action"] == "CLOSE" and intent["reason"] == "TARGET"


def test_managed_adverse_cut_when_held():
    s = _strat(adverse_cut_atr=1.5)
    end = _load(s)
    now = end * 1000 + 100
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 2.0})
    s.on_tape(_tape(now, 96.0))  # 4 pts offside ≥ 1.5·ATR(2)=3, never green
    intent = s.decide(now)
    assert intent["action"] == "CLOSE" and intent["reason"] == "ADVERSE_CUT"


def test_pending_timeout_frees_action():
    s = _strat()
    end = _load(s)
    now = end * 1000 + 100
    s.on_tape(_tape(now, 103.5))
    assert s.decide(now)["action"] == "OPEN"
    later = now + 9_000  # > 8s pending timeout
    s.on_tape(_tape(later, 103.7))
    assert s.decide(later) is not None  # timed out → free to act again


def test_no_open_window_suppresses_entry():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    close_soon = int(datetime(2026, 7, 15, 16, 50, tzinfo=et).timestamp())  # 10 min before close
    s = _strat()
    _load(s, end_ts=close_soon)
    now = close_soon * 1000 + 100
    s.on_tape(_tape(now, 103.5))
    assert s.decide(now) is None  # thrust would fire, but the no-open window blocks it


def test_entry_fires_midday_outside_window():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    midday = int(datetime(2026, 7, 15, 12, 0, tzinfo=et).timestamp())
    s = _strat()
    _load(s, end_ts=midday)
    now = midday * 1000 + 100
    s.on_tape(_tape(now, 103.5))
    assert s.decide(now)["action"] == "OPEN"  # open session, well before close


def test_rejected_intent_result_clears_pending():
    s = _strat()
    end = _load(s)
    now = end * 1000 + 100
    s.on_tape(_tape(now, 103.5))
    op = s.decide(now)
    s.on_intent_result({"iid": op["iid"], "accepted": False, "reason": "already in position"})
    s.on_tape(_tape(now + 500, 103.6))
    assert s.decide(now + 500) is not None  # rejection cleared pending
