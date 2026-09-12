#!/usr/bin/env python3
"""Rebuild reports/friday_v7/plays.json from THIS week's findings only (2026-08-17 .. 08-21).

★ The file on disk before this ran was the 2026-08-14 cycle's 46 plays. Carrying it forward
would put last week's recommendations on this week's front page — including several that this
week's sections refute — so it is overwritten wholesale rather than merged.

RULE APPLIED TO EVERY ROW: a play may only exist if a section of THIS report reached the verdict
behind it. `section_ref` names that section and the numbers in `number` are the ones that section
computed. Anything that felt like a good idea but has no section behind it is not on the card.

  python3 scripts/fv7_plays_0821.py
"""
from __future__ import annotations

import json
import pathlib

OUT = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"

P = []


def play(**kw):
    for req in ("id", "window", "rank", "topic", "tier", "play", "mechanism", "rationale",
                "section_ref", "verification", "suggested_mode", "arms_when", "exit", "kill",
                "number", "owner", "revert"):
        assert req in kw, f"{kw.get('id')} missing {req}"
    kw.setdefault("money_gbp", 0)
    P.append(kw)


# ══════════════════════════════════════════════════════════════════════════════ SATURDAY
play(
    id="flatten-the-weekend-carry-0821", window="SATURDAY", rank=1,
    topic="The four lots that are still open — confirm the gateway before Sunday 22:00Z",
    tier="LIVE",
    play="Before the Sunday 22:00 UTC reopen, check that the IB gateway is answering on "
         "127.0.0.1:4002 (restart it if it is not — nothing on this box can heal a wedge). "
         "<code>gazbot7-weekend-flatten.timer</code> is already installed and enabled and will "
         "fire at 22:00Z then retry every minute for two hours, self-disabling once flat. Your "
         "job is the precondition, not the flatten.",
    mechanism="The day rider opened 4 MNQU6 long at 29491.93 on Friday at 13:13:06Z. At about "
              "19:57Z the gateway entered the documented fourth-class partial wedge — it accepts "
              "nothing new while serving everything old — and all four independent closing paths "
              "share one <code>ib.connectAsync</code>: the rider's 20:40 hard flat, the "
              "flatten-only watchdog, the EOD flatten and desk_reconcile. All four failed. The "
              "EOD flatten's timer is Mon–Fri with Persistent=false, so a Friday failure gets no "
              "catch-up at all; its next elapse is Monday 20:53Z and the tape reopens Sunday "
              "22:00Z.",
    rationale="This is the only row on the card with a hard deadline and it is the largest single "
              "number in the report. Everything else can wait a week; a live-market window of "
              "about 23 hours with an unmanaged four-lot position in it cannot.",
    section_ref="Front page and Part 1 §0; the mechanism is Part 1.6 §5 and the nightly review of "
                "2026-08-21 22:43Z, which read the position live off updatePortfolio.",
    verification="After the reopen: <code>systemctl is-failed gazbot7-weekend-flatten</code> and "
                 "<code>day_rider_state.json</code> showing <code>venue_net: 0</code>. Check the "
                 "state file, not <code>core_health.flat</code> — that flag said the desk was "
                 "flat throughout.",
    suggested_mode="operate", arms_when="Once, at the Sunday 22:00Z reopen.",
    exit="Flat. The unit disables itself.",
    kill="n/a — this is a position, not an experiment.",
    number="4 lots long from 29491.93. Marked at the last tick before the close (29370.00) that "
           "is −121.93 points and <strong>−$975.44</strong>; IB's own updatePortfolio at "
           "21:00:32Z read unrealizedPNL −$950.27. Roughly $235k of notional.",
    owner="Garrath — gateway health check. The flatten itself is automated.",
    revert="n/a.",
)

play(
    id="rider-protective-stop-0821", window="SATURDAY", rank=2,
    topic="Put a protective stop on the day rider's own book",
    tier="LIVE",
    play="Add a 1.5×ATR protective stop, sized off the rider's entry ATR, to the day rider. It "
         "has none today at any width — below its peak-give-back arm threshold there is no stop, "
         "no trail and no alert.",
    mechanism="Thursday's loss was one long, four lots, held five hours fifty-five minutes with "
              "nothing in the water. Raced on the real tick tape from the rider's own entry, six "
              "stop widths from 0.5× to 3.0×ATR all beat what actually happened. The entry itself "
              "is the rider's ordinary open-hour entry and it made money on three other days this "
              "week, so this is not an entry change.",
    rationale="A losing rider is structurally silent: it pages on give-back from a peak and on "
              "stalls, so a position that is simply losing produces no output, and both tools you "
              "would naturally check print “flat, $0” because they count closed rows. The stop is "
              "what makes the silence safe.",
    section_ref="Part 1.5 §3 — the six-width stop race on Thursday's tape, with the entry ATR "
                "estimated at 36.1 points; and Part 1.6 §5.",
    verification="First week the rider takes a stop: check the fill is inside 1 ATR of the trigger "
                 "and that the day's loss is bounded by it. Also confirm the stop survives the "
                 "00:00Z session roll — see MONDAY #1.",
    suggested_mode="deploy", arms_when="Every rider entry.",
    exit="The stop is the exit being added.",
    kill="Two consecutive weeks where the stop costs more in cut winners than it saves in bounded "
         "losers, measured on the rider's own book.",
    number="Thursday cost −$1,294.50. The same position with a 0.5×ATR stop would have cost about "
           "−$150 and with 3.0×ATR about −$870 — every one of six widths better, the tightest by "
           "roughly $1,000 on one day.",
    owner="Garrath — day_rider config + restart",
    revert="Remove the stop key. It is additive; nothing else changes.",
)

