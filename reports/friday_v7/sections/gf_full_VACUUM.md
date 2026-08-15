# GREENFIELD HUNT — cluster **VACUUM** (census 2026-08-09 → 2026-08-15)

**The job:** ignore every gate we own, invent a brand-new entry signal from scratch that shows up for
the runs the census filed under VACUUM, spec it mechanically, backtest it tick-honest over the **full
Parquet lake** at the **true $1.50 round-trip fee**, and try hard to kill it.

**Two answers, and the first one matters more than the second.**

**1. The VACUUM label is not a footprint. It is a coin flip.** Before building anything on top of it I
checked its base rate on all bars, the way the standing instruction demands. The flow event the label
is built on fires on **20.7% of every minute of tape we own** — one minute in five, not a rare tell. And
once it has fired, the direction test that turns it into "VACUUM" comes up the VACUUM way **51.3% of the
time** — against **51.2% on the minutes where no flow event happened at all**. The label adds
**one tenth of one percentage point** of information, on a measurement whose own error bar is ±1.15pp.
There is no cluster there. VACUUM is the name we give a normal flow minute after a coin has landed.

**2. Hunting anyway found a real edge — but it is not the one we were sent for.** A signal I've called
**VAC-ABS** (huge one-sided aggression that *fails* to move price → fade it) books **+$1,843 over 74
trades, +$24.91 a trade net of $1.50/RT**, and it passes the mechanism tests convincingly: the sign-flip
loses −$2,388, the time-shifted placebo loses, and it beats 98.5% of 200 random-minute fakes. But it
**does not catch the runs**. Against the census's own sat-out list it scores **4 of 60**, and against the
top-15 biggest sat-out runs it scores **0 of 15**. Its money comes from somewhere else entirely. It also
fails strip-5 and its out-of-sample leg is negative. It goes to **SHADOW**, honestly labelled as a
mean-reversion scalp and *not* as an answer to "how do we grab the big runs".

**And the size-threshold question, answered: there isn't one.** The escalation the mandate asks for —
full sat-out → top-25 → top-15 — shows the footprint getting *weaker*, not stronger, as the runs get
bigger. Full detail below, every attempt by name, nulls included.

---

## 1. What the census actually labelled, and the trap inside it

`scripts/run_census.py` calls a run **VACUUM** when, in the 60 seconds before the run starts, the net
aggressor flow was unusual for that moment (|z| ≥ 1.0 against the trailing two hours of the same
statistic) **and pointed the opposite way to the move that followed**. In plain English: the tape was
full of buyers and then price fell.

There were **8** such runs this week, all 8 sat out, **$928 of 1-lot hindsight ceiling** between them.

| # | Run start (UTC) | Dir | Move | $ ceiling | 60s flow | amp% | book |
|---|---|---|---|---|---|---|---|
| 1 | 08-10 06:13 | DN | −50 | $100 | +166 | 0.07 | 0.44 |
| 2 | 08-10 07:11 | UP | +54 | $108 | −659 | 0.11 | 0.47 |
| 3 | 08-10 23:47 | DN | −48 | $96 | +351 | 0.07 | 0.53 |
| 4 | 08-11 00:02 | UP | +74 | $149 | −377 | 0.14 | 0.48 |
| 5 | 08-11 12:01 | UP | +47 | $94 | −305 | 0.05 | 0.49 |
| 6 | 08-12 00:08 | UP | +44 | $89 | −200 | 0.08 | 0.54 |
| 7 | 08-12 12:25 | UP | +87 | $174 | −161 | 0.07 | 0.53 |
| 8 | 08-12 20:05 | DN | −59 | $118 | +392 | 0.11 | 0.52 |

Now look at the definition again, carefully. **The label uses the forward move to decide the label.** You
cannot know a minute is VACUUM until you already know which way price went for the next fifteen minutes.
That is fine for a *taxonomy* — it is a description of what happened — but it means the label can never
be a trigger, and any signal built "on VACUUM" is really a signal built on the one thing that *is*
knowable in advance: the flow z-score. So that is the thing I tested.

---

## 2. ★ THE LABEL INTERROGATION — the finding that outranks everything else here

I rebuilt the census's own statistic on **every minute of MNQ tape in the lake**, 2026-07-05 22:00Z →
2026-08-14 21:00Z, **35,358 minutes** across 28 trading days (V5 archive + Parquet lake + hot capture,
via `gazbot7.lake` — not `capture.db`, which would have given me a fifth of it and no error message).
For each minute: the 60-second net aggressor flow, its z-score against the trailing two hours of the same
statistic with the census's own ≥30-bucket minimum, and the forward 15-minute close-to-close move with
contiguity enforced at both ends so nothing straddles a weekend or the 07-18→07-24 tick hole.

**34,724 minutes were fully scorable. Here is the whole finding in one table.**

| Question | Answer |
|---|---|
| How often does the flow event (\|z\| ≥ 1.0) fire? | **7,196 / 34,724 = 20.7% of all minutes** |
| Given it fired, how often does flow disagree with the next 15 min (= VACUUM)? | **3,689 / 7,196 = 51.3%** |
| VACUUM's base rate over all tape | **10.6% of every minute we own** |
| Disagreement rate on **non-event** minutes (\|z\| < 1) | **51.2%** |
| Difference | **+0.1pp**, against a ±1.15pp error bar |

One minute in ten of all tape is a "VACUUM" minute. That is not a footprint, that is the weather.

And it does not sharpen when you push the threshold. This is the same test at four z-bands, plus — the
more useful column — whether the flow tells you *anything* about where price goes next:

| Flow band | n | disagree% | mean fwd-15min move **in the flow's own direction** |
|---|---|---|---|
| \|z\| < 1.0 (ordinary minute) | 27,528 | 51.2% | −0.69 pt |
| \|z\| 1.0–1.5 | 3,523 | 51.1% | −1.77 pt |
| \|z\| 1.5–2.5 | 2,366 | 51.0% | +0.11 pt |
| \|z\| > 2.5 | 1,307 | 52.3% | −1.08 pt |

