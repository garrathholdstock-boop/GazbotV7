"""Cross-service contract: the intent strategy emits is exactly what core consumes.

The split's one fragile seam is the intent schema — strategy stamps it, core
reads it. This wires a real Strategy decision straight into a real Core (fakes
for the broker/publisher, no sockets) so a field rename on either side fails
loudly here rather than silently dropping live orders."""

from __future__ import annotations

import asyncio

from gazbot7.config import RunConfig
from gazbot7.core import Core
from gazbot7.engine import OrderEngine
from gazbot7.safety import SafetyManager
from gazbot7.store import open_store
from gazbot7.strategy import Strategy
from gazbot7.tracker import TradeTracker


class _FakeBroker:
    def __init__(self):
        self.orders = []

    def place(self, order):
        self.orders.append(dict(side=order.side, qty=order.qty))

    def cancel(self, coid):
        pass


class _FakeStopBroker:
    def place_stop(self, *, symbol, side, qty, stop_price):
        return "stp-1"

    def cancel(self, coid):
        pass


class _FakePub:
    def __init__(self):
        self.sent = []

    async def send(self, topic, payload):
        self.sent.append((topic, payload))


def _bar(ts, c, v=10):
    return {"symbol": "MNQ", "tf": "5s", "ts": ts, "o": c, "h": c + 0.5, "l": c - 0.5, "c": c, "v": v}


def _thrust_up_intent():
    """Drive a Strategy to a real OPEN intent off a thrust."""
    s = Strategy(RunConfig(gate="thrust", gate_params={"thr": 1.5}))
    ts = 2000 - 19 * 5
    for _ in range(15):
        s.on_bar(_bar(ts, 100.0)); ts += 5
    px = 100.0
    for j in range(5):
        px += 0.7
        s.on_bar(_bar(ts, px, 40 if j == 4 else 10)); ts += 5
    now = 2000 * 1000 + 100
    s.on_tape({"ts_ms": now - 100, "net_flow": 0, "win_price_delta": 0, "last": px, "in_rth": True})
    return s.decide(now)


def test_strategy_open_intent_is_accepted_by_core():
    async def scenario():
        intent = _thrust_up_intent()
        assert intent is not None and intent["action"] == "OPEN"  # sanity

        store = open_store(":memory:")
        broker = _FakeBroker()
        core = Core(
            RunConfig(place_live=True),
            OrderEngine(broker, store),
            TradeTracker(store, value_per_point=2.0, fee_rt=1.5),
            SafetyManager(_FakeStopBroker()),
            _FakePub(),
            store,
        )
        await core.on_intent(intent)
        # core understood the strategy's intent and placed the matching order
        assert broker.orders == [dict(side="BUY", qty=intent["qty"])]

    asyncio.run(scenario())
