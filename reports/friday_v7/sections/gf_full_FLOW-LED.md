# GREENFIELD HUNT — census `full` · cluster **FLOW-LED**

**Run:** 2026-08-08 · MNQ · `data/capture.db` (5s bars + aggressor ticks + L2) · tick-honest, **net $5/round-trip**
**Working files:** `scratchpad/gf_flowled/` (`load.py`, `frame2.py`, `engine.py`, `fast.py`, `sig.py`, `bt.py`, `alt.py`)
**Brief:** ignore the existing gates, invent a brand-new entry signal to catch the FLOW-LED sat-out runs.

---

## 0. THE HEADLINE, IN PLAIN ENGLISH

I could not build a signal that catches the FLOW-LED runs, and I now believe the reason is that
**"FLOW-LED" is not a real family of runs — it is a labelling accident.** The census hangs the label on
*one minute* of aggressor flow just before the run. When you go and look at that minute on the tape, the
flow is not a lead — it is noise that happened to point the right way, and it points the other way again
the very next minute. There is nothing there to trigger on.

What the hunt *did* find, while digging, is two genuinely tradeable footprints that live in the same
flow data. Neither of them catches a single FLOW-LED run, so neither is an answer to the question I was
asked — but both beat their nulls at p<0.01 and both belong in the shadow book.

| what | verdict | one line |
|---|---|---|
| **FLOW-LED as a tradeable family** | **REFUTED** | catch-rate and profit move in *opposite* directions — the more of the cluster you catch, the more you lose |
| **A — FLOW-BREAK IGNITION** (the signal I invented for this cluster) | **SHADOW** | +$1,830 / n=39 / 56.4% / p=0.002 vs random-time null, but **0/4** on the target runs and its OOS leg collapses |
| **D — FLOW-TRAP FADE** (spin-off) | **SHADOW — the better one** | +$1,870 / n=44 / 54.5% / **all five days green**, LOO stable, OOS holds — but also **0/4** on target |

---

## 1. THE TARGET SET — and the hard n-ceiling that governs everything below

### 1.1 The cluster is n=2

`census_summary.json` (7 days, 67 runs ≥1.5×ATR, 54 sat out) splits the runs into
UNCLASS 33 / OPEN-NEWS 24 / VACUUM 8 / **FLOW-LED 2**. Both FLOW-LED runs sat out, so at census level
`full` the target set is **two runs**:

| # | time UTC | dir | move | 1-lot ceiling | flow60 | amp% | book |
|---|---|---|---|---|---|---|---|
| 1 | 08-04 01:40 | UP | +128pt | $256 | +222 | 0.10 | 0.49 |
| 2 | 08-05 08:07 | DN | −74pt | $148 | −152 | 0.07 | 0.51 |

I re-derived the census independently on the tick era rather than inherit it (`scratchpad/gf_flowled/pop.py`).
62 big runs, and my FLOW-LED set is **3**: `08-05 08:07 −74`, `08-06 12:52 −68`, `08-07 19:43 +74`.
It overlaps the census on one run only — the labels are not stable to a bucket-alignment change, which is
itself a warning about the label. I score against the **union of 4** and also report the strict census 2.

**Note the sizes.** The FLOW-LED runs are −68, −74, +74, +128. The week's big money — +250, +210, +176,
+165, −172, −154 — is *all* in UNCLASS / OPEN-NEWS / VACUUM. Even a perfect FLOW-LED catcher is chasing
the small end of the tape.

### 1.2 Flow only exists for 5 days, and there is no way around it

`capture.db` keeps **5 trading days of ticks** (08-03..08-07) against **17 days of 5s bars**. Every
FLOW-LED idea needs aggressor sign, so every number below rests on 5 days. I tried hard to extend it —
four different bar-derived proxies for net aggressor flow, validated on the 6,779 overlapping minutes:

| proxy | corr vs true net-aggressor | sign agreement |
|---|---|---|
| `sign(close−open) × volume` | 0.212 | 53.1% |
| `((c−l)−(h−c))/range × volume` | 0.188 | 49.9% |
| `(c−o)/range × volume` | **0.272** | 52.2% |
| tick-rule on consecutive 5s closes | 0.210 | 53.4% |

Total volume reconstructs perfectly (corr 0.960, ratio 1.0000) — the *sign* does not. A 52% sign
agreement is a coin flip. **The bar tape cannot stand in for the tick tape, so the flow work is hard-capped
at 5 days.** Per the disposition doctrine, thin n can never be REFUTED — which is exactly why A and D
below land on SHADOW and not on a verdict.

---

## 2. WHY THE LABEL IS AN ACCIDENT — the tape at the four target runs

This is the single most important table in the section. It is the minute-by-minute tape either side of
each target run: net aggressor flow, its z-score against the trailing 2h, how many consecutive minutes
the flow has held one sign (`per`), and whether price had broken its 30-minute range.

```
=== 08-05 08:07  DN −74pt  (dead-chop, R15=35, ER=0.11) ===
   min      px     flow     fz   per   brkDN
    -2  29920.0     +43  +0.56    +1     .
    -1  29915.8      -9  +0.08    -1     .
    +0  29908.5    -209  -1.75    -2     .    <- the minute that earns the FLOW-LED label
    +1  29899.8    +139  +1.42    +1     .    <- flow flips to +1.42 while price keeps falling
    +2  29889.0    -195  -1.59    -1     .
    +3  29881.5    -111  -0.82    -2     Y    <- price only confirms here, 3 min and ~27pt late

=== 08-06 12:52  DN −68pt  (building, R15=46) ===
    -1  29420.2     +36  +0.13    +7     .    <- flow had been POSITIVE 7 minutes running
    +0  29426.5    -273  -1.87    -1     .    <- one minute, sign flips, label assigned
    +1  29426.8     +12  -0.02    +1     .    <- and flips straight back
    +3  29403.5     +61  +0.29    +3     Y

=== 08-07 19:43  UP +74pt  (building, R15=40) ===
    -1  29790.0    -194  -0.77    -2     .
    +0  29781.2    +302  +1.17    +1     .    <- label minute
    +1  29779.8    -252  -1.00    -1     .    <- immediately reverses
    +2  29788.2     -21  -0.10    -2     .

=== 08-04 01:40  UP +132pt  (building, R15=61) ===
    +0  28906.5     -74  -0.37    -2     .    <- flow is NEGATIVE at the start of a +132pt UP run
```

Three things fall straight out of this, and they close the assignment:

1. **There is no persistence to trigger on.** At every one of the four run starts, the flow's run-length
   is 1 or 2 minutes and it reverses sign on the very next bar. A "sustained one-sided aggression"
   trigger — the only mechanically sensible reading of "flow-led" — cannot fire here, because the
   sustained aggression does not exist.
2. **On 08-04 the flow is pointing the wrong way entirely.** A +132pt up-run starts on a −74 flow minute.
   The census called it FLOW-LED; my re-derivation called it UNCLASS. The label is a coin toss.
3. **Price confirms 3–5 minutes and 25–45% of the move late.** The 30-min range break arrives at +3/+4/+5.
   This is the desk's detection-latency finding re-derived from a different direction and on a different
   statistic — anything that waits for price is buying the back half of the run.

**Generalised, over all 62 big runs.** I measured every feature at run-start against every control minute
(`scratchpad/gf_flowled/foot.py`), sign-aligned to the run direction. The median run does **not** start
with flow behind it — it starts with flow *against* it:

| feature at run start, aligned to the run's direction | median at run start | median on all minutes |
|---|---|---|
| 1-min flow imbalance | **−0.016** | ±0.078 |
| 3-min net aggressor | **−100 contracts** | ±152 |
| 1-min price displacement | **−3.25pt** | ±4.5 |
| flow persistence (signed run-length) | **−1** | ±1 |
| 15-min range (R15) | 66pt | 43pt |
| volume z-score | **+0.25** | −0.21 |

