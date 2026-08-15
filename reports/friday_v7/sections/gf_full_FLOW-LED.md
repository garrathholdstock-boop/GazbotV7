# MOVEMENT 3 — GREENFIELD LAB: THE **FLOW-LED** CLUSTER
### Full working, 2026-08-15 · MNQ · full parquet lake 2026-07-05 → 2026-08-14 · tick-honest · $1.50/round trip

---

## THE SHORT VERSION, BEFORE ANY OF THE WORKING

Garrath — two things came out of this cluster, and the second one is worth more than the first.

**The first thing is about the LABEL, and it outranks any gate on this page.** "FLOW-LED" means the
census looked at the 60 seconds before a run, found net aggressor flow that was at least a 1-sigma
event against its own trailing two hours, and found that flow pointing the SAME way the run then
went. It sounds like a footprint. It is not, at least not the way it is being used. On the full lake
that label is true on **10.0% of ordinary minutes** — and it is true on only **8.4% of actual runs**.
A run is *less* likely to wear the FLOW-LED badge than a random minute of tape is. Its twin, VACUUM
(the same flow event pointing the *wrong* way), is on 10.4% of tape and **18.6%** of runs. So when a
big flow event and a run happen together, the run goes **against** the flow more than twice as often
as it goes with it. Following the aggressors at the moment they get loud loses 0.75 points over the
next fifteen minutes and 1.07 over the next thirty, measured across 7,083 such minutes. The cluster I
was handed is, on the raw numbers, the *weaker half of a coin flip that mostly lands the other way*.

**The second thing is that the flow event is still worth having — as a FILTER, not as an entry.** A
plain 15-minute range break in the US session makes $5.18 a trade over 461 trades. The same break,
taken only when that minute is also carrying a ≥2-sigma flow event, makes **$24.26 a trade over 189**.
The flow reading throws away 60% of the breaks and quadruples what the survivors pay. That gate —
I've called it **BREAKFLOW** — is the one thing that walked out of this section alive, and it walked
out on a routed basis only: US session, elevated ATR, mid-ER tape. Overnight and pre-open it loses.

And the honest caveat that stops it being a LIVE recommendation: **73% of its money was made in one
week** (07-27..07-31), and **this report's own week was its worst — minus $278.60 over 44 trades.**

---

## 0. WHAT I RAN THIS ON, AND ONE BUG I WALKED INTO ON THE WAY

Everything here is off the parquet lake via `gazbot7.lake`, never `capture.db`. Capture holds five
trading days; using it would have cut the sample by four-fifths and told me nothing was there with
complete confidence.

| what | figure |
|---|---|
| tape used | MNQ, 2026-07-05 → 2026-08-14 |
| tick-days | **28** (V5 archive 07-05..07-17 + V7 capture 07-24..08-14) |
| the gap | 07-18..07-23 — real, left as a hole, never bridged |
| traded minutes | 35,350 |
| trade ticks underneath | 37.2 million |
| L2 depth (250ms) | 07-16..08-14, 22 days |
| costs | **$1.50 per round trip**, $2.00 per MNQ point, plus 1 tick (0.25pt = $0.50) adverse on every market fill |
| so a scratch costs | $2.50 = 1.25 MNQ points |

The cost line matters, and it is worth being precise about how much. An earlier version of this brief
said $5 a round trip — $3.50 a trade too much. At $5 the survivor still survives on its home segment
(+$24.44 becomes +$20.94), but its blanket book falls from +$6.10 to +$2.60, the volume-only variant
(+$2.74) dies outright, and the handful of marginal positive cells in the FDWELL and FFADE sweeps all
go negative. So the wrong fee would not have changed this section's verdict — but it would have
deleted three of the comparisons the verdict is built on, including the one in §5b that decides what
this gate is actually detecting.

**The instrument bug, reported because the scope asks for it.** My first pass at the minute table
came back with 1,931,352 rows for 28 days. Twenty-eight days is 40,320 minutes. The line was
`CAST(ts_ms/1000 AS BIGINT)/60*60` — and in DuckDB `/` is float division, so that expression is a
no-op and I had bucketed the tape **by second**. This is the exact failure the V7 scope already
flags from 08-07 (`(bar_ts/60)*60`), and it re-appeared unprompted in fresh code an hour after I read
the warning. It is caught here only because 1.9M was obviously wrong; had the number been merely
plausible the whole section would have been built on second-bars called minutes. The fix is `//`
(true integer divide) and a row-count assertion. **If any other study on this desk buckets time with
`/` in DuckDB, its numbers are wrong.**

---

## 1. ★ INTERROGATING THE CLUSTER LABEL — the finding that outranks the gates

The scope says to check a label's base rate before building anything on top of it, because a label
that is true on most of the tape is noise wearing a name. Here is the census's rule, unchanged:

```python
if flow is not None and fz is not None and abs(fz) >= 1.0:
    return "FLOW-LED" if (flow > 0) == (mv > 0) else "VACUUM"
```

### 1a. How much of the tape wears it

