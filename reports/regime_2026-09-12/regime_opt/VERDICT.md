# REGIME-TRANSITION OPTIMISATION — VERDICT

**2026-09-12 · MNQ · PAPER · read-only study · artifacts in `reports/regime_2026-09-12/regime_opt/`**

---

## VERDICT: **REFUTED**

No configuration of the regime-transition entry clears this desk's measured friction stably
across TRAIN, VALIDATE and TEST. **7,092 configurations were searched.** Two cleared all three
of the addendum's bars — and so did a winner selected the same way inside a world where the
state labels had been **rotated away from price**, with numbers that are indistinguishable
from the real one.

### The named test that decided it — the NULL-WORLD GAUNTLET
The same procedure (search 5,040 cells → take the best with n ≥ 250 → three periods, sign-flip
twin, day-block bootstrap) run in six worlds where the fitted state series is rotated by whole
sessions against price:

| world | winning cell | n | net @1.25 | twin edge (sd) | p | day-block 95% CI | clears all 3 bars |
|---|---|---|---|---|---|---|---|
| **REAL** | 30m/3/base_vol/c2/LDN/180m | 268 | **+20.26** | 2.27 | 0.01 | **[+2.11, +38.52]** | **YES** |
| NULL47 | 5m/5/drift/c2/LDN/180m | 294 | **+20.31** | 2.26 | 0.01 | **[+2.77, +38.21]** | **YES** |
| NULL31 | 30m/5/base_vz/c0/LDN/180m | 251 | +20.08 | 1.48 | 0.07 | [−5.32, +48.12] | no |
| NULL−53 | 5m/5/drift/c0/OPEN/180m | 267 | +19.01 | 1.36 | 0.09 | [−4.74, +44.71] | no |
| NULL17 | 15m/5/full/c2/OPEN/180m | 283 | +17.55 | 1.26 | 0.10 | [−3.97, +39.84] | no |
| NULL−37 | 30m/3/base_vz/c0/RTH/150m | 327 | +16.74 | 1.67 | 0.05 | [−2.60, +36.03] | no |
| NULL−23 | 30m/5/base_sp/c0/RTH/180m | 267 | +12.14 | 1.19 | 0.12 | [−7.23, +32.54] | no |

**6 of 6 null winners are positive in all three periods. 1 of 6 clears all three bars.** The real
winner is the seventh draw from that distribution, not an outlier of it. `tables/null_gauntlet.csv`

---

**Reproduction anchor.** `scripts/regimelab.py` is the successor to `scripts/bt_regime_transition.py`
and reproduces it exactly where they overlap: identical TRAIN state table (shares 25.5/55.8/18.6%,
mean bar returns +10.37/+0.62/−14.93, d8 +2.32/+0.02/−2.61) and per-cell means within 0.2 pt.
Differences from the incumbent are deliberate and documented in the module: TRAIN-only feature
standardisation, best-of-four EM starts by log-likelihood, states named from their own TRAIN drift
statistic rather than from bar returns, and a vectorised entry path asserted against the loop.

## 1 · WHY THIS DESIGN CANNOT CONCLUDE — the power floor (run this before any sweep)

One trade's spread against the edge being hunted. 15-min / 3-state / base features:

| hold | n | gross edge (pt) | gross sd (pt) | **min detectable edge @95%** | n needed to see 1.5 pt |
|---|---|---|---|---|---|
| 30m | 2,059 | +0.53 | 50.7 | **±2.19** | 4,389 |
| 60m | 2,000 | +1.49 | 72.7 | **±3.18** | 9,012 |
| 90m | 1,961 | +1.73 | 88.3 | **±3.91** | 13,299 |
| 180m | 1,830 | +1.70 | 125.6 | **±5.76** | 26,946 |

**Every gross edge this shape produces is between a third and a tenth of the smallest edge the
sample could resolve.** Longer holds are the escape from friction *and* the escape from
statistical power at the same rate — sd grows as √hold while the edge does not. Eleven months of
MNQ is roughly 2,000 transitions; a 1.5-pt edge needs 9,000–27,000. `tables/stage0_power.csv`

