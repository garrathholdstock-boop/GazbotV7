"""The hard flat must never fire into a CLOSED venue, and must never send a SECOND order.

★★★ THE 2026-09-06 SUNDAY RUNAWAY FLATTEN. `hard_flat_window()` tests minute-of-day and nothing
else, so at 20:40Z on a SUNDAY the rider entered its flatten window against a market that would not
open until 22:00Z. A market order into a shut venue does not fail — it QUEUES. No fill comes back,
so our book still reads LONG 4, so the next minute's tick places the same SELL 4 again. Eleven got
through a flapping gateway. At the 22:00Z reopen all eleven filled inside one second:

    11 x SELL 4 = 44 lots   against a venue holding LONG 4   ->   the account was SHORT 40

Nobody claimed it, the dashboard showed a FALSE +$250 off the phantom book, and it cost about
-$8,400 before it was flattened by hand on 09-07.

★ TWO INDEPENDENT DEFECTS, and either one alone would have stopped it:
    1. no day-of-week guard  -> venue_closed()
    2. no idempotency        -> own_working_flatten()
Both are tested here. ⚠ The second is the one that generalises: an UNFILLED order is not a FAILED
order, and a retry that re-places rather than waiting turns one correct decision into a pile.

⚠ THE DAILY HALT IS THE SAME BUG WITH A SHORTER FUSE — the flat window runs to 22:00 but the venue
shuts at 21:00, so 21:00-22:00 on an ordinary Monday would queue up to 60 orders. Covered below.
"""
import asyncio
import sys
import types

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.day_rider import (  # noqa: E402
    CLIENT_ID, FLAT_UTC_MIN, HALT_UTC_MIN, REOPEN_UTC_MIN,
    hard_flat_window, own_working_flatten, venue_closed,
)

MON, TUE, THU, FRI, SAT, SUN = 0, 1, 3, 4, 5, 6


def _m(h, m=0):
    return h * 60 + m


# ── 1. THE CLOCK ────────────────────────────────────────────────────────────

def test_the_incident_minute_is_closed():
    """20:40Z Sunday — the exact tick that started it. This is the whole fix in one assertion."""
    assert hard_flat_window(FLAT_UTC_MIN) is True, "still inside the flatten window (unchanged)"
    assert venue_closed(SUN, FLAT_UTC_MIN) is True, "the venue was SHUT and we queued 11 orders"


def test_every_minute_of_that_sunday_window_is_closed():
    """No survivable minute. If ANY minute here read open, the loop could start again."""
    for mod in range(FLAT_UTC_MIN, REOPEN_UTC_MIN):
        assert venue_closed(SUN, mod) is True, f"Sunday {mod//60:02d}:{mod%60:02d}Z read OPEN"


def test_the_nightly_halt_is_closed_on_an_ordinary_weekday():
    """21:00-22:00 Mon-Thu: inside the flatten window but past the CME close — up to 60 orders."""
    for dow in (MON, TUE, THU):
        for mod in range(HALT_UTC_MIN, REOPEN_UTC_MIN):
            assert venue_closed(dow, mod) is True, f"dow={dow} {mod//60:02d}:{mod%60:02d}Z read OPEN"


def test_the_real_flatten_window_is_still_open_and_still_works():
    """★ THE GUARD MUST NOT EAT THE FLATTEN IT PROTECTS. 20:40-21:00 Mon-Fri is a live market and
    the ~20 automatic retries there are the entire reason the clock was moved off 21:00."""
    for dow in (MON, TUE, THU, FRI):
        for mod in range(FLAT_UTC_MIN, HALT_UTC_MIN):
            assert venue_closed(dow, mod) is False, f"dow={dow} {mod//60:02d}:{mod%60:02d}Z read SHUT"


