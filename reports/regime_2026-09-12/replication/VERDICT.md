# Replication of Mesfin (2026)'s two positive-control signals on GAZBOT V7's MNQ lake

**Date** 2026-09-12 (Saturday, venue shut) · **Analyst** research agent · **Read-only on data**
**Paper** Mesfin, M. (2026), *Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures*,
arxiv.org/pdf/2605.04004 (local copy: `mesfin_2026.pdf`)

---

## VERDICT

| signal | paper | this lake | verdict |
|---|---|---|---|
| **RTH Confluence (ATR-adaptive)** | +15.77 pt, t=5.83, 61.0% win, n=538 | **0 of 30 constructions positive**; grid mean −12.31 pt/trade; assembled signal +0.02 pt at **t=0.00** | **REFUTED** |
| **London Session Signal B (R0→R2)** | +5.77 pt, t=5.15, 64.7% win, n=289, 1-bar-delay t=−3.56 | frequency-matched construction **+0.14 pt, t=+0.03**; loses to its own random-entry control by **2.38 control-sd** | **REFUTED** |

**The named test that decided each:**

- **Signal A — the condition decomposition against a time-of-day-matched control.** With the three
  confluence conditions assembled exactly as written, n=620 signals produce **+0.02 pt/trade,
  t=0.00**. The largest-sample construction (n=1,067) gives −7.31 pt with a day-block 95% CI of
  **[−23.7, +8.2]**, which **excludes the paper's +15.77 pt**. This is a rejection of the claimed
  effect size, not merely a failure to confirm it.
- **Signal B — the random-entry control on the frequency-matched construction.** The real signal
  nets **+0.14 pt/trade**; drawing the *same number of 60-minute longs on the same sessions at
  random entry times* nets **+11.25 pt (sd 4.66)**. The signal is **2.38 control-sd worse than
  randomly picking the entry bar**. Day-block 95% CI **[−9.02, +9.18]** includes zero. It fails
  addendum tests (b) and (c) outright.

Both fail the addendum bar. Neither goes to SHADOW: there is no cell to shadow that was not picked
on its own P&L.

---

## Why this is a genuine test, and where it is not

- **Sample is truly out-of-sample for both signals.** Paper: Dec 2021 – Aug 2025 (NinjaTrader).
  This lake: **2025-09-14 → 2026-08-18**, IBKR, 291 ET dates / **239 RTH sessions** /
  **240 London sessions**. Zero overlap, different vendor.
- **Power is adequate for A, marginal for B.** The 65-minute MNQ move has sd ≈ 96 pt. Signal A's
  large-n cells exclude +15.77 pt at 95%. Signal B's frequency-matched CI upper bound is +9.18 pt,
  which **does not exclude the paper's +5.77 pt** — B is *not detected*, not *proven absent*. Said
  plainly because it matters.
- **Contract selection is clean.** Front month chosen **per ET date by volume**. All 43
  multi-contract dates audited (`tape.py` output): the volume rule picks the correct leg on every
  one, and because every trade opens and closes inside one ET date, the 118–289 pt roll-level
  defect **cannot enter a trade** by construction.
- **DST is handled explicitly** (`dst_and_spread.txt`). The 03:00–08:30 ET London window is held on
  tz-aware `America/New_York` wall-clock minutes. Both 07:00Z (EDT) and 08:00Z (EST) start hours
  appear in the sample; a fixed UTC offset would have mis-anchored **88 of 240 sessions**.
- **The harness is verified unbiased.** An unconditional 13-bar (65-min) long from *every* RTH
  5-minute bar returns **−0.232 pt gross, t=−0.30, n=15,253**. The large negative signal means are
  therefore real conditional results, not an accounting bug.

---

## ★ THE CENTRAL PROBLEM: the paper does not specify these signals

Section 5 is **two paragraphs**, and says the controls "were developed independently and are not
the subject of this paper." It states no GMM feature vector, no state count, no rule mapping fitted
components to R0/R1/R2, no pullback mechanics, and no exit anchor. I had to guess **twelve** things
(full text in `lib.py:GUESSES`):

