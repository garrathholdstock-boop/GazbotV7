---
name: momentum-amp-floor-ab
description: "Momentum filter = AMPLITUDE floor (atr_pct>=0.04), NOT efficiency (that failed); deployed observe-only A/B on the 5 named momentum shadows 2026-07-10, controls left ungated"
metadata: 
  node_type: memory
  type: project
  originSessionId: d7443f59-d3b4-466f-b7e6-3903cacfd274
---

**2026-07-10 DEPLOYED (observe-only A/B, marker 10:32:39 UTC):** added `MOMENTUM_AMP_FLOOR_PCT = 0.04` (a `atr_pct >= 0.04` entry veto via `_amp_floor_blocks`) to the 5 momentum shadows the operator named — **#1 tw_mnq_thrust_cont, #2 tw_mes_thrust_cont, #3 tw_m2k_vst, #12 momentum_shadow, #13 orb_shadow** — in `alphabot/strategy/shadow_strategies.py`. The **other momentum sims #4–#11 stay UNGATED as a live control cohort**; watch the gated sims diverge from controls on the same tape from the marker. Deploy = strategy-daemon restart (desk was flat). **Observe-only shadows — no live money; the live vwap_dip/vwap_pullback fade desk is UNCHANGED.**

**Why:** 14d forensic (momentum_shadow real_pnl) — the ONLY −EV amplitude bucket is `atr_pct<0.03` (−$256, +$0.18/tr = noise); edge lives at 0.04–0.08 (+$575, **+$2.70/tr**). `amp≥0.04 OR RTH` blocks a net-losing set (−$73). **The efficiency hypothesis FAILED** — 07-10 chop had HIGH trailing-eff (0.125) but THIN amplitude; slope (1.22) + rvol (1.47) also looked normal at losing entries → amplitude is the separator the recorded features are blind to. Same axis as reversion's strong-chop `atr_pct` floor (0.06), lower threshold = the universal "thin tape = stand down" signal (why momentum bled, passive-fade was a mirage, AND reversion stood down on 07-10: one root cause — thin amplitude).

**Watch / next:** confirm as a PLATEAU (0.03/0.04/0.05) forward, not in-sample spike; session overlay (momentum edge 4–5× richer in US RTH 13–20 UTC); logged to tonight's report via `desk_analysis` row `momentum_amp_floor_ab_20260710` + Friday RUNBOOK lead. **Revert = floor→0.0.** Arming any LIVE momentum gate stays operator-gated. Ties [[favourable-condition-gating-vision]], [[exit-architecture-scar-tissue]], [[shadow-sim-understates-losses]].
