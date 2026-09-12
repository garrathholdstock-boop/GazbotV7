# THE REGIME STUDY ON 10.5 YEARS — 2026-09-12

Run on `data/tape/bars/NQ/` (3,666,547 1-min bars, 2015-01-02 → 2025-07-25, 2,740 sessions) at the
desk's measured 1.25pt friction. Command:

    scripts/bt_regime_transition.py --source nq_lake --bar 15 --states 4 --friction 1.25 --zscore --by-era

## ⛔ THE FIRST RUN WAS INVALID, AND THE GUARD IS WHY WE KNOW

3 states on the long tape produced **degenerate labels** — BULLISH/BEARISH separated by
**−0.03 ATR** of 8-bar drift, with the "bearish" state drifting UP. The mixture had clustered on
EFFICIENCY (0.10 / 0.35 / 0.54), not direction, because the raw features carry two scales and a
diagonal-covariance mixture weights whichever is wider. On 11 months of MNQ that was drift; on 10.5
years of NQ it was efficiency. **Fix: standardise on TRAIN (`--zscore`) and use 4 states** → d8_gap
**4.70 ATR**, BULLISH +2.64 mean return against BEARISH −3.31. The `d8_gap` guard now prints on every
run and says DEGENERATE out loud. Banked from last night's finding that 8 of 72 fitted models had
this defect and reported like any other cell.

## THE RESULT — the edge is REAL, CONSISTENT, and a quarter of what it costs

Sign-flip control (identical bars, identical n, direction reversed), 26,000–35,000 trades per cell:

| hold | n | real net | flipped | **GROSS edge** | t |
|---|---|---|---|---|---|
| 30m | 34,821 | −1.11 | −1.39 | **+0.14 pt** | 1.07 |
| 60m | 34,038 | −0.94 | −1.56 | **+0.31 pt** | 1.62 |
| 90m | 33,221 | −0.91 | −1.59 | **+0.34 pt** | 1.45 |

**Real beats its flipped twin in 12 of 12 cells.** The direction call is not nothing — it is
**+0.15 to +0.34 points**, against **1.25 points** of friction. Every net cell is negative in TRAIN,
VALIDATE and TEST.

In scale-free units, with a **year-clustered** error (11 years, not 33,000 pseudo-independent trades):

| hold | gross | t naive | **t by year** | friction today | net at 2025 prices |
|---|---|---|---|---|---|
| 30m | +0.155 bp | 1.38 | **1.97** | 0.60 bp | **−0.44 bp** |
| 60m | +0.259 bp | 1.63 | **1.79** | 0.60 bp | −0.34 bp |
| 90m | +0.210 bp | 1.08 | 1.07 | 0.60 bp | −0.39 bp |

## ★ THE STRUCTURAL FINDING — our costs have fallen 4.7× in a decade and will keep falling

Friction is fixed in dollars and ticks; the index is not. The same 1.25pt round trip was:

    2015  2.82bp     2018  1.79bp     2021  0.87bp     2024  0.65bp
    2016  2.75bp     2019  1.64bp     2022  0.99bp     2025  0.60bp
    2017  2.18bp     2020  1.25bp     2023  0.89bp

**A strategy unchanged since 2015 is 4.7× cheaper to run today**, purely because NQ is at 23,000
instead of 4,400. That is why the per-year net turns positive in 2023 (+0.31 pt), 2024 (+0.09) and
2025 (+1.24) — **and why the original 11-month MNQ study saw +0.82/+0.47: it sampled only that era.**
The gross edge in bp is flat-to-noisy across the whole tape (mean +0.19bp, year sd 0.77bp); what
changed is the cost, not the signal.

**What would have to be true to trade it:** friction below ~0.2bp. Either the index near 60,000, or
the spread leg (0.50pt of the 1.25) removed — and passive entry is already dead on this desk.

## AND THE VOL-CONDITIONING STORY IS REFUTED

