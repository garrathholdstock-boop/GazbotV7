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


def test_claude_binary_is_an_absolute_path_that_exists():
    """2026-10-05: a bare "claude" made 138 of 138 calls fail under systemd, whose PATH is
    /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/snap/bin — the CLI is in
    /root/.local/bin. An interactive hand-test passed because the shell resolved it, which
    is [[the-labs-tape-is-not-productions-tape]] in its purest form. tape_reader.py has
    hardcoded the absolute path since 2026-09-12.
    """
    import os
    import sim_week_recursive as S
    assert os.path.isabs(S.CLAUDE), f"not absolute: {S.CLAUDE!r} — systemd cannot resolve it"
    assert os.access(S.CLAUDE, os.X_OK), f"not executable: {S.CLAUDE}"


def test_preflight_catches_a_missing_binary_and_decides_nothing(monkeypatch):
    import datetime as dt
    import shadow_runner as R
    monkeypatch.setattr(R.S, "CLAUDE", "/nonexistent/claude")
    called, paged = [], []
    monkeypatch.setattr(R.S, "ask", lambda *a, **k: called.append(1) or {"action": "WAIT"})
    monkeypatch.setattr(R, "_page", lambda m: paged.append(m))
    out = R.tick(now=dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC), dry=True)
    assert "PREFLIGHT FAILED" in out["skip"]
    assert not called, "decided anyway with no model behind it"
    assert paged, "failed silently — the whole point of the 2026-10-05 lesson"


def test_repeated_identical_failure_pages_once_not_every_tick(monkeypatch, tmp_path):
    """138 failures must produce ONE page, not 138 and not zero."""
    import datetime as dt
    import shadow_runner as R
    monkeypatch.setattr(R, "STATE", str(tmp_path / "st.json"))
    monkeypatch.setattr(R, "LOG", str(tmp_path / "l.jsonl"))
    monkeypatch.setattr(R.S, "ask", lambda *a, **k: {"action": "WAIT", "error": "boom"})
    monkeypatch.setattr(R, "live_bars",
                        lambda k, n: [(n - 60 * i, 1.0, 1.0, 1.0) for i in range(40)][::-1])
    paged = []
    monkeypatch.setattr(R, "_page", lambda m: paged.append(m))
    base = dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.UTC)
    for i in range(12):
        R.tick(now=base + dt.timedelta(minutes=5 * i))
    assert len(paged) == 1, f"paged {len(paged)} times for one fault"
    assert "3 in a row" in paged[0]


def test_position_matches_the_sims_own_structure(tmp_path, monkeypatch):
    """⚠ The runner's position dict must be the SIM's structure, not an invented one.

    The first cut stored {"side": ±1, "entry", "opened": <int epoch>} and was wrong three
    ways: S.context() reads pos["dir"] (KeyError on the next tick after any entry),
    S._close() reads pos["dir"] and pos["peak"], and it calls pos["opened"].isoformat() so
    `opened` must be a datetime. It never fired because the runner had never held a
    position — it would have crashed on the first live entry.
    """
    import datetime as dt
    import shadow_runner as R
    monkeypatch.setattr(R, "STATE", str(tmp_path / "st.json"))
    st = {"key": "2026-10-02", "pos": None, "done": [], "calls": 0, "errors": 0,
          "closed_out": False}
    st = R.apply_action(st, "ENTER_LONG", 31000.0, 1759_392_000, {"reason": "x"})
    p = st["pos"]
    assert set(("dir", "entry", "peak", "opened", "reason")) <= set(p), f"missing keys: {p}"
    assert p["dir"] == 1
    assert isinstance(p["opened"], dt.datetime), "opened must be a datetime for _close()"
    # the sim's own closer must accept it
    t = R.S._close(p, 31050.0, 1759_395_600, "TEST")
    assert t["side"] == "LONG" and t["pnl_usd"] > 0


def test_position_survives_the_json_round_trip(tmp_path, monkeypatch):
    """The runner is ONESHOT: every tick reloads state from disk, so a datetime that cannot
    round-trip through JSON breaks the next tick rather than this one."""
    import datetime as dt
    import shadow_runner as R
    monkeypatch.setattr(R, "STATE", str(tmp_path / "st.json"))
    opened = dt.datetime(2026, 10, 2, 8, 0, tzinfo=dt.UTC)
    R.save_state({"key": "2026-10-02", "pos": {"dir": -1, "entry": 1.0, "peak": 0.0,
                                               "opened": opened, "reason": "r"},
                  "done": [], "calls": 0, "errors": 0, "closed_out": False})
    back = R.load_state("2026-10-02")
    assert isinstance(back["pos"]["opened"], dt.datetime)
    assert back["pos"]["opened"] == opened


