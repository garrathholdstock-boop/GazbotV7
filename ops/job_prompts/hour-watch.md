HOURLY TAPE/GATE WATCH — read-only. You are running headless with no operator watching.

RUN: cd /home/alphabot/gazbot7 && PYTHONPATH=src .venv/bin/python scripts/hour_watch.py

★★★ THE DATA CONTRACT — READ BEFORE YOU QUERY ANYTHING. It binds every step below.

1. **THE TWO TOOLS ARE THE SOURCE OF TRUTH FOR TRADES: `hour_watch.py` and `desk_view.py`.**
   Do not hand-roll a query against `data/gazbot7.db` to "check" or "enrich" what they report.
2. **EVERY trade query MUST be bounded to the desk day:** `closed_at >= paris_day_start_utc(now)`
   (`gazbot7.pnl.paris_day_start_utc`). The desk day starts at PARIS midnight = 22:00Z the previous
   day, which is also the reopen — never `date('now')`, never a bare hour offset.
3. **NEVER `ORDER BY closed_at DESC LIMIT n`.** "The last N trades" has no date floor, so on a quiet
   morning it silently walks back into the PREVIOUS SESSION — or, after a weekend, into Friday.
   If you want recent trades, filter by time and accept that the answer may be zero rows.
4. **ZERO TRADES IS A COMPLETE ANSWER.** If the tools say `hour_trades: 0` / `day_net: 0` /
   `gates: []` / `DAY TOTAL +0.0`, then the desk has not traded and there is NOTHING to dissect.
   Do not go hunting for rows to explain. Report "no action needed" and stop.
5. **A DUAL-LOT GATE WRITES TWO ROWS PER SIGNAL** (`<gate>_A` and `<gate>_B`). Six rows is three
   signals. Say which you are counting, and never present leg-count as signal-count.
6. **NEVER PAIR A LIVE TAPE READ WITH A TRADE READ FROM ANOTHER DAY.** If your price/ER/ATR numbers
   are from now, your trade numbers must be from now. State the window for BOTH, explicitly.

⚠ WHY THIS EXISTS — 2026-08-17 07:08Z, a false ATTENTION GAZ. This job told the operator to bench
`exhaustion_short` because "it is the only gate trading" and "net ~−$88 on the day", citing "its last
3 signals (18:41, 18:44, 19:43), all STOPs for −$133". **The desk had taken ZERO trades that day** —
those were Friday 08-14's six A/B legs (−$133.5), reached by an unbounded "last N" query, and 18:41
had not yet occurred at 07:08. The tape half of the alert was correctly today's, which is exactly
what made it convincing. Both sanctioned tools reported the truth at that moment and were not used.
The durable router read the SAME rows correctly the day before — *"residue, not a wall"* — because
its prompt carries this contract and this one did not.

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
