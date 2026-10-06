"""THE FINE-TUNING BIBLE — the single source of truth, injected into every prompt.

★★★ Operator, 2026-10-06: *"how do we make the AI always abide. Just like Claude code does.
If it sits outside CLAUDE.md you don't do it."*

That is the correct diagnosis of the enforcement problem. `CLAUDE.md` works not because it
exists but because it is **injected into every session automatically**. A bible in `docs/`
that one prompt happens to quote is a bible that binds one prompt. So:

  · THE LAWS LIVE HERE, as a constant — one place, importable, impossible to read "stale".
  · Every prompt that writes, reviews or judges a rule set injects `laws()`.
  · `tests/test_bible_is_enforced.py` FAILS if any of those prompts does not contain them.
    That test is the actual enforcement; everything else is intention.

⚠ I had already proved the point by failing it: the first attempt to add these laws patched
`recursive_loop`'s module DOCSTRING instead of its `CONSOLIDATE` prompt. Reading the diff
looked correct. Capturing the assembled prompt and grepping for each law showed L1, L2 and L5
**missing**. [[a-memory-is-not-a-rule-until-it-is-in-the-prompt]] and
[[a-written-rule-with-no-test-is-a-suggestion]], both earned on this desk, both repeated by me
in the commit that was supposed to honour them.
"""
from __future__ import annotations

# ── the two that outrank everything else ────────────────────────────────────────────────
PRIMARY = """★★★ LAW 0 — CONSISTENCY OUTRANKS RETURN. THIS IS THE FIRST LAW.
The operator, in his own words: *"Yes we absolutely want to maximise daily return. But
consistency is more important. If we maximise one day to $2000 but then have 3 negatives or
$200 days it's no good."*
A configuration that earns the same money in a straight line is strictly better than one that
earns it in lurches, and the lurching one is NOT an improvement however large its average.
Measured on this desk: the exit-fix arm had the HIGHEST median day of any arm (+$636) and was
the WORST configuration tested — 6 of 10 days positive, worst day −$1,882, and a daily spread
3.6× its own mean. A rule ranked on the typical day would have selected it.

★★★ LAW 0b — IMPROVE WHAT ALREADY WORKS. DO NOT TRY NEW THINGS.
Every change starts from the best-scoring configuration and edits ONE rule of it. You are not
exploring; you are tightening something that already earns money. Measured: three iterations
of free rewriting produced $509 → $620 → $406/day and ended by discarding the best set.
"""

# ── the consistency gate, which is Law 0 made mechanical ────────────────────────────────
GATE = """THE CONSISTENCY GATE — how Law 0 is actually scored, and why it is not one number.
On the same ten days, mean and median DISAGREE about which configuration is better:
iteration 2 wins on mean ($620 vs $509) while iteration 1 wins on median ($595 vs $414). So
consistency cannot be a single statistic, and a challenger is judged on DOMINANCE instead:

  A challenger REPLACES the champion only if it worsens NONE of these, and then earns more:
    1. days positive        must be >= the champion's
    2. worst single day     must be >= the champion's (no deeper hole)
    3. spread / mean (CV)   must be <= the champion's (scale-free, so a bigger
                            average is allowed a bigger absolute spread)
  and only then:
    4. $/day                must be > the champion's

Against the current champion (iteration 2: $620/day, 9/10 positive, worst −$496, CV 1.17) this
gate rejects every challenger so far — iteration 1 (6/10, −$1,180, CV 2.01), iteration 3
(6/10, −$780, CV 2.24) and the exit-fix arm (6/10, −$1,882, CV 3.61). That is the gate working:
each of those was worse at the thing that matters most.
"""

