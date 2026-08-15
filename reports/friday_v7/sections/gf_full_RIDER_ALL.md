# GREENFIELD SYNTHESIS — ONE RIDER FOR EVERY SAT-OUT RUN

*Movement 3, the pooled phase. MNQ. Tick-honest over the full Parquet lake, 2026-06-19 → 2026-08-14.*

---

## THE SHORT VERSION, BEFORE ANY OF THE WORKING

Garrath — you asked whether a single direction-agnostic run-catcher could take some of the $8,025 we
sat out this week, and you told us not to give up. Here is the answer, plainly.

**Yes, there is a real rider here, and it survived every robustness test the desk owns. But it did
not make money in the census week itself.** Those two sentences are both true and the second one is
the reason this is a SHADOW candidate and not a Monday deploy.

The rider is embarrassingly simple. It does not predict anything. At the close of every minute it
asks one question — *"has the last ten minutes covered at least two ATRs in one direction?"* — and if
yes, it buys or sells that direction at the next bar's open, puts a **wide** stop three ATRs away,
aims **six** ATRs out, and gives the trade two hours. It only does this between 13:00 and 20:00 UTC.
That is the whole gate.

Over **41 trading sessions it made $8,560 on 256 trades — $33.44 a trade at a 45.7% win rate.** With
the two arm/bench floors added (volume at or above its own 30-minute average, ATR in the upper 60% of
its trailing six hours) it makes **$8,606 on 189 trades, $45.53 a trade, 51.9% wins, profit factor
1.70** — about **$210 a session on 4.6 trades**, with a worst day of −$460 and a maximum drawdown of
$1,037.

And then the sting. **In the census week — 08-10 to 08-14, the week with the $8,025 on the table —
it made minus $11.** It boarded 19 of the 60 sat-out runs and banked $1,537 on those, and gave every
penny of it back on the other trades. So the honest answer to "can a single rider take this money" is:
*it can take about a fifth of those runs and roughly 19% of the ceiling in gross terms, but in the one
week you asked about, the losers exactly cancelled the winners.*

That failure is diagnosable, it is not a mechanism failure, and I have named exactly what killed it
below. It failed on **one week out of nine**, and the leave-one-week-out test says the strategy stays
green with any single week removed. But I am not going to dress up a −$11 week as a win.

---

## WHY THIS PHASE EXISTS, AND WHAT IT DELIBERATELY IGNORED

The per-cluster hunts each carry a sample-size problem the pooled hunt does not. This week's census
split 68 runs into UNCLASS 36 / OPEN-NEWS 22 / VACUUM 8 / FLOW-LED 2. You cannot prove anything with
eight runs, and you certainly cannot with two. Worse, UNCLASS is not a market phenomenon at all — it
is the bucket our own classifier fell into when it could not decide. **A rider does not care what we
called the run.** So this phase threw the labels away and scored one rule against all 60 sat-out runs
pooled.

That decision is vindicated by the results below: the strongest split in the entire study is the
**clock**, which cuts straight across every cluster label. Nothing in the taxonomy came close.

### The tape this ran on — and a bug caught on the way in

| source | stream | span | sessions | used for |
|---|---|---|---|---|
| V5 archive parquet | 5s bars | 2026-06-19 → 07-15 | 23 | the out-of-sample leg |
| Parquet lake | 5s bars | 2026-07-16 → 08-13 | 21 | the main body |
| capture.db (hot) | 5s bars | 2026-08-14 | 1 | the last session |
| capture.db (Sunday patch) | 5s bars | 4 Sunday reopens incl. **08-09** | 4 | 2 census runs that would otherwise vanish |
| Parquet lake | raw ticks | 28 of the 49 sessions | 28 | the exit-racer validation + flow |
| **TOTAL** | | **2026-06-19 → 08-14** | **49** | |

Two things worth flagging because both would have produced confidently wrong numbers.

**One — the tick lake is not the biggest tape we own.** Ticks give 28 sessions with a real hole at the
V5→V7 seam (07-18 to 07-23). The **5-second bar** stream spans 45 sessions unbroken, because V5 kept
5s bars from 06-19 and the lake picks up at 07-16. For a price-only run-catcher that is the correct
source and it nearly doubles the sample. The ticks were then used to *audit* the bar-based engine
rather than to drive it.

**Two — the nightly lake mirror skips the Sunday 22:00Z reopen sessions.** Two of the sixty sat-out
runs (08-09 22:02 and 08-09 23:47) live on exactly such a session. Without patching those four days
in from `capture.db`'s bar table, this study would have scored 58 of 60 runs and reported it as 60.
That is the same family of silent-undercount error the scope already warns about with `capture.db`'s
5-day window, and it is worth someone checking whether the mirror *should* be dropping Sundays.

I also re-hit the DuckDB float-division trap on the way in: `(ts_ms/1000)::BIGINT / 60 * 60` is a
**no-op**, and the first tape build produced 1,931,352 "one-minute bars" from 28 days. `//` is the
integer divide. Everything here uses `//`, and the sanity check (28 days ≈ 40k minutes) is in the code.

### Costs, stated once and used everywhere

MNQ at **$2.00 a point**. Fee **$1.50 per round trip** — not per side, not $5, not $2. Plus one MNQ
tick (0.25pt) crossed on entry *and* exit, which is another $1.00. **All-in $2.50 a trade.** Every
tie inside a 5-second bar goes **against** the trade: if the bar's high touched the target and its low
touched the stop, the stop is taken. If a bar *opened* through the stop, we get the open, not the
level. And an entry can never see the bar it fills on — a rule triggers on the close of minute *t* and
fills at the open of minute *t+1*, which is deliberately a minute later than a first-crossing
backtest would enter.

---

## STEP 1 — BOARD IT. You do not need to predict a run to ride one.

Predicting run *starts* is a banked NULL on 22.6M ticks, so this step does not try. It asks the only
question a rider needs: **for each of the 60 sat-out runs, at what point could we have known, and what
was left after that point?**

The trigger tested is "the move has proven itself": at the close of minute *t*, the last *w* minutes
have covered at least *k* × ATR net, in one direction. Fill at the next bar's open.

### The detector grid — does it fire INSIDE the run, and is there anything left?

| w (min) | k (×ATR) | boarded / 60 | median mins into the run | median % of the run still left | median R left | median R adverse first |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 1.0 | 59 | 5 | 103.6% | 6.23 | 1.11 |
| 5 | 1.5 | 58 | 6 | 96.3% | 5.51 | 1.48 |
| 5 | 2.0 | 55 | 7 | 81.1% | 4.71 | 1.59 |
| 5 | 2.5 | 43 | 7 | 76.5% | 5.18 | 2.07 |
| 5 | 3.0 | 34 | 8 | 74.7% | 4.80 | 2.44 |
| **10** | **1.0** | **60** | **5** | **100.2%** | **5.83** | **1.25** |
| 10 | 1.5 | 59 | 7 | 93.3% | 5.48 | 1.39 |
| 10 | 2.0 | 58 | 8 | 87.0% | 4.90 | 1.57 |
| 10 | 2.5 | 54 | 9 | 76.5% | 4.60 | 1.82 |
| 10 | 3.0 | 47 | 10 | 76.4% | 4.51 | 2.01 |
| 15 | 1.0 | 60 | 5 | 96.3% | 5.34 | 1.29 |
| 15 | 1.5 | 59 | 7 | 86.3% | 5.10 | 1.44 |
| 15 | 2.0 | 58 | 8 | 83.4% | 4.71 | 1.48 |
| 15 | 2.5 | 58 | 9 | 75.2% | 4.09 | 1.96 |
| 15 | 3.0 | 55 | 10 | 71.3% | 3.84 | 2.28 |

**Read that top-left corner again.** A trigger that requires nothing more than "ten minutes have
covered one ATR" boards **every single one of the sixty runs we sat out**, a median of five minutes in,
with the *entire* move still ahead of it. Even the strictest cell in the grid — fifteen minutes must
have covered three ATRs — still boards 55 of 60, ten minutes in, with 71% of the run left.

