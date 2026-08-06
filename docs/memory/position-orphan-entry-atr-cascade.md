---
name: position-orphan-entry-atr-cascade
description: 2026-07-01 ROOT-CAUSED — the "orphan messing up MES" = IBKR reqExecutions returning EMPTY cascades to a fully-unmanaged position (muzzled max-hold + wide fallback stop + no ratchet); local ledger has the truth; fix SCOPED
metadata:
  type: project
---

2026-07-01 dug into the orphan (the live MES that peaked +$40 then gave it all back with no ratchet). ROOT CAUSE = after the 04:31 gateway zombie, **IBKR `ib.fills()`/`reqExecutions` returns EMPTY** for a held symbol (persistent after-effect). That single broker fault cascades:
1. no IBKR fill → no `entry_exec_id` → reconcile recovers opened_at from DB fallback → §278 age-anchor falls back to now() EVERY cycle → **max-hold + flat-clock MUZZLED** (the MES sat 2h24m past its 2h max-hold, never flattened).
2. `entry_atr` is **recomputed LIVE each tick from bars, never persisted** (futures_broker_adapter.py:429; positions table has no entry_atr col) → when bars briefly unavailable (zombie/post-restart) → None → **initial stop drops to wide 0.5% fallback (MES 7556=$189)** + ATR ratchet degrades.
3. position in reconcile-limbo churning every ~30s, under-managed → $40 peak → ~breakeven, nothing fired.
**The truth is LOCAL** — the `executions` ledger has every fill IBKR is missing (verified MES+MNQ). So the fix is viable.

FIX SCOPE `docs/POSITION_ORPHAN_FIX_SCOPE.md`: **F1** rebuild entry_exec_id+opened_at from the LOCAL executions ledger when ib.fills() empty (un-muzzles the age exits — highest leverage); **F2** persist entry_atr at fill time (compute from bar_history at exec_time) so stop+ratchet survive bar gaps/restart; **F3 DONE** = the ATR-free profit-lock backstop ([[ratchet-giveback-leak-and-robustness]]) already protects it; **F4** dead-man watchdog force-flatten any position past max-hold; **F5** broker fills-stream health-check + auto-resubscribe (a broker restart re-establishes ib.fills() now). Priority F1→F4→F2→F5. Distinct from the give-back leak (that's firing-miss on healthy positions; THIS is a position dropping out of management). The current held MES is still orphaned but profit-lock-protected (non-urgent). Related [[futures-order-status-sync-gap]], [[positions-stale-empty-not-phantom]].
