---
name: pipeline-health-monitor-the-mechanism
description: "Sweeps must monitor the live pipeline MECHANISM, not just outcomes — every safety-net activation is an alarm; pipeline_health check is live in the 10-min monitor"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3c5e04a7-ccf2-4bdb-be9b-60270fb55691
---

2026-07-15 operator (frustrated — a dead pipeline blocked the desk ~8h undetected): **"these things can't just sit there blocking the system for hours — why didn't we know? we do sweeps all night. sweep the WHOLE system (order pipeline + DB-recording pipeline) for health all the time; if something dies overnight, auto-restart."**

**Why:** the IBKR fill stream (`OrderFilledV3`/`execDetailsEvent`) wedged at 04:37 (Error-1100) and stayed dead ~8h. Every fill routed through the `realtime-sync` FALLBACK (force-closes the position book, writes NO trades row) → every close DROPPED → swept up ~2min late by `dropped_trade_backfill` as `RECONSTRUCTED_BACKFILL`. **Every existing check PASSED the whole time** — P&L correct, positions matched, `reconciled_rows=0` — because the safety nets kept every OUTCOME correct while the MECHANISM was dead. Broker restarts didn't fix it (the wedge was at the GATEWAY exec stream); the fix was `docker restart alphabot-gateway` → broker → MD bounce → strategy.

**The principle to apply:** monitor the MECHANISM, not just the outcome — and **treat every safety-net activation as an ALARM, not a silent save.** The desk is layered with nets (ledger truth, dropped-trade backfill, reconcile, realtime-sync fallback, force-flatten) — which is exactly why a dead primary can run for hours looking healthy. If a backup did the work, the primary failed, and someone gets told.

**How to apply:**
- BUILT + LIVE (commit 809c46bf): `pipeline_health()` in `scripts/execution_monitor.py`, run every 10 min by `alphabot-execution-monitor.timer` (`--persist --alarm`). Two fail-soft signals: DB (recent US-futures closes recorded by the backfill net vs the live path; ≥60% = dead) + JOURNAL (`dropped_trade_backfill: recorded` firings; fills via `realtime-sync[Fix1]` fallback with `OrderFilledV3` silent = stream WEDGED). CRIT → Telegram Garrath immediately (reuses the integrity-alarm path [[execution-integrity-standing-check]]). Validated against 07-15 as a known-positive fixture (240m window → CRIT; would have paged at ~04:47 not 08:48).
- Report a `PIPELINE_HEALTH:` line every sweep alongside `EXECUTION INTEGRITY`.
- AUTO-REBOOT BUILT + INSTALLED, DISARMED (commit 0135bee6): `scripts/pipeline_auto_reboot.py` runs as ROOT via `alphabot-pipeline-reboot.timer` (5-min; the alphabot monitor can't docker/systemctl). Guards, ALL required: `FUT_PIPELINE_AUTO_REBOOT_ENABLED` armed (`.env`, DEFAULT FALSE = pure no-op) + pipeline CRIT now + a prior CRIT within 20m (confirmed) + no reboot in 3h (cap) + FLAT book (else alarm for manual). Does `docker restart alphabot-gateway` → broker → MD bounce → strategy → verify `execDetailsEvent subscribed`; Telegram before+after. Read-only on the DB + a file marker for cap (root must never write the alphabot-owned SQLite). **To ARM: set `FUT_PIPELINE_AUTO_REBOOT_ENABLED=true` in `.env`** (next 5-min tick picks it up; no restart). Future GAP: a broker `/health` `execDetails subscribed` field (catch a dead stream with ZERO trading). Full analysis: `docs/PIPELINE_HEALTH_SWEEP_GAP_ANALYSIS.md`.