## 2 · THE FRICTION CURVE (brief task 1) — net pt/trade, incumbent shape

| hold | clean | 0.75 | 1.00 | **1.25** | 1.50 | 2.00 |
|---|---|---|---|---|---|---|
| 60m | yes | +0.74 | +0.49 | **+0.24** | −0.01 | −0.51 |
| 90m | yes | +0.98 | +0.73 | **+0.48** | +0.23 | −0.27 |
| 120m | yes | −0.04 | −0.29 | **−0.54** | −0.79 | −1.29 |
| 180m | yes | +0.95 | +0.70 | **+0.45** | +0.20 | −0.30 |

Break-even friction = the gross edge: **0.53 to 1.73 pt** across the eight hold cells. So cutting
friction from 2.0 to 1.25 does flip most cells positive (it is worth +0.75 pt to every cell) —
and it changes nothing about whether the cell is real, because **the control pays the same fee**.
`tables/stage0_friction_curve.csv`

## 3 · THE SEARCH (brief tasks 2–7) — 7,092 cells, calibrated against 34,815 null cells

| sweep | real cells | null cells | 3-period screen: REAL | NULL | best net REAL | best net NULL |
|---|---|---|---|---|---|---|
| GRID A — bar × states × features × clean × window × hold | 5,040 | 30,216 | 6.7% | 2.8% | +22.08 | **+23.79** |
| GRID B — vol-z, Markov P, ATR pullback, revert exit | 776 | 4,599 | 33.5%¹ | 5.5% | +25.74 | **+29.37** |
| DWELL arm | 960 | — | — | — | — | — |
| DWELL by block | 221 | — | — | — | — | — |

¹ inflated by construction: GRID B's structures were pre-selected on TRAIN, so `TR > 0` is close
to guaranteed in REAL and not in the nulls. Not evidence.

**In both grids the real search's best cell is INSIDE the null search's best-cell distribution.**
Best t-stat: GRID A real 2.41 vs null max 2.77.

Marginals worth keeping (`logs/grid_a_analysis.txt`): every dimension's *mean* sits near zero and
its *best* sits near 20 pt on 200 trades — the signature of a search reading variance. 30-min bars
and the US-OPEN window score highest purely because they have the fewest trades and the widest
spread. Among the 2,384 cells with **n ≥ 1000** — the only ones with any power — the best gross
edge in the real grid is **+7.75 pt** against **+10.85 pt** in the null grid.

### The one thing that does *not* look like noise
Across those 2,384 n ≥ 1000 cells the real grid's **median gross is +0.24 pt and the null grid's
is −0.54 pt** (means +0.29 vs −0.67), a consistent offset of about **+0.9 pt** that holds across
every bar size and every window. That is a real, tiny, structural edge — **and it is below the
1.25 pt it costs to trade.** It replicates Mesfin's gross-edge ceiling on our own tape rather
than refuting it. It is the study's only surviving positive content, and it is not tradeable.

### Which features the states actually separate on (brief task 4)
`tables/feature_separation.csv`, `tables/label_degeneracy.csv`. Signed drift `d8` dominates
(F ≈ 12,000 at 15-min), then `er8`; `vr` (vol ratio) and `er2` do almost no work (F ≈ 41 and 86).
**But 8 of the 72 fitted models produce DEGENERATE labels** — their "BULLISH" and "BEARISH"
states differ in 8-bar drift by less than 0.5 ATR, because the mixture has clustered on
*efficiency* instead of *direction*. At 5-min bars with the incumbent feature set the gap is
**0.10 ATR** (BULLISH d8 = 0.114, BEARISH d8 = 0.010) while `er4` separates at F = 17,000. Every
5-min "base" cell in GRID A was therefore trading a direction label that carries no direction —
and it reported like any other cell. Check `d8_gap` before believing a state name.

