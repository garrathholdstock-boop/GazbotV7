"""The two-gate live lineup (grind conviction + rgv 2R, single-position, first-to-fire).
Grind fires the clean trend, conviction-sized; its exit routes to the vol-adaptive chandelier."""
from __future__ import annotations

from datetime import UTC, datetime

from gazbot7.config import RunConfig, live_gates
from gazbot7.strategy import Strategy

_TS = int(datetime(2026, 7, 15, 16, 0, tzinfo=UTC).timestamp())


def _bar(ts, o, h, l, c, v):
    return {"symbol": "MNQ", "tf": "5s", "ts": ts, "o": o, "h": h, "l": l, "c": round(c, 4), "v": v, "closed": True}


def _trend_up(end_ts=_TS):
    closes = [100.0] * 5 + [100.8, 101.6, 102.4, 103.2, 104.0] + [104.0]
    vols = [12] * 5 + [12, 14, 16, 18, 60] + [20]
    msgs, prev, start = [], 100.0, end_ts - 11 * 60
    for i, cl in enumerate(closes):
        ms = start + i * 60
        for j in range(12):
            c = prev + (cl - prev) * (j + 1) / 12
            msgs.append(_bar(ms + j * 5, c, c + 0.15, c - 0.15, c, vols[i] / 12))
        prev = cl
    return msgs


def _tape(now_ms, last, **kw):
    return {"ts_ms": now_ms - 100, "net_flow": kw.get("net_flow", 0.0),
            "win_price_delta": kw.get("wpd", 0.0), "last": last, "in_rth": True}


def _load(s):
    for m in _trend_up():
        s.on_bar(m)


def test_twogate_grind_fires_conviction_sized():
    s = Strategy(RunConfig(gates=live_gates()))
    _load(s)
    now = _TS * 1000
    s.on_tape(_tape(now, 104.0))
    s.on_core_position({"flat": True})
    intent = s.decide(now)
    assert intent is not None and intent["action"] == "OPEN"
    assert intent["gate"] == "grind"          # momentum gate takes the clean trend
    assert intent["side"] == "LONG"
    assert intent["qty"] in (1, 2)            # conviction-sized (clean trend → full)
    assert s._active is not None and s._active.name == "grind"


def test_twogate_grind_exit_routes_to_chandelier():
    s = Strategy(RunConfig(gates=live_gates()))
    _load(s)
    now = _TS * 1000
    s.on_tape(_tape(now, 104.0))
    s.on_core_position({"flat": True})
    op = s.decide(now)
    assert op and op["gate"] == "grind"
    atr = op["meta"]["entry_atr"]
    # core confirms the grind long held
    s.on_core_position({"flat": False, "side": "LONG", "entry": 104.0, "atr": atr})
    # run 8 ATR up (build the peak), then retrace to 2 ATR → the chandelier gives back and CLOSEs
    s.on_tape(_tape(now + 1000, 104.0 + 8 * atr)); s.decide(now + 1000)
    s.on_tape(_tape(now + 2000, 104.0 + 2 * atr))
    close = s.decide(now + 2000)
    assert close is not None and close["action"] == "CLOSE" and close["reason"] == "CHANDELIER"


def test_twogate_clears_active_gate_on_flat():
    s = Strategy(RunConfig(gates=live_gates()))
    _load(s)
    now = _TS * 1000
    s.on_tape(_tape(now, 104.0)); s.on_core_position({"flat": True})
    s.decide(now)
    assert s._active is not None
    s.on_core_position({"flat": True})   # flat confirmed → no gate owns a position
    assert s._active is None
