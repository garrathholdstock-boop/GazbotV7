---
name: promotion-ladder-sizing
description: "Operator's promotion-ladder concept — sizing is EARNED via an evidence-gated ladder (shadow@1 → live@1 → 2 → 3 micros), a new Friday SIZING section, CHAMP eventually automates the nominate/demote decision."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d7443f59-d3b4-466f-b7e6-3903cacfd274
---

**2026-07-09 operator idea — sizing should be EARNED, not chosen.** Framing: "this strategy has EARNED another contract," NEVER "the best one gets 2." The Friday report gains a **SIZING** section running each sim up a **promotion ladder**; CHAMP (the best-sim-per-contract view) is the machinery to eventually AUTOMATE the nominate/demote call.

**The ladder:** Stage 1 shadow@1 sim contract → Stage 2 live@1 micro → Stage 3 (gates below) 2 micros → Stage 4 (another review) 3 micros. Symmetric DOWN escalator = the **DEPARTURE LOUNGE** (decaying sims monitored-for-removal). Report NOMINATES; operator ARMS (L-DAYREVIEW-DESCRIPTIVE).

**Nomination gates (ALL, never one hot week):** (1) 8–12 weeks consistent data; (2) ≥100–200 trades for stable expectancy (⚠ selective sims trade less → take LONGER, that's a feature); (3) +EV ACROSS regimes (trend/chop/vol); (4) drawdowns within comfort; (5) **LOW CORRELATION with the deployed desk** (don't double a risk you already hold); (6) profile — low churn, clean rules, good R:R > a 70%-win tiny-grind (those SCALE; grinders don't).

**Sim #1 (`tw_mnq_thrust_cont`) is the exemplar** — selective, +expectancy, complementary to Ride-Strength, clean, R:R-driven. ⚠ its edge is MNQ-SPECIFIC (+$35/tr MNQ → +$1.9 MES → +$0.3 M2K, does NOT port — [[exit-architecture-scar-tissue]] thread) → a size-up is MNQ-ONLY and gate #5 (correlation vs Ride-Strength/thrust, all MNQ-momentum) is load-bearing.

Same evidence spine as the confirmation ladder (🔴 in-sample → 🟡 1wk OOS → 🟢 3wk) but applied to SIZE, not arm/disarm. Logged in `scripts/friday/RUNBOOK.md` addendum; scope `docs/PROMOTION_LADDER_SCOPE.md` when built. Related [[three-pass-adversarial-friday]] (the Friday report), [[favourable-condition-gating-vision]].
