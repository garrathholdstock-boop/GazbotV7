# ARM 5 — THE QUIET TURN

**MNQ · 273 session-days of 1-minute bars · 2025-09-14 → 2026-10-01 · 371,814 minute bars**
**~560 scored cells · read-only: no order placed, no `/api/control` POST, no service touched**
**Every headline RE-DERIVED on clean tape after three shared-loader bugs and one of my own; both
baselines quoted (vs 50% and vs a side-matched control); shift-scanned and ablated. See §METHOD.**

> *"the thing you need to understand is the turns are not violent. they often just change
> direction. sometimes its violent. but more often than not it can just start grinding in
> that direction."* — the operator

---

## THE ONE-PARAGRAPH ANSWER

**He is right about the character of a turn, and the hypothesis built on it is inverted.**
**86.3% of turns are low-efficiency grinds** (median efficiency of the first 30 minutes after a
turn: **0.32** — price travels three times the net distance it covers), and `turn_watch`'s 15×ATR
retrace confirms a turn within 30 minutes on only **7.9%** of them: where it speaks at all it is a
median **91 minutes late with 129pt already gone of a 185pt new move (70%)**. The blind spot is
real and large. But every quiet-turn feature I built — stall in time, slope zero-cross, time
asymmetry — is **NEGATIVE as a turn entry (43.3%, n=594) and POSITIVE as a CONTINUATION entry.** A
run going quiet near its extreme is **pausing, not ending.** **The leader: stall ≥30min + a slope
flip + price still within 8×ATR of the extreme, entered WITH the run — 3.23 fires/session,
56.7% at ±50pt/120min (n=594), which is +6.7pp vs the 50% break-even and +6.4pp vs a side-matched
control (they nearly coincide because the rule is side-balanced 53/47). OOS halves 56.8% / 56.7%,
all four session blocks positive, and — the test that matters — the edge DECAYS monotonically to
+1.0pp when the entry is shifted 60 minutes later, so the trigger minute is doing the work.**
**≈ +$24/session at single lot, of which ~$9 is simply being with the run and ~$15 is the signal.**
**PROMISING, not PROVEN**: one target only, and it does not *provably* beat a plain pullback entry.

---

## ★ HEADLINE: THE VIOLENT-versus-QUIET SPLIT

**It does not exist as a single number, and that is the finding.** Censused on **871 turns
(3.19/session)** — a turn being a run's terminal extreme, identified with hindsight, which is legal
for a census and illegal for a signal. Nothing below feeds a rule.

| "VIOLENT" defined as | VIOLENT | QUIET |
|---|---|---|
| a 1-min move ≥ 1.0 × ATR within 15min of the extreme | 85.1% | 14.9% |
| a 1-min move ≥ 1.5 × ATR within 15min | 65.1% | **34.9%** |
| a 1-min move ≥ 2.0 × ATR within 15min | 45.4% | 54.6% |
| 30-min displacement ≥ 3 × ATR in the new direction | 81.1% | 18.9% |
| 30-min displacement ≥ 5 × ATR | 59.0% | 41.0% |
| 5 × ATR given back within 15 min | 54.2% | 45.8% |
| **efficiency of the first 30 min ≥ 0.5** | **13.7%** | **86.3%** |

**The number swings from 14% to 85% with the threshold, so anyone quoting one figure has chosen
it.** The row that is not threshold-sensitive is the last, and it is his sentence measured:

> **86.3% of turns are low-efficiency grinds. Median efficiency of the first 30 minutes after a
> turn is 0.32.**

Two claims, not one number:

- **A turn with no magnitude event at all is a MINORITY — 14% to 35%.** Arm 2's independent volume
  measurement agrees: **22.5% of turns are quiet by volume (z<1)**; climax volume is genuinely
  enriched 2.2× at turns but still covers only 35.2%, and a z≥5 detector fires 5.85/session with
  18.2% landing near a turn.
- **A turn that announces itself EFFICIENTLY is a 14% minority** — and this is the more useful
  half. **The problem is not that the magnitude is absent; it is that the magnitude is embedded in
  a grind**, so a displacement detector cannot separate the turn from noise. That is why every
  violence detector on this desk fires 20–87 times a session or not at all.

