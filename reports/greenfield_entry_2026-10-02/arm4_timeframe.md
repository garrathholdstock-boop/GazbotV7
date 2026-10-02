# ARM 4 of 4 — THE LEG AT A COARSER SCALE

**MNQ · 273 session-days · 2025-09-14 → 2026-10-01 · read-only · 2026-10-02**

> **THE HYPOTHESIS, AS BRIEFED.** Every signal tested so far was computed on ONE-MINUTE bars, and on
> that scale a 298pt / 266min leg is buried in noise — net-direction flips fire 42-87 times a
> session. Resample to 5m / 15m / 30m / 60m and the same rule should become statistically obvious.
>
> **THE ANSWER. The family-level hypothesis is CONFIRMED on fire rate and REFUTED on direction —
> but three specific configurations survive every robustness test I can build, and one of them is
> the operator's own feature ①.** Coarsening does exactly what was predicted for counting
> (net-direction flips go 49.82/session → **4.51**). It does not lift the family: across **476
> scored race cells**, the 322 surface cells with n≥50 have mean edge **−0.72pp** and a
> z-distribution of mean −0.193 / sd 0.946 against H₀'s 0 / 1.00. **That is the verdict on the
> FAMILY.** Three individual rules nonetheless clear a clustered CI, both date halves, both tape
> sources, a time-of-day-matched control and a window-phase scan — led by **`stall_15m_180min`,
> 3.05 fires/session, SKILL +8.6pp at ±150** (§6 #1). None is PROVEN; all three are PROMISING and
> belong in shadow.
>
> **THE OPERATOR'S "TURNS ARE QUIET" CORRECTION is threshold-dependent** (§4.2): at ≥1.5×ATR15 in
> 30 minutes **64-74% are VIOLENT**; at ≥2.0×ATR15 **47-58% are QUIET**. Unambiguous either way —
> the median turn is 1×ATR15 away after **6-8 minutes**.
>
> **AND THE FINDING THAT SHOULD REDIRECT EFFORT: the fault is CONFIRMATION LAG, not
> magnitude-versus-quiet.** The shipped magnitude detector sees 7.3% of real turns within an hour
> and is a median **114 minutes** late; **every** detector here, at every timeframe, under both turn
> definitions, lands near a real turn **less often than a rate-matched random detector** — because
> coarsening buys confidence with the part of the move worth having. §5.

---

## 0. THE SEVEN MID-FLIGHT CORRECTIONS — WHAT EACH DID TO THIS ARM

| correction | status here |
|---|---|
| **① Weight toward QUIET-TURN features** (stall-in-time, zero-crossing slope with no magnitude floor, low-ER continuation, structure without thrust) | **Applied as the arm's primary families** — §3.4. All four implemented, 212 configs screened. **Feature ① (time-stall) ends up the #1 candidate** and feature ④ (structure without thrust) the #3; features ② and ③ are refuted |
| **② Use a SIDE-MATCHED control, not random-side** | **Already applied — found independently before any result was read**, §1.3 |
| **③ "Random-side is inflated by upward drift" — withdrawn; random-side is pinned to ~50% by construction** | **Agreed, and independently PROVEN here on 40,000 random minutes** (mean over sides = 50.0% to one decimal at all four targets, §1.3). **Both numbers are now reported for every rule: TRADEABLE (rule − 50) and SKILL (rule − side-matched control).** ⚠ They differ by only 0.3-0.9pp in this arm because every shortlisted rule is **49.3-51.3% long** — the EMA/net-direction tilt the correction warns about does not appear once the rules are flip-only. ⚠⚠ **And the drift inference is still backwards for this tape:** it rose +6,696.8pt **and** SHORT wins the race 57.2% to 42.8% at ±200pt, because a race rewards the faster tail, not the sum (§1.3) |
| **④ `bars` mixes timeframes for the same minute** | **Already applied, and taken further** — one dominant timeframe per session **and** every coarse (left-edge-labelled) timeframe excluded outright. §1.1. This arm is credited in the fixed loader as the one that did not import the bug |
| **⑤ `race()` tested `fav` before `adv` — ambiguous bars scored as wins** | **Adopted and re-run. Measured effect: 294 ambiguous races out of ~441,000 = 0.07%**, all at ±50 (16 at ±100, zero at ±150/±200). Every headline moved by ≤0.2pp. §1.6 — the bug was severe in the shared loader because *its* bars were contaminated by `1day` rows with a 310pt median range; on clean minute bars there is almost nothing to resolve |
| **⑥ ≥20 control draws — one draw is not a control** | **Already exceeded, and now reported.** The control is session- **and** side-matched from 400 draws per session per side; re-run as **20 independent draws**, whose own mean has a draw-SD of **0.08-0.28pp** (§6), two orders below the effects discussed |
| **⑦ ★★★ RUN A WINDOW-SHIFT SCAN on any rule ≤6 fires/session** | **Run — and it changed the ranking.** For a resampling arm the analogue is the **bucket-grid PHASE**, which is wholly arbitrary (§3.7). It **killed `structboth_5m_p4`** (+9.7pp at ±200 → phase-mean +3.4pp, sd 7.2, only 60% of phases positive) and **killed `netdir_60m_180min`'s ±100 cell** (+3.9 → +1.0, 60% positive), and it **held `stall_15m_180min`** (±150 phase-mean +7.2pp, 100% of 15 phases positive). ⚠ **With an honest limitation I measured: a phase shift changes these rules' fire counts by only 1-6%, so it is a SENSITIVITY check that rules OUT a boundary artefact — it does not rule one IN** |
| **⑧ THE CEILING: the operator's own 187 presses score +0.2pp (±50) / −2.1pp (±100) side-matched** | **Adopted as the reference line and it reframes the shortlist** — §6.0. Every candidate's ±50 cell is now read against **+0.2pp**, and the large ±150/±200 figures are explicitly labelled as resting on **8-24% subsets** of each rule's own fires |

---

## 1. METHOD, AND THE FOUR TRAPS THAT CHANGED THE NUMBERS

### 1.1 The tape, and why it is 273 sessions

`gazbot7.lake.connect()`. The `bars` table holds eight timeframes for MNQ; only `5s`, `1min` and `1m`
are used. **The others are excluded because they are LEFT-EDGE LABELLED** — a `1hour` bar stamped
14:00 carries the high and low of 14:00-15:00, and `1day` has a median range of 310.8pt — so folding
one into a per-minute aggregate imports a future extreme into the minute being decided on, and the
race then resolves off a price that never printed. One source timeframe **per session**, priority
`5s` > `1min` > `1m`. **No volume column is read anywhere in this arm**, so the `SUM(volume)`
double-count cannot reach these results.

| | |
|---|---|
| sessions with ≥300 one-minute bars | **273** |
| source | **197** sessions IBKR `1min` backfill · **76** sessions our own `5s` capture |
| minutes/session | min 646 · median **1380** (full 23h ETH session, 22:00Z anchor) · max 1380 |
| span | 2025-09-14 → 2026-10-01 |
| closed bars/session | 5m **271.7** · 15m **89.9** · 30m **44.5** · 60m **21.7** |

**Six counting definitions, all 273:** ≥300 distinct minutes fine-only · the same all-timeframe ·
≥300 **rows** rather than minutes · calendar-day instead of 22:00Z sessions · ≥300 rows within the
best single (session, timeframe) pair · MNQ **and** MGC together. The per-expiry MNQ backfill
outside the lake glob adds nothing (5 files, 2025-09-14 → 2026-09-18, 263 qualifying sessions — the
same tape). **273 is the ceiling for minute-resolution MNQ tape on this box, and the 328 figure is
not reproducible here.**

The brief's "616 session-days / 1.64M rows" is the union over *all* timeframes: 483 of those days
exist only as `1day` bars and 476 only as `1hour`. Neither can carry a minute-resolution race.

**Source is not driving any result** — every shortlisted config was re-scored on the 197 backfill and
76 own-capture sessions separately; signs agree in 17 of 20 cells and no conclusion flips (§6.5).

### 1.2 The left-edge look-ahead, handled three ways

1. Buckets are **absolute** (`epoch_minute // K`) — a missing minute cannot shift the grid.
2. Every K-bar is keyed by the **index of its final minute**, not its first.
3. **The last bucket of every session is dropped** — it has not been proven closed, and a rule that
   reads a still-forming bar reads the future.

The race starts at `last_minute_index + 1`. Swing pivots carry the same discipline: a pivot at bar
*j* needs *p* bars either side, so it is **confirmed at bar j+p** and entry is at `close[j+p]` —
reading the pivot as it forms is the error that once produced 866 winners from 866 trades.

`DuckDB /` was tested rather than assumed: `(7/2)::BIGINT` returns **4** on this build (CAST rounds,
it does not floor), so every bucketing uses `//`. `minute` and `days` are both reserved words here.

### 1.3 THE CONTROL — both numbers, and the drift inference corrected twice

The first scoring pass used the brief's control (random minute, **random side**) and produced
controls reading **43.8%** and **46.4%** on a symmetric race, which is impossible. Diagnosed on
40,000 random minutes:

| entering at a random minute | ±50pt | ±100pt | ±150pt | ±200pt |
|---|---|---|---|---|
| **LONG** wins the race | 48.7% | 45.6% | 45.0% | **42.8%** |
| **SHORT** wins the race | 51.4% | 54.4% | 55.0% | **57.2%** |
| **mean over sides** | **50.0%** | **50.0%** | **50.0%** | **50.0%** |

**This independently confirms correction ③:** a random-side control is pinned to 50.0% by
construction, because for a fixed minute long wins iff short loses and the race resolves at the same
instant for both sides. The 43.8% readings were the SE of a 5-draw control, not drift.

> ### ⚠ BUT THE DRIFT INFERENCE IS STILL BACKWARDS FOR THIS TAPE, AND IT IS WORTH ONE MEASUREMENT
> The reasoning offered twice was *"the tape rose, so a long-biased rule scores above 50."* The
> premise is right; the conclusion is not. Measured here: the tape **rose +6,696.8pt** (24,352.2 →
> 31,049.0; 54.6% of sessions closed up) **and a long-biased rule scores BELOW 50** — long wins only
> 42.8% at ±200pt. **Net drift and race asymmetry are different statistics.** A symmetric race is
> decided by which side reaches N **first**, which rewards the faster, fatter tail: 30-minute moves
> run UP median 20.0pt / p90 71.2 / p99 164.8 against DOWN median 19.8pt / **p90 73.0 / p99 178.0**.
> The tape grinds up and drops fast, so it has positive net displacement **and** a short-favouring
> race, worth up to **14.4pp** to a short-tilted rule. **The sign of this artefact cannot be inferred
> from a drift figure — it has to be measured on the actual race definition, once, and shared across
> the arms.**

**Both numbers are reported for every rule**, as instructed:

- **TRADEABLE = rule − 50.0.** Break-even is 50%. Drift you actually capture is real money.
- **SKILL = rule − session-and-side-matched control.** Does the timing add anything?
- **`ctrl_tod` = rule − time-of-day-and-side-matched control in OTHER sessions** — kept as a third
  reading because it is the one that separates a signal from a clock (§6.4).

In this arm the first two differ by only **0.3-0.9pp**, because every shortlisted rule is **49.3-51.3%
long** (§1.5). The structural long-bias the correction warns about belongs to EMA and raw
net-direction rules; the flip-only forms used here are side-balanced, and the matched control charges
them regardless.

### 1.4 Uncertainty

**Per-fire binomial SE is inflated here** — ~4.5 fires a session with overlapping 120-minute races
are not independent draws; this desk measured per-observation t on book data as ~10× too confident.
Every interval is a **block bootstrap over sessions** (the cluster is the day, 2,000 resamples), with
rule *and* matched control recomputed inside each resample.

### 1.5 Every rule's long/short split

| rule | fires/session | % long |
|---|---|---|
| `donch_5m_180min` | 3.80 | 51.3% |
| `netdir_60m_180min` | 4.51 | 49.3% |
| `structboth_5m_p4` | 4.59 | 51.2% |
| `struct_15m_p3` | 4.35 | 51.0% |
| `struct_30m_p1` | 5.08 | 50.6% |
| `stall_15m_180min` | 3.05 | 49.7% |
| `stall_5m_180min` | 3.20 | 50.6% |
| `slope_15m_L180min_p3` | 5.09 | 49.4% |
| `stallslope_30m_90min` | 3.57 | 49.7% |

### 1.6 The ambiguity fix, measured

An OHLC bar whose high **and** low both clear the target cannot say which came first; testing `fav`
before `adv` silently scored every one as a win. Adopted (`None`, excluded) and everything re-run.
**Measured effect: 294 ambiguous races out of ~441,000 = 0.07%** — 294 at ±50, 16 at ±100, **zero at
±150 and ±200**. No headline moved by more than 0.2pp.

> That is not a contradiction of the correction, it is its corollary: the bug was catastrophic in the
> shared loader **because that loader's bars were contaminated** — a `1day` row with a 310pt range
> folded into one minute makes almost every bar ambiguous, and `fav`-first then manufactured wins
> wholesale. On clean minute bars there is almost nothing to resolve. **Two bugs that were only
> severe together**, which is why the arm that avoided the first barely felt the second.

### 1.7 The charged search

| stage | what | outcome touched? |
|---|---|---|
| eligibility screen | **212** configs, fires/session only | **no** — the brief's hard gate reads no outcome |
| ↳ eligible at 2.0-8.0/session | 116 | no |
| ↳ **selected, outcome-blind** | **28** — per (family × timeframe), the eligible parameter closest to 4.5 fires/session | no |
| main race | 28 × 4 targets | **112 cells** |
| neighbour surface | 96 × 4 targets | **384 cells** (322 with n≥50) |
| conjunctions | 8 × 4 targets | **32 cells** |
| **distinct configs raced** | **119** × 4 targets | **476 primary race cells** |
| trailing-ER terciles · date halves · source splits | 60 · 88 · 40 | 188 sub-cells |
| detection quality (2 turn definitions) | 15 rows × 5 metrics | 75 cells |
| `ctrl_tod` re-test | 4 × 4 | 16 cells |
| **window-phase scan** | 7 configs × 4 targets × 5-15 phases | **308 cells — a ROBUSTNESS scan, not a search** |
| **total outcome-touching comparisons** | | **≈ 1,060** |

> ⚠ 5,026 specs once reproduced a published t=5.83 from pure noise 13% of the time. §3.1 charges the
> 476 race cells formally rather than rhetorically. Selection into the main race was fixed **before
> any race was run**. **The 308 phase cells carry no selection** — no config was ever chosen for
> having a good phase; they are perturbations of configs already on the list, and a config is judged
> on the whole phase distribution, never its best phase.

---

## 2. THE HALF THAT WORKS — RESAMPLING FIXES THE FIRE RATE

| net-direction flip | fires/session |
|---|---|
| 5m bars, 30min lookback | **49.82** |
| 5m, 60min | 33.79 |
| 15m, 60min | 19.49 |
| 15m, 120min | 12.59 |
| 30m, 120min | 8.94 |
| 30m, 240min | **5.65** ✔ |
| 60m, 180min | **4.51** ✔ |
| 60m, 240min | 3.70 ✔ |

The same collapse happens in every family — `stall` runs 37.11/session at a 20-minute window on 15m
bars and 3.05 at 180 minutes; `donchian` 15.99 → 3.01. **116 of 212 screened configs land in the 2-8
range.** The brief's signal-to-noise claim is right about *counting*: a 266-minute object is not
legible on a 1-minute grid. It does not follow that it becomes *correct*.

---

## 3. THE FAMILY VERDICT — THE DIRECTION CALL IS A COIN

### 3.1 The noise calibration — the decisive family-level test

The full parameter surface of the four quiet families (96 configs × 4 targets) was raced, so the
question *"is there anything in this family at all"* could be asked of the **distribution** rather
than of its maximum.

| 322 cells with n ≥ 50 | observed | H₀ expects |
|---|---|---|
| mean edge | **−0.72pp** | 0 |
| median edge | −0.50pp | 0 |
| sd of edge | 3.64pp | — |
| mean z (per-fire binomial, **no** day clustering — generous to the null) | **−0.193** | 0 |
| sd of z | **0.946** | 1.00 |
| \|z\| > 1.96 | **5.3%** | 5.0% |
| z > +1.96 | **1.2%** | 2.5% |
| z < −1.96 | **4.0%** | 2.5% |

**A textbook null with a slight negative tilt.** The family yields exactly as many "significant"
cells as chance, and twice as many losing as winning. **Any surviving rule is therefore a specific
claim about a specific configuration, never evidence for its family** — and §3.2 shows why that
distinction has teeth.

### 3.2 The surface alternates sign

| `structboth` on 5m bars | fires/sess | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|
| p=3 | 6.11 | +0.6 | +0.2 | **−0.9** | **−1.0** |
| **p=4** | **4.59** | **+3.3** | **+2.8** | **+5.2** | **+9.5** |
| p=5 | 3.81 | **−2.1** | **−0.6** | **−3.3** | **−1.4** |
| p=6 | 3.21 | −1.7 | +2.3 | +3.8 | +7.4 |

| `struct` on 15m bars | fires/sess | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|
| p=2 | 6.11 | −0.5 | +0.1 | +0.5 | **−1.4** |
| **p=3** | **4.35** | **+0.5** | **+3.5** | **+4.5** | **+6.1** |
| p=4 | 3.11 | **−2.1** | **−2.2** | +0.3 | **−0.1** |
| p=5 | 2.37 | −4.4 | −1.3 | −6.0 | +0.3 |

| `stall` window on 15m bars | fires/sess | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|
| 60min | 9.84 | −1.2 | −0.9 | +0.5 | −3.1 |
| 90min | 6.45 | −0.2 | −0.4 | **−1.2** | +1.4 |
| 120min | 4.79 | −0.6 | **−5.2** | **+0.5** | +1.0 |
| **180min** | **3.05** | **+2.8** | **+2.4** | **+8.8** | **+6.1** |

**All three leaders sit on a narrow parameter ridge with flat-or-negative neighbours.** The brief's
rule binds: *under +6pp is indistinguishable unless neighbouring cells agree.* **This is the single
unresolved weakness of every rule in §6 and it is stated there, per rule, rather than buried here.**

### 3.3 Where the surface is coherently NEGATIVE — a known result, replicated

| config | fires/sess | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|
| `struct_60m_p1` | 2.10 | −2.8 (n=430) | −4.6 (n=220) | **−9.2** (n=122) | **−8.7** (n=67) |
| `structboth_60m_p1` | 1.07 | −0.0 | −3.1 | **−12.8** | **−15.8** |
| `structboth_30m_p2` | 1.34 | −5.3 | −8.0 | **−13.3** | **−14.0** |
| `slope_30m_L120min_p3` | 4.30 | −1.8 | −1.9 | −3.4 | −4.9 |

Confirming a lower high on a 60-minute chart and going short is a **losing** trade, worsening as the
target widens — [[break-then-join-direction-is-a-coin]] and *"joining a 60-min break is significantly
NEGATIVE"* reappearing in a new family at a new timeframe. **It replicates. Do not build a
join-the-new-direction entry at 30-60m scale.**

### 3.4 The operator's four quiet features

| feature | best eligible config | fires/sess | verdict |
|---|---|---|---|
| **① STALL, measured in time** (minutes since the last new extreme; no giveback required) | `stall_15m_180min` | **3.05** | **PROMISING — §6 #1.** Survives clustered CI, both halves, both sources, a time-of-day control and the phase scan. ⚠ Fails parameter-neighbour agreement (§3.2) and has below-random turn detection (§5), so **what it is capturing is not turn identification**. ⚠ Arm 2's *"bare STALL raced at 49.2%, a coin"* **replicates here at every window except 180min** — 60/90/120min are −3.1 to +1.4pp |
| **② SLOPE SIGN CHANGE** (OLS, **no magnitude floor**, held P bars) | `slope_15m_L180min_p3` | 5.09 | **REFUTED.** SKILL +1.9/+0.4/+0.0/+1.7pp; phase-stable at ±50 only and flat elsewhere; the 30m variant runs −1.8 to −4.9pp. Dropping the magnitude floor was the right instruction and changed nothing |
| **③ LOW-ER CONTINUATION** | §3.5 | — | **REFUTED — the inconsistency IS the evidence** |
| **④ STRUCTURE WITHOUT THRUST** (successive lower highs / higher lows, no size requirement per step) | `struct_15m_p3` | 4.35 | **PROMISING — §6 #3** at ±100/±150, where the phase scan holds 100% positive. The 5m variant `structboth_5m_p4` had the biggest raw edge in the study and **the phase scan killed it** |
| (conjunction) **STALL + SLOPE agreeing**, no magnitude anywhere | `stallslope_30m_90min` | 3.57 | **REFUTED.** +0.4/+2.1/+2.1/+2.5pp, all CIs spanning zero, ±200 halves +16.3 → −5.9 |

### 3.5 Feature ③, read causally — and why it fails

> The instruction was to test whether a direction change *"followed by* LOW efficiency" is more
> reliable. **Read literally that is a look-ahead** — the efficiency of the move *after* the fire is
> not knowable at the fire. Tested instead on the **trailing** ER over the 120 minutes **up to** the
> fire; the forward version is in §4.4, flagged as not implementable.

| detector | LOW-ER (grindy tape) | MID | HIGH-ER (trending) |
|---|---|---|---|
| `structboth_5m_p4` (±200) | +9.3 | +3.6 | **+15.0** ← high best |
| `struct_15m_p3` (±150) | +5.4 | **+10.1** | −0.0 ← mid best |
| `stall_15m_180min` (±150) | −1.0 | **+21.8** | +2.9 ← mid best |
| `donch_5m_180min` (±150) | −1.5 | +2.8 | **+5.7** ← high best |
| `slope_15m_L180min_p3` (±150) | **+7.4** | −8.9 | −0.1 ← low best |

**Five detectors, three different answers, one of them the middle tercile.** If a quiet trailing tape
genuinely made a turn more reliable the sign would be stable. It is not, and at n=20-108 a 20pp swing
costs nothing. **REFUTED.**

### 3.6 CONJUNCTIONS — arm 2's shape, rejected on fire rate

| conjunction | fires/sess | %lng | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|---|
| `donch_5m_180` + `netdir_60m_180`, W=60 | **2.60** ✗ | 49.4 | +2.7 (n=563) | +2.7 (n=321) | −0.4 (n=186) | −0.1 (n=105) |
| `netdir_60m_180` + `struct_30m_p1`, W=60 | **1.95** ✗ | 48.4 | +0.2 (n=397) | +4.1 (n=209) | +3.6 (n=112) | +16.0 (n=63) |
| `donch_5m_180` + `netdir_60m_180`, W=30 | **1.75** ✗ | 52.0 | +2.7 (n=386) | +2.3 (n=220) | +0.7 (n=121) | −1.4 (n=64) |
| `netdir_60m_180` + `struct_30m_p1`, W=30 | **1.30** ✗ | 47.6 | +1.3 (n=264) | +6.0 (n=138) | +4.0 (n=74) | +11.2 (n=47) |
| `donch_5m_180` + `struct_30m_p1`, W=60 | **1.30** ✗ | 52.5 | −1.8 (n=239) | +2.6 (n=131) | +0.3 (n=69) | −6.3 (n=34) |
| `donch_5m_180` + `struct_15m_p3`, W=30 | **0.74** ✗ | 46.8 | +3.1 (n=144) | +2.5 (n=78) | +9.3 (n=45) | +15.0 (n=17) |

**All eight fall BELOW the 3/session floor** (0.74-2.60) and are rejected on the brief's own gate
before accuracy is considered. The large ±150/±200 figures sit on n=17-63, and **W=30 vs W=60 of the
same pair disagree by 16pp at ±200**, which is the tell. **A conjunction halves the fire rate out of
the target zone — the structural problem with the shape in this arm, where the single features
already fire only 3-5 times a session.** Arm 2's conjunction worked from a 5.85/session climax
detector, with room to spend.

### 3.7 ★★★ THE WINDOW-PHASE SHIFT SCAN — and what it is and is not worth

A K-minute bucket grid has an arbitrary **phase**: a 15-minute bar can start at :00 or at :07.
Nothing in the market privileges one. **If an edge lives at one phase it is a boundary artefact** —
arm 1's +10.8pp [+2.5,+19.5], holdout-confirmed, threshold-robust candidate died exactly this way.

| config | target | phase 0 | across phases: mean | sd | range | % positive | verdict |
|---|---|---|---|---|---|---|---|
| `stall_15m_180min` | ±50 | +2.9 | **+2.4** | 0.8 | [+0.8, +3.6] | **100%** | **holds** |
| | ±100 | +2.5 | +0.9 | 1.3 | [−1.1, +3.3] | 80% | weak |
| | ±150 | +8.6 | **+7.2** | 2.2 | [+3.4, +10.3] | **100%** | **holds** |
| | ±200 | +6.0 | **+7.7** | 2.4 | [+4.7, +12.0] | **100%** | **holds** |
| `donch_5m_180min` | ±50 | +2.4 | **+2.1** | 1.1 | [+0.6, +3.3] | **100%** | **holds** |
| | ±100 | +1.8 | **+1.2** | 0.7 | [+0.2, +1.9] | **100%** | holds, small |
| | ±150 | +1.7 | **+1.8** | 1.2 | [+0.2, +3.6] | **100%** | holds, small |
| | ±200 | +0.3 | +1.6 | 2.1 | [−1.0, +4.5] | 80% | spans 0 |
| `struct_15m_p3` | ±50 | +0.4 | −0.7 | 0.9 | [−2.6, +0.4] | 20% | **fails** |
| | ±100 | +3.5 | **+2.3** | 1.3 | [+0.5, +5.6] | **100%** | **holds** |
| | ±150 | +4.4 | **+3.8** | 2.0 | [+0.5, +6.6] | **100%** | **holds** |
| | ±200 | +5.9 | +2.9 | 2.5 | [−1.2, +8.8] | 93% | weak |
| `structboth_5m_p4` | ±150 | +5.0 | +1.9 | 3.0 | [−1.4, +5.2] | 60% | **ARTEFACT** |
| | ±200 | **+9.7** | **+3.4** | **7.2** | [−5.2, +12.0] | 60% | **ARTEFACT** |
| `netdir_60m_180min` | ±100 | **+3.9** | **+1.0** | 2.2 | [−2.4, +4.8] | 60% | **ARTEFACT** |
| `struct_30m_p1` | ±150 | +3.7 | +2.8 | 2.7 | [−1.4, +6.8] | 80% | spans 0 |
| `slope_15m_L180min_p3` | ±100 | +0.4 | +0.3 | 1.0 | [−2.0, +1.7] | 73% | flat |

**It earned its keep immediately: it destroyed the two biggest edges in the study** —
`structboth_5m_p4`'s +9.7pp at ±200 collapses to a phase-mean of +3.4pp with an sd of 7.2 and only
3 of 5 phases positive, and `netdir_60m_180min`'s +3.9pp at ±100 — the cell whose clustered CI
excluded zero and which replicated in both date halves — collapses to +1.0pp with 60% of phases
positive. **Both were boundary artefacts, and nothing short of this scan would have caught them.**

> ⚠⚠ **AND HERE IS THE LIMITATION, MEASURED RATHER THAN ASSUMED.** A phase shift changes these
> rules' fire counts by only **1-6%** (`stall_15m_180min` 3.05 → 3.14/session across 15 phases;
> `donch_5m_180min` 3.74 → 3.89; `struct_15m_p3` 4.34 → 4.53). **The 15 phases are therefore NOT 15
> independent tests — they are one test, perturbed.** "100% of phases positive" means *the edge does
> not live on a grid boundary*; it does **not** mean the edge replicated fifteen times. For a rule
> whose window is 180 minutes a 14-minute phase shift moves <8% of the criterion, which is why the
> scan is a strong falsifier here and a weak confirmer. **It rules artefacts OUT. It cannot rule an
> edge IN.** The date split, the source split and the clustered CI remain the load-bearing tests.