The per-year pattern (negative in the 2020 and 2022 vol shocks, positive in the calm bull years)
does not survive an honest test. ATR quintile cuts chosen on TRAIN YEARS ONLY (2015-2019), applied
unchanged to 2020-2025:

| ATR quintile | TRAIN gross bp | TEST gross bp |
|---|---|---|
| Q1 quietest | +0.33 | −0.40 |
| Q2 | +0.06 | +0.71 |
| Q3 | +0.09 | −0.47 |
| Q4 | −0.10 | **+1.60 (t=3.04)** |
| Q5 loudest | +1.06 | −0.52 |

TRAIN's best quintile is TEST's worst; TEST's only significant cell is the one TRAIN ranked last.
**The ordering does not carry. Vol does not condition this edge.**

## VERDICT

**REFUTED as tradeable — PARKED as a measurement.** On 10.5 years and eleven regimes the
regime-transition direction call is worth **+0.15 to +0.34 points a trade** and costs **1.25** to
take. This is the first time the desk has had enough tape to say the edge is *real and too small*
rather than *undetectable*, and that is the difference between a null and a measurement.

---

# THE SAME STUDY ON GOLD — 2026-09-12

**Gold has no long intraday tape.** `data/tape/bars/GC/` is **daily only** (6,532 bars,
2000-08-30 → 2026-09-11); the minute history is 13 months. So gold gets two runs, and neither is
the multi-regime intraday test NQ got.

**Friction is gold's own constant: 0.45pt.** `MGC_FEE_RT = $4.50` at $10/point — a round trip
crosses the 0.30pt spread ONCE ($3.00) plus $1.50 of commission. Not MNQ's 1.25pt, and not the
$7.50 that once killed a gold lead by mistake.

## 1. INTRADAY — corrected front-month MGC, 13 months, 15-min bars

States are directional (d8_gap **4.39 ATR**, BULLISH +2.47 mean return vs BEARISH −2.89). Run on
the **rebuilt** front-month series, never `backfill_1min.parquet`, 22.46% of which is a dying contract.

| hold | n | real net | flipped | **GROSS** | t |
|---|---|---|---|---|---|
| 30m | 3,630 | −0.30 | −0.60 | **+0.15** | 0.75 |
| 60m | 3,577 | −0.19 | −0.71 | **+0.26** | 1.03 |
| 75m | 3,541 | −0.17 | −0.73 | **+0.28** | 0.94 |

**Same shape as MNQ: real beats its flipped twin in every cell, and it is still too small.** But the
RATIO is much better — gold's gross edge is **16–62% of its friction**, against MNQ's 12–27%, because
gold's cost in points is 2.8× smaller while the edge is comparable. The 120m cells are the first
positive net this study has produced anywhere (+0.16 / +0.17 pooled), on t = 0.2–1.7. Not a finding;
the first thing that is not obviously dead.

## 2. DAILY — GC, 26 years, holds of 2 to 8 DAYS

⚠ Held overnight, which this desk does not do. Run to learn whether the effect exists where cost
cannot bind, not as a candidate.

**The sign REVERSES.** Gross is negative in **all 12 cells** (−0.36 to −3.91 pt, t to −1.87): on
daily gold, joining the established regime is worse than fading it. Not significant, and the
disagreement with the intraday result is the point — the effect does not survive a change of
instrument AND horizon together.

## ★ THE LESSON THAT QUALIFIES LAST NIGHT'S CONCLUSION

**A long tape is not a large sample.** 26 years of daily gold yields **627–848 transitions — about
24 a year**, so not one calendar year clears a 30-event floor and the per-era table is empty. The
daily design fires too rarely to ever accumulate power, no matter how far back the history goes.

Last night's blocker was stated as "we need more data". The precise version is: **we need more
EVENTS, and only intraday bars generate them.** For gold that means buying intraday history —
depth of years does nothing on its own.