### Why the shipped detector is effectively blind — 871 turns

| `turn_watch`'s 15 × ATR retrace | |
|---|---|
| confirms within **30 min** of the true extreme | **7.9%** |
| confirms within 240 min | 77.3% |
| median delay where it confirms | **91 minutes** |
| median points already gone | **129pt of a 185pt new move = 70%** |

`turn_watch`'s own docs put the cost at "160pt of a 298pt leg". **This independently re-derives it:
the detector is not wrong, it is LATE, and it misses the first 70% of the move.** Any replacement
must be judged on **latency against a hindsight extreme** — a question no arm has been asked, and
in my view the most valuable thing this study surfaces.

---

## ★★ THE TEST THAT DECIDES THIS ARM: THE WINDOW-SHIFT SCAN

Arm 1's headline lost 85% of its edge to ablation — its cooled rule was **a subset of a flat
population, not a signal.** The diagnostic is to move the entry *k* minutes from the trigger and
re-race. **A real timing signal must DECAY with the shift. A flat profile refutes it.**

| entry shifted | n | rule | vs 50% | vs side-matched control (50.4% ± 2.0) |
|---|---|---|---|---|
| **+0 — THE TRIGGER** | **594** | **56.7%** | **+6.7pp** | **+6.4pp** |
| +15 min | 581 | 53.0% | +3.0pp | +2.6pp |
| +30 min | 574 | 52.3% | +2.3pp | +1.9pp |
| +60 min | 578 | 51.4% | +1.4pp | +1.0pp |
| +120 min | 556 | 48.7% | −1.3pp | −1.6pp |
| +240 min | 487 | 47.6% | −2.4pp | −2.7pp |

**Monotonic decay to nothing by +60 minutes and negative by +120. The trigger MINUTE is carrying
the result, not the window it sits in.** This is the strongest single piece of evidence in this arm
and the reason I am ranking it PROMISING rather than filing it as a selection artefact.

⚠ **BACKWARD shifts are NOT a valid control and must not be read as findings.** They measure
83.8% at −120min, 69.4% at −60, 15.9% at −30 and 40.1% at −15 — all **hindsight-contaminated by
construction**, because the fire's *existence* depends on a stall that had not yet happened at the
shifted entry. −30min lands essentially on the run's extreme (the stall is 30 minutes long), so
entering with the run there loses 84% of the time; −120min sits mid-advance in a run we only
selected *because* it later stalled. **Only forward shifts test inertness.** I report the numbers
so nobody rediscovers 83.8% and mistakes it for an edge.

### The ablation — which condition is actually working

Dropping one condition at a time, ±50pt/120min, entering WITH the run:

| rule | fires/sess | n | rule | vs 50% | vs control |
|---|---|---|---|---|---|
| **FULL: stall≥30 + slope flip + depth≤8×ATR** | 3.23 | 594 | **56.7%** | **+6.7** | **+5.8** |
| drop the slope flip *(= FLAT-TOP)* | 3.28 | 600 | 56.0% | +6.0 | +4.7 |
| drop the depth cap | 3.32 | 609 | 55.8% | +5.8 | +6.3 |
| **drop the STALL** | 3.68 | 648 | 53.4% | **+3.4** | +3.8 |
| stall only | 3.34 | 611 | 55.3% | +5.3 | +5.7 |
| depth cap only | 3.72 | 636 | 52.8% | +2.8 | +3.0 |
| slope flip only | 3.68 | 648 | 53.4% | +3.4 | +3.8 |
| **NOTHING — first eligible minute of every run** | 3.72 | 636 | **52.8%** | **+2.8** | +3.0 |

**Dropping the STALL costs the most (−3.3pp), and the stall alone recovers +5.3 of the +6.7. The
operator's feature 1 is the active ingredient.** The slope flip and the depth cap add ~1.4pp
between them, and the paired test says the slope flip alone is not measurable
(**+0.7pp [−1.6..+2.9]**).

⚠⚠ **AND THE HONEST DECOMPOSITION, which is less flattering than the headline.** Simply being with
the run from its first eligible minute already scores **52.8% (+2.8pp)**. So:
**be with the run +2.8pp → add the stall +2.5pp → add depth and slope +1.4pp = +6.7pp.**
**Roughly 40% of the headline is the run-entry baseline, not the quiet-turn feature.**

