# REHAB — `chandelier` / `give-back` (the managed-profit exit path)

**What is on trial:** not a gate — an **exit mechanism**. `exit_chandelier` (tightening ATR trail),
`exit_chandelier_lock` (loose-then-lock trend trail) and `exit_giveback` (dollar ratchet), i.e. the
`CHANDELIER` and `GIVEBACK` exit reasons.
**Symptom on the roster:** 2026-07-10 → 07-30 these two reasons booked **145 fires for +$7,156**
(GIVEBACK 81 / +$2,332 · CHANDELIER 64 / +$4,823.5). GIVEBACK last fired **2026-07-27**; CHANDELIER last
fired meaningfully **2026-07-30**. Across 2026-08-03 → 08-07 the whole book produced **one** chandelier exit
(+$50) out of 110 closes. The week is binary: **71 STOP / −$2,600.5 with zero winning stops, 34 TARGET /
+$1,794, 1 CHANDELIER / +$50, 2 MANUAL_CLAIM / +$79.5, 2 MAX_HOLD / −$255.5 = −$932.50.**
**Tape:** MNQ. **20 sessions 2026-07-15 → 08-07**, 495 signals / 990 lots. **11 of those sessions are
tick-honest** (07-24, 07-27…07-31, 08-03…08-07 — `capture.db.ticks` + `data/tape/ticks/MNQ/*.parquet`,
15.4M prints); the other 9 replay on 5s bars. All 5 of the symptom week are tick-honest.
**Costs:** **$2.00/pt**, **$1.50 per lot per round trip** (venue truth — every `fees_usd` row is 1.50),
exit slippage **0.25 pt** (calibrated below, and swept to 2.0 pt).
**Reproduce:** `PYTHONPATH=src:scratchpad .venv/bin/python scratchpad/<script>.py`. **Harness:** `scratchpad/chand_lib.py` (tape + ATR/ER reconstruction + the *shipped* deciders),
`chand_tick.py` (print-by-print), `chand_fast.py` (1-second precompute for the sweeps),
`chand_desk.py` (**slot-occupancy-honest** replay), `chand_parity.py`, `chand_forfeit.py`,
`chand_sweep.py`, `chand_pairs.py`, `chand_master.py`.

---

## VERDICT (up front)

> ### 1. `GIVEBACK` → **TRULY-RETIRE.** It is not "below its arm threshold" — it is **switched off in code**, and every attempt to bring it back loses money.
> ### 2. `CHANDELIER` as a blanket restore (the pre-08-01 shape) → **REJECT.** Once you account for the fact that a trailing Lot B *holds the slot and blocks the next signal*, restoring it is **worse than what is deployed**: −$3,433 vs −$2,932 over 20 sessions, losing in **20 of 20** leave-one-day-out folds.
> ### 3. What the desk actually forfeited is **not the trail — it is the WIDTH**, and only in one regime → **REGIME-DEPENDENT, SHIP THE WIDTH.** In **ER30 ≥ 0.25 and ATR14 ≥ 22** (84 of 495 signals, 17%), moving Lot B from the deployed rungs to a **wide rung** is worth **+$3,049 over 20 sessions, positive in 20/20 LODO folds, better in all 4 ISO weeks, and better OOS**. Same regime gate, same Lot A, only the Lot-B shape varied: **fixed 6R +$3,049 · fixed 4R +$2,801 · lock-chandelier 3.5/6.0/0.5 +$2,144 · lock 3.5/8.0/0.5 +$1,736 · chandelier k1.5 +$761 · give-back 50/40 +$581.** The fix is the **rung**, not the machinery. **⚠ Read §5.2 before you size it: 6 of 16 sessions in that cell are green and two days (07-27, 07-23) carry two-thirds of the edge.**
> ### 4. The bleed is **SIGNAL/BASE, not EXIT.** The best exit policy I could prove takes the archive from −$2,932 to **+$117** (break-even) and this week from −$1,073 to **−$643**. Against a 200-trial random-side null the deployed desk sits at the **67th percentile** and the fixed desk at the **88th** — neither clears 95.
> ### 5. Two malfunctions found and normalized, worth **+$262 / −$131** this week, one of them **new and previously unreported** (a 122× ATR poisoning that left both stop and both targets unreachable).

---

## 0. THE HARNESS, AND WHY YOU CAN TRUST IT

### 0.1 The ATR reconstruction is exact

Nothing in `trades` stores the risk unit, so every number here depends on rebuilding `entry_atr` as the
live desk read it. `chand_lib` folds `capture.db`'s 5s bars into 1-minute bars exactly as `agg.MinuteBars`
does and runs the **shipped, halt-aware** `deciders._atr` (`_ATR_CONTIGUOUS_S = 90`) over completed bars only.

Test: for every non-NIPC lot that exited on a STOP, `|exit − entry| − ATR(t₀)` is the realised stop
slippage. It should be a small positive number.

| ATR read at | n | median residual | mean |
|---|---|---|---|
| **t₀ (entry fill)** | **264** | **+0.27 pt** | +0.64 pt |
| t₀ − 30s | 264 | +0.56 | +0.95 |
| t₀ − 60s | 264 | +0.72 | +1.11 |
| t₀ − 120s | 264 | +1.16 | +1.57 |

A 0.27 pt median residual on a ~20 pt ATR is **1.3%**. The reconstruction is right and the read time is right.
NIPC carries its own R (`|entry − pullback-extreme ∓ 4pt|`, not ATR) so for NIPC I back R out of the ledger
itself — A-target/2.0, B-target/2.5, stop distance — and the three estimators agree to ≤1.7 pt on every signal.

### 0.2 Parity — the engine reproduces the booked week

Replaying the **deployed** config over the real prints for 08-03…08-07:

| | booked | tick replay | diff |
|---|---|---|---|
| all 110 live lots | **−$932.50** | −$848.60 | +$83.90 |
| exit reason agreement | | **104 / 110** | |

