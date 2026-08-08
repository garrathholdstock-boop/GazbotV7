# GREENFIELD HUNT — census "full" · cluster **OPEN/NEWS**

**Question asked:** forget every gate the desk owns. Invent a brand-new entry signal, from scratch,
that shows up for the runs the census filed under **OPEN/NEWS**. Spec it mechanically, backtest it
tick-honest on `capture.db` net of ~$5 a round trip, and then try as hard as possible to kill it.

**Answer up front — this one has a survivor, and it is not the clever one.** Two of the three
inventions died, and the third only lived once I stripped every filter off it. What is left is
embarrassingly simple: **during 13:00–15:00 UTC, every five minutes, be positioned in the direction
of the last fifteen minutes, with a stop two ATRs wide and a 2R target.** No thresholds, no
efficiency-ratio dial, no book reading. Over **17 trading days** that is **129 trades, +$4,169,
48.1% winners, +$32.32 a trade, +0.272R a trade**, it survives strip-the-3-best (+$2,931), it is
positive on **leave-one-day-out for all 17 days**, and it shows up for **11 of the 14 sat-out
OPEN/NEWS runs** — and for **15 of the 15 biggest** runs on the wider tape.

It also carries one honest wound that I have not been able to dress: **when the day's own drift is
taken out, its timing skill is negative.** It makes its money by being on the right side of a
directional two-hour window, not by picking moments inside it. That is stated plainly in §7 and it
is why the verdict is **SHADOW, not LIVE**.

---

## 1. What OPEN/NEWS actually is — read this before believing any number below

The census does **not** detect OPEN/NEWS from the tape. It is a **clock label**: `cluster()` in
`scripts/run_census.py` returns `OPEN/NEWS` for any big run whose 15-minute window *starts* between
**13:00 and 15:00 UTC**, before it ever looks at flow, amplitude or book. That is the US cash open
(13:30 UTC = 09:30 ET) plus the half hour in front of it and the 14:00 UTC (10:00 ET) data drop.

Two consequences, and they shape everything:

**(a) There is nothing rare about an OPEN/NEWS run.** Cutting the tape into non-overlapping
15-minute slots:

| Slot location | slots | of which "census big run" (≥65 pt) | rate |
|---|---|---|---|
| **13:00–15:00 UTC** | 134 | 52 | **39%** |
| everywhere else | 1,387 | 100 | 7% |

Four out of every ten quarter-hours in that window is a "big run". The label is not telling you an
event happened; it is telling you the clock. In-window the median |15-min move| is **50 pt**, the
75th percentile **87 pt** and the 95th **180 pt**. So "catch the OPEN/NEWS runs" reduces, honestly,
to **"trade 13:00–15:00 UTC directionally on a quarter-hour horizon"** — which is a much better
brief than it sounds, because it means the base rate is high and the sample is not starved.

**(b) Because the label is clock-only, the WHOLE bar tape is usable.** This is the single biggest
difference from the VACUUM hunt, which was welded to the 5 days of aggressor-tagged ticks and could
never have an out-of-sample leg. OPEN/NEWS needs no tick data to *define* it, so:

| Table | Coverage | Usable for this study |
|---|---|---|
| `bars` 5s MNQ | 2026-07-15 → 08-07 | **17 trading days with full 13:00–15:00 coverage** |
| `ticks` (aggressor) | 08-03 → 08-07 | 5 days — used for the tick-honest re-price only |
| `quotes` (L1 bid/ask) | 08-03 → 08-08 | 5 days — used for real entry prices |

**Every signal below is built from 5s bars only, so it runs on all 17 days.** That bought a real
walk-forward: **DEV = 07-16 … 07-31 (12 days)**, **HOLDOUT = 08-03 … 08-07 (5 days, the census
week)**. The holdout is the week the target runs live in, which is the right way round — the signal
never saw them while it was being designed.

**And the drift check that killed half of the VACUUM study passes here.** Over the 17 days the
13:00–15:00 window's unconditional 15-minute forward return is **−4.58 pt with P(up) = 47.8%** —
essentially balanced, no melt-up to flatter a long-biased signal. (The census week on its own *was*
up-biased; the 12 DEV days were down-biased. They cancel, which is exactly why using both matters.)

## 2. The target — the 14 sat-out OPEN/NEWS runs

The census (7 days, 67 runs) filed **24 runs** as OPEN/NEWS. Ten were caught by a live gate, three
were fought, and **14 were sat out**. Those 14 are the scoreboard:

| # | Start (UTC) | Dir | Move | $ 1-lot ceiling |
|---|---|---|---|---|
| 1 | 08-07 14:12 | UP | +183 | 366 |
| 2 | 08-07 13:50 | DN | −143 | 286 |
| 3 | 08-03 13:18 | DN | −141 | 282 |
| 4 | 08-05 14:16 | DN | −129 | 258 |
| 5 | 08-06 14:03 | UP | +152 | 304 |
| 6 | 08-06 14:46 | UP | +120 | 240 |
| 7 | 08-07 13:00 | DN | −105 | 210 |
| 8 | 08-04 13:56 | UP | +100 | 200 |
| 9 | 08-05 13:25 | UP | +96 | 193 |
| 10 | 08-07 14:29 | DN | −88 | 176 |
| 11 | 08-06 13:17 | DN | −82 | 165 |
| 12 | 08-06 14:24 | DN | −79 | 158 |
| 13 | 08-05 14:39 | DN | −78 | 156 |
| 14 | 08-05 14:54 | UP | +73 | 146 |

