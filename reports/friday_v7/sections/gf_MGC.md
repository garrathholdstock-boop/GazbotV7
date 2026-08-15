# THE GOLD GATE HUNT — MGC, greenfield, 2026-08-15

**Garrath — the short version.** We have found something in gold, and it is not the thing anyone was
looking for. Every attempt to build a *momentum* gate on MGC has failed again this week, for the
sixth, seventh and eighth time — but in failing it pointed at the answer. **Gold's breakouts are
traps.** When gold pushes through its own hour-high or hour-low and there is *no resting interest
within a point of that level on either side of the book*, price comes straight back, and it does so
often enough and far enough to pay for the trade twice over. That one trigger, split by what the
order book was doing at the moment of the break, gives you three of the four cells you asked for:

| cell | gate | n | net | $/trade | verdict |
|---|---|---|---|---|---|
| REVERSION-LONG | `mgc_hole_break_fade` (fade a DOWN break) | 72 | **+$1,387** | **+$19.27** | **SHADOW** |
| REVERSION-SHORT | `mgc_hole_break_fade` (fade an UP break) | 85 | **+$1,261** | **+$14.84** | **SHADOW** |
| MOMENTUM-LONG | `mgc_wall_break_go` (follow a break that ate a defended level) | 36 | +$380 | +$10.56 | **SHADOW (thin)** |
| MOMENTUM-SHORT | `mgc_wall_break_go` | 27 | +$365 | +$13.53 | **SHADOW (thin)** |

*(Those reversion figures are the refined "hole on both sides" rule, n=157. The simpler rule — far
side empty only, n=219 — makes +$1,365 long and +$1,365 short at +$13.25 and +$11.77 a trade, and it
is the one I want shadowed as the **primary** arm, with the refinement alongside it. Why, in §5.1.)*

Nothing here is a live promotion and I am not proposing one. The reversion pair is the real find —
22 days, five ISO weeks, every week green, both halves green, both capture blocks green, beaten by
zero of thirty placebo draws, still green after paying an extra tick of slippage each way. The
momentum pair is a **glimmer**, not a result: 63 trades on 15 days, and it loses money on the July
leg. Both go in the shadow book to accumulate n, which is exactly what that book is for.

And one number underpins the whole section, so it goes first: **a round trip in gold costs $7.50,
not $1.50.** Every previous gold study on this desk has been scored at $1.50.

---

## 1. THE RULER — what I measured with, and the one correction that changes every prior number

### 1.1 The tape

I used the Parquet lake, never `capture.db` (five trading days would have given me a fifth of this
and no error to tell me). Two things about gold's tape are worth stating because they decide how
much you can believe anything below.

| stream | span | days | note |
|---|---|---|---|
| MGC L1 bars (5s) | 07-07 … 07-17, 08-05 … 08-14 | 18 | **two islands with a three-week hole** |
| MGC L1 ticks | same | ~20 | same hole |
| MGC L2 depth (`depth.db.depth_snap`, 10 levels, 250ms) | **07-16 … 08-14** | **22** | **no gap** |

The depth capture kept running through the window where the L1 mirror did not. And depth carries
`bid1p`/`ask1p`, so **it is also a price tape**. I re-validated that from scratch rather than
inheriting it: across **13,440 minutes where both streams exist**, the quote mid and the traded close
correlate at **0.999998** with a median absolute difference of **0.150pt** — half a spread, which is
exactly what it should be. So every number in this section is built on **22 contiguous days of
quote-mid minute bars, 2026-07-16 to 2026-08-14, 29,565 minutes, raced on 352,699 five-second
bid/ask bars.**

That matters three ways. It closes the hole, so the sample is one block instead of two islands. It
adds **twelve days (07-20 … 08-04) that no gold study has ever touched** — all six refuted attacks
in `docs/MGC_LEADS_2026-08-14.md` were fitted on 08-05 onward — which makes the July block a genuine
out-of-sample leg rather than a random split of one fitted sample. And racing on quotes rather than
trades is what makes an honest cost model possible at all.

### 1.2 ★ The cost correction, and it is not small

Per `docs/CAPPED_MARKETABLE_LIMIT_ENTRIES.md` the live desk enters on a **marketable limit, IOC** —
it crosses — and "CLOSES / FLATTENS stay MKT", which crosses too. So both legs pay the spread.

```
MGC spread   median 0.30 pt   (p25 0.20, p75 0.40)   flat round the clock, ~5 lots at the touch
0.30pt x 2 legs x $10/pt = $6.00 of spread
                         + $1.50 fee
                         = $7.50 per round trip
```

Gold's ATR over this window runs **1.1 – 2.6 points**, so one R is **$11 – $26**. The spread alone is
between a quarter and a half of an R. On MNQ, where R is $30–$50 and the spread is one tick, the same
fee is a rounding error. **On gold it is the main term**, and every gold candidate this desk has ever
judged was judged at a fifth of its true cost.

Everything below is therefore priced twice and both are shown:

- **`true_pnl`** — entry crosses, exit crosses, minus $1.50. **This is the number that decides.**
- **`desk_pnl`** — mid-to-mid, minus $1.50. The old convention, kept only so you can see the gap.

Measured on the momentum grid, the gap is **$3.32 a trade**. There are candidates in this section
that are green on `desk_pnl` and red on `true_pnl`, and they are dead.

### 1.3 The exit race, and how it is biased

Exits are raced on 5-second bid/ask bars. A long is filled on the ask and marked out on the bid; a
short the reverse. Inside a bar the order is **stop, then trail, then target, then extend the peak** —
a 5-second bar does not record whether its high or its low came first, so every ambiguity is resolved
*against* the trade. Every number here is therefore biased **downward**, which is the only direction
a bias is allowed to point.

Two traps from the 08-14 session are hard-coded against: `resample` labels a bar by its **left** edge,
so every entry is stamped at `ts + 60s` (getting this wrong cost the coil gate +$906 → +$470); and the
60-minute extreme is taken over bars **strictly before** the signal bar, because including the signal
bar's own high in its own break level is circular. `lake.connect()` is passed `symbol="MGC"` everywhere.

---

## 2. THE MAP — before building anything, is there a cell to build?

`scripts/gf_mgc_map.py`. No trades, no thresholds: just "conditioned on what gold has *just* done, is
the next interval biased at all, and is the bias continuation or reversal?" Scored against **the best
constant on the same rows**, because `always SHORT` beat every directed gold gate in the 08-05 study.

**The confound, stated up front.** Gold closed up on 13 of these 22 days, mean +$143 a day. A
directional cell that merely reproduces that has found nothing, so everything below is also read
drift-neutral (the average of the two sides).

### 2.1 The one stable structure in the map

Twenty regime × cell combinations, at four impulse horizons, split into calendar halves. Most of it is
noise — at the 20min→60min horizon only **6 of 20** cells agree on sign between halves. But one thing
repeats at two horizons and does not flip:

| horizon | regime | cell | edge vs constant, H1 | edge vs constant, H2 | agree |
|---|---|---|---|---|---|
| 10m ≥1.0 ATR → 30m | CLEAN_TREND | **REV-LONG** | +$6.93 | +$5.20 | ✔ |
| 10m ≥1.0 ATR → 30m | CLEAN_TREND | **REV-SHORT** | +$3.72 | +$7.28 | ✔ |
| 10m ≥1.0 ATR → 30m | CLEAN_TREND | MOM-LONG | −$3.72 | −$7.28 | ✔ |
| 10m ≥1.0 ATR → 30m | CLEAN_TREND | MOM-SHORT | −$6.93 | −$5.20 | ✔ |
| 30m ≥1.5 ATR → 120m | CLEAN_TREND | **REV-SHORT** | +$5.97 | +$0.93 | ✔ |
| 30m ≥1.5 ATR → 120m | CLEAN_TREND | **REV-LONG** | +$6.21 | +$1.03 | ✔ |
| 30m ≥1.5 ATR → 120m | CLEAN_TREND | MOM-LONG | −$5.97 | −$0.93 | ✔ |
| 30m ≥1.5 ATR → 120m | CLEAN_TREND | MOM-SHORT | −$6.21 | −$1.03 | ✔ |

