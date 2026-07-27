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


# Protective stops are placed as STOP-LIMITS with an EXPLICIT limit, this many points past the
# trigger on the fill side. Why: a plain STP (limit unset) let IBKR's paper account attach its OWN
# limit ~1 ATR toward entry (≈ the entry price) — the WRONG side — so it never filled on trigger
# (2026-07-22 id114 / STOP_UNFILLED class, cost a −$216 max-hold ride). Setting our own fillable
# limit forces the fill (bounded slippage) and is strictly better live too (caps a naked market
# fill). Wide enough to fill through normal gaps; the stop-breach guard backstops a bigger gap.
# MNQ-tuned; make per-contract if a non-MNQ contract is re-added.
STOP_LIMIT_BAND_PTS = 20.0


def stop_limit_price(trigger: float, side: str, tick: float, band: float = STOP_LIMIT_BAND_PTS) -> float:
    """The fillable limit for a protective stop-LIMIT: `band` points PAST the trigger on the side
    that fills. A SELL stop (long protection) fills at/below the trigger → limit below; a BUY stop
    (short protection) → limit above. Rounded in the loosening direction so it stays marketable."""
    from .ticks import round_stop
    raw = trigger - band if side == "SELL" else trigger + band
    return round_stop(raw, tick, closing_side=side)


class IBBrokerAdapter:
    """Implements both BrokerPort (entries/exits) and StopBrokerPort (native STP)."""

    def __init__(self, ib, contract, symbol: str, on_fill: Callable[[Fill], None],
                 on_stop_event: Callable[[str, str], None] | None = None,
                 stop_contract=None) -> None:
        self._ib = ib
        self._contract = contract
        # Protective stops REST on their own contract — the CONCRETE front-month Future, not the
        # continuous ContFuture used for (marketable) entries/exits. IBKR intermittently never fires
        # a resting stop's TRIGGER on a continuous contract (order sits PreSubmitted/whyHeld='trigger';
        # our stop-breach guard then has to market-flatten = STOP_UNFILLED). Same conId, so positions/
        # naked-audit still reconcile at the venue. Defaults to `contract` (back-compat).
        self._stop_contract = stop_contract if stop_contract is not None else contract
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
        from ib_async import StopLimitOrder

        from .ticks import round_stop, tick_for

        self._stop_seq += 1
        coid = f"stp-{self._stop_seq:06d}"
        tick = tick_for(symbol)
        # trigger: final tick guard (Error 110), idempotent if safety already rounded (loosen only).
        trig = round_stop(stop_price, tick, closing_side=side)
        # STOP-LIMIT with an EXPLICIT fillable limit (see STOP_LIMIT_BAND_PTS) — a plain STP let the
        # paper account attach a toothless wrong-sided limit. The recorded stop's trigger is `trig`;
        # the stop-breach guard still backstops on that trigger if a gap outruns the limit band.
        lmt = stop_limit_price(trig, side, tick)
        ibo = StopLimitOrder(side, qty, lmt, trig)
        ibo.orderRef = coid
        ibo.tif = "GTC"  # server-side, rests until the position closes
        self._trades[coid] = self._ib.placeOrder(self._stop_contract, ibo)  # concrete Future, not ContFuture
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
