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

DURABLE LEDGER (restart-survivable per-slot P&L): every order coid is attributed to its
gate in the store, and each open slot's position (side/qty/entry-VWAP/entry_atr + its live
stop coid/price) is snapshotted on every fill. ``reconstruct()`` rebuilds the SlotBook and
re-attaches each stop from OUR ledger on boot — the netted venue can't (a long slot + a
short slot show net 0). The venue net is then only the reconcile tripwire: if it disagrees
with the reconstructed logical net → DRIFT → halt + page (safe; no guessing which slot owns
a venue-only lot). Fills are recorded before applying, so a redelivery across a restart is
idempotent.

TIME-EXITS + WEDGE-BREAKER (per slot): ``time_exit_check`` cuts every open slot at the
session-end window (flat before the 17:00 ET close) and any single slot past its own
max-hold ceiling; ``exit_watchdog_slot`` escalates a slot whose close went in-flight but
never completed (page → re-fire the flatten, cancelling the dangling order first → force
reconnect) — the 2026-07-20 wedge, bounded per slot. Both run in the venue-audit loop.
Clean-room.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime

from . import session
from .safety import is_live_status
from .store import (
    clear_slot_position,
    get_slot_orders,
    get_slot_positions,
    record_fill,
    record_signal,
    record_slot_order,
    record_trade,
    upsert_slot_position,
)
from .ticks import round_to_tick, tick_for

log = logging.getLogger(__name__)

_EPS = 1e-9
PROTECT_INTERVAL_S = 5.0        # per-slot naked-audit cadence
PROTECT_BOOT_SETTLE_S = 120.0   # grace after (re)start — let a GTC stop reappear before acting
NAKED_FLATTEN_STREAK = 2        # re-arm once, then flatten a slot still naked next cycle
STOP_BREACH_FLATTEN_STREAK = 2  # price past a slot's stop trigger but still held → force-flatten (triggered-but-unfilled stop)
AUDIT_STALE_S = 30.0            # audit loop hasn't COMPLETED a cycle in this long → it's dead/hung (was: silent)
UNVERIFIED_PAGE_CYCLES = 3      # can't read venue while a slot is HELD → page fast
UNVERIFIED_RECONNECT_CYCLES = 6 # → force a fresh session to heal the data path
EXIT_STUCK_CYCLES = 3           # a slot's close in flight this many audit cycles w/o going flat → escalate
EXIT_REFIRE_MAX = 3             # re-fire a wedged slot close this many times before forcing a reconnect