| # | unstated choice | what I did |
|---|---|---|
| G1 | **GMM feature vector** — never stated | three specs: direction-only; direction+activity; the desk's existing `bt_regime_transition.py` features |
| G2 | **number of states** | K=3 (forced by the R0/R1/R2 naming); K=2,4,5,6 swept for A |
| G3 | **which fitted component is which regime** | two rules: order by TRAIN mean return; or R1 = highest-activity state, rest split by mean return. Never by outcome |
| G4 | **"rolling 200-bar Markov transition probability to Regime 2"** — P(1→2) or unconditional? | causal trailing-200-bar P(R1→R2) |
| G5 | volume z-score: raw or log, window inclusive? | raw volume, trailing 50 bars inclusive |
| G6 | **"25-point ATR-scaled pullback"** — mechanics entirely unstated | long limit at `close − 25·ATR20/median(ATR20 on TRAIN)`; fixed-25 pt and no-pullback variants also run |
| G7 | pullback limit lifetime | 3 bars and 6 bars both run; unfilled = no trade |
| G8 | **"exit at bar 13"** — from signal bar or entry bar? | 13 bars after the **entry** bar (=65 min, per the brief), capped at 16:00 ET |
| G9 | Signal A direction | LONG (decision D023 rejects the short confluence signal) |
| G10 | B's "clean transition, no R1 contamination in the prior two bars" | strict (`R[i]=2, R[i−1]=0, R[i−2]≠1`) and loose (`came from R0 in prior two, no R1`) both run |
| G11 | GMM fitted on session bars or the whole tape | on the same session window the signal trades |
| G12 | walk-forward structure | paper uses calendar-year expanding windows; this lake is 11 months, so the brief's chronological 40/30/30 session split |

**How much do the guesses matter? More than the effect being claimed.**

| | constructions run | ALL-period net/trade spread across constructions | positive cells | cells with t ≥ +2 |
|---|---|---|---|---|
| Signal A | 30 | −23.19 → −2.96 pt (**20.2 pt wide**) | **0 / 30** | 0 |
| Signal B | 18 (12 with n≥25) | −19.83 → +10.96 pt (**30.8 pt wide**) | 4 / 12 | 0 |

The unstated choices move the answer by 20–31 points per trade. The paper claims effects of 5.77
and 15.77 points. **A recipe whose undocumented details swamp its claimed effect cannot be
replicated in principle** — the best anyone can do is report the whole grid, which is what this
does.

---

## Signal A — RTH Confluence. Full results

`signal_a_grid.txt` · `signal_a_grid.csv` · `signal_a_verdict.txt` · `signal_a_decompose.txt`

239 RTH sessions, 18,360 5-minute bars (09:30–16:00 ET). TRAIN 95 / VALIDATE 72 / TEST 72 sessions,
chronological. GMM fitted on TRAIN only, applied unchanged. Net points **per trade at this desk's
measured 1.25 pt friction**; at the paper's 2.0 pt every figure is **exactly 0.75 pt worse** (a
constant — friction cannot rescue a cell, and cannot sink one, relative to its control).

Selected cells (full 30-row grid in `signal_a_grid.txt`):

| construction | sig/sess | TRAIN n / net / t | VALIDATE n / net / t | TEST n / net / t | ALL n / net / t |
|---|---|---|---|---|---|
| **frequency-matched** F1dir/Lret/atr25/life3 | 0.37 | 28 / +14.34 / 1.03 | 20 / −39.69 / −1.60 | 16 / −49.01 / −0.95 | **64 / −18.38 / −1.13** |
| best-t F2diract/Lret/atr25/life6 | 2.93 | 143 / +2.43 / 0.24 | 113 / −0.55 / −0.05 | 114 / −12.11 / −0.95 | **370 / −2.96 / −0.47** |
| largest-n F3desk/Lret/none | 4.94 | 397 / +0.48 / 0.09 | 362 / +4.76 / 0.74 | 308 / −31.53 / −3.27 | **1067 / −7.31 / −1.78** |
| **paper** | 0.717 | — | — | OOS 196 / **+11.82** / **3.11** | IS 538 / **+15.77** / **5.83** |

*Frequency-matched* = the construction whose signals-per-session is closest to the paper's
538/947 = 0.717. Frequency is the only construction diagnostic the paper reports, so selecting on
it never touches the outcome.

**Controls (addendum bar):** every cell **FAILS (b)** — none beats a time-of-day-matched random
entry by more than one control sd — and every cell **FAILS (c)** — every day-block bootstrap CI
includes zero. No cell even clears (a).

### Condition decomposition — what each leg is actually worth

