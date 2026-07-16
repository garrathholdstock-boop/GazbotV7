"""GAZBOT V7 — the shadow desk (D8).

Runs N strategy variants on the live feed, each ``(name, gate, params, symbol)``,
using the SAME deciders as the live desk (D6) — so a shadow result can never
drift from what the live desk would do. It records one ``shadow_trades`` row per
simulated round-trip at bar prices (the *ceiling*). Those ceilings are NEVER
scored on directly — the tick repricer (repricer.py) re-prices every trade on
honest ticks into ``shadow_real.real_pnl``, which is the only number we trust.
The R-target scalp leg is first-class here (V5's rtarget-leg blindness — which
left dip_loose_absorption's honest P&L blank — cannot happen).

Instrument-parameterised: a variant can run on MGC (or anything captured), so
the shadow desk gives research breadth without touching the MNQ-only live path.
Clean-room: nothing copied from V5.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from .deciders import (
    REVERSAL_SHORT_VARIANTS,
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
from .store import record_shadow_trade


@dataclass
class ShadowVariant:
    name: str
    gate: str  # "thrust" | "reversal_grab"
    params: dict = field(default_factory=dict)
    symbol: str = "MNQ"
    qty: float = 1.0
    target_r: float = 2.0
    stop_atr_mult: float = 1.0
    adverse_cut_atr: float = 1.5
    absorption_flow_min: float = 50.0


class ShadowSim:
    def __init__(self, store, variants: list[ShadowVariant], *, value_per_point: float = 2.0, fee_rt: float = 1.5) -> None:
        self._store = store
        self._variants = variants
        self._vpp = value_per_point
        self._fee = fee_rt
        self._open: dict[str, dict] = {}  # variant name → open sim position

    def on_bars(self, bars: list[Bar], *, tape_net: float = 0.0,
                window_price_delta: float = 0.0, in_rth: bool = True) -> None:
        f = compute_features(bars)
        ts = bars[-1].ts
        for v in self._variants:
            self._step(v, f, ts, tape_net, window_price_delta, in_rth)

    def _entry(self, v: ShadowVariant, f: Features, tape_net: float, in_rth: bool):
        if v.gate == "thrust":
            return gate_thrust(f, **v.params)
        if v.gate == "reversal_grab":
            return gate_reversal_grab(f, tape_net=tape_net, in_rth=in_rth, **v.params)
        return None

    def _step(self, v, f, ts, tape_net, wpd, in_rth):
        op = self._open.get(v.name)
        if op is None:
            entry = self._entry(v, f, tape_net, in_rth)
            if entry is not None:
                self._open[v.name] = dict(
                    side=entry.side, entry_price=f.price, entry_atr=f.atr, entry_ts=ts, peak=0.0
                )
            return
        # manage — track peak favourable, then check the sim exit stack
        fav = (f.price - op["entry_price"]) if op["side"] == "LONG" else (op["entry_price"] - f.price)
        op["peak"] = max(op["peak"], fav)
        pos = Position(op["side"], op["entry_price"], op["entry_atr"], op["peak"])
        reason = exit_scalp(pos, f.price, target_r=v.target_r, stop_atr_mult=v.stop_atr_mult)  # STOP/TARGET
        if reason is None and exit_adverse_cut(pos, f.price, cut_atr=v.adverse_cut_atr):
            reason = "ADVERSE_CUT"
        if reason is None and exit_absorption(pos, tape_net=tape_net, window_price_delta=wpd, flow_min=v.absorption_flow_min):
            reason = "ABSORPTION_CUT"
        if reason is not None:
            self._record(v, op, f.price, ts, reason)
            del self._open[v.name]

    def _record(self, v, op, exit_price, exit_ts, reason):
        side = op["side"]
        if side == "LONG":
            gross = (exit_price - op["entry_price"]) * v.qty * self._vpp
        else:
            gross = (op["entry_price"] - exit_price) * v.qty * self._vpp
        record_shadow_trade(
            self._store,
            strategy=v.name, symbol=v.symbol, side=side, qty=v.qty,
            entry_ts=op["entry_ts"], entry_price=op["entry_price"], entry_atr=op["entry_atr"],
            target_r=v.target_r, stop_atr_mult=v.stop_atr_mult,
            exit_ts=exit_ts, exit_price=exit_price, exit_reason=reason,
            ceiling_pnl=gross - self._fee,
        )


# ── the research slate ────────────────────────────────────────────────────────
def default_slate() -> list[ShadowVariant]:
    """Thrust threshold A/B (loose 1.5 = the LIVE control vs cont 2.0), amplitude-
    floor A/B (none / 0.0003 / 0.0004 = live), and the reversal-grab short slate —
    all on 1-minute bars, scored on honest real_pnl."""
    slate = [
        ShadowVariant("thrust_loose", "thrust", {"thr": 1.5, "amp_floor": 0.0004}),  # live control
        ShadowVariant("thrust_cont", "thrust", {"thr": 2.0, "amp_floor": 0.0004}),   # tighter thrust
        ShadowVariant("thrust_noamp", "thrust", {"thr": 1.5, "amp_floor": 0.0}),     # amp floor OFF
        ShadowVariant("thrust_amp03", "thrust", {"thr": 1.5, "amp_floor": 0.0003}),  # looser floor
    ]
    slate += [ShadowVariant(name, "reversal_grab", params)
              for name, params in REVERSAL_SHORT_VARIANTS.items()]
    # target A/B (2026-07-16): the best-firing reversal_grab at a 1.5R take-profit vs
    # the 2.0R default above. A 7-trade tick replay weakly favoured 1.5R (banks a
    # marginal winner that reverses before 1.7-2.0R) — too thin to act on, so let it
    # earn a real read in shadow. Identical entry to rg_short_025_flow25; only target differs.
    slate.append(ShadowVariant("rg_short_025_flow25_t15", "reversal_grab",
                               dict(REVERSAL_SHORT_VARIANTS["rg_short_025_flow25"]), target_r=1.5))
    return slate


# ── service entrypoint ────────────────────────────────────────────────────────
async def run(cfg, *, variants=None, reprice_interval_s: float = 30.0,
              max_seconds: float | None = None) -> None:
    """The shadow desk: subscribe the MD stream, run the variant slate on 1-minute
    bars (same aggregator as the live strategy → no drift), record ceiling trades,
    and periodically reprice closed trades on honest ticks. Touches NO account."""
    from .agg import MinuteBars
    from .capture import open_capture
    from .ipc import MD_STREAM, T_BAR, T_TAPE, Subscriber
    from .repricer import reprice_pending
    from .store import open_store

    store = open_store(cfg.shadow_store_path)  # isolated — no live path, no IBKR
    cap = open_capture(cfg.capture_path)
    sim = ShadowSim(store, variants or default_slate(),
                    value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
    mb = MinuteBars(cfg.bar_lookback)
    mb.warm(cap, cfg.symbol, cfg.bar_lookback)
    md = Subscriber(MD_STREAM, topics=[T_BAR, T_TAPE])
    start = time.monotonic()
    last_reprice = start
    try:
        while max_seconds is None or (time.monotonic() - start) < max_seconds:
            msg = await md.poll(500)
            if msg is not None:
                topic, body = msg
                if topic == T_BAR:
                    mb.fold(body["ts"], body["o"], body["h"], body["l"], body["c"], body["v"])
                elif topic == T_TAPE:
                    bars = mb.bars()
                    if len(bars) >= 6:
                        sim.on_bars(bars, tape_net=body.get("net_flow", 0.0),
                                    window_price_delta=body.get("win_price_delta", 0.0),
                                    in_rth=body.get("in_rth", True))
            if time.monotonic() - last_reprice >= reprice_interval_s:
                try:
                    reprice_pending(store, cap, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
                except Exception:
                    pass
                last_reprice = time.monotonic()
    finally:
        md.close()
        store.close()
        cap.close()


def main() -> None:  # `python -m gazbot7.shadow`
    from .config import RunConfig
    asyncio.run(run(RunConfig()))


if __name__ == "__main__":
    main()
