---
name: router-full-roster-pin-is-silent-noop
description: "A PINNED set covering every gate makes the durable router tick a silent no-op that still logs \"no change\" as if healthy."
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-01T10:39:01.069Z
---

`scripts/router_tick_durable.py` filters proposed switch changes with `g not in PINNED` (around line 149). If `PINNED` covers **all** of `GATES`, the change set is permanently empty — the router can never bench or arm anything.

Hit on 2026-07-31: a US-open override set `PINNED = frozenset({all 6 gates})` with a comment saying "revert once the open settles." It was never reverted. **411 ticks across 07-31 and 08-01 logged `no change` and applied nothing**; the last real switch change was 2026-07-30T22:15.

The failure is invisible because a dead router and a correctly-idle router log the *same line*. Cost already paid: `grind` (the churner) was armed into the 07-31 violent open for −$370 with the untradeable meter unable to bench it, and the proven fader bench — the only router behaviour that survived independent re-derivation (+$810 non-overlap, n=25, stable under every regime tag) — was switched off the whole time.

**Why:** it is the [[pipeline-health-monitor-the-mechanism]] pattern again — the safety/override mechanism silently disabled the thing it was protecting, and the health signal kept reading green.

**How to apply:** treat any full-roster pin as an outage. On session start, check `PINNED` alongside the timer being active — an active timer is NOT evidence the router works. Grep `router_headless.log` for the last `APPLIED` line; if it is more than a day old during trading days, suspect the pin. Any temporary pin needs an expiry, and the tick should alarm loudly when `PINNED >= set(GATES)`.
