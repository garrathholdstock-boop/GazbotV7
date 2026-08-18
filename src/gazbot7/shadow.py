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
import json
import logging
import os
import time
from dataclasses import dataclass, field

from .levelbreak import gate_level_break  # noqa: E402
from .deciders import (
    gate_board,
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

# ★2026-08-16 THE OPEN RIDER'S WINDOW, named once. 14:45 is the 08-08 corrected right edge, NOT the
# original 15:00: the 14:45–15:00 slice is −$446 across all days and −$453 on the unseen leg alone.
# Read by gate="clock_rider" and nothing else — see ShadowVariant.__post_init__.
RIDER_WIN_START_S = 13 * 3600              # 13:00 UTC
RIDER_WIN_END_S = 14 * 3600 + 45 * 60      # 14:45 UTC


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
    # ★2026-08-15 (audit #13). gf_MGC.md: "mine requires the peak to reach 2.0 ATR before the trail
    # arms at all, whereas exit_chandelier_lock effectively arms as soon as the peak clears the
    # give-back ... if you want an exact mirror the ShadowVariant needs one new field — chand_arm_k".
    # 0.0 = arm immediately, which is the existing behaviour for every MNQ variant.
    chand_arm_k: float = 0.0
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
    # ★2026-08-16 BUILD #13 — ER band at entry, so a per-RUNG proposal can be shadowed as the rung it
    # was measured on. The rungs are ER30 thresholds (exit_ladder_lab_v2: >=0.50 BIG-TREND,
    # >=0.30 MED-TREND), so MED-TREND is [0.30, 0.50). 0.0 on either side = unbounded, which is every
    # pre-existing variant. ⚠ An arm carrying a rung's numbers WITHOUT its band is not that rung — it
    # is the proposal averaged over regimes it was never graded in.
    er_min: float = 0.0
    er_max: float = 0.0
    # ★2026-08-16 BUILD #18 — a FIXED-POINTS target ("bank Lot A at +20 points onside"). R-multiples
    # scale with ATR; this deliberately does not, which is the whole hypothesis. Points, not dollars,
    # so it is instrument-agnostic. 0.0 = use target_r as before.
    target_pt: float = 0.0
    # ★2026-08-16 BUILD #15 — "require_flip OR a 90-second timeout". The gate is PURE and stateless:
    # it sees a rolling tape window and cannot know how long a climax has been waiting for a flip.
    # That state lives here. >0 = take a climax that has held this many seconds WITHOUT a flip.
    # The play: take the flush when buyers are slow to show, instead of waiting for a flip that
    # never comes. 0 = off, which is every other variant.
    flip_timeout_s: int = 0
    # ★2026-08-16 BUILD #16 — the quiet-tape clip STANDS DOWN on a range-break ignition.
    # The clip exists because quiet tape does not pay a full R-target. A range break is the one quiet
    # setup that CAN run, so clipping it may be cutting exactly the move the clip was never aimed at.
    # BRK is the report's own definition (gf_chop_scalp §2): the bar closes outside the PRIOR 2h
    # high/low. Not my invention — using a hand-rolled break test here would make the arm answer a
    # different question from the one asked.
    clip_standdown_on_brk: bool = False
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
    # ★★2026-08-16 −1 = UNSET, and the window is read ONLY by _rider_entry (gate="clock_rider").
    # It used to default to 13:00–14:45 on EVERY variant, so `rider_w5` — gate="board", whose real
    # window is hh_lo/hh_hi=13–20 in params — resolved with a rider_win_end_s of 14:45 that nothing
    # reads. Inspecting the arm showed a 1h45m window for a gate that trades 7 hours. A config field
    # carried but consumed by no one is CLAUDE.md trap #9, and the danger is not today's confusion:
    # it is that "fixing" this arm's window by editing the field would be a silent no-op.
    # __post_init__ fills the clock_rider default and REFUSES the field on any other gate.
    rider_win_start_s: int = -1                  # clock_rider only; -1 = unset
    rider_win_end_s: int = -1                    # clock_rider only; -1 = unset
    time_cap_s: float = 0.0                      # flat at market after this long (0 = no cap)
    # ★2026-08-13 THE DRIFT-DIRECTION GATE. Once drift.py's detector CONFIRMS a session direction,
    # refuse rider entries against it. Entries BEFORE confirmation stay completely unguarded — that
    # asymmetry is the whole design; see _rider_entry.
    rider_gate_drift: bool = False

    def __post_init__(self) -> None:
        if self.gate == "clock_rider":
            # Preserve the historical defaults exactly for the arms that actually read them.
            if self.rider_win_start_s < 0:
                self.rider_win_start_s = RIDER_WIN_START_S
            if self.rider_win_end_s < 0:
                self.rider_win_end_s = RIDER_WIN_END_S
        elif self.rider_win_start_s >= 0 or self.rider_win_end_s >= 0:
            raise ValueError(
                f"{self.name}: rider_win_start_s/rider_win_end_s are read ONLY by "
                f"gate='clock_rider' (this arm is gate='{self.gate}'). Setting them here changes "
                f"NOTHING. A board arm's window is hh_lo/hh_hi in params.")


def _brk_2h(bars, price: float) -> bool:
    """Range-break ignition: does `price` sit outside the PRIOR 2 hours' high/low?

    ★ THE REPORT'S OWN DEFINITION (gf_chop_scalp §2, the regime taxonomy): "BRK = block closes
    outside the prior 2h high/low". Using a hand-rolled break test here would make BUILD #16 answer a
    different question from the one asked. The window EXCLUDES the current bar — a bar cannot break a
    level it is itself setting, which is the circularity detect_break() also guards against.
    """
    if not bars or len(bars) < 30:
        return False                       # not enough history to claim a break either way
    w = bars[-121:-1] if len(bars) > 121 else bars[:-1]
    if not w:
        return False
    return price > max(b.high for b in w) or price < min(b.low for b in w)


def _eff_target_r(v: ShadowVariant, atr: float, vpp: float, brk: bool = False) -> float:
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
    # ★2026-08-16 BUILD #18 — a FIXED-POINTS target, checked FIRST and independent of decoupling.
    # "Bank Lot A at +20 points onside" is a claim that the right exit does NOT scale with volatility,
    # so it must not be expressed as an R-multiple: exit_scalp puts the target at
    # target_r * stop_atr_mult * atr, and dividing back out is exactly how a fixed distance is
    # recovered. If ATR is unusable there is no honest conversion, so it falls back rather than
    # inventing one.
    if brk and v.clip_standdown_on_brk:
        # ★ BUILD #16 — ignition was a range break: skip the clip, keep the full R-target. Evaluated
        # BEFORE the clip branch below, because standing down means the clip never applies at all.
        return v.target_r
    if v.target_pt and atr > 0 and v.stop_atr_mult > 0:
        return v.target_pt / (v.stop_atr_mult * atr)
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
                 fee_rt: float = 1.5, absorption_min_loss_usd: float = 60.0,
                 store_path: str | None = None) -> None:
        self._store = store
        self._variants = variants
        self._vpp = value_per_point
        self._fee = fee_rt
        self._abs_min_loss = absorption_min_loss_usd  # absorption = catastrophe backstop, not a green-scalp cutter
        self._open: dict[str, dict] = {}  # variant name → open sim position
        # ★★★2026-08-18 OPEN SIM POSITIONS ARE PUBLISHED, because until now they were INVISIBLE.
        # record_shadow_trade() only fires on EXIT, so a variant sitting in a trade and a variant
        # not firing at all looked identical from outside. That is how rider_w5 taking ONE trade on
        # a session the gate was true for 32 minutes had to be reconstructed by replaying the tape
        # four hours later. "Blocked" and "dead" must not render the same — the MGC lesson in a
        # different costume. Written on OPEN and on CLOSE only (not per tick), next to the store.
        self._open_path = f"{store_path}.open.json" if store_path else None
        self._publish_open()
        self._pending: dict[str, dict] = {}  # variant name → pending entry watching absorption
        # ★2026-08-15 level-break state (audit fixes #2/#3). `_lb_seen` latches the last bar a
        # level_break variant was evaluated on, so one completed bar produces at most one decision
        # however many tape messages arrive. `_lb_cool` holds the bar-ts before which it may not
        # re-enter, set from the EXIT — the research measures the cooldown from the close
        # (`busy_until = ts + held + cooldown*60`), not from the entry.
        self._lb_seen: dict[str, int] = {}
        # ★2026-08-15 GENERALISED from level_break to any variant whose params declare
        # `cooldown_min`. rider_w5 had the identical defect: its backtest ran one position at a time
        # with a 15-MINUTE cooldown after every exit (gf_rider_engine.run_trades,
        # `busy_until = r.ts + held + cooldown_min * 60`), which is why 337 signals a session
        # collapse to ~6 trades. Without it the shadow fires far more often than the thing that was
        # measured, and every number quoted for it came from the constrained version.
        self._cool_until: dict[str, float] = {}
        # BUILD #15: variant -> ts a flip-less climax was FIRST seen (the timeout clock)
        self._flip_wait: dict[str, int] = {}

    def on_bars(self, bars: list[Bar], *, tape_net: float = 0.0,
                window_price_delta: float = 0.0, in_rth: bool = True, now_ms: int | None = None,
                cap: dict | None = None, book: dict | None = None) -> None:
        # ★2026-08-15 `book` added for the MGC level-break gates. Defaults to None, and every gate
        # that needs it FAILS CLOSED without one — so the MNQ path is untouched by construction.
        f = compute_features(bars)
        self._book = book
        ts = bars[-1].ts
        now_ms = now_ms if now_ms is not None else ts * 1000  # wall-clock for the entry delay
        cap = cap or {}
        for v in self._variants:
            self._step(v, f, ts, tape_net, window_price_delta, in_rth, now_ms, cap, bars)

    def _publish_open(self) -> None:
        """Snapshot the open sim positions beside the store. FAIL-QUIET by design: this is
        observability, and it must never be able to take the shadow desk down."""
        if not self._open_path:
            return
        try:
            caps = {v.name: v.time_cap_s for v in self._variants}
            snap = {"ts": int(time.time()),
                    "open": {n: {**o, "time_cap_s": caps.get(n, 0.0),
                                 "held_s": max(0, int(time.time()) - int(o.get("entry_ts") or 0))}
                             for n, o in self._open.items()}}
            tmp = self._open_path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(snap, fh, indent=1, sort_keys=True)
            os.replace(tmp, self._open_path)
        except Exception:
            pass

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
        side = "LONG" if mom > 0 else "SHORT"

        # ★★2026-08-13 THE DRIFT-DIRECTION GATE (gated arms only).
        # Measured on the 4 days the rider has run (n=68, tick-repriced), the ungated book is
        # −$476.50 and it splits sharply:
        #   · entries BEFORE the detector confirms:  n=36  +$502.50  (+$14.00/tr)  <- the edge
        #   · the two chop days lost in BOTH directions, 15 of 16 trades stopping  <- whipsaw
        # So the fault is never "it traded too early", it is "it kept re-entering AGAINST a
        # direction the tape had already declared". A permission gate (wait for confirmation
        # before trading at all) tests WORSE than doing nothing — n=32, −$979.00 — because the
        # detector confirmed on all four days and so suppressed no losses while deleting the
        # profitable early window. Operator: "the fact it jumps in early is kind of its edge."
        # Hence the asymmetry: unguarded before confirmation, direction-only after.
        #   ungated  −$476.50   ->   gated  +$603.50   (+$1,080), ahead on strip-best-day all 4 ways
        # ⚠ n=68 over FOUR days and one of them is a third of the sample. This is a shadow arm to
        # settle the question forward, NOT a validated result. Its ungated twin runs alongside it
        # precisely so the gate can be attributed rather than assumed.
        if v.rider_gate_drift:
            read = self._rider_drift(bars, ts)
            if read is not None and read.confirmed and read.direction in ("UP", "DOWN"):
                if side != ("LONG" if read.direction == "UP" else "SHORT"):
                    return None
            # read is None / not yet confirmed -> DELIBERATELY unguarded. Do not "fail closed" here:
            # failing closed would silently recreate the permission gate that tested worse.

        return Entry(side=side, gate="clock_rider",
                     target_r=v.target_r, stop_atr_mult=v.stop_atr_mult)

    @staticmethod
    def _rider_drift(bars: list, ts: int):
        """drift.py's real detector, fed the session's minute bars up to `ts`. Returns None on any
        doubt (too little tape, a bad read) so the caller leaves the entry unguarded.

        ★ CALLS THE REAL DETECTOR rather than re-deriving it. A hand-rolled version of this that
        omitted MIN_BARS=9 once fabricated a +$819 counterfactual on this desk. And note it must be
        `compute()` on a BOUNDED window, never `drift.read()`: read() selects `bar_ts >= open` with
        no upper bound, so replaying it at a past instant silently reads forward to now.
        """
        try:
            from .drift import OPEN_UTC_MIN, compute
            open_s = (ts // 86400) * 86400 + OPEN_UTC_MIN * 60
            rows = [(b.ts, b.high, b.low, b.close) for b in bars if open_s <= b.ts < ts]
            if not rows:
                return None
            r = compute(rows)
            return r if r.ok else None
        except Exception:
            return None

    def _entry(self, v: ShadowVariant, f: Features, tape_net: float, in_rth: bool, cap: dict,
               bars: list[Bar] | None = None, ts: int = 0):
        # ★2026-08-15 THE COOLDOWN, CENTRAL AND BEFORE ANY DISPATCH. Two gates shipped without the
        # one their backtest ran under (level_break: 45min; board/rider_w5: 15min), each time
        # because the pure gate function has no such kwarg so passing it would raise. Handling it
        # here means a variant declares `cooldown_min` in params and it is simply enforced — the
        # gate never sees it, and the next gate to need one cannot forget.
        _cd = v.params.get("cooldown_min")
        if _cd:
            _until = self._cool_until.get(v.name)
            _now = bars[-1].ts if bars else (ts or 0)
            if _until is not None and _now < _until:
                return None
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
        elif v.gate == "level_break":
            # ★★★2026-08-15 AUDIT FIX #3 — DECIDE ONCE PER BAR, NOT ONCE PER SECOND.
            # on_bars re-runs on every T_TAPE message (1/s), re-evaluating the SAME newest completed
            # bar ~60 times. The break condition is a property of that bar and cannot change during
            # the minute — only the BOOK does. So the effective rule became "was the far side empty
            # at ANY second while this bar was newest?" instead of the research's "was it empty at
            # the bar's close?". Measured on real depth: 85.9% of breaks admitted vs the research's
            # 47.1% — 1.82x the population, and the book cut IS the gate.
            # It also created a look-ahead: the sim stamps entry at the bar label and the repricer
            # fills at label+60s, so a decision taken 55s later was booked at a price from before it.
            # Latching on the bar timestamp makes the decision instant and the fill instant the same.
            _last = self._lb_seen.get(v.name)
            if bars and _last == bars[-1].ts:
                return None
            if bars:
                self._lb_seen[v.name] = bars[-1].ts

            # ★2026-08-15 MGC gold. Needs BARS (for the rolling level) and the BOOK, neither of
            # which is on Features. gate_level_break returns None without a book — the book
            # condition IS the gate, and without it this is the plain extension trigger, which
            # loses -$3.60 to -$5.49/trade in every cell at gold's true cost.
            bb = bars or []
            side = gate_level_break(
                [b.high for b in bb], [b.low for b in bb], [b.close for b in bb],
                f.atr, getattr(self, "_book", None),
                **{k: x for k, x in v.params.items() if k != "cooldown_min"}) if len(bb) >= 2 else None
            e = Entry(side=side, gate="level_break") if side else None
        elif v.gate == "board":
            # ★2026-08-15 the pooled sat-out run-catcher. The clock comes from `ts`, not Features —
            # Features carries no hour, and gate_board fails CLOSED without one.
            e = gate_board(f, utc_hour=(ts % 86400) / 3600.0,
                           **{k: x for k, x in v.params.items() if k != "cooldown_min"})
        else:
            e = None
        if e is not None and v.side and e.side != v.side:
            return None   # side-constrained variant (e.g. thrust_short) — drop the wrong direction
        if e is not None and v.atr_max and f.atr >= v.atr_max:
            return None   # regime-restricted variant (the clip A/B runs only where the clip is live)
        # ★2026-08-16 BUILD #15 — the flip TIMEOUT, which only this sim can supply.
        # A climax with require_flip=True and no flip returns None from the gate. We remember when
        # that pairing was FIRST seen and, once it has stood for flip_timeout_s, admit the entry
        # anyway. The latch clears the moment the climax stops holding, so a fresh flush starts a
        # fresh clock — otherwise an old, unrelated climax would authorise a much later entry.
        if e is None and v.flip_timeout_s and v.gate == "capitulation" and ts:
            # ⚠ mirror the real dispatch EXACTLY — `cap` is keyed sell/buy/base/dpx/flip, not by
            # the gate's parameter names, and the gate takes `f` positionally. My first version
            # splatted `cap` straight in, which would have raised on every capitulation tick.
            loose = gate_capitulation(
                f, cap_sell=cap.get("sell", 0.0), cap_buy=cap.get("buy", 0.0),
                cap_base=cap.get("base", 0.0), cap_dpx=cap.get("dpx", 0.0),
                cap_flip=cap.get("flip", False),
                **{k: x for k, x in v.params.items() if k != "require_flip"}) if cap else None
            if loose is not None:
                first = self._flip_wait.setdefault(v.name, ts)
                if ts - first >= v.flip_timeout_s:
                    self._flip_wait.pop(v.name, None)
                    e = loose
            else:
                self._flip_wait.pop(v.name, None)
        elif v.flip_timeout_s:
            self._flip_wait.pop(v.name, None)

        # ★2026-08-16 BUILD #13 — the ER band. Computed only when a variant asks for one, so this
        # costs nothing for the 20-odd arms that do not. Uses the SAME ER30 the rung classifier does.
        if e is not None and (v.er_min or v.er_max):
            from .sizing import efficiency_ratio      # local: shadow.py does not import it globally
            er = efficiency_ratio(bars, 30) if bars else 0.0
            if v.er_min and er < v.er_min:
                return None
            if v.er_max and er >= v.er_max:
                return None
        return e

    def _absorbed(self, v, side, tape_net, wpd) -> bool:
        return exit_absorption(Position(side, 0.0, 0.0, 0.0), tape_net=tape_net,
                               window_price_delta=wpd, flow_min=v.absorption_flow_min) is not None

    def _open_pos(self, v, entry, f, ts, bars=None) -> None:
        # ★2026-08-16 BUILD #16 — stamp the IGNITION at entry, not at exit. Whether the move began as
        # a range break is a fact about the moment we entered; recomputing it later would read a
        # different 2h window and could flip the answer mid-trade.
        brk = _brk_2h(bars, f.price) if (bars and v.clip_standdown_on_brk) else False
        self._open[v.name] = dict(side=entry.side, entry_price=f.price, entry_atr=f.atr,
                                  entry_ts=ts, peak=0.0, brk=brk)
        self._publish_open()

    def _step(self, v, f, ts, tape_net, wpd, in_rth, now_ms, cap, bars=None):
        op = self._open.get(v.name)
        if op is None:
            if v.confirm_s <= 0:  # immediate entry (the default / live control)
                entry = self._entry(v, f, tape_net, in_rth, cap, bars, ts)
                if entry is not None:
                    self._open_pos(v, entry, f, ts, bars)
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
                self._open_pos(v, entry, f, ts, bars)
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
            # ★2026-08-15 (audit #13) THE ARM THRESHOLD. gf_MGC's exit does not trail at all until
            # the peak has reached chand_arm_k x ATR; exit_chandelier_lock would otherwise start
            # trailing the moment the peak clears the give-back. Default 0.0 = arm immediately, so
            # every MNQ variant behaves exactly as before.
            armed = (v.chand_arm_k <= 0.0
                     or (op["entry_atr"] > 0
                         and op["peak"] / op["entry_atr"] >= v.chand_arm_k))
            fired = armed and (exit_chandelier_lock(pos, f.price, start_k=v.chand_start_k,
                                                    lock_r=v.lock_r, lock_k=v.lock_k) if v.chand_lock
                               else exit_chandelier(pos, f.price, start_k=v.chand_start_k,
                                                    min_k=0.5, tighten=v.chand_tighten))
            reason = "CHANDELIER" if fired else exit_scalp(
                pos, f.price, target_r=99.0, stop_atr_mult=v.stop_atr_mult)  # target off; STOP only
        else:
            reason = exit_scalp(pos, f.price,
                                target_r=_eff_target_r(v, op["entry_atr"], self._vpp,
                                                       brk=bool(op.get("brk"))),
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
            self._publish_open()

    def _record_target_r(self, v, atr):
        """What to persist as target_r so the TICK REPRICER reproduces this sim's own target.
        The repricer replays from (target_r, stop_atr_mult) using the same coupled formula, so it must
        receive the EFFECTIVE value — persisting the nominal one would reprice a decoupled variant
        against a target 2x too far away and quietly convert its winners into max-holds."""
        if v.chandelier:
            return 0.0            # 0 = repricer replays the chandelier
        return _eff_target_r(v, atr, self._vpp)

    def _record(self, v, op, exit_price, exit_ts, reason):
        # ★2026-08-15 start the cooldown at the EXIT, matching both research engines.
        _cd = v.params.get("cooldown_min")
        if _cd:
            self._cool_until[v.name] = float(exit_ts) + float(_cd) * 60.0
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
MGC_EXIT = dict(stop_atr_mult=3.0, chandelier=True, chand_lock=True,
                chand_start_k=2.0, chand_arm_k=2.0, lock_r=99.0, lock_k=2.0,
                time_cap_s=480 * 60)
# ★★ THE EXIT IS THE FINDING, not a default. All four gold cells want a WIDE CHANDELIER and a
# SINGLE LOT: the tight scalp is NEGATIVE on both survivors at 1R, the dual slot has Lot A cancel
# Lot B, and a time cap's headline is a long-drift artefact. This is the OPPOSITE of the live MNQ
# slot configuration, and it is the most actionable structural result in the gold work.
# lock_r=99.0 disables the profit lock deliberately — it must never tighten this trail.


def mgc_slate() -> list[ShadowVariant]:
    """The MGC gold book. SHADOW ONLY — never promoted, never routed, never in gate_switches.env.

    ★ Runs in its OWN service instance against its OWN store (data/shadow_mgc.db). That is not
    tidiness: `reprice_pending()` reprices every unprocessed trade with ONE value_per_point, so two
    services sharing a store would price gold at MNQ's $2 instead of $10 — and the fee at $1.50
    instead of $7.50 — depending on which called first. A RACE, silent, and 5x wrong.
    """
    return [
        # ★★2026-08-15 (audit #12) THE CONTROL ARM, which the spec ships and I had omitted:
        # gf_MGC.md — "without it the book cut cannot be attributed, and attributing a filter to
        # itself is how the router-filtered gold attack fooled us in August." Same trigger, same
        # exit, NO book condition. If the two hole arms do not beat this one, the book is decorative
        # and the whole thesis is wrong. It is also the arm that would have exposed the 1.82x
        # over-admission the audit found in #3.
        ShadowVariant("mgc_break_fade_nobook", "level_break", symbol="MGC", side="",
                      params={"look_min": 60, "margin_atr": 0.10, "fade": True,
                              "book_band_pt": 1.0, "require_book": False,
                              "cooldown_min": 45}, **MGC_EXIT),
        ShadowVariant("mgc_holebreak_fade_long", "level_break", symbol="MGC", side="LONG",
                      params={"look_min": 60, "margin_atr": 0.10, "fade": True,
                              "book_band_pt": 1.0, "obstacle_max": 0,
                              # ★ EXPLICIT, never a default. The research (gf_mgc_cells, cool=45)
                              # and every ShadowVariant line in gf_MGC.md §10.2 carry this. A
                              # silent default is precisely how it went missing the first time,
                              # and it is worth $12.47/trade against $2.67 without it.
                              "cooldown_min": 45}, **MGC_EXIT),
        ShadowVariant("mgc_holebreak_fade_short", "level_break", symbol="MGC", side="SHORT",
                      params={"look_min": 60, "margin_atr": 0.10, "fade": True,
                              "book_band_pt": 1.0, "obstacle_max": 0,
                              # ★ EXPLICIT, never a default. The research (gf_mgc_cells, cool=45)
                              # and every ShadowVariant line in gf_MGC.md §10.2 carry this. A
                              # silent default is precisely how it went missing the first time,
                              # and it is worth $12.47/trade against $2.67 without it.
                              "cooldown_min": 45}, **MGC_EXIT),
    ]


# ════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★2026-08-15 THE TRIM — 47 arms -> 20. Operator: "there are tons of shadow sims that lose all the
# time. trim the shadow desk down to the best 20 first. kill the rest."
#
# Definitions stay in source and are filtered out at the end of default_slate() alongside RETIRED:
# registry numbers are permanent, a retired sim keeps its number, and the history stays in shadow.db.
# Re-arming one is deleting a line from this dict.
#
# ⚠⚠ THIS IS NOT A P&L SORT AND MUST NEVER BECOME ONE. The PROTECTED list above this one exists
# because the biggest losers are often CONTROLS doing their job:
#   · capit_loose (-$11,292, the worst number on the desk) is the NO-FLIP CONTROL. It is supposed to
#     lose — it is the evidence that require_flip=True is worth having. Killing it would delete the
#     justification for a LIVE config while leaving the config in place.
#   · thrust_loose (-$43 on n=611) is the un-vetoed BASE the abs_veto +$2,537.50 claim is measured
#     against, and is HARD-CODED in three shipped scripts, which would break.
#   · chand_k35 IS the live desk exit · thrust_short_raw is the raw arm proving the 55s filter adds
#     +$11.20/trade · rg_long_fast_v is the only long-reversion coverage left · abs_veto_60s is the
#     upper flank proving 55s is a peak and not a floor · capit_live_mirror is the counterfactual for
#     a live gate.
# That is EIGHT of the twenty slots spent on arms that are not trying to win. It is the right spend:
# an experiment with no control is an anecdote.
#
# ⚠ AND THIN n IS NOT EVIDENCE. The odr (Open Rider) arms fire about once a day, so small n is
# expected rather than damning. They are cut on a REASON — s30 beats s20 on all four paired
# comparisons — never on sample size.
# ════════════════════════════════════════════════════════════════════════════════════════════════
RETIRED_2026_08_15: dict[str, str] = {
    # ── ANSWERED, and the answer is "this loses". Unprotected, large n, clearly negative. ───────
    "grind_fast":   "n=1,407 at -$1.23/trade — the largest sample on the desk says no edge",
    "thrust_aligned": "n=349 at +$1.01 — inside noise, and thrust_cont dominates it on the same tape",
    # ── capit_mid / capit_ride: the 08-02 note kept them because their disqualifying reason had
    #    evaporated (the roster re-adopted require_flip). That made them VALID tests, not winning
    #    ones. They have since reached n=40 and both read about -$12.50/trade. The test ran and
    #    returned an answer, so now they retire — on the result, not on the old objection.
    "capit_mid":  "n=41 at -$12.74; the test the 08-02 note preserved has now returned its answer",
    "capit_ride": "n=40 at -$12.49; same",
    # ── THE WHOLE rgv-SHORT FAMILY, control included. flow50 +$168, raw -$4, flow25 -$24 on n=52-67:
    #    every arm sits inside noise, so there is nothing left for the control to control. Retiring
    #    the family and keeping its baseline would be the expensive half of the trade.
    "rg_short_025_flow50": "family answered: all three arms inside noise on n=52-67",
    "rg_short_025_flow25": "family answered",
    "rg_short_025_raw":    "the family's CONTROL — retired WITH its family, never on its own",
    # ── ANSWERED AS AN EXPERIMENT: stop width does not rescue grind. Six rungs, n=54-227, every one
    #    negative. The question the family was built to ask has an answer. It is NOT retired for
    #    "grind loses" — these hold ext_hi=2.0 deliberately to freeze the entry population.
    "sw_grind_A_k10": "stop-width on grind: answered — every rung negative",
    "sw_grind_A_k20": "stop-width on grind: answered — every rung negative",
    "sw_grind_A_k30": "stop-width on grind: answered — every rung negative",
    "sw_grind_B_k10": "stop-width on grind: answered — every rung negative",
    "sw_grind_B_k20": "stop-width on grind: answered — every rung negative",
    "sw_grind_B_k30": "stop-width on grind: answered — every rung negative",
    # ── STALLED, not answered: n=36-40 after weeks, spread +$184 to -$40. abs_veto's LONG side does
    #    not fire often enough to settle this. The SHORT quartet asks the same question, fires as
    #    often and is strongly positive, so it is kept and this one is dropped as a duplicate.
    "sw_absL_A_k10": "abs_veto LONG side too slow to settle; the short quartet answers the same question",
    "sw_absL_A_k20": "abs_veto LONG side too slow to settle",
    "sw_absL_B_k10": "abs_veto LONG side too slow to settle",
    "sw_absL_B_k20": "abs_veto LONG side too slow to settle",
    # ── CLIP PAIRS, cut TOGETHER — half an A/B is not a result. ─────────────────────────────────
    "cx_absSB_clip": "clip and live differ by $16 on n=37: the clip does nothing on this gate",
    "cx_absSB_live": "pair of cx_absSB_clip",
    "cx_absLA_clip": "n=31 at -$6.39, not accumulating toward a decision",
    "cx_absLA_live": "pair of cx_absLA_clip",
    # ── THE s20 AXIS IS REFUTED on four independent Open Rider pairs: s30 beats s20 every time
    #    (+263/-390, -17/-335, -79/-142, +226/-142). Cut on that pattern, not on n.
    "odr_c5_s20":    "s30 beats s20 on every paired comparison",
    "odr_c10_s20":   "s30 beats s20 on every paired comparison",
    "odr_c5_s20_g":  "s30 beats s20 on every paired comparison",
    "odr_c10_s20_g": "s30 beats s20 on every paired comparison",
    # ⚠ THE GATED s30 PAIR IS **NOT** RETIRED, and cutting it was my first answer. test_shadow's own
    #    guard refused it, correctly: "an unpaired gated arm confounds the gate with whichever cadence
    #    or stop cell it sits in". Keeping c5_s30/c10_s30 while dropping their _g twins would leave a
    #    2x2 that cannot separate the DRIFT GATE from cadence — which is the live question the
    #    operator wants answered weekly. So the family keeps a clean 2x2 (cadence x gate) at the
    #    winning stop, and the slate lands at 22 rather than 20. Two slots for a working factorial is
    #    the right trade; a broken factorial is worth zero slots.
}

def _live_rgv_short() -> dict:
    """The LIVE rgv_short entry params, read from slot_strategy so the mirror cannot drift.

    Falls back to an empty dict on any import failure, which makes the mirror fire on the gate's own
    defaults rather than silently mirroring something that is not live — and a fallback that changed
    behaviour without saying so is the failure this whole file keeps meeting.
    """
    try:
        from .slot_strategy import _RGV_SHORT
        return dict(_RGV_SHORT)
    except Exception:
        log.warning("rgv_short_live_mirror: could not read _RGV_SHORT — mirroring gate defaults")
        return {}


def _live_rgv_short_exit() -> tuple[float, float]:
    """(target_r, stop_atr_mult) of the LIVE rgv_short LOT A, resolved from the slate.

    ★ RESOLVED, never read from the SlotSpec literal. The source says target_r=2.0; scaleout_slots()
    returns rgv_short_A at 1.5R (and a chandelier B at 2.0). Reading source here would have shadowed
    an exit the desk does not run — [[a-slate-is-assembled-from-helpers]].
    """
    try:
        from .slot_strategy import scaleout_slots
        a = [s for s in scaleout_slots() if s.tag == "rgv_short_A"]
        if a:
            return float(a[0].target_r), float(a[0].stop_atr_mult)
    except Exception:
        log.warning("rgv_short_live_mirror: could not resolve the live exit — using 1.5R/1.0xATR")
    return 1.5, 1.0


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
        # ★★★2026-08-18 THE BENCH ON rgv_short IS NOW PRICED. Operator: "why doesnt router arm rgv
        # short on days like today". It has been off since a STANDING 07-31 VERDICT — "benched for
        # the week, verdicted SHADOW (11 fires, -$142, negative at every exit rung)" — which the
        # router still quotes on every tick eighteen days later. But the rg_short_* twins were all
        # retired in RETIRED_2026_08_15, so the gate could neither trade nor be shadowed: no live
        # evidence, no counterfactual, and an n=11 verdict frozen in place.
        # That is a lead in none of the four permitted states — [[never-kill-a-lead-that-has-a-glimmer]]
        # says every lead ends LIVE / SHADOW / PARKED / REFUTED, and "benched with nothing watching"
        # is not one of them. This is the SHADOW state, and it costs nothing: it places no orders.
        # ★ PARAMS ARE IMPORTED FROM THE LIVE SLATE, NEVER COPIED. A mirror that duplicates the dict
        # by hand stops being a mirror the moment the live gate is retuned — the same two-surfaces
        # drift that just put the wrong sim number on the dashboard. Exit matches live too
        # (scalp, target_r 2.0, stop 1.0xATR), so a divergence can only come from the BENCH.
        # ⚠ MIRRORS LOT A ONLY, and the number is 1.5R not 2.0R. I first wrote 2.0 by reading
        # SlotSpec("rgv_short", ... target_r=2.0) in SOURCE — but the live slate RESOLVES to
        # rgv_short_A scalp 1.5R + rgv_short_B chandelier 2.0. That is CLAUDE.md trap #3 verbatim
        # ("verify via scaleout_slots(), NEVER source"), and only the assertion caught it.
        # Lot B is a chandelier ride and is NOT mirrored, so this arm is the SCALP LEG's
        # counterfactual — never read it as the whole gate's P&L.
        ShadowVariant("rgv_short_live_mirror", "reversal_grab",
                      {"side": "SHORT", **_live_rgv_short()},
                      target_r=_live_rgv_short_exit()[0], stop_atr_mult=_live_rgv_short_exit()[1]),
    ]
    slate += _stop_width_ab()
    slate += _clip_ab()
    slate += _open_rider()
    # ── GF RIDER (2026-08-15, operator: "shadow arm rider_w5") ────────────────────────────────
    # The pooled sat-out run-catcher. This is LEG 3 of the lab's slate — the one that ships with no
    # new feature, because it reads the existing net_atr_5. Legs 1-2 (rider_all / rider_open) need a
    # `net_atr_10` on Features and are NOT armed here.
    #   backtest: +$4,841, $19.29/tr — half the headline edge, but it was the ONE leg that was GREEN
    #   in the census week itself (+$340).
    # ★ FLOORS DELIBERATELY OFF (rvol_min / atr_pr_min absent). They help w=10 and HURT w=5
    #   ($4,841 -> $2,833). They are not a general truth and must not be copied across.
    # ★ stop 3.0xATR is WIDE ON PURPOSE: the median adverse excursion is 3.00R by design, and 129 of
    #   256 trades stop out. That IS the strategy — do not bench it on a wall of stops.
    # ★ chandelier=False: every chandelier variant tested RED. Do not add one.
    slate.append(
        ShadowVariant("rider_w5", "board",
                      # ★2026-08-15 cooldown_min=15 RESTORED. gf_rider_engine.run_trades ran one
                      # position at a time with a 15-minute cooldown after every exit — that is why
                      # 337 signals a session become ~6 trades, and every number quoted for this leg
                      # (+$4,841, $19.29/tr) came from the constrained version.
                      # ⚠ CONFIG BOUNDARY: this arm ran UNCAPPED 2026-08-17 13:25 → 08-18 17:49.
                      # Its first 10 trades are FAITHFUL (all closed <=60min, so the cap never bound)
                      # but their FREQUENCY is censored — a slow trade blocks the session and is not
                      # recorded until it closes, and one entry was lost to the deploy restart. Count
                      # toward the promotion bar from 08-18 17:49. See SESSIONS.md.
                      # ★★★2026-08-18 time_cap_s=120min RESTORED — the SECOND constraint this arm
                      # shipped without. The report's spec is "stop 3.0xATR, target 6.0xATR, 120min"
                      # and gf_rider_engine caps every race at `cap_min` (i1 = min(n, i0 + cap_min*12)),
                      # but the variant carried time_cap_s=0.0, i.e. NO CLOCK. With a 3xATR stop and a
                      # 6xATR target and one position at a time, an uncapped trade holds until one of
                      # them prints and blocks re-entry for the whole session: on 08-18 the gate was
                      # TRUE on 32 minutes and produced ONE trade, against nine on 08-17 when every
                      # hold happened to close inside an hour. Exactly the cooldown defect again —
                      # "every number quoted for this leg came from the CONSTRAINED version".
                      {"k": 2.0, "w": 5, "hh_lo": 13.0, "hh_hi": 20.0, "cooldown_min": 15},
                      symbol="MNQ", qty=1.0, stop_atr_mult=3.0, target_r=2.0,
                      adverse_cut_atr=3.0, chandelier=False, time_cap_s=120 * 60))

    # ★2026-08-15 the trim rides alongside the older RETIRED set — see RETIRED_2026_08_15.
    return [v for v in slate
            if v.name not in RETIRED and v.name not in RETIRED_2026_08_15]


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
    # ★2026-08-16 the window is now set EXPLICITLY here rather than inherited from a dataclass
    # default that every non-rider variant also carried. Same values, same behaviour — but the
    # 14:45 cut is now stated where the arms that read it are defined.
    common = dict(gate="clock_rider", params={}, target_r=2.0, time_cap_s=45 * 60,
                  rider_lookback_min=15, adverse_cut_atr=99.0, absorption_flow_min=1e9,
                  rider_win_start_s=RIDER_WIN_START_S, rider_win_end_s=RIDER_WIN_END_S)
    return [
        ShadowVariant("odr_c5_s20", rider_cadence_min=5, stop_atr_mult=2.0, **common),
        ShadowVariant("odr_c5_s30", rider_cadence_min=5, stop_atr_mult=3.0, **common),
        ShadowVariant("odr_c10_s20", rider_cadence_min=10, stop_atr_mult=2.0, **common),
        ShadowVariant("odr_c10_s30", rider_cadence_min=10, stop_atr_mult=3.0, **common),
        # ★★2026-08-13 THE DRIFT-GATED HALF — an EXACT PAIR for each cell above, differing in one
        # bit (rider_gate_drift). Paired on purpose: the backtest cannot rank cadence or stop width
        # (per-trade SD ~$160 makes every cell difference noise), so an unpaired gated arm would
        # confound the gate with whichever cell it happened to sit in. Four extra arms is real slate
        # cost — the slate was cut 28->18 on 08-02 — but attribution is the entire point of running
        # this forward instead of just believing the backtest.
        # The gate itself and its evidence are documented at _rider_entry. Headline: ungated
        # −$476.50 -> gated +$603.50 on the same 68 trades, ahead on strip-best-day all four ways,
        # and it takes NOTHING off the one trending day (the detector agreed with the tape).
        ShadowVariant("odr_c5_s20_g", rider_cadence_min=5, stop_atr_mult=2.0,
                      rider_gate_drift=True, **common),
        ShadowVariant("odr_c5_s30_g", rider_cadence_min=5, stop_atr_mult=3.0,
                      rider_gate_drift=True, **common),
        ShadowVariant("odr_c10_s20_g", rider_cadence_min=10, stop_atr_mult=2.0,
                      rider_gate_drift=True, **common),
        ShadowVariant("odr_c10_s30_g", rider_cadence_min=10, stop_atr_mult=3.0,
                      rider_gate_drift=True, **common),
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
        # ★★2026-08-16 SATURDAY #4 — the counter-move veto, as a SHADOW PAIR.
        # "The mechanism that does work, and it is a veto" (Part 2.5 Part B): refuse a grind LONG
        # when the last 30 minutes have fallen more than 1x ATR. `vwap_slope_atr` is a 60-bar
        # measure and LAGS, so the gate reads "established up-trend" while the last half hour slides.
        # ⚠ IT SHIPS WITH ITS OWN CONTROL. cx_grindA_live is the identical arm WITHOUT the veto and
        # already runs beside it, so the veto's effect is ATTRIBUTABLE rather than assumed — the
        # rule that the gold work had to learn twice. Do NOT retire one without the other.
        # Live grind_long is UNCHANGED (counter_veto_atr defaults to None).
        # ⚠ NAMED cx_ DELIBERATELY. It shares `base` with cx_grindA_live — same atr_max=22 regime
        # restriction, same decoupling — because a control is only a control if it differs in
        # exactly ONE thing. Two slate invariants ("only sw_/cx_ may decouple", "only cx_ may be
        # regime-restricted") caught this when it was called grind_long_cveto, and they were right:
        # the name implied a plain grind arm while the config was a clip-family one.
        ShadowVariant("cx_grindA_cveto", "grind", GRIND | {"counter_veto_atr": 1.0},
                      side="LONG", target_r=2.5, **base),
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
    # ⚠★2026-08-08 GRIND HERE IS DELIBERATELY FROZEN AND NO LONGER MIRRORS LIVE.
    # SATURDAY #2 deleted `ext_hi` from the live grind gate and moved its ATR floor 10 -> 22. These
    # arms keep `ext_hi: 2.0` ON PURPOSE: this is a STOP-WIDTH experiment, and it is only readable
    # if the ENTRY population is held constant across the rungs. Changing entries mid-experiment
    # would confound the one variable being measured and would invalidate the 512 trades already
    # collected since 08-04. The cost is that `sw_grind_*` must NOT be read as "what live grind is
    # doing" — it is a fixed cohort for comparing stops. Re-baseline it (and restart the series)
    # only when the stop question is answered.
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
    # ★★2026-08-16 BUILD #12 — THE TIGHTER abs_veto_short LADDER, 1.5R/2.5R -> 1.0R/1.5R.
    # Part 2 calls this "the week's main proposal" and Rev 1's card did not carry it at all. REV2 Q3
    # then established WHY it is the ladder and not the fills: across 46 live legs the desk fills a
    # median 0.60 points BETTER than the repricer assumes (+$47.78 over the sample), so the gap that
    # motivated it is not execution — it is where the rungs sit.
    # ★ IT NEEDS NO NEW CONTROL: sw_absS_A_k10 / sw_absS_B_k10 already run the LIVE ladder at the
    # live 1.0x stop on the same entries. These two differ from those in the target ALONE, which is
    # the whole comparison. Adding a fresh pair of controls would have been two wasted slots and a
    # second population to reconcile.
    lad = dict(gate="thrust", params=THRUST, side="SHORT", confirm_s=55,
               stop_atr_mult=1.0, qty=1.0, decouple_target=True)
    out += [
        ShadowVariant("lad_absS_A_10", target_r=1.0, **lad, **_A_CLIP),
        ShadowVariant("lad_absS_B_15", target_r=1.5, **lad, **_B_CLIP),
    ]

    # ★★2026-08-16 BUILD #13 — grind_long MED-TREND rung, A 0.5R / B 1.0R.
    # The only cell of the per-rung deliverable REV2 did NOT withdraw (n=161, +$8.25/signal,
    # strip3 +$160, loo_worst +$5.52 in data/exit_overrides_proposed.json).
    # ⚠ IT RUNS ONLY IN ITS OWN RUNG. The rungs are ER30 bands (exit_ladder_lab_v2: >=0.50 BIG-TREND,
    # >=0.30 MED-TREND), so MED-TREND is [0.30, 0.50) — hence er_min/er_max. An arm carrying a rung's
    # numbers WITHOUT its band is not that rung; it is the proposal averaged over regimes it was
    # never graded in, which is how a per-regime result gets quietly converted into a blanket one.
    # ★ ITS CONTROL IS THE SAME BAND AT THE LIVE LADDER, so the rung and the ladder are not confounded.
    _rung = dict(gate="grind", params=GRIND, side="LONG", stop_atr_mult=1.0, qty=1.0,
                 decouple_target=True, er_min=0.30, er_max=0.50)
    out += [
        ShadowVariant("rung_grindA_med_05", target_r=0.5, **_rung),
        ShadowVariant("rung_grindB_med_10", target_r=1.0, **_rung),
        ShadowVariant("rung_grindA_med_live", target_r=2.5, **_rung),   # control: live Lot A, same band
    ]

    # ★★2026-08-16 BUILD #18 — bank Lot A at a FIXED +20 POINTS onside.
    # Part 1 §11 called this "the first thing I would test next week" and Rev 1's card carried nothing
    # against the week's largest diagnosed loss. REV2 measured it at +$219.50 with all 25 winners kept
    # and every fold positive — but -$45.00 once stripped of its best three, which is why it is a
    # SHADOW arm and not a deploy, and why it needs forward n rather than another pass at the same days.
    # ⚠ POINTS, DELIBERATELY. The hypothesis is that the right bank does NOT scale with volatility; an
    # R-multiple would smuggle ATR back in and test something else. Lot B is untouched by design —
    # the play is "bank A, leave B riding".
    # ★★2026-08-16 BUILD #15 — capitulation_long: require_flip OR a 90-SECOND TIMEOUT.
    # "Take the flush when buyers are slow to show, instead of waiting for a flip that never comes."
    # The live gate runs require_flip=True (the 07-25 rehab found the flip IS the edge — the loose
    # version was fading the climax itself). This does not dispute that; it asks whether the flip is
    # worth waiting for INDEFINITELY, which is a different question and the one nobody has measured.
    # ★ THE PAIR IS THE POINT: capit_flip_live is the live rule, capit_flip_t90 is the same rule with
    # a patience limit. Any difference is the timeout, because nothing else differs.
    # ★★2026-08-16 BUILD #16 — the quiet-tape clip STANDS DOWN on a range-break ignition.
    # The clip exists because quiet tape does not pay a full R-target. A range break is the one quiet
    # setup that CAN run, so clipping it may be cutting the exact move the clip was never aimed at.
    # ★ PAIRED against the clip as it runs live, differing only in the stand-down — and both carry
    # atr_max=22 so they only run where the clip is actually live. BRK is the report's own definition
    # (gf_chop_scalp §2): closes outside the PRIOR 2h high/low.
    _clipbase = dict(gate="grind", params=GRIND, side="LONG", target_r=2.5, stop_atr_mult=1.0,
                     qty=1.0, decouple_target=True, atr_max=22.0,
                     clip_atr_split=22.0, clip_a_usd=40.0)
    out += [
        ShadowVariant("cx_clip_brk_live", **_clipbase),
        ShadowVariant("cx_clip_brk_standdown", clip_standdown_on_brk=True, **_clipbase),
    ]

    _capit = dict(gate="capitulation", side="LONG", stop_atr_mult=1.0, qty=1.0, target_r=1.5)
    out += [
        ShadowVariant("capit_flip_live", params={"require_flip": True}, **_capit),
        ShadowVariant("capit_flip_t90", params={"require_flip": True}, flip_timeout_s=90, **_capit),
    ]

    _bank = dict(gate="grind", params=GRIND, side="LONG", stop_atr_mult=1.0, qty=1.0)
    out += [
        ShadowVariant("bank20_grindA", target_pt=20.0, **_bank),
        ShadowVariant("bank20_grindA_ctl", target_r=2.5, decouple_target=True, **_bank),
    ]
    # ★2026-08-08 THE k30 THIRD RUNG — grind ONLY, and only grind.
    # The 08-08 open-window read on the 512 tick-repriced trades already running here says wide
    # stops do NOT transfer as a class: in 13:00-14:45Z the house 1.0x and 2.0x are a dead heat
    # (+$30.76 vs +$30.41/tr, delta -$104, stable through strip-best-3, two days each way). It
    # splits by GATE — grind prefers wide on BOTH lots (+$72 / +$64) while abs_veto prefers tight
    # in all four cells. So the third rung goes on the one gate with a consistent preference, and
    # NOT roster-wide, which is now refuted twice.
    # ⚠ It is a rung on the SAME frozen cohort as k10/k20 (ext_hi kept — see the note above), so
    # the three are directly comparable. Two arms, no orders, no risk.
    grind_common = dict(decouple_target=True, stop_atr_mult=3.0, qty=1.0)
    out += [
        ShadowVariant("sw_grind_A_k30", "grind", GRIND, side="LONG",
                      target_r=2.5, **grind_common, **_A_CLIP),
        ShadowVariant("sw_grind_B_k30", "grind", GRIND, side="LONG",
                      chandelier=True, chand_lock=True, chand_start_k=3.5, lock_r=6.0, lock_k=0.5,
                      **grind_common),
    ]
    return out


def chandelier_params() -> dict[str, tuple[float, float, float]]:
    """{strategy name → (start_k, min_k, tighten)} for every chandelier variant, so
    the repricer replays EACH variant's OWN trail on the tick path instead of the 3.5
    default — otherwise chand_k20/k25 would be scored as if they were the live 3.5 and
    the whole A/B would be meaningless. min_k is fixed at 0.5 (the tight floor).


    ★★2026-08-15 AUDIT FIX #4 — IT REPLAYED THE WRONG EXIT FOR GOLD.
    This built from default_slate() (MNQ) only, so every MGC name missed and the repricer fell back
    to (3.5, 0.5, 0.75) — a TIGHTENING trail — while the sim ran exit_chandelier_lock at a CONSTANT
    2.0xATR. `real_pnl` is the only number this desk trusts, and it was scoring an exit the strategy
    does not use: wider than 2.0 below peak_r=2, then collapsing to 0.5xATR beyond peak_r=4. The
    report calls the wide chandelier "the most actionable structural finding in the gold work" — and
    the number that would confirm or refute it was generated under a different trail.

    ★ HOW A CONSTANT TRAIL IS EXPRESSED HERE: the repricer's width is
    max(min_k, start_k - tighten*peak_r), so tighten=0.0 with min_k == start_k is a FLAT trail at
    start_k for all peak_r — exactly what lock_r=99.0 (a lock that never engages) produces in the
    sim. No repricer change is needed; it simply has to be TOLD.
    """
    out = {v.name: (v.chand_start_k, 0.5, v.chand_tighten)
           for v in default_slate() if v.chandelier}
    for v in mgc_slate():
        if v.chandelier:
            # lock_r >= 99 means the profit lock never engages -> a constant chand_start_k trail.
            flat = v.chand_lock and v.lock_r >= 99.0
            base = ((v.chand_start_k, v.chand_start_k, 0.0) if flat
                    else (v.chand_start_k, v.lock_k, v.chand_tighten))
            # ★ 4th element = the arm threshold (audit #13). Appended rather than inserted so every
            # existing 3-tuple caller keeps working; the repricer unpacks defensively.
            out[v.name] = base + (v.chand_arm_k,) if v.chand_arm_k > 0 else base
    return out


# ── service entrypoint ────────────────────────────────────────────────────────
async def run(cfg, *, variants=None, reprice_interval_s: float = 30.0,
              max_seconds: float | None = None, depth=None, extras: bool = True) -> None:
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
                    absorption_min_loss_usd=cfg.absorption_min_loss_usd,
                    store_path=cfg.shadow_store_path)
    # the per-side direction circuit breaker (prototype) rides the same feed alongside
    # the variant slate, booking cb_thrust (governed) + cb_thrust_dropped (phantom).
    # ★2026-08-02 RETIRED — it is in RETIRED, so it no longer runs. It was falsified by its own
    # validation arm: window-matched, GOVERNED −$878.0 against the ungoverned base chand_k35 −$470.5,
    # and the phantom of the sides it stood down is +$16.5 — i.e. it vetoed the winning sides. The
    # durable router supersedes it. Revert: drop "cb_thrust" from RETIRED.
    breaker = (SessionDirectionBreaker(store, symbol=cfg.symbol,
                                       value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt)
               if (extras and "cb_thrust" not in RETIRED) else None)
    # the exhaustion-reversal footprint rides its OWN tick+book loop (not bar-based) —
    # observe-only incubation, reads capture directly, records exhaustion_rev trades.
    # ★2026-08-15 `extras=False` for the MGC instance. The breaker and the footprint shadow are
    # MNQ-specific: FootprintShadow reads capture.db's tick+book loop and capture.db has NO MGC
    # depth at all (gold's L2 only ever lands in depth.db). Running them on gold would not error —
    # they would silently record nothing, which is the failure mode this whole build guards against.
    # ★2026-08-16 THE EXHAUSTION STOP-WIDTH ARMS ride the SAME signal as exhaustion_rev, added as
    # extra exit LEGS rather than extra instances — so all three enter on an identical fill and the
    # comparison is of the exit alone. exhaustion_rev keeps its legacy 8/12pt leg untouched (it is a
    # protected control and the entry substrate for seven shipped scripts).
    # exh_w15 mirrors what went live today; exh_w20 is the candidate held back from live because the
    # grid improves monotonically to its own edge, which is what the 44% stop-leak bias produces.
    from .footprint import LEGACY_LEG, WIDE_LEGS
    footprint = (FootprintShadow(store, cfg.symbol,
                                 value_per_point=cfg.value_per_point, fee_rt=cfg.fee_rt,
                                 legs=[LEGACY_LEG, *WIDE_LEGS])
                 if extras else None)
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
                    # ★★★2026-08-18 KEY ON THE NEWEST BAR'S TIMESTAMP, NEVER ON THE BAR COUNT.
                    # `mb` is a deque(maxlen=bar_lookback) and line ~1227 WARMS it to capacity
                    # before the loop starts, so `len(mb.bars()) > _n_before` was `120 > 120` on the
                    # very first message and every one after — false FOREVER. The gold shadow could
                    # therefore never fire, and did not: 0 sims in 3 days while the same gate
                    # replayed 459 fires on the same tape. A count comparison on a FIXED-SIZE RING
                    # can only ever be true while the ring is filling, and the warm-up guarantees it
                    # never is. Same class as the 08-15 audit's "the gate could never have fired"
                    # (bar_lookback=60 vs a look_min needing 61) — in this same service, one week on.
                    _bs_before = mb.bars()
                    _ts_before = _bs_before[-1].ts if _bs_before else None
                    mb.fold(body["ts"], body["o"], body["h"], body["l"], body["c"], body["v"])
                    # ★★2026-08-15 (audit #10) DRIVE OFF OUR OWN BARS WHEN WE HAVE A BOOK.
                    # md publishes T_TAPE tagged with ITS OWN symbol (MNQ) and shadow.py never
                    # filtered it, so gold's decision clock was MNQ's tape: an MNQ-only tape outage
                    # froze the gold shadow silently while MGC bars kept arriving. When a depth feed
                    # is attached we step on OUR completed bars instead, which is also the natural
                    # cadence now that level_break decides once per bar.
                    _bs = mb.bars()
                    if depth is not None and _bs and _bs[-1].ts != _ts_before:
                        if len(_bs) >= 6:
                            _t = _bs[-1].ts * 1000
                            sim.on_bars(_bs, now_ms=_t, in_rth=True,
                                        book=depth.book_at(_t))
                elif topic == T_TAPE:
                    now_ms = body.get("ts_ms")
                    bars = mb.bars()
                    if len(bars) >= 6:
                        capft = capitulation_tape(cap, cfg.symbol, now_ms) if now_ms else {}
                        # ★2026-08-15 the book, for the MGC level-break gates. None on the MNQ
                        # instance (depth=None); every gate needing it then fails closed.
                        if depth is not None:
                            continue          # gold steps on its own bars above, not on MNQ's tape
                        bk = None
                        sim.on_bars(bars, tape_net=body.get("net_flow", 0.0),
                                    window_price_delta=body.get("win_price_delta", 0.0),
                                    in_rth=body.get("in_rth", True), now_ms=now_ms, cap=capft,
                                    book=bk)
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
                            footprint and footprint.on_cycle(cap, now_ms)   # observe-only; must never break the loop
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
