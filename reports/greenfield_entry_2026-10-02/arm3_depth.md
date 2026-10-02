# ARM 3 — THE LEVEL-2 BOOK AT THE TURNS

*GAZBOT greenfield entry study, 2026-10-02. MNQ. Read-only throughout: no order, no `/api/control`,
no service touched, nothing written to `gazbot7.db` / `capture.db` / `depth.db`.*

---

## 0. THE DATA, FIRST — AND THE BRIEF'S PREMISE WAS WRONG IN BOTH DIRECTIONS

The brief told me to check the depth span first and to scope down if it was thin. It is not thin, but
finding that out required not stopping where the brief pointed.

| where I looked | MNQ depth coverage |
|---|---|
| `data/depth.db` (the hot tier the brief named) | **19 full sessions**, 2026-09-07 → 10-02, 5.5M snapshots |
| `gazbot7.lake` `depth` stream (Parquet + hot, de-duplicated) | **57 session-days**, 2026-07-16 → 10-02, **15.8M snapshots** |
| B2 `plain/tape/depth/MNQ/` | 65 objects — the 56 lake partitions, 8 Saturday fragments, today |

`depth_capture.RETENTION_DAYS = 20` prunes the hot tier; `tape_mirror.py` has been exporting
`depth_snap` to the lake the whole time. **Had I scoped this arm to `depth.db` as instructed I would
have reported 19 sessions and built the study three times too small.** This is
[[a-retention-policy-describes-the-hot-tier-not-the-data]] for the third time on this desk — the same
shape as the `aggressor` claim the operator caught, where a prereg's entire justification rested on
"only ~6 days exist" while the lake held 46 partitions.

It matters because of power. At the brief's own fire-rate bar of 3-6/session:

- on **19** sessions → 57-114 fires. 2σ binomial ≈ ±9-13pp. **The brief's own ±6pp standard is
  unreachable**, and the fire-rate bar and the power bar would have been mutually exclusive.
- on **57** sessions → 171-342 fires. 2σ ≈ ±5.4-7.6pp. The standard is **just** reachable.

The second premise in the brief — "~13.3M rows a day" — is also wrong. MNQ depth runs **~280,000
snapshots/session** (0.25s sampling, dedup on an unchanged book); 13.3M is the whole 47-session
local store, not a day.

**What I actually measured:** 56 sessions, 75,688 minutes. **2026-08-17 excluded** — only 20.5% of its
snapshots are clean (its ask levels come from a different contract than its bids, median spread
−66.25pt). That day was found independently by the 2026-09-04 L2 study and reproduces exactly here;
nothing outside the L2 store is affected, which is why no other instrument flags it.

**Cleaning**, reusing `reports/friday_v2/scripts/book_features.clean_mask` rather than reinventing
it: uncrossed, spread in (0, 10pt], all 20 prices and 20 sizes present, levels monotone away from the
touch. **98.8% of snapshots survive**; 1.34% of minutes end up with no clean book and are treated as
"do not trade" (fail-closed, the same contract as `depthfeed.book_at`). An absent rung is *unknown*,
never zero — calling it zero manufactures the very vacuum this arm is testing for.

### The two tapes, stated explicitly

- **Signal** — `lake.depth` (250ms L2, 10 levels/side), aggregated to per-minute means with
  `ts_ms // 60000`.
- **Race** — 1-min bars built from **5s TRADE bars only**. Not depth mid.
- **Checked:** last depth-mid in a minute vs last 5s trade close — median |diff| **0.25pt** (exactly
  half the 0.53pt median spread), p95 1.0pt, mean bias **−0.011pt**. The two tapes are aligned, so
  this is not the 41%-survival switch that bit the earlier depth-MID study.
- **Production** reads both: `day_rider`'s `_minute_bars` is the MD_STREAM trade tape (matches my
  race series), and `depthfeed.DepthFeed` reads `depth_snap` live at ≤5s staleness (matches my
  signal series). No lab/production gap for either half.

