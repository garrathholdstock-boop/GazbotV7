# GREENFIELD — THE CHOP-DAY TURN SCALP (L2-LED)

## What you asked for, and what came back

You asked for something specific this week, Garrath, and you were right to ask for it in the
shape you did. The trend days carry the profit. The chop days donate. "Untradeable" is a
statement about the gates we happen to own, not about the tape — so build a purpose-built
chop-turn scalper, catch the oscillation turns, bank tiny, and **lead with the order book**,
because a price-only turn-fade is a known coin-flip and because our best gate in the roster,
`exhaustion_short`, was built out of L2 footprints in the first place.

I built it. Nine named candidates, 290,700 five-second decision points across eighteen trading
days, 25.2 million trade ticks, 5.06 million ten-deep book snapshots and 33.9 million level-1
book updates at 41 milliseconds. Everything raced tick by tick on the real tape at $1.50 the
round trip.

**The answer is no, and it is a clean no with two named causes of death.** The best candidate
that reached the robustness battery, CT-9 STALL+PUSH, made **+$399.49 on 148 trades in-sample**
and then lost **−$167.44 on 82 trades out-of-sample — which is to say, on THIS WEEK, the exact
five chop days it was built to rescue.** Strip its three best trades and the whole eighteen-day
window drops to **+$27.77, twelve cents a trade.** It is killed by the **out-of-sample leg** and
by **strip-the-best-3**, and I will show you both.

**Three things came out of this that are worth more than the scalper would have been:**

**1. The book does not separate the turns. I looked at it six ways and it is a null.** The
resting-size ratio, the depletion rate, the refill count, the aggressor delta, the 250ms
ten-deep sample and the 41ms event stream all land inside noise. The one term from the
`exhaustion_short` family that DOES carry something is not the wall at all — it is **"price
refused to follow"**, the stall. That is a real finding about our own best gate's lineage:
what travels is the no-progress term, not the wall.

**2. Your VWAP-flat filter is inert.** I swept it three ways across 108 cells and it moves
nothing — 0.5 ATR, 1.0 ATR, and switched off entirely produce the same median dollar-per-trade
to within a cent. It is not wrong, it is just not doing any work, and the 30-minute efficiency
reading already does the job you wanted it to do.

**3. ★ The premise needs correcting, and this is the finding I would act on.** The chop DAYS
bleed, but the money is not lost in the chop. Attributing every live trade to the 30-minute
block it opened in: this week the desk made **+$146.50 in dead-chop blocks and lost −$46.50 in
normal-chop blocks — a net +$100 across 44 trades in the quiet tape.** It lost **−$842.50 on 54
trades inside the violent-whipsaw blocks** that sit *inside* those same chop days. Over the full
eighteen days it is **−$5,414 on 348 whipsaw-block trades at −$15.56 each**, against −$246 across
206 trades in all the genuinely quiet blocks combined. **We are not donating in the chop. We are
donating in the high-ATR thrash inside chop days.** A scalper aimed at the quiet tape is aimed at
the wrong target — the money is a bench, not a new gate.

---

## 1. The prize, re-measured before anything was built

Your brief prices the win at "+$200-300 on a chop day instead of sitting out". Before inventing
anything I went and checked what the desk actually does on those days, because if the donation
is not where we think it is then the scalper is solving the wrong problem.

