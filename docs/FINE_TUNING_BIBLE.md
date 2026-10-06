# THE FINE-TUNING BIBLE — how the loop is allowed to change the rules

> Operator, 2026-10-06: *"All fine tuning needs to try as best we can to preserve the
> configuration of the best iteration and improve it. We can't be trying things and getting
> worse... I believe we need a bible of guidelines for the AI to refer to."*

## ⚠⚠⚠ THIS FILE IS DOCUMENTATION. THE SOURCE IS `src/gazbot7/bible.py`.

Operator, 2026-10-06: *"how do we make the AI always abide. Just like Claude code does. If it
sits outside CLAUDE.md you don't do it."* That is the right diagnosis: `CLAUDE.md` binds
because it is **injected into every session automatically**, not because it is well written.

So the laws live in **`src/gazbot7/bible.py`** as one importable constant, and every prompt
that writes, reviews or judges a rule set calls `laws()`:

| prompt | what it does |
|---|---|
| `recursive_loop.CONSOLIDATE` | writes the next rule set |
| `sim_week_recursive.REVIEW` | writes the nightly lessons that become rules |
| `preflight_iteration.AUDIT` | judges whether a planned change is sound |

**`tests/test_bible_is_enforced.py` fails if any of those is missing any law.** That test is
the enforcement; this document is only a readable copy, and a test asserts the two cannot
drift.

⚠ **The failure this guards against happened twice while building it.** The first attempt
patched `recursive_loop`'s module DOCSTRING — text no model reads — and the diff looked
correct; only capturing the assembled prompt and grepping it showed L1, L2 and L5 missing. The
second attempt spliced from the docstring anchor into the middle of the prompt and **deleted
201 lines**, including `ALL_WEEKS`, `score_week`, `meets_bar` and the `CONSOLIDATE` assignment
itself. Restored from the last verified commit and redone with an anchor inside the assignment.
Both were caught by running the checks, neither by reading the change.

---

**The operative half of this file is injected from `bible.py`.** A rule
that lives only in a document is a rule the reviewer never sees — this desk has already lost
three banked lessons to exactly that, which is why `a-memory-is-not-a-rule-until-it-is-in-the-prompt`
exists. If you edit a law here, edit the prompt in the same commit.

## Why this exists: the loop was a random walk

| iteration | rules it traded | $/day | days + | daily SD | worst day | trades/day |
|---|---|---|---|---|---|---|
| 1 | none at all | +509 | 6/10 | 1,024 | −1,180 | 6.5 |
| **2** | **rules_iter1** | **+620** | **9/10** | **724** | **−496** | **6.4** |
| 3 | rules_iter2 | +406 | 6/10 | 910 | −780 | 4.1 |

Three iterations, each rewriting up to ten rules at once, each run once. No selection pressure
existed anywhere: `rules = consolidate(...)` ran unconditionally, so the loop always carried
forward the **most recent** set rather than the **best** one. Iteration 4 would have been built
on iteration 3's weaker rules. And the prompt told the reviewer to *"drop what has stopped
earning its place"* — an instruction to change everything, every night.

---

## THE TWO THAT OUTRANK EVERYTHING

### LAW 0 — CONSISTENCY OUTRANKS RETURN. THIS IS THE FIRST LAW.
> Operator, 2026-10-06: *"Yes we absolutely want to maximise daily return. But consistency is
> more important. If we maximise one day to $2000 but then have 3 negatives or $200 days it's
> no good."*

A configuration earning the same money in a straight line is strictly better than one earning
it in lurches, and the lurching one is **not an improvement however large its average**.
> *Earned:* the exit-fix arm had the **highest median day of any arm (+$636)** and was the
> worst configuration tested — 6 of 10 days positive, worst day −$1,882, spread 3.6× its own
> mean. Ranking on the typical day would have selected it.

### LAW 0b — IMPROVE WHAT ALREADY WORKS. DO NOT TRY NEW THINGS.
Every change starts from the best-scoring configuration and edits **one** rule of it. You are
not exploring; you are tightening something that already earns money.
> *Earned:* three iterations of free rewriting gave $509 → $620 → $406/day and ended by
> discarding the best set.

### THE CONSISTENCY GATE — Law 0 made mechanical
Consistency cannot be one statistic: on the same ten days **mean and median disagree** about
which configuration is better — iteration 2 wins on mean ($620 vs $509), iteration 1 wins on
median ($595 vs $414). So a challenger is judged on **dominance**:

| # | must not worsen | champion (iter 2) |
|---|---|---|
| 1 | days positive | 9 of 10 |
| 2 | worst single day | −$496 |
| 3 | spread ÷ mean (CV) | 1.17 |
| 4 | **then** $/day must be higher | $620 |

CV rather than raw SD is deliberate: a configuration earning twice as much is allowed twice
the absolute spread, and comparing raw SD would reject every genuine improvement in scale.

Against that gate **every challenger measured so far is rejected** — iteration 1 (6/10,
−$1,180, CV 2.01), iteration 3 (6/10, −$780, CV 2.24), exit-fix (6/10, −$1,882, CV 3.61).
That is the gate working: each was worse at the thing that matters most.

⚠ It also refuses a **flat but tidy** challenger — consistency first does not mean consistency
only. `bible.gate()` returns *"consistency held but no more money"* and keeps the champion.

## THE TEN LAWS

### L1 — START FROM THE CHAMPION, NEVER A BLANK PAGE
The champion's rule text is the baseline. Reproduce it **verbatim** and change at most one
rule. You are editing a working configuration, not writing a new one.
> *Earned:* iteration 2 scored $620/day; iteration 3 replaced its rule set wholesale and
> scored $406. Nothing from the champion was deliberately preserved because nothing told the
> reviewer there was a champion.