---

## THE RANKED SHORTLIST

All verdicts at **±50pt / 120min — the only target that survives.** Two baselines, per the
coordinator's correction, because they answer different questions: **vs 50%** is the TRADEABLE
number (50% is the real break-even on a symmetric race, and drift you capture is money in the
book); **vs side-matched** is the SKILL number. **For this arm they nearly coincide — the rules are
side-balanced 51–53% long by construction, because the 15×ATR latch alternates direction — so
unlike arm 1, nothing here was riding the tape's +5,159pt drift.**

### 1. THE CONJUNCTION — **PROMISING.** Best performer, most stable, passes the shift scan.

**The rule, precisely enough to implement.** 1-minute MNQ bars, causal ATR14:

1. **Latch a run direction** with `turn_watch`'s frozen rule: flip when price gives back
   **15 × ATR** from the running extreme; seed with `leg_watch`'s open rule (8 min moving ≥1×ATR).
   → **3.71 runs/session**, an independent re-derivation of `turn_watch`'s published 3.6. Nothing
   fitted.
2. Track the live run's running extreme; `stall = minutes since the last new extreme`.
3. **FIRE** at the first minute where all three hold: `stall ≥ 30` · the rolling 15-min OLS slope
   of close has flipped **against** the run (**no magnitude threshold** — grinding means the slope
   is small) · price is still within **8 × ATR** of the extreme. One fire per run.
4. **ENTER WITH THE RUN.** ⚠ **The inverse of the hypothesis.**

**3.23 fires/session. Side split 53% LONG / 47% SHORT.**

| | n | rule | vs 50% | side-matched ctl (20 draws) | vs ctl | 95% day-clustered |
|---|---|---|---|---|---|---|
| **±50pt / 120min** | **594** | **56.7%** | **+6.7pp** | **50.4% ± 2.0** | **+6.4pp** | **[+2.6..+10.7] excl. 0** |
| ±100pt / 120min | 294 | 54.1% | +4.1pp | 50.2% ± 2.8 | +3.9pp | [−2.4..+10.2] spans 0 |
| ±150pt / 120min | 146 | 52.1% | +2.1pp | 51.1% ± 3.7 | +1.0pp | [−8.1..+10.1] spans 0 |
| ±150pt / 240min | 273 | 52.0% | +2.0pp | 51.0% ± 2.4 | +1.0pp | [−5.0..+7.2] spans 0 |

**OOS halves (136/137 sessions): 56.8% and 56.7%.** Near-identical.

**By session block** (control is side- and clock-matched, drawn from a different session):

| block | fires/sess | rule | vs 50% | control | vs ctl |
|---|---|---|---|---|---|
| ASIA 00–07Z *(benched by policy)* | 1.00 | 57.4% (n=155) | +7.4 | 48.3% ± 3.9 | +9.1 |
| EU 07–13Z | 0.62 | 55.1% (n=136) | +5.1 | 50.8% ± 4.9 | +4.4 |
| **US cash 13–20Z** | **0.75** | **57.0% (n=179)** | **+7.0** | 51.0% ± 5.3 | **+6.0** |
| LATE 20–24Z | 0.85 | 57.3% (n=124) | +7.3 | 50.9% ± 5.1 | +6.4 |

All four positive. Each n is 124–179 with a ±4–5pp control spread, so no block is conclusive alone
— but they agree.

**Mechanism, one sentence:** a run that stops making new extremes and rolls its short-term slope
over *while having given nothing back* is **pausing, not ending** — the Lindy effect already frozen
in `leg_watch`'s REFCLASS (median remaining points *rise* 39→54pt from 15 to 180 minutes of age
while the chance of dying within 15 minutes *falls* 27%→13%).

**In his units.** Single lot, ±50pt = $100/side, MNQ fee **$1.50/RT** (never $5). 2.17 resolved
trades/session at 56.7% = **+$25.8**, less ~$1.6 for 1.06 unresolved fires scratched flat
→ **≈ +$24/session**. ⚠ **Of which ~$9 is the run-entry baseline (52.8%) and ~$15 is the signal.**
⚠ A symmetric race is **not a trading harness**: perfect ±50pt bracket, no slippage, no queue.
Single-lot fills on this paper engine are clean (the 0.1% fabrication hits only lots beyond the
first), so **a single-lot forward trial is the correct next rung.**

