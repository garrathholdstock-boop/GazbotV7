---
name: weekend-no-flatten-no-fuss
description: "Sat/Sun = markets closed: NO flatten happens, broker gateway FATAL is EXPECTED, open positions held over the weekend are normal — maintenance sweeps must NOT alarm/buzz/act on any of it"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b98efc3a-63db-4236-bd2a-69cc1a89a6f2
---

Operator (2026-06-20, Sat night): *"it's saturday night, no flatten happening. note that down for our
schedules. nothing needed like that on saturdays and sundays."*

**On weekends (Sat + Sun), markets (Globex/Eurex) are CLOSED. Therefore, as NORMAL — not faults:**
- The IBKR gateway is down → broker `connection_state=FATAL` (socket to :4002 refused, "exceeded 10 reconnect
  attempts"). This is the weekend closure, NOT a new incident. The `HYGIENE_BROKER_UNHEALTHY:ibkr` CRIT trips
  all weekend — carried/known, do not escalate unless it persists PAST Globex reopen.
- NO session-end flatten runs. Positions can sit OPEN across the weekend (e.g. M6E 1 lot on 2026-06-20). That
  is expected — do NOT flag a held weekend position as a missing-flatten or naked-risk problem.

**Why:** can't trade or manage stops when the venue is closed; nothing to fix until Globex reopens (~Sun 22:00
UTC). Acting would be noise.

**How to apply:** weekend maintenance sweeps → pre-flight will fail on the FATAL gateway → READ-ONLY, no
fixes (correct, expected). Send NO heartbeat for the weekend-closure FATAL or weekend open positions (it's not
new and not actionable). Only buzz on a GENUINELY new, actionable problem. Re-audit stop coverage on held
positions at the Sunday Globex-reopen restart, not before. Ties [[backup-timeout-db-4gb]] (other known/carried
weekend-quiet conditions).

**★ SATURDAY-NIGHT IBKR MAINTENANCE — DON'T RESTART THE DESK (operator 2026-07-25):** IBKR runs weekend
maintenance Saturday nights, so the broker accepts a connection + "Logged on to server version" but the
POSITION SYNC hangs ("Synchronization complete" never logs) → `systemctl restart gazbot7-tournament` TIMES OUT
(Type=notify never gets READY=1) → systemd crash-loops, each attempt re-grabbing clientId 0 and stalling. **A
restart during Sat-night maintenance can leave the desk stuck 'activating'.** RECOVERY (worked 2026-07-25): a
clean `systemctl stop` → wait ~15s (lets IBKR release clientId 0) → ONE `systemctl start` synced immediately.
**RULE: don't do restart-requiring deploys on Saturday nights — schedule them for Sunday (before the ~22:00 UTC
reopen) or another day.** If a restart is unavoidable and hangs, don't hammer it — clean stop, wait, single start.
