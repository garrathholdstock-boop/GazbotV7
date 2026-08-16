"""GAZBOT V7 — per-slot decisions for the multi-position paper tournament.

Each SLOT is one (gate, direction). grind-LONG and grind-SHORT are two *independent*
slots: the long slot opens only on a grind LONG signal, the short slot only on a grind
SHORT — so we can score the two directions separately (the operator's musing: grind
long earns its keep, grind short may not). A slot opens when its gate fires ITS
direction and the slot is flat, then manages its OWN exit stack (chandelier/2R +
give-back) independently of every other slot.

Pure decision half: reads each slot's position from the ``SlotBook``, emits per-slot
OPEN/CLOSE intents (each tagged with its slot). Reuses the single-position deciders +
sizing, applied per slot. The native 1-ATR loss stop is a server-side order armed by
the execution half — this layer owns only the *profit/managed* exits (same split as
the single-position ``strategy._manage``). Clean-room.
"""

from __future__ import annotations

import json
import os

from dataclasses import dataclass, field, replace

from .deciders import (
    NIPC_ER15_BARS,
    NIPC_FLAT_BY_S,
    NIPC_HOLD_CAP_S,
    NipcTracker,
    Position,
    _atr,
    chandelier_start_k,
    exit_chandelier,
    exit_chandelier_lock,
    exit_fixed,
    exit_giveback,
    exit_scalp,
    gate_capitulation,
    gate_grind,
    gate_reversal_grab,
    gate_thrust,
)
from .footprint import exhaustion_signal
from .sizing import conviction_lots, efficiency_ratio


@dataclass
class SlotSpec:
    tag: str                               # slot id / gate label ("grind_long")
    kind: str                              # "grind" | "reversal_grab" | "thrust"
    side: str                              # "LONG" | "SHORT" — the ONLY direction this slot takes
    params: dict = field(default_factory=dict)
    sizing: str = "flat"                   # "flat" (base_size) | "conviction" (0..base by ER)
    base_size: int = 1
    exit: str = "chandelier"               # "chandelier" | "chandelier_lock" | "scalp" | "fixed"
    target_r: float = 2.0
    stop_atr_mult: float = 1.0
    fixed_stop_pt: float = 0.0             # exit="fixed": POINT stop/target (ATR-independent snap-back fade)
    fixed_target_pt: float = 0.0
    vol_adaptive_chandelier: bool = True
    chandelier_start_k: float = 3.5
    chandelier_min_k: float = 0.5
    chandelier_tighten: float = 0.75
    lock_r: float = 0.0                    # exit="chandelier_lock": hold start_k trail until peak_r>=lock_r, then step-lock to lock_k
    lock_k: float = 0.0
    giveback_enabled: bool = True
    giveback_arm_usd: float = 50.0
    giveback_usd: float = 40.0
    risk_budget_usd: float = 80.0
    adaptive_exit: bool = False            # regime-3-exit selector: pick exit WIDTH by regime-at-entry
                                           # (aligned-trend→WIDE lock-chandelier, chop→TIGHT k1.5, counter→k2.0).
                                           # Validated regime-only, +$756 OOS/6-of-7d (exit_selector_sweep.py).
                                           # Overrides `exit` when True. Revert: set False (falls back to `exit`).
    veto_counter_regime: bool = False      # ★2026-07-28 (operator): SKIP the OPEN when regime-at-entry is
                                           # COUNTER (_regime_mode=='mid' — a fade fired against a local trend).
                                           # exhaustion_short bled −$190/56tr shorting INTO up-trends (225-tr shadow
                                           # reprice); the router's DAY-path UP_OFF misses these (0 fires, see
                                           # memory router-exhaustion-short-null) so the cut is at ENTRY on the
                                           # LOCAL regime the selector already reads. Revert: set False.
    max_hold_s: float = 0.0                # ★2026-08-01 (NIPC): per-slot HARD time cap in seconds, 0 = none
                                           # (the global cfg.max_hold_minutes stays the outer backstop). NIPC's
                                           # rule 5 is a 20-min cap — mean hold in the lab was 2.4 min, so this
                                           # is a tail-cutter, not a normal exit path.
    flat_by_utc_s: float = 0.0             # ★2026-08-01 (NIPC): seconds-of-day UTC by which this slot must be
                                           # flat (NIPC = 15:30 UTC), 0 = none. Session-end flatten still applies.
    # ★2026-08-02 QUIET-TAPE CLIP — the exit split. 0/"" = OFF, so every gate without it is byte-identical
    # to before. When entry ATR < atr_split the slot uses the `lo_*` exit for the life of the position
    # (frozen at entry, never re-evaluated mid-trade); at or above it, the normal exit stack runs unchanged.
    # Evidence (live fills, 250ms ticks, fee $1.50/RT, strip-best-3 + leave-one-day-out on every cell):
    #   QUIET 22:00-13:30 (n=97, median ATR 17.4pt) — a fixed $40 clip nets +$360, holds at +$244 stripped
    #     and +$25 on its WORST leave-one-day-out fold, top trade only 11% of net. The WIDE lock-chandelier
    #     is -$538 and degrades to -$1,232 stripped; as-traded was -$354.
    #   US 13:30-22:00 (n=144, median ATR 28.4pt) — the opposite: 3.5R nets +$2,022 (+$1,019 stripped,
    #     +$645 LODO-worst) and wide +$2,611 (+$964 / +$416). A $40 clip there FAILS LODO at -$232.
    # So the tape decides, and ATR is the mechanism (a trail needs room; on a 17pt ATR there is none).
    # Keyed on ATR rather than the clock deliberately: a dead US afternoon should clip and a violent
    # overnight should ride, and an ATR rule gets both right where a clock rule gets both wrong.
    # Lot A takes a DOLLAR clip, not an R: a fixed $ auto-tightens as ATR rises within the quiet window,
    # and it beat every R cell there (1.0R -$32, 1.25R -$18 — both fail stripped).
    atr_split: float = 0.0                 # entry ATR (pt) below which the lo_* exit applies. 0 = off.
    lo_target_usd: float = 0.0             # Lot A: bank at this $ of open profit (per the slot's own qty)
    lo_target_r: float = 0.0               # Lot B: bank at this R instead — a fixed clip, NOT a chandelier,
                                           # because the trail is precisely what hands the money back here
    lo_floor_usd: float = 0.0              # ★ Lot B DOLLAR FLOOR — takes max(lo_target_r*ATR, this).
                                           # Without it the two lots INVERT on very quiet tape: Lot A is a
                                           # fixed $40 (=20pt) while Lot B is 1.75R, and 1.75R < 20pt for any
                                           # ATR below 11.4 — so the runner would bank BEFORE the scalp and
                                           # the scale-out is upside down. ATR<11 is ~17% of MNQ minute bars,
                                           # so this is a live case, not a corner. Floor keeps B strictly the
                                           # wider leg at every ATR while still scaling up when there is room.


