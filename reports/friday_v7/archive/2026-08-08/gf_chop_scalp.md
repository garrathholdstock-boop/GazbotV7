# GREENFIELD — CHOP-DAY SCALP

**Question asked.** The desk's trend gates already carry the profit. Chop days are where it donates.
"Untradeable" is only a statement about the *current* gates — so invent a purpose-built chop scalper
(mean-reversion / range mechanism), spec it mechanically, backtest it regime-by-regime, and see whether
the donation can be turned into a collection.

**Answer up front: REFUTED, and not because of costs.** Fading a stretch on chop-classified MNQ tape is
a **47.2% proposition** (n=4,249 model-free first-touch races, z = −3.61). It is not a cost problem, it
is a **sign problem** — the tape *continues* more often than it reverts even inside blocks that every
chop metric calls chop. Across 540 costed parameter cells only 9 were positive; across 450
**frictionless** cells only 34 were positive at a median of **−$1.50/trade before a cent of fee**. The
single best cell is beaten by a random-coin-flip direction 77% of the time once the same grid search is
allowed to the placebo.

**The result the operator actually wants is the avoidance number.** Attributing every live trade to the
regime it opened in: chop blocks cost the desk **−$5,483 on 336 trades**; everything else made
**+$1,482**. The whole −$4,001 drawdown of the window, plus $1,482, is sitting inside blocks the desk
should not have been armed in. **A perfect chop filter is worth ~$5,500 over 17 trading days. A chop
scalper is worth nothing.** Do the first thing.

**One survivor, filed as SHADOW, not as a win:** dead-chop (ATR < 10) in the **20:00–21:00 UTC** hour
before the CME halt fades at **p(revert) = 0.610** (n=159 races, z = +2.78) and is positive in **all 20**
costed parameter cells and on **5 of 5** days it appears. It is **10 trades**. Thin n is a shadow, never
a kill — revival conditions at the end.

---

## 1. Method, data and the cost model — stated before any number

| Item | Value |
|---|---|
| Bars (5s, MNQ) | 2026-07-15 → 2026-08-07, **17 trading days**, folded to **23,625 1-min bars** |
| Ticks (MNQ trades) | 2026-07-24 → 2026-08-07, **11 trading days**, **16,728,571 ticks** |
| Sources | Parquet lake (`data/tape/`) + hot `capture.db` for 08-07, unioned and de-duplicated on `bar_ts` |
| Trade record | `gazbot7.db.trades`, `symbol='MNQ'`, **`data_quality IS NULL`** → 599 trades, 07-16 → 08-07 |
| Contract | MNQ, **$2.00 per point**, tick 0.25 pt |
| **Fee** | **$1.50 per ROUND TRIP** (venue truth; not $5, not $2, not per side) |
| Entry slip | market, filled at the next tick **+1 tick adverse** (cross the spread) = $0.50 |
| Stop slip | stop-market, filled **1 tick beyond the trigger** = $0.50 on the ~50% of trades that stop |
| Target fill | limit; requires a print **one tick THROUGH** the target before it is deemed filled |
| **Total friction** | **≈ $2.24 / round trip** at the observed stop rate |

Every exit is resolved by **first-touch on the forward tick path** — the stop and the target race each
other tick by tick. No MFE is reported anywhere in this section as if it were a win rate.

`(bar_ts/60)*60` is never used; minute folding is `bar_ts - bar_ts % 60`. Every bar and tick query
filters `symbol='MNQ'` explicitly. All queries aggregate in SQL; nothing multi-million-row is
materialised into pandas.

---

## 2. The regime taxonomy, built from the tape

Five regimes, keyed on **ATR level + efficiency + range-break**, computed on 30-minute blocks of 1-min
bars — never on the clock. 787 blocks over the 17-day bar window.

```
ATR20    mean 1-min true range over the trailing 20 minutes          (points)
ER30     |close[t] - close[t-30]| / Σ|Δclose| over the same 30 min   (0..1)
RT       Σ|Δclose| / (high - low) of the block   "roundtrip"         (path per unit of range)
BRK      block closes outside the prior 2h high/low                  (0/1)

CLEAN-TREND       ER >= 0.35 and |net| >= 25 pt
BUILDING          ER >= 0.22
VIOLENT-WHIPSAW   ER <  0.22 and ATR >= 20
DEAD-CHOP         ER <  0.22 and ATR <  10
NORMAL-CHOP       ER <  0.22 and 10 <= ATR < 20
```

