"""GAZBOT V7 — multi-slot position ledger (the paper-tournament foundation).

N gates run concurrently on ONE paper account; IBKR nets position per *account*, so
a LONG slot + a SHORT slot show a venue net of **0** — the venue cannot tell the two
apart. This ledger keeps the logical per-slot truth (side / qty / entry-VWAP) and
attributes every fill to its slot **by order coid** — the only reliable key, since the
netted venue can't distinguish slots. It carries the invariant that makes the whole
scheme safe:

    sum of signed slot qtys  ==  venue net position    (else DRIFT → the core halts)

It reuses the tracker's completion discipline per slot (partial-fill-aware, atomic on
flat, idempotent on exec_id), so a round-trip is recorded exactly once with the true
fills-VWAP prices. Pure — the core registers each order's coid→gate, feeds it venue
fills, and records the completed round-trips it returns. Clean-room; nothing copied
from V5's (netted, un-attributed) position book.
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS = 1e-9


@dataclass
class Slot:
    """One gate's logical position over the shared, netted venue book."""

    gate: str
    side: str | None = None          # None = flat; else LONG / SHORT
    entry_qty: float = 0.0
    entry_notional: float = 0.0      # Σ qty*price on the entry side → entry VWAP
    exit_qty: float = 0.0
    exit_notional: float = 0.0
    opened_at: str | None = None
    exit_reason: str | None = None
    entry_atr: float = 0.0           # for the per-slot exit stack (manage layer)
    peak_favorable: float = 0.0      # tracked by the manage layer (chandelier/give-back)

    @property
    def qty(self) -> float:
        """Open magnitude (>= 0)."""
        return max(0.0, self.entry_qty - self.exit_qty)

    @property
    def net(self) -> float:
        """Signed logical qty (+long / -short), 0 when flat."""
        mag = self.entry_qty - self.exit_qty
        if mag <= _EPS:
            return 0.0
        return mag if self.side == "LONG" else -mag

    @property
    def entry_price(self) -> float:
        return self.entry_notional / self.entry_qty if self.entry_qty > _EPS else 0.0

    @property
    def is_flat(self) -> bool:
        return self.side is None or self.qty < _EPS


class SlotBook:
    """Per-gate logical positions over a netted venue, attributed by order coid."""

    def __init__(self, gates, *, value_per_point: float, fee_rt: float) -> None:
        self._slots: dict[str, Slot] = {g: Slot(gate=g) for g in gates}
        self._coid_gate: dict[str, str] = {}   # order coid → the gate that owns it
        self._applied: set[str] = set()        # exec_ids already applied (idempotent)
        self._vpp = value_per_point
        self._fee = fee_rt

    # ── registration + introspection ────────────────────────────────────────
    def register(self, coid: str, gate: str) -> None:
        """The core calls this when it submits ANY order (open/stop/close) for a slot,
        so the resulting venue fill routes back to the right slot."""
        self._coid_gate[coid] = gate

    def slot(self, gate: str) -> Slot:
        return self._slots[gate]

    def restore_slot(
        self, gate: str, *, side: str, entry_qty: float, entry_notional: float,
        exit_qty: float, exit_notional: float, opened_at: str, entry_atr: float,
    ) -> None:
        """Load a persisted OPEN slot back into memory after a restart (no I/O — the
        core reads the durable snapshot and hands it here). The netted venue can't
        reconstruct per-slot state, so our ledger is the source of truth on boot; the
        venue net is only the reconcile tripwire the core checks against."""
        self._slots[gate] = Slot(
            gate=gate, side=side, entry_qty=entry_qty, entry_notional=entry_notional,
            exit_qty=exit_qty, exit_notional=exit_notional, opened_at=opened_at,
            entry_atr=entry_atr,
        )

    def gates(self) -> list[str]:
        return list(self._slots.keys())

    def any_held(self) -> bool:
        return any(not s.is_flat for s in self._slots.values())

    def net_qty(self) -> float:
        """Logical net across all slots — must equal the venue net."""
        return sum(s.net for s in self._slots.values())

    def reconcile(self, venue_net: float) -> str:
        """`match` if the logical net equals venue truth, else `drift` (core halts)."""
        return "match" if abs(self.net_qty() - venue_net) < _EPS else "drift"

    def owner(self, coid: str) -> str | None:
        return self._coid_gate.get(coid)

    # ── the one fill path ────────────────────────────────────────────────────
    def apply(self, fill, *, exit_reason: str | None = None) -> dict | None:
        """Route a venue fill to its slot by coid and update the slot. Returns a
        completed round-trip dict when that slot goes flat (else None). Idempotent on
        exec_id; an unattributed fill (unknown coid) returns None so the core can flag
        it — the ledger never guesses which slot an un-owned fill belongs to."""
        if fill.exec_id in self._applied:
            return None
        gate = self._coid_gate.get(fill.order_id)
        if gate is None:
            return None                        # unattributed → core's problem, not a guess
        self._applied.add(fill.exec_id)
        s = self._slots[gate]
        buy = fill.side == "BUY"

        if s.side is None:                     # flat → this fill opens the slot
            s.side = "LONG" if buy else "SHORT"
            s.entry_qty = fill.qty
            s.entry_notional = fill.qty * fill.price
            s.opened_at = fill.exec_time
            return None

        if buy == (s.side == "LONG"):          # same direction → an add / partial entry
            s.entry_qty += fill.qty
            s.entry_notional += fill.qty * fill.price
            return None

        # opposite direction → an exit (possibly one of several partials)
        remaining = s.entry_qty - s.exit_qty
        close = min(fill.qty, remaining)
        s.exit_qty += close
        s.exit_notional += close * fill.price
        if exit_reason is not None and s.exit_reason is None:
            s.exit_reason = exit_reason
        if abs(s.exit_qty - s.entry_qty) < _EPS:   # slot FLAT → complete + reset it
            trade = self._complete(s, fill.exec_time)
            self._slots[gate] = Slot(gate=gate)
            return trade
        return None

    def _complete(self, s: Slot, closed_at: str) -> dict:
        ep = s.entry_notional / s.entry_qty
        xp = s.exit_notional / s.exit_qty
        gross = ((xp - ep) if s.side == "LONG" else (ep - xp)) * s.entry_qty * self._vpp
        return {
            "gate": s.gate, "side": s.side, "qty": s.entry_qty,
            "entry_price": ep, "exit_price": xp,
            "opened_at": s.opened_at, "closed_at": closed_at,
            "pnl_usd": gross - self._fee, "fees_usd": self._fee,
            "exit_reason": s.exit_reason or "UNKNOWN",
        }
