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
import logging
import os
import time
from dataclasses import dataclass, field

from .deciders import (
    REVERSAL_SHORT_VARIANTS,
    Bar,
    Entry,
    Features,
    Position,
    compute_features,
    exit_absorption,
    exit_adverse_cut,
    exit_chandelier,
    exit_chandelier_lock,
    exit_scalp,
    gate_capitulation,
    gate_grind,
    gate_reversal_grab,
    gate_thrust,
)
from .store import record_shadow_trade

log = logging.getLogger("shadow")   # ★2026-08-04: shadow.py had no module logger


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
    side: str = ""  # "" = two-sided (gate picks); "LONG"/"SHORT" constrains to that direction only
    chandelier: bool = False  # profit exit = the tightening chandelier (ride) instead of the R-target
    chand_start_k: float = 3.5  # chandelier trail width at peak_r=0 (k*ATR); lower = tighter give-back
    chand_tighten: float = 0.75  # how fast k tightens toward min_k (0.5) as the peak extends
    # ── ★2026-08-04 STOP-WIDTH A/B SUPPORT (operator: "build the shadow a/b at 2.0") ──
    # chand_lock: use the loose-THEN-LOCK chandelier (exit_chandelier_lock) instead of the tightening
    # one. Needed for fidelity: live grind_long_B runs exit="chandelier_lock", and mirroring it with the
    # tightening chandelier would model a different desk.
    chand_lock: bool = False
    lock_r: float = 6.0
    lock_k: float = 0.5
    # ★★ decouple_target FIXES A COUPLING THAT WOULD HAVE INVALIDATED THE WHOLE A/B.
    # exit_scalp computes `r = stop_atr_mult * entry_atr` and puts the target at `target_r * r`, so the
    # TARGET IS TIED TO THE STOP WIDTH. Setting stop_atr_mult=2.0 to test a wider stop would silently
    # double the profit target as well, measuring "stop and target both doubled" — a different and
    # useless experiment. With decouple_target the target is held at `target_r * entry_atr` in POINTS
    # regardless of stop width, so the two arms differ in exactly one variable. Default False so no
    # existing variant's behaviour changes.
    decouple_target: bool = False
    # quiet-tape clip, mirroring data/exit_overrides.json so the arms share the LIVE target ladder:
    # ATR < clip_atr_split -> Lot A takes clip_a_usd, Lot B takes clip_b_r floored at clip_b_floor_usd.
    # ★2026-08-04 atr_max: only enter below this ATR. Needed for the CLIP A/B — above clip_atr_split the
    # clip is inactive, so both arms would take identical trades and contribute pure noise to the delta
    # while doubling the row count. Restricting both arms to the regime under test keeps the comparison
    # about the clip and nothing else. 0 = no ceiling (every pre-existing variant).
    atr_max: float = 0.0
    clip_atr_split: float = 0.0
    clip_a_usd: float = 0.0
    clip_b_r: float = 0.0
    clip_b_floor_usd: float = 0.0
    # ── ★2026-08-08 THE OPEN RIDER (gate="clock_rider") ──────────────────────────────────────
    # The first shadow variant with NO SIGNAL. Every other one asks the deciders "is there a
    # setup?"; this asks "what time is it?" and takes the direction the last quarter-hour moved.
    # That is the whole thesis, not laziness: Movement 3's ignition table puts entry on a run's
    # start minute at +$131.65/trade and fifteen minutes late at -$39.76, so anything waiting for
    # confirmation is buying the back half. It has no gate to wait for.
    #   DIRECTION  sign(close - close[-lookback]) — a RAW sign, no threshold. Tested 2026-08-08:
    #              deadbands of 5/10/30pt are worse on both the fitted and the unseen legs.
    #   TIME CAP   the shadow had no time-based exit before this; every other variant runs to a
    #              stop, a target or a chandelier.
    # All fields default to 0/off so no pre-existing variant changes behaviour.
    rider_cadence_min: int = 0                   # fire every N min when flat (0 = not a rider)
    rider_lookback_min: int = 15                 # direction = sign of the move over this window
    rider_win_start_s: int = 13 * 3600           # 13:00 UTC
    rider_win_end_s: int = 14 * 3600 + 45 * 60   # 14:45 UTC — the 08-08 right-edge cut
    time_cap_s: float = 0.0                      # flat at market after this long (0 = no cap)