**Total hindsight ceiling: 1,569 points = $3,138 on one lot.** Six up, eight down — nearly balanced,
which is why the long/short symmetry test below is meaningful rather than decorative.

Widening to the full 17-day tape with the same 65-pt threshold gives **78 OPEN/NEWS-window runs**,
4–5 a day, every single day, 39 up and 39 down. That is the larger scoreboard used in §8.

## 3. The three inventions, fully specified

All three run inside 13:00–15:00 UTC. Common definitions: `mom15` = close(t) − close(t−15 min);
`ATR1m` = the mean 1-minute high−low over the trailing 15 minutes (during this window it runs
**18–34 pt** — the open is fast); `ER30` = |net move| ÷ |path| over the trailing 30 minutes on
1-minute closes. Costs everywhere: **MNQ 1 lot, $2/point, $5 per round trip**, entries at a 5s bar
close (already past the level, no limit-fill optimism), and **the stop wins ties** when a 5s bar
spans both stop and target.

### Invention A — COIL-CRACK (CC)
> *"The last half hour went nowhere, and then it snapped. That snap is an ignition out of balance —
> ride it."*
- **Arm** when `|mom15| ≥ 30 pt` **and** `ER30 < 0.20` (the previous half hour was chop, so this
  move is new information, not the continuation of something already spent).
- **Confirm** the bar closes in the top 30% (long) / bottom 30% (short) of its 15-minute range.
- **Direction** = sign(mom15). **Entry** market at that bar's close. **Stop** k × ATR1m.
  **Target** RR × stop. **Time cap** 45 min. **Cooldown** 15 min after an exit.

### Invention B — OPEN EXHAUSTION FADE (OXF)
> *"A near-straight line for thirty minutes into the open is not a trend, it is a finished move.
> Take the other side."*
- **Arm** when `ER30 ≥ 0.45` (the last half hour was almost pure directional travel).
- **Direction** = *against* mom15. Same entry/stop/target/cap machinery.
- A second, kinder version was also built: **wait for confirmation** — arm on ER30, then enter only
  when price breaks the low (high) of the last 3/5/10 minutes against the run, so you are not
  catching the knife.

### Invention C — THE OPEN RIDER (ODR) ← *the survivor*
> *"Stop trying to be clever about which fifteen minutes matters. During the open, just be
> positioned with the last fifteen minutes, and give it room."*
- **Every 5 minutes**, if flat, take a trade. **No arming threshold at all.**
- **Direction** = sign(mom15).
- **Entry** market at that 5s bar's close.
- **Stop** = **2.0 × ATR1m** (floor 4 pt). **Target** = **2R**. **Time cap 45 min.**
- No re-entry until the previous trade is out.

A/B are the "clever" ones. C is the control that was supposed to lose. It didn't.

## 4. Invention A — COIL-CRACK: the filter does nothing. **REFUTED as a filter.**

The cost-free forward-return scan looked terrific. Sampling every minute of the window across all
17 days (n = 1,769 observations), the raw 15-minute forward return of a momentum entry sorted
beautifully by ER30:

| ER30 bucket at entry | n | fwd-15 (raw) | win% |
|---|---|---|---|
| < 0.15 (coil) | 355 | **+22.5 pt** | 60.3% |
| 0.15–0.25 | 259 | +14.0 pt | 55.2% |
| 0.25–0.35 | 236 | +6.2 pt | 51.3% |
| 0.35–0.50 | 261 | +4.9 pt | 51.8% |
| ≥ 0.50 (extended) | 58 | **−58.2 pt** | 35.5% |

That is a clean monotone dial, and it is the same shape as the desk's own abs_veto post-mortem
("it chased an already-exhausted move"). So I built it, traded it, and then **ablated it** — the
only test that matters for a filter. Same exits, same window, same everything, with and without the
ER gate:

| Version | period | n | net | strip-3 | $/trade |
|---|---|---|---|---|---|
| RIDE with `ER30 < 0.20` | ALL 17d | 51 | +$2,049 | +$724 | +$40.17 |
| **RIDE with NO ER filter** | ALL 17d | **58** | **+$2,238** | **+$833** | +$38.58 |
| RIDE with `ER30 < 0.20` | DEV | 37 | +$1,290 | −$2 | +$34.85 |
| **RIDE with NO ER filter** | DEV | 41 | **+$1,763** | **+$358** | +$42.99 |
| RIDE with `ER30 < 0.20` | HOLDOUT | 14 | +$759 | −$303 | +$54.24 |
| **RIDE with NO ER filter** | HOLDOUT | 17 | +$475 | −$430 | +$27.95 |

**The filter costs money and costs sample.** It is better on the 5-day holdout by $284 and worse on
the 12-day DEV by $473 and worse on the union — that is noise, not a filter. The same happened to
the close-location confirm: at clv 0.5 / 0.6 / 0.7 the results were **+$830 / +$830 / +$832** — three
identical numbers, because a 30-point 15-minute move already closes near its extreme, so the filter
selects nothing.

The later filter menu (§9) confirms it from the other end: `skip ER ≥ 0.35` on the final spec gives
+$3,462 against the naked +$4,169. **Every efficiency-ratio gate tested made the OPEN RIDER worse.**

**Why the forward-return table lied:** it is measured on *overlapping* one-minute samples with a
15-minute forward window, so 1,769 rows is perhaps 120 independent observations, and the ER buckets
are heavily day-clustered (one quiet day fills the low-ER bucket). Once the same idea is traded with
a stop and a cooldown, the effective n collapses to 51 and the separation evaporates.