---

## 4. THE OPERATOR'S QUESTION — VIOLENT OR QUIET?

> *"the turns are not violent. they often just change direction. sometimes its violent. but more
> often than not it can just start grinding in that direction."*

### 4.1 Ground truth, and its honest limits

Turns are defined two ways — a **ZigZag** on minute highs/lows at 75 / 100 / 150pt, and **arm 2's
±90min pivot with both legs ≥60pt** (§4.5). **Both are descriptive ground truth, not signals** — a
pivot is identified with hindsight by construction. Violence is measured **only from what happens
after the pivot**, normalised by ATR14 on **closed 15-minute bars as known at the pivot**, so the
yardstick carries no future.

| ZigZag | turns | per session | median ending leg | median new leg | new-leg ER |
|---|---|---|---|---|---|
| 75pt | 4,308 | 15.78 | 126.8pt / 23min | — | 0.4 |
| 100pt | 2,482 | 9.09 | 166.0pt / 41min | 163.8pt / 35min | 0.3 |
| **150pt** | **1,053** | **3.86** | **244.5pt / 89min** | **239.0pt / 75min** | **0.3** |

The 150pt threshold reproduces the brief's leg population on count (3.86 vs 3.1/session) and size
(244pt vs 298pt); duration runs shorter (89 vs 266min) because `leg_watch`'s 3×ATR retrace rule
merges across pullbacks a 150pt ZigZag splits.

