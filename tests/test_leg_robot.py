"""THE LEG ROBOT (E15): it must press only the rider's BUY file, only when the frozen detector says so.

Nothing here reads the wall clock (`now` is injected), sends a message, or touches the live desk: every
path the robot writes is redirected into tmp_path by the `box` fixture, and a test asserts the fixture
really did redirect all of them (a sandbox that covers the writes but not the channel is not a sandbox).
The robot imports no notifier at all. ⚠ The docstring names request files to say what it does not touch,
so path assertions look at executable string constants only.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import pathlib
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
SRC = GB / "scripts" / "leg_robot.py"
LAKE = GB / "data/tape/bars/MNQ/backfill_1min.parquet"
sys.path.insert(0, str(GB / "scripts"))
sys.path.insert(0, str(GB / "src"))
import leg_robot as L  # noqa: E402
import mil_labels as ML  # noqa: E402

UTC = dt.timezone.utc


def _tree():
    return ast.parse(SRC.read_text())


def _code_strings():
    t = _tree()
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(t)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    return [n.value for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docs]


def test_no_broker_no_notifier_no_other_request_file():
    imported = set()
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert not imported & {"ib_insync", "ib_async", "ibapi", "requests", "urllib", "smtplib", "subprocess", "gazbot7"}
    bad = [(s, f) for s in _code_strings()
           for f in ("day_rider_claim", "gate_switches", "desk_kill", "placeOrder", "MarketOrder",
                     "LimitOrder", "telegram", "notify", ".notify_env", "capture.db")
           if f in s]
    assert not bad, bad
    assert any("day_rider_buy.txt" in s for s in _code_strings())


def test_frozen_parameters():
    assert L.ROBOT == "GazBot V8 Robo" and L.VERSION == "1.00"
    assert L.K == 11 and L.WARM_DAYS == 4 and L.ENTRY_END_MIN == 19 * 60 + 40 and L.QTY == 4
    assert L.ARM == "H" and L.ARMS["H"] == "25,50,75,100" and L.ARMS["F"] == "100,100,100,100"
    assert L.detector_sha() == L.DETECTOR_SHA
    assert L.START_AFTER == dt.datetime(2026, 10, 11, 22, 0, tzinfo=UTC)
    assert L.STOP_AFTER == dt.datetime(2026, 10, 30, 21, 0, tzinfo=UTC)
    assert L.STOP_AFTER < dt.datetime(2026, 11, 1, 0, 0, tzinfo=UTC)   # before US DST ends


def test_veto_cutoff_is_05_paris_on_the_session_date():
    ts = lambda s: int(dt.datetime.fromisoformat(s).timestamp())
    assert L.VETO_PARIS_HOUR == 5
    assert L.veto_cutoff(ts("2026-10-11T22:00:00+00:00")) == ts("2026-10-12T03:00:00+00:00")   # CEST
    assert L.veto_cutoff(ts("2026-10-12T10:00:00+00:00")) == ts("2026-10-12T03:00:00+00:00")
    assert L.veto_cutoff(ts("2026-10-12T21:59:00+00:00")) == ts("2026-10-12T03:00:00+00:00")
    assert L.veto_cutoff(ts("2026-10-12T22:00:00+00:00")) == ts("2026-10-13T03:00:00+00:00")
    assert L.veto_cutoff(ts("2026-10-26T01:00:00+00:00")) == ts("2026-10-26T04:00:00+00:00")   # CET
    assert L.veto_cutoff(ts("2026-10-25T22:00:00+00:00")) == ts("2026-10-26T04:00:00+00:00")
    assert L.veto_cutoff(ts("2026-10-24T22:00:00+00:00")) == ts("2026-10-25T04:00:00+00:00")   # DST ends 01:00Z that day, so 05:00 Paris is already CET
    assert L.veto_cutoff(ts("2026-10-25T10:00:00+00:00")) == ts("2026-10-25T04:00:00+00:00")


def test_veto_cutoff_matches_the_sims_definition():
    from zoneinfo import ZoneInfo
    for d in ("2026-03-10", "2026-07-23", "2026-10-12", "2026-10-26", "2026-11-03"):
        sim = int(dt.datetime.fromisoformat(d).replace(hour=5, tzinfo=ZoneInfo("Europe/Paris")).timestamp())
        mid = int(dt.datetime.fromisoformat(d).replace(hour=12, tzinfo=UTC).timestamp())
        assert L.veto_cutoff(mid) == sim


def test_veto_switch_off(monkeypatch):
    monkeypatch.setattr(L, "VETO_PARIS_HOUR", None)
    assert L.veto_cutoff(1_790_000_000) is None


def test_session_day():
    f = lambda s: L.session_day(dt.datetime.fromisoformat(s))
    assert f("2026-10-11T22:00:00+00:00") == dt.date(2026, 10, 12)
    assert f("2026-10-12T21:59:00+00:00") == dt.date(2026, 10, 12)
    assert f("2026-10-12T22:00:00+00:00") == dt.date(2026, 10, 13)


@pytest.fixture
def box(tmp_path, monkeypatch):
    for name in ("SWITCH", "RIDER_SWITCH", "RIDER_STATE", "BUY_FILE", "STATE_FILE", "LOG_FILE"):
        monkeypatch.setattr(L, name, str(tmp_path / name.lower()))
    assert not any(str(GB / "data") in getattr(L, n) for n in
                   ("SWITCH", "RIDER_SWITCH", "RIDER_STATE", "BUY_FILE", "STATE_FILE", "LOG_FILE"))
    (tmp_path / "switch").write_text("leg_robot=on\n")
    (tmp_path / "rider_switch").write_text("day_rider=on\n")
    monkeypatch.setattr(L, "START_AFTER", dt.datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(L, "STOP_AFTER", dt.datetime(2027, 1, 1, tzinfo=UTC))
    return tmp_path


def rider(box, now, **kw):
    s = {"heartbeat": now.isoformat(), "entered": False, "lots_open": 0, "venue_ok": True, "venue_net": 0.0,
         "blind_holding": False}
    s.update(kw)
    (box / "rider_state").write_text(json.dumps(s))


needs_lake = pytest.mark.skipif(not LAKE.exists(), reason="lake parquet not on this box")


@pytest.fixture
def lake(monkeypatch):
    import e14_lake
    monkeypatch.setattr(ML, "minute_bars", e14_lake.lake_minute_bars)


def a_signal(day="2026-07-23"):
    d = dt.date.fromisoformat(day)
    bars = L.series_for(d)
    for t in L.confirmed_turns(bars):
        h = dt.datetime.fromtimestamp(t[3], UTC)
        if h.date() == d and 5 <= h.hour <= 17:
            return t
    raise AssertionError("no mid-day turn")


@needs_lake
def test_causal_truncation_equals_batch(lake):
    d = dt.date(2026, 7, 23)
    bars = L.series_for(d)
    full = L.confirmed_turns(bars)
    for k in range(len(bars) - 7000, len(bars), 450):
        cut = L.confirmed_turns(bars[:k])
        horizon = bars[k - 1][0]
        assert cut == [t for t in full if t[3] <= horizon], k


@needs_lake
def test_signals_equal_the_sims_signals(lake):
    e6 = pytest.importorskip("e6_detector_t3a")
    for day in ("2026-07-23", "2026-07-29"):
        d = dt.date.fromisoformat(day)
        assert L.series_for(d) == e6.series_for(day)
        assert L.confirmed_turns(L.series_for(d)) == e6.confirmed_turns(e6.series_for(day))


def test_buy_file_is_what_the_rider_parses(box, monkeypatch):
    import gazbot7.day_rider as R
    monkeypatch.setattr(R, "BUY_FILE", L.BUY_FILE)
    now = dt.datetime.now(UTC)           # the rider's own age check reads the wall clock
    L.write_press(now, "SELL")
    assert R.buy_requested() == ("SELL", 4, [25.0, 50.0, 75.0, 100.0])


@needs_lake
def test_fresh_flat_signal_presses_once(box, lake):
    t = a_signal()
    now = dt.datetime.fromtimestamp(t[3] + 60 + 20, UTC)
    rider(box, now)
    (box / "state_file").write_text(json.dumps({"last_confirm_ts": t[3] - 1}))
    r = L.step(now, sleep=lambda s: None)
    assert r["status"] == "PRESSED"
    line = (box / "buy_file").read_text().strip().split("|")
    assert line[1] == ("BUY" if t[2] > 0 else "SELL") and line[2] == "4" and line[3] == "25,50,75,100"
    (box / "buy_file").unlink()
    r2 = L.step(now + dt.timedelta(seconds=60), sleep=lambda s: None)
    assert r2["status"] == "OK" and not (box / "buy_file").exists()
    sig = [json.loads(x) for x in (box / "log_file").read_text().splitlines() if '"SIGNAL"' in x]
    assert len(sig) == 1 and sig[0]["action"].startswith("PRESS_")


@needs_lake
@pytest.mark.parametrize("kw,expect", [
    ({"entered": True, "lots_open": 4}, "SKIPPED_HOLDING"),
    ({"venue_net": 4.0}, "SKIPPED_VENUE_NOT_FLAT_4.0"),
    ({"venue_ok": False}, "SKIPPED_VENUE_NOT_OK"),
    ({"blind_holding": True}, "SKIPPED_RIDER_BLIND"),
])
def test_rider_not_flat_means_no_press(box, lake, kw, expect):
    t = a_signal()
    now = dt.datetime.fromtimestamp(t[3] + 80, UTC)
    rider(box, now, **kw)
    (box / "state_file").write_text(json.dumps({"last_confirm_ts": t[3] - 1}))
    assert L.step(now, sleep=lambda s: None)["status"] == "OK"
    assert not (box / "buy_file").exists()
    assert json.loads((box / "log_file").read_text().splitlines()[0])["action"] == expect


@needs_lake
def test_stale_heartbeat_pending_request_and_rider_off(box, lake):
    t = a_signal()
    now = dt.datetime.fromtimestamp(t[3] + 80, UTC)
    for setup, expect in (
        (lambda: rider(box, now - dt.timedelta(seconds=600)), "SKIPPED_RIDER_HEARTBEAT_STALE_600s"),
        (lambda: (rider(box, now), (box / "buy_file").write_text("operator press")), "SKIPPED_REQUEST_ALREADY_PENDING"),
        (lambda: (rider(box, now), (box / "rider_switch").write_text("day_rider=off\n")), "SKIPPED_RIDER_OFF"),
    ):
        for f in ("buy_file", "log_file"):
            if (box / f).exists():
                (box / f).unlink()
        (box / "rider_switch").write_text("day_rider=on\n")
        setup()
        (box / "state_file").write_text(json.dumps({"last_confirm_ts": t[3] - 1}))
        L.step(now, sleep=lambda s: None)
        assert json.loads((box / "log_file").read_text().splitlines()[0])["action"] == expect
        if expect.endswith("PENDING"):
            assert (box / "buy_file").read_text() == "operator press"      # never overwritten


@needs_lake
def test_stale_signal_not_entered_and_outside_window(box, lake, monkeypatch):
    t = a_signal()
    late = dt.datetime.fromtimestamp(t[3] + 60 + L.FRESH_S + 30, UTC)
    rider(box, late)
    (box / "state_file").write_text(json.dumps({"last_confirm_ts": t[3] - 1}))
    L.step(late, sleep=lambda s: None)
    assert json.loads((box / "log_file").read_text().splitlines()[0])["action"] == "STALE_NOT_ENTERED"
    assert not (box / "buy_file").exists()
    (box / "log_file").unlink()
    monkeypatch.setattr(L, "ENTRY_END_MIN", 0)
    now = dt.datetime.fromtimestamp(t[3] + 80, UTC)
    rider(box, now)
    (box / "state_file").write_text(json.dumps({"last_confirm_ts": t[3] - 1}))
    L.step(now, sleep=lambda s: None)
    assert json.loads((box / "log_file").read_text().splitlines()[0])["action"] == "OUT_OF_ENTRY_WINDOW"


@needs_lake
def test_first_run_initialises_without_acting(box, lake):
    t = a_signal()
    now = dt.datetime.fromtimestamp(t[3] + 80, UTC)
    rider(box, now)
    assert L.step(now, sleep=lambda s: None)["status"] == "INIT"
    assert not (box / "buy_file").exists()
    assert json.loads((box / "state_file").read_text())["last_confirm_ts"] >= t[3]


@needs_lake
def test_gates_switch_window_detector_feed(box, lake, monkeypatch):
    t = a_signal()
    now = dt.datetime.fromtimestamp(t[3] + 80, UTC)
    rider(box, now)
    (box / "switch").write_text("leg_robot=off\n")
    assert L.step(now)["status"] == "SWITCH_OFF"
    (box / "switch").write_text("")
    assert L.step(now)["status"] == "SWITCH_OFF"
    (box / "switch").write_text("leg_robot=on\n")
    monkeypatch.setattr(L, "START_AFTER", now + dt.timedelta(seconds=1))
    assert L.step(now)["status"] == "WAITING_START"
    monkeypatch.setattr(L, "START_AFTER", dt.datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(L, "STOP_AFTER", now)
    assert L.step(now)["status"] == "PAST_STOP_AFTER"
    monkeypatch.setattr(L, "STOP_AFTER", dt.datetime(2027, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(L, "DETECTOR_SHA", "0" * 16)
    assert L.step(now)["status"] == "DETECTOR_CHANGED"
    monkeypatch.setattr(L, "DETECTOR_SHA", L.detector_sha())
    import e14_lake
    cutoff = int(now.timestamp()) - 600
    monkeypatch.setattr(ML, "minute_bars", lambda day: [b for b in e14_lake.lake_minute_bars(day) if b[0] <= cutoff])
    assert L.step(now)["status"] == "FEED_STALE"
    assert not (box / "buy_file").exists()


@needs_lake
def test_dry_run_writes_nothing(box, lake):
    t = a_signal()
    now = dt.datetime.fromtimestamp(t[3] + 80, UTC)
    rider(box, now)
    (box / "state_file").write_text(json.dumps({"last_confirm_ts": t[3] - 1}))
    before = (box / "state_file").read_text()
    r = L.step(now, dry=True)
    assert r["signals"][0]["action"].startswith("PRESS_")
    assert not (box / "buy_file").exists() and not (box / "log_file").exists()
    assert (box / "state_file").read_text() == before


def _early_turn(day):
    """A confirmed turn on `day` whose decision time is before / after the 05:00 Paris cutoff."""
    d = dt.date.fromisoformat(day)
    early = late = None
    for t in L.confirmed_turns(L.series_for(d)):
        ct = t[3] + 60
        if dt.datetime.fromtimestamp(ct, UTC).date() != d and L.session_day(dt.datetime.fromtimestamp(ct, UTC)) != d:
            continue
        if ct < L.veto_cutoff(ct):
            early = early or t
        elif ct <= int(dt.datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp()) + L.ENTRY_END_MIN * 60:
            late = late or t
    return early, late


@needs_lake
def test_early_signal_is_vetoed_and_late_signal_presses(box, lake):
    early = late = None
    for day in ("2026-07-23", "2026-07-22", "2026-07-21", "2026-07-20", "2026-07-17", "2026-07-16"):
        early, late = _early_turn(day)
        if early and late:
            break
    assert early and late, "no day with both an early and a later turn"
    now = dt.datetime.fromtimestamp(early[3] + 80, UTC)
    rider(box, now)
    (box / "state_file").write_text(json.dumps({"last_confirm_ts": early[3] - 1}))
    L.step(now, sleep=lambda s: None)
    recs = [json.loads(x) for x in (box / "log_file").read_text().splitlines()]
    sig = [r for r in recs if r.get("event") == "SIGNAL" and r["confirm_ts"].startswith(L.iso(early[3])[:16])]
    assert sig and sig[0]["action"] == "VETOED_BEFORE_05_PARIS" and sig[0]["would_be"] in ("BUY", "SELL")
    assert not (box / "buy_file").exists()
    assert json.loads((box / "state_file").read_text())["last_confirm_ts"] >= early[3]
    (box / "log_file").unlink()
    now = dt.datetime.fromtimestamp(late[3] + 80, UTC)
    rider(box, now)
    (box / "state_file").write_text(json.dumps({"last_confirm_ts": late[3] - 1}))
    L.step(now, sleep=lambda s: None)
    recs = [json.loads(x) for x in (box / "log_file").read_text().splitlines()]
    assert any(r.get("action", "").startswith("PRESS_") for r in recs)


def test_every_log_record_carries_the_robot_version(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LOG_FILE", str(tmp_path / "l.jsonl"))
    L.log({"event": "x"})
    rec = json.loads(open(L.LOG_FILE).read())
    assert rec["robot"] == "GazBot V8 Robo" and rec["version"] == "1.00" and rec["event"] == "x"
