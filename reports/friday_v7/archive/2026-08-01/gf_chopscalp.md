# GREENFIELD — CHOP-DAY TURN SCALP (MNQ)
### Verdict: **HONEST NULL.** One marginal candidate survives to SHADOW-only; it does not clear the +$200–300/chop-day bar on evidence.

*Built 2026-08-01. Tape: MNQ, 6 session days (2026-07-24, 27, 28, 29, 30, 31). Working dir `/home/alphabot/gazbot7/scratch/chopscalp/`.*

---

## 0. THE BAR, RESTATED FROM LIVE DATA

Actual live desk P&L (`gazbot7.db.trades`), so we are arguing about a real number and not a vibe:

| day | regime | live n | live net |
|---|---|---|---|
| 2026-07-24 Fri | directional-down | 47 | **−$579** |
| 2026-07-27 Mon | **CHOP** | 37 | **−$155** |
| 2026-07-28 Tue | **CHOP** | 25 | **−$22** |
| 2026-07-29 Wed | trend | 32 | +$1,349 |
| 2026-07-30 Thu | trend | 82 | +$94 |
| 2026-07-31 Fri | **CHOP** | 27 | **−$569** |

**The chop-day donation is −$746 over 3 days = −$249/chop-day.** That is the prize. The operator's ask was to convert it into +$200–300/day, i.e. a ~$450–550/day swing.

Day-level regime evidence (RTH 13:30–20:00 UTC, ATR14 on 1-min bars, `range_eff = |net| / range`):

| day | RTH range | net | range_eff | ATR14 |
|---|---|---|---|---|
| 07-24 | 418.75 | −237.25 | 0.567 | 25.0 |
| 07-27 | 678.50 | −391.75 | 0.577 | 27.1 |
| 07-28 | 476.50 | −36.50 | **0.077** | 25.0 |
| 07-29 | 782.25 | −524.00 | 0.670 | 33.7 |
| 07-30 | 484.75 | +342.25 | 0.706 | 22.8 |
| 07-31 | 646.00 | −204.75 | **0.317** | 27.3 |

Note: only **07-28** is a textbook round-trip chop day. **07-27** is a −392 pt directional day that *felt* like chop because it went there in violent whipsaws, and **07-31** is a mixed day. This matters — it is one reason "fade the range" struggles: on two of the three "chop" days there was no range to fade.

---

## 1. DATA — AND ONE IMPORTANT SOURCING FIX

| source | content | coverage |
|---|---|---|
| `gazbot7/data/capture.db` `ticks` | MNQ trade prints w/ aggressor, 10.08M rows | 07-23 22:00 → 07-31 21:00 UTC ✅ |
| `gazbot7/data/capture.db` `book` | 5-deep L2 | **starts 07-27 21:33 UTC — misses 07-27 RTH entirely** ❌ |
| `alphabot2/data/depth.db` `depth_snap` | **10-deep L2, uniform 250 ms cadence** | 07-12 → 07-31, 93k snaps/RTH-day, *all six days* ✅ |

**Fix applied:** all L2 work in this section uses `depth.db` (10-deep, 250 ms), not `capture.db.book`. Using `capture.db.book` would have silently dropped 07-27 — one of the three target days — from every book test. Median inter-snapshot gap 251 ms, p90 252 ms, on every day. This is a clean, uniform L2 series.

Artifacts built: `ticks.parquet`, `depth10.parquet`, `frame1s.parquet` (1-second tape+book grid), `feat2/feat3.parquet` (124 per-second features), `pool.parquet` (candidate turns + tick-honest outcomes).

**Fill model (tick-honest, deliberately unkind):**
- entry = marketable — SHORT hits the bid, LONG lifts the ask (real `bid1p`/`ask1p` at the signal second);
- target = resting LIMIT → requires a print **through** by one tick (0.25) before it counts as filled;
- stop = STOP-MARKET → triggers on touch, fills **one tick worse**;
- stop wins all ties inside a tick gap;
- fee $3.00 round-trip (memory `[[execution-cost-autopsy-stage1]]`: real fee ≈$1.50/side, not $5);
- MNQ $2/point. **Total friction ≈ 1.75 points/round-trip.** Hold that number — it is the whole story.

