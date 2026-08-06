---
name: orphan-stop-optimistic-cancel
description: orphan IBKR trailing stops on flat positions — broker marks the stop CANCELLED before IBKR applies it
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

**Root cause (found 2026-06-15):** a futures position that exits via a NON-bracket path (flat-clock / time-stop SELL, or a realtime-sync force-close) leaves its native IBKR TRAIL stop ORPHANED — live at IBKR on a now-flat (qty 0) position. If price hits the trail it fires and opens an UNWANTED SHORT.

Mechanism (SX7E, order 588, 08:30): the exit raced the realtime force-close (`on_fill_event: exit SELL raced the realtime force-close`). The broker cancelled the trail AND **optimistically marked it CANCELLED in its order registry** — but the cancel was racing and **IBKR never applied it** (the trail was `PreSubmitted`, a state where a cancel can be silently dropped). So the broker's books say "stop cancelled, flat, clean" while IBKR still holds the live order. The reconcile can't catch it because the registry already shows the order terminal — this is the unbuilt **Domain-B "compare IBKR open orders vs the registry, re-cancel divergent ones"** piece.

**Why it's STUCK / can't be cleared from the Claude session:** every broker cancel path (`DELETE /stops/{symbol}` → cancelled:false; `POST /orders/cancel` → 404 "no cancellable order") refuses because the registry state is CANCELLED (terminal). A separate IBKR client (ib_async readonly or not) CANNOT cancel the broker's order — IBKR ties cancel rights to the placing client (broker = clientId 0); only the broker, or `reqGlobalCancel` (which would also kill the held position's stop), can. So clearing it needs: **manual cancel in the IBKR Gateway/TWS GUI**, or a broker restart whose `reconcile_on_startup` re-reads IBKR STP orders (risky while a position is held — same class can orphan the held one).

**The systemic FIX (proposed, not built):** the exit-path cancel must CONFIRM IBKR applied the cancel before marking the order terminal (don't optimistically mark CANCELLED), AND/OR build the Domain-B reconcile that diffs IBKR's open-orders snapshot against the registry each cycle and re-cancels any IBKR order the broker believes is terminal. Relates to [[futures-trade-multiplier-recording]] Fix-1 churn (restarts + force-closes are when these races happen). DB `stops`-table rows for already-flat symbols (MNQ/M2K seen 06-15) are separate STALE LOG rows — not live at IBKR, harmless.

**2026-07-01 — NOW AUTO-HANDLED (sweep allowlist item #6):** built `scripts/ops_cancel_orphan_stops_when_flat.py` — clears flat-book orphan stops via reqGlobalCancel (clientId 88, clears cross-session orphans the broker can't), guarded by IBKR-TRUTH flat check before+after (never nakeds a real position) + cap>20=abort-flag-systemic + agent_audit log. Operator folded it into the maintenance-sweep auto-fix allowlist (no more IBKR-GUI needed — operator "i dont do anything on ibkr these days"). First live use this session cleared 5 orphan TRAIL stops (MNQ×3/MGC×1/MES×1) on a flat book. Exit codes: 0 cleared · 2 not-flat-abort · 3 incomplete · 4 over-cap.
