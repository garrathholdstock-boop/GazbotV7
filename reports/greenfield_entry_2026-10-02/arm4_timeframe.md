# ARM 4 of 4 — THE LEG AT A COARSER SCALE

**MNQ · 273 session-days · 2025-09-14 → 2026-10-01 · read-only · 2026-10-02**

> **THE HYPOTHESIS, AS BRIEFED.** Every signal tested so far was computed on ONE-MINUTE bars, and on
> that scale a 298pt / 266min leg is buried in noise — net-direction flips fire 42-87 times a
> session. Resample to 5m / 15m / 30m / 60m and the same rule should become statistically obvious.
>
> **THE ANSWER. The hypothesis is CONFIRMED on fire rate and REFUTED on direction.** Resampling
> fixes exactly what it was predicted to fix: every family that fired 20-90 times a session at 1m
> lands inside the 3-6 target zone at 15-60m (net-direction flips go 49.82/session → **4.51**). It
> does not fix the only thing that pays. Across **476 scored race cells**, the 322 surface cells with
> n≥50 have a mean edge of **−0.72pp** and a z-distribution of mean −0.193 / sd 0.946 against H₀'s
> 0 / 1.00, with 5.3% beyond |z|>1.96 against H₀'s 5.0% — and the significant tail pointing the
> **wrong way** (4.0% negative, 1.2% positive). No configuration survives neighbour agreement, a date
> split and a day-clustered interval together.
>
> **THE OPERATOR'S CORRECTION IS PART-REFUTED, AND HIS INSTINCT POINTS AT A REAL AND DIFFERENT
> FAULT.** Whether turns are mostly quiet depends entirely on where the violence bar is set (§4.2):
> at ≥1.5×ATR15 inside 30 minutes, **64-74% are VIOLENT**; at ≥2.0×ATR15, **53-58% are QUIET**. What
> is unambiguous is the clock — the median turn is 1×ATR15 (≈48-62pt) away after **6-8 minutes** and
> 50pt away after **3-9**. And what is unambiguous is the failure: the shipped magnitude detector sees
> only **7.3%** of real turns within an hour and is a median **114 minutes** late, while **every
> detector tested here, at every timeframe, under both turn definitions, lands near a real turn LESS
> often than a rate-matched random detector does.** **The fault is CONFIRMATION LAG, not
> magnitude-versus-quiet** — and coarsening the bars makes it worse, not better. §5.

---

## 0. THE FOUR MID-FLIGHT CORRECTIONS — WHAT EACH DID TO THIS ARM

| correction | status here |
|---|---|
| **① Use a SIDE-MATCHED control, not random-side** | **Already applied — found independently, §1.3.** The first pass used the brief's random-side control, produced controls reading 43.8% on a symmetric race, and was rebuilt around a session-**and**-side-matched control before any result was read. ⚠ **BUT THE SIGN OF THE ARTEFACT IS THE OPPOSITE OF THE ONE REPORTED.** On this tape a **SHORT**-biased rule gets the free lift, not a long-biased one, and it is worth up to **+14.4pp** — nearly 3× arm 2's 5pp. The net drift does not tell you the sign; it must be measured. §1.3 |
| **② `bars` mixes timeframes for the same minute** | **Already applied, and taken further — §1.1.** One dominant timeframe is chosen per session, *and* every coarse timeframe (`5m`, `5mins`, `3m`, `1hour`, `1day`) is excluded outright because those rows are **left-edge labelled** and would import a future extreme. No volume is used anywhere in this arm, so the double-count does not arise. `minute` being reserved was hit and aliased |
| **③ Re-run on arm 2's larger ≥300-bar session set** | **No larger set exists for MNQ.** 273 sessions under **six** different counting definitions — distinct-minutes vs rows, 22:00Z vs calendar day, fine-only vs all-timeframe, MNQ vs MNQ+MGC — all return **273**. The per-expiry backfill in `data/backfill/` (outside the lake glob) was checked separately: 5 files, 2025-09-14 → 2026-09-18, **263** qualifying sessions, i.e. the same tape. **The 328 figure is not reproducible from this box and needs reconciling at the coordinator's end.** §1.1 |
| **④ Arm 2's ±90min / 60pt pivot definition, and its refuted list** | **Adopted as a second ground truth and re-measured — §4.5, §5.2.** On this session set it yields **5.88 turns/session**, not 3.96 (a discrepancy that travels with ③). Every §5 conclusion holds under both definitions. Arm 2's *"a bare STALL raced at 49.2%, a coin"* **replicates here independently** — §3.4 row 1 — and arm 2's *"the one survivor was a conjunction"* was tested: §3.6, rejected on fire rate |

---

## 1. METHOD, AND THE THREE TRAPS THAT CHANGED THE NUMBERS

### 1.1 The tape, and why it is 273 sessions

`gazbot7.lake.connect()`. The `bars` table holds eight timeframes for MNQ; only `5s`, `1min` and `1m`
are used. **The others are excluded because they are LEFT-EDGE LABELLED** — a `1hour` bar stamped
14:00 carries the high and low of 14:00-15:00, so folding one into a per-minute aggregate imports the
next hour's extreme into the minute being decided on, and the race then resolves off a price that had
not printed.

> ⚠ `scripts/entry_cvd_climax.load()` queries `FROM bars` with no timeframe filter and does exactly
> this. Its `ticks` join restricts it to 74 recent sessions where the damage is smaller, but it is a
> look-ahead and it should be filtered.

