# REHAB — `grind_long` (tick-honest, regime-segmented)

**Date:** 2026-08-01 · **Analyst:** router/rehab pass · **Symbol:** MNQ · **Cost model:** $2/pt, $1.50/RT per lot
**Tape:** this-week `data/capture.db` (MNQ ticks 2026-07-23 22:00Z → 2026-07-31 21:00Z, ~7 sessions) + V5 archive
(`alphabot2/data/ticks.db` + `alphabot.db` 1m bars, 2026-07-05 → 07-17, ~12 sessions = a **second, different regime**).
**Method:** entry decided on the 1-min signal exactly as live; **exit repriced on the real trade ticks**, first-touch, 60-min
max-hold cap; one-position-at-a-time per gate. Tool: `scripts/rehab_grind_long.py` (reproducible).

**The gate as it runs LIVE (reproduced faithfully):**
- Entry: `gate_grind(slope_min=0.4, fast_slope=True)` LONG → `vwap_slope_fast≥0.4` AND `0.3 ≤ ext_atr ≤ 4.0`.
- Floors: **ER(30-bar 1m) ≥ 0.35** (`ER_FLOOR`, added 07-30) AND **ATR ≥ 24pt** (`ATR_FLOOR`, 07-25).
- Exit (scaleout slate): Lot A scalp **2.5R** (1-ATR stop) + Lot B **"wide" lock-chandelier** (start_k 3.5, lock_r 6.0, lock_k 0.5, 1-ATR native stop).

---

## TL;DR — VERDICT: **FIXED** (entry-selectivity), regime-dependent in *magnitude*

The bleed is the **SIGNAL (entry), not the exit**. The exit already works. Two live floors are actively
**destroying** the gate:

| Config (tick-honest, capture.db window, always-armed) | n | net | win% | strip-top3 |
|---|--:|--:|--:|--:|
| **LIVE** (ER≥.35 & ATR≥24, A2.5/Bwide) | 11 | **−$284** | 18% | −$1,161 |
| raw signal, no floors | 193 | +$1,552 | 30% | −$263 |
| **RECOMMENDED** (drop ER floor; ATR 24→12; **ext_atr ≤ 2.0**; keep A2.5/Bwide) | 111 | **+$2,830** | 34% | +$1,172 |

