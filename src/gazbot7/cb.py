"""GAZBOT V7 — session direction circuit breaker (prototype, observe-only).

Runs the two-sided thrust base, but tracks per-SIDE realized P&L over the session
and STANDS DOWN the side that is clearly losing while the other clearly wins. It is
a THRESHOLD gate, NOT hard-and-fast (operator 2026-07-17: "there are days when long
AND short both win — it has to have a threshold; today was very clear"): a veto arms
only when the loser is at least ``loss_usd`` down AND the winner at least ``win_usd``
up, after each side has taken ``n_min`` probe trades. So a both-sides-win day trips
nothing, and you always "lose a few early, then confirm" before committing.

The stood-down side keeps trading as a PHANTOM (recorded under ``cb_thrust_dropped``)
so we can (a) validate the veto was right and (b) RE-ARM the side if its phantom book
recovers by ``rearm_usd`` (operator: "if we switch there has to be a commitment to
periodically simulate the dropped side over the day and make sure we were correct").

The governor DECIDES on ceiling P&L (what's known at close time, mirrors the live
desk knowing its fills); every trade it books is SCORED honestly by the repricer on
ticks, same as any shadow trade. Reuses the shared deciders — no gate/exit math is
duplicated here, only the per-side session orchestration. Touches NO account.
"""

from __future__ import annotations

from dataclasses import dataclass

from .deciders import Position, compute_features, exit_chandelier, exit_scalp, gate_thrust
from .store import record_shadow_trade

LIVE_STRATEGY = "cb_thrust"          # the trades the breaker LET THROUGH (governed)
DROPPED_STRATEGY = "cb_thrust_dropped"  # the stood-down side's phantom (validation + re-arm)
CB_STRATEGIES = (LIVE_STRATEGY, DROPPED_STRATEGY)


@dataclass
class BreakerConfig:
    # base gate = the live desk's thrust_loose, chandelier exit at the live 3.5 trail
    thr: float = 1.5
    amp_floor: float = 0.0004
    stop_atr_mult: float = 1.0
    chand_start_k: float = 3.5
    chand_tighten: float = 0.75
    # the governor thresholds (operator's "it has to have a threshold")
    n_min: int = 3          # min probe trades a side must take before it can be vetoed
    loss_usd: float = 80.0  # the losing side must be at least this far DOWN this session…
    win_usd: float = 80.0   # …AND the other side at least this far UP, to arm the veto
    rearm_usd: float = 120.0  # a vetoed side whose PHANTOM book recovers this much re-arms


@dataclass
class _Leg:
    cum: float = 0.0        # realized (ceiling) P&L of LIVE trades this session
    n: int = 0              # LIVE closed trades this session
    veto: bool = False
    veto_cum: float = 0.0   # phantom P&L accrued SINCE the veto (for re-arm)
    open: dict | None = None  # one position at a time per side