One source timeframe **per session**, priority `5s` > `1min` > `1m`, rather than `MAX(high)/MIN(low)`
across sources: mixing our own capture with the IBKR backfill inside one session makes the bar
extremes source-dependent for no gain. **No volume column is read anywhere in this arm**, so the
`SUM(volume)` double-count the coordinator flags cannot reach these results.

| | |
|---|---|
| sessions with ≥300 one-minute bars | **273** |
| source | **197** sessions IBKR `1min` backfill · **76** sessions our own `5s` capture |
| minutes/session | min 646 · median **1380** (the full 23h ETH session, 22:00Z anchor) · max 1380 |
| span | 2025-09-14 → 2026-10-01 |
| closed bars/session | 5m **271.7** · 15m **89.9** · 30m **44.5** · 60m **21.7** |

**Six counting definitions, all 273:** ≥300 distinct minutes with fine timeframes only · the same
with all timeframes · ≥300 **rows** rather than minutes · calendar-day instead of 22:00Z sessions ·
≥300 rows within the best single (session, timeframe) pair · MNQ **and** MGC together. The
per-expiry MNQ backfill outside the lake glob adds nothing (263 qualifying sessions over the same
dates). **273 is the ceiling for minute-resolution MNQ tape on this box.**

The brief's "616 session-days / 1.64M rows" is the union over *all* timeframes: 483 of those days
exist only as `1day` bars and 476 only as `1hour`. Neither can carry a minute-resolution race.

**Source is not driving any result.** Every shortlisted config was re-scored on the 197 backfill
sessions and the 76 own-capture sessions separately: signs agree in 17 of 20 cells and no conclusion
flips (§6.5). [[the-labs-tape-is-not-productions-tape]] is satisfied.

### 1.2 The left-edge look-ahead, handled three ways

A pandas-style resample labels a K-minute bar with its **opening** timestamp, and racing forward
"from ts" replays the K minutes being decided on. So:

1. Buckets are **absolute** (`epoch_minute // K`) — a missing minute cannot shift the grid.
2. Every K-bar is keyed by the **index of its final minute**, not its first.
3. **The last bucket of every session is dropped** — it has not been proven closed, and a rule that
   reads a still-forming bar is reading the future. A bar becomes visible only once the next bucket
   has opened.

The race then starts at `last_minute_index + 1`. Nothing a rule reads and nothing the race scores
overlap. Swing pivots carry the same discipline: a pivot at bar *j* needs *p* bars either side, so it
is **confirmed at bar j+p** and entry is at `close[j+p]` — reading the pivot as it forms is the shape
of error that once produced 866 winners from 866 trades.

`DuckDB /` was tested rather than assumed: `(7/2)::BIGINT` returns **4** on this build (it rounds, it
does not truncate), so every bucketing uses `//`. `minute` and `days` are both reserved words here
and are aliased.

### 1.3 ⚠⚠⚠ THE CONTROL — AND THE ARTEFACT'S SIGN IS THE OPPOSITE OF THE ONE REPORTED

The first scoring pass used the brief's control (same count, same sessions, random minute, random
side) and produced controls reading **43.8%** and **46.4%** on a symmetric race, which is impossible.
Diagnosed on 40,000 random minutes:

| entering at a random minute | ±50pt | ±100pt | ±150pt | ±200pt |
|---|---|---|---|---|
| **LONG** wins the race | 48.7% | 45.6% | 45.0% | **42.8%** |
| **SHORT** wins the race | 51.4% | 54.4% | 55.0% | **57.2%** |
| mean over sides | 50.0% | 50.0% | 50.0% | 50.0% |

The race is exactly side-symmetric — a random-side control is **50.0% by construction** — but the
tape is not side-neutral. **A rule that merely fires SHORT more often than LONG inherits up to
+14.4pp at ±200pt for free, and a single random-side control averages that away and hides it.** With
5 matched draws its own SE was ~2pp, the size of the effects being claimed.

> ### ⚠ CORRECTION TO CORRECTION ①, AND IT MATTERS FOR EVERY ARM
> The coordinator's reasoning was *"the lake tape ROSE +5,712pt, so a long-biased rule beats a
> random-side control on drift alone."* **The premise is right and the conclusion is backwards.**
> Measured on these 273 sessions: the tape **rose +6,696.8pt** (first close 24,352.2 → last close
> 31,049.0; 54.6% of sessions closed up) — **and SHORT still wins the symmetric race 57.2% to 42.8%
> at ±200pt.**
>
> Both are true because **net drift and race asymmetry are different statistics.** A symmetric race
> is decided by which side reaches N points **first**, which rewards the faster, fatter tail — not
> the sum. Measured on 30-minute moves: UP median 20.0pt / p90 71.2 / p99 164.8 against DOWN median
> 19.8pt / **p90 73.0 / p99 178.0**. The tape grinds up and drops fast, so it has positive net
> displacement **and** a short-favouring race.
>
> **So the free lift goes to SHORT-biased rules here, and it is ~14pp rather than ~5pp.** The sign of
> this artefact cannot be inferred from a net drift figure — it has to be measured on the actual race
> definition, and the arms should agree on one measurement before comparing edges.

Both controls were rebuilt, and both are reported:

- **`ctrl_mix`** — session- **and** side-matched: the rule's own long/short mix, in the rule's own
  sessions, at random minutes. 400 draws per session per side (≈109k per side per target, SE
  ~0.3pp). This charges a rule for the tape's drift.
