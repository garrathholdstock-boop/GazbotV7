#!/usr/bin/env python3
"""Rebuild reports/friday_v7/plays.json for the week ending 2026-08-21.

★ EVERY PLAY ON THIS CARD TRACES TO A VERDICT A SECTION ACTUALLY REACHED. `section_ref` names the
section and the paragraph; if you cannot find the verdict there, the play is wrong and should be
deleted rather than defended. Nothing here is carried over from a previous week's card except the
NOT-AN-ACTION rows, which exist precisely so a previous week's idea cannot come back unexamined.

★ WHY THE FILE ON DISK HAD TO BE OVERWRITTEN. The plays.json this replaces was frozen on 2026-08-22
and its SATURDAY #1 was "confirm the gateway before Sunday 22:00Z so the weekend-flatten timer can
close the four open lots". That deadline has passed, the timer failed 119 times, and you closed the
position by hand on Monday. A card whose top row is an expired instruction about a position that no
longer exists is worse than no card: it is the first thing the reader sees and it is wrong.

★ THE THREE IN-FRAGMENT POINTERS THAT CONSTRAIN THE NUMBERING. Three sections written on 08-22 cite
plays by position, and those citations are stitched into this report:

    movement2_idle_gates.html  "BUILD #6's n>=60 kill criterion has to be PER GATE"
    part1_live.html            "BUILD #8, with an AUC-0.60 / permutation-p kill criterion"
    part2_6_router_review.html "BUILD #9 is the fix: populate signal_journal.suppressed_by"

So BUILD ranks 6, 8 and 9 are PINNED to those three plays. A re-rank that moves them sends the
reader to the wrong row, and nothing in the build catches a pointer that resolves to the wrong
meaning — only one that resolves to nothing. (A fourth match, the "SATURDAY #1 + MONDAY #1 SHIPPED"
in Part 2.6 §5, is a VERBATIM QUOTE of a line sitting in gate_switches.env since 2026-08-09. It is
not a pointer at this card and must not be "fixed".)

Run:  python3 scripts/friday_v7_plays_0821.py
"""
from __future__ import annotations

import json
import pathlib
import sys

OUT = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"

OP = "Garrath — by hand at the desk"
ME = "Claude — code change, then a restart"


def P(**kw) -> dict:
    kw.setdefault("money_gbp", 0)
    return kw


