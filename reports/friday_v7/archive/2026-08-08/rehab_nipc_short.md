# REHAB — `nipc_short`

**Gate:** news-impulse pullback continuation, SHORT leg (`nipc_short_A` / `nipc_short_B`)
**Symptom on the roster:** 1 win in 16 (6%), 15 of 16 exits STOP, this-week P&L **−$337.00**
**Tape:** MNQ, 18 sessions 2026-07-15 → 2026-08-07 (11 tick-honest, 7 bar-replay) + the live ledger
**Costs:** $1.50 per **lot** per round trip (venue truth — every one of the 601 live rows is exactly 1.50), $2.00/pt, slippage a swept parameter
**Harness:** `scratchpad/nipc_rehab.py` + `scratchpad/nipc_eval.py`, driving the **shipped** `gazbot7.deciders.NipcTracker` (parity-checked below)
**Status of the gate right now:** `nipc_long=off`, `nipc_short=off`, both in `reactivate_gates.py::HOLD`

---

## VERDICT (up front)

> ### `nipc_short` → **SHADOW**. Do not re-arm on live capital.
> ### Separately → **FIX and SHIP the `lo` block to BOTH nipc legs in `data/exit_overrides.json`.** The operator's structural suspect was right, and it is the only change in this entire report that survives every robustness test — and it improves `nipc_long` more than it improves `nipc_short`.

The short leg is **not broken code and not the wrong rung**. It is a **real but sub-friction construct whose P&L is 53% explained by which way the tape happened to drift between 13:00 and 15:00 UTC.** It clears a random-entry null at only the 80th percentile (needs 95th), and it beats a one-line "sell at 13:00, cover at 15:00" null by $154 over 17 sessions while using **63 trades instead of 17**. Three of four ISO weeks are negative *in every single exit, stop, hold-cap and cost configuration I tested* — the entire positive number lives in 2026-W31, the one week the news window fell ~900 points.

Full reasoning in Movements 3–6. Exact configs in the Verdict section.

---

## 0. THE HARNESS, AND WHY YOU CAN TRUST IT

`scratchpad/nipc_rehab.py` drives the **actual shipped `NipcTracker`** — the same object `slot_strategy._nipc_step` feeds live — so there is no re-implementation to drift.

**Parity proof.** On the 6 bar-replay sessions where the shipped `scripts/nipc_replay.py` still runs, my harness reproduces it **trade-for-trade and dollar-for-dollar**:

| | 07-16 | 07-17 | 07-20 | 07-21 | 07-22 | 07-23 | total |
|---|---|---|---|---|---|---|---|
| `scripts/nipc_replay.py` | +402 / 17 | +53 / 14 | −260 / 16 | −80 / 16 | +110 / 14 | −68 / 14 | **+157 / 91** |
| `scratchpad/nipc_rehab.py` | +402 / 17 | +53 / 14 | −260 / 16 | −80 / 16 | +110 / 14 | −68 / 14 | **+157 / 91** |

### ⚠ TWO DEFECTS FOUND IN THE EXISTING TOOLING (report these, they poison future work)

**(a) `scripts/nipc_replay.py` is currently returning silent zeros.** `capture.db`'s ticks have been pruned back to 08-03; the harness's `TICK_DAYS` still names 07-24 … 07-31, so for those six days it takes the tick path, finds an empty tick list, and books **0 trades** with no error:

```
  2026-07-24:  3600 bars        0 ticks ->   0 trades        +0
  ... 07-27 .. 07-31 likewise
```

Every acceptance number in `deciders.py`'s NIPC header (`n=159 +$264`) and the 08-05 regime-filter attribution were computed when those ticks existed and **cannot be reproduced with today's tool**. My harness restores them from `data/tape/ticks/MNQ/*.parquet`. *Fix: fall back to the parquet archive, and raise if a TICK_DAY yields no ticks rather than booking zero.*

**(b) The replay was non-deterministic.** DuckDB's parallel parquet scan returns same-millisecond ticks in arbitrary order; the 1-second decision-cadence downsample keeps the **last** print per bucket, so tie order changed fills. The identical config re-measured **+$559 and +$639** on two runs. Pinned with `SET threads TO 1` + `preserve_insertion_order`; all three subsequent runs returned +$559 exactly. **Note the size of that: an $80 swing on 60 trades from tick tie-ordering alone — a useful yardstick for how much of everything below is noise.**

---

## MOVEMENT 1 — NORMALIZE THE MALFUNCTIONS

### Every fill was tape-consistent

I checked all 16 live legs against `capture.db` ticks in a ±1.5s window around the recorded exit. **No phantom prints, no synthetic fills.** The ledger is honest arithmetic. What is wrong with it is *provenance*, not *pricing*.

### M1 — TWO OF THE SIXTEEN ARE NOT `nipc_short` TRADES AT ALL

Trades **577 / 578** (08-06 13:47:28, −$17.50 / −$17.00):

```
exec_id                  order_id    side qty price     exec_time
0000e1a7.6a804e4d.01.01  stp-000001  SELL 1.0 29511.5   2026-08-06T13:47:28.807Z   <- ENTRY
0000e1a7.6a804e4e.01.01  stp-000002  SELL 1.0 29511.75  2026-08-06T13:47:28.865Z   <- ENTRY
0000e1a7.6a804ec0.01.01  stp-000007  BUY  1.0 29519.5   2026-08-06T13:48:04.248Z
0000e1a7.6a804ec1.01.01  stp-000008  BUY  1.0 29519.5   2026-08-06T13:48:04.290Z
```

Four independent confirmations that these are the 08-06 shared-account cascade, not signals:

1. **The order ids are `stp-*`, not `v7-mnq-*`.** Joining all 49 nipc entry legs to `fills` on `exec_time` (0 unmatched): **47 carry `v7-mnq-NNNNNN`, exactly these 2 carry `stp-*`.** `stp-*` is the *protective-stop* ref namespace. Two orphaned GTC stops fired with no position behind them and **opened** a naked 2-lot short — then two more orphans closed it.
2. **There is no `submitted` signal row.** All 47 other nipc entry legs have a `submitted` → `filled` pair in `signals`. These two have `filled` alone.
3. **No NIPC setup exists at that time.** Replaying 08-06 through the shipped tracker, the short setups are 13:08:22, 13:16:54, 13:34:17, 14:04:36, 14:25:12, 14:28:06. Nothing at 13:47.
4. **nipc was router-benched at 13:09 that day** (−$400 kill criterion hit). It could not have fired at 13:47.

