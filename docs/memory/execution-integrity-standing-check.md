---
name: execution-integrity-standing-check
description: Execution integrity is a first-class standing check — reliable Telegram on rejects / submitted-but-no-fill; run it every sweep
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3c5e04a7-ccf2-4bdb-be9b-60270fb55691
---

2026-07-14 operator (after the desk was silently DEAD for ~4h — every entry rejected/IOC-cancelled while the through-rate read 100% because it counted SUBMITS not fills): **"execution integrity has to be in your main sweeps. telegram me if i need to act."**

**Why:** great signals + broken execution = no $, and it can be INVISIBLE. On 07-14 two stacked bugs (short cap 1 vs 2-lot sizing → `gate_sell_quantity_short_cap` reject; MKT entry vs native trail → IBKR Error 328 bracket collapse) took the desk to ZERO fills for 4h and nothing alarmed.

**How to apply:**
- The enforcement is the **`alphabot-execution-monitor.timer`** (systemd, every 10 min, `scripts/execution_monitor.py --minutes 30 --persist --alarm`). `_integrity_alarm` CRITs on the two REAL failure signatures from `fut_entry_audit` + ACTUAL fills: (1) any broker **REJECT**, (2) **≥3 entries submitted but 0 filled**. CRIT → Telegram Garrath. This is the reliable "telegram me if I need to act" (fixed 2026-07-14, commit 267a9190; the old through-rate counted submits as success and never fired).
- **Every LIGHT/FULL sweep**: run `scripts/execution_monitor.py --symbols MNQ --minutes 60` and report a 1-line `EXECUTION INTEGRITY:` (through-rate + fills + rejects + [exact]/[inferred]). It is a standing sweep check even though it is not in the injected cron prompt — the sweep crons are too large to safely recreate, so the monitor timer + this practice are the mechanism.
- The exact per-signal outcomes live in `fut_entry_audit` (submitted / rejected / blocked-by-`<reason>` / observe_only + intended price), surfaced on the `/mnq` EXEC tab. See [[golive-shadow-momentum-to-paper]] (the live gate) and the execution-monitor build (Phases 1/1.5/2, SESSIONS 2026-07-14).
