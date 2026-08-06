---
name: estx50-fesx-short-tangle
description: "ESTX50 full-size FESX (x10) was traded alongside the micro; mis-routed flattens + drift-detector miscancellation built a runaway -11 short; broker is long-only and CAN'T clear shorts — must flatten on IBKR directly"
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

2026-06-16 incident. The desk had BOTH `estx50` (full-size FESX, conId 655095977,
mult 10, ~€63k notional) and `estx50_mc` (micro FSXE, conId 840885640, mult 1) in
`ACTIVE_CONTRACTS` (eurex_desk.py:57/64). A full-size long got flattened repeatedly,
but the **drift detector kept marking the FILLED flatten SELLs as CANCELLED
'drift_reconciled'** (misreading a fill as a vanished order), so the book never
recorded them, stayed "+1", and the flatten loop kept selling into the position →
a runaway **−11 FESX short** (−€6.3k), invisible to the dashboard (which showed the
DB's phantom +1).

**Two structural facts to remember:**
1. **The broker is a long-only engine and cannot clear a short from inside.** It
   refuses to import a short (reconcile.py:1171 "SHORT import not allowed … Flatten
   on IBKR directly first") and refuses to re-attach/cover (B5, reconcile.py:2899 —
   a SELL stop deepens a short → it latches reconcile_paused + CRITICAL-logs). A
   broker-routed BUY-to-close is also blocked by gate_market_open (ESTX50 is
   mis-mapped to SMART in exchange_for_symbol, closed until 13:30 UTC). **The only
   way to clear an orphan short is to act on IBKR directly.**
2. **How to do that without TWS:** a direct-gateway ops script — connect as a spare
   clientId (88; broker=0, md-daemon=14), conId-pinned MKT orders, hard-abort unless
   positions match expectation. Pattern in `scripts/ops_estx50_unwind_20260616.py`
   (and `ops_ibkr_global_cancel.py`). The broker (master clientId 0) sees the fills
   and venue_corrects its book to flat; stop-coverage auto-cancels the orphan trail.

**Recurrence guard (pending operator OK):** drop `estx50` (full-size ×10) from
ACTIVE_CONTRACTS — micro-only, consistent with the drop-the-big-contracts philosophy
([[golive-drop-mnq-mgc]]). The deeper bug is the drift-detector miscancelling fills.
Related: [[orphan-stop-optimistic-cancel]], [[futures-contract-roll]] (conId-by-roll).

**RECURRED 2026-06-18 (~05:34 UTC) — now on the MICRO.** Even micros-only, the tangle
came back: estx50_mc (conId 840885640, mult 1) ran to a **−9 short**, MASKED by a frozen
reconcile/stop-coverage publish (the broker's order-status sync degraded ~22:00–22:46 UTC
06-17 — OrderFilledV3 emission gap, ~267 stuck-SUBMITTED, duplicate trade rows: one entry
coid `eurex-estx50-fe6cb4f` booked 13×, faking +$347 long-profit while the position was
actually going short). The book showed +1 long; IBKR truth was −9. A **broker restart
(operator-approved)** re-synced to truth and EXPOSED it — restart did the right thing.
Post-restart the broker oscillates pause↔resume, issues cover-BUY×9 that won't fill (fill
accounting "BUY-total=10 vs IBKR −9, off by 19"), can't self-clear → needs the clientId-88
IBKR-direct flatten. **Lesson: a frozen reconcile masks a runaway short → the dashboard/book
lie; periodic broker restart (or a liveness check on the coverage-publish `at` timestamp)
catches it. Watch the `/stops/coverage` "at" freshness as a tell.**

**RESOLVED ~06:14 UTC.** The flatten was MESSY: the operator-authorised cover raced the
broker's OWN cover-BUYs (they DO reach IBKR as clientId 0 and STACK) → over-shot −9 → **+9
LONG** at the 06:00 EUREX open; accounting corrupted to "qty=73 vs IBKR 9", thrashing.
Operator ran `systemctl stop` (NOTE: the agent is BLOCKED from `systemctl stop` broker —
only `restart` is permitted; and the broker AUTO-RESTARTS via systemd, so a manual stop does
NOT hold it down). That auto-restart did the job: reset accounting from IBKR truth AND
adopted the resting clientId-0 SELL orders, which filled +8→0 as the near-empty FSXE micro
book (bidSize 1!) trickled liquidity. Verified end state: ESTX50 flat (0), no orders,
accounting clean, desk resumed 6/6 covered, coverage publish fresh. **LESSONS: (1) flattening
a futures drift by hand RACES the broker's own reduce/cover orders (which reach IBKR) — the
clean path is restart-to-reset-accounting, NOT an order war. (2) FSXE micro is near-illiquid
off-peak (bidSize 1) — MKT covers just sit. (3) ESTX50 realized P&L after this churn is
fiction — reconcile vs IBKR executions. Ops script: `scripts/ops_estx50_unwind_20260618.py`.**
