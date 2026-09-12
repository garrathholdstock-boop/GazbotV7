#!/usr/bin/env python3
"""THE ACTION CARD for the week to Friday 2026-08-28 — built from THIS week's verdicts only.

★ Every play below traces to a verdict a section of THIS report actually reached, and the
`section_ref` field names where. The file that was on disk (reports/friday_v7/plays.json,
written 2026-08-26) is the week-to-08-21 card and is overwritten: a stale action card is the
most dangerous artifact this build produces, because it is the part the operator acts on and
it is the part that looks least like it has a date on it.

Sections that did NOT regenerate this cycle (Part 1.5, Part 1.6, Part 2.5) contribute NOTHING
here. That is deliberate and it is the whole point of the rule: a play must trace to a verdict
reached this week, and a section that did not run reached no verdicts this week. Where last
week's card carried a row sourced only from one of those sections, the row is dropped rather
than carried forward — carrying it would date-launder a prior-week conclusion onto a card
headed 2026-08-28.

Run:  python3 scripts/friday_v7_plays_0828.py
"""
from __future__ import annotations

import json
import pathlib

OUT = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"

P: list[dict] = []


def play(**kw):
    P.append(kw)


# ══════════════════════════════════════════════════════════════════════════════════════════
# SATURDAY — before the Sunday 22:00Z reopen
# ══════════════════════════════════════════════════════════════════════════════════════════

play(
    id="timer-the-two-dead-nightlies-0828",
    window="SATURDAY", rank=1, tier="LIVE",
    topic="Put router_nightly.py and selector_nightly.py on a timer — both have been silently dead for a fortnight",
    play="Write a systemd timer for each (or one timer that runs both), 22:30Z daily, after the "
         "Paris-day roll. They are pure rollups: no orders, no switches, no risk.",
    mechanism="Neither script has a systemd unit or a crontab entry anywhere on the box. The only "
              "things that reference them are the Friday build scripts, so they have effectively "
              "been running <em>once a week, by accident, inside the report</em>. When Part 2.6 "
              "went looking this cycle, the newest <code>data/router_nightly/*.json</code> was "
              "dated <strong>2026-08-14</strong> and the newest selector file "
              "<strong>2026-08-18</strong>.",
    rationale="This is the report's own instrumentation, and the report is the thing that noticed. "
              "Every nightly number in Part 2.6 this week is a REBUILD done during the report, not "
              "the output of a monitor that was watching — so the desk has had no daily read on "
              "router value or exit selection for 10–14 days and nothing said so.",
    number="router_nightly last wrote 2026-08-14, selector_nightly 2026-08-18 — 14 and 10 days "
           "dead. Zero units in /etc/systemd/system, zero crontab entries. Part 2.6 rebuilt all "
           "five days by hand to write its section.",
    section_ref="Part 2.6 §honesty-flag-1 and recommendation #1 (confidence: CERTAIN).",
    verification="<code>systemctl list-timers | grep nightly</code> shows both, and a file dated "
                 "tomorrow appears in <code>data/router_nightly/</code> without anyone running the "
                 "Friday build.",
    arms_when="Immediately. It is plumbing and it cannot trade.",
    exit="n/a.",
    kill="If a nightly rollup turns out to be so cheap that running it inside the Friday build is "
         "genuinely sufficient, delete the timers — but then the Friday scope must stop describing "
         "them as a weekly rollup OF a monitor.",
    suggested_mode="deploy",
    owner="Garrath — two unit files, no code change",
    revert="<code>systemctl disable --now</code> both timers.",
    money_gbp=0,
)

play(
    id="alert-on-router-headless-aborts-0828",
    window="SATURDAY", rank=2, tier="LIVE",
    topic="★ The router went blind for 3h35m and every health instrument on the box said it was fine",
    play="Point the health alert at <code>data/router_headless.log</code> ABORT lines rather than "
         "at the trial log, and fix the health page's text — it currently blames an "
         "&ldquo;expired login&rdquo; for what is a usage limit resetting on the hour.",
    mechanism="43 ticks aborted this cycle. An abort is fail-closed — it writes nothing — which is "
              "the correct default and is exactly why it is invisible: the trial log gets no line "
              "at all, <code>systemctl</code> reports the unit as cleanly deactivated, and the tick "
              "count reads normal. 31 of the 43 are the LLM session limit; the other 12 are all "
              "Monday, inside the 04:28–05:00Z gateway window — 4 invocation failures plus 8 empty "
              "responses, a second failure mode with the same silent signature.",
    rationale="A monitor that cannot see its subject's most common failure is not a monitor. The "
              "desk's #1 lever was absent for three and a half hours and the only evidence is a "
              "log nothing watches.",
    number="43 ABORTs ≈ 3h35m blind. 31 session-limit, 12 Monday-gateway. The −$135.43 Friday miss "
           "landed inside a blackout. systemctl / trial log / tick count all read clean throughout.",
    section_ref="Part 2.6 recommendation #2 (CERTAIN, measured on four separate days); Part 1 §5 "
                "counts the same 43 from the tournament's side.",
    verification="Kill the router mid-tick and confirm a page arrives naming the abort, not silence.",
    arms_when="Immediately.",
    exit="n/a — it is an alert.",
    kill="If ABORT rates prove noisy enough to page nightly, rate-limit rather than remove: the "
         "failure this closes is silence, and a noisy alert is still not silence.",
    suggested_mode="deploy",
    owner="Garrath — alert source + one string on the health page",
    revert="Point the alert back at the trial log.",
    money_gbp=0,
)

play(
    id="open-hour-watch-must-match-its-unit-0828",
    window="SATURDAY", rank=3, tier="LIVE",
    topic="Make open_hour_watch.py match its own unit file, or give its prompt header an EXPIRY",
    play="Either remove the gate-switch write path from <code>open_hour_watch.py</code> so it is "
         "genuinely alert-only as its unit file promises, or — if the auto-arm is wanted — change "
         "the unit file to say so and add a hard expiry to the header notes it injects.",
    mechanism="<code>open-hour-watch.service</code> states the process &ldquo;must NEVER write "
              "gate_switches.env&rdquo;. It wrote twice this week, and on Friday one of those "
              "writes re-armed a gate the router had deliberately benched 9 minutes earlier. "
              "Separately, the note it splices into the router's prompt carries no expiry, so it "
              "sat in every router prompt for 3h51m after being reversed.",
    rationale="Two independent hazards in one file, and they compound: a second writer with no "
              "standdown awareness, plus a no-expiry instruction that outlives the situation it "
              "described. Obeying the stale note would have cost −$258.06.",
    number="2 writes this week against a unit file that forbids them; a 9-minute override of a live "
           "router bench; a header note live for 3h51m past its reversal, worth −$258.06 if obeyed.",
    section_ref="Part 2.6 recommendation #7 (HIGH); Part 1 §4 shows the watcher as one of only "
                "three writers of gate_switches.env this week.",
    verification="<code>grep -n 'gate_switches' scripts/open_hour_watch.py</code> returns nothing, "
                 "or the unit file no longer claims it cannot write.",
    arms_when="Before the Sunday 22:00Z reopen — the watcher runs on Monday's open.",
    exit="n/a.",
    kill="Keep the auto-arm ONLY if it is made standdown-aware and cannot reverse a router bench "
         "younger than its own hold period.",
    suggested_mode="deploy",
    owner="Garrath — one script or one unit file, your choice of which end to fix",
    revert="git revert; the auto-arm has fired twice all week, so nothing depends on it.",
    money_gbp=0,
)

# ══════════════════════════════════════════════════════════════════════════════════════════
# MONDAY — at the desk, reversible
# ══════════════════════════════════════════════════════════════════════════════════════════

play(
    id="promote-absveto55s-two-sided-0828",
    window="MONDAY", rank=1, tier="SHADOW (battery passed)",
    topic="Promote abs_veto_55s TWO-SIDED — the only arm on a 79-row board that survived everything",
    play="Promote <code>abs_veto_55s</code> to a live slot, <strong>both sides</strong>, with the "
         "LONG side sized smaller than the SHORT. It is not a new mechanism: it is the absorption "
         "veto the desk already runs, given its own slot.",
    mechanism="A 55-second absorption confirm sits in front of the thrust entry and refuses the "
              "thrusts that are being absorbed. Head-to-head against its own un-vetoed twin "
              "(<code>thrust_short_raw</code>) over the same window it is +$5,350 — so the veto, "
              "not the thrust, is what is being promoted.",
    rationale="It is the same candidate as last week, and that is the point: this is another week "
              "of FORWARD evidence rather than another week of the same evidence. It added "
              "+$948.50 on 45 trades this week without being re-tuned.",
    number="All-time n=433, +$5,302, +$12.25/trade, 48% win, green on 24 of 31 trading days. This "
           "week +$948.50 on 45 trades (+$21.08/tr). Both halves, both regimes and BOTH SIDES pay "
           "(SHORT +$3,612 / LONG +$1,691). Strip its 3 best days and it is still +$3,363.",
    section_ref="Part 2 §1 (board, ranked on real_pnl not ceiling_pnl) and §9 disposition.",
    verification="The gate appears in <code>gate_switches.env</code> and takes its first live fill "
                 "on the same side the shadow arm did, at a comparable price.",
    arms_when="Monday at the desk, SIZED SMALL. Two-sided from the start — see NOT-AN-ACTION #2, "
              "relegating a direction is refuted. ★ REV2 — and one thing that was open is now "
              "closed: the promoted slot runs WITHOUT an ATR floor, and so does the live gate it "
              "goes into (deciders.py:203 lists only grind_long 22.0 and capitulation_long 10.0). "
              "The shadow arm's entry params — thr 1.5, amp_floor 0.0004, confirm_s 55 — are "
              "IDENTICAL to the live slots'. It is the same entry, not a looser one.",
    exit="Its shadow ruler: 2.0R target, 1.0×ATR stop. Do not import an exit cell from Part 2's "
         "exit lab — twenty of twenty of those failed.",
    # ★2026-08-29 REV2 — the SHADOW number now carries the desk's own live haircut. See Part 3 Q1.
    kill="★ REV2 — THE KILL IS NOW A SLIPPAGE TEST, NOT A P&L ONE, AND IT RESOLVES IN 20 TRADES. "
         "This is a shadow number and this desk's standing correction is that live losses run "
         "1.1–3.1× modelled. Applied to the loss side only (wins +$13,586.00, losses −$8,283.50, "
         "n=433): +$10.33/tr at 1.1×, +$2.68 at 1.5×, ZERO at 1.64×, −$6.88 at 2.0× and −$27.93 at "
         "3.1×. So it survives the bottom quarter of its own haircut band and nothing above. "
         "Compare the first 20 live fills against what the shadow said they were worth; if the "
         "realised loss multiple comes in above 1.64×, this is a null and not a winner. Also kill "
         "on two consecutive red weeks at n≥40, or the LONG side below −$5/trade on n≥60.",
    suggested_mode="deploy",
    owner="Garrath — slate entry + tournament restart",
    revert="Remove from the slate. It keeps running in shadow either way.",
    money_gbp=0,
)

play(
    id="router-step-15m-to-5m-0828",
    window="MONDAY", rank=2, tier="LIVE",
    topic="★ Attack the 20-minute arm lag — the router's dominant error is no longer direction, it is LATENESS",
    play="Change the router step from 15m to 5m (the timing half of the sweep winner) and add one "
         "explicit prompt line: <em>arm on the FIRST confirmed break impulse, not the fifth</em>.",
    mechanism="Decomposed, roughly 15 of the 20 minutes is the router's own confirmation appetite "
              "and only ~5 is the tick grid — so the step change alone does not fix it, which is "
              "why the prompt line ships with it. Actuation once decided is not the problem: on "
              "Friday the gates filled <strong>1.4 seconds</strong> after the switch flipped.",
    rationale="This is the week's clearest measured cost and it points the same way from two "
              "independent sections. The arm that made the week's money was right — and late.",
    number="Friday 14:45:03Z arm: measured lateness $205–$705 against the $181.50 the arm banked. "
           "Part 1 prices the same delay on one lot at $33.84 (grind_long's own 14:36:26Z "
           "suppressed signal was worth +$150.02; the fill 8m37s later was worth +$116.18).",
    section_ref="Part 2.6 recommendation #3 (HIGH) and Part 1 §5 / §9, which price the same arm "
                "from the tournament's side and agree on the direction.",
    verification="<code>router_trial_log.txt</code> shows ticks 5 minutes apart, and the next arm's "
                 "gap between first suppressed signal and switch write is under 5 minutes.",
    arms_when="Monday. It is a constant and a prompt line.",
    exit="n/a.",
    kill="If switch changes per hour rise above ~1.0 (this week ran 0.18 — no thrash) or if a "
         "5-minute cadence starts producing arm/bench round trips with no intent in between, "
         "revert to 15m and attack the confirmation appetite alone.",
    suggested_mode="deploy",
    owner="Garrath — one constant in router_tick_durable.py + one prompt line",
    revert="Set the step back to 15m. Reversible in five minutes.",
    money_gbp=0,
)

play(
    id="router-must-quote-window-and-family-0828",
    window="MONDAY", rank=3, tier="LIVE",
    topic="Make the router quote a WINDOW and a FAMILY whenever it cites the shadow board",
    play="One line in the router prompt: any shadow-board figure must name its date window and the "
         "arm family it covers, or it may not be used as a reason.",
    mechanism="On 08-28 a bench rested on &ldquo;344 fader trades at −$3,021 today&rdquo;. The real "
              "figure for that day and family was <strong>128 trades / −$636.50</strong> — the "
              "quoted number was an all-time total wearing the word &ldquo;today&rdquo;.",
    rationale="The error is not random: an unwindowed aggregate is almost always larger than the "
              "windowed one, so it systematically INFLATES the case for benching. Here it inflated "
              "it about five-fold and the bench then cost −$135.43.",
    number="Claimed 344 trades / −$3,021; actual 128 / −$636.50 — a ~5× overstatement. The bench it "
           "justified cost −$135.43.",
    section_ref="Part 2.6 recommendation #6 (CERTAIN). Part 2 §2 finds the same class of fault in "
                "the tooling (<code>abs_veto_sides.py</code> hard-codes WEEK0 = 2026-07-27 and "
                "reports 4½ weeks as &ldquo;this week&rdquo;).",
    verification="Next router citation of the board includes a date range and an arm name.",
    arms_when="Monday.",
    exit="n/a.",
    kill="n/a — it constrains a citation, not a decision.",
    suggested_mode="deploy",
    owner="Garrath — one prompt line",
    revert="Delete the line.",
    money_gbp=0,
)

play(
    id="untradeable-stop-meter-tournament-only-0828",
    window="MONDAY", rank=4, tier="LIVE",
    topic="Filter the untradeable stop-rate meter to tournament gates only — it has never once discriminated",
    play="Restrict the meter's stop-rate input to tournament rows. Today it reads the last 15 "
         "trades of BOTH books.",
    mechanism="The day rider's exit vocabulary contains no <code>STOP</code> at all, so every rider "
              "row it ingests votes zero by construction. On Friday that vote pulled the score "
              "53&rarr;42 and flipped the verdict — on an input that was measuring nothing.",
    rationale="A sub-meter that structurally cannot fire is not a conservative input, it is a "
              "constant with a vote. Zero of this week's 32 trades exited on STOP.",
    number="0 of 32 trades exited STOP this week. Friday: score 53→42 on the rider-dominated "
           "sample, verdict flipped.",
    section_ref="Part 2.6 recommendation #5 (CERTAIN).",
    verification="Re-score Friday 08-28 with the filter on and confirm the meter reads 53, not 42.",
    arms_when="Monday.",
    exit="n/a.",
    kill="If the tournament ever starts exiting on STOP frequently, re-examine — but the fix is "
         "still to read the right book.",
    suggested_mode="deploy",
    owner="Garrath — one filter in untradeable.py",
    revert="Remove the filter.",
    money_gbp=0,
)

