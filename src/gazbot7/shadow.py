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
    exit_chandelier,
    exit_scalp,
    gate_capitulation,
    gate_grind,
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
    confirm_s: float = 0.0  # delayed-entry absorption veto: wait N s before entering (0 = immediate)
    chandelier: bool = False  # profit exit = the tightening chandelier (ride) instead of the R-target
    chand_start_k: float = 3.5  # chandelier trail width at peak_r=0 (k*ATR); lower = tighter give-back
    chand_tighten: float = 0.75  # how fast k tightens toward min_k (0.5) as the peak extends


class ShadowSim:
    def __init__(self, store, variants: list[ShadowVariant], *, value_per_point: float = 2.0,
                 fee_rt: float = 1.5, absorption_min_loss_usd: float = 60.0) -> None:
        self._store = store
        self._variants = variants
        self._vpp = value_per_point
        self._fee = fee_rt
        self._abs_min_loss = absorption_min_loss_usd  # absorption = catastrophe backstop, not a green-scalp cutter
        self._open: dict[str, dict] = {}  # variant name → open sim position
        self._pending: dict[str, dict] = {}  # variant name → pending entry watching absorption

    def on_bars(self, bars: list[Bar], *, tape_net: float = 0.0,
                window_price_delta: float = 0.0, in_rth: bool = True, now_ms: int | None = None,
                cap: dict | None = None) -> None:
        f = compute_features(bars)
        ts = bars[-1].ts
        now_ms = now_ms if now_ms is not None else ts * 1000  # wall-clock for the entry delay
        cap = cap or {}
        for v in self._variants:
            self._step(v, f, ts, tape_net, window_price_delta, in_rth, now_ms, cap)

    def _entry(self, v: ShadowVariant, f: Features, tape_net: float, in_rth: bool, cap: dict):
        if v.gate == "thrust":
            return gate_thrust(f, **v.params)
        if v.gate == "reversal_grab":
            return gate_reversal_grab(f, tape_net=tape_net, in_rth=in_rth, **v.params)
        if v.gate == "capitulation":
            return gate_capitulation(f, cap_sell=cap.get("sell", 0.0), cap_buy=cap.get("buy", 0.0),
                                     cap_base=cap.get("base", 0.0), cap_dpx=cap.get("dpx", 0.0),
                                     cap_flip=cap.get("flip", False), **v.params)
        if v.gate == "grind":
            return gate_grind(f, tape_net=tape_net, **v.params)
        return None

    def _absorbed(self, v, side, tape_net, wpd) -> bool:
        return exit_absorption(Position(side, 0.0, 0.0, 0.0), tape_net=tape_net,
                               window_price_delta=wpd, flow_min=v.absorption_flow_min) is not None

    def _open_pos(self, v, entry, f, ts) -> None:
        self._open[v.name] = dict(side=entry.side, entry_price=f.price, entry_atr=f.atr, entry_ts=ts, peak=0.0)

    def _step(self, v, f, ts, tape_net, wpd, in_rth, now_ms, cap):
        op = self._open.get(v.name)
        if op is None:
            if v.confirm_s <= 0:  # immediate entry (the default / live control)
                entry = self._entry(v, f, tape_net, in_rth, cap)
                if entry is not None:
                    self._open_pos(v, entry, f, ts)
                return
            # DELAYED ENTRY — raise the signal, watch absorption for confirm_s, enter
            # only if the thrust still fires and no absorption appeared (mirrors the
            # live strategy._entry, at wall-clock resolution).
            pc = self._pending.get(v.name)
            if pc is None:
                entry = self._entry(v, f, tape_net, in_rth, cap)
                if entry is not None:
                    self._pending[v.name] = {"side": entry.side, "start_ms": now_ms}
                return
            if self._absorbed(v, pc["side"], tape_net, wpd):
                del self._pending[v.name]
                return
            if now_ms - pc["start_ms"] < v.confirm_s * 1000:
                return  # still watching
            del self._pending[v.name]
            entry = self._entry(v, f, tape_net, in_rth, cap)
            if entry is not None and entry.side == pc["side"] and not self._absorbed(v, entry.side, tape_net, wpd):
                self._open_pos(v, entry, f, ts)
            return
        self._pending.pop(v.name, None)  # holding — abandon any pending confirm
        # manage — track peak favourable, then check the sim exit stack
        fav = (f.price - op["entry_price"]) if op["side"] == "LONG" else (op["entry_price"] - f.price)
        op["peak"] = max(op["peak"], fav)
        pos = Position(op["side"], op["entry_price"], op["entry_atr"], op["peak"])
        # chandelier variants RIDE on chandelier + native STOP only (matches the live
        # desk + the backtest) — the early risk cuts would choke the ride, so they only
        # apply to the fixed-R-target variants.
        if v.chandelier:
            fired = exit_chandelier(pos, f.price, start_k=v.chand_start_k,
                                    min_k=0.5, tighten=v.chand_tighten)
            reason = "CHANDELIER" if fired else exit_scalp(
                pos, f.price, target_r=99.0, stop_atr_mult=v.stop_atr_mult)  # target off; STOP only
        else:
            reason = exit_scalp(pos, f.price, target_r=v.target_r, stop_atr_mult=v.stop_atr_mult)
            if reason is None and exit_adverse_cut(pos, f.price, cut_atr=v.adverse_cut_atr):
                reason = "ADVERSE_CUT"
            # absorption is a CATASTROPHE backstop (operator 2026-07-16): only once the
            # trade is deep underwater (>= absorption_min_loss_usd) — mirrors the live
            # strategy._exit. Without this floor it guillotines green scalps and, since
            # the signal persists, insta-re-enters → churn (bug that faked sims 10/11/12).
            loss_usd = -fav * self._vpp  # >0 only when offside
            if (reason is None and loss_usd >= self._abs_min_loss
                    and exit_absorption(pos, tape_net=tape_net, window_price_delta=wpd,
                                        flow_min=v.absorption_flow_min)):
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
            target_r=(0.0 if v.chandelier else v.target_r),  # 0 = repricer replays the chandelier
            stop_atr_mult=v.stop_atr_mult,
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
        # 2026-07-16 — thrust_loose + the sign filter: only fire WITH the VWAP slope.
        # A n=50 measurement said counter-trend thrust IS the bleed; this forward-tests
        # whether the filter flips thrust ~breakeven vs the −$903 control.
        ShadowVariant("thrust_aligned", "thrust", {"thr": 1.5, "amp_floor": 0.0004, "slope_align": True}),
        # 2026-07-16 — FAST trigger: fire off the 2-bar impulse (not the lagging 5-bar)
        # + alignment, no veto. Tests "jump in near the START" of a move instead of
        # arriving at the bottom 5-6 min late. Alignment keeps it from chop-firing.
        ShadowVariant("thrust_fast", "thrust", {"thr": 1.5, "amp_floor": 0.0004, "slope_align": True, "fast": True}),
    ]
    # CHANDELIER give-back A/B (2026-07-17, operator "2 or 3 chandeliers ready … pick
    # the best for the day"). SAME entry as the live gate (thrust_loose) — only the
    # profit trail differs. The live desk runs start_k=3.5 (chand_k35 = the faithful
    # control); on 07-17's huge ATR (44pt) that gave back ~$135 of a +$224 MNQ run,
    # because give-back = k*ATR and a +$224 peak is only peak_r~2.5 (k hadn't tightened).
    # k25/k20 lock in sooner. Friday scores lock-in GAINED vs runner CLIPPED, per ATR
    # regime — that regime split is how we learn WHICH chandelier the day wants.
    slate += [
        ShadowVariant("chand_k35", "thrust", {"thr": 1.5, "amp_floor": 0.0004},
                      chandelier=True, chand_start_k=3.5),  # = the LIVE desk exit (control)
        ShadowVariant("chand_k25", "thrust", {"thr": 1.5, "amp_floor": 0.0004},
                      chandelier=True, chand_start_k=2.5),
        ShadowVariant("chand_k20", "thrust", {"thr": 1.5, "amp_floor": 0.0004},
                      chandelier=True, chand_start_k=2.0),
    ]
    # CAPITULATION fade (2026-07-16, from the L1/tape footprint) — fade a fast flush
    # driven by a one-sided aggressor climax. Tight (require the delta flip, big climax)
    # → mid → loose (fade the climax itself). target 1R = the typical ~1-ATR bounce.
    slate += [
        ShadowVariant("capit_tight", "capitulation",
                      {"climax_min": 8.0, "dom_min": 0.85, "require_flip": True}, target_r=1.0),
        ShadowVariant("capit_mid", "capitulation",
                      {"climax_min": 4.0, "dom_min": 0.75, "require_flip": True}, target_r=1.0),
        ShadowVariant("capit_loose", "capitulation",
                      {"climax_min": 2.5, "dom_min": 0.60, "require_flip": False}, target_r=1.0),
        # capit that RIDES with the chandelier instead of the 1R scalp — to capture a
        # flush→reclaim→grind continuation (today's 13:55 +200pt run started as a flush).
        ShadowVariant("capit_ride", "capitulation",
                      {"climax_min": 4.0, "dom_min": 0.75, "require_flip": True}, chandelier=True),
    ]
    # GRIND (2026-07-16) — trend CONTINUATION: ride an established VWAP slope that
    # thrust (a burst gate) misses. L2 was balanced through today's +200pt grind, so
    # this is price/flow, not book. Chandelier-ridden. slope floor 0.4 vs 0.6.
    slate += [
    ]
    # FAST-SLOPE rewire (2026-07-16) — the short-window slope flips at reversals where
    # the 60-bar slope lags 30-40min and wrong-foots these gates. PROVEN on the 15:17
    # run: rg_long_fast enters @29351 (13% of the run) + chandelier bank +$161, vs the
    # live desk's -$50 top-tick. grind_fast lets grind reverse direction quickly too.
    slate += [
        ShadowVariant("rg_long_fast", "reversal_grab",
                      {"side": "LONG", "ext_min": 2.0, "turn_atr": 0.15, "fast_slope": True, "fast_turn": True},
                      chandelier=True),
        ShadowVariant("grind_fast", "grind", {"slope_min": 0.4, "fast_slope": True}, chandelier=True),
        # + a VOLATILITY floor (atr>=13): a full-day backtest showed the noise is
        # almost all low-ATR fizzles — the floor cut 28→~13 trades, +$182→+$400,
        # 35%→46% win, KEEPING both big runs. The vol regime = the on/off switch.
        ShadowVariant("rg_long_fast_v", "reversal_grab",
                      {"side": "LONG", "ext_min": 2.0, "turn_atr": 0.15, "fast_slope": True,
                       "fast_turn": True, "atr_min": 13.0}, chandelier=True),
    ]
    # absorption-veto DURATION sweep (2026-07-16, operator) — thrust_loose + the
    # delayed-entry veto at 50/55/60/70/90s. thrust_loose (0s, above) is the no-veto
    # control; live desk runs 45s. Which wait best trades avoided-bleed vs missed moves?
    slate += [ShadowVariant(f"abs_veto_{s}s", "thrust", {"thr": 1.5, "amp_floor": 0.0004}, confirm_s=s)
              for s in (50, 55, 60)]  # 70/90s removed — failures (too much lag)
    slate += [ShadowVariant(name, "reversal_grab", params)
              for name, params in REVERSAL_SHORT_VARIANTS.items()]
    # target A/B (2026-07-16): the best-firing reversal_grab at a 1.5R take-profit vs
    # the 2.0R default above. A 7-trade tick replay weakly favoured 1.5R (banks a
    # marginal winner that reverses before 1.7-2.0R) — too thin to act on, so let it
    # earn a real read in shadow. Identical entry to rg_short_025_flow25; only target differs.
    slate.append(ShadowVariant("rg_short_025_flow25_t15", "reversal_grab",
                               dict(REVERSAL_SHORT_VARIANTS["rg_short_025_flow25"]), target_r=1.5))
    # LONG reversal mirror (2026-07-16) — fade a stretch BELOW VWAP turning up. The
    # thresholds are from a tick grid-search, NOT a copy of the shorts: the long side
    # needs a looser extension (ext 2.0 not 2.5) + a looser turn (0.25) + a 1.5R
    # target (best in-sample; 2.0/2.5 barely fired and lost). A tight spread to
    # forward-test: the winner, a 2R-target control, and a net-BUY-flow cut.
    slate += [
        ShadowVariant("rg_long_20_t15", "reversal_grab",
                      {"side": "LONG", "ext_min": 2.0, "turn_atr": 0.25}, target_r=1.5),
        ShadowVariant("rg_long_20_t20", "reversal_grab",
                      {"side": "LONG", "ext_min": 2.0, "turn_atr": 0.25}, target_r=2.0),
        ShadowVariant("rg_long_20_flow25", "reversal_grab",
                      {"side": "LONG", "ext_min": 2.0, "turn_atr": 0.25, "flow_min": 25}, target_r=1.5),
    ]
    return slate