Read it in plain English: **in the regime that looks most like a trend, gold mean-reverts** — both
sides, both halves, two horizons. And the momentum cells in that same regime are negative on both
halves. That is the first of three independent instruments that will say the same thing.

### 2.2 ★ The "size is predictable even if direction is not" question, tested explicitly

You asked for this one by name — if we cannot call the side, can we trade a straddle or a
breakout-either-way? **No, and the premise is false on gold.** A straddle needs the *tightest*
compression to expand *more* than average. It expands **less**:

| 20-min range compression | n | mean abs. 60-min move | vs all |
|---|---|---|---|
| Q1 tightest | 5,895 | $74.96 | **−$6.23** |
| Q2 | 5,895 | $79.58 | −$1.61 |
| Q3 | 5,895 | $82.84 | +$1.65 |
| Q4 | 5,895 | $82.95 | +$1.76 |
| Q5 widest | 5,895 | $85.62 | **+$4.43** |

Rank correlation between the 20-minute range and the size of the next 60 minutes: **+0.036**. Between
ATR and the same: +0.221 — but that is volatility clustering (big begets big), which is not tradeable
on its own and points the wrong way for a straddle anyway. **A coil in gold predicts a smaller move,
not a bigger one.** No trade was taken; the idea dies at the measurement.

---

## 3. ★★★ THE COST FLOOR — the number that killed the last three years of gold ideas

Before any gate: `scripts/gf_mgc_touch.py` takes a plain extension trigger — a 20/30/60-minute move of
1.5–2.5 ATR — and trades it **both ways** through five different target/stop pairs, on 1,000+ entries.

| trigger | barriers | n | FADE $/tr | FOLLOW $/tr |
|---|---|---|---|---|
| 20m ≥1.5 ATR | tp1.0 / sl1.0 | 1,301 | −$5.02 | −$3.60 |
| 20m ≥1.5 ATR | tp0.75 / sl1.5 | 1,301 | −$5.45 | — |
| 30m ≥2.0 ATR | tp1.0 / sl1.0 | 1,128 | −$4.51 | −$4.30 |
| 30m ≥2.0 ATR | tp3.0 / sl1.5 | 1,128 | — | −$5.49 |
| 60m ≥2.5 ATR | tp1.5 / sl1.5 | 1,045 | −$4.31 | — |

**Every cell, both directions, loses.** That is not a contradiction — it is arithmetic. Fade and
follow on the same rows are the same two trades, so they sum to roughly minus twice the round trip.
When the round trip is $7.50 and one R is $16, a 1.0-ATR target pays $16 gross → **+$8.50 net on a
win against −$23.50 on a loss**, so you need to be right about **73% of the time just to break even.**

**That is the wall every gold gate has hit, and it is why the exit matters more here than the entry.**
It also explains the whole shape of what follows: the surviving gates do not take a 1-ATR target. They
take a wide stop and let a snap-back run, because that is the only geometry on gold where the payoff
is big enough to clear a $7.50 floor.

Look at the same rows on the two cost conventions and you can see the floor doing the killing:

| regime / side (follow 20m ≥1.5 ATR, tp3.0/sl1.5) | n | `desk_pnl` $/tr | `true_pnl` $/tr |
|---|---|---|---|
| NORMAL_CHOP LONG | 272 | **+$3.84** | **+$0.74** |
| NORMAL_CHOP SHORT | 277 | +$1.85 | −$3.18 |
| DEAD_CHOP SHORT | 198 | +$0.39 | −$2.11 |
| VIOLENT_WHIPSAW SHORT | 108 | +$1.22 | −$1.18 |

Four cells that look like a gate at $1.50 and are a bleed at $7.50.

---

## 4. THE TRIGGER — a 60-minute level break, and its mirror

**Mechanical spec.** On 1-minute quote-mid bars: `hi = high.rolling(60).max().shift(1)`,
`lo = low.rolling(60).min().shift(1)`. A break is `close ≥ hi + 0.10·ATR` (up) or
`close ≤ lo − 0.10·ATR` (down). Entry at `signal_ts + 60s`. 45-minute cooldown per side.
**449 breaks over 22 days — 228 up, 221 down.**

Traded both ways on a fixed tp1.0/sl1.0 exit so only the direction varies:

| | n | net | win% | $/trade |
|---|---|---|---|---|
| FADE the break (reversion) | 449 | −$1,865 | 41.4% | −$4.15 |
| FOLLOW the break (momentum) | 449 | −$2,597 | 38.1% | −$5.78 |
| …the fade on the old $1.50 mid convention | 449 | −$264 | 41.6% | −$0.59 |

Both red — the cost floor again. **But the trigger is not empty.** Thirty placebo draws of the same
count, on the same days, in the same hours, with the same side mix, at random minutes, through the
identical exit, average **−$3,045**. The fade loses $1,865. **The trigger is worth about $2.63 a
trade of genuine information — against a $7.50 cost.** The signal was real all along; the exit and
the cost were eating it.

### 4.1 ★ Then the exit matrix changed the answer

Rule 3 says the entry and the exit are separate questions. On gold that turns out to be the whole
game. **Same 449 entries, only the exit varies:**

**(a) tight-R scalp, 120-minute cap**

| tp ATR | sl ATR | n | net | win% | $/tr | LONG $/tr | SHORT $/tr | `desk_pnl` net |
|---|---|---|---|---|---|---|---|---|
| 0.50 | 0.50 | 449 | −$1,760 | 34.1% | −$3.92 | −$4.61 | −$3.25 | −$132 |
| 0.75 | 0.75 | 449 | −$1,828 | 40.1% | −$4.07 | −$4.07 | −$4.07 | −$334 |
| 1.00 | 1.00 | 449 | −$1,865 | 41.4% | −$4.15 | −$3.73 | −$4.56 | −$264 |
| 1.50 | 1.50 | 449 | −$1,073 | 47.0% | −$2.39 | −$2.15 | −$2.62 | +$459 |
| 1.50 | 2.00 | 449 | −$882 | 55.5% | −$1.96 | −$1.87 | −$2.05 | +$972 |
| 2.00 | 2.00 | 449 | −$1,007 | 47.7% | −$2.24 | −$2.71 | −$1.79 | +$998 |

**(b) wide chandelier — arm at N ATR, then trail M ATR, 480-minute cap**

| stop ATR | arm | trail | n | net | win% | $/tr | LONG $/tr | SHORT $/tr |
|---|---|---|---|---|---|---|---|---|
| 2.0 | 1.0 | 1.0 | 449 | +$154 | 55.9% | +$0.34 | +$0.68 | +$0.02 |
| 2.0 | 1.5 | 1.5 | 449 | +$1,484 | 51.7% | +$3.31 | +$4.17 | +$2.47 |
| 3.0 | 1.5 | 1.5 | 449 | +$1,556 | 60.4% | +$3.46 | +$4.35 | +$2.60 |
| **3.0** | **2.0** | **2.0** | **449** | **+$1,952** | **55.9%** | **+$4.35** | **+$3.90** | **+$4.78** |
| 5.0 | 2.0 | 2.0 | 449 | +$1,618 | 66.1% | +$3.60 | +$5.29 | +$1.97 |
| 5.0 | 3.0 | 3.0 | 449 | +$1,147 | 57.2% | +$2.55 | +$5.66 | −$0.46 |

**(c) the desk's dual slot** — Lot A scalps 1.0R (−$1,865), Lot B rides the chandelier (+$1,952) =
**+$88 over 449 signals, $0.20 per signal on two lots.** The scalp leg cancels the ride leg almost
exactly. **On gold the dual-slot shape is worthless**, and that is a direct answer to Rule 3(c): the
live MNQ configuration does not transfer.

