"""strategy — the decision half, now on 1-MINUTE bars (aggregated from the 5s
stream): gate → OPEN intent, managed exits → CLOSE intent, the freshness
stand-down, and the one-in-flight-intent guard. Pure logic; no sockets."""

from __future__ import annotations

from datetime import UTC, datetime

from gazbot7.config import RunConfig
from gazbot7.strategy import Strategy

# a fixed in-session clock (Wed 2026-07-15 16:00 UTC = 12:00 ET) so the session
# gate is deterministic and the built bars are "fresh" relative to it.
_TS = int(datetime(2026, 7, 15, 16, 0, tzinfo=UTC).timestamp())


def _bar(ts, o, h, l, c, v):
    return {"symbol": "MNQ", "tf": "5s", "ts": ts, "o": o, "h": h, "l": l, "c": round(c, 4), "v": v, "closed": True}


def _thrust_up(end_ts=_TS):
    """11 minutes of 5s bars → 10 completed 1m bars: 5 flat @100 then 5 rising
    +0.8/min (a clean 1-minute thrust) with a volume surge on the last thrust
    minute, plus a trailing minute so that minute completes."""
    closes = [100.0] * 5 + [100.8, 101.6, 102.4, 103.2, 104.0] + [104.0]
    vols = [12] * 5 + [12, 14, 16, 18, 60] + [20]
    msgs, prev = [], 100.0
    start = end_ts - len(closes) * 60  # minute-aligned (end_ts is on a minute)
    for i, cl in enumerate(closes):
        mstart = start + i * 60           # each minute's 12 bars stay inside one clock minute
        for j in range(12):
            c = prev + (cl - prev) * (j + 1) / 12
            msgs.append(_bar(mstart + j * 5, c, c + 0.15, c - 0.15, c, vols[i] / 12))
        prev = cl
    return msgs, end_ts


def _strat(**kw):
    # base mechanics tests use immediate entry + the fixed 2R target; the delayed
    # entry and the chandelier get their own dedicated tests below.
    kw.setdefault("entry_confirm_s", 0.0)
    kw.setdefault("chandelier_enabled", False)
    cfg = RunConfig(gate="thrust", gate_params={"thr": 1.5, "amp_floor": 0.0004}, **kw)
    return Strategy(cfg)


def _load(s, end_ts=_TS):
    for m in _thrust_up(end_ts)[0]:
        s.on_bar(m)
    return end_ts


def _tape(now_ms, last, **kw):
    return {"ts_ms": now_ms - 100, "net_flow": kw.get("net_flow", 0.0),
            "win_price_delta": kw.get("wpd", 0.0), "last": last, "in_rth": True}


def test_fires_open_when_flat_and_gate_triggers():
    s = _strat()
    _load(s)
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 104.0))
    intent = s.decide(now)
    assert intent is not None
    assert intent["action"] == "OPEN" and intent["side"] == "LONG" and intent["gate"] == "thrust"
    assert intent["meta"]["entry_atr"] > 0


def test_stands_down_when_tape_stale():
    s = _strat()
    _load(s)
    now = _TS * 1000 + 100
    s.on_tape({"ts_ms": now - 20_000, "net_flow": 0, "win_price_delta": 0, "last": 104.0, "in_rth": True})
    assert s.decide(now) is None  # tape 20s stale → stand down


def test_stands_down_when_bars_stale():
    s = _strat()
    _load(s)
    now = _TS * 1000 + 100_000  # 100s since the last 5s bar
    s.on_tape(_tape(now, 104.0))
    assert s.decide(now) is None


def test_one_in_flight_intent_guard():
    s = _strat()
    _load(s)
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 104.0))
    assert s.decide(now)["action"] == "OPEN"
    s.on_tape(_tape(now + 1000, 104.1))
    assert s.decide(now + 1000) is None  # pending OPEN, still flat → no duplicate


def test_pending_clears_on_core_held_then_manages_target():
    s = _strat(target_r=2.0)
    _load(s)
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 104.0))
    assert s.decide(now)["action"] == "OPEN"
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 2.0})
    s.on_tape(_tape(now + 2000, 110.0))  # well past 2R target
    intent = s.decide(now + 2000)
    assert intent["action"] == "CLOSE" and intent["reason"] == "TARGET"


def test_managed_adverse_cut_when_held():
    s = _strat(adverse_cut_atr=1.5)
    _load(s)
    now = _TS * 1000 + 100
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 2.0})
    s.on_tape(_tape(now, 96.0))  # 4 pts offside ≥ 1.5·ATR(2), never green
    intent = s.decide(now)
    assert intent["action"] == "CLOSE" and intent["reason"] == "ADVERSE_CUT"


