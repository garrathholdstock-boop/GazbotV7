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
        return SimpleNamespace(order=order, orderStatus=SimpleNamespace(status="PreSubmitted"))


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
