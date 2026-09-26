"""THE DEAD-MAN'S-SWITCH URL INSTALLER — it may write ONE key, and it verifies before it writes.

★2026-09-26. `data/live_mode.json` holds BOTH the monitoring URL and the kill-switch configuration
(`live_accounts`, `venue_stop_armed`, `equity_loss_limit_usd`, `margin_floor_usd`). A setter that
could write any key would be a path from "configure monitoring" to "arm a kill switch" — against the
operator's standing instruction for the paper phase. So the scope is narrow by construction.
"""
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import deadman as dm

SRC = "/home/alphabot/gazbot7/scripts/deadman.py"


def test_only_the_url_key_is_settable():
    assert dm.SETTABLE_KEY == "deadman_url"


def test_the_setter_cannot_touch_a_kill_switch():
    """⚠⚠ THE SAFETY PROPERTY. Asserted on the source because the guard is a comparison, and the
    only way to reach it with a kill-switch key would be to edit this function."""
    body = open(SRC).read().split("def set_url", 1)[1].split("\ndef ", 1)[0]
    code = "\n".join(l for l in body.splitlines()
                     if not l.strip().startswith("#") and '"""' not in l)
    for switch in ("venue_stop_armed", "live_accounts", "equity_loss_limit_usd",
                   "margin_floor_usd", "max_lots"):
        assert switch not in code, f"the URL setter must never name {switch}"
    # it must diff everything-but-the-one-key and refuse if anything else moved
    assert "before != after" in code
    assert "refusing to write" in body


def test_a_non_https_url_is_refused_without_a_network_call():
    for bad in ("not-a-url", "http://hc-ping.com/abc", "", "   ", "ftp://x/y"):
        ok, msg = dm.set_url(bad)
        assert ok is False
        assert "https" in msg


def test_it_VERIFIES_with_a_real_ping_before_writing(monkeypatch):
    """★ An unverified monitoring URL is worse than none: it makes the desk look watched when it is
    not. A URL that does not accept a ping must not be written."""
    calls = []
    monkeypatch.setattr(dm, "ping", lambda u, **k: calls.append(u) or (False, "HTTP 404"))
    ok, msg = dm.set_url("https://hc-ping.com/some-id")
    assert ok is False and calls, "it must actually ping before accepting"
    assert "nothing was written" in msg


def test_a_verified_url_is_written_and_nothing_else_changes(tmp_path, monkeypatch):
    conf = tmp_path / "live_mode.json"
    original = {"paper_accounts": ["DUQ191770"], "live_accounts": [],
                "venue_stop_armed": False, "equity_loss_limit_usd": None, "deadman_url": None}
    conf.write_text(json.dumps(original))
    monkeypatch.setattr(dm, "GB", str(tmp_path.parent))
    # GB is used as f"{GB}/data/live_mode.json" — lay the path out to match
    (tmp_path.parent / "data").mkdir(exist_ok=True)
    (tmp_path.parent / "data" / "live_mode.json").write_text(json.dumps(original))
    monkeypatch.setattr(dm, "ping", lambda u, **k: (True, "HTTP 200"))
    ok, msg = dm.set_url("https://hc-ping.com/a-real-looking-id")
    assert ok is True, msg
    after = json.loads((tmp_path.parent / "data" / "live_mode.json").read_text())
    assert after["deadman_url"] == "https://hc-ping.com/a-real-looking-id"
    for k, v in original.items():
        if k != "deadman_url":
            assert after[k] == v, f"{k} changed — the setter must write ONE key"


def test_the_url_is_never_printed_back():
    """⚠ The URL is a credential: anyone holding it can silence the alarm by pinging it. The
    success message names the HOST only."""
    body = open(SRC).read().split("def set_url", 1)[1].split("\ndef ", 1)[0]
    ret = [l for l in body.splitlines() if "installed" in l]
    assert ret and "parsed.netloc" in "".join(ret)
    assert "{u}" not in "".join(ret), "the raw URL must not reach the message"


def test_quoting_a_pasted_url_is_tolerated(monkeypatch):
    """A paste often arrives wrapped in quotes. That is not a reason to fail the operator."""
    seen = []
    monkeypatch.setattr(dm, "ping", lambda u, **k: seen.append(u) or (False, "stop here"))
    dm.set_url('  "https://hc-ping.com/xyz"  ')
    assert seen == ["https://hc-ping.com/xyz"]
