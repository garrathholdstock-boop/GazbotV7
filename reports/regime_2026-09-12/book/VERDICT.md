# ORDER BOOK AT REGIME TRANSITIONS — VERDICT: **REFUTED**

*2026-09-12 · MNQ · 31 sessions of order book (2026-07-31..09-11) · read-only · no orders placed*

## The verdict in one line
**The order book does not add direction at regime transitions.** The best cell in a 240-cell
grid is *inside* what a day-block sign-flip null produces (familywise **p = 0.4617**), and the
single most-powered directional test on this desk to date — 45 cells at n≈13,000 minutes each —
puts every hit rate between **0.4863 and 0.5064**.

The desk's existing summary survives intact and is now anchored an order of magnitude better:
**THE BOOK SAYS WHEN, NOT WHICH WAY.** Previously that rested on 610 observations across 19
sessions. It now rests on 41,142 minutes.

---

## The named tests that decided it

| # | test | statistic | verdict |
|---|---|---|---|
| **T1** | **S07 / L3 — book as a FILTER on the regime side.** 240 cells (10 features × 3 normalisations × 4 holds × clean/all). Null = **day-block sign-flip permutation** of the book's agreement, 4,000 draws. | observed max abs contrast **22.41 pt** vs null max 95th pct **31.03 pt** · **familywise p = 0.4617** · **0 of 240** cells pass all three legs of the addendum bar | REFUTED |
| **T2** | **S08 — the contrarian reading**, pre-registered from S06 rather than mined. 360 cells. Same day-block sign-flip null on the friction-free gross statistic. | best gross edge **11.46 pt** vs null max 95th pct **15.41 pt** · **familywise p = 0.4285** | REFUTED |
| **T3** | **S10(B) — the glimmer against its RIGHT control.** T2's best cells "fade the book" for +10 pt, but the regime strategy is −9 pt here, so *fading the regime* already earns that with no book at all. Paired increment, same trades. | book increment over fade-the-regime: **−4.02 to +5.12 pt**, **17/28 positive** (a coin), **0 of 28** day-block CIs exclude zero | REFUTED |
| **T4** | **S13 — the last place direction could hide.** Does the book's asymmetry pick the side *at the moments it is loudly signalling "when"*? Split by depth-withdrawal tercile, n≈13,000 per cell. | hit rates **0.4863 .. 0.5064** over 45 cells. The THIN (withdrawn) tercile is **0.490–0.503** — indistinguishable from THICK. Only 3 CIs exclude 0.500 and **all three are below it** | REFUTED |

### The addendum's three-part bar, scored
- (a) agree-cell beats zero at 1.25 pt friction — **2 of 240**
- (b) beats its own shuffled twin by more than the control's spread — 125 of 240
- (c) day-block bootstrap CI excludes zero — **0 of 240**
- **all three — 0 of 240.**

---

## Why this null is credible: two positive controls that DID fire

A null is worthless from an instrument that was never shown to work
(*[an instrument that reports healthy about what it never checks]*).

**PC1 — S06, the instrument check.** My OFI reproduces the Cont/Kukanov/Stoikov result exactly:

| horizon | OFI r | t | hit |
|---|---|---|---|
| **same minute (contemporaneous, NOT tradeable)** | **+0.6883** | **192.46** | **0.7934** |
| +1 min | −0.0134 | −2.72 | 0.4919 |
| +5 min | −0.0146 | −2.97 | 0.4955 |
| +15 min | −0.0047 | −0.95 | 0.5002 |
| +60 min | −0.0013 | −0.26 | 0.4974 |

Touch imbalance is contemporaneously **−0.185 (t=−38.2)** — more resting bid, price goes *down*
this minute — and trade-sign imbalance **+0.175 (t=+35.8)**. The features are real, correctly
signed and enormously significant **within the minute they arrive**, and carry **nothing**
forward. The information is fully incorporated on arrival. At n=39,254 the 95% band on r at
+60 min is ±0.010, so any r above 0.01 would have been seen.

**PC2 — S12, the desk's own prior finding, reproduced.** Pre-leg 3-level depth vs a
time-of-day-matched control (strictly the 5 minutes BEFORE the leg):

