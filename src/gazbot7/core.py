"""GAZBOT V7 — the core service: the broker.

Core owns the IBKR **order path** and is the single authority on what we hold:
it connects as the master client (**clientId 0**), drains order *intents* from
strategy, submits them, routes ``execDetailsEvent`` fills through the order
engine → trade tracker → safety, and publishes position / fill / trade / status
back on ``CORE_STATE``. Recording lives here, welded to the fills, so the §274
race stays dead (see tracker.py). Strategy never touches IBKR; it only sends
intents and reads what core publishes.

This is the execution half lifted out of the old single-process ``Desk`` — the
decision half (features → gates → exits) moves to strategy. Core makes no trading
decisions; it validates (one-position guard, ``place_live``, and — layered in the
safety drops — kill-switch/session/naked/reconcile gates) and executes.

The P0 protection spine (tick-rounding, orderStatus/error reject handling, the
naked auditor) lands on this order path next. Clean-room.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime

from .broker_adapter import IBBrokerAdapter, execution_to_fill
from .config import RunConfig
from .deciders import Position
from .engine import OrderEngine
from .ib_gateway import IBGateway
from .ipc import (
    CORE_STATE,
    INTENTS,
    T_FILL,
    T_INTENT_RESULT,
    T_POSITION,
    T_STATUS,
    T_TRADE,
    Publisher,
    PullServer,
)
from . import pnl, session
from .sdnotify import sd_notify
from .safety import SafetyManager, is_naked, reconcile_verdict, safe_flatten_verdict
from .store import (
    clear_open_position,
    get_open_position,
    open_store,
    record_signal,
    upsert_open_position,
)
from .tracker import TradeTracker

CORE_CLIENT_ID = 0  # master client (reqAutoOpenOrders binding wired in S10)
_EPS = 1e-9
PROTECT_INTERVAL_S = 5.0       # naked-auditor cadence
PROTECT_BOOT_SETTLE_S = 120.0  # grace after start — let a GTC stop reappear before acting
ARM_SETTLE_S = 4.0             # after arming a stop, let it propagate to IBKR before calling naked
EXIT_STUCK_CYCLES = 3          # a close in flight this many cycles without reducing → CRIT
# Protection-unverifiable watchdog (2026-07-17 naked-bleed fix). When a position is
# HELD but the venue snapshot can't be read, escalate instead of silently skipping —
# the incident: reqCurrentTime answered (so healthy/probe/liveness were all green)
# while reqPositions/reqAllOpenOrders failed, so the auditor no-op'd for 3h with no
# alarm and no flatten, and a stop-less position bled unbounded.
UNVERIFIED_PAGE_CYCLES = 3       # ~15s at PROTECT_INTERVAL_S — page the operator fast
UNVERIFIED_RECONNECT_CYCLES = 6  # ~30s — force a fresh session to heal the data path
UNVERIFIED_REPAGE_CYCLES = 60    # ~5min — keep nagging + retry the heal until it clears


class _NoOpBroker:
    """Dry-run broker (place_live off): accepts nothing, touches no account."""

    def place(self, order) -> None: ...
    def cancel(self, coid: str) -> None: ...
    def place_stop(self, *, symbol, side, qty, stop_price) -> str:
        return "dry-run"


class Core:
    """The execution manager: intents in, orders out, position truth published."""

    def __init__(self, cfg: RunConfig, engine, tracker, safety, publisher, store,
                 notifier=None, is_healthy=None, now_fn=None) -> None:
        self._cfg = cfg
        self._oe = engine
        self._tt = tracker
        self._safety = safety
        self._pub = publisher
        self._store = store
        self._notify = notifier or (lambda _m: None)
        self._is_healthy = is_healthy or (lambda: True)  # gateway TRADING-eligible?
        self._now = now_fn or (lambda: datetime.now(UTC))  # injectable clock (tests)
        self._pos: Position | None = None
        self._qty = 0.0
        self._pending_open = False
        self._closing = False
        self._exit_reason: str | None = None
        self._open_atr = 0.0
        self.opened_at: str | None = None
        self._boot_mono = time.monotonic()  # boot-settle anchor for the naked auditor
        self._armed_mono = 0.0  # monotonic of the last stop arm — the confirm-settle anchor
        self._naked_streak = 0
        self._halted = False  # set on reconcile DRIFT — rejects new entries until clean
        self._exit_stuck = 0  # cycles a close has been in flight without reducing
        self._exit_alarmed = False
        self._protect_poke = asyncio.Event()  # a dead stop wakes the auditor instantly
        # protection-unverifiable watchdog (see UNVERIFIED_* constants)
        self._unverified = 0            # consecutive cycles a HELD position couldn't be verified
        self._unverified_alarmed = False
        self._protection_ok = False     # did the last successful audit confirm live coverage?
        self._last_verified_mono = 0.0  # monotonic of the last successful venue verification

    def poke_protection(self, *_a) -> None:
        """Called when a protective stop goes dead — wake the auditor now."""
        self._protect_poke.set()

    @property
    def position(self) -> Position | None:
        return self._pos

    # ── intents ──────────────────────────────────────────────────────────────
    async def on_intent(self, intent: dict) -> None:
        action = intent.get("action")
        iid = intent.get("iid")
        if action == "OPEN":
            await self._open(intent, iid)
        elif action in ("CLOSE", "FLATTEN"):
            await self._close(intent, iid)
        else:
            await self._result(iid, False, f"unknown action {action!r}")

    def _open_reject_reason(self, intent: dict, now) -> str | None:
        """All entry gates in one testable place. None = clear to open. Order:
        halt → health → session → kill-switch → one-position → live → side."""
        if self._halted:
            return "halted (reconcile drift)"
        if not self._is_healthy():
            return "gateway not healthy"
        blk = self._session_block(now)
        if blk:
            return blk
        kill = self._kill_check(now)
        if kill:
            return kill
        if self._pos is not None or self._pending_open:
            return "already in position"
        if not self._cfg.place_live:
            return "place_live off"
        if intent.get("side") not in ("LONG", "SHORT"):
            return f"bad side {intent.get('side')!r}"
        return None

    async def _open(self, intent: dict, iid) -> None:
        gate = intent.get("gate") or "unknown"
        side = intent.get("side")
        reason = self._open_reject_reason(intent, self._now())
        if reason is not None:  # record the block in the funnel (S6), then reject
            record_signal(self._store, symbol=self._cfg.symbol, gate=gate, side=side,
                          outcome="blocked", block_reason=reason)
            return await self._result(iid, False, reason)
        qty = int(intent.get("qty") or self._cfg.size)
        meta = intent.get("meta") or {}
        self._open_atr = float(meta.get("entry_atr") or 0.0)
        self._exit_reason = None
        order_side = "BUY" if side == "LONG" else "SELL"
        coid = self._oe.submit(symbol=self._cfg.symbol, side=order_side, qty=qty, order_type="MKT")
        self._pending_open = True
        record_signal(self._store, symbol=self._cfg.symbol, gate=gate, side=side, outcome="submitted")
        await self._result(iid, True, "submitted", coid=coid)

    async def _close(self, intent: dict, iid) -> None:
        if self._pos is None:
            return await self._result(iid, False, "flat")
        if self._closing:
            return await self._result(iid, False, "already closing")
        if not self._cfg.place_live:
            return await self._result(iid, False, "place_live off")
        self._exit_reason = intent.get("reason") or (
            "FLATTEN" if intent.get("action") == "FLATTEN" else "SIGNAL_CLOSE"
        )
        self._closing = True
        close_side = "SELL" if self._pos.side == "LONG" else "BUY"
        coid = self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=self._qty, order_type="MKT")
        await self._result(iid, True, "closing", coid=coid)

    # ── fills (from execDetailsEvent, in-loop) ───────────────────────────────
    def on_fill(self, fill) -> None:
        sym = self._cfg.symbol
        was_flat = abs(self._tt.net_qty(sym)) < _EPS
        self._oe.on_fill(fill)
        closing = self._pos is not None and self._is_closing_side(fill.side)
        reason = (self._exit_reason or "STOP") if closing else None
        self._tt.apply(fill, exit_reason=reason)
        now_flat = abs(self._tt.net_qty(sym)) < _EPS
        self._emit(T_FILL, {
            "symbol": sym, "side": fill.side, "qty": fill.qty,
            "price": fill.price, "exec_id": fill.exec_id, "exec_time": fill.exec_time,
        })
        if was_flat and not now_flat:
            self._on_opened(fill)
        elif not was_flat and now_flat:
            self._on_closed()
        self._emit(T_POSITION, self._position_payload())

    def _is_closing_side(self, side: str) -> bool:
        if self._pos is None:
            return False
        return (self._pos.side == "LONG" and side == "SELL") or (
            self._pos.side == "SHORT" and side == "BUY"
        )

    def _on_opened(self, fill) -> None:
        sym = self._cfg.symbol
        side = "LONG" if fill.side == "BUY" else "SHORT"
        self._qty = abs(self._tt.net_qty(sym))  # true filled size (venue-derived)
        self._pos = Position(side, fill.price, self._open_atr, 0.0)
        self.opened_at = fill.exec_time
        self._pending_open = False
        # arm the fixed native stop the instant the position opens (zero naked).
        st = self._safety.arm_stop(
            sym, side=side, qty=self._qty, entry_price=fill.price, atr=self._open_atr,
        )
        # CONFIRM the arm (don't fire-and-forget): stamp the settle anchor + poke the
        # auditor to verify the stop is live at IBKR truth. The ARM_SETTLE_S grace lets
        # it propagate first (no double-stop race); a placement that never lands is
        # then caught + re-armed within seconds instead of only by the 5s poll.
        self._armed_mono = time.monotonic()
        self._protect_poke.set()
        # persist the position (esp. entry_atr) so a restart can ADOPT it (S2).
        upsert_open_position(
            self._store, symbol=sym, side=side, qty=self._qty, entry_price=fill.price,
            entry_atr=self._open_atr, opened_at=self.opened_at,
            stop_price=st.stop_price if st else None,
        )

    def _on_closed(self) -> None:
        self._safety.on_flat(self._cfg.symbol)
        clear_open_position(self._store, self._cfg.symbol)
        self._pos = None
        self._qty = 0.0
        self._closing = False
        self._exit_reason = None
        self.opened_at = None
        self._armed_mono = 0.0
        self._exit_stuck = 0
        self._exit_alarmed = False
        self._publish_last_trade()

    # ── naked auditor (S1): protection == fresh IBKR truth, never a local flag ─
    def assess_protection(self, net_qty: float, orders, now_mono: float) -> str:
        """Given IBKR truth (net position + open orders) decide the action:
        flat | ok | settle | reprotect | flatten. Pure — the live loop fetches
        the snapshot and executes the verdict. Reattach twice, then flatten."""
        if self._pos is None or abs(net_qty) < _EPS:
            self._naked_streak = 0
            return "flat"
        side = "LONG" if net_qty > 0 else "SHORT"
        if not is_naked(side, net_qty, orders):
            self._naked_streak = 0
            return "ok"
        if now_mono - self._boot_mono < PROTECT_BOOT_SETTLE_S:
            return "settle"  # let a GTC stop re-appear after a (re)start before acting
        if self._armed_mono and now_mono - self._armed_mono < ARM_SETTLE_S:
            return "settle"  # a just-armed stop may still be propagating to IBKR — don't double-arm
        self._naked_streak += 1
        return "flatten" if self._naked_streak >= 2 else "reprotect"

    def _verify_ok(self) -> None:
        """A cycle obtained fresh venue truth → clear the unverifiable watchdog."""
        self._unverified = 0
        self._unverified_alarmed = False
        self._last_verified_mono = time.monotonic()

    def _on_unverified_protection(self, gw) -> None:
        """A held position whose protection could NOT be verified this cycle (gateway
        unhealthy, probe failed, or the venue snapshot threw). A FLAT desk has nothing
        at risk — stay silent. A HELD one must escalate: page fast, then force a fresh
        session to heal the (zombie) data path so the naked auditor can resume. This is
        the fix for the silent 3h no-op — 'can't check' must never read as 'all clear'."""
        if self._pos is None:
            self._unverified = 0
            self._unverified_alarmed = False
            return
        self._unverified += 1
        self._protection_ok = False
        if self._unverified >= UNVERIFIED_PAGE_CYCLES and (
                not self._unverified_alarmed or self._unverified % UNVERIFIED_REPAGE_CYCLES == 0):
            self._unverified_alarmed = True
            self._notify(f"CANNOT VERIFY protection on held {self._cfg.symbol} {self._pos.side} "
                         f"{self._qty:g} — venue snapshot failing {self._unverified} cycles while "
                         f"conn reads healthy. Healing session; CHECK IBKR / flatten if it persists.")
        if self._unverified >= UNVERIFIED_RECONNECT_CYCLES and \
                self._unverified % UNVERIFIED_RECONNECT_CYCLES == 0:
            gw.force_reconnect()  # rebuild the session → next cycle's snapshot should answer

    def _reprotect(self) -> None:
        p = self._pos
        if p is not None:
            self._safety.arm_stop(self._cfg.symbol, side=p.side, qty=self._qty,
                                  entry_price=p.entry_price, atr=p.entry_atr)
            self._armed_mono = time.monotonic()  # a re-arm gets its own confirm-settle

    def _emergency_flatten(self, reason: str = "NAKED_FLATTEN", venue_net: float | None = None) -> None:
        if self._pos is None or self._closing:
            return  # never double-submit a close
        if venue_net is not None:
            verdict = safe_flatten_verdict(venue_net)  # fire ONLY what IBKR holds
            if verdict is None:
                return  # IBKR already flat — a close here would open a position
            close_side, qty = verdict
        else:  # no venue snapshot to hand — fall back to the tracked position
            close_side = "SELL" if self._pos.side == "LONG" else "BUY"
            qty = self._qty
        self._exit_reason = reason
        self._closing = True
        self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=qty, order_type="MKT")

    # ── kill-switches (S8) ────────────────────────────────────────────────────
    def _kill_check(self, now) -> str | None:
        """Bound the catastrophic day. Computed fresh from realized P&L each open,
        so a breach stays tripped for the session (realized losses don't un-realize;
        a halted desk takes no trade that could reset the streak)."""
        day_pnl, _n, _w = pnl.day(self._store, self._cfg.symbol, now)
        limit = self._cfg.max_daily_loss_usd
        if limit > 0 and day_pnl <= -limit:
            return f"daily loss limit (${day_pnl:.0f} ≤ −${limit:.0f})"
        k = self._cfg.loss_streak_halt
        if k > 0:
            ph = ",".join("?" * len(pnl._CLEANUP_REASONS))  # exclude cleanup (ADOPT_FLATTEN)
            rows = self._store.execute(
                f"SELECT pnl_usd FROM trades WHERE symbol=? AND exit_reason NOT IN ({ph}) "
                f"ORDER BY id DESC LIMIT ?",
                (self._cfg.symbol, *pnl._CLEANUP_REASONS, k),
            ).fetchall()
            if len(rows) == k and all(r[0] < 0 for r in rows):
                return f"loss streak ({k} in a row)"
        return None

    # ── session discipline (S4) ───────────────────────────────────────────────
    def _session_block(self, now) -> str | None:
        if not session.is_open(now):
            return "market closed"
        if session.in_no_open_window(now, self._cfg.no_open_minutes):
            return "no-open window (session end)"
        return None

    def over_max_hold(self, now) -> bool:
        if self._pos is None or not self.opened_at:
            return False
        try:
            opened = datetime.fromisoformat(self.opened_at)
        except Exception:
            return False
        return (now - opened).total_seconds() / 60.0 >= self._cfg.max_hold_minutes

    def _exit_watchdog(self, venue_net: float) -> None:
        """A close is in flight. The ``_closing`` latch already prevents the
        re-fire walk (V5's +1→−101); this alarms if the exit isn't *completing* —
        the position hasn't reduced after EXIT_STUCK_CYCLES. Detect + page (the
        operator reconciles at IBKR), don't auto-thrash."""
        if self._pos is not None and abs(venue_net) > _EPS:
            self._exit_stuck += 1
            if self._exit_stuck >= EXIT_STUCK_CYCLES and not self._exit_alarmed:
                self._exit_alarmed = True
                self._notify(f"EXIT_NOT_COMPLETING {self._cfg.symbol}: {venue_net:g} not reducing "
                             f"after {self._exit_stuck} cycles — reconcile + flatten at IBKR")

    def _time_exit_check(self, venue_net: float) -> None:
        now = self._now()
        if self.over_max_hold(now):
            self._emergency_flatten("MAX_HOLD", venue_net)
            self._notify(f"{self._cfg.symbol} max-hold ({self._cfg.max_hold_minutes:g}m) — flattening")
        elif session.should_flatten(now, self._cfg.session_flat_minutes):
            self._emergency_flatten("SESSION_END_FLAT", venue_net)
            self._notify(f"{self._cfg.symbol} session-end — flattening")

    async def _read_venue_protection(self, gw):
        try:
            positions = [p for p in await gw._ib.reqPositionsAsync()
                         if p.contract.symbol == self._cfg.symbol]
            net = sum(p.position for p in positions)
            # IBKR avgCost is per-contract → per-unit for the tracker entry price
            avg = (positions[0].avgCost / self._cfg.value_per_point
                   if positions and abs(positions[0].position) > _EPS and self._cfg.value_per_point else None)
            await gw._ib.reqAllOpenOrdersAsync()
            orders = [
                (t.order.orderType, t.order.action, t.orderStatus.status, t.order.totalQuantity)
                for t in gw._ib.openTrades()
                if getattr(t.contract, "symbol", None) == self._cfg.symbol
            ]
            return net, orders, avg
        except Exception:
            return None  # a bad/timed-out snapshot → never act on it

    # ── reconcile / adopt (S2): tracker == IBKR truth ────────────────────────
    def adopt_from_venue(self, net_qty: float, avg_price: float | None = None) -> str:
        """Take over a venue position the desk isn't tracking (restart / manual).
        Side + qty come from IBKR truth; entry_price + entry_atr from the persisted
        open_position when available (IBKR can't tell us the ATR), else IBKR's
        avg cost. ALWAYS seeds the tracker so a later close reconciles cleanly.
        Returns 'adopted' (re-armed) or 'flatten' (no trustworthy stop distance →
        close it, recorded as an honest ADOPT_FLATTEN trade)."""
        sym = self._cfg.symbol
        side = "LONG" if net_qty > 0 else "SHORT"
        qty = abs(net_qty)
        rec = get_open_position(self._store, sym)
        recoverable = bool(rec and rec["entry_atr"] and rec["entry_atr"] > 0 and rec["side"] == side)
        if recoverable:
            entry_price, entry_atr, opened_at = rec["entry_price"], rec["entry_atr"], rec["opened_at"]
        else:
            entry_price = avg_price if avg_price is not None else (rec["entry_price"] if rec else 0.0)
            entry_atr, opened_at = 0.0, (rec["opened_at"] if rec else self._now().isoformat())
        self._tt.adopt(sym, side, qty, entry_price, opened_at)  # seed the tracker (fixes mis-book)
        self._pos = Position(side, entry_price, entry_atr, 0.0)
        self._qty = qty
        self._open_atr = entry_atr
        self.opened_at = opened_at
        if recoverable:
            st = self._safety.arm_stop(sym, side=side, qty=qty, entry_price=entry_price, atr=entry_atr)
            upsert_open_position(self._store, symbol=sym, side=side, qty=qty, entry_price=entry_price,
                                 entry_atr=entry_atr, opened_at=opened_at, stop_price=st.stop_price if st else None)
            return "adopted"
        # un-adoptable → flatten the now-tracked position (fill closes it cleanly)
        self._exit_reason = "ADOPT_FLATTEN"
        self._closing = True
        self._oe.submit(symbol=sym, side="SELL" if side == "LONG" else "BUY", qty=qty, order_type="MKT")
        return "flatten"

    def _handle_adopt(self, net_qty: float, avg_price: float | None = None) -> None:
        if self.adopt_from_venue(net_qty, avg_price) == "adopted":
            self._notify(f"adopted {self._cfg.symbol} {net_qty:g} from venue + re-armed stop")
        else:
            self._notify(f"adopt {self._cfg.symbol} {net_qty:g}: no recoverable protection — FLATTENING")

    async def _fetch_unseen_fills(self, gw) -> list:
        """Venue executions for our symbol NOT yet applied to the tracker — i.e. the
        closing fills of a position that vanished off our own execDetails stream
        (a manual flatten / eod_flatten / a stop fill we missed). Filtered by exec_id
        so an already-applied entry can never be double-counted."""
        try:
            from ib_async import ExecutionFilter
            rows = await gw._ib.reqExecutionsAsync(ExecutionFilter())
        except Exception:
            return []
        out = []
        for r in rows:
            ex = getattr(r, "execution", None)
            if ex is None or getattr(r.contract, "symbol", None) != self._cfg.symbol:
                continue
            if self._tt.has_applied(ex.execId):
                continue
            out.append(execution_to_fill(ex, order_ref=None, symbol=self._cfg.symbol,
                                         time_iso=r.time.isoformat()))
        out.sort(key=lambda f: f.exec_time)
        return out

    async def _reconcile_vanished(self, gw) -> None:
        """Venue is flat but we held — the close happened OFF our fill stream. Feed the
        unseen venue fills through the tracker so the round-trip RECORDS at its real
        exit price + P&L (the one completion path), instead of silently dropping it
        (the -$405 recording gap). Page if it can't be reconstructed; then clear."""
        sym = self._cfg.symbol
        for f in await self._fetch_unseen_fills(gw):
            self._tt.apply(f, exit_reason="RECONCILED_CLOSE")
        if abs(self._tt.net_qty(sym)) < _EPS:
            self._notify(f"{sym} closed off-desk — reconstructed the close from venue executions + recorded")
        else:
            self._notify(f"{sym} vanished at venue but the close couldn't be reconstructed from "
                         f"executions — P&L NOT journaled, reconcile manually")
            self._tt.forget(sym)  # drop the dangling open so the next fill doesn't mis-book
        self._clear_phantom()

    def _clear_phantom(self) -> None:
        """Venue is flat but we thought we held — our position closed unseen. Drop
        the phantom held state + cancel any tracked stop. Called after
        ``_reconcile_vanished`` has already recorded the round-trip from venue truth."""
        self._safety.on_flat(self._cfg.symbol)
        clear_open_position(self._store, self._cfg.symbol)
        self._pos = None
        self._qty = 0.0
        self._naked_streak = 0
        self._armed_mono = 0.0
        self._closing = False
        self._exit_stuck = 0
        self._exit_alarmed = False

    async def venue_audit_loop(self, gw) -> None:
        """One fresh IBKR read per cycle drives BOTH reconcile (agreement) and the
        naked auditor (coverage). Freshness-gated by a reqCurrentTime probe — a
        stale/unconfirmed snapshot is skipped, never acted on."""
        while True:
            try:  # wake on a dead-stop poke, else poll every PROTECT_INTERVAL_S
                await asyncio.wait_for(self._protect_poke.wait(), timeout=PROTECT_INTERVAL_S)
            except (TimeoutError, asyncio.TimeoutError):
                pass
            self._protect_poke.clear()
            snap = None
            if gw.healthy and self._cfg.place_live and await gw.probe_alive():
                snap = await self._read_venue_protection(gw)
            if snap is None:
                # Could not verify venue truth this cycle. A flat desk is silent; a
                # HELD position escalates (page + heal) — never a silent skip, which
                # is exactly how a stop-less position bled for 3h (2026-07-17).
                self._on_unverified_protection(gw)
                continue
            self._verify_ok()  # got fresh venue truth → watchdog clear
            net, orders, avg = snap
            verdict = reconcile_verdict(self._pos.side if self._pos else None, self._qty, net)
            if verdict == "adopt":
                self._handle_adopt(net, avg)
                continue
            if verdict == "drift":
                if not self._halted:
                    self._notify(f"DRIFT {self._cfg.symbol}: tracker "
                                 f"{(self._pos.side if self._pos else 'flat')} {self._qty:g} vs "
                                 f"venue {net:g} — HALTED (no new entries)")
                self._halted = True
                continue
            if verdict == "vanished":
                await self._reconcile_vanished(gw)  # record the off-desk close, don't drop its P&L
                continue
            # match — a clean cycle clears any halt, then manage the position
            self._halted = False
            if self._pos is not None:
                if self._closing:
                    self._exit_watchdog(net)  # a close is in flight — is it completing?
                else:
                    action = self.assess_protection(net, orders, time.monotonic())
                    self._protection_ok = action == "ok"  # confirmed live coverage this cycle
                    if action == "reprotect":
                        self._reprotect()
                        self._notify(f"naked {self._cfg.symbol} — re-armed stop (attempt {self._naked_streak})")
                    elif action == "flatten":
                        self._emergency_flatten("NAKED_FLATTEN", net)
                        self._notify(f"NAKED {self._cfg.symbol} unresolved after {self._naked_streak} "
                                     f"re-arms — FLATTENED")
                    else:  # protected — enforce the time exits (max-hold / session-end)
                        self._time_exit_check(net)

    # ── publishing ───────────────────────────────────────────────────────────
    def _position_payload(self) -> dict:
        sym = self._cfg.symbol
        if self._pos is None:
            return {"symbol": sym, "flat": True}
        st = self._safety.stop_for(sym)
        return {
            "symbol": sym, "flat": False, "side": self._pos.side, "qty": self._qty,
            "entry": self._pos.entry_price, "atr": self._pos.entry_atr,
            "stop": st.stop_price if st else None, "opened_at": self.opened_at,
        }

    def _publish_last_trade(self) -> None:
        row = self._store.execute(
            "SELECT symbol, side, pnl_usd, exit_reason, closed_at FROM trades "
            "ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if row is not None:
            self._emit(T_TRADE, {
                "symbol": row[0], "side": row[1], "pnl": row[2],
                "exit_reason": row[3], "closed_at": row[4],
            })

    def _emit(self, topic: str, payload: dict) -> None:
        """Fire-and-forget publish from the in-loop fill callback."""
        asyncio.ensure_future(self._pub.send(topic, payload))

    async def publish_status(self, gw: IBGateway) -> None:
        await self._pub.send(T_STATUS, {
            "ts": datetime.now(UTC).isoformat(), "conn": gw.state.value,
            "healthy": gw.healthy, "place_live": self._cfg.place_live,
            "flat": self._pos is None,
        })
        await self._pub.send(T_POSITION, self._position_payload())
        self._write_heartbeat(gw)
        sd_notify("WATCHDOG=1")  # S9: prove the loop is live to systemd's watchdog

    def _protection_status(self) -> dict:
        """Whether a held position is CONFIRMED protected at venue truth, and how
        stale that confirmation is. The sweep reads this — a held-but-unverified
        position must not read 'OK' just because the heartbeat is fresh."""
        if self._pos is None:
            return {"held": False}
        age = round(time.monotonic() - self._last_verified_mono, 1) if self._last_verified_mono else None
        return {"held": True, "verified": self._protection_ok,
                "verified_age_s": age, "unverified_cycles": self._unverified}

    def _write_heartbeat(self, gw: IBGateway) -> None:
        """Two files, both written every cycle (real wall-clock ts):
        - core_health.json: the liveness file the EXTERNAL monitor reads (S6).
        - status.json: the web-shaped status the dashboard (web.py) reads — conn,
          healthy, place_live, halted, and the live position (None when flat)."""
        ts = datetime.now(UTC).isoformat()
        data_dir = os.path.dirname(self._cfg.store_path) or "."
        protection = self._protection_status()
        health = {
            "ts": ts, "conn": gw.state.value, "healthy": gw.healthy,
            "place_live": self._cfg.place_live, "flat": self._pos is None, "halted": self._halted,
            "protection": protection,
        }
        status = {
            "ts": ts, "conn": gw.state.value, "healthy": gw.healthy,
            "place_live": self._cfg.place_live, "halted": self._halted,
            "position": None if self._pos is None else self._position_payload(),
            "protection": protection,
        }
        for name, payload in (("core_health.json", health), ("status.json", status)):
            path = os.path.join(data_dir, name)
            try:
                with open(path + ".tmp", "w") as f:
                    json.dump(payload, f)
                os.replace(path + ".tmp", path)
            except Exception:
                pass  # a status write must never break the loop

    async def _result(self, iid, accepted: bool, reason: str, *, coid: str | None = None) -> None:
        await self._pub.send(T_INTENT_RESULT, {
            "iid": iid, "accepted": accepted, "reason": reason, "coid": coid,
        })


# ── service entrypoint ───────────────────────────────────────────────────────
async def _drain_intents(pull: PullServer, core: Core) -> None:
    while True:
        intent = await pull.recv()
        try:
            await core.on_intent(intent)
        except Exception:  # an intent must never kill the drain loop
            pass


async def run(cfg: RunConfig, *, notifier=None, status_interval_s: float = 1.0,
              max_seconds: float | None = None) -> None:
    store = open_store(cfg.store_path)
    pub = Publisher(CORE_STATE)
    pull = PullServer(INTENTS)
    gw = IBGateway(cfg.host, cfg.port, client_id=CORE_CLIENT_ID, readonly=not cfg.place_live)
    core_ref: dict = {}

    async def _reassert(ib):  # S3: runs on the initial connect AND every reconnect
        if cfg.place_live:
            try:
                ib.reqAutoOpenOrders(True)  # master binds ALL orders — sees the EOD-timer
            except Exception:                # flatten + manual fills; cross-restart cancel
                pass
        c = core_ref.get("core")
        if c is not None:
            c.poke_protection()  # re-verify position + coverage immediately after reconnect

    gw.on_reconnect(_reassert)
    await gw.start()

    from ib_async import ContFuture

    (contract,) = await gw._ib.qualifyContractsAsync(ContFuture(cfg.symbol, cfg.exchange))

    broker = (
        IBBrokerAdapter(
            gw._ib, contract, cfg.symbol,
            on_fill=lambda f: core_ref["core"].on_fill(f),
            on_stop_event=lambda coid, status: core_ref["core"].poke_protection(),
        )
        if cfg.place_live else _NoOpBroker()
    )
    engine = OrderEngine(broker, store)
    tracker = TradeTracker(store, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt, gate=cfg.gate)
    safety = SafetyManager(broker, notifier=notifier)
    core = Core(cfg, engine, tracker, safety, pub, store, notifier=notifier,
                is_healthy=lambda: gw.healthy)  # S3 trading-eligibility gate
    core_ref["core"] = core

    # boot reconcile (S2): adopt any position IBKR holds before accepting intents,
    # so a restart mid-position re-arms rather than orphaning. Freshness-gated.
    if cfg.place_live and await gw.probe_alive():
        boot = await core._read_venue_protection(gw)
        if boot is not None and abs(boot[0]) > _EPS:
            core._handle_adopt(boot[0], boot[2])  # net, avg_cost

    intents_task = asyncio.ensure_future(_drain_intents(pull, core))
    protect_task = asyncio.ensure_future(core.venue_audit_loop(gw))  # S1 naked + S2 reconcile
    liveness_task = asyncio.ensure_future(gw.liveness_loop())        # S3 zombie guard
    sd_notify("READY=1")  # S9: Type=notify — core is up (no-op outside systemd)
    start = time.monotonic()
    try:
        while max_seconds is None or (time.monotonic() - start) < max_seconds:
            await core.publish_status(gw)
            await asyncio.sleep(status_interval_s)
    finally:
        intents_task.cancel()
        protect_task.cancel()
        liveness_task.cancel()
        await gw.stop()
        pub.close()
        pull.close()
        store.close()


def _telegram_notifier(msg: str) -> None:
    from .notify import notify
    notify(f"[V7-core] {msg}", critical=True)  # core alerts are all safety — always send


def main() -> None:  # `python -m gazbot7.core`  (GAZBOT7_PLACE_LIVE=1 to trade)
    live = os.environ.get("GAZBOT7_PLACE_LIVE") == "1"
    cfg = RunConfig(place_live=live, client_id=CORE_CLIENT_ID)
    asyncio.run(run(cfg, notifier=_telegram_notifier))


if __name__ == "__main__":
    main()
