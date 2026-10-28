"""E127 overnight shadow: log only, never presses; window 22:00-02:00Z; votes on an ENTER with the MIL."""
import ast
import datetime as dt
import json
import pathlib
import sys

GB = pathlib.Path("/home/alphabot/gazbot7")
sys.path.insert(0, str(GB / "scripts")); sys.path.insert(0, str(GB / "src"))
import hybrid_overnight_shadow as O  # noqa: E402

UTC = dt.timezone.utc


def test_the_module_can_never_press_or_touch_desk_files():
    src = (GB / "scripts/hybrid_overnight_shadow.py").read_text()
    names = {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)} | {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    for bad in ("write_press", "BUY_FILE", "CLAIM_FILE", "STATE_FILE", "save_state", "write_claim", "exit_alert", "LOG_FILE"):
        assert bad not in names, bad


def test_window_is_22_to_02_utc():
    assert O.in_window(dt.datetime(2026, 10, 28, 22, 0, tzinfo=UTC)) and O.in_window(dt.datetime(2026, 10, 29, 1, 55, tzinfo=UTC))
    assert not O.in_window(dt.datetime(2026, 10, 29, 2, 0, tzinfo=UTC)) and not O.in_window(dt.datetime(2026, 10, 28, 21, 55, tzinfo=UTC))


def test_an_enter_with_the_mil_is_voted_and_logged(tmp_path, monkeypatch):
    env = tmp_path / "env"; env.write_text("hybrid_robot=on\nhybrid_overnight_shadow=on\n")
    monkeypatch.setattr(O.H, "SWITCH", str(env)); monkeypatch.setattr(O, "LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr(O.H, "PROMPT_DIR", str(tmp_path / "p"))
    bars = [(1793224800 - 60 * i, 100.0, 99.0, 99.5) for i in range(200, 0, -1)]
    monkeypatch.setattr(O, "page_bars", lambda now: bars)
    monkeypatch.setattr(O.L, "series_for", lambda d: bars)
    monkeypatch.setattr(O.L, "confirmed_turns", lambda b: [])
    monkeypatch.setattr(O.H, "det_dir", lambda turns, t: 1)
    monkeypatch.setattr(O.H, "desk_prompt", lambda *a, **k: ("PROMPT from " + k["entry_from"], {"version": "D6"}, None))
    monkeypatch.setattr(O.time, "time", lambda: 1793224800 + 25)
    r = O.tick(dt.datetime(2026, 10, 28, 22, 0, 20, tzinfo=UTC), ask=lambda p: {"action": "ENTER_LONG", "reason": "go"},
               ballots=lambda p, k, timeout: [{"action": "ENTER_LONG"}, {"action": "WAIT"}, {"action": "ENTER_LONG"}, {"action": "WAIT"}])
    assert r["would_press"] is True and r["votes"]["agree"] == 3 and r["session"] == "2026-10-29"
    assert json.loads(open(tmp_path / "log.jsonl").read())["event"] == "OVERNIGHT_SHADOW"


def test_switch_off_does_nothing(tmp_path, monkeypatch):
    env = tmp_path / "env"; env.write_text("hybrid_robot=on\n")
    monkeypatch.setattr(O.H, "SWITCH", str(env))
    assert O.tick(dt.datetime(2026, 10, 28, 23, 0, tzinfo=UTC)) is None