| regime | blocks | med ATR | med ER | med range | med RT | % closing outside prior 2h |
|---|---:|---:|---:|---:|---:|---:|
| DEAD-CHOP | 93 | 8.5 | 0.095 | 38.8 | 2.85 | 10% |
| NORMAL-CHOP | 315 | 13.6 | 0.102 | 62.5 | 2.90 | 18% |
| VIOLENT-WHIPSAW | 94 | 25.8 | 0.116 | 125.6 | 2.85 | 26% |
| BUILDING | 181 | 13.5 | 0.270 | 83.3 | 2.30 | 42% |
| CLEAN-TREND | 104 | 13.8 | 0.426 | 113.5 | **1.78** | 64% |

The taxonomy separates cleanly and independently of ATR: trend blocks are not bigger-ATR blocks, they
are **lower-roundtrip** blocks (1.78 vs 2.85–2.90) that **close outside the prior range** 64% of the
time vs 10–26%. **502 of 787 blocks (64%) are chop.** That is the surface area at stake.

Distribution by time-of-day (blocks):

| | BUILDING | CLEAN-TREND | DEAD-CHOP | NORMAL-CHOP | VIOLENT-WHIPSAW |
|---|---:|---:|---:|---:|---:|
| ASIA 00-07 | 56 | 27 | 30 | 113 | 12 |
| LONDON 07-13 | 46 | 23 | 29 | 104 | 2 |
| US-OPEN 13-16 | 28 | 21 | 0 | 8 | **46** |
| US-PM 16-20 | 32 | 17 | 5 | 61 | 23 |
| CLOSE 20-21 | 19 | 16 | 29 | 29 | 11 |

The US open is where whipsaw lives (46 of 94 whipsaw blocks, and **zero** dead-chop blocks); dead chop
lives overnight, in London and in the closing hour.

---

## 3. The premise, tested: where the desk's money actually goes

Every live trade (`data_quality IS NULL`) attributed to the 30-min block it **opened in**. This is a
descriptive attribution using the block's completed statistics — it is *hindsight labelling*, correct
for "where did the money go", and it is **not** used anywhere as a trading rule.

| regime at entry | n | net | $/trade | win |
|---|---:|---:|---:|---:|
| **CLEAN-TREND** | 120 | **+$1,373** | **+$11.44** | 45% |
| BUILDING | 143 | +$109 | +$0.76 | 42% |
| DEAD-CHOP | 11 | −$125 | −$11.36 | 36% |
| **NORMAL-CHOP** | 159 | **−$3,413** | **−$21.47** | 31% |
| **VIOLENT-WHIPSAW** | 166 | **−$1,944** | **−$11.71** | 39% |
| | | | | |
| **CHOP (3 rows)** | **336** | **−$5,483** | **−$16.32** | |
| **NON-CHOP** | 263 | **+$1,482** | +$5.64 | |
| ALL | 599 | −$4,001 | −$6.68 | |

By time-of-day: ASIA −$1,043 · LONDON +$172 · US-OPEN −$1,489 · US-PM −$1,624 · CLOSE −$17.

**The premise is confirmed, hard.** The desk is profitable in trend and building blocks and gives all of
it back plus $4,001 in chop. This is the target. The rest of the section asks whether a purpose-built
mechanism can *collect* in those blocks, or whether the only move is to *not be there*.

---

## 4. CHOP-FADE — the exact mechanical spec

Two mechanisms were built. Both are evaluated on the 11-day tick tape with the cost model of §1.

### 4.1 CHOP-FADE (band fade) — the primary candidate

```
CLOCK      evaluated at every 1-minute close. One position at a time.

REGIME GATE (trailing only, no look-ahead; all inputs end at the bar just closed)
    ATR20   in [atr_lo, atr_hi]                 default 6 .. 20 pt
    ER30    <  er_max                           default 0.22        (chop)
    RT30    >= rt_min                           default 2.2         (back-and-forth)
    hour    not in skip_hours                   default 00-07 UTC excluded (ASIA is config-benched)
    minute  before 20:40 UTC                    (never hold into the 21:00 CME halt)

ANCHOR     MID    = mean(close, trailing `anchor` minutes)      default 20
           STRETCH = (close - MID) / ATR20

TRIGGER    mode = 'touch'   : STRETCH >= +k  -> SHORT ;  <= -k  -> LONG
           mode = 'revert'  : STRETCH[t-1] >= +k AND STRETCH[t] < STRETCH[t-1] -> SHORT
                              STRETCH[t-1] <= -k AND STRETCH[t] > STRETCH[t-1] -> LONG
                              ("the stretch has begun to contract" — the anti-grind confirmation)
           default k = 1.0 ATR

ENTRY      market on the first tick after the minute close, filled 1 tick adverse.

STOP       s_atr * ATR20 against, stop-market, filled 1 tick beyond.      default 1.0
TARGET     t_r * (stop distance), limit, requires a print 1 tick through. default 1.0 R
TIME EXIT  maxhold minutes -> market.                                     default 30
HARD FLAT  20:45 UTC.

COOLDOWN   `cooldown` minutes after any exit.                             default 5
MAX TRADES `maxtr` per session.                                           default uncapped in tests
```

