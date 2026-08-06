---
name: stop-width-ab-2x-live
description: Stop-width A/B (1.0 vs 2.0 ATR) live in the shadow slate as sw_*_k10/k20; 1.5x already REFUTED; the exit_scalp target-coupling trap
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-04T12:44:26.478Z
---

2026-08-04, operator: "is atr 1 too tight for the momentum gates… would 1.5 or 2 let the runs survive?"
then "build the shadow a/b at 2.0".

## SETTLED: 1.5x is REFUTED — don't retest it
`scripts/stop_width_study.py B` (epoch Jul 29→31, 52 stopped momentum trades, live entries, first-touch
race on 250ms ticks): 1.5x **rescued 2 of 52** while making the other 50 lose 50% more = **−$1,126**.
Mechanical, not marginal: 1.5x sits just past the noise, so you pay more on nearly every loser and buy
almost no survivors. Epoch E (n=6) said 1.5x was BETTER — a 6-trade sample reversing sign against a
52-trade one. 2.0x looked +$1,133 but sits inside the model's 18% error, hence the A/B.

## LIVE NOW: 12 paired shadow arms
`sw_{grind_A,grind_B,absL_A,absL_B,absS_A,absS_B}_{k10,k20}` in `shadow.py::_stop_width_ab()`.
Read with `scripts/stop_width_ab.py`. Pinned by `tests/test_stop_width_ab.py` (45 cases).
7-day dry-run: k20 ahead +$1,738 ceiling_pnl, but NOT uniform — grind + absS prefer WIDE, **absL
prefers TIGHT** (k20 worse on both its lots). Do not apply one stop width roster-wide.

## ★★ THE TRAP THAT WOULD HAVE INVALIDATED IT — check for this in any exit sweep
`deciders.exit_scalp` computes `r = stop_atr_mult * entry_atr` and puts the target at `target_r * r`.
**THE TARGET IS COUPLED TO THE STOP WIDTH.** Setting stop_atr_mult=2.0 silently doubles the profit
target too, so you measure "stop AND target doubled" — a different experiment that looks plausible and
is worthless. Fixed with `decouple_target=True` (holds the target in POINTS at `target_r * atr`), and
`_record_target_r` persists the EFFECTIVE target_r so the tick repricer doesn't reprice against a target
2x too far. Any future stop-width or R sweep must check this coupling first.

## Second-order effect worth remembering
The arms take DIFFERENT numbers of trades (grind_A 141 at 1.0x vs 128 at 2.0x) with identical entry
logic. Cause is OCCUPANCY: a wider stop holds the position longer, so the slot is busy when the next
signal fires. Widening changes per-trade outcomes AND reduces trade count. Print n for both arms always.

## Method notes that cost real time to learn
- **Config epochs are mandatory.** My first run applied TODAY's exit spec (incl. the quiet-tape clip) to
  trades taken before the clip existed and produced a confident **+$2,477** for 2.0x. Pure artefact.
  Caught only because the harness reports k=1.0 as a LIVE-REPRODUCTION CHECK — k=1.0 *is* the live
  config, so it must reproduce the live book; it was 56% off. Every exit study needs that check.
- **`data/exit_overrides.json` IS NOT GIT-TRACKED.** The live exit ladder for Jul 31→Aug 2 is therefore
  UNRECOVERABLE — not hard, gone. Only undated snapshots (.pre-nipc, .pre-0801-TRUE) survive. FIX
  FORWARD: track it, or have the tournament log its resolved config at startup.
- Stop slippage measured per-trade from live fills: **median 0.82pt ($1.64/stop)** — much smaller than
  the ~$1,200-leak framing suggests, and it scales with the NUMBER of stops, so wider stops pay it less.
- Residual 18% model error concentrates in a few high-ATR trades where the tick replay and the live fill
  disagree on stop-vs-target ordering. Unexplained. It is why this needed paired live arms, not more
  modelling. Related: [[mfe-is-not-a-win-rate]], [[shadow-sim-understates-losses]],
  [[exit-lab-paired-method-overstates]].
