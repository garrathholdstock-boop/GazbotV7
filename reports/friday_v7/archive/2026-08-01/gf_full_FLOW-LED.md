# Greenfield Hunt — FLOW-LED cluster (census level: **full**, all 53 sat-out runs)

Week Mon 2026-07-27 → Fri 2026-07-31 · census `census_summary.json` (73 runs, 53 sat out,
$14,519 hindsight ceiling) · tape used: **8.0 days of MNQ 250ms ticks + 5s bars**
(2026-07-23 22:00 → 2026-07-31 21:00 UTC, 99,245 bars / 10,080,956 ticks, `capture.db`).
*(Last week's version of this section archived at `gf_full_FLOW-LED.prev-0724.md` — it reached
the same verdict by a different route, which is itself a data point.)*

> **VERDICT: NO SURVIVOR. Nine graves.** The best thing I could build (FLOWTRAP, +$1,460
> net, PF 1.50, 48 % win) does **not** beat its own placebo: circularly shifting the flow
> series while keeping every other rule produces a null distribution the real result sits
> inside (p = 0.075 / 0.145 / 0.105). And the cluster it was hunting is itself a labelling
> artifact — see Grave 0, which is the real finding of this section.

---

## 0. First, the census's own label does not survive contact with the tape

Before inventing anything I profiled the 5s bar at each run's *start* against the
background distribution of all 99,245 bars.

`run_census.py` tags a run **FLOW-LED** when the 60s of net aggressor flow *before* the move
exceeds ±50 contracts and is *aligned* with the move (outside 13–15 UTC). Three facts kill it:

| Test | Result |
|---|---|
| Base rate of the trigger | **P(\|cvd_60s\| > 50) = 66.5 % of all bars.** Two thirds of random moments qualify as a "flow event". Background IQR of cvd_60s is −86…+82. |
| Aligned vs opposed | Of the runs with \|flow\|>50 outside the open window: **21 aligned (FLOW-LED) vs 17 opposed (VACUUM)**. One-tailed binomial **p = 0.314**. A coin flip. |
| Flow at the 16 FLOW-LED sat-out run starts | median aligned flow z = **−0.089** (only **44 %** positive); median volume surge vz = **0.71** — *below* the tape median of 0.95. The runs did **not** start on a flow burst. |

And the brief's hypothesis that narrowing to the biggest runs reveals a stronger footprint is
**falsified — it inverts**:

| Run set (sat out) | n | median aligned flow-z | mean | frac > 0 |
|---|---|---|---|---|
| ALL sat-out | 53 | +0.116 | +0.025 | 57 % |
| top25 | 25 | +0.038 | **−0.189** | 52 % |
| top15 | 15 | +0.100 | **−0.090** | 60 % |
| FLOW-LED sat-out | 16 | **−0.089** | **−0.194** | 44 % |

`corr(|move|, aligned pre-run flow-z)` over the 53 sat-out runs = **−0.209** — **the bigger
the run, the *less* aligned the flow that preceded it.** The top of the census is emptier of
this footprint than the marginal runs, not richer. Hunting harder at the top made it worse.

**Grave 0 — "FLOW-LED" is not a cluster.** It is a 66 %-base-rate flow filter × a 50/50
direction coin. Any signal built to its literal definition is being fitted to noise.

---

## 1. What the tape actually says about aggressor flow

Two-dimensional scan, 10-min price change (mvz) × 10-min signed-aggressor z (cvdz), value =
mean forward 15-min move in points, demeaned (n = 97,506 bars; **n_eff ≈ 541** independent
15-min windows — every number below carries that penalty):