The **ER≥0.35 floor is backwards** for a fast-slope momentum gate, and **ATR≥24 is far too tight** for this
regime. Replacing both with a single **ext_atr ≤ 2.0 ceiling** (don't buy when already stretched = don't buy
resistance/session-highs — the operator's exact symptom) flips the gate from −$284 to +$2,830 on the same tape,
**keeps 24–28 of the 30 big tail-winners**, survives strip-the-best, leave-one-day-out, and — critically — **holds
in the second regime** (V5 archive: raw −$3,008 / live −$1,135 → **+$172** with the fix). Exit `B=wide` and
`A=2.5R` are both **proven**, not just guessed.

---

## 1. NORMALIZE — malfunctions in the live record

Live `grind_long*` (all sub-slots, `gazbot7.db`): base −$615 (40tr) + _A +$31 (33tr) + _B +$302 (19tr) = **−$282 / 92tr raw.**
Exit-reason split (why the raw number lies about the gate):

| reason | n | $ | note |
|---|--:|--:|---|
| STOP | 53 | −2,718 | the entries get stopped — the bleed lives here |
| STOP_UNFILLED | 8 | −220 | ContFuture stop-trigger bug ([[stop-unfilled-contfuture-root-cause]]) |
| MAX_HOLD | 1 | −216 | **naked ride** — stop never fired, rode 107pt against |
| GIVEBACK | 5 | +170 | |
| CHANDELIER | 11 | +961 | Lot-B tail |
| MANUAL_CLAIM | 5 | +606 | Lot-B tail |
| TARGET | 9 | +1,137 | Lot-A / A-target |

**Every dollar of profit is in the exit tail; every dollar of loss is in stopped entries.** That is the whole story.

**Malfunctions requiring normalization:**
- **Trade 171 (MAX_HOLD, −$216):** qty 1, entry 29323.75 → 29216.5 = **−107pt naked ride**, the 1-ATR stop never
  fired (rode to the 20-min max-hold clock). If the stop had worked (ATR≈24–28 → ~−50pt) → **≈ −$55**. **Recover +$161.**
- **Trade 433 (STOP, −$235.5):** **qty = 5.0** on `grind_long_A` (which is `base_size=1`) — a **position-size
  malfunction** (5 lots opened, odd 27857.**85** fill). Price move was only −23.4pt; the loss was inflated 5×.
  Normalized to 1 lot → **≈ −$47**. **Recover +$188.** (Class: [[futures-trade-multiplier-recording]] / sizing leak.)
- **STOP_UNFILLED ×8 (−$220.5):** all exited **inside 1 ATR** (−7.5 to −15.8pt) — the fallback cut *tighter* than a
  1-ATR stop would have, so these **did not inflate** the loss. No $ correction; flagged as a **reliability** defect
  (the fix is built, not deployed — [[stop-unfilled-contfuture-root-cause]]).

**Corrected-cost live P&L: −$282 + $161 + $188 = ≈ +$67 (≈ breakeven), not −$282.** The raw live number is
inflated ~$350 by two mechanical incidents. But breakeven is still a fail for a gate the router thrashed 8+ times —
the real fix is the entry.

## 2. RECONSTRUCT — corrected-cost true P&L (tick-honest)

On the always-armed tick-honest reconstruction (no router benching, so we judge the *signal*, not the routing):
raw grind LONG fires **1,232** one-min signals → **193 realized** trades → **+$1,552** (30% win). But that is a
**blanket cross-tape number and therefore a bug** per the operator's discipline — it averages trend sessions the gate
should be ON with chop sessions it should be OFF. Segmented below.

## 3. ROOT-CAUSE — base config / exit / signal?

**It is the SIGNAL.** Proof:

**(a) The exit is fine.** Lot-B `wide` lock-chandelier = **+$1,878** of the +$1,552 (the tail *is* the edge); Lot A is
near-flat. Swapping B to `tight` → **−$331**; to fixed 2.5R → +$981. The wide tail-rider is doing its job. (§5 proves it.)

**(b) The signal fires late/extended and buys resistance.** Sliced on the raw realized population:

```
by range-break at entry:   BROKE-high  31tr net −$366  23%W      <-- breakouts FAIL
                           into-resist 162tr net +$1,918 31%W    <-- money is riding the establishing trend
by ext_atr (stretch):      ext≤1.0  net +1103 | ≤1.5 +2162 | ≤2.0 +2419 | ≤2.5 +2900 | ≤3.0 +1812 | ≤4.0 +1552
```
The gate makes money when price is **moderately** extended and **loses** when it's already stretched (`ext>2.5`) —
i.e. buying the exhausted top. That is the operator's "buys resistance/session-highs and churns chop" — confirmed.

**(c) The ER≥0.35 floor is BACKWARDS.** Sliced by 30-min ER-at-entry, the money is in **LOW** ER:

```
by ER-regime:  dead-chop ER<.15  117tr +$3,736 37%W   <-- the big tail-runs enter HERE
               norm-chop .15-.30  64tr −$2,045 19%W   <-- the churn/bleed is HERE
               building  .30-.45   9tr   +$194 33%W
               trend     ER≥.45    3tr   −$333  0%W    <-- late = dead
```
Not a paradox: `gate_grind` fires on the **12-bar fast slope**, so it catches a trend at **inception**, when the
**30-min** ER lookback still reads the *prior* chop → ER prints LOW. By the time ER(30) climbs past 0.35 the move is
extended and reversing. **26 of the 30 big tail-winners enter at ER < 0.30** (e.g. +$468 @ ER 0.05, +$348 @ ER 0.02).
The 07-30 rotation-day floor of 0.35 (banked N=1, "needs a multi-regime backtest before trusting" — its own note)
is now **disproven across the fuller week and the archive**.

## 4. FILTERS — keep the winners, cut the bleed (★ every attempt shown, incl. the graves)

Rule enforced: a filter that "wins" by dropping the 30 target Lot-B tail-winners is a **FAKE win → REJECTED**.
Scored on the raw realized population (post-hoc slice for the winner-count; finalists re-priced pre-filter in §5).

| filter | n | net | winners kept | verdict |
|---|--:|--:|:--:|---|
| none (raw) | 193 | +1,552 | 30/30 | baseline |
| **ext_atr ≤ 2.5** | 152 | **+2,900** | **28/30** | ★ best keep-winners |
| **ext_atr ≤ 2.0** | 131 | +2,419 | 24/30 | ★ (best once re-priced, §5) |
| ext_atr ≤ 1.5 | 107 | +2,162 | 19/30 | too tight, sheds winners |
| net30 ≥ 0 (don't fade a drop) | 166 | +1,168 | 26/30 | marginal help, not the lever |
| ATR ≥ 12 | 155 | +1,183 | 26/30 | light floor OK, small |
| ATR ≥ 20 | 49 | +2,697 | 13/30 | ⚠ high net but sheds 17 winners — concentration, not a fix |
| **LIVE: ER≥.35 & ATR≥24** | 11 | −41 | **1/30** | ❌ GRAVE — drops 29/30 winners, barely trades |
| ER ≥ 0.20 | 48 | −1,593 | 3/30 | ❌ GRAVE — backwards (drops the low-ER tail-runs) |
| ER ≥ 0.15 … 0.45 | — | all ≤ −41 | ≤6/30 | ❌ GRAVE at every threshold |
| range-BREAK only (px>prior-30hi) | 31 | −366 | 2/30 | ❌ GRAVE — breakouts fail; edge is the *ride*, not the poke |
| slope_fast ≥ 0.7 (strong) | 68 | −1,540 | 6/30 | ❌ GRAVE — strong-slope = late entry |
| US session only (≥13:30Z) | 75 | +1,638 | 12/30 | ⚠ real but drops overnight winners; not needed if ext-capped |
| ext≤2.0 & ATR≥12 | 99 | +2,207 | 20/30 | good combo |

**Graves (honest failures):** every ER floor; the range-break filter; the strong-slope filter; the ATR≥20/24
concentrators (they raise net by discarding genuine tail-winners — the operator's definition of a fake win, so
rejected as the *primary* lever). **Survivor: a single `ext_atr` ceiling ≈ 2.0**, optionally with a light `ATR≥12`.

## 5. ROBUSTNESS — strip-the-best · LODO · per-day · cross-regime

Finalists re-priced **pre-filter** (the filter blocks the entry and *frees the slot* for a later signal — the true
live count), A=2.5R / B=wide:

| config | n | net | win% | strip-top3 |
|---|--:|--:|--:|--:|
| LIVE ER≥.35 ATR≥24 | 11 | −$284 | 18% | −$1,161 |
| ext≤2.0 only | 143 | +$2,681 | 33% | **+$1,023** |
| ext≤2.5 only | 170 | +$2,287 | 31% | +$472 |
| **ext≤2.0 & ATR≥12 (RECOMMENDED)** | 111 | **+$2,830** | 34% | **+$1,172** |

**ext≤2.0 beats ext≤2.5 once re-priced** (blocking the 2.0–2.5 stretch frees the slot for a cleaner later entry)
and is more strip-robust. Adding the light `ATR≥12` nudges +$150 and cleans the tiniest-ATR noise.

**Strip-the-best (RECOMMENDED):** top1 +$2,161 · top3 +$1,172 · top5 +$393 · top10 −$1,343. Honest read: this is a
**positive-skew tail gate** — ~the top 10 trades carry it, and past that it's flat-to-red. That is *inherent* to a
trend-tail harvester (and why the wide B-lot matters). It survives moderate stripping (top5 still +$393); it is **not**
a high-hit-rate grinder and should not be sold as one.

**Leave-one-day-out (RECOMMENDED):** dropping any single session leaves +$1,528 … +$3,046 — **no single day carries
it.** Per-day: 07-24 +$367, 07-27 −$67, 07-28 +$1,302, 07-29 +$158, 07-30 −$216, 07-31 +$1,285. Green on trend
sessions, only *mildly* red on the chop sessions (07-27/07-30) — vs the raw gate which bled −$376/−$511 those days.
**The ext ceiling contains the chop bleed** instead of the router having to catch every chop tick.

**Cross-regime (V5 archive 07-05→17, the low-vol summer regime, a genuinely different tape):**

| config | n | net | win% |
|---|--:|--:|--:|
| raw, no floors | 355 | **−$3,008** | 25% |
| LIVE ER≥.35 ATR≥24 | 12 | −$1,135 | 8% |
| **ext≤2.0 & ATR≥12** | 186 | **+$172** | 30% |

- **ext ceiling plateau holds in the 2nd regime:** archive ext≤1.5 +$268 · **≤2.0 +$172** · ≤2.5 −$838 · ≤3.0 −$818
  · ≤4.0 −$1,128. The **≤1.5–2.0 plateau is the same as this week's** → a real parameter, not a curve-fit.
- **B=wide proven in the 2nd regime too:** archive B=wide +$172 vs tight −$818 vs 2.5R −$316 vs 4.0R −$36.
- The fix turns a **−$3,008 disaster into ≈ breakeven (+$172)** in the summer chop, and **+$2,830** in the trend
  week. Magnitude is regime-dependent (trend-harvester); **the ext ceiling is what removes the catastrophic tail**,
  in both regimes. This is the multi-regime evidence the 07-30 ER-floor note explicitly asked for — and it points
  the opposite way to that floor.

## 6. R-TARGET / EXIT sweep — proven Rs vs the guesses (operator discipline §3)

Guess (regime→exit cheat-sheet, "trend" gate): **A 2.5R + B wide**. Swept on the ext≤2.0 entry:

- **A-lot scalp R** (B=wide fixed): 1.0R +1,824 · 1.5R +2,268 · 2.0R +2,366 · **2.5R +2,681** · 3.0R +2,837 · 4.0R +3,251.
  Net **rises monotonically** with A-R on this trend-heavy tape — but that is exactly the trap the operator warned
  about: a wider A abandons the scale-out's **floor role** (A exists to de-risk, not to chase the tail — B already
  does that). A wide A would be punished on a chop week. **Keep A = 2.5R** (guess holds as a defensible floor);
  explicitly do **not** chase the +$3,251 at 4R — it's directional-exposure creep, unproven out-of-regime.
- **B-lot mode** (A=2.5R): **wide +$1,878** ≫ 6.0R +1,758 · 4.0R +1,448 · 2.5R +981 · 2.0R +790 · **tight −$331**.
  The **wide lock-chandelier B is PROVEN** (and again in the archive) — capping B at any fixed R leaves the tail on
  the table; the tight snap-back B is a grave for this gate. **Guess confirmed.**

**Proven exit = A 2.5R + B wide-lock-chandelier — the current config is correct. The fix is 100% at the entry.**

---

## RECOMMENDED CONFIG (exact)

`deciders.py`:
- **`ER_FLOOR`: remove `"grind_long": 0.35`.** (Disproven: backwards for a fast-slope gate; drops 29/30 winners in
  both regimes.)
- **`ATR_FLOOR["grind_long"]`: 24 → 12.** (24 was a trend-week finding; too tight here — drops 22/30 winners.)

`slot_strategy.py` grind_long entry params:
- add **`"ext_hi": 2.0`** to the grind_long `params` (currently defaults to 4.0). **This is the rehab.** It is the one
  filter that keeps the winners, cuts the bleed, survives strip/LODO, and holds cross-regime.

Exit: **unchanged** — Lot A 2.5R + Lot B wide lock-chandelier (proven).

**Expected effect:** capture.db window −$284 → **+$2,830**; V5 archive −$1,135 → **+$172**; contains the chop-day
bleed to ≈−$100–200 instead of −$500 (so the router thrashes far less — bench in *confirmed* chop, not every tick).

## Caveats (honest)
- Tick coverage = ~7 sessions (capture.db) + ~12 (archive); two July regimes, both summer-ish. A high-vol/violent-
  whipsaw week (US-open ATR-60 chop) is under-represented — the ext ceiling should help there (it bans the extended
  chase) but re-validate when such a week is captured.
- Positive-skew tail gate: top-~10 trades carry the window; genuine but n-sensitive. Treat the *policy* (ext-capped
  entry + wide B tail) as the edge, not any single number.
- Backtest is **always-armed** (no router benching) to isolate the signal; live P&L will differ by whatever the
  router does. With the ext fix the gate self-contains chop, so the router's job shrinks to benching *confirmed* trend-
  breaks/chop, not damage-control every 5 min.
- A-lot 5-lot sizing incident (trade 433) and the MAX_HOLD naked ride (trade 171) are **execution** defects, not gate
  defects — worth a separate look (sizing guard + the built-but-undeployed ContFuture stop fix).
