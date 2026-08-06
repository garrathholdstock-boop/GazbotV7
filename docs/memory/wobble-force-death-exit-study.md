---
name: wobble-force-death-exit-study
description: "2026-06-30 STUDY (NEGATIVE) — \"let it wobble red/green then instant-death on the forceful run south\" does NOT beat the flat-clock on chop data; room-to-wobble costs money monotonically"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a177229-b370-41db-bb71-2814d3a9582c
---

2026-06-30 operator idea: an exit that lets the contract go red→green→red→green (give it time to
wobble and recover), then **instant death on the final forceful run south**. Built + ran
`scripts/wobble_force_death_sim.py` (READ-ONLY, 1m bars, 30-min horizon, ~530 flat-clock futures
trades / 10d, causal). Replaces the 5-min RED flat-clock with: ride free (no time cut) → force-death
= N consecutive adverse 1m closes covering ≥ force_atr×ATR (the desk's existing
`trailing_adverse_run` "force" gate), keeping the 1-ATR stop + RATCHET 1.

**Result = NEGATIVE, decisive, consistent across all 6 micros.**
- Best per-contract config (in-sample UPPER BOUND): Δ **+$171 / 10d** on a −$9,272 flat-clock bleed → realistically ~$0 out-of-sample.
- The force-death trigger **barely fires** (0–10×/contract) and never clips a winner (ratchet/stop own those).
- **"Room to wobble" is FALSIFIED**: widening the disaster stop 1→2→3 ATR makes every contract monotonically WORSE (e.g. MNQ −$3291→−$4029; M2K −$862→−$1226). The optimizer picks the TIGHTEST 1-ATR stop every time.

**Why:** on this ~8d CHOP week these reds don't systematically recover — 43–80% "touch green" but only fleetingly (RATCHET 1 already banks those). The genuine runs south are already caught by the 1-ATR disaster stop BEFORE 2-3 adverse minutes accumulate, so force-death adds almost nothing. The 1-ATR stop IS the "instant death," and tight beats loose. Consistent with [[recovery-exit-study]] ("extending non-recoverers is the killer"), [[ratchet-giveback-width-study]] ("tighter wins monotonically on chop"), and the [[strategy-layer-reframe]] ("let-winners-run is a REGIME problem not a static curve").

**Caveats / how to revisit:** chop-only sample (no trend) — the idea could still shine in a TRENDING regime where a red wobbler recovers into a sustained run; needs a winning-trend period to test. 1m granularity blunts "instant" (force needs ≥2 minute-closes); a faithful sub-minute version needs a continuous tape PAST the recorded exit — `ticks.db` (1s/250ms) is accumulating but doesn't yet span these trades. Revisit alongside the passive tick re-sweep DUE ~2026-07-06 (see [[force-kill-dormant-and-resweep]]). Nothing armed; flat-clock stays.