### 2. FLAT-TOP — **PROMISING**, two conditions instead of three, and what I would actually ship

Drop the slope condition: `stall ≥ 30` **AND** depth ≤ 8 × ATR, enter WITH the run.
**3.28 fires/session.** ±50pt/120min **56.0% — +6.0pp vs 50%, +4.7pp vs control, n=600**,
day-clustered [+1.9..+9.8] **excludes 0**. OOS **55.0% / 56.7%**. Blocks +5.8/+6.5/+6.1/+7.2pp vs
control — the most uniform of any rule here. Longer targets +4.0/+1.6/+2.2pp, all spanning zero.
**The slope flip adds +0.7pp [−1.6..+2.9] — nothing measurable — and `W=15` is a number I chose by
looking at outcomes, so I would ship the two-condition version.**

### 3. ASYMMETRY OF TIME — **PROMISING.** His feature 4, and the nearest thing to independent confirmation

Fire when **≥60% of the last 30 minutes closed on the wrong side of the run's running mean**; enter
WITH the run. **3.23 fires/session.** ±50pt/120min **54.2% — +4.2pp vs 50%, +4.0pp vs control,
n=614**, day-clustered [+0.2..+7.8] **excludes 0 (barely)**. Longer targets +2.0/+1.0/+1.5pp, all
spanning zero. **It earns third place despite being weaker because it is built on *time spent*
rather than recency-of-extreme — a structurally different measurement of the same pause, and it
agrees.**

### 4. PULLBACK 4×ATR alone — **the INCUMBENT, and the reason nothing above is PROVEN**

Enter WITH the run once price is 4 × ATR off the extreme; no time condition. **3.40 fires/session.**
±50pt/120min **54.3% — +4.3pp vs 50%, +3.8pp vs control, n=621**, day-clustered [−0.2..+7.0]
**spans zero**, and **negative at every longer target.**

⚠⚠ **THE CENTRAL CAVEAT.** Paired, day-clustered, same sessions:

| | difference | 95% day-clustered | verdict |
|---|---|---|---|
| CONJUNCTION − PULLBACK | +2.5pp | [−1.6 .. +6.5] | **TIES** |
| FLAT-TOP − PULLBACK | +1.7pp | [−2.0 .. +5.8] | **TIES** |

By the `prereg_book_thinning` standard — *C must beat A; indistinguishable is REFUTED* — **the time
feature is not proven to do work that pullback DEPTH does not already do.** What tips me toward the
stall rules anyway, as a preference not a proof: the incumbent is **unstable out-of-sample
(58.1% → 51.4%)** and **flat in the EU block (−0.2pp)**, while the conjunction holds 56.8% → 56.7%
and is positive in all four blocks — *and the ablation says dropping the stall costs 3.3pp while
dropping everything else costs ~1.4pp.* **A rule that ties on the pooled mean but holds its shape
everywhere, and whose ablation points at the right condition, is the better bet. The forward trial
settles it.**

### 5. SLOPE ZERO-CROSS alone — **PARKED.** Right direction, no measurable size.

W∈{15,30,60} crossing against the run, held P∈{3,10,20} minutes, no magnitude requirement.
3.2–3.6 fires/session, edges **+1 to +4pp with every CI spanning zero.** Consistently
*continuation*, never turn. Same event the stall catches, later and noisier. **Dominated, not
refuted.**

---

## REFUTED — do not re-derive

- ⛔ **THE QUIET TURN AS A TURN ENTRY.** Entering **against** the run at a stall / slope-cross /
  asymmetry fire: **43.3%** at ±50pt/120min (n=594, the exact complement of the leader) and 44–45%
  at every other target. Not a coin — reliably **bad**. **Refuted at every parameterisation of
  every feature I built.** The clearest result in this arm.
