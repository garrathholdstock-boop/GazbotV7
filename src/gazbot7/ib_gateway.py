"""GAZBOT V7 — the IBKR gateway primitive (D1).

A thin, testable async wrapper over ``ib_async.IB`` that owns exactly one
concern: a *healthy connection*. It connects, watches for disconnects, and
reconnects with exponential backoff — and on **every** (re)connection it
**re-asserts the registered subscriptions** before declaring itself HEALTHY.

That last point is the scar. V5's 04:37 outage was an Error-1100 disconnect
after which the fill/order subscriptions were never re-established — fills kept
flowing on one path while the recording path stayed silent. Here, a subscription
is a callback registered via :meth:`on_reconnect`; it is re-run on the initial
connect AND after every reconnect, so there is no post-reconnect gap by
construction. D3 will register "re-subscribe fills/status for my live orders"
here.

The ``ib_async.IB`` instance is injected via ``ib_factory`` so the reconnect
state machine is unit-tested against a fake, with a thin live smoke against the
real paper gateway. Clean-room: nothing copied from V5.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum

# Default reconnect backoff (seconds), capped. Exposed for tests to shrink.
_DEFAULT_BACKOFF: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)


class ConnState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    HEALTHY = "HEALTHY"
    RECONNECTING = "RECONNECTING"
    STOPPED = "STOPPED"


def _new_ib():
    import ib_async

    return ib_async.IB()


class IBGateway:
    """Owns a healthy connection to one IB gateway, with self-healing reconnect."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 7,  # V7's dedicated clientId (V5 uses 0,1,2,14,16,97,99,101)
        *,
        readonly: bool = True,
        timeout: float = 4.0,
        backoff: tuple[float, ...] = _DEFAULT_BACKOFF,
        ib_factory: Callable[[], object] = _new_ib,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.readonly = readonly
        self.timeout = timeout
        self._backoff = backoff
        self._ib = ib_factory()
        self.state = ConnState.DISCONNECTED
        self._stopping = False
        self._reconnect_task: asyncio.Task | None = None
        # Subscriptions to re-assert on every (re)connect. Each is an async
        # callable taking the IB instance. reassert_count is a test observable.
        self._subscriptions: list[Callable[[object], Awaitable[None]]] = []
        self.reassert_count = 0
        self._wired = False

    # ── subscription registration ──────────────────────────────────────────
    def on_reconnect(self, coro: Callable[[object], Awaitable[None]]) -> None:
        """Register a subscription to (re-)assert on the initial connect and
        after every reconnect. This is how downstream layers stay subscribed
        across a gateway bounce with no gap."""
        self._subscriptions.append(coro)

    async def _reassert(self) -> None:
        for coro in self._subscriptions:
            await coro(self._ib)
        self.reassert_count += 1

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Connect (with backoff) and wire auto-reconnect. Idempotent-ish:
        call once at startup."""
        self._stopping = False
        if not self._wired:
            self._ib.disconnectedEvent += self._on_disconnected
            self._wired = True
        await self._connect_with_backoff()

    async def _connect_once(self) -> None:
        self.state = ConnState.CONNECTING
        await self._ib.connectAsync(
            self.host, self.port, clientId=self.client_id,
            timeout=self.timeout, readonly=self.readonly,
        )
        await self._reassert()
        self.state = ConnState.HEALTHY

    async def _connect_with_backoff(self) -> None:
        attempt = 0
        while not self._stopping:
            try:
                await self._connect_once()
                return
            except Exception:
                if self._stopping:
                    return
                self.state = ConnState.RECONNECTING
                wait = self._backoff[min(attempt, len(self._backoff) - 1)]
                attempt += 1
                await asyncio.sleep(wait)

    def _on_disconnected(self) -> None:
        """Fired by ib_async on any disconnect. Ignore if we're stopping;
        otherwise kick off the reconnect loop."""
        if self._stopping or self.state == ConnState.STOPPED:
            return
        self.state = ConnState.RECONNECTING
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.ensure_future(self._connect_with_backoff())

    async def stop(self) -> None:
        self._stopping = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._ib.isConnected():
            self._ib.disconnect()
        self.state = ConnState.STOPPED

    # ── read-only reads (D1 scope) ───────────────────────────────────────────
    @property
    def healthy(self) -> bool:
        return self.state == ConnState.HEALTHY and self._ib.isConnected()

    async def probe_alive(self, timeout: float = 5.0) -> bool:
        """A positive round-trip to IBKR (reqCurrentTime) — the freshness gate for
        reconcile/adopt. A stale-but-responsive gateway is the failure a socket's
        own liveness bit misses; this proves the data path answers *now*.
        Fail-closed: False on any error/timeout, so callers never act on a stale
        snapshot."""
        if not self.healthy:
            return False
        try:
            await asyncio.wait_for(self._ib.reqCurrentTimeAsync(), timeout=timeout)
            return True
        except Exception:
            return False

    async def liveness_loop(self, *, interval: float = 20.0, max_fail: int = 2,
                            timeout: float = 8.0) -> None:
        """Zombie-connection guard. Probe reqCurrentTime on a cadence; after
        ``max_fail`` consecutive silent failures on a *HEALTHY* connection, force a
        disconnect so the reconnect machinery rebuilds the session. This is the
        class where a gateway reports 'connected' while the socket is half-dead —
        V5's nightly-restart 63k-phantom-order storm. The probe interval sits below
        any process watchdog so a zombie is caught before escalation."""
        fails = 0
        while not self._stopping:
            await asyncio.sleep(interval)
            if self._stopping:
                break
            if self.state != ConnState.HEALTHY:
                fails = 0
                continue
            if await self.probe_alive(timeout=timeout):
                fails = 0
                continue
            fails += 1
            if fails >= max_fail:
                fails = 0
                self._force_reconnect()

    def force_reconnect(self) -> None:
        """Public: tear down a (possibly zombie) connection so the reconnect loop
        rebuilds a fresh session. Core calls this when it HOLDS a position it cannot
        verify — reqCurrentTime can answer while reqPositions/reqAllOpenOrders is dead
        (the 2026-07-17 naked-bleed), and a fresh session restores the data path the
        naked auditor depends on. Safe to call repeatedly; a no-op while stopping."""
        if not self._stopping:
            self._force_reconnect()

    def _force_reconnect(self) -> None:
        """Tear the (zombie) connection down so the reconnect loop rebuilds it."""
        self.state = ConnState.RECONNECTING
        if self._ib.isConnected():
            self._ib.disconnect()  # → disconnectedEvent → _on_disconnected → reconnect
        elif self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.ensure_future(self._connect_with_backoff())

    async def positions(self):
        """Venue-truth positions (read-only)."""
        return await self._ib.reqPositionsAsync()

    async def account_summary(self):
        return await self._ib.accountSummaryAsync()
