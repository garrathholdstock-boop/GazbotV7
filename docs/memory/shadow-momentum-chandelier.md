---
name: shadow-momentum-chandelier
description: "2026-07-06 shadow revelation — momentum wants a wide tightening ATR chandelier, reversion wants tight 25%; + the reprice canonical-exit bug it exposed"
metadata: 
  node_type: memory
  type: project
  originSessionId: ed1c42ef-2406-4523-9fbd-a9a07df11ff2
---

**2026-07-06 REVELATION (shadow analytics only; live desk untouched). DECISIONS §333.**

**Momentum and reversion want OPPOSITE exits.** Every past chandelier-vs-25% test lost ONLY because the reversion trades (which love the tight 25%-of-peak give-back) clouded the blended number. Isolate momentum and **25% is its WORST exit** — it clips runs on the first small retrace.
- **REVERSION → tight 25% give-back** (`exit_desk`, `SHADOW_RATCHET_GIVEBACK_REVERSION=0.25`). Bank the mean-reversion pop before it reverts.
- **MOMENTUM → a volatility-scaled TIGHTENING ATR chandelier** (`exit_ratchet`): give-back DISTANCE = k·ATR, k starts WIDE (`SHADOW_MOMO_CHANDELIER_KWIDE=3.5` ATR — invisible early, the 1-ATR stop owns the downside so the run breathes) and TIGHTENS to `KTIGHT=0.5` ATR once the peak clears `CAP_R=4.0` R. Let it run, then lock it hard. Fine-tuned on the day's top-10 momentum runs: **captured ~69% of the $950 peak**, grid-robust across kwide 3.5-5 / ktight 0.4-0.75 / cap 4-6R. Gated `rmult<=0` (rmult>0 = the dead pre-2026-07-05 ATR-mult path, kept for the test).

**THE LOAD-BEARING BUG this exposed (now fixed):** `scripts/passive_through_fill_backtest.realistic_trade` replayed the DEFAULT `exit_desk` for EVERY shadow → momentum was silently repriced under the REVERSION exit, and NO ratchet tuning ever reached the dashboard. Fix = `realistic_trade` takes the strategy's CANONICAL `exit_fn` via **`_canonical_exit_fn`** (reversion→exit_desk, momentum→exit_ratchet; mirrors the desk-else-ratchet canonical). **This is the new invariant** — a new momentum shadow reprices under the chandelier, a reversion one under 25%. The 2-min `alphabot-shadow-reprice.timer` keeps it current; the sim records the same going forward.

**Impact:** re-repriced full → shadow WEEK P&L **−302 → −104 (+$198)**; momentum combos finally capture their runs (`tw_mnq_thrust_cont` +$433, `momentum_shadow` MNQ +$252, `tw_mgc_momo_thrust` +$156). Commits `a57235f4`+`bfedda02` (+ the mobile redesign `7975f8d5`, ratchet-enable `49da9fd6`/`e4935c11`).

**FAITHFUL-EXIT FIX (2026-07-06 late, commit `b78f2c91`, DECISIONS §337):** the reprice used to cap its tick window at ~`clock_min`+3min + model NO time-exit for momentum (`exit_ratchet` has no flat-clock; its EOD is dead in the replay since `sid==esid`) → held runners marked `INCOMPLETE` at an optimistic ~8-min mark (was 42% of the momentum green). Now `replay_exit` runs the desk's FULL stack — loads ticks to each trade's real `exit_ts` + adds a RED-ONLY FLAT_CLOCK (winner survives, matches `daytrade_stop_runner`) + SESSION_FLAT at the real close. **Registered INCOMPLETE 45→0; today re-repriced +$527→+$508 (−$19 — green was mostly real, revelation survives). Every shadow $ is now a banked desk exit; pre-`b78f2c91` shadow P&L is SUPERSEDED.**

**🔴 EXPERIMENTAL — not proven:** ONE chop day, IN-SAMPLE, win% only 46-56% → the +$198 may be fat-tail-carried. **Carried into `scripts/friday/RUNBOOK.md`** for weekend interrogation: needs OOS + a TREND week (where the wide chandelier should really separate) + a FULL-week k/cap grid. Nothing armed on the live desk (L-DAYREVIEW-DESCRIPTIVE). Related: [[ratchet-giveback-leak-and-robustness]] (the live desk's 25%-static revert), [[favourable-condition-gating-vision]].
