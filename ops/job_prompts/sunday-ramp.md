SUNDAY PRE-OPEN / OPEN RAMP — read-only, ahead of and through the 22:00 UTC CME reopen.
Running headless, no operator watching. Report exceptions only.

CHECK:
1. `cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json` — healthy, flat, capture
   fresh, not halted. (See the known false alarms: the tournament restart count is a LIFETIME
   counter, gazbot7-core/strategy have never started, and the killswitch headroom is vacuous.)

2. THE ROUTER IS ALIVE AND DECIDING. `systemctl is-active gazbot7-router-tick.timer` AND
   `tail -3 data/router_headless.log` — the last line must be a real decision, not an `ABORT:`.
   An ABORT streak means an expired login and a FROZEN desk: the fix is to run `claude` on the box
   and /login. This is the single most important check here, because a reopen with a dead router
   means the desk trades the whole week on stale switches.
   Also confirm gazbot7-router-health.timer is active — that is the alarm for exactly this.

3. THE 22:00Z GATE REACTIVATION. `gazbot7-gate-reactivate.timer` arms EVERY `=off` gate at the
   reopen. Confirm `reactivate_gates.py::HOLD` still holds whatever must stay benched — as of
   2026-08-13 that is nipc_long, nipc_short and rgv_short. A gate that failed acceptance must not
   come back on the reopen minute.
   ⚠ Note the reopen is also historically the churniest moment: an all-gates-open reopen churned
   −$275 on 08-01 before the router could bench the wrong-side gates. Expect the first ticks to
   bench, and do not read that as thrash.

4. THE DAY-RIDER is unaffected by the reopen (it only runs 13:38–20:40 UTC) but confirm
   `data/day_rider.env` still says `day_rider=on` and its timers are active.

REPORT: only exceptions, and lead with the action needed. If everything is ready, print exactly one
line: "reopen ready — <six-word note>". Change nothing; never edit data/gate_switches.env.