### ⚠ The physical ceiling on this whole arm, measured not assumed

The visible book spans a **median 4.5 points across both sides** — ~2.25pt per side for all 10
levels — against a median MNQ ATR near 9.5pt. **The book sees 0.24 ATR.** Median total resting size
is 214 lots; median size at the touch is 4.1 lots.

So "a thinning of the far side" and "absorption at a level" are only testable *within a quarter of an
ATR of the touch*. A wall one ATR away — which is what a human means by the phrase — is outside this
feed entirely, and no amount of history fixes that. The 2026-09-04 study reached the same conclusion
and it is a fact about the entitlement, not a null result.

---

## 1. VERDICT

**The book does change shape at the turns, and one family of rules beats a matched random control by
+7 to +9pp at 50 points on 56 sessions at a tradeable 4.2 fires/session. It does not survive a
hold-out in time, and I cannot call it proven.**

Three things are solid:

1. **A side-specific liquidity vacuum is the only book feature here with any signal.** Price ≥2 ATR
   extended with the side it leans on at its 180-minute thinnest → continuation wins **58.7%** vs a
   50.0% control, **+8.6pp [+1.4, +16.0]** day-clustered, n=150, **4.23 fires/session**. Three
   neighbouring extension settings (1.0 / 1.5 / 2.0 ATR) all land +7.2 to +8.6pp with CIs excluding
   zero, and the sign is the same at 100pt.
2. **The momentum half of that rule is a coin, so whatever is there is the book's.** The extension
   gate alone fires 20-22×/session and scores **−1.8 / +0.7 / +2.4pp**. Splitting those same
   episodes by the book gives **+19.0 / +15.2 / +21.4pp** in the thin cell against **−1.4 / +0.1 /
   −0.5pp** in the thick cell — same sign at all three settings, but n = 7 / 19 / 13. The mechanism
   is visible; it is not measured.
3. **Raw book imbalance is refuted again, and the side-specific measure is why.** Total-book
   depletion (`vacuum_dep`) gives +4.1pp at 50pt but **−3.9pp at 100pt** and **−1.8pp** stripped of
   5 days; the side-specific twin holds up at both. Summing both sides cancels the thing that
   carries the information. Book-imbalance climax/roll-off — the structural analogue of the
   operator's CVD rule — is **negative** (−2.1pp at 50, −3.7pp at 100).

And the reason I cannot call it proven:

| `vacuum_side_p1_2.0atr_with` | ±50pt edge |
|---|---|
| all 56 sessions | **+8.6pp** [+1.4, +16.0] n=150 |
| first 28 sessions | **+14.4pp** n=76 |
| **last 28 sessions** | **+3.6pp** n=74 |
| strip the best 3 days | +5.2pp |
| strip the best 5 days | +4.3pp |

Two-thirds of the effect lives in the first half of the window, and in 30 null worlds (control vs
control on the same fires) **2 reached the measured edge** — p ≈ 0.07 before any multiplicity charge,
against ~58 independent cells searched. Under the desk's own three-outcome rule this is **PROMISING,
not PROVEN**: it goes to shadow, where it costs nothing but time. It is not REFUTED — its control
loses, its mechanism is coherent, its neighbours agree, and it degrades gracefully rather than
flipping sign.

---

## 2. RANKED SHORTLIST — best first

Every row: 56 sessions, symmetric race (+N before −N on 1-min **trade-bar** highs/lows within
120 min), control = **mean of 50 matched random draws** (same count, same session, random minute,
random side), CI = day-clustered bootstrap over sessions, 5,000 reps. `$/session` is **race-implied
at one MNQ lot** on a ±N bracket at $1.50/RT — an illustration of scale, *not* a backtest: it has no
stop placement, no scale-out, and it excludes the 37% of fires where neither barrier is reached
inside 120 min.