## 5. Invention B — OPEN EXHAUSTION FADE: **REFUTED.** 51 configurations, every one negative.

This is the most seductive failure in the whole study, so it gets its own section.

**Day-demeaned** (see §7 for what that means), the exhaustion fade has the strongest signal I found
anywhere in this cluster:

| Arm | n | demeaned fwd-15 | win% | t | Long | Short |
|---|---|---|---|---|---|---|
| fade `ER30 ≥ 0.40` | 222 | +28.8 pt | 56.3% | +4.40 | +23.8 | +33.3 |
| fade `ER30 ≥ 0.45` | 117 | **+54.2 pt** | 65.8% | **+5.69** | +54.2 | +54.1 |
| fade `ER30 ≥ 0.50` | 62 | +81.2 pt | 72.6% | +5.85 | +64.3 | +99.3 |
| fade `ER30 ≥ 0.55` | 27 | +117.4 pt | 77.8% | +4.93 | +78.7 | +153.3 |

Both sides. Monotone. Huge t-stats. And it **cannot be traded**, because of the path:

| Entry type | median MFE (ATR) | median MAE (ATR) |
|---|---|---|
| RIDE (with the move) | 3.69 | 2.55 |
| **FADE (against the move)** | 3.00 | **4.76** |

The fade goes **further against you than for you before it works**. It is adverse from the first
tick — the same signature the desk found on abs_veto's four overnight losers. So every stop you can
afford is hit first. The evidence:

| Family | configs tested | best | worst | win% range |
|---|---|---|---|---|
| Immediate fade (stop 1.25–4.0 × ATR × RR 1.5/2.0/3.0) | 15 | **−$775** | −$1,457 | 10–30% |
| Confirmed fade (wait for a 3/5/10-min break back, stop 1.5–2.5, RR 2.0/3.0, ER 0.40/0.45/0.50) | 36 | **+$10** (n=21) | −$1,886 | 6–38% |

**51 out of 51 negative or zero.** Widening the stop does not help (−$973 at 2.5 ATR, −$1,457 at
3.0 ATR); waiting for confirmation does not help; the mean R is between **−0.30 and −0.83** in every
delayed-entry cell. And it caught **0 of the 14** sat-out runs.

**This is a REFUTATION, not a park,** and the named test is the **51-cell exit/entry-timing grid plus
the MFE/MAE path measurement**: the entry has real 15-minute information (t = +5.69 demeaned) but it
is delivered *after* a 4.8-ATR excursion against you, and there is no stop, no target and no
confirmation delay inside the tested space that survives that excursion. The only reformulation left
would be an options-style payoff or a scale-in against the move, neither of which this desk trades.

## 6. Invention C — THE OPEN RIDER: the survivor

**Full spec, no discretion left in it:**

```
WINDOW     13:00–15:00 UTC
CADENCE    every 5 minutes; if FLAT, take a trade
TRIGGER    none — the clock is the trigger
DIRECTION  sign( close(t) − close(t − 15 min) )
ENTRY      market at the close of that 5s bar
STOP       2.0 × ATR1m   (ATR1m = mean 1-min high−low over the trailing 15 min; floor 4 pt)
TARGET     2R  (= 4.0 × ATR1m from entry)
TIME CAP   45 minutes, then out at market
RE-ENTRY   blocked until the open trade is closed
COST       $5 round trip, MNQ 1 lot, $2/point
```

Mean stop distance **54.6 pt = $109 of risk a trade**. That is **four to five times** what the live
gates risk, and it is the single most uncomfortable fact about this candidate — see §10.

### Headline

| Period | n | net | win% | $/trade | R/trade | Long | Short |
|---|---|---|---|---|---|---|---|
| **ALL 17 days** | **129** | **+$4,169** | **48.1%** | **+$32.32** | **+0.272R** | +$1,475 (58) | +$2,695 (71) |
| DEV 12d (07-16 → 07-31) | 90 | +$3,447 | 50.0% | +$38.30 | +0.346R | +$896 | +$2,552 |
| HOLDOUT 5d (08-03 → 08-07) | 39 | +$722 | 43.6% | +$18.51 | +0.102R | +$579 | +$143 |

Exit mix: **STOP 66 / TARGET 51 / TIME 12**. Total **+35.1R** banked over 17 days, **7.6 trades a
day**, and — this matters operationally — **it is in the market essentially 100% of the 13:00–15:00
window** (a five-minute cadence with 45-minute caps means the next trade starts the moment the last
one ends). It is not a gate that waits for a setup; it is a **two-hour always-in posture that
re-picks its side every time it gets flat**. Anyone deploying it should read it as a second desk for
two hours a day, not as a seventh gate in the tournament.

A look-ahead audit was run on all 129 trades: every feature index is strictly before the entry bar,
every exit index strictly after it, and the stored ATR reproduces exactly from past bars only. Zero
failures.

## 7. The robustness battery — including the test that wounds it

### TEST 1 — parameter sweep: **PASSED, and it is the strongest evidence here**

The operator's specific worry is *"does the edge only appear as n collapses?"* Here it is the
opposite. Full grid, `cadence × stop_k × RR`, 100 cells, each shown as **net / net-after-strip-3 / n
/ mean R**:

