# Is there a construction inside the paper's stated constraints that reproduces its result?

**Follow-up to `VERDICT.md`** · 2026-09-12 · operator's instruction: *"that published study shows it
works. we need to find how. be relentless."*

The first pass asked "does the paper's recipe, as I guessed it, work here?" — no. This pass asks the
operator's actual question: **search the space of everything the paper leaves unstated and find out
whether the claim lives anywhere inside it.**

---

## ANSWER IN ONE PARAGRAPH

For the **RTH Confluence Signal**, yes — and that is the finding. A search over 3,846 constructions
contains a cell at **t = 7.26**, beating the paper's 5.83. But the identical search run on a
**session-permuted (pure-noise) outcome** produces a best cell with **t ≥ 2.0 in 100% of searches
and t ≥ 5.83 in 13%**. A search of this size manufactures the paper's headline statistic roughly
one time in eight from nothing. **Zero of 3,846 constructions survive our bar.** Signal A is
refuted *with adequate power*, and the mechanism of the paper's result is identified as
specification search.

For **London Signal B**, no — and that is a different finding. **No construction anywhere in 1,180
reaches t = 5.15; the maximum is 2.86.** And a noise search of that size reaches 5.15 only **0.5%**
of the time, so B's reported statistic is *not* explainable as a search artefact of this size.
But our sample cannot decide it: detecting B's effect needs ~**780 London sessions** and we have
240. **Signal B is not refutable on this tape. The deliverable is the data, not a verdict.**

| signal | verdict | decided by |
|---|---|---|
| RTH Confluence | **REFUTED (with power)** | search charge: P(noise search best t ≥ 5.83) = **0.130**; 0 of 3,846 cells survive the bar; best cell's holdout **−117.54 pt, t = −3.48** |
| London Signal B | **PARKED — data-limited, not refuted** | no cell reaches t=5.15 (max 2.86) but power needs 780 sessions vs our 240; bar survivors within the null (p=0.233) |

---

## ⚠ CORRECTION TO MY OWN CONTROL — issued before anything below is read

`VERDICT.md` stated: *"on this lake a 60-minute long taken at a random time in the London session
made +11.25 pt (sd 4.66) per trade."* **That statement is WRONG and is withdrawn.** Re-derived
(`CONTROL_CORRECTION.txt`):

| measurement | value |
|---|---|
| **+11.25 pt** — what I published as "the London drift" | **WITHDRAWN** |
| London 60-min long, **all 4,320 bars, overlapping** | **+1.30 pt**, session-clustered t = +0.88 |
| London 60-min long, **non-overlapping (n=1,200)** | **+1.51 pt**, t = +0.91 — not significant |
| coordinator's independent measure, non-overlapping 07–12Z | +1.80 pt, t = 1.33 — **agrees** |
| RTH 65-min long, all bars | **−0.23 pt**, t_cl = −0.09 |

**Root cause, found and reproduced.** My control drew entries *only from the sessions the cell
itself fired on*. That cell fired on **52 of 240** London sessions, and those 52 drifted
**+8.27 pt/hour** while the other 188 drifted **−0.62**. So +11.25 was a *session-conditioned*
number that I wrote up as a property of the lake. It is a legitimate **timing** control; it is not
the London drift, and it must never be quoted as one.

**What the correction changes.** The claim *"Signal B is 2.38 control-sd worse than random timing"*
is **withdrawn**. Corrected adjudication of the frequency-matched cell:

- vs the **unconditional** London population (+0.05 pt net): real +0.14 pt, difference **+0.09 pt =
  +0.01 sd** of an n=76 draw → **indistinguishable**. The signal adds nothing; it is not "worse
  than random".
- vs its **own sessions** (+11.14, sd 4.48): −2.45 control-sd. True, but this is now stated for
  what it is — *given the days it picked, its timing captured +1.39 pt of a +12.39 pt/hour drift* —
  and the day-picking is not skill either, since the cell's sessions are a coin-flip selection.

**And the bull tape is not a benchmark.** MNQ 24,000→30,000 is real cumulatively, but **755 pt of
that rise is contract basis across rolls**, which an intraday hold never touches. Every long cell
below is scored against **+1.30 pt/hour in London and ≈0 in RTH**, not against a bull drift. A wrong
control silently re-grades every cell that touches it, which is why this sits above the results.

---

## 1. The space, and how it was searched exhaustively rather than sampled

