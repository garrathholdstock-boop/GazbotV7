"""Live glue — the pure fill translation + config defaults."""

from __future__ import annotations

from types import SimpleNamespace

import eventkit

from gazbot7.broker_adapter import IBBrokerAdapter, execution_to_fill, stop_limit_price
from gazbot7.config import RunConfig
from gazbot7.ticks import tick_for


class _FakeIB:
    def __init__(self):
        self.execDetailsEvent = eventkit.Event()
        self.orderStatusEvent = eventkit.Event()

    def placeOrder(self, contract, order):
        return SimpleNamespace(order=order, contract=contract,
                               orderStatus=SimpleNamespace(status="PreSubmitted"))


def _status(ref, status):
    return SimpleNamespace(order=SimpleNamespace(orderRef=ref), orderStatus=SimpleNamespace(status=status))


def _exec(execId="e1", side="BOT", shares=2, price=29950.0):
    return SimpleNamespace(execId=execId, side=side, shares=shares, price=price)


def test_bot_maps_to_buy():
    f = execution_to_fill(_exec(side="BOT"), order_ref="o1", symbol="MNQ", time_iso="2026-07-15T13:00:00+00:00")
    assert f.side == "BUY"
    assert f.exec_id == "e1" and f.order_id == "o1" and f.qty == 2.0 and f.price == 29950.0


def test_sld_maps_to_sell():
    f = execution_to_fill(_exec(side="SLD"), order_ref="o1", symbol="MNQ", time_iso="t")
    assert f.side == "SELL"


def test_stop_limit_price_is_on_the_fillable_side():
    # 2026-07-22: a plain STP let IBKR attach a toothless limit on the WRONG side. Our explicit limit
    # must sit PAST the trigger on the side that fills: SELL below, BUY above.
    tk = tick_for("MNQ")
    assert stop_limit_price(29120.25, "SELL", tk) < 29120.25   # long protection → sell below trigger
    assert stop_limit_price(29131.5, "BUY", tk) > 29131.5      # short protection → buy above trigger


def test_place_stop_sends_a_fillable_stop_limit():
    ib = _FakeIB()
    a = IBBrokerAdapter(ib, contract=SimpleNamespace(), symbol="MNQ", on_fill=lambda f: None)
    coid = a.place_stop(symbol="MNQ", side="SELL", qty=1, stop_price=29120.25)
    order = a._trades[coid].order
    assert order.orderType == "STP LMT"                       # explicit limit, not a bare STP
    assert order.auxPrice == 29120.25                         # trigger preserved (guard reads this)
    assert order.lmtPrice < order.auxPrice                    # limit BELOW trigger → fills (not toothless)
    assert order.tif == "GTC" and order.orderRef == coid


def test_stop_rests_on_the_stop_contract_not_the_entry_contract():
    # 2026-07-27: IBKR won't fire a resting stop's trigger on the continuous ContFuture (stuck
    # PreSubmitted/whyHeld='trigger' → STOP_UNFILLED). Stops must rest on the CONCRETE front-month
    # Future; entries/exits stay on the (marketable) ContFuture.
    ib = _FakeIB()
    entry_c = SimpleNamespace(kind="ContFuture")
    stop_c = SimpleNamespace(kind="Future")
    a = IBBrokerAdapter(ib, contract=entry_c, symbol="MNQ", on_fill=lambda f: None, stop_contract=stop_c)
    scoid = a.place_stop(symbol="MNQ", side="SELL", qty=1, stop_price=29120.25)
    assert a._trades[scoid].contract is stop_c                # stop → concrete Future
    a.place(SimpleNamespace(order_type="MKT", side="SELL", qty=1, limit_price=None,
                            tif=None, client_order_id="x1"))
    assert a._trades["x1"].contract is entry_c                # entry/exit → ContFuture


def test_stop_contract_defaults_to_entry_contract():
    # back-compat: no stop_contract → stops rest on the same contract as before.
    ib = _FakeIB()
    c = SimpleNamespace(kind="only")
    a = IBBrokerAdapter(ib, contract=c, symbol="MNQ", on_fill=lambda f: None)
    scoid = a.place_stop(symbol="MNQ", side="SELL", qty=1, stop_price=29120.25)
    assert a._trades[scoid].contract is c