All six disagreements are named and explained in Movement 1 (2 malfunctions, 2 operator claims, 2 stop-touch
cases). Excluding those, the replay reproduces the booked week to **+$69 on 104 lots = 0.33 pt/lot**, which is
where the 0.25 pt slippage constant comes from. Slippage sweep on the same basis: 0.00 → −$121, **0.25 → −$174**,
0.50 → −$227, 1.00 → −$333 (all vs booked −$756.5 ex-malfunction).

### 0.3 ⚠ THREE DEFECTS IN MY OWN FIRST-PASS METHOD — found, fixed, and reported because they would have poisoned the answer

**(a) Minute-key entry clustering merged distinct signals.** My first pass keyed a "signal" on
`(gate, side, minute)`. On 08-05 `grind_long` fired twice inside 13:33 (13:33:24 and 13:33:51 at different
prices) and four lots collapsed into one entry with the wrong entry price — which manufactured a phantom
"707 prints past the stop" malfunction that does not exist. Fixed to a **3-second cluster** (the real A/B fill
gap is ~100 ms). Entry count 56 → 58 for the week, 468 → 495 for the archive.

**(b) 5s-bar replay is systematically pessimistic and it matters.** On 3 of 110 lots a single 5s bar
contains both the stop and the target (08-07 12:30:00: open 29667.25, **low 29647.5, high 29740.5** — the
08:30 ET release). Bar replay resolves stop-first and books a loss where the live 1 Hz desk banked
+$108.50. The full tick engine cuts these from 3 to 1. **Everything headline in this report is run on ticks
where ticks exist**; the sweeps use a 1-second precompute (level crossings exact to the second) which is
uniformly ~$500/archive *more* pessimistic than the tick engine but preserves every ranking.

**(c) ★ The big one: unconstrained scoring inflates every trailing exit.** The obvious way to compare exits
is to score every signal under every policy. That is **wrong for this desk**, because a slot must be flat to
re-enter. On 2026-07-27 `exhaustion_short` fired **13 times inside one down-leg**; unconstrained, a wide trail
books that single move thirteen times over. My first-pass numbers said "no profit exit at all" was worth
**+$13,540** over the archive. Replayed with **one position per sub-slot** (`chand_desk.run_desk`) the same
policy is **−$1,058**. The artifact was worth **$14,600**. Every headline below is slot-occupancy-honest, and
the unconstrained number is shown alongside it wherever it differs, so you can see the size of the trap.

---

## MOVEMENT 1 — NORMALIZE THE MALFUNCTIONS

### M1 ★ NEW AND UNREPORTED: a 122× ATR poisoning that removed the stop *and* both targets (2026-08-04 22:02)

Trades **538 / 539** (`abs_veto_short_A/B`, opened 22:02:01, closed 00:02:02 next day, **MAX_HOLD**,
**−$124.50 / −$131.00**). This is the largest single loss of the week and it has never been attributed.

The tournament log at the fill:

```
22:02:01,152 tournament abs_veto: abs_veto_short_A clean thrust after 55s → OPEN @29789.25
22:02:01,462 placeOrder StopLimitOrder(orderId=1505, action='BUY', lmtPrice=31658.0, auxPrice=31638.0, tif='GTC', orderRef='stp-000001')
22:02:01,616 placeOrder StopLimitOrder(orderId=1506, action='BUY', lmtPrice=31654.5, auxPrice=31634.5, tif='GTC', orderRef='stp-000002')
```

The protective stops were armed **1,848.25 points** above the entries. `safety.arm_stop` places at
`entry + 1.0·entry_atr`, so **the desk read ATR = 1848.25 pt**. The true halt-aware ATR at 22:02:01 is
**14.73 pt** — a factor of **125**.

Independent arithmetic for where 1848.25 comes from: ATR-14 = (13 ordinary TRs + one poisoned TR)/14.
With 13 TRs at the true ~13.8 pt, the poisoned bar's true range must be **25,696 pt** — which is exactly
`29,800 (MNQ) − 4,104 (MGC at 22:00 on 08-04)`. **A gold bar was folded into the MNQ deque.** This is the
`MD_STREAM` multi-symbol leak fixed at 22:07 that night by commit `d4984cc`; the commit header quotes
"ATR read 1848.16 against a true 15.11". My reconstruction lands on 1848.25 / 14.73 from the tape alone.

**What has not been written down before is the second-order damage.** The desk restarted at 22:07:21 with
the filter in place — but `reconstruct()` re-adopted the two open slots *with the poisoned `entry_atr`
persisted in `slot_positions`*. So for the next 115 minutes:

* the stop sat 1,848 pt away → effectively **naked**;
* Lot A's target sat at `1.5 × 1848 = 2,772 pt`, Lot B's at `2.5 × 1848 = 4,621 pt` → **unreachable**;
* `atr_split = 22` compares `1848 < 22` → **false**, so the quiet-tape clip also did not apply.

**The position had no exit of any kind.** It rode to the 120-minute `MAX_HOLD`. The tape breached the
*correct* stop level (29,804.5) at **22:05:00**, three minutes after entry — 117 minutes before the flatten,
by which time price was 46 pt further away.

**Normalization (what the loss would have been if the stop had worked): tick-honest STOP at −$31.50 per lot.
Swing +$93.00 / +$99.50 = +$192.50.** Both arms of every comparison in this report are scored on ATR = 14.73,
so no configuration is credited for the malfunction.

*Third-order:* GTC orders `stp-000001/2` were never cancelled and rested ~2,000 pt away for three days until
the 08-07 14:58 orphan sweep (`ORPHAN SWEEP: {'adopted': 2, 'cancelled': 2, 'stop_seq': 2}`). The
still-open gap in `broker_adapter` — *"the desk audits does every SLOT have a live stop, never does every
live STOP have a slot"* — is what let a 122× ATR survive a restart. **Recommendation: on
`reconstruct()`, re-derive `entry_atr` from the tape and reject/re-arm any stop further than `k·ATR`
from entry.**

### M2 — stop-limit orders filling AT their limit, 20 pt through the trigger (2 lots, paper defect)

Cross-confirmed with `rehab_exhaustion_short.md` §M2, which found the same class independently. The desk's
protective order is a `StopLimitOrder` with `lmtPrice = auxPrice + 20` (visible in the 08-04 log above).
Two lots this week filled at the **limit**, i.e. 20 pt past their own trigger, in the first four minutes of
the cash open:

| trade | gate | booked | tape-honest | swing |
|---|---|---|---|---|
| 587 | `exhaustion_short_B` 08-07 13:31 | −$78.00 | −$47.00 | **+$31.00** |
| 576 | `abs_veto_short_B` 08-06 13:33 | −$84.00 | ≈−$45.50 | **+$38.50** |

**+$69.50.**

### M3 — a stop-guard miss that went the desk's WAY (normalized adversely, because honesty runs both directions)

Systematic audit of all 110 lots on real prints (stop level vs every print between entry and exit): 18 lots
traded past their stop before closing; 17 of them closed on a STOP anyway (normal 1–3 pt reaction slippage,
plus the two M2 cases). **One did not.**

Trade **582** (`capitulation_long_B`, 08-07 12:29:58, entry 29662.00, R = 10.36 → stop 29651.64). The tape
printed **through** the stop **12 times, to 4.14 pt below it**, starting 12:30:00.478 — inside the 08:30 ET
release burst (1,702 contracts in one 5s bar). The 1 Hz `note_price` cadence missed it, the desk held, and
banked **+$108.50** ten seconds later. **Normalized to the stop it should have taken: −$22.70. Swing −$131.20.**

Its twin (trade 581, Lot A) went 0.46 pt past on 5 prints, and 08-06's `abs_veto_long_B` went 0.11 pt past on
1 print — both **inside** `ticks.round_stop`'s directional loosening, so **not** normalized. 08-06's
`nipc_short_A` came 0.50 pt short of its stop; already covered by `rehab_nipc_short.md` and not double-counted.

### M4 — MANUAL_CLAIM ×2: flagged, NOT credited

Trades 528/535 (`abs_veto_long_B`, 08-04, +$50.50 / +$29.00) were the operator's dashboard "Claim profit"
button. The shipped config would have banked **+$86.50 / +$58.00**. Operator P&L is real P&L; I have not
credited the **+$65.00**. Recorded so it isn't mistaken for machine behaviour.

### M5 — no naked rides, no STOP_UNFILLED, and one thing I could not audit

Zero `STOP_UNFILLED` this week (there were 24 between 07-21 and 07-27). Holds are 0.2 s to 5 min except the
M1 pair. **⚠ Honest limitation:** `orders` contains no `stp-*` rows at all (protective stops are only visible
via broker fills and the systemd journal), so per-trade stop *coverage* cannot be audited from the store —
only from the fact that 71 of 110 closed on a stop-shaped exit plus the journal reconstruction above.

---

## MOVEMENT 2 — CORRECTED-COST RECONSTRUCTION

| step | n lots | net | note |
|---|---|---|---|
| **Venue truth** (tournament book, 08-03…08-07, ex `day_rider_crossdesk`) | 110 | **−$932.50** | as booked |
| − M1 MGC bar-leak: stop restored to true ATR | 110 | −$740.00 | +$192.50 |
| − M2 two stop-limits filled 20 pt through trigger | 110 | −$670.50 | +$69.50 |
| − M3 stop-guard miss that PAID, normalized to the stop | 110 | **−$801.70** | −$131.20 |
| *(M4 operator claims — flagged, not credited)* | | | *(+$65 if credited)* |
| **TRUE, malfunction-normalized week** | **110** | **−$801.70** | |
| memo: tick replay of the deployed config on the same lots | 110 | −$848.60 | $47 residual = slippage |

`day_rider_crossdesk` (2 lots, −$95.50, 08-06 `CROSS_DESK_FLATTEN`) is a different desk and is excluded
throughout; the full-desk week is −$1,028.00.

### What the 34 TARGET exits were actually worth under the pre-08-01 management — **the scope's central question, answered NO**

Repriced on real prints, same entries, same lots:

| subset | booked | deployed replay | **pre-08-01 managed profit** | give-back 50/40 | regime-keyed fix |
|---|---|---|---|---|---|
| the **34 TARGET** lots | **+$1,794.0** | +$1,527.5 | **+$1,472.0** | +$1,393.0 | +$1,720.6 |
| the **71 STOP** lots | −$2,600.5 | −$2,510.6 | −$2,260.0 | −$2,263.4 | −$2,403.2 |
| the 1 CHANDELIER lot | +$50.0 | +$53.0 | −$66.8 | +$53.0 | −$66.8 |
| **all 110** | **−$932.5** | −$848.6 | **−$387.7** | −$839.3 | −$402.3 |

> **The premise of the rehab request is falsified on its own terms.** Handing this week's 34 winners to the
> pre-08-01 chandelier/give-back management makes them **worth $322 LESS**, not more. The −$460.9 the
> managed-profit arm gains on the whole book comes **entirely from the STOP side** (+$340.5: the trail cuts
> some losers before 1R) and from the 08-04 normalization — **not** from captured runners.

Why: the median booked winner had already given the desk everything it was going to give. Measured with no
profit exit at all (1R stop, 120-min cap), the 34 winners' excursion profile is bimodal — 18 of 34 eventually
reach ≥6R, but **19 of those 34 lots round-trip all the way back to the 1R stop before the 2-hour cap**, and
the pre-08-01 trail (`k=1.5` continuous, or `3.5/6.0/0.5` lock) sits far enough from price that on a 10–16 pt
R it waits through the entire retrace. Booked +$1,794 → hold-with-no-target +$4,416 is a **cherry-picked
number** (it conditions on lots that happened to win) and is quoted here only to show why it is not evidence.

---

## MOVEMENT 3 — ROOT CAUSE: BASE, EXIT, or SIGNAL?

### 3.1 Why the machinery went silent — a code-and-commit-level answer, not a threshold one

The scope's hypothesis is that "the arm threshold is simply never being reached". **It is not a threshold
problem. On 93% of this week's positions the chandelier is not in the code path at all, and the give-back
cannot execute under any tape.**

**Where the deployed config routes every Lot-B position:**

