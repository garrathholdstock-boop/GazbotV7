# ARM 2 — VOLUME AND PARTICIPATION AT THE TURNS

**MNQ · 328 session-days of bars (2025-09-14 → 2026-10-02) + 74 tick-days · read-only · 2026-10-02**

Verdict standard, identical to the other three arms: fire **3–6 times/session**; symmetric race
(**+N before −N on bar highs/lows within 120 min**) at **N = 50 and 100**; scored against a
**matched random control**; 50% IS ZERO; day-clustered CIs; cells counted.

---

## HEADLINE

**One rule clears the bar, and it is not the one the arm was built to test.**

Volume's relationship to turns is real but weak and mostly *confirmatory*. What survives is a
**conjunction**: a mature leg whose successive new extremes are being made on *shrinking* volume,
*and* which is currently printing several consecutive below-average minutes at its extreme — entered
**WITH** the move. **62.0% vs 52.9% on a side-matched control at ±50pt (+9.1pp, 95% day-clustered CI
[+3.7, +14.4], n=637), 3.16 fires/session.** It is **PROMISING, not proven** (see the four charges
against it), and it works at **±50pt only** — the ±100pt result is carried entirely by one half of
the tape.

**Three things were REFUTED outright**, and one of them was my own interim result:

1. **The climax-volume reversal is dead.** Every cell sits in control noise (−1.1 to +1.7pp).
2. **A stall's volume signature does not distinguish a turn from a pause.** 0.819 vs 0.836 of
   trailing mean, CI [−0.043, +0.011]; the stall itself is a coin (49.2% turned).
3. **⚠ The single-family participation-fade arms were a DRIFT ARTEFACT.** They scored +5.8 to
   +7.6pp against the brief's random-**side** control and collapse to **+2.0 / +2.2pp against a
   side-matched control**. The tape rose +5,712pt over these 328 sessions and those rules fire
   long about twice as often as short. **I would have shipped a shortlist of drift had I not run
   that test** ([[a-drift-baseline-must-be-unconditional]]). Every number below is therefore quoted
   against the side-matched control as well.

---

## ★ THE OPERATOR'S QUESTION, ANSWERED FIRST

> *"the turns are not violent. they often just change direction. sometimes its violent. but more
> often than not it can just start grinding in that direction."*

**He is right, and here is the number.** Turns defined structurally and **non-causally** (close is
the extreme of ±90 min *and* both legs ≥60pt, 30-min dedupe) → **1,298 turns, 3.96/session**, the
same order as the desk's own 3.1 real legs/day, which is the sanity check on the definition.

Peak 1-min volume z-score (vs trailing 60 min) in the ±5 min window around each turn:

| volume at the turn | share of turns | share at RANDOM minutes | enrichment |
|---|---|---|---|
| **QUIET** z < 1 | **22.5%** | 46.9% | 0.48× |
| ORDINARY 1 ≤ z < 2 | 22.9% | 24.6% | 0.93× |
| ELEVATED 2 ≤ z < 3 | 19.4% | 12.7% | 1.53× |
| CLIMACTIC 3 ≤ z < 5 | 18.3% | 9.4% | 1.95× |
| **VIOLENT** z ≥ 5 | **16.9%** | 6.4% | 2.64× |

median peak z **2.17 at a turn vs 1.12 at a random minute**.

**So: climax volume is genuinely enriched at turns — 35.2% of turns carry z ≥ 3 against a 15.8%
base rate, a 2.2× lift — and that is still a MINORITY of turns. 64.8% of turns are not climactic
and 22.5% are outright quiet.** A violence detector can therefore address at most about a third of
the problem *even if it were perfect*, and it is nowhere near perfect:

| detector | episodes/session | % landing within 15 min of a turn |
|---|---|---|
| volume z ≥ 3 | 11.26 | **15.1%** |
| volume z ≥ 4 | 8.07 | **17.3%** |
| volume z ≥ 5 | 5.85 | **18.2%** |

against a turn base rate of 3.96/session (turn-adjacent minutes are ~8.5% of the session, so the
lift is ~2×, and **four of every five climax fires are not a turn**). That is the quantitative
version of his correction, and it is why the shortlist below is built on the *quiet* side.

---

## ★★★ RANKED SHORTLIST — best first

### 1. `VOLFADE_AND_DECAY` (k4 / 0.65 / 90min × N5 / 0.90 / 1.0ATR / 120min, coincidence 30min) — **PROMISING**

**Fires 3.16/session.**

