# Greenfield Hunt — VACUUM cluster · census level "full" (week 2026-07-27 → 07-31)

**VERDICT: GRAVE. `survived = false`.** Four brand-new signals invented and killed. The VACUUM
footprint is real as a *description* and worthless as a *trigger*: after conditioning on it, the
tape gives no directional information, and every config that actually participates in the runs
loses money.

---

## 1. The target

VACUUM (census `run_census.py::cluster`) = a ≥1.5×ATR 15-min run where net aggressor flow in the
**60 s before** the run was heavy (|flow| > 50) and pointed the **opposite** way to the eventual
move — price ran *away from* the tape. Snap-back / stop-run / liquidity-vacuum footprint.

Frozen census: 73 runs, 53 sat out, $14,519 hindsight ceiling. **17 VACUUM runs, 13 sat out**
(census level "full" = all sat-out runs), **$3,106 of ceiling** on those 13.

| # | run start (UTC) | dir | move | $ ceil | flow(60s) | ATR15 | ER15 | session |
|---|---|---|---|---|---|---|---|---|
| 1 | 07-27 15:53:20 | UP | +115 | 230 | −225 | 63 | 0.05 | US |
| 2 | 07-27 16:48:20 | DN | −139 | 278 | +62 | 68 | 0.04 | US |
| 3 | 07-28 23:09:50 | UP | +124 | 249 | −101 | 79 | 0.18 | ON |
| 4 | 07-28 23:54:10 | UP | +101 | 202 | −71 | 200 | 0.61 | ON |
| 5 | 07-29 00:18:10 | DN | −113 | 226 | +87 | 60 | 0.00 | ON |
| 6 | 07-29 01:01:10 | DN | −117 | 234 | +233 | 84 | 0.37 | ON |
| 7 | 07-29 16:15:25 | UP | +148 | 297 | −515 | 111 | 0.59 | US |
| 8 | 07-29 16:42:25 | UP | +94 | 188 | −92 | 96 | 0.22 | US |
| 9 | 07-29 20:13:25 | DN | −111 | 222 | +524 | 171 | 0.02 | US |
| 10 | 07-30 00:52:35 | UP | +115 | 230 | −140 | 60 | 0.10 | ON |
| 11 | 07-30 18:58:50 | UP | +116 | 232 | −62 | 35 | 0.13 | US |
| 12 | 07-30 20:00:50 | UP | +115 | 230 | −857 | 61 | 0.08 | US |
| 13 | 07-31 19:50:20 | DN | −144 | 288 | +785 | 84 | 0.30 | US |

(The other 4 VACUUM runs were caught by live gates and are excluded from the target set.)
Run detection was re-derived locally with the census algorithm — **73 runs / 17 VACUUM reproduced
exactly**, so no `run_census.py` re-run was needed.

## 2. Tape, cost, and segmentation

* **Tape:** `capture.db` MNQ ticks — 10,080,959 ticks, 2026-07-23 22:00 → 07-31 21:00 UTC
  (137,521 5-s bars; 99,168 "live" bars after the no-trade/maintenance mask).
  **07-24 is a genuine OOS leg** (pre-census-week Friday); 07-27→07-31 is the census week.
* **L2 book:** 78 M rows, levels 0–3 both sides, 07-27 20:00 → 07-31 21:00 (dual-feed rows at the
  same ms → normalised per snapshot, not summed).
* **Tick-honest exits:** entry = first tick *after* the signal bar closes; the entire exit path is
  replayed on the 250 ms tick stream; within a tick the **stop is checked before the target**
  (conservative). Cost **$5/round-trip**, MNQ $2/pt. One position at a time + cooldown.
* **Regime segmentation** (ATR level + ER, not the clock — ATR carries the time-of-day effect):
  `ATR15` = 15-min hi-lo range in points; `ER15` = |15-min displacement| ÷ Σ|1-min legs|.
  * `violent` = ATR ≥ 110 & ER < 0.30 (5.0 k bars) · `trend` = ER ≥ 0.50 (14.4 k)
  * `building` = 0.30 ≤ ER < 0.50 (25.2 k) · `dead-chop` = ATR < 45 (60.1 k) · `normal-chop` = rest (32.7 k)
  * cross-cut by session: **US** = 13:30–21:00 UTC vs **ON** (overnight/pre-open).