def grind_long_short_slots() -> list[SlotSpec]:
    """The first tournament pairing: grind-long vs grind-short as separate slots."""
    p = {"slope_min": 0.4, "fast_slope": True}
    return [
        SlotSpec("grind_long", "grind", "LONG", params=p, sizing="conviction", base_size=2),
        SlotSpec("grind_short", "grind", "SHORT", params=p, sizing="conviction", base_size=2),
    ]


_RGV_SHORT = {"ext_min": 1.5, "turn_atr": 0.25, "flow_min": None, "atr_min": 20.0,
              "fast_slope": False, "fast_turn": False}  # ★2026-07-25 rehab: fast_turn fired on NOISE
              # (live −$3,543 → +$778); ATR floor 13→20. Own per-side dict (rgv_long researched separately).


_RGV_LONG = {"ext_min": 3.0, "turn_atr": 0.50, "flow_min": 50.0, "atr_min": 13.0,
             "fast_slope": True, "fast_turn": False, "net30_floor": -125.0}  # ★2026-07-25 rehab base-A
             # + the in-gate net30-depth floor (skip deep down-legs = falling knives). Router-UNMANAGED.


def tournament_slots() -> list[SlotSpec]:
    """The live tournament slate — 3 long / 3 short, single-position first-to-fire.
    ★ 2026-07-25 (operator, Saturday roster change): promoted abs_veto (thrust + 55s
    absorption-veto, the validated shadow abs_veto_55s = +$1,340 engine-truth 07-16..24)
    as TWO independently-switchable single-sided gates — abs_veto_long / abs_veto_short —
    replacing thrust_short (superseded) and rgv_long (worst performer, −$691). The 55s
    veto itself is applied in tournament.run() (VETO_GATES); side-filtering is automatic
    (_gate_fires drops the wrong-direction thrust). base_size=1 for the first live week
    to read like-for-like against the still-running shadow (scale on live evidence).
    ★ 2026-07-25 REHAB (operator, gate-rehab-findings): grind_long (scalp-2R + no give-back;
    ATR≥24, ER floor dropped), capitulation_long (require_flip=True is the edge + give-back off;
    ATR≥10, ER ceiling dropped — was bug-based), rgv_short (fast_turn off + ATR≥20), exhaustion_short (REVIVED — FIXED 8/12 exit = its
    FootprintShadow design, ER ceiling dropped as bug-based, edge=flow-absorption). rgv_long
    was researched + given a net30-depth floor but SWAPPED OUT for the more-robust exhaustion
    (its _RGV_LONG + gate net30_floor kept in code for a possible shadow). Each root-caused, not
    benched at face value.
    ★ 2026-07-27 (operator): the regime-3-exit SELECTOR is LIVE roster-wide (adaptive_exit — see below):
    every gate now picks its exit WIDTH by the router regime at entry (aligned-trend → WIDE lock-chandelier
    to ride, chop → TIGHT k1.5 to bank, counter → k2.0). Validated regime-only, +$756 OOS / 6-of-7 days
    (scripts/exit_selector_sweep.py). Each gate's static `exit=` is kept as the revert target."""
    specs = [
        # LONG
        SlotSpec("grind_long", "grind", "LONG",   # ★2026-07-26 deploy (§356): threshold-chandelier (loose start_k=3.5 until 6.0R, then firm lock_k=0.5) captures the trend tail — +$1,782 full/+$747 wk30, robust 15/15 LODO, BEATS scalp-2R +$508+. ATR≥24 + ER floor DROPPED (deciders); no give-back.
                 # ★2026-08-08 (operator, SATURDAY #2 / grind-long-revert-atr22-ext30-0808): "ext_hi" DELETED.
                 # Falls back to gate_grind's own default of 4.0. REV2 · Q1 §10 re-derived it on the tick-honest
                 # book AND on the 128 live router-gated lots and removes it on BOTH: everything from 3.0 upward
                 # scores identically (+$5,893 / +$6,081 / +$5,981 / +$6,262) so there is NO optimum to find and
                 # 2.0 was a $2,210 tax. The live 128 agrees more strongly — the ceiling deleted 12 real lots
                 # worth +$389 at 50% win. ★ DO NOT PIN 3.0: the earlier card said "ext 2.0 → 3.0", and pinning
                 # any literal here just re-fits the thing this revert is undoing. Supersedes BUILD #18
                 # (grind-ext-hi-regime-conditional-0808), which said "do NOT remove it" on the Movement-2
                 # sat-out-run population — a ceiling judged on exactly the trades it was designed to skip.
                 # Revert: re-add "ext_hi": 2.0.
                 #   Superseded rationale, kept for the audit trail: ★2026-08-01 (operator, Saturday window):
                 #   + ext_hi 2.0 — "don't buy what is already stretched". Cuts ~39% of grind fires; claimed
                 #   before/after +$1,552 → +$2,830 on replay.
                 params={"slope_min": 0.4, "fast_slope": True}, sizing="conviction", base_size=2,
                 exit="chandelier_lock", chandelier_start_k=3.5, lock_r=6.0, lock_k=0.5, giveback_enabled=False),
        SlotSpec("capitulation_long", "capitulation", "LONG",   # ★2026-07-25 rehab: require_flip=True IS the edge (wait for buyers to step in); give-back off; ATR≥10 + ER ceiling DROPPED (was bug-based). ★2026-07-28: base_size 2→1 (operator) — it's the gate most exposed to fast directional drops (fades a knife); a fast-move stop split its 2 lots (1 at the stop, 1 −28pt deeper) for −$147 07-28. Halve the exposure.
                 # ★2026-08-02 REVERTED to require_flip=True / 2.0R. The 08-01 change (flip=False, 1.0R) was
                 # shipped on a BROKEN STATISTIC and is withdrawn. The rehab justified it with "78% of bounces
                 # reach 1R" and used that as a WIN RATE. Reaching 1R is an MFE measure — it ignores whether the
                 # STOP came first. Measured on this gate's own live entries against 250ms ticks:
                 #     "reached 1R" (MFE, ignores ordering) = 14/14 = 100%
                 #     actually hit +1R BEFORE -1R (the race) =  4/14 =  29%
                 # Breakeven at a 1.0R target with a 1.0xATR stop is 50%, so 29% is structurally negative. Every
                 # independent measurement agrees and none is near 78%: the byte-identical shadow twin capit_loose
                 # (climax 2.5 / dom 0.60 / no-flip / 1.0R) is -$5,250 on 238 fires at 16.8% win, and the live gate
                 # all-time is -$122 on 24 fires at 37.5%. Same MFE-vs-ordering error found in giveback_grid.py the
                 # same weekend — easy to make, and it inflates everything it touches.
                 # Back to the 07-25 rehab config. Do NOT re-propose flip=False/1.0R without an ordering-correct
                 # win rate. Also drop the capitulation_long cell from data/exit_overrides.json (it pinned Lot A
                 # to the falsified 1.0R).
                 params={"climax_min": 2.5, "dom_min": 0.6, "require_flip": True},
                 sizing="flat", base_size=1, exit="scalp", target_r=2.0, stop_atr_mult=1.0, giveback_enabled=False),
        SlotSpec("abs_veto_long", "thrust", "LONG",   # thrust + 55s absorption-VETO (tournament.VETO_GATES)
                 params={"thr": 1.5, "amp_floor": 0.0004}, sizing="flat", base_size=1,
                 exit="scalp", target_r=2.0, stop_atr_mult=1.0),
        # SHORT
        SlotSpec("rgv_short", "reversal_grab", "SHORT",   # ★2026-07-25 rehab: fast_turn OFF + ATR floor 13→20 (see _RGV_SHORT)
                 params={"side": "SHORT", **_RGV_SHORT}, sizing="flat", base_size=2,
                 exit="scalp", target_r=2.0, stop_atr_mult=1.0),
        SlotSpec("exhaustion_short", "exhaustion", "SHORT",   # ★2026-07-25 rehab REVIVED (swapped in for rgv_long): FIXED 8pt-stop/12pt-target exit (its FootprintShadow design — ATR-2R was too wide for a snap-back), give-back off, ER ceiling dropped (bug-based). Edge = flow-absorption. Router-unmanaged.
                 params={}, sizing="flat", base_size=2,
                 exit="fixed", fixed_stop_pt=8.0, fixed_target_pt=12.0, giveback_enabled=False,
                 veto_counter_regime=True),   # ★2026-07-28: skip shorts fired INTO a local up-trend (counter −$190/56tr)
        SlotSpec("abs_veto_short", "thrust", "SHORT",  # thrust + 55s absorption-VETO (tournament.VETO_GATES)
                 params={"thr": 1.5, "amp_floor": 0.0004}, sizing="flat", base_size=1,
                 exit="scalp", target_r=2.0, stop_atr_mult=1.0),
        # ★2026-08-01 (operator, Friday M3 greenfield): NIPC — news-impulse pullback continuation, the ONE
        # brand-new entry that survived the whole robustness battery (+$2,676 · n=171 · 12d · 43.3% · 9/12
        # days green · 44/44 parameter variants positive · both sides independently green · survives $12/RT
        # and a 3-pt stop-slip). Two-sided, one slot per side (the abs_veto pattern). Armed 13:00–15:00 UTC
        # ONLY, OFF in dead-chop (ATR1m<18 AND ER15<0.35), 20-min cap, flat by 15:30 UTC, one position at a
        # time across BOTH sides + a 2-min cooldown (the shared NipcTracker enforces all of that).
        # ★ The R is NOT ATR-derived: the decider carries |entry−stop| as entry_atr on the OPEN intent, so
        # stop_atr_mult=1.0 reproduces the lab's pullback-extreme∓4pt stop exactly. target_r=2.5 is the
        # 1-lot headline config; under the scaleout slate it becomes Lot A 2.0R / Lot B 2.5R (the PROVEN
        # pair — fixed 2.5R on Lot B beats the trail by $1,285 here, so Lot B must NOT be a chandelier).
        # base_size=1: promotion-ladder first live week. NEW GATE — ships benched (gate_switches.env=off).
        # ★★2026-08-15 NIPC RETIRED FROM THE LIVE ROSTER (operator: "delete nipc gates theyve never
        # done anything"). It hit the operator's -$400 kill criterion (n=47, 26% win), then sat PINNED
        # OFF and held out of the 22:00 reactivation, so it has not traded since 2026-08-06. Its whole
        # live record is 49 lots for -$434.50 across 08-03..08-06.
        # Removing the SlotSpecs is what actually retires it: no spec means no slot, no intents, no
        # switch to manage. The deciders (nipc_in_window / nipc_past_flat_clock / nipc_dead_chop), the
        # NipcTracker and tests/test_nipc.py are DELIBERATELY KEPT — they are the record of how it
        # worked and cost nothing dark, and [[never-kill-a-lead-that-has-a-glimmer]] says a refuted
        # lead is archived, not erased. Its 49 historical trades stay in the ledger untouched; deleting
        # them would corrupt the P&L record to tidy a roster.
        # Revive: restore the two SlotSpecs below from git history (this commit).
    ]
    for s in specs:            # ★2026-07-27: regime-3-exit selector LIVE roster-wide (revert: set False)
        if s.kind != "nipc":   # ★2026-08-01: NIPC is exempt — its exit is a PROVEN fixed 2.0R/2.5R pair
            s.adaptive_exit = True   # (the regime-3 chandelier is the very thing the lab falsified here)
    return specs


