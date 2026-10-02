# GAZBOT — AUTONOMOUS RECURSIVE TRADING LOOP · SCOPING DOCUMENT

> **Status: PROPOSAL, rev 2 (2026-10-02). Nothing built. Nothing in the baseline touched.**
> **Rev 2 supersedes rev 1 on three operator corrections:**
> 1. *"lets not assume entries are perfext. we have never tested live. only strong backtests."*
>    → **entry and exit are CO-EQUAL subjects.** Rev 1 wrongly treated the entry as settled.
> 2. *"it also needs a $200 loss kill in there somewhere especially if you get direction wrong
>    around the us open. it can run 200pt in 2 minutes."* → §5, with a recommendation.
> 3. *"assume zero methodologies are proven."* → §2 is now a register of unproven claims, and
>    **that includes every number this desk currently ships.**

---

## 1. THE GUIDING PRINCIPLE — CONFIRMED BY THE OPERATOR

> **We trade MNQ, and only the major intraday legs** — the three to six big directional moves a day,
> not the wobbles inside them.
>
> **We enter at a confirmed turn, in the direction of the new leg.** The turn is the signal: price
> has run a long way and aggression is pinned hard in the direction of that run — the climax — so
> the leg is ending and we take the other side. **Never against the prevailing line.**
>
> **We exit at the next turn, targeting ~80% of the leg** — *"if the leg is 300pt, exit at 240pt."*
> Which means riding through the wobbles and not re-reading the gauge once in: use it to enter, then
> stop looking at it.
>
> **One detector does both jobs.** The signal that exits this leg enters the next. That is why 4–5
> trades a day comes out of ~3 legs: we trade **both sides of each turn**, not more often.
>
> **The objective: take 80% of three to six legs a day, automatically, with the machine getting
> better at it every night.**

⚠ **80% is the TARGET, not a rule.** Reading the peak is hindsight; the turn detector is the causal
mechanism that *approximates* 80%. Any candidate that needs to know the peak is disqualified.
⚠ **"Never against the prevailing line" is a HARD CONSTRAINT, not a preference.**

---

## 2. ASSUME ZERO METHODOLOGIES ARE PROVEN

Operator instruction. Every number below is a **claim the loop must re-derive**, not a foundation.
This register is the loop's starting backlog.

| claim | current status | why it is NOT proven |
|---|---|---|
| **15×ATR retrace = a turn, 77%, 3.6/day** | shipped in `turn_watch` | measured on 100 sessions **in-sample**; its first cut shipped three wrong numbers ("7×ATR, 70%, 2.3/day") from a study of a rule it did not implement. Live: **18 fires, ~1 in 4 useful** — three false in compressed ATR, one 384pt late |
| **the turn detector works at all** | unproven | the ATR-ratio threshold fires on stillness in compression (ATR 5.4–9.3) and 384pt late in expansion (ATR 24.9). Its `compose()` reports incoherent arithmetic. **Three known defects, unfixed** |
| **CVD climax marks the end of a leg** | operator's rule, 6/6 once | n=6, one session, **manually executed**. Never run as automation |
| **"use the gauge to enter then stop looking"** | measured, thin | n=31 roll-offs |
| **legs: 3.1/day, 298pt, 266min** | measured, in-sample | 100 sessions, single window, no out-of-sample split |
| **`REFCLASS` leg survival is Lindy** | measured, in-sample | frozen table from the same 100 sessions. Not validated forward |
| **ladder reach rates 77.5/58/29.4/15%** | measured | 231 lake sessions, but the ladder itself has never been compared to any alternative |
| **1–4h is the best hold bucket** | ⚠ **LIKELY A FILL ARTIFACT** | see §2a — it inverts at clean fills |
| **his manual entries make +$78/trade** | ⚠ **CONTAMINATED** | §2a |
| **the incumbent ladder is good** | **BASELINE, NOT PROVEN** | it is the thing to beat, nothing more |

### 2a. ⚠⚠⚠ THE CONTAMINATION THAT BLOCKS EVERYTHING — FOUND 2026-10-02

Manual entries, clean non-flagged rows, split by lot size:

| hold | SINGLE LOT (clean fills) | MULTI LOT (fabricated 0.1% fill) |
|---|---|---|
| under 15 min | n=20 · **+$120.91** | n=86 · **−$65.56** |
| 15–60 min | n=25 · **+$121.27** | n=79 · −$6.15 |
| 1–4 h | n=18 · **+$109.74** | n=33 · −$8.89 |
| over 4 h | n=1 · +$104.50 | n=8 · **−$973.88** |
| **total** | **n=64 · +$7,530 · +$117.65/trade** | **n=206 · −$14,209 · −$68.97/trade** |

