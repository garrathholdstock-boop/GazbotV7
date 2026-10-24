"""THE HYBRID'S NIGHTLY REVIEW (E92): read-only analysis, critical-only paging, a weekly pack for Saturday.

Nothing here reads the wall clock (`now` is injected), calls Claude, pages anyone (`send` is injected) or touches the live desk: every path
is redirected into tmp_path by `mk`, and the fixtures are synthetic 5s bars + a synthetic ledger. The module's AUTHORITY (what it can write,
what it can run) is asserted against the AST, not by grepping text, because the docstring names the files it must never touch.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import sqlite3
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
SRC = GB / "scripts" / "hybrid_nightly.py"
sys.path.insert(0, str(GB / "scripts"))
sys.path.insert(0, str(GB / "src"))
import hybrid_nightly as HN  # noqa: E402

H, L, S = HN.H, HN.L, HN.S
UTC = dt.timezone.utc
KEY = "2026-10-15"                                   # a Thursday, CEST: the 05:00 Paris veto is 03:00Z
D0 = int(dt.datetime(2026, 10, 15, tzinfo=UTC).timestamp())
EVE = dt.datetime(2026, 10, 15, 20, 50, 30, tzinfo=UTC)
SLOTS = list(range(D0 + S.WIN_START_MIN * 60, D0 + S.WIN_END_MIN * 60, 300))
BRIEF_SHA = hashlib.sha256(S.brief_for(H.LINE).encode()).hexdigest()[:16]


def T(h, m=0, s=0):
    return D0 + h * 3600 + m * 60 + s


def iso(ts):
    return dt.datetime.fromtimestamp(ts, UTC).isoformat()


# ── synthetic world ─────────────────────────────────────────────────────────────────────────────────────────────────────
def flat_px(_t):
    return 20000.0


def fall_from(t0, rate=1.0, base=20000.0):
    """price flat, then falling `rate` pt per 5s bar from t0 (a SHORT entered at ~base wins)"""
    return lambda t: base if t < t0 else base - rate * ((t - t0) // 5)


def mk(tmp, px=flat_px, ledger=(), decisions="all", day_rec="good", switch="on", rider=None, ticks=(), extra_log=(), series=None, key=KEY):
    """Build an Env over tmp. Returns (env, ctx). `decisions` is 'all', 'none' or a set of slot timestamps to LEAVE OUT."""
    d0 = int(dt.datetime.fromisoformat(key + "T00:00:00+00:00").timestamp())
    cap, led = tmp / "capture.db", tmp / "gazbot7.db"
    con = sqlite3.connect(cap)
    con.execute("CREATE TABLE bars(symbol TEXT, timeframe TEXT, bar_ts INTEGER, open REAL, high REAL, low REAL, close REAL, volume REAL)")
    con.executemany("INSERT INTO bars VALUES('MNQ','5s',?,?,?,?,?,1)",
                    [(t, px(t), px(t) + 0.25, px(t) - 0.25, px(t)) for t in range(d0 - 2 * 3600, d0 + 22 * 3600, 5)])
    con.commit()
    con.close()
    con = sqlite3.connect(led)
    con.execute("CREATE TABLE trades(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL, qty REAL NOT NULL, "
                "entry_price REAL NOT NULL, exit_price REAL NOT NULL, entry_exec_id TEXT, exit_exec_id TEXT, opened_at TEXT NOT NULL, "
                "closed_at TEXT NOT NULL, pnl_usd REAL NOT NULL, fees_usd REAL NOT NULL DEFAULT 0, exit_reason TEXT NOT NULL, gate TEXT, "
                "data_quality TEXT, entry_source TEXT, exit_source TEXT)")
    for r in ledger:
        con.execute("INSERT INTO trades(symbol,side,qty,entry_price,exit_price,opened_at,closed_at,pnl_usd,exit_reason,gate,data_quality,entry_source) "
                    "VALUES('MNQ',?,?,?,?,?,?,?,?,'day_rider',?,?)",
                    (r["side"], r.get("qty", 1), r["entry"], r["exit"], r["opened"], r["closed"], r["pnl"], r["reason"], r.get("dq"), r.get("src")))
    con.commit()
    con.close()
    slots = [o for o in range(d0 + S.WIN_START_MIN * 60, d0 + S.WIN_END_MIN * 60, 300)]
    left_out = set(slots) if decisions == "none" else (set(decisions) if decisions != "all" else set())
    over = {r["decision_ts_slot"]: r for r in extra_log if "decision_ts_slot" in r}
    lines = []
    for op in slots:
        if op in left_out:
            continue
        rec = {"event": "DECISION", "at": iso(op + 20), "decision_ts": iso(op), "px": 20000.0, "action": "HOLD", "conf": 0.5, "reason": "x",
               "error": None, "sim_holding": False, "latency_s": 12.0, "dry": False}
        rec.update({k: v for k, v in over.get(op, {}).items() if k != "decision_ts_slot"})
        lines.append(json.dumps(rec))
    lines += [json.dumps({k: v for k, v in r.items() if k != "decision_ts_slot"}) for r in extra_log if "decision_ts_slot" not in r]
    (tmp / "log.jsonl").write_text("\n".join(lines) + "\n")
    (tmp / "hybrid_robot.env").write_text(f"hybrid_robot={switch}\n")
    (tmp / "leg_robot.env").write_text("leg_robot=off\n")
    (tmp / "days").mkdir(exist_ok=True)
    if day_rec == "good":
        n = len(slots) - len(left_out)
        (tmp / "days" / f"{key}.json").write_text(json.dumps({"version": H.VERSION, "day": key, "calls": n, "errors": 0, "poisoned": False,
                                                              "brief_sha": BRIEF_SHA, "partial_from": None, "claude_sim_net_usd": 0.0,
                                                              "claude_sim_trades": []}))
    elif isinstance(day_rec, dict):
        (tmp / "days" / f"{key}.json").write_text(json.dumps(day_rec))
    (tmp / "rider.json").write_text(json.dumps(rider if rider is not None else {"lots_open": 0, "venue_net": 0, "entered": False, "closed": False}))
    env = HN.Env(gb=str(tmp), out=str(tmp / "out"), series_fn=series or (lambda d: []), ticks_fn=lambda e, k: list(ticks) if ticks is not None else None,
                 log=str(tmp / "log.jsonl"), state=str(tmp / "state.json"), switch=str(tmp / "hybrid_robot.env"),
                 leg_switch=str(tmp / "leg_robot.env"), daydir=str(tmp / "days"), ledger=str(led), capture=str(cap),
                 rider_state=str(tmp / "rider.json"))
    return env


def codes(rep, sev=None):
    return sorted(h["code"] for h in rep["health"] if sev is None or h["sev"] == sev)


def press_world(tmp, *, side="SHORT", entry_action="PRESS_SELL", detector_dir=-1, op=T(5, 0), lots=4, lag=3, qty_row=None, reason="TARGET_1",
                dq=None, nlots_rows=None, ledger_extra=(), rate=None, **kw):
    """a SHORT press decided at `op`, filled at op+25, falling 1pt/5s so +37.5pt is crossed 190s after the fill-ish; lots sold `lag`s after the cross"""
    fill = op + 25
    cross_t = fill + 210                              # price starts falling at fill+20, 1pt/5s: low <= 19962.5 at the bar starting t0+190
    rows = []
    if qty_row is not None:
        rows.append({"side": side, "qty": qty_row, "entry": 20000.0, "exit": 19980.0, "opened": iso(fill), "closed": iso(cross_t + 600),
                     "pnl": -579.5, "reason": "MANUAL_CLAIM"})
    else:
        for _ in range(nlots_rows if nlots_rows is not None else lots):
            rows.append({"side": side, "qty": 1, "entry": 20000.0, "exit": 19962.5, "opened": iso(fill), "closed": iso(cross_t + lag),
                         "pnl": 73.5, "reason": reason, "dq": dq})
    rows += list(ledger_extra)
    req = f"{iso(op + 20)}|{'SELL' if side == 'SHORT' else 'BUY'}|4|75,75,75,75"
    ex = {"decision_ts_slot": op, "action": "ENTER_SHORT" if side == "SHORT" else "ENTER_LONG", "candidate": "SHORT" if side == "SHORT" else "LONG",
          "detector_dir": detector_dir, "veto_cutoff": iso(T(3)), "entry_action": entry_action, "request": req}
    if rate is None:
        rate = -0.2 if qty_row is not None else 1.0           # a claimed entry is one that never reached its rung: the tape ran AGAINST the short
    return mk(tmp, px=fall_from(fill + 20, rate=rate), ledger=rows, extra_log=[ex] if not kw.get("no_ex") else [], **{k: v for k, v in kw.items() if k != "no_ex"})


# ── 1. AUTHORITY: it can read, it can write only its own reports, and it can run exactly one fixed command ───────────────
_TREE = ast.parse(SRC.read_text())


def _tree():
    return _TREE


def _code_strings():
    t = _tree()
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    return [n.value for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docs]


def _enclosing(fn_name_of):
    """map every Call/Attr node to the name of its enclosing function"""
    out = {}
    for f in ast.walk(_tree()):
        if isinstance(f, ast.FunctionDef):
            for n in ast.walk(f):
                out.setdefault(id(n), []).append(f.name)
    return out


def test_it_has_no_broker_no_order_path_and_no_other_request_file():
    imported = set()
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0])
    assert not imported & {"ib_insync", "ib_async", "ibapi", "requests", "urllib", "smtplib", "socket", "shutil"}, imported
    bad = [(s, f) for s in _code_strings()
           for f in ("day_rider_buy", "day_rider_claim", "gate_switches", "desk_kill", "placeOrder", "MarketOrder", "LimitOrder", ".notify_env", "hybrid_robot.env\"")
           if f in s]
    assert not bad, bad
    names = {n.attr for n in ast.walk(_tree()) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(_tree()) if isinstance(n, ast.Name)}
    assert not names & {"BUY_FILE", "write_press", "placeOrder", "claim", "CLAIM_FILE"}, names & {"BUY_FILE", "write_press", "claim"}


def test_the_only_subprocess_is_one_fixed_argv_journalctl_read():
    calls = [n for n in ast.walk(_tree()) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"]
    assert len(calls) == 1 and calls[0].func.attr == "run", [c.func.attr for c in calls]
    argv = calls[0].args[0]
    assert isinstance(argv, ast.List) and isinstance(argv.elts[0], ast.Constant) and argv.elts[0].value == "journalctl"
    assert not any(k.arg == "shell" for k in calls[0].keywords), "no shell"
    flat = [e.value for e in argv.elts if isinstance(e, ast.Constant)]
    assert not set(flat) & {"restart", "start", "stop", "kill", "enable", "disable", "systemctl", "--vacuum-size", "--rotate"}, flat


def test_every_write_goes_through_atomic_write_and_only_atomic_write():
    enc = _enclosing(None)
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            is_os_replace = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "os"
            open_w = name == "open" and len(n.args) > 1 and isinstance(n.args[1], ast.Constant) and any(c in str(n.args[1].value) for c in "wax+")
            recv = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ""
            other = name in {"unlink", "rmtree", "makedirs", "write_text", "write_bytes", "touch", "utime", "chmod", "chown"} or (name in {"remove", "rename"} and recv in {"os", "shutil"})
            writes = open_w or other or (name == "replace" and is_os_replace)
            if writes:
                assert enc.get(id(n)) and "atomic_write" in enc[id(n)], f"{name} outside atomic_write at line {n.lineno}"
    # sqlite is opened read-only by URI, never by plain path
    uris = [s for s in _code_strings() if "mode=ro" in s]
    assert len(uris) >= 2, uris
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "connect":
            assert any(isinstance(k, ast.keyword) and k.arg == "uri" for k in n.keywords), f"sqlite3.connect at {n.lineno} is not a read-only URI"


def test_a_review_changes_neither_database_nor_any_input_file(tmp_path):
    env = press_world(tmp_path)
    inputs = [env.capture, env.ledger, env.log, env.switch, env.leg_switch, env.rider_state, f"{env.daydir}/{KEY}.json"]
    before = {p: hashlib.sha256(open(p, "rb").read()).hexdigest() for p in inputs}
    mt = {p: os.stat(p).st_mtime_ns for p in inputs}
    HN.run(env, KEY, EVE, send=lambda m: None)
    assert before == {p: hashlib.sha256(open(p, "rb").read()).hexdigest() for p in inputs}
    assert mt == {p: os.stat(p).st_mtime_ns for p in inputs}
    assert not (tmp_path / "gazbot7.db-journal").exists() and not (tmp_path / "gazbot7.db-wal").exists()


def test_atomic_write_refuses_anything_outside_its_directory(tmp_path):
    env = HN.Env(out=str(tmp_path / "out"))
    for bad in ("../escape.txt", "/etc/escape.txt", "sub/x.txt", "./../x"):
        with pytest.raises(ValueError):
            HN.atomic_write(env, bad, "x")
    assert not (tmp_path / "escape.txt").exists()
    p = HN.atomic_write(env, "ok.txt", "hello")
    assert open(p).read() == "hello" and not os.path.exists(p + ".tmp")


def test_the_unit_and_timer_are_what_the_docs_say():
    svc = (GB / "ops/systemd/gazbot7-hybrid-nightly.service").read_text()
    tim = (GB / "ops/systemd/gazbot7-hybrid-nightly.timer").read_text()
    assert "User=alphabot" in svc and "Type=oneshot" in svc and "hybrid_nightly.py" in svc
    assert "SuccessExitStatus=0 3" in svc, "a FAULT verdict (exit 3) is a finding, not a failed unit"
    assert "OnCalendar=*-*-* 20:50:00 UTC" in tim and "Persistent=true" in tim
    assert not any(l.startswith("OnCalendar=") and "Mon" in l for l in tim.splitlines()), "daily, so the supervisor's 26h freshness window does not false-fault on Sunday evening"


# ── 2. a healthy day ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_quiet_healthy_day_is_OK_and_complete(tmp_path):
    env = mk(tmp_path)
    rep = HN.review_day(env, KEY, EVE)
    assert rep["verdict"] == "OK", rep["health"]
    cov = rep["coverage"]
    assert cov["expected"] == len(SLOTS) and cov["decided"] == len(SLOTS) and cov["unexplained"] == 0
    assert rep["arm"] == "v1.02+LOCK" and rep["totals"]["presses"] == 0 and rep["totals"]["ledger_net_usd"] == 0.0


def test_a_full_winning_press_is_attributed_and_costed_from_the_ledger(tmp_path):
    env = press_world(tmp_path)
    rep = HN.review_day(env, KEY, EVE)
    assert rep["verdict"] == "OK", rep["health"]
    p = rep["presses"][0]
    assert p["filled"] and p["n_lots"] == 4 and p["n_closed"] == 4 and p["ledger_net_usd"] == 294.0
    assert rep["funnel"]["pressed"] == 1 and rep["funnel"]["filled_entries"] == 1 and rep["totals"]["lots_by_target"] == 4
    assert all(l["target_pt"] == 37.5 and l["target_exit"] and 0 <= l["lag_s"] <= 10 for l in p["lots"])
    assert p["mfe_pt"] >= 37.5 and p["post_fast_ladder"] is True
    assert rep["detector"]["sha_ok"] is True


def test_a_four_lot_claim_is_ONE_row_with_qty_4_and_is_not_a_partial_entry(tmp_path):
    """★ the 2026-10-14 16:25 entry: the operator's MANUAL_CLAIM closed four lots as a single qty=4 row. Counting ROWS reported a 1-lot entry."""
    env = press_world(tmp_path, qty_row=4)
    rep = HN.review_day(env, KEY, EVE)
    assert "PRESS_LOT_COUNT" not in codes(rep), rep["health"]
    p = rep["presses"][0]
    assert p["n_lots"] == 4 and p["n_closed"] == 4 and p["manual_exit"] is True and p["ledger_net_usd"] == -579.5
    assert "OPERATOR_EXIT" in codes(rep, "INFO") and rep["verdict"] == "OK"
    assert rep["totals"]["manual_exit_entries"] == 1 and rep["totals"]["lots_by_target"] == 0 and rep["totals"]["lots_other_exit"] == 4


