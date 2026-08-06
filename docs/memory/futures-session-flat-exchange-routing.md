---
name: futures-session-flat-exchange-routing
description: "BUG found+fixed 2026-06-23 (commit 6ccbcba0, DEPLOY-PENDING strategy restart): US futures on COMEX/NYMEX/CBOT (MGC/MCL/MYM) were routed to the EUREX desk by _desk_for_position (matched only exch=='CME') → flattened against Eurex's 21:50-08:00 Berlin window = 19:50-06:00 UTC, blanketing the whole US overnight Globex session → continuous SESSION_END_FLAT churn all night, cutting overnight shorts short"
metadata: 
  node_type: memory
  type: project
  originSessionId: 67c42436-f6c3-496d-ac98-2caeb1ac27ce
---

The 2026-06-23 "session-flat exits all night" report. `alphabot/strategy/futures_broker_adapter.py:_desk_for_position` routes a held futures position to its desk's session config by the canonical-id exchange (`future:EXCHANGE:SYM:CCY:conid`). It matched ONLY `exch == "CME"` → `us_futures_desk`; everything else fell through to the `eurex_desk` DEFAULT.

US futures trade on **four** CME-Group exchanges, not just CME: CME (MES/MNQ/M2K + crypto MBT), **CBOT** (MYM), **NYMEX** (MCL), **COMEX** (MGC). So MGC/MCL/MYM were flattened against the **Eurex** session — flatten window `21:50→08:00 Berlin` = **19:50–06:00 UTC**, which covers the entire US overnight Globex session. The futures adapter fired `DAYTRADE_SESSION_END_FLAT` every ~5s all night (120/321/1411/1975/1398 attempts per hour 00–04 UTC) on MGC/MCL/MYM, recording 30 cut-short overnight scalp shorts (net only +$36) on a strongly trending-down night where they should have run. MES/MNQ/M2K (CME) were UNAFFECTED — the tell that pinpointed the missing exchange keys. The churn also interacted with the same-night [[futures-order-status-sync-gap]] broker freeze (many flatten-BUYs got stuck SUBMITTED, so some shorts accidentally survived to profit).

**FIX (commit 6ccbcba0, main, DEPLOY-PENDING a strategy-daemon restart):** `_desk_for_position` now routes a `_CME_GROUP_US_EXCHANGES = {CME, CBOT, NYMEX, COMEX, GLOBEX}` frozenset → `us_futures_desk` (all share the 17:00-ET Globex daily halt). Verified: MGC `session_end_flat_due` @00:07 UTC now False (was True via eurex); the real 17:00-ET flatten @20:55 UTC still True. 6 routing tests in test_drop_futures_broker_adapter.py + full adapter suite (40) green. **Bug is DORMANT during the day (06:00–19:50 UTC) and re-triggers at the 19:50-UTC Eurex window — deploy the strategy restart before then.** Rollback = revert the frozenset to `=="CME"`.