# ══════════════════════════════════════════════════════════════════════════════════════════
# BUILD — nothing goes live this week
# ══════════════════════════════════════════════════════════════════════════════════════════

play(
    id="measure-absveto-short-trigger-lag-0828",
    window="BUILD", rank=1, tier="PARKED",
    topic="★★ THE WEEK'S #1 STONE — abs_veto_short was armed for 46m30s of the exact tape it exists to trade and produced ZERO signals",
    play="Measure the lag between &ldquo;the break starts&rdquo; and &ldquo;the thrust trigger "
         "fires&rdquo; on this week's tick tape. If the answer is 20+ minutes, the fix is either "
         "the router arming on break ONSET or the gate running its <code>fast=True</code> "
         "start-of-move trigger. Do not change either until the lag is measured.",
    mechanism="Friday 16:00–17:03Z the tape fell 328 points in one confirmed direction. "
              "<code>abs_veto_short</code> was armed for 46m30s of it across two windows and never "
              "opened its mouth. Its two nearest signals landed 4 minutes BEFORE the first arm "
              "ended and 5 minutes AFTER the second — and on their own exits both LOSE money "
              "(−$47.79 and −$42.07).",
    rationale="Those bracketing losses are what make this interesting rather than a simple "
              "arm-it-earlier story. It is not that the router was late and it is not that the "
              "gate is dead: <strong>the gate's trigger and the router's regime read are out of "
              "phase.</strong> The router arms when a break is CONFIRMED; a thrust gate needs the "
              "moment a break STARTS. On Friday those were about 25 minutes apart.",
    number="46m30s armed across a 328-point one-directional break, 0 signals. The two nearest "
           "signals: −$47.79 (4 min before the arm) and −$42.07 (5 min after the bench).",
    section_ref="Part 1 §9 flagship case study and §11 disposition (PARKED, named the week's #1 "
                "stone); Part 1 §4 for the armed windows.",
    verification="A table of (break-onset time, trigger time) pairs for every confirmed break in "
                 "the week, with the median lag.",
    arms_when="Nothing arms. This is a measurement.",
    exit="n/a.",
    kill="If the measured lag is under ~5 minutes, the hypothesis is wrong and Friday was a "
         "one-off; say so and close it.",
    suggested_mode="observe",
    owner="Claude — one lab against this week's 250ms tape",
    revert="n/a — it is a measurement. ★ It is a MECHANISM question, so it does not need a big "
           "sample to answer, which is why it outranks everything else in this window.",
    money_gbp=0,
)

play(
    id="day-level-gate-reads-once-at-1300z-0828",
    window="BUILD", rank=2, tier="PARKED",
    topic="Build a DAY-level gate for the Open Rider that reads its feature ONCE at 13:00Z and sets a session flag",
    play="Build the instrument, not another search. One feature, read once, before the session "
         "commits, setting a flag for the whole day.",
    mechanism="The drift gate the desk already runs was assumed to be this. It is not: over 11 "
              "paired days it net-blocked <strong>1 entry of 89 (1.1%)</strong>, fired 6 times, "
              "and cost $301 — five of the six blocks were simply re-entered at the next cadence "
              "slot, three of them at a worse price. It is a five-minute entry delay wearing a day "
              "filter's name.",
    rationale="Everything in Part 2 §3 says day selection is where the Open Rider's money is; §3d "
              "says we have never actually built a day-level instrument to test that with. The "
              "searched classifier was refuted — but a search over 8 features is not the same "
              "experiment as one pre-registered day-level read.",
    number="Ungated Open Rider, 15 days: 6 green days +$3,066 against 9 red −$5,626, oracle "
           "≈$1,022/wk. Drift gate as a day filter: 1 block in 89 entries, −$301.",
    section_ref="Part 2 §3, §3d and §9 disposition (drift gate PARKED, not refuted); Part 2's "
                "closing line names this as next weekend's build.",
    verification="A session flag written at 13:00Z each day, and a 20-session log of "
                 "flag-vs-outcome before anything is gated on it.",
    arms_when="Nothing arms. Shadow only.",
    exit="n/a.",
    # ★2026-08-29 REV2 — the interim read's SIGN was an artefact of a dropped row. Part 2 §3c's
    # ledger printed 08-24 as "0 trades, $0.00" while the book has the 08-21 carry closing that
    # morning for −$2,149.44, on a sit-out day. Restored, the filter points the RIGHT way.
    kill="The pre-registered ATR≥9.5 filter is the honest control, and at 10 of 60 sessions its "
         "sign is decided by ONE row: −$253 on trade days against −$1,493.44 on skip days with the "
         "08-24 carry close included (right way, by $1,240.44), or +$656 on skip days with it "
         "dropped (wrong way, by $909). One trade of 33. If the day-level instrument still agrees "
         "with the unfavourable reading after 50 sessions, day selection is dead for this strategy.",
    suggested_mode="shadow",
    owner="Claude — small build, one read per day",
    revert="n/a — shadow only.",
    money_gbp=0,
)

play(
    id="precursors-are-atr-proxies-find-another-input-0828",
    window="BUILD", rank=3, tier="REFUTED / structural",
    topic="★★★ THE STRUCTURAL FINDING — every precursor feature on this desk is a proxy for ATR, and that is why selection keeps failing",
    play="Stop re-tuning selectors built on the current feature set, and go find an input that is "
         "not a volatility proxy. Order-book imbalance at depth, cross-instrument lead/lag and "
         "session-level positioning are the candidates; none of them is recorded in a form a "
         "selector can read today.",
    mechanism="Against a fixed POINT threshold, every precursor looks predictive — volume z, trade "
              "count z, ATR expansion, aggressor flow, ER(15) and ATR level all beat a coin flip "
              "with p=0.00. Express the same threshold in ATR and the discrimination "
              "<em>collapses</em>: ATR expansion falls to 0.234 and ATR level to 0.306, both now "
              "WORSE than a coin flip. Hold ATR fixed and ask within the band and every feature "
              "sits between 0.29 and 0.56. A 55-point move is easy on a wide tape and hard on a "
              "quiet one, so anything correlated with ATR scores well against a point threshold. "
              "It is the same instrument measured twice.",
    rationale="For three cycles this lab has closed with &ldquo;detection is solved, selection is "
              "not&rdquo; without being able to say WHY selection kept failing. It can now. We have "
              "been feeding a volatility meter to a selector and asking it for a direction. No "
              "amount of re-tuning fixes that.",
    number="52,937 minutes across 41 days. Point-threshold AUCs 0.51–0.81 (all p=0.00); "
           "ATR-normalised 0.23–0.53; ATR-conditioned 0.29–0.56. Direction carries nothing at any "
           "threshold: up-share 48.1–50.0%, aggressor flow BELOW 0.50 everywhere, continuation "
           "agreement 40.9–52.2% with no trend.",
    # ★2026-08-29 REV2 — Movement 2 §4's corroboration is DOWNGRADED. Its "0 of 6" scored a
    # direction-handed control against a both-directions gate number. Like for like the gates win
    # 3 of 5, and nothing separates from the control at n=2..10 lots. This play stands on
    # Movement 3's 52,937 minutes, which is where its weight always was.
    section_ref="Movement 3 §3 (the escalation study, computed this cycle). ★ REV2: Movement 2 §4 "
                "was cited here as independent confirmation and that citation is WITHDRAWN — its "
                "random-entry control returns a NULL, not a kill (gates win 3 of 5 in-direction, "
                "4 of 5 direction-blind, on 2–10 lots; only exhaustion_short separates, P=0.033 "
                "raw and 0.166 Holm-adjusted). This finding does not need it.",
    verification="Any proposed new feature must be re-run through the same three tables and hold "
                 "its AUC after ATR conditioning. That test is now the bar.",
    arms_when="Nothing arms. This is why several things should NOT be built.",
    exit="n/a.",
    kill="A feature that keeps AUC ≥ 0.60 in the ATR-conditioned table would refute this and would "
         "be the most valuable thing on the desk.",
    suggested_mode="observe",
    owner="Claude — the finding is banked; the search for a non-volatility input is the build",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="decline-the-dead-band-0828",
    window="BUILD", rank=4, tier="SHADOW",
    topic="★ 48.2% of entries go NOWHERE and pay $10 each — and REV2 shows ATR can SEE them (AUC 0.683). Ship it as a pre-registered shadow arm.",
    play="Build and shadow a size/participation rule that declines entries whose realised excursion "
         "band is the ±20-point dead zone. It is a SIZE decision, not a direction decision, which "
         "is why it is the one lever in Movement 3 that does not depend on predicting anything.",
    mechanism="Decompose the pooled book by what the tape actually did next. Moves of ≥120 points "
              "are 1.6% of entries and pay +$319.51 each; the ±20-point band is 48.2% of entries "
              "and pays −$10.00 each. That band alone is −$8,254 on a book whose total is −$2,814.",
    rationale="Three harnesses now agree independently — the rider lab, the census and this "
              "decomposition — that the tradeable threshold is size, around 120 points, and that "
              "the friction is the dead band rather than the losers.",
    number="ATR-scaled ruler, n=1,713, −$2,814 total. ≥120pt: n=27 (1.6%), +$8,627, +$319.51/tr. "
           "±20pt: n=825 (48.2%), −$8,254, −$10.00/tr. The fixed-22pt ruler agrees: 48.4% dead, "
           "−$13.57/tr.",
    section_ref="Movement 3 §7 (this cycle); Movement 3 §1 for the fire-rate side of the same "
                "problem (66.4 entries/day, 21.1% of them inside a run); ★ Part 3 Q2 for the "
                "classifier test and its robustness battery (scripts/rev2_deadband_classifier.py).",
    # ★★2026-08-29 REV2 — THIS PLAY'S OWN KILL CRITERION HAS BEEN RUN, AND IT DID NOT KILL IT.
    # The criterion was "close it loudly if the dead band cannot be identified ex-ante at better
    # than chance". Measured with §3's own AUC harness on §7's own 1,713-entry book, ATR at entry
    # separates dead-band entries at 0.683 (permutation p = 0.0005) — comfortably over the 0.60 bar
    # stated in advance. So it is NOT closed. But the DOLLAR rule fails strip-best-3, so it is not
    # built either. It ships as a shadow arm with a threshold fixed BEFORE the data. See Part 3 Q2.
    verification="A shadow arm that declines the dead band and reports what it declined, so the "
                 "decline rule can be graded on what it AVOIDED as well as what it took. ★ REV2 — "
                 "the threshold must be PRE-REGISTERED before it runs, exactly like the Open "
                 "Rider's ATR filter, because the 48.2% cut used in the test below was fitted to "
                 "the same book it was measured on.",
    arms_when="Nothing arms this week. Shadow only.",
    exit="n/a.",
    kill="★ REV2 — RUN, AND THE VERDICT IS SPLIT. Detection PASSES: ATR at entry separates the "
         "±20pt dead band at AUC 0.683, permutation p = 0.0005, against a 0.60 bar stated in "
         "advance; nothing else on the desk clears it (ATR expansion 0.558, volume z 0.554, "
         "trade-count z 0.570, |flow z| 0.548, ER15 0.519 and not even significant). The MONEY "
         "fails: declining the lowest-ATR 48.2% turns the book from −$1.64/tr to +$1.71/tr "
         "(+$1,517.61 on 886 trades), and STRIP-BEST-3 takes that to −$266.64 — three trades of "
         "886 are the whole result. A walk-forward that fits the cut on the first half LOSES on "
         "that half (−$2.82/tr). ⚠ Note the ATR-normalised control: against an ATR-scaled dead "
         "band the same feature reads 0.531, a coin flip — §3's finding for the third time. It "
         "does not bite here only because the friction is paid in POINTS, not in ATR.",
    suggested_mode="shadow",
    owner="Claude — shadow arm",
    revert="n/a — shadow only.",
    money_gbp=0,
)