def _eff_target_r(v: ShadowVariant, atr: float, vpp: float) -> float:
    """The target_r to hand exit_scalp so the sim's target lands where it is MEANT to.

    Two corrections, both mandatory for the stop-width A/B and both no-ops for every pre-existing
    variant (they leave decouple_target False and set no clip):

    1. DECOUPLING. exit_scalp puts the target at `target_r * (stop_atr_mult * atr)`. For a variant whose
       only intended change is a wider STOP, that formula drags the target out with it. Dividing by
       stop_atr_mult holds the target at `target_r * atr` in points, so stop width moves alone.
    2. THE QUIET-TAPE CLIP. Below clip_atr_split the live desk abandons the R-target for a cash clip
       (Lot A) or a floored R (Lot B). Both arms must share it or the A/B compares stop widths across
       two different profit ladders.
    """
    if not v.decouple_target:
        return v.target_r                      # untouched legacy behaviour
    if atr <= 0:
        return v.target_r
    tgt_pt = None
    if v.clip_atr_split and atr < v.clip_atr_split:
        if v.clip_a_usd:
            tgt_pt = v.clip_a_usd / (vpp * v.qty)
        elif v.clip_b_r:
            tgt_pt = max(v.clip_b_r * atr, v.clip_b_floor_usd / (vpp * v.qty))
    if tgt_pt is None:
        tgt_pt = v.target_r * atr
    return tgt_pt / (v.stop_atr_mult * atr)


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
            self._step(v, f, ts, tape_net, window_price_delta, in_rth, now_ms, cap, bars)

    def _rider_entry(self, v: ShadowVariant, bars: list[Bar], ts: int):
        """★2026-08-08 THE CLOCK GATE. No signal — the clock is the trigger.

        Fires when ALL of: inside the UTC window, on a cadence boundary, and enough history to
        measure the lookback. Direction is the raw sign of the lookback move; a dead-flat tape
        (mom == 0) is SKIPPED rather than sent short. The reference harness sends it short via an
        `else` branch, which is an accident of `1 if mom > 0 else -1` — it happened once in 129
        trades, but shadowing an accident would make the shadow a worse mirror, not a better one.
        """
        sec = ts % 86400
        if not (v.rider_win_start_s <= sec < v.rider_win_end_s):
            return None
        if (sec // 60) % max(v.rider_cadence_min, 1):
            return None                      # not on a cadence boundary
        lb = v.rider_lookback_min
        if len(bars) < lb + 1:
            return None                      # not enough history to measure the move
        mom = bars[-1].close - bars[-1 - lb].close
        if mom == 0:
            return None
        return Entry(side="LONG" if mom > 0 else "SHORT", gate="clock_rider",
                     target_r=v.target_r, stop_atr_mult=v.stop_atr_mult)

    def _entry(self, v: ShadowVariant, f: Features, tape_net: float, in_rth: bool, cap: dict,
               bars: list[Bar] | None = None, ts: int = 0):
        if v.gate == "clock_rider":
            return self._rider_entry(v, bars or [], ts)
        if v.gate == "thrust":
            e = gate_thrust(f, **v.params)
        elif v.gate == "reversal_grab":
            e = gate_reversal_grab(f, tape_net=tape_net, in_rth=in_rth, **v.params)
        elif v.gate == "capitulation":
            e = gate_capitulation(f, cap_sell=cap.get("sell", 0.0), cap_buy=cap.get("buy", 0.0),
                                  cap_base=cap.get("base", 0.0), cap_dpx=cap.get("dpx", 0.0),
                                  cap_flip=cap.get("flip", False), **v.params)
        elif v.gate == "grind":
            e = gate_grind(f, tape_net=tape_net, **v.params)
        else:
            e = None
        if e is not None and v.side and e.side != v.side:
            return None   # side-constrained variant (e.g. thrust_short) — drop the wrong direction
        if e is not None and v.atr_max and f.atr >= v.atr_max:
            return None   # regime-restricted variant (the clip A/B runs only where the clip is live)
        return e

    def _absorbed(self, v, side, tape_net, wpd) -> bool:
        return exit_absorption(Position(side, 0.0, 0.0, 0.0), tape_net=tape_net,
                               window_price_delta=wpd, flow_min=v.absorption_flow_min) is not None

    def _open_pos(self, v, entry, f, ts) -> None:
        self._open[v.name] = dict(side=entry.side, entry_price=f.price, entry_atr=f.atr, entry_ts=ts, peak=0.0)

    def _step(self, v, f, ts, tape_net, wpd, in_rth, now_ms, cap, bars=None):
        op = self._open.get(v.name)
        if op is None:
            if v.confirm_s <= 0:  # immediate entry (the default / live control)
                entry = self._entry(v, f, tape_net, in_rth, cap, bars, ts)
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
            fired = (exit_chandelier_lock(pos, f.price, start_k=v.chand_start_k,
                                          lock_r=v.lock_r, lock_k=v.lock_k) if v.chand_lock
                     else exit_chandelier(pos, f.price, start_k=v.chand_start_k,
                                          min_k=0.5, tighten=v.chand_tighten))
            reason = "CHANDELIER" if fired else exit_scalp(
                pos, f.price, target_r=99.0, stop_atr_mult=v.stop_atr_mult)  # target off; STOP only
        else:
            reason = exit_scalp(pos, f.price, target_r=_eff_target_r(v, op["entry_atr"], self._vpp),
                                stop_atr_mult=v.stop_atr_mult)
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
        # ★2026-08-08 TIME CAP — added for the Open Rider, which is flat at market after 45 min.
        # Checked LAST so a stop/target/chandelier that fired on the same bar still wins: the cap
        # is a backstop, and booking a TIME exit where a STOP was hit would flatter the arm.
        if reason is None and v.time_cap_s and (ts - op["entry_ts"]) >= v.time_cap_s:
            reason = "TIME_CAP"
        if reason is not None:
            self._record(v, op, f.price, ts, reason)
            del self._open[v.name]

    def _record_target_r(self, v, atr):
        """What to persist as target_r so the TICK REPRICER reproduces this sim's own target.
        The repricer replays from (target_r, stop_atr_mult) using the same coupled formula, so it must
        receive the EFFECTIVE value — persisting the nominal one would reprice a decoupled variant
        against a target 2x too far away and quietly convert its winners into max-holds."""
        if v.chandelier:
            return 0.0            # 0 = repricer replays the chandelier
        return _eff_target_r(v, atr, self._vpp)

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
            target_r=self._record_target_r(v, op["entry_atr"]),
            stop_atr_mult=v.stop_atr_mult,
            exit_ts=exit_ts, exit_price=exit_price, exit_reason=reason,
            ceiling_pnl=gross - self._fee,
        )


