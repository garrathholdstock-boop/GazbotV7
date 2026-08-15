# GREENFIELD HUNT — cluster **OPEN/NEWS**
### Friday report 2026-08-14 · Movement 3 · full working
*(MNQ · $2.00/point · $1.50 per round trip · parquet lake 2026-06-19 → 2026-08-14 · frozen census `census_summary.json`)*

---

## 0. THE SHORT VERSION, BEFORE ANY OF THE MONEY

Garrath — I was sent to invent a gate that catches the runs we sat out in the "OPEN/NEWS" bucket.
I did that, and one of them stands up. But the **biggest thing I found is not a gate at all, it is that
the cluster label I was sent to hunt does not mean what its name says**, and that finding outranks
everything else on this page, so it goes first.

Then, in order:

| # | finding | one line |
|---|---|---|
| 1 | **The label is a clock, not a footprint** | `OPEN/NEWS` is literally `if 13 <= hour < 15`. It is true on **every single bar** in that window and false everywhere else. It says nothing about news and nothing about the run. |
| 2 | **But the clock itself is real** | 29.4% of all runs happen in 8.87% of the tape — a **3.31× lift**. The bucket is worthless as a *label* and genuinely useful as a *window*. |
| 3 | **Its right-hand edge is arbitrary** | The run-density decays smoothly: 13h lift 3.52 → 14h 3.10 → 15h 2.04 → 16h 1.69. Cutting at 15:00 splits one continuous phenomenon into two clusters and dumps the 15:00–16:00 half into UNCLASS. |
| 4 | **Five invented gates, one survivor** | ORX, VPOP, SQZGO, FBURST, VWRC → four dead. VPOP refined into POPGO, POPGO's own null battery produced **POPSAR**, which survives everything I could throw at it in-sample. |
| 5 | **A 5-second look-ahead was quietly worth $700** | I had a bug. Fixing it turned ORX's "+$582 building-regime edge" into −$112. Reported in full in §5 because it is the kind of thing that ships a fake gate. |
| 6 | **The escalation DID reveal the footprint — and it is VOLUME, not price** | Pre-run volume separates runs from ordinary minutes with AUC 0.70, rising **monotonically to 0.88 on the top 8 runs**. Pre-run price range is 0.50 — it knows nothing, at any size. |
| 7 | **But the volume footprint does not convert into a trade** | VSURGE, built directly on it, has no parameter plateau (adjacent cells flip sign) and dies on strip-3. Detection ≠ direction ≠ timing, again. |
| 8 | **The survivor does not do the job it was hired for** | POPSAR makes **+$5,706 over 54 trades (+$105.66/trade)** — and catches **2 of the 16 sat-out runs**. It is a good trade that is not the trade I was sent to find. I am reporting both halves of that sentence with equal weight. |

**VERDICT (full statement at the end): POPSAR → SHADOW. The OPEN/NEWS *cluster hunt itself* → NULL,
with the size-threshold finding as the deliverable.**

---

## 1. ★ INTERROGATING THE LABEL FIRST

The brief said to check the cluster label's base rate before trusting anything built on top of it.
I did that first, and it changed how I read the whole section.

Here is the entire rule, from `scripts/run_census.py:52`:

```python
def cluster(hour, flow, mv, amp, fz=None):
    if 13 <= hour < 15:
        return "OPEN/NEWS"          # ← checked FIRST, before flow, before amplitude
    ...
```

That is the whole thing. No economic calendar, no release schedule, no volume test, no flow test.
A run is "OPEN/NEWS" if and only if it started between 13:00 and 15:00 UTC.

### 1.1 Base rate — the label is true on all of its own window

| measure | value |
|---|---:|
| 5s bars in the lake (2026-07-16 → 08-14) | 356,916 |
| bars carrying the `OPEN/NEWS` label | 31,674 |
| **share of the tape wearing the label** | **8.87%** |
| precision of the label *given the clock* | **1.000** |

8.87% sounds discriminating. It isn't. The label is a **deterministic function of the clock** — inside
13:00–15:00Z it is true on 100% of bars, quiet or violent, trending or dead. It cannot separate a run
from a non-run because it never looks at either. **A label that is true on every bar in its own domain
is not a footprint, it is a bucket name.**

### 1.2 The clock, however, is carrying real information

This is the part that saves the exercise. Running the census's own run detector across the whole lake
(320 runs, 15-min close-to-close ≥ 1.5× the typical 15-min range = 69pt) and binning by hour:

| UTC hour | runs | % of runs | % of tape | **lift** | median move |
|---:|---:|---:|---:|---:|---:|
| 00 | 18 | 5.62 | 4.44 | 1.27 | 91.5 |
| 01–12 | 90 | 28.1 | 53.3 | ~0.53 | ~83 |
| **13** | **50** | **15.62** | 4.44 | **3.52** | **126.5** |
| **14** | **44** | **13.75** | 4.44 | **3.10** | **99.5** |
| 15 | 29 | 9.06 | 4.44 | 2.04 | 99.0 |
| 16 | 24 | 7.50 | 4.44 | 1.69 | 93.2 |
| 17 | 13 | 4.06 | 4.44 | 0.92 | 83.0 |
| 18 | 13 | 4.06 | 4.44 | 0.92 | 113.2 |
| 19 | 21 | 6.56 | 4.44 | 1.48 | 83.8 |
| 20–23 | 18 | 5.6 | ~11.3 | ~0.50 | ~98 |

**29.4% of all runs land in 8.87% of the tape — a 3.31× concentration.** And the runs there are bigger:
median 110.8pt in-window against 87.5pt out. So the *window* is worth hunting in. The *label* is just
its name, and the name is misleading in two specific ways.

### 1.3 Misleading way one — there is no "NEWS" in it

If this bucket were about scheduled releases, run starts would pile up at 13:30Z (08:30 ET, the US data
slot) and 14:00/15:00Z. They do not. Every in-window run start, binned to 5 minutes:

| slot | runs | slot | runs | slot | runs |
|---|---:|---|---:|---|---:|
| 13:00 | 3 | 13:45 | 4 | 14:30 | 2 |
| 13:10 | 1 | 13:50 | 5 | 14:35 | 5 |
| 13:15 | 4 | 13:55 | 5 | 14:40 | 3 |
| 13:20 | 5 | 14:00 | 3 | 14:45 | 5 |
| **13:25** | **9** | 14:05 | 2 | 14:50 | 4 |
| 13:30 | 7 | 14:10 | 3 | 14:55 | 4 |
| 13:35 | 3 | **14:15** | **7** | | |
| 13:40 | 4 | 14:20 | 5 | | |

The busiest 5-minute slot is **13:25**, not 13:30. There is no release spike anywhere in this
distribution — it is broad and flat across two hours. What we are actually looking at is **the US cash
open and the ninety minutes after it**, which is a liquidity and participation phenomenon, not a news
one. The name "OPEN/NEWS" gets the OPEN half right and invented the NEWS half.

### 1.4 Misleading way two — the clock rule STEALS from the other clusters

Because the clock test runs first, any 13:00–15:00Z run is taken before flow or amplitude is ever
consulted. Re-labelling all 94 in-window lake runs with the clock rule removed:

| what it would have been | runs | share |
|---|---:|---:|
| UNCLASS | 52 | 55% |
| VACUUM | 17 | 18% |
| FLOW-LED | 14 | 15% |
| VOL-EXPANSION | 11 | 12% |

