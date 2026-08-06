---
name: router-exhaustion-short-null
description: "2026-07-26 — router-managing exhaustion_short is a NULL (0 up-trend fires, structural); router correctly sized at 2 gates"
metadata: 
  node_type: memory
  type: project
  originSessionId: 56db3271-178d-477c-8537-702242d72c01
---

Asked "should the direction-router manage all 6 gates?" → NO. The 3 momentum gates (grind_long, abs_veto_long, abs_veto_short) must stay unmanaged (benching thrust "cost a winner and nothing else"; a counter-thrust can be the reversal). The router correctly manages the 2 clear reversion faders: `capitulation_long` (off in TREND_DOWN) + `rgv_short` (off in TREND_UP).

The only candidate gap was `exhaustion_short` (a short-side flow-absorption fader, dropped from UP_OFF on 07-25 with a stale/inverted code comment). **Backtested it (scratchpad `router_exhaustion_bt.py`, imports live `direction_router` constants, monkeypatch-only): adding exhaustion_short to UP_OFF = $0 effect.** In a 15-day window with 63 TREND_UP marks (~16h of up-trend), exhaustion_short fired **0 times** in TREND_UP (vs rgv_short n=2/−$152, which the router correctly blocks). **Structural reason:** exhaustion_short needs heavy BUY-flow that FAILS to move price — in a clean up-trend buyers win/price moves, so the failed-absorption trigger rarely fires. It self-selects away from up-trends → no counter-trend bleed to catch.

Where exhaustion_short DID lose = 3 fires in TREND_DOWN (−$118) = shorts WITH the down-trend (trend-following) → a gate-edge/fixed-8-12-exit issue, NOT a router one; the router must never bench trend-following fires.

⚠ n=21, one summer RANGE regime, no monster up-trend. Revisit ONLY if a real TREND week shows exhaustion_short firing into + losing in up-trends (would surface in the Friday rehab section). Related: [[gates-two-sided-per-side-tuning]], [[direction-router-live]], [[friday-gate-rehabilitation-section]].