This is exactly the incident already written up in `CLAUDE_snapshot_20260806.md` ("a leftover GTC stop from that mess fired with no position behind it, opened a naked short, and was booked as `nipc_short` — six and a half hours later") and the open gap in `broker_adapter.adopt_and_sweep`'s header: *the desk audits "does every SLOT have a live stop?" but never "does every live STOP have a slot?"*.

**Normalization: REMOVE. +$34.50 back to `nipc_short`; the −$34.50 belongs to the 08-06 incident ledger.**

### M2 — STOP_UNFILLED: the gate's ONLY green print should have been a stop

Trade **572** (08-06 13:04:34 `nipc_short_A`, +$28.50 TARGET) — the single winner the whole roster line rests on.

Reconstruction: A's target filled at 29367.75 from an entry of 29382.75 = **15.00 pt = 2.0R**, so **R = 7.50 pt** and its protective stop trigger sat at **29382.75 + 7.50 = 29390.25**.

The tape at 13:04:36.857 (from `capture.db` ticks):

```
13:04:36.856 29390.0   2.0 buy
13:04:36.857 29390.25  2.0 buy     <- AT the stop trigger
13:04:36.857 29390.25  2.0 buy
13:04:36.857 29390.25  1.0 buy
13:04:36.857 29390.0   1.0 buy     <- and away again, ~1 millisecond later
```

Price traded **at 29390.25 and never above it**. The venue's stop-limit did not trigger on a touch-without-through; the desk's own breach guard (`multislot_core:616`, `_last_price >= stop.stop_price`) *would* have fired it, but the desk reads one price snapshot per second (`DECISION_MS = 1000`) and the touch lasted about a millisecond.

Its twin **B** — same signal, same second, filled 2.75 pt lower at 29380.00 — had its stop at 29387.50, which the same burst breached at 13:04:36.143, and B was stopped out at 29388.50 (1.00 pt of stop slip) for −$18.50.