**31 of 94 in-window runs had a genuine flow verdict waiting for them and never got it.** Two from this
week's own census make the point: `08-11 13:51 UP +124` printed −1,145 net aggressor flow *against* the
move (a textbook VACUUM), and `08-11 14:16 DN −49` printed +1,720 *against* its move (also VACUUM).
Both are stamped OPEN/NEWS and both are therefore invisible to any vacuum work.

### 1.5 And the 15:00 cut-off has nothing behind it

Hour 15 still carries a 2.04× run lift and hour 16 a 1.69×. The decay from 13:00 is smooth. So the
boundary at 15:00 is not a regime edge, it is a round number — and it sends real members of the same
phenomenon into UNCLASS. In this week's own census, `08-13 15:22 DN −98`, `08-13 15:43 DN −61`,
`08-14 15:11 DN −73`, `08-10 15:20 DN −62`, `08-10 15:40 UP +76` and `08-11 15:22 DN −54` are all
UNCLASS purely because they started after the hour struck.

> **What I'd change:** rename the cluster **US-OPEN** and make it a *session tag* that runs ALONGSIDE
> the flow/amplitude taxonomy rather than pre-empting it, with the window extended to 13:00–16:00Z
> where the lift is still ≥1.69×. That is a one-line change in `cluster()` (move the clock test to
> last, and return a tuple) and it would give UNCLASS back about a third of its members with real
> labels attached.

---

## 2. THE TARGET — WHAT THE FROZEN CENSUS ACTUALLY ASKED FOR

From `census_summary.json` and the frozen `census_stdout.txt` (68 runs, 60 sat out, $8,024 of sat-out
ceiling), the OPEN/NEWS cluster holds **22 runs**: 3 caught, 3 fought, **16 sat out**.

| # | run (UTC) | dir | move | $ ceiling | flow | amp% | book |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | 08-10 13:20 | DN | −74 | 147 | +6 | 0.09 | 0.50 |
| 2 | 08-10 13:56 | UP | +109 | 218 | −118 | 0.21 | 0.51 |
| 3 | 08-10 14:25 | UP | +46 | 92 | −438 | 0.22 | 0.50 |
| 4 | 08-10 14:45 | DN | −90 | 179 | +101 | 0.10 | 0.48 |
| 5 | 08-11 13:24 | DN | −137 | 274 | +48 | 0.05 | 0.51 |
| 6 | 08-11 13:51 | UP | +124 | 249 | −1145 | 0.16 | 0.50 |
| 7 | 08-11 14:16 | DN | −49 | 98 | +1720 | 0.15 | 0.50 |
| 8 | 08-11 14:40 | UP | +55 | 110 | +543 | 0.13 | 0.51 |
| 9 | 08-11 14:55 | DN | −89 | 178 | +601 | 0.13 | 0.51 |
| 10 | 08-12 13:08 | UP | +52 | 105 | +0 | 0.08 | 0.45 |
| 11 | **08-13 13:32** | **UP** | **+236** | **472** | +73 | 0.19 | 0.50 |
| 12 | 08-13 14:20 | UP | +75 | 150 | −711 | 0.11 | 0.42 |
| 13 | 08-13 14:41 | DN | −45 | 90 | +432 | 0.08 | 0.53 |
| 14 | 08-14 13:22 | DN | −80 | 159 | +144 | 0.05 | 0.48 |
| 15 | 08-14 14:13 | DN | −98 | 197 | −411 | 0.13 | 0.48 |
| 16 | 08-14 14:48 | DN | −48 | 96 | +160 | 0.07 | 0.48 |

**16 runs · $2,814 of 1-lot hindsight ceiling** — that is 35% of the whole week's sat-out money coming
out of 27% of the sat-out runs. Worth the effort.

One thing to hold in mind for everything below: **this was a dead-vol week.** Median in-window 1-min
ATR ran 14.6–22.3pt Monday to Friday, against 29–41pt for most of July. The census's own run threshold
was 44pt; run the same detector on the full lake and it is 69pt. So the week we are hunting is the
quietest in the sample, and a gate tuned to it would be tuned to the exception.

---

## 3. THE TAPE, AND WHAT I ACTUALLY RAN ON

Everything here is the **parquet lake** (`gazbot7.lake.connect`), never `capture.db` on its own.

| tier | stream | span | days |
|---|---|---|---:|
| v5 archive | 5s bars | 2026-06-19 → 07-15 | 19 |
| parquet lake | 5s bars | 2026-07-16 → 08-13 | 21 |
| hot capture | 5s bars | 2026-08-14 | 1 |
| v5 archive | trade ticks | 2026-07-05 → 07-17 | 12 |
| parquet lake | trade ticks | 2026-07-24 → 08-13 | 15 |
| hot capture | trade ticks | 2026-08-14 | 1 |
| parquet lake | L2 book (L1–3) | 2026-07-31 → 08-14 | 11 |

- **26 days carry trade ticks** in the 12:30–16:00Z window (17,046,818 ticks cached) → the tick-honest
  primary backtest.
- **15 further days carry bars but no ticks** → held back untouched as the out-of-sample leg.
- **Real hole 07-18 → 07-23** for ticks (the V5→V7 seam). Bars bridge it, ticks do not.
- ⚠ **A gap I found and am flagging:** Sunday-evening sessions (07-19, 07-26, 08-02, 08-09) exist in
  `capture.db` but have **no day-file in the parquet lake**, and `connect()` only pulls hot rows for
  days *after* the lake's last, so those Sunday reopens are missing from any lake query. It does not
  touch this section (13:00–15:00Z never occurs on a Sunday evening) but it will silently shrink an
  overnight study, and someone should look at `tape_mirror.py`.

**Costs, asserted in code so they cannot drift:** `VPP = 2.0`, `FEE = 1.50` per round trip, with
`assert (VPP, FEE) == (2.0, 1.50)` at import of `gf_on_engine.py`. Entry and exit each take **1 tick
(0.25pt) of adverse slippage** on top. A stop-and-reverse pays **two** full round-trip fees.

**The simulator.** Signals come off 5s or 1-min bars; execution walks **real trade ticks**. Because a
tick is a single price there is never a "did the stop or the target fill first" fudge. I wrote it
twice — a plain loop and a vectorised twin — and cross-checked them on **650 randomised simulations
across all 26 tick days: 0 mismatches** (`scripts/gf_on_verify.py`). That check found a real
off-by-one: the loop was closing time-stopped trades on the first tick *past* the time stop. Fixed.

---

## 4. THE FIVE INVENTED GATES — LEVEL 1, FULL SAT-OUT SET

Five entries, none ported from a live gate, each built around one claim about why 13:00–15:00Z is
different.

| gate | the claim |
|---|---|
| **ORX** | The 13:00–13:30 range is the day's first real auction. The first 5s close beyond it is the ignition. |
| **VPOP** | The move starts on one bar. Fire on the 1-min bar whose true range clears 2×ATR and closes on its own extreme — aimed straight at the detection-latency problem. |
| **SQZGO** | ORX, but only on days whose 12:30–13:30 pre-open range is compressed. Fewer, cleaner. |
| **FBURST** | 60s net-aggressor flow z ≥ 2 with price agreeing. A tape-order signal, not a price one. |
| **VWRC** | Session VWAP from 13:00; price crosses it and holds 60s with 30-min ER above a floor. |

Each got an 80-cell exit grid (4 stop distances × 10 exit shapes × 2 time stops), and the config was
picked by its **neighbourhood** $/trade, never by the single best cell. Then the full battery.

