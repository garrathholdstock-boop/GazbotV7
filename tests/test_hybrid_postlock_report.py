"""E108 nightly post-lock report: pure functions, injected clock, tmp dirs. Reads no live state, sends nothing, touches no desk file."""
from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import sys

GB = pathlib.Path("/home/alphabot/gazbot7")
SRC = GB / "scripts" / "hybrid_postlock_report.py"
sys.path.insert(0, str(GB / "scripts"))
import hybrid_postlock_report as R  # noqa: E402

UTC = dt.timezone.utc


def nightly(*presses):
    return {"presses": [{"decision_ts": f"2026-10-22T{t}:00+00:00", "filled": True, "side": "SELL", "ledger_net_usd": usd} for t, usd in presses]}


def shadow(lock=(), pm=(), partial=False):
    def arm(es, status):
        return {"status": status if es else "NO_DATA", "entries": [{"decision_ts": f"2026-10-22T{t}:00+00:00", "side": "BUY", "hit": h, "net_usd": u, "mae_pt": 5} for t, h, u in es],
                "slots_made": 10, "slots_expected": 12, "poisoned": False, "calls": 10, "errors": 0}
    return {"partial_tape": partial, "arms": {"LOCK": arm(lock, "ACTIVE"), "PM": arm(pm, "ACTIVE")}}


LOCK = [{"decision_ts": "2026-10-22T05:25:00+00:00", "touched_at": "x", "peak": 1, "equity_now": 1}]


def test_live_split_and_leak():
    r = R.build_day("2026-10-22", nightly(("03:00", 262.0), ("04:40", 329.0), ("06:25", 284.0), ("10:40", 254.0)), shadow(), LOCK, "g")
    assert r["live"]["to_cut"]["entries"] == 2 and r["live"]["to_cut"]["usd"] == 591.0
    assert r["live"]["as_ran"]["usd"] == 1129.0
    assert any(f.startswith("LOCK_LEAK x2") for f in r["flags"])


def test_no_lock_uses_whole_live_window_and_no_leak():
    r = R.build_day("2026-10-23", nightly(("03:00", 100.0), ("12:00", 50.0)), shadow(pm=[("17:40", True, 294.0)]), [], "g")
    assert r["live"]["to_cut"]["entries"] == 2 and not r["live"]["after_lock_live_presses"]
    assert r["combined"]["usd"] == 444.0 and r["combined"]["entries"] == 3 and r["flags"] == []


def test_relatch_and_missing_lock_arm_and_arms_not_pooled():
    locks = LOCK + [{"decision_ts": "2026-10-22T06:30:00+00:00"}]
    r = R.build_day("2026-10-22", nightly(("03:00", 10.0)), shadow(pm=[("15:00", False, -300.0)]), locks, "g")
    assert "LOCK_RELATCH x2" in r["flags"] and "SHADOW_MISSING_LOCK_ARM" in r["flags"]
    assert r["arms"]["PM"]["misses"] == 1 and r["arms"]["LOCK"]["n"] == 0


def test_missing_records_are_flagged_not_zeroed_silently():
    r = R.build_day("2026-10-22", None, None, [], "g")
    assert "NIGHTLY_MISSING" in r["flags"] and "SHADOW_RECORD_MISSING" in r["flags"]
    assert "sim arms unavailable" in R.render_day(dict(r, locks=LOCK))


def test_weekend_is_no_session():
    r = R.build_day("2026-10-24", None, None, [], "g")
    assert r["flags"] == ["NO_SESSION"]


def test_tag_thresholds():
    assert [R.tag(n) for n in (0, 9, 10, 29, 30)] == ["NO DATA", "UNDERPOWERED (n<10)", "n<30: NO FITTING, NO DECISION", "n<30: NO FITTING, NO DECISION", "n>=30"]


def test_default_day_uses_injected_clock():
    assert R.default_day(dt.datetime(2026, 10, 23, 21, 0, tzinfo=UTC)) == "2026-10-23"
    assert R.default_day(dt.datetime(2026, 10, 24, 6, 10, tzinfo=UTC)) == "2026-10-23"
    assert R.prev_weekday(dt.date(2026, 10, 26)) == dt.date(2026, 10, 23)


def test_atomic_write_cannot_escape(tmp_path):
    try:
        R.atomic_write("../x.txt", "no", str(tmp_path))
    except ValueError:
        return
    raise AssertionError("escaped")


def test_morning_critical_when_report_missing_and_quiet_when_ok(tmp_path):
    sent = []
    send = lambda m, critical=False: sent.append((m, critical)) or True  # noqa: E731
    now = dt.datetime(2026, 10, 23, 4, 10, tzinfo=UTC)         # Friday morning -> expects Thursday
    assert R.morning(now, str(tmp_path), send) == 1 and sent[-1][1] is True
    r = R.build_day("2026-10-22", nightly(("03:00", 100.0)), shadow(), [], "g")
    (tmp_path / "latest.json").write_text(json.dumps(r))
    assert R.morning(now, str(tmp_path), send) == 0 and sent[-1][1] is False and "2026-10-22" in sent[-1][0]
    assert R.morning(dt.datetime(2026, 10, 25, 4, 10, tzinfo=UTC), str(tmp_path), send) == 0     # Sunday: silent
    assert len(sent) == 2


def test_saturday_message_carries_week_line():
    r = R.build_day("2026-10-23", nightly(("03:00", 100.0)), shadow(), [], "g")
    txt = R.morning_text(r, dt.date(2026, 10, 24), "WEEK | x\ndays 5; y\n")
    assert "WEEK:" in txt and "losers study" in txt


def test_authority_ast():
    tree = ast.parse(SRC.read_text())
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[0] for a in n.names}
        if isinstance(n, ast.ImportFrom):
            imported.add((n.module or "").split(".")[0] + ("." + n.module.split(".", 1)[1] if n.module and "." in n.module else ""))
    banned = {"subprocess", "sqlite3", "ib_insync", "ibapi", "socket", "requests", "urllib", "http"}
    assert not (imported & banned), imported
    assert imported <= {"__future__", "argparse", "datetime", "json", "os", "re", "sys", "gazbot7.notify"}, imported
    strs = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) < 200]
    for forbidden in ("day_rider_buy", "day_rider_claim", "gate_switches", "desk_kill", "hybrid_robot.env", "leg_robot.env"):
        assert not any(forbidden in s for s in strs if "/" in s or s.endswith((".txt", ".env", ".json"))), forbidden
    writes = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open" and len(n.args) > 1
              and isinstance(n.args[1], ast.Constant) and "w" in str(n.args[1].value)]
    assert len(writes) == 1, "only atomic_write may open for writing"
    fn = [f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == "atomic_write"][0]
    assert writes[0] in list(ast.walk(fn))


def test_never_reads_wall_clock_outside_main():
    tree = ast.parse(SRC.read_text())
    for f in ast.walk(tree):
        if isinstance(f, ast.FunctionDef) and f.name != "main":
            for n in ast.walk(f):
                assert not (isinstance(n, ast.Attribute) and n.attr in ("now", "utcnow", "today")), (f.name, n.attr)