def chandelier_params() -> dict[str, tuple[float, float, float]]:
    """{strategy name → (start_k, min_k, tighten)} for every chandelier variant, so
    the repricer replays EACH variant's OWN trail on the tick path instead of the 3.5
    default — otherwise chand_k20/k25 would be scored as if they were the live 3.5 and
    the whole A/B would be meaningless. min_k is fixed at 0.5 (the tight floor)."""
    return {v.name: (v.chand_start_k, 0.5, v.chand_tighten)
            for v in default_slate() if v.chandelier}


# ── service entrypoint ────────────────────────────────────────────────────────
async def run(cfg, *, variants=None, reprice_interval_s: float = 30.0,
              max_seconds: float | None = None) -> None:
    """The shadow desk: subscribe the MD stream, run the variant slate on 1-minute
    bars (same aggregator as the live strategy → no drift), record ceiling trades,
    and periodically reprice closed trades on honest ticks. Touches NO account."""
    from .agg import MinuteBars
    from .capture import capitulation_tape, open_capture
    from .cb import SessionDirectionBreaker
    from .ipc import MD_STREAM, T_BAR, T_TAPE, Subscriber
    from .repricer import reprice_pending
    from .store import open_store

    store = open_store(cfg.shadow_store_path)  # isolated — no live path, no IBKR
    cap = open_capture(cfg.capture_path)
    sim = ShadowSim(store, variants or default_slate(),
                    value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt,
                    absorption_min_loss_usd=cfg.absorption_min_loss_usd)
    # the per-side direction circuit breaker (prototype) rides the same feed alongside
    # the variant slate, booking cb_thrust (governed) + cb_thrust_dropped (phantom).
    breaker = SessionDirectionBreaker(store, symbol=cfg.symbol,
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
                        capft = capitulation_tape(cap, cfg.symbol, body["ts_ms"]) if body.get("ts_ms") else {}
                        sim.on_bars(bars, tape_net=body.get("net_flow", 0.0),
                                    window_price_delta=body.get("win_price_delta", 0.0),
                                    in_rth=body.get("in_rth", True), now_ms=body.get("ts_ms"), cap=capft)
                        breaker.on_bars(bars, tape_net=body.get("net_flow", 0.0),
                                        window_price_delta=body.get("win_price_delta", 0.0),
                                        in_rth=body.get("in_rth", True), now_ms=body.get("ts_ms"))
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