### 4.1 The scoreboard

| gate | signals | chosen config | n | net $ | win% | $/trade | big-moves-caught |
|---|---:|---|---:|---:|---:|---:|---:|
| ORX | 26 | stop1.0 · trail1.5/1 · flat 15:00 | 26 | **+343** | 34.6% | +13.17 | 2/16 |
| VPOP | 71 | stop1.0 · no target · flat 15:00 | 71 | **+3,123** | 16.9% | +43.98 | 2/16 |
| SQZGO | 9 | stop0.5 · no target · flat 16:00 | 9 | **+466** | 22.2% | +51.72 | 2/16 |
| FBURST | 78 | stop2.0 · 3R target · flat 15:00 | 78 | **+540** | 26.9% | +6.92 | 3/16 |
| VWRC | 38 | stop2.0 · no target · flat 16:00 | 38 | **+3,199** | 26.3% | +84.19 | 1/16 |

### 4.2 The battery, and who died of what

| test | ORX | VPOP | SQZGO | FBURST | VWRC |
|---|---:|---:|---:|---:|---:|
| grid cells negative | **56/80** | 24/80 | **61/80** | **60/80** | 8/80 |
| best cell's neighbourhood min $/tr | **−16.32** | +31.13 | +21.19 | +2.27 | +52.70 |
| strip-best-1 | −708 | +2,429 | −286 | +78 | +2,254 |
| **strip-best-3** | **−1,599** | +1,155 | **−510** | **−608** | +734 |
| strip-best-5 | −2,136 | +66 | −393 | −1,128 | **−523** |
| leave-one-day-out, days negative | **3/26** | 0/25 | **1/9** | 0/26 | 0/20 |
| halves (1st / 2nd) | +596 / **−254** | +521 / +2,602 | **−371** / +837 | **−366** / +906 | +1,706 / +1,493 |
| day-shuffle placebo, median | −454 | +460 | +112 | +148 | +1,406 |
| — % of shuffles beating the real signal | 25.0% | 0.0% | 16.7% | **41.7%** | 8.3% |
| coin-flip on the same clock, median | −66 | +954 | +214 | +380 | +1,459 |
| — % of flips beating the real signal | **26.7%** | 3.3% | **40.0%** | **43.3%** | 6.7% |
| forced all-LONG | −230 | +361 | +815 | −578 | +1,042 |
| forced all-SHORT | +347 | +1,826 | −387 | +1,203 | +1,689 |

### 4.3 Cause of death, one line each

**ORX — REFUTED by the parameter-plateau test.** Its headline number is a single-cell spike. The best
cell (`stop1.0 · trail1/1 · flat 16:00`, +$1,132) has a neighbourhood whose worst member is
**−$16.32/trade**, and 56 of 80 cells in the grid are negative. On top of that it goes to **−$1,599 on
strip-the-3-best**, loses money in the second half, and a quarter of coin flips beat it. There is
nothing here: the opening-range break, on this tape, is noise with a good story attached.

**SQZGO — PARKED on sample size.** n = 9. It is the only gate whose *shape* I still half-believe —
compressed pre-open then break is a real pattern in the literature and its chosen cell's neighbourhood
holds up (+$21.19/trade worst neighbour). But 40% of coin flips beat it, its first half is −$371, and
nine trades cannot carry a verdict either way. **Revive when n ≥ 40** — that is roughly a full quarter
of tape at the current compression threshold, or sooner if the threshold is loosened from the 33rd
percentile to the median (which would roughly double the fire rate; worth a run next week).

**FBURST — REFUTED by the placebo.** **41.7% of day-shuffles and 43.3% of coin flips beat it.** That is
the definition of no signal: shuffle the days, flip the direction, and you do just as well. It also
posts 60/80 negative grid cells, −$608 on strip-3, and a −$366 first half. Note the forced-direction
row — all-SHORT makes +$1,203 while the real signal makes +$540, so the flow-agreement rule is actively
*worse* than ignoring flow and always shorting. Net aggressor flow, standardised or not, does not
predict the next fifteen minutes here.

**VWRC — REFUTED by strip-the-best.** This one hurt, because it looked the best of the five on the
headline (+$3,199, +$84/trade, 8/80 negative cells, both halves green, zero negative LOO days). But
**strip the 5 best trades and it is −$523** — five trades out of 38 carry more than the entire net. And
its exit breakdown is the tell: **28 stop-outs for −$1,885 (0% win), 10 clock-exits for +$5,084 (100%
win)**. Combined with a coin-flip median of +$1,459 — 46% of its money available to a coin toss on the
same clock — there is not enough of a signal left underneath. **REFUTED as an outright directional
gate**; its underlying mechanism reappears, properly handled, in §6.

**VPOP — SURVIVES level 1, and goes forward.** 0% of day-shuffles beat it, 3.3% of coin flips, zero
negative LOO days, second half stronger than first, and — critically — it has a **genuine plateau**:
`time-only` wins at every stop distance from 0.75 to 2.0×ATR ($2,210 / $3,123 / $3,137 / $2,203) and
`tgt4R` is next. Tight targets (1.5R, 2R) sit at zero. **The shape is unambiguous: the money is
entirely in the tail, and capping it kills the gate.** That is exactly what a run-catching gate should
look like, and it is why VPOP earned a second round rather than a headstone.

---

## 5. ⚠ THE BUG I SHIPPED INTO MY OWN FIRST PASS

I am putting this in the body, not a footnote, because it changed a conclusion.

My first run of the five gates produced **ORX +$582 over 11 trades in the building regime, +$52.91 a
trade** — a clean, plausible, regime-specific edge. It was fake. Three separate look-aheads:

1. **5s bars are START-labelled.** A bar stamped 13:35:00 covers 13:35:00–13:35:05, so its *close* is
   not knowable until 13:35:05. I was entering at the first tick after 13:35:00 — a five-second peek,
   and on an ignition bar five seconds is precisely where the money is.
2. **ATR and ER read from the live minute.** The minute bar starting at 13:35:00 does not close until
   13:36:00, so its ATR cannot size a stop at 13:35:05. I was reading it anyway.
3. (found by the twin-simulator check) the **time-stop off-by-one** described in §3.

| | ORX blanket | ORX "building" regime | VWRC blanket |
|---|---:|---:|---:|
| with the look-ahead | −$244 | **+$582 (+$52.91/tr)** | +$712 |
| after the fix | +$34 | **−$112 (−$28.06/tr)** | +$326 |

**A five-second peek was worth roughly $700 across the candidate set and manufactured an entire
regime-specific edge that does not exist.** Every number elsewhere in this section is post-fix. If you
want one operational takeaway from this page it is this: *any* backtest on this desk that reads a bar's
close, ATR or ER at the bar's own start timestamp is producing fiction, and it will look like a good
gate rather than like a bug.

---

## 6. LEVEL 2 — REFINING THE SURVIVOR, AND WHAT THE NULLS FORCED

### 6.1 POPGO — VPOP with the padding removed

VPOP's own time-of-day split told me half of it was dead weight:

| slot | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| 13:00–13:30 (pre-open) | 34 | +249 | 5.9% | **+7.31** |
| 13:30–14:00 (open drive) | 37 | +2,874 | 27.0% | **+77.68** |

And the shift-placebo confirmed it from the other side: the −30min shift "beat" the real signal
(+$3,587 on 37 trades) **only because shifting 30 minutes earlier pushes the pre-open half out of the
window entirely and keeps the good half.** That is not a placebo win, it is a filter I had not written
down yet. So **POPGO = VPOP, restricted to 13:30–15:00Z.**