- **`ctrl_tod`** — time-of-day- and side-matched in **other** sessions: for each fire at
  minute-of-day T on side d, race side d at minute-of-day T in 10 randomly chosen other sessions.
  Asks the sharper question — is *this* session's moment special, or is "15:30Z short" just good?

The two agree to within ~1-2pp everywhere, which is the reassurance that neither is broken. All
edges below are **rule − `ctrl_mix`** unless stated.

**Every rule's long/short split, as requested.** None of them is materially tilted, so for *this*
family the artefact is small even before the control charges it — the warning above is for the
EMA/net-direction rules on 1m that the coordinator flags, which are structurally tilted:

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

> ⚠ **And it follows that my inherited numbers are suspect in the other direction too.** The brief's
> *"EMA 20/60 at +3.9pp"* and *"netdir_60 at +3.0pp"* were scored against a random-side control; on
> this tape that control **understates** a long-biased rule and **overstates** a short-biased one.
> They were not inherited — every rule in this arm was re-derived from the tape against the matched
> control.

### 1.4 Uncertainty

**Per-fire binomial SE is inflated here.** ~4.5 fires a session with overlapping 120-minute races are
not independent draws — this desk measured per-observation t on book data as ~10× too confident. So
every interval in §4 and §6 is a **block bootstrap over sessions** (the cluster is the day, 2,000
resamples), with the rule *and* its matched control recomputed inside each resample.

### 1.5 The charged search

| stage | what | outcome touched? |
|---|---|---|
| eligibility screen | **212** configs, fires/session only | **no** — the brief's hard gate (3-6/session; 20+ rejected regardless of accuracy) reads no outcome |
| ↳ eligible at 2.0-8.0/session | 116 | no |
| ↳ **selected, outcome-blind** | **28** — per (family × timeframe), the eligible parameter closest to 4.5 fires/session | no |
| main race | 28 × 4 targets | **112 cells** |
| neighbour surface | 96 × 4 targets | **384 cells** (322 with n≥50) |
| conjunctions | 8 × 4 targets | **32 cells** |
| **distinct configs raced** | **119** × 4 targets | **476 primary race cells** |
| trailing-ER terciles | 5 × 3 × 4 | 60 sub-cells |
| date halves | 11 × 4 × 2 | 88 sub-cells |
| tape-source split | 5 × 4 × 2 | 40 sub-cells |
| detection quality | 15 detector × turn-definition rows × 5 metrics | 75 cells |
| **total outcome-touching comparisons** | | **≈ 740** |

> ⚠ 5,026 specs once reproduced a published t=5.83 from pure noise 13% of the time. At 476 race cells
> the bar is high, and §3.1 charges it formally rather than rhetorically. Selection into the main
> race was fixed **before any race was run**, and no config was promoted for being the best
> neighbour.

---

## 2. THE HALF THAT WORKS — RESAMPLING FIXES THE FIRE RATE

This is the real, reproducible benefit of coarsening, and it is worth banking on its own.

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
bars and 3.05 at 180 minutes; `donchian` 15.99 → 3.01. **A rule that fired 50 times a session at 1m
fires 4 times a session at 60m, and 116 of 212 screened configs land in the 2-8 range.** The brief's
signal-to-noise claim is correct about *counting*: a 266-minute object is not legible on a 1-minute
grid, and coarsening makes it countable.

It does not make it right.

---

## 3. THE HALF THAT FAILS — THE DIRECTION CALL IS STILL A COIN

### 3.1 The noise calibration — the decisive test

The full parameter surface of the four quiet-family detectors (96 configs × 4 targets) was raced, so
the question *"is there anything in this family at all"* could be asked of the **distribution**
rather than of its maximum.

| 322 cells with n ≥ 50 | observed | H₀ expects |
|---|---|---|
| mean edge | **−0.72pp** | 0 |
| median edge | −0.50pp | 0 |
| sd of edge | 3.64pp | — |
| mean z (per-fire binomial, **no** day clustering — deliberately generous to the null) | **−0.193** | 0 |
| sd of z | **0.946** | 1.00 |
| \|z\| > 1.96 | **5.3%** | 5.0% |
| z > +1.96 | **1.2%** | 2.5% |
| z < −1.96 | **4.0%** | 2.5% |

**A textbook null with a slight negative tilt** — and the z-spread of 0.946 against an expected 1.00
is computed *without* the day-clustering correction that would shrink it further. The surface yields
exactly as many "significant" cells as chance, and twice as many losing as winning.

### 3.2 The surface alternates sign, which is what noise looks like

The two biggest edges in the study both die here.

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

An edge of +9.5pp between two negative neighbours is a fitted knob, not a mechanism. The brief's own
rule binds: **under +6pp is indistinguishable unless neighbouring cells agree — and here they
actively disagree.**

### 3.3 Where the surface is coherently NEGATIVE — a known result, replicated

`struct` and `structboth` at 30m and 60m are consistently and at real n **wrong-sided**:

| config | fires/sess | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|
| `struct_60m_p1` | 2.10 | −2.8 (n=430) | −4.6 (n=220) | **−9.2** (n=122) | **−8.7** (n=67) |
| `structboth_60m_p1` | 1.07 | −0.0 | −3.1 | **−12.8** | **−15.8** |
| `structboth_30m_p2` | 1.34 | −5.3 | −8.0 | **−13.3** | **−14.0** |
| `struct_30m_p3` | 1.64 | −0.2 | −3.4 | −7.2 | −8.6 |
| `slope_30m_L120min_p3` | 4.30 | −1.8 | −1.9 | −3.4 | −4.9 |

