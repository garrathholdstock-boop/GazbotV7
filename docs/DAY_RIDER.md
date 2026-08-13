# DAY RIDER — the drift strategy as a second desk

**Live in PAPER from 2026-08-06.** Read this before changing anything in `drift.py`, `day_rider.py`,
`day_rider_watchdog.py`, or the two `gazbot7-day-rider*` timers.

It is **not** a tournament gate. It is a separate desk with its own IBKR clients, its own safety, and
its own switch, and it places real (paper) orders every morning it confirms.

---

## 1. The strategy, exactly as validated

```
DETECT   from the 13:30 UTC US cash open:  efficiency >= 0.15  AND  roundtrip >= 0.45
ENTER    2 lots, direction = sign of net. ONE entry per session. No entry after 15:00 UTC.
EXIT     100pt trail, ARMED only once +150pt ahead.  HARD FLAT 20:40 UTC (22:40 Paris).
ASK      a 2xATR reversal off the peak pages the operator 3x / 15 min  ->  DEFAULT IS HOLD.
NEVER    hold overnight. Not a preference — a constraint.
```

Switch: `data/day_rider.env` → `day_rider=on|off`. Off by default; a missing or garbled file reads OFF.

**Record over 31 MNQ sessions:** fires ~16 of 31 days, ~$428/firing day, 81-84% days green,
strip-best-3 +$7,748, +2.29 sd against 30 random-direction seeds (beaten by 1).

**★ `drift.compute()` reproduces the backtest detector on all 31 sessions with ZERO mismatches** —
same confirmation minute, same direction, every day. That equivalence is the whole licence to run it
live. If you change `drift.py`, re-run that check.

---

## 2. Why it is NOT a tournament gate

`multislot_core.py:372` force-flattens **every** position at `cfg.max_hold_minutes = 120`. This holds
from ~13:40 to 20:40 — seven hours.

| | total | battery |
|---|---|---|
| inside the 120-min cap | $7,047 | **FAILS** (beaten by 2 of 30 seeds) |
| uncapped, own service | $13,257 | passes 5/5 |

⚠ **Do NOT "fix" this by raising the global cap.** That same 120-minute cap is what closed the
MD_STREAM incident's 1,848-point-stop shorts at exactly two hours for −$255.50. The tournament keeps its
cap; this runs alone.

---

## 3. Timings, and why each one is where it is

| what | when | why |
|---|---|---|
| anchor | 13:30 UTC | see §5 — the CME anchor gives **zero** detections |
| earliest detect | ~13:38 | metrics are noise below 9 minutes of tape |
| entry cutoff | 15:00 UTC | all 31 validated detections were 13:38-14:09; later entries are untested |
| hard flat | **20:40 UTC** | 21:00 **is** the CME halt — see below |
| halt | 21:00 UTC | nothing can be done after it |

**★★ THE FLAT IS 20:40, NEVER 21:00.** 23:00 Paris is the halt itself: a flatten fired there has no
market to fill into and no retry window — the one failure mode that turns "never hold overnight" from a
constraint into a hope. 20:40 leaves **20 automatic minute-tick retries**, and the flatten verifies the
fill and alarms if it did not complete.

Measured cost of the earlier flat: **$149 of $13,257 (1.1%)**, and days-green *improves* 81% → 84%.
Moving it to 22:00 Paris instead would cost $2,309, so 20:40 is the right point on that curve.

---

## 4. The exit — and why it is nearly exit-proof

**25 exit variants were tested. Holding to the flat beat or matched every one.** Do not re-run these.

```
HOLD to the flat            $13,257  (baseline)
armed trail +150/100pt      +$2,320  <- the ONLY improvement found
fixed 400pt target          within $33 of the trail
stops, 7 widths             ALL negative; cost/benefit -$6,957 to -$11,572
give-back 25/35/50/65%      ~$0
progress / underwater       <= baseline everywhere
reactive direction-change   best is -$3,115
```

**Why stops cannot work here:** winner and loser drawdowns overlap almost completely — winner MAEs run
2…511pt, loser MAEs 66…778pt, and **eight winners drew more than 200pt and still won**. A stop tight
enough to cut losers kills more winners than it saves; one wide enough to be safe never fires. A 400pt
stop's worst day (−$1,603) is *worse* than running naked (−$1,531).

**The tail is the price of the strategy.** The three worst days ran up only 187, 33 and 80pt before
dying, so no exit mechanism of any kind reaches them. The −$2,220 day and the +$1,884 day are the same
phenomenon.

**Therefore default-HOLD on the approval exit is profit-maximising, not merely cautious.**

---

## 5. The anchor — tested, do not re-litigate

Operator asked whether to measure from the midnight COMEX/CME open instead. Tested. Medians at 13:40
across 33 sessions:

| anchor | tape | range | path | efficiency | roundtrip |
|---|---|---|---|---|---|
| 13:30 cash | 11 min | 165pt | 241pt | **0.239** | 0.439 |
| 22:00 CME | 941 min | 455pt | 5921pt | **0.048** | 0.689 |

The CME anchor produced **zero detections in 33 sessions**. Not worse — structurally incompatible:
15h40m of overnight oscillation makes the path ~25x longer, collapsing efficiency an order of magnitude
below the 0.15 floor. Adopting it means re-deriving the whole strategy, not changing a constant.

---

## 6. Safety — four layers, because it inherits none

1. **HEARTBEAT + INDEPENDENT WATCHDOG.** `scripts/day_rider_watchdog.py`, clientId 5, every 2 min,
   **flatten-only** — it cannot open, size or reverse. It flattens if the venue holds a position while
   the strategy is not managing it. Independent so a hung strategy cannot disable its own safety.
   ⚠ It requires **both** a fresh heartbeat **and `venue_ok`**. Found live: a clientId collision made
   the strategy's venue connection fail; it correctly took no action *and still stamped a heartbeat*.
   Reading that as "managed" would recreate the naked-position bug through the watchdog's own health
   signal. `venue_ok` defaults to **False** if a caller forgets to set it.
2. **A 600pt VENUE STOP — last resort only, not a trading decision.** Deliberately wider than any
   drawdown in the sample (deepest recovery: 511pt) so it should never fire on a live trade. It is
   insurance against losing the watchdog too, priced at ~zero historically.
3. **RESTART-SAFE ATOMIC STATE.** Entry, direction, peak and the pending-exit token persist every loop,
   so a bounce mid-trade resumes managing rather than orphaning. Losing the peak would silently reset
   the trail.
4. **FAIL-CLOSED.** Any exception, unreadable tape, or venue/state disagreement ⇒ no action + alarm. It
   never opens a position it cannot verify and never sizes from a stale read.

**Client IDs:** core 0 · md 2 · **day-rider 4** · **watchdog 5** · eod 6 · checks 8 · depth 97.

---

## 7. The operator-approval exit

```
2xATR reversal off the peak  ->  Telegram #1
                                 #2 at +15 min
                                 #3 at +30 min
  /sell  ->  service flattens on its next tick (<=60s)
  /hold  ->  dismissed, rides on
  silence -> HOLDS to the 20:40 flat. NEVER escalates to a sell.
```

**★ The bot does not place orders.** `/sell` and `/hold` write a token-matched decision file; the
service flattens through the order path that already carries `safe_flatten_verdict`, venue
reconciliation and fail-closed handling. `telegram_bot.py`'s own rule was that per-gate on/off is the
only mutating command — this is the second, so its blast radius is one file write.

**★ Consent is token-matched.** A `/sell` typed at 20:00 cannot sit on disk and flatten tomorrow's fresh
position. A stray `/sell` with nothing pending is refused.

The ask trigger is armed **not** because it makes money (it does not — see §4) but so a genuine reversal
reaches the operator instead of being silently ignored or silently acted on.

---

## 8. Dashboard

`/v7/router` carries a **"Which way is the day leaning?"** panel above the untradeable meter. Both bars
are drawn as a fraction of their own threshold, so a bar reaching 100% *is* confirmation — the operator
watches it build rather than being told only at the instant it fires, and it states exactly what must
change to confirm.

It calls the same `gazbot7.drift.read()` the service calls. **One source of truth** — the panel can
never show one thing while the desk acts on another.

---

## 9. Honest limits

- **31 in-sample sessions after ~60 configurations.** Clearing a pre-registered bar on the 60th attempt
  is weaker evidence than clearing it on the first. Treat the first weeks as evidence, not proof.
- **No-stop is the best config**, which is operationally uncomfortable, and the stop sweep is
  non-monotonic — a noise signature. Some of "no stop is best" is luck.
- **The trail is checked once a minute**, matching the minute bars it was validated on, so a fast
  reversal can slip past the 100pt level. Expect live fills to differ from backtest fills.
- **MGC would need a different anchor.** Gold moves all day — Asia 00-02 UTC is nearly as active as its
  US session — so 13:30 is meaningless for it. And six independent attacks on MGC direction are null:
  moving is not the same as tradeable.


---

## APPENDIX — live operational facts (moved from CLAUDE.md, 2026-08-13)

The scoping notes above predate deployment. THIS is what the running service actually does; the
session bootstrap now carries only a summary and points here.

