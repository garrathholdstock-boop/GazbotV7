# ARM 1 — MINE THE OPERATOR'S OWN PRESSES

**Greenfield entry study, 2026-10-02. READ-ONLY throughout: no order, no POST to `/api/control`, no
service restarted, nothing written to `data/gazbot7.db` or `capture.db`.** Working scripts live in
the session scratchpad; this file is the only thing written in the repo.

> ### ⚠ RE-DERIVED AFTER THE SHARED-LOADER BUG REPORT — what changed and what did not
> **Bugs 1 and 2 never reached this arm, and that is verified rather than assumed.** I did not call
> `entry_cvd_climax.load()`; I wrote a separate loader because I had independently found both faults
> (the missing `timeframe` filter and the rounding `CAST`) while building it. Cross-checked against
> the fixed loader: **82,087 overlapping minutes across all 61 common sessions, 0 differences in
> high, low or close.** My minute ranges are sane (median 10.25pt, p99 51.2pt, 57 of 102,263 minutes
> above 100pt) — no `1day` bar was ever folded into a minute here.
> **Bug 3 (ambiguous bar) differed in my favour and is now fixed to match:** my `race` scored an
> ambiguous bar **0** (a loss), the opposite bias to the shared loader's win; it now returns `None`
> and is excluded. **205 of 418,352 race evaluations excluded = 0.049%** — immaterial either way.
> **Bug 4 (the control) is the one that mattered, and it changed the conclusions.** Every number
> below is now scored against a **side-matched control averaged over 20 independent draws**, with
> the across-draw SD printed, *and* against the 50% break-even. **The arm's headline candidate did
> not survive it.** Pre-fix, the thrust-join rule read +3.6pp / +6.5pp; side-matched it reads
> **+0.7pp / +0.6pp.** The whole thing was the random-side control.
> ⚠ One correction to the correction: a **random-side control at a symmetric race is pinned to
> ~50% by construction**, not biased by drift — for a fixed minute, long wins iff short loses, so
> the two are complementary and a random side averages to exactly 50% (measured: 46.5-53.9% across
> every cell here). Tape drift shows up as **the rule scoring above 50 just for being long**, not as
> a biased control. The side-matched control is still the right instrument — it isolates *timing*
> from *side* — but its absolute level (35-55% here) is a drift reading, so I report rule-vs-50
> alongside it. **The practical break-even on a symmetric race is 50%, not the control.**

---

## THE ONE-LINE ANSWER

**Nothing in this arm clears the bar, and the reason is measurable rather than circumstantial: his
own presses score +0.2pp at ±50 and −2.1pp at ±100 against a side-matched control.** His entries are
a coin on this verdict, so the arm has a ceiling of zero and no rule distilled from his presses can
beat it. Of ~600 verdict cells, exactly two excluded the 50% break-even on a session-clustered CI,
and both belong to one rule that a window-shift scan then refuted.

**What does stand is a behavioural result, and it is the first of its kind on this desk.** Measured
against time-of-day-matched negatives with **no outcome data involved at all**, I can now say
precisely what he is looking at: **he joins a 15-minute thrust.** Signed `net15/ATR` separates his
press minutes from matched non-press minutes at **AUC 0.733 [0.686, 0.789]**, stable at 0.67-0.77
across twelve different negative-sampling choices. And the mirror finding is the useful one:
**his CLAIM instinct scores far better than his entry instinct** — reversing his claims is the
strongest cell in the arm, which says his skill lives in recognising exhaustion, not in picking
entries.

---

## 1. THE DATA, AND WHAT IT ACTUALLY CONTAINS

`data/operator_reads.jsonl`, 489 snapshots, 2026-09-14 → 2026-10-02 (15 calendar sessions).

| kind | rows | what it is |
|---|---|---|
| `buy` | 236 | the BUY/SELL button — **an ENTRY, and the request carries his SIDE** (`…|BUY|4|1`) |
| `claim` | 244 | the Claim button — an exit; the request carries **no side** |
| `pass` | 9 | the PASS button, incl. one labelled `BUTTON AUDIT - not a real pass` |