| routed to | this week (58) | archive (495) |
|---|---|---|
| quiet-tape clip (`atr_split 22` → `loclip`) | **24 (41%)** | 179 (36%) |
| fixed 2.5R scalp (`nipc` 2.5, `abs_veto_short` 2.5) | **28 (48%)** | 32 |
| fixed 1.5R scalp (`abs_veto_long`) | 2 | 15 |
| `chand` k1.5 ("tight") | 2 | 237 |
| `chandelier_lock` 3.5/6.0/0.5 ("wide") | 2 | 32 |
| **any chandelier at all** | **4 of 58 (7%)** | 269 of 495 (54%) |

**Four eligible positions. One fired.** And the one that fired — trade 589, `exhaustion_short_B`, 08-07
14:48, +$50.00 — is the only entry all week in a gate with a chandelier rung **and** an entry ATR above the
split (**ATR = 32.38**). The mechanism is fully determined.

Two independent pre-emptors, and the scope names only one:

1. **The numeric `b` rungs** (the scope's hypothesis) — 30 of 58. Correct, but it is not "every family":
   `grind_long` still carries `wide`, and `capitulation_long` / `exhaustion_short` / `rgv_short` still carry
   `tight`.
2. **The quiet-tape clip** (`slot_strategy._manage`, 2026-08-02) — 24 of 58, and this one is *structural*:
   ```python
   if spec.atr_split and self._exit_lo.get(spec.tag):
       if spec.lo_target_usd and ...: return "TARGET"
       if spec.lo_target_r  and ...: return "TARGET"
       return None                     # <-- returns BEFORE the chandelier block is ever reached
   ```
   It runs **first** and returns unconditionally. Any gate with `atr_split` set and `ATR < 22` has no
   chandelier, no give-back, no adaptive selector — whatever its `b` rung says. Entry-ATR median this week
   is **20.1 pt** (p25 14.5, p75 34.2); **55%** of all entries — and **73% of the 33 non-NIPC entries** —
   are below the split.

**And `atr_split = 22` keys on the wrong variable.** Over the archive, of the 174 entries with ER30 ≥ 0.30,
**66% have ATR < 22 and get clipped** — and of the 321 entries with ER30 < 0.30, **also 66%**. The clip's
selector is **statistically independent of the regime it exists to protect against.**

**GIVEBACK is not silent — it is switched off, twice over:**

| date | change | effect |
|---|---|---|
| **2026-07-27 16:23** | commit `da98af0`, "regime-3-exit selector LIVE roster-wide" sets `adaptive_exit=True` on every spec | `_manage`'s overlay is guarded by `if reason is None and spec.giveback_enabled and **not spec.adaptive_exit**` → **give-back dies.** Its last live fire is **2026-07-27.** |
| **2026-07-29 16:20** | systemd drop-in `/etc/systemd/system/gazbot7-tournament.service.d/scaleout.conf` → `GAZBOT7_TOURNAMENT_SLATE=scaleout` | `scaleout_slots` / `_lot_b` hard-set `giveback_enabled=False` on **all 16** sub-slots → give-back becomes **structurally impossible**. |
| **2026-08-01 13:23 / 14:08** | `exit_overrides` moves `exhaustion_short` and `abs_veto_*` from `"tight"` to numeric rungs | chandelier leaves those gates |
| **~2026-08-02** | `atr_split: 22` + `lo` clip added | chandelier pre-empted on the majority of the rest |

`data/config_journal.jsonl` confirms it independently: **16 startups, 16 slots each, `giveback_enabled` is
`false` on 256 of 256 resolved specs.** The scope's read that the specs "still resolve" the machinery is
half right — `chandelier`/`chandelier_lock` do resolve on 4 of 16 slots; **give-back resolves on none.**

**A third cause no config can fix: 61% of the July give-back book came from gates that no longer exist.**

| | on today's 8-gate roster | retired gates |
|---|---|---|
| CHANDELIER 07-10…07-30 (+$4,773.5) | +$3,525.5 (74%) | +$1,248 (`thrust`, `grind`, `rgv`, `thrust_short`) |
| GIVEBACK 07-10…07-30 (+$2,332.0) | +$899.5 (39%) | **+$1,432.5 (61%)** — `rgv_long` alone was 30 fires / +$847 |

### 3.2 EXIT or SIGNAL? — the decomposition

Slot-occupancy-honest, full archive, 20 sessions:

| arm | lots taken | net | win% | avg hold | LODO folds beating deployed |
|---|---|---|---|---|---|
| **deployed (as shipped)** | 924 | **−$2,932** | 40.6% | 4.0 min | — |
| pre-08-01 managed profit (Lot B trails) | 890 | **−$3,433** | 39.0% | 5.4 min | **0 / 20** |
| give-back 50/40 on Lot B | 924 | −$4,425 | 42.0% | 3.8 min | **0 / 20** |
| clip everywhere (A $40 / B 1.75R·$60) | 936 | −$3,121 | 40.5% | 3.6 min | 3 / 20 |
| no profit exit (1R stop + 120-min cap) | 688 | −$1,058 | 11.6% | 23.3 min | 19 / 20 |
| **regime-keyed: ER≥.25 & ATR≥22 → A 2.5R / B 6.0R, else clip (NIPC untouched)** | 897 | **+$117** | 37.6% | 5.4 min | **20 / 20** |
| same, but Lot B = lock-chandelier 3.5/6.0/0.5 | 897 | −$788 | 37.7% | 5.0 min | **20 / 20** |
| same, but Lot B = 4.0R | 905 | −$131 | 37.8% | 4.9 min | **20 / 20** |
| same, but Lot B = chandelier k1.5 | 908 | −$2,171 | 39.5% | 4.3 min | 20 / 20 |
| same, but Lot B = give-back 50/40 | 910 | −$2,351 | 40.3% | 4.1 min | 17 / 20 |

**Read that carefully.** The best exit policy I can prove takes the desk from **−$2,932 to break-even**.
It does not make the desk profitable. The bleed is not the exit.

**The signal test.** 200-trial random-side null — same timestamps, same entries, same exits, coin-flip
direction:

| arm | real | null mean | null sd | null p95 | **percentile** |
|---|---|---|---|---|---|
| deployed exits, all entries | −$3,528 | −$4,389 | $1,780 | −$1,238 | **67th** |
| regime-keyed exits, all entries | −$146 | −$2,681 | $2,107 | +$948 | **88th** |
| regime-keyed, ER≥.30 & ATR≥22 entries only | +$2,971 | **+$376** | $1,493 | +$2,913 | **95.5th** |

*(unconstrained basis, so the levels are inflated; the percentiles are the point)*

The desk's direction call is better than a coin flip but **does not clear the 95th percentile** except on the
narrow trend-capable slice — and there the **null's own mean is +$376**, i.e. most of that slice's edge is the
regime and the exit, not the gates' opinion about which way to lean. **VERDICT on cause: EXIT explains ~$3,000
over 20 sessions and is worth fixing; SIGNAL explains the remaining ~$3,000 and is not fixed by anything in
this report.** The BASE config (fees, 1-ATR stop, 2-lot scale-out) is not the problem — at $1.50/RT friction
is $1,485 of the 990-lot archive.

---

## MOVEMENT 4 — FILTERS THAT KEEP THE WINNERS, AND THE FAKE WINS I REJECTED

Baseline for this section = the regime-keyed exit on all entries (n=990 unconstrained, −$146, 385 winning
lots worth $25,842 gross).

| filter | lots kept | net | saved | **winners kept** | $/lot kept | **$/lot DROPPED** | LODO worst |
|---|---|---|---|---|---|---|---|
| **not `violent-whipsaw`** (ATR≥22 & ER<.30) | 774 | +$2,543 | **+$2,690** | **78%** | +3.29 | **−12.45** | +$2,014 |
| ER30 ≥ 0.20 | 636 | +$2,135 | +$2,282 | 64% | +3.36 | −6.45 | +$1,716 |
| ER30 ≥ 0.25 | 514 | +$2,808 | +$2,955 | 51% | +5.46 | −6.21 | +$2,149 |
| ER30 ≥ 0.30 | 348 | +$2,946 | +$3,092 | 34% | +8.46 | −4.82 | +$1,944 |
| ER≥.30 **&** ATR≥22 (trade the home regime only) | 120 | +$2,971 | +$3,117 | **10%** | +24.76 | −3.58 | +$2,015 |
| US session only (13:30–20:00 UTC) | 600 | +$890 | +$1,037 | 61% | +1.48 | −2.66 | +$566 |
| ATR ≥ 22 | 336 | +$281 | +$427 | 32% | +0.84 | −0.65 | **−$271** |

**The test I apply:** a genuine filter drops a population whose per-lot expectancy is *worse* than the book's;
a fake one wins by amputating winners. The `$/lot DROPPED` column is the discriminator, and it is why I
deliberately ran four filters I expected to be fake:

| REJECTED fake | net | saved | winners kept | **$/lot DROPPED** | why rejected |
|---|---|---|---|---|---|
| drop `abs_veto_long` | −$1,509 | **−$1,362** | 85% | **+11.95** | drops the one profitable gate — self-identifies |
| LONGs only | −$2,368 | −$2,221 | 58% | +5.61 | self-identifies |
| drop 12:00–14:00 UTC | −$2,068 | −$1,922 | 79% | +8.98 | kills the release window, where the winners are |
| **SHORTs only** | **+$2,221** | **+$2,368** | 42% | −3.99 | **LOOKS robust (LODO worst +$1,406) — REJECT ANYWAY** |

> ### ★ REJECTED: "SHORTs only". It passes LODO and it is still fake.
> corr(session net drift 13:30–20:00, SHORT-minus-LONG P&L) = **−0.462** across the 20 sessions. The tape fell
> 182 pt net over the window; the "edge" is a **bet on tape direction**, and 07-27 (−376 pt drift, SHORT +$2,596
> vs LONG +$3) and 08-04 (+560 pt, SHORT −$63 vs LONG +$988) are the same trade seen twice. **This is the exact
> class of result the operator's discipline exists to catch and I am flagging it rather than banking it.**

**The one filter I would actually ship** is `not violent-whipsaw` — it keeps **78% of the winning lots**, saves
+$2,690, drops a population running −$12.45/lot, and is positive in 20/20 LODO folds. Note it is *not* the
same as the trend filter: it removes **high-ATR, low-ER** tape (the ATR≥22 & ER<0.30 cell, n=108 entries,
−$2,178 under the deployed config and worse under every trail I tested). **⚠ It is an ENTRY change and
therefore outside this rehab's mandate — recorded for the gate rehabs, not recommended here.**

---

## MOVEMENT 5 — ROBUSTNESS: SEGMENT THE TAPE, THEN PROVE THE RUNGS

### 5.1 The regime taxonomy, and the single cell that carries everything

Regimes are keyed on **ATR14 level + ER30 + range-break position**, computed from *completed* 1-minute bars
at the entry second — no lookahead, and reproducible live from `compute_features`. Single-lot net over the
whole archive (unconstrained; this is the exit *science*, the deployable numbers are slot-honest below):

| Lot-B exit (single lot) | ER<.30 / ATR<22 (n=213) | ER<.30 / ATR≥22 (n=108) | ER≥.30 / ATR<22 (n=114) | **ER≥.30 / ATR≥22 (n=60)** |
|---|---|---|---|---|
| `clip $40` (deployed Lot A shape) | **−$164** *(2nd of 28)* | −$695 *(3rd)* | **+$40** *(1st)* | −$345 ***(26th)*** |
| `clip 1.75R/$60` (deployed Lot B shape) | −$238 *(3rd)* | −$1,995 ***(27th)*** | −$65 *(4th)* | +$676 *(12th)* |
| fixed 1.0R | −$469 | −$985 | −$52 | +$484 |
| fixed 2.5R | −$586 | −$1,633 | −$760 | +$1,203 |
| fixed 4.0R | −$699 | −$1,119 | −$680 | **+$2,113** |
| **fixed 6.0R** | −$761 | −$318 *(1st)* | −$631 | **+$2,517** *(2nd)* |
| `chandelier` k1.5 (deployed "tight") | −$960 | −$1,455 | −$437 | +$76 *(23rd)* |
| `chandelier_lock` 3.5/6.0/0.5 (deployed "wide") | −$1,379 ***(28th)*** | −$1,246 | −$622 | **+$1,768** *(4th)* |
| `chandelier_lock` 3.5/8.0/0.5 | −$722 | −$1,288 | −$189 | **+$2,710** *(1st)* |
| give-back 50/40 | −$1,013 | −$1,490 | −$1,059 | −$41 *(24th)* |
| *segment winner* | R1.25 −$139 | R6.0 −$318 | clip $40 +$40 | lock 3.5/8.0/0.5 +$2,710 |

**The entire managed-profit edge of the desk lives in ONE cell — ER30 ≥ 0.30 and ATR14 ≥ 22 — which is 12%
of signals. There the deployed $40 clip ranks 26th of 28 and the wide rung ranks 1st: a $3,055 swing on 60
entries. In the other three cells the wide trail is 28th, 8th and 14th while the deployed clip is 2nd, 3rd
and 1st.** The deployed config is not wrong about clipping; it is wrong about *when*.

By time of day (the operator's second axis): 56 of those 60 trend-capable entries are **US-session
post-13:30 UTC**, 3 post-close, 1 pre-open. The clock is a *consequence* of ATR, exactly as the discipline says
— ATR≥22 selects the session without being told about it.

### 5.2 Concentration — stated before the good numbers, not after

Inside the trend-capable cell, per-day net for the wide lock-chandelier:

```
07-17  -106 | 07-20  -622 | 07-21   -96 | 07-22  -108 | 07-23  +611 | 07-24  -351
07-26   -49 | 07-27 +1452 | 07-28  +150 | 07-29  +463 | 07-30  +163 | 07-31  -165
08-02   -55 | 08-03   -66 | 08-04  +599 | 08-06   -50
```

**6 of 16 sessions green. 2026-07-27 alone is +$1,452 of the +$1,768.** Attributing the whole
deployed→regime-keyed improvement by gate across the archive: `exhaustion_short` **+$3,515** (of which
**07-27 is +$3,280**), `rgv_short` **+$1,030** (of which **07-23 is +$1,374**), `abs_veto_short` +$767,
`abs_veto_long` +$452, `grind_long` +$353; `grind` −$188 and `rgv` −$148 go the other way; NIPC is $0 by
construction. **Two days carry it.** Strip-the-best inside the cell: the trail-vs-deployed delta survives
stripping the top 5 trades (+$323) and **inverts at the top 8 (−$422)** — the cell's edge rests on 5–7 trades
out of 60.

### 5.3 The full robustness battery on the deployable policy

`REC` = *ER30 ≥ 0.25 and ATR14 ≥ 22 → Lot A 2.5R / Lot B 6.0R; otherwise the existing $40 / 1.75R·$60 clip;
NIPC keeps its own proven 2.0R/2.5R pair.* All slot-occupancy-honest, 1-second engine.

| test | deployed | REC | verdict |
|---|---|---|---|
| full archive, 20 sessions (924 vs 897 lots taken) | −$2,932 | **+$117** | **+$3,049** |
| **leave-one-day-out** (20 folds) | — | **20 / 20 positive**, min **+$1,604**, max +$3,401 | PASS |
| **per ISO week** W29 / W30 / W31 / W32 | −910 / −2,632 / +1,683 / −1,073 | **−840 / −2,587 / +4,187 / −643** | better in **4 / 4** |
| **OOS** (fit 07-15…07-31 → test 08-03…08-07) | IN −$1,859, OUT −$1,073 | IN +$760, **OUT −$643** | PASS (still negative) |
| **strip-the-best** (top 1 / 3 / 8 / 20 of 897 lots) | — | delta +2,781 / +2,374 / +1,546 / **+305** | PASS, thin |
| **cost sensitivity** slip 0.25 / 1.0 / 2.0 pt | −2,932 / −4,318 / −6,166 | **+117 / −1,228 / −3,022** | delta holds (+$3.1k at 2 pt); level breaks ~0.35 pt |
| **fee** $1.50 → $6.00 / RT | −$7,090 | **−$3,919** | ranking holds, level does not |
| **random-side null** (unconstrained basis) | 67th pct | 88th pct | does not clear 95th |

### 5.4 ⚠ THE PARAMETER PLATEAU TEST — FAILED, AND I AM REPORTING IT AS FAILED

The discipline demands a plateau, not a peak. **There isn't one.**

**ER × ATR threshold surface (slot-honest desk net):**

| | ATR≥16 | ATR≥18 | ATR≥20 | **ATR≥22** | **ATR≥24** | ATR≥26 | ATR≥30 |
|---|---|---|---|---|---|---|---|
| ER≥0.15 | −2,232 | −1,918 | −1,873 | −765 | **+23** | −655 | −1,988 |
| ER≥0.20 | −2,183 | −1,732 | −1,666 | −321 | **+173** | −505 | −1,711 |
| **ER≥0.25** | −1,202 | −767 | −896 | **+60** | **+404** | −265 | −1,250 |
| ER≥0.30 | −2,503 | −2,000 | −1,954 | −1,407 | −1,149 | −922 | −1,216 |
| ER≥0.35 | −3,103 | −2,874 | −2,821 | −2,112 | −1,941 | −1,714 | −1,772 |

Only **four cells of thirty-five are positive**, all in a narrow ridge at ATR 22–24. Move one step to ATR≥26
and it is −$265. The ER≥0.30 row — the value I picked first from the segment table — is negative everywhere.

**Lot-B rung inside the home regime (slot-honest):** R1.5 −1,864 → R2.5 −916 → R4.0 −188 → **R6.0 +60** →
R8.0 −234 → R10.0 +660. Monotone-ish to 6R then jagged. Unconstrained it is monotone all the way to R10,
which is the tell that this segment is *defined by two-hour trends* rather than by any optimal target.

**So what survives?** Not the point estimate — the **neighbourhood**:

| family | mean over the parameter block | min | max | vs deployed −$2,932 |
|---|---|---|---|---|
| ATR-keyed split, Lot B = **wide fixed rung (6R)** (5 splits × 4 Lot-A rungs) | **−$899** | −1,593 | +140 | **+$2,033** |
| ER-keyed, Lot B = **6R** (3 ER × 3 ATR) | **−$751** | −1,954 | +404 | **+$2,181** |
| ATR-keyed split, Lot B = **wide lock-chandelier** (20 cells) | **−$2,686** | −3,972 | −1,080 | +$246 |

> **The direction is robust; the knob is not. And note which family survives:** widening Lot B to a **fixed
> 6R rung** is worth ~$2,000 across its whole parameter block. Widening it to the **lock-chandelier** is worth
> $246 — i.e. **essentially nothing**. What the desk forfeited on 08-01/08-02 was the *width*, not the *trail*.

### 5.5 PROVEN Rs vs the operator's GUESS (faders 0.5/1.5 · momentum 1.5/2.5 · trend 2.5/wide)

Every (Lot A, Lot B) pair from a 9 × 15 grid, scored per family **per regime**, guess ranked against 135
combinations:

| family | regime | n | **guess** | rank | best pair | best net |
|---|---|---|---|---|---|---|
| **fader** | ER≥.30 & ATR≥22 | 25 | +$559 | **131 / 135** | 3.0R / 6.0R | **+$4,488** |
| fader | ER≥.30 & ATR<22 | 43 | −$215 | 50 / 135 | clip$40 / lock 3.5/8/0.5 | +$359 |
| fader | ER<.30 & ATR<22 | 88 | −$555 | 46 / 135 | 1.5R / lock 3.5/8/0.5 | +$31 |
| fader | ER<.30 & ATR≥22 | 48 | −$315 | **9 / 135** | 0.5R / lock 3.5/8/0.5 | −$203 |
| **momentum** | ER≥.30 & ATR≥22 | 14 | +$431 | 78 / 135 | 3.0R / lock 3.5/8/0.5 | +$1,495 |
| momentum | ER≥.30 & ATR<22 | 45 | +$53 | 29 / 135 | 1.0R / 1.0R | +$534 |
| momentum | ER<.30 & ATR<22 | 84 | −$371 | 95 / 135 | 3.0R / 6.0R | +$397 |
| momentum | ER<.30 & ATR≥22 | 39 | −$1,083 | 86 / 135 | 1.0R / 1.0R | −$155 |
| **trend** (`grind*`) | ER≥.30 & ATR≥22 | 21 | **−$1,308** | **119 / 135** | 1.0R / 1.0R | −$325 |
| trend | ER<.30 & ATR<22 | 41 | −$841 | **130 / 135** | 1.25R / 1.0R | +$103 |

**Three findings that overturn the cheat-sheet:**

1. **The fader guess (0.5R/1.5R) is the SECOND-WORST of 135 configurations in the one regime where faders
   make money.** `exhaustion_short` / `rgv_short` / `capitulation_long` firing into big-ATR trending tape are
   the desk's biggest runners — a snap-back that becomes the leg — and the guessed tight pair throws away
   **$3,929** on 25 signals. The live config is worse still: `exhaustion_short` sits at `a_r 0.75, b "tight",
   atr_split 22` — the tightest cell available. **The runner capture the desk lost belongs to the FADE gates,
   not the trend gates.**
2. **The fader guess is nearly right (rank 9/135) in violent-whipsaw.** The prior isn't wrong, it is
   *unconditioned*. Same numbers, opposite verdicts, in two regimes.
3. **`grind_long`'s deployed 2.5R / wide-lock ranks 119/135 in its OWN home regime**, at −$1,308, and 130/135
   in chop. The "trend gate gets the wide trail" prior — the thing the 07-26 `lock_r` fine-sweep shipped — is
   **falsified on this tape** (n=21 in-cell; thin, and this contradicts a prior study, so treat as a flag
   rather than a finding).

---

## ★ THE TRYING — EVERY ATTEMPT, INCLUDING THE NULLS AND FAILURES

Twelve things I tried that did **not** work, in the order I tried them:

| # | attempt | result | verdict |
|---|---|---|---|
| 1 | Remove the quiet-tape clip, keep the existing rungs | archive −$3,528 → **−$4,735**; week −$848.6 → **−$1,013.3** | **NULL — worse.** The clip is not the problem on its own |
| 2 | Restore the pre-08-01 managed-profit shape (Lot B trails) | slot-honest −$2,932 → **−$3,433**, **0/20 LODO** | **FAILED — the rehab's own premise** |
| 3 | Reprice this week's 34 TARGETs under that shape | +$1,794 → **+$1,472** | **FAILED — the trail loses on the winners** |
| 4 | Restore `exit_giveback` 50/40 on Lot B | archive **−$4,425**, 0/20 LODO, worst arm tested | **FAILED** |
| 5 | Sweep give-back arm × retrace, 42 configs (arm $30–$120 × retrace $20–$100) | **42 of 42 negative** in every regime; best cell −$1,934 | **NULL — no config exists** |
| 6 | Continuous `exit_chandelier` at k = 1.0 / 1.5 / 2.0 / 2.5 / 3.5 | all in the bottom half; k1.0 = −$3,759, k3.5 = −$3,700 | **NULL** |
| 7 | "No profit exit at all" (1R stop + 120-min cap) | **+$13,540 unconstrained** → **−$1,058** slot-honest | **ARTIFACT — my own bug, $14.6k of it** |
| 8 | Hold-cap sweep 15…240 min | monotone improving to 180 min | **ARTIFACT — same overlap; discarded** |
| 9 | ER≥0.30 as the regime key (my first pick from the segment tables) | slot-honest **−$1,407**; ER≥0.25 is +$60 | **WRONG — corrected, kept for the audit trail** |
| 10 | `lock_r = 8.0` (in-sample best of the lock family, +$4,375 in-cell) | slot-honest **−$1,253** vs lock_r 6.0's −$845 | **REJECTED — overlap + noise** |
| 11 | "SHORTs only" filter (+$2,368 saved, LODO worst +$1,406) | corr with session drift **−0.462** | **REJECTED as a direction bet** |
| 12 | Blanket best-exit across the whole tape (`R6.0`, +$806 single-lot) | −$826 in violent-whipsaw, −$1,079 in clean-trend | **REJECTED — a blanket number is a bug in this report** |

And three things that **did** hold up: the ER×ATR regime key (20/20 LODO), the **wide fixed rung** in the
trend-capable cell (+$2,033 across its whole parameter block), and the finding that the deployed **$40 clip
is already near-optimal** everywhere else (rank 1 of 28 in ER<.30/ATR<22 and in ER≥.30/ATR<22).

---

## MOVEMENT 6 — VERDICT AND EXACT CONFIG

### `GIVEBACK` → **TRULY-RETIRE**

Dominated in every regime, in all 42 sweep cells, in 0/20 LODO folds. It earned +$2,332 in July because it
was the **only** profit exit on trail-less single-lot gates — 61% of that came from `rgv_long`, `grind`,
`rgv`, `thrust_short`, none of which are on the roster. Under the scale-out slate every gate already has a
fixed-R Lot A floor doing that job. **Leave `giveback_enabled=False`. Delete the dead branch in `_manage`
or leave it as documentation, but stop treating its silence as a symptom — it is the design.**

### `CHANDELIER` (the trail machinery) → **REGIME-DEPENDENT / SHADOW**

Not a blanket restore. It is worth **+$246 across its parameter block** — noise — and it *loses* in 3 of the
4 regime cells. Held constant against the regime gate and Lot A, the trail recovers **+$2,144** where the fixed 6R rung
recovers **+$3,049** — the trail is *directionally right and quantitatively second-best*. Keep
`exit_chandelier_lock` in the code (it is the runner-up in the home cell and it is uncapped, which a fixed
rung is not), but **do not re-arm it on the strength of this report.** The tightening `exit_chandelier` k1.5
("tight") recovers only +$761 and the give-back only +$581 — those two are the ones to stop reaching for.

### The WIDTH → **FIXED, ship it**

**Recommended, config-only, no code change** (`data/exit_overrides.json` — the schema already supports it):

```json
{
  "grind_long":        {"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}},
  "capitulation_long": {"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}},
  "exhaustion_short":  {"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}},
  "rgv_short":         {"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}},
  "abs_veto_long":     {"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}},
  "abs_veto_short":    {"a_r": 3.0, "b": 6.0, "atr_split": 24, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}},
  "nipc_long":         {"a_r": 2.0, "b": 2.5},
  "nipc_short":        {"a_r": 2.0, "b": 2.5}
}
```

Two edits only: **`atr_split` 22 → 24**, and every non-NIPC **`b` → `6.0`, `a_r` → `3.0`**. Below the split
nothing changes — the $40 / 1.75R·$60 clip is already the best thing in that regime and it keeps 100% of the
quiet-tape behaviour the 08-02 deploy was built for. **NIPC keeps its own proven 2.0/2.5 pair** (its 270-config
lab explicitly falsified a trailing Lot B; my grid agrees — NIPC deltas are $0 under this change).

Measured, slot-occupancy-honest, with the NIPC carve-out above: **archive −$2,932 → +$92 (+$3,024, 20/20
LODO, min +$1,259)**; pre-window −$1,859 → **+$891**; **symptom week −$1,073 → −$799**.
**⚠ Disclose:** per ISO week this config-only version is better in only **2 of 4** (W31 +4,557 vs +1,683 and
W32 −799 vs −1,073, but W29 −954 vs −910 and W30 −2,712 vs −2,632). It buys most of the edge with none of the
deploy risk; it is not strictly dominant.

**Optional one-field code change (better, needs a deploy):** add `er_split` to `_load_exit_overrides` and gate
the clip on `f.er15 < er_split` **as well as** `f.atr < atr_split`, frozen at entry alongside `_exit_lo`.
With `er_split 0.25 / atr_split 22 / a_r 2.5 / b 6.0`: archive **+$117 (+$3,049, 20/20 LODO, min +$1,604)**,
week **−$643**, and it is the **only** variant better than the deployed config in **all four ISO weeks**.
It beats the config-only version on every axis (archive +$25, week +$156, LODO floor +$345, per-week 4/4 vs
2/4) — the margins are small, but they all point the same way. **Ship the config-only edit today; queue
`er_split` as the follow-up and re-measure before promoting it.**

### Malfunction fixes to ship regardless (highest expected value in this document)

1. **`multislot_core.reconstruct()` must re-derive `entry_atr` from the tape** and refuse to adopt a slot whose
   persisted stop is more than a few ATR from entry. The 08-04 MGC leak was fixed in five minutes; its
   *consequence* survived a restart and cost **$192.50** in one night because a poisoned number was durable.
2. **Close the orphan-stop asymmetry** — `adopt_and_sweep` now answers "does every live STOP have a slot?" at
   startup, but stops 1505/1506 still rested for three days. Run it on a timer, not only at boot.
3. The **stop-limit filling at its limit 20 pt through the trigger** (2 lots this week, ~$70/wk, also found by
   `rehab_exhaustion_short.md`) — either widen `lmtPrice` offset or use a plain STP.

### What this report does NOT claim

* It does not make the desk profitable. Best proven policy = +$117 over 20 sessions (break-even), −$643 on
  the symptom week.
* The parameter plateau test **failed** (4 positive cells of 35; jagged Lot-B rung surface). Only the
  *neighbourhood mean* survives.
* The home-cell edge is **5–7 trades out of 60**, and **two sessions (07-27, 07-23) carry two thirds of it**.
* Entry-side conclusions (`not violent-whipsaw`, ER floors) are outside this rehab's mandate and belong to the
  gate rehabs — they are recorded here, not recommended here.
* 9 of 20 sessions are 5s-bar replay, not tick. Every headline was re-checked on the 11 tick sessions and the
  ranking held (deployed +$50, pre-08-01 +$1,788, regime-keyed +$1,974 on that subset), but the archive-wide
  levels carry that fidelity caveat.
