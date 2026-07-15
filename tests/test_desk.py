"""D7 — the live loop end-to-end: entry, each exit path, two-sided, sizing."""

from __future__ import annotations

from gazbot7.deciders import Bar, compute_features, gate_thrust
from gazbot7.desk import Desk, DeskConfig
from gazbot7.engine import OrderEngine
from gazbot7.safety import SafetyManager
from gazbot7.store import Fill, get_trades, open_store
from gazbot7.tracker import TradeTracker

VPP, FEE = 2.0, 1.5


class FakeBroker:
    def __init__(self):
        self.orders: list[dict] = []

    def place(self, order):
        self.orders.append(dict(side=order.side, qty=order.qty))

    def cancel(self, coid):
        pass


class FakeStopBroker:
    def __init__(self):
        self.stops: list[dict] = []
        self.cancelled: list[str] = []
        self._n = 0

    def place_stop(self, *, symbol, side, qty, stop_price):
        self._n += 1
        self.stops.append(dict(side=side, qty=qty, stop_price=stop_price))
        return f"stp-{self._n}"

    def cancel(self, coid):
        self.cancelled.append(coid)


def _build(cfg: DeskConfig):
    store = open_store(":memory:")
    broker, sb = FakeBroker(), FakeStopBroker()
    oe = OrderEngine(broker, store)
    tt = TradeTracker(store, value_per_point=VPP, fee_rt=FEE)
    sm = SafetyManager(sb)
    return Desk(cfg, oe, tt, sm), broker, sb, tt, store


def _flat_then(deltas, last_vol=40, base=100.0, flat=15):
    bars = [Bar(i, base, base + 0.5, base - 0.5, base, 10) for i in range(flat)]
    px = base
    for j, d in enumerate(deltas):
        px += d
        vol = last_vol if j == len(deltas) - 1 else 10
        bars.append(Bar(flat + j, px - d, max(px, px - d) + 0.2, min(px, px - d) - 0.2, px, vol))
    return bars


def _flat_at(price):
    return [Bar(i, price, price + 0.5, price - 0.5, price, 10) for i in range(20)]


def _fill(exec_id, side, qty, price):
    return Fill(exec_id=exec_id, order_id="o", symbol="MNQ", side=side, qty=qty, price=price,
                exec_time="2026-07-15T13:00:00+00:00")


THRUST_UP = _flat_then([0.7, 0.7, 0.7, 0.7, 0.7])
THRUST_DOWN = _flat_then([-0.7, -0.7, -0.7, -0.7, -0.7])


def test_thrust_up_fires_long():  # sanity: the bar helper actually triggers the gate
    assert gate_thrust(compute_features(THRUST_UP)).side == "LONG"


def test_entry_opens_and_arms_stop():
    desk, broker, sb, _tt, _s = _build(DeskConfig(gate="thrust"))
    desk.on_bars(THRUST_UP)
    assert broker.orders == [dict(side="BUY", qty=1)]  # submitted a long
    desk.on_fill(_fill("e1", "BUY", 1, 100.0))  # entry fill
    assert desk.position is not None and desk.position.side == "LONG"
    assert len(sb.stops) == 1 and sb.stops[0]["side"] == "SELL"  # a SELL stop below entry
    assert sb.stops[0]["stop_price"] < 100.0


def test_target_exit_records_trade_and_clears_stop():
    desk, broker, sb, _tt, store = _build(DeskConfig(gate="thrust", target_r=2.0))
    desk.on_bars(THRUST_UP)
    desk.on_fill(_fill("e1", "BUY", 1, 100.0))
    desk.on_bars(_flat_at(110.0))  # well past the 2R target → managed close
    assert broker.orders[-1] == dict(side="SELL", qty=1)
    desk.on_fill(_fill("x1", "SELL", 1, 110.0))  # close fill
    (tr,) = get_trades(store)
    assert tr["exit_reason"] == "TARGET"
    assert tr["pnl_usd"] == (110 - 100) * 1 * VPP - FEE  # +18.5
    assert desk.position is None
    assert sb.cancelled == ["stp-1"]  # protective stop cleared on flat


def test_native_stop_fill_records_as_STOP():
    # a closing fill with no managed exit submitted = the native STP fired
    desk, _b, _sb, _tt, store = _build(DeskConfig(gate="thrust"))
    desk.on_bars(THRUST_UP)
    desk.on_fill(_fill("e1", "BUY", 1, 100.0))
    desk.on_fill(_fill("x1", "SELL", 1, 96.0))  # STP filled at the venue
    (tr,) = get_trades(store)
    assert tr["exit_reason"] == "STOP"


def test_adverse_cut_exit():
    desk, broker, _sb, _tt, store = _build(DeskConfig(gate="thrust", adverse_cut_atr=1.5))
    desk.on_bars(THRUST_UP)
    desk.on_fill(_fill("e1", "BUY", 1, 100.0))
    desk.on_bars(_flat_at(95.0))  # offside, never went green → adverse cut
    assert broker.orders[-1] == dict(side="SELL", qty=1)
    desk.on_fill(_fill("x1", "SELL", 1, 95.0))
    (tr,) = get_trades(store)
    assert tr["exit_reason"] == "ADVERSE_CUT"


def test_short_entry_two_sided():
    desk, broker, sb, _tt, _s = _build(DeskConfig(gate="thrust"))
    desk.on_bars(THRUST_DOWN)
    assert broker.orders == [dict(side="SELL", qty=1)]  # opened a short
    desk.on_fill(_fill("e1", "SELL", 1, 100.0))
    assert desk.position.side == "SHORT"
    assert sb.stops[0]["side"] == "BUY" and sb.stops[0]["stop_price"] > 100.0  # BUY stop above


def test_sizing_n_contracts():
    desk, broker, _sb, _tt, _s = _build(DeskConfig(gate="thrust", size=2))
    desk.on_bars(THRUST_UP)
    assert broker.orders[0]["qty"] == 2