play(
    id="fix-two-byte-identical-shadow-arms-0828",
    window="BUILD", rank=5, tier="PARKED",
    topic="Two shadow A/Bs are byte-identical and have therefore tested NOTHING — fix the arm wiring",
    play="Fix the wiring so each variant actually diverges from its control, then restart both "
         "A/Bs from zero. Until then their &ldquo;perfect null&rdquo; must not be quoted.",
    mechanism="<code>capit_flip_live</code> and <code>capit_flip_t90</code> are identical on all 29 "
              "trades (−$445). <code>cx_clip_brk_live</code> and <code>cx_clip_brk_standdown</code> "
              "are identical on all 251 trades (−$848). One arm of each pair never diverged, so the "
              "control's trades are being recorded twice under two names.",
    rationale="A broken A/B does not fail loudly — it reports a PERFECT NULL, which reads as a "
              "clean negative result. And the same cluster inflates evidence four-fold: "
              "<code>cx_clip_brk_live</code>, <code>cx_clip_brk_standdown</code> and "
              "<code>cx_grindA_clip</code> all carry the same 251 trades, all of which also sit "
              "inside <code>bank20_grindA</code>'s 275.",
    number="29/29 and 251/251 trades identical. Four arm names on the leaderboard, one trade set.",
    section_ref="Part 2 §2 (instrument audit) and §9 disposition.",
    verification="After the fix, the two arms of each pair differ on at least one trade within a "
                 "day of running.",
    arms_when="n/a — shadow plumbing.",
    exit="n/a.",
    kill="n/a.",
    suggested_mode="observe",
    owner="Claude — shadow slate wiring",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="investigate-exhaustion-short-up-off-0828",
    window="BUILD", rank=6, tier="PARKED",
    topic="The exhaustion_short UP_OFF rule is the week's single biggest over-bench",
    play="Re-price the <code>UP_OFF</code> rule specifically: it benches "
         "<code>exhaustion_short</code> in every trend-up hour, and this week the up-hours are "
         "exactly where it earned.",
    mechanism="98 blocked legs worth +$516 of benched winners — the largest over-bench of any gate "
              "in the ledger. The rule is categorical (it sits in UP_OFF), so it cannot distinguish "
              "an up-hour the gate would have faded profitably from one it would not.",
    rationale="Part 1's independent replay agrees on the sign and disagrees on the certainty: it "
              "scores the exhaustion_short bench at +$442.65 saved over 34 signals but flags it "
              "NOT PROVEN, because the saving flips at a 0.5× stop width. Two instruments pointing "
              "opposite ways on the same gate is exactly what should be investigated rather than "
              "acted on.",
    number="98 blocked legs, +$516 of benched winners (Part 2.6 rec #10, MODERATE). Part 1 §7 "
           "scores the same bench at +$442.65 / +$13.02 per signal, verdict NOT PROVEN, "
           "P(≥0)=0.196.",
    section_ref="Part 2.6 recommendation #10; Part 1 §7 bench-replay table; Part 2 §9 notes the "
                "live fade-scalp trial is un-graded (14 fills, 9 of them MANUAL_CLAIM).",
    verification="A per-hour reprice of the 98 blocked legs on the gate's own exit stack, with the "
                 "stop-width sweep attached.",
    # ★★2026-08-29 REV2 — THE PLAY NOW CARRIES A RE-ARM CONDITION, BECAUSE IT WAS A DEADLOCK.
    # Part 2 §9 asks for 40+ fills on the gate's OWN exits before the fade-scalp trial can be
    # graded, and the gate cannot collect a single one while benched. See Part 3 Q7.
    arms_when="★ REV2 — ARM IT, on a dated window. The gate has been off since 2026-08-18 and the "
              "evidence everyone is waiting for can only be made while it is on. Era A fired 9.7 "
              "fills per armed day and 7 of the trial's 14 fills (50%) ended on the gate's own "
              "exits rather than on the claim button, so 40 machine-exited fills is about 80 fills "
              "is about EIGHT armed trading days. Arm Monday 2026-08-31 through Tuesday "
              "2026-09-15; grade on 40 machine-exited fills (MANUAL_CLAIM legs excluded from the "
              "grade and counted separately) or that date, whichever comes first.",
    exit="Its current cell — 2.0R both lots, stop 1.5×ATR — unchanged for the whole window. "
         "Changing it mid-window restarts the count.",
    kill="If the +$516 does not survive its own stop-width sweep, UP_OFF is fine and this closes. "
         "★ REV2 — and the exposure of collecting the sample is bounded and small: era A's entire "
         "146-fill history at the OLD config is −$158.00, or −$1.08 a fill, so 80 fills is about "
         "−$86 of expected cost against +$516 of benched winners this week alone. ⚠ If you would "
         "rather not arm it, that is a legitimate answer — but then THIS PLAY AND Part 2 §9's "
         "grading request must both be WITHDRAWN rather than carried, because they are asking for "
         "evidence the desk has decided not to produce.",
    suggested_mode="observe",
    owner="Claude — one reprice",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="shadow-untradeable-cutoff-45-0828",
    window="BUILD", rank=7, tier="SHADOW",
    topic="Trial the untradeable STAY-OUT cutoff at 45 in SHADOW — direction proven, exact value fitted",
    play="Run cutoff 45 in shadow for a week. Do <strong>not</strong> deploy it, and do not use 40.",
    mechanism="On a 51-day lake rebuild with 25 days of real trades the bands are monotone "
              "(−$38.62 / −$219.92 / −$345.92 per day). At the live cutoff of 65 the meter FAILS "
              "its placebo (P=0.120); at 40 it passes (P=0.029); 45 survives leave-3-out (+$972) "
              "and is positive in all 6 ISO weeks.",
    rationale="40 sits on a two-cell plateau, which is too narrow to ship — a threshold that is "
              "only right at one value is a fitted value, not a finding. 45 is the honest "
              "compromise and it still costs $542 of green days, so it is worth a shadow week "
              "before anyone types it into production.",
    number="Placebo P: 0.120 at 65, 0.029 at 40. Cutoff 45: leave-3-out +$972, positive in 6 of 6 "
           "ISO weeks, costs $542 of green days.",
    section_ref="Part 2.6 recommendation #4 (MODERATE — direction proven, exact value fitted).",
    verification="A shadow log of the meter's verdict at 45 beside its verdict at 65, per day.",
    arms_when="Shadow only.",
    exit="n/a.",
    kill="If the shadow week disagrees with the backtest's band monotonicity, drop it — a monotone "
         "band is the whole reason to believe this one.",
    suggested_mode="shadow",
    owner="Claude — shadow config",
    revert="n/a — shadow only.",
    money_gbp=0,
)

play(
    id="grade-router-timing-config-on-a-trend-week-0828",
    window="BUILD", rank=8, tier="SHADOW",
    topic="Shadow the router timing config (window 45m / step 5m / hold 3) — but the grade needs a TREND week",
    play="Run the timing config in shadow for a week that contains at least one genuine trend day, "
         "then decide. Do <strong>not</strong> deploy it off this sample.",
    mechanism="The ER × NET sweep's timing half gains +$440–$502 with 0–1 days made worse. But it "
              "differentiates on only 4–5 days, all of them inside one summer range regime.",
    # ★★2026-08-29 REV2 — "wait for a trend week" is not a plan and now has the count to prove it.
    rationale="This is Part 2.6's own assessment of its best single result and its worst sample, "
              "and it interlocks with a fact from Part 1: <strong>there was no trend day this "
              "week at all</strong>. ★ REV2 — AND WAITING FOR A TREND WEEK IS WAITING FOR "
              "SOMETHING THAT HAS NEVER HAPPENED. Counted over 51 sessions and 11 ISO weeks in the "
              "lake (2026-06-19 → 2026-08-28), on 5-minute path with ER ≥ 0.15: SIX weeks "
              "contained a trend DAY, and NOT ONE contained more than one. The rate is 0.55 trend "
              "days a week, so ten of them is eighteen weeks away. Worse, \"ER ≥ 0.15\" is not "
              "even well defined until you name the bar size — the same threshold on the same tape "
              "gives 0, 6, 18, 27 or 34 trend days at 1m / 5m / 15m / 30m / 60m path. So the "
              "condition is replaced: run it in shadow NOW and grade on FIVE TREND DAYS or "
              "2026-11-06, whichever comes first.",
    number="Timing config +$440–$502, 0–1 days worse, on 4–5 differentiating days. Router value "
           "splits +$381/day on chop-heavy days against −$64/day on trendy ones.",
    section_ref="Part 2.6 recommendation #8 (MODERATE) and its closing caveat (iii); Part 1 §8 for "
                "the no-trend-day finding.",
    verification="The shadow log covers at least one session with whole-day ER ≥ 0.15.",
    arms_when="Shadow only.",
    exit="n/a.",
    kill="If it is negative on the first trend day it sees, it is dead — a chop-fitted timing "
         "config is precisely what this is at risk of being.",
    suggested_mode="shadow",
    owner="Claude — shadow config",
    revert="n/a — shadow only.",
    money_gbp=0,
)

play(
    id="mgc-empty-seat-0828",
    window="BUILD", rank=9, tier="PARKED",
    topic="Gold: 80 runs and $15,196 of ceiling on the 08-28 freeze, and no gate at all — an empty seat, not a bleed",
    play="Keep hunting MGC gates, and keep them INVENTED FRESH — never port, clone or re-tune an "
         "MNQ gate onto gold. Nothing gold-side is close to a promotion.",
    mechanism="MGC printed 80 runs of ≥1.5×ATR this cycle (≥12 points against a typical 15-minute "
              "range of 8). We caught 0 and fought 0, because there is nothing on the instrument to "
              "catch or fight with. ★ REV2 — the cluster mix (46 UNCLASS, 14 VACUUM, 12 OPEN/NEWS, "
              "5 VOL-EXPANSION, 3 FLOW-LED) is NO LONGER quoted here as a hunting map: it is "
              "computed off the census's keep-strongest dedup, which this report's own VACUUM "
              "appendix shows selects local extrema and inflates the VACUUM rate 10.45% → 21.87% on "
              "MNQ. Gold has had no unselected-population re-run, so the honest statement is that "
              "we do not know how much of gold's 14 is the picker.",
    # ★★2026-08-29 REV2 — THE BAR-SOURCE BLOCKER IS RETIRED, AND THIS CARD WAS QUOTING THE STALE
    # ARTIFACT WHILE CITING THE FRESH ONE. "+$3.06/tr vs −$8.96/tr" comes from gf3_mgc_barsource.json
    # (written 08-25), and only from its 6-day "hole PRIMARY" sub-cell at n=56/53. The fresh
    # gf4_mgc_barsource.json (08-28, 32 days) has DEPTH-MID at −$1.21/tr on 506 trades and TRADE
    # BARS at −$0.41/tr on 299 — SAME SIGN, no flip, at any cut. The §8 cross-reference was also
    # wrong: Movement 3 §8 is the chop-day turn scalp. It now points at the rebuilt gold section.
    rationale="The $15,196 is the SIZE OF THE SEAT, not money forgone: with no gate, sitting out is "
              "not a decision that went wrong. ★ REV2 — AND THE STANDING BLOCKER IS GONE. The "
              "bar-source scare (lab builds bars from the depth MID, production from TRADES, and "
              "the sign flips on that alone) was measured on SIX days. Re-run on THIRTY-TWO it does "
              "not survive: −$1.21/tr on mid bars (n=506) against −$0.41/tr on trade bars (n=299), "
              "same sign, and −$1.76 vs −$0.41 on the 19 days both tapes cover. What the bar source "
              "actually controls is FIRE RATE, not quality — 35.2% of the mid arm's trades open in "
              "a minute where the trade tape printed nothing at all. The replacement blocker is "
              "smaller and more useful: gold's money is all in the busiest quartile of the tape "
              "(+$27.11/tr against −$11.85 in the quietest), and every attempt to turn that into a "
              "threshold has been a fit — an activity floor worth +$40.80/tr in-sample makes "
              "−$11.92/tr forward.",
    number="80 runs, $15,196 ceiling, 0 caught, 0 fought. Bar source over 32 days: −$1.21/tr (mid, "
           "n=506) vs −$0.41/tr (trade, n=299) — no flip. Best-looking cell, the double hole, is "
           "+$921.50 on 311 trades and −$109.00 once its three best trades are removed. MGC is "
           "$10.00/point — never price it with the MNQ $2.00 multiplier.",
    section_ref="Movement 3 → THE MGC GREENFIELD (rebuilt from the gf4_* artifacts) §G3 for the "
                "bar source, §G4 for the activity finding, §G5 for the floor that died forward, "
                "§G6 for the double hole. ⚠ THE 80/$15,196 IS THE 2026-08-28 CENSUS FREEZE, which "
                "is the freeze Movements 2 and 3 were computed against. The MGC census PRINTED in "
                "Movement 1 of this document is a week younger (2026-08-30→09-04) and reads 71 "
                "runs / $13,238 / 0 caught. Both say the same thing — an empty seat — and neither "
                "number should be quoted as the other. See the two-week seam at the top of the "
                "report. ★ And read this row against the 2026-09-04 gold hunt in the Movement 3 "
                "ADDENDUM (NOT-AN-ACTION #11, gold-four-cells-null-0904), which is a harder null "
                "than this row, and against SATURDAY #9 (lake-gold-wrong-contract-0904), which "
                "puts the 32-day bar-source re-run itself on notice.",
    verification="Any gold result must name its bar source AND its sample size in the same sentence "
                 "as its number. The claim this card carried for a week was a 56-trade sub-cell on "
                 "six days.",
    arms_when="Nothing arms. Shadow only, and not yet.",
    exit="n/a.",
    kill="Strip-the-best-trades. Every gold arm on the board is negative pooled and MORE negative "
         "with its three best trades removed; the one positive cell (the double hole) inverts on "
         "three trades of 311. Nothing ships until an arm survives that with a pre-registered "
         "activity measure run forward.",
    suggested_mode="observe",
    owner="Claude — gold programme",
    revert="n/a.",
    money_gbp=0,
)

# ══════════════════════════════════════════════════════════════════════════════════════════
# HOLD — already right, do not touch
# ══════════════════════════════════════════════════════════════════════════════════════════

play(
    id="hold-the-chop-bench-0828",
    window="HOLD", rank=1, tier="LIVE",
    topic="Keep the chop bench — but stop quoting the dollar figure",
    play="Leave the policy exactly as it is: bench everything with no confirmed direction. And do "
         "not quote the $810 at anybody, including yourself.",
    mechanism="Every benched gate's suppressed intents were collapsed to distinct impulses (187) "
              "and walked forward on the 250ms tick tape under each gate's own live exit. Of the "
              "127 priced signals, the 66 that fired into CHOP account for essentially the whole "
              "saving: −$771.78, or −$11.69 a signal, versus a wash in both trend buckets.",
    rationale="The direction is consistent under a lot of ways to break it and the magnitude is "
              "not. Drop any single day and the saving is still +$419 to +$955; strip the 3 "
              "biggest saves and it is +$455; reprice at 1.0R through 3.0R and it stays positive at "
              "all five widths. But the bootstrap band is −$639 to +$2,141 and P(the bench saved "
              "nothing or lost money) = 0.13.",
    number="127 priced signals, bench saved +$810.44 (+$6.38/signal). CHOP bucket 66 signals "
           "−$771.78. Aligned-trend bucket 50 signals −$0.81/signal — benching in trend is FREE. "
           "Label-shuffle placebo on the aligned-vs-chop gap: P = 0.178. It is a candidate, not a "
           "finding.",
    section_ref="Part 1 §7 and §8; Movement 2 agrees independently — the six gates fired into this "
                "week's runs lose −$741.50 on 32 lots.",
    verification="Nothing to verify — this is the current policy.",
    arms_when="n/a — it is already in force.",
    exit="n/a.",
    kill="Revive to a LIVE claim at ~350 signals, or after one genuine TREND week — the aligned "
         "bucket is the thin half of the sample and 61.5% of this week's minutes were chop.",
    suggested_mode="observe",
    owner="Nobody — no change",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="hold-arm-aggressively-in-aligned-trend-0828",
    window="HOLD", rank=2, tier="LIVE",
    topic="Keep the router's aligned-momentum arm — and note WHY it stays, which is not the six winners",
    play="Leave the arm behaviour alone: arm <code>grind_long</code> + <code>abs_veto_long</code> "
         "into a confirmed aligned break.",
    mechanism="One arm at Friday 14:45:03Z, four lots in 58 seconds, four winners, +$181.50. Fifty "
              "minutes later the router benched both 46.5 points under the day high and the tape "
              "then fell 328 points. One arm and one bench, both right, with money on both sides.",
    rationale="★ It stays live because the benched-signal replay says arming in aligned trend is "
              "FREE (−$0.81 per signal over 50 signals) — <strong>not</strong> because six lots "
              "won. Six-for-six on lots that are three gates agreeing about one push, each booking "
              "two lots of a scale-out, is n=1 with a wide grin.",
    number="6 lots, 6 winners, +$330.00 for the week — one market event inside 51 minutes. The "
           "supporting number is the aligned bucket: 50 benched signals, −$0.81 each.",
    section_ref="Part 1 §2, §9 and §11 disposition (KEEP LIVE).",
    verification="n/a — no change.",
    arms_when="n/a.",
    exit="n/a.",
    kill="If the aligned bucket turns materially negative on a trend week, the free-to-arm argument "
         "goes and the policy should be re-examined.",
    suggested_mode="observe",
    owner="Nobody — no change",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="hold-the-stop-contract-fix-0828",
    window="HOLD", rank=3, tier="LIVE",
    topic="Do NOT revert the stop-contract fix — 31 clean days, but read the caveat",
    play="Leave it in production.",
    mechanism="Every STOP_UNFILLED the desk has ever booked — all 26, worth −$1,377.50 — happened "
              "between 21 and 28 July. The last one was a month ago.",
    rationale="The fair caveat is exposure, not time: the tournament has traded 6 lots in the last "
              "nine sessions, so the recent stretch of that clean record is thin and largely "
              "untested rather than proven. Do not read &ldquo;31 clean days&rdquo; as 31 days of "
              "exposure.",
    number="21–28 July: 26 STOP_UNFILLED exits, −$1,377.50. 29 July – 28 August: 0. This week: 0.",
    section_ref="Part 1 §10.",
    verification="n/a.",
    arms_when="n/a.",
    exit="n/a.",
    kill="n/a — reverting it is the failure mode.",
    suggested_mode="observe",
    owner="Nobody — already in production",
    revert="<strong>Do NOT revert it.</strong>",
    money_gbp=0,
)

