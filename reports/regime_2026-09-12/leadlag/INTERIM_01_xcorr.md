# Interim 1 — MNQ<->MGC cross-correlation (descriptive)  [2026-09-12]

Data: 229 joint sessions, 314,370 joint 1-min bars, 2025-09-15 -> 2026-08-18.
Front month rebuilt per session by volume. **22.46% of `data/tape/bars/MGC/backfill_1min.parquet`
is the wrong contract** (80,332 / 357,692 bars differ from the front-month rebuild) — house rule
confirmed empirically; that file was NOT used.

XC(k) = corr(r_MGC(t), r_MNQ(t+k)).  k>0 = gold leads.

| scope | lag | train | validate | test |
|---|---|---|---|---|
| US hours | **0** | **0.188** | **0.423** | **0.447** |
| US hours | max abs non-zero lag | +0.017 @ k=-3 | +0.033 @ k=+9 | -0.020 @ k=-26 |
| all hours | **0** | **0.139** | **0.351** | **0.401** |
| all hours | max abs non-zero lag | +0.012 @ k=-3 | +0.034 @ k=-1 | -0.012 @ k=-26 |

## Two findings

1. **CONTEMPORANEOUS correlation is large, POSITIVE, and has roughly TRIPLED over the year**
   (US hours 0.19 -> 0.42 -> 0.45). Gold and the Nasdaq now move *together* intraday, not
   risk-on/risk-off opposite. This is real and it is a regime change in the *relationship*.
   Note it does not contradict the desk's prior "daily P&L correlation 0.061" — that was realised
   P&L of two different strategies, not returns of two instruments.

2. **There is NO lead-lag.** Every non-zero lag in every split is |corr| <= 0.034, and the biggest
   one is at a DIFFERENT lag and a DIFFERENT sign in each split. Under the null, sd(corr) =
   1/sqrt(n) ~= 0.003 at n~95k, so 0.034 is "10 sigma" and still explains 0.1% of variance and
   does not replicate. Tests run: 61 lags x 2 scopes x 3 splits = 366; expected false positives
   at p<0.05 = 18.

**Interim verdict on the raw cross-correlation: NULL.** Information arrives in both instruments in
the same minute. Neither leads.

Artifacts: `03_xcorr.csv`, `03_splits.json`, `02_coverage_by_hour.csv`, `front_map_{MNQ,MGC}.csv`.

---
**CORRECTION (added after step 09).** "roughly tripled" overstates it. The split-level numbers are
pooled-minute correlations; the *monthly* mean of the daily lag-0 correlation is
0.14 / 0.12 / 0.26 / 0.24 / 0.18 / 0.28 / 0.43 / 0.54 / 0.48 / 0.44 / 0.38 / 0.23
(Sep-25 .. Aug-26). Coupling ROSE into April 2026 and has been DECAYING since. It is an episode,
not a trend. See `09_daily_coupling.csv` and VERDICT.md sec.4.
