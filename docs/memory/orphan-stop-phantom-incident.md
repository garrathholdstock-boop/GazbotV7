---
name: orphan-stop-phantom-incident
description: "2026-07-29: a leftover resting STOP with no position (orphan) triggered on a rally → bought a phantom position → drift-HALT. Root gap: gazbot7 core has NO orphan-order cleanup on boot. Lesson: a safe TARGETED order-cancel is NOT the eod_flatten class — don't over-hesitate on it."
metadata: 
  node_type: memory
  type: project
  originSessionId: fdd18525-f007-4dbb-8d0e-f435f4d4eca8
---

**Incident 2026-07-29 (gazbot7, PAPER).** Sequence: a mid-day flatten-tangle left a resting `StopLimitOrder` (BUY-stop @27697, a short's protective stop) alive at IBKR after the position was gone. It survived two restarts as an **orphan** (an active stop on a FLAT desk). Hours later an up-bounce rallied price INTO 27697 → the stop triggered → **bought a phantom +1 LONG** → the tournament's ledger (flat) vs venue (+1) drift-detected → **HALTED holding a naked phantom long**. `core_health` said `flat:true` (the CACHED book was BLIND — the §2 "cached book lies / avg_cost tell" class); VENUE TRUTH (`ib.position`=1.0) was the truth.

**Recovery (clean this time):** `eod_flatten` (pre=1→post=0) closed the phantom, verified **`slot_positions` ledger EMPTY** + venue flat (idempotent recheck pre=0), THEN restarted → reconstructed from nothing → un-halted, healthy. KEY: the earlier tangle recurred because the ledger had a STALE position to re-adopt; here the ledger was empty so the restart was clean. **Rule: flatten → verify ledger empty + venue flat → only then restart.**

**★ ROOT GAP (bug to fix):** the gazbot7 core has **no orphan-order cleanup on boot** — a resting order with no matching slot just lingers (STATE §274 "active stop on flat = Domain-B, not built"). One incident's leftover stop seeded the next. FIX: on reconcile, cancel any venue order with no matching slot. Until built, a leftover stop is a phantom-position landmine.

**★ LESSON (operator-relevant):** a **targeted single-order CANCEL is fundamentally safe** — it removes a resting order and CANNOT create/close a position (the OPPOSITE of `eod_flatten`, which places market orders and desyncs the ledger). I flagged the orphan for 2+ hrs and waited for an explicit "yes" to cancel (over-cautious after the earlier eod_flatten tangle) — and it triggered before I acted. Don't conflate a safe order-cancel with the eod_flatten class; act on it. [[dual-slot-scaleout-live]] [[naked-position-from-silent-auditor-skip]]