Confirming a lower high on a 60-minute chart and going short is a **losing** trade, and it worsens as
the target widens. That is [[break-then-join-direction-is-a-coin]] and *"joining a 60-min break is
significantly NEGATIVE"* reappearing in a new family, at a new timeframe, from a new direction. **It
replicates. Do not build a join-the-new-direction entry at 30-60m scale.**

### 3.4 The quiet features specifically — the operator's four

| feature | best eligible config | fires/sess | verdict |
|---|---|---|---|
| **① STALL, measured in time** (minutes since the last new extreme; no giveback required) | `stall_15m_180min` | 3.05 | **REFUTED as an entry — and this independently replicates arm 2's *"a bare STALL raced at 49.2%, a coin"*.** +2.9/+2.4/+8.8/+5.9pp here, but the 90min and 120min stall-window neighbours are flat-to-negative on 5m, 15m, 30m *and* 60m bars; the halves decay 13.3→3.5 and 14.8→−0.0; and detection is the **worst in the table** (recall60 3.9% against a rate-matched random 6.5%). ⚠ Its apparent corroboration by `stall_5m_180min` is **not independent** — both are the same 180-minute wall-clock criterion at two granularities, [[agreement-is-not-independence]] |
| **② SLOPE SIGN CHANGE** (OLS over a rolling window, **no magnitude floor**, held P bars) | `slope_15m_L180min_p3` | 5.09 | **REFUTED.** +1.9/+0.4/+0.0/+1.9pp, every CI spanning zero; the 30m variant runs −1.8 to −4.9pp. Dropping the magnitude floor was the right instruction and it changed nothing |
| **③ LOW-ER CONTINUATION** | §3.5 | — | **REFUTED — and the inconsistency IS the evidence** |
| **④ STRUCTURE WITHOUT THRUST** (successive lower highs / higher lows, no size requirement on any step) | `struct_15m_p3` / `structboth_5m_p4` | 4.35 / 4.59 | **PARKED.** The largest edges in the study and the only family positive in *both* date halves at all four targets — but §3.2 shows the parameter is a fitted knob and §5 shows it lands near a real turn less often than random |
| (conjunction) **STALL + SLOPE agreeing**, no magnitude anywhere | `stallslope_30m_90min` | 3.57 | **REFUTED.** +0.4/+2.1/+2.1/+2.5pp, all CIs spanning zero, ±200 halves swinging +16.3 → −5.9 |

### 3.5 Feature ③, read causally — and why it fails

> The instruction was to test whether a direction change *"followed by* LOW efficiency" is more
> reliable. **Read literally that is a look-ahead** — the efficiency of the move *after* the fire is
> not knowable at the fire. The implementable version was tested instead: split each detector's fires
> by the **trailing** ER over the 120 minutes **up to** the fire. The forward version is in §4.4,
> flagged as not implementable.

| detector | LOW-ER tercile (grindy tape) | MID | HIGH-ER tercile (trending) |
|---|---|---|---|
| `structboth_5m_p4` (±200) | +9.3 | +3.6 | **+15.0** ← high best |
| `struct_15m_p3` (±150) | +5.4 | **+10.1** | −0.0 ← mid best |
| `stall_15m_180min` (±150) | −1.0 | **+21.8** | +2.9 ← mid best |
| `donch_5m_180min` (±150) | −1.5 | +2.8 | **+5.7** ← high best |
| `slope_15m_L180min_p3` (±150) | **+7.4** | −8.9 | −0.1 ← low best |

**Five detectors, three different answers, one of them the middle tercile.** If a quiet trailing tape
genuinely made a turn more reliable the sign would be stable across detectors. It is not, and at
n=20-108 a 20pp swing costs nothing. **REFUTED, and the disagreement is more informative than any
single row.**

### 3.6 CONJUNCTIONS — arm 2's shape, tested and rejected on fire rate

Arm 2's one survivor was a conjunction of two conditions, never a single feature. So the two
detectors here with any above-random detection were crossed with the two structural ones, requiring
**agreement on side within W minutes**, entry at the later fire:

| conjunction | fires/sess | %lng | ±50 | ±100 | ±150 | ±200 |
|---|---|---|---|---|---|---|
| `donch_5m_180` + `netdir_60m_180`, W=30 | **1.75** ✗ | 52.0 | +2.7 (n=386) | +2.3 (n=220) | +0.7 (n=121) | −1.4 (n=64) |
| `donch_5m_180` + `netdir_60m_180`, W=60 | **2.60** ✗ | 49.4 | +2.7 (n=563) | +2.7 (n=321) | −0.4 (n=186) | −0.1 (n=105) |
| `netdir_60m_180` + `struct_30m_p1`, W=60 | **1.95** ✗ | 48.4 | +0.2 (n=397) | +4.1 (n=209) | +3.6 (n=112) | +16.0 (n=63) |
| `netdir_60m_180` + `struct_30m_p1`, W=30 | **1.30** ✗ | 47.6 | +1.3 (n=264) | +6.0 (n=138) | +4.0 (n=74) | +11.2 (n=47) |
| `donch_5m_180` + `struct_15m_p3`, W=30 | **0.74** ✗ | 46.8 | +3.1 (n=144) | +2.5 (n=78) | +9.3 (n=45) | +15.0 (n=17) |
| `donch_5m_180` + `struct_30m_p1`, W=60 | **1.30** ✗ | 52.5 | −1.8 (n=239) | +2.6 (n=131) | +0.3 (n=69) | −6.3 (n=34) |