play(
    id="standdown-as-a-file-0821", window="SATURDAY", rank=3,
    topic="Make the tournament standdown a FILE every writer checks",
    tier="LIVE",
    play="Move <code>TOURNAMENT_STOOD_DOWN</code> out of router_tick_durable.py and into a small "
         "state file that every writer to <code>gate_switches.env</code> reads before it writes. "
         "Six processes can write that file; two respect the lock.",
    mechanism="On Friday at 14:03Z, with the tournament stood down and all six gates reading off, "
              "<code>open_hour_watch.py</code> armed <code>abs_veto_short</code>. It has off→on "
              "authority and zero standdown awareness, and it did exactly what it was built to "
              "do. The router caught it on its very next tick and re-benched it at 14:05:18Z.",
    rationale="The gate was live for 2 minutes 15 seconds and fired nothing, so this cost $0 by "
              "luck rather than by design. The exposure is bounded by the router's five-minute "
              "poll, not by any guard — arm three minutes later and the gate is live through the "
              "whole US open window.",
    section_ref="Part 2.6 §4 — the three log lines, unedited.",
    verification="Set the standdown, then run open_hour_watch by hand against a confirmed break "
                 "and assert it declines to write.",
    suggested_mode="deploy", arms_when="Always.",
    exit="n/a.",
    kill="n/a — it is a guard, not a strategy. If it ever blocks a legitimate arm, that is the "
         "signal that the standdown itself was wrong, not the guard.",
    number="One incident this week, $0 by luck. Six writers to one file, two of which respect the "
           "lock, and all six share a single .tmp path.",
    owner="Garrath — code edit across the switch writers",
    revert="Delete the file check; the variable stays where it is.",
)

play(
    id="delete-expired-carveouts-0821", window="SATURDAY", rank=4,
    topic="Delete the five expired carve-out comments from gate_switches.env",
    tier="LIVE",
    play="Delete the expired instruction blocks from the top of <code>gate_switches.env</code>. "
         "<code>switch_notes()</code> splices the top 45 comment lines into every router prompt "
         "labelled ACTIVE and nothing prunes them.",
    mechanism="Five instructions are currently in that header: 2026-08-21 (fresh), 2026-08-19 "
              "(“PINNED until 21:55Z”, that deadline passed on Wednesday), 2026-08-13, 2026-08-11 "
              "(“expires 16:00Z”, eleven days ago) and 2026-08-09 — which states that "
              "<code>abs_veto_short</code> IS ARMED BY DEFAULT, directly contradicting the "
              "standdown the router is enforcing.",
    rationale="Only 172 of 1,425 ticks restated any of them this week and all 172 were the two "
              "recent ones, which looks like the problem has gone away. It has not, and no "
              "mention-rate streak can show that it has: 1,424 of the 1,425 reason fields are "
              "pinned at exactly the 1,200-character cap, so the mention rate is measuring spare "
              "room, not belief. Any quieter week and the thirteen-day-old “armed by default” "
              "line is one tick from being read as policy.",
    section_ref="Part 2.6 §5 — the header table with each line's age and its own mention count.",
    verification="Re-read the header after the edit and confirm only instructions with a live "
                 "expiry remain. Revoking a carve-out in the ledger does not revoke it in the file.",
    suggested_mode="operate", arms_when="n/a.",
    exit="n/a.",
    kill="n/a — housekeeping.",
    number="5 carve-outs spliced as ACTIVE; ages 0d, 2d, 8d, 11d and 13d. Obeying the 08-09 one "
           "would arm a gate the operator has stood down.",
    owner="Garrath — text edit, no restart",
    revert="Git restore the file's header.",
)

play(
    id="rider-venue-net-not-entered-0821", window="MONDAY", rank=1,
    topic="Branch the rider on <code>venue_net</code>, never on <code>entered</code>",
    tier="LIVE",
    play="One line in the day rider: gate the flatten path on <code>venue_net != 0</code> instead "
         "of on <code>entered</code>.",
    mechanism="At 00:00Z the session roll resets <code>day_rider_state.json</code> to "
              "<code>entered: false</code> with <code>note: \"switch off\"</code> while "
              "<code>venue_net</code> still reads the true position. On Friday morning the rider "
              "read its own reset state, concluded it was flat, and flattened a position it had "
              "opened sixty seconds earlier.",
    rationale="It stops being silent and starts asserting FLAT, which is worse. The 3-lot leg "
              "went out on-tape; the 1-lot remainder filled 26 points below a 30-minute low about "
              "92ms later and had to be flagged BADFILL.",
    section_ref="Part 1.5 §1 — both lots named, with the timestamps one timer tick apart.",
    verification="Watch the next 00:00Z roll with a position open and confirm no CLOCK_FLAT_BUG "
                 "row appears.",
    suggested_mode="deploy", arms_when="Always.",
    exit="n/a.",
    kill="n/a — it is a defect fix.",
    number="−$73.50 clean plus a −$83.00 BADFILL lot = −$156.50, in sixty seconds, on 2026-08-21.",
    owner="Garrath — one line in day_rider.py",
    revert="Restore the <code>entered</code> branch.",
)