## 4 · THE DWELL ARM (operator instruction, 2026-09-12)

> *"i want to see if we can trade in between the tunnels or regimes. will it use sustained
> efficiency as a trigger?"*

As the code stood: **no**, and it did the opposite. Efficiency was only a GMM *feature*, and
`clean=True` **required the target state to be absent in the prior two bars** — the incumbent
deliberately selects the newest, least-confirmed instance of a state. The dwell arm inverts that:
wait K bars for the state to hold, then enter at the open of bar K+1 (K=1 is the incumbent).

**THE FULL CURVE — STATE arm, tradeable (unmatched), net pt/trade at 1.25:**

| K | dwell forfeited (ATR) | n (30m hold) | 30m | 60m | 90m | 120m |
|---|---|---|---|---|---|---|
| 1 | 0.00 | 2,646 | −0.52 | +0.07 | −0.02 | −0.82 |
| 2 | 0.34 | 1,656 | +0.38 | −0.56 | −1.83 | −1.95 |
| 3 | 0.68 | 1,184 | +0.36 | +0.96 | +0.51 | +0.47 |
| 4 | 1.03 | 910 | +0.61 | +0.47 | −0.32 | −0.96 |
| 5 | 1.40 | 714 | +0.82 | −0.27 | +0.73 | −0.25 |
| 6 | 1.71 | 584 | −0.27 | +0.92 | +0.99 | +1.54 |

**No plateau. No monotone trend. Nothing outside ±2 pt on a per-trade sd of 50–100.** The ER-gated
arms look better at large K (er4 ≥ 0.7, K=4, 90m: **+6.04**) but the neighbours refute them:
K=5 is **−7.81** and K=6 is **−13.18** on the same floor. That is the single-spiking-K pattern the
operator named, with the sign reversing at both neighbours. `tables/dwell_all.csv`

**THE COST OF WAITING — matched (only runs that last 6 bars, the same runs at every K):**

| K | forfeited (ATR) | net pt (90m hold) |
|---|---|---|
| 1 | 0.00 | **+66.21** |
| 2 | 0.49 | +45.50 |
| 3 | 0.89 | +31.79 |
| 4 | 1.25 | +18.81 |
| 5 | 1.53 | +8.98 |
| 6 | 1.72 | **+0.99** |

⚠ **Those levels are NOT P&L** — the matched subset conditions on knowing the run will last six
bars, which is hindsight. They are only valid as a *difference*, and as a difference they are
unambiguous: **−11.02 pt per extra dwell bar**, monotone across all six K and all four holds,
against **+0.34 ATR of the leg surrendered per bar waited**.

> **Dwell is LATENCY, not information.** Same verdict, same mechanism, as the pre-registered
> book-thinning trigger that lost to its own control by $224.75/trade. Waiting for confirmation
> buys nothing here and costs about a third of an ATR per bar.

**THE 2×2 — does sustained ER add to the state, or is the state carrying ER?** (er8 ≥ 0.3)

| | NEITHER (control) | STATE only | ER only | BOTH | ER adds | STATE adds |
|---|---|---|---|---|---|---|
| mean over K=1..6 × 4 holds | **−1.45** | +0.04 | −0.59 | **+0.51** | +0.46 | +1.10 |

The NEITHER control loses, as a control should, and **gets worse with K** — pooled over holds it
runs −0.96 / −0.26 / −0.32 / −2.25 / −2.62 / −2.29 for K = 1..6, stepping down at K = 4. That is
the cost of waiting again, in the cell with no state and no ER filter at all.
Both increments are positive and both are far inside the ±2–3 pt noise band. **Sustained
efficiency does not add a usable trigger on top of the state label.**

**BY SESSION BLOCK** (`tables/dwell_by_block.csv`, 221 cells):

