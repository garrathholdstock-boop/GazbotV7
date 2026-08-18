"""A FULL bar ring must still step the sim.

★★★2026-08-18. `mb` is a deque(maxlen=bar_lookback) and `run()` WARMS it to capacity before the
loop starts. The gate for stepping the gold sim was `len(mb.bars()) > _n_before` — i.e. "did the bar
COUNT grow" — which on a pre-filled fixed-size ring is `120 > 120`: false on the first message and
every one after, forever.

So `gazbot7-shadow-mgc` could NEVER fire. It didn't: 0 sims in 3 days, while the same gate replayed
459 fires on the same week of tape. The service was `active`, burning 1h45m of CPU, logging nothing,
raising nothing — it folded bars faithfully and stepped the sim zero times.

⚠ THIS IS THE SECOND "the gate could never have fired" IN THIS SERVICE IN A WEEK (08-15 audit:
bar_lookback=60 against a look_min needing 61). The shape to distrust is a LIVENESS PROXY that is
only true during warm-up.
"""
import os
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gazbot7.agg import MinuteBars  # noqa: E402


def test_warm_fills_the_ring_to_capacity():
    """The precondition that made the count test dead on arrival."""
    mb = MinuteBars(5)
    for i in range(200):
        mb.fold(1_700_000_000 + i * 5, 100, 101, 99, 100, 1)
    assert len(mb.bars()) == 5, "the ring is bounded — this is why a count can stop growing"


def test_a_full_ring_still_advances_its_newest_timestamp():
    """★ THE FIX. The count saturates; the newest timestamp does not."""
    mb = MinuteBars(3)
    for i in range(300):
        mb.fold(1_700_000_000 + i * 5, 100, 101, 99, 100, 1)
    saturated = len(mb.bars())
    ts_before = mb.bars()[-1].ts
    for i in range(300, 324):                      # two more whole minutes of 5s bars
        mb.fold(1_700_000_000 + i * 5, 100, 101, 99, 100, 1)
    assert len(mb.bars()) == saturated, "count cannot grow — the OLD test's whole failure"
    assert mb.bars()[-1].ts != ts_before, "timestamp MUST advance — the new test's whole point"


def test_the_old_count_predicate_is_dead_on_a_warmed_ring():
    """Pin the actual defect so it cannot be reintroduced as a 'simplification'."""
    mb = MinuteBars(3)
    for i in range(300):                            # stand in for warm()
        mb.fold(1_700_000_000 + i * 5, 100, 101, 99, 100, 1)
    fired_count, fired_ts = 0, 0
    for i in range(300, 372):
        n_before = len(mb.bars())
        ts_before = mb.bars()[-1].ts if mb.bars() else None
        mb.fold(1_700_000_000 + i * 5, 100, 101, 99, 100, 1)
        if len(mb.bars()) > n_before:               # the OLD predicate
            fired_count += 1
        if mb.bars() and mb.bars()[-1].ts != ts_before:   # the NEW predicate
            fired_ts += 1
    assert fired_count == 0, "the old predicate must be provably dead on a warmed ring"
    assert fired_ts >= 5, f"the new predicate must step once per completed minute, got {fired_ts}"


def test_an_empty_ring_does_not_crash_the_predicate():
    """Cold start: no bars yet, so `_ts_before` is None and the first fold must still step."""
    mb = MinuteBars(3)
    assert mb.bars() == []
    ts_before = mb.bars()[-1].ts if mb.bars() else None
    assert ts_before is None
    for i in range(24):
        mb.fold(1_700_000_000 + i * 5, 100, 101, 99, 100, 1)
    assert mb.bars() and mb.bars()[-1].ts != ts_before


def test_a_deque_is_still_what_backs_it():
    """If MinuteBars ever stops being bounded the fix is harmless, but the REASON changes."""
    mb = MinuteBars(4)
    assert isinstance(mb._bars, deque) and mb._bars.maxlen == 4
