# SKEPTIC PASS — THE OPEN RIDER (ODR), robustness lens

**Mandate:** refute it. Default to REFUTED if uncertain.
**Verdict: NOT REFUTED — it survives, and it survives on tape the author never had.**
The one thing I set out to prove (17 days, in-sample thresholds, probably just the known
13:30–14:45 window) is **not** what the tape says. Two of the author's own stated wounds do not
replicate. Three new weaknesses are found and named below.

Everything here is re-derived from raw 5s bars via `gazbot7.lake.connect()` with a harness written
from scratch (`/home/alphabot/gazbot7/scratch/skeptic_odr/odr.py`). **Nothing from
`scratchpad/gf_on/` was read or reused.** Fee **$1.50/RT** throughout unless stated; $2/point; 1 lot;
entry at the 5s bar close; **stop wins ties**; every feature index strictly before the entry bar.

---

## 0. Bookkeeping errors in the claim as handed to me

| Claim | Truth |
|---|---|
| "+$4,169, 48.1% win, **102 trades**" | The report's +$4,169 / 48.1% figure is **n=129**, not 102. 102 belongs to a *different* row (§9's duty-matched no-threshold control, +$4,142/102). The claim conflates two lines. |
| priced at "$5/RT" | Correct, and **wrong in the conservative direction** — the house fee is $1.50/RT, so the true fee correction *adds* $3.50 × n. It cannot rescue a loser and does not need to rescue this one. |
| net +$4,169 | My independent re-derivation of the same spec on the same 17 days gets **n=121, +$3,483 at $5/RT**, i.e. **16% below** the author's headline. Same sign, same order, but the exact number does not reproduce — implementation detail (ATR window alignment, entry-mark inclusion) moves it by ~$700. **Treat +$4,169 as ±20%, not as a precise figure.** |

**Re-priced at the house $1.50/RT on the 17-day design tape, my harness gives +$3,907 (n=121,
47.1% win, +$32.29/trade, +0.299R).**

---

## 1. THE TEST THAT SHOULD HAVE KILLED IT — a true OOS leg the design never saw

The author explicitly scoped the study to `capture.db` (17 days, 07-16 → 08-07) and said so in §1.
But `lake.connect()` also exposes the **V5 archive: 5s MNQ bars from 2026-06-19 → 2026-07-15**, with
full 13:00–15:00 coverage on **19 further trading days**. That tape did not exist for this study.
No parameter, no window edge, no threshold was ever fitted on it.

| Leg | days | n | net | win% | $/trade | R/trade |
|---|---|---|---|---|---|---|
| **TRUE OOS — V5 06-19 → 07-15** | **19** | **115** | **+$3,526** | **47.0%** | **+$30.66** | **+0.277R** |
| DESIGN — 07-16 → 08-07 | 17 | 121 | +$3,907 | 47.1% | +$32.29 | +0.299R |
| **ALL** | **36** | **236** | **+$7,433** | **47.0%** | **+$31.50** | **+0.288R** |

**+$30.66 vs +$32.29 a trade. A 5% degradation out of sample.** Green days **15/19** OOS against
12/17 in-sample. Both sides positive on both legs (OOS: short +$2,671/62, long +$855/53). Exit mix
OOS 57 STOP / 39 TARGET / 19 TIME — the same shape.

This is the single strongest fact in the file and it is the opposite of what a curve-fit produces.
**A 17-day in-sample study that reproduces at 95% of its per-trade rate on 19 unseen days is not
overfitted.**

## 2. Strip-best / LOO / halves / bootstrap — all pass on 36 days

| Test | Result |
|---|---|
| strip best **day** | +$7,433 → **+$6,268** |
| strip best **3 days** | **+$4,486** |
| strip best 1 / 3 / 5 / 10 **trades** | +$6,827 / **+$5,901** / +$5,048 / **+$3,160** |
| strip **worst** 3 trades | +$8,349 |
| top-10 trades' share of net | **57%** (author's 17-day figure was 89% — concentration halves as n doubles) |
| **leave-one-day-out, all 36 drops** | **positive 36/36**, range +$6,268 … +$8,334 |
| halves scored independently | H1 (06-19→07-10) **+$3,280 / n=109 / +$30.10** · H2 (07-13→08-07) **+$4,153 / n=127 / +$32.70** |
| quarters | +$2,221 / +$1,059 / +$868 / +$3,285 — **all four positive**, per-trade +$39.67 / +$19.98 / +$13.56 / +$52.14 |
| day-bootstrap, 5,000 draws | mean +$7,433, 5th pct **+$3,743**, **P(net≤0) = 0.001** |
| day-clustered t-stat | **+3.79** on 36 day-clusters |

Strip-best-3-days still leaves +$4,486 and every quarter of the tape is independently green. That is
not a spike held up by one week.