play(
    id="hold-the-standdown-0821", window="MONDAY", rank=2,
    topic="Leave the four silent slots benched",
    tier="LIVE",
    play="No change. Keep <code>grind_long</code>, <code>capitulation_long</code>, "
         "<code>abs_veto_long</code> and <code>rgv_short</code> off, and note that "
         "reactivate_gates no longer re-arms them at 22:00Z, so this needs no action to hold.",
    mechanism="All six gates were fired mechanically in their exact live config across the whole "
              "of this week's captured tape — every fire counted, not only the ones near a big "
              "move. Fired into the 65 sat-out runs they lose −$1,333.85; stripped of every "
              "filter they lose more, not less; and joining a run after ignition is roughly free "
              "where predicting one is not.",
    rationale="The base-rate control is what makes this different from the last three idle-gate "
              "labs, which measured only windows already known to contain a run and reported "
              "survivorship as skill.",
    section_ref="Movement 2 §2–§4, with the base-rate control in §3.",
    verification="Re-run the base rate on the first genuine trend week. This is one quiet week and "
                 "the finding is scoped to it.",
    suggested_mode="hold", arms_when="Not until the base rate turns on a trend week.",
    exit="n/a.",
    kill="One trend week where the mechanical base rate for these four is positive.",
    number="All six mechanically: −$1,905.36 on 117 fires across the week's tape. The four silent "
           "slots alone: −$517.79 on 48 fires. Aligned fires — the ones pointing the same way the "
           "run then went — still lost $602.60 on 11.",
    owner="Nobody — this is the current state",
    revert="n/a.",
)

play(
    id="bench-the-absveto-short-slot-0821", window="MONDAY", rank=3,
    topic="Bench the automated half of <code>abs_veto_short</code>, keep the signal shadowed",
    tier="SHADOW",
    play="Leave the live slot off (it already is, since Friday 14:05Z). Keep the signal running in "
         "shadow through the 55-second confirm and the ladder arms, which is where its case now "
         "lives.",
    mechanism="Re-raced at five stop widths, twice over — once scaling the whole trade, once "
              "moving only the stop with the target pinned — <strong>all ten cells are "
              "negative</strong>. The sign survives, so this is a verdict rather than a "
              "knife-edge. The live book reads −$203 only because manual claims took +$412.93 out "
              "of it that the machine would not have taken; left to itself the machine reads "
              "−$548.73.",
    rationale="The root cause is not what it looks like. Zero of its 15 losing lots were chases — "
              "every one went at least 6 points onside, median +11.25 — so the entries work "
              "briefly and then stop working. That is exactly what a continuation-confirm "
              "addresses, which is why the case moves to shadow rather than to a bench-and-forget.",
    section_ref="Part 1.5 §2.1–§2.3, and Part 2 §3 for where the signal's case now sits.",
    verification="The 55s mirror needs a positive TRADABLE-HOURS week with a positive "
                 "leave-one-day-out before this comes back as a promotion question.",
    suggested_mode="hold", arms_when="Not this week.",
    exit="n/a.",
    kill="Two consecutive tradable-hours-positive shadow weeks would re-open it.",
    number="Live −$203.00 on 22 lots. Machine-only at the live stop width −$548.73. Ten sweep "
           "cells, all negative, worst leave-one-day-out negative at every width.",
    owner="Nobody — the slot is already off",
    revert="<code>abs_veto_short=on</code>. Reversible in five minutes.",
)

play(
    id="widen-nothing-this-week-0821", window="MONDAY", rank=4,
    topic="Do not re-tune any exit cell or router threshold on this week",
    tier="LIVE",
    play="No change to <code>exit_overrides.json</code> and no change to the router's thresholds "
         "or timing constants.",
    mechanism="The tournament traded two slots and 22 lots. The A/B leg comparison has 16 paired "
              "signals and the sign flips on one pair (B−A −$76.50, −$96.00 with the best pair "
              "stripped). The router wrote 20 switches all week, 5 of them worth $0 by "
              "construction because they were in the Asia block.",
    rationale="Four separate sections reach the same conclusion independently. Tuning on a week "
              "the desk was stood down is fitting to the standdown.",
    section_ref="Part 1 §3 (the A/B legs), Part 2.6 §8 (the router verdict).",
    verification="n/a — the action is inaction.",
    suggested_mode="hold", arms_when="n/a.", exit="n/a.",
    kill="A week with ≥40 paired signals would re-open the exit-ladder question.",
    number="16 paired A/B signals, B−A −$76.50, strip-best-1 −$96.00. 20 router switches, 5 of "
           "them $0 by construction.",
    owner="Nobody — no change",
    revert="n/a.",
)

