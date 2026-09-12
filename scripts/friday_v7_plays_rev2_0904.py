#!/usr/bin/env python3
"""REV 2 (2026-09-04) — re-date the action card, stamp the shipped-check, and re-decide four rows.

★ WHAT THE PROOFREAD FOUND. The card was addressed to a weekend that had already gone: the window
headers read "SATURDAY · BEFORE THE SUNDAY 22:00Z REOPEN" and "MONDAY · AT THE DESK", MONDAY #1-#4
said "Arms: Monday", and BUILD #6 asked for an arming window that opened on 2026-08-31. Published
2026-09-04, those point four to six days into the past. 42 of the 54 rows carry a -0828 suffix and
the reader could not tell which were this weekend's work and which were last weekend's, unactioned.

★ WHAT THIS DOES, in order:
  1. Stamps every -0828 row with the verdict of scripts/rev2_shipped_check_0904.py (DONE / NOT DONE
     / CARRIED / STANDING) plus the one-line evidence, so nothing is re-issued blind.
  2. Re-dates every arms_when that named a date to the 2026-09-05/07 weekend.
  3. Inserts the weekend CARRY as SATURDAY #1 and demotes the rest — it is the only row with a
     deadline, and the deadline is Sunday's 22:00Z reopen.
  4. Re-decides four rows against evidence the report did not have: the abs_veto_55s promotion
     (an 8th ISO week, negative), the bench-saving figure ($810 retired -> $312.35), the off-tape
     artefact (one adjudicated figure, and it PERSISTED), and BUILD #6 (its window opened and the
     gate has traded).

  python3 scripts/friday_v7_plays_rev2_0904.py
"""
from __future__ import annotations

import json
import pathlib
import shutil

GB = "/home/alphabot/gazbot7"
PLAYS = f"{GB}/reports/friday_v7/plays.json"
SHIP = f"{GB}/reports/friday_v7/sections/rev2_shipped_0904.json"


