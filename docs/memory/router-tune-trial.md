---
name: router-tune-trial
description: "Claude IS the intelligent router — PERMANENT/ONGOING as of 2026-07-30 (operator ended the trial framing: 'i want you in there ongoing, it works'). Every 5 min reads the global desk view + recent-trades and benches/enables gates on a HOLISTIC judgment the ER-router misses. PAPER, benching-only, auto-router stays OFF."
metadata: 
  node_type: memory
  type: project
  originSessionId: 56db3271-178d-477c-8537-702242d72c01
---

**★ NOW PERMANENT (2026-07-30).** Operator made the Claude-run router ongoing, not a time-boxed trial — *"why would we wrap the trial. i want you in there ongoing. it works. i have heaps of claude credits i dont use because all the heavy building is done."* Actions taken: **cancelled the WRAP cron `0c307b5c`** (was 21:55 UTC 07-30 — would have re-enabled the mechanical auto-router + deleted the tick); **re-armed the 5-min tick as `cd4edefc`** with ongoing framing (drops "finish the trial" language, links the lessons). Auto-router timer stays DISABLED indefinitely; Claude owns `data/gate_switches.env`.

**⚠ OPERATIONAL CONSTRAINTS of the ongoing arrangement (session crons):** (1) **session-bound** — every cron (the 5-min tick, hourly watch, sweeps) lives only in THIS Claude session and vanishes if it exits; a truly durable always-on router would need a disk-backed scheduler outside the session. (2) **7-day auto-expiry** — recurring crons fire a last time then delete after 7 days, so the tick (and the others) must be **re-armed ~weekly** (CronCreate again) to stay alive. Re-arm resets the clock. If the desk ever goes quiet unexpectedly, check `CronList` first — the tick may have expired or the session died.

**LIVE TRIAL 2026-07-29 Paris day (operator-authorized, PAPER).** Operator gave Claude "absolute licence today to bench gates based on a global view of the desk" — a scoped one-day override of the standing RULE that only the operator benches. Goal: stop the little bad entries that bleed all day (his words: "if we only did half the trades but cut out 10 losers we're suddenly profitable"). Grounded in the Mon+Tue analysis: **LONG gates −$399 vs SHORT gates +$118** — the whole 2-day loss was longs fighting down-biased days. Validated lever = **DAY DIRECTIONAL BIAS** (net pt from the Paris open), which the ER-router MISSES (choppy-down days are low-ER so it never called TREND_DOWN → longs stayed on). At ±50pt bench-the-fighters flipped Mon+Tue from −$280 → +$98 (`scripts/loser_daybias_analysis.py`).

**Mechanism:**
- Auto-router timer DISABLED (`gazbot7-direction-router.timer`); Claude owns `data/gate_switches.env`. Backup = `gate_switches.env.pre-trial`.
- 15-min cron `13c4f429` wakes Claude → runs `scripts/desk_view.py` (DAY BIAS, last-hr ER/ATR, per-gate day+hr P&L, SHADOW per-gate = unbenched counterfactual, position, switches) → applies the framework → writes gate_switches.env → logs to `data/router_trial_log.txt` → notifies only on a change.
- FRAMEWORK: (1) day-bias DOWN≤−40 → bench longs / UP≥+40 → bench shorts; (2) chop (ER<.10,|net|<40) → bench momentum; (3) bleeder ≥$80+fighting → bench; (4) never bench aligned+green, re-enable when condition clears; (5) cross-check shadow (benched-but-shadow-green = over-benching).
- Removed the US-open check cron `2f659bf0` (ran the router → would fight the trial).
- WRAP cron `32834fee` (21:55 UTC 07-29, one-shot): shadow-SCORE the trial (each bench window vs that strategy's shadow P&L = saved-vs-cost), re-enable the auto-router timer, delete `13c4f429`, report verdict + recommend whether the day-bias veto becomes a PERMANENT router feature.
- First call (00:4x Paris): DAY BIAS DOWN −90pt/ER0.32 → benched all 3 longs, kept shorts on.

**★ OUTCOME → extended to DAY 2 + succeeding — see [[router-trial-day2-findings-0730]].** Operator extended it overnight ("keep it going") then to a 5-min cadence for 07-30. Result: **FIRST 2 GREEN DAYS IN A ROW EVER (07-29 +$638.5, 07-30 +$586)**. The trial fed REAL gate improvements back into the desk (grind ER floor 0.35 validated; abs_veto wants no floor; abs_veto=reliable momentum gate vs grind=churner), a live ROUTER panel `/v7/router`, and `scripts/recent_trades.py`. Day-2 WRAP cron = 21:55 UTC 07-30 (`0c307b5c`). The framework below is the 15-min v1; day-2 added: bench by MECHANISM in a rotation (all momentum off, reversion on), re-arm only on a vol-EXPANDING break, don't override abs_veto's veto with the lagging ER.

**REVERT anytime:** `cp data/gate_switches.env.pre-trial data/gate_switches.env; sudo systemctl enable --now gazbot7-direction-router.timer; CronDelete 13c4f429`. Safe: PAPER, benching only gates NEW entries (open positions always exit; stops/safety untouched). [[loser-router-analysis]] [[direction-router-live]] [[gates-two-sided-per-side-tuning]]