| leg size | 10pt | 20pt | 30pt | 40pt | 60pt | 80pt | **120pt** |
|---|---|---|---|---|---|---|---|
| pre-leg depth ratio | 1.000 | 0.982 | 0.969 | 0.946 | 0.934 | 0.895 | **0.767** |
| day-block sig? | ns | ns | ns | ns | ns | **yes** | **yes, CI [0.670, 0.917]** |

Monotone dose-response, and at the largest legs it lands on the desk's published **0.72x**.
The pipeline detects a real book effect. The same pipeline reports 0.50 on direction.

---

## Three findings that were not the mission but matter more than the null

### F1 — ⚠ THE REGIME-TRANSITION STRATEGY IS NEGATIVE ON THIS WINDOW, and this window cannot judge it
Computed from S02's transition table with the book never touched, at 1.25 pt friction:

| hold | clean | n | net pt | win% | day-block 95% CI |
|---|---|---|---|---|---|
| 30m | no | 346 | −3.48 | 49% | [−7.36, +0.48] |
| 60m | no | 339 | −4.74 | 49% | [−11.33, +1.76] |
| 60m | **yes** | 269 | **−5.41** | 47% | [−13.69, +2.87] |
| 90m | **yes** | 264 | **−9.00** | 46% | [−19.96, +1.91] |

The incumbent's **+0.82 pt (90m clean)** and **+0.47 pt (60m clean)** are the mean over its whole
span (2025-09..2026-08). On the most recent 31 sessions the point estimate is −3.5 to −9.0 pt.
**But every CI spans zero and contains the incumbent's number too.** This is not a refutation —
it is a statement that **31 sessions have no power to confirm or refute a ~1 pt edge**: the
per-trade sd of a 60m hold is 64.4 pt, so the sd of the mean is 3.50 pt, roughly **4× the effect
being claimed**. Any read of this strategy on a book-length window is noise in both directions.

### F2 — A 15-MIN GMM REGIME TRANSITION IS NOT A LEG START, and the book knows it
S09: at a regime transition the book is **normal in every respect** vs a time-of-day-matched
control — depth **1.003x** (CI spans 1), touch 1.002x, spread 1.003x, quote intensity 1.004x,
depth trend 1.006x. Yet S12 shows a genuine **0.767x** withdrawal before a large leg. Both are
true because the GMM label is built from **4-bar and 8-bar net moves** — it is a *lagging
confirmation* of a move that began 1–2 hours earlier, not a mark on its start.
**"The book says when" does not transfer to "the book says when a regime transition is
happening."** Any future attempt to marry book microstructure to this regime model has to fix
the event first; the transition moment is microstructurally unremarkable.

### F3 — ⚠ PER-OBSERVATION t-STATS ON BOOK DATA ARE INFLATED ~10× HERE
At the 40 pt leg threshold: **t = −12.13 per observation** on 1,592 legs, while the **day-block
CI is [0.889, 1.004] and spans one**. 1,592 minutes drawn from 31 correlated sessions are not
1,592 independent draws. The prior desk figure — 0.72x at **t = −12.45** — sits in exactly that
zone. The *effect* replicates (PC2); the *t-stat* should not be reused. **Book studies on this
desk must block by session.** Method note for the ledger.

---

## What was built (features this desk had never computed)

| feature | built | carries direction? |
|---|---|---|
| **OFI** (Cont/Kukanov/Stoikov, snapshot-to-snapshot at the touch, full window + last-5-min) | yes | **no** (r=−0.001 @60m, n=39k) |
| **Trade-sign imbalance** (ticks `aggressor`, buy- vs sell-initiated volume) | yes | **no** (0.499–0.506) |
| **Depth slope / book shape** (price distance to walk 3 rungs, per side; asymmetry) | yes | **no** |
| **Quote intensity** (touch-changing snapshots per snapshot) | yes | **no** |
| Freshest-snapshot imbalance (last snapshot strictly inside the bar), 3-level and touch | yes | **no** |
| Depth trend inside the window (late-5 vs early-5) | yes | **no** |

