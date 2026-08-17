NIGHTLY REVIEW — grind-exit shadow + router/selector, run inside the CME halt. Read-only on the
desk; you may write notes to disk. Running headless, no operator watching.

DO:
1. THE DAY'S BOOK, SPLIT BY DESK. The tournament and the day-rider are SEPARATE desks sharing one
   IBKR account (DUQ191770), and the day-rider's P&L does not appear in the tournament total.

   ★★★ THE DESK DAY IS THE PARIS DAY: it runs 22:00Z → 22:00Z, and 22:00Z IS THE REOPEN.
   `date(closed_at)=date('now')` is the UTC calendar day and IS NOT THE DESK DAY — it was used here
   until 2026-08-17 and it misfiled every trade in the 22:00–24:00Z reopen window (**41 trades /
   $368 across the book**, including 07-30's 8 trades / −$336, which IS the documented reopen churn).
   You run at 22:43, i.e. 43 minutes INTO the next desk day, so the naive query also swept in trades
   that belong to tomorrow. Bound BOTH ends, and derive them — never hardcode +2h, that breaks at DST:

     read -r D0 D1 < <(PYTHONPATH=src .venv/bin/python -c "
     import datetime as dt; from gazbot7.pnl import paris_day_start_utc
     e=paris_day_start_utc(dt.datetime.now(dt.UTC))
     print(paris_day_start_utc(dt.datetime.fromisoformat(e)-dt.timedelta(seconds=1)), e)")
     sqlite3 -readonly data/gazbot7.db "SELECT gate LIKE 'day_rider%' AS rider,
       count(*), round(sum(pnl_usd),2) FROM trades
       WHERE closed_at >= '$D0' AND closed_at < '$D1' AND data_quality IS NULL GROUP BY 1"

   VERIFIED 2026-08-17 against the desk's own record: for the 07-30 desk day the corrected window
   returns **91 trades / +$1,172.00**, which is exactly the "+$1,172 — best ever" in
   `router_badcall_ledger.md`. The old form returned **82 trades / +$93.50** — a $1,078 miss on a
   single day, and it had never looked odd.

   ⚠ **State the window you used in the report.** A day figure with no stated boundary cannot be
   reconciled against anything, and this one was wrong for weeks without a single number looking odd.

   ⚠ DST, from 2026-10-25. Paris goes to UTC+1, so the desk boundary/reopen moves 22:00Z → 23:00Z
   while this job stays pinned at 22:43 UTC — it would then fire 17 min BEFORE the reopen instead of
   43 min after, and report the last COMPLETE desk day (one behind what the operator expects). The
   query above stays correct either way; the TIMER is what needs revisiting. Flag it, do not fudge
   the window to compensate.

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
