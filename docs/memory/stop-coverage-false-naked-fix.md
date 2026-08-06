---
name: stop-coverage-false-naked-fix
description: "stop-coverage audit false-naked flatten (snapshot-lag) — targeted re-confirm fix DEPLOYED 2026-06-18 (main 3ce58255); was the gate for futures-shorts re-arm"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7f83ba46-9480-4d61-afc1-9ca55897e71f
---

The stop-coverage audit (`alphabot/broker/stop_coverage_audit.py` + `_handle_naked_flatten` in `reconcile.py`) decides "naked" from a single per-cycle BULK `reqAllOpenOrdersAsync` snapshot. During session-close churn that snapshot can transiently DROP a live GTC trail → a healthy position reads naked for `FLATTEN_CONFIRM_CYCLES`(2) consecutive cycles → audit escalates to MARKET-EXIT (flatten). **2026-06-17: MSL flapped naked this way; only the oversell guard (`gate_sell_quantity`) stopped the bad flatten; it re-read `covered:true` a minute later.** This is the venue-truth lag that keeps the Domain-A soak amber (§263) — the futures-shorts re-arm blocker.

**Why it gates shorts:** the false-naked flatten was blocked ONLY because shorts are dark (the guard refuses any sell beyond the held long). Arming shorts relaxes that guard, so a false-naked could then execute a flatten that opens a short. Operator decision 2026-06-17: **fix first, then arm.** See [[shorts-reenable-cluster]].

**FIX (built, NOT deployed):** branch `fix/stop-coverage-false-naked`, commit `c4c5bd12`. Before flatten, `_handle_naked_flatten` re-fetches IBKR open orders and re-confirms coverage for that ONE position via new `stop_coverage_audit.position_is_covered()` (reuses `find_naked_positions`, `grace_seconds=0`, so re-confirm can't drift from detection). Live coverage on the fresh read ⇒ false-naked ⇒ abort + reset streak. A true naked also fails the re-read → still flattens immediately (no delay). Fetch failure ⇒ defer. 6 new tests, 62/62 green in the stop-coverage suite, 0 regressions (the 6 wider-run failures are pre-existing test-rot).

**DEPLOYED 2026-06-18 08:16 UTC** — cherry-picked to main (`3ce58255`), broker restarted, verified: 3 positions re-adopted, coverage publish fresh, not paused, no errors. Also deployed alongside: the trade-tracker dup-reconstruct guard (`4f0358ef`, see [[estx50-fesx-short-tangle]]). **Shorts re-arm now gated only on a clean Domain-A soak** (no false-naked flatten-attempts over a session) → then arm onto the green gate (gate re-order already live). Watch the soak on maintenance sweeps. Still NOT deployed: the deeper OrderFilledV3 emission-gap root fix (the trigger); and the ESTX50 P&L reconcile SQL still needs the operator to run it.
