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

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .ticks import round_stop, tick_for

_EPS = 1e-9

# What counts as *live protective coverage* at IBKR truth — a resting server-side
# stop on the closing side. Anything Cancelled / Inactive / Filled does NOT count,
# no matter what a local flag says (the "placed but didn't stick" naked class).
_LIVE_STATUSES = frozenset({"Submitted", "PreSubmitted", "PendingSubmit", "ApiPending"})
_STOP_TYPES = frozenset({"STP", "STP LMT", "STP_LMT", "TRAIL", "TRAIL LIMIT", "TRAIL_LIMIT"})


def compute_stop_price(entry_price: float, atr: float, *, is_short: bool, atr_mult: float = 1.0) -> float:
    """The fixed protective stop: ``atr_mult`` ATRs adverse of entry. Below entry
    for a long, above entry for a short — symmetric by construction. (Rounded to
    the contract tick when armed — see ``SafetyManager.arm_stop``.)"""
    r = atr_mult * atr
    return (entry_price + r) if is_short else (entry_price - r)


def is_live_status(status: str) -> bool:
    """A resting (not dead) order status. A stop leaving this set while a position
    is held is the poke signal for the naked auditor."""
    return status in _LIVE_STATUSES


def is_protective_stop(order_type: str, action: str, status: str, position_side: str) -> bool:
    """Does this IBKR order count as live protection for a ``position_side``? A
    live STP/TRAIL on the closing side. Inactive/Cancelled never count."""
    if status not in _LIVE_STATUSES or order_type not in _STOP_TYPES:
        return False
    close_side = "SELL" if position_side == "LONG" else "BUY"
    return action == close_side


def covered_qty(position_side: str, orders: Iterable[tuple]) -> float:
    """Total live protective-stop quantity for the position. ``orders`` is an
    iterable of ``(order_type, action, status, qty)`` read from IBKR truth."""
    return sum(q for (ot, ac, st, q) in orders if is_protective_stop(ot, ac, st, position_side))


def is_naked(position_side: str, position_qty: float, orders: Iterable[tuple]) -> bool:
    """A held position with less live protective coverage than its size. Reads
    IBKR truth (the orders list) — never a local 'armed' flag, which can lie when
    a placement was accepted then went Inactive."""
    if abs(position_qty) < _EPS:
        return False
    return covered_qty(position_side, orders) < abs(position_qty) - _EPS


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
        # round onto the contract tick (Error-110 fix) — directional so it only
        # loosens; the recorded StopOrder equals what actually rests at IBKR.
        stop_px = round_stop(stop_px, tick_for(symbol), closing_side=close_side)
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


def reconcile_verdict(tracked_side: str | None, tracked_qty: float, venue_net: float) -> str:
    """Single-symbol agreement between the desk's tracked position and IBKR truth:

    * ``match``    — they agree (incl. both flat)
    * ``adopt``    — desk flat, venue holds a position → take it over (re-arm)
    * ``vanished`` — desk holds, venue flat → our position closed unseen
    * ``drift``    — both hold but side/qty disagree → halt + alarm (don't auto-fix)
    """
    t_flat = tracked_side is None or abs(tracked_qty) < _EPS
    v_flat = abs(venue_net) < _EPS
    if t_flat and v_flat:
        return "match"
    if t_flat:
        return "adopt"
    if v_flat:
        return "vanished"
    v_side = "LONG" if venue_net > 0 else "SHORT"
    if v_side == tracked_side and abs(abs(venue_net) - abs(tracked_qty)) < _EPS:
        return "match"
    return "drift"