### 1. `vacuum_side_p1_2.0atr_with` — ★ the pick

> **Rule.** On 1-min bars with a clean book (≥20 clean snapshots in the minute):
> `mv = close[i] − close[i−60]`; `atr` = 14-period ATR on 1-min bars.
> `bid_pctl` / `ask_pctl` = percentile rank (0-100) of that minute's mean total resting size over
> levels 1-10 on that side, within its own trailing **180-minute** window.
> `lean = bid_pctl if mv ≥ 0 else ask_pctl`.
> **Fire** on the first minute `(|mv| ≥ 2.0 × atr) AND (lean ≤ 1)` becomes true after being false,
> with a **30-minute cooldown**. **Direction = sign(mv)** — *with* the move.

| | fires/sess | rule | control | edge | day-clustered 95% | n | $/sess @1 lot |
|---|---|---|---|---|---|---|---|
| ±50pt | **4.23** | 58.7% | 50.0% | **+8.6pp** | **[+1.4, +16.0]** | 150 | **+$43** |
| ±100pt | 4.23 | 53.5% | 49.2% | +4.2pp | [−6.5, +15.9] | 86 | +$19 |

Hold-out +3.6pp / strip-best-5 +4.3pp → the honest forward range is **+$10 to +$43 per session at one
lot**. Fires in 56/56 sessions, median 5, max 8 — no day carries it. Hours: 18% Asia (00-07Z,
permanently benched), 32% Europe, 18% US, 32% 20-24Z. **~1 fire in 5 is untradeable under standing
policy**; budget ~3.5/session net.

**Mechanism.** Price is two ATR extended and the liquidity on the side it is leaning on has emptied
to a 180-minute low, so each unit of flow travels further and the move continues. Note the sign: the
naive reading — "support has gone, the rally fails" — is the `against` variant and it is **negative**
(−7.2pp). This is a *travel-cost* effect, not a *support* effect: makers step out of the way in front
of a trend rather than catching it.

### 2. `climax_nf_div_99/60_cool120_exh` — the only candidate that is bigger at the bigger target

> **Rule.** `nf_div = imb(L1-3) − imb(L4-10)`, where `imb(X) = (bid_size(X) − ask_size(X)) /
> (bid_size(X) + ask_size(X))`, per minute. Gauge = position 0-100 of `nf_div` in its trailing
> 180-min range. Fire when the gauge reaches **≥99** then crosses back below **60** (mirrored at
> ≤1 / >40), **120-minute cooldown**. Direction = **against** the pinned side.

| | fires/sess | rule | control | edge | day-clustered 95% | n | $/sess @1 lot |
|---|---|---|---|---|---|---|---|
| ±50pt | 6.05 | 54.6% | 49.5% | +5.1pp | [+0.1, +9.9] | 260 | +$36 |
| ±100pt | 6.05 | 58.2% | 49.2% | **+9.0pp** | **[+1.1, +16.9]** | 134 | **+$75** |

Ranked second despite the larger 100pt edge, for three reasons. **Strip-best-3 collapses it to
+1.4pp** — far more concentrated than the vacuum family. Its fire rate is 6.05, at the ceiling of the
bar. And its **decay profile is flat** (+4.4 / +7.7 / +3.0 / +7.2 / +4.8pp at 0 / 5 / 15 / 30 / 60
minutes' delay) — book information should *decay*, as OFI does from r=+0.688 to r=−0.001 in 60
minutes. A book feature whose edge is unchanged an hour later is probably not reading the book; it is
reading some slower state the near/far split happens to correlate with. **That is a mechanism
warning, not a bonus.** Worth shadowing at 100pt — the desk's own money is in 1-4h holds (+$86/entry
over 30, against −$27/entry under 15 min) — but find out what it is actually tracking first.

### 3. `absorption_v75_r75_s75_withdeep` — the only one that holds out

