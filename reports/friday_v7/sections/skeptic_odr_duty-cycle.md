# SKEPTIC — THE OPEN RIDER (ODR) · lens: DUTY-CYCLE / PLACEBO

**VERDICT: REFUTED as a standalone edge. It is a levered long position on `|13:00–15:00 window drift|`
with no measurable component left over once that exposure is priced, and on the only 17 days it was
never fitted to it sits *inside* its own placebo distribution.**

Everything below was re-derived from raw 5s bars via `gazbot7.lake.connect()`. I did not reuse the
author's harness. Working script: `/tmp/.../scratchpad/odr.py`, `ctrl.py`, `ctrl2.py`, `ctrl3.py`.
Costs: **$1.50/RT** (house rule 1), $2/point, MNQ 1 lot, `symbol='MNQ'`, `timeframe='5s'`,
integer division via `//` throughout (house rule 4).

---

## 0. Reproduction — the spec is real and I hit it exactly

Spec as given: 13:00–15:00 UTC, cadence 300s if flat, `dir = sign(close(t) − close(t−900))`,
stop `2.0 × ATR1m` (floor 4pt, ATR1m = mean 1-min high−low over trailing 15 completed minutes),
target 2R, 45-min cap, stop wins ties, entry at the 5s bar close.

| | n | net | win% | $/trade |
|---|---|---|---|---|
| author, 17 days, **$5/RT** (their number) | 129 | +$4,169 | 48.1% | +$32.32 |
| **mine, same 17 days, $5/RT** | **129** | +$4,577 | 48.8% | +$35.48 |
| **mine, same 17 days, $1.50/RT (correct)** | **129** | **+$5,028** | 48.8% | +$38.98 |

The trade count reproduces to the trade. The residual $408 at matched fees is ATR-window detail.
Two bookkeeping corrections before the attack begins:

- **The claim as handed to me says "102 trades". The author's own section says 129 and I get 129.**
  Whoever compressed the claim dropped 27 trades.