class MultiSlotCore:
    def __init__(self, cfg, engine, slotbook, safeties, publisher, store, *,
                 notifier=None, now_fn=None) -> None:
        self._cfg = cfg
        self._oe = engine
        self._sb = slotbook                 # SlotBook
        self._safeties = safeties           # dict[gate -> SafetyManager] (per-slot stops)
        self._pub = publisher
        self._store = store
        self._notify = notifier or (lambda _m: None)
        self._now = now_fn or (lambda: datetime.now(UTC))   # injectable wall clock (time-exits/tests)
        self._pending: dict[str, str] = {}      # gate -> in-flight OPEN coid
        self._pending_mono: dict[str, float] = {}
        self._pending_side: dict[str, str] = {}  # gate -> side of the in-flight entry (for the nofill signal)
        self._pending_ref: dict[str, float] = {}  # gate -> intended entry ref (for slippage)
        self._closing: dict[str, str] = {}      # gate -> in-flight CLOSE coid
        # ★2026-08-07 close coids CANCELLED because the slot went flat underneath them (its own stop
        # won the race). Kept so a fill that still sneaks through is recognised as a REDUNDANT CLOSE
        # and never mistaken for a fresh entry. Bounded: a close coid matters for seconds, not hours.
        self._voided_closes: dict[str, str] = {}   # coid -> gate
        self._close_reason: dict[str, str] = {}
        self._open_atr: dict[str, float] = {}
        self._halted = False
        self._gates = slotbook.gates()
        self._naked_streak: dict[str, int] = {g: 0 for g in self._gates}
        # per-slot exit wedge-breaker state (a close in flight that never completes)
        self._exit_stuck: dict[str, int] = {g: 0 for g in self._gates}
        self._exit_refires: dict[str, int] = {g: 0 for g in self._gates}
        self._exit_alarmed: dict[str, bool] = {g: False for g in self._gates}
        self._stop_breach_streak: dict[str, int] = {g: 0 for g in self._gates}  # price past a live stop, still held
        self._last_price: float | None = None  # latest tape print — for the triggered-but-unfilled stop guard
        self._boot_mono = time.monotonic()   # boot-settle anchor for the naked auditor
        self._unverified = 0                  # consecutive cycles the venue couldn't be read
        self._unverified_alarmed = False
        # audit-loop liveness: the loop stamps this each non-raising cycle; write_heartbeat exposes
        # its age so a DEAD auditor (2026-07-22: a silent exception killed it → an unmanaged position
        # rode 153min past max-hold while the MAIN heartbeat stayed green) is visible, not silent.
        self._last_audit_ok_mono: float | None = None
        self._audit_alarmed = False

    # ── durable ledger (restart-survivable per-slot P&L) ──────────────────────
    def _register(self, coid: str, gate: str) -> None:
        """Attribute an order coid to its gate, in memory AND durably. Over a netted
        venue the coid is the only reliable fill key; persisting it means an in-flight
        (or native-stop) fill still routes to the right slot after a restart."""
        self._sb.register(coid, gate)
        if self._store is not None:
            record_slot_order(self._store, coid=coid, gate=gate, symbol=self._cfg.symbol)

    def _persist_slot(self, gate: str) -> None:
        """Snapshot a gate's OPEN position (or clear it when flat) so a restart rebuilds
        per-slot truth from OUR ledger — the netted venue can't. Carries entry_atr +
        the live stop coid/price the venue can't hand back."""
        if self._store is None:
            return
        slot = self._sb.slot(gate)
        if slot.is_flat:
            clear_slot_position(self._store, gate)
            return
        stop = self._safeties[gate].stop_for(self._cfg.symbol)
        upsert_slot_position(
            self._store, gate=gate, symbol=self._cfg.symbol, side=slot.side,
            entry_qty=slot.entry_qty, entry_notional=slot.entry_notional,
            exit_qty=slot.exit_qty, exit_notional=slot.exit_notional,
            opened_at=slot.opened_at or "", entry_atr=slot.entry_atr,
            stop_coid=stop.coid if stop else None,
            stop_price=stop.stop_price if stop else None,
        )

    def reconstruct(self) -> list[str]:
        """Rebuild per-slot logical positions + their stops from the durable store after
        a restart. OUR ledger is the source of truth (a netted venue shows a long slot +
        a short slot as net 0 — it can't reconstruct them); the venue net is only the
        reconcile tripwire the audit loop checks. Re-attaches each open slot's stop by
        its stored coid (no fresh place → no duplicate coverage). Returns the open gates.

        If the venue net then disagrees with the reconstructed logical net, the audit
        loop's reconcile fires DRIFT → halt + page (safe: we never guess which slot a
        venue-only lot belongs to)."""
        if self._store is None:
            return []
        for row in get_slot_orders(self._store):      # replay the coid→gate map first
            self._sb.register(row["coid"], row["gate"])
        open_gates: list[str] = []
        for row in get_slot_positions(self._store):
            gate = row["gate"]
            if gate not in self._safeties:
                self._notify(f"stored slot {gate!r} not in this lineup — LEFT for operator")
                continue
            self._sb.restore_slot(
                gate, side=row["side"], entry_qty=row["entry_qty"],
                entry_notional=row["entry_notional"], exit_qty=row["exit_qty"],
                exit_notional=row["exit_notional"], opened_at=row["opened_at"] or "",
                entry_atr=row["entry_atr"],
            )
            if row["stop_coid"] and row["stop_price"] is not None:
                close_side = "SELL" if row["side"] == "LONG" else "BUY"
                self._safeties[gate].restore_stop(
                    self._cfg.symbol, side=close_side,
                    qty=self._sb.slot(gate).qty, stop_price=row["stop_price"],
                    coid=row["stop_coid"],
                )
            open_gates.append(gate)
        if open_gates:
            self._notify(f"reconstructed {len(open_gates)} open slot(s) from store: "
                         f"{open_gates} — venue-audit will reconcile vs IBKR net")
        return open_gates

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
        # ★2026-08-05 ASIA BENCH — placed HERE because _open is the single funnel every tournament
        # entry passes through, so one guard covers all 8 gates and every sub-slot; a per-gate check
        # would have to be repeated and could be missed on the next gate added. NEW ENTRIES ONLY.
        if getattr(self._cfg, "no_open_asia", False):
            from datetime import UTC, datetime as _dtm
            from . import session as _sess
            if _sess.in_asia_block(_dtm.now(UTC)):
                return
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
        self._register(coid, gate)           # route this slot's fills back to it (durably)
        self._pending[gate] = coid
        self._pending_mono[gate] = time.monotonic()
        self._pending_side[gate] = side
        self._pending_ref[gate] = float(ref) if ref else 0.0
        self._signal(gate, side, "submitted", ref)   # "what we said to buy" — once per entry order

    def _close(self, intent: dict) -> None:
        gate = intent["slot"]
        slot = self._sb.slot(gate)
        if slot.is_flat or gate in self._closing or not self._cfg.place_live:
            return
        close_side = "SELL" if slot.side == "LONG" else "BUY"
        coid = self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=slot.qty, order_type="MKT")
        self._register(coid, gate)
        self._closing[gate] = coid
        self._close_reason[gate] = intent.get("reason") or "SIGNAL_CLOSE"

    # ── fills in (route via the SlotBook) ────────────────────────────────────
    def on_fill(self, fill) -> None:
        # Persist the raw execution FIRST — the fills table (idempotent on exec_id) is the
        # guard against a redelivered fill being applied twice across a restart, where the
        # in-memory dedup set is empty. A second delivery returns False here → no-op.
        if self._store is not None and not record_fill(self._store, fill):
            return
        gate = self._sb.owner(fill.order_id)
        if gate is None:
            self._notify(f"unattributed fill {fill.exec_id} (coid {fill.order_id}) — no slot")
            return
        slot = self._sb.slot(gate)
        was_flat = slot.is_flat
        closing = (not was_flat) and self._is_closing_side(slot.side, fill.side)
        reason = (self._close_reason.get(gate) or "STOP") if closing else None
        # ★★2026-08-07 BACKSTOP for the redundant-close race (see _on_slot_closed). If a fill would
        # OPEN a flat slot and its coid is one we already CANCELLED as redundant, this is not an
        # entry — it is a close order that outlived its position and won the cancel race. We still
        # let it open the slot, deliberately: the venue really does hold the contract, and an
        # untracked one is a NAKED position, which is far worse than a tracked one. But we alarm and
        # close it immediately rather than letting it sit behind a stop pretending to be a strategy.
        phantom = was_flat and fill.order_id in self._voided_closes
        trade = self._sb.apply(fill, exit_reason=reason)
        now_flat = self._sb.slot(gate).is_flat
        if was_flat and not now_flat:
            self._on_slot_opened(gate)
            if phantom:
                self._voided_closes.pop(fill.order_id, None)
                self._notify(
                    f"⚠ PHANTOM ENTRY CAUGHT — a cancelled CLOSE for {gate} filled anyway "
                    f"({fill.side} {fill.qty} @ {fill.price}) and opened a position on a flat slot. "
                    f"Closing it immediately. This is the 2026-08-07 13:30 abs_veto_short_B bug; "
                    f"seeing this means the cancel lost the race and the backstop caught it.")
                self._close({"slot": gate, "reason": "PHANTOM_CLOSE"})
        if trade is not None:
            self._on_slot_closed(gate, trade)
        self._persist_slot(gate)             # snapshot (open) or clear (flat) — restart-durable

    @staticmethod
    def _is_closing_side(slot_side: str, fill_side: str) -> bool:
        return (slot_side == "LONG" and fill_side == "SELL") or (slot_side == "SHORT" and fill_side == "BUY")

    def _on_slot_opened(self, gate: str) -> None:
        self._pending.pop(gate, None)
        self._pending_mono.pop(gate, None)
        self._pending_side.pop(gate, None)
        self._pending_ref.pop(gate, None)
        slot = self._sb.slot(gate)
        slot.entry_atr = self._open_atr.get(gate, 0.0)   # for the manage layer's exit stack
        self._signal(gate, slot.side, "filled", slot.entry_price)   # "what we actually bought" (vs the ref)
        sm = self._safeties[gate]
        st = sm.arm_stop(self._cfg.symbol, side=slot.side, qty=slot.qty,
                         entry_price=slot.entry_price, atr=slot.entry_atr)   # this slot's native 1-ATR stop
        self._register(st.coid, gate)        # a stop FILL must attribute to this slot too

    # ── the entry funnel: what we SAY to buy vs what we ACTUALLY buy ───────────
    def _signal(self, gate: str, side: str, outcome: str, price=None) -> None:
        """Log one entry-funnel event to the ``signals`` table (submitted / filled / nofill
        / rejected). This is the desk's signal→fill visibility — the EXEC tab reads it. Only
        the entry path logs (closes/stops aren't 'signals'); each is once-per-entry so the
        table never floods (the ``_pending`` guard dedups the per-tick re-fires)."""
        if self._store is None:
            return
        try:
            record_signal(self._store, symbol=self._cfg.symbol, gate=gate, side=side,
                          outcome=outcome, intended_price=(float(price) if price else None))
        except Exception:
            pass  # visibility logging must never break the trading loop

    def expire_pending_opens(self, now_mono: float) -> None:
        """An entry order (marketable-limit IOC) that submitted but never filled leaves
        ``_pending`` latched forever → that gate can never re-open (silent wedge). After
        ``entry_timeout_s`` with the slot still flat, clear the latch and log a **nofill**
        — the honest 'we said buy but got nothing' (IOC cancelled / thin book / fast move).
        The IOC is already dead at the venue; this just frees the gate + records why."""
        timeout = getattr(self._cfg, "entry_timeout_s", 3.0) or 3.0
        for gate in list(self._pending):
            if not self._sb.slot(gate).is_flat:
                continue                     # a fill is arriving/arrived — _on_slot_opened handles it
            if now_mono - self._pending_mono.get(gate, now_mono) < timeout:
                continue
            side = self._pending_side.pop(gate, "LONG")
            self._pending.pop(gate, None)
            self._pending_mono.pop(gate, None)
            self._pending_ref.pop(gate, None)
            self._signal(gate, side, "nofill", None)
            self._notify(f"entry NOFILL slot {gate} {side} — IOC did not fill, gate freed")

    def _on_slot_closed(self, gate: str, trade: dict) -> None:
        self._safeties[gate].on_flat(self._cfg.symbol)   # cancel + forget THIS slot's stop
        record_trade(
            self._store, symbol=self._cfg.symbol, side=trade["side"], qty=trade["qty"],
            entry_price=trade["entry_price"], exit_price=trade["exit_price"],
            opened_at=trade["opened_at"], closed_at=trade["closed_at"],
            pnl_usd=trade["pnl_usd"], fees_usd=trade["fees_usd"],
            exit_reason=trade["exit_reason"], gate=trade["gate"],
        )
        # ★★2026-08-07 BUGFIX — CANCEL the in-flight close, do not merely forget it.
        # This line used to be a bare pop(). If the slot went flat because its own STOP filled while
        # a MKT close was still working, that close order stayed LIVE at the venue with nothing left
        # to close — and filled into a BRAND NEW POSITION IN THE OPPOSITE DIRECTION.
        # Observed 2026-08-07 13:30 (abs_veto_short_B, -$35.50 real money):
        #   13:30:00.620  MKT BUY placed to close the short   (slot legitimately still short)
        #   13:30:01.057  the slot's OWN stop fills @29724     -> slot flat, trade booked, coid popped
        #   13:30:02.074  the orphaned MKT BUY fills @29712.25 -> on_fill sees a FLAT slot, so
        #                 was_flat=True, closing=False, and it OPENS A LONG on a gate named
        #                 abs_veto_SHORT. A protective SELL stop was then armed for that phantom long.
        # Same family as the 08-06 incident: an order outliving the position it belonged to.
        cl = self._closing.pop(gate, None)
        if cl:
            try:
                self._oe.cancel(cl)          # kill it before it can fill into a fresh position
            except Exception:
                pass                          # cancel is best-effort; the guard in on_fill backstops it
            self._voided_closes[cl] = gate
            if len(self._voided_closes) > 64:     # bounded — drop the oldest insertion
                self._voided_closes.pop(next(iter(self._voided_closes)), None)
        self._close_reason.pop(gate, None)
        self._exit_stuck[gate] = 0            # the close completed → clear the wedge-breaker
        self._exit_refires[gate] = 0
        self._exit_alarmed[gate] = False
        self._stop_breach_streak[gate] = 0

    # ── liveness snapshot (the tournament IS the desk → it owns these files) ──
    def write_heartbeat(self, *, conn: str, healthy: bool) -> None:
        """Write core_health.json + status.json — the liveness/flatness/protection snapshot
        the EXTERNAL monitor, the maintenance sweep, and the web page read. The tournament
        replaces core as the desk, so it takes over these files (a stale file reads as a DEAD
        desk → false CRIT). Per-slot: flat = no slot held; protection lists each held slot +
        whether its own stop coid is recorded. A write must never break the loop."""
        if self._store is None:
            return
        ts = datetime.now(UTC).isoformat()
        data_dir = os.path.dirname(self._cfg.store_path) or "."
        slots = []
        for g in self._gates:
            s = self._sb.slot(g)
            if s.is_flat:
                continue
            stop = self._safeties[g].stop_for(self._cfg.symbol)
            slots.append({"gate": g, "side": s.side, "qty": s.qty,
                          "entry_price": s.entry_price, "entry_atr": s.entry_atr,
                          "opened_at": s.opened_at,
                          "stop_price": stop.stop_price if stop else None,
                          "stop_coid": stop.coid if stop else None})
        held = bool(slots)
        protection = {"held": held, "slots": slots, "unverified_cycles": self._unverified}
        # age of the last COMPLETED audit cycle — the tell for a dead/hung safety loop. None until
        # the loop has run (dry-run / pre-start); the main loop (this writer) stays green regardless,
        # so this is the ONLY signal that the auditor itself stopped.
        audit_age = (round(time.monotonic() - self._last_audit_ok_mono, 1)
                     if self._last_audit_ok_mono is not None else None)
        health = {"ts": ts, "conn": conn, "healthy": healthy,
                  "place_live": self._cfg.place_live, "flat": not held,
                  "halted": self._halted, "protection": protection, "audit_age_s": audit_age}
        status = {**health, "position": slots or None}
        for name, payload in (("core_health.json", health), ("status.json", status)):
            path = os.path.join(data_dir, name)
            try:
                with open(path + ".tmp", "w") as f:
                    json.dump(payload, f)
                os.replace(path + ".tmp", path)
            except Exception:
                pass  # a status write must never break the loop

    def audit_stale(self, threshold_s: float = AUDIT_STALE_S) -> bool:
        """Has the audit loop (the safety spine) gone this long without COMPLETING a cycle?
        The run loop calls this to gate the systemd watchdog ping — a stale auditor → withhold the
        ping → systemd restarts the desk → it re-adopts open slots from the ledger and the revived
        loop fires any overdue max-hold/stop-breach. Returns False before the loop has started
        (None) so the desk doesn't self-restart at boot / on a dry desk."""
        if self._last_audit_ok_mono is None:
            return False
        return (time.monotonic() - self._last_audit_ok_mono) > threshold_s

    # ── per-slot time-exits (never hold overnight / past a ceiling) ───────────
    def over_max_hold(self, gate: str, now) -> bool:
        """Has THIS slot been open past the hard max-hold ceiling? (Per-slot: each gate
        has its own opened_at — a stale grind slot is cut without touching a fresh one.)"""
        slot = self._sb.slot(gate)
        if slot.is_flat or not slot.opened_at:
            return False
        try:
            opened = datetime.fromisoformat(slot.opened_at)
        except ValueError:
            return False
        return (now - opened).total_seconds() / 60.0 >= self._cfg.max_hold_minutes

    def time_exit_check(self, now=None) -> None:
        """Session-end → flatten EVERY open slot (flat before the 17:00 ET close is the
        cardinal rule); else per-slot max-hold → flatten just the stale slot. Each cut is
        the slot's own MKT close, bounded by its native stop until it fills. Idempotent —
        ``_flatten_slot`` no-ops a slot already closing."""
        if not self._cfg.place_live:
            return
        now = now or self._now()
        session_end = session.should_flatten(now, self._cfg.session_flat_minutes)
        for gate in self._gates:
            if self._sb.slot(gate).is_flat:
                continue
            if session_end:
                self._flatten_slot(gate, "SESSION_END_FLAT")
            elif self.over_max_hold(gate, now):
                self._flatten_slot(gate, "MAX_HOLD")

    def claim_check(self) -> None:
        """Operator 'Claim profit' — read data/claim_requests.txt (one gate per line, written
        by the dashboard's PIN-guarded button) and flatten each requested OPEN slot via the SAME
        safe per-slot MKT close as the time-exits. Idempotent; the request file is truncated once
        read (a request for an already-flat/closing slot is simply dropped)."""
        if not self._cfg.place_live:
            return
        path = os.path.join(os.path.dirname(self._cfg.store_path) or ".", "claim_requests.txt")
        try:
            with open(path) as f:
                gates = [ln.strip() for ln in f if ln.strip()]
        except (FileNotFoundError, OSError):
            return
        if not gates:
            return
        for gate in gates:
            if gate in self._gates and not self._sb.slot(gate).is_flat and gate not in self._closing:
                self._flatten_slot(gate, "MANUAL_CLAIM")
        try:
            open(path, "w").close()   # consume all requests
        except OSError:
            pass

    # ── per-slot exit wedge-breaker (a close that never completes) ─────────────
    def exit_watchdog_slot(self, gate: str, gw=None) -> None:
        """A slot's close went in-flight but the slot hasn't gone flat — the 2026-07-20
        wedge, per slot (a dropped/cancelled close left ``_closing`` latched and blocked
        the slot's time-exits). Bounded + idempotent: page once, then re-fire the flatten
        (cancel the dangling close first — no pile-up/oversell) up to EXIT_REFIRE_MAX, then
        force a reconnect and let the cycle retry. NOT a self-restart; every step pages."""
        slot = self._sb.slot(gate)
        if gate not in self._closing or slot.is_flat:
            self._exit_stuck[gate] = 0
            self._exit_alarmed[gate] = False
            self._exit_refires[gate] = 0
            return
        self._exit_stuck[gate] = self._exit_stuck.get(gate, 0) + 1
        if self._exit_stuck[gate] < EXIT_STUCK_CYCLES:
            return
        if not self._exit_alarmed.get(gate):
            self._exit_alarmed[gate] = True
            self._notify(f"EXIT_NOT_COMPLETING slot {gate}: {slot.side} {slot.qty:g} not reducing "
                         f"after {self._exit_stuck[gate]} cycles — re-firing the flatten")
        if self._exit_refires.get(gate, 0) < EXIT_REFIRE_MAX:
            old = self._closing.get(gate)
            if old is not None:
                self._oe.cancel(old)             # kill the stuck order first — no pile-up/oversell
            close_side = "SELL" if slot.side == "LONG" else "BUY"
            coid = self._oe.submit(symbol=self._cfg.symbol, side=close_side,
                                   qty=slot.qty, order_type="MKT")
            self._register(coid, gate)
            self._closing[gate] = coid           # keep the original _close_reason → trade records it
            self._exit_refires[gate] = self._exit_refires.get(gate, 0) + 1
            self._notify(f"slot {gate} exit wedged — re-fired flatten "
                         f"(attempt {self._exit_refires[gate]}/{EXIT_REFIRE_MAX})")
        elif gw is not None:
            self._notify(f"slot {gate} exit STILL wedged after {EXIT_REFIRE_MAX} re-fires — "
                         f"forcing gateway reconnect; CHECK IBKR")
            gw.force_reconnect()
            self._exit_refires[gate] = 0         # fresh session → let the re-fire cycle try again

    def owned_stop_coids(self) -> set[str]:
        """Stop coids the slot book currently depends on — the ONLY stops that must survive an
        orphan sweep. Anything else carrying our `stp-` prefix belongs to no slot and, per the
        standing gap CLAUDE.md names ('the desk never asks: does every live STOP have a slot?'),
        is exactly what fires unattended."""
        out: set[str] = set()
        for g in self._gates:
            if self._sb.slot(g).is_flat:
                continue
            stop = self._safeties[g].stop_for(self._cfg.symbol)
            if stop is not None and stop.coid:
                out.add(stop.coid)
        return out

    # ── reconcile (the safety invariant) ─────────────────────────────────────
    # ★★2026-08-07 THE IBKR ACCOUNT IS SHARED AND THIS INVARIANT DID NOT KNOW IT.
    # The DAY RIDER trades MNQ on clientId 4; the tournament is clientId 0 and receives NONE of its
    # executions, so reconcile compared its own slot total against the WHOLE account net and read the
    # day-rider's lots as an unattributable leak. Live at 14:12Z: day-rider opened SHORT 2, tournament
    # book flat, verdict=drift, HALTED. Unlike the transient 08-06 drift this one CANNOT self-clear —
    # the position is real and held to 20:40Z — so it sidelines the tournament for 6+ hours AND skips
    # its entire safety block (max-hold / naked-audit / re-protect / stop-breach all sit behind
    # != "drift"). The fix is to reconcile against OUR SHARE of the account, not the whole of it.
    DR_STATE = "/home/alphabot/gazbot7/data/day_rider_state.json"
    DR_MAX_AGE_S = 180.0          # heartbeat older than this → do NOT believe the claim

    def _foreign_net(self) -> float:
        """Lots at the venue owned by the DAY RIDER, not by us. Returns 0.0 on ANY doubt.

        ★ FAIL-CLOSED BY CONSTRUCTION. Every failure path returns 0.0, which reproduces the old
        behaviour exactly (halt on drift). Subtracting a position we are not certain about would
        MASK A REAL LEAK — the single thing this invariant exists to catch — so the bar for believing
        the claim is deliberately high: the file must parse, say entered and not closed, carry a
        usable qty and direction, AND have a heartbeat younger than DR_MAX_AGE_S. A dead, stale or
        garbled day-rider cannot excuse a venue position; in that case we halt, as before."""
        try:
            with open(self.DR_STATE) as fh:
                st = json.load(fh)
            if not st.get("entered") or st.get("closed"):
                return 0.0
            qty = abs(float(st.get("qty") or 0.0))
            direction = int(st.get("direction") or 0)
            if qty <= 0 or direction not in (-1, 1):
                return 0.0
            hb = datetime.fromisoformat(str(st.get("heartbeat"))).timestamp()
            if (datetime.now(UTC).timestamp() - hb) > self.DR_MAX_AGE_S:
                return 0.0
            return direction * qty
        except Exception:
            return 0.0

    def reconcile(self, venue_net: float) -> str:
        """Logical net across slots MUST equal venue truth. On drift → HALT (no new
        opens) — a lot leaked/appeared at the venue that the slot ledger can't place.

        ★ "Venue truth" means OUR SHARE of a shared account: the day-rider's declared lots are
        subtracted first (see _foreign_net), because IBKR nets both desks into one number and that
        difference is another desk's position, not a leak."""
        foreign = self._foreign_net()
        if foreign:
            venue_net = venue_net - foreign
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

    # ── triggered-but-unfilled stop guard (2026-07-21, from id114) ────────────
    def note_price(self, price) -> None:
        """Feed the latest tape print AND run the stop as our PRIMARY exit (2026-07-28): check the
        breach every tick (~1s) and flatten fast, instead of waiting ~10s for the 5s audit loop. IBKR
        (esp. PAPER) intermittently never fires a resting stop's trigger even on the concrete Future
        (whyHeld='trigger' → STOP_UNFILLED), so we DON'T rely on it — our tape sees price hit the
        level and we flatten. The native StopLimitOrder stays as a backup (live-account primary + a
        tape-feed-stall backstop); `_flatten_slot`'s `_closing` latch makes the per-tick call
        idempotent. The 5s audit loop still calls `_check_stop_breach` as a second backstop."""
        if price:
            self._last_price = float(price)
            for gate in self._gates:
                self._check_stop_breach(gate)

    def stop_breached(self, gate: str) -> bool:
        """True when price has traded PAST this slot's stop trigger yet the slot is still
        held — a triggered-but-unfilled stop. The naked auditor can't catch this: the stop
        IS a live resting order, it just isn't executing (2026-07-21 id114 — IBKR paper
        converted a triggered STP to a stale unfillable limit; the short rode 84pt to the
        120-min MAX_HOLD, −$171 vs the ~−$44 a filled stop caps). A LONG's stop sits below
        entry (breach = price at/under it); a SHORT's above (price at/over it)."""
        if self._last_price is None:
            return False
        slot = self._sb.slot(gate)
        if slot.is_flat:
            return False
        stop = self._safeties[gate].stop_for(self._cfg.symbol)
        if stop is None or not stop.stop_price:
            return False
        return (self._last_price <= stop.stop_price if slot.side == "LONG"
                else self._last_price >= stop.stop_price)

    def _check_stop_breach(self, gate: str) -> None:
        """Our PRIMARY stop: streak the breach (STOP_BREACH_FLATTEN_STREAK consecutive checks — a
        1-tick spike guard), then market-flatten AT the stop level. Driven per-tick from note_price
        (~2s) with the 5s audit loop as a backstop. Books `STOP` — this IS the stop-out (not a
        failure); we no longer wait for IBKR's paper-flaky resting-stop trigger. `_flatten_slot`
        is idempotent (the `_closing` latch), so repeated per-tick calls fire exactly one close."""
        if self.stop_breached(gate):
            self._stop_breach_streak[gate] += 1
            if self._stop_breach_streak[gate] >= STOP_BREACH_FLATTEN_STREAK:
                sp = self._safeties[gate].stop_for(self._cfg.symbol)
                self._notify(f"STOP slot {gate}: price {self._last_price:g} hit stop {sp.stop_price:g} "
                             f"— flattening (tape-primary stop)")
                self._flatten_slot(gate, "STOP")
        else:
            self._stop_breach_streak[gate] = 0

    def _reprotect_slot(self, gate: str) -> None:
        slot = self._sb.slot(gate)
        st = self._safeties[gate].arm_stop(self._cfg.symbol, side=slot.side, qty=slot.qty,
                                           entry_price=slot.entry_price, atr=slot.entry_atr)
        self._register(st.coid, gate)        # new stop coid → attribute + persist
        self._persist_slot(gate)             # snapshot the new stop_coid/price for restart
        self._notify(f"naked slot {gate} {slot.side} {slot.qty:g} — re-armed stop "
                     f"(attempt {self._naked_streak[gate]})")

    def _flatten_slot(self, gate: str, reason: str = "NAKED_FLATTEN") -> None:
        slot = self._sb.slot(gate)
        if slot.is_flat or gate in self._closing:
            return
        close_side = "SELL" if slot.side == "LONG" else "BUY"
        coid = self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=slot.qty, order_type="MKT")
        self._register(coid, gate)
        self._closing[gate] = coid
        self._close_reason[gate] = reason
        self._notify(f"FLATTEN slot {gate} {slot.side} {slot.qty:g} — {reason}")

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
        # This loop IS the safety spine (naked-audit, drift-halt, max-hold, stop-breach). If it
        # dies, positions go unmanaged while the main heartbeat still reads green (2026-07-22). So
        # every cycle is exception-GUARDED (a throw pages + CONTINUES, never kills the task) and
        # stamps _last_audit_ok_mono on completion → write_heartbeat exposes the age → sweep CRITs
        # if it goes stale. A dead/hung auditor can no longer hide behind the main loop's heartbeat.
        self._last_audit_ok_mono = time.monotonic()      # baseline: loop is up
        i = 0
        while max_cycles is None or i < max_cycles:
            await asyncio.sleep(interval_s)
            i += 1
            cycle_ok = False
            try:
                snap = await self._read_venue(gw)
                if snap is None:
                    self._on_unverified(gw)              # venue unreadable — handled (not a dead auditor)
                else:
                    self._unverified = 0
                    self._unverified_alarmed = False
                    net, live_coids = snap
                    if self.reconcile(net) != "drift":   # drift → halted (handled); else run the exits
                        self.time_exit_check()            # session-end / per-slot max-hold cuts
                        self.claim_check()                # operator 'Claim profit' per-slot flatten
                        now = time.monotonic()
                        for gate in self._gates:
                            verdict = self.assess_slot(gate, live_coids, now)
                            if verdict == "reprotect":
                                self._reprotect_slot(gate)
                            elif verdict == "flatten":
                                self._flatten_slot(gate)
                            self._check_stop_breach(gate)      # live stop but price ran past it
                            self.exit_watchdog_slot(gate, gw)  # escalate a close that isn't completing
                cycle_ok = True                          # reached here without raising → auditor ran
                self._audit_alarmed = False
            except Exception:
                log.exception("venue_audit_loop cycle raised — auditor CONTINUES (not dead)")
                if not self._audit_alarmed:              # page once per error-run, not every 5s
                    self._audit_alarmed = True
                    self._notify("AUDIT_LOOP_ERROR: a venue-audit cycle raised — safety checks "
                                 "(max-hold/stop-breach/naked) SKIPPED this cycle; loop continues. "
                                 "A persistent error → stale audit_age → sweep CRIT. Investigate.")
            if cycle_ok:
                self._last_audit_ok_mono = time.monotonic()