> **Rule.** Per minute: `vol_pctl` ≥75 and `(high−low) ≤ 0.75 × atr` and exactly one side's
> total-L1-10 `pctl` ≥75 (all percentiles over the trailing 180 min). Fire on the rising edge,
> 30-min cooldown. Direction = **toward the deeper side**.

| | fires/sess | rule | control | edge | day-clustered 95% | n | $/sess @1 lot |
|---|---|---|---|---|---|---|---|
| ±50pt | 4.66 | 54.1% | 49.5% | +4.6pp | [−1.4, +10.7] | 233 | +$28 |
| ±100pt | 4.66 | 54.9% | 49.6% | +5.3pp | [−3.2, +13.5] | 142 | +$33 |

Both CIs include zero, so by the strict bar it is nothing. But it is **the only candidate stable
across the hold-out: +3.4pp first half, +5.2pp second half** — the opposite profile to the two above,
and it is positive at both targets. On the brief's own logic (*neighbours agreeing matters more than
one cell clearing a bar*) that stability is worth more than the vacuum family's larger in-sample
edge. Clean mechanism: heavy volume with a sub-ATR range and one side unusually deep is size resting
and being eaten without price moving. **Shadow it alongside #1; it is the natural diversifier because
its failure mode is different.** ⚠ 49% of its fires are in Europe hours and 26% in Asia.

### 4. `vacuum_side_p1_1.0atr_with` / `_1.5atr_with` — the neighbours, not separate ideas

+7.3pp [+1.0,+13.7] n=176 at 4.95/sess, and +7.2pp [+0.7,+13.7] n=168 at 4.64/sess. These exist in
the shortlist only as **#1's corroboration**: three adjacent extension thresholds giving the same
answer is why #1 is not a lone standout cell. Ship one of the three, not three rules. 2.0 ATR is the
pick because it is the most robust of the three on both the hold-out (+3.6 vs +1.2 / +1.0) and
strip-best-5 (+4.3 vs +2.0 / +1.9), and it fires least.

### PARKED — real but below the fire-rate bar

`extension ≥ k·ATR AND leaned-side ≤ p1`, scored on the **extension** episode rather than the book
edge: **+19.0 / +15.2 / +21.4pp** at k = 1.0 / 1.5 / 2.0, n = **7 / 19 / 13**, 0.25-0.50 fires/session.
This is the purest statement of the mechanism and the largest effect in the study, and it is
untradeable at a quarter of a fire per session and unmeasurable at n=13. It is the single best reason
to keep collecting: 19 resolved races came from 56 sessions, so **n=100 needs ~295 sessions —
about 1.2 years of depth capture at ~250 sessions a year**, and the store already has 57 banked. Do
not loosen the p1 gate to make the count arrive sooner; tuning a threshold to manufacture n is how
the in-sample edge above got its size.

### REFUTED — measured negative or beaten by its own control

| rule | why |
|---|---|
| `climax_imb_c10_*_exh` | **−2.1pp** @50, **−3.7pp** @100, −4.6pp strip-5. Book imbalance pinned at an extreme then rolling off — the structural analogue of the operator's CVD climax — carries nothing. Consistent with the prior r=+0.07 single-feature probe. |
| `climax_imb_top_*` | −1.4 to +2.4pp across settings, inside noise at every cell. |
| `vacuum_dep_*` (total book) | +4.1pp @50 but **−3.9pp @100**, **+0.3pp** strip-3, **−3.0pp** hold-out, and its decay dies by d=5 (+8.4 → +2.5). Summing both sides destroys the side-specific signal. |
| extension-only (plain momentum) | −1.8 / +0.7 / +2.4pp at 20-22 fires/session. The incumbent loses, which is what licenses #1 — and also means #1 is not a momentum rule in disguise. |
| `absorption_*_againstdeep` | **Incoherent across thresholds**: `s75_withdeep` is +11.0pp @100 while `s90_againstdeep` is +13.8pp @100 — the same mechanism wanting opposite sides at adjacent size thresholds. That is noise wearing a result's clothes, and it is why #3 is ranked on its hold-out rather than its headline. |