- 59 request keys appear twice — the capture fires on both the `-buy.path` and the `-claim.path`
  unit for one write. Deduped on `(side, within 300s)` → **187 entry presses over 14 sessions =
  13.4/session**, 95 BUY / 92 SELL. 7 `buy` rows carry `request: {}` (the known `ExecStartPre` race)
  and are dropped, not guessed.
- `drift` is present in 249 of 489 rows and `drift_error` in 240, so **the drift field is unusable
  as a feature** across the set.
- **The snapshot holds no CVD and no volume.** So I did not model from the snapshot: I used the
  press **timestamps as labels** and rebuilt every feature causally from the lake. One consequence
  worth having — the same feature code scores his presses and scores every candidate rule, so the
  two cannot silently disagree.
- 186 of 187 presses match an entry in `research_entries` within +180s; over those 14 sessions his
  clean-fill entry P&L is **−$33.23/entry (96 winners / 90 losers)**. That is not the +$117.65/entry
  in the brief, which must be a different window or filter — flagged rather than reconciled, since
  this arm's verdict is the race.
- Tape: **76 sessions** of 1-minute bars aggregated from the lake's `5s` bars (2026-06-19 →
  2026-10-02). **62 contain no press at all and serve as a time holdout.** CVD (from `ticks.aggressor`,
  lowercase) exists for 61 of the 76; the 15 oldest have price but no aggressor, and their CVD gauge
  correctly returns `None` rather than a flat zero.

### ⚠ THE LIMIT THAT BOUNDS EVERY NUMBER IN SECTION 2
There are **zero recorded instances of him looking at the tape and deciding not to press.** A
sampled negative minute is "a minute with no press" — which includes every minute he was asleep, in
a meeting, or already holding. It is **not** "a minute he rejected". So section 2 measures *what the
tape looks like when he is at the desk and acts*; it cannot measure his judgement against the
alternative he declined. `scripts/presence.py` already holds the missing class (nginx distinguishes
a phone burst = **LOOKED**, strong, from a desktop poll = **DASHBOARD-OPEN**, weak and possibly an
idle tab; 11 of the 16 alerts he ignored in the week to 09-18 fired while he was demonstrably
looking). **Joining presence sessions to press times is the single highest-value addition to this
dataset and needs no new instrument.**

---

## 2. WHAT DISTINGUISHES THE MINUTES HE PRESSED — the result that stands

**Negatives:** for each press, 12 random minutes from the **same session** within ±45 clock-minutes,
at least 10 minutes from any press — time-of-day matched so this cannot rediscover "he trades at
14:30". 187 positives / 2,148 negatives. Signed features are multiplied by the side he took, so
"+2.24" means *2.24 ATR in the direction he went*. **No outcome data anywhere in this table.**
Intervals are session-clustered bootstraps over the 14 sessions, because a per-observation interval
on minutes inside a session is inflated ~10×.

| feature (in HIS direction) | his median | matched median | AUC | 95% clustered |
|---|---|---|---|---|
| **`net15` move / ATR** | **+2.24** | **+0.20** | **0.733** | **[0.686, 0.789]** |
| `net30` move / ATR | +2.83 | +0.81 | 0.652 | [0.609, 0.696] |
| `rvol` (last 5min vs trailing 60) | 1.16 | 0.90 | 0.623 | [0.586, 0.657] |
| `ER30` (efficiency ratio) | 0.20 | 0.17 | 0.601 | [0.544, 0.656] |
| `ER60` | 0.16 | 0.12 | 0.585 | [0.536, 0.634] |
| `net60` / ATR | +3.48 | +1.57 | 0.580 | [0.548, 0.615] |
| CVD gauge (0-100, his direction) | 74.5 | 62.4 | 0.579 | [0.560, 0.609] |
| `pos_in_range` (his direction) | 0.67 | 0.64 | 0.570 | [0.550, 0.601] |
| VWAP stretch / ATR (his direction) | +2.91 | +2.37 | 0.540 | [0.525, 0.563] |