## 3. Parameter surface — a plateau in STOP and TARGET, **NOT in cadence**

45-cell grid (cadence × stop_k × RR) scored on all 36 days, and separately on the true OOS leg:

- **42/45 cells positive** on the full tape; **27/27 cells with stop ≥ 2.0×ATR positive**.
- **Every stop ≤ 1.0×ATR cell is flat-to-negative.** The desk's ~1-ATR house stop is confirmed as
  the wrong instrument here — independently reproduced.
- Cap sweep 30/45/60/90 min: **+$7,281 / +$7,433 / +$5,373 / +$6,379** — all positive, 45 best but
  30 within 2%. Not a knife edge.

**★ FINDING THE AUTHOR GOT WRONG.** §7 claims *"the same shape holds at cadence 3, 10 and 15 minutes."*
On the unseen V5 tape it does not:

| cadence | OOS cells positive (of 16) |
|---|---|
| **3 min** | **4 / 16** |
| 5 min (the spec) | **13 / 16** |
| 10 min | **15 / 16** |

**The 3-minute cadence family is out-of-sample broken.** The plateau is real in stop and target and
one-sided in cadence — 5 min and slower work, faster does not. Overtrading the same signal destroys
it. Call this a **PARTIAL REFUTATION of the plateau claim**; the chosen cell sits on the good side of
the cliff, but the author did not know the cliff was there.

## 4. Reverse walk-forward — fit on V5, score blind on the design tape

48 cells fitted on the 19 V5 days only, then applied blind to the 17 design days:

| | |
|---|---|
| cells positive on DEV (V5) | 32 / 48 |
| **cells positive on HOLDOUT (design tape)** | **48 / 48** |
| mean HOLDOUT, all cells | +$3,846 |
| mean HOLDOUT of DEV-top-5 | +$4,384 (**selection tax +$538, i.e. selection HELPS**) |
| DEV-best cell | **cad 300 / stop 2.0 / RR 2.0 — the spec exactly**, DEV +$3,526 → HOLDOUT +$3,907 |

The published spec is the **#1 of 48 cells on tape it was never fitted to**. That is the cleanest
possible answer to "the thresholds were chosen on the same tape they score on."

## 5. Is it just the desk's already-known 13:30–14:45 window? **NO — but 80% of it is.**

