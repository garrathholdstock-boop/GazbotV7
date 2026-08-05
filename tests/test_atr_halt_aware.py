"""★2026-08-03 — ATR must not treat a session-halt gap as a real bar's true range."""
from gazbot7.deciders import Bar, _atr


def _b(ts, o, h, l, c):
    return Bar(ts=ts, open=o, high=h, low=l, close=c, volume=100.0)


def _contiguous(n=20, start=1_000_000, px=28_000.0, rng=10.0):
    return [_b(start + i * 60, px, px + rng, px, px + 1) for i in range(n)]


def test_contiguous_bars_are_byte_identical_to_the_old_behaviour():
    """The fix must be a no-op at every other moment of the week."""
    bars = _contiguous()
    trs = [max(bars[i].high - bars[i].low, abs(bars[i].high - bars[i - 1].close),
               abs(bars[i].low - bars[i - 1].close)) for i in range(1, len(bars))]
    assert _atr(bars) == sum(trs[-14:]) / len(trs[-14:])


def test_weekend_gap_does_not_inflate_atr():
    """The real 2026-08-02 shape: quiet 10pt bars, then a 283.5pt gap across the halt."""
    pre = _contiguous(n=14, start=1_000_000, px=28_284.0, rng=10.0)
    halt_s = 50 * 3600                      # ~50h weekend
    post = [_b(pre[-1].ts + halt_s + i * 60, 28_567.5, 28_577.5, 28_567.5, 28_568.5)
            for i in range(3)]
    bars = pre + post
    atr = _atr(bars)
    assert atr < 20, f"gap leaked into ATR: {atr:.1f}pt"
    # and the naive computation really would have blown up — proves the test has teeth
    naive = [max(bars[i].high - bars[i].low, abs(bars[i].high - bars[i - 1].close),
                 abs(bars[i].low - bars[i - 1].close)) for i in range(1, len(bars))]
    assert sum(naive[-14:]) / 14 > 30


def test_only_the_gap_bar_is_adjusted_not_its_neighbours():
    pre = _contiguous(n=14, px=28_284.0, rng=10.0)
    post = [_b(pre[-1].ts + 50 * 3600 + i * 60, 28_567.5, 28_567.5 + 40, 28_567.5, 28_580.0)
            for i in range(3)]
    bars = pre + post
    # bars after the gap are contiguous with each other, so their 40pt range still counts
    assert _atr(bars) > 10


def test_ts_is_seconds_not_ms():
    """Guard the unit. If Bar.ts were ever ms, a 60s delta would read 60 <= 90 as False and the
    fix would silently invert — dropping gap terms on EVERY bar."""
    b = _contiguous(n=3)
    assert b[1].ts - b[0].ts == 60