# ★2026-07-29 (operator): DUAL-SLOT SCALE-OUT — the unified profit exit. Each gate splits into TWO
# independent 1-lot sub-slots that BOTH fire on the same signal: Lot A banks a fixed-R scalp (guaranteed
# floor), Lot B rides the chandelier for the tail. Replaces the mixed per-gate exits. base-name benching /
# the 55s veto / the exhaustion confirm all key on the BASE gate (tournament._base strips the _A/_B suffix).
# BIG-RUN gates → A@2.5R + B wide lock-chandelier; FADERS → A@1.5R + B tight k1.5 chandelier.
# Revert: GAZBOT7_TOURNAMENT_SLATE=tournament (back to the single-position first-to-fire slate).
_BIG_RUN = frozenset({"grind_long", "abs_veto_short", "abs_veto_long", "exhaustion_short"})

# ★2026-08-01 (NIPC): gates whose (Lot A, Lot B) pair was PROVEN by a sweep, not inherited from the
# BIG-RUN/FADER default. NIPC's 270-config exit sweep put 2.0R/2.5R at the top (+$5,199 vs +$4,642 for
# the 1.5R/2.5R prior) and explicitly FALSIFIED a trailing Lot B in this window ($4,642 vs $3,357 at the
# same Lot A) — so neither built-in default is right for it. data/exit_overrides.json still wins; this is
# the FAIL-SAFE floor for when that file is missing/malformed.
_FIXED_PAIR: dict[str, tuple[float, float]] = {"nipc_long": (2.0, 2.5), "nipc_short": (2.0, 2.5)}

