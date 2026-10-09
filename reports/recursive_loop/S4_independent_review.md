# S4 independent review: the S line against the four operator objectives

Reviewer: independent (read-only). Date of reading: 2026-10-08. Account: PAPER. MNQ, 4 lots, $8/pt, $6/trade fee.
Scope: BRIEF_V2, the page the model sees, S1b, S2 (rejected), S3 (INTERIM), and the four decided S4 changes.
Nothing here was simulated. Every number is a count or a sum over trades that were actually recorded in
`reports/sim_week_recursive/sline_{s1b,s2,s3}_<day>.json`, joined to `data/tape/bars/MNQ/backfill_1min.parquet` for context only.

## 0. Read this first: what these numbers are and are not

- Days: S1b 9 days, S2 9 days, S3 6 days (02-05, 02-19, 03-05, 03-19, 04-02, 04-16). **S3 is INTERIM (Law L6). It is not a result.**
  The 04-16 S3 file was complete (138 calls) when read, so it is included; no in-progress file was touched.
- Noise: the standard error of a 9-day mean is about $350/day and the preflight floor is $324/day. **Single-run dollars cannot
  decide anything here.** Counts can, because they describe what the model did, not what the market paid for it (Law L10).
- Four labels are MY proxies, applied identically to every arm:
  - CLAIMED = closed green and points >= 2 x ATR(14,1m) at the exit bar (the S3 definition). SMALL GREEN = green but below that. RED = P&L <= 0.
  - MIL = a 7 x ATR(14) retrace tracker on 1-min closes from 00:00Z. It lags at turns, so an entry flagged "against the MIL" at a genuine
    turn is really an early entry (the best S3 trade, 02-05 short 02:05 +$886, is flagged against it). Treat "against" as weak.
  - ENTRY TIMING (early / mid / late) = share of the MIL's eventual extent already travelled at entry. That uses the MIL's future extent.
    **It is a hindsight label for describing what happened and must never become an instruction.**
  - "Rebuy" = an entry within 15 minutes of the previous exit; "next look" = the 5-minute gap.
- Counterfactual re-simulation is not used anywhere (119 failed calibrations). Where I say "S4 would have removed X", I mean
  "these recorded trades fail the S4 rule as written", not "the P&L would have been Y without them". Removing a trade changes every
  later decision the model makes that day.

## 1. Verdict per objective

| Objective | Verdict | Key numbers (S1b 9d / S2 9d / S3 6d interim) |
|---|---|---|
| PROFITABLE | FAIL in all three arms. | Net -$180 (-$20/day) / -$2,068 (-$230/day) / -$2,248 (-$375/day). On the same six days S1b was -$842 (-$140/day), so S3 is worse than the baseline it was meant to improve. |
| CONSISTENT (Law 0) | FAIL. | Days positive 5/9 / 4/9 / 3/6. Worst day -$1,490 / -$1,516 / -$1,948. Daily SD $1,042 / $802 / $989. Top winning day is 39% / 62% / 65% of all positive-day dollars. On the shared six days S3 fails `bible.gate` against S1b: days-positive equal (3/6), worst day worse (-$1,948 vs -$1,204), $/day lower. |
| PATIENT | FAIL, and S3 made the opposite worse. | 31% / 30% / 35% of trades held 10 minutes or less (43 / 24 / 37). Median hold of a red trade 15 / 15 / 18 min. 87-93% of red exits quote the brief's own "the leg itself has reversed" carve-out (58 of 71, 38 of 41, 49 of 56). Median red exit is -20 / -26 / -24 points, which is 2.1 / 2.3 / 2.5 ATR, the same distance as a 2 x ATR claim. |
| 3-6 TRADES/DAY | FAIL by a factor of 3. | 15.2 / 9.0 / 17.7 trades/day. Days inside 3-6: 0 of 9, 0 of 9, 0 of 6. Days above 10: 9 / 2 / 6. Rebuys within 15 minutes: 64 / 26 / 66 (7.1 / 2.9 / 11.0 per day). |

The single sentence that explains all four: **the model wins about half its trades and cuts its losers at the same distance it takes its
winners, so the book is a symmetric bracket of about +/- 2 ATR traded 15 times a day.** A symmetric bracket at a 47-50% hit rate and
$6 per trade is a coin flip with a fee. Everything below is about why and what moves it.

| Exit class | S1b n / mean $ / median hold | S2 | S3 (interim) |
|---|---|---|---|
| CLAIMED (>= 2 ATR) | 27 / +$345 / 35 min | 17 / +$298 / 45 min | 36 / +$233 / 15 min |
| SMALL GREEN | 39 / +$89 / 20 min | 23 / +$72 / 20 min | 14 / +$105 / 18 min |
| RED | 71 / -$183 / 15 min | 41 / -$215 / 15 min | 56 / -$216 / 18 min |
| Share of trades that are red | 52% | 51% | 53% |
| Exits in profit | 48% | 49% | 47% |

What S3 did, in counts: claims per day doubled (3.0 to 6.0) and the claims got smaller and faster (mean +$345 to +$233, median
hold 35 to 15 min), but red trades did not fall (7.9 to 9.3 per day). Gross claimed dollars per day rose by about $359; gross red
dollars per day rose by about $574. The claim rule moved the winners' exit earlier, which the operator asked for, and left the
entry problem (more than half of all trades are red) and the churn problem (rebuys) untouched.

## 2. Per-day tables

Columns: n trades; net $; exits claimed / small green / red; entries with the MIL; held <= 10 min; rebuys within 15 min of the
previous exit; entries right after a claim; median hold (min).

**S1b (baseline)**

| Day | n | Net $ | CLM | sg | red | with MIL | <=10m | rebuy<=15m | after claim | med hold |
|---|---|---|---|---|---|---|---|---|---|---|
| 02-05 | 20 | +752 | 4 | 7 | 9 | 12 | 8 | 10 | 4 | 15 |
| 02-19 | 11 | +274 | 2 | 3 | 6 | 10 | 1 | 5 | 2 | 30 |
| 03-05 | 21 | -1,204 | 1 | 6 | 14 | 11 | 10 | 11 | 1 | 15 |
| 03-19 | 19 | -1,168 | 2 | 6 | 11 | 13 | 11 | 8 | 2 | 10 |
| 04-02 | 12 | +988 | 6 | 1 | 5 | 9 | 1 | 5 | 6 | 25 |
| 04-16 | 12 | -484 | 2 | 2 | 8 | 11 | 2 | 7 | 2 | 25 |
| 04-30 | 11 | +544 | 3 | 4 | 4 | 11 | 2 | 4 | 3 | 25 |
| 05-14 | 17 | -1,490 | 2 | 6 | 9 | 11 | 6 | 6 | 2 | 15 |
| 05-28 | 14 | +1,608 | 5 | 4 | 5 | 13 | 2 | 8 | 4 | 35 |
| Total | 137 | -180 | 27 | 39 | 71 | 101 | 43 | 64 | 26 | 20 |

**S2 (against-MIL veto + R4 spacing; REJECTED)**

| Day | n | Net $ | CLM | sg | red | with MIL | <=10m | rebuy<=15m | after claim | med hold |
|---|---|---|---|---|---|---|---|---|---|---|
| 02-05 | 10 | +32 | 2 | 4 | 4 | 10 | 3 | 4 | 2 | 20 |
| 02-19 | 7 | -294 | 0 | 2 | 5 | 7 | 2 | 2 | 0 | 25 |
| 03-05 | 11 | -908 | 1 | 4 | 6 | 11 | 4 | 2 | 1 | 15 |
| 03-19 | 11 | -1,516 | 2 | 3 | 6 | 11 | 6 | 3 | 2 | 10 |
| 04-02 | 9 | +392 | 4 | 1 | 4 | 9 | 2 | 3 | 4 | 45 |
| 04-16 | 7 | -262 | 1 | 2 | 4 | 7 | 1 | 3 | 1 | 40 |
| 04-30 | 7 | +1,242 | 4 | 0 | 3 | 7 | 1 | 3 | 3 | 40 |
| 05-14 | 10 | -1,086 | 0 | 3 | 7 | 10 | 4 | 3 | 0 | 15 |
| 05-28 | 9 | +332 | 3 | 4 | 2 | 9 | 1 | 3 | 3 | 30 |
| Total | 81 | -2,068 | 17 | 23 | 41 | 81 | 24 | 26 | 16 | 25 |

**S3 (claim at >= 2 x ATR while green; INTERIM)**

| Day | n | Net $ | CLM | sg | red | with MIL | <=10m | rebuy<=15m | after claim | med hold |
|---|---|---|---|---|---|---|---|---|---|---|
| 02-05 | 20 | +200 | 5 | 5 | 10 | 12 | 12 | 13 | 4 | 10 |
| 02-19 | 13 | +350 | 7 | 1 | 5 | 12 | 2 | 6 | 7 | 25 |
| 03-05 | 23 | -1,948 | 5 | 2 | 16 | 12 | 12 | 17 | 5 | 10 |
| 03-19 | 21 | -980 | 7 | 3 | 11 | 14 | 5 | 14 | 6 | 15 |
| 04-02 | 17 | +1,010 | 8 | 2 | 7 | 13 | 3 | 10 | 8 | 20 |
| 04-16 | 12 | -880 | 4 | 1 | 7 | 12 | 3 | 6 | 4 | 28 |
| Total | 106 | -2,248 | 36 | 14 | 56 | 75 | 37 | 66 | 34 | 15 |

Same six days under S1b: 95 trades, -$842, 3 of 6 positive, worst -$1,204.

**The day's trade number is the cleanest churn picture.** Win count and net by the order of the trade within its day:

| Trade # | S1b n / wins / net | S2 | S3 (interim) |
|---|---|---|---|
| #1 | 9 / 5 / +$1,550 | 9 / 3 / -$328 | 6 / 5 / +$1,446 |
| #2-3 | 18 / 10 / +$1,948 | 18 / 10 / +$534 | 12 / 6 / +$542 |
| #4-6 | 27 / 13 / -$1,022 | 27 / 14 / -$352 | 18 / 11 / -$156 |
| #7-10 | 36 / 18 / -$344 | 25 / 12 / -$1,428 | 24 / 14 / -$354 |
| #11+ | 47 / 20 / -$2,312 | 2 / 1 / -$494 | 46 / 14 / -$3,726 |