play(
    id="hold-adaptive-exit-off-0828",
    window="HOLD", rank=4, tier="LIVE",
    topic="Leave adaptive_exit OFF — and leave data/exit_overrides.json alone this weekend",
    play="Change nothing about the exit selector or the per-gate exit cells.",
    mechanism="All 12 sub-slots already return <code>adaptive_exit=False</code>. On the only day "
              "this week with real tournament trades, a fixed always-SCALP exit beat the "
              "counterfactual selector by $1,400 (+$799 vs −$600), and 18 of the week's 22 "
              "&ldquo;optimal picks&rdquo; were all-modes-identical and carried no information.",
    rationale="Independently, Part 2's exit lab widened the window as far as this desk can go — "
              "831,379 five-second bars, three entry pools including the retired V5 desk's real "
              "fills, 6,736 scored entries, a 63-cell grid plus six chandeliers — and graded 20 "
              "rung-cells. <strong>All 20 failed.</strong> Not one survived strip-the-best-3, "
              "leave-one-day-out, the half-split and the pool-split together.",
    number="20 of 20 rung-cells fail. Selector vs fixed on the only live day: −$600 vs +$799. "
           "Written to <code>data/exit_overrides_proposed_v2.json</code> with DEPLOY=false and a "
           "cause of death per cell.",
    section_ref="Part 2 §8–§9 (the exit ladder, a NULL with named tests); Part 2.6 recommendation "
                "#9.",
    verification="n/a.",
    arms_when="n/a.",
    exit="n/a.",
    kill="Revive the MED-TREND ride-vs-bank gap (+$3.20/signal, 4 of 5 families) as a SINGLE "
         "pre-registered hypothesis — not as the winner of a 72-cell search.",
    suggested_mode="observe",
    owner="Nobody — no change",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="hold-er-and-net-0828",
    window="HOLD", rank=5, tier="LIVE",
    topic="Do NOT move the router's ER or NET_MIN thresholds",
    play="Leave ER at 0.15 and NET_MIN at 30.",
    mechanism="The pair sits on a 3-cell plateau with a 0.6% spread, and both the live-managed and "
              "the full-historical universes independently pick the same cell.",
    rationale="A plateau that two independent universes agree on is the best evidence a threshold "
              "can have, and it is evidence for LEAVING IT ALONE. The tuning opportunity this week "
              "is timing (MONDAY #2), not level.",
    number="3-cell plateau, 0.6% spread, agreed by both universes in a 40-day sweep.",
    section_ref="Part 2.6 recommendation #8.",
    verification="n/a.",
    arms_when="n/a.",
    exit="n/a.",
    kill="Re-open only on a sweep that includes a trend week.",
    suggested_mode="observe",
    owner="Nobody — no change",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="hold-the-benches-movement2-0828",
    window="HOLD", rank=6, tier="LIVE",
    topic="Do not re-arm any gate on the strength of a missed run — the idle-gate lab says it a third time",
    play="Leave every benched gate benched. A big run the desk sat out is not an argument for "
         "arming the gate that was nearest to it.",
    mechanism="Every one of this week's 62 sat-out runs was replayed second by second — 36,600 "
              "decision-seconds of real quotes, each gate's own deciders, each gate's own A/B exit "
              "pair, $1.50 a round trip. Fired as configured, the six gates take 32 lots into those "
              "runs and lose −$741.50 (−$23.17/lot, 18.8% win).",
    # ★2026-08-29 REV2 — the random-entry control has been RESTATED, and the play does not need it.
    # Rev1 read "not one gate's trigger beats it, 0 of 6" — a direction-handed control against a
    # both-directions gate figure, which loses by construction. The HOLD rests on the MECH line.
    rationale="★ The direct measurement is the argument: fired as configured into the runs the "
              "desk sat out, the six gates lose money. A random-entry control was also run — show "
              "up at a RANDOM second inside the same pre-ignition window, handed the run's "
              "direction — and it comes back a NULL: scored like for like the gates beat it on 3 "
              "of 5 in-direction and 4 of 5 direction-blind, on 2–10 lots each, and only "
              "exhaustion_short separates at all (P=0.033 raw, 0.166 Holm-adjusted). It neither "
              "supports nor undermines the hold. ★ REV2: an earlier draft of this card said the "
              "control killed all six triggers. It does not, and the hold does not need it to.",
    number="MECH layer: 32 lots, −$741.50 (−$23.17/lot, 18.8% win). Ungated: 114 lots, −$168.50. A "
           "724-cell threshold sweep finds no cell that is both positive and more than three trades "
           "wide. Random-entry control: NULL — nothing separates at n=2–10 in-direction lots.",
    section_ref="Movement 2 §2, §4 and §5 (recomputed this cycle on this week's census freeze); "
                "control re-scored by scripts/rev2_m2_indirection_control.py.",
    verification="n/a — it is the current policy.",
    arms_when="n/a.",
    exit="n/a.",
    kill="A gate whose trigger beats the random-entry control on n≥40 would overturn this and would "
         "be a genuine finding.",
    suggested_mode="observe",
    owner="Nobody — no change",
    revert="n/a.",
    money_gbp=0,
)

# ══════════════════════════════════════════════════════════════════════════════════════════
# NOT-AN-ACTION — refuted or withdrawn, printed so nobody re-proposes them
# ══════════════════════════════════════════════════════════════════════════════════════════

play(
    id="not-an-action-shadow-is-green-so-arm-it-0828",
    window="NOT-AN-ACTION", rank=1, tier="REFUTED",
    topic='★ "The momentum shadow book is green while the routed book sits flat" — REFUTED as an arming argument, 106 times over',
    play="When the open-hour watcher makes this argument — and it made it 106 times this week — it "
         "carries no information about the gate it is asking you to arm. Do not act on it.",
    mechanism="Reprice the LIVE gates' own suppressed intents at the shadow's exact ruler (2.0R "
              "target, 1.0×ATR stop) and you get <strong>−$143.61 on 65 signals</strong>, against "
              "the shadow's <strong>+$948.50 on 45</strong>. Same week, same instrument, same exit "
              "rule, opposite sign — so the exit is not the difference. The gap is entirely the "
              "ENTRY POPULATION: the shadow variants run a looser trigger with no ATR floor, so "
              "they fire in exactly the tape where the live gate's floor refuses.",
    rationale="There is no reformulation that makes a floorless variant's P&amp;L evidence about a "
              "floored gate. The shadow result itself stands — it is the promotion candidate at "
              "MONDAY #1. Only its use as a reason to arm the LIVE gate is dead.",
    number="106 [ACT] alerts this week; 5 router arms. The alerts name abs_veto_short 59 times, "
           "abs_veto_long 54, exhaustion_short 16, grind_long 9, rgv_short 9, capitulation_long 4. "
           "Shadow +$948.50 / n=45 vs live suppressed intents at the identical ruler −$143.61 / "
           "n=65.",
    section_ref="Part 1 §6 and §11 disposition (REFUTED as an arming argument).",
    verification="n/a.",
    arms_when="Never, on this argument.",
    exit="n/a.",
    kill="n/a — this IS the kill.",
    suggested_mode="observe",
    owner="Nobody — it is a refutation",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-relegate-a-direction-0828",
    window="NOT-AN-ACTION", rank=2, tier="REFUTED",
    topic="Never relegate a DIRECTION — tune the side, keep the direction",
    play="When a gate's long side is red and its short side green, do not switch the red side off.",
    mechanism="Across all 7 shadow arms that have a red side and a green side with ≥20 trades each, "
              "the red side's green-day rate averages 43% against the green side's 50%. "
              "<code>thrust_loose</code>'s LOSING long side is green on MORE days than its winning "
              "short side.",
    rationale="Sides differ in magnitude, not in whether they work. A direction that is green on "
              "43% of days is not broken; it is smaller. This is why MONDAY #1 promotes "
              "abs_veto_55s two-sided with the long side merely sized smaller.",
    number="7 arms, red-side green-day rate 43% vs green-side 50%. Spearman between the two sides' "
           "daily P&amp;L is not the point — the point is that both sides fire on the same days.",
    section_ref="Part 2 §9 disposition (REFUTED, named test).",
    verification="n/a.",
    arms_when="n/a.",
    exit="n/a.",
    kill="n/a.",
    suggested_mode="observe",
    owner="Nobody — standing principle",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-searched-day-classifier-0828",
    window="NOT-AN-ACTION", rank=3, tier="REFUTED",
    topic="The searched causal day-classifier for the Open Rider — REFUTED by three tests, do not search again",
    play="Do not run another single-feature threshold search over this sample. The day-level "
         "INSTRUMENT is still worth building (BUILD #2); the SEARCH is dead.",
    mechanism="Eight features were hunted, placebo-controlled and corrected for having looked eight "
              "times. (1) Placebo against random day-removal, 10,000 draws: only 2 of 8 features "
              "beat it even raw. (2) Holm correction across the 8: best adjusted p = 0.136. (3) A "
              "genuine out-of-sample leg, fit on 41 days and tested on 9: 4 held, 4 failed, and "
              "even the holders still lost money.",
    rationale="Removing 60% of days looks brilliant whenever the removed 60% lost — which is why "
              "the placebo is the test that matters here and why a raw win means nothing. The "
              "concentration the operator identified is REAL (6 green days +$3,066 vs 9 red "
              "−$5,626); the searched classifier that was supposed to exploit it is not.",
    number="8 features, best Holm-adjusted p = 0.136. OOS 41-fit/9-test: 4 of 8 held, all still "
           "losing money. Oracle day-selection ≈ $1,022/week — real, and only knowable afterwards.",
    section_ref="Part 2 §3, §3d and §9 disposition.",
    verification="n/a.",
    arms_when="Never on this evidence.",
    exit="n/a.",
    kill="n/a — this IS the kill. The pre-registered ATR≥9.5 filter is the only honest instrument "
         "still running and it needs 50 more sessions. Do not tune it, do not add a feature, do "
         "not stop it early.",
    suggested_mode="observe",
    owner="Nobody — it is a refutation",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-one-shared-day-classifier-0828",
    window="NOT-AN-ACTION", rank=4, tier="REFUTED",
    topic="One day-classifier serving BOTH MNQ and MGC — refuted; detection must be built twice",
    play="Do not build a shared good-day detector across the two instruments.",
    mechanism="On the 25 days we hold both tapes, label agreement is <strong>44% against a 49% "
              "chance baseline</strong> — a lift of MINUS five points — and the Spearman "
              "correlation between the two instruments' daily P&amp;L is +0.019.",
    rationale="It was a genuinely attractive idea: two strategies on two instruments both live or "
              "die on a minority of days, so one classifier serving both would have been worth more "
              "than either gate. The good days are simply unrelated. What DOES transfer is "
              "threshold SELECTIVITY in percentile space, which is a much weaker claim and is "
              "already how the gold work is being done.",
    number="44% agreement vs 49% chance, n=25 days. Spearman +0.019.",
    section_ref="Part 2 §9 disposition (REFUTED, named test).",
    verification="n/a.",
    arms_when="n/a.",
    exit="n/a.",
    kill="n/a.",
    suggested_mode="observe",
    owner="Nobody — it is a refutation",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-big-trend-exit-rung-0828",
    window="NOT-AN-ACTION", rank=5, tier="REFUTED",
    topic="The BIG-TREND exit rung — refuted at usable n, after the window was widened as far as this desk can go",
    play="Do not ship a special exit for the BIG-TREND rung, and do not edit "
         "<code>data/exit_overrides.json</code> this weekend.",
    mechanism="At ER≥0.40 — the only boundary where the rung carries 71–192 signals per family over "
              "25–37 days — every family's best-of-72 exit is negative and the first/second-half "
              "split flips sign in 3 of 5. At ER≥0.50 the rung is 3.0% of tape-minutes and n=21–66; "
              "the two apparently-good cells (capitulation +$34.20 and +$82.10) strip to −$47.50 "
              "and −$65.20 on three trades.",
    rationale="This has been half-believed on this desk for weeks on the strength of a tiny sample, "
              "and the honest fix was to widen the window rather than argue about it: 831,379 "
              "five-second bars, three independent entry pools, 6,736 scored entries. It is refuted "
              "as a place where a SPECIAL exit earns its keep — <strong>not</strong> refuted as a "
              "market state.",
    number="20 of 20 rung-cells graded, 20 failed. None survived strip-best-3 + LODO + half-split + "
           "pool-split together.",
    section_ref="Part 2 §8 and §9 disposition (REFUTED at usable n).",
    verification="n/a.",
    arms_when="Never on this evidence.",
    exit="n/a.",
    kill="n/a — this IS the kill.",
    suggested_mode="observe",
    owner="Nobody — it is a refutation",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-coil-brk-0828",
    window="NOT-AN-ACTION", rank=6, tier="REFUTED",
    topic="COIL-BRK — this week's fresh greenfield candidate, built and killed inside one cycle",
    play="Do not shadow it, do not re-tune it. It is a clock, not a trigger.",
    mechanism="Four independent fatal tests. <strong>(1)</strong> Out of sample it inverts: "
              "+$3.87/trade in sample, <strong>−$4.62</strong> out of it. <strong>(2)</strong> It "
              "is three trades wide: strip its best 3 of 513 and +$2.20/trade becomes −$0.44. "
              "<strong>(3)</strong> The placebo beats it — the same rule taken 30 minutes EARLY, "
              "when the coil condition has not happened yet, books +$3.55/trade against the real "
              "signal's +$2.20, and 60 minutes early also beats it. <strong>(4)</strong> It is a "
              "one-sided artefact: LONG −$2.05/trade, SHORT +$6.39, on a tape with a known short "
              "drift, green on only 22 of 52 days.",
    rationale="★ The shape of the placebo ladder is the tell and it is worth learning. The shifted "
              "copies decay SMOOTHLY from +$3.55 at 30 minutes to −$11.29 at 8 hours. That is not "
              "a signal being destroyed by misalignment — it is a slow intraday drift being sampled "
              "at different points. And the control settles it: the UNARMED break, with the coil "
              "filter switched off entirely, books +$1,625.70 on 1,356 trades. The filter the whole "
              "candidate is built around SUBTRACTS value.",
    number="n=513, +$1,126.27, +$2.195/tr. IS +$3.865 / OOS −$4.615. Strip-best-3 −$0.437. "
           "Sign-flip −$3.496. 2 of 5 placebos beat it. Arm ladder flips sign four times.",
    section_ref="Movement 3 §4 (built and killed this cycle).",
    verification="n/a.",
    arms_when="Never.",
    exit="n/a.",
    kill="n/a — this IS the kill.",
    suggested_mode="observe",
    owner="Nobody — it is a refutation",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-promote-a-frozen-candidate-0828",
    window="NOT-AN-ACTION", rank=7, tier="REFUTED",
    topic="Do not promote any of the five frozen greenfield candidates on their out-of-sample bounce",
    play="<code>UNCL-RIDE-ER</code> and <code>board_atrband</code> both show a positive OOS leg this "
         "week. Leave them parked.",
    mechanism="Both OOS legs are 27 and 29 trades over <strong>4 sessions</strong>, and both are "
              "driven entirely by their LONG side (+$15.56 and +$20.21 a trade) while both SHORT "
              "sides are red. Over their whole lives both are still net negative (−$483.60 and "
              "−$334.60). Four days is not a forward test; it is a sample of the week's drift.",
    rationale="★ The reassuring half of this table is the other three. <code>FL-4 "
              "flow_ignition</code> went from +$4.84/trade in sample to <strong>−$16.82</strong> "
              "out of it, and <code>MOMBRK</code> from +$3.66 to −$0.56 at an 11% win rate — and "
              "<strong>both were already REFUTED by their own placebo tests last week.</strong> "
              "The forward tape has now agreed with the placebo. The kill tests are calling it "
              "right, which is the strongest methodological result in the movement.",
    number="5 candidates forward-tested on tape none had seen. 4 of 5 net negative over their whole "
           "life. Best OOS legs: 27 and 29 trades over 4 days, both long-side only.",
    section_ref="Movement 3 §5 (the forward test, computed this cycle).",
    verification="n/a.",
    arms_when="Never on a 4-day OOS leg.",
    exit="n/a.",
    kill="n/a.",
    suggested_mode="observe",
    owner="Nobody — it is a refutation",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-six-for-six-0828",
    window="NOT-AN-ACTION", rank=8, tier="REFUTED",
    topic='"The tournament went 6 for 6 this week" — that is n=1 with a wide grin, not six observations',
    play="Do not draw any conclusion from the week's 100% win rate, in either direction.",
    mechanism="Three gates fired within 51 minutes of each other on the same up-leg of the same "
              "tape, and each booked TWO lots because the slate is a scale-out. So the A and B lots "
              "are one signal with two different exits, and the three signals are three gates "
              "agreeing about one push. It is one market event sampled six times.",
    rationale="This is the same standing error as a rolling-window &ldquo;3 of 3 confirmed&rdquo;, "
              "and it is worth naming on the card because a 100% week is exactly the number that "
              "gets quoted. Every quantitative claim in Part 1 is deliberately built on populations "
              "of 30–130 signals instead.",
    number="6 lots, 3 signals, 1 push, 51 minutes, +$330.00. The desk was armed for 24h31m of 720 "
           "available gate-hours — <strong>3.40%</strong> of the week.",
    section_ref="Part 1 §2 (&ldquo;a win rate of 100% on six lots is one observation, not six&rdquo;) "
                "and §11 standing caveats.",
    verification="n/a.",
    arms_when="n/a.",
    exit="n/a.",
    kill="n/a.",
    suggested_mode="observe",
    owner="Nobody — a standing caution",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="not-an-action-claim-button-0828",
    window="NOT-AN-ACTION", rank=9, tier="LIVE",
    topic="Your Claim button — neither helping nor hurting this week. Leave it alone.",
    play="No change. Keep claiming when you want to.",
    # ★2026-08-29 REV2 — RE-DERIVED AT THE VENUE'S OWN ENTRY ATR. Rev1 replayed these lots at a
    # MODELLED 23.5-point ATR and Part 2.6 §2.1 at about 25.5, and the two sections printed
    # different answers for the same arm. Neither had to guess: the tournament places a native
    # 1×ATR stop with every fill and its auxPrice is in the journal, so the distance from the fill
    # IS the entry ATR — stp-000003/4 at 29,714.00 against a 29,738.25 fill says 24.25, and
    # stp-000005/6 agree. Harness: scripts/rev2_arm_own_exits.py.
    mechanism="Three of the six lots ended MANUAL_CLAIM. Each was re-run forward on the tick tape "
              "under its own configured exit stack, at the <strong>24.25</strong>-point entry ATR "
              "read off the native 1×ATR stop the desk actually placed (<code>stp-000003/4</code> "
              "at 29,714.00 against a 29,738.25 fill) rather than a modelled one. You gave up "
              "$78.25 on grind_long_A by banking early and saved $72.00 on grind_long_B by not "
              "waiting for a trail that mathematically could not arm — its chandelier needed "
              "+84.9 points and the run peaked at +73.5.",
    rationale="The individual lots were not close; the aggregate is a dead heat. That is worth "
              "printing precisely because a claim TRUNCATES the gate's own exit stack, so it is the "
              "kind of thing that could quietly cost money for months.",
    number="Three claimed lots: you booked +$136.50, their own exits were worth +$141.00 — a delta "
           "of <strong>+$4.50</strong> across the week. The whole tournament week on its own exits "
           "is +$334.50 against the +$330.00 booked. (Rev1 of this card said −$0.86 / +$329.15, on "
           "a modelled 23.5-point ATR; the venue's own stops say 24.25.)",
    section_ref="Part 1 §3 and §11 disposition (NOT AN ACTION); harness scripts/rev2_arm_own_exits.py.",
    verification="n/a.",
    arms_when="n/a.",
    exit="n/a.",
    kill="If the delta goes materially negative over 20+ claimed lots, revisit.",
    suggested_mode="observe",
    owner="Nobody — no change",
    revert="n/a.",
    money_gbp=0,
)