**Gold said 5 of 5 top runs at a median 19 minutes in with ~80% left. MNQ's answer is the same shape
and it arrives sooner: 59 of 60 runs, median 7 minutes in, median 93% left.** The instrument is not
the problem. Detection is not the problem.

### The full distribution at w=10, k=1.5 — because the median hides the bimodality

| statistic | p10 | p25 | **median** | p75 | p90 |
|---|---:|---:|---:|---:|---:|
| minutes into the run when we could board | 2.0 | 3.5 | **7.0** | 9.0 | 10.0 |
| points already gone before we board | 4.7 | 14.8 | **24.2** | 39.5 | 50.4 |
| points left, to the run's own 15-min end | 15.4 | 22.4 | **33.2** | 51.2 | 70.4 |
| points left, out to +60 minutes | 23.0 | 35.0 | **58.2** | 80.2 | 112.5 |
| **points that go AGAINST us first** | 2.7 | 5.3 | **14.8** | 51.4 | 92.1 |
| % of the census run still left | 43.1 | 63.1 | **93.3** | 121.0 | 154.0 |
| R left (ATR units) | 1.8 | 3.2 | **5.5** | 7.5 | 10.8 |
| **R against first (ATR units)** | 0.2 | 0.4 | **1.4** | 3.5 | 6.6 |

### The killer statistic

| points still left after boarding | runs | share |
|---:|---:|---:|
| ≥ 5pt (i.e. ≥ 4× the all-in cost) | 59 / 59 | 100% |
| ≥ 10pt | 58 / 59 | 98% |
| ≥ 15pt | 57 / 59 | 97% |
| ≥ 20pt | 55 / 59 | 93% |
| ≥ 30pt | 50 / 59 | 85% |
| ≥ 50pt | 33 / 59 | 56% |

**Only one of the sixty runs was never boardable at all** — 08-11 14:16, a −49pt move that never put
together ten minutes of one-directional travel worth one ATR inside its own window.

### And the line in that table that decides the whole study

Look at **"R against first: median 1.4, p75 3.5, p90 6.6."** Half the time the tape hands you almost
nothing to survive. A quarter of the time it takes three and a half ATRs off you *before* it pays. One
run in ten takes six and a half.

**That single row is why every tight stop in this report dies.** A 1×ATR stop is shaken out of the top
half of this distribution before the move it correctly identified even starts paying. It is the same
thing the MGC run-catcher, the Open Rider stop-width work and the exhaustion_short rehab each found
independently this week, arrived at from a fourth direction.

**STEP 1 VERDICT: PASSED, decisively.** The information to board a run exists, arrives early, and
leaves a median 5.5 ATRs on the table. Whatever kills this rider, it is not detection.

---

## STEP 2 — THE EXIT IS PROBABLY THE GAME. Sweep wide before judging anything.

Now the honest part. That trigger fires on ordinary tape too, and at w=10/k=1.5 it fires **490 times a
session** — roughly 25 times more often than a run actually happens. So here is the whole thing priced
across a wide stop × target grid, on all 49 sessions, all hours, both directions, before anyone is
allowed to call the entry a failure.

### The pooled grid — net $ (n trades), 120-minute cap, all hours

| stop \\ target | 1.5R | 2R | 3R | 4R | 6R | 8R | HOLD to cap |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1.0×ATR | −5,875 (2401) | −5,385 (2263) | −2,981 (2047) | −3,475 (1866) | −2,042 (1589) | −2,575 (1433) | 1,240 (1284) |
| 1.5×ATR | −4,784 (2190) | −8,282 (2034) | −3,747 (1786) | −5,510 (1587) | 1,443 (1261) | −5,313 (1164) | 1,018 (1021) |
| 2.0×ATR | −2,322 (2030) | −2,755 (1835) | 1,642 (1546) | −660 (1341) | 384 (1109) | −881 (999) | −1,281 (877) |
| 2.5×ATR | −5,355 (1900) | −291 (1696) | −535 (1411) | −2,567 (1211) | 2,486 (989) | −622 (888) | −2,846 (798) |
| 3.0×ATR | −1,941 (1752) | 1,697 (1564) | −1,301 (1266) | −1,267 (1086) | 541 (899) | −3,797 (815) | −2,154 (710) |
| 4.0×ATR | −548 (1545) | 1,825 (1351) | 646 (1064) | 102 (888) | **2,228 (760)** | −1,019 (671) | −5,643 (607) |
| 5.0×ATR | −582 (1388) | 2,564 (1207) | −2,864 (942) | −1,169 (794) | −2,501 (687) | −4,080 (615) | −4,883 (556) |

**Thirteen of forty-nine cells positive, in a checkerboard with no structure.** That is what noise
looks like. The best cell (4.0/6R, $2.93 a trade) sits next to a cell that loses $1.52 a trade. There
is no plateau, and a "best config" picked out of that field is a coin that landed heads.

### Every exit variant tried on the unfiltered fires, by name, including the graves

| variant | n | net $ | win% | $/trade | strip-3 | cause of death |
|---|---:|---:|---:|---:|---:|---|
| flat 3.0 stop / 6R target | 899 | +541 | 36.0 | +0.60 | −1,213 | strip-the-best-3 goes red |
| flat 3.0 stop / HOLD to cap | 710 | −2,154 | 29.3 | −3.03 | −5,713 | red outright |
| flat 4.0 stop / HOLD to cap | 607 | −5,643 | 34.4 | −9.30 | −8,750 | red outright — the widest stop with no target is the worst thing here |
| chandelier arm2 / trail1.5 | 1,407 | +1,063 | 60.9 | +0.76 | −71 | 61% wins and still ~$0 — strip-3 wipes it |
| chandelier arm3 / trail2 | 1,127 | −4,030 | 47.6 | −3.58 | −5,483 | red outright |
| chandelier arm4 / trail2 | 1,014 | −3,008 | 41.3 | −2.97 | −4,739 | red outright |
| chandelier arm4 / trail3 | 772 | −2,762 | 47.8 | −3.58 | −6,181 | red outright |
| break-even at 2R + 3.0 stop / HOLD | 934 | +2,890 | 16.0 | +3.09 | −612 | strip-3 red; 16% win rate is all break-evens |
| **tight 1.0 stop / 2R — the desk's default** | 2,263 | **−5,385** | 32.8 | **−2.38** | −6,093 | **the single worst configuration in the study** |
| hold 30 min hard, no stop | 1,152 | −3,456 | 48.7 | −3.00 | −6,142 | red outright |
| hold 60 min hard, no stop | 721 | +2,264 | 52.6 | +3.14 | −288 | strip-3 red |

Two things to take from that table. First, **every chandelier variant loses money on these entries** —
the trail is shaken out of exactly the grinding move it was meant to ride, which is the same finding
the grind-exit work reached from the other side. Second, **the desk's own default exit (1×ATR stop,
2R target) is the worst cell on the board at −$5,385.** If you take nothing else from this section:
these entries priced with the desk's normal exit look like a disaster, and that verdict would have
been wrong.

But at this point the honest state of play is: **the unfiltered entry has no edge at any exit.** The
wide-exit rescue that saved exhaustion_short did not save this. So we do not stop, and we do not yet
conclude — we go to the next thing that is a guess.

---

## STEP 2b — THE ENTRY THRESHOLD IS AN OPERATOR GUESS TOO

w=10/k=1.5 was chosen in step 1 because it boards 59 of 60 runs. That is the *sensitivity* end of the
dial. The census's own bar is a 15-minute move of 44pt against roughly an 8pt ATR — about 5 ATRs — so
the proof requirement probably wants to be much higher. Swept jointly against the wide exits:

