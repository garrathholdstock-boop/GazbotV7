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


def _bar(ts, o, h, l, c, v):
    return {"symbol": "MNQ", "tf": "5s", "ts": ts, "o": o, "h": h, "l": l, "c": round(c, 4), "v": v}


def _thrust_up_intent():
    """Drive a Strategy to a real OPEN intent off a 1-minute thrust (5s → 1m)."""
    from datetime import UTC, datetime
    end = int(datetime(2026, 7, 15, 16, 0, tzinfo=UTC).timestamp())  # in-session, minute-aligned
    s = Strategy(RunConfig(gate="thrust", gate_params={"thr": 1.5, "amp_floor": 0.0004}))
    closes = [100.0] * 5 + [100.8, 101.6, 102.4, 103.2, 104.0] + [104.0]
    vols = [12] * 5 + [12, 14, 16, 18, 60] + [20]
    prev = 100.0
    start = end - len(closes) * 60
    for i, cl in enumerate(closes):
        mstart = start + i * 60
        for j in range(12):
            c = prev + (cl - prev) * (j + 1) / 12
            s.on_bar(_bar(mstart + j * 5, c, c + 0.15, c - 0.15, c, vols[i] / 12))
        prev = cl
    now = end * 1000 + 100
    s.on_tape({"ts_ms": now - 100, "net_flow": 0, "win_price_delta": 0, "last": 104.0, "in_rth": True})
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
