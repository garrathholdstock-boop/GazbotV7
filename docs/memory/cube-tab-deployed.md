---
name: cube-tab-deployed
description: CUBE dashboard tab v1 deployed live 2026-06-21 (schema→108); renders empty until Monday Globex capture accrues — verify then
metadata: 
  node_type: memory
  type: project
  originSessionId: 67c42436-f6c3-496d-ac98-2caeb1ac27ce
---

The CUBE dashboard tab (DAY|WEEK|REPORTS|COURTROOM|**CUBE**) — the daily-capture X-ray (regime/flow/force heatmap, 3 markets × 5 phases, per-contract drill, Claude-authored themes strip) — is **BUILT + MERGED + DEPLOYED LIVE** as of 2026-06-21. Commit `c5ebc3fb` on `main` (was `feat/cube`, both pushed). Scope: `docs/CUBE_SCOPE.md`. This is the descriptive *eyes* tab, NOT the north-star Gate Cube ([[strategy-layer-reframe]] / GATE_CUBE_SCOPE.md is still SCOPED-only).

Deploy: full suite green (8629 passed), pre-deploy backup taken, broker restart applied migrations **105→108** (schema 104→108: §286 session_regime / §287 OFI+book / §288 force features / §289 multi-horizon labels — all additive ADD COLUMN), then strategy-daytrade + dashboard restarted. No live positions touched (all 72 open ledger entries are paper).

**Capture CONFIRMED WORKING on deploy day** (Sun 06-21): `fut_signal_funnel` already carries non-null session_regime/ofi/net_atr on the weekend-open **crypto futures** (MBT/MET) — 1243 populated rows, and `/api/cube/2026-06-21` renders 1243 cycles in the Crypto×eu_session cell (regime=trending). The ~17K NULL-capture rows are the weekend-CLOSED equity-index futures (MES/MYM/MNQ, session_active=0) — expected, not a bug. Use the explicit-day endpoint `/api/cube/YYYY-MM-DD`, not `/latest` (latest mis-resolved to an empty day on deploy).

**Monday check still scheduled** to confirm the **US + Eurex** equity cells populate during the real session (only Crypto proven so far). Mechanism: local `at` job (#6, fires Mon 2026-06-22 18:05 UTC = 20:05 Paris) running `scripts/verify_cube_capture.sh 2026-06-22` (committed to the repo, HEAD 2c42da12) → telegrams the operator a ✅/❌/⚠️ verdict + appends the result here. NOT a cloud /schedule routine (those can't reach the VPS-local DB / localhost:8080) and NOT a session-only CronCreate (dies with the session). If US/Eurex cells stay empty after Monday's live cycles, the capture wiring (not the tab/migrations, which are confirmed fine) is the bug.

`/cube` page is PIN-gated (302 redirect like `/day`); `/api/cube/{day}` + `/available-days` return 200.

**Armed `at` jobs (local, session-independent; `atq` to list):** #8 `scripts/post_open_scan.sh` @ Sun 2026-06-21 22:20 UTC (post Globex-reopen desk health: services/IBKR-HEALTHY/schema-108/0-live-naked/capture-fresh/cube-200 → telegram) · #6 `scripts/verify_cube_capture.sh 2026-06-22` @ Mon 18:05 UTC (US+Eurex cube cells populate). Both committed (HEAD fb2d67fd). Pipeline proven live 06-21 (test telegram sent). Pre-existing weekend-benign: `alphabot-nightly-reset.service` fails at 21:05 (gateway closed) — leave it, self-corrects Monday.

**VERIFIED 2026-06-22:** Garrath — ✅ CUBE capture live for 2026-06-22. Funnel: 137457 rows, 137457 with regime/ofi/force. Cube grid: 149823 cycles across 12 cells. markets populated: Crypto,Eurex,US.