**(d) time cap, 1.5 ATR stop, no target** — 15/30/60min all negative; 120min +$1,889 but with LONG at
+$8.45 and SHORT at +$0.09; 480min LONG +$11.83 / SHORT −$8.00. **That side-split is the signature of
drift, not edge** — when only the long side pays on a tape that rose 13 of 22 days, the exit is
harvesting the sample, and I have discarded every configuration with that shape.

The exit plateau is real, not a lucky cell. Forty-five chandelier combinations (stop 2.0–5.0 × arm
1.5–2.5 × trail 1.5–2.5): **45 of 45 positive, LONG positive in 45 of 45, SHORT in 44 of 45.**

### 4.2 ★★★ The mirror test — is the chandelier just harvesting the drift?

This is the test that decides whether any of the above means anything. Same 449 rows, same
chandelier, four ways:

| | n | net | win% | $/trade | LONG | SHORT | drift-neutral |
|---|---|---|---|---|---|---|---|
| **FADE the break** | 449 | **+$1,952** | 55.9% | **+$4.35** | +$3.90 | +$4.78 | **+$4.34** |
| FOLLOW the break | 449 | −$2,834 | 51.7% | −$6.31 | −$5.54 | −$7.11 | −$6.32 |
| always LONG at the same stamps | 449 | −$400 | 52.6% | −$0.89 | — | — | — |
| always SHORT at the same stamps | 449 | −$481 | 55.0% | −$1.07 | — | — | — |

**Both constants lose.** Hand the identical exit a fixed direction at the identical moments and it
makes −$400 or −$481. Hand it the fade's direction and it makes +$1,952. The drift-neutral figure
(+$4.34) is within a cent of the pooled figure (+$4.35), so **none of it is gold going up.** The
direction call is worth **$10.66 a trade** across the fade/follow spread.

(One internal check that the arithmetic is honest: fade + follow = −$882 and always-long +
always-short = −$881. They must be identical — the same 898 trades in a different order — and they
are. The whole pot at these stamps is *negative*; the fade extracts +$1,952 from it.)

Placebo on the winning exit — 30 draws, same count, same days, same hours, same side mix, random
minutes: **beaten 0 of 30**, pooled and on each side separately.

> ⚠ **An honest caveat on that placebo.** Random-minute draws average −$16.27 a trade with this exit,
> while a *constant* direction at the break stamps averages only −$0.98. So roughly $15 a trade of the
> placebo's margin comes from **being at a break at all**, not from the direction call — the break
> stamp is simply a good moment to have a position on, either way. That is itself a real finding, but
> it means the mirror and the constant are the *stronger* controls here, and both pass on their own.

---

## 5. ★★★ THE BOOK SPLITS THE TRIGGER INTO TWO DIFFERENT GATES

This is the part I think is genuinely new. Gold's book is far thinner than MNQ's — **the median size
resting within a point of a break level is 1 lot** — so a break either clears what is there or it does
not, and that ought to be visible where in Nasdaq depth it washes out.

**And this is not the refuted L2 attack.** That one asked the book, at an arbitrary moment, *which way
price will go*, and it flipped sign across five disjoint samples. This asks the book nothing about
direction. The break has already picked the side. The book is asked only whether the side it picked
will **hold** — a liquidity question, and liquidity is the one thing a book genuinely knows.

**Definitions, all strictly causal** (last snapshot at or before the entry stamp, never the next):

- `obstacle` — lots resting within 1.0pt **beyond** the level, on the side the break is running into.
- `support` — lots resting within 1.0pt **behind** the level, the side that would catch a failure.
- `ratio` — `obstacle / support`.

Split the 449 breaks three ways and trade each bucket the way the liquidity story says:

| bucket | rule | n | share | trade | net | $/trade | win% |
|---|---|---|---|---|---|---|---|
| **VACUUM** | `obstacle == 0` | 219 | 49% | **FADE** | **+$2,730** | **+$12.47** | 61.2% |
| **WALL** | `obstacle > support` | 63 | 14% | **FOLLOW** | **+$746** | **+$11.84** | 65.1% |
| neither | — | 167 | 37% | fade | +$37 | +$0.22 | 55.1% |
| neither | — | 167 | 37% | follow | −$636 | −$3.81 | 51.5% |

**Read that middle row.** When the book has no opinion, neither cell works — the fade makes 22 cents a
trade and the follow loses. **The book's opinion is the entire edge**, and the sign of each cell was
predicted by the liquidity story before it was priced. That is the 2×2 from one mechanism instead of
four separately-fitted gates, which is what you asked for and is much harder to overfit into.

Filter placebo — keep the same *number* of trades at random, 200 times, because a filter that keeps
49% of trades looks brilliant whenever the 51% it dropped happened to lose:

| cut | keep n | real | random-keep mean | beaten | percentile |
|---|---|---|---|---|---|
| far side EMPTY | 219 | +$2,730 | +$965 | **2/200** | **99.0** |
| far side THIN (<5 lots) | 258 | +$2,711 | +$1,110 | 6/200 | 97.0 |
| the WALL cut (follow population) | 63 | +$746 | −$389 | **0/200** | **100.0** |
| book imbalance against the break | 169 | +$721 | +$645 | 101/200 | 49.5 ← **exactly random** |

And the mechanism is the **ratio**, not the size. Absolute obstacle thresholds are all negative:

| wall rule | n | net | $/tr | LONG $/tr | SHORT $/tr |
|---|---|---|---|---|---|
| obstacle > support (ratio > 1) | 63 | +$746 | **+$11.84** | +$10.56 | +$13.53 |
| obstacle ≥ support + 1 | 116 | +$757 | +$6.52 | +$7.55 | +$5.39 |
| obstacle ≥ support + 2 | 107 | +$524 | +$4.90 | +$5.98 | +$3.80 |
| obstacle ≥ 3 lots | 213 | −$87 | −$0.41 | −$0.22 | −$0.60 |
| obstacle ≥ 5 lots | 191 | −$205 | −$1.08 | −$1.02 | −$1.13 |
| obstacle ≥ 10 lots | 110 | −$653 | −$5.94 | −$8.89 | −$3.38 |

"How much is in the way" tells you nothing. "Is there more in the way than behind" tells you
everything. That is a *relative* liquidity statement and it is a much better mechanism than a
threshold on lots.

### 5.1 ★ Then I tried to break the vacuum story, and it half broke

The obvious objection: is `obstacle == 0` really about the *far* side, or is the book just thin
around that price generally? So I split the vacuum cell four ways on both sides of the book:

| | n | net | $/trade | LONG | SHORT | mirror $/tr |
|---|---|---|---|---|---|---|
| `obstacle==0 AND support>0` — a true one-sided vacuum | 62 | +$82 | **+$1.32** | −$0.72 | +$3.37 | −$15.89 |
| **`obstacle==0 AND support==0` — a hole on BOTH sides** | **157** | **+$2,648** | **+$16.87** | +$19.27 | +$14.84 | −$12.48 |
| `obstacle>0 AND support==0` — empty behind only | 53 | +$247 | +$4.66 | +$22.13 | −$14.91 | +$0.21 |
| `obstacle>0 AND support>0` — both sides populated | 177 | −$1,025 | −$5.79 | −$12.47 | +$1.11 | +$0.56 |

**The pretty story was wrong and I am correcting it rather than keeping it.** It is *not* "the far
side was eaten". A one-sided vacuum makes $1.32 a trade, which is nothing. **Every dollar is in the
double hole** — no resting interest within a point on *either* side of the level. In plain English:
gold pushed through an hour-high into a price area where **nobody was bidding and nobody was
offering**, i.e. a level nobody had an opinion about, and it came straight back.

Two further checks confirm this is real structure and not a dead feed:

- 72% of the hole rows had size in front **60 seconds earlier** (median 5 lots), so the book was alive
  and populated a minute before. A dropped feed reads zero then too.
