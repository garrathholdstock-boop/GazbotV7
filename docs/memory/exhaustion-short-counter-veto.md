---
name: exhaustion-short-counter-veto
description: "2026-07-28: exhaustion_short is a TRIGGER-and-ride not a fader; its real bleed is COUNTER-trend (short-into-uptrend), not low-ER. ER floor tried+REVERTED same day; fixed via veto_counter_regime entry veto. Gate now marginal → relegation-watch."
metadata: 
  node_type: memory
  type: project
  originSessionId: 56db3271-178d-477c-8537-702242d72c01
---

**2026-07-28 (operator-driven deep dive on exhaustion_short).** exhaustion_short (footprint absorption-fade, SHORT-only on the live roster) is NOT really a mean-reversion fader — the absorption event is a TRIGGER (a good spot to get short); whether it fades or RIDES is set by the adaptive exit + regime. So with the live wide exit it can ride big trends (the +$324 open on 07-28).

**The key finding (225-trade `exhaustion_rev` SHADOW repriced under the LIVE adaptive exit, `scripts/shadow_er_adaptive.py`):** the real bleed is DIRECTIONAL, not low-ER.
- by alignment (`_regime_mode` at entry): **wide (aligned, short-in-downtrend) 46tr −$60 @26%w · mid (COUNTER, short-in-UPtrend) 56tr −$190 @43%w · tight (chop) 93tr +$19 @53%w**. Counter-trend is the killer; chop ≈ breakeven; even aligned rides are streaky (26% win, carried by rare monsters).
- Whole gate nets **−$231/195tr** under the live exit → exhaustion_short is a **MARGINAL / relegation-watch gate** (Saturday). Cutting counter → −$41 (still ~breakeven).

**What was deployed (commit `5234d31`, gazbot7 — LIVE, local-only not pushed):**
1. An ER floor 0.08 was tried first (operator, after a live chop loss) then **REVERTED same day** — the 48 REALISED trades looked like low-ER was the problem (chop <0.08 −$202) but that was a DOWN-trend-biased week; the bigger faithful shadow sample showed low-ER/chop is ≈breakeven under the live exit and the bleed is counter-trend. ER-floor lesson: a small down-biased sample overstated the ER story.
2. **`SlotSpec.veto_counter_regime=True` on exhaustion_short** — skip the OPEN when `_regime_mode(side, bars)=='mid'` (a short fired INTO a local up-trend). Cut is at ENTRY on the LOCAL trailing-bar regime the exit-selector already reads. Verified: up→mid→VETOED, down→wide→kept, chop→tight→kept. Revert: set False + restart.

**Why NOT the router (important):** the router benches on the Paris DAY-path regime; exhaustion_short in router UP_OFF = $0 (0 up-trend fires — the day-state is ~never TREND_UP when exhaustion fires; see [[router-exhaustion-short-null]]). The counter losses are only visible on the LOCAL 30-bar regime → the fix must be an entry veto, not router management. [[direction-router-live]]

**Offline gate-replay 2 weeks back is UNRELIABLE for this gate:** the signal is episodic (net≥400 in a 20s window = ~0.01% of windows on BOTH archives), so a coarse-cadence walk misses ~all fires. Faithful sources = REALISED trades or the SHADOW (same live tick loop). Tools: `fade_override_test.py`, `exhaustion_er_bands.py`, `shadow_er_validate.py`, `shadow_er_adaptive.py`. Related exit finding: aligned→ride wins, chop→bank ([[exit-selector-regime-live]]). ⚠ one-regime (~1wk capture) lead. TODO exhaustion_LONG never modelled (no long shadow; offline replay unreliable) → add to SHADOW to collect faithful data.