def test_the_weekend_boundaries():
    assert venue_closed(FRI, _m(20, 59)) is False, "Friday 20:59Z still trades"
    assert venue_closed(FRI, _m(21, 0)) is True, "Friday 21:00Z is the weekly close"
    assert venue_closed(SAT, _m(3)) is True and venue_closed(SAT, _m(23)) is True
    assert venue_closed(SUN, _m(21, 59)) is True, "one minute before the reopen"
    assert venue_closed(SUN, _m(22, 0)) is False, "the 22:00Z Sunday reopen"
    assert venue_closed(MON, _m(2)) is False, "Monday small hours trade — the session is continuous"
    assert venue_closed(MON, _m(14, 30)) is False, "the US open"


# ── 2. IDEMPOTENCY ──────────────────────────────────────────────────────────

class _Order:
    def __init__(self, oid, client, action, otype, qty=4):
        self.orderId, self.clientId = oid, client
        self.action, self.orderType, self.totalQuantity = action, otype, qty


class _Trade:
    def __init__(self, oid, client, action="SELL", otype="MKT", symbol="MNQ",
                 status="PreSubmitted"):
        self.order = _Order(oid, client, action, otype)
        self.contract = types.SimpleNamespace(symbol=symbol)
        self.orderStatus = types.SimpleNamespace(status=status)


class _IB:
    def __init__(self, trades):
        self._trades = trades

    async def reqAllOpenOrdersAsync(self):
        return None

    def openTrades(self):
        return list(self._trades)


def _find(trades):
    return asyncio.run(own_working_flatten(_IB(trades), "MNQ"))


def test_our_own_queued_flatten_is_found_so_it_is_not_re_sent():
    """THE REGRESSION CASE. This is minute two of 2026-09-06: order one is still working."""
    t = _find([_Trade(101, CLIENT_ID)])
    assert t is not None and t.order.orderId == 101


def test_nothing_working_means_place():
    assert _find([]) is None


def test_a_filled_or_cancelled_order_does_not_block_the_next_flatten():
    """★ A DEAD ORDER MUST NOT BE ADOPTED — that would be the inverse bug: never flattening."""
    assert _find([_Trade(1, CLIENT_ID, status="Filled")]) is None
    assert _find([_Trade(2, CLIENT_ID, status="Cancelled")]) is None
    assert _find([_Trade(3, CLIENT_ID, status="Inactive")]) is None


def test_the_tournaments_market_order_is_never_adopted():
    """⚠ SHARED ACCOUNT. Adopting another desk's order would make us wait on a fill that closes
    nothing of ours, and carry the position through the halt. clientId is the only tag there is."""
    assert _find([_Trade(77, CLIENT_ID + 1)]) is None
    assert _find([_Trade(77, 0)]) is None


def test_our_own_stop_is_not_mistaken_for_a_flatten():
    """The 600pt venue stop sits WORKING for the whole trade; adopting it would block every
    flatten for the life of the position. Only a market order is a flatten."""
    assert _find([_Trade(49, CLIENT_ID, otype="STP")]) is None


def test_another_symbol_is_ignored():
    assert _find([_Trade(5, CLIENT_ID, symbol="MGC")]) is None


def test_the_incident_shape_end_to_end():
    """Eleven ticks, one position. With BOTH guards live, exactly ONE order can ever exist.

    Minute 1 places (had the venue been open); minutes 2-11 find it working and wait. And on the
    actual Sunday, venue_closed() means minute 1 never places at all — 44 lots become 0.
    """
    working = []
    for minute in range(11):
        mod = FLAT_UTC_MIN + minute
        if venue_closed(SUN, mod):
            continue                                  # guard 1: nothing goes out on a Sunday
        if _find(working) is None:                    # guard 2: only if none is already live
            working.append(_Trade(200 + minute, CLIENT_ID))
    assert working == [], "an order reached a shut venue on the incident's own timeline"

    working = []
    for minute in range(11):                          # the same eleven ticks on a TRADING day
        mod = FLAT_UTC_MIN + minute
        if venue_closed(MON, mod):
            continue
        if _find(working) is None:
            working.append(_Trade(300 + minute, CLIENT_ID))
    assert len(working) == 1, f"the flatten sent {len(working)} orders for one position"