**All eight conjunctions fall BELOW the 3/session floor** (0.74-2.60) and are rejected on the brief's
own gate before accuracy is considered. The large-looking ±150/±200 figures sit on n=17-63, where a
single session's run moves the cell 10pp — and the W=30 and W=60 variants of the *same* pair disagree
by 16pp at ±200, which is the tell. **A conjunction halves the fire rate out of the target zone,
which is the structural problem with the shape in this arm: the single features already fire only
3-5 times a session.** Arm 2's conjunction worked from a 5.85/session climax detector, with room to
spend.

---

## 4. THE OPERATOR'S QUESTION — VIOLENT OR QUIET?

> *"the thing you need to understand is the turns are not violent. they often just change direction.
> sometimes its violent. but more often than not it can just start grinding in that direction."*

### 4.1 Ground truth, and its honest limits

Turns are defined two ways: a **ZigZag** on minute highs/lows at 75 / 100 / 150pt, and **arm 2's
±90min pivot with both legs ≥60pt** (§4.5), so the arms describe the same population. **Both are
descriptive ground truth, not signals** — a pivot is identified with hindsight by construction.
Violence is measured **only from what happens after the pivot**, normalised by ATR14 on **closed
15-minute bars as known at the pivot**, so the yardstick carries no future.

| ZigZag | turns | per session | median ending leg | median new leg | new-leg ER |
|---|---|---|---|---|---|
| 75pt | 4,308 | 15.78 | 126.8pt / 23min | — | 0.4 |
| 100pt | 2,482 | 9.09 | 166.0pt / 41min | 163.8pt / 35min | 0.3 |
| **150pt** | **1,053** | **3.86** | **244.5pt / 89min** | **239.0pt / 75min** | **0.3** |

The 150pt threshold reproduces the brief's leg population on count (3.86 vs 3.1/session) and size
(244pt vs 298pt); duration runs shorter (89 vs 266min) because `leg_watch`'s 3×ATR retrace rule
merges across pullbacks a 150pt ZigZag splits.

### 4.2 ★ THE SPLIT — and it is THRESHOLD-DEPENDENT, which is the honest answer

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

**There is no single number, and claiming one would be the fitted answer.** Set the violence bar at
1.5×ATR15 in 30 minutes (≈70-95pt) and violent wins **64-74%**. Set it at 2.0×ATR15 (≈95-125pt) and
quiet wins **47-58%**. His belief is defensible at the higher bar and wrong at the lower one.

Two things *are* unambiguous, and both cut against treating turns as slow events:

| time for the new direction to travel | ZigZag 150pt | arm 2 pivot |
|---|---|---|
| 1×ATR15 (≈62pt / ≈48pt) | **6 min** | **8 min** |
| 50pt | **3 min** | **9 min** |
| 100pt | 14 min | 33 min |
| never reaches 1×ATR15 inside 180min | **0.5%** | **0.4%** |

And the quiet share **shrinks as legs get bigger**: 41.0% quiet at a 75pt ZigZag → 34.2% at 100pt →
**26.3% at 150pt** (all at the 1.5× bar). **The quiet turns are disproportionately the small ones;
the big legs he wants are the violent ones.**

> ⚠ **THE ONE CONDITIONING CAVEAT, STATED PLAINLY.** A 150pt ZigZag pivot is *defined* by a
> subsequent 150pt giveback, so "the new direction eventually moves 150pt" is guaranteed by
> construction. **How FAST it does so is not** — that is the measurement. But the population is
> conditioned on moves that reach 150pt, so the honest statement is: *among the moves that become
> real legs, the median covers 100pt in 14 minutes.* That is the population he trades, so it is the
> relevant number — it is not a statement about all slope changes. Arm 2's ±90min definition is
> conditioned differently (both legs ≥60pt) and gives 33 minutes to 100pt, so the two bracket it.

### 4.3 WHY IT FEELS QUIET ANYWAY — both halves of his description are true

The median new leg's **efficiency ratio is 0.3** at every ZigZag threshold. The shape of a real turn
is therefore **fast off the pivot, grindy thereafter**: 100 points in 14 minutes, then another hour
to deliver the next 140 at an ER of 0.3, zig-zagging the whole way.

**That reconciles his description with the data.** What he watches — "it just starts grinding in that
direction" — is the *body* of the leg, and he is right about it. What the measurement adds is that
the **first fifteen minutes are not like the rest**, and that window is where the entry lives.

### 4.4 Quiet turns lead to LONGER legs — descriptive, not implementable

ZigZag 150pt, split at 30min ≥ 1.5×ATR15 (uses the *next* pivot, so **not** implementable):

| | median new leg | duration | new-leg ER | n |
|---|---|---|---|---|
| after a **QUIET** turn | 228.5pt | **110 min** | **0.2** | 195 |
| after a **VIOLENT** turn | 242.1pt | 63 min | 0.3 | 622 |

Same size, **75% longer to deliver it, at a lower ER**. A quiet turn is a slower grind, not a smaller
one.

### 4.5 Arm 2's pivot definition, re-measured here — and a second discrepancy

Implemented as specified (a ±90-minute pivot with both legs ≥60pt) it yields **1,604 turns over 273
sessions = 5.88/session**, against arm 2's reported **3.96/session**; median ATR15 at the turn 47.5pt
against the ZigZag's 61.8pt. The ratio is close to the session-count ratio, so **the most likely
cause is the same one behind the 273-vs-328 discrepancy** — a different session window (23h ETH here)
or a different session set. **Worth reconciling before the arms' turn-rate figures are compared**, and
flagged rather than quietly averaged. Every §5 conclusion is reported under both definitions and
holds under both.

