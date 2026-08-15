# GREENFIELD HUNT — CLUSTER `UNCLASS`

*Movement 3. MNQ. Tick-honest over the full Parquet lake, 2026-06-19 → 2026-08-15 (49 sessions).*
*$2.00/point · $1.50 per ROUND TRIP · one tick crossed each side. All-in $2.50 a trade.*

---

## THE SHORT VERSION, BEFORE ANY OF THE WORKING

Garrath — you told this phase that "we could not classify it" is a banned verdict, that the order of
work is **ride → filter → router**, and that classification is not a prerequisite for riding. I did it
in that order and I am not going to hide behind the label. Here is what came back.

**1. The label is the biggest finding, and it is worse than useless.** `UNCLASS` is true on **74.9%
of every minute of the tape**. It is not a market state; it is the leftover branch of a four-step
waterfall. And its share of the sat-out runs (34 of 60, 57%) is *below* its base rate on ordinary
tape. Knowing a run was UNCLASS tells you **less than nothing** — of the four labels it is the only
one that is *anti*-enriched among the runs. OPEN/NEWS, by contrast, is 3.0× enriched: that one is a
real footprint. So the reason the census could not name these runs is not that they are mysterious.
It is that the classifier only has three tests, all three are narrow, and everything else falls in
the bin.

**2. The runs ARE boardable — that half is solved.** A dumb direction-agnostic thrust detector
("the last 10 minutes covered ≥ 2×ATR in one direction") fires inside **34 of 34** sat-out UNCLASS
runs, at a median **7.5 minutes in**, with a median **2.19 ATR still ahead** to the run's end and a
median **4.33 ATR** of favourable excursion in the following hour. Exactly the gold result, on MNQ.
Boarding was never the problem.

**3. A rider was built, filtered, routed — and it survives, but only in the Asia session.** The
survivor is **UNCL-RIDER-ASIA**: thrust board, 00:00–06:00 UTC, absolute ATR floor 8pt, ATR
percentile ≤ 0.60, wide 2.5×ATR stop, far 6×ATR target, 2-hour cap. **157 trades, +$5,006, $31.88 a
trade, 46.5% wins, PF 1.87.** It beat every named test: placebo, shuffled direction, shifted signal,
strip-3, leave-one-day-out, long/short symmetry, cost stress ×3, and a 21-of-25 entry plateau.

**4. And it does not take the UNCLASS money.** That is the sting. Only 5 of the 34 runs live in Asia.
Across all hours the rider boards **9 of 34 runs for −$162**. The bucket's money is in Europe
(11 runs, $1,323) and the US afternoon (14 runs, $1,713) — and there I tested **about eighty**
entry × exit × filter configurations, swept stops to 6×ATR, targets to 12×ATR, caps to six hours,
chandeliers, break-even, pullback boards, short-only. **Every single one is red or flat.** Best of
eighty: +$0.65 a trade, which dies on strip-3.

**5. The $4,097 ceiling is largely a hindsight fiction.** With a *perfect* filter — board only the
34 runs, nothing else, and pick the best exit in hindsight — the best cell banks **$1,054, 25.7% of
the ceiling.** Not because the exit is wrong; because a run boarded 7.5 minutes late with an honest
stop simply does not pay what its 15-minute close-to-close headline says. So the prize you are
chasing in this bucket is roughly a thousand dollars a week gross under hindsight-perfect selection,
not four thousand.

**6. And the survivor is decaying.** First five weeks: +$5,114 on 110 trades ($46.49/tr). Last three
weeks — the true forward out-of-sample: **−$109 on 47 trades.** That is the named test that stops
this from being a Monday deploy.

Bottom line: the ride works, the filter works, the router rule is written, and the thing still
cannot be shipped — killed on the **forward out-of-sample leg** — and even if it were green it would
not be an answer to UNCLASS, because UNCLASS is not a thing.

---

## ★ STEP 0 — INTERROGATE THE LABEL. This outranks anything built on top of it.

Your standing rule: check the cluster's base rate on all bars first. I did, and it changes the whole
question.

`run_census.cluster()` is a four-branch waterfall, and UNCLASS is the *else*:

```
13 ≤ hour < 15                          → OPEN/NEWS
|flow z| ≥ 1.0  (needs ≥30 tick buckets) → FLOW-LED (sign agrees) / VACUUM (sign disagrees)
amp > 0.30 %                            → VOL-EXPANSION
otherwise                               → UNCLASS
```

I re-implemented that waterfall vectorised and evaluated it on **every one of the 6,820 minutes** of
the census's own 7-day window, not just the 68 run minutes.

### Base rate of every label, on all bars

| label | minutes | % of ALL tape | share of the 60 sat-out runs | **lift** |
|---|---:|---:|---:|---:|
| **UNCLASS** | 5,109 | **74.9%** | 34 / 60 = 56.7% | **0.76 ←** |
| OPEN/NEWS | 600 | 8.8% | 16 / 60 = 26.7% | **3.03** |
| VACUUM | 532 | 7.8% | 8 / 60 = 13.3% | 1.71 |
| FLOW-LED | 577 | 8.5% | 2 / 60 = 3.3% | 0.39 |
| VOL-EXPANSION | 2 | 0.03% | 0 | — |

**UNCLASS is true on three quarters of the tape and is UNDER-represented among the runs.** A label
with a lift below 1.0 is not a footprint — it is the null hypothesis wearing a name tag. The census
line "UNCLASS 36 runs" reads like a discovery and is arithmetically closer to "36 runs happened at
some point during the 75% of the week we have no test for."

Two supporting facts:

