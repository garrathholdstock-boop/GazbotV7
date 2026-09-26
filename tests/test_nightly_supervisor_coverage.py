"""THE SUPERVISOR MUST WATCH EVERY GUARD, AND MUST SPEAK EVERY NIGHT.

★★★2026-09-26 AUDIT. Two defects in the one job whose whole purpose is noticing that something
stopped:

  1. REQUIRED_SERVICES had not grown since 2026-08-13, so every safety watcher built after that
     date ran unwatched — gateway-watch (the wedge detector, $364 and $2,149 when absent),
     step-away (his away-guard), web (his BUTTONS), tgbot (phone control), rider-peak-watch.
     TIMER_FRESHNESS checked the router every 0.25h and never checked desk-reconcile, the
     30-second cross-desk invariant.
  2. It sent only `if faults or repaired`, so A CLEAN NIGHT AND A DEAD SUPERVISOR WERE THE SAME
     SILENCE — and nothing checks the supervisor, because it is the thing that checks everything
     else. Operator: "so we never dont know something is happening in the background."
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/scripts")
sys.path.insert(0, "/home/alphabot/gazbot7/src")

import nightly_supervisor as ns


# ── 1. COVERAGE ────────────────────────────────────────────────────────────────────────────────
# Named explicitly, because the defect was an OMISSION — a test that only checked "the list is
# non-empty" would have passed throughout.
GUARDS_THAT_COST_MONEY_WHEN_DOWN = [
    "gazbot7-gateway-watch",      # blind windows measured in hours
    "gazbot7-step-away",          # an armed guard that is not running is not a guard
]
HIS_OWN_CONTROLS = [
    "gazbot7-web",                # the BUY / SELL / CLAIM buttons
    "gazbot7-tgbot",              # phone control
]
SAFETY_TIMERS = [
    "gazbot7-desk-reconcile.timer",       # 30s — IBKR vs every desk's claim
    "gazbot7-daily-loss-limit.timer",     # the only risk rule that actually runs
    "gazbot7-request-watch.timer",        # did his press land
    "gazbot7-day-rider-watchdog.timer",   # flattens a position nobody is managing
]


def test_every_guard_that_costs_money_when_down_is_watched():
    for unit in GUARDS_THAT_COST_MONEY_WHEN_DOWN:
        assert unit in ns.REQUIRED_SERVICES, f"{unit} can be down with nothing saying so"


def test_his_own_controls_are_watched():
    """If web or tgbot is down he has no hands, and before this nothing paged."""
    for unit in HIS_OWN_CONTROLS:
        assert unit in ns.REQUIRED_SERVICES, f"{unit} is how he acts — it must be watched"


def test_the_safety_timers_are_checked_for_actually_firing():
    """'enabled and active' is not 'working' — the 2026-08-13 lesson. These are the four whose
    silence is most expensive, and none of them was checked."""
    for unit in SAFETY_TIMERS:
        assert unit in ns.TIMER_FRESHNESS, f"{unit} could stop firing unnoticed"


def test_the_reconciler_is_held_to_a_tight_window():
    """It runs every 30 seconds. A generous window would let a real outage pass as fresh."""
    assert ns.TIMER_FRESHNESS["gazbot7-desk-reconcile.timer"] <= 0.25


def test_vestigial_units_are_still_NOT_required():
    """⚠ The opposite failure: requiring a unit that has never run manufactures a nightly false
    alarm, which is how real ones get ignored."""
    for unit in ("gazbot7-core", "gazbot7-strategy"):
        assert unit not in ns.REQUIRED_SERVICES


# ── 2. IT SPEAKS EVERY NIGHT ───────────────────────────────────────────────────────────────────
def test_a_clean_night_still_sends():
    """★ THE INVARIANT: silence means the supervisor itself is gone, never 'all was well'."""
    text, critical, mark = ns.supervisor_message([], [], [], flat=True)
    assert text, "a clean night must still produce a message"
    assert "all clear" in text


def test_the_all_clear_is_not_critical_and_not_marked():
    """⚠ It must not bypass quiet hours and must never wear 🔴 — it is a heartbeat, not an alarm.
    Marking it would be exactly the dilution the 09-24 mark rule exists to prevent."""
    _, critical, mark = ns.supervisor_message([], [], [], flat=True)
    assert critical is False and mark is False


def test_a_fault_IS_critical_and_marked():
    text, critical, mark = ns.supervisor_message(["SERVICES down: gazbot7-web"], [], [], flat=True)
    assert critical is True and mark is True
    assert "gazbot7-web" in text


def test_the_all_clear_reports_what_it_actually_checked():
    """A heartbeat that does not say what it verified is the instrument-reports-healthy failure —
    it would read identically if the lists were empty."""
    text, _, _ = ns.supervisor_message([], [], [], flat=True)
    assert str(len(ns.REQUIRED_SERVICES)) in text
    assert str(len(ns.TIMER_FRESHNESS)) in text


def test_repairs_and_declines_survive_into_both_messages():
    """A repair he is not told about is a background action he cannot audit — on a clean night
    just as much as a faulty one."""
    for faults in ([], ["something"]):
        text, _, _ = ns.supervisor_message(faults, ["gazbot7-md"],
                                           ["gazbot7-web (not flat)"], flat=True)
        assert "REPAIRED: gazbot7-md" in text
        assert "NOT repaired" in text


# ── 3. DORMANT IS NOT STALE ────────────────────────────────────────────────────────────────────
def test_a_weekday_only_timer_is_dormant_at_the_weekend_not_stale(monkeypatch):
    """★★ TWO FALSE CRITICALS EVERY WEEKEND. This supervisor runs `*-*-*`; claude-job@sweep is
    `Mon-Fri`, so on Sat/Sun its last trigger was legitimately 24-48h old against a 6h window."""
    monkeypatch.setattr(ns, "sh", lambda *c, **k: (
        "Mon 2026-09-28 00:41:00 UTC" if "NextElapseUSecRealtime" in c else
        str(int(__import__("time").time() + 36 * 3600))))
    dormant, _ = ns.timer_is_dormant("gazbot7-claude-job@sweep.timer", 6.0)
    assert dormant is True


def test_a_frequent_timer_is_never_dormant(monkeypatch):
    """A 5-minute timer is always due, so an old last-trigger is always a real fault."""
    monkeypatch.setattr(ns, "sh", lambda *c, **k: (
        "Sat 2026-09-26 15:25:00 UTC" if "NextElapseUSecRealtime" in c else
        str(int(__import__("time").time() + 120))))
    dormant, _ = ns.timer_is_dormant("gazbot7-router-tick.timer", 0.25)
    assert dormant is False


def test_an_unreadable_next_elapse_FAILS_LOUD(monkeypatch):
    """⚠⚠ 'I cannot tell whether it was due' must never read as 'it was not due'. Anything else
    and an unparseable schedule silences the check."""
    for bad in ("", "n/a", "0", "not a date"):
        monkeypatch.setattr(ns, "sh", lambda *c, **k: bad)
        dormant, _ = ns.timer_is_dormant("gazbot7-anything.timer", 6.0)
        assert dormant is False, f"{bad!r} must not be treated as dormant"


def test_the_schedule_is_not_reimplemented_here():
    """⚠ systemd is the authority on its own calendar. A second OnCalendar parser would drift from
    the first, so the check must ASK systemd rather than compute weekdays itself.

    ⚠⚠ This test was itself written wrong the first time: it grepped the whole function for
    "Mon-Fri", which appears in the DOCSTRING explaining the bug. That is the comment trap — six
    assertions fell to it in the two days before this audit — so it now strips comments and
    docstring lines and inspects CODE only.
    """
    src = open("/home/alphabot/gazbot7/scripts/nightly_supervisor.py").read()
    body = src.split("def timer_is_dormant")[1].split("\ndef ")[0]
    # keep code lines only: drop comments and the docstring block
    code, in_doc = [], False
    for ln in body.splitlines():
        st = ln.strip()
        if st.count('"""') == 1:
            in_doc = not in_doc
            continue
        if in_doc or st.startswith("#") or st.startswith('"""'):
            continue
        code.append(ln)
    code = "\n".join(code)
    assert "NextElapseUSecRealtime" in code, "it must ask systemd for the next elapse"
    for reimpl in ("weekday", "strftime", "%a", "calendar", "Mon", "Fri"):
        assert reimpl not in code, f"{reimpl!r} in code means the calendar is being reimplemented"


