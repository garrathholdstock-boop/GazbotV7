# REHAB — `MAX_HOLD` (the 2-hour time-cap exit)

**Target:** the week's worst per-trade exit. 2 fires, −$255.50, −$127.75 each — about 3.5× the average STOP (−$36.63).
**Data:** `data/gazbot7.db` (601 live trades, 07-16 → 08-07) · `data/shadow.db` (7,639 shadow trades, 53 sims) · `data/capture.db` (5s MNQ bars + 6.76m trade ticks, 21 trading days 07-15 → 08-07).
**Cost basis:** $2.00/point, $1.50/round-turn. Every number below is tick-honest and re-derived from prices, not read off a field.
**Working:** `scratchpad/rehab_maxhold/` — `tape.py` · `normalize.py` · `capsweep.py` · `fakewin.py` · `mfe_release.py` · `robust.py` · `decisive.py` · `proven.py`, with raw output in `out_*.txt`.

---

## THE SHORT VERSION

I was handed three rehab angles and a symptom. Here is what I found, in the order it matters.

**First, the symptom is measured on rows the desk has already thrown away.** Both of this week's MAX_HOLD fires carry `data_quality = EXCLUDE:md_stream_atr_corruption_20260804`. `pnl.py` filters them at source. The desk's own canonical P&L for this week books MAX_HOLD at **zero fires and $0.00**. The −$255.50 in the brief comes from reading the raw `trades` table without the exclusion clause. That is worth saying plainly before anything else, because it means the headline "worst per-trade exit mechanism on the desk" is being computed on two rows the desk formally does not count.

**Second, I widened the window and it got more interesting, not less.** The brief says 2 fires. MAX_HOLD has fired **4 times all-time**, for **−$642.50**. Two of them are from the archive (07-21 and 07-22) and nobody has looked at them. Four fires, four losers, no winners ever.

**Third — and this is the whole finding — all four are the same thing, and it is not an exit problem.** I reconstructed every one on the 5s tape. In every single case a working 1.0×ATR stop would have cut the trade **inside five minutes** for a normal-sized loss. The four fires together should have cost **−$128.54**. They cost −$642.50. **Eighty percent of the MAX_HOLD book — $513.96 — is a stop that did not work, not a clock that held too long.** MAX_HOLD is not an exit mechanism the desk chose. It is the last thing standing when everything upstream has already broken, and grading it on the damage is grading the fire alarm for the fire.

**Fourth, the brief's main angle — shorten the cap / release early — is a FAKE WIN and I am rejecting it.** A blanket sweep looks fantastic: a 5-minute cap earns +$4,976 by cutting losers. But it hands back −$4,382 by clipping winners, and only **4 of the desk's top 20 winners survive it intact**. The top-20 winner pool falls from $4,356 to $1,864 — the runners get slaughtered — to net +$594. That is exactly the trade the 15/17-winners rule exists to refuse. Ironically, **the 120-minute cap is the only setting in the entire sweep that takes money purely from losers and nothing at all from winners: 20/20 top winners intact, $0 off the winner pool, in 601 live and 7,473 shadow trades.** The number the operator guessed is the one number that passes.

**Fifth, there IS a real defect in MAX_HOLD, and it is not the length — it is that the cap is not enforced.** Trade id171 ran **278.9 minutes** — the cap fired **159 minutes late**. Trade id54 ran **277.1 minutes** and MAX_HOLD **never fired at all** (it exited on ABSORPTION_CUT). Had the cap simply been honoured at 120 minutes, those two trades would have been **+$461.50 better** — id54 alone would have booked **+$225.50 instead of −$141.00**. The cap is only alive while the 5-second audit loop is alive; when the loop dies, the ceiling dies with it and the position rides.

**Sixth, the honest deflater.** I ran a placebo on the 120-minute cap: keep the same three trades, but exit at a *random* moment in each trade's life instead of at the cap. Random timing matched or beat the real cap in **161 of 400 draws (pseudo-p = 0.403)**. The cap has **no timing skill whatsoever**. Its +$460 is not "120 minutes was the right moment" — it is "literally any exit would have been better than what actually happened." Which is the same finding as everything above, said a third way.

**Verdict: FIXED — but the fix is an enforcement guarantee, not a new exit rule, and most of the cure already shipped.** Exact config at the end. Three of the four rehab angles I was given came back NULL and I have shown all three by name.

---

## 1 · NORMALIZE THE MALFUNCTIONS

Every MAX_HOLD fire in the desk's history, reconstructed tick-honest.

### 1a — The complete book, and what a working stop would have done