```
ALL TAPE                              US SESSION 13:30–21:00 UTC
cq     fl--   fl-   fl0   fl+  fl++   cq     fl--    fl-    fl0    fl+    fl++
mv--  -8.01 -2.56 -1.90 -5.42 -37.59  mv-- -14.35  -6.26 -14.47 -34.93 -113.25
mv-   -0.02  5.32 -2.67 -1.14  -5.84  mv-    2.83  13.13  -3.27  -2.03  -30.16
mv0    2.95  6.79  6.26 -0.29  -5.01  mv0    5.68  14.25  15.60   1.37  -15.41
mv+    3.66  6.23  8.53  1.19  -0.82  mv+   -6.93   9.64  14.91   4.11   -4.84
mv++  10.71  2.14  1.76  4.01   0.40  mv++  -0.70  -9.31   7.75   8.30   -3.68
```

The signal is **not** where the census looked. Flow *aligned* with the move (the diagonal
`mv--/fl--`, `mv++/fl++`) predicts ~nothing. Flow *opposed* to the move — the off-diagonal
corner `mv--/fl++` (price collapsing while aggressors keep **buying**) — predicts −37.6 pt of
further downside all-tape, **−113 pt in the US session**. Ranked by counter-alignment:

```
aligned-flow sextile (0 = most COUNTER-aligned):   0      1      2     3     4     5
mean continuation of the prior 10-min move (pt): +10.55  +4.76  +0.01 +0.81 +0.32 +2.52
   ... within the strongest-prior-move quartile: +37.29  +4.69  -0.55 +3.40 +7.27 +4.98
```

Mechanism read: **trapped counter-aggressors are fuel; confirmed flow is already priced.**
That is a real, mechanism-clean hypothesis and the exact opposite of the cluster's name. So I
built it and tried to kill it.

---

## 2. The invented signal — **FLOWTRAP** (exact mechanical spec)

Evaluated on every closed 5s bar `t`; one slot; no pyramiding.

```
STATE (all trailing, no look-ahead — every window ends at bar t)
  mv10   = close[t] − close[t−120]                     # 10-min price change, points
  cvd10  = Σ signed aggressor size over the same 120 bars (buy +size, sell −size)
  mvz    = (mv10  − mean(mv10, 1440)) / std(mv10, 1440)     # 1440 bars = trailing 2 h
  cvdz   = (cvd10 − mean(cvd10,1440)) / std(cvd10,1440)
  r15    = max(high,180) − min(low,180)                # 15-min range = the vol unit
  er15   = |close[t]−close[t−180]| / Σ|Δclose| over 180 bars

TRIGGER  (Zm = 1.25, Zf = 1.00)
  SHORT  when  mvz ≤ −Zm   AND   cvdz ≥ +Zf     # price fell hard while they kept BUYING
  LONG   when  mvz ≥ +Zm   AND   cvdz ≤ −Zf     # price rose hard while they kept SELLING
REGIME GATE   r15 ≥ 70 pt (expanded-vol only)  — see §4, mandatory
ENTRY    market on the first tick at/after t+5s, filled 1 tick (0.25 pt) ADVERSE
STOP     0.45 × r15 from fill (floor 5 pt); filled 1 tick ADVERSE on touch
TARGET   2.0 R (= 0.90 × r15), limit, filled at price
TIME-EXIT 1200 s, market, 1 tick adverse
COOLDOWN no new entry until the prior trade has exited (single slot, ≥600 s)
COSTS    $5.00 round-trip, MNQ $2/pt
```

Exits are repriced on the **250ms tick stream**, stop-vs-target resolved by whichever tick
came first (no bar-close cheating; memory `[[sims-on-tick-price]]`).

---

## 3. Headline backtest (tick-honest, net of $5/RT)

| Config | n | net $ | win % | avg $/tr | PF |
|---|---|---|---|---|---|
| BASE, all tape, both sides | 79 | **+1,460** | 48.1 | +18.48 | 1.50 |
| HOME (r15 ≥ 70), both sides | 52 | **+1,632** | 51.9 | +31.38 | 1.76 |
| EXPVOL-US (r15 ≥ 70, 13–20 UTC) | 21 | **+1,391** | 57.1 | +66.23 | 2.58 |

Looks like a winner. It is not. §5 is why.