---

## 5. ★★★ THE REAL FAULT — CONFIRMATION LAG, NOT MAGNITUDE

This is the finding that should direct the next effort, and the one place the quiet-turn hypothesis
was pointing at something real.

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
prec±30/60 = share of its own fires sitting within that many minutes of a real turn on the correct
side. "v" = the rate-matched random detector.*

Three things fall out, identically under both turn definitions.

1. **NOT ONE DETECTOR BEATS RANDOM ON prec±30 — under either definition.** Every one is *below* its
   rate-matched baseline (3.0-8.6% against ~9.1-9.4% on ZigZag; 1.9-10.3% against ~13.0-13.5% on arm
   2's pivots). None lands in the half-hour around a real turn more often than a dart. That is
   systematic, not noise: these rules all require confirmation, so they systematically **avoid** the
   window around the pivot and arrive at +42 to +104 minutes.
2. **HIGH recall120 IS LAG WEARING A DISGUISE.** `stall_60m_30min` "detects" 54.1% of turns against
   random's 23.0% — at a median lag of **87 minutes**, against a median leg of **89 minutes**. It
   names the turn as the leg ends; `stall_30m_90min` is worse at 104. **A high recall at a 120-minute
   horizon is a clock, not a signal.**
3. **THE SHIPPED MAGNITUDE RULE IS THE WORST THING IN BOTH TABLES.** `retrace_15×ATR` on 1m scores
   prec±30 of **3.1% against random's 9.4%**, and **1.9% against 13.0%** on arm 2's turns — a
   seventh of chance — with a median lag of 85-86 minutes. Measured against ground truth
   independently: it fires within 60 minutes of a real turn **7.3%** of the time, within 120 minutes
   32.3%, and **never within 240 minutes on 39.6% of turns**; median delay when it does, **114
   minutes**.

> **SO THE OPERATOR IS RIGHT ABOUT THE SYMPTOM AND WRONG ABOUT THE CAUSE, AND THE CAUSE IS WORSE.**
> He says magnitude detectors miss turns because the turns are quiet. They miss turns because **they
> are an hour and a half late** — by which time the median leg is over and the median turn is 150+
> points away. Re-pointing the same confirmation logic at coarser bars cannot fix that; coarsening
> **adds** lag, which is exactly why the 60m variants are the latest (§5.1) and the most negative
> (§3.3).
>
> **The next arm should not be another detector. It should be an attempt to shorten the lag** — to
> name a turn inside its first 15 minutes, where §4.2 says 1.59×ATR15 of the move still lies ahead of
> a median pivot and §4.3 says an hour of grind follows. Every rule tested across all four arms pays
> for its confidence with the part of the move that was worth having. `struct_15m_p3` is the only
> thing in this arm pointing that way: shortest lag (54m), best recall60 on arm 2's turns (17.3% v
> 9.5%) and the one prec±60 above random there (29.1% v 25.8%) — its *race* is a null, but its
> *timing* is the least bad on the board.

---

## 6. RANKED SHORTLIST — best first

**Nothing clears the bar.** No configuration is simultaneously (a) inside 3-6 fires/session,
(b) positive beyond the day-clustered interval, (c) coherent with its parameter neighbours, and
(d) stable across the date split. Ranked by what came closest, each named precisely enough to
implement.

### #1 — `donch_5m_180min` · **PROMISING-WEAK · the only one worth a shadow arm**

- **Rule.** 5-minute bars, absolute buckets, final bucket of the session dropped. Donchian channel
  over the prior **36 closed bars (180 min)**. `close > max(high[k−36..k−1])` → LONG;
  `close < min(low[k−36..k−1])` → SHORT. **Fire only when the side changes** (flip-only); entry at
  that bar's close.
- **Fires/session 3.80 · 51.3% long** — inside the target window, side-balanced.
- **Race (edge vs session+side-matched control; day-clustered 95% CI):**

  | | ±50pt | ±100pt | ±150pt | ±200pt |
  |---|---|---|---|---|
  | edge | **+2.4pp** | +1.7pp | +1.7pp | +0.3pp |
  | CI95 | [−1.0, +6.0] | [−2.6, +6.3] | [−4.3, +7.7] | [−7.5, +8.2] |
  | n | 772 | 430 | 245 | 134 |
  | halves | 2.2 / 2.5 | 2.5 / 1.1 | 1.8 / 1.6 | −0.7 / 1.0 |
  | by source (1min / 5s) | +2.3 / +2.7 | +2.9 / −0.6 | +0.1 / +4.4 | −1.7 / +3.2 |

- **Why it ranks first despite the smallest edges.** It is the **only** configuration positive in
  *both* date halves at *every* target, positive on *both* tape sources at ±50, and above its
  rate-matched random baseline on detection under both turn definitions (recall60 14.2% v 8.0% and
  11.9% v 8.8%). Low and consistent beats large and alternating.
- **Mechanism, in one sentence.** A three-hour extreme being taken out is the only event in this arm
  that is both a real structural fact and *not* a confirmation-lagged derivative of one — the break
  **is** the event, so its lag is 66-69 minutes rather than 87-104.
- **What to do.** Shadow arm at **±50pt only**, single lot, no live money. Honest expectation ≈
  **+2pp over a matched random entry** — a few dollars a day at one lot, interval including zero.
  ⚠ Do **not** tune the 36 bars: the 120min (5.34/sess) and 240min (3.01/sess) neighbours were raced,
  and 180min is the fires/session centre, not an optimum.