# ★★2026-08-29 REV2 — THE DAY RIDER GETS A ROW. Rev 1's card had nothing at all about the bigger
# book: the rider moved the account by −$1,576.94, owns the week's largest single loss and still
# runs naked by the operator's 2026-08-20 decision, and the only section discussing it (Part 1.6)
# did not regenerate and is quarantined behind a stale banner. Re-priced on this week's own tape in
# Part 1 §3b (scripts/rev2_rider_stop_week.py), and the re-pricing turned up something bigger.
play(
    id="rider-off-tape-fills-0828",
    window="SATURDAY", rank=4, tier="LIVE",
    topic="★★ 74% of the day rider's loss this week is a FILL ARTEFACT — every entry is a split order whose residual leg is priced 0.1% adverse, off the tape",
    play="Audit the split-fill path on the rider's order route and reject or re-price any leg that "
         "did not trade. This is not a strategy change and it does not touch a threshold.",
    mechanism="Every 4-lot rider order this week filled in two pieces: one leg at a price the tape "
              "actually printed, and the residual at <strong>base × (1 ± 0.001), always "
              "ADVERSE</strong>. 2026-08-26 13:44:06 bought 1 lot at 29,301.00 and <strong>3 at "
              "29,330.00</strong> while the tape's whole ±10s range was 29,282.50–29,308.75; "
              "2026-08-28 12:39:06 bought 1 at 29,635.25 and 3 at 29,664.75 against a range of "
              "29,632.75–29,637.75. The trades row then records the fill-VWAP of the two, so the "
              "book's entry price is a number the market never printed.",
    rationale="It is the largest single item on the rider's week and it is not a trading decision — "
              "so it is fixable without deciding anything about strategy. It also corrupts every "
              "downstream measurement: a protective stop placed k×ATR under a booked entry that is "
              "29 points off the tape is under water before the position exists, which is exactly "
              "what broke the first version of §3b's stop grid.",
    number="12 fill events with an off-tape leg from the 08-21 carry entry to Friday's close, "
           "20 of 116 lots (17%), <strong>$1,170.50 of adverse pricing</strong> against a rider "
           "week of −$1,576.94. That is 74% of the loss.",
    section_ref="Part 1 §3b (new this revision); harness scripts/rev2_rider_stop_week.py, which "
                "verifies every base leg IS inside the tape's ±10s range and every off leg is not.",
    verification="Re-run the audit next Friday. A week with zero off-tape legs, or with the "
                 "residual priced at the tape, is the fix landing.",
    arms_when="Immediately — it is execution plumbing and it cannot change what the rider trades.",
    exit="n/a.",
    kill="If the 0.1% offset turns out to be a paper-broker simulation artefact that will not exist "
         "on a live route, then it is a MEASUREMENT correction rather than a fix — but in that case "
         "every P&L number this desk has ever quoted from a split fill is overstated in the same "
         "direction, and that needs saying rather than shrugging at.",
    suggested_mode="deploy",
    owner="Garrath — order route / fill handling",
    revert="n/a — it is an audit before it is a change.",
    money_gbp=0,
)

play(
    id="hold-rider-naked-reaffirmed-0828",
    window="HOLD", rank=7, tier="LIVE",
    topic="The day rider stays NAKED — your 2026-08-20 decision re-priced on this week's tape, and it holds",
    play="No change. The rider keeps running without a protective stop.",
    mechanism="All thirteen rider positions of the week raced forward on lake ticks at 0.5–3.0× the "
              "ATR the rider itself froze at entry, one stop per position, $1.50 the round trip. On "
              "the TWELVE positions this week actually opened, naked made <strong>+$572.50</strong> "
              "and <em>every</em> stop width lost money — the best of them, the tightest at 0.5×, "
              "made −$617.44.",
    rationale="The whole apparent case for a stop is ONE position: the 08-21 four-lot carry, "
              "−$2,149.44 naked against −$34.56 at 0.5×. But that position was carried through a "
              "49-hour CME halt, and <strong>a stop cannot fill in a closed market</strong>. What "
              "would have prevented it is the standing flat-by-20:40Z rule, which failed for an "
              "unrelated reason. Grading the no-stop decision on that trade grades it on the one "
              "night a stop was guaranteed not to work. ★ Note the SLOPE too: the grid worsens "
              "monotonically as the stop widens, which is the signature of entries that go adverse "
              "immediately — an entry problem, not a stop problem.",
    number="Ex-carry: naked +$572.50 vs best stop −$617.44 — the no-stop policy wins by $1,189.94 "
           "on this week's own decisions. Including the carry, 0.5× beats naked by $924.94, and "
           "that is one trade of thirteen.",
    section_ref="Part 1 §3b (new this revision); harness scripts/rev2_rider_stop_week.py.",
    verification="n/a — it is the current policy, now with a dated re-price against it.",
    arms_when="n/a.",
    exit="n/a.",
    kill="A week in which the rider is stopped out of a position it would have recovered, or in "
         "which naked loses to a stop on the rider's OWN entries (not on a carry), re-opens this. "
         "★ And the honest trigger: it should be re-priced EVERY week, because that is the "
         "difference between a standing decision and an unwatched one.",
    suggested_mode="observe",
    owner="Garrath — it is your standing decision of 2026-08-20",
    revert="Set PLACE_VENUE_STOP = True in src/gazbot7/day_rider.py.",
    money_gbp=0,
)

play(
    id="not-an-action-capitulation-armed-by-rota-0828",
    window="NOT-AN-ACTION", rank=10, tier="PARKED",
    topic="★ capitulation_long is armed by a CRON, not by a decision — and it produced the week's largest single win",
    play="This needs a Saturday call that is not a code change: either the router should own "
         "<code>capitulation_long</code> like the other five gates, or the asymmetry should be "
         "written down as deliberate. Right now it is neither, and that is why it is here rather "
         "than in the SATURDAY window.",
    mechanism="<code>reactivate_gates.py</code> re-arms three gates at 22:00Z nightly. The router "
              "benches two of them within 32–38 seconds and leaves the fader standing. So "
              "<code>capitulation_long</code> sat armed for 17h45m and was the one gate awake when "
              "the 14:00Z flush came. The router DID read it and chose to keep it — that part was a "
              "decision — but nothing decided to ARM it.",
    rationale="Being right by rota is not the same as being right. 84% of the desk's entire armed "
              "time this week came from a cron the router does not clean up, and it produced +$148.50 "
              "of the week's +$330.00. That is luck wearing a policy's coat, and next time the rota "
              "leaves a gate standing into the wrong tape nobody will have decided that either.",
    number="capitulation_long armed 20h31m = 17.10% duty, 84% of ALL armed gate-time this week. "
           "The desk overall used 24h31m of 720 available gate-hours (3.40%). Its two lots made "
           "+$148.50.",
    section_ref="Part 1 §4 (every armed window, with who opened and closed it) and §11 disposition "
                "(PROCESS, needs a Saturday call).",
    # ★★2026-08-29 REV2 — THIS IS NOW A DECISION, NOT AN OBSERVATION, AND THE EVIDENCE IS IN.
    # Part 3 Q6 separates the three things that were being run together. capit_loose (−$16,681 on
    # 1,038, 17.2% win) is NOT this gate: it is the require_flip=False / 1.0R config the desk
    # REVERTED on 2026-08-02 after finding its supporting statistic was an MFE measure used as a
    # win rate (29% ordering-correct against a 50% breakeven). The live gate's own counterfactual
    # is capit_live_mirror: −$15.67 a fire over 352 unbenched fires at 12.5% win. The live gate
    # took 34 of those 352 — the 10% the switch file happened to leave armed — for +$63.00.
    verification="Either the router's switch writes cover capitulation_long, or a comment in "
                 "reactivate_gates.py states the carve-out and why. ★ REV2 — and the number that "
                 "should settle it: the gate's unbenched mirror (capit_live_mirror, its own live "
                 "parameters) is −$15.67 a fire over 352 fires at a 12.5% win rate. Its live "
                 "all-time record is +$63.00 on 34 fills — which is LESS than the +$148.50 it made "
                 "on 2026-08-28 alone, so on the other 32 fills of its life it is −$85.50. The "
                 "positive record is what BENCHING selected, not what the gate does.",
    arms_when="n/a.",
    exit="n/a.",
    kill="★ REV2 — no longer 'a governance question, not a hypothesis'. There are exactly two "
         "defensible positions and 'leave it' is not one of them. EITHER the router owns it like "
         "the other five (remove it from reactivate_gates.py's roster and let the tick decide) — "
         "leaving the arming of a gate whose unbenched counterfactual loses $15.67 a fire to a "
         "clock is leaving $15.67 a fire to a clock. OR the asymmetry is written down as "
         "deliberate, with its reason, inside reactivate_gates.py — because a carve-out nobody can "
         "find the rationale for is indistinguishable from a bug, and this one produced the week's "
         "largest single win, which is the most dangerous way for a bug to behave. ⚠ n=34 live "
         "fills and the mirror is a replay, so neither number is strong — but the decision is "
         "about which instrument owns the switch, and that does not need n.",
    suggested_mode="observe",
    owner="Garrath — a decision, not a deploy",
    revert="n/a.",
    money_gbp=0,
)


# ══════════════════════════════════════════════════════════════════════════════════════════
# ★★2026-08-30 — THE LATE-SECTION SWEEP. Part 1.6 (the day rider) and Part 2.5 (the mid-week
# musings) were SKIPPED by the serial runner's fair-share allocator at 22:34Z and 22:55Z and
# were rebuilt afterwards, at 07:52Z and 08:53Z on 08-29 — AFTER this card was first written at
# 02:25Z. So the rule that governs this file ("a play must trace to a verdict a section reached
# THIS week") was applied to a document that was two sections short, and both of those sections
# then landed carrying FAULT and FIX-ON-SATURDAY verdicts with money attached to them.
#
# The eight plays below close that gap. Every one of them is a row from Part 1.6 §7 or Part 2.5
# §4 that no play on the card already covered — checked against the whole card, not assumed.
# Nothing here comes from Part 1.5, which did NOT regenerate and therefore still contributes
# nothing; a stale section reached no verdicts this week and last week's card is not evidence.
#
# ⚠ They are APPENDED at the end of their windows (SATURDAY 5-8, BUILD 10-13) rather than
# ranked into the middle. Sections cross-reference the card by POSITION ("SATURDAY #2"), so an
# insertion that renumbers an existing play silently repoints 42 references in the document at
# the wrong row. Appending cannot.
# ══════════════════════════════════════════════════════════════════════════════════════════