A new strategy runs **as its own service**, not as a tournament gate, and it places real (paper) orders.
`gazbot7-day-rider.timer` (every minute) + `gazbot7-day-rider-watchdog.timer` (every 2 min).
Switch: `data/day_rider.env` -> `day_rider=on|off`. **Currently ON.**
★ Deployed 08-05 at 15:54 UTC, i.e. AFTER that day's 15:00 entry cutoff — so it ticked and heartbeat
from 08-05 but its **first tradeable session is 2026-08-06**. Do not read an 08-05 no-entry as a miss.

```
DETECT  from the 13:30 UTC cash open: efficiency >=0.15 AND roundtrip >=0.45  (gazbot7/drift.py)
ENTER   2 lots, direction = sign of net. ONE entry per session. No entry after 15:00 UTC.
EXIT    trail 100pt, ARMED only once +150pt ahead. HARD FLAT 20:40 UTC.
ASK     a 2xATR reversal off the peak pages the operator 3x/15min -> DEFAULT IS HOLD.
```

**★ WHY IT IS NOT A GATE:** `multislot_core.py:372` force-flattens every position at
`max_hold_minutes=120`; this holds ~7h. Inside that cap it earns $7,047 and FAILS the battery; uncapped
$13,257 and passes 5/5. Do NOT "fix" this by raising the global cap — that cap is what limited the
MD_STREAM incident to −$255.50.

**★★ FLAT AT 20:40 UTC (22:40 Paris), NEVER 21:00.** 21:00 UTC *is* the CME halt — a flatten fired then
has no market and no retry. 20:40 leaves 20 minute-ticks of retry. Cost: $149 of $13,257; days-green
81%→84%. **STANDING OPERATOR RULE: NEVER HOLD OVERNIGHT. EVER.**

**★ THE ANCHOR IS THE CASH OPEN, and this was tested — do not re-litigate.** A 22:00 UTC (midnight
Paris/CME) anchor gives ZERO detections in 33 sessions: 15h40m of overnight chop makes the path ~25x
longer so efficiency collapses to 0.048 vs the 0.15 floor. Full numbers pinned in `drift.py`.

**★ SAFETY, since it inherits none of the tournament's:** heartbeat + an INDEPENDENT flatten-only
watchdog (clientId 5) that requires BOTH a fresh heartbeat AND `venue_ok` — a tick that could not reach
IBKR still stamps a heartbeat, and treating that as "managed" would recreate the naked-position bug.
600pt venue stop is last-resort insurance only (a 400pt stop costs $3,451 and *worsens* the worst day).
Restart-safe atomic state. Fail-closed everywhere; a garbled switch reads OFF.

**★★2026-08-13 — FOUR FIXES AFTER IT SOLD 8 LOTS IT DID NOT OWN.** Full account in
`docs/SESSION_2026-08-13.md`; all live and tested, but **none has traded yet** — 08-14's open is
their first real exercise.
- **the `closed` guard.** Section-2's manage block now tests `abs(net) > 1e-9 and entered and NOT
  closed`. `net` is the SHARED ACCOUNT NET, so without the last clause the tournament opening a
  position re-animated a rider trade that had already closed. Pinned by a test that also asserts the
  source line has not drifted.
- **`venue_first_ok()`** gates ENTRY / TRAIL / MANUAL_CLAIM / OPERATOR_SELL on the cross-desk
  invariant. ⚠ **NOT the 20:40 hard flat** — refusing to flatten because the books disagree turns a
  bookkeeping fault into an overnight position, which is strictly worse. A test pins that exemption.
- **`CLOSED_ELSEWHERE`.** Venue flat at the clock while our book still holds now books, latches and
  ALARMS. It used to fall through silently: **2 of 4 rider trades this week never reached the
  ledger** (backfilled as `CLOCK_FLAT_RECON`).
- **`cancel_own_stops()`** on all five close paths. The 600pt stop used to outlive every exit — one
  sat working for 2h against a flat account. **clientId-filtered: it must NEVER cancel the
  tournament's per-slot stops**, and that is the tested safety property, not an optimisation.
- ⚠ The trail readout used to print `need +150` (the `ARM_PT` fallback) while the rule armed at
  `4 × arm_atr` ≈ **131pt**. It overstated the distance to arming by ~19pt every time it was read.

**★ THE EXIT IS ESSENTIALLY EXIT-PROOF — 25 variants tested, holding to the flat beat every one.**
Stops (7 widths) all negative; give-back rules ~$0; progress/underwater exits worse; reactive
direction-change worse by $3,115+. Do not re-run these. The ONE thing that beat holding is the
armed trail (+$2,320), and a fixed 400pt target lands within $33 of it — so "take profit somehow"
is the robust finding, not the specific mechanism.

⚠ It is 31 in-sample sessions after ~60 configurations. Treat the first weeks as evidence, not proof.
