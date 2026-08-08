# Greenfield Hunt — OPEN-NEWS cluster (census level: top25)

**Verdict: GRAVE. No survivor. survived = false.** Narrowing from the full OPEN/NEWS cluster to
the biggest runs did *change* the mechanism that looked best — the full-cluster hunt buried a
Donchian **breakout**; here the forward tape says breakouts are dead and a **fade** is the only
positive-EV direction. But the fade does not survive commitment: every positive config is a
razor-peak whose profit is a long/short **cooldown artifact** plus a handful of survivorship-defined
on-target trades. The winning *side* flips between candidates. A coin-flip that bleeds at scale.
Buried.

---

## 1. Target set — OPEN/NEWS ∩ top25 (8 sat-out runs)

OPEN/NEWS is the census's **clock bucket**: every ≥1.5×ATR 15-min run starting in 13:00–15:00 UTC
(US pre-open ramp / 13:30 cash open / 14:00 data drop). 19 runs total; **8** are sat-out *and* fall
in the top25 biggest sat-out moves (|move| ≥ 89 pt):

| time UTC | dir | move | pre-5m path | fwd-15m end / max-fav / max-adverse |
|---|---|---|---|---|
| 07-24 13:38 | DN | −194 | +78 then reversed | end −176 · fav +20 · adv −189 |
| 07-23 14:40 | DN | −178 | −107 (already falling) | end −171 · fav +20 · adv −175 |
| 07-23 13:28 | UP | +166 | quiet | end +161 · fav +164 · adv −47 |
| 07-23 14:59 | DN | −118 | quiet | end −92 · fav +20 · adv −109 |
| 07-22 14:55 | UP | +110 | quiet | end +91 · fav +101 · adv −20 |
| 07-20 14:40 | DN | −105 | quiet | end −78 · fav +26 · adv −95 |
| 07-24 13:59 | UP | +99 | quiet | end +74 · fav +94 · adv −41 |
| 07-21 14:00 | DN | −97 | −60 (already falling) | end −23 · fav +37 · adv −90 |

5 DN / 3 UP — a down-skewed week. All 8 sit between 13:28 and 14:59 UTC (open + data drop). Data:
`data/capture.db` MNQ, 7.30M ticks, 07-19 22:00→07-24 21:00 UTC. Tick-honest replay (stop checked
before target within a tick = conservative), $5/round-trip, MNQ $2/pt. Tools in `scratchpad/`:
`lib.py`, `fwd.py`, `engine.py`, `sweep.py`, `stress.py`, `stress2.py`, `final.py`, `ride.py`.

## 2. Forward study flips the mechanism (news window, whole week, 2,400 samples)

Signed forward move by short-horizon displacement `D` (sample every 15s, 13–15 UTC only):

| |D| lookback | D>+30 (up impulse) | D<−30 (down impulse) |
|---|---|---|---|
| fwd 5m | cont 38–42%, mean **−10 to −20** | cont 48–52%, mean +4 to +5 |
| fwd 10m | cont 38–44%, mean **−16 to −18** | cont 55–61%, mean −7 to −13 (up-drift → reverts) |
| fwd 15m | cont 35–44%, mean **−20 to −26** | cont 58–60% |

A sharp impulse in the news window **mean-reverts** — continuation for |D|>30 is only 35–44%. This
**kills the natural news bet** (breakout/continuation, which the full-cluster hunt already buried)
and points at a **fade**. That is the only mechanism worth testing here, and it is a genuinely
different footprint than the full-cluster hunt surfaced.

## 3. Invented signal — "News-Window Impulse Fade" (NWIF)

Active only 13:00–15:00 UTC. On a 5s grid, when flat and past cooldown:
- `D` = price(t) − price(t−`L`s). If `|D| ≥ TH` pts → **FADE**: D>0 → SHORT, D<0 → LONG.
- Entry: first tick after trigger. Hard stop `STOP` pts. Two exits tested:
  **(a) fixed** target `TGT` pts; **(b) ride** — no target, hold the reversion to `CAP`-sec time-cap.
- Single position, `CD`-sec cooldown after exit.

## 4. Backtest — looks alive, then fails every stress test

**Continuation (the natural news bet) is dead** — confirms the full-cluster grave: base
(L60/TH40/s30/t60) **−$788, win 26%**; only **16/81** sweep configs positive.

**Fade** looks alive. 108 fixed-target configs, 43 positive (40%). Leading candidates:

| id | spec | net | n | win% | INDEP long / short | big-moves-caught |
|---|---|---|---|---|---|---|
| A | L30 TH20 s30 t30 | +$845 | 91 | 63 | +$948 / **−$104** | 5/8 |
| B | L60 TH40 s30 t60 | +$901 | 40 | 50 | +$291 / +$202 | **3/8** (on-target +$5) |
| C | L30 TH30 s40 t40 | +$791 | 54 | 63 | +$656 / **−$249** | 5/8 |
| RIDE | L60 TH40 s50 (ride) | **+$1534** | 25 | 64 | **−$156** / +$338 | 4/8 |

