#!/usr/bin/env python3
"""THE ACTION CARD for the week to Friday 2026-09-18 — REFOCUSED REPORT.

★★★ THIS CARD IS BUILT FROM THREE SECTIONS AND NOTHING ELSE.

The report was refocused on 2026-09-18 onto ONE subject: the operator's own trading and whether it
can be automated. Its body is four sections — op_record, op_conditions, automation_gap, run_charts
— and every row below is lifted from the RANKED SHORTLIST that one of the first three ends with.
Nothing here comes from the retired tournament phases (part1_live, part2_shadow, part25_musings,
part2_6_router, movement*, rehab, gf_*). Those fragments are still on disk and are a MONTH old;
sourcing a play from one would put last month's tournament review on this week's card.

Why this is a script and not a hand-edited JSON: the previous card (58 plays, `plays.json.pre-0918`)
was the 2026-09-04 cycle's, and the report leads with the card. A refocused report shipping the
previous subject's card is the one failure a reader cannot catch — every row would be internally
consistent and simply about a different desk.

★ THE SHAPE OF THIS WEEK'S CARD, AND WHY IT IS SHORT. There are 21 rows against 58 last cycle, and
almost none of them change how he trades. The reason is on the card itself and is MONDAY #1: there
are 36 recorded presses and ZERO recorded passes, so every behavioural finding in this report is
one side of a decision boundary. A description is not a rule. The rows that ARE actionable are
therefore parameter changes, instrument fixes and one dataset — none of which need his judgement
modelled first.

  python3 scripts/friday_v7_plays_0918.py
"""
from __future__ import annotations

import json
import pathlib

OUT = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"


def P(**kw) -> dict:
    """A play. Every field the build's renderer reads is required — a missing one is a hole in
    the most-read table in the document, and play_meta() raises rather than printing a blank."""
    need = ("id", "window", "rank", "tier", "topic", "play", "number", "section_ref",
            "verification", "arms_when", "exit", "kill", "suggested_mode", "owner", "revert")
    missing = [k for k in need if not kw.get(k)]
    if missing:
        raise SystemExit(f"FATAL — play {kw.get('id')} is missing {missing}")
    kw.setdefault("money_gbp", 0)
    return kw


