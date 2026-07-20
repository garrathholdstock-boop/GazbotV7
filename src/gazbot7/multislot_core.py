"""GAZBOT V7 — multi-slot execution core (the paper-tournament hands).

Ties the SlotBook (per-gate positions over a netted venue) to the order engine +
per-slot stops. Each slot opens/manages/closes independently; every order registers
its coid with the SlotBook so venue fills route back to the right slot; each slot
arms its OWN native 1-ATR stop (a per-slot SafetyManager — the broker places N stops
on the one contract). Inherits today's hardening per slot: capped marketable-limit
IOC entry (no blow-up fill), and the reconcile invariant sum(slots)==venue_net.

BUILT: the intent→order→fill→record + per-slot stop flow; the reconcile drift-halt; and
the **per-slot venue-audit loop** — a COID-KEYED naked-auditor (each slot's own stop
must be a live venue order — aggregate is_naked is meaningless over a netted book),
reprotect-then-flatten, boot-settle grace, and the unverified-protection escalation
(held + can't-read → page + reconnect). This is the critical unbounded-bleed class.
STILL DEFERRED (bounded by the stop, next layer): per-slot time-exits (max-hold /
session-flat) and the per-slot wedge-breaker (stuck-close re-fire). ADOPT-on-boot: a
venue net the empty SlotBook can't attribute → reconcile DRIFT → halt + page (safe; no
guessing which slot owns it). Clean-room.
"""

from __future__ import annotations

import asyncio
import time

from .safety import is_live_status
from .store import record_trade
from .ticks import round_to_tick, tick_for

_EPS = 1e-9
PROTECT_INTERVAL_S = 5.0        # per-slot naked-audit cadence
PROTECT_BOOT_SETTLE_S = 120.0   # grace after (re)start — let a GTC stop reappear before acting
NAKED_FLATTEN_STREAK = 2        # re-arm once, then flatten a slot still naked next cycle
UNVERIFIED_PAGE_CYCLES = 3      # can't read venue while a slot is HELD → page fast
UNVERIFIED_RECONNECT_CYCLES = 6 # → force a fresh session to heal the data path


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
        self._gates = slotbook.gates()
        self._naked_streak: dict[str, int] = {g: 0 for g in self._gates}
        self._boot_mono = time.monotonic()   # boot-settle anchor for the naked auditor
        self._unverified = 0                  # consecutive cycles the venue couldn't be read
        self._unverified_alarmed = False

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

    # ── per-slot naked auditor (the netted-venue safety) ─────────────────────
    def assess_slot(self, gate: str, live_coids: set, now_mono: float) -> str:
        """Is THIS slot protected? Over a netted venue the aggregate is_naked is
        meaningless (a long slot + a short slot net to 0 with 2 different stops), so
        protection is per-slot and COID-KEYED: the slot's own stop must be a live
        working order at the venue. flat | ok | settle | reprotect | flatten.
        Re-arm once, then flatten a slot still naked — never let one bleed unbounded."""
        slot = self._sb.slot(gate)
        if slot.is_flat:
            self._naked_streak[gate] = 0
            return "flat"
        stop = self._safeties[gate].stop_for(self._cfg.symbol)
        if stop is not None and stop.coid in live_coids:
            self._naked_streak[gate] = 0
            return "ok"
        if now_mono - self._boot_mono < PROTECT_BOOT_SETTLE_S:
            return "settle"                       # let a GTC stop reappear after a (re)start
        self._naked_streak[gate] = self._naked_streak.get(gate, 0) + 1
        return "flatten" if self._naked_streak[gate] >= NAKED_FLATTEN_STREAK else "reprotect"

    def _reprotect_slot(self, gate: str) -> None:
        slot = self._sb.slot(gate)
        self._safeties[gate].arm_stop(self._cfg.symbol, side=slot.side, qty=slot.qty,
                                      entry_price=slot.entry_price, atr=slot.entry_atr)
        self._notify(f"naked slot {gate} {slot.side} {slot.qty:g} — re-armed stop "
                     f"(attempt {self._naked_streak[gate]})")

    def _flatten_slot(self, gate: str, reason: str = "NAKED_FLATTEN") -> None:
        slot = self._sb.slot(gate)
        if slot.is_flat or gate in self._closing:
            return
        close_side = "SELL" if slot.side == "LONG" else "BUY"
        coid = self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=slot.qty, order_type="MKT")
        self._sb.register(coid, gate)
        self._closing[gate] = coid
        self._close_reason[gate] = reason
        self._notify(f"NAKED slot {gate} unresolved after {self._naked_streak[gate]} re-arms — FLATTENED")

    async def _read_venue(self, gw):
        """Venue truth: (net position, set of LIVE working-order coids). None if the
        venue can't be read (→ unverified escalation — 'can't check' is never 'safe')."""
        try:
            positions = [p for p in await gw._ib.reqPositionsAsync()
                         if p.contract.symbol == self._cfg.symbol]
            net = sum(p.position for p in positions)
            await gw._ib.reqAllOpenOrdersAsync()
            live = {t.order.orderRef for t in gw._ib.openTrades()
                    if getattr(t.contract, "symbol", None) == self._cfg.symbol
                    and is_live_status(t.orderStatus.status)}
            return net, live
        except Exception:
            return None

    def _on_unverified(self, gw) -> None:
        """A slot is HELD but the venue snapshot couldn't be read — escalate, never
        silent-skip (the 2026-07-17 naked-bleed class). Page fast, then heal the session."""
        if not self._sb.any_held():
            self._unverified = 0
            self._unverified_alarmed = False
            return
        self._unverified += 1
        if self._unverified >= UNVERIFIED_PAGE_CYCLES and not self._unverified_alarmed:
            self._unverified_alarmed = True
            self._notify(f"CANNOT VERIFY slot protection ({self._unverified} cycles) — CHECK IBKR / flatten")
        if self._unverified >= UNVERIFIED_RECONNECT_CYCLES and self._unverified % UNVERIFIED_RECONNECT_CYCLES == 0:
            gw.force_reconnect()

    async def venue_audit_loop(self, gw, *, interval_s: float = PROTECT_INTERVAL_S,
                               max_cycles: int | None = None) -> None:
        i = 0
        while max_cycles is None or i < max_cycles:
            await asyncio.sleep(interval_s)
            i += 1
            snap = await self._read_venue(gw)
            if snap is None:
                self._on_unverified(gw)
                continue
            self._unverified = 0
            self._unverified_alarmed = False
            net, live_coids = snap
            if self.reconcile(net) == "drift":
                continue                          # a lot unaccounted → halted; operator/adopt
            now = time.monotonic()
            for gate in self._gates:
                verdict = self.assess_slot(gate, live_coids, now)
                if verdict == "reprotect":
                    self._reprotect_slot(gate)
                elif verdict == "flatten":
                    self._flatten_slot(gate)
