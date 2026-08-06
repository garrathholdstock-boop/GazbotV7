---
name: projector-conid-dedup-scope
description: "BUILT+MERGED fix for the recurring MGC ledger phantom (deploy-pending broker+brain restart) — projector now folds on con_id not the exchange-embedding canonical"
metadata: 
  node_type: memory
  type: project
  originSessionId: f8d854cc-966e-4451-ac84-f55a2a72b8da
---

**STATUS 2026-06-30: BUILT + MERGED + DEPLOYED LIVE** (commit 46402d95, merge 08cbf3bc; deployed ~15:58 UTC via broker+brain restart, operator-authorized). Post-deploy VERIFIED: broker boot clean (schema 117), MGC projector divergence GONE (compare_projection_to_live, only pre-existing retired-crypto diffs remain on the unchanged null-con_id path), 0 EXIT_BOOK_DIVERGENCE post-restart, the stuck MGC `_tp` orphan order reconciled away, R4_ORDER_STUCK_SUBMITTED:MGC stopped re-tripping (frozen pre-restart, ages out). Deploy hit a flat window (the MGC short closed just before restart); desk resumed trading normally (new MGC long, stop-protected). 7 new + 463 regression tests pass. The recurring 3×/day phantom should now be GONE at the root — watch that it does not recur.

The recurring MGC book-vs-IBKR divergence (`EXIT_BOOK_DIVERGENCE` + `RECON_BREAK:R4_ORDER_STUCK_SUBMITTED:MGC` + `J17_PHANTOM_TRADES`, 3× on 2026-06-30, each "fixed" by a broker restart) has a confirmed root cause and a SCOPED fix.

**Root cause:** `alphabot/broker/ledger_projector.py::_exec_key` folds executions on `instrument_canonical`, which is `future:{exchange}:{symbol}:{conId}` (futures_contract.py:82) — the **exchange** is in the key. IBKR flip-flops MGC's exchange between `COMEX` (the 582-row fill history) and `CME` (the venue_correction rows), so one con_id (`732156883`, which nets to **0.0**) splits into TWO projector lots that never net. A `venue_correction` then lands on the `CME` key while the fills sit on `COMEX` → reconciles the wrong lot → residual phantom drives the divergence. Only **MGC** is split today (whole-log check); recurs whenever IBKR flip-flops the exchange string.

**Fix (operator-requested 2026-06-30):** key the fold on `con_id` when present, fallback canonical→symbol. Safe because futures = 100% con_id populated (0/5646 null), equity/crypto = 0% (647/647 null) → off-futures behaviour unchanged. Keeps FDAX/FDXM + contract rolls apart (different con_ids). No consumer indexes the key tuple — the critical one (venue_correction emitter, futures_broker_adapter.py:397-399) already buckets by con_id. Pure re-fold ⇒ self-healing history, NO migration/schema bump; deploy = broker+brain restart (FLAG-AND-WAIT) that *replaces* the papering-over restarts. Risk LOW.

Full scope: `docs/PROJECTOR_CONID_DEDUP_SCOPE.md` (+ punchlist §1). NOT built — branch `fix/projector-conid-dedup` when armed. Ties to [[futures-session-flat-exchange-routing]] (same COMEX/NYMEX/CBOT-vs-CME class) and [[positions-stale-empty-not-phantom]].
