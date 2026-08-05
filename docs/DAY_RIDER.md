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