### 4.2 CHOP-EDGE (range-edge failure fade) — the structural alternative

Same gate, entry, stop, exit and cooldown machinery. Different trigger:

```
TRIGGER    PH = highest high of the prior 120 minutes (excl. current bar); PL = lowest low
           bar HIGH > PH + pen*ATR  AND  bar CLOSE < PH  -> SHORT   (failed break up)
           bar LOW  < PL - pen*ATR  AND  bar CLOSE > PL  -> LONG    (failed break down)
```

This is the canonical range-trade — fade the failed poke through the range boundary — and it is
mechanically distinct from a mean-band fade, so its absence would have left the class untested.

---

## 5. Per-session backtest — the 11 tick-tape days

CHOP-FADE at its **best swept cell** (`revert`, k=1.25, s_atr=1.5, t_r=1.0R, maxhold=30, cooldown=5),
against what the desk actually did. Regime composition is from §2.

| session | 30m blocks | chop blocks | med ATR | med ER | med RT | desk n | desk net | desk **chop** n | desk **chop** net | CHOP-FADE n | CHOP-FADE net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-24 Fri | 42 | 28 (67%) | 13.5 | 0.170 | 2.71 | 47 | −$578.5 | 39 | −$455.5 | 23 | −$86.1 |
| 2026-07-27 Mon | 46 | 30 (65%) | 11.4 | 0.192 | 2.84 | 37 | −$155.0 | 11 | −$23.0 | 25 | +$96.9 |
| 2026-07-28 Tue | 46 | 27 (59%) | 16.5 | 0.172 | 2.63 | 25 | −$22.0 | 10 | −$255.5 | 36 | +$172.5 |
| 2026-07-29 Wed | 46 | 28 (61%) | 19.2 | 0.188 | 2.48 | 35 | +$1,203.0 | 13 | −$123.0 | 20 | −$122.4 |
| 2026-07-30 Thu | 46 | 32 (70%) | 17.1 | 0.146 | 2.50 | 79 | +$239.5 | 44 | −$604.5 | 21 | −$287.4 |
| 2026-07-31 Fri | 42 | 24 (57%) | 14.0 | 0.163 | 2.49 | 27 | −$569.0 | 9 | −$383.5 | 29 | +$129.9 |
| **2026-08-03 Mon** | 46 | 26 (57%) | 11.8 | 0.194 | 2.55 | 30 | −$280.0 | 10 | +$106.0 | 28 | +$205.0 |
| **2026-08-04 Tue** | 46 | 29 (63%) | 11.8 | 0.154 | 2.46 | 16 | +$330.5 | 4 | −$125.5 | 28 | +$44.6 |
| **2026-08-05 Wed** | 46 | 30 (65%) | 11.9 | 0.152 | 2.59 | 29 | −$817.0 | 27 | −$786.5 | 25 | +$2.3 |
| **2026-08-06 Thu** | 46 | 34 (**74%**) | 12.7 | 0.137 | 2.60 | 14 | −$305.0 | 4 | −$39.5 | 26 | **+$428.4** |
| **2026-08-07 Fri** | 42 | 24 (57%) | 11.1 | 0.196 | 2.68 | 21 | +$299.0 | 5 | −$56.5 | 25 | −$152.9 |
| **TOTAL** | | | | | | 360 | −$654.5 | 176 | **−$2,747.0** | 286 | **+$430.8** |

The completed week's genuine chop sessions, identified from the tape and not by reputation, are
**08-05 (65% chop, ER 0.152)** and above all **08-06 (74% chop blocks, median ER 0.137 — the choppiest
session in the whole 17-day window)**. 08-03 and 08-07 are the least choppy of the five.

Read naively that final row says the scalper made $431 while the desk lost $2,747 in the same blocks.
**It does not survive contact with §6.**

---

## 6. Robustness — the four tests the candidate has to pass, and does not

### 6.1 The grid is barren, not a plateau

