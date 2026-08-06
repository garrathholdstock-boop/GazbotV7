---
name: day-rider-live-paper
description: "DAY RIDER — the drift strategy live in paper from 2026-08-06 as its own service; detect at 13:38-14:09, 2 lots, armed trail, flat 20:40 UTC, never overnight"
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-05T16:26:16.315Z
---

**Live (PAPER) from 2026-08-06.** A SECOND desk alongside the tournament, its own systemd timers, its own IBKR clientIds. Switch `data/day_rider.env` → `day_rider=on`. Code: `src/gazbot7/{drift,day_rider}.py`, `scripts/day_rider_watchdog.py`.

```
DETECT  13:30 UTC cash-open anchor: efficiency >=0.15 AND roundtrip >=0.45
ENTER   2 lots, direction = sign of net. ONE per session. No entry after 15:00 UTC.
EXIT    100pt trail, ARMED only once +150pt ahead. HARD FLAT 20:40 UTC.
ASK     2xATR reversal off the peak → pages operator 3x/15min → DEFAULT HOLD.
```

**★ NOT a tournament gate, deliberately.** `multislot_core.py:372` force-flattens everything at `max_hold_minutes=120`; this holds ~7h. Capped it earns $7,047 and FAILS the battery; uncapped $13,257, passes 5/5. **Never raise the global cap to accommodate it** — that cap is what limited the MD_STREAM incident to −$255.50.

**★★ FLAT 20:40 UTC (22:40 Paris), NOT 21:00.** 21:00 UTC *is* the CME halt: a flatten there has no market and no retry window. 20:40 gives 20 minute-ticks of retry and the flatten verifies the fill. Cost $149 of $13,257; days-green 81%→84%. ★ **STANDING RULE: NEVER HOLD OVERNIGHT. EVER.**

**★ ANCHOR = CASH OPEN. Tested, do not re-litigate.** A 22:00 UTC (midnight Paris / CME) anchor gives **ZERO detections in 33 sessions** — 15h40m of overnight chop makes the path ~25x longer, so efficiency reads 0.048 against the 0.15 floor. Not "worse", structurally incompatible.

**★ SAFETY (it inherits none):** heartbeat + INDEPENDENT flatten-only watchdog on clientId 5 requiring BOTH a fresh heartbeat AND `venue_ok`. ⚠ Found live: a tick that cannot reach IBKR still stamps a heartbeat — treating that as "managed" recreates [[naked-position-silent-auditor-skip]] through the watchdog's own health signal. 600pt venue stop is last-resort only (a 400pt stop costs $3,451 AND worsens the worst day, killing the winner that drew 511pt and recovered). Atomic restart-safe state. Fail-closed; garbled switch reads OFF. Telegram `/sell` `/hold` write a token-matched decision file — **the bot never places orders**.

**Validation:** `drift.compute()` reproduces the backtest on all 31 sessions with **zero mismatches**. 71% of early drifts persist to the close. ~16 of 31 days fire, ~$428/firing day, 81-84% green.

⚠ 31 in-sample sessions after ~60 configurations. First weeks are evidence, not proof. See [[exits-are-exit-proof]].