# ★2026-07-31 (operator): PER-GATE EXIT OVERRIDES — the regime-flex control panel. gate_switches.env is the
# on/off (arming) axis; data/exit_overrides.json is the EXIT axis — put ANY gate on scalp (both lots fixed-R,
# tunable) OR chandelier, matched to the regime, so we tune the exit instead of sitting out. Format:
#   {gate: {"a_r": <LotA scalp R>, "b": <LotB: number = scalp R | "wide" = lock-chandelier ride | "tight" = k1.5 snap-back>}}
# e.g. {"exhaustion_short":{"a_r":0.5,"b":1.5}, "abs_veto_long":{"a_r":1.5,"b":2.5}, "grind_long":{"a_r":2.5,"b":"wide"}}
# A gate ABSENT from the file uses its built-in default (BIG-RUN → A@2.5R + B wide; FADERS → A@1.5R + B tight).
# Read at slate build → RESTART tournament to apply. FAIL-SAFE: missing/malformed file or entry → that gate falls
# back to its default (never breaks the desk). Revert slate entirely: GAZBOT7_TOURNAMENT_SLATE=tournament.
_EXIT_OVERRIDES_PATH = os.environ.get("GAZBOT7_EXIT_OVERRIDES", "/home/alphabot/gazbot7/data/exit_overrides.json")


