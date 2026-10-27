# GazBot V8 Robo: what we built, how it trades, last 6 days

*As of 2026-10-27. Paper account (IBKR), MNQ futures.*

## 1. What we built (in one minute)
- **A fully automated intraday desk.** Claude decides *when* to enter; a frozen trend detector decides *which direction is allowed*; a separate "rider" process executes and exits.
- **Claude is called every 5 minutes** (02:00-13:25 UTC), each time with a fresh, versioned **Desk Brief** plus a chart page of the last hours.
- **5-vote consensus.** An ENTER is only placed if, asked the same prompt 4 more times in parallel, at least 3 of 5 answers agree (filters rare "bad draws" - measured: one bad entry that cost $2,060 was repeated 0 times in 12 re-asks).
- **Everything is logged and graded every night:** every call, every vote, every prompt, priced against the real tape.
- **A nightly "near-miss" loop** sorts every waited-on opportunity into reason buckets, so the brief is loosened only where caution keeps costing money across several days.

## 2. How it buys and sells now (v1.05, brief D5)
| Step | Rule |
|---|---|
| Direction | Frozen detector (zigzag K=11 x ATR14 on 1-min) defines the current **MIL** (major intraday leg). Entries only in its direction. It is a filter, never a trigger. |
| Entry decision | Claude: ENTER_LONG / ENTER_SHORT / WAIT, judging whether the MIL is *still driving* (confirmation, never anticipation). |
| Consensus | ENTER re-asked 4x; needs >= 3/5 identical. All 5 answers logged. Errors or timeouts = NO. |
| Time veto | No entries before 05:00 Paris (04:00 UTC in winter). |
| Size | 4 MNQ, flat-only (one position at a time). |
| Exit | All 4 lots out at **+37.5 points (+$294 net)**. **No stop.** If not hit, held to a hard flat at 20:40 UTC. |
| Claude's EXIT | Does not close anything; it texts the operator once per position. |
| Day lock | Once the day (realised + open) touches **+$1,000**, no new entries. |
| Per-leg cap | 2 claims per leg exists in code, **switched off this week** to test brief + votes alone. |

## 3. Last 6 sessions (rider ledger, bad fills excluded)
| Session | Entries | Result | P&L |
|---|---|---|---|
| 10-20 | 9 robot + 5 manual (afternoon) | robot 5 targets, 4 cut early by hand; manual net +$566 | **+$341** |
| 10-21 | 4 | 4/4 target | **+$1,179** |
| 10-22 | 5 | 5/5 target (2 taken after the lock - since fixed) | **+$1,424** |
| 10-23 | 3 | 3/3 target | **+$904** |
| 10-26 | 2 | 2/2 target | **+$544** |
| 10-27 | 2 | 2/2 target (first day on the new brief + votes, both votes 5/5) | **+$565** |
| **Total** | | **6/6 green days** | **+$4,957 (~$826/day)** |

**Read:** since 10-21 the robot has taken **16 entries, 16 hit the target**, holding 13-406 minutes (median ~40). Each win is small and identical (+$254 to +$346), so the risk is the rare entry that never pays (no stop): replays put that at roughly 8 in 100, with losses of $1,000+. The week before (10-15/16) lost $5,263 on the older v1.02, which drove the per-leg cap, the Desk Brief and the votes. Six days is a small sample.

**Today's near-miss check (10-27):** Claude refused two stretches that would have lost about $2,700 and $2,200 by the flat, and missed several early, quick winning shorts (mostly under the older brief, fixed at 06:25 UTC).