- **VOL-EXPANSION is dead code.** `amp > 0.30%` fired on **2 minutes out of 6,820**. On MNQ near
  23,000 that threshold demands a ~69pt range in five minutes. That branch has never classified a
  run and never will at its current setting. It should be recalibrated to a percentile or deleted.
- **The label is unstable to an implementation detail.** My reimplementation reproduces the census on
  **59 of 68 runs (87%)**. All nine disagreements sit in the |z| = 0.39–1.83 band, and the only
  difference between the two implementations is *bucket phase* — the census aligns its 60-second flow
  buckets to each run's own timestamp, I align to the wall clock. Six of the nine are runs the census
  called UNCLASS that a one-minute shift calls FLOW-LED or VACUUM. **13% of the census's cluster
  assignments are decided by an arbitrary choice of where a minute starts.**

### What UNCLASS actually means, minute by minute

| reason a minute lands in UNCLASS | share |
|---|---:|
| flow verdict available, but ordinary flow (\|z\| < 1) | 97.1% |
| flow verdict **unavailable** (fewer than 30 tick buckets in the trailing 2h) | 2.9% |

I expected the missing-data path to be a large contaminant and it is not — 2.9% of minutes, and
4 of the 34 sat-out runs. Worth stating because it was a live hypothesis and the data refused it.

**Deliverable for next week's census:** UNCLASS should not be a cluster. Rename it `UNTESTED` and
report it as coverage — "our classifier has no test that fires here" — rather than as a finding. And
because the waterfall's first branch is the clock, UNCLASS is *by construction* everything outside
13:00–15:00 UTC. That single definitional fact drives the rest of this section.

---

## STEP 1 — RIDE FIRST. Cluster the members, but never gate the ride on it.

You said clustering is a filter tool, not a precondition. So it runs here, first, only because it is
cheap — and its output is used in Step 2 and nowhere else.

### The 34 sat-out UNCLASS runs — $4,097, 51% of the week's $8,025 ceiling

| by hour (UTC) | runs | ceiling | median move |
|---|---:|---:|---:|
| ASIA 00–06 | 5 | $611 | 59 pt |
| EUROPE 06–13 | 11 | $1,323 | 64 pt |
| US-PM 15–20 | 14 | $1,713 | 57 pt |
| LATE 20–24 | 4 | $450 | 59 pt |

| direction | | ATR regime at the start | | preceded by |  |
|---|---:|---|---:|---|---:|
| DOWN | 22 | normal-chop | 17 | REVERSAL of the prior 30m | 16 |
| UP | 12 | in-between-building | 6 | CONTINUATION of it | 14 |
| | | violent-whipsaw | 6 | flat | 4 |
| | | clean-trend | 2 | | |
| | | dead-chop | 2 | | |

**It is genuinely heterogeneous.** No hour holds more than 41%, no regime more than 50%, and
continuation and reversal split almost exactly down the middle (14/16). Per your own instruction that
is an argument *for* a direction-agnostic rider and *against* a shape-specific gate — and it is why I
did not spend the phase trying to name sub-shapes that the data does not support. The one honest
sub-split available is the clock, and I use it as the router axis below.

### ★ The structural fact that defines this phase

**20 of the 34 runs — $2,384 of the $4,097 — fall OUTSIDE 13:00–20:00 UTC**, which is the pooled
`RIDER_ALL` phase's home window and its single strongest filter. The pooled rider benches two thirds
of this bucket *by construction*. That is not a criticism of it; it is the reason this phase had
somewhere useful to go. My hunt is therefore the off-hours tape: Asia, Europe, and the late session.

### Boarding — the half that is already solved

For each run, walk forward from its start; the first minute the detector "last *w* minutes covered
≥ *k*×ATR net in one direction" fires is the board; fill at the next minute's open.

| w | k | boarded | median min in | % of move left | ATR left | best ATR in next 60m | % positive |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 1.0 | **34/34** | 3.0 | 62.7% | 3.64 | 5.85 | 97% |
| 5 | 1.5 | 34/34 | 5.0 | 50.1% | 2.95 | 5.30 | 94% |
| **10** | **2.0** | **34/34** | **7.5** | **40.4%** | **2.19** | **4.33** | **94%** |
| 10 | 2.5 | 30/34 | 8.0 | 37.4% | 2.01 | 4.21 | 90% |
| 15 | 2.0 | 34/34 | 6.5 | 40.5% | 2.00 | 4.17 | 91% |
| 15 | 2.5 | 34/34 | 8.0 | 29.7% | 1.43 | 3.73 | 85% |

**STEP 1 VERDICT: PASSED, unambiguously.** Every single run is boardable, late and deliberately,
with multiple ATRs still on the table. Nothing about UNCLASS makes these runs harder to get on than
the gold runs were. Whatever kills this study, it is not the boarding.

---

## STEP 2 — THE EXIT, SWEPT WIDE BEFORE ANY VERDICT ON THE ENTRY

Entry fixed at w=10, k=2.0 on the UNCLASS-eligible tape (every hour except 13:00–15:00). 120-minute
cap. Net $ (n trades). Segmented — never one blanket config across the tape.

### ASIA 00:00–06:00 — the only shelf on the whole eligible tape

| stop ↓ / target → | 2R | 3R | 4R | 5R | 6R | 8R | 10R | none |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.5 | −370 | 811 | 906 | 1,716 | **2,167** | 1,794 | 596 | 1,369 |
| 2.0 | −620 | −571 | 539 | 2,094 | **2,380** | 238 | 349 | 55 |
| **2.5** | 945 | 1,659 | 1,008 | 2,626 | **4,482** | 1,869 | 1,221 | 1,680 |
| 3.0 | −886 | 283 | −1,079 | 1,168 | **2,372** | 1,270 | 729 | 727 |
| 3.5 | −833 | 847 | −2,372 | 405 | **2,178** | −603 | −1,666 | −1,131 |
| 4.0 | −17 | 138 | −1,832 | −627 | **1,664** | 65 | −730 | −882 |

