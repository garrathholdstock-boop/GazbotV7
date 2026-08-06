---
name: ratchet-activation-floor-lowered
description: "LIVE CHANGE 2026-06-22 — profit-ratchet activation floor lowered $10→$2 in .env (PROFIT_RATCHET_ACTIVATION_FLOOR_USD=2.0), strategy daemon restarted; a \"watch it\" forward test to catch green-then-drift-red trades; give-back UNCHANGED at 25%"
metadata: 
  node_type: memory
  type: project
  originSessionId: 67c42436-f6c3-496d-ac98-2caeb1ac27ce
---

**What changed:** `PROFIT_RATCHET_ACTIVATION_FLOOR_USD` 10.0 → **2.0** in `.env` (line 244), applied live by restarting `alphabot-strategy-daytrade.service` (desk was FLAT → no exposure to the un-deployed [[ratchet-restart-peak-loss-fix]] re-seed bug). Dashboard also restarted so the displayed knob shows $2. Verified: `settings.PROFIT_RATCHET_ACTIVATION_FLOOR_USD=2.0`, enabled=True, give-back UNCHANGED 0.25. Only `futures_runner.py:366` consumes it functionally. Backup: `.env.bak-floor-*`. **ROLLBACK** = set back to 10.0 + restart strategy daemon.

**Why:** the ratchet arms earlier (~as soon as a green clears the ~$2 fee buffer) to bank the trades that go green briefly then drift red into a flat-clock cut. The $2 floor is conservative — at 25% give-back the ~$2 breakeven loss-floor means it still won't actually bank until peak ≈$2.7, so it's "arm once meaningfully green past fees," NOT $0.01-aggressive. Operator chose to run it live and WATCH while the 5s data accrues.

**Evidence (caveated):** on the 06-18→06-22 1m week, arming earlier was strongly +$ vs actual (arm-green 25%-flat +$765; ATR-0.5-filtered +$468) — BUT every noise filter shrank the gain, the fingerprint that much of it is **1m intrabar-wick noise**, not real rescues. Loose-50%-early DIED (worse than flat). 5s (today, 5 trades) didn't confirm. See [[ratchet-giveback-width-study]] + scripts `ratchet_activation_sim.py` / `regime_giveback_sim.py`.

**The decider:** the mid-July 5s re-run (atd job #9, 2026-07-15 22:00 UTC → `scripts/regime_giveback_rerun.sh`, writes `~/study_output/regime_giveback_5s_rerun_*.txt`) now ALSO runs the arm-on-green + ATR sim on 5s. If the +Δ survives on clean 5s bars → keep/extend the low floor; if it collapses like the 1m noise filters → revert toward $10. A future session should read that report AND review how the live $2 floor performed in the interim (compare ratchet-exit P&L vs flat-clock round-trips since 06-22).