### 4.2 ★ THE SPLIT — threshold-dependent, and that IS the answer

| | VIOLENT | QUIET |
|---|---|---|
| **ZigZag 150pt** (3.86/sess, median leg 244pt) | | |
| 30min ≥ 1.0×ATR15 | 92.5% | 7.5% |
| 30min ≥ **1.5×ATR15** | **73.7%** | **26.3%** |
| 30min ≥ **2.0×ATR15** | **53.2%** | **46.8%** |
| **arm 2's ±90min / 60pt pivot** (5.88/sess) | | |
| 30min ≥ 1.0×ATR15 | 88.8% | 11.2% |
| 30min ≥ **1.5×ATR15** | **64.3%** | **35.7%** |
| 30min ≥ **2.0×ATR15** | 42.1% | **57.9%** |

**There is no single number, and claiming one would be the fitted answer.** At a 1.5×ATR15 bar
(≈70-95pt in half an hour) violent wins **64-74%**; at 2.0×ATR15 (≈95-125pt) quiet wins **47-58%**.
His belief is defensible at the higher bar and wrong at the lower one.

Two things *are* unambiguous, and both cut against treating turns as slow:

| time for the new direction to travel | ZigZag 150pt | arm 2 pivot |
|---|---|---|
| 1×ATR15 (≈62pt / ≈48pt) | **6 min** | **8 min** |
| 50pt | **3 min** | **9 min** |
| 100pt | 14 min | 33 min |
| never reaches 1×ATR15 inside 180min | **0.5%** | **0.4%** |