# ══════════════════════════════════════════════════════════════════════════════════ BUILD
play(
    id="dedupe-shadow-arms-0821", window="BUILD", rank=1,
    topic="Row-level duplicate check on the shadow board, and re-seed three broken arms",
    tier="LIVE",
    play="Add a duplicate check at shadow-write time that compares an arm's rows against every "
         "other arm's, and re-seed the three A/B pairs that are currently writing one "
         "configuration's trades under two names.",
    mechanism="Seven of the 38 families with n≥8 this week are byte-identical to another family "
              "on every field including qty, target_r, stop multiple and real_pnl: "
              "<code>capit_flip_live == capit_flip_t90</code>, "
              "<code>cx_clip_brk_live == cx_clip_brk_standdown == cx_grindA_clip</code>, and "
              "<code>odr_c5_s30 == odr_c5_s30_g</code>.",
    rationale="Every one of those pairs exists to measure a difference and every one reports a "
              "perfect null — not because the configurations agree but because only one is "
              "running. A broken arm and a genuinely neutral change look identical in the board's "
              "summary view, and the summary view is what a report reads. Note especially the "
              "clip-vs-standdown pair, which exists specifically to test whether standing an exit "
              "down changes anything.",
    section_ref="Part 2 §5 — the four groups, with the hash comparison that found them.",
    verification="The check should fail the three known pairs today. After re-seeding, they should "
                 "diverge within a week.",
    suggested_mode="build", arms_when="n/a.", exit="n/a.",
    kill="n/a — it is an instrument fix.",
    number="7 of 38 arms duplicated; 3 A/B experiments invalidated. Until this lands, every "
           "shadow A/B delta on the board is unverified.",
    owner="Claude — shadow writer + a one-off re-seed",
    revert="Remove the check. The re-seed is not revertible and does not need to be.",
)

play(
    id="grind-atr-floor-ladder-0821", window="BUILD", rank=2,
    topic="Shadow a ladder on grind's 22-point ATR floor — the number nobody has ever swept",
    tier="SHADOW",
    play="Seed shadow arms for <code>grind_long</code> at ATR floors of 14, 16, 18 and 22 and let "
         "them accumulate n. Nothing goes live.",
    mechanism="The 22-point floor blocked 24,110 of 24,121 raw grind signals on this week's tape. "
              "Recomputed off capture.db's own 5s bars, only 11.0% of one-minute ATR readings "
              "clear 22 and the p90 is 22.64 — the floor sits at the ninetieth percentile. The "
              "p25 lab, on a longer window via the lake, gets 25.3%; both windows are printed "
              "because they disagree.",
    rationale="This is the finding the whole grind programme turns on. The trend-day arming rule "
              "makes +$580.50 and is un-runnable because only 1 of 240 sessions is both "
              "clean-trend and above the floor; the two grind-exit shadow watches have had no new "
              "trade since 5 August; the gate has fired nothing live in a fortnight. A filter at "
              "p90 is not a filter, it is an off-switch that opens during violence — and 22 is a "
              "number the gate was born with, never tested.",
    section_ref="Part 2.5 §1–§2, Part 1.5 §4, Movement 2 §3.",
    verification="Report each rung's fires, real_pnl and winner retention at n≥40. Do not promote "
                 "a rung on fire count alone.",
    suggested_mode="shadow", arms_when="Shadow only.",
    exit="Same exits as the live grind slot, so the floor is the only variable.",
    kill="If no rung produces a positive real_pnl at n≥40, the floor is not the problem and grind "
         "goes back to being an entry question.",
    number="24,110 of 24,121 signals blocked this week. 11.0% of 37,412 one-minute ATR readings "
           "over 33 sessions clear 22 points; median 11.69, p90 22.64.",
    owner="Claude — shadow slate only",
    revert="Remove the arms.",
)

play(
    id="core-health-reads-the-venue-0821", window="BUILD", rank=3,
    topic="Point <code>core_health.flat</code> at the venue position, or rename it",
    tier="LIVE",
    play="Make <code>core_health.json</code>'s <code>flat</code> field reflect the venue position "
         "across both books, or rename it <code>tournament_flat</code> so nothing downstream can "
         "read it as a desk-wide safety signal.",
    mechanism="It is tournament-scoped today. The router reads it and 137 of the 141 ticks since "
              "the rider's Friday entry contain the word “flat” while the venue was long four "
              "lots. The last of those ticks describes the rider as “clientId 4, a desk I neither "
              "route nor bench”.",
    rationale="The trades table only enumerates what CLOSED, so it can never contradict a benign "
              "story. The venue position line can. Citing closed rows and declining "
              "responsibility for an open one is an attribution that terminates in the wrong "
              "place — “not mine to close” obliges escalation, not dismissal.",
    section_ref="Part 2.6 §6, Part 1 §7.",
    verification="Open a position on either book and assert the flag goes false.",
    suggested_mode="build", arms_when="n/a.", exit="n/a.",
    kill="n/a — instrument fix.",
    number="137 of the last 141 router ticks said flat against a 4-lot venue position worth about "
           "$235k of notional.",
    owner="Claude — core_health writer",
    revert="Restore the tournament-scoped field.",
)

