---
name: quiet-tape-clip-live
description: "ATR-conditional exit split — below 22pt ATR both lots clip ($40 / 1.75R floored $60); at or above, today's chandelier behaviour is unchanged."
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-02T16:41:42.546Z
---

Live 2026-08-02. `atr_split` / `lo_target_usd` / `lo_target_r` / `lo_floor_usd` on `SlotSpec`, configured per gate in `data/exit_overrides.json` as `{"atr_split": 22, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}}`. On for grind_long, capitulation_long, exhaustion_short, abs_veto_long/short. **Off for nipc** (13:00–15:00 only, never sees quiet tape, has its own swept pair). Revert = delete the `lo` keys + restart.

**The decision is made once, at entry, on entry ATR, and frozen for the life of the position.** Re-evaluating mid-trade would let a widening tape move the target away from an already-green position — the exact give-back this closes.

**The evidence** (live fills, 250 ms ticks, $1.50/RT, strip-best-3 + LODO on every cell):
- QUIET 22:00–13:30, n=97, median ATR **17.4pt** — $40 clip **+$360**, holds **+$244** stripped and **+$25** on its worst LODO fold, top trade 11% of net. Wide chandelier **−$538**, degrading to −$1,232 stripped. As-traded −$354.
- US 13:30–22:00, n=144, median ATR **28.4pt** — the reverse: 3.5R +$2,022 (+$1,019 / +$645), wide +$2,611 (+$964 / +$416). A $40 clip there **fails LODO** at −$232.
- Round-trippers (went ≥1R green, finished ≤0): **20.6% quiet vs 7.6% US** — the give-back really is a quiet-tape problem.

**Keyed on ATR, not the clock**, deliberately: a dead US afternoon should clip and a violent overnight should ride; a clock rule gets both wrong. The window split *is* an ATR split.

**Lot A is dollars, Lot B is R** — a fixed $ auto-tightens as ATR rises inside the quiet band and beat every R cell there (1.0R −$32, 1.25R −$18). The `b_floor_usd` exists because 1.75R is only 20pt at ATR 11.4, so without it **Lot B clipped tighter than Lot A below that** — runner banking before scalp, scale-out inverted, and ATR<11 is ~17% of MNQ minute bars.

**Not fully proven:** the 22pt threshold is a midpoint between the two medians, and Lot B's 1.75R/$60 are *inferred* — the grid swept single-lot exits, so the evidence says "B should clip not trail", not that level specifically. Only Lot A's $40 survived the full battery. Related: [[mfe-is-not-a-win-rate]], [[exit-architecture-scar-tissue]], [[mnq-fee-is-150-per-round-trip]].