And the quiet share **shrinks as legs get bigger**: 41.0% quiet at a 75pt ZigZag → 34.2% at 100pt →
**26.3% at 150pt**. **The quiet turns are disproportionately the small ones; the big legs he wants
are the violent ones.**

> ⚠ **CONDITIONING CAVEAT.** A 150pt ZigZag pivot is *defined* by a subsequent 150pt giveback, so
> "the new direction eventually moves 150pt" is guaranteed. **How FAST is not** — that is the
> measurement — but the population is conditioned on moves that reach 150pt. The honest statement:
> *among the moves that become real legs, the median covers 100pt in 14 minutes.* Arm 2's definition
> is conditioned differently and gives 33 minutes, so the two bracket it.

### 4.3 WHY IT FEELS QUIET ANYWAY — both halves of his description are true

The median new leg's **efficiency ratio is 0.3** at every ZigZag threshold. The shape of a real turn
is **fast off the pivot, grindy thereafter**: 100 points in 14 minutes, then another hour to deliver
the next 140 at an ER of 0.3. **What he watches — "it just starts grinding in that direction" — is
the BODY of the leg, and he is right about it. What the measurement adds is that the first fifteen
minutes are not like the rest, and that window is where the entry lives.**

### 4.4 Quiet turns lead to LONGER legs — descriptive, not implementable

