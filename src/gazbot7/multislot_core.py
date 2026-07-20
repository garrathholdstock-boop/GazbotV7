"""GAZBOT V7 — multi-slot execution core (the paper-tournament hands).

Ties the SlotBook (per-gate positions over a netted venue) to the order engine +
per-slot stops. Each slot opens/manages/closes independently; every order registers
its coid with the SlotBook so venue fills route back to the right slot; each slot
arms its OWN native 1-ATR stop (a per-slot SafetyManager — the broker places N stops
on the one contract). Inherits today's hardening per slot: capped marketable-limit
IOC entry (no blow-up fill), and the reconcile invariant sum(slots)==venue_net.

SCOPE (first cut): the intent→order→fill→record + per-slot stop flow + reconcile.
DEFERRED (documented follow-up, PAPER_TOURNAMENT_SCOPE §4): the async venue-audit loop
— per-slot naked-auditor, adopt-on-boot, and the wedge-breaker — over the netted book.
For now a slot's loss floor is its stop-armed-on-open + the drift halt; the auditor
hardening is the next layer before this ever fronts real money. Clean-room.
"""

from __future__ import annotations

import time

from .store import record_trade
from .ticks import round_to_tick, tick_for


class MultiSlotCore:
    def __init__(self, cfg, engine, slotbook, safeties, publisher, store, *, notifier=None) -> None:
        self._cfg = cfg
        self._oe = engine
        self._sb = slotbook                 # SlotBook
        self._safeties = safeties           # dict[gate -> SafetyManager] (per-slot stops)
        self._pub = publisher
        self._store = store
        self._notify = notifier or (lambda _m: None)
        self._pending: dict[str, str] = {}      # gate -> in-flight OPEN coid
        self._pending_mono: dict[str, float] = {}
        self._closing: dict[str, str] = {}      # gate -> in-flight CLOSE coid
        self._close_reason: dict[str, str] = {}
        self._open_atr: dict[str, float] = {}
        self._halted = False

    # ── intents in ───────────────────────────────────────────────────────────
    async def on_intents(self, intents: list[dict]) -> None:
        for intent in intents:
            if intent.get("action") == "OPEN":
                self._open(intent)
            elif intent.get("action") == "CLOSE":
                self._close(intent)

    def _open(self, intent: dict) -> None:
        gate = intent["slot"]
        if self._halted or not self._sb.slot(gate).is_flat or gate in self._pending:
            return                           # halted, slot occupied, or an open already in flight
        side = intent["side"]
        qty = int(intent.get("qty") or 1)
        if qty <= 0 or not self._cfg.place_live:
            return
        self._open_atr[gate] = float((intent.get("meta") or {}).get("entry_atr") or 0.0)
        order_side = "BUY" if side == "LONG" else "SELL"
        ref = intent.get("price")
        buf = self._cfg.entry_limit_buffer_pts
        if ref and buf > 0:                  # capped marketable-limit IOC (inherited)
            tick = tick_for(self._cfg.symbol)
            raw = (ref + buf) if order_side == "BUY" else (ref - buf)
            px = round_to_tick(raw, tick, mode="ceil" if order_side == "BUY" else "floor")
            coid = self._oe.submit(symbol=self._cfg.symbol, side=order_side, qty=qty,
                                   order_type="LMT", limit_price=px, tif="IOC")
        else:
            coid = self._oe.submit(symbol=self._cfg.symbol, side=order_side, qty=qty, order_type="MKT")
        self._sb.register(coid, gate)        # route this slot's fills back to it
        self._pending[gate] = coid
        self._pending_mono[gate] = time.monotonic()

    def _close(self, intent: dict) -> None:
        gate = intent["slot"]
        slot = self._sb.slot(gate)
        if slot.is_flat or gate in self._closing or not self._cfg.place_live:
            return
        close_side = "SELL" if slot.side == "LONG" else "BUY"
        coid = self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=slot.qty, order_type="MKT")
        self._sb.register(coid, gate)
        self._closing[gate] = coid
        self._close_reason[gate] = intent.get("reason") or "SIGNAL_CLOSE"

    # ── fills in (route via the SlotBook) ────────────────────────────────────
    def on_fill(self, fill) -> None:
        gate = self._sb.owner(fill.order_id)
        if gate is None:
            self._notify(f"unattributed fill {fill.exec_id} (coid {fill.order_id}) — no slot")
            return
        slot = self._sb.slot(gate)
        was_flat = slot.is_flat
        closing = (not was_flat) and self._is_closing_side(slot.side, fill.side)
        reason = (self._close_reason.get(gate) or "STOP") if closing else None
        trade = self._sb.apply(fill, exit_reason=reason)
        now_flat = self._sb.slot(gate).is_flat
        if was_flat and not now_flat:
            self._on_slot_opened(gate)
        if trade is not None:
            self._on_slot_closed(gate, trade)

    @staticmethod
    def _is_closing_side(slot_side: str, fill_side: str) -> bool:
        return (slot_side == "LONG" and fill_side == "SELL") or (slot_side == "SHORT" and fill_side == "BUY")

    def _on_slot_opened(self, gate: str) -> None:
        self._pending.pop(gate, None)
        self._pending_mono.pop(gate, None)
        slot = self._sb.slot(gate)
        slot.entry_atr = self._open_atr.get(gate, 0.0)   # for the manage layer's exit stack
        sm = self._safeties[gate]
        sm.arm_stop(self._cfg.symbol, side=slot.side, qty=slot.qty,
                    entry_price=slot.entry_price, atr=slot.entry_atr)   # this slot's native 1-ATR stop

    def _on_slot_closed(self, gate: str, trade: dict) -> None:
        self._safeties[gate].on_flat(self._cfg.symbol)   # cancel + forget THIS slot's stop
        record_trade(
            self._store, symbol=self._cfg.symbol, side=trade["side"], qty=trade["qty"],
            entry_price=trade["entry_price"], exit_price=trade["exit_price"],
            opened_at=trade["opened_at"], closed_at=trade["closed_at"],
            pnl_usd=trade["pnl_usd"], fees_usd=trade["fees_usd"],
            exit_reason=trade["exit_reason"], gate=trade["gate"],
        )
        self._closing.pop(gate, None)
        self._close_reason.pop(gate, None)

    # ── reconcile (the safety invariant) ─────────────────────────────────────
    def reconcile(self, venue_net: float) -> str:
        """Logical net across slots MUST equal venue truth. On drift → HALT (no new
        opens) — a lot leaked/appeared at the venue that the slot ledger can't place."""
        verdict = self._sb.reconcile(venue_net)
        if verdict == "drift" and not self._halted:
            self._halted = True
            self._notify(f"SLOT DRIFT: logical net {self._sb.net_qty():g} != venue {venue_net:g} — HALTED")
        elif verdict == "match":
            self._halted = False
        return verdict