- Requiring genuine *depletion* (`obst_pre ≥ 3` or `≥ 5`) makes the cell **worse**, not better —
  +$7.31 and +$7.20 a trade against +$16.87. So "the wall was eaten" is explicitly **not** the
  mechanism, and I am not going to claim it is.

> **Forking-paths warning, stated plainly.** I reached the double-hole cell by asking a mechanism
> question and I have shown you all four of its cells, not just the winner. But it *is* a second cut
> on the same data, and I have therefore kept the **simpler `obstacle == 0` version as the primary
> shadow arm** and the double-hole refinement as a second arm alongside it. If the refinement is real,
> the shadow book will show it in a few weeks at no cost. That is the disciplined way to spend this.

---

## 6. CELLS 1 & 2 — REVERSION-LONG and REVERSION-SHORT · `mgc_hole_break_fade`

### 6.1 The exact mechanical spec

```
INSTRUMENT   MGC (COMEX gold), $10.00/point, 1 lot
BARS         1-minute, built from the depth-quote MID (bid1p+ask1p)/2
TRIGGER      hi = high.rolling(60).max().shift(1)          # strictly prior bars
             lo = low.rolling(60).min().shift(1)
             UP break   : close >= hi + 0.10 * ATR(14)
             DOWN break : close <= lo - 0.10 * ATR(14)
BOOK GATE    at the entry stamp, from the last depth snapshot at or before it:
             obstacle = lots resting within 1.0pt BEYOND the level  == 0
             support  = lots resting within 1.0pt BEHIND the level  == 0
             (primary shadow arm relaxes this to obstacle == 0 alone)
DIRECTION    AGAINST the break.  UP break -> SHORT (reversion-short)
                                 DOWN break -> LONG  (reversion-long)
ENTRY        signal_ts + 60s, marketable limit IOC (crosses the spread)
STOP         3.0 x ATR(14) at entry          [plateau: 2.0-4.0 all work]
EXIT         chandelier - arm once peak favourable >= 2.0 x ATR,
             then trail the peak by 2.0 x ATR   [plateau: arm 1.5-2.5, trail 1.5-2.5]
TIME CAP     480 min backstop (it almost never binds - median hold is 16 minutes)
COOLDOWN     45 min per side
COSTS        both legs cross ~0.30pt; fee $1.50/RT
```

### 6.2 The backtest, per cell

| | n | days | net | win% | $/trade | median |
|---|---|---|---|---|---|---|
| **POOLED** | 157 | 22 | **+$2,648** | 64.3% | **+$16.87** | +$12.14 |
| **REVERSION-LONG** (fade a DOWN break) | 72 | 20 | **+$1,387** | 63.9% | **+$19.27** | +$10.57 |
| **REVERSION-SHORT** (fade an UP break) | 85 | 21 | **+$1,261** | 64.7% | **+$14.84** | +$12.14 |
| the MIRROR (follow instead) | 157 | 22 | −$1,959 | 46.5% | −$12.48 | −$1.50 |

Drift-neutral +$17.05 against pooled +$16.87 — the two sides are within $4.43 a trade of each other,
so this is not the sample's up-drift wearing a gate.

### 6.3 ★ Rule 4 — the home regime and the router rule

| regime | side | n | net | win% | $/trade |
|---|---|---|---|---|---|
| CLEAN_TREND | SHORT | 21 | +$1,002 | 71.4% | **+$47.74** |
| CLEAN_TREND | LONG | 18 | +$855 | 66.7% | **+$47.48** |
| DEAD_CHOP | SHORT | 8 | +$333 | 100.0% | +$41.57 |
| DEAD_CHOP | LONG | 10 | +$355 | 80.0% | +$35.52 |
| VIOLENT_WHIPSAW | SHORT | 4 | +$288 | 100.0% | +$72.12 *(too thin to count)* |
| VIOLENT_WHIPSAW | LONG | 2 | +$98 | 100.0% | +$48.75 *(too thin to count)* |
| BUILDING | SHORT | 10 | +$55 | 70.0% | +$5.46 |
| BUILDING | LONG | 9 | −$54 | 66.7% | −$5.97 |
| **NORMAL_CHOP** | **SHORT** | **42** | **−$417** | 50.0% | **−$9.93** |
| **NORMAL_CHOP** | LONG | 33 | +$134 | 54.5% | +$4.05 |

**The router rule writes itself, and it is counter-intuitive in a useful way.** The gate wants the
*extremes* of gold's own volatility distribution — a clean trend or a dead-flat tape — and it must be
benched in the ordinary middle. NORMAL_CHOP is 75 of the 157 trades and is the only bucket that loses.

In the same vocabulary the MNQ router already speaks:

```
ARM   when ATR is in gold's own TOP tercile and ER30 >= gold's p75   (CLEAN_TREND)
      or  ATR is in gold's own BOTTOM tercile                        (DEAD_CHOP)
BENCH when ATR is mid-tercile with mid/low efficiency                (NORMAL_CHOP)
      and in the BUILDING band (mid ATR, high ER) - it is a wash there
```

Cross-check without the book, which shows the two filters are doing *different* work and compose:

| | n | net | $/trade |
|---|---|---|---|
| CLEAN_TREND breaks, no book filter | 84 | +$1,803 | +$21.46 |
| CLEAN_TREND **and** vacuum | 56 | +$2,043 | **+$36.48** |
| CLEAN_TREND **and NOT** vacuum | 28 | −$240 | **−$8.56** |

Inside the same regime, the book-selected rows make $36 a trade and the rest lose $9. The book is not
a proxy for the regime.

**By session** — and here there is nothing to bench:

| session | side | n | net | $/trade |
|---|---|---|---|---|
| US | LONG | 18 | +$491 | +$27.27 |
| LONDON | LONG | 28 | +$603 | +$21.53 |
| ASIA | LONG | 26 | +$294 | +$11.29 |
| ASIA | SHORT | 32 | +$616 | +$19.24 |
| US | SHORT | 31 | +$401 | +$12.94 |
| LONDON | SHORT | 22 | +$244 | +$11.10 |

All six positive. It is a 23-hour gate, not a US-session one — which is worth flagging against your
"I watch intently the US session so I can claim profit": the US session is the *best* single bucket
for the long side, but two thirds of the trades happen while you are asleep.

### 6.4 ★ Rule 3 — the full exit matrix on this entry

| exit family | config | n | net | win% | $/tr | LONG $/tr | SHORT $/tr | median mins |
|---|---|---|---|---|---|---|---|---|
| (a) tight scalp | tp 1.0 / sl 1.0 | 157 | −$493 | 45.2% | −$3.14 | −$2.20 | −$3.93 | 1.3 |
| (a) tight scalp | tp 2.0 / sl 2.0 | 157 | +$437 | 54.1% | +$2.78 | +$3.78 | +$1.94 | 6.7 |
| (b) chandelier | stop 2.0 / arm 2 / trail 2 | 157 | +$2,121 | 54.1% | +$13.51 | +$18.30 | +$9.46 | 9.9 |
| (b) chandelier | stop 2.5 / arm 2 / trail 2 | 157 | +$2,809 | 61.1% | +$17.89 | +$16.76 | +$18.85 | 13.8 |
| **(b) chandelier** | **stop 3.0 / arm 2 / trail 2** | **157** | **+$2,648** | **64.3%** | **+$16.87** | **+$19.27** | **+$14.84** | **16.1** |
| (b) chandelier | stop 4.0 / arm 2.5 / trail 1.5 | 157 | +$3,086 | 66.2% | **+$19.66** | +$18.41 | +$20.71 | 21.2 |
| (b) chandelier | stop 5.0 / arm 3 / trail 3 | 157 | +$1,403 | 61.1% | +$8.94 | +$13.97 | +$4.68 | 39.0 |
| (d) time cap | sl 3.0, flat at 480m | 157 | +$1,698 | 21.7% | +$10.81 | +$21.13 | +$2.08 | 62.3 |

