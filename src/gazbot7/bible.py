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

# ── the laws that outrank everything else ────────────────────────────────────────────────
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

★★★ LAW 0c — NO CHANGE WITHOUT TRADES. ZERO GUESSING. THE EVIDENCE IS THE CHAMPION'S OWN TRADES.
The operator, 2026-10-06: *"Zero guessing as to what we should do… That needs to be written in"*
and *"Claude code rarely guesses. He always answers me based on real data."* He must never have
to supply the proposal, and you must never produce one from general trading wisdom.
A change to the rules is ADMISSIBLE only if it is derived from reading the champion's actual
trades against the tape picture, and it must NAME THE TRADES it would alter — for each one: the
day, the entry time, the entry and exit price, the exit reason the trade recorded — and say what
would have happened to that trade under the new wording, read off the tape. A change that cannot
name a specific trade is a guess and is REFUSED, however sensible it sounds. If the champion's
trades give no such evidence, the answer is "no change" (see NULL ITERATION below).
Trades are drawn from DEVELOPMENT weeks (the generator); the held-out weeks only SCORE the
result and are never read for ideas.

★★★ LAW 0d — CLAIM THE PROFIT. THIS IS A STANDING GOAL OF EVERY ITERATION.
The operator, 2026-10-07: *"The whole thing about exiting is to claim profit."* and *"They're
jumping in ok. And if Claude is monitoring, then when profit is decent. Take it!"*
Entries are not where the champion loses; the EXIT is. The champion has no rule that banks a
profit: it forbids exiting on a fixed gain, it exits on a structure break only, and that break
sits just beyond the entry — so a trade that ran in profit is cut only after it has given the
profit back. Measured on June 2026 (22 unseen days, now development data): of 126 exits the
model chose, 93 were losses, 54 of those 93 had been in profit first and 26 of them by 20pt or
more; the 3 trades the model never got to exit (window close) all won, +$1,932.
How it binds: every iteration asks where the champion's OWN trades sat in profit and handed it
back, and names them (Law 0c). A claim is the monitoring model's judgement from the picture,
made when profit is decent — never a fixed number (fixed-level claim calibrations against the
operator's own claims failed 119 times, and capturing 1-7% of a leg repeatedly is how a losing
day is built). It is still ONE rule per iteration (L2) and still judged by the consistency gate:
a claim that raises $/day but worsens days positive or the worst day is rejected like any other.
If no cited trade shows profit a specific wording would have banked, the answer is "no change".

★★★ LAW 0e — THE STRATEGY IS THE HEADLINE. EVERY OTHER LAW, RULE AND CHANGE SERVES IT.
The operator, 2026-10-07, in his own words: *"we are trying to buy at the start of the major
intraday leg and exit near the top. Now achieving both of those will be hard so at the start we
will buy late, half way up the leg and exit early to be safe. That is it. Simple. Then with each
iteration all we do is try and fine tune slightly and safely so we get in a little bit earlier
and exit a little bit later. Always exiting in profit!!!!!! My desired strategy is quite simple.
If we are doing things outside that then we need to simplify."*
THE CHECK. Every change you propose, review or judge must say in one line which of these it serves:
  (1) it enters a little EARLIER into the same proven leg;
  (2) it exits a little LATER while the trade is still in profit;
  (3) it keeps exits IN PROFIT.