def _load_exit_overrides() -> dict:
    """Validated per-gate exit overrides. Any bad file/entry is skipped so that gate keeps its built-in default."""
    try:
        with open(_EXIT_OVERRIDES_PATH) as f:
            raw = json.load(f)
        assert isinstance(raw, dict)
    except Exception:
        return {}
    ok: dict = {}
    for gate, o in raw.items():
        try:
            a = float(o["a_r"]); b = o["b"]
            if not 0 < a <= 20:
                continue
            if isinstance(b, (int, float)):
                if not 0 < float(b) <= 20:
                    continue
                b = float(b)
            elif b not in ("wide", "tight"):
                continue
            entry = {"a_r": a, "b": b}
            # ★★2026-08-16 STOP WIDTH IS NOW AN OVERRIDE LEVER. Until today `stop_atr_mult` was
            # hard-coded to 1.0 in all three branches of scaleout_slots(), so this panel could tune
            # targets but NOT the stop — and the Friday report's exhaustion_short answer (REV2 Q2)
            # IS a stop change: +$3,459.98 at stop 1.5xATR / target 2.0R against -$339.06 for the
            # tight chandelier on the same 87 signals, with the chandelier at the 58th percentile of
            # its own random-entry control. Validated hard and DEFAULTED TO 1.0, so any gate without
            # the key behaves exactly as before. Capped at 5.0 — a wider stop than that on MNQ is a
            # typo, and a typo here would size every stop on the desk.
            try:
                sk = float(o.get("stop_k", 0) or 0)
                if 0 < sk <= 5.0:
                    entry["stop_k"] = sk
            except Exception:
                pass
            # ★2026-08-02 OPTIONAL quiet-tape clip: {"atr_split": <pt>, "lo": {"a_usd": <$>, "b_r": <R>}}.
            # Validated hard and independently of the rest of the entry — a malformed `lo` drops ONLY the
            # split and leaves the gate's normal A/B intact, so a typo can never disarm an exit.
            try:
                sp = float(o.get("atr_split", 0) or 0)
                lo = o.get("lo") or {}
                a_usd = float(lo.get("a_usd", 0) or 0)
                b_r = float(lo.get("b_r", 0) or 0)
                b_floor = float(lo.get("b_floor_usd", 0) or 0)
                if sp > 0 and 0 < a_usd <= 500 and 0 < b_r <= 20 and 0 <= b_floor <= 500:
                    if b_floor and b_floor <= a_usd:      # Lot B must never clip tighter than Lot A
                        b_floor = 0.0                      # bad floor → drop the floor, keep the split
                    entry.update(atr_split=sp, lo_a_usd=a_usd, lo_b_r=b_r, lo_b_floor=b_floor)
            except Exception:
                pass
            ok[gate] = entry
        except Exception:
            continue
    return ok


def _lot_b(base: SlotSpec, b, stop_k: float = 1.0) -> SlotSpec:
    """Lot B from a spec: number = fixed-R scalp; "wide" = lock-chandelier (ride tail); "tight" = k1.5 chandelier (snap-back)."""
    common = dict(tag=f"{base.tag}_B", sizing="flat", base_size=1, adaptive_exit=False, giveback_enabled=False)
    if b == "wide":
        return replace(base, exit="chandelier_lock", chandelier_start_k=3.5, lock_r=6.0, lock_k=0.5, **common)
    if b == "tight":
        return replace(base, exit="chandelier", vol_adaptive_chandelier=False, chandelier_start_k=1.5,
                       chandelier_min_k=0.5, chandelier_tighten=0.75, **common)
    return replace(base, exit="scalp", target_r=float(b), stop_atr_mult=stop_k, **common)