**Which exit family does this entry NEED?** Unambiguously **(b), the wide chandelier.** The tight
scalp is negative at 1R and barely positive at 2R; the time cap only "works" through a one-sided
long-drift artefact (LONG +$21.13 vs SHORT +$2.08) and is discarded on that ground; **the dual slot
is a dead heat** (Lot A −$493 + Lot B +$2,648 over 157 signals is $13.72 a signal on two lots, worse
per lot than running Lot B alone). So: **one lot, wide stop, chandelier. Not the live MNQ dual-slot
shape.**

The mechanism explains the geometry: the trade is catching the *snap-back leg* of a failed break, and
on gold that leg is a grind of ten to twenty minutes, not a two-tick pop. A 1-ATR target clips it
before it has paid for the spread.

**Hold-time boundary** (the 08-14 priority-2 question, measured on this entry): median hold is
**16 minutes** and the time cap does essentially nothing between 60 minutes and 12 hours
(+$4.36 / +$4.42 / +$4.47 / +$4.35 / +$4.35 / +$4.35 per trade at 60/120/240/360/480/720 min on the
449-row set). **The 8h-to-12h boundary does not bind for this gate** because the trail always fires
first. That boundary belongs to the run-catcher, which is a different and now-dead animal.

### 6.5 The full robustness battery

| test | POOLED | REVERSION-LONG | REVERSION-SHORT |
|---|---|---|---|
| n / days | 157 / 22 | 72 / 20 | 85 / 21 |
| net | **+$2,648** | **+$1,387** | **+$1,261** |
| **strip the best 3 trades** | **+$1,626** ✔ | +$551 ✔ | +$387 ✔ |
| **leave out the best DAY** | **+$2,192** ✔ | +$1,098 ✔ | +$772 ✔ |
| **leave out ANY single day** *(measured on the n=219 primary arm)* | green on all 22 days, worst residual **+$2,345** ✔ | — | — |
| days green | 77.3% | 70.0% | 61.9% |
| best / worst day | 07-29 +$457 / 08-05 −$120 | 07-22 +$289 / 07-23 −$127 | 07-29 +$489 / 07-21 −$199 |
| **first half / second half** | +$1,220 / +$1,428 ✔ | +$838 / +$549 ✔ | +$334 / +$927 ✔ |
| **JUL out-of-sample leg** | **+$1,472** (n=102) ✔ | +$1,046 (n=48) ✔ | +$426 (n=54) ✔ |
| **AUG in-sample leg** | +$1,176 (n=55) ✔ | +$341 (n=24) ✔ | +$835 (n=31) ✔ |
| **placebo (30 draws)** | **beaten 0/30** ✔ | **beaten 0/30** ✔ | **beaten 0/30** ✔ |
| cost at $1.50 mid | +$2,796 | +$1,498 | +$1,298 |
| **cost as traded ($7.50)** | **+$2,648** | **+$1,387** | **+$1,261** |
| **cost + 1 extra tick each way** | **+$2,334** ✔ | +$1,243 ✔ | +$1,091 ✔ |

Every test passes on both cells. The one I would draw your eye to is the **JUL leg**: 102 of the 157
trades happen in a block that includes twelve days no gold study on this desk has ever looked at, and
it is the *better* half. That is the closest thing to a real out-of-sample result gold has produced.

**The per-day ledger** (on the `obstacle == 0` primary arm, n=219, so you can see the whole shape):

| week (ISO) | trades | net |
|---|---|---|
| wk 29 | 18 | +$170 |
| wk 30 | 52 | +$150 |
| wk 31 | 54 | +$876 |
| wk 32 | 47 | +$704 |
| wk 33 | 48 | +$830 |
| **total** | **219** | **+$2,730** |

**Five weeks, five green.** 16 green days of 22. Worst day −$116.

**Parameter plateaus.** Nothing here sits on a knife edge:

| parameter | swept | result |
|---|---|---|
| chandelier stop × arm × trail | 45 combinations *(n=449 all-breaks set)* | **45/45 positive** (LONG 45/45, SHORT 44/45) |
| book band width | 0.5 / 1.0 / 1.5 / 2.0 / 3.0 pt *(double-hole rule)* | 5/5 positive; $12.33 → $16.87 → $22.84 → $25.56 → $50.34 per trade as n falls 235 → 23 |
| vacuum definition | obstacle 0 / <2 / <5 / <10 *(primary arm)* | +$12.47 / +$12.23 / +$10.51 / +$5.27 — monotone decay, no cliff |
| cooldown | 0 / 15 / 30 / 45 / 90 / 180 min *(primary arm)* | 6/6 positive, net $1,574–$2,769 across the lot |
| break lookback × margin | 30–120 min × 0–0.25 ATR | 15/15 *negative on the scalp exit* — see the honesty note below |

> **The one plateau that does not look good, and I am not hiding it.** The trigger's own
> lookback/margin grid is 0-for-15 positive — but that grid was run on the **tp1.0/sl1.0 scalp**, i.e.
> the exit that this section has just shown cannot pay for gold's spread. It confirms the cost floor,
> not a defect in the trigger. I have not re-run all 15 cells on the chandelier, and until I do,
> **"the trigger works at other lookbacks" is an untested claim.** That is the first thing I would run
> next week.

### 6.6 The charts

`reports/friday_v7/sections/gf_mgc_charts.svg.html` — three real gold sessions with the actual price
path and **every fill marked**: entry as a triangle (▲ long, ▼ short) on the fill price, a dashed line
to the exit, a dot at the exit and the dollar result beside it. Green fills made money, red lost it.

| session | fades | net | what it shows |
|---|---|---|---|
| **2026-07-29** | 8 | **+$457** | the best day — six breaks that all failed inside twenty minutes |
| 2026-07-22 | 12 | +$172 | a busy day; the wins are small and the losses are smaller |
| 2026-08-13 | 7 | +$120 | a US-session day you would have watched live |

---

## 7. CELLS 3 & 4 — MOMENTUM-LONG and MOMENTUM-SHORT · `mgc_wall_break_go`

### 7.1 The spec

Identical trigger and entry to §6.1. Two changes only:

```
BOOK GATE    obstacle > support     (more resting size IN THE WAY than BEHIND -
                                     a defended level that broke anyway)
DIRECTION    WITH the break.  UP break -> LONG.  DOWN break -> SHORT.
STOP/EXIT    same 3.0 x ATR stop + arm 2 / trail 2 chandelier
```

The story: something crossed a bid or lifted an offer that was actually being defended. That is a
buyer or seller with size and intent, not a drift through an empty level.

### 7.2 The backtest, per cell

| | n | days | net | win% | $/trade | median |
|---|---|---|---|---|---|---|
| POOLED | 63 | 15 | +$746 | 65.1% | +$11.84 | +$6.43 |
| **MOMENTUM-LONG** | 36 | 13 | +$380 | 69.4% | +$10.56 | +$7.71 |
| **MOMENTUM-SHORT** | 27 | 14 | +$365 | 59.3% | +$13.53 | +$6.43 |
| the MIRROR (fade instead) | 63 | 15 | −$815 | 39.7% | −$12.94 | −$30.11 |

Drift-neutral +$12.05 vs pooled +$11.84 — again, not the drift.

### 7.3 Where it is weak, said plainly

| test | POOLED | MOM-LONG | MOM-SHORT |
|---|---|---|---|
| strip the best 3 trades | +$301 ✔ | +$27 ~ | **−$14** ✘ |
| leave out the best day | +$476 ✔ | +$59 ~ | +$195 ✔ |
| days green | 53.3% | 53.8% | 57.1% |
| first / second half | +$41 / +$705 | +$390 / −$9 | −$79 / +$444 |
| **JUL out-of-sample leg** | **−$136** (n=14) ✘ | **−$17** (n=6) ✘ | **−$119** (n=8) ✘ |
| AUG in-sample leg | +$881 (n=49) | +$397 (n=30) | +$484 (n=19) |
| **filter placebo (200 random keeps)** | **beaten 0/200** ✔ | — | — |
| **random-minute placebo (30 draws)** | **beaten 22/30** ✘ | beaten 23/30 ✘ | beaten 12/30 ~ |
| cost + 1 tick each way | +$620 ✔ | +$308 ✔ | +$311 ✔ |