A change that serves none of the three is CUT. A rule set that contains anything serving none of
them is to be SIMPLIFIED, not added to. "Slightly and safely" means one small step per iteration
(L2) — never a jump to entering at the start of the leg or exiting at its top.
NO STOPS. The operator, 2026-10-07: *"using stops with this style of trading won't work. You'll
be stop lossed out all the time. Hence the reason Claude is watching so we can make calls."* The
exit is the monitoring model's call from the picture — never a stop, never a fixed level. A
pullback inside a good leg is not a reason to leave; the leg itself being undone is.
TRADES PER DAY. 3-6 is a description of a normal day, NOT a limit. When the tape keeps grinding
one way for a large part of the day, keep jumping in and harvesting $200-300 at a time —
*"That's great trading."* Judge each trade (did it join a proven leg in its direction and come out
in profit), never the count. No prompt, rule or review may cap the count.
THIS OUTRANKS ANY INSTRUCTION BELOW OR ELSEWHERE that pushes toward holding for a bigger leg
capture while in profit: a profit taken at the first honest sign of tiring is CORRECT under this
strategy, and leaving a bigger one on the table is what is improved slowly, one cited rule at a
time, not by default.
THE RESTART (granted by the operator, 2026-10-07: *"If things have been dirtied up until now I'm
ok to start again"* / *"make it part of the constitution and let's start again"*). The S line
begins from this strategy and an EMPTY rule set — iteration 2's ten rules are NOT carried into it.
L1 applies within the S line from its first rule onward. A SECOND OPERATOR DECLARATION, 2026-10-07:
*"Forget the initial iterations. Start fresh from S1. That will be our baseline. The others had
the wrong brief."* S1 (empty rules, BRIEF_V2) is the BASELINE; iterations 1 to 5 ran on the wrong
brief and are history, not the thing to beat. The S line is gated against ITSELF (S2 onward must
dominate S1 under the gate below) once S1 has been measured clean. The live shadow_runner is not
touched by this; nothing may repoint it but the operator. A RESTART IS THE OPERATOR'S ALONE:
no iteration, review or audit may declare one.
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

AS OF 2026-10-07 THE IT LINE IS HISTORY (operator restart: S1 is the baseline). The S line's
champion is S1 once it has been measured clean; until then there is no S champion and nothing may
be promoted. For the historical IT line, the live record is reports/recursive_loop/CHAMPION.json
(iteration 2: $620/day, 9/10 positive, worst −$496, CV 1.17), and against it this gate rejected
iteration 1 (6/10, −$1,180, CV 2.01), iteration 3 (6/10, −$780, CV 2.24) and the exit-fix arm
(6/10, −$1,882, CV 3.61): each was worse at the thing that matters most.
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

L4 — A CHALLENGER MUST PASS THE CONSISTENCY GATE AND THEN EARN MORE, OR IT IS REVERTED.
Days positive, worst single day and spread/mean (CV) may NONE of them worsen against the
champion, and only then must $/day be higher (the gate above). A rejected challenger is
recorded, never silently discarded.

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
A bare stall is a coin. Hunting for a new entry SIGNAL or a turn call is therefore closed. The
money is in the asymmetric payoff — 4 lots, no stop, and the model itself is the exit.
★ EXCEPTION, BY LAW 0e(1): entering a little EARLIER into the same proven leg is the strategy's
own improvement path and is NOT re-deriving the settled list. A change that moves the entry
earlier along the SAME proven leg — a leg the tape has already confirmed (leg confirmed first,
then entered earlier along it; never a prediction of the next leg) — and cites recorded trades
(Law 0c), is admissible.

L10 — COUNTS BEFORE DOLLARS. One week cannot resolve $/day: the daily spread is ~$1,000.
Median hold, premature-exit rate, leg capture, side accuracy and trades/day are COUNTS and
move well outside their own noise. Aim the one change at a count you can name.
⚠ This is NOT a claim that a few hundred dollars a day is immaterial — it is tens of thousands
a year. It means five days cannot MEASURE it.

A NULL ITERATION IS A LEGITIMATE OUTCOME. If the week gives no evidence that a specific rule
failed, return the champion's set UNCHANGED with "CHANGELOG: no change — the week gave no
reason to alter the rules." Churn is not progress.
"""

LAW_IDS = ("LAW 0", "LAW 0b", "LAW 0c", "LAW 0d", "LAW 0e", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10")

L4_ONE_LINE = ("a challenger replaces the champion only if days-positive, worst day and "
               "spread/mean (CV) do not worsen, and $/day is higher")


def _heading_re(law_id: str) -> str:
    import re
    return (rf"^★★★ {re.escape(law_id)} — " if law_id.startswith("LAW") else rf"^{re.escape(law_id)} — ")


def _law_blocks() -> dict[str, str]:
    """Each law's whole text (heading line to the line before the next heading), whitespace-
    normalised, cut from the canonical PRIMARY / LAWS constants."""
    import re
    blocks: dict[str, str] = {}
    for src in (PRIMARY, LAWS):
        cur, buf = None, []
        for ln in src.splitlines() + ["\0"]:
            hit = next((i for i in LAW_IDS if re.search(_heading_re(i), ln)), None)
            if hit or ln == "\0":
                if cur:
                    blocks[cur] = " ".join(" ".join(buf).split())
                cur, buf = hit, [ln] if hit else []
            elif cur:
                buf.append(ln)
    return blocks


def missing_laws(text: str) -> list[str]:
    """Laws absent or GUTTED in `text`. Two checks, both required per law:
      1. the HEADING is present, anchored at line start — a bare substring check passes when
         "L1" is found inside "L10" or "LAW 0" inside the laws() preamble;
      2. the law's WHOLE canonical text is present (whitespace-normalised) — a prompt that kept
         the heading and lost the body told the model a law exists and not what it says."""
    import re
    flat = " ".join(text.split())
    blocks = _law_blocks()
    out = []
    for i in LAW_IDS:
        if not re.search("(?m)" + _heading_re(i), text) or blocks.get(i, "\0") not in flat:
            out.append(i)
    return out


def laws() -> str:
    """The whole bible, for injection into a prompt. One call, one source."""
    return (f"=== THE FINE-TUNING BIBLE — THESE BIND YOU ===\n"
            f"Every law below serves the strategy in LAW 0e: LAW 0e says what a rule is FOR, and "
            f"LAW 0 (consistency) still decides which configuration is BETTER.\n\n{PRIMARY}\n"
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
    # ★2026-10-07 A NON-POSITIVE MEAN HAS NO MEANINGFUL CV. abs(sd/mean) made a small-negative baseline
    # read as a HUGE spread that any challenger clears for free. Such a mean gets cv = inf, and a
    # champion with no meaningful CV can be replaced only by a challenger that actually earns (> $0/day).
    cv_c = challenger["daily_sd"] / challenger["usd_per_day"] \
        if challenger["usd_per_day"] > 0 else float("inf")
    cv_h = champion["daily_sd"] / champion["usd_per_day"] \
        if champion["usd_per_day"] > 0 else float("inf")
    if champion["usd_per_day"] <= 0 and challenger["usd_per_day"] <= 0:
        return False, ("baseline is not profitable (CV undefined) and the challenger is not either: "
                       f"${challenger['usd_per_day']:+,.0f} vs ${champion['usd_per_day']:+,.0f}")
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


TRADE_FIELDS = ("day", "entry_time", "entry", "exit", "reason", "would_have")
NUMERIC_TOL = 0.5      # points / minutes; trades are stored rounded


def admissible(change: dict, find_trade) -> tuple[bool, str]:
    """Law 0c, mechanical. `change["trades"]` is a list of citations, each carrying TRADE_FIELDS.
    `find_trade(day, entry_time, entry)` returns the recorded trade or None.

    A citation counts only if (a) every field is filled and (b) the trade EXISTS in the
    champion's recorded runs with that entry price and exit reason — a trade the proposer
    remembered wrongly, or invented, is exactly the guess this law forbids.
    """
    cites = change.get("trades") or []
    if not cites:
        return False, "LAW 0c: the change names no trades — it is a guess"
    for i, c in enumerate(cites, 1):
        gap = [f for f in TRADE_FIELDS if not str(c.get(f, "")).strip()]
        if gap:
            return False, f"LAW 0c: citation {i} is missing {gap}"
        t = find_trade(c["day"], c["entry_time"], float(c["entry"]))
        if not t:
            return False, (f"LAW 0c: citation {i} ({c['day']} {c['entry_time']} @ {c['entry']}) "
                           "matches no recorded trade")
        if abs(float(t["exit"]) - float(c["exit"])) > 0.5 or \
                str(c["reason"]).strip() not in (str(t.get("why", "")) + " " + str(t.get("entry_reason", ""))):
            return False, f"LAW 0c: citation {i} misstates the trade's exit or recorded reason"
        # the numbers a rule is justified FROM (how far up it got, what it lost, how long it was
        # held) are checked too, whenever the citation states them — "87pt in profit at its
        # best" is the whole case for a claim rule, and it was taken on trust.
        for key, rec_key in (("recorded_pts", "points"), ("peak_pt", "peak_pt"), ("held_min", "held_min")):
            if str(c.get(key, "")).strip() != "" and t.get(rec_key) is not None and \
                    abs(float(c[key]) - float(t[rec_key])) > NUMERIC_TOL:
                return False, (f"LAW 0c: citation {i} states {key}={c[key]} but the recorded trade "
                               f"has {rec_key}={t[rec_key]}")
        if str(c.get("side", "")).strip() and t.get("side") and \
                str(c["side"]).strip().upper() != str(t["side"]).strip().upper():
            return False, f"LAW 0c: citation {i} states side={c['side']} but the recorded trade is {t['side']}"
    return True, f"LAW 0c satisfied: {len(cites)} recorded trade(s) cited and verified"
