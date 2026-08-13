3-HOURLY FULL MAINTENANCE SWEEP — read-only. Running headless, no operator watching.

RUN: cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json

Report CRIT immediately and plainly. For WARN, judge whether it is real before speaking.

⚠ THREE KNOWN FALSE COMFORTS / FALSE ALARMS in this sweep — check against these before you page:

1. "restart-storm: gazbot7-tournament×N" is a LIFETIME counter that never resets, not a rate.
   Established 2026-08-13: those restarts are IB Gateway reconnects (a daily ~04:40Z re-auth window
   plus container restarts). The desk handles them correctly — the audit loop goes stale, the
   tournament DELIBERATELY withholds its systemd watchdog ping, systemd restarts it and it re-adopts
   slots from the ledger. That is the post-naked-position fail-safe working. Only escalate if the
   restarts are CLUSTERED IN THE LAST FEW HOURS; check with
   `journalctl -u gazbot7-tournament --since "6 hours ago" | grep "restart counter"`.

2. "all up · restarts core: 0" for gazbot7-core and gazbot7-strategy is meaningless — both units are
   `disabled` and have NEVER started. They are vestigial. The live desk is gazbot7-tournament.

3. killswitch "headroom OK" is VACUOUS: max_daily_loss_usd and loss_streak_halt are both 0, so there
   is no killswitch to have headroom against. Do not report it as a health signal.

ALSO CHECK, because the sweep does not:
 * `tail -3 /home/alphabot/gazbot7/data/router_headless.log` — the last line must be a real decision
   ("no change ..." with reasoning, or "APPLIED ..."), NOT an `ABORT:` line. An ABORT streak means
   the router is deciding nothing and the desk is frozen. (gazbot7-router-health.timer also alarms
   on this; if you see it and no alarm has fired, say so — the alarm itself may be broken.)
 * A dirty working tree WARN is a bookkeeping failure, not an order-path failure. Report it, do not
   treat it as urgent.

REPORT: only what needs acting on. If everything is genuinely fine, print exactly one line:
"sweep clean — <six-word note>". No progress pings. Change nothing.
