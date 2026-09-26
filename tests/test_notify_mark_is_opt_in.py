"""THE 🔴 MARK IS OPT-IN, AND THE LIST IS SHORT.

★★★2026-09-26 AUDIT. The mark shipped on 2026-09-24 for "the four that can cost money, under one a
day". Measured from notify_sent.jsonl over the three days after: **241 of 456 sends carried it —
53%, about 80 a day.** Marked traffic included his OWN button confirmations (DAY RIDER MANUAL
BUY/SELL, 45 sends), RIDER PEAK readings, and ROUTER WATCH DAY-RIDER BLEED at 66 sends.

The cause was structural, not a bad call at any one site: `mark` DEFAULTED TO `critical`, and
`critical=True` is set at 56 places purely to bypass quiet hours. Splitting the two flags in the
signature while defaulting one to the other is not a split. The mark is now opt-in via MARK_ALWAYS.
"""
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.notify import CRITICAL_MARK, MARK_ALWAYS, notify, wears_the_mark

WEEKDAY_NOON = __import__("datetime").datetime(2026, 9, 23, 12, 0,
                                               tzinfo=__import__("datetime").UTC)


def _sent(msg, **kw):
    box = []
    notify(msg, now=WEEKDAY_NOON, send=lambda m: box.append(m) or True, **kw)
    return box[0] if box else None


# ── what must NOT wear it ──────────────────────────────────────────────────────────────────────
ROUTINE_BUT_CRITICAL = [
    # every one of these was marked in the measured window, and every one is either his own
    # action echoed back or a reading he asked for
    "DAY RIDER MANUAL BUY 4 lots @ 30910.25",
    "DAY RIDER MANUAL SELL 4 lots @ 30865.25",
    "GAZBOT ROUTER WATCH — 14:02:11Z DAY-RIDER BLEED — unrealised -$180",
    "📈 RIDER PEAK $262 (now $210) · 1.8x ATR",
    "RIDER +$200 — ABOVE $200 START WATCHING.",
    "😴 RIDER STALLED — peak $120 now $95",
    "⚠️ RIDER OFF THE HIGH — peak $262 now $187",
]


def test_routine_traffic_loses_the_circle_but_keeps_its_bypass():
    """★ THE POINT. These still reach him at 3am (critical=True); they just stop claiming to be
    the one to look at."""
    for msg in ROUTINE_BUT_CRITICAL:
        out = _sent(msg, critical=True)
        assert out is not None, f"{msg!r} must still be DELIVERED"
        assert not out.startswith(CRITICAL_MARK), f"{msg!r} must not wear the circle"


def test_critical_no_longer_implies_the_mark():
    """The exact defect: the flags were separated in the signature and then re-joined by default."""
    out = _sent("some entirely ordinary status line", critical=True)
    assert not out.startswith(CRITICAL_MARK)


# ── what MUST wear it ──────────────────────────────────────────────────────────────────────────
MUST_MARK = [
    "GAZBOT cross-desk kill FIRED — unaccounted -4",
    "[V7-tournament] SLOT DRIFT: logical net 0 != venue 4 — HALTED",
    "⚠⚠⚠ DESK IS BLIND AND HOLDING — holds 4 lot(s) and venue_ok=false",
    "🆘 DESK BLIND AND HOLDING, AND I HAVE STOPPED RESTARTING — 3 attempts",
    "⚠⚠ GATEWAY IS FILLING UP AND I CANNOT FIX IT — CLOSE-WAIT 44/50",
    "⚠ UNREAD CLAIM — pressed 130s ago and the rider has not consumed it",
    "DAILY LOSS LIMIT HIT — session P&L $-252.00 after 6 trades",
    "🛡 STEP AWAY FIRED — open P&L hit -204, your stop was $200",
    "⚠⚠ GAZBOT ORPHAN STOP — a working order with nothing behind it",
    "⚠ DAY RIDER WATCHDOG BLIND for 3 consecutive cycles",
    "GAZBOT ROUTER WATCH — ⚠DESK-MISMATCH — venue net +0 but day-rider claims +4",
]


def test_everything_that_can_cost_money_keeps_the_circle():
    for msg in MUST_MARK:
        out = _sent(msg, critical=True)
        assert out.startswith(CRITICAL_MARK), f"{msg!r} MUST wear the circle"


def test_anything_that_acts_on_his_position_is_marked():
    """⚠ The list was widened after replaying real traffic: a guard that flattens for him, an
    orphan order that can OPEN a position, and a blind watchdog are all position-affecting."""
    for frag in ("STEP AWAY FIRED", "ORPHAN STOP", "WATCHDOG BLIND", "DESK-MISMATCH"):
        assert any(frag in f for f in MARK_ALWAYS), f"{frag} must be markable"


# ── the properties of the mechanism itself ─────────────────────────────────────────────────────
def test_an_unknown_message_is_UNMARKED():
    """Opt-in means the safe default is 'ordinary'. A universal circle is the failure that was
    measured; a missing one merely makes a real alert look ordinary."""
    assert wears_the_mark("something nobody has classified yet") is False


def test_a_routine_alert_can_never_be_marked_even_if_asked():
    """⚠ If it is not worth waking him for, the circle would claim an urgency the quiet-hours rule
    itself denies. Pre-existing property — asserted so the opt-in change did not lose it."""
    out = _sent("DAILY LOSS LIMIT HIT", critical=False, mark=True)
    assert out is None or not out.startswith(CRITICAL_MARK)


def test_never_double_marked():
    out = _sent(CRITICAL_MARK + "SLOT DRIFT: logical net 0 != venue 4", critical=True)
    assert out.count(CRITICAL_MARK) == 1


def test_an_explicit_flag_still_wins_both_ways():
    assert _sent("unclassified thing", critical=True, mark=True).startswith(CRITICAL_MARK)
    assert not _sent("SLOT DRIFT here", critical=True, mark=False).startswith(CRITICAL_MARK)


def test_the_list_stays_short():
    """⚠ The moment this needs a scroll bar it has stopped working, and the failure is silent:
    nothing errors, the mark just stops meaning anything again."""
    assert len(MARK_ALWAYS) <= 20, f"MARK_ALWAYS has grown to {len(MARK_ALWAYS)} — re-read the rule"
