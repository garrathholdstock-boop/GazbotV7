---
name: positions-stale-empty-not-phantom
description: "2026-06-30 — a broker /positions=[] read does NOT mean flat; it can be a stale endpoint while IBKR holds REAL positions. The force-resync guard refusing = it's protecting real positions, not malfunctioning."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f8d854cc-966e-4451-ac84-f55a2a72b8da
---

2026-06-30: I diagnosed a "phantom-position tangle" — broker `positions_count=2-3` + open trail stops while `/positions` returned `[]` (read as "IBKR flat"). I concluded phantom, recommended force-resync to clear it. **I was BACKWARDS.**

**What was actually true:** IBKR genuinely held **3 real positions** (MES −1, MNQ −1, MGC +1). The broker's `/positions` ENDPOINT was returning stale-empty (the bug); its internal `positions_count` was the CORRECT side. The execution ledger showed 0 because the entry executions weren't logged (the OrderFilledV3 / order-sync gap), so ledger ≠ gateway.

**The guard saved us.** `POST /admin/reconcile/force-resync` (→ `force_resync_guarded`) REFUSED with `"gateway snapshot not corroborated by ledger — possible stale gateway; investigate"` + divergences `[[MES,-1,0],[MGC,1,0],[MNQ,-1,0]]`. That refusal was CORRECT — force-syncing to "flat" would have **wiped tracking of 3 real positions**, leaving them naked. The guard exists precisely to stop a stale-but-non-empty (or here, stale-empty endpoint vs live gateway) read from wiping the book.

**The fix = broker RESTART** (operator-authorized): the post-reconnect path rebuilds the book from a FRESH IBKR snapshot → restored all 3 positions, `positions_count == /positions == open_orders == 3`, and the stop-coverage audit re-attached a TRAIL to each (IBKR Warning 399 = trails won't ACTIVATE until RTH 08:30 CT; stop-runner backstops overnight). Safe to restart because the schema fix (LATEST_SCHEMA_VERSION=117) was in, and IBKR-flat-or-not the naked-flatten only acts on confirmed-naked.

**LESSON / How to apply:** NEVER read `/positions=[]` as authoritative "flat" when `positions_count` > 0 or stops exist — cross-check the force-resync guard's gateway-vs-ledger divergence and the broker's internal count. A guard REFUSING a force-resync is a signal there ARE positions to protect, not a malfunction. The clean clear for a stale book is a broker restart (rebuild from IBKR), not forcing past the guard. The `realized_pnl_usd` in a post-restart /positions snapshot is a re-import basis artifact, not real P&L (use canonical desk_pnl). Related [[orphan-stop-optimistic-cancel]] [[futures-order-status-sync-gap]].