play(
    id="timers-on-the-nightly-rollups-0821", window="BUILD", rank=4,
    topic="Put timers on router_nightly and selector_nightly, and fix selector's two defects",
    tier="LIVE",
    play="Add systemd timers for both nightly rollups, and before believing selector_nightly "
         "again, give it a <code>data_quality</code> filter and make it reprice at each gate's "
         "actual stop multiple instead of a hard-coded 1.0.",
    mechanism="The newest router rollup is 2026-08-14 and the newest selector rollup 2026-08-18. "
              "Neither has a timer, so both simply stopped. The whole weekly router review had to "
              "be rebuilt from raw logs this week.",
    rationale="A monitoring file that stops being written is worse than one that errors, because "
              "its absence looks like a quiet week. And the selector rollup is wrong even when it "
              "runs: quarantined rows inflate its regret, and two of the live gates do not use a "
              "1.0 stop multiple.",
    section_ref="Part 2.6 §7, and Part 1 §7 for the instrument list.",
    verification="Both directories should gain a dated file every night for a week.",
    suggested_mode="build", arms_when="n/a.", exit="n/a.",
    kill="n/a.",
    number="Router rollup 8 days stale, selector rollup 4 days stale, at this report.",
    owner="Claude — two timer units plus the selector fixes",
    revert="Disable the timers.",
)

play(
    id="report-gold-long-short-mix-0821", window="BUILD", rank=5,
    topic="Report the long/short mix on every gold result",
    tier="LIVE",
    play="Add a long/short split and a directional-control column to every MGC study, "
         "retrospectively for the ones in this report.",
    mechanism="On the same out-of-sample window the gold rider is scored against, holding gold "
              "LONG every session loses $21,738 and holding it SHORT every session makes $20,382 "
              "over 226 sessions. Any gold arm with even a slight short bias will read as "
              "profitable without carrying any edge.",
    rationale="Two arms in this report were already reading that drift as edge before the control "
              "was run: the derived-trigger gold rider (+$655 out-of-sample) and the stay-out "
              "meter's direction call, whose UP/DOWN hit-rate gap turns out to be the same drift.",
    section_ref="Part 2.5 §4d and §5.",
    verification="Every gold table in next week's report carries the split. Any arm whose edge "
                 "vanishes against the control is re-dispositioned.",
    suggested_mode="build", arms_when="n/a.", exit="n/a.",
    kill="n/a — method fix.",
    number="$21,738 long / +$20,382 short over 226 out-of-sample sessions. MGC is $10.00 a point.",
    owner="Claude — every MGC harness",
    revert="n/a — it is an added column.",
)

play(
    id="shadow-post-ignition-entry-0821", window="BUILD", rank=6,
    topic="Shadow an ignition-CONFIRMED entry, since joining a run is nearly free",
    tier="SHADOW",
    play="Seed a shadow arm that fires the existing six gates only AFTER a run has ignited, and "
         "let it accumulate n against the pre-ignition arm.",
    mechanism="Movement 2's four arms: fired in the 10 minutes before ignition with live filters "
              "on, the gates lose −$1,333.85 on 23 fires; fired in the 5 minutes AFTER ignition "
              "with the same filters, they lose −$45.00 on 17. That is the only asymmetry in the "
              "whole lab and it points the same way as the greenfield lab's timing-decay ladder.",
    rationale="Predicting a run costs money; joining one is roughly free. Free is not profitable, "
              "so this is an incubation, not a proposal — but it is the one place in the idle-gate "
              "work where the sign is not clearly against us.",
    section_ref="Movement 2 §2 — the four-arm table.",
    verification="n≥60 fires before it is discussed again, and it must beat the post-ignition "
                 "arm's own base rate, not just the pre-ignition one.",
    suggested_mode="shadow", arms_when="Shadow only.", exit="Live scaleout exits.",
    kill="If it is still not positive at n=60 it joins the refuted pile with the rest of the "
         "idle-gate programme.",
    number="Pre-ignition −$1,333.85 on 23 fires; post-ignition −$45.00 on 17.",
    owner="Claude — shadow slate only",
    revert="Remove the arm.",
)

play(
    id="ladder-arms-need-n-0821", window="BUILD", rank=7,
    topic="Let the abs-veto ladder arms run to n≥60 before anyone promotes them",
    tier="SHADOW",
    play="No change — keep <code>lad_absS_B_15</code>, <code>lad_absS_A_10</code>, "
         "<code>sw_absS_A_k10</code> and <code>sw_absS_B_k10</code> running, and do not promote "
         "any of them on this week.",
    mechanism="On the tradable-hours board these are the four most robust things this week: "
              "+$244.00, +$203.50, +$183.00 and +$186.00, four of five days green on the ladder "
              "pair, and leave-one-day-out positive on all four. But the ladder arms have n=20 in "
              "their first week and no all-time record at all.",
    rationale="They also cross-confirm Part 1.5 from a different direction: the k=1.0 stop-width "
              "arms beat the k=2.0 ones (+$183.00 / +$186.00 against +$61.50 / +$103.50), which "
              "is the same “tighter is better” ordering the live gate's own stop sweep produced.",
    section_ref="Part 2 §3 — the promotion battery, tradable hours only.",
    verification="n≥60 tradable-hour fires with a positive leave-one-day-out.",
    suggested_mode="shadow", arms_when="Shadow only.", exit="As configured per arm.",
    kill="Leave-one-day-out negative for two consecutive weeks.",
    number="+$244.00 / +$203.50 / +$186.00 / +$183.00 tradable-hours this week. Best-3-stripped "
           "is negative on all four, which is what n=20 looks like.",
    owner="Claude — shadow slate only",
    revert="n/a — no change.",
)