## 5. Robustness — the four graves die four ways, and the *side* keeps flipping

1. **Edge only exists as n collapses (the curve-fit tell).** Fade sweep net by trade-count bucket:
   n<50 → median **+$75** (26/43 pos); n∈[50,100) → median **−$289** (15/56); n∈[100,200) →
   median **−$706** (2/9). The moment the trigger fires often, it bleeds. Widening the population
   turns the edge negative — the fade is a negative-EV entry throttled to profit only by rarity.

2. **Parameter razor-edge on the lookback L.** The single most sensitive knob flips the sign 15s away:
   - **C**: L20 +$395 · L30 **+$791** · **L45 −$498** · L60 −$428 · L90 +$136.
   - **B**: L20 −$45 · L30 −$200 · **L45 −$487** · **L60 +$901** · L90 +$46 (a lonely peak).
   On a tape swinging 100–200 pt, a 15-second change in the momentum window should not swing $1,300.

3. **Long/short symmetry — the smoking gun (same as the full-cluster grave).** Isolating each side on
   its *own* trade set (removing the single-slot cooldown that skips one side's losers):
   - **C**: long **+$656** / short **−$249** — shorts bleed.
   - **RIDE**: long **−$156** / short **+$338** — **longs bleed**.
   The profitable side **flips** between candidates. There is no directional edge; the combined
   positives are a cooldown scheduling accident, not a signal. (A also: short-only −$104.)

4. **Strip-3-best + survivorship.** RIDE +$1534 → **+$642** after 3 trades (top-3 = $892 = **58%**);
   and its on-target 5 trades carry **+$1127 of the $1534 (73%)** — those 5 are the very runs the
   census *defined* as OPEN/NEWS, so profiting on them is circular. B makes its money the opposite
   way: **on-target +$5, off-target +$896** — it does not catch the runs it was built for (3/8).

5. **Per-day / big-day failure.** C loses **−$240 on 07-23**, the single biggest-run day of the week
   (a down-trend that runs *over* the fader's longs). The fade's population reversion (§2) has a fat
   left tail on trend legs that stops book as full losses while reversion winners are TGT-capped.

6. **Big-moves-caught.** Best fade (RIDE) aligns-and-profits on **4/8**; the symmetric config (B)
   **3/8**; C 5/8 but only by bleeding its shorts; continuation/breakout **2/8**. No config both
   catches the target runs and survives side-isolation.

## 6. Cause of death

> **The top25 narrowing rotated the best-looking mechanism (breakout → fade) but not the outcome.**
> The forward tape confirms a real population tendency — sharp news-window impulses mean-revert
> (|D|>30 continues only 35–44%) — yet that tendency does not survive being turned into a mechanical
> entry. Every positive fade config is a razor-peak on the lookback L (a 15s nudge flips +$901 to
> −$487), and once the long/short cooldown coupling is removed, **no side is independently +EV in a
> stable way** — the winning side flips from longs (C) to shorts (RIDE) between candidates. The
> apparent profit is 58% in three trades and 73% in five survivorship-defined on-target trades. As
> the trigger is allowed to fire at scale the net falls to −$289 / −$706 median. **A coin-flip that
> bleeds.** OPEN/NEWS remains a clock bucket, not a footprint: a two-sided open-drive whipsaw with no
> real-time directional tell separating the leg that runs from the leg that reverts. BURIED.

De-biased realizable edge (independent long-only −$156 + short-only +$338, cooldown-artifact
removed) ≈ **+$182 over 41 trades — flat, a coin-flip** — and negative once the trigger fires at
population scale.

## 7. Graves

- **NWIF-fade-ride** — impulse fade, ride reversion to time-cap. Best L60/TH40/s50 **+$1534/64%/n25**,
  but **long-only −$156** (only shorts +$338 survive isolation); strip-3 removes **58%**; **73%** of
  net from 5 survivorship on-target trades; catches 4/8. Death: profit is a cooldown artifact + fat
  tail on census-defined runs, not a base rate.
- **NWIF-fade (fixed target)** — best B L60/TH40/s30/t60 **+$901/50%/n40**, symmetric but a lonely
  **L-razor peak** (L45 −$487), and **on-target +$5 / off-target +$896** → doesn't catch the runs
  (3/8). Candidate C +$791 but **short-only −$249** and **−$240 on the 07-23 trend day**. Sweep edge
  lives only at n<50 (median −$289 at n50-100, −$706 at n100-200). Death: negative-EV entry throttled
  to profit only by rarity; winning side flips config-to-config.
- **NWIF-continuation (breakout)** — the natural news bet. Base **−$788/26%/n39**; only **16/81**
  configs positive; catches 2/8. Death: news-window impulses mean-revert (§2), so continuation is
  structurally −EV — the same result the full-cluster Donchian hunt reached.
