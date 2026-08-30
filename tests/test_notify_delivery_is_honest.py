"""The alarm must know when it failed. Regression for the 2026-08-21 silent outage.

`data/.notify_env` was written mode 600 root:root while every desk service runs as `alphabot`.
open() raised PermissionError, `except Exception: pass` ate it, the sender exited 1 for want of
credentials, and `_subprocess_send` returned True regardless. Five services could not page for ~12
hours and no instrument noticed. The operator discovered it by pressing a button that did nothing.
"""
import os, pwd, subprocess, types, pytest
from gazbot7 import notify as N

DESK_USER = "alphabot"


def test_unreadable_credentials_are_reported_not_swallowed(tmp_path, monkeypatch, capsys):
    """★ Injected rather than chmod-ed: the suite runs as root, and root bypasses file permissions,
    so a chmod(0o000) fixture would SKIP on this box — silently retiring the one test that covers
    the fault. Raising PermissionError from open() exercises the same handler as any uid."""
    f = tmp_path / ".notify_env"
    f.write_text("TELEGRAM_TOKEN=x\nTELEGRAM_CHAT_ID=y\n")
    monkeypatch.setattr(N, "_ENVFILE", str(f))
    import builtins
    real = builtins.open

    def boom(path, *a, **k):
        if str(path) == str(f):
            raise PermissionError(13, "Permission denied")
        return real(path, *a, **k)

    monkeypatch.setattr(builtins, "open", boom)
    assert N._load_env() == {}
    assert "UNREADABLE" in capsys.readouterr().err, "a dead alarm chain said nothing"


def test_missing_credentials_stay_quiet(tmp_path, monkeypatch, capsys):
    """MISSING is the documented legacy-fallback path and must NOT cry wolf."""
    monkeypatch.setattr(N, "_ENVFILE", str(tmp_path / "does-not-exist"))
    assert N._load_env() == {}
    assert capsys.readouterr().err == ""


def _fake_run(code):
    return lambda *a, **k: types.SimpleNamespace(returncode=code)


def test_a_failing_sender_is_not_reported_as_delivered(monkeypatch, capsys):
    monkeypatch.setattr(N.subprocess, "run", _fake_run(1))
    assert N._subprocess_send("x") is False, "reported delivery while the sender exited non-zero"
    assert "NOT DELIVERED" in capsys.readouterr().err


def test_a_successful_sender_is_reported_as_delivered(monkeypatch):
    monkeypatch.setattr(N.subprocess, "run", _fake_run(0))
    assert N._subprocess_send("x") is True


def test_notify_propagates_failure_to_the_caller(monkeypatch):
    monkeypatch.setattr(N.subprocess, "run", _fake_run(1))
    assert N.notify("boom", critical=True) is False


@pytest.mark.skipif(not os.path.exists(N._ENVFILE), reason="no credentials file on this box")
def test_the_desk_user_can_actually_read_the_credentials():
    """★ THE CHECK THAT WAS MISSING. Every desk service runs as `alphabot`; root-only creds are
    a total alarm outage that every other instrument reports as healthy."""
    try:
        uid = pwd.getpwnam(DESK_USER).pw_uid
    except KeyError:
        pytest.skip(f"no {DESK_USER} user on this box")
    st = os.stat(N._ENVFILE)
    readable = st.st_uid == uid and st.st_mode & 0o400
    assert readable, (
        f"{N._ENVFILE} is uid {st.st_uid} mode {st.st_mode & 0o777:o} — the desk services run as "
        f"{DESK_USER} (uid {uid}) and CANNOT PAGE. This is a silent, total alarm outage.")
