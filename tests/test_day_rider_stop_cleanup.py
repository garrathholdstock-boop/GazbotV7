"""The day-rider must take its venue stop down WITH the position — and touch nothing else.

★ WHY. The 600pt venue stop is placed with the entry and nothing ever removed it. On 2026-08-13 the
operator claimed at 14:26 and the stop (orderId 49, SELL 2 STP @ 29424.25) stayed WORKING against a
flat account for two more hours. That is the 08-06 shape: on that date a leftover stop fired with
nothing behind it and OPENED A NAKED SHORT, booked six hours later as a gate trade nobody placed.
eod_flatten cannot clean it up — it runs as clientId 6 and IBKR answers a cross-client cancel with
`Error 10147: not found`, which reads exactly like success.

★★ THE clientId FILTER IS THE SAFETY PROPERTY, NOT AN OPTIMISATION. DUQ191770 is shared with the
tournament, whose per-slot stops are the only thing between it and an unprotected position.
Cancelling those would turn a bookkeeping tidy-up into the worst incident this desk has had.
"""
import asyncio
import sys
import types

sys.path.insert(0, "/home/alphabot/gazbot7/src")

from gazbot7.day_rider import CLIENT_ID, cancel_own_stops  # noqa: E402


class _Order:
    def __init__(self, oid, client, action, otype):
        self.orderId, self.clientId, self.action, self.orderType = oid, client, action, otype


class _Trade:
    def __init__(self, oid, client, action="SELL", otype="STP", symbol="MNQ", status="PreSubmitted"):
        self.order = _Order(oid, client, action, otype)
        self.contract = types.SimpleNamespace(symbol=symbol)
        self.orderStatus = types.SimpleNamespace(status=status)


class _IB:
    def __init__(self, trades):
        self._trades, self.cancelled = trades, []

    async def reqAllOpenOrdersAsync(self):
        return None

    def openTrades(self):
        return list(self._trades)

    def cancelOrder(self, o):
        self.cancelled.append(o.orderId)
        for t in self._trades:
            if t.order.orderId == o.orderId:
                t.orderStatus.status = "Cancelled"


def _run(trades, notify=None):
    ib = _IB(trades)
    n = asyncio.run(cancel_own_stops(ib, "MNQ", notify))
    return ib, n


def test_cancels_our_own_orphan_stop():
    ib, n = _run([_Trade(49, CLIENT_ID)])
    assert n == 1 and ib.cancelled == [49]


def test_NEVER_cancels_the_tournaments_stops():
    """The load-bearing test. clientId 0 is the tournament; its per-slot stops must survive."""
    ib, n = _run([_Trade(1861, 0), _Trade(1862, 0), _Trade(49, CLIENT_ID)])
    assert ib.cancelled == [49], "only OUR order may be cancelled"
    assert n == 1


def test_leaves_other_clients_alone_entirely():
    ib, n = _run([_Trade(70, 5), _Trade(71, 6), _Trade(72, 8)])
    assert ib.cancelled == [] and n == 0


def test_ignores_non_stop_orders():
    # a resting entry limit is not ours to tidy up here
    ib, n = _run([_Trade(80, CLIENT_ID, otype="LMT"), _Trade(81, CLIENT_ID, otype="MKT")])
    assert ib.cancelled == [] and n == 0


def test_covers_trailing_and_stop_limit():
    ib, n = _run([_Trade(82, CLIENT_ID, otype="TRAIL"), _Trade(83, CLIENT_ID, otype="STP LMT")])
    assert sorted(ib.cancelled) == [82, 83] and n == 2


def test_ignores_other_symbols():
    ib, n = _run([_Trade(84, CLIENT_ID, symbol="MGC")])
    assert ib.cancelled == [] and n == 0


def test_already_cancelled_is_not_re_cancelled():
    ib, n = _run([_Trade(85, CLIENT_ID, status="Cancelled"), _Trade(86, CLIENT_ID, status="Filled")])
    assert ib.cancelled == [] and n == 0


def test_a_stop_that_survives_cancellation_PAGES():
    """Silence is what let orderId 49 live for two hours. A refused cancel must be loud."""
    class _Stubborn(_IB):
        def cancelOrder(self, o):
            self.cancelled.append(o.orderId)      # accepted, but the order stays working

    ib = _Stubborn([_Trade(49, CLIENT_ID)])
    pages = []
    asyncio.run(cancel_own_stops(ib, "MNQ", lambda m, critical=False: pages.append((m, critical))))
    assert pages, "an uncancelled stop must page"
    msg, critical = pages[0]
    assert "still" in msg.lower() and "naked" in msg.lower() and critical is True


def test_never_raises_even_if_ib_is_broken():
    """A failed cleanup must not break a flatten that has already completed."""
    class _Broken:
        async def reqAllOpenOrdersAsync(self):
            raise RuntimeError("gateway went away")

    pages = []
    n = asyncio.run(cancel_own_stops(_Broken(), "MNQ",
                                     lambda m, critical=False: pages.append(m)))
    assert n == 0 and pages, "it must fail quietly to the caller but loudly to the operator"


def test_every_close_path_calls_it():
    """Five exits close a position; each must clean up. A new one added without this is the bug."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    reasons = [ln for ln in src.splitlines() if 'out["exit_reason"] = "' in ln]
    assert len(reasons) == 5, f"close paths changed ({len(reasons)}) — wire the new one up"
    assert src.count("await cancel_own_stops(") == 5