def test_pending_timeout_frees_action():
    s = _strat()
    _load(s)
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 104.0))
    assert s.decide(now)["action"] == "OPEN"
    later = now + 9_000
    s.on_tape(_tape(later, 104.1))
    assert s.decide(later) is not None  # timed out → free to act again


def test_rejected_intent_result_clears_pending():
    s = _strat()
    _load(s)
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 104.0))
    op = s.decide(now)
    s.on_intent_result({"iid": op["iid"], "accepted": False, "reason": "already in position"})
    s.on_tape(_tape(now + 500, 104.1))
    assert s.decide(now + 500) is not None


def test_no_open_window_suppresses_entry():
    et = datetime(2026, 7, 15, 16, 50, tzinfo=__import__("zoneinfo").ZoneInfo("America/New_York"))
    end = int(et.timestamp())
    s = _strat()
    _load(s, end_ts=end)
    now = end * 1000 + 100
    s.on_tape(_tape(now, 104.0))
    assert s.decide(now) is None  # thrust would fire, but the no-open window blocks it


def test_entry_fires_midday_outside_window():
    s = _strat()
    _load(s)  # _TS is 12:00 ET, well before the close
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 104.0))
    assert s.decide(now)["action"] == "OPEN"


# ── delayed-entry absorption confirm (operator 2026-07-16) ────────────────────
def test_entry_confirm_delays_then_opens():
    s = _strat(entry_confirm_s=5.0)
    _load(s)
    t0 = _TS * 1000 + 100
    s.on_tape(_tape(t0, 104.0))
    assert s.decide(t0) is None          # signal raised — watching, no immediate OPEN
    assert s._confirm is not None
    t1 = t0 + 6000                        # 6s on: still fresh, thrust persists, clean tape
    s.on_tape(_tape(t1, 104.0))
    intent = s.decide(t1)
    assert intent is not None and intent["action"] == "OPEN" and intent["side"] == "LONG"


def test_entry_confirm_vetoes_on_absorption():
    s = _strat(entry_confirm_s=5.0)
    _load(s)
    t0 = _TS * 1000 + 100
    s.on_tape(_tape(t0, 104.0))
    assert s.decide(t0) is None
    t1 = t0 + 2000                        # heavy BUY flow that failed to lift price = absorb a LONG
    s.on_tape(_tape(t1, 104.0, net_flow=80.0, wpd=-1.0))
    assert s.decide(t1) is None
    assert s._confirm is None             # confirmation abandoned — vetoed


def test_entry_confirm_immediate_when_zero():
    s = _strat(entry_confirm_s=0.0)
    _load(s)
    t0 = _TS * 1000 + 100
    s.on_tape(_tape(t0, 104.0))
    assert s.decide(t0)["action"] == "OPEN"   # 0 = the pre-2026-07-16 immediate entry


# ── chandelier profit exit ────────────────────────────────────────────────────
def test_chandelier_closes_a_runner():
    s = _strat(chandelier_enabled=True)
    _load(s)
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 4.0})
    t0 = _TS * 1000 + 100
    s.on_tape(_tape(t0, 130.0))           # runs to +30 (7.5R) — peak set, no exit at the peak
    assert s.decide(t0) is None
    t1 = t0 + 1000
    s.on_tape(_tape(t1, 121.0))           # gives back to +21 (>0.5-ATR trail from peak) → bank
    intent = s.decide(t1)
    assert intent is not None and intent["reason"] == "CHANDELIER"


# ── absorption = catastrophe backstop, not a scalp-cutter (2026-07-16) ─────────
def test_absorption_holds_a_green_trade():
    s = _strat()  # absorption_min_loss_usd default 60
    _load(s)
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 30.0})
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 110.0, net_flow=80.0, wpd=-1.0))  # green + absorption tape
    assert s.decide(now) is None  # no loss → absorption stands down (won't cut a winner)


def test_absorption_holds_a_small_loss():
    s = _strat()
    _load(s)
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 30.0})
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 95.0, net_flow=80.0, wpd=-1.0))  # −$10, absorption tape
    assert s.decide(now) is None  # $10 < $60 tolerance → let it breathe


def test_absorption_cuts_a_deep_loss():
    s = _strat()
    _load(s)
    s.on_core_position({"flat": False, "side": "LONG", "entry": 100.0, "atr": 30.0})
    now = _TS * 1000 + 100
    s.on_tape(_tape(now, 65.0, net_flow=80.0, wpd=-1.0))  # −$70 runaway, absorption tape
    intent = s.decide(now)
    assert intent["action"] == "CLOSE" and intent["reason"] == "ABSORPTION_CUT"