# ★2026-08-02 RETIREMENT (operator, Saturday roster window). The board was −$7,505 and these 13 carried
# −$8,122 of it; the 16 retained are +$616. Filtered HERE rather than deleted at source, because
# REVERSAL_SHORT_VARIANTS also feeds runner.py and tests/test_deciders.py asserts len == 5.
# Each is retired on a CONVICTING number, not on P&L rank — and see PROTECTED below for the ones that
# look retirable and are not. Revert: RETIRED = frozenset().
#   capit_tight              0 fires in 16 days — not thin n, NO n
#   chand_k20 / chand_k25    −$4.39/tr, identical to each other to the cent (J=0.97, r=0.94); the trail
#                            A/B is answered (k35 −$1.79 / k25 −$4.39 / k20 −$4.39) and k35 is KEPT
#   rg_long_fast             −$7.63/tr on 299, PF 0.72; the ATR≥13 floor does not rescue it
#   rg_long_20_t15/_t20/     all three arms red on all 12 days, r=0.86–0.99 — the whole experiment goes,
#     _flow25                not one arm, so no survivorship illusion is left behind
#   thrust_fast              the only losing thrust arm (cont +710 / aligned +396 / loose +130 / fast −430)
#   rg_short_050             86% of its entries also fire flow25, which makes +$103.5 on them
#   rg_short_025_flow25_t15  100% identical entries to flow25; 1.5R −$26 vs 2.0R +$103.5 — zero info lost
#   rg_short_025_flow50_rth  1.17 fires/day — never decidable. A MEASURABILITY cut; the softest of these
#   cb_thrust/_dropped       falsified by its own validation arm: window-matched governed −$878 vs
#                            ungoverned base chand_k35 −$470.5, and the stood-down phantom is +$16.5 —
#                            it vetoed the WINNING sides. Superseded by the durable router.
# ★ NOT retired despite the review recommending them — capit_mid and capit_ride were both convicted for
# "testing the config the roster abandoned", but the roster RE-ADOPTED require_flip=True on 08-02 when
# the 1.0R change was reverted. Their disqualifying reason evaporated, so they stay as the threshold and
# chandelier arms of the live family. 13 retired, not 15.
# ★ PROTECTED, do not retire on P&L: thrust_loose (the un-vetoed control the abs_veto +$2,537.5 claim is
# measured against, hard-coded as BASE in 3 shipped scripts) · capit_loose (now the no-flip CONTROL) ·
# chand_k35 · thrust_short_raw · rg_short_025_raw (controls) · exhaustion_rev (entry substrate for 7
# shipped scripts) · rg_long_fast_v (sole long-reversion coverage) · abs_veto_60s (upper flank — proves
# 55s is a peak, not a floor).
RETIRED: frozenset = frozenset({
    "capit_tight", "chand_k20", "chand_k25", "rg_long_fast",
    "rg_long_20_t15", "rg_long_20_t20", "rg_long_20_flow25", "thrust_fast",
    "rg_short_050", "rg_short_025_flow25_t15", "rg_short_025_flow50_rth",
    "cb_thrust", "cb_thrust_dropped",
})


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
    # ★ thrust_SHORT-specific abs_veto (2026-07-24, operator) — mirror the LIVE thrust_short slot
    # (short-only, chandelier ride) to A/B whether the 55s continuation-confirm fixes its SPIKE-ENTRY
    # whipsaws (3 stops -$127 in violence on 07-24). The confirm waits 55s and enters only if the
    # down-thrust STILL fires + no absorption — dropping the unconfirmed spike-chases. _raw = the
    # matched no-confirm control (both side=SHORT + chandelier, minus the live ER/ATR floors).
    slate += [
        ShadowVariant("thrust_short_raw", "thrust", {"thr": 1.5, "amp_floor": 0.0004},
                      side="SHORT", chandelier=True),
        ShadowVariant("thrust_short_absveto55", "thrust", {"thr": 1.5, "amp_floor": 0.0004},
                      side="SHORT", chandelier=True, confirm_s=55),
    ]
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
    # ★2026-08-02 NEW ARMS — two gaps the retirement review exposed.
    slate += [
        # ★ NIPC's control is deliberately NOT here. ShadowSim._entry dispatches on v.gate and has no
        # "nipc" branch, so an nipc variant would fall through to e=None and sit in the slate NEVER
        # FIRING — a control that silently records zero trades is worse than no control, and it is the
        # exact capit_tight pathology just retired above. NIPC is also a tick state-machine (its own 5s
        # folding, 1-min trigger expiry, 20-min cap), not a 1-minute bar gate, so it cannot ride this
        # loop at all — it would need its own tick loop like FootprintShadow. The control instead runs
        # as a nightly REPLAY: scripts/nipc_replay.py --no-regime drives the SHIPPED decider with the
        # dead-chop filter off over the same tape, which is the same comparison for a fraction of the
        # machinery. See the kill review at n>=40 / 2026-08-07.
        # live capitulation_long lost its twin when the 08-01 flip=False/1.0R change was reverted
        #     on 08-02 (its "78% win" was an MFE stat, not a win rate — see [[mfe-is-not-a-win-rate]]).
        #     capit_loose is now the no-flip CONTROL rather than the mirror, so this is the mirror:
        #     live's exact entry (climax 2.5 / dom 0.60 / require_flip TRUE) at the live 2.0R.
        ShadowVariant("capit_live_mirror", "capitulation",
                      {"climax_min": 2.5, "dom_min": 0.60, "require_flip": True}, target_r=2.0),
    ]
    slate += _stop_width_ab()
    slate += _clip_ab()
    slate += _open_rider()
    return [v for v in slate if v.name not in RETIRED]


