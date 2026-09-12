# VERDICT — Cross-instrument and lead-lag research (MNQ x MGC)
**2026-09-12 · GAZBOT V7 · artifacts in `reports/regime_2026-09-12/leadlag/`**

## VERDICT: **REFUTED** for directional information. **PARKED** for one measurement worth keeping.

> **REFUTED** — no cross-instrument or session-handoff relationship between MNQ and MGC produces
> directional information that clears this desk's costs, at any horizon from 1 minute to a full US
> session, in any of three chronological periods.
>
> **The test that decided it:** `05_decompose.py` / `09_conditioned_and_control.py` — the best of
> 160 causal train cells (`MGC->MNQ`, 30-min gold move, 60-min MNQ hold, top-20% moves, US hours)
> went **hit 0.546 / 0.509 / 0.489** and **+13.17 / +3.60 / -3.65 net points** across
> train / validate / test, with the test day-block CI **[-22.5, +16.6]** and the block-level
> sign-flip control beaten by **2.22 sd on train, 1.05 on validate, -0.23 on test**. It fails
> requirement (b) and requirement (c) of the addendum out of sample.
>
> **PARKED, not a trade:** the contemporaneous MNQ/MGC 1-minute correlation is large, positive and
> non-stationary — monthly mean **0.12 (Oct-25) -> 0.54 (Apr-26) -> 0.23 (Aug-26)**. That is a real
> measurement about the desk's two instruments and it is currently *decaying*. It is a risk /
> position-sizing fact, not an entry signal.

---

## 1. What was built

| | |
|---|---|
| Panel | **229 joint sessions, 314,370 joint 1-min bars**, 2025-09-15 -> 2026-08-18 |
| Front month | rebuilt **per session by volume** from `data/backfill/*_1min.parquet` |
| Splits (chronological 40/30/30) | train 2025-09-15..2026-02-04 (91) · validate 2026-02-05..2026-05-13 (69) · test 2026-05-14..2026-08-18 (69) |
| Costs | MNQ **1.25 pt** RT ($1.50 comm + one 0.25pt tick) · MGC **0.45 pt = $4.50** RT (0.30pt spread crossed ONCE + $1.50) · hedged pair **$7.00** |

**The gold contract-mix warning is real and was measured, not assumed.**
`data/tape/bars/MGC/backfill_1min.parquet` disagrees with the front-month rebuild on
**80,332 of 357,692 bars = 22.46%**. That file was not used anywhere in this study.

**Causality contract** (`harness.py`): a signal ending at bar *t* may use only closes <= *t*; the
entry fill is the **OPEN of t+1**, never the close of *t*. With a lag-0 correlation of 0.45,
filling at the close of *t* would book the contemporaneous co-move as if it were a forecast — that
is the precise error that produced yesterday's two t=8.99 results.

## 2. Line 1 — lead-lag. NULL.

`XC(k) = corr(r_MGC(t), r_MNQ(t+k))`, US hours (`03_xcorr.csv`):

| lag | train | validate | test |
|---|---|---|---|
| **0** | **0.188** | **0.423** | **0.447** |
| best non-zero lag | +0.017 @ k=-3 | +0.033 @ k=+9 | -0.020 @ k=-26 |

Every non-zero lag in every split is `|corr| <= 0.034`. The largest is at a **different lag and a
different sign in each split**. At n~95k, sd(corr) under the null is 0.003, so these are "10 sigma"
and explain 0.1% of variance and do not replicate. Information arrives in both instruments in the
**same minute**; neither leads.

## 3. Line 1 causal grid — REFUTED.

160 train cells (5 signal windows x 4 horizons x 2 thresholds x 2 directions x 2 hour-scopes),
selected on train, confirmed on validate and test (`04_grid.csv`, `05_decompose.csv`).

* **22 of 24** headline decomposition rows have a day-block CI containing zero; the 2 that don't are
  both train.
* The `always-long` benchmark on the **identical minutes** swings **-13.9 / +6.9 / -16.6** points.
  The MNQ 60-minute drift on those minutes dwarfs and drowns any claimed signal — which is exactly
  why a raw P&L sort handed back "+13 pt/trade".
* **The naive within-session shuffled twin was itself +2.40 pt net of friction.** A control that
  makes money is a broken control: shuffling the signal re-selects which minutes clear the top-20%
  threshold, so it changes the entry population — the same defect the addendum flagged in the
  5-way label permutation. Replaced with same-minute controls (always-long, sign-flip) and with a
  **block-level** sign flip that respects the 60-minute overlap.

## 4. Line 1, second form — pairs / dislocation. REFUTED.

Dollar spread `S = 2.0*MNQ - beta*10*MGC`, beta fit on train (`beta = MNQ$ per MGC$`), z-scored on a
causal trailing window, traded on |z| > 1.5 / 2.5 (`08_spread.csv`).

* **Only 5 of 48 train cells are positive.**
* All four cells with a CI excluding zero are **validate-only** and negative on train.
* Best-looking cell (w=120, h=60, z=2.5, hedged): **-$34.0 / +$33.7 / +$20.6** — sign-inconsistent.

**The conditioning test that could have rescued it, fails and is a calendar artefact.** Conditioning
on a causal trailing-20-session coupling estimate (`09_conditioned.csv`): the **HIGH-coupling**
bucket — where the theory says a dislocation trade must live — is the *worse* bucket in 3 of 4
spread cells pooled. The one cell whose pooled CI excludes zero is `coupling_LOW`, the opposite of
the hypothesis, and `coupling_LOW` is **50% of train, 10% of validate and 0.0% of test**. The
bucket is a proxy for the calendar, not a state. Discarded.

## 5. Lines 2+3 — session handoffs and risk-on/risk-off. REFUTED.

