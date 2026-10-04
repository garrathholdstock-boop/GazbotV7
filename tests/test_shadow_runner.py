"""THE SHADOW RUNNER MUST NOT BE ABLE TO TRADE — asserted against the SOURCE.

The same shape as `tests/test_tape_reader.py` and `tests/test_request_watch.py`: a
read-only instrument earns that label from a test, not from a docstring.
[[a-written-rule-with-no-test-is-a-suggestion]] — and a source-TEXT grep is a lint, not a
test ([[a-source-text-test-is-a-lint-not-a-test]]), so the path assertions walk the AST
and the behaviour assertions call the real entry point.

⚠ The docstring deliberately NAMES `day_rider_buy.txt` and `gate_switches.env` to say it
never writes them, so a naive grep over the file would fail on its own documentation.
These tests look at executable string constants only.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import pathlib
import sys

import pytest

GB = pathlib.Path("/home/alphabot/gazbot7")
SRC = GB / "scripts" / "shadow_runner.py"
sys.path.insert(0, str(GB / "scripts"))
sys.path.insert(0, str(GB / "src"))


def _tree():
    return ast.parse(SRC.read_text())


def _docstrings(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(n, clean=False)
            if d:
                out.add(d)
    return out


def _code_strings(tree):
    """Every string constant that is NOT a docstring."""
    docs = _docstrings(tree)
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docs]


FORBIDDEN = ("day_rider_buy", "day_rider_claim", "gate_switches", "desk_kill",
             "placeOrder", "MarketOrder", "LimitOrder", "reqIds", "openOrder")


def test_no_order_path_in_executable_code():
    bad = [(s, f) for s in _code_strings(_tree()) for f in FORBIDDEN if f in s]
    assert not bad, f"order-path vocabulary in live code: {bad}"


def test_imports_no_broker():
    tree = _tree()
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
    forbidden = {m for m in mods if "ib_insync" in m or "ib_gateway" in m or "ibapi" in m}
    assert not forbidden, f"imports a broker: {forbidden}"


def test_writes_only_its_own_files():
    """Every open() in write/append mode must target one of the module's own paths."""
    import shadow_runner as R
    allowed = {R.STATE, R.STATE + ".tmp", R.LOG, R.DAYLOG}
    tree = _tree()
    writes = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "open"):
            continue
        mode = None
        if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
            mode = n.args[1].value
        for kw in n.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
        if mode and ("w" in mode or "a" in mode):
            writes.append(ast.unparse(n.args[0]))
    # every write target is built from STATE / LOG / DAYLOG, never a literal elsewhere
    for w in writes:
        assert any(t in w for t in ("STATE", "LOG", "DAYLOG", "tmp", "f\"{DAYLOG}")), \
            f"writes to something that is not its own file: {w}"


# ── behaviour, through the real entry point ─────────────────────────────────────────────

def test_session_key_opens_tomorrow_at_2200z():
    import shadow_runner as R
    assert R.session_key(dt.datetime(2026, 10, 5, 21, 59, tzinfo=dt.UTC)) == "2026-10-05"
    assert R.session_key(dt.datetime(2026, 10, 5, 22, 0, tzinfo=dt.UTC)) == "2026-10-06"


def test_new_session_never_inherits_a_position(tmp_path, monkeypatch):
    """The overnight rule. A stale session key once ate a whole day on the rider."""
    import shadow_runner as R
    p = tmp_path / "st.json"
    monkeypatch.setattr(R, "STATE", str(p))
    json.dump({"key": "2026-10-01", "pos": {"side": 1, "entry": 100.0, "opened": 0},
               "done": [{"pnl_usd": 50.0}], "calls": 9, "errors": 0,
               "closed_out": False}, open(p, "w"))
    st = R.load_state("2026-10-02")
    assert st["pos"] is None, "carried a position into a new session"
    assert st["done"] == [] and st["calls"] == 0


def test_weekend_declines_without_deciding(monkeypatch):
    import shadow_runner as R
    called = []
    monkeypatch.setattr(R.S, "ask", lambda *a, **k: called.append(1) or {"action": "WAIT"})
    out = R.tick(now=dt.datetime(2026, 10, 3, 9, 0, tzinfo=dt.UTC), dry=True)  # Saturday
    assert "weekend" in out["skip"] and not called


def test_before_window_declines_without_deciding(monkeypatch):
    import shadow_runner as R
    called = []
    monkeypatch.setattr(R.S, "ask", lambda *a, **k: called.append(1) or {"action": "WAIT"})
    out = R.tick(now=dt.datetime(2026, 10, 5, 1, 0, tzinfo=dt.UTC), dry=True)  # 01:00Z Mon
    assert "before the window" in out["skip"] and not called


def test_stale_tape_declines_rather_than_reading_a_dead_feed(monkeypatch):
    """A shut venue and a dead feed produce the same silence — the tape_reader rule."""
    import shadow_runner as R
    now = dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC)
    old = int(now.timestamp()) - 3600
    monkeypatch.setattr(R, "live_bars",
                        lambda k, n: [(old - 60 * i, 1.0, 1.0, 1.0) for i in range(40)][::-1])
    called = []
    monkeypatch.setattr(R.S, "ask", lambda *a, **k: called.append(1) or {"action": "WAIT"})
    out = R.tick(now=now, dry=True)
    assert "stale" in out["skip"] and not called


def test_a_dead_cli_is_recorded_not_silently_flat(tmp_path, monkeypatch):
    """The 2026-10-03 lesson: 138/138 errored calls booked $0.00 and read as a quiet day."""
    import shadow_runner as R
    monkeypatch.setattr(R, "STATE", str(tmp_path / "st.json"))
    monkeypatch.setattr(R, "LOG", str(tmp_path / "l.jsonl"))
    monkeypatch.setattr(R, "DAYLOG", str(tmp_path / "days"))
    st = {"key": "2026-10-05", "pos": None, "done": [], "calls": 138, "errors": 138,
          "closed_out": False}
    rec = R.write_day(st, [], "2026-10-05")
    assert rec["poisoned"] is True and rec["error_rate"] == 1.0
    assert rec["net_usd"] == 0.0, "a poisoned day still books 0 — the flag is what distinguishes it"


def test_rules_are_frozen_and_fingerprinted():
    """A forward test whose rules change nightly is not a forward test."""
    import shadow_runner as R
    assert R._sha(R.RULES) != "missing", "the frozen rule set is absent"
    src = SRC.read_text()
    assert "rules_sha" in src, "a day record must fingerprint the rules it traded"