def _open_rider() -> list[ShadowVariant]:
    """★2026-08-08 THE OPEN RIDER — 2x2, cadence x stop width. BUILD #2, shadow only.

    Not live, and not eligible to go live: 17 in-sample days earns SHADOW at most, and its own
    skeptic panel voted 2-1 rather than 3-0. Promotion needs ALL FOUR of: +0.15R over 200 shadow
    trades INCLUDING a genuinely non-trending open week, the 14:45 cut, a real 2xATR stop path
    live, and position isolation from the day-rider.

    ★ WHY 2x2 AND NOT ONE ARM. Both axes were re-swept on 2026-08-08 against the 17-day desk book
    and the 5 unseen days, and on both the shipped spec is NOT the peak:

      cadence   ALL 17d $/tr   5 UNSEEN $/tr        stop      ALL 17d $/tr   (n)
        3 min     +37.09          +8.16             1.0xATR      +7.33       264   <- desk house style
        5 min     +35.82         +22.01  (shipped)  2.0xATR     +35.82       129   <- shipped
       10 min     +47.47         +46.88             3.0xATR     +76.51        84
       20 min     +27.69         -18.60

    Cadence 10 beats the shipped 5 on the unseen leg by better than 2:1, and stop width is
    MONOTONE across everything tested. Neither is a reason to re-tune now — the report's own
    finding is that this thing is fitted-looking and needs forward evidence, and picking the best
    backtest cell is how you get a number that does not survive. Running all four forward is how
    you find out which one was real, at zero extra risk because none of them place an order.

    ★ 2R IS COUPLED TO THE STOP ON PURPOSE HERE (decouple_target stays False). The reference
    harness computes `targ = entry + dir * (stop_k * atr) * rr`, so the target IS a multiple of
    the stop distance. The 3.0x arms therefore run a WIDER target too, which is exactly what the
    sweep above measured. This is the opposite of the stop-width A/B above, where decoupling was
    essential — there the question was "is a wider stop better?"; here it is "is this whole
    published cell better?".
    """
    common = dict(gate="clock_rider", params={}, target_r=2.0, time_cap_s=45 * 60,
                  rider_lookback_min=15, adverse_cut_atr=99.0, absorption_flow_min=1e9)
    return [
        ShadowVariant("odr_c5_s20", rider_cadence_min=5, stop_atr_mult=2.0, **common),
        ShadowVariant("odr_c5_s30", rider_cadence_min=5, stop_atr_mult=3.0, **common),
        ShadowVariant("odr_c10_s20", rider_cadence_min=10, stop_atr_mult=2.0, **common),
        ShadowVariant("odr_c10_s30", rider_cadence_min=10, stop_atr_mult=3.0, **common),
    ]