Big MNQ runs begin **against** the aggressor flow, out of a volume expansion, after a counter-move. That
is the *opposite* of the FLOW-LED premise, and it is what pointed the hunt at candidate D.

---

## 3. THE SIGNALS — exact mechanical specs

### 3.1 CANDIDATE A — **FLOW-BREAK IGNITION (FBI)** — the signal invented for this cluster

The strongest honest reading of "flow-led": don't trigger on one minute of flow, trigger on flow that has
*held one side* for a while and has *already pushed price out of its range* — the book in front of the
move has been eaten.

> **Evaluated once per minute, on closed data only.**
>
> 1. `net60(t)` = Σ(buy-initiated size) − Σ(sell-initiated size) over minute t, from `capture.db.ticks.aggressor`.
> 2. `fz(t)` = (`net60(t)` − mean) / sd of the **previous 120** `net60` values, strictly prior. Need ≥30
>    non-null buckets and sd>0, else no signal.
> 3. `persist(t)` = signed count of consecutive minutes ending at t whose `net60` shares the current sign.
> 4. `HH30/LL30` = highest high / lowest low of the **previous 30 minutes, excluding minute t** (1-min bars from 5s).
> 5. `R15(t)` = high−low over the last 15 minutes (the ATR unit; tape median 43pt).
>
> **TRIGGER LONG** — `fz ≥ +2.0` **AND** `persist ≥ +2` **AND** `close(t) > HH30`
> **TRIGGER SHORT** — `fz ≤ −2.0` **AND** `persist ≤ −2` **AND** `close(t) < LL30`
>
> **ENTRY** — market, first tick ≥1s after the minute close (measured fill lag 1.33s; slippage vs the
> signal-minute close was **+0.245pt** in the trade's own direction — i.e. you pay it, no look-ahead).
> **STOP** — `0.75 × R15`, floor 6pt (≈32pt typical = $64 risk on 1 lot).
> **EXIT** — first of: **2R target**, stop, or a **60-minute time cap**.
> **COOLDOWN** — 15 minutes. **BOOK** — one position at a time (flat-book).

### 3.2 CANDIDATE D — **FLOW-TRAP FADE** — the spin-off the footprint table pointed at

Same plumbing, opposite trade. Aggressors lean hard on one side and **fail to move price**. They are
trapped; fade them.

> **TRIGGER LONG** — `fz ≤ −2.5` **AND** `|close(t) − close(t−1)| < R15/15` (the minute moved less than a
> typical single bar despite the flow burst) → **BUY**.
> **TRIGGER SHORT** — `fz ≥ +2.5` and the same displacement condition → **SELL**.
> Entry / stop / exit / cooldown / flat-book identical to A.

---

## 4. BACKTEST — tick-honest, net $5/RT

Two independent engines were built and cross-checked: a full tick-walk (`engine.py`, handles trails/BE)
and a vectorised first-crossing engine (`fast.py`). They agree to the dollar (A $+1,830, D $+1,870), so
the fill logic is not doing anything clever. Stop is checked **before** target on the same tick sequence.

### 4.1 Headline

| signal | n | net | win% | $/trade | best | worst |
|---|---|---|---|---|---|---|
| **A — FLOW-BREAK IGNITION** (flat-book) | 39 | **+$1,830** | 56.4% | +$46.94 | +$416 | −$150 |
| A, allowing overlaps | 47 | +$2,612 | 61.7% | +$55.58 | +$416 | −$150 |
| **D — FLOW-TRAP FADE** (flat-book) | 44 | **+$1,870** | 54.5% | +$42.49 | — | — |
| A + D combined | 61 | +$2,370 | 52.5% | +$38.86 | — | — |

Exit mix on A: 23 MAXHOLD / 13 STOP / 11 TARGET, median hold 59 minutes. **Half of A's trades never
resolve inside the hour** — the 60-min cap is doing a lot of the work, which is a weakness, not a feature.

### 4.2 The placebo controls — this is where "flow" earns its place

| variant | n | net | $/trade |
|---|---|---|---|
| **A — full (flow + persistence + break)** | 39 | **+$1,830** | **+$46.94** |
| PLACEBO — **break only**, no flow at all | 206 | −$82 | **−$0.40** |
| PLACEBO — flow only, no break | 144 | +$561 | +$3.90 |
| PLACEBO — flow only, no persistence | 197 | −$1,122 | −$5.70 |
| PLACEBO — A with the direction flipped | 47 | −$2,411 | −$51.31 |

The 30-minute range break **on its own is worth exactly nothing** (−$0.40/trade over 206 trades). Flow is
the discriminator, and it is not the drift: on the short side alone, break-only is −$11.13/trade and the
full signal is +$22.58/trade, so flow adds **+$33.71/trade against the week's +1,261pt uptrend**.

**Random-entry and sign-shuffle nulls** (500 draws each, identical stop/exit/flat-book):

| signal | random-time null (mean / p95) | sign-shuffle null (mean / p95) | actual | p |
|---|---|---|---|---|
| A | −$274 / +$702 | +$63 / +$1,433 | +$1,830 | **0.002 / 0.008** |
| D | −$272 / +$694 | −$131 / +$1,293 | +$1,870 | **0.000 / 0.006** |

Re-run independently on the slow full-tick-walk engine (300 draws): A random-time null −$188 / p95 +$796
→ p=0.000, sign-shuffle p=0.010. Two engines, same answer. A's trade-level t-stat is **2.04** (sd $143.6).

⚠ **Multiple-comparisons honesty:** I searched ~45 sweep cells plus 6 candidate families to get here. A
crude Bonferroni on the sign-shuffle p (0.008 × ~50) lands well above 0.05. **Treat these as
"not-obviously-noise", not as significance.**

---

## 5. REGIME-CONDITIONAL SCORING (the standing backtest rule)

### 5.1 The regime split is *degenerate*, and that is the finding

Regimes keyed on R15 terciles (36 / 53.75pt) × ER15, per the doctrine:

| regime | A: n | A: net | A: $/tr | A: strip-3 $/tr |
|---|---|---|---|---|
| dead-chop | **0** | — | — | — |
| normal-chop | **0** | — | — | — |
| in-between / building | 12 | +$735 | +$61.28 | −$3.21 |
| clean-trend | 25 | +$612 | +$24.48 | −$6.18 |
| violent-whipsaw | 2 | +$483 | +$241.50 | n/a |

**Signal A cannot fire in dead-chop or normal-chop — not once in 5 days.** A flow burst plus a 30-minute
range break mechanically requires ER≥0.15. The trigger is **self-regime-gating**: the regime filter this
desk would normally bolt on is already inside the entry condition, so there is no regime→config policy to
tune here, and no blanket-across-the-tape bug to commit. That is worth saying out loud because it is the
cleanest version of the thing the doctrine is asking for.

### 5.2 Time-of-day is where the policy actually lives

| session (A) | n | net | $/tr | strip-1 $/tr | strip-3 $/tr |
|---|---|---|---|---|---|
| overnight (21:00–06:00Z) | 11 | +$27 | **+$2.42** | −$12.81 | −$38.92 |
| pre-open (06:00–13:30Z) | 13 | +$351 | +$27.00 | +$13.60 | −$11.35 |
| **US (13:30–21:00Z)** | 15 | **+$1,453** | **+$96.86** | +$74.03 | **+$22.86** |

The operator's prior holds exactly: **the money is post-13:30Z**. Overnight is a null that survives no
strip test at all. Pre-open is marginal and dies on strip-3.

**And that is the trap for this assignment.** The census *forces* the 13:00–15:00Z window to the label
OPEN/NEWS, so a run can only be called FLOW-LED **outside** the US open. The FLOW-LED cluster lives at
01:40Z, 08:07Z, 12:52Z and 19:43Z — overnight and pre-open, precisely the segments where A earns nothing.
**The signal's home segment and the target cluster's habitat are disjoint by construction.**

### 5.3 Proven Rs vs the operator's guessed cheat-sheet

Exits swept per regime (flat-book, stop 0.75×R15). Net $ per cell:

| exit | building | clean-trend |
|---|---|---|
| R1.0 / 60m | **+$850** | +$512 |
| R1.5 / 60m | +$779 | +$407 |
| R2.0 / 60m | +$735 | +$612 |
| R3.0 / 60m | +$550 | +$451 |
| trail 1.0/0.5 ATR / 60m | +$428 | +$484 |
| **trail 1.5/0.75 ATR / 60m** | +$713 | **+$660** |
| trail 0.5/0.5 ATR / 60m | +$653 | +$390 |
| any of the above at a 30m cap | lower in 6 of 7 | lower in 5 of 7 |

| regime | operator's guess | proven optimum here | holds? |
|---|---|---|---|
| momentum / building | Lot-A 1.5R, Lot-B 2.5R | **R1.0–1.5** | **guess is too greedy** — building wants to bank *earlier* |
| clean-trend | Lot-A 2.5R, Lot-B wide | **R2.0 or a 1.5/0.75-ATR trail** | **broadly holds** — wide/trail is right, 2.5R is a touch rich |
| every regime | — | **60-minute cap beats 30** | new: the runs need an hour |

Caveat in the same breath: n=12 and n=25. These are directional, not settled.

---

## 6. ROBUSTNESS — where A gets hurt

| test | result | read |
|---|---|---|
| **Parameter sweep** (Z ∈ 1.0–3.0 × persist ∈ 1–3 × break ∈ 15/30/60) | **45 of 45 cells net-positive** | broad plateau, not a spike |
| **…does the edge need n to collapse?** | at persist≥2: n=34–69, $/tr +$42 to +$68 across 9 cells | **no** — the plateau holds at full n. `persist` is the load-bearing knob, not Z: at persist=1 the short side is negative at every single Z |
| **Stop/exit sweep** (4 stops × 6 exits) | 24 of 24 cells positive, $/tr +$10.50 to +$56.41 | not exit-dependent |
| **Long/short symmetry** | L n=22 +$1,442 (+$65.55/tr, 59.1%) · S n=17 +$388 (+$22.85/tr, 52.9%) | **both sides green** — but the long side is 3.8× the short |
| **Per-day** | 4 of 5 days green (+$387/+$1,115/+$235/+$244/−$151) | acceptable |
| **Leave-one-day-out** | all 5 LOO nets positive, +$715 to +$1,982 | no single day carries it |
| **Strip-the-best** | strip-1 → +$37.21/tr · **strip-3 → +$18.11/tr** · strip-5 → **+$7.80/tr** | ⚠ **a 61% haircut at strip-3.** Five trades out of 39 are most of the money |
| **OOS leg (fit 08-03..05, test 08-06..07)** | IS +$66.83/tr (n=26, 65.4%) · **OOS +$7.15/tr (n=13, 38.5%), OOS strip-1 −$26.96/tr** | ⚠ **this is the one that hurts.** The OOS half is a coin flip |
| **US-only sub-sweep** | 6 configs, $/tr +$81 to +$150, strip-3 positive in all 6 | the home segment is a plateau, but n=9–16 |

**D — FLOW-TRAP FADE robustness, for comparison — it is the sturdier of the two:**

| test | D |
|---|---|
| per-day | **+$293 / +$343 / +$415 / +$345 / +$474 — all five days green** |
| leave-one-day-out | +$41.03 to +$43.80/tr — flat as a board |
| OOS split | IS +$42.02/tr (n=25) · **OOS +$43.11/tr (n=19, 68.4%)** — it holds |
| long/short | L n=27 +$1,026 (+$38.0/tr) · S n=17 +$844 (+$49.6/tr) — **genuinely symmetric** |
| parameter plateau | Z ∈ 2.25–3.0 × displacement ∈ 0.75–1.0 → 8 cells, $/tr +$37 to +$89, **strip-3 positive in all 8** |
| the gradient is coherent | loosening the displacement cap to 1.5 kills it at every Z (+$2 to +$12/tr, strip-3 negative) — the edge really is in *"the flow failed to move price"*, not in the flow burst |
| strip-3 | +$18.24/tr (from +$42.49) — same tail dependence as A |

---

## 7. BIG MOVES CAUGHT — X/N

"Caught" = the signal fires in the run's direction between 10 minutes before and 5 minutes after the run start.

| target set | A | D |
|---|---|---|
| **census FLOW-LED sat-out (strict, n=2)** | **0 / 2** | 0 / 2 |
| my re-derived FLOW-LED (n=3) | **0 / 3** | 0 / 3 |
| **union target set (n=4)** | **0 / 4** | **0 / 4** |
| all 62 big runs in the tick era | **12 / 62** | 8 / 62 |

A's 12 hits include the week's two biggest — **08-06 13:32 +249pt (fired +4 min)** and
**08-03 13:43 +165pt (fired 7 min early)** — plus +154, +148-adjacent, −136, −125, +107. It is a
real big-run catcher. It is just not catching *these* runs.

---

## 8. THE KILL — Candidate F, the census's own rule used as an entry

The decisive test. Take the census's FLOW-LED definition *exactly as written* — `|fz| ≥ Z`, flow sign
agrees with the minute's price move, outside the 13:00–15:00Z window the census reserves for OPEN/NEWS —
and trade it. This is the most charitable possible version of the assignment.

| Z | n | net | win% | $/trade | strip-3 $/tr | **catch of 4 targets** | catch of 62 runs |
|---|---|---|---|---|---|---|---|
| 0.75 | 129 | −$1,646 | 36.4% | **−$12.76** | −$17.60 | **2/4** | 18/62 |
| 1.00 | 116 | −$1,708 | 37.9% | **−$14.72** | −$20.42 | **2/4** | 12/62 |
| 1.25 | 111 | −$822 | 40.5% | −$7.41 | −$13.39 | **2/4** | 12/62 |
| 1.50 | 94 | +$358 | 45.7% | +$3.81 | **−$2.85** | 1/4 | 13/62 |
| 2.00 | 83 | −$632 | 41.0% | −$7.62 | −$15.15 | 0/4 | 10/62 |
| 2.50 | 70 | −$399 | 41.4% | −$5.70 | −$14.25 | 0/4 | 7/62 |

**Read the last two columns against the money column.** The settings that actually catch the FLOW-LED
runs (Z ≤ 1.25) are the settings that lose the most — −$12.76 and −$14.72 a trade over 116–129 trades.
The only cell that makes money (Z=1.5, +$3.81/tr) catches 1 of 4, and dies on strip-3 anyway. **Catch-rate
and profitability move in opposite directions.** That is not a threshold that needs tuning; that is a
mechanism with the wrong sign.

Widening the stop to 1.0–1.5×R15 and the hold to 120 minutes to "give the quiet overnight run room" does
not save it either — 6 of 8 of those cells are negative or ~zero, and the single big one
(Z=1.5 / stop 1.5 / 120m, +$31.66/tr) is an **isolated cell surrounded by negatives**, i.e. the textbook
curve-fit artefact this report exists to refuse.

---

## 9. DISPOSITION TABLE — every lead, by name

| # | lead | verdict | the numbers | what killed it / what would revive it |
|---|---|---|---|---|
| **F** | **FLOW-LED as an entry mechanism** (census rule traded directly) | **REFUTED** | best money cell +$3.81/tr catches 1/4; every cell that catches 2/4 loses $7–15/tr over n=111–129; strip-3 negative in **6 of 6** cells | **Named test: strip-best-3 + the catch/profit inversion across the whole Z sweep.** No reformulation saves it, because the tape shows there is nothing to trigger on — flow run-length at the target runs is 1–2 minutes and reverses on the next bar (§2). n is *not* the problem here: n=129. |
| **B** | follow a single-minute flow spike (no persistence, no break) | **REFUTED** | Z=1.0 −$13.68/tr (n=136) · Z=1.5 +$5.51 · Z=2.0 +$2.67 · Z=2.5 −$1.13; **strip-3 negative at all four** | Named test: strip-best-3 + sign-instability across the parameter sweep. n=98–136, so this is not thin-n. |
| **B2** | the same, restricted to the **quiet tape** (R15 < 36pt) — i.e. the FLOW-LED cluster's actual habitat | **REFUTED** | −$11.72 / −$11.34 / −$21.50 per trade at Z=1.0/1.5/2.0; win% **20–29%** | Named test: it loses at *every* threshold, monotonically worse as you tighten. The mechanism is negative **in its own home segment** — that is the strongest single kill in this section. |
| **C** | fade the flow spike (because it reverses next minute) | **REFUTED** | −$5.45 to −$19.88/tr across five Z settings, n=80–135; strip-3 negative everywhere | Named test: negative at all five thresholds. The naive fade is not the trapped-flow trade (see D). |
| **E** | census "flow agrees with the move" rule, all hours | **REFUTED** | −$12.84 / +$4.58 / −$3.90 / −$2.54 per trade; strip-3 negative at all four Z | Named test: strip-best-3 + sign-instability. |
| **A** | **FLOW-BREAK IGNITION** | **SHADOW** | n=39, **+$1,830**, 56.4%, +$46.94/tr; nulls p=0.002/0.008; 45/45 sweep cells green; US segment +$96.86/tr | Does **not** answer the assignment (0/4 on target) and its **OOS half collapses to +$7.15/tr with strip-1 negative**. Not refuted — 5 days of flow tape is all that exists. **Revive/promote if:** ≥3 more weeks of tick capture keep the US-session $/tr above ~$40 at n≥50, *and* the OOS leg stops being a coin flip. Log it US-session-only (13:30–21:00Z); the overnight arm is a null (+$2.42/tr) and should never be armed. |
| **D** | **FLOW-TRAP FADE** | **SHADOW — the better candidate** | n=44, **+$1,870**, 54.5%, +$42.49/tr; nulls p=0.000/0.006; **all 5 days green**; LOO +$41–44/tr; **OOS holds (+$43.11/tr, 68.4%)**; both sides green; 8-cell plateau with strip-3 positive throughout | Also 0/4 on the target cluster — it is the **VACUUM** mechanism, not FLOW-LED. Thin n (44) and a 5-day tape. **Revive/promote if:** it holds ≥$25/tr over n≥80 on the next 3 weeks of ticks. ⚠ It overlaps conceptually with the desk's existing absorption/`abs_veto` work — **check for redundancy before shadowing a duplicate.** |
| **P** | bar-derived flow proxy, to extend the tape past 5 days | **REFUTED** | 4 proxies, best corr **0.272**, sign agreement **49.9–53.4%** vs 6,779 true minutes (volume itself reconstructs at corr 0.960) | Named test: direct validation against the true aggressor series. Aggressor sign is genuinely absent from OHLCV. **No revival without a longer tick archive** — which is an *infrastructure* action, not a research one (see §10). |

**LIVE candidates from this section: none.** Nothing here is a Saturday deploy.

---

## 10. THE ONE STONE STILL UNTURNED

**`capture.db` retains 5 trading days of ticks and that is the binding constraint on every flow idea this
desk will ever have.** Both surviving candidates (A and D) are stuck at n≈40 for a reason that has nothing
to do with the market and everything to do with a retention setting. This section's real recommendation is
not a gate — it is: **start archiving `ticks` to cold storage now.** Three more weeks would take D from
n=44 to n≈180 and turn "not obviously noise" into an answer. Until then every flow finding on this desk,
including these two, is a 5-day finding wearing a confident number.

Second, smaller: **the census's cluster labels should carry a persistence requirement.** As written, one
minute of |z|≥1 flow assigns a run to FLOW-LED, and §2 shows that minute reverses on the next bar and
disagrees with an independent re-derivation 3 times out of 4. The cluster column is currently reporting
noise as structure — I would either require `persist≥3` for the label or retire FLOW-LED and VACUUM back
into a single "flow event" bucket.
