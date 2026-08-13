# WEEKEND 2026-08-08 — what changed, and what got withdrawn

> **Read the withdrawals first.** This weekend's pattern is not "five ideas, one survived" like 08-01.
> It is narrower and more uncomfortable: **almost everything that broke this week was an instrument,
> not a strategy.** A journal that recorded half the config. A sweep that never read the flag it was
> writing. A shadow board whose ceiling disagreed in sign with its own repricer. A report that argued
> for things its own proofread had refuted, because the build was killed before folding them in.
>
> Nothing here should be trusted because it is written down — each item carries the test that survived
> and the caveat that did not.

---

## 1. WITHDRAWN — things that were being acted on and should not be

| Claim | Verdict | What killed it |
|---|---|---|
| **RUN STATE is the primary routing discriminator** (in-run aligned TAKEN = n=34 · 50% · **+$10.34/tr**) | **WITHDRAWN as a routing lever** | Re-derived from scratch on the SAME 89 Mon–Thu trades: n=46 · 41% · **−$1.83/tr**. Armed inside an aligned run the desk made *nothing*. The 34/4/51 split could not be reproduced under **any** run-span definition (merge gaps 0/120/300/600/900s all give an identical 46/10/33). Verdict: *an exit find wearing a router's coat.* ⚠ `CLAUDE.md` asserted this as "★★★ READ IT FIRST" and the durable tick was injecting it into every 5-minute decision. |
| **`abs_veto_short` needs an ER30 ≥ 0.35 arming floor** | **WITHDRAWN — REFUTED** | Keeps **5 of 15** winners, discards **+$1,363** of profitable trades, OOS +$809 → +$363, zero fires in wk29, −$3,863 pooled across nine exits, 77th placebo percentile on winner retention (random expects 3.4/15), a spike not a plateau (0.325/0.35/0.375 = +$849/+$927/+$679), and its own live evidence dies at strip-1 (+$550.50 → +$14.50). It also silently **subsumes and deletes** the BUILDING × US veto rather than adding to it. Killed independently by REV2 Q0 and FIX2, and corroborated a third time in Q2. |
| **grind: "ext ceiling 2.0 → 3.0"** | **CORRECTED — delete it, do not pin 3.0** | Everything from 3.0 up scores identically (+$5,893 / +$6,081 / +$5,981 / +$6,262). There is no optimum to find, so pinning a new literal just re-fits the thing the revert is undoing. Ships as a deletion → falls back to `gate_grind`'s own default of 4.0. |
| **"chandelier: regime-key the width"** (SATURDAY #3, +$3,049) | **REPLACED IN FULL** | It is not a chandelier play and as written could not be typed into any file the desk reads. The edit actually resolves every sub-slot to `exit="scalp"` and leaves **zero** chandeliers in the live slate. Re-issued as `lotb-rung-widen-atrsplit24-0808`. ⚠ Its parameter-plateau test FAILED (4 of 35 cells positive) and two days carry two-thirds of the edge. |
| **`abs_veto_long` needs a US-session guard / a wider Lot B** | **BOTH REFUTED** | The −$258.50 "overnight problem" is an **ASIA** problem, and Asia is already blocked at config level; excluding it the non-US book is **+$0.59/lot all-time**. A US-only guard would bench LONDON, the desk's only positive block. The exit widening: SCALP-CHOP edge is 98% from 2 of 9 days and goes negative on strip-best-3; the MED-TREND "sign flip" is one day. |
| **Wide stops (2×ATR) beat the house 1×ATR on the live gates** | **REFUTED (2026-08-08)** | Read off the 512 tick-repriced trades already running. In the 13:00–14:45Z open window: house 1.0× n=36 **+$30.76/tr** vs wide 2.0× n=33 **+$30.41/tr** — delta −$104, stable through strip-best-3, two days each way. **It splits by GATE, not by window**: grind prefers wide on both lots (+$72/+$64), `abs_veto` prefers tight in all four cells. The Open Rider's wide-stop edge belongs to *its own entries*, not to wide stops as a property. |
| **Stop-width A/B: "k20 ahead +$1,738"** | **WITHDRAWN — that was a CEILING number** | On the *identical* 512 trades, `ceiling_pnl` says wide is **ahead +$311** while tick-repriced `real_pnl` says wide is **behind −$364**, with **3 of 6 gates flipping sign**. The standing rule ("ceilings are NEVER scored on directly") earning its keep on a live question. |
| **Open Rider: "cadence 10 beats cadence 5 on the unseen days by better than 2:1"** | **WITHDRAWN — inside noise** | Per-trade SD ≈ **$160**, so on n=28/39 the SE on the difference is **$39.78 against a $24.86 gap — t = +0.63**. The unseen leg cannot discriminate between configs at this sample size; every rank in that column is noise. Caught by an external review, checked, conceded. |
| **Marginal optima compose** (implicit) | **FALSE, tested** | cad10 × stop3.0 is the best all-days cell (+$82.88/tr) but only **+$43.64** unseen — *below* cad10 × stop2.0 (+$46.88). Never test axes one at a time and then combine the winners. |

---

## 2. Live desk changes

**`grind_long` — SATURDAY #2, live 20:29:33Z**
- `deciders.ATR_FLOOR["grind_long"]` **10.0 → 22.0**; grind's `"ext_hi": 2.0` **deleted**.
- Verified at the **resolved** layer, not source: `scaleout_slots()` shows `ext_hi` gone, and the floor is
  genuinely wired because `tournament.py:156` calls `atr_blocks(_base(slot), atr)` — the raw suffixed tag
  `grind_long_A` does **not** block, which was the 07-29 dead-floor bug.
- ⚠ `grind_long` has **two** SlotSpecs in source (`slot_strategy.py:116` and `:161`); the slate resolves
  **:161**. Editing the other is a silent no-op.
- ⚠ **NOT YET GRADED.** First tradeable tape is the Sunday 22:00Z reopen. Review on **20 admitted legs**
  and on whether 4R events appear near the expected **12.7%** rate — **not** on P&L, and not on a
  fortnight without expansion days. The +$4,151 is a *delta* over 165 legs of which **21 runner events
  are the entire result**; strip them and it is +$380.70. The week's 6 live grind legs all fired at
  ATR ≥ 22, so the live book is **silent** on this revert.
- **NOT** added to `reactivate_gates.py::HOLD` (operator call) — with the floor in code it self-gates.

**Exit ladder — `grind_long` EXEMPTED from the `atr_split` 22 → 24 move**
- The other five non-NIPC rows take 24; grind keeps **22**. REV2 Q1 relied on the clip being *inert* at
  the ATR-22 entry floor, and **19.3%** of grind-eligible time sits in the 22–24 band the move would
  newly clip — where the clip caps Lot B at 1.75R/$60, truncating the 21 runner events that ARE grind's
  case. ⚠ FIX0's +$3,024 was measured with **all six** rows at 24, so the shipped config is not the
  tested config and the direction is **unmeasured**. Re-run the archive before quoting that number.

**Router**
- `abs_veto_short` is **carved out of the chop bench** until its 15-fire arm-by-default review completes.
  It is positive in **all five regimes** including chop (159 fires / 17 days), so benching it there costs
  money *and* biases the sample the review is drawn from.
- Router timing (WINDOW 45 / HOLD 3 / STEP 5) is **DEFERRED one week**, not rejected: it confounds with
  the chop off-switch by the report's own admission — *"a stickier router is a chop optimisation."*

---

## 3. Instruments fixed (the actual theme of the weekend)

| Instrument | What was wrong | Fix |
|---|---|---|
| `config_journal.py` | Recorded the **exit ladder only**, excusing entry params as "already recorded by slot_strategy.py and git". Both false — git does not record an uncommitted tree, and source is not the resolved config. **Proven the same day**: SATURDAY #2 changed a live entry floor and the journal logged `changed_from_previous: false`. | Rows now carry `entry` (per-slot params/sizing) + `gates` (the global `ATR_FLOOR`/`ER_FLOOR`/`ER_CEIL`/`ER_BAND`) + `entry_hash`. `config_hash` keeps its **exit-only** meaning so every existing scan stays valid. Pre-08-08 rows read `- (not recorded)` = *unknown*, never *unchanged*. |
| `sweep.py` | The journal had stamped `exit_overrides_uncommitted: true` at every startup since 08-04 and **nothing consumed it**, while five live behaviours existed only as working-tree edits. | `check_config_committed()` — WARNs if `exit_overrides.json` / `deciders.py` / `slot_strategy.py` / `multislot_core.py` are uncommitted. WARN not CRIT: a dirty tree is a bookkeeping failure, and a CRIT would train the operator to ignore a red sweep on a desk that is trading fine. |
| `config_at.py` | Could not read the entry side at all. | `--epochs --entry` segments on `entry_hash`; the decider tables print on every `--at`. |
| `friday_v7_build.py` | Plays cross-referenced each other by **position** ("see MONDAY #4") and the re-rank rotted five of them silently — a stale pointer is still a grammatical sentence. | Every reference carries its target's **id**; `check_xrefs()` asserts each pair resolves to the stated window and rank, and **the build refuses to run** if one does not. Negative-tested. |
| `scripts/friday/run_charts.py` | `load_trades()` had no `data_quality IS NULL` filter — `desk_view`/`recent_trades` were fixed 08-06 and this reader was missed. | Filter added. **No chart this week was affected** (the two excluded rows sit at 22:02Z, outside every window) — preventative, not a correction. |
| `gazbot7-friday-report.service` | Grew past 6.5GB on a 7.5GB box and was OOM-killed; two of the operator's own tmux sessions went the same way. | `MemoryHigh=3G` / `MemoryMax=4G` / `MemorySwapMax=1G` so the cgroup OOMs *itself*; `OOMScoreAdjust=-500` on the trading path, applied live via `/proc` too. ⚠ A cap does not make the job **finish** — the real fix is checkpointing per movement. |
| `.gitignore` | `scratchpad/` (807MB), `scratch/` and `*.pre-*` were **not ignored**. A literal "commit everything" would have added ~826MB. | Ignored. |

---

## 4. The play card

- Ordered by **execution logic**, not headline size. SATURDAY #1/#2 are the two the 22:00Z reactivate
  timer decides for you if you do nothing.
- **The play ledger is real**: `status` / `shipped_ts` / `outcome` on all 52 plays, plus `operator_pick`
  / `picked_ts`. **A pick is not a ship** — `status` stays `PROPOSED` until the change is applied.
  Last week's card had no outcome field, so nothing graded it and the audit hand-derived all 24 grades.
- Monday playbook regained the live/shadow/skip picker and copy-all, same localStorage contract as
  07-31, with each play's **id** now in the copied payload so a future re-rank cannot orphan a pick.

---

## 5. Shadow slate — 6 new arms, 59 sims numbered

**THE OPEN RIDER (BUILD #2) — `odr_c5_s20` · `odr_c5_s30` · `odr_c10_s20` · `odr_c10_s30`** (sims 54–57)
- Needed a new gate kind — **`clock_rider`, the first shadow variant with no signal at all** — plus the
  shadow's **first time-based exit** (`TIME_CAP`, 45 min). The tick repricer needed no change: its quote
  window ends at the sim's `exit_ts`, so a capped trade races stop-vs-target on honest ticks.
- Direction is the **raw sign** of the 15-min move; deadbands of 5/10/30pt are worse on both legs.
- **The four arms ARE the joint grid, run forward, because the backtest cannot rank them** (t = +0.63).
- Checked and held: 3.0×ATR is a real stop (**34.5%** stop-hit vs 62.9% at 1.0×), and it is not
  directional drift (LONG +$1,475 / SHORT +$2,695, both positive). ⚠ 17 days contain no FOMC/CPI gap —
  the tail a 3×ATR stop is actually exposed to.
- **Not eligible for live.** Needs all four of: +0.15R over 200 shadow trades *including a non-trending
  open week*, the 14:45Z cut, a real 2×ATR live stop path, day-rider position isolation.

**`sw_grind_A_k30` / `sw_grind_B_k30`** (sims 58–59) — the third stop rung, **grind only**, because the
wide-stop preference splits by gate. ⚠ `sw_grind_*` deliberately keeps `ext_hi: 2.0` and therefore **no
longer mirrors live**: a stop-width experiment is only readable with the entry population held constant.
Do not read those arms as "what live grind is doing".

**Sim registry** — 59 sims numbered, allocated once and never reissued:
`PYTHONPATH=src .venv/bin/python scripts/sim_registry.py [--stats|--id N|--match frag]`

---

## 6. Standing lessons banked

1. **A ceiling and a repriced book can disagree in SIGN.** 3 of 6 gates flipped. Never conclude from
   `ceiling_pnl`.
2. **Marginal optima do not compose.** Test the joint grid or run all cells forward.
3. **An unseen leg with n≈30 cannot rank configs.** Compute the standard error before believing a gap.
4. **The system's own tooling is where the undetected errors live**, not the trading logic — four
   instruments failed this weekend and no gate did.
5. **A pointer by position rots the moment you re-rank.** Anchor cross-references to ids and enforce it.

---

## APPENDIX — moved out of CLAUDE.md 2026-08-13 (bootstrap prune)

These were carried inline in the session bootstrap and are recorded here instead. The two that are
still BINDING CONFIG are also kept as one-liners in CLAUDE.md; the rest is reference.

### ★ grind_long is EXEMPT from the `atr_split` 22→24 move (SATURDAY #10) — still binding
The other five non-NIPC rows take 24; **`grind_long` keeps `atr_split: 22`**. Reason: SATURDAY #2 set
grind's entry floor to 22 and Q1 relied on the clip being *inert* at that floor. **19.3% of
grind-eligible time sits in the 22–24 band**, and the clip caps Lot B at 1.75R/$60 — which truncates
the 21 runner events that are grind's entire case.

⚠ **FIX0's +$3,024 was measured with all six rows at 24, so the shipped config is NOT the tested
config and the direction is unmeasured.** Re-run the archive before quoting that number.

### ★ Cross-references on the card are ID-ANCHORED and the build ENFORCES it
Plays used to point at each other by position ("see MONDAY #4"); a re-rank rotted five of those
silently. Every reference now carries the target's id, `friday_v7_build.py::check_xrefs()` asserts
each one resolves to the stated window and rank, and **the build refuses to run if one does not**.

### ★ Router timing (WINDOW 45 / HOLD 3 / STEP 5) is DEFERRED one week, not rejected
It confounds with the chop off-switch by the report's own admission — *"a stickier router is a chop
optimisation."*

### ★ ALL SHADOW SIMS ARE NUMBERED — permanent ids, never reissued
`PYTHONPATH=src .venv/bin/python scripts/sim_registry.py [--stats|--id N|--match frag]`.
Open Rider arms **54–57**, grind k30 rungs **58–59**, drift-gated Open Rider arms **60–63**
(added 2026-08-13). A retired sim keeps its number forever.
