"""MinuteBars — the shared 5s→1m aggregator both the live desk and shadow use."""

from __future__ import annotations

from gazbot7.agg import MinuteBars


def _feed(mb: MinuteBars, start_min: int, minutes: int, per_min: int = 12) -> None:
    """Feed `minutes` complete minutes of `per_min` 5s bars each, rising close."""
    px = 100.0
    for mi in range(minutes):
        base = (start_min + mi) * 60
        for j in range(per_min):
            ts = base + j * 5
            px += 0.25
            mb.fold(ts, px, px + 0.5, px - 0.5, px, 10.0)


def test_folds_5s_into_completed_minutes():
    mb = MinuteBars(maxlen=60)
    _feed(mb, start_min=1000, minutes=3)
    # 3 minutes fed, but the 3rd is still forming → only 2 completed bars
    bars = mb.bars()
    assert len(bars) == 2
    assert bars[0].ts == 1000 * 60
    assert bars[1].ts == 1001 * 60


def test_ohlc_aggregation_within_a_minute():
    mb = MinuteBars(maxlen=60)
    base = 500 * 60
    mb.fold(base + 0, 100.0, 101.0, 99.0, 100.5, 5.0)
    mb.fold(base + 5, 100.5, 103.0, 100.0, 102.0, 7.0)
    mb.fold(base + 10, 102.0, 102.5, 98.0, 99.5, 3.0)
    mb.fold((501 * 60), 99.5, 99.5, 99.5, 99.5, 1.0)  # roll to next minute → finalise
    bars = mb.bars()
    assert len(bars) == 1
    b = bars[0]
    assert b.open == 100.0       # first open
    assert b.high == 103.0       # max high
    assert b.low == 98.0         # min low
    assert b.close == 99.5       # last close
    assert b.volume == 15.0      # summed volume


def test_out_of_order_bar_ignored():
    mb = MinuteBars(maxlen=60)
    _feed(mb, start_min=200, minutes=2)
    before = mb.bars()[0]
    mb.fold(150 * 60, 5.0, 5.0, 5.0, 5.0, 99.0)  # stale minute — must not corrupt
    after = mb.bars()[0]
    assert after == before


def test_maxlen_evicts_oldest():
    mb = MinuteBars(maxlen=3)
    _feed(mb, start_min=0, minutes=10)
    bars = mb.bars()
    assert len(bars) == 3  # only the last 3 completed minutes retained


def test_fresh_tracks_last_bar():
    mb = MinuteBars(maxlen=60)
    mb.fold(1000 * 60, 100.0, 100.0, 100.0, 100.0, 1.0)
    last_ms = 1000 * 60 * 1000
    assert mb.fresh(last_ms + 10_000, stale_ms=30_000) is True
    assert mb.fresh(last_ms + 40_000, stale_ms=30_000) is False


def test_fresh_false_before_any_bar():
    mb = MinuteBars(maxlen=60)
    assert mb.fresh(123_456, stale_ms=30_000) is False