Every live MNQ tournament trade from 2026-07-16 to 2026-08-14 (`data_quality IS NULL`, so the
quarantined phantom rows are out), attributed to the 30-minute regime block it OPENED in.
`day_rider` is excluded throughout — it has no ledger of its own and it is not part of the
tournament (that gap is Part 1's business, not mine).

**The whole window — 705 trades, −$4,230.50:**

| block regime | n | net | win% | $/trade |
|---|---:|---:|---:|---:|
| BUILDING | 121 | **+$1,836.50** | 48.8% | +$15.18 |
| NORMAL-CHOP | 165 | −$46.00 | 46.1% | −$0.28 |
| CLEAN-TREND | 24 | −$181.00 | 33.3% | −$7.54 |
| DEAD-CHOP | 41 | −$199.50 | 36.6% | −$4.87 |
| no block (gaps) | 6 | −$226.50 | 33.3% | −$37.75 |
| **VIOLENT-WHIPSAW** | **348** | **−$5,414.00** | **33.9%** | **−$15.56** |

**This week — 108 trades, −$325.00:**

| block regime | n | net | win% | $/trade |
|---|---:|---:|---:|---:|
| BUILDING | 10 | +$417.50 | 90.0% | +$41.75 |
| DEAD-CHOP | 20 | +$146.50 | 50.0% | +$7.32 |
| NORMAL-CHOP | 24 | −$46.50 | 37.5% | −$1.94 |
| **VIOLENT-WHIPSAW** | **54** | **−$842.50** | **33.3%** | **−$15.60** |

Read those two tables next to each other. **Half of this week's tournament trades opened inside
violent-whipsaw blocks, and that half is the entire loss.** The quiet tape — the tape a chop-turn
scalper would live in — was mildly *profitable* for the existing gates this week. The problem is
not that we sit out the chop; it is that we do not sit out the thrash.

So the honest prize for a chop-turn scalper is not $200-300 a day. The desk is already roughly
flat-to-positive in the blocks it would trade. **The prize for a whipsaw bench, by contrast, is
about $5,400 over eighteen days.** I am not going to pretend the scalper's ceiling is the
headline number when the data says otherwise.

---

## 2. Method, data and the cost model — stated before a single result

| item | value |
|---|---|
| Symbol | **MNQ only**, $2.00 per point, 0.25 pt tick |
| **Fee** | **$1.50 per ROUND TRIP** — not $5, not $2, not per side |
| Entry | market at the 5s bar's **CLOSE**, filled at the next real print, crossed **one tick adverse** ($0.50) |
| Stop | stop-market, filled **one tick BEYOND** the trigger ($0.50) |
| Target | limit — only filled if a print goes **one tick THROUGH** it |
| Exit resolution | **first-touch race on the real tick path**; stop and target race each other tick by tick |
| Total friction | ≈ **$2.25 per round trip** at the observed ~30% stop rate |
| Days | **18** with both trade ticks AND ten-deep L2: 07-16, 07-17, 07-24, 07-27→07-31, 08-03→08-07, 08-10→08-14 |
| In-sample | 13 days, 2026-07-16 → 2026-08-07 |
| **Out-of-sample** | **5 days, 2026-08-10 → 2026-08-14 — THIS WEEK** |
| Bars | 5s bars folded to 1m with `bar_ts - bar_ts % 60`; **never** `(bar_ts/60)*60` |
| Tape source | the **Parquet lake** (`gazbot7.lake.connect`), never a bare `capture.db` ATTACH |
| L2 (breadth) | `depth.db.depth_snap`, **ten deep**, 250ms sample, 5,060,853 snapshots |
| L2 (fidelity) | `capture.db.book`, **41ms event-driven**, 4 deep, 33,930,448 level-1 updates, 11 days |
| Decision clock | 5 seconds; 290,700 decision rows |
| Ticks | 25,197,096 MNQ trade prints |

Two deliberate choices worth flagging. **First, the out-of-sample leg is this week and only this
week.** Fitting on this week and testing on July would have been the comfortable way round and
would have told us nothing — the whole question is whether a thing built on past chop survives
onto the chop days you actually care about. **Second, no MFE is reported anywhere in this
section as though it were a win.** Every exit is a race that the stop can win.

The regime taxonomy is keyed on ATR level plus efficiency plus range-break on 30-minute blocks
of 1-minute bars — never on the clock — with time-of-day carried alongside as a separate split
(US session 13:30–20:00 UTC vs overnight). 991 blocks over the window.

| regime | blocks | mean 1m-ATR20 | mean ER30 | rule |
|---|---:|---:|---:|---|
| DEAD-CHOP | 251 | 7.66 pt | 0.141 | ER < 0.22 and ATR below the 33rd pctile (10.17 pt) |
| NORMAL-CHOP | 374 | 12.46 pt | 0.185 | ER < 0.30, otherwise |
| BUILDING | 101 | 17.19 pt | 0.358 | ER ≥ 0.30, no confirmed break |
| VIOLENT-WHIPSAW | 248 | 22.05 pt | 0.153 | ATR above the 67th pctile (15.09 pt) and ER < 0.25 |
| CLEAN-TREND | 17 | 19.89 pt | 0.505 | ER ≥ 0.45 with a 2-hour range break |

### This week was a chop week end to end, and it got quieter every day

| day | 1m-ATR20 | ER30 | day range | dead-chop | normal-chop | whipsaw | day type |
|---|---:|---:|---:|---:|---:|---:|---|
| 2026-08-10 | 10.25 | 0.179 | 307.25 pt | 50% | 35% | 11% | **CHOP** |
| 2026-08-11 | 9.71 | 0.183 | 353.50 pt | 48% | 37% | 7% | **CHOP** |
| 2026-08-12 | 8.97 | 0.163 | 376.50 pt | 61% | 17% | 13% | **CHOP** |
| 2026-08-13 | 8.53 | 0.186 | 476.75 pt | 61% | 24% | 2% | **CHOP** |
| 2026-08-14 | 8.00 | 0.175 | 262.25 pt | 69% | 17% | 7% | **CHOP** |

All five. Not one clean-trend block in the entire week, and the average true range fell from
10.25 points on Monday to 8.00 on Friday — the quietest tape in the whole eighteen-day sample.
That matters twice over: it is exactly the tape you wanted the scalper for, **and** it is the
hardest possible tape to clear $2.25 of friction on, because a 0.75-ATR target on Friday is six
points where in late July it was seventeen.

---

## 3. ★ Two instrument failures — in MY harness, found by me, and the first one was the entire edge

This belongs near the front because you have been burned by exactly this three times already
this month, and because if I had not gone looking I would be handing you a $3,251 gate that does
not exist.

**Failure 1 — the 5-second entry leak.** The first cut raced the tick path from the 5s bar's
OPEN while using that bar's CLOSE as the reference price. Five seconds of hindsight. Worth
**1.2 points of measured revert probability** (54.2% → 53.0%) all on its own.

**Failure 2 — the 55-second ATR/efficiency leak, and this one was fatal.** The feature builder
joined each 5-second row to the 1-minute bar it *sits inside*, so the ATR and the efficiency
reading at 09:14:05 were computed from a minute that had not finished yet — up to 55 seconds of
future. And efficiency was the strongest separator in the whole study, so the leak went straight
into the thing everything else was conditioned on.

Here is what that one join cost, on identical code, identical days, identical costs:

| measurement | with the leak | leak fixed | |
|---|---:|---:|---|
| P(revert) at range extremes, chop blocks | 54.2% (z=+6.16) | **50.6% (z=+0.84)** | the edge |
| P(revert), dead-chop blocks (ER<0.09) | 60.2% (z=+6.63) | **51.6% (z=+1.24)** | the "great segment" |
| First-pass configs positive (6 candidates × 4 exits) | **23 of 24** | **5 of 24** | |
| Best first-pass config | **+$3,250.83** | −$823.01 | CT-4 at 1.5/0.75 |
| CT-1 FLATLINE (control), in-sample, 1.5/0.75 | +$1,843.19 | −$1,494.86 | |

**Five of the six candidates were profitable at every one of the four exit settings before the
fix, and the sixth was profitable at three of four. That is what tipped me off** — six candidates
that share a mechanism are not six independent edges, and twenty-three green cells out of
twenty-four is not a discovery, it is a bug. The tell is always the same: when the null refuses
to appear anywhere, the harness is lying.

I am reporting the leaked figures alongside the honest ones deliberately, because the leaked
version is precisely the report I would have written if I had not checked, and it would have
read beautifully.

---

## 4. Does the book separate? The model-free race, before any gate exists

No parameters, no fitting, no P&L. At every 5-second point where price sits in the top or bottom
decile of the trailing 30-minute range, and that range is worth at least 1.5 ATR, put two
symmetric barriers at ±0.75 ATR and let the real tick path decide which is touched first, out to
ten minutes. One event per side per 60 seconds so a single touch does not vote twelve times.
**8,386 decided races.** A fade with no information is 50%.

| segment | n | P(revert first) | z |
|---|---:|---:|---:|
| All extremes | 8,386 | 51.2% | +2.16 |
| **Chop blocks (ER30 < 0.30)** | **5,607** | **50.6%** | **+0.84** |
| Trend blocks (ER30 ≥ 0.30) | 2,779 | 52.4% | +2.56 |
| Chop + US session | 1,642 | 52.5% | +2.02 |
| Chop + overnight | 3,965 | 49.8% | −0.30 |
| At a HIGH (fade = short) | 4,397 | 50.7% | +0.89 |
| At a LOW (fade = long) | 3,989 | 51.7% | +2.20 |

**Fading a range extreme in chop is a 50.6% proposition.** With $2.25 of friction against a
±0.75-ATR payoff — about $12 a side on this week's 8-point ATR — you need roughly 55% to break
even. We have 50.6%, and the confidence interval comfortably contains a coin.

Note the small oddity: the *trend* blocks fade marginally better than the chop blocks. That is
not a trend-fade edge, it is the arithmetic of a bigger ATR making the barriers wider relative
to the noise. It does not survive costs either.

### The book, marginally — six measures, top and bottom decile, chop blocks only

| measure | tail | n | P(revert) | z |
|---|---|---:|---:|---:|
| far-side 5-deep / near-side 5-deep | bottom 10% | 564 | 49.3% | −0.34 |
| far-side 5-deep / near-side 5-deep | top 10% | 562 | 50.0% | +0.00 |
| level-1 far / near | bottom 10% | 567 | 48.1% | −0.88 |
| level-1 far / near | top 10% | 832 | 48.7% | −0.76 |
| far-side 30s size change (depletion) | bottom 10% | 561 | 50.8% | +0.38 |
| far-side 30s size change (depletion) | top 10% | 562 | 52.0% | +0.93 |
| near-side 30s size change | bottom 10% | 561 | 49.4% | −0.30 |
| absorption, \|60s delta\| / (\|60s move\|+1) | top 10% | 563 | 51.2% | +0.55 |
| aggressor delta into the extreme | top 10% | 561 | 53.8% | +1.82 |
| far-side ABSOLUTE 5-deep size | top 10% | 565 | **56.3%** | **+2.99** |
| 60s price progress into the extreme | top 10% | 571 | 48.5% | −0.71 |

**Nothing. The wall ratio is 49.3% thin and 50.0% thick — the measure the whole hypothesis rests
on has no sign at all.** The single result above two sigma is *absolute* far-side size, and that
is a quietness proxy, not a wall: a thick book on both sides means a slow tape, and a slow tape
mean-reverts a little. Its twin, absolute NEAR-side size, reads 53.3% — the same direction, which
is exactly what you would expect from a confound and not at all what you would expect from
directional wall pressure.

### The 41-millisecond book — the fidelity stone, turned

The data contract is explicit that `capture.db.book` sees fleeting quotes the 250ms `depth.db`
sample cannot, and "is this wall real or is it being pulled and re-posted" is a fleeting-quote
question. So I rebuilt the wall test from the raw 41ms event stream on the 11 days that carry
it (07-31 → 08-14): every level-1 size increase, every decrease, and the contracts behind each,
rolled to a trailing 30 seconds. 33.9 million updates. 3,269 chop-block races.

| 41ms measure | n | P(revert) | z |
|---|---:|---:|---:|
| **added/removed on the continuation side ≥ 1.0 (a DEFENDED wall) + price stalled ≤2pt** | **481** | **49.3%** | **−0.32** |
| defended wall, no stall condition | 1,478 | 51.4% | +1.09 |
| level-1 refills, top quintile | 648 | 55.1% | +2.59 |
| level-1 pulls, top quintile | 650 | 56.2% | +3.14 |
| total level-1 churn, top quintile | 654 | 55.8% | +2.97 |
| 41ms mean level-1 size far/near, bottom quintile | 654 | 54.1% | +2.11 |

**The defended-wall cell — the literal thing your brief asks for — is 49.3%, below a coin.** The
only quintiles that lift are refills, pulls and total churn *together*, all in the same
direction, which means the signal is "the book is busy", not "the book is defended". A measure
that reads the same whether size is being added or removed is measuring activity.

**Honest note on the two book studies:** at 250ms I get one clean null; at 41ms I get the same
null with a busy-tape confound on top. Two fidelities, same answer. That is as far as the L2
question can be pushed with the data we hold, and I would call the wall term REFUTED for this
application rather than parked.

### Where this sits against last week's section

Last week's `gf_chop_scalp.md` put the chop fade at **47.2%** over 4,249 races. I get **50.6%**
over 5,607. The event definitions are different (that study faded a stretch from VWAP; this one
fades the extreme of a trailing 30-minute range) and the windows only partly overlap, so the two
numbers are not the same measurement and I am not going to reconcile them by argument. What
matters is that they agree on the only thing that counts: **there is no exploitable sign in a
chop fade, and adding L2 does not create one.** Two independent event definitions, two
independent harnesses, same verdict.

---

## 5. Every candidate, by name, including the ones that died

Nine gates. All of them are two-sided by construction — a HIGH fades short, a LOW fades long —
because you do not relegate a direction. All backtested at stop 1.5 ATR / target 0.75 ATR /
600s hold, one position at a time, 120s cooldown, across all 18 days.

| # | name | the idea, in one line |
|---|---|---|
| CT-1 | **FLATLINE** | control: range extreme in a dead 30-min structure, **no book input at all** |
| CT-2 | **THINWALL** | CT-1 + the continuation side is THIN (what the leaked race pointed at) |
| CT-3 | **EXHAUST-CT** | **your brief, literally**: delta in + price refuses + far-side wall + VWAP-flat |
| CT-4 | **PUSHFADE** | a sharp 10-min push into the edge of a 30-min structure going nowhere |
| CT-5 | **DEPLETE** | CT-1 + the continuation side is DRAINING (30s size change below its 5m mean) |
| CT-6 | **THINWALL+PUSH** | CT-2 + the sharp-push trigger |
| CT-7 | **STALL** | wall + price stalls; delta and VWAP-flat terms deleted |
| CT-8 | **STALL-NO-BOOK** | CT-7 with the book term deleted — the control that decides if L2 earns its keep |
| CT-9 | **STALL+PUSH** | the single best cell of the 108-cell sweep, chosen in-sample only |

### The scoreboard

| candidate | n | net | win% | $/trade | green days | trades/day | IS net | **OOS net (this week)** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **CT-9 STALL+PUSH** | 230 | **+$232.05** | 69.1% | +$1.01 | 11/18 | 12.8 | +$399.49 | **−$167.44** |
| **CT-3 EXHAUST-CT** | 78 | **+$230.97** | 70.5% | +$2.96 | 12/18 | 4.3 | +$279.92 | **−$48.95** |
| CT-6 THINWALL+PUSH | 167 | −$88.99 | 65.9% | −$0.53 | 11/18 | 9.3 | +$43.10 | −$132.09 |
| CT-7 STALL | 404 | −$968.23 | 63.6% | −$2.40 | 7/18 | 22.4 | −$505.24 | −$462.98 |
| CT-4 PUSHFADE | 911 | −$1,127.01 | 65.3% | −$1.24 | 5/18 | 50.6 | −$823.01 | −$304.00 |
| CT-1 FLATLINE | 838 | −$1,807.38 | 64.0% | −$2.16 | 5/18 | 46.6 | −$1,494.86 | −$312.52 |
| CT-5 DEPLETE | 689 | −$2,460.69 | 61.7% | −$3.57 | 3/18 | 38.3 | −$1,809.20 | −$651.49 |
| CT-2 THINWALL | 675 | −$3,188.04 | 60.9% | −$4.72 | 3/18 | 37.5 | −$2,368.56 | −$819.48 |
| CT-8 STALL-NO-BOOK | 1,113 | −$4,130.16 | 62.2% | −$3.71 | **1/18** | 61.8 | −$3,647.10 | −$483.06 |

**Look at the win-rate column and then ignore it, exactly as your judging rule says.** Every
single candidate wins between 61% and 71% of its trades, including the one that loses $4,130.
That is not a quality signal, it is the geometry: a 1.5-ATR stop against a 0.75-ATR target wins
twice as often as it loses by construction, and needs about 67% just to stand still. **CT-8
wins 62% of 1,113 trades and is the worst gate in the table.** This is the clearest illustration
I have ever produced of why you were right to take win% off the kill list — and also why a high
win% must never go on the *promotion* list either.

Three structural readings from that scoreboard:

**Trade count is the tax, and it is visible.** Rank the table by trades per day and you almost
recover the P&L ranking. CT-8 fires 61.8 times a day and loses the most; CT-3 fires 4.3 times a
day and is the only candidate positive on both n and per-trade terms. You said "a few
high-quality turns a day, not hundreds" — the data agrees, but note *why*: it is not that the
selective gates find better turns, it is that they pay less friction while being equally
directionless.

**CT-8 vs CT-7 is the L2 verdict in two rows.** CT-7 is CT-8 plus the wall term. Adding the book
takes 1,113 trades to 404 and −$4,130 to −$968. The book improved the dollar-per-trade from
−$3.71 to −$2.40 — but it did that by **removing trades, not by finding good ones**, and both
numbers are still deep negative. A filter that improves a loser by cutting exposure is a
volume cut wearing a filter's clothes. We have seen this exact shape before on this desk, in
the rgv absorption-confirm.

**CT-2 and CT-5 — the inverted-book candidates — are the two worst gates in the table.** Those
were built directly from what the LEAKED race pointed at (thin/depleting far side). When the
leak came out, so did they: −$4.72 and −$3.57 a trade. They are worth showing precisely because
they are the fingerprint of the bug, and they are the reason I do not trust a signal that only
appears in one measurement.

---

## 6. The sweeps — is there a plateau, or a spike?

### 6a. Thresholds: 108 cells, no plateau

CT-3's five thresholds swept: wall ratio × aggressor delta × price-progress cap × VWAP-flatness
× efficiency ceiling. In-sample, stop 1.5 / target 0.75.

**50 of 108 cells positive, median dollar-per-trade −$0.36.** A coin flip over the grid. But the
marginals are genuinely informative, and this is where the mechanism gets diagnosed:

| parameter | setting | cells | positive | median $/trade | median n |
|---|---|---:|---:|---:|---:|
| **price progress cap** | **≤ 2 pt (stall)** | 54 | **40** | **+$1.73** | 41 |
| **price progress cap** | ≤ 4 pt | 54 | 10 | −$1.44 | 78 |
| far-side wall | ≥ 1.2× | 36 | 13 | −$0.52 | 137 |
| far-side wall | **≥ 1.5×** | 36 | **24** | **+$2.39** | 58 |
| far-side wall | ≥ 2.0× | 36 | 13 | −$2.66 | 17 |
| aggressor delta | ≥ 0.00 | 36 | 13 | −$0.62 | 97 |
| aggressor delta | ≥ 0.05 | 36 | 17 | −$0.80 | 70 |
| aggressor delta | ≥ 0.10 | 36 | 20 | +$0.92 | 40 |
| **VWAP flatness** | **≤ 0.5 ATR** | 36 | 14 | −$0.70 | 41 |
| **VWAP flatness** | **≤ 1.0 ATR** | 36 | 18 | −$0.01 | 65 |
| **VWAP flatness** | **switched OFF** | 36 | 18 | **+$0.00** | 76 |
| efficiency ceiling | ER < 0.15 | 54 | 26 | −$0.47 | 44 |
| efficiency ceiling | ER < 0.30 | 54 | 24 | −$0.32 | 82 |

**The stall term is the only parameter in the gate that separates.** Tighten "price refused to
follow" from 4 points to 2 and the grid goes from 10-of-54 positive to 40-of-54. That is a real
mechanism and it is the honest residue of the `exhaustion_short` lineage — but note what it is
*not*: it is not the book. It is a price condition.

**The wall term is a spike, not a plateau, and that is a curve-fit tell.** 1.5× works, 1.2×
fails, 2.0× fails, and at 2.0× the sample collapses to a median of 17 trades. Your own rule —
edge appearing only as n collapses — applies to it exactly.

**The VWAP-flatness filter does nothing at all.** −$0.70, −$0.01, +$0.00 across its three
settings. Switching it off entirely is, to the cent, as good as the tightest setting. It is a
clean, cheap null: the 30-minute efficiency read already carries the "is it actually ranging"
question, and the flatness test is measuring the same thing twice.

### 6b. Exits: 60 cells, and here there IS a plateau — and it disagrees with the guess

Same entries (CT-3 base, n=41 in-sample), stop × target × hold swept. Dollar-per-trade:

| stop \ target | 0.25 ATR | 0.50 ATR | 0.75 ATR | 1.00 ATR | 1.50 ATR |
|---|---:|---:|---:|---:|---:|
| 0.75 ATR | +0.77 | +0.02 | +1.30 | +0.63 | −3.16 |
| 1.00 ATR | +1.48 | +0.56 | +1.83 | +1.02 | −3.97 |
| **1.50 ATR** | +2.67 | +3.37 | **+6.36** | **+5.32** | +0.65 |
| **2.00 ATR** | +2.04 | +3.30 | **+6.90** | **+5.88** | +1.33 |

**53 of 60 cells positive, median +$1.84/trade, and a genuinely broad ridge** in the
bottom-middle: any stop at or above 1.5 ATR with a target between 0.5 and 1.0 ATR sits between
+$3.30 and +$6.90. That is a plateau in the proper sense — you can move both knobs a long way
without falling off.

**Proven R versus your guess.** You said "bank at ~0.5R/1R — sweep the exact R". The sweep says
the reward-to-risk that works is **0.33R to 0.67R, and only off a WIDE stop (1.5–2.0 ATR)**. The
peak cell is target 0.75 ATR on a 1.5–2.0 ATR stop = **0.38R–0.50R**. So your 0.5R instinct was
right and your 1R alternative is the worse half of the pair — but the important part is the
*other* axis, which you did not guess: **a tight stop kills it.** At a 0.75-ATR stop the same
entries make $1.30 a trade instead of $6.36. The scalp needs room to breathe far more than it
needs a small target.

I want to be blunt about the size of that finding, though: it is an exit ridge measured on
**41 in-sample trades**, sitting on entries that do not survive out-of-sample. It is a good
piece of engineering knowledge about how to exit a fade on this instrument. It is not an edge.

---

## 7. The robustness battery — where the two survivors died

Only CT-3 and CT-9 finished the scoreboard positive, so they get the full treatment. Same
battery, same ruler, no exceptions.

### 7a. CT-9 STALL+PUSH — the best-of-108, judged out-of-sample

| test | result | verdict |
|---|---|---|
| In-sample (13 days) | n=148, **+$399.49**, 70.9% win, **+$2.70/trade** | passes |
| **Out-of-sample — THIS WEEK** | n=82, **−$167.44**, 65.9% win, **−$2.04/trade** | ✗ **KILLED** |
| Whole window | n=230, +$232.05, 69.1% win, +$1.01/trade | marginal |
| **Strip the best 3 trades** | **+$27.77 → +$0.12/trade** | ✗ **KILLED** |
| Placebo, 300 side-shuffled draws, in-sample | real +$399.49 vs placebo mean +$196.57 (sd $261.27), **p = 0.203** | fails |
| Placebo, out-of-sample | real −$167.44 vs placebo mean −$98.25, **p = 0.740** | fails — worse than the shuffle |
| Mirror test (every side inverted) | in-sample −$643.42, whole window −$804.76 | passes — the sign is not arbitrary |
| Strip the best 5 | −$68.25 | fails |
| Leave-one-day-out | 0 of 18 removals turn it negative (min +$74.71) | passes |
| Side symmetry | LONG 111 / +$109.65 · SHORT 119 / +$122.40 | passes, cleanly |
| Cost stress +$0.50/RT | +$117.05 | survives |
| Cost stress +$1.00/RT | **+$2.05** | ✗ dead |
| Cost stress +$2.00/RT | −$227.95 | dead |
| Trend-tape bleed (ER ≥ 0.30) | n=125, −$7.43, −$0.06/trade | harmless |
| US session | n=38, +$285.81, +$7.52/trade | the only green pocket |
| Overnight | n=192, −$53.76, −$0.28/trade | flat |

Its five out-of-sample days, which are the five days the whole project exists for:

| day | n | net | win% | $/trade |
|---|---:|---:|---:|---:|
| 2026-08-10 | 15 | −$71.42 | 60.0% | −$4.76 |
| 2026-08-11 | 10 | +$25.71 | 80.0% | +$2.57 |
| 2026-08-12 | 14 | +$24.29 | 78.6% | +$1.74 |
| 2026-08-13 | 16 | −$56.81 | 56.2% | −$3.55 |
| 2026-08-14 | 27 | −$89.21 | 63.0% | −$3.30 |

**Green on two of this week's five chop days.** Your brief said it must hold on ALL the chop
days, not one. It holds on two, loses on three, and the sum is negative.

The exit mix says the rest: 63 stops at −$33.82 each against 153 targets at +$16.06 each. It
needs **67.8%** just to tread water and it delivers **69.1%** — the whole "edge" is 1.3 percentage
points of win rate above its own geometric break-even, and 1.3 points is not an edge on 230
trades, it is a rounding error.

### 7b. CT-3 EXHAUST-CT — your literal mechanism, killed by its own placebo

| test | result | verdict |
|---|---|---|
| In-sample (13 days) | n=41, **+$279.92**, 75.6% win, **+$6.83/trade** | passes, and looks great |
| **Out-of-sample — THIS WEEK** | n=37, **−$48.95**, 64.9% win, **−$1.32/trade** | ✗ **KILLED** |
| Whole window | n=78, +$230.97, 70.5% win, +$2.96/trade | marginal |
| **Placebo — 300 side-shuffled draws, in-sample** | real **+$279.92** vs placebo mean **+$111.69** (sd $181.44), **p = 0.207** | ✗ **KILLED** |
| Placebo, out-of-sample | real −$48.95 vs placebo mean −$95.69, p = 0.213 | fails |
| Placebo, whole window | real +$230.97 vs placebo mean +$15.99, p = 0.163 | fails |
| Mirror test (every side inverted) | in-sample −$174.45, whole window −$337.96 | passes — the sign is not arbitrary |
| Strip the best 3 | +$99.81 → +$1.33/trade | fails |
| Strip the best 5 | +$47.52 → +$0.65/trade | fails |
| Leave-one-day-out | 0 of 18 removals turn it negative | passes |
| Side symmetry | LONG 30 / +$134.29 · SHORT 48 / +$96.68 | passes |
| Cost stress +$1.00/RT | +$152.97 | survives |
| Selectivity | 4.3 trades/day | exactly what you asked for |

**The placebo is the one that matters, and it needs explaining because the number looks strange.**
I kept CT-3's entry times exactly as the gate produced them and shuffled only the SIDE — long
where it said short, short where it said long — 300 times. **The shuffled version makes +$111.69
on average.** A random-direction gate is *profitable* on these entries, because the 1.5-ATR-stop
/ 0.75-ATR-target geometry pays out that way regardless of direction. CT-3's real +$279.92 sits
0.93 standard deviations above that, **p = 0.207 — it beats a coin toss about four times in five,
which is another way of saying it does not beat one.**

**But I want to be careful here, because there is a second reading and it is the fairer one.**
I also ran the mirror: invert every side the gate calls, keep everything else. That version loses
**−$174.45 in-sample and −$337.96 across the window.** So the gate's direction is emphatically
*not* arbitrary — flipping it costs about $11 a trade. What the placebo actually says is narrower
and more mundane: **with 41 in-sample trades, the spread between the real gate and a coin is
smaller than the noise of 41 trades.** That is a thin-n verdict, not a mechanism verdict, and
under your own rule thin n is never a refutation. CT-3 goes to PARKED, not REFUTED, and the
revival condition is simply more of it.

What it is *not* is deployable. It wins 75.6% of its trades, makes $6.83 a trade, is green on
12 of 18 days, fires a disciplined three or four times a session — and loses money on the five
days it was built for. Most of what looks impressive about it is the exit geometry, which a
random signal gets for free.

### 7c. The rest of the placebo table

Run identically, 200 draws each, in-sample (CT-3 and CT-9 above were re-run at 300 draws; the
two runs agree to within a few dollars of placebo mean, so nothing here turns on the draw count):

| candidate | n | real | placebo mean | placebo sd | beats placebo | p |
|---|---:|---:|---:|---:|---:|---:|
| CT-6 THINWALL+PUSH | 123 | +$43.10 | −$286.12 | $246.16 | 91.0% | 0.090 |
| CT-3 EXHAUST-CT | 41 | +$279.92 | +$118.29 | $181.53 | 77.5% | 0.225 |
| CT-4 PUSHFADE | 686 | −$823.01 | −$1,175.86 | $732.76 | 69.0% | 0.310 |
| CT-1 FLATLINE | 597 | −$1,494.86 | −$1,607.35 | $770.60 | 58.5% | 0.415 |
| CT-5 DEPLETE | 487 | −$1,809.20 | −$1,126.04 | $720.97 | 18.0% | 0.820 |
| CT-2 THINWALL | 485 | −$2,368.56 | −$1,594.34 | $689.73 | 12.5% | 0.875 |

Not one candidate clears p < 0.05. CT-6 comes closest at p=0.090 — and CT-6 makes **+$43.10
in-sample and −$88.99 across the whole window**, so what it is closest to clearing is a bar for
being reliably worthless. CT-2 and CT-5, the two inverted-book gates, are worse than their own
placebos at p=0.875 and p=0.820, which is a fair description of a signal pointing the wrong way.

---

## 8. Projected chop-day P&L against the +$200–300 bar

You set the bar at +$200-300 on a chop day. Here is the honest projection, taking each
candidate's best honest configuration and applying it to this week's five chop days:

| candidate | this week, 5 chop days | per chop day | vs the +$200–300 bar |
|---|---:|---:|---|
| CT-3 EXHAUST-CT | −$48.95 (37 trades) | **−$9.79** | misses by ~$250/day |
| CT-9 STALL+PUSH | −$167.44 (82 trades) | **−$33.49** | misses by ~$270/day |
| CT-6 THINWALL+PUSH | −$132.09 | −$26.42 | misses |
| CT-1 FLATLINE (control) | −$312.52 | −$62.50 | misses |
| best in-sample rate, applied generously | +$2.70/tr × 11.4 tr/day | **+$30.78** | still misses by ~$220/day |

And that last row is the kindest number in the section — it takes CT-9's *in-sample* per-trade
figure, the one that does not replicate, and multiplies it by its trade rate. Even granting a
result I have just shown is not real, the ceiling is about **$31 a day against a $250 target.**

**To clear $250 on a chop day at CT-3's in-sample $6.83 a trade you would need 37 qualifying
turns per session. The gate produces between three and five.** The gap is not a tuning gap, it
is an order of magnitude, and no threshold in the sweep closes it — the settings that raise the
trade count are exactly the settings that take the per-trade edge negative. That trade-off is
visible right across the sweep table in §6a: every parameter that lifts median n above ~80 also
puts median dollar-per-trade below zero.

---

## 9. What I would actually do with this

**Do not build a chop-turn scalper.** Not because chop is untradeable in principle, but because
the specific thing that would have to be true — that the resting book separates a turn from a
break at a range extreme — is measurably false at two fidelities across 8,386 model-free races,
and because the desk is not losing money in the chop anyway.

**The real lead this section turned up is a bench, not a gate.** −$5,414 on 348 trades opened in
violent-whipsaw blocks, −$15.56 each, 33.9% win — against roughly breakeven across all 206
trades opened in genuinely quiet blocks. The block classifier that produced that split is
cheap and strictly trailing: 1-minute ATR20 above its 67th percentile with 30-minute efficiency
under 0.25, computed from trailing bars in milliseconds. **That is the same family of
measurement `runstate.py` already computes, and it is a Part-1.5 / router question, not a
greenfield one.** I am handing it over rather than claiming it: I have not run the counterfactual
of what benching those blocks would have cost us in missed winners, and until someone does, the
$5,414 is a gross number and not a net one. That counterfactual is the single most valuable
backtest anyone could run off this section.

**Two pieces of engineering worth keeping** even though the gate died:

1. **The exit ridge.** For any fade on MNQ, a stop at 1.5–2.0 ATR with a target at 0.5–1.0 ATR
   (0.33R–0.67R) is a broad, stable plateau — 53 of 60 cells positive. A tight stop on a fade
   costs about $5 a trade against a wide one on identical entries. That is reusable by any gate
   on the roster that fades anything.
2. **The "price refused to follow" term travels; the wall does not.** If anyone reaches for the
   `exhaustion_short` footprint again in a new context, take the stall condition and leave the
   wall ratio behind. The sweep is unambiguous: 40-of-54 cells positive with the stall at 2 points,
   10-of-54 at 4 points, while the wall term spikes at exactly one setting and collapses either side.

---

## 10. Disposition

| lead | verdict | why, and what would bring it back |
|---|---|---|
| **CT-3 EXHAUST-CT** (your literal brief) | **PARKED** | Killed by its **side-shuffled placebo** (p=0.207; the shuffle makes +$112 by itself) and by the **out-of-sample leg** (−$1.32/trade on this week). The mechanism is not disproven — the mirror test says its direction is real (flipping every side costs −$174 in-sample) — the *sample* is hopeless at 41 in-sample trades. **Revive if:** n reaches ~250 real fires (about 12 more weeks of tape at 4.3/day) AND the placebo p drops below 0.05 on that larger n. Cheap to accumulate — 4 trades a day, so a shadow slot costs nothing. |
| **CT-9 STALL+PUSH** | **PARKED** | Killed by the **out-of-sample leg** (−$167.44 on this week's five chop days, p=0.740 against its own placebo there, green on only 2 of 5) and by **strip-the-best-3** (+$27.77 total, $0.12/trade). Its in-sample +$2.70/trade is 1.3 points of win rate above the geometric break-even of its own exit. **Revive if:** a wider tape shows the US-session pocket (n=38, +$7.52/trade) holding on independent days — that is the only segment with a pulse and it is far too thin to act on now. |
| **CT-6 THINWALL+PUSH** | **PARKED** | Best placebo showing in the study (p=0.090) but +$43.10 in-sample and −$88.99 across the window. **Revive if:** the placebo result replicates on fresh tape — it is the only candidate whose direction was better than random at anything approaching significance, and that is worth one more look, on new days only. |
| **CT-1 FLATLINE** / **CT-8 STALL-NO-BOOK** (controls) | **REFUTED** | −$2.16 and −$3.71 a trade, green on 5/18 and **1/18** days, both inside their own placebo distributions (p=0.415, and CT-8 is the worst gate in the table). A range-extreme fade in chop with no further condition is a costed coin flip. Named test: the **model-free first-touch race** — 50.6% over 5,607 events, which is the mechanism failing, not the sample. |
| **CT-2 THINWALL** / **CT-5 DEPLETE** (thin/depleting far side) | **REFUTED** | −$4.72 and −$3.57 a trade, worse than their own placebos (p=0.875, p=0.820). These were built from what the **leaked** race pointed at and did not survive the leak's removal. Named test: **placebo-null plus the leak audit** — the signal existed only in a measurement containing 55 seconds of future. |
| **The far-side WALL as a turn separator** (the core L2 hypothesis) | **REFUTED** | Named tests: the **250ms ten-deep race** (thin far side 49.3%, thick far side 50.0%, z = −0.34 / +0.00 over 1,126 events) and the **41ms event-stream race** (defended wall + stall = 49.3%, z = −0.32, n=481). Two fidelities, 33.9M level-1 updates, no sign. No reformulation is left: I tested the ratio at level 1, at 5 deep, at 10 deep, its 30-second change, its refill count, its pull count and its added/removed balance. |
| **The VWAP-FLAT filter** | **REFUTED** | Named test: the **108-cell threshold sweep**. Three settings (0.5 ATR / 1.0 ATR / off) give −$0.70 / −$0.01 / +$0.00 median dollar-per-trade. It is redundant against the 30-minute efficiency read, which is already in the gate. |
| **The "price refused to follow" (stall) term** | **SHADOW** | The one component with a pulse: 40-of-54 sweep cells positive at ≤2pt against 10-of-54 at ≤4pt. It is not a gate on its own (CT-8 proves that) but it is a real conditioning term and it belongs in the shadow book as a **modifier** for any future fade, not as a signal. |
| **The exit ridge: stop 1.5–2.0 ATR, target 0.5–1.0 ATR (0.33R–0.67R)** | **SHADOW** | 53 of 60 cells positive, a broad plateau rather than a spike. Reusable by any fading gate on the roster. Measured on only 41 in-sample entries, so it is a shape to carry forward, not a number to trust to the cent. |
| **★ The VIOLENT-WHIPSAW block bench** | **SHADOW → hand to Part 1.5 / the router** | The finding this section actually produced: −$5,414 on 348 trades at −$15.56 each in high-ATR/low-efficiency blocks, against roughly breakeven in all the quiet blocks. **Not claimed as an edge** — the missed-winner counterfactual has not been run, so $5,414 is gross. That counterfactual is the next thing to build. |

**No LIVE candidates and no Monday deploy from this section.** The one stone still unturned:
**the whipsaw-bench counterfactual** — what benching the high-ATR/low-ER blocks would have cost
in winners forgone. Everything in §1 says that is where the money is; nothing in this section
proves the bench is free, and I would not arm it on a gross number.

---

## 11. Limitations, stated plainly

* **Eighteen days.** Enough to refute comfortably — a null needs the coin inside the confidence
  interval, and 50.6% over 5,607 races is a coin — and nowhere near enough to confirm anything.
  That asymmetry is why every survivor here is PARKED or SHADOW and none is LIVE.
* **One instrument, one contract month.** MNQ Sep'26. Nothing here has been tested on MGC and
  nothing here should be ported to it — gold gates get invented fresh.
* **Slippage is modelled, not measured**: one tick on entry, one tick beyond the stop. Since
  every conclusion in this section is a refutation, a harsher model only strengthens it. The one
  place this cuts the other way is the exit ridge in §6b, which would narrow under worse fills.
* **The regime attribution in §1 is hindsight labelling.** It answers "where did the money go",
  not "what should have been armed at 09:14". The gate features themselves are strictly
  trailing — that distinction is the whole subject of §3.
* **The out-of-sample leg is five days.** It is the right five days, but it is five. CT-9's
  −$167.44 is a kill on the standard we agreed, not a proof that the mechanism can never work.
* **Two leaks were found and fixed in this harness.** I cannot rule out a third. What I can say
  is that the direction of the surviving result is a null, and leaks manufacture edges rather
  than destroy them — so an undiscovered leak would make this section's verdict *more* negative,
  not less.

---

**VERDICT — the chop-day turn scalp DID NOT SURVIVE.** The lead candidate CT-9 STALL+PUSH was
killed by the **out-of-sample leg** (−$167.44 / −$2.04 per trade across this week's five chop
days, green on only 2 of 5) and by **strip-the-best-3** (+$27.77, twelve cents a trade over the
full window); the operator's literal mechanism CT-3 EXHAUST-CT was killed by its **side-shuffled
placebo** (real +$279.92 against a placebo mean of +$111.69, p = 0.207) and by the same
out-of-sample leg. The core L2 hypothesis — that the far-side book separates a turn from a break
at a range extreme — is **REFUTED** by the model-free first-touch race at both 250ms ten-deep
(49.3% thin / 50.0% thick) and 41ms event-stream fidelity (defended wall + stall = 49.3%, z =
−0.32). Projected chop-day P&L is **−$10 to −$33 per day against the +$200–300 bar, and about
+$31 even on the in-sample figures that do not replicate.** The section's transferable result is
elsewhere: **the desk does not donate in the chop, it donates −$5,414 in the violent-whipsaw
blocks inside chop days** — that is a bench for the router to price, not a gate for greenfield to
build.