### L2 — ONE RULE PER ITERATION
Exactly one. Not "one theme", not "a few related clauses".
> *Earned:* iteration 1→2 changed all ten rules. The result moved +$111/day, inside the
> ±$324 standard error, and not one dollar of it is attributable to any rule.

### L3 — DECLARE THE CHANGE AND ITS PREDICTED DIRECTION BEFORE IT RUNS
Name the rule, the edit, the observation that caused it, and which measured number should
move and which way. A prediction written afterwards is a story.
> *Built:* the `CHANGELOG:` section, required by `consolidate()`, split to its own file.

### L4 — A CHALLENGER MUST BEAT THE CHAMPION ON BOTH AXES, OR IT IS REVERTED
Higher $/day **and** no fewer positive days. Consistency is the operator's stated priority, so
a higher average bought with more losing days is not an improvement.
> *Built:* the champion ratchet. A rejected challenger is kept as
> `rules_iter<N>_rejected.txt` — recorded, never silently discarded.

### L5 — NEVER REVERSE A RULE ON ONE WEEK'S IMPRESSION
Reversing a rule requires evidence that **that rule** is what failed, not that the week went
badly.
> *Earned:* iteration 1 said *"Target 8-15 entries per session"* and *"a session with no
> trade is a failure"*. Iteration 2 replaced both with *"there is no quota and a flat session
> is not a failure"* — a 180° turn on the one lever the operator watches most. Trades/day fell
> 6.4 → 4.1 and $/day fell $620 → $406. Neither of us noticed the reversal until the rule sets
> were diffed, three iterations later.

### L6 — AN INTERIM IS NEVER A RESULT
Score only a complete, clean set of days. Never report, and never act on, a partial run.
> *Earned:* the exit-fix arm read **3 of 3 predictions met** on six days. The remaining four
> reversed it to **1 of 3**, $/day 698 → 294, worst day −$528 → −$1,882. The six happened to
> be the September half; the champion's strength is in August. A Telegram went out on the
> interim and had to be corrected.

### L7 — A POISONED DAY IS NOT A DAY
A day whose calls errored above 10% is not a trading decision and must never be scored,
reviewed, or inherited by `resume`.
> *Earned:* two days of a training week errored 125/138 and 138/138 during a token outage.
> One booked exactly **$0.00 with zero trades** and read as a flat session in every summary,
> and the nightly review then wrote the next rule set from it. Later, 16 of 20 A/B arms and 4
> of 10 exit-fix days went the same way on rate limits.

### L8 — CHANGING ONE RULE CHANGES THE WHOLE PATH
A single-clause edit is a clean comparison of two rule **sets**. It is **not** an isolation of
that clause, because the exit decides when the next entry happens. No causal claim about one
rule without a replicate arm.
> *Earned:* widening the exit reference was predicted to make it hold longer. It held
> **shorter** (median 47.5 → 45.0 min) and on 2026-08-20 entered the day's big leg **92% of
> the way in**, losing on all seven trades where the champion made +$1,386.

### L9 — DO NOT RE-DERIVE THE SETTLED LIST
Entries are a coin on a symmetric race (+0.2pp side-matched, n=174). Turn entries are a coin
at every multiple, timeframe and target tested. A bare stall is a coin. The money is in the
asymmetric payoff — 4 lots, no stop, hold to structure — not in entry timing.
> *Earned:* 119 exit calibrations and eleven months of studies failed before anyone recorded
> the operator's actual inputs.

### L10 — COUNTS BEFORE DOLLARS
$/day cannot be resolved on ten days: the daily spread is ~$1,000, so the standard error of a
ten-day mean is ~$229–324 — larger than the $180 gap to the $800 bar. **Median hold,
premature-exit rate, leg capture, side accuracy and trades/day are counts** and move far
outside their own noise. Judge on those; record the dollars.
> ⚠ This is **not** a claim that $300/day is immaterial — it is $75k a year. It means ten days
> cannot *measure* it. The answer is a better measurement (pairing, replicates), never
> dismissal.

---

## WHAT IS ALREADY ENFORCED IN CODE, AND WHAT IS ONLY WRITTEN HERE

| law | enforced by | status |
|---|---|---|
| L1 start from the champion | `CONSOLIDATE` prompt + the champion ratchet | **NEW 2026-10-06** |
| L2 one rule per iteration | `CONSOLIDATE` prompt | **NEW 2026-10-06** |
| L3 declare the change | `consolidate()` demands `CHANGELOG:` | built |
| L4 beat it on both axes or revert | `recursive_loop` champion ratchet | built |
| L5 no reversal on one week | `CONSOLIDATE` prompt | **NEW 2026-10-06** |
| L6 no interim results | `paired_arm` pairs on the intersection and names exclusions | built |
| L7 poisoned ≠ a day | `run_day` resume check, `night_guard`, `preflight_iteration` | built |
| L8 one rule ≠ isolation | this document + the arm's own docstring | written only |
| L9 settled list | `preflight_iteration.state_brief` | built |
| L10 counts before dollars | `paired_arm` frozen predictions; `preflight` audit | built |

⚠ L8 is deliberately not automated: it is a constraint on *interpretation*, and a script
cannot stop a person over-reading a result. It is in the preflight audit's prompt instead.

## THE LIVE DESK IS SEPARATE AND FROZEN
`shadow_runner` trades `rules_live_champion.txt` — a stable copy of the champion, which no
iteration can overwrite. The loop may churn; what paper-trades does not change until a
challenger beats the champion under L4 and a human repoints it.
