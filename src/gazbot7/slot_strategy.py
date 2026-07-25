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

from dataclasses import dataclass, field

from .deciders import (
    Position,
    chandelier_start_k,
    exit_chandelier,
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
    exit: str = "chandelier"               # "chandelier" | "scalp"
    target_r: float = 2.0
    stop_atr_mult: float = 1.0
    vol_adaptive_chandelier: bool = True
    chandelier_start_k: float = 3.5
    chandelier_min_k: float = 0.5
    chandelier_tighten: float = 0.75
    giveback_enabled: bool = True
    giveback_arm_usd: float = 50.0
    giveback_usd: float = 40.0
    risk_budget_usd: float = 80.0


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
    ATR≥10, ER ceiling dropped — was bug-based), rgv_short (fast_turn off + ATR≥20). Each
    root-caused, not benched at face value."""
    return [
        # LONG
        SlotSpec("grind_long", "grind", "LONG",   # ★2026-07-25 rehab: scalp-2R BEATS chandelier for grind; no give-back; ATR≥24 + ER floor DROPPED (deciders)
                 params={"slope_min": 0.4, "fast_slope": True}, sizing="conviction", base_size=2,
                 exit="scalp", target_r=2.0, stop_atr_mult=1.0, giveback_enabled=False),
        SlotSpec("capitulation_long", "capitulation", "LONG",   # ★2026-07-25 rehab: require_flip=True IS the edge (wait for buyers to step in); give-back off; ATR≥10 + ER ceiling DROPPED (was bug-based)
                 params={"climax_min": 2.5, "dom_min": 0.6, "require_flip": True},
                 sizing="flat", base_size=2, exit="scalp", target_r=2.0, stop_atr_mult=1.0, giveback_enabled=False),
        SlotSpec("abs_veto_long", "thrust", "LONG",   # thrust + 55s absorption-VETO (tournament.VETO_GATES)
                 params={"thr": 1.5, "amp_floor": 0.0004}, sizing="flat", base_size=1,
                 exit="scalp", target_r=2.0, stop_atr_mult=1.0),
        # SHORT
        SlotSpec("rgv_short", "reversal_grab", "SHORT",   # ★2026-07-25 rehab: fast_turn OFF + ATR floor 13→20 (see _RGV_SHORT)
                 params={"side": "SHORT", **_RGV_SHORT}, sizing="flat", base_size=2,
                 exit="scalp", target_r=2.0, stop_atr_mult=1.0),
        SlotSpec("exhaustion_short", "exhaustion", "SHORT",     # fade heavy buying into an ask wall
                 params={}, sizing="flat", base_size=2, exit="scalp", target_r=2.0, stop_atr_mult=1.0),
        SlotSpec("abs_veto_short", "thrust", "SHORT",  # thrust + 55s absorption-VETO (tournament.VETO_GATES)
                 params={"thr": 1.5, "amp_floor": 0.0004}, sizing="flat", base_size=1,
                 exit="scalp", target_r=2.0, stop_atr_mult=1.0),
    ]


class SlotStrategy:
    def __init__(self, specs: list[SlotSpec], *, value_per_point: float) -> None:
        self._specs = specs
        self._vpp = value_per_point
        self._peak: dict[str, float] = {s.tag: 0.0 for s in specs}  # per-slot peak-fav (manage state)

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
               footprint: dict | None = None) -> list[dict]:
        footprint = footprint or {}
        intents: list[dict] = []
        for spec in self._specs:
            slot = slotbook.slot(spec.tag)
            if slot.is_flat:
                self._peak[spec.tag] = 0.0
                if self._gate_fires(spec, f, tape_net, footprint):
                    qty = self._size(spec, bars, f.atr)
                    if qty > 0:
                        intents.append({"action": "OPEN", "slot": spec.tag, "gate": spec.tag,
                                        "side": spec.side, "qty": qty, "price": price,
                                        "meta": {"entry_atr": f.atr}})
            else:
                reason = self._manage(spec, slot, price)
                if reason is not None:
                    intents.append({"action": "CLOSE", "slot": spec.tag, "gate": spec.tag,
                                    "reason": reason})
        return intents

    def _manage(self, spec: SlotSpec, slot, price: float) -> str | None:
        # track this slot's own peak-favourable, then run its exit stack. The native
        # 1-ATR STP (execution half) owns the loss side; here = the managed/profit exits.
        fav = (price - slot.entry_price) if slot.side == "LONG" else (slot.entry_price - price)
        if fav > self._peak[spec.tag]:
            self._peak[spec.tag] = fav
        pos = Position(slot.side, slot.entry_price, slot.entry_atr, self._peak[spec.tag])
        reason = None
        if spec.exit == "chandelier":
            sk = (chandelier_start_k(pos.entry_atr) if spec.vol_adaptive_chandelier
                  else spec.chandelier_start_k)
            if exit_chandelier(pos, price, start_k=sk, min_k=spec.chandelier_min_k,
                               tighten=spec.chandelier_tighten):
                reason = "CHANDELIER"
        elif exit_scalp(pos, price, target_r=spec.target_r,
                        stop_atr_mult=spec.stop_atr_mult) == "TARGET":
            reason = "TARGET"
        if reason is None and spec.giveback_enabled:
            if exit_giveback(pos, price, value_per_point=self._vpp, qty=(slot.qty or 1),
                             arm_usd=spec.giveback_arm_usd, giveback_usd=spec.giveback_usd):
                reason = "GIVEBACK"
        return reason