def test_three_lot_entry_is_a_FAULT_once_the_flat_has_passed_and_not_before(tmp_path):
    env = press_world(tmp_path, nlots_rows=3)
    assert "PRESS_LOT_COUNT" in codes(HN.review_day(env, KEY, EVE), "FAULT")
    mid = dt.datetime(2026, 10, 15, 8, 0, tzinfo=UTC)               # session still live: lots may be mid-ladder
    assert "PRESS_LOT_COUNT" not in codes(HN.review_day(env, KEY, mid))


def test_a_press_with_no_ledger_rows_is_a_FAULT_only_after_the_flat_and_when_the_rider_is_flat(tmp_path):
    env = press_world(tmp_path, lots=0)
    assert "PRESS_NOT_ENTERED" in codes(HN.review_day(env, KEY, EVE), "FAULT")
    assert "PRESS_NOT_ENTERED" not in codes(HN.review_day(env, KEY, dt.datetime(2026, 10, 15, 6, 0, tzinfo=UTC)))
    holding = press_world(tmp_path / "h", lots=0, rider={"lots_open": 4, "venue_net": 4, "entered": True, "closed": False}) if (tmp_path / "h").mkdir() is None else None
    c = codes(HN.review_day(holding, KEY, EVE), "FAULT")
    assert "NOT_FLAT" in c and "PRESS_NOT_ENTERED" not in c, "an open position is NOT_FLAT's finding, not a vanished entry"


