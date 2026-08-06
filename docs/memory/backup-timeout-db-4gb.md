---
name: backup-timeout-db-4gb
description: nightly alphabot-backup.service times out — DB grew past what gzip can do in the 30-min systemd limit
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

As of 2026-06-15, the nightly `alphabot-backup.service` (V3 §Y30a, runs ~03:34 UTC daily) FAILS with `Result=timeout`. The trading DB reached ~4.8 GB and `sqlite .backup` + gzip overruns `TimeoutStartUSec=30min` (killed after consuming ~25 min CPU), leaving a ~2.7 GB uncompressed half-file in `/home/alphabot/backups/`. Last GOOD backup before it started failing: `alphabot.db.2026-06-14-0332.gz` (834 MB compressed).

**Why:** structural, not transient — re-triggering the timer just re-fails and burns CPU near the session open. The maintenance sweep should NOT auto-retry it.

**How to apply:** real fix is a config change (flag-and-wait, not in the sweep auto-fix allowlist) — raise `TimeoutStartUSec`, and/or switch to a faster path (e.g. `VACUUM INTO` then background `zstd -1` instead of gzip). Also clean the stale 2.7 GB partial. Flagged to Garrath via heartbeat 2026-06-15 06:43 Paris; awaiting his OK. Until fixed, future sweeps will keep seeing `alphabot-backup` in `systemctl --failed` — treat as KNOWN, not new.
