"""Everything is OFF at weekends. Operator, 2026-08-29: "everything should be off on weekends."

gazbot7-gate-reactivate runs at 00:00 Europe/Paris EVERY day = 22:00Z — and on Friday that is one
hour AFTER the CME halt. On 2026-08-28 it armed three gates into a venue shut until Sunday; the
router benched two as "housekeeping" and capitulation_long stayed armed the whole weekend.

No new clock is invented: session.is_open() already returns False at Fri/Sat 22:00Z and True at
Sun 22:00Z, because that instant IS the reopen. These tests pin that the SAME timer disarms on the
way into the weekend and arms on the way out.
"""
import datetime as dt, pytest
from gazbot7.session import is_open

Z = dt.UTC


def at(day, h=22, m=0):
    return dt.datetime(2026, 8, day, h, m, tzinfo=Z)


@pytest.mark.parametrize("day,label", [(28, "Friday 22:00Z — 1h after the halt"),
                                       (29, "Saturday 22:00Z")])
def test_the_paris_midnight_run_must_not_arm_into_a_shut_venue(day, label):
    assert is_open(at(day)) is False, f"{label} read as OPEN — gates would arm into a shut venue"


def test_sunday_2200z_is_the_reopen_and_must_arm():
    """★ The boundary that makes one timer enough: Sunday 22:00Z IS the reopen."""
    assert is_open(at(30)) is True, "the Sunday reopen was treated as weekend — nothing would arm"


@pytest.mark.parametrize("day", [24, 25, 26, 27])
def test_weeknight_reopens_still_arm(day):
    assert is_open(at(day)) is True


@pytest.mark.parametrize("h", [0, 6, 12, 18, 23])
def test_saturday_is_shut_all_day(h):
    assert is_open(at(29, h)) is False


def test_the_guard_actually_runs_and_disarms(tmp_path, monkeypatch, capsys):
    """★ EXECUTED, not grepped. The first version of this test only searched the source, and it
    passed green while the job crashed on an AttributeError before ever reaching the guard — the
    same 'a string in the file is not a working code path' failure that let a gutted order function
    through on 08-21. Drive the real run() against a temp switch file."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rg", "/home/alphabot/gazbot7/scripts/reactivate_gates.py")
    rg = importlib.util.module_from_spec(spec); spec.loader.exec_module(rg)

    sw = tmp_path / "gate_switches.env"
    sw.write_text("# header\ngrind_long=on\ncapitulation_long=on\nabs_veto_long=off\n")
    monkeypatch.setattr(rg, "SWITCH", str(sw))
    monkeypatch.setattr(rg, "_session_is_open", lambda now: False)   # the weekend
    assert rg.run() == 0
    body = sw.read_text()
    assert "grind_long=off" in body and "capitulation_long=off" in body, \
        "the weekend run did not disarm the armed gates"
    assert "=on" not in body, "a gate survived the weekend disarm"
    assert "VENUE SHUT" in capsys.readouterr().out


def test_when_open_it_still_arms(tmp_path, monkeypatch):
    """The guard must not swallow the ordinary weeknight reopen."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rg2", "/home/alphabot/gazbot7/scripts/reactivate_gates.py")
    rg = importlib.util.module_from_spec(spec); spec.loader.exec_module(rg)
    sw = tmp_path / "gate_switches.env"
    sw.write_text("# header\nexhaustion_short=off\n")
    monkeypatch.setattr(rg, "SWITCH", str(sw))
    monkeypatch.setattr(rg, "_session_is_open", lambda now: True)
    rg.run()
    assert "exhaustion_short=on" in sw.read_text(), "the reopen stopped arming"
