# REHAB — `grind_long`

**Gate:** VWAP trend-continuation, LONG leg (`grind_long_A` / `grind_long_B`)
**Symptom on the roster:** 1 win in 6 legs, all 5 losses `STOP`, `grind_long_B` 0-for-3, this-week P&L **−$172.00**
**Tape:** MNQ, 21 sessions 2026-07-15 → 2026-08-07 — **11 tick-honest** (07-24, 07-27…07-31, 08-03…08-07) + **10 bar-replay** held back as an out-of-sample leg
**Costs:** $2.00 / point, **$1.50 per lot per round trip** (venue truth), stop slippage a swept parameter
**Harness:** `scratchpad/grind_core.py` + `scratchpad/grind_run.py`, driving the **shipped** `gazbot7.deciders` objects (`gate_grind`, `compute_features`, `exit_chandelier_lock`, `exit_chandelier`) — no re-implementation to drift
**Switch state right now:** `grind_long=off` (benched 2026-08-07 22:05Z at the Paris reopen)

---

## THE VERDICT, UP FRONT

> ### `grind_long` → **FIXED — but the fix is one number, and it is not the one anybody has been arguing about.**
>
> **Raise the ATR floor from 10 back to 22, and loosen the extension ceiling from 2.0 back to 3.0.**
> Everything else — the exit, the chandelier, the lock, the stop, the 2-lot split — is fine and should not be touched.
>
> On the 11 tick-honest sessions that turns **+$1,930 across 744 legs (10 of 11 sessions can't carry it — it dies at strip-best-5)** into **+$5,893 across 155 legs, still +$3,593 after you delete its five best trades**. On this week specifically it turns **−$288 into +$2,178**.

And a second verdict that is really about the desk, not the gate:

> ### The router is currently **inverted** on `grind_long`. This week the fixed gate made **−$211 in the ~45 minutes it was armed and +$2,388 in the four days it was benched.**

Three things I want to say plainly before the working, because they are the honest bits:

1. **The exit is not the problem and never was.** I tried seven different exit configurations on the losing population. All seven lose. You cannot exit your way out of an entry that has no runner in it.
2. **The ER floor everybody keeps re-proposing is a FAKE win, and I can now prove it twice.** An ER≥0.20 floor drops **17 of this gate's 19 real winners**, and — worse — its sign *flips* between the two halves of the tape. Deleting the floors on 08-01 was right.
3. **The 08-01 Saturday window made two changes to this gate. One was right and one was wrong, and I think we got them the wrong way round.** Dropping the ER floor: right. Dropping ATR 24→10 and adding `ext_hi 2.0`: both wrong, and together they are most of this gate's bleed.

---

## 0. THE HARNESS — AND EXACTLY HOW MUCH YOU SHOULD TRUST IT

I rebuilt the live `grind_long` pipeline from the shipped code rather than describing it:

| stage | what live does | where it comes from |
|---|---|---|
| entry | `gate_grind(slope_min=0.4, fast_slope=True, ext_lo=0.3, ext_hi=2.0)` LONG, on `Features` over the last 60 **completed** 1-min bars | `slot_strategy.tournament_slots` |
| floor | ATR14(1m) ≥ **10.0** pt | `deciders.ATR_FLOOR` |
| floor | ER floor: **none** (all deleted 2026-08-01) | `deciders.ER_FLOOR = {}` |
| size | 2 sub-slots × 1 lot (Lot A, Lot B), each independently one-position-at-a-time | scaleout slate |
| exit A | ATR≥22 → scalp 2.5R; ATR<22 → bank at **$40** of open profit (the quiet-tape clip) | `data/exit_overrides.json` |
| exit B | ATR≥22 → lock-chandelier `start_k 3.5 / lock_r 6.0 / lock_k 0.5`; ATR<22 → bank at max(1.75R, $60) | `data/exit_overrides.json` |
| stop | native **1.0 × entry ATR** protective STP on both lots | slate |
| cadence | decisions and managed exits on the 1-second grid; the resting stop on the raw tick (it is a broker order, not a decision) | `gazbot7.cadence` |

**Re-entry is modelled the way the desk actually behaves.** A slot that stops out re-arms on the next decision tick and can re-enter inside the same signal minute. That is not a modelling liberty — it is exactly what happened live on 08-05, where three entries went through in 177 seconds. Any harness that takes one trade per signal will understate this gate's churn by about 4×.

### Fidelity, measured three ways

**(a) Bar path vs tick path.** I replayed the same 11 tick sessions through the 5-second-bar path as well, because the 10 out-of-sample days only have bars. The gap is the honest error bar on every OOS number below:

| day | n tick | net tick | n bar | net bar | bar − tick |
|---|---|---|---|---|---|
| 07-24 | 56 | +666.6 | 52 | +702.2 | +35.6 |
| 07-27 | 50 | −149.4 | 52 | −145.5 | +3.9 |
| 07-28 | 80 | +980.7 | 82 | +836.2 | −144.6 |
| 07-29 | 66 | −176.8 | 60 | −335.5 | −158.7 |
| 07-30 | 86 | +667.8 | 81 | +770.4 | +102.6 |
| 07-31 | 81 | +228.8 | 80 | +493.5 | +264.8 |
| 08-03 | 65 | +668.8 | 72 | +369.9 | −298.8 |
| 08-04 | 60 | +455.5 | 66 | +457.4 | +1.9 |
| 08-05 | 59 | −456.7 | 52 | −257.0 | +199.7 |
| 08-06 | 71 | −188.8 | 73 | −240.2 | −51.3 |
| 08-07 | 70 | −766.4 | 70 | −393.1 | +373.3 |
| **total** | **744** | **+1929.9** | **740** | **+2258.3** | **+328.4** |

So the bar path runs about **17% optimistic in total and up to ±$370 on a single day.** Every OOS figure in this report carries that. It is not enough to overturn any conclusion below, but it is enough that I never lean on an OOS number alone.

**(b) Against the live ledger.** My reconstructed entry ATR sits within 1% of the live stop distance on the first pair of 08-05 (21.02 vs 21.25 pt) and up to 23% wide on the last pair (27.02 vs 20.75 pt). My harness therefore gives *slightly wider* stops than the desk did in the fast minutes — mildly forgiving. I stress-tested that directly (§5.5) and the answer holds at 3 pt of stop slip and $6/RT.

**(c) A vectorised second implementation.** For the placebo nulls I wrote a numpy replay and checked it against the exact loop on all 744 real trades: total delta **−$86.4 on +$1,929.9** (4.5%), 524 of 744 trades byte-identical. Good enough for null distributions, not used for any headline.

### What I could NOT measure — stated plainly

- **`signal_journal.suppressed_by` is NULL in all 596 rows**, so I cannot read from the store which grind fires were suppressed by which mechanism. Everything about "what the gate would have done unrouted" in this report is *reconstructed from the tape*, not read from a log.
- **`capture.db` ticks only go back to 08-03.** The 07-24…07-31 ticks come from `data/tape/ticks/MNQ/*.parquet`. 2026-08-07 exists in capture but **not** in the parquet archive — if that archive is ever the only source, 08-07 vanishes silently. Same failure family as the `nipc_replay.py` zero-rows defect.
- **`grind_short` has no live sample at all** in this window. Everything here is the LONG leg.

---

## 1. MOVEMENT 1 — NORMALIZE THE MALFUNCTIONS

**There are none.** This is the rare week where the software behaved and the strategy simply lost.

All six legs, audited tick-by-tick against `capture.db`:

| # | slot | opened → closed | entry → exit | P&L | reason | MFE | MAE | hold | entry on tape | exit on tape |
|---|---|---|---|---|---|---|---|---|---|---|
| 545 | grind_long_A | 13:33:24.23 → 13:33:30.56 | 29999.75 → 29978.50 | −44.0 | STOP | +2.25 pt | 24.25 pt | 6.3 s | ✔ | ✔ |
| 546 | grind_long_B | 13:33:24.29 → 13:33:30.60 | 29999.75 → 29978.50 | −44.0 | STOP | +2.25 pt | 24.25 pt | 6.3 s | ✔ | ✔ |
| 547 | grind_long_A | 13:33:51.53 → 13:35:53.52 | 29998.25 → 30021.25 | **+44.5** | TARGET | +24.75 pt | 20.00 pt | 122.0 s | ✔ | ✔ |
| 550 | grind_long_B | 13:33:51.53 → 13:36:21.24 | 29998.50 → 29981.00 | −36.5 | STOP | +24.50 pt | 32.75 pt | 149.7 s | ✔ | ✔ |
| 551 | grind_long_A | 13:36:05.61 → 13:36:21.80 | 29998.75 → 29975.00 | −49.0 | STOP | +5.50 pt | 38.50 pt | 16.2 s | ✔ | ✔ |
| 552 | grind_long_B | 13:36:21.74 → 13:36:24.85 | 29976.25 → 29955.50 | −43.0 | STOP | +0.75 pt | 35.50 pt | 3.1 s | ✔ | ✔ |

- **No `STOP_UNFILLED`.** Every stop fired and filled. (Contrast the 07-21/07-22 grind era, which was riddled with them.)
- **No naked rides, no system stops, no orphan `stp-*` entries.** All six entries carry `v7-mnq-*` order ids with a matching `submitted` → `filled` pair in `signals`. Every fill price printed on the tape inside ±1.5 s.
- **No cross-desk mis-attribution.** The two extra `v7-mnq-*` BUYs at 13:34:32 and the `stp-000011` sell at 13:36:11 belong to `nipc_long`, and I checked them off against trades 548/549. Nothing leaked into grind's line.
- **Longest hold 150 seconds.** No max-hold, no clock flat, no runaway.

**So nothing is credited back. The venue's −$172.00 is the strategy's −$172.00.**

### But there IS a malfunction — it is a governance one, and it is the whole week

`data/config_journal.jsonl` records the arming:

```
2026-08-05T13:33Z  APPLIED {grind_long: on, abs_veto_long: on, abs_veto_short: on, exhaustion_short: on}
2026-08-05T13:44Z  APPLIED {grind_long: off}   [OPERATOR INSTRUCTION "bench grind"]
```

**The entire week's `grind_long` sample is an 11-minute hand-armed window at the US open, on the one day of five that the gate loses money.** There was no durable-tick regime read behind the 13:33Z arm; it was a session override at the moment of the open. The badcall ledger's own standing rule — *"don't hand-toggle grind, it self-gates"* — was not honoured, and this is the third recorded time (§ledger 12:45 08-07, §ledger 15:49) that hand-arming grind into the open produced an immediate wall of stops.

**And the arming lag has a price I can put a number on.** The signal came off the 13:32 bar, which closed at 13:33:00. Price at that instant was **29956.50**. The desk did not fill until 13:33:24 at **29999.75** — a **43.25-point chase** into a window whose full 13:33–13:37 range was 109.75 pt. My harness, taking the identical signal at the legal first decision tick, banked **+$41.50 (A) and +$73.50 (B)**. Live, 24 seconds later, both lots took **−$44.00**.

**That single pair of legs is a $203 swing caused purely by when the switch got flipped, not by the gate.** It is 118% of the week's whole reported loss.

I am **not** normalizing it away — a chase you actually paid for is a real loss. But it belongs on the arming ledger, not on the gate's card.

---

## 2. MOVEMENT 2 — CORRECTED-COST RECONSTRUCTION

| step | n legs | net | note |
|---|---|---|---|
| **Venue truth** (`gate LIKE 'grind_long%'`, 08-03…08-07) | 6 | **−$172.00** | as booked, 1 TARGET / 5 STOP |
| − commission component | — | −$9.00 of it | 6 legs × $1.50; **5% of the loss**, not the story |
| − mechanical malfunctions | 0 | **−$172.00** | nothing to strip (Movement 1) |
| − the 43.25 pt arming chase on legs 545/546 | 2 | **+$31.00** if filled on time | i.e. the gate's own decision was worth +$31, the switch timing cost $203 |
| **Tick-honest, arming-neutral** | 6 | **+$31.00** | the number the *gate* earned; the desk banked −$172 |

And the counterfactual that actually matters — what the **unrouted** gate did across the whole week, entry-for-entry on the tick tape:

| config | n legs | net | win% | $/leg |
|---|---|---|---|---|
| **LIVE config, unrouted, whole week** | 325 | **−$287.70** | 30.5% | −$0.89 |
| **PROPOSED config, unrouted, whole week** | 59 | **+$2,177.50** | 35.6% | **+$36.91** |

So the honest framing of the week is not "grind lost $172". It is: **grind's live config would have bled $288 over the full week if left armed; the router held it flat for all but 45 minutes; and the fixed config would have made $2,178 over the same five days.**

---

## 3. MOVEMENT 3 — ROOT CAUSE: BASE, EXIT, or SIGNAL?

### 3.0 The regime segmentation, and where the cut points came from

Per the 07-31 backtest discipline, nothing below is a blanket cross-tape number. The tape is keyed on **ATR level + ER + range position**, and separately on **session** (overnight/pre-open vs US, ≥13:30 UTC). The cut points are **quantiles of this tape**, not guesses:

- ATR14(1m) percentiles across 23,520 minutes: p10 **8.4**, p25 **10.4**, p50 **13.5**, p75 **18.2**, p90 **25.6**
- ER30 percentiles: p10 **0.03**, p25 **0.08**, p50 **0.17**, p75 **0.28**, p90 **0.39**

| label | rule | share of all minutes |
|---|---|---|
| **clean-trend** | ER30 ≥ 0.45 | 5.9% |
| **building** | 0.25 ≤ ER30 < 0.45 | 25.0% |
| **high-vol expansion** *(the taxonomy calls it "violent-whipsaw")* | ER30 < 0.25 and ATR ≥ 22 | 9.4% |
| **normal-chop** | ER30 < 0.25 and 12 ≤ ATR < 22 | 32.4% |
| **dead-chop** | ER30 < 0.25 and ATR < 12 | 27.4% |

⚠ I am going to keep the label "violent-whipsaw" for consistency with the scope's vocabulary, but **it is a misleading name for what grind finds there** — on this tape that bucket is mostly the US-open volatility *expansion*, and it is where grind's entire edge lives. Read it as "high vol, no established direction yet".

### 3.1 The live config, cut by regime (11 tick-honest sessions, 744 legs, +$1,929.9)

| regime | n | net | win% | $/leg | strip-best-3 |
|---|---|---|---|---|---|
| high-vol expansion | 105 | **+$2,959.5** | 34.3% | +$28.19 | **+$1,502.0** |
| building | 50 | +$310.4 | 34.0% | +$6.21 | −$350.6 |
| dead-chop | 129 | +$56.6 | 32.6% | +$0.44 | −$143.9 |
| **clean-trend** | 14 | **−$673.3** | **0.0%** | −$48.09 | −$586.6 |
| **normal-chop** | 446 | **−$723.3** | 38.1% | −$1.62 | −$955.8 |

| session | n | net | win% | $/leg |
|---|---|---|---|---|
| overnight / pre-open | 471 | **−$1,608.9** | 33.3% | −$3.42 |
| US (≥13:30Z) | 273 | **+$3,538.9** | 39.6% | +$12.96 |

**One bucket carries the gate and one bucket is 60% of its trades.** High-vol-expansion/US alone is **+$3,195.9 on 85 legs**. Normal-chop/overnight is **−$1,025.0 on 310 legs**.

### 3.2 The exit mix says the shape of the edge out loud

| exit reason | n | net | $/leg |
|---|---|---|---|
| CHANDELIER | **16** | **+$3,951.5** | +$246.97 |
| TARGET | 245 | +$14,598.0 | +$59.58 |
| EOD | 9 | +$286.5 | +$31.83 |
| STOP | 474 | −$16,906.1 | −$35.67 |

**Sixteen chandelier exits — 2% of the trades — are 205% of the net.** Every single one of the eight biggest is Lot B, and every single one peaked at **6.1–6.8 R** — that is, right at the `lock_r = 6.0` step. The lock is doing exactly what it was built to do.

### 3.3 THE MECHANISM — and it settles base-vs-exit-vs-signal in one table

If the edge is the runner, then the only question that matters is: **when does a runner exist at all?**

| entry ATR band | n | net$ | mean R per trade | median MFE (R) | % reaching 2R | % reaching **4R** | % reaching 6R |
|---|---|---|---|---|---|---|---|
| 0–14 | 289 | −$36.5 | −0.010 | 0.95 | 20% | **0%** | 0% |
| 14–18 | 221 | −$1,428.9 | −0.204 | 0.60 | 4% | **0%** | 0% |
| 18–22 | 114 | +$308.8 | +0.058 | 1.08 | 1% | **0%** | 0% |
| 22–24 | 24 | −$328.8 | −0.284 | 1.15 | 33% | 4% | 0% |
| 24–32 | 53 | +$272.3 | +0.126 | 1.57 | 36% | **15%** | 4% |
| 32+ | 43 | **+$3,143.1** | **+0.903** | 1.44 | 47% | **16%** | **14%** |

> **Below an entry ATR of about 22, not one trade in 624 reached 4R. Above 24, one in six does.**

That is the whole gate in one line. `grind_long`'s edge is a >4R runner on Lot B. A runner is a *tape phenomenon*, not an exit phenomenon — it needs enough volatility that four risk units of room actually exist inside the next hour. Below ~22 pt of ATR that room does not exist, so 624 trades pay full friction for a payoff that is structurally unreachable.

**And the effect survives risk-normalisation**, which is the check that would have killed it: mean R-per-trade is −0.01 / −0.20 / +0.06 below ATR 22 and **+0.90 at ATR 32+**. It is not "bigger ATR means bigger dollars on the same edge". The edge itself is different.

### 3.4 Is it the EXIT? No — and here is the proof

I ran **seven** different exit configurations against the sub-ATR-18 population, which is where 73% of the trades and all of the bleed live:

| exit config on the **ATR<18** segment | n | net | win% | $/leg | strip-3 |
|---|---|---|---|---|---|
| LIVE (A $40 / B max(1.75R,$60) quiet clip) | 544 | −$1,078.9 | 34.6% | −$1.98 | −$1,283.9 |
| A 2.5R / B wide lock-chandelier | 422 | −$612.8 | 25.4% | −$1.45 | −$1,814.8 |
| A 3.0R / B wide | 414 | −$364.9 | 23.7% | −$0.88 | −$1,566.9 |
| A 2.0R / B wide | 439 | −$564.1 | 27.8% | −$1.29 | −$1,766.1 |
| A 1.5R / B 2.5R (the fader preset) | 520 | −$863.5 | 33.7% | −$1.66 | −$1,141.5 |
| A 2.5R / B tight k1.5 | 573 | −$1,206.8 | 40.8% | −$2.11 | −$1,496.3 |
| A 2.5R / B wide, stop 1.25×ATR | 340 | −$1,297.6 | 28.2% | −$3.82 | −$2,039.1 |

**Every one loses. There is no exit that rescues a low-ATR grind entry.** The best of them still bleeds $0.88 a trade over 414 trades.

> **Root cause: the BASE CONFIG — specifically the ATR floor.** Not the exit, not the signal geometry. The `gate_grind` shape is fine; it is being allowed to fire in tape where its payoff cannot occur.

### 3.5 The clean-trend embarrassment — flagged, not explained away

The one result I cannot make sense of and will not paper over: **grind_long is 0-for-14 in its own namesake regime.** All 14 clean-trend legs (ER30 ≥ 0.45) stopped:

| day | time | ATR | ER30 | ext | box position | MFE (R) | result |
|---|---|---|---|---|---|---|---|
| 07-31 | 13:38 ×3 pairs | 33.6 | 0.49 | 1.98 | 0.71 | 0.06 / 0.15 / 0.49 | STOP ×6 |
| 08-06 | 00:09, 00:10 | 17.6 / 17.4 | 0.73 / 0.76 | 1.12 / 1.24 | 0.83 / 0.90 | 0.51 / 0.26 | STOP ×4 |
| 08-07 | 00:06 ×2 | 13.7 | 0.98 | 0.85 | 0.82 | 0.26 / 0.95 | STOP ×4 |

n=14 across three episodes is far too thin to conclude anything, and I will not. What it *does* say is that **a high ER30 is not evidence for arming this gate**, which is the same message the ER sweep gives from the other direction. **This is the one stone left unturned** and it needs a genuine trend week to settle.

---

## 4. MOVEMENT 4 — FILTERS THAT KEEP THE WINNERS

### 4.1 First, name the winners

Nineteen legs cleared +$150. They are **284% of the book's net** — take them out and the live config is −$3,549.

| day | time | lot | P&L | exit | **ATR** | ER30 | ER15 | ext | box | session |
|---|---|---|---|---|---|---|---|---|---|---|
| 08-03 | 13:40 | B | +528.5 | CHANDELIER | **47.2** | 0.08 | 0.23 | 1.40 | 0.83 | US |
| 07-28 | 14:41 | B | +468.0 | CHANDELIER | **40.4** | 0.05 | 0.24 | 1.24 | 0.95 | US |
| 08-06 | 13:39 | B | +461.0 | CHANDELIER | **39.9** | 0.10 | 0.14 | 1.07 | 0.77 | US |
| 07-31 | 15:54 | B | +412.5 | CHANDELIER | **34.4** | 0.12 | 0.08 | 0.51 | 0.89 | US |
| 07-24 | 14:56 | B | +406.5 | CHANDELIER | **35.7** | 0.02 | 0.31 | 0.65 | 0.80 | US |
| 08-04 | 13:39 | B | +360.0 | CHANDELIER | **32.6** | 0.38 | 0.49 | 1.72 | 0.75 | US |
| 07-28 | 23:21 | B | +328.0 | CHANDELIER | **27.5** | 0.05 | 0.21 | 0.51 | 0.86 | US |
| 07-30 | 12:45 | B | +279.0 | CHANDELIER | **24.6** | 0.08 | 0.01 | 1.15 | 0.69 | ONP |
| 07-24 | 15:20 | A | +242.0 | TARGET | **47.9** | 0.17 | 0.16 | 1.73 | 0.63 | US |
| 08-03 | 13:40 | A | +239.0 | TARGET | **47.2** | 0.08 | 0.23 | 1.40 | 0.83 | US |
| 07-29 | 18:40 | A | +228.0 | TARGET | **45.2** | 0.06 | 0.47 | 1.86 | 0.89 | US |
| 07-30 | 20:04 | B | +224.5 | EOD | **36.0** | 0.20 | 0.31 | 1.69 | 0.66 | US |
| 07-28 | 14:41 | A | +212.5 | TARGET | **40.4** | 0.05 | 0.24 | 1.24 | 0.95 | US |
| 08-06 | 13:39 | A | +206.5 | TARGET | **39.9** | 0.10 | 0.14 | 1.07 | 0.77 | US |
| 08-03 | 14:05 | A | +188.0 | TARGET | **37.7** | 0.18 | 0.32 | 1.99 | 0.70 | US |
| 07-30 | 20:04 | A | +179.5 | TARGET | **36.0** | 0.20 | 0.31 | 1.69 | 0.66 | US |
| 07-24 | 14:56 | A | +178.5 | TARGET | **35.7** | 0.02 | 0.31 | 0.65 | 0.80 | US |
| 07-31 | 15:54 | A | +173.0 | TARGET | **34.4** | 0.12 | 0.08 | 0.51 | 0.89 | US |
| 08-04 | 13:39 | A | +163.5 | TARGET | **32.6** | 0.38 | 0.49 | 1.72 | 0.75 | US |

Read the ATR column. **Every single winner has entry ATR ≥ 24.6. Eighteen of nineteen are ≥ 27.5.** Now read the ER30 column: **thirteen of nineteen fired below ER30 0.15.**

### 4.2 The filter battery, scored on winners kept

| filter | n | net | win% | $/leg | strip-3 | LODO-min | days green | **winners kept** |
|---|---|---|---|---|---|---|---|---|
| **LIVE** (ATR≥10, ext≤2.0) | 744 | +$1,929.9 | 35.6% | +$2.59 | +$472.4 | +$949.2 | 6/11 | 19/19 |
| ❌ **ER floor 0.20** | 132 | **−$1,637.0** | 25.0% | −$12.40 | −$2,298.0 | −$1,892.0 | 2/11 | **2/19** |
| ❌ **ER floor 0.35** (the one deleted 08-01) | 24 | +$38.5 | 25.0% | +$1.60 | −$622.5 | −$365.8 | 2/4 | **2/19** |
| ⚠ ER **ceiling** 0.20 | 612 | +$3,567.0 | 37.9% | +$5.83 | +$2,109.5 | +$2,563.8 | 6/11 | 17/19 |
| ❌ ER15 floor 0.25 | 364 | −$942.1 | 32.1% | −$2.59 | −$1,936.6 | −$1,368.2 | 4/11 | 8/19 |
| ATR ≥ 14 | 455 | +$1,966.4 | 36.7% | +$4.32 | +$508.9 | +$1,047.4 | 7/11 | 19/19 |
| ✅ **ATR ≥ 18** | 234 | +$3,395.3 | 40.2% | +$14.51 | +$1,937.8 | +$2,513.6 | 8/11 | **19/19** |
| ✅ **ATR ≥ 20** | 163 | +$3,521.9 | 39.3% | +$21.61 | +$2,064.4 | +$2,616.4 | **9/11** | **19/19** |
| ✅ **ATR ≥ 22** | 120 | +$3,086.5 | 34.2% | +$25.72 | +$1,629.0 | +$2,034.5 | 6/11 | **19/19** |
| ✅ **ATR ≥ 24** (the pre-08-01 floor) | 96 | +$3,415.3 | 37.5% | +$35.58 | +$1,957.8 | +$2,269.8 | **19/19** | **19/19** |
| ATR ≥ 27 | 67 | +$3,197.8 | 37.3% | +$47.73 | +$1,740.3 | +$2,052.3 | 7/11 | 18/19 |
| ATR ≥ 32 | 43 | +$3,143.1 | 41.9% | +$73.09 | +$1,685.6 | +$2,371.2 | 7/11 | 17/19 |
| US session only | 273 | +$3,538.9 | 39.6% | +$12.96 | +$2,081.4 | +$2,338.6 | 7/11 | 18/19 |
| ATR≥24 AND US | 79 | +$3,082.8 | 36.7% | +$39.02 | +$1,625.3 | +$1,937.3 | 7/11 | 18/19 |
| ATR≥24 AND box 0.5–0.95 | 86 | +$3,668.2 | 39.5% | +$42.65 | +$2,210.7 | +$2,522.7 | 7/10 | 19/19 |
| ❌ box ≥ 0.85 ("buy the break") | 338 | −$515.3 | 32.2% | −$1.52 | −$1,723.8 | — | — | — |
| ❌ net30 > 0 | 572 | +$2,619.1 | 36.7% | +$4.58 | +$1,161.6 | +$1,701.6 | 8/11 | 17/19 |

### 4.3 ★ THE FAKE WIN, NAMED AND REJECTED

> **REJECTED — an ER floor on `grind_long`, at any level, in either direction.**

The ER≥0.20 floor is the textbook fake: it cuts the trade count by 82% and it "wins" by throwing away **17 of the 19 target winners**. It doesn't just fail the 15/17-winners rule, it fails it catastrophically — it keeps the two *smallest* winners and deletes every runner.

And the ER≥0.35 floor is worse than fake, it is **an illusion of a filter**: it admits 24 legs across four sessions, seven of which are one day. Its "+$38.5" headline is −$622.5 after strip-3.

**Now the part that makes this permanent.** Somebody will notice that an ER *ceiling* at 0.20 looks great in-sample (+$3,567, 17/19 winners kept) and propose that instead. Don't. **The ER filter's sign flips between the two halves of the tape:**

| ER filter | W29 | W30 | W31 | W32 |
|---|---|---|---|---|
| ER30 ≥ 0.20 | **+$543** | **+$1,016** | −$1,151 | −$405 |
| ER30 < 0.20 | −$1,170 | +$868 | **+$2,779** | +$117 |
| out-of-sample check (10 bar days) | ER≥0.20 = **+$1,640 / 61** | | ER<0.20 = **−$973 / 321** | |

In-sample the ceiling wins by $4,500. Out-of-sample the **floor** wins by $2,600. That is not a parameter with a robust optimum, it is a coin. **ER is not a usable discriminator for this gate in either direction, and this is now the second independent re-derivation to say so.** The 08-01 deletion stands, permanently — and the reason is *not* "the floor blocked profitable trades", it is "ER has no stable sign here at all".

### 4.4 The one filter that keeps everything: the ATR floor

`ATR ≥ 24` is the only filter in the battery that **cuts 87% of the trades and keeps 19 of 19 winners.** `ATR ≥ 18`, `≥ 20` and `≥ 22` also keep 19/19. That is what a real filter looks like: it removes population that had no path to the payoff, and touches nothing that did.

**Independent confirmation from a completely separate ledger.** `data/two_ratchet_shadow.json` has been recording 26 *live* `grind_long_B` trades since 07-26, with no involvement from my harness. Split its own rows by entry ATR:

| two_ratchet ledger, live rows | n | live net |
|---|---|---|
| entry ATR ≥ 22 | 14 | **+$262.5** |
| entry ATR < 22 | 12 | **−$233.0** |

and all three of its recorded runners (rMFE 4.20R, 5.21R, 4.75R) had entry ATR **24.8, 46.7, 33.8**. Live data, different tool, same answer.

---

## 5. MOVEMENT 5 — ROBUSTNESS

### 5.1 The parameter plateau — a 2-D grid, not a point

The discipline says prove a plateau, not a peak. ATR floor × extension ceiling, on the 11 tick-honest days:

**In-sample net ($)**

| ATR ≥ | ext≤1.5 | ext≤2.0 | ext≤2.5 | ext≤3.0 | ext≤4.0 | ext≤6.0 |
|---|---|---|---|---|---|---|
| 10 | 1935 | **1930 ← LIVE** | 2653 | 3637 | 2619 | 1990 |
| 14 | 2064 | 1861 | 2147 | 2406 | 1522 | 1474 |
| 18 | 2306 | 3122 | 3977 | 4713 | 4575 | 4703 |
| 20 | 2530 | 3318 | 3721 | 4765 | 5041 | 5233 |
| **22** | 2852 | 3872 | 4209 | **5893** | **6081** | 5981 |
| 24 | 2203 | 3121 | 3402 | 4543 | 4708 | 4424 |
| 27 | 2561 | 3085 | 3662 | 4314 | 4236 | 3960 |
| 32 | 2217 | 2878 | 2830 | 3262 | 3298 | 2803 |

**In-sample strip-best-3 ($)** — the number that matters

| ATR ≥ | ext≤1.5 | ext≤2.0 | ext≤2.5 | ext≤3.0 | ext≤4.0 | ext≤6.0 |
|---|---|---|---|---|---|---|
| 10 | 478 | **472 ← LIVE** | 1195 | 2180 | 1161 | 533 |
| 14 | 606 | 404 | 690 | 949 | 65 | 16 |
| 18 | 849 | 1664 | 2520 | 3255 | 3118 | 3246 |
| 20 | 1073 | 1861 | 2264 | 3307 | 3584 | 3776 |
| **22** | 1395 | 2414 | 2751 | **4436** | **4624** | 4524 |
| 24 | 745 | 1664 | 1944 | 3086 | 3251 | 2966 |
| 27 | 1104 | 1627 | 2205 | 2857 | 2779 | 2502 |
| 32 | 759 | 1420 | 1373 | 1804 | 1841 | 1346 |

**Out-of-sample net ($, the 10 bar-replay days)**

| ATR ≥ | ext≤1.5 | ext≤2.0 | ext≤2.5 | ext≤3.0 | ext≤4.0 | ext≤6.0 |
|---|---|---|---|---|---|---|
| 10 | 92 | **667 ← LIVE** | 485 | 980 | 776 | 550 |
| 18 | 139 | 525 | 319 | 221 | 645 | 881 |
| 20 | 384 | 653 | 446 | 579 | 692 | 1060 |
| **22** | 571 | 925 | 764 | **796** | 663 | 862 |
| 24 | 886 | 845 | 684 | **1086** | 1078 | 1549 |
| 27 | 452 | 365 | 203 | 214 | 275 | 500 |
| 32 | 583 | 382 | 221 | 355 | 137 | 122 |

**Runners captured (MFE ≥ 4R)**

| ATR ≥ | ext≤1.5 | ext≤2.0 | ext≤2.5 | ext≤3.0 | ext≤4.0 |
|---|---|---|---|---|---|
| 10 | 10 | **16 ← LIVE** | 17 | 18 | 19 |
| 20 | 10 | 16 | 18 | 19 | 19 |
| **22** | 11 | 17 | 19 | **21** | 21 |
| 24 | 9 | 15 | 16 | 18 | 17 |
| 32 | 5 | 7 | 8 | 8 | 8 |

**This is a plateau, not a spike.** Everything in the block ATR 18–24 × ext 2.5–6.0 is in-sample ≥ $3,400 and strip-3 ≥ $1,900; the OOS grid puts its own best in the same neighbourhood (22–24). The live cell sits in the worst corner of both. **I am recommending ATR≥22 / ext≤3.0 as the centre of the plateau, and the exact number is deliberately not load-bearing** — 20/24 and 2.5/4.0 all work.

### 5.2 The full robustness card for the proposed config

**`grind_long`: ATR floor 22, ext_hi 3.0, everything else unchanged.**

| test | LIVE config | **PROPOSED config** |
|---|---|---|
| 11 tick-honest sessions | +$1,929.9 / 744 legs / 35.6% | **+$5,893.4 / 155 legs / 38.7%** |
| $ per leg | +$2.59 | **+$38.02** |
| strip-best-1 | +$1,401.4 | **+$5,364.9** |
| strip-best-3 | +$472.4 | **+$4,435.9** |
| **strip-best-5** | **−$346.6** | **+$3,592.9** |
| leave-one-day-out (min … max) | +$949.2 … +$2,696.4 | **+$4,655.9 … +$6,244.8** |
| sessions green | 6 of 11 | **10 of 11** (only 08-05 red, −$351) |
| out-of-sample, 10 bar-replay days | +$667.2 / 382 | **+$796.0 / 92** |
| per ISO week (all 21 days) | W29 −628, W30 +1884, W31 +1628, **W32 −288** | **W29 +2, W30 +1503, W31 +1666, W32 +1960** |
| runners captured (MFE ≥ 4R) | 16 | **21** |
| placebo null (300 random-entry draws, same population, same exits) | 88th percentile — **does not clear** | **100th percentile** |

The two lines I would put most weight on: **it survives deleting its five best trades**, and **it is positive in all four ISO weeks** where the live config is negative in two.

### 5.3 The placebo null in full

"Is this just *be long in a high-ATR minute*?" I drew random long entries from exactly the minute-population each filter admits, matched the count, ran the same exits, 300 times:

| population | real | placebo mean | placebo sd | placebo p95 | real sits at |
|---|---|---|---|---|---|
| ATR≥10 (the LIVE floor) | +$1,929.9 (n=744) | −$568.9 | 2161 | +$3,053 | **88th pct** |
| ATR≥24, any session | +$3,415.3 (n=96) | +$263.5 | 1703 | +$3,145 | 97th pct |
| ATR≥24 AND US | +$3,082.8 (n=79) | +$369.8 | 1623 | +$3,141 | 95th pct |
| **ATR≥22 AND ext≤3.0 (proposed)** | **+$5,893.4 (n=155)** | +$632.8 | 2098 | +$4,205 | **100th pct** |

**The live configuration does not clear a random-entry null.** The proposed one clears it outright. That is the single most useful sentence in this section: the grind *geometry* is real, but only inside tape where it can pay.

⚠ Honest caveat: those standard deviations (~$1,700–2,100) are enormous relative to the means, because the placebo distribution has the same fat tail the strategy does. A 95th-percentile result on this distribution is worth less than a 95th percentile on a tight one.

### 5.4 Leave-one-day-out, in full

| day dropped | LIVE remaining | PROPOSED remaining |
|---|---|---|
| 07-24 | +$1,263.4 | +$5,212.8 |
| 07-27 | +$2,079.4 | +$5,814.2 |
| 07-28 | +$949.2 | **+$4,655.9** |
| 07-29 | +$2,106.7 | +$5,231.3 |
| 07-30 | +$1,262.2 | +$4,941.8 |
| 07-31 | +$1,701.2 | +$5,788.5 |
| 08-03 | +$1,261.2 | +$5,298.7 |
| 08-04 | +$1,474.5 | +$4,705.9 |
| 08-05 | +$2,386.7 | **+$6,244.8** |
| 08-06 | +$2,118.8 | +$5,276.2 |
| 08-07 | **+$2,696.4** | +$5,763.9 |

No single day is load-bearing for the proposed config. For the live config, three separate days each account for more than a third of the total.

### 5.5 Cost and timing stress

Everything here is on the proposed config, 11 tick-honest days:

| stop slippage | $1.50/RT | $3.00/RT | $6.00/RT |
|---|---|---|---|
| 0.0 pt | +$5,893 (strip-3 +$4,436) | +$5,661 | +$5,196 |
| 1.0 pt | +$5,703 | +$5,471 | +$5,006 |
| 2.0 pt | +$5,513 | +$5,281 | +$4,816 |
| 3.0 pt | +$5,323 (strip-3 +$3,866) | +$5,091 | **+$4,626 (strip-3 +$3,182)** |

**Quadruple the commission and add three points of stop slip and it still makes $4,626 with a $3,182 strip-3.** This is not a friction-marginal construct.

Entry-timing stress — because the live desk fills late, I re-ran with the decision clock pushed back:

| entry delay after bar close | n | net | $/leg | strip-3 |
|---|---|---|---|---|
| 0 s | 155 | +$5,893 | +$38.02 | +$4,436 |
| 5 s | 159 | +$4,861 | +$30.57 | +$3,408 |
| 10 s | 158 | +$4,950 | +$31.33 | +$3,307 |
| 20 s | 151 | +$5,794 | +$38.37 | +$4,170 |
| 30 s | 153 | +$5,586 | +$36.51 | +$3,967 |
| 60 s | 166 | +$4,399 | +$26.50 | +$2,817 |

Costs 15–25% and stays strongly positive. **The finding is not an artefact of first-tick entry.** (Worth noting against the 08-05 experience: a *systematic* delay is survivable; a 43-point chase in a 110-point window is not.)

---

## 6. THE R-TARGETS — SWEPT, NOT INHERITED

The regime→exit cheat-sheet says a trend gate gets **Lot A 2.5R and Lot B wide**. That is an operator prior. Here is what the tape says, scored on grind's home segment (ATR≥24, US) with the quiet-clip disabled so the R is a real R:

**Lot A scalp R**

| Lot A R | n | net | win% | $/leg | strip-3 | days green |
|---|---|---|---|---|---|---|
| 1.0 | 64 | +$6.7 | 48.4% | +$0.10 | −$281.8 | 7 |
| 1.5 | 57 | +$517.6 | 43.9% | +$9.08 | +$69.1 | 6 |
| 2.0 | 48 | +$971.9 | 41.7% | +$20.25 | +$396.9 | 7 |
| **2.5 (the guess)** | 44 | +$917.4 | 36.4% | +$20.85 | +$208.4 | 6 |
| 3.0 | 42 | **+$1,349.0** | 35.7% | +$32.12 | **+$503.5** | 7 |
| 3.5 | 41 | +$1,178.0 | 31.7% | +$28.73 | +$195.0 | 6 |
| 4.0 | 40 | +$1,271.0 | 30.0% | +$31.77 | +$205.5 | 6 |
| 5.0 | 40 | +$1,662.8 | 27.5% | +$41.57 | +$333.8 | 8 |

**Verdict on Lot A 2.5R: NOT PROVEN, but not wrong either.** 2.0–3.0 are indistinguishable at this n (44–48 legs), and 2.5 happens to sit in a small local dip. The real message is directional — **1.0R and 1.5R are clearly too tight for this segment** — and I would leave 2.5R alone rather than chase 3.0R on 42 trades.

**Lot B mode**

| Lot B | n | net | win% | $/leg | strip-3 |
|---|---|---|---|---|---|
| fixed 2.0R | 48 | +$971.9 | 41.7% | +$20.25 | +$396.9 |
| fixed 3.0R | 42 | +$1,349.0 | 35.7% | +$32.12 | +$503.5 |
| fixed 6.0R | 38 | +$1,992.9 | 23.7% | +$52.45 | +$234.9 |
| ❌ tight k1.5 chandelier | 67 | +$45.4 | 53.7% | +$0.68 | −$366.6 |
| ✅ **"wide" lock-chandelier (live)** | 39 | **+$1,950.6** | 33.3% | +$50.02 | **+$493.1** |

**Verdict: Lot B "wide" HOLDS.** It has the best strip-3 of any mode. Note the trap in that table — fixed 6.0R has a *higher* headline than wide but a strip-3 of only $235, i.e. it is three trades. And the **tight** chandelier — the mode the regime-3 selector would pick in chop — is a disaster here (+$45 headline, −$367 strip-3, 53.7% win rate that earns nothing). That is a direct warning about the adaptive_exit selector picking "tight" on a high-vol expansion.

**The chandelier internals** (home segment, Lot B):

| lock_r | net | strip-3 | | start_k | net | strip-3 | | lock_k | net | strip-3 |
|---|---|---|---|---|---|---|---|---|---|---|
| 2.0 | +776 | +67 | | 1.5 | +62 | −760 | | 0.25 | +2052 | +535 |
| 3.0 | +1402 | +483 | | 2.0 | +499 | −561 | | **0.50 (live)** | +1951 | +493 |
| 4.0 | +1114 | +135 | | 2.5 | +1295 | −108 | | 0.75 | +2074 | +507 |
| 5.0 | +1585 | +184 | | 3.0 | +1625 | +223 | | 1.0 | +1994 | +487 |
| **6.0 (live)** | +1951 | **+493** | | **3.5 (live)** | +1951 | **+493** | | 1.5 | +2023 | +525 |
| 8.0 | +2097 | −214 | | 4.0 | +1827 | +369 | | 2.0 | +3110 | +591 |
| 10.0 / none | +2528 | −159 | | 5.0 | +2031 | +331 | | | | |

- **`lock_r = 6.0` is VINDICATED — by robustness, not by headline.** Removing the lock entirely gives a bigger number (+$2,528) with a **negative** strip-3 (−$159): without the lock, the whole thing is three trades. 6.0 has the best strip-3 in the column.
- **`start_k = 3.5` HOLDS.** There is a plateau at 3.0–5.0 and a cliff below 2.5 (strip-3 goes negative). The guess is at the plateau's best point.
- **`lock_k` is NOT A LEVER.** Everything from 0.25 to 1.5 is +$1,950 to +$2,074 with strip-3 +$487 to +$535. It is flat. Leave it.

**Stop width — the one exit parameter that might actually be mis-set.** Deconfounded (targets held at a constant 2.5×ATR and lock at 6×ATR so only the stop moves):

| stop ×ATR | n | net | win% | strip-3 | per ISO week | OOS bar days |
|---|---|---|---|---|---|---|
| 0.75 | 97 | +$2,244 | 24.7% | −$103 | W30 +694 W31 +119 W32 +1431 | +$317 |
| **1.0 (live)** | 83 | +$2,868 | 34.9% | +$1,411 | W30 +773 W31 +1052 W32 +1043 | +$643 |
| **1.25** | 74 | **+$3,343** | 41.9% | **+$2,018** | W30 +562 W31 +1851 W32 +929 | **+$829** |
| 1.5 | 70 | +$1,704 | 41.4% | +$744 | W30 +317 W31 +1240 W32 +148 | −$21 |
| 2.0 | 61 | +$2,174 | 52.5% | +$1,329 | W30 +810 W31 +917 W32 +447 | +$269 |
| 2.5 | 59 | +$3,721 | 69.5% | +$3,013 | W30 +1220 W31 +927 W32 +1573 | +$137 |
| 3.0 | 59 | +$3,019 | 71.2% | +$2,311 | — | **−$465** |
| 4.0 | 57 | +$1,569 | 75.4% | +$872 | — | **−$857** |

**1.25×ATR is the only widening that improves in-sample strip-3 AND out-of-sample.** 2.5× looks spectacular in-sample and is worse than 1.25× out-of-sample; 3.0 and 4.0 go OOS-negative. And 1.5× *dips* between 1.25 and 2.0, which means the surface is noisy, not a clean plateau.

**Verdict: the 1.0×ATR stop is probably a touch tight, and 1.25× is a defensible SHADOW candidate — but it is not part of the recommendation.** One parameter change at a time, and the ATR floor is worth ten times as much.

---

## 7. THE SHADOW LEDGERS, RE-DERIVED

### 7.1 `two_ratchet_shadow.json` — still a null, and now I can say *why* it is a null

| | this week (08-03…07) | whole window (since 07-26) |
|---|---|---|
| trades reaching the ledger | **3** | 26 |
| runners (rMFE ≥ 4R) | **0** | 3 |
| runner-clips | **0** | **0** |
| live net | −$123.5 | +$29.5 |
| shadow (two-ratchet) net | −$143.0 | −$265.0 |
| max realised MFE this week | **1.17 R** | 5.21 R |

This week's three rows, in full:

| opened | ATR | rMFE | live | shadow | exit |
|---|---|---|---|---|---|
| 08-05 13:33:24 | 21.0 | 0.11 R | −$44.0 | −$43.5 | STOP |
| 08-05 13:33:51 | 21.0 | 1.17 R | −$36.5 | −$43.5 | STOP |
| 08-05 13:36:21 | 27.2 | 0.03 R | −$43.0 | −$56.0 | STOP |

**The verdict logic in the scope says: zero clips over a genuine trend week is EVIDENCE FOR reconsidering the two-ratchet. It does not apply, because this was not a trend week for grind — it was 177 seconds of tape.** The ledger did not fail to find a clip; it never got a candidate. Two of the three entries were at ATR 21.0, below the floor this report proposes.

But the ledger does deliver something it was not designed to: **its own 26 live rows are the independent ATR proof in §4.4** (ATR≥22 → +$262.5 / n=14; ATR<22 → −$233.0 / n=12; all three runners at ATR 24.8/33.8/46.7).

> **Disposition: two-ratchet stays SHADOW, unchanged, and the watch is now conditional — it is only meaningful on trades the new ATR floor would admit.** Under the proposed config, 14 of the 26 rows to date would have existed and all 3 runners would have. **Revive the question when the ledger has ≥ 10 runners under an ATR≥22 entry.**

### 7.2 `partial_shadow.json` — the 2R-partial, and the standing prior RESTORED

The brief flags that the partial is now +$307.5 better on mean over the window (−$1,074.9 vs −$1,382.4) with a shallower drawdown, which "quietly inverts the standing *variance lever, not a mean-raiser* prior". I re-derived it and **the inversion is an artefact of the broken entry gate.**

Of the 40 trades in the ledger, **only 10 have a non-zero delta at all**. Here they are, every one:

| date | entry ATR | baseline | partial | delta |
|---|---|---|---|---|
| 07-27 | 24.8 | +$66.0 | +$130.5 | **+$64.5** |
| 07-29 | 27.2 | +$356.0 | +$285.5 | **−$70.5** |
| 07-29 | 18.7 | +$79.0 | +$113.0 | +$34.0 |
| 07-30 | 21.6 | −$90.0 | +$40.0 | +$130.0 |
| 07-30 | 20.7 | +$22.0 | +$92.5 | +$70.5 |
| 07-30 | 14.1 | +$28.0 | +$69.5 | +$41.5 |
| 07-30 | 15.5 | −$65.4 | +$28.1 | +$93.5 |
| 07-30 | 46.7 | +$688.0 | +$529.5 | **−$158.5** |
| 07-30 | 39.9 | +$187.0 | +$252.0 | +$65.0 |
| 07-30 | 25.5 | +$126.0 | +$163.5 | +$37.5 |
| | | | **total** | **+$307.5** |

Look at where the money comes from and where it goes:

- **Both negative deltas are the high-ATR runners** (ATR 27.2 and 46.7): −$229.0. That is the tail forfeit, exactly as the standing prior predicts.
- **The positive deltas are dominated by the mid- and low-ATR trades** the new floor removes: the five rows at ATR 14.1–21.6 alone are **+$369.5**.

**Re-derive the ledger under an ATR≥22 entry floor and the partial's mean edge goes from +$307.5 to −$62.0.** In other words:

> **The 2R-partial's apparent mean-raising is created entirely by the low-ATR population this rehab is removing. Fix the entry and the standing "variance lever, not a mean-raiser" prior is restored — the partial costs about $62 of mean on the trades that will remain.**

This week the partial's delta was exactly $0.00 across 3 trades (baseline −$286.0 = partial −$286.0) because nothing came within a mile of 2R. That is a non-observation, not evidence.

> **Disposition: the 2R-partial stays SHADOW, and the operator's mean-vs-smoothness choice is UNCHANGED, not inverted.** Re-present it after 20+ trades under the ATR≥22 floor. ⚠ The ledger's `green_day_pct` and `green_week_pct` both read 0.0 for baseline *and* partial across 40 trades — that is a suspicious pair of zeros and the smoothness half of that file should be checked before anyone leans on it.

---

## 8. THE ROUTER — the finding I did not go looking for

`grind_long` was armed for roughly **45 minutes in a 120-hour week**, in four windows (08-05 13:33–13:44, 08-05 22:35–22:55, 08-07 12:45–13:05, 08-07 13:36–13:38), across **13 recorded switch changes** in `router_trial_log.txt` + `config_journal.jsonl`. Two of the four arms were operator session overrides, not durable-tick regime reads.

Now score the *fixed* gate against that arming schedule:

| | n legs | net |
|---|---|---|
| **inside the ~45 min it was ARMED** | 10 | **−$210.6** |
| **while it was BENCHED (the rest of the week)** | 49 | **+$2,388.1** |

Per day, with the switch state beside it:

| day | live switch state | n | net | win% | $/leg |
|---|---|---|---|---|---|
| 2026-08-03 | **OFF all day** | 8 | **+$594.7** | 37.5% | +$74.34 |
| 2026-08-04 | **OFF all day** | 9 | **+$1,187.5** | 66.7% | +$131.94 |
| 2026-08-05 | ON 13:33–13:44 + 22:35–22:55 | 16 | −$351.4 | 18.8% | −$21.96 |
| 2026-08-06 | **OFF all day** | 11 | **+$617.2** | 36.4% | +$56.11 |
| 2026-08-07 | ON 12:45–13:05 + 13:36–13:38 | 15 | +$129.5 | 33.3% | +$8.63 |

> **The router benched `grind_long` on all four days the fixed gate would have earned, and armed it for the eleven minutes on the day it lost. It is not slightly off — it is anti-correlated.**

I want to be careful about what that does and does not prove. It does **not** prove the router is a bad idea; on the *live* config it was roughly neutral this week (the unrouted live gate was −$288 all week, and the armed windows contributed −$30 of that). What it proves is that **the router's arming criteria and the gate's actual habitat do not overlap.** The router arms grind on *ER climbing + trend confirmation*; the gate's money is in **ATR ≥ 22 with ER *below* 0.25** — the US-open expansion, before any trend is provable. Those are close to opposite conditions.

That also lands directly on the Part 2.5 "arm for periods, not runs" contradiction, and on the "bench on a wall of stops" question. Two of my null tests speak to it:

| policy | n | net | $/leg | strip-3 |
|---|---|---|---|---|
| no cap (live behaviour) | 744 | +$1,929.9 | +$2.59 | +$472.4 |
| **cap at 4 entries per day per lot** | 88 | **−$1,645.7** | −$18.70 | −$1,869.2 |
| **cap at 2 entries per day per lot** | 44 | **−$810.2** | −$18.41 | −$1,024.7 |

A per-day entry cap **is** "bench after a wall of stops", mechanically. It costs **$3,576**. The reason is now obvious from §3.3: grind's runner almost always arrives *after* a cluster of stops in the same expansion — 08-05 13:36:32 is the pattern in miniature (four stops in 20 seconds, then a +$135 / +$95.5 pair off the same minute). **"Bench on losses" is refuted for this gate. "Arm on ATR" replaces it.**

---

## 9. ★ THE TRYING — EVERY ATTEMPT, INCLUDING ALL THE NULLS

Nothing here is hidden. Every entry-side idea I tested, on the whole tape (no ATR change) and stacked on the ATR≥24/US home segment. **OOS** is the 10 held-back bar-replay days.

| # | attempt | whole tape: n / net / strip-3 / OOS | on ATR≥24 & US: n / net / strip-3 / OOS | read |
|---|---|---|---|---|
| 0 | live base (ATR≥10, ext 0.3–2.0) | 744 / +1930 / +472 / +667 | 83 / +2868 / +1411 / +643 | the baseline |
| 1 | ext_hi **1.5** (tighter "not stretched") | 589 / +1935 / +478 / **+92** | 53 / +2048 / +591 / +678 | ❌ **NULL** — tightening further does nothing in-sample and kills OOS |
| 2 | ext_hi **3.0** | 1050 / **+3637** / **+2180** / **+980** | 108 / **+4248** / **+2790** / +884 | ✅ **the second real win** |
| 3 | ext_hi **4.0** (pre-08-01, no ceiling) | 1255 / +2619 / +1161 / +776 | 118 / +4413 / +2955 / +875 | ✅ works too; 3.0 better on the whole tape |
| 4 | ext_lo 0.8 (demand more separation) | 628 / +807 / **−651** / +863 | 81 / +2210 / +752 / +1009 | ❌ **FAILED** — strip-3 negative |
| 5 | slope_min 0.8 (steeper trend) | 343 / +1791 / +250 / **+37** | 50 / +1925 / +384 / +295 | ❌ **NULL** |
| 6 | slope_min 1.2 | 145 / +96 / **−1153** / **−1024** | 20 / +494 / −755 / −238 | ❌ **FAILED badly** |
| 7 | 60-bar slope (fast_slope OFF) | 823 / +1940 / +772 / **−1436** | 88 / +2341 / +1180 / **−1167** | ❌ **FAILED OOS** — `fast_slope=True` vindicated |
| 8 | **DWELL 2** (signal must hold 2 bars) | 504 / +296 / **−1273** / **−548** | 56 / +1311 / −259 / +105 | ❌ **FAILED** — the anti-churn idea does not work |
| 9 | DWELL 3 | 342 / +1393 / −26 / +220 | 46 / +1634 / +215 / +550 | ❌ **NULL** — no better than base |
| 10 | max 4 entries/day/lot | 88 / **−1646** / −1869 / +465 | 71 / +2081 / +624 / +445 | ❌ **FAILED** — this is "bench on a wall of stops" |
| 11 | max 2 entries/day/lot | 44 / **−810** / −1025 / +4 | 44 / +1786 / +328 / +70 | ❌ **FAILED** |
| 12 | box 0.5–0.95 (mid-upper of the 30m range) | 685 / +2489 / +1031 / **+1081** | 83 / +2897 / +1440 / +341 | ⚠ **MARGINAL** — helps on the whole tape, neutral on home |
| 13 | box ≥ 0.85 ("buy the break") | 338 / **−515** / −1724 / −641 | 48 / +618 / −591 / +144 | ❌ **FAILED** — do not chase the range high |
| 14 | volume ≥ 1.0× its 20-bar mean | 514 / +831 / **−555** / +1021 | 68 / +633 / −754 / +1420 | ❌ **FAILED** in-sample, wild OOS — noise |
| 15 | volume ≥ 1.5× | 178 / +339 / −755 / +141 | 34 / +335 / −733 / −163 | ❌ **FAILED** |
| 16 | ER15 floor 0.30 | 402 / +1170 / −122 / **−859** | 65 / +2556 / +1264 / +118 | ❌ **FAILED OOS** |
| 17 | ER30 ceiling 0.30 | 716 / +1966 / +508 / +644 | 75 / +2756 / +1299 / +640 | ❌ **NULL** — indistinguishable from base |
| 18 | ER30 floor 0.20 | 202 / **−533** / −1724 / +348 | 41 / +1036 / −156 / +717 | ❌ **FAKE WIN** — drops 17/19 winners (§4.3) |
| 19 | ER30 ceiling 0.20 | 612 / +3567 / +2110 / — | — | ❌ **REJECTED — sign flips OOS** (§4.3) |
| 20 | US-session-only clock | 273 / +3539 / +2081 / — | — | ⚠ **DROPPED** — once ATR≥22 is in, the clock adds nothing (see below) |
| 21 | net30 > 0 (must be up over 30 min) | 572 / +2619 / +1162 / — | — | ❌ **NULL** |
| 22 | stop 1.5 / 2.0 / 3.0 / 4.0 × ATR | — | see §6 | ❌ 1.5 dips, 3.0–4.0 **OOS-negative** |
| 23 | Lot B tight-k1.5 chandelier | — | 111 / +963 / +254 | ❌ **FAILED** |
| 24 | Lot B fixed 6.0R instead of the trail | — | 38 / +1993 / **+235** | ❌ **FAILED strip-3** — three trades |
| 25 | remove the `lock_r` step entirely | — | 34 / +2528 / **−159** | ❌ **FAILED strip-3** |
| 26 | seven exit configs on the ATR<18 population | see §3.4 | — | ❌ **ALL SEVEN LOSE** |
| 27 | **ATR floor 18 / 20 / 22 / 24** | see §4.2, §5.1 | — | ✅ **THE WIN** |

**On #20, the US clock.** It looked like a good idea for a long time and I ran it as a candidate. Once the ATR floor is in place it stops earning: proposed config **with** the clock is +$5,147.5/130 in-sample and +$685.1 OOS; **without** it is +$5,893.4/155 and +$796.0. The overnight segment under the new floor is **+$986.2 on 28 legs**. So the clock is dropped — one fewer knob, and it was only ever a proxy for "when is ATR high".

**Two things I could not test at all, stated as gaps:**
- **`grind_short`.** Zero live rows in the window. The two-sided-gate principle says its thresholds should be derived independently, and I have not done that. Not in scope here, but it means "grind" as a family is half-measured.
- **The `adaptive_exit` regime-3 selector.** It is `False` under the scaleout slate for the A/B sub-slots (the override file wins), so it never ran on these trades. Its *would-have* behaviour on the home segment is the "tight k1.5" row in §6 — **+$45 net, −$367 strip-3** — which is a warning, not a measurement.

---

## 10. VERDICT AND THE EXACT CONFIG

> # `grind_long` → **FIXED**

### The change — two numbers, both reverting a 2026-08-01 decision

**`src/gazbot7/deciders.py`**
```python
ATR_FLOOR: dict[str, float] = {"grind_long": 22.0, "capitulation_long": 10.0}
#   ^ was 10.0 (set 2026-08-01). Re-derived 2026-08-08 on 21 sessions (11 tick-honest
#     + 10 bar-replay OOS): below ~22pt of entry ATR, ZERO of 624 grind_long legs ever
#     reached 4R — the runner that carries this gate is structurally unavailable there.
#     ATR 18/20/22/24 is a genuine plateau (all keep 19/19 of the target winners);
#     22 is its centre. Revert: set back to 10.0.
```

**`src/gazbot7/slot_strategy.py`, the `grind_long` SlotSpec**
```python
params={"slope_min": 0.4, "fast_slope": True, "ext_hi": 3.0},
#   ^ ext_hi was 2.0 (added 2026-08-01, "don't buy what is already stretched").
#     Re-derived: 2.0 is the worst cell of the whole ATRxext grid, in-sample AND
#     out-of-sample. 3.0 keeps 21 runners vs 16 and adds ~$2,000 in-sample /
#     ~$130 OOS. 2.5-4.0 all work. Revert: set back to 2.0.
```

**Do NOT change:** the exit (`lock_r 6.0`, `start_k 3.5`, `lock_k 0.5` all survive their own sweeps), the 1.0×ATR stop (1.25 is a shadow candidate only), Lot A's 2.5R, `base_size=2`, `fast_slope=True`, `slope_min 0.4`, `ext_lo 0.3`.

**One cleanup that is now free:** with the ATR floor at 22, the `atr_split: 22` quiet-tape clip in `data/exit_overrides.json` becomes **completely inert for `grind_long`** — I verified it produces byte-identical results with the clip on and off (155 legs, +$5,893.4 either way). Leave it in as a fail-safe or delete the `lo` block for this gate; it makes no difference. It should stay for the other gates.

### What it is expected to do

| | LIVE config | **PROPOSED** |
|---|---|---|
| 11 tick-honest sessions | +$1,930 / 744 legs | **+$5,893 / 155 legs** |
| per leg | +$2.59 | **+$38.02** |
| after deleting its 5 best trades | **−$347** | **+$3,593** |
| sessions green | 6 of 11 | **10 of 11** |
| all four ISO weeks | 2 negative | **4 positive** |
| this week (08-03…07) | −$288 | **+$2,178** |
| trades per session | ~68 legs | **~14 legs** |

**A fifth of the trades, three times the money, and it stops being a churner.**

### What it does NOT do — the honest limits

1. **It does not save 08-05.** In the exact 13:25–13:50Z window the desk traded, the proposed config still loses **−$178** (vs −$59 for the live config unrouted, and −$172 actually banked). The US-open reversal that day beat every configuration I tested. The gain is on the four days grind was benched, not on the day it wasn't.
2. **n is not large.** 155 legs is 78 signals across 11 sessions. The runners that carry it are 21 events. Every conclusion here is a 3½-week, one-instrument, summer-tape conclusion.
3. **The clean-trend hole is real and unexplained** (0-for-14, §3.5).
4. **The OOS leg is bar-replayed**, worth ±17% and up to ±$370/day (§0a).
5. **The placebo distribution is fat.** 100th percentile of 300 draws sounds decisive; the sd of those draws is $2,098.

### Deployment shape

**Deploy the two-line config change on Saturday. Do NOT simultaneously change the router's arming rule** — that is a second, bigger change and it deserves its own week. Instead, run the fixed gate with a **simple arming rule that matches its measured habitat**:

> **Arm `grind_long` when 1-min ATR14 ≥ 22 pt. Bench it when ATR14 < 18 pt. Ignore ER entirely for this gate — in either direction.**

That is a hysteresis band on the one variable that survives every test, and it is the exact opposite of the ER-climbing criterion the router currently uses. If it is easier, the in-gate `ATR_FLOOR` already enforces the floor per-tick with no polling lag, so **the switch could simply be left ON and the floor allowed to self-gate** — which is what the badcall ledger has been saying about grind for two weeks.

---

## 11. DISPOSITION TABLE

| lead | verdict | detail / what would revive it |
|---|---|---|
| **`grind_long` ATR floor 10 → 22** | ✅ **LIVE** | Plateau 18–24, 19/19 winners kept, 4/4 ISO weeks positive, survives strip-5, clears a placebo null at the 100th pct, survives $6/RT + 3pt slip. Deploy Saturday. |
| **`grind_long` `ext_hi` 2.0 → 3.0** | ✅ **LIVE** | The 08-01 ceiling is the worst cell of the 48-cell grid in-sample and OOS. 2.5–4.0 all work; 3.0 is the centre. Deploy with the floor. |
| **`grind_long` stop 1.0 → 1.25 × ATR** | 🔵 **SHADOW** | Only widening that improves strip-3 AND OOS (+$2,018 / +$829 vs +$1,411 / +$643). Surface is noisy (1.5 dips). Revive as a live change if it holds on ≥ 40 more legs. |
| **`grind_long` Lot A 2.5R** | 🟡 **PARKED — unproven, keep as-is** | 2.0/2.5/3.0 indistinguishable at n=44. Revive with a proper answer when the home segment has ≥ 100 legs. |
| **Lot B "wide" lock-chandelier (`3.5 / 6.0 / 0.5`)** | ✅ **HOLD — not an action** | `start_k 3.5` and `lock_r 6.0` both have the best strip-3 in their own sweeps. `lock_k` is a flat parameter — leave it. |
| **`grind_long` ER floor (any level)** | ❌ **REFUTED** | Named tests: winner-keep (drops 17/19), per-ISO-week sign flip, out-of-sample sign flip. The 08-01 deletion is confirmed permanently. No reformulation saves it — the ER *ceiling* fails the same way in the other direction. |
| **"Bench grind after a wall of stops"** | ❌ **REFUTED** | Entry caps at 2 and 4 per day per lot cost $3,576 and $2,740 respectively. The runner arrives *after* the stop cluster. Named test: §8. |
| **DWELL requirement (2 or 3 bars) as the anti-churn fix** | ❌ **REFUTED for this gate** | DWELL-2 strip-3 −$1,273 and OOS −$548; DWELL-3 is a null. The churn fix is the ATR floor, which cuts trades 79%. |
| **`fast_slope=True`** | ✅ **HOLD — not an action** | Turning it off is in-sample neutral and OOS −$1,436. |
| **US-session-only clock on grind** | 🟡 **PARKED** | Earns nothing once ATR≥22 is in place (+$986 overnight under the new floor). Revive only if the overnight segment turns negative over ≥ 30 legs. |
| **box / range-position filter (0.5–0.95)** | 🟡 **PARKED** | Whole-tape positive (+$2,489 / strip-3 +$1,031 / OOS +$1,081) but neutral on the home segment. Revive as a second-order filter after the ATR floor has 4 weeks of live data. |
| **two-ratchet mop-up arm** | 🔵 **SHADOW (unchanged)** | Still 0 clips, but this week produced no candidate at all (3 trades, max 1.17R). Revive the question at **≥ 10 runners recorded under an ATR≥22 entry**. |
| **2R-partial (Lot A scalp / Lot B ride)** | 🔵 **SHADOW (prior RESTORED)** | Its +$307.5 mean edge is created by the ATR<22 population being removed; under the new floor it is **−$62.0**. It is a variance lever after all. Re-present after 20+ trades on the new floor. ⚠ audit the `green_day_pct = 0.0` fields first. |
| **Router arming criteria for `grind_long`** | 🟡 **PARKED — needs its own week** | Anti-correlated this week: −$211 armed / +$2,388 benched. The router arms on ER-climb; the gate earns at ATR≥22 with ER<0.25. Revive as the "ATR band, ignore ER" rule above once the config change has a fortnight of live data. |
| **`grind_long` in clean-trend (ER30 ≥ 0.45)** | 🟡 **PARKED — the one unturned stone** | 0-for-14, all stops, three episodes. Revive with a genuine multi-hour trend week; n=14 cannot settle it. |
| **`grind_short`** | 🟡 **PARKED — never measured** | Zero live rows in the window. The two-sided-gate rule says it needs its own independently-derived thresholds. Revive with a dedicated per-side sweep. |
| **`adaptive_exit` regime-3 selector on grind** | 🟡 **PARKED — a warning, not a finding** | Never ran (the override file wins). Its "tight" mode on grind's home segment is +$45 net / −$367 strip-3. Do not let it pick tight here. |

---

## 12. TOOLING DEFECTS FOUND ALONG THE WAY

These matter beyond this report:

1. **`data/tape/ticks/MNQ/` is missing 2026-08-07** while `capture.db` has it. Any harness that reads only the parquet archive silently loses the most recent session — the same class of defect as the `nipc_replay.py` zero-rows bug. `capture.db` ticks only reach back to 08-03, so **neither source alone covers the window; they must be unioned.**
2. **`signal_journal.suppressed_by` is NULL in all 596 rows.** Any statement anywhere about "which gate fires were suppressed and why" is currently unsupported by the store.
3. **`partial_shadow.json` reports `green_day_pct: 0.0` and `green_week_pct: 0.0` for both baseline and partial across 40 trades and five dates.** Two identical zeros on a metric whose whole purpose is to show a difference is more likely a bug than a result. **Do not quote the smoothness half of that file until it is checked.**
4. **`two_ratchet_shadow.json`'s `xcheck` field (−$406.0) disagrees with `live_net` (+$29.5)** by $435 with no documented reconciliation. Worth a look before the ledger is used to settle anything.

---

*Harness: `scratchpad/grind_core.py`, `scratchpad/grind_run.py`. Data: `data/capture.db` (5s bars 07-15…08-07, ticks 08-03…08-07), `data/tape/ticks/MNQ/*.parquet` (07-24, 07-27…07-31, 08-03…08-06), `data/gazbot7.db` (live ledger), `data/two_ratchet_shadow.json`, `data/partial_shadow.json`, `data/router_trial_log.txt`, `data/config_journal.jsonl`. All P&L tick-honest at $2.00/pt and $1.50/lot/RT.*
