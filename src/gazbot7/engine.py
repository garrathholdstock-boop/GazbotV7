"""GAZBOT V7 — the order engine core (D2).

Owns the order lifecycle and applies venue fills. The one correctness guarantee
of D2: applying a fill is **idempotent on exec_id**, so a re-delivered fill (the
same execution seen by two paths — the exact V5 hazard) never double-counts an
order's filled quantity. Trade *assembly* (pairing an entry+exit into a closed
``trades`` row, partial-fill-aware, atomic on flat) is D3 — this drop is the
lifecycle + the idempotent fill application it stands on.

The broker is injected via ``BrokerPort`` so the engine is pure and fully
tested against a fake; the ib_async adapter (which needs a live/isolated paper
account) is wired later. Clean-room: nothing copied from V5.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .store import Fill, record_fill, upsert_order

_EPS = 1e-9


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    WORKING = "WORKING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


_TERMINAL = frozenset({OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED})


@dataclass
class Order:
    client_order_id: str
    symbol: str
    side: str  # BUY / SELL
    qty: float
    order_type: str
    limit_price: float | None
    status: OrderStatus
    filled_qty: float = 0.0
    tif: str | None = None  # None = broker default (DAY); "IOC" for marketable entries


class BrokerPort(Protocol):
    """The minimal broker surface the engine drives (ib_async adapter later)."""

    def place(self, order: Order) -> None: ...
    def cancel(self, client_order_id: str) -> None: ...


class OrderEngine:
    def __init__(self, broker: BrokerPort, store, *, coid_prefix: str = "v7-mnq") -> None:
        self._broker = broker
        self._store = store
        self._prefix = coid_prefix
        self._orders: dict[str, Order] = {}
        # Seed the sequence PAST every coid already in the store so a restart never
        # re-issues an old coid (2026-07-20). The counter was in-memory → it reset to
        # 0 on every restart, re-minting v7-mnq-000001… which collided with prior
        # sessions and corrupted the orders table via the partial upsert-on-conflict.
        self._seq = self._max_coid_seq()

    def _max_coid_seq(self) -> int:
        """Highest numeric suffix among stored coids with this prefix (0 if none)."""
        try:
            rows = self._store.execute(
                "SELECT client_order_id FROM orders WHERE client_order_id LIKE ?",
                (f"{self._prefix}-%",),
            ).fetchall()
        except Exception:
            return 0
        mx = 0
        for (coid,) in rows:
            try:
                mx = max(mx, int(str(coid).rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                pass
        return mx

    def _next_coid(self) -> str:
        self._seq += 1
        return f"{self._prefix}-{self._seq:06d}"

    def _persist(self, o: Order) -> None:
        upsert_order(
            self._store,
            client_order_id=o.client_order_id,
            symbol=o.symbol,
            side=o.side,
            qty=o.qty,
            order_type=o.order_type,
            limit_price=o.limit_price,
            status=o.status.value,
        )

    # ── submit / cancel ──────────────────────────────────────────────────────
    def submit(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        limit_price: float | None = None,
        coid: str | None = None,
        tif: str | None = None,
    ) -> str:
        coid = coid or self._next_coid()
        o = Order(coid, symbol, side, qty, order_type, limit_price, OrderStatus.PENDING, tif=tif)
        self._orders[coid] = o
        self._persist(o)
        self._broker.place(o)  # if this raises, the order never advances to WORKING
        o.status = OrderStatus.WORKING
        self._persist(o)
        return coid

    def cancel(self, coid: str) -> None:
        o = self._orders.get(coid)
        if o is None or o.status in _TERMINAL:
            return
        self._broker.cancel(coid)  # the terminal CANCELLED arrives via on_status

    # ── event application ────────────────────────────────────────────────────
    def on_fill(self, fill: Fill) -> bool:
        """Apply a venue fill idempotently. Returns True if newly applied,
        False if this exec_id was already seen (a no-op — no double-count)."""
        newly = record_fill(self._store, fill)
        o = self._orders.get(fill.order_id)
        if o is not None and newly:
            o.filled_qty += fill.qty
            o.status = (
                OrderStatus.FILLED
                if o.filled_qty >= o.qty - _EPS
                else OrderStatus.PARTIAL
            )
            self._persist(o)
        return newly

    def on_status(self, coid: str, status: OrderStatus) -> None:
        """Broker-driven status (ack / reject / cancel confirm). Never regress a
        terminal state; fills own FILLED, so a status update can't override it."""
        o = self._orders.get(coid)
        if o is None or o.status in _TERMINAL:
            return
        o.status = status
        self._persist(o)

    def get(self, coid: str) -> Order | None:
        return self._orders.get(coid)
