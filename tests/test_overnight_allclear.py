"""SILENCE IS ONLY AN ALARM IF SOMETHING ELSE IS LISTENING.

★★★2026-09-26, AND THIS IS THE SECOND ATTEMPT AT ONE IDEA — the first one did not work and the
reason is the lesson. The audit found `nightly_supervisor` spoke only on faults, so a clean night and
a DEAD supervisor were identical silence. The fix made it send unconditionally. That fix was
suppressed EVERY NIGHT OF THE YEAR: it fires 21:40 UTC = 23:40 Paris (22:40 CET), quiet hours are
22:00-06:00 Paris, and the all-clear was correctly non-critical.

⚠⚠ The design error was deeper than the timestamp: **A PROCESS CANNOT REPORT ITS OWN ABSENCE.** So
this job is a DIFFERENT process on a DIFFERENT timer at 06:05 Paris — just after quiet hours end, so
it needs no exemption — and it asks a question about SOMEONE ELSE.
"""
import datetime as dt
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import overnight_allclear as oc

NOW = dt.datetime(2026, 9, 27, 4, 5, tzinfo=dt.UTC)      # 06:05 Paris


def _verdict(tmp_path, payload, *, age_h=7.0):
    p = tmp_path / "nightly_supervisor.json"
    p.write_text(json.dumps(payload))
    import os
    t = NOW.timestamp() - age_h * 3600
    os.utime(p, (t, t))
    return str(p)


# ── the case the whole job exists for ─────────────────────────────────────────────────────────
def test_a_MISSING_verdict_is_CRITICAL():
    """★ The supervisor did not run. Before this, that was indistinguishable from a good night."""
    status, msg, critical = oc.assess(NOW, "/definitely/not/here.json")
    assert status == "MISSING" and critical is True
    assert "DID NOT RUN" in msg


def test_a_STALE_verdict_is_CRITICAL(tmp_path):
    """A file from two nights ago is the same fact as no file — last night was not verified."""
    path = _verdict(tmp_path, {"faults": []}, age_h=30.0)
    status, msg, critical = oc.assess(NOW, path)
    assert status == "STALE" and critical is True


def test_an_UNREADABLE_verdict_is_CRITICAL(tmp_path):
    p = tmp_path / "nightly_supervisor.json"
    p.write_text("{ this is not json")
    import os
    t = NOW.timestamp() - 7 * 3600
    os.utime(p, (t, t))
    status, _msg, critical = oc.assess(NOW, str(p))
    assert status == "UNREADABLE" and critical is True


def test_a_fresh_CLEAN_verdict_is_one_quiet_line(tmp_path):
    path = _verdict(tmp_path, {"faults": [], "repaired": [], "router_aborts_today": 0})
    status, msg, critical = oc.assess(NOW, path)
    assert status == "OK" and critical is False
    assert "verified clean" in msg


def test_faults_are_repeated_in_the_morning(tmp_path):
    """They already paged at 21:40 in real time; this is the record he reads with coffee. A repeat
    is cheap next to a missed one."""
    path = _verdict(tmp_path, {"faults": ["SERVICES down: gazbot7-web"],
                               "declined_repairs": ["gazbot7-md (not flat)"]})
    status, msg, critical = oc.assess(NOW, path)
    assert status == "FAULT" and critical is True
    assert "gazbot7-web" in msg and "NOT repaired" in msg


# ── the properties that make it work at all ───────────────────────────────────────────────────
def test_it_runs_OUTSIDE_quiet_hours_so_it_needs_no_exemption():
    """⚠⚠ THE WHOLE POINT OF THE HOUR. If this ever moved back inside 22:00-06:00 Paris it would be
    silently suppressed exactly like the first attempt — and adding a quiet-hours bypass would
    re-couple the `critical`/`mark` flags that the 2026-09-24 split separated.
    Checked in BOTH CEST and CET, because a UTC schedule would drift across the DST change."""
    from gazbot7.notify import _PARIS, in_quiet_hours
    for month, day in ((9, 21), (11, 16)):
        fire = dt.datetime(2026, month, day, 6, 5, tzinfo=_PARIS)
        assert in_quiet_hours(fire) is False, f"06:05 Paris fell inside quiet hours in month {month}"


def test_the_timer_is_scheduled_in_PARIS_not_UTC():
    """★ A UTC time would sit outside quiet hours for half the year and inside it for the other
    half — the same class of bug as storing event times in UTC (CLAUDE.md, the event calendar)."""
    unit = open("/home/alphabot/gazbot7/ops/systemd/gazbot7-overnight-allclear.timer").read()
    assert "Europe/Paris" in unit
    assert "Persistent=true" in unit, (
        "if the box was down at 06:05 the question 'did last night run?' is MORE interesting")


def test_it_is_a_DIFFERENT_process_from_the_one_it_checks():
    """⚠ The invariant behind the whole file. If this ever became part of nightly_supervisor it
    would be unable to report that nightly_supervisor is dead."""
    unit = open("/home/alphabot/gazbot7/ops/systemd/gazbot7-overnight-allclear.service").read()
    assert "overnight_allclear.py" in unit
    assert "nightly_supervisor" not in unit.split("ExecStart")[1]


def test_it_has_no_authority():
    """⚠ CAPABILITY, NOT SUBSTRINGS. My first cut of this test failed on the word "systemctl"
    appearing in the ALERT TEXT ("check `systemctl status gazbot7-nightly-supervisor`") — advice for
    him, not an action it can take. Grepping raw source for a verb is the comment-trap class; what
    matters is whether the module can execute or write anything, so this checks imports and write
    targets instead."""
    import ast
    src = open("/home/alphabot/gazbot7/scripts/overnight_allclear.py").read()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for banned in ("subprocess", "shutil", "ib_async", "socket"):
        assert banned not in imported, f"a morning report must not import {banned}"
    # the only file it may open is the verdict, and only for reading
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
            mode = node.args[1].value if len(node.args) > 1 else "r"
            assert mode == "r", f"it opened a file with mode {mode!r} — it must only read"
    for banned in ("placeOrder", "gate_switches", "day_rider.env", "desk_kill"):
        assert banned not in src, f"a morning report must never name {banned}"


def test_the_clean_line_is_not_marked_but_the_missing_one_is(tmp_path):
    """⚠ 365 circled messages a year would be exactly the dilution the mark rule exists to stop —
    while a supervisor that did not run must wear it."""
    from gazbot7.notify import wears_the_mark
    clean = oc.assess(NOW, _verdict(tmp_path, {"faults": []}))[1]
    missing = oc.assess(NOW, "/nope.json")[1]
    assert wears_the_mark(missing) is True
    # the clean line is sent with mark=False explicitly; assert the call site keeps that
    src = open("/home/alphabot/gazbot7/scripts/overnight_allclear.py").read()
    assert "mark=None if critical else False" in src
    assert "verified clean" in clean