def test_missing_order_ref_is_unknown():
    f = execution_to_fill(_exec(), order_ref=None, symbol="MNQ", time_iso="t")
    assert f.order_id == "unknown"


def test_stop_event_pokes_only_on_dead_protective_stop():
    ib = _FakeIB()
    pokes = []
    ad = IBBrokerAdapter(ib, contract=object(), symbol="MNQ", on_fill=lambda f: None,
                         on_stop_event=lambda coid, status: pokes.append((coid, status)))
    coid = ad.place_stop(symbol="MNQ", side="SELL", qty=1, stop_price=29478.0)
    ib.orderStatusEvent.emit(_status(coid, "Cancelled"))        # dead stop → poke
    ib.orderStatusEvent.emit(_status(coid, "PreSubmitted"))     # live → no poke
    ib.orderStatusEvent.emit(_status("v7-mnq-000001", "Cancelled"))  # not a stop → no poke
    assert pokes == [(coid, "Cancelled")]


def test_config_default_is_dry_run():
    c = RunConfig()
    assert c.place_live is False  # SAFE default — no live orders until cutover
    assert c.symbol == "MNQ" and c.client_id == 7 and c.port == 4002


# ── 2026-08-07 REGRESSION: the orphan sweep ───────────────────────────────────────────────────
# GTC stops 1505/1506 rested ~2000pt from the market for DAYS, uncancellable by any client, and by
# 14:48 the restarted desk had re-minted stp-000001/2 for LIVE stops — two orders sharing a ref,
# on a desk that attributes fills BY REF. Root cause: `_stop_seq` restarts at 0 and the coid->Trade
# map is in-memory, so a restarted desk can neither recognise nor cancel its own leftovers.

class _SweepOrder:
    def __init__(self, ref): self.orderRef = ref


class _SweepTrade:
    def __init__(self, ref): self.order = _SweepOrder(ref)


class _SweepIB:
    def __init__(self, refs): self._refs = refs; self.cancelled = []
    def openTrades(self): return [_SweepTrade(r) for r in self._refs]
    def cancelOrder(self, order): self.cancelled.append(order.orderRef)


def _adapter(refs):
    from gazbot7.broker_adapter import IBBrokerAdapter
    a = IBBrokerAdapter.__new__(IBBrokerAdapter)      # bypass __init__ (needs a live gateway)
    a._ib = _SweepIB(refs); a._trades = {}; a._stop_seq = 0
    return a


def test_sweep_cancels_unowned_stops_and_keeps_owned_ones():
    a = _adapter(["stp-000001", "stp-000002", "stp-000009"])
    out = a.adopt_and_sweep({"stp-000009"})           # only 9 belongs to a live slot
    assert sorted(a._ib.cancelled) == ["stp-000001", "stp-000002"]
    assert "stp-000009" not in a._ib.cancelled, "cancelled a stop a live slot depends on"
    assert out["cancelled"] == 2


def test_sweep_never_touches_another_desks_order():
    """The day-rider's venue stop carries orderRef '' — it must be invisible to the sweep."""
    a = _adapter(["", "manual-thing", "stp-000001"])
    a.adopt_and_sweep(set())
    assert a._ib.cancelled == ["stp-000001"], "swept an order that was not ours"


def test_sweep_bumps_the_sequence_past_resting_refs():
    """The collision fix: never re-mint a ref that is still alive at the venue."""
    a = _adapter(["stp-000001", "stp-000047"])
    out = a.adopt_and_sweep(set())
    assert a._stop_seq >= 47, "sequence would re-mint a ref still resting at IBKR"
    assert out["stop_seq"] >= 47


def test_sweep_makes_pre_restart_orders_cancellable():
    a = _adapter(["stp-000003"])
    a.adopt_and_sweep({"stp-000003"})                 # owned → adopted but NOT cancelled
    assert "stp-000003" in a._trades, "pre-restart order still unreachable by cancel()"
