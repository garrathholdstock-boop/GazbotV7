---
name: daytrade-flat-clock-20min
description: "exit_reason DAYTRADE_FLAT_CLOCK is the 20-min stale-position time-exit, NOT the 22:00 session-end flatten — a ~20-min exit is normal, don't alarm"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

`exit_reason = "exit:DAYTRADE_FLAT_CLOCK"` is the **20-minute stale-position time-exit** (a legacy equity mechanism, still active and applied to FUTURES). It is NOT the EUREX session-end flatten (`eurex_desk.SESSION_END_FLAT_LOCAL = "22:00" Berlin`). So a futures position that opens and closes ~20 minutes later via `DAYTRADE_FLAT_CLOCK` is **working as designed** — operator confirmed 2026-06-15 ("it's fine").

**Don't false-alarm in a maintenance sweep:** seeing a EUREX (or US) position flat-clocked mid-session — e.g. SX7E opened 14:00:07, closed 14:20:09 UTC — is the 20-min exit, not a premature session flatten or a restart artifact. The ~20-min hold is the tell. (I raised this as a "6h-early flatten" once; it was a misread of the reason name.)