def test_excluded_lots_are_flagged_and_not_counted(tmp_path):
    env = press_world(tmp_path, dq="EXCLUDE: test")
    rep = HN.review_day(env, KEY, EVE)
    assert rep["presses"][0]["ledger_net_usd"] == 0.0 and "FLAGGED_LOTS" in codes(rep, "WARN")


def test_riders_entries_the_hybrid_did_not_make_are_not_in_its_numbers(tmp_path):
    other = [{"side": "LONG", "qty": 1, "entry": 19000.0, "exit": 19010.0, "opened": iso(T(11)), "closed": iso(T(11, 30)), "pnl": 18.5, "reason": "TARGET_1"}]
    env = press_world(tmp_path, ledger_extra=other)
    rep = HN.review_day(env, KEY, EVE)
    assert rep["totals"]["ledger_net_usd"] == 294.0 and len(rep["unattributed_entries"]) == 1
    assert "UNATTRIBUTED_ENTRIES" in codes(rep, "INFO") and rep["verdict"] == "OK"


# ── 3. the entry rules, audited after the fact ────────────────────────────────────────────────────────────────────────────
def test_a_press_against_the_detectors_leg_is_a_FAULT(tmp_path):
    rep = HN.review_day(press_world(tmp_path, detector_dir=+1), KEY, EVE)
    assert "PRESS_RULE_BREACH" in codes(rep, "FAULT")


def test_a_press_before_the_05_paris_veto_is_a_FAULT(tmp_path):
    rep = HN.review_day(press_world(tmp_path, op=T(2, 30)), KEY, EVE)           # 03:00Z is the cutoff in CEST
    assert "PRESS_RULE_BREACH" in codes(rep, "FAULT")
    ok = HN.review_day(press_world(tmp_path / "x", op=T(3, 0)) if (tmp_path / "x").mkdir() is None else None, KEY, EVE)
    assert "PRESS_RULE_BREACH" not in codes(ok)


def test_candidate_funnel_counts_every_skip_reason(tmp_path):
    extra = []
    for i, ea in enumerate(["NOT_WITH_LEG", "NO_DETECTOR_LEG", "VETOED_BEFORE_05_PARIS", "STALE_NOT_ENTERED", "SKIPPED_HOLDING"]):
        extra.append({"decision_ts_slot": T(6, 5 * i), "action": "ENTER_LONG", "candidate": "LONG", "detector_dir": -1 if ea != "NO_DETECTOR_LEG" else None,
                      "veto_cutoff": iso(T(3)), "entry_action": ea})
    rep = HN.review_day(mk(tmp_path, extra_log=extra), KEY, EVE)
    f = rep["funnel"]
    assert f["enter_signals"] == 5 and f["not_with_leg"] == 2 and f["vetoed_before_05_paris"] == 1 and f["stale"] == 1 and f["skipped_rider_busy"] == 1
    assert "STALE_ENTRIES" in codes(rep, "WARN") and rep["verdict"] == "WARN"


def test_the_counterfactual_is_first_passage_on_the_tape(tmp_path):
    """an ENTER_SHORT skipped as NOT_WITH_LEG on a tape that then falls 60pt: its counterfactual REACHED +37.5 (and the filter cost that)"""
    ex = [{"decision_ts_slot": T(6, 0), "action": "ENTER_SHORT", "candidate": "SHORT", "detector_dir": +1, "veto_cutoff": iso(T(3)), "entry_action": "NOT_WITH_LEG"}]
    rep = HN.review_day(mk(tmp_path, px=fall_from(T(6, 1)), extra_log=ex), KEY, EVE)
    c = rep["candidates"][0]
    assert c["cf_reached_champion"] is True and c["cf_mfe_pt"] >= 37.5 and 0 < c["cf_minutes_to_champion"] < 5
    assert c["cf_grid_usd"]["37.5"] == round(4 * (37.5 * 2 - 1.5), 2)


# ── 4. coverage: what a missing slot means ────────────────────────────────────────────────────────────────────────────────
def _gone(a, n):
    return {T(a) + 300 * i for i in range(n)}


def test_missing_slots_with_no_cause_anywhere_are_a_COVERAGE_FAULT(tmp_path):
    gone = _gone(8, 8)                                                    # 8 consecutive 5-min slots = 40 minutes of nothing
    ticks = [{"ts": o + 20, "status": "OK"} for o in SLOTS if o not in gone]
    ticks += [{"ts": o + 20, "status": "OK"} for o in gone]               # the timer DID fire and logged OK, yet no decision exists
    rep = HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks), KEY, EVE)
    assert "COVERAGE" in codes(rep, "FAULT") and rep["coverage"]["longest_unexplained_run"] == 8 and rep["verdict"] == "FAULT"


def test_a_LATE_TICK_explains_the_slot_it_cost(tmp_path):
    """★ the 14:55 slot on 2026-10-14: lost to a timer edit, recorded ONLY in the journal"""
    gone = {SLOTS[40]}
    ticks = [{"ts": SLOTS[40] + 250, "status": "LATE_TICK", "late_s": 250}]
    rep = HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks), KEY, EVE)
    assert rep["coverage"]["late_tick"] == 1 and rep["coverage"]["unexplained"] == 0 and rep["verdict"] == "OK"
    assert "LATE_TICKS" in codes(rep, "INFO")