**POPGO spec** — trigger: a 1-min bar at or after 13:30Z whose true range ≥ 2.0 × ATR14(1-min) and
whose close sits in the extreme 70% of its own range · direction: that bar's direction · entry: first
trade tick after the bar closes, +1 tick adverse · stop: 1.0 × ATR14 · exit: no target, flat 15:00Z ·
max 3 a day.

**POPGO: n = 54 · net +$2,103 · win 20.4% · +$38.94/trade.**

Entry-parameter grid (45 cells, k × close-fraction × trades-per-day, exit held fixed): **7 negative,
median +$20.93/trade** — a real plateau, not a spike.

But the battery is unkind:

| test | result |
|---|---:|
| coin flip on the same clock, median | **+$1,206 — and 22% of 200 flips beat the real signal** |
| forced all-LONG / all-SHORT | +$813 / +$1,419 — **both sides positive** |
| strip-best-3 | **+$245** (from +$2,103) |
| strip-best-5 | **−$756** |
| halves | +$43 / +$2,059 |
| LOO | 0/24 days negative, worst +$1,466 |
| exits | 42 stops −$2,117 (0% win) · 12 clock-exits +$4,220 (92% win) |

### 6.2 The thing the nulls were actually telling me

**Both directions profitable from the same entries is impossible for a directional edge.** If you enter
long and short at the same tick with the same exit, the two P&Ls cancel to minus costs. Getting
+$813 *and* +$1,419 means the money is not in the direction call — it is in the **shape**: a tight stop
truncates the loser while the winner runs unbounded to the clock. That is a straddle. It pays when the
tape makes a big directional move either way, and loses when it round-trips ±1 ATR.

And the random-clock null nails it down: **random times in the same window, random direction, same
rules → median −$170, and only 3% beat the real signal.** So the *moment* POPGO picks is worth real
money and the *side* it picks is close to worthless. POPGO detects a volatility expansion, not a
direction.

We cannot buy a straddle — this desk trades outright MNQ futures. **The one-instrument equivalent of a
straddle is stop-and-reverse.** So I built it.

### 6.3 POPSAR — the candidate the null battery asked for

**POPSAR spec** — trigger, direction, entry and stop identical to POPGO · **on the stop, flip: enter the
opposite side at the stop price, same 1.0 × ATR stop, at most one reversal** · flat 15:00Z · **$1.50
round trip PER LEG** — a reversed trade pays $3.00 in total, charged honestly.

| | n | fee-paying legs | net $ | win% | $/trade |
|---|---:|---:|---:|---:|---:|
| **POPSAR** | **54** | **96** | **+5,706** | **40.7%** | **+105.66** |
| POPGO (same signals, no reverse) | 54 | 54 | +2,103 | 20.4% | +38.94 |

The reversal is where the improvement is, and it is not subtle:

| leg count | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| 1 leg — never stopped, rode the clock | 12 | +4,220 | 92% | +351.62 |
| 2 legs — stopped, reversed | 42 | +1,486 | 26% | +35.39 |

Those same 42 trades were **−$2,117** for POPGO. Turning round after the stop is worth **+$3,603**, net
of the extra 42 round-trip fees. In plain English: *when a 2×ATR pop fails and gives back a full ATR,
it usually keeps going the other way — and this desk currently has nothing that trades that.*

### 6.4 The full grid — 20 cells, every one positive

| | rev 0 | rev 1 | rev 2 | rev 3 |
|---|---:|---:|---:|---:|
| **stop 0.50×ATR** | +719 | +1,613 | +1,631 | +1,421 |
| **stop 0.75×ATR** | +1,541 | +2,912 | +3,742 | +3,504 |
| **stop 1.00×ATR** | +2,103 | **+5,706** | +6,729 | +6,231 |
| **stop 1.50×ATR** | +2,171 | +5,568 | +6,496 | +6,448 |
| **stop 2.00×ATR** | +1,290 | +4,364 | +4,982 | +4,087 |

**Zero negative cells, and the surface is smooth in both directions** — it climbs to a broad ridge
around stop 1.0–1.5 × ATR with 1–3 reversals and falls away gently at the edges. That is a plateau, not
a fit. I deliberately report the **1-reversal** column as the headline rather than the better
2-reversal one, because one flip is the simplest structure that expresses the idea and I would rather
under-claim.

### 6.5 The battery on POPSAR

| test | result | read |
|---|---:|---|
| **random-clock placebo** (same structure, random times in 13:30–15:00Z, 200 draws) | median **−$376**, p90 +$1,128, p95 +$1,607 · **0/200 beat +$5,706** | passes hard |
| **direction coin flip** (200 draws on the starting side) | median **+$2,973**, p90 +$4,066 · **0/200 beat it** | passes hard |
| start on the **wrong** side | **+$251** | direction is worth ~$2,733 |
| strip-best-1 / 3 / 5 / 8 | +4,937 / **+3,506** / +2,205 / +441 | passes strip-3 comfortably |
| strip best **day** / 2 days / 3 days | +4,248 / +3,010 / **+1,964** | not carried by one session |
| leave-one-day-out | **0/24 days negative**, worst +$4,248 | passes |
| halves (1st 12 days / last 12) | +$1,008 / +$4,698 | both green |
| positive days | 13/24 | |
| long / short | LONG 23 tr +$1,694 (+$73.66) · SHORT 31 tr +$4,012 (+$129.41) | **both sides pay** |
| cost stress 2× / 4× slippage | +$6,229 / +$5,274 | not fragile |
| shift placebo, $/trade | −20m +48 · −10m +18 · −5m +25 · **real +106** · +5m +72 · +10m +3 · +20m +2 · +30m −24 | real is the peak |

**On the direction question I need to correct my own §6.2 reading.** The coin-flip test on POPGO's
outright form was inconclusive (22% of flips beat it) and I took that to mean the side did not matter.
On the SAR form the same test is decisive: **the pop's own direction is worth +$2,733 and not one of 200
coin flips beat it.** The reason is variance, not contradiction — the outright form's wrong-direction
branch is a catastrophic loss that swamps the measurement, while the SAR structure caps that branch and
lets the directional information show through. The moment *and* the side both carry information; the
outright form just could not measure the side.

Two honest scratches. The **+5min shift keeps 68% of the edge**, so the exact trigger minute is not
sacred — this is a signal about a *moment in the session*, not a precise price level. And **2× slippage
scores higher than 1×**, which is path noise at n=54 rather than a free lunch; it tells me the result is
not slippage-sensitive, and it tells me not to read the third significant figure of anything here.

### 6.6 POPFADE — the reversal leg on its own

If the reversal carries +$3,603, does it stand alone as a cheaper gate — one fee, not two? Wait for the
pop, wait for it to fail by 1 ATR, then take the other side only.

**POPFADE: n = 42 · net +$3,615 · win 28.6% · +$86.08/trade · 0/20 grid cells negative · random-clock
placebo 0/200 beat it · LOO 0/22 negative.**

Genuinely good — and it dies anyway:

| test | result |
|---|---:|
| strip-best-1 | +$2,795 |
| strip-best-3 | +$1,248 |
| **strip-best-5** | **−$29** |
| exits | 30 stops −$1,456 (0% win) · 12 clock-exits +$5,072 (100% win) |