**Normalized (apply B's measured 1.00 pt stop slip to A):** fill 29391.25 → `(29382.75 − 29391.25) × 2 − 1.50` = **−$18.50**. Swing **−$47.00**.

> **The consequence is the headline of this whole report: normalized, `nipc_short` is 0-for-14. Its one green print was a single-millisecond, exactly-at-the-trigger touch that neither the venue's trigger rule nor the desk's 1-second breach guard happened to catch, on the lot that got the better of two fills 2.75 pt apart.** Every backtest in this report uses the `>=` convention (a touch fires the stop), so none of what follows leans on that tie.

### M3 — no naked rides, and one thing I could not audit

Holds: 3.4s, 3.7s, 4.1s, 4.1s, 26.7s, 26.8s, 53.4s, 53.5s, 116.7s, 116.8s, 15.8s, 16.6s, 3.6s, 85.2s. Nothing near the 20-minute cap or the 15:30 flat; no runaway. **⚠ Honest limitation:** `orders` holds no `stp-*` rows at all (protective stops are only visible via broker fills), so I **cannot** audit per-trade protective-stop coverage from the store. Stop coverage is asserted here only from the fact that 14 of 14 closed on a stop-shaped exit.

### M4 — a governance malfunction, flagged but NOT normalized away

On **08-03** the router logged `STAY-OUT 96/100 — 358pt box, day-ER 0.00, last-hr ER 0.18, 100% of last 12 trades stopped and every shadow strategy deeply red; all six tradeable gates already off … **nipc pair operator-pinned and out of scope**`. nipc took 3 of its 7 real signals that day, for **−$184.50**, on a tape the desk had already judged untradeable. That is not an execution fault and I have not credited it back — but it is why over half the live sample exists.

---

## MOVEMENT 2 — CORRECTED-COST RECONSTRUCTION

| step | n signals | n lots | net | TARGET | note |
|---|---|---|---|---|---|
| **Venue truth** (`gate LIKE 'nipc_short%'`) | 8 | 16 | **−$337.00** | 1 | as booked |
| − M1 orphan-stop naked entries (577/578) | 7 | 14 | **−$302.50** | 1 | not nipc signals |
| − M2 STOP_UNFILLED normalized (572) | 7 | 14 | **−$349.50** | **0** | **0-for-14** |
| − M4 signals the *currently shipped* regime filter would have blocked | **4** | **8** | **−$167.00** | 0 | see below |

**The M4 correction, itemised.** The 08-05 regime filter (`NIPC_REGIME_FILTER`, keep only `in-between-building` + `clean-trend`) shipped *after* the 08-05 session. Recomputing ATR1m/ER15 from the 5s bars at each live entry:

| id(s) | entry UTC | ATR1m | ER15 | regime | t.o.d. | pair P&L | shipped filter |
|---|---|---|---|---|---|---|---|
| 491/490 | 08-03 13:34:52 | 30.6 | 0.69 | clean-trend | us-session | −$60.00 | ALLOW |
| 494/495 | 08-03 13:43:16 | 55.5 | 0.08 | **violent-whipsaw** | us-session | −$77.50 | **BLOCK** |
| 503/502 | 08-03 14:05:02 | 37.7 | 0.32 | **violent-whipsaw** | us-session | −$47.00 | **BLOCK** |
| 542/543 | 08-05 13:17:24 | 9.6 | 0.43 | in-between-building | pre-open | −$30.50 | ALLOW |
| 558/557 | 08-05 13:50:30 | 44.8 | 0.18 | **violent-whipsaw** | us-session | −$58.00 | **BLOCK** |
| 572/571 | 08-06 13:04:34 | 13.8 | 0.37 | in-between-building | pre-open | −$37.00 † | ALLOW |
| 573/574 | 08-06 13:08:22 | 14.3 | 0.51 | in-between-building | pre-open | −$39.50 | ALLOW |
| ~~577/578~~ | ~~08-06 13:47:28~~ | — | — | — | — | ~~−$34.50~~ | **not a signal** |

† after the M2 normalization. Blocked total −$182.50; allowed total **−$167.00 on 4 signals**.

### The corrected cost picture — and why entry slippage does NOT show up where you expect

Measured from `signals` (`submitted.intended_price` → `filled.intended_price`, n=47 legs):

```
ALL     n=47  mean +1.191 pt adverse   median +1.25 pt   max +3.00 pt   (= 4.8 ticks mean)
SHORT   n=14  mean +1.161 pt           median +0.75 pt   max +3.00 pt
LONG    n=33  mean +1.205 pt           median +1.25 pt   max +3.00 pt
```

The max is exactly 3.00 pt because entries are capped marketable-limit IOC at `entry_limit_buffer_pts=3.0` — the cap is *binding*, which is itself the tell.

**The subtle part, stated precisely.** For a lot that stops out, entry slippage costs **zero dollars directly**: the desk arms `arm_stop(entry_price=slot.entry_price, atr=slot.entry_atr)`, i.e. `stop = fill ± R`, so the whole bracket *translates* with the fill and a stopped lot always books `−(R + stop_slip)×2 − 1.50` regardless of where it filled. Entry slippage bills you a different way — **it moves the stop 1.19 pt closer to the market and the target 1.19 pt further away, and pays out only in converted outcomes.**

08-06 13:04:34 is that mechanism caught on camera: same signal, same R = 7.50 pt, entries 2.75 pt apart, **stops on opposite sides of the same 3-second burst**, +$28.50 vs −$18.50 — a **$47 swing on one lot's fill quality**. Confirmed in the backtest, where moving the slippage assumption from the lab's 0.25 pt to the measured 1.25 pt costs the SHORT leg **−$570 over 63 trades (−$9.0/trade)** entirely through hit rate:

| adverse slip each side | SHORT leg net (n≈63) | $/trade | win% |
|---|---|---|---|
| 0.00 pt | +$1,142 | +17.8 | 45.3% |
| 0.25 pt *(the lab / shipped replay assumption)* | +$1,078 | +16.8 | 45.3% |
| 0.50 pt | +$872 | +13.6 | 43.8% |
| 1.00 pt | +$673 | +10.7 | 42.9% |
| **1.25 pt** *(measured live median — used everywhere below)* | **+$508** | **+8.1** | **41.3%** |
| 1.50 pt | +$316 | +5.1 | 38.7% |

**⚠ And this slippage is structural, not an execution bug.** NIPC's trigger is "price trades *through* the half-back level in the direction of the impulse" — to sell there you need a **stop-entry**. A resting limit is geometrically impossible (price arrives at the level from the wrong side). Stop orders always slip, and they slip most in exactly the fast tape the setup selects for. The only lever available is latency: `submitted → filled` is 120–170 ms, and a **server-side resting STP at `entry_level`** would remove that round trip — which is what the 0.50 pt row above is worth (+$364 vs 1.25 pt). That is a real, buildable improvement. It is also not remotely enough to change the verdict.

---

## MOVEMENT 3 — ROOT CAUSE: BASE, EXIT, or SIGNAL?

### It is NOT the EXIT. The rungs are approximately right.

The brief's structural suspect was that a 2.0R/2.5R pair on a gate stopping out 94% of the time means the targets are never consulted. **Measured, that is false.** Parking the target at 12R (one lot, so only the 1R stop / 20-min cap / 15:30 flat can close it) and reading the max favourable excursion *before* the stop:

| reached ≥ | SHORT (n=91) | LONG (n=97) |
|---|---|---|
| 1.0R | 50.5% | 52.6% |
| 1.5R | 41.8% | 40.2% |
| 2.0R | **36.3%** | 32.0% |
| 2.5R | **31.9%** | 29.9% |
| 3.0R | 28.6% | 24.7% |
| 4.0R | 22.0% | 15.5% |

31.9% of shorts reach 2.5R before their 1R stop. The rung is reachable. The **raw geometric expectancy per lot** (`P(T)·T − (1−P(T))·1`) is:

| target T | 1.0R | 1.5R | 2.0R | 2.5R | 3.0R | 4.0R |
|---|---|---|---|---|---|---|
| SHORT E, R per lot | +0.010 | +0.045 | +0.089 | **+0.117** | **+0.144** | +0.100 |

A shallow maximum around **2.5–3.0R** — the shipped 2.0/2.5 pair sits on that plateau. **The exit is not the disease.**

### It IS the BASE — the edge is smaller than the friction

Median R on the short book is **13.2 pt**, so 1R ≈ **$26.40** per lot.

```
gross edge per lot   = 0.117 R  x  $26.40   =  +$3.09
cost per lot         = $1.50 fee + 2 x 1.25pt x $2.00 slip  =  −$6.50
                                                              ---------
net per lot                                                    −$3.41
```

Even at the lab's fantasy 1-tick slippage the cost is $2.50/lot against a $3.09 gross edge. **`nipc_short` is a construct whose entire edge is the same order of magnitude as its execution cost**, and a *fixed-dollar* cost is a regressive tax on a gate whose R is small.

The mechanism predicts a cure: the edge only clears the cost when `0.117 × 2R > 6.50`, i.e. **R > 27.8 pt**. **Tested — and it is a NULL.** P&L by R bucket is non-monotone and swamped by variance:

| R bucket | 0–8 | 8–12 | 12–16 | 16–20 | 20–25 | 25–30 |
|---|---|---|---|---|---|---|
| SHORT net | −$355 | +$267 | −$394 | +$465 | −$67 | −$111 |
| n | 16 | 35 | 54 | 22 | 8 | 1 |

There is essentially no R region above 28 pt to trade (n=1), and the sign flips twice below it. **REJECTED — an R-size floor is not a fix.**

### And the SIGNAL is short-delta BETA, not alpha

This is the finding that decides the case. Per-session P&L of the shipped short leg against the 13:00–15:00 UTC drift:

| day | week | drift (pt) | SHORT $ | n |
|---|---|---|---|---|
| 07-16 | W29 | +42.5 | +4 | 4 |
| 07-17 | W29 | +61.2 | −154 | 4 |
| 07-20 | W30 | −133.0 | −69 | 4 |
| 07-21 | W30 | +64.8 | +34 | 2 |
| 07-22 | W30 | +223.8 | −103 | 2 |
| 07-23 | W30 | −189.8 | −63 | 4 |
| 07-24 | W30 | −142.5 | +54 | 2 |
| **07-27** | **W31** | **−520.5** | **+374** | 6 |
| **07-28** | **W31** | **−190.5** | **+243** | 5 |
| **07-29** | **W31** | **−308.2** | **+329** | 4 |
| 07-30 | W31 | +264.8 | +11 | 4 |
| **07-31** | **W31** | **−160.0** | **+208** | 4 |
| 08-03 | W32 | +342.2 | +7 | 3 |
| 08-04 | W32 | +346.5 | −56 | 1 |
| 08-05 | W32 | −67.5 | −322 | 5 |
| 08-06 | W32 | +257.8 | +47 | 2 |
| 08-07 | W32 | −123.5 | −34 | 7 |

```
corr(drift, SHORT P&L) = −0.528       <- half the daily variance is just direction
corr(drift, SHORT n)   = −0.640       <- it even TRADES MORE on down days
DOWN sessions (n=9): +$719      UP sessions (n=8): −$211
```

2026-W31's news window fell on four of five sessions (−520, −191, −308, −160; net −914 pt); 2026-W32's rose net +756 pt. That is the whole story of the "one good week".

### The two nulls

**NULL 1 — the dumb short.** Sell one lot at 13:00, cover at 15:00, same $1.50 fee and same 1.25 pt slip each side, no signal, no state machine, no regime filter:

```
dumb short, 17 sessions, 17 round trips :  +$354   ($20.8 per session)
nipc_short leg, same 17 sessions        :  +$508   over 63 trades / 126 lot round-trips
                                                    = $4.03 per lot round trip
```

**The entire NIPC apparatus buys $154 over a one-line rule, at 7× the execution surface and 7× the incident exposure.**

**NULL 2 — random entry.** 200 trials, same 13:00–15:00 window, same per-day trade counts, R drawn from the gate's own R distribution, same 2.0R/2.5R exits and 1R stop, same costs:

```
median −$185      5th pct −$1,305      95th pct +$1,107
nipc_short scores +$508  ->  80th percentile
```

**It does not clear the random-entry null at any conventional threshold (p ≈ 0.20).**

### ⚠ And a variance source bigger than the edge itself: SLOT CONTENTION

Rule 6 gives both nipc legs **one shared tracker and one position at a time**. Which setups the short leg gets therefore depends on what the *long* leg happened to be holding. Same tape, same costs, same exits, blanket book:

```
shorts with the LONG leg armed alongside :  n=136   −$194
shorts with the LONG leg NOT armed       :  n=151  +$1,638
overlap: 100 identical setups, identical P&L (+$764) on both sides
36 setups unique to the both-armed book  :  −$958
51 setups unique to the short-only book  :  +$874
```

**$1,832 of the answer — larger than any effect in this report — is decided by slot-contention luck.** (Mirror check: longs go +$278 → −$97 the other way. It is a coin flip, not a structure.) Everything below is therefore evaluated in the configuration the desk **actually runs**: both legs armed.

---

## MOVEMENT 4 — FILTERS: EVERY ATTEMPT, INCLUDING THE NULLS

Baseline throughout: **P0 = shipped policy** (detection-time block, keep `in-between-building` + `clean-trend`), both legs armed, 2 lots @ 2.0R/2.5R, slip 1.25 pt, 18 sessions. **SHORT leg: n=63, +$508, +$8.1/tr, 41.3% win, 22 TARGETs, gross-profit +$2,740.**

A filter that "wins" by throwing away the target winners is a fake win. Every candidate is scored on **how many of the 22 baseline TARGETs it keeps** and **how much of the baseline gross profit it retains**.

### 4a. The 22-filter battery (post-hoc vetoes on the same book, so the FILTER is isolated)

| veto | n | net | $/tr | keeps TGT | strip-3 | W29 / W30 / W31 / W32 | verdict |
|---|---|---|---|---|---|---|---|
| *(none)* BASE | 63 | +508 | +8.1 | 22/22 | **−90** | −150 / −148 / **+1164** / −359 | reference |
| ATR1m ≥ 25 | 40 | +732 | +18.3 | 16/22 | +134 | −210 / −157 / +1254 / −156 | W31-only |
| ATR1m ≥ 35 | 25 | +706 | +28.2 | 11/22 | +108 | −288 / −23 / +1056 / −38 | **drops half the winners** |
| ATR1m ≥ 40 | 13 | +475 | +36.6 | 6/22 | −122 | −132 / −149 / +775 / −19 | **FAKE — 27% of winners** |
| R ≥ 12 pt | 40 | +545 | +13.6 | 15/22 | −53 | −210 / −102 / +1163 / −307 | NULL |
| R ≥ 16 pt | 19 | +623 | +32.8 | 8/22 | +25 | −62 / −149 / +1006 / −172 | **FAKE — 36% of winners** |
| R 16–20 pt | 12 | +660 | +55.0 | **6/22** | +159 | −62 / −149 / +689 / +182 | **FAKE — keeps 36% of gross profit** |
| span ≥ 35 pt | 42 | +590 | +14.1 | 16/22 | −7 | −210 / −66 / +1111 / −245 | NULL |
| span 35–50 pt | 18 | +538 | +29.9 | 9/22 | +128 | +120 / +83 / +340 / −6 | see 4b — **knife-edge** |
| retrace ≥ 0.40 | 38 | +470 | +12.4 | 14/22 | −110 | −37 / −274 / +1110 / −328 | NULL |
| retrace ≥ 0.50 | 11 | +344 | +31.2 | 5/22 | −198 | +34 / −108 / +322 / +96 | **FAKE + fails strip** |
| ER15 ≤ 0.55 | 46 | +692 | +15.0 | 17/22 | +112 | −79 / −154 / +1161 / −236 | W31-only |
| regime = IBB only | 46 | +692 | +15.0 | 17/22 | +112 | −79 / −154 / +1161 / −236 | W31-only |
| 13:30 ≤ t < 14:30 | 30 | +907 | +30.2 | 14/22 | +310 | −81 / +144 / +1034 / −189 | W31-only |
| t ≥ 13:30 (US session) | 47 | +766 | +16.3 | 19/22 | +168 | −210 / −32 / +1213 / −206 | keeps winners; W31-only |
| rpos ≤ 0.20 (at the 60m low) | 34 | +475 | +14.0 | 13/22 | −123 | −82 / −132 / +1050 / −362 | NULL |
| rpos outside 0.2–0.5 | 56 | +776 | +13.9 | 21/22 | +178 | −150 / −75 / +1198 / −198 | W31-only |
| al60 ≤ 0 (impulse vs 60m drift) | 22 | +241 | +11.0 | 8/22 | −161 | −189 / +164 / +148 / +118 | fails strip |
| al15 ≤ −1 (a genuine reversal impulse) | 17 | +354 | +20.8 | 7/22 | **−50** | +60 / +57 / +29 / +208 | see 4b |
| ATR ≥ 35 AND retrace ≥ 0.40 | 18 | +553 | +30.7 | 8/22 | −27 | −158 / −76 / +825 / −38 | FAKE + fails strip |
| ATR ≥ 25 AND t ≥ 13:30 | 40 | +732 | +18.3 | 16/22 | +134 | −210 / −157 / +1254 / −156 | W31-only |
| ATR ≥ 35 AND IBB | 17 | +658 | +38.7 | 8/22 | +78 | −217 / −72 / +986 / −38 | FAKE |

### 4b. The two that looked alive — and both died

Only two filters were non-negative in all four ISO weeks. Both fail on inspection.

**`span 35–50 pt` — REJECTED, knife-edge.** Move either edge of the band 5 points and the result changes sign:

| band | n | net | strip-3 |
|---|---|---|---|
| 25–45 | 20 | +356 | **+4** |
| 30–50 | 21 | +650 | +240 |
| 35–45 | 13 | +240 | **−111** |
| 35–50 | 18 | +538 | +128 |
| 35–55 | 23 | +378 | **−32** |
| 35–60 | 28 | +235 | **−207** |
| 40–50 | 9 | +394 | **−16** |
| 35–∞ | 42 | +590 | **−7** |

No plateau — a two-sided band on a raw feature with n≈18 that flips sign in a ±5 pt neighbourhood. Classic overfit shape. And it keeps only 9/22 winners (45% of gross profit).

**`al15 ≤ −1` — REJECTED, but it is the most interesting lead in the file.** `al15` is the prior-15-minute drift measured in ATR units and signed *with* the impulse; `≤ −1` means the impulse ran **against** the preceding drift by more than 1 ATR — i.e. a genuine news shock that *turned* the tape, which is what the letters N-I-P-C are supposed to mean. It is the only filter positive in all four weeks **including the live one** (+60 / +57 / +29 / +208), 52.9% win, +$20.8/tr. It is not a knife-edge in the threshold either (the feature is bimodal: 17 shorts at ≤ −1, 45 at ≥ +2, one in between).

It dies on two tests. **(i) strip-the-best-3 = −$50** — all $354 is three trades. **(ii) It keeps only 7 of 22 winners and 29% of the gross profit**, which by the operator's own rule makes it a fake win. **(iii)** It does not generalise: the same rule on the LONG leg is +$46 on n=15. **REJECT as a rehab; carry as the one thing worth watching in shadow.**

### 4c. The operator's structural suspect — the missing `lo` block. **THIS ONE IS REAL.**

The brief's hypothesis: `nipc_short` is the only family besides `nipc_long` whose `exit_overrides.json` entry has no adaptive `lo` block, running a bare `{a_r 2.0, b 2.5}` while every mature gate carries `atr_split 22 + lo {a_usd 40, b_r 1.75, b_floor_usd 60}`.

Note the wrinkle that makes this *more* relevant than it looks: **NIPC carries `entry_atr = R`, not ATR** (rule 4 — that is how the pullback-extreme∓4pt stop reproduces without new exit machinery). So `atr_split=22` is tested against **R (median 13.2 pt)** and the clip binds on ~75% of fires. Under the clip, Lot A takes a fixed **$40 = 20 pt** and Lot B takes `max(1.75·R, $60 = 30 pt)`.

| config | n | net | $/tr | win | keeps TGT | strip-1 | strip-3 | strip-5 | W29 / W30 / W31 / W32 |
|---|---|---|---|---|---|---|---|---|---|
| **A.** bare `{a_r 2.0, b 2.5}` *(shipped)* | 63 | +508 | +8.1 | 41.3% | 22/22 | +272 | **−90** | **−410** | −150 / −148 / +1164 / **−359** |
| **B.** + `lo{22, $40, 1.75R, $60}` | 60 | +559 | +9.3 | 43.3% | **22/22** | +322 | **+118** | −76 | **−7 / −34 / +691 / −91** |
| **C.** B + entry ≥ 13:30 UTC | 47 | +649 | +13.8 | 46.8% | 19/22 | +413 | **+209** | **+15** | −99 / **+43** / +709 / **−4** |

**B keeps every one of the 22 baseline TARGET winners and 84% of the gross profit.** It does not win by cutting winners — it wins by *banking* more of them (win rate 41.3% → 43.3%), which is precisely what a fixed-dollar clip is for on a gate whose R is too small to pay an R-multiple ladder. And it collapses the week-concentration: W31 falls from 229% of net to 124%, W29 from −150 to −7, the live week from −359 to −91.

**Parameter plateau — it holds.** `b_r` swept 1.25 → 3.0: net +547 / +550 / +559 / +627 / +615 / +676 / +620, strip-3 positive at every value. `a_usd` swept $25 → $60: the optimum is a genuine hump at $35–$40 (+484 / **+559** / +417 / +399 / +426) with strip-3 turning negative on both shoulders — so $40 is on a real, if narrow, ridge, and it is **the same $40 the whole rest of the roster already uses**, not a fitted number.

**It generalises to the mirror leg** — the strongest evidence it is a mechanism and not a curve-fit:

| leg | bare | with `lo` |
|---|---|---|
| **LONG** | +$463, 43.3% win, strip-3 **−$5** | **+$668, 50.9% win, strip-3 +$332** |
| **SHORT** | +$508, 41.3% win, strip-3 **−$90** | +$559, 43.3% win, strip-3 **+$118** |

The `lo` block helps `nipc_long` *more* than it helps `nipc_short`.

### 4d. Exits, stops and holds — the sweeps the operator asked for, guess vs proven

**The Lot-A × Lot-B grid (SHORT, net $).** The desk's guess is A=2.0/B=2.5; the cheat-sheet's momentum prior is 1.5/2.5.

| A\B | 1.5 | 2.0 | 2.5 | 3.0 | 4.0 | 6.0 |
|---|---|---|---|---|---|---|
| 0.75 | −221 | +84 | +56 | +76 | +764 | +605 |
| 1.0 | −27 | +245 | +245 | +222 | +908 | +736 |
| **1.5** | −219 | +80 | **+193** | +187 | +820 | +620 |
| **2.0** | — | +327 | **+508** | +513 | **+1065** | +839 |
| 2.5 | — | — | +486 | +439 | +1093 | +840 |
| 3.0 | — | — | — | +365 | +1033 | +862 |

- **The operator's guess A=2.0 beats the cheat-sheet's momentum prior A=1.5 by $315 (+508 vs +193) at B=2.5.** The guess is CONFIRMED for the short leg, and it is the best A at every B.
- The LONG leg's optimum is different again (best cells at A=2.5–3.0 / B=3.0). **A single "proven pair" for both nipc legs was never justified.**
- **The apparent B=4–5R ridge is a mirage.** It is a *different book* (n drops 63 → 51 because the position is held longer and blocks later setups), and its per-week profile is identical to everything else: `B=5.0 → W29 −242 / W30 −24 / W31 +1840 / W32 −322`.
- **Lot B must NOT be a chandelier — confirmed independently.** Trailing Lot B at 0.75R / 1.0R / 1.5R gives +$1 / +$306 / +$429 against +$508 for the fixed 2.5R. The 08-01 finding holds.

**Stop width (SHORT):** 0.6× −128 · 0.8× +508 · **1.0× +508** · 1.25× +658 · 1.5× +876 · 2.0× +863. Wider looks better — and its per-week line is `1.5× → W29 −59 / W30 +372 / W31 +1100 / W32 −537`, i.e. it makes the live week **worse**. NULL.

**Break-even stops — all NEGATIVE, a clean failure worth recording.** BE after 0.5R: −$96. After 0.75R: −$60. After 1.0R: +$265. After 1.5R: +$65. All far below the +$508 baseline, all with strip-3 in the −$333 to −$640 range. A break-even stop on a gate that reaches 1.0R half the time and 2.5R a third of the time simply converts winners into scratches. **REJECT.**

**Hold cap:** 180s +708 · 300s +404 · 600s +412 · **1200s (shipped) +508** · 3600s +508. Non-monotone noise; the 20-minute cap binds on nothing (mean hold ~2 min). NULL.

---

## MOVEMENT 5 — ROBUSTNESS

### 5a. The finding that decides the case

**In every single configuration I tested — 9 Lot-B rungs, 7 A×B rows, 6 stop widths, 5 break-even variants, 3 trails, 5 hold caps, 7 slippage assumptions, 23 filters — 2026-W31 is positive and W29 / W30 / W32 are (almost always) negative.** A representative slice, the Lot-B sweep at A=2.0R:

| B | n | net | strip-1 | strip-3 | W29 | W30 | **W31** | W32 |
|---|---|---|---|---|---|---|---|---|
| 2.0 | 65 | +327 | +118 | −186 | −118 | −169 | **+922** | −307 |
| **2.5** | 63 | **+508** | +272 | **−90** | −150 | −148 | **+1164** | **−359** |
| 3.0 | 63 | +513 | +250 | −134 | −42 | −176 | **+1143** | −412 |
| 3.5 | 57 | +1016 | +726 | +302 | −46 | −124 | **+1527** | −342 |
| 4.0 | 51 | +1065 | +748 | +284 | −24 | −144 | **+1599** | −365 |
| 4.5 | 51 | +1212 | +868 | +364 | −85 | −118 | **+1759** | −344 |
| 5.0 | 51 | +1253 | +881 | +348 | −242 | −24 | **+1840** | −322 |
| 6.0 | 49 | +839 | +413 | −185 | −242 | −494 | **+1962** | −388 |
| 8.0 | 47 | +388 | −24 | −668 | −302 | −424 | **+1502** | −388 |

Even at **zero slippage** the picture does not change: W29 −148, W30 +45, W31 +1,328, W32 −83.

### 5b. Strip-the-best

The shipped short book is **+$508 on 63 trades, and −$90 after removing its 3 best trades.** Its top 8 winners: seven of eight are in W31.

| candidate | net | strip-1 | strip-3 | strip-5 |
|---|---|---|---|---|
| A. shipped bare | +508 | +272 | **−90** | **−410** |
| B. + `lo` block | +559 | +322 | +118 | −76 |
| **C. B + t ≥ 13:30** | **+649** | **+413** | **+209** | **+15** |

**C is the only configuration in this entire report that survives strip-the-best-5.**

### 5c. Leave-one-day-out

| candidate | days green | worst LODO fold |
|---|---|---|
| A. shipped bare | 10/17 | drop 07-27 → **+$134** |
| B. + `lo` | 10/17 | drop 07-29 → +$252 |
| C. B + t ≥ 13:30 | 11/17 | drop 07-29 → +$321 |

LODO is the one test all three pass — and it passes them for the wrong reason: with 17 sessions, dropping one day cannot dislodge a result carried by five.

### 5d. Out-of-sample: fit on W29–W31, apply unchanged to W32 (the live week)

**Every train-argmax loses money out of sample.** 13 of 13 filters, 8 of 8 rungs, 5 of 5 stop widths:

| family | train-argmax | TRAIN | **OOS W32** |
|---|---|---|---|
| Lot-B rung | B = 5.0R (+1575) | +1575 | **−322** |
| stop multiple | 1.5× (+1413) | +1413 | **−537** |
| entry veto | 13:30–14:30 (+1096) | +1096 | **−189** |
| *(none — shipped bare)* | — | +867 | **−359** |
| **`lo` block (B)** | — | +649 | **−91** |
| **`lo` + t ≥ 13:30 (C)** | — | +653 | **−4** |

The only two configs that come back roughly flat out of sample are the two that were **not** fitted on the training window — the `lo` block is copied verbatim from the mature gates and the 13:30 cut is the US cash open.

The 13:30 cut has a genuine plateau (13:15 +584 · **13:30 +649** · 13:45 +638), collapsing only at 14:00 (+160, strip-3 −126). It also matches the desk's own prior that the big runners live post-13:30 UTC. But note where it lands the live evidence: of the 4 surviving real live signals, **three were pre-13:30**, so under C the live week has **n = 1**.

### 5e. Cross-regime and time-of-day (the segmentation the discipline demands)

Blanket book, both legs armed, slip 1.25 pt, 18 sessions:

| segment | SHORT n / net / $tr / win | LONG n / net / $tr / win |
|---|---|---|
| dead-chop / pre-open | 16 / −110 / −6.9 / 31% | 17 / +150 / +8.8 / 53% |
| dead-chop / us-session | 5 / −309 / −61.8 / 0% | 5 / −24 / −4.8 / 40% |
| normal-chop / us-session | 11 / −446 / −40.5 / 9% | 8 / +126 / +15.8 / 38% |
| **violent-whipsaw / us-session** | **52 / +638 / +12.3 / 42%** | 50 / −464 / −9.3 / 34% |
| in-between-building / pre-open | 13 / −216 / −16.6 / 31% | 10 / +93 / +9.3 / 50% |
| **in-between-building / us-session** | **22 / +344 / +15.7 / 50%** | 18 / +182 / +10.1 / 39% |
| clean-trend / pre-open | 2 / +156 / +78.1 / 100% | 1 / −38 / −37.5 / 0% |
| clean-trend / us-session | 15 / −252 / −16.8 / 27% | 17 / +293 / +17.2 / 41% |
| **ALL** | **136 / −194 / −1.4 / 36%** | 127 / +278 / +2.2 / 39% |

**On this tape the shipped regime filter is close to backwards for the SHORT leg specifically.** It keeps `clean-trend/us-session` (−$252) and `in-between-building/pre-open` (−$216) while blocking `violent-whipsaw/us-session` (+$638) — the largest and best short bucket. For the LONG leg it is roughly right (clean-trend +$293 kept, violent-whipsaw −$464 blocked). The asymmetry reads sensibly: a news impulse **down** into a violent tape continues, and a short into a clean uptrend is counter-trend.

**I am not recommending acting on it, for three reasons that are worth stating rather than burying:**
1. The shipped filter's regime test lives in `_detect_impulse` and is **side-blind by construction** (side is computed *after* it). A side-specific rule can only sit at the trigger — and moving the block from detection to trigger is not a relabelling, it changes the state machine's path. Measured: same allow-list, detection-time → SHORT +$508; trigger-time → SHORT **−$212**. A $720 swing from *where the identical rule is evaluated*.
2. The whole segmentation is measured on a window that overlaps the one that produced the filter.
3. `violent-whipsaw/us-session` P&L is, once again, a W31 artifact.

### 5f. Bar-replay vs tick-honest (honesty about the tape)

| | n | net | $/tr | win |
|---|---|---|---|---|
| tick-honest, 11 sessions (250 ms prints) | 100 | **+$2,046** | +20.5 | 47.0% |
| bar-replay, 6 sessions (4 synthetic prints/bar) | 51 | **−$409** | −8.0 | 33.3% |

⚠ The two halves disagree by $28/trade. The tick half is also the half that contains W31. Candidate **C restricted to tick-honest days only**: n=31, +$715, +$23.1/tr, 51.6% win, strip-5 +$81, days-green 8/11 — and per-week `W30 +10 / W31 +709 / W32 −4`. Same shape: one week.

---

## MOVEMENT 6 — VERDICT

### `nipc_short` → **SHADOW**

Not FIXED. Not REGIME-DEPENDENT. Not (quite) TRULY-RETIRE.

**Why not FIXED.** The best configuration I could build (C) makes +$649 over 18 sessions, of which **+$709 is one week**. It does not clear a random-entry null (80th percentile). It beats "sell at 13:00, cover at 15:00" by $154 while using 7× the trades. Its P&L correlates −0.53 with the session's own direction. Normalized, the live record is **0-for-14**. And $1,832 of the measurement — more than the entire effect — is decided by slot-contention luck.

**Why not REGIME-DEPENDENT.** The regime story is available (`violent-whipsaw/us-session` +$638) and I do not believe it: it is measured on the window that produced the current filter, it inverts if the identical rule is moved from detection-time to trigger-time (−$720), it cannot be implemented side-aware without changing the state machine's path, and it is W31 again underneath.

**Why not TRULY-RETIRE.** Three things are genuinely alive and cost nothing to keep watching:
1. The **`lo` block** is a real mechanism, plateau-stable, keeps 22/22 winners, and improves the LONG leg more than the SHORT one. It converts strip-3 from −$90 to +$118 and the OOS live week from −$359 to −$91.
2. The `t ≥ 13:30` cut has a plateau, matches the desk's standing prior, and is the only thing that survives strip-5 (+$15) and lands OOS at −$4.
3. `al15 ≤ −1` (the impulse *fights* the prior 15-minute drift — an actual news shock rather than a trend extension) is positive in all four weeks including the live one. It fails strip-3 and it is a fake win by the winner-preservation rule, so it is not a fix — but it is the one hypothesis in this file with a mechanism behind it that has not yet been falsified, and the shadow arm is where to find out.

### THE EXACT CONFIGS

**SHIP NOW — `data/exit_overrides.json`, both nipc legs** *(this is a config change with no arming implication; both gates stay off)*:

```json
  "nipc_long": {
    "a_r": 2.0, "b": 2.5,
    "atr_split": 22, "lo": { "a_usd": 40, "b_r": 1.75, "b_floor_usd": 60 }
  },
  "nipc_short": {
    "a_r": 2.0, "b": 2.5,
    "atr_split": 22, "lo": { "a_usd": 40, "b_r": 1.75, "b_floor_usd": 60 }
  }
```

Evidence: SHORT +508 → +559, strip-3 −90 → +118, OOS live week −359 → −91, keeps 22/22 winners. LONG +463 → +668, strip-3 −5 → +332, win 43.3% → 50.9%. `b_r` plateau-stable 1.25–3.0; `a_usd` on a ridge at $35–$40, the same $40 every mature gate uses. **Requires a tournament restart to apply** (overrides are read at slate build). Revert: delete the two keys.
⚠ Be aware of the wrinkle when reading it: for nipc, `atr_split` is compared against **R**, not ATR, because rule 4 carries `entry_atr = R`. That is what makes $40 a ~1.5R clip rather than a ~1.4R one. It is fine, but it is not what the field name says, and it should be commented where it is set.

**SHADOW ARM — do not put capital behind this:**

```
nipc_short   :  exit_overrides as above (lo block)
             +  entry window 13:30–15:00 UTC   (not 13:00 — the US cash open)
             +  regime allow-list unchanged (in-between-building, clean-trend, blocked at DETECTION)
             +  stop 1.0 x R, hold cap 20 min, flat 15:30 UTC  (all unchanged — every alternative was a null)
             +  log al15 (prior-15m drift / ATR1m, signed with the impulse) on every fire
```

Measured: n=47, +$649, +$13.8/tr, 46.8% win, keeps 19/22 winners, strip-5 +$15, LODO-worst +$321, OOS live week −$4.

**RE-ARM CRITERION (the whole point of the shadow).** `nipc_short` returns to live capital only when it prints **≥ 3 consecutive ISO weeks non-negative, at least one of which has a NET-UP 13:00–15:00 tape**, on ≥ 40 shadow fires. That is a direct test of the one thing that actually killed it: it has never yet made money in a week the market rose.

**LEAVE OFF** `nipc_long` as well for now — it is near-flat live (−$97.50 on 33) and it shares the tracker, so re-arming one changes the other's book by up to $1,800.

### THE FOUR THINGS TO FIX THAT ARE NOT ABOUT THIS GATE

1. **The inverse stop audit.** `broker_adapter.adopt_and_sweep` already names the gap; 08-06 13:47 is it firing. Nothing in the desk asks *"does every live STOP have a slot?"*. Two orphans opened a naked 2-lot short and it was booked to a gate that had been benched 38 minutes earlier. Until that audit exists, **any gate's ledger can be contaminated by another gate's garbage** — and this rehab would have started from a 6% hit rate on 16 trades instead of 0% on 14 if I had not checked the order-id namespace.
2. **The stop-trigger tie rule.** Trade 572 survived on an exactly-at-trigger touch. The desk's own guard uses `>=` but only sees one price per second. Either the guard needs the raw tape at the trigger level, or the venue stop needs to be placed one tick tighter — but **decide it deliberately**, because right now the rule is "whatever the paper engine happened to do", and it was worth $47 on a $337 ledger.
3. **`scripts/nipc_replay.py` books silent zeros** when `capture.db` ticks have aged out (see §0a). Point it at `data/tape/ticks/` and make an empty TICK_DAY raise.
4. **Pin the replay's tick ordering** (§0b) — `SET threads TO 1` + `preserve_insertion_order`. An $80-per-60-trades reproducibility band is larger than several of the effects people will try to measure with it.

---

## APPENDIX — THE FULL LIST OF THINGS THAT DID NOT WORK

Recorded because the trying is the point.

| # | attempt | result |
|---|---|---|
| 1 | R-size floor derived from the cost mechanism (`R > 27.8 pt`) | **NULL** — n=1 above the threshold, sign flips twice below it |
| 2 | ATR1m ≥ 40 | FAKE — keeps 6/22 winners |
| 3 | R ≥ 16 pt / R 16–20 pt | FAKE — keeps 8/22 and 6/22; 36% of gross profit |
| 4 | span ≥ 35 pt | NULL (strip-3 −7) |
| 5 | span 35–50 pt | REJECTED — knife-edge, sign flips within ±5 pt |
| 6 | retrace ≥ 0.40 | NULL (strip-3 −110) |
| 7 | retrace ≥ 0.50 | FAKE + fails strip |
| 8 | rpos ≤ 0.20 (short at the 60m low) | NULL (strip-3 −123) |
| 9 | al60 ≤ 0 (impulse vs 60m drift) | fails strip-3 (−161) |
| 10 | al15 ≤ −1 (counter-drift reversal impulse) | 4/4 weeks positive, but strip-3 −50 and keeps 7/22 winners → **FAKE WIN, rejected**; kept as the shadow's watch-item |
| 11 | ER15 band 0.15–0.45 | identical to "IBB only"; W31-only |
| 12 | Lot B chandelier / trail at 0.75R, 1.0R, 1.5R | +$1 / +$306 / +$429 vs +$508 fixed — **the 08-01 finding confirmed, do not trail Lot B** |
| 13 | Break-even stop at 0.5R / 0.75R / 1.0R / 1.5R | **all four NEGATIVE or far below baseline**; strip-3 −333 to −640 |
| 14 | stop width 0.6× / 0.8× / 1.25× / 1.5× / 2.0× R | wider looks better in aggregate and makes the LIVE week worse (1.5× → W32 −537). NULL |
| 15 | hold cap 3 / 5 / 10 / 60 min | non-monotone noise; the cap binds on nothing |
| 16 | Lot-B rung 3.5R–5.0R (the apparent sweep optimum) | mirage — different book (n 63→51), same W31-only per-week profile |
| 17 | cheat-sheet momentum prior A=1.5R | **WORSE than the operator's guess** (+193 vs +508) — the guess is confirmed, the prior is not |
| 18 | side-aware regime allow-list at trigger-time | −$720 vs the same list at detection-time — the placement, not the rule, carries the result |
| 19 | short-leg-only book (unshare the tracker) | +$1,638 vs −$194 — real, but it is contention luck, not edge; the mirror flips the same way |
| 20 | zero-slippage counterfactual (perfect execution) | +$1,142 — still W29 −148 and W32 −83. Even free execution does not fix it |

**Two things worked, and one of them is not about the short leg at all:** the `lo` block (a mechanism, plateau-stable, keeps every winner, helps `nipc_long` more) and the 13:30 UTC entry cut (a plateau, the only survivor of strip-5). Neither makes `nipc_short` a gate. Together they make it cheap enough to keep watching.