def test_three_or_more_late_ticks_is_a_WARN(tmp_path):
    gone = {SLOTS[i] for i in (10, 20, 30)}
    ticks = [{"ts": o + 200, "status": "LATE_TICK", "late_s": 200} for o in gone]
    assert "LATE_TICKS" in codes(HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks), KEY, EVE), "WARN")


def test_a_stale_feed_in_the_journal_explains_the_gap(tmp_path):
    gone = _gone(10, 3)
    ticks = [{"ts": o + 20, "status": "FEED_STALE"} for o in gone]
    rep = HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks), KEY, EVE)
    assert rep["coverage"]["feed_explained"] == 3 and rep["coverage"]["unexplained"] == 0 and "FEED_GAPS" in codes(rep, "INFO")


def test_a_dead_tape_explains_a_gap_even_with_no_journal_record(tmp_path):
    """no bars for 30 minutes around the slots: the robot declined to decide on a dead feed, and the review says so rather than faulting it"""
    gone = _gone(9, 3)
    px = lambda t: 20000.0                                                # noqa: E731
    env = mk(tmp_path, px=px, decisions=gone, ticks=[])
    con = sqlite3.connect(env.capture)
    con.execute("DELETE FROM bars WHERE bar_ts BETWEEN ? AND ?", (T(8, 45), T(9, 45)))
    con.commit()
    con.close()
    rep = HN.review_day(env, KEY, EVE)
    assert rep["coverage"]["feed_explained"] == 3 and rep["coverage"]["unexplained"] == 0


def test_a_slot_with_no_journal_record_at_all_means_the_timer_did_not_fire(tmp_path):
    gone = {SLOTS[50], SLOTS[51]}
    ticks = [{"ts": o + 20, "status": "OK"} for o in SLOTS if o not in gone]
    rep = HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks), KEY, EVE)
    assert "TIMER_DID_NOT_FIRE" in codes(rep, "WARN")


def test_an_unreadable_journal_degrades_to_unexplained_not_to_a_crash(tmp_path):
    gone = {SLOTS[5]}
    env = mk(tmp_path, decisions=gone, ticks=None)
    rep = HN.review_day(env, KEY, EVE)
    assert rep["coverage"]["journal_ok"] is False and rep["coverage"]["unexplained"] == 1 and rep["verdict"] in ("OK", "WARN")


def test_a_preflight_failure_or_leg_robot_conflict_is_a_FAULT(tmp_path):
    gone = _gone(7, 3)
    ticks = [{"ts": o + 20, "status": "PREFLIGHT_FAILED", "fault": "DETECTOR_SHA"} for o in gone]
    assert "ROBOT_REFUSED" in codes(HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks), KEY, EVE), "FAULT")


def test_switch_off_is_a_WARN_about_coverage_not_a_FAULT(tmp_path):
    rep = HN.review_day(mk(tmp_path, decisions="none", switch="off", ticks=[]), KEY, EVE)
    assert "SWITCH_OFF" in codes(rep, "WARN") and "COVERAGE" not in codes(rep, "FAULT")


def test_a_missing_log_is_a_FAULT_when_decisions_were_due(tmp_path):
    env = mk(tmp_path)
    os.remove(env.log)
    assert "LOG_UNREADABLE" in codes(HN.review_day(env, KEY, EVE), "FAULT")


def test_corrupt_log_lines_are_counted_not_skipped_silently(tmp_path):
    env = mk(tmp_path)
    with open(env.log, "a") as f:
        f.write("{not json\n")
    assert "LOG_CORRUPT_LINES" in codes(HN.review_day(env, KEY, EVE), "WARN")


def test_a_decision_on_another_session_or_a_dry_run_is_not_this_sessions(tmp_path):
    extra = [{"event": "DECISION", "at": "2026-10-16T02:00:20+00:00", "decision_ts": "2026-10-16T02:00:00+00:00", "action": "HOLD", "dry": False},
             {"event": "DECISION", "at": iso(T(9)), "decision_ts": iso(T(9, 0)), "action": "HOLD", "dry": True}]
    rep = HN.review_day(mk(tmp_path, extra_log=extra), KEY, EVE)
    assert rep["coverage"]["decided"] == len(SLOTS) and "DOUBLE_DECISION" not in codes(rep)


# ── 5. Claude's calls, the day record, the frozen things ──────────────────────────────────────────────────────────────────
def test_over_ten_percent_call_errors_poison_the_day(tmp_path):
    bad = {SLOTS[i]: {"decision_ts_slot": SLOTS[i], "error": "boom"} for i in range(0, 40)}
    rep = HN.review_day(mk(tmp_path, extra_log=list(bad.values())), KEY, EVE)
    assert "POISONED_DAY" in codes(rep, "FAULT")


def test_a_few_call_errors_are_a_WARN(tmp_path):
    bad = [{"decision_ts_slot": SLOTS[i], "error": "boom"} for i in range(0, 6)]
    rep = HN.review_day(mk(tmp_path, extra_log=bad), KEY, EVE)
    assert "CALL_ERRORS" in codes(rep, "WARN") and "POISONED_DAY" not in codes(rep)


def test_slow_claude_calls_are_a_WARN(tmp_path):
    slow = [{"decision_ts_slot": o, "latency_s": 140.0} for o in SLOTS[:30]]
    assert "LATENCY" in codes(HN.review_day(mk(tmp_path, extra_log=slow), KEY, EVE), "WARN")


def test_the_close_out_record_must_exist_after_the_window(tmp_path):
    rep = HN.review_day(mk(tmp_path, day_rec=None), KEY, EVE)
    assert "DAY_RECORD_MISSING" in codes(rep, "FAULT")
    during = HN.review_day(mk(tmp_path / "d", day_rec=None) if (tmp_path / "d").mkdir() is None else None, KEY, dt.datetime(2026, 10, 15, 9, tzinfo=UTC))
    assert "DAY_RECORD_MISSING" not in codes(during)


def test_a_poisoned_or_drifted_day_record_is_a_FAULT(tmp_path):
    base = {"version": H.VERSION, "day": KEY, "calls": len(SLOTS), "errors": 0, "poisoned": True, "brief_sha": BRIEF_SHA}
    assert "POISONED_RECORD" in codes(HN.review_day(mk(tmp_path, day_rec=base), KEY, EVE), "FAULT")
    d = tmp_path / "b"
    d.mkdir()
    assert "BRIEF_DRIFT" in codes(HN.review_day(mk(d, day_rec=dict(base, poisoned=False, brief_sha="deadbeef00000000")), KEY, EVE), "FAULT")


def test_a_changed_detector_hash_is_a_FAULT(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "detector_sha", lambda: "0" * 16)
    assert "DETECTOR_SHA" in codes(HN.review_day(mk(tmp_path), KEY, EVE), "FAULT")


def test_the_real_detector_hash_matches_the_frozen_one():
    assert L.detector_sha() == H.DETECTOR_SHA


# ── 6. the ladder ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_rung_left_unsold_for_minutes_after_the_deploy_is_a_FAULT(tmp_path):
    rep = HN.review_day(press_world(tmp_path, lag=400), KEY, EVE)
    assert "LADDER_STALLED" in codes(rep, "FAULT")


def test_the_same_slow_rung_before_the_fast_ladder_is_not_a_fault(tmp_path, monkeypatch):
    monkeypatch.setattr(HN, "FAST_LADDER_LIVE_FROM", dt.datetime(2099, 1, 1, tzinfo=UTC))
    rep = HN.review_day(press_world(tmp_path, lag=400), KEY, EVE)
    assert "LADDER_STALLED" not in codes(rep) and "RUNG_LAG" not in codes(rep) and rep["presses"][0]["post_fast_ladder"] is False


def test_a_rung_that_sold_a_little_late_is_a_WARN(tmp_path):
    rep = HN.review_day(press_world(tmp_path, lag=45), KEY, EVE)
    assert "RUNG_LAG" in codes(rep, "WARN") and "LADDER_STALLED" not in codes(rep)


