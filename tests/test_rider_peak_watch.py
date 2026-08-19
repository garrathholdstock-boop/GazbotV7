"""The peak watcher must ping on the way UP and never machine-gun the alarm channel.

★2026-08-19. This process exists to give the operator presence he does not have — he claimed $726 by
hand in 23 minutes and could only do it because he happened to be watching. The failure modes are
asymmetric and both bad:

  * too few pings  -> he misses the peak, which is the entire point;
  * too many pings -> the ONE Telegram channel that also carries naked-position alarms becomes noise,
    and this desk has already learned that an alarm which fires when nothing is wrong is training to
    ignore the channel.

So the ladder is pinned here, not left to a reading of the code.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from rider_peak_watch import Ladder, open_pnl  # noqa: E402


def kinds(evts):
    return [k for k, _ in evts]


# ── the money conversion ─────────────────────────────────────────────────────
def test_pnl_reproduces_the_real_booked_trade_to_the_penny():
    """★ THE UNIT TEST THAT MATTERS. 13:39→13:50 on 2026-08-19: SHORT 2 @ 29607.50 out at 29470.75,
    booked by the VENUE at exactly $544.00. $2/pt is PER LOT; using the per-position figure by
    mistake is what once turned a "$200 claim" into $100 banked."""
    assert round(open_pnl(29470.75, 29607.50, -1, 2.0), 2) == 544.00


def test_a_long_and_a_short_are_symmetric_and_fees_always_subtract():
    assert round(open_pnl(29707.50, 29607.50, 1, 2.0), 2) == 397.00     # +100pt long
    assert round(open_pnl(29507.50, 29607.50, -1, 2.0), 2) == 397.00    # +100pt short
    assert open_pnl(29607.50, 29607.50, 1, 2.0) == -3.00               # flat = the fee


# ── the arm ──────────────────────────────────────────────────────────────────
def test_nothing_is_sent_below_the_arm():
    lad = Ladder()
    for pnl in (-120, 0, 50, 199.99):
        assert lad.update(pnl) == []


def test_the_arm_fires_exactly_once():
    lad = Ladder()
    assert kinds(lad.update(210)) == ["ARM"]
    assert kinds(lad.update(215)) == []          # still inside the $200 rung
    assert kinds(lad.update(180)) == []          # and never re-arms on the way back up
    assert kinds(lad.update(205)) == []


def test_a_jump_straight_past_several_rungs_does_not_backfill_them():
    """★ A 137-point impulse can cross $200→$380 between two 1Hz ticks. The operator must get ONE
    message, not four."""
    lad = Ladder()
    assert kinds(lad.update(380)) == ["ARM"]
    assert lad.last_rung == 350
    assert kinds(lad.update(390)) == []          # still the $350 rung
    assert kinds(lad.update(401)) == ["RUNG"]


# ── the rungs ────────────────────────────────────────────────────────────────
def test_one_ping_per_fifty_dollar_high_water_mark():
    lad = Ladder()
    lad.update(200)
    got = []
    for pnl in (240, 251, 262, 299, 301, 349, 355):
        got += [d for k, d in lad.update(pnl) if k == "RUNG"]
    assert got == ["250", "300", "350"]


def test_rungs_never_fire_on_the_way_down():
    """★ THE ANTI-MACHINE-GUN PROPERTY. A position chopping across $300 must not ping every crossing."""
    lad = Ladder()
    lad.update(200)
    lad.update(320)
    n = 0
    for pnl in (290, 305, 288, 302, 295, 310, 299, 315):
        n += len([k for k in kinds(lad.update(pnl)) if k == "RUNG"])
    assert n == 0, "re-crossing an old rung is not a new high-water mark"


def test_a_fresh_high_above_the_old_rung_still_pings():
    lad = Ladder()
    lad.update(200)
    lad.update(320)
    for pnl in (290, 305, 299):
        lad.update(pnl)
    assert kinds(lad.update(355)) == ["RUNG"]


# ── the give-back: the "$550 then it started dropping" alert ─────────────────
def test_giveback_fires_once_per_peak_and_rearms_only_on_a_new_high():
    lad = Ladder(giveback_usd=75)
    lad.update(200)
    lad.update(550)
    assert kinds(lad.update(500)) == []               # −$50, inside the threshold
    assert kinds(lad.update(470)) == ["GIVEBACK"]     # −$80
    assert kinds(lad.update(450)) == []               # ★ must NOT repeat on the same peak
    assert kinds(lad.update(400)) == []
    evts = lad.update(600)                            # a new high re-arms it
    assert kinds(evts) == ["RUNG"]
    assert kinds(lad.update(510)) == ["GIVEBACK"]


def test_giveback_can_be_disabled():
    lad = Ladder(giveback_usd=0)
    lad.update(200)
    lad.update(550)
    assert kinds(lad.update(300)) == []


def test_giveback_does_not_fire_before_the_arm():
    """Below $200 the operator is not watching and does not want to be told about noise."""
    lad = Ladder(giveback_usd=50)
    for pnl in (150, 60, 120, 20):
        assert lad.update(pnl) == []


# ── the reset between sessions ───────────────────────────────────────────────
def test_reset_clears_every_latch():
    lad = Ladder()
    lad.update(200)
    lad.update(600)
    lad.update(400)
    lad.reset()
    assert (lad.armed, lad.peak, lad.last_rung, lad.gb_peak, lad.seen) == (False, 0.0, 0.0, 0.0, False)
    assert kinds(lad.update(-50)) == []
    assert kinds(lad.update(260)) == ["ARM"]


def test_the_first_tick_seeds_the_peak_rather_than_counting_as_a_drawdown():
    """Starting mid-move at −$300 must not instantly read as a give-back from $0."""
    lad = Ladder(giveback_usd=75)
    assert lad.update(-300) == []
    assert lad.peak == -300


# ── the boundaries that keep this thing safe ─────────────────────────────────
def test_the_watcher_holds_no_order_path():
    """★ THE INVARIANT. A notifier that dies is a missed message; an actor that dies is a naked
    position. Nothing in this file may reach the broker."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "rider_peak_watch.py")).read()
    for forbidden in ("placeOrder", "StopOrder", "MarketOrder", "ib_async", "cancelOrder", "INTENTS"):
        assert forbidden not in src, f"peak watch must never {forbidden}"


def test_the_tape_is_filtered_by_symbol():
    """★ MD_STREAM IS MULTI-SYMBOL — verified live: bar:MNQ and bar:MGC both publish. Folding MGC
    into an MNQ reader once made ATR read 1848 against a true 15."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "rider_peak_watch.py")).read()
    assert 'body.get("symbol") != SYMBOL' in src
