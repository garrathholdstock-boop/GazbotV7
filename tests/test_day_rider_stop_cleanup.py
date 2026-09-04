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
    """Six exits close a position; each must clean up. A new one added without this is the bug.

    ★2026-08-20 5 -> 7: LADDER_COMPLETE joined when the rider went to 4 lots with a per-lot
    profit ladder, then the PER-LOT MANUAL_CLAIM (one of the four buttons) joined as the seventh.
    Both counts were RAISED only after each new path was given its `cancel_own_stops()` call —
    never to make a red test go green. The per-lot claim cleans up only when it takes the LAST
    lot, which is correct: a stop must outlive a partial exit and die with the position."""
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    reasons = [ln for ln in src.splitlines() if 'out["exit_reason"] = "' in ln]
    assert len(reasons) == 7, f"close paths changed ({len(reasons)}) — wire the new one up"
    assert src.count("await cancel_own_stops(") == 7


# ── ★2026-08-20 SIZE FIELDS MUST GO TO ZERO ON A WHOLE-POSITION CLOSE ──────────────
# On 08-20 the state read `closed: True, lots_open: 2, qty: 2.0` against a venue of ZERO for half
# an hour, and a monitor reading it announced two open lots at a flat book. `lots_open` was added
# for the 4-lot ladder and only the PER-LOT paths decremented it.
def test_whole_position_close_zeroes_the_size_fields():
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "dr_size", "/home/alphabot/gazbot7/src/gazbot7/day_rider.py")
    m = importlib.util.module_from_spec(spec); sys.modules["dr_size"] = m
    try:
        spec.loader.exec_module(m)
    except Exception:
        import pytest; pytest.skip("day_rider needs ib_async to import")
    out = {"lots_open": 2, "qty": 2.0}
    m._zero_size_if_flat(out, None)                 # whole-position close
    assert out["lots_open"] == 0 and out["qty"] == 0.0, "a flat book must report zero size"
    out2 = {"lots_open": 3, "qty": 3.0}
    m._zero_size_if_flat(out2, 1)                   # ONE lot booked — caller owns the decrement
    assert out2["lots_open"] == 3 and out2["qty"] == 3.0, "a partial book must not be zeroed here"


def test_manual_buy_is_checked_before_the_session_latch():
    """A human pressing BUY is not the automatic detector re-entering.

    The once-per-session latch exists to stop `drift` firing twice. On 08-20 it swallowed the
    operator's manual BUY with "already traded this session" — the latch governing a decision it
    was never written for. Manual entry must be evaluated FIRST.
    """
    src = open("/home/alphabot/gazbot7/src/gazbot7/day_rider.py").read()
    # ★2026-08-21 assert the CALL SITE, not a comment string. The first version of this test matched
    # a docstring literal; renaming the helper made it pass/fail for reasons unrelated to the
    # invariant. What matters is that step() invokes the manual entry BEFORE the latch returns.
    call = src.index("await do_manual_entry(_buy")
    latch = src.index('out["note"] = "already traded this session — no re-entry"')
    assert call < latch, "the manual BUY call has fallen below the once-per-session latch"
    # and it must still actually place an order — a gutted helper is worse than no button
    # ★2026-09-04 was `MarketOrder(_side, _q)`. Entries are now marketable LIMITS via place_entry()
    # because the paper engine fabricated a 0.1%-adverse fill on every lot after the first
    # (SESSIONS §387). The invariant this line defends — the button reaches the broker — is
    # unchanged; only the order type is.
    assert "await place_entry(ib, contract, _side, _q" in src, (
        "do_manual_entry no longer places an order")
    # ★2026-09-04 was 7 = 6 closes + the manual ENTRY. The entry moved to place_entry(), which
    # sources the same avgFillPrice AND returns the filled quantity (entries are marketable limits
    # now — SESSIONS §387). The six CLOSE paths are what this line is really guarding.
    assert src.count("await await_fill(") == 6, "a CLOSE path lost its fill-sourced exit"
    assert src.count("await place_entry(") == 2, "an ENTRY path lost its fill-sourced entry"
