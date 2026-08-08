# SKEPTIC — THE OPEN RIDER, **cost-and-execution attack**

**Verdict: the execution attack FAILS to kill it. HOLDS on this lens.**
Re-priced at the desk's real fee and re-run tick-honest with the spread crossed, the stop filled on the
tape's own flush and the time-cap crossed out, the ODR is **+$4,435 net on 95 sequential trades over the
12 execution-verifiable days ( +$46.69/trade, +0.386R, 51.6% win, 11/12 days green )**. The total
execution bill is **$5.18 a trade** against a **$52.42/trade** exact-fill gross — an 11% haircut, not a
refutation. Two of the five sub-attacks land as *deployment* findings rather than P&L findings, and one
number in the claim as stated is simply wrong (§0).

Everything below is re-derived from `gazbot7.lake.connect()` — bars, ticks **and** L1 quotes — with my
own harness. The original `rider.py` / `tickcheck.py` were read but not run and none of their outputs
are reused.

Working: `/tmp/claude-0/-root/a896b11d-25b4-42c9-a015-3fe2168c1910/scratchpad/{slip,odr_base,odr_tick,odr_exec,odr_exec2,odr_exec3}.py`

---

## 0. First, the claim's own arithmetic does not close

The brief says **"net +$4,169, 48.1% win, 102 trades"**. The source section says **129 trades**
(48.1% win, +$32.32/trade → 129 × 32.32 = $4,169 ✓). The **102** is a different row entirely — §10 item F,
the *thresholding* comparison ("none +$4,142 on 102 trades"), which is a different cadence/threshold cell.
**+$4,169 and 102 trades are not the same experiment.** My independent re-derivation returns **n = 129**
on the same 17 days, so 129 is the right count and 102 should not be quoted against the $4,169 headline.

Independent reproduction, timestamp-keyed (the original indexes bars *positionally*, so a missing 5s bar
would silently shorten its 15-min lookback; there are 6 missing bars on 07-22, hence a small drift):

| | n | net @ $5/RT | win% | exit mix |
|---|---|---|---|---|
| original `rider.py` (claimed) | 129 | +$4,169 | 48.1% | 66/51/12 |
| **this re-derivation, from the lake** | **129** | **+$4,688** | **49.6%** | 64/53/12 |

Same n, +$519 apart. The signal reproduces.

## (a) RE-PRICE AT $1.50/RT — the honest number is BIGGER, as expected

The fee correction is exactly linear: `net@1.50 = net@5.00 + 3.50 × n`.

| | n | @ $5/RT (as published) | **@ $1.50/RT (correct)** |
|---|---|---|---|
| author's headline, corrected in place | 129 | +$4,169 | **+$4,620** |
| my re-derivation, 17 days, 5s bars | 129 | +$4,688 | **+$5,139** |
| — DEV 12d | 90 | +$3,920 | +$4,235 |
| — HOLDOUT 5d | 39 | +$767 | +$904 |

**Corrected net = +$4,620 on 129 trades** on the author's own arithmetic; **+$5,139 on 129** on mine.
The $5/RT figure was over-charging this gate $3.50 × 129 = **$451**.

⚠ But the standing rule from the cost autopsy is *"don't just swap 5 → 1.5"* — the $5 flat was partly
proxying unmodelled slippage. So the $1.50 number is only honest once the slippage is put back in
explicitly. That is (b) and (c), and I do them together.

## (b) SLIPPAGE, DERIVED FROM REAL FILLS — not assumed

I measured the desk's actual execution against the **prevailing L1 quote at the fill millisecond**
(lake `quotes`, ASOF join, MNQ, `data_quality IS NULL`, 367 of 599 trades matched a quote inside 60s):

| | n | mean slip vs mid (pt) | median | p90 | $ / lot |
|---|---|---|---|---|---|
| market **ENTRY** | 367 | **+0.389** | +0.375 | +1.250 | $0.78 |
| mean quoted half-spread at entry | 367 | 0.341 | | | |
| **STOP** exit | 209 | **+1.550** | +0.500 | +3.800 | $3.10 |
| **STOP** exit, 13:00–15:00 UTC only | **90** | **+1.820** | +0.500 | | **$3.64** |
| TARGET exit | 67 | +0.453 | +0.375 | | |
| CHANDELIER exit | 46 | +0.359 | | | |

So: entries pay **essentially the touch and nothing more** (0.389 vs a 0.341 half-spread → 0.05 pt of
market-impact), and stops pay **1.55 pt beyond mid on the book, 1.82 pt inside the ODR's own window** —
the open is the worst place on the clock to be stopped, exactly as expected. Total measured stop-slippage
bill across the live book: **$742 on 209 stop exits = $3.55 a stop**.