# ── the ten ─────────────────────────────────────────────────────────────────────────────
LAWS = """L1 — START FROM THE CHAMPION, NEVER A BLANK PAGE. You are shown the champion's rule
set and its score. Reproduce it VERBATIM and change at most ONE rule. Rules you are not
changing must come back word-for-word; rewording one you did not mean to change destroys the
only record of what changed.

L2 — ONE RULE PER ITERATION. Exactly one. Not "one theme", not "a few related clauses".
Iteration 1 to 2 changed all ten and moved $111/day, inside the ±$324 standard error of a
ten-day mean, so none of it is attributable to anything.

L3 — DECLARE THE CHANGE AND ITS PREDICTED DIRECTION BEFORE IT RUNS. Name the rule, the edit,
the observation that caused it, and which measured number should move and which way. A
prediction written afterwards is a story.

L4 — A CHALLENGER MUST PASS THE CONSISTENCY GATE AND THEN EARN MORE, OR IT IS REVERTED. See
the gate above. A rejected challenger is recorded, never silently discarded.

L5 — NEVER REVERSE A RULE ON ONE WEEK'S IMPRESSION. Reversing needs evidence that THAT RULE
failed, not that the week went badly. Iteration 1 said "Target 8-15 entries per session" and
"a session with no trade is a failure"; iteration 2 replaced both with "there is no quota and
a flat session is not a failure". Trades/day fell 6.4 to 4.1 and $/day fell $620 to $406. To
reverse a rule, use the word REVERSE in the CHANGELOG and name the number that justifies it.

L6 — AN INTERIM IS NEVER A RESULT. Score only a complete, clean set of days. The exit-fix arm
read 3 of 3 predictions met on six days; the remaining four reversed it to 1 of 3, $/day 698
to 294, worst day −$528 to −$1,882.

L7 — A POISONED DAY IS NOT A DAY. A day whose calls errored above 10% is not a trading
decision and must never be scored, reviewed or inherited. One such day booked exactly $0.00
with zero trades and read as a flat session in every summary.

L8 — CHANGING ONE RULE CHANGES THE WHOLE PATH. A single-clause edit compares two rule SETS; it
does not isolate that clause, because the exit decides when the next entry happens. Widening
the exit reference was predicted to lengthen holds and SHORTENED them.

L9 — DO NOT RE-DERIVE WHAT IS SETTLED. Entries are a coin on a symmetric race (+0.2pp
side-matched, n=174). Turn entries are a coin at every multiple, timeframe and target tested.
A bare stall is a coin. The money is in the asymmetric payoff — 4 lots, no stop, hold to
structure — not in entry timing.

L10 — COUNTS BEFORE DOLLARS. One week cannot resolve $/day: the daily spread is ~$1,000.
Median hold, premature-exit rate, leg capture, side accuracy and trades/day are COUNTS and
move well outside their own noise. Aim the one change at a count you can name.
⚠ This is NOT a claim that a few hundred dollars a day is immaterial — it is tens of thousands
a year. It means five days cannot MEASURE it.

A NULL ITERATION IS A LEGITIMATE OUTCOME. If the week gives no evidence that a specific rule
failed, return the champion's set UNCHANGED with "CHANGELOG: no change — the week gave no
reason to alter the rules." Churn is not progress.
"""

LAW_IDS = ("LAW 0", "LAW 0b", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10")


def laws() -> str:
    """The whole bible, for injection into a prompt. One call, one source."""
    return (f"=== THE FINE-TUNING BIBLE — THESE BIND YOU ===\n\n{PRIMARY}\n"
            f"{GATE}\n{LAWS}\n=== END OF THE BIBLE ===")


def gate(challenger: dict, champion: dict) -> tuple[bool, str]:
    """Law 0 / L4, mechanical. Returns (challenger_replaces_champion, why).

    Keys required on both: days_positive, worst_day, daily_sd, usd_per_day.
    ⚠ CV not raw SD: a configuration that earns twice as much is allowed twice the absolute
    spread. Comparing raw SD would reject every genuine improvement in scale.
    """
    need = ("days_positive", "worst_day", "daily_sd", "usd_per_day")
    for k in need:
        if challenger.get(k) is None or champion.get(k) is None:
            return False, f"cannot judge: {k} missing"
    cv_c = abs(challenger["daily_sd"] / challenger["usd_per_day"]) \
        if challenger["usd_per_day"] else float("inf")
    cv_h = abs(champion["daily_sd"] / champion["usd_per_day"]) \
        if champion["usd_per_day"] else float("inf")
    fails = []
    if challenger["days_positive"] < champion["days_positive"]:
        fails.append(f"days+ {challenger['days_positive']} < {champion['days_positive']}")
    if challenger["worst_day"] < champion["worst_day"]:
        fails.append(f"worst day {challenger['worst_day']:+,.0f} < {champion['worst_day']:+,.0f}")
    if cv_c > cv_h:
        fails.append(f"spread/mean {cv_c:.2f} > {cv_h:.2f}")
    if fails:
        return False, "CONSISTENCY GATE FAILED — " + "; ".join(fails)
    if challenger["usd_per_day"] <= champion["usd_per_day"]:
        return False, (f"consistency held but no more money: "
                       f"${challenger['usd_per_day']:+,.0f} <= ${champion['usd_per_day']:+,.0f}")
    return True, (f"passes the gate and earns more: ${challenger['usd_per_day']:+,.0f} vs "
                  f"${champion['usd_per_day']:+,.0f}, days+ {challenger['days_positive']} vs "
                  f"{champion['days_positive']}, spread/mean {cv_c:.2f} vs {cv_h:.2f}")