The 6R column is positive at **every one of six stop widths**. That is a plateau along the axis that
matters, not a lucky square — and it is your wide-stop/far-target finding reproduced a fourth time
this week. Best cell 2.5/6R: **+$4,482 on 243 trades, $18.45/tr, 39.5% wins, PF 1.48.**

### Everywhere else — the graves

| segment | fires | best cell in the whole grid | verdict |
|---|---:|---|---|
| EUROPE 06–13 | 5,435 | 2.5/10R **+$1,005** ($3.79/tr, PF 1.09) — 43 of 48 cells red | **grave** |
| US-PM 15–20 | 3,219 | 2.5/3R **+$2,248** ($8.14/tr) — 36 of 48 cells red, no plateau | **grave** |
| LATE 20–24 | 1,693 | 4.0/3R +$686 ($5.49/tr) — sign-flips cell to cell | **grave** |
| ALL-ELIGIBLE (blanket) | 14,972 | 2.5/3R +$307 ($0.26/tr) | **zero** |

The blanket number is exactly the bug the discipline warns about: spraying one config across all
tape averages Asia's +$18.45 against Europe's losses and reports "no edge." Per-segment is the only
honest read.

---

## STEP 2b — THE ENTRY THRESHOLD IS A GUESS TOO. Swept.

Home segment, exit fixed at 2.5/6R/120min. Net $ (n).

| w \\ k | 1.0 | 1.5 | 2.0 | 2.5 | 3.0 |
|---|---:|---:|---:|---:|---:|
| 5 | 139 (283) | 1,194 (262) | −266 (251) | −435 (199) | −355 (146) |
| **10** | 710 (292) | 2,096 (274) | **4,482 (243)** | −106 (238) | 265 (216) |
| 15 | 973 (298) | 713 (288) | 1,883 (270) | 1,794 (254) | 120 (238) |
| 20 | 1,453 (292) | 564 (296) | 2,902 (264) | 707 (272) | 2,809 (238) |
| 30 | 1,919 (284) | 1,144 (292) | 1,774 (280) | 2,418 (263) | 3,156 (251) |

**21 of 25 cells positive.** The chosen cell is the best one, which always deserves suspicion — but
the surface around it is green in every direction and the four reds are scattered, not a boundary.
This is a plateau, not a spike.

---

## STEP 3 — THEN FILTER, WITH A PLACEBO ON EVERY SINGLE CUT

Every cut is scored against a control that discards the **same number of fires at random**, 200
repetitions. A filter that only trades less is not a filter.

| causal cut | n | net | $/tr | placebo mean | placebo p95 | verdict |
|---|---:|---:|---:|---:|---:|---|
| `atr_pr ≤ 0.60` — do not chase an already-hot tape | 200 | $4,209 | **$21.04** | $11.10 | $17.46 | **BEATS** |
| `00:00–03:00` only | 134 | $2,900 | **$21.64** | $7.39 | $15.16 | **BEATS** |
| `atr ≥ 10pt` absolute floor | 189 | $3,914 | **$20.71** | $11.96 | $18.65 | **BEATS** |
| `atr ≥ 8pt` absolute floor | 218 | $4,260 | **$19.54** | $14.46 | $19.18 | **BEATS** |
| `atr_pr ≥ 0.40` | 184 | $3,548 | **$19.28** | $9.14 | $16.87 | **BEATS** |
| SHORT only | 202 | $2,998 | $14.84 | $8.20 | $16.63 | fails |
| Mon–Thu | 194 | $2,824 | $14.56 | $13.87 | $19.47 | fails |
| `er15 ≥ 0.15` (move is efficient) | 221 | $2,364 | $10.69 | $11.08 | $17.27 | fails |
| `atr_pr ≥ 0.60` | 123 | $856 | $6.96 | $4.01 | $12.70 | fails |
| `er15 ≤ 0.15` | 230 | $1,535 | $6.67 | $4.87 | $13.36 | fails |
| `03:00–06:00` only | 145 | $676 | $4.66 | $7.49 | $15.80 | fails |
| `rvol ≥ 1.3` | 238 | $240 | $1.01 | $4.58 | $13.19 | fails |
| `rvol ≥ 1.0` | 253 | $96 | $0.38 | $8.71 | $15.56 | fails |
| flow agrees with the thrust | 147 | −$91 | −$0.62 | $6.30 | $13.33 | fails |
| LONG only | 207 | −$1,054 | −$5.09 | $7.34 | $14.84 | fails |

Two results worth calling out because they are counter-intuitive and both survived their control:

- **`atr_pr ≤ 0.60` — a CEILING, not a floor.** The pooled rider uses `atr_pr ≥ 0.40` as an arming
  condition. On Asia the *cap* pays more than the floor. Boarding a thrust when volatility is already
  in the top 40% of its own six hours means boarding an extended move. This is the only place in the
  week's work where a volatility *ceiling* beat a volatility floor, and I would not have guessed it.
- **`rvol` is worthless here and flow is worse than worthless.** Volume-confirmation is the standard
  continuation filter and it fails its placebo outright ($0.38/tr). Requiring aggressor flow to agree
  with the thrust turns +$18.45 into −$0.62. Overnight, the tape that trades *with* the move is the
  tape that is finishing it.

---

## STEP 4 — THE BATTERY. Everything that was allowed to kill it.

On the raw, unfiltered Asia rider (n=243, +$4,482, $18.45/tr):