---

## 2. THE COST WALL (why "scalp tiny" is the wrong instinct)

Breakeven win-rate, exactly, for a stop `S` points and target `R·S`:

| shape | net win | net loss | breakeven win% |
|---|---|---|---|
| S=20, R=0.5 | +$17 | −$43.5 | **71.9%** |
| S=20, R=1.0 | +$37 | −$43.5 | **54.0%** |
| S=30, R=0.5 | +$27 | −$63.5 | **70.2%** |
| S=30, R=1.0 | +$57 | −$63.5 | **52.7%** |

The fee is a *fixed* tax, so **the smaller the target, the higher the hurdle**. This is the arithmetic behind the preview finding, and it holds in every cut below: **0.5R at a tight stop is the single worst configuration in the entire study.** The operator's "bank at 0.5R" instinct only survives when it is paired with a **wide** stop (so the fee is diluted), and even then it barely survives.

---

## 3. BASELINE — the naive turn-fade reproduces the preview NULL exactly

Candidate turns: every new 300-second local extreme, RTH+late (13:30–21:00 UTC), 30 s dedupe → **1,675 events / 6 days (279/day)**.

| stop | R | hold | n | win% | breakeven | $/trade |
|---|---|---|---|---|---|---|
| 20 | 0.5 | 600 | 1675 | 64.4% | 71.9% | **−$4.23** |
| 20 | 1.0 | 600 | 1675 | 49.6% | 54.0% | **−$3.43** |
| 30 | 0.5 | 900 | 1675 | 65.9% | 70.2% | **−$3.18** |
| 30 | 1.0 | 900 | 1675 | 50.7% | 52.7% | **−$2.53** |

Win-rates sit **2–7 pp below** the breakeven line at every R — the preview's "coin-flip, right on the line" finding, reproduced to the point. At R=1.0 the win-rate is **below 50%**, i.e. the price process at a fresh local extreme is a random walk plus a whisker of continuation, not reversion.

**Gross-vs-net decomposition** (fee zeroed, slippage/spread kept — the honest measure of whether an *edge* exists at all):

| stop | R | n | win% | **gross pts/trade** | net $/trade |
|---|---|---|---|---|---|
| 1.6·ATR | 0.50 | 490 | 69.4% | **+1.63** | +$0.26 |
| 1.6·ATR | 0.75 | 385 | 59.5% | **+1.81** | +$0.62 |
| 1.2·ATR | 1.00 | 451 | 52.1% | +0.26 | −$2.49 |
| 1.2·ATR | 0.50 | 621 | 65.7% | −0.51 | −$4.02 |
| 1.6·ATR | 1.00 | 339 | 49.6% | −0.94 | −$4.87 |
| 1.2·ATR | 1.50 | 370 | 41.4% | −2.25 | −$7.50 |

### ★ The single most important number in this section
> **Best gross edge of the turn-fade = +1.81 points/trade. Round-trip friction = 1.75 points/trade.**
> The mean-reversion at a local extreme is REAL but it is **~0.06 points net** — the cost eats 97% of it.

Sanity check by inversion: flipping the same signal to **breakout continuation** at the same extremes gives −$5.29/trade vs the fade's −$2.49. The ~$2.80 spread is the reversion tendency, ≈1.4 points gross — consistent. **There is a real fade edge here; it is simply an order of magnitude too small to pay a $3 ticket.**

To clear +$250/chop-day at the observed ~30 trades/day you need **+$8.3/trade = 4.2 pts net = 5.9 pts gross**. That is **3.3× the best gross edge measured anywhere in this study.** Everything below is an attempt to find selectivity worth 3.3×.

---

## 4. THE L2 LEAD — turned, hard, and it does not hold on MNQ

The operator's direction was explicit: the separator must be the **book** — far-side absorption / depletion at the extreme, the `exhaustion_short` / `footprint.py` lineage. Every version of that was built and tested.

### 4.1 First, the physical fact that kills it