| # | date/time (UTC) | gate | side | hold | booked | entry ATR | MFE | MAE | working 1.0×ATR stop | malfunction cost |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|
| id114 | 07-21 00:30 | `rgv_short` | SHORT | 120.1m | **−$171.00** | 20.30 | **−6.5pt** | 124.5pt | fills 00:31:00 (**0.9m in**) → −$42.11 | **−$128.89** |
| id171 | 07-22 00:05 | `grind_long` | LONG | **278.9m** | **−$216.00** | 12.46 | +13.5pt | 135.8pt | fills 00:10:10 (**5.1m in**) → −$26.43 | **−$189.57** |
| id538 | 08-04 22:02 | `abs_veto_short_A` | SHORT | 120.0m | **−$124.50** | 14.25 | +14.3pt | 67.5pt | fills 22:05:00 (**3.0m in**) → −$30.00 | **−$94.50** |
| id539 | 08-04 22:02 | `abs_veto_short_B` | SHORT | 120.0m | **−$131.00** | 14.25 | +10.8pt | 71.0pt | fills 22:05:00 (**3.0m in**) → −$30.00 | **−$101.00** |
| | | | | | **−$642.50** | | | | **−$128.54** | **−$513.96** |

Read that MFE column. The best any of these four trades ever looked was **+14.25 points**. One of them (id114) was **never favourable by a single tick** — MFE of *minus* 6.5. These are not positions that went good and then went bad and the clock caught them late. They were wrong from the opening print and the machine simply did not close them.

And read the stop column. **0.9 minutes. 5.1 minutes. 3.0 minutes. 3.0 minutes.** Every single one of these trades had a valid 1-ATR stop level touched inside the first five minutes of its life. The 2-hour clock is 24× to 133× later than the exit that should have happened. There is no version of this where the time cap is the mechanism under investigation.

### 1b — What actually broke, per fire

**id114 and id171 (07-21, 07-22) — the resting-stop defect.** The desk's own code comments this incident at `multislot_core.py:606`: *"IBKR paper converted a triggered STP to a stale unfillable limit; the short rode 84pt to the 120-min MAX_HOLD, −$171 vs the ~−$44 a filled stop caps."* My independent reconstruction says −$42.11, which matches. Fixed twice: commit `551923b` (07-21) added the triggered-but-unfilled guard, and `d0218c6` (07-28) promoted the tape-based stop to *primary*, firing every tick rather than waiting for IBKR.

**id538 and id539 (08-04 22:02) — the MD-stream ATR corruption.** MGC (gold) joined the capture stream and `tournament.py` folded it into the MNQ bar deque, so ~3,300-handle gold bars interleaved with ~29,800-handle MNQ bars. ATR read in the thousands against a true 14.25. Both lots were opened with stops placed *hundreds of points* away instead of ~14, so the tape-primary stop — working perfectly — never had anything to trigger against. The failure mode had moved from "the stop doesn't fire" to "the stop is placed on garbage." Already flagged `EXCLUDE` and already excluded at source.

**A detail nobody has flagged: these two fired 2 minutes after the 21:00–22:00 UTC CME maintenance break.** I confirmed the gap in the tape directly (bars stop at 20:59:55 and resume at 22:00:00). At 22:02 the desk had **two minutes** of post-reopen bars in a 14-bar ATR window. Whatever else was wrong, the gate was also making an ATR-relative decision on a deque that had just been emptied by an hour of no market.