Flat. A three-sigma flow event tells you essentially nothing more than an ordinary minute does. And on
the census's own subset — the 6,677 minutes that actually started a ≥44pt 15-minute run — **51.9%** of the
flow events were "VACUUM", which is the same coin flip one more time.

**What this means for the report, plainly:** the 8 VACUUM runs are not 8 members of a family. They are
what you get when you take the ~25% of run-starts that happened to have a flow event and flip a coin.
Expected VACUUM share of run-starts on that arithmetic is 25.4% × 51.9% ≈ 13%; the census found 8 of 68
= 11.8% (the gap is the 13:00–15:00Z window, which `cluster()` assigns to OPEN/NEWS first). The
cluster is **exactly the size chance predicts**.

I want to be careful about what I am *not* saying. I am not saying the census is broken — the taxonomy
is doing an honest job of describing runs, and the 2026-08-01 fix that replaced the raw `|flow| > 50`
threshold (which fired on 66.5% of bars) with the z-score was a real improvement. What I am saying is
that **VACUUM has no predictive content and no gate should ever be armed on it**, and any future report
that opens "the VACUUM cluster suggests…" is building on sand.

---

## 3. The mechanism the label was reaching for — and where I went instead

The *idea* behind VACUUM is a good one and it is worth separating from the label. The idea is:
somebody leaned on the tape hard and it did not work, so they are trapped, so price goes the other way.
That is a real microstructure story. The census's version only tests half of it — it tests that the flow
was big, and then asks the future what happened. **The other half, the half that is knowable at the
time, is that the price did not respond.** Effort without result.

So I scanned for it. Same tape, same 34k minutes, and I asked: after each kind of minute, what is the
mean 15-minute move *against* the flow?