In S1b and S3 the first three trades of the day are the whole profit (+$3,498 and +$1,988), and every trade after the sixth is
net negative (S1b trades #7+: 83 trades, -$2,656; S3: 70 trades, -$4,080). That is a description of what happened, not a cap; it is
the reason the operator's 3-6 is the right shape for this model and not just a preference.

## 3. Per-trade classification (aggregates; full 324-row listing in the Appendix)

Every trade in all three arms carries: side, entry time, hold, P&L, exit class, with/against MIL, entry timing, minutes since the
previous exit, class of the previous exit, held <= 10 min, and the S4(c) verdict. Aggregates:

| Cut | S1b | S2 | S3 (interim) |
|---|---|---|---|
| WITH the MIL | 101 trades, 51 wins, +$1,796 | 81, 40 wins, -$2,068 (veto: all with) | 75, 38 wins, -$712 |
| AGAINST the MIL | 36 trades, 15 wins, -$1,976 | 0 | 31, 12 wins, -$1,536 |
| With-MIL, early third | 8, 75% win, +$1,050 | 10, 70%, +$908 | 6, 67%, +$478 |
| With-MIL, middle third | 38, 63%, +$3,728 | 26, 58%, +$1,458 | 22, 55%, +$236 |
| With-MIL, last third (hindsight) | 55, 38%, -$2,982 | 45, 40%, -$4,434 | 47, 47%, -$1,426 |
| Held <= 10 min | 43, 13 wins, -$2,604 | 24, 7 wins, -$2,812 | 37, 15 wins, -$340 |
| Held > 10 min | 94, 53 wins, +$2,424 | 57, 33 wins, +$744 | 69, 35 wins, -$1,908 |
| Entry right after a CLAIM | 26, 14 wins, +$1,282 | 16, 9 wins, +$192 | 34, 15 wins, -$988 |
| Entry right after a NON-claim | 102, 47 wins, -$3,012 | 56, 28 wins, -$1,932 | 66, 30 wins, -$2,706 |
| Rebuy <=15m after a claim | 17, 8 wins, +$684 | 4, 2 wins, -$98 | 25, 11 wins, -$776 |
| Rebuy <=15m after a non-claim | 47, 21 wins, -$1,130 | 22, 13 wins, +$132 | 41, 18 wins, -$1,962 |
| Red exits that went >= 1 ATR further against within 30 min | 47 of 70 | 27 of 41 | 43 of 56 |
| Red exits back at the entry price within 60 min | 42 of 70 | 25 of 41 | 32 of 56 |

Readings that matter:
1. **The money is in the middle of the move, not the end.** The last-third entries are the loss makers in every arm (but this label uses
   hindsight; the usable causal form is the brief's own "after a fresh extreme" test, which is met every few looks - see section 4a).
2. **Patience on a red trade is a coin with a fat tail.** After the model cut a red trade, price returned to the entry within 60 minutes
   60% / 61% / 57% of the time, but it also went at least one more ATR against within 30 minutes 67% / 66% / 77% of the time. The paths
   are not exclusive (adverse first, recovery later). **No recorded data shows that holding a red trade longer pays;** the case for
   patience rests on the operator's instruction, the S1b long-hold winners (held > 30 min: 34 trades, 74% win, +$4,650) and on the
   fact that the models's own red exits are shallow (median 2-2.5 ATR) against legs that run 100-300 points.
3. **Re-entries after a claim win 54% in S1b and 44% in S3.** The grind exception works on the days it is a grind (04-02) and costs on
   the days it is not (03-05, 03-19). Section 6 tests exactly this.


## 4. What the brief and the page say: lines that push toward churn or impatience, and lines that say the right thing but do not bind

Source: `scripts/sim_week_recursive.py`, `BRIEF_V2` (lines 509-563) and `context()` (lines 313-457); the S3 rule is `reports/recursive_loop/S3.txt`.

### 4a. Lines that license churn or impatience

| Where | Text | Why it pushes the wrong way |
|---|---|---|
| BRIEF_V2 L540-543 | "THE EXCEPTION, and it is great trading: when the tape keeps grinding one way for a large part of the day, keep jumping in and harvesting $200-300 at a time, as many times as it keeps giving. The Asia and London grinds are exactly that. Do not hold back because the count is getting high. Judge each trade, not the total" | The single strongest churn licence. (1) "Asia and London" is the whole 02:00-13:30Z window, so the exception is never off. (2) It has no condition on the previous trade: it does not say the last trade must have been a claimed profit. (3) "Judge each trade, not the total" tells the model to ignore the whole-day view, which is the opposite of what the operator judges by. (4) "Do not hold back" is an instruction to suppress the one hesitation that would help. |
| BRIEF_V2 L534-536 | "AFTER YOU TAKE A PROFIT the same stall is not a new trade. Come back in only when the leg proves itself again with a fresh extreme beyond where it ran to, or when a new leg forms." | Governs only the after-a-profit case, and nothing governs the after-a-loss case, so 47 / 22 / 41 rebuys within 15 min followed a NON-claim (S1b / S2 / S3). The test it offers ("a fresh extreme", "a new leg forms") is cheap: 69-76% of all entries in the three arms cite a fresh or new extreme in their own reason (104 of 137, 59 of 81, 73 of 106), including 30 of 47, 17 of 22 and 24 of 41 of the rebuys that followed a non-claim. A test that 70% of entries pass is not a gate. |
| BRIEF_V2 L525-529 | "IN PROFIT AND THE MOVE IS TIRING (stalling, no new extreme, momentum fading, the shape flattening): TAKE IT. You do not need proof the leg is over, the first honest sign is enough ... Do not hand it back waiting for more." | Impatience on winners. At a 5-minute look, "stalling / no new extreme / flattening" is true of many looks inside a healthy leg. "The first honest sign is enough" sets the evidence bar at one bar. It is the objective-correct instruction for the exit side of Law 0e, but it has no counterweight for the situation where the leg is still driving. |
| BRIEF_V2 L530-532 | "RED: a pullback inside the leg is not a reason to leave. Stay while the leg you joined is intact. If the leg itself has reversed - the move you joined has been undone, not just pulled back - get out; that is a call, not a stop." | Right sentence, defeated by its own second half. "Undone" has no measure, so the model supplies one. 87-93% of all red exits quote the carve-out (58 of 71, 38 of 41, 49 of 56), and the distance at which they do is a median 2.1-2.5 ATR against, the same as a claim. Recorded example, S3 03-05 08:40 short, -$194, held 5 min: "Price has rallied ~39pt (near 2x ATR) off the 24973 low ... the down-leg shorted into has reversed rather than merely pulled back, so cut the loss here." A 2-ATR bounce is being called a reversal. |
| BRIEF_V2 L553-555 | "Legs are big - the median leg on this tape is 298 points over 266 minutes - so even getting in halfway and leaving early still leaves a good trade." | Two scales of "leg". The brief says a leg is 298 pt; the page the model sees draws a leg at every swing of max(40 pt, 25% of the range), which is 1 to 8 per day (3, 4, 8, 6, 1, 7, 3, 8, 6 on the nine days). Every 40-100 pt swing therefore qualifies as "a leg that has proven itself", and "leaving early still leaves a good trade" is read as permission to leave at once. |
| BRIEF_V2 L524 | "That is why you are watching every five minutes - you make the call." | Frames every look as a decision point, which is the opposite of "do not react to sudden changes". |
| S3.txt rule 1 | "if the tape keeps grinding the same way, you may join it again on the usual entry judgement." and "Do not wait for the leg to stall, tire or reverse first" | The re-entry licence is explicit and conditional only on "the usual entry judgement", i.e. the fresh-extreme test above. In S3, 25 rebuys within 15 min followed a claim and lost -$776 (11 wins); 12 of those 25 followed a claim of under 25 points (under $200). |
| `context()` L440-442 | "SO FAR: n trade(s), w winner(s), net $...", "N of them never showed +8pt in your favour", "last exit was N min ago" | A scorecard with no standard to hold it against. "last exit was N min ago" is a clock on idleness: after a claim it reads as "you have been out 20 minutes", which pulls toward re-entry. "never showed +8pt" measures entry quality but says nothing about the count. |
| BRIEF_V2 L517 | "its not urgent to jump in. if we miss most of it, you can still jump in late for 20-30 points and make $200." | Right sentence (see 4b), but it is read as "you can jump in late", i.e. as a licence, rather than "there is no urgency". |

### 4b. Lines that already say the right thing and do not bind

| Where | Text | Why it fails to bind (with the recorded evidence) |
|---|---|---|
| L532-533 | "A red trade means the entry was too early or the leg was not proven yet. The cure is to enter later next time, not to exit sooner." | Correct, and the model is stateless across calls, so "next time" is never now. After a trade that was not a claimed profit the model re-entered within 15 minutes 47 / 22 / 41 times (S1b / S2 / S3). The sentence has no mechanism on the page to make "later" mean anything. |
| L537-539 | "A normal day has a few major legs, so a normal day is a few trades (3 to 6). That is a description, not a limit." | Correct under Law 0e and unbinding by design. 0 of 24 recorded S days fall in 3-6 trades. A description with no scorecard on the page is a sentence the model agrees with and does not apply. |
| L544-546 | "What a high count is really a symptom of is chop and fighting the leg. In one session 23 entries lost $1,882: the 19 entries with the leg made +$1,010, the 4 against it lost $2,892." | The right diagnosis, but it comes after the licence, carries no action, and its example teaches the wrong lesson: "19 entries with the leg made money". In the recorded S days, WITH-MIL entries do not reliably make money (S3: 75 trades, 38 wins, -$712; S2, where only with-MIL entries are allowed: 81 trades, -$2,068). 03-05 (S3) is the same shape as the 23-entry example (23 trades), and both groups lose: with-MIL 12 trades -$752, against-MIL 11 trades -$1,196. |
| L534 / L530 | "Stay while the leg you joined is intact." | Correct. Held 10 minutes or less: 43 / 24 / 37 trades (31 / 30 / 35%). In S1b 30 of the 43 are red and lose -$4,872; in S3 22 of the 37 are red and lose -$4,558, which is more than the whole net loss of the arm (-$2,248). The loss in the book lives in quick reds. |
| L563 | "WAIT when flat and no leg has proven itself." | Correct, but "proven" is the cheap test above, so the model rarely WAITs after an exit: 66 of the 106 S3 entries (62%) came within 15 minutes of the previous exit (S1b 64 of 137, 47%; S2 26 of 81, 32%). |
| `context()` L443-446 comment | `band=False` for v2: "a per-call nag saying AT OR OVER THE LIMIT would silently override it" | The reasoning is right for a hard nag. But removing the v1 band line also removed the only global prompt the model had ("Entering again needs a reason you would defend to him in the morning"). The v2 page now has no whole-day sentence at all. S4(a)/(b) restore one without a cap. |

Read together: the brief gives the model a correct philosophy in six places and a standing exception that voids it in one place, with a page that supplies no day-level number to hold the philosophy against. The exception wins because it is concrete ("as many times as it keeps giving") and the philosophy is abstract ("a few trades").

## 5. The four named days, explained from the recorded S3 trades

All figures are S3 (INTERIM) unless stated; "gate" refers to the S4(c) classification in section 6 (a label on recorded trades, not a re-simulation).

| Day | Net | n | Claimed (n / $) | Red (n / $) | Side flips | Long / Short | Held <= 10 min | With / against MIL |
|---|---|---|---|---|---|---|---|---|
| 03-05 | -$1,948 | 23 | 5 / +$1,366 | 16 / -$3,386 | 12 | 9 / -$576, 14 / -$1,372 | 12 / -$562 | 12 / -$752, 11 / -$1,196 |
| 03-19 | -$980 | 21 | 7 / +$1,194 | 11 / -$2,272 | 7 | 6 / -$1,222, 15 / +$242 | 5 / -$578 | 14 / +$174, 7 / -$1,154 |
| 04-02 | +$1,010 | 17 | 8 / +$1,842 | 7 / -$1,126 | 3 | 4 / +$16, 13 / +$994 | 3 / -$78 | 13 / +$952, 4 / +$58 |
| 02-19 | +$350 | 13 | 7 / +$1,170 | 5 / -$906 | 4 | 8 / -$430, 5 / +$780 | 2 / +$370 | 12 / +$538, 1 / -$188 |

**03-05 (-$1,948): chop, answered with volume.** The day has 6 MILs and 12 side flips in 23 trades.
- Trades 1-8 (02:00-06:15Z) are flat: +$20 net, with three claims (03:25 S +$260, 05:40 S +$140, 06:00 S +$322).
- The 06:00 short claim is followed at 06:15 by a rebuy (a "fresh extreme below my last exit") that loses -$210 in 10 minutes, and at 06:35 by a second rebuy after that red: -$522, entry reason "worth rejoining after the last stop-out". That is the clearest recorded case of the model treating its own red as a licence to try again. Chain 06:00-06:35: +$322 - $210 - $522 = -$410. The gate would keep 06:15 (claim, running) and block 06:35 (after red).
- Trades 12-22 (08:05-11:30Z): 11 trades, 1 winner (a 5-minute +$478 long claim at 09:05), net -$1,312. Nine of the 11 are held <= 10 minutes, seven are against the MIL, and the sides run S, S, S, L, S, S, L, L, S, S, L. The entry reasons at 08:30, 08:40, 10:50 and 11:00 each cite a fresh low or lower 15-minute closes, while the 11:00 exit reason describes the same tape as "chopped in a 25082-25143 range for two hours". The model reads a flat range as a new leg again and again, and the exits at 08:30, 08:40, 10:50 and 11:00 each say the leg was "undone" or "reversed" after a 36-39 pt bounce (08:30, 08:40) or a grind back through entry (10:50, 11:00). The day is less a bad entry rule than a day with no leg, in which the page still draws 6.
- Diagnosis: churn (23 trades) in a chop; entry quality about coin-flip; exit symmetric. A tape with no leg, where WAIT is the correct answer for three hours, produced 11 trades.

**03-19 (-$980): the counter-direction longs.** The day's tape runs down for the whole window; shorts: 15 trades, +$242. Longs: 6 trades, -$1,222. Four of the six longs are 06:15, 08:15, 09:00, 09:50 (-$160, -$234, -$522, -$184 = -$1,100), all flagged "against the MIL", i.e. entries into a bounce inside the larger down leg. The -$522 at 09:00 is tied for the worst trade of the arm (with 03-05 06:35); it was taken 10 minutes after a +$42 small green short. A second contribution: three claim-then-rebuy losses at 02:35 L -$282 (10 min after a +$160 claim), 05:50 S -$240 (5 min after a +$202 claim) and 11:35 S -$194. Diagnosis: entry against the larger leg, the one thing the brief says never to do, because the model's leg is the page's 40-100 pt swing and not the day's.

**04-02 (+$1,010): a real grind, harvested and then given back about even.** Trades 1-5 (02:05-04:55Z), all SHORT in the Asia down-grind, are +$312, -$2, +$236, +$188, +$296: +$1,030 from five trades, four of them claims, held 10-55 min. After 05:00Z the same day is 12 trades, -$20 net. It is the clearest S3 example of the grind exception working as the operator describes it: 03:05 S +$236 (claim), a rebuy 10 minutes later at 03:50 S +$188 (claim), a rebuy 15 minutes later at 04:55 S +$296 (claim). The S1b arm has the same pattern on 05-28 (02:15 S +$182, 03:05 S +$1,268 held 50 min, 04:00 S +$150: three chained shorts, two claims and a small green, +$1,600) and 04-30 (02:20 S two trades +$528; 04:05 S two trades +$476). The gate would also have removed the rebuy at 05:55 S -$190 (price back inside the exit, 5 minutes after the 04:55 claim). The first five trades alone sum to +$1,030, the shape the operator describes (five trades, four claims).

**02-19 (+$350): a good short chain between five long losers.** The day's profit is one chain of four shorts at 08:50 +$176, 09:05 +$326, 09:45 +$194 and 10:10 -$8 = +$688; the 08:50 entry follows a red, the next three each follow a claim. Longs lose -$430 across 8 trades (07:30 L -$296 five minutes after a +$120 claim; 11:25 L -$188; 12:25 L -$302). 12 of 13 trades are with the MIL, so the loss is not against-the-leg entry; it is the late-morning and midday long entries (11:25, 12:25), which are two of the five reds and follow non-claims. A day with 7 claims and +$1,170 of claimed dollars earned +$350 because five red trades took back -$906.

**What the four days say together.** The winning days earn their money in 4-5 trades inside a real directional stretch (04-02 trades 1-5, 02-19 trades 8-11) and give a large fraction back in the 8-12 trades that follow. The losing days have no stretch and produce the volume anyway. By trade order the same picture holds across all days: S3 trades #1-3 of the day sum to +$1,988 and trades #7 onward (70 trades) to -$4,080 (section 2).


## 6. The test: "no claimed profit means no re-entry" (counts before dollars, Law L10)

**Method, and what it is not.** Each recorded trade is labelled with what the S4(c) gate would have decided at the moment of entry, using only information that existed then:
- KEEP if it is the first trade of the day; or the first trade in a MIL (the 7 x ATR tracker, causal) not yet traded that day; or the previous trade was a CLAIMED profit (green, >= 2 x ATR at exit) AND the entry is on the same side AND price at entry is still beyond the previous exit price in the trade's direction ("still running").
- Otherwise the trade is labelled REMOVED.

This is a classification of recorded trades. It is **not** a re-simulation: if the model had been told not to take a REMOVED trade, every later decision that day would have been different (119 failed calibrations). The dollar sums of the sets are shown only after the counts, and they are bookkeeping, not forecasts.

Two further caveats. The MIL is not on the S1b / S3 page, so the model did not see it; the label is applied as an observer. And the MIL lags at turns, so a genuinely new leg at a turn can be labelled "same MIL" (the worst blocked winner below is of that kind).

### 6a. Counts

| | S1b (9 d) | S2 (9 d) | S3 (6 d, INTERIM) |
|---|---|---|---|
| Trades recorded | 137 | 81 | 106 |
| KEPT by the gate | 63 (7.0 / day) | 57 (6.3 / day) | 48 (8.0 / day) |
| REMOVED by the gate | 74 (54%) | 24 (30%) | 58 (55%) |
| Win rate of KEPT | 56% | 51% | 54% |
| Win rate of REMOVED | 42% | 46% | 41% |
| REMOVED, by reason | after red 47, after small green 24, after claim but opposite side 3 | after red 12, after small green 9, after claim but price back inside exit 3 | after red 39, after small green 8, after claim but price back inside exit 8, after claim opposite side 3 |
| KEPT, by reason | first of day 9, new MIL 37, claim + still running 17 | first of day 9, new MIL 38, claim + still running 10 | first of day 6, new MIL 26, claim + still running 16 |
| REMOVED trades held <= 10 min (of which red) | 29 (20) | 10 (6) | 20 (14) |
| REMOVED winners (count) | 31 | 11 | 24 |
| REMOVED winners that were CLAIMS | 12 | 5 | 15 |
| REMOVED winners >= $400 | 4 | 3 | 2 |
| Days on which the REMOVED set has a positive sum | 3 of 9 (02-05, 02-19, 04-30) | 2 of 9 (02-05, 04-30) | 1 of 6 (04-02) |

Read the counts first:
1. **The gate does not reach 3-6 trades a day by itself.** It leaves 6.3-8.0 per day. The other 3 to 4 trades a day must come from (a), (b) and (d) changing what the model does, not from (c). A pass criterion of "mean <= 6" on (c) alone would be failed by construction.
2. **It removes 54-55% of trades in the two churn-heavy arms** (S1b, S3) and 30% in S2 (where R4 spacing already blocked many). It removes roughly 7-8 trades per day.
3. **It discriminates, modestly.** Removed trades win 41-46% and kept trades 51-56%; a random removal would leave both at about 49%. A difference of 5 to 15 percentage points on 24 to 74 trades per arm is not strong evidence.
4. **The re-entry tier that the exception exists to protect is not clearly good in the records.** "Claim and still running" is 17 / 10 / 16 trades with 9 / 6 / 6 wins; by dollars +522 / -508 / -516 for the same-side rebuy-within-15-min subset (14 / 3 / 16 trades). Pooled across the three arms, rebuys after a claim within 15 minutes are 46 trades, 21 wins (46%), -$190; rebuys within 15 minutes after a non-claim are 110 trades, 52 wins (47%), -$2,960. What the gate removes is the larger and worse pool; what it keeps is roughly breakeven on the data we have, not a demonstrated edge.
5. **The timing of the rebuy matters more than its existence.** Among same-side rebuys after a claim where price was still beyond the exit at entry (all three arms, n = 48): those at the very next look (5 min) were 18 trades, 7 wins, -$1,474; at 10 min 10 trades, 4 wins, -$120; at 15 min or later 20 trades, 12 wins, +$2,086. This matches the operator's words ("then in a few minutes it's still grinding") better than the gate's "still running" condition at entry does. The sample is small (n = 18 and 20) and in-sample, so it is a reason to word the gate as a wait, not a measured edge.
6. **A claim that is small is not a claim.** Of 36 S3 claims, 17 were under 25 points (under $200 at 4 lots; the smallest 9.5 pt = $70, ATR 4.2) and 19 were under $200 net. 12 of the 25 post-claim rebuys in S3 followed such a claim (6 wins, -$256); the 13 that followed a >= 25-pt claim were 5 wins, -$520. The brief's own floor is MIN_TARGET_PT = 20 pt and the operator's phrase is "a decent profit ... $200-300". A claim defined as only 2 x ATR is the whole loophole in a quiet tape.

### 6b. The worst blocked winners (what the rule costs)

| Arm | Trade | Gate reason | Comment |
|---|---|---|---|
| S3 | 02-05 12:35 S, 15 min, +$608 (claim) | after red (12:10 L, -$472, 15 min before) | A short at what was in fact a reversal of the long that had just lost. The MIL had not flipped, so it is labelled same-MIL. This is the sort of trade a one-per-MIL rule blocks and the operator would have wanted. |
| S3 | 03-05 09:05 L, 5 min, +$478 (claim) | after red | Held 5 minutes, a +60.6 pt long claimed at 3 x ATR (the 2-ATR target was 40.3 pt); sits inside the 08:05-11:30 chop (the other 10 trades there lost -$1,790). |
| S1b | 02-19 09:05 S, 55 min, +$506 | after small green | Part of the 02-19 short chain. |
| S1b | 05-28 12:30 L, +$488 | after small green | |
| S2 | 04-30 04:05 S, +$702 | after red | The largest single blocked winner in the data. |

For scale: removed winners sum to +$5,326 / +$2,604 / +$4,470 and removed losers to -$8,462 / -$3,784 / -$7,544. Per arm, the REMOVED set sums to -$3,136 / -$1,180 / -$3,074. That is a bookkeeping total, and the net is negative in each arm, but the winners given up are real: 12 / 5 / 15 of them were claims worth +$3,572 / +$2,068 / +$3,514. **A claim given up is a direct cost to the "claim profit" objective**, and the gate has no way of knowing which blocked trade is the 02-05 +$608.

### 6c. Day-level count effects (labels, not a P&L estimate)

- S3: the REMOVED set sums to a negative on 5 of 6 days (02-05 -$566, 02-19 -$34, 03-05 -$1,158, 03-19 -$666, 04-16 -$1,030) and positive on 04-02 (+$380), the best day. The gate would have thinned the one day it should not. The two worst days (03-05, 03-19) shed 17 and 10 of 23 and 21 trades respectively.
- S1b: negative on 6 of 9 days, positive on 02-05 (+$178), 02-19 (+$534), 04-30 (+$60).
- Day counts of positive days using only the KEPT trades (bookkeeping): S1b 6 of 9 versus 5 of 9 actual; S3 4 of 6 versus 3 of 6; S2 4 of 9 versus 4 of 9. Worst day by the same bookkeeping: S1b -$962 versus -$1,490; S3 -$790 versus -$1,948; S2 -$538 versus -$1,516. This is the direction S4 is meant to move and the order of magnitude (worst day roughly halved), but it carries the re-simulation caveat in full.

**What I conclude from the count test.** "No claimed profit, no re-entry" is the correct direction for the objectives: it removes 41-46%-win trades, the quick reds, and the middle of the day's churn, and it keeps the first trade of the day, which is the best trade in all three arms (S1b 9 trades +$1,550, S3 6 trades +$1,446). Its cost is a small number of large blocked winners. It is not, on this evidence, an edge that adds dollars; it is a consistency and churn instrument, and should be judged on those counts.

## 7. Consistency (Law 0): where the problem sits

| | S1b (9 d) | S2 (9 d) | S3 (6 d, INTERIM) |
|---|---|---|---|
| Net, $/day | -$180, -$20 | -$2,068, -$230 | -$2,248, -$375 |
| Days positive | 5 of 9 | 4 of 9 | 3 of 6 |
| Worst day | -$1,490 (05-14) | -$1,516 (03-19) | -$1,948 (03-05) |
| Daily SD | $1,042 | $802 | $989 |
| Largest day's share of positive-day dollars | 39% (05-28, +$1,608) | 62% (04-30, +$1,242) | 65% (04-02, +$1,010) |
| Spread / mean | undefined (negative mean) | undefined | undefined |

The "spread / mean" test in `bible.gate` is not computable on any arm because the mean is negative. In plain terms none of the arms passes Law 0: S3 on its six days fails the gate against S1b on the same six days on worst day (-$1,948 vs -$1,204) and on $/day (days positive are equal, 3 of 6).

**Entries, exits or churn?** All three, in this order of measurable weight:
1. **Churn (the same trades as the quick reds).** 66 / 26 / 66 rebuys within 15 minutes; trade # 7 onward is net negative in S1b (83 trades, -$2,656) and S3 (70 trades, -$4,080) while trades #1-3 of each day are positive (+$3,498, +$1,988). The extra trades are not special bad trades; they are ordinary trades whose only fault is that a day cannot absorb 15 of them at a 47-50% hit rate and a symmetric bracket. Held <= 10 minutes and red: S1b 30 trades -$4,872; S3 22 trades -$4,558, which is larger than the arm's net.
2. **Exits (symmetry).** Claimed winners average +$345 / +$298 / +$233; red trades average -$183 / -$215 / -$216; the median red exit is -20 to -26 pt (2.1-2.5 ATR), as far as a claim target. The book is a +/-2-ATR bracket, so the hit rate decides the sign and it is about 47-49% exits in profit. S3 doubled claims per day (3.0 to 6.0) but made them smaller and faster (median hold 35 min to 15) and did not reduce reds (7.9 to 9.3 per day). The operator's "claim profit" objective is in tension with his "do not exit quickly" objective, and S3 resolved it entirely toward claiming.
3. **Entries.** About half of entries are red. The hindsight split puts the loss in the last third of the MIL (S1b: 55 trades, 38% wins, -$2,982), but a causal split is not possible from this data and must not become an instruction. The causal evidence is the first trade of the day (S1b +$1,550, S3 +$1,446) and the first trade in a new MIL (S1b 37 trades, 57% wins, +$1,602; S3 26 trades, 58% wins, -$64; S2 38 trades, 53%, -$732), which is positive but not stable.

The consistent-days lever is therefore the count of trades after the first productive stretch, not the quality of the first trade. That is what S4(a)-(c) target, and (d) addresses the exit side.


## 8. Audit of the four S4 changes (wording, risks, collisions)

Status of what the page already shows: `context()` already prints the model's trade list and a SO FAR line ("n trade(s), w winner(s), net $..."), a "N of them never showed +8pt" line and "last exit was N min ago". So S4(b) is an extension of an existing block, not a new idea, and the existing block has not moved the count (0 of 24 recorded S days in 3-6 trades). What is missing is any number the model can hold the day against, and any statement that the day, not the trade, is the thing judged.

### 8a. S4(a) State the day's job: a few well-chosen legs; a count above about 6 needs a stated reason

Risks:
1. **The sentence already exists and does not bind.** BRIEF_V2 L537-539 says 3 to 6 is a normal day; 0 of 24 days landed there. Adding the same sentence again, in the brief, is the weakest possible form of (a). It has to be a number on the page (see 8b and section 10), not more prose.
2. **"Well-chosen legs" has two scales.** The brief's leg is 298 pt over 266 min (L553-555); the page's leg is every swing of max(40 pt, 25% of the range so far), 1-8 a day. "A few legs" is satisfied by 6 small page legs. Pick ONE scale for the day's job and use it everywhere. The only day-scale object the harness already computes is the MIL (7 x ATR retrace; 3-10 flips a day), so the unit should be "major move" = MIL, shown as a number.
3. **"Needs a stated reason" is a free-text hurdle.** A model that is asked for a reason will write one. 69-76% of recorded entries already cite "a fresh extreme" or "a new leg" (104 of 137, 59 of 81, 73 of 106). If the reason is free, it becomes boilerplate ("the grind continues"). Make the ONLY accepted reason a fact the page can check: "my last trade was a claimed profit of $X at HH:MM and price is still beyond where I claimed". That folds (a) into (c) and removes the free-text loophole.
4. **Anchoring risk (accidental cap).** A printed "about 6" can become a ceiling the model stops at even when the tape is giving. It is the 04-02 shape: five trades +$1,030 (S3 trades 1-5, four claims), and a model that stops at 6 on a day like that gives up little, but a day with a real grind and claims every 15 minutes should not be stopped. Law 0e forbids a cap. Guard it by wording ("a description, not a limit; above 6 the only reason is the claim-and-running test") and by measurement (histogram of trades/day: if more than a third of days stop at exactly 6 or 7 while the tape was still running, the sentence has become a cap).
5. **Inverse risk: idleness.** The first-trade-of-day is the best trade in every arm (S1b 9 trades +$1,550, S3 6 trades +$1,446). A "do less" message must not suppress it. Count a day with fewer than 2 trades as a measurement flag (section 9).

### 8b. S4(b) Show the model its own day: trades so far, MILs traded, time since last claim, whether this MIL already has a trade

Risks:
1. **MIL is not on the S1b or S3 page.** Showing "MILs traded" and "this MIL already has a trade" requires putting the MIL on the page. That recreates the S2 display (S2 showed the MIL when flat with "NOT ALLOWED" lines and was REJECTED: 9 days, -$2,068, 4 of 9 positive, worst -$1,516). The cause of the S2 failure is not established (it also had R4 spacing, L8), but the safe form is a bare label with no instruction attached: "MIL 3, began 06:10Z, 1 trade so far". Never a direction word (UP/DOWN) and never "NOT ALLOWED"; the first is a turn call (Law L9) and the second is the S2 veto.
2. **The MIL lags at turns and it flips 3-10 times a day.** A genuinely new leg is labelled as the old MIL until the 7 x ATR retrace has happened. A one-per-MIL gate therefore blocks the first trade of a new leg at exactly the moment the operator wants "enter a little earlier". Recorded cost: S3 02-05 12:35 S +$608 (15 min claim) and S2 04-30 04:05 S +$702, the two largest blocked winners. Keep the first-trade-of-day exempt (it is the best trade) and accept the cost knowingly; do not paper over it with a "unless you are sure" clause, which re-opens the loophole.
3. **"Time since last claim" can become a clock on idleness.** "last exit was N min ago" is printed today; after a claim it reads as "you have been out 20 minutes", pulling toward re-entry. 66 of 106 S3 entries (62%) came within 15 minutes of the previous exit. I cannot show the line causes this (no ablation exists), but removing a clock that has no purpose is free. Replace it with the information that matters: the last CLAIM (time, $) and "since that claim: k trades, net $".
4. **The page must compute "claimed"; the model must not.** If the model decides whether its last trade was a claim, the 2 x ATR definition in a quiet tape (ATR 4.2 = 9.5 pt = $70; 17 of 36 S3 claims were under 25 pt) is gamed without any bad intent. The harness should print "last trade: CLAIMED +$296 (>= 2 ATR and >= $200)" or "NOT a claim: +$98 is below $200". The $200 floor is the operator's own phrase ("a decent profit ... $200-300") and equals 25 pt at 4 lots and $8/pt, which is also above the brief's MIN_TARGET_PT 20.
5. **A test must prove the numbers on the page equal the ledger** (armed is not verified). A scorecard that says "1 trade in this MIL" when the harness ledger says 3 is worse than none.

### 8c. S4(c) The grind exception becomes a gate

Wording problems in the stated rule ("re-enter only if the LAST trade was a CLAIMED profit (about >= 2 x ATR) AND the same-direction move is still running a few minutes later; otherwise one trade per MIL"):
1. **"About >= 2 x ATR" is the loophole** (see 8b.4). Use "closed green, at least 2 ATR AND at least $200".
2. **"A few minutes later" is shorter than the model's look.** The cadence is 5 minutes, so the earliest "few minutes later" is the very next look. The recorded rebuys after a claim, where price was still beyond the exit when the model re-entered (all three arms pooled, n = 48): at the next look (5 min) 18 trades, 7 wins, -$1,474; at 10 min 10 trades, 4 wins, -$120; at 15 min or later 20 trades, 12 wins, +$2,086. Small samples, in-sample; I offer them as a reason to word the gate as three looks (15 minutes), not as an estimate. This is also what the operator's own sentence says: "then in a few minutes it's still grinding".
3. **"Still running" is cheap.** My observer label used "price at entry is beyond the previous exit price in the trade's direction", which 16 of the 25 recorded S3 post-claim rebuys met (14 of 17 in S1b), and only 7 of those 16 (6 of 14 in S1b) won. Use "price is beyond the best price reached in the claimed trade", and have the page print the claimed trade's extreme and the current price so the model does not estimate.
4. **"Otherwise one trade per MIL" is a loss-triggered lockout.** After a red in a MIL the model may not trade that MIL again. This is not a loss-exit (no open position is closed), but it has the shape of the old rule 1 ("after two losers in that state, stop for the day"), which the pre-iteration audit caught as a hidden confound on 2026-10-06. Word it ONLY as a condition on the next entry ("a new entry needs either a new MIL or a claim"), never "stop for the day", never "after two losers", and never as a condition on staying in the current trade.
5. **Which of "the usual entry judgement" and the gate wins?** S3.txt rule 1 says "you may join it again on the usual entry judgement". That sentence must be replaced, not left beside the gate, or the model has two rules that disagree (L8: one rule changed is not one rule isolated).
6. **Counts it will and will not produce** (section 6): 6.3-8.0 trades a day remain after the gate, so (c) alone does not deliver 3-6. Pass criteria must not demand 3-6 from (c).

### 8d. S4(d) Patience: do not react to short-lived changes; stay in unless the leg itself has reversed (never a stop or loss-exit)

1. **The carve-out is the exact sentence the loser exits already quote.** 87-93% of red exits cite "the leg itself has reversed" (58 of 71, 38 of 41, 49 of 56), at a median 2.1-2.5 ATR against. Re-stating "unless the leg itself has reversed" re-licenses them. There is no objective definition of "reversed" that is not a stop (any price level is a stop; Law 0e forbids it) and no vague one that binds. The workable middle is to bind the EXPLANATION: an exit inside the first 10 minutes must name the day-scale move that has turned (the MIL, or the move since 02:00Z), not the 5-minute bar. That is also the operator's "toggle between day view and close-in view".
2. **Direct collisions in the existing text.** (i) BRIEF_V2 L525-529 says "the first honest sign is enough ... do not hand it back" on a tiring winner. (d) says do not react to short-lived changes. (ii) S3 rule 1 says "Do not wait for the leg to stall, tire or reverse first" at 2 ATR. The three can be reconciled only by scoping: (d) applies BELOW the claim level (a green trade that has not reached $200 / 2 ATR, and any red trade); at or above the claim level, S3 stands. That scoping must be written in the rule, or the model will pick whichever sentence is nearest.
3. **The recorded data does not show that holding a RED longer pays.** After the red exits, price went at least one more ATR against the position at some point within 30 minutes in 47 of 70 (S1b), 27 of 41 (S2) and 43 of 56 (S3) cases; it was also back at the entry price within 60 minutes in 42 / 25 / 32 of them. Both happen (adverse first, recovery later). Patience on reds is therefore an operator instruction, not a measured improvement, and it carries bag-holding risk (reds held over 60 minutes already cost -$608 on 3 trades in S1b, -$200 on 2 in S2, -$790 on 3 in S3; the worst single trade in any arm is -$622). Monitor that tail (section 9) rather than assume it is benign.
4. **The data does support patience on the way in and on greens.** Trades held more than 30 minutes: S1b 34 trades, 25 wins, +$4,650; S2 28 trades, 20 wins, +$2,362; S3 20 trades, 10 wins, -$344. Trades held 10 minutes or less: S1b 43 trades, 13 wins, -$2,604; S2 24, 7 wins, -$2,812; S3 37, 15 wins, -$340. Selection partly explains it (a trade that works is held longer, and a red median is 15 minutes), so this is an association, not a measured effect of holding. The S3 claim rule moved the winners' exit earlier (median hold 35 to 15 minutes) and the over-30-minute group went from 74% to 50% wins. After S3 claims, price went at least 1 ATR back against the closed position within 30 minutes in 29 of 36 cases (S1b 15 of 27) and at least 1 ATR further in the direction in 16 of 36 (S1b 20 of 27); both are "at some point" measures. The claim itself did not look premature.
5. **"Do not react to sudden changes" can be misread as "ignore everything".** A 5-minute look is a sudden-change detector by construction. The brief should say what to do instead of reacting: look at the day-scale view first (section 10) and write what it shows before deciding.

### 8e. Collisions, accidental caps and loss-exits: summary

| Item | Collides with / creates | Severity | Fix |
|---|---|---|---|
| (c) one-per-MIL needs MIL on the page | S2 display (REJECTED); MIL lag blocks new-leg trades | Medium | Bare numbered label, no direction word, no "NOT ALLOWED"; first trade of day exempt |
| (c) "claimed about >= 2 ATR" | Quiet-tape claims of 9.5-25 pt (17 of 36 S3 claims) | High | ">= 2 ATR AND >= $200", computed by the harness and printed on the page |
| (c) vs S3 rule 1 "usual entry judgement" | Two rules that disagree | High | Replace the sentence; do not append |
| (c) lockout after a red | Looks like the old "stop after two losers" clause (preflight confound) | Medium | Entry condition on the NEXT entry only; no "for the day" |
| (d) vs L525-529 "first honest sign is enough" | Same brief, opposite instructions | High | Scope: first-sign exit only at or above the claim level |
| (d) "leg itself has reversed" | The carve-out 87-93% of red exits already quote | High | Bind the explanation (day-scale move named), not a price |
| (a) "about 6" | Anchoring cap; L0e says no cap | Medium | "description not a limit"; only valid reason above 6 is the claim-and-running test; monitor histogram |
| (a) "a few legs" | Brief leg 298 pt vs page leg 40-100 pt | Medium | One unit: the numbered MIL |
| (b) "last exit N min ago" | Clock on idleness | Low-Medium | Replace with last claim and since-claim net |
| (d) patience on reds | Bag-holding tail | Medium | Monitor largest loss and reds over 60 min; never write a price for it |
| None of the four creates a stop, a loss-exit or a count cap as worded, PROVIDED the fixes above are made and the lockout is worded as an entry condition only. | | | |

### 8f. Bundling four changes (L2, L8) and interpretation

Law L2 says one rule per iteration and L8 says one rule changed is not one rule isolated. The operator has decided to ship all four together. I do not re-open that. Two things make the bundle readable:
1. **Pre-declare each change's own count signature** before the run, so a single run can still be read per change: (a)+(b) should move trades/day and the "after a non-claim rebuy" count; (c) should move the share of re-entries that follow a claim and the rebuys within 15 minutes; (d) should move median hold and the share held 10 minutes or less. If trades/day falls but median hold does not move, (d) did not bind (the carve-out won). If median hold rises and trades/day does not fall, (a)-(c) did not bind.
2. **Do not read dollars as attribution.** The 9-day standard error of the mean is about $350/day, the same size as any plausible effect (floor $324/day). A single bundle run cannot say which change helped or hurt. If one ablation is affordable, make it S4 without (d): (d) is the change most likely to hurt consistency (bag-holding) and the one the data supports least.

## 9. Measurement setup and pass criteria

**Set-up.**
1. Same nine days as S1b and S2 (02-05, 02-19, 03-05, 03-19, 04-02, 04-16, 04-30, 05-14, 05-28), same window (02:00Z-13:30Z), 5-minute cadence, 4 lots, a fresh tag (for example `sline_s4`), declared before the run (L3), with the rules file and the exact page changes hashed into every day record as the shadow runner does. Poisoned days (error rate above 10%) are excluded and re-run (L7). The held-out weeks are not used.
2. **Contamination note.** These nine days were used to choose the wording in this review. The count signatures are fair to read on them; the dollar comparison is in-sample for the wording. The confirming run should use days that were not read for writing S4, chosen by the operator, from outside the permanently held-out weeks.
3. Compare S4 against S1b (the baseline) on all nine days with `bible.gate`, and against S3 on its six days as a labelled interim comparison only. S3 is interim (L6) and S2 is rejected; neither is the bar.
4. Log per day: every look's page scorecard values (trade count, MIL number, trades in this MIL, last claim time and $), the model's DAY/BOOK reason prefix (section 10), and the harness's own S4(c) label of each entry (kept or violating). A violating entry means the page told the model "WAIT" and it entered anyway; that is a direct compliance count, independent of dollars.
5. Add a test that the page numbers equal the ledger.

**Pass criteria, counts first (my proposals; baselines are the recorded S1b / S3 numbers).**

| # | Count criterion | Baseline S1b / S3 | Pass | Notes |
|---|---|---|---|---|
| 1 | Trades per day, mean (9 d) | 15.2 / 17.7 | <= 8, and no day above 12 | (c) alone leaves 6.3-8.0; do not demand 3-6 of it |
| 2 | Days in the 3-6 range | 0 of 9 / 0 of 6 | >= 3 of 9 | Stretch: mean <= 6. Flag, do not fail, if a third of days stop at exactly 6-7 |
| 3 | Days with fewer than 2 trades | 0 | 0 (flag any) | Guard against idleness and an accidental cap |
| 4 | Rebuys within 15 min of the previous exit, per day | 7.1 / 11.0 | <= 3 | Counted by the harness from timestamps |
| 5 | Share of re-entries (entries in a MIL already traded) that follow a claim of >= 2 ATR and >= $200 | 19% (17 of 91 re-entries) / 22% (16 of 74) meet the claim-and-running test | >= 90% | Harness label; model compliance, not P&L |
| 6 | Entries the harness labels as violating the gate | 74 of 137 / 58 of 106 | <= 10% of entries | Same label as section 6 |
| 7 | Median hold, minutes | 20 / 15 | >= 25 | Compare per day, not only pooled |
| 8 | Trades held 10 minutes or less | 31% / 35% | <= 15% | The loss is concentrated here |
| 9 | Exits in profit | 48% / 47% | >= 55% **and** the guards below | Never read alone: taking tiny greens raises it |
| 10 | Guards on 9 | Claims under 25 pt: 17 of 36 (S3); worst trade -$622; reds held over 60 min: 3 trades | Claims under $200: 0 by definition of "claim"; no single trade worse than about -$700; reds held over 60 min <= 3 and total <= $800 | Detects both small-green gaming and bag-holding |

Then dollars, only after the counts pass:
- Days positive >= 6 of 9 (baseline 5 of 9), worst day no worse than about -$1,000 (baseline -$1,490), mean per day above S1b's (-$20), and `bible.gate` dominance against S1b. A positive mean makes spread/mean computable; with a negative mean it is not.
- State that $/day is recorded, not decided, at the $324 floor (L6). The gate verdict, not a higher dollar number, is what promotes S4.
- A pass on counts and a fail on dollars is "behaviour changed, edge not shown"; a pass on dollars and a fail on counts is noise until proven otherwise.

## 10. Why does Claude not figure this out without our briefs, and how do we get it to think globally each time?

The honest answer is that it is doing what the setup rewards.
1. **Every look is a fresh, stateless call.** The model has no memory between looks; "enter later next time" (L532-533) cannot be carried out because next time never knows it was this time. Whatever must persist has to be on the page.
2. **The page and the brief reward the local view.** The page leads with the last few bars and the current leg; its only measure of how it is doing is a per-trade list and a SO FAR sum. The brief tells it "judge each trade, not the total" (L543) and "you make the call" every five minutes (L524). The concrete, immediate evidence (a fresh low) beats the abstract goal (a few trades, a positive day) every time.
3. **The test it is given is cheap.** "A fresh extreme or a new leg" is passed by 69-76% of its own entries.
4. **A 5-minute look on a 5-minute chart is a sudden-change detector.** Patience cannot be reactive and also be evaluated every five minutes from the same bars.
5. **It is never told what it is judged on.** The operator judges the DAY by days-positive, worst day and spread; the model is told neither the standard nor how its day is going against it.

What on the page and in the prompt would make the whole-day view the thing it is judged on (hypotheses to be tested under L3; none is a prediction or a turn call):
1. **Put a DAY SCORECARD at the TOP of the page, computed by the harness, in fixed format**, before the bars: day-so-far net, trades so far, MIL number and age, trades in this MIL, last claim (time, $, claimed or not), trades and net since that claim, and one line "THE DAY IS JUDGED AT 13:30Z ON NET AND ON HAVING FEW, WELL-CHOSEN TRADES, NOT ON THIS TRADE".
2. **Two views in a fixed order, as the operator asked ("toggle between day view and close-in view")**: first the DAY VIEW (the whole window since 02:00Z, the major move, where price sits in the day's range), then the CLOSE-IN VIEW (the last hour). The decision request comes after both, and the model is asked to read in that order.
3. **A fixed-format prefix on the `reason` field**, filled before the decision: `DAY: <what the day has done so far, in a few words>. BOOK: <trade count, last claim, this MIL's trades>. NOW: <what the close-in view shows>.` The first thing the model writes is then the whole-day check. This is a description, not a forecast. It is a hypothesis: a prefix can become boilerplate, so measure whether it is ever different from the previous look's (section 9 log) and whether entries that violate the gate still write a clean prefix.
4. **Default to WAIT in the wording of the decision itself**: "WAIT unless (1) this is your first trade today, or (2) this is a MIL with no trade yet, or (3) your last trade was a claim of at least $200 and the move is still running three looks later." The brief's current default is the opposite: every look is "you make the call".
5. **Have the nightly review judge the day first.** The review prompt should open with the day-level scorecard (trade count, rebuys, share after a claim, median hold, days-positive) before any trade is discussed, so the one-rule-per-iteration change is chosen against the day's counts.
6. **Test the prompt as the model sees it.** The failure the project has seen twice (laws in a docstring, not the prompt) applies: capture the assembled page and grep for the scorecard, the claim definition and the gate sentence.

## 11. Daily instructions (ready to paste, plain wording)

Each instruction names the recorded trades that justify it and the objective it serves. None is a stop, a loss-exit, a price level or a count cap, and none predicts the next leg or a turn. All trade figures are 4 lots, $8/pt; S3 figures are INTERIM.

1. **A claim is a profit worth having.** "A claim means you closed green, by at least 2 ATR and at least $200. A smaller green exit is fine, but it is not a claim and it does not entitle you to come back in."
   - Evidence: 17 of 36 S3 claims were under 25 pt (smallest 9.5 pt = $70). S3 03-19: 04:05 S +$98 (5 min) was a "claim", followed by a 04:20 S +$98, a 04:45 S -$144, and 05:50 S -$240 five minutes after the 05:30 S +$202 claim. 12 of 25 post-claim rebuys followed a claim under 25 pt.
   - Serves: PROFITABLE, CONSISTENT; defines the word the gate depends on.

2. **One trade per major move, unless the last one was a claim.** "After a trade that was not a claim, do not enter again in the same major move (the MIL number on the page). Wait for the next one."
   - Evidence: S3 03-05: 06:00 S +$322 claim, 06:15 S -$210, then 06:35 S -$522 ("worth rejoining after the last stop-out"); 08:05-11:30 eleven trades, one winner (09:05 L +$478), net -$1,312; 39 of the 58 S3 trades that fail the gate follow a red. S1b: 47 of 74.
   - Serves: 3-6 TRADES (the gate removes 54-55% of trades in the churn-heavy arms), CONSISTENT.
   - Known cost: the gate would have blocked S3 02-05 12:35 S +$608 and S2 04-30 04:05 S +$702.

3. **Rejoin a grind only after a real claim, and only when it is still going.** "If your last trade was a claim, you may rejoin the same direction only when at least three looks (15 minutes) later price is still beyond the best price your claimed trade reached. Not the very next look."
   - Evidence: S3 04-02: 03:05 S +$236 (claim), then 03:50 S +$188 (rebuy 10 min after a claim) and 04:55 S +$296 (rebuy 15 min after a claim), each claimed and the move still running; trades 1-5 sum +$1,030 with four claims. S1b 05-28 02:15 S +$182, 03:05 S +$1,268 (50 min), 04:00 S +$150: +$1,600. Counter-case: 04-02 05:55 S -$190, 5 minutes after the +$296 claim. Pooled same-side rebuys after a claim: next look 18 trades, 7 wins, -$1,474; 15 minutes or later 20 trades, 12 wins, +$2,086 (small, in-sample).
   - Serves: PROFITABLE on grinds, PATIENT, 3-6 with the operator's grind exception kept.

4. **After the sixth trade, only one reason counts.** "From your seventh trade of the day onward, the only valid reason to enter is: my last trade was a claim of at least $200 and the move is still running three looks later. Write that reason; if you cannot, WAIT. This is not a limit; a grind can carry on."
   - Evidence: S3 trades #7 onward, 70 trades, -$4,080; S1b 83 trades, -$2,656; trades 1-3 of each day +$1,988 (S3) and +$3,498 (S1b); 0 of 24 recorded days in 3-6 trades.
   - Serves: 3-6 TRADES, CONSISTENT.

5. **Leave early only for the day-scale move.** "Before you leave a trade in its first 10 minutes, say what the day-scale move is doing, not what the last bar did. A bounce of one or two ATR on a five-minute chart is not by itself the leg reversing."
   - Evidence: held 10 minutes or less: S1b 43 trades, 13 wins, -$2,604; S3 37 trades, 15 wins, -$340; 87-93% of red exits quote "the leg itself has reversed" at a median 2.1-2.5 ATR against. S3 03-05 08:30 S -$166 and 08:40 S -$194, each cut after a 36-39 pt bounce, inside the 08:05-11:30 chop that the 11:00 exit reason itself calls a two-hour 25082-25143 range.
   - Serves: PATIENT. Not a stop: it binds the explanation, not the price.
   - Cost: the data does not show holding a red longer pays (47 of 70 S1b red exits went at least 1 ATR further against within 30 minutes).

6. **A green trade below the claim level stays.** "While your trade is green but has not reached a claim, one quiet look or one small bar against you is not a reason to leave. Leave only when the move you joined has clearly stopped making progress over several looks, and say how many."
   - Evidence: held over 30 minutes: S1b 34 trades, 25 wins, +$4,650; S2 28, 20 wins, +$2,362 (association; winners are held longer). S1b 05-28 03:05 S +$1,268 held 50 min. The brief's L525-529 "the first honest sign is enough" is what this replaces below the claim level; at or above the claim level, take it.
   - Serves: PATIENT, PROFITABLE.

7. **Start every reason with the day, then the book, then now.** "Begin your reason with `DAY:` what today has done so far, `BOOK:` your trade count, your last claim, the trades in this major move; then `NOW:` what the last hour shows."
   - Evidence: 0 of 24 days in 3-6 trades although the brief says 3-6; the model's per-trade view is what the page rewards (SO FAR sums, "judge each trade, not the total").
   - Serves: all four objectives, as a format. Hypothesis, to be tested (section 10); it can become boilerplate.

## 12. What to remove or reword in the existing brief and page (it licenses churn or impatience)

| Where | Action | Wording direction |
|---|---|---|
| BRIEF_V2 L540-543 (THE EXCEPTION) | Reword | Delete "Do not hold back because the count is getting high. Judge each trade, not the total" and "The Asia and London grinds are exactly that". Replace with the gate: rejoin only after a claim of at least $200 with the move still running three looks later. |
| BRIEF_V2 L534-536 (AFTER YOU TAKE A PROFIT) | Reword | A fresh extreme or a new leg is not enough; it must be a claim and the move still running past the claimed trade's best price. |
| BRIEF_V2 L525-529 (IN PROFIT AND THE MOVE IS TIRING) | Reword | Scope to the claim level: at or above it take it; below it a tiring look is not a reason to leave. Delete "the first honest sign is enough". |
| BRIEF_V2 L530-532 (RED carve-out) | Reword | Keep "leg itself has reversed" only with the day-scale explanation requirement. |
| BRIEF_V2 L553-555 (legs are big, leaving early still leaves a good trade) | Reword | Keep the 298 pt fact; remove the reading that leaving at once is fine. Say the unit is the numbered major move. |
| BRIEF_V2 L524 ("watching every five minutes - you make the call") | Reword | "Most looks end with no action. The decision to act needs a reason that passes the gate." |
| BRIEF_V2 L544-546 (23-entry example) | Add | Add the recorded S-line fact that entries with the leg also lose when there is no leg: S3 03-05 with the MIL 12 trades -$752, against 11 trades -$1,196. |
| BRIEF_V2 L563 (WAIT when flat and no leg has proven itself) | Reword | "WAIT unless: first trade today, a major move with no trade yet, or a claim of at least $200 with the move still running." |
| `context()` L440-442 "last exit was N min ago" | Replace | "Last claim: HH:MM +$X. Since then: k trades, net $Y." |
| `context()` SO FAR | Add | MIL number and trades in it; a one-line statement of how the day is judged (section 10). |
| S3.txt rule 1 "you may join it again on the usual entry judgement" | Replace, do not append | The gate wording. |
| S3.txt rule 1 "Do not wait for the leg to stall, tire or reverse first" | Keep, scope | At or above the claim level only. |
| Claim definition (S3: 2 x ATR) | Reword | "At least 2 ATR and at least $200". |

## Appendix: per-trade classification, every recorded trade


### S1b (baseline, 9 days)

Columns: # = trade number that day | in = entry time Z | S = side | hold = minutes | $ = P&L | exit = CLM claimed (green and >= 2 x ATR at exit bar) / sg small green / red | MIL = W with, A against the 7xATR major-leg tracker at entry | timing = share of the MIL's eventual extent already travelled at entry (E <1/3, M 1/3-2/3, L >= 2/3; HINDSIGHT label, with-MIL only) | gap = minutes since previous exit | prev = class of previous exit | <=10 = held 10 min or less | S4(c) = K kept / X removed by the claimed-profit gate, with reason

```
day    # in    S hold      $ exit MIL tim gap  prev  <=10 S4(c)
02-05  1 02:05 S   15   +448 CLM  A   -        -     .    K:first
02-05  2 02:25 L   15   +206 sg   A   -     5  CLM   .    K:newMIL
02-05  3 02:50 S   10   +364 sg   A   -    10  sg    y    K:newMIL
02-05  4 03:25 L   10   -372 red  W   M    25  sg    y    X:after small green
02-05  5 03:50 S   10    -98 red  W   L    15  red   y    K:newMIL
02-05  6 04:25 S    5   -154 red  W   L    25  red   y    X:after red
02-05  7 04:40 L   20   +204 CLM  A   -    10  red   .    X:after red
02-05  8 05:20 S    5   -128 red  A   -    20  CLM   y    K:newMIL
02-05  9 05:40 L   15   -256 red  W   M    15  red   .    X:after red
02-05 10 06:35 L   40   +208 CLM  W   M    40  red   .    X:after red
02-05 11 07:20 L   30   -104 red  W   L     5  CLM   .    K:claim+run
02-05 12 08:05 L   25   +182 sg   W   L    15  red   .    X:after red
02-05 13 08:50 S   10   +214 sg   A   -    20  sg    y    X:after small green
02-05 14 09:05 S   15   -304 red  A   -     5  sg    .    X:after small green
02-05 15 09:25 L   10   +116 sg   W   L     5  red   y    X:after red
02-05 16 10:20 L   15   -240 red  A   -    45  sg    .    K:newMIL
02-05 17 10:55 S   20    +24 sg   W   E    20  red   .    X:after red
02-05 18 11:35 S   15   -146 red  W   E    20  sg    .    X:after small green
02-05 19 12:20 S    5   +462 CLM  W   M    30  red   y    X:after red
02-05 20 12:35 S   25   +126 sg   W   L    10  CLM   .    K:claim+run
02-19  1 02:30 L   75    -52 red  W   L        -     .    K:first
02-19  2 04:00 L   25   -112 red  W   L    15  red   .    X:after red
02-19  3 04:55 S   20    +38 sg   W   M    30  red   .    K:newMIL
02-19  4 05:40 L   30    +60 sg   W   M    25  sg    .    K:newMIL
02-19  5 06:30 L   70   +182 CLM  W   M    20  sg    .    X:after small green
02-19  6 07:45 L   60   -272 red  W   L     5  CLM   .    K:claim+run
02-19  7 08:50 S   10   +174 sg   W   E     5  red   y    K:newMIL
02-19  8 09:05 S   55   +506 CLM  W   M     5  sg    .    X:after small green
02-19  9 10:10 S   35     -8 red  W   L    10  CLM   .    K:claim+run
02-19 10 11:15 L   25    -42 red  A   -    30  red   .    X:after red
02-19 11 12:25 L   30   -200 red  W   L    45  red   .    K:newMIL
03-05  1 02:00 S    5    -74 red  W   L        -     y    K:first
03-05  2 02:20 S   25   -130 red  W   L    15  red   .    X:after red
03-05  3 02:50 L    5   -228 red  A   -     5  red   y    X:after red
03-05  4 03:25 S   15    +30 sg   W   L    30  red   .    X:after red
03-05  5 04:15 L   50   +106 sg   A   -    35  sg    .    X:after small green
03-05  6 05:40 S   45   +394 CLM  A   -    35  sg    .    K:newMIL
03-05  7 06:35 S   10    -74 red  W   L    10  CLM   y    K:newMIL
03-05  8 06:50 L   15    +16 sg   A   -     5  red   .    X:after red
03-05  9 07:25 L   25   -260 red  W   M    20  sg    .    K:newMIL
03-05 10 08:05 S   15   -140 red  A   -    15  red   .    X:after red
03-05 11 08:30 S    5   -166 red  A   -    10  red   y    X:after red
03-05 12 08:40 S    5   -194 red  A   -     5  red   y    X:after red
03-05 13 09:05 L   10   +258 sg   W   M    20  red   y    X:after red
03-05 14 09:30 S   20    +80 sg   A   -    15  sg    .    X:after small green
03-05 15 10:15 L    5    -50 red  W   M    25  sg    y    X:after small green
03-05 16 10:30 L   10   -270 red  A   -    10  red   y    K:newMIL
03-05 17 10:50 S   15   -178 red  W   M    10  red   .    X:after red
03-05 18 11:25 L   10   -128 red  A   -    20  red   y    X:after red
03-05 19 11:55 S   15    +18 sg   W   M    20  red   .    X:after red
03-05 20 12:50 S   10    -18 red  W   L    40  sg    y    X:after small green
03-05 21 13:10 S   19   -196 red  W   L    10  red   .    X:after red
03-19  1 02:15 L   35   +164 CLM  W   L        -     .    K:first
03-19  2 03:10 L   20   -222 red  W   L    20  CLM   .    K:claim+run
03-19  3 03:35 S   60   +258 CLM  W   E     5  red   .    K:newMIL
03-19  4 04:40 S   15    +12 sg   W   M     5  CLM   .    K:claim+run
03-19  5 05:45 S   10   -198 red  W   L    50  sg    y    X:after small green
03-19  6 06:15 L   15   -160 red  A   -    20  red   .    X:after red
03-19  7 06:55 S   10    +40 sg   A   -    25  red   y    K:newMIL
03-19  8 07:55 S    5   -204 red  W   M    50  sg    y    K:newMIL
03-19  9 08:05 S    5   -148 red  W   M     5  red   y    X:after red
03-19 10 08:40 S    5    +76 sg   W   L    30  red   y    X:after red
03-19 11 09:05 L   20   -612 red  A   -    20  sg    .    X:after small green
03-19 12 09:40 L    5   -174 red  A   -    15  red   y    X:after red
03-19 13 10:25 S    5   -136 red  A   -    40  red   y    K:newMIL
03-19 14 10:40 S    5    +30 sg   A   -    10  red   y    X:after red
03-19 15 11:05 S   25   +102 sg   W   E    20  sg    .    K:newMIL
03-19 16 11:35 S   15    -98 red  W   M     5  sg    .    X:after small green
03-19 17 12:25 S   10    -54 red  W   L    35  red   y    X:after red
03-19 18 12:50 S   10     -2 red  W   L    15  red   y    X:after red
03-19 19 13:05 S   10   +158 sg   W   L     5  red   y    X:after red
04-02  1 02:05 S   40   +450 CLM  W   M        -     .    K:first
04-02  2 03:05 S   70   +276 CLM  W   L    20  CLM   .    K:claim+run
04-02  3 04:30 S   15    +24 sg   W   L    15  CLM   .    K:claim+run
04-02  4 04:55 S   35   -206 red  W   L    10  sg    .    X:after small green
04-02  5 05:40 S   35   +210 CLM  W   L    10  red   .    X:after red
04-02  6 06:55 L   25   +184 CLM  A   -    40  CLM   .    X:claim,opp side
04-02  7 07:40 L   25    -16 red  W   L    20  CLM   .    K:newMIL
04-02  8 08:20 S   15   -128 red  A   -    15  red   .    X:after red
04-02  9 10:10 S   20   +176 CLM  W   M    95  red   .    K:newMIL
04-02 10 11:10 S   45   +320 CLM  W   M    40  CLM   .    K:claim+run
04-02 11 12:00 S   20   -136 red  W   L     5  CLM   .    K:claim+run
04-02 12 12:50 L   10   -166 red  A   -    30  red   y    X:after red
04-16  1 02:00 L  145   -102 red  W   L        -     .    K:first
04-16  2 04:40 S   15    -50 red  W   M    15  red   .    K:newMIL
04-16  3 05:15 S    5   -102 red  W   L    20  red   y    X:after red
04-16  4 05:30 L   55   +172 CLM  W   M    10  red   .    K:newMIL
04-16  5 06:30 L   35   -150 red  W   L     5  CLM   .    K:claim+run
04-16  6 07:45 L   10   -180 red  W   L    40  red   y    X:after red
04-16  7 08:05 S   40    +16 sg   W   L    10  red   .    K:newMIL
04-16  8 09:00 L   30    +12 sg   W   L    15  sg    .    K:newMIL
04-16  9 10:05 L   20   -158 red  W   L    35  sg    .    X:after small green
04-16 10 10:30 S   20   +268 CLM  W   M     5  red   .    K:newMIL
04-16 11 11:00 L   25   -134 red  A   -    10  CLM   .    X:claim,opp side
04-16 12 11:50 L   25    -76 red  W   L    25  red   .    K:newMIL
04-30  1 02:20 S   15   +716 CLM  W   E        -     .    K:first
04-30  2 02:50 S   10   -188 red  W   M    15  CLM   y    K:claim+run
04-30  3 04:05 S   20   +432 CLM  W   M    65  red   .    X:after red
04-30  4 04:30 S   35    +44 sg   W   L     5  CLM   .    K:claim+run
04-30  5 06:00 S   30   -242 red  W   L    55  sg    .    X:after small green
04-30  6 06:40 L   10   -182 red  W   E    10  red   y    K:newMIL
04-30  7 07:10 L   40    +38 sg   W   M    20  red   .    X:after red
04-30  8 08:05 L   55    +24 sg   W   M    15  sg    .    X:after small green
04-30  9 09:30 L   85   -454 red  W   M    30  sg    .    X:after small green
04-30 10 11:15 L   25   +262 CLM  W   M    20  red   .    X:after red
04-30 11 12:15 L   20    +94 sg   W   L    35  CLM   .    K:claim+run
05-14  1 02:00 S   25   -182 red  W   M        -     .    K:first
05-14  2 02:50 S   20   -214 red  W   M    25  red   .    X:after red
05-14  3 03:30 S   45   +178 CLM  W   L    20  red   .    X:after red
05-14  4 04:25 L   25    +90 sg   A   -    10  CLM   .    X:claim,opp side
05-14  5 05:15 S   15   -194 red  A   -    25  sg    .    K:newMIL
05-14  6 05:45 L   40    +90 sg   W   L    15  red   .    X:after red
05-14  7 06:30 L   35   -240 red  W   L     5  sg    .    X:after small green
05-14  8 07:10 S   10   -144 red  A   -     5  red   y    X:after red
05-14  9 07:45 L    5   -156 red  W   L    25  red   y    X:after red
05-14 10 08:05 S    5   -262 red  W   M    15  red   y    K:newMIL
05-14 11 08:15 L   30   -494 red  A   -     5  red   .    X:after red
05-14 12 09:30 S   10   +256 CLM  W   M    45  red   y    X:after red
05-14 13 10:00 L   15    +82 sg   W   M    20  CLM   .    K:newMIL
05-14 14 10:35 S   10   +106 sg   A   -    20  sg    y    X:after small green
05-14 15 11:10 L   15   -458 red  A   -    25  sg    .    K:newMIL
05-14 16 12:10 L   10    +14 sg   W   L    45  red   y    K:newMIL
05-14 17 12:55 S   20    +38 sg   W   L    35  sg    .    K:newMIL
05-28  1 02:15 S   35   +182 CLM  A   -        -     .    K:first
05-28  2 03:05 S   50  +1268 CLM  W   M    15  CLM   .    K:newMIL
05-28  3 04:00 S   25   +150 sg   W   L     5  CLM   .    K:claim+run
05-28  4 04:30 S   10   -262 red  W   L     5  sg    y    X:after small green
05-28  5 05:05 S   15   -352 red  W   L    25  red   .    X:after red
05-28  6 05:30 L   60   +426 CLM  W   M    10  red   .    K:newMIL
05-28  7 07:10 L   40     +8 sg   W   L    40  CLM   .    K:claim+run
05-28  8 07:55 L   35    +98 sg   W   L     5  sg    .    X:after small green
05-28  9 09:00 L   35   -210 red  W   L    30  sg    .    X:after small green
05-28 10 10:20 S   35   +238 CLM  W   M    45  red   .    K:newMIL
05-28 11 11:00 S   15   -170 red  W   L     5  CLM   .    K:claim+run
05-28 12 11:30 S   10   -360 red  W   L    15  red   y    X:after red
05-28 13 12:00 L   25   +104 sg   W   E    20  red   .    K:newMIL
05-28 14 12:30 L   40   +488 CLM  W   M     5  sg    .    X:after small green
```

### S2 (against-MIL veto + R4 spacing, REJECTED, 9 days)

Columns: # = trade number that day | in = entry time Z | S = side | hold = minutes | $ = P&L | exit = CLM claimed (green and >= 2 x ATR at exit bar) / sg small green / red | MIL = W with, A against the 7xATR major-leg tracker at entry | timing = share of the MIL's eventual extent already travelled at entry (E <1/3, M 1/3-2/3, L >= 2/3; HINDSIGHT label, with-MIL only) | gap = minutes since previous exit | prev = class of previous exit | <=10 = held 10 min or less | S4(c) = K kept / X removed by the claimed-profit gate, with reason

```
day    # in    S hold      $ exit MIL tim gap  prev  <=10 S4(c)
02-05  1 02:10 S   10   +300 sg   W   M        -     y    K:first
02-05  2 02:35 L   15   -482 red  W   L    15  sg    .    K:newMIL
02-05  3 03:40 S   20    +72 sg   W   M    50  red   .    K:newMIL
02-05  4 04:45 L   35   -366 red  W   M    45  sg    .    K:newMIL
02-05  5 07:25 L   60   +260 CLM  W   L   125  red   .    X:after red
02-05  6 09:25 L   10   +116 sg   W   L    60  CLM   y    X:claim,px back
02-05  7 09:50 S   20   -150 red  W   E    15  sg    .    K:newMIL
02-05  8 11:35 S   30   -306 red  W   E    85  red   .    X:after red
02-05  9 12:20 S    5   +462 CLM  W   M    15  red   y    X:after red
02-05 10 12:35 S   25   +126 sg   W   L    10  CLM   .    K:claim+run
02-19  1 02:25 S    5    -60 red  W   M        -     y    K:first
02-19  2 02:40 L   65    -40 red  W   M    10  red   .    K:newMIL
02-19  3 04:50 S   25     +0 red  W   L    65  red   .    K:newMIL
02-19  4 05:35 L   35    +42 sg   W   M    20  red   .    K:newMIL
02-19  5 08:10 L   35   -318 red  W   L   120  sg    .    X:after small green
02-19  6 08:50 S   20   +172 sg   W   E     5  red   .    K:newMIL
02-19  7 11:30 L   10    -90 red  W   L   140  sg    y    K:newMIL
03-05  1 02:00 S   50   -286 red  W   L        -     .    K:first
03-05  2 03:15 S   25   +228 sg   W   L    25  red   .    X:after red
03-05  3 03:50 S    5   -244 red  W   L    10  sg    y    X:after small green
03-05  4 04:30 L   55     +8 sg   W   L    35  red   .    K:newMIL
03-05  5 05:55 S   25   +248 CLM  W   M    30  sg    .    K:newMIL
03-05  6 07:10 L   45   -202 red  W   M    50  CLM   .    K:newMIL
03-05  7 09:15 L   15   -252 red  W   L    80  red   .    X:after red
03-05  8 10:20 S   10   -200 red  W   M    50  red   y    K:newMIL
03-05  9 12:10 S   10   -320 red  W   M   100  red   y    X:after red
03-05 10 12:50 S    5    +46 sg   W   L    30  red   y    X:after red
03-05 11 13:00 S   15    +66 sg   W   L     5  sg    .    X:after small green
03-19  1 02:10 L   40   +142 CLM  W   L        -     .    K:first
03-19  2 03:10 L   20   -222 red  W   L    20  CLM   .    K:claim+run
03-19  3 03:35 S   50   +260 CLM  W   E     5  red   .    K:newMIL
03-19  4 05:40 S   15    -50 red  W   L    75  CLM   .    K:claim+run
03-19  5 06:25 L    5   -230 red  W   L    30  red   y    K:newMIL
03-19  6 07:55 S   10     +2 sg   W   M    85  red   y    K:newMIL
03-19  7 09:45 S    5   -622 red  W   L   100  sg    y    X:after small green
03-19  8 09:55 L   10   -322 red  W   L     5  red   y    K:newMIL
03-19  9 10:55 S   20    +20 sg   W   E    50  red   .    K:newMIL
03-19 10 13:00 S    5    +66 sg   W   L   105  sg    y    X:after small green
03-19 11 13:10 S   10   -560 red  W   L     5  sg    y    X:after small green
04-02  1 02:10 S   45   +274 CLM  W   M        -     .    K:first
04-02  2 03:55 S   50    +62 sg   W   L    60  CLM   .    K:claim+run
04-02  3 04:55 S   80   +234 CLM  W   L    10  sg    .    X:after small green
04-02  4 07:00 L   25   -104 red  W   M    45  CLM   .    K:newMIL
04-02  5 09:25 L   10   -254 red  W   L   120  red   y    X:after red
04-02  6 09:45 S   45   +306 CLM  W   E    10  red   .    K:newMIL
04-02  7 11:10 S   45   +320 CLM  W   M    40  CLM   .    K:claim+run
04-02  8 12:00 S   25   -308 red  W   L     5  CLM   .    K:claim+run
04-02  9 12:55 L    5   -138 red  W   L    30  red   y    K:newMIL
04-16  1 02:05 L  145   -160 red  W   L        -     .    K:first
04-16  2 04:35 S   10    -28 red  W   M     5  red   y    K:newMIL
04-16  3 05:30 L   50   +114 CLM  W   M    45  red   .    K:newMIL
04-16  4 08:05 S   40    +16 sg   W   L   105  CLM   .    K:newMIL
04-16  5 09:00 L   55    +10 sg   W   L    15  sg    .    K:newMIL
04-16  6 10:35 S   20    -16 red  W   M    40  sg    .    K:newMIL
04-16  7 11:05 L   20   -198 red  W   L    10  red   .    K:newMIL
04-30  1 02:10 S    5     -4 red  W   E        -     y    K:first
04-30  2 04:05 S   40   +702 CLM  W   M   110  red   .    X:after red
04-30  3 04:55 S   15   -326 red  W   L    10  CLM   .    K:claim+run
04-30  4 06:00 S   25   -144 red  W   L    50  red   .    X:after red
04-30  5 06:35 L   50   +330 CLM  W   E    10  red   .    K:newMIL
04-30  6 09:30 L  130   +274 CLM  W   M   125  CLM   .    K:claim+run
04-30  7 11:50 L   45   +410 CLM  W   L    10  CLM   .    X:claim,px back
05-14  1 02:00 S   40   -168 red  W   M        -     .    K:first
05-14  2 03:55 S   25   -234 red  W   L    75  red   .    X:after red
05-14  3 04:30 L   25     +8 sg   W   M    10  red   .    K:newMIL
05-14  4 07:35 L   15    -54 red  W   L   160  sg    .    X:after small green
05-14  5 08:05 S    5   -262 red  W   M    15  red   y    K:newMIL
05-14  6 09:40 S   10   -260 red  W   L    90  red   y    X:after red
05-14  7 10:00 L   15    +82 sg   W   M    10  red   .    K:newMIL
05-14  8 10:40 S   10   -112 red  W   L    25  sg    y    K:newMIL
05-14  9 11:50 L    5   -124 red  W   L    60  red   y    K:newMIL
05-14 10 12:55 S   20    +38 sg   W   L    60  red   .    K:newMIL
05-28  1 02:00 L   15   -366 red  W   L        -     .    K:first
05-28  2 02:25 S   25   +176 CLM  W   E    10  red   .    K:newMIL
05-28  3 03:55 S   30   +254 CLM  W   L    65  CLM   .    K:claim+run
05-28  4 04:45 S   35   -216 red  W   L    20  CLM   .    X:claim,px back
05-28  5 05:35 L   55   +298 CLM  W   M    15  red   .    K:newMIL
05-28  6 07:20 L   55    +42 sg   W   L    50  CLM   .    K:claim+run
05-28  7 08:25 L   55    +14 sg   W   L    10  sg    .    X:after small green
05-28  8 10:10 S    5    +26 sg   W   M    50  sg    y    K:newMIL
05-28  9 12:00 L   25   +104 sg   W   E   105  sg    .    K:newMIL
```

### S3 (claim at >= 2 x ATR, INTERIM, 6 days)

Columns: # = trade number that day | in = entry time Z | S = side | hold = minutes | $ = P&L | exit = CLM claimed (green and >= 2 x ATR at exit bar) / sg small green / red | MIL = W with, A against the 7xATR major-leg tracker at entry | timing = share of the MIL's eventual extent already travelled at entry (E <1/3, M 1/3-2/3, L >= 2/3; HINDSIGHT label, with-MIL only) | gap = minutes since previous exit | prev = class of previous exit | <=10 = held 10 min or less | S4(c) = K kept / X removed by the claimed-profit gate, with reason

```
day    # in    S hold      $ exit MIL tim gap  prev  <=10 S4(c)
02-05  1 02:05 S   10   +886 CLM  A   -        -     y    K:first
02-05  2 02:25 L   10   +326 CLM  A   -    10  CLM   y    K:newMIL
02-05  3 02:50 S   10   +364 sg   A   -    15  CLM   y    K:newMIL
02-05  4 03:25 L   10   -372 red  W   M    25  sg    y    X:after small green
02-05  5 03:50 S   10    -98 red  W   L    15  red   y    K:newMIL
02-05  6 04:25 S   10   -348 red  W   L    25  red   y    X:after red
02-05  7 04:40 L    5   +214 CLM  A   -     5  red   y    X:after red
02-05  8 04:50 L   30   -428 red  W   M     5  CLM   .    K:newMIL
02-05  9 05:35 L   10    +82 sg   W   M    15  red   y    X:after red
02-05 10 06:40 L   25   +178 CLM  W   L    55  sg    .    X:after small green
02-05 11 07:25 L   45   +136 sg   W   L    20  CLM   .    X:claim,px back
02-05 12 08:15 L   30   -306 red  W   L     5  sg    .    X:after small green
02-05 13 08:50 S   10   +214 sg   A   -     5  red   y    X:after red
02-05 14 09:05 S   15   -304 red  A   -     5  sg    .    X:after small green
02-05 15 09:25 L   10   +116 sg   W   L     5  red   y    X:after red
02-05 16 10:25 L   10   -284 red  A   -    50  sg    y    K:newMIL
02-05 17 11:00 S   20   -208 red  W   E    25  red   .    X:after red
02-05 18 11:30 S   25   -104 red  W   E    10  red   .    X:after red
02-05 19 12:10 L   10   -472 red  A   -    15  red   y    X:after red
02-05 20 12:35 S   15   +608 CLM  W   L    15  red   .    X:after red
02-19  1 02:45 L   45   +116 CLM  W   L        -     .    K:first
02-19  2 04:00 L   25   -112 red  W   L    30  CLM   .    X:claim,px back
02-19  3 04:50 S   20    +92 CLM  W   L    25  red   .    K:newMIL
02-19  4 05:35 L   20    +86 sg   W   M    25  CLM   .    K:newMIL
02-19  5 06:05 L   55   +146 CLM  W   M    10  sg    .    X:after small green
02-19  6 07:10 L   15   +120 CLM  W   L    10  CLM   .    X:claim,px back
02-19  7 07:30 L   75   -296 red  W   L     5  CLM   .    K:claim+run
02-19  8 08:50 S    5   +176 CLM  W   E     5  red   y    K:newMIL
02-19  9 09:05 S   35   +326 CLM  W   M    10  CLM   .    K:claim+run
02-19 10 09:45 S    5   +194 CLM  W   L     5  CLM   y    K:claim+run
02-19 11 10:10 S   35     -8 red  W   L    20  CLM   .    K:claim+run
02-19 12 11:25 L   25   -188 red  A   -    40  red   .    X:after red
02-19 13 12:25 L   40   -302 red  W   L    35  red   .    K:newMIL
03-05  1 02:00 S   45    -98 red  W   L        -     .    K:first
03-05  2 02:50 L   25   -232 red  A   -     5  red   .    X:after red
03-05  3 03:25 S    5   +260 CLM  W   L    10  red   y    X:after red
03-05  4 04:15 L   30    +70 sg   A   -    45  CLM   .    X:claim,opp side
03-05  5 04:50 L   40   -232 red  W   L     5  sg    .    K:newMIL
03-05  6 05:40 S   15   +140 CLM  A   -    10  red   .    X:after red
03-05  7 06:00 S   10   +322 CLM  W   M     5  CLM   y    K:newMIL
03-05  8 06:15 S   10   -210 red  W   L     5  CLM   y    K:claim+run
03-05  9 06:35 S   15   -522 red  W   L    10  red   .    X:after red
03-05 10 06:55 L   30   +166 CLM  A   -     5  red   .    X:after red
03-05 11 07:30 L   25   -302 red  W   M     5  CLM   .    K:newMIL
03-05 12 08:05 S   15   -140 red  A   -    10  red   .    X:after red
03-05 13 08:30 S    5   -166 red  A   -    10  red   y    X:after red
03-05 14 08:40 S    5   -194 red  A   -     5  red   y    X:after red
03-05 15 09:05 L    5   +478 CLM  W   M    20  red   y    X:after red
03-05 16 09:30 S    5   -128 red  A   -    20  CLM   y    X:claim,opp side
03-05 17 09:40 S   30   -238 red  A   -     5  red   .    X:after red
03-05 18 10:15 L    5    -50 red  W   M     5  red   y    X:after red
03-05 19 10:30 L   10   -270 red  A   -    10  red   y    K:newMIL
03-05 20 10:50 S    5   -176 red  W   M    10  red   y    X:after red
03-05 21 11:00 S   10   -224 red  W   M     5  red   y    X:after red
03-05 22 11:30 L    5   -204 red  A   -    20  red   y    X:after red
03-05 23 12:55 S   20     +2 sg   W   L    80  red   .    X:after red
03-19  1 02:10 L   15   +160 CLM  W   L        -     .    K:first
03-19  2 02:35 L   55   -282 red  W   L    10  CLM   .    K:claim+run
03-19  3 03:35 S   25   +142 CLM  W   E     5  red   .    K:newMIL
03-19  4 04:05 S    5    +98 CLM  W   M     5  CLM   y    K:claim+run
03-19  5 04:20 S   20    +98 CLM  W   M    10  CLM   .    X:claim,px back
03-19  6 04:45 S   15   -144 red  W   L     5  CLM   .    K:claim+run
03-19  7 05:30 S   15   +202 CLM  W   L    30  red   .    X:after red
03-19  8 05:50 S    5   -240 red  W   L     5  CLM   y    K:claim+run
03-19  9 06:15 L   15   -160 red  A   -    20  red   .    X:after red
03-19 10 06:55 S   15    +38 sg   A   -    25  red   .    K:newMIL
03-19 11 07:35 S   25   -110 red  A   -    25  sg    .    X:after small green
03-19 12 08:05 S    5   -148 red  W   M     5  red   y    K:newMIL
03-19 13 08:15 L   10   -234 red  A   -     5  red   y    X:after red
03-19 14 08:35 S   15    +42 sg   W   L    10  red   .    X:after red
03-19 15 09:00 L   25   -522 red  A   -    10  sg    .    X:after small green
03-19 16 09:50 L   25   -184 red  A   -    25  red   .    X:after red
03-19 17 10:40 S   20    +18 sg   A   -    25  red   .    K:newMIL
03-19 18 11:05 S   20   +238 CLM  W   E     5  sg    .    K:newMIL
03-19 19 11:35 S   35   -194 red  W   M    10  CLM   .    K:claim+run
03-19 20 12:25 S   10    -54 red  W   L    15  red   y    X:after red
03-19 21 12:50 S   20   +256 CLM  W   L    15  red   .    X:after red
04-02  1 02:05 S   10   +312 CLM  W   M        -     y    K:first
04-02  2 02:25 S   30     -2 red  W   L    10  CLM   .    K:claim+run
04-02  3 03:05 S   35   +236 CLM  W   L    10  red   .    X:after red
04-02  4 03:50 S   50   +188 CLM  W   L    10  CLM   .    K:claim+run
04-02  5 04:55 S   55   +296 CLM  W   L    15  CLM   .    K:claim+run
04-02  6 05:55 S   30   -190 red  W   L     5  CLM   .    X:claim,px back
04-02  7 06:55 L   15   +160 sg   A   -    30  red   .    X:after red
04-02  8 07:15 L   10   -254 red  W   M     5  sg    y    K:newMIL
04-02  9 07:40 L   20   +218 CLM  W   L    15  red   .    X:after red
04-02 10 08:20 S   15   -128 red  A   -    20  CLM   .    X:claim,opp side
04-02 11 09:00 S   35   +134 sg   A   -    25  red   .    X:after red
04-02 12 10:00 S   15   +234 CLM  W   E    25  sg    .    K:newMIL
04-02 13 10:25 S   10   -136 red  W   M    10  CLM   y    X:claim,px back
04-02 14 11:10 S   15   +194 CLM  W   M    35  red   .    X:after red
04-02 15 11:30 S   15   +164 CLM  W   L     5  CLM   .    K:claim+run
04-02 16 12:00 S   25   -308 red  W   L    15  CLM   .    K:claim+run
04-02 17 12:45 L   25   -108 red  A   -    20  red   .    X:after red
04-16  1 02:00 L   45    +70 CLM  W   L        -     .    K:first
04-16  2 03:05 L   75   -138 red  W   L    20  CLM   .    K:claim+run
04-16  3 05:10 S   10   -112 red  W   L    50  red   y    K:newMIL
04-16  4 05:40 L   30   +202 CLM  W   M    20  red   .    K:newMIL
04-16  5 06:15 L  110   -356 red  W   L     5  CLM   .    X:claim,px back
04-16  6 08:15 S   20   +140 CLM  W   L    10  red   .    K:newMIL
04-16  7 09:00 L   55    +10 sg   W   L    25  CLM   .    K:newMIL
04-16  8 10:05 L   25   -394 red  W   L    10  sg    .    X:after small green
04-16  9 10:35 S   10   +176 CLM  W   M     5  red   y    K:newMIL
04-16 10 10:50 S    5   -184 red  W   L     5  CLM   y    X:claim,px back
04-16 11 11:05 L   20   -198 red  W   L    10  red   .    K:newMIL
04-16 12 11:55 L   60    -96 red  W   L    30  red   .    X:after red
```