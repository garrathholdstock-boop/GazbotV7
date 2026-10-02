# ARM 6 — WHERE ON THE SNAKE DOES HE ENTER, AND WHERE DOES HE EXIT?

**Greenfield entry study, 2026-10-02.** Read-only throughout: no order placed, no POST to
`/api/control`, no service restarted, nothing written to `gazbot7.db` / `capture.db` / `depth.db`.
(`research_data.connect()` would have created its two views had they been absent; they already
existed and the DB mtime is unchanged at 03:30Z, so this arm wrote nothing to it. All subsequent
reads used an explicit `mode=ro` handle.)

His instruction: *"if you want my successful entries and exits, pick my best performing 5 days in
the last 3 weeks and analyse those trades. in the context of that days tape. look at where they are
on the snake for the day."* Narrowed mid-flight to *"use the 3 days there with the least trades and
longest hold times."*

---

## 0. THE ANSWER, UP FRONT

**He enters mid-leg, with the leg, well away from the turns — and that placement is the single
strongest discriminator anyone has measured on this book. It is also, as far as I can make it,
NOT CAUSALLY COMPUTABLE.**

| | n | per entry | win | med hold |
|---|---|---|---|---|
| **WITH** the day's pivot leg | 115 | **+$87** | **65%** | 20m |
| **AGAINST** the pivot leg | 45 | **−$244** | **27%** | 13m |
| 16–45 min from the nearest turn | 53 | **+$82** | **70%** | 22m |
| within 15 min of a turn | 39 | **−$138** | **38%** | 12m |

Day-clustered 95% CIs on the per-entry differences (resampling the 9 sessions, not the entries):
WITH − AGAINST = **+$334 [+$226, +$507]**; (16–45min) − (within 15min) = **+$220 [+$82, +$493]**.
Both exclude zero. On the four losing days, **AGAINST the leg won 1 trade out of 17 (6%)** at
−$438/entry.

**And then it does not cash.** Every causal restatement I could build loses the separation:

- the desk's own live 15×ATR turn state (`turn_watch`) is *backwards* on this book — WITH it
  −$13/entry (n=83) vs AGAINST it +$2 (n=77);
- a left-confirmed local extreme ("a trailing-90min extreme printed ≤15 min ago") reproduces the
  hindsight veto at **33% precision** — it fires on 109 of 159 entries because on a trending tape a
  new trailing high prints constantly — and its day-clustered CI spans zero (**+$58 [−$70, +$200]**);
- the best causal entry rule I could derive from the shape races **+3.5pp** at ±50pt on 273 sessions
  against a side-matched control, but it fires **9.4/session** (the standard rejects >6), and sliding
  its one free parameter across 9 bands gives a **mean of +0.89pp (spread −2.3 … +2.4)**. The +3.5
  was a favourable draw — the exact failure mode Arm 1 warned about.

**So Arm 6's deliverable is a mechanism and a ranked shortlist, not a rule.** The mechanism is
specific and matches Arm 1 independently: *the gap between "a new extreme inside a run that is
continuing" and "a new extreme that was the turn" is only resolvable afterwards.* That is the
operator's own correction in measurement form — *"the turns are not violent. they often just change
direction."*

⚠ **n IS SMALL AND THE DAYS WERE CHOSEN BY P&L.** 30 entries on the primary three days, 160 across
all nine. Thresholds were read off these same entries. Everything below is an **upper bound** and a
hypothesis for the 616-session lab, not a validated result.

---

## 1. SCOPE AND DATA

```
from gazbot7.research_data import clean_entries     # views pre-existing; mode=ro handle
clean_entries(conn, "entry_source='manual' AND opened_at >= '2026-09-16'")
```
One row per **ENTRY**, never per scale-out leg, with `fill_clean=1` so the paper engine's fabricated
0.1%-adverse multi-lot fills are excluded. Every entry is 4 lots. MNQ = $2.00/point/lot, fee
$1.50/RT.

| day | group | entries | P&L | med hold | long share |
|---|---|---|---|---|---|
| 2026-09-21 | **PRIMARY** | 7 | +$1,464 | 98m | 6/7 |
| 2026-09-17 | **PRIMARY** | 8 | +$1,478 | 55m | 7/8 |
| 2026-09-18 | **PRIMARY** | 15 | +$1,546 | 50m | 7/15 |
| 2026-09-29 | over-traded | 20 | +$1,465 | 16m | 13/20 |
| 2026-09-25 | over-traded | 36 | +$56 | 5m | 15/36 |
| 2026-09-24 | BAD | 33 | −$614 | 14m | 17/33 |
| 2026-09-28 | BAD | 23 | −$1,882 | 17m | 10/23 |
| 2026-09-30 | BAD | 15 | −$2,129 | 13m | 4/15 |
| 2026-10-01 | BAD | 3 | −$2,313 | 41m | 2/3 |

⚠ **TWO DAY CONVENTIONS, AND THEY DISAGREE.** The brief's figures are by UTC **calendar date**; the
tape is segmented on the **22:00Z-anchored session** the dashboard shows, so a trade opened after
22:00Z belongs to the next session. That moves three trades and changes two headline numbers:
**09-25 is +$56 over 36 entries, not +$975 over 35**, because the session absorbs a SHORT opened
2026-09-24 23:57Z that lost **−$920**; and **09-21 is +$1,464 over 7, not +$1,190 over 8**, because
one 09-21 22:xx entry belongs to the 09-22 session. 160 of the 161 calendar-date entries are located
here (the one dropped belongs to a session outside the nine). The session attribution is the correct
one for a question about the day's structure, and it is worth noting that it makes the 5-minute-hold
day **break-even, not profitable**.

⚠ **LONG/SHORT IS A CONFOUND IN THE RAW P&L, AND IT IS LARGE.** PRIMARY is **67% long** on sessions
that rose +750 / +448 / +243 pt; longs made **+$4,782** and shorts **−$294**. On the BAD days he was
45% long and longs lost **−$6,506**. So *"his good days are good"* is partly *"he was long on a tape
that went up."* This is why every race below uses a **side-matched** control, and why the placement
finding matters more than the P&L: the WITH/AGAINST split holds **inside the losing days too**, where
the tape fell.

---

## 2. (a) THE SNAKE — THREE DEFINITIONS, AND leg_watch's IS NOT IT

### The frozen leg definition does not draw the snake

`scripts/leg_watch.py`: a leg opens on an 8-minute close move ≥ 1×ATR14 and dies when the close gives
back 3×ATR from its extreme, with ATR rolled per minute. Replayed exactly (including leg_watch's
back-dating of `t0` to minute *i−8*):

**27 to 46 legs per session, mean 37.4.** Not five straight lines, not three.

⚠ **AND MY BRIEF CONFLATED TWO OF THE DESK'S OWN SCALES.** "3.1 legs/session, median 298pt over
266min" is **turn_watch's** number (a ~20×ATR decomposition), not leg_watch's; leg_watch's own
docstring says **17/session, median 43min/64pt**, and the operator's `LEG_MIN_ATR=6.0` size gate is
what cuts its *paging* to ~4/session. The frozen rule is also **not a partition of the day** —
consecutive legs overlap by up to 8 minutes from the back-dating, and two same-direction legs can sit
adjacent (09-21 L16 DWN → L17 DWN). It is a *leg-running detector*, not a chart decomposition.

### Definition 2 — the 15×ATR turn segmentation (the desk's own turn scale)

`turn_watch.replay`: one direction at a time, running extreme, direction **flips** when the close
gives back 15×ATR. Vertices sit at the extremes, so it partitions the session end to end.

**2 to 6 segments per session, median 4, mean 4.4.** This is the count closest to "five straight
lines", and it scales with ATR.

### Definition 3 — the ±90min / 60pt structural pivot (Arm 2's)

A local extreme over ±90 minutes with both legs ≥ 60pt. **2 to 11 segments, mean 7.1.**

⚠ Its 60pt floor is **absolute, not ATR-scaled**, and that is visible in the output: the three quiet
PRIMARY days give 2 / 6 / 5 segments while the loud BAD days give 11 / 7 / 9 / 8. It inflates exactly
where ATR rises.

**Which looks like his snake?** The 15×ATR segmentation gives the right *count*; the pivot
segmentation gives the right *shape* (vertices at real highs and lows, which is what he draws) and it
is the one that discriminates his trades. **I report both and use the pivot snake as the primary
frame, with the 15×ATR segment number carried in every row.** On the quiet primary days the two
agree closely; on the loud days the pivot snake is finer.

### The snake, day by day (±90min/60pt pivot segments)

**2026-09-21 — PRIMARY — 2 segments. One straight line with a kink; no turn all session.**
```
P1 UP  00:00->13:24  804m  +170.0pt   30032.25 -> 30202.25
P2 UP  13:24->20:59  455m  +579.5pt   30202.25 -> 30781.75
```
15×ATR view: **2 segments** — UP 00:00→19:38, 1178 min, **+829pt**, then a 64-min −101pt tail.
A +846pt range on a **median ATR of 7.1**. His single best-hold day was the most one-way day of the
nine, and the 15×ATR rule found **no turn in it at all**.

**2026-09-17 — PRIMARY — 6 segments** (15×ATR: 4). ATR 8.1, range 546pt.
```
P1 UP  22:00->00:43  163m  +208.0 | P2 DWN 00:43->06:00  317m  -110.8
P3 UP  06:00->12:34  394m  +384.5 | P4 DWN 12:34->13:38   64m  -147.5
P5 UP  13:38->14:42   64m  +142.5 | P6 DWN 14:42->20:59  377m   -28.5
```

**2026-09-18 — PRIMARY — 5 segments** (15×ATR: 4). ATR 7.1, range 346pt.
```
P1 UP  22:00->07:30  570m  +250.0 | P2 DWN 07:30->09:45  135m  -131.5
P3 UP  09:45->10:38   53m   +67.8 | P4 DWN 10:38->16:25  347m  -244.2
P5 UP  16:25->20:59  274m  +301.0
```

**2026-09-29 — over-traded — 9 segments** (15×ATR: 5). ATR 10.7. Legs 60–239 min, 10–263 pt.
**2026-09-25 — over-traded — 7 segments** (15×ATR: 3). ATR 8.9. One 607-min +100pt crawl, then
a −314pt and a +268pt swing inside three hours.

**2026-09-24 — BAD — 11 segments** (15×ATR: 4). ATR 11.4, **net +(−66)pt on a 457pt range**.
**2026-09-28 — BAD — 7 segments** (15×ATR: 6). ATR 12.6. Includes a −402pt leg in 76 min and a
+365pt leg in 99 min, back to back.
**2026-09-30 — BAD — 9 segments** (15×ATR: 6). ATR 10.4, net +58pt on a 394pt range.
**2026-10-01 — BAD — 8 segments** (15×ATR: 6). ATR 12.5, net +76pt on a **604pt** range.

**The day-level contrast, before a single trade is placed on it:**

| | pivot segs | 15×ATR segs | median ATR14 | range | \|net\| | efficiency |
|---|---|---|---|---|---|---|
| PRIMARY (3) | 2 / 6 / 5 | 2 / 4 / 4 | **7.1 / 8.1 / 7.1** | 846 / 546 / 346 | 750 / 448 / 243 | **.156 / .076 / .046** |
| over-traded (2) | 9 / 7 | 5 / 3 | 10.7 / 8.9 | 354 / 318 | 96 / 186 | .012 / .027 |
| BAD (4) | 11 / 7 / 9 / 8 | 4 / 6 / 6 / 6 | **11.4 / 12.6 / 10.4 / 12.5** | 457–604 | **58–287** | **.007–.035** |

His good days were **quiet, few-turn, one-way**. His bad days were **fast, many-turn, and went
nowhere**. Median ATR14 at his entry: **PRIMARY 8.0, over-traded 12.5, BAD 15.2**. Fourteen of 30
primary entries were taken at ATR < 8; **one of 74** bad-day entries was.

---

## 3. (b) EVERY ENTRY AND EXIT, LOCATED

Columns: `turn-seg` = which of the day's 15×ATR segments · `pivot-seg` = which ±90min/60pt segment ·
`w/a` = his side WITH or AGAINST that segment · `frac` = fraction of the segment's *eventual*
duration elapsed at entry · `min from pivot` = signed minutes to the nearest vertex (**negative =
before the turn, positive = after**) · `rng%` = close in the session-to-date range (causal) ·
`CVD` = the dashboard's own gauge, CVD's position in its rolling 180-min range (causal) ·
`ATR` = ATR14 at that minute (causal).

⚠ **`frac` AND `min from pivot` ARE HINDSIGHT AND CAN NEVER BE A LIVE INPUT.** Both need the leg's
end, which needs future tape. They are here to say *where a causal rule would have to aim*, nothing
more. `rng%`, `CVD` and `ATR` are causal.

### PRIMARY — 2026-09-21, 7 entries, +$1,464, snake 2 segments, ATR 7.1

| in | out | side | hold | P&L | turn-seg | pivot-seg | w/a | frac | min from pivot | rng% | CVD | ATR | exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 06:45 | 08:31 | LONG | 106m | +588 | 1/2 | 1/2 | WITH | 0.50 | 399 | 96 | 62 | 4.5 | 1/2 WITH 0.64 |
| 09:28 | 11:09 | LONG | 101m | −289 | 1/2 | 1/2 | WITH | 0.71 | 236 | 97 | 98 | 7.0 | 1/2 WITH 0.83 |
| 11:41 | 12:06 | SHORT | 25m | −351 | 1/2 | 1/2 | **AGST** | 0.87 | 103 | 83 | 87 | 6.8 | 1/2 AGST 0.90 |
| 12:06 | 13:44 | LONG | 98m | +449 | 1/2 | 1/2 | WITH | 0.90 | 78 | 98 | 76 | 9.3 | 2/2 WITH 0.04 |
| 13:44 | 13:53 | LONG | 8m | +456 | 1/2 | 2/2 | WITH | 0.04 | −20 | 100 | 100 | 20.2 | 2/2 WITH 0.06 |
| 13:54 | 14:14 | LONG | 21m | +294 | 1/2 | 2/2 | WITH | 0.07 | −30 | 100 | 100 | 15.2 | 2/2 WITH 0.11 |
| 16:36 | 18:16 | LONG | 100m | +316 | 1/2 | 2/2 | WITH | 0.42 | −192 | 98 | 99 | 8.0 | 2/2 WITH 0.64 |

Six longs with the day's one line; **every one of the seven was taken at rng ≥ 83, five of them at
≥ 96.** The only loser of size is the single SHORT against it.

### PRIMARY — 2026-09-17, 8 entries, +$1,478, snake 6 segments, ATR 8.1

| in | out | side | hold | P&L | turn-seg | pivot-seg | w/a | frac | min from pivot | rng% | CVD | ATR | exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 00:25 | 07:00 | LONG | 395m | +272 | 1/4 | 1/6 | WITH | 0.89 | 18 | 86 | 50 | 13.5 | 3/6 WITH 0.15 |
| 07:07 | 08:43 | LONG | 97m | +193 | 3/4 | 3/6 | WITH | 0.17 | −67 | 99 | 100 | 10.9 | 3/6 WITH 0.41 |
| 11:55 | 12:16 | LONG | 21m | +608 | 3/4 | 3/6 | WITH | 0.90 | 39 | 91 | 38 | 7.8 | 3/6 WITH 0.95 |
| 12:19 | 12:40 | LONG | 21m | +504 | 3/4 | 3/6 | WITH | 0.96 | 15 | 100 | 90 | 11.2 | 4/6 AGST 0.09 |
| 13:26 | 14:55 | LONG | 88m | **−441** | 3/4 | 4/6 | **AGST** | 0.81 | 12 | 95 | 47 | 8.0 | 6/6 AGST 0.03 |
| 15:27 | 17:02 | LONG | 95m | +382 | 3/4 | 6/6 | AGST | 0.12 | −45 | 90 | 63 | 12.0 | 6/6 AGST 0.37 |
| 19:35 | 19:38 | SHORT | 2m | −35 | 3/4 | 6/6 | WITH | 0.78 | −293 | 98 | 82 | 6.2 | 6/6 WITH 0.79 |
| 19:38 | 19:50 | LONG | 12m | −7 | 3/4 | 6/6 | AGST | 0.79 | −296 | 98 | 80 | 6.4 | 6/6 AGST 0.82 |

All eight at rng ≥ 86. The day's one real loss (−$441) is the one entry taken **against the leg that
was running**, 12 minutes after the 12:34 top.

### PRIMARY — 2026-09-18, 15 entries, +$1,546, snake 5 segments, ATR 7.1

| in | out | side | hold | P&L | turn-seg | pivot-seg | w/a | frac | min from pivot | rng% | CVD | ATR | exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 02:37 | 03:27 | LONG | 50m | +338 | 2/4 | 1/5 | WITH | 0.49 | 293 | 48 | 75 | 4.4 | 1/5 WITH 0.57 |
| 04:50 | 05:46 | LONG | 56m | +414 | 2/4 | 1/5 | WITH | 0.72 | 160 | 96 | 100 | 6.7 | 1/5 WITH 0.82 |
| 06:06 | 07:05 | LONG | 59m | +410 | 2/4 | 1/5 | WITH | 0.85 | 84 | 98 | 79 | 7.4 | 1/5 WITH 0.96 |
| 07:10 | 07:43 | LONG | 33m | +62 | 2/4 | 1/5 | WITH | 0.96 | 20 | 99 | 100 | 8.1 | 2/5 AGST 0.10 |
| 08:11 | 09:08 | SHORT | 57m | +176 | 3/4 | 2/5 | WITH | 0.30 | −41 | 82 | 58 | 11.1 | 2/5 WITH 0.73 |
| 09:31 | 10:13 | SHORT | 41m | +75 | 3/4 | 2/5 | WITH | 0.90 | 14 | 68 | 37 | 6.9 | 3/5 AGST 0.53 |
| 10:15 | 10:59 | LONG | 44m | +65 | 3/4 | 3/5 | WITH | 0.57 | 23 | 67 | 100 | 6.9 | 4/5 AGST 0.06 |
| 11:01 | 11:02 | SHORT | 1m | +2 | 3/4 | 4/5 | WITH | 0.07 | −23 | 72 | 76 | 7.3 | 4/5 WITH 0.07 |
| 11:21 | 11:37 | SHORT | 16m | −198 | 3/4 | 4/5 | WITH | 0.12 | −43 | 58 | 12 | 10.8 | 4/5 WITH 0.17 |
| 12:16 | 13:22 | SHORT | 67m | −30 | 3/4 | 4/5 | WITH | 0.28 | −98 | 43 | 34 | 12.0 | 4/5 WITH 0.47 |
| 13:55 | 14:15 | SHORT | 20m | +434 | 3/4 | 4/5 | WITH | 0.57 | 150 | 43 | 2 | 18.2 | 4/5 WITH 0.63 |
| 14:23 | 15:13 | LONG | 50m | −118 | 3/4 | 4/5 | **AGST** | 0.65 | 122 | 31 | 14 | 16.3 | 4/5 AGST 0.79 |
| 16:02 | 16:08 | SHORT | 6m | −160 | 3/4 | 4/5 | WITH | 0.93 | 23 | 19 | 1 | 9.0 | 4/5 WITH 0.95 |
| 16:11 | 17:07 | SHORT | 56m | −208 | 3/4 | 4/5 | WITH | 0.96 | 14 | 20 | 7 | 7.5 | 5/5 AGST 0.15 |
| 17:07 | 18:33 | LONG | 86m | +284 | 4/4 | 5/5 | WITH | 0.15 | −42 | 29 | 65 | 6.8 | 5/5 WITH 0.47 |