ZigZag 150pt, split at 30min ≥ 1.5×ATR15 (uses the *next* pivot, so **not** implementable):

| | median new leg | duration | new-leg ER | n |
|---|---|---|---|---|
| after a **QUIET** turn | 228.5pt | **110 min** | **0.2** | 195 |
| after a **VIOLENT** turn | 242.1pt | 63 min | 0.3 | 622 |

Same size, **75% longer to deliver it, at a lower ER**. A quiet turn is a slower grind, not a smaller
one.

### 4.5 Arm 2's pivot definition, re-measured — a second discrepancy

Implemented as specified (±90-minute pivot, both legs ≥60pt) it yields **1,604 turns / 273 sessions =
5.88 per session**, against arm 2's reported **3.96**; median ATR15 at the turn 47.5pt against the
ZigZag's 61.8pt. The ratio tracks the 273-vs-328 session discrepancy, so **one shared cause is
likely** — most plausibly the session window (23h ETH here). **Worth reconciling before the arms'
per-session rates are compared.** Every §5 conclusion is reported under both definitions and holds
under both.

---

## 5. ★★★ THE REAL FAULT — CONFIRMATION LAG, NOT MAGNITUDE

### 5.1 Against ZigZag(150pt) turns — 3.86/session

Every detector scored **beside a rate-matched random detector** (same fires/session, random minute,
random side, 30 draws). The rate match matters: recall rises mechanically with fire count.

| detector | f/s | recall60 | recall120 | **prec±30** | prec±60 | med lag |
|---|---|---|---|---|---|---|
| **INCUMBENT** `retrace_15×ATR` (1m) | 2.73 | 5.2% v 5.8% | 20.5% v 11.6% | **3.1% v 9.4%** | 11.3% v 17.1% | **85m** v 60m |
| `donch_5m_180min` | 3.80 | **14.2% v 8.0%** | 31.7% v 15.6% | 8.6% v 9.3% | **18.0% v 16.9%** | 66m v 59m |
| `netdir_60m_180min` | 4.51 | **12.4% v 9.5%** | 32.2% v 18.4% | 6.7% v 9.0% | 16.6% v 17.0% | 72m v 59m |
| `struct_15m_p3` | 4.35 | 10.0% v 9.1% | 13.1% v 17.8% | 3.2% v 9.1% | 14.7% v 17.0% | **55m** v 59m |
| `struct_30m_p1` | 5.08 | 9.0% v 10.8% | 17.5% v 20.6% | 3.0% v 9.1% | 13.0% v 17.0% | 59m v 57m |
| `slope_15m_L180min_p3` | 5.09 | 7.3% v 10.6% | 32.7% v 20.3% | 5.1% v 9.1% | 11.4% v 17.1% | 90m v 58m |
| `structboth_5m_p4` | 4.59 | 6.6% v 9.8% | 24.4% v 18.6% | 6.5% v 9.2% | 10.4% v 17.3% | 84m v 57m |
| `stall_60m_30min` | 5.67 | 5.0% v 12.1% | **54.1% v 23.0%** | 5.8% v 9.3% | 11.6% v 17.3% | **87m** v 58m |
| `stall_30m_90min` | 5.41 | 4.6% v 11.6% | **48.7% v 21.9%** | 5.9% v 9.3% | 11.2% v 17.3% | **104m** v 57m |
| `stall_15m_180min` | 3.05 | 3.9% v 6.5% | 7.5% v 12.8% | 6.1% v 9.3% | 10.9% v 17.3% | 58m v 60m |

