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
from .config import RunConfig
from .deciders import (
    Position,
    compute_features,
    exit_absorption,
    exit_adverse_cut,
    exit_scalp,
    gate_reversal_grab,
    gate_thrust,
)
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
            return self._entry(f, now_ms)
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

    def _entry(self, f, now_ms: int) -> dict | None:
        now = datetime.fromtimestamp(now_ms / 1000, UTC)
        if not session.is_open(now) or session.in_no_open_window(now, self._cfg.no_open_minutes):
            return None  # closed, or too close to the session end — no new entries
        entry = self._gate(f)
        if entry is None:
            return None
        return self._stamp("OPEN", now_ms, {
            "action": "OPEN", "side": entry.side, "qty": self._cfg.size,
            "gate": entry.gate, "reason": entry.gate,
            "meta": {"entry_atr": f.atr, "target_r": self._cfg.target_r,
                     "stop_atr_mult": self._cfg.stop_atr_mult},
        })

    def _manage(self, f, price: float, now_ms: int) -> dict | None:
        if self._local_pos is None:
            cp = self._core_pos or {}
            self._local_pos = Position(cp.get("side"), cp.get("entry"), cp.get("atr", 0.0), 0.0)
        pos = self._local_pos
        fav = (price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - price)
        if fav > pos.peak_favorable:  # track best favourable excursion (adverse-cut arm)
            pos = Position(pos.side, pos.entry_price, pos.entry_atr, fav)
            self._local_pos = pos
        # the native STP owns STOP; strategy adds the scalp TARGET + the cuts
        reason = None
        if exit_scalp(pos, price, target_r=self._cfg.target_r,
                      stop_atr_mult=self._cfg.stop_atr_mult) == "TARGET":
            reason = "TARGET"
        elif exit_adverse_cut(pos, price, cut_atr=self._cfg.adverse_cut_atr):
            reason = "ADVERSE_CUT"
        elif exit_absorption(pos, tape_net=self._tape.get("net_flow", 0.0),
                             window_price_delta=self._tape.get("win_price_delta", 0.0),
                             flow_min=self._cfg.absorption_flow_min):
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
    asyncio.run(run(RunConfig()))


if __name__ == "__main__":
    main()