# ═══════════════════════════════════════════════════════════════════════════════════ HOLD
play(
    id="hold-weekend-flatten-unit-0821", window="HOLD", rank=1,
    topic="The weekend-flatten unit is installed — do not disable it",
    tier="LIVE",
    play="Nothing. <code>gazbot7-weekend-flatten.timer</code> is installed and enabled, fires at "
         "Sunday 22:00Z and retries every minute for two hours, and self-disables once flat.",
    mechanism="It exists because the EOD flatten's timer is Mon–Fri with Persistent=false, so a "
              "Friday failure gets no catch-up: next elapse Monday 20:53Z against a Sunday 22:00Z "
              "reopen. The retry loop is there because the failure being fixed was a gateway that "
              "would not answer, and a single shot at 22:00 would reproduce the original bug.",
    rationale="Note what it does NOT fix: if the gateway is still wedged at the reopen the loop "
              "fails sixty times exactly as designed. It is a retry, not a heal. That is why "
              "SATURDAY #1 is a human check.",
    section_ref="Front page; the failure it addresses is in Part 1.6 §5.",
    verification="<code>systemctl list-timers gazbot7-weekend-flatten</code> shows Sun 22:00Z.",
    suggested_mode="hold", arms_when="Sundays, until it is no longer needed.", exit="n/a.",
    kill="n/a.",
    number="Both of Friday's EOD attempts (20:53Z and 20:57Z) died on the same gateway "
           "TimeoutError, four minutes apart. Four minutes buys nothing; two hours of retries "
           "across the reopen might.",
    owner="Nobody — already in production",
    revert="<strong>Do not.</strong>",
)

play(
    id="hold-asia-void-rule-0821", window="HOLD", rank=2,
    topic="Keep voiding the Asia block on every shadow number",
    tier="LIVE",
    play="Nothing to build — apply the rule. Any shadow figure quoted without the 00:00–07:00Z "
         "entries removed is wrong, in either direction.",
    mechanism="The permanent Asia bench sits downstream of where a shadow arm records its fire, "
              "and the desk has filled nothing in that window since 5 August. Across the 38 "
              "families with n≥8 this week, −$3,631.00 of the board was booked there.",
    rationale="It reorders the board rather than shifting it: the family second on the raw board "
              "falls to eleventh, and one promotion candidate crosses from positive to negative.",
    section_ref="Part 2 §1–§2.",
    verification="Every shadow table in this report already carries both columns.",
    suggested_mode="hold", arms_when="n/a.", exit="n/a.", kill="n/a.",
    number="−$3,631.00 of −$13,780.50 booked in untradeable hours; abs_veto_55s +$332 → +$23.50.",
    owner="Nobody — a standing rule",
    revert="n/a.",
)

play(
    id="hold-manual-claim-0821", window="HOLD", rank=3,
    topic="Keep claiming by hand — and do not try to automate it",
    tier="LIVE",
    play="No change. The Claim button stays as it is, and the peak/give-back detector does not go "
         "live in any form.",
    mechanism="Your 16 claims made +$550.00 this week against +$412.93 on abs_veto_short alone "
              "that the machine would not have taken, at a median capture of 80% of each trade's "
              "own in-life peak. The detector calibrated against those same trades makes +$1,069 "
              "in-sample on 341 trades and −$4 out-of-sample on 126; applied exactly as it stands "
              "live it fires on 10 of 467 trades for −$436.",
    rationale="Scoring a claim rule against the trades you chose to be present for was always "
              "going to lose, because your presence IS the filter. The money an automated claim "
              "could win is in the 671 exits nobody watched, and in that population the STOP "
              "bucket is −$18,672 over 378 trades — which is an entry-side question, not an "
              "exit-side one.",
    section_ref="Part 1 §6 and the claim-replay study; the OOS table is in "
                "reports/claim_replay/REPORT_UNWATCHED.md.",
    verification="n/a — the action is inaction.",
    suggested_mode="hold", arms_when="n/a.", exit="n/a.",
    kill="An entry-side 'is this trade stop-bound?' study coming back positive would re-open it "
         "as a different question.",
    number="+$550.00 on 16 claims, 80% median peak capture. Detector: +$1,069 in-sample, −$4 out.",
    owner="Nobody — no change",
    revert="n/a.",
)