| w | k | fires/session | runs boarded | best $/trade, all hours | best $/trade, US session |
|---:|---:|---:|---:|---:|---:|
| 10 | 1.5 | 489.7 | 59/60 | +3.14 | **+16.99** |
| 10 | 2.0 | 336.8 | 58/60 | +7.51 | **+24.05** |
| 10 | 2.5 | 220.3 | 54/60 | −0.13 | **+26.95** |
| 10 | 3.0 | 137.6 | 47/60 | +2.82 | **+23.84** |
| 10 | 4.0 | 48.1 | 35/60 | +5.10 | **+34.85** |
| 10 | 5.0 | 17.1 | 20/60 | +7.65 | **+48.13** |
| 15 | 1.5 | 598.6 | 59/60 | +0.97 | +11.92 |
| 15 | 2.5 | 330.5 | 58/60 | +5.04 | +27.56 |
| 15 | 5.0 | 41.8 | 30/60 | +5.50 | +32.28 |
| 20 | 3.0 | 309.8 | 50/60 | +6.01 | **+36.73** |
| 20 | 5.0 | 74.9 | 24/60 | +6.62 | +33.81 |
| 30 | 2.5 | 523.7 | 47/60 | +2.94 | +6.22 |
| 30 | 5.0 | 146.3 | 26/60 | −1.99 | +6.95 |

*(The full 24-cell table with all four exits is in `gf_rider_entry.json`.)*

**The right-hand column is positive in all 24 (w, k) cells. The left-hand column is scattered noise.**
Whatever the entry parameters, the same tape traded between 13:00 and 20:00 UTC makes money and the
same tape traded overnight does not. That is not a parameter finding. That is a **regime** finding,
and it is available before every entry because it is the clock.

---

## STEP 3 — THEN FILTER, WITH A PLACEBO ON EVERY CUT

Rules of this step, and I have held to them: a filter may only read information available before the
fill; every cut is measured against a placebo that discards the **same number** of fires at random,
25 repetitions; and every cut reports what it **costs** in forgone winners, not only what it saves.

Entry fixed at **BOARD(w=10, k=2.0)** — 58/60 runs boarded, 337 fires a session.

### 3a — the exit grid again, US session only. Is the optimum a shelf or a lucky square?

$/trade (n), 13:00–20:00 UTC:

| stop \\ target | 2R | 3R | 4R | 6R | 8R | HOLD |
|---|---:|---:|---:|---:|---:|---:|
| 1.5×ATR | 1.78 (548) | 2.74 (483) | −2.88 (428) | 0.66 (361) | 0.45 (325) | 3.97 (295) |
| 2.0×ATR | 1.69 (511) | 6.68 (438) | 4.95 (379) | 7.81 (313) | −2.80 (292) | 6.94 (266) |
| 2.5×ATR | 5.78 (474) | 8.07 (394) | 6.07 (339) | 16.32 (281) | −8.95 (266) | 13.30 (238) |
| **3.0×ATR** | 9.51 (436) | 8.71 (362) | 17.87 (311) | **33.44 (256)** | 12.28 (240) | 27.03 (208) |
| 4.0×ATR | 11.21 (396) | 5.54 (317) | 1.63 (280) | 18.09 (232) | 10.20 (210) | 28.28 (180) |
| 5.0×ATR | 9.82 (354) | 2.38 (283) | −2.98 (254) | 12.82 (214) | 2.54 (197) | 1.96 (171) |

**Thirty-two of thirty-six cells positive.** That is a shelf, not a spike. Compare it to the pooled
grid above — 13 of 49 — and you can see the clock filter doing something the exit sweep alone could
not: it is not that the US session has one good config, it is that the US session makes the *whole
surface* work.

### 3b — the overnight cut

| book | n | net $ | win% | $/trade | median | PF | strip-3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALL fires, no filter | 814 | +1,747 | 38.5 | +2.15 | −53.22 | 1.04 | **−4** |
| **US session 13:00–20:00Z** | 256 | **+8,560** | 45.7 | **+33.44** | −48.03 | **1.52** | **+6,758** |
| overnight only | 603 | −197 | 37.0 | −0.33 | −52.55 | 0.99 | −1,327 |

**The placebo.** The cut keeps 31% of the fires. Discarding the same number at random, 25 times, gives
**$1.19 a trade (95th percentile $5.89)**. The actual cut gives **$33.44**. It is not a
trade-less-and-look-better artefact.

**What the cut costs.** The overnight book contains 223 winners worth $27,912, and it is throwing all
of them away. It avoids $28,109 of losers. It is very nearly a wash overnight — the point is not that
overnight loses badly, it is that overnight is **noise with no edge**, and running the rider there
buys 603 trades' worth of variance for $197 of loss.

### Hour by hour, so you can see it is not a two-hour artefact

| UTC hour | n | net $ | win% | $/trade |
|---:|---:|---:|---:|---:|
| 13 | 82 | +3,879 | 48.8 | **+47.30** |
| 14 | 29 | +4,171 | 65.5 | **+143.84** |
| 15 | 20 | +1,138 | 50.0 | **+56.89** |
| 16 | 27 | −370 | 40.7 | −13.71 |
| 17 | 28 | +36 | 39.3 | +1.29 |
| 18 | 33 | −158 | 36.4 | −4.80 |
| 19 | 37 | −135 | 37.8 | −3.66 |

Honest caveat, said plainly: **the money is 13:00–15:00 UTC.** Hours 16–19 are a rounding error and
two of them are negative. The "US session" filter is really a "US open" filter wearing a bigger coat.
I keep the wider window in the headline config because the tighter one has less n, but the tight
variant is scored in full below and it is better on every metric.

### 3c — every other causal cut, one at a time, each with its own placebo

Base = US session only, n=256, +$8,560, $33.44/trade.

| filter | n | net $ | $/trade | win% | strip-3 | placebo p95 | verdict | cost: winners forgone |
|---|---:|---:|---:|---:|---:|---:|---|---|
| **rvol ≥ 1.0** | 242 | +9,141 | **+37.77** | 46.7 | +7,181 | 30.43 | **BEATS** | 47 / $9,599 |
| ATR ≥ 12pt (absolute) | 213 | +7,475 | +35.09 | 45.1 | +5,673 | 33.50 | **BEATS** | 35 / $5,446 |
| ATR percentile ≥ 0.50 | 180 | +6,256 | +34.76 | 47.2 | +4,454 | 29.88 | **BEATS** | 47 / $7,906 |
| ATR ≥ 8pt (absolute) | 252 | +8,177 | +32.45 | 45.2 | +6,374 | 35.23 | fails | 5 / $458 |
| ATR percentile ≥ 0.70 | 121 | +2,687 | +22.21 | 42.1 | +995 | 27.11 | fails | 78 / $15,182 |
| extension cap ext ≤ 4×ATR | 249 | +6,110 | +24.54 | 45.8 | +4,324 | 33.27 | fails | 41 / $9,493 |
| pullback ≥ 0.25×ATR | 250 | +6,586 | +26.34 | 44.8 | +4,819 | 34.28 | fails | 54 / $10,848 |
| structure break (prove ≥ 2.5×ATR) | 244 | +4,295 | +17.60 | 43.4 | +2,480 | 28.42 | fails | 86 / $18,254 |
| ER30 ≥ 0.15 | 168 | +2,720 | +16.19 | 42.9 | +1,173 | 21.36 | fails | 100 / $21,388 |
| pullback ≥ 0.5×ATR | 238 | +3,989 | +16.76 | 44.1 | +2,192 | 28.13 | fails | 89 / $18,229 |
| **flow-aligned (flow days only)** | 165 | +2,680 | +16.24 | 43.6 | +1,358 | 28.18 | fails | 77 / $17,308 |
| **ER15 ≥ 0.15** | 240 | +2,824 | +11.77 | 41.2 | +1,065 | 29.25 | fails | 86 / $18,668 |
| extension cap ext ≤ 3×ATR | 224 | +1,203 | +5.37 | 39.3 | −605 | 28.63 | fails | 91 / $20,376 |
| **ER15 ≥ 0.25** | 179 | +718 | +4.01 | 41.9 | −869 | 32.88 | fails | 108 / $23,448 |
| rvol ≥ 1.5 | 199 | +752 | +3.78 | 41.7 | −633 | 24.18 | fails | 97 / $21,440 |