def scaleout_slots() -> list[SlotSpec]:
    """Dual-slot scale-out slate (12 sub-slots). Inherits each base gate's entry config (kind/side/params/vetoes)
    via ``replace`` — single source of truth — overriding only tag+exit. Per-gate exit is the built-in default
    (BIG-RUN → A@2.5R + B wide-chandelier; FADERS → A@1.5R + B tight-chandelier) UNLESS overridden per
    data/exit_overrides.json (the regime-flex control). Revert slate: GAZBOT7_TOURNAMENT_SLATE=tournament."""
    ov = _load_exit_overrides()
    out: list[SlotSpec] = []
    for base in tournament_slots():
        o = ov.get(base.tag)
        if o:   # operator exit override (data/exit_overrides.json)
            _sk = float(o.get("stop_k", 1.0))     # 1.0 = the pre-2026-08-16 behaviour
            a = replace(base, tag=f"{base.tag}_A", sizing="flat", base_size=1, adaptive_exit=False,
                        exit="scalp", target_r=o["a_r"], stop_atr_mult=_sk, giveback_enabled=False)
            b = _lot_b(base, o["b"], _sk)
            if o.get("atr_split"):   # ★2026-08-02 quiet-tape clip — Lot A takes $, Lot B a tighter fixed R
                a = replace(a, atr_split=o["atr_split"], lo_target_usd=o["lo_a_usd"])
                b = replace(b, atr_split=o["atr_split"], lo_target_r=o["lo_b_r"],
                            lo_floor_usd=o.get("lo_b_floor", 0.0))
            out += [a, b]
            continue
        pair = _FIXED_PAIR.get(base.tag)
        if pair:                     # proven fixed pair (NIPC) — fail-safe when the override file is gone
            a = replace(base, tag=f"{base.tag}_A", sizing="flat", base_size=1, adaptive_exit=False,
                        exit="scalp", target_r=pair[0], stop_atr_mult=1.0, giveback_enabled=False)
            out += [a, _lot_b(base, pair[1])]
            continue
        big = base.tag in _BIG_RUN   # built-in default
        a = replace(base, tag=f"{base.tag}_A", sizing="flat", base_size=1, adaptive_exit=False,
                    exit="scalp", target_r=(2.5 if big else 1.5), stop_atr_mult=1.0, giveback_enabled=False)
        out += [a, _lot_b(base, "wide" if big else "tight")]
    return out