- ⛔ **FEATURE 3, the low-efficiency continuation split.** Slope crosses zero, wait K minutes, enter
  at cross+K, bucket by the efficiency of those K minutes. **The answer flips sign with the slope
  window:** W30/K30 has low-ER beating high-ER by **+5.1 to +12.3pp**; W60/K30 has high-ER beating
  low-ER by **+3.6 to +21.5pp**. Twelve cells, neighbours in direct contradiction, n=67–312.
  **Noise — and W30/K30 is exactly the lone standout a 560-cell search manufactures.**
- ⛔ **DEEP STALLS / DEEP PULLBACKS.** Stall ≥30min but price **more** than 8 × ATR off the extreme:
  **−0.0 / −3.0 / −4.2 / −2.7pp.** Pullback 8×ATR and 10×ATR alone: −2.6 to −4.4pp. **Buying a deep
  dip in a run loses on this tape** — the edge lives entirely in the SHALLOW stall.
- ⛔ **THE LONGER HORIZON DOES NOT HELP.** The brief asked explicitly. ±150pt at 240min: **+2.0pp vs
  50%, +1.0pp vs control [−5.0..+7.2]**, against +6.7/+6.4pp at ±50pt/120min. **A grinding move
  does not need more time or a bigger target to express this edge — it expresses it at 50pt or not
  at all.**
- ⛔ **STALL N45.** +1.3pp [−2.9..+5.5], OOS first half 50.2%, while N30 (+4.6) and N60 (+2.5)
  straddle it. **Non-monotonic in N** — see §CAVEATS.
- ⛔ **A BARE STALL AS A TURN TRIGGER.** Confirmed independently by arm 2 (raced 49.2%, a coin; and
  a stall's volume signature does not separate a turn from a pause, 0.819 vs 0.836, CI
  [−0.043,+0.011]). **Arm 2's advice — *pair it* — produced this arm's leader.**

---

## METHOD — and the six things that nearly went wrong

**1. ⚠⚠⚠ THREE SHARED-LOADER BUGS WERE REPORTED MID-STUDY AND EVERYTHING WAS RE-DERIVED.**

- **The race tested `fav` before `adv`**, so a bar clearing BOTH targets scored a **win** — a
  one-way bias *toward finding edges that are not there*, and most dangerous for an arm whose
  features fire on quiet tape where one wide bar decides the race. **FIXED:** such a bar is
  ambiguous (OHLC cannot order the touches) and is **excluded**. **Exclusions: 9 at ±50pt/120min,
  0 at every other cell** — negligible, *because of §2*.
- **`bars` read with no `timeframe` filter** (`1day` median range 310.8pt). **Never reached my
  numbers** — I wrote an independent loader filtered to minute-or-finer from the start. **But
  filtering was not enough; see §2.**
- **`CAST` rounds, it does not floor**, putting the shared loader's session anchor half a day off
  22:00Z. **My loader used `//`, which floors — and I verified it empirically rather than assuming:
  first-bar hours came out 22/23/00 and last-bar hours 20/21 across all 273 sessions.**
- **One matched control is not a control** (draw-SD is the size of the edges). **FIXED:** every
  control here is the mean of **20 independent draws** with the spread printed.