| condition | n | net pt | t | control mean | gap (control sd) |
|---|---|---|---|---|---|
| (a) state == R1 Active Flow | 5,184 | −1.01 | −0.84 | −1.08 | +0.06 |
| (b) rolling P(R1→R2) > 0.15 | 15,202 | −1.52 | −1.94 | −1.47 | −0.06 |
| (c) 50-bar volume z > 0.5 | 3,840 | **−6.07** | **−2.85** | −4.00 | −1.06 |
| (c′) volume z > 1.5 | 1,836 | −8.28 | −2.48 | −4.35 | −1.26 |
| **(a)+(b)+(c) — THE SIGNAL** | **620** | **+0.02** | **0.00** | −4.49 | +1.00 |
| all bars (baseline) | 15,252 | −1.48 | −1.90 | −1.39 | −0.12 |

Two structural findings that hold regardless of my guesses:

1. **Condition (b) is not a condition.** At K=3 and K=4 the rolling P(R1→R2) exceeds 0.15 on
   **99.4–100%** of bars. Whether the paper's transition filter bites *at all* is decided entirely
   by the unstated state definition, not by the 0.15 threshold. At K=5/6 it binds (22%/13%) — the
   threshold is a hidden free parameter of the GMM, not of the signal.
2. **Condition (c) has the wrong sign on this tape.** High relative volume predicts a *worse*
   65-minute long (−6.07 pt, t=−2.85) and loses to a time-of-day control — i.e. it is mostly a
   time-of-day proxy, since a 50-bar window inside a 78-bar session makes the z-score fire at the
   open and the close. This is consistent with the paper's **own** Section 4.5 volume null.

The K sweep (K=5 gap +1.98 sd, K=6 gap +1.86 sd, both t≈1.3) is the multiplicity artefact you get
from sweeping five values of a parameter the paper never names. It is not reported as a finding.

---

## Signal B — London R0→R2. Full results

`signal_b_grid.txt` · `signal_b_grid.csv` · `signal_b_verdict.txt` · `signal_b_results.txt` ·
`signal_b_trades.csv`

240 London sessions, 5,280 15-minute bars (03:00–08:30 ET, DST-aware). Entry long at the next
15-min bar open; exit at the close of entry+3 (exactly 60 minutes) or the 08:30 ET bar, whichever
first. Net pt at 1.25 pt friction; at 2.0 pt subtract 0.75.

| construction | trades/sess | TRAIN n / net / t | VALIDATE n / net / t | TEST n / net / t | ALL n / net / t | 1-bar delay t |
|---|---|---|---|---|---|---|
| **frequency-matched** F3desk/Lret/loose | 0.317 | 40 / +0.53 / 0.09 | 21 / −13.48 / −1.16 | 15 / +18.17 / 1.36 | **76 / +0.14 / +0.03** | −0.34 |
| best-t F1dir/Lret/loose | 0.208 | 20 / **+27.65 / 4.42** | 14 / +1.80 / 0.11 | 16 / −4.78 / −0.38 | **50 / +10.04 / 1.48** | **+0.49** |
| primary pre-spec F2diract/Lact/strict | 0.142 | 10 / +2.45 / 0.18 | 16 / −14.44 / −1.60 | 8 / −21.56 / −1.02 | **34 / −11.15 / −1.47** | −1.21 |
| **paper** | 0.305 | — | — | — | **289 / +5.77 / +5.15** | **−3.56** |

### The three addendum tests

| construction | (a) beats 0 @1.25 | (b) beats control by > 1 control-sd | (c) day-block CI excludes 0 |
|---|---|---|---|
| frequency-matched | marginal (+0.14) | **FAIL** — rotation −1.59 sd, **random-entry −2.38 sd** | **FAIL** [−9.02, +9.18] |
| best-t | yes (+10.04) | PASS — rotation +2.47 sd, random-entry +2.21 sd | **FAIL** [−2.24, +23.09] |
| primary pre-spec | **FAIL** (−11.15) | **FAIL** −1.39 / −1.67 sd | **FAIL** [−25.88, +3.11] |

**The best-t cell is the one that has to be argued down, so here is the argument.** It passes both
controls, and only that cell does. But (i) it was selected on its own P&L out of 18 constructions;
(ii) its entire edge lives in TRAIN — **+27.65 pt at t=4.42 in the 96 sessions the GMM was fitted
on**, decaying to +1.80 in VALIDATE and −4.78 in TEST. That is hindsight relabelling of the fit
period, the exact artefact the desk's own `sessionmap.py` warns about and the paper's own
"one strong year" failure mode; (iii) it fails the day-block CI; and (iv) it fails the paper's own
diagnostic below. **PARKED-as-artefact, not SHADOW.**

### The paper's own strongest diagnostic: the 1-bar delay