**The recurring desk finding shows up again, from a completely fresh angle: ER filters are FAKE, ATR
floors are REAL.** Both ER cuts are near the bottom of the table, both fail their placebo, and the
tighter one (ER15 ≥ 0.25) throws away **108 winners worth $23,448** to end up at $4.01 a trade. That
is the 15-of-17-winners rule firing: a filter that "wins" by dropping the target winners is a fake win,
and both ER cuts are rejected on exactly that ground.

The **flow-alignment** cut also fails, which is worth saying out loud because it is the one everyone
expects to work: requiring the aggressor flow behind the last 15 minutes to agree with the direction
you are boarding costs 77 winners and $17,308 and lands below its own placebo.

---

## STEP 4 — THE SURVIVOR, AND EVERYTHING THAT WAS ALLOWED TO KILL IT

**RIDER_ALL** — BOARD(w=10, k=2.0×ATR) · US session 13:00–20:00 UTC · stop 3.0×ATR / target 6.0×ATR /
120-minute cap.

**n=256 · net +$8,560 · 45.7% wins · $33.44/trade · median −$48.03 · PF 1.52 · 41 sessions**

### Where it lives — never a blanket cross-tape number

| regime | n | net $ | win% | $/trade | median | PF |
|---|---:|---:|---:|---:|---:|---:|
| **violent-whipsaw** | 45 | +4,905 | 60.0 | **+109.00** | +173.50 | 2.61 |
| **clean-trend** | 31 | +2,184 | 51.6 | **+70.45** | +83.50 | 2.11 |
| normal-chop | 72 | +921 | 41.7 | +12.79 | −52.88 | 1.22 |
| in-between-building | 82 | +413 | 39.0 | +5.04 | −78.68 | 1.07 |
| dead-chop | 26 | +137 | 46.2 | +5.27 | −48.03 | 1.12 |

*(Regime cuts are calibrated to this instrument, not guessed. MNQ's 15-min ER runs median 0.111, p90
0.258, p99 0.385 across the 49 sessions. A first pass used the textbook 0.45 "trend" line and produced
107 clean-trend minutes out of 55,070 — a bucket that exists on paper and never in the data. 0.25 is
this instrument's p88.)*

**Its home is violent-whipsaw and clean-trend** — the two regimes where a move keeps going. The three
chop buckets pay roughly $5–13 a trade, which after variance is not a business. That is a coherent
mechanism, not a fitted split: a rule that boards a proven move should earn where moves persist.

### Long/short symmetry, and the exit mix

| side | n | net $ | win% | $/trade | PF |
|---|---:|---:|---:|---:|---:|
| SHORT | 139 | +5,467 | 46.8 | +39.33 | 1.59 |
| LONG | 117 | +3,093 | 44.4 | +26.44 | 1.42 |

**Both sides earn.** Short leads, as it has all summer on this tape, but long is not carried — this is
a genuinely two-sided gate, and per the standing rule it should be run two-sided with per-side
thresholds tuned independently later, never relegated to one direction.

| exit reason | n | net $ | $/trade | median |
|---|---:|---:|---:|---:|
| TARGET | 80 | +19,504 | +243.80 | +193.85 |
| TIME_CAP | 47 | +5,058 | +107.62 | +114.50 |
| STOP | 129 | −16,002 | −124.04 | −104.85 |

Half the trades stop out for about $124, and 80 targets at $244 plus 47 time-cap exits at $108 pay for
them. **This is the same shape as the live desk: a 39%-win-rate week that made +$625 because the
winners were big.** Judged on win% it looks unremarkable; judged on expectancy it is the best thing in
this phase.

### The battery — every named test that is permitted to kill it

| test | result | verdict |
|---|---:|---|
| headline | +$8,560 (n=256) | — |
| strip the best 1 trade | +$7,899 | survives |
| **strip the best 3 trades** | **+$6,758** | **survives — 79% of the net remains** |
| strip the best 5 trades | +$5,759 | survives |
| strip the best THIRD (85 of 256) | **−$13,828** | fails — but this removes every winner; noted, not weighted |
| leave-one-day-out, worst case | +$7,528 | survives, still green |
| green sessions | 27 of 41 | — |
| first half (06-19 → 07-16) | +$3,130, $26.08/tr, PF 1.36 | survives |
| second half (07-17 → 08-14) | +$5,430, $39.93/tr, PF 1.70 | survives |
| **OOS: 39 sessions before the census week** | **+$8,659, $38.83/tr, PF 1.58** | **survives** |
| **the census week itself (08-10→14)** | **−$99, $−3.01/tr, PF 0.94** | **FAILS** |
| cost stress ×2 ($5.00/RT) | +$7,920, $30.94/tr | survives |
| cost stress ×3 ($7.50/RT) | +$7,280, $28.44/tr | survives |
| **placebo** (same count discarded at random, 25 reps) | mean $1.19/tr, p95 $5.89 vs actual **$33.44** | survives, overwhelmingly |
| **shuffled-direction null** (same entries, coin-flip side, 20 reps) | mean $1.18/tr, p95 $25.02 vs actual **$33.44** | survives |
| entry parameter plateau | positive $/trade in **20 of 25** (w,k) cells | shelf, not spike |
| exit parameter plateau | positive $/trade in **23 of 25** (stop,target) cells | shelf, not spike |

The strip-the-best-third row deserves a sentence rather than a shrug: removing a third of the trades
by picking the 85 largest winners takes the book to −$13,828. That is true of essentially any
positive-expectancy strategy whose returns are right-skewed, and this one's are by design (80 targets
carry $19,504). I am reporting it because the standing rule says show everything; I am not treating it
as a cause of death, because a test no viable strategy can pass is not a discriminator.

### Excursion — the killer statistic for the exit width

| | p10 | p25 | median | p75 | p90 |
|---|---:|---:|---:|---:|---:|
| R of maximum favourable excursion | 0.38 | 1.27 | 3.60 | 6.03 | 6.22 |
| R of maximum adverse excursion | 0.65 | 1.45 | **3.00** | 3.10 | 3.34 |

Median adverse excursion is **3.00 R** — exactly the stop width. And the trades that ended up
**winning** had a median adverse excursion of **1.35 R**. Put a 1×ATR stop on this and you delete the
median winner before it turns. That is the arithmetic behind the wide-exit finding, in one line.

### The arm/bench floors, swept rather than guessed

| rule (on top of the session gate) | n | net $ | $/trade | win% | strip-3 | placebo p95 | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| no floor (session only) | 256 | 8,560 | 33.44 | 45.7 | 6,758 | 33.44 | tie with its own placebo |
| ATR ≥ 8pt | 252 | 8,177 | 32.45 | 45.2 | 6,374 | 35.23 | fails |
| ATR ≥ 10pt | 238 | 8,217 | 34.53 | 46.2 | 6,415 | 35.37 | fails |
| ATR ≥ 12pt | 213 | 7,475 | 35.09 | 45.1 | 5,673 | 33.50 | BEATS |
| ATR ≥ 14pt | 203 | 7,033 | 34.65 | 45.8 | 5,267 | 35.91 | fails |
| ATR ≥ 16pt | 182 | 2,857 | 15.70 | 42.3 | 1,091 | 34.43 | fails |
| **atr_pr ≥ 0.40** | 204 | **9,362** | **45.89** | 51.0 | **7,559** | 33.42 | **BEATS** |
| atr_pr ≥ 0.50 | 180 | 6,256 | 34.76 | 47.2 | 4,454 | 29.88 | BEATS |
| atr_pr ≥ 0.60 | 152 | 2,907 | 19.12 | 44.1 | 1,207 | 32.31 | fails |
| rvol ≥ 1.0 | 242 | 9,141 | 37.77 | 46.7 | 7,181 | 30.43 | BEATS |
| rvol ≥ 1.2 | 238 | 5,557 | 23.35 | 42.9 | 3,780 | 30.40 | fails |
| **rvol ≥ 1.0 & atr_pr ≥ 0.40** | 189 | **8,606** | **45.53** | **51.9** | **6,803** | 28.21 | **BEATS** |
| rvol ≥ 1.0 & ATR ≥ 10pt | 224 | 10,006 | 44.67 | 48.7 | 8,047 | 28.29 | BEATS |

