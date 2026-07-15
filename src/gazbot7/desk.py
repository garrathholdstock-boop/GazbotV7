"""GAZBOT V7 — the live desk loop (D7).

Assembles every drop into one cycle: capture → features → decide → size → submit
→ manage → close. MNQ, two-sided, 1..N contracts. On each bar it computes
features (D6), and if flat runs the configured entry gate; if in a position it
manages the exits. Fills flow in through ``on_fill`` and are applied to the order
engine (D2), the trade assembler (D3), and the safety layer (D4) — a newly-opened
position arms its fixed native 1-ATR STP in the same call as the open fill (zero
naked), and a close clears it. The protective stop is server-side; the desk's
managed exits are the scalp R-target + the adverse / absorption cuts.

Pure orchestration over injected components — fully testable end-to-end against
fakes; the ib_async adapter is the thin live wiring. Clean-room: nothing copied.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .deciders import (
    Bar,
    Features,
    Position,
    compute_features,
    exit_absorption,
    exit_adverse_cut,
    exit_scalp,
    gate_reversal_grab,
    gate_thrust,
)
from .store import Fill

_EPS = 1e-9


@dataclass
class DeskConfig:
    symbol: str = "MNQ"
    size: int = 1  # contracts per position (1..N — one size concept)
    gate: str = "thrust"  # "thrust" | "reversal_grab"
    gate_params: dict = field(default_factory=dict)
    target_r: float = 2.0
    stop_atr_mult: float = 1.0
    adverse_cut_atr: float = 1.5
    absorption_flow_min: float = 50.0


class Desk:
    def __init__(self, cfg: DeskConfig, order_engine, tracker, safety) -> None:
        self._cfg = cfg
        self._oe = order_engine
        self._tt = tracker
        self._safety = safety
        self._pos: Position | None = None
        self._last_atr = 0.0
        self._pending_entry = False
        self._exit_reason: str | None = None
        self._closing = False
        self.opened_at: str | None = None

    @property
    def position(self) -> Position | None:
        return self._pos

    # ── decision cycle ───────────────────────────────────────────────────────
    def on_bars(self, bars: list[Bar], *, tape_net: float = 0.0,
                window_price_delta: float = 0.0, in_rth: bool = True) -> None:
        f = compute_features(bars)
        self._last_atr = f.atr
        if self._pos is None:
            if not self._pending_entry:
                self._maybe_enter(f, tape_net=tape_net, in_rth=in_rth)
        else:
            self._manage(f, tape_net=tape_net, window_price_delta=window_price_delta)

    def _maybe_enter(self, f: Features, *, tape_net: float, in_rth: bool) -> None:
        if self._cfg.gate == "thrust":
            entry = gate_thrust(f, **self._cfg.gate_params)
        elif self._cfg.gate == "reversal_grab":
            entry = gate_reversal_grab(f, tape_net=tape_net, in_rth=in_rth, **self._cfg.gate_params)
        else:
            entry = None
        if entry is None:
            return
        side = "BUY" if entry.side == "LONG" else "SELL"
        self._oe.submit(symbol=self._cfg.symbol, side=side, qty=self._cfg.size, order_type="MKT")
        self._pending_entry = True

    def _manage(self, f: Features, *, tape_net: float, window_price_delta: float) -> None:
        pos = self._pos
        assert pos is not None
        # track best favourable excursion (for the adverse-cut arm test)
        fav = (f.price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - f.price)
        if fav > pos.peak_favorable:
            self._pos = pos = Position(pos.side, pos.entry_price, pos.entry_atr, fav)
        if self._closing:
            return
        # managed exits: the scalp TARGET (native STP owns the stop), then the cuts
        reason = None
        if exit_scalp(pos, f.price, target_r=self._cfg.target_r,
                      stop_atr_mult=self._cfg.stop_atr_mult) == "TARGET":
            reason = "TARGET"
        elif exit_adverse_cut(pos, f.price, cut_atr=self._cfg.adverse_cut_atr):
            reason = "ADVERSE_CUT"
        elif exit_absorption(pos, tape_net=tape_net, window_price_delta=window_price_delta,
                             flow_min=self._cfg.absorption_flow_min):
            reason = "ABSORPTION_CUT"
        if reason:
            self._submit_close(reason)

    def _submit_close(self, reason: str) -> None:
        pos = self._pos
        assert pos is not None
        close_side = "SELL" if pos.side == "LONG" else "BUY"
        self._exit_reason = reason
        self._closing = True
        self._oe.submit(symbol=self._cfg.symbol, side=close_side, qty=self._cfg.size, order_type="MKT")

    # ── fill application ─────────────────────────────────────────────────────
    def on_fill(self, fill: Fill) -> None:
        sym = self._cfg.symbol
        was_flat = abs(self._tt.net_qty(sym)) < _EPS
        self._oe.on_fill(fill)
        closing = self._pos is not None and self._is_closing_side(fill.side)
        # a closing fill with no managed reason set is the native STP → "STOP"
        reason = (self._exit_reason or "STOP") if closing else None
        self._tt.apply(fill, exit_reason=reason)
        now_flat = abs(self._tt.net_qty(sym)) < _EPS
        if was_flat and not now_flat:
            self._on_opened(fill)
        elif not was_flat and now_flat:
            self._on_closed()

    def _is_closing_side(self, fill_side: str) -> bool:
        if self._pos is None:
            return False
        return (self._pos.side == "LONG" and fill_side == "SELL") or (
            self._pos.side == "SHORT" and fill_side == "BUY"
        )

    def _on_opened(self, fill: Fill) -> None:
        side = "LONG" if fill.side == "BUY" else "SHORT"
        self._pos = Position(side, fill.price, self._last_atr, 0.0)
        self.opened_at = fill.exec_time  # for the holdings tab (time-in-trade)
        self._pending_entry = False
        self._safety.arm_stop(
            self._cfg.symbol, side=side, qty=self._cfg.size,
            entry_price=fill.price, atr=self._last_atr,
        )

    def _on_closed(self) -> None:
        self._safety.on_flat(self._cfg.symbol)
        self._pos = None
        self._exit_reason = None
        self._closing = False