play(
    id="rider-hard-flat-sits-on-the-blackout-edge-0828",
    window="SATURDAY", rank=5, tier="LIVE",
    topic="★★ The day rider's 20:40Z hard flat sits on the edge of a recurring gateway blackout with ZERO margin — it cost $1,258 on 21 August",
    play="Move the rider's first flatten attempt EARLIER (20:25Z or so, with the 20:40Z shot kept "
         "as the backstop), and put the page UPSTREAM of the flatten — it must fire when the "
         "venue read fails, not after the flatten it was supposed to protect has already been "
         "skipped.",
    mechanism="On Friday 21 August the rider was long 4 lots from 13:13Z. The IB gateway went "
              "unreachable at <strong>19:58:50Z</strong> and stayed unreachable until 23:44:50Z "
              "— 3h46m and 114 consecutive <code>SKIP venue read failed</code> polls — which "
              "straddles the 20:40Z flatten clock completely. The flatten never happened, the "
              "position rode the weekend, and it was closed by hand on Monday at 11:59Z. The "
              "blackout is not a freak: it also starts at 20:40:50Z on 17 Aug, 20:42:50Z on "
              "27 Aug and 20:06:50Z on 23 Aug. <strong>Two of those begin within three minutes "
              "of the flatten clock</strong> — 21 August is only the day that hurt because the "
              "outage arrived 42 minutes early.",
    rationale="This is a scheduling collision, not a strategy question, and it is the cheapest "
              "real money on the card. The flatten and the blackout are both recurring and both "
              "known; they are simply booked at the same minute. Moving one of them apart costs "
              "nothing and removes a class of weekend carry. ⚠ And note what the instruments did "
              "while it happened: the watchdog printed <code>ok position 4.0 managed</code> "
              "<strong>1,908 times</strong> across that open position, because its heartbeat was "
              "fresh. A strategy that is running and a strategy that can reach the venue are not "
              "the same thing, and nothing on this box currently distinguishes them.",
    number="Flatten at 20:40Z would have closed at 29,381.25 (−110.7pt, −$891.44). It actually "
           "closed Monday 11:59Z at 29,224.00 (−244.7pt, −$2,149.44). <strong>Cost of the failed "
           "flatten: −$1,258.00.</strong> The position was never once in profit (MFE −3.4pt) and "
           "its MAE was −375.2pt, or −$3,002 on 4 lots, reached while the market was open and "
           "nothing could see it.",
    section_ref="Part 1.6 §6(a) and §7 disposition (FAULT); Part 1.6 §1 for the two-book money.",
    verification="Run the flatten path against a simulated venue-unreachable window covering "
                 "20:40Z and confirm (i) the 20:25Z attempt closed the position and (ii) a page "
                 "arrived on the FIRST failed venue read, not at 23:45Z.",
    arms_when="Immediately — it is a clock change plus an alert, and it cannot open a position.",
    exit="n/a.",
    kill="If moving the first attempt to 20:25Z is shown to give up real money on the 20:25–20:40 "
         "window across the session history, keep 20:40Z as the only flatten and ship the "
         "upstream page alone — the page is the part that closes the silence, and the silence is "
         "what made this expensive.",
    suggested_mode="deploy",
    owner="Garrath — one timer change and one alert, no strategy code",
    revert="Restore the single 20:40Z attempt and the existing alert source.",
    money_gbp=0,
)

play(
    id="lake-extra-timeframe-files-inflate-bars-0828",
    window="SATURDAY", rank=6, tier="LIVE",
    topic="★★ The Parquet lake silently blends four extra timeframes into its bars view — 44.4% of July's minutes are inflated, and every backtest reads them",
    play="Add <code>timeframe='5s'</code> to the bars view in <code>lake.connect()</code>, or move "
         "the backfill files out of the stream directory. Then re-run anything that priced ATR, "
         "range or efficiency off lake bars and see which conclusions move.",
    mechanism="The bars view unions every Parquet file in the stream directory, and four backfill "
              "files written at other timeframes are sitting in it. A minute that exists at more "
              "than one timeframe is returned more than once, and the ranges compose — so ATR and "
              "efficiency read HIGH exactly where the duplication is densest. MNQ has the same "
              "four files, so this is not a gold-only fault.",
    rationale="This is the most dangerous thing on the card, because it is upstream of the "
              "evidence rather than in it. The lake is the DATA CONTRACT's designated source for "
              "every study longer than this week — the rolling 5-day capture.db cannot be used "
              "for history — so a bar-level inflation propagates into every multi-week backtest "
              "this desk has run since the backfill landed, including ones whose verdicts are "
              "already on this card. It fails silently and in the flattering direction: inflated "
              "range makes a volatility floor look cleared and an edge look bigger.",
    number="44.4% of July minutes inflated. The audit's own zero-control — which should return "
           "nothing — now reads <strong>9,469</strong> rows. Four files, both instruments.",
    section_ref="Part 2.5 §2 and §4 disposition (INSTRUMENT — FIX ON SATURDAY).",
    verification="Re-run the audit's zero-control and require it to return 0 rows, then confirm a "
                 "known July session returns exactly one row per minute.",
    arms_when="Immediately, and before any further backtesting — this is a read-path fix and "
              "touches no live code.",
    exit="n/a.",
    kill="Nothing to kill; if the extra timeframes turn out to be wanted, they belong in a "
         "SEPARATE view with the timeframe on it, never unioned into the default bars view.",
    suggested_mode="deploy",
    owner="Garrath — one filter in lake.connect(), or move four files",
    revert="Remove the filter. ⚠ But then no lake-derived number is trustworthy, so revert only "
           "together with the studies that depend on it.",
    money_gbp=0,
)

play(
    id="router-needs-a-weekend-calendar-0828",
    window="SATURDAY", rank=7, tier="LIVE",
    topic="Give the router a weekend and holiday check — it armed a gate 38.7 hours before any market opened, on zero bars",
    play="Add a market-calendar guard to the router tick: if the venue is closed, do not evaluate "
         "and do not write. Roughly fifteen lines.",
    mechanism="The router has no calendar at all. Across the CME halt it keeps ticking, and on a "
              "dead tape it evaluates against zero bars — which is not a neutral input, it is an "
              "absence the deciders read as a value. On 2026-08-29 at 07:20:25Z it armed "
              "<code>capitulation_long</code> on 0 bars, 38.7 hours before anything opened. The "
              "existing Asia block does not cover this: it expires on a clock boundary at 07:00Z "
              "and the tape stays shut for another day and a half.",
    rationale="This removes a whole class of decision made on zero information, which is worth "
              "more than the single change it would have prevented this week. A weekend arm is "
              "not merely idle — it survives into Sunday's reopen, so the desk can open the week "
              "in a state nobody chose on evidence that never existed.",
    number="1 change in 645 weekend ticks — so the RATE is low and the SIZE is not: the one "
           "change armed a live gate on 0 bars, 38.7h early. ~15 lines to close.",
    section_ref="Part 2.5 §4 disposition (FIX ON SATURDAY); Part 2.6 for the tick census that "
                "counts the weekend ticks.",
    verification="Run the router against a Saturday timestamp and confirm it declines to evaluate "
                 "and writes nothing to <code>gate_switches.env</code>.",
    arms_when="Immediately.",
    exit="n/a.",
    kill="If a genuine out-of-hours use is ever wanted, gate it on an explicit flag rather than on "
         "the absence of a calendar.",
    suggested_mode="deploy",
    owner="Garrath — ~15 lines in the router tick",
    revert="Remove the guard.",
    money_gbp=0,
)

play(
    id="both-nightly-scorecards-are-one-sided-0828",
    window="SATURDAY", rank=8, tier="LIVE",
    topic="Both nightly scorecards only count the modelled side — print realised P&L beside modelled, or stop publishing them",
    play="Make <code>router_nightly</code> add the realised P&amp;L of managed gates while the "
         "router was ON, and make <code>selector_nightly</code> print realised beside modelled "
         "(or stop scoring <code>adaptive_exit</code> at all while it is disabled). Pairs with "
         "SATURDAY #1 (timer-the-two-dead-nightlies-0828): that play makes them RUN, this one "
         "makes what they print mean something.",
    mechanism="<code>router_value</code> counts what the router's decisions cost and never what "
              "its arms earned, so on any day it armed something the number is a LOWER BOUND "
              "wearing the appearance of a total. <code>selector_nightly</code> has the mirror "
              "fault: it scores a feature that is switched off, and its 'regret' is the gap "
              "between a model and a model.",
    rationale="A one-sided scoreboard does not merely under-report, it points the wrong way — it "
              "makes the router look like a cost centre on exactly the days it did its job. This "
              "desk's standing rule is that a number without its counterfactual is not a "
              "measurement, and both of these publish a counterfactual with no realised leg.",
    number="08-28: <code>router_value</code> printed <strong>−$117</strong> on a day the router's "
           "own arms booked <strong>+$330</strong>. <code>selector_nightly</code>: −$347 modelled "
           "against +$330 booked on the SAME six legs, with $1,576 of 'regret' living entirely "
           "inside the model.",
    section_ref="Part 2.5 §4 disposition (two INSTRUMENT rows, both FIX ON SATURDAY); Part 2.6 "
                "recommendation #1 for the liveness half of the same problem.",
    verification="Re-run both nightlies for 08-28 and confirm each prints a realised figure beside "
                 "its modelled one, and that the router's day reads positive.",
    arms_when="Immediately — reporting only, no order path.",
    exit="n/a.",
    kill="If the realised leg proves impossible to attribute cleanly per gate, print the desk "
         "total beside the model rather than nothing — an approximate second side beats a "
         "confident single one.",
    suggested_mode="deploy",
    owner="Garrath — reporting change in two rollups",
    revert="Drop the realised column.",
    money_gbp=0,
)

play(
    id="rider-blind-outside-rth-0828",
    window="BUILD", rank=10, tier="PARKED",
    topic="★ The day rider does not MANAGE positions opened outside 13:30–21:00Z — it carries them",
    play="Move the rider's manage path out from behind the RTH-gated drift read, or give it a "
         "fallback ATR so the trail can arm outside the US session. Until then, treat any "
         "out-of-hours entry as hand-managed and say so on the desk view.",
    mechanism="<code>drift.read</code> is gated to 13:30–21:00Z and the manage path is downstream "
              "of it, so outside that window the rider falls back to <code>px = entry</code>: "
              "<code>ahead_pt</code> freezes at 0.0, <code>peak</code> stays pinned at the entry "
              "price, <code>arm_atr</code> is 0.0 so the trail can never arm, and the note "
              "degrades to <em>trail not armed (need +150 [fixed])</em> because there is no ATR "
              "to scale with. The heartbeat stays fresh throughout, so nothing looks wrong.",
    rationale="Two of this week's manual entries were opened outside the session and BOTH made "
              "money (+$377.50 and +$187.00) — which is precisely why it is worth flagging now "
              "rather than after one goes the other way. A position with no peak, no trail, no "
              "give-back and no exit except a hand is not a managed position; it is an unhedged "
              "carry that the instruments describe as managed.",
    number="Thursday 07:20 entry: 4 lots held 371 minutes with <code>ahead_pt</code> pinned at 0.0 "
           "for <strong>370 of them</strong>. Friday 12:39 entry: frozen for 50 of its 65 "
           "minutes. Both profitable — the fault is invisible in the P&amp;L.",
    section_ref="Part 1.6 §6(c) and §7 disposition; Part 1.6 §4 for which exit actually captured "
                "the week (the hand won).",
    verification="Open a paper position at 07:00Z and confirm <code>ahead_pt</code>, "
                 "<code>peak</code> and <code>arm_atr</code> all move before 13:30Z.",
    arms_when="Not this weekend — it touches the live manage path and wants its own test. Build "
              "it, shadow it, then arm.",
    exit="n/a.",
    kill="If an out-of-hours ATR proves too noisy to trail against, then say so explicitly in the "
         "desk view and keep the carry — the unacceptable state is the current one, where the "
         "position reads as managed and is not.",
    suggested_mode="observe",
    owner="Garrath — rider manage path",
    revert="Restore the RTH gate.",
    money_gbp=0,
)

play(
    id="shadow-rider-entry-dwell-confirm-0828",
    window="BUILD", rank=11, tier="SHADOW",
    topic="Shadow a dwell / 2-of-3-minute confirmation on the day rider's entry — the floor crossing is a coin flip at the sampling boundary",
    play="Build it as a SHADOW variant of the rider's entry: require the efficiency floor to hold "
         "for 2 of 3 consecutive minutes rather than firing on the first crossing. Score it "
         "against the live entry weekly. It costs nothing and cannot trade.",
    mechanism="The efficiency reading oscillates across its own 0.15 floor faster than the service "
              "samples it, so the entry time — and therefore the entry PRICE — is decided by when "
              "the sample happens to land rather than by the tape. This is the same "
              "threshold-noise mechanism Part 2.5 found at the router, measured here at the "
              "rider's own entry.",
    number="Wednesday crossed the 0.15 floor <strong>four times in six minutes</strong>. Tuesday's "
           "entry flips on a FIVE-SECOND boundary: 0.390/0.517 at :01 against 0.314/0.440 at :06. "
           "The sample is already 49 sessions, so the shadow has n from the first day.",
    rationale="A dwell requirement is the cheapest possible answer to threshold noise and it is "
              "testable for free. ⚠ Note the honest risk, which the section names: a confirmation "
              "delays every entry, and on this desk delay has repeatedly been the thing that "
              "killed a good rule. That is exactly why it goes to the shadow book and not to the "
              "live entry.",
    section_ref="Part 1.6 §7 disposition (SHADOW); Part 2.5 §2 for the same noise at the router's "
                "thresholds.",
    verification="After four weeks, compare shadow entries against live on the same sessions: "
                 "entry price, capture, and how many detections were LOST to the dwell.",
    arms_when="Never live on this evidence — shadow only, until it beats the live entry across "
              "60+ sessions AND the lost-detection count is known.",
    exit="Promote only if it wins on price without dropping winners; retire it if it drops more "
         "than it improves.",
    kill="If the dwell costs more detections than it saves points, it is dead — and that is the "
         "specific number to watch, not the net.",
    suggested_mode="shadow",
    owner="Garrath — one shadow variant",
    revert="Delete the variant. The live entry is untouched throughout.",
    money_gbp=0,
)