| test | result | pass? |
|---|---|---|
| **Placebo** — random Asia minutes, random side, same n, 200 reps | mean −$1.11/tr, p95 $14.48 vs actual **$18.45** | ✅ |
| **Shuffled-direction null** — same timestamps, alternating side | **−$11.91/tr**, PF 0.76 | ✅ the sign carries the information |
| **Shifted +30min** — fake signal, every other rule kept | $5.22/tr (28% of the real) | ✅ |
| **Strip 3 best trades** | $4,482 → **$3,681** | ✅ |
| **Strip 5 best trades** | → **$3,162** | ✅ |
| **Leave-one-day-out**, worst | **+$3,844** (dropping 2026-06-26) | ✅ |
| **Long / short symmetry** | LONG +$10.40/tr · SHORT +$25.80/tr — both green | ✅ |
| **Cost stress ×2 / ×3 round trip** | +$15.95/tr · **+$13.45/tr** | ✅ |
| **Per-ISO-week** | 7 green of 8, worst −$26 | ⚠ but see decay |

**Per-regime, home segment only** (the policy view, never a blanket):

| regime | n | net | win% | $/trade | PF |
|---|---:|---:|---:|---:|---:|
| normal-chop | 81 | $2,700 | 44.4 | **$33.33** | 1.97 |
| in-between-building | 84 | $1,784 | 41.7 | **$21.24** | 1.55 |
| dead-chop | 20 | $172 | 35.0 | $8.61 | 1.31 |
| violent-whipsaw | 31 | −$58 | 29.0 | −$1.88 | 0.96 |
| clean-trend | 27 | −$115 | 33.3 | −$4.27 | 0.91 |

Note the shape: the **raw** rider wants chop with structure, not a clean trend. By the time the desk's
ER vocabulary calls Asia "clean-trend", the move looks finished and the late board is buying the top.

⚠ **But this table does not survive the filters, and the router rule below follows the filtered one.**
Once `atr_pr ≤ 0.60` is applied the picture inverts, and I nearly shipped the wrong arming condition
off the raw table:

| regime (SHIPPING config) | n | net | win% | $/trade | PF |
|---|---:|---:|---:|---:|---:|
| clean-trend | 22 | $1,147 | 54.5 | **$52.15** | 2.62 |
| normal-chop | 76 | $3,033 | 50.0 | **$39.91** | 2.22 |
| in-between-building | 48 | $1,062 | 41.7 | $22.13 | 1.52 |
| dead-chop | 11 | −$238 | 27.3 | −$21.59 | 0.53 |
| violent-whipsaw | 0 | — | — | — | eliminated by the `atr_pr` ceiling |

The `atr_pr ≤ 0.60` ceiling is doing the work a regime filter would otherwise be asked to do: it
removes violent-whipsaw entirely, and what remains inside "clean-trend" is the *early* part of a
trend rather than the extended part. Benching clean-trend on the strength of the raw table would have
benched the best bucket in the strategy.

Dead-chop is the only red row, so I tested benching it and **rejected the cut**: n=159, +$4,663,
$29.33/tr — **$343 worse** than leaving it in. Removing those 11 signals frees the
one-position-at-a-time book to take other, worse trades in their place. It is a useful reminder that
a per-bucket table cannot be read as if each row were separable: in a single-position book, cutting a
losing bucket is not the same as adding its losses back. **The shipped rule therefore carries no
regime filter at all** — two volatility conditions and a clock, nothing else.

---

## STEP 5 — THE SHIPPING CANDIDATE, AND THE OPERATIONAL CATCH THAT PAID FOR ITSELF

**UNCL-RIDER-ASIA** = thrust board (w=10, k=2.0) · 00:00–06:00 UTC · `atr ≥ 8pt` · `atr_pr ≤ 0.60` ·
stop 2.5×ATR · target 6×ATR · 2-hour cap · **minus 04:15–05:15 UTC**.

That last exclusion is not a tuning knob. The desk has a **daily 04:30–05:00Z IB gateway outage** —
the reset hangs the audit loop and systemd SIGABRTs the tournament, and the clock is drifting later
(08-15 hit 04:57). Eleven backtest trades opened inside that window and the live desk could not have
taken any of them. Removing them **improves** the result, which is the rare case where an operational
constraint is free money.

| | n | net | win% | $/trade | PF |
|---|---:|---:|---:|---:|---:|
| Asia raw | 243 | $4,482 | 39.5 | $18.45 | 1.48 |
| + `atr ≥ 8pt` | 218 | $4,260 | 39.9 | $19.54 | 1.48 |
| + `atr ≥ 8pt` + `atr_pr ≤ 0.60` | 166 | $4,594 | 44.6 | $27.67 | 1.74 |
| **+ minus the gateway outage → SHIPPING** | **157** | **$5,006** | **46.5** | **$31.88** | **1.87** |

Full battery on the shipping config: **strip-3 +$4,219 · strip-5 +$3,776 · leave-one-day-out worst
+$4,438 · 29 of 38 sessions green · LONG +$19.33/tr, SHORT +$43.66/tr (both green) · cost ×3
+$4,221 ($26.88/tr) · placebo p95 $14.69 vs actual $31.88.** Exit mix: 63 targets (+$10,035), 13 time
caps (+$586), 81 stops (−$5,614) — a textbook wide-stop/far-target distribution where the winners are
big and the win rate is beside the point, exactly as your judging rule anticipates.

### ⚠ And the reason it is not a deploy

| ISO week | W26 | W27 | W28 | W29 | W30 | W31 | W32 | W33 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| net | +1,325 | +859 | +1,241 | +999 | +690 | **−170** | **−13** | +75 |

