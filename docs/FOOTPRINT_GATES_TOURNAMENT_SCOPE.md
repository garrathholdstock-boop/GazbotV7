# GAZBOT V7 — Footprint gates into the tournament

**Status:** ✅ **BUILT + LIVE 2026-07-21** (commit `4c708fc`). The tournament runs the full
**3 long / 3 short** slate: rgv-long, grind-long, **capitulation-long** | thrust-short,
rgv-short, **exhaustion-short**. Implementation note: instead of extending the live **md**
service, the **tournament** computes the footprint each tape tick from `capture.db`
(`footprint.footprint_summary()` — rolls up `capitulation_tape` + the exhaustion 20s
net/move + L1 book), exactly as the shadow loop does — so the live md service is
**untouched** (lower risk). `SlotStrategy.decide` takes a `footprint` dict; `_gate_fires`
routes it to the capitulation/exhaustion gates, direction-gated per slot. +9 tests;
validated on the live capture.db. Original scope kept below.

---

## Why

The tournament's `SlotStrategy` feeds each gate `(Features, tape_net)`. That's enough
for the **drop-in** gates — grind, rgv, thrust — which are the starting 4-slot slate.
But two of the operator's chosen gates are **tape-footprint / L2**, not Features-based:

- **`gate_capitulation`** (flush-and-flip) needs `cap_sell, cap_buy, cap_base, cap_dpx,
  cap_flip` — a one-sided aggressor **climax** in the short tape window (a side's volume
  ≥ `climax_min`× its baseline AND ≥ `dom_min` of flow, while price moved that way).
- **`exhaustion_signal`** (footprint.py) needs `net_signed` (20s buy−sell) + `price_move_pt`
  — heavy aggression that FAILED to move price (a distinct signature from absorption).

Neither is in the `Features` struct, so they can't slot in until the tournament carries
the footprint summary. The raw data already exists (the md aggressor `ticks`, `depth.db`
L2, and `footprint.FootprintShadow`); it just isn't fed to the decision layer.

## The wiring (small, shared by both gates)

1. **md publishes a footprint summary.** The md service already computes the tape
   (`recent_tape` → net_flow / win_price_delta). Extend it (or a new `T_FOOTPRINT`
   message) to also emit the short-window aggressor climax: `cap_sell, cap_buy,
   cap_base, cap_dpx, cap_flip` and `net_signed, price_move_pt`. This is the same
   aggressor-tick roll-up `FootprintShadow` already does — lift it into md.
2. **`SlotStrategy.decide` takes a `footprint` dict** alongside `tape_net`, and
   `_gate_fires` routes it: `capitulation` gets the `cap_*`, an `exhaustion` kind gets
   `net_signed/price_move_pt`. (grind/rgv/thrust ignore it — unchanged.)
3. **Add the two slots** to `tournament_slots()`:
   - `capitulation_long` — LONG (fade a sell-flush).
   - `exhaustion_short` — SHORT (fade an exhausted top).
   → the slate becomes **6**: rgv-long, grind-long, capitulation-long (3 long) ·
   thrust-short, rgv-short, exhaustion-short (3 short).

## Notes / risks
- **Exhaustion is 20s-tick, not 1-min** — it fires faster than the bar clock. Confirm
  the decision cadence (tape-tick) is fast enough; it should be (SlotStrategy runs per
  tape tick, ~1s).
- **`cap_dpx` sign** decides direction (down-move → LONG fade, up-move → SHORT fade);
  the slot's `side` filter (already in SlotStrategy) keeps each slot to its direction.
- **L2 (depth) for exhaustion** — the current `exhaustion_signal` is tick-only
  (net_signed/price_move_pt); the L2-book variant was tried and removed in V5 (the book
  can't see the iceberg refill). Keep it tick-based.

## Test plan
- md footprint summary matches `FootprintShadow` on the same ticks.
- `capitulation_long` fires on a synthetic sell-climax-with-down-move; not otherwise.
- `exhaustion_short` fires on heavy buy-flow + no up-move; direction-gated to the slot.
- The 6-slot slate: a long-flush routes only to capitulation_long; a top-exhaustion
  only to exhaustion_short.

## References
Gates: `deciders.gate_capitulation`, `footprint.exhaustion_signal` / `FootprintShadow`.
Tournament: `slot_strategy.tournament_slots()` (the drop-in 4), `PAPER_TOURNAMENT_SCOPE.md`.
Memory: `desk-l2-book-consumption-scope` (tape≠book; exhaustion stays tick-based).