# ═════════════════════════════════════════════════════════════════════════ NOT-AN-ACTION
play(
    id="not-promote-absveto55s-0821", window="NOT-AN-ACTION", rank=1,
    topic="Promote <code>abs_veto_55s</code> to a live two-sided slot",
    tier="REFUTED",
    play="Do not. It was the obvious read off the raw board and it does not survive the ruler.",
    mechanism="$308.50 of its $332.00 was booked between 00:00 and 07:00Z, a window with zero "
              "live fills since 5 August. Tradable hours: +$23.50 on 34 fires, 35% win, 2 of 5 "
              "days green, and −$133.50 once the single best fire is stripped. Its 50-second "
              "sibling goes negative.",
    rationale="The family is NOT dead — all-time tradable-hours it is +$3,078.00 on 263 fires, "
              "which is the best-evidenced thing on the board and the reason it is still "
              "incubating. The refuted claim is specifically “promote it on this week's numbers”.",
    section_ref="Part 2 §2–§3.",
    verification="n/a.", suggested_mode="hold", arms_when="n/a.", exit="n/a.",
    kill="A positive tradable-hours week with a positive leave-one-day-out re-opens it.",
    number="+$332 raw → +$23.50 tradable. All-time tradable +$3,078.00 on 263.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-arm-grind-on-trend-days-0821", window="NOT-AN-ACTION", rank=2,
    topic="Arm grind only on clean-trend days",
    tier="PARKED",
    play="Do not deploy it — but do not throw it away either. It is parked behind the floor "
         "question in BUILD #2.",
    mechanism="On 128 live grind fires the rule turns −$958 into +$580.50 and keeps 25 of 43 "
              "winners, so it is not a fake win. Strip its best three fires and it is −$202; "
              "worst leave-one-out −$123. And of 240 classified sessions, exactly ONE is both "
              "clean-trend and above the 22-point ATR floor.",
    rationale="Arming was never the binding constraint. In production this rule would have armed "
              "the gate on about one day in 240, and on the other 239 the floor would have "
              "refused every signal regardless.",
    section_ref="Part 2.5 §1 — the mechanism table and the day-type conjunction.",
    verification="Revive it the moment the floor ladder returns a workable rung.",
    suggested_mode="hold", arms_when="n/a.", exit="n/a.",
    kill="If no floor rung works, this dies with the floor.",
    number="+$580.50 vs a −$958.00 control; strip-3 −$202.00; 1 of 240 sessions satisfies both "
           "conditions.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-er-floor-for-grind-0821", window="NOT-AN-ACTION", rank=3,
    topic="Fix grind with an efficiency-ratio floor or a directional-net requirement",
    tier="REFUTED",
    play="Do not. This is the third time it has been refuted and it keeps coming back.",
    mechanism="Nine cells across two families, scored on the same 128 live grind fires: every one "
              "negative. The ER-0.35 floor that is already deployed keeps 35 fires and still "
              "loses $417.50.",
    rationale="Kept on the card with its autopsy so next Friday's agent does not re-derive it.",
    section_ref="Part 2.5 §1, the b- and c-family rows.",
    verification="n/a.", suggested_mode="hold", arms_when="n/a.", exit="n/a.", kill="n/a.",
    number="9 of 9 cells negative. The live ER-0.35 floor: 35 fires, −$417.50.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-wall-of-stops-0821", window="NOT-AN-ACTION", rank=4,
    topic="Stand a gate down after two consecutive stops",
    tier="REFUTED",
    play="Do not. Fourth independent population to refuse it.",
    mechanism="Applied to <code>abs_veto_short</code>'s 22 lots this week it cuts winners along "
              "with losers and fails the 80%-winner-retention rule. Previously refuted "
              "mechanically on 104 signals, live across last week's tape, and on the same "
              "principle in the run-state work.",
    rationale="The discriminator is the REGIME the losses happened in, not the count of them.",
    section_ref="Part 1.5 §2.3 — the filter table with the winners-kept column.",
    verification="n/a.", suggested_mode="hold", arms_when="n/a.", exit="n/a.", kill="n/a.",
    number="No variant keeps 80% of the winners while beating the as-traded total.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-tighten-absveto-stop-0821", window="NOT-AN-ACTION", rank=5,
    topic="Tighten <code>abs_veto_short</code>'s stop to 0.5× or 0.75×ATR",
    tier="REFUTED",
    play="Do not — even though the sweep's ordering makes it look attractive.",
    mechanism="Both tight cells are less bad than the live width but still negative: −$124.83 and "
              "−$57.94 on the shape sweep, −$386.89 and −$498.24 with the target pinned. Ten "
              "cells across two sweeps, all ten negative.",
    rationale="'Less negative' is not a reason to deploy. The instruction the two sweeps support "
              "is to stop running the automated slot, not to re-size its stop.",
    section_ref="Part 1.5 §2.2 and §2.2b.",
    verification="n/a.", suggested_mode="hold", arms_when="n/a.", exit="n/a.", kill="n/a.",
    number="10 sweep cells, all negative, at both target treatments.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-2r-partial-as-variance-0821", window="NOT-AN-ACTION", rank=6,
    topic="Describe the 2R-partial as a variance / smoothness lever",
    tier="REFUTED",
    play="Stop calling it that. On its own current window it does the opposite.",
    mechanism="Baseline −$1,382.40 against partial −$1,074.90, so it improves the mean by "
              "$307.50 — while daily standard deviation goes from 42.3 to 83.3 and green-day "
              "percentage is 0% for both.",
    rationale="It was adopted as a variance lever on a backtest that showed daily vol −29%. On "
              "the live shadow window it is a mean lever that increases variance, which is a "
              "different product. Also note the watch has had no new trade since 5 August, "
              "because grind has not fired.",
    section_ref="Part 2 §6.",
    verification="Re-measure on the first week grind actually trades.",
    suggested_mode="hold", arms_when="n/a.", exit="n/a.",
    kill="A fresh window where std falls would revive the variance claim.",
    number="std 42.3 → 83.3; mean +$307.50; newest trade in the watch 2026-08-05.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-open-rider-window-filter-0821", window="NOT-AN-ACTION", rank=7,
    topic="The open-rider 'inside the window' session filter",
    tier="REFUTED",
    play="Do not deploy it. Three sessions are the entire lead.",
    mechanism="Across 229 replayed sessions at two lots the open rider loses $20,739. Split by "
              "the window, 'inside' makes +$825 on 60 sessions and 'outside' loses $21,564 on "
              "165 — but strip the best three inside sessions and it is −$7,745.",
    rationale="Kept on the card because the split looks compelling in isolation and will be "
              "re-proposed otherwise.",
    section_ref="Part 2.5 §5.",
    verification="n/a.", suggested_mode="hold", arms_when="n/a.", exit="n/a.", kill="n/a.",
    number="+$825 on 60 sessions → −$7,745 with the best three stripped.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-stayout-as-direction-0821", window="NOT-AN-ACTION", rank=8,
    topic="Read the stay-out meter as a DIRECTION signal",
    tier="REFUTED",
    play="Do not. It stays in service as a stay-out instrument, which is what it was built to be.",
    mechanism="When both of its reads agree it is right 51.7% of the time over 178 sessions. Its "
              "UP calls hit 56.7% and its DOWN calls 45.7%, and that gap is the same large short "
              "drift the gold control exposed, not skill.",
    rationale="The label on the instrument already says this. It keeps getting forgotten because "
              "the up/down asymmetry looks like signal.",
    section_ref="Part 2.5 §5.",
    verification="n/a.", suggested_mode="hold", arms_when="n/a.", exit="n/a.", kill="n/a.",
    number="51.7% over 178 agreeing sessions — a coin.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-mgc-coil-0821", window="NOT-AN-ACTION", rank=9,
    topic="Trade the MGC coil edge, in either direction",
    tier="REFUTED",
    play="Do not. Both directions lose and the placebo closes it.",
    mechanism="Fading the coil edge loses $1,828.93 over 2,487 trades across 251 sessions; the "
              "mirror control — breaking out of it — loses $4,767.86 on the same trades. Zero of "
              "the placebo sets did worse, against a placebo median of −$3,354.96.",
    rationale="The tightest-compression cell is separately PARKED (+$616.32 on n=666) with a "
              "named revival condition: run the same placebo, hold out a year. That is a "
              "different claim from this one.",
    section_ref="Part 2.5 §4a–§4b. MGC priced at $10.00/point.",
    verification="n/a.", suggested_mode="hold", arms_when="n/a.", exit="n/a.", kill="n/a.",
    number="−$1,828.93 / −$4,767.86 on 2,487 trades; 0 placebo sets beaten.",
    owner="Nobody", revert="n/a.",
)

