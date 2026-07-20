"""GAZBOT V7 — the strategy service: the decision half.

Strategy subscribes the md live stream (closed 5s bars + tape summary) and core's
position stream, keeps a rolling bar window (warmed from ``capture.db``, then
live), runs the deciders, and sends OPEN / CLOSE **intents** to core. It never
touches IBKR and holds no order state — core is the authority on what we hold;
strategy's local position is a decision-making mirror of core's stream, plus the
peak-favourable it tracks itself for the adverse-cut arm.

Two guards make it safe to restart freely and to run unattended:

* **Freshness / stand-down** — if the tape or the 5s bars go stale (md died, or
  the reqRealTimeBars farm dropped while ticks flow), strategy decides nothing.
  The native stop at IBKR is the position's protection; strategy never acts on a
  frozen chart.
* **One in-flight intent** — after sending an OPEN/CLOSE it waits for core to
  confirm (position flips, or an ``intent_result`` rejects, or a timeout) before
  acting again, so a jittery book can't stack duplicate entries. Core's
  one-position guard is the backstop.

The ``Strategy`` class is pure decision logic (bars/tape/position → intent),
fully tested without a socket; ``run`` is the thin live wiring. This is the
decision half lifted out of the old ``Desk``. Clean-room.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from . import session
from .agg import MinuteBars
from .capture import open_capture
from .config import RunConfig, live_gates
from .deciders import (
    Position,
    chandelier_start_k,
    compute_features,
    exit_absorption,
    exit_adverse_cut,
    exit_chandelier,
    exit_giveback,
    exit_scalp,
    gate_grind,
    gate_reversal_grab,
    gate_thrust,
)
from .sizing import conviction_lots, efficiency_ratio
from .ipc import (
    CORE_STATE,
    INTENTS,
    MD_STREAM,
    T_BAR,
    T_INTENT_RESULT,
    T_POSITION,
    T_TAPE,
    PushClient,
    Subscriber,
)

_STALE_TAPE_MS = 10_000     # no tape for 10s → stand down
_STALE_BAR_MS = 30_000      # no 5s bar for 30s (farm drop) → stand down
_PENDING_TIMEOUT_MS = 8_000  # give up waiting on core's confirm, free to act again


class Strategy:
    """Pure decision logic. Fed state via on_* methods; ``decide`` emits an intent."""

    def __init__(self, cfg: RunConfig) -> None:
        self._cfg = cfg
        self._mb = MinuteBars(cfg.bar_lookback)  # 5s → completed 1-minute bars
        self._tape: dict = {}
        self._core_flat = True
        self._core_pos: dict | None = None
        self._local_pos: Position | None = None
        self._confirm: dict | None = None  # pending entry watching absorption (the wait)
        self._active = None  # GateSpec that opened the current position (multi-gate exit routing)
        self._pending: str | None = None  # "OPEN" | "CLOSE" while awaiting core
        self._pending_iid: str | None = None
        self._pending_ts = 0
        self._iid = 0

    # ── state feeds ──────────────────────────────────────────────────────────
    def warm(self, cap_conn) -> None:
        """Seed the rolling window with 1-MINUTE bars aggregated from the captured
        5s bars — the thrust is decided on 1m (a 5-bar thrust = a 5-min move)."""
        self._mb.warm(cap_conn, self._cfg.symbol, self._cfg.bar_lookback)

    def on_bar(self, msg: dict) -> None:
        self._mb.fold(msg["ts"], msg["o"], msg["h"], msg["l"], msg["c"], msg["v"])

    def on_tape(self, msg: dict) -> None:
        self._tape = msg

    def on_core_position(self, msg: dict) -> None:
        if msg.get("flat"):
            self._core_flat = True
            self._core_pos = None
            self._active = None  # flat → no gate owns a position
            self._local_pos = None
            if self._pending == "CLOSE":
                self._pending = None  # confirmed flat
        else:
            self._core_flat = False
            self._core_pos = msg
            if self._pending == "OPEN":
                self._pending = None  # confirmed held

    def on_intent_result(self, msg: dict) -> None:
        if msg.get("iid") == self._pending_iid and not msg.get("accepted"):
            self._pending = None  # core rejected → free to act again

    # ── decision ─────────────────────────────────────────────────────────────
    def fresh(self, now_ms: int) -> bool:
        tape_ts = self._tape.get("ts_ms", 0)
        if not tape_ts or now_ms - tape_ts > _STALE_TAPE_MS:
            return False
        return self._mb.fresh(now_ms, _STALE_BAR_MS)

    def decide(self, now_ms: int) -> dict | None:
        """The one entry point. Returns an intent to send, or None. Mutates
        pending/peak state; call once per tape tick."""
        if self._pending and now_ms - self._pending_ts > _PENDING_TIMEOUT_MS:
            self._pending = None
        if self._pending:
            return None
        if not self.fresh(now_ms):
            return None
        bars = self._mb.bars()
        if len(bars) < 6:
            return None
        f = compute_features(bars)
        price = self._tape.get("last") or f.price
        if self._core_flat:
            self._local_pos = None
            return self._entry(f, price, now_ms, bars)
        self._confirm = None  # holding a position — abandon any pending confirmation
        return self._manage(f, price, now_ms)

    def _gate(self, f):
        if self._cfg.gate == "thrust":
            return gate_thrust(f, **self._cfg.gate_params)
        if self._cfg.gate == "reversal_grab":
            return gate_reversal_grab(
                f, tape_net=self._tape.get("net_flow", 0.0),
                in_rth=self._tape.get("in_rth", True), **self._cfg.gate_params,
            )
        return None

    # ── two-gate lineup (single-position, first-to-fire) ─────────────────────
    def _eval_spec(self, spec, f):
        if spec.kind == "grind":
            return gate_grind(f, tape_net=self._tape.get("net_flow", 0.0), **spec.params)
        if spec.kind == "reversal_grab":
            return gate_reversal_grab(f, tape_net=self._tape.get("net_flow", 0.0),
                                      in_rth=self._tape.get("in_rth", True), **spec.params)
        if spec.kind == "thrust":
            return gate_thrust(f, **spec.params)
        return None

    def _pick_gate(self, f):
        """First gate in the lineup that fires → (spec, entry). None if none fire."""
        for spec in self._cfg.gates:
            e = self._eval_spec(spec, f)
            if e is not None:
                return spec, e
        return None, None

    def _size_for(self, spec, bars, atr: float) -> int:
        qty = conviction_lots(efficiency_ratio(bars), base=spec.base_size) \
            if spec.sizing == "conviction" else spec.base_size
        # RISK-BOUNDED SIZING (2026-07-20): cap qty so the 1-ATR stop's dollar risk
        # (atr × stop_atr_mult × $/pt × qty) <= risk_budget_usd. A volatile entry sizes
        # DOWN so a 2-lot stop-out can't balloon (id68 −$130 @ ATR 31). Floors at 1 when
        # the gate fired — the cap never zeroes a fire (conviction's 0-rung still skips).
        budget = spec.risk_budget_usd
        if budget > 0 and atr > 0 and qty > 0:
            per_lot = atr * spec.stop_atr_mult * self._cfg.value_per_point
            if per_lot > 0:
                qty = min(qty, max(1, int(budget // per_lot)))
        return qty

    def _entry(self, f, price, now_ms: int, bars) -> dict | None:
        now = datetime.fromtimestamp(now_ms / 1000, UTC)
        if not session.is_open(now) or session.in_no_open_window(now, self._cfg.no_open_minutes):
            self._confirm = None
            return None  # closed, or too close to the session end — no new entries
        if self._cfg.gates:  # TWO-GATE lineup: immediate, first-to-fire, per-gate sizing
            spec, e = self._pick_gate(f)
            if e is None:
                return None
            qty = self._size_for(spec, bars, f.atr)
            if qty <= 0:
                return None  # conviction sizing says chop → skip (the 0-lot rung)
            self._active = spec
            return self._emit_open(e.side, spec.name, f, now_ms, qty=qty)
        if self._cfg.entry_confirm_s <= 0:  # wait disabled — immediate entry
            entry = self._gate(f)
            return self._emit_open(entry.side, entry.gate, f, now_ms) if entry else None
        # DELAYED ENTRY (operator 2026-07-16): raise the signal, watch absorption for
        # entry_confirm_s, enter only if the thrust PERSISTS and no absorption appeared.
        if self._confirm is None:
            entry = self._gate(f)
            if entry is None:
                return None
            self._confirm = {"side": entry.side, "gate": entry.gate, "start_ms": now_ms}
            return None  # signal raised — begin the confirmation window
        c = self._confirm
        if self._absorbed(c["side"]):  # tape absorbed our side during the wait — veto
            self._confirm = None
            return None
        if now_ms - c["start_ms"] < self._cfg.entry_confirm_s * 1000:
            return None  # still watching
        self._confirm = None  # window elapsed — enter only if thrust still fires clean
        entry = self._gate(f)
        if entry is not None and entry.side == c["side"] and not self._absorbed(entry.side):
            return self._emit_open(entry.side, entry.gate, f, now_ms)
        return None  # thrust faded / flipped / absorbed during the wait — stand down

    def _emit_open(self, side: str, gate: str, f, now_ms: int, qty: int | None = None) -> dict:
        return self._stamp("OPEN", now_ms, {
            "action": "OPEN", "side": side, "qty": qty if qty is not None else self._cfg.size,
            "gate": gate, "reason": gate,
            "meta": {"entry_atr": f.atr, "target_r": self._cfg.target_r,
                     "stop_atr_mult": self._cfg.stop_atr_mult},
        })

    def _absorbed(self, side: str) -> bool:
        """Would absorption cut a fresh `side` position given the current tape?"""
        return exit_absorption(
            Position(side, 0.0, 0.0, 0.0),
            tape_net=self._tape.get("net_flow", 0.0),
            window_price_delta=self._tape.get("win_price_delta", 0.0),
            flow_min=self._cfg.absorption_flow_min,
        ) is not None

    def _manage(self, f, price: float, now_ms: int) -> dict | None:
        if self._local_pos is None:
            cp = self._core_pos or {}
            self._local_pos = Position(cp.get("side"), cp.get("entry"), cp.get("atr", 0.0), 0.0)
        pos = self._local_pos
        fav = (price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - price)
        if fav > pos.peak_favorable:  # track best favourable excursion (adverse-cut arm)
            pos = Position(pos.side, pos.entry_price, pos.entry_atr, fav)
            self._local_pos = pos
        # native STP owns STOP. Profit exit = the tightening chandelier (momentum,
        # uncapped) — or the fixed 2R target if the chandelier is disabled. Then the
        # risk cuts (failed-entry adverse-cut + tape absorption) underneath.
        reason = None
        spec = self._active
        if spec is not None:  # TWO-GATE: route the profit exit by the gate that opened it
            if spec.exit == "chandelier":
                sk = chandelier_start_k(pos.entry_atr) if spec.vol_adaptive_chandelier else spec.chandelier_start_k
                if exit_chandelier(pos, price, start_k=sk, min_k=spec.chandelier_min_k,
                                   tighten=spec.chandelier_tighten):
                    reason = "CHANDELIER"
            elif exit_scalp(pos, price, target_r=spec.target_r,
                            stop_atr_mult=spec.stop_atr_mult) == "TARGET":
                reason = "TARGET"
            cut_atr = spec.adverse_cut_atr
        else:  # legacy single-gate path (unchanged)
            if self._cfg.chandelier_enabled:
                if exit_chandelier(pos, price, start_k=self._cfg.chandelier_start_k,
                                   min_k=self._cfg.chandelier_min_k, tighten=self._cfg.chandelier_tighten):
                    reason = "CHANDELIER"
            elif exit_scalp(pos, price, target_r=self._cfg.target_r,
                            stop_atr_mult=self._cfg.stop_atr_mult) == "TARGET":
                reason = "TARGET"
            cut_atr = self._cfg.adverse_cut_atr
        if reason is None and cut_atr > 0 and exit_adverse_cut(pos, price, cut_atr=cut_atr):
            reason = "ADVERSE_CUT"
        # dollar give-back ("ratchet 2", 2026-07-20) — the tight profit protector that
        # catches the green-then-reverse deep losers BEFORE the wide chandelier / 2R
        # scalp lets them round-trip. Arms only after a real green peak; a never-green
        # trade never arms (that loss is the native stop's job). Checked under the
        # profit exits so a true runner still exits on chandelier, not here.
        gb_on = self._active.giveback_enabled if self._active is not None else self._cfg.giveback_enabled
        if reason is None and gb_on:
            gb_arm = self._active.giveback_arm_usd if self._active is not None else self._cfg.giveback_arm_usd
            gb_usd = self._active.giveback_usd if self._active is not None else self._cfg.giveback_usd
            qty = (self._core_pos or {}).get("qty") or 1
            if exit_giveback(pos, price, value_per_point=self._cfg.value_per_point, qty=qty,
                             arm_usd=gb_arm, giveback_usd=gb_usd):
                reason = "GIVEBACK"
        # absorption is a CATASTROPHE backstop: only once the trade is deep underwater
        # (>= absorption_min_loss_usd). A green trade has no loss and a small loss is
        # under the floor, so absorption never guillotines a winner or a scalp — the
        # native ~1-ATR stop is the normal loss exit; this catches a runaway past it.
        loss_usd = -fav * self._cfg.value_per_point  # >0 only when offside
        if (reason is None and loss_usd >= self._cfg.absorption_min_loss_usd
                and exit_absorption(pos, tape_net=self._tape.get("net_flow", 0.0),
                                    window_price_delta=self._tape.get("win_price_delta", 0.0),
                                    flow_min=self._cfg.absorption_flow_min)):
            reason = "ABSORPTION_CUT"
        if reason is None:
            return None
        return self._stamp("CLOSE", now_ms, {"action": "CLOSE", "reason": reason})

    def _stamp(self, kind: str, now_ms: int, intent: dict) -> dict:
        self._iid += 1
        iid = f"s-{self._iid}"
        intent["iid"] = iid
        self._pending = kind
        self._pending_iid = iid
        self._pending_ts = now_ms
        return intent


# ── service entrypoint ───────────────────────────────────────────────────────
async def run(cfg: RunConfig, *, max_seconds: float | None = None) -> None:
    cap = open_capture(cfg.capture_path)
    strat = Strategy(cfg)
    strat.warm(cap)
    cap.close()

    md = Subscriber(MD_STREAM, topics=[T_BAR, T_TAPE])
    cs = Subscriber(CORE_STATE, topics=[T_POSITION, T_INTENT_RESULT])
    push = PushClient(INTENTS)

    async def drain_core() -> None:
        while True:
            topic, msg = await cs.recv()
            if topic == T_POSITION:
                strat.on_core_position(msg)
            elif topic == T_INTENT_RESULT:
                strat.on_intent_result(msg)

    core_task = asyncio.ensure_future(drain_core())
    start = time.monotonic()
    try:
        while max_seconds is None or (time.monotonic() - start) < max_seconds:
            msg = await md.poll(500)
            if msg is None:
                continue
            topic, body = msg
            if topic == T_BAR:
                strat.on_bar(body)
            elif topic == T_TAPE:
                strat.on_tape(body)
                intent = strat.decide(int(time.time() * 1000))  # tape tick = decision clock
                if intent is not None:
                    await push.send(intent)
    finally:
        core_task.cancel()
        md.close()
        cs.close()
        push.close()


def main() -> None:  # `python -m gazbot7.strategy`
    # 2026-07-19 go-live: two-gate lineup (grind conviction + rgv 2R), replaces thrust.
    asyncio.run(run(RunConfig(gates=live_gates())))


if __name__ == "__main__":
    main()
