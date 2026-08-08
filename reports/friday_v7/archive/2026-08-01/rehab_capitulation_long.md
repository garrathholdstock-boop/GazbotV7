# GATE REHAB — `capitulation_long` (flush-and-flip micro-fader / LONG)

**Discipline:** full 6-step rehab, tick-honest ($2/pt, $1.50/RT-contract), regime-SEGMENTED
(never a blanket cross-tape number — operator's 2026-07-31 backtest rule). **Every attempt shown,
including the NULLs and graves.** Every R/threshold is swept and reported as PROVEN-vs-GUESS.

**Data used**
- Live actuals: `data/gazbot7.db` `trades WHERE gate LIKE 'capitulation%'` — 24 fills, 07-21 → 07-31
  (14 this-week ≥07-27; the dual-slot `_A`/`_B` pairs are the SAME signal split into 2 lots).
- Tick-honest reconstruction: `data/capture.db` MNQ **aggressor ticks** (10.08 M) + 5s bars →
  1-min features. **Tick coverage 07-23 22:00 → 07-31 21:00 UTC** (≈6 trading days, one summer
  chop regime). Earlier live trades read from the ledger, not tick-repriceable.
- Engine: the REAL `gate_capitulation` + `capitulation_tape` (short_s 20 / base_s 180) + real
  `exit_scalp/exit_chandelier/exit_fixed` from `src/gazbot7`. Entry decided EXACTLY as live
  (completed 1-min bars, `MinuteBars(60)`, footprint recomputed every 5s), exit repriced on the
  real ticks, single-position first-to-fire. Script: `scripts/rehab_capitulation_long.py`
  (+ `_pass2.py`).

**Current LIVE config** (`slot_strategy` `capitulation_long`, post-07-25 rehab):
`climax_min 2.5 · dom_min 0.6 · require_flip=True`, `base_size 1` (was 2, halved 07-28),
`exit scalp 2.0R / 1-ATR stop`, `giveback off`, `ATR floor 10 · ER ceiling dropped`,
`adaptive_exit ON`, router-managed (`DOWN_OFF = {capitulation_long}` — benched in a down-trend so
it never fades a knife).

---

## Headline verdict (read first)

> **REGIME-DEPENDENT + a real, robust CONFIG FIX — the live bleed is NOT the signal, it is two
> tuning mistakes + a structural amplifier.** Tick-honest, single-lot, the CURRENT config
> (`require_flip=True`, 2.0R) is already ~breakeven (+$24, n11) — NOT the −$139 the live book shows.
> The −$139 came from (a) **`require_flip=True` starving the gate to a trickle**, (b) the **2.0R
> target being wrong for a fast bounce-fader**, (c) **dual-slot `_A`/`_B` doubling every chop stop**
> (07-30/31), (d) **US-session / low-vol-grind fires** the router should bench, and (e) live
> stop-slippage on the 07-23 `STOP_UNFILLED` malfunctions.
>
> The fix that survives strip-best-3 and every leave-one-day-out on the tick week:
> **`require_flip=False` + tighten the scalp to 1.0R** → **+$434, n32, 78% win** (strip-best-3 still
> **+$327**; worst LODO **+$220**). Overlay the regime discipline the operator asked for — **fade
> OVERNIGHT only** (ON +$422/n27 vs US +$12/n5) and keep the router's down-trend bench — and it is
> **+$422 at 81% win**. This is the **least data-starved, most robust config in the whole study**,
> and it *reverses a specific prior* (the 07-25 "require_flip IS the edge") that tick-honest data
> contradicts.
>
> **VERDICT: FIXED (config below), REGIME-DEPENDENT (chop-only; must stay benched in trend/US).**
> The one hard caveat: the tick tape is **one chop week** — there is **no trend week in it** to
> exercise the (predicted) trend-day bleed, so ship the config + keep the router benches + confirm
> the trend-side in shadow. Do NOT stack the looser-climax variant (it buys n but adds a −$222 bad
> day — rejected below).

---

## Step 1 — NORMALIZE the malfunctions

Live book has **2 malfunction exits**, both `STOP_UNFILLED` (the known ContFuture resting-stop bug,
[[stop-unfilled-contfuture-root-cause]]), both on **07-23** — i.e. **BEFORE the tick tape and BEFORE
the operator's "this-week"**. Repricing each to where its intended **1-ATR** stop would have fired
(ATR from 5s bars at the entry minute):

| id | when (UTC) | recorded | intended 1-ATR stop | malfn cost | note |
|----|-----------|---------:|--------------------:|-----------:|------|
| 202 | 07-23 10:06 | −$116.5 | **−$46.9** (atr 11.0, exit 28.75pt deep vs 11pt stop) | −$69.6 | stop never fired; ran 17pt past the stop |
| 206 | 07-23 12:16 | −$107.0 | **−$71.1** (atr 17.0, exit 26.4pt deep vs 17pt stop) | −$35.9 | ditto, smaller overshoot |

**Normalization result:** the two malfunctions are **−$223.5 recorded → −$118.0 fixed** (a −$105.5
malfunction tax). Applied to the all-time book: **−$122.0 → −$16.5**.

**BUT — the operator's complaint is the THIS-WEEK −$139, and this-week has ZERO malfunctions**
(10 clean `STOP` + 2 `TARGET` + 2 `CHANDELIER`). No naked rides, no system-stops this week.
**So the this-week bleed is REAL, not a malfunction artifact.** The malfunctions matter only for the
older archive tail. Step 1 clears the archive; it does not explain the headline.

## Step 2 — Corrected-cost RECONSTRUCT

Live P&L by exit reason (corrected-cost, $2/pt, $1.50/RT-contract):

| reason | n | net | note |
|--------|--:|----:|------|
| TARGET | 5 | **+$412.5** | the winners are real |
| CHANDELIER | 2 | +$130.5 | 07-28 + 07-30 rides |
| GIVEBACK | 4 | −$7.5 | ≈flat |
| STOP | 11 | **−$434.0** | the bleed |
| STOP_UNFILLED (malfn) | 2 | −$223.5 | → −$118.0 normalized |
| **all-time total** | **24** | **−$122.0** | → **−$16.5** malfn-normalized |
| **this-week (≥07-27)** | **14** | **−$139.0** | 10 STOP (base −195.5, _A −92.5, _B −108.5) |

**This-week STOP split — the smoking gun for the amplifier:** the `_A`/`_B` dual-slot pairs
(07-30 onward) contributed **−$92.5 + −$108.5 = −$201** of the −$139, on **the same 4 signals**.
Single-lot those would be ≈ −$100. **Dual-slot doubled the chop-stop bleed.**

**Reconciliation with the tick engine (the key number):** repricing the CURRENT config single-lot on
the tick tape over the same this-week days = **≈ +$60** (07-27 +$132 · 07-28 −$16 · 07-29 −$117 ·
07-30 +$61). The **~$200 gap** to the live −$139 is exactly: **dual-slot doubling (~−$100)** +
**07-31 low-vol-grind fires the recon/ATR-floor filtered out but live took (4 lots, ~−$78)** +
**stop slippage**. **The recorded book is honest; the loss is an EXECUTION/EXPOSURE story layered on
a ~breakeven single-lot signal — not a broken signal.**

## Step 3 — ROOT-CAUSE (base / exit / signal?)

Tick-honest, single-position first-to-fire, 07-23 → 07-31 (all $/pt·fee honest):

**Exit sweep at the CURRENT entry (climax2.5/dom0.6/flip=True, ATR≥10):**

| exit | n | net | win% | $/tr |
|------|--:|----:|-----:|-----:|
| scalp 0.5R | 11 | −$60 | 64% | −5.5 |
| scalp 1.0R | 11 | −$100 | 45% | −9.0 |
| scalp 1.5R | 11 | −$38 | 45% | −3.5 |
| **scalp 2.0R (LIVE)** | 11 | **+$24** | 45% | +2.2 |
| scalp 2.5R | 10 | +$23 | 40% | +2.3 |
| scalp 3.0R | 10 | +$72 | 40% | +7.2 |
| chandelier | 11 | −$64 | 45% | −5.8 |
| fixed 8/12 | 11 | +$7 | 45% | +0.6 |

- **Base config? YES — `require_flip=True` is the primary culprit.** It starves the gate to **11
  fires in 6 days** and does not improve quality. Dropping it (`require_flip=False`, fade the climax
  itself instead of waiting for the delta to already flip) triples the sample AND raises net at
  every exit (below). This directly **falsifies the 07-25 rehab claim "require_flip IS the edge"**
  under tick-honest single-lot repricing.
- **Exit? YES — 2.0R is the wrong target for THIS mechanism, but only once `require_flip` is off.**
  With flip ON the book is too small to read (3.0R noise-wins). With flip OFF the shape is decisive
  (Step 4): a flush-and-flip bounce pays ~**1 ATR** reliably (78% reach 1.0R) but only ~40-45% reach
  2.0R — **the current 2.0R lets the high-probability bounce give back.**
- **Signal? SOUND in chop, correctly benched in trend.** The 78%-win 1:1 profile is a genuine
  short-horizon mean-reversion edge *in chop*; it will invert in a trend (which is why the router's
  `DOWN_OFF` and a US/trend bench are load-bearing, not optional).

**Root-cause verdict: BASE (`require_flip`) + EXIT (2.0R), with a REGIME/ToD overlay and a live
dual-slot amplifier. NOT a malfunction, NOT a dead signal.**

## Step 4 — FILTERS / config that KEEP winners while cutting bleed

A filter that "wins" only by dropping the target winners is a FAKE win — flagged and rejected as such.

**(a) `require_flip=False` (fade the climax, don't wait for the delta-flip) — the core fix:**

| exit | n | net | win% | strip-best-3 | worst LODO |
|------|--:|----:|-----:|-------------:|-----------:|
| loose scalp 0.5R | 36 | +$174 | 83% | +$120 | +$99 |
| **loose scalp 1.0R** | **32** | **+$434** | **78%** | **+$327** | **+$220** |
| loose scalp 1.5R | 30 | +$38 | 47% | −$106 ❌ | −$74 ❌ |
| loose scalp 2.0R | 30 | +$130 | 43% | — | — |
| loose scalp 2.5R | 30 | +$212 | 40% | — | — |

**loose 1.0R is the standout and it is ROBUST** (see Step 5). Note the sharp 1.0R→1.5R cliff:
widening past 1R makes the book fragile (strip-best goes negative) — proof the edge is the *fast
bounce*, not a ride. **KEEP.** ✅

**(b) OVERNIGHT-only (bench US cash 13:30–20:00 UTC) — the operator's ToD split:**

loose 1.0R by ToD: **ON n27 +$422 (81% win)** vs **US n5 +$12 (60% win)**. The US session is where a
fader gets run over (matches [[us-open-dont-bench-trend-rider]] for the *fade* side). ON-only is
still robust (strip-best-3 +$322, every LODO positive). **KEEP as a regime bench** (low cost, clean
mechanism, not a fitted threshold). ✅

**(c) ATR ceiling (fade only small flushes):** at the CURRENT strict config an `atr≤16` ceiling helps
(n7 +$188, 71% win) — consistent with "fade small flushes, not big ones." But under **loose 1.0R the
tight scalp already banks before a big-ATR run-over**, so the ceiling is largely redundant there.
**MARGINAL — fold into the ToD/router regime read, don't add a third hard threshold.** ⚠

**(d) climax_min 2.0 (looser trigger):** buys a lot of n (loose+climax2.0 1.0R = **n68 +$492**) — but
it fires into **07-29's dead chop and bleeds −$222 that day** (per-day: 07-28 +$268 / **07-29 −$222**
/ 07-30 +$121). The added n does not justify the new bad-day tail. **REJECT — do not stack.** ❌

**(e) dom_min 0.7 / 0.8:** starves to n1–5. **REJECT (NULL).** ❌

**(f) drop dual-slot `_A`/`_B` (base_size / scale-out):** the −$201 doubling in Step 2 is pure harm
on a fader whose winner is a single fast 1R pop (no tail for Lot-B to ride). **base_size 1, single
scalp — no A/B.** ✅ (live already at base_size 1 since 07-28; this says *also drop the scale-out*).

## Step 5 — ROBUSTNESS

**Recommended config — `require_flip=False`, scalp 1.0R, climax2.5/dom0.6, ATR≥10, single-lot:**

- **Full:** +$434 / n32 / 78% win.
- **Strip-the-best:** best-1 +$396 · best-2 +$360 · **best-3 +$327**. (Does NOT lean on a few
  lucky fires — the opposite of the rgv_short book.)
- **Leave-one-day-out:** −07-24 +$331 · −07-27 +$350 · **−07-28 +$220 (worst)** · −07-29 +$454 ·
  −07-30 +$360 · −07-31 +$458. **Every LODO stays strongly positive.**
- **Per-day:** 07-24 +$104 · 07-27 +$84 · **07-28 +$214** · 07-29 −$20 · 07-30 +$74 · 07-31 −$23.
  Only two mildly-red days, both small.
- **Overnight-only overlay:** +$422 / n27 / 81%; strip-best-3 +$322; worst LODO (−07-28) +$238.

**Cross-regime / OOS:** ⚠ **the binding limit.** The tick tape is **~6 days of one summer CHOP
regime** — there is **no clean-trend or trend-day week in it**. The fix is proven **on chop**; the
gate's *predicted* trend-day bleed (a fader run over) is exactly what the router `DOWN_OFF` + the
ON/US bench are there to prevent, but that side is **unproven on this tape** and must be confirmed in
shadow / a future trend week. This is a LEAD with strong in-regime robustness, not a cross-regime law.

## Step 6 — the R-sweep: PROVEN vs the GUESS (operator's cheat-sheet rule)

The regime→exit cheat-sheet guesses **fader Lot-A 0.5R / Lot-B 1.5R**. Tick-honest, that guess is
**wrong for this gate:**

- **0.5R is too tight** (loose 0.5R +$174 @ 83% — banks too little; leaves money) and **1.5R is over
  the cliff** (loose 1.5R +$38, strip-best-3 −$106 ❌ — gives the bounce back). The **proven robust
  optimum is a single 1.0R scalp** (+$434, plateau-topped: 0.5R<1.0R>1.5R, and 1.0R is the robust
  one). **PROVEN R = 1.0R single lot; the 0.5/1.5 dual-lot guess is REJECTED for this fader.**
- Per-regime R-sweep (current strict entry, small n): normal-chop peaks at 2.5–3.0R, but that book
  is data-starved (n7–8) and dominated by one clean-trend fire — do **not** trust a per-regime R
  table at this n. The robust statement is the **whole-book 1.0R under the loose entry**.

Per-segment scorecard (loose 1.0R, the recommended policy's home):

| segment | n | net | win% | $/tr | home? |
|---------|--:|----:|-----:|-----:|------|
| normal-chop | 20 | +$246 | 75% | +12.3 | ★ HOME |
| building | 5 | +$136 | 100% | +27.1 | ✅ |
| dead-chop | 5 | +$13 | 60% | +2.6 | ⚠ marginal |
| clean-trend | 2 | +$40 | 100% | +20.0 | (n too small) |
| ON (overnight) | 27 | +$422 | 81% | +15.6 | ★ HOME |
| US (13:30–20:00) | 5 | +$12 | 60% | +2.4 | ✗ bench |

---

## RECOMMENDED CONFIG (what to change)

```
capitulation_long:
  require_flip = False      # ← was True (the 07-25 "flip is the edge" — falsified tick-honest)
  target_r     = 1.0        # ← was 2.0 (fade a fast bounce, bank 1R; 1.5R+ gives it back)
  climax_min   = 2.5        # keep (2.0 adds a −$222 bad day; 3.0 starves)
  dom_min      = 0.6        # keep (0.7/0.8 starve)
  atr_floor    = 10         # keep (raising it cuts the overnight winners, −$133 at ≥14)
  base_size    = 1, single scalp   # DROP the _A/_B scale-out (no tail to ride; doubled the chop stops)
  regime bench = router DOWN_OFF (keep) + BENCH US cash 13:30–20:00 UTC / trend
```
Expected in-regime (chop-week, tick-honest): **+$434 all-session / +$422 overnight-only**, vs the
live **−$139**. Ship the config; keep the benches; **confirm the trend-side in shadow** (the one gap).

---

## ★ The TRYING — every attempt, including the NULLs and graves

- **NULL / FALSIFIED — `require_flip=True` (the CURRENT live setting).** The 07-25 rehab installed it
  as "the edge (wait for buyers to step in)." Tick-honest single-lot it **starves the gate to 11
  fires and is beaten at every exit by the loose version** (loose 1.0R +$434 / n32 vs flip 1.0R
  −$100 / n11). The flip wait enters late and skips the bounces. **The prior does not survive.**
- **NULL — widen the loose exit (1.5R / 2.0R / 2.5R / chandelier).** 1.5R falls off a cliff
  (+$38, strip-best-3 −$106); chandelier −$64 at the strict entry. **The fade does not run — there is
  no tail; bank 1R.**
- **NULL — tighten climax (3.0 / 3.5).** −$80 / −$39, starved. **NULL — dom_min 0.7 / 0.8** → n1–5.
- **NULL — raise the ATR floor (≥14 / ≥18 / ≥22).** −$133 / −$128 / −$47 — the winners live in the
  overnight **low-ATR** band (10–14); raising the floor keeps the fewer, bigger US-session losers.
  (Opposite of a momentum gate — for a fader, big ATR is the danger, not the requirement.)
- **GRAVE — the "+$492, n68" looser-climax book (climax2.0 + loose + 1.0R).** Tempting (biggest n,
  biggest headline) — and exactly the operator's "don't stack filters on one week." It buys volume
  by firing into **07-29's dead chop for −$222**; the added n does not pay for the new bad-day tail.
  **Rejected — climax stays 2.5.**
- **GRAVE — the single 07-24 14:39 violent-whipsaw +$130 (atr 32.8) US fade.** It flatters the US /
  violent buckets in the strict-entry book (US "+$7" is really +$130 winner masking 3 losers).
  Excluded, the US session is marginal-to-negative — hence the ON-only bench. A one-off, not an edge.
- **⚠ MARGINAL — ATR ceiling (atr≤16).** Real at the strict entry (+$188/n7) but largely redundant
  under loose 1.0R (the tight scalp banks before the run-over). Folded into the ToD/router regime
  read rather than added as a third hard threshold (avoid over-fitting the count).
- **Aggravators (live, not backtest) — the amplifiers behind the −$139:** (1) **dual-slot `_A`/`_B`
  doubled every chop stop** (this-week −$201 on 4 signals); (2) the **07-31 low-vol-grind fires**
  ([[low-vol-grind-untradeable-stay-flat]]) — counter-trend fades of a compressed grind the recon's
  ATR floor filtered but live took (4 lots ≈ −$78); (3) 07-23 **`STOP_UNFILLED` slippage** (Step 1).

*Caveats: ~6 days of tick tape, ONE summer CHOP regime, no trend week to exercise the fader's
predicted trend-day bleed. Everything here is a strongly-robust IN-REGIME lead, not a cross-regime
law. The single most valuable next step is a trend-week / shadow confirmation of the benched side.*