class SessionDirectionBreaker:
    """One base gate, two legs (LONG/SHORT), a per-session direction governor."""

    def __init__(self, store, *, symbol: str = "MNQ", qty: float = 1.0,
                 value_per_point: float = 2.0, fee_rt: float = 1.5,
                 cfg: BreakerConfig | None = None) -> None:
        self._store = store
        self._sym = symbol
        self._qty = qty
        self._vpp = value_per_point
        self._fee = fee_rt
        self._cfg = cfg or BreakerConfig()
        self._legs: dict[str, _Leg] = {"LONG": _Leg(), "SHORT": _Leg()}
        self._day: int | None = None

    def _reset_session(self) -> None:
        # a new session re-arms BOTH sides and zeroes the scoreboard; open positions
        # are left to close out naturally on their own exit.
        for lg in self._legs.values():
            lg.cum = 0.0
            lg.n = 0
            lg.veto = False
            lg.veto_cum = 0.0

    def on_bars(self, bars, *, tape_net: float = 0.0, window_price_delta: float = 0.0,
                in_rth: bool = True, now_ms: int | None = None) -> None:
        if not bars:
            return
        ts = bars[-1].ts
        day = ts // 86400  # UTC-day session boundary (prototype; Globex-session split is a refinement)
        if self._day is None:
            self._day = day
        elif day != self._day:
            self._day = day
            self._reset_session()
        f = compute_features(bars)
        # 1) manage the open position on each leg
        for side, lg in self._legs.items():
            if lg.open is not None:
                self._manage_leg(side, lg, f, ts)
        # 2) a fresh thrust → open on that leg (LIVE if the side isn't vetoed, else PHANTOM)
        entry = gate_thrust(f, thr=self._cfg.thr, amp_floor=self._cfg.amp_floor)
        if entry is not None:
            lg = self._legs[entry.side]
            if lg.open is None:
                lg.open = dict(side=entry.side, entry_price=f.price, entry_atr=f.atr,
                               entry_ts=ts, peak=0.0, live=not lg.veto)
        # 3) re-evaluate the governor (arm a veto / re-arm a recovered side)
        self._update_governor()

    def _manage_leg(self, side: str, lg: _Leg, f, ts: int) -> None:
        op = lg.open
        fav = (f.price - op["entry_price"]) if side == "LONG" else (op["entry_price"] - f.price)
        op["peak"] = max(op["peak"], fav)
        pos = Position(side, op["entry_price"], op["entry_atr"], op["peak"])
        # EXACTLY the chand_k35 exit: tightening chandelier (profit) + 1-ATR native STOP
        # (target off) — so cb_thrust differs from chand_k35 ONLY by the direction governor.
        reason = "CHANDELIER" if exit_chandelier(
            pos, f.price, start_k=self._cfg.chand_start_k, min_k=0.5,
            tighten=self._cfg.chand_tighten) else exit_scalp(
            pos, f.price, target_r=99.0, stop_atr_mult=self._cfg.stop_atr_mult)
        if reason is not None:
            self._close_leg(side, lg, f.price, ts, reason)

    def _close_leg(self, side: str, lg: _Leg, exit_price: float, exit_ts: int, reason: str) -> None:
        op = lg.open
        if side == "LONG":
            gross = (exit_price - op["entry_price"]) * self._qty * self._vpp
        else:
            gross = (op["entry_price"] - exit_price) * self._qty * self._vpp
        pnl = gross - self._fee
        live = op["live"]
        record_shadow_trade(
            self._store,
            strategy=LIVE_STRATEGY if live else DROPPED_STRATEGY, symbol=self._sym,
            side=side, qty=self._qty, entry_ts=op["entry_ts"], entry_price=op["entry_price"],
            entry_atr=op["entry_atr"], target_r=0.0, stop_atr_mult=self._cfg.stop_atr_mult,
            exit_ts=exit_ts, exit_price=exit_price, exit_reason=reason, ceiling_pnl=pnl,
        )
        if live:
            lg.cum += pnl
            lg.n += 1
        else:
            lg.veto_cum += pnl  # phantom book of the stood-down side, for the re-arm check
        lg.open = None

    def _update_governor(self) -> None:
        c = self._cfg
        legs = self._legs
        # ARM: one side clearly losing while the other clearly wins (BOTH thresholds).
        for side in ("LONG", "SHORT"):
            lg = legs[side]
            other = legs["SHORT" if side == "LONG" else "LONG"]
            if not lg.veto and lg.n >= c.n_min and lg.cum <= -c.loss_usd and other.cum >= c.win_usd:
                lg.veto = True
                lg.veto_cum = 0.0
        # RE-ARM: a vetoed side whose PHANTOM book has recovered → we were (now) wrong; switch it back on.
        for lg in legs.values():
            if lg.veto and lg.veto_cum >= c.rearm_usd:
                lg.veto = False
                lg.veto_cum = 0.0

    # small read-only accessors for tests / introspection
    def state(self) -> dict:
        return {s: dict(cum=lg.cum, n=lg.n, veto=lg.veto, veto_cum=lg.veto_cum)
                for s, lg in self._legs.items()}
