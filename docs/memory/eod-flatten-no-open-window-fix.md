---
name: eod-flatten-no-open-window-fix
description: "EOD-flatten \"didn't work\" was open→flatten churn (no no-open guard); fix on branch fix/futures-no-open-before-close, BUILT+TESTED+PUSHED, NOT deployed"
metadata: 
  node_type: memory
  type: project
  originSessionId: 892f6dcf-d148-46c5-b6fb-8c5dba881d6c
---

The futures EOD flatten "didn't work" (operator 2026-06-18 night) = the flatten fires fine, but the entry path had NO session-end awareness, so the strategy re-opened positions straight through the 22:50-Paris flatten (open→flatten churn) until the exchange itself closed at the Globex halt. Live evidence: MBT/MYM/M6E shorts opened 20:50–21:02 UTC, each instantly DAYTRADE_SESSION_END_FLAT'd; one MBT opened+killed at 21:02:00.

Root: `NO_OPEN_MINUTES_BEFORE_CLOSE` was defined on both desks (eurex_desk, us_futures_desk) but wired NOWHERE (the long-flagged "NOT built" guard).

Fix on branch **`fix/futures-no-open-before-close`** (`fec2b3cc`, pushed), BUILT+TESTED, **NOT deployed** (gate: operator go — entry-path change is flag-and-wait; operator was asleep):
- `futures_broker_adapter.no_open_due()` reuses `session_end_flat_due`'s DST-correct tz logic.
- `EurexEntryDriver` gains a `desk` param; `run_once` suppresses the bracket submit in the no-open window (plans + funnel capture still run).
- `NO_OPEN_MINUTES_BEFORE_CLOSE 30→15` both desks → no new opens from 22:45 Paris, 5 min before the 22:50 flatten. Flatten time unchanged.
- +3 tests, 0 new ruff/mypy/test-failures (49 pre-existing futures-test failures = registry rot, unchanged).

Operator's cadence: no buys from 22:45 Paris, flatten 22:50. DEPLOY = `git merge fix/futures-no-open-before-close` to main + restart `alphabot-strategy-daytrade`; must be live before tomorrow's 22:50-Paris flatten. §4.5 ritual on main `e3f7efda`; full record HANDOVER_66 addendum. Upstream enabler is the OrderFilledV3 emission gap (see [[futures-order-status-sync-gap]]).