# ── 7. never hold overnight ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_holding_after_the_flat_is_a_FAULT(tmp_path):
    env = mk(tmp_path, rider={"lots_open": 4, "venue_net": -4, "entered": True, "closed": False})
    assert "NOT_FLAT" in codes(HN.review_day(env, KEY, EVE), "FAULT")


def test_holding_at_20_30_is_not_yet_a_fault(tmp_path):
    env = mk(tmp_path, rider={"lots_open": 4, "venue_net": -4, "entered": True, "closed": False})
    assert "NOT_FLAT" not in codes(HN.review_day(env, KEY, dt.datetime(2026, 10, 15, 20, 30, tzinfo=UTC)))


def test_flat_after_the_flat_is_clean_and_a_backdated_review_never_reads_todays_rider(tmp_path):
    env = mk(tmp_path, rider={"lots_open": 4, "venue_net": -4, "entered": True, "closed": False})
    assert "NOT_FLAT" not in codes(HN.review_day(env, KEY, dt.datetime(2026, 10, 16, 20, 50, tzinfo=UTC)))


# ── 8. sessions, weekends, arms ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_weekend_is_NO_SESSION_not_a_fault(tmp_path):
    key = "2026-10-17"
    env = mk(tmp_path, key=key)
    rep = HN.review_day(env, key, dt.datetime(2026, 10, 17, 20, 50, tzinfo=UTC))
    assert rep["verdict"] == "OK" and "NO_SESSION" in codes(rep, "INFO") and rep["coverage"]["expected"] == 0


def test_a_day_before_the_hybrid_existed_is_not_reviewed_and_writes_nothing_daily(tmp_path):
    env = mk(tmp_path)
    res = HN.run(env, "2026-10-13", dt.datetime(2026, 10, 13, 20, 50, tzinfo=UTC), send=lambda m: None)
    assert res["report"] is None and not (tmp_path / "out" / "2026-10-13.json").exists()


def test_the_afternoon_extension_is_its_own_arm_and_is_never_pooled(tmp_path):
    assert HN.arm_of("2026-10-14") == "v1.02-EXT" and HN.arm_of("2026-10-15") == "v1.02+LOCK"
    ext_slots = HN.expected_slots("2026-10-14", int(dt.datetime(2026, 10, 14, 21, tzinfo=UTC).timestamp()))
    assert ext_slots[-1] == int(dt.datetime(2026, 10, 14, tzinfo=UTC).timestamp()) + (H.EXT_END_MIN - 5) * 60
    assert ext_slots[0] >= int(H.START_AFTER.timestamp())
    a = tmp_path / "a"
    a.mkdir()
    ledger_ext = [{"side": "SHORT", "qty": 1, "entry": 20000.0, "exit": 19962.5, "opened": iso(T(17)), "closed": iso(T(17, 5)), "pnl": 73.5, "reason": "TARGET_1"}] * 4
    env = mk(a, ledger=ledger_ext, key="2026-10-14", decisions="none", switch="off")
    out = env.out
    HN.run(env, "2026-10-14", dt.datetime(2026, 10, 14, 20, 50, tzinfo=UTC), quiet=True)
    env2 = mk(tmp_path / "b", ledger=[]) if (tmp_path / "b").mkdir() is None else None
    env2.out = out
    HN.run(env2, KEY, EVE, quiet=True)
    wk = json.load(open(f"{out}/week_2026-W42.json"))
    assert set(wk["arms"]) == {"v1.02+LOCK", "v1.02-EXT"}
    assert wk["arms"]["v1.02+LOCK"]["cumulative"]["days"] == 1 and wk["arms"]["v1.02-EXT"]["cumulative"]["days"] == 1
    assert wk["arms"]["v1.02+LOCK"]["cumulative"]["net_usd"] == 0.0


def test_a_day_with_no_entries_is_a_zero_day_in_the_consistency_numbers_but_a_weekend_is_not():
    def day(k, net, health=()):
        return {"key": k, "totals": {"ledger_net_usd": net, "filled": 1 if net else 0, "winners": 1 if net > 0 else 0, "manual_exit_entries": 0}, "health": list(health)}
    s = HN.arm_stats([day("2026-10-15", 300.0), day("2026-10-16", 0.0), day("2026-10-17", 0.0, [{"code": "NO_SESSION"}]), day("2026-10-19", -100.0)])
    assert s["days"] == 3 and s["days_positive"] == 1 and s["worst_day"] == -100.0 and s["net_usd"] == 200.0 and s["median_usd_day"] == 0.0


# ── 9. the weekly pack and the shortlist ────────────────────────────────────────────────────────────────────────────────────
def _cf(n, grid, cats):
    return {"real_entries": n, "grid_per_entry_usd": grid, "grid_total_usd": {}, "by_category": cats}


def test_below_ten_entries_nothing_is_called_promising():
    cf = _cf(4, {"12.5": 80.0, "37.5": 100.0, "75.0": 160.0}, {"PRESSED": {"n": 4, "mean_cf37_usd": 100.0, "reached_pct": 100.0},
                                                               "NOT_WITH_LEG": {"n": 4, "mean_cf37_usd": 300.0, "reached_pct": 90.0}})
    sl = HN.shortlist("v1.02", {}, cf)
    assert sl and all(i["status"] in ("UNDERPOWERED", "NOT BETTER", "FILTER EARNING ITS KEEP") or i["status"].startswith(("PARKED", "DATA ONLY")) for i in sl), sl
    assert not [i for i in sl if i["status"] == "PROMISING"]


def test_at_ten_entries_a_better_target_is_PROMISING_and_ranked_first_with_its_governance():
    cf = _cf(12, {"12.5": 80.0, "37.5": 100.0, "75.0": 160.0}, {"PRESSED": {"n": 12, "mean_cf37_usd": 100.0, "reached_pct": 100.0}})
    sl = HN.shortlist("v1.02", {}, cf)
    assert sl[0]["status"] == "PROMISING" and sl[0]["rank"] == 1 and "75.0pt" in sl[0]["change"] and "+60.0" in sl[0]["point_estimate"]
    assert "L2" in sl[0]["governance"] and "L4" in sl[0]["governance"]


def test_the_leg_filter_is_reported_as_earning_its_keep_when_against_the_leg_entries_lose():
    cf = _cf(12, {"37.5": 100.0}, {"PRESSED": {"n": 12, "mean_cf37_usd": 100.0, "reached_pct": 90.0},
                                   "NOT_WITH_LEG": {"n": 15, "mean_cf37_usd": -40.0, "reached_pct": 30.0}})
    it = [i for i in HN.shortlist("v1.02", {}, cf) if "detector-leg filter" in i["change"]][0]
    assert it["status"] == "FILTER EARNING ITS KEEP" and "-40.0" in it["point_estimate"]


def test_the_parked_veto_appears_as_data_only_and_never_ranks_above_a_real_candidate():
    cf = _cf(12, {"37.5": 100.0, "75.0": 130.0}, {"VETOED_BEFORE_05_PARIS": {"n": 9, "mean_cf37_usd": 250.0, "reached_pct": 80.0}})
    sl = HN.shortlist("v1.02", {}, cf)
    veto = [i for i in sl if "veto" in i["change"]][0]
    assert veto["status"].startswith("PARKED") and veto["rank"] > sl[0]["rank"] and sl[0]["status"] == "PROMISING"


def test_pooled_counterfactuals_exclude_provisional_entries():
    p = lambda prov: {"filled": True, "provisional": prov, "grid_usd": {"37.5": 100.0}}          # noqa: E731
    days = [{"presses": [p(False), p(True)], "candidates": []}]
    assert HN.pooled_cf(days)["real_entries"] == 1


