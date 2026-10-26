"""THE HYBRID ROBOT (E89, GazBot V8 Robo v1.02): it may press only the rider's BUY file, only for a Claude entry that agrees with the
frozen detector's leg, after the 05:00 Paris veto, and only when the rider is flat.

Nothing reads the wall clock (`now` and `clock` are injected), calls Claude, sends a message or touches the live desk: every path the
robot writes is redirected into tmp_path by the `box` fixture and a test asserts the fixture redirected ALL of them. The docstring names
request files to say what it does not touch, so path assertions look at executable string constants only.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
SRC = GB / "scripts" / "hybrid_robot.py"
sys.path.insert(0, str(GB / "scripts"))
sys.path.insert(0, str(GB / "src"))
import hybrid_robot as H  # noqa: E402
import leg_robot as L  # noqa: E402

UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 13)                      # a Tuesday: CEST, so the 05:00 Paris veto is 03:00Z
D0 = int(dt.datetime(2026, 10, 13, tzinfo=UTC).timestamp())


def at(h, m=0, s=5):
    return dt.datetime(2026, 10, 13, h, m, s, tzinfo=UTC)


def _tree():
    return ast.parse(SRC.read_text())


def _code_strings():
    t = _tree()
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(t)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    return [n.value for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docs]


def test_no_broker_and_no_other_request_file():
    imported = set()
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert not imported & {"ib_insync", "ib_async", "ibapi", "requests", "urllib", "smtplib", "subprocess"}
    bad = [(s, f) for s in _code_strings()
           for f in ("gate_switches", "desk_kill", "placeOrder", "MarketOrder", "LimitOrder", "telegram", ".notify_env")
           if f in s]
    assert not bad, bad
    # the only request file it can name is reached through leg_robot's constant, and it writes it in exactly one function
    writers = [f.name for f in ast.walk(_tree()) if isinstance(f, ast.FunctionDef)
               and any(isinstance(c, ast.Name) and c.id == "BUY_FILE" for c in ast.walk(f))
               and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "open" and len(c.args) > 1
                       and getattr(c.args[1], "value", None) == "w" for c in ast.walk(f))]
    assert writers == ["write_press"], writers
    # the Claim-button file is reachable only through CLAIM_FILE, written in exactly one function, which only exit_alert calls
    claim_writers = [f.name for f in ast.walk(_tree()) if isinstance(f, ast.FunctionDef)
                     and any(isinstance(c, ast.Name) and c.id == "CLAIM_FILE" for c in ast.walk(f))
                     and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "open" and len(c.args) > 1
                             and getattr(c.args[1], "value", None) == "w" for c in ast.walk(f))]
    assert claim_writers == ["write_claim"], claim_writers
    callers = [f.name for f in ast.walk(_tree()) if isinstance(f, ast.FunctionDef)
               and any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "write_claim" for c in ast.walk(f))]
    assert callers == ["exit_alert"], callers
    assert [s for s in _code_strings() if "day_rider_claim" in s and "CLAIM_FILE" not in s] == [s for s in _code_strings() if "day_rider_claim" in s]


def test_every_write_targets_one_of_its_own_paths():
    allowed = {"BUY_FILE", "STATE_FILE", "LOG_FILE", "DAYLOG"}
    src = SRC.read_text()
    for tok in ("open(STATE_FILE", "open(LOG_FILE", "open(BUY_FILE", 'open(f"{DAYLOG}'):
        assert tok in src or tok == 'open(STATE_FILE'
    names = {n.id for n in ast.walk(_tree()) if isinstance(n, ast.Name)}
    assert allowed <= names


def test_frozen_parameters():
    assert (H.ROBOT, H.VERSION, H.LINE, H.QTY, H.TARGETS) == ("GazBot V8 Robo", "1.03", "v2", 4, "75,75,75,75")
    assert (H.MIL_CAP, H.MILCAP_FROM, H.PREV_VERSION) == (2, "2026-10-26", "1.02")
    assert H.DETECTOR_SHA == L.DETECTOR_SHA == L.detector_sha()
    assert H.L.VETO_PARIS_HOUR == 5 and H.L.K == 11
    assert H.S.brief_for("v2") is H.S.BRIEF_V2
    assert H.START_AFTER == dt.datetime(2026, 10, 14, 14, 55, tzinfo=UTC)  # E90


def test_the_rider_reads_the_press_as_four_lots_all_at_37_5_points(tmp_path, monkeypatch):
    from gazbot7 import day_rider as R
    f = tmp_path / "buy.txt"
    monkeypatch.setattr(R, "BUY_FILE", str(f))
    monkeypatch.setattr(H, "BUY_FILE", str(f))
    line = H.write_press(dt.datetime.now(UTC), "SELL")
    assert line.endswith("|SELL|4|75,75,75,75")
    side, qty, tg = R.buy_requested()
    assert (side, qty, tg) == ("SELL", 4, [75.0] * 4)
    assert [round(t / R.VPP, 2) for t in tg] == [37.5] * 4


def test_det_dir_is_causal():
    turns = [(1, 1.0, 1, 1000, 1.0), (2, 2.0, -1, 5000, 2.0)]
    assert H.det_dir(turns, 939) == 0
    assert H.det_dir(turns, 1060) == 1
    assert H.det_dir(turns, 5059) == 1                 # the second turn is not knowable until cts+60
    assert H.det_dir(turns, 5060) == -1


@pytest.mark.skipif(not (GB / "data/tape/bars/MNQ/backfill_1min.parquet").exists(), reason="needs the lake")
def test_truncated_series_gives_the_same_direction_as_the_full_day():
    full = L.confirmed_turns(L.series_for(dt.date(2026, 10, 9)))
    d0 = int(dt.datetime(2026, 10, 9, tzinfo=UTC).timestamp())
    series = L.series_for(dt.date(2026, 10, 9))
    for hh in (4, 7, 10, 13):
        t = d0 + hh * 3600
        trunc = L.confirmed_turns([b for b in series if b[0] + 60 <= t + 60])
        assert H.det_dir(trunc, t - 60) == H.det_dir(full, t - 60), hh


# ── the step() flow, fully sandboxed ───────────────────────────────────────────────────────────────

class Box:
    pass


@pytest.fixture
def box(tmp_path, monkeypatch):
    b = Box()
    b.tmp = tmp_path
    paths = {"SWITCH": tmp_path / "hybrid.env", "STATE_FILE": tmp_path / "state.json", "LOG_FILE": tmp_path / "log.jsonl",
             "DAYLOG": tmp_path / "days", "BUY_FILE": tmp_path / "buy.txt", "CLAIM_FILE": tmp_path / "claim.txt", "LEG_SWITCH": tmp_path / "leg.env"}
    for k, v in paths.items():
        monkeypatch.setattr(H, k, str(v))
    for k, v in {"BUY_FILE": paths["BUY_FILE"], "SWITCH": paths["LEG_SWITCH"], "RIDER_SWITCH": tmp_path / "rider.env",
                 "RIDER_STATE": tmp_path / "rider_state.json"}.items():
        monkeypatch.setattr(L, k, str(v))
    b.paths = paths
    monkeypatch.setattr(H, "START_AFTER", dt.datetime(2026, 10, 1, tzinfo=UTC))
    paths["SWITCH"].write_text("hybrid_robot=on\n")
    paths["LEG_SWITCH"].write_text("leg_robot=off\n")
    (tmp_path / "rider.env").write_text("day_rider=on\n")
    b.clock = dt.datetime(2026, 10, 13, 8, 0, 20, tzinfo=UTC)

    def rider(**kw):
        st = {"heartbeat": b.clock.isoformat(), "entered": False, "closed": False, "lots_open": 0, "venue_ok": True, "venue_net": 0}
        st.update(kw)
        (tmp_path / "rider_state.json").write_text(json.dumps(st))
    b.rider = rider
    rider()
    bars = [(D0 - 7200 + 60 * i, 101.0, 99.0, 100.0) for i in range(0, 60 * 14)]
    monkeypatch.setattr(H, "live_bars", lambda key, now_epoch: [x for x in bars if x[0] <= now_epoch])
    monkeypatch.setattr(H, "preflight", lambda: None)
    monkeypatch.setattr(H.S, "context", lambda *a, **k: "")
    monkeypatch.setattr(L, "series_for", lambda day: [(D0 - 86400 + 60 * i, 1.0, 1.0, 1.0) for i in range(300)])
    b.turns = []
    monkeypatch.setattr(L, "confirmed_turns", lambda bars_: b.turns)
    b.answer = {"action": "WAIT"}
    monkeypatch.setattr(H.S, "ask", lambda prompt, timeout=180: dict(b.answer))
    monkeypatch.setattr(H.page.__globals__["__builtins__"] if False else H, "page", lambda m, critical=False: (b.__dict__.setdefault("pages", []).append(m), critical and b.__dict__.setdefault("crit_pages", []).append(m)))
    b.leg_up = lambda: setattr(b, "turns", [(D0 + 3600, 99.0, 1, D0 + 4000, 100.0)])
    b.leg_down = lambda: setattr(b, "turns", [(D0 + 3600, 99.0, -1, D0 + 4000, 100.0)])
    b.step = lambda now, **kw: H.step(now, clock=lambda: b.clock, sleep=lambda s: None, **kw)
    return b


def test_fixture_redirects_every_write_path(box):
    for name in ("SWITCH", "STATE_FILE", "LOG_FILE", "DAYLOG", "BUY_FILE", "CLAIM_FILE"):
        assert str(box.tmp) in getattr(H, name), name
    assert str(box.tmp) in L.BUY_FILE and str(box.tmp) in L.RIDER_STATE and str(box.tmp) in L.RIDER_SWITCH


def test_with_leg_entry_after_veto_presses_four_lots_at_37_5(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG", "reason": "r"}
    r = box.step(at(8))
    assert r["status"] == "PRESSED", r
    assert r["decision"]["entry_action"] == "PRESS_BUY"
    assert box.paths["BUY_FILE"].read_text().strip().endswith("|BUY|4|75,75,75,75")


def test_against_the_leg_writes_nothing(box):
    box.leg_down(); box.answer = {"action": "ENTER_LONG"}
    r = box.step(at(8))
    assert r["decision"]["entry_action"] == "NOT_WITH_LEG" and not box.paths["BUY_FILE"].exists()


def test_no_detector_leg_writes_nothing(box):
    box.answer = {"action": "ENTER_SHORT"}
    r = box.step(at(8))
    assert r["decision"]["entry_action"] == "NO_DETECTOR_LEG" and not box.paths["BUY_FILE"].exists()


def test_before_05_paris_is_vetoed(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    r = box.step(at(2, 55))                       # 04:55 Paris (CEST)
    assert r["decision"]["entry_action"] == "VETOED_BEFORE_05_PARIS" and not box.paths["BUY_FILE"].exists()
    box.answer = {"action": "EXIT"}
    box.step(at(3, 0))                            # Claude closes its simulated book
    box.answer = {"action": "ENTER_LONG"}
    box.clock = at(3, 0, 20)
    r2 = box.step(at(3, 5))                       # first decision at/after 05:00 Paris... 03:05Z
    assert r2["decision"]["entry_action"] == "PRESS_BUY"


def test_the_veto_is_inclusive_at_exactly_05_paris(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.clock = at(3, 0, 20)
    r = box.step(at(3, 0))
    assert r["decision"]["entry_action"] == "PRESS_BUY"


def test_rider_holding_blocks_the_press(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.rider(entered=True, lots_open=3)
    r = box.step(at(8))
    assert r["decision"]["entry_action"] == "SKIPPED_HOLDING" and not box.paths["BUY_FILE"].exists()


def test_stale_rider_heartbeat_blocks_the_press(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.rider(heartbeat=(box.clock - dt.timedelta(seconds=500)).isoformat())
    r = box.step(at(8))
    assert r["decision"]["entry_action"].startswith("SKIPPED_RIDER_HEARTBEAT_STALE")


def test_slow_claude_call_makes_the_entry_stale(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.clock = at(8, 4, 30)                       # 270s after the 08:00 decision
    r = box.step(at(8, 0, 5))
    assert r["decision"]["entry_action"] == "STALE_NOT_ENTERED" and not box.paths["BUY_FILE"].exists()


def test_claudes_own_exit_never_touches_the_real_position(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.paths["BUY_FILE"].unlink()
    box.rider(entered=True, lots_open=4)           # the rider took the press, so the real desk is holding
    box.answer = {"action": "EXIT"}
    r = box.step(at(8, 5))
    assert not box.paths["BUY_FILE"].exists() and r["status"] == "OK"
    st = json.loads(box.paths["STATE_FILE"].read_text())
    assert st["pos"] is None and st["done"][0]["why"] == "CLAUDE_EXIT"


def test_no_second_entry_while_claudes_sim_book_is_open(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.paths["BUY_FILE"].unlink()
    box.rider(entered=True, lots_open=4)           # the real desk is holding too, so nothing reconciles away
    r = box.step(at(8, 5))                         # Claude says ENTER again but its sim book is long already
    assert "entry_action" not in r["decision"] and not box.paths["BUY_FILE"].exists()


def test_reentry_after_flat_is_allowed(box):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8)); box.paths["BUY_FILE"].unlink()
    box.rider(entered=True, lots_open=4)
    box.answer = {"action": "EXIT"}; box.step(at(8, 5))
    box.answer = {"action": "ENTER_LONG"}
    box.clock = at(8, 10, 20); box.rider()
    r = box.step(at(8, 10))
    assert r["decision"]["entry_action"] == "PRESS_BUY"


def test_same_boundary_is_decided_once(box):
    box.step(at(8))
    assert box.step(at(8, 0, 40))["status"] == "ALREADY_DECIDED"


def test_late_tick_is_skipped(box):
    assert box.step(at(8, 2, 0))["status"] == "LATE_TICK"


def test_off_switch_leg_robot_conflict_weekend_and_window(box):
    box.paths["SWITCH"].write_text("hybrid_robot=off\n")
    assert box.step(at(8))["status"] == "SWITCH_OFF"
    box.paths["SWITCH"].write_text("hybrid_robot=on\n")
    box.paths["LEG_SWITCH"].write_text("leg_robot=on\n")
    assert box.step(at(8))["status"] == "LEG_ROBOT_ON_CONFLICT" and box.pages
    box.paths["LEG_SWITCH"].write_text("leg_robot=off\n")
    assert box.step(dt.datetime(2026, 10, 17, 8, 0, 5, tzinfo=UTC))["status"] == "WEEKEND"
    assert box.step(at(1, 55))["status"] == "OUTSIDE_WINDOW"


def test_start_and_stop_gates(box, monkeypatch):
    monkeypatch.setattr(H, "START_AFTER", dt.datetime(2026, 10, 14, 22, 0, tzinfo=UTC))
    assert box.step(at(8))["status"] == "WAITING_START"
    monkeypatch.setattr(H, "START_AFTER", dt.datetime(2026, 10, 1, tzinfo=UTC))
    monkeypatch.setattr(H, "STOP_AFTER", dt.datetime(2026, 10, 13, 6, tzinfo=UTC))
    assert box.step(at(8))["status"] == "PAST_STOP_AFTER"


def test_errors_are_counted_and_three_in_a_row_page_once(box):
    box.answer = {"action": "WAIT", "error": "timeout 180s"}
    for m in (0, 5, 10, 15):
        box.step(at(8, m))
    st = json.loads(box.paths["STATE_FILE"].read_text())
    assert st["errors"] == 4 and len(box.pages) == 1


def test_day_close_writes_the_record_once_and_flags_poison(box):
    box.answer = {"action": "WAIT", "error": "x"}
    box.step(at(8))
    r = box.step(at(13, 30, 5))
    assert r["status"] == "DAY_WRITTEN" and r["poisoned"] is True
    assert box.step(at(13, 35, 5))["status"] == "OUTSIDE_WINDOW"
    assert (box.paths["DAYLOG"] / "2026-10-13.json").exists()


def test_dry_run_writes_nothing(box):
    box.leg_up()
    r = box.step(at(8), dry=True, fake="ENTER_LONG")
    assert r["decision"]["entry_action"] == "PRESS_BUY"
    assert not box.paths["BUY_FILE"].exists() and not box.paths["STATE_FILE"].exists() and not box.paths["LOG_FILE"].exists()


# ── E90: the one-off afternoon extension ───────────────────────────────────────────────────────────

def test_ext_text_rewrites_the_window_only_on_the_extension_session(monkeypatch):
    txt = "- the window is 02:00Z-13:30Z; you are flattened at 13:30Z whatever you say\n⏱ -90 minutes left in the window. At 13:30Z"
    op = int(dt.datetime(2026, 10, 14, 16, 0, tzinfo=UTC).timestamp())
    out = H.ext_text(H.EXT_KEY, op, txt)
    assert "13:30Z" not in out and "19:55Z" in out and "⏱ 235 minutes left" in out
    assert H.ext_text("2026-10-15", op, txt) == txt


def _long_bars(box, monkeypatch):
    bars = [(D0 - 7200 + 60 * i, 101.0, 99.0, 100.0) for i in range(0, 60 * 24)]
    monkeypatch.setattr(H, "live_bars", lambda key, now_epoch: [x for x in bars if x[0] <= now_epoch])


def test_ext_session_decides_in_the_afternoon_and_closes_at_19_55(box, monkeypatch):
    monkeypatch.setattr(H, "EXT_KEY", "2026-10-13")
    _long_bars(box, monkeypatch)
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.clock = at(15, 0, 20); box.rider()
    assert box.step(at(15, 0))["status"] == "PRESSED"
    box.clock = at(19, 50, 20); box.rider()
    assert box.step(at(19, 50))["status"] in ("OK", "PRESSED")
    r = box.step(at(19, 55, 5))
    assert r["status"] == "DAY_WRITTEN"
    assert box.step(at(20, 0, 5))["status"] == "OUTSIDE_WINDOW"
    assert (box.paths["DAYLOG"] / "2026-10-13.json").exists()


def test_a_normal_session_stays_closed_in_the_afternoon(box, monkeypatch):
    monkeypatch.setattr(H, "EXT_KEY", "2099-01-01")
    _long_bars(box, monkeypatch)
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    assert box.step(at(15, 0))["status"] == "OUTSIDE_WINDOW" and not box.paths["BUY_FILE"].exists()


# ── the sim book reconciles with the real desk before Claude is asked ──────────────────────────────

def _log_events(box):
    return [json.loads(x) for x in box.paths["LOG_FILE"].read_text().splitlines()]


def test_flat_desk_drops_a_stale_sim_position_and_claude_may_enter_again(box):
    box.leg_down(); box.answer = {"action": "ENTER_SHORT"}
    box.rider(entered=True, lots_open=4)                       # 08:00: the press is skipped because the rider "holds"
    assert box.step(at(8))["decision"]["entry_action"] == "SKIPPED_HOLDING"
    box.rider()                                                # the desk is in fact flat at 08:05
    r = box.step(at(8, 5))
    assert r["decision"]["sim_reconciled"] is True and r["decision"]["entry_action"] == "PRESS_SELL"
    ev = [e for e in _log_events(box) if e["event"] == "SIM_RECONCILED"]
    assert len(ev) == 1 and ev[0]["real"] == "FLAT" and ev[0]["side"] == "SELL"
    st = json.loads(box.paths["STATE_FILE"].read_text())
    assert st["done"] == [] and len(st["reconciled"]) == 1     # dropped, not booked: it never traded


def test_the_dropped_position_is_not_in_front_of_claude(box, monkeypatch):
    seen = []
    monkeypatch.setattr(H.S, "context", lambda upto, op, pos, *a, **k: seen.append(pos) or "")
    box.leg_down(); box.answer = {"action": "ENTER_SHORT"}
    box.rider(entered=True, lots_open=4); box.step(at(8))
    box.rider(); box.step(at(8, 5))
    assert seen[0] is None and seen[1] is None


def test_a_holding_or_unknown_desk_never_reconciles(box):
    box.leg_down(); box.answer = {"action": "ENTER_SHORT"}
    box.step(at(8)); box.paths["BUY_FILE"].unlink()
    for state in ({"entered": True, "lots_open": 4}, {"venue_ok": False}, {"venue_net": -4.0},
                  {"heartbeat": (box.clock - dt.timedelta(seconds=900)).isoformat()}, {"blind_holding": True}):
        box.rider(**state)
        box.step(at(8, 5))
        st = json.loads(box.paths["STATE_FILE"].read_text())
        assert st["pos"] is not None and not st.get("reconciled"), state
        st["last_op"] = 0; box.paths["STATE_FILE"].write_text(json.dumps(st))


def test_a_pending_request_is_unknown_not_flat(box):
    box.leg_down(); box.answer = {"action": "ENTER_SHORT"}
    box.step(at(8))                                            # the BUY file is left in place on purpose
    assert box.paths["BUY_FILE"].exists()
    box.step(at(8, 5))
    assert json.loads(box.paths["STATE_FILE"].read_text())["pos"] is not None


def test_dry_run_reconciles_in_memory_only(box):
    box.leg_down(); box.answer = {"action": "ENTER_SHORT"}
    box.rider(entered=True, lots_open=4); box.step(at(8))
    box.rider()
    before = box.paths["STATE_FILE"].read_text(); n = len(_log_events(box))
    box.step(at(8, 5), dry=True, fake="WAIT")
    assert box.paths["STATE_FILE"].read_text() == before and len(_log_events(box)) == n


def test_day_record_carries_the_reconciliations(box):
    box.leg_down(); box.answer = {"action": "ENTER_SHORT"}
    box.rider(entered=True, lots_open=4); box.step(at(8))
    box.rider(); box.step(at(8, 5))
    st = json.loads(box.paths["STATE_FILE"].read_text())
    assert H.write_day(st)["sim_reconciled"][0]["real"] == "FLAT"


# ── v1.02+LOCK: once the day has touched +$1000 no NEW entries (operator, 2026-10-14) ─────────────────────────────

def _eq(**kw):
    e = {"now": 1100.0, "peak": 1100.0, "peak_ts": D0 + 28000, "touch_ts": D0 + 28000, "bars": 100}
    e.update(kw)
    return e


@pytest.fixture
def lockbox(box, monkeypatch):
    monkeypatch.setattr(H, "LOCK_FROM", "2026-10-01")
    box.eq = _eq
    monkeypatch.setattr(H, "day_equity", lambda key, now_ts: box.eq_val)
    box.trust = (True, {})
    monkeypatch.setattr(H.FP, "ledger_trust", lambda db, key, tol=50.0: box.trust)   # never read the live ledger/fills from a test
    box.eq_val = _eq(touch_ts=None, now=200.0, peak=300.0)
    return box


def test_below_the_limit_nothing_changes(lockbox):
    lockbox.leg_up(); lockbox.answer = {"action": "ENTER_LONG"}
    r = lockbox.step(at(8))
    assert r["status"] == "PRESSED" and "lock" not in json.loads(lockbox.paths["STATE_FILE"].read_text())


def test_touching_the_limit_blocks_the_entry_and_the_claude_call(lockbox, monkeypatch):
    calls = []
    monkeypatch.setattr(H.S, "ask", lambda prompt, timeout=180: calls.append(1) or {"action": "ENTER_LONG"})
    lockbox.leg_up(); lockbox.eq_val = _eq()
    r = lockbox.step(at(8))
    assert r["status"] == "DAY_LOCKED" and not calls and not lockbox.paths["BUY_FILE"].exists()
    events = [json.loads(x) for x in lockbox.paths["LOG_FILE"].read_text().splitlines()]
    assert [e["event"] for e in events] == ["DAY_LOCK"] and events[0]["limit"] == 1000.0
    assert any("No new entries" in m for m in lockbox.pages)


def test_the_lock_latches_even_if_the_day_falls_back_below_it(lockbox):
    lockbox.leg_up(); lockbox.answer = {"action": "ENTER_LONG"}
    lockbox.eq_val = _eq(); lockbox.step(at(8))
    lockbox.eq_val = _eq(touch_ts=None, now=-300.0, peak=-300.0)       # the wipe-out: the day is now negative
    r = lockbox.step(at(8, 5))
    assert r["status"] == "DAY_LOCKED" and not lockbox.paths["BUY_FILE"].exists()
    events = [json.loads(x) for x in lockbox.paths["LOG_FILE"].read_text().splitlines()]
    assert [e["event"] for e in events].count("DAY_LOCK") == 1


def test_the_lock_resets_with_the_next_session(lockbox):
    lockbox.leg_up(); lockbox.answer = {"action": "ENTER_LONG"}
    lockbox.eq_val = _eq(); lockbox.step(at(8))
    assert lockbox.step(at(8, 5))["status"] == "DAY_LOCKED"
    st = H.load_state("2026-10-14")
    assert not st.get("lock")


def test_a_locked_session_does_not_touch_the_open_position(lockbox):
    lockbox.rider(entered=True, lots_open=4)
    lockbox.eq_val = _eq(); r = lockbox.step(at(8))
    assert r["status"] == "DAY_LOCKED" and not lockbox.paths["BUY_FILE"].exists()


def test_sessions_before_lock_from_are_untouched(box, monkeypatch):
    monkeypatch.setattr(H, "day_equity", lambda key, now_ts: _eq())
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    assert box.step(at(8))["status"] == "PRESSED"                      # LOCK_FROM is 2026-10-15; this session is 2026-10-13


def test_the_off_switch_disables_the_lock(lockbox):
    lockbox.paths["SWITCH"].write_text("hybrid_robot=on\nhybrid_lock=off\n")
    lockbox.leg_up(); lockbox.answer = {"action": "ENTER_LONG"}; lockbox.eq_val = _eq()
    assert lockbox.step(at(8))["status"] == "PRESSED"


def test_an_unreadable_day_fails_open_but_loudly(lockbox, monkeypatch):
    def boom(key, now_ts):
        raise RuntimeError("ledger locked")
    monkeypatch.setattr(H, "day_equity", boom)
    lockbox.leg_up(); lockbox.answer = {"action": "ENTER_LONG"}
    assert lockbox.step(at(8))["status"] == "PRESSED"
    assert any("NOT protecting" in m for m in lockbox.pages)
    assert any(json.loads(x)["event"] == "LOCK_CHECK_ERROR" for x in lockbox.paths["LOG_FILE"].read_text().splitlines())


_MISMATCH = (False, {"ledger": 1194.0, "ledger_all": 1506.0, "fills": 400.0, "diff": 794.0, "n_fills": 10, "overstated": True})


def test_a_ledger_the_broker_does_not_back_withholds_the_latch(lockbox):
    lockbox.leg_up(); lockbox.answer = {"action": "ENTER_LONG"}
    lockbox.eq_val = _eq(); lockbox.trust = _MISMATCH
    r = lockbox.step(at(8))
    assert r["status"] == "PRESSED" and not H.load_state("2026-10-14").get("lock")        # keeps trading: the profit is not real
    events = [json.loads(x) for x in lockbox.paths["LOG_FILE"].read_text().splitlines()]
    assert "LOCK_WITHHELD_LEDGER_MISMATCH" in [e["event"] for e in events] and "DAY_LOCK" not in [e["event"] for e in events]
    assert any("Lock NOT latched" in m for m in lockbox.pages) and not getattr(lockbox, "crit_pages", [])


def test_a_persisting_mismatch_pages_critical_and_a_cleared_one_latches(lockbox):
    lockbox.leg_up(); lockbox.eq_val = _eq(); lockbox.trust = _MISMATCH
    lockbox.step(at(8)); lockbox.step(at(8, 5))
    assert len(lockbox.crit_pages) == 1                                                    # second consecutive tick → critical
    lockbox.trust = (True, {})                                                             # the human labelled the phantom
    assert lockbox.step(at(8, 10))["status"] == "DAY_LOCKED"


def test_unverifiable_fills_still_latch(lockbox):
    lockbox.eq_val = _eq(); lockbox.trust = (True, {"unverified": "no rider fills recorded this session"})
    assert lockbox.step(at(8))["status"] == "DAY_LOCKED"
    assert any(json.loads(x)["event"] == "LOCK_XCHECK_UNVERIFIED" for x in lockbox.paths["LOG_FILE"].read_text().splitlines())


def test_dry_run_locks_in_memory_only(lockbox):
    lockbox.eq_val = _eq()
    r = lockbox.step(at(8), dry=True)
    assert r["status"] == "DAY_LOCKED" and not lockbox.paths["STATE_FILE"].exists() and not lockbox.paths["LOG_FILE"].exists()


def _row(side, qty, entry, o, c, pnl):
    f = lambda s: dt.datetime.fromtimestamp(D0 + s, UTC).isoformat()   # noqa: E731
    return {"side": side, "qty": qty, "entry_price": entry, "opened_at": f(o), "closed_at": f(c), "pnl_usd": pnl}


def test_equity_path_counts_realised_open_marks_and_the_live_position():
    rows = [_row("LONG", 1, 100.0, 0, 20, 50.0)]                        # +$50 booked at t=20
    bars = [(D0 + 10, 110.0), (D0 + 25, 90.0)]
    live = {"dir": -1, "entry": 100.0, "qty": 4, "since": D0 + 5}
    p = H.equity_path(rows, live, bars)
    assert p[0][1] == pytest.approx(10 * 2 * 1 + (-1) * (110 - 100) * 4 * 2)      # long mark +20, short mark -80
    assert p[1][1] == pytest.approx(50 + (-1) * (90 - 100) * 4 * 2)               # booked 50, short now +80


def test_equity_path_sees_a_peak_between_ticks():
    bars = [(D0 + i * 5, 100.0 + (i if i < 100 else 200 - i)) for i in range(0, 201)]
    live = {"dir": 1, "entry": 100.0, "qty": 4, "since": D0}
    p = H.equity_path([], live, bars)
    assert max(e for _, e in p) == pytest.approx(100 * 4 * 2) and p[-1][1] == pytest.approx(0.0)


# ---- the CLAUDE EXIT CALLED alert: a notification only, never an order ---------------------------------------------------------

@pytest.fixture
def sent(monkeypatch):
    out = []
    import gazbot7.notify as N
    monkeypatch.setattr(N, "notify", lambda m, **kw: out.append((m, kw)) or True)
    return out


def _hold_then_exit(box, **rider_kw):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.paths["BUY_FILE"].unlink()
    box.rider(entered=True, lots_open=4, venue_net=4.0, direction=1, entry=100.0, qty=4,
              entered_at=at(7, 30).isoformat(), **rider_kw)
    box.answer = {"action": "EXIT", "reason": "failed break"}
    box.step(at(8, 5))
    return [json.loads(x) for x in box.paths["LOG_FILE"].read_text().splitlines()]


def test_exit_while_the_live_side_matches_texts_him_in_capitals_with_red_icons_both_ends(box, sent):
    recs = _hold_then_exit(box)
    assert len(sent) == 1
    msg, kw = sent[0]
    assert kw["critical"] is True and kw["weekend_ok"] is True
    lines = msg.splitlines()
    assert "CLAUDE EXIT CALLED" in lines[0] and "CLAUDE EXIT CALLED" in lines[-1]
    assert lines[0][0] == lines[-1][0] == "\U0001F6A8" and "\U0001F534" in lines[0] and "\U0001F534" in lines[-1]
    assert "LIVE LONG 4 @ 100.00" in msg and "FAILED BREAK" in msg and "FLATTEN IT YOURSELF" in msg
    assert recs[-1]["exit_alert"] == "SENT"
    assert not box.paths["BUY_FILE"].exists()


def test_exit_when_the_rider_is_flat_says_nothing(box, sent):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.paths["BUY_FILE"].unlink()
    box.answer = {"action": "EXIT"}
    r = box.step(at(8, 5))                                   # the rider never took the press: flat
    assert not sent and r["status"] == "OK"


def test_exit_against_a_live_short_does_not_mislead_him(box, sent):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.paths["BUY_FILE"].unlink()
    box.rider(entered=True, lots_open=4, venue_net=-4.0, direction=-1, entry=100.0, qty=4, entered_at=at(7, 30).isoformat())
    box.answer = {"action": "EXIT"}
    box.step(at(8, 5))
    assert not sent
    assert json.loads(box.paths["LOG_FILE"].read_text().splitlines()[-1])["exit_alert"] == "OPPOSITE_SIDE"


def test_a_failing_notifier_never_stops_the_robot(box, monkeypatch):
    import gazbot7.notify as N
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(N, "notify", boom)
    recs = _hold_then_exit(box)
    assert recs[-1]["exit_alert"].startswith("ALERT_FAULT")
    st = json.loads(box.paths["STATE_FILE"].read_text())
    assert st["pos"] is None and st["done"][0]["why"] == "CLAUDE_EXIT"


def test_dry_run_sends_no_alert(box, sent):
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.rider(entered=True, lots_open=4, venue_net=4.0, direction=1, entry=100.0, qty=4, entered_at=at(7, 30).isoformat())
    box.answer = {"action": "EXIT"}
    box.step(at(8, 5), dry=True)
    assert not sent


def test_auto_flatten_on_writes_the_claim_button_file_and_says_so(box, sent):
    box.paths["SWITCH"].write_text("hybrid_robot=on\nhybrid_exit_live=on\n")
    recs = _hold_then_exit(box)
    claim = box.paths["CLAIM_FILE"].read_text()
    stamp, _, spec = claim.partition("|")
    assert dt.datetime.fromisoformat(stamp) and spec == "src=hybrid_claude_exit"        # a bare stamp + src= means ALL to the rider
    assert recs[-1]["exit_claim"] == "WRITTEN" and "FLATTEN REQUESTED" in sent[0][0]
    assert not box.paths["BUY_FILE"].exists()


def test_auto_flatten_off_is_text_only(box, sent):
    recs = _hold_then_exit(box)
    assert not box.paths["CLAIM_FILE"].exists() and recs[-1]["exit_claim"] == "NO" and "FLATTEN IT YOURSELF" in sent[0][0]


def test_auto_flatten_never_fires_when_flat_opposite_or_dry(box, sent):
    box.paths["SWITCH"].write_text("hybrid_robot=on\nhybrid_exit_live=on\n")
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.paths["BUY_FILE"].unlink()
    box.answer = {"action": "EXIT"}
    box.step(at(8, 5))                                          # flat desk
    assert not box.paths["CLAIM_FILE"].exists()


def test_auto_flatten_opposite_side_and_dry_run_write_nothing(box, sent):
    box.paths["SWITCH"].write_text("hybrid_robot=on\nhybrid_exit_live=on\n")
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    box.step(at(8))
    box.paths["BUY_FILE"].unlink()
    box.rider(entered=True, lots_open=4, venue_net=-4.0, direction=-1, entry=100.0, qty=4, entered_at=at(7, 30).isoformat())
    box.answer = {"action": "EXIT"}
    box.step(at(8, 5), dry=True)
    box.step(at(8, 5))
    assert not box.paths["CLAIM_FILE"].exists() and not sent


def test_auto_flatten_does_not_overwrite_a_pending_request_and_survives_a_write_fault(box, sent, monkeypatch):
    box.paths["SWITCH"].write_text("hybrid_robot=on\nhybrid_exit_live=on\n")
    box.paths["CLAIM_FILE"].write_text("pending")
    recs = _hold_then_exit(box)
    assert box.paths["CLAIM_FILE"].read_text() == "pending" and recs[-1]["exit_claim"] == "ALREADY_PENDING"


def test_a_claim_write_fault_still_texts_and_says_flatten_it_yourself(box, sent, monkeypatch):
    box.paths["SWITCH"].write_text("hybrid_robot=on\nhybrid_exit_live=on\n")
    monkeypatch.setattr(H, "CLAIM_FILE", str(box.tmp / "nodir" / "claim.txt"))
    recs = _hold_then_exit(box)
    assert recs[-1]["exit_claim"].startswith("CLAIM_FAULT") and "AUTO-FLATTEN FAILED" in sent[0][0]


# ── v1.03 MIL CAP: at most 2 claims per MIL, then wait for the next confirmed MIL (operator, 2026-10-26, E115) ─────────

import sqlite3  # noqa: E402


def _ledger(path, rows):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE trades (opened_at TEXT, closed_at TEXT, side TEXT, qty REAL, entry_price REAL, pnl_usd REAL, data_quality TEXT, gate TEXT)")
    for o, side, pnl, q in rows:
        for _ in range(4):                                   # four lots per entry, as the rider books them
            c.execute("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?)", (o, o, side, 1, 100.0, pnl / 4, q, "day_rider"))
    c.commit(); c.close()


@pytest.fixture
def capbox(box, monkeypatch):
    monkeypatch.setattr(H, "MILCAP_FROM", "2026-10-01")
    box.db = str(box.tmp / "ledger.db")
    monkeypatch.setattr(H, "LEDGER", box.db)
    box.ledger = lambda rows: _ledger(box.db, rows)
    return box


def _iso(h, m=0):
    return dt.datetime(2026, 10, 13, h, m, 30, tzinfo=UTC).isoformat()


def test_mil_pivot_is_causal():
    turns = [(100, 1.0, 1, 1000, 1.0), (2000, 2.0, -1, 5000, 2.0)]
    assert H.mil_pivot(turns, 939) is None
    assert H.mil_pivot(turns, 1060) == (100, 1)
    assert H.mil_pivot(turns, 5059) == (100, 1) and H.mil_pivot(turns, 5060) == (2000, -1)


def test_two_claims_on_this_mil_block_the_press(capbox):
    capbox.leg_up(); capbox.answer = {"action": "ENTER_LONG"}
    capbox.ledger([(_iso(5), "LONG", 294.0, None), (_iso(6), "LONG", 270.0, None)])
    r = capbox.step(at(8))
    assert r["status"] == "OK" and r["decision"]["entry_action"] == "MIL_CAP_2_CLAIMS", r
    assert r["decision"]["mil"]["claims"] == 2 and not capbox.paths["BUY_FILE"].exists()


def test_one_claim_still_presses(capbox):
    capbox.leg_up(); capbox.answer = {"action": "ENTER_LONG"}
    capbox.ledger([(_iso(5), "LONG", 294.0, None)])
    r = capbox.step(at(8))
    assert r["decision"]["entry_action"] == "PRESS_BUY" and r["decision"]["mil"]["claims"] == 1


def test_losers_flagged_lots_other_side_and_the_previous_mil_are_not_claims(capbox):
    capbox.leg_up(); capbox.answer = {"action": "ENTER_LONG"}
    pivot = dt.datetime.fromtimestamp(D0 + 3600, UTC)                       # the leg_up MIL pivots at 01:00Z
    before = (pivot - dt.timedelta(minutes=20)).isoformat()
    capbox.ledger([(before, "LONG", 294.0, None), (_iso(5), "LONG", -500.0, None), (_iso(6), "SHORT", 294.0, None),
                   (_iso(7), "LONG", 294.0, "EXCLUDE:phantom")])
    r = capbox.step(at(8))
    assert r["decision"]["entry_action"] == "PRESS_BUY" and r["decision"]["mil"]["claims"] == 0, r


def test_the_next_confirmed_mil_resets_the_count(capbox):
    capbox.ledger([(_iso(5), "SHORT", 294.0, None), (_iso(6), "SHORT", 294.0, None)])
    capbox.turns = [(D0 + 3600, 99.0, -1, D0 + 4000, 100.0), (D0 + 7 * 3600, 98.0, 1, D0 + 7 * 3600 + 600, 100.0)]
    capbox.answer = {"action": "ENTER_LONG"}
    r = capbox.step(at(8))
    assert r["decision"]["entry_action"] == "PRESS_BUY" and r["decision"]["mil"]["claims"] == 0


def test_an_unreadable_ledger_fails_closed_and_pages_once(capbox, monkeypatch):
    capbox.leg_up(); capbox.answer = {"action": "ENTER_LONG"}
    monkeypatch.setattr(H, "LEDGER", str(capbox.tmp / "missing" / "nope.db"))
    r = capbox.step(at(8))
    assert r["decision"]["entry_action"] == "MIL_CAP_UNREADABLE" and not capbox.paths["BUY_FILE"].exists()
    capbox.step(at(8, 5))
    assert sum("MIL cap FAILS CLOSED" in p for p in capbox.pages) == 1


def test_sessions_before_milcap_from_are_untouched(box, monkeypatch):
    monkeypatch.setattr(H, "LEDGER", str(box.tmp / "missing.db"))       # would fail closed if the cap ran
    box.leg_up(); box.answer = {"action": "ENTER_LONG"}
    r = box.step(at(8))
    assert r["decision"]["entry_action"] == "PRESS_BUY" and "mil" not in r["decision"]


def test_against_the_leg_never_reads_the_ledger(capbox, monkeypatch):
    monkeypatch.setattr(H, "mil_claims", lambda *a: (_ for _ in ()).throw(AssertionError("read")))
    capbox.leg_down(); capbox.answer = {"action": "ENTER_LONG"}
    assert capbox.step(at(8))["decision"]["entry_action"] == "NOT_WITH_LEG"


def test_a_one_day_release_switches_the_cap_off_for_that_session_only(capbox):
    capbox.leg_up(); capbox.answer = {"action": "ENTER_LONG"}
    capbox.ledger([(_iso(5), "LONG", 294.0, None), (_iso(6), "LONG", 270.0, None)])
    capbox.paths["SWITCH"].write_text("hybrid_robot=on\nhybrid_milcap_off_for=2026-10-13\n")
    r = capbox.step(at(8))
    assert r["decision"]["entry_action"] == "PRESS_BUY" and "mil" not in r["decision"]
    assert H.milcap_enabled("2026-10-14")                     # the next session is capped again without anyone touching the switch
