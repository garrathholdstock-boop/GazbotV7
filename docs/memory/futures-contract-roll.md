---
name: futures-contract-roll
description: "how to roll the futures desk forward to the next contract month (and when it's next due)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

The desk pins each contract to a dated front month in `tools/{us_futures,eurex}_verified.json`. `plan_entry`'s roll gate (`is_rollable_now`, eurex_desk.py) refuses to OPEN within `roll_days_before` of expiry (5 days index / 2 rates). So near a quarterly expiry the whole book freezes — funnel fires LONG bursts but `plan_entry` vetoes and zero orders place. This is by design; the fix is to **roll the front month forward**, not remove the gate (the gate stays — operator's call 2026-06-15, see [[backup-timeout-db-4gb]] sibling sweep context).

**How to roll (the procedure):**
1. `tools/{us_futures,eurex}_resolver.py --json --roll-buffer-days 8` — the buffer (added 2026-06-15) skips contracts expiring within N days so it picks the NEXT active month (Sep for quarterly index, next month for crude/FX). Read-only IBKR call (port 4002, clientId 88/89).
2. MERGE the `ok=True` rolled entries into the live json by key — update con_id/local_symbol/trading_class/last_trade_date/min_tick, **guard multiplier+currency** (a mismatch = wrong contract, skip it). Don't blind-overwrite: the json has more keys than the resolver and the resolver had been missing mcl/mgc/m6e/mbt (now added).
3. Restart `alphabot-market-data alphabot-broker alphabot-strategy-daytrade`; verify broker re-qualifies the new con_ids (no "No security definition"), all traded contracts `rollable=True`, strategy cycling.
4. `.bak-<ts>` snapshots of the registries are the instant rollback.

**Why:** the resolver picks "nearest non-expired," which is still the expiring front during roll week — buffer 8 forces the next month.

**2026-06-22 — ROLLED the crypto-futures trio + MGC** (were stuck on exp 20260626, in the roll window → 200+ signals/day but 0 trades since Fri 06-19): `us_futures_resolver.py --json --roll-buffer-days 7` → MBT/MET/MSL → **20260731 (Jul)**, MGC → **20260827 (Aug)**; index (Sep) + MCL (Jul-20) untouched (outside buffer). Verified field-parity (12 entries, 13 fields, only the 4 changed) then FULL-overwrote (safe now the resolver registry is complete — no missing keys). Committed 3cb6c29d (tools/us_futures_verified.json is git-tracked). **Restarted strategy-daytrade ONLY** (not md/broker): the broker qualifies conIds ON-DEMAND (`contracts_router.qualifyContractsAsync` + `executor_live` uses `intent.con_id`), md streams by SYMBOL (front-month auto-rolls at expiry), so strategy-only suffices. ⚑ WATCH the first live crypto/MGC order for "No security definition" — if it errors, restart alphabot-broker to clear (unlikely given on-demand qualify). All four `rollable_now=True` post-restart.

**NEXT ROLL DUE:** index on **Sep 2026** (exp 09-18) → roll before ~2026-09-13. **MCL** (exp 07-20) → before ~2026-07-15. **Crypto MBT/MET/MSL monthly** (now Jul-31) → before ~2026-07-24. **MGC** (now Aug-27) → before ~2026-08-20. Worth automating as a scheduled pre-expiry job (crypto rolls MONTHLY — most frequent).