One trade per session, entry at the OPEN of the 13:30Z bar, features ending 13:29Z
(`06_handoff.csv`, `07_paired.csv`).

* 126 cells. **Every** cell whose CI excludes zero is **validate-only** — none in train, none in
  test. 4 such cells against ~6 expected by chance.
* Nothing is positive with a CI excluding zero in more than one period. Best pooled over all 222
  sessions: `MNQ_eu -> full US session` **t = 1.74**, `RISKOFF_pre -> full US session` **t = 1.70**.
  Neither clears 2. Hit rates 0.53-0.54.
* **The deciding paired test ("does gold ADD anything?", `07_paired_gold_adds.py`).** The only
  session rules that looked alive were driven by **MNQ's own** pre-US move, so the cross-instrument
  question is C-vs-A, not C-vs-zero:

  | horizon | C - A pooled | CI | t |
  |---|---|---|---|
  | first 60m | **-4.39** | [-15.4, +6.1] | -0.77 |
  | first 120m | +4.62 | [-14.3, +24.7] | 0.45 |
  | full session | +14.38 | [-12.8, +43.5] | 1.01 |

  Adding gold is indistinguishable from not adding it, and is *significantly negative* on validate
  at 120m (-23.3, CI [-48.0, -1.8]) — i.e. sign-inconsistent. The gold leg flips the MNQ-only call
  on only **48 of 222 sessions**, and on those 48 the hit rate is **0.458 / 0.479 / 0.562**.

* **Power, stated honestly.** sd of one MNQ US-session move = **265 pt**; at n=222 the sd of the
  mean is 17.8 pt, so the minimum detectable edge at 80% power is **~50 pt ($100) per session**.
  This line of enquiry cannot resolve a small edge and I am not claiming it has. What it *can*
  exclude is a large one, and it excludes one.

## 6. Line 2, the magnitude half — gold adds nothing here either (but this was the best shot).

Direction is a coin, but this desk *can* forecast magnitude, so: does gold's pre-US state improve
the MNQ US-session range forecast? OOS R^2 of `log(MNQ US range)`, coefficients fit on train only
(`10_magnitude.csv`):

| model | validate | test |
|---|---|---|
| **A** = MNQ's own pre-US range + volume | 0.269 | 0.554 |
| **C** = A + MGC pre-US range + volume | 0.267 | **0.566** |
| **B** = gold alone | 0.188 | **-0.083** |

Paired OOS squared-error improvement from adding gold, validate+test n=134: **t = 1.18**. The fitted
gold coefficients are 0.030 and 0.011 against 0.727 on MNQ's own pre-US volume. Gold alone is
*worse than the training mean* on the test period. **MNQ's own tape already contains it.**

## 7. Multiple testing — the number that settles the whole study

**805 cells in this study carry a day-block bootstrap CI. Twelve of them exclude zero on the
upside — 1.5%. Pure chance under a true null produces 2.5%.**

This study found **fewer** apparently-significant results than noise alone would generate. There is
nothing here to correct for; there is nothing here.

## 8. What I did NOT test, and why

* **L2 depth cross-instrument** (`data/depth.db`): 2026-08-14 onward only, ~21 sessions. Given the
  MDE above, 21 sessions cannot resolve anything at session scale and would only add tests.
* **Other instruments via IBKR**: gateway is down for weekend maintenance and `gazbot7-tournament`
  is in a restart loop. No connection was attempted.
* **Tick/quote microstructure lead-lag under 1 minute**: the desk's harness cannot act on a
  sub-minute cross-instrument signal (the rider's own tick is once a MINUTE), so a finding there
  would not be actionable. Flagged as the only untested corner with a plausible mechanism.

## 9. Consequences for the desk

1. **Do not build a gold-informed MNQ router lever, and do not build the reverse.** Five independent
   framings say the sign of one instrument's move carries no usable information about the other.
2. **The `RISKOFF` idea is answered, not merely untested.** Gold/equity risk-on-risk-off exists as a
   *contemporaneous* fact and is worth ~nothing as a *forecast*. It flips the call on 48 sessions a
   year at a 0.50 hit rate.
3. **Keep the coupling measurement (PARKED).** MNQ/MGC 1-min correlation ran 0.12 -> 0.54 -> 0.23 by
   month. When the desk trades both MNQ and MGC simultaneously it is not running two independent
   books — in April 2026 it was running roughly 1.5 books, not 2. That is a sizing input. It does
   not contradict the prior "daily P&L correlation 0.061", which compared two strategies' realised
   P&L, not two instruments' returns.
4. **`data/tape/bars/MGC/backfill_1min.parquet` should carry a warning or be rebuilt.** 22.46% of it
   is the wrong contract. `01_build_front.py` in this directory does the rebuild; `front_MGC_1min.parquet`
   and `front_map_MGC.csv` are the corrected artifacts.

## 10. Artifacts

`01_build_front.py` `02_panel.py` `03_xcorr.py` `04_grid.py` `05_decompose.py` `06_handoff.py`
`07_paired_gold_adds.py` `08_spread.py` `09_conditioned_and_control.py` `10_magnitude.py`
`harness.py` · tables `03_xcorr.csv` `04_grid.csv` `05_decompose.csv` `06_handoff.csv`
`06_daily_features.csv` `07_paired.csv` `07_disagree.csv` `08_spread.csv` `09_blockflip.csv`
`09_conditioned.csv` `09_daily_coupling.csv` `10_magnitude.csv` · panels `front_MNQ_1min.parquet`
`front_MGC_1min.parquet` `panel_1min.parquet` · interims `INTERIM_01_xcorr.md` `INTERIM_02_causal_grid.md`