### #2 — `netdir_60m_180min` · **PROMISING-WEAK · the 1m-refuted rule, rehabilitated to "null"**

- **Rule.** 60-minute bars. `sign(close[k] − close[k−3])` — net direction over the last 3 hours. Fire
  when the sign flips; entry at that bar's close.
- **Fires/session 4.51 · 49.3% long** (the same rule on 5m bars with a 30min lookback fires
  **49.82**/session).
- **Race:** ±50 **+1.6pp** [−1.3,+4.8] n=946 · ±100 **+3.9pp** [+0.1,+7.6] n=533 · ±150 −0.1pp
  [−5.4,+5.2] n=289 · ±200 +2.1pp [−4.7,+8.8] n=173.
- **The ±100 cell is the single most stable positive in the study** — halves 3.7 / 4.0, sources
  +4.6 / +2.5 — and the only cell whose clustered interval clears zero *and* replicates in both
  halves. But ±150 is −0.1, so it is one target of four, and across 44 bootstrapped cells ~2 should
  clear 95% by chance.
- **Mechanism.** Three hours of net displacement reversing sign is the operator's own rule
  ("direction is net in one direction, and then for a period it changes") at the only sampling rate
  where it is countable.
- **What to do.** Shadow beside #1 **at ±100 only**. The pairing *is* the test: if the cell is real
  it reappears forward; if it was the 2-in-44, it will not. Cheap, and it answers his own stated rule.

### #3 — `structboth_5m_p4` · **PARKED — biggest edge in the study, fitted parameter**

- **Rule.** 5-minute bars. A pivot high at bar *j* requires `high[j] ≥ max(high[j−4..j+4])`,
  **confirmed at bar j+4**. Fire SHORT when a newly confirmed pivot high is **lower than the previous
  one** *and* the last two pivot lows are also descending; mirror for LONG. No size requirement on
  any step.
- **4.59 fires/session · 51.2% long.** Edges **+3.3 / +2.7 / +5.0 / +9.7pp**; CIs [−0.1,+6.6],
  [−1.3,+7.0], [−0.9,+11.3], [−0.2,+19.6]; halves **positive in both at all four targets**
  (2.2/4.1, 1.6/3.3, 2.6/6.5, 12.7/7.4); sources +4.1/+1.5, +2.9/+2.2, +2.6/+9.9, +10.1/+8.8.
- **Why parked, not shortlisted.** It passes temporal *and* source stability and **fails parameter
  stability**: p=3 is −0.9/−1.0 at ±150/±200 and p=5 is −2.1/−3.3/−1.4 — four neighbours, two
  negative. And prec±30 is 6.5% against a random 9.2%: it is not finding the turns. **Reviving it
  needs a mechanism for why 4 bars and not 3 or 5**, not a re-run.

### #4 — `struct_15m_p3` · **PARKED on the race, but it is the lead for §5's open question**

15-minute bars, pivots confirmed at *j+3*, fire on a lower confirmed pivot high (or higher pivot
low), no size requirement. 4.35 fires/session · 51.0% long; edges +0.5/+3.4/+4.5/+5.7pp; all CIs span
zero; halves disagree at ±100 (−1.8 / +7.2); neighbours p=2 and p=4 both negative at ±200. **Its race
is a null — but it has the shortest lag on the board (54 min), the best recall60 against arm 2's turns
(17.3% v 9.5% random) and the only prec±60 above random there (29.1% v 25.8%).** If the next arm is
about shortening lag, this is where to start.

### #5 — `stall_15m_180min` · **REFUTED as an entry — and it was the lead hypothesis**

15-minute bars; declare the leg over when there has been **no new extreme for 12 closed bars (180
min)** — no giveback, no points, no velocity — and enter the other way. 3.05 fires/session · 49.7%
long; edges +2.9/+2.4/+8.8/+5.9pp with ±150 the one clustered-significant cell [+0.2,+16.9].

**It fails on five independent counts**, and this is the most important negative result in the arm
because the correction named it as the single most promising feature available:

1. **Parameter neighbours disagree** — the same stall at 90min and 120min windows is flat-to-negative
   on 5m, 15m, 30m and 60m bars alike.
2. **Its cross-timeframe corroboration is not independent.** `stall_5m_180min` (+4.4/+1.7/+7.2/+4.9)
   is the *same 180-minute wall-clock rule* at a different granularity — 36 bars instead of 12.
   [[agreement-is-not-independence]].
3. **The halves collapse** — ±150 goes 13.3 → 3.5, ±200 goes 14.8 → −0.0.
4. **Its detection is the worst in §5.1** — recall60 **3.9% against a rate-matched random 6.5%**. A
   time-stall does not locate turns; it locates the end of the *next* leg.
5. **Arm 2 found the same thing independently** — a bare stall raced at 49.2%, a coin.

**Mechanism, and why it was always going to fail:** §4.2 shows the median turn is already 1×ATR15
away after **6-8 minutes**. A rule that waits **180 minutes of silence** before speaking cannot be a
turn detector — by then the next leg is over. The feature is not wrong about the market; it is wrong
about the clock.

### Also measured, and REFUTED

