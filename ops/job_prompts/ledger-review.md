ROUTER BAD-CALL LEDGER review (~4-hourly, ONGOING) — keep the learning fresh. You are running
headless with no operator watching, so be decisive and write your conclusions to disk.

DO:
1. Read /home/alphabot/gazbot7/data/router_badcall_ledger.md THOROUGHLY — re-internalise the
   ❌ BAD / ⚠ CHURN patterns before the next tick.
2. GRADE any switch-changes from the last ~4h that now have a known outcome. Pull them from
   `tail -80 /home/alphabot/gazbot7/data/router_trial_log.txt`, and for each judge right/wrong in
   dollars where measurable (per-gate live P&L, or the gate's shadow P&L over the benched window as
   the "what it would've done" proxy). Add/update ledger entries with a verdict
   (✅ GOOD / ❌ BAD / ⚠ CHURN / ◻ NEUTRAL) and update the running scoreboard.
3. COUNT SWITCH CHANGES in the window. Churn is invisible at $0 — on 08-07 there were 20 changes in
   4h and only 4 produced a fill. Flag it if changes far exceed fills.
4. If a ❌/⚠ reveals a durable rule that is not yet a memory, say so explicitly in the ledger entry.

⚠ TWO THINGS THAT WILL MISLEAD YOU, both established 2026-08-13:
 * THE ROUTER LOG TRUNCATES AT 1200 CHARS AND THE CLIPPING IS POSITIONAL. The reason is written
   meter → direction/shorts → LONG SIDE LAST, and the mean reason is 962 chars, so whenever the
   shorts discussion runs long the momentum-gate reasoning falls off the end entirely. Absence of a
   gate from the log is NOT evidence the router ignored it, and a clean-looking log may be only the
   shorts half. Do not grade a long-side call from the router log alone.
 * TO SEE WHAT A GATE ACTUALLY DID, use the tournament journal, which is reliable:
   `journalctl -u gazbot7-tournament --since "4 hours ago" | grep -E "SUPPRESSED-OPEN|ATR gate"`.
   `SUPPRESSED-OPEN ... (disabled by switch)` = benched while it WANTED to trade.
   `ATR gate: ... (atr=Xpt below floor)` = it could not have fired anyway, so the bench cost nothing.
   That distinction is the difference between a real miss and a free one.

REPORT: write your verdicts into the ledger file. Then print a SHORT summary (a few lines) of the
verdicts and any new pattern. If nothing in the window had a gradeable outcome, say exactly that in
one line and write nothing. Read-only on the desk — this is a learning pass, not a tick. Never edit
data/gate_switches.env.