**The same features UNSIGNED are all 0.46-0.53.** That is the load-bearing row: it is not that he
presses when the tape is busy, it is that he presses **with** a specific recent direction. ATR itself
(0.527), session range in ATR (0.462), extreme age (0.481) and unsigned `pos_in_range` (0.499)
separate nothing at all.

**Sensitivity:** signed `net15` AUC across match windows ±30/45/90/180 min × press-exclusion gaps
0/10/30 min = **0.674 … 0.769**, twelve cells, every one clear of 0.5.

**Stated as a rule:** *he buys when the last 15 minutes have run ~2.2 ATR his way on volume ~1.16×
the trailing hour, with price ~0.67 up the session range and CVD pinned ~75 in his direction.* He is
a **15-minute thrust joiner** who presses **with** the aggression — the exact inverse of the shipped
`cvd_climax` roll-off trigger, which fades a pinned gauge.

**15% of his presses go the other way.** The 10th percentile of signed `net15` is **−1.15 ATR**:
33 of 187 presses (18%) were taken *against* the 15-minute line. That subset is shortlist item #2.

### What he is looking at when he CLAIMS (same method, 185 claims, 31 cells)
| feature | claim median | matched median | AUC | 95% clustered |
|---|---|---|---|---|
| `ER30` | 0.23 | 0.16 | 0.636 | [0.583, 0.683] |
| `rvol` | 1.12 | 0.90 | 0.630 | [0.578, 0.690] |
| `net30`/ATR, his direction | **+2.13** | +0.57 | 0.597 | [0.563, 0.622] |
| `net60`/ATR, his direction | +3.26 | +1.61 | 0.562 | [0.531, 0.583] |
| `net15`/ATR, his direction | **+0.62** | +0.33 | 0.530 | [0.489, 0.561] |