The paper's best evidence that Signal B is real is that **delaying entry one bar reverses it**,
t = +5.15 → **−3.56**. That is the check the brief calls the strongest evidence of a faithful
replication.

**It does not reproduce.** Across the 12 constructions with n≥25, cells where the real t is
positive *and* the delayed t is negative number **2 of 12** — indistinguishable from coin-flipping.
In the frequency-matched cell t moves +0.03 → −0.34 (both indistinguishable from zero, so the
"reversal" is meaningless). In the best-t cell it moves +1.48 → **+0.49**, i.e. the edge *survives*
a one-bar delay, which is precisely what the paper says cannot happen to the real signal.

### ⚠ CORRECTED 2026-09-12 — the control number below was WRONG

**The "+11.25 pt random London long" published in the next paragraph is WITHDRAWN.** It was a
*session-conditioned* control (drawn only from the 52 sessions the cell fired on, which drifted
+8.27 pt/hr against −0.62 for the other 188), written up as a property of the lake. The correct
unconditional figure is **+1.30 pt/hour (overlapping) / +1.51 pt (non-overlapping, t=0.91) — not
significant**. Consequently the claim *"Signal B is 2.38 control-sd worse than random timing"* is
also **withdrawn**: against the unconditional population the cell is **+0.01 sd — indistinguishable,
not worse**. Full root cause in `CONTROL_CORRECTION.txt`; the conclusions of this report are
unchanged (they never rested on the size of that control), but the number must not be reused.

### One finding worth keeping (SUPERSEDED — see the correction above)

The random-entry control exposed something independently useful: **on this lake a 60-minute long
taken at a random time in the London session made +11.25 pt (sd 4.66) per trade.** Sep-2025 →
Aug-2026 was a strong up-tape (MNQ ~24,000 → ~30,000). The frequency-matched Signal B does *worse
than that baseline*. Any London long study on this sample **must** be scored against this drift, or
it will read a bull market as an edge. Filed as a method note for the next London study.

---

## What this tells the operator about the paper as a whole

The paper's *negative* results — fourteen falsified signal families, the ~1.05–1.50 pt gross edge
ceiling at 5-minute OHLCV resolution — are not touched by this work and remain the paper's real
contribution. They are also consistent with everything this desk has measured.

What does not survive is the paper's **positive controls**. Their job in the paper is to prove the
methodology "can find genuine edge when it exists". On a different vendor, a different year, and a
grid of every reasonable reading of two under-specified paragraphs, **neither one is detectable**,
and Signal A's claimed effect size is excluded outright. The narrow lesson is the desk's own:

> **a live instrument's founding number must be re-derived** — and a number that cannot be
> re-derived because its recipe was never written down is not a number, it is a citation.

---

## Follow-up

**`SPEC_SEARCH.md`** answers the harder question the operator asked next — whether ANY construction
inside the paper's stated constraints reproduces its result. Short answer: for the RTH signal yes,
and a pure-noise search of the same size reaches the paper's t 13% of the time; for London Signal B
no construction reaches it, but this tape is too small to decide it.

## Artifacts (all under `reports/regime_2026-09-12/replication/`)

| file | what |
|---|---|
| `VERDICT.md` | this report |
| `mesfin_2026.pdf` | the paper as fetched |
| `tape.py` → `mnq_1min_canon.parquet` | canonical MNQ 1-min tape, front month per ET date by volume, + roll audit |
| `lib.py` | bars/features/GMM/EM/predict, day-block bootstrap, splits, **the 12 guesses** |
| `signal_b_london.py` → `signal_b_results.txt`, `signal_b_trades.csv` | Signal B primary pre-spec, both friction levels |
| `signal_b_grid.py` → `signal_b_grid.txt`, `.csv` | Signal B, 18 constructions |
| `signal_b_verdict.py` → `signal_b_verdict.txt` | Signal B controls: rotation, random-entry, day-block, 1-bar delay |
| `signal_a_rth.py` → `signal_a_grid.txt`, `.csv` | Signal A, 30 constructions |
| `signal_a_verdict.py` → `signal_a_verdict.txt` | harness sanity check + time-of-day-matched controls |
| `signal_a_decompose.py` → `signal_a_decompose.txt` | K sweep + per-condition decomposition |
| `dst_and_spread.txt` | DST proof (88/240 sessions would mis-anchor) + construction-spread table |

No service was started, stopped or restarted; no gateway or IBKR connection was attempted; all DB
reads were read-only.