| cadence 5 min | RR 1.0 | RR 1.5 | RR 2.0 | RR 2.5 | RR 3.0 |
|---|---|---|---|---|---|
| **stop 1.0×ATR** | −566/−897/349/−0.07 | −692/−1189/302/−0.07 | +1012/+344/264/+0.00 | +2054/+1245/234/+0.09 | +1306/+368/205/+0.04 |
| **stop 1.5×ATR** | +1275/+795/257/+0.04 | +2392/+1641/200/+0.09 | +1665/+739/174/+0.05 | +1845/+721/148/+0.09 | +2193/+860/140/+0.13 |
| **stop 2.0×ATR** | +2457/+1788/186/+0.08 | +3469/+2544/141/+0.18 | **+4169/+2931/129/+0.27** | +4161/+2868/107/+0.35 | +5893/+4405/95/+0.55 |
| **stop 2.5×ATR** | +4397/+3628/144/+0.22 | +4202/+3056/118/+0.24 | +5283/+3990/94/+0.41 | +7029/+5521/86/+0.58 | +4143/+2412/87/+0.37 |
| **stop 3.0×ATR** | +3033/+2147/119/+0.18 | +4166/+2918/97/+0.28 | +6133/+4683/84/+0.49 | +4196/+2549/80/+0.41 | +3511/+1674/75/+0.42 |

The same shape holds at cadence 3, 10 and 15 minutes. **Every cell with stop ≥ 2.0 × ATR is positive
in net AND positive after stripping its three best trades**, at every cadence and every target — that
is a 40-cell contiguous plateau, not a spike. The chosen spec (2.0 / 2.0) is deliberately the
plateau's **bottom-left corner**, not the maximum (2.5 / 2.5 at +$7,029), precisely so the headline
is not the number the grid was mined for.

The tell runs the *right* way: the plateau is where n is **largest** (129–215 trades) and the mess is
in the narrow-stop cells. **The desk's standard ~1-ATR stop is exactly the wrong stop for this
signal** — that is a finding in its own right.

### TEST 2 — walk-forward, parameters chosen on DEV only: **PASSED**

192 cells (`threshold × stop × RR × cooldown`) fitted on the 12 DEV days and scored on the 5
holdout days:

| | count |
|---|---|
| cells positive on DEV | **181 / 192** |
| cells positive on HOLDOUT | **179 / 192** |
| mean HOLDOUT across all 192 cells | **+$582** (median +$609) |
| mean HOLDOUT of the DEV-top-10 | +$853 |
| mean HOLDOUT of the DEV-bottom-10 | +$645 |

The gap between picking the DEV-best and picking the DEV-worst is **$208** — i.e. **the selection tax
is almost nil, because the whole surface works.** That is the opposite of the VACUUM result, where
the walk-forward policy cost −$1,267 against the blanket best.

### TEST 3 — strip the best trades: **PASSED to strip-5, fails at strip-10**

| | net | n |
|---|---|---|
| full | +$4,169 | 129 |
| strip best 1 | +$3,701 | 128 |
| **strip best 3** | **+$2,931** | 126 |
| strip best 5 | +$2,188 | 124 |
| strip best 10 | +$468 | 119 |
| (strip *worst* 3) | +$4,779 | 126 |

70% of the net survives removing the three best trades; 11% survives removing ten. **Ten trades out
of 129 carry 89% of the money.** That is concentration, and it is honest to call it a weakness — but
it is also the arithmetic of a 2R system with a 48% hit rate, where winners are 2× losers and the
tail is where trend lives. The plateau's strip-3 column (above) shows this is not one lucky cell.

### TEST 4 — leave-one-day-out and both halves: **PASSED / MIXED**

Leave-one-day-out is **positive on all 17 drops**, from **+$3,282** (dropping 07-30, the best day) to
+$4,726. **12 of 17 days green.** Both halves are positive but wildly uneven: first half
**+$323 on 51 trades**, second half **+$3,846 on 78 trades**. The first eight sessions were a
grind — that is a real warning about how long a flat stretch can run.

### TEST 5 — long/short symmetry: **PASSED**

**Long +$1,475 (58 trades, 46.6%) · Short +$2,695 (71 trades, 49.3%).** Both sides positive over the
17 days, on a tape whose in-window drift was −4.58 pt (mildly short-favouring, which explains the
tilt). Per-period the sides split with the period's drift (DEV: L +$896 / S +$2,552 on a down-biased
stretch; HOLDOUT: L +$579 / S +$143 on an up-biased week) — the union is what makes it symmetric,
and that is exactly the point of using both.

### TEST 6 — placebo null and the direction controls: **PASSED, decisively**

Same 129 entry bars, same stop and target geometry, **direction chosen at random**, 400 draws:

| | net |
|---|---|
| placebo mean | **+$7** (sd $1,850) |
| **the strategy** | **+$4,169** → **z = +2.25, one-sided p = 0.018** |
| the strategy REVERSED (fade instead of ride) | **−$4,975** (−0.353R) |
| always LONG at the same bars | −$1,981 (−0.122R) |
| always SHORT at the same bars | +$527 (+0.000R) |
| alternating direction every 10 min (null) | −$1,269 (−0.113R) |

The placebo lands on zero, which validates the cost model — random direction with a 2R target and a
$5 cost is a fair coin. **Ride and reverse are $9,144 apart on the same 129 bars**, and neither
constant-direction control explains it. The direction rule is doing the work.

### TEST 7 — **the day-drift test: FAILED. This is the wound.**

Here is the test I could not get it past, and it is the same one that decides the VACUUM report.

Subtract, from every forward return, the **mean forward return of that same day's window**. What is
left is pure *timing skill within the day* — did you pick better moments than a blindfolded constant
position on that day would have?