| block | cells | mean net | mean always-long at the same bars | cells clearing all 3 bars |
|---|---|---|---|---|
| ASIA 22:00–08:00 | 72 | −0.53 | +0.37 | 0 |
| LDN 08:00–13:30 | 72 | −1.02 | −1.32 | 2 |
| **USCASH 13:30–20:00** | 72 | **+1.42** | −2.19 | 0 |
| LATE 20:00–21:00 | 5 | +2.59 | −1.47 | 0 |

The dwell arm is least bad in the block the desk actually trades and worst in Asia, which the
desk already benches permanently. The two LDN cells that clear all three bars carry n = 116–122
with TEST at +54 to +58 pt/trade against TRAIN at +3 — a single-period spike on ~30 test trades,
2 out of 221, which is what this screen's own false-positive rate produces.

## 5 · THE CONTROLS — audited, because a broken control decides nothing

A sibling agent measured a shuffled twin scoring **+2.40 pt NET**. A control that makes money is
broken, and the cause is always the same: it trades a different entry population. Measured here
on one fixed cell (15m/3/base, clean 2, 90m):

| control | n | **bar overlap with real** | long % | mean net | |
|---|---|---|---|---|---|
| REAL (the arm) | 1,983 | 100% | 55.0 | +0.80 | |
| **SIGN-FLIP, day-blocked** | 1,983 | **100%** | 48.9 | −2.83 | ✅ decides this study |
| **ALWAYS-LONG, same bars** | 1,983 | **100%** | 100 | −2.65 | ✅ drift baseline |
| LABEL PERMUTATION (5-way) | 1,983–2,646 | **45–100%** | 49.0 | −1.66 | ❌ entry set moves |
| SESSION-SHIFT (×6) | ~1,969 | 10.6% | 55.1 | −1.81 | structural null only |

**The addendum's suspicion about the 5-way permutation is now measured, not argued:** it swings
the entry count from 1,983 to 2,646 (+33%) and one of its five arrangements scores **+1.20 net**.
It is reported for comparison and decides nothing. Everything in this study is decided on the
**sign-flip twin at identical bars**, whose mean is −1.22 ≈ exactly the friction, as an unbiased
control must be. `tables/control_audit.csv`

### The brief's two required controls — both lose, as controls must
`tables/random_entry_control.csv`

| cell | n | real net | random-entry (matched count, random bar, random side) | buy-and-hold |
|---|---|---|---|---|
| 15m/3/base c2 90m | 1,983 | +0.80 | −1.20 ± 1.85 (p = 0.12) | −0.27 |
| 15m/3/base c2 60m | 2,042 | +0.27 | −1.32 ± 1.54 (p = 0.16) | −0.52 |
| 30m/3/base_vol c2 EUUS 180m | 502 | +16.00 | −1.32 ± 5.46 (p = 0.00) | +0.08 |
| 30m/3/base_vol c2 LDN 180m | 268 | +20.26 | −0.36 ± 7.70 (p = 0.00) | +0.08 |

Random entry lands at −1.2 to −1.3, i.e. **exactly the friction**, which is the calibration proof
that the control is unbiased. The two grid winners beat it at p = 0.00 — and so does the winner
picked the same way out of a rotated world, which is the whole point of §"VERDICT".

## 6 · THE BULL-TAPE BASELINE — measured here, and it disagrees with the figure I was handed

A sibling reported a 60-min random-time London long at **+11.25 pt/trade** on this lake. **I do
not reproduce it.** Re-measured on the same front-month tape, every bar in the window, day-block
CI, 1.25 pt friction:

| window | 60m hold | 90m | 180m |
|---|---|---|---|
| LDN | **−0.42** [−3.99, +3.20] | −0.29 | +0.12 |
| USCASH | −1.29 | −1.50 | −0.50 |
| ALL | −0.52 | −0.27 | +0.28 |