def test_peak_advances_while_holding(tmp_path, monkeypatch):
    """peak_pt feeds every giveback figure in the post-mortem; if it never advances the
    nightly review reads 'gave back 0pt' on every trade."""
    import shadow_runner as R
    monkeypatch.setattr(R, "STATE", str(tmp_path / "st.json"))
    st = {"key": "d", "pos": None, "done": [], "calls": 0, "errors": 0, "closed_out": False}
    st = R.apply_action(st, "ENTER_LONG", 100.0, 0, {})
    st = R.apply_action(st, "HOLD", 140.0, 60, {})
    assert st["pos"]["peak"] > 30, f"peak did not advance: {st['pos']['peak']}"
    st = R.apply_action(st, "HOLD", 110.0, 120, {})
    assert st["pos"]["peak"] > 30, "peak must RATCHET, not track price"


def test_shadow_runner_trades_the_champion_not_the_latest():
    """2026-10-06: it was frozen on rules_iter2.txt — the set iteration 3 is losing with —
    because the loop overwrites rules.txt with the MOST RECENT iteration's output, which is
    not the best one. The champion is iteration 1's set ($620/day via iteration 2)."""
    import hashlib
    import pathlib
    import shadow_runner as R
    import json
    assert R.RULES.endswith("CHAMPION.txt"), R.RULES
    live = hashlib.sha256(pathlib.Path(R.RULES).read_bytes()).hexdigest()[:12]
    meta = json.loads(pathlib.Path(
        "/home/alphabot/gazbot7/reports/recursive_loop/CHAMPION.json").read_text())
    named = hashlib.sha256(pathlib.Path(
        f"/home/alphabot/gazbot7/reports/recursive_loop/{meta['file']}").read_bytes()
        ).hexdigest()[:12]
    assert live == named, (f"CHAMPION.txt ({live}) is not {meta['file']} ({named}) — "
                           f"the paper desk is trading something other than the champion")


def _drive(monkeypatch, tmp_path, actions, times):
    """Run REAL tick() calls with a scripted model, reloading state from disk each time."""
    import datetime as dt
    import shadow_runner as R
    monkeypatch.setattr(R, "STATE", str(tmp_path / "st.json"))
    monkeypatch.setattr(R, "LOG", str(tmp_path / "l.jsonl"))
    monkeypatch.setattr(R, "DAYLOG", str(tmp_path / "days"))
    monkeypatch.setattr(R, "preflight", lambda: None)
    script = iter(actions)
    monkeypatch.setattr(R.S, "ask", lambda *a, **k: {"action": next(script), "reason": "t"})
    monkeypatch.setattr(
        R, "live_bars",
        lambda k, n: [(n - 60 * i, 100.0 + (40 - i), 100.0 + (40 - i), 100.0 + (40 - i))
                      for i in range(40)][::-1])
    return R, [R.tick(now=dt.datetime(2026, 10, 7, h, m, tzinfo=dt.UTC)) for h, m in times]


def test_entry_then_hold_then_exit_through_real_ticks(monkeypatch, tmp_path):
    """⚠ The 2026-10-07 02:05 crash: tick() built the log line from pos["side"] after apply_action
    had switched the dict to the sim's pos["dir"], so the FIRST live entry raised KeyError before
    the state was saved. The next tick re-asked, re-entered and crashed again — the runner could
    never hold a position. Every earlier test called apply_action() alone, never tick()."""
    R, outs = _drive(monkeypatch, tmp_path, ["ENTER_LONG", "HOLD", "EXIT"],
                     [(2, 5), (2, 10), (2, 15)])
    assert outs[0]["position"] == {"side": 1, "entry": outs[0]["position"]["entry"]}
    assert outs[1]["position"] is not None, "position was lost between ticks"
    assert outs[2]["position"] is None and outs[2]["trades_today"] == 1


def test_open_position_is_closed_at_window_end_through_real_ticks(monkeypatch, tmp_path):
    R, outs = _drive(monkeypatch, tmp_path, ["ENTER_SHORT", "HOLD"], [(13, 20), (13, 25)])
    assert outs[1]["position"] is not None
    import datetime as dt
    out = R.tick(now=dt.datetime(2026, 10, 7, 13, 35, tzinfo=dt.UTC))
    assert out.get("day_written") is not None, f"window end did not close the book: {out}"
    assert R.load_state("2026-10-07")["pos"] is None