| momentum entries, `|mom15| ≥ 30 pt`, n = 1,314 | RAW forward | **DAY-DEMEANED** | t |
|---|---|---|---|
| 15 min ahead | +11.08 pt (57.5%) | **−0.70 pt** (51.4%) | −0.30 |
| 30 min ahead | +8.54 pt (53.9%) | **−14.39 pt** (47.5%) | −4.61 |
| 45 min ahead | +13.95 pt (55.2%) | **−18.94 pt** (45.6%) | **−5.35** |
| 60 min ahead | +11.13 pt (52.9%) | **−28.95 pt** (40.0%) | −7.82 |

**Every raw number is positive; every demeaned number is negative, on both sides, and it gets worse
the longer you hold.** In plain English: the entries have *no* skill at picking moments. All of the
raw positive is that the momentum rule ends up on the side the whole two-hour window went. Two
corroborations:

- Correlation between **|the day's 13:00–15:00 net move|** and **that day's strategy P&L: +0.597.**
  Days where the window moved ≥120 pt net: **+$209 a day** (13 days). Days where it moved less:
  **−$119 a day** (4 days).
- A duty-matched control that replaces the 15-minute momentum with the crudest imaginable rule —
  *"is price above where it was at 13:00?"* — scores **+$2,627 on 97 trades** against the momentum
  version's **+$2,576 on 101**. **Identical.** The fifteen-minute lookback is not the signal. "Which
  way has today gone" is the signal.

**So what is the OPEN RIDER, honestly?** It is a **mechanically unbiased way to be long the
directionality of the US-open window**, harvested through a 2R payoff with a wide stop. That is a
real thing to own — the open *is* the most directional two hours of the session (39% big-run rate
against 7% elsewhere) — but it is not a timing edge, and its P&L will track how trendy the open is,
week to week, with nothing in the signal to warn you when that stops.

One thing does survive demeaning: forcing an **equal number of longs and shorts within each day**
(which removes day direction by construction) still leaves **+$1,418 on 72 trades, +$19.69 a trade**
— 55% of the money. So it is not *purely* a direction bet; the 2R-with-a-wide-stop payoff shape is
harvesting the genuine right-skew of open-window moves (median MFE 3.69 ATR vs median MAE 2.55 ATR).
But the majority of the headline is day direction.

### TEST 8 — tick-honest re-price: **PASSED on mechanics, FAILED on size**

On the only 5 days with tick and quote data, every trade was re-priced properly: **entry at the live
quote you would actually pay** (ask if long, bid if short — you cross the spread), and stop/target
checked against **every trade print in sequence** rather than against 5s bar extremes.

| Holdout week 08-03 → 08-07 | n | net | win% | STOP / TARGET / TIME |
|---|---|---|---|---|
| 5s-bar model | 39 | +$722 | 43.6% | 22 / 13 / 4 |
| **tick + quote honest** | 39 | **+$238** | 43.6% | 22 / 11 / 6 |

Mean quoted spread at entry **0.615 pt ($1.23 of the $5 allowance)**. First the reassuring part: on
600 sampled 5s bars the bar highs and lows agree with the tick prints to **+0.04 pt and +0.05 pt on
average** — the bars are faithful, and with a 2-ATR stop the intrabar path assumption is irrelevant
(the earlier ER-filtered variant re-priced to within **$7 on 17 trades**).

Now the unflattering part. Only **6 of 39** trades moved by more than $1, and **two of them account
for $478 of the $484**:

| Trade | 5s model | tick-honest | why |
|---|---|---|---|
| 08-06 long | +$378 TARGET | **+$224 TIME** | entry 0.50 pt worse → target missed, timed out |
| 08-07 short | +$393 TARGET | **+$70 TIME** | entry 0.50 pt worse → target missed, timed out |
| 08-03 long | +$313 TIME | +$311 TIME | quote 2.50 pt off the bar close (a wide-spread instant) |
| other 3 | — | −$2 to −$4 each | half a spread |

So this is **not** a systematic 33% haircut; it is **two knife-edge trades whose 2R target was
grazed by under half a point**. That is still a real cost — those coin flips will land against you as
often as for you — and the honest way to carry it is a blanket entry-slippage assumption. Half a
point of entry slippage applied to all 17 days pulls the headline from **+$4,169 to +$3,491**
(**+0.229R a trade**, n=128), and reproduces the holdout at +$204 against the tick truth of +$238.
**+$3,491 / +0.229R is the number to plan against.**

## 8. Big moves caught — and the operator's narrowing hypothesis, **confirmed**

Aligned direction, a trade opened within ±15 minutes of the run start.

| Configuration | sat-out runs caught | net on the hits | also hit the already-caught 10 |
|---|---|---|---|
| **OPEN RIDER cad 5 / 2.0 / 2R** | **11 / 14** | +$549 | 8 / 10 |
| OPEN RIDER cad 3 / 2.0 / 2R | 11 / 14 | +$243 | 7 / 10 |
| OPEN RIDER cad 5 / 2.5 / 2.5R | 10 / 14 | +$766 | 6 / 10 |
| COIL-CRACK (ER < 0.20) | 2 / 14 | −$15 | 5 / 10 |
| OPEN EXHAUSTION FADE | **0 / 14** | — | 1 / 10 |

The three misses are **08-05 14:54 (+73)**, **08-06 14:03 (+152)** and **08-06 14:46 (+120)** — all
three are runs that began while the RIDER was already in an open position facing the other way, so
the cooldown, not the signal, missed them. Cadence 3 recovers 08-06 14:03.