Each emitted three ways: raw, z-scored **within session**, and z-scored against the **same
15-min-of-day slot in other sessions, leave-one-out**. Never a global average — measured
session-dependence is depth **38 overnight → 76 at 18:00Z**, which a day median would conflate.

## Hygiene and causality actually applied
- **Crossed/locked** (ask0 ≤ bid0) dropped; **frozen-feed minutes** (one distinct ask0 in the
  minute) dropped whole — this removed 17 consecutive hours of ask0 = 30151.75 on 2026-08-17
  plus its Sunday tail, i.e. the documented 19.6 h / 200,708-snapshot incident, automatically.
- **A missing rung is UNKNOWN, never zero** — depth is built by arithmetic addition so an absent
  rung propagates NULL and the snapshot leaves the sample. Never silently summed as a thin book.
- **Decision timing**: bar *i* is stamped `bt`, closes at `bt+900`, entry is bar *i+1*'s open
  which prints at `bt+900`. Every feature uses only minutes *m* with `m + 60 ≤ bt+900`.
  **Nothing straddles the decision.** S11 additionally marched the window across a leg event at
  six offsets to show no straddle-confound is hiding in the "when" result.
- **Tape substitution justified, not assumed**: `data/backfill` 1-min ends **2026-08-18** while
  the book runs to 09-11, so the tape was rebuilt from `capture.db` 5s bars. Validated on 33,285
  overlapping bars: mean close diff **+0.0000**, sd 0.134 pt, |diff|>1 tick on **0.05%**,
  1-min return correlation **0.99983** (`s01_tape_check.txt`).
- Source is **B2** (`b2raw:gazbotv7/plain/tape/book/MNQ/`, 2026-07-31..09-11) — roughly double
  what `depth.db` holds locally. 36 day-files processed one at a time under a 900 MB scope;
  peak RSS **539 MB**.

## Power, stated plainly
- Directional tests at minute scale: **n ≈ 13,000–41,000**. Well powered; detects |r| ≥ 0.01.
- Transition-level P&L: **n = 253–347 over 31 sessions**, per-trade sd **64.4 pt**, sd of the
  mean **3.50 pt**. **Underpowered by roughly 4× for a 1 pt effect.** No P&L cell in this report,
  positive or negative, should be read as evidence on its own; that is why every conclusion here
  rests on the minute-scale tests and on familywise permutation, not on a P&L ranking.

## Disposition
- **This lead: REFUTED.** Book → direction at regime transitions. Do not re-derive. The
  conditional version (S13) is also refuted, which closes the "maybe it works when the book is
  thin" escape hatch.
- **Still LIVE and strengthened: "the book says when, not which way."** PC1 and PC2 are the
  evidence; cite these n's, not the old 610.
- **PARKED, not killed:** the book's *contemporaneous* explanatory power (r=0.688) is real and
  large. It is worthless as a forecast but it is a good **execution / slippage** object —
  nowcasting what a child order is about to pay. Different question, different study.
- **F1 and F3 are the actionable items** and belong in front of the operator before any further
  work on `bt_regime_transition.py`.

## Files
`s01_tape.py` + `s01_tape_check.txt` · `s02_regimes.py` + `s02_regimes.txt`,
`s02_transitions_{all,bookwindow}.csv`, `s02_bars15.parquet` · `s03_bookday.py` + `s03_run.sh` ·
`s04_tickday.py` + `s04_run.sh` · `s05_decision_features.py` + `s05_features.txt` +
`s05_decision_features.parquet` · `s06_ofi_anchor.py` + `.txt` + `.csv` ·
`s07_main.py` + `s07_L1_L2_direction.csv` + `s07_L3_book_as_filter.csv` + `s07_perm_max.npy` ·
`s08_baseline_and_contrarian.py` + `.txt` + `.csv` · `s09_when.py` + `.txt` + `.csv` ·
`s10_legstart_and_rightcontrol.py` + `.txt` · `s11_before_vs_during.py` + `.txt` + `.csv` ·
`s12_legsweep.py` + `.txt` + `.csv` · `s13_when_loud.py` + `.txt` + `.csv`