## 3. The four invented signals (exact mechanical specs)

All are causal (bar-close decisions), all fire **both sides**, none reuses an existing gate.

**VR-1 — VACUUM RECLAIM** (flush → trapped aggressors → reclaim)
Let `hi_w/lo_w` = rolling hi/lo of the last *w* 5-s bars, `net_w` = signed aggressor flow over them.
LONG when `hi_w − close ≥ f·ATR15` (a real flush) **and** `net_w ≤ −F` (sellers were the aggressors)
**and** `close − lo_w ≥ rec·(hi_w − lo_w)` (price has reclaimed off the low) **and** `low > lo_w`
(this bar is not a new low). SHORT = mirror. Stop = `lo_w − 0.10·ATR15` (structural, clipped 6–60 pt);
target = R × risk; 15/30-min cap; 15-min cooldown. Swept w ∈ {12,24,60}, f ∈ {0.10…0.40},
F ∈ {100…600}, rec = 0.35.

**VR-2 — ABSORPTION FADE** (heavy flow, no travel, at the extreme)
LONG when `net_w ≤ −F` **and** `|close − close[−w]| ≤ eff·ATR15` (the flow bought nothing — absorption)
**and** price sits in the bottom `pos` of the *w*-bar range. SHORT = mirror. Stop = k·ATR15 or fixed;
target R × risk. Swept w ∈ {12,24,60}, F ∈ {200,400,800}, eff ∈ {0.08,0.15,0.25}, pos = 0.30.
A session-normalised variant (`net_w` z-scored against its trailing 2 h) was also tested — **worse**.

**VR-3 — TRAP BREAK** (delayed, confirmed continuation of the vacuum)
LONG when `net_w ≤ −F` (sellers heavy) **and** `close` breaks above the prior `w2`-bar high — i.e. the
sellers are now trapped and price is running. SHORT = mirror. Swept w ∈ {24,60}, F ∈ {200,400,800},
w2 ∈ {12,36,72}.

**VR-4 — LIQUIDITY VACUUM (L2)** (the literal reading; uses book depth the desk does not consume)
`ask_rel/bid_rel` = L0–L3 depth ÷ its own 30-min median; `imb` = (bid−ask)/(bid+ask).
LONG when `ask_rel ≤ thin` (no supply above) **and** `imb ≥ +imb₀` (bids stacked) **and** `net_w ≤ −F`
(sellers hitting a holding bid). SHORT = mirror. Also tested book-only (no flow) and flow-aligned
(`vr4b`, continuation) readings. Swept thin ∈ {0.85,0.70,0.55}, imb₀ ∈ {0.05…0.25}, F ∈ {0…400}.

## 4. Exit-free edge screen (before any exit tuning)

For every signal (deduped ≥60 s), replay the forward tick path: first touch of ±20 pt (a cost-free
coin-flip test) and the 5/15-min displacement. **Baseline on random live bars: touch+ 50.1 % (long)
/ 50.6 % (short).**

| family | best block | n | touch+ | d15 (pt) | read |
|---|---|---|---|---|---|
| VR-1 | w24 f0.10 F100–600 | 568–3681 | 45.2–50.6 % | +2.3…+7.8 | **no edge** — touch rate at/below baseline; d15 is drift |
| **VR-2** | w24/60 F200–400 eff .08–.15 | 248–1095 | **54.0–60.2 %** | +5.3…+11.7 | the only broad plateau — pursued |
| VR-3 | w24/60 F200–800 w2 = 72 | 26–504 | 42.3–50.9 % | +8.8…+39 | below-coin-flip hit rate with a fat tail (lottery) |
| VR-4 | any book cut | 26–2579 | 42.0–50.6 % | −0.9…+13 | **below baseline**; >55 % only at n = 26–50 (n-collapse) |

