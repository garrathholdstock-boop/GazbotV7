# REHAB — `exhaustion_short`

**Gate:** the flow-absorption reversal fade — heavy buying that fails to move price into a resting ask wall → SHORT (`exhaustion_short_A` / `exhaustion_short_B`)
**Symptom on the roster:** 2 wins in 6, this-week P&L **−$162.00**, of which `exhaustion_short_B` is **−$98.50 with 2 STOPs**
**Second symptom (the operator's real complaint):** the most mis-benched gate of the week — router 8 off / 5 on, with an explicit 2026-08-07T13:24Z operator carve-out saying a MOMENTUM direction rule was being applied to a FADER
**Tape:** MNQ. Six sessions replayed at full live fidelity (tick + dense L2 book): **2026-07-31, 08-03, 08-04, 08-05, 08-06, 08-07**. Five more (07-24, 07-27…07-30) at reduced fidelity. Plus the live ledger (75 lots since 07-21) and the 467-trade `exhaustion_rev` shadow book.
**Costs:** **$1.50 per lot per round trip** (venue truth — every one of the 75 live rows is exactly 1.50), **$2.00/pt**, entry slippage **0.75 pt** (measured: A/B-era mean +0.63 pt, median +0.25 pt), stop slippage 1.00 pt, all swept.
**Harness:** `scratchpad/exh_lib.py` + `scratchpad/exh_engine.py` (replay), `exh_analysis.py` / `exh_analysis2.py` / `exh_analysis3.py` (the battery). Raw output: `/tmp/exh_results.txt`, `/tmp/exh_results2.txt`, `/tmp/exh_results3.txt`.
**Status right now:** `exhaustion_short=on` in `gate_switches.env`, armed under the 13:24Z operator carve-out.

---

## VERDICT (up front, so you can stop reading here if you want)

> ### `exhaustion_short` → **PARKED**, and the router was **RIGHT**, not wrong.
> ### Two things to SHIP anyway, both worth real money and neither of them about arming:
> ### **(1) The exit is worse than the one we replaced it with.** Put `exhaustion_short` back on the fixed **8pt stop / 12pt target / 120s cap** it had on 07-25. On the same six days, same entries, the current `a_r 0.75 / tight-chandelier / atr_split 22` config loses **−$847**; the old fixed exit loses **−$243**. That is **$604 of pure exit damage in six days** and it applies to every future fire.
> ### **(2) A paper-account fill defect is inflating our losses, desk-wide.** Two stop-limit orders this week filled at their **limit price** — 20.00 pt through their own trigger — at prices the tape never printed. One was `exhaustion_short_B` on 08-07 (**−$78.00 booked, −$47.00 real**), the other was `abs_veto_short_B` on 08-06 (**−$84.00 booked, ≈−$45.50 real**). ≈**$70/week** of fake losses, and both happened in the first four minutes of the cash open.

**Why PARKED and not FIXED, in one paragraph.** The router's benching of this gate did not cost us money — measured window by window across the whole week, being benched **saved $140**. Left armed for the full 120 hours instead of the 10 it actually got, the gate would have lost **−$614** this week (mean over ten polling phases), and **−$847** over the six-day dense tape. And the reason is not the exit and not the config: it is the **signal**. Measured against a 200-trial placebo null, the entry is *significantly anti-predictive* at 30–120 seconds (0th–2nd percentile). The whole fade move happens inside the **five-second confirm window the desk itself waits through** — after that wait, the average forward drift is **zero to negative at every horizon out to five minutes.** Gross of costs the construct is worth about **+$1.36 a lot**; friction is **$3.28 a lot**. It is a real micro-effect with a half-life shorter than our own reaction time, and it is roughly **two dollars a lot short of the fee**.

**What would revive it (the PARKED condition, stated concretely):** a **zero-latency execution path** — fire and fill inside the 20-second window, not 5 seconds after it — *plus* a fee below ≈$0.50/RT. On the honest tape, the same trigger with a 10pt/5pt/30s scalp and **zero friction** makes **+$232 (8 of 10 phases green)**; with our real friction it makes **−$330**. That gap is the entire lead. Nothing about arming, benching, ER, ATR or regime closes it.

---

## 0. THE HARNESS, AND WHY YOU CAN TRUST IT

The replay drives the same logic the live desk does, in the same order: `footprint_summary` (20-second signed aggressor net, price move over that window, the level-1 book read) → `exhaustion_signal` (net ≥ 400, |move| ≤ 2 pt, ask wall ≥ 1.5× bid) → `veto_counter_regime` → the **5-second confirm-veto** → two independent sub-slots A and B with their own pending buffers → a native 1-ATR server stop checked on **ticks**, and the managed exits checked on the **1 Hz** decision grid, exactly as `md` publishes tape.

### Parity proof — it reproduces the live fills to the millisecond

The three signals the live desk actually confirmed this week all reproduce:

| live event | live time (submit) | replay signal | gap |
|---|---|---|---|
| `exh confirm: exhaustion_short_A/B held after 5s → OPEN @29714.25` | 2026-08-07 **13:30:48.657** | fires at **13:30:43.600** | +5.057 s (the 5s confirm) |
| `exh confirm: … held after 5s → OPEN @29719.0` | 2026-08-07 **14:48:15.819** | fires at **14:48:10.800** | +5.019 s |
| `exh confirm: … held after 5s → OPEN @29869.25` | 2026-08-05 **14:31:48.603** | fires at **14:31:43.6** | +5.00 s |

And the derived risk unit matches the venue to a fraction of a tick. The live stop orders (from the tournament journal) were placed at `auxPrice = entry + ATR`:

| live trade | entry | live stop trigger | implied R | replay ATR14 | error |
|---|---|---|---|---|---|
| 08-05 14:31:48 | 29867.75 | 29903.50 | **35.75 pt** | 35.6 pt | 0.15 pt (0.4%) |
| 08-07 13:30:48 | 29715.00 | 29733.25 | **18.25 pt** | 18.2 pt | 0.05 pt (0.3%) |

### ⚠ THE THING THAT MAKES THIS GATE HARD TO MEASURE — and it is a finding, not an excuse

**The trigger is a sub-second, knife-edge event, and the desk only looks once a second.** Slide the polling phase by 100 ms and you get a different set of trades. Here is the same config, the same six days, the same code — only the phase of the 1 Hz decision grid changes:

| phase (ms) | 0 | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900 |
|---|---|---|---|---|---|---|---|---|---|---|
| lots | 78 | 62 | 76 | 84 | 66 | 72 | 68 | 54 | 70 | 74 |
| net $ | −1,711 | −704 | −740 | −365 | −509 | −1,331 | −757 | −785 | −1,258 | −645 |

**Mean −$880, standard deviation $418, range $1,346.** That is the noise floor of every number in this report, and it is why **every headline below is the mean of all ten phases, with the spread quoted.** Any "improvement" smaller than about $800 over six days is inside the sampling noise of *when we happened to look at the book*.

The same instability shows up in the data source. On the days where we archived **both** the dense `md` book (~190 snapshots/sec) and the separate 250 ms depth capture, the identical config gives:

| day | dense md book | 250 ms depth archive | disagreement |
|---|---|---|---|
| 2026-07-31 | −$169 | +$149 | $318 |
| 2026-08-03 | −$234 | −$113 | $121 |
| 2026-08-05 | −$302 | +$189 | $491 |

Same tape, same gate, same exits. The only difference is which snapshot of the order book the poll happened to catch. **This is the single most important structural fact about `exhaustion_short`: its output is dominated by microstructure sampling luck.** It is also why the 07-24…07-30 leg below is labelled LOW FIDELITY and never used for a headline.

### ⚠ A REAL BUG FOUND IN THE SHIPPED GATE — the "level-1 book" is not the top of book

`capture.py:277` writes depth levels **0-indexed** (`enumerate(tkr.domBids)`), so level 0 is the best bid. `footprint._book_l1` reads **`level = 1`**. So the wall test that defines this gate — *"is there a resting wall on the side being hit?"* — has been comparing the sizes at the **second** price level, not the touch, for the gate's entire life.

I replayed it both ways. It does not rescue anything (true top-of-book is **worse**: −$1,265 vs −$847, and its 120s/300s forward drift is −0.35/−2.31 pt against the L2 read's +0.65/+2.70). But it means the mechanism as documented has never actually been tested, and anyone reading `footprint.py` is being told something untrue. **Fix the read or fix the comment — my recommendation is the comment, because level 0 measures worse.**

---

## MOVEMENT 1 — NORMALIZE THE MALFUNCTIONS

### M1 — ★ A PHANTOM FILL. `exhaustion_short_B` was closed at a price MNQ never traded.

Trade **587** (08-07 13:30:48 → 13:31:01, booked **−$78.00**).

Both lots entered at 29715.00 and both stops were placed as `StopLimitOrder(auxPrice=29733.25, lmtPrice=29753.25)` — a stop with a 20-point limit buffer. Both triggered at 13:31:01.634773, **the same microsecond**:

```
stp-000006  BUY 1 @ 29737.75   (4.50 pt through the 29733.25 trigger)   -> booked -$47.00
stp-000007  BUY 1 @ 29753.25   (20.00 pt through — EXACTLY the limit)   -> booked -$78.00
```

The tape between the entry (13:30:48.800) and 13:31:10 says:

```
highest TRADE printed             29743.00   (at 13:31:02.135)
highest LEVEL-1 ASK quoted        29742.00
highest ASK across all 5 levels   29743.25
next print at or above 29753.25   13:32:04   — sixty-two seconds LATER
```

**Price never reached 29753.25.** The fill is 10.25 points above the highest print in the window and 10.00 points above the deepest offer in the book. It is the IBKR **paper** simulator filling a stop-limit at its limit price when the sim book ran out — not a market event. Its twin, from the identical entry and the identical trigger, filled at 29737.75.

**Normalization: restate trade 587 at Lot A's measured fill, 29737.75 → −$47.00. Swing +$31.00.**

**★ This is not an exhaustion problem, it is a DESK problem.** Across all 56 stop fills I could match to their placement, exactly **two** filled at the limit price — and both were the *second* lot of a pair, both within four minutes of the 13:30 cash open:

| date | ref | gate | trigger | limit | fill | slip | booked | real |
|---|---|---|---|---|---|---|---|---|
| 08-06 13:33:45 | stp-000006 | `abs_veto_short_B` | 29274.75 | 29295.25 | **29295.25** | +20.00 | −$84.00 | ≈−$45.50 |
| 08-07 13:31:01 | stp-000007 | `exhaustion_short_B` | 29733.25 | 29753.25 | **29753.25** | +20.00 | −$78.00 | −$47.00 |

For context, the other 54 stop fills have a **median slippage of 0.00 pt** and a mean of **−4.25 pt** (i.e. usually *better* than the trigger). So this is a fat tail, not a distribution — and it is a simulator artefact. ≈**$70 of fake losses this week**, and it will recur every violent open until we either narrow the stop-limit buffer or switch the protective order to a stop-market.

### M2 — ★ A SIGNAL THAT PASSED EVERY FILTER AND SILENTLY NEVER BECAME AN ORDER

The tournament journal, 08-07:

```
14:19:36,959 tournament exh confirm: exhaustion_short_A held after 5s → OPEN @29696.75
14:19:36,960 tournament exh confirm: exhaustion_short_B held after 5s → OPEN @29696.75
```

…and then **nothing**. No `placeOrder`. No `signals` row (not even `submitted`). No error, no warning, no `nofill`. The gate was armed (the switch file did not bench it again until 14:20:45). The desk was flat. `MultiSlotCore._open` has **three silent `return` paths** — `self._halted`, slot-not-flat, and `gate in self._pending` — and **none of them logs anything.** There is no halt anywhere in the day's log, so it was one of the other two, and the store cannot tell me which.

**Priced honestly, the bug made us money.** ATR at 14:19:36 was 41.79 pt; the pair would have stopped at 14:23:57 for **−$174.14** (MAE ran to 82.25 pt within 30 minutes). I have **not** credited that back — you cannot bank a loss you avoided by accident. But it is a real observability hole: *the desk cannot tell you why an approved entry never became an order.* One log line in `_open` fixes it.

### M3 — the 07-30 "best day" is not what the ledger says it is

`router_badcall_ledger.md` records *"exhaustion_short went 4/4 +$372.5 live fading the roll-over (operator claimed each)."* Two corrections, both from our own data:

1. **It was 4-for-6, not 4-for-4.** Twenty-two minutes after the last winner, the same gate took another pair at 15:44:31 and both stopped: **−$100.50 and −$55.00**. The day's honest total is **+$217.00**, not +$372.50. (The ledger entry was written at ~15:40, before that pair — an honest timing artefact, not a mistake, but it has been quoted as +$372.50 ever since.)
2. **Every exit was `MANUAL_CLAIM` — the operator's hand, not the gate's exit.** `data/claim_audit.json` flags all four as unpriceable ("no_ticks"), but the tick archive *does* have 07-30, so I priced them:

| entry (UTC) | lot | hand $ | gate's own exit $ | delta | machine reason |
|---|---|---|---|---|---|
| 15:05:54 | A | +107.50 | +58.50 | −49.00 | TARGET, 80 s |
| 15:05:54 | B | +117.00 | +62.00 | −55.00 | CHANDELIER, 148 s |
| 15:22:25 | A | +38.50 | +60.00 | +21.50 | TARGET, 61 s |
| 15:22:25 | B | +109.50 | +9.00 | −100.50 | CHANDELIER, 165 s |
| 15:44:31 | A | −100.50 | −62.20 | +38.30 | STOP, 124 s |
| 15:44:31 | B | −55.00 | −62.20 | −7.20 | STOP, 124 s |
| **total** | | **+217.00** | **+65.10** | **−151.90** | |

**Seventy per cent of the gate's best-ever day was Garrath's hand on the exit button.** The gate's own machinery, on the same six entries, makes +$65.10. And the independent shadow twin (`exhaustion_rev`, always on, its own tick loop) was **−$91.00 short-side on 07-30**. The counter-evidence in the brief is real but it is thinner than it reads.

### M4 — a half-fill, recorded not normalized

07-31 18:41:58: `exhaustion_short_A` filled at 28429.25 (stopped, −$27.50); `exhaustion_short_B` logged **`nofill`** — its IOC never filled and the pair traded as a single lot. Not an error, just a fact that makes the A/B ledger asymmetric. No adjustment.

### M5 — no naked rides, no system stops, no `STOP_UNFILLED`

Holds across the 17 A/B lots: 13 s, 22 s, 61–165 s, 390 s, 400 s, 754 s. Nothing near the 120-minute cap, nothing overnight, no stop-breach flatten, no `STOP_UNFILLED` on this gate all week. **The only execution faults are M1 (a phantom fill) and M2 (a silent drop).**

---

## MOVEMENT 2 — CORRECTED-COST RECONSTRUCTION

### This week (08-03 → 08-07), lot by lot

| id | UTC | lot | entry | exit | reason | booked | corrected |
|---|---|---|---|---|---|---|---|
| 566 | 08-05 14:31:48 | A | 29867.75 | 29902.25 | STOP | −70.50 | −70.50 |
| 565 | 08-05 14:31:48 | B | 29867.75 | 29902.25 | STOP | −70.50 | −70.50 |
| 586 | 08-07 13:30:48 | A | 29715.00 | 29737.75 | STOP | −47.00 | −47.00 |
| 587 | 08-07 13:30:48 | B | 29715.00 | **29753.25** | STOP | −78.00 | **−47.00** ← M1 phantom |
| 588 | 08-07 14:48:15 | A | 29717.75 | 29690.00 | TARGET | +54.00 | +54.00 |
| 589 | 08-07 14:48:15 | B | 29717.25 | 29691.50 | **CHANDELIER** | +50.00 | +50.00 |
| | | | | | **total** | **−162.00** | **−131.00** |

**This week, corrected: −$131.00 on 6 lots (2 winners), −$21.83 a lot.** Trade 589 is, as the brief says, the **desk's only chandelier exit of the entire week** — 112 lots, 71 stops, 34 targets, one chandelier.

For scale: the whole desk this week was **≈−$1,028**, so `exhaustion_short` is 13–16% of the bleed on 5% of the lots.

### The whole life of the gate

| era | lots | booked | note |
|---|---|---|---|
| `exhaustion_short` single-slot, 07-21 → 07-29 | 58 | **+$271.00** | fixed 8/12/120s exit + give-back |
| `exhaustion_short_A/B` dual-slot, 07-29 → 08-07 | 17 | **−$210.50** | the current scalp/chandelier exits |
| **all time** | **75** | **+$60.50** | +$0.81 a lot |

| A/B-era correction | net |
|---|---|
| as booked | −$210.50 |
| + M1 phantom fill normalized | −$179.50 |
| − 07-30 hand exits (+$217.00) replaced by the gate's own (+$65.10) | **−$331.40** |

**On its own exits, with the phantom fill removed, the dual-slot era is −$331.40 over 17 lots = −$19.49 a lot.** The +$271 from the earlier single-slot era was earned under a *different exit* — which is Movement 4's headline.

---

## MOVEMENT 3 — THE BENCH QUESTION (the operator's specific ask)

The brief asks two things: give the fader its own bench predicate, and **measure the P&L forgone in the six benched windows**. I did the measurement first, because it settles the argument.

### How much was it actually armed?

Reconstructed exactly, from the tournament's own `gate switches changed` log:

| armed window (UTC) | hours |
|---|---|
| 08-02 22:00 → 22:10 | 0.17 |
| 08-04 22:00 → 22:45 | 0.76 |
| 08-05 13:32 → 14:35 | 1.04 |
| 08-05 22:00 → 22:35 | 0.60 |
| 08-06 22:00 → 22:10 | 0.18 |
| 08-07 13:28 → 13:38 | 0.17 |
| 08-07 14:15 → 14:20 | 0.08 |
| 08-07 14:25 → 15:23 | 0.96 |
| 08-07 15:40 → 19:10 | 3.50 |
| 08-07 19:30 → 22:00 | 2.49 |
| **total** | **10.0 h of 120** |

**The gate was armed 8.3% of the week.** The operator's read of the situation is completely correct on the *facts*. Four of those windows are just the 22:00 nightly `reactivate_gates.py` re-arm being re-benched by the durable router tick within ten to forty-five minutes.

### What the benching actually cost — window by window

Replaying the always-armed counterfactual and totalling only the trades that fall **inside** each benched interval (mean of ten polling phases):

| benched window (UTC) | hours | fires/phase | net if it had been armed |
|---|---|---|---|
| 08-03 00:00 → 22:00 | 22.0 | 8.0 | **−$243** |
| 08-03 22:00 → 08-04 22:00 | 24.0 | 7.0 | **−$192** |
| 08-04 22:45 → 08-05 13:32 | 14.8 | 1.4 | +$55 |
| 08-05 14:35 → 22:00 | 7.4 | 10.9 | +$139 |
| 08-05 22:35 → 08-06 22:00 | 23.4 | 15.0 | +$123 |
| 08-06 22:10 → 08-07 13:28 | 15.3 | 0.4 | −$13 |
| 08-07 13:38 → 14:15 | 0.6 | 6.4 | +$76 |
| 08-07 14:20 → 14:25 | 0.1 | 1.2 | −$85 |
| **TOTAL FORGONE** | | | **−$140** |

> ### **Benching `exhaustion_short` this week did not cost $140. It SAVED $140.**

And the full-week picture agrees:

| policy | lots/phase | net (mean of 10 phases) | sd | $/lot | phases green |
|---|---|---|---|---|---|
| **as actually armed** (10 h) | 11.2 | **−$474** | 225 | −42.34 | 0/10 |
| **always armed** (120 h) | 61.5 | **−$614** | 509 | −9.98 | 1/10 |

Over the six-day dense tape (adding 07-31) always-armed is **−$847 ± 466, 0 of 10 phases green**.

**So the diagnosis in the 13:24Z carve-out is right about the LOGIC and wrong about the MONEY.** Applying "day-bias UP → bench shorts" to a fader *is* a category error — it benches the fade exactly when the fade's setup forms. But this particular fader was losing money in those windows anyway, so the category error was accidentally protective. Both of those things are true and neither cancels the other, and the carve-out note itself already said the honest version: *"THIS IS AN OPTION, NOT A CONVICTION… strip-best-1 = −$135.50, strip-best-2 = −$230.50."* That was the right call on the evidence available; three more sessions of evidence have now landed on the same side.

### The bench predicate the brief asks for — and why I am not recommending it

The brief asks for a **regime/extremes** bench predicate instead of a day-bias-direction one. I built and tested exactly that, in four forms, on the six-day dense tape:

| candidate fader bench predicate | lots | net | strip-3 | LODO worst | phases green | target winners kept |
|---|---|---|---|---|---|---|
| baseline (no extra predicate) | 71 | −$847 | −$1,188 | −$970 | 0/10 | 8/8 |
| bench unless price ≥ VWAP + 1.0 ATR (**an extension floor**) | 19 | −$132 | −$316 | −$246 | 4/10 | **0/8** |
| bench unless price ≥ VWAP + 1.5 ATR | 15 | −$3 | −$184 | −$129 | 4/10 | **0/8** |
| bench unless price is at a 30-bar high (break cap ≤ 0) | 69 | −$829 | −$1,170 | −$952 | 0/10 | 8/8 |
| bench on regime = violent-whipsaw | 44 | −$729 | −$951 | −$776 | 0/10 | **1/8** |
| **keep** the existing counter-regime veto (already live) | 71 | −$847 | — | — | — | — |
| **remove** the counter-regime veto | 131 | −$1,158 | −$1,512 | −$1,308 | 0/10 | 8/8 |

Two readings:

- **The extension floor is a FAKE WIN and I am rejecting it.** "Only fade something that is genuinely stretched above VWAP" is a beautiful fader predicate and it takes the number from −$847 to −$3. It does that by **throwing away all eight of the target winners** and shrinking the book to 15 lots. That is the 15/17-winners rule failing at its most seductive, and it is exactly the trap this section exists to catch. **REJECTED.**
- **`veto_counter_regime` — the one bench predicate that is already live — is the one that earns.** Turning it off adds 60 lots and **−$311**. It is worth **≈$5.20 per lot blocked** and it keeps all eight winners. **HOLD, no change.** It is also, note, precisely a mechanism-based predicate rather than a day-sign one — the fix the brief asks for was already shipped on 07-28.

---

## MOVEMENT 4 — ROOT CAUSE: BASE, EXIT, or SIGNAL?

### It is not the base config

Every threshold in the trigger, swept on the honest tape, mean of ten phases:

| knob | value | lots | net | strip-3 | phases green |
|---|---|---|---|---|---|
| `net_min` | 400 (live) | 71 | −$847 | −$1,188 | 0 |
| | 500 | 38 | −$151 | −$470 | 5 |
| | 600 | 23 | +$8 | −$261 | 4 |
| | 800 | 13 | +$46 | −$189 | 4 |
| | 1000 | 5 | −$21 | −$131 | 5 |
| `wall_ratio` | 1.0 (off) | 149 | −$1,446 | −$1,843 | 0 |
| | 1.5 (live) | 71 | −$847 | −$1,188 | 0 |
| | 2.0 | 35 | −$649 | −$907 | 1 |
| | 3.0 | 7 | −$175 | −$225 | 2 |
| `move_max` | 0.5 pt | 23 | −$452 | −$707 | 0 |
| | 1.0 pt | 41 | −$653 | −$933 | 1 |
| | 2.0 pt (live) | 71 | −$847 | −$1,188 | 0 |
| | 4.0 pt | 120 | −$839 | −$1,236 | 0 |
| flow window | 10 s | 37 | −$455 | −$728 | 3 |
| | 20 s (live) | 71 | −$847 | −$1,188 | 0 |
| | 30 s | 106 | −$1,040 | −$1,421 | 0 |
| | 60 s | 166 | −$1,375 | −$1,762 | 0 |

**Not one cell crosses zero on strip-best-3.** The best cells (`net_min ≥ 600/800`) get there by taking 13–23 lots out of 71, and they fail strip-3 too. The knobs are all pointing at the same thing: **fewer trades = less loss.** That is the signature of no edge, not of a mis-set parameter.

### It IS partly the exit — and this part is fixable and worth $604

Same entries, six days, ten phases, only the exit changed:

| exit | lots | net | sd | $/lot | phases green |
|---|---|---|---|---|---|
| **LIVE today** (A 0.75R / B tight-k1.5 chandelier / atr_split 22 → A $40, B 1.75R floor $60) | 71 | **−$847** | 466 | −11.93 | 0/10 |
| **8 pt stop / 12 pt target / 120 s** (the 07-25 rehab config, still in `footprint.py`) | 66 | **−$243** | 250 | −3.67 | 2/10 |
| 12 pt stop / 8 pt target / 120 s | 66 | −$121 | 226 | −1.83 | 3/10 |
| 8 pt / 6 pt / 120 s | 66 | −$196 | 223 | −2.95 | 3/10 |
| 15 pt / 20 pt / 300 s | 66 | −$182 | 305 | −2.76 | 3/10 |
| 8 pt / 12 pt / 60 s | 66 | −$220 | 253 | −3.32 | 2/10 |

**The mechanism is obvious once you see the ATRs.** This is a snap-back fade, but the current exit hangs a **1.0 × ATR** stop on it, and the ATRs at these entries are 18–49 points. So on 08-07 at 14:19 the desk was risking **41.8 points** to make **31 points** (0.75R) on a move whose entire measured life is a handful of points and a few seconds. The `atr_split 22` `lo` block helps on quiet tape, but 62% of this gate's fires happen at ATR ≥ 22 where it does not apply at all.

Look at the ATR ladder — it is the cleanest table in the report:

| entry ATR (pt) | lots | net | win% | $/lot | mean MFE (R) | mean MAE (R) |
|---|---|---|---|---|---|---|
| 0–12 | 78 | +$22 | 32.1 | +0.28 | 1.21 | 0.88 |
| 12–18 | 142 | +$119 | 40.1 | +0.84 | 1.13 | 0.77 |
| 18–22 | 82 | −$1,032 | 32.9 | −12.58 | 0.81 | 0.80 |
| 22–30 | 120 | −$591 | 50.8 | −4.93 | 0.78 | 0.71 |
| **30–40** | **170** | **−$4,979** | 34.1 | **−29.29** | 0.60 | 0.80 |
| 40+ | 118 | −$2,009 | 41.5 | −17.03 | 0.77 | 0.72 |

The MFE/MAE columns say it plainly: **the favourable excursion never scales with the stop.** At ATR 12–18 the average trade reaches 1.13 R in its favour; at ATR 30–40 it reaches 0.60 R while the adverse excursion sits at 0.80 R. The move is roughly a **fixed number of points**, so an ATR-scaled stop and an ATR-scaled target both become nonsense as vol rises. **A fixed-point exit is structurally the right shape for this gate, and we replaced it with an ATR one on 07-29.**

**SHIP THIS regardless of the arming verdict:** put `exhaustion_short` back on `exit="fixed", fixed_stop_pt=8.0, fixed_target_pt=12.0` — i.e. delete the `exhaustion_short` entry from `data/exit_overrides.json` and let the built-in spec stand. Worth **+$604 over six days** on identical entries. It does not make the gate positive; it stops the exit adding $600 of damage on top of the signal's own.

### But the real root cause is the SIGNAL — and the proof is the placebo null

For every entry the gate actually took, the forward move in points (positive = the short fade won), against a **200-trial placebo** of the same number of entries at random seconds in the same sessions:

| horizon | signal mean (pt) | null mean (pt) | signal's percentile in the null |
|---|---|---|---|
| 15 s | −0.64 | −0.03 | **10th** |
| 30 s | −1.15 | −0.00 | **2nd** |
| 60 s | −2.56 | −0.18 | **0th** |
| 120 s | −4.36 | −0.75 | **0th** |
| 300 s | −3.67 | −1.84 | 15th |
| 600 s | +1.48 | −2.50 | 96th |
| 1800 s | −1.92 | −3.05 | 62nd |

**The entry is significantly ANTI-predictive out to two minutes.** Not "no edge" — negative edge, at the 0th percentile of a random null. Shorting here is measurably worse than shorting at a coin-flip second.

### Why — and it is the desk's own five-second wait

Decompose the trigger's life around the confirm window. Same fires, de-duplicated to one per two minutes, all ten phases pooled:

| segment | n | 0→5 s (the confirm wait) | 5→35 s | 5→65 s | 5→125 s | 5→305 s |
|---|---|---|---|---|---|---|
| **all raw fires** | 906 | **+0.25** | +0.03 | −0.38 | −2.29 | −2.48 |
| ↳ confirm-veto **PASSED** | 699 | **+1.88** | +0.14 | −0.45 | −1.15 | −1.02 |
| ↳ confirm-veto **REJECTED** | 207 | −5.25 | −0.32 | −0.14 | −6.11 | −7.40 |

Read the top row: **the fade happens during the five seconds we spend confirming it, and it is over by the time we are allowed in.** After the wait, forward drift is zero-to-negative at every horizon.

The 5-second confirm-veto is not the villain — the rejected fires drift −5.25 pt against you inside the window and −7.40 pt after, so it is correctly filtering disasters, and it keeps all eight target winners. But it proves the shape of the thing: **this signal's half-life is under five seconds, which is shorter than the desk's own confirmation latency and barely longer than its polling interval.**

### The wall — the mechanism's actual claim — does nothing

The gate's story is *"heavy aggression absorbed by a resting wall → the flip."* Test the wall in isolation, on forward drift (+ = fade wins):

| variant | fires | 30 s | 60 s | 120 s | 300 s |
|---|---|---|---|---|---|
| live trigger (flow + move cap + wall ≥ 1.5 at L2) | 91 | +2.18 | +0.65 | +0.65 | +2.70 |
| **wall test removed entirely** | 229 | +1.53 | +2.01 | +1.53 | +0.06 |
| wall measured on the **true** top of book | 146 | +1.23 | +1.59 | −0.35 | −2.31 |
| wall ≥ 3.0 | 10 | −1.43 | −4.58 | −13.43 | −23.50 |
| **flow only** (net ≥ 400 in 20 s, nothing else) | 410 | +1.18 | +1.29 | +1.24 | −1.51 |

Removing the wall test **improves** 60 s and 120 s drift and quadruples the sample. Measuring it correctly makes it worse. Demanding a bigger wall makes it catastrophically worse. **The wall is noise** — and mechanically that is unsurprising: the sizes it compares are typically 1 to 10 contracts on a book that updates ~190 times a second. Whether `ask ≥ 1.5 × bid` at the exact millisecond you look is close to a coin toss, which is the same fact the phase experiment in §0 found from the other direction.

### And the sign is wrong

If the fade is anti-predictive, following the flow should be better. It is:

| same trigger, same exits, 6 dense days | lots | net | sd | $/lot | phases green |
|---|---|---|---|---|---|
| **FADE it** (live: SHORT) | 71 | **−$847** | 466 | −11.93 | 0/10 |
| **FOLLOW it** (LONG) | 158 | **+$51** | 354 | +0.32 | 5/10 |

A $900 swing from a sign flip. I am **not** proposing it as a play: +$51 ± $354 on $0.32 a lot is not an edge, it is the absence of a bleed. Recorded as a NULL. But it is the cleanest confirmation that heavy buying that has not yet moved price is a **continuation** tell, not an exhaustion tell.

### The independent shadow agrees, and the standing lesson needs updating

`exhaustion_rev` — the observe-only footprint twin in `shadow.db`, always on, its own tick loop, the original 8/12/120 s exit, honest tick-repriced `real_pnl`:

| side | n | net | $/trade | win% |
|---|---|---|---|---|
| SHORT | 239 | **−$680.00** | −$2.85 | 39.7 |
| LONG | 228 | −$719.50 | −$3.16 | 37.7 |
| **both** | **467** | **−$1,399.50** | −$3.00 | 38.8 |

Nineteen sessions, 467 trades, both sides negative at almost exactly the same rate. My replay says −$3.67/lot on the same exit; the shadow says −$2.85. **Two completely independent implementations agree to within a dollar a trade.**

> **★ The banked lesson `[[exhaustion-short-live-fader-success]]` — *"judge footprint faders on LIVE P&L; the shadow understates them"* — was banked when the shadow was −$194 on 145 trades and the live book had just had its +$372.50 afternoon. On 467 trades the shadow does not understate it: shadow −$2.85/trade short-side vs the live dual-slot era's −$19.49/lot. The shadow was not wrong. It was early. That memory should be amended.**

---

## MOVEMENT 5 — FILTERS THAT KEEP THE WINNERS (every attempt, including the NULLs)

The eight target winners the filter must keep (pooled across phases): 08-07 13:52 ×3 (+$208 each), 08-07 13:48 (+$158, +$156), 07-31 13:45 (+$151), 08-07 14:09 ×2 (+$122). Baseline: 71 lots, **−$847**, strip-3 **−$1,188**, LODO-worst **−$970**, 0/10 phases green, 8/8 winners.

| filter | lots | net | sd | strip-3 | LODO-worst | phases green | winners kept | verdict |
|---|---|---|---|---|---|---|---|---|
| ATR floor ≥ 10 | 66 | −$822 | 528 | −$1,163 | −$944 | 0 | 8/8 | NULL |
| ATR floor ≥ 14 | 59 | −$761 | 415 | −$1,102 | −$841 | 0 | 8/8 | NULL |
| ATR floor ≥ 18 | 49 | −$865 | 396 | −$1,206 | −$886 | 0 | 8/8 | NULL |
| ATR floor ≥ 22 | 41 | −$769 | 367 | −$1,108 | −$725 | 0 | 8/8 | NULL |
| ATR floor ≥ 26 | 35 | −$680 | 325 | −$1,019 | −$698 | 0 | 8/8 | NULL |
| ATR floor ≥ 30 | 29 | −$699 | 338 | −$1,035 | −$668 | 0 | 8/8 | NULL |
| ATR floor ≥ 35 | 21 | −$660 | 340 | −$984 | −$578 | 0 | 8/8 | NULL |
| **ATR ceiling ≤ 18** | 22 | **+$14** | 154 | −$169 | −$178 | 5 | **0/8** | **FAKE WIN — rejected** |
| ATR ceiling ≤ 22 | 30 | −$89 | 232 | −$279 | −$281 | 4 | **0/8** | FAKE WIN |
| ATR ceiling ≤ 26 | 36 | −$195 | 302 | −$385 | −$411 | 2 | 0/8 | FAKE WIN |
| ATR ceiling ≤ 30 | 42 | −$148 | 290 | −$354 | −$412 | 4 | 0/8 | FAKE WIN |
| ATR ceiling ≤ 35 | 51 | −$204 | 344 | −$430 | −$381 | 2 | 0/8 | FAKE WIN |
| ATR ceiling ≤ 45 | 65 | −$711 | 476 | −$1,024 | −$833 | 0 | 5/8 | NULL |
| ER15 ceiling ≤ 0.20 | 32 | −$360 | 266 | −$617 | −$399 | 1 | 2/8 | NULL |
| ER15 ceiling ≤ 0.30 | 46 | −$271 | 425 | −$598 | −$495 | 2 | 7/8 | NULL |
| ER15 ceiling ≤ 0.40 | 53 | −$552 | 430 | −$880 | −$712 | 1 | 7/8 | NULL |
| ER15 ceiling ≤ 0.50 | 59 | −$453 | 501 | −$792 | −$582 | 2 | 8/8 | NULL |
| ER15 floor ≥ 0.20 | 40 | −$475 | 434 | −$796 | −$600 | 0 | 6/8 | NULL |
| ER15 floor ≥ 0.35 | 23 | −$608 | 269 | −$813 | −$562 | 0 | 1/8 | NULL |
| ER15 floor ≥ 0.55 | 8 | −$234 | 165 | −$294 | −$212 | 0 | 0/8 | NULL |
| extension floor ext ≥ 0.0 ATR | 34 | −$214 | 237 | −$516 | −$338 | 2 | 5/8 | NULL |
| extension floor ext ≥ 0.5 ATR | 27 | −$175 | 258 | −$444 | −$347 | 1 | 3/8 | FAKE WIN |
| extension floor ext ≥ 1.0 ATR | 19 | −$132 | 238 | −$316 | −$246 | 4 | **0/8** | FAKE WIN |
| **extension floor ext ≥ 1.5 ATR** | 15 | **−$3** | 206 | −$184 | −$129 | 4 | **0/8** | **FAKE WIN — the seductive one** |
| extension floor ext ≥ 2.0 ATR | 13 | −$18 | 139 | −$168 | −$122 | 4 | 0/8 | FAKE WIN |
| break cap ≤ +0.5 ATR | 71 | −$847 | 466 | −$1,188 | −$970 | 0 | 8/8 | inert |
| break cap ≤ 0.0 ATR | 69 | −$829 | 469 | −$1,170 | −$952 | 0 | 8/8 | NULL |
| break cap ≤ −0.5 ATR | 62 | −$896 | 483 | −$1,234 | −$1,007 | 0 | 8/8 | NULL (worse) |
| **counter-regime veto OFF** | 131 | −$1,158 | 509 | −$1,512 | −$1,308 | 0 | 8/8 | **keeping it is worth +$311** |
| confirm adverse ≤ 10 pt | 89 | −$1,130 | 743 | −$1,490 | −$1,314 | 1 | 8/8 | NULL (worse) |
| confirm adverse ≤ 20 pt | 98 | −$1,180 | 870 | −$1,564 | −$1,233 | 1 | 8/8 | NULL (worse) |
| confirm wait 3 s | 80 | −$858 | 554 | −$1,200 | −$964 | 1 | — | NULL |
| confirm wait 10 s | 60 | −$703 | 480 | −$1,019 | −$752 | 0 | — | NULL |
| confirm wait 15 s | 52 | −$404 | 312 | −$718 | −$456 | 1 | — | NULL |
| confirm wait 30 s | 43 | −$98 | 349 | −$401 | −$225 | 5 | — | NULL (fails strip-3) |
| US only, 13–22 UTC | 70 | −$841 | 448 | −$1,182 | −$954 | 0 | 8/8 | inert (it already is) |
| LONDON only, 07–13 UTC | 1 | −$1 | 43 | $0 | −$11 | 1 | 0/8 | **no sample — the setup does not form** |
| regime: drop violent-whipsaw | 44 | −$729 | 426 | −$951 | −$776 | 0 | 1/8 | FAKE WIN |
| regime: drop dead-chop | 58 | −$899 | 365 | −$1,240 | −$913 | 0 | 8/8 | NULL (worse) |
| regime: keep in-between + clean-trend | 23 | −$608 | 269 | −$813 | −$562 | 0 | 1/8 | NULL |
| regime: keep chop only | 22 | −$137 | 222 | −$308 | −$236 | 2 | 0/8 | FAKE WIN |
| book level 0 (true top-of-book) | 124 | −$1,265 | 639 | −$1,637 | −$1,435 | 0 | 2/8 | NULL (worse) |

**Forty-two filters. Not one of them is a real win.** Every single cell that gets the number near zero does it by cutting the winners — the ATR ceiling family, the extension family, the regime allow-lists — and every cell that keeps the winners keeps the loss. **Zero of forty-two clears strip-best-3.** The one thing on the list that genuinely earns is the veto we already have.

### ⚠ Honest note on the winner-matching test

The "winners kept" column matches on exact `(day, entry time, lot)`. Filters that shift the entry *timing* (`confirm wait`, `flow window`) mechanically score 0/8 and I have left those cells blank rather than pretend the test applied. The ATR-ceiling, extension and regime rows are genuine — those filters do not move entry times, they only remove entries, and the eight winners had ATR 32–49 pt and extension below +1.0 ATR, so every one of those filters really is deleting them.

---

## MOVEMENT 6 — THE PROVEN Rs vs THE OPERATOR'S GUESS, PER REGIME

The brief is explicit that the regime→exit cheat sheet (faders 0.5 R / 1.5 R) is a **prior, not a truth**, and must be swept per regime. Done: 8 Lot-A values × 7 Lot-B options = **56 configs per regime**, ten phases each, `atr_split` off so the R grid is the whole story.

Regimes use the desk's own classifier (`deciders.nipc_regime` on ATR1m / ER15 — one definition, no drift). The population, pooled over ten phases (710 lots / 355 signals):

| regime | lots | net | win% | $/lot | mean MFE (R) | mean MAE (R) |
|---|---|---|---|---|---|---|
| dead-chop (ATR<18 & ER15<0.35) | 136 | **+$480** | 41.2 | **+3.53** | 1.23 | 0.85 |
| normal-chop | 79 | −$1,757 | 24.1 | −22.24 | 0.56 | 0.84 |
| in-between-building (ER15 0.35–0.55) | 141 | −$3,896 | 28.4 | −27.63 | 0.80 | 0.79 |
| clean-trend (ER15 ≥ 0.55) | 79 | −$2,119 | 25.3 | −26.82 | 0.80 | 0.87 |
| violent-whipsaw (ATR ≥ 25, low ER) | 275 | −$1,179 | 51.6 | −4.29 | 0.80 | 0.69 |

And by time of day (the operator's second required split):

| block (UTC) | lots | net | win% | $/lot |
|---|---|---|---|---|
| 07–13 London | 6 | −$10 | 33.3 | −1.62 |
| **13–15 US open** | **325** | **−$7,733** | 35.7 | **−23.79** |
| 15–18 US mid | 242 | −$219 | 45.5 | −0.90 |
| 18–22 US late | 135 | −$462 | 36.3 | −3.42 |
| 22–24 reopen | 2 | −$47 | 0.0 | −23.43 |

**Ninety per cent of the damage is in the two hours after the cash open**, which is also where the ATR is 30–50 pt and the 1-ATR stop is at its most absurd. That is the same finding as the ATR ladder, seen from the clock.

### Guess vs proven, per regime

| regime | n/phase | operator's guess A 0.5R / B 1.5R | best cell found | best cell's config | plateau? | robust? |
|---|---|---|---|---|---|---|
| ALL (blanket) | 66.6 | −$725 | **−$506** | A 0.25R / B 4.0R | shallow | **no** — every cell negative |
| violent-whipsaw | 24.3 | −$150 | **−$21** | A 1.25R / B 4.0R | yes (all 56 within $400) | no — sd $555, 5/10 phases |
| in-between-building | 15.5 | −$266 | **−$77** | A 0.25R / B tight-2.5 | yes | no — 4/10 phases |
| clean-trend | 8.4 | −$198 | **−$99** | A 0.75R / B 1.0R | yes | no — n too thin |
| normal-chop | 8.2 | −$194 | **−$152** | A 0.25R / B 1.0R | yes | no |
| **dead-chop** | 13.6 | **+$20** | **+$127** | **A 2.5R / B 2.5R** | **yes, a real one** | **strip-3 −$95, LODO −$35 → FAILS** |

**Verdict on the cheat sheet:** the operator's 0.5/1.5 fader prior is **not** the optimum in any regime — it is beaten everywhere — but so is everything else, because **every regime except dead-chop is negative at every one of the 56 configurations tested.** There is no R to prove. The one honest thing the sweep says is directional and it agrees with Movement 4: **wider Lot-B targets beat trailing chandeliers here in every regime** (the `wide` lock-chandelier column is the worst in five of six tables), because a trail on a snap-back hands the money straight back.

### The one positive cell, interrogated properly

`regime = dead-chop`, Lot A 2.5R / Lot B 2.5R: **+$127**, 8 of 10 phases green, 13.6 lots/phase.

| test | result | pass? |
|---|---|---|
| parameter plateau (4×4 neighbourhood) | **all 16 cells positive**, +$16 → +$127 | ✅ |
| per-day | 07-31 −$49 · 08-03 −$20 · 08-04 −$68 · 08-05 +$115 · 08-06 +$162 · 08-07 −$13 | ⚠ 2 of 6 days carry it |
| **strip-best-3** | **−$95** | ❌ |
| **leave-one-day-out, worst fold** | drop 08-06 → **−$35** | ❌ |
| low-fidelity extension tape 07-24…07-30 | +$62, but strip-3 **−$60** | ❌ |

A genuine plateau sitting on a number that two of six days produce, and which dies on both strip-3 and LODO. That is a **lucky cell in a 5-regime × 56-config search**, i.e. 280 comparisons — you would expect several to look this good by chance. **Not promoted.** It is, however, the one place worth watching if the gate is ever shadowed again: *the fade only works when nothing is happening*, which is at least a coherent story.

---

## MOVEMENT 7 — ROBUSTNESS

| test | baseline (live config, always armed, 6 dense days) |
|---|---|
| headline | −$847 (mean of 10 phases) |
| **phase spread** | sd $418, range −$365 → −$1,711, **0 of 10 phases green** |
| **strip-best-3** | **−$1,188** (range −$759 → −$2,044) — stripping the winners makes it *worse*, i.e. the losers are the population |
| **leave-one-day-out** | worst fold (drop 08-06) −$970; best fold −$604 — **no fold is positive** |
| **per-day** | 07-31 −$233±133 · 08-03 −$243±191 · 08-04 −$196±122 · 08-05 −$94±231 · 08-06 **+$123**±239 · 08-07 −$204±340 → **1 of 6 days green** |
| **cross-regime** | 1 of 5 regimes positive (dead-chop), and it fails strip-3 |
| **per-ISO-week** | W31 (07-24…07-31, mixed fidelity) **+$370**, strip-3 **−$119** · W32 (08-03…08-07, live fidelity) **−$614**, strip-3 **−$941** |
| **out-of-sample leg** | 07-24…07-30 on the 250 ms depth archive: +$603 ± $994, 9/10 phases green — **but see the caveat** |

### ⚠ The out-of-sample leg, honestly

The 07-24…07-30 extension is the only positive block in the whole report, and I do not believe it, for a stated reason: **it uses a different book source.** On the three days where I have both, the dense `md` book and the 250 ms depth archive disagree by $121–$491 *per day* on the identical config, and they disagree in **sign** twice. The live gate reads the dense book. So the +$603 is measuring "what would this gate do if it polled a different, coarser book" — a different gate. Its per-day breakdown is also flat (+$297, +$256, +$19, +$52, −$22) with sd $994, and W31's strip-best-3 is −$119.

I am reporting it because the brief demands the failures *and* the successes be shown, and because burying the one green number would be exactly the dishonesty this section exists to prevent. **But it does not carry weight against six days of live-fidelity tape, 467 shadow trades and a 0th-percentile placebo result.**

### Cost sensitivity — how much is friction and how much is the signal?

| assumption | net (6 days) | $/lot |
|---|---|---|
| as measured ($1.50 RT, 0.75 pt entry, 1.0 pt stop) | −$847 | −11.93 |
| zero fee | −$741 | −10.43 |
| zero entry slip | −$570 | −8.01 |
| zero stop slip | −$761 | −10.71 |
| **all costs zero — perfect fills, free trading** | **−$382** | **−5.37** |

**Even with free trading and perfect fills the live configuration loses.** Friction is $465 of the $847; the other $382 is the strategy. That is the cleanest possible split between "we are being nickel-and-dimed" and "this does not work": here it is both, and the strategy half is the bigger half.

---

## MOVEMENT 8 — THE TRYING: every attempt to make it work, including the ones that failed

The brief says show the trying. Here is all of it, in the order I tried it.

| # | attempt | result | verdict |
|---|---|---|---|
| 1 | Re-arm it and measure the forgone P&L in the benched windows | −$140 forgone, i.e. benching **saved** money | **the premise is refuted** |
| 2 | Replace the day-bias bench rule with a regime/extremes predicate (4 forms) | best one takes −$847 → −$3 by deleting 8/8 winners | **fake win, rejected** |
| 3 | Keep the counter-regime veto (already live) | worth **+$311**, keeps 8/8 winners | ✅ **hold, no change** |
| 4 | Sweep every entry threshold (`net_min`, `wall`, `move_max`, flow window) — 20 cells | 0 of 20 clears strip-best-3 | NULL |
| 5 | Sweep every regime/vol/time filter — 22 more cells | 0 of 22 is a real win | NULL |
| 6 | Full 56-config exit grid per regime (5 regimes = 280 configs) | 4 of 5 regimes negative in **every** cell | NULL |
| 7 | The one positive cell (dead-chop, A 2.5R/B 2.5R) | plateau ✅, strip-3 ❌, LODO ❌ | **PARKED, not promoted** |
| 8 | Go back to the original fixed 8/12/120 s exit | −$847 → **−$243** | ✅ **SHIP — worth $604/6d** |
| 9 | Sweep the fixed-point exit family (6 cells) | best −$121 (12/8/120 s), still negative | partial win, not a fix |
| 10 | Fix the book-level bug and read the true top of book | **worse** (−$1,265), drift turns negative | NULL — but fix the comment |
| 11 | Remove the wall test entirely | **better** drift, 2.5× the sample | the mechanism's core claim is **refuted** |
| 12 | Flip the side — follow the flow instead of fading it | −$847 → **+$51** | $900 swing, but +$0.32/lot = NULL |
| 13 | Zero-latency scalp: enter AT the fire, no 5 s wait, 11 fixed-point exit cells | best −$330 (10/5/30 s); **+$232 with zero friction** | **the PARKED revival condition** |
| 14 | Placebo null, 200 trials | signal at the **0th percentile** at 60–120 s | **the root cause** |
| 15 | Cross-check against the 467-trade shadow twin | −$2.85/trade short-side, agrees within $1 | confirms |

### The one that came closest — and exactly why it fails

Attempt 13 is the honest lead, so here it is in full. Enter **at the fire instant** (skip the 5 s confirm entirely, since §4 shows that is where the move is), fixed point stop and target, hard time cap, 2 lots as live:

| stop / target / cap | lots | net | sd | strip-3 | $/lot | phases green |
|---|---|---|---|---|---|---|
| 4 / 3 / 5 s | 171 | −$416 | 105 | −$430 | −2.43 | 0 |
| 4 / 3 / 10 s | 171 | −$461 | 126 | −$475 | −2.69 | 0 |
| 6 / 4 / 10 s | 171 | −$369 | 162 | −$388 | −2.16 | 1 |
| 8 / 4 / 10 s | 171 | −$347 | 189 | −$366 | −2.02 | 1 |
| 8 / 6 / 15 s | 171 | −$352 | 194 | −$383 | −2.05 | 1 |
| 5 / 5 / 20 s | 171 | −$454 | 174 | −$479 | −2.65 | 0 |
| 8 / 12 / 120 s | 171 | −$424 | 529 | −$492 | −2.48 | 2 |
| **10 / 5 / 30 s** | 171 | **−$330** | 233 | −$355 | **−1.93** | 1 |
| 6 / 6 / 30 s | 171 | −$370 | 181 | −$401 | −2.16 | 1 |
| 12 / 6 / 60 s | 171 | −$395 | 242 | −$426 | −2.31 | 0 |
| 4 / 8 / 30 s | 171 | −$501 | 183 | −$544 | −2.92 | 0 |
| **same 10/5/30 s cell with ZERO friction** | 171 | **+$232** | 204 | **+$202** | **+1.36** | **8/10** |

> **This is the whole story of `exhaustion_short` in two rows.** Gross, the construct makes **+$1.36 a lot** and is green in 8 of 10 sampling phases and survives strip-best-3. Net of $1.50 fee, 0.75 pt entry slip and 1.0 pt stop slip, it makes **−$1.93 a lot**. **Friction costs $562 over the window; the edge is worth $232.** It is not broken. It is **sub-friction by roughly two dollars a lot**, and no arming rule, no regime filter and no exit target closes a gap that large.

---

## WHAT TO DO — the exact configs

### ✅ SHIP NOW (independent of the arming decision)

**1. Revert the exit to the fixed 8/12/120 s snap-back.** Delete the `exhaustion_short` block from `data/exit_overrides.json`:

```json
"exhaustion_short": { "a_r": 0.75, "b": "tight", "atr_split": 22,
                      "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60} }   <- DELETE
```

With it gone the gate falls back to its `SlotSpec` default (`exit="fixed", fixed_stop_pt=8.0, fixed_target_pt=12.0, giveback_enabled=False`), which is what the 07-25 rehab shipped and what the `+$271` single-slot era was earned on. Restart the tournament to apply. **Worth +$604 over six days on identical entries.** Revert: put the block back.

⚠ Note the `_BIG_RUN` set in `slot_strategy.py` still lists `exhaustion_short`, so with the override gone the **scale-out slate** would give it A@2.5R + B wide-chandelier — which the sweep says is the *worst* Lot B in every regime. **Remove `exhaustion_short` from `_BIG_RUN` at the same time**, or the "revert" silently ships a worse exit than the one being replaced. This is the single most important line in this section.

**2. Fix the stop-limit buffer, desk-wide.** The protective stop is a `StopLimitOrder` with a **20-point** limit buffer. In the paper sim that buffer is where the fill lands when the sim book empties, and it cost us ≈$70 this week across two gates. Either narrow it to ~5 points or make the protective order a stop-market. Also add a fill-plausibility check: **if a stop fills more than N points through its trigger, alarm and reprice it against `capture.db` before it is booked.** We caught this one by hand; nothing in the desk would have.

**3. One log line in `MultiSlotCore._open`.** Its three silent `return` paths swallowed a confirmed entry on 08-07 and left no trace anywhere. Log which guard fired.

**4. Fix the `footprint._book_l1` comment (or the code).** It reads depth `level = 1`, which `capture.py` writes as the **second** price level, not the touch. Reading the true top of book measures *worse*, so my recommendation is to keep the code and correct the docstring — but nobody should read `footprint.py` and believe it is looking at the touch.

**5. Amend the memory `[[exhaustion-short-live-fader-success]]`.** "The shadow understates footprint faders" was true at n=145. At n=467 the shadow (−$2.85/trade) is *kinder* than the live dual-slot book (−$19.49/lot).

### ⏸ ARMING — no change requested

Leave the 13:24Z carve-out exactly as it is. It costs ~nothing to be armed (the gate produces 0.4–15 fires a day and the counter-regime veto is doing real work), the operator has explicitly chosen to pay nothing to be present for a rare setup, and this report has no evidence that arming it earns — but also no evidence that a *fifth* bench rule would help. **The one thing I would ask: with the exit reverted to 8/12/120 s, the next ~20 fires are a clean re-test of the gate as originally rehabilitated. Judge it on those.**

---

## DISPOSITION TABLE

| lead | verdict | condition |
|---|---|---|
| **`exhaustion_short` as a live gate** | **PARKED** | **Revive if (a) a zero-latency entry path exists — fill inside the 20 s window, not 5 s after it — AND (b) round-trip cost falls below ≈$0.50. Gross edge is +$1.36/lot and survives strip-3; friction is $3.28/lot. Nothing else closes it.** |
| Revert exit to fixed 8/12/120 s (+ drop from `_BIG_RUN`) | **LIVE — deploy** | +$604 / 6 days on identical entries; 6 of 6 fixed-point cells beat the current config |
| `veto_counter_regime` (already live) | **LIVE — hold** | +$311 / 6 days, keeps 8/8 winners; it is already the mechanism-based bench the brief asked for |
| Stop-limit 20 pt buffer → phantom fills | **LIVE — fix** | 2 fills/week at the limit price, ≈$70; hits every gate, not just this one |
| Silent drop in `MultiSlotCore._open` | **LIVE — fix** | one log line |
| `_book_l1` reads level 1 (= 2nd level) | **LIVE — fix the comment** | true top-of-book measures worse (−$1,265 vs −$847) |
| Regime/extension bench predicate for faders | **REFUTED** | named test: keeps 0 of 8 target winners at every threshold that helps the number |
| ATR floor / ATR ceiling / ER floor / ER ceiling / break cap | **REFUTED** | named test: 0 of 42 filter cells clears strip-best-3 with winners intact |
| The resting-**wall** mechanism | **REFUTED** | removing the wall test improves 60 s and 120 s forward drift and 2.5×s the sample; wall ≥ 3.0 drifts −13.4 pt at 120 s |
| Fade direction (SHORT on buy-absorption) | **REFUTED** | placebo null, 200 trials: 0th percentile at 60 s and 120 s. Following the flow is $900 better |
| dead-chop, A 2.5R / B 2.5R | **PARKED** | genuine 4×4 plateau but strip-3 −$95 and LODO −$35. Revive if n > 60 in that bucket alone, i.e. ~4 more weeks of dead-chop tape |
| Follow-the-flow (side flip) | **PARKED** | +$0.32/lot is not an edge. Revive only if someone wants a cheap two-sided shadow sim; not worth a slot |
| 07-24…07-30 positive extension leg | **NOT COUNTED** | different book source (250 ms depth vs dense md); the two disagree in sign on 2 of 3 overlap days |

---

## ⚠ WHAT I COULD NOT TEST (state it, don't hide it)

1. **07-30 — the gate's best day — cannot be replayed at live fidelity.** The dense `md` book was not archived before 07-31. I priced its six live entries directly (M3) but I cannot regenerate its *signals*.
2. **Six days is six days.** The dense-book tape starts 07-31. Everything with a "6 days" label is one working week plus a Friday, one market regime, one direction of drift.
3. **Sunday-evening reopens are missing** — the book archive has 08-02 20:50–24:00 but the tick archive does not, so the 22:00 reopen window (where four of the ten armed hours sat) is under-sampled.
4. **`tape.last` vs the last tick.** Live entry prices come from `md`'s `recent_tape`, published up to a second before the decision; I use the last tick at the decision instant. Measured effect on the three reproducible entries: 0.25–1.25 pt, inside the swept entry-slip band.
5. **Phase.** Everything here is the mean of ten 100 ms-spaced polling phases, because a single phase is worth ±$418 on a −$880 mean. If a future reader quotes a single number from a single run of this harness, they are quoting noise.
6. **The 08-07 14:19:36 silent drop** — I know the guard fired, I cannot tell you *which* guard, because none of them logs. That is item 3 on the ship list.