**Mechanism controls** (same machinery, one ingredient removed — these are graves in their own
right, and they are what makes FLOWTRAP *look* real):

| Control | n | net $ | win % | PF |
|---|---|---|---|---|
| **A** — aligned-flow momentum (*the census's literal FLOW-LED read: go WITH the leading flow*) | 171 | **+74** | 42.7 | **1.01** |
| **B** — flow-only, no price condition, go WITH flow | 301 | **−2,179** | 35.9 | 0.82 |
| **C** — price-momentum only, flow condition deleted | 280 | **−889** | 40.0 | 0.92 |

Control C → BASE is a +$2,349 swing produced purely by adding the contra-flow condition, and
the `Zf = 0` column of the sweep is negative at **every** Zm (−33 … −1,060). So the ingredient
is doing work. It just isn't doing *enough* work to clear its own null (§5g).

---

## 4. Regime segmentation — per-segment n / net / win% / $-per-trade

Terciles on the tape: r15 (vol) 48.2 / 74.2 pt; er15 0.042 / 0.095. **No blanket number is
reported anywhere in this section without its regime split** (operator, 2026-07-31).

| Time-of-day | Segment | n | net $ | win % | $/trade |
|---|---|---|---|---|---|
| US | expvol/hiER | 7 | +543 | 57 | +77.6 |
| US | expvol/lowER | 6 | +461 | 50 | +76.8 |
| US | expvol/midER | 5 | +306 | 60 | +61.1 |
| US | midvol (all ER) | 3 | −76 | 33 | −25.3 |
| ONITE | expvol/hiER | 13 | +664 | 69 | +51.0 |
| ONITE | expvol/lowER | 2 | −203 | 0 | −101.2 |
| ONITE | expvol/midER | 5 | +150 | 60 | +30.0 |
| ONITE | midvol/lowER | 8 | −214 | 25 | −26.7 |
| ONITE | midvol/midER | 5 | −289 | 0 | −57.8 |
| ONITE | deadvol (all ER) | 16 | +14 | 50 | +0.9 |

**Vol-floor sweep (the one genuinely robust structure found):**

```
r15 ≥   0: n=79 net=+1460 $18/tr  |  r15 ≥ 70: n=52 net=+1632 $31/tr  |  r15 ≥ 90: n=36 net=+2007 $56/tr
r15 ≥  50: n=68 net=+1309 $19/tr  |  r15 ≥ 80: n=45 net=+1616 $36/tr  |  r15 ≥110: n=28 net=+1339 $48/tr
```

Monotone plateau — every step of the floor raises $/trade while n decays gracefully. This is
the honest half of the finding, and it re-confirms `[[low-vol-grind-untradeable]]`:
**compressed vol is untradeable for this mechanism.**

**Per-regime R sweep — proving the Rs instead of taking the operator's cheat-sheet on faith**
(cell = n / net $):

```
EXPVOL-US            R1.0        R1.5        R2.0        R3.0        R4.0
  stop 0.30×r15   24/  494    24/ 1152    23/  832    21/ 1328    21/ 1575
  stop 0.45×r15   24/ 1208    23/ 1392    21/ 1391    21/ 1754    20/ 1669
  stop 0.60×r15   23/ 1520    21/ 1655    21/ 1910    20/ 1810    20/ 1882     ← all 15 cells green
EXPVOL-ONITE
  stop 0.30×r15   33/  -54    32/  179    32/  274    31/  356    31/  184
  stop 0.45×r15   32/   51    31/   78    31/  205    31/  -24    31/  -24
  stop 0.60×r15   32/  445    31/  462    31/  290    31/  233    31/  233     ← coin flip
LOWVOL-ALL (r15 < 70)
  stop 0.30×r15   43/ -477    43/ -410    43/ -225    41/ -392    41/ -436
  stop 0.45×r15   41/ -382    41/ -357    39/ -493    38/ -425    38/ -383
  stop 0.60×r15   41/   18    39/ -323    39/ -354    38/ -139    38/ -127     ← consistently red
```

**PROVEN vs GUESS.** The operator's momentum prior (Lot-A 1.5R / Lot-B 2.5R) is *not*
contradicted — but neither is anything else: inside EXPVOL-US the surface is a **flat plateau
from R1.5 to R4.0** (+1,655 / +1,910 / +1,810 / +1,882 at stop 0.60). **R is not the lever
here; direction is.** Widening the stop 0.30 → 0.60 × r15 helps at every R, and the time-exit
sweep is monotone in *holding longer* (300s +422 → 900s +1,381 → 1200s +1,487 → 2700s +1,664).
Straight confirmation of `[[exit-architecture-scar-tissue]]`: on a good entry the exit barely
matters — so a flat, healthy exit surface is **not** evidence that the entry is good.

---

## 5. Robustness — where FLOWTRAP dies

**(a) Parameter sweep — is it an n-collapse?** Partly no, partly yes. Zm × Zf (all tape,
both sides, cell = n / net$ / $per-trade):

```
Zm\Zf       0.0            0.5           0.75           1.0            1.25           1.5
1.00   276/ -631/ -2  181/  397/  2  143/ 1489/ 10  110/ 1758/ 16   93/ 1607/ 17   69/ 1290/ 19
1.25   215/-1060/ -5  141/ 1370/ 10  118/ 1040/  9   86/ 1704/ 20   74/ 1683/ 23   56/ 1422/ 25
1.50   162/ -734/ -5  111/ 1144/ 10   91/  758/  8   68/ 1487/ 22   55/ 1154/ 21   48/ 1172/ 24
1.75   126/ -442/ -4   83/  442/  5   65/  548/  8   52/  964/ 19   43/  863/ 20   34/  996/ 29
2.00    82/  -33/ -0   62/  123/  2   52/  357/  7   42/  912/ 22   30/ 1022/ 34   25/  983/ 39
2.50    41/  970/ 24   31/  750/ 24   26/ 1020/ 39   23/ 1154/ 50   18/  838/ 47   13/  778/ 60
```

Genuine plateau at Zf ≥ 0.75 (all green) with a clean sign-flip at Zf = 0 (all red). But
$/trade climbs monotonically as n collapses (+10 at n=143 → +60 at n=13) — the classic tell
that the "quality" is thinning sample, not sharper selection.

**Lookback window is a step, not a plateau** — a real curve-fit warning:
`W = 3 min → −$236 · 5 min → −$106 · **10 min → +$1,487** · 15 min → +$1,325 · 20 min → +$815`.
Two adjacent settings are *negative*.

**(b) Strip the best trades — fatal.**

| | BASE (all tape) | HOME (r15≥70) | EXPVOL-US |
|---|---|---|---|
| as-is | +1,460 (PF 1.50) | +1,632 (PF 1.76) | +1,391 (PF 2.58) |
| strip top-1 | +1,088 | +1,260 | +1,019 |
| strip top-2 | +716 | +888 | +647 |
| **strip top-3** | **+385** (PF 1.13) | **+557** (PF 1.26) | **+317** (PF 1.36) |
| strip top-5 | **−150** (PF 0.95) | +22 (PF 1.01) | — |

Top 8 winners: 372, 372, 331, 268, 268, 228, 175, 167. Worst 5: −120…−159. **Five trades out
of 79 are the entire edge.** It clears strip-3 by $5.06/trade — one dollar above the
commission — and dies at strip-5.

**(c) Leave-one-day-out — the one clean pass.** Every day removable, all remain green:
`drop 07-24 +1529 · 07-27 +1263 · 07-28 +881 · 07-29 +922 · 07-30 +1673 · 07-31 +1030`.
Per-day: −69 / +197 / +578 / +538 / −214 / +429 (4 green, 2 red). **Not** a one-day artifact.

**(d) OOS split — passes.** IS (07-24, 27, 28) n=41 +$706 PF 1.51 · OOS (07-29, 30, 31)
n=38 +$754 PF 1.50. Stable across the split.

**(e) Long/short symmetry — broken, and it *sign-flips by session*:**

| | n | net $ | win % | $/trade |
|---|---|---|---|---|
| US · SHORT | 12 | **+1,434** | 62 | +99.8 |
| US · LONG | 9 | **−0.3** | 44 | −0.0 |
| ONITE · LONG | 34 | **+346** | 47 | +10.2 |
| ONITE · SHORT | 23 | **−184** | 43 | −8.0 |

Four sub-populations of n = 9–34 with two opposite signs. That is not one policy, it is four
fitted policies. Violates `[[gates-two-sided-per-side-tuning]]` in the worst way: the sides
don't just need different tuning, they need opposite *signs* by session. **Not carryable.**

**(f) Is the short-side edge just drift?** No — this is the one accusation FLOWTRAP beats,
and I report it because I expected the opposite. The tape fell 414 pt over 8 days =
−0.0006 pt/s = **$1.40 of free carry per 20-min short**. Drift-neutral alpha: BASE +$1,471
(vs +$1,460 raw), HOME +$1,637, EXPVOL-US +$1,389. The short-side dominance is **not** passive
short carry; it is that this week's *down* moves were bigger and faster than its up moves —
a regime property, not an edge property, and equally unrepeatable.

**(g) PLACEBO / PERMUTATION TEST — the execution.** 200 draws each: circularly shift the
signed-flow series by a random offset (2,000 … n−2,000 bars), keeping the price trigger, the
vol gate, the stops, the targets, the tick engine and the costs identical. This asks the only
question that matters: *does the real flow beat an arbitrary flow filter?*

| Config | real net | null mean | null sd | null 95th pct | **p(null ≥ real)** |
|---|---|---|---|---|---|
| BASE all-tape | +1,460 | +234 | 886 | +1,723 | **0.075** |
| HOME r15 ≥ 70 | +1,632 | +592 | 929 | +2,044 | **0.145** |
| EXPVOL-US | +1,391 | +598 | 712 | +1,738 | **0.105** |

The real result is **+0.9 to +1.4 sd** above a randomly time-shifted flow series and sits
*below* the null's own 95th percentile in all three configs. Note what the null itself says:
a *fake* flow filter on the same price trigger already books ~+$600 on this tape. Combined with
n_eff ≈ 541 and 79 trades, **FLOWTRAP is not distinguishable from luck.** Buried.

**(h) Big-moves-caught — it does not even do the job it was hired for.**

| Signal | vs 16 FLOW-LED sat-out runs | vs all 53 sat-out runs | $ of the $14,519 ceiling |
|---|---|---|---|
| BASE (all tape) | **3 / 16** (19 %) | 11 / 53 | $1,401 |
| HOME (r15 ≥ 70) | **4 / 16** (25 %) | 11 / 53 | $1,309 |

Caught: 07-29 06:22 (+138 → +$148), 07-29 18:34 (+298 → +$268), 07-29 19:32 (−248 → +$372),
07-30 00:29 (−98 → −$12). Missed 12/16, including the entire 07-31 15:14 → 16:17 sequence and
07-29 19:49 (−276), the second-biggest run of the week. **9 % of the ceiling.**

---

## 6. THE GRAVES (every one, as the operator asked)

| # | Signal | n | net $ | win % | PF | Cause of death |
|---|---|---|---|---|---|---|
| **0** | **The FLOW-LED cluster label itself** | 21 runs | — | — | — | 66.5 % base rate × 50/50 direction; 21 aligned vs 17 opposed, binomial **p = 0.314**. Not a cluster. |
| **1** | **FLOWTRAP** (trapped counter-aggressors) — best of the hunt | 79 | +1,460 | 48.1 | 1.50 | **Fails its own placebo (p = 0.075 / 0.145 / 0.105).** Strip-5 → −$150. Long/short sign-flips by session across n = 9–34 buckets. Catches 4/16 of its target runs. |
| **2** | Aligned-flow momentum — *the census's literal FLOW-LED read* | 171 | +74 | 42.7 | **1.01** | Dead coin-flip; longs −$799 / shorts +$873 cancel out. The cluster's own definition is untradeable. |
| **3** | Flow-only continuation (CVD z, no price condition, go WITH flow) | 301 | **−2,179** | 35.9 | 0.82 | Buying every aggression burst is a fee machine — flow is not information at 10-min scale. |
| **4** | Price-momentum only (flow condition deleted) | 280 | **−889** | 40.0 | 0.92 | Naked 10-min momentum-continuation bleeds; chasing with no trap condition. |
| **5** | Contra-flow fade **at a 30-min extreme** | 79 | **−973** | 44.3 | 0.73 | The long leg (−$1,231) catches every falling knife; the extreme filter selects exactly the moves that keep going. |
| **6** | Contra-flow fade, no price condition (Zf 1.5) | 215 | +1,845 | 46.0 | 1.25 | **One day.** 07-29 alone = +$1,483; the other six days sum to +$362 on ~180 trades. Longs −$369. Single-flush artifact. |
| **7** | Breakout **with** flow confirmation at a 30-min extreme | 125 / 79 | +405 / +374 | 41 / 39 | 1.08 / 1.11 | Inside cost noise — $3–5/trade against a $5 round-trip. |
| **8** | Low-vol variants of everything (r15 < 70) | 38–43 | **−477 … +18** | — | < 1.0 | Red in **all 15** stop × R cells. Compressed vol is structurally untradeable for this mechanism. |

---

## 7. What I would carry forward (the residue that *is* real)

1. **Fix the census, not the desk.** The `|flow| > 50 aligned` rule fires on 66.5 % of bars.
   It should be a **z-score against trailing 2 h** with a real threshold (|cvdz| ≥ 1); otherwise
   FLOW-LED / VACUUM are two names for one coin. As written, next Friday's FLOW-LED cluster will
   again be ~half the non-open runs by construction, and next week's greenfield agent will dig
   this same empty hole. **One-line fix in `scripts/run_census.py:cluster()`.**
2. **Counter-alignment > alignment.** The strongest tape-wide relationship found all night is
   that flow *opposed* to a strong move predicts continuation (+37 pt in the strong-move
   quartile; −113 pt in the US-session `mv--/fl++` corner) while flow *aligned* predicts ~0.
   Not significant on 8 days — but it is the right *shape* to re-test at n_eff ≈ 2,000
   (6+ weeks of tick tape). **Re-run this exact permutation test then; do not ship before.**
3. **The vol floor is the reusable part.** r15 ≥ 70 pt lifts $/trade from +18 → +31 on the same
   mechanism, monotonically, and r15 < 70 is red across all 15 stop × R cells. Mechanism-
   independent, and it matches `[[low-vol-grind-untradeable]]` and the live ATR gates.
4. **Do not touch exits for this.** R is a flat plateau from 1.5 to 4.0 inside the home segment.
   Any Lot-A/Lot-B tuning here would be fitting noise.

**Nothing from this cluster is promotable, not even to shadow.** Recommend the FLOW-LED
greenfield lane be closed until (a) the census's flow rule is z-scored and (b) there are
≥ 6 weeks of tick tape to give the counter-alignment hypothesis a real n.

---

*Method notes: no look-ahead (every rolling window ends at the signal bar; entry is the first
tick ≥ bar-close + 5s); 1-tick adverse slippage on entry, stop and time-exit; $5/RT; single
slot. Census **not** re-run — read frozen from `census_summary.json` + `census_stdout.txt`.
Working files: `/tmp/claude-0/-root/7ee8ed49-da74-4888-8564-7a26b4598a97/scratchpad/gf_flowled/`
(`engine.py` tick-honest sim · `feat.py` · `scan.py` / `scan2.py` footprint scans · `sweep1.py` ·
`robust.py` · `policy.py` · `perm.py` placebo · `alt.py` alternate forms · `drift.py`).*