PLAYS = [

    # ══════════════════════════════════════════════════════════════════════════════════
    # MONDAY — at the desk. Three rows, and the first of them is the whole report.
    # ══════════════════════════════════════════════════════════════════════════════════
    P(
        id="press-the-pass-button-0918",
        window="MONDAY", rank=1, tier="BLOCKER",
        topic="★★ PRESS THE PASS BUTTON. This is the highest-value thing on the desk and it costs "
              "you one tap",
        play="<strong>Every time you look at the tape and do NOT trade, press <code>PASS</code>.</strong> "
             "Not sometimes — every time, including the times it feels obvious. Roughly 30 passes over "
             "the next two weeks and this desk can, for the first time in eleven months, learn what "
             "separates a moment you take from a moment you leave.",
        mechanism="<code>data/operator_reads.jsonl</code> holds <strong>78 recorded presses, 36 of them "
                  "entries, and 0 passes</strong>. The PASS button shipped on Wednesday and has never "
                  "been pressed. Every threshold, band and description in Sections 1, 2 and 3 is "
                  "therefore fitted on positives only.",
        rationale="The desk's own written fitting threshold is 30 labelled examples, and it was written "
                  "for positives AND negatives. On that count the real figure is <strong>zero</strong>, "
                  "not 36 — and no amount of waiting fixes it, because a press only ever generates a "
                  "positive. This is the one row on the card that is genuinely blocking: Section 2's "
                  "continuation description cannot become a filter without it, Section 1 cannot promote "
                  "a single observation to a rule without it, and Section 3's decision half stays at "
                  "&ldquo;no&rdquo; until it exists.",
        number="<strong>36 positives, 0 negatives.</strong> 78 presses across 4 sessions. Negatives from "
               "the alternative source (declined <code>leg_watch</code> pages, BUILD&nbsp;#1) accrue at "
               "~21/week against ~7/week for positives, so positives are the binding side either way "
               "and the pool reaches 30/30 in about <strong>3.6 weeks</strong> — or roughly one week "
               "if MONDAY #2 (drop-the-page-band-to-15-0918) ships alongside it.",
        section_ref="§2.1 (the sample), §2.5 lead 1 (HIGHEST VALUE ON THE DESK); §1 §8 row 1 (BLOCKER); "
                    "§3.3 (what is not automatable, and exactly how far off).",
        verification="<code>python3 -c \"import json;print(sum(1 for l in "
                     "open('data/operator_reads.jsonl') if json.loads(l)['kind']=='pass'))\"</code> — "
                     "it reads 0 today. Any number above zero next Friday is this row working.",
        arms_when="Nothing arms. It is a habit, and it is the cheapest item on this card.",
        exit="n/a.",
        kill="If 30 passes land and the press/pass boundary STILL does not separate on any of the "
             "features in §2, that is a real answer and this desk stops trying to model entry "
             "selection. That outcome would be worth knowing and is currently unreachable.",
        suggested_mode="do it",
        owner="Garrath — at the desk, every session",
        revert="n/a. ★ Nothing else in this report is unblocked without it, which is why it is #1 "
                "despite having no dollar figure attached.",
    ),
    P(
        id="drop-the-page-band-to-15-0918",
        window="MONDAY", rank=2, tier="MEASURED",
        topic="Drop <code>leg_watch</code>'s first page from 60 minutes of leg age to 15 — and route "
              "it to the dashboard, not the phone",
        play="<strong>Change one number and one destination.</strong> The detector is already right; it "
             "is speaking forty minutes after you have acted. At a 15-minute band the same detector, "
             "unchanged in every other respect, precedes <strong>82%</strong> of your entries.",
        mechanism="<code>leg_watch</code> saw a live 1&times;ATR leg at <strong>33 of your 34</strong> "
                  "entries in its window and took your side at 26 of them. It told you about "
                  "<strong>3</strong>. Its first page fires at 60 minutes of leg age; the median leg "
                  "dies at <strong>22 minutes</strong> and the median leg you press into is "
                  "<strong>28 minutes old</strong>. The machine is watching the right thing at the "
                  "wrong time.",
        rationale="This is the only row on the card with a significance test behind it and no model in "
                  "it. Scored against a session-blocked permutation of your own presses: the policy "
                  "running today precedes 24% of entries against a chance rate of 18%, "
                  "<strong>P&nbsp;=&nbsp;0.24 — no separation at all</strong>. At 15 minutes it is 82% "
                  "against 56%, <strong>P&nbsp;=&nbsp;0.0009</strong>. 10 minutes still clears (0.015); "
                  "30 minutes does not (0.43). That is an edge between 15 and 30, not a plateau, so the "
                  "band matters and 15 is the measured end of it.",
        number="<strong>82% coverage at P&nbsp;=&nbsp;0.0009</strong>, against 24% at P&nbsp;=&nbsp;0.24 "
               "today. Price: your phone goes from <strong>7 to 32 pages a day</strong> — which is the "
               "entire reason for the dashboard half of this row.",
        section_ref="§3.1 (delivery, not detection) and §3.2 (the page band, priced, with the null); "
                    "§3.5 row 1, ranked the best thing in that section.",
        verification="<code>scripts/leg_survival.py</code> for the leg census; the permutation is "
                     "re-runnable against <code>data/operator_reads.jsonl</code> and the "
                     "<code>gazbot7-leg-watch</code> journal. Freeze the band on Monday and count "
                     "coverage forward.",
        arms_when="On the config change. Nothing about the detector's definition moves.",
        exit="n/a — it is an alert, never a filter and never an order.",
        kill="<strong>34 presses, four days, and the 15 was chosen off this week's own curve.</strong> "
             "Freeze it and measure forward: if next week's forward coverage comes in below ~50%, or "
             "if the page volume makes you stop reading them, put it back to 60 and say so. An "
             "in-sample band that is never re-measured is a fitted number wearing a P-value.",
        suggested_mode="ship it Monday",
        owner="Claude — one config change to the leg-watch band + dashboard route",
        revert="One number in the leg-watch config. ★ No fitting on your judgement, no negatives "
               "required, and it is reversible in a minute.",
        money_gbp=0,
    ),
    P(
        id="keep-the-event-day-standaside-0918",
        window="MONDAY", rank=3, tier="MEASURED",
        topic="Keep standing aside on event days — as a PAGE, never as a bench",
        play="<strong>Leave the calendar and the T-60/T-15 pages exactly as they are and keep taking "
             "them seriously.</strong> They are already built and already running. What this row asks "
             "for is that they stay a prompt to you and never become an automatic bench.",
        mechanism="<code>data/event_calendar.json</code> plus the T-60/T-15 pager. The report week held "
                  "exactly one calendar event — <strong>FOMC, Wednesday 2026-09-16, 20:00 Paris</strong> "
                  "— and it was the week's worst day.",
        rationale="FOMC Wednesday was <strong>&minus;$833.00 over 6 entries</strong> and the only day in "
                  "the week that lost more than a hundred dollars. Over the book's life event days run "
                  "<strong>&minus;$1,518.49 across 12 entries</strong> against "
                  "<strong>+$1,843.55 over 80 ordinary ones</strong>. And the run charts show the "
                  "mechanism plainly: he was flat through the release itself and then bought at "
                  "<strong>T+52 with the slide still running</strong> for &minus;$1,272.00.",
        number="<strong>+$166.60 a day this week</strong> / <strong>+$54.23 a session</strong> over the "
               "book / +$379.62 per event day avoided. FOMC ran MNQ at <strong>2.7&ndash;3.5&times;</strong> "
               "a normal 30-minute window on both FOMC days in our tape (98th/100th percentile) and MGC "
               "at <strong>6.6&times;</strong> its median.",
        section_ref="§1 §5 (by event day, refreshed with this week's FOMC) and §1 §8 row 3; §3.4(b); "
                    "§3.5 row 2. The run charts render the FOMC hour on both instruments.",
        verification="<code>data/event_calendar.json</code> is regenerated and human-verified; the "
                     "event-day split is re-derivable from <code>trades</code> against it.",
        arms_when="Already armed. The pages fire on the calendar.",
        exit="n/a.",
        kill="<strong>Four event days, one of them positive at +$224.50, and the split was chosen after "
             "seeing the losses.</strong> The Wednesday damage was also ONE entry at T+52, not the "
             "session — so this is nowhere near strong enough to become a bench. If the next four event "
             "days are net green, it dies.",
        suggested_mode="carry on",
        owner="Garrath — it is a page, and the decision stays yours",
        revert="n/a. ★ Note what this row deliberately does NOT say: it does not say block the book, "
               "because a bench can only ever remove trades and this book's event-day sample is four "
               "days deep.",
    ),

    # ══════════════════════════════════════════════════════════════════════════════════
    # SATURDAY — instrument faults. None of these change a threshold; all of them are
    # reasons a number in this report, or a number he is SHOWN at the desk, may be wrong.
    # ══════════════════════════════════════════════════════════════════════════════════
    P(
        id="anchor-drift-to-the-cme-session-0918",
        window="SATURDAY", rank=1, tier="FIX — DEFECT",
        topic="★ <code>drift</code> is blind before 13:30Z — and that is two thirds of his trading",
        play="<strong>Anchor the drift detector's day to the CME session (22:00Z), or fall back to a "
             "trailing 24 hours</strong> — which is what <code>tape_reader</code> already does for its "
             "bars. Until this is fixed the automated path cannot even LOOK at most of his entries.",
        mechanism="<code>drift.read</code> is gated to 13:30&ndash;21:00Z. Outside that window it "
                  "returns <code>no 5s rows since 13:30Z today</code> and the caller carries on.",
        rationale="This is the biggest single instrument fault in the report, measured on his own "
                  "record: <strong>51 of 78 presses and 24 of 36 entries</strong> returned the blind "
                  "reading. The other 12 all read <code>confirmed=false</code>. So for the majority of "
                  "his trading the desk's drift signal is not wrong — it is <em>absent</em>, and absent "
                  "reads as neutral to everything downstream. He trades the European morning heavily "
                  "(20 of 39 entries this week were before 13:00Z); the detector is switched off for "
                  "all of it.",
        number="<strong>51 of 78 presses / 24 of 36 entries</strong> returned no rows. 0 of 78 returned "
               "a confirmed drift read.",
        section_ref="§2.5 lead 3 (FIX — DEFECT).",
        verification="Call <code>drift.read()</code> at 08:00Z on Monday. Today it returns "
                     "<code>no 5s rows since 13:30Z today</code>; after the fix it returns a real read.",
        arms_when="On the code change. No threshold moves.",
        exit="n/a.",
        kill="None needed — it is a defect, not a hypothesis. ⚠ But note what fixing it does NOT do: it "
             "does not make drift predictive. It makes drift <em>measurable</em> outside RTH, which is "
             "the precondition for ever finding out.",
        suggested_mode="fix it",
        owner="Claude — one session anchor in the drift reader",
        revert="Revert the anchor. ★ Related, same species, same fix: SATURDAY&nbsp;#2.",
    ),
    P(
        id="anchor-tape-reader-session-window-0918",
        window="SATURDAY", rank=2, tier="FIX — INSTRUMENT",
        topic="<code>tape_reader</code>'s &ldquo;day open/high/low&rdquo; splices yesterday afternoon "
              "onto this morning",
        play="<strong>Anchor <code>tape_reader</code>'s session window to 22:00Z</strong>, the same "
             "anchor SATURDAY&nbsp;#1 asks for. This is about what you are SHOWN, not about any "
             "conclusion in this report.",
        mechanism="The &ldquo;session&rdquo; window does not start at the CME reopen, so it carries the "
                  "previous afternoon's bars into the current morning's day-open, day-high and day-low. "
                  "On 2026-09-14 its 203 &ldquo;session bars&rdquo; were Sunday night plus Monday "
                  "morning spanning an eleven-hour hole.",
        rationale="Position-in-range is REFUTED as an entry condition (NOT-AN-ACTION&nbsp;#2), so no "
                  "conclusion in this document moves when this is fixed — that was checked, and it is "
                  "why this is #2 and not #1. What it changes is the number on his screen: a day-high "
                  "that includes yesterday afternoon is not the day's high, and he reads it live.",
        number="<strong>203 bars on 2026-09-14</strong> labelled &ldquo;session&rdquo;, spanning an "
               "11-hour gap. No conclusion in §2 changes when corrected (checked).",
        section_ref="§2.5 lead 8 (FIX — INSTRUMENT).",
        verification="Print <code>tape_reader</code>'s session bar count and first bar timestamp at "
                     "07:00Z Monday; the first bar should be 22:00Z Sunday, not Friday afternoon.",
        arms_when="On the code change.",
        exit="n/a.",
        kill="None — it is a defect. ★ It is ranked below SATURDAY&nbsp;#1 precisely because nothing in "
             "this report depends on it; that is the honest reason, not a judgement about severity.",
        suggested_mode="fix it",
        owner="Claude — one session anchor in tape_reader",
        revert="Revert the anchor.",
    ),
    P(
        id="loss-limit-pages-a-false-claim-0918",
        window="SATURDAY", rank=3, tier="FIX — DEFECT",
        topic="★ The $250 daily loss limit pages you a claim its own journal contradicts",
        play="<strong>Drive the notification sentence from the <code>changed</code> list the guard "
             "actually wrote</strong>, not from a hard-coded string. A guard that reports an action it "
             "did not take is worse than a guard that stays quiet.",
        mechanism="The notify string reads &ldquo;All six gates benched&rdquo;. The journal for the same "
                  "firing reads <code>\"benched\": []</code>. Every gate the limit can reach was already "
                  "<code>=off</code>, so the guard is structurally incapable of doing the thing it "
                  "announces.",
        rationale="It fired <strong>twice this week</strong>, benched <strong>zero</strong> gates both "
                  "times, and paged him both times saying it had benched six. This is the "
                  "instrument-reports-healthy failure in its purest form: the page is the only evidence "
                  "a human sees, and it is manufactured.",
        number="<strong>Fired 2&times;, benched 0, paged 2&times;</strong> claiming six.",
        section_ref="§3.4(c) and §3.5 row 6.",
        verification="Grep the notify call site for the literal string, then compare against the "
                     "<code>benched</code>/<code>changed</code> key written to the same journal record.",
        arms_when="On the code change.",
        exit="n/a.",
        kill="None — it is a defect.",
        suggested_mode="fix it",
        owner="Claude — one f-string driven from the guard's own return value",
        revert="Revert the string. ★ Same subsystem as SATURDAY&nbsp;#4 and "
               "NOT-AN-ACTION&nbsp;#4; fix them together.",
    ),
    P(
        id="loss-limit-counts-fabricated-fills-0918",
        window="SATURDAY", rank=4, tier="FIX — DEFECT",
        topic="★ The loss limit's trigger can be moved by a price that never printed",
        play="<strong>Put a <code>data_quality IS NULL</code> filter in <code>session_pnl()</code>.</strong> "
             "It is the desk's standing convention everywhere else and this reader was missed.",
        mechanism="<code>session_pnl()</code> sums every closed row for the session with no "
                  "<code>data_quality</code> filter, so a row the desk has already marked known-bad "
                  "counts towards a guard that can halt trading.",
        rationale="Tuesday's trip read <strong>&minus;$418.50</strong>. That is "
                  "<strong>&minus;$114.00 real and &minus;$304.50 fabricated</strong> by the paper "
                  "engine, which invented the price on 3 of that entry's 4 lots. On the real number the "
                  "session was <em>below</em> the limit and the guard should not have fired at all.",
        number="Tuesday 2026-09-15: trigger read &minus;$418.50 = <strong>&minus;$114.00 real "
               "+ &minus;$304.50 fabricated</strong>.",
        section_ref="§3.4(c) and §3.5 row 7; the BADFILL row is named in §1 §1 and excluded from every "
                    "total in this report.",
        verification="<code>sqlite3 data/gazbot7.db \"SELECT data_quality FROM trades WHERE "
                     "id=895\"</code> → the <code>BADFILL:paper_engine_0.1pct_fabrication_3of4_lots_"
                     "20260915</code> tag. Then re-run <code>session_pnl()</code> for that date.",
        arms_when="On the code change.",
        exit="n/a.",
        kill="None — it is a defect.",
        suggested_mode="fix it",
        owner="Claude — one WHERE clause",
        revert="Revert the clause.",
    ),
    P(
        id="event-alert-needs-a-dry-run-0918",
        window="SATURDAY", rank=5, tier="FIX — DEFECT",
        topic="A hand-run of <code>event_alert.py</code> wrote a live <code>PAGED</code> line into the "
              "record",
        play="<strong>Give <code>event_alert.py</code> a <code>--dry-run</code> that logs nowhere</strong>, "
             "or stamp manual runs so they can be filtered out.",
        mechanism="<code>2026-09-18T07:04:03Z PAGED T-15 FOMC</code> sits in the log — off the "
                  "<code>*:0/5:30</code> timer cadence, two days after the only FOMC in the calendar, "
                  "with the timer's own run at 07:05:30 logging &ldquo;nothing in a band&rdquo; thirty "
                  "seconds later.",
        rationale="It is small and it is exactly the kind of small that corrupts a score. It cost this "
                  "report one false LED and <strong>would have inflated the alerting measurement in "
                  "§3.2 by 25%</strong> had it not been caught — and §3.2 is the evidence behind "
                  "MONDAY&nbsp;#2.",
        number="<strong>1 fabricated PAGED line</strong>; would have inflated the §3.2 alerting score by "
               "<strong>25%</strong>.",
        section_ref="§3.5 row 8.",
        verification="Diff the PAGED timestamps against the timer's <code>*:0/5:30</code> cadence — a "
                     "line that is not on the cadence was hand-run.",
        arms_when="On the flag.",
        exit="n/a.",
        kill="None — it is a defect.",
        suggested_mode="fix it",
        owner="Claude — one argparse flag",
        revert="Drop the flag.",
    ),
    P(
        id="chase-the-target100-mispriced-exit-0918",
        window="SATURDAY", rank=6, tier="DEFECT",
        topic="A <code>TARGET_100</code> rung booked a fill 79.5 points BELOW the entry it was supposed "
              "to take $100 a lot above",
        play="<strong>Read trade id 868 and find out what price that exit actually saw.</strong> Small "
             "money; a target exit reporting a price its own trigger cannot have produced is not small.",
        mechanism="Trade id 868, 2026-09-11: long at 29,320.25, out at 29,240.75 on a "
                  "<code>TARGET_100</code> exit — <strong>&minus;$160.50</strong>. A $100-a-lot rung on "
                  "MNQ is +50 points; this booked &minus;79.5.",
        rationale="<strong>It is the only one.</strong> There are 25 <code>TARGET_100</code> exits in "
                  "the whole clean record and <strong>24 of them booked between +$97.50 and "
                  "+$132.25</strong> — including all <strong>fourteen</strong> in the report week. "
                  "This one landed <strong>129.5 points</strong> from the level it names. One row, and "
                  "it is outside the report week, which is why it is last in this window.",
        number="<strong>1 row of 25, &minus;$160.50</strong>, against 24 that booked +$97.50 to "
               "+$132.25 (14 of them this week).",
        section_ref="§1 §8 row 6 (DEFECT); §1 §6 for how the week's exits ended.",
        verification="<code>sqlite3 data/gazbot7.db \"SELECT * FROM trades WHERE id=868\"</code>, then "
                     "the rider journal for that timestamp.",
        arms_when="Nothing arms. It is an investigation.",
        exit="n/a.",
        kill="If it turns out to be a mislabelled manual claim, close it and move on. n=1.",
        suggested_mode="investigate",
        owner="Claude — one journal read",
        revert="n/a.",
    ),

    # ══════════════════════════════════════════════════════════════════════════════════
    # BUILD — the measurement queue. One of these (the label harvest) is the only thing
    # on the card that can unblock MONDAY #1 without waiting on the PASS button.
    # ══════════════════════════════════════════════════════════════════════════════════
    P(
        id="harvest-declined-pages-as-negatives-0918",
        window="BUILD", rank=1, tier="ENABLER",
        topic="★★ Turn the paged legs into LABELS — every page you decline is a negative example",
        play="<strong>Record the outcome of every <code>leg_watch</code> page while your phone is "
             "awake.</strong> A page you see and do not act on is a negative, and it is free. This is "
             "the only item on the card that can unblock MONDAY&nbsp;#1 without waiting on the PASS "
             "button.",
        mechanism="<code>leg_watch</code> already pages. What is missing is the disposition — the join "
                  "between a page and whether an entry followed it inside a window.",
        rationale="The dataset already half exists: <strong>5 positives and 15 negatives</strong> are "
                  "recoverable from the 25 pages actually sent, plus 5 more that nobody saw. Negatives "
                  "accrue at <strong>21/week</strong> and positives at <strong>7/week</strong>, so "
                  "<em>positives</em> are the binding side — which is why this row supports MONDAY&nbsp;#1 "
                  "rather than replacing it. At the current 60-minute band the pool reaches 30/30 in "
                  "about 3.6 weeks; at MONDAY #2 (drop-the-page-band-to-15-0918)'s 15-minute band, in roughly one.",
        number="<strong>5 positives / 15 negatives</strong> already held. 30/30 in ~3.6 weeks at the "
               "current band, ~1 week at a 15-minute band. Direct P&amp;L: <strong>$0/day</strong> — "
               "this buys a dataset, not a trade.",
        section_ref="§3.5 row 3 (ENABLER); §3.3 for what the missing negatives actually block.",
        verification="Count rows in the disposition store next Friday. It does not exist today.",
        arms_when="Nothing arms. It is a log.",
        exit="n/a.",
        kill="If the negatives turn out to be indistinguishable from the positives on every feature in "
             "§2, that is the same real answer MONDAY&nbsp;#1's kill line describes, reached sooner.",
        suggested_mode="build it",
        owner="Claude — one disposition log joined to the leg-watch pages",
        revert="Delete the log. ★ It writes nothing to the order path.",
    ),
    P(
        id="the-eight-hour-stopwatch-0918",
        window="BUILD", rank=2, tier="MEASURED",
        topic="The eight-hour stopwatch — a hard flat-out at 8h, which needs no model and no judgement",
        play="<strong>Build the stopwatch, but ship it knowing this week says it would have earned "
             "nothing.</strong> It is a clock, not a rule about your judgement: no fitting, no "
             "negatives, no threshold on the tape.",
        mechanism="A hard flat at eight hours of hold time, on top of the existing 20:40Z clock.",
        rationale="Over the book's life <strong>4 entries held past eight hours, 0 winners, "
                  "&minus;$6,612.44</strong> — and every other entry ever made adds to +$6,937.50. That "
                  "is a &minus;$228.02 drag per session traded. <strong>It did not recur this week:</strong> "
                  "0 of 39 entries reached eight hours, longest 7h01m. So on this week's tape it earns "
                  "$0.00 and is pure insurance.",
        number="Lifetime it recovers <strong>+$1,720.00 over 28 sessions = +$61.43/session</strong>, "
               "which is <strong>26%</strong> of the bucket's &minus;$6,612.44 headline — not all of "
               "it. This week: <strong>$0.00/day</strong>.",
        section_ref="§1 §3 (by hold time) and §1 §8 row 2 (PROMISING); §3.4(a), where the recovery "
                    "number §1 deferred is actually computed.",
        verification="Re-run the 8h sweep against <code>trades</code>; the four cases are enumerable by "
                     "id.",
        arms_when="On the clock. It closes a position at 8h regardless of P&amp;L.",
        exit="The stopwatch IS the exit.",
        kill="<strong>Four cases, and 68% of the total is one trade.</strong> One case gets $202 "
             "<em>worse</em> under the sweep, and at the neighbouring widths where the sweep had work to "
             "do this week (4h, 6h) it LOST &minus;$81.60 and &minus;$186.40 a session. If the next 8h "
             "hold is a winner, this row is in real trouble and should be said so out loud.",
        suggested_mode="build it, expect nothing this week",
        owner="Claude — one timer in the rider's manage path",
        revert="One constant. ★ The honest summary is &ldquo;cheap insurance against a shape that did "
               "not recur&rdquo;, and it is ranked second, not first, for exactly that reason.",
    ),
    P(
        id="re-derive-the-morning-window-0918",
        window="BUILD", rank=3, tier="NEEDS REFRESH",
        topic="Re-derive the 05:00&ndash;11:00Z window before any hour-of-day rule ships",
        play="<strong>Recompute it on the current sample and retire the standing figure.</strong> The "
             "old number was a property of a sample that no longer describes how he trades.",
        mechanism="The standing figure is <strong>26 of 28 presses</strong> inside 05:00&ndash;11:00Z. "
                  "This week it is <strong>16 of 36</strong>, spread across 18 distinct hours.",
        rationale="He has widened out. Any hour-of-day filter built on the standing figure would be "
                  "fitted to a concentration that has already dispersed — and NOT-AN-ACTION&nbsp;#1 "
                  "shows what happens when a time-of-day result from one week is promoted to a rule.",
        number="<strong>26/28 → 16/36</strong>, across 18 distinct hours.",
        section_ref="§2.5 lead 9 (NEEDS REFRESH); §1 §4 (by hour of day).",
        verification="Re-derive from <code>data/operator_reads.jsonl</code> and <code>trades</code> at "
                     "70 entries.",
        arms_when="Nothing arms. It is a measurement.",
        exit="n/a.",
        kill="n/a — it is a refresh, and the outcome is the answer either way.",
        suggested_mode="measure",
        owner="Claude — one re-derivation",
        revert="n/a.",
    ),
    P(
        id="spend-the-captured-narratives-0918",
        window="BUILD", rank=4, tier="UNSPENT",
        topic="The 78 captured narratives — a ~3,160-character read of the whole session is stored with "
              "every press and nothing has been done with it",
        play="<strong>Hold them until passes exist, then pair them.</strong> The narrative pairs are the "
             "actual experiment: the same kind of text, one ending in a press and one in a pass.",
        mechanism="Every row in <code>data/operator_reads.jsonl</code> carries a full natural-language "
                  "read of the session at the moment of the press. 78 of them are stored. None has been "
                  "used for anything.",
        rationale="This is the richest thing on the desk and it is currently worth nothing, for exactly "
                  "the reason MONDAY&nbsp;#1 exists: 78 narratives that all end in &ldquo;he "
                  "pressed&rdquo; cannot teach a boundary. The moment passes start landing, the paired "
                  "comparison becomes the single best-powered test available here — same instrument, "
                  "same author, same format, opposite outcome.",
        number="<strong>78 narratives, ~3,160 characters each, 0 spent.</strong>",
        section_ref="§2.5 lead 10 (UNSPENT); §2.1 for the sample.",
        verification="Count rows with a non-empty <code>context</code> field; it is 78 today and every "
                     "one is a positive.",
        arms_when="Nothing arms.",
        exit="n/a.",
        kill="n/a — it is deliberately deferred, and saying so is the point of the row. ⚠ Do NOT mine "
             "them for features now: 78 positives with no negatives will produce a confident model of "
             "nothing.",
        suggested_mode="hold, then measure",
        owner="Claude — after ~30 passes land",
        revert="n/a. ★ Blocked on MONDAY&nbsp;#1.",
    ),
    P(
        id="move-the-leg-definition-to-1x-atr-0918",
        window="BUILD", rank=5, tier="REFUTED",
        topic="The scope's 3&times;ATR leg definition is a test that everything passes",
        play="<strong>Move the written definition to 1&times;ATR.</strong> <code>leg_survival.py</code> "
             "already defaults to it; the scope document has not caught up.",
        mechanism="A 3&times;ATR leg is alive in <strong>97.6% of ALL minutes</strong>. A condition that "
                  "97.6% of minutes satisfy carries no information.",
        rationale="This matters because every &ldquo;a leg was running&rdquo; number in §2 and §3 is "
                  "computed on the 1&times; definition, and a reader checking it against the scope's "
                  "3&times; text would conclude the sections had used a loose filter. They used the "
                  "tighter one. The document is what is wrong.",
        number="<strong>97.6% of all minutes</strong> at 3&times;; the 1&times; definition (1&times;ATR "
               "travelled in 8 minutes, dead on a 1&times;ATR give-back) is alive in "
               "<strong>74.6%</strong>, which is what §2's P&nbsp;=&nbsp;0.008 is measured against.",
        section_ref="§2.5 lead 7 (REFUTED); §2.3 for the definition actually used.",
        verification="<code>scripts/leg_survival.py</code> — its default is already 1&times;.",
        arms_when="Nothing arms. It is a documentation fix.",
        exit="n/a.",
        kill="n/a.",
        suggested_mode="fix the doc",
        owner="Claude — one line in the scope",
        revert="n/a.",
    ),
    P(
        id="dedupe-operator-reads-before-counting-0918",
        window="BUILD", rank=6, tier="FIX — INSTRUMENT",
        topic="<code>operator_reads.jsonl</code> must be de-duplicated before anything counts it",
        play="<strong>De-duplicate at read time and write the rule down beside the file.</strong> "
             "Counting lines instead of records nearly doubled the sample.",
        mechanism="The file holds <strong>135 lines</strong> and <strong>77 distinct records</strong> — "
                  "58 duplicates.",
        rationale="Counting lines would have reported <strong>65 presses where there are 36</strong>. "
                  "Section 2 de-duplicates and says so; the risk is the next consumer that does not, "
                  "and there is no de-dup helper next to the file to stop it. Every sample size on this "
                  "card — the 36, the 78, the 30-press threshold — moves if this is got wrong.",
        number="<strong>135 lines → 77 records</strong>; 65 presses → <strong>36</strong>.",
        section_ref="§1's closing housekeeping note to §2; §2.1 (the sample).",
        verification="Count lines against distinct records in the file. ⚠ Whole-row JSON equality is "
                     "NOT the de-dup key — all 135 lines differ on it; the rule has to be written down "
                     "rather than rediscovered.",
        arms_when="Nothing arms.",
        exit="n/a.",
        kill="n/a — it is a defect.",
        suggested_mode="fix it",
        owner="Claude — one reader helper beside the file",
        revert="n/a.",
    ),

    # ══════════════════════════════════════════════════════════════════════════════════
    # HOLD — things to watch and explicitly NOT fit.
    # ══════════════════════════════════════════════════════════════════════════════════
    P(
        id="watch-the-wrong-from-minute-one-shape-0918",
        window="HOLD", rank=1, tier="WATCH",
        topic="★ Your losers are wrong from the first minute — log it, watch it, do NOT fit it",
        play="<strong>Carry this as a description and nothing more.</strong> It is the cleanest finding "
             "in the report and turning it into a bail rule means backtesting an exit, which the "
             "standing rule forbids.",
        mechanism="Measured off the 5-second tape from fill to final lot out, per decision.",
        rationale="Your <strong>25 winners</strong> had a median best-moment of <strong>59.2 points</strong> "
                  "in your favour and you booked a median <strong>70%</strong> of it. Your "
                  "<strong>14 losers</strong> had a median best moment of <strong>11.2 points</strong>; "
                  "<strong>11 of 14 never once showed you 25 points</strong> and 7 never showed ten. "
                  "You are not giving winners back — you are occasionally getting on the wrong side and "
                  "staying there.",
        number="<strong>59.2pt vs 11.2pt</strong> median best-moment; 70% of the best moment kept on "
               "winners; 11 of 14 losers never showed 25 points.",
        section_ref="§1 §2 (every entry, with best/worst/kept) and §1 §8 row 5 (WATCH).",
        verification="Re-derivable per decision from the 5s tape against <code>trades</code>.",
        arms_when="Nothing arms.",
        exit="n/a.",
        kill="n/a. ⚠ <strong>The kill criterion for this row is on the person reading it:</strong> the "
             "standing rule forbids a 120th exit calibration, and this shape is precisely the bait for "
             "one. If it is still true at 100 entries it becomes a candidate; at 39 it is a picture.",
        suggested_mode="watch",
        owner="Garrath — noticing, not acting",
        revert="n/a.",
    ),
    P(
        id="volatility-preference-conflicted-0918",
        window="HOLD", rank=2, tier="OPEN — CONFLICTED",
        topic="The volatility preference — the description and the dollars point opposite ways",
        play="<strong>Write no ATR band. Re-measure at 70 entries.</strong> This is the one place in §2 "
             "where two honest readings of the same 36 trades disagree, and the sample cannot settle "
             "it.",
        mechanism="ATR percentile at press vs at a randomly chosen control minute, and post-hoc terciles "
                  "of the same 36 trades by ATR.",
        rationale="He presses at ATR percentile <strong>71.7 against a baseline of 49.3</strong> "
                  "(within-session rank 62.9, CI [54.0, 71.4]) — a real preference for a lively tape. "
                  "But the <em>money</em> went the other way: the quiet tercile made "
                  "<strong>+$2,762</strong> and the lively one <strong>&minus;$1,262</strong>. Those are "
                  "12-trade cells, chosen after the fact, and the medians barely move.",
        number="ATR pct <strong>71.7 vs 49.3</strong>; quiet tercile <strong>+$2,762</strong>, lively "
               "tercile <strong>&minus;$1,262</strong>, on 12-trade cells.",
        section_ref="§2.4 (what the dollars did — post-hoc, three-deep, and not a rule) and §2.5 lead 6.",
        verification="Re-run the terciles at 70 entries.",
        arms_when="Nothing arms.",
        exit="n/a.",
        kill="Either reading could die at 70 entries and that is the point of holding it. Acting on "
             "the dollar half today would be fitting a 12-trade cell.",
        suggested_mode="hold",
        owner="Claude — re-measure at 70 entries",
        revert="n/a.",
    ),

    # ══════════════════════════════════════════════════════════════════════════════════
    # NOT-AN-ACTION — the refutations, printed with their autopsies. On a week this thin
    # these are the most valuable output: a list of things now ruled out.
    # ══════════════════════════════════════════════════════════════════════════════════
    P(
        id="do-not-trade-only-the-morning-0918",
        window="NOT-AN-ACTION", rank=1, tier="REFUTED",
        topic="★ &ldquo;Only trade the European morning&rdquo; — the most tempting idea in the report, "
              "and it does not survive its own sample",
        play="<strong>Do NOT build this filter.</strong> This week it looks like the whole edge. Over "
             "the record it is negative, and a single trade flips its sign.",
        mechanism="Split the record at 13:00Z and compare.",
        rationale="This week, 05:00&ndash;12:59Z was <strong>+$2,445.51 over 20 entries</strong> and "
                  "after 13:00Z was <strong>&minus;$553.02 over 16</strong>. Over the whole "
                  "confirmed-manual record the SAME morning window is "
                  "<strong>&minus;$779.48</strong> — and <strong>one trade on 10 September flips its "
                  "sign</strong>. A filter fitted on a week that one trade can reverse is not a filter.",
        number="<strong>+$2,445.51 / 20 this week; &minus;$779.48 lifetime</strong>, one trade from "
               "changing sign.",
        section_ref="§1 §4 (by hour of day) and §1 §8 row 4 (REFUTED as a rule).",
        verification="Re-derive the split from <code>trades</code> with <code>entry_source='manual'</code>.",
        arms_when="Nothing arms — that is the point.",
        exit="n/a.",
        kill="It is already killed. ★ If it ever comes back, it comes back through BUILD&nbsp;#3's "
             "re-derivation at 70 entries, not through another good morning.",
        suggested_mode="do not build",
        owner="n/a",
        revert="n/a.",
    ),
    P(
        id="position-in-range-refuted-0918",
        window="NOT-AN-ACTION", rank=2, tier="REFUTED",
        topic="Position-in-range as an entry condition — the number everyone expects to matter, and it "
              "does not",
        play="<strong>Stop building it.</strong> Two independent rulers, 5,255 control minutes, one "
             "answer.",
        mechanism="Rank the press inside its own session's range, against control minutes from the same "
                  "sessions.",
        rationale="Ranked inside its own session the median press sits at the <strong>54.2nd "
                  "percentile, CI [44.6, 63.5]</strong>; on a clean-session ruler, 56.7 [47.5, 66.2]. "
                  "<strong>Both intervals contain 50.</strong> He is not buying breakouts and he is not "
                  "buying dips — where price sits in the day's range does not separate his presses from "
                  "picking a minute at random.",
        number="<strong>54.2 [44.6, 63.5]</strong> and <strong>56.7 [47.5, 66.2]</strong>; both contain "
               "50. 5,255 control minutes.",
        section_ref="§2.2 (the one comparison legitimate without negatives) and §2.5 lead 4.",
        verification="Re-runnable against the control-minute set for the same four sessions.",
        arms_when="Nothing arms.",
        exit="n/a.",
        kill="It is already killed. ⚠ Standing caveat: refuted <em>as a separator of his presses from "
             "random minutes</em>. It is not a claim that range position is meaningless in general.",
        suggested_mode="do not build",
        owner="n/a",
        revert="n/a. ★ SATURDAY&nbsp;#2 fixes the instrument that computes day range — and this "
               "conclusion was re-checked against the fix and does not move.",
    ),
    P(
        id="vwap-stretch-refuted-0918",
        window="NOT-AN-ACTION", rank=3, tier="REFUTED",
        topic="VWAP stretch as an entry condition — he is neither fading nor chasing VWAP",
        play="<strong>Stop building it.</strong> Same ruler, same answer as NOT-AN-ACTION&nbsp;#2.",
        mechanism="Signed distance from session VWAP in ATR units at the press, ranked against control "
                  "minutes.",
        rationale="Within-session rank <strong>54.0, CI [45.6, 62.4]</strong> — contains 50. The press "
                  "median stretch is <strong>+5.21 ATR</strong> against a control baseline of "
                  "<strong>+5.41</strong>. There is no stretch preference to find.",
        number="rank <strong>54.0 [45.6, 62.4]</strong>; press median <strong>+5.21 ATR</strong> vs "
               "baseline <strong>+5.41</strong>.",
        section_ref="§2.2 and §2.5 lead 5.",
        verification="Same control-minute set as NOT-AN-ACTION #2.",
        arms_when="Nothing arms.",
        exit="n/a.",
        kill="Already killed.",
        suggested_mode="do not build",
        owner="n/a",
        revert="n/a.",
    ),
    P(
        id="do-not-extend-the-250-loss-limit-0918",
        window="NOT-AN-ACTION", rank=4, tier="REFUTED",
        topic="★ Do NOT extend the $250 daily loss limit to this book — it is listed as already "
              "automated and it is worse than nothing here",
        play="<strong>Leave it pre-registered and frozen on the automated single-lot book where its "
             "evidence came from.</strong> Do not point it at the manual book. Two separate defects in "
             "it are SATURDAY&nbsp;#3 and SATURDAY&nbsp;#4.",
        mechanism="A $250 session loss limit that benches the book for the rest of the day.",
        rationale="Applied to this book it measures <strong>&minus;$67.09 a session</strong> over 29 "
                  "sessions. It trips on 10 of them, and the trades opened after those trips net "
                  "<strong>+$1,945.50</strong>. On <strong>6 of the 10</strong> trips he had already "
                  "stopped anyway, so the entire measured cost sits in four sessions. It is "
                  "one-directional by construction: the rule can only ever remove trades, and on this "
                  "book the trades it removes made money.",
        number="<strong>&minus;$67.09 a session</strong> over 29 sessions; this week "
               "<strong>&minus;$31.40/day</strong>; the post-trip trades net <strong>+$1,945.50</strong>.",
        section_ref="§3.4(c) (the one that is worse than nothing) and §3.5 row 5.",
        verification="Re-run the limit against <code>trades</code> per session — and note "
                     "SATURDAY&nbsp;#4 first: the guard's own P&amp;L reader counts fabricated fills, "
                     "so its live trips are not the same population as this replay.",
        arms_when="Nothing arms — and the point of this row is that nothing should.",
        exit="n/a.",
        kill="Scoped to THIS book. It is not a verdict on the loss limit where it currently runs, and "
             "it does not say remove it from there.",
        suggested_mode="do not extend",
        owner="n/a",
        revert="n/a.",
    ),
]


def main() -> int:
    seen = set()
    for p in PLAYS:
        if p["id"] in seen:
            raise SystemExit(f"FATAL — duplicate play id {p['id']}")
        seen.add(p["id"])
    at = {}
    for p in PLAYS:
        k = (p["window"], p["rank"])
        if k in at:
            raise SystemExit(f"FATAL — two plays at {k}: {at[k]} and {p['id']}")
        at[k] = p["id"]
    # Ranks must be contiguous from 1 inside each window: the card is read as a numbered list and
    # a gap reads as a row that was dropped.
    from collections import defaultdict
    byw = defaultdict(list)
    for p in PLAYS:
        byw[p["window"]].append(p["rank"])
    for w, rs in byw.items():
        if sorted(rs) != list(range(1, len(rs) + 1)):
            raise SystemExit(f"FATAL — {w} ranks are {sorted(rs)}, not 1..{len(rs)}")
    pathlib.Path(OUT).write_text(json.dumps(PLAYS, indent=1, ensure_ascii=False))
    print(f"wrote {len(PLAYS)} plays → {OUT}")
    for w, rs in byw.items():
        print(f"  {w:<14} {len(rs)} plays")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