Read the last two rows together: when he claims, the **30-minute move is still 2.1 ATR his way but
the 15-minute move has collapsed to 0.62 ATR.** The run is intact and the last quarter-hour has
stopped paying — a deceleration signature, and a precisely implementable one. Tested as an entry
(#5) it is a null, which is the interesting part.

---

## 3. THE CEILING — the most important measurement in this arm

His own presses, his own side, on the arm's verdict. Side-matched control = 20 draws, same session,
same side, random minute in the same 05:00-20:00Z window; `±` is the SD *across draws*.

| arm | fires/sess | tgt | rule | n | side-matched ctrl | edge | 95% clustered | rule's own CI | random-side ctrl |
|---|---|---|---|---|---|---|---|---|---|
| **his 187 presses, his side** | 13.4 | ±50 | **52.3%** | 174 | 52.1% ±3.73 | **+0.2pp** | [−5.1, +6.7] | [46.9, 59.3] | 50.6% |
| | | ±100 | **50.9%** | 106 | 53.0% ±3.21 | **−2.1pp** | [−8.6, +7.6] | [43.4, 62.4] | 50.3% |
| the same, side flipped | 13.4 | ±50 | 47.7% | 174 | 47.6% ±3.19 | +0.1pp | [−5.4, +4.2] | — | 49.6% |
| his 185 claims, reversed | 13.2 | ±100 | **57.4%** | 101 | 47.6% ±5.54 | **+9.8pp** | **[+1.8, +18.2]** | [47.5, 65.6] | 51.2% |

His presses' long/short split is 50.8%/49.2%, so the side-matched and random-side controls agree, as
they must for a balanced rule. **+0.2pp and −2.1pp, with the rule's own clustered CI straddling 50
at both targets. The ceiling is zero.**

**Three consequences, and they bound the whole study:**

1. **No rule that reproduces his presses can beat this verdict**, because the thing being reproduced
   does not. Any candidate scoring well above zero is scoring on a *subset* of his behaviour, and a
   subset of a coin is where this desk's 119 failed calibrations live. Section 4 #3 is that exact
   failure caught in the act.
2. **His +$/entry is therefore not an entry edge on a symmetric payoff.** A ±50 race is symmetric;
   his book is not — four lots banking 50/100/200/300 with no stop and a 20:40Z flat is asymmetric,
   and `[[payoff-asymmetry-is-the-only-thing-a-hit-rate-hides]]` is precisely about where a 0.50 hit
   rate still pays. **The money is in the holding, not the entering** — consistent with
   `[[exits-are-exit-proof]]`, `[[the-operators-hands-are-the-exit]]`, and CLAUDE.md's own hold-time
   table (1-4h holds +$86/entry vs −$27 under 15 min).
3. **And the claim row is the signpost.** Reversing his claims scores +9.8pp against a side-matched
   control with a CI excluding zero, while his entries score zero. **His exit instinct carries
   information his entry instinct does not.** For the other three arms: the exhaustion/turn family
   is where this dataset points, and **+0.2pp is the empirical ceiling of "copy the human's entry"** —
   treat anything much above it at n~300 as a search artefact until it survives a window-shift test.

---

## 4. THE RANKED SHORTLIST

Verdict standard applied identically everywhere: **3-6 fires/session** (20+ is rejected on rate
regardless of accuracy) · **symmetric race** at ±50 and ±100 within 120 min on bar highs/lows ·
ambiguous bars excluded · **side-matched control, 20 draws** · every interval a **session-clustered
bootstrap** · and **rule-vs-50%, because 50% is the actual break-even on a symmetric race.**

### #1 · THE CLAIM-REVERSE AT EXTENSION — *closest to the bar; PROMISING, shadow it*
> **Rule as measured.** When he presses Claim on a live position **and** price is more than **3 ATR
> past session VWAP in the direction the position was making money**, enter the **opposite** way.
>
> **6.1 fires/session** (85 fires / 14 sessions) · long/short 47%/53%
> ±50: **53.9%** n=76 · side-matched ctrl 43.0% ±5.06 · **edge +11.0pp [+3.9, +17.8]** · random-side
> ctrl 47.3% · **rule's own CI [41.8, 63.9]**
> ±100: **63.0%** n=46 · side-matched ctrl 43.2% ±8.21 · **edge +19.9pp [+11.0, +31.2]** ·
> random-side ctrl 49.7% · **rule's own CI [44.9, 77.8]**
> Leave-one-session-out on the ±100 cell: **+18.0 to +25.4pp across all 14 drops — no single session
> carries it.** Variant "claim + price in the top/bottom 15% of the session range" (3.8/session):
> ±100 57.6%, edge +22.1pp [+6.3, +36.5], n=33.
>
> **Mechanism (one sentence).** His exit instinct marks exhaustion, and an exhausted extension is a
> reversal entry — the same family as `entry_cvd_climax`, which is the only prior non-coin entry
> evidence on this desk.
>
> **⚠ Why this is PROMISING and not PROVEN, in order of severity.**
> 1. **The rule's own CI contains 50 at both targets** ([41.8, 63.9] and [44.9, 77.8]). Against the
>    side-matched control it is unambiguous; against the break-even that actually pays, 14 sessions
>    is not enough. The honest point estimate is **+3.9pp at ±50 and +13.0pp at ±100 over
>    break-even**, with 46 resolved observations at ±100.
> 2. **The side-matched control sits at 43%, a long way below 50**, because the 14 press sessions
>    rose **+1,539pt (+110/session)** while the full 76-session tape was flat (−2.5/session). So part
>    of the +19.9pp is "his side at a random minute in those sessions loses" — a drift reading, not
>    skill. Both controls still point the same way, which is why it ranks first.
> 3. **It is not automatic.** It needs *him* to press. My attempt at a mechanical detector for the
>    same pattern is #5, and it is a null — so the automatable version of this rule does not yet
>    exist. That, not more slicing, is the next step.
> 4. The slicing that should have helped is inconsistent: claims taken **in profit** give +11.1pp /
>    +14.8pp but claims with **more than +25pt of profit** gave **−7.1pp** at ±50 pre-fix on n=60,
>    and the CVD-pinned slice gives +3.6pp / +10.7pp with CIs through zero. At these n the slices
>    are not distinguishable from each other.

### #2 · THE AGAINST-THE-LINE VETO — *not an entry; the cheapest actionable thing in the dataset*
> **Finding.** His presses split by whether he went with or against the 15-minute line:
> **WITH (154 presses): 53.8%**, side-matched edge +1.5pp [−4.8, +9.0], n=145.
> **AGAINST (33 presses): 44.8%**, side-matched edge −4.9pp [−16.6, +10.5], n=29 — ±100 has n=12 and
> is not scored.
> 2σ at n=29 is ±18pp, so the *difference* is suggestive, not established. But it agrees
> independently with CLAUDE.md's own 2026-09-28 record — **19 entries with the prevailing line
> +$1,010, 4 against it −$2,892** — and with `[[the-five-worst-trades-share-one-behaviour]]`.
>
> **Mechanism.** He is a thrust joiner (section 2). The 18% of presses where he overrides his own
> trigger and fades are the ones that cost money.
>
> **⚠ What this is.** A **veto**, not an entry — it fires 0 times a session on its own and cannot be
> scored on the fires/session bar. It needs no new instrument (`net15/ATR` is computed everywhere
> already), it is reversible, and it would have flagged 18% of his presses. **Worth trialling as a
> dashboard colour long before it is ever a block.** ⚠ The split was chosen after seeing the data and
> n=33 on the against side; treat as PROMISING, not established.

### #3 · THE THRUST JOIN — *REFUTED by the control fix, and by its own ablation*
> **Rule.** 05:00-20:00Z, `x = (close − close[30min ago]) / ATR14`; arm below 2.83, fire on the first
> armed minute with `|x| ≥ 2.83` **and** `rvol ≥ 1.16` **and** `ER30 ≥ 0.20`, in the direction of
> `x`, one fire per 180 min. **4.61 fires/session**, long/short 45%/55%.
>
> | | ±50 | ±100 |
> |---|---|---|
> | rule | 54.5% (n=303) | 55.9% (n=161) |
> | **side-matched ctrl** | 53.7% ±2.43 | 55.3% ±3.92 |
> | **edge (side-matched)** | **+0.7pp [−5.0, +6.6]** | **+0.6pp [−6.7, +7.8]** |
> | edge (random-side, the brief's spec) | +5.7pp | +6.2pp |
> | holdout, 62 sessions, side-matched | +2.5pp [−4.0, +9.1] | +2.1pp [−5.6, +10.0] |
>
> **This was the arm's headline before the control was fixed** (+3.6pp / +6.5pp). Side-matched it is
> nothing, and the gap between the two control specs is the whole of the former result. Its own
> ablations said the same thing independently: drop the cooldown and it fires 21.7/session for
> **−3.1pp [−6.4, −0.1]** at ±50; keep the cooldown but drop the thrust to `net30 ≥ 1.0` and it
> **still** scores +2.1pp / +3.6pp. A 240-minute cooldown in a 900-minute window yields ~3.7 fires
> whatever the threshold is, so **the cooled rule is a subset of a flat population and the threshold
> was never doing any work.** REFUTED on mechanism as well as on measurement.

### #4 · THE FIRST-THRUST-OF-THE-SESSION RULE — *the only cells that beat break-even, and still REFUTED*
> **Rule.** Take only the **first 1-3** fresh ≥2.83-ATR 30-minute thrusts after 05:00Z, joined.
> ranks 1-3: 3.0/session, ±50 **60.1%** n=208, side-matched edge +7.9pp [−0.2, +15.8], **rule's own
> CI [51.7, 68.4] — excludes 50**.
> rank 1 alone: 1.0/session, ±50 **64.7%** n=68, edge +12.4pp [+1.9, +23.4], **CI [52.9, 75.8]**;
> ±100 **69.0%** n=29, **CI [51.9, 85.7]**. Threshold-insensitive from 2.0 to 4.5 ATR.
>
> **These are the only two cells in ~600 whose clustered CI excludes the 50% break-even. They are
> still refuted, by two tests:**
> 1. **The full population is flat.** Every fresh ≥2.83-ATR 30-min thrust in 05-20Z is 4,226 fires
>    (55.6/session) at **+0.6pp [−1.7, +2.9]** (n=3,758, pre-fix control). By rank: 1 → +16.0pp,
>    2 → +8.6, 3 → +6.9, 4-5 → +8.0, and **6+ → −1.1pp on n=3,412.**
> 2. **It is pinned to a number I chose.** Rank 1 fires at a median **05:01Z** — the edge of the
>    05:00-20:00Z window I took from his press histogram. Re-running "the first fresh ≥2.83-ATR
>    30-min thrust after H:00Z" for H = 0…14 (one draw per session, n=50-75 each, side-matched):
>    −8.0, −7.4, +7.6, +8.6, +3.9, **+13.6**, +0.8, −1.9, −6.3, +2.3, −8.6, −0.6, +1.3, −2.0, −4.7pp.
>    **Mean +(−0.1)pp. The effect exists at exactly one window start.** An unconditional hourly scan
>    (21 hours × 3 lookbacks = 63 specs) says the same: −25.6pp to +37.2pp with no structure, and
>    05:00Z/L=30 itself scores **+0.1pp**.
>
> **REFUTED — its mechanism is broken.** Recorded in full because it is the shape of the trap: a
> candidate passed a threshold-robustness scan, a session-clustered CI excluding break-even, *and* a
> 62-session holdout, and was still an artefact of a window boundary. **Any arm reporting a rule that
> fires ≤6 times a session should be made to pass a window-shift scan before it is believed.**

### #5 · THE CLAIM-STALL REVERSAL — *REFUTED; the mechanical proxy for #1 does not work*
> **Rule.** 05:00-20:00Z, `|net30| ≥ 3.0` ATR but the last 15 min has given back to `≤ 0.5` ATR
> (his claim signature from section 2) → enter **opposite**, one fire per 240 min. **3.7/session.**
> ±50 48.2% (n=251), side-matched edge +0.7pp [−5.7, +7.2], own CI [42.0, 54.3].
> ±100 47.3% (n=131), edge +1.3pp [−5.8, +8.9], own CI [39.7, 55.1].
> The same minutes **joined** instead: +0.4pp / +1.7pp — also nothing. Adding the VWAP extension
> (`≥2 ATR`) makes the reversal worse (44.1% at ±50). Eight parameter cells span −4.9 to +1.3pp
> pre-fix and the holdout agrees.
>
> **This is the informative null in the arm.** It is my mechanical attempt at #1 — the same family,
> the same conditions, built from his own claim-minute medians — and it is flat. So what #1 contains
> is **not** "fade an extended, stalled 30-minute move"; it is his selection of *which* extended
> stall. Closing that gap is the named next step, and until it closes #1 is not a signal.

### Did not reach the bar at all
- **Reproduce his presses wholesale** — 13.4/session (rejected on rate) and the ceiling is +0.2pp.
- **`net15` thrust-join** (vs `net30`): the filtered `cool180` variant swings +4.5pp at ±50 and
  **−3.1pp** at ±100 on the same 288/163 fires — a sign flip across targets on one fire set, which
  is what noise looks like.
- **Longer-line alignment as a filter** (require `net60` or `net120` also aligned): 4 cells,
  +2.0 to +3.7pp pre-fix, every CI through zero, no improvement on #3.
- **CVD-pinned claim reversal:** +3.6pp / +10.7pp, CIs through zero (n=56/32), and it is *worse* than
  the plain VWAP-extension version — so the CVD half of the operator's stated rule adds nothing here.
- **His presses while already holding** — 0 of 187 carry a live position in the snapshot, so the
  known BUY-while-holding bug has no labelled examples in this dataset.

---

## 5. THE SEARCH, CHARGED

| step | rule specs | verdict cells (×2 targets) |
|---|---|---|
| press discovery (no outcome) | 35 features | — |
| claim discovery (no outcome) | 31 features | — |
| ceiling (presses, flipped, claims) | 3 | 6 |
| thrust join/fade scan | 60 (**30 independent** — FADE is the arithmetic complement of JOIN, not a second test) | 120 |
| clone at 3-6/session + holdout | 20 | 40 |
| matched-control + ablations | 14 | 28 |
| rank / gap decomposition | 20 | 40 |
| first-thrust robustness + clock-matched control + holdout | 14 | 28 |
| unconditional hourly scan | 63 | 126 |
| window-start scan (pre-fix) | 15 | 30 |
| claim-reverse conditionals + press subsets | 15 | 30 |
| claim-stall reversal | 12 | 24 |
| **re-derivation under the fixed race + side-matched control** | 40 | 80 |
| **window-start scan, re-derived** | 15 | 15 |
| **rule-vs-50 clustered CIs** | 12 | 24 |
| **total** | **~303 specs** | **~591 verdict cells** |

Plus 66 discovery cells that used no outcome data. **At ~591 verdict cells, roughly 15 should clear
2σ by chance alone** — `[[charge-the-search-and-then-charge-the-bar]]`: 5,026 specs once reproduced a
published t=5.83 from pure noise 13% of the time on this desk. **Two cells excluded the 50%
break-even, both from the one rule that the window-shift scan refutes.** That is what a null looks
like when the search is counted honestly.

---

## 6. METHOD NOTES

Reused from `entry_cvd_climax`: the 180-minute rolling CVD `gauge`, the `race` shape and the
120-minute window, so this arm scores the same object the other arms do. **Not reused: `load()`** —
I wrote a `timeframe='5s'`-only loader with Python/DuckDB integer floor division, which is why bugs 1
and 2 did not reach these numbers (verified bit-identical to the fixed loader on 82,087 minutes).
A note for whoever next touches the loader: I hit the DuckDB float-division trap myself on my first
attempt (`ts_ms/60000` as a float grouped every tick into its own minute and produced 16,555
"minutes" per session) — the symptom is loud if you print the session length, and silent otherwise.

- **Why both controls are reported.** A random-side control at a symmetric race is pinned to ~50% by
  symmetry (long wins iff short loses), so it measures nothing about side and is effectively the
  break-even reference; a side-matched control at random minutes inherits the session's drift and so
  isolates *timing* from *side*. They answer different questions and the honest cell shows both plus
  the rule's own CI.
- **Control stability.** 20 draws per cell; across-draw SD is printed in every row and runs
  **±1.25 to ±11.20pp** — on the small cells the draw spread alone is bigger than the edge, which is
  exactly the coordinator's point and the reason single-draw controls were discarded.
- **No future bar or peak is read anywhere.** ATR, VWAP, session extremes, ER, rvol and the CVD gauge
  use minutes ≤ i only. The only forward read is the race, which is the verdict.
- `aggressor` compared lowercase (`'buy'`/`'sell'`) — the trap that returns zero rows silently.
- `gazbot7.db` was copied to the scratchpad before reading, because `research_data.connect()` opens
  the live file **writable** to create its views.

---

## 7. WHAT I WOULD DO NEXT, IN ORDER

1. **Build a mechanical detector for #1 and measure the detector.** The claim-reverse at extension is
   the only live thread, and #5 proves the obvious proxy (extended + stalled) does not reproduce it.
   The gap is his *minute selection* inside that family. Until something fires without him, #1 is not
   a signal — and this is a bounded, well-posed piece of work rather than another calibration.
2. **Record the negatives.** `scripts/presence.py` + the nginx log turns this from a one-class
   problem into a two-class one. No new instrument required, and it is the only thing that would
   genuinely raise this arm's power.
3. **Stop looking for his entry edge and go measure his holding.** The ceiling says his entries are a
   coin on a symmetric race while his book is asymmetric. The question with money in it is *which
   50pt he lets run to 200*.
4. **Make the window-shift scan a standing requirement** for any rule firing ≤6 times a session. #4
   would have shipped otherwise, and it passed four other robustness checks first.
5. **And re-run the other arms' positive cells against a side-matched control.** This arm's headline
   lost 85% of its edge to that one change; any arm still quoting a random-side control is quoting a
   number that has not been tested.