| Condition | n | fade-15min (mean pt) | win% |
|---|---|---|---|
| All minutes (the baseline) | 33,590 | **+0.73** | 50.4% |
| \|z\| ≥ 1 (the census's VACUUM trigger) | 6,938 | +0.96 | 51.1% |
| \|z\| ≥ 2 | 2,012 | +0.73 | 52.6% |
| \|z\| ≥ 3 | 831 | +1.49 | 52.3% |
| \|z\| ≥ 1 **and absorbed** (\|1-min close change\| ≤ 2.75pt) | 1,469 | +1.16 | 49.7% |
| \|z\| ≥ 2 **and absorbed** | 282 | +2.16 | 53.2% |
| **\|z\| ≥ 3 and absorbed** | **74** | **+8.01** | **59.5%** |
| \|z\| ≥ 2 and **climax** (big flow *with* a big same-way move) | 609 | −0.96 | 52.5% |
| \|z\| ≥ 2, ATR high tercile | 926 | −0.16 | 52.8% |
| \|z\| ≥ 2, ATR low tercile | 508 | +2.70 | 54.3% |

Two things jump out. First, there is a **small mean-reversion tilt on the whole tape** — +0.73pt against
the last minute's flow, on every minute, which is ordinary market-impact decay and is *not* an edge once
you pay for it (0.75pt of fee alone at $1.50/RT ÷ $2/pt). Every number in that table has to be read
against +0.73, not against zero.

Second, the **|z| ≥ 3 and absorbed** cell is genuinely different: **+8.01pt**, eleven times the baseline.
And note the climax row is *negative* — big flow that DOES move price keeps going. The absorption test
is doing the work, not the flow test. Mechanically coherent: trapped size, not exhausted size.

### Is that cell a plateau or a fitted spike?

The single most important check, because a corner of a grid with n=74 is exactly what a curve-fit looks
like. Mean fade-15min in points, with win% and n:

| z ≥ | \|dp\| ≤ 1.0 | ≤ 1.5 | ≤ 2.0 | ≤ 2.75 | ≤ 3.5 | ≤ 5.0 | no cap |
|---|---|---|---|---|---|---|---|
| **1.5** | +0.8/53%/233 | +1.1/52%/336 | +1.8/52%/441 | +1.3/52%/600 | +1.3/51%/748 | +1.7/52%/1054 | +0.2/51%/3531 |
| **2.0** | +2.7/56%/104 | +2.5/54%/149 | +2.4/55%/206 | +2.2/53%/282 | +2.8/55%/354 | +2.2/55%/510 | +0.6/53%/2009 |
| **2.5** | +5.7/67%/46 | +5.2/64%/61 | +4.4/63%/92 | +5.5/59%/132 | +5.8/61%/176 | +3.2/57%/259 | +0.9/52%/1250 |
| **3.0** | +7.4/72%/25 | +7.3/68%/34 | +5.5/65%/46 | **+8.0/59%/74** | +7.2/63%/105 | +5.0/59%/153 | +1.2/52%/828 |
| **3.5** | n=18 | +6.9/68%/25 | +6.1/68%/31 | +8.3/58%/48 | +8.3/62%/69 | +7.7/60%/97 | +0.1/51%/573 |
| **4.0** | n=16 | n=21 | +4.7/65%/26 | +9.4/61%/36 | +10.6/65%/52 | +11.4/65%/69 | −2.5/51%/427 |

That is a **plateau**, not a spike — every cell from z ≥ 2.5 down and rightward is positive, and it grows
monotonically with z. The "no cap" column (i.e. drop the absorption test) is flat near zero everywhere
and turns *negative* at z ≥ 4, which is the cleanest possible statement that **the absorption filter is
the signal and the flow z-score alone is not**.

Hold length is monotone too, which is what a genuine drift looks like rather than a fitted horizon:

| Hold | 5m | 10m | 15m | 20m | 30m | 45m | 60m |
|---|---|---|---|---|---|---|---|
| mean pt | +2.33 | +2.39 | +8.01 | +14.38 | +20.38 | +21.62 | +24.45 |
| win% | 59.5 | 55.4 | 59.5 | 60.8 | 61.6 | 52.7 | 59.5 |

---

## 4. **VAC-ABS** — the mechanical spec

| Component | Rule |
|---|---|
| **Instrument** | MNQ, $2.00/point. (Not ported to MGC — gold gates get invented fresh, see `gf_MGC`.) |
| **Clock** | 1-minute bars built from ticks. Every value below is computed on **completed** bars only. |
| **Flow** | `netflow` = Σ(buy size) − Σ(sell size) over the bar. |
| **Flow z** | `z` = (netflow − mean) / sd of the same 1-minute statistic over the trailing 120 minutes; requires ≥ 30 buckets, else no signal. |
| **TRIGGER** | `\|z\| ≥ 3.0` **AND** `\|close − prev close\| ≤ 2.75 pt` — huge one-sided aggression that moved price almost nothing. |
| **DIRECTION** | **Fade it.** netflow > 0 (buyers absorbed) → **SHORT**. netflow < 0 (sellers absorbed) → **LONG**. |
| **ENTRY** | Market on the **first tick after the trigger bar closes**. No same-bar entry, no lookahead. |
| **STOP** | 2.0 × ATR(1-min, 14) from entry. |
| **EXIT** | Stop, or **time-stop at 30 minutes**, whichever comes first. No target. |
| **COSTS** | **$1.50 per round trip** (the true venue fee) **plus 0.25pt slippage each way**, both charged in every number in this document. |
| **Left out and why** | No L2 filter (MNQ book only covers 15 days — half the sample, and I would rather have the n). No session filter in the base spec — that is the router's job, §7. No ER filter: §8 shows ER is *inverted* here. |

Fires **74 times in 28 trading days** — roughly one every two and a half days per side. Exit mix 42 TIME
/ 32 STOP. Average winner **+$101.45**, average loser **−$33.49**.

---

## 5. The tick-honest backtest, and the stop × hold surface

Every trade is walked tick by tick over the full lake (37.2M MNQ ticks), stop checked before time.

| stop (ATR) | hold 15m | hold 30m | hold 45m | hold 60m |
|---|---|---|---|---|
| 0.75 | +$69 (+0.93/tr, 18%) | +$486 (+6.57, 16%) | +$753 (+10.18, 11%) | +$844 (+11.41, 8%) |
| 1.0 | +$567 (+7.66, 27%) | +$1,209 (+16.33, 24%) | +$1,511 (+20.42, 22%) | +$1,408 (+19.03, 16%) |
| 1.5 | +$712 (+9.62, 38%) | +$1,257 (+16.99, 31%) | +$1,575 (+21.29, 28%) | +$1,457 (+19.69, 24%) |
| **2.0** | +$979 (+13.22, 46%) | **+$1,840 (+24.86, 43%)** | +$1,876 (+25.36, 36%) | +$2,095 (+28.31, 34%) |
| 3.0 | +$740 (+10.00, 49%) | +$1,779 (+24.04, 49%) | +$1,801 (+24.34, 43%) | +$1,805 (+24.39, 41%) |

**All twenty cells are positive.** I picked stop 2.0 ATR / hold 30 min because it sits in the middle of
the plateau on both axes, not because it is the maximum — 2.0/60 is $255 better and I am not taking it.

Note the win rate: 43%, and at the tight stops it drops to 8–18%. Per the operator's standing judging
rule that is **not** a kill criterion — the live desk booked +$625 this week at 39% — and here the shape
is explicit: average winner $101, average loser $33, a 3:1 payoff carrying a sub-half hit rate.

---

## 6. The robustness battery — what passed and what did not

**Headline: n=74, net +$1,840, 43.2% win, +$24.86/trade, best +$458, worst −$68.29.**

### PASSED

**Placebo / shuffle.** Same rules, same sides, same stop and exit — only the signal *times* moved:

| shift | n | net | $/tr |
|---|---|---|---|
| −120 min | 66 | −$358 | −5.42 |
| −60 min | 63 | −$529 | −8.40 |
| −30 min | 67 | −$957 | −14.29 |
| −11 min | 69 | +$8 | +0.12 |
| **REAL** | **74** | **+$1,840** | **+24.86** |
| +11 min | 74 | +$1,447 | +19.55 |
| +30 min | 73 | +$435 | +5.96 |
| +60 min | 68 | −$659 | −9.70 |
| +120 min | 66 | −$1,301 | −19.71 |
| +240 min | 69 | −$98 | −1.43 |

Read that shape: the money is a **sharp peak at zero that decays over about an hour and then goes
negative**. The +11 minute shift still books $1,447 because eleven minutes later you are usually still
inside the same absorption episode — that is persistence of the effect, not contamination of the test.
A fake signal does not book most of the money; a fake signal loses.

**Random-minute bootstrap, 200 draws**, matched on count with random sides: mean −$228, sd $874, 95th
percentile +$1,202, max +$2,011. The real book at +$1,840 **beats 98.5% of the fakes**. Honest caveat:
that is a p ≈ 0.015, respectable but not overwhelming, and one fake in the 200 did beat it.

**Sign-flip.** Trade *with* the absorbed flow instead of against it: **−$2,326 over the same 74 bars,
16.2% win.** This is the strongest single result in the section. The trigger is not merely selecting
volatile moments — it is selecting them *with a direction*, and the direction is the fade.

**Leave-one-day-out.** 24 days with trades. **Not one day's removal turns the book negative.** Worst LOO
is dropping 2026-07-27, which leaves n=69, +$1,403, +$20.33/tr. Green days 15/24, best day +$437,
worst day −$189.

**Cost stress.** Survives fees three times the truth:

| fee/RT + slip each way | net | $/tr |
|---|---|---|
| $1.50 + 0.25pt (the truth) | +$1,840 | +24.86 |
| $1.50 + 0.50pt | +$1,691 | +22.85 |
| $1.50 + 0.75pt | +$1,634 | +22.07 |
| $3.00 + 0.50pt | +$1,580 | +21.35 |
| $5.00 + 0.50pt | +$1,432 | +19.35 |
| $5.00 + 1.00pt | +$1,317 | +17.80 |

Worth naming: the **$5 figure a previous version of this prompt carried** would still have left this one
alive, but at −$400 it would have made every marginal cell in §3 look dead. On a signal with a $24/trade
expectancy, a fee 3.3× too high is the difference between a shadow candidate and a discarded one.

### FAILED

**Strip-the-best.** This is the one that hurts.

| | n | net | $/tr |
|---|---|---|---|
| full book | 74 | +$1,840 | +24.86 |
| strip-1 | 73 | +$1,382 | +18.93 |
| strip-3 | 71 | +$635 | +8.94 |
| **strip-5** | **69** | **+$98** | **+1.43** |
| **strip-10** | **64** | **−$534** | **−8.34** |

**Five trades are the entire book.** Strip them and there is nothing left but costs. The mandate's
strip-3 test is passed — $635 over 71 trades is still positive — but strip-5 is a wash and strip-10 is
negative, and I am not going to dress that up.

**Out-of-sample.** The chronological split decays badly and the held-out week is red:

| leg | n | net | win% | $/tr |
|---|---|---|---|---|
| first half | 37 | +$1,725 | 54.1% | +46.61 |
| second half | 37 | +$115 | 32.4% | +3.12 |
| in-sample (≤ 08-08) | 48 | +$1,979 | 52.1% | +41.24 |
| **OOS — the census week, 08-09 onward** | **26** | **−$139** | **26.9%** | **−5.36** |

**The census week is the out-of-sample leg, and VAC-ABS lost money in it.** That is the week this whole
section exists to explain. n=26 is thin enough that −$139 is well inside noise, but it is not evidence
for, and it means the signal has never been forward-validated on a week we did not fit it on.

**Long/short asymmetry.** Short does 86% of the earning:

| side | n | net | win% | $/tr |
|---|---|---|---|---|
| LONG (sellers absorbed) | 31 | +$258 | 38.7% | +8.32 |
| SHORT (buyers absorbed) | 43 | +$1,582 | 46.5% | +36.79 |

Both sides are green, which is better than it could be, but a 4.4× per-trade gap on n=31/43 is not
symmetry. Following the desk's two-sided-gate rule I would not relegate the long side — I would tune
it separately — but on this n I cannot tune anything honestly.

---

## 7. ★ THE ROUTER — where VAC-ABS is actually armed, and the honest hole in it

The mandate is explicit that a blanket cross-tape number is a bug. So: **all** of VAC-ABS's money is in
one regime, and the blanket +$24.86 is an average of a strong regime with two dead ones.

| segment | n | net | win% | $/tr |
|---|---|---|---|---|
| ATR(1m,14) **low** tercile (≤ 10.2pt) | 35 | −$88 | 34.3% | −2.51 |
| ATR **mid** tercile | 25 | −$154 | 36.0% | −6.17 |
| **ATR high tercile (≥ 15.2pt)** | **14** | **+$2,082** | **78.6%** | **+148.73** |
| US session 13:00–21:00Z | 23 | +$1,580 | 43.5% | +68.70 |
| overnight / pre-open | 51 | +$260 | 43.1% | +5.09 |
| ER15 < 0.15 (dead chop) | 23 | +$318 | 47.8% | +13.83 |
| ER15 0.15–0.35 | 24 | +$518 | 37.5% | +21.60 |
| ER15 ≥ 0.35 (trend) | 27 | +$1,004 | 44.4% | +37.17 |

The ATR split is the real one, and it is not just "the US session wearing a hat":

| | n | net | $/tr | win% |
|---|---|---|---|---|
| ATR-high **and** US session | 9 | +$1,683 | +187.02 | 67% |
| ATR-high **and** overnight | 5 | +$399 | +79.80 | 100% |
| ATR-low **and** US session | 14 | −$103 | −7.36 | 29% |
| ATR-low **and** overnight | 46 | −$139 | −3.03 | 37% |

Both ATR-high cells earn; both ATR-low cells bleed regardless of clock. **ATR is the arm condition, the
session is not.**

### The ATR-floor sweep — a plateau in net, a collapse in n

| ATR floor | n | net | $/tr | win% | strip-3 net | strip-3 $/tr | OOS n | OOS net |
|---|---|---|---|---|---|---|---|---|
| none | 74 | +$1,840 | +24.86 | 43.2% | +$634 | +8.94 | 26 | −$139 |
| ≥ 8 | 54 | +$1,842 | +34.10 | 50.0% | +$636 | +12.47 | 11 | −$195 |
| ≥ 10 | 41 | +$1,929 | +47.05 | 51.2% | +$723 | +19.04 | 7 | −$182 |
| ≥ 12 | 26 | +$1,706 | +65.63 | 50.0% | +$501 | +21.78 | 4 | −$181 |
| ≥ 14 | 18 | +$1,840 | +102.22 | 61.1% | +$634 | +42.30 | 1 | −$68 |
| **≥ 15.2** | **15** | **+$2,020** | **+134.64** | **73.3%** | **+$814** | **+67.85** | **1** | **−$68** |
| ≥ 18 | 8 | +$1,916 | +239.44 | 87.5% | +$710 | +142.00 | 0 | $0 |
| ≥ 20 | 6 | +$1,740 | +290.08 | 83.3% | +$535 | +178.33 | 0 | $0 |
| ≥ 22 | 4 | +$1,284 | +320.88 | 100% | +$263 | +263.00 | 0 | $0 |

This needs reading carefully, because it has both a good tell and a bad one. **The good tell:** net stays
flat at roughly $1,700–2,100 the whole way from no floor to ≥20 while n falls from 74 to 6. That is what
a *filter* looks like — it is removing trades that contribute nothing, not cherry-picking winners. If the
floor were fitting noise, net would climb with the floor. It doesn't; only $/trade does, mechanically,
because the denominator is shrinking.

**The bad tell, and it is fatal to deployment:** look at the last two columns. **Above an ATR floor of
14, the out-of-sample week contains one trade. Above 18, it contains none.** The routed policy is not
out-of-sample-negative; it is out-of-sample-*untested*. There is no honest way to call that validated.

### The routed book, every trade, n=14

| day | hr | side | z | ATR | exit | pts | $ |
|---|---|---|---|---|---|---|---|
| 07-07 | 13 | SHORT | 3.6 | 42.5 | TIME | +169.50 | +337.50 |
| 07-09 | 05 | SHORT | 6.9 | 17.1 | TIME | +54.25 | +107.00 |
| 07-14 | 00 | SHORT | 3.6 | 19.2 | TIME | +15.25 | +29.00 |
| 07-17 | 10 | LONG | −3.2 | 17.1 | TIME | +50.75 | +100.00 |
| 07-27 | 13 | SHORT | 3.1 | 42.5 | TIME | +205.75 | +410.00 |
| 07-27 | 19 | LONG | −4.1 | 20.1 | TIME | +0.25 | −1.00 |
| 07-28 | 13 | SHORT | 8.1 | 21.1 | TIME | +229.75 | **+458.00** |
| 07-30 | 09 | LONG | −3.7 | 16.0 | TIME | +9.25 | +17.00 |
| 07-31 | 12 | LONG | −3.2 | 19.5 | TIME | +73.75 | +146.00 |
| 08-03 | 13 | LONG | −4.7 | 55.5 | TIME | +137.25 | +273.00 |
| 08-04 | 18 | LONG | −3.7 | 17.3 | TIME | +39.50 | +77.50 |
| 08-06 | 13 | LONG | −6.3 | 16.1 | STOP | −32.50 | −66.50 |
| 08-07 | 13 | SHORT | 6.1 | 47.9 | TIME | +132.25 | +263.00 |
| **08-10** | **13** | **LONG** | **−4.2** | **16.6** | **STOP** | **−33.39** | **−68.29** |

13 distinct days, 12 winners, 2 losers, both losers stopped and both bounded near −$67. Strip-3 leaves
+$877 over 11 trades ($79.70/tr) — it survives. LOO kills nothing. The home-regime placebo battery is
clean too: sign-flip **−$1,379**, shifts of +60/+120 min both negative, and an **ATR-matched** random
bootstrap over 300 draws (mean −$33, sd $474, max +$1,432) that the real +$2,082 **beats 100% of**.

And then the last row of the table is the whole problem: **the only census-week trade this policy took
was a loser.** Six of those fourteen sit in hour 13, i.e. the cash open — which means the routed
VAC-ABS is substantially a *cash-open* signal, and that is the OPEN-NEWS phase's territory, not VACUUM's.

### The router rule, in the live router's own vocabulary

If it is ever armed, this is the spec — stated so it is testable rather than aspirational:

> **ARM** `vac_abs` when `ATR(1m,14) ≥ 15.0 pt` on MNQ. **BENCH** it below `13.0 pt` (2-point hysteresis,
> matching the existing 2-mark convention, plus a **dwell of ≥ 5 minutes** on the arm side — the churn
> finding from Part 2.5 applies directly here, since ATR crossing a bare threshold on a partial bar is
> exactly the oscillation that produced 20 switch changes for 4 trades on 08-07).
> **No ER condition** — §7 shows ER ≥ 0.35 is the *best* bucket, which is the opposite of the faders'
> usual guard, so an ER floor borrowed from another gate would be wrong here.
> **No session condition** — the ATR-high/overnight cell earns.

**Expectancy on the home regime only: +$134.64/trade over 15 trades. Blanket, for context and not as the
verdict: +$24.86/trade over 74.** Frequency on the home regime: roughly **one trade every two days**.

**What we cannot yet measure:** nothing. That is worth saying plainly — unlike some findings this week,
this gate needs no new instrument. `ATR(1m,14)` is already computed live. The blocker is purely **n**.

---

## 8. ★ THE ESCALATION — full sat-out → top-25 → top-15, and the size-threshold answer

This is where VAC-ABS stops being an answer to the question I was sent to answer.

**Big-moves-caught** — a signal fires within ±15 minutes of the run start, on the run's own side:

| candidate | VACUUM 8 | all sat-out 60 | top-25 sat-out | top-15 sat-out | all 68 runs |
|---|---|---|---|---|---|
| **VAC-ABS** (n=74) | **2/8** | **4/60** | **1/25** | **0/15** | 5/68 |
| **VAC-ABS/HI** (routed, n=14) | 0/8 | 0/60 | 0/25 | **0/15** | 1/68 |

And the four it did catch made $18 between them:

| run | move | cluster | VAC-ABS $ |
|---|---|---|---|
| 08-10 06:13 | −50 | VACUUM | −$25 |
| 08-10 19:44 | −52 | UNCLASS | −$20 |
| 08-11 06:18 | −66 | UNCLASS | −$35 |
| 08-12 00:08 | +44 | VACUUM | +$62 |

**Does the footprint strengthen as the runs get bigger?** No. It gets weaker. Of census-week runs in each
size band, how many had a VAC-ABS trigger pointing the right way in the 15 minutes before:

| move size | runs | pre-run trigger, right way | rate |
|---|---|---|---|
| 44–60 pt | 35 | 2 | 6% |
| 60–80 pt | 18 | 0 | 0% |
| 80–110 pt | 12 | 1 | 8% |
| 110–300 pt | 3 | 0 | 0% |

**★ THE SIZE-THRESHOLD ANSWER: there is no threshold. The footprint does not appear at any size.** The
mandate asks for the size at which a footprint becomes tradeable, and the honest answer for this cluster
in this window is that narrowing from 60 runs to 25 to 15 reveals nothing — it just shrinks n. The
escalation was worth running precisely because it could have gone the other way; it didn't.

### Precursor dissection — the 10 minutes before the top-15 sat-out runs

Since VAC-ABS doesn't show up, I went and looked directly at what *is* there. Two of the 25 had no
usable tape (08-10 00:02, 08-09 23:47 — the Sunday reopen), leaving 23 dissected, 14 in the top-15.

| stat (median) | top-15 | top-25 | all tape |
|---|---|---|---|
| ATR(1m,14) at the run's first minute | 14.50 | 11.14 | 12.52 |
| **ER15 at the run's first minute** | **0.13** | **0.18** | **0.24** |
| max \|flow z\| in the prior 10 min | 2.19 | 2.53 | 0.44 |
| **max \|1-min move\| in the prior 10 min** | **15.38 pt** | **13.75 pt** | **4.50 pt** |

| test | top-15 | top-25 |
|---|---|---|
| pre-run flow **agrees** with the run direction | **6/14** | 9/23 |
| a \|flow z\| ≥ 3 minute in the prior 10 | 4/14 | 8/23 |
| ER15 ≥ 0.35 at the run's first minute | 2/14 | 5/23 |
| ATR ≥ 15.2 at the run's first minute | 6/14 | 6/23 |

Three things fall out of that, and they are more useful than any of the gates I built.

**(a) The flow coin flip reappears, independently.** 6 of 14 — a coin flip, derived on a completely
different sample from §2 by a completely different method. Two independent routes to the same verdict.

**(b) The runs are already moving before the census sees them.** Median biggest 1-minute move in the ten
minutes *before* a top-15 run is **15.4 points, against 4.5 on ordinary tape**. The census's 15-minute
window is not catching an ignition; it is catching the middle of something already underway. This is the
same thing the Part-2.5 detection-latency work found from the other direction (median 119pt already
moved when run-state first fires), and it says that *any* signal keyed to a 15-minute window is
structurally late.

**(c) Big runs start from CHOP, not from trend.** ER15 at the run's first minute is **0.13** for the
top-15 against **0.24** for the tape at large — the runs start from *below-average* efficiency, and only
2 of 14 had ER ≥ 0.35. Every ER-floor arm condition on this desk would have been standing the gate
*down* at the moment the biggest moves began. That deserves testing properly in the router section
rather than being buried here.

---

## 9. ★ EVERY ATTEMPT BY NAME — the survivors and the graves

Nothing here is dropped. Nine candidates, all backtested identically: 1-min triggers, entry on the first
tick after the bar closes, stop 2.0 ATR, 30-minute time exit, **$1.50/RT + 0.25pt slippage each way**,
over the full lake. "placebo" is the +90-minute shift; "flip" is the same bars traded the other way;
"top15" is big-moves-caught against the 15 biggest sat-out runs.

| # | Candidate | What it does | n | net | $/tr | win% | strip-3 | flip | placebo | OOS | top15 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **VAC-Z1** | fade any \|flow-z\| ≥ 1 minute — *the census's own VACUUM trigger, traded literally* | 6,937 | **−$19,054** | −2.75 | 35.6% | −$21,666 | −$27,809 | −$26,564 | −$5,918 | — |
| 2 | **VAC-Z3** | fade \|flow-z\| ≥ 3, no absorption test | 831 | +$357 | +0.43 | 35.4% | **−$1,816** | +$3,448 | −$4,226 | +$976 | — |
| 3 | **VAC-CLIMAX** | fade a buy/sell climax bar (big flow *with* a big same-way move) | 609 | −$1,245 | −2.05 | 36.8% | −$3,336 | +$5,127 | −$1,707 | +$46 | — |
| 4 | **VAC-ABS** | **absorption: \|z\| ≥ 3 and the minute closed within 2.75pt → fade** | **74** | **+$1,843** | **+24.91** | 41.9% | **+$637** | **−$2,388** | **−$817** | −$141 | **0/15** |
| 5 | **VAC-ABSX** | VAC-ABS, but only when the 15-min move was already ≥ 2 ATR extended | 27 | +$984 | +36.44 | 40.7% | **−$222** | −$1,184 | −$188 | −$39 | 0/15 |
| 6 | **VAC-ABSGO** | same trigger, traded *with* the absorbed flow (the continuation reading) | 74 | −$2,388 | −32.27 | 14.9% | −$2,827 | +$1,843 | −$766 | −$402 | 0/15 |
| 7 | **VAC-SWEEP** | stop-run: new 15-min extreme on vol-z ≥ 2 that closes back inside → fade | 478 | +$725 | +1.52 | 35.6% | **−$1,867** | +$918 | **+$540** | +$133 | — |
| 8 | **VAC-QUIET** | *negative control*: absorption-shaped price, ordinary flow (\|z\| < 1) | 10,258 | −$34,736 | −3.39 | 34.0% | −$37,048 | −$39,349 | −$31,048 | −$15,816 | — |
| 9 | **VAC-ABS/HI** | **VAC-ABS armed only on ATR ≥ 15.2pt — the router policy** | **14** | **+$2,080** | **+148.59** | 78.6% | **+$874** | **−$1,379** | **−$94** | 1 / −$68 | **0/15** |
| 10 | **COIL-BREAK** | ER-dead + ATR-compressed coil, then break the 15-min range → go with it | 1,326 | −$6,529 | −4.92 | 33.1% | −$7,818 | −$2,721 | −$4,934 | −$1,839 | 3/15 |
| 11 | **ATR-IGNITION** | 1-min true range ≥ 3× its own ATR → go with the ignition bar | 150 | −$583 | −3.89 | 30.0% | −$1,672 | −$247 | −$818 | −$706 | 4/15 |
| 12 | **ATR-IGNITION/f** | the same bar, faded instead | 150 | −$247 | −1.65 | 32.0% | −$1,260 | −$583 | **+$1,108** | −$124 | 4/15 |
| 13 | **COIL-BREAK/HI** | COIL-BREAK armed only on ATR ≥ 15.2 | 254 | −$1,688 | −6.65 | 40.2% | −$2,596 | −$2,152 | −$619 | +$19 | 1/15 |
| 14 | **ATR-IGNITION/HI** | ATR-IGNITION armed only on ATR ≥ 15.2 | 59 | +$842 | +14.27 | 39.0% | **−$247** | **+$340** | −$908 | −$313 | 3/15 |

### Cause of death, one line each

| Candidate | Disposition | Cause of death / condition |
|---|---|---|
| **VAC-Z1** | **REFUTED** | The label test in §2 — 51.3% vs a 51.2% base rate, ±1.15pp. It is not a thin-n failure, it is a measured absence of information, and traded literally it loses **−$19,054**. No reformulation of "fade a flow event" saves it because the flow event carries no direction. |
| **VAC-Z3** | **PARKED** | **Strip-3 turns it negative (+$357 → −$1,816)** — three trades were the entire book. *Revive if:* the absorption leg is what matters (it is — see #4), so this is really superseded rather than promising. |
| **VAC-CLIMAX** | **REFUTED** | Negative outright (−$1,245) **and the sign-flip earns +$5,127** — the mechanism runs the other way. Big flow that *does* move price continues; it does not exhaust. That is a real finding, it just isn't a fade. |
| **VAC-ABS** | ★ **SHADOW** | Survives placebo, sign-flip, bootstrap, plateau, LOO and 3× cost stress. **Killed as a deployment candidate by strip-5 (+$98) / strip-10 (−$534) and a negative OOS leg (−$139, n=26).** Not REFUTED — thin n never is. Needs n. |
| **VAC-ABSX** | **PARKED** | **Strip-3 negative (+$984 → −$222).** The extension filter costs 47 of 74 trades to buy $12/trade, and what is left is three trades wide. *Revive if:* n reaches ~60 on the extension-filtered leg. |
| **VAC-ABSGO** | **REFUTED** | It is #4 inverted, and it loses −$2,388 at a 14.9% win rate. Included because it is the honest control: it proves the direction of #4 is the finding. |
| **VAC-SWEEP** | **PARKED** | **Placebo test: the +90-min shifted fake books +$540 while the real signal books +$725** — a fake captures three quarters of it. Strip-3 is also negative. *Revive if:* the sweep is re-specified against L2 (a sweep that clears the far side of the book is a different object from one defined on 1-min extremes) once MNQ book coverage passes ~30 days. |
| **VAC-QUIET** | **negative control, working as intended** | Loses in both directions (−$34,736 fade, −$39,349 with). Its job is to show that absorption-shaped *price* with ordinary flow is pure cost bleed, which means the flow leg of #4 is load-bearing. |
| **VAC-ABS/HI** | ★ **SHADOW** | The strongest thing in the section by every in-sample measure — and **untestable out of sample: the held-out week contains one trade.** Cannot be promoted on 14 trades over 13 days, 6 of them at the cash open. |
| **COIL-BREAK** | **REFUTED** | −$6,529 on n=1,326. Both directions lose (flip −$2,721), so it is not a sign error; range breaks out of compression on MNQ do not pay after costs at this horizon. |
| **ATR-IGNITION** | **PARKED** | Negative both ways (−$583 with, −$247 faded). *Revive if:* the direction is resolved by a second variable — it catches **4/15** of the biggest runs, the best hit rate anything here achieved, so the *detection* half works and only the *direction* half fails. That is the most promising unfinished thread in this section. |
| **ATR-IGNITION/f** | **PARKED** | Same object; the **placebo books +$1,108 against the real signal's −$247**, i.e. a fake beats it outright. |
| **COIL-BREAK/HI** | **REFUTED** | −$1,688 even on its best regime; flip also negative. |
| **ATR-IGNITION/HI** | **PARKED** | Only positive-looking one of the escalation set (+$842) but **strip-3 kills it (−$247)** *and* **the sign-flip is also positive (+$340)** — when both directions win, you have found volatility, not an edge. *Revive if:* a directional discriminator is found (see ATR-IGNITION). |

---

## 10. Run charts

Written to `gf_vac_charts.svg.html` — three inline SVGs built from the real tick tape with the real fills
marked, no external image, no CDN, no JS:

1. **2026-08-13, the +236pt monster** — the census week's biggest sat-out run. Nothing fired anywhere in
   the window. This is the honest picture of the miss.
2. **2026-07-28, VAC-ABS's best trade** — SHORT, +229.75pt, **+$458.00**, exited on the 30-minute clock,
   with entry and exit marked on the path.
3. **2026-08-10, VAC-ABS's out-of-sample loser** — LONG, −33.39pt, **−$68.29**, stopped out. The only
   trade the routed policy took in the census week, and it lost.

---

## 11. What I would tell Garrath over a coffee

The thing I was asked to hunt isn't there, and I can prove it rather than just assert it. VACUUM isn't a
family of runs with a shared cause — it's the name we put on a perfectly ordinary minute after the fact.
One minute in five on this tape has a "big flow" event, and once one has, which way price goes next is
51.3% one way and 48.7% the other, which is the same as on the minutes where nothing happened at all.
Eight runs got the label this week; chance alone predicts about eight. **Nobody should ever arm a gate
on this cluster, and if a future report opens with "the VACUUM cluster suggests", that report is wrong.**

While I was in there I did find something real, and I want to be careful about how I sell it, because it
is not what we were looking for. If somebody dumps a huge amount of aggressive buying into the tape in
sixty seconds and **price doesn't move**, that buyer is trapped, and fading them pays: **+$1,843 over 74
trades, +$24.91 each, net of the true $1.50 fee.** The mechanism checks out about as well as a mechanism
can — trade it the other way and it loses $2,388; shift the signal an hour and it loses; it beats 98.5%
of random fakes; no single day carries it; it survives a fee three times too high. And it lives almost
entirely in one regime: when 1-minute ATR is above about 15 points it made **$148 a trade at a 79% win
rate**, and below that it is flat-to-slightly-negative. That's a clean router story — arm on ATR ≥ 15,
bench below 13, five-minute dwell — and unusually for this week, it needs **no new instrument**; we
already compute that ATR live.

But two things stop me short of recommending it, and I'd rather say them now than have the skeptic say
them later. **Five trades are the entire book** — strip them and $1,840 becomes $98, strip ten and it's
−$534. And **the held-out week lost money**: 26 trades, −$139. When I tighten to the ATR-high regime that
looks so good, the held-out week contains exactly **one** trade, and it was a loser. So the honest
sentence is: the mechanism is real, the sample is not yet a sample, and I have never once seen it work
on a week I didn't fit it on.

The last thing is the one I'd actually act on this week, and it came out of the escalation rather than
any of the gates. I went and dissected the ten minutes before each of the fifteen biggest runs we sat
out, and two numbers there matter more than anything else in this section. **The biggest single-minute
move in the ten minutes before a top-15 run is 15.4 points, against 4.5 on ordinary tape** — by the time
the census calls it a run, it has been running for a while, which is the same latency problem Part 2.5
measured from the other end. And **those runs start from chop, not from trend**: efficiency at the run's
first minute is 0.13 against a tape median of 0.24, and only 2 of 14 were above 0.35. Every ER-floor arm
condition we own would have been standing gates *down* at the exact moment the week's biggest moves
began. I can't fix that from this section, but somebody should look at it hard.

**Stone still unturned:** `ATR-IGNITION` caught **4 of the 15** biggest sat-out runs — the best detection
rate anything in this hunt achieved — but loses money in **both** directions, which means the detection
half works and only the direction half is missing. Find the variable that tells you which way an ignition
bar resolves and there is a run-catcher there. My first candidate would be the L2 book at the moment of
ignition (far-side depletion in `depth.db`), which I deliberately left out of every backtest above
because MNQ book coverage is only 15 days and I would have halved my sample to buy one filter. Come back
to it when book coverage passes 30 days.

---

## 12. DISPOSITION TABLE

| Lead | Verdict | Named test / revival condition |
|---|---|---|
| **The VACUUM cluster label itself** | **REFUTED** | Base-rate test on 34,724 minutes of lake tape: fires on 10.6% of all tape; 51.3% disagreement vs a 51.2% non-event base rate, ±1.15pp. Independently reconfirmed on the top-15 precursor dissection (flow agrees with the run 6/14). No reformulation saves it — the label is defined using the forward move, so it can never be a trigger. |
| **VAC-ABS** (absorption fade) | ★ **SHADOW** | Mechanism confirmed (sign-flip −$2,388, bootstrap p≈0.015, plateau across 20/20 stop×hold cells, LOO clean, survives $5/RT). Blocked from LIVE by **strip-5 → +$98** and a **negative OOS leg (−$139, n=26)**. Shadow it two-sided to accumulate n. **Do not present it as a run-catcher: 0/15 on the top-15.** |
| **VAC-ABS/HI** (ATR ≥ 15.2 router policy) | ★ **SHADOW** | Best in-sample object in the section (+$148.59/tr, 15 trades, strip-3 +$814, ATR-matched bootstrap beats 100/100). **Revive to LIVE if n ≥ 40 with a positive forward leg** — today the out-of-sample week holds one trade, so it is untested, not validated. |
| **VAC-Z1** | **REFUTED** | The label test above; −$19,054 traded literally. |
| **VAC-Z3** | **PARKED** | Strip-3 (+$357 → −$1,816). Superseded by VAC-ABS. |
| **VAC-CLIMAX** | **REFUTED** | Loses −$1,245 while its sign-flip earns +$5,127 — the mechanism is continuation, not exhaustion. |
| **VAC-ABSX** | **PARKED** | Strip-3 (+$984 → −$222). Revive if the extension-filtered leg reaches n ≈ 60. |
| **VAC-ABSGO** | **REFUTED** | −$2,388 at 14.9% win — the deliberate inverse control. |
| **VAC-SWEEP** | **PARKED** | Placebo: a +90-min fake books +$540 of the real +$725. Revive re-specified against L2 once MNQ book coverage ≥ 30 days. |
| **VAC-QUIET** | **control** | Working as intended — loses both ways, proving the flow leg of VAC-ABS is load-bearing. |
| **COIL-BREAK** | **REFUTED** | −$6,529 on n=1,326, both directions negative. |
| **COIL-BREAK/HI** | **REFUTED** | −$1,688 on its own best regime, flip also negative. |
| **ATR-IGNITION** | **PARKED** ★ | Loses both ways, **but catches 4/15 of the biggest sat-out runs**. Revive with a directional discriminator — first candidate is L2 far-side depletion at the ignition bar (`depth.db`), once MNQ book coverage ≥ 30 days. **This is the one stone still unturned.** |
| **ATR-IGNITION/f** | **PARKED** | Placebo beats it (+$1,108 vs −$247). Same revival condition. |
| **ATR-IGNITION/HI** | **PARKED** | Strip-3 → −$247 **and** sign-flip also positive (+$340): both directions win = volatility, not edge. Same revival condition. |
| **"Big runs start from chop, not trend"** (ER 0.13 vs 0.24 tape median; 2/14 above 0.35) | **finding — hand to the router section** | Not a gate. It says every ER-floor arm condition we own is standing gates down at the moment the biggest moves start. Needs testing against the live router's arm logic, not here. |

**No LIVE candidate. Two SHADOW candidates (VAC-ABS, VAC-ABS/HI), both explicitly not run-catchers.**

---

## VERDICT

**The VACUUM cluster did NOT survive, and it was killed by the LABEL BASE-RATE TEST, not by a backtest:**
the census's VACUUM condition fires on **10.6% of every minute of tape we own** and its direction test
comes up VACUUM **51.3%** of the time against a **51.2%** base rate on non-event minutes — a 0.1pp
difference inside a ±1.15pp error bar — so the cluster carries no information and the 8 runs it labelled
this week are exactly the number chance predicts. Traded literally (**VAC-Z1**) it loses **−$19,054** over
6,937 trades. **The one signal invented here that does survive its robustness battery — VAC-ABS,
+$1,843 / 74 trades / +$24.91 per trade net of $1.50 per round trip, mechanism confirmed by a −$2,388
sign-flip, a decaying placebo curve and a bootstrap it beats 98.5% of — is nonetheless NOT an answer to
this section's question: it scores 0/15 against the biggest sat-out runs, its out-of-sample leg is
−$139, and strip-5 reduces it to +$98. It is dispositioned SHADOW, not LIVE. There is NO size-threshold
at which a footprint becomes tradeable: 6% / 0% / 8% / 0% across the 44-60, 60-80, 80-110 and 110-300pt
bands — narrowing to the top-25 and top-15 revealed nothing and only shrank n.** The one stone still
unturned is **ATR-IGNITION**, which detects 4 of the 15 biggest runs but cannot tell which way they
resolve — revive it with an L2 far-side-depletion discriminator once MNQ book coverage passes 30 days.
