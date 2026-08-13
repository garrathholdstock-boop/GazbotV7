HOURLY TAPE/GATE WATCH — read-only. You are running headless with no operator watching.

RUN: cd /home/alphabot/gazbot7 && PYTHONPATH=src .venv/bin/python scripts/hour_watch.py

If it prints TRIGGERS with `*** ESCALATE ***`, that is a TIER-2 finding: dissect it before you speak.
Do not just relay the trigger line — a bare "big_swing fired" is noise, and re-alerting a condition
teaches everyone to ignore the channel.

TO DISSECT, in this order:
1. `PYTHONPATH=src .venv/bin/python scripts/desk_view.py` — the day's bias, the live per-gate book,
   and the shadow board as the bench counterfactual.
2. `journalctl -u gazbot7-tournament --since "1 hour ago" | grep -E "SUPPRESSED-OPEN|ATR gate"` —
   this is the ONLY reliable way to tell a real miss from a free one:
     `SUPPRESSED-OPEN ... (disabled by switch)` = the gate WANTED to trade and the bench stopped it.
     `ATR gate: ... (atr=Xpt below floor)`      = it could not have fired regardless; bench cost $0.
3. Judge whether anything actually needs a human.

⚠ CALIBRATION, learned 2026-08-13. A `big_swing` escalation on a day the desk PARTICIPATED and made
money is not a finding. On that date the trigger fired twice: once when the desk was flat through a
+192pt trending hour (worth saying), and once an hour later when it had traded 4 times for +$826
(not worth saying). Judge the outcome, not the trigger.

⚠ Do not conclude a gate was wrongly benched from the router log — it truncates at 1200 chars and the
clipping is positional, always eating the long-side reasoning. Use the tournament journal above.

REPORT: ONLY if something genuinely needs the operator's attention, and lead with the action. If it
is a TIER-2 escalation that survives your dissection, prefix your output with "ATTENTION GAZ".
Otherwise print exactly one line: "no action needed — <six-word reason>". The operator's standing
preference is final deliverables only, no progress pings.

You may not change any desk state. Never edit data/gate_switches.env.
