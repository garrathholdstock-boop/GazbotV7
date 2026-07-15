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
import os
import subprocess
import time
from datetime import UTC, datetime

from .broker_adapter import IBBrokerAdapter
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
from .safety import SafetyManager, is_naked, reconcile_verdict
from .store import clear_open_position, get_open_position, open_store, upsert_open_position
from .tracker import TradeTracker

CORE_CLIENT_ID = 0  # master client (reqAutoOpenOrders binding wired in S10)
_EPS = 1e-9
PROTECT_INTERVAL_S = 5.0       # naked-auditor cadence
PROTECT_BOOT_SETTLE_S = 120.0  # grace after start — let a GTC stop reappear before acting


class _NoOpBroker:
    """Dry-run broker (place_live off): accepts nothing, touches no account."""

    def place(self, order) -> None: ...
    def cancel(self, coid: str) -> None: ...
    def place_stop(self, *, symbol, side, qty, stop_price) -> str:
        return "dry-run"


class Core:
    """The execution manager: intents in, orders out, position truth published."""

    def __init__(self, cfg: RunConfig, engine, tracker, safety, publisher, store,
                 notifier=None, is_healthy=None) -> None:
        self._cfg = cfg
        self._oe = engine
        self._tt = tracker
        self._safety = safety
        self._pub = publisher
        self._store = store
        self._notify = notifier or (lambda _m: None)
        self._is_healthy = is_healthy or (lambda: True)  # gateway TRADING-eligible?
        self._pos: Position | None = None
        self._qty = 0.0
        self._pending_open = False
        self._closing = False
        self._exit_reason: str | None = None
        self._open_atr = 0.0
        self.opened_at: str | None = None
        self._boot_mono = time.monotonic()  # boot-settle anchor for the naked auditor
        self._naked_streak = 0
        self._halted = False  # set on reconcile DRIFT — rejects new entries until clean
        self._protect_poke = asyncio.Event()  # a dead stop wakes the auditor instantly

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

    async def _open(self, intent: dict, iid) -> None:
        if self._halted:
            return await self._result(iid, False, "halted (reconcile drift)")
        if not self._is_healthy():
            return await self._result(iid, False, "gateway not healthy")
        if self._pos is not None or self._pending_open:
            return await self._result(iid, False, "already in position")
        if not self._cfg.place_live:
            return await self._result(iid, False, "place_live off")
        side = intent.get("side")
        if side not in ("LONG", "SHORT"):
            return await self._result(iid, False, f"bad side {side!r}")
        qty = int(intent.get("qty") or self._cfg.size)
        meta = intent.get("meta") or {}
        self._open_atr = float(meta.get("entry_atr") or 0.0)
        self._exit_reason = None
        order_side = "BUY" if side == "LONG" else "SELL"
        coid = self._oe.submit(symbol=self._cfg.symbol, side=order_side, qty=qty, order_type="MKT")
        self._pending_open = True
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
        self._naked_streak += 1
        return "flatten" if self._naked_streak >= 2 else "reprotect"

    def _reprotect(self) -> None:
        p = self._pos
        if p is not None:
            self._safety.arm_stop(self._cfg.symbol, side=p.side, qty=self._qty,
                                  entry_price=p.entry_price, atr=p.entry_atr)

    def _emergency_flatten(self) -> None:
        if self._pos is None:
            return
        self._exit_reason = "NAKED_FLATTEN"
        self._closing = True
        close_side = "SELL" if self._pos.side == "LONG" else "BUY"
        self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=self._qty, order_type="MKT")

    async def _read_venue_protection(self, gw):
        try:
            positions = await gw._ib.reqPositionsAsync()
            net = sum(p.position for p in positions if p.contract.symbol == self._cfg.symbol)
            await gw._ib.reqAllOpenOrdersAsync()
            orders = [
                (t.order.orderType, t.order.action, t.orderStatus.status, t.order.totalQuantity)
                for t in gw._ib.openTrades()
                if getattr(t.contract, "symbol", None) == self._cfg.symbol
            ]
            return net, orders
        except Exception:
            return None  # a bad/timed-out snapshot → never act on it

    # ── reconcile / adopt (S2): tracker == IBKR truth ────────────────────────
    def adopt_from_venue(self, net_qty: float) -> str:
        """Take over a venue position the desk isn't tracking (restart / manual /
        an independent EOD flatten). Side + qty come from IBKR truth; entry_price
        and — crucially — entry_atr are recovered from the persisted open_position
        (IBKR can't tell us the ATR the stop was sized against). Returns 'adopted'
        after re-arming, or 'flatten' when protection can't be re-established."""
        side = "LONG" if net_qty > 0 else "SHORT"
        qty = abs(net_qty)
        rec = get_open_position(self._store, self._cfg.symbol)
        if rec is None or not rec["entry_atr"] or rec["entry_atr"] <= 0 or rec["side"] != side:
            return "flatten"  # no trustworthy stop distance → don't hold naked
        self._pos = Position(side, rec["entry_price"], rec["entry_atr"], 0.0)
        self._qty = qty
        self._open_atr = rec["entry_atr"]
        self.opened_at = rec["opened_at"]
        st = self._safety.arm_stop(self._cfg.symbol, side=side, qty=qty,
                                   entry_price=rec["entry_price"], atr=rec["entry_atr"])
        upsert_open_position(
            self._store, symbol=self._cfg.symbol, side=side, qty=qty,
            entry_price=rec["entry_price"], entry_atr=rec["entry_atr"],
            opened_at=rec["opened_at"], stop_price=st.stop_price if st else None,
        )
        return "adopted"

    def _handle_adopt(self, net_qty: float) -> None:
        if self.adopt_from_venue(net_qty) == "adopted":
            self._notify(f"adopted {self._cfg.symbol} {net_qty:g} from venue + re-armed stop")
        else:
            self._flatten_qty(net_qty)
            self._notify(f"adopt {self._cfg.symbol} {net_qty:g}: no recoverable protection — FLATTENING")

    def _flatten_qty(self, net_qty: float) -> None:
        close_side = "SELL" if net_qty > 0 else "BUY"
        self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=abs(net_qty), order_type="MKT")

    def _clear_phantom(self) -> None:
        """Venue is flat but we thought we held — our position closed unseen. Drop
        the phantom held state + cancel any tracked stop (the round-trip audit at
        S6 recovers the missing record)."""
        self._safety.on_flat(self._cfg.symbol)
        clear_open_position(self._store, self._cfg.symbol)
        self._pos = None
        self._qty = 0.0
        self._naked_streak = 0

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
            if not gw.healthy or not self._cfg.place_live:
                continue
            if not await gw.probe_alive():  # freshness gate — fail-closed
                continue
            snap = await self._read_venue_protection(gw)
            if snap is None:
                continue
            net, orders = snap
            verdict = reconcile_verdict(self._pos.side if self._pos else None, self._qty, net)
            if verdict == "adopt":
                self._handle_adopt(net)
                continue
            if verdict == "drift":
                if not self._halted:
                    self._notify(f"DRIFT {self._cfg.symbol}: tracker "
                                 f"{(self._pos.side if self._pos else 'flat')} {self._qty:g} vs "
                                 f"venue {net:g} — HALTED (no new entries)")
                self._halted = True
                continue
            if verdict == "vanished":
                self._notify(f"{self._cfg.symbol} vanished at venue — clearing phantom held state")
                self._clear_phantom()
                continue
            # match — a clean cycle clears any halt, then run the coverage auditor
            self._halted = False
            if self._pos is not None:
                action = self.assess_protection(net, orders, time.monotonic())
                if action == "reprotect":
                    self._reprotect()
                    self._notify(f"naked {self._cfg.symbol} — re-armed stop (attempt {self._naked_streak})")
                elif action == "flatten":
                    self._emergency_flatten()
                    self._notify(f"NAKED {self._cfg.symbol} unresolved after {self._naked_streak} "
                                 f"re-arms — FLATTENED")

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
            core._handle_adopt(boot[0])

    intents_task = asyncio.ensure_future(_drain_intents(pull, core))
    protect_task = asyncio.ensure_future(core.venue_audit_loop(gw))  # S1 naked + S2 reconcile
    liveness_task = asyncio.ensure_future(gw.liveness_loop())        # S3 zombie guard
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
    subprocess.run(
        ["/home/alphabot/alphabot2/.venv/bin/python",
         "/home/alphabot/alphabot2/scripts/notify_operator.py", f"[V7-core] {msg}"],
        check=False, timeout=15,
    )


def main() -> None:  # `python -m gazbot7.core`  (GAZBOT7_PLACE_LIVE=1 to trade)
    live = os.environ.get("GAZBOT7_PLACE_LIVE") == "1"
    cfg = RunConfig(place_live=live, client_id=CORE_CLIENT_ID)
    asyncio.run(run(cfg, notifier=_telegram_notifier))


if __name__ == "__main__":
    main()