def test_the_week_pack_writes_a_ranked_shortlist_and_says_nothing_is_applied(tmp_path):
    env = press_world(tmp_path)
    res = HN.run(env, KEY, EVE, quiet=True)
    txt = open(f"{env.out}/LATEST_WEEK.txt").read()
    assert "RANKED SHORTLIST FOR SATURDAY (never applied)" in txt and "Nothing here is applied" in txt
    assert "UNDERPOWERED" in txt or "NOT BETTER" in txt or "PROMISING" not in txt
    assert res["week"]["arms"]["v1.02+LOCK"]["cumulative"]["entries"] == 1


# ── 10. paging: critical-only, once, and never fatal ───────────────────────────────────────────────────────────────────────
def _fault_env(tmp):
    return mk(tmp, day_rec=None)                         # DAY_RECORD_MISSING is a FAULT


def test_a_fault_pages_once_per_session_and_code(tmp_path):
    env = _fault_env(tmp_path)
    sent = []
    r1 = HN.run(env, KEY, EVE, send=sent.append)
    assert r1["paged"] == ["DAY_RECORD_MISSING"] and len(sent) == 1 and "DAY_RECORD_MISSING" in sent[0] and "Nothing was auto-repaired" in sent[0]
    r2 = HN.run(env, KEY, EVE, send=sent.append)
    assert r2["paged"] == [] and len(sent) == 1, "the same fault is not re-paged on a re-run"


def test_a_NEW_fault_on_a_re_run_is_paged_without_repeating_the_old_one(tmp_path, monkeypatch):
    env = _fault_env(tmp_path)
    sent = []
    HN.run(env, KEY, EVE, send=sent.append)
    assert len(sent) == 1
    monkeypatch.setattr(L, "detector_sha", lambda: "0" * 16)           # a second, different fault appears on the same session
    r = HN.run(env, KEY, EVE, send=sent.append)
    assert r["paged"] == ["DETECTOR_SHA"] and len(sent) == 2 and "DETECTOR_SHA" in sent[1] and "DAY_RECORD_MISSING" not in sent[1]


def test_warnings_and_infos_never_page(tmp_path):
    env = mk(tmp_path, decisions={SLOTS[3]}, ticks=[{"ts": SLOTS[3] + 250, "status": "LATE_TICK", "late_s": 250}])
    sent = []
    r = HN.run(env, KEY, EVE, send=sent.append)
    assert r["report"]["verdict"] == "OK" and sent == [] and r["paged"] == []
    with open(env.log, "a") as f:
        f.write("{bad\n")
    r = HN.run(env, KEY, EVE, send=sent.append)
    assert r["report"]["verdict"] == "WARN" and sent == []


def test_quiet_never_pages(tmp_path):
    sent = []
    r = HN.run(_fault_env(tmp_path), KEY, EVE, quiet=True, send=sent.append)
    assert r["report"]["verdict"] == "FAULT" and sent == [] and r["paged"] == []


def test_a_failed_page_does_not_fail_the_review_and_is_retried_next_run(tmp_path):
    env = _fault_env(tmp_path)

    def boom(_m):
        raise RuntimeError("telegram down")
    r = HN.run(env, KEY, EVE, send=boom)
    assert r["report"]["verdict"] == "FAULT" and r["paged"] == [] and os.path.exists(f"{env.out}/{KEY}.json")
    sent = []
    r2 = HN.run(env, KEY, EVE, send=sent.append)
    assert r2["paged"] == ["DAY_RECORD_MISSING"] and len(sent) == 1


def test_the_real_notifier_is_reached_with_critical_true(tmp_path, monkeypatch):
    """the default `send` must be notify(msg, critical=True) — NOT the quiet-hours-suppressed path (20:50Z is inside quiet hours)"""
    import gazbot7.notify as N
    got = []
    monkeypatch.setattr(N, "notify", lambda m, **k: got.append((m, k)))
    HN.run(_fault_env(tmp_path), KEY, EVE)
    assert len(got) == 1 and got[0][1].get("critical") is True


# ── 11. outputs ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_default_day_is_the_latest_session_whose_window_has_ended():
    assert HN.default_day(dt.datetime(2026, 10, 15, 20, 50, tzinfo=UTC)) == "2026-10-15"
    assert HN.default_day(dt.datetime(2026, 10, 16, 6, 0, tzinfo=UTC)) == "2026-10-15"
    assert HN.default_day(dt.datetime(2026, 10, 14, 20, 50, tzinfo=UTC)) == "2026-10-14"


def test_latest_json_is_only_written_for_the_default_day(tmp_path):
    env = mk(tmp_path)
    HN.run(env, KEY, dt.datetime(2026, 10, 16, 21, 0, tzinfo=UTC), quiet=True)       # a back-dated manual run of 10-15 on the evening of 10-16
    assert not os.path.exists(f"{env.out}/latest.json")
    HN.run(env, KEY, EVE, quiet=True)
    v = json.load(open(f"{env.out}/latest.json"))
    assert v["key"] == KEY and v["verdict"] == "OK" and v["expected"] == len(SLOTS) and v["decided"] == len(SLOTS) and v["faults"] == []


def test_a_rerun_is_idempotent(tmp_path):
    env = press_world(tmp_path)
    a = HN.run(env, KEY, EVE, quiet=True)["report"]
    b = HN.run(env, KEY, EVE, quiet=True)["report"]
    assert a == b
    assert sorted(os.listdir(env.out)) == sorted({"2026-10-15.json", "2026-10-15.txt", "week_2026-W42.json", "week_2026-W42.txt", "LATEST_WEEK.txt", "latest.json"})


def test_the_text_report_says_what_it_found(tmp_path):
    txt = HN.render_day(HN.review_day(press_world(tmp_path, qty_row=4), KEY, EVE))
    assert "NIGHTLY REVIEW 2026-10-15" in txt and "VERDICT: OK" in txt and "MANUAL_CLAIM" in txt