**2. ⚠⚠ MY OWN BUG, AND THE WORST ONE — found by auditing my own bars rather than trusting them.**
V1 filtered to the three minute-or-finer timeframes and then took `MAX(high)/MIN(low)` over their
**union**. `1min` is the 08-18 backfill (`src=lake`) and `1m` is the V5 archive (`src=v5`), and
**on 2026-06-17/18 they disagree by up to 498 points** — so the union fabricated **5,155 minutes
with a ≥100pt range, worst 508pt.** Verified pairwise before fixing: 5s vs 1min on 57,710
overlapping minutes is median 0.0 / p90 |diff| 0.0 (same series, matching arm 2's 57,712); 5s vs
V5 1m median 0.0 / max 15.8; **V5 1m vs lake 1min median 0.0 but max +498.3** — a cluster of bad
backfill bars (172 `1min` and 46 `1m` rows have an own range ≥100pt). **FIX: ONE dominant timeframe
per session (prefer 5s, else 1min), never a union, plus a per-bar sanity cap.** Minutes with a
≥100pt range fall from **5,155 to 46**, and those 46 are real event minutes (max 160.5pt).
**This is [[the-labs-tape-is-not-productions-tape]] in a new costume, and no `timeframe` filter
alone would have caught it — it took comparing the sources to each other.**

**3. "616 session-days from 2024-09-23" is the BACKFILL, not intraday tape.** Only `5s` (92 days),
`1min` (291) and `1m` (28) are minute-or-finer; `1day` and `1hour` (483 days each) are the 08-18
backfill. **273 sessions carry ≥300 one-minute bars, 2025-09-14 → 2026-10-01.** The 291 `1min` days
is the figure `leg_survival` reports for REFCLASS — the cross-check that the filter is right.
I never touched `volume`, so arm 2's double-count cannot reach any number here.

**4. BOTH BASELINES, AND WHY THEY COINCIDE HERE.** At a symmetric race a random-**side** control is
pinned to ~50% by construction (long wins iff short loses) — and that is exactly what every control
in this arm measured: **48–52%**. So the drift the tape carried (**+5,159pt** summed session
close-to-close) does not inflate a control; it would show up as *the rule* scoring above 50 for
being long. **This arm's rules are side-balanced 51–53% long because the 15×ATR latch alternates
direction, so the two baselines differ by only ~0.3pp** (+6.7 vs 50%, +6.4 vs side-matched) —
unlike arm 1, which lost 85% of its edge to side-matching. **I am claiming the side-matched number;
the tradeable number happens to be the same.**

**5. THE CONTROL HAD TO BE CHOSEN, AND TWO CANDIDATES DISAGREED BY 4pp.** A control from the **same
session and same block** with the same side put the US-cash edge at **+2.3pp**; the arbiter puts it
at **+6.0pp**. The same-block control scores **50.9–55.5% on its own**, far above an unconditional
draw's 50.4%, because it is **over-conditioned**: asking *"given this session-block went up, does a
long at a random minute inside it win?"* borrows the block's realised drift and deletes the signal
with the artifact. That is [[a-drift-baseline-must-be-unconditional]], where a session-conditioned
control once invented +11.25pt of bull drift against a true +1.3–1.8pt. **The arbiter — same clock
minute, same side, DIFFERENT random session — matches time-of-day and the long/short mix without
conditioning on the session's own outcome, and it is what every headline uses.**

**6. THE LEG DEFINITION HAD TO BE CHOSEN TOO, AND THE FIRST CHOICE FAILED IN THE OPEN.**
`leg_watch`'s open rule used as a direction *latch* gives **87.9 flips/session**, median run 5
minutes and 1.2 ATR — noise, because 8 minutes of random walk clears 1×ATR in both directions
routinely, and at that scale a 30-minute stall does not exist to be detected. Equally, a stall rule
*inside* a `leg_watch` leg is impossible: **the median time from the extreme to its 3×ATR death is
11 minutes**, so no N above ~15 can ever fire. `turn_watch`'s 15×ATR latch both survives and is
already measured here — and my re-derivation reproduces its published rates (**3.71 / 4.66 / 10.16
vs published 3.6 / 5.3 / 13.3** at 15× / 12× / 7×ATR).

**7. A SYMMETRIC RACE CONDITIONS ON THE FUTURE WHEN IT DOES NOT RESOLVE.** Unresolved races are
dropped from rule and control alike; resolution is **67% at 50pt/120min, 34% at 100pt, 18% at
150pt/120min, 32% at 150pt/240min.** At 150pt **four fires in five are discarded by future price
action.** Not a look-ahead in the *entry* — no feature reads a bar beyond its own minute — but it
is why **the verdict rests on the 50pt cell.**

### The search, charged

**~560 scored cells** (240 arms×targets×sides · 64 three-control · 48 arm C · 76 pullback/flat-top/
deep · 12 paired · 36 side-matched · 32 clean re-run · ~25 arbiter/blocks · 26 shift+ablation). A
further ~170 combinations were swept for **fire rate only, deliberately before any outcome was
computed**, so the 3–6/session band was settled in the dark. Binomial noise is ±4pp at n=600 and
±8pp at n=150; **the day-clustered intervals above are wider than both**, because minutes inside a
session are not independent draws.

### ⚠ THE CAVEATS THAT STOP THIS BEING "PROVEN"

1. **The time feature does not provably beat the depth feature** (+2.5pp [−1.6..+6.5]). The
   *mechanism* may be right while its *marginal* contribution over a plain pullback is unmeasurable
   at this n. **The one thing a forward trial must answer.**
2. **~40% of the headline is the run-entry baseline.** Being with the run from its first eligible
   minute already scores +2.8pp. The quiet-turn feature adds +2.5pp and the remaining conditions
   +1.4pp. **Quote +6.7pp only with that decomposition attached.**
3. **⚠ THE PARAMETERS WERE SELECTED ON THE CONTAMINATED TAPE.** N=30, depth ≤8×ATR and W=15 were
   chosen before I found the 1m/1min union fault, then *confirmed* on clean tape. The confirmation
   reproduces the ranking — **but it is not independent, and the forward run is the first honest
   out-of-sample test of these numbers.**
4. **Non-monotonic in N** (N15 +3.2, N30 +4.6, **N45 +1.3**, N60 +2.5). The *sign* is consistent
   across every N, every arm and both OOS halves — that is what carries it — but **N=30's magnitude
   is an optimistic pick.** Expect **+2 to +4pp** forward, not +6.
5. **Only one of four targets survives.** A result living at exactly one horizon is on probation.
6. **The ceiling warning applies.** Arm 1 measured the operator's own 187 presses at **+0.2pp at
   ±50pt side-matched** — his entries are a coin. **A rule scoring +6.4pp is far above that
   ceiling, which is itself grounds for suspicion.** My defence is the shift scan: a window artefact
   would be *flat* across forward shifts, and this decays monotonically to +1.0pp by +60min. That is
   evidence, not proof.
7. **1.00 of 3.23 fires a session land in ASIA, which is permanently benched by policy** (shadow
   n=1840 at −$3.17/trade) and must be excluded from any expectancy the desk banks. **US cash hours
   carry only ~0.75 fires/session.**
8. **I did not use the tick tape.** A stall is a price-and-clock feature; arm 2 has since shown a
   stall's volume signature does not separate a turn from a pause, consistent with the stall not
   being a turn signal at all.

---

## WHAT I WOULD DO NEXT, BEST FIRST

1. ★★★ **FIRE A QUIET-TURN DETECTOR WHERE HIS CLAIMS FIRE.** Arm 1 found claim-reverse at extension
   scoring **+19.9pp [+11.0, +31.2]** side-matched at 6.1 fires/session, LOSO-stable +18 to +25pp —
   **two to three times anything in this report** — but it needs him to press, so it is not yet a
   detector. **My run tracker already provides the missing half: extension in ATR off a latched
   run's extreme, computed causally every minute.** Join the 187 captured presses to the run state
   at the press and ask what the *tape* looked like when he claimed while extended. **That is the
   highest-value thing available tonight and it is squarely in this arm's family.**
2. **Shadow FLAT-TOP (two conditions, not three) at single lot**, scored **per session block with
   Asia excluded**, pre-registered at a **+2 to +4pp** expectation — not +6pp — then frozen. A
   changed level restarts the count.
3. **Run the conjunction-vs-pullback comparison forward.** It decides whether "the stall" is a real
   feature or a re-description of "the dip".
4. **Re-ask the TURN side with a payoff model, not a symmetric race.** The turn side is 43.3% on a
   symmetric race — but a turn entry's payoff may be asymmetric (small stop, large target) in a way
   a symmetric race *cannot see*, and
   [[payoff-asymmetry-is-the-only-thing-a-hit-rate-hides]] says classify the payoff *before*
   concluding. **I did not do that, and it is the one way his original hypothesis is still alive.**
5. **Change the yardstick for turn detectors.** The measurement that should redirect effort is not
   the split — it is that the shipped 15×ATR detector confirms within 30 minutes on **7.9%** of
   turns and is **70% of the move late** on the rest. **Judge the next one on LATENCY AGAINST A
   HINDSIGHT EXTREME.**
6. ⚠ **Do not ship rule 1 as a "turn" alert in any form.** It fires at a turn-shaped moment and
   means **the opposite**. An instrument whose name inverts its content is the `tunnel_watch`
   failure waiting to happen again.