### ⚠ Information lifetime — the mechanism check that the vacuum family passes

Edge at 50pt, entering *d* minutes after the fire:

| rule | d=0 | d=5 | d=15 | d=30 | d=60 |
|---|---|---|---|---|---|
| `vacuum_side_p1_1.5atr_with` | +9.9 | **+11.3** | +1.0 | +4.4 | −5.4 |
| `vacuum_side_p1_1.0atr_with` | +6.0 | +8.7 | +5.5 | +3.8 | −3.0 |
| `vacuum_side_p1_2.0atr_with` | +10.1 | −3.1 | +3.7 | +2.6 | −12.5 |
| `vacuum_dep_p1_1.5atr_with` | +8.4 | +2.5 | −2.2 | +1.9 | −1.2 |
| `climax_nf_div_c120_exh` | +4.4 | +7.7 | +3.0 | +7.2 | +4.8 |

The vacuum family survives ~5 minutes, is halved by 15, and is **negative at 60** — exactly the decay
a genuine liquidity effect should show, and the brief asked for this test explicitly. Operationally:
**the fill has to be within a few minutes of the fire.** `climax_nf_div`'s flat profile is the
anomaly discussed in #2.

---

## 3. THE SEARCH, CHARGED

| pass | cells |
|---|---|
| first pass, 16 rules × 2 targets | 32 |
| scored pass at 3-6 fires/session, 24 rules × 2 targets | 48 |
| information lifetime, 12 rules × 5 delays | 60 |
| incumbent/nested split, 3 k × 3 cells × 2 targets | 18 |
| final ranking, 7 candidates × 2 targets | 14 |
| **race-scored cells total** | **172** |
| of which **independent** (the rest are exact complements or delayed re-scores of one population) | **~58** |
| threshold calibration — **fire rate only, no race computed** | 48 |

Two honesty notes. **The two side conventions of any trigger are exact complements** — same fires,
opposite side, so their edges sum to zero and only one is information plus one post-hoc bit of sign
choice. I have counted them that way. And **every threshold was chosen on fires/session alone, in
`calib.py`, with no outcome computed**, precisely so the 3-6 bar could not be used to shop for P&L;
the full fire-rate grid is in the artifacts. At ~58 independent cells, **~3 false positives at p<0.05
are the expectation** — which is the whole reason #1 rests on three agreeing neighbours and a losing
incumbent rather than on its own CI.

---

## 4. ⚠⚠ THREE FINDINGS THAT ARE NOT ABOUT THIS ARM — they hit arms 1, 2 and 4

All three live in `scripts/entry_cvd_climax.py`, which `entry_signals.py` imports for `load()`,
`race()`, `gauge()` and `triggers()`. **Arm 3 is immune to all three** (own loader, 5s-only bars,
floor division) — which is also how they surfaced.

**(a) `bars` is read with no `timeframe` filter, and one `1day` bar poisons a whole minute.**
`load()` does `FROM bars WHERE symbol='MNQ'` then `MAX(high), MIN(low) GROUP BY minute`. MNQ `bars`
holds eight timeframes: `5s`, `1min`, `1m`, `3m`, `5m`, `5mins`, `1hour`, `1day`. Median range by
timeframe: `5s` 2.50pt, `1min` 8.50pt, `1hour` **40.75pt**, `1day` **310.75pt**.

- **83,869** MNQ minute buckets carry ≥2 timeframes; 8,815 contain a `1hour` or `1day` bar.
- **7,805 buckets** have their range inflated by **>25pt** versus the 5s-only truth; worst case
  **+1,228pt**.