# ★★2026-08-04 CLIP A/B — operator: "do the shadow a/b" after disputing the backtest.
#
# THE DISAGREEMENT, stated fairly. scripts/atr_split_sweep2.py says that below ATR 22 the clip wins MORE
# OFTEN (41% vs 39%) and takes MORE trades (+69) but nets LESS (-$1,219 over 11 days). The operator, who
# watches the desk all day: "i know in low tape we have never taken profit. this is an enormous
# improvement." Both can be true — win rate and expectancy are different quantities — but there is also a
# real reason to distrust the backtest here, and it is not a small one:
#
#   ★ THE SWEEP'S ENTRY POPULATION IS NOT THE LIVE ONE. It calls the raw gate functions with no ER floor,
#     no ATR floor, no 55s absorption veto, no benching — so its "live exit" arm trades a larger,
#     unfiltered signal set and books +$3,266 in exactly the low-tape regime where the operator says the
#     real desk never banked anything. An 11-day in-sample study with no slippage and the wrong entry
#     population is weaker evidence than a year of watching the thing.
#
# So this settles it FORWARD, with no modelling assumptions: real gates, live feed, identical signals,
# only the profit target differs. atr_max=22 keeps both arms inside the regime under test — above the
# split the clip is inactive and the arms would be identical, adding rows and no information.
#
# THREE SLOTS CHOSEN TO SPAN THE PREDICTION, so the backtest is falsifiable rather than just re-run:
#   cx_grindA  2.5R  — sweep says clip is MUCH worse (43% win but $1.9/tr vs 32% and $4.5/tr)
#   cx_absLA   1.0R  — clip RESCUES this one: at ATR 11.3 its R-target is $22.60, the clip pays $40
#   cx_absSB   2.5R  — the one slot where the sweep says the clip WINS (+$153)
# If the forward ordering matches, the backtest is credible. If cx_grindA's clip arm wins, it is not.
def _clip_ab() -> list[ShadowVariant]:
    THRUST = {"thr": 1.5, "amp_floor": 0.0004}
    GRIND = {"slope_min": 0.4, "fast_slope": True, "ext_hi": 2.0}
    base = dict(decouple_target=True, atr_max=22.0, qty=1.0, stop_atr_mult=1.0)
    A_CLIP = dict(clip_atr_split=22.0, clip_a_usd=40.0)
    B_CLIP = dict(clip_atr_split=22.0, clip_b_r=1.75, clip_b_floor_usd=60.0)
    return [
        ShadowVariant("cx_grindA_live", "grind", GRIND, side="LONG", target_r=2.5, **base),
        ShadowVariant("cx_grindA_clip", "grind", GRIND, side="LONG", target_r=2.5, **base, **A_CLIP),
        ShadowVariant("cx_absLA_live", "thrust", THRUST, side="LONG", confirm_s=55,
                      target_r=1.0, **base),
        ShadowVariant("cx_absLA_clip", "thrust", THRUST, side="LONG", confirm_s=55,
                      target_r=1.0, **base, **A_CLIP),
        ShadowVariant("cx_absSB_live", "thrust", THRUST, side="SHORT", confirm_s=55,
                      target_r=2.5, **base),
        ShadowVariant("cx_absSB_clip", "thrust", THRUST, side="SHORT", confirm_s=55,
                      target_r=2.5, **base, **B_CLIP),
    ]