- **The fee correction HELPS it**, not hurts: 129 × $3.50 = +$451. Honest net is **+$5,028**, and
  crossing the quoted spread on entry (author's measured 0.615 pt) takes it to **+$4,870**.

**I also found 17 more trading days of tape the author never used.** `lake.connect()` unions the V5
archive, and V5 carries full 13:00–15:00 5s bars for **2026-06-19 → 2026-07-15** — 17 sessions,
same instrument (window-open price 29,160–30,827 vs 27,813–29,920 after; mean ATR1m **31.9 pt vs
29.2 pt**, i.e. *more* volatile, not a degenerate stretch). That is a free, genuinely out-of-sample
leg and it is where this candidate dies.

---

## 1. The controls the lens demanded

All on identical cadence / window / stop / target / cap, sequential with the same re-entry lock.

| Direction rule | 34 days | | 17 days (author's) | |
|---|---|---|---|---|
| | n | net | n | net |
| **ODR — ride sign(mom15)** | 243 | **+$6,810** | 129 | **+$5,028** |
| REVERSED (fade) | 253 | −$3,798 | 138 | −$4,076 |
| ALWAYS LONG | 260 | −$4,401 | 135 | −$1,509 |
| ALWAYS SHORT | 248 | +$3,233 | 137 | +$1,186 |
| C1 `sign(price − price@13:00)` | 241 | +$204 | 125 | +$1,462 |
| **C2 one decision/day: sign of the window's first 15 min, held all window** | 237 | **+$6,005** | 126 | +$3,226 |
| C4 `sign(previous day's window drift)`, fixed per day | 257 | −$3,699 | 136 | −$720 |
| C3 **HINDSIGHT** — sign of that day's realised window drift | 234 | +$10,778 | 125 | +$6,988 |

### (a) placebo A — random direction, identical timing, 2,000 draws

| sample | placebo mean | sd | ODR | z | percentile | one-sided p |
|---|---|---|---|---|---|---|
| 34 days | +$683 | $2,610 | +$6,810 | +2.35 | 99.2 | 0.0080 |
| 17 days (fitted) | +$694 | $1,794 | +$5,028 | +2.42 | 99.4 | 0.0065 |
| **17 V5 days (never seen)** | **−$71** | **$1,871** | **+$1,782** | **+0.99** | **83.2** | **0.168** |

### (b) placebo B — DAY-LEVEL sign flip, 2,000 draws

Per-trade randomisation is the *wrong* unit for an always-in strategy: it destroys the within-day
direction clustering that is the entire mechanism and so understates the null's variance. Flipping
the sign of a whole day's direction stream keeps the clustering intact.

| sample | null mean | sd | ODR | z | percentile | p |
|---|---|---|---|---|---|---|
| 34 days | +$1,573 | $2,316 | +$6,810 | +2.26 | 98.8 | 0.0125 |
| 17 days (fitted) | +$497 | $1,776 | +$5,028 | +2.55 | 99.9 | 0.0015 |

So: **on the tape it was designed on, ODR is outside both placebos.** That much is true and I am not
going to pretend otherwise. The kill comes from the next two tests.

---

## 2. KILL SHOT 1 — the drift decomposition. The intercept is zero.

Regress each day's ODR P&L on that day's **absolute** 13:00–15:00 net travel:

```
daily_pnl  =  a  +  b · |window drift in points|
```

| sample | a (zero-drift day) | t(a) | b | t(b) | R² |
|---|---|---|---|---|---|
| **ALL 34 days** | **−$23** | **−0.22** | **$1.237/pt** | **+2.75** | 0.19 |
| 17 fitted days | +$74 | +0.45 | $1.091/pt | +1.58 | 0.14 |
| 17 V5 days (OOS) | −$86 | −0.60 | $1.207/pt | +1.91 | 0.20 |

**The only coefficient that is statistically distinguishable from zero anywhere in this table is the
loading on |drift|.** On a day where the open window ends where it started, ODR's expected P&L is
**−$23 ± $105 — i.e. nothing.** Mean |drift| is 180.5 pt; fitted daily P&L at that mean is $200,
against an actual mean of $200. The regression reproduces the strategy's entire headline from one
number it does not forecast and cannot control.

This is exactly the null the lens specified: *the open moves a lot and an always-in strategy books
the travel.* ODR is a 1.24 $/pt long position in realised open-window directionality. That is a real
exposure — it is not an edge, and it carries no signal that tells you when the exposure stops paying.

Corroboration, on the sample's own drift: cumulative 13:00–15:00 travel over the 34 days is
**−1,389.5 pt**. One lot held short across every window would book $2,728 net of fees with no
strategy at all.

## 3. KILL SHOT 2 — the machinery is decorative

**C2** makes exactly **one** directional decision per day — the sign of the window's *first fifteen
minutes* — and holds that side for the whole two hours. No 5-minute cadence, no rolling 15-minute
lookback, no re-picking. It earns **+$6,005 of ODR's +$6,810 over the 34 days: 88%.**

The entire 5-min re-decision apparatus that the claim is built around is therefore worth
**$805 / 243 trades = $3.31 a trade** — *less than* the $1.23/trade spread-crossing cost the author
himself measured, and far less than any realistic stop slippage (129 of 243 exits are stops).

**C3**, which is allowed to know the day's answer in advance, earns $10,778. ODR captures 63% of a
pure hindsight day-direction bet. That is the correct way to read this strategy: a partially
efficient estimator of *"which way is today going"*, not a timing signal. The author's own §7
day-demeaning found the same thing from the other side (demeaned forward return −0.70 / −14.4 /
−18.9 / −29.0 pt at 15/30/45/60 min); I reach it independently via C2 and via the zero intercept.

**C4** (yesterday's direction) is −$3,699, so this is *not* a static short bias dressed up. The
mechanism is genuine within-day momentum persistence. The question is whether that persistence is
stable, which is §4.

## 4. KILL SHOT 3 — out of sample it is inside the null

The 17 V5 sessions (2026-06-19 → 07-15) are the only data ODR was never fitted to, they have
*higher* ATR than the design period, and they are the same size sample.

| | n | net | win% | $/trade | daily mean | daily t | placebo pctile |
|---|---|---|---|---|---|---|---|
| fitted 17d (07-16 → 08-07) | 129 | +$5,028 | 48.8% | +$38.98 | $296 | **3.31** | **99.4** |
| **OOS 17d (06-19 → 07-15)** | **114** | **+$1,782** | **41.2%** | **+$15.63** | **$105** | **0.94** | **83.2** |
| pooled 34d | 243 | +$6,810 | 45.3% | +$28.03 | $200 | 2.78 | 99.2 |

**Out of sample: $15.63/trade, win rate 41.2%, daily t = 0.94, and it lands at the 83rd percentile of
its own random-direction placebo — p = 0.168. Inside the null.** The lens's stated kill condition
("if ODR is not clearly outside the placebo distribution, it is REFUTED") is met on the only sample
that was not used to build it.

Per-trade expectancy falls by 60% out of sample. The slope on |drift| is stable across both halves
(1.207 vs 1.091) — the *exposure* is real and persistent; only the *alpha on top of it* changes, and
it changes from "$74/day, t=0.45" to "−$86/day, t=−0.60". Both are zero.

## 5. Concentration, for completeness

Stripping best **days** (the correct unit, not trades — trades within a day are one bet):

| | full | −1 day | −3 days | −5 days | −8 days |
|---|---|---|---|---|---|
| 34d | $6,810 | $5,854 | $4,181 | $2,851 | $1,197 |
| 17d | $5,028 | $4,134 | $2,804 | $1,713 | — |

Eight sessions of thirty-four carry 82% of the money — which is precisely what a long-|drift|
position looks like. Day-bootstrap on the pooled 34 days gives mean daily P&L $200, 95% CI
[$57, $338] — positive, but that pools the 17 days the parameters were chosen on.

Long/short over 34 days: LONG n=108 +$1,714, SHORT n=135 +$5,096, on a window that fell 1,389 pt.
Forcing equal longs and shorts within each day leaves +$3,869 on 178 trades — the residual the
author called the "right-skew of the payoff shape". Note the per-trade random placebo also runs
**positive** (+$683/243 = +$2.70 a trade at $1.50 fees): a slice of that residual is the 2R-with-a-
wide-stop geometry itself, available to a coin flip, not to this signal.

---

## 6. What survives, and what to do with it

Not everything here is worthless, and I will not overclaim the kill:

1. **The clock observation is sound.** 13:00–15:00 UTC is genuinely where MNQ travels: mean |window
   drift| 180.5 pt across 34 sessions, and the b = $1.237/pt loading is the most significant number
   in this study (t = +2.75, and it holds at 1.207 / 1.091 in both independent halves).
2. **Wide stops beat the desk's ~1 ATR standard for this window** — that reproduces and is
   independent of the direction question.
3. **What does not survive is the claim that ODR has an edge.** Its intercept is zero, 88% of it is
   reproduced by one decision a day, and out of sample it is a coin flip at p = 0.168.

**Correct framing if anyone wants to keep it:** it is not a seventh gate and not a signal. It is a
two-hour, 1.24 $/pt long position in open-window realised directionality, whose P&L is a linear
function of a quantity nothing in the spec forecasts. It should be judged as an exposure — sized
against how trendy the open is — never as an alpha, and never sized off the +$4,169 headline.

---

## LEAD STATUS

- **ODR as a tradeable edge — REFUTED.** Killing test: the out-of-sample V5 17-day leg lands at the
  **83.2nd percentile of 2,000 identical-timing random-direction placebo draws (p = 0.168)**, and
  the pooled 34-day regression of daily P&L on |window drift| has intercept **−$23, t = −0.22** —
  zero P&L on a zero-drift day. Supporting: **C2**, one direction decision per day, captures **88%**
  of the net ($6,005 of $6,810), so the 5-minute cadence and the 15-minute lookback are worth
  $3.31/trade against $1.23/trade of spread alone.
- **"13:00–15:00 is where MNQ travels" — PARKED**, as a *sizing/regime* input rather than an entry
  signal. Revival condition: an independent forecaster of next-window |drift| (not direction) that
  is positive out of sample; the b = $1.237/pt payoff is then worth harvesting deliberately.
- **Wide stops (≥2 × ATR1m) in the open window — SHADOW.** It reproduces on 34 days and is
  orthogonal to the direction question, but it has only ever been measured inside ODR. Revival
  condition: re-measure the stop-width plateau on a signal whose intercept is not zero.