| MNQ, RTH | value |
|---|---|
| median displayed size, **top of book** | **3.0 contracts** |
| median displayed, top-3 | 17.2 |
| median displayed, **full visible 10-deep** | 86.2 |
| median **60-second traded volume** | **2,664 contracts** |
| ⇒ visible 10-deep book turnover | **≈31× per minute** |
| median individual print size | **1 lot** (mean 1.82; only 0.62% of prints ≥10 lots) |

> **On MNQ there is no wall to absorb into.** The entire visible 10-deep book is ~2 seconds of flow. The `exhaustion_signal` "wall" test (`ask1s ≥ 1.5 × bid1s`) is, in practice, *3 lots versus 2 lots* — a coin-flip comparison of two tiny, ephemeral, largely-cancelled queues. And the tape is retail micro-flow: median print 1 contract, so there is no institutional absorption footprint to read either.
>
> For contrast, over the same window `depth.db` shows **MES top-of-book averages 23.9 lots and 10-deep 527 lots — 6.8× / 6.1× deeper than MNQ.** "Absorption" is a physical quantity on MES. On MNQ it is mostly noise.

This is the mechanistic root cause under every L2 null below, and it independently re-explains memory `[[run-catcher-null-all-microstructure]]` and the earlier `l2_depletion_probe` result.

### 4.2 Unconditional sanity check — does book imbalance predict *anything*?

Ask-share of depth (top-1 / top-3 / top-10) → forward return at H = 10 s / 30 s / 60 s / 300 s, whole RTH tape, all 6 days:

**corr = 0.000 to 0.015, non-monotone in every quintile profile.** Zero. Before any conditioning, MNQ's L2 imbalance carries no directional information. (Replicates `l2_depletion_probe`.)

### 4.3 The graves — every L2 / footprint variant by name

Each was scored on the **chop days**, cfg stop-30/R-1.0/900 s, quartile profiles with per-day breakdown and t-stats.

