"""PRESENCE — "the dashboard was open" is NOT "he was looking", and the devices differ.

Operator, 2026-09-18: *"im looking at it periodically during the work day when i have time. not all
day and reading every telegram."*

★★★ WHY IT MATTERS. Alert scoring found 17 alerts he never acted on. Without presence they all read
as rejections; with it, 12 fired while he was demonstrably looking and 5 did not. Only the 12 are
evidence about his judgement — the rest are alerts nobody saw.

⚠⚠⚠ MEASURED 2026-09-18, and it is the whole reason the devices are kept apart:
    DESKTOP  14,571 requests in 109 minutes = 134/MINUTE, zero gaps over 30 min, ONE session.
             That page polls, so a tab left open manufactures presence indefinitely.
    PHONE    3,550 requests, TEN distinct sessions across 02:25-08:19.
"""
import datetime as dt
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")

import presence as pr

SRC = "/home/alphabot/gazbot7/scripts/presence.py"


def test_a_desktop_session_is_never_the_strong_signal():
    """★★★ THE CORE GUARD. The desktop polls 134x/min — an idle tab must never read as attention,
    and `strong_only` must DEFAULT to refusing it rather than quietly upgrading."""
    import inspect
    sig = inspect.signature(pr.looked_around)
    assert sig.parameters["strong_only"].default is True, (
        "strong_only no longer defaults True — an idle desktop tab would read as 'he looked'")


def test_bots_are_excluded_by_user_agent_not_by_ip():
    """⚠ The scanners rotate addresses; an IP allowlist would drift silently."""
    assert pr.BOT_UA.search('"Hello from Palo Alto Networks, find out more about our scans"')
    assert pr.BOT_UA.search("python-requests/2.31")
    assert not pr.BOT_UA.search(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) Version/26.6.1 Mobile Safari/604.1")


def test_his_two_devices_are_recognised_and_not_confused():
    phone = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) Version/26.6.1 Mobile/15E148"
    desk = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/153.0.0.0 Safari/537.36"
    assert pr.PHONE_UA.search(phone) and not pr.DESK_UA.search(phone)
    assert pr.DESK_UA.search(desk) and not pr.PHONE_UA.search(desk)


def test_devices_are_sessionised_SEPARATELY():
    """⚠ Merging first would let the desktop's 134 req/min swallow every phone gap and report one
    unbroken presence for the whole day."""
    src = open(SRC).read()
    assert 'for who in ("phone", "desk")' in src, "sessions() no longer splits by device first"
    assert "NEVER merge the devices before sessionising" in src


def test_the_session_gap_is_longer_than_a_polling_interval():
    """★ A gap shorter than the page's own refresh would split one look into dozens of sessions."""
    assert pr.SESSION_GAP_S >= 300, "the session gap is short enough to shatter a single look"


def test_sessions_are_bursts_not_one_blob():
    """★ The live check: his phone showed TEN sessions in six hours. One blob means the gap logic
    is broken and every absence has been erased."""
    ss = [s for s in pr.sessions("2026-09-18") if s["device"] == "phone"]
    if not ss:
        import pytest
        pytest.skip("no phone traffic on the sampled day")
    assert len(ss) >= 3, f"phone sessionised into {len(ss)} blocks — the gap logic has collapsed"
    assert all(s["end"] >= s["start"] for s in ss)


def test_it_reads_rotated_logs_too():
    """⚠ nginx rotates daily and gzips. A presence history that silently starts at midnight would
    make every alert before today look unseen."""
    src = open(SRC).read()
    assert "gzip" in src and "access.log*" in src


def test_it_is_read_only():
    src = open(SRC).read()
    for banned in ("placeOrder", "connectAsync", "gate_switches", '"w"', "os.remove", "os.unlink"):
        assert banned not in src, f"presence reached for {banned}"