This is the day that proves it is **not** "buy high". He went long into the up-leg at rng 48→99, then
**switched sides at the 07:30 top** and shorted the down-leg at rng 82→19. The variable is not
"high in the range", it is **high in the range IN THE DIRECTION OF THE TRADE** (median
`extreme_pos`: PRIMARY **90.4**, BAD 69.9). The two weakest shorts (−$160, −$208) are the two taken
at `frac` 0.93 and 0.96 — within ~15 min of the 16:25 bottom, i.e. **at the end of the leg he was
riding**.

### BAD — the negative examples

**2026-10-01, 3 entries, −$2,313** — the archetype in one row:

| in | out | side | hold | P&L | pivot-seg | w/a | frac | min from pivot | rng% | ATR | exit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 05:05 | 05:47 | LONG | 41m | +281 | 3/8 | WITH | 0.82 | 60 | 99 | 10.1 | 3/8 WITH 0.95 |
| 06:01 | 13:20 | LONG | **439m** | **−2,398** | 3/8 | WITH | **0.99** | **−4** | 99 | 11.6 | **6/8 AGST 0.57** |
| 14:12 | 14:12 | SHORT | 0m | −196 | 6/8 | WITH | 0.77 | 59 | 11 | 39.7 | 6/8 WITH 0.77 |

The −$2,398 was **WITH the leg, at the session high, 4 minutes before the leg's top**, and held for
7¼ hours across three subsequent turns. "WITH the leg" is worthless at `frac` 0.99.

**2026-09-30, 15 entries, −$2,129.** Four AGAINST-the-leg entries cost **−$1,793** of it; the worst
single trade (−$1,195) was a SHORT taken 37 min *before* the 15:50 top of a +394pt up-leg. The two
longs at 13:31/13:43 were taken at ATR **24.2 and 41.6** and lost −$509 and −$221 in 4 and 1 minutes.

**2026-09-28, 23 entries, −$1,882.** Seven entries within 6 minutes of a vertex; the three biggest
losses (−$806, −$768, −$728) are all `|min from pivot| ≤ 21` and two of the three are AGAINST the leg.
ATR at those three entries: 25.3, 31.7, 30.2.

**2026-09-24, 33 entries, −$614.** The flattest day of the nine (net −66pt on a 457pt range, 11 pivot
segments) and his most-traded. Nine AGAINST-leg entries cost −$2,432; the worst (−$789) was at
**ATR 34.4**.

Full tables for the four bad days and the two over-traded days are reproduced from the same
generator; the rows above are the ones that carry the finding.

### Where he EXITS

| | n | per entry | win | med hold |
|---|---|---|---|---|
| exit at `frac` > 0.85 — at the leg's own end | 30 | **+$149** | **77%** | 12m |
| exit in the same pivot-leg he entered | 132 | +$6 | 54% | 13m |
| exit after that leg turned (held through a turn) | 24 | −$88 | 58% | 43m |
| — of those, on BAD days | 8 | **−$437** | 38% | 24m |

Median exit sits at **`frac` 0.54** of the leg and **3 minutes before** the nearest vertex. His exits
are *not* clustered at the turns, and the "exit at the leg's end" cell is his best and is **stable
across all three groups** (PRIMARY +$127, over-traded +$135, BAD +$170). The thing that costs him is
**holding through a turn on a bad day** — −$437/entry over 8.

---

## 4. (c) THE CLEAREST DIFFERENCE, IN ONE SENTENCE

> **On his good days he enters mid-leg and with the leg on a quiet, few-turn, one-way tape — median
> ATR 8, 90th percentile of the session range in his own direction, 16–45+ minutes clear of any
> turn — whereas on his bad days he enters into a fast, two-sided tape at ATR 15 that has already
> turned several times, and 39 of his 160 entries landed within 15 minutes of a turn and lost
> −$138 each at a 38% win rate while the 53 that landed 16–45 minutes away made +$82 each at 70%.**

The mechanism behind it is **adverse excursion, not direction**: median MAE over the actual hold is
**17.5pt WITH the leg vs 36.0pt AGAINST it**, and 24.9pt for entries within 15 min of a turn. On a
4-lot book with **no stop**, banking 50/100/200/300, the thing that decides the trade is how deep it
goes against him before it works — which is exactly what placement predicts.

---

## 5. THE REFRAME — PLACEMENT PREDICTS THE HOLD, NOT THE DIRECTION

Arm 1 established that his own entries race **52.3% vs 49.3% control at ±50pt (n=174, 2σ ±7.6pp)** —
his timing carries no measurable directional edge, and the money is in the asymmetric payoff. Arm 6
independently reaches the same place from the other side, and the agreement is the result:

| cell (all 9 days) | n | med hold | avail in leg | took | capture | MAE | win |
|---|---|---|---|---|---|---|---|
| WITH the pivot leg | 115 | 20m | 91.5pt | +13.6pt | 0.16 | 17.5pt | 65% |
| AGAINST the pivot leg | 45 | 13m | 19.8pt | −28.2pt | −0.52 | 36.0pt | 27% |
| 16–45 min from a pivot | 53 | 22m | 77.0pt | +20.7pt | **0.24** | 18.8pt | 70% |
| within 15 min of a pivot | 39 | 12m | 32.2pt | −11.5pt | **0.00** | 24.9pt | 38% |

`avail` = the most the leg still offered in his direction before it ended; `took` = pnl/(lots×2);
`capture` = took/avail. **An AGAINST-the-leg entry has only 19.8pt left to collect and he gives back
28.2 — placement decides the OPPORTUNITY, not just the outcome.** And placement predicts the hold:
22 minutes vs 12.

### Arm 1's trigger, confirmed a third way

Signed 15-minute move ÷ ATR, in the trade's direction, measured here on the tape:

| | median net15/ATR | WITH the line (>0) | AGAINST (≤0) |
|---|---|---|---|
| PRIMARY | **+2.42** | n=26, +$194, 73% | n=4, −$139, 25% |
| over-traded | +1.49 | n=40, +$36, 65% | n=16, +$5, 50% |
| BAD | +2.50 | n=63, −$95, 44% | n=11, −$89, 45% |
| ALL 9 | **+2.19** | n=129, +$4, 57% | n=31, −$47, 45% |

**Median +2.19 ATR against Arm 1's +2.24** — an independent replication on different data, from the
book side rather than the press side. **He is a continuation trader who joins a thrust.** The
against-the-line veto corroborates for the third time (45% vs 57% win), though the day-clustered CI
on its P&L effect spans zero (**+$54 [−$37, +$166]**) — it is real but small, and it is dominated by
the placement effect.

⚠ Note the BAD row: his net15 median there is **+2.50**, *higher* than on his good days. **He applies
the same trigger on both kinds of day.** The trigger is not what distinguishes them; the tape is.

### Quiet turns or violent ones?

Peak per-minute aggressive-size z within ±5 min of his entry (tick `size` only — one source, so no
timeframe double-count):

| | pivots | quiet (z<1) | climax (z≥3) | his entries: median peak-z | quiet | climax |
|---|---|---|---|---|---|---|
| PRIMARY (3 days) | 10 | 5 | 2 | **0.29 / 1.02 / 0.40** | 19/30 | 6/30 |
| BAD (4 days) | 31 | 18 | 5 | 1.82 / 3.70 / 0.55 / 0.64 | 31/74 | 26/74 |

**He trades quiet tape.** On the primary three days his median entry sits at peak-z **0.29–1.02** and
**19 of 30 entries are in genuinely quiet minutes (z<1)**, against 6 at a climax. On the bad days
climax entries rise to 26 of 74 and 09-28's median entry z is 3.70. That directly supports his
correction and Arm 2's finding: **a magnitude/climax detector cannot see what he is reading**, because
most of what he reads is not loud.

---

## 6. (d) RANKED SHORTLIST — CAUSAL CANDIDATES, WITH THEIR RACE RESULTS

**Race standard**: ±N arrives before ∓N on bar highs/lows within 120 min, from the close at the fire
minute. **50% IS ZERO.** 273 sessions of MNQ minute bars (197 from IBKR `1min` history
2025-09-14→2026-08-18, **76 from our own 5s capture aggregated to minutes** — reported separately,
because [[the-labs-tape-is-not-productions-tape]]). **Control is SIDE-MATCHED**: same direction as
the fire it pairs with, random minute, same session. The unit is an **EPISODE** (false→true
transition), never a minute. 2σ binomial at n≈1,400 is ±2.7pp; at n≈300 it is ±5.8pp.

---

**RANK 1 — PROMISING, and it is a DAY FILTER, not an entry.**
*Do not take a discretionary entry when ATR14 ≥ 12 and the day has already produced ≥ 3 confirmed
15×ATR turns.*

Fully causal: both terms are in `turn_watch`'s live state file today. Not raceable as an entry (it
emits no side), so it is scored on his own book:

| | n | total | per entry | win |
|---|---|---|---|---|
| ≥3 turns confirmed today | **19** | **−$3,343** | −$176 | 32% |
| 0–2 turns | 141 | +$2,413 | +$17 | 57% |
| ATR < 8 | 21 | +$1,250 | +$60 | 67% |
| ATR ≥ 12 | 88 | −$1,208 | −$14 | 51% |

