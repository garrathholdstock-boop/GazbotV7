---
name: router-trial-day2-findings-0730
description: "★ Router-tune trial DAY 2 (2026-07-30, 5-min cadence, Claude managing the router). FIRST 2 GREEN DAYS IN A ROW EVER (07-29 +$638.5, 07-30 +$586). Produced real gate tuning: grind_long ER floor 0.35 VALIDATED (10-day backtest +$728), abs_veto_long wants NO floor (its veto is the filter). abs_veto=reliable momentum gate, grind=churner. Built /v7/router panel + recent_trades.py."
metadata: 
  node_type: memory
  type: project
  originSessionId: fdd18525-f007-4dbb-8d0e-f435f4d4eca8
---

**Router-tune trial extended to DAY 2 (2026-07-30), operator "keep it going into tonight" → 5-min cadence.** Claude owns `gate_switches.env`, benches on a HOLISTIC regime read (trend/chop/rotation) the ER-router misses. ★★ **FIRST TWO GREEN DAYS IN A ROW EVER: 07-29 +$638.5, 07-30 +$586** (still climbing). The trial's regime-benching is the proximate cause — it kept momentum OFF through a ~13-hour range-rotation (the day's bleed) and ON only for the real afternoon breakout. "Success so far" (operator). North star = [[desk-green-by-end-august-goal]].

**★ ER-FLOOR GATE TUNING (backtested 10 days 07-20..30, `scripts` inline reprice) — the trial fed a real code change:**
- **grind_long ER floor → 0.35: STRONGLY VALIDATED.** Flips grind from −$670 (10d) to **+$58** (Δ +$728). grind has NO absorption-veto, so the ER *is* its trend-confirmation; a high floor cuts the mid-zone bleed. Reverses the 07-25 rehab that DROPPED grind's floor (that was a trend-week finding; this is a rotation-day one). LIVE (commit `9767c67`).
- **abs_veto_long: NO ER floor is right — its 55s absorption-veto IS the filter.** Backtest: floor 0.25 = **−$121 (HURTS)**; abs_veto is BIMODAL — winners at LOW ER (0.04–0.18, veto-caught early thrusts, incl. today's +$251 which fired at ER **0.06**) AND high ER (≥0.35), losers ONLY in the mid-band 0.25–0.35. A floor removes the low-ER gems. Currently deployed at 0.25 (operator's pick before the backtest); **RECOMMEND revert to no-floor** (or a mid-band 0.25–0.35 EXCLUSION, backtests ~+$460 — a code change to build). abs_veto already +$232/10d on its own.
- Grounding: today's momentum longs bucketed by 30-min entry-ER = **−$431 @18%W in the MID band 0.20–0.35** (rotation legs that look trendy but reverse) vs **+$279 @40%W at ≥0.35**. `deciders.ER_FLOOR`.

**★ abs_veto (veto) vs grind (no-veto) — THE momentum-gate lesson.** abs_veto is the RELIABLE momentum gate: its veto filters fakes and lets it catch thrusts EARLY (low trailing ER), then the scale-out banks it (A target + B chandelier). grind CHURNS — even floor-gated it buys into resistance/stalls (today it fired 6× at the session-high, mostly stopped). **07-30 live: abs_veto +$630 (A +202 / B +428) vs grind −$53.** RULE: run momentum through abs_veto, keep grind mostly benched; grind needs a veto/absorption-check or resistance-awareness, an ER floor alone doesn't fix it. [[er-favourable-condition-gate-live]]

**★ Router lessons banked DAY 2 (add to [[router-benching-lessons-0729]]):**
1. **Don't override abs_veto's veto-passed thrust with the LAGGING ER.** I benched abs_veto on last-hr ER 0.03 — but its veto was catching the REAL break; it won +$251. The veto IS confirmation; the ER lags a fresh move.
2. **Don't thrash a gate.** I toggled grind ~6× chasing breaks. Discipline: pick the mechanism read (abs_veto carries momentum, grind's a net-red coin-flip) and HOLD it; don't re-arm on every green flicker.
3. **Low-ATR "hold" ≠ breakout.** Every fake break today was on COMPRESSING ATR (12–14); real trends EXPAND vol. Require vol-expansion, not just a duration-hold above the level.
4. **Multi-clock ER** (the "why chop at 0.30?" answer): 30-min gate-ER 0.30–0.50 can be day-ER 0.03 — the legs alternate and cancel (rotation). Judge on the DECISION clock (are legs sustaining or alternating?), not one ER number.

**★ Dual-slot scale-out proven REPEATEDLY (operator: "resounding success"):** 5 dual-profit exits today — Lot A TARGET + Lot B CHANDELIER both green: +$163, +$111, +$146, +$72, **+$251** (abs_veto_long — the standout, mirror of yesterday's abs_veto_short +$768). [[dual-slot-scaleout-live]]

**★ Built (LIVE):** the **ROUTER dashboard panel `/v7/router`** (web.py `router_json` + `web_static/router.html`, commit `e58e1e0` + brightness/Paris-time tweaks) — multi-clock regime, per-gate on/off + auto-derived reason, shadow-family cross-check, timestamped activity stream (Paris time), 2-slot holdings. And **`scripts/recent_trades.py`** — the live bleeding check (exit_reason wall-of-STOP per gate; aggregate P&L hides a stale-tail-masking-a-bleeding-scalp). [[v7-dashboard-routing-and-restore]]

**Open items:** revert abs_veto floor (operator call); build the mid-band exclusion + multi-regime backtest for the Friday report; grind needs a deeper fix than ER. Trial WRAP cron 21:55 UTC 07-30 (`0c307b5c`) scores + re-enables the auto-router. [[router-tune-trial]] [[router-benching-lessons-0729]]