def test_main_exit_codes_and_a_crash_is_loud(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hybrid_nightly.py", "--day", KEY])
    rep = lambda v: {"report": {"verdict": v, "health": [], "key": KEY, "arm": "v1.02", "version": "1.02", "generated_at": "x", "calls": {"n": 0, "errors": 0, "actions": {}},
                                "funnel": {}, "totals": {}, "coverage": {}, "presses": [], "candidates": [], "detector": {}, "notes": []}, "week": {}, "paged": []}   # noqa: E731
    monkeypatch.setattr(HN, "render_day", lambda r: "TXT")
    monkeypatch.setattr(HN, "run", lambda *a, **k: rep("OK"))
    assert HN.main() == 0
    monkeypatch.setattr(HN, "run", lambda *a, **k: rep("FAULT"))
    assert HN.main() == 3
    monkeypatch.setattr(HN, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert HN.main() == 2 and "CRASHED" in capsys.readouterr().out


def test_path_stats_first_passage_and_grid():
    tape = HN.Tape([(100 + 5 * i, h, l, c) for i, (h, l, c) in enumerate([(100.5, 99.5, 100.0), (105.0, 99.0, 104.0), (112.5, 103.0, 112.0), (130.0, 111.0, 125.0)])])
    ps = HN.path_stats(tape, +1, 100.0, 100, 130, grid=(12.5, 25.0, 50.0))
    assert ps["cross"]["12.5"] == 110 and ps["cross"]["25.0"] == 115 and "50.0" not in ps["cross"]
    assert ps["mfe_pt"] == 30.0 and ps["mae_pt"] == 1.0 and ps["last_px"] == 125.0
    assert ps["grid_usd"]["12.5"] == 4 * (12.5 * 2 - 1.5) and ps["grid_usd"]["50.0"] == 4 * (25.0 * 2 - 1.5)
    s = HN.path_stats(tape, -1, 100.0, 100, 130, grid=(12.5,))
    assert "12.5" not in s["cross"] and s["mae_pt"] == 30.0 and s["grid_usd"]["12.5"] == 4 * (-25.0 * 2 - 1.5)
    assert HN.path_stats(tape, +1, 100.0, 500, 600)["n_bars"] == 0


def test_expected_slots_respect_the_clock_and_the_self_gate():
    now = int(dt.datetime(2026, 10, 15, 4, 0, tzinfo=UTC).timestamp())
    sl = HN.expected_slots(KEY, now)
    assert sl[0] == T(2) and sl[-1] == T(3, 55) and all(o + 120 <= now for o in sl)
    assert HN.expected_slots("2026-10-31", int(dt.datetime(2026, 11, 2, tzinfo=UTC).timestamp())) == []           # weekend (and past the gate)
    assert HN.expected_slots("2026-11-02", int(dt.datetime(2026, 11, 3, tzinfo=UTC).timestamp())) == []           # after STOP_AFTER
    assert HN.expected_slots("2026-10-13", int(dt.datetime(2026, 10, 14, tzinfo=UTC).timestamp())) == []         # before START_AFTER


def test_after_the_clocks_change_the_05_paris_veto_moves_to_04Z_and_the_review_follows_it(tmp_path):
    """2026-10-25 is the CEST->CET change: on Monday 10-26 05:00 Paris is 04:00Z, so a press at 03:30Z (legal last week) is now a breach"""
    key, d0 = "2026-10-26", int(dt.datetime(2026, 10, 26, tzinfo=UTC).timestamp())
    now = dt.datetime(2026, 10, 26, 20, 50, 30, tzinfo=UTC)

    def world(sub, hh, mm):
        sub.mkdir()
        op = d0 + hh * 3600 + mm * 60
        fill = op + 25
        rows = [{"side": "SHORT", "qty": 1, "entry": 20000.0, "exit": 19962.5, "opened": iso(fill), "closed": iso(fill + 213), "pnl": 73.5, "reason": "TARGET_1"}] * 4
        ex = {"decision_ts_slot": op, "action": "ENTER_SHORT", "candidate": "SHORT", "detector_dir": -1, "veto_cutoff": iso(d0 + 4 * 3600),
              "entry_action": "PRESS_SELL", "request": f"{iso(op + 20)}|SELL|4|75,75,75,75"}
        return mk(sub, px=fall_from(fill + 20), ledger=rows, extra_log=[ex], key=key)
    assert "PRESS_RULE_BREACH" in codes(HN.review_day(world(tmp_path / "a", 3, 30), key, now), "FAULT")
    assert "PRESS_RULE_BREACH" not in codes(HN.review_day(world(tmp_path / "b", 4, 0), key, now))


# ── 11. independent-audit regressions (E92 audit, 2026-10-14) ───────────────────────────────────────────────────────────────
def test_NOT_FLAT_does_not_fire_on_the_rider_state_a_manual_claim_leaves_behind(tmp_path):
    """★ the live state after the 10-14 16:44Z MANUAL_CLAIM: closed=True, lots_open STILL 4, venue flat. Paging on lots_open alone was a false critical page."""
    env = mk(tmp_path, rider={"lots_open": 4, "venue_net": 0, "entered": True, "closed": True})
    assert "NOT_FLAT" not in codes(HN.review_day(env, KEY, EVE))


def test_NOT_FLAT_fires_on_an_unclosed_claim_or_on_a_nonzero_venue_net_alone(tmp_path):
    a = mk(tmp_path / "a", rider={"lots_open": 0, "venue_net": 0, "entered": True, "closed": False}) if (tmp_path / "a").mkdir() is None else None
    b = mk(tmp_path / "b", rider={"lots_open": 0, "venue_net": -2, "entered": False, "closed": True}) if (tmp_path / "b").mkdir() is None else None
    assert "NOT_FLAT" in codes(HN.review_day(a, KEY, EVE), "FAULT")
    assert "NOT_FLAT" in codes(HN.review_day(b, KEY, EVE), "FAULT")


def test_a_page_that_did_not_go_out_is_not_recorded_and_is_retried(tmp_path):
    env = _fault_env(tmp_path)
    r1 = HN.run(env, KEY, EVE, send=lambda m: False)                     # notify() returns False when suppressed/failed, it does not raise
    assert r1["paged"] == [] and not os.path.exists(f"{env.out}/paged.json")
    sent = []
    r2 = HN.run(env, KEY, EVE, send=lambda m: sent.append(m) or True)
    assert r2["paged"] == ["DAY_RECORD_MISSING"] and len(sent) == 1
    r3 = HN.run(env, KEY, EVE, send=lambda m: sent.append(m) or True)
    assert r3["paged"] == [] and len(sent) == 1


def test_a_send_that_returns_none_counts_as_sent(tmp_path):
    env = _fault_env(tmp_path)
    assert HN.run(env, KEY, EVE, send=lambda m: None)["paged"] == ["DAY_RECORD_MISSING"]


def test_a_tape_dead_all_day_is_a_LOST_SLOTS_FAULT_even_though_every_slot_has_an_excuse(tmp_path):
    """★ the audit finding: a dead robot was only a WARN because each missing slot was 'explained'"""
    ticks = [{"ts": o + 20, "status": "FEED_STALE"} for o in SLOTS]
    rep = HN.review_day(mk(tmp_path, decisions="none", ticks=ticks), KEY, EVE)
    assert rep["coverage"]["unexplained"] == 0 and rep["coverage"]["feed_explained"] == len(SLOTS)
    assert "LOST_SLOTS" in codes(rep, "FAULT") and rep["verdict"] == "FAULT"


def test_a_robot_that_crashed_every_slot_is_a_LOST_SLOTS_FAULT(tmp_path):
    crashes = [{"event": "ERROR", "at": iso(o + 20), "error": "boom"} for o in SLOTS]
    rep = HN.review_day(mk(tmp_path, decisions="none", extra_log=crashes, ticks=[{"ts": o + 20, "status": "ERROR"} for o in SLOTS]), KEY, EVE)
    assert rep["coverage"]["crash_logged"] == len(SLOTS) and rep["coverage"]["unexplained"] == 0
    assert "LOST_SLOTS" in codes(rep, "FAULT")


def test_a_few_late_ticks_and_a_switch_that_is_off_are_not_LOST_SLOTS(tmp_path):
    gone = {SLOTS[i] for i in (10, 20, 30)}
    ticks = [{"ts": o + 200, "status": "LATE_TICK", "late_s": 200} for o in gone]
    assert "LOST_SLOTS" not in codes(HN.review_day(mk(tmp_path / "a", decisions=gone, ticks=ticks), KEY, EVE)) if (tmp_path / "a").mkdir() is None else 0
    off = mk(tmp_path / "b", decisions="none", switch="off", ticks=[{"ts": o + 20, "status": "FEED_STALE"} for o in SLOTS]) if (tmp_path / "b").mkdir() is None else None
    assert "LOST_SLOTS" not in codes(HN.review_day(off, KEY, EVE))


def test_poisoned_coverage_and_lost_days_are_not_days_in_the_arm_numbers():
    def day(k, net, health=()):
        return {"key": k, "totals": {"ledger_net_usd": net, "filled": 1, "winners": 1 if net > 0 else 0, "manual_exit_entries": 0}, "health": list(health),
                "presses": [{"filled": True, "provisional": False, "grid_usd": {"37.5": net}}], "candidates": []}
    days = [day("2026-10-15", 300.0), day("2026-10-16", -5000.0, [{"code": "POISONED_RECORD"}]), day("2026-10-19", -4000.0, [{"code": "LOST_SLOTS"}]),
            day("2026-10-20", -3000.0, [{"code": "COVERAGE"}]), day("2026-10-21", 100.0, [{"code": "RUNG_LAG"}])]
    s = HN.arm_stats(days)
    assert s["days"] == 2 and s["net_usd"] == 400.0 and s["worst_day"] == 100.0
    assert HN.pooled_cf(days)["real_entries"] == 2


def test_the_real_main_returns_3_on_a_fault_and_the_unit_treats_3_as_success_and_1_2_as_failure():
    unit = (pathlib.Path(__file__).resolve().parents[1] / "ops/systemd/gazbot7-hybrid-nightly.service").read_text()
    assert "SuccessExitStatus=0 3" in unit


def test_slots_after_the_day_lock_are_explained_not_lost(tmp_path):
    """v1.02+LOCK: after the lock the robot makes no call by design — that must not read as a dead robot (COVERAGE / LOST_SLOTS)."""
    gone = set(SLOTS[40:])
    lock = {"event": "DAY_LOCK", "at": iso(SLOTS[40] + 20), "limit": 1000.0, "touched_at": iso(SLOTS[40] - 60), "equity_now": 1100.0,
            "peak": 1150.0, "decision_ts": iso(SLOTS[40])}
    ticks = [{"ts": o + 20, "status": "DAY_LOCKED" if o in gone else "OK"} for o in SLOTS]
    rep = HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks, extra_log=[lock]), KEY, EVE)
    assert rep["coverage"]["locked"] == len(gone) and rep["coverage"]["unexplained"] == 0
    assert rep["verdict"] == "OK", rep["health"]
    assert "DAY_LOCK" in codes(rep, "INFO")


