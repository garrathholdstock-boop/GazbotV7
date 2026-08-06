---
name: ratchet-giveback-leak-and-robustness
description: 2026-07-01 — the ratchet gave back $763/wk (captured 28% of $1287 peak vs 75% design); it's a FIRING failure not width; elite 7-layer robustness fix SCOPED (nothing armed)
metadata:
  type: project
---

2026-07-01 (operator furious a live MES short peaked +$40 then gave it all back). Built `scripts/ratchet_giveback_report.py` (250ms MFE from ticks.db vs banked pnl, per exit_reason). **THIS WEEK MNQ/MES/MGC: captured only 28% of $1,287 peak profit → $763 excess give-back.**

**Diagnosis — NOT give-back WIDTH, a FIRING failure:** RATCHET_1 captures **83%** when it fires (beats the 75% design). But **$637 of $763 is on trades the ratchet NEVER FIRED on** — they spiked green then died on FLAT_CLOCK (−134% capture, $383), SIGNAL_SELL ($151), FORCE_KILL ($103). MGC worst (captured −5%, $487 — fleeting gold reversions). Worst single: 06-30 MGC LONG peaked +$88 closed −$104.

**3 root causes:** (1) stale-price eval — runner evals on 5s/1m bar closes, misses fast spikes; (2) entry_atr orphaning — a position that loses entry_atr (reconcile-recovery after a gateway fills-wipe, e.g. today's live MES) hits degrade-safe "no ATR→skip ratchet" and drops out of management entirely → rides to flat-clock; (3) runner-side only — no venue-side protection if daemon/feed/reconcile degraded.

**FIX SCOPE `docs/RATCHET_ROBUSTNESS_FIX_SCOPE.md` — 7-layer defense-in-depth (flag-and-wait, shadow-first, NOTHING armed):** L1 250ms peak track, L2 250ms give-back react, **L3 HARD $ profit-lock floor (a peaked-green trade can NEVER close red — highest leverage, kills the $383)**, L4 entry_atr rebuild from LOCAL ledger + degrade-FALLBACK-not-skip, **L5 server-side ratcheting IBKR stop (survive dead daemon/feed)**, L6 per-contract fast calibration (MGC tightest), L7 dead-man watchdog (past max-hold/big-giveback → force-flatten+alert). Priority: L3 first, then L5, then L1/L2, then L4. Validate: shadow A/B on 250ms + weekly `ratchet_giveback_report.py`; arm L3 first. TARGET captured 28%→≥70%, excess $763/wk→<$150, zero peaked-green-closed-red. Friday report now has a RATCHET section (peak/banked/captured%/why). Related [[ratchet-fast-feed-study]] (this is the measurement it called for), [[mgc-pullback-clock-regression]]. NEXT: the MES entry_atr-orphan bug (L4).

**PROFIT-LOCK (L3+L4) BUILT+MERGED+DEPLOYED LIVE 2026-07-01** (commit d56015eb, .env FUT_PROFIT_LOCK_ENABLED=true, strategy restarted 07:25). New `profit_lock_fires` in futures_stop_logic: hard $ floor off running_extreme (arm $15, keep 50%, never-red), fires after R1/R2 before force-kill/flat-clock, ATR-FREE so it manages entry_atr-orphaned positions too. Rides existing per-tick running_extreme (L1) + server-side modify_stop_price (L5) rails — the build was small, operator was right. 8 tests + 1179 regression green. BONUS: the arming restart un-muzzled max-hold (re-anchored age) → the orphaned live MES flattened at **+$52.5** (DAYTRADE_MAX_HOLD). NEXT phases still scoped-not-built: 250ms react tightening (L2), per-contract fast calibration (L6 — MGC tightest), dead-man watchdog (L7). Watch captured% in Friday report.