### 5.2 Against arm 2's ±90min / 60pt pivots — 5.88/session. **The conclusion holds**

| detector | f/s | recall60 | **prec±30** | prec±60 | med lag |
|---|---|---|---|---|---|
| **INCUMBENT** `retrace_15×ATR` (1m) | 2.73 | 3.2% v 6.1% | **1.9% v 13.0%** | 9.9% v 26.1% | 86m |
| `donch_5m_180min` | 3.80 | **11.9% v 8.8%** | 6.8% v 13.5% | 21.0% v 26.5% | 69m |
| `netdir_60m_180min` | 4.51 | **11.7% v 10.3%** | 8.0% v 13.3% | 21.6% v 26.6% | 73m |
| `struct_15m_p3` | 4.35 | **17.3% v 9.5%** | 3.2% v 13.0% | **29.1% v 25.8%** | **54m** |
| `stall_15m_180min` | 3.05 | 4.8% v 6.7% | 10.3% v 13.0% | 20.4% v 25.5% | 42m |

*recall60/120 = share of REAL turns the detector names on the correct side within that many minutes.
prec±30/60 = share of its own fires within that many minutes of a real turn on the correct side.
"v" = the rate-matched random detector.*

1. **NOT ONE DETECTOR BEATS RANDOM ON prec±30, under either definition.** Every one is *below* its
   rate-matched baseline (3.0-8.6% vs ~9.1-9.4%; 1.9-10.3% vs ~13.0-13.5%). Systematic, not noise:
   these rules all require confirmation, so they systematically **avoid** the window around the pivot
   and arrive at +42 to +104 minutes.
2. **HIGH recall120 IS LAG WEARING A DISGUISE.** `stall_60m_30min` "detects" 54.1% of turns against
   random's 23.0% — at a median lag of **87 minutes**, against a median leg of **89**. It names the
   turn as the leg ends; `stall_30m_90min` is worse at 104. **A high recall at a 120-minute horizon
   is a clock, not a signal.**
3. **THE SHIPPED MAGNITUDE RULE IS THE WORST THING IN BOTH TABLES.** `retrace_15×ATR` scores prec±30
   of **3.1% against random's 9.4%** and **1.9% against 13.0%** on arm 2's turns — a seventh of
   chance. Measured independently against ground truth: it fires within 60 minutes of a real turn
   **7.3%** of the time, within 120 minutes 32.3%, **never within 240 minutes on 39.6% of turns**;
   median delay when it does, **114 minutes**.

> **SO THE OPERATOR IS RIGHT ABOUT THE SYMPTOM AND WRONG ABOUT THE CAUSE, AND THE CAUSE IS WORSE.**
> Magnitude detectors do not miss turns because the turns are quiet. They miss them because **they
> are an hour and a half late** — by which time the median leg is over and the median turn is 150+
> points away. Coarsening **adds** lag, which is exactly why the 60m variants are the latest (§5.1)
> and the most negative (§3.3).
>
> **⚠⚠ AND THIS IS THE CAVEAT ON §6 #1.** `stall_15m_180min` has a positive race *and* below-random
> turn detection (recall60 3.9% v 6.5%). **Those two facts together mean it is not detecting turns.**
> Whatever it is capturing — and §6.4 rules out a time-of-day clock — has no mechanism yet, and a
> rule without a mechanism is a shadow candidate, never a live one.
>
> **The next arm should not be another detector. It should shorten the lag** — name a turn inside its
> first 15 minutes, where §4.2 says 1.59×ATR15 of the move still lies ahead and §4.3 says an hour of
> grind follows, accepting far worse precision for arriving while the move is there.
> **`struct_15m_p3` is the starting point**: shortest lag on the board (54m), best recall60 against
> arm 2's turns (17.3% v 9.5%) and the only prec±60 above random there (29.1% v 25.8%).

---

## 6. RANKED SHORTLIST — best first

### 6.0 How to read these numbers

- **TRADEABLE = rule − 50.0.** 50% is break-even.
- **SKILL = rule − session-and-side-matched control** (20 independent draws; the control's own mean
  has a draw-SD of **0.08-0.28pp**).
- **⚠ THE CEILING, per correction ⑧: the operator's own 187 presses score +0.2pp at ±50 and −2.1pp
  at ±100, side-matched. His entries are a coin.** Read every ±50 cell below against **+0.2pp**.
- **⚠⚠ THE ±150 AND ±200 CELLS REST ON SUBSETS.** A race is scored only when it resolves inside 120
  minutes, and resolution falls away fast:

| rule | fires | resolve at ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|
| `stall_15m_180min` | 833 | 70.8% | 36.3% | **16.4%** | **7.8%** |
| `donch_5m_180min` | 1,038 | 74.4% | 41.4% | 23.6% | 12.9% |
| `struct_15m_p3` | 1,188 | 68.0% | 32.0% | **16.7%** | **8.7%** |

  Resolution is side-independent (proved in §1.3), so excluding unresolved races is unbiased — but a
  **+8.6pp at ±150 describes the 16% of fires where price moved 150pt either way inside two hours**,
  and the other 84% are two hours in a trade that went nowhere. **The ±50 column is the one with
  coverage, and it is the honest tradeable spec.**

### #1 — `stall_15m_180min` · **PROMISING · the operator's own feature ①, and the arm's best survivor**

- **Rule.** 15-minute bars, absolute buckets, final bucket of the session dropped. Track the running
  extreme of the current leg on closed bars. When **12 consecutive closed bars (180 minutes) pass
  with no new extreme**, declare the leg over and enter the other way at that bar's close; reset the
  extreme. **No giveback, no points, no velocity — the only thing that happens is that nothing
  happens.**
- **3.05 fires/session · 49.7% long.**

  | | ±50pt | ±100pt | ±150pt | ±200pt |
  |---|---|---|---|---|
  | rule | 53.2% | 53.3% | 59.9% | 56.9% |
  | n (of 833 fires) | 590 | 302 | 137 | 65 |
  | **TRADEABLE** (−50) | **+3.2pp** | +3.3pp | **+9.9pp** | +6.9pp |
  | **SKILL** (side-matched) | **+2.9pp** | +2.5pp | **+8.6pp** | +6.0pp |
  | control draw-SD | 0.13 | 0.25 | 0.21 | 0.28 |
  | day-clustered CI95 | [−1.2, +7.0] | [−3.2, +7.4] | **[+0.2, +16.9]** | [−6.7, +18.2] |
  | date halves | 0.1 / 5.1 | 3.1 / 2.0 | **10.7 / 7.4** | 8.3 / 4.5 |
  | source (1min / 5s) | +1.5 / +5.8 | +0.3 / +6.9 | +6.7 / +13.4 | +7.2 / +3.3 |
  | `ctrl_tod` edge | +3.1pp | +4.2pp | +8.7pp | +6.6pp |
  | phase scan (15 phases) | mean +2.4, **100% pos** | mean +0.9, 80% | mean +7.2, **100% pos** | mean +7.7, **100% pos** |

- **What it passes.** Fire rate · a day-clustered CI excluding zero at ±150 · **positive in BOTH date
  halves at all four targets** · **positive on BOTH tape sources at all four targets** · a
  time-of-day-and-side-matched control in other sessions (§6.4) · the phase scan at 3 of 4 targets.
  It is the only rule in the arm to pass all of those.