**PARKED, killed by strip-the-best-5.** Five trades out of 42 are the entire strategy. It is not
refuted — the mechanism is the same one that makes POPSAR work, and POPSAR spreads its money far better
(strip-5 still +$2,205) because the ride-the-clock leg and the fade leg pay on *different* days.
**Revive if n ≥ 100, or if a second instrument (MGC) shows the same fade shape** — two uncorrelated
sources of the same edge would fix the concentration that killed it here.

---

## 7. THE ESCALATION — AND THE SIZE THRESHOLD, WHICH IS THE REAL DELIVERABLE

The brief said: if the full set fails, narrow to the biggest runs, because a stronger footprint may
separate there — and report the size at which a footprint becomes tradeable.

I did that as a **measurement** rather than as five more backtests, which I think is the more honest
form of the question. ⚠ Note the detector here is *not* the one in §1.2: this one runs on 1-minute
bars over the whole lake including the v5 tier (2026-06-19 →), and sets its bar at 1.5× the median
in-window run, which lands at **130pt** rather than §1.2's 69pt. Different span, different grid,
deliberately stricter — so the two run counts (320 all-day / 78 in-window) are not subsets of each
other and should not be compared directly.

For every in-window run on the full lake (78 at that 130pt threshold) and for
**2,847 matched in-window NON-run windows**, I measured what the 10 minutes *before* looked like, then
asked how well each feature separates the two — and whether that separation sharpens as the size bar
rises. AUC 0.50 means the 10 minutes before a run look exactly like any other 10 minutes.

| level | n runs | min move | pre-run **volume** | pre-run **ER** | pre-run **abs drift** | 1-min TR mean | 1-min TR max | 10-min range |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL runs | 78 | 131pt | **0.703** | 0.560 | 0.508 | 0.600 | 0.536 | 0.519 |
| top 25 | 25 | 205pt | **0.769** | 0.603 | 0.682 | 0.734 | 0.568 | 0.617 |
| top 15 | 15 | 235pt | **0.848** | 0.675 | 0.668 | 0.713 | 0.490 | 0.535 |
| top 8 | 8 | 265pt | **0.883** | 0.721 | 0.779 | 0.741 | 0.522 | 0.709 |

**This is the finding the escalation was supposed to produce, and it did produce it:**

1. **There IS a pre-run footprint, and it is VOLUME.** Traded volume in the 10 minutes before a run
   separates it from ordinary tape at AUC 0.70 across all runs, rising **monotonically to 0.88 on the
   top 8**. Efficiency ratio does the same, more weakly (0.56 → 0.72).
2. **It is NOT price.** Pre-run 1-min true range sits at 0.49–0.57 at every size level — it knows
   nothing. Neither does the 10-minute price range until you get to the very top (0.71 on the top 8,
   n = 8, which I would not lean on).
3. **The size threshold at which the footprint becomes properly readable is ≈ 235 points** (AUC ≥ 0.85,
   the top-15 bar). Below that it is a 0.70–0.77 hint. The lake produced **15 such runs in 30 trading
   days** — but this week produced exactly **one** (the 08-13 +236pt). In a dead-vol week the tradeable
   tier is essentially empty.
4. **And here is the uncomfortable part: my survivor triggers on the wrong column.** POPGO/POPSAR fire
   on a price-range pop — the flat 0.50 line. That is precisely why POPSAR earns well and catches
   almost none of the runs I was sent to find.

### 7.1 So I built the gate the footprint asked for — VSURGE — and it failed

**VSURGE spec** — at or after 13:00Z, the last 10 minutes' volume ≥ v × the per-minute mean of the
previous 60 minutes, and 30-min ER ≥ er_min · direction = the sign of the last 10 minutes' drift ·
stop 1.0 × ATR · flat 15:00Z · 10-minute cooldown.

| cfg | n | outright net | $/tr | SAR net | $/tr | big-moves-caught |
|---|---:|---:|---:|---:|---:|---:|
| v1.4 er0.0 | 78 | +2,073 | +26.57 | +1,384 | +17.74 | 2/16 |
| v1.4 er0.2 | 73 | +227 | +3.11 | **−1,167** | −15.98 | 3/16 |
| v1.4 er0.3 | 61 | −335 | −5.49 | +546 | +8.96 | 3/16 |
| v1.6 er0.0 | 78 | +4 | +0.05 | **−2,909** | −37.29 | 4/16 |
| v1.6 er0.2 | 70 | −434 | −6.20 | **−2,339** | −33.41 | 3/16 |
| v1.6 er0.3 | 54 | −385 | −7.13 | +523 | +9.68 | 3/16 |
| v1.8 er0.0 | 78 | +606 | +7.77 | +504 | +6.46 | 4/16 |
| v1.8 er0.2 | 69 | +1,307 | +18.94 | +1,597 | +23.15 | 3/16 |
| v1.8 er0.3 | 52 | +112 | +2.16 | +2,415 | +46.45 | 3/16 |
| v2.2 er0.0 | 77 | +2,207 | +28.67 | +839 | +10.90 | 4/16 |
| v2.2 er0.2 | 59 | +977 | +16.55 | **−458** | −7.76 | 3/16 |
| v2.2 er0.3 | 44 | −170 | −3.87 | +1,257 | +28.56 | 3/16 |
| v2.6 er0.0 | 74 | +1,772 | +23.95 | +2,260 | +30.54 | 4/16 |
| v2.6 er0.2 | 57 | +1,423 | +24.97 | +2,001 | +35.11 | 3/16 |
| v2.6 er0.3 | 41 | +407 | +9.93 | +2,124 | +51.80 | 3/16 |

**VSURGE — REFUTED by the parameter-plateau test.** Look at the SAR column going down: +1,384, −1,167,
+546, −2,909, −2,339, +523, +504, +1,597, +2,415, +839, −458, +1,257… **the sign flips between adjacent
cells.** There is no ridge anywhere in this surface. Confirmed by strip-the-best — the best cell I would
have picked (`v1.8 er0.2`) goes **+$1,307 → −$441 on strip-3** outright and +$1,597 → −$469 on the SAR
form — and by the coin flip, which 18.5% of the time beats it.

**Why the detector does not become a trade.** The volume surge tells you *that* a move is coming with
AUC 0.70–0.88. It does not tell you *which way* (the drift-sign direction rule adds nothing — 18.5% of
coin flips beat it) and it does not tell you *when* (by the time 10 minutes of volume have accumulated,
the run is frequently under way). This is the same wall the desk already hit on run-start prediction
over 22.6M ticks, arrived at from a completely different direction. **The footprint is real and the
trade is not — that is the honest state of the OPEN/NEWS hunt.**

### 7.2 The 16 sat-out runs, one at a time

The mission's actual scoreboard. For each census run I checked whether POPSAR fired within
[start − 5min, start + 15min] and, when it did not, which clause refused it.

