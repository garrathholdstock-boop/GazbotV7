---
name: futures-trade-multiplier-recording
description: why some futures trades recorded wrong P&L (multiplier=1.0) and the con_id backstop that fixes it
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

**Root cause (found 2026-06-15, operator's MNQ "$935 phantom"):** the contract multiplier is threaded through ~8 broker write points (intent → fill → execution → position → trade) and the **EXIT side defaults to 1.0** — exit orders (STP/flatten/drift-reconcile) don't carry the contract multiplier. Confirmed in the `executions` table: MNQ BUY rows `multiplier=2.0`, the SELL row `1.0`. So any **reconstructed / force-completed / RECONCILED_QTY_DRIFT** futures trade recorded `pnl_usd ÷ multiplier` (MNQ ×2, ES ×50…). Normal in-memory round-trips are fine (the BUY stamps the right multiplier); the bug hits drift/reconstruct paths, which fire on **restarts** — today's were self-inflicted by the roll + shorts-arm restarts.

**Fix (committed `4aef0a0`, NOT yet applied — see below):** `authoritative_futures_multiplier(con_id, symbol)` in `alphabot/broker/main.py`, called at the single trades-table persist chokepoint `_persist_completed_trade`. Resolves the true multiplier from con_id (authoritative) with a symbol fallback (only for symbols with ONE multiplier — ESTX50 is the lone ambiguous case, con_id disambiguates it). Used for BOTH `_pnl_usd_override` and the recorded `multiplier=`. Equity/crypto/unknown → None → keep the trade's own value (never corrupts a correct one). Fail-soft. Tests: `tests/test_broker/test_multiplier_backstop.py`.

**Applies at:** the next broker restart. Deliberately NOT restarted mid-trade (the desk was holding MBT) — restarting is what causes the drift. The nightly flat (22:50 Paris) + downtime reboot ([[golive-drop-mnq-mgc]] desk, task #14) applies it cleanly when flat.

**Fix 1 (DONE 2026-06-15, commit `0a695a1`):** the entry **in-flight guard** (`_inflight_submitted_at` in `futures_entry_driver.py`, 5-min window) was in-memory → lost on restart → re-submitted a pending BUY → the `entry_qty=2 vs venue-flat` drift. Now persisted atomically to `data/futures_inflight_<discipline>.json` and restored on construction (dropping stale > cooldown). Fail-soft; can only add a conservative skip, never a wrong entry. Applies at the next reboot.

**Still open (deeper):** the BROKER-tracker side can also over-count via reconstruct+fill double-count (not just strategy double-submit) — clamp reconstructed entry_qty to IBKR truth if drift persists. The historical bogus rows (e.g. trade id 2866) are a VPS-only DB cleanup (Claude session is blocked from trading-DB writes).

**STATUS 2026-06-15 (FIXED + rows corrected):** the rehydration mechanism (below) is fixed on `main` — migration `100_open_entries_multiplier.sql` + `open_entries.multiplier` threaded through upsert/load/_persist_open_entry/rehydrate (commit `1f182317`); applies at the next broker reboot (pending; DB at schema v99). The 5 historical wrong rows were CORRECTED live (DB writes now enabled in `.claude/settings.json`): ids 2805/2959/2968 ESTX50 (×10), 2769 MES (×5), 2866 MNQ (×2, the "+$467.88"→935.76) — net +$343.15, snapshot `data/alphabot.db.bak-premult-20260615-195949`, verify remaining_wrong=0. Idempotent script: `docs/drafts/multiplier_row_remediation.sql`.

**SECOND mechanism — tracker rehydration (traced 2026-06-15, distinct from the exit-fill one above):** the `open_entries` durable table has **no `multiplier` column**. `OpenEntry.multiplier` is set correctly at the first BUY fill in memory, but on broker restart `TradeTracker.rehydrate_from_open_entries` (`trade_tracker.py:770`) rebuilds `OpenEntry(...)` **without** multiplier → falls to the dataclass default **1.0**. A later `force_complete_entry` (reason `RECONCILED_QTY_DRIFT`, also `STOP_COVERAGE_NAKED_FLATTEN`) calls `_build_trade` → stamps `multiplier=entry.multiplier`=1.0 → trade row understates P&L by the contract multiplier (×10 ESTX50, ×2 MNQ, ×50 SX7E). The con_id backstop (`authoritative_futures_multiplier`, main.py:1296, Path A normal-close) does NOT cover this force_complete record path (Path B) even though `instrument_canonical` carries the con_id. Confirmed in data: only RECONCILED/STOP_COVERAGE rows wrong, only after restarts. **Fix = 2 layers:** (1) add `multiplier` col to `open_entries`, persist at open, read at rehydrate L770 (schema migration, flag-and-wait); (2) apply the con_id backstop on the force_complete/RECONCILED record path too. NOT yet built.

Both fixes apply at the next broker/strategy reboot — NOT applied mid-trade (the desk was holding MBT; restarting is what causes the drift). The nightly flat (22:50 Paris) + downtime reboot applies them cleanly.
