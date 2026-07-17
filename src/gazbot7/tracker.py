"""GAZBOT V7 — position + trade assembly (D3). The §274-C race, designed out.

This is the whole reason for the rewrite. In V5 a round-trip could complete via
TWO racing paths — the exit fill vs a ``positionEvent(qty=0)`` flat signal — and
when the flat won a partial-fill scalp, the close was DROPPED and deferred to a
~2-min-late ledger backfill (``RECONSTRUCTED_BACKFILL``). That race is what wedged
the desk twice today, and a gateway reset can't fix it because it isn't a
connectivity fault — it's a design fault.

V7 has **one** completion path: the round-trip closes when the accumulated exit
**fills** bring the net position to flat. It is:

* **partial-fill-aware** — a close is not done until ``exit_qty == entry_qty``;
  a flat arriving while only some exit partials are in simply hasn't completed
  yet, so nothing is dropped;
* **atomic** — when the last partial lands, the trade is written *now*, at the
  true fills-VWAP exit price we already hold, with the real ``exit_reason``;
* **idempotent** — a re-delivered fill is never applied to the position twice,
  and the trade record itself is idempotent on the close exec_id (store layer).

``positionEvent`` is used elsewhere only as a *reconcile cross-check* against
venue truth — never as the completion trigger. Clean-room: nothing copied from V5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .store import Fill, record_trade

_EPS = 1e-9


@dataclass
class _Open:
    """An in-flight round-trip, accumulating entry then exit fills."""

    symbol: str
    side: str  # LONG / SHORT
    opened_at: str
    entry_qty: float
    entry_notional: float  # Σ qty*price → entry VWAP
    entry_exec_ids: list[str]
    exit_qty: float = 0.0
    exit_notional: float = 0.0
    exit_exec_ids: list[str] = field(default_factory=list)
    exit_reason: str | None = None


class TradeTracker:
    """Assembles closed round-trips from venue fills. Position-signed, two-sided,
    N-lot, partial-fill-aware."""

    def __init__(self, store, *, value_per_point: float, fee_rt: float, gate: str | None = None) -> None:
        self._store = store
        self._vpp = value_per_point
        self._fee = fee_rt
        self._gate = gate  # the live desk's gate, stamped on every completed trade
        self._open: dict[str, _Open] = {}
        self._applied: set[str] = set()  # exec_ids already applied to a position

    # ── introspection ────────────────────────────────────────────────────────
    def net_qty(self, symbol: str) -> float:
        """Signed net position derived purely from applied fills (+long/-short)."""
        o = self._open.get(symbol)
        if o is None:
            return 0.0
        mag = o.entry_qty - o.exit_qty
        return mag if o.side == "LONG" else -mag

    def has_applied(self, exec_id: str) -> bool:
        """Has this venue exec already moved the position? Lets the vanished-close
        reconstruction feed ONLY unseen fills, so it can't double-count."""
        return exec_id in self._applied

    def forget(self, symbol: str) -> None:
        """Drop a dangling in-flight round-trip WITHOUT recording it — for a
        vanished close that couldn't be reconstructed, so the next fill doesn't
        mis-book onto a stale open."""
        self._open.pop(symbol, None)

    # ── adopt (S2) ───────────────────────────────────────────────────────────
    def adopt(self, symbol: str, side: str, qty: float, price: float, opened_at: str) -> None:
        """Seed a position taken over from IBKR truth (boot reconcile) WITHOUT
        recording a fill, so ``net_qty`` reflects it and its later close completes
        a trade normally. Without this, a close fill on an un-seeded tracker
        mis-books as a fresh open (the adopt-mis-book bug)."""
        self._open[symbol] = _Open(
            symbol=symbol, side=side, opened_at=opened_at,
            entry_qty=qty, entry_notional=qty * price, entry_exec_ids=[],
        )

    # ── the one fill path ────────────────────────────────────────────────────
    def apply(self, fill: Fill, *, exit_reason: str | None = None) -> None:
        """Apply a venue fill. Idempotent on exec_id (never double-count). When
        the accumulated exits bring the position flat, the trade is recorded
        atomically — this is the only place a round-trip completes."""
        if fill.exec_id in self._applied:
            return  # a re-delivered fill — no-op, position never double-moved
        self._applied.add(fill.exec_id)

        sym = fill.symbol
        signed_buy = fill.side == "BUY"
        o = self._open.get(sym)

        if o is None:
            # flat → this fill opens a new round-trip
            self._open[sym] = _Open(
                symbol=sym,
                side="LONG" if signed_buy else "SHORT",
                opened_at=fill.exec_time,
                entry_qty=fill.qty,
                entry_notional=fill.qty * fill.price,
                entry_exec_ids=[fill.exec_id],
            )
            return

        opening_is_buy = o.side == "LONG"
        if signed_buy == opening_is_buy:
            # same direction as the entry → an add (also handles partial entries)
            o.entry_qty += fill.qty
            o.entry_notional += fill.qty * fill.price
            o.entry_exec_ids.append(fill.exec_id)
            return

        # opposite direction → an exit (possibly one of several partials)
        remaining = o.entry_qty - o.exit_qty
        close_qty = min(fill.qty, remaining)
        o.exit_qty += close_qty
        o.exit_notional += close_qty * fill.price
        o.exit_exec_ids.append(fill.exec_id)
        if exit_reason is not None and o.exit_reason is None:
            o.exit_reason = exit_reason

        if abs(o.exit_qty - o.entry_qty) < _EPS:
            # FLAT — every exit partial is in. Complete NOW from the fills we hold.
            self._complete(o, closed_at=fill.exec_time, last_exit=fill.exec_id)
            del self._open[sym]
            # A close that overshoots flat (a flip) opens the remainder the
            # other way — never silently swallow the excess (V5 oversell scar).
            excess = fill.qty - close_qty
            if excess > _EPS:
                self._open[sym] = _Open(
                    symbol=sym,
                    side="SHORT" if signed_buy is False else "LONG",
                    opened_at=fill.exec_time,
                    entry_qty=excess,
                    entry_notional=excess * fill.price,
                    entry_exec_ids=[fill.exec_id],
                )

    # ── completion ───────────────────────────────────────────────────────────
    def _complete(self, o: _Open, *, closed_at: str, last_exit: str) -> None:
        entry_px = o.entry_notional / o.entry_qty
        exit_px = o.exit_notional / o.exit_qty
        if o.side == "LONG":
            gross = (exit_px - entry_px) * o.entry_qty * self._vpp
        else:
            gross = (entry_px - exit_px) * o.entry_qty * self._vpp
        record_trade(
            self._store,
            symbol=o.symbol,
            side=o.side,
            qty=o.entry_qty,
            entry_price=entry_px,
            exit_price=exit_px,
            entry_exec_id=o.entry_exec_ids[0] if o.entry_exec_ids else None,  # adopted = no entry fill
            exit_exec_id=last_exit,
            opened_at=o.opened_at,
            closed_at=closed_at,
            pnl_usd=gross - self._fee,
            fees_usd=self._fee,
            exit_reason=o.exit_reason or "UNKNOWN",
            gate=self._gate,
        )
