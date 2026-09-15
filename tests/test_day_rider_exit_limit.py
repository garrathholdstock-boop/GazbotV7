"""Multi-lot EXITS go in on a marketable LIMIT that ESCALATES TO MARKET.

★★★ THE EVENT (2026-09-15). The operator claimed a 4-lot position while his screen showed -$115.
The desk booked -$304.50. The fills:

    08:30:58  SELL 1 @ 29291.25     <- real; the tape was 29290-29292
    08:30:58  SELL 3 @ 29262.00     <- 29.25pt worse = 0.0999% of price

0.1% adverse on every lot beyond the first is the IBKR paper engine's fabricated-fill signature.
29262.00 NEVER PRINTED: the lowest trade in the surrounding six minutes was 29274.75. $175.50 of
that loss is a price that does not exist, and `sweep.py`'s fill_vs_book check caught it unprompted.

★★ THE MECHANISM. A limit cannot fill through its own price, so the band is a HARD CEILING on the
fabrication. The same morning's 4-lot ENTRY proves it: it spread 5.5pt across its lots — which is
ENTRY_LIMIT_BAND_PT — not 0.1%.

⚠⚠⚠ THE HAZARD, AND WHY IT IS CLOSED. place_entry() argued exits must stay on market orders:
"an exit that does not fill is unbounded risk." That is CORRECT, and place_exit() does not overturn
it — it removes the premise by cancelling the resting limit and MARKETing the remainder. Every test
below exists to keep that escape hatch working; a limit that could hang would be strictly worse
than the fabrication it prevents.
"""
import asyncio
import sys

sys.path.insert(0, "/home/alphabot/gazbot7/src")

import gazbot7.day_rider as dr


class _Status:
    def __init__(self, filled, avg, status):
        self.filled, self.avgFillPrice, self.status = filled, avg, status


class _Trade:
    def __init__(self, filled, avg, status="Filled"):
        self.orderStatus = _Status(filled, avg, status)
        self.order = object()


class _IB:
    """Returns a scripted trade per placeOrder call, and records what was placed."""

    def __init__(self, *trades):
        self.placed, self.cancelled, self._t = [], [], list(trades)

    def placeOrder(self, contract, order):
        self.placed.append(order)
        return self._t[min(len(self.placed) - 1, len(self._t) - 1)]

    def cancelOrder(self, order):
        self.cancelled.append(order)


class _Notes:
    def __init__(self):
        self.sent = []

    def __call__(self, msg, critical=False):
        self.sent.append((msg, critical))


def _run(c):
    return asyncio.run(c)


def _kind(order):
    return type(order).__name__


def test_multi_lot_exit_places_a_limit_not_a_market_order():
    """★ THE FIX. 4 lots must not go out as a market order — that is the order that was fabricated."""
    ib = _IB(_Trade(4, 29291.0))
    px = _run(dr.place_exit(ib, object(), "SELL", 4, 29291.25, "MNQ", what="t"))
    assert len(ib.placed) == 1
    assert _kind(ib.placed[0]) == "LimitOrder", f"expected a LimitOrder, got {_kind(ib.placed[0])}"
    assert px == 29291.0


def test_the_limit_is_priced_THROUGH_the_touch_on_both_sides():
    """★ A limit priced AT the market rests there. It must cross, on both sides, or the escalation
    becomes the normal path and nothing is gained."""
    for side, ref, want in (("SELL", 29291.25, 29281.25), ("BUY", 29291.25, 29301.25)):
        ib = _IB(_Trade(4, ref))
        _run(dr.place_exit(ib, object(), side, 4, ref, "MNQ", what="t"))
        lmt = ib.placed[0].lmtPrice
        assert lmt == want, f"{side}: limit {lmt} should be {want} ({dr.EXIT_LIMIT_BAND_PT}pt through)"
        if side == "SELL":
            assert lmt < ref, "a SELL limit ABOVE the market would never fill"
        else:
            assert lmt > ref, "a BUY limit BELOW the market would never fill"


def test_the_band_caps_the_fabrication_at_the_real_events_numbers():
    """★★ THE MEASURED CLAIM, pinned. The real exit was fabricated 29.25pt away on 3 lots = $175.50.
    Under the band the SAME exit cannot lose more than the band on those lots."""
    ref = 29291.25
    ib = _IB(_Trade(4, 29281.25))
    _run(dr.place_exit(ib, object(), "SELL", 4, ref, "MNQ", what="t"))
    worst = ref - ib.placed[0].lmtPrice
    assert worst == dr.EXIT_LIMIT_BAND_PT
    assert worst * 3 * 2.0 < 175.50, "the band must cost less than the fabrication it replaces"


def test_a_partial_fill_CANCELS_and_MARKETS_the_remainder():
    """★★★ THE ESCAPE HATCH. This is the whole answer to 'an unfilled exit is unbounded risk'.
    The position MUST end up closed."""
    ib = _IB(_Trade(1, 29291.25, "Submitted"), _Trade(3, 29262.0))
    notes = _Notes()
    px = _run(dr.place_exit(ib, object(), "SELL", 4, 29291.25, "MNQ", what="t", notify=notes))
    assert _kind(ib.placed[0]) == "LimitOrder"
    assert ib.cancelled, "the resting limit was never cancelled — that is the 08-06 orphan shape"
    assert _kind(ib.placed[1]) == "MarketOrder", "the remainder must go out at MARKET"
    assert ib.placed[1].totalQuantity == 3, "only the UNFILLED lots may be re-sent"
    # weighted, not the mean of two prices
    assert abs(px - (29291.25 * 1 + 29262.0 * 3) / 4) < 1e-6
    assert any("MARKET" in m for m, _ in notes.sent), "an escalation must be visible"


def test_one_lot_is_still_a_plain_market_order():
    """⚠ The fabrication cannot reach a single lot — the first lot of every multi-lot order on
    2026-09-15 filled at the true touch. Unchanged by design."""
    ib = _IB(_Trade(1, 29291.25))
    _run(dr.place_exit(ib, object(), "SELL", 1, 29291.25, "MNQ", what="t"))
    assert _kind(ib.placed[0]) == "MarketOrder"


def test_no_reference_price_EXITS_ANYWAY():
    """⚠⚠ THE ASYMMETRY WITH place_entry(). An entry with no reference price REFUSES — costing a
    re-press. An exit must never refuse: refusing to close is the unbounded failure."""
    ib = _IB(_Trade(4, 29291.25))
    px = _run(dr.place_exit(ib, object(), "SELL", 4, 0.0, "MNQ", what="t"))
    assert _kind(ib.placed[0]) == "MarketOrder", "a priceless exit must still GO"
    assert px == 29291.25


def test_zero_lots_places_nothing():
    ib = _IB(_Trade(0, 0.0))
    _run(dr.place_exit(ib, object(), "SELL", 0, 29291.25, "MNQ", what="t"))
    assert not ib.placed


def test_a_cancel_that_throws_does_not_kill_the_exit():
    """⚠ never die on a cancel — the remainder still has to go."""
    class _Bad(_IB):
        def cancelOrder(self, order):
            raise RuntimeError("TWS said no")

    ib = _Bad(_Trade(1, 29291.25, "Submitted"), _Trade(3, 29262.0))
    notes = _Notes()
    px = _run(dr.place_exit(ib, object(), "SELL", 4, 29291.25, "MNQ", what="t", notify=notes))
    assert _kind(ib.placed[1]) == "MarketOrder"
    assert px > 0
    assert any("CHECK TWS" in m and c for m, c in notes.sent)