A **cell** = (GMM feature vector × state count × EM seed × component→R-number mapping × transition
rule × execution variant). Held **fixed** because the paper *does* state them: 5-min RTH / 15-min
London bars, the 03:00–08:30 ET and 09:30–16:00 ET windows, the 0.15 and 0.5 thresholds, 60/65-min
holds, long side, entry at the next bar's open, chronological train/validate/test with the GMM fit
on TRAIN only.

| axis | values | n |
|---|---|---|
| feature vector | direction-only · direction+activity · desk's `bt_regime_transition` · pure returns · direction+vol · full · **raw unnormalised** | 7 |
| state count K | 3, 4, 5, 6 | 4 |
| EM seed (an unstated choice that moves labels) | 1, 3, 7, 11, 23 | 5 |
| component → R0/R1/R2 | by mean return (middles=R1) · top-3 by share · R1=most active · by mean drift | 4 |
| B: transition rule | strict · loose · simple | 3 |
| A: pullback × lifetime × exit anchor | none / fix25 / atr25 × 3,6 bars × entry,signal | 10 |
| **cells with n ≥ 25** | | **A: 3,846 · B: 1,180** |

Made affordable by precomputing, for each execution variant, `ret_all[i]` = the net points that
variant returns *if bar i were a signal*, for every bar. A cell is then a mask and scoring is a
masked mean — which also makes the same-entry control closed-form and lets the **entire search be
re-run under the null** at negligible cost.

### The full distribution — not the best cell

| | Signal A (3,846) | Signal B (1,180) |
|---|---|---|
| mean net pt/trade across cells | **−4.26** | **+0.37** |
| t: mean / sd across cells | **−0.98 / 1.48** | **+0.11 / 1.04** |
| cells with mean > 0 | 857 (22.3%) | 636 (53.9%) |
| cells with t ≥ 2.0 | 169 (4.4%) | 45 (3.8%) |
| **cells with t ≥ the paper's** | **4** (≥5.83) | **0** (≥5.15) |
| **max session-clustered t** | **2.71** | **2.85** |
| best raw t | **7.26** | 2.86 |

Signal B's t-distribution across the whole space is **N(0.11, 1.04)** — indistinguishable from the
null distribution of a t-statistic. Signal A's is shifted **negative**. And note the last row but
one: **once trades are clustered by session, nothing in either space exceeds t = 2.9.** The paper's
5.83 and 5.15 are not reachable under clustering at all.

---

## 2. The search charge — what a search this size is worth on noise

`search_charge_A.txt` · `search_charge_B.txt` · 200 placebo draws. Under the null, a trade at slot
*k* of session *s* is paid what the same execution earned at slot *k* of a **randomly permuted
session**: execution mechanics, time-of-day structure and the return distribution all preserved,
only the label→outcome link cut. Then the **whole search** is re-run and its **best cell** recorded.

