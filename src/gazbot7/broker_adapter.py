"""GAZBOT V7 — the ib_async broker adapter (live glue).

The thin layer that turns the desk's abstract ``BrokerPort`` / ``StopBrokerPort``
into real IBKR orders, and routes ``execDetailsEvent`` fills back into the desk.
It is deliberately tiny — all the correctness lives in the tested core (D2–D4);
this just translates. The one pure, tested piece is ``execution_to_fill``; the
live placement/cancel wiring is exercised at cutover (the first real fill is its
test — by design, per the no-soak plan). Clean-room: nothing copied from V5.
"""

from __future__ import annotations

from collections.abc import Callable

from .store import Fill


def execution_to_fill(execution, *, order_ref: str | None, symbol: str, time_iso: str) -> Fill:
    """Translate an ib_async Execution into our immutable Fill. Pure + tested."""
    return Fill(
        exec_id=execution.execId,
        order_id=order_ref or "unknown",
        symbol=symbol,
        side="BUY" if execution.side == "BOT" else "SELL",
        qty=float(execution.shares),
        price=float(execution.price),
        exec_time=time_iso,
    )


class IBBrokerAdapter:
    """Implements both BrokerPort (entries/exits) and StopBrokerPort (native STP)."""

    def __init__(self, ib, contract, symbol: str, on_fill: Callable[[Fill], None],
                 on_stop_event: Callable[[str, str], None] | None = None) -> None:
        self._ib = ib
        self._contract = contract
        self._symbol = symbol
        self._on_fill = on_fill
        self._on_stop_event = on_stop_event  # (coid, status) when a protective stop goes dead
        self._trades: dict[str, object] = {}  # coid → ib Trade (for cancel)
        self._seen: set[str] = set()  # execIds already routed (belt-and-braces)
        self._stop_seq = 0
        ib.execDetailsEvent += self._on_exec
        if on_stop_event is not None:
            ib.orderStatusEvent += self._on_status

    # ── BrokerPort ───────────────────────────────────────────────────────────
    def place(self, order) -> None:
        from ib_async import LimitOrder, MarketOrder

        if order.order_type == "LMT":
            ibo = LimitOrder(order.side, order.qty, order.limit_price)
        else:
            ibo = MarketOrder(order.side, order.qty)
        if order.tif:  # e.g. IOC for a marketable-limit entry (no resting order)
            ibo.tif = order.tif
        ibo.orderRef = order.client_order_id
        self._trades[order.client_order_id] = self._ib.placeOrder(self._contract, ibo)

    def cancel(self, coid: str) -> None:
        tr = self._trades.get(coid)
        if tr is not None:
            self._ib.cancelOrder(tr.order)

    # ── StopBrokerPort ───────────────────────────────────────────────────────
    def place_stop(self, *, symbol: str, side: str, qty: float, stop_price: float) -> str:
        from ib_async import StopOrder

        from .ticks import round_stop, tick_for

        self._stop_seq += 1
        coid = f"stp-{self._stop_seq:06d}"
        # final tick guard (Error 110): idempotent if safety already rounded.
        px = round_stop(stop_price, tick_for(symbol), closing_side=side)
        ibo = StopOrder(side, qty, px)
        ibo.orderRef = coid
        ibo.tif = "GTC"  # server-side, rests until the position closes
        self._trades[coid] = self._ib.placeOrder(self._contract, ibo)
        return coid

    # ── protective-stop liveness (S1 fast path) ──────────────────────────────
    def _on_status(self, trade) -> None:
        """A protective stop leaving a live status (rejected / cancelled / went
        Inactive) while we may still be holding → poke the naked auditor. The
        auditor re-reads IBKR truth and decides; a spurious poke is harmless."""
        from .safety import is_live_status

        ref = getattr(trade.order, "orderRef", "") or ""
        if ref.startswith("stp-") and not is_live_status(trade.orderStatus.status):
            self._on_stop_event(ref, trade.orderStatus.status)

    # ── fill routing ─────────────────────────────────────────────────────────
    def _on_exec(self, trade, fill) -> None:
        ex = fill.execution
        if ex.execId in self._seen:
            return  # idempotent at the boundary too (the store is the real guard)
        self._seen.add(ex.execId)
        f = execution_to_fill(
            ex, order_ref=getattr(trade.order, "orderRef", None),
            symbol=self._symbol, time_iso=fill.time.isoformat(),
        )
        self._on_fill(f)
