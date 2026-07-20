# GAZBOT V7 — Exit Wedge-Breaker (scope, NOT built)

**Status:** scoped 2026-07-20 after a live incident. NOT built — safety-critical
core change, operator sign-off required before implementation. Owner: core.

---

## The incident (2026-07-20)

A live rgv LONG (2 lots, opened 01:32:05 UTC) sat **held ~4h10m** — far past the
`max_hold_minutes=120` ceiling — and never auto-flattened. It was **protected the
whole time** (native venue stop live, +$12 → then drifted toward the stop), so no
uncapped bleed, but it was **stuck open when the desk should have exited it**.
Operator flatten (`python -m gazbot7.eod_flatten`) completed the close at 06:09
(recorded as the latched `ABSORPTION_CUT`, −$141).

**Mechanism (verified against code + journal):**
1. ~01:44 the absorption backstop fired → core initiated a close → `self._closing`
   latched `True`, `self._exit_reason='ABSORPTION_CUT'`.
2. The close order did **not complete** — `Order Canceled` (Error 202), later
   compounded by an IBKR connectivity drop (Error 1100→1102 at 04:28).
3. With `_closing` latched, the audit loop diverts **every** cycle to
   `_exit_watchdog` (`core.py:527-528`), which **only alarms** (`EXIT_NOT_COMPLETING`,
   fired once ~01:44 = the operator's "01:42 error") and **never re-attempts the
   exit**. The `_time_exit_check` branch (max-hold / session-flat, `core.py:540`)
   is unreachable while `_closing` is stuck. → indefinitely wedged.

## Why core does NOT already self-heal this

Deliberate: a live order-managing service must not **auto-restart** mid-position —
that drops in-memory position/exit tracking and orphans exits (the V5 −$713 scar;
the STATE §3 broker↔strategy restart-pairing rule). The `_exit_watchdog` doctrine
is *"detect + page the operator, don't auto-thrash."* The gap this incident exposes:
paging **once** into an overnight/quiet window, with no corrective action and a
latch that blocks all subsequent exits, means a wedge = an indefinitely stuck
position. Passive detection is not enough.

## The fix — an in-loop wedge-breaker (NOT a self-restart)

Escalate `_exit_watchdog` from *alarm-only* to *bounded self-heal*, inside the
running process (no restart, no tracking loss):

1. **Re-fire the flatten.** When a close has been in flight for
   `EXIT_STUCK_CYCLES` and the position hasn't reduced, **force-cancel the dangling
   close order and re-submit a fresh MKT flatten** for the venue-truth net qty —
   instead of only alarming. Reclaims the exit in-process.
2. **Bounded + idempotent.** Cap re-fires (e.g. `EXIT_REFIRE_MAX=3`); each re-fire
   cancels the prior dangling order first (no order pile-up / re-fire walk — reuse
   the `_closing` idempotency that already prevents the V5 +1→−101 storm). Space
   them by cycles, not instantly.
3. **Escalate on repeated failure.** If re-fires still don't complete after the cap,
   `gw.force_reconnect()` (already used for unverified-protection — the connectivity
   class, e.g. the 04:28 Error 1100), then resume the re-fire cycle once healthy.
4. **Page on every escalation**, critical tier, so a stuck exit is never silent for
   4h again — not one alarm, but one per escalation step until resolved.
5. **Guards / preconditions.** Only act when venue truth is **fresh** (the same
   pre-flight the naked auditor uses — never re-fire blind during an unverified
   cycle); respect `place_live`; never re-fire onto a position the venue says is
   already flat (that's the vanished-close path, handled separately).

**Self-restart stays OUT of scope** as the primary mechanism. If ever added as a
last-resort backstop, it must go only through the existing boot-adopt path (core
re-adopts the venue position + re-arms the stop on boot) so it can't orphan — but
the in-process re-fire above is strictly preferred and should make it unnecessary.

## Parameters (new / reused)

- `EXIT_STUCK_CYCLES` — *exists* (alarm threshold); reuse as the re-fire trigger.
- `EXIT_REFIRE_MAX` — *new* — cap on re-fire attempts before the reconnect escalation.
- (No new env knobs unless the operator wants them tunable; sensible constants first.)

## Test plan

- Close in flight + position not reducing for `EXIT_STUCK_CYCLES` → asserts a
  **re-submitted** MKT flatten (not just an alarm), prior order cancelled first.
- Re-fire cap reached → asserts `force_reconnect()` then resumed re-fire.
- Re-fire onto an already-flat venue → **no** order (vanished path, no double-flatten).
- Max-hold + a *stuck* `_closing` latch → the position is ultimately flattened
  (regression for exactly this incident: max-hold must win even through a wedge).
- Idempotency: no re-fire order-storm; `_closing` never produces a +1→−101 walk.

## References

- Incident: SESSIONS 2026-07-20 (the −$141 stuck rgv close), core journal
  (Error 202 / 1100→1102), `core.py:358-377` (`_exit_watchdog` / `_time_exit_check`),
  `core.py:520-540` (the audit loop divert).
- Related scars: STATE §3 (restart pairing), memory `naked-position-from-silent-auditor-skip`
  (the "can't verify = alarm, never silent-skip" hardening — this is its exit-completion twin).
