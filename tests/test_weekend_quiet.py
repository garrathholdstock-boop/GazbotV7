"""WEEKEND QUIET — everything off while the desk is shut AND flat, except the reports (2026-09-26).

★★★ Operator, after a Saturday of alarms: "everything should be off on weekends except notifications
about reports."

⚠⚠⚠ AND THE CARVE-OUT IS NOT NEGOTIABLE: IT SUPPRESSES ONLY WHILE THE DESK IS FLAT. On 2026-08-21
four naked lots went through the halt INTO the weekend and cost -$2,149. A weekend gag that silenced
that would be the most dangerous thing in notify.py. So the rule is not "it is Saturday, be quiet" —
it is "there is nothing at risk, so be quiet", which is a different and safe statement.
"""
import datetime as dt
import json
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")
from gazbot7 import notify as N

SAT = dt.datetime(2026, 9, 26, 5, 39, tzinfo=dt.UTC)
FRI_TRADING = dt.datetime(2026, 9, 25, 20, 0, tzinfo=dt.UTC)


def _flat(monkeypatch, flat: bool):
    monkeypatch.setattr(N, "desk_is_flat_and_verified", lambda: flat)


def test_the_window_is_the_actual_halt_not_the_calendar_weekend():
    """Fri 21:00Z is the CME halt and Sun 22:00Z the reopen — not Saturday 00:00 to Sunday 23:59."""
    assert N.venue_shut_for_the_weekend(FRI_TRADING) is False
    assert N.venue_shut_for_the_weekend(dt.datetime(2026, 9, 25, 21, 30, tzinfo=dt.UTC)) is True
    assert N.venue_shut_for_the_weekend(SAT) is True
    assert N.venue_shut_for_the_weekend(dt.datetime(2026, 9, 27, 21, 0, tzinfo=dt.UTC)) is True
    assert N.venue_shut_for_the_weekend(dt.datetime(2026, 9, 27, 22, 30, tzinfo=dt.UTC)) is False


def test_a_critical_alert_is_suppressed_on_a_shut_flat_weekend(monkeypatch):
    """★ IT OUTRANKS `critical`. A critical alert about a desk that is shut and flat is still noise —
    and it was the 🔴 ones that woke him on the Saturday."""
    _flat(monkeypatch, True)
    sent = []
    assert N.notify("noise", critical=True, now=SAT, send=sent.append) is False
    assert not sent


def test_reports_still_speak(monkeypatch):
    """★ The one thing he asked to keep. And the Friday report RUNS in this window by design
    (Fri 22:07Z → Sat 05:15Z), so without the waiver the whole chain would be silenced by the very
    window it runs in."""
    _flat(monkeypatch, True)
    sent = []
    N.notify("✅ Friday report READY", critical=True, weekend_ok=True, now=SAT, send=sent.append)
    assert sent, "the report chain was silenced"


def test_EVERYTHING_speaks_if_the_desk_is_NOT_flat(monkeypatch):
    """⚠⚠⚠ THE SAFETY PROPERTY. 2026-08-21: four naked lots through the halt into the weekend,
    -$2,149. If anything is open, every alarm works normally — that is precisely when he needs them."""
    _flat(monkeypatch, False)
    sent = []
    assert N.notify("naked position!", critical=True, now=SAT, send=sent.append) is not False
    assert sent


def test_it_fails_OPEN_when_the_position_cannot_be_read(monkeypatch, tmp_path):
    """⚠ NOT KNOWING IS NOT FLAT. Every error path in desk_is_flat_and_verified must return False,
    i.e. must SPEAK. A gag that engaged when it could not see the book would be silent exactly when
    the desk was in trouble."""
    monkeypatch.setattr(N, "_WEEKEND_STATE", str(tmp_path / "nope.json"))
    assert N.desk_is_flat_and_verified() is False


def test_a_stale_venue_read_is_not_evidence_of_flat(monkeypatch, tmp_path):
    import os, time
    p = tmp_path / "recon.json"
    p.write_text(json.dumps({"read1": {"ok": True, "venue": 0}}))
    old = time.time() - 6000
    os.utime(p, (old, old))
    monkeypatch.setattr(N, "_WEEKEND_STATE", str(p))
    assert N.desk_is_flat_and_verified() is False, "a 100-minute-old read was treated as flat"


def test_our_own_book_disagreeing_also_speaks(monkeypatch, tmp_path):
    """⚠ "IBKR IS THE TRUTH" cuts both ways here: the venue reading zero is not enough if OUR book
    thinks it holds something, because that disagreement is itself an alarm."""
    r = tmp_path / "recon.json"; r.write_text(json.dumps({"read1": {"ok": True, "venue": 0}}))
    d = tmp_path / "rider.json"; d.write_text(json.dumps({"qty": 4.0, "closed": False}))
    monkeypatch.setattr(N, "_WEEKEND_STATE", str(r))
    monkeypatch.setattr(N, "_WEEKEND_RIDER", str(d))
    assert N.desk_is_flat_and_verified() is False


def test_weekday_behaviour_is_completely_unchanged(monkeypatch):
    _flat(monkeypatch, True)
    sent = []
    assert N.notify("weekday", critical=True, now=FRI_TRADING, send=sent.append) is not False
    assert sent


def test_no_test_outcome_depends_on_the_day_of_the_week():
    """⚠⚠⚠ FIFTH INSTANCE IN ONE MORNING. Adding this gate immediately broke three tests that call
    notify() without an explicit `now` — they would have passed Monday to Friday and failed every
    weekend. Four others, fixed an hour earlier, were reading the LIVE TAPE and failing because the
    market was shut. Same root cause every time: a test whose result depends on when it runs.
    ★ The conftest neutralises the gate through its FLAT half, not its CALENDAR half — the gate needs
    both, so `venue_shut_for_the_weekend()` stays real for the tests whose subject it is, while every
    other test gets the SPEAKING behaviour. "Not flat" is the fail-open direction, so forgetting to
    think about this yields noise rather than silence."""
    raw = open("/home/alphabot/gazbot7/tests/conftest.py", encoding="utf-8").read()
    # ⚠⚠ STRIP COMMENTS FIRST — SIXTH TIME TODAY. The comment block beside this very patch EXPLAINS
    # the calendar/flat split and therefore names `venue_shut_for_the_weekend`, so a raw-text search
    # finds it in the prose and fails on correct code. A test about not repeating a mistake fell to a
    # different mistake I had already made five times this morning.
    c = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))
    assert 'setattr(_n, "desk_is_flat_and_verified", lambda: False)' in c
    body = c.split("def _no_telegram", 1)[1].split("yield", 1)[0]
    assert "venue_shut_for_the_weekend" not in body, \
        "the calendar half must stay real, or the gate's own tests become vacuous"