The arithmetic says it cannot be +11.25: the tape rises 5,202 pt over 240 sessions = **21.67 pt
per session**, and **755 pt of that is contract basis, not price** (three rolls at +245/+213/+296),
leaving ~18.5 pt of real drift per 23-hour session. A 60-minute slice can carry about **0.8 pt**
of it, which is what I measure. +11.25 pt would be half a session's entire drift captured in one
hour. **This lake does not pay a long for doing nothing on any hold this study uses.**
`tables/drift_baseline.csv`, `tables/roll_basis.csv`

Every headline cell is nonetheless reported against always-long and always-short at its **own**
entry bars (`tables/adjudication.csv`). The LDN survivor fails that test — its +20.26 does not
clear its own always-long upper CI of +21.15. Real-arm long share is 49–57% throughout, so no
cell is a disguised long-only bet.

## 7 · ROLL CONTAMINATION — checked, and clean

Three rolls (2025-12-16, 2026-03-16, 2026-06-14) step the stitched series through **+755 pt** of
basis, and the rolling 4/8-bar drift features **do** cross those boundaries. Effect measured:

| cell | n | entries within ±20 bars of a stitch | net (all) | net (cleaned) | Δ |
|---|---|---|---|---|---|
| 15m/3/base c2 90m | 1,983 | 32 (1.6%) | +0.80 | +1.22 | +0.42 |
| 15m/3/base c2 60m | 2,042 | 33 (1.6%) | +0.27 | +0.58 | +0.31 |
| 30m/3/base_vol c2 EUUS 180m | 502 | 10 (2.0%) | +16.00 | +16.67 | +0.67 |
| 30m/3/base_vol c2 LDN 180m | 268 | 5 (1.9%) | +20.26 | +20.09 | −0.17 |

**Nothing here rests on a roll.** `tables/roll_robustness.csv`

---

## WHAT IS AND IS NOT CLOSED

**CLOSED — do not re-derive.**
- The regime-transition entry with a fixed long hold, over bar sizes 5/10/15/30, state counts
  3/4/5, eight feature sets, four clean-transition depths, five session windows, holds 30–180 min,
  volume-z and Markov-transition-probability filters, ATR pullback entry and state-reversion exit:
  **7,092 configurations, none tradeable.** Best gross edge on any cell with real power: +7.75 pt
  against a null-world best of +10.85 pt.
- **Dwell / sustained-efficiency as a TRIGGER: REFUTED.** −11.02 pt per dwell bar on matched runs,
  no plateau in the tradeable curve, and the one good K is flanked by its own sign reversal.
- The 5-way label permutation as a control: **retired**, it moves the entry set by up to 33%.

**PARKED — one glimmer, deliberately not killed.**
The +0.9 pt population-level gross offset between real and rotated worlds looks structural rather
than selected. It is **below the 1.25 pt cost of trading it**, so it cannot be shipped as-is. It
would become interesting only if (a) the same measurement holds on an instrument or hold where
gross scales above ~2.5 pt while friction does not, or (b) the desk's round-trip cost falls below
~0.9 pt. It should not be re-searched on MNQ 15-min bars — that sample is exhausted, and its
power floor (±2.2 to ±5.8 pt) is ten to forty times the effect.

**The structural conclusion, which is not a null.** Mesfin's gross-edge ceiling of ~1.05–1.50 pt
**replicates on our tape at ~+0.9 pt**. Duration was proposed as the escape from a fixed cost, and
it is — but it is also the escape from statistical power, at the same √hold rate. On eleven months
of MNQ the two cancel exactly. **This shape cannot be rescued by better tuning; it needs either a
larger gross move per trade or an order of magnitude more trades.**

---

### Artifacts
`scripts/` regimelab.py (the one audited implementation) · build_tape.py · stage0_friction.py ·
grid_a.py · grid_b.py · analyse_grid.py · dwell.py · dwell_blocks.py · adjudicate.py ·
null_gauntlet.py · control_audit.py · drift_baseline.py · roll_check.py · features_report.py ·
hygiene.py · random-entry&buy-hold control run in `logs/random_entry_control.txt`
`tables/` 22 CSVs · `logs/` 18 run logs (every table in this document is reproducible from them)