| target | rule | random-side control | **side-matched control** | edge (side-matched) | n | resolved |
|---|---|---|---|---|---|---|
| ±50pt | **62.0%** | 51.4% | 52.9% | **+9.1pp** CI95 [+3.7, +14.4] | 637 | 61% |
| ±100pt | 58.2% | 54.6% | 51.0% | +7.1pp *(H1 −0.4 / H2 +15.2 — NOT established)* | 275 | 27% |

Both halves of the tape agree at ±50pt: **H1 +8.0pp** (n=256), **H2 +10.5pp** (n=381). Both *sides*
agree: **LONG +10.1pp** (n=432), **SHORT +7.3pp** (n=205) — which is what kills the drift
explanation. Against the stricter **hour-matched** control (random minute within ±90 min of the
fire) the edge is **+13.4pp**.

**The rule, precisely.** Per-minute bars (close/high/low/volume), session anchored 22:00Z.
- `hi60[i]`, `lo60[i]` = trailing 60-minute max/min of **close**. A *new extreme* at `i` is
  `close[i] >= hi60[i] > lo60[i]` (direction `+1`) or `close[i] <= lo60[i] < hi60[i]` (`−1`).
  Maintain the list of a leg's new-extreme indices; **reset the list whenever the direction flips**.
- **Condition A — volume decay across successive extremes.** At a new extreme at `i`, take that
  leg's extremes within **90 minutes** of `i`; require at least **4**. With `h = max(2, len//2)`:
  `early = mean(volume)` of the first `h`, `late = mean(volume)` of the last `h`. **A fires when
  `late <= 0.65 * early`.**
- **Condition B — sustained fade at the extreme.** `volume[i] <= 0.90 * mean(volume[i-60 .. i-1])`
  for **5 consecutive minutes**, AND `close[i] >= hi120[i] - 1.0*ATR14[i]` (up case; mirrored for
  down), where `hi120`/`lo120` are the trailing **120**-minute close extremes.
- **FIRE** at B's minute, direction **= the direction of the extreme (WITH the move)**, provided an
  A-fire occurred within **±30 minutes**. **Cooldown 30 min.**
- ⚠ The trailing volume mean **excludes the current minute** — including a spike in its own
  baseline halves the number the threshold is supposed to mean.

**Mechanism, one sentence:** it selects a leg that has kept making new extremes while participation
drained away — nobody is on the other side, so the grind continues rather than turns.

**In his units:** at ±50pt and 62.0%, one MNQ lot is `(2×0.62−1) × 50pt × $2 = $24.0` per resolved
trade less the **$1.50/RT** venue fee = **$22.5**; 61% of fires resolve inside 2h, so **≈ $13.8 per
fire × 3.16 fires = ≈ $44/session at ONE LOT** (≈$35/session measured as the excess over the
side-matched control). ⚠ **That figure assumes a ±50pt bracket this desk does not currently run,
and treats the 39% unresolved as scratches, which is optimistic** — an unresolved fire is a live
position, not a flat one.

### 2. `VOLFADE_AND_DECAY` — strict sibling (k**5**, coincidence 30min) — **PROMISING**

**2.96 fires/session** (marginally under the 3-fire bar). ±50pt **63.2% vs 52.1% side-matched
= +11.1pp** CI95 [+5.8, +16.6], n=600; H1 +7.1 / H2 +12.9. ±100pt +8.1pp (H1 −4.2 / H2 +20.1).
Identical rule, **≥5** leg extremes instead of ≥4. Same mechanism, one notch stricter.

### 3. `VOLFADE_AND_DECAY` — tightest point (k5, coincidence **15**min) — **PROMISING but under-fires**

**2.01 fires/session**, below the bar. ±50pt **66.6% vs 55.9% side-matched = +10.7pp**, n=395;
LONG +12.1 / SHORT +7.5. Listed because it is the end of the **dose–response curve**, which is the
best single piece of evidence that the family is not a lucky cell: tightening the conjunction moves
the random-side edge monotonically across six cells — **+5.4 → +10.6 → +11.1 → +14.9 → +18.5 →
+24.1pp** as fires fall **4.50 → 3.16 → 2.96 → 2.01 → 1.69 → 1.31/session**. A noise cell does not
do that.

### 4. `AGGRESSION_CONFIRM` — one-sided aggression at a trailing extreme — **PARKED, under-powered**