**First five weeks +$5,114 on 110 trades ($46.49/tr). Last three weeks −$109 on 47 trades
(−$2.31/tr).** Chronologically the last three weeks are the only true forward out-of-sample this
tape can offer, and the strategy is flat-to-red across all of it.

I tested the obvious excuse and it does not hold. Correlation between a week's $/trade and that
week's median Asia ATR is **+0.57** — so quiet tape explains *some* of it, and the absolute ATR floor
(`atr ≥ 8pt`) was added precisely to address it. **The floor did not restore W31 or W32.** The
volatility-drought hypothesis is a partial explanation, not an exoneration.

> Note on how the OOS leg is oriented. The pooled study calls the V5 archive leg (June–early July) its
> out-of-sample and reports it green. On my candidate that leg is +$31.13/tr while the recent tape is
> +$8.12/tr — i.e. the "OOS" is the *strong* half. That is backwards for a forward test. An earlier
> period cannot validate a strategy fitted afterwards. Judged the only way that means anything —
> walking forward — this rider is in a three-week drawdown of its edge.

---

## STEP 6 — THE RESCUE. Eighty attempts on the half of the bucket that holds the money.

$3,036 of the $4,097 and 25 of the 34 runs sit in Europe and the US afternoon, where the Asia-shaped
rider is a proven grave. Declaring victory on the Asia shelf while the bucket's own money sits
untouched is exactly the move you banned. So:

### R1 — wider still (stops to 6×ATR, targets to 12×ATR, caps to 6 hours)

Sixty cells per segment. **EUROPE: every one of 60 cells negative**, best −$5. **US-PM: every one of
60 cells negative**, best −$841. Going wider does not help; past 4×ATR it actively hurts (Europe
6.0-stop cells run −$1,751 to −$6,297). The wide-exit finding is real in Asia and does not generalise.

### R2 — managed exits

| attempt | EUROPE | US-PM |
|---|---:|---:|
| 3.0 stop / 6R (reference) | −$1,605 (302) | −$1,613 (185) |
| chandelier arm 2.0 trail 1.5, no target | −$1,795 (446) | −$374 (270) |
| chandelier arm 3.0 trail 2.0, no target | −$2,998 (373) | −$324 (209) |
| chandelier arm 4.0 trail 2.0, no target | −$2,969 (323) | −$2,973 (177) |
| break-even at 1.0R + 3.0/6R | −$2,258 (477) | −$1,762 (289) |
| break-even at 2.0R + 3.0/6R | −$531 (370) | −$3,751 (236) |
| no target, 240min time-only, 3.0 stop | −$3,735 (192) | −$1,143 (127) |

The chandeliers post 50–60% win rates and still lose money — the classic give-back signature, and a
neat illustration of why win% is not the criterion.

### R3 — direction (the bucket is 65% DOWN)

EUROPE short-only −$3.60/tr, long-only −$6.38/tr. US-PM short-only −$4.69/tr, long-only −$3.48/tr.
The directional skew of the *runs* does not transfer to the *rule*. Both sides lose.

### R4 — a different entry

| attempt | EUROPE | US-PM |
|---|---:|---:|
| slower thrust w=20 k=2.5 | −$2,053 (308) | −$2,033 (177) |
| slower thrust w=30 k=3.0 | −$3,902 (310) | −$1,858 (182) |
| slower thrust w=30 k=2.0 | −$2,709 (324) | −$1,493 (205) |
| pullback 0.5×ATR within 10min | −$2,477 (300) | −$1,811 (187) |
| pullback 0.5×ATR within 20min | −$1,667 (300) | −$1,660 (192) |
| pullback 1.0×ATR within 10min | −$1,224 (295) | −$824 (164) |
| **pullback 1.0×ATR within 20min** | −$411 (300) | **+$111 (170)** ← best of ~80 |

The best of roughly eighty configurations is **+$0.65 a trade on 170 trades, and strip-3 takes it to
−$1,540.** Cause of death: strip-the-3-best. It is three trades, not an edge.

**STEP 6 VERDICT: the busy-session half of UNCLASS is a NULL.** Not "unclassified" — genuinely
untradeable by a continuation rider on 49 sessions of tape, under every exit family the desk owns.

---

## STEP 7 — HOW BIG IS THE PRIZE, REALLY? The oracle, and the escalation.

### The escalation you asked for — and it runs BACKWARDS

You asked for the size threshold at which a footprint becomes tradeable. Scoring the floored rider
across all eligible hours against the runs themselves:

| band | boarded | net | ceiling | capture |
|---|---:|---:|---:|---:|
| ALL 34 | 9/34 | −$162 | $4,097 | −3.9% |
| top-25 | 5/25 | +$35 | $3,251 | 1.1% |
| top-15 | 2/15 | +$47 | $2,134 | 2.2% |
| top-10 | 1/10 | +$94 | $1,510 | 6.2% |
| top-5 | **0/5** | $0 | $827 | 0.0% |

**There is no size threshold. The relationship runs the wrong way** — the bigger the run, the *less
likely* this rider is on it. The mechanism is not mysterious: the biggest UNCLASS runs are
concentrated in Europe and the US afternoon (the top-5 are 98pt, 84pt, 82pt, 76pt, 73pt — four of
five outside Asia), and that is precisely where the router keeps the gate dark. Narrowing to the
biggest runs does not reveal a footprint the marginal runs washed out. It removes the only runs we
can trade. **That is the finding, and it is a negative one.**

### The oracle — what a PERFECT filter would be worth

Board only the 34 runs, nothing else, real costs, real tie-breaks against the trade. 33 of 34 are
boardable by the aligned thrust.

