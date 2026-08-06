---
name: brain-retire-janitor-migration
description: Brain-retire Part B — the 5 J-rules now run from the janitor too (Phase 1 done); Phase 2 (stop/disable brain) is OPERATOR-gated
metadata: 
  node_type: memory
  type: project
  originSessionId: ed1c42ef-2406-4523-9fbd-a9a07df11ff2
---

**2026-07-06. Retiring the `alphabot-brain` service. DECISIONS §331 (Part A) + §335 (Part B Phase 1). Scope `docs/BRAIN_RETIRE_SCOPE.md`.**

- **Part A DONE:** the 4 Claude-API loops off by default (`BRAIN_CLAUDE_LOOPS_ENABLED=false`, `4abdf481`) — Claude Code's sweeps/nightly/Friday cover them.
- **Part B Phase 1 DONE + LIVE (`aabf878f`):** the 5 load-bearing J-rules (J17 phantom-audit, J10 stop-coverage, J16 stuck-broker, J13 orphan-bracket, J9 cycle-stall) now ALSO run from **`alphabot-janitor`** via **`alphabot/maintenance/j_rules.py`** (imports the exact brain functions → zero drift, byte-identical `rule_key`s; a 4th janitor loop, `J_RULES_INTERVAL_SECONDS`=600). **ADDITIVE** — the brain still runs its own copy; `system_alarms` is upsert-by-rule_key so parallel firing just bumps `last_seen` (no dupes, no gap). Dropped J8/J12 (dead on futures). Verified `ran=5 errored=0`. Tests `tests/test_janitor_j_rules.py`.
- **⚠️ Phase 2 = OPERATOR RUNS IT (hard-denied to Claude, CLAUDE.md §6):** `sudo systemctl stop alphabot-brain` then `sudo systemctl disable alphabot-brain`. Do it after a few days' soak confirms the janitor J-rules fire clean. Frees ~0.9G RAM + drops the :8000 bind. THEN update the sweep prompts (drop the `brain(:8000)` health check) + retire `alphabot-brain-heartbeat.timer`.
- **Phase 3 (later):** archive `alphabot/brain/` to `_RETIRED/`, re-home the J-rule bodies into `alphabot/maintenance/` (they currently IMPORT from `brain/loops/sweep.py` — that coupling breaks only when brain/ is archived).

**If you edit a J-rule before Phase 3:** it lives in `brain/loops/sweep.py` (the janitor imports it). Related: [[broker-watchdog-and-cron-liveness]] (the other 2026-07-06 self-healing drop).
