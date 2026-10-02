# GAZBOT — AUTONOMOUS RECURSIVE EXIT LOOP · SCOPING DOCUMENT

> **Status: PROPOSAL, 2026-10-02. Nothing built. Nothing in the baseline touched.**
> Operator brief: *"i want 4-5 trades a day on the manor intraday legs. with modifications every
> night. not every month. dont be cautious and tell me why we cant. youve already proved to me you
> can do the entries. you just need to practice the exits."*
>
> This document scopes **ONE loop with ONE subject: the exit.** The entry is treated as settled and
> is out of scope for modification. Read with `STATE.md` §1, §5d and `SESSIONS.md` 09-28 → 10-02.

---

## 0. THE ONE-PARAGRAPH VERSION

The desk already generates 3–6 tradeable legs a day and the operator already enters them well. What
it does not do is *stay in them*. His median hold is **21 minutes against a 266-minute median leg**.
So the loop being built here does not search for a strategy; it practises a single skill — **when to
stay and when to bank** — against **616 sessions of replayable price history**, every night, and
promotes an exit policy only when it beats the shipped one on sessions it has never seen. Exits are
the one part of this desk where the data is deep enough to honestly support nightly change.

---

## 1. WHY THIS IS THE EXITS AND NOT THE ENTRIES

### 1a. The entry is settled, and the record says so

| date | entries | median hold | result |
|---|---|---|---|
| 2026-09-28 Mon | 23 | 17 min | **−$1,882.50** |
| 2026-09-29 Tue | **6** | **32 min** | **+$1,788.00 — 6 of 6 winners** |
| 2026-10-01 Thu | 3 | — | −$2,114.76 (one 7h19m hold, −$2,397) |

Same instrument, same week, **$3,670 swing**. On Monday, **19 entries WITH the prevailing line made
+$1,010 and 4 entries AGAINST it lost −$2,892.50** — four from four, three within minutes of a turn.
The entry rule that produced Tuesday is his own and is already written down:

> *"once its run a lot and cvd and peice are birh lushinf hard right ill claim. and wait for the
> turn."*

Claim at the climax, re-enter the other way as CVD rolls off. **That is the entry. It is not in
scope.** The loop may read it, model it, and measure it. It may not change it.

### 1b. The measured operating rule that supports leaving it alone

From the 09-29 CVD study (5,963 gauge-minutes): a pin lasts a **median of 3 minutes**; his trigger
(gauge ≥95 then <90) fired 31 times and **snapped back above 95 in 65% of them while price still
fell a median 42.1pt**, against 51.2pt when it persisted. Persistence is nearly irrelevant.
→ **Use the gauge to ENTER, then stop looking at it.** The loop inherits this: CVD is an entry input
and must not become an exit input without passing the same bar as anything else.

### 1c. The data asymmetry is the whole reason this is tractable

| research subject | sessions available | why |
|---|---|---|
| CVD / aggressor / entry microstructure | **~49** | `aggressor` is in `ticks`; the lake has 46 MNQ partitions from 2026-07-24 |
| **price — legs, exits, holds, giveback** | **616** | `gazbot7.lake` unified view: 2024-09-23 → 2026-10-02, 1.64M MNQ bar rows |

**Verified 2026-10-02** via `gazbot7.lake.connect()`. Exit research needs **price**, not aggressor.
That is a **12.5× larger** evidence base, and it is why a nightly cadence can be honest here and
could not be for the entry.

---

## 2. THE EXIT PROBLEM, STATED PRECISELY

### 2a. The incumbent

`day_rider.py`, 4 lots, **no stop** (operator design, 2026-08-20):

| lot | target | reach rate (231 lake sessions, causal) |
|---|---|---|
| 1 | 50pt / $100 | **77.5%** |
| 2 | 100pt / $200 | 58.0% |
| 3 | 200pt / $400 | 29.4% |
| 4 | 300pt / $600 | ~15% |

Plus `USE_ATR_TRAIL=True`, `TRAIL_ATR_MULT=2.0`, fallback `ARM_PT=150 / TRAIL_PT=100`,
`VENUE_STOP_PT=600` (unarmed), and `EXIT_ASK` — a 2×ATR reversal from the peak raises a question at
15-minute intervals, max 3 pushes, **never escalating to a sell**.

**The structural observation:** lot 1 banks at **50pt** on a **median 298pt leg**. The ladder is
front-loaded by design, and that design has never been tested against the leg distribution.

### 2b. The asset that argues for holding: leg survival is Lindy