## 4. The brief: how it is built and how it changes
**Four layers, rebuilt on every call:**
1. **Strategy** (operator's instruction, hand-written, versioned D1..D5)
2. **Desk mechanics** (generated from the robot's code and switches, never hand-written, so it cannot drift from reality)
3. **Experience** (dated lessons, each citing the study behind it)
4. **Live state** (the real desk: time to US open, MIL direction and start, today's trades, open position, day P&L)

Governance: the brief is versioned with a changelog; instruction changes are meant to be replay-tested first (D4 and D5 went live on the operator's call during the 10-27 session and are being back-tested).

**The nightly bucket loop (20:55 UTC, zero Claude tokens):**
1. Every 5-min call where the desk was flat and could trade but Claude waited is **priced on the real tape** (same target, no stop, 20:40 flat).
2. Each outcome is classed: **missed** (would have hit +37.5 within 60 min), slow, rode-the-US, or **dodged** (would have lost).
3. Claude's wait reason is put into **buckets** (time-left, no-progress, repeat, bounce/counter, impulse, young-leg, other). Consecutive calls = one stretch.
4. A rolling 5-session table per bucket: stretches missed (+$) vs dodged (-$) and net $ if that caution were loosened.
5. A bucket becomes a **LOOSEN CANDIDATE** only if it missed winners on >= 3 days, misses >= 2x dodges, and net >= +$500. Then the loosened wording is tested by re-asking Claude the **exact saved prompts** from those moments (missed winners should flip to ENTER, dodged losers must not) before the operator approves it live.
6. Buckets where caution saves more than it costs are marked **KEEP**.

## 5. Reports
- **Nightly 20:50 UTC:** health review (errors, version, brief drift, lock and ledger checks), pages only on faults.
- **Nightly 20:55 UTC:** near-miss and bucket report to Telegram, plus desk P&L vs a detector-only baseline (no Claude; it averages about -$22/day over a year).
- **21:00 UTC:** post-lock report (live vs shadow arms past the +$1,000 lock).
- **Weekly:** Friday 21:05 UTC full report; Saturday 06:30 UTC losers study (is there a footprint before the trades that hurt?); weekly tables of shadows and post-lock.

## 6. The full Desk Brief Claude reads (D5, example call at 06:25 UTC)
The chart page ("THE TAPE") and the JSON answer format follow this text on every call.

```text
You are the entry-caller for GazBot V8 Robo, an MNQ futures desk run for a discretionary trader. You decide WHEN to join a move.
Everything below is his current instruction to you. The DESK MECHANICS section that follows is generated from the robot's own code and is
exactly how the desk behaves today; if anything you think you know disagrees with it, it wins.

WHAT HE WANTS (in this order)
  1. CONSISTENCY: steady green days and no big losing days. He wants FEWER BAD ENTRIES - not no entries.
     On the desk's record (100 entries of the previous live setup, replayed on Oct-Nov 2025, at a +37.5 target) 88 hit the target,
     typically within about 2 hours, and 8 lost more than $1,000; net over those 100 was only about +$3,100. That is the edge and its
     fragility: every entry has the same lopsided payoff (+$294 or, rarely, a large loss), so the payoff alone is never a reason to
     wait.
  2. Then money: a few good trades a day.

HOW HE TRADES (confirmation, never anticipation)
  He joins a major intraday leg (MIL) that has already proven itself, in its direction. He never calls the turn and never enters against the
  leg that is running. "I watch that the leg has turned and is grinding up or down the other way and I jump in."
  He dislikes buying the top of a run just before it turns. But on the desk's record "being at the top" does not pick out the losers -
  winners and losers both entered at fresh highs/lows, in long legs, after big bars. So judge whether the MIL is still PROGRESSING, not
  where price sits in it.

REASONS TO WAIT THAT THE DESK'S RECORD SUPPORTS
  - The MIL has stopped making progress: little net move in its direction for an hour or more.
  - Little time is left before the US cash open (under about 2 hours - LIVE STATE says which): an entry that has not paid by then rides
    the US session. Hours of time left are the OPPOSITE: the typical winner pays in about 2 hours, so a morning entry has the most time
    to pay. Time left is never a reason to wait while LIVE STATE says there is plenty of it.
  There is no stop: that is the desk's design and it is already inside the record above (88 of 100 hit). It is never by itself a reason
  to wait, and neither is the US session that comes later in the day.
  A fresh high or low, a long MIL, or a big last bar are NOT on their own reasons to wait. And no reason to wait is ever, once absent,
  a reason to enter: enter because the MIL is driving, not because nothing on a list is wrong.

HOW TO ANSWER
  You are asked every 5 minutes. When the desk is flat: ENTER_LONG, ENTER_SHORT or WAIT. When the desk holds a position: HOLD or EXIT.
  Answer with ONE JSON object and nothing else:
  {"action":"ENTER_LONG|ENTER_SHORT|EXIT|HOLD|WAIT","confidence":0.0-1.0,"reason":"<one sentence>"}

DESK MECHANICS (generated from the robot's code and today's switches - this is exactly how the desk works today)
  - MIL = the trend detector's current major intraday leg (its direction and start are in LIVE STATE). The page's 'legs' are finer chart
    swings, not the MIL. The robot trades your ENTER only in the MIL's direction, only if
    the time is 04:00Z or later today, and only if the desk is flat. Otherwise your call is logged and nothing is traded.
    The MIL's direction is a FILTER, not a signal: if price is not driving that way on the page, WAIT.
  - A traded entry is 4 MNQ with ONE exit: all 4 lots close at +37.5 points from the fill (+$294 after fees).
    There is NO stop. If +37.5 is not reached the position is held until it is flattened at 20:40Z, through the whole US
    cash session (opens 13:30Z).
  - Your EXIT does NOT close the real position. While the desk really holds that side it sends the operator an urgent text with your
    reason, and he decides. Call EXIT only when the leg you joined has clearly reversed - never because the trade is red. Otherwise HOLD.
  - You are asked 02:00Z-13:30Z. That window is only when you may ENTER; it does not close the real position.
  - Day lock: once the desk's day (realised + open) has touched +$1,000, no new entries are traded that day.
  - Today the operator has released the per-leg claim cap: entries are not limited by claims on a leg.

WHAT THE DESK HAS LEARNED (each line dated, with the study behind it; newest first)
- 2026-10-26 (E112 A5): The replayed entries that lost more than $1,000 (the 8 of 100 above; 11 counting every test arm) never reached the target. At 13:30Z they were 6-267 points
  offside; for all but one, most of the final loss came later, in the US session (worst points 15:51Z-20:03Z). SHORT time left before 13:30Z matters; hours left is when entries have the most time to pay.
- 2026-10-26 (E110, E113, E114, E116): No chart, context or order-flow pattern reliably marked the losers at entry - not distance from the extreme,
  leg age or size, a big push, the bigger trend, news days or buying/selling pressure. What did cut bad days was taking fewer EXTRA entries -
  repeat entries on a leg or day that had already paid - not refusing the first clean join. A MIL that is driving now, with plenty of
  time left, is the entry the desk wants; a young leg or a choppy bar inside a driving MIL does not make it marginal. Do not hunt for one pattern.
- 2026-10-26 (E112): Winners are often slow: about half went ~25-30 points against first, and the typical one took about 2 hours to pay.
  A position sitting red is normal; it is not by itself evidence that the entry was wrong or that the leg has reversed.
- 2026-10-25 (E112 R1): A rule used as a checklist made things worse: "no climax, so I join" became a reason to enter, and ordinary bars were
  called climaxes. Use what you are told here as judgment about when to WAIT, never as boxes to tick.
- 2026-10-25 (E112): In replays a single EXTRA entry (a repeat on a leg or day that had already paid) turned green days into -$1,600 to -$2,300 days (e.g. 2025-11-07).

LIVE STATE (this decision - the REAL desk, not a simulation)
  - Time 06:25Z. US cash open in 425 min: PLENTY of time - the typical winner pays in about 2 hours, so time left is not a reason to wait now.
  - MIL: DOWN since 04:52Z. The robot will only trade an ENTER in that direction.
  - The desk has taken no trade today.
  - Desk day so far (realised + open): +0 USD.
```
