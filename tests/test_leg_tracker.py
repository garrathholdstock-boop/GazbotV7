"""The leg tracker strip: read-only, and it must say what the ROBOT will do, not what a tidier robot would.

Synthetic bars throughout and every path monkeypatched into tmp_path: no wall clock, no live state, no lake.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import random
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
SRC = GB / "scripts" / "leg_tracker.py"
sys.path.insert(0, str(GB / "scripts"))
sys.path.insert(0, str(GB / "src"))
import leg_robot as R  # noqa: E402
import leg_tracker as T  # noqa: E402
import hybrid_robot as H  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 12, 14, 0, 30, tzinfo=UTC)   # 16:00 Paris, past the 05:00 veto


def _strings():
    t = ast.parse(SRC.read_text())
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(t)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    return [n.value for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docs]


def test_read_only_no_order_path_no_switch_no_request_file():
    imported = set()
    for n in ast.walk(ast.parse(SRC.read_text())):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert not imported & {"ib_insync", "ib_async", "ibapi", "requests", "urllib", "smtplib", "subprocess", "gazbot7"}
    bad = [(s, f) for s in _strings()
           for f in ("day_rider_buy", "day_rider_claim", "gate_switches", "desk_kill", "leg_robot.env",
                     "placeOrder", "telegram", "notify", ".notify_env")
           if f in s]
    assert not bad, bad
    writes = [s for s in _strings() if "leg_tracker" in s]
    assert writes, "tracker must name its own output files"


def _bars(seed=7, n=900, start=1791400000):
    rng = random.Random(seed)
    px, out = 31000.0, []
    drift = 0.0
    for i in range(n):
        if i % 150 == 0:
            drift = rng.choice([-1.2, 1.2])
        o = px
        px += drift + rng.gauss(0, 2.0)
        hi, lo = max(o, px) + abs(rng.gauss(0, 1)), min(o, px) - abs(rng.gauss(0, 1))
        out.append((start + i * 60, hi, lo, px))
    return out


@pytest.mark.parametrize("seed", [1, 2, 3, 7, 11])
def test_replay_pivots_equal_the_robots_detector(seed):
    b = _bars(seed)
    a = R.DF.atr14(b)
    piv, s = T.replay(b, a)
    assert piv == R.DF.zigzag(b, a, lambda leg, x: R.K * x)
    assert s["dirn"] in (1, -1)


@pytest.fixture
def snap(monkeypatch, tmp_path):
    n = 3000
    b = _bars(7, n=n, start=int(NOW.timestamp() // 60 * 60) - n * 60)
    monkeypatch.setattr(R, "series_for", lambda day: b)
    for name in ("SWITCH", "RIDER_SWITCH", "RIDER_STATE", "BUY_FILE"):
        monkeypatch.setattr(R, name, str(tmp_path / name.lower()))
    (tmp_path / "switch").write_text("leg_robot=on\n")
    (tmp_path / "rider_switch").write_text("day_rider=on\n")
    monkeypatch.setattr(R, "START_AFTER", dt.datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(R, "STOP_AFTER", dt.datetime(2027, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(H, "SWITCH", str(tmp_path / "hswitch"))
    monkeypatch.setattr(H, "LOG_FILE", str(tmp_path / "hlog.jsonl"))
    monkeypatch.setattr(H, "START_AFTER", dt.datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(H, "STOP_AFTER", dt.datetime(2027, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(H, "EXT_KEY", "2026-10-12")      # NOW is 14:00Z, after the normal 13:30Z window
    monkeypatch.setattr(H, "LEG_SWITCH", str(tmp_path / "legsw"))      # absent file = leg robot off
    (tmp_path / "hswitch").write_text("hybrid_robot=on\n")

    def run(now=NOW, **rider):
        s = {"heartbeat": now.isoformat(), "entered": False, "closed": False, "lots_open": 0, "venue_ok": True,
             "venue_net": 0.0, "blind_holding": False}
        s.update(rider)
        (tmp_path / "rider_state").write_text(json.dumps(s))
        return T.snapshot(now)
    run.tmp = tmp_path
    return run


def test_flat_rider_is_armed(snap):
    o = snap()
    assert o["status"] == "OK" and o["gate"] == "ARMED_WAITING"
    assert 0 <= o["retrace_pct"] and o["trigger_px"] != o["extreme_px"]


def test_open_position_is_in_trade(snap):
    assert snap(entered=True, closed=False, lots_open=4)["gate"] == "IN_TRADE"


def test_closed_flat_ladder_is_armed_again(snap):
    """v1.01 (E34): a completed trade no longer latches the robot out for the rest of the session."""
    o = snap(entered=True, closed=True, lots_open=0)
    assert R.rider_gate(NOW) is None
    assert o["gate"] == "ARMED_WAITING"


def test_manual_claim_stale_lots_open_does_not_read_as_holding(snap):
    """2026-10-14: a MANUAL_CLAIM left lots_open=4 with closed=True and the venue flat; the gate read HOLDING, the
    hybrid skipped a real ENTER_SHORT (SKIPPED_HOLDING) and the strip said IN TRADE. Closed => the venue decides."""
    o = snap(entered=True, closed=True, lots_open=4, venue_net=0)
    assert R.rider_gate(NOW) is None
    assert o["gate"] == "ARMED_WAITING"


def test_closed_with_lots_open_is_still_refused_if_the_venue_is_not_flat(snap):
    snap(entered=True, closed=True, lots_open=4, venue_net=-4)
    assert R.rider_gate(NOW) == "VENUE_NOT_FLAT_-4"


def test_open_book_is_still_holding(snap):
    o = snap(entered=True, closed=False, lots_open=4, venue_net=-4)
    assert R.rider_gate(NOW) == "HOLDING" and o["gate"] == "IN_TRADE"


def test_switch_off_and_other_rider_refusals(snap):
    (snap.tmp / "hswitch").write_text("hybrid_robot=off\n")
    assert snap()["gate"] == "SWITCH_OFF"
    (snap.tmp / "hswitch").write_text("hybrid_robot=on\n")
    assert snap(venue_ok=False)["gate"] == "RIDER_VENUE_NOT_OK"


def test_veto_active_before_05_paris(snap):
    early = dt.datetime(2026, 10, 12, 1, 0, 30, tzinfo=UTC)   # 03:00 Paris
    assert snap(now=early)["gate"] == "VETO_ACTIVE"


def test_reports_the_hybrid_and_the_side_it_may_press(snap):
    o = snap()
    import hybrid_robot as HR
    assert o["robot"] == "GazBot V8 Robo" and o["version"] == HR.VERSION and o["mode"] == "hybrid"
    assert o["allowed_side"] == ("BUY" if o["dir"] > 0 else "SELL") and o["window_end_hhmm_utc"] == "19:55"


def test_afternoon_of_a_normal_session_is_closed(snap, monkeypatch):
    monkeypatch.setattr(H, "EXT_KEY", "2099-01-01")
    assert snap()["gate"] == "ENTRY_WINDOW_CLOSED"


def test_last_call_is_read_from_the_hybrid_log(snap):
    (snap.tmp / "hlog.jsonl").write_text(json.dumps({"event": "DECISION", "decision_ts": "x", "action": "WAIT",
                                                      "entry_action": None, "reason": "r"}) + "\n")
    assert snap()["last_call"]["action"] == "WAIT"


def _ts(d, h, m, s=0):
    return int(dt.datetime(2026, 10, d, h, m, s, tzinfo=UTC).timestamp())


def test_next_look_is_the_next_five_minute_mark_plus_20s(snap):
    assert T.next_look(NOW) == (_ts(12, 14, 5, 20), "RUN")
    assert T.next_look(dt.datetime(2026, 10, 12, 14, 5, 20, tzinfo=UTC)) == (_ts(12, 14, 5, 20), "RUN")
    assert T.next_look(dt.datetime(2026, 10, 12, 14, 5, 21, tzinfo=UTC)) == (_ts(12, 14, 10, 20), "RUN")


def test_next_look_skips_the_closed_window_and_the_weekend(snap, monkeypatch):
    monkeypatch.setattr(H, "EXT_KEY", "2099-01-01")
    assert T.next_look(NOW) == (_ts(13, 2, 0, 20), "RUN")            # Tue 04:00 Paris, the next session's first look
    fri = dt.datetime(2026, 10, 16, 14, 0, 30, tzinfo=UTC)
    assert T.next_look(fri) == (_ts(19, 2, 0, 20), "RUN")            # Monday


def test_next_look_honours_the_extension_day_window(snap):
    assert T.next_look(dt.datetime(2026, 10, 12, 19, 45, 30, tzinfo=UTC)) == (_ts(12, 19, 50, 20), "RUN")   # last decision 19:50Z
    assert T.next_look(dt.datetime(2026, 10, 12, 19, 50, 30, tzinfo=UTC)) == (_ts(13, 2, 0, 20), "RUN")


def test_next_look_none_when_the_switch_is_off_or_leg_robot_is_on(snap):
    (snap.tmp / "hswitch").write_text("hybrid_robot=off\n")
    assert T.next_look(NOW) == (None, "OFF")
    (snap.tmp / "hswitch").write_text("hybrid_robot=on\n")
    (snap.tmp / "legsw").write_text("leg_robot=on\n")
    assert T.next_look(NOW) == (None, "OFF")


def test_next_look_none_after_the_run_ends(snap, monkeypatch):
    monkeypatch.setattr(H, "STOP_AFTER", dt.datetime(2026, 10, 12, 14, 1, tzinfo=UTC))
    assert T.next_look(NOW) == (None, "DONE")


def test_clock_is_exported_even_with_no_bars(snap, monkeypatch):
    monkeypatch.setattr(R, "series_for", lambda day: [])
    o = snap()
    assert o["status"] == "NO_BARS" and o["next_look_ts"] == _ts(12, 14, 5, 20) and o["look_state"] == "RUN"


def _log(tmp, *recs):
    (tmp / "hlog.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))


def _dec(ts, action, entry_action=None, **kw):
    return {"event": "DECISION", "decision_ts": ts, "at": ts, "action": action, "entry_action": entry_action, "reason": "r", **kw}


def test_last_entry_call_pressed_is_taken(snap):
    _log(snap.tmp, _dec("t1", "ENTER_SHORT", "PRESS_SELL"), _dec("t2", "WAIT"), _dec("t3", "HOLD"))
    c = snap()["last_entry_call"]
    assert c["decision_ts"] == "t1" and c["side"] == "SELL" and c["taken"] is True


def test_last_entry_call_skipped_is_ignored_with_its_reason(snap):
    _log(snap.tmp, _dec("t1", "ENTER_SHORT", "PRESS_SELL"), _dec("t2", "ENTER_LONG", "NOT_WITH_LEG"), _dec("t3", "WAIT"))
    c = snap()["last_entry_call"]
    assert c["decision_ts"] == "t2" and c["side"] == "BUY" and c["taken"] is False and c["entry_action"] == "NOT_WITH_LEG"


def test_last_entry_call_ignores_dry_runs_and_non_entries(snap):
    _log(snap.tmp, _dec("t1", "ENTER_LONG", "SKIPPED_HOLDING"), _dec("t2", "ENTER_SHORT", "PRESS_SELL", dry=True), _dec("t3", "EXIT"))
    assert snap()["last_entry_call"]["decision_ts"] == "t1"


def test_last_entry_call_none_without_a_log(snap):
    assert snap()["last_entry_call"] is None