VR-2's 54–60 % touch rate held across an entire (w × F × eff) block — a plateau, not a spike. That is
why it got the full battery. VR-4's only good numbers appear where n collapses to 26 — the textbook
curve-fit tell, called out and dropped.

## 5. Regime-segmented P&L and the R sweep (policy, not a static config)

VR-2, 480 configs (signal × stop × R × cap). **Only 36 % positive; median net −$271; median
−$1.45/trade.** The signal-level 55–58 % hit rate does not survive $5/RT plus real stops.

**Per-regime sign consistency across those 480 configs** — the honest home-segment answer:

| regime | % of configs positive | median net |
|---|---|---|
| dead-chop | 26 % | −$132 |
| normal-chop | 34 % | −$134 |
| trend | 23 % | −$217 |
| building | 54 % | +$30 |
| violent | 53 % | +$35 |

Three regimes are consistently negative → OFF. The two "positive" regimes are **coin flips at the
config level**, and `building` (ER 0.30–0.50) + `violent` (ATR ≥ 110, ER < 0.30) sit at opposite ends
of the regime axis — no coherent mechanism links them. Neighbouring configs also disagree about which
segment pays (`trend` = +$1,192 in one config and −$607 one knob away).

**R sweep per regime** (median $/trade over 16 signal × 2 stop configs, 1800 s cap). Operator's fader
prior is Lot-A 0.5R / Lot-B 1.5R:

| regime | R=0.5 | R=1.0 | R=1.5 | R=2.0 | R=3.0 | R=4.0 | median n |
|---|---|---|---|---|---|---|---|
| building | +1.0 | +2.7 | +0.1 | +4.8 | +4.8 | +8.2 | ~50 |
| dead-chop | −8.5 | −6.7 | −6.9 | −9.9 | −10.5 | −11.7 | ~20 |
| normal-chop | −1.1 | −1.8 | −1.6 | −1.5 | +4.0 | +5.6 | ~55 |
| trend | −6.6 | −7.0 | −10.9 | −12.3 | −10.2 | −14.6 | ~26 |
| violent | −6.5 | **+22.7** | **+21.4** | **+24.7** | **+43.7** | **+45.2** | **~16** |

**Proven vs guessed:** the guessed fader 0.5R is negative in *every* regime, including the one that
looks alive — the fader-R prior does **not** hold for this signal. The only positive corner is a wide
stop (0.40 × ATR15) with R ≥ 3, i.e. the opposite of a fader. And it is fake — see §6.

## 6. Robustness battery — every test fails

Representative plateau config `VR-2 w60 F200 eff0.15 stop 0.40·ATR15 R=2 cap 30 m`:
n = 205, net **+$1,301**, win 42.4 %, $6.3/trade *(all-tape diagnostic only)*.

* **STRIP-THE-3-BEST:** +$1,301 → **+$596**. The 3 best trades are 54 % of the net — and all three
  are the *same* clipped max winner ($235), i.e. the R=2 target on a wide stop. On the neighbouring
  config the same test takes +$1,325 → +$620 (53 %).
* **Strip-3 across the whole policy** (48 configs per segment, median stripped net):
  all-tape **−$412** (29 % positive) · violent **−$132** (28 %) · building+violent **−$17** (48 %) ·
  ATR ≥ 90 **−$179** (38 %) · US & ATR ≥ 90 **−$302** (23 %). **The entire "violent-regime edge" is
  three trades per config.** n = 16 per config in that bucket — the edge appears exactly where n
  collapses.
* **Leave-one-day-out:** dropping 07-30 takes +$1,301 → +$564; dropping 07-31 → +$583. Two of six
  days carry it. The neighbouring config is carried by the *other* two days (07-27, 07-28) and
  *loses* on 07-30. Day attribution is noise.
* **OOS leg (07-24, outside the census week):** n = 36, **+$94** ($2.6/trade); neighbour n = 41,
  **+$11** ($0.26/trade) — effectively zero. Across the whole VR-2 config block the median OOS net is
  **−$104**.