540 costed cells (2 modes × 6 k × 3 stops × 5 targets × 3 max-holds, all with n ≥ 100):

| | cells | positive | median $/trade |
|---|---:|---:|---:|
| Costed ($1.50 RT + slip) | 540 | **9 (1.7%)** | **−$3.42** |
| **Frictionless** (fee 0, slip 0) | 450 | **34 (7.6%)** | **−$1.50** |

**The mechanism loses money with the costs switched off.** That single line reframes everything below:
this is not a thin edge eaten by fees, it is a negative-expectancy direction.

### 6.2 Parameter plateau — the "best" cell is a one-cell-wide ridge

Net $ / n / $-per-trade, `revert` mode, t_r = 1.0R, maxhold 30, cooldown 5:

| s_atr \ k | 0.75 | 1.00 | 1.25 | 1.50 | 1.75 |
|---|---:|---:|---:|---:|---:|
| 1.00 | −1762 / 435 / −4.05 | −1323 / 389 / −3.40 | −1261 / 330 / −3.82 | −1061 / 265 / −4.00 | −751 / 205 / −3.67 |
| 1.25 | −874 / 398 / −2.20 | −423 / 362 / −1.17 | −827 / 307 / −2.69 | −935 / 253 / −3.70 | −415 / 201 / −2.06 |
| **1.50** | −471 / 349 / −1.35 | −222 / 325 / −0.68 | **+431 / 286 / +1.51** | **+336 / 232 / +1.45** | **+432 / 189 / +2.29** |
| 1.75 | −1106 / 320 / −3.46 | −1054 / 300 / −3.51 | −807 / 261 / −3.09 | −633 / 217 / −2.92 | −399 / 178 / −2.24 |
| 2.00 | −994 / 290 / −3.43 | −403 / 271 / −1.49 | −572 / 241 / −2.37 | −278 / 204 / −1.36 | −14 / 170 / −0.08 |

Every positive number in the table sits on the **s_atr = 1.5 row**, sandwiched between −$2.69 above it
and −$3.09 below it at the same k. A plateau is a region; this is a ridge one cell wide, and moving the
stop by 0.25 ATR in either direction costs $4/trade. Same story in the target axis:

| t_r | 0.5 | 0.75 | 0.9 | **1.0** | 1.1 | 1.25 | 1.5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| net | −249 | −573 | +229 | **+431** | +152 | −624 | −1141 |

Non-monotone with two sign flips inside 0.5 R.

### 6.3 The chop gate is not what makes it work — and more chop makes it worse

If this were a *chop* edge, tightening the chop definition should improve it. It does not:

| ER ceiling (lower = purer chop) | 0.08 | 0.10 | 0.12 | 0.16 | **0.22** | 0.30 | **1.00 (no gate)** |
|---|---:|---:|---:|---:|---:|---:|---:|
| $/trade | −0.48 | +1.39 | −0.63 | −0.21 | **+1.51** | +1.34 | **+1.47** |

| roundtrip floor (higher = purer chop) | 0.0 | 1.8 | **2.2** | 2.6 | 3.0 | 3.4 |
|---|---:|---:|---:|---:|---:|---:|
| $/trade | +0.43 | +0.43 | **+1.51** | −2.74 | −0.06 | +6.92 |

Sign flips at every step, and **removing the efficiency filter entirely (er_max = 1.0) performs as well
as the tuned value**. The variable that *defines* chop contributes nothing. The candidate is not a chop
mechanism; it is a stop/target geometry that happened to fit this tape.

### 6.4 Strip-best, leave-one-day-out, out-of-sample, placebo

| | CF-A `revert k1.25 s1.5 1.0R` | CF-B `revert k1.5 s1.5 1.0R` | CF-C `touch k0.8 s1.5 1.0R` | CF-E `edge s1.5 1.0R` |
|---|---:|---:|---:|---:|
| n / net / $per / win | 286 / **+$431** / +1.51 / 53.5% | 232 / +$336 / +1.45 / 53.0% | 358 / +$187 / +0.52 / 51.4% | 139 / +$101 / +0.73 / 53.2% |
| t-stat on $/trade | **0.62** | 0.54 | 0.24 | 0.16 |
| strip best 1 | +$372 | +$278 | +$128 | **−$42** |
| strip best 3 | +$256 | +$162 | +$12 | −$264 |
| strip best 5 | +$141 | +$48 | −$105 | −$456 |
| strip best 10 | **−$141** | **−$232** | **−$393** | −$810 |
| days green | 7 / 11 | 5 / 11 | 4 / 11 | 5 / 11 |
| **LOO worst** (drop 1 day) | **+$2.4** (drop 08-06) | +$77 (drop 08-06) | **−$551** (drop 07-28) | **−$377** (drop 07-28) |
| IN 07-24…07-31 | −$97 (−$0.63/tr) | +$34 (+$0.28/tr) | +$393 (**+$2.13**/tr) | +$254 (**+$2.95**/tr) |
| OUT 08-03…08-07 | +$527 (+$4.00/tr) | +$302 (+$2.82/tr) | −$206 (**−$1.18**/tr) | −$152 (**−$2.87**/tr) |