**I did not assume any of this into the ODR.** Instead the harness models a real stop-market order —
on the first print through the level, the fill is the **worst print inside the next 250 ms**, taken from
the tape — and then I checked the model against the measurement:

| | n | mean slip through the trigger |
|---|---|---|
| ODR simulated stop fills (tape flush) | 45 | **1.624 pt** ($3.25) |
| live desk STOP fills, 13:00–15:00 UTC | 90 | 1.820 pt ($3.64) |

The model is **11% cheaper than reality**; charging the live 1.82 pt instead would cost a further **$18**
across all 45 stop exits. Immaterial. **The ODR's share of the desk's stop-slippage leak is $146 over
12 days (45 stop exits × $3.25)** — about $12 a session. Per stop it is no worse than the book; it just
stops out less often, because a 2×ATR stop is outside the noise the desk's 1×ATR stops sit inside.

## (c) THE RACE IS GENUINE — and the 5s-bar model was, unusually, fine

Every exit is a **first-touch race on the raw trade-print sequence** (sub-250 ms — I used the print
stream itself, which is finer than 250 ms buckets), never an MFE count:

- stop level and 2R target both scanned over the same forward print array; **whichever timestamp comes
  first wins, stop wins ties**;
- stop → market fill at the worst print inside the latency window (the flush);
- target → resting limit, filled at the target price, requires a print through it;
- 45-min cap → cross the spread at the prevailing quote (bid if long, ask if short);
- **sequential**: the next 5-minute slot is only considered after the previous trade's *real* exit ms.

Like-for-like on the **same 12 days** (07-16, 07-17, 07-27…07-31, 08-03…08-07 — the days that carry
both ticks and quotes):

| | n | net @$1.50 | win% | $/trade | STOP/TARGET/TIME |
|---|---|---|---|---|---|
| 5s-bar model, exact fills | 94 | +$4,957 | 53.2% | +$52.74 | 44 / 41 / 9 |
| **250 ms tick race, exact fills** | 94 | **+$4,927** | 53.2% | +$52.42 | 44 / 41 / 9 |
| + cross the spread on entry | 95 | +$4,587 | 51.6% | +$48.28 | 45 / 40 / 10 |
| + **stop FLUSH fill from the tape** | 95 | +$4,440 | 51.6% | +$46.74 | 45 / 40 / 10 |
| + cross out on the time cap = **FULL** | **95** | **+$4,435** | **51.6%** | **+$46.69** | 45 / 40 / 10 |

**The bar→tick resolution effect is −$30 on $4,957 — 0.6%.** The 87% flush-loss that 5s bars caused
elsewhere on this desk **does not appear here**, and the reason is structural, not luck: the stop sits at
**2 × ATR1m (mean 54.6 pt = $109)**, an order of magnitude outside a 5s bar's range, so the intrabar path
ambiguity that destroys tight-stop backtests has almost nothing to resolve. The whole execution bill is
**$5.18/trade**, and it is mostly the entry spread, not the stop.

**The one optimism left in the race — the resting 2R limit filling at the touch — is worth exactly $0.**
Requiring a print **1 or 2 ticks beyond** the target before the limit fills (queue priority) leaves the
result **byte-identical: +$4,435, 40 targets, 45 stops, 10 time-outs, at 0, 1 and 2 ticks of required
penetration.** Every target that was reached was blown through. This directly refutes the author's own §8
worry that "two knife-edge trades whose 2R target was grazed by under half a point" drove the tick-honest
haircut — at print resolution across 12 days there is no such trade.

Honest execution, split:

| | n | net | $/trade | R |
|---|---|---|---|---|
| FULL, DEV days | 55 | +$3,752 | +$68.21 | +0.596R |
| FULL, HOLDOUT days | 40 | +$684 | +$17.10 | +0.097R |

**The four days that can never be execution-verified (07-20…07-23, no ticks, no quotes; plus 07-24, ticks
but no quotes) are almost P&L-neutral** — the 17-day bar model at $1.50 is +$5,139 and the 12-day subset
is +$4,957, so all five unverifiable days together are worth **+$182**. That closes the obvious "you only
checked the good days" objection.

## (d) OVERLAPPING POSITIONS — the attack misses, the original was already sequential

`rider.py` line `if k is None or k < 360 or k < last: continue` with `last = ex[0]` **already blocks a new
entry until the previous trade's exit bar.** There is no paired-method overlap here of the kind that swung
the exit lab $5,076. My harness re-imposes it independently on the *tick-resolved* exit ms — which matters,
because a tick-resolved exit lands at a different moment and therefore changes which later slots are free
(n moves 94 → 95, not 94 → 129).

Occupancy under honest execution: **101.1% of the 2-hour window** (min 82%, max 123%), **7.9 trades a day**.
It is over 100% because the 45-minute cap on the 14:55 slot runs to 15:40 — i.e. it is genuinely an
always-in two-hour posture that spills past its own window, exactly as the author says. The desk can hold
that; it just cannot hold it *and* anything else (see (e)).