* **Long/short symmetry:** config A shorts +$1,482 / longs −$181; config B (one knob away) shorts
  +$717 / longs +$607. The asymmetry is not stable → not a directional effect, just the week's
  −2 pt/15-min downward drift plus noise.
* **Family-level summary** (each family swept over stop × R × cap):

| family | configs | % positive | median net | median $/t | strip-3 still positive | median OOS | max runs caught |
|---|---|---|---|---|---|---|---|
| VR-1 reclaim | 288 | 23 % | −$800 | −$2.95 | 8 % | −$306 | 5/13 |
| VR-2 absorption fade | 192 | 48 % | −$65 | −$0.25 | 22 % | −$104 | 5/13 |
| VR-3 trap break | 144 | 49 % | −$4 | $0.00 | 25 % | −$206 | 6/13 |
| VR-4 book vacuum | 288 | 34 % | −$153 | −$2.30 | 7 % | n/a (no book pre-07-27) | 2/13 |

## 7. BIG MOVES CAUGHT — and the participation/profit anti-correlation

Best configs catch **1–3 of the 13** sat-out VACUUM runs (census ±300 s alignment window; 5/13 on a
loose −300…+900 s window). The configs that *do* participate are the ones that bleed:

| runs caught (of 13) | configs | median net | % positive |
|---|---|---|---|
| 0 | 69 | −$320 | 36 % |
| 1 | 374 | −$358 | 34 % |
| 2 | 434 | −$459 | 24 % |
| 3 | 236 | −$683 | 20 % |
| 4 | 38 | −$1,274 | 16 % |
| 5 | 37 | −$1,503 | **0 %** |
| 6 | 9 | −$1,598 | **0 %** |
| 7 | 3 | −$3,091 | **0 %** |

**corr(runs caught, net) = −0.32 over 1,200 configs.** Participation is bought with churn, and the
churn costs more than the runs pay. The best participation (7/13) nets −$2,012 / −$3,091.

## 8. Autopsy — why it cannot work (the ex-ante detectability test)

At the 13 run starts, each candidate feature's percentile inside 6,000 random live bars (signed
features flipped so "+" = points the way the run went), with a two-sided sign test:

| feature | mean percentile | p | read |
|---|---|---|---|
| net flow 60 s (signed) | 0.22 | 0.000 | significant — but **definitional** (VACUUM *is* opposite flow) and it points the WRONG way |
| net flow 2 min (signed) | 0.18 | 0.003 | same tautology |
| net flow 5 min (signed) | 0.47 | 1.000 | gone by 5 min |
| \|net flow\| 60 s | 0.57 | 1.000 | magnitude adds nothing |
| 60-s volume | 0.76 | 0.022 | runs start in busy tape — **non-directional** |
| ATR15 | 0.66 | 0.003 | runs start in hot tape — **non-directional** |
| 2-min range | 0.75 | 0.022 | ditto |
| ER15 | 0.38 | 0.267 | nothing |
| **position in 2-min range** | **0.53** | **1.000** | **nothing** — kills the "fade at the extreme" premise |
| absorption (pts per contract) | 0.50 | 1.000 | **no absorption signature at all** |
| book imbalance | 0.38 | 0.549 | nothing |
| far-side depth (ask_rel) | 0.48 | 1.000 | **no liquidity vacuum in the book** |

Base rate of the footprint itself (deduped 15-min events, forward 15-min move ≥ 90 pt):

| condition | events | ran AGAINST flow ≥90 | ran WITH flow ≥90 | P(vacuum run) | P(flow run) |
|---|---|---|---|---|---|
| unconditional | 556 | — | — | 8.8 % (either way) | — |
| \|net60\| ≥ 50 | 549 | 23 | 19 | 4.2 % | 3.5 % |
| \|net60\| ≥ 200 | 444 | 23 | 17 | 5.2 % | 3.8 % |
| \|net60\| ≥ 800 | 116 | 15 | 9 | 12.9 % | 7.8 % |
| ATR15 ≥ 90 & \|net60\| ≥ 50 | 176 | — | — | 7.4 % | **13.6 %** |

