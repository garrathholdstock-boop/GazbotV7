"""CRITICAL ALERTS CARRY A ONE-GLANCE MARKER.

★★★ WHY (2026-09-24). The operator receives ~10 Telegrams a day and 85% of them are informational
(leg 4.6/day, tunnel 3.7/day). The FOUR that can actually cost him money — rider blind and holding,
rider cannot flatten, an unread press, a book/venue mismatch — total under ONE a day and were
buried underneath. His words: "a lot are old and not useful. theres going to be several that i
really need so we need to make sure theyre useful so i dont ignore."

An alarm channel he has learned to swipe past is an alarm channel he does not have.

★★★2026-09-26 AUDIT — THE MARK IS NOW OPT-IN, AND TWO TESTS IN THIS FILE WERE REVERSED ON PURPOSE.
Measured over the three days after the mark shipped: 241 of 456 sends wore it (53%, ~80/day) against
"under one a day". `mark` defaulted to `critical`, and `critical=True` is set at 56 sites purely for
the quiet-hours bypass — so the split introduced on 09-24 was never a split. notify.MARK_ALWAYS is
the list now; see tests/test_notify_mark_is_opt_in.py for the full rule.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7 import notify as N


def test_the_alerts_that_can_cost_money_are_marked():
    """★2026-09-26 THIS USED TO ASSERT ON A STRING NO CALLER EVER SENDS ("the rider is blind and
    holding"). It passed because `mark` defaulted to `critical`, so ANY text was marked — which
    means it would have gone on passing even if the REAL message had lost its circle. Now it uses
    the actual text `gateway_watch` emits, so it tests the path that runs."""
    for real_message in ("⚠⚠⚠ DESK IS BLIND AND HOLDING — holds 4 lot(s) and venue_ok=false",
                         "[V7-tournament] SLOT DRIFT: logical net 0 != venue 4 — HALTED",
                         "DAILY LOSS LIMIT HIT — session P&L $-252.00 after 6 trades"):
        sent = []
        N.notify(real_message, critical=True, send=sent.append)
        assert sent[0].startswith(N.CRITICAL_MARK), f"{real_message[:40]!r} lost its circle"


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


# ── the mark and the quiet-hours bypass are SEPARATE QUESTIONS (2026-09-24, same day) ────────────
# ★★★ `critical` was doing two jobs. `rider_peak_watch` sends all four of its alerts critical=True —
# correctly, because a position can still be open at 20:00Z when quiet hours begin — and that one
# service is ~63 messages a day. Within hours of the marker shipping it was on 98% routine traffic.
# The fix splits the flags. These tests pin BOTH halves, because dropping either one is a
# regression with no visible symptom: lose `mark` and the circle means nothing again; lose
# `critical` and his rungs go dark for the last 40 minutes before the hard flat.

def test_mark_can_be_declined_without_losing_the_quiet_hours_bypass():
    import datetime as dt
    quiet = dt.datetime(2026, 9, 24, 2, 0, tzinfo=dt.UTC)
    sent = []
    N.notify("RIDER PEAK $400", critical=True, mark=False, now=quiet, send=sent.append)
    assert sent, "mark=False must not stop a critical alert reaching him at any hour"
    assert not sent[0].startswith(N.CRITICAL_MARK)


def test_the_default_is_the_MARK_ALWAYS_list_not_critical():
    """⚠⚠⚠ 2026-09-26 THIS TEST'S ORIGINAL PREMISE WAS THE DEFECT, AND IT IS REVERSED DELIBERATELY.

    It used to assert `mark` defaults to `critical` "so every existing call site is unchanged".
    That default is exactly what diluted the circle: **241 of 456 sends in the three days after the
    mark shipped carried it — 53%, ~80/day** against a design intent of under one a day, because
    `critical=True` is set at 56 sites purely to bypass quiet hours and the default promoted all of
    them. Leaving the call sites unchanged was the goal; being unchanged is what broke it.

    So the default is now the MARK_ALWAYS list. Call sites are still untouched — the difference is
    that the mark is decided by WHAT THE MESSAGE IS, not by whether it may wake him.
    """
    sent = []
    N.notify("naked position", critical=True, send=sent.append)
    assert sent[0].startswith(N.CRITICAL_MARK), "a NAKED alert is on the list and must be marked"
    sent = []
    N.notify("DAY RIDER MANUAL BUY 4 lots @ 30910.25", critical=True, send=sent.append)
    assert sent and not sent[0].startswith(N.CRITICAL_MARK), (
        "his own button confirmation must NOT be marked — 45 of them were")


def test_a_routine_alert_can_never_be_marked():
    """⚠ If it is not worth waking him for, the circle claims an urgency quiet hours itself denies.
    Checked OUTSIDE quiet hours, so the assertion is about the mark and not about suppression."""
    import datetime as dt
    awake = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC)
    sent = []
    N.notify("informational", critical=False, mark=True, now=awake, send=sent.append)
    assert sent and not sent[0].startswith(N.CRITICAL_MARK)


def test_the_rider_rungs_are_unmarked_but_still_bypass_quiet_hours():
    """★ Asserted against the SOURCE: the three CONTINUATION alerts carry both flags.

    ⚠ ARM is deliberately NOT in this list — it opens the episode and keeps its circle. If a future
    edit "tidies" ARM into the same call shape, this test is what notices.
    """
    raw = open("/home/alphabot/gazbot7/scripts/rider_peak_watch.py", encoding="utf-8").read()
    # ⚠ STRIP COMMENTS FIRST. The block above this code EXPLAINS `mark=False`, so a naive count
    # over the raw text scores the prose as if it were calls — the same class of mistake as slicing
    # source by a fixed width. Count what RUNS.
    src = "\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#"))
    body = src.split('if kind == "ARM":', 1)[1]
    for kind in ("RUNG", "GIVEBACK"):
        seg = body[body.index(f'kind == "{kind}"'):][:400]
        assert "critical=True" in seg and "mark=False" in seg, f"{kind} lost a flag"
    assert body.count("mark=False") == 3, (
        f"expected exactly RUNG, GIVEBACK and STALL unmarked, found {body.count('mark=False')}")
    arm = body.split('elif kind ==', 1)[0]
    assert "mark=False" not in arm, "ARM opens the episode — it must keep its mark"