# ★★2026-08-04 STOP-WIDTH A/B — operator: "build the shadow a/b at 2.0".
#
# WHY IT EXISTS. scripts/stop_width_study.py asked whether the 1xATR stop is too tight for the momentum
# gates by replaying live entries at 1.0/1.5/2.0. It answered ONE of the two questions cleanly: 1.5x is
# the worst of both worlds (rescued 2 of 52 stopped trades while making the other 50 lose 50% more,
# −$1,126). It could NOT settle 2.0x, because the replay only reproduced the live book to within 18% —
# the residual sat in a handful of high-ATR trades where the tick replay and the live fills disagree on
# which of stop/target was touched first. No amount of further modelling fixes a fill-ordering
# disagreement; only paired live-feed arms do.
#
# WHY PAIRED ARMS INSTEAD OF COMPARING TO THE LIVE BOOK. Scoring a 2.0x sim against the live 1.0x desk
# reintroduces every difference that is not stop width — real slippage, real fill ordering, the ATR the
# live desk actually read. Both arms here run on the same feed, the same bar, the same gate and the same
# entry, so the ONLY difference is stop_atr_mult. The deliverable is the DELTA between arms, which is
# exactly the quantity today's work showed to be robust while absolute levels were not.
#
# ⚠ THE TRAP THAT WOULD HAVE MADE THIS MEANINGLESS. exit_scalp sets the target at
# `target_r * (stop_atr_mult * atr)`, so simply raising stop_atr_mult to 2.0 ALSO DOUBLES THE PROFIT
# TARGET. That measures "stop and target both doubled" — a different experiment that would have looked
# plausible and been worthless. decouple_target=True holds the target in POINTS at `target_r * atr` on
# both arms. Every pair below is therefore identical except the stop.
#
# Fidelity notes: Lot B of grind_long is exit="chandelier_lock" live, so chand_lock mirrors it rather
# than using the tightening chandelier. The quiet-tape clip (exit_overrides.json: atr_split 22, Lot A
# $40, Lot B 1.75R floored $60) is applied to BOTH arms so they share the live profit ladder.
# abs_veto = thrust + the 55s absorption veto, so confirm_s=55 on both arms.
#
# Read it with: PYTHONPATH=src .venv/bin/python scripts/stop_width_ab.py
_CLIP = dict(clip_atr_split=22.0, clip_b_floor_usd=60.0)
_A_CLIP = dict(clip_a_usd=40.0, **_CLIP)
_B_CLIP = dict(clip_b_r=1.75, **_CLIP)


