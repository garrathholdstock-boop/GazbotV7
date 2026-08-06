---
name: exit-selector-regime-live
description: "2026-07-27 LIVE — regime-3-exit selector: every gate picks exit WIDTH by router regime at entry (aligned→wide chandelier / chop→tight / counter→k2.0)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 56db3271-178d-477c-8537-702242d72c01
---

**LIVE roster-wide on the paper desk 2026-07-27 (gazbot7 `da98af0`), operator-directed ("put it live into paper").** Every tournament gate now picks its exit **WIDTH by the router regime at entry** (frozen for the trade's life), instead of a fixed per-gate exit:
- **aligned-trend → WIDE** = `exit_chandelier_lock(start_k3.5, lock_r6, lock_k0.5)` — ride the run
- **chop → TIGHT** = `exit_chandelier(start_k1.5, min_k0.5, tighten0.75)` — bank before give-back
- **counter-trend → k2.0** = `exit_chandelier(start_k2.0, …)` — damage control

The native 1-ATR IBKR STP still owns the loss side (now fills clean via [[stop-unfilled-contfuture-root-cause]]). **Give-back overlay is OFF under adaptive_exit (gazbot7 `ae55ab6`, 2026-07-27)** — the chandelier is the sole managed profit exit (give-back was pre-empting it on abs_veto/rgv). Wiring: `SlotSpec.adaptive_exit` (default False; each gate keeps its static `exit=` as the fallback/revert), `SlotStrategy._regime_mode(side,bars)` mirrors `direction_router`'s ER_TREND/NET_MIN/WINDOW (no drift), mode stamped at OPEN in `decide()`, dispatched in `_manage()`. Set live roster-wide via `tournament_slots()` `for s in specs: s.adaptive_exit=True`.

**Why (the sweep):** `scripts/exit_selector_sweep.py` (tick-honest on capture.db, 260 realised entries 07-20..27) swept chandelier width tight→wide + the lock. Per-regime winners UNAMBIGUOUS: **ALIGNED→lock +$2382, CHOP→k1.5, COUNTER→k2.0** (a wide chandelier in chop bleeds −$3118; a tight one in aligned-trend leaves +$2000 on the table). The **regime-only** selector beats the best single fixed exit by **+$756 out-of-sample, 6-of-7 leave-one-day-out days**. The **per-gate×regime** version OVERFITS (−$512 OOS, thin cells) → use regime-only, NOT per-gate. `scripts/exit_selector_backtest.py` = the earlier 2-way (scalp vs chandelier) version.

⚠ **The aligned-WIDE magnitude leans on today (07-27), the ONE real trend day in the window** — the selector survives LODO but the wide-exit payoff wants more trend days to trust its size. Forward-validate on the next trend days. Revert = `adaptive_exit=False` roster-wide + restart (each gate → its static exit). Related: [[direction-router-live]], [[chandelier-momentum-exit-tuning]], [[sims-on-tick-price]], [[exit-architecture-scar-tissue]].
