---
name: ratchet-giveback-width-study
description: "STUDY 2026-06-22 (negative) — widening the ratchet give-back to \"let winners run\" LOSES in every form tested (loose-early curve, velocity×freshness strength-gating); on this week TIGHTER give-back wins monotonically; \"let winners run\" is regime work not a static curve; tools scripts/ratchet_adaptive_sim.py + ratchet_strength_sim.py"
metadata: 
  node_type: memory
  type: project
  originSessionId: 67c42436-f6c3-496d-ac98-2caeb1ac27ce
---

**Operator asked** to let winners run via a wider/adaptive give-back on the profit ratchet (currently flat 25%, `PROFIT_RATCHET_GIVEBACK=0.25`, $10 activation floor). Built two measure-first sims (read-only, causal, fill at the give-back floor, capped at actual close, compare IN-MODEL so only the give-back RULE differs). See [[ratchet-fast-feed-study]] for the 5s-feed context.

**All three findings say DON'T widen — and the give-back actually wants to be TIGHTER on this sample:**
1. **Magnitude curve** (`ratchet_adaptive_sim.py`, give-back 60–75%→10% as peak profit grows): loses **−$393–402 over 5 days** (1m, 443 trades) vs flat-25. Bleeds because it stays wide on every young winner incl. the weak ones that round-trip.
2. **Velocity×peak-freshness strength-gating** (`ratchet_strength_sim.py`, default tight, widen only while run is fresh+moving in ATR units): **loses in EVERY swept config** (−$37 to −$491/5d; 95 worse / 13 better). The velocity signal does NOT predict continuation at 1m granularity; widening always costs. Closer to "do nothing" = smaller loss.
3. **Flat give-back sweep is monotonic the OTHER way:** 10%→−$593, 15%→−$726, 20%→−$859, **25%(live)→−$982**, 40%→−$1353, 50%→−$1545. TIGHTER banks more — ~$389 saved at 10% vs 25% on this window.

**Why:** 06-18→06-22 was a net-LOSING chop week (actual −$1164). In chop, the rare winners give back fast → banking quickly wins. "Let winners run" only pays in a TREND regime. So the right lever is **regime-conditioned give-back** (wide on trend days, tight on chop — we now have `session_regime` in the funnel), NOT a static curve or per-trade velocity. Aligns with [[strategy-layer-reframe]] (regime-first, mechanism-over-threshold).

**CAVEATS (why no live change made):** all at scale on **1m bars** (the sim fires on bar LOWS; live ratchet prices off ~5s-fresh bar CLOSES → less twitchy, so the tighten-edge is partly 1m-noise). The **5s feed is too thin** — only ~5 covered trades even on Monday (per-symbol 5s coverage is sparse, started 06-19 17:49). ONE chop week. Do NOT retune live give-back on this; re-run as 5s accrues. KEEP flat 25%.