- **⚠⚠ What it fails, and this is not a footnote.** **(a) Parameter neighbours.** The same stall at
  60 / 90 / 120-minute windows runs −3.1 to +1.4pp on 15m bars and is negative at 30m and 60m —
  180min is a narrow ridge (§3.2), and arm 2's independent *"bare stall = 49.2%, a coin"* **matches
  every window except this one**. **(b) It is not a turn detector.** recall60 is 3.9% against a
  rate-matched random 6.5% (§5.1), so whatever it captures, it is not locating the turns. **There is
  no mechanism.** **(c)** Its apparent corroboration by `stall_5m_180min` (SKILL +5.2/+1.4/+5.9/+5.5
  on `ctrl_tod`) is **not independent** — same 180-minute wall-clock rule at a different granularity,
  [[agreement-is-not-independence]].
- **Mechanism, honestly: unknown.** The best available guess is that three hours without a new
  extreme marks a tape that has stopped trending and is about to be resolved by the next session
  hand-over — but the fires are spread across the clock (26% Asia, 40% US, no single hour above 10%)
  and `ctrl_tod` does not touch the edge, so that guess is unsupported.
- **What to do.** **Shadow arm at ±50, single lot, no live money** — point estimate **+2.9pp SKILL**
  against a human ceiling of +0.2pp, on 71% of its fires. Log the ±150 variant for observation only;
  do **not** size it on +8.6pp, which is a 16% subset. ⚠ **Do not tune the 180 minutes.** The 90 and
  120-minute neighbours were raced and are flat; moving it is a search, and the ridge is the single
  biggest reason this is PROMISING and not PROVEN.

### #2 — `donch_5m_180min` · **PROMISING · the smallest edge and the only mechanism**

- **Rule.** 5-minute bars. Donchian channel over the prior **36 closed bars (180 min)**.
  `close > max(high[k−36..k−1])` → LONG; `close < min(low[k−36..k−1])` → SHORT. **Fire only when the
  side changes**; entry at that bar's close.
- **3.80 fires/session · 51.3% long.** TRADEABLE **+3.6 / +3.5 / +3.5 / +2.2pp**; SKILL **+2.4 /
  +1.7 / +1.7 / +0.3pp** (n=772 / 430 / 245 / 134); `ctrl_tod` +4.0 / +3.6 / +2.6 / +1.4pp; every
  clustered CI spans zero.
- **Date halves 2.2/2.5, 2.5/1.1, 1.8/1.6, −0.7/1.0 · sources +2.3/+2.7 at ±50 · phase scan 100%
  positive at ±50, ±100 and ±150.** The most *consistently* positive thing in the study even though
  never the largest.
- **The only candidate with a mechanism and above-random detection.** A three-hour extreme being
  taken out is a real structural fact rather than a confirmation-lagged derivative of one — the break
  **is** the event — which shows up as the best recall60 in §5.1 (14.2% v 8.0% random) and the one
  prec±60 above random (18.0% v 16.9%), at the shortest lag of the three (66-69 min).
- **What to do.** Shadow at **±50** beside #1. Honest expectation **+2.4pp SKILL**, interval
  including zero, against the +0.2pp human ceiling. ⚠ Do not tune the 36 bars: the 120min
  (5.34/sess) and 240min (3.01/sess) neighbours were raced and 180min is the fires/session centre,
  not an optimum.

### #3 — `struct_15m_p3` · **PROMISING at ±100/±150 · and the lead for §5's open question**

- **Rule.** 15-minute bars. A pivot high at bar *j* requires `high[j] ≥ max(high[j−3..j+3])`,
  **confirmed at bar j+3**. Fire SHORT when a newly confirmed pivot high is **lower than the previous
  one**; mirror for LONG (higher pivot low). **No size requirement on any step** — the operator's
  feature ④ exactly.
- **4.35 fires/session · 51.0% long.** TRADEABLE +1.1 / +4.2 / +5.1 / +6.3pp; SKILL +0.4 / **+3.5** /
  **+4.4** / +5.9pp; `ctrl_tod` +1.0 / **+5.2** / **+5.4** / +7.3pp. **Phase scan 100% positive at
  ±100 and ±150** (means +2.3 and +3.8) and **fails at ±50** (20% positive).
- **Fails:** parameter neighbours p=2 and p=4 are negative at ±200 (§3.2); date halves disagree at
  ±100 (−1.8 / +7.2); all clustered CIs span zero; prec±30 3.2% against random 9.1%.
- **But it is the best-timed detector on the board** — 54-minute median lag, 17.3% recall60 against
  9.5% random on arm 2's turns, the only prec±60 above random there. **If the next arm is about
  shortening lag, start here.**
- **What to do.** Shadow at **±100** for observation; it is third because its ±50 cell — the one with
  68% resolution — fails the phase scan.

### #4 — `structboth_5m_p4` · **REFUTED BY THE PHASE SCAN (was the biggest edge in the study)**

5-minute bars, pivots confirmed at *j+4*, requiring **both** a lower pivot high and descending pivot
lows. 4.59 fires/session; SKILL +3.3 / +2.7 / +5.0 / **+9.7pp**; positive in both halves at all four
targets; positive on both sources. **And the phase scan destroys it**: ±200 falls to a phase-mean of
**+3.4pp with sd 7.2** and only 3 of 5 phases positive; ±150 to +1.9pp, 60% positive. Its neighbours
p=3 and p=5 were already negative. **A boundary artefact that passed every other test I had — the
single clearest demonstration that correction ⑦ was necessary.**

### #5 — `netdir_60m_180min` · **REFUTED BY THE PHASE SCAN**

60-minute bars, `sign(close[k] − close[k−3])` flipping — net direction over 3 hours, the operator's
own words at the only sampling rate where it is countable (the same rule on 5m/30min fires
**49.82**/session). 4.51 fires/session; the ±100 cell was the most stable positive in the study —
SKILL +3.9pp, clustered CI **[+0.1, +7.6]**, halves 3.7 / 4.0, sources +4.6 / +2.5. **The phase scan
takes it to a mean of +1.0pp with 60% of 15 phases positive.** The CI, the halves and the source
split all agreed, and all three were fooled by the grid.

### Also measured, and REFUTED

| | |
|---|---|
| **OLS slope sign crossing zero**, no magnitude floor (60 configs) | SKILL +1.9pp at best; phase-stable at ±50 only; `slope_30m_L120min_p3` −1.8 to −4.9pp |
| **STALL + SLOPE agreeing**, no magnitude anywhere (16 configs) | +0.4 to +2.5pp, all CIs spanning zero, ±200 halves +16.3 → −5.9 |
| **Efficiency-ratio crossing a threshold** (36 configs) | −4.6 to +3.1pp, no coherent sign |
| **Join-the-break structure at 30m and 60m** | Coherently **NEGATIVE** to −15.8pp. §3.3 |
| **Trailing-ER conditioning** | Five detectors, three different answers. §3.5 |
| **Conjunctions** (8 configs) | All **below 3 fires/session**. §3.6 |
| **The 322-cell quiet-family surface** | mean edge −0.72pp, z sd 0.946. §3.1 |