- ⚠⚠ **And `race()` checks the favourable barrier first:** `if fav >= n_pt: return 1` precedes
  `if adv >= n_pt: return 0`. A bar spanning ±310pt satisfies both, so **every contaminated bar is
  scored as a WIN**, for rule and control alike. At ±50pt and ±100pt that is a guaranteed win on
  thousands of minutes.
- Fix: `AND timeframe = '5s'` (the only timeframe covering all 57 depth sessions, 923k bars) and make
  `race()` return `None`, not `1`, when both barriers fall in the same bar.

**(b) The documented 22:00Z session anchor is actually 10:00Z.** `CAST((ts_ms/1000 − 22*3600)/86400
AS INT)` — **DuckDB `CAST` rounds**, so the boundary sits at 22:00 + 12h = **10:00Z**. Verified:
09:00Z → 20710, 11:00Z → 20711. The CVD "session cumulative", whose whole claim is that it replicates
`web.cvd_meter`'s 22:00Z anchor, is anchored half a day off the dashboard the operator reads. The same
rounding in `CAST(ts_ms/60000 AS INT)` shifts tick→bar attribution ~30s late (stale, not a
look-ahead). Fix: `//`.

> The brief warned that DuckDB `/` is float and sqlite `/` is integer. **Both are true and both were
> handled; the trap that actually fired was `CAST`.** `CAST(161/60 AS INT)` is **3**, not 2.

**(c) One matched random control is not a control.** The identical rule on the identical 168 fires
scored **+9.9pp** against one control draw and **+7.4pp** against another. Across 50 draws the
control rate has an SD of **±2.7 to ±5.5pp** depending on cell — *comparable to every edge in this
study*, and the difference between a CI that excludes zero and one that does not. `entry_signals.py`
and `entry_cvd_climax.py` both draw **once**. Every number in this report averages **50 draws**, and
the other arms' single-draw edges should be re-run the same way before they are ranked against each
other.

---

## 5. WHAT I WOULD DO NEXT, cheapest first

1. **Shadow `vacuum_side_p1_2.0atr_with` and `absorption_v75_r75_s75_withdeep` together.** Different
   failure modes, both ~4.2-4.7 fires/session, both read-only to build. Pre-register before the first
   fire: 2.0 ATR, p1, 30-min cooldown, 180-min window, **frozen**, verdict at 200 fires on
   day-clustered CIs against both the random control *and* extension-only. The in-sample window
   2026-07-16..10-02 is where these were found and **its numbers are not a result.**
2. **Re-run arms 1, 2 and 4 with (a), (b) and (c) fixed** before any cross-arm ranking. The
   `1day`-bar contamination and the one-draw control can each move an edge by more than the
   differences the ranking would turn on.
3. **Do not re-ask the book which way price will go.** Three independent attempts now — the 2026-08
   five-sample L2 direction probe that flipped sign, the 2026-09-04 break study (34 features, nothing
   clearing a family-wise gate on 210 pooled breaks), and `climax_imb_c10` here at −2.1pp. The book
   answers *liquidity* questions, which is exactly why the side-specific vacuum is the one thing that
   worked and `levelbreak.py`'s gold hole-break is the desk's only shipped book gate.
4. **Leave the 0.24-ATR ceiling alone unless the entitlement changes.** No study design recovers a
   wall one ATR away from a 10-tick book.

---

### Artifacts

Working files (scratchpad, not committed): `build_feat.py` (per-minute feature cache),
`arm3.py` (rules, gauge, day-clustered bootstrap), `calib.py` (outcome-blind fire-rate grid),
`arm3_final.py` (scored pass + lifetime), `arm3_robust.py` (incumbent, hold-out, placebo),
`arm3_rank.py` (50-draw control ranking), and the matching `.json` results.

Reused, not rebuilt: `entry_cvd_climax.race/gauge/triggers`, `entry_signals._atr` (pattern),
`book_features.clean_mask` (ported to SQL), `gazbot7.lake.connect`.