`leg_watch.REFCLASS`, frozen — `{age: (% of legs reaching it, median more MINUTES, median more
POINTS, % dying within 15min)}`:

| leg age | % reach | median more min | **median more pt** | % die in 15min |
|---|---|---|---|---|
| 15 | 97 | 29 | 39 | 27 |
| 30 | 70 | 26 | 31 | 32 |
| 45 | 48 | 27 | 28 | 32 |
| 60 | 33 | 29 | 29 | 31 |
| 90 | 16 | 40 | 37 | 25 |
| 120 | 9 | 58 | 44 | 21 |
| 180 | 5 | 98 | **54** | **13** |

**Remaining points INCREASE with age** (39 → 31 → 28 → 29 → 37 → 44 → 54) while **death rate FALLS**
(27% → 13%). An old leg is a *safer* leg with *more* left. This is the single strongest measured
argument for the thing he wants to practise, and it is already computed, frozen and live.

### 2c. ⚠⚠⚠ BUT THE PATIENCE THESIS NEEDS RE-DERIVING ON CLEAN FILLS — FOUND 2026-10-02

The justification repeated in `CLAUDE.md`, `STATE.md`, the `turn_watch` message and the `step_away`
case is: *under 15min −$27/entry over 67, 1–4h +$86/entry over 30.* Split by lot size, on clean
non-flagged rows:

| hold | SINGLE LOT (clean fills) | MULTI LOT (fabricated 0.1% fill) |
|---|---|---|
| under 15 min | n=20 · **+$120.91**/trade | n=86 · **−$65.56** |
| 15–60 min | n=25 · **+$121.27** | n=79 · −$6.15 |
| 1–4 h | n=18 · **+$109.74** | n=33 · −$8.89 |
| over 4 h | n=1 · +$104.50 | n=8 · **−$973.88** |
| **total** | **n=64 · +$7,530 · +$117.65** | **n=206 · −$14,209 · −$68.97** |

**At single lot the hold-time gradient disappears.** Every bucket sits at +$110–121. The under-15min
penalty exists **only** in multi-lot rows — precisely the rows where the IBKR paper engine fabricates
a fixed ~0.1%-of-price adverse fill on every lot beyond the first (21/21 orders at 0.09897–0.09998%,
$2,916.50 over 32 orders).

**And the mechanism explains it exactly: a FIXED fabricated cost is REGRESSIVE on hold time.** ~30pt
per extra lot is crushing on a 20-point scalp and marginal on a 300-point hold. The same shape as
`mnq-fee-is-150-per-round-trip`. So a large part of "hold longer" may be "stop paying a fixed
fabrication on small moves".

⚠ **n is small (18–25 per clean cell) and single-lot trades may be a biased subset.** This is not a
refutation — it is a **first-order research question that must be answered before the loop optimises
toward patience**, or the loop will spend every night chasing a fill artifact. **It is Experiment #1.**
★ The over-4h multi-lot cell (−$973.88 over 8) remains large and consistent with
`the-five-worst-trades-share-one-behaviour`; the *upper* bound on hold time looks real.

### 2d. Why 119 previous attempts failed, and what is different

`claiming-cannot-be-backtested`: 86% capture, 18% headroom, 119 calibrations, all failed. On 09-28 I
added three more hindsight failures (866 winners from 866; a 5-min/8pt median scalper; +$1,287/day
with 98/100 winning sessions). The lesson recorded was:

> *"exit within 20% of the peak" has no causal implementation — read the peak and you have a ceiling,
> make it a rule and you have a trailing stop.*

**Every one of the 119 searched for a fixed exit level on a fixed history.** The difference here is
structural, not a matter of trying harder:

1. **The subject is a POLICY over observable state, never a level.** Input is only what is knowable
   at that minute (leg age, extension in ATR, giveback from peak, ATR regime, time of session,
   lot already banked). No peak-reading, ever.
2. **The evidence advances.** One genuinely unseen session is added every night, forever.
3. **The loop remembers.** 119 calibrations failed partly because each one started from zero. The
   Historian makes a 120th impossible to run by accident.
4. **The objective is bounded** (§4), so "hold forever" and "scalp everything" are both excluded by
   construction rather than by a reviewer noticing.

---

## 3. WHAT "4–5 TRADES A DAY" MEANS MECHANICALLY

