---
name: backtest-per-regime-segment-not-blanket
description: "RULE — never blanket-backtest one fixed gate/exit config across weeks of tape; segment by regime + time-of-day and score each config only on its home tape (test the POLICY, not a static config). Use more tape."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0bb3b1b0-e3be-4607-baa9-5ed673420d95
---

**Operator (2026-07-31):** when backtesting the regime-flex desk, do NOT blanket ONE fixed gate/exit config across 2 weeks of tape — that averages the regimes where a config should be ON with the ones where it should be OFF/different, washing the edge out. The desk is regime-conditional now (which gates are armed + which EXIT each uses depend on ATR / ER / time-of-day — the `gate_switches.env` on/off axis + the `data/exit_overrides.json` exit axis, see [[favourable-condition-gating-vision]], [[exit-selector-regime-live]]). The backtest must replicate that switching.

**Why:** a config that is +EV in its HOME regime and −EV elsewhere nets to ~0 / negative under a blanket test → you wrongly REJECT a real edge (or accept a mediocre average). A blanket test measures a config we would never actually run unchanged. This is the same trap as judging a gate at face value ([[friday-gate-rehabilitation-section]]).

**How to apply:**
1. **Segment the tape first** — by regime (dead-chop / normal-chop / in-between-building / clean-trend / violent-chop, keyed on **ATR level + ER + range-break**, NOT the clock alone — see [[backtest-per-regime-segment-not-blanket]] sibling finding that ATR carries the time-of-day effect) AND by **time-of-day** (overnight vs US session post-13:30 UTC — the big 4R/6R runners are a post-open phenomenon).
2. **Map each segment → the config designated to run there** (the regime→exit cheat-sheet).
3. **Score each config ONLY on its home segments** — evaluate the POLICY (regime→config selection), never a single static config blanket-applied.
4. **Use MORE tape** so each regime bucket keeps a meaningful n after segmenting.

Applies to the Friday report exit/scalp studies and every gate/exit sweep. Related: [[favourable-condition-gating-vision]], [[exit-selector-regime-live]], [[three-pass-adversarial-friday]], [[dual-slot-scaleout-live]].