| stop ↓ / target → | 2R | 3R | 4R | 5R | 6R | none |
|---|---:|---:|---:|---:|---:|---:|
| 1.5 | $752 (33) | **$1,054 (33)** | $784 (30) | $916 (28) | $511 (28) | $60 (26) |
| 2.0 | $587 (32) | $836 (32) | $907 (28) | $1,048 (26) | $640 (25) | $252 (23) |
| 2.5 | $551 (32) | $731 (32) | $813 (28) | $962 (26) | $543 (24) | $227 (22) |
| 3.0 | $457 (32) | $619 (32) | $712 (28) | $869 (26) | $426 (24) | $95 (22) |
| 4.0 | $299 (30) | $394 (29) | $747 (27) | $715 (23) | $484 (22) | $190 (20) |

**Best possible hindsight-perfect capture: $1,054 — 25.7% of the $4,097 headline.** Two things follow.

1. **The ceiling is a hindsight fiction and should be reported as such.** The census ceiling prices a
   15-minute close-to-close move on one lot. A late board with an honest stop cannot take it. Even the
   *oracle-of-oracles* — selling the exact 2-hour high after boarding — recovers $4,180 (102% of the
   ceiling), and the median run gives back **14%** of its headline to the 7.5-minute board alone;
   everything else is lost to the path. When the report says "$8,025 on the table", the tradeable
   fraction under perfect selection is closer to a quarter of it.
2. **The exit finding INVERTS on this population.** The best oracle cell is **stop 1.5 / target 3R** —
   *tight*, not wide. Asia's population wants 2.5/6R; the census-run population wants 1.5/3R. This is
   the one place I would push back on the "wide stop, far target" consensus: it is a property of the
   *fires* the rule generates in a quiet session, not a universal law of the tape. A late board into
   an already-extended busy-session run does not have 6R left in it.

### Separability — we CAN identify these runs, and it does not help

Census-week fires: 254 inside a sat-out UNCLASS run, 1,513 not. Rank AUC (0.50 = no information):

| feature | AUC | run median | ordinary median |
|---|---:|---:|---:|
| \|net10\| (thrust size) | 0.851 | 36.4 pt | 20.0 pt |
| ATR | 0.804 | 9.78 | 7.13 |
| volume | 0.773 | 1,494 | 628 |
| atr_pr | 0.671 | 0.687 | 0.469 |
| er15 | 0.636 | 0.226 | 0.184 |
| rvol | 0.617 | 1.264 | 1.014 |

**This kills the premise the bucket's name implies.** These runs are *not* unidentifiable — ATR
separates them at AUC 0.80 and volume at 0.77. (The 0.851 on |net10| is partly tautological: a run
*is* a big net move, so I discount it.) The problem was never that we cannot see them. It is that
identifying them is worth $1,054 under perfect selection, and the same conditions that mark a run
(high ATR, high volume) mark thousands of ordinary minutes that are not runs. AUC 0.80 against a
6:1 base rate does not produce a tradeable filter.

---

## STEP 8 — THE L2 BOOK. The instrument nobody had opened — and it is empty.

The pooled study closed by naming its most wanted next input: *"the L2 book read at the moment of
boarding, which is the one data source this entire study never opened."* I opened it.

**First look, capture.db, 6 sessions.** Boarding only when the far side of the book (the side price
runs *into*) was thin, `far_share < 0.48`, turned the census week's +$107 into **+$735 on 76 trades,
and it beat its own placebo p95** ($9.68/tr vs $3.37). That looked like the finding of the phase.

**But capture.db keeps 5 trading days of book, and the Parquet lake keeps 15 sessions —
170,619,876 rows, 2026-07-31 to 08-15.** That is 2.5× the window and it is the correct source. Rebuilt
per-minute L1–L3 depth from the lake and re-ran:

| far_share cut | n | net | $/trade | strip-3 | placebo p95 | verdict |
|---|---:|---:|---:|---:|---:|---|
| < 0.44 | 50 | +$315 | $6.29 | **−$190** | $9.68 | fails |
| < 0.46 | 117 | −$854 | −$7.30 | −$1,309 | $4.79 | fails |
| < 0.48 | 173 | −$22 | −$0.13 | −$881 | $2.70 | fails |
| < 0.50 | 207 | −$59 | −$0.29 | −$772 | $1.55 | fails |
| < 0.52 | 226 | −$1,637 | −$7.25 | −$2,350 | $1.61 | fails |
| < 0.54 | 225 | −$896 | −$3.98 | −$1,608 | $0.70 | fails |
| **> 0.54 (mirror — the OPPOSITE prediction)** | 104 | **+$671** | **+$6.46** | | | — |

Killed three separate ways, and I want each named:

1. **Parameter sweep — no plateau, the sign flips cell to cell** (+315, −854, −22, −59, −1,637). A
   real depth effect would be monotone in the threshold.
2. **Shifted-signal placebo — the fake beats the real.** Moving the signal 30 minutes later, keeping
   the book cut and every other rule, makes **$14.04/tr against the real signal's $6.29**. Your
   criterion says that alone is fatal.
3. **The mirror works too.** A *thick* far side — the exact opposite prediction — makes +$671. When
   both directions of a hypothesis pay, neither is the mechanism.

Consistent with the direct measurement: at board time, far-side depth share separates run-fires from
ordinary fires at **AUC 0.496** and signed book imbalance at **0.504**. Coin flips, both. The only
book variable with any signal is raw event count (AUC 0.793) — and that is just another activity
proxy, telling us nothing volume did not already say.

**This retires the pooled study's headline recommendation.** The L2 book, read as depth imbalance at
the minute of boarding, contains no information about whether a thrust continues. The +$735 was six
sessions of luck. Whatever the next attempt needs, it is not this — and knowing that costs the desk
one paragraph instead of a week.