* **CF-A's entire net is one day.** Removing 2026-08-06 leaves **+$2.40** on 260 trades. 99.4% of the
  edge is a single session — the choppiest session of the window, which is at least the right session,
  but one day is one day.
* **CF-C and CF-E flip sign out of sample** (+$2.13 → −$1.18 and +$2.95 → −$2.87). CF-A/CF-B flip the
  other way, which is the same disease pointing the opposite direction.
* No candidate reaches t = 1.0 on per-trade P&L.

**Placebo, single cell.** Keep CF-A's exact trigger minutes and stop/target geometry, randomise the
**side** of every trade, 400 repetitions. Placebo mean net **−$830** (sd $672) — i.e. the placebo is
centred almost exactly on the friction bill, as it must be. CF-A's +$431 sits at the **97.2nd
percentile**; taken alone, p ≈ 0.028.

**Placebo, corrected for the search.** That p is the p-value of the *winner of a 540-cell grid*, so the
honest test applies the same grid to the placebo. Over a 75-cell sub-grid (k × s_atr × t_r), the real
best-of-grid is **$902**; the random-side best-of-grid has mean **$1,166** (sd $336, median $1,157) and

> **77.0% of random-direction placebos beat the real best-of-grid.  p = 0.770.**

The best configuration this hunt could find is *worse than a coin flip* once the coin flip is given the
same number of tries. That is the end of CF-A.

---

## 7. Home-segment scoring — no segment survives either

The instruction is to score each config only on its home segments, never blanket. So: 216 costed
configurations were run with the ATR band and hour filters **open**, every trade tagged with its
**trailing** ATR bucket and time-of-day, and each (segment × config) cell with n ≥ 25 scored. The
statistic that matters is *what fraction of configurations are positive in that segment* — one positive
config in a segment is noise, most of them being positive is structure.

**Costed** (216 configs):

| segment | configs | median n | median $/trade | **fraction of configs net-positive** |
|---|---:|---:|---:|---:|
| DEAD-CHOP ATR<10 | 216 | 124 | −$3.56 | **0.037** |
| NORMAL-CHOP ATR 10-20 | 216 | 437 | −$2.93 | **0.102** |
| VIOLENT-WHIPSAW ATR≥20 | 216 | 127 | −$7.74 | **0.000** |
| ASIA 00-07 | 216 | 247 | −$2.82 | 0.199 |
| LONDON 07-13 | 216 | 213 | −$5.03 | **0.000** |
| US-OPEN 13-16 | 216 | 83 | −$4.47 | 0.074 |
| US-PM 16-20 | 216 | 125 | −$4.10 | 0.134 |
| CLOSE 20-21 | 52 | 28 | −$0.82 | 0.442 |
| ER trailing ≤0.05 / ≤0.10 / ≤0.15 / ≤0.22 | 216 ea | 138–257 | −$3.37 / −$6.07 / −$3.00 / −$3.53 | 0.042 / 0.028 / 0.199 / 0.065 |
| RT 2.0-2.5 / 2.5-3.0 / 3.0-3.5 / >3.5 | 216 ea | 119–233 | −$4.16 / −$2.92 / −$6.61 / −$2.41 | 0.139 / 0.120 / 0.000 / 0.199 |

**Every single segment has a negative median across the configuration space.** The best is the closing
hour at −$0.82 with 44% of configs positive on a median of 28 trades.

**Frictionless** (450 configs) — the only fair way to ask "is there gross edge here anywhere":

| segment | configs | median n | median $/trade **gross** | fraction positive |
|---|---:|---:|---:|---:|
| DEAD-CHOP × LONDON | 368 | 49 | **+$0.76** | 0.633 |
| NORMAL-CHOP × US-PM | 450 | 78 | +$0.21 | 0.538 |
| NORMAL-CHOP × US-OPEN | 52 | 26 | +$1.32 | 0.519 |
| NORMAL-CHOP × ASIA | 450 | 148 | −$0.03 | 0.482 |
| CLOSE 20-21 (all ATR) | 92 | 28 | **+$1.77** | 0.685 |
| NORMAL-CHOP × LONDON | 450 | 138 | −$2.63 | 0.047 |
| WHIPSAW × US-PM | 321 | 35 | −$9.66 | 0.069 |
| WHIPSAW × US-OPEN | 360 | 61 | −$2.97 | 0.267 |

