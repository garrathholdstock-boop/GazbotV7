"""THE NO-PRESS SHADOWS (E104, v1.02-LOCKSHADOW / v1.02-PM-shadow): they log what the robot is NOT allowed to take, and press nothing.

Nothing here reads the wall clock (`now` and `clock` are injected), calls Claude, sends a message or touches the live desk: every path the
shadow writes or reads is redirected into tmp_path by the `box` fixture, Claude and the rider gate are fakes, and the capture DB is a synthetic
tape. The shadow's docstring names forbidden files to say what it never touches, so path assertions look at executable string constants only.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import pathlib
import sqlite3
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
SRC = GB / "scripts" / "hybrid_shadow.py"
sys.path.insert(0, str(GB / "scripts"))
sys.path.insert(0, str(GB / "src"))
import hybrid_shadow as HS  # noqa: E402

UTC = dt.timezone.utc
KEY = "2026-10-13"                                        # a Tuesday, CEST: the 05:00 Paris veto is 03:00Z
D0 = int(dt.datetime(2026, 10, 13, tzinfo=UTC).timestamp())
T0 = D0 + 870 * 60                                        # 14:30Z, the first PM decision after 13:30Z + one hour
BASE = 29000.0


def at(h, m=0, s=20):
    return dt.datetime(2026, 10, 13, tzinfo=UTC) + dt.timedelta(hours=h, minutes=m, seconds=s)


def price(t):
    """Flat until T0, then +1pt per 6s up to +40: a long from T0 reaches +37.5 at ~T0+225s, a short never does."""
    return BASE + min(40.0, max(0.0, (t - T0) / 6.0))


_TREE = ast.parse(SRC.read_text())


def _tree():
    return _TREE


def _code_strings():
    t = _tree()
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    return [n.value for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docs]


def _enclosing():
    out = {}
    for f in ast.walk(_tree()):
        if isinstance(f, ast.FunctionDef):
            for n in ast.walk(f):
                out.setdefault(id(n), []).append(f.name)
    return out


class Box:
    pass


@pytest.fixture
def box(tmp_path, monkeypatch):
    b = Box()
    b.dir = tmp_path
    for name, fn in (("SWITCH", "hybrid_shadow.env"), ("STATE_FILE", "hybrid_shadow_state.json"), ("LOG_FILE", "hybrid_shadow.jsonl"),
                     ("OUT_DIR", "out"), ("CAPTURE", "capture.db")):
        monkeypatch.setattr(HS, name, str(tmp_path / fn))
    (tmp_path / "hybrid_shadow.env").write_text("hybrid_shadow=on\nshadow_lock=on\nshadow_pm=on\n")
    con = sqlite3.connect(str(tmp_path / "capture.db"))
    con.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, bar_ts INTEGER, open REAL, high REAL, low REAL, close REAL)")
    con.executemany("INSERT INTO bars VALUES ('MNQ','5s',?,?,?,?,?)",
                    [(t, price(t), price(t + 5), price(t), price(t + 5)) for t in range(D0 - 7200, D0 + 1300 * 60, 5)])
    con.commit()
    con.close()
    b.det = [1]
    b.gate = [None]
    b.action = ["WAIT"]
    b.asked = []
    b.live = {"lock": None, "pos": None, "done": []}
    b.lock_on = [True]
    H, L, S = HS.H, HS.L, HS.S
    monkeypatch.setattr(H, "preflight", lambda: None)
    monkeypatch.setattr(H, "lock_enabled", lambda: b.lock_on[0])
    monkeypatch.setattr(H, "load_state", lambda key: b.live)
    monkeypatch.setattr(H, "det_dir", lambda turns, t: b.det[0])
    monkeypatch.setattr(H, "live_bars", lambda key, now: [(m, price(m + 5), price(m), price(m + 60)) for m in range(D0 - 7200, D0 + 1300 * 60, 60) if m <= now])
    monkeypatch.setattr(L, "rider_gate", lambda now: b.gate[0])
    monkeypatch.setattr(L, "series_for", lambda day: [(D0 + i * 60, 1.0, 1.0, 1.0) for i in range(-300, 1300)])
    monkeypatch.setattr(L, "confirmed_turns", lambda series: [])
    monkeypatch.setattr(S, "context", lambda *a, **k: "CTX")

    def fake_ask(prompt):
        b.asked.append(prompt)
        return {"action": b.action[0], "reason": "fake", "confidence": 0.5}
    monkeypatch.setattr(S, "ask", fake_ask)
    b.step = lambda now, **kw: HS.step(now, clock=kw.pop("clock", lambda: now + dt.timedelta(seconds=5)), **kw)
    b.log = lambda: [json.loads(x) for x in open(HS.LOG_FILE)] if os.path.exists(HS.LOG_FILE) else []
    return b


def lock_state(decision_h, decision_m, pos=None):
    return {"at": "x", "limit": 1000, "touched_at": at(decision_h, decision_m - 3).isoformat(), "equity_now": 1100.0, "peak": 1100.0,
            "decision_ts": at(decision_h, decision_m, 0).isoformat()}


# ── authority: it can read the desk and write nothing but its own files ─────────────────────────────────────────────────
def test_it_has_no_broker_no_order_path_no_request_file_and_no_telegram():
    imported = set()
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert not imported & {"ib_insync", "ib_async", "ibapi", "requests", "urllib", "smtplib", "socket", "shutil", "subprocess", "sqlite3"}, imported
    bad = [(s, f) for s in _code_strings()
           for f in ("day_rider_buy", "day_rider_claim", "gate_switches", "desk_kill", "placeOrder", "MarketOrder", "LimitOrder", ".notify_env",
                     "hybrid_robot.env", "leg_robot.env", "telegram") if f in s]
    assert not bad, bad
    names = {n.attr for n in ast.walk(_tree()) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(_tree()) if isinstance(n, ast.Name)}
    forbidden = {"BUY_FILE", "CLAIM_FILE", "write_press", "write_claim", "exit_alert", "page", "notify", "write_day", "placeOrder", "save_state_live"}
    assert not names & forbidden, names & forbidden
    # of the live robot's helpers it may use only the pure ones; its own save/log/state files are never referenced
    used_h = {n.attr for n in ast.walk(_tree()) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "H"}
    assert used_h <= {"preflight", "lock_enabled", "load_state", "det_dir", "live_bars", "session_key", "QTY", "PRESS_MAX_AGE_S", "FEED_STALE_S",
                      "POISON_RATE", "RECONCILE_SIM", "LOG_FILE", "LINE", "_enc", "_dec"}, used_h


def test_every_write_is_one_of_its_three_own_files_and_nothing_else():
    enc = _enclosing()
    allowed = {"log": "LOG_FILE", "save_state": "STATE_FILE", "atomic_write": "OUT_DIR"}
    seen = set()
    for n in ast.walk(_tree()):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        recv = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
        open_w = name == "open" and len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and any(c in str(n.args[1].value) for c in "wax+")
        other = name in {"unlink", "rmtree", "write_text", "write_bytes", "touch", "utime", "chmod", "chown"} or (name in {"remove", "rename", "replace", "makedirs"} and recv in {"os", "shutil"})
        if open_w or other:
            fn = enc[id(n)][-1]
            assert fn in allowed, f"write ({name}) in {fn} at line {n.lineno}"
            assert allowed[fn] in {x.id for x in ast.walk(next(f2 for f2 in ast.walk(_tree()) if isinstance(f2, ast.FunctionDef) and f2.name == fn)) if isinstance(x, ast.Name)}
            seen.add(fn)
    assert seen == set(allowed), seen


def test_atomic_write_refuses_anything_outside_its_directory(box):
    HS.atomic_write("a.json", "{}")
    assert (box.dir / "out" / "a.json").read_text() == "{}"
    for bad in ("../x.json", "sub/x.json", "/etc/x"):
        with pytest.raises(ValueError):
            HS.atomic_write(bad, "no")


def test_frozen_parameters():
    assert HS.ARMS == {"LOCK": "v1.02-LOCKSHADOW", "PM": "v1.02-PM-shadow"}
    assert (HS.AM_START_MIN, HS.AM_END_MIN, HS.PM_START_MIN, HS.PM_END_MIN, HS.HARD_FLAT_MIN) == (120, 810, 810, 1195, 1240)
    assert HS.TARGET_PT == 37.5 and HS.FREE_S == 30 and HS.STEP_S == 300
    assert (HS.N.LOTS, HS.N.FEE_LOT, HS.N.USD_PT) == (4, 1.5, 2.0)
    assert HS.H.QTY == 4 and HS.H.LINE == "v2" and HS.H.DETECTOR_SHA == HS.L.detector_sha()
    assert HS.S.brief_for("v2") is HS.S.BRIEF_V2
    assert HS.MIN_N_FIT == 30 and HS.MIN_N_PROMISING == 10


# ── the switch, the windows and the boundary ────────────────────────────────────────────────────────────────────────────
def test_switch_off_weekend_and_window_edges_do_nothing(box):
    (box.dir / "hybrid_shadow.env").write_text("hybrid_shadow=off\n")
    assert box.step(at(14, 30))["status"] == "SWITCH_OFF"
    (box.dir / "hybrid_shadow.env").write_text("hybrid_shadow=on\nshadow_lock=on\nshadow_pm=on\n")
    assert box.step(dt.datetime(2026, 10, 17, 14, 30, 20, tzinfo=UTC))["status"] == "WEEKEND"
    assert box.step(at(1, 55))["status"] == "OUTSIDE_WINDOW"
    assert box.step(at(19, 55, 20))["status"] == "OUTSIDE_WINDOW"
    assert box.step(at(21, 0))["status"] == "OUTSIDE_WINDOW"
    assert box.asked == [] and not os.path.exists(HS.LOG_FILE)


def test_each_arm_switch_gates_only_its_own_arm(box):
    (box.dir / "hybrid_shadow.env").write_text("hybrid_shadow=on\nshadow_lock=on\nshadow_pm=off\n")
    assert box.step(at(14, 30))["status"] == "ARM_OFF"
    box.live["lock"] = lock_state(10, 0)
    assert box.step(at(10, 30))["status"] != "ARM_OFF"
    (box.dir / "hybrid_shadow.env").write_text("hybrid_shadow=on\nshadow_lock=off\nshadow_pm=on\n")
    assert box.step(at(10, 35))["status"] == "ARM_OFF"
    assert box.step(at(14, 30))["arm"] == "v1.02-PM-shadow"


def test_a_late_tick_and_a_second_tick_for_the_same_boundary_decide_nothing(box):
    assert box.step(at(14, 30, 200))["status"] == "LATE_TICK"
    assert box.asked == []
    assert box.step(at(14, 30))["status"] == "OK"
    assert box.step(at(14, 31, 5) - dt.timedelta(seconds=40))["status"] == "ALREADY_DECIDED"
    assert len(box.asked) == 1


def test_a_dead_feed_is_declined_not_decided(box, monkeypatch):
    monkeypatch.setattr(HS.H, "live_bars", lambda key, now: [(D0 + 14 * 3600 - 60 * i, 1.0, 1.0, 1.0) for i in range(300, 0, -1)])
    r = box.step(at(14, 30))
    assert r["status"] == "FEED_STALE" and box.asked == []


def test_a_failed_preflight_is_logged_once_and_nothing_is_decided(box, monkeypatch):
    monkeypatch.setattr(HS.H, "preflight", lambda: "the frozen detector changed (sha mismatch)")
    assert box.step(at(14, 30))["status"] == "PREFLIGHT_FAILED"
    assert box.step(at(14, 35))["status"] == "PREFLIGHT_FAILED"
    assert [r["event"] for r in box.log()] == ["PREFLIGHT_FAILED"] and box.asked == []


# ── the entry chain: the live one, with the press replaced by a log line ───────────────────────────────────────────────
def test_a_pm_entry_that_passes_every_filter_is_logged_never_pressed(box):
    box.action[0] = "ENTER_LONG"
    r = box.step(at(14, 30))
    d = r["decision"]
    assert r["status"] == "WOULD_PRESS" and d["entry_action"] == "WOULD_PRESS_BUY" and d["entry_dir"] == 1 and d["entry_px"] == BASE
    assert d["arm_label"] == "v1.02-PM-shadow" and d["decision_ts"] == at(14, 30, 0).isoformat()
    ev = [x["event"] for x in box.log()]
    assert ev == ["ARM_START", "DECISION"], ev
    assert sorted(p.name for p in box.dir.iterdir()) == ["capture.db", "hybrid_shadow.env", "hybrid_shadow.jsonl", "hybrid_shadow_state.json"]
    st = json.load(open(HS.STATE_FILE), object_hook=HS.H._dec)
    assert st["arms"]["PM"]["open_wb"]["entry"] == BASE and st["arms"]["PM"]["decisions"] == 1


def test_the_page_for_the_pm_arm_says_the_window_ends_1955z(box):
    txt = HS.pm_text(T0, "x ⏱ 5 minutes left in the window until 13:30Z")
    assert "⏱ 325 minutes left in the window" in txt and "19:55Z" in txt and "13:30Z" not in txt
    box.step(at(14, 30))
    assert "19:55Z" in box.asked[0]


@pytest.mark.parametrize("det,expect", [(-1, "NOT_WITH_LEG"), (0, "NO_DETECTOR_LEG")])
def test_an_entry_against_or_without_the_detector_leg_is_not_entered(box, det, expect):
    box.det[0] = det
    box.action[0] = "ENTER_LONG"
    r = box.step(at(14, 30))
    assert r["decision"]["entry_action"] == expect and r["status"] == "OK"
    assert "entry_dir" not in r["decision"]


def test_the_05_paris_veto_applies_before_03z_in_cest(box):
    box.live["lock"] = lock_state(2, 30)
    box.action[0] = "ENTER_LONG"
    r = box.step(at(2, 40))
    assert r["arm"] == "v1.02-LOCKSHADOW" and r["decision"]["entry_action"] == "VETOED_BEFORE_05_PARIS"
    r = box.step(at(3, 5))
    assert r["decision"]["entry_action"] == "WOULD_PRESS_BUY"


def test_a_stale_decision_is_not_entered(box):
    box.action[0] = "ENTER_LONG"
    r = box.step(at(14, 30), clock=lambda: at(14, 30, 0) + dt.timedelta(seconds=HS.PRESS_MAX_AGE_S + 1))
    assert r["decision"]["entry_action"] == "STALE_NOT_ENTERED"


@pytest.mark.parametrize("gate", ["HOLDING", "VENUE_NOT_FLAT_2", "LATCHED_AFTER_TRADE"])
def test_the_real_rider_gate_blocks_exactly_as_it_would_block_the_live_robot(box, gate):
    box.gate[0] = gate
    box.action[0] = "ENTER_LONG"
    d = box.step(at(14, 30))["decision"]
    assert d["entry_action"] == "SKIPPED_" + gate and "entry_px" not in d


def test_the_shadows_own_would_be_position_blocks_until_its_target_prints_plus_30s(box):
    box.det[0] = -1
    box.action[0] = "ENTER_SHORT"
    assert box.step(at(14, 30))["decision"]["entry_action"] == "WOULD_PRESS_SELL"        # a short on a rising tape: never reaches +37.5
    box.action[0] = "WAIT"
    box.step(at(14, 35))                                                                 # claude holds his sim book; reconcile cannot drop it (own is open)
    box.action[0] = "ENTER_SHORT"
    r = box.step(at(14, 40))
    assert r["decision"]["sim_holding"] is True


def test_a_long_that_hits_frees_the_slot_30s_after_the_print_and_re_entry_is_allowed(box):
    box.action[0] = "ENTER_LONG"
    assert box.step(at(14, 30))["decision"]["entry_action"] == "WOULD_PRESS_BUY"
    box.action[0] = "ENTER_LONG"
    r = box.step(at(14, 35))                                                             # the +37.5 printed at ~T0+225s; +30s < 300s, so the slot is free
    assert r["decision"]["shadow_open"] is False
    assert r["decision"]["sim_reconciled"] is True                                       # the real desk is flat, his sim long is dropped (RECONCILE_SIM)
    assert r["decision"]["entry_action"] == "WOULD_PRESS_BUY"


def test_a_would_be_entry_while_the_shadow_is_open_is_skipped_with_that_reason(box, monkeypatch):
    box.action[0] = "ENTER_SHORT"
    box.det[0] = -1
    box.step(at(14, 30))
    st = json.load(open(HS.STATE_FILE), object_hook=HS.H._dec)
    st["arms"]["PM"]["pos"] = None                                                       # his sim book is flat again, but the would-be short is still riding
    json.dump(st, open(HS.STATE_FILE, "w"), default=HS.H._enc)
    r = box.step(at(14, 35))
    assert r["decision"]["entry_action"] == "SKIPPED_SHADOW_HOLDING" and r["decision"]["shadow_open"] is True


def test_claude_exit_only_closes_his_own_sim_book(box):
    box.action[0] = "ENTER_LONG"
    box.step(at(14, 30))
    box.gate[0] = "HOLDING"                                                              # a real position keeps his sim book alive
    box.action[0] = "EXIT"
    box.step(at(14, 35))
    st = json.load(open(HS.STATE_FILE), object_hook=HS.H._dec)
    assert st["arms"]["PM"]["pos"] is None and len(st["arms"]["PM"]["done"]) == 1
    assert [p.name for p in box.dir.iterdir() if "buy" in p.name or "claim" in p.name] == []


# ── LOCKSHADOW exists only on a session the live robot locked ──────────────────────────────────────────────────────────
def test_lockshadow_is_dormant_until_and_unless_the_live_robot_locks(box):
    r = box.step(at(10, 0))
    assert (r["status"], r["arm"]) == ("NO_LOCK", "v1.02-LOCKSHADOW") and box.asked == []
    box.live["lock"] = lock_state(10, 30)
    assert box.step(at(10, 20))["status"] == "BEFORE_LOCK"
    r = box.step(at(10, 30))
    assert r["status"] == "OK" and len(box.asked) == 1
    box.lock_on[0] = False
    assert box.step(at(10, 35))["status"] == "LOCK_DISABLED" and len(box.asked) == 1


def test_lockshadow_inherits_the_live_sim_book_and_trade_list_at_the_lock(box):
    pos = {"dir": 1, "entry": BASE, "peak": 3.0, "peak_1m": 3.0, "last_ts": T0 - 600, "opened": dt.datetime.fromtimestamp(T0 - 3600, UTC), "reason": "x"}
    box.live.update({"lock": lock_state(14 - 4, 30), "pos": pos, "done": [{"pnl_usd": 12.0}]})
    box.gate[0] = "HOLDING"
    box.step(at(10, 30))
    st = json.load(open(HS.STATE_FILE), object_hook=HS.H._dec)
    a = st["arms"]["LOCK"]
    assert a["done"] == [{"pnl_usd": 12.0}] and a["pos"] is not None and a["pos"]["entry"] == BASE and a["pos"]["dir"] == 1
    assert box.live["done"] == [{"pnl_usd": 12.0}] and box.live["pos"]["last_ts"] == T0 - 600     # the live book is untouched
    start = [r for r in box.log() if r["event"] == "ARM_START"][0]
    assert start["arm"] == "LOCK" and start["inherited_pos"] is True


def test_the_two_arms_keep_separate_books(box):
    box.live["lock"] = lock_state(10, 0)
    box.action[0] = "ENTER_LONG"
    box.step(at(10, 5))
    box.step(at(14, 30))
    st = json.load(open(HS.STATE_FILE), object_hook=HS.H._dec)
    assert st["arms"]["LOCK"]["decisions"] == 1 and st["arms"]["PM"]["decisions"] == 1
    assert st["arms"]["LOCK"]["last_op"] != st["arms"]["PM"]["last_op"]


def test_a_new_session_never_inherits_a_simulated_position(box):
    box.action[0] = "ENTER_LONG"
    box.step(at(14, 30))
    st = HS.load_state("2026-10-14")
    assert st["arms"]["PM"]["pos"] is None and st["arms"]["PM"]["decisions"] == 0


# ── dry runs, fakes and errors ──────────────────────────────────────────────────────────────────────────────────────────
def test_a_dry_run_writes_nothing_and_a_fake_costs_no_call(box):
    box.action[0] = "ENTER_LONG"
    r = HS.step(at(14, 30), dry=True, fake="ENTER_LONG", clock=lambda: at(14, 30))
    assert r["status"] == "DRY_DECISION" and r["entry_action"] == "WOULD_PRESS_BUY"
    assert box.asked == [] and not os.path.exists(HS.LOG_FILE) and not os.path.exists(HS.STATE_FILE)


def test_dry_results_are_never_graded(box, monkeypatch):
    box.log_lines = [{"event": "DECISION", "arm": "PM", "decision_ts": at(14, 30, 0).isoformat(), "dry": True, "entry_action": "WOULD_PRESS_BUY"}]
    open(HS.LOG_FILE, "w").write("\n".join(json.dumps(x) for x in box.log_lines) + "\n")
    assert HS.read_log(HS.LOG_FILE, KEY)["decisions"]["PM"] == {}


def test_a_claude_error_is_counted_and_a_poisoned_arm_day_is_not_scored(box):
    box.action[0] = "WAIT"
    errs = {"n": 0}

    def ask(prompt):
        errs["n"] += 1
        return {"action": "WAIT", "error": "boom"} if errs["n"] <= 2 else {"action": "WAIT"}
    HS.S.ask = ask
    for m in (30, 35, 40):
        box.step(at(14, m))
    day = HS.grade_day(KEY)
    pm = day["arms"]["PM"]
    assert pm["calls"] == 3 and pm["errors"] == 2 and pm["poisoned"] is True


# ── grading ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _decision(arm, h, m, side, px):
    return {"event": "DECISION", "arm": arm, "arm_label": HS.ARMS[arm], "decision_ts": at(h, m, 0).isoformat(), "px": px, "action": "ENTER_LONG" if side > 0 else "ENTER_SHORT",
            "error": None, "entry_action": "WOULD_PRESS_" + ("BUY" if side > 0 else "SELL"), "entry_px": px, "entry_dir": side, "reason": "r"}


def test_a_hit_nets_294_and_a_miss_is_marked_at_the_last_print_with_its_mae(box):
    rows = [_decision("PM", 14, 30, 1, BASE), _decision("PM", 14, 40, -1, price(T0 + 600))]
    open(HS.LOG_FILE, "w").write("\n".join(json.dumps(x) for x in rows) + "\n")
    day = HS.grade_day(KEY)
    es = day["arms"]["PM"]["entries"]
    assert [e["side"] for e in es] == ["BUY", "SELL"] and [e["hit"] for e in es] == [True, False]
    assert es[0]["net_usd"] == 294.0 and es[0]["mae_pt"] == 0.0
    last = price(D0 + HS.HARD_FLAT_MIN * 60)
    assert es[1]["net_usd"] == round(4 * ((price(T0 + 600) - last) * 2.0 - 1.5), 2) and es[1]["mae_pt"] == 0.0
    assert es[1]["net_usd"] < 0
    assert day["arms"]["PM"]["n"] == 2 and day["arms"]["PM"]["hits"] == 1 and day["arms"]["PM"]["misses"] == 1


def test_the_summary_leads_with_counts_then_the_tail_then_dollars_and_never_pools_arms(box):
    rows = [_decision("PM", 14, 30, 1, BASE), _decision("PM", 14, 40, -1, price(T0 + 600))]
    open(HS.LOG_FILE, "w").write("\n".join(json.dumps(x) for x in rows) + "\n")
    r = HS.grade(KEY)
    txt = (box.dir / "out" / "SUMMARY.txt").read_text()
    pm = r["summary"]["PM"]
    assert pm["n_entries"] == 2 and pm["n_misses"] == 1 and pm["p_miss"] == 0.5 and pm["tag"] == "UNDERPOWERED (n<10)"
    assert r["summary"]["LOCK"]["n_entries"] == 0 and r["summary"]["LOCK"]["tag"] == "NO DATA"
    i_counts, i_tail, i_usd = txt.index("MISSES"), txt.index("TAIL"), txt.index("$/day")
    assert i_counts < i_tail < i_usd
    assert txt.index("v1.02-LOCKSHADOW") != txt.index("v1.02-PM-shadow")
    assert sorted(p.name for p in (box.dir / "out").iterdir()) == [f"{KEY}.json", "SUMMARY.json", "SUMMARY.txt"]


def test_no_decision_or_fitting_label_below_30_entries():
    assert HS._tag(0) == "NO DATA" and "UNDERPOWERED" in HS._tag(9)
    assert "NO FITTING" in HS._tag(10) and "NO FITTING" in HS._tag(29) and HS._tag(30) == "n>=30"


def test_a_missing_lock_arm_is_named_when_the_live_robot_locked_and_the_shadow_made_no_decision(box):
    open(HS.LOG_FILE, "w").write("")
    live = [json.dumps({"event": "DAY_LOCK", "at": at(10, 31).isoformat(), "touched_at": at(10, 28).isoformat(), "decision_ts": at(10, 30, 0).isoformat(), "peak": 1010.0})]
    HS.H.LOG_FILE = str(box.dir / "live.jsonl")
    open(HS.H.LOG_FILE, "w").write("\n".join(live) + "\n")
    day = HS.grade_day(KEY)
    assert day["arms"]["LOCK"]["status"] == "MISSING_LOCK_ARM"
    assert HS.summarise([day])["LOCK"]["missing_lock_arm_days"] == [KEY]


def test_pm_summary_splits_by_entry_hour_block(box):
    rows = [_decision("PM", 14, 30, 1, BASE), _decision("PM", 17, 0, 1, price(D0 + 17 * 3600)), _decision("PM", 19, 0, 1, price(D0 + 19 * 3600))]
    open(HS.LOG_FILE, "w").write("\n".join(json.dumps(x) for x in rows) + "\n")
    s = HS.grade(KEY)["summary"]["PM"]["by_hour_block"]
    assert [v["n"] for v in s.values()] == [1, 1, 1] and list(s) == ["13:30-16:00", "16:00-18:00", "18:00-19:55"]


def test_grading_is_idempotent_and_reads_no_wall_clock(box):
    rows = [_decision("PM", 14, 30, 1, BASE)]
    open(HS.LOG_FILE, "w").write("\n".join(json.dumps(x) for x in rows + rows) + "\n")           # the same decision logged twice counts once
    a = HS.grade_day(KEY)
    assert a["arms"]["PM"]["n"] == 1
    assert HS.default_day(dt.datetime(2026, 10, 13, 20, 56, tzinfo=UTC)) == "2026-10-13"
    assert HS.default_day(dt.datetime(2026, 10, 13, 20, 30, tzinfo=UTC)) == "2026-10-12"