74 tick sessions only. `buy_share = buy size / total size` over the trailing 15 min; at a trailing
**60**-min close extreme, fire **WITH** the move when `buy_share >= 0.55` at a high (`<= 0.45` at a
low). **4.14 fires/session.** ±50pt **56.1% vs 50.0% random-side = +6.1pp (n=214)**; ±100pt 54.0%
vs 47.4% = +6.6pp (n=87). Its **price-only twin** (same extreme, no aggression filter) scores
+1.8pp at 19.4 fires/session, so the aggression filter is doing the work. **But:** against the
hour-matched control it is only **+1.1pp**, n is 3× smaller than every bar arm, and it has **not**
been side-matched. Park it; it is the natural thing to re-run when the tick lake reaches ~200
sessions. ⚠ Its mirror (`exhaust`: same fire, entered *against* the move) is **−5.6 / −10.2pp** —
the exhaustion reading of one-sided aggression is wrong, consistent with the desk's existing finding
that CVD at a turn is one-sided in the direction that is **ending**.

### 5. `STALL_N20_R080` — the best of the price-stall family — **INSIDE NOISE**

Price made a trailing-60 extreme, then no new extreme for 20 min, with stall volume ≤0.80× its
trailing mean; fire opposite. **4.12/session**, ±50pt 52.0% vs 48.9% = **+3.1pp** (n=798, CI
[−2.0, +8.1]), ±100pt +2.0pp. Ranked last because it is the only *reversal* rule in the whole arm
that is not negative, and because its fire rate is right. There is no evidence for it.

---

## REFUTED — do not re-derive

| hypothesis | cells | result |
|---|---|---|
| **Climax volume at a price extreme → REVERSE** | Z 2.5/3/4/5 × W 60/120 | **−1.1 to +1.7pp** at 3.85–5.46 fires/session. Flat dead, at every threshold, both targets. |
| Climax volume at an extreme → CONTINUE | Z5 W120 | −1.3pp. The *climax* carries no direction either way. |
| **Time-of-day relative volume** (expanding prior-sessions profile, 30-min buckets) at an extreme | X 2/3/4 × W 60/120 | **−2.2 to −4.3pp.** Judging an 07:00 spike against other 07:00s changed nothing. |
| Climax **then** volume collapse (2-stage) | Z3/Z4 × R 0.6/0.8 | +1.4pp at 3.29/session. Inside noise. |
| **Participation fade / extreme-volume decay as STANDALONE rules** | 9 arms | **+2.0 / +2.2pp side-matched.** Their +5.8 to +7.6pp against a random-**side** control was the tape's +5,712pt drift. Only the conjunction survives. |
| Participation collapse (15-min rate ≤ R × 120-min rate) at an extreme → reverse | R 0.5/0.6/0.7 × W 60/120 | −3.6 to +3.2pp. Inside noise. |
| **The stall's volume signature separates a turn from a pause** | 831 stalls | **NO.** turned 0.819 × trailing mean vs resumed 0.836; difference −0.017, CI95 day-clustered **[−0.043, +0.011]**. Second-half/first-half volume within the stall: 0.757 vs 0.751 — identical. And the event is a coin: **49.2% turned / 50.8% resumed.** |
| Volume-confirmed displacement (≥M×ATR over 15 min with volume z ≥ Z) → continue | M 2–6 × Z 2–4 | +1.9 to +2.9pp at 3.49–4.94/session; not side-matched, so probably drift. |

---

## METHOD, AND THE TRAPS THIS WAS BUILT AGAINST

- **The verdict is reused, not reimplemented.** `scripts/entry_cvd_climax.py`'s `race()` is the
  verdict for every bar arm. The tick arm needed a wider row tuple, so `race_any()` indexes instead
  of unpacking — and it was **asserted equal to `race()` on 20,000 random draws, 0 disagreements**
  before use. Two implementations of one verdict that silently disagree is the bug this prevents.
- **⚠ `bars` MIXES TIMEFRAMES for the same symbol and minute** — 5s, 1min, 1m, 3m, 5m, 5mins, 1hour
  and 1day all live in that table. `MAX(high)/MIN(low)` survives it; **`SUM(volume)` does not** —
  the 5s rows and the 1min rows describe the **same trades** (measured on 57,712 overlapping
  minutes: 5s-summed 1997.6 vs 1min 1999.4, corr 0.964). So **one dominant intraday timeframe per
  session, chosen by row count, ≥300 rows**: 328 sessions survive (236 `1min`-dominated, 92 `5s`).
  A naive `SUM(volume)` over the raw table would have doubled volume on every session that has both.
- **⚠ The timeframe change is confounded with calendar time, and was prised apart.** The edge is
  **+5.9pp on `1min` sessions and +6.2pp on `5s` sessions** — so it is *not* a measurement artefact.
  But it *does* trend: by quarter, +0.9 → +3.7 → +9.5 → +10.1pp (2025Q4 → 2026Q3), with 2026Q2
  (65 of 76 sessions still `1min`) already at +9.5. **Time, not tooling.** This is the single biggest
  reason the rule is PROMISING and not PROVEN: it is strongest in the most recent tape.