Legs measured at **3.1/day** (315 legs / 100 sessions, median 298pt over 266min); **68 of 100 days
had ≤3**. So 4–5 trades/day is *not* more frequent trading than the tape supports — it is **trading
both sides of the turns**: claim at the climax, re-enter opposite. That is exactly his 09-29 pattern
(6 entries from ~3 legs) and exactly what `turn_watch` exists to flag.

**Therefore the trade-count band is a CONSTRAINT, not a target:**
- **floor 3** — below this he is missing legs the tape offered
- **ceiling 6** — above this he is trading noise inside legs (Monday's 23 → −$1,882)
- a candidate policy that needs >6 trades/day to win is **rejected regardless of P&L**

---

## 4. THE OBJECTIVE FUNCTION — AND WHY IT IS NOT P&L

Optimising P&L on 616 sessions will find a pathology. The objective is instead:

> **LEG CAPTURE RATIO (LCR) = points banked / points the leg actually offered from our entry.**

Maximise **median LCR per trade**, subject to all of:

| constraint | threshold | why |
|---|---|---|
| trades/day | **3 ≤ n ≤ 6** | §3 |
| fills | **single-lot-equivalent, modelled** | multi-lot paper fills are fabricated (§2c) |
| cost | **$3.42/lot round-turn** | not the booked $1.50 — IB-implied, understates by 128% |
| worst session | **no worse than incumbent's** | tail control, not average chasing |
| regimes | **must not lose in any ATR tertile** | `backtest-per-regime-segment-not-blanket` |
| parameter sensitivity | **≥80% of neighbours within 1 step must also beat baseline** | a lone good cell is noise |
| interpretability | **the rule must state in one sentence why it exited** | §16 of the brief |

★ **LCR is bounded in [0,1]**, so it cannot be gamed by size, leverage or frequency, and it is
directly the thing he asked for: *take more of the legs you are already in.*
⚠ **LCR is computed from the leg's realised extent, which is hindsight — so it is a SCORE, never an
input.** The policy being scored may only read causal state. A test must assert that separation; it
is the exact failure that produced 866 winners from 866.

---

## 5. ARCHITECTURE — EIGHT ROLES, MAPPED ONTO WHAT EXISTS

No new trading platform. Each role is a thin layer over something already running.

| role | implementation | reuses |
|---|---|---|
| **Observer** | `exit_journal.py` — one row per *exit decision point*, every minute of every open position, with the causal state and what followed | `day_rider` state, `capture.db` bars, `operator_reads.jsonl` |
| **Researcher** | `exit_hypothesis.py` — reads the journal + research memory, proposes candidate policies with a stated mechanism | `leg_survival.py`, `REFCLASS` |
| **Experimenter** | `exit_replay.py` — replays a policy over N lake sessions | **`exit_ladder_lab_v2.py`, `exit_policy_build.py`, `adaptive_exit_bt_ext.py`, `run_census.py --lake`** |
| **Skeptic** | `exit_adversary.py` — placebo policies, label shuffles, random-clock controls, leave-one-day-out | `exh_exit_placebo.py`, `gf_rider_engine.py` placebo harness |
| **Validator** | `exit_validate.py` — rolling walk-forward, regime split, sensitivity neighbourhood | `rerun_walkforwards.sh` |
| **Historian** | `data/exit_research_memory.json` — every hypothesis, result, rejection and reason, forever | pattern of `router_badcall_ledger.md` |
| **Engineer** | writes `data/exit_policy_active.json`; the rider **reads** a policy file, never executes generated code | existing `gate_switches.env` ownership pattern |
| **Auditor** | `data/exit_policy_journal.md` — every promotion/demotion with its full evidence chain | `DECISIONS.md` pattern |

### ★★★ THE SAFETY INVARIANT THAT MAKES THIS SAFE TO RUN AUTONOMOUSLY

**The loop writes DATA, never CODE.** `exit_policy_active.json` is a declarative policy — thresholds
and conditions drawn from a **fixed, human-reviewed vocabulary** of causal state terms. The rider
interprets it. Therefore:

- an experimental failure can produce a bad *policy*, never a crash, a naked position or a runaway
- the policy schema is versioned and validated on load; an invalid file → **fall back to the
  incumbent ladder**, log loudly, page
- the vocabulary cannot be extended by the loop. Adding a new input is a **human** change.
- **the 20:40Z hard flat, `desk_reconcile`, and `eod_flatten` sit entirely outside the policy layer**
  and cannot be modified by it, exactly as the daily-loss-limit can only ever bench

---

## 6. THE NIGHTLY CYCLE, AND HOW NIGHTLY PROMOTION IS HONEST

```
21:00Z CME halt
   ↓  finalise the session: fills, legs, exit-decision journal
   ↓  SCORE yesterday — LCR per trade vs what the incumbent would have done on the same tape
   ↓  OBSERVE — where did we exit with the most left on the table? cluster them
   ↓  HYPOTHESISE — Researcher reads memory, proposes ≤5 candidates with mechanisms
   ↓  RANK by expected information gain (§7)
   ↓  REPLAY the top candidates over the TRAIN window
   ↓  SKEPTIC — placebo, shuffle, random-clock; a candidate that beats its own placebo by < 2x dies
   ↓  VALIDATE — rolling walk-forward on the HOLDOUT window + regime split + sensitivity
   ↓  COMPARE to the incumbent on the holdout ONLY
   ↓  PROMOTE / REJECT / KEEP RESEARCHING
   ↓  write policy, update memory, write the morning report
06:00 Paris — report on his phone
```

### 6a. Why this can promote nightly without promoting noise

The anti-pattern is re-testing the same validation set until something passes — which is how
`charge-the-search-then-charge-the-bar` got **6 of 6 null worlds through all three bars**. Four
defences, all mechanical:

1. **Rolling walk-forward, advancing one session per night.** Train = sessions 1..N−K. Holdout =
   the most recent K (**K=40**). Every night the holdout gains exactly **one genuinely unseen
   session** and drops its oldest.
2. **The search is CHARGED.** The number of candidates evaluated against the holdout is counted and
   the bar rises with it — the Bonferroni-style correction `charge-the-search` demands. The nightly
   budget is **5 candidates**; a 6th costs more to pass than a 1st.
3. **FORWARD DEGRADATION IS A DEMOTION TRIGGER.** Every promoted policy keeps accruing live paper
   evidence. If its realised LCR falls below the incumbent's over a 10-session window, it is
   **automatically demoted and the reason recorded**. Promotion is reversible, so being wrong is
   cheap — which is what makes nightly change affordable.
4. **One change at a time.** At most **one** promotion per night, so every change has a clean
   forward attribution window. Two simultaneous changes make both unattributable.

★ **This is the actual answer to "nightly, not monthly":** the pre-registration model is slow because
it freezes a parameter and waits for *new* trades. The exit loop instead validates on **616 existing
sessions** and uses the new session as the incrementally-unseen test. Nightly promotion is honest
*because* a promotion is cheap to reverse and is attributed forward.

---

## 7. RESEARCH PRIORITISATION — EXPECTED INFORMATION GAIN

Each queued question carries a score:

```
EIG = (points left on the table in this pattern)      ← measured from the journal, $/day at 4 lots
    × (frequency per session)
    × (confidence the observation is real: n, CI width)
    × (remaining uncertainty: has this family been tested before?)
    ÷ (compute cost of the test)
```

★ The **remaining-uncertainty** term is what makes the loop recursive rather than a cron of
backtests: a family that has failed three times is divided down and starves; a family that keeps
producing signal is amplified. The Historian supplies that term, so **the 120th calibration scores
near zero by construction.**

### 7a. The opening research queue, ranked

| # | question | why it is first |
|---|---|---|
| **1** | **Is the hold-time edge real at clean fills, or a fabricated-fill artifact?** | §2c. Everything downstream depends on it. Blocks the rest of the queue. |
| 2 | Does banking lot 1 at 50pt on a 298pt median leg cost more than it protects? | The incumbent's most front-loaded choice, never tested against the leg distribution |
| 3 | Does a leg-age-conditioned ladder beat a fixed one? | `REFCLASS` says remaining points *rise* with age — the ladder ignores age entirely |
| 4 | Is `EXIT_ASK`'s 2×ATR reversal the right question at the right time? | It never sells, so it is free to test and currently unvalidated |
| 5 | What distinguishes a leg that resumes from one that is over, at the moment of a 2×ATR pullback? | 23% of `turn_watch` calls see the old direction resume |
| 6 | Does the over-4h penalty survive clean fills? | The only hold-time cell that still looks real (−$973.88, n=8) |

---

## 8. WHAT MUST BE BUILT BEFORE ANY OF IT (PHASE 0 — NON-NEGOTIABLE)

Found by inspection today. Without these the loop optimises against corrupted inputs.

| gap | consequence if skipped | fix |
|---|---|---|
| **`trades` has no entry-grouping key** (no `entry_id`/`parent_id`) | `CLAUDE.md`'s own rule *"group by ENTRY, not by trade row"* is **mechanically unobeyable**; n inflated ~1.6–2.5× | add `entry_id`, backfill from `entry_exec_id` + `opened_at` |
| **No clean-fill flag** | the loop would conclude manual entries lose $24.74/trade when at single lot they make **+$117.65** — **sign inversion on the desk's central question** | `fill_fabricated` column, computed from the 0.1% signature |
| **`FEE_RT` understates cost by 128%** | an optimiser with cheap costs systematically prefers over-trading — the exact behaviour being fixed | re-derive from book-recon, then one constant, one place |
| **No exit-decision journal** | nothing to learn from; the unit of exit research does not currently exist | Observer, §5 |
| **No counterfactual record** | cannot ask "what would the incumbent have done here?" | replay the incumbent nightly alongside the live result |

---

## 9. GUARDRAILS

**Trading**
- policy layer cannot open, size, reverse or add — **exit only**
- the 20:40Z hard flat, `eod_flatten` and `desk_reconcile` are outside the policy layer
- no kill switch is armed by this work (standing operator instruction)
- entry logic is read-only to the loop

**Research**
- causal-state-only inputs; a test asserts the policy cannot read a future bar
- `data_quality`-flagged and fabricated-fill rows excluded from every score
- holdout untouchable except by the nightly validator, search charged
- every experiment reproducible: id, seed, data window, code hash

**Infrastructure**
- ⚠⚠ **the research engine must YIELD like `backfill` does.** 18 of 25 gateway CLOSE-WAIT episodes
  start 18:00–00:00Z where `driftlab`/`backfill`/`overnight` already hammer historical data, and one
  wedge cost **$2,149**. The loop runs **lake/parquet only, no IBKR historical calls**, and pauses
  while any desk holds a position.
- `MemoryMax` drop-in; the box is 7.5GB with ~5GB available and has OOM-killed three times
- artifact-on-disk checkpointing; **judge the artifact, never the exit code**

---

## 10. PHASES

| phase | contents | exit criterion |
|---|---|---|
| **0 — instrument** | §8 gaps; answer Experiment #1 | the hold-time question has a clean-fill answer |
| **1 — observe** | Observer + Historian; nightly scoring of the live day vs the incumbent replay | 10 sessions journalled; LCR reproducible to the cent |
| **2 — replay** | Experimenter over 616 sessions; reproduce the *incumbent* exactly | replayed incumbent LCR matches the live book within tolerance |
| **3 — skeptic** | adversary + validator; run on the 119 **already-rejected** ideas | it must re-reject them. If it promotes a known failure, it is wrong |
| **4 — loop, shadow** | full cycle nightly, promotions written to a **shadow** policy the rider ignores | 20 sessions; shadow LCR ≥ incumbent, ≤1 promotion/night, demotions firing correctly |
| **5 — live** | the rider reads the active policy | operator says go |

★ **Phase 3's exit criterion is the one that matters.** A loop that cannot re-derive the desk's own
119 failures is not a validator, it is a random number generator with good manners.

---

## 11. THE MORNING REPORT

One page, phone-readable, 06:00 Paris, outside quiet hours (the
`a-process-cannot-report-its-own-absence` lesson — a missing report is itself the alarm).

```
YESTERDAY     4 trades · LCR 0.38 median (incumbent replay: 0.31) · +$412
              worst exit: 09:14 SHORT banked 52pt, leg gave 180pt more over 71min
OVERNIGHT     5 hypotheses · 3 rejected (1 failed placebo, 2 failed regime split)
              1 promoted: ladder lot-1 target 50pt -> 80pt when leg age > 45min
              evidence: holdout LCR 0.34 -> 0.39, n=412 legs, all 3 ATR tertiles positive
              sensitivity: 9 of 11 neighbours also beat baseline
CONFIDENCE    validated improvement (holdout + walk-forward + sensitivity)
TODAY         policy v23 · demotion watch on v21's age rule (7 of 10 sessions below incumbent)
```

Confidence is always one of: **established observation · promising hypothesis · validated
improvement · inconclusive**.

---

## 12. WHAT SUCCESS LOOKS LIKE

- **3–6 trades a day**, on the legs, both directions of the turns
- **median LCR rising** over sessions — more of each leg captured
- the operator's role is **reading the morning report**, not deciding what to test
- every change traceable: change → experiment → hypothesis → observation → data
- and the honest failure mode stated up front: **if 60 sessions of this produce no LCR improvement,
  the answer is that the incumbent ladder is already near the achievable frontier**, and that is a
  real result worth having rather than a reason to keep searching.