| run (UTC) | move | fired | net $ | why |
|---|---:|:--:|---:|---|
| 08-10 13:20 | −74 | yes | −68 | fired, but the first leg took the wrong side |
| 08-10 13:56 | +109 | no | 0 | no trigger — no 1-min bar cleared 2×ATR closing on its extreme |
| 08-10 14:25 | +46 | no | 0 | trigger existed; the 3-a-day cap was already spent |
| 08-10 14:45 | −90 | no | 0 | no trigger |
| 08-11 13:24 | −137 | yes | −60 | fired, correct side, stopped and the reversal stopped too |
| 08-11 13:51 | +124 | no | 0 | no trigger |
| 08-11 14:16 | −49 | no | 0 | no trigger |
| 08-11 14:40 | +55 | no | 0 | no trigger |
| 08-11 14:55 | −89 | no | 0 | no trigger |
| 08-12 13:08 | +52 | no | 0 | **refused — starts before 13:30Z** |
| **08-13 13:32** | **+236** | **yes** | **+1,005** | fired; first leg wrong side, the reversal caught the run |
| 08-13 14:20 | +75 | no | 0 | no trigger |
| 08-13 14:41 | −45 | no | 0 | no trigger |
| 08-14 13:22 | −80 | no | 0 | **refused — starts before 13:30Z** |
| 08-14 14:13 | −98 | no | 0 | no trigger |
| 08-14 14:48 | −48 | no | 0 | no trigger |