**And the operator's specific hypothesis — that narrowing to the biggest runs may reveal a stronger
footprint — is CONFIRMED here, which is the opposite of what VACUUM found:**

| Cut (census week, 14 sat-out) | caught | rate |
|---|---|---|
| top-5 biggest | 4 / 5 (5/5 at cadence 3) | 80–100% |
| top-8 biggest | 6 / 8 (7/8 at cadence 3) | 75–88% |
| all 14 | 11 / 14 | 79% |

| Cut (17-day tape, all 78 OPEN/NEWS runs) | caught | rate |
|---|---|---|
| **top-15 biggest** | **15 / 15** | **100%** |
| top-25 biggest | 23 / 25 | 92% |
| all 78 | 62 / 78 | 79% |

**The OPEN RIDER is on every one of the fifteen biggest OPEN/NEWS runs of the last seventeen
sessions.** It is a participation machine — which is precisely the hole the census identified (54
sat-out runs, $9,917 of ceiling, of which OPEN/NEWS sat-outs were $3,138).

## 9. The regime work — per-segment scores and a walk-forwarded policy

Per the standing discipline, nothing here is a blanket number. Regimes are assigned **at entry, from
past-only data**: ER30 ≥ 0.35 → CLEAN-TREND; 0.20–0.35 → BUILDING; below that, ATR1m terciles
(<18.4 / 18.4–33.8 / ≥33.8 pt) split DEAD-CHOP / NORMAL-CHOP / VIOLENT-WHIPSAW.

| Regime | n | net | win% | $/trade | R/trade | strip-3 | Long | Short |
|---|---|---|---|---|---|---|---|---|
| **VIOLENT-WHIPSAW** | 24 | **+$2,036** | 58.3% | +$84.85 | **+0.454R** | +$888 | +$957 | +$1,080 |
| BUILDING | 40 | +$1,342 | 50.0% | +$33.56 | +0.289R | +$270 | −$109 | +$1,451 |
| DEAD-CHOP | 20 | +$494 | 50.0% | +$24.68 | +0.399R | +$134 | +$318 | +$175 |
| **CLEAN-TREND** | 26 | +$154 | 42.3% | +$5.93 | +0.151R | **−$826** | −$3 | +$158 |
| **NORMAL-CHOP** | 19 | +$143 | 36.8% | +$7.52 | +0.038R | **−$550** | +$312 | −$169 |

| Time-of-day segment | n | net | win% | $/trade | R/trade |
|---|---|---|---|---|---|
| PRE-OPEN 13:00–13:30 | 39 | +$822 | 51.3% | +$21.09 | +0.439R |
| **OPEN-DRIVE 13:30–14:00** | 48 | **+$3,207** | 50.0% | **+$66.82** | +0.380R |
| POST-OPEN 14:00–14:30 | 20 | +$464 | 50.0% | +$23.18 | +0.098R |
| **LATE 14:30–15:00** | 22 | **−$324** | 36.4% | −$14.73 | −0.101R |

**Two things worth saying out loud.** First, **CLEAN-TREND is the second-worst bucket and goes
negative on strip-3** — a momentum system that does badly when the last half hour was a clean trend.
That is the exhaustion effect again, arriving from a third direction, and it is why the ER filter in
§4 kept failing: by the time ER is high the move is late. Second, **VIOLENT-WHIPSAW is the best
bucket** at +0.454R — the wide stop is what makes that possible, and it is exactly where a 1-ATR stop
would be shredded.

### The R-ladder, swept rather than guessed

The desk's cheat-sheet Rs (faders 0.5/1.5, momentum 1.5/2.5, trend 2.5/wide) are an operator prior.
Swept per segment at stop 2.0 × ATR (net / n / mean R):

| Segment | RR 1.0 | RR 1.5 | RR 2.0 | RR 2.5 | RR 3.0 | RR 4.0 | **proven best** | vs the guess |
|---|---|---|---|---|---|---|---|---|
| PRE-OPEN | +253/51/+0.08 | +823/39/+0.38 | +822/39/+0.44 | +840/32/+0.54 | **+1238/29/+0.83** | +1068/27/+0.83 | **3.0R** | wider than the 1.5–2.5 guess |
| OPEN-DRIVE | +2192/69/+0.20 | +2466/56/+0.20 | **+3207/48/+0.38** | +2651/43/+0.37 | +2879/41/+0.41 | +2174/33/+0.32 | **2.0–3.0R** | matches "momentum 1.5/2.5", edge to wider |
| POST-OPEN | +558/36/+0.07 | +299/26/+0.05 | +464/20/+0.10 | +374/14/+0.13 | +1252/9/+1.01 | +726/13/+0.47 | **inconclusive (n=9–36)** | no verdict |
| LATE | −546/30/−0.17 | −119/20/−0.05 | −324/22/−0.10 | +296/18/+0.11 | +523/16/+0.16 | −404/18/−0.22 | **stand down** | — |

And the stop is the bigger lever than the target: at RR 2.0, PRE-OPEN goes **+$196 → +$1,699** as the
stop widens from 1.0 to 3.0 ATR (+0.07R → +0.85R), and POST-OPEN goes **−$119 → +$1,782**. **The
proven answer is "give it room", in every segment.**

### The policy, walk-forwarded honestly

Segments and their R chosen **on the 12 DEV days only**, then applied blind to the holdout:

| Segment | DEV says | DEV result | HOLDOUT result |
|---|---|---|---|
| PRE-OPEN | RR 3.0 | +$1,170 (n=19) | +$68 (n=10) |
| OPEN-DRIVE | RR 2.0 | +$2,542 (n=34) | +$665 (n=14) |
| POST-OPEN | RR 3.0 | +$942 (n=7) | +$310 (n=2) |
| LATE | RR 3.0 | +$541 (n=12) | −$18 (n=4) |
| **POLICY total on HOLDOUT** | | | **+$1,025 on 30 trades** |
| blanket 2.0/2R on HOLDOUT | | | +$722 on 39 trades |

**The regime-conditional policy beats the blanket by $303 out of sample on 9 fewer trades** — a
+$34.17/trade policy against +$18.51/trade blanket. It is a small, thin-n win, but it points the same
way the discipline predicts, and unlike VACUUM (where the policy cost $1,267) here it earns its keep.

### Filters tested against the naked spec — one improves it

| Filter on the OPEN RIDER | ALL n | ALL net | R/trade | strip-3 | DEV | HOLDOUT |
|---|---|---|---|---|---|---|
| **none (the spec)** | 129 | +$4,169 | +0.272 | +$2,931 | +$3,447 | +$722 |
| **inside the pre-open range (12:00–13:30 hi/lo)** | 73 | +$3,692 | **+0.446** | +$2,485 | +$2,569 | **+$1,123** |
| outside the pre-open range | 61 | +$1,132 | +0.080 | −$52 | +$656 | +$475 |
| stand down 14:30–15:00 | 107 | **+$4,493** | +0.349 | +$3,255 | +$3,800 | +$693 |
| stand down after 14:00 | 87 | +$4,030 | +0.407 | +$2,791 | +$3,419 | +$611 |
| skip ER30 ≥ 0.35 | 112 | +$3,462 | +0.248 | +$2,223 | +$2,749 | +$713 |
| ATR1m ≥ 25 pt floor | 71 | +$3,655 | +0.310 | +$2,414 | +$2,919 | +$736 |
| `|mom15| ≥ 1 × ATR1m` | 110 | +$2,818 | +0.213 | +$1,632 | +$2,596 | +$222 |

**The one filter that improves risk-adjusted return *and* the holdout is "only trade while price is
still inside the pre-open range".** +0.446R against +0.272R, and it nearly doubles the holdout. Its
mirror loses (outside the range: +0.080R, strip-3 negative). That is the **don't-chase-the-extension**
rule the desk already believes from abs_veto, arriving independently. It halves the sample (129 → 73)
and it was picked from a menu of ten, so it is a **shadow refinement, not part of the headline spec**.

## 10. Disposition table