**Cause of death.** Heavy one-sided flow is followed by a ≥90 pt run against it ~4–5 % of the time
and *with* it ~3.5–4 % of the time — a coin flip on direction, and no more likely than the 8.8 %
unconditional base rate. Once the tape is hot (ATR ≥ 90) the tilt actually flips *toward*
continuation (13.6 % with-flow vs 7.4 % against). The VACUUM label is a **post-hoc description of
what happened**, not a condition that precedes it — it is defined by the sign of the outcome.
Nothing measurable at the trigger — price location, absorption, book depth, ER, session — separates
the 13 runs from the ~500 identical-looking setups that go nowhere. Every "winner" found in this hunt
was a handful of outlier trades inside an n ≈ 16 regime bucket.

## 9. GRAVES

| # | signal | best config | n | net | win % | cause of death |
|---|---|---|---|---|---|---|
| 1 | **VR-1 Vacuum Reclaim** | w24 f0.2 F600 · 0.40 ATR stop · R3 | 93 | +$2,109 headline, but only 23 % of 288 configs positive (median −$800) | 36.6 % | The reclaim confirmation adds nothing — the flush low is not a level, price simply re-flushes. Only 8 % of configs survive strip-3-best; median OOS −$306. |
| 2 | **VR-2 Absorption Fade** | w60 F200 eff.15 · 0.40 ATR stop · R2 | 205 | +$1,301 headline → **+$596 after strip-3**, **+$94 OOS**; family median −$65 | 42.4 % | The 54–60 % touch rate is real but worth ~$1/trade before cost; the whole "violent-regime edge" is 3 trades per config at n = 16. Catches 1/13 runs. |
| 3 | **VR-3 Trap Break** | w24 F400 w2 = 72 · 0.40 ATR stop · R3 | 62 | +$1,870 headline; 49 % of configs positive, median −$4, median OOS −$206 | 51.6 % | Below-coin-flip hit rate (42–51 % on ±20 pt) carried by a fat tail that is 3 trades. Catching 6/13 runs costs −$1,465 to −$3,127. |
| 4 | **VR-4 Liquidity Vacuum (L2)** | book-only thin .55 imb .25 | 26 | headline touch+ 75 % at **n = 26**; 34 % of 288 configs positive, median −$153 | 48.9 % | Pure n-collapse. Book depth at the run starts sits at its 48th percentile — there is **no** far-side depletion before these runs. Catches 2/13. |
| 5 | *(prior week, kept for the record)* Absorption Fade v1 | F200 P8 STOP25 TGT45 | 238 | −$1,985 | 38 % | Naive static fade of heavy flow; 13/144 configs positive, neighbours flip sign; longs-only −$3,649 / shorts-only −$1,610. Same disease, killed again this week with a stricter spec. |

## 10. What would change this verdict

1. **A level, not a footprint.** Nothing here used *where* price was (prior-session hi/lo, VWAP bands,
   overnight-range edges). 8 of 13 runs start within 10 pt of a 2-min extreme, but that extreme has
   zero percentile signal — an external reference level is the untested axis.
2. **Order flow at trade granularity** (iceberg/refill detection, per-price absorption at the touched
   level) instead of a 60-s net-flow sum. The 5-s aggregate provably throws the information away
   (absorption percentile = 0.50).
3. **More tape.** 13 target events in one week cannot support a robust claim either way. Anything
   that survives strip-3-best on n ≈ 16 buckets is fiction; a VACUUM gate needs 6–8 weeks of tick
   capture per regime bucket before it should be believed.
4. Until then: **do not arm anything that fades heavy flow.** The live side says the same
   (memories [[router-benching-lessons-0729]], [[some-days-stay-out-fully-flat]]), and this week's
   tape says that once ATR ≥ 90 the money is on the **continuation** side, not the fade.

*Working: `scratchpad/{vac_data,book_data,runs,engine,signals,es,hunt,drill,sweep,sweep3,policy,robust,disc,precision}.py`.
All numbers tick-honest on `capture.db`, net of $5/round-trip.*