**At single lot the hold-time gradient vanishes** — every bucket +$110–121. The short-hold penalty
exists **only** in multi-lot rows, exactly where the IBKR paper engine fabricates a fixed
~0.1%-of-price adverse fill on every lot beyond the first (21/21 orders at 0.09897–0.09998%,
$2,916.50 over 32 orders — more than the desk's entire booked loss).

**A FIXED FABRICATED COST IS REGRESSIVE ON HOLD TIME.** ~30pt per extra lot is crushing on a 20pt
scalp and marginal on a 300pt hold. Same shape as `mnq-fee-is-150-per-round-trip`.

⚠ n is 18–25 per clean cell, so this is **not a refutation — it is EXPERIMENT #1**, and it blocks
the queue: a loop that optimises toward patience before answering it chases a fill artifact nightly.
★ The aggregate also **inverts the sign** on the desk's central question: group `trades` by
`entry_source` and manual entries appear to lose $24.74/trade when at clean fills they make
**+$117.65**. Any research loop's first query would get this wrong.

---

## 3. TWO CO-EQUAL SUBJECTS

Rev 1's error was treating the entry as solved because **the operator** is good at it. He is; the
machine is not, and has never tried.

| | ENTRY | EXIT |
|---|---|---|
| **the question** | is this a turn, and which way is the new leg? | how much of this leg do we keep? |
| **decisions per session** | 3–6 | ~300–500 (every minute of every open position) |
| **evidence available** | **~49 sessions** (needs `aggressor` for CVD) | **616 sessions** (needs price only) |
| **live automated record** | **none** | none (the ladder runs, but unevaluated) |
| **current instrument** | `turn_watch`, read-only, 18 fires, 3 known defects | the 4-lot ladder 50/100/200/300pt |
| **failure mode** | wrong direction → fast, large loss (§5) | right direction, too little of it |

### 3a. They share one detector, so they must be researched together

The same turn call exits leg N and enters leg N+1. A change to the detector changes **both** sides at
once, which means:

- **a candidate is scored on the round trip**, never on entry quality or exit quality alone
- **an entry change and an exit change may not be promoted the same night** (§6a one-change rule)
- the detector's **two defects are Phase-0 work**, not research: the ATR-ratio instability and the
  incoherent leg bookkeeping must be fixed before any measurement taken from it means anything

### 3b. The entry's data ceiling is real and shapes the plan

Entry research needs `aggressor` (the CVD climax is half the rule) and that exists for **~49
sessions**. So:

- **entry candidates validate forward and slowly**, on a rolling window, accumulating ~4 entries/day
- **exit candidates validate on 616 sessions of replay**, nightly
- ★ therefore the loop will honestly promote **exit** changes often and **entry** changes rarely —
  not because the entry matters less, but because the evidence arrives at different rates. The
  morning report must state which kind of change is pending and on what evidence base.
- ⚠ **An entry rule that can be tested on price alone can use all 616 sessions.** A first-order
  research question is therefore: *how much of the turn signal survives without CVD?* If most of it
  does, the entry joins the exit on the deep history. **That question is Experiment #2.**

---

## 4. THE OBJECTIVE FUNCTION

> **LEG CAPTURE RATIO (LCR) = points banked ÷ points the leg offered from our entry.**
> **Target: median LCR → 0.8** (the operator's number).

Maximise median LCR per round trip, subject to all of:

| constraint | threshold | why |
|---|---|---|
| trades/day | **3 ≤ n ≤ 6** | legs run 3.1/day; >6 is trading inside legs (09-28: 23 trades, −$1,882) |
| direction | **never against the prevailing line** | 09-28: 4 such trades, 4 losers, −$2,892.50 |
| fills | **modelled, single-lot-equivalent** | §2a |
| cost | **$3.42/lot round-turn** | not the booked $1.50 — understates by 128% |
| worst session | **no worse than baseline's** | tail control |
| regimes | **positive in every ATR tertile** | the detector's defects are ATR-regime-specific |
| sensitivity | **≥80% of 1-step neighbours also beat baseline** | a lone good cell is noise |
| interpretability | **one sentence for why it entered and why it exited** | no black box |

★ LCR is bounded [0,1] — ungameable by size, leverage or frequency.
⚠ **LCR is computed from the leg's realised extent, so it is hindsight: a SCORE, never an INPUT.** A
test must assert the separation. Violating it is what produced 866 winners from 866 trades.

---

## 5. RISK — THE $200 KILL. MY RECOMMENDATION.

> *"it also needs a $200 loss kill in there somewhere especially if you get direction wrong around
> the us open. it can run 200pt in 2 minutes. maybe we include it or maybe we cop those losses on
> the chin. you tell me."*

**My answer: include a kill — but NOT $200, and not as a stop. $200 is 25 points, and 25 points is
inside the noise.**

### 5a. The arithmetic that rules out $200-as-a-stop

```
$200 ÷ (4 lots × $2.00/pt) = 25 POINTS
MNQ ATR runs 10–25 points.  Median leg: 298 points.
```

A 25-point stop is **1–2.5× ATR**. It would be hit inside the ordinary breathing of almost every
winning leg. We would exit at −$200 repeatedly on trades that go on to make +$600, and the measured
cost is on the record: `step_away`'s $200 trigger, applied while the position was being watched,
**turned his +$819 of 09-16 and +$623 of 09-15 into −$200 apiece.**

★ And note the unit slip in the brief: **200 POINTS at 4 lots is $1,600, not $200.** The thing you
are describing — *direction wrong at the open, 200pt in 2 minutes* — is an **eight-times-larger**
event than the $200 figure. A $200 stop does not protect against it; it fires long before it, on
noise, every day.

### 5b. But the exposure is real and measured

| event | cost |
|---|---|
| 09-28, 4 entries **against** the prevailing line | **−$2,892.50** (4 from 4) |
| 10-01, LONG 4 held 7h19m through a 324pt slide | **−$2,396.88 on one trade** |
| the five worst trades in the book | **48% of all losses** — all LONG, all held 3h+ |
| `step_away` armed while **away** (≥90min), 20 fires | **+$3,257** |
| `step_away` armed while **watching** (<90min) | **+$95 — worthless** |

**That last pair is the whole answer.** A protective exit is worth +$3,257 when nobody is managing
the position and ~nothing when somebody is. **An autonomous system is the "away" case by
definition.** So the loop's own trades must carry protection. This does not change your standing
instruction for your *manual* trading — see 5d.

### 5c. What I recommend instead — three distinct mechanisms, not one stop

**1. ENTRY INVALIDATION (this is the one that answers the US-open worry).**
Not a stop — a **falsification of the entry thesis**. We entered because a turn happened and the new
leg runs *this* way. If price immediately runs the *old* way hard, **the turn call was simply
wrong**, and that is knowable in minutes rather than hours.

> Rule shape: adverse excursion > **K × ATR within M minutes of entry** → exit, flat, no re-entry
> on that leg.

★ This is cheap to be wrong about (a fresh turn that is genuinely resuming will re-signal), it
targets exactly the 09-28 against-the-line cluster, and it is **fast enough to matter at the open**.
⚠ **K and M are research outputs, not numbers I pick.** Experiment #3.

**2. CATASTROPHE STOP — wide, dumb, and only for the 10-01 shape.**
Sized to the leg structure, not to a dollar feeling: roughly **2–3× the median adverse excursion of
eventual WINNERS**, so it cannot fire on a normal winning leg by construction. Its job is capping
−$2,397, not improving expectancy. A real venue stop, not a watcher.
⚠ The desk's current `VENUE_STOP_PT = 600.0` exists and is **unarmed**, and `armed-is-not-verified`
records that it would not have fired anyway (a plain `StopOrder` on a `ContFuture`). **Arming it
correctly is Phase-0 engineering work, not research.**

**3. DAILY LOSS FLOOR.** The existing `$250` daily limit already does this, counts **realised only**,
and can only ever bench. Extend to **open + realised** via `equity_guard` — which is built and
deliberately unarmed. For the loop's own trades, arm it.

### 5d. The one distinction that resolves this against your standing instruction

You said: *"just dont switch on any kill switches while paper trading. i want to be able to trade and
learn."* That stands, and it is not in conflict:

| whose position | protection |
|---|---|
| **your manual trades** | **unchanged — no kill switches.** You keep learning without the desk pulling you out |
| **the loop's automated trades** | **all three mechanisms armed.** Nobody is watching them, which is the only condition under which they are worth +$3,257 |

This needs the `entry_source` separation to be real in the risk layer, which is Phase-0 work.

### 5e. Or we cop them on the chin — the honest alternative

If you would rather carry the losses: the measured price of *no* protection on the loop's own trades
is roughly the 09-28/10-01 shape, ~**−$2,400 per incident**, at an observed rate of perhaps one or
two a fortnight. Against a target of 4–5 trades a day that is survivable but it is the single
largest line item, and it is **concentrated**, not spread — the five worst trades being 48% of all
loss is the signature of exactly this. **My recommendation is to include the protection**, because
the asymmetry is in our favour: an entry-invalidation that is wrong costs us one re-entry, and one
that is right saves ~$700 per occurrence.

---

## 6. THE NIGHTLY CYCLE

```
21:00Z CME halt
   ↓  finalise session: fills, legs, entry journal, exit-decision journal
   ↓  SCORE — LCR per round trip vs what the baseline would have done on the same tape
   ↓  OBSERVE — cluster the misses: wrong-direction entries, and exits with the most left behind
   ↓  HYPOTHESISE — Researcher reads memory, proposes <=5 candidates, each with a mechanism
   ↓  RANK by expected information gain (§7)
   ↓  REPLAY — exits on 616 sessions; entries on whatever their evidence base allows (§3b)
   ↓  SKEPTIC — placebo, label shuffle, random-clock; beat your own placebo by 2x or die
   ↓  VALIDATE — rolling walk-forward holdout + ATR-tertile split + sensitivity neighbourhood
   ↓  COMPARE to baseline on the HOLDOUT only
   ↓  PROMOTE (at most one) / REJECT / KEEP RESEARCHING
   ↓  write policy, update memory, write the morning report
06:00 Paris — report on his phone
```

### 6a. How nightly promotion stays honest

1. **Rolling walk-forward.** Holdout = most recent **40 sessions**, gaining exactly **one genuinely
   unseen session** each night.
2. **The search is CHARGED.** Candidates scored against the holdout are counted and the bar rises
   with the count — `charge-the-search-then-charge-the-bar` got **6 of 6 null worlds** through three
   naive bars. Budget: 5/night.
3. **Forward degradation auto-demotes.** Realised LCR below baseline over 10 sessions → automatic
   revert, reason recorded. **Promotion is reversible, which is what makes nightly affordable.**
4. **One change per night, and never one of each.** An entry change and an exit change on the same
   night makes both unattributable.

---

## 7. RESEARCH PRIORITISATION

```
EIG = (points left on the table / lost to this pattern, $/day at 4 lots)
    × (frequency per session)
    × (confidence it is real: n, CI width)
    × (remaining uncertainty: has this family failed before?)
    ÷ (compute cost)
```

The **remaining-uncertainty** term is what makes the loop recursive: a family that has failed three
times starves; one that keeps producing signal is amplified. **The 120th exit calibration scores
near zero by construction.**

### 7a. Opening queue, ranked

| # | question | subject | why |
|---|---|---|---|
| **1** | Is the hold-time edge real at clean fills, or a fill artifact? | both | §2a. Blocks the queue |
| **2** | How much of the turn signal survives on **price alone**, without CVD? | entry | decides whether entries get 49 sessions or 616 (§3b) |
| **3** | What are K and M for entry invalidation? | risk | §5c; the US-open exposure |
| 4 | Is 15×ATR the right threshold once an ATR floor and a stability guard are added? | entry | three known defects make the 77% unmeasured |
| 5 | Does banking lot 1 at 50pt of a 298pt median leg cost more than it protects? | exit | the ladder's most front-loaded choice, never tested |
| 6 | Does a leg-age-conditioned ladder beat a fixed one? | exit | `REFCLASS` says remaining points *rise* with age; the ladder ignores age |
| 7 | What separates a leg that resumes from one that is over? | both | 23% of turn calls see the old direction resume |
| 8 | Does the over-4h penalty survive clean fills? | exit | the only hold-time cell still looking real |

---

## 8. PHASE 0 — WHAT MUST EXIST FIRST

| gap | consequence if skipped | 
|---|---|
| **`trades` has no entry-grouping key** (no `entry_id`/`parent_id`) | `CLAUDE.md`'s own *"group by ENTRY, not by trade row"* rule is **mechanically unobeyable**; n inflated 1.6–2.5× |
| **no clean-fill flag** | the loop's first query inverts the sign on the central question (§2a) |
| **`FEE_RT` understates cost 128%** | cheap costs make an optimiser prefer over-trading — the behaviour being fixed |
| **no entry journal / no exit-decision journal** | the units of research do not currently exist |
| **no counterfactual replay** | cannot ask "what would the baseline have done here?" |
| **`turn_watch`'s three defects** | every number taken from it is unmeasured until fixed |
| **`VENUE_STOP` would not fire** | `armed-is-not-verified`: plain `StopOrder` on a `ContFuture`. Must be a real venue stop before it is called protection |
| **risk layer cannot tell loop trades from manual trades** | §5d is unimplementable without it |

---

## 9. GUARDRAILS

**The loop writes DATA, never CODE.** `data/trade_policy_active.json` — a declarative policy over a
**fixed, human-reviewed vocabulary** of causal state terms. The rider interprets it. An invalid file
→ fall back to the baseline, log loudly, page. **The vocabulary cannot be extended by the loop;
adding an input is a human change.**

- **outside the policy layer and unmodifiable by it:** the 20:40Z hard flat, `eod_flatten`,
  `desk_reconcile`, the catastrophe stop, the daily floor
- the loop may not size, add to, or reverse a position outside the policy vocabulary
- **manual trades are never touched by the loop or its risk layer** (§5d)
- causal-inputs-only, asserted by test; fabricated-fill and `data_quality` rows excluded from scoring
- every experiment reproducible: id, seed, data window, code hash
- ⚠⚠ **research runs lake/parquet ONLY — no IBKR historical calls — and yields while any desk holds.**
  18 of 25 gateway CLOSE-WAIT episodes start 18:00–00:00Z where the existing overnight jobs already
  hammer history, and one wedge cost **$2,149**
- `MemoryMax` drop-in; the box is 7.5GB with ~5GB free and has OOM-killed three times
- artifact-on-disk checkpointing; **judge the artifact, never the exit code**

---

## 10. PHASES

| phase | contents | exit criterion |
|---|---|---|
| **0 — instrument** | §8 in full; answer Experiments #1 and #2 | the hold-time question has a clean-fill answer; we know the entry's true evidence base |
| **1 — observe** | journals + Historian; nightly scoring of the live day against a baseline replay | 10 sessions journalled; LCR reproducible to the cent |
| **2 — replay** | reproduce the **baseline** exactly over 616 sessions | replayed baseline matches the live book within tolerance |
| **3 — skeptic** | adversary + validator, run against the **119 already-rejected** exit ideas | **it must re-reject them.** Promoting a known failure means it is wrong |
| **4 — loop, shadow** | full cycle nightly; promotions go to a **shadow** policy the rider ignores | 20 sessions: shadow LCR ≥ baseline, ≤1 promotion/night, demotions firing |
| **5 — live** | rider reads the active policy; risk mechanisms armed on loop trades only | operator says go |

★ **Phase 3 is the gate that matters.** A loop that cannot re-derive this desk's own 119 exit
failures is not a validator — it is a random number generator with good manners.

---

## 11. THE MORNING REPORT

One page, phone-readable, **06:00 Paris** — outside quiet hours, because
`a-process-cannot-report-its-own-absence`: a missing report is itself the alarm.

```
YESTERDAY   4 round trips · LCR 0.38 median (baseline replay 0.31) · +$412
            1 entry invalidated at -$180 (turn call wrong, exited in 4min)
            worst exit: 09:14 SHORT banked 52pt, leg gave 180pt more over 71min
OVERNIGHT   5 hypotheses · 3 rejected (1 failed placebo, 2 failed ATR-tertile split)
            1 promoted (EXIT): lot-1 target 50pt -> 80pt when leg age > 45min
            evidence: holdout LCR 0.34 -> 0.39, n=412 legs, all 3 tertiles positive,
                      9 of 11 neighbours also beat baseline
            entry research: #2 still accumulating, 23 of 40 sessions
CONFIDENCE  validated improvement (holdout + walk-forward + sensitivity)
TODAY       policy v23 · demotion watch on v21's age rule (7 of 10 below baseline)
```

Confidence is always one of: **established observation · promising hypothesis · validated
improvement · inconclusive**.

---

## 12. SUCCESS, AND THE HONEST FAILURE MODE

- **3–6 round trips a day** on the legs, both sides of the turns
- **median LCR rising toward 0.8**
- entry and exit both automated, both improving, both auditable
- the operator reads the morning report; he does not decide what to test
- every change traceable: change → experiment → hypothesis → observation → data

⚠ **And the failure mode stated in advance:** if 60 sessions produce no LCR improvement, the answer
is that the baseline is already near the achievable frontier and the edge was in the operator's
hands all along — which is a real result, and is the one this desk's history makes most likely. The
loop is built to find that out honestly and quickly rather than to keep searching.
