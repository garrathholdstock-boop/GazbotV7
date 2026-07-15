"""GAZBOT V7 — position safety (D4): the native 1-ATR stop, naked guard, reconcile.

Two invariants, mechanically enforced:

1. **Zero naked.** Every open position carries a *fixed native 1-ATR STP*
   (server-side at IBKR) armed the instant it opens. If a position is ever found
   open at venue truth with no protective stop, it is auto-reprotected AND the
   operator is paged. A fixed STP (not a trailing stop) attaches to any parent —
   the V5 Error-328 class can't occur.
2. **Venue truth before reducing.** Position sign/qty come from IBKR truth
   (``reconcile`` against the fill-derived position); a cached book can never
   authorise a close.

Pure stop math + a coverage manager driven through an injected broker/notifier,
so all of it is tested without a live gateway. Clean-room: nothing copied from V5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

_EPS = 1e-9


def compute_stop_price(entry_price: float, atr: float, *, is_short: bool, atr_mult: float = 1.0) -> float:
    """The fixed protective stop: ``atr_mult`` ATRs adverse of entry. Below entry
    for a long, above entry for a short — symmetric by construction."""
    r = atr_mult * atr
    return (entry_price + r) if is_short else (entry_price - r)


@dataclass(frozen=True, slots=True)
class StopOrder:
    symbol: str
    side: str  # the CLOSING side: SELL protects a long, BUY protects a short
    qty: float
    stop_price: float
    coid: str


class StopBrokerPort(Protocol):
    def place_stop(self, *, symbol: str, side: str, qty: float, stop_price: float) -> str: ...
    def cancel(self, coid: str) -> None: ...


class Notifier(Protocol):
    def __call__(self, message: str) -> None: ...


class SafetyManager:
    def __init__(
        self,
        broker: StopBrokerPort,
        *,
        atr_mult: float = 1.0,
        notifier: Notifier | None = None,
    ) -> None:
        self._broker = broker
        self._atr_mult = atr_mult
        self._notify = notifier or (lambda _msg: None)
        self._stops: dict[str, StopOrder] = {}  # symbol → its active protective stop

    def has_stop(self, symbol: str) -> bool:
        return symbol in self._stops

    def stop_for(self, symbol: str) -> StopOrder | None:
        return self._stops.get(symbol)

    def arm_stop(self, symbol: str, *, side: str, qty: float, entry_price: float, atr: float) -> StopOrder:
        """Place the fixed 1-ATR STP for a freshly-opened position. ``side`` is
        the POSITION side (LONG/SHORT); the stop is the opposite (closing) side."""
        is_short = side == "SHORT"
        stop_px = compute_stop_price(entry_price, atr, is_short=is_short, atr_mult=self._atr_mult)
        close_side = "BUY" if is_short else "SELL"
        coid = self._broker.place_stop(symbol=symbol, side=close_side, qty=qty, stop_price=stop_px)
        st = StopOrder(symbol, close_side, qty, stop_px, coid)
        self._stops[symbol] = st
        return st

    def on_flat(self, symbol: str) -> None:
        """Position closed → cancel and forget its protective stop."""
        st = self._stops.pop(symbol, None)
        if st is not None:
            self._broker.cancel(st.coid)

    def handle_naked(
        self, symbol: str, *, side: str, qty: float, entry_price: float, atr: float
    ) -> StopOrder:
        """A position found naked at venue truth → auto-reprotect AND page."""
        st = self.arm_stop(symbol, side=side, qty=qty, entry_price=entry_price, atr=atr)
        self._notify(f"NAKED {symbol} {side} {qty:g} — auto-reprotected: {st.side} STP @ {st.stop_price:g}")
        return st


def audit_naked(venue_positions: dict[str, float], venue_stops: set[str]) -> list[str]:
    """Symbols open at IBKR truth with NO protective stop resting at IBKR. Reads
    venue truth (never a cached book) — the input is the source of truth."""
    return [
        sym
        for sym, qty in venue_positions.items()
        if abs(qty) > _EPS and sym not in venue_stops
    ]


def reconcile(tracker_net: dict[str, float], venue_net: dict[str, float]) -> list[str]:
    """Symbols where the fill-derived position disagrees with IBKR venue truth."""
    drift: list[str] = []
    for sym in set(tracker_net) | set(venue_net):
        if abs(tracker_net.get(sym, 0.0) - venue_net.get(sym, 0.0)) > _EPS:
            drift.append(sym)
    return drift