play(
    id="shadow-grind-regime-and-hour-bench-0828",
    window="BUILD", rank=12, tier="SHADOW",
    topic="Shadow benching grind_long in NORMAL_CHOP and CLEAN_TREND — together with the 13:00Z hour, never separately",
    play="Put both grind benches into the shadow book as ONE variant: stand grind_long down in "
         "NORMAL_CHOP and CLEAN_TREND, and stand it down for the 13:00Z US-open hour. Score it "
         "against live grind weekly.",
    mechanism="Grind's money is concentrated in regimes that are not the ones it fires most in, "
              "and the US-open hour is its worst cell on every measure at once — net, green days "
              "and win rate. Benching by regime is the one grind lever that survived this week's "
              "testing; the entry-confirmation and ER-floor levers did not.",
    number="Regime bench: <strong>+$2,310 against +$922</strong> live, strip-best-3 still +$249, "
           "leave-one-day-out +$1,430, and BOTH halves positive. The 13Z hour: <strong>−$1,618 "
           "over 50 fires on 25 days</strong>, green 8 of 25, 18% win.",
    rationale="This is the week's strongest surviving grind result and it still does not clear the "
              "bar for a live change. ★ The hour rule must ship ONLY alongside the regime rule "
              "and never alone, and the section is explicit about why: the 13Z hour was chosen "
              "AFTER seeing the table, so on its own it is a fitted cut wearing a result. The "
              "regime rule was not, and it carries the robustness.",
    section_ref="Part 2.5 §1 and §4 disposition (GRIND (d) and (e), both SHADOW).",
    verification="Weekly: shadow net against live grind net, plus the placebo on unseen days.",
    arms_when="Not live. Promote when the second half (+$238) reaches parity with the first AND "
              "the placebo drops below 5% on days the rule has never seen.",
    exit="Retire if the second half stays flat or the placebo stays above 5%.",
    kill="If the regime leg fails its placebo, the hour leg dies with it — it was corroboration, "
         "not an independent finding.",
    suggested_mode="shadow",
    owner="Garrath — one shadow variant, two conditions",
    revert="Delete the variant. Live grind_long is unchanged.",
    money_gbp=0,
)

play(
    id="shadow-gold-session-bounded-run-boarder-0828",
    window="BUILD", rank=13, tier="SHADOW",
    topic="Shadow the SESSION-BOUNDED gold run-boarder — the only MGC candidate that beat both its mirror and its random control",
    play="Shadow the session-bounded version of the gold run-boarder (board a run, wide stop, "
         "time cap), and spend the 12 untouched L2-only days on it as a genuine out-of-sample "
         "leg. Do not run the unbounded version.",
    mechanism="It boards a run already in progress rather than predicting its start — which is the "
              "one thing this desk's 22.6M-tick null did NOT refute — takes a wide stop so the "
              "run's own noise cannot remove it, and caps the hold so a dead run stops costing "
              "carry. The session bound is what keeps it inside the hours the behaviour exists in.",
    number="+$2,702 true against a mirror of <strong>−$5,438</strong> and a random control of "
           "<strong>−$3,010</strong> — it beats both, which most of this week's gold candidates "
           "did not. ⚠ The 3h session-bounded cell — the version actually being shadowed — is "
           "<strong>+$370</strong>, not $2,702. That is the honest number.",
    rationale="Gold is an empty seat (BUILD #9, mgc-empty-seat-0828) and this is the only "
              "candidate the week produced that has a mechanism, a control and a positive "
              "out-of-sample plan at the same time. It goes to shadow because the honest cell is "
              "+$370 on thin n, which is a glimmer, not an edge — and thin n is never a kill. "
              "★ Priced at $10.00/point: MGC is NOT the MNQ multiplier.",
    section_ref="Part 2.5 §3 and §4 disposition (GOLD — run-boarding, SHADOW); Movement 3's gold "
                "chapter for the bar-source caveat.",
    verification="Score the 12 L2-only days it has never seen. A sign that flips between the "
                 "depth-mid and trade bar sources is NOT a verdict — name the bar source with "
                 "every number.",
    arms_when="Never live on +$370 and this n. Shadow only.",
    exit="Promote if the 12 out-of-sample days hold the sign on the PRODUCTION bar source.",
    kill="If the out-of-sample leg goes negative, or the result only exists on depth-mid bars, it "
         "is PARKED again — not refuted, because the n is too thin to refute anything.",
    suggested_mode="shadow",
    owner="Garrath — one shadow variant on MGC",
    revert="Delete the variant. Nothing live trades gold.",
    money_gbp=0,
)



# ══════════════════════════════════════════════════════════════════════════════════════════
# ★★★ 2026-09-04 — THE THREE HUNTS THAT FINISHED TONIGHT.
#
# The durable runner skipped ten body sections as "already have" and ran three greenfield
# clusters to completion against a newly frozen census: gf_MGC, gf_RIDER_ALL and gf_UNCLASS
# (rc=0 at 21:39, 21:40 and 21:37Z). Their dossiers are carried IN FULL in the Movement 3
# ADDENDUM, so every row below has a home in this document and traces to a verdict a section
# actually reached — which is the only rule this file has.
#
# They are appended at the END of each window's ranking on purpose. Every id-anchored
# cross-reference already on the card resolves by (window, rank); inserting these anywhere
# else would silently repoint nine of them.
# ══════════════════════════════════════════════════════════════════════════════════════════

play(
    id="lake-gold-wrong-contract-0904",
    window="SATURDAY", rank=9, tier="LIVE",
    topic="The lake's gold year is 22% the WRONG CONTRACT — fix the front-month rule, and quarantine every gold study built on it",
    play="Change the gold backfill's contract selection from 'earliest expiry with a print' to a "
         "volume-led front-month roll, rebuild <code>backfill_1min.parquet</code>, and mark last "
         "Friday's thirteen-months-of-gold section as NOT SAFE until it is re-run on the fixed tape.",
    mechanism="<code>gazbot7.lake</code> builds gold's <code>bars</code> view by unioning "
              "<code>backfill_1min.parquet</code>, which keeps the earliest expiry that has a print "
              "at each instant. An expiring contract keeps printing for about five weeks after it "
              "stops being the front month, so the lake quietly serves the DYING contract for that "
              "whole stretch — at a price that is nowhere near where gold is actually trading.",
    rationale="This is not a rounding error and it is not confined to one study. On <strong>77 of "
              "266 sessions</strong> the lake quotes a contract whose median minute volume is "
              "<strong>zero lots</strong>, a median <strong>30.1 points — $301 a lot at gold's "
              "$10.00 multiplier</strong> — away from the real price. Any backtest that entered on "
              "those minutes was trading a tape on which nothing traded. It sits UNDER every gold "
              "conclusion this desk has reached in three weeks, including the 32-day bar-source "
              "re-run that BUILD #9 leans on and the router rule that a prior report killed.",
    number="77 of 266 sessions on the wrong expiry (22% of minutes). Median minute volume on those "
           "sessions: 0 lots. Median price error: 30.1 points = $301 a lot. MGC is $10.00/point.",
    section_ref="Movement 3 ADDENDUM → GOLD (gf_MGC.md, 2026-09-04) §1.1, which is the first thing "
                "in that dossier because it is the biggest thing in it.",
    verification="Re-derive the front month by volume for all 266 sessions and diff the two tapes "
                 "day by day. The fix is verified when the sessions that changed are exactly the "
                 "ones inside five weeks of an expiry, and no others.",
    arms_when="Nothing arms. This is a data-integrity fix, not a trading decision.",
    exit="n/a — the fix is the deliverable.",
    kill="If the volume-led roll and the current rule disagree on fewer than a handful of sessions, "
         "the finding is wrong and this row is withdrawn. The 77/266 count is the falsifiable part.",
    suggested_mode="fix",
    owner="Garrath — one selection rule in the lake's gold backfill",
    revert="Keep the old parquet beside the new one. Nothing live reads it; only research does.",
    money_gbp=0,
)

play(
    id="roll-the-stale-cutoff-0904",
    window="SATURDAY", rank=10, tier="LIVE",
    topic="Roll the durable runner's STALE cutoff with the cycle — it is why this report covers two different weeks",
    play="Derive the runner's stale cutoff from the run's own start time (the previous Friday "
         "22:00Z), not from a constant that has to be edited. The same constant lives in "
         "<code>scripts/friday_v7_build.py</code> as <code>CYCLE_START</code> and must be derived "
         "from <code>--slug</code> the same way.",
    mechanism="The 2026-09-04 run opened its log with <code>artifacts older than "
              "2026-08-28T22:00Z are STALE</code> — the PREVIOUS cycle's cutoff. Under that cutoff "
              "the fragments written on 08-29/30 look current, so the runner logged <code>HAVE "
              "&hellip; skipping (artifact is the checkpoint)</code> ten times and rebuilt none of "
              "them, while separately freezing a new census and running three greenfield clusters.",
    rationale="The failure mode is the nastiest kind this build has: <em>nothing errored</em>. Ten "
              "skips are the runner working exactly as designed, on a date that was one week out. "
              "The result is a document whose two halves describe different weeks and whose "
              "freshness checks all pass — which is precisely the silent-staleness failure the "
              "whole honesty apparatus was built to prevent, arriving through the one door nobody "
              "had a check on. The seam is now drawn on the front page, but drawing it is a "
              "mitigation, not the fix.",
    number="10 sections skipped as HAVE; 3 rebuilt; 2 censuses and 1 progress page a week younger "
           "than the 11 sections around them. One constant, in two files.",
    section_ref="The two-week provenance box at the top of this report (generated by "
                "<code>provenance()</code> in the build), and <code>data/friday_durable.log</code> "
                "at 2026-09-04T21:13:24Z, which is where the cutoff and the ten HAVE lines are "
                "printed side by side.",
    verification="Next Friday, grep the run's first log line for the cutoff and assert it equals "
                 "the previous Friday 22:00Z. If it does not, the fix did not land.",
    arms_when="Nothing arms.",
    exit="n/a.",
    kill="If the cutoff is already derived somewhere and the 08-28 value came from a config the "
         "operator set deliberately, this is a config row, not a bug row.",
    suggested_mode="fix",
    owner="Garrath — one derived date in the runner and in friday_v7_build.py",
    revert="Pin the constant again. It is a one-line change either way.",
    money_gbp=0,
)

play(
    id="lake-missing-sunday-partitions-0904",
    window="SATURDAY", rank=11, tier="LIVE",
    topic="The parquet lake is missing its Sunday partitions — the week's first session is absent from every lake-based study",
    play="Backfill the Sunday partitions and add a partition-completeness assertion to "
         "<code>gazbot7.lake.connect</code> so a missing day fails loudly instead of shortening "
         "the sample in silence.",
    mechanism="The UNCLASS hunt went looking for its own sessions and found the lake has no Sunday "
              "partitions, so the 22:00Z Sunday reopen — the start of every trading week — is "
              "simply not in the data any lake-based backtest reads.",
    rationale="A missing partition does not raise; it shortens n. Every study in this report that "
              "reads the lake has been silently excluding the week's opening session, and that is "
              "the session with the reopen gap in it. Nobody would have found this by looking at a "
              "result, because the result looks fine.",
    number="Sunday partitions absent across the lake's whole 2026-06-19 → 2026-09-04 range; the "
           "UNCLASS hunt's own 67 sessions / 914,146 bars are counted after the omission.",
    section_ref="Movement 3 ADDENDUM → UNCLASS (gf_full_UNCLASS.md, 2026-09-04), the engineering "
                "faults at the end of the dossier.",
    verification="Count distinct session dates in the lake against the CME calendar for the same "
                 "range. Every Sunday reopen should be present exactly once.",
    arms_when="Nothing arms.",
    exit="n/a.",
    kill="If the Sundays are deliberately excluded (thin tape, a capture decision), then this is "
         "documentation, not a backfill — but it still has to be asserted rather than assumed.",
    suggested_mode="fix",
    owner="Garrath — lake backfill + one assertion",
    revert="Nothing live reads the lake.",
    money_gbp=0,
)

play(
    id="drop-absorption-cut-from-rider-w5-0904",
    window="BUILD", rank=14, tier="SHADOW",
    topic="Remove ABSORPTION_CUT from rider_w5 — one cut has cost it −$3,520 across 42 of its 108 shadow trades",
    play="Run <code>rider_w5</code> in shadow with <code>ABSORPTION_CUT</code> disabled, alongside "
         "the current arm, and grade the pair on the same tape. This is the ONE concrete live "
         "experiment the UNCLASS hunt left behind, and it is cheap.",
    mechanism="<code>rider_w5</code> is in shadow now and losing. The UNCLASS dossier attributes "
              "the loss to a single exit cut: 42 of its 108 shadow trades are closed by "
              "<code>ABSORPTION_CUT</code>, and those 42 account for −$3,520 — more than the arm's "
              "whole deficit.",
    rationale="This is the difference between 'the hypothesis is dead' and 'one cut is killing it'. "
              "Both are consistent with the arm's headline record, and only a paired shadow can "
              "tell them apart. ★ Note it does NOT rescue the rider thesis: NOT-AN-ACTION #12 "
              "(rider-w5-fit-vs-forward-0904) stands either way, because a $45-a-trade fit-to-"
              "forward gap is not closed by an exit tweak.",
    number="108 live shadow trades, −$2,803 net, −$25.95/tr, 21% win. 42 of the 108 exit on "
           "ABSORPTION_CUT for −$3,520 — i.e. the other 66 are net POSITIVE.",
    section_ref="Movement 3 ADDENDUM → UNCLASS (gf_full_UNCLASS.md, 2026-09-04), the PARKED "
                "disposition and its one named live experiment; and → THE POOLED RUN-CATCHER "
                "(gf_full_RIDER_ALL.md) for the same arm's forward record.",
    verification="A paired shadow: same signals, same entries, one arm with the cut and one "
                 "without. Anything short of paired is a different-tape comparison.",
    arms_when="Shadow only. Nothing about this goes near a live slot.",
    exit="Grade at n≥60 on the cut-free arm.",
    kill="If the cut-free arm is also negative at n≥60, the cut was not the problem and rider_w5 "
         "is REFUTED rather than PARKED.",
    suggested_mode="shadow",
    owner="Garrath — one shadow variant",
    revert="Delete the variant.",
    money_gbp=0,
)

play(
    id="rider-s-home-shadow-0904",
    window="BUILD", rank=15, tier="SHADOW",
    topic="RIDER-S-HOME to shadow — the one leg that survived every placebo, and it is NOT a rider",
    play="Shadow it exactly as specified and do not widen it: short only, ATR14≥15, 13:00–21:00Z, "
         "stop 6×ATR, target 2×ATR, 60-minute cap. Book it as a short-side momentum scalp, not as "
         "a run-catcher.",
    mechanism="The pooled run-catcher died at the filter step, but one narrow leg came through the "
              "whole battery intact — including a random-entry placebo drawn from its OWN regime "
              "rather than from the whole tape, which is the harder version of that test.",
    rationale="It is worth a slot and it must be described honestly: it takes <strong>2.5% of the "
              "ceiling, not 60%</strong>. Calling it a rider is how a 2.5% scalp gets sized like a "
              "60% strategy. ⚠ The exit corner it lives in (WIDE stop, TIGHT target) is the "
              "OPPOSITE of the exhaustion_short shape the brief assumed, so nothing about it "
              "transfers to the existing gates.",
    number="n=58, +$2,980, +$51.38/tr, 79% win, bootstrap CI [+16.46, +82.60], beats a "
           "same-regime random-entry placebo at p=0.003. Median out-of-sample across all 81 "
           "configurations tried: −$4.26/tr — this is the one that is not that.",
    section_ref="Movement 3 ADDENDUM → THE POOLED RUN-CATCHER (gf_full_RIDER_ALL.md, 2026-09-04), "
                "STEP 3 and the closing verdict.",
    verification="Forward n≥40 in shadow at the stated parameters. n=58 in-sample with a p=0.003 "
                 "placebo is a reason to look, not a reason to trade.",
    arms_when="Shadow only.",
    exit="Stop 6×ATR, target 2×ATR, 60-minute cap — as specified, unchanged.",
    kill="Negative at n≥40 forward, or a positive result that only survives with the 13:00–21:00Z "
         "window tuned. The clock window is part of the hypothesis, not a knob.",
    suggested_mode="shadow",
    owner="Garrath — one shadow arm",
    revert="Delete the arm.",
    money_gbp=0,
)