play(
    id="not-idle-gate-arming-0821", window="NOT-AN-ACTION", rank=10,
    topic="Arm the idle gates to catch the runs we sat out",
    tier="REFUTED",
    play="Do not. This is the fourth idle-gate lab and the first one with an honest denominator.",
    mechanism="65 sat-out runs, four arms, plus a whole-week base-rate control. Live config into "
              "the pre-ignition window: −$1,333.85 on 23 fires. Ungated: −$1,620.40 on 60. Whole "
              "week, all six gates, every fire counted: −$1,905.36 on 117. Even the fires that "
              "pointed the right way lost $602.60 on 11.",
    rationale="Previous idle-gate labs reported a small positive and it was survivorship — they "
              "measured only windows already known to contain a run. The base-rate control is "
              "what makes this one different, and it cuts both ways: the run windows and the "
              "whole week lose at about the same rate per fire, so there is nothing special about "
              "the tape near a run from these gates' point of view.",
    section_ref="Movement 2, all sections.",
    verification="Re-run the base rate on a genuine trend week — this is one quiet week and the "
                 "finding is scoped to it.",
    suggested_mode="hold", arms_when="n/a.", exit="n/a.",
    kill="A trend week where the base rate is positive.",
    number="−$1,905.36 on 117 fires across the week's tape; −$517.79 of it the four silent slots.",
    owner="Nobody", revert="n/a.",
)


def main():
    ids = [p["id"] for p in P]
    assert len(ids) == len(set(ids)), "duplicate play id"
    for w in ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION"):
        rk = sorted(p["rank"] for p in P if p["window"] == w)
        assert rk == list(range(1, len(rk) + 1)), f"{w} ranks not contiguous: {rk}"
    pathlib.Path(OUT).write_text(json.dumps(P, indent=1, ensure_ascii=False))
    print(f"→ {OUT}  {len(P)} plays")
    for w in ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION"):
        print(f"   {w:14} {sum(1 for p in P if p['window'] == w)}")


if __name__ == "__main__":
    main()
