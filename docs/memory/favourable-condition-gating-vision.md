---
name: favourable-condition-gating-vision
description: "The desk's north-star direction — per (contract × gate) learn winning conditions, only trade when they're met"
metadata: 
  node_type: memory
  type: project
  originSessionId: ccb6199e-59b1-4963-8e0b-88c88bf59bac
---

Operator's strategic direction (2026-07-02): *"once we understand the conditions that win for each contract and each gate, we simply don't trade unless those conditions are reached. Not regime, just favourable conditions — or maybe you want to call it regime!"*

The desk fires too much and **bleeds into unfavourable tape**. The fix is a **per-(contract × gate) favourable-condition gate**: for every live gate on every contract, learn (each Friday, on realistic P&L, robustness-gated, carried forward OOS) the tape conditions where it WINS vs bleeds, and only fire when the favourable conditions are met — block the toxic ones ("stop firing into the red").

**Why:** the 2026-07-02 live-desk scan proved conditions are LOUD and contract-specific — MES pullback: calm atr_pct PF 3.62 vs expanded PF 0.11; MNQ pullback wins shorting into TREND, dies in CHOP; MGC reversion bleeds (its edge was the retired momentum gate). And the MGC momentum 5s replay: over-fires 1434×/−$3,970, the EXIT is NOT the lever (tighter stops just churn more), SELECTIVITY is (net_atr floor 1.5→8 → ~50 trades, +EV PF 1.25).

**How to apply:** this is the home of the Friday Condition-Isolation Study ([[reversion-edge-quiet-tape-gate-tuner]] + scope `docs/FRIDAY_CONDITION_ISOLATION_SCOPE.md`). The report must (a) study favourable conditions for all 7 tracked contracts (MNQ/MES/MGC/M2K/MYM/MCL/MBT) × each live gate, (b) include momentum-gold, and (c) PRESCRIBE the best entry thresholds that isolate the favourable conditions (armable one-liners, confidence-tiered, OOS-confirmed). Operationalizes [[strategy-layer-reframe]] (mechanism/regime over threshold). Descriptive only — surfaces + prescribes; operator arms, courtroom confirms. Tools: `live_condition_scan.py`, `momentum_5s_tick_replay.py`, `momentum_gold_study.py`, `friday_condition_isolation.py`.
