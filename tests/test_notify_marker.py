"""CRITICAL ALERTS CARRY A ONE-GLANCE MARKER.

★★★ WHY (2026-09-24). The operator receives ~10 Telegrams a day and 85% of them are informational
(leg 4.6/day, tunnel 3.7/day). The FOUR that can actually cost him money — rider blind and holding,
rider cannot flatten, an unread press, a book/venue mismatch — total under ONE a day and were
buried underneath. His words: "a lot are old and not useful. theres going to be several that i
really need so we need to make sure theyre useful so i dont ignore."

An alarm channel he has learned to swipe past is an alarm channel he does not have.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import notify as N


def test_critical_alerts_are_marked():
    sent = []
    N.notify("the rider is blind and holding", critical=True, send=sent.append)
    assert sent[0].startswith(N.CRITICAL_MARK)


def test_routine_alerts_are_not():
    """⚠ If everything is marked, nothing is. The 4.6/day leg alert must stay unmarked."""
    sent = []
    N.notify("UP LEG · 60min", critical=False, now=None, send=sent.append)
    assert not sent or not sent[0].startswith(N.CRITICAL_MARK)


def test_the_mark_never_doubles():
    """⚠ A caller that already prefixed, or a retry of the same text, must not accumulate circles."""
    sent = []
    N.notify(N.CRITICAL_MARK + "already marked", critical=True, send=sent.append)
    assert sent[0].count(N.CRITICAL_MARK) == 1


def test_the_mark_is_applied_in_ONE_place():
    """⚠⚠ Not at the 46 call sites. A marker added per-caller drifts the moment someone adds the
    47th — and then the ABSENCE of a mark means nothing, which is worse than no mark at all."""
    import subprocess
    out = subprocess.run(["grep", "-rn", "CRITICAL_MARK", "--include=*.py",
                          "/home/alphabot/gazbot7/src", "/home/alphabot/gazbot7/scripts"],
                         capture_output=True, text=True).stdout
    files = {l.split(":")[0] for l in out.splitlines() if l.strip()}
    assert files == {"/home/alphabot/gazbot7/src/gazbot7/notify.py"}, (
        f"CRITICAL_MARK is referenced outside notify.py: {sorted(files)}")


def test_critical_still_bypasses_quiet_hours():
    """★ The mark must not have changed what `critical` MEANS — it already selected the set that
    matters at 3am, which is exactly the set worth marking."""
    import datetime as dt
    quiet = dt.datetime(2026, 9, 24, 2, 0, tzinfo=dt.UTC)
    sent = []
    N.notify("safety", critical=True, now=quiet, send=sent.append)
    assert sent, "a critical alert was suppressed during quiet hours"