- **DuckDB `/` is FLOAT.** Every bucket uses `CAST(x/60 AS INT)`, never `(x/60)*60`.
  ⚠ `minute` is a reserved word in this DuckDB — the tick query uses `mnt`.
- **`aggressor` is lowercase** (`'buy'`/`'sell'`); comparing to `'BUY'` returns 0 rows and reads as
  a clean null.
- **No future bar, ever.** "At the extreme" always means *close[i] is the trailing-W high-water
  mark*, never a future-confirmed pivot. The only non-causal code in this report is the ±90-min turn
  definition in the SPLIT section, which is a **measuring stick and is never an entry rule** — it is
  labelled as such at its definition.
- **The grid is dense per minute.** A minute with no bar is price-flat with volume 0, so index ==
  minute offset and the 120-min race window really is 120 minutes. A flat minute cannot win a race,
  which is the conservative direction. 4.0% of minutes are filled this way.
- **Parameters were fixed on COUNT ONLY.** 132 calibration cells were run to land fire rates in the
  3–6 band; a fire count carries no information about direction, so this is not outcome tuning.
- **Cooldown 30 min on every arm.** Without it a volume rule fires in bursts — a climax minute sits
  next to other heavy minutes, one event is counted ten times, and the fires/session bar fails for a
  reason that has nothing to do with the signal.
- **Three controls, not one.** (i) the brief's: same count, same session, random minute, **random
  side**; (ii) **hour-matched**: random minute within ±90 min of the fire, random side — because a
  volume rule is heavily time-of-day confounded; (iii) **side-matched**: same side as the fire,
  random minute — the one that mattered.
- **Day-clustered bootstrap (2,000 resamples of SESSIONS)** on every headline edge. Minutes inside a
  session are not independent draws; a per-observation interval here is inflated ~10×.
- **US-cash vs outside:** the headline family is **not** a US-open artefact — `CONT_decay_k5` scores
  +8.9pp inside 13:30–20:00Z (1.28 fires/session) and +5.3pp outside it (3.45/session).

### THE SEARCH, CHARGED

**≈220 outcome-bearing cells** (a race computed): 52 reversal arms × targets, 28 flipped, 24
stability, 20 timeframe/quarter, 32 tick, 36 AND-conjunction × subsets, 10 side-matched, 12 headline
splits. Plus **132 count-only calibration cells** and 3 descriptive diagnostics that read no race.
At that cell count a lone +11pp standout would be unremarkable. What makes the AND family worth
trialling is **four independent agreements**, not its point estimate: the monotone dose–response
across six strictness cells, sign consistency in **both halves** of the tape, sign consistency on
**both sides**, and survival of the **side-matched** control that killed its own components.

### FOUR CHARGES AGAINST THE HEADLINE RULE — read before trialling

1. **The SIDE was chosen post-hoc.** The reversal arms were built first and came back consistently
   *negative*; the continuation reading is the flip of that. It is a binary a-priori choice rather
   than a tuned parameter, and five cells across three families agreed in sign — but it doubles the
   search and it is in-sample.
2. **The COMPOSITION was chosen post-hoc.** Which two families to AND was decided after seeing which
   two scored best.
3. **It is ±50pt only.** The ±100pt edge is +7.1pp overall but **−0.4pp in the first half of the
   tape and +15.2pp in the second**. Treat ±100pt as unmeasured.
4. **It is strongest in the newest tape.** The quarterly ramp (+0.9 → +10.1pp) is either a regime
   that has arrived or a regime that will leave.

**What that means for the next step:** this belongs in **shadow on a pre-registered forward run**,
with the rule, the ±50pt target, the 3.16-fires/session expectation and the +9.1pp side-matched edge
**frozen in writing before the first fire** — and the side-matched control run alongside it, not
instead of it. It does **not** belong on a live gate, and nothing in this report authorises an order
path.

---

## FILES

Harnesses (working scripts, read-only, no service touched, nothing written to `gazbot7.db` or
`capture.db`): `scratch/arm2_lib.py` (loader, ATR, volume stats, expanding time-of-day profile,
verified `race_any`), `scratch/arm2_signals.py` (the eight signal families), `scratch/arm2_eval.py`
(race + three controls + day-clustered bootstrap), `scratch/arm2_calib.py` · `arm2_calib2.py`
(count-only calibration), `arm2_flip.py`, `arm2_stab.py`, `arm2_tf.py`, `arm2_split.py`,
`arm2_diag.py`, `arm2_ticks.py`, `arm2_final.py`, `arm2_and.py`, `arm2_side.py`, `arm2_head.py`.