| Slice | n | net | $/trade | R/trade |
|---|---|---|---|---|
| 13:00–15:00 (the spec) | 236 | **+$7,433** | +$31.50 | +0.288 |
| 13:30–14:45 (**the desk's validated window**) | 165 | +$5,921 | +$35.88 | +0.224 |
| **13:00–13:30 only** (outside the known window) | **74** | **+$1,427** | +$19.29 | **+0.390** |
| **14:45–15:00 only** (outside the known window) | 48 | **−$446** | −$9.29 | **−0.100** |

**Honest reading:** 80% of ODR's money ($5,921 of $7,433) sits inside a window the desk already
knows is good. The genuinely new territory is the **pre-open half hour 13:00–13:30**, which is
positive and carries the **best R/trade of any slice (+0.390)** — the desk's validated finding does
not cover it. The right edge (14:45–15:00) is **dead weight and should be cut**: it is negative on
both legs (ALL −$446, OOS −$453) and independently re-confirms the desk's 14:45 boundary.

But ODR is **not reducible** to "the window is good", and the control that proves it is one the
author never ran:

## 6. THE CONTROL THE AUTHOR NEVER RAN — same mechanics, every other hour of the day

If a wide stop + 2R target is just harvesting right-skew, it should print money all day. It does not.

| 2h window | n | $/trade | R/trade |
|---|---|---|---|
| **13:00–15:00 (spec)** | 236 | **+$31.50** | **+0.288** |
| 12:00–14:00 (straddles it) | 262 | +$18.21 | +0.180 |
| 16:00–18:00 | 188 | +$7.30 | +0.087 |
| 14:00–16:00 | 188 | +$5.46 | +0.051 |
| 06:00–08:00 | 216 | +$2.39 | +0.044 |
| 02:00–04:00 | 226 | +$1.52 | +0.029 |
| 00:00–02:00 | 190 | +$1.17 | +0.062 |
| 04:00–06:00 | 231 | +$0.61 | +0.057 |
| 20:00–22:00 | 86 | +$0.64 | −0.017 |
| 08:00–10:00 | 223 | −$4.66 | −0.102 |
| 10:00–12:00 | 245 | −$5.92 | −0.128 |
| 18:00–20:00 | 209 | −$10.37 | −0.222 |

Aggregated non-overlapping: **LONDON 07–13 −$1.89/tr (n=645) · ASIA 00–07 +$0.38/tr (n=678) ·
US-AFTER 15–21 +$0.31/tr (n=545) · IN-WINDOW +$31.50/tr.**

**The spec window is #1 of 11 and it is 4× the next-best block.** The mechanics are not a
free lunch; the clock is load-bearing. This *validates* the author's headline claim
("OPEN/NEWS is not an event cluster — it is the clock") rather than refuting it.

## 7. Direction: the rule does real work

| Same 13:00–15:00 bars, same geometry | n | net | $/trade |
|---|---|---|---|
| **ODR (sign of mom15)** | 236 | **+$7,433** | **+$31.50** |
| always LONG | 257 | −$5,373 | −$20.91 |
| always SHORT | 248 | +$2,810 | +$11.33 |
| **REVERSED (fade)** | 254 | **−$3,885** | −$15.29 |
| placebo, random direction, 200 draws | — | mean **+$1,129** (sd $2,432) | **z = +2.59, p = 0.005** |

Ride and fade are **$11,318 apart** on the same bars. Note the placebo mean is **+$1,129, not zero** —
the wide-stop/2R payoff shape *is* worth something on its own — but the direction rule is worth
$6,300 more than that, at p=0.005 over 36 days.

## 8. THE AUTHOR'S OWN "WOUND" DOES NOT REPLICATE

§7 of the original calls the day-demeaning test a **FAILURE** with t = −0.30 / −4.61 / **−5.35** at
15/30/45 min. Re-run on 36 days, **with the t-stat clustered by DAY instead of treating overlapping
1-minute samples as independent**:

| horizon | RAW | DAY-DEMEANED | **t (clustered by day, 36 clusters)** |
|---|---|---|---|
| fwd-15 min | +6.46 pt (53.3%) | −1.10 pt (50.3%) | **−0.08** |
| fwd-30 min | +8.57 pt (53.9%) | −6.48 pt (49.6%) | **−0.33** |
| fwd-45 min | +8.49 pt (51.7%) | −12.61 pt (46.2%) | **−0.57** |

The demeaned returns are still *negative in sign* — there is **no positive moment-picking skill** —
but they are **nowhere near significant**. The author's −5.35 is a **pseudo-replication artefact**:
4,224 overlapping 1-minute samples with a 45-minute forward window are perhaps 36 independent
day-clusters. **This is exactly the error the author himself diagnosed in §4 for the ER table and
then failed to apply to his own killer test.**

Two further checks kill the "it is all day drift" story outright:

- **Equal longs and shorts within every day** (removes day direction *by construction*):
  **+$5,128 on 166 trades = +$30.89/trade, +0.315R.** Per-trade rate is **unchanged** from the
  full +$31.50. The author's 17-day version degraded to +$19.69; on 36 days it does not degrade at all.
- **A passive "take sign(mom15) at 13:00, hold to 15:00" position — the literal day-drift bet —
  LOSES $3,259 over the 36 days (−$90.53/day)**, while ODR makes **+$206.48/day**. If ODR were only
  harvesting day direction, the pure day-direction bet would not be the losing side of a $10,692 gap.
- corr(|window net move|, ODR day P&L) = **+0.440** (author: +0.597). Days moving **<120 pt still pay
  +$171/day** (author claimed −$119/day). Up-window days +$178/day, down-window days +$239/day.

**The "it is only a directional harvest" wound is REFUTED on the wider tape.** What survives is the
weaker and true statement: *the entry has no moment-picking skill; the money is in the payoff shape
plus being mechanically unbiased inside the most directional two hours of the session.*

## 9. Participation claims — independently reproduced

Re-derived run detector (rolling 15-min windows, |move| ≥ 65 pt, start in 13:00–15:00, greedy
non-overlapping by size), aligned-direction, position open overlapping the run:

| | author | **my re-derivation** |
|---|---|---|
| design-17d, all runs | 62/78 = 79% | **67/87 = 77%** |
| design-17d, top-15 biggest | 15/15 = 100% | **15/15 = 100%** |
| **36-day tape, all runs** | — | **134/182 = 74%** |
| 36-day, top-15 / top-25 / top-50 | — | **93% / 92% / 92%** |

The participation claim **holds**, including out of sample. My run count differs (87 vs 78 on the
same days) because the non-overlap rule is not specified in the original — that is a spec gap worth
noting, not a discrepancy in the finding.

## 10. Costs and slippage

| | fee $1.50/RT | fee $5.00/RT |
|---|---|---|
| no slippage | **+$7,433 (+$31.50/tr)** | +$6,607 (+$28.00) |
| 0.25 pt entry slip | +$7,033 (+$29.68) | +$6,204 (+$26.18) |
| **0.50 pt entry slip** | **+$6,828 (+$28.57, +0.248R)** | +$5,992 (+$25.07) |
| 1.00 pt entry slip | +$6,141 (+$25.48, +0.224R) | +$5,297 (+$21.98) |

A full point of adverse entry slippage *and* the wrong $5 fee still leaves +$5,297 / +0.224R.
**Cost sensitivity is not where this dies.** (I could not redo the tick+quote re-price — quotes span
only 5 days — so the author's $722→$238 holdout haircut stands unaudited; the blanket 0.5 pt
assumption above is my substitute and it costs $605 of $7,433, i.e. 8%.)

## 11. The three real weaknesses (none of which is refutation)

1. **Position size.** Mean stop **57.7 pt = $115 of risk a trade**, 4–5× the live gates. 6.6 trades a
   day. Anyone deploying this at 1 lot is running a second desk, not a seventh gate.
2. **Concentration is real but improving.** Top-10 of 236 trades = 57% of net (was 89% of 129).
   Strip-best-10 leaves +$3,160.
3. **Drawdown is untested at scale.** Worst day −$901; max day-close equity drawdown over 36 days is
   also **−$901**, because the curve never had a losing run. **36 days has not shown this thing a bad
   month.** The author's promotion bar — 200 shadow trades including a non-trending open week — is
   the right bar and it is not yet met.

Also unfixed: the right window edge (14:45–15:00) is negative on both legs and should be cut before
any shadow deployment; the 3-minute cadence variant is OOS-broken and should be struck from the
"plateau" language.

## 12. Disposition

| Lead | Verdict | The named test |
|---|---|---|
| **THE OPEN RIDER (ODR) — cad 5 min / 2.0×ATR stop / 2R / 45-min cap / 13:00–15:00** | **SHADOW (upheld, strengthened)** | **True OOS on 19 V5-archive days the design never saw: +$3,526 / n=115 / +$30.66 per trade / +0.277R**, against the design tape's +$32.29 / +0.299R — a 5% degradation. LOO positive 36/36; all four quarters green; day-bootstrap P(net≤0)=0.001; reverse walk-forward picks the published cell #1 of 48 and every cell is holdout-positive; placebo z=+2.59 p=0.005; reversed −$3,885. Survives 1 pt slippage at the wrong $5 fee (+$5,297). **PROMOTE TO LIVE IF** the author's own bar is met: +0.15R over 200 shadow trades including one non-trending open week — plus the two spec corrections below. |
| **"The parameter surface is a 40-cell plateau, cadence 3/5/10/15 alike"** | **PARTIALLY REFUTED** | On the unseen V5 tape, **cadence 3 min is positive in only 4/16 cells** vs 13/16 at 5 min and 15/16 at 10 min. The plateau is real in stop_k (27/27 cells positive at stop ≥ 2.0) and in RR, and **one-sided in cadence**. Fix the language; the chosen cell is on the safe side. |
| **"The day-demeaned timing test FAILS, t = −5.35" (the author's stated wound)** | **REFUTED as stated** | Clustering the t-stat by DAY (36 clusters) instead of by overlapping 1-min sample gives **t = −0.08 / −0.33 / −0.57**. Corroborated by equal-L/S-per-day (**+$30.89/tr, unchanged**) and by the passive day-direction bet **LOSING $3,259** while ODR makes $7,433. The correct, weaker statement — *no moment-picking skill* — stands. |
| **"ODR is nothing more than the known 13:30–14:45 window"** (my hypothesis) | **REFUTED** | 13:00–13:30, entirely outside the desk's validated window, is **+$1,427 on 74 trades at +0.390R — the best R of any slice**. And the same mechanics run in every other 2h block of the day: the spec window is **#1 of 11 and 4× the next-best**, with LONDON at −$1.89/tr and ASIA at +$0.38/tr. It is not a free payoff shape and it is not only the known window. |
| **Window right edge 14:45–15:00** | **REFUTED — cut it** | −$446 on 236-trade tape (−$9.29/tr, −0.100R) and −$453 on the OOS leg alone. Independently re-confirms the desk's own 14:45 boundary. |
| **Narrow (~1 ATR) stops for this window** | **REFUTED (re-confirmed)** | Every stop ≤ 1.0×ATR cell is flat-to-negative; every stop ≥ 2.0×ATR cell is positive (27/27). Mean stop 57.7 pt against mean ATR1m 28.8 pt. |
| **"+$4,169 / 102 trades" as a precise figure** | **PARKED — do not quote it** | My from-scratch harness on the identical 17 days gives **n=121, +$3,483 at $5/RT, +$3,907 at the house $1.50/RT**. 16% below the headline, and the "102" in the claim belongs to a different row. **Revive as a quotable number only once the two harnesses are reconciled line-by-line.** |

**Working:** `/home/alphabot/gazbot7/scratch/skeptic_odr/` — `odr.py` (harness), `step1.py`…`step7.py`
(the battery, one file per block above). Data: `gazbot7.lake.connect()`, 5s MNQ bars only,
36 trading days 2026-06-19 → 2026-08-07, `symbol='MNQ'` filtered, integer `//` division throughout.