def _stop_width_ab() -> list[ShadowVariant]:
    THRUST = {"thr": 1.5, "amp_floor": 0.0004}
    GRIND = {"slope_min": 0.4, "fast_slope": True, "ext_hi": 2.0}
    out: list[ShadowVariant] = []
    for k, sfx in ((1.0, "k10"), (2.0, "k20")):
        common = dict(decouple_target=True, stop_atr_mult=k, qty=1.0)
        out += [
            # grind_long — Lot A fixed 2.5R scalp, Lot B loose-then-lock chandelier
            ShadowVariant(f"sw_grind_A_{sfx}", "grind", GRIND, side="LONG",
                          target_r=2.5, **common, **_A_CLIP),
            ShadowVariant(f"sw_grind_B_{sfx}", "grind", GRIND, side="LONG",
                          chandelier=True, chand_lock=True, chand_start_k=3.5, lock_r=6.0, lock_k=0.5,
                          **common),
            # abs_veto_long — A 1.0R, B 1.5R, both scalp, both behind the 55s veto
            ShadowVariant(f"sw_absL_A_{sfx}", "thrust", THRUST, side="LONG", confirm_s=55,
                          target_r=1.0, **common, **_A_CLIP),
            ShadowVariant(f"sw_absL_B_{sfx}", "thrust", THRUST, side="LONG", confirm_s=55,
                          target_r=1.5, **common, **_B_CLIP),
            # abs_veto_short — A 1.5R, B 2.5R
            ShadowVariant(f"sw_absS_A_{sfx}", "thrust", THRUST, side="SHORT", confirm_s=55,
                          target_r=1.5, **common, **_A_CLIP),
            ShadowVariant(f"sw_absS_B_{sfx}", "thrust", THRUST, side="SHORT", confirm_s=55,
                          target_r=2.5, **common, **_B_CLIP),
        ]
    return out


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
    from .footprint import FootprintShadow
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
    # ★2026-08-02 RETIRED — it is in RETIRED, so it no longer runs. It was falsified by its own
    # validation arm: window-matched, GOVERNED −$878.0 against the ungoverned base chand_k35 −$470.5,
    # and the phantom of the sides it stood down is +$16.5 — i.e. it vetoed the winning sides. The
    # durable router supersedes it. Revert: drop "cb_thrust" from RETIRED.
    breaker = (SessionDirectionBreaker(store, symbol=cfg.symbol,
                                       value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
               if "cb_thrust" not in RETIRED else None)
    # the exhaustion-reversal footprint rides its OWN tick+book loop (not bar-based) —
    # observe-only incubation, reads capture directly, records exhaustion_rev trades.
    footprint = FootprintShadow(store, cfg.symbol,
                                value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
    # ★2026-08-04 CL sims + signal journal. Opt-in via GAZBOT7_CL_SIMS=1 so it can be switched off
    # without a code change, and constructed inside try/except so a fault here leaves the shadow desk
    # running exactly as before (cl stays None and every call site is guarded).
    cl = None
    if os.environ.get("GAZBOT7_CL_SIMS") == "1":
        try:
            from .cl_sims import ClSims
            cl = ClSims(store, store, value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
            log.info("CL sims ENABLED — 8 mirrored gates, trades only on a Claude PASS; "
                     "signal_journal recording every fire")
        except Exception as e:
            log.warning("CL sims disabled (construction failed, desk unaffected): %s", e)
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
                    # ★★2026-08-04 SAME BUG AS tournament.py — MD_STREAM is MULTI-SYMBOL and this
                    # folded every symbol into one deque. Latent for the desk's whole life; adding MGC
                    # to md capture at 17:30 today exposed it, interleaving gold (~3,300) with MNQ
                    # (~29,800) so true range across the jump made ATR read 1848 against a true 15.
                    # Every shadow sim is ATR-relative, so all 36 — including the stop-width and clip
                    # A/B arms built today — were being fed corrupt features from 17:30 onward.
                    if body.get("symbol") != cfg.symbol:
                        continue
                    mb.fold(body["ts"], body["o"], body["h"], body["l"], body["c"], body["v"])
                elif topic == T_TAPE:
                    now_ms = body.get("ts_ms")
                    bars = mb.bars()
                    if len(bars) >= 6:
                        capft = capitulation_tape(cap, cfg.symbol, now_ms) if now_ms else {}
                        sim.on_bars(bars, tape_net=body.get("net_flow", 0.0),
                                    window_price_delta=body.get("win_price_delta", 0.0),
                                    in_rth=body.get("in_rth", True), now_ms=now_ms, cap=capft)
                        if breaker is not None:   # ★2026-08-02 None once cb_thrust is RETIRED
                            breaker.on_bars(bars, tape_net=body.get("net_flow", 0.0),
                                            window_price_delta=body.get("win_price_delta", 0.0),
                                            in_rth=body.get("in_rth", True), now_ms=now_ms)
                        # ★2026-08-04 SIGNAL JOURNAL + CL SIMS. Both live here rather than in the
                        # live desk deliberately: this loop already evaluates every gate on the same
                        # feed each second, so the signals are already present and nothing that
                        # touches money gains a new failure surface. Wrapped whole — a fault in the
                        # experiment must never take the shadow desk down with it.
                        if cl is not None:
                            try:
                                cl.step(bars, price=body.get("last") or bars[-1].close,
                                        tape_net=body.get("net_flow", 0.0), now_ms=now_ms,
                                        in_rth=body.get("in_rth", True), cap=capft)
                            except Exception as e:
                                log.warning("cl_sims step failed (experiment only, desk unaffected): %s", e)
                    if now_ms:
                        try:
                            footprint.on_cycle(cap, now_ms)   # observe-only; must never break the loop
                        except Exception:
                            pass
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