| threshold | share of all traded minutes |
|---|---|
| \|fz\| ≥ 0.5 | 45.33% |
| **\|fz\| ≥ 1.0 (the census's cut)** | **20.33%** |
| \|fz\| ≥ 1.5 | 10.47% |
| \|fz\| ≥ 2.0 | 5.97% |
| \|fz\| ≥ 3.0 | 2.47% |

Split that 20.33% by whether the flow agreed with what price did next, exactly as the census splits
it: **FLOW-LED is true on 10.02% of ordinary minutes, VACUUM on 10.44%.** So this is not the OPEN/NEWS
disaster (a clock true on 100% of its own window) and it is not the pre-08-01 `abs(flow) > 50` rule
that fired on 66.5% of bars. The z-score fix did its job. One minute in ten is a fair thing to call a
footprint — *if runs wear it more often than ordinary minutes do.*

### 1b. They don't. Runs wear it LESS often.

Running the census detector over the whole lake (1-minute port of the 5s scan; 15-minute move ≥ 1.5×
the typical 15-minute range, which on this tape is **73.1 points** against a typical range of 48.8):

| | runs | share of runs | share of tape | **lift** |
|---|---|---|---|---|
| **FLOW-LED** | 29 | 8.4% | 10.02% | **0.84** |
| **VACUUM** | 64 | 18.6% | 10.44% | **1.78** |
| neither (no flow event) | 251 | 73.0% | 79.7% | 0.92 |
| **all runs** | **344** | | | |

Read that twice. **The label I was handed is anti-selected for runs.** The flow-event *magnitude*
does carry information — P(a run starts | any ≥1σ flow event) is 1.301% against a 0.978% base rate,
a lift of **1.33** — but once a run does start on a flow event, the flow was pointing the *wrong* way
**64 times to 29**. The mean flow z-score measured **in the run's own direction** at the moment the
run starts is **−0.405** (median −0.153, only 39.5% positive, t = −3.90 on 344 runs). Runs on this
tape start by running away from the aggressors, not with them.

### 1c. And following the flow loses money before you even add a gate

Signed forward move in the flow's own direction, every minute on the tape, no entry logic at all:

| flow event | horizon | n | mean pt in flow direction | median | % positive | t |
|---|---|---|---|---|---|---|
| \|fz\| ≥ 1 | 5 min | 7,128 | −0.01 | 0.00 | 49.4% | −0.04 |
| \|fz\| ≥ 1 | 15 min | 7,083 | **−0.75** | −0.75 | 48.8% | −1.26 |
| \|fz\| ≥ 1 | 30 min | 7,031 | **−1.07** | −0.25 | 49.6% | −1.29 |
| \|fz\| ≥ 2 | 15 min | 2,073 | −0.53 | −1.00 | 48.8% | −0.41 |
| \|fz\| ≥ 3 | 15 min | 856 | **−1.63** | −2.25 | 47.0% | −0.75 |
| \|fz\| ≥ 3 | 30 min | 848 | **−1.96** | −2.88 | 47.4% | −0.65 |

Every horizon beyond five minutes is negative, and it gets *more* negative as the flow event gets
bigger. None of it is statistically strong (no t beyond 1.4), but the direction is consistent and the
sign is the wrong one for a continuation gate. **A cost line of 1.25 points sits above every cell in
that table.** Before a single trade is simulated, the mechanism "aggressors lead, follow them" is
already under water on this tape.

### 1d. The label is also phase-unstable — a bonus finding I did not go looking for

Cross-checking my pipeline against the frozen census, the 08-11 05:16 FLOW-LED run is recorded with
flow **−109**. My minute bucket for 05:15–05:16 said **+48**. Both are right: the census measures the
60s before the run *start*, and that run started at **05:16:40**, so its window is 05:15:40–05:16:40.
The scan grid's origin is arbitrary — and inside that one minute the flow sign flips.

So I re-measured every run's label at all 12 five-second phases of the same 60-second window,
rebuilding the z population at each phase:

| | result |
|---|---|
| runs given the SAME label at all 12 phases | **164 / 344 (47.7%)** |
| runs that flip **FLOW-LED ↔ VACUUM** outright | 23 (6.7%) |
| label share across all runs × phases | FLOW-LED 11.1% · VACUUM 15.8% · neither 73.1% |

**More than half of all runs get a cluster assignment that depends on where the scan grid happened to
start.** One in fifteen gets filed under the exact opposite footprint. That is not fatal — the
aggregate shares are stable even when individual rows move — but it means a *per-run* claim of the
form "this run was FLOW-LED" is worth much less than it looks, and the two members of this week's
frozen FLOW-LED cluster are a coin toss away from being VACUUM rows.

### 1e. What this week's frozen census actually handed me

| | |
|---|---|
| sat-out runs this week | 60, ceiling $8,024 |
| labelled **FLOW-LED** | **2** — 08-11 05:16 (−46pt) and 08-14 00:03 (−47pt) |
| their size rank among the 60 | 57th and 55th — the **smallest end** of the sat-out list |
| FLOW-LED runs in the frozen top-25 | **0** |
| FLOW-LED runs in the frozen top-15 | **0** |

The frozen census was produced by the classifier *before* this morning's fix, so the clock rule
(`13 ≤ hour < 15 → OPEN/NEWS`) still ran first and took the entire US-open block — which, as §2 shows,
is precisely where the FLOW-LED footprint lives. **This week's FLOW-LED cluster is two overnight
46-point moves, and it is two overnight 46-point moves partly because the label with the real
footprint was being robbed by a clock.** I did not re-run the census (frozen, as instructed); I ran
the same rule myself over the whole lake, which is the honest way to get the population back.

---

## 2. THE ESCALATION — where the footprint DOES appear

The operator's standing instruction: don't stop at the marginal runs, narrow to the biggest and hunt
again, and report the size threshold at which a footprint becomes visible. That threshold is real
here, and it is the reason this section didn't end at §1.

| run set | n | min move | **% FLOW-LED** | lift vs the 10.02% tape rate | % VACUUM | mean signed fz at start |
|---|---|---|---|---|---|---|
| ALL runs | 344 | 73pt | 8.4% | **0.84** | 18.6% | −0.405 (t −3.90) |
| TOP 50 | 50 | 153pt | 18.0% | **1.80** | 28.0% | −0.445 |
| TOP 25 | 25 | 195pt | 28.0% | **2.79** | 28.0% | −0.388 |
| **TOP 15** | 15 | 216pt | **40.0%** | **3.99** | 20.0% | **+0.315** (median +0.679, 67% positive) |

**The footprint appears at about 150 points and gets clean around 200.** Below that, flow-agreeing is
worse than random; at the top of the distribution it is four times the base rate, and the sign of the
mean flips positive for the first time. Six of the fifteen biggest moves on 28 days of tape were
genuinely led by aggressive flow.

Two honest brakes on that. First, **n = 15, and six events is six events** — the t-stat on that
positive mean is 0.42, which is nothing. Second, look at *when* those six fired:

| top-15 FLOW-LED runs | move | signed fz | ER at start |
|---|---|---|---|
| 07-17 **13:45** | +291pt | +2.11 | 0.56 |
| 07-30 **13:40** | +250pt | +2.84 | 0.24 |
| 08-06 **13:32** | +249pt | +4.66 | 0.61 |
| 07-27 **14:21** | −235pt | +1.12 | 0.18 |
| 07-31 **13:57** | −234pt | +1.87 | 0.27 |
| 08-13 **13:33** | +225pt | +1.69 | 0.08 |

Every single one between **13:32 and 14:21 UTC**. So "the FLOW-LED footprint appears in big runs" and
"the FLOW-LED footprint appears at the US cash open" are, on this sample, the *same statement*, and I
cannot separate them with 28 days. That ambiguity is what killed the escalation candidate in §4 and
it is what the router rule in §7 has to be honest about.

---

## 3. THE FIVE INVENTED CANDIDATES — every one by name, including the graves

All five are built from the cluster's own idea (a ≥z burst of net aggressor flow leads price), each
attacking a different reason the plain version might fail. Common machinery: signal evaluated at a
minute close, entry at the **first tick strictly after** that minute (no lookahead) plus a tick of
slippage, ATR-scaled stop and target, one position at a time, $1.50/RT.

First pass exit — stop 1.0×ATR, target 2.0×ATR, 30-minute clock (an operator-style guess, swept in §4):

| # | candidate | mechanical trigger | signals | trades | net | win% | **$/trade** |
|---|---|---|---|---|---|---|---|
| 1 | **FBURST** | \|fz\| ≥ 2.0, go **with** the flow | 2,061 | 1,377 | **−$7,759.75** | 30.2% | **−$5.64** |
| 2 | **FDWELL** | \|fz\| ≥ 1.5 on ≥2 of the last 3 minutes, same sign | 1,006 | 508 | −$2,027.07 | 31.3% | −$3.99 |
| 3 | **FBREAK** | \|fz\| ≥ 1.5 **and** the minute closes beyond the 15-min extreme, in the flow's direction | 1,135 | 867 | −$1,866.76 | 31.7% | −$2.15 |
| 4 | **FACCEL** | \|fz\| ≥ 1.5 **and** the trailing 15-min leg already runs the same way (≥0.5 ATR) | 2,029 | 1,396 | −$3,569.37 | 31.9% | −$2.56 |
| 5 | **FFADE** | the mirror: \|fz\| ≥ 2.0, take it **against** the flow | 2,061 | 1,389 | −$5,252.89 | 32.1% | −$3.78 |

All five lose. That in itself is informative: **the mirror loses too.** When a signal and its exact
opposite both lose about the same, nothing directional is happening and the costs are eating the
whole book — which is what §1c predicted before any of this ran.

Per-regime and per-session, because a blanket number is a bug, not a verdict (five cells out of
ninety came out positive, which is roughly what you'd expect from noise alone):

| candidate | best segment | n | net | $/tr | next-best segment |
|---|---|---|---|---|---|
| FBURST | NORMAL-CHOP | 166 | +$111.93 | +$0.67 | everything else negative; CLEAN-TREND −$8.82, VIOLENT −$12.34 |
| FDWELL | VIOLENT-WHIPSAW | 76 | +$349.07 | +$4.59 | CLEAN-TREND −$13.75 |
| FBREAK | **US session** | 290 | +$706.68 | +$2.44 | VIOLENT-WHIPSAW +$1.08 |
| FACCEL | CLEAN-TREND | 258 | +$58.89 | +$0.23 | everything else negative |
| FFADE | VIOLENT-WHIPSAW | 188 | +$347.93 | +$1.85 | US session −$6.66 |

Only FBREAK had a segment with both size and money in it. It was also the only one whose losing
blanket number looked like a *configuration* problem rather than a *mechanism* problem: 32% win rate
on a 2:1 payoff is a hair below break-even, and a break needs room. That is what §4 tested.

---

## 4. THE SWEEP — every threshold was a guess, so every threshold got swept

Grid: z × stop (×ATR) × target (×ATR) × hold, 108–135 cells per candidate, 594 tick-honest backtests.

| candidate | cells | **positive cells** | best cell | best $/tr | shape |
|---|---|---|---|---|---|
| FBURST | 135 | **0** | z3.0 / s1.0 / t1.5 / 15m | −$0.48 | no positive cell exists anywhere |
| FDWELL | 108 | 4 | z2.5 / s1.0 / t2.0 / 15m | +$2.05 | four scattered cells, n=136 |
| FFADE | 108 | 4 | z3.0 / s1.5 / t3.0 / 60m | +$1.47 | scattered |
| **FBREAK** | 108 | **46** | z2.5 / s1.5 / t3.0 / 60m | +$8.20 | **a contiguous plateau** |
| FBIG (§5) | 135 | 53 | z3.0 / s1.5 / t1.5 / 60m | +$11.98 | **a checkerboard** |

FBREAK's surface, $/trade, is the thing worth showing — it is monotone in the way a real edge is:

| exit | z=1.0 | z=1.5 | z=2.0 | z=2.5 |
|---|---|---|---|---|
| stop 0.5 / targ 1.5 | −2.26 | −1.25 | −0.29 | +1.64 |
| stop 1.0 / targ 2.0 | −2.65 | −1.13 | −0.55 | +0.71 |
| stop 1.5 / targ 1.5 | −1.20 | +1.73 | +2.54 | +3.16 |
| stop 1.5 / targ 2.0 | −2.05 | +0.53 | +1.76 | +2.54 |
| **stop 1.5 / targ 3.0** | −0.52 | **+2.62** | **+4.28** | **+5.68** |
| stop 1.5 / targ 3.0, 60-min hold | +0.81 | **+5.96** | **+6.10** | **+8.20** |

Ten of the twelve cells in the wide-stop / big-target block are positive, and the neighbours of the
best cell are all positive too. That is a plateau, not a spike. The diagnosis is plain in the numbers:
**a tight stop on a break is a donation.** At 0.5×ATR the gate is stopped out of moves that go on to
pay, at every single z.

Because the best cells sat on the grid's right-hand edge, I pushed the hold out past it (§5): 30 / 60
/ 90 / 120 / 180 minutes give **+$3.06 / +$6.09 / +$6.17 / +$6.25 / +$6.29** — the optimum is interior
and flat from an hour onward, so 60 minutes is a real choice and not an artefact of where I stopped
the grid.

**FBIG's surface is the counter-example, and it is why FBIG is dead.** Adjacent cells flip sign:
z2.0 / stop1.0 / targ1.5 gives −$1.58 while z2.5 in the same column gives +$7.18; the whole targ=2.0
block is deeply negative (−$12.35 at its worst) while targ=1.5 and targ=3.0 are positive. An edge
that exists at z=2.5 and z=3.0 but not at z=2.0, on 130–160 trades, is a curve fit.

---

## 5. THE ABLATION — does the FLOW half do any work at all?

This is the test that decides whether anything here belongs to *this* cluster. FBREAK is two rules
stapled together. Same exit (stop 1.5×ATR, target 3.0×ATR, 60-min clock), same costs, same book:

| variant | what fires | trades | net | win% | **$/trade** |
|---|---|---|---|---|---|
| **FBREAK** | break **+ flow event agreeing** | 572 | **+$3,481.20** | 35.1% | **+$6.09** |
| BRKONLY | break, no flow condition at all | 1,604 | −$2,074.70 | 32.8% | −$1.29 |
| BRKAGAINST | break + flow event **disagreeing** | 85 | +$1,196.80 | 37.6% | +$14.08 |
| FLOWONLY | flow event, no break (= FBURST at this exit) | 1,081 | −$4,254.80 | 32.1% | −$3.94 |

**Breaks alone lose. Flow alone loses. Together they make money.** That is a genuine interaction and
it is the only reason this section has a survivor. Confirmed across the breakout lookback, which I
swept because "15 minutes" was another guess:

| lookback | FBREAK $/tr (n) | BRKONLY $/tr (n) |
|---|---|---|
| 5 min | +$4.18 (701) | −$3.21 (2,001) |
| 10 min | +$3.00 (630) | −$2.16 (1,756) |
| 15 min | +$6.09 (572) | −$1.29 (1,604) |
| 30 min | +$8.21 (461) | −$0.27 (1,200) |
| 60 min | +$6.12 (373) | +$0.40 (851) |

Positive at every lookback for the filtered version, negative or nil at every lookback without it.

### 5b. But WHICH half of the flow condition — the size, or the direction?

BRKAGAINST making $14.08 a trade was the loose thread. If a flow event pointing the *wrong* way also
works, then what the filter detects is the **size** of the event, not its direction — and this section
would be claiming a directional footprint it hasn't got. So:

| variant | trades | net | **$/trade** |
|---|---|---|---|
| break + flow ≥2σ **agreeing** | 572 | +$3,487.20 | +$6.10 |
| break + flow ≥2σ **either sign** | 623 | **+$3,901.70** | **+$6.26** |
| break + flow ≥2σ **disagreeing** | 85 | +$1,196.80 | +$14.08 |
| break + raw **volume** surge (rvol ≥ 2), no aggressor sign at all | 610 | +$1,671.80 | +$2.74 |
| break, nothing else | 1,604 | −$2,068.70 | −$1.29 |

Flow-threshold curve, agreeing vs either-sign, $/trade:

| z | 0.5 | 1.0 | 1.5 | 2.0 | 2.5 | 3.0 | 4.0 | 5.0 |
|---|---|---|---|---|---|---|---|---|
| agreeing | +1.94 | +0.81 | +5.96 | +6.10 | +8.20 | +9.85 | +9.51 | +8.08 |
| either sign | +0.79 | +1.07 | +6.50 | +6.26 | +8.33 | +10.33 | +8.89 | +6.85 |

**The two curves are on top of each other at every threshold.** The verdict has to be stated plainly:

> **The directional half of the FLOW-LED label contributes nothing. What separates a good break from
> a bad one is the SIZE of the aggressor-flow event, not whether it agrees with the break.** Raw
> volume gets you about a third of the way there ($2.74 against $6.26 at matched n), so the signed
> aggressor tape is doing real work over and above "it was busy" — but the *sign* is decoration.

That is a finding about the cluster taxonomy itself, and it belongs alongside §1: FLOW-LED and VACUUM
are splitting one population — "the tape got loud" — into two directional halves that the money does
not distinguish. On these numbers the useful cut is **loud vs quiet**, not **with vs against**.

---

## 6. THE SURVIVOR: **BREAKFLOW** — exact mechanical spec

| component | rule |
|---|---|
| **instrument** | MNQ (this is not portable to MGC untested — gold gets its own hunt) |
| **clock** | evaluate once per minute, on the closed minute |
| **trigger A — structure** | the minute's close is above the highest high (long) or below the lowest low (short) of the **previous 15 minutes** |
| **trigger B — flow** | net aggressor flow in that same minute is a **\|z\| ≥ 2.0** event against the trailing **2 hours** of the same 60-second statistic (≥30 buckets of history required, else no signal) |
| **direction** | the **break's** direction (not the flow's — §5b) |
| **entry** | market on the first tick after the minute closes; costed at +1 tick adverse |
| **stop** | **1.5 × atr15** from entry, where atr15 = mean per-minute true range over the trailing 15 min (≈13–20pt on this tape); filled at the touched tick +1 tick adverse |
| **target** | **3.0 × atr15**, limit, requires the tape to trade through |
| **time stop** | **60 minutes** (flat from 60 to 180 — see §4) |
| **position** | one at a time; a signal arriving inside an open trade is skipped, and the skips are counted (96 of 287 in the routed book) |
| **costs** | $1.50 round trip + 1 tick slippage on entry, stop and time exit |

### Headline — routed (US session only), which is the number that counts

| | n | net | win% | **$/trade** | median | best | worst |
|---|---|---|---|---|---|---|---|
| **BREAKFLOW, US armed** | **191** | **+$4,668.60** | 40.8% | **+$24.44** | −$34.00 | +$323.80 | −$151.50 |
| blanket (armed 24h) — context only, never the verdict | 572 | +$3,487.20 | 35.1% | +$6.10 | −$29.00 | +$323.80 | −$151.50 |

Exit mix on the blanket book: 368 stops (−$44.88 average), 190 targets (+$102.30 average), 14 time
exits (+$40.07). A 35–41% win rate with a 2.3:1 payoff — exactly the shape the operator's judging
rule was written for. Win rate is not the story; the winners being big is.

### The excursion statistic

| | winners | losers |
|---|---|---|
| median MFE **inside the trade's own life** (points) | **79.12** | 12.75 |
| median hold | 12.6 min | 4.2 min |
| never went 1 ATR green before dying | — | **60.2%** |

⚠ That MFE is capped at the exit tick. My first version measured the best price over the whole
60-minute window and reported 135.75 / 39.00 / 19.5% — money the book was flat for. The desk has been
caught by that exact error before; the corrected figures are the ones above and they are much less
flattering to the losers, which is the point.

Losers die fast and shallow — four minutes, and **three in five never get a single ATR in front**.
Winners run a quarter of an hour and put 79 points on the board before they close. That is the
signature of a break-continuation edge: a cheap, quick, frequent loss paying for an occasional long
one, and it is why the wide stop with the 3R target beat everything tighter in §4.

---

## 7. ★ THE ROUTER — this gate is nothing without it

The blanket $6.10 is the average of one strong book and two losing ones. Never present it as the
verdict.

### By session

| session (UTC) | n | net | **$/trade** |
|---|---|---|---|
| **US — 13:30–20:00** | 189 | **+$4,585.90** | **+$24.26** |
| PRE-OPEN — 07:00–13:30 | 156 | −$681.30 | −$4.37 |
| OVERNIGHT — 20:00–07:00 | 227 | −$417.40 | −$1.84 |

### By regime × session ($/trade, n in brackets)

| regime | OVERNIGHT | PRE-OPEN | **US** |
|---|---|---|---|
| BUILDING (ER 0.20–0.40) | −$1.30 (157) | −$3.10 (104) | **+$40.50 (78)** |
| VIOLENT-WHIPSAW (ER<0.20, ATR ≥ p67) | −$43.20 (6) | +$38.60 (5) | **+$48.30 (25)** |
| CLEAN-TREND (ER ≥ 0.40, ATR ≥ p50) | −$4.20 (40) | −$15.50 (31) | +$4.50 (72) |
| NORMAL-CHOP | +$21.80 (11) | −$2.90 (9) | −$3.20 (7) |
| DEAD-CHOP (ATR ≤ p33) | −$2.90 (13) | −$6.30 (7) | −$0.20 (6) |

ATR cut points on this tape: p33 = 10.2pt, p50 = 12.4pt, p67 = 15.2pt (per-minute true range averaged
over 15 minutes).

Note what is **not** its home: **CLEAN-TREND pays $4.50.** By the time efficiency is above 0.40 the
break is late and you are buying the end of the leg. Its money is in the tape that is *building* — ER
between 0.2 and 0.4, ATR up — and in outright violence.

### The router rule, in the vocabulary the live router already speaks

```
ARM breakflow   WHEN  session == US            (minute_of_day >= 13:30 and < 20:00 UTC)
                AND   atr15   >= p33           (~10.2pt on current tape — the amp floor)
                AND   ( 0.20 <= er15 < 0.40    → BUILDING, the primary home )
                     OR ( er15 < 0.20 AND atr15 >= p67 → VIOLENT-WHIPSAW, the secondary home )
BENCH           WHEN  session != US            (this is the big one: −$1,098 across 383 trades)
                OR    er15 >= 0.40             (CLEAN-TREND: late, +$4.50/tr, not worth the slot)
                OR    atr15 <= p33             (DEAD-CHOP: nothing to break into)
```

**Every input already exists.** The router measures session, ATR and ER today; nothing new has to be
built for the arm/bench decision. **One instrument is missing for the entry itself:** the 60-second
net-aggressor z-score against a trailing 2 hours. The desk captures aggressor-tagged ticks live into
`capture.db.ticks`, so this is computable in real time from data we already have — it is a small
rolling-statistic service, not a new subscription. That is the entire build cost.

⚠ And the honest caveat that §2 forced: on 28 days I **cannot separate "US session" from "13:30–14:30
ignition"**. All six big FLOW-LED runs, and most of the money, land in the first three hours after the
cash open (13Z +$36.10/tr on 60 trades, 14Z +$36.00 on 33, 15Z +$42.00 on 15, then 16Z–19Z at −$2.90,
−$3.60, +$7.80, +$1.40). The router rule above arms for the whole US session because narrowing to
13:30–16:00 on this sample is fitting to where the sample happens to be thickest. If it goes to
shadow, log both windows and let a month of forward data pick.

---

## 8. THE ROBUSTNESS BATTERY on the routed (US) book

| test | result | verdict |
|---|---|---|
| headline | n=191, +$4,668.60, +$24.44/tr, 40.8% win | — |
| **strip best 1** | +$4,344.80 | pass |
| **strip best 3** | **+$3,759.80 (+$20.00/tr)** — top 3 are 19.5% of net | **pass** |
| **strip best day** | +$3,570.40 (+$19.84/tr) | pass |
| strip best 3 days | +$2,074.00 (+$12.35/tr) | pass |
| **leave-one-day-out** | positive on **26 of 26** day-drops; range +$20.07 to +$27.65/tr | **pass, emphatically** |
| **chronological halves** | first +$25.58/tr (n=87) · second +$23.49/tr (n=104) | pass |
| **era OOS** (V5 tape 07-05..07-17 vs V7 tape 07-24..08-14) | +$8.30/tr (n=70) vs +$33.78/tr (n=121) | pass in sign, **4× gap in size** |
| **long/short symmetry** | long +$24.52/tr (n=92) · short +$24.37/tr (n=99) | **pass — near-perfect** |
| **cost stress** ($2.50 RT + 2 ticks slip) | +$4,286.60 (from +$4,668.60) | pass |
| max drawdown | $736.60 | — |
| green days | 19 of 26 | — |
| **big-moves-caught** | **11/15** top runs · 18/25 · 95/344 | pass |

### The symmetry result is worth a paragraph, because the blanket book fails it

On the **blanket** (always-armed) book, long makes +$0.23/trade and short makes +$11.27 — a
one-sided gate, which the desk's rules say is a regime bet, not a mechanism. But split it by session
and the picture inverts completely:

| | OVERNIGHT | PRE-OPEN | **US** |
|---|---|---|---|
| long | −$12.22 (101) | −$13.95 (76) | **+$25.83 (91)** |
| short | +$6.44 (126) | +$4.73 (80) | **+$22.81 (98)** |

The long side isn't broken. The long side is **broken outside the US session**, where every overnight
break higher gets sold back. On the segment the gate is actually armed for, the two sides are within
$3 of each other. This is the clearest example in this section of why the standing rule against
blanket scoring exists: judged blanket, I would have shipped this as a short-only gate and thrown away
half of a symmetric edge.

### The placebos — including the one I had to redo

**First attempt (the standard time-shift):** slide the whole signal series 20–240 minutes, keep every
other rule, 200 draws.

| book | real net | fake mean | fake % positive | real percentile | p |
|---|---|---|---|---|---|
| blanket | +$3,487 | −$276 | 41.0% | 91.5 | **0.085** |
| US-routed | +$4,669 | +$58 | 45.5% | 96.5 | **0.035** |

Then I realised that test is **confounded on the routed book**: sliding a 13:45 signal two hours moves
it out of the US session, so it partly measures "is the afternoon better than the night" rather than
"is the flow filter better than nothing". A p of 0.035 earned that way is too kind. So it was redone
two ways, both holding session and trading day fixed:

| placebo | what it randomises | draws | real | fake mean | fake median | fake p90 | fake % positive | **p** |
|---|---|---|---|---|---|---|---|---|
| **A. matched-minute** | a random other US minute, same day, same count, direction drawn from the real mix | 200 | +$4,668.60 | −$510.91 | −$392.10 | +$1,117.96 | 35.0% | **0.000** |
| **B. filter-permutation** | a random 191 of the **465 real US breaks** — i.e. does the flow filter pick better breaks than a coin? | 200 | +$4,668.60 | +$1,189.29 | +$1,210.45 | +$2,504.67 | 86.0% | **0.000** |

*(A note on two numbers that differ by a hair: the routed book is 191 trades / +$4,668.60 when the
gate is armed US-only, and 189 / +$4,585.90 when you take the always-armed book and slice the US rows
out of it afterwards. Same for the break population — 465 armed-US signals versus 461 sliced. The
difference is real and it is the router doing its job: an overnight trade still open at 13:30 blocks
the first US signal in the always-armed version. The armed figures are the honest ones for a routed
gate; both are quoted so nothing looks like a typo.)*

Test B is the one that matters and it is the one I would have wanted an adversary to run. Every one
of the 200 random subsets of US breaks came in below the real book, and the median random subset made
about a quarter of what the flow filter made. **The filter is doing the work, and it is not the
session, the exit or the tape.**

Direction-shuffle placebo (real moments, permuted directions, 100 draws): fake mean +$649, real at the
100th percentile, p = 0.000.

### The kill shot that didn't quite land, and the one caveat that stands

Day-level leave-one-out passes 26 out of 26, which reads beautifully — and it hides the thing that
matters. Regrouped by ISO week:

| ISO week | dates | days | n | net | **$/trade** | win% |
|---|---|---|---|---|---|---|
| 28 | 07-06..07-10 | 5 | 35 | +$168.80 | +$4.82 | 37.1% |
| 29 | 07-13..07-17 | 5 | 35 | +$412.30 | +$11.78 | 34.3% |
| 30 | 07-24 only | 1 | 6 | +$309.40 | +$51.57 | 50.0% |
| **31** | **07-27..07-31** | 5 | 33 | **+$3,337.70** | **+$101.14** | 63.6% |
| 32 | 08-03..08-07 | 5 | 36 | +$636.30 | +$17.67 | 38.9% |
| **33** | **08-10..08-14 (this report's week)** | 5 | 44 | **−$278.60** | **−$6.33** | 29.5% |

**Week 31 is 72.8% of the entire net.** Strip it and the gate still works — +$1,248.20 over 156 trades,
**+$8.00 a trade** — so this is a concentration finding, not a fabrication finding. But two things must
be said out loud:

1. Day-level LOO cannot see week-level concentration. It passed 26/26 while three-quarters of the
   money sat in five consecutive sessions. **Any gate cleared by day-LOO alone on this desk should be
   re-checked by week.** That is a methodology note worth more than this gate.
2. **The most recent week — the week this report is about — is the worst in the sample.** 44 trades,
   −$278.60, 29.5% win. The tape this week was quiet (the census's typical 15-minute range was 29
   points against 48.8 across the lake), which is exactly the DEAD-CHOP condition the router is
   supposed to bench for — and yet it still fired 44 times, because ATR is scored against the *whole
   lake's* percentiles, not this week's. **The p33 floor needs to be a rolling percentile, not a
   static one.** That is the single most actionable fix on this page.

### The adversarial re-derivation

Everything above rests on a simulator I wrote this morning, so I re-walked 12 randomly-chosen trades
straight off the raw ticks with independent code, checking that the entry is the first tick *after*
the signal minute (no lookahead), that the P&L arithmetic reproduces from raw prices at $2.00/pt and
$1.50/RT, and — the one thing a bar backtest cannot know — that the stop and target were hit in the
order claimed.

**12 of 12 passed on all three checks.** Entry prices exact, net exact, and the exit reason matched
what the tape did in every case.

---

## 9. THE 250ms L2 BOOK — an honest null

Did the order book telegraph these breaks? 404 of the trades fall inside the depth window
(07-16..08-14). For each, the far-side depletion over the 30 seconds before entry: far / (far + near)
across levels 1–5, where "far" is the side price is about to run into. Below 0.5 means the book got
out of the way.

| far-side depletion | range | n | net | $/trade | win% |
|---|---|---|---|---|---|
| thin far side (T1) | 0.389–0.483 | 135 | +$286.00 | +$2.12 | 36.3% |
| middle (T2) | 0.483–0.510 | 134 | +$1,990.60 | +$14.86 | 36.6% |
| thick far side (T3) | 0.510–0.624 | 135 | +$365.80 | +$2.71 | 29.6% |

US-only, the ordering **reverses** — thin far side is the *worst* tercile (+$13.36) and thick far side
the best (+$38.55), on 45 trades a cell. Correlation between depletion and net across the whole book:
**−0.007.** Signed imbalance terciles are non-monotone too (+$4.51 / +$15.11 / +$0.06).

**Verdict: the 250ms sampled book does not separate these trades, in either direction.** The middle
tercile winning both times is the signature of noise, not of a hidden edge in the middle. Worth
saying what this does *not* claim: `depth.db` is a 250ms sample, and `capture.db.book` (41ms,
event-driven, MNQ-only) sees fleeting quotes this cannot. A single-print sweep of the far side would
not show up here. This table rules out a 30-second *average* depletion signal, nothing more.

---

## 10. DID IT SHOW UP FOR THE RUNS WE SAT OUT?

"Caught" = a BREAKFLOW trade in the run's direction opened between 5 minutes before and 15 minutes
after the run's start.

| run set | runs | caught (blanket book) | caught (US-routed) | ceiling | **banked (routed)** |
|---|---|---|---|---|---|
| ALL runs ≥73pt | 344 | 159/344 | 95/344 | $78,558 | +$6,661.10 |
| **FLOW-LED labelled** | 29 | 17/29 | 15/29 | $7,920 | +$1,216.70 |
| VACUUM labelled | 64 | 34/64 | 19/64 | $15,716 | +$1,236.60 |
| unlabelled | 251 | 108/251 | 61/251 | $54,922 | +$4,207.80 |
| TOP 25 by size | 25 | 20/25 | 18/25 | $12,087 | +$3,584.50 |
| **TOP 15 by size** | 15 | **13/15** | **11/15** | $8,024 | **+$2,890.70** |

**36% of the top-15 ceiling converted into honest money** — against the census's live-desk conversion
of 50% on the three runs it actually caught, but across 11 runs instead of 3. The two it missed
outright in the routed book (07-29 19:30 −271pt and 07-29 18:55 −215pt) were both after 18:00Z on the
same evening; the two it missed entirely were outside any break structure.

The top 15, named, because the operator asks for the specific runs:

| run | move | label | routed? | banked |
|---|---|---|---|---|
| 07-31 13:35 | −356 | — | yes | +$292.70 |
| 07-08 08:15 | −349 | VACUUM | no (pre-open — benched) | $0 (blanket book made +$421.00) |
| 07-14 12:15 | +314 | — | no (pre-open — benched) | $0 (blanket −$96.50) |
| 07-29 18:35 | +292 | — | yes | +$271.20 |
| 07-17 13:45 | +291 | **FLOW-LED** | yes | +$260.00 |
| 07-29 19:30 | −271 | — | **missed** | $0 |
| 07-30 13:40 | +250 | **FLOW-LED** | yes | +$273.10 |
| 08-06 13:32 | +249 | **FLOW-LED** | yes | +$207.00 |
| 07-29 19:49 | −247 | — | yes | +$262.10 |
| 07-28 13:30 | −242 | VACUUM | yes | +$268.70 |
| 07-29 19:11 | −242 | VACUUM | yes | +$282.50 |
| 07-27 14:21 | −235 | **FLOW-LED** | yes | +$227.50 |
| 07-31 13:57 | −234 | **FLOW-LED** | yes | +$323.80 |
| 08-13 13:33 | +225 | **FLOW-LED** | yes | +$222.10 |
| 07-29 18:55 | −216 | — | **missed** | $0 |

**And the two runs this section was literally handed** — the frozen census's FLOW-LED pair — the
blanket book caught both: 08-11 05:16 (−46pt) for **+$36.20** and 08-14 00:03 (−47pt) for **+$67.70**.
Both are outside the US window, so the **routed** gate would have benched itself and taken neither.
That is the correct outcome and I am not going to dress it up: the cluster's two nominal members are
overnight 46-point moves whose combined ceiling is $186, and the routed gate declines them on
purpose, because taking overnight breaks costs $1.84 a trade across 227 of them.

Charts of three of these afternoons — 08-11, 08-13 and 08-14, with the census sat-out runs marked and
every BREAKFLOW entry and exit drawn on the real price path — are in
`reports/friday_v7/sections/fl/gf_fl_charts.svg.html` (inline SVG, built from the lake's own 5s bars
and the simulator's real fills).

---

## 11. DISPOSITION TABLE — every lead touched, nothing quietly dropped

| lead | what it was | best honest number | **disposition** | cause of death / revival condition |
|---|---|---|---|---|
| **The FLOW-LED label itself** | ≥1σ flow event agreeing with the move | 8.4% of runs vs 10.02% of tape → **lift 0.84** | **REFUTED as a footprint** | Named test: base-rate + lift measurement on 344 runs / 35,350 minutes, plus the signed-fz test (mean −0.405, t = −3.90) and the 12-phase stability test (unanimous on only 47.7% of runs). No reformulation of "flow agreeing with the move predicts a run" survives a lift below 1. **The flow event survives as a magnitude filter — see BREAKFLOW.** |
| **BREAKFLOW** (was FBREAK) | 15-min range break + ≥2σ flow event, wide stop, 3R target, 60-min clock | **US-routed: n=191, +$4,668.60, +$24.44/tr, 40.8% win** | **SHADOW** | Survived strip-3 (+$20.00/tr), day-LOO 26/26, both halves, era OOS, cost stress, symmetry-on-home-segment, matched-minute placebo (p=0.000) and the filter-permutation placebo (p=0.000, beat all 200 draws). Held back from LIVE by **week-level concentration (wk31 = 72.8% of net)** and by **this week being its worst (−$278.60)**. Promote to LIVE after ≥3 forward weeks with no single week >50% of net. |
| **FBURST** | the literal cluster mechanism: ≥2σ flow event, go with the flow | −$7,759.75 over 1,377 trades (−$5.64/tr) | **REFUTED** | Named test: the **parameter sweep — 0 of 135 cells positive**, at any z, stop, target or hold; corroborated by the unconditional measurement in §1c (following a ≥1σ flow event loses 0.75pt/15min across 7,083 minutes) and by the mirror (FFADE) also losing, which means no directional information exists to invert. |
| **FFADE** | the mirror: fade the flow event | 4 of 108 cells positive; best +$1.47/tr | **PARKED** | Failed the sweep as built (scattered cells, no plateau). Mechanism belongs to the **VACUUM** section, which owns the against-the-flow population (18.6% of runs, lift 1.78) — revive only as a cross-reference if VACUUM's hunt finds a structure trigger, since flow-alone has no edge either way. |
| **FDWELL** | flow burst that PERSISTS (≥2 of 3 minutes) | 4 of 108 cells; best +$2.05/tr, n=136 | **PARKED** | Failed the sweep. Revive by testing dwell as a **filter on breaks** rather than as an entry — i.e. BREAKFLOW with a 2-of-3 persistence requirement on the flow event. Untested; it may raise BREAKFLOW's per-trade at the cost of n. |
| **FACCEL** | flow burst joining an established leg | −$3,569.37 over 1,396 (−$2.56/tr) | **PARKED** | Only tested at the first-pass exit (stop 1×ATR / target 2×ATR) — the exact exit that also made BREAKFLOW look dead. Never swept. Revive by running it through the wide-stop / 3R / 60-min exit that rescued the break. |
| **FBIG** | the escalation candidate: the top-15 profile (≥2.5σ flow event, US ignition window 13:25–14:30, ATR above median) mechanised | best cell +$11.98/tr (n=128); base config **−$7.54/tr** | **PARKED** | Named test: the **parameter sweep — a checkerboard, not a plateau.** Adjacent cells flip sign (z2.0 −$1.58 vs z2.5 +$7.18 in the same column; the whole target=2.0 block deeply negative). Revive at n ≥ 400 — roughly three more months of tape — since the top-15 population that motivated it is only six events. |
| **BRK_FLOWANY** | break + ≥2σ flow event of **either** sign | +$3,901.70 over 623 (+$6.26/tr) — beats the agreeing version | **SHADOW (as the preferred form)** | Not a failure: it is the *better* version, and it is what forces the §5b verdict that the label's direction is decoration. Shadow it alongside BREAKFLOW and let forward data choose between them; they differ by 51 trades. |
| **BRK_RVOL** | break + raw volume surge, no aggressor tape at all | +$1,671.80 over 610 (+$2.74/tr) | **PARKED** | Works, but at matched n it is less than half of the signed-flow version ($2.74 vs $6.26). Kept on the page because it is the fallback if the live flow-z instrument proves unreliable — volume is already measured everywhere. |
| **BRKONLY** | the naked 15-minute break | −$2,074.70 over 1,604 (−$1.29/tr); +$5.18/tr US-only | **REFUTED as a standalone** | Named test: the ablation. Negative blanket and at 4 of 5 lookbacks. It is the *substrate* BREAKFLOW filters, not a gate. |
| **250ms book separation** | far-side depletion before the break | correlation −0.007; terciles non-monotone and reversed between blanket and US | **HONEST NULL** | Rules out a 30-second average depletion signal only. The 41ms event book (`capture.db.book`) could still show a single-print sweep; untested here. |

---

## 12. WHAT I'D DO WITH THIS ON SATURDAY, AND THE ONE STONE STILL UNTURNED

**Ship to shadow, not to the paper tournament:** BREAKFLOW at z=2.0 / stop 1.5×ATR / target 3.0×ATR /
60-minute clock, armed **only** US session with the ATR floor and the ER band above, alongside its
either-sign twin. Log both the 13:30–20:00 and the 13:30–16:00 arming windows so forward data can
separate "US session" from "cash-open ignition", which 28 days cannot.

**Build the one missing instrument:** a rolling 60-second net-aggressor z-score against the trailing
two hours, computed live off `capture.db.ticks`. Everything else the router rule needs, the router
already measures.

**Fix the floor before anything goes live:** the ATR percentile cut is currently static across the
whole lake, which is why the gate fired 44 times into this week's dead tape and lost $278.60. It has
to be a rolling percentile — the same amp-floor idea the abs_veto rehab already uses, but recomputed
on a trailing window rather than frozen.

**And the stone still unturned.** Every number in this section treats the flow event as a
*one-minute* quantity, because that is what the census's rule does. The thing I never tested is
**where inside the run the flow event sits** — whether a break that comes with its flow burst is
different from a break whose burst arrived three minutes earlier and has already faded. §1d showed
the label is phase-unstable at the 5-second scale, which strongly hints the *timing* of the burst
relative to the break carries information the ±1-minute alignment throws away. That is a
lead-lag study on the 41ms event book, and it is the first thing I would do next week.

---

## 13. WHERE THE WORKING LIVES (so the next reader can break it)

Every number above comes from one cached minute table, so nothing in this section silently
re-derives on a different window. All outputs in `reports/friday_v7/sections/fl/`.

| step | script | what it produces |
|---|---|---|
| 0a | `scripts/gf_fl_feat.py` | `fl/feat.csv` — 35,350 minutes of flow / fz / ATR / ER / forward moves off the lake |
| 0b | `scripts/gf_fl_label.py` | `fl/label.json` — base rate, lift, precision/recall, raw directional edge |
| 0c | `scripts/gf_fl_phase.py` | `fl/phase.json` — the 12-phase label-stability test |
| — | `scripts/gf_fl_engine.py` | the tick-honest simulator ($1.50/RT, $2.00/pt, 1 tick slippage) |
| 1 | `scripts/gf_fl_cands.py` | `fl/cands.json` + `fl/trades_*.csv` — the five candidates, with regime/session splits |
| 2 | `scripts/gf_fl_escalate.py` | `fl/escalate.json` — the ALL / TOP50 / TOP25 / TOP15 escalation |
| 3 | `scripts/gf_fl_sweep.py` | `fl/sweep.json` — 594 tick-honest backtests |
| 4 | `scripts/gf_fl_robust.py` | `fl/robust_FBREAK.json` (blanket) and `fl/robust_FBREAK_sessionUS.json` (routed) |
| 5 | `scripts/gf_fl_ablate.py`, `gf_fl_ablate2.py` | `fl/ablate.json`, `fl/ablate2.json` — the break-vs-flow ablations |
| 6 | `scripts/gf_fl_book.py` | `fl/book.json` — the 250ms L2 separation null |
| 7 | `scripts/gf_fl_placebo2.py` | `fl/placebo2.json` — the matched-minute and filter-permutation placebos |
| 8 | `scripts/gf_fl_verify.py` | `fl/verify.json` — 12 trades re-walked off raw ticks, plus the per-ISO-week concentration |
| 9 | `scripts/gf_fl_catch.py` | `fl/catch.json` — big-moves-caught, run by run |
| charts | `scripts/gf_fl_chart.py` | `fl/gf_fl_charts.svg.html`, `fl/conc.json` |

The two things most likely to be wrong, named so someone can attack them: **(a)** the run detector is
a 1-minute port of the census's 5-second scan, so its run set (344 runs, ≥73.1pt) is close to but not
identical with the frozen census's; **(b)** `simulate()` gives target fills at the limit price with no
slippage while charging a tick on every market fill — if real target fills slip, the survivor's
per-trade drops by up to $0.50 (it survives the $2.00-a-trade cost stress, so this does not change the
verdict, but it does move the number).

---

## VERDICT

**The FLOW-LED cluster LABEL is REFUTED as a footprint** — killed by the base-rate/lift test: it is
true on 10.02% of ordinary tape but only 8.4% of runs (lift **0.84**, below one), its mirror VACUUM
carries 18.6% at lift 1.78, the mean flow z-score in a run's own direction at the moment it starts is
**−0.405 (t = −3.90)**, and the label is phase-unstable on more than half of runs. **One gate SURVIVED
on top of it — BREAKFLOW (SHADOW, US-routed: n=191, +$4,668.60, +$24.44/trade, 40.8% win, 11/15 big
moves caught)** — but it survives as a **magnitude filter, not a directional one**: the same break
taken with the flow event pointing the *wrong* way pays the same ($6.26 either-sign vs $6.10
agreeing), so what earns is "the tape got loud at the break", not "flow led the move". It is held at
SHADOW rather than LIVE because **72.8% of its money is one week (07-27..07-31)** and **this report's
own week is its worst at −$278.60 over 44 trades**. Of the five candidates invented from the cluster's
literal mechanism, **FBURST is REFUTED** (parameter sweep: 0 of 135 cells positive) and **FFADE,
FDWELL, FACCEL and the escalation candidate FBIG are PARKED**, each with its revival condition named
above. **The footprint's size threshold, which the escalation was asked to find: it appears around
150 points and is clean by 200** — 8.4% of all runs are FLOW-LED, rising to 18% of the top 50, 28% of
the top 25 and **40% of the top 15** — but on 28 days that threshold is inseparable from the
13:30–14:30 UTC cash-open ignition window, and saying otherwise would be inventing a finding.