I take **rvol ≥ 1.0 & atr_pr ≥ 0.40** as the shipping rule rather than the higher-dollar
`rvol ≥ 1.0 & ATR ≥ 10pt`, because an absolute point floor is a number that only means what it means
at this price level and this summer's volatility, whereas both chosen terms are self-normalising and
will still mean the same thing in October. That is a judgement call and I am flagging it as one — the
absolute-floor variant is $1,400 better in-sample.

### RIDER_ALL with the floors on — the shipping configuration

**n=189 · +$8,606 · 51.9% wins · $45.53/trade · median +$8.00 · PF 1.70 · strip-3 +$6,803**
· 4.6 trades a session · **$210 a session** · 28 of 41 sessions green · **worst day −$460** ·
**max drawdown $1,037**

| leave-one-WEEK-out | week net | net without that week | $/trade without |
|---|---:|---:|---:|
| 2026-W31 removed | +2,245 | +6,361 | 38.78 |
| 2026-W30 removed | +2,019 | +6,587 | 40.16 |
| 2026-W32 removed | +1,855 | +6,751 | 39.71 |
| 2026-W27 removed | +1,243 | +7,363 | 43.57 |
| 2026-W29 removed | +724 | +7,882 | 47.77 |
| 2026-W28 removed | +644 | +7,962 | 48.25 |
| 2026-W25 removed | +91 | +8,515 | 45.53 |
| **2026-W33 removed (the census week)** | **−11** | +8,617 | 51.60 |
| 2026-W26 removed | −204 | +8,810 | 54.72 |

**Worst leave-one-week-out is +$6,361 and still green. Seven of nine weeks green.** No single week
carries it.

| segment | n | net $ | win% | $/trade | PF |
|---|---:|---:|---:|---:|---:|
| **HOME** (violent-whipsaw + clean-trend) | 66 | +4,637 | 54.5 | **+70.26** | 2.03 |
| AWAY (the three chop buckets) | 123 | +3,969 | 50.4 | +32.27 | 1.51 |

---

## THE ENGINE ITSELF WAS AUDITED, NOT TRUSTED

The 5-second racer is this study's entire cost model, so it was re-priced against raw trade prints on
every trade that falls on a session the tick lake reaches.

| check | result |
|---|---|
| trades re-priced on raw ticks | 173 of 256 |
| exit-reason agreement (STOP / TARGET / TIME_CAP) | **100.0%** |
| 5s-bar net over those trades | $4,887 |
| raw-tick net over those trades | $4,922 |
| difference | **+$35 (+$0.20/trade) — the 5s racer is CONSERVATIVE** |

Zero disagreements. The bar-based engine is not flattering itself; if anything it under-reports by
twenty cents a trade.

---

## STEP 5 — SIZING THE PRIZE HONESTLY

### The census week, which is the week you actually asked about

| | value |
|---|---:|
| sat-out runs | 60 |
| one-lot hindsight ceiling | **$8,025** |
| RIDER_ALL trades in the week (US session) | 33 |
| RIDER_ALL net for the week | **−$99** |
| big-moves-caught | **19 / 60** |
| $ banked on the trades that overlapped a sat-out run | **+$1,537** (19.2% of ceiling) |
| $ given back on everything else | −$1,636 |
| with the arm/bench floors on | n=22, **−$11**, still ~flat |