| | Signal A (3,846 cells) | Signal B (1,180 cells) |
|---|---|---|
| null best-of-search max t: median / 95th | **4.23 / 6.55** | 2.93 / 4.09 |
| **P(noise search best t ≥ 2.0 — the paper's own bar)** | **1.000** | **1.000** |
| **P(noise search best t ≥ the paper's)** | **0.130** (≥5.83) | **0.005** (≥5.15) |
| our observed best t | 7.26 | 2.86 |
| charged p for our best cell | 0.015 | **0.575** |

**This is the answer to "find how it works" for Signal A.** A median noise search of this size
returns **t = 4.23**. The paper's institutional threshold of t ≥ 2.0 is cleared by a pure-noise
search of the unstated choices **every single time**. Its headline 5.83 is at roughly the 87th
percentile of noise — reachable one search in eight, *before* counting the author's own additional
degrees of freedom in a signal the paper says was "developed independently" in a separate research
program, i.e. through an unknown amount of prior iteration.

**Signal B does not get this explanation.** 5.15 on a low-dispersion 60-minute hold is reached by
only 0.5% of noise searches. Whatever produced B's number, a search of this size is not it.

### And the bar itself was charged, not just the best cell

`bar_charge_A.txt` · `bar_charge_B.txt` — 60 placebo searches, counting cells passing the full
filter (a) mean>0 @1.25 pt · (b) beats its same-entry control by >1 control sd · (c) session-
clustered t ≥ 1.96 · (d) positive in TRAIN, VALIDATE **and** TEST.

| | survivors on the real tape | null: median / 90th pct | p |
|---|---|---|---|
| Signal A | **8** | 10 / 47 | **0.583** |
| Signal B | **26** | 10 / 49 | **0.233** |

A filter this strict still passes ~10 cells by chance out of a search this size. **Neither signal's
survivor count exceeds the null.** Our own survivors are, by this test, nothing.

---

## 3. Does any survivor clear our bar? The funnel, both signals

| step | Signal A | Signal B |
|---|---|---|
| constructions with n ≥ 25 | 3,846 | 1,180 |
| (a) beats zero @ 1.25 pt friction | 857 | 636 |
| (b) + beats same-entry control by > 1 control sd | 363 | 228 |
| (c) + session-clustered t ≥ 1.96 | 22 | 31 |
| (d) + positive in TRAIN, VALIDATE and TEST | 8 | 26 |
| **(e) + positive on the PRIOR-PERIOD HOLDOUT** | **0** | **3** |

**The holdout is the sharpest instrument here and it was free.** `data/driftlab/NQ_202509.parquet`
covers **2025-06-18 → 2025-09-11 (74 dates, ~62 sessions)** — *entirely before the lake starts*,
contiguous with it (23,951 → 24,354), same index level. It took no part in any fit and no part in
the search. NQ and MNQ quote identically, so points are directly comparable.

**Signal A's 8 survivors are 2 distinct state configs, and both reverse violently out of sample:**

| construction | n | net pt | t_cl | vs unconditional pop | **holdout** |
|---|---|---|---|---|---|
| F1dir/K5/seed7/Lact × 6 exec variants | 51–76 | +46.7…+52.6 | 2.04–2.71 | +3.7…+4.8 sd | **−36.5 … −51.5 pt, t = −2.53** |
| F6full/K6/seed3/Lret_top3 × 2 | 38 | +40.0/+43.0 | 2.21/2.61 | +2.7/+2.9 sd | n=2, undeterminable |
| best-t cell (t=7.26) F3desk/K6 | 34 | +73.5 | **2.17** | +5.8 sd | **−117.5 pt, t = −3.48** |

The t=7.26 cell that beats the paper lives **entirely in VALIDATE** (no TRAIN, no TEST trades) and
loses 117 points per trade out of sample. That is what the top of a 3,846-cell search looks like.

**Signal B's 3 holdout survivors are one construction (F7raw/K5/Ldrift/loose at seeds 1, 7, 11),
and it is a volatility-era artefact.** `f7raw_diagnostic.txt`:

- F7raw is the **raw, unnormalised** feature set — and the raw features drift hard across the
  sample: mean |1-bar return| **22.96 → 35.43**, mean range **28.84 → 46.08**, log volume
  **8.63 → 9.25** from first to last quarter. The GMM's state frequencies drift with them (state 4:
  **0.27 → 0.03**; state 1: **0.21 → 0.49**). The model is classifying *the era*, not the structure.
- Its P&L decays monotonically by sample quartile: **+13.38 → +20.89 → +6.76 → −1.73**.
- **72% of its total +2,595 pt comes from the top 5% of sessions** — 6 sessions out of 122.
- Its holdout is n=11 trades at t=1.15. That is not evidence of anything.

**So: zero constructions in either space clear the bar.** The one that clears the most steps is a
regime-drift artefact concentrated in six days.

---

## 4. The sample-era question — and the two signals land on opposite sides of it

`era_and_power.txt`. **A point edge is not scale-free.** Friction is fixed in points ($1.50/RT =
0.75 pt) but an edge is not. The paper's era averaged MNQ ≈ 16,000; this lake averages ≈ 27,000
(⚠ the 16,000 is from general knowledge — **the paper's era is not on this box**, so it is flagged
as an estimate, not a measurement).

Back out the paper's implied per-trade dispersion from its own t and n (`sd = mean·√n / t`):

| signal | paper-implied sd | our measured sd | level-scaled expectation | reading |
|---|---|---|---|---|
| A (65-min RTH) | **62.7 pt** | 96.4 pt | 57.1 pt | **consistent** |
| B (60-min London) | **19.0 pt** | 53.6 pt | 31.8 pt | **~40% below plausible** |

Signal A's reported statistics are internally coherent with a 2021–2025 MNQ tape. **Signal B's are
not**: a 60-minute MNQ London hold with a per-trade sd of 19 points is below what that instrument
plausibly did in any year of the paper's sample. Either its exits were much shorter in effect than
60 minutes (the 08:30 ET cap binding on most trades would do it), or its dispersion is misreported.
That is a question for the author, and it is the single most useful thing to ask him.

### Power — which situation are we in, per signal

Sessions needed for 80% power, α = 0.05 two-sided, assuming the edge scales with price level:

| signal | effect at our level | trades needed | **sessions needed** | we have |
|---|---|---|---|---|
| A | +26.6 pt | 103 | **181** (0.7 yr) | **239** ✅ |
| B | +9.7 pt | 238 | **780** (3.1 yr) | **240** ❌ |

**Signal A: situation one — refutable here, and refuted.** We have more sessions than the effect
requires, our large-n constructions (up to n=3,255) have ample power, the whole space skews
negative, and the best cell reverses out of sample. The paper's claim is rejected, not merely
unconfirmed.

**Signal B: situation two — not refutable on this tape.** 240 sessions against a requirement of 780
(2,220 if the edge does *not* scale with level). Our best cell at t=2.86 and our 26 bar-survivors
are exactly what this sample size produces under the null. **We cannot say Signal B is false. We can
only say we cannot see it, and that we would not expect to.**

### What sample would settle Signal B

| | requirement |
|---|---|
| **size** | ≥ **780** London sessions; **2,200** if the edge does not scale with price level |
| **span** | must cross a volatility regime, not one bull leg. The paper's own Dec 2021 – Aug 2025 (COVID vol, the 2022 bear, the 2023–24 recovery) is the right shape |
| **bars** | 1-minute MNQ, aggregated locally to 15-min (London) and 5-min (RTH) — never vendor-aggregated, so the session and DST anchoring stay ours |
| **why not IBKR** | the documented entitlement ceiling: 15Y and 5Y requests return the **same 482 daily bars**. More runtime buys nothing. `MNQ_CONTFUT_1day` confirms it — it stops at 2024-09-23 |
| **the concrete action** | the paper itself names it: **Databento MNQ at ~$42/quarter**. Dec 2021 – Aug 2025 = 15 quarters ≈ **$630**, one purchase, and it also settles the RTH sd question and gives this desk a multi-regime tape it does not currently own at any price |

That $630 is the deliverable. It is the only thing that converts Signal B from *undecidable* to
*decided*, and the desk's entire lake being one 11-month bull leg is a limitation that will keep
recurring in every study until it is fixed.

---

## 5. What I would tell the operator

1. **The paper's positive control for the RTH Confluence Signal does not survive contact.** The
   mechanism is identified: its unstated choices form a space in which a *pure-noise* search clears
   the paper's own t ≥ 2.0 bar **100% of the time** and reaches its published 5.83 **13%** of the
   time. That is not an accusation of bad faith — it is what happens when a signal's construction
   is never written down and its author iterates. It is the same shape as this desk's own
   `abs_veto_short` promotion: **a real-looking number attached to the wrong object.**
2. **Signal B is undecided, and honestly so.** Nothing in 1,180 constructions reaches its t, but
   nothing could at this sample size. Its reported dispersion is the anomaly worth chasing.
3. **I published a wrong control and it is withdrawn above, in full, with the root cause.** +11.25
   was a session-conditioned number masquerading as the London drift; the real number is +1.30 pt/hr
   and not significant.
4. **Neither signal goes to SHADOW.** There is nothing to shadow: every cell that clears our bar was
   selected on its own P&L out of thousands, and the survivor counts are inside the null.

---

## Artifacts added by this pass

| file | what |
|---|---|
| `SPEC_SEARCH.md` | this report |
| `CONTROL_CORRECTION.txt` | the withdrawn +11.25, its root cause, the corrected numbers |
| `spec_search.py`, `run_search.py` | the exhaustive search engine (mask × ret_all design) |
| `spec_search_A.csv` (3,846 rows), `spec_search_B.csv` (1,180 rows) | **every construction**: n, mean, t, clustered t, control, gap, per-period, holdout |
| `charge_search.py` → `search_charge_A.txt`, `search_charge_B.txt` | best-of-search under the null, 200 placebo draws |
| `charge_bar.py` → `bar_charge_A.txt`, `bar_charge_B.txt` | the **bar** charged, not just the best cell |
| `finalists.txt` | top cells, the funnel, the survivors |
| `era_and_power.txt` | corrected baselines, implied-vs-measured dispersion, power, sample requirement |
| `f7raw_diagnostic.txt` | why Signal B's only holdout survivor is a volatility-era artefact |

Read-only on data throughout; no service started, stopped or restarted; no IBKR/gateway connection
attempted.