**All 19 of the ≥3-turns entries are on losing days; the primary three days never reached 3 turns.**
Likewise **zero** of 30 primary entries were taken within 30 min of a confirmed flip, against 13 of
74 on bad days (−$2,250). ⚠ In-sample and partly tautological — days with many turns and high ATR are
*why* they were bad days. But it is the only candidate here that is (i) fully causal, (ii) already
computed by a running service, (iii) a **veto**, so it cannot invent a trade. It is cheap to trial
as an advisory line on the dashboard.

---

**RANK 2 — PROMISING as a HOLD rule, not an entry.**
*Once in, do not carry a position through a confirmed turn on a high-ATR day.*

Holding through the turn of the leg he entered: **−$437/entry over 8 on the bad days** (+$97 over 8
on the primary days). And exits at the leg's own end are his best cell at **+$149/entry, 77%, n=30,
stable across all three groups**. This is a `step_away`-shaped intervention — it can be expressed by
writing `day_rider_claim.txt`, the file his own Claim button writes, with **no order path at all**.
⚠ n=8 per group. This is a hypothesis, nothing more.

---

**RANK 3 — the causally-confirmed pivot, REFUTED as a directional entry.**
*A trailing-90min extreme printed 20–45 min ago, the leg into it travelled ≥60pt, price has already
travelled ≥60pt back out, and no new extreme has printed since.* Every term reads minutes ≤ i.

| spec | fires | /session | long% | ±50 rule | ctrl | edge | n | ±100 edge | ±50 on 5s tape only |
|---|---|---|---|---|---|---|---|---|---|
| P1 as derived (20–45m, 60pt) | 2567 | **9.40** | 54 | 50.8 | 47.3 | **+3.5** | 2278 | +3.9 | 51.6 vs 48.5 (n=825) |
| P1a legs 40pt | 3882 | 14.22 | 52 | 50.5 | 49.0 | +1.5 | 3203 | +1.2 | |
| P1b legs 90pt | 1390 | **5.09** | 56 | 49.6 | 46.1 | **+3.5** | 1301 | +5.2 | **49.5 vs 48.6 (n=463)** |
| P1c age 10–30m | 2535 | 9.29 | 55 | 50.5 | 47.7 | +2.7 | 2325 | +5.0 | |
| P1d age 45–90m | 2182 | 7.99 | 53 | 50.0 | 49.8 | +0.2 | 1837 | −2.4 | |
| P1e + ATR≤10 | 842 | **3.08** | 57 | 50.0 | 47.6 | +2.4 | 618 | +2.9 | 50.2 vs **52.9** (n=239) |
| P1f + with day's half of range | 1545 | 5.66 | 53 | 50.2 | 51.4 | −1.2 | 1372 | −5.6 | 49.9 vs **57.3** |
| P1g 60-min window | 2860 | 10.48 | 56 | 50.7 | 48.2 | +2.5 | 2561 | +1.9 | |
| P1h 120-min window | 2222 | 8.14 | 54 | 50.1 | 47.5 | +2.6 | 1978 | +4.0 | |

**REJECTED, on three independent grounds:**

1. **Fire rate.** The version with the best edge fires **9.4/session**. The standard rejects >6
   however accurate. The versions that fit the rate (P1b 5.09, P1e 3.08) carry the weakest evidence.
2. **The robustness sweep Arm 1 earned.** Sliding the age band in 10-minute steps:

   | band | 5–30 | 15–40 | 25–50 | 35–60 | 45–70 | 55–80 | 65–90 | 75–100 | 85–110 |
   |---|---|---|---|---|---|---|---|---|---|
   | ±50 edge | +1.9 | +1.2 | +0.5 | +1.3 | +1.5 | +2.4 | −2.3 | +0.2 | +1.3 |

   **Mean +0.89pp, spread −2.3 … +2.4.** The +3.5pp at 20–45 is a favourable draw from a
   distribution centred near zero. This is the window-boundary failure mode, caught the way Arm 1
   said to catch it.
3. **The two tapes disagree.** On **our own 5s capture** — the input production actually reads —
   P1b is **49.5 vs 48.6 (+0.9pp)** and P1e is **50.2 vs 52.9 (−2.7pp)**. The nominal edge lives in
   the IBKR `1min` half.

---

**RANK 4 — the earlier shape, REFUTED outright.**
*"The old quiet run"*: live 15×ATR direction, ≤1 turn today, ≥120 min since the flip, ≥10 ATR of run
banked, ATR ≤ 10, `extreme_pos` ≥ 90, giveback ≤ 2 ATR. **9.39 fires/session, ±50pt 47.7% vs 50.1%
control = −2.4pp (n=1430); ±100pt −4.1pp.** Six one-at-a-time ablations span −5.1 … +3.0pp, i.e.
noise. ⚠ These twelve specs were raced against a **random-side** control before the correction
arrived; a side-matched control would move them toward zero, and they are already negative, so the
conclusion stands.

---

**RANK 5 — REFUTED, and this one is the most useful negative in the arm.**
*"Trade with the snake"* implemented through `turn_watch`'s **live** state:

| | n | total | per entry | win |
|---|---|---|---|---|
| WITH the live 15×ATR direction | 83 | −$1,112 | **−$13** | 54% |
| AGAINST it | 77 | +$182 | **+$2** | 55% |
| *(for contrast)* WITH the hindsight pivot leg | 115 | +$10,038 | +$87 | 65% |

**The sign is backwards and the separation is gone.** At 15×ATR the flip confirms 107–190 pt after
the vertex, so the live label frequently still points at the move that already ended — and on the
bad days WITH-the-live-direction is the *worse* cell (−$153/entry vs −$34). Anyone building on
`turn_watch_state.json` as a "which way is the day going" input should read this first.

The causal restatement of the *veto* fails the same way: **"a trailing-90min extreme printed ≤15 min
ago"** has **33% precision / 95% recall** against the hindsight label — it is true at 109 of 159
entries, because on a trending tape a new trailing extreme prints constantly. Its effect on his book
(+$45/entry kept vs −$0 as traded) has a day-clustered CI of **+$58 [−$70, +$200]**, and the
"travelled <60pt out" variant moves the P&L the **wrong way**. It cannot tell a continuation's new
high from a top, which is the whole job.

---

## 7. WHAT I LOOKED AT AND DID NOT FIND

- **CVD at entry does not separate.** Direction-normalised, `cvd_dir ≥ 80` (aggression pinned his
  way) = −$10/entry over 69; `cvd_dir < 20` = −$8 over 19. It inverts between groups (PRIMARY +$145
  at ≥80, BAD −$71), which is a group effect, not a signal. His primary-day entries span the whole
  gauge (CVD 2 to 100).
- **`frac` into the leg is nearly uniform** on his good days (median ≈0.55, spanning 0.04–0.98). He
  does not favour the start, the middle or the end of a leg — he favours *not being near its ends*,
  which is a different statement and is the `|min from pivot|` result.
- **Hold time is not the subject and is not the discriminator.** The three primary days run 98 / 55 /
  50 minutes median and the two over-traded profitable days run 16 / 5 — yet 09-25 is **+$56, not
  +$975**, once its overnight short is attributed to the right session. The over-traded days' entries
  sit **mid-range** (`extreme_pos` median 60.9 vs 90.4 primary) and their `run_atr` median is 8.8
  against 18.4 — so they are **not** in the same place on the snake. Placement and hold move together
  here; I cannot separate them at n=30.
- **Position in the session range alone** is not it: `extreme_pos ≥ 90` is +$263/entry on PRIMARY and
  −$149 on BAD.

---

## 8. SEARCH CHARGED, AND THE LIMITS

**Cells reported: ~272.** Descriptive placement cells 212 (sets A–H 100, I–L 56, M–O 36, Q 20);
race cells 60 (24 random-side R1 specs ×2 targets, 18 side-matched P1 specs ×2, 18 age-band sweep).
No cell was selected for reporting by its result.

⚠ **n = 30 entries on the primary three days, 160 across all nine, 9 sessions.** Per-observation 2σ
on the headline win rates: WITH-leg 65.2% ±8.9pp (n=115), AGAINST 26.7% ±13.2pp (n=45), within-15min
38.5% ±15.6pp (n=39), 16–45min 69.8% ±12.6pp (n=53). Day-clustered intervals are wider than those
and are the ones quoted in §0.
⚠ **The nine days were chosen by P&L and the thresholds were read off these same entries.** The
day-level findings (ATR, turn count) are partly tautological with that selection.
⚠ **The pivot and `frac` labels are hindsight** and are stated as descriptions throughout.
⚠ **All of this is PAPER**, 4 lots, with `fill_clean` excluding the engine's fabricated fills. It is
unknown whether a live account behaves the same way.
⚠ **The 09-21 and 09-28 sessions begin at 00:00Z, not 22:00Z** — our capture has no Sunday-evening
reopen for those two, so their snakes are 1,260 minutes rather than 1,380.

---

## 9. WHAT I WOULD HAND THE LAB

1. **The placement measurement itself**, on all 616 sessions and on his whole press history rather
   than nine days: *does distance-to-the-nearest-pivot predict MAE and hold length?* That is the
   claim with a day-clustered CI excluding zero here, and it is a **hold/risk** question, not a
   direction question, so it is not the thing Arms 1–5 already refuted.
2. **The causal-label problem as the explicit target.** The gap between the hindsight pivot (65%/27%)
   and every causal proxy (no separation) is the whole finding. The next thing worth building is not
   another entry signal — it is a **better causal estimator of "has the leg ended"** scored on
   precision/recall against the ±90min/60pt label, not on P&L. Three non-price inputs are untried for
   that job and are available: L2 depth (Arm 3), multi-timeframe agreement (Arm 4), and the
   participation/aggressor mix at the extreme.
3. **RANK 1 as a dashboard line, not a gate.** "ATR 15.2 · 3 turns confirmed today" next to his
   buttons costs nothing, has no order path, and is the only causal thing here that distinguished his
   good days from his bad ones.