## (e) IS IT RUNNABLE AS A TOURNAMENT GATE? — **NO, not at this geometry.** This is where the attack lands.

Three checks. Two pass and one fails hard.

**PASS — `max_hold_minutes=120`.** Longest realised hold is 45.0 min (the cap). It never approaches the
global force-flat that limited the MD_STREAM incident to −$255.50. Unlike the day-rider, this needs no
architecture exemption.

**PASS — session guards.** `no_open_asia` blocks 00–07 UTC; the ODR window is 13:00–15:00 UTC and sits
inside the desk's only proven expectancy window (13:30–14:45, +$8.93/trade, n=562). No conflict.

**FAIL — the live slate cannot build a 2×ATR stop.** Every path through `scaleout_slots()`
(`src/gazbot7/slot_strategy.py:308, 319, 324` and `_lot_b():294`) hard-codes **`stop_atr_mult=1.0`** on
Lot A and on any numeric Lot B. A 2.0× stop exists **only in the shadow slate** (`shadow.py::_stop_width_ab`,
`sw_*_k20`), never in the live tournament, and `deciders.exit_scalp` **couples the target to the stop
width**, so naively setting 2.0 doubles the target as well. Re-running the identical entries on the tick
tape at the only stop the live machinery can produce:

| geometry | n | net @$1.50, FULL execution | win% | $/trade | R |
|---|---|---|---|---|---|
| **ODR as specified — stop 2.0×ATR, 2R** | 95 | **+$4,435** | 51.6% | +$46.69 | +0.386 |
| live slate — stop 1.0×ATR, 2R (decoupled) | 181 | +$3,183 | 43.1% | +$17.59 | +0.220 |
| live slate — stop 1.0×ATR, 4R (same $ target) | 124 | +$2,387 | 27.4% | +$19.25 | +0.164 |
| live Lot-A default — stop 1.0×ATR, 2.5R | 157 | +$2,795 | 37.6% | +$17.80 | +0.223 |
| stop 1.5×ATR, 2R (already REFUTED live) | 121 | +$2,505 | 42.1% | +$20.70 | +0.202 |

**Deploying it through today's slate costs 62% of the per-trade edge ($46.69 → $17.59) and nearly doubles
the trade count (95 → 181)** — i.e. it pays the spread and the stop-flush twice as often for a third of
the reward. The narrower stop is also what the author's own grid says is wrong (§10 item G), so this is
not a modelling nicety: **the ODR's edge lives in a stop width the live desk has no code path to produce.**

And **the quiet-tape clip would fire on 34–41% of its entries** — mean ATR1m at entry is 27.7 pt but
median 28.4 with a long low tail, so 41% of the spec's entries and 34% of the 1.0×ATR variant's entries
land under the 22 pt split, where Lot A is clipped to **$40** and Lot B to **max(1.75R, $60)** against the
spec's **$222 mean 2R target**. Whatever the resulting two-lot book earns, **it is not the strategy that
was tested**, and any P&L quoted for "ODR live" must be re-derived through `scaleout_slots()`, never from
the section's spec (this is the exact trap that has already eaten the ER/ATR floors, the ER-hold shadow,
the regime-3 selector and capitulation's base `target_r`).

**FAIL — the account is shared, and this thing is always in.** MNQ trades in **DUQ191770** and IBKR nets
the desks into one number; the day-rider is live in PAPER from 08-06, entering **2 lots between 13:38 and
15:00 UTC** and holding to 20:40.

- **49% of ODR entries (47 of 95) open inside the day-rider's live window.**
- The ODR **flips direction 2.6 times a day** (31 flips over 12 days) — every flip is a net-sign reversal
  on a shared account.
- **34% of the colliding entries (16 of 47) are opposite the day-rider's own direction rule** (sign of net
  from the 13:30 cash open).

That is the **08-06 cascade class verbatim**: one desk's order moving a net position another desk believes
it owns → reconcile DRIFT → 11 minutes halted with the whole safety block skipped, phantom exits, and a
leftover GTC stop firing naked six hours later. `safety.own_flatten_verdict` gates *flattens*; it does not
stop two strategies from netting each other's entries. **A second always-in desk in the day-rider's window
is not a config change, it is an architecture change**, and the still-open gap CLAUDE.md names — *"does
every live STOP have a slot?"* — gets materially worse with 7.9 extra wide stops a day working in the book.

## The one thing that genuinely worries me: the headline sits close to its own execution noise

Perturbing **only nuisance execution parameters that carry no information whatever** — latency, and the
arbitrary phase/period of the cadence clock:

| setting | net (FULL execution, 12 days) |
|---|---|
| latency 100 ms | +$4,284 |
| latency 250 ms (base) | +$4,435 |
| latency 500 ms | +$4,679 |
| latency 750 ms | +$4,805 |
| latency 1000 ms | +$4,938 |
| latency 1500 ms | +$3,981 |
| latency 2000 ms | +$3,291 |
| cadence 4 min | +$5,106 |
| cadence 6 min | +$3,903 |

**Range $3,291 → $5,106 = $1,815 = 41% of the headline, sd $519.** Two facts inside that: the net is
*non-monotone in latency* (worse fills at 1000 ms earn **more** than perfect fills at 0 ms, +$4,938 vs
+$3,762), which is proof that several hundred dollars of the headline is fill-luck, not edge; and the
desk's real decision loop is **~1 s**, not 250 ms, so the base case is if anything the optimistic corner.

It is a wide band — but **the whole band is positive, 8.5 sd above zero**, and that is why this lens
cannot refute. Under honest execution: **11 of 12 days green**, leave-one-day-out worst **+$3,543**,
strip-best-3 **+$3,204**, strip-best-10 **+$790** (the top 10 of 95 trades carry 82% of the net —
concentrated, and honestly so, for a 2R system at a 51.6% hit rate).

## Disposition

| Lead | Verdict | The test |
|---|---|---|
| **ODR survives correct pricing** | **LIVE finding (correction accepted)** | Fee is $1.50/RT, not $5. Linear correction `+3.50 × n`: +$4,169 → **+$4,620 on 129 trades**; my own re-derivation +$4,688 → **+$5,139**. The published number was **under**-stated by $451. |
| **ODR survives realistic execution** | **HOLDS** | 250 ms first-touch print race, spread crossed on entry, stop filled at the worst print in the flush window, time-cap crossed out, sequential: **+$4,435 / 95 trades / +$46.69 a trade / 11 of 12 days green / LOO worst +$3,543**. Execution bill **$5.18/trade** against a $52.42 gross. Its stop-slippage share is **$146 over 12 days**, and the tape-derived flush (1.62 pt) is within 11% of the desk's live measured stop slippage in this window (1.82 pt, n=90). |
| **"5s bars are unsafe here"** | **REFUTED for this gate** | Tick race vs 5s-bar model on identical days: **−$30 on $4,957 (0.6%)**. A 54.6 pt stop is far outside a 5s bar's range, so there is no intrabar ambiguity to resolve. The 87% flush-loss finding does not generalise to 2×ATR stops. |
| **"overlapping positions inflate it"** | **REFUTED** | `rider.py` was already sequential (`k < last` on the exit bar); re-imposing sequencing on *tick-resolved* exit times moves n from 94 to 95, not to 129. Occupancy 101% of the window, 7.9 trades/day. |
| **Deployable as a tournament gate at its own geometry** | **REFUTED** | `scaleout_slots()` forces `stop_atr_mult=1.0` on every live path (`slot_strategy.py:294,308,319,324`); a 2.0× stop exists only in the shadow slate; `exit_scalp` couples target to stop width. At the live 1.0×ATR stop the same entries earn **+$3,183 on 181 trades = +$17.59/trade**, a **62% per-trade haircut** at double the fill count. The quiet-tape clip additionally fires on **34–41%** of entries, replacing a $222 target with $40/$60. |
| **Deployable alongside the day-rider on the shared account** | **REFUTED as configured — PARKED pending isolation** | **49% of entries (47/95) open inside the day-rider's 13:38–15:00 live window; 2.6 direction flips a day; 34% of the colliding entries are opposite the day-rider's own direction rule.** Same class as the 08-06 cascade (shared DUQ191770, IBKR nets). **REVIVE IF:** it runs in its own account or the desk gains per-strategy position isolation, and the "does every live STOP have a slot?" auditor is built. |
| **The headline is precise** | **PARKED — treat ±$900 as fill noise** | Pure-nuisance execution sweep (latency 100 ms–2 s, cadence 4/5/6 min) spans **$3,291–$5,106, sd $519**, and is **non-monotone in latency** (0 ms fills earn $3,762, 1000 ms fills earn $4,938). Quote it as **"about +$4.4k ± $0.9k on 95 verified trades"**, never as +$4,169. **REVIVE/PROMOTE IF:** 200 shadow trades reproduce +0.15R at the desk's real ~1 s loop latency. |

## What I would tell the operator in one line

**The fee correction makes it better, the tick race barely moves it, and the slippage it actually causes
is $12 a session — so on cost and execution this survives. It dies on plumbing, not on money:** the live
slate has no code path to the 2×ATR stop the edge depends on (costing 62% of the per-trade edge), and a
second always-in desk inside the day-rider's window on a netted account is the 08-06 incident waiting to
happen.