| Lead | Verdict | The named test that decided it / what would revive it |
|---|---|---|
| **C. THE OPEN RIDER** — 5-min cadence, direction = last 15 min, 2.0×ATR stop, 2R, 45-min cap, 13:00–15:00 UTC | **SHADOW** | Survived: a 40-cell contiguous parameter plateau (all positive net **and** positive after strip-3); a 192-cell DEV→HOLDOUT walk-forward with 179/192 cells positive out of sample and a near-zero selection tax; strip-3 (+$2,931 of +$4,169); LOO positive on all 17 days; long/short both positive; placebo z=+2.25, p=0.018; reversal −$4,975. **Not LIVE because of three things:** (1) the **day-demeaned timing test fails** — all of the raw edge is "the open window went somewhere", none is moment-picking (t = −5.35 at 45 min); (2) the **tick-honest re-price is worse** than the 5s model ($722 → $238 on the holdout week, driven by two knife-edge target misses), so plan on **+$3,491 / +0.229R** not +$4,169; (3) it risks **$109 a trade**, 4–5× the live gates. **PROMOTE TO LIVE IF:** it clears **+0.15R a trade over 200 shadow trades (~30 sessions)** including at least one demonstrably **non-trending open week** — that is the exact regime the demeaned test says will hurt it. |
| **A. COIL-CRACK** — momentum ignition out of a quiet 30 minutes (ER30 < 0.20) | **REFUTED as a filter** (the underlying momentum entry lives on inside C) | **Direct ablation**, the only test that decides a filter: with the ER gate +$2,049 / n=51 / strip-3 +$724; **without it +$2,238 / n=58 / strip-3 +$833**. It costs money and sample. Confirmed from the other side on the final spec (`skip ER ≥ 0.35` → +$3,462 vs +$4,169). The close-location confirm was worse than useless — clv 0.5 / 0.6 / 0.7 returned +$830 / +$830 / +$832, i.e. it selected nothing. The beautiful monotone ER table that motivated it is an artefact of **overlapping one-minute sampling** (1,769 rows ≈ 120 independent observations, heavily day-clustered). No reformulation: a filter that removes trades and money has nothing to reformulate. |
| **B. OPEN EXHAUSTION FADE** — fade a straight-line 30 minutes (ER30 ≥ 0.45) | **REFUTED** | **51 configurations, every one negative or zero**: 15 immediate-entry cells (−$775 to −$1,457, 10–30% win) and 36 confirmed-entry cells (best +$10 at n=21, worst −$1,886, mean R −0.30 to −0.83). The mechanism is disproven by the **path measurement**: median MAE **4.76 ATR** against median MFE **3.00 ATR** — it is adverse from the first tick, so the 15-minute information it genuinely carries (demeaned +54.2 pt, t = +5.69) is delivered only after an excursion no affordable stop survives. Caught **0 / 14** of the target runs. Widening the stop to 3–4 ATR and delaying entry by 10 minutes both fail, which closes the two obvious reformulations. |
| **D. The regime-conditional policy** (segment → R, walk-forwarded) | **SHADOW** | The only regime work in this cluster that paid: DEV-chosen segments and Rs scored **+$1,025 on 30 holdout trades vs +$722 on 39** for the blanket — **+$34.17/trade vs +$18.51/trade**. But per-segment n is **19–48** and two buckets (CLEAN-TREND, NORMAL-CHOP) go negative on strip-3. **REVIVE/PROMOTE IF:** each segment reaches **n ≥ 60** — about 25 more sessions of shadow — at which point the LATE (14:30–15:00) stand-down and the PRE-OPEN wide-R rung are the two rungs worth deploying first. |
| **E. Pre-open-range containment** ("only trade while price is still inside the 12:00–13:30 range") | **SHADOW** | Best filter found: **+0.446R vs +0.272R**, holdout **+$1,123 vs +$722**, and its mirror loses (+0.080R, strip-3 −$52), which is the sign of a real asymmetry rather than a coin. Independently reproduces the desk's own abs_veto **"don't chase the extension"** finding. Held out of the headline spec because it **halves the sample (129 → 73)** and was **selected from a menu of ten filters** — the multiple-comparison tax is unpaid. **PROMOTE IF:** it holds at +0.40R over the next 60 shadow trades. |
| **F. The 15-minute momentum trigger itself** (any threshold: 20 / 25 / 30 / 40 / 50 pt) | **REFUTED as a trigger** | Thresholding **always cost money**: no threshold +$4,142 on 102 trades vs thr-20 +$2,576 and thr-50 +$1,366 at the same cadence. Worse, a **duty-matched control** replacing the 15-minute lookback with *"is price above the 13:00 print?"* scored **+$2,627 / 97** against momentum's **+$2,576 / 101** — statistically the same. **The lookback is not the signal; being positioned with the window's direction is.** No path: there is nothing to tune in a parameter that does not matter. |
| **G. Narrow (≈1 ATR) stops — the desk's house style** | **REFUTED for this cluster** | Across the 100-cell grid, **every** stop ≤ 1.5 × ATR1m is flat-to-negative on mean R (−0.09 to +0.13) while **every** stop ≥ 2.0 × ATR1m is positive (+0.18 to +0.58), at every cadence and target. The median MAE of a with-the-move entry in this window is **2.55 ATR** — a 1-ATR stop is inside the noise by construction. Named test: the mean-R plateau, which is risk-normalised and therefore not a leverage illusion. |
| **H. "Regime label picks the trade"** (the 5-state ATR×ER×range-break classifier as an on/off switch) | **PARKED** | The labels behaved **backwards**: CLEAN-TREND was the second-worst bucket (+0.151R, strip-3 −$826) and VIOLENT-WHIPSAW the best (+0.454R). Either the classifier is mislabelling, or the true structure is "already-trending = already-late", which is what every other test in this report also said. n per bucket is 19–40, far too thin to deploy an on/off switch. **REVIVE IF:** re-cut the classifier on **forward-looking realised trendiness measured over the hold**, not on trailing ER — and only once each bucket has n ≥ 60. |

**★ The one stone still unturned.** Everything here is built from 5-second bars, because that is the
only representation that spans 17 days. The **L2 book (82M rows) and the aggressor tape are never
used** in this cluster — and the one question they could answer is the one the day-drift test raises:
**can you tell, at 13:30 UTC, whether this open is going to trend or chop?** If that is knowable at
all it will be in the opening auction's depth and the first minutes' aggressor imbalance, not in the
bars. That is a five-day study today and a proper one in three weeks. It is the only thing that would
turn the OPEN RIDER from a directional harvest into an edge.

## 11. What to take away

1. **OPEN/NEWS is not an event cluster, it is the clock.** 39% of quarter-hours in 13:00–15:00 UTC
   are "big runs" against 7% everywhere else. The census is right that we sit out the money; it is
   not right that anything unusual is happening when we do.
2. **The simplest thing beat both clever things, and the gap was not close.** Two hand-built
   footprint signals lost $2,000–$5,000 between them; the control that just shows up every five
   minutes with a wide stop made +$4,169 and caught 15 of the 15 biggest runs.
3. **The stop, not the entry, was the lever.** Every filter tested made it worse; every widening of
   the stop made it better, on a risk-normalised basis. **The desk's ~1-ATR house stop is the wrong
   instrument for the US open** — that finding is transferable to the live gates immediately and
   costs nothing to check.
4. **The day-demeaning test should become standard on this desk.** It is what separated a real
   payoff-shape edge from a directional bet in this study, and it is what should have been run on
   the momentum-continuation number (+13.4 pt, 58.9% win) before anyone got excited — that number is
   entirely the day's drift and demeans to **−0.70 pt**.
5. **17 days of 5s bars is worth more than 5 days of ticks.** The single reason this hunt has a
   survivor and the VACUUM hunt does not is that a clock-defined cluster can be studied on the whole
   bar tape and therefore can have a walk-forward. Where a study can be built bars-only, build it
   bars-only.

*Working: `/home/alphabot/gazbot7/scratchpad/gf_on/` — `core.py` (data + census run detector),
`feats.py` (ATR / ER / forward-return scan), `dial.py` (COIL-CRACK + EXHAUSTION-FADE engine),
`rider.py` (the OPEN RIDER + battery), `tickcheck.py` (tick + quote honest re-price).
Data: `data/capture.db`, read-only, DuckDB.*