**Cross-confirmation the shadow book gives for free:** my tape-consistency screen (does the row's own `entry_price` actually match the MNQ tape at that instant?) struck **166 of 7,639 shadow rows across 14 separate days** — 07-17, 07-20, 07-23, 07-24, 07-26 through 07-30, and 08-03 through 08-07. **The MD-stream contamination is not a one-night 08-04 event. It is a recurring, fourteen-day condition in the shadow book, and nothing currently flags it there.** That is a finding this rehab produced by accident and it is probably worth more than the rehab.

### 1c — The second malfunction: the cap itself did not fire

| id | gate | hold | cap should fire at | actually fired | late by | booked | P&L at the 120m mark | cost of lateness |
|---|---|---:|---|---|---:|---:|---:|---:|
| id171 | `grind_long` | 278.9m | 120m | MAX_HOLD @ 278.9m | **+158.9m** | −$216.00 | −$121.00 | **−$95.00** |
| id54 | `thrust` | 277.1m | 120m | **never** (ABSORPTION_CUT) | **+157.1m** | −$141.00 | **+$225.50** | **−$366.50** |
| | | | | | | | | **−$461.50** |

id54 is the sharpest single fact in this report. It was a **winner at the cap** — up $225.50 at the 120-minute mark — and it was allowed to run another 157 minutes and come back as a −$141.00 loser, because nothing enforced the ceiling. The order log shows 4h38m of near-silence around id171's life; the cap fired the instant activity resumed. This is a liveness dependency, not a parameter choice.

### 1d — The normalized book

| | fires | net |
|---|---:|---:|
| RAW as booked, all-time | 4 | **−$642.50** |
| less the stop-failure component (a working 1.0×ATR stop on the true ATR) | | +$513.96 |
| **TRUE strategy cost of holding to a 2-hour cap** | 4 | **−$128.54** |
| memo: additional money lost because the cap fired late or not at all | 2 | −$461.50 |
| **THIS WEEK, as the desk actually books it (`data_quality IS NULL`)** | **0** | **$0.00** |

−$128.54 across four fires over 21 trading days. That is the entire honest bill for the 2-hour time cap.

---

## 2 · CORRECTED-COST RECONSTRUCT

I re-derived every MAX_HOLD row from entry and exit prices rather than trusting `pnl_usd`.

| id | side | qty | entry | exit | points | ×$2/pt | −$1.50 RT | recorded | delta |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 114 | SHORT | 1 | 28815.50 | 28900.25 | −84.75 | −169.50 | −171.00 | −171.00 | **0.00** |
| 171 | LONG | 1 | 29323.75 | 29216.50 | −107.25 | −214.50 | −216.00 | −216.00 | **0.00** |
| 538 | SHORT | 1 | 29789.75 | 29851.25 | −61.50 | −123.00 | −124.50 | −124.50 | **0.00** |
| 539 | SHORT | 1 | 29786.25 | 29851.00 | −64.75 | −129.50 | −131.00 | −131.00 | **0.00** |

**0 of 4 rows need restating.** The book is already at $2/point net of $1.50/RT; $6.00 of fees across four round turns. There is no hidden cost story — the money is real, it is just not *time-cap* money.

For scale: MAX_HOLD's −$642.50 is **15.1% of the desk's entire all-time −$4,256.50** across 601 trades, off **0.67% of the trades**. That is the number that makes it look like the worst mechanism on the desk. Strip the stop failures and it is 3.0%.

---

## 3 · ROOT CAUSE — BASE, EXIT, or SIGNAL?

**None of the three. It is the STOP, and secondarily the LIVENESS of the audit loop.**

Here is the structural argument, and then the evidence for it.

### 3a — A healthy trade cannot reach this cap

| | live book (n=599, dq-clean) | shadow book (n=7,473) |
|---|---:|---:|
| median hold | **2.49 min** | 6.0 min |
| mean hold | 7.67 min | 12.9 min |
| trades reaching 15 min | 62 (10.4%) | 1,819 |
| trades reaching 60 min | 10 (1.7%) | 96 |
| **trades reaching the 120-min cap** | **5 (0.83%)** | **30 (0.40%)** |

The cap sits at **48× the median hold**. Every slot carries a 1.0×ATR stop and a target/chandelier above it. For a position to survive two hours, one of those has to have failed. That is not an interpretation, it is arithmetic — and the four fires confirm it, because all four had touched a valid stop level within five minutes.

### 3b — The evidence: the stop fix moved the tail, not the frequency

I measured, for every live trade, how far price ran *past* its own 1.0×ATR stop before the trade closed, split at commit `d0218c6` (the tape-primary stop, 2026-07-28).

| era | n | ran >0.25×ATR past the stop | median overshoot | **max overshoot** |
|---|---:|---:|---:|---:|
| BEFORE 07-29 (resting-stop era) | 346 | 84 (24.3%) | 0.57×ATR | **9.89×ATR** |
| AFTER 07-29 (tape-primary stop) | 253 | 56 (22.1%) | 0.49×ATR | **1.24×ATR** |

The *frequency* barely moved — that is just tape granularity, a 5s bar wick past the stop before the ~2s tick check catches it, and it is harmless. What matters is the **tail: 9.89×ATR collapsed to 1.24×ATR**. A runaway of the size that reaches a two-hour cap is no longer possible on the live desk by that route. The road to MAX_HOLD has already been closed, in code, on 2026-07-28.

The 08-04 pair got there by a *different* road — a corrupt ATR meaning the stop was placed hundreds of points away — and that road was closed too, at source, on 08-05.

### 3c — Is the SIGNAL to blame? Partly, but it is not this rehab's problem

All four fires opened **overnight** (00:30, 00:05, 22:02, 22:02 UTC), and all four had a tiny MFE. Gates firing into already-exhausted overnight moves is a real issue — it is the `abs_veto` exhaustion-chase finding, it has its own rehab, and it is where that argument belongs. The relevant point *here* is narrow: a bad entry with a working stop costs ~$30–42. A bad entry with a broken stop costs $124–216. **The signal chose the direction; the stop chose the size of the loss; the clock chose nothing at all.**

---

## 4 · FILTERS AND ALTERNATIVES THAT KEEP THE WINNERS

Now the sweeps. Everything here is regime- and time-of-day-segmented per the 07-31 discipline, and every table carries a winner-preservation column so a fake win has nowhere to hide.

### 4a — ★ THE HEADLINE FAKE WIN: shortening the cap

The blanket cap-length sweep on the live book looks like an easy win. Decomposed, it is not.

| cap | saved on LOSERS | lost on WINNERS | NET | winners clipped | **top-20 winners intact** | **top-20 pool after** |
|---:|---:|---:|---:|---:|---:|---:|
| 5m | +$4,976 | **−$4,382** | +$594 | 96 | **4/20** | **$1,864** |
| 10m | +$2,534 | −$2,356 | +$178 | 50 | 7/20 | $2,658 |
| 15m | +$1,908 | −$1,154 | +$754 | 32 | 12/20 | $3,556 |
| 20m | +$1,384 | −$932 | +$451 | 25 | 12/20 | $3,526 |
| 30m | +$955 | −$296 | +$660 | 19 | 13/20 | $3,841 |
| 45m | +$471 | −$239 | +$232 | 12 | 15/20 | $3,993 |
| 60m | +$271 | −$126 | +$146 | 5 | 18/20 | $4,168 |
| 90m | +$490 | **$0** | +$490 | **0** | **20/20** | **$4,356** |
| **120m (live)** | **+$460** | **$0** | **+$460** | **0** | **20/20** | **$4,356** |

Top-20 winner pool with no cap at all: **$4,356**.

A 5-minute cap "makes" $594 by destroying **57% of the desk's best trades**. That is the textbook fake win and I am rejecting it outright. The same shape holds on the shadow book at far greater n — at a 5-minute cap only **1 of the top 30** winners survives and **$64,053** comes off the winner pool.

**Only caps of 90 minutes and longer take zero dollars off the winners.** The operator's 120-minute guess is inside the admissible region and the shorter "optimum" the naive sweep points at is a mirage.

### 4b — The runner audit, trade by trade

The operator's specific concern is the 4R/6R runners. I found all 51 live runners (MFE ≥ 3× entry ATR, worth $4,988 as booked) and put each candidate cap through them.

| cap | runners clipped | runner P&L | verdict |
|---:|---:|---:|---|
| 15m | 24 of 51 | $4,988 → **$4,386** (−$602) | clips the tail |
| 30m | 15 of 51 | $4,988 → $5,374 (+$385) | still clips the biggest ones |
| **120m** | **0 of 51** | $4,988 → **$4,988** | **untouched** |

The named casualties at 15 minutes are exactly the trades the desk lives on: `abs_veto_long_B` 07-29 (7.9R, $342 → $264), `grind_long_B` 07-29 (6.3R, 87-minute hold, **$305 → $148.50**), `abs_veto_short_B` 07-29 (6.3R, **$536 → $294**). Those three alone are −$477. A cap short enough to have caught the four malfunctions would have cost more than the malfunctions did.

### 4c — Angle 1 from the brief: MFE-conditioned early release — **NULL on the live desk**

*"cut at the cap only if the position never went favourable."* This is the right instinct — it is runner-safe **by construction**, since a runner has a large MFE by definition and can never be released. It sweeps beautifully on the shadow book and it does not work on the live one.

Rule: at T minutes after entry, if running MFE has never reached `mfe_r` × entry ATR, flatten at tape.

**Shadow book (n=7,473) — looks excellent:**

| T | MFE < | fires | delta | top-30 winners intact |
|---:|---:|---:|---:|---:|
| 10m | 0.75R | 181 | +$4,078 | **30/30** |
| **10m** | **1.00R** | **426** | **+$9,134** | **30/30** |
| 15m | 1.00R | 154 | +$4,386 | 30/30 |
| 20m | 1.00R | 76 | +$2,586 | 30/30 |
| 30m | 1.00R | 46 | +$1,904 | 30/30 |

A clean plateau, positive everywhere, zero winner damage. On the shadow book this is the best idea in the report.

**Live book (n=599) — it is not there:**

| T | MFE < 1.00R | fires | delta |
|---:|---:|---:|---:|
| 5m | | 83 | +$1,296 |
| 10m | | 25 | **−$139** |
| 15m | | 13 | **−$508** |
| 20m | | 7 | **−$262** |
| 30m | | 3 | **−$217** |
| 45m | | 1 | −$10 |
| 60m | | 1 | −$8 |

No plateau — noise straddling zero, mostly negative. Two books, opposite answers. So I ran the decisive test.

**THE DECISIVE TEST — is the MFE release an edge, or a stop-failure proxy?**

Test 1: split the shadow book by whether each row's price ever ran past that row's *own* stop.

| shadow bucket | n | base | delta from MFE release | fires |
|---|---:|---:|---:|---:|
| stop-HONEST | 2,904 | +$33,050 | **+$1,477** | 109 |
| **stop-LEAKED (ran past its own stop)** | **4,569** | −$47,366 | **+$7,658** | 317 |

**84% of the rule's shadow gain comes from rows where the sim's stop had already failed.** And the shadow sim's stop fails a *lot*: **44.0% of shadow trades ran more than 0.25×ATR past their own stop, median overshoot 0.56×ATR, maximum 32.32×ATR** — on a book where 7,402 of 7,473 rows carry a 1.0×ATR stop. That is a shadow-repricer integrity problem, and the MFE release is largely being paid to repair it.

Test 2: split the live book the same way.

| live bucket | n | base | delta from MFE release | fires |
|---|---:|---:|---:|---:|
| stop-HONEST | 331 | +$8,755 | **−$102** | 5 |
| stop-LEAKED | 268 | −$12,756 | **−$37** | 20 |
| BEFORE 07-29 (broken-stop era) | 346 | −$3,922 | −$208 | 15 |
| AFTER 07-29 (tape-primary stop) | 253 | −$79 | +$70 | 10 |

**On the live desk the rule loses money in both stop buckets.** The residual stop-honest shadow gain (+$1,477 over 109 fires, $13.60 a fire) does not replicate anywhere on live tape.

**Disposition: PARKED, not REFUTED** — 25 live fires is far too thin to disprove a mechanism, and the shadow stop-honest slice is genuinely positive. **Revival condition: re-test once the shadow repricer's stop leak is fixed (that 44% must come down), and only on the stop-honest slice; revive for live consideration if it clears +$10/fire over 60+ live fires.**

### 4d — Angle 2 from the brief: a session-boundary cap — **NULL (it reaches the same three trades)**

*"a session-boundary cap rather than a fixed 2h clock."*

| flat by (UTC) | fires | delta (live) | delta (shadow) | top winners intact |
|---|---:|---:|---:|---:|
| 00:00 | 3 | +$240 | +$1,076 | 20/20 · 30/30 |
| 02:00 | 4 | +$226 | +$320 | 20/20 · 30/30 |
| **04:00** | **3** | **+$378** | **+$730** | 20/20 · 30/30 |
| 06:00 | 3 | +$42 | −$300 | 20/20 · 30/30 |
| 13:00 | 4 | −$156 | +$350 | 19/20 · 30/30 |
| 20:00 / 21:00 | 0 | $0 | −$1,351 / +$121 | 20/20 |

It is winner-safe, and flat-by-04:00 is mildly positive. But look at the fire count: **three trades.** They are the *same three trades* the 120-minute cap already catches — id114, id171, id54. A session boundary is not a better mechanism, it is a different clock arriving at the same handful of malfunctions, and at 04:00 it arrives **later** than 120 minutes does for two of them. It buys nothing the existing cap does not already buy, and it introduces a wall-clock coupling the desk does not currently have.

**Disposition: PARKED. Revival condition: if the desk ever runs a strategy that deliberately holds for hours (day_rider holds ~7h20m and already has its own `flat_by_utc_s`), a session boundary is the correct primitive for THAT slot — but it is not an improvement to the general 2h backstop.**

### 4e — Angle 3 from the brief: paired-lot simultaneous flatten — **NULL, and it is a small null**

*"both lots hitting the same tick (no stagger, so the second lot eats the first lot's impact)."*

I found every group of live trades sharing an identical `closed_at` to the microsecond — 18 groups, 36 trades — and costed each lot against the best fill in its own group.

| | |
|---|---:|
| Same-instant flatten groups, all-time | 18 (36 trades of 601) |
| **Cost on the MAX_HOLD pair (id538/539)** | **−$0.50** (exits 29851.25 / 29851.00 — **one tick apart**) |
| Total cost across all 18 groups | −$55.00 |
| Of which one trade: `exhaustion_short` 08-07 (15.5pt spread) | −$31.00 |
| Total across the other 17 groups | −$24.00 |

The hypothesis is that the second lot eats the first lot's market impact. On the target event the two lots filled **one tick apart for fifty cents**, against a −$255.50 loss. Across the desk's entire history the effect is **−$55.00**, and 56% of that is a single unrelated trade. There is no slippage story here. Staggering the flatten would add code, add a window in which a naked position exists, and recover pennies.

**Disposition: REFUTED for this purpose.** Named test: full-book same-instant fill census, 18/18 groups, total −$55.00 against a book of −$4,256.50. There is no reformulation of "stagger the lots" that finds meaningful money in this data, because the fills are already one tick apart.

---

## 5 · ROBUSTNESS

Six policies, scored head-to-head as policies, not as static numbers.

- **P0** no cap (floor) · **P1** 120m as actually run · **P2** 120m *reliably enforced* · **P3** MFE-gated release T=10m, MFE<1.0R · **P4** session cap flat-by-04:00 · **P5** P2+P3

### 5a — Headline and strip-the-best (LIVE, n=599)

| policy | net | vs P1 | win% | strip-1 | strip-3 | strip-5 | strip-10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| P0 no cap | −$4,001 | $0 | 38.7% | −$4,537 | −$5,203 | −$5,752 | −$6,783 |
| P1 120m as-run | −$4,001 | $0 | 38.7% | −$4,537 | −$5,203 | −$5,752 | −$6,783 |
| **P2 120m enforced** | **−$3,541** | **+$460** | 38.9% | −$4,077 | −$4,743 | −$5,292 | −$6,367 |
| P3 MFE10<1.0R | −$4,140 | −$139 | 38.4% | −$4,676 | −$5,342 | −$5,891 | −$6,922 |
| P4 flat-by-04:00 | −$3,623 | +$378 | 38.9% | −$4,159 | −$4,825 | −$5,403 | −$6,496 |
| P5 P2+P3 | −$4,045 | −$44 | 38.4% | −$4,581 | −$5,247 | −$5,796 | −$6,827 |

P2's **+$460 advantage is exactly constant across strip-1, strip-3, strip-5 and strip-10.** That is not luck — it is structural. P2's gains come entirely from truncating *losses*, so stripping the best trades cannot erode it. It is the one property in this whole report that survives every cut cleanly.

P5 is worth noting: bolting the MFE release onto the enforced cap **destroys 90% of the cap's gain** (+$460 → −$44). The two rules fight.

### 5b — Per ISO week and leave-one-day-out (LIVE)

| policy | wk29 | wk30 | wk31 | wk32 |
|---|---:|---:|---:|---:|
| P1 120m as-run | −$662 | −$3,083 | +$516 | −$772 |
| **P2 120m enforced** | −$662 | **−$2,623** | +$516 | −$772 |
| P3 MFE10<1.0R | −$669 | −$3,284 | +$572 | −$758 |
| P4 flat-by-04:00 | −$662 | −$2,698 | +$509 | −$772 |

**P2's entire benefit is in wk30, and zero in the other three weeks.** Honest reading: the cap did something useful in exactly one week out of four, because that is the week the stop was broken. Leave-one-day-out is equally blunt — dropping 07-29 moves every policy by roughly −$1,200 and changes no ranking, because none of these policies touch 07-29 at all.

### 5c — Per regime and per time-of-day (LIVE)

| policy | normal-chop (182) | building (180) | clean-trend (145) | violent-whipsaw (83) |
|---|---:|---:|---:|---:|
| P1 120m as-run | −$2,307 | −$1,346 | +$184 | −$363 |
| **P2 120m enforced** | **−$1,941** | −$1,348 | **+$280** | −$363 |
| P3 MFE10<1.0R | −$2,194 | −$1,358 | +$407 | **−$670** |

| policy | US-session (368) | pre-open (121) | overnight (110) |
|---|---:|---:|---:|
| P1 120m as-run | −$2,879 | −$336 | −$785 |
| **P2 120m enforced** | −$2,879 | −$336 | **−$325** |
| P3 MFE10<1.0R | −$3,051 | −$564 | −$524 |

**The 120-minute cap is an overnight-only mechanism.** Its entire effect (+$460) lands in the overnight bucket and it is *literally inert* in the US session and pre-open — it has never once bound a trade there. That is the correct regime read and it matches the structure: overnight is the only window quiet enough and long enough for a position to survive two hours.

P3 fails the regime test independently — negative in violent-whipsaw (−$307 vs P1) and in dead-chop, positive only in clean-trend. A release rule that costs money precisely in the whipsaw regime where you would most want an escape hatch is not a risk tool.

### 5d — Out-of-sample and the placebo null

**Out-of-sample (LIVE), fit wk29–31 → test wk32:** the fit half picks a 90-minute cap (in-sample +$490). Applied untouched to wk32: **0 trades bound, delta $0.00.** The cap is completely inert out-of-sample. That is not a failure — it is the correct behaviour of insurance in a week where nothing broke — but it must be stated: **there is no out-of-sample evidence for any cap length, because there were no out-of-sample events.**

**Placebo null (LIVE, 120m cap, 3 bound trades, 400 shuffles):** keep the same three trades and the same number of exits, but exit at a *random* moment in each trade's life.

| | |
|---|---:|
| Real cap delta | **+$460** |
| Random-timing delta, median | +$420 |
| Random-timing delta, p05 / p95 | +$90 / +$645 |
| **Random matched or beat the real cap** | **161 of 400 draws (pseudo-p = 0.403)** |

**The 120-minute cap has no timing skill.** Any exit from those three trades was worth roughly the same. The cap is not a good exit — it is *an* exit, applied to positions that should never have still been open. (The same placebo at 30 minutes gives pseudo-p = 0.080, and on the shadow book at 120m, p = 0.058 — suggestive, but on a book I have just shown leaks past its own stops 44% of the time, so I will not lean on it.)

### 5e — The guess vs the proven optimum, winner-safe, per regime

The operator's rule: every threshold is a guess until swept. Here is the 120-minute guess swept per regime, with admissibility defined mechanically as *"takes ≤1% off the segment's winner pool."*

| segment (LIVE) | n | admissible range | proven optimum | delta | **trades bound** |
|---|---:|---|---:|---:|---:|
| all tape | 599 | ≥60m | 90m | +$490 | **3** |
| normal-chop | 182 | ≥60m | 180m | +$446 | **1** |
| building | 180 | ≥30m | 30m | +$180 | **2** |
| clean-trend | 145 | ≥90m | 120m | +$95 | **1** |
| violent-whipsaw | 83 | ≥30m | 30m | +$70 | **2** |
| US-session | 368 | ≥15m | 30m | +$516 | **4** |
| pre-open | 121 | ≥60m | 60m | +$5 | **1** |
| overnight | 110 | ≥90m | 90m | +$490 | **3** |

**I am not going to pretend this table is a result.** Look at the last column: every "proven optimum" rests on **one to four bound trades**. There is no plateau to find because there is barely any data — the cap almost never binds, which is the whole point of it. The only honest thing the table says is that **the admissible floor is 60–90 minutes almost everywhere** (below that you start clipping winners), and 120 is comfortably inside it with room to spare.

**Verdict on the guess: 120 minutes is NOT proven optimal — nothing here can prove a cap length. But it is proven ADMISSIBLE, it is the only region that never touches a winner, and no shorter alternative survives the fake-win test. Leave it alone.**

---

## 6 · VERDICT

# ✅ FIXED — with one change to ship

**MAX_HOLD is not a bad exit. It is a correctly-sized backstop whose entire recorded P&L consists of claims paid out on other components' failures.** Four fires in 21 days, all four with a valid stop level touched inside five minutes, all four overnight, all four with an MFE under 15 points. Strip the stop failures and the honest cost of the 2-hour ceiling is **−$128.54** — and this week, as the desk actually books it, **$0.00**.

Its length is right and every attempt to shorten it is a fake win: only caps of 90 minutes and longer take **zero** dollars off the winner pool, and the shorter "optima" the naive sweep points at cost 24 of 51 runners and 57% of the top-20 winners.

### The exact config

| knob | now | **ship** | why |
|---|---|---|---|
| `config.py: max_hold_minutes` | **120.0** | **120.0 — NO CHANGE** | only admissible region (≥90m) that never clips a winner; 0/51 runners touched; 20/20 top-20 intact |
| MFE-conditioned early release | none | **do not add** | −$139 live; 84% of its shadow gain is stop-leak repair; kills 90% of the cap's own value when combined |
| Session-boundary cap | none (global) | **do not add globally** | reaches the same 3 trades, later; keep `flat_by_utc_s` for slots that genuinely hold long (NIPC, day_rider) |
| Paired-lot flatten stagger | none | **do not add** | −$0.50 on the target event, −$55.00 across the desk's entire history |
| **Cap ENFORCEMENT** | audit-loop only | **★ THE ONE CHANGE — see below** | the cap fired 159 min late once and never once; cost **−$461.50** |

### ★ The one change to ship: make the ceiling survive a dead loop

The cap is only alive while the 5-second audit loop is alive. When the loop stalls, the ceiling stalls with it — id171 fired 158.9 minutes late, id54 never fired at all and gave back a **+$225.50** position to close at **−$141.00**.

1. **Arm the ceiling at the venue, not just in the loop.** When a slot opens, place a resting flatten scheduled for `opened_at + max_hold_minutes` that does not depend on the desk process being alive. The desk already has the pattern — `_flatten_slot` is idempotent and the `_closing` latch makes a duplicate harmless.
2. **Make a stale audit loop loud.** `audit_stale()` already exists and already gates the systemd watchdog ping. Extend it: if any slot is open past `0.9 × max_hold_minutes` and the auditor has not completed a cycle, notify immediately rather than waiting for the restart to catch up.
3. **Book the overrun.** When MAX_HOLD fires more than 5 minutes past the ceiling, book it as `MAX_HOLD_LATE`, not `MAX_HOLD`. Right now a 278.9-minute hold and a 120.1-minute hold carry the same label, which is exactly why nobody noticed.

**Expected value: +$461.50 over the observed archive, all of it from cutting losses, none of it from winners.** It survives strip-10 unchanged because it cannot touch a winner by construction.

### The honest caveats

- **The cap is inert out-of-sample.** Fit wk29–31 → wk32: **zero trades bound**. There is no OOS evidence for any cap length because there were no OOS events. This is insurance; the correct expected number of claims is zero.
- **The placebo says the cap has no timing skill** (pseudo-p = 0.403). Its value is "there is a ceiling at all", not "the ceiling is at 120."
- **All four fires are overnight and every regime table shows the cap inert in the US session.** Anything claimed about the cap is an overnight claim.
- **The shadow book cannot arbitrate this question.** It leaks past its own stops on 44% of trades with a maximum overshoot of 32×ATR, so every shadow result that rewards early exits is inflated by that leak.
- **n is tiny and I am not hiding it.** Four fires, five over-cap trades, three bound by the cap. Every per-regime "optimum" in §5e rests on 1–4 trades.

---

## 7 · DISPOSITION TABLE

| lead | verdict | detail / revival condition |
|---|---|---|
| **`MAX_HOLD` 120-min cap as an exit** | **✅ FIXED (no length change)** | Only admissible region; 0/51 runners clipped; 20/20 top winners intact; true cost −$128.54 not −$642.50 |
| **Cap enforcement (audit-loop liveness)** | **✅ FIXED — SHIP** | Venue-side ceiling + stale-auditor alarm + `MAX_HOLD_LATE` label. Worth **+$461.50** on the archive |
| Shorten the cap (5–60 min) | **REFUTED** | Named test: winner-decomposition + runner audit. 5m leaves **4/20** top winners and −$4,382 off the pool for +$594. Textbook fake win |
| MFE-conditioned early release (T=10m, MFE<1.0R) | **PARKED** | −$139 live; 84% of shadow gain from stop-leaked rows; negative in both live stop buckets. **Revive** once the shadow repricer's 44% stop leak is fixed, re-test on the stop-honest slice only, promote if >+$10/fire over 60+ live fires |
| MAE-conditioned release (stop-failure alarm) | **PARKED — already superseded** | +$28,881 on shadow is an artifact of the shadow book's own 44% stop leak. The live desk shipped this mechanism on 07-28 as the tape-primary stop and it cut the overshoot tail from 9.89×ATR to 1.24×ATR. **Revive** only if live overshoot tail re-expands past ~2×ATR |
| Session-boundary cap (flat by fixed UTC) | **PARKED** | Winner-safe but reaches the same 3 malfunction trades, later. **Revive** for any slot that deliberately holds >1h (day_rider, NIPC already have `flat_by_utc_s`) — not as a global replacement |
| Paired-lot simultaneous-flatten stagger | **REFUTED** | Named test: 18/18 same-instant fill groups, all-time cost **−$55.00**; the target pair filled **one tick apart for −$0.50** |
| **★ Shadow-book MD contamination (NEW, unasked-for)** | **SHADOW — escalate** | The tape-consistency screen struck **166 of 7,639 rows across 14 days**, not just 08-04. Nothing flags these. `shadow.db` needs the `data_quality` column `gazbot7.db` already has |
| **★ Shadow repricer stop leak (NEW, unasked-for)** | **SHADOW — escalate** | **44.0%** of shadow trades ran >0.25×ATR past their own stop; median 0.56×ATR, **max 32.32×ATR**, on a book that is 99% 1.0×ATR stops. Every shadow study that rewards cutting early is inflated by this |

**LIVE candidates from this section:** one — the cap-enforcement guarantee (§6). **SHADOW candidates:** two, and both are data-integrity escalations rather than strategies.

**The one stone still unturned:** every MAX_HOLD fire opened overnight and two of them fired *two minutes* after the 21:00–22:00 UTC CME reopen, on an ATR window holding two minutes of bars. I have not tested whether a **reopen cool-down** (no entries for N minutes after 22:00 UTC until the bar deque refills) would have prevented the 08-04 pair outright. That belongs to the entry rehab, not the exit rehab, but it is the single most promising untested idea this reconstruction turned up.
