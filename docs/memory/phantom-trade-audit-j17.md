---
name: phantom-trade-audit-j17
description: "BUILT+DEPLOYED 2026-06-23 (commits 01d4bc9b+73ea8114): J17 brain-sweep phantom-trade audit — validates the trades table against the executions ledger (ledger_projector.project) every 10min/24h-lookback. Closes the gap that let OrderFilledV3-gap reconcile phantoms (RECONCILED_QTY_DRIFT, wrong side/prices) go undetected twice in a day. DETECT-ONLY → WARN alarm J17_PHANTOM_TRADES with phantom ids + net P&L correction"
metadata: 
  node_type: memory
  type: project
  originSessionId: 67c42436-f6c3-496d-ac98-2caeb1ac27ce
---

The trades-level equivalent of `ledger_shadow` (which only checked open *positions* vs the ledger). `alphabot/brain/phantom_trade_audit.py::audit_trades_vs_ledger(conn, since_iso, execution_mode)` folds the immutable executions ledger through `ledger_projector.project` → authoritative round-trips, then diffs recorded `trades`:
- **PHANTOM** = a recorded RECONCILE-tagged trade (`exit_reason` starts with RECONCILED) that matches NO projected round-trip (wrong side/prices / fabricated). Only reconcile-tagged rows alarm — a legit SIGNAL_SELL/RATCHET trade the projector pairs differently is a VWAP/pairing nuance, not a phantom (the #3886 false-positive that drove commit 73ea8114).
- **MISSING** = a projected round-trip with no recorded trade (a dropped real scalp).

Match key: symbol + side + entry≈ + exit≈, **tight 0.5bp price tolerance** (min 1¢) so a corrupted price can't hide in the band (the MBT ~63000 phantom did at 0.05%). EUR/EUREX desks EXCLUDED from the diff (ledger is contract-currency, live pnl_usd is USD — needs an FX step, same caveat as ledger_projector).

Wired as **brain sweep J17** (`alphabot/brain/loops/sweep.py::_j17_phantom_trades`, in the J8/J9/J10/J16/J17 tuple, runs every SWEEP_INTERVAL_S=600s, 24h lookback). **DETECT-ONLY** by design: raises WARN `J17_PHANTOM_TRADES` (category STATE_DRIFT) with `phantom_trade_ids` + `net_pnl_correction` in details; self-clears when clean. It does NOT auto-write trades — the broker is the single DB writer, and (as the SIGNAL_SELL false-positive showed) not every flag is a clean auto-correctable phantom. The operator applies the fix with a broker-stopped reconcile script. **Validated live 2026-06-23:** caught all 6 of that day's phantoms PLUS 4 older 06-22 ones a manual pass had missed (net +$250). See [[futures-order-status-sync-gap]] for the incident; correction tool pattern = scripts/reconcile_phantom_drift_trades_20260623.py (DELETE phantom ids + INSERT missing reals, dry-run/--commit/backup/broker-stopped guard).

NOTE on the J-rule numbering: the stuck-broker alarm added the same day took J14 by mistake (J14 was already `_j14_capture_health`) and was renamed **J16** (commit 9384e956). J17 is the next free number.
