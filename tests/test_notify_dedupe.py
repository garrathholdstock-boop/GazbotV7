"""Repeat-suppression for operator alerts.

★★2026-08-14 WHY THIS EXISTS. The day-rider correctly stands down when the venue holds a position it
did not open — the 08-06 ownership gate working as designed. But that branch is reached on EVERY tick
outside its window, so with the tournament legitimately short the operator received the identical
message every minute for hours, while `desk_reconcile` was independently confirming
`venue -2 = tournament -2 + rider +0, unaccounted +0`.

Telegram is where CRITICAL desk alarms land. Training the operator to swipe past a benign repeat
trains them to swipe past a naked position. Steady state must be SILENT so that CHANGE is LOUD.

The load-bearing property is that this layer FAILS OPEN: suppression may only ever be the result of a
successful positive check that the same thing was said recently. Anything else sends.
"""
from datetime import UTC, datetime, timedelta

from gazbot7.notify import dedupe_clear, dedupe_ok

T0 = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
MSG = "DAY RIDER: venue holds -2 MNQ that is NOT mine"


def _p(tmp_path):
    return str(tmp_path / "dedupe.json")


def test_first_send_goes_through_then_repeats_are_suppressed(tmp_path):
    p = _p(tmp_path)
    assert dedupe_ok("k", MSG, now=T0, path=p) is True
    for i in range(1, 60):                       # a full hour of 60s ticks
        assert dedupe_ok("k", MSG, now=T0 + timedelta(minutes=i), path=p) is False


def test_cooldown_expiry_lets_it_speak_again(tmp_path):
    p = _p(tmp_path)
    assert dedupe_ok("k", MSG, cooldown_s=3600, now=T0, path=p) is True
    assert dedupe_ok("k", MSG, cooldown_s=3600, now=T0 + timedelta(minutes=59), path=p) is False
    assert dedupe_ok("k", MSG, cooldown_s=3600, now=T0 + timedelta(minutes=61), path=p) is True


def test_a_changed_message_alarms_immediately(tmp_path):
    """THE SAFETY PROPERTY. These alarms carry live numbers, so the position going -2 -> -4 must
    NOT hide behind a running cooldown. A dedupe that swallowed a size change would be worse than
    no dedupe at all."""
    p = _p(tmp_path)
    assert dedupe_ok("k", "venue holds -2 MNQ", now=T0, path=p) is True
    assert dedupe_ok("k", "venue holds -2 MNQ", now=T0 + timedelta(seconds=60), path=p) is False
    assert dedupe_ok("k", "venue holds -4 MNQ", now=T0 + timedelta(seconds=61), path=p) is True


def test_clear_rearms_so_a_new_occurrence_is_never_swallowed(tmp_path):
    """A cooldown must suppress a CONTINUING state, never a fresh occurrence of one. The rider
    clears the key the moment the venue goes flat."""
    p = _p(tmp_path)
    assert dedupe_ok("k", MSG, now=T0, path=p) is True
    dedupe_clear("k", path=p)                    # venue went flat
    assert dedupe_ok("k", MSG, now=T0 + timedelta(seconds=60), path=p) is True


def test_keys_do_not_interfere(tmp_path):
    p = _p(tmp_path)
    assert dedupe_ok("a", MSG, now=T0, path=p) is True
    assert dedupe_ok("b", MSG, now=T0, path=p) is True
    assert dedupe_ok("a", MSG, now=T0, path=p) is False


def test_corrupt_store_FAILS_OPEN(tmp_path):
    """A dedupe store that suppressed an alarm because its own JSON was unreadable would be the
    instrument-that-reports-healthy failure this desk keeps meeting — the alarm lost, and nothing
    saying so. Garbage in must mean SEND."""
    p = _p(tmp_path)
    open(p, "w").write("{not json at all")
    assert dedupe_ok("k", MSG, now=T0, path=p) is True


def test_unwritable_path_FAILS_OPEN(tmp_path):
    """Can't record the send? Then send. Never trade an alarm for bookkeeping."""
    assert dedupe_ok("k", MSG, now=T0, path="/nonexistent-dir-xyz/dedupe.json") is True


def test_a_store_holding_junk_for_our_key_fails_open(tmp_path):
    p = _p(tmp_path)
    open(p, "w").write('{"k": "not-a-dict"}')
    assert dedupe_ok("k", MSG, now=T0, path=p) is True


def test_clock_going_backwards_does_not_suppress(tmp_path):
    """A negative age is nonsense — a box whose clock stepped back must not go quiet for hours."""
    p = _p(tmp_path)
    assert dedupe_ok("k", MSG, now=T0, path=p) is True
    assert dedupe_ok("k", MSG, now=T0 - timedelta(hours=2), path=p) is True


def test_clear_of_an_unknown_key_is_harmless(tmp_path):
    dedupe_clear("never-seen", path=_p(tmp_path))


# ── the rider's signature contract ───────────────────────────────────────────
def test_rider_signature_ignores_size_but_not_direction(tmp_path):
    """★2026-08-14 observed live. The first cut keyed the dedupe on the full message, which carries
    `net` — so when the tournament closed a lot at 12:12Z (-2 -> -1) it re-alarmed, and it would have
    done so on every scale-in and scale-out all session. The rider's decision is IDENTICAL at -1 and
    -2, and size correctness belongs to desk_reconcile (`venue == tournament + rider`, every 30s).
    So the signature carries direction and ownership, never magnitude."""
    p = _p(tmp_path)

    def sig(net, entered=False):
        return f"unowned {'SHORT' if net < 0 else 'LONG'} present, entered={entered}"

    assert dedupe_ok("k", sig(-2), now=T0, path=p) is True
    assert dedupe_ok("k", sig(-1), now=T0 + timedelta(minutes=1), path=p) is False   # resize: quiet
    assert dedupe_ok("k", sig(-4), now=T0 + timedelta(minutes=2), path=p) is False   # resize: quiet
    assert dedupe_ok("k", sig(+2), now=T0 + timedelta(minutes=3), path=p) is True    # FLIP: news