**Two things are wrong with it and I am not going to talk past either.** It **loses on the July
out-of-sample leg**, which is the one leg nothing has ever been fitted on. And it **fails the
random-minute placebo** 22 times in 30, while passing the filter placebo 200 times in 200.

Those two placebos disagree for a reason worth writing down. The *filter* placebo asks "does the wall
cut pick better-than-average breaks to follow?" — emphatically yes, 0 of 200. The *random-minute*
placebo asks "is following a wall break better than simply having a position on at a comparable
moment?" — no. Both are true: the cut is a good selector inside a bad population. Note also that the
random-minute control matches day and hour, and with only 63 trades on 15 days that matched pool is
small and noisy — its own mean swings from −$15 to +$15 a trade depending on which days the candidate
happens to trade. At this n the control is not very informative in either direction.

**Verdict: SHADOW, and only shadow.** Thin n is never a kill and never a promotion. It has a named
mechanism, a passing mirror, a passing filter placebo and a decaying-but-positive threshold plateau
(ratio-based cells +$11.84 / +$6.52 / +$4.90 / +$9.88 / +$10.98 across five formulations). It needs
**n ≥ 150 and a positive July-equivalent leg** before it is anything more than a glimmer.

**Its exit matrix** carries one trap worth naming, because it is the drift signature again:

| exit | n | net | $/tr | LONG $/tr | SHORT $/tr |
|---|---|---|---|---|---|
| scalp tp1.0/sl1.0 | 63 | −$48 | −$0.76 | −$1.56 | +$0.30 |
| scalp tp2.0/sl2.0 | 63 | +$370 | +$5.87 | +$6.48 | +$5.06 |
| chandelier 2.5/2/2 | 63 | +$869 | +$13.79 | +$12.26 | +$15.83 |
| chandelier 3/2/2 | 63 | +$746 | +$11.84 | +$10.56 | +$13.53 |
| ~~time cap sl1.5, 240m~~ | 63 | ~~+$2,471~~ | ~~+$39.23~~ | **+$80.70** | **−$16.06** |
| ~~time cap sl3.0, 480m~~ | 63 | ~~+$2,380~~ | ~~+$37.78~~ | **+$102.02** | **−$47.89** |

The two time-cap rows are the biggest numbers in this entire section and **both are discarded**: they
make $80–$102 a trade on the long side and lose $16–$48 on the short side, on a tape that rose 13 days
of 22. That is not a gate, that is a long position with extra steps. Same exit family as this entry
needs as the reversion pair: **wide chandelier, one lot.**

---

## 8. EVERYTHING THAT DIED, BY NAME

The honest failures are the deliverable. Every attempt this session, with its stats and the specific
test that killed it.

| # | candidate | shape | n | result | cause of death | disposition |
|---|---|---|---|---|---|---|
| 1 | `mgc_break_follow` | MOM ×2 | 449 | −$2,834 (−$6.31/tr) chandelier; −$2,597 scalp | **The mirror.** Its own fade is +$1,952 on the identical rows. Negative in all 15 lookback×margin cells. | **REFUTED** |
| 2 | `mgc_extension_follow` | MOM ×2 | 1,128–1,301 | −$3.39 to −$5.49/tr across 8 barrier pairs | Blanket negative; negative in 9 of 10 regime×side cells at tp3.0/sl1.5. Green only on the fake $1.50 cost model. | **REFUTED** |
| 3 | `mgc_extension_fade` | REV ×2 | 1,045–1,301 | −$4.31 to −$6.10/tr across 15 barrier pairs | 15/15 barrier cells and 10/10 regime×side cells negative. The cost floor with no compensating signal. | **REFUTED** |
| 4 | `mgc_session_drift_rider` | MOM ×2 | 18 days | −$842 (−$46.80/tr); MOM-SHORT −$78.74/tr at 10% win | **Loses to the best constant** — `always_LONG` made +$1,296 on the identical exit. **0 of 16** threshold-plateau cells positive. Placebo beaten 20/30. | **PARKED** — revive only if a *causal* day filter can be built that beats discarding the same number of firings at random |
| 5 | `mgc_coil_bounce` | REV ×2 | 306 | −$1,701 (−$5.56/tr), days-green **9.1%** | Placebo beaten 13/20 (35th pct). Negative on **both** cost conventions (−$760 at $1.50) and **both** halves. The 08-14 +$470/n=154 does **not** replicate on the 22-day quote tape. | **PARKED** — revive only if it can be shown green on the quote-mid tape; the prior result depended on the L1 construction and the $1.50 cost |
| 6 | `mgc_straddle` / breakout-either-way | VOL | — | not traded | **The premise is false.** The tightest compression quintile expands **less** than average (−$6.23); rank corr(20m range, next 60m size) = +0.036. | **REFUTED** |
| 7 | `mgc_book_imbalance` cut | filter | 169 | +$721 | **Filter placebo: beaten 101/200, the 49.5th percentile.** Exactly random. | **REFUTED** as a filter |
| 8 | `mgc_obstacle_size` cut (absolute lots) | filter | 110–213 | −$87 / −$205 / −$653 at ≥3 / ≥5 / ≥10 lots | Monotonically worse with size. The signal is the **ratio**, not the size. | **REFUTED** as a filter |
| 9 | `mgc_depletion` cut ("the wall was eaten") | filter | 119–128 | +$7.20–$7.31/tr | Makes the vacuum cell **worse** than not filtering (+$16.87 → +$7.31). The mechanism is a liquidity *hole*, not depletion. | **REFUTED** as a filter |
| 10 | dual-slot (Lot A scalp + Lot B chandelier) | exit | 157–449 | +$0.20 to +$13.72 per signal on **two** lots | Lot A is negative on gold and cancels Lot B. Worse per lot than Lot B alone. | **REFUTED** as an exit shape for gold |
| 11 | time-cap exits on both survivors | exit | 63–449 | headline +$39/tr | **The drift signature** — LONG +$80.70 / SHORT −$16.06. Discarded on the side-split, not on the total. | **REFUTED** as an exit shape |
| 12 | one-sided vacuum (`obstacle==0, support>0`) | REV ×2 | 62 | +$82 (+$1.32/tr) | Below the cost floor; the long side is negative. Superseded by the double-hole cell. | **PARKED** — revive at n>150 if the double hole degrades |

Plus the six attacks already closed on 2026-08-05 and re-confirmed rather than re-derived: momentum/
direction, arm-then-confirm, router-filtered, L2 book *direction*, fader-on-extension + clock, and
thrust-continuation. I did not spend the night re-digging those.

**The London-open break FADE** (`mgc_session_anchor.py`, n=16, +$502, beaten 0/7 shifted anchors) I
have deliberately **not** re-derived — 16 trades on a clock anchor is below the threshold at which
anything I could say would be informative, and its median trade already loses. It stays **PARKED** on
last week's terms: revive at n > 40.

---

## 9. WHAT COULD STILL BE WRONG WITH THE SURVIVOR

The adversarial list, because a verdict with no visible doubt is worth less than one with it.

1. **Twenty-two days is twenty-two days.** Five ISO weeks, one instrument, one macro regime. Gold rose
   in 13 of 22 sessions. Everything here is drift-controlled, but a *regime* the sample does not
   contain cannot be controlled for.
2. **The regime labels have a mild in-sample peek.** The ATR and ER cut points that define
   CLEAN_TREND / NORMAL_CHOP are whole-sample percentiles. **The signal is fully causal; the router
   rule's calibration is not.** In live use those percentiles must be computed on a trailing window,
   and that will move the arm/bench boundary somewhat.
3. **The double-hole refinement is a second cut on the same data.** Handled by shadowing the simpler
   arm as primary — but it is the most likely thing here to shrink.