def test_the_lock_is_also_recognised_from_the_log_when_the_journal_is_unreadable(tmp_path):
    gone = set(SLOTS[40:])
    lock = {"event": "DAY_LOCK", "at": iso(SLOTS[40] + 20), "limit": 1000.0, "touched_at": iso(SLOTS[40] - 60), "equity_now": 1100.0,
            "peak": 1150.0, "decision_ts": iso(SLOTS[40])}
    rep = HN.review_day(mk(tmp_path, decisions=gone, ticks=None, extra_log=[lock]), KEY, EVE)
    assert rep["coverage"]["unexplained"] == 0 and rep["verdict"] == "OK", rep["health"]


def test_missing_slots_with_no_lock_are_still_a_fault_when_a_lock_is_absent(tmp_path):
    gone = set(SLOTS[40:])
    ticks = [{"ts": o + 20, "status": "OK"} for o in SLOTS]
    rep = HN.review_day(mk(tmp_path, decisions=gone, ticks=ticks), KEY, EVE)
    assert "COVERAGE" in codes(rep, "FAULT")


def test_a_lock_check_error_is_a_warn(tmp_path):
    err = {"event": "LOCK_CHECK_ERROR", "at": iso(SLOTS[10] + 20), "error": "RuntimeError('db')"}
    rep = HN.review_day(mk(tmp_path, extra_log=[err]), KEY, EVE)
    assert "LOCK_CHECK_ERROR" in codes(rep, "WARN")


# ── the weekly discipline table: real ledger + 5s tape, never the future ────────────────────────────────────────────────
def _disc_world():
    d0 = HN.d0_of(KEY)

    def px(t):
        h = (t - d0) / 3600.0
        if h < 10.5:
            return 20000.0 + (min(h, 10.0) - 10.0) * 0 + max(0.0, (h - 10.0)) * 75.0     # +37.5 by 10:30Z
        if h < 14.0:
            return 20037.5 - (h - 10.5) * (77.5 / 3.5)                                      # falls to 19960 at 14:00
        return 19960.0 + min(h - 14.0, 6.0) * (80.0 / 6.0)
    rows = [(t, px(t) + 0.25, px(t) - 0.25, px(t)) for t in range(d0, d0 + 22 * 3600, 5)]
    tape = HN.Tape(rows)
    opened = iso(d0 + 10 * 3600)
    lot = lambda i, closed, pnl: {"id": i, "side": "LONG", "qty": 1.0, "entry_price": 20000.0, "opened_at": opened, "closed_at": closed, "pnl_usd": pnl, "data_quality": None}  # noqa: E731
    lots = [lot(1, iso(d0 + 10.5 * 3600), 73.5), lot(2, iso(d0 + 20 * 3600 + 40 * 60), -50.0), lot(3, iso(d0 + 20 * 3600 + 40 * 60), -50.0), lot(4, iso(d0 + 20 * 3600 + 40 * 60), -50.0)]
    return d0, tape, [{"opened_at": opened, "lots": lots}]


def test_discipline_row_marks_the_open_position_at_1330_from_real_lots_and_the_tape():
    d0, tape, groups = _disc_world()
    r = HN.discipline_row(groups, tape, KEY, d0 + 23 * 3600, True, -76.5)
    p = r["pos"]
    assert r["trades"] == 1 and r["day_total_usd"] == -76.5 and p["lots_open"] == 3 and p["side"] == "LONG"
    # 13:30Z price = 20037.5 - 3.0*(77.5/3.5) = 19971.1: one lot banked (+73.5), three marked as if flattened now
    px13 = 20037.5 - 3.0 * (77.5 / 3.5)
    want = 73.5 + 3 * (((px13 - 20000.0) - HN.HALF_SPREAD_PT) * 2 - 1.5)
    assert abs(p["pnl_1330"] - want) < 1.0 and abs(r["total_1330_usd"] - p["pnl_1330"]) < 0.01
    assert p["pnl_close"] == -76.5 and p["pnl_1330"] < 0 < 73.5
    assert p["low_after_1330"] <= p["pnl_1330"] and p["low_after_1330"] <= p["pnl_1800"]
    assert r["day_low_usd"] <= p["low_after_1330"] and r["day_low_usd"] < 0


def test_discipline_row_never_uses_the_future_for_a_provisional_day():
    d0, tape, groups = _disc_world()
    r = HN.discipline_row(groups, tape, KEY, d0 + 15 * 3600, False, 73.5)      # reviewed at 15:00Z
    p = r["pos"]
    assert p["pnl_1330"] is not None and p["pnl_1800"] is None and p["pnl_close"] is not None and r["complete"] is False
    assert p["low_ts"] is not None and HN.parse_ts(p["low_ts"]).timestamp() <= d0 + 15 * 3600


def test_discipline_row_for_a_flat_book_at_1330_has_no_position():
    d0, tape, groups = _disc_world()
    for x in groups[0]["lots"]:
        x["closed_at"] = iso(d0 + 10.5 * 3600)
    r = HN.discipline_row(groups, tape, KEY, d0 + 23 * 3600, True, 0.0)
    assert r["pos"] is None and r["total_1330_usd"] is not None


def test_weekly_pack_ranks_the_discipline_table_best_to_worst_per_arm():
    rows = [("2026-10-12", {"trades": 2, "day_total_usd": -300.0, "total_1330_usd": -300.0, "pos": None, "day_low_usd": -400.0, "complete": True}),
            ("2026-10-13", {"trades": 3, "day_total_usd": 600.0, "total_1330_usd": 250.0, "day_low_usd": -900.0, "complete": True,
                            "pos": {"side": "SHORT", "entered_at": "2026-10-13T11:00:00+00:00", "entry": 20000.0, "lots_open": 3, "pnl_1330": -400.0,
                                    "pnl_1800": -800.0, "pnl_close": 350.0, "low_after_1330": -1200.0}})]
    txt = "\n".join(HN.render_discipline(rows))
    assert txt.index("2026-10-13") < txt.index("2026-10-12")
    assert "-1200" in txt and "SHORT" in txt and "11:00Z" in txt