# ── 4. THE APPEND-FILE OWNERSHIP CHECK (2026-09-26, the third instance of this bug) ────────────
def test_the_append_ownership_check_exists_and_distinguishes_write_patterns():
    """★★★ A data file created by ROOT that the appending service (alphabot) cannot write. Twice:
    08-21 `.notify_env` 600 root:root muted FIVE services for ~12h while the rider crashed
    mid-flatten; 09-26 `equity_guard.jsonl` made the brand-new account reader log a PermissionError
    every 2 minutes for 25 minutes while exiting 0.

    ⚠⚠ THE CHECK WAS WRONG ON ITS FIRST CUT AND THIS TEST PINS THE CORRECTION. It flagged seven
    files that were fine, because it ignored the write PATTERN: tmp + os.replace needs DIRECTORY
    write (so a root-owned target is harmless — verified by running tgbot's exact write against
    gate_switches.env as alphabot: it succeeded), while open(path,"a") needs FILE write. Seven
    nightly false faults is how a real one gets ignored.
    """
    src = open("/home/alphabot/gazbot7/scripts/nightly_supervisor.py").read()
    assert "APPEND_WRITERS" in src
    # ⚠ split on the tuple's CLOSING line, not on the first ")" — that is the first entry's own
    # paren, which truncated this test's view to one element and failed on a correct list.
    body = src.split("APPEND_WRITERS = (", 1)[1].split("\n    )", 1)[0]
    # the atomic-replace files must NOT be in the list
    for atomic in ("gate_switches.env", "day_rider.env", "core_health.json",
                   "desk_reconcile_state.json"):
        assert atomic not in body, (
            f"{atomic} is written with tmp+os.replace, which needs DIRECTORY write — listing it "
            f"here manufactures a nightly false fault")
    # and the ones that actually broke must BE in it
    for appended in ("equity_guard.jsonl", "gateway_watch.log"):
        assert appended in body, f"{appended} is append-only and is the case that broke"


def test_root_appenders_are_skipped_because_root_bypasses_permissions():
    """⚠ Checking a root-written file against uid 0 would always pass and always be meaningless —
    the same false comfort as sweep's 'restarts core: 0' for a unit that never ran. Skipped
    explicitly instead, so nobody later reads its silence as a verified pass."""
    src = open("/home/alphabot/gazbot7/scripts/nightly_supervisor.py").read()
    seg = src.split("APPEND_WRITERS = (", 1)[1]
    assert "uid == 0" in seg and "root bypasses file permissions" in seg
