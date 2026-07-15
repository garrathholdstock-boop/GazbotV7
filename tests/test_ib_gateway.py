"""D1 — the IBKR gateway primitive: connect, reconnect, and the scar
(subscriptions re-asserted on every reconnect)."""

from __future__ import annotations

import eventkit  # ib_async's event lib — the fake uses the real event type

from gazbot7.ib_gateway import ConnState, IBGateway


class FakeIB:
    """A minimal stand-in for ib_async.IB — enough to drive the state machine."""

    def __init__(self, fail_first: int = 0) -> None:
        self._connected = False
        self._fail_first = fail_first
        self.connect_calls = 0
        self.disconnectedEvent = eventkit.Event()
        self._positions = ["POS"]

    async def connectAsync(self, host, port, clientId, timeout, readonly):
        self.connect_calls += 1
        if self.connect_calls <= self._fail_first:
            raise ConnectionError("refused")
        self._connected = True

    def isConnected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False
        self.disconnectedEvent.emit()

    def simulate_drop(self) -> None:
        """An external/unexpected disconnect (Error-1100 class)."""
        self._connected = False
        self.disconnectedEvent.emit()

    async def reqPositionsAsync(self):
        return list(self._positions)

    async def accountSummaryAsync(self):
        return []


def _gw(fake: FakeIB, **kw) -> IBGateway:
    return IBGateway(ib_factory=lambda: fake, backoff=(0.01, 0.01, 0.01), **kw)


async def test_connect_healthy():
    gw = _gw(FakeIB())
    await gw.start()
    assert gw.state == ConnState.HEALTHY
    assert gw.healthy
    assert gw.reassert_count == 1  # initial connect asserts subscriptions too


async def test_reconnect_reasserts_subscriptions():
    # THE D1 scar: after an unexpected disconnect, subscriptions are re-asserted
    # before HEALTHY. (V5's 04:37 gap was a reconnect that never re-subscribed.)
    fake = FakeIB()
    gw = _gw(fake)
    seen: list[int] = []

    async def sub(_ib):
        seen.append(1)

    gw.on_reconnect(sub)
    await gw.start()
    assert len(seen) == 1 and gw.reassert_count == 1

    fake.simulate_drop()
    assert gw.state == ConnState.RECONNECTING
    await gw._reconnect_task  # let the reconnect complete

    assert gw.state == ConnState.HEALTHY
    assert len(seen) == 2  # subscription re-asserted on reconnect
    assert gw.reassert_count == 2


async def test_backoff_then_connects():
    fake = FakeIB(fail_first=2)  # first two connect attempts fail
    gw = _gw(fake)
    await gw.start()
    assert gw.healthy
    assert fake.connect_calls == 3  # retried through the backoff to success


async def test_stop_prevents_reconnect():
    fake = FakeIB()
    gw = _gw(fake)
    await gw.start()
    await gw.stop()
    assert gw.state == ConnState.STOPPED
    fake.simulate_drop()  # a disconnect AFTER stop must not trigger a reconnect
    assert gw.state == ConnState.STOPPED


async def test_positions_readonly():
    gw = _gw(FakeIB())
    await gw.start()
    assert await gw.positions() == ["POS"]