---

## EVERY ATTEMPT, BY NAME, INCLUDING THE GRAVES

| # | candidate | n | net | $/tr | outcome — cause of death |
|---:|---|---:|---:|---:|---|
| 1 | Cluster label `UNCLASS` as a footprint | 6,820 bars | — | — | **KILLED — base rate 74.9% of all tape, lift 0.76 (anti-enriched)** |
| 2 | `VOL-EXPANSION` branch (amp > 0.30%) | 2 bars | — | — | **DEAD CODE — fires on 0.03% of tape, has never classified a run** |
| 3 | Boarding detector, grid of 12 (w,k) | 34 runs | — | — | **PASSED — 34/34 boarded, 2.19 ATR left, 4.33 ATR in the next hour** |
| 4 | Blanket rider, all eligible hours, 48-cell exit grid | 1,196 | +$307 | $0.26 | KILLED — blanket-across-regimes is the bug, not the result |
| 5 | EUROPE rider, 48-cell exit grid | 5,435 fires | best +$1,005 | $3.79 | KILLED — 43 of 48 cells red, no plateau |
| 6 | US-PM rider, 48-cell exit grid | 3,219 fires | best +$2,248 | $8.14 | KILLED — 36 of 48 cells red, no plateau |
| 7 | LATE 20–24 rider | 1,693 fires | best +$686 | $5.49 | KILLED — sign-flips cell to cell |
| 8 | **ASIA rider, raw** | 243 | **+$4,482** | **$18.45** | **SURVIVED the full battery** |
| 9 | Filter `rvol ≥ 1.0` / `≥ 1.3` | 253 / 238 | +$96 / +$240 | $0.38 / $1.01 | KILLED — fails placebo; volume confirmation is worthless overnight |
| 10 | Filter "flow agrees with the thrust" | 147 | −$91 | −$0.62 | KILLED — fails placebo, negative outright |
| 11 | Filter `er15 ≥ 0.15` / `≤ 0.15` | 221 / 230 | +$2,364 / +$1,535 | $10.69 / $6.67 | KILLED — both fail placebo (either direction "works" = neither does) |
| 12 | Filter `atr_pr ≥ 0.60` | 123 | +$856 | $6.96 | KILLED — fails placebo |
| 13 | Filter Mon–Thu | 194 | +$2,824 | $14.56 | KILLED — fails placebo (p95 $19.47) |
| 14 | Filter LONG-only / SHORT-only | 207 / 202 | −$1,054 / +$2,998 | −$5.09 / $14.84 | KILLED — both fail placebo; keep both sides |
| 15 | **Filters `atr ≥ 8pt`, `atr_pr ≤ 0.60`, `00:00–03:00`** | — | — | — | **SURVIVED — all beat placebo p95** |
| 16 | **UNCL-RIDER-ASIA (shipping)** | **157** | **+$5,006** | **$31.88** | **SURVIVED battery — then KILLED on the forward OOS leg (−$109 on the last 47 trades)** |
| 17 | R1 wide: stops→6×ATR, targets→12R, caps→6h, EUROPE | 60 cells | all ≤ −$5 | — | KILLED — every cell red |
| 18 | R1 wide, US-PM | 60 cells | all ≤ −$841 | — | KILLED — every cell red |
| 19 | R2 chandelier ×3 widths, EUROPE / US-PM | 6 configs | −$324 … −$2,998 | — | KILLED — 50–60% win rates and still red (give-back) |
| 20 | R2 break-even at 1R / 2R | 4 configs | −$531 … −$3,751 | — | KILLED — BE converts winners into scratches |
| 21 | R2 no-target time-only 240min | 2 configs | −$1,143 / −$3,735 | — | KILLED |
| 22 | R3 short-only / long-only, EUROPE + US-PM | 4 configs | −$487 … −$1,679 | — | KILLED — run direction skew does not transfer |
| 23 | R4 slower thrust w=20/30, EUROPE + US-PM | 6 configs | −$1,493 … −$3,902 | — | KILLED |
| 24 | R4 pullback board, 4 configs × 2 segments | 8 configs | best **+$111** | $0.65 | KILLED — strip-3 → −$1,540 |
| 25 | Size escalation top-25 / 15 / 10 / 5 | — | +$35 → $0 | — | **KILLED — runs backwards; 0/5 of the biggest boarded** |
| 26 | L2 book `far_share` cut, capture.db 6 sessions | 76 | +$735 | $9.68 | promoted for validation — beat placebo p95 |
| 27 | L2 book `far_share` cut, **lake, 15 sessions** | 50 | +$315 | $6.29 | **KILLED — no plateau + shifted-signal fake ($14.04) beats real ($6.29) + strip-3 −$190 + mirror also pays** |
| 28 | Oracle (perfect filter on the 34 runs) | 33 | +$1,054 | $31.94 | **BOUND — 25.7% of the ceiling is the maximum this bucket can pay** |

---

## THE ROUTER RULE — in the live router's own vocabulary

Written for the survivor, because a gate that is only viable behind a router condition is still a
finding. **Arm** `uncl_rider_asia` when *all* hold, evaluated on closed 1-minute bars:

```
session      : 00:00 ≤ utc_hour < 06:00        AND NOT (04:15 ≤ utc_hour < 05:15)   # gateway outage
volatility   : atr(1m,30) ≥ 8.0 points                    # ABSOLUTE, cross-session — not a percentile
                                                          #   the percentile re-baselines every 6h and
                                                          #   structurally cannot see a quiet week
extension    : atr_pct_rank(6h) ≤ 0.60                    # a CEILING. do not board an extended move
structure    : NO regime filter. The ATR floor and the atr_pr ceiling already do that work.
               (Benching dead-chop was tested and REJECTED: n=159, +$4,663, $29.33/tr —
                $343 WORSE than leaving it in, because removing those signals frees the
                one-position-at-a-time book to take worse trades elsewhere. And clean-trend
                must NOT be benched: after the ceiling it is the best bucket at $52.15/tr.)
trigger      : |close − close[−11]| ≥ 2.0 × atr           # direction-agnostic; side = sign(net10)
entry        : market, next bar's open
stop         : 2.5 × atr        target: 6.0 × atr        time cap: 120 min
```

**Bench it** outside 00:00–06:00 UTC — that is not a preference, it is the whole finding. In Europe
and the US afternoon this exact rule is a documented grave across ~80 configurations, and arming it
there would have cost roughly $2,000 over the tape.

Expectancy **on the home regime only**: **$31.88/trade, n=157, PF 1.87** (blanket cross-tape number
for context only: **$0.26/trade** — quoting that as the verdict would be the bug the discipline
names). Everything the rule needs (`net_atr_10`, `atr`, `atr_pct_rank`, `utc_hour`, `regime`) already
exists on `Features` bar the signed `net_atr_10`, which the pooled phase also requires.

---

## WHAT THE NEXT ATTEMPT WOULD NEED

1. **Fix the census, not the hunt.** Rename `UNCLASS` → `UNTESTED` and print it as a coverage gap.
   Recalibrate `amp > 0.30%` to a percentile (it is dead code). Align the flow-z buckets to the run
   timestamp *and* the wall clock and flag any run whose label disagrees between the two — 13% of
   them do. And report a **lift column** next to every cluster count; a cluster with lift < 1 should
   never again be handed to a phase as a hunting ground.
2. **Report a path-honest ceiling.** The 15-minute close-to-close ceiling overstates the tradeable
   prize by ~4×. A "boarded ceiling" — the best a late board with an honest stop could take — is one
   query and would have redirected this entire phase on day one.
3. **Do not ask for the L2 book again.** Depth imbalance at board time is AUC 0.496. Measured, on 15
   sessions, and reported above. If a book-based idea is proposed next week, it needs a different
   statistic (queue depletion *rate*, iceberg detection, or the 41ms event stream rather than a
   per-minute aggregate) and it needs to say why the per-minute imbalance null does not apply.
4. **The instrument the Asia rider actually needs is TIME.** It is 157 trades over 38 sessions with a
   three-week soft patch. Nothing in the robustness battery can settle whether that is decay or
   variance; only more sessions can. That is what the shadow book is for.

---

## DISPOSITION

| item | disposition |
|---|---|
| `UNCLASS` as a cluster label | **RETIRE** — 74.9% base rate, lift 0.76. Rename `UNTESTED`, report as coverage |
| `VOL-EXPANSION` branch | **FIX or DELETE** — fires on 0.03% of tape |
| UNCL-RIDER-ASIA | **SHADOW** — full spec above, accumulate n; revisit at 300 trades or 8 green weeks |
| Europe / US-PM continuation rider | **CLOSED** — ~80 configurations, all red. Do not re-hunt without a new instrument |
| L2 depth imbalance at board time | **CLOSED** — AUC 0.496; retires the pooled study's top recommendation |
| The $4,097 UNCLASS ceiling | **RESTATE** — hindsight-perfect capture is $1,054 (25.7%) |

---

## VERDICT

**VERDICT: NULL for the UNCLASS bucket, with one SHADOW survivor that does not answer it — and the
label itself is RETIRED as the phase's primary finding.** The ride was built (thrust board fires
inside **34/34** runs at a median 7.5 min in with 2.19 ATR left), filtered (five causal cuts beat
their placebos, ten failed and are named above), and routed (arm/bench rule written in the live
router's vocabulary) — exactly the order you specified — and the survivor **UNCL-RIDER-ASIA**
(n=157, +$5,006, $31.88/tr, 46.5% wins, PF 1.87, strip-3 +$4,219, strip-5 +$3,776, leave-one-day-out
worst +$4,438, 29/38 sessions green, both sides green, cost-stress ×3 +$4,221, placebo p95 $14.69 vs
$31.88, shuffled-direction null −$11.91/tr, 21 of 25 entry cells positive, 6 of 6 stop widths
positive at the 6R target) **was then killed by the FORWARD OUT-OF-SAMPLE LEG: +$5,114 on the first
110 trades (5 weeks) against −$109 on the last 47 (3 weeks)**, and the absolute ATR floor added
specifically to explain that away did not restore either red week (corr of weekly $/trade to weekly
Asia ATR = +0.57, partial at best). Separately and more importantly, the survivor is **not an answer
to UNCLASS**: it boards 9 of the 34 runs for −$162, it is dark by design over the Europe/US-PM
sessions holding $3,036 of the $4,097, the size escalation runs **backwards** (0 of the top-5 biggest
runs boarded, so there is no size threshold at which a footprint appears), the busy-session half died
across ~80 configurations with the best at +$0.65/tr **killed by strip-the-3-best (−$1,540)**, and the
L2 book — the one instrument never opened — was opened on 15 lake sessions and **killed by the
parameter sweep (sign-flipping, no plateau) and the shifted-signal placebo (the fake signal made
$14.04/tr against the real signal's $6.29)**, with the opposite prediction also profitable. The
banned verdict is not being used: these runs are **identifiable** (ATR AUC 0.804, volume 0.773) and
**boardable** (34/34) — the reason they cannot be ridden for money is that a hindsight-perfect filter
on them is worth only **$1,054, 25.7% of their $4,097 headline**, because the census ceiling prices a
close-to-close move that a late board with an honest stop can never take.