### 6.4 The clock test — it is not time-of-day

`stall_15m_180min` has a positive race and below-random turn detection, so the obvious alternative
explanation is a clock: a 180-minute stall needs a quiet tape, which is Asia, and "be positioned
before the US open" is a clock, not a signal. **`ctrl_tod` — the same minute-of-day, the same side,
in 20 randomly chosen OTHER sessions — rules it out:**

| | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|
| `stall_15m_180min` vs `ctrl_tod` | +3.1pp | +4.2pp | +8.7pp | +6.6pp |
| (vs session+side-matched, for comparison) | +2.9pp | +2.5pp | +8.6pp | +6.0pp |
| `donch_5m_180min` vs `ctrl_tod` | +4.0pp | +3.6pp | +2.6pp | +1.4pp |
| `struct_15m_p3` vs `ctrl_tod` | +1.0pp | +5.2pp | +5.4pp | +7.3pp |

The two controls agree, and the fires are spread across the clock (`stall_15m_180min`: 26% in Asia
00-07Z, 40% in US 13-21Z, no single hour above 10%). **Whatever these rules are, they are not the
session hand-over.**

### 6.5 Tape-source split

| rule | ±50 (1min / 5s) | ±100 | ±150 | ±200 |
|---|---|---|---|---|
| `donch_5m_180min` | +2.3 / +2.7 | +2.9 / −0.6 | +0.1 / +4.4 | −1.7 / +3.2 |
| `stall_15m_180min` | +1.5 / +5.8 | +0.3 / +6.9 | +6.7 / +13.4 | +7.2 / +3.3 |
| `struct_15m_p3` | +2.2 / −3.1 | +2.6 / +5.0 | +4.6 / +4.1 | +5.7 / +5.6 |
| `structboth_5m_p4` | +4.1 / +1.5 | +2.9 / +2.2 | +2.6 / +9.9 | +10.1 / +8.8 |
| `netdir_60m_180min` | +2.2 / +0.2 | +4.6 / +2.5 | +1.0 / −2.5 | +0.5 / +5.3 |

Signs agree in 17 of 20 cells. **No conclusion depends on whether a session came from the IBKR
backfill or from our own 5s capture** — [[the-labs-tape-is-not-productions-tape]] is satisfied.

---

## 7. WHAT THIS ARM BANKS

1. **Resampling fixes fire rate and nothing else at the family level.** 116 of 212 configs land in
   2-8 fires/session at coarse scale against 20-90/session at 1m; the family's direction call is
   unchanged across 476 cells (mean edge −0.72pp, z sd 0.946). **It was the COUNTING that was broken
   at 1m, not the discrimination.** Three specific configurations nonetheless survive — a
   distinction worth keeping, because the family verdict is the reason none of them is PROVEN.
2. **★★★ THE WINDOW-PHASE SCAN IS NOW MANDATORY FOR THIS DESK, and it paid for itself twice.** It
   killed `structboth_5m_p4` (+9.7pp → phase-mean +3.4, sd 7.2) and `netdir_60m_180min` (+3.9pp →
   +1.0), **both of which had already passed a day-clustered CI, a date split and a tape-source
   split.** ⚠ With the limitation measured, not assumed: a phase shift perturbs these rules' fire
   counts by only 1-6%, so the scan **rules artefacts OUT and cannot rule an edge IN.**
3. **★ THE SPLIT HE ASKED FOR IS THRESHOLD-DEPENDENT, AND THAT IS THE ANSWER.** At ≥1.5×ATR15 within
   30 minutes **64-74% of real turns are VIOLENT**; at ≥2.0×ATR15, **47-58% are QUIET**. The quiet
   share *shrinks* with leg size (41.0% at a 75pt ZigZag → 26.3% at 150pt), so **quiet is the
   minority among the legs he actually wants**. His description is nonetheless right about the *body*
   of a leg — median new-leg ER **0.3** — so the shape is fast off the pivot and grinding thereafter,
   and quiet turns grind **75% longer** for the same distance. Unambiguous either way: **the median
   turn is 1×ATR15 away after 6-8 minutes.**
4. **★★★ THE FAULT IS CONFIRMATION LAG.** Not one detector — any timeframe, quiet or violent family,
   under **either** turn definition — beats a rate-matched random detector on prec±30. The shipped
   `retrace_15×ATR` scores **3.1% against random's 9.4%**, sees 7.3% of real turns within an hour,
   never sees 39.6% inside four hours, and is a median **114 minutes** late against a median
   **89-minute** leg. **Coarser bars make it worse.** If one thing gets built from this study it
   should be an attempt to name a turn inside its first 15 minutes, starting from `struct_15m_p3`.
5. **⚠ A METHOD NOTE FOR THE OTHER ARMS: measure the side-artefact's direction, do not infer it.**
   This tape rose **+6,696.8pt** and **SHORT still wins the symmetric race 57.2% to 42.8% at ±200pt**,
   because a race rewards the faster tail (DOWN p99 178.0pt vs UP 164.8pt) rather than the sum. A
   short-tilted rule collects up to **+14.4pp** free here. A random-side control is 50.0% by
   construction (proved on 40,000 minutes) — so report **rule − 50** and **rule − side-matched**, and
   when they differ, the difference *is* the tilt.
6. **Two cross-arm discrepancies to reconcile, not average.** 273 sessions here under six counting
   definitions against arm 2's 328; and **5.88 turns/session** from arm 2's own ±90min/60pt pivot
   definition against its reported **3.96**. Similar ratios point at one shared cause, most likely
   the session window. **Per-session rates are incomparable between the arms until that is settled.**

> **Status of every lead.** `stall_15m_180min` → **SHADOW at ±50**, observe ±150; the parameter ridge
> and the missing mechanism are why it is not more. · `donch_5m_180min` → **SHADOW at ±50**. ·
> `struct_15m_p3` → **SHADOW at ±100**, and **LEAD on lag**. · `structboth_5m_p4`,
> `netdir_60m_180min` → **REFUTED by the phase scan.** · `slope_*`, `stallslope_*`, `ercross_*`,
> stall at every window except 180min, trailing-ER conditioning, conjunctions, join-the-break at
> 30-60m → **REFUTED**. · **Short-lag turn detection → the open lead, and the one this arm
> recommends.**

---

### Reproduction

Scripts in the session scratchpad: `arm4_lib.py` (loader / resampler / race), `arm4_sigs.py`
(detectors), `arm4_screen.py`, `arm4_score2.py`, `arm4_neigh.py`, `arm4_robust.py`, `arm4_quiet.py`,
`arm4_detect.py`, `arm4_calib.py`, `arm4_calib2.py`, `arm4_src.py`, `arm4_arm2.py`, `arm4_recon.py`,
`arm4_sesscount.py`, `arm4_tod.py`, `arm4_final.py` (ambiguity fix + both numbers + phase scan),
`diag_race.py`. This arm does **not** import `scripts/entry_cvd_climax.py`: its loader was written
independently (which is how the eight-timeframe contamination was found), and its `race` now matches
the fixed shared version's ambiguity handling.

**Nothing in this arm wrote to `gazbot7.db`, `capture.db` or any switch, request or state file,
placed an order, POSTed to `/api/control`, or restarted a service. The only file written is this
report.**