class SlotStrategy:
    def __init__(self, specs: list[SlotSpec], *, value_per_point: float) -> None:
        self._specs = specs
        self._vpp = value_per_point
        self._peak: dict[str, float] = {s.tag: 0.0 for s in specs}  # per-slot peak-fav (manage state)
        self._exit_mode: dict[str, str] = {}   # per-slot exit width chosen at entry (adaptive_exit gates)
        self._exit_lo: dict[str, bool] = {}    # ★2026-08-02 per-slot quiet-tape clip on/off, frozen at entry
        # ★ NIPC (2026-08-01): ONE tracker shared by the long+short (and _A/_B) sub-slots — rule 6 is
        # "one position at a time" across BOTH sides, so the state machine must be single, not per-slot.
        self._nipc_tags = [s.tag for s in specs if s.kind == "nipc"]
        self._nipc = NipcTracker() if self._nipc_tags else None
        self._nipc_busy = False
        self._nipc_fire = None                 # this tick's triggered NipcSetup (consumed by _gate_fires)

    @staticmethod
    def _regime_mode(side: str, bars) -> str:
        """Regime-at-entry → exit width, mirroring direction_router (same ER/NET thresholds, no drift).
        aligned-trend → 'wide' (ride) · counter-trend → 'mid' · chop/insufficient → 'tight' (bank)."""
        from .direction_router import ER_TREND, NET_MIN, WINDOW
        closes = [b.close for b in bars[-WINDOW:]]
        if len(closes) < 6:
            return "tight"
        path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))) or 1.0
        er = abs(closes[-1] - closes[0]) / path
        net = closes[-1] - closes[0]
        up = er >= ER_TREND and net >= NET_MIN
        down = er >= ER_TREND and net <= -NET_MIN
        if (side == "SHORT" and down) or (side == "LONG" and up):
            return "wide"
        if (side == "SHORT" and up) or (side == "LONG" and down):
            return "mid"
        return "tight"

    # ── entry: this slot's gate, THIS slot's direction only ──────────────────
    def _gate_fires(self, spec: SlotSpec, f, tape_net: float, footprint: dict) -> bool:
        if spec.kind == "grind":
            e = gate_grind(f, tape_net=tape_net, **spec.params)
        elif spec.kind == "reversal_grab":
            e = gate_reversal_grab(f, tape_net=tape_net, **spec.params)
        elif spec.kind == "thrust":
            e = gate_thrust(f, **spec.params)
        elif spec.kind == "capitulation":       # tape-footprint climax fade
            e = gate_capitulation(f, cap_sell=footprint.get("cap_sell", 0.0),
                                  cap_buy=footprint.get("cap_buy", 0.0),
                                  cap_base=footprint.get("cap_base", 0.0),
                                  cap_dpx=footprint.get("cap_dpx", 0.0),
                                  cap_flip=footprint.get("cap_flip", False), **spec.params)
        elif spec.kind == "exhaustion":         # heavy flow that failed to move price into a wall
            sig = exhaustion_signal(footprint.get("net_signed", 0.0), footprint.get("price_move_pt", 0.0),
                                    footprint.get("bid1_size", 0.0), footprint.get("ask1_size", 0.0),
                                    footprint.get("bid1_price", 0.0), footprint.get("ask1_price", 0.0))
            return sig is not None and sig[0] == spec.side   # (side, entry) tuple
        elif spec.kind == "nipc":               # news-impulse pullback — the shared tracker fired this tick
            return self._nipc_fire is not None and self._nipc_fire.side == spec.side
        else:
            e = None
        return e is not None and e.side == spec.side   # direction-gated per slot

    def _size(self, spec: SlotSpec, bars, atr: float) -> int:
        qty = (conviction_lots(efficiency_ratio(bars), base=spec.base_size)
               if spec.sizing == "conviction" else spec.base_size)
        if spec.risk_budget_usd > 0 and atr > 0 and qty > 0:      # risk-bounded (per slot)
            per_lot = atr * spec.stop_atr_mult * self._vpp
            if per_lot > 0:
                qty = min(qty, max(1, int(spec.risk_budget_usd // per_lot)))
        return qty

    # ── one decision cycle → per-slot intents ────────────────────────────────
    def decide(self, f, price: float, bars, slotbook, tape_net: float,
               footprint: dict | None = None, now_ms: int | None = None) -> list[dict]:
        footprint = footprint or {}
        intents: list[dict] = []
        self._nipc_step(price, bars, slotbook, now_ms)
        for spec in self._specs:
            slot = slotbook.slot(spec.tag)
            if slot.is_flat:
                self._peak[spec.tag] = 0.0
                if self._gate_fires(spec, f, tape_net, footprint):
                    qty = self._size(spec, bars, f.atr)
                    # regime-at-entry (local trailing bars) — drives the exit-width selector AND the
                    # counter-regime entry veto; compute once when either needs it.
                    mode = (self._regime_mode(spec.side, bars)
                            if (spec.adaptive_exit or spec.veto_counter_regime) else None)
                    if spec.veto_counter_regime and mode == "mid":      # fade fired INTO a local trend → skip
                        continue
                    if qty > 0:
                        if spec.adaptive_exit:                          # freeze the exit width at entry
                            self._exit_mode[spec.tag] = mode
                        # ★2026-08-02 quiet-tape clip: decide ONCE, at entry, on the entry ATR — and hold
                        # it for the life of the position. Re-evaluating mid-trade would let a widening
                        # tape move the target away from a position that is already green, which is the
                        # exact give-back this is meant to stop.
                        if spec.atr_split:
                            self._exit_lo[spec.tag] = f.atr < spec.atr_split
                        # ★ NIPC carries its OWN R (|entry − pullback-extreme ∓ 4pt|) as entry_atr, so the
                        # native STP + exit_scalp land exactly on the lab's stop / 2.0R / 2.5R. Every other
                        # gate keeps f.atr (unchanged).
                        eatr = (self._nipc_fire.r_pt if (spec.kind == "nipc" and self._nipc_fire) else f.atr)
                        intents.append({"action": "OPEN", "slot": spec.tag, "gate": spec.tag,
                                        "side": spec.side, "qty": qty, "price": price,
                                        "meta": {"entry_atr": eatr,
                                                 "exit_mode": self._exit_mode.get(spec.tag) if spec.adaptive_exit else None}})
            else:
                reason = self._manage(spec, slot, price, now_ms)
                if reason is not None:
                    intents.append({"action": "CLOSE", "slot": spec.tag, "gate": spec.tag,
                                    "reason": reason})
        return intents

    # ── NIPC: drive the shared state machine once per tick, before the slot loop ──────────
    def _nipc_step(self, price: float, bars, slotbook, now_ms: int | None) -> None:
        """Fold this tape print into the tracker's 5s bars and test the live half-back trigger.
        Rule 6 ("one position at a time", 2-min cooldown) is enforced HERE, across both sides:
        while any nipc sub-slot holds, no impulse is detected and no trigger can fill; the
        cooldown starts the moment the last sub-slot goes flat. now_ms is required — without a
        clock NIPC cannot know the window, so it simply never fires (fail-safe)."""
        self._nipc_fire = None
        if self._nipc is None or now_ms is None or len(bars) < 6:
            return
        busy = any(not slotbook.slot(t).is_flat for t in self._nipc_tags)
        if self._nipc_busy and not busy:            # the position just closed → rule 6 cooldown
            self._nipc.note_exit(now_ms)
        self._nipc_busy = busy
        self._nipc.on_price(now_ms, price, atr1m=_atr(bars),
                            er15=efficiency_ratio(bars, NIPC_ER15_BARS), busy=busy)
        if not busy:
            self._nipc_fire = self._nipc.trigger(now_ms, price)

    @staticmethod
    def _opened_ms(slot) -> int | None:
        """Epoch-ms of this slot's entry fill (``opened_at`` is the venue exec time). None if
        unparseable — the caller then skips the time-cap rather than cutting on bad data."""
        from datetime import datetime, timezone
        if not slot.opened_at:
            return None
        try:
            dt = datetime.fromisoformat(slot.opened_at)
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    def _manage(self, spec: SlotSpec, slot, price: float, now_ms: int | None = None) -> str | None:
        # ★ TIME exits first (NIPC rule 5: 20-min hard cap + flat by 15:30 UTC). Both are opt-in
        # per spec (0 = off), so no existing gate's behaviour changes. They pre-empt the profit
        # exits deliberately — a clock exit is a risk cut, not a P&L decision.
        if now_ms is not None:
            if spec.flat_by_utc_s and ((now_ms // 1000) % 86400) >= spec.flat_by_utc_s:
                return "SESSION_FLAT"
            if spec.max_hold_s:
                op = self._opened_ms(slot)
                if op is not None and (now_ms - op) >= spec.max_hold_s * 1000:
                    return "TIME_CAP"
        # track this slot's own peak-favourable, then run its exit stack. The native
        # 1-ATR STP (execution half) owns the loss side; here = the managed/profit exits.
        fav = (price - slot.entry_price) if slot.side == "LONG" else (slot.entry_price - price)
        if fav > self._peak[spec.tag]:
            self._peak[spec.tag] = fav
        pos = Position(slot.side, slot.entry_price, slot.entry_atr, self._peak[spec.tag])
        reason = None
        # ★2026-08-02 QUIET-TAPE CLIP — pre-empts the whole normal exit stack when the entry ATR said so.
        # Deliberately first: on quiet tape the trail IS the leak, so nothing downstream should get to run.
        # Lot A banks a fixed DOLLAR amount, Lot B a tighter fixed R. The native 1-ATR STP still owns the
        # loss side, unchanged. Off unless atr_split is set, so no existing gate is touched.
        if spec.atr_split and self._exit_lo.get(spec.tag):
            if spec.lo_target_usd and fav * self._vpp * (slot.qty or 1) >= spec.lo_target_usd:
                return "TARGET"
            if spec.lo_target_r and slot.entry_atr > 0:
                # max(R-based, dollar floor) — the floor stops Lot B inverting under Lot A on very
                # quiet tape (1.75R < the $40 clip for any ATR under 11.4). See lo_floor_usd.
                tgt_pt = spec.lo_target_r * slot.entry_atr
                if spec.lo_floor_usd:
                    tgt_pt = max(tgt_pt, spec.lo_floor_usd / (self._vpp * (slot.qty or 1)))
                if fav >= tgt_pt:
                    return "TARGET"
            return None
        if spec.adaptive_exit:   # regime-3-exit selector (width frozen at entry); native 1-ATR STP owns the loss
            mode = self._exit_mode.get(spec.tag, "tight")
            if mode == "wide":   # aligned trend → WIDE lock-chandelier (ride the run)
                reason = exit_chandelier_lock(pos, price, start_k=3.5, lock_r=6.0, lock_k=0.5)
            else:                # chop → TIGHT k1.5 · counter-trend → k2.0 (bank / damage-control)
                k = 1.5 if mode == "tight" else 2.0
                if exit_chandelier(pos, price, start_k=k, min_k=0.5, tighten=0.75):
                    reason = "CHANDELIER"
        elif spec.exit == "chandelier":
            sk = (chandelier_start_k(pos.entry_atr) if spec.vol_adaptive_chandelier
                  else spec.chandelier_start_k)
            if exit_chandelier(pos, price, start_k=sk, min_k=spec.chandelier_min_k,
                               tighten=spec.chandelier_tighten):
                reason = "CHANDELIER"
        elif spec.exit == "fixed":   # fixed POINT stop+target (snap-back fade); native 1-ATR STP is the backstop
            reason = exit_fixed(pos, price, stop_pt=spec.fixed_stop_pt, target_pt=spec.fixed_target_pt)
        elif spec.exit == "chandelier_lock":   # loose start_k trail until lock_r R, then firm lock_k lock (grind_long trend-capture)
            reason = exit_chandelier_lock(pos, price, start_k=spec.chandelier_start_k,
                                          lock_r=spec.lock_r, lock_k=spec.lock_k)
        elif exit_scalp(pos, price, target_r=spec.target_r,
                        stop_atr_mult=spec.stop_atr_mult) == "TARGET":
            reason = "TARGET"
        if reason is None and spec.giveback_enabled and not spec.adaptive_exit:
            # ★2026-07-27: under the regime-3-exit selector the chandelier IS the profit exit —
            # the give-back overlay is off so it can't pre-empt the (tight/wide) chandelier.
            if exit_giveback(pos, price, value_per_point=self._vpp, qty=(slot.qty or 1),
                             arm_usd=spec.giveback_arm_usd, giveback_usd=spec.giveback_usd):
                reason = "GIVEBACK"
        return reason
