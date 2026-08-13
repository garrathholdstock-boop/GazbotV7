NIGHTLY REVIEW — grind-exit shadow + router/selector, run inside the CME halt. Read-only on the
desk; you may write notes to disk. Running headless, no operator watching.

DO:
1. THE DAY'S BOOK, SPLIT BY DESK. The tournament and the day-rider are SEPARATE desks sharing one
   IBKR account (DUQ191770), and the day-rider's P&L does not appear in the tournament total:
     sqlite3 -readonly data/gazbot7.db "SELECT gate LIKE 'day_rider%' AS rider,
       count(*), round(sum(pnl_usd),2) FROM trades
       WHERE date(closed_at)=date('now') AND data_quality IS NULL GROUP BY 1"
   Report TOURNAMENT, DAY-RIDER and TOTAL separately. On 2026-08-13 the week's tournament book was
   −$438 while the day-rider made +$1,183.50 — reporting one without the other is misleading.

2. THE DAY-RIDER'S SESSION. Did it detect? enter? how did it exit? Its exits are:
   MANUAL_CLAIM (operator), TRAIL, CLOCK_FLAT, OPERATOR_SELL, CLOSED_ELSEWHERE.
   ⚠ CLOSED_ELSEWHERE means the venue was already flat at the 20:40 clock while the rider's own book
   still held — someone or something else closed the position. That is ALWAYS worth reporting, and
   worth naming who: the shared account means the tournament or a stray stop can do it.

3. THE ROUTER'S DAY. Count switch changes and compare against fills — churn is invisible at $0.
   `grep -c APPLIED data/router_headless.log` for today vs the day's trade count.
   ⚠ Do NOT judge a long-side decision from the router log: it truncates at 1200 chars and the
   clipping is positional (the long side is written last and falls off). Use the tournament journal:
   `journalctl -u gazbot7-tournament --since today | grep -E "SUPPRESSED-OPEN|ATR gate"`.

4. GRIND-EXIT SHADOW + the exit selector's per-regime behaviour, if there is anything to say.

⚠ METHOD RULES that have burned this desk repeatedly:
 * MFE IS NOT A WIN RATE. "reached N R" ignores whether the STOP came first — compute the race.
 * The fee is $1.50/round-trip. Never $5, never per-side.
 * Verify config via `scaleout_slots()`, never by reading source — the slate silently drops things.
 * A shadow result is not a live result, and the shadow repricer leaks past its own stops on 44% of
   trades, so any study concluding "exit earlier" is suspect. Exiting LATER is not affected.

REPORT: a tight summary — the three P&L figures, the day-rider's session, the router's churn count,
and anything that needs a decision. If a durable rule emerged, state it in one sentence. Never edit
data/gate_switches.env.