play(
    id="book-is-the-untried-discriminator-0904",
    window="BUILD", rank=16, tier="PARKED",
    topic="The next run-catcher attempt needs the ORDER BOOK, not more days — and we already capture it",
    play="Regress the census's far-side depletion column, and the 41ms L2 in "
         "<code>capture.db.book</code>, against forward continuation at board time. Do that BEFORE "
         "building another entry rule.",
    mechanism="Two independent hunts reached the same wall from opposite directions. Detection is "
              "solved — a dumb momentum rule boards 71 of 73 sat-out runs a median 3.4 minutes in, "
              "with three-quarters of the move still ahead. SELECTION is what fails, and the bar "
              "features we select on (ATR, ER, range, clock) separate run-fires from chop-fires "
              "only weakly.",
    rationale="This is the row that says what to do INSTEAD of the eleven things this movement just "
              "killed. The oracle-filter bound is $18,955 a week — 180% of ceiling — so the money "
              "is demonstrably there and the failure is purely selection. The one discriminator "
              "nobody has ever regressed is the book, and it needs no data we do not already "
              "capture. ⚠ It is not free: the UNCLASS hunt reports a book/continuation correlation "
              "of −0.010 across 401 million depth rows, so the honest prior is that this fails too.",
    number="Boards 71/73 runs, median 3.4 min in. Pre-entry separation: ATR 12.7 (run) vs 8.7 "
           "(chop), ER-15 0.31 vs 0.22. Oracle-filter bound $18,955/wk. Book/continuation "
           "correlation so far: −0.010 on 401M depth rows.",
    section_ref="Movement 3 ADDENDUM → THE POOLED RUN-CATCHER (gf_full_RIDER_ALL.md, 2026-09-04), "
                "WHAT THE NEXT ATTEMPT NEEDS; and → UNCLASS for the −0.010.",
    verification="A pre-registered regression with the target and the horizon fixed BEFORE looking, "
                 "reported whatever it says. This is exactly the kind of study that finds an edge "
                 "if you let yourself choose the horizon afterwards.",
    arms_when="Nothing arms. This is a measurement.",
    exit="n/a.",
    kill="A pre-registered book regression that comes back at |r| < 0.1 kills the whole run-catcher "
         "programme, and that is a legitimate outcome worth paying for.",
    suggested_mode="measure",
    owner="Garrath — one study, no new capture",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="gold-exit-is-not-mnq-exit-0904",
    window="HOLD", rank=8, tier="LIVE",
    topic="If a gold gate is EVER promoted, it must not inherit the live slot config — gold's exit wants the opposite of MNQ's",
    play="Do nothing now, and write this down where the next gold promotion will hit it: gold gets "
         "ONE wide lot held to a clock, not the dual slot (Lot A tight scalp + Lot B chandelier).",
    mechanism="On every gold entry built this cycle, the desk's own dual-slot shape is negative and "
              "a single lot with a very wide stop held to a clock is the only exit family that "
              "pays. Same entries, same tape, only the exit changes.",
    rationale="This is a HOLD because there is nothing to promote — but it is the highest-value "
              "sentence in the gold work, because the default when a gold gate finally does earn a "
              "slot will be to give it the MNQ slot config, and that default is worth −$10,851 on "
              "the lead cell alone. ⚠ The magnitudes below come off the same year tape that "
              "SATURDAY #9 shows is 22% the wrong contract; the SIGN is the finding, and the sign "
              "is what this row asks you to remember.",
    number="Lead cell, same entries: dual slot −$1,649 vs single wide lot +$9,202.",
    section_ref="Movement 3 ADDENDUM → GOLD (gf_MGC.md, 2026-09-04), the exit-family work; and its "
                "own §1.1 for the contract-roll caveat on the magnitudes.",
    verification="Re-run the exit families on the volume-led front-month tape once SATURDAY #9 "
                 "lands. If the sign survives the contract fix, this becomes a rule.",
    arms_when="Never — it is an instruction about a future promotion, not a promotion.",
    exit="n/a.",
    kill="If the sign flips on the corrected tape, delete this row.",
    suggested_mode="note",
    owner="Nobody — this is a standing constraint",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="gold-four-cells-null-0904",
    window="NOT-AN-ACTION", rank=11, tier="REFUTED",
    topic="All four gold cells came back NULL — six candidates, every one beaten by shorting a lot at a fixed time of day",
    play="Do NOT build another gold entry off this cycle's candidate list. Momentum and reversion, "
         "long and short, are all covered and all fail.",
    mechanism="Six candidates were built fresh from gold's own distribution — not ported from MNQ — "
              "and all four cells were covered. Every one is beaten by a fixed-time-of-day short "
              "with the same exit, and five of the six lose money out of sample.",
    rationale="It is printed as a NOT-AN-ACTION so nobody re-proposes the same four cells in a "
              "fortnight. ★ The control is the finding: when a fixed clock constant beats every "
              "gate you built, the gate was measuring the clock. Two cells — momentum-long and "
              "reversion-long — have no surviving candidate AT ALL, which is the honest place to "
              "start next time, and only after SATURDAY #9's contract fix.",
    number="6 candidates, 4 cells, all beaten by a fixed-time constant; 5 of 6 negative out of "
           "sample. Live gold shadow book over 17 days: 225 trades, −$1,671, with the "
           "book-filtered LONG arm +$485 (n=19) and SHORT −$376 (n=20).",
    section_ref="Movement 3 ADDENDUM → GOLD (gf_MGC.md, 2026-09-04), the four-cell battery and the "
                "clock sweep.",
    verification="Score any future gold trigger against the fixed-time CONSTANT, not against a "
                 "random placebo. The constant is the harder control and it is the one that killed "
                 "these six.",
    arms_when="Nothing.",
    exit="n/a.",
    kill="A gold candidate that beats the fixed-time constant out of sample, on the corrected "
         "front-month tape, reopens this.",
    suggested_mode="none",
    owner="Nobody",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="rider-w5-fit-vs-forward-0904",
    window="NOT-AN-ACTION", rank=12, tier="REFUTED",
    topic="rider_w5 is the desk's cleanest fit-versus-forward case: +$19.29/tr promised, −$25.95/tr delivered",
    play="Do not promote anything on a backtest of this shape again, and do not re-tune rider_w5 "
         "to close the gap. Read the $45-a-trade swing as the size of the fitting error on this "
         "kind of study.",
    mechanism="<code>rider_w5</code> (the <code>board</code> gate) was promoted to shadow on a "
              "+$4,841 / +$19.29-per-trade backtest. It has been running live in shadow since "
              "08-17 and has delivered −$25.95 a trade over 108 trades at a 21% win rate. The "
              "independent re-derivation this cycle found the same thing without being told: "
              "across 81 configurations, the median out-of-sample result is −$4.26 a trade.",
    rationale="Two separate roads to the same number is what makes this worth a card row rather "
              "than a footnote. It is also the strongest available argument for the desk's "
              "out-of-sample protocol, because the protocol predicted this. ⚠ It does NOT settle "
              "whether the rider hypothesis is dead — BUILD #14 tests one specific exit cut that "
              "may be carrying the whole deficit — but it does settle that the +$19.29 was never "
              "real.",
    number="Backtest +$19.29/tr (n implied by +$4,841). Live shadow 108 trades, −$2,803, "
           "−$25.95/tr, 21% win. Swing: $45/trade. Independent OOS median across 81 configs: "
           "−$4.26/tr.",
    section_ref="Movement 3 ADDENDUM → THE POOLED RUN-CATCHER (gf_full_RIDER_ALL.md, 2026-09-04); "
                "and → UNCLASS for the same arm's exit breakdown.",
    verification="It is already verified forward — that is the point of the row. The check is that "
                 "shadow.db still shows the arm and its record.",
    arms_when="Nothing.",
    exit="n/a.",
    kill="n/a — a forward result is not killed by a better backtest.",
    suggested_mode="none",
    owner="Nobody",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="size-threshold-is-a-units-artefact-0904",
    window="NOT-AN-ACTION", rank=13, tier="REFUTED",
    topic="★ THE SIZE THRESHOLD THIS REPORT'S OWN MOVEMENT 3 FOUND IS A UNITS ARTEFACT — it dies in ATR units",
    play="Withdraw the size-threshold finding. Do not build a 'only take runs above N points' "
         "filter, and do not carry the threshold into next week's card.",
    mechanism="Sorted by how big a run turned out to be in POINTS, discrimination climbs "
              "beautifully and looks exactly like a footprint emerging — AUC reaches 0.81 on the "
              "≥200pt runs. Measured in ATR UNITS, which is the only unit a stop can be set in, "
              "every feature collapses to AUC ≈ 0.50 and ATR itself INVERTS to 0.42.",
    rationale="★ This refutes a headline conclusion of the section it sits inside: Movement 3's "
              "editorial half, written on 08-29, reports the size threshold as a finding. Sorting "
              "by points sorts by volatility, and volatility is the thing the feature was supposed "
              "to be discovering — the apparent threshold was the ruler, not the tape. It is "
              "printed loudly because a plausible, half-believed number is more dangerous than a "
              "wrong one, and this desk has been half-believing this one for two weeks.",
    number="AUC 0.81 at ≥200pt in POINTS; AUC ≈ 0.50 in ATR units, with ATR itself inverting to "
           "0.42. Board-time size predictor: best single feature r=0.074 on 4,830 boards; all "
           "fourteen features fitted and scored on the SAME data reach multiple R=0.149; fitted "
           "in-sample and scored out-of-sample, r=0.116. The revival condition asked for 0.40.",
    section_ref="Movement 3 ADDENDUM → UNCLASS (gf_full_UNCLASS.md, 2026-09-04) §3 and its closing "
                "verdict. It contradicts the Movement 3 editorial half above it, which was written "
                "on 2026-08-29 — later evidence on more data, so the addendum wins.",
    verification="Any future 'runs above size N are tradeable' claim must be stated in ATR units "
                 "before it is believed, and must beat the same AUC test in those units.",
    arms_when="Nothing.",
    exit="n/a.",
    kill="A discriminator that holds AUC ≥ 0.65 in ATR units on a held-out set reopens it.",
    suggested_mode="none",
    owner="Nobody",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="filter-signals-not-trades-0904",
    window="NOT-AN-ACTION", rank=14, tier="REFUTED",
    topic="A backtest that filters TRADES instead of SIGNALS manufactures edge out of replay sequencing",
    play="Never filter a trade list. Filter the SIGNAL list and re-run the replay. Any past result "
         "produced by filtering trades has to be re-run before it is quoted again.",
    mechanism="Removing trades from a finished replay changes which subsequent signals were "
              "reachable, because a signal that arrived while the book was occupied never became a "
              "trade. Filter the trades and you silently un-occupy the book, so the survivors are "
              "no longer the trades the rule would have taken.",
    rationale="This is a method wound with a body attached: the UNCLASS hunt nearly shipped a "
              "+$1.02-per-trade candidate that is really <strong>−$3.60</strong> once the filter is "
              "applied to signals and the replay re-run. It is the same family as this desk's "
              "standing finding that an exit sweep with position occupancy is really an entry "
              "sweep — and it is why the surviving legs in this report were re-run rather than "
              "re-filtered.",
    number="One candidate: +$1.02/tr filtered-on-trades vs −$3.60/tr filtered-on-signals. A 4.6× "
           "sign-flipping gap from the accounting alone.",
    section_ref="Movement 3 ADDENDUM → UNCLASS (gf_full_UNCLASS.md, 2026-09-04), the two "
                "engineering faults at the end.",
    verification="Re-run, never re-filter. The check is that the signal count changes when the "
                 "filter is applied — if only the trade count changed, it was done wrong.",
    arms_when="Nothing.",
    exit="n/a.",
    kill="n/a — this is an accounting identity, not an empirical claim.",
    suggested_mode="none",
    owner="Nobody",
    revert="n/a.",
    money_gbp=0,
)

play(
    id="unclass-is-not-a-cluster-0904",
    window="NOT-AN-ACTION", rank=15, tier="REFUTED",
    topic="UNCLASS is not a cluster — it is the base rate, and the census should print it as UNRESOLVED",
    play="Stop hunting UNCLASS as a cause-cluster. Change the census to print it as "
         "<code>UNRESOLVED</code> with its base rate beside it, and ship the four shapes it did "
         "produce as census vocabulary only.",
    mechanism="UNCLASS covers <strong>75.4% of all minutes</strong> against <strong>56.6% of the "
              "runs</strong> — a lift of <strong>0.75</strong>, i.e. runs are LESS likely to be "
              "UNCLASS than an arbitrary minute is. That has now been measured independently on "
              "two separate weeks.",
    rationale="A bucket with a lift below 1.0 is not a cause, it is the absence of a label, and "
              "hunting it is hunting the residual. Printing it as UNRESOLVED with its base rate is "
              "the fix, because the name is what made it look like a finding. Four shapes (TURN / "
              "DRIFT-VOID / GRIND-CONT / STEP-REPRICE) did replicate across two independent run "
              "sets and are worth keeping — as vocabulary for describing runs, not as gates.",
    number="Base rate 75.4% of minutes vs 56.6% of runs; lift 0.75, replicated on two weeks. Four "
           "replicating shapes, zero tradeable candidates.",
    section_ref="Movement 3 ADDENDUM → UNCLASS (gf_full_UNCLASS.md, 2026-09-04), closing verdict.",
    verification="Recompute the lift on a third independent week. A lift below 1.0 three times is "
                 "not a sampling accident.",
    arms_when="Nothing.",
    exit="n/a.",
    kill="A lift materially above 1.0 on a third week reopens it.",
    suggested_mode="none",
    owner="Garrath — one label in run_census.py",
    revert="Rename it back.",
    money_gbp=0,
)

# ── write it out ─────────────────────────────────────────────────────────────────────────
def main() -> int:
    seen = set()
    for p in P:
        assert p["id"] not in seen, f"duplicate id {p['id']}"
        seen.add(p["id"])
        for k in ("id", "window", "rank", "tier", "topic", "play", "mechanism", "rationale",
                  "number", "section_ref", "verification", "arms_when", "exit", "kill",
                  "suggested_mode", "owner", "revert"):
            assert p.get(k), f"{p['id']} missing {k}"
    for w in ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION"):
        ranks = sorted(p["rank"] for p in P if p["window"] == w)
        assert ranks == list(range(1, len(ranks) + 1)), f"{w} ranks are {ranks}"
    pathlib.Path(OUT).write_text(json.dumps(P, indent=1))
    from collections import Counter
    c = Counter(p["window"] for p in P)
    print(f"plays.json → {len(P)} plays: " + " · ".join(f"{k} {c[k]}" for k in
          ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