| | |
|---|---|
| **OLS slope sign crossing zero**, no magnitude floor, 1-3 bar persistence, 5m-60m, 30-180min windows (60 configs screened) | +1.9pp at best; `slope_30m_L120min_p3` −1.8 to −4.9pp. Removing the magnitude floor — the explicit instruction, and the right call — changed nothing |
| **STALL + SLOPE agreeing**, no magnitude anywhere (16 configs) | +0.4 to +2.5pp, every CI spanning zero, ±200 halves +16.3 → −5.9 |
| **Efficiency-ratio crossing a threshold** (0.4 / 0.55 / 0.7; 36 configs) | −4.6 to +3.1pp, no coherent sign by timeframe or threshold |
| **Join-the-break structure at 30m and 60m** | Coherently **NEGATIVE** to −15.8pp. Replicates [[break-then-join-direction-is-a-coin]]. Do not build it |
| **Trailing-ER conditioning** (low/mid/high × 5 detectors) | Three different answers from five detectors. §3.5 |
| **Conjunctions of the two best detectors** (8 configs) | All **below 3 fires/session** (0.74-2.60) — rejected on the brief's gate; W=30 and W=60 of the same pair disagree by 16pp at ±200. §3.6 |
| **The whole 322-cell quiet-family surface** | mean edge −0.72pp, z sd 0.946, positive tail 1.2% against H₀'s 2.5%. §3.1 |

---

## 7. WHAT THIS ARM BANKS

**Five results worth carrying out of here. None of them is an entry signal.**

1. **Resampling fixes fire rate and nothing else.** 116 of 212 configs land in 2-8 fires/session at
   coarse scale against 20-90/session at 1m; the direction call is unchanged across 476 cells (mean
   edge −0.72pp, noise-calibrated). **The brief's hypothesis — "hopeless at 1m becomes tradeable at
   15-30m purely because of sampling" — is refuted, and specifically: it was the COUNTING that was
   broken at 1m, not the discrimination.**
2. **⚠ THE SIDE-ARTEFACT IS REAL, BIGGER THAN REPORTED, AND POINTS THE OTHER WAY.** This tape **rose
   +6,696.8pt** over the window and **SHORT still wins the symmetric race 57.2% to 42.8% at ±200pt**,
   because a race rewards the faster tail (DOWN p99 178.0pt vs UP 164.8pt) rather than the sum. So on
   these sessions a **SHORT**-biased rule collects up to **+14.4pp** free — ~3× arm 2's 5pp, and the
   opposite sign to the one inferred from net drift. **No arm should infer this artefact's direction
   from a drift figure; it has to be measured on the actual race definition, once, and shared.**
3. **★ THE SPLIT HE ASKED FOR IS THRESHOLD-DEPENDENT, AND THAT IS THE ANSWER.** At ≥1.5×ATR15 within
   30 minutes, **64-74% of real turns are VIOLENT**; at ≥2.0×ATR15, **47-58% are QUIET**. The quiet
   share *shrinks* with leg size (41.0% at a 75pt ZigZag → 26.3% at 150pt), so **quiet is the
   minority among the legs he actually wants**. His description is nonetheless accurate about the
   *body* of a leg — median new-leg ER is **0.3** — so the shape is fast off the pivot and grinding
   thereafter, and quiet turns grind **75% longer** for the same distance. Unambiguous either way:
   the median turn is 1×ATR15 away after **6-8 minutes**.
4. **★★★ THE FAULT IS CONFIRMATION LAG.** Not one detector in this arm — any timeframe, quiet or
   violent family, under **either** turn definition — beats a rate-matched random detector on
   prec±30. The shipped `retrace_15×ATR` rule scores **3.1% against random's 9.4%** (and 1.9% v
   13.0% on arm 2's turns), sees 7.3% of real turns within an hour, never sees 39.6% inside four
   hours, and is a median **114 minutes** late against a median **89-minute** leg. **Coarser bars make
   this worse.** If one thing gets built from this study it should be an attempt to name a turn inside
   its first 15 minutes, accepting far worse precision in exchange for arriving while the move is
   still there — starting from `struct_15m_p3`, the shortest-lag detector on the board.
5. **Two cross-arm discrepancies to reconcile, not average.** 273 sessions here under six counting
   definitions against arm 2's 328; and 5.88 turns/session from arm 2's own ±90min/60pt pivot
   definition against its reported 3.96. The ratios are similar, which points at one shared cause —
   most likely the session window or session set. **Both arms' per-session rates are incomparable
   until that is settled.**

> **Status of every lead, per the standing rule.** `donch_5m_180min` → **SHADOW** (±50). ·
> `netdir_60m_180min` → **SHADOW** (±100). · `structboth_5m_p4` → **PARKED**, revive only with a
> mechanism for the pivot width. · `struct_15m_p3` → **PARKED on the race, LEAD on lag.** ·
> `stall_*`, `slope_*`, `stallslope_*`, `ercross_*`, trailing-ER conditioning, conjunctions,
> join-the-break at 30-60m → **REFUTED**. · **Short-lag turn detection → the open lead, and the one
> this arm recommends.**

---

### Reproduction

Working scripts in the session scratchpad: `arm4_lib.py` (loader / resampler / race),
`arm4_sigs.py` (detectors), `arm4_screen.py`, `arm4_score2.py`, `arm4_neigh.py`, `arm4_robust.py`,
`arm4_quiet.py`, `arm4_detect.py`, `arm4_calib.py`, `arm4_calib2.py`, `arm4_src.py`, `arm4_arm2.py`,
`arm4_recon.py`, `diag_race.py`. The race convention matches `scripts/entry_cvd_climax.race` so arms
stay comparable; `arm4_lib.race` differs only in reading a 4-tuple minute row.

**Nothing in this arm wrote to `gazbot7.db`, `capture.db` or any switch, request or state file,
placed an order, POSTed to `/api/control`, or restarted a service. The only file written is this
report.**