Four segments are gross-positive. **The best of them makes $1.77 a trade before costs against a $2.24
friction floor.** Even where the fade is directionally right, it is not right by enough to pay the
round trip. That is the whole story in one line.

---

## 8. Why it fails — the model-free race

Everything above is config-dependent. This is not. At **every** minute whose trailing tape passes the
chop gate and whose stretch is ≥ 1 ATR from the 20-min mean, race **+X·ATR against −X·ATR** on the
forward tick path over 30 minutes. No stop, no target, no fee, no parameters beyond X. Ties and
unresolved races discarded. **P(revert first) > 0.5 is the fade's entire premise.**

| X (ATR) | n | **P(revert first)** | after an UP stretch, P(down first) | after a DOWN stretch, P(up first) |
|---:|---:|---:|---:|---:|
| 0.50 | 4,254 | **0.4770** | 0.482 | 0.472 |
| 0.75 | 4,254 | **0.4673** | 0.472 | 0.462 |
| 1.00 | 4,249 | **0.4723** | 0.476 | 0.469 |
| 1.25 | 4,229 | **0.4883** | — | — |
| 1.50 | 4,191 | 0.5006 | 0.500 | 0.501 |
| 2.00 | 3,961 | 0.5032 | — | — |
| 2.50 | 3,549 | 0.4970 | — | — |

At X = 1.0: **P = 0.4723, n = 4,249, 95% CI [0.4573, 0.4874], z = −3.61.** Both sides agree (0.476 up,
0.469 down — not a one-sided artifact). By day: **all 11 sessions ≤ 0.506**, range 0.406–0.506. By
segment: NORMAL-CHOP 0.467 (z −3.39), WHIPSAW 0.451 (z −2.69), LONDON 0.448 (z −3.68), US-OPEN 0.444.

**Chop-classified MNQ tape is mildly trending, not mean-reverting, at the 1-ATR / 30-minute scale.**
This is the same thing the desk's own reversion book has been saying by bleeding into grinds — the
greenfield hunt reproduces it from the raw tape with no gate in the loop.

### The friction hurdle, both directions

Take the best-signed version of the trade at each distance — fade where P(revert) > 0.5, continuation
where it is < 0.5 — and put the gross expectancy next to the cost:

| X·ATR | n | P(revert) | med ATR | distance $ | EV **fade** | EV **continuation** | friction | net fade | net cont |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 | 4,254 | 0.4770 | 13.5 | $13.48 | −$0.62 | +$0.62 | $2.24 | −$2.86 | −$1.62 |
| 0.75 | 4,254 | 0.4673 | 13.5 | $20.22 | −$1.32 | +$1.32 | $2.23 | −$3.56 | −$0.91 |
| **1.00** | 4,249 | 0.4723 | 13.5 | $26.98 | −$1.49 | **+$1.49** | $2.24 | −$3.73 | **−$0.74** |
| 1.25 | 4,229 | 0.4883 | 13.5 | $33.72 | −$0.79 | +$0.79 | $2.24 | −$3.03 | −$1.45 |
| 1.50 | 4,191 | 0.5006 | 13.5 | $40.42 | +$0.05 | −$0.05 | $2.25 | −$2.20 | −$2.30 |
| 2.00 | 3,961 | 0.5032 | 13.4 | $53.50 | +$0.34 | −$0.34 | $2.25 | −$1.91 | −$2.59 |
| 2.50 | 3,549 | 0.4970 | 13.3 | $66.69 | −$0.39 | +$0.39 | $2.25 | −$2.64 | −$1.85 |

**At no distance, in either direction, does a symmetric scalp out of a chop-gated stretch clear its own
friction.** The largest gross edge anywhere in the table is $1.49 against a $2.24 bill. The obvious
escape — widen the distance so the fixed $1.50 fee amortises — fails because the directional bias
**decays to zero by X = 1.5** (P → 0.5006). The bias is real but small and short-ranged; the fee is
fixed. There is no window where they cross.

Per home segment at X = 1.0, best-signed:

| segment | n | P(revert) | z | med ATR | best side | gross EV | friction | **net** |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| DEAD-CHOP ATR<10 | 859 | 0.5076 | +0.44 | 8.2 | fade | $0.25 | $2.25 | −$2.00 |
| NORMAL-CHOP 10-20 | 2,634 | 0.4670 | −3.39 | 13.7 | cont | $1.81 | $2.23 | −$0.42 |
| WHIPSAW ≥20 | 756 | 0.4511 | −2.69 | 25.9 | **cont** | $5.08 | $2.23 | **+$2.85** |
| ASIA 00-07 | 1,405 | 0.4762 | −1.79 | 12.6 | cont | $1.20 | $2.24 | −$1.04 |
| LONDON 07-13 | 1,231 | 0.4476 | −3.68 | 12.1 | **cont** | $2.54 | $2.22 | **+$0.31** |
| US-OPEN 13-16 | 453 | 0.4437 | −2.40 | 30.1 | **cont** | $6.79 | $2.22 | **+$4.56** |
| US-PM 16-20 | 710 | 0.4915 | −0.45 | 17.0 | cont | $0.58 | $2.25 | −$1.67 |
| CLOSE 20-21 | 450 | 0.5267 | +1.13 | 11.4 | fade | $1.21 | $2.24 | −$1.02 |
| **DEAD-CHOP × CLOSE 20-21** | **159** | **0.6101** | **+2.78** | 7.9 | **fade** | **$3.47** | $2.19 | **+$1.28** |

Three segments clear the hurdle and **all three are continuation, not fade** — chop-gated whipsaw at the
US open is a $4.56/trade *momentum* proposition, which is a finding for the trend book and not for this
one (and it is exactly the block the desk currently loses −$1,944 in, by being armed with churners
rather than with continuation). Exactly one **fade** cell clears: dead chop in the closing hour.

---

## 9. The second mechanism — range-edge failure fade

CHOP-EDGE, all 15 stop × target cells, 11 days, ATR and hours open:

| s_atr \ t_r | 0.5 | 0.75 | 1.0 | 1.5 | 2.0 |
|---|---:|---:|---:|---:|---:|
| 0.6 | −$487 | −$530 | −$792 | −$1,036 | −$891 |
| 1.0 | −$470 | −$876 | −$1,044 | −$912 | −$1,004 |
| 1.5 | −$372 | −$147 | **+$101** | −$700 | −$366 |

One positive cell out of 15, +$101 on n=139, immediate neighbours at −$147 and −$700, **strip-best-1
already negative (−$42)**, LOO worst −$377, and OOS sign flip +$2.95 → −$2.87. Frictionless the grid is
still 3 of 15 positive. The structural alternative dies the same death as the band fade, which is the
point: the failure is in the *premise*, not in either implementation.

---

## 10. The one thing worth keeping — SHADOW

**DEAD-CHOP × CLOSE 20-21 UTC, fade.** ATR20 < 10, ER30 < 0.22, hour 20 UTC only (the final hour before
the 21:00 CME halt), flat by 20:55.

* Model-free race: **n = 159, P(revert first) = 0.6101, z = +2.78**, gross EV $3.47 vs $2.19 friction.
* Costed backtest, **all 20 parameter cells positive** — s_atr {1.0, 1.5} × t_r {0.5, 0.75, 1.0, 1.5} ×
  cooldown {2, 5} × mode {revert, touch}: net +$26 to +$180, $/trade +$1.28 to +$22.49, win 67–91%.
  This is the one genuine **plateau** produced anywhere in this hunt.
* Reference cell (`revert`, k=1.0, s_atr=1.0, t_r=1.0R, cooldown=5): **n = 10, +$117, +$11.69/trade,
  9 of 10 won, 5 of 5 days green, strip-best-1 +$99, strip-best-2 +$81.**
* Widening the ATR ceiling keeps it alive (<8: n=7 +$30 · <10: n=10 +$117 · <12: n=18 +$238 · <14: n=20
  +$176) and **removing it kills it** (all ATR, hour 20: n=36, −$0.65/trade) — so the ATR<10 condition
  is load-bearing, which is the right shape for a real effect.

**It is ten trades.** No verdict beyond SHADOW is defensible, and the mechanism is at least plausible —
the last hour before the halt is when positioning unwinds into a thinning book and pokes have nothing
behind them. The plateau and the 5/5 day split are what stop this being filed as noise.

**Revival conditions (all three):**
1. **n ≥ 60 costed trades** accumulated in shadow, i.e. roughly 6–8 more weeks of tape at ~1 trade/day.
2. Race P(revert first) stays **≥ 0.57 with z ≥ 2** on the *forward* sample only.
3. The 20-cell parameter plateau still has **≥ 80% of cells positive** on the combined sample, and the
   ATR<10 gate still separates from ATR-open.

