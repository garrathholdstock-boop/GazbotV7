"""Sweep must go CRITICAL on an unreadable alarm credential — and it must be provable.

2026-08-21: five desk services could not page for ~12 hours and sweep stayed green, because sweep
never looked. A check that cannot be shown to fail is the same class of instrument as the one that
caused the outage, so this asserts BOTH directions.
"""
import importlib.util, os, pwd, pytest

spec = importlib.util.spec_from_file_location("sweep", "/home/alphabot/gazbot7/scripts/sweep.py")
sweep = importlib.util.module_from_spec(spec); spec.loader.exec_module(sweep)

HAS_DESK_USER = True
try:
    DESK_UID = pwd.getpwnam("alphabot").pw_uid
except KeyError:
    HAS_DESK_USER = False


@pytest.mark.skipif(not HAS_DESK_USER, reason="no alphabot user on this box")
def test_root_owned_credentials_are_CRITICAL(tmp_path):
    f = tmp_path / ".notify_env"; f.write_text("TELEGRAM_TOKEN=x\n"); f.chmod(0o600)
    os.chown(f, 0, 0)                       # root:root 600 — exactly the outage
    r = sweep.check_alarm_chain(str(f))
    assert r["status"] == "critical", "sweep stayed green on a dead alarm chain"
    assert "UNABLE TO PAGE" in " ".join(r["notes"])


@pytest.mark.skipif(not HAS_DESK_USER, reason="no alphabot user on this box")
def test_desk_owned_credentials_are_ok(tmp_path):
    f = tmp_path / ".notify_env"; f.write_text("TELEGRAM_TOKEN=x\n"); f.chmod(0o600)
    os.chown(f, DESK_UID, DESK_UID)
    assert sweep.check_alarm_chain(str(f))["status"] == "ok"


def test_a_missing_credentials_file_warns(tmp_path):
    """The legacy alphabot2 fallback is RETIRED, so missing is not 'fine'."""
    r = sweep.check_alarm_chain(str(tmp_path / "nope"))
    assert r["status"] == "warn" and "MISSING" in " ".join(r["notes"])


def test_the_live_desk_can_page():
    r = sweep.check_alarm_chain()
    assert r["status"] != "critical", f"THE DESK CANNOT PAGE: {r['notes']}"