PLAYS: list[dict] = [

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # SATURDAY — needs a restart or a deadline
    # ══════════════════════════════════════════════════════════════════════════════════════════
    P(id="delete-weekend-flatten-timer-0821", window="SATURDAY", rank=1, tier="LIVE",
      topic="DELETE gazbot7-weekend-flatten.timer — it is still armed and it fires again on Sunday",
      play="<code>systemctl disable --now gazbot7-weekend-flatten.timer</code> and remove the unit "
           "file. It was built as a one-shot for a position that no longer exists, and it is the "
           "only row on this card with a date attached.",
      mechanism="The unit is written to self-disable once the venue reads flat — but it dies on a "
                "<code>PermissionError</code> before it ever reads the venue, so it has never "
                "disabled itself. <code>systemctl list-timers</code> has it next elapsing "
                "<strong>Sunday 2026-08-30 22:00Z</strong>, then every minute to 23:59Z. What it "
                "does when it runs is re-arm the day rider and write a <em>bare-stamp</em> claim "
                "through the operator-button path — and a bare stamp means <strong>claim "
                "everything</strong>. Against whatever happens to be open that night, on a shared "
                "netted account, that is the 08-06 cascade with a timer on it.",
      rationale="A recovery job that outlives the incident it was built for is not a safety net, it "
                "is an unowned actor with write authority. This one cannot even report that it "
                "failed: the page() call sits BELOW the file write that kills it.",
      number="119 firings on 2026-08-23, 0 orders placed, 0 pages sent. Next elapse Sun 2026-08-30 "
             "22:00Z. Journal: 105 gateway failures then 14 PermissionError.",
      section_ref="Front page (how the open position ended); Part 1.6 §5; the unit's own journal, "
                  "which is the arbiter here rather than any desk instrument.",
      verification="<code>systemctl list-timers | grep weekend-flatten</code> returns nothing, and "
                   "<code>systemctl is-enabled gazbot7-weekend-flatten.timer</code> says "
                   "<code>disabled</code> or the unit is gone.",
      arms_when="Immediately. There is no condition.",
      exit="n/a — this is a deletion.",
      kill="If you want the capability kept, the kill criterion is the opposite: it may stay ONLY "
           "once page() is moved ABOVE the file write and the run is proven end-to-end against a "
           "live position on a Sunday. Until then it is a liability, not a net.",
      suggested_mode="deploy", owner=OP,
      revert="Re-enable the timer; the unit file is in git.", money_gbp=0),

    P(id="day-rider-protective-stop-3atr-0821", window="SATURDAY", rank=2, tier="LIVE",
      topic="Put a protective stop on the day rider's own book at 3.0×ATR",
      play="Add a venue-resting protective stop to <code>day_rider.py</code> at "
           "<strong>3.0×ATR</strong> from entry. Not 1.5× — that width was this report's first "
           "answer and it is wrong.",
      mechanism="The rider is a second book on the same IB account and it has never had a stop. "
                "Re-racing ALL SIX of the week's rider entries at seven widths, rather than just "
                "the losing one, moves the answer: the closed book as traded is −$272.00; at "
                "3.0×ATR it is <strong>+$195.70</strong>, the only positive cell and the only one "
                "that keeps all three winners. 1.5×ATR — the first pick — is −$388.90 and keeps "
                "one. Cause of death for the tighter width is winners-retention, not expectancy.",
      rationale="It is the week's highest-value change and the week's whole loss is one unstopped "
                "position. Every width tested closes Friday's four lots within nineteen minutes of "
                "entry, six and a half hours before the gateway stopped answering — so the stop is "
                "upstream of the wedge, not a victim of it.",
      number="+$468 against the week as traded (as-traded −$272.00 → +$195.70 at 3.0×ATR), on 6 "
             "entries × 7 widths.",
      section_ref="Part 1.5 disposition (LIVE) and Part 1.6 §3b — the corrected rider-stop grid, "
                  "raced on every day rather than only the losing one.",
      verification="A resting stop order visible on the venue within 60s of a rider entry, and "
                   "<code>day_rider_state.json</code> carrying its price. Not a soft stop in code.",
      arms_when="Every rider entry, unconditionally.",
      exit="The stop, the existing trail, or the 20:40Z hard flat — whichever fires first.",
      kill="If over the next 20 rider entries the 3.0×ATR stop costs more in clipped winners than "
           "it saves in tail losses, widen it before removing it. Removing it entirely is not on "
           "the table: an unstopped book is what this week cost.",
      suggested_mode="deploy", owner=ME,
      revert="<code>data/day_rider.env</code> → <code>day_rider=off</code>, or drop the stop "
             "parameter.", money_gbp=0),

    P(id="standdown-to-a-file-0821", window="SATURDAY", rank=3, tier="LIVE",
      topic="Make the tournament standdown a FILE that every writer checks",
      play="Move <code>TOURNAMENT_STOOD_DOWN</code> out of <code>router_tick_durable.py</code> and "
           "into a state file, and make <code>open_hour_watch.py</code> — and any future writer — "
           "read it before writing a switch.",
      mechanism="The standdown is a router-LOCAL variable. It only stops the ROUTER writing "
                "<code>on</code>. <code>open_hour_watch.py</code> is a second writer with off→on "
                "authority and zero standdown awareness, and on Friday it armed "
                "<code>abs_veto_short</code> straight through the standing operator standdown. The "
                "only reason that cost nothing is that the tape produced no signal in the 2m15s "
                "window before it was benched again.",
      rationale="A safety state that one of its two writers cannot see is not a safety state. This "
                "is a $0 incident purely by luck, and luck is not a control.",
      number="1 unauthorised arm on 2026-08-21, 2m15s wide, $0 by luck. "
             "<code>open-hour-watch.service</code>'s own unit file says it must NEVER write "
             "<code>gate_switches.env</code>; it has written since 08-05.",
      section_ref="Part 2.6 §4 and its disposition (LIVE, named a Saturday item).",
      verification="Set the standdown, then force an <code>open_hour_watch</code> arm condition and "
                   "confirm it refuses and logs the refusal. A test that cannot be shown to fail is "
                   "not a test.",
      arms_when="n/a — it is a guard, always on.",
      exit="n/a.",
      kill="If the file becomes a third source of truth rather than the single one, delete it and "
           "make the standdown a property of the switch file itself.",
      suggested_mode="deploy", owner=ME,
      revert="Revert the commit; the variable comes back.", money_gbp=0),

    P(id="delete-carveout-header-0821", window="SATURDAY", rank=4, tier="LIVE",
      topic="Delete the five expired carve-outs from gate_switches.env's comment header",
      play="Open <code>data/gate_switches.env</code> and delete the five dated instruction lines in "
           "its header. Deleting the lines is the only thing that closes a carve-out.",
      mechanism="<code>switch_notes()</code> splices the top 45 comment lines of that file into "
                "EVERY router prompt, labelled ACTIVE, and nothing prunes them. Five are in there "
                "now, the oldest thirteen days old. Four are past their own stated expiry. "
                "<strong>The 2026-08-09 line is the dangerous one: it asserts that "
                "<code>abs_veto_short</code> IS ARMED BY DEFAULT</strong> — which directly "
                "contradicts the standing operator standdown the router is currently enforcing, on "
                "the same gate that <code>open_hour_watch.py</code> armed through that standdown on "
                "Friday.",
      rationale="A carve-out comment never expires and a zero-mention streak is not a fix. Two of "
                "the five have been restated to the router 106 and 66 times out of 1,425 ticks; the "
                "other three sit there quietly and would be read the moment the tape produces the "
                "situation they describe.",
      number="5 instructions spliced as ACTIVE, oldest 13d 1h. Restated 106 and 66 times in 1,425 "
             "ticks; three at 0 of 1,425 — which is a dormant instruction, not a closed one.",
      section_ref="Part 2.6 §5 and its disposition (LIVE).",
      verification="<code>head -45 data/gate_switches.env</code> shows no dated instruction lines, "
                   "and the next router tick's prompt carries no ACTIVE carve-out block.",
      arms_when="Immediately.",
      exit="n/a.",
      kill="n/a — this is a deletion of expired text. If a carve-out is still wanted, re-add it "
           "with an expiry the splicer enforces.",
      suggested_mode="deploy", owner=OP,
      revert="git restore the file; the lines are in history.", money_gbp=0),

    P(id="core-health-flat-venue-0821", window="SATURDAY", rank=5, tier="LIVE",
      topic="Point core_health.flat at the venue position, or rename it tournament_flat",
      play="Either make <code>core_health.flat</code> read the venue position line, or rename the "
           "field so nobody reads it as a desk-wide safety signal again.",
      mechanism="The field is tournament-scoped. It said the desk was flat while the venue was long "
                "four lots, and the router repeated that reading for 137 of 141 consecutive ticks "
                "while <code>updatePortfolio</code> in the same journal read "
                "<code>position=4.0 … unrealizedPNL=−950.27</code>.",
      rationale="This is the instrument that should have caught the whole incident and it read "
                "green throughout. A flag that is right about one book and silent about the other "
                "is worse than no flag, because it is the one people check.",
      number="137 of 141 router ticks called a live four-lot position flat.",
      section_ref="Part 2.6 §6 and disposition (LIVE); Part 1 disposition (FAULT).",
      verification="Open a 1-lot rider position by hand and confirm <code>core_health.flat</code> "
                   "goes false. If it stays true, the rename is the honest option.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="deploy", owner=ME,
      revert="Revert the commit.", money_gbp=0),

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # MONDAY — switch file, shadow slate, router constants. All reversible in five minutes.
    # ══════════════════════════════════════════════════════════════════════════════════════════
    P(id="bench-absveto-short-slot-0821", window="MONDAY", rank=1, tier="SHADOW",
      topic="Bench abs_veto_short's automated slot — and keep the signal in shadow",
      play="Set <code>abs_veto_short=off</code> in <code>data/gate_switches.env</code>. Leave the "
           "55s-confirm mirror running in the shadow book to carry the case.",
      mechanism="The gate is only live-positive because your hand took <strong>+$314.74</strong> "
                "out of it. Strip the hand and the machine's half is negative across ten cells in "
                "two stop sweeps, every one of them negative, with the worst leave-one-day-out "
                "negative throughout — so the sign survives, which makes this a verdict rather than "
                "a knife-edge.",
      rationale="Benching the machine's half is not benching the idea. The entry treatment (the 55s "
                "continuation-confirm) is the top of this week's shadow board and it stays there; "
                "what is being switched off is the unfiltered automated slot.",
      number="−$203.00 over 22 lots live; the machine's half is negative in 10 of 10 stop cells; "
             "your hand contributed +$314.74 of it (venue-stop figure, §2.4).",
      section_ref="Part 1.5 §2 and disposition (SHADOW); Part 2 §3 for the mirror's standing.",
      verification="<code>grep abs_veto_short data/gate_switches.env</code> reads <code>off</code>, "
                   "and the tournament's next start logs it in the "
                   "<code>gate switches changed → DISABLED [...]</code> line. ⚠ Prove it by that "
                   "line, never by the file's mtime.",
      arms_when="n/a — it is a bench.",
      exit="Existing positions still exit normally; a bench blocks NEW entries only.",
      kill="Un-bench when the 55s mirror clears the Part 2 battery on a positive tradable-hours "
           "week with a positive leave-one-day-out. Not on a lapse, and not on a quiet week.",
      suggested_mode="config", owner=OP,
      revert="Delete the <code>=off</code> line — but restart the tournament FIRST; the roster is "
             "import-time only and an absent gate defaults to ON.", money_gbp=0),

    P(id="retire-rider-w5-0821", window="MONDAY", rank=2, tier="REFUTED",
      topic="Retire rider_w5 from the shadow book — it has been quietly red since 08-17",
      play="Remove the <code>rider_w5</code> arm from <code>src/gazbot7/shadow.py</code> (or add it "
           "to the retired set). It is the only decided item that comes out of Movement 3 and it "
           "costs nothing.",
      mechanism="Shipped on 2026-08-15 out of last week's greenfield phase, quoted at "
                "<strong>+$4,841 and +$19.29 a trade</strong>. It has taken 51 forward trades since "
                "08-17 and sits at <strong>−$1,471, or −$28.84 a trade</strong>, 18% wins, red on 6 "
                "of 7 days and red in all four ATR buckets — worst in the 11–16 band its own filter "
                "selects for. Zero flagged rows, so this is clean data, not a measurement artefact. "
                "Its in-sample +$1,936 collapses to +$282 on strip-best-3, and the +$19.29 it "
                "shipped on never had a strip test attached.",
      rationale="This is not a thin-n case. 51 live trades, 1,339 out-of-sample trades at "
                "−$5.43 each, and −$174 on the census week it was built for all agree, and the "
                "mechanism has an explanation: at fire time the median run has 12–41pt left against "
                "a 33–48pt stop, and about one fire in twenty is a run.",
      number="−$1,471 over 51 live forward trades (−$28.84/tr) against +$19.29/tr claimed. "
             "OOS: 1,339 trades, −$5.43/tr, strip-3 −$9,293.",
      section_ref="Movement 3 §3 and §5 (the pooled-rider card); RIDER_ALL §5 in the appendix "
                  "carries the full grading.",
      verification="The arm no longer appears in <code>shadow.db</code>'s active strategy list, and "
                   "the next shadow tick logs one fewer arm.",
      arms_when="n/a — this is a retirement.",
      exit="n/a.",
      kill="Only revive it behind a SELECTOR — something that predicts which board becomes a run. "
           "Not more days: the power calculation says ~10,500 trades to separate it from zero.",
      suggested_mode="deploy", owner=ME,
      revert="Re-add the ShadowVariant; it is in git.", money_gbp=0),

    P(id="retire-vac-abs-0821", window="MONDAY", rank=3, tier="REFUTED",
      topic="Retire VAC-ABS too — last week's other greenfield shadow pick",
      play="Retire the <code>VAC-ABS</code> arm. Do not re-shadow it.",
      mechanism="Forward-tested unaltered it looked like the week's best greenfield result: "
                "+$1,319.21 over 97 trades, +$13.60 a trade net of the $1.50 round trip. Then it "
                "was given the five days it had never seen: <strong>−$529.50 over 27 trades</strong>, "
                "confirmed by strip-5 at −$427.",
      rationale="Two shadow arms shipped off last week's greenfield phase; both are dead a week "
                "later; neither was being graded by anything. That is the finding, and it is "
                "procedural rather than analytical.",
      number="+$1,319.21 / n=97 / +$13.60 per trade forward, then −$529.50 over 27 unseen trades; "
             "strip-5 −$427.",
      section_ref="Movement 3 §6 (the graves table) and the VACUUM dossier's VERDICT in the "
                  "appendix.",
      verification="Absent from <code>shadow.db</code>'s active strategy list on the next tick.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a — refuted by its own out-of-sample leg.",
      suggested_mode="deploy", owner=ME,
      revert="Re-add the arm.", money_gbp=0),

    P(id="bench-late-boarders-europe-0821", window="MONDAY", rank=4, tier="SHADOW",
      topic="Adopt the 07:00–13:00Z bench for any late-boarding rider as a router rule",
      play="Add a router constant that benches late-boarding rider arms in the European session "
           "(07:00–13:00Z). It is a bench, so it fails safe.",
      mechanism="It is the one rule in the whole greenfield movement that replicates on all three "
                "independent legs: −$29.38 a trade on the in-sample lake, −$20.04 on the "
                "205-session leg, and −$2.43 on the 11-session forward leg (n=373 on the last). No "
                "new instrument is needed and nothing has to be predicted.",
      rationale="Everything else the movement produced is a build or a question. This is the only "
                "positive deliverable that survived its own battery, and its direction is the cheap "
                "one — a wrong bench costs an option, a wrong arm costs money.",
      number="Red on all three legs: −$29.38 / −$20.04 / −$2.43 a trade, the last on n=373.",
      section_ref="Movement 3 §10 disposition and §5 (the UNCLASS card); the UNCLASS dossier §11 in "
                  "the appendix has the three legs in full.",
      verification="A router tick inside 07:00–13:00Z shows the rule in its reasoning and no "
                   "late-boarding arm switched on.",
      arms_when="n/a — it is a bench, active 07:00–13:00Z.",
      exit="n/a.",
      kill="Drop the rule if a late-boarding arm is green in that window over 100+ forward trades. "
           "One green week is not enough — the effect it is buying is small.",
      suggested_mode="config", owner=ME,
      revert="Delete the constant.", money_gbp=0),

    P(id="gold-fade-unrouted-0821", window="MONDAY", rank=5, tier="SHADOW",
      topic="Run the gold fade UNROUTED — last week's MGC router rule is refuted",
      play="Do not apply last week's regime router rule to <code>mgc_hole_break_fade</code>. Leave "
           "the arm running across all regimes in shadow.",
      mechanism="The rule was killed twice, independently: by the forward walk AND by the 320-day "
                "tape. It would bench the gate in <code>NORMAL_CHOP</code>, which is the regime "
                "currently paying best.",
      rationale="A router rule fitted on 29 days of gold and then contradicted by 320 is exactly "
                "the shape of the in-sample rules this desk keeps having to withdraw. The absence "
                "of a rule is the finding.",
      number="Refuted on both the forward walk and 320 trading days of MGC minute bars "
             "(2025-07-28 → 2026-08-19).",
      section_ref="Movement 3 §8 and disposition; the MGC dossier §5.3 in the appendix.",
      verification="No regime condition on the gold arm in the shadow config.",
      arms_when="All regimes, in shadow only.",
      exit="The wide chandelier on a single lot — stop 3.0 ATR, arm 2.0, trail 2.0, 480-min "
           "backstop. NOT the live MNQ slot configuration, which is the opposite shape.",
      kill="Revisit routing only after a forward walk on the depth-mid bars, i.e. after BUILD #1.",
      suggested_mode="shadow-first", owner=ME,
      revert="Re-add the regime condition.", money_gbp=0),

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # BUILD — ranks 6, 8 and 9 are PINNED (see the module docstring).
    # ══════════════════════════════════════════════════════════════════════════════════════════
    P(id="mgc-depth-mid-bars-0821", window="BUILD", rank=1, tier="LIVE",
      topic="★ Build the depth-mid bar source into the MGC shadow — the gating item for all of gold",
      play="Point the MGC shadow service's minute-bar builder at the <strong>depth mid</strong> "
           "instead of at trades, and keep the existing trade-bar arms alive as "
           "<code>*_tradebar</code> controls so the difference is visible rather than asserted. "
           "Nothing else on the gold line is worth doing first.",
      mechanism="Last week's shadowed gold gate has been live since Monday and is losing: "
                "<strong>−$1,196 across 80 trades in seven days, all three arms red</strong>. The "
                "lab replay of the same seven days makes +$512. The cause is the input tape: the "
                "research builds one-minute bars from the depth mid (which updates every 250ms "
                "whether or not anything trades), the service builds them from trades, and gold "
                "prints sparsely — so a sixty-minute high on one is not the sixty-minute high on "
                "the other. Hold everything else constant and change only the tape: depth-mid bars "
                "n=56 → <strong>+$172 (+$3.06/tr)</strong>; trade bars n=53 → "
                "<strong>−$475 (−$8.96/tr)</strong>. The sign flips on the bar source alone.",
      rationale="This is a plumbing mismatch between lab and production, not a research failure, "
                "and the fix is mechanical: the service already holds a <code>DepthFeed</code> "
                "connection to gold's book because the liquidity filter needs it, so it already has "
                "the bid and the ask. Until it lands, no gold cell should be promoted and none is "
                "being proposed.",
      number="Live shadow −$1,196 / 80 trades vs lab +$512 on the same days. Bar-source A/B on the "
             "six days both tapes cover: +$3.06/tr vs −$8.96/tr.",
      section_ref="Movement 3 §8 (gold, in its own right); the MGC dossier §3 and §12.1 in the "
                  "appendix.",
      verification="Both arms present in <code>data/shadow_mgc.db</code> under distinct names, and "
                   "a week of forward trades where the depth-mid arm and the "
                   "<code>*_tradebar</code> control diverge in the predicted direction.",
      arms_when="Shadow only. No live gold promotion behind this until the two arms have run "
                "side by side.",
      exit="Wide chandelier on a single lot: stop 3.0 ATR, arm 2.0, trail 2.0, 480-min backstop.",
      kill="If the depth-mid arm is ALSO red over 60+ forward trades, the bar source was not the "
           "explanation and the whole gold reversion family goes back to PARKED.",
      suggested_mode="deploy", owner=ME,
      revert="Point the bar builder back at trades.", money_gbp=0),

    P(id="shadowvariant-missing-fields-0821", window="BUILD", rank=2, tier="LIVE",
      topic="Add atr_min, a wrapping clock window and an ER10 gate param to ShadowVariant",
      play="Three small changes to <code>src/gazbot7/shadow.py</code>: (1) "
           "<code>gate_board</code>'s window test becomes "
           "<code>inw = (lo &lt;= h &lt; hi) if lo &lt; hi else (h &gt;= lo or h &lt; hi)</code> so "
           "a 21:00→07:00 window can exist at all; (2) <code>ShadowVariant</code> gains an "
           "<code>atr_min</code>, defaulted to 0.0 so nothing existing changes; (3) an "
           "<code>er_win_min</code> that reads the ENTRY WINDOW's efficiency rather than ER30.",
      mechanism="All three are blockers on shadowing anything from this movement honestly. A rule "
                "that is a BAND cannot be expressed with only a ceiling. A wrapping clock window "
                "is never true, so an overnight arm silently never fires. And "
                "<code>ShadowVariant.er_min</code> reads ER30 — substituting it for the 10-minute "
                "ER FLIPS the held-out leg from +$5.34 to −$2.25 a trade and turns both controls "
                "positive, i.e. it is a different hypothesis wearing the same name.",
      rationale="★ This is exactly how <code>rider_w5</code> came to be quoted at +$19.29 while "
                "making −$28.84. An arm shipped AROUND a missing field records a different strategy "
                "under the intended name, and nothing downstream can tell.",
      number="ER30 substituted for ER10 flips the held-out leg +$5.34/tr → −$2.25/tr and reverses "
             "both controls.",
      section_ref="Movement 3 §9 item 5; the RIDER_ALL dossier §11 in the appendix, which lists all "
                  "three blockers with the one-line fix for each.",
      verification="A unit test that an arm with <code>hh_lo=21, hh_hi=7</code> fires at 23:00Z and "
                   "not at 12:00Z, and one that <code>atr_min</code> excludes a below-band fire.",
      arms_when="n/a — infrastructure.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="deploy", owner=ME,
      revert="Revert the commit; defaults are chosen so nothing existing changes.", money_gbp=0),

    P(id="census-flow-bucket-phase-0821", window="BUILD", rank=3, tier="LIVE",
      topic="★ Fix the census's flow-bucket phase — 21 of 68 labels move on it alone",
      play="In <code>scripts/run_census.py</code>, snap the flow window's slide to the CLOCK rather "
           "than to the array index.",
      mechanism="21 of 68 run labels change on bucket phase alone, and only 17 of the 68 run "
                "timestamps are minute-aligned in the first place. This is the mechanism behind the "
                "divergence between the two census freezes this cycle — 70 runs / 65 sat out / "
                "$9,986 became 68 / 62 / $9,610 — which is why Movement 2 carries a red banner.",
      rationale="Every hunt this desk scopes by cluster inherits this error, and it is a real bug "
                "with a one-line character rather than a modelling judgement.",
      number="21 of 68 labels phase-dependent; 17 of 68 run timestamps minute-aligned; two freezes "
             "of the same week differ by 2 runs and $376 of ceiling.",
      section_ref="Movement 3 §4 (the vocabulary table) and §9 item 3; the UNCLASS dossier §13.",
      verification="Re-freeze the census twice with the bucket origin offset by 30s and get the "
                   "same 68 labels both times.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="build", owner=ME,
      revert="git revert.", money_gbp=0),

    P(id="census-vocabulary-0821", window="BUILD", rank=4, tier="LIVE",
      topic="★ Rename two census labels, stop splitting on flow, and ship the four run SHAPES",
      play="Three edits to the census's vocabulary: <code>UNCLASS</code> → <code>UNTESTED</code> "
           "and report it as COVERAGE; <code>OPEN/NEWS</code> → <code>US-OPEN-WINDOW</code> with "
           "the two footprint tests DELETED; stop splitting runs into "
           "<code>FLOW-LED</code>/<code>VACUUM</code> at all. Then add the four run SHAPES — TURN, "
           "STEP-REPRICE, DRIFT-VOID, GRIND-CONT — one <code>if</code> each, all computable at the "
           "run's start minute.",
      mechanism="Three of the five labels were interrogated directly this week and none survived. "
                "<code>UNCLASS</code>: base rate 75.4% on all tape, lift <strong>0.82</strong> — a "
                "run is LESS likely to be UNCLASS than an arbitrary minute is. "
                "<code>OPEN/NEWS</code>: lift over the bare clock <strong>0.921×</strong>, i.e. the "
                "two footprint tests remove 41% of the window and keep the LESS run-dense half. "
                "<code>FLOW-LED</code>/<code>VACUUM</code>: the flow event fires on 20.4–20.6% of "
                "all tape and then splits it on a <strong>49.6–49.9% coin toss</strong> — 0.33 "
                "percentage points of directional information.",
      rationale="These are independent measurements by different hunts on different tape, and two "
                "of them are the second such measurement in two weeks. The vocabulary is the thing "
                "the whole cold half of the report is scoped by; leaving it wrong is more expensive "
                "than any single gate on this card.",
      number="UNCLASS lift 0.82 on 75.4% base; OPEN/NEWS lift 0.921× over the bare clock; "
             "FLOW-LED/VACUUM split carries 0.33pp. Replacement: <code>VOL-EXPANSION</code> is "
             "<strong>4.18× lift on 1.95% of tape</strong> and the census barely uses it.",
      section_ref="Movement 3 §4; the FLOW-LED, UNCLASS and OPEN-NEWS dossiers in the appendix each "
                  "reach it independently.",
      verification="Next week's census prints the new names and a <code>VOL-EXPANSION</code> bucket "
                   "with more than one member.",
      arms_when="n/a.",
      exit="n/a.",
      kill="If the four SHAPES turn out to be as unstable as the labels they replace, report runs "
           "with NO cluster at all rather than a third wrong vocabulary.",
      suggested_mode="build", owner=ME,
      revert="git revert.", money_gbp=0),

    P(id="lake-timeframe-landmine-0821", window="BUILD", rank=5, tier="LIVE",
      topic="⚠ Fix the lake's bars timeframe landmine — every unfiltered query now has look-ahead",
      play="Make <code>gazbot7.lake</code> require an explicit <code>timeframe</code> on any "
           "<code>bars</code> query, or default it to the 5s daily files. Then audit every caller.",
      mechanism="New <code>backfill_{1min,5mins,1hour,1day}.parquet</code> files now sit BESIDE the "
                "daily 5s files. Any query that does not filter on <code>timeframe</code> now "
                "inherits <strong>up to a full day of look-ahead, on every day</strong>. "
                "<code>gf_mgc_tape.load_l1()</code> is safe. <code>mgc_session_anchor.load()</code> "
                "is NOT.",
      rationale="This is a silent correctness fault in the data layer that every backtest in this "
                "report and every future one runs on top of. It produces confidently wrong numbers "
                "with no error, which is the class of fault this desk has been bitten by four times "
                "already this month.",
      number="1 confirmed unsafe caller found (<code>mgc_session_anchor.load()</code>); the blast "
             "radius is every <code>bars</code> query in the repo.",
      section_ref="Movement 3 §7 (the harness-bug table) and disposition; the MGC dossier §1.2.",
      verification="A test that an unfiltered <code>bars</code> query raises rather than returning "
                   "rows. A fault that cannot be shown to fail is not fixed.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="build", owner=ME,
      revert="git revert — but do not, this one is a correctness fault.", money_gbp=0),

    # ★ PINNED — movement2_idle_gates.html cites "BUILD #6's n>=60 kill criterion".
    P(id="shadow-ignition-confirmed-entry-0821", window="BUILD", rank=6, tier="SHADOW",
      topic="Shadow an ignition-CONFIRMED entry — the only asymmetry the idle-gate lab found",
      play="Add a shadow arm that joins a run AFTER ignition rather than predicting it, and score "
           "it <strong>per gate</strong> with an n≥60 kill criterion on each.",
      mechanism="Across 65 sat-out runs and four arms, every arm is negative and the live config "
                "loses −$1,333.85 in the run windows. The single exception is the "
                "post-ignition arm, nearly flat at −$45.00 on 17 fires against a clearly negative "
                "pre-ignition arm.",
      rationale="★ AND THE CAVEAT IS THE PLAY. That −$45.00 is <code>abs_veto_short</code>'s "
                "+$504.50 on 5 fires against −$549.50 on the other five gates' 12 fires; strip one "
                "fire and the arm is −$156.00. So the n≥60 kill criterion has to be PER GATE, not "
                "pooled — pooling is what made this look like an asymmetry in the first place.",
      number="−$45.00 on 17 post-ignition fires vs a clearly negative pre-ignition arm; but "
             "+$504.50 of it is 5 fires on one gate, and strip-one is −$156.00.",
      section_ref="Movement 2 §2 and disposition (SHADOW), which states the per-gate requirement "
                  "explicitly.",
      verification="Six separate per-gate rows in the shadow board, each with its own n, and no "
                   "pooled headline anywhere on the page.",
      arms_when="Shadow only.",
      exit="Match the gate's own live exit so the comparison is entry-only.",
      kill="Any gate that is negative at n≥60 on its OWN fires is dropped from the arm. If all six "
           "are dropped, the asymmetry was one gate on five fires and the lead is REFUTED.",
      suggested_mode="shadow-first", owner=ME,
      revert="Remove the arms.", money_gbp=0),

    P(id="shadow-duplicate-check-0821", window="BUILD", rank=7, tier="LIVE",
      topic="Add a row-level duplicate check at shadow-write time, and re-seed the broken arms",
      play="At shadow-write time, detect two arms writing byte-identical rows and refuse. Then "
           "re-seed the three broken arms.",
      mechanism="7 of the 38 shadow arms are the same rows under different names — one pair "
                "(<code>cx_clip_brk_live</code> vs <code>_standdown</code>) matches on 77 of 77 "
                "rows on every field. A broken arm records the CONTROL's trades under a second name "
                "and then reports a perfect null, which is indistinguishable from a real null.",
      rationale="Until this lands, <strong>every A/B delta on the shadow board is unverified</strong> "
                "— including the ones this report quotes. That is a bigger problem than any single "
                "arm's number.",
      number="7 of 38 arms duplicated; one pair identical on 77/77 rows across every field.",
      section_ref="Part 2 §5 and disposition (FAULT, named as a BUILD item).",
      verification="Deliberately seed two identical arms and confirm the writer refuses. Then diff "
                   "every remaining pair row-for-row and publish the count.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="deploy", owner=ME,
      revert="git revert.", money_gbp=0),

    # ★ PINNED — part1_live.html cites "BUILD #8, with an AUC-0.60 / permutation-p kill criterion".
    P(id="entry-side-claim-study-0821", window="BUILD", rank=8, tier="SHADOW",
      topic="Move the claim question to the ENTRY side, and give it a kill criterion",
      play="Run the study as an ENTRY-side question — is this entry stop-bound? — rather than an "
           "exit-side one, with a pre-registered kill criterion of <strong>AUC ≥ 0.60 and a "
           "permutation p below 0.05</strong>.",
      mechanism="The automated claim detector (peak / give-back) is refuted as an exit rule: "
                "out-of-sample it makes <strong>−$4 on 126 held-out trades</strong> against "
                "+$1,069 in-sample, and −$436 as the live config stands. Two independent "
                "populations, 119 calibrations. But the money it was chasing is real and it is on "
                "the entry side: −$18,672 over 378 unwatched STOP exits.",
      rationale="This is the largest identified pool of money in the report, and in the first draft "
                "it left the document with no play, no kill criterion and no owner. A relocation is "
                "only honest if it comes with the test that will kill it too.",
      number="Exit-side detector: +$1,069 in-sample → −$4 on 126 held-out trades. The pool it was "
             "aimed at: −$18,672 over 378 unwatched STOP exits.",
      section_ref="Part 1 §6 and disposition (REFUTED as an exit rule, relocated rather than "
                  "killed).",
      verification="A written pre-registration of the feature set and the kill criterion BEFORE the "
                   "study runs, and a permutation null run on the same feature count.",
      arms_when="Study only. Nothing arms off this.",
      exit="n/a.",
      kill="AUC below 0.60, or permutation p ≥ 0.05, charged for the full feature search. Then it "
           "is REFUTED on both sides and the pool is written off.",
      suggested_mode="build", owner=ME,
      revert="n/a.", money_gbp=0),

    # ★ PINNED — part2_6_router_review.html cites "BUILD #9 is the fix".
    P(id="populate-suppressed-by-0821", window="BUILD", rank=9, tier="LIVE",
      topic="Populate signal_journal.suppressed_by so a gate's fires can be reproduced",
      play="Actually write <code>suppressed_by</code> on the signal-journal insert.",
      mechanism="The column is NULL in every row despite being in the INSERT, so "
                "<code>COALESCE(...,'TAKEN')</code> reports every fire as TAKEN — including fires "
                "on benched gates on a zero-fill day. Any counterfactual built on that column is "
                "reading a constant.",
      rationale="You cannot grade a gate's alternative history without first checking that the sim "
                "reproduces its actual fires, and right now nothing can. This is upstream of the "
                "router review, the idle-gate lab and every bench-pricing question on the card.",
      number="NULL in all 222 rows this week — and it is the same defect the scope flagged last week.",
      section_ref="Part 2.6 §7 (the two instruments that should have written this section).",
      verification="A benched gate's next suppressed fire shows a non-NULL "
                   "<code>suppressed_by</code>, and the TAKEN count drops.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="deploy", owner=ME,
      revert="git revert.", money_gbp=0),

    P(id="nightly-timers-0821", window="BUILD", rank=10, tier="LIVE",
      topic="Put a timer on router_nightly and selector_nightly — both stopped silently",
      play="Add systemd timers for both, and make each write a heartbeat that "
           "<code>sweep.py</code> checks.",
      mechanism="Neither has a timer. Both stopped being written and nothing noticed — "
                "<code>selector_nightly</code> was four days stale on 08-18.",
      rationale="A monitoring file that stops being written is worse than one that errors, because "
                "its absence looks like a quiet week.",
      number="selector_nightly 4 days stale on 2026-08-18; no timer on either.",
      section_ref="Part 2.6 disposition (LIVE).",
      verification="<code>systemctl list-timers</code> shows both, and <code>sweep.py</code> goes "
                   "critical when a heartbeat is older than 36h. Prove the critical fires.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="build", owner=ME,
      revert="Disable the timers.", money_gbp=0),

    P(id="selector-nightly-defects-0821", window="BUILD", rank=11, tier="PARKED",
      topic="Fix selector_nightly's two known defects before believing it again",
      play="Add a <code>data_quality IS NULL</code> filter, and read each gate's OWN "
           "<code>stop_atr_mult</code> instead of hard-coding 1.0.",
      mechanism="Quarantined rows inflate its regret figure — on 2026-08-13, 48% of it was one "
                "phantom counted five times — and all four of its modes reprice at "
                "<code>stop_atr_mult=1.0</code>, so <code>exhaustion_short</code> (stop_k 1.5 since "
                "08-16) reads −$167 where live made +$100.50, and the day rider reads +$31.50 "
                "against +$188.",
      rationale="It is the instrument that is supposed to tell us whether the router is "
                "over-benching, and it is currently answering a different question with a "
                "different ruler.",
      number="48% of one day's regret was a single phantom counted 5×; exhaustion_short repriced "
             "−$167 vs +$100.50 live.",
      section_ref="Part 2.6 disposition (PARKED, both defects named).",
      verification="Re-run it on 2026-08-13 and confirm the regret figure falls and the "
                   "per-gate stop widths appear in its output.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="build", owner=ME,
      revert="git revert.", money_gbp=0),

    P(id="shadow-board-overnight-band-0821", window="BUILD", rank=12, tier="SHADOW",
      topic="Shadow board_overnight_band as an INSTRUMENTED QUESTION, not a candidate",
      play="After BUILD #2 (<code>shadowvariant-missing-fields-0821</code>) lands, add "
           "<code>board_overnight_band</code>: k=2.5, w=10, ER10 ≥ 0.50, 21:00→07:00Z, cooldown "
           "60m, ATR band 11.0–16.0, stop 3.0×ATR, target 6.0×ATR, "
           "<code>adverse_cut_atr=99</code> (ON PURPOSE), no chandelier, 240-minute cap.",
      mechanism="Generated on a 236-session backfill (+$10.46/tr, +0.444R, n=396, strip-10 still "
                "+$2,281, leave-one-month-out worst +$2,388) and held out on the 28-session 5s lake "
                "(+$5.34/tr, +0.224R, n=95) where the SIGN held — but strip-3 fell to −$51 and the "
                "DAYTIME control came back POSITIVE. The overnight-vs-daytime SEPARATION that "
                "generated the idea did not reproduce.",
      rationale="★ It is not here because we think it makes money. The specific thing being bought "
                "is whether overnight boards really differ from daytime ones, which two independent "
                "samples disagree about. Its random-time placebo is p = 0.097 and the session split "
                "was one of three post-hoc comparisons.",
      number="+$10.46/tr on the generating sample, +$5.34/tr held out; placebo p = 0.097; daytime "
             "control reverses.",
      section_ref="Movement 3 §10 disposition; the RIDER_ALL dossier §10 and §11 in the appendix "
                  "carry the exact arm and its router rule.",
      verification="The arm exists with <code>atr_min=11.0</code> AND <code>atr_max=16.0</code> "
                   "both set, an ER10 gate (never <code>er_min</code>, which reads ER30), and "
                   "<code>adverse_cut_atr=99</code>. Any of those three wrong records a different "
                   "strategy.",
      arms_when="Shadow only, 21:00–07:00Z, ATR 11–16, ER10 ≥ 0.50.",
      exit="Stop 3.0×ATR, target 6.0×ATR, 240-minute cap. No chandelier — every chandelier variant "
           "tested red once the trail bug was fixed.",
      kill="Negative over 150 forward trades, OR the daytime control arm beats it. The second is "
           "the real kill: if daytime is as good, the hypothesis is dead regardless of the P&amp;L.",
      suggested_mode="shadow-first", owner=ME,
      revert="Remove the arm.", money_gbp=0),

    P(id="shadow-gold-cross-asset-veto-0821", window="BUILD", rank=13, tier="SHADOW",
      topic="Shadow the cross-asset MNQ VETO for gold — the unturned stone that paid",
      play="Add a <code>veto_ref_symbol=\"MNQ\"</code> branch to the gold entry path and run it as "
           "its own arm. It needs an MNQ state feed the gold service does not currently have.",
      mechanism="Over 278 paired days, fading a gold break that the Nasdaq AGREES with loses "
                "<strong>$10.52 a trade</strong> and sits at the 2.5th percentile of its own "
                "placebo. As an arm it reads +$5.43/tr against +$1.72 blanket, and it is two-sided. "
                "The mirror — a cross-asset momentum CONFIRM — is cleanly negative at −$2.29/tr on "
                "the same days, which is what a real asymmetry looks like rather than a fitted one.",
      rationale="It is a genuinely new input rather than another cut of the same tape, it is "
                "well-powered, and its direction is the cheap one (a veto).",
      number="+$5.43/tr vs +$1.72 blanket over 278 paired days; placebo 97th/2.5th percentile. Does "
             "NOT reproduce on the 29-day book window (34th percentile).",
      section_ref="Movement 3 §8 and disposition; the MGC dossier §6 in the appendix.",
      verification="The arm and its un-vetoed control both present in "
                   "<code>data/shadow_mgc.db</code>, and an MNQ state value logged on every gold "
                   "entry decision.",
      arms_when="Shadow only, alongside BUILD #1's bar-source work.",
      exit="Wide chandelier on a single lot, as for every gold cell.",
      kill="If it does not separate from its control over 100+ forward trades, the 34th-percentile "
           "book-window reading was the true one and it goes PARKED.",
      suggested_mode="shadow-first", owner=ME,
      revert="Remove the branch.", money_gbp=0),

    P(id="shadow-er30-meter-0821", window="BUILD", rank=14, tier="SHADOW",
      topic="Shadow the ER30 arm-meter WITH its own control arm — do not arm a gate behind it",
      play="Instrument ER30 as an arm meter and run a control arm beside it. Nothing gates on it "
           "until the two have separated.",
      mechanism="+$3.54 against −$3.40 a trade on 3,238 untouched trades — the largest-n effect "
                "anywhere in the greenfield movement — but it REVERSES on the most recent eleven "
                "sessions.",
      rationale="One of those two readings is noise and we do not know which. Shadowing the meter "
                "with a control answers it for free and is the single cheapest open question in the "
                "movement.",
      number="+$3.54 vs −$3.40 a trade on n=3,238, reversing on the last 11 sessions.",
      section_ref="Movement 3 §11 (the stones still unturned) and disposition; UNCLASS §13.",
      verification="Two arms in the shadow board with the same entry and only the meter differing.",
      arms_when="Shadow only.",
      exit="Match the control exactly.",
      kill="If the meter and its control are within noise after 300 forward trades, the effect is "
           "an eleven-session artefact and it is REFUTED.",
      suggested_mode="shadow-first", owner=ME,
      revert="Remove the arms.", money_gbp=0),

    P(id="price-violent-whipsaw-bench-0821", window="BUILD", rank=15, tier="SHADOW",
      topic="★ Price a violent-whipsaw router bench — the chop commission's premise was wrong",
      play="Measure a two-term bench (high ATR + low efficiency) on the tournament's own fires, and "
           "propose it as a router rule only once it is priced.",
      mechanism="You asked for a chop-day scalper because the desk donates on chop days. <strong>It "
                "does not.</strong> On this week's two chop days (08-20 and 08-21) the tournament "
                "took ZERO trades, and the week's −$2,323 is the day rider's book. Across the whole "
                "18-day window the tournament's loss is concentrated in "
                "<strong>violent-whipsaw</strong> blocks — high ATR going nowhere — at "
                "<strong>−$1,383.50 on 95 trades</strong>, against −$403.00 on 58 in plain chop.",
      rationale="The correction is worth roughly ten times the scalper that was commissioned to fix "
                "the wrong thing, and it needs no new instrument — both terms are already in the "
                "router's vocabulary.",
      number="Violent-whipsaw −$1,383.50 on 95 trades vs plain chop −$403.00 on 58; zero tournament "
             "trades on the week's two chop days.",
      section_ref="Movement 3 §5 (the chop card) and §10 disposition; the chopscalp dossier §2 and "
                  "§13 in the appendix.",
      verification="A table of the tournament's P&amp;L by (ATR bucket × ER bucket) over 18 days, "
                   "with the bench's cost in forgone winners priced beside its saving.",
      arms_when="Nothing arms yet. This is a measurement.",
      exit="n/a.",
      kill="If the bench's forgone winners exceed its saved losses on the same 18 days, it is "
           "REFUTED and the chop lead closes entirely.",
      suggested_mode="build", owner=ME,
      revert="n/a.", money_gbp=0),

    P(id="grade-every-shipped-arm-0821", window="BUILD", rank=16, tier="LIVE",
      topic="★ Every shadow arm gets a named grading date and a strip-best figure printed beside it",
      play="Two rules, enforced in the shadow board's own rendering: an arm may not be added "
           "without a <code>graded_on</code> date, and any headline $/trade must print its "
           "strip-best-3 figure next to it.",
      mechanism="Two arms were shipped off last week's greenfield work. Both are dead a week later "
                "and <strong>neither was being graded by anything</strong>. "
                "<code>rider_w5</code> ran red for seven days on a quoted +$19.29 that had no strip "
                "test attached. <code>UNCL-RIDER-ASIA</code> is worse: it was never shipped at all, "
                "and nobody noticed for a week — it does not exist anywhere in "
                "<code>shadow.db</code>'s 82 strategies.",
      rationale="This is the procedural fix behind two of this card's retirements. A number that "
                "goes into the shadow book without a strip test and without anybody owning the "
                "grading is not evidence; it is a claim with a week's head start.",
      number="2 of 2 arms shipped last week are dead; 1 of the 2 was never actually shipped; 0 of "
             "the 2 were graded by anything.",
      section_ref="Movement 3 §3 (closing the loop) — the two rows and the paragraph beneath them.",
      verification="The shadow board page refuses to render an arm with no <code>graded_on</code>, "
                   "and every $/trade on it carries a strip figure.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a.",
      suggested_mode="build", owner=ME,
      revert="git revert.", money_gbp=0),

    P(id="mirror-book-to-lake-0821", window="BUILD", rank=17, tier="PARKED",
      topic="Mirror the 41ms book feed to the lake — it is the one L2 term that ever helped",
      play="Extend <code>tape_mirror.py</code> to export <code>capture.db.book</code> to the "
           "parquet lake before <code>prune_capture.py</code> deletes it.",
      mechanism="The chop lab tested sixteen candidates against 261.9M book rows and found exactly "
                "one L2 term that contributed anything: the <strong>41ms refill count</strong>, a "
                "RATE rather than a level. The 250ms <code>depth.db</code> sample cannot see it — "
                "it needs the 41ms <code>capture.db.book</code> feed, which is MNQ-only and rolls "
                "off after five trading days.",
      rationale="Every other book statistic this desk has tested is refuted (far-side depth share "
                "twice, the resting wall with the sign inverted). The one that is not cannot be "
                "studied at length, because the data does not survive the week.",
      number="1 of 16 candidates' L2 terms contributed; 5 trading days of retention on the only "
             "feed that carries it.",
      section_ref="Movement 3 §11 (stones) and §10 disposition; the chopscalp dossier §7.",
      verification="Book parquet in the lake for a date already pruned from "
                   "<code>capture.db</code>, with matching row counts. ⚠ The existing interlock "
                   "applies: never prune a day the mirror has not exported AND verified by count.",
      arms_when="n/a.",
      exit="n/a.",
      kill="Revive the 41ms study only once 30+ days are mirrored. Below that it is the same "
           "thin-n problem in a new place.",
      suggested_mode="build", owner=ME,
      revert="Stop the export; pruning is unaffected.", money_gbp=0),

    P(id="wide-target-ridge-shadow-0821", window="BUILD", rank=18, tier="SHADOW",
      topic="Shadow the 10×ATR target ridge — the wide-exit thesis, confirmed on one axis only",
      play="Add a shadow A/B on an existing MNQ arm that changes ONLY the target, from its current "
           "value to <strong>10×ATR</strong>, holding the stop fixed.",
      mechanism="The UNCLASS exit sweep — stop 1.0–4.0×ATR against target 2–16×ATR, caps 30 min to "
                "12 h, run on segments rather than blanket — found a genuine ridge at a 10×ATR "
                "target that holds across EVERY stop width tested. That is a plateau, not a point, "
                "and it is the most robust single thing in the movement.",
      rationale="★ And it splits the operator's own thesis in half honestly: <strong>wide exits are "
                "CONFIRMED on the target axis and REFUTED on the stop axis</strong>. Stop width "
                "barely matters here (1.5, 2.0, 2.5 and 4.0 all land in the same place) because the "
                "median MAE inside a run is half an ATR — we are not being shaken out, so a wider "
                "stop buys nothing.",
      number="A 10×ATR target ridge holding across every stop width from 1.0 to 4.0; the entry it "
             "was measured on is refuted, the exit shape is not.",
      section_ref="Movement 3 §5 (the UNCLASS card); the UNCLASS dossier §3 in the appendix has the "
                  "full 7×6 sweep.",
      verification="An A/B pair in the shadow board differing in exactly one field, verified "
                   "row-for-row as NOT byte-identical (see BUILD #7).",
      arms_when="Shadow only.",
      exit="Target 10×ATR, stop unchanged from the control.",
      kill="If the wide-target leg does not beat its control over 100 paired signals, the ridge was "
           "a property of the refuted entry rather than of the exit, and it goes PARKED.",
      suggested_mode="shadow-first", owner=ME,
      revert="Remove the arm.", money_gbp=0),

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # HOLD — already right; the action is to NOT touch them
    # ══════════════════════════════════════════════════════════════════════════════════════════
    P(id="hold-four-gates-benched-0821", window="HOLD", rank=1, tier="LIVE",
      topic="The four silent gates stay benched — the standdown is the best-performing thing here",
      play="Leave <code>rgv_long</code>, <code>rgv_short</code>, <code>grind_long</code> and "
           "<code>capitulation_long</code> off. Do nothing.",
      mechanism="Fired mechanically across this week's own tape in their exact live config, the "
                "four benched gates lose <strong>−$517.79 on 48 fires</strong>. Firing all six "
                "loses <strong>−$1,905.36 on 117 fires</strong> across the week, and −$1,333.85 in "
                "the run windows specifically. Stripping their filters to make them show up more "
                "often triples the fire count and makes the result worse in both windows — so the "
                "ATR floors and vetoes are earning their keep.",
      rationale="The four slots that did nothing are the best-performing thing on the desk this "
                "week. That is a genuinely uncomfortable sentence and it is the measured one.",
      number="−$517.79 on 48 fires (the four); −$1,905.36 on 117 fires (all six), whole week.",
      section_ref="Movement 2 §2–§3 and disposition (REFUTED); Part 1.5 §4.",
      verification="The switch file still reads <code>off</code> for all four after the next "
                   "restart, and the tournament's DISABLED line names them.",
      arms_when="Revisit on a MEASURED trend week, not on this one.",
      exit="n/a.",
      kill="An un-bench needs a positive arming case on a week the gates actually trade — never a "
           "lapse, never a quiet week, and never the absence of adverse evidence.",
      suggested_mode="no-op", owner=OP,
      revert="n/a — this is the current state.", money_gbp=0),

    P(id="hold-no-drift-action-0821", window="HOLD", rank=2, tier="LIVE",
      topic="Do not act under drift — and do not 'fix' the safety-block skip",
      play="Leave it exactly as it is. On <code>drift</code> the tournament skips its entire safety "
           "block, by decision.",
      mechanism="Acting on a position whose ownership is unknown, on a shared netted account, IS "
                "the 08-06 cascade. What changed on 08-16 is that the skip is no longer SILENT: "
                "<code>safety_skipped_cycles</code> is published in <code>core_health.json</code>, "
                "the desk alarms at cycles 1/12/60 naming each inactive protection, and "
                "<code>sweep</code> goes critical while holding.",
      rationale="The operator was asked directly and said \"no. dont act under drift. leave it.\" "
                "This row exists so the next session does not re-open it as a bug.",
      number="Standing decision, 2026-08-16 (DECISIONS §362).",
      section_ref="docs/STATE.md §5; standing operator decision.",
      verification="A test fails if an order path appears in that branch.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a — this is a decision, not a hypothesis.",
      suggested_mode="no-op", owner=OP,
      revert="n/a.", money_gbp=0),

    P(id="hold-never-overnight-0821", window="HOLD", rank=3, tier="LIVE",
      topic="NEVER HOLD OVERNIGHT — rider flat at 20:40Z, never 21:00Z",
      play="Unchanged. The rider flattens at 20:40 UTC.",
      mechanism="21:00Z <em>is</em> the CME halt, so a flatten fired then has no market and no "
                "retry. This week is the proof of what happens when the 20:40 flatten fails and "
                "nothing behind it works.",
      rationale="The week's largest loss is one position that went past this rule because every "
                "automatic path to enforce it shared a single failed connection.",
      number="The 2026-08-21 carry: opened 13:13:06Z, closed by hand 2026-08-24 11:59:39Z, "
             "−$2,155.44 net.",
      section_ref="Front page; Part 1.6 §5; standing operator rule.",
      verification="<code>day_rider_state.json</code> reads <code>venue_net: 0</code> by 20:45Z "
                   "every weekday. ⚠ Branch on <code>venue_net</code>, never on "
                   "<code>entered</code> — the 00:00Z session roll resets the latter.",
      arms_when="n/a.",
      exit="n/a.",
      kill="n/a — standing rule.",
      suggested_mode="no-op", owner=OP,
      revert="n/a.", money_gbp=0),

    P(id="hold-grind-atr-floor-0821", window="HOLD", rank=4, tier="PARKED",
      topic="Leave grind_long's 22-point ATR floor alone — grind is an entry question now",
      play="Do not raise, lower or remove the floor this week.",
      mechanism="The floor blocked <strong>24,110 of 24,121</strong> raw signals this week, which "
                "makes the gate un-testable rather than benched. The floor ladder IS monotone "
                "upward — 14pt −$1,143.50 → 22pt −$280.50 → 28pt +$469.00 — but strip-best-3 is "
                "negative at every rung, the worst leave-one-day-out is negative at every rung, and "
                "against 5,000 random same-size subsets the live 22pt rung sits at only the 65th "
                "percentile.",
      rationale="Raising the floor cannot make grind positive on its own live record, so this has "
                "stopped being \"the real grind question\". Grind is an entry question. Reachability "
                "is settled too: 22pt is the p75 of SESSION minutes and the p89 of ALL minutes — "
                "the two published figures were one denominator apart, not two measurements.",
      number="Blocked 24,110 of 24,121 signals; strip-best-3 negative at every rung; 65th percentile "
             "against 5,000 random subsets.",
      section_ref="Part 2.5 §2b and disposition (SHADOW); Movement 2 disposition (PARKED); "
                  "Part 1.5 disposition.",
      verification="Keep the shadow floor-ladder arms running as a forward confirmation of the "
                   "monotone shape, and nothing more.",
      arms_when="n/a.",
      exit="n/a.",
      kill="Revive the floor question only if grind's ENTRY is fixed first. A floor on a bad entry "
           "is a filter on a coin.",
      suggested_mode="no-op", owner=OP,
      revert="n/a.", money_gbp=0),

    P(id="hold-gold-exit-shape-0821", window="HOLD", rank=5, tier="LIVE",
      topic="Gold's exit is the OPPOSITE of the Nasdaq's — do not port the MNQ slot config to MGC",
      play="Every gold cell uses the wide chandelier on a SINGLE lot: stop 3.0 ATR, arm 2.0, trail "
           "2.0, 480-minute backstop. Do not apply the live MNQ two-lot configuration.",
      mechanism="Not the tight scalp — negative at 1R on both entries. Not the dual slot — Lot A is "
                "negative on gold and CANCELS Lot B, on both entries. Not a time cap — its headline "
                "numbers are a long-drift artefact on both entries. The finding replicates on 29 "
                "days.",
      rationale="This is the standing rule that MGC gates must be invented fresh rather than "
                "ported, earning its keep with a measurement. Gold is not the Nasdaq with a "
                "different multiplier — and it is $10.00 a point, not $2.00.",
      number="Replicates across 29 days on both entries; the dual-slot and time-cap refutations "
             "were re-confirmed this week.",
      section_ref="Movement 3 §8 (the exit family paragraph); the MGC dossier §13 in the appendix.",
      verification="The gold shadow config carries one lot and the chandelier constants above.",
      arms_when="n/a.",
      exit="As stated.",
      kill="n/a.",
      suggested_mode="no-op", owner=ME,
      revert="n/a.", money_gbp=0),

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # NOT-AN-ACTION — withdrawn or refuted, printed with their autopsies
    # ══════════════════════════════════════════════════════════════════════════════════════════
    P(id="na-promote-absveto55s-0821", window="NOT-AN-ACTION", rank=1, tier="REFUTED",
      topic="Do NOT promote abs_veto_55s to a live two-sided slot on Monday",
      play="It was last week's lead promotion candidate. It does not go live this week.",
      mechanism="Named test: the Asia void. <strong>$308.50 of its $332.00 was booked in a window "
                "with zero live fills since 08-05</strong>, leaving $23.50 on 34 fires and 2 of 5 "
                "days green.",
      rationale="Refuted as a THIS-WEEK case only. It is still the best-evidenced family on the "
                "board across all tradable-hour fires, and it stays in shadow.",
      number="$308.50 of $332.00 in a dead window; $23.50 on 34 tradable fires; 2 of 5 days green.",
      section_ref="Part 2 §3 and disposition (REFUTED for this week, SHADOW on its all-time record).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="Revive the promotion question when it has a positive TRADABLE-HOURS week with a "
           "positive leave-one-day-out. Not before, and never on an all-hours total.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-arm-grind-clean-trend-0821", window="NOT-AN-ACTION", rank=2, tier="PARKED",
      topic="Do NOT arm grind only on clean-trend days — it is un-runnable, not wrong",
      play="Leave it. The rule cannot be run often enough to matter.",
      mechanism="It makes $580.50 gross against a −$958.00 gross control and keeps 25 of 43 "
                "winners, so it is not refuted. But <strong>only 1 of 240 sessions is both "
                "clean-trend and above the 22-point floor</strong>. Net of fees it is +$548.00 and "
                "<strong>2026-07-29 alone is +$634.50 of it on 46 fires</strong> — drop that one "
                "session and the other eight days are −$1,784.50.",
      rationale="\"The best rule on the board\" and \"arm on 2026-07-29\" are nearly the same "
                "instruction on this sample. And the BUILDING-block version, scored on the same 128 "
                "fires, is −$748.50 on 51 fires keeping 17 of 43 winners — worse per fire than no "
                "rule at all, so it is not parked behind the wrong condition either.",
      number="1 of 240 sessions qualify; one session is +$634.50 of a +$548.00 net total.",
      section_ref="Part 2.5 §1 and disposition (PARKED).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="Revive only if the qualifying-session rate rises above ~10% of sessions, which means "
           "changing the floor or the trend definition, not the rule.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-grind-er-floor-0821", window="NOT-AN-ACTION", rank=3, tier="REFUTED",
      topic="Do NOT fix grind with an ER floor or a directional-net requirement",
      play="Both families are dead. Do not re-propose either.",
      mechanism="Named test: nine cells across two families on 128 live fires, every one negative — "
                "including the ER-0.35 floor that is already deployed elsewhere.",
      rationale="ER filters keep coming back because they sound like they should work. Nine "
                "negative cells on the gate's own live fires is the answer.",
      number="9 of 9 cells negative on 128 live fires.",
      section_ref="Part 2.5 disposition (REFUTED).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-2r-partial-variance-0821", window="NOT-AN-ACTION", rank=4, tier="REFUTED",
      topic="Do NOT run the 2R-partial as a variance lever — it does not smooth anything",
      play="Withdrawn. It was proposed as a smoothness trade and it is not one.",
      mechanism="Named measurement: daily standard deviation goes <strong>42.3 → 83.3</strong> on "
                "the same window in which it improves the mean.",
      rationale="It was only ever interesting as a variance lever. Measured, it doubles the "
                "variance. Re-open it as a MEAN lever if at all, and only on fresh grind trades.",
      number="Daily std 42.3 → 83.3.",
      section_ref="Part 2 §6 and disposition (REFUTED).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted on its own stated purpose.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-automated-claim-exit-0821", window="NOT-AN-ACTION", rank=5, tier="REFUTED",
      topic="Do NOT automate your claim hand as an EXIT rule",
      play="The peak / give-back detector does not ship. The question moves to the entry side "
           "(BUILD #8).",
      mechanism="Out-of-sample <strong>−$4 on 126 held-out trades</strong> against +$1,069 "
                "in-sample, and −$436 as the live config stands. Two independent populations, 119 "
                "calibrations.",
      rationale="Your hands made real money this week and the machine's profit exits made almost "
                "nothing — but the study that tried to copy your hand comes back at zero out of "
                "sample. Ask what the denominator is, every time.",
      number="+$1,069 in-sample → −$4 out of sample on 126 held-out trades.",
      section_ref="Part 1 §6 and disposition (REFUTED, relocated to BUILD #8).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted as an exit rule; the entry-side version carries its own kill criterion.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-reshadow-uncl-rider-asia-0821", window="NOT-AN-ACTION", rank=6, tier="REFUTED",
      topic="Do NOT re-shadow UNCL-RIDER-ASIA — four red weeks, and it never actually shipped",
      play="Leave it dead.",
      mechanism="Forward out-of-sample: W31 −$2.93, W32 −$15.90, W33 −$36.46, <strong>W34 "
                "−$38.08</strong> a trade. The ATR floor added to explain the first two restored "
                "none of them. ★ And then the deeper finding: <strong>there is no arm by that name "
                "anywhere in <code>shadow.db</code></strong> — all 82 strategies were listed.",
      rationale="It was last week's SHADOW pick out of the UNCLASS phase, it was never shipped, and "
                "nobody noticed for a week. That is the reason BUILD #16 exists.",
      number="Four consecutive red forward weeks; 0 of 82 shadow strategies carry the name.",
      section_ref="Movement 3 §3 and §10 disposition; the UNCLASS dossier §9 in the appendix.",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted by the forward leg.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-trade-any-mnq-greenfield-0821", window="NOT-AN-ACTION", rank=7, tier="REFUTED",
      topic="Do NOT arm anything on MNQ out of the greenfield movement — seven hunts, zero survivors",
      play="Nothing from Movement 3 goes live on the Nasdaq. Stated plainly rather than dressed as "
           "a near-miss.",
      mechanism="Seven hunts, dozens of named candidates, and not one MNQ LIVE candidate. The "
                "pooled rider measured <strong>+$14 over 1,289 out-of-sample trades</strong>; "
                "UNCLASS's rider is beaten by the same signal taken thirty minutes early; "
                "OPEN/NEWS is beaten by a gate containing no signal at all; FLOW-LED's last "
                "survivor is beaten by a time-shifted fake; VACUUM's survivor wins in both "
                "directions; the chop finalist is beaten by the null handed its own search.",
      rationale="Not one candidate survived its own robustness battery. That is not a bad week — it "
                "is the batteries working. What the movement produced instead is on the BUILD list, "
                "and it is worth more than another thin gate.",
      number="7 hunts, 0 LIVE candidates, 33 named graves each with the test that killed it.",
      section_ref="Movement 3 §1 (the board) and §6 (every grave).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="The next attempt is SELECTION BY EXPECTED SIZE at the board moment — no new data "
           "source, a different question of the same tape. Three labs independently put the "
           "tradeable threshold at about 120 points.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-l2-far-side-depletion-0821", window="NOT-AN-ACTION", rank=8, tier="REFUTED",
      topic="Do NOT revive L2 far-side depletion as a run selector — refuted twice, and not n-limited",
      play="Two independent measurements this week. Do not ask for 30 days.",
      mechanism="The pooled rider: 311 fires against 264M book rows, correlation "
                "<strong>−0.009</strong>, no monotone band, placebo p = 0.62. VACUUM, separately: "
                "<strong>49.44% ±2.52pp</strong> on unselected 55pt+ moves over 246.9M book rows, "
                "and 49.72% ±0.67pp on all 21,249 book-minutes.",
      rationale="The error bars are already tight. The null is not sample-limited, so more days buy "
                "nothing — which is the specific thing that makes this REFUTED rather than PARKED.",
      number="r = −0.009 (n=311, placebo p=0.62); 49.44% ±2.52pp and 49.72% ±0.67pp.",
      section_ref="Movement 3 §10 disposition; RIDER_ALL §7 and VACUUM §6 in the appendix.",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="A DIFFERENT book statistic — resting-size decay rate, or the sweep-through print — "
           "would be a new lead, not a revival of this one.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-wall-as-absorption-0821", window="NOT-AN-ACTION", rank=9, tier="REFUTED",
      topic="⚠ The resting wall is a TARGET, not absorption — the sign is inverted",
      play="Your lead L2 hypothesis for the chop scalper is refuted, and it points the other way.",
      mechanism="Unfiltered chop turns drift <strong>+0.054pt</strong> in the fade's favour over "
                "the next minute. Add \"wall ≥ 1.5×\" and it becomes <strong>−0.117pt</strong>. Add "
                "\"five-deep wall ≥ 1.3×\" and it becomes <strong>−0.374pt</strong> (t = −1.72; "
                "quintile z = −2.37). In the costed sweep <code>CT2_WALL</code> is the WORST of "
                "sixteen candidates at −$3.09/trade against the naive fade's −$2.54.",
      rationale="This is worth more than a null, because it is a null with a direction. A big "
                "resting wall at a range edge is not somebody absorbing — it is somebody's target, "
                "and price goes to it.",
      number="+0.054pt → −0.117pt → −0.374pt as the wall filter tightens; CT2_WALL worst of 16.",
      section_ref="Movement 3 §5 (the chop card) and §10 disposition; chopscalp §3 in the appendix.",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted with the sign inverted in two independent tests.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-router-thresholds-0821", window="NOT-AN-ACTION", rank=10, tier="REFUTED",
      topic="Do NOT change the router's thresholds or timing this week",
      play="No tuning. There is no sample to tune on.",
      mechanism="There were <strong>20 switch writes all week, 5 of them worth $0 by "
                "construction</strong>. Tuning on this week would be fitting to a standdown.",
      rationale="The tournament traded two of six slots for 22 lots. Four separate sections say "
                "independently that this is not enough evidence to re-tune anything, and this card "
                "is short on purpose because of it.",
      number="20 switch writes, 5 structurally worthless; 22 lots on 2 of 6 slots.",
      section_ref="Part 2.6 §2–§3 and disposition (REFUTED).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="Revive on a week the tournament actually trades — with a lag number attached, which "
           "this week could not produce.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-rearm-on-lapse-0821", window="NOT-AN-ACTION", rank=11, tier="REFUTED",
      topic="Do NOT re-arm a gate on a LAPSE — it needs a positive case",
      play="When a bench's rule goes quiet the gate returns to UNDECIDED, not ARMED.",
      mechanism="Named instance: 2026-08-19 15:35Z re-armed <code>abs_veto_short</code> thirty "
                "minutes after benching it, with no new evidence, straight into three stops for "
                "−$133. <strong>Third occasion on this gate.</strong>",
      rationale="\"Armed-by-default\" is a cold-start tiebreaker, not an override of a live adverse "
                "read. Decayed evidence removes the case for the bench; it does not create a case "
                "for the arm.",
      number="−$133 on 3 stops, 30 minutes after the bench. Third occasion on the same gate.",
      section_ref="Part 2.6 disposition (REFUTED, with the instance named).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted three times on the same gate.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-mgc-straddle-0821", window="NOT-AN-ACTION", rank=12, tier="REFUTED",
      topic="Do NOT revive mgc_straddle — refuted on 320 days, and last week's reason was wrong too",
      play="The volatility cell is dead. Upgraded from 22 days to 320 and from a gradient to an "
           "actual trade.",
      mechanism="n=3,945, <strong>−$1,248, −$0.32 a trade</strong>. All eight compression cells "
                "negative, the control also negative, and it dies on one tick of slippage.",
      rationale="★ Worth reading for the method rather than the verdict: last week's REASON for "
                "killing it was wrong (raw range sorts on ATR), and the verdict was right anyway. A "
                "right answer for a wrong reason is a fault, not a save.",
      number="n=3,945, −$1,248, −$0.32/tr, 8 of 8 cells negative, dies at one tick.",
      section_ref="Movement 3 §8 (the per-cell table) and §10 disposition.",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted on 320 trading days.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    P(id="na-strip-gate-filters-0821", window="NOT-AN-ACTION", rank=13, tier="REFUTED",
      topic="Do NOT strip the gates' filters to make them show up more often",
      play="The ATR floors and the vetoes stay.",
      mechanism="Ungating triples the fire count and makes the result WORSE in both the run windows "
                "and the whole week. Direction alignment does not rescue it either: aligned "
                "mechanical fires made <strong>−$602.60 on 11 fires</strong> — knowing which way "
                "the run would go was not enough, because the gates fire before the ignition and "
                "get stopped in the chop.",
      rationale="The recurring instinct when a gate is silent is to loosen it. Measured, that is "
                "the wrong direction: the filters are the part that works.",
      number="Ungated: 3× the fires, worse in both windows. Direction-aligned: −$602.60 on 11 fires.",
      section_ref="Movement 2 §2 and §4, and disposition (REFUTED twice).",
      verification="n/a.", arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted.",
      suggested_mode="no-op", owner=OP, revert="n/a.", money_gbp=0),

    # ★ PINNED count — rev2 material cites NOT-AN-ACTION #14; kept as the last row.
    P(id="na-exhaustion-exit-overrides-0821", window="NOT-AN-ACTION", rank=14, tier="REFUTED",
      topic="Do NOT ship the proposed exhaustion_short exit-override rows",
      play="Remove the <code>exhaustion_short</code> rows from "
           "<code>data/exit_overrides_proposed.json</code>. They were withdrawn once and the file "
           "still carries them.",
      mechanism="The chandelier variant sits at the 58th percentile of its own control on the same "
                "87 signals — i.e. it is indistinguishable from the control it was supposed to "
                "beat. The random-entry control is the named test.",
      rationale="A withdrawn proposal that stays in a proposal file is a live instruction to the "
                "next reader. Deleting the rows is the only thing that closes it — the same shape "
                "as the carve-out header in SATURDAY #4.",
      number="58th percentile of its own control on 87 signals.",
      section_ref="Part 2 §3 and the exhaustion_short battery; the random-entry control is named "
                  "there as the test that killed it.",
      verification="<code>grep exhaustion_short data/exit_overrides_proposed.json</code> returns "
                   "nothing.",
      arms_when="n/a.", exit="n/a.",
      kill="n/a — refuted by its own control.",
      suggested_mode="deploy", owner=OP,
      revert="git restore the file.", money_gbp=0),
]


def main() -> int:
    # A row whose whole instruction is "change nothing" must not print an owner, or the card
    # reads as if somebody has a job to do. Applied here rather than typed 18 times.
    for p in PLAYS:
        if p["suggested_mode"] == "no-op":
            p["owner"] = "Nobody — no change"

    seen, dupes = set(), []
    for p in PLAYS:
        if p["id"] in seen:
            dupes.append(p["id"])
        seen.add(p["id"])
    if dupes:
        raise SystemExit(f"FATAL — duplicate play id(s): {dupes}")

    required = ("id", "window", "rank", "topic", "tier", "play", "section_ref", "verification",
                "suggested_mode", "arms_when", "exit", "kill", "number", "owner", "revert")
    for p in PLAYS:
        miss = [k for k in required if not p.get(k)]
        if miss:
            raise SystemExit(f"FATAL — play {p['id']} is missing {miss}")

    # Ranks must be dense and start at 1 inside each window, or the card reads as if rows were
    # dropped — and the in-fragment pointers (BUILD #6/#8/#9) key off exactly this.
    by_win: dict[str, list[int]] = {}
    for p in PLAYS:
        by_win.setdefault(p["window"], []).append(p["rank"])
    for w, rs in by_win.items():
        if sorted(rs) != list(range(1, len(rs) + 1)):
            raise SystemExit(f"FATAL — {w} ranks are {sorted(rs)}, expected 1..{len(rs)}")

    pins = {("BUILD", 6): "shadow-ignition-confirmed-entry-0821",
            ("BUILD", 8): "entry-side-claim-study-0821",
            ("BUILD", 9): "populate-suppressed-by-0821"}
    at = {(p["window"], p["rank"]): p["id"] for p in PLAYS}
    for k, want in pins.items():
        if at.get(k) != want:
            raise SystemExit(f"FATAL — {k[0]} #{k[1]} is PINNED to {want} by a section fragment "
                             f"that cites it; it currently holds {at.get(k)}")

    pathlib.Path(OUT).write_text(json.dumps(PLAYS, indent=1, ensure_ascii=False) + "\n")
    for w in ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION"):
        print(f"  {w:<14} {len(by_win.get(w, []))}")
    print(f"plays.json → {OUT} ({len(PLAYS)} plays)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