def main() -> int:
    plays = json.loads(pathlib.Path(PLAYS).read_text())
    ship = {r["id"]: r for r in json.loads(pathlib.Path(SHIP).read_text())["rows"]}
    shutil.copy(PLAYS, PLAYS + ".pre-rev2-0904")
    by = {p["id"]: p for p in plays}

    # ── 1. the shipped-check stamp ────────────────────────────────────────────────────────────
    for p in plays:
        r = ship.get(p["id"])
        if r:
            p["shipped"] = r["verdict"]
            p["shipped_why"] = r["evidence"]

    # ── 2. re-date every arms_when that named the wrong weekend ───────────────────────────────
    for p in plays:
        a = p.get("arms_when", "")
        a = (a.replace("Monday at the desk", "Monday 2026-09-07 at the desk")
              .replace("Arms: Monday", "Arms: Monday 2026-09-07")
              .replace("Monday 2026-08-31", "Monday 2026-09-07")
              .replace("Saturday", "Saturday 2026-09-05")
              .replace("this weekend", "the weekend of 2026-09-05/06"))
        if a.strip() in ("Monday", "Monday.", "Monday at the desk."):
            a = "Monday 2026-09-07, at the desk."
        p["arms_when"] = a

    # ── 3. the weekend carry goes to the top of SATURDAY ──────────────────────────────────────
    # ★ RANK 0, NOT RANK 1. Renumbering the SATURDAY window would silently rot every
    # "SATURDAY #4 / #5 / #10" pointer in the document body — the exact failure check_xrefs()
    # exists to catch, and one this revision is fixing elsewhere. Rank 0 sorts first and breaks
    # nothing.
    plays.append(dict(
        id="weekend-carry-4-lots-0904", window="SATURDAY", rank=0, tier="LIVE",
        topic="★★★ FOUR RIDER LOTS ARE OPEN OVER THE WEEKEND — the only row on this card with a deadline",
        play="Nothing can be done before the venue comes back. At the <strong>Sunday 22:00Z reopen</strong>: "
             "get a venue read FIRST, confirm it says 4, and then decide FLAT or MANAGE deliberately — do not "
             "let the position drift into Monday by default, which is exactly what happened on 08-21 and cost "
             "&minus;$2,149.44. If the gateway is still refusing connections at 22:00Z, that is the whole "
             "decision: you are flat-blind and the position is unmanaged until it answers.",
        mechanism="<code>data/day_rider_state.json</code> reads <code>lots_open 4</code>, <code>closed false</code>, "
                  "LONG from <strong>29,641.25</strong>, <code>ahead_pt &minus;114.0</code>, "
                  "<code>flatten_blocked true</code>, <code>venue_ok false</code>, "
                  "<code>venue_net_ts 18:48:06Z</code>, note <code>ERROR (no action): TimeoutError</code>. "
                  "<code>desk_reconcile</code> reads <em>venue ? = tournament +0 + rider +4 &rarr; unaccounted ?</em> "
                  "with &ldquo;no venue read &mdash; IBKR truth unavailable&rdquo;. The watchdog has printed "
                  "<code>SKIP venue read failed</code> every two minutes since 18:48:50Z, and <strong>both</strong> "
                  "eod-flatten shots (20:53Z and 20:57Z) died inside the same <code>connectAsync</code> "
                  "TimeoutError. Port 4002 is refusing connections, so this is the gateway being DOWN, not the "
                  "04:28Z hang where the port stays open.",
        rationale="This is the identical mechanism as 2026-08-21, which is the largest single item in the "
                  "report body. Then, the position was &minus;121.93pt at the Friday close and &minus;267.93pt "
                  "when it was finally claimed by hand on the Monday: &minus;$2,149.44. Tonight it is "
                  "&minus;114.0pt at the close. <strong>The reopen itself is not the risk — the Monday is.</strong> "
                  "Across the seven Sunday reopens on tape the median gap is 22.25 points and the worst first "
                  "hour for a long is &minus;82.50pt (&minus;$660 on four lots); the 08-21 weekend gapped "
                  "+22.25 in the position's FAVOUR and still lost $2,149 by Monday lunchtime.",
        number="LONG 4 @ 29,641.25 · &minus;114.0pt = <strong>&minus;$912.00</strong> unrealised at the 21:00Z "
               "close. Sunday-reopen risk from 7 reopens on tape (capture.db 5s bars; the lake has NO Sunday "
               "partitions): median |gap| 22.25pt = $178 on 4 lots, worst gap DOWN &minus;21.25pt = "
               "&minus;$170, worst first hour for a long &minus;82.50pt = &minus;$660. Precedent 08-21: "
               "&minus;$2,149.44.",
        section_ref="Part 4 §1 (this revision) · the same mechanism as SATURDAY #5 (rider-hard-flat-sits-on-the-blackout-edge-0828) and Part 1.6 §6(a).",
        verification="At 22:00Z Sunday: <code>python3 -c \"import json;print(json.load(open('data/desk_reconcile_state.json')))\"</code> "
                     "must show a NUMBER in the venue field, not <code>?</code>. If it shows <code>?</code>, "
                     "the decision is unavailable and the position is unmanaged — say so out loud.",
        arms_when="Sunday 2026-09-06, 22:00Z reopen. Nothing before then: the market is shut and the venue "
                  "is unreachable.",
        exit="Your call, deliberately taken. FLAT is the low-variance choice and costs the &minus;$912 that "
             "is already marked; MANAGE keeps a position with no venue stop "
             "(<code>PLACE_VENUE_STOP = False</code>) through a session the desk cannot watch.",
        kill="If the venue read is still unavailable at 22:00Z, do not place a managing order into a book you "
             "cannot see. Wait for the read.",
        suggested_mode="Do it yourself. This one is not automatable tonight — the automation is what failed.",
        owner="★ Garrath — at the Sunday reopen",
        revert="N/A — this is a position, not a setting.",
        money_gbp=0,
    ))

    # ── 4a. MONDAY #1 — the promotion, re-decided with the 8th ISO week visible ────────────────
    p = by["promote-absveto55s-two-sided-0828"]
    p["topic"] = ("★ HOLD the abs_veto_55s promotion one more week — the 8th week of forward evidence "
                  "came in NEGATIVE and it tripped this row's own kill line")
    p["play"] = ("<strong>Do not promote this weekend.</strong> Leave <code>abs_veto_55s</code> in shadow, "
                 "both sides, and re-read it next Friday on n&nbsp;&asymp;&nbsp;500. Promote then only if the "
                 "LONG side is back above &minus;$5/trade over the trailing two weeks.")
    p["mechanism"] = ("The 08-28 report promoted this on <strong>n=433, +$5,302.50, +$12.25/trade, green in "
                      "7 of 7 ISO weeks</strong> and gave as its reason &ldquo;another week of FORWARD evidence "
                      "rather than another week of the same evidence&rdquo;. That week has now happened. "
                      "Re-run to 2026-09-04: <strong>n=464, +$4,876.50, +$10.51/trade</strong>. The unseen week "
                      "(W36, 08-31&rarr;09-04) is <strong>31 trades for &minus;$426.00 = &minus;$13.74/trade</strong>, "
                      "split LONG 18 at &minus;$346.50 (<strong>&minus;$19.25/tr</strong>) and SHORT 13 at "
                      "&minus;$79.50 (&minus;$6.12/tr). So it is 7 green weeks of 8, and "
                      "<strong>this row's own kill criterion — &ldquo;the LONG side below &minus;$5/trade&rdquo; — "
                      "is already tripped on evidence the report did not show.</strong>")
    p["rationale"] = ("The candidate is not refuted: all-time it is still +$10.51 a trade, the veto's "
                      "incremental edge over the un-vetoed <code>thrust_loose</code> is +$5,600 across the "
                      "board, and both regimes and both walk-forward halves stay green. But the stated reason "
                      "for promoting was forward evidence, the forward evidence arrived, and it argued the "
                      "other way. Promoting a candidate the week after its own kill line trips is how a desk "
                      "learns to ignore its kill lines. ★ Note also that a shadow mirror's stop is CLOSE-ONLY, "
                      "so its loss side is structurally understated — one more reason not to promote on the "
                      "shadow number alone.")
    p["number"] = ("All-time n=464, +$4,876.50, <strong>+$10.51/tr</strong> (was n=433 / +$5,302.50 / +$12.25). "
                   "W36 alone: 31 trades, &minus;$426.00, &minus;$13.74/tr, 19.4% win — LONG &minus;$19.25/tr. "
                   "ISO weeks green: <strong>7 of 8</strong>. Per-day 25/36 green.")
    p["kill"] = ("Already tripped once — the LONG side ran &minus;$19.25/trade in W36. Re-arm the promotion "
                 "only after two consecutive weeks with the LONG side above &minus;$5/trade.")
    p["arms_when"] = "NOT this weekend. Re-read Friday 2026-09-11."
    p["verification"] = ("Re-run <code>scripts/abs_veto_robustness.py</code> next Friday and print the ISO-week "
                         "row and the two-sided split before any promotion is proposed again.")
    p["tier"] = "SHADOW"

    # ── 4b. HOLD #1 — the bench saving, re-derived; and the refuted regime split removed ───────
    p = by["hold-the-chop-bench-0828"]
    p["play"] = ("Leave the policy exactly as it is: bench everything with no confirmed direction. "
                 "<strong>And stop quoting $810 &mdash; it is retired, not merely un-quotable.</strong> "
                 "If you must quote a number, it is +$312 with its band.")
    p["number"] = ("<strong>REVISED.</strong> 117 durable above-floor signals, bench saved "
                   "<strong>+$312.35 at the live stop (+$2.67/signal)</strong>; sign-stable across the "
                   "0.5&times;&ndash;1.5&times; sweep but DECAYING across it (+$624.59 &rarr; +$490.34 &rarr; "
                   "+$312.35 &rarr; +$73.29 &rarr; +$11.86). Two of five days carry 100% of the gross positive; "
                   "strip-3 leaves +$66.31; bootstrap &minus;$623.74 to +$1,208.31, "
                   "<strong>P(&le;0) = 0.253</strong>. Part 3 §Q4's independent floor: +$128. "
                   "The old +$810.44 / 127 signals is RETIRED — its population was counted off "
                   "<code>SUPPRESSED-OPEN</code> journal lines and the systemd journal is a ring buffer.")
    p["mechanism"] = ("Every above-floor impulse in <code>signal_journal</code> (durable on disk from "
                      "2026-08-04, unlike the journal) entered at the first tick at or after its own "
                      "timestamp and run forward on that gate's own live Lot-A exit, at five stop widths at "
                      "once with R pinned to the configured stop. <code>scripts/rev3_bench_replay.py</code>, "
                      "artifact <code>sections/rev3_bench_replay.json</code>. At the live width 65 of the 117 "
                      "stop out and 52 reach target.")
    p["rationale"] = ("The DIRECTION survives everything the desk can throw at it and the MAGNITUDE survives "
                      "nothing, which is the same verdict as before on a number that can actually be "
                      "reproduced. ★ What is GONE is the decomposition: &ldquo;the saving is entirely chop; "
                      "in aligned trend benching is FREE&rdquo; does not survive re-derivation — chop is "
                      "+$3.99 a signal (n=78) against aligned trend's +$3.37 (n=35), the same number, and a "
                      "10,000-draw label-shuffle placebo on the gap returns <strong>P = 0.943</strong>.")
    p["kill"] = ("Revive to a LIVE claim at ~350 signals or after one genuine TREND week. Kill the policy "
                 "outright only if the replay turns negative at the live stop width on a fresh week.")

    # ── 4c. HOLD #2 — its stated reason was the refuted sentence. Say what it now rests on ─────
    p = by["hold-arm-aggressively-in-aligned-trend-0828"]
    p["topic"] = ("Keep the router's aligned-momentum arm — but its stated reason is REFUTED, so it is now "
                  "held on judgement with no number behind it")
    p["number"] = ("<strong>The supporting number is withdrawn.</strong> &ldquo;50 benched signals, "
                   "&minus;$0.81 each&rdquo; came from the retired $810/127 population. On the durable "
                   "population the aligned-trend bucket is <strong>+$3.37 a signal over 35 signals</strong> "
                   "and the chop bucket +$3.99 over 78 — the same number — with a label-shuffle placebo at "
                   "<strong>P = 0.943</strong>. There is no measured regime split. What remains is 6 lots, "
                   "6 winners, +$330.00 in one 51-minute market event, which is n=1.")
    p["rationale"] = ("★ REV2, stated plainly: <strong>this arm is now held on judgement, not on evidence.</strong> "
                      "Its stated reason — that benching in aligned trend is free, so arming costs nothing — "
                      "was refuted by its own placebo. The honest case for keeping it is that it is the "
                      "operator's standing instruction of 2026-08-05 (&ldquo;if a huge trend develops you arm "
                      "gates immediately and let them run&rdquo;), that the one arm it produced was right, and "
                      "that no test has said it is WRONG. That is a reason to leave it alone; it is not a "
                      "reason to arm harder, and nothing on this card should cite the free-in-trend sentence "
                      "again.")
    p["kill"] = ("It has no live number to turn negative, so it cannot be killed by one. Re-open it when the "
                 "durable bench replay reaches ~350 signals and the aligned bucket can be measured against "
                 "chop with power. Until then: unchanged, uncited.")

    # ── 4d. HOLD #4 — ONE verdict on exit_overrides.json ──────────────────────────────────────
    p = by["hold-adaptive-exit-off-0828"]
    p["topic"] = "Leave adaptive_exit OFF — and leave data/exit_overrides.json alone. ★ Including the MED-TREND rung."
    p["play"] = ("Change nothing about the exit selector or the per-gate exit cells. <strong>This now "
                 "explicitly includes the grind MED-TREND branch that Part 2 §11 proposed deploying:</strong> "
                 "it is NOT deployed this weekend.")
    p["rationale"] = ("★ REV2 — the report gave two opposite instructions about one file on one Monday, and "
                      "this is the single verdict. They are different rungs and different bars: Part 2 §7.2 "
                      "grades <strong>grind MED-TREND</strong> PROVEN on a THREE-test bar (strip-3 +$5.60, "
                      "LODO +$6.20, both halves positive, +$7.70/signal on n=215, five adjacent cells positive), "
                      "while HOLD #4's &ldquo;20 of 20 failed&rdquo; is a FOUR-test bar that adds the "
                      "out-of-sample POOL split. MED-TREND is the one cell that clears three and fails the "
                      "fourth. <strong>Cause of death for the deploy, named: the out-of-sample leg.</strong> "
                      "Its V5 out-of-sample pool reads &minus;$4.50/signal on n=52, and its own live forward "
                      "arm has run &minus;$8.36/trade on n=21 since 08-16 against a control at &minus;$9.29 — "
                      "the whole rung is losing money live, in both configurations. The lab and the forward "
                      "arm agree on DIRECTION (paired on the 19 shared entries the proposal beats live by "
                      "+$60.50) and disagree on sign of the level, which is an entry problem wearing an exit "
                      "costume. Keep it in shadow with <code>rung_grindA_med_live</code> as referee.")
    p["number"] = ("19 of 20 rung-cells fail on three tests; <strong>20 of 20 fail once the out-of-sample "
                   "pool split is added</strong>. grind MED-TREND: lab +$7.70/sig (n=215) · V5 OOS "
                   "&minus;$4.50/sig (n=52) · live forward &minus;$8.36/tr (n=21) vs control &minus;$9.29/tr. "
                   "Selector vs fixed on the only live day: &minus;$600 vs +$799. "
                   "(The extended sweep is <strong>822,746</strong> five-second bars, not the 831,379 this "
                   "row used to print.)")
    p["kill"] = ("Deploy the MED-TREND branch when EITHER out-of-sample leg turns positive: the V5 pool above "
                 "$0/signal, or <code>rung_grindA_med_05</code> above its control over n&ge;40 forward trades. "
                 "Not before, and not on the in-sample lab number.")

    # ── 4e. SATURDAY off-tape — one figure, one window, one unit; and it PERSISTED ─────────────
    p = by["rider-off-tape-fills-0828"]
    p["topic"] = ("★★ The rider's off-tape residual leg — ONE adjudicated figure, and it is STILL HAPPENING "
                  "a week later")
    p["number"] = ("<strong>ONE figure, one window, one unit:</strong> report week 08-24&rarr;08-28 = "
                   "<strong>11 split orders / 15 residual legs / 18 lots / $1,053.50 = 66.8%</strong> of the "
                   "rider's &minus;$1,576.94. (Not the $1,170.50 / 74% / 12 events / 20 lots this row used to "
                   "carry, and not Part 1.6 §5's $734.50 / 47%.) "
                   "<strong>★ AND IT PERSISTED:</strong> re-run over 08-31&rarr;09-04 — the verification this "
                   "row itself asked for — gives <strong>7 split orders / 7 residual legs / 15 lots / "
                   "$876.00</strong>, every one of them adverse and <strong>0 of 7 on the tape</strong>. "
                   "That is 143% of the rider's whole +$613.50 week.")
    p["rationale"] = ("The audit this row asked for has now been run twice and the answer did not change: the "
                      "residual leg is priced at base &times; (1 &plusmn; 0.001), always adverse, at a price "
                      "the tape did not print within &plusmn;30 seconds. It is the largest single item on the "
                      "rider's book in both weeks and it is not a trading decision. Every leg carries a "
                      "distinct, correctly-formatted IBKR execId, so it is not obviously fabricated — but "
                      "0.001 appears nowhere in <code>src/gazbot7/</code>, which is the other half of the "
                      "question and still open.")
    p["verification"] = ("<code>PYTHONPATH=src .venv/bin/python scripts/rev3_offtape_audit.py</code> — the "
                         "08-31&rarr;09-04 window is now one of its printed cuts. A week with zero off-tape "
                         "legs is the fix landing.")

    # ── 4f. BUILD #1 — the #1 stone, answered rather than re-issued ────────────────────────────
    p = by["measure-absveto-short-trigger-lag-0828"]
    p["topic"] = ("★★ THE WEEK'S #1 STONE IS ANSWERED — abs_veto_short fired twice on 09-01 and won all four "
                  "legs, and the phase-gap fix would NOT have helped")
    p["play"] = ("<strong>Do not build the &ldquo;arm on break ONSET&rdquo; change.</strong> The lag is real "
                 "and large, but it runs the wrong way for that fix: the gate's own trigger is LATER than the "
                 "router's confirmation, so arming earlier buys idle armed time and nothing else. If anything "
                 "is built here it is the gate's <code>fast=True</code> start-of-move trigger, and that is a "
                 "separate row that does not exist yet.")
    p["mechanism"] = ("Measured on the 250ms tape, <code>scripts/rev2_break_onset_lag_0904.py</code>. "
                      "On 2026-09-01 the break's ONSET (the 60-minute swing high the move departed from) was "
                      "<strong>07:14Z at 29,556.50</strong>. The router's own confirmation trio "
                      "(ER-30 &ge; 0.35, ATR-14 &ge; 18, new session extreme) first read true at "
                      "<strong>08:06Z — 52 minutes later</strong>. The router armed the gate at "
                      "<strong>08:07:29Z, 1m29s after that</strong>. The gate then triggered at "
                      "<strong>08:39:57Z and 09:01:00Z</strong> — 32 and 54 minutes AFTER the arm, 86 and 107 "
                      "minutes after onset.")
    p["rationale"] = ("The 08-28 hypothesis was &ldquo;the router arms when a break is CONFIRMED; a thrust "
                      "gate needs the moment a break STARTS, and those were about 25 minutes apart&rdquo;. "
                      "On the two clean live cases the gap is bigger than 25 minutes — but the ROUTER is not "
                      "the late one. It armed 89 seconds after its own criterion went true. The gate then sat "
                      "armed and silent for another 32 minutes before it triggered. "
                      "<strong>Arming at onset would have armed it 52 minutes earlier and changed nothing: "
                      "the same two signals, at the same two times.</strong> And the trades were good — both "
                      "signals, four legs, <strong>+$163.50, 4 of 4 winners</strong>, entered 86 and 107 "
                      "minutes into a 328-point break. Entering late into a confirmed break was profitable, "
                      "which is the opposite of what the stone assumed.")
    p["number"] = ("2 signals / 4 legs / <strong>+$163.50</strong>, 4 of 4 winners, 2026-09-01. "
                   "onset 07:14Z &rarr; confirm 08:06Z (52m) &rarr; arm 08:07:29Z (+1m29s) &rarr; triggers "
                   "08:39:57Z and 09:01:00Z (+32m and +54m). Armed 3 times that day for a total 3h36m53s "
                   "and produced signals in only the first window.")
    p["verification"] = ("<code>PYTHONPATH=src .venv/bin/python scripts/rev2_break_onset_lag_0904.py</code> — "
                         "it prints the four clocks and the router's own switch writes for every "
                         "<code>abs_veto_short</code> signal since 08-31.")
    p["kill"] = ("The row's own kill line was &ldquo;if the measured lag is under ~5 minutes the hypothesis is "
                 "wrong&rdquo;. It is 86 minutes, so the LAG is real — but the DIRECTION refutes the fix, "
                 "which is the outcome the row could not have predicted. Closed on measurement, n=2.")
    p["tier"] = "MEASURED"
    # ★ It stays at BUILD #1. Moving an answered row to NOT-AN-ACTION would rot every "BUILD #1"
    # pointer in the body — and the body is where the reader meets the stone. The row keeps its
    # position and changes its verdict, which is what "answered" looks like on a card.

    # ── 4g. BUILD #6 — its window opened and the gate traded ──────────────────────────────────
    p = by["investigate-exhaustion-short-up-off-0828"]
    p["topic"] = ("exhaustion_short's arming window opened on 2026-08-31 and produced 2 fills — the row is "
                  "RE-ISSUED with its clock restarted, not repeated")
    p["play"] = ("Re-issue with a new window: <strong>arm from Monday 2026-09-07 to Tuesday 2026-09-22</strong>, "
                 "or 40 machine-exited fills, whichever comes first. The original window has closed with "
                 "<strong>2 of the 40 fills banked</strong>, which is not a grade.")
    p["number"] = ("Window opened 2026-08-31, closed 2026-09-04. Banked: <strong>2 machine-exited fills "
                   "(both TARGET, +$5.50 each, +$11.00 total)</strong>, on one signal at 2026-09-03 22:59:53Z. "
                   "That is 2 of the 40 the row asked for. The gate is <code>off</code> in "
                   "<code>data/gate_switches.env</code> right now, so the window is not currently running.")
    p["rationale"] = ("The row asked for 40 machine-exited fills or 2026-09-15, whichever came first. Five "
                      "sessions produced two. That is not evidence for or against the UP_OFF rule — it is a "
                      "duty-cycle problem, and re-issuing the same window unchanged would produce the same "
                      "answer. The &minus;$86 expected-cost estimate is unaffected because the gate barely "
                      "traded; it stands. ★ The one thing the window DID establish: the gate is not dead — "
                      "when it fires it exits on its own targets, and both did.")
    p["arms_when"] = "Monday 2026-09-07, at the desk — and it needs someone to actually turn it on."
    p["kill"] = ("If the second window also produces fewer than 10 machine-exited fills, withdraw the row: the "
                 "gate cannot be graded at this duty cycle and the UP_OFF question should be answered off the "
                 "shadow book instead.")
    p["verification"] = ("<code>grep exhaustion_short data/gate_switches.env</code> must read <code>on</code>, "
                         "and the fill count is <code>SELECT count(*) FROM trades WHERE gate LIKE "
                         "'exhaustion_short%' AND exit_reason NOT IN ('MANUAL_CLAIM')</code>.")

    # ── 4h. NOT-AN-ACTION #9 — scope the "dead heat" to the book it describes ─────────────────
    p = by["not-an-action-claim-button-0828"]
    p["topic"] = "Your Claim button — a dead heat on the TOURNAMENT, and the rider's biggest single exit"
    p["rationale"] = ("The individual lots were not close; the aggregate is a dead heat. ★ REV2 — and the "
                      "scope matters: this row is about the TOURNAMENT's three claimed lots. On the DAY RIDER, "
                      "the same button is the desk's main exit and Part 1.6 §4 scores it at "
                      "<strong>+$5,426.50</strong> this week. &ldquo;Dead heat&rdquo; is true of the "
                      "tournament and false of the desk. Part 1 §8's &minus;$75.14 is the Rev1 figure on a "
                      "modelled 23.5-point ATR; the +$4.50 here is the same three lots on the venue's own "
                      "24.25-point stop, and it supersedes it.")

    # ── 4i. MONDAY #2 — re-key the kill criterion to the ONE churn number ─────────────────────
    p = by["router-step-15m-to-5m-0828"]
    p["kill"] = ("If gate-VALUE changes per hour rise above ~1.0 — the desk's ONE churn metric, defined in "
                 "Part 1 §10: a gate's state flipping VALUE (not a write), Mon 00:00Z to Fri 22:00Z, all "
                 "three writers, over 118 elapsed hours. <strong>This week ran 0.237/hour</strong> (28 value "
                 "changes: 14 arms, 14 benches). The 0.18 this row used to quote was one of three retired "
                 "counts. Or if a 5-minute cadence starts producing arm/bench round trips with no intent in "
                 "between — revert and attack the confirmation appetite alone.")
    p["play"] = ("The tick grid is ALREADY 5 minutes (<code>OnCalendar=*:0/5</code>), so the only shippable "
                 "half of this row is the prompt line: <em>arm on the FIRST confirmed break impulse, not the "
                 "fifth</em>. ★ REV2 — and BUILD #1's measurement now argues it is worth less than it looked: "
                 "on 09-01 the router armed 89 seconds after its own confirmation criterion went true. The "
                 "confirmation APPETITE is not the binding constraint; the CRITERION is (52 minutes from break "
                 "onset to trio-true). Ship the prompt line, and treat the criterion as the next question.")

    plays = sorted(plays, key=lambda p: (p.get("window"), p.get("rank", 99), p["id"]))
    pathlib.Path(PLAYS).write_text(json.dumps(plays, indent=1))
    print(f"{len(plays)} plays written -> {PLAYS}")
    tal = {}
    for p in plays:
        if p.get("shipped"):
            tal[p["shipped"]] = tal.get(p["shipped"], 0) + 1
    print("shipped-check stamps:", tal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