**Big-moves-caught: 2/16 on the strict measure (fired AND on the run's side), 3/16 if you count any
fire. +$877 total.**

The dominant refusal is **"no trigger" — 11 of 16.** These runs simply did not open with a 2×ATR
one-minute bar closing on its extreme; they ground out over fifteen minutes without a single ignition
bar. That is a real property of a dead-vol week, and it is the same thing the AUC table says: on
sub-235pt runs there is no footprint big enough to trip a mechanical trigger.

Two more were refused by the 13:30 window start, and one by the trades-per-day cap. Lifting the cap:

| max trades/day | n | net $ | $/trade | big-moves-caught |
|---:|---:|---:|---:|---:|
| 3 | 54 | +5,706 | +105.66 | 2/16 |
| 5 | 59 | +6,293 | +106.66 | 3/16 |
| 8 | 59 | +6,293 | +106.66 | 3/16 |
| unlimited | 59 | +6,293 | +106.66 | 3/16 |

The cap is not binding in practice — the trigger is rare enough that raising it from 3 to 5 adds five
trades and one caught run, at no cost to $/trade. **I would ship max_trades = 5**, but I am reporting
the 3 numbers as the headline because that is what the battery was run on.

The one it caught is the big one, and it caught it the interesting way. On **08-13** POPSAR fired three
times inside the +236pt run's window, for **+$1,005 between them**:

| trigger | first leg | outcome | net $ |
|---|---|---|---:|
| 13:32 | **SHORT** — the wrong side of a +236pt up-move | stopped, **reversed to LONG**, rode the clock | **+595** |
| 13:35 | LONG | never stopped, rode the clock | +506 |
| 13:37 | LONG | stopped, reversed, reversal stopped too | −96 |

So the structure did exactly what it was built to do: the first read was **wrong**, the stop paid for
being wrong, and the flip caught the run anyway. That single sequence is the clearest argument on this
page for the reversal leg.

### 7.3 The escalation levels, stated plainly

| level | what I hunted | outcome |
|---|---|---|
| **Full sat-out set (16 runs)** | ORX, VPOP, SQZGO, FBURST, VWRC | 4 dead, 1 (VPOP) forward |
| **Refinement** | POPGO → POPSAR, POPFADE | POPSAR survives, POPFADE parked |
| **Top-25 / top-15 / top-8 by size** | the pre-run footprint measurement | **footprint found, and it sharpens monotonically** — volume AUC 0.703 → 0.769 → 0.848 → 0.883 |
| **Footprint → gate** | VSURGE | refuted on plateau + strip-3 |

**The size-threshold answer, which is what the brief actually asked for: a footprint becomes readable
at roughly 235 points of 15-minute move (AUC ≥ 0.85), and it is a VOLUME footprint. Below ~130 points
there is nothing to read at all. But readable is not tradeable — at 235pt+ the lake holds 15 events in
30 days, and the one gate I could build on the footprint fell over on plateau and concentration.**

---

## 8. THE ROUTER — AND WHY I AM NOT PROPOSING ONE

The scope is explicit that the router is part of the deliverable, so I swept the arm condition for
POPSAR in the live router's own vocabulary. The result is not what I expected.

### 8.1 One condition at a time

| arm condition | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| **(none — the clock alone)** | **54** | **+5,706** | 41% | **+105.66** |
| ER ≥ 0.15 | 40 | +4,815 | 45% | +120.38 |
| ER ≥ 0.20 | 33 | +3,464 | 42% | +104.96 |
| ER ≥ 0.25 | 28 | +3,769 | 46% | +134.62 |
| ER ≥ 0.30 | 21 | +3,272 | 48% | +155.80 |
| ER ≥ 0.40 | 9 | +2,105 | 56% | +233.94 |
| ATR ≥ 15pt | 51 | +4,984 | 39% | +97.73 |
| ATR ≥ 20pt | 42 | +5,086 | 45% | +121.10 |
| ATR ≥ 25pt | 21 | +3,046 | 52% | +145.04 |
| ATR ≥ 30pt | 12 | +1,946 | 58% | +162.18 |

### 8.2 Two conditions

| arm condition | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| ER ≥ 0.20 & ATR ≥ 15 | 31 | +3,337 | 42% | +107.65 |
| ER ≥ 0.20 & ATR ≥ 20 | 26 | +3,709 | 50% | +142.64 |
| ER ≥ 0.25 & ATR ≥ 15 | 26 | +3,643 | 46% | +140.12 |
| ER ≥ 0.25 & ATR ≥ 20 | 22 | +3,946 | 54% | +179.38 |

### 8.3 Every one of these is a fake win

The $/trade column climbs and the win% climbs, and it is an illusion — **every filter reduces total
net, because the trades it benches were making money.** Take the most plausible one,
`ER ≥ 0.20 & ATR ≥ 15pt`:

| | n | net $ | $/trade |
|---|---:|---:|---:|
| armed (home) | 31 | +3,337 | +107.65 |
| **benched** | **23** | **+2,368** | **+102.96** |

The bench refuses 23 trades that between them made **+$2,368 at +$102.96 a trade** — statistically
indistinguishable from the ones it keeps. This is precisely the 15/17-winners trap the scope warns
about: a filter that "wins" by dropping the target winners is a fake win, and I am rejecting it and
saying so.

Nor is the pattern monotone — ER ≥ 0.15 gives +$120/trade, ER ≥ 0.20 gives +$105, ER ≥ 0.25 gives
+$135. That wobble at n = 28–40 is noise, not a threshold.

**So the router rule I am proposing is: there isn't one beyond the clock.**

> **ROUTER SPEC (POPSAR):**
> **ARM** — every session, 13:30:00Z to 15:00:00Z. Nothing else.
> **BENCH** — outside that window. Flat everything at 15:00:00Z regardless of state.
> **Explicitly NOT gated on** ER, ATR, structure-break or the untradeable meter: all four were swept,
> all four bench profitable trades, none is monotone.

That is an unusual answer for this desk, and I want to be plain about what it costs: **a gate with no
regime condition has no defence when the regime turns against it.** The mitigation here is structural
rather than routed — the stop-and-reverse *is* the regime adaptation, because it flips side when the
first read is wrong. Over 24 days that produced 13 green days and zero negative leave-one-day-out. Over
a genuinely hostile stretch it is untested, and that is the main reason this goes to SHADOW rather than
LIVE.

**The instrument I would want but do not have:** a *forward-looking* participation measure — the
footprint work says pre-run VOLUME carries the information (AUC up to 0.88), but the desk's router
reads ER, ATR and structure-break, none of which is a volume measure. **A rolling volume-vs-baseline z,
computed on the same 1-minute grid the router already uses, is the missing instrument.** It would not
have saved VSURGE as an entry, but it is the only candidate arm-condition on this page with measured
separation behind it, and it is cheap to build.

### 8.4 The regime split, reported because the discipline requires it

| regime | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| building (ER 0.25–0.45) | 23 | +2,763 | 48% | +120.13 |
| clean-trend (ER ≥ 0.45) | 5 | +1,006 | 40% | +201.28 |
| dead-chop (low ATR, ER < 0.25) | 8 | +789 | 38% | +98.63 |
| normal-chop | 16 | +613 | 31% | +38.31 |
| violent-whipsaw (high ATR, ER < 0.25) | 2 | +534 | 50% | +267.18 |

**Green in all five buckets.** That is unusual and it is consistent with the stop-and-reverse story: the
structure does not need the regime to be favourable, it needs the *tape to move*, and 13:30–15:00Z is
where it moves. The weakest bucket is normal-chop at +$38/trade, which is still above costs.

### 8.5 Long/short symmetry

| side | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| LONG | 23 | +1,694 | 35% | +73.66 |
| SHORT | 31 | +4,012 | 45% | +129.41 |

Both sides pay, so it passes symmetry. The short lean is real but I would not tune on it at n = 23/31 —
the sample straddles a stretch of tape that leaned down, and the desk has been burned before by
mirroring one side's optimum onto the other.

---

## 9. THE 250ms L2 READ

Book data (`capture.db.book`, 41ms event-driven, L1–3) covers 11 of the 26 tick days, so this is
**23 of 54 POPSAR trades** and it is thin. Far-side share of L1–3 depth in the 30 seconds before entry —
"far side" being the side price is about to run into, so a low number means the book was depleted and
supposedly telegraphing the move:

| book state at entry | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| far side **THIN** (depleted, share < 0.508) | 11 | +2,569 | 46% | +233.56 |
| far side **THICK** (share ≥ 0.508) | 12 | +1,846 | 42% | +153.85 |

The sign is in the right direction — a depleted far side does better — but **11 against 12 trades cannot
support a filter**, and the median far-side share across all these entries is 0.508, i.e. dead neutral.
The book is not telegraphing these entries in any way I can measure at this n. **Honest null, revisit
when the book lake has a full quarter.**

---

## 10. THE RUN CHARTS

`gf_on_charts.svg.html` — inline self-contained SVG, no CDN, no JS, built from the lake's own 5s closes
and the backtest's **real simulated fills**. Two panels:

- **2026-08-13** — the census's three sat-out OPEN/NEWS runs marked on the price path (orange dashed),
  with POPSAR's actual entries and exits on top. You can see the +236pt run at 13:32, the first leg
  going the wrong way, the stop, and the reversal riding the move for +$1,005.
- **2026-08-14** — a day with three sat-out runs where POPSAR **never fired at all**. I put it in
  deliberately: the misses should be as visible as the hit, and this panel is what "no trigger — 11 of
  16" looks like on a chart.

---

## 11. EVERY ATTEMPT, INCLUDING THE GRAVES

Nothing here was quietly dropped. Nine named candidates across three escalation levels.

| # | candidate | level | n | net $ | $/trade | verdict | cause of death / revival condition |
|---:|---|---|---:|---:|---:|---|---|
| 1 | **ORX** opening-range expansion | full set | 26 | +343 | +13.17 | **REFUTED** | **Parameter plateau** — best cell's worst neighbour −$16.32/tr, 56/80 cells negative; strip-3 −$1,599; 3/26 LOO days negative. Its earlier "+$582 building edge" was a 5-second look-ahead. |
| 2 | **VPOP** volatility pop | full set | 71 | +3,123 | +43.98 | **PROMOTED → POPGO** | Survived: 0% of day-shuffles beat it, genuine time-only plateau across all four stop distances. Refined by dropping the dead pre-open half. |
| 3 | **SQZGO** compressed pre-open → break | full set | 9 | +466 | +51.72 | **PARKED** | n = 9. 40% of coin flips beat it; first half −$371. Neighbourhood holds (+$21.19/tr). **Revive at n ≥ 40** — loosen the compression cut from the 33rd percentile to the median and re-run next week. |
| 4 | **FBURST** 60s flow-burst z ≥ 2 | full set | 78 | +540 | +6.92 | **REFUTED** | **Placebo** — 41.7% of day-shuffles and 43.3% of coin flips beat it; 60/80 cells negative; forced all-SHORT (+$1,203) beats the real signal, so the flow-agreement rule is worse than ignoring flow. |
| 5 | **VWRC** VWAP reclaim drive | full set | 38 | +3,199 | +84.19 | **REFUTED** | **Strip-the-best-5 → −$523.** 5 of 38 trades carry more than the whole net; 28 stops −$1,885 / 10 clock-exits +$5,084; coin-flip median +$1,459 is 46% of its money. |
| 6 | **POPGO** VPOP after 13:30 only | refinement | 54 | +2,103 | +38.94 | **PARKED — superseded** | Strip-3 → +$245, strip-5 → −$756; 22% of coin flips beat it. Not dead, just strictly dominated by POPSAR on identical signals. **Revive only if the reversal leg proves unexecutable live.** |
| 7 | **POPSAR** pop, stop-and-reverse | refinement | 54 | **+5,706** | **+105.66** | **★ SHADOW** | Survived the whole battery. Held back from LIVE by the OOS concentration in §12. |
| 8 | **POPFADE** the reversal leg alone | refinement | 42 | +3,615 | +86.08 | **PARKED** | **Strip-the-best-5 → −$29.** 5 of 42 trades are the strategy. **Revive at n ≥ 100, or if MGC shows the same fade shape** — a second uncorrelated source would fix the concentration. |
| 9 | **VSURGE** pre-run volume surge | escalation | 69 | +1,307 | +18.94 | **REFUTED** | **Parameter plateau** — sign flips between adjacent grid cells with no ridge anywhere; strip-3 → −$441; 18.5% of coin flips beat it. The footprint it is built on is real (AUC 0.88); the trade is not. |

---

## 12. THE SKEPTIC'S PASS ON MY OWN SURVIVOR

POPSAR makes +$5,706 over 24 days on one lot. The live six-gate desk made **+$625** this week. I am
claiming a single invented gate that out-earns the entire desk by roughly 3×, and that claim deserves
to be attacked, not celebrated. Here is everything I can find wrong with it.

**1. The out-of-sample leg is carried by two days.** This is the serious one. On the 15 days that have
bars but no ticks — genuinely untouched by any fitting — bar-executed with the stop winning every tie:

| | n | net $ | win% | $/trade |
|---|---:|---:|---:|---:|
| OOS, all 14 trading days with fires | 37 | +1,807 | 32.4% | +48.85 |

Per day: `06-22 −294 · 06-23 +132 · 06-24 −75 · 06-25 +1,660 · 06-26 +64 · 06-29 −259 · 06-30 +1,202 ·
07-01 −407 · 07-02 −312 · 07-03 −52 · 07-20 +290 · 07-21 −255 · 07-22 +138 · 07-23 −24`

**Only 6 of 14 OOS days are green, and stripping the best two (06-25 and 06-30) leaves −$1,055.**
The in-sample set is far better behaved (13/24 green, strip-best-3-days still +$1,964), but in-sample
good behaviour is worth less than out-of-sample good behaviour, and this is the number that keeps
POPSAR out of the LIVE column. **It is not a refutation** — the OOS days are a different, much
higher-ATR regime (June ran 27–54pt 1-min ATR against August's 15–22), the execution is bar-based
rather than tick-based, and the sample is 37 trades. But it is the honest reason to incubate rather
than deploy.

**2. Twelve trades are 74% of the money.** The 12 single-leg trades that rode to the clock make +$4,220
of the +$5,706. Strip-3 (+$3,506) and strip-5 (+$2,205) hold up, and strip-best-3-*days* holds up
(+$1,964), so it is not one session — but this is a lottery-ticket payoff shape and Garrath should
expect long dry stretches. **Win rate 40.7% is fine** (the desk's own best days run ~40%); the point is
the *distribution*, not the win rate.

**3. The exit is a hard clock.** Flat at 15:00Z, no target, no trail. That is not how any live gate on
this desk exits, and it means POPSAR gives back everything after 15:00 by construction. I tried
targets and trails — the grid in §4.2 shows tight targets take VPOP from +$3,123 to +$22. **The tail is
the edge and any exit that caps it kills the gate.** That is a genuine operational constraint, not a
preference.

**4. It does not do its job.** 2 of 16. Everything above is money made *somewhere else in the same
window*. If the objective is literally "catch the runs the census says we sat out", **this section is a
null** and I am saying so in the verdict.

**5. Parameters were chosen on the same 26 days that scored them.** The entry grid is a plateau (7/45
cells negative, median +$20.93/trade) and the exit grid is a plateau (0/20 cells negative), which is
the best defence available, but it is not the same as a held-out fit.

**6. Two soft results I am not hiding.** The +5min shift keeps 68% of the edge — the trigger minute is
not sacred. And 2× slippage scored *higher* than 1×, which is path noise at n = 54 and a reminder not
to read the last significant figure of anything here.

---

## 13. DISPOSITION TABLE

| lead | verdict | required next step |
|---|---|---|
| **The `OPEN/NEWS` label itself** | **REFUTED as a footprint** — it is `13 <= hour < 15`, true on 100% of its own window, with no news structure in the run-start distribution and an arbitrary 15:00 edge. | Rename to **US-OPEN**, move the clock test to LAST in `cluster()` so it stops pre-empting flow (31 of 94 in-window runs had a real flow verdict waiting), and extend the window to 16:00Z where lift is still 1.69×. |
| **The 13:00–15:00Z window** | **HELD** — 3.31× run lift, median run 110.8pt vs 87.5pt outside. | Keep hunting here. It is the right place. |
| **POPSAR** | **★ SHADOW** | Ship to the shadow book at max_trades = 5. Watch specifically: (a) does the reversal leg fill in live conditions, (b) does the OOS two-day concentration repeat, (c) how it behaves on a high-ATR week. **Promote at n ≥ 120 with strip-best-3-days still positive.** |
| **POPFADE** | **PARKED** | Revive at n ≥ 100, or if MGC shows the same failed-pop fade shape. Killed by strip-best-5 (−$29). |
| **POPGO** | **PARKED — superseded** | Revive only if the SAR's reversal leg turns out to be unexecutable live. |
| **SQZGO** | **PARKED** | Revive at n ≥ 40 — loosen the compression cut from the 33rd percentile to the median and re-run. |
| **ORX** | **REFUTED** | Parameter plateau (best cell's worst neighbour −$16.32/tr, 56/80 negative) + strip-3 (−$1,599). No reformulation of an opening-range break survives that surface. |
| **FBURST** | **REFUTED** | Placebo — 43.3% of coin flips beat it, and always-short beats it outright. |
| **VWRC** | **REFUTED** | Strip-best-5 → −$523. |
| **VSURGE** | **REFUTED** | Parameter plateau — sign flips between adjacent cells, no ridge; strip-3 → −$441. |
| **Pre-run VOLUME as a footprint** | **HELD — and it is the section's best raw finding** | AUC 0.703 → 0.769 → 0.848 → 0.883 as runs get bigger, monotone. Build a **rolling volume-vs-baseline z on the router's 1-minute grid** — it is the one measured-separation instrument the router does not have. |
| **Pre-run price range as a footprint** | **REFUTED** | AUC 0.49–0.57 at every size level. It knows nothing. |
| **A router condition for POPSAR** | **REFUTED for now** | Every ER and ATR arm condition benches profitable trades (+$2,368 at +$102.96/tr refused by the best one) and none is monotone. The clock is the arm condition. |
| **The 5s-bar look-ahead class of bug** | **ACTION, not a lead** | Audit every backtest on this desk that reads a bar's close/ATR/ER at the bar's own start timestamp. It was worth ~$700 and a fake regime edge in this section alone. |
| **Missing Sunday sessions in the parquet lake** | **ACTION** | 07-19, 07-26, 08-02, 08-09 have `capture.db` rows and no lake day-file, and `connect()` cannot reach them. Check `tape_mirror.py`. Harmless here, silently wrong for any overnight study. |

### The one stone still unturned

**The 15:00–16:00Z hour.** It carries a 2.04× and 1.69× run lift, it is where six of this week's runs
landed, and it is in UNCLASS purely because of a round number — so **no greenfield phase has ever
hunted it, in this report or any previous one.** POPSAR's own grid already prefers the 16:00 time stop
on several cells. That is where I would send next week's OPEN/NEWS agent first.

---

## VERDICT

**The cluster hunt: NULL.** No invented gate catches the runs the census says we sat out in the
OPEN/NEWS bucket. The best of nine candidates catches **2 of 16**, and the reason is now measured
rather than guessed: **11 of the 16 never produced an ignition bar at all**, because on a dead-vol week
the pre-run footprint is too weak to trip a mechanical trigger. The escalation to the biggest runs did
what the scope hoped and **found the footprint — pre-run VOLUME, AUC 0.703 across all runs rising
monotonically to 0.883 on the top 8 — establishing the size threshold at roughly 235 points of 15-minute
move.** But the one gate built directly on that footprint, VSURGE, was **killed by the parameter-plateau
test** (sign flips between adjacent grid cells, no ridge) and by strip-the-3-best (−$441). Detection is
real; direction and timing are not.

**One candidate survives, for a different job than the one it was hired for: POPSAR → SHADOW.**
54 trades, **+$5,706, +$105.66/trade, 40.7% win**, tick-honest on the parquet lake at $1.50/round-trip
per leg. It passed every kill test I have: 0 of 200 random-clock placebos beat it, 0 of 200 direction
coin flips beat it, all 20 cells of its stop × reversal grid are positive, strip-the-3-best leaves
+$3,506, strip-the-best-three-*days* leaves +$1,964, leave-one-day-out is negative on 0 of 24 days,
both halves are green, both sides pay, and it survives 4× slippage. It is held at SHADOW rather than
LIVE for one named reason: **its only true out-of-sample leg (15 untouched days) is +$1,807 but goes to
−$1,055 when its best two days are removed, with only 6 of 14 days green.**

**And the finding that outranks all of it: the `OPEN/NEWS` label is not a footprint. It is
`if 13 <= hour < 15`, evaluated before anything else, true on 100% of the bars inside its own window,
with no news structure in the run-start distribution (busiest slot 13:25, not 13:30) and an arbitrary
right-hand edge that dumps six of this week's runs into UNCLASS. The window is real — 3.31× run lift —
the label is just its name, and it has been stealing 31 of 94 in-window runs from VACUUM and FLOW-LED
since it was written.** Fixing that one line is worth more to next week's hunt than any gate on this
page.
