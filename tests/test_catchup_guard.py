"""The repair pass must never run a second build on top of a live one.

2026-08-25: the guard was `systemctl is-active --quiet`, which exits NON-ZERO for the state
"activating" — exactly the state a long-running `Type=oneshot` sits in for its whole run. It
reported "not running" about a running build and launched a competing serial_runner: two builds
racing over the same section artifacts and the same headless-Claude auth, unattended at 01:00.
Caught only by running it. Both checks are asserted here so neither can silently regress.
"""
import importlib.util, types, pytest

spec = importlib.util.spec_from_file_location("r", "/home/alphabot/gazbot7/scripts/friday/catchup_repair.py")
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)


def _systemctl(state):
    def run(cmd, *a, **k):
        if cmd[0] == "systemctl":
            return types.SimpleNamespace(stdout=state, returncode=0)
        return types.SimpleNamespace(stdout="", returncode=1)
    return run


@pytest.mark.parametrize("state", ["active", "activating", "reloading", "deactivating"])
def test_every_busy_state_stands_the_repair_down(state, monkeypatch):
    monkeypatch.setattr(R.subprocess, "run", _systemctl(state))
    assert R.unit_busy("x") is True, f"state {state!r} was treated as NOT running"


@pytest.mark.parametrize("state", ["inactive", "failed"])
def test_idle_states_allow_the_repair(state, monkeypatch):
    monkeypatch.setattr(R.subprocess, "run", _systemctl(state))
    assert R.unit_busy("x") is False


def test_activating_specifically(monkeypatch):
    """★ THE EXACT BUG. A Type=oneshot build reports 'activating' for its entire run."""
    monkeypatch.setattr(R.subprocess, "run", _systemctl("activating"))
    assert R.unit_busy("gazbot7-friday-catchup.service") is True


def test_a_hand_started_build_is_also_caught(monkeypatch):
    """The 18:07 collision came from a build started OUTSIDE systemd — unit state cannot see it."""
    monkeypatch.setattr(R.subprocess, "run",
                        lambda cmd, *a, **k: types.SimpleNamespace(stdout="12345\n", returncode=0))
    assert R.build_running() is True


def test_no_process_means_clear(monkeypatch):
    monkeypatch.setattr(R.subprocess, "run",
                        lambda cmd, *a, **k: types.SimpleNamespace(stdout="", returncode=1))
    assert R.build_running() is False


def test_main_stands_down_when_a_build_is_activating(monkeypatch, capsys):
    monkeypatch.setattr(R, "unit_busy", lambda u: u.endswith("catchup.service"))
    called = []
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: called.append(a) or
                        types.SimpleNamespace(stdout="activating", returncode=0))
    assert R.main() == 0
    assert "standing down" in capsys.readouterr().out