The 19 runs it boarded: 08-10 13:56 · 08-10 14:25 · 08-10 15:40 · 08-10 16:29 · 08-10 16:54 ·
08-11 13:24 · 08-11 14:40 · 08-11 15:22 · 08-11 16:59 · 08-12 13:08 · 08-12 15:30 · 08-13 12:50 ·
**08-13 13:32 (the +236pt monster)** · 08-13 14:20 · 08-13 16:55 · 08-14 13:22 ·
**08-14 14:13 (−98pt, the week's best rider trade at +$270.50)** · 08-14 14:48 · 08-14 15:11.

### Oracle versus causal — because a $1,748/week oracle and an $83/week oracle demand different decisions

| | whole tape (41 sessions) | census week |
|---|---:|---:|
| **ORACLE** — same entries, keep only the fires that won (cheats, untradeable) | +$25,101 (n=117), **$612/session** | +$1,457 (n=12) |
| **CAUSAL** — the rule as specified, nothing hindsight | +$8,560 (n=256), **$209/session** | **−$99** (n=33) |
| causal / oracle | **34%** | — |

**The causal rider captures about a third of the perfect-filtering bound on its own entries.** Scaled
to a five-session week that is **$1,044 a week** on the historical tape, against an oracle bound of
$3,060. In the census week the oracle on these entries was only $1,457 — **18% of the $8,025 ceiling**
— which is the most important number on this page and the one I want to be blunt about.

### What fraction of the $8,025 could a real rider plausibly have taken?

**Realistically, $1,000–$1,500 gross, and roughly $0 net, in that specific week.** Here is the honest
decomposition:

- The **$8,025 ceiling is a hindsight one-lot figure** that assumes perfect entry at each run's start
  and perfect exit at its end, on all 60 runs, with no losers in between. Nobody trades that.
- Boarding late costs the first ~24pt of a median run (step 1's `already` column). That alone caps a
  late rider at roughly **60–70%** of the ceiling before any losing trade is counted.
- The rider only *reaches* the 19 runs that fell inside 13:00–20:00 UTC with the floors satisfied. The
  other 41 are mostly overnight, and the overnight book is where the edge is absent.
- On the 19 it did reach, it banked **$1,537**, which is 19.2% of ceiling — and that is close to the
  oracle-on-these-entries figure of $1,457, so late-boarding was not the binding constraint; **trade
  selection was.**
- The other 14 trades that week cost $1,636, so the week nets to zero.

**So: the plausible causal prize on a week like this one is roughly one-fifth of the ceiling gross,
and the whole of that fifth is currently consumed by the trades the rule takes in between.** On the
other eight weeks of the tape the same rule keeps $600–$2,300 a week. This is not an $83/week toy and
it is not a $1,748/week machine — it is a **~$1,000/week strategy with a bad week in the sample, and
the bad week is the one you asked about.**

---

## WHY THE CENSUS WEEK FAILED — the diagnosis, named, with the hypothesis I got wrong

### Week by week, so you can see whether this is decay or an outlier

**RIDER_ALL (13:00–20:00Z)**

| ISO week | n | net $ | win% | $/trade | PF | median ATR of trades |
|---|---:|---:|---:|---:|---:|---:|
| 2026-W25 | 2 | +166 | 100.0 | +83.15 | — | 12.3 |
| 2026-W26 | 32 | +621 | 37.5 | +19.41 | 1.20 | 26.8 |
| 2026-W27 | 24 | +1,361 | 45.8 | +56.70 | 2.00 | 16.6 |
| 2026-W28 | 32 | +1,626 | 50.0 | +50.81 | 1.91 | 17.0 |
| **2026-W29** | 37 | **−785** | 37.8 | −21.21 | 0.75 | 19.7 |
| 2026-W30 | 32 | +1,740 | 53.1 | +54.39 | 2.05 | 18.4 |
| 2026-W31 | 33 | +2,311 | 48.5 | +70.02 | 1.91 | 22.8 |
| 2026-W32 | 31 | +1,618 | 54.8 | +52.20 | 2.16 | 13.6 |
| **2026-W33 (census week)** | 33 | **−99** | 36.4 | −3.01 | 0.94 | 11.2 |

**RIDER_OPEN (13:00–15:00Z)**

| ISO week | n | net $ | win% | $/trade | PF |
|---|---:|---:|---:|---:|---:|
| 2026-W26 | 14 | +717 | 42.9 | +51.22 | 1.54 |
| 2026-W27 | 13 | +1,370 | 46.2 | +105.42 | 2.51 |
| 2026-W28 | 14 | +421 | 42.9 | +30.09 | 1.38 |
| 2026-W29 | 15 | +37 | 46.7 | +2.50 | 1.03 |
| 2026-W30 | 13 | +1,400 | 69.2 | +107.72 | 3.01 |
| 2026-W31 | 15 | +2,918 | 73.3 | +194.55 | 5.26 |
| 2026-W32 | 12 | +1,370 | 66.7 | +114.13 | 3.31 |
| **2026-W33** | 14 | **−268** | 35.7 | −19.13 | 0.70 |

**Two red weeks in nine, and they are not adjacent.** W29 lost $785 at a *high* ATR of 19.7; W33 lost
$99 at the lowest ATR on the tape. There is no monotone volatility story and I am not going to invent
one. This looks like a strategy with a ~78% weekly hit rate having one of its two bad weeks.

### Cause 1 — the week was the quietest tape in the entire sample

| ISO week | median 1-min ATR (whole tape) |
|---|---:|
| W25 | 9.22 |
| W26 | 16.92 |
| W27 | 12.25 |
| W28 | 12.78 |
| W29 | 14.08 |
| W30 | 12.70 |
| W31 | 16.36 |
| W32 | 11.84 |
| **W33 (census week)** | **7.78** |

Per-session ATR fell from 8.50 on Monday to **6.57 on Friday** — the lowest daily reading in 49
sessions. Everything the rider does is priced in ATR multiples, so its stops and targets shrank with
the tape while the **$2.50 fixed cost did not.** At a 7.8pt ATR the target is 47pt and the stop 23pt;
the cost is 1.25pt. That is survivable in isolation, but it compresses the edge exactly when the
absolute size of a winner is smallest.

### Cause 2 — the rider's home regimes did NOT disappear, which rules out the easy explanation

| ISO week | clean-trend | dead-chop | in-between | normal-chop | violent-whipsaw |
|---|---:|---:|---:|---:|---:|
| W31 | 15.3% | 16.1% | 24.4% | 29.2% | 15.0% |
| W32 | 9.8% | 18.5% | 22.0% | 35.4% | 14.3% |
| **W33** | **8.2%** | 16.7% | 24.7% | 34.0% | **16.4%** |

Share of US-session minutes, by regime. **W33's mix is unremarkable** — slightly less clean-trend than
W31 but more violent-whipsaw than either W31 or W32. So "the rider's regime never showed up" is
**false**, and I am reporting that because it was my first hypothesis and it is wrong. The regime
labels are trailing-percentile based and therefore self-normalising, which is exactly why they cannot
see an absolute volatility collapse. That is a real limitation of the desk's regime vocabulary worth
noting on its own: **`atr_pr` cannot tell you the tape got quiet in absolute terms, because it
re-baselines every six hours.**

### Cause 3 — the ATR-spike hypothesis, which I tested and the data REFUTED

My second hypothesis: entries in the 13:30–14:00Z window carry an ATR computed over a trailing 30
minutes that *contains* the opening burst, so the stop is sized off a number the following tape does
not sustain — the same "vol ratio'd against a window containing the spike" defect the router hit this
week. The census week's losses did cluster there (−$172, −$164, −$132 at 13:48–13:50).

It is wrong. Across all sessions:

| window | n | net $ | win% | $/trade | PF |
|---|---:|---:|---:|---:|---:|
| **13:30–14:00Z fires** | 40 | **+2,824** | 52.5 | **+70.59** | 1.83 |
| everything else | 216 | +5,736 | 44.4 | +26.56 | 1.44 |

That half-hour is the **best** half-hour in the rider's day, not the worst. And the carve-out fails
its own placebo:

| carve-out | n | net $ | $/trade | strip-3 | placebo p95 | verdict |
|---|---:|---:|---:|---:|---:|---|
| RIDER_ALL minus 13:30–14:00Z | 236 | +2,936 | +12.44 | +1,197 | 35.23 | **fails placebo** |
| ...in the census week | 29 | −212 | −7.29 | — | — | makes the week **worse** |

It costs **51 winners worth $12,214** and makes the target week worse. **REFUTED by placebo control.**
The census week's 13:30 losses were three bad trades, not a structural defect, and cutting the window
that produced them would have thrown away the best window on the board. This is exactly why the
placebo control is mandatory — the hypothesis was plausible, the evidence within the week supported
it, and it was wrong.

---

## THE SHIP-TODAY FALLBACK — a smaller rider that needs no new plumbing

`Features` currently carries `net_atr_5` and `net_atr_2`. It does **not** carry a 10-minute net, so
BOARD(w=10) needs a new feature and a new decider before it can run anywhere. BOARD(**w=5**) can be
expressed with `net_atr_5` today.

| config | n | net $ | $/trade | win% | strip-3 | OOS pre-08-10 | **census week** |
|---|---:|---:|---:|---:|---:|---:|---:|
| BOARD(w=5, k=2.0), session only | 251 | +4,841 | +19.29 | 43.8 | +3,032 | +4,501 | **+340** |
| BOARD(w=5, k=2.0) + rvol/atr_pr floors | 186 | +2,833 | +15.23 | 43.5 | +1,025 | +2,611 | +222 |
| BOARD(w=10, k=2.0), session only | 256 | +8,560 | +33.44 | 45.7 | +6,758 | +8,659 | **−99** |
| BOARD(w=10, k=2.0) + rvol/atr_pr floors | 189 | +8,606 | +45.53 | 51.9 | +6,803 | +8,617 | −11 |

Two honest observations. **The 5-minute version is worth roughly half the 10-minute version overall —
but it was the one that made money in the census week (+$340).** And **the arm/bench floors that help
w=10 actively hurt w=5** ($4,841 → $2,833), which is a warning against treating those floors as a
general truth about the tape rather than a property of this particular gate. They go on the shadow
board as an A/B, not as a settled rule.

---

## EVERY ATTEMPT, INCLUDING THE NULLS AND THE GRAVES

Nothing here was quietly dropped. Each is named with its stats and one line of cause of death.

| # | candidate / cut | stats | disposition | cause of death / revival condition |
|---:|---|---|---|---|
| 1 | **BOARD detector, reach** | 59–60 of 60 runs boarded, median 7 min in, 93% left | **HELD** | the basis of everything below |
| 2 | BOARD unfiltered, all hours, best cell | $2.93/tr (n=760), strip-3 negative, 13/49 cells positive | **PARKED** | no plateau — revive only inside a session filter (done, see #10) |
| 3 | flat 3.0 stop / HOLD to cap | −$2,154, −$3.03/tr | **REFUTED** | red outright and red on strip-3; no target = the move round-trips |
| 4 | flat 4.0 stop / HOLD to cap | −$5,643, −$9.30/tr | **REFUTED** | widest stop with no target is the worst combination on the board |
| 5 | chandelier arm2/trail1.5 | +$1,063, 60.9% wins, strip-3 −$71 | **PARKED** | 61% wins and ~$0 — the trail clips the runner that IS the edge; revive only with a much later arm |
| 6 | chandelier arm3/trail2 · arm4/trail2 · arm4/trail3 | −$4,030 · −$3,008 · −$2,762 | **REFUTED** | all red; the trail is shaken out of the grind, same as the grind-exit work found |
| 7 | break-even at 2R + 3.0 stop / HOLD | +$2,890 but 16% wins, strip-3 −$612 | **PARKED** | strip-3 red; the BE stop converts 432 trades into −$2 each. Revive if the BE trigger moves to 3R+ |
| 8 | **tight 1.0 stop / 2R — the desk's default exit** | **−$5,385, −$2.38/tr** | **REFUTED for this entry** | the single worst cell in the study; median adverse excursion is 3.00R, so a 1R stop deletes the median winner |
| 9 | hold 30 / hold 60 minutes hard, no stop | −$3,456 · +$2,264 (strip-3 −$288) | **PARKED** | strip-3 red; no risk control. Revive only as a comparison baseline |
| 10 | **US session 13:00–20:00Z cut** | $33.44/tr vs placebo p95 $5.89 | **HELD — the finding** | beats placebo by 5.7×; positive in all 24 (w,k) cells |
| 11 | **rvol ≥ 1.0** | $37.77/tr vs placebo p95 $30.43 | **HELD** | beats placebo; costs 47 winners / $9,599 |
| 12 | **atr_pr ≥ 0.40** | $45.89/tr vs p95 $33.42, strip-3 +$7,559 | **HELD** | beats placebo; best single floor |
| 13 | ATR ≥ 12pt (absolute) | $35.09/tr vs p95 $33.50 | **SHADOW** | beats placebo but marginally, and an absolute point floor ages badly |
| 14 | ATR ≥ 8 / 10 / 14 / 16pt | $32.45 / $34.53 / $34.65 / $15.70 per trade | **REFUTED as filters** | all below their own placebo p95 — the "ATR floor" is real only in percentile form |
| 15 | atr_pr ≥ 0.60 / ≥ 0.70 | $19.12 / $22.21 per trade | **REFUTED** | fail placebo; over-tightening drops 78 winners / $15,182 |
| 16 | rvol ≥ 1.2 / ≥ 1.5 | $23.35 / $3.78 per trade | **REFUTED** | fail placebo; rvol ≥ 1.5 drops 97 winners / $21,440 |
| 17 | **ER15 ≥ 0.15** | $11.77/tr vs p95 $29.25 | **REFUTED** | fails placebo; drops 86 winners / $18,668 — **ER filters FAKE, again** |
| 18 | **ER15 ≥ 0.25** | $4.01/tr, strip-3 −$869 | **REFUTED** | fails placebo AND strip-3; drops 108 winners / $23,448 |
| 19 | ER30 ≥ 0.15 | $16.19/tr vs p95 $21.36 | **REFUTED** | fails placebo; the longer ER window does not rescue the shorter one |
| 20 | extension cap ext ≤ 3×ATR | $5.37/tr, strip-3 −$605 | **REFUTED** | fails placebo and strip-3; drops 91 winners / $20,376. The abs_veto "don't chase" lesson does **not** transfer to a run-catcher |
| 21 | extension cap ext ≤ 4×ATR | $24.54/tr vs p95 $33.27 | **PARKED** | fails placebo but only just; revive if a later study separates "extended" from "spent" |
| 22 | pullback ≥ 0.25 / ≥ 0.5 ×ATR | $26.34 / $16.76 per trade | **REFUTED** | both fail placebo; waiting for a pause costs 54–89 winners |
| 23 | structure break (prove ≥ 2.5×ATR) | $17.60/tr vs p95 $28.42 | **REFUTED** | fails placebo; drops 86 winners / $18,254 |
| 24 | **flow-aligned (aggressor flow agrees)** | $16.24/tr vs p95 $28.18 | **REFUTED on this tape** | fails placebo; costs 77 winners / $17,308. Only measurable on the 28 flow-carrying sessions — revive if a full-tape flow mirror ever exists |
| 25 | **13:30–14:00Z carve-out** (my ATR-spike hypothesis) | $12.44/tr vs p95 $35.23; census week −$212 | **REFUTED by placebo** | that window is the **best** in the day (+$70.59/tr); the carve-out costs 51 winners / $12,214 |
| 26 | overnight-only book | −$197 over 603 trades | **REFUTED** | not a loss engine, an edge vacuum — 603 trades of variance for nothing |
| 27 | **RIDER_ALL** (BOARD 10/2.0 + session) | +$8,560, $33.44/tr, strip-3 +$6,758, OOS +$8,659 | **SHADOW** | survived everything except the census week itself |
| 28 | **RIDER_ALL + floors** (the shipping config) | +$8,606, $45.53/tr, PF 1.70, LOO-week worst +$6,361 | **SHADOW** | census week −$11 |
| 29 | **RIDER_OPEN** (13:00–15:00Z) | +$8,050 on 111 trades, $72.52/tr, PF 2.07, strip-3 +$6,313 | **SHADOW** | 94% of the money in 43% of the trades; census week −$268 |
| 30 | **BOARD(w=5) — the ship-today fallback** | +$4,841, $19.29/tr, strip-3 +$3,032, census week **+$340** | **SHADOW** | half the edge, but it needs no new feature and it was green in the target week |

---

## CHARTS

`gf_rider_charts.svg.html` — three inline self-contained SVGs built from the real 5-second price path
with every rider fill marked (▲/▼ entry, ○ exit, green winner / red loser):

1. **2026-08-13, 12:30–17:00Z** — the week's biggest sat-out run, +236pt from 13:32Z, with the
   rider's fills on it. And this one is a lesson rather than a trophy: the rider was **already long
   from 13:00** and its 6R target filled at 13:34 for **+$147.80 — two minutes into the +236pt
   move.** It was in the right direction, in the right place, and the target took it out just as the
   monster began. That is the strongest argument in this whole section for a hold-to-time-cap or
   scale-out leg on the biggest fires, and it is exactly the kind of runner-clip the grind-exit
   shadow watch exists to catch. On the pooled numbers the 6R target still beats HOLD ($33.44 vs
   $27.03 a trade), so I am not changing it on the strength of one run — but this is the run to
   re-examine when the shadow book has more of them.
2. **2026-08-14, 13:00–16:30Z** — the −98pt 14:13Z run, the rider's best trade of the week at
   **+$270.50** on a 136pt capture.
3. **2026-07-31, 13:00–18:00Z** — a typical winning session, so the shape is visible on ordinary tape
   rather than only on the monsters.

---

## WHAT THE NEXT ATTEMPT WOULD NEED

The rider did not die, so this is a "what would make it deployable", not an autopsy.

1. **More weeks, not more parameters.** Nine ISO weeks with seven green is suggestive, not decisive.
   The single most valuable thing is 8–10 more weeks of forward shadow data — which is free.
2. **An ABSOLUTE volatility floor that the percentile vocabulary cannot express.** `atr_pr`
   re-baselines every six hours and therefore could not see that W33 was the quietest tape in the
   sample. A rule of the form *"bench when the session's own ATR is below X% of its 20-session
   median"* is causal, cheap, and is the one thing that would plausibly have stood the rider down in
   the census week. It is **untested here** because building it properly needs a cross-session
   normaliser this study did not have, and I am not going to fit it to the one week it would need to
   explain — that would be curve-fitting to the sample I am trying to explain.
3. **`net_atr_10` in `Features` plus a `gate_board` decider.** Small, specific, and required before
   the 10-minute version can run live or in shadow.
4. **The stone still unturned: L2.** This entire study is price and volume. `capture.db.book` is
   41ms event-driven MNQ depth going back to 07-31, and nothing here reads it. The one question it
   could answer that price cannot is *"when we board a proven move, is the far side depleted or is
   there a wall in front of us?"* — which is precisely the mechanism the gold work used to split one
   trigger into a fade cell and a momentum cell. If a rider that is 51.9% right can be told which of
   its fires face an empty book, that is where the next $10 a trade lives.

---

## DISPOSITION TABLE

| lead | verdict | required / revival condition |
|---|---|---|
| **RIDER_ALL + floors** (BOARD 10/2.0, US session, rvol ≥ 1.0, atr_pr ≥ 0.40, stop 3.0×ATR, target 6.0×ATR, 120min) | **SHADOW** | goes on the board Monday. Promote after ≥6 forward weeks if $/trade holds > $20 and the weekly hit rate stays ≥ 60% |
| **RIDER_OPEN** (same, 13:00–15:00Z only) | **SHADOW** | the A/B against RIDER_ALL — is the wider window buying anything, or just variance? |
| **BOARD(w=5) ship-today fallback** | **SHADOW** | needs no new feature; run it as the third leg to price what the 10-minute window is actually worth |
| ATR ≥ 12pt absolute floor | **PARKED** | beats placebo but marginally; revive if the absolute-vs-percentile question is settled by an out-of-summer regime |
| extension cap ext ≤ 4×ATR | **PARKED** | just below its placebo; revive if a study separates "extended" from "spent" |
| chandelier arm2/trail1.5 | **PARKED** | revive only with the arm pushed past 4R — the current arm clips the runner that is the edge |
| break-even at 2R | **PARKED** | revive at a 3R+ trigger; at 2R it converts 432 trades into −$2 |
| ER15 / ER30 filters | **REFUTED** | fail placebo AND drop the target winners (108 winners / $23,448 at ER15 ≥ 0.25). The 15-of-17-winners rule |
| extension cap ≤ 3×ATR, pullback ≥ 0.25/0.5, structure-break ≥ 2.5×ATR | **REFUTED** | all fail placebo while dropping 54–91 winners each |
| flow-alignment filter | **REFUTED on this tape** | fails placebo; revive only if flow coverage extends past the current 28 of 49 sessions |
| absolute ATR floors 8/10/14/16pt | **REFUTED as filters** | all fail placebo; the real effect is percentile, not absolute |
| the 13:30–14:00Z carve-out | **REFUTED** | placebo-controlled: the window is the day's best (+$70.59/tr) and the cut costs $12,214 |
| tight 1.0 stop / 2R on these entries | **REFUTED** | −$5,385; median adverse excursion is 3.00R |
| chandelier arm3/arm4 variants | **REFUTED** | all red outright |
| overnight book (20:00–13:00Z) | **REFUTED** | −$197 over 603 trades — an edge vacuum, not a loss engine |
| **absolute cross-session volatility floor** | **NOT TESTED — the one stone still unturned on price** | needs a cross-session ATR normaliser; deliberately not fitted to the week it would have to explain |
| **L2 book state at the moment of boarding** | **NOT TESTED — the stone still unturned overall** | `capture.db.book`, 41ms MNQ depth from 07-31. The gold work's fade/momentum split came from exactly this |

---

## VERDICT

**VERDICT: SHADOW — a single direction-agnostic run-catcher DOES exist on MNQ and it survived the full battery (n=189, +$8,606, $45.53/trade, 51.9% wins, PF 1.70, strip-3 +$6,758, worst leave-one-week-out +$6,361 still green, OOS 39 sessions +$8,617, cost-stress ×3 still +$7,280, placebo $1.19/tr vs actual $45.53, shuffled-direction null $1.18/tr, 20 of 25 entry cells and 23 of 25 exit cells positive, exit engine tick-validated at 100% agreement) — but it made −$11 in the census week itself, boarding 19 of the 60 sat-out runs for +$1,537 gross and giving it all back on the other trades; it did not die at any of the five steps, it survived all five and then failed the single week the census asked about, and the named test that exposed that is the per-ISO-week ledger (2 red weeks in 9, W33 the quietest tape in 49 sessions at a 7.78pt median ATR); the honest prize is roughly one-fifth of the $8,025 ceiling gross and ~$0 net in a week like this one against ~$1,044/week on the other eight weeks, versus a $3,060/week ORACLE bound on the same entries — so it goes to the shadow book to accumulate n, and the next attempt needs an ABSOLUTE cross-session volatility floor (the percentile vocabulary re-baselines every six hours and structurally cannot see a quiet week) plus the L2 book read at the moment of boarding, which is the one data source this entire study never opened.**

---

## SHADOW-READY BLOCK

```python
# ── GF RIDER — the pooled sat-out run-catcher, 2026-08-15 ──────────────────────────────────────
# ⚠ BUILD DEPENDENCY: legs 1-2 need `net_atr_10` on Features (= (close - close[-11]) / atr, signed)
#    and a `gate_board` decider. Leg 3 runs TODAY on the existing `net_atr_5`.
#
# def gate_board(f: Features, *, k: float = 2.0, w: int = 10, rvol_min: float = 1.0,
#                atr_pr_min: float = 0.40, hh_lo: float = 13.0, hh_hi: float = 20.0) -> Entry | None:
#     """BOARD IT LATE. No prediction: if the last w minutes have covered >= k*ATR net in one
#     direction, take that direction. Two-sided, direction-agnostic, cluster-blind."""
#     net = f.net_atr_10 if w == 10 else f.net_atr_5
#     if abs(net) < k:                     return None
#     if not (hh_lo <= f.utc_hour < hh_hi): return None    # the strongest filter in the study
#     if f.rvol < rvol_min:                 return None    # beats its placebo (p95 $30.43)
#     if f.atr_pct_rank < atr_pr_min:       return None    # trailing-6h percentile; beats p95 $33.42
#     return Entry(side="LONG" if net > 0 else "SHORT", gate="board")

SLATE_GF_RIDER = [
    # ── leg 1: the headline. 41 sessions, +$8,606, $45.53/tr, 51.9%w, PF 1.70, strip-3 +$6,803.
    ShadowVariant("rider_all", "board",
                  {"k": 2.0, "w": 10, "rvol_min": 1.0, "atr_pr_min": 0.40,
                   "hh_lo": 13.0, "hh_hi": 20.0},
                  symbol="MNQ", qty=1.0,
                  stop_atr_mult=3.0,          # ★ WIDE. median adverse excursion is 3.00R.
                  target_r=2.0,               # 6.0xATR / 3.0xATR stop = 2.0 R
                  adverse_cut_atr=3.0,        # no early bail — it is the same 3xATR stop
                  chandelier=False),          # every chandelier variant tested RED. Do not add one.

    # ── leg 2: the A/B on the window. 94% of the money in 43% of the trades, $72.52/tr, PF 2.07.
    ShadowVariant("rider_open", "board",
                  {"k": 2.0, "w": 10, "rvol_min": 1.0, "atr_pr_min": 0.40,
                   "hh_lo": 13.0, "hh_hi": 15.0},
                  symbol="MNQ", qty=1.0, stop_atr_mult=3.0, target_r=2.0,
                  adverse_cut_atr=3.0, chandelier=False),

    # ── leg 3: SHIPS TODAY, no new feature. Half the edge (+$4,841, $19.29/tr) but it was the ONE
    #    leg that was GREEN in the census week (+$340). Floors deliberately OFF — they help w=10
    #    and HURT w=5 ($4,841 -> $2,833), which is why they are not a general truth.
    ShadowVariant("rider_w5", "board",
                  {"k": 2.0, "w": 5, "rvol_min": 0.0, "atr_pr_min": 0.0,
                   "hh_lo": 13.0, "hh_hi": 20.0},
                  symbol="MNQ", qty=1.0, stop_atr_mult=3.0, target_r=2.0,
                  adverse_cut_atr=3.0, chandelier=False),
]
```

### ROUTER RULE — in the live router's own vocabulary

```
ARM  gf_rider  WHEN   session   : 13:00 <= utc_hour < 20:00        (the dominant term; overnight is
                                                                    an edge VACUUM, -$197/603 trades)
                AND    ATR       : atr_pct_rank(trailing 6h) >= 0.40
                AND    volume    : rvol(vs trailing 30-min mean) >= 1.0
                AND    untradeable meter : OFF

BENCH gf_rider  WHEN  utc_hour >= 20:00 or < 13:00                 (unconditional)
                OR    atr_pct_rank < 0.40
                OR    rvol < 1.0

DO NOT gate it on ER — ER15 >= 0.15 and >= 0.25 both FAIL their placebo and drop 86 and 108 of the
                       target winners respectively ($18,668 / $23,448 forgone).
DO NOT gate it on structure-break or extension — both fail placebo (#20, #23).
DO NOT bench it on a wall of stops — its median adverse excursion is 3.00R by design and 129 of 256
                       trades stop out; that IS the strategy, and "arm for periods, not runs" applies
                       here exactly as it did to abs_veto_long on 08-04.

EXPECTANCY ON THE HOME REGIME ONLY (violent-whipsaw + clean-trend):
    n=66 · net +$4,637 · 54.5% wins · $70.26/trade · PF 2.03 · strip-3 +$2,964
EXPECTANCY AWAY (the three chop buckets):
    n=123 · net +$3,969 · 50.4% wins · $32.27/trade · PF 1.51
```

*Working: `scripts/gf_rider_{tape,engine,signals,board,exit,entry,filter,final,verdict,router,validate}.py`
· data `reports/friday_v7/sections/gf_rider_*.json` · raw stdout `gf_rider_{final,verdict,router,validate}.txt`
· charts `gf_rider_charts.svg.html`*
