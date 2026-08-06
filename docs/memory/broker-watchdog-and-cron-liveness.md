---
name: broker-watchdog-and-cron-liveness
description: 2026-07-06 morning-outage fixes — broker heartbeat-watchdog ARMED (self-restart) + external cron-liveness monitor + beacon + 7-day expiry warning
metadata: 
  node_type: memory
  type: project
  originSessionId: ed1c42ef-2406-4523-9fbd-a9a07df11ff2
---

**2026-07-06 — the "restart-fixes-it must become self-healing" drop. DECISIONS §334.** Fixes the morning's ~7h broker outage (operator: "if we ever put real cash in this thing, that can't happen"). TWO independent failures:

**1. The broker FROZE (not crashed).** CPU/RAM exhaustion (shadow sim, throttled+sliced [[shadow-sim-and-desk-resource-throttle]]) starved the broker → event loop froze → heartbeat stalled 60-96s while connection read HEALTHY. The broker's own **`heartbeat_watchdog.py`** (V3 Drop 1.2.1a) DETECTED it 3× (13:05/09/11 UTC) but was **detect-only** (`WATCHDOG_AUTO_RESTART_ENABLED=False`) → couldn't act → manual restart at 13:17.
- **FIX A (LIVE):** armed `WATCHDOG_AUTO_RESTART_ENABLED=true` (.env, gitignored; broker restarted flat 18:21 UTC). 60s STALL or 120s persistent-DEGRADED → `os._exit(75)` → systemd `Restart=always` respawns. **Weekend-safe by construction:** acts only on STALL + DEGRADED; **IGNORES RECONNECTING/FATAL** (the expected weekend/IBKR-maintenance states) → no market-gating needed, no weekend restart-storm. Soak-proven (3 real detections, 0 false positives). Tests in `test_drop_1_2_1a_split_and_watchdog.py` (armed-stall→exit; armed-never-restarts-on-reconnecting/fatal). Rollback: set the .env flag false + restart broker. **A-plus BUILT+committed** (activates on next flat broker restart): market-gated stuck-RECONNECTING/FATAL restart — `futures_broker_expected_connected(now)` Globex gate (dark Sat; closed Sun<18:00 ET & Fri≥17:00 ET; closed during 17:00-18:00 ET daily halt) gates a 600s stuck-connection restart so it fires ONLY in-session, never into the expected weekend/halt states (fail-safe: no gate/raises → CLOSED). `WATCHDOG_STUCK_CONNECTION_SECONDS=600`, wired in broker `main.py`. Catches a connection-loss the STALL path misses (heartbeat keeps ticking). Deferred the activating restart because a position was open — loads at the next flat gap.

**2. The CRONS died with the Claude session** → 7h of NO sweeps, undetected (a cron can't watch the crons). All maintenance sweeps are SESSION-ONLY Claude-Code crons.
- **FIX B (LIVE, `a9e7f8a5`):** external monitor `scripts/cron_liveness.py` + `alphabot-cron-liveness.{service,timer}` (systemd, 30min — survives session death). An hourly **BEACON** cron (9th standing job, `17 * * * *`) touches `data/cron_heartbeat.json`; monitor Telegrams Garrath if stale **>5h** (300min — tolerates a long-task heads-down since crons fire-when-idle/deferred, catches a dead session within 5h vs the 7h blind spot). The broker (A) self-heals independently → a dead session pauses sweeps/reports but NOT the money path.
- **FIX C (same commit):** session crons auto-expire 7d after creation. Monitor also watches `data/cron_armed_at.json` (stamp via `cron_liveness.py armed` on each re-arm) and warns at **day 6** → restart re-arms from CLAUDE.md §8. **Deliberately warn-then-re-arm-from-§8, NOT programmatic cron delete/recreate** (that's a footgun that could strand crons).

**Ops:** on session start, after re-arming crons, run `.venv/bin/python scripts/cron_liveness.py armed`. §8 documents the beacon + the `§8-liveness` block. The beacon prompt = a one-line touch, reply "beacon ok", silent. Both markers live in `data/`. Related: [[warn-before-dashboard-restart]], [[weekend-no-flatten-no-fuss]] (why ignoring RECONNECTING/FATAL is correct).