4. **157 trades is not 500.** The short cell is 85 trades; strip its best three and it is +$387, which
   is fine but not a fortress.
5. **The 45-minute cooldown is doing real work.** At zero cooldown the same rule makes $2.67 a trade
   instead of $12.47. That is expected (overlapping trades are not independent) but it means live
   throughput will be far lower than 219 signals a month suggests, and the per-trade figure depends on
   *not* re-entering.
6. **The trigger plateau across lookbacks is untested on the winning exit.** Named in §6.5 and it is
   the first thing to run next week.
7. **Depth is a 250ms SAMPLE, not an event stream.** `capture.db.book` is 41ms and event-driven but is
   MNQ-only. Gold's book cannot see a fleeting quote that Nasdaq's can — so the live gate will read a
   slightly *different* book than this backtest did, in the direction of missing brief refills.
8. **The fill model is optimistic in one specific way.** I charge a crossed spread on both legs, but I
   assume the fill happens at the touch. In a genuine liquidity hole — which is precisely the state
   this gate selects for — the touch may be further away than the last quote said. That is the single
   most likely way this degrades in live shadow, and it is exactly why it goes to shadow first.

---

## 10. SHADOW-READY BLOCKS

### 10.1 ⚠ The blocker, and it is architectural, not a threshold

I checked whether `ShadowSim` can express these, and **it cannot — for four separate reasons**, three
of which would fail *silently* and produce a confident wrong number:

| # | blocker | evidence | consequence |
|---|---|---|---|
| 1 | **No gate kind for a level break.** `ShadowSim._entry` dispatches on `thrust` / `reversal_grab` / `capitulation` / `grind` / `clock_rider` and nothing else. | `src/gazbot7/shadow.py:229-247` | a new `level_break` branch is required |
| 2 | **`ShadowSim` never sees an order book.** `on_bars(bars, tape_net, window_price_delta, in_rth, now_ms, cap)` carries no depth. `FootprintShadow` runs its own tick+book loop precisely because of this — and it reads `capture.db`, which has **no MGC depth at all** (IBKR allows three depth subscriptions; gold's L2 goes to `depth.db`). | `src/gazbot7/shadow.py:150-156` | the book gate cannot be expressed; needs a `depth.db` feed |
| 3 | **The shadow service is single-symbol.** `if body.get("symbol") != cfg.symbol: continue`. A `symbol="MGC"` variant added to the MNQ slate would **never see a gold bar** and would silently record nothing. | `src/gazbot7/shadow.py:768` | MGC needs its **own** shadow service instance |
| 4 | **★ `value_per_point` is per-INSTANCE, not per-variant** — and `reprice_pending(..., value_per_point=...)` takes **one** value for every trade regardless of symbol. | `src/gazbot7/shadow.py:140,144`, `src/gazbot7/repricer.py:95,131` | an MGC trade inside the MNQ shadow service is priced at **$2/pt instead of $10/pt — a 5× understatement, with no error** |

Blocker 4 is the dangerous one. It is the same family as the 08-04 multi-symbol bar bug that fed every
sim corrupt ATR for hours. **Do not add an MGC variant to the existing slate.** Gold needs
`cfg.symbol="MGC"`, `cfg.value_per_point=10.0` and its own service.

### 10.2 The literal lines, for when the plumbing exists

```python
# ── MGC GOLD — the level-break 2x2, one trigger split by the book ────────────────────────────
# ⚠ REQUIRES: a second ShadowSim instance with cfg.symbol="MGC", cfg.value_per_point=10.0,
#             and a new gate="level_break" branch fed from depth.db.depth_snap.
#             Adding these to the MNQ slate prices gold at $2/pt. See §10.1.

# CELLS 1+2 — REVERSION. Primary arm: the simpler book rule (obstacle == 0).
ShadowVariant("mgc_holebreak_fade_long", "level_break", symbol="MGC", side="LONG",
              params={"look_min": 60, "margin_atr": 0.10, "cooldown_min": 45,
                      "fade": True, "book_band_pt": 1.0, "obstacle_max": 0},
              stop_atr_mult=3.0, chandelier=True, chand_lock=True,
              chand_start_k=2.0, lock_r=99.0, lock_k=2.0, time_cap_s=480 * 60),
ShadowVariant("mgc_holebreak_fade_short", "level_break", symbol="MGC", side="SHORT",
              params={"look_min": 60, "margin_atr": 0.10, "cooldown_min": 45,
                      "fade": True, "book_band_pt": 1.0, "obstacle_max": 0},
              stop_atr_mult=3.0, chandelier=True, chand_lock=True,
              chand_start_k=2.0, lock_r=99.0, lock_k=2.0, time_cap_s=480 * 60),

# Second arm: the double-hole refinement, so the extra cut can be ATTRIBUTED rather than assumed.
ShadowVariant("mgc_holebreak_fade_long_dbl", "level_break", symbol="MGC", side="LONG",
              params={"look_min": 60, "margin_atr": 0.10, "cooldown_min": 45,
                      "fade": True, "book_band_pt": 1.0, "obstacle_max": 0, "support_max": 0},
              stop_atr_mult=3.0, chandelier=True, chand_lock=True,
              chand_start_k=2.0, lock_r=99.0, lock_k=2.0, time_cap_s=480 * 60),
ShadowVariant("mgc_holebreak_fade_short_dbl", "level_break", symbol="MGC", side="SHORT",
              params={"look_min": 60, "margin_atr": 0.10, "cooldown_min": 45,
                      "fade": True, "book_band_pt": 1.0, "obstacle_max": 0, "support_max": 0},
              stop_atr_mult=3.0, chandelier=True, chand_lock=True,
              chand_start_k=2.0, lock_r=99.0, lock_k=2.0, time_cap_s=480 * 60),

# CELLS 3+4 — MOMENTUM. Thin (n=63, negative on the July leg) — a glimmer, on probation.
ShadowVariant("mgc_wallbreak_go_long", "level_break", symbol="MGC", side="LONG",
              params={"look_min": 60, "margin_atr": 0.10, "cooldown_min": 45,
                      "fade": False, "book_band_pt": 1.0, "require_obstacle_gt_support": True},
              stop_atr_mult=3.0, chandelier=True, chand_lock=True,
              chand_start_k=2.0, lock_r=99.0, lock_k=2.0, time_cap_s=480 * 60),
ShadowVariant("mgc_wallbreak_go_short", "level_break", symbol="MGC", side="SHORT",
              params={"look_min": 60, "margin_atr": 0.10, "cooldown_min": 45,
                      "fade": False, "book_band_pt": 1.0, "require_obstacle_gt_support": True},
              stop_atr_mult=3.0, chandelier=True, chand_lock=True,
              chand_start_k=2.0, lock_r=99.0, lock_k=2.0, time_cap_s=480 * 60),

# THE CONTROL — the same trigger with NO book gate. Without it the book cut cannot be attributed,
# and attributing a filter to itself is how the router-filtered gold attack fooled us in August.
ShadowVariant("mgc_break_fade_nobook", "level_break", symbol="MGC",
              params={"look_min": 60, "margin_atr": 0.10, "cooldown_min": 45, "fade": True},
              stop_atr_mult=3.0, chandelier=True, chand_lock=True,
              chand_start_k=2.0, lock_r=99.0, lock_k=2.0, time_cap_s=480 * 60),
```

**One fidelity caveat on the exit.** `exit_chandelier_lock(start_k=lock_k=2.0, lock_r=99)` gives a
*constant* 2.0-ATR give-back that only ever fires in profit, which is the closest the existing
deciders get. It is **not** identical to the backtested exit: mine requires the peak to reach **2.0
ATR before the trail arms at all**, whereas `exit_chandelier_lock` effectively arms as soon as the
peak clears the give-back. The difference is small on this entry (median hold 16 minutes, median peak
well past 2 ATR) but it is a difference, and if you want an exact mirror the `ShadowVariant` needs one
new field — `chand_arm_k` — rather than a new decider.

**The router rule to attach**, in the router's own vocabulary:

```
gate:        mgc_holebreak_fade_{long,short}
ARM   when   regime == CLEAN_TREND   (gold ATR >= own p67 AND ER30 >= own p75)
        or   regime == DEAD_CHOP     (gold ATR <= own p33)
BENCH when   regime == NORMAL_CHOP   (-$9.93/tr on the short side, 75 of 157 trades)
        or   regime == BUILDING      (a wash: +$5.46 short / -$5.97 long)
session:     no bench - all six session x side buckets are positive
⚠ the percentile cuts must be computed on a TRAILING window in live use, not on the whole sample
  as they are here; that will move the boundary.
```

---

## 11. ★ PER-CELL VERDICT TABLE

| cell | gate | trigger | n | net (true, $7.50/RT) | $/trade | win% | home regime | strip-3 | leave-out-best-day | OOS (JUL) | placebo | **verdict** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **MOMENTUM-LONG** | `mgc_wall_break_go` | 60m level break UP with `obstacle > support` → **buy** | 36 | +$380 | +$10.56 | 69.4% | DEAD_CHOP / US session | +$27 | +$59 | **−$17 ✘** | filter 0/200 ✔, random 23/30 ✘ | **SHADOW** (thin, on probation) |
| **MOMENTUM-SHORT** | `mgc_wall_break_go` | 60m level break DOWN with `obstacle > support` → **sell** | 27 | +$365 | +$13.53 | 59.3% | NORMAL_CHOP / ASIA | **−$14 ✘** | +$195 | **−$119 ✘** | filter 0/200 ✔, random 12/30 ~ | **SHADOW** (thin, on probation) |
| **REVERSION-LONG** | `mgc_hole_break_fade` | 60m level break DOWN into a **liquidity hole** → **buy** | 72 | **+$1,387** | **+$19.27** | 63.9% | **CLEAN_TREND** (+$47.48/tr) | +$551 ✔ | +$1,098 ✔ | **+$1,046 ✔** | **0/30 ✔** | **SHADOW — the lead candidate** |
| **REVERSION-SHORT** | `mgc_hole_break_fade` | 60m level break UP into a **liquidity hole** → **sell** | 85 | **+$1,261** | **+$14.84** | 64.7% | **CLEAN_TREND** (+$47.74/tr) | +$387 ✔ | +$772 ✔ | **+$426 ✔** | **0/30 ✔** | **SHADOW — the lead candidate** |

**Exit family each cell NEEDS** (Rule 3, stated plainly): **all four want the wide chandelier and a
single lot.** Not the tight scalp (negative on both survivors at 1R). Not the dual slot (Lot A cancels
Lot B). Not a time cap (its headline numbers are a long-drift artefact). This is the opposite of the
live MNQ slot configuration and it is the single most actionable structural finding in the section.

---

## 12. DISPOSITION TABLE

| lead | verdict | required note |
|---|---|---|
| `mgc_hole_break_fade` LONG + SHORT | **SHADOW** | The lead gold candidate. 22 days, 5/5 weeks green, both halves and both capture blocks green, placebo 0/30, survives +1 tick each way. Two arms (simple `obstacle==0` primary, double-hole refinement second) plus a no-book control. |
| `mgc_wall_break_go` LONG + SHORT | **SHADOW** | Glimmer only: n=63 on 15 days, **negative on the July out-of-sample leg**, fails the random-minute placebo. Promote no further until n ≥ 150 **and** a positive held-out leg. |
| `mgc_session_drift_rider` | **PARKED** | Revive if a **causal** day/condition filter can be built that beats discarding the same number of firings at random. As built it loses to `always_LONG` by $2,138 on the identical exit and has 0/16 positive plateau cells. |
| `mgc_coil_bounce` | **PARKED** | Revive only if it can be shown green on the 22-day quote-mid tape at the true $7.50 cost. The 08-14 +$470 depended on the L1 construction and the $1.50 model; it is −$1,701 here with 9.1% green days and a failed placebo. |
| London-open break FADE (`mgc_session_anchor`) | **PARKED** (unchanged) | Not re-derived — n=16 is below the level at which any statement is informative. Revive at n > 40. |
| One-sided vacuum (`obstacle==0, support>0`) | **PARKED** | Revive at n > 150 if the double-hole arm degrades in shadow. Currently +$1.32/tr, below the cost floor. |
| `mgc_break_follow` / `mgc_extension_follow` / `mgc_extension_fade` | **REFUTED** | Killed by the mirror and by 15/15 and 10/10 negative cells. Momentum-by-continuation on gold is now closed from three independent directions. |
| Breakout-either-way / straddle (`mgc_straddle`) | **REFUTED** | The premise is false on gold: the tightest compression quintile expands **less** than average. No reformulation of a straddle survives a negative expansion gradient. |
| Book **imbalance** as a filter | **REFUTED** | Filter placebo: beaten 101/200. Indistinguishable from random. |
| Absolute **obstacle size** as a filter | **REFUTED** | Monotonically worse with size (−$0.41 → −$1.08 → −$5.94/tr at ≥3/≥5/≥10 lots). The ratio is the signal. |
| **Depletion** ("the wall was eaten") as a filter | **REFUTED** | Requiring prior size halves the cell (+$16.87 → +$7.31/tr). The mechanism is a hole, not depletion. |
| Dual-slot exit on gold | **REFUTED** | Lot A is negative on gold and cancels Lot B; worse per lot than Lot B alone. |
| Time-cap exits on gold | **REFUTED** | Green only through a one-sided long-drift artefact (LONG +$80.70 / SHORT −$16.06). |
| **MGC shadow plumbing** | **BUILD REQUIRED** | Four blockers in §10.1, one of which (`value_per_point` is per-instance and the repricer takes one value) would price gold at **$2/pt with no error**. This is the gating item for everything above. |

---

## 13. THE ONE STONE STILL UNTURNED

**Cross-asset.** Every source this desk has pointed at gold is gold's own price and gold's own book.
The one genuinely different input we have never used is **the relationship between MGC and MNQ on the
same clock** — we capture both, L1 and L2, on the same tape, and gold is a macro instrument whose
moves are frequently the *other side* of a risk move in equities. A break in gold that coincides with
a matching break in the Nasdaq is a different event from one that does not, and nothing in this
section can tell them apart. That is next week's first question.

**And the concrete next three runs, in order:**

1. Re-run the trigger's lookback × margin plateau **on the chandelier exit** — the 0-for-15 grid in
   §6.5 is the one loose thread in the survivor's evidence.
2. Build the MGC shadow service (§10.1) — four blockers, all mechanical, none of them research.
3. Re-price the fill assumption: measure what actually trades at the touch in the 60 seconds after a
   hole-break, because §9.8 is the most likely way this shrinks in live shadow.

---

### Files

| artefact | path |
|---|---|
| the honest gold tape (5s-only, spread-honest, 22-day quote tape) | `scripts/gf_mgc_tape.py` |
| conditional-bias map + the straddle test | `scripts/gf_mgc_map.py` |
| first-touch barrier geometry / the cost floor | `scripts/gf_mgc_touch.py` |
| the 2×2 bench: racer, battery, placebo, exit matrix | `scripts/gf_mgc_cells.py` |
| the mirror / constant / drift-neutral adversarial round | `scripts/gf_mgc_verify.py` |
| the L2 book cut and the filter placebo | `scripts/gf_mgc_l2.py` |
| the two survivors, taken apart | `scripts/gf_mgc_final.py` |
| the five ways I tried to break it, + the charts | `scripts/gf_mgc_skeptic.py` |
| results | `reports/friday_v7/sections/gf_mgc_{cells,verify,l2,final,skeptic}.json` |
| trade-level dumps | `reports/friday_v7/sections/gf_mgc_trades_{vacuum_fade,wall_go}.json` |
| **the run charts, fills marked** | `reports/friday_v7/sections/gf_mgc_charts.svg.html` |