If it clears all three it earns a 1-lot promotion inside the 20:00–21:00 window only. It should never be
promoted on this sample.

---

## 11. Verdicts

| Lead | Status | Basis |
|---|---|---|
| **CHOP-FADE** — band fade of a ≥k·ATR stretch on chop-gated tape | **REFUTED** | Model-free first-touch race P(revert) = 0.4723 (n=4,249, z=−3.61) — negative gross expectancy before any cost. 540 costed cells: 9 positive. 450 **frictionless** cells: 34 positive, median −$1.50/trade. Best cell's edge is 99.4% one session; **77% of random-direction placebos beat the best-of-grid (p=0.770)**. The ER gate — the variable that defines chop — contributes nothing (er_max 1.0 ≈ er_max 0.22). |
| **CHOP-EDGE** — failed-break fade of the prior 2h range | **REFUTED** | 1 of 15 costed cells positive; strip-best-1 turns it negative; LOO worst −$377; OOS sign flip +$2.95 → −$2.87/trade. |
| **Any symmetric chop scalp at any distance** | **REFUTED** | §8 hurdle table: max gross EV in either direction is $1.49/trade at X=1.0 vs a $2.24 friction floor, and the directional bias decays to 0.5006 by X=1.5 — widening to amortise the fixed fee destroys the edge it was meant to pay for. |
| **"Sit out the chop blocks"** | **LIVE — this is the finding** | Live trades attributed to entry regime: chop = 336 trades, **−$5,483**; non-chop = 263 trades, **+$1,482**. Perfect avoidance turns −$4,001 into +$1,482 over 17 trading days. No new mechanism required; this is a **router** job. |
| **DEAD-CHOP × 20:00–21:00 UTC fade** | **SHADOW** | Race n=159, P=0.610, z=+2.78; all 20 costed cells positive; n=10 trades. Revival conditions in §10. |
| **Chop-gated WHIPSAW at the US open is a CONTINUATION trade** | **PARKED** | P(revert)=0.444 (n=453, z=−2.40), best-signed gross EV **$6.79** vs $2.22 friction = **+$4.56/trade** — but it is *momentum*, out of scope for a chop scalper, and the desk currently loses −$1,944 in whipsaw blocks by being armed with churners there. Revival: hand to the trend book as an entry-selection study with its own stop/target sweep and a forward leg — do **not** promote off this section's numbers. |

### What to do instead

1. **The money is in avoidance, and the router already owns the lever.** −$5,483 in chop blocks over 17
   days is ~$320/day of pure not-being-there. Nothing in this greenfield hunt came within an order of
   magnitude of that.
2. **The chop taxonomy of §2 is reusable and cheap.** ER30 < 0.22 with RT > 2.5 and no 2h range break
   is computable from trailing 1-min bars in milliseconds, separates the desk's +$11.44/trade blocks
   from its −$16.32/trade blocks, and is the same family of measurement `runstate.py` already runs.
   Note it disagrees with a run-state read by construction — it is a *block* statistic, and the standing
   rule that RUN STATE wins on disagreement still applies.
3. **Do not re-derive the chop fade.** The race in §8 is model-free, 4,249 samples, and points the wrong
   way at every distance and in every segment. Any future "chop scalper" proposal must first show
   P(revert first) > 0.5 on fresh tape, or it is this study again with different parameters.

### Limitations, stated

* **11 tick days, 17 bar days.** The regime census is 787 blocks; the race is 4,249 events; the per-config
  backtests are 130–390 trades. That is enough to *refute* comfortably (a negative result needs the null
  to be inside the confidence interval, and −3.61 sigma is not) and nowhere near enough to *confirm*
  anything, which is why the one survivor is a shadow.
* **Single instrument, single contract month.** MNQ Sep'26 only.
* **The regime attribution in §3 is hindsight labelling.** It answers "where did the money go", not
  "what should have been armed at 09:14". The §4 gate, by contrast, is strictly trailing.
* **Slippage is modelled, not measured.** 1 tick on entry and 1 tick beyond the stop. The desk's own
  cost autopsy puts real stop slippage near that figure, and every conclusion here is a refutation, so
  a *more* pessimistic model only strengthens it.
* Shadow-simulated losses have historically run 1.1–3.1× modelled. Every negative number in this
  section is therefore a **floor**, and the one positive one (§10) is a **ceiling**.