| # | GRAVE | best \|t\| | cause of death |
|---|---|---|---|
| **G1** | **Static far-side depth share at the extreme** (`opp1/opp3/opp10`) | 1.7 | Non-monotone; and the *sign is backwards* from the hypothesis — a **thick** opposition wall predicts the fade **losing** (−$8.45/trade, 0/6 days green). Consistent with §4.1: the "wall" is 3 lots and gets run. |
| **G2** | **Far-side depletion / building** (`opp*_d15/30/60/120`, `oppd3_*`, `oppd10_*`) | 1.6 | Flat. Deltas of a 3-lot queue are noise. |
| **G3** | **Opposition depth z-score vs its own 15-min baseline** (`oppz1/3/10`, `supz*`) | 1.7 | Non-monotone, fails leave-one-day-out. |
| **G4** | **`exhaustion_signal` (live footprint gate) as a standalone chop scalp** — net≥400/250, move≤2/3 pt, wall≥1.5/1.3, L1 and top-3 variants, at its live 8 pt stop / 12 pt target / 120 s | — | **Negative on all 6 days in every parameterisation** (best −$0.13/trade, worst −$11.40). Chop-day net −$158 to −$604. The proven lineage does not transfer to a chop-day scalp. |
| **G5** | **Absorption-vs-cancellation** (`repl5/15/30`: does the far-side queue *refill* faster than it is eaten? `cxl*`: is depth vanishing without trades = spoof-pull?) | 1.8 | **Degenerate.** Quartile boundaries land at 0.999 / 1.000 / 1.001 — because traded volume dwarfs queue change by ~30×, so the ratio is pinned at 1. The measurement is not resolvable on MNQ. |
| **G6** | **Absorption dwell at the level** — time spent within 2 pt of the 30-min extreme, volume traded near the level, `absr = near-level volume / displayed opposition depth` | 1.5 | Non-monotone, 2/3 chop days wrong-signed. |
| **G7** | **Big-print / institutional absorption** — max print, volume in ≥10-lot prints, signed big-print delta *against* the leg, avg print size, 30 s & 60 s windows | 2.2 | Non-monotone, day-inconsistent. Root cause: median print = 1 lot, 0.62% ≥10 lots — there is no institutional footprint in MNQ prints. |
| **G8** | **Delta divergence at the retest** — 60 s aggressor delta now vs at the moment the range extreme was originally set (`ddiv900/1800/3600`) | 0.7 | Flat. |
| **G9** | **Flow-per-point absorption** (`abs10/20/60/120` = push flow ÷ price progress; `push*`, `prog*`) | 1.8 | Non-monotone; the "heavy flow, no progress" cell is not distinguishable from the rest. |
| **G10** | **Retest / double-top structure** — fade only an *established* range extreme (extreme set ≥180/300 s ago, price back within 1 pt), W = 15/30/60 min, ± delta divergence | 2.8 (**wrong sign**) | **Actively negative**: −$11.30 to −$16.06/trade, win 34–40%, chop-day net −$1 to −$105/day. Adding the divergence filter did not rescue it. The cleanest structural version of "fade the range extreme" is the *worst* variant tested. |
| **G11** | **VWAP-flat "is it actually ranging" filter** (the operator's explicit ask): fade only when `er30 ≤ 0.025` and \|VWAP slope\| ≤ 0.035 ATR/min | — | **Lifts the fade from −$2.53 to +$7.60/trade — but 100% of the profit is on the TREND days** (07-29 +$868, 07-30 +$1,156) and it **loses on the chop days** (−$368). Cause of death: on chop days the "ranging" windows are not ranges, they are the whipsaw itself; on trend days they are genuine consolidations. It makes money on the days we already make money. Textbook confirmation of the operator's own blanket-config warning. |

---

## 5. THE ONE THING THAT DID SHOW STRUCTURE — and why it is still not an edge

The features that separated were **not** book features. They were **vetoes**, and they were the operator's own priors:

Chop-days-only quartile profiles (cfg stop-30/R-1.0/900 s, per-day P&L shown):

```
er60 (60-min efficiency ratio)        rngW1800 (30-min range ÷ ATR)
q3 = 0.028–0.066  →  −$14.39/tr  t=−3.52   q0 = 2.56–4.24  →  −$12.32/tr  t=−3.09
   (07-27 −1780, 07-28 −102, 07-31 −1082)     (07-27 −942, 07-28 −302, 07-31 −1294)

atr14                                  sod (time of day, UTC)
q3 = 34.7–61.6    →  −$10.27/tr  t=−2.46   q1 = 15:06–17:00 → −$8.65/tr  t=−2.07
```

Read mechanistically, and all four are sound:
1. **Don't fade a trending leg** (high `er60`) — validates `[[rearm-momentum-needs-er-climb-not-delta-blip]]` in the mirror.
2. **Don't fade in high vol** (ATR > ~30) — the exhaustion ATR-gate, independently rediscovered.
3. **Don't fade a compressed range** (30-min range < 4.2 ATR) — a compressed extreme is a *breakout*, not a range test. New, and the strongest single veto found.
4. **Don't fade the US open** — validates `[[us-open-dont-bench-trend-rider]]` / `[[us-open-arm-veto-gates-not-churners]]`.

### 5.1 The trap: parallel events ≠ a tradeable sequence

Stacking all four vetoes on the **event pool** gives n=557, win 58.2%, **+$5.98/trade, chop +$3,434 (+$1,145/chop-day), t=2.71.** That looks like the answer.

It is not. Those 557 events overlap — with a 30 s dedupe and a 900 s hold you are "holding" up to 30 positions at once and counting the same move many times. Re-run **sequentially, one position at a time** (the only honest form):

> **n=101, net +$361, win 55.4%, +$3.57/trade, t=0.66. Chop-day = +$135/day.**

**A 3× collapse.** Every parallel-pool number in a fade study is inflated by roughly the overlap factor. *(Recommend this be a standing rule for the lab: fader studies must be scored sequentially.)*

### 5.2 The full policy grid — and the multiple-testing kill

1,152 sequential policies: `er60` ∈ {0.022, 0.028, 0.04, off} × `atr_max` ∈ {18, 22, 28, off} × `range ≥` {3.5, 4.2, off} × stop ∈ {0.5, 0.8, 1.2, 1.6}·ATR × R ∈ {0.5, 1.0, 1.5} × hold ∈ {600, 900}, all with the ≥17:00 UTC veto.

| grid statistic | value |
|---|---|
| mean chop-day P&L across all 1,152 configs | **−$36** |
| sd | $131 |
| fraction with chop-day > 0 | **40.9%** |
| fraction with $/trade > 0 | **18.8%** |
| **best** config chop-day | **+$288** |

**+$288 is 2.5σ above the grid mean, from 1,152 trials.** Under an iid-normal null the *expected maximum* of 1,152 draws is ≈ +$455/chop-day — the observed best is **below** what pure noise would be expected to produce. Marginal effects confirm it: averaging over the grid, no R and no stop multiple is meaningfully positive (best marginal: stop = 1.2·ATR at +$37/chop-day; every R marginal is negative).

The best-of-grid config for the record — `ATR ≤ 28, 30-min range ≥ 3.5 ATR, ≥17:00 UTC, stop 1.2·ATR, R = 1.0, hold 600 s`:

| | n | win% | $/trade | t | chop net | chop/day | trend net | chop days green |
|---|---|---|---|---|---|---|---|---|
| | 197 | 58.9% | +$4.42 | **1.50** | +$840 | **+$280** | +$30 | **3/3** |

Strip-the-best-trades on the chop days: strip 1 → +$260/day, strip 3 → +$225/day, strip 5 → +$192/day, strip 10 → **+$113/day**. It is *not* carried by one lucky trade (best chop trade is only +$61) — that part is genuinely healthy. But 07-28 alone supplies $454 of the $840, and **t = 1.50 selected from 1,152 trials is not evidence.**

### 5.3 The decisive test — is *anything* here learnable out of sample?

Leave-one-day-out, 76 features (price, stretch, flow, footprint, absorption, 10-deep book), 6 folds. For each held-out day: pick the single best feature+threshold rule on the other 5 days, apply it blind to the held-out day.

| held out | rule learned | in-sample $/tr | **OOS $/tr** |
|---|---|---|---|
| 07-24 | `slp30_a ≤ 0.029` | +7.04 | **−12.65** |
| 07-27 | `oppz3 ≤ 0.876` | +7.20 | **−5.21** |
| 07-28 | `er15 ≤ 0.014` | +6.81 | **−12.44** |
| 07-29 | `opp3 ≤ 0.465` | +6.76 | +0.03 |
| 07-30 | `opp3 ≤ 0.465` | +7.89 | **−4.19** |
| 07-31 | `oppz10 ≤ 0.942` | +7.30 | **−5.43** |
| | | **mean +$7.17** | **TOTAL −$5.84 (n=318)** |

And an L2-regularised logistic regression on **all 76 features**, same LOO protocol, trading the top-30% predicted:
**OOS correlation with outcome = −0.011, −0.093, +0.059, −0.087, −0.004, +0.027 → OOS −$8.05/trade (n=530).**

> **In-sample selection buys +$7/trade. Out of sample the identical rules pay −$6/trade.** Nothing in the feature set — including every L2 book feature, the footprint battery, and the operator's absorption constructs — generalises across a single day boundary. **This is the null, stated as sharply as the data allows.**

### 5.4 Regime instability (the operator's segmentation requirement, honoured)

Scoring the fade (stop 1.6·ATR / 0.5R / 900 s) per regime segment — every 2-way cut flips sign:

| segment | n | win% | $/trade |
|---|---|---|---|
| ER < 0.02 (ranging) | 274 | 73% | **+2.77** |
| ER 0.02–0.04 | 147 | 65% | **−6.97** |
| ER > 0.04 (**trending**) | 55 | 71% | **+9.80** ← contradicts the ER veto found in §5 |
| ATR < 18 | 132 | 70% | −0.22 |
| ATR 18–28 | 166 | 73% | **+3.38** |
| ATR > 28 | 178 | 67% | **−1.45** |
| CHOP-day × open 13:30–15:30 | 70 | 61% | **−10.94** |
| TREND-day × open 13:30–15:30 | 74 | 73% | **+7.44** ← same clock, opposite sign |
| CHOP-day × mid 15:30–17:30 | 60 | 75% | **+7.65** |
| TREND-day × mid 15:30–17:30 | 53 | 60% | **−10.83** ← same clock, opposite sign |

A real regime effect is *stable within its segment*. This one changes sign on every conditioning axis. That is the signature of no edge, not of a regime-conditional edge.

---

## 6. THE R SWEEP — the operator's cheat-sheet guesses, tested

168 exit configs on the **unfiltered** signal (deliberately *not* on a filtered subset, so exit conclusions are uncontaminated by entry-filter selection): stop ∈ {0.8…2.5}·ATR × R ∈ {0.25…1.5} × hold ∈ {300, 600, 900}.

**Only 3 of 168 configs are net-positive**, and they are one corner:

| stop | R | hold | n | win% | gross pts | **net $/tr** | chop/day | chop days green |
|---|---|---|---|---|---|---|---|---|
| 1.6·ATR | 0.75 | 600 | 385 | 59.5% | +1.81 | **+$0.62** | +$8 | 1/3 |
| 1.6·ATR | 0.50 | 900 | 476 | 70.2% | +1.79 | **+$0.58** | +$67 | 1/3 |
| 1.6·ATR | 0.50 | 600 | 490 | 69.4% | +1.63 | **+$0.26** | −$103 | 1/3 |

Marginal means (the plateau test — a real optimum shows a plateau, a fitted one shows a spike):

| R | 0.25 | 0.40 | 0.50 | 0.60 | 0.75 | 1.00 | 1.25 | 1.50 |
|---|---|---|---|---|---|---|---|---|
| gross pts | −0.69 | −0.41 | −0.48 | −0.79 | −0.85 | −1.58 | −1.91 | **−2.16** |
| net $/tr | −4.37 | −3.81 | −3.96 | −4.57 | −4.71 | −6.16 | −6.81 | **−7.32** |

| stop | 0.8 | 1.0 | 1.2 | 1.4 | **1.6** | 2.0 | 2.5 |
|---|---|---|---|---|---|---|---|
| net $/tr | −3.66 | −4.48 | −4.46 | −6.52 | **−3.98** | −6.21 | −7.19 |

**No plateau — a single corner spike at stop = 1.6·ATR.** Verdict on the guesses:

| operator's prior | proven? |
|---|---|
| fader **Lot-A 0.5R** | **directionally right, and only with a WIDE stop.** 0.5R is the best R marginally, but only survives at 1.6·ATR (≈32 pt) stops. At a tight stop 0.5R is the worst thing in the study. |
| fader **Lot-B 1.5R** | **FALSIFIED for this entry.** 1.5R is the worst R at every stop (gross −2.16 pts, net −$7.32/trade). A chop-turn fade has no runner. |
| "scalp tiny, bank fast" | **FALSIFIED as stated.** Tiny target + tiny stop = maximum fee tax. The shape that works is *wide stop, small target, high hit rate* — which is a large-risk scalp, not a tiny one. |
| hold | shorter is better: 300 s > 600 s > 900 s on average ($−4.47 / −5.22 / −5.96 per trade). |

---

## 7. VERDICT

**NULL.** A chop-turn scalp built on price, VWAP stretch, aggressor flow, footprint absorption and the 10-deep L2 book **does not clear the +$200–300/chop-day bar**, and does not clear zero on evidence.

| the ask | measured |
|---|---|
| per-trade edge | **best gross +1.81 pts vs 1.75 pts friction ⇒ ≈ +$0.1 to +$0.6/trade net, unfiltered** |
| win% | 59–74% depending on R, **2–7 pp below breakeven** unfiltered |
| projected chop-day P&L, honest | **+$67/chop-day** (best unfiltered exit corner), 1/3 chop days green |
| projected chop-day P&L, best-of-1,152 | +$280/chop-day, 3/3 green, **but t = 1.50 from 1,152 trials, and the LOO test says it will not repeat** |
| clears +$200–300/chop-day? | **No.** |
| does it bleed the trend days? | No — the best config is +$30 on Wed/Thu, i.e. harmless. That is its only clean property. |

**What to do with the chop-day money instead:** the −$249/chop-day donation is recoverable **with certainty by benching**, not speculatively by adding a gate. The four vetoes this study *did* validate — no fading into high `er60`, no fading at ATR > ~30, no fading a compressed (<4.2 ATR) 30-min range, no fading 13:30–17:00 UTC — are worth more as **router benching evidence** than as a new gate. This is the same lesson as `[[us-open-arm-veto-gates-not-churners]]` and `[[some-days-stay-out-fully-flat.md]]`: on these days the edge is the OFF switch.

**If anything is armed, arm it SHADOW-only**, clearly labelled unproven:

```
gate:        chop_turn_fade         (SHADOW ONLY — NOT a promotion candidate)
trigger:     new 300s local extreme
vetoes:      ATR14(1m) <= 28
             30-min range >= 3.5 * ATR      (there must BE a range)
             time >= 17:00 UTC              (never the US open)
direction:   fade (short the high / long the low)
entry:       marketable, hit bid / lift ask
stop:        1.2 * ATR        target: 1.0R        hold cap: 600 s
one position at a time; 60 s cooldown after exit
observed:    n=197/6d, 58.9% win, +$4.42/tr, t=1.50, chop +$280/day, trend +$30
status:      INCUBATE. Needs ~15-20 more captured chop days before it is re-judged.
             Prior expectation given the LOO result: it reverts to ~0.
```

---

## 8. THE ONE STONE UNTURNED — named, with its blocker

> **Run this identical study on MES, on 2026-07-12 → 07-17.**

The L2 lead did not fail because absorption is a bad idea. It failed because **MNQ's book is too thin for absorption to be a measurable quantity**: 3 lots at the top, 86 lots across the full visible 10-deep book, versus 2,664 contracts of flow per minute — a 31× turnover — and a median print of 1 contract. Every far-side/absorption construct in §4 was trying to read a signal out of a 3-lot queue.

Over the same window `depth.db` shows **MES averages 23.9 lots at the top and 527 lots 10-deep — 6.8× / 6.1× MNQ.** On MES, "the far side is absorbing / depleting at the extreme" is a real, resolvable physical measurement.

**The window exists and the blocker is known:** `alphabot2/data/depth.db` holds 10-deep MES book for 07-12 → 07-31 (2.94M snapshots), and `alphabot2/data/ticks.db` holds MES trade prints for 07-05 → 07-17 (3.71M prints). **They overlap on 2026-07-12 → 07-17 — roughly 4–5 session days with both a tick tape and a 10-deep book.** `gazbot7/data/capture.db` carries MNQ ticks only, which is why this could not be run inside the V7 lab as-is.

Two smaller stones, in order:
2. **Cross-instrument confirmation** (ES/NQ lead-lag, index internals). Not captured anywhere — the turn may be visible in a *correlated* book even when it is invisible in MNQ's own.
3. **More tape.** Everything above rests on **three** chop days. The LOO result is decisive about *learnability*, but three days cannot rule out a small effect that needs 20 days to see. If MNQ capture keeps running, re-run this exact harness at ~15 chop days; every script is parameterised and re-runnable.

---

## Appendix — reproducibility

All in `/home/alphabot/gazbot7/scratch/chopscalp/`:

| file | purpose |
|---|---|
| `extract_ticks.py`, `extract_book.py` | capture.db ticks + depth.db 10-deep → parquet |
| `build_frame.py` | 1-second tape+book grid (`frame1s.parquet`) |
| `feat2.py`, `feat3.py` | 124 per-second features: stretch anchors, ER, flow, book, rolling arg-extreme age, absorption dwell |
| `outcomes.py` | tick-honest first-touch fill engine (limit-through targets, slipped stops, stop wins ties) |
| `pool.py`, `scan.py` | candidate-turn pool + side-signed features + quartile scanner w/ per-day consistency |
| `bt.py` | **sequential** one-position-at-a-time backtester ← use this, not the pool, for any fader |
| `grid1.py`, `grid1.csv` | 1,152-config policy grid |
| `exit_sweep.csv` | 168-config R/stop/hold sweep on the unfiltered signal |
| `loo.py` | leave-one-day-out learnability test (best-single-rule + logistic) |
| `trades_best_exit.csv` | trade-level ledger for the regime scorecard |
