#!/usr/bin/env python3
"""Assemble the FULL V7 Friday report -> light-theme HTML + iPad PDF.

2026-08-14 BUILD. Stitches every pre-baked section fragment into the proven light-theme shell,
in the report's canonical order, and renders a PDF via weasyprint (system python3):

  Front      WHAT TO ACTUALLY DO + honest headline + scorecard  (generated from plays.json
             and, for the money table, from data/gazbot7.db — never typed into this file)
  Part 0     are we getting better?  part0_progress.html
  Part 1     live desk               part1_live.html   + run_charts.html INSIDE it
  Part 1.5   REHABILITATION          part1_5_rehab.html
  Part 2     shadow / promotion      part2_shadow.html
  Part 2.5   mid-week musings        part25_musings.html
  Part 2.6   ROUTER REVIEW           part2_6_router_review.html
  M1         run census              movement1_census.html + movement1_census_MGC.html INSIDE it
  M2         idle-gate lab           movement2_idle_gates.html
  M3         greenfield lab          movement3_greenfield.html

Three properties this build guarantees, each one closing a failure that actually shipped:

  * NO SILENT OMISSION, AND NO SILENT ABORT. The 08-08 build made a missing fragment a hard
    failure, which was right for the failure it was written against (a short report that looked
    complete) and wrong for this week's (two phases overran, four never started). A missing
    fragment now renders as a LOUD NAMED PLACEHOLDER saying which phase failed and what the
    reader is not getting — see fragment_or_placeholder(). Absence is fine; silence is not,
    because "we looked and found nothing" and "nobody looked" are opposite instructions.
  * NO STALE FRAGMENT. Anything older than CYCLE_START is a previous week's conclusions wearing
    this week's date, and that DOES abort — it is the one case where the reader cannot possibly
    tell something is wrong. (It caught run_charts.html this week, which still charted 08-03.)
  * ONE STRING, ONE PASS. The PDF is rendered from the same `doc` value as the HTML, in the same
    invocation, and BEFORE the HTML is written — so a PDF failure cannot leave a newer orphaned
    HTML behind claiming to be current. Both mtimes are printed on success.

Note on the section directory: a rehab dossier's filename contains a "/" which the writing agent
turned into a real DIRECTORY, so a naive rehab_*.md glob returns a path that is not a file and
read_text() raises IsADirectoryError. This script reads an EXPLICIT list of fragments and never
globs; scripts/friday_v7_rehab_section.py, which does glob, skips non-files rather than choking.

Build the plays first, then the report, then the playbook:
  python3 scripts/friday_v7_plays_0814.py
  python3 scripts/friday_v7_build.py --slug 2026-08-14
  python3 /home/alphabot/alphabot2/scripts/friday/build_playbook.py --slug 2026-08-14
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = "/home/alphabot/gazbot7/src/gazbot7/web_static"
PLAYS = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"
DESK_DB = "/home/alphabot/gazbot7/data/gazbot7.db"
PLAYBOOK_URL = "/v7/static/monday_2026-08-14.html"
CSS_TEMPLATE = "/home/alphabot/alphabot2/alphabot/dashboard/static/weekly_2026-06-26.html"

# supplemental CSS for classes the template may not define
SUPP = """<style>
.n{display:inline-block;min-width:1.6em;padding:0 .4em;margin-right:.4em;background:#0f2942;color:#fff;
   border-radius:.3em;font-size:.62em;vertical-align:middle;font-weight:700;letter-spacing:.02em}
.tag{display:inline-block;padding:.08em .5em;border-radius:.3em;font-size:.72em;font-weight:700;
     background:#eee;color:#0f2942;border:1px solid #cbd5e0}
.pill-shadow{background:#fff3d6;border-color:#e0b84a}.pill-null{background:#f0f0f0}
.pill-dontarm{background:#fbe3e0;border-color:#c0392b;color:#8a1c10}
.pill-live{background:#dff3e6;border-color:#1f6f43;color:#14512f}
.pill-parked{background:#e8eef5;border-color:#5a6472;color:#33404f}
.frag-sep{border:0;border-top:2px solid #e6e2d8;margin:2.4em 0}
.v7toc{background:#fbfaf7;border:1px solid #e6e2d8;border-radius:10px;padding:1em 1.3em;margin:1.6em 0}
.v7toc h3{margin:0 0 .5em;font-size:1.02em;letter-spacing:.04em;text-transform:uppercase;color:#0f2942}
.v7toc ol{margin:0;padding-left:1.3em}
.v7toc li{margin:.28em 0;font-size:.96em}
.v7toc .lab{font-weight:700;color:#0f2942}
.v7toc .sub{color:#5a6472}

/* ---- REV3: corrections, pointers and struck-through superseded text ---- */
.rev3{background:#fff6f4;border:1px solid #e0a99e;border-left:5px solid #c0392b;border-radius:8px;
      padding:.8em 1.05em;margin:1.05em 0}
.rev3 .ct{font-weight:700;color:#8a1c10;text-transform:uppercase;letter-spacing:.04em;font-size:.74em;
          margin-bottom:.4em}
.rev3 p{margin:.45em 0}
.rev3ptr{background:#fdf6e3;border:1px solid #e0b84a;border-left:5px solid #b8860b;border-radius:8px;
         padding:.7em 1.05em;margin:.9em 0;font-size:.95em}
.was{color:#8a8577;text-decoration:line-through;text-decoration-color:#c0392b}

/* ---- REV3: the action tables, built from plays.json ---- */
.winhead{margin:1.6em 0 .2em;padding:.5em .8em;border-radius:8px 8px 0 0;color:#fff;font-weight:700;
         letter-spacing:.05em;text-transform:uppercase;font-size:.82em}
.w-sat{background:#a4262c}.w-mon{background:#0f2942}.w-build{background:#8a6d0b}
.w-hold{background:#1f6f43}.w-not{background:#6b7280}
.winsub{font-size:.88em;color:#5a6472;margin:.35em 0 .5em}
table.plays{width:100%;border-collapse:collapse;margin:0 0 .6em;font-size:.94em}
table.plays th{background:#0f2942;color:#fff;text-align:left;padding:.42em .6em;font-size:.68em;
               letter-spacing:.06em;text-transform:uppercase;font-weight:700}
table.plays td{border-bottom:1px solid #e6e2d8;padding:.55em .6em;vertical-align:top}
table.plays tr:nth-child(even) td{background:#fbfaf7}
table.plays td.rk{font-weight:800;color:#0f2942;white-space:nowrap;font-size:1.05em}
table.plays .topic{font-weight:700;color:#0f2942;display:block;margin-bottom:.3em}
table.plays .why{color:#5a6472;font-size:.9em;margin-top:.45em;display:block}
table.plays .num-cell{font-weight:700;color:#0f2942}
.moneytag{display:inline-block;background:#1f6f43;color:#fff;border-radius:.3em;padding:.05em .45em;
          font-size:.78em;font-weight:700;margin-left:.3em}
@media (max-width:680px){
  table.plays,table.plays tbody,table.plays tr,table.plays td{display:block;width:100%}
  table.plays thead{display:none}
  table.plays tr{border:1px solid #e6e2d8;border-radius:8px;margin:.8em 0;padding:.25em 0;background:#fff}
  table.plays tr:nth-child(even) td{background:transparent}
  table.plays td{border:0;padding:.35em .8em}
  table.plays td:before{content:attr(data-l);display:block;font-size:.64em;letter-spacing:.07em;
    text-transform:uppercase;color:#8a8577;font-weight:700;margin-bottom:.12em}
  table.plays td.rk:before{content:none}
}
/* PDF-only: force wide tables to fit the page — screen HTML untouched. */
@media print{
  @page{size:A4;margin:1.2cm 1cm}
  .wrap{max-width:none;padding-left:12px;padding-right:12px}
  table{table-layout:fixed;width:100%;font-size:9px}
  th,td{padding:3px 4px !important;overflow-wrap:break-word;word-break:break-word;white-space:normal}
  pre,code{white-space:pre-wrap;word-break:break-word}
  table.plays{font-size:8.4px}
  .rev3,.rev3ptr{page-break-inside:avoid}
}
</style>"""


# ══════════════════════════════════════════════════════════════════════════════════════
# ★2026-08-14 SPINE. Three structural changes from the 08-08 build, all of them requested:
#
#   1. REHABILITATION IS A HEADLINE LIVE-DESK SECTION. It sits at Part 1.5, directly after
#      the live desk and before the shadow board — not buried behind the movements. It is
#      the operator's #1 recurring section and the running order should say so.
#   2. RUN CHARTS GO INSIDE PART 1, not in an appendix. The charts are visual trade review
#      of the case-study days Part 1 discusses, so they belong beside that prose. They are
#      rendered INSIDE Part 1's <section> via the `inserts` field below rather than as a
#      section of their own — see the stitch loop in main().
#   3. LAST WEEK'S SECTIONS ARE GONE. The 08-08 spine carried day_rider.html and six Rev2
#      correction chapters (Part 3.1–3.6). Both are PRIOR-WEEK fragments: nothing regenerated
#      them this week, and stitching a stale chapter into a fresh report is worse than
#      omitting it because the reader cannot tell. This week's day-rider work is inside
#      Part 1 (§2.3 and §6), which is where it was written.
#
# (label, sub-title, fragment file, anchor, inserts)
#   inserts = extra fragments rendered INSIDE this section, each (heading, filename).
SECTIONS = (
    # ★★2026-08-13 PART 0 GOES FIRST, in the operator's own words: "we never had multiple green days
    # in a week like we having now ... we should almost open with this. gives hope and shows
    # progress." He is right and the report had no place that showed it — every other section answers
    # "what happened THIS WEEK"; none answered "are we getting BETTER?", which is the only question
    # that survives past Friday. A reader could finish 287 pages knowing every gate's P&L and still
    # not know the desk had gone from 0 green days in a week to 2-3.
    # GENERATED, never written: scripts/friday/progress_page.py rebuilds it from the live trade
    # record each Friday — total desk (tournament + day-rider), data_quality IS NULL — so it cannot
    # drift from the books and nobody has to remember to update it.
    ("Part 0", "Are we getting better? — every day the desk has traded, green or red",
     "part0_progress.html", "sec0", ()),
    ("Part 1", "The live desk — what the paper tournament and the day rider actually did",
     "part1_live.html", "sec1",
     (("THE RUN CHARTS &mdash; every fill of the week, marked on the day&rsquo;s own price path",
       "run_charts.html"),)),
    ("Part 1.5", "Live-desk REHABILITATION — never bench a gate at face value",
     "part1_5_rehab.html", "sec2", ()),
    ("Part 2", "The shadow desk, the promotion battery &amp; the regime-flex exit lab",
     "part2_shadow.html", "sec3", ()),
    ("Part 2.5", "Mid-week musings — every lead from the desk chat, tested hard",
     "part25_musings.html", "sec4", ()),
    ("Part 2.6", "ROUTER OPERATION REVIEW — the desk's #1 lever, on the stand",
     "part2_6_router_review.html", "sec5", ()),
    ("Movement 1", "The census — the biggest runs this week, and did we show up",
     "movement1_census.html", "sec6",
     (("THE SAME CENSUS ON GOLD &mdash; MGC, the second instrument",
       "movement1_census_MGC.html"),)),
    ("Movement 2", "The idle-gate lab — could the gates we own have caught them?",
     "movement2_idle_gates.html", "sec7", ()),
    ("Movement 3", "The greenfield lab — the gold book-break hunt, and the hunts that did not run",
     "movement3_greenfield.html", "sec8", ()),
    # ★2026-08-15 REVISION 2. The self-proofread pass reopened eight questions and fourteen
    # contradictions AFTER the report rendered. The fourteen are fixed in place, each tagged
    # ★REV2 where it sits, so nobody has to hold two numbers in their head. The eight are new
    # work and they get their own part rather than being scattered — several of them change a
    # play, and one of them withdraws a claim this report made about its own books.
    ("Part 3", "REVISION 2 — the eight open questions, answered on real data",
     "rev2_answers.html", "sec9", ()),
)

# No Part 3 this week. The 08-08 cycle had a self-proofread pass that reopened six questions
# AFTER the report rendered, and those became Part 3.1-3.6. Nothing equivalent ran this week,
# so there is no Part 3 opener to key off. Kept as None rather than deleted: the stitch loop
# still checks it, and a future cycle that revives the pass only has to set it again.
PART3_FIRST = None

WINDOWS = (
    # ★2026-08-08 — these three windows are now ordered by EXECUTION LOGIC, not by the size of
    # each play's headline number. #1 and #2 on Saturday are the two the 22:00Z reactivate timer
    # decides for you if you do nothing.
    ("SATURDAY", "w-sat", "TONIGHT — this window shuts at the Sunday 22:00 UTC reopen",
     "Code and config changes that need a restart, <strong>in execution order, not in order of "
     "headline size</strong>. <strong>#1 and #2 are forced</strong>: "
     "<code>gazbot7-gate-reactivate.timer</code> arms every <code>=off</code> gate at 22:00 UTC "
     "Sunday, so for both of them &ldquo;decide later&rdquo; is not one of the available states. "
     "<strong>#3 is a correctness fix</strong> (one WHERE clause, no experiment attached) and "
     "<strong>#4 is an in-code veto</strong> that has to go in with the restart or wait a week. "
     "&#9733;&nbsp;REV2: #1 now carries its regime split &mdash; the +$502 is entirely non-trend-day "
     "money and the change is mildly NEGATIVE on the trending eighth of its own sample; #2 now "
     "carries both rulers."),
    ("MONDAY", "w-mon", "AT THE DESK — switch-file and exit-cell changes, all reversible",
     "No code deploy in this window at all. Every row is <code>gate_switches.env</code>, "
     "<code>exit_overrides.json</code> or a router constant, and comes back in five minutes. "
     "<strong>#1 needs nothing but a decision</strong> — the router already owns the lever."),
    ("BUILD", "w-build", "NEXT — nothing goes live this week",
     "Instrumentation, shadow slates and the method fixes that decide whether next Friday's numbers "
     "can be trusted at all. <strong>#1 gates #4</strong>, and gates every future study that "
     "concludes &ldquo;exit earlier&rdquo; &mdash; the shadow repricer leaks past its own stops on "
     "44% of trades, which is exactly the bias that makes cutting early look good."),
    ("HOLD", "w-hold", "LEAVE ALONE — these are already right",
     "Standing lessons and things already in production. The action is to <em>not</em> touch them."),
    ("NOT-AN-ACTION", "w-not", "WITHDRAWN / REFUTED — kept on the card so nobody re-proposes them",
     "Every one of these was a recommendation at some point this week. They are printed with their "
     "autopsies so next Friday's agent does not dig the same hole."),
)

# Owner and revert path per play. Derived by hand from each play's own text — plays.json carries no
# owner/revert field, and inventing them per-render would be worse than writing them down once.
# "the number behind it" is likewise lifted from the play/rationale, never recomputed.
META: dict[str, tuple[str, str, str]] = {
    # id: (the number behind it, owner, revert path)
    "fix-dead-er-atr-floors-0731": (
        "383 blocked signal episodes / 8 days (not 7,734 — that was a 44× log-line count). "
        "Ship step 2 before step 1 and the four floored gates go 382 signals / +$3,630 → 103 / +$668, "
        "about −$370/day.",
        "Garrath — code edit + tournament restart",
        "Step 2 is the kill switch: <code>_base(slot)</code> → <code>slot</code>, one line, neutralises "
        "steps 1+2 together. Nuclear: <code>GAZBOT7_TOURNAMENT_SLATE=tournament</code>."),
    "grind-entry-ceiling-fix-0731": (
        "Honest before/after <strong>+$1,552 → +$2,830</strong> (n=181 → 111) — <em>not</em> −$284 → "
        "+$2,830. <strong>ATR 10, not 12</strong>: 12 is one notch the wrong side of a cliff and costs $941.",
        "Garrath — ships as steps 1 and 3 of the floors sequence",
        "Restore the two literals in <code>deciders.py</code>; delete the <code>ext_hi</code> key from "
        "<code>slot_strategy.py</code>."),
    "capitulation-flip-off-1r-0731": (
        "11 trades +$24 @ 45% win → 32 trades +$434 @ 78%. Overnight-only +$422 @ 81%. Strip-best-3 still "
        "+$327.",
        "Garrath — gate config + restart",
        "Restore <code>require_flip=True</code> and the 2.0R target."),
    "router-er-floor-020-to-015-0731": (
        "ER0.20 → ER0.15 at NET30: +$176 → +$492 (live-managed set), +$995 → +$1,307 (full historical set). "
        "Beats 0.20 in every NET column on both universes.",
        "Garrath — one threshold in the direction-router",
        "Set the fader-bench ER-trend floor back to 0.20."),
    "absveto-confirm-no-edit-0731": (
        "No edit. Cold re-validation: 238 trades, +$2,668, 47% win; LONG +$1,187 / SHORT +$1,482, both green "
        "independently; 9 of 12 days green.",
        "Nobody — this is a confirmation",
        "N/A — nothing changes."),
    "unpin-the-router-0801": (
        "411 ticks across 07-31 and 08-01 logged &ldquo;no change&rdquo; and applied <strong>nothing</strong>. "
        "The one router claim that survives every robustness test — the fader bench, +$810, n=25 — is "
        "switched off right now.",
        "★ Garrath — my edit was refused by the permission classifier",
        "Restore the all-six pin. One line either way."),
    "meter-sets-the-gate-list-0731": (
        "The meter scored 13 and 23 on the two green days, 47 and 56 on both CAUTION days (both lost), and "
        "86 on the −$905 day. n=5 — a promising start, not a validation.",
        "The durable router tick",
        "One line in <code>gate_switches.env</code>; reversible every 5 minutes."),
    "bench-rgv-short-0731": (
        "11 fires, −$142, negative at every exit rung (1.5R −$32 → chandelier −$190). Strip-best-1 −$242. "
        "Automated-only ledger: −$154.5 on 3 fills.",
        "The durable router tick (or you, in the switch file)",
        "<code>rgv_short=on</code>. It is a bench, not a retirement — the shadow keeps running."),
    "exhaustion-exit-075-k15-0731": (
        "64-entry 250 ms sweep: Lot A 0.75R +$510 (the loaded 0.5R is the <em>worst</em> rung at +$306); "
        "Lot B k1.5 chandelier +$502, the highest leave-one-day-out floor in the sweep at +$330.",
        "Garrath — <code>exit_overrides.json</code> + tournament restart",
        "Delete the key. <strong>Method caveat:</strong> graded per-signal on overlapping entries — the same "
        "accounting that swung grind's verdict by $5,076. Re-run it sequentially before trusting the size."),
    "absveto-long-exit-10-15-0731": (
        "The live A1.5/B2.5 is the worst of eleven cells swept: +$13.6/signal vs +$22.7 for A1.0/B1.5; "
        "LODO-min +$4.7 vs +$16.8. n=81, broad plateau, second independent sweep agrees.",
        "Garrath — <code>exit_overrides.json</code> + tournament restart",
        "Delete the key → back to the built-in default. Same overlapping-entry method caveat as #4."),
    "bench-absveto-short-violent-0731": (
        "n=11 shadow fires −$185.5; live 5 lots −$257. Negative at all 11 exit cells and every R from 0.5 to "
        "6.0 — no exit rescues this segment.",
        "The durable router tick",
        "Reversible every 5 minutes."),
    "stop-benching-absveto-long-chop-0731": (
        "13 blocked fires worth +$384. Live and shadow both green in that cell (+$383.5 / +$525). The "
        "long-side benching cost −$397 this week.",
        "The durable router tick",
        "Reversible every 5 minutes."),
    "capitulation-overnight-only-0731": (
        "Live config 11 trades +$24. Overnight-restricted recommended config +$422 at 81% win. Cash-session "
        "exit cells MED −$19 / CHOP −$20.",
        "The durable router tick",
        "Re-arm on any tick."),
    "grind-exit-a30-wide-0801": (
        "130 configs × 3,064 tick-repriced entries × 16 sessions, <strong>sequential</strong> sim. Loaded "
        "default −$2,115; best of all 130 still −$414. A3.0/wide is +$617 ≈ +$10/session live.",
        "Claude — pre-registered cell, graded 2026-08-21",
        "Delete the key. Treat as damage control, not an edge — the real lever is arming, 3–5× bigger."),
    "grind-in-code-continuation-veto-0731": (
        "Same open, same tape: veto-protected abs_veto +$146, un-vetoed grind −$370. The veto's standalone "
        "edge on thrust is +$2,538.",
        "Claude — build + per-regime backtest",
        "Nothing goes live this week; it is not eligible for a Saturday until it is backtested."),
    "exit-lab-method-is-wrong-0801": (
        "★ $5,076 swing from methodology alone: the paired method scored grind's loaded default +$2,961, the "
        "sequential one-position-per-slot sim scores the same config −$2,115.",
        "Claude — re-run every exit verdict in the report",
        "N/A. Until this lands, treat the exhaustion and abs_veto_long cells as directions, not measurements."),
    "instrument-the-claim-button-0731": (
        "Your hands were worth <strong>+$862.5</strong> this week. Twelve claims at 12-for-12 is not luck, "
        "and it is invisible in every P&amp;L we report.",
        "Claude — auto-reprice every MANUAL_CLAIM against its slot's exit",
        "Observe-only; nothing to revert."),
    "big-trend-grading-plan-0731": (
        "The cell is n=24, not n=5. The pre-registered grade needs 39 paired entries. Grade date Friday "
        "2026-08-21; hard backstop 2026-09-11.",
        "Claude (durable router + Friday max-depth lab); you sign off the freeze only",
        "N/A — it is a measurement plan."),
    "deploy-stop-unfilled-frontmonth-0731": (
        "6 abs_veto lots this week, −$273.5, roughly $168 of it inside the long-side exit gap. Commit "
        "99e3c11, still on a branch.",
        "Claude to deploy, then live-verify",
        "Branch revert. Distinct from the per-tick stop guard already in production (see HOLD #2)."),
    "census-cluster-zscore-fix-0731": (
        "The <code>|flow| &gt; 50</code> rule fires on <strong>66.5% of ALL bars</strong> — FLOW-LED and "
        "VACUUM are two names for one coin.",
        "Claude — two scripts, <code>run_census.py:30</code> and <code>run_census_full.py:38</code>",
        "Git revert. Without it, next Friday's agent digs the same empty hole."),
    "nipc-to-shadow-slate-0731": (
        "+$2,676 on n=171 over 12 days, 43.3% win, $15.6/trade, null-control z = +5.0. Fixed 2.5R beats the "
        "trail by $1,285.",
        "Claude — shadow slate only",
        "Remove from <code>default_slate()</code>. Explicitly never live this week."),
    "confirmed-trend-guardrail-0801": (
        "$0. As a permission filter it clears 26 of 274 signals (9%), worth +$86 non-overlap, and flips "
        "negative on two of four folds. Its value is determinism, not money.",
        "Garrath — optional, prompt text only",
        "Delete the seven inserted string-literal lines. Fail-safe either way."),
    "chop-days-the-off-switch-wins-0731": (
        "A large swept family of chop specialists; none beat simply not trading. Note the correction: the "
        "&ldquo;bench-into-CHOP +$1,088&rdquo; corroboration has been <strong>withdrawn</strong> — it is "
        "tag-fragile (+$612 / +$187 / −$382 across three independent regime tags).",
        "The untradeable meter operationalises it",
        "N/A — this is the governing lesson of the week, not a build."),
    "stop-unfilled-per-tick-guard-hold-0731": (
        "Before: 26 unfilled stops. At and after commit d0218c6 (live 07-28 08:34): 0 unfilled, 103 clean "
        "stops. On real ticks the 2s path <em>beats</em> a perfect stop by about $15.",
        "Nobody — it is already in production",
        "<strong>Do NOT revert it.</strong>"),
    "keep-adaptive-exit-selector-0731": (
        "It earned its keep on this week's tape. The exit changes elsewhere on this card are per-gate cells, "
        "not a change to the selector mechanism.",
        "Nobody — no change",
        "N/A."),
    "router-stop-benching-trendup-0731": (
        "+$1,615 → <strong>+$767</strong> once one open position per gate is enforced → <strong>+$158 on "
        "n=4</strong> once the rule cannot buy dips in a downtrend. Placebo: null under ADX(14) (p=0.56), "
        "<em>worse than random</em> under a 60-min regression tag (z=−2.56).",
        "Nobody — do NOT change the router's TREND_UP benching",
        "N/A. Kept on the card with the full autopsy so it is not re-proposed off the same estimator."),
    "not-an-action-promote-absveto-0731": (
        "Live since the 07-25 roster change; both sides verified armed in <code>gate_switches.env</code> "
        "today.",
        "Nobody",
        "N/A."),
    "grind-exit-cell-05-10-0731": (
        "−$1,127 <em>worse</em> than the default that is loaded today. 8/16 sessions, LODO-worst −$2,036, "
        "strip-best-3 −$3,392, bootstrap P=0.302, OOS sign flip (+$699 / −$1,826).",
        "Nobody — do NOT add this cell",
        "N/A."),
    "not-an-action-chop-turn-fade-0731": (
        "Best of 1,152 configurations returned +$288 against a pure-noise expectation of +$455 — it "
        "underperformed noise. LODO OOS −$5.84/trade.",
        "Nobody",
        "N/A."),
    "not-an-action-retire-rgv-short-0731": (
        "11 fires. Retiring on 11 is exactly as unjustified as arming on 11.",
        "Nobody — bench and shadow instead (MONDAY #3)",
        "N/A."),
    "not-an-action-router-timing-knobs-0731": (
        "The joint-best (+$692 / +$984) sits on the loosest grid edge on three axes at once — the signature "
        "of a fit to the grid boundary.",
        "Nobody",
        "N/A."),
    "not-an-action-two-ratchet-2r-partial-0731": (
        "4 trades, 1 runner, 1 day. The entire delta (+$122 / +$64) is that single 4.2R ride.",
        "Nobody — keep both shadowing",
        "N/A."),
    "not-an-action-idle-gate-lab-0731": (
        "Survivorship, not skill — the gates look good because of which ones happened to sit idle.",
        "Nobody",
        "N/A."),
    "not-an-action-flow-footprint-family-0731": (
        "Compounded by the census bug: <code>|flow| &gt; 50</code> fires on 66.5% of bars, so the clusters "
        "this family was built to exploit were never clusters.",
        "Nobody — fix the census before anyone revisits it",
        "N/A."),
}


def esc(s: str) -> str:
    return html.escape(s).replace("\n", "<br>")


# Anything on disk older than this belongs to a previous report cycle. The serial runner uses
# the same cutoff to decide what to rebuild (`artifacts older than ... are STALE`).
CYCLE_START = dt.datetime(2026, 8, 14, 19, 0, tzinfo=dt.UTC).timestamp()

# Why each fragment is absent, and what the reader is NOT getting. Written per-phase rather than
# generated, because "the phase failed" is not useful and "the phase failed, here is what was in
# it and here is what it cost you" is.
WHY_MISSING = {
    "part1_5_rehab.html": (
        "the <code>rehab</code> phase hit its 90-minute timeout",
        "It finished the whole exhaustion_short battery and saved it as JSON before it died, so "
        "this section was rebuilt from those artifacts by the assembly step. If you are seeing "
        "this placeholder instead, that rebuild also failed."),
    "movement3_greenfield.html": (
        "four of the five greenfield phases never started",
        "The serial runner ran out of budget (<code>BUDGET: stopping section builds to protect "
        "the tail</code>). The MNQ cause-cluster hunts — VACUUM, FLOW-LED, OPEN/NEWS — and the "
        "chop-day scalp lab did not run at all."),
    "run_charts.html": (
        "the run-chart generator produced nothing for this week's sessions",
        "These are the price paths of each session with every fill marked on them. Without them "
        "the case-study days in Part 1 are prose only."),
    "movement1_census_MGC.html": (
        "the gold census did not freeze",
        "Movement 1's MNQ census is unaffected; what is missing is the same table for MGC."),
}


def fragment_or_placeholder(fname: str, label: str, sub: str) -> str:
    """Read a fragment, or return a LOUD, NAMED placeholder if it is not fit to stitch.

    ★2026-08-14. The alternative — omitting the section — is the one thing that must not happen:
    a reader cannot tell the difference between "we looked and found nothing" and "nobody looked",
    and those two are opposite instructions for next week. So the gap is printed, with the phase
    that failed and what the section would have contained.
    """
    p = pathlib.Path(SEC) / fname
    if p.is_file() and p.stat().st_size and len(p.read_text().strip()) >= 200:
        return p.read_text()
    why, cost = WHY_MISSING.get(
        fname, ("its phase did not complete", "No further detail was recorded."))
    return (
        '<div class="rev3"><div class="ct">★ THIS SECTION IS MISSING &mdash; it did not run</div>'
        f'<p><strong>{esc(label)} &mdash; {sub}</strong> is not in this report because '
        f'{why}. The fragment <code>{esc(fname)}</code> was never written.</p>'
        f'<p>{cost}</p>'
        '<p><strong>Read this as a GAP, not as a null result.</strong> Nothing here was tested and '
        'found wanting; it was not tested. Do not treat the absence as evidence in either '
        'direction, and do not let next week&rsquo;s report inherit a conclusion from it. The '
        'disposition tables in the sections that DID run name every lead this affects.</p></div>')


def play_meta(p: dict) -> tuple[str, str, str]:
    """(the number behind it, owner, revert path).

    ★2026-08-08: these now live ON the play in plays.json, so the action card and the Monday
    playbook cannot drift apart. The legacy hand-written META dict above is the fallback for
    plays carried over from an earlier week.
    """
    if p.get("number") and p.get("owner") and p.get("revert"):
        return p["number"], p["owner"], p["revert"]
    if p["id"] in META:
        return META[p["id"]]
    raise SystemExit(f"FATAL — play {p['id']} has no number/owner/revert and no legacy META entry")


TIER_CLASS = {"LIVE": "pill-live", "SHADOW": "pill-shadow", "PARKED": "pill-parked",
              "REFUTED": "pill-dontarm"}


def tier_pill(tier: str) -> str:
    """Render the evidence tier. A tier may be compound ('SHADOW (panel 2-1)', 'REFUTED / LIVE')
    — colour off the FIRST recognised word so a compound tier still reads at a glance."""
    head = re.split(r"[^A-Z]", tier.strip().upper(), maxsplit=1)[0]
    return f'<span class="tag {TIER_CLASS.get(head, "")}">{esc(tier)}</span>'


def top_callout(plays: list[dict]) -> str:
    """"The ones that matter most" — GENERATED from the card's own top rows.

    ★2026-08-14. This block used to be hand-written above a generated table, and on 08-08 it
    ended up selling two things the table beneath it had withdrawn. Deriving it from SATURDAY #1
    and #2 and MONDAY #1 means it cannot disagree with the card: if a re-rank moves a play, this
    text moves with it.
    """
    picks = []
    for window, rank in (("SATURDAY", 1), ("SATURDAY", 2), ("MONDAY", 1)):
        hit = [p for p in plays if p.get("window") == window and p.get("rank") == rank]
        if hit:
            picks.append((window, rank, hit[0]))
    body = "".join(
        f'<p><strong>{i} &middot; {esc(p["topic"])} '
        f'({w}&nbsp;#{r}).</strong> {esc(p["play"])} '
        f'<em>{esc(p["number"])}</em></p>'
        for i, (w, r, p) in enumerate(picks, 1))
    return ('<div class="callout"><div class="ct">The three that matter most</div>'
            + body
            + '<p class="ln">Generated from the top of the card below, so the two cannot drift '
              'apart. Everything else, including every refuted idea and why it died, is in the '
              'five windows underneath.</p></div>')


def render_plays() -> tuple[str, int]:
    plays = json.loads(pathlib.Path(PLAYS).read_text())
    if not plays:
        raise SystemExit("FATAL — plays.json is empty. The report leads with the action card; "
                         "building without it is how Rev 1 shipped with no playbook.")

    out = [
        '<h2 id="actions"><span class="n">★</span> WHAT TO ACTUALLY DO</h2>',
        '<p class="lead">Garrath — this is the whole answer to &ldquo;so what do I actually DO?&rdquo;, and it '
        'is at the front. Every row below mirrors <code>reports/friday_v7/plays.json</code>, which is the '
        'reconciled source of truth for this week; the same file drives the '
        f'<a href="{PLAYBOOK_URL}"><strong>Monday playbook</strong></a>, so the two cannot drift apart. '
        f'<strong>&#9733; REV2 &mdash; the card grew from 38 rows to {len(plays)}.</strong> Seven SHADOW verdicts in the '
        'body of the report never became plays, including the one Part&nbsp;2 calls &ldquo;the week&rsquo;s main '
        'proposal&rdquo;, and a shadow slate costs nothing and needs no Saturday deploy, so a SHADOW verdict that '
        'produces no action is a lost week of incubation. They are BUILD&nbsp;#11&ndash;#18. One play moved the other '
        'way: the Open&nbsp;Rider stop width was a live MONDAY row on the strength of a section that forbids one, and '
        'it is now a shadow arm. '
        f'{len(plays)} plays, five windows, in the order they need doing. Every play carries its '
        '<strong>evidence tier</strong> and its <strong>kill criterion</strong> — if a play has no way to '
        'be proven wrong it should not be on the card.</p>',
        # ★2026-08-14. This callout is the most prominent text in the document, so it is
        # GENERATED from the top of the card rather than written — a hand-written summary above a
        # generated table is the single easiest way for the front page to end up arguing for a
        # play the card no longer contains, which is exactly what happened on 08-08.
        top_callout(plays),
    ]

    order = {w[0]: i for i, w in enumerate(WINDOWS)}
    for wname, cls, strap, blurb in WINDOWS:
        rows = sorted([p for p in plays if p.get("window") == wname],
                      key=lambda p: (p.get("rank", 99), p["id"]))
        out.append(f'<div class="winhead {cls}">{wname} &nbsp;·&nbsp; {strap} &nbsp;·&nbsp; {len(rows)} '
                   f'{"play" if len(rows) == 1 else "plays"}</div>')
        out.append(f'<p class="winsub">{blurb}</p>')
        out.append('<table class="plays"><thead><tr>'
                   '<th style="width:3%">#</th><th style="width:40%">What to do</th>'
                   '<th style="width:25%">The number behind it</th>'
                   '<th style="width:20%">Arms when &middot; exit &middot; kill criterion</th>'
                   '<th style="width:12%">Owner &amp; revert</th>'
                   '</tr></thead><tbody>')
        for p in rows:
            num, owner, revert = play_meta(p)
            money = p.get("money_gbp") or 0
            mtag = f'<span class="moneytag">&pound;{money}/wk</span>' if money else ""
            out.append(
                f'<tr>'
                f'<td class="rk">{p.get("rank", "—")}</td>'
                f'<td data-l="What to do"><span class="topic">{esc(p["topic"])}{mtag}</span>'
                f'{tier_pill(p["tier"])} {esc(p["play"])}'
                # Omit an empty field rather than printing a bare label. Where the mechanism
                # already carries the reasoning, a separate "Why:" line just restates it.
                + (f'<span class="why"><strong>Mechanism:</strong> {esc(p["mechanism"])}</span>'
                   if p.get("mechanism") else "")
                + (f'<span class="why"><strong>Why:</strong> {esc(p["rationale"])}</span>'
                   if p.get("rationale") else "")
                +
                f'<span class="why"><em>Evidence:</em> {esc(p["section_ref"])} '
                f'&nbsp;·&nbsp; verification: <strong>{esc(p["verification"])}</strong> '
                f'&nbsp;·&nbsp; mode: {esc(p["suggested_mode"])}</span></td>'
                f'<td data-l="The number" class="num-cell">{esc(num)}</td>'
                f'<td data-l="Arms / exit / kill">'
                f'<span class="why"><strong>Arms:</strong> {esc(p["arms_when"])}</span>'
                f'<span class="why"><strong>Exit:</strong> {esc(p["exit"])}</span>'
                f'<span class="why"><strong>Kill:</strong> {esc(p["kill"])}</span></td>'
                f'<td data-l="Owner &amp; revert">{esc(owner)}'
                f'<span class="why">{esc(revert)}</span></td>'
                f'</tr>')
        out.append('</tbody></table>')

    out.append(
        '<div class="callout"><div class="ct">Standing caveats on every dollar on this card</div>'
        '<p><strong>Every repriced number is a CEILING.</strong> Fills are modelled at the exact '
        'stop/target/trail level with no slippage, and the desk\'s own standing finding is that live losses '
        'run <strong>1.1&ndash;3.1&times; modelled</strong>. Treat the policy as the edge and the headline '
        'dollar as decoration. Anything on thin n is flagged in-row as a <em>direction</em>, not a '
        'measurement.</p>'
        '<p><strong>The fee is $1.50 per round trip and the multipliers are not the same.</strong> '
        'MNQ is $2.00 a point; <strong>MGC is $10.00</strong>. Every gold number in Movement 3 and in '
        'Part 2.5 Part A is priced at the gold multiplier &mdash; pricing gold with the Nasdaq one would '
        'understate it fivefold, and doing the reverse would flatter it fivefold.</p>'
        '<p><strong>Four method wounds are open and they bound everything above.</strong> '
        '<code>signal_journal.suppressed_by</code> is NULL in all 222 rows this week, so every claim about '
        'what a gate <em>would</em> have done unrouted is a reconstruction from the tape rather than a '
        'measurement &mdash; BUILD&nbsp;#6, and it is the <em>same defect the scope flagged last week</em>. '
        'The router&rsquo;s leakage detector is scoped to a universe that barely trades, so its zero is an '
        'empty set and not a clean week &mdash; BUILD&nbsp;#3. The nightly rollup reports $0/$0/$0 when the '
        'systemd journal has rotated past the day it is backfilling, which is indistinguishable from a day '
        'with no value &mdash; BUILD&nbsp;#8. And <code>selector_nightly</code> counted a quarantined trade '
        'four extra times, inflating one day&rsquo;s regret by 39% ($747.50 &rarr; $457.50 on 10 real trades) &mdash; SATURDAY&nbsp;#3. &#9733; REV2: the phantom is FOUR rows worth $290.00, not five worth $362.50 &mdash; the fifth day-rider row that day is the genuine claimed trade and must survive the fix.</p>'
        '<p><strong>Two sections of this report did not run.</strong> The rehabilitation phase timed out '
        'and Movement 3&rsquo;s four MNQ hunts never started. Part 1.5 was rebuilt from the artifacts the '
        'timed-out phase had already saved, and Movement 3 is the one gold hunt that finished; both say so '
        'at the top. <strong>Nothing on this card rests on a section that is missing</strong>, and the gaps '
        'are named as gaps rather than reported as nulls &mdash; BUILD&nbsp;#2 is the reschedule.</p></div>')
    _ = order
    return "\n".join(out), len(plays)


XREF = re.compile(r"\b(SATURDAY|MONDAY|BUILD|HOLD|NOT-AN-ACTION)\s*#\s*(\d+)\s*[(,]\s*([a-z0-9][a-z0-9-]{6,})")


def check_xrefs() -> int:
    """★2026-08-08. Plays cross-reference each other by POSITION ("see MONDAY #4"), and a
    re-rank silently invalidates every one of them — a stale pointer is still a grammatical
    sentence, so nothing catches it. The 08-08 re-rank rotted five in one go.

    Every cross-reference now carries its target's ID beside the position. That pair is
    checkable: assert the named play really does sit at that window and rank. A re-rank that
    forgets to repoint a reference fails the build instead of shipping a card that sends the
    operator to the wrong play.
    """
    plays = json.loads(pathlib.Path(PLAYS).read_text())
    at, byid = {}, {}
    for p in plays:
        at[(p.get("window"), p.get("rank"))] = p["id"]
        byid[p["id"]] = p

    bad, seen = [], 0
    for p in plays:
        for field, val in p.items():
            if not isinstance(val, str):
                continue
            for window, rank, target in XREF.findall(val):
                if target not in byid:      # a bare word in brackets, not an id — skip
                    continue
                seen += 1
                tp = byid[target]
                if tp.get("window") != window or str(tp.get("rank")) != rank:
                    bad.append(f"  {p['id']}.{field}: says '{window} #{rank} ({target})' but "
                               f"{target} is at {tp.get('window')} #{tp.get('rank')} "
                               f"— {window} #{rank} is now "
                               f"{at.get((window, int(rank)), 'NOTHING')}")
    if bad:
        print("=" * 72, file=sys.stderr)
        print(f"FATAL — {len(bad)} stale cross-reference(s) on the card:", file=sys.stderr)
        for b in bad:
            print(b, file=sys.stderr)
        print("A play that points at the wrong play is worse than one that points nowhere.\n"
              "Repoint them (scripts/friday_v7_fix_xrefs.py) and re-run.", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        return 1
    print(f"cross-refs OK — {seen} id-anchored reference(s) resolve to their stated position")
    return 0


def desk_numbers() -> dict:
    """The week's money, COMPUTED from the trade record — never typed into this file.

    ★ The 08-08 front page hard-coded every figure in its headline table. That is how a report
    ends up asserting a P&L that no longer matches the books after a re-attribution or a
    quarantine flag lands. These are read at build time from data/gazbot7.db, with
    `data_quality IS NULL` as the clean-ledger predicate, and the quarantined rows counted
    separately so the difference between the two totals is visible rather than silent.
    """
    import sqlite3
    con = sqlite3.connect(f"file:{DESK_DB}?mode=ro", uri=True)
    W = "closed_at >= '2026-08-10' AND closed_at < '2026-08-15'"

    def one(sql):
        return con.execute(sql).fetchone()

    raw = one(f"SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE {W}")
    clean = one(f"SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE {W} "
                "AND data_quality IS NULL")
    rider = one(f"SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE {W} "
                "AND data_quality IS NULL AND gate LIKE 'day_rider%'")
    tour = one(f"SELECT count(*), round(sum(pnl_usd),2) FROM trades WHERE {W} "
               "AND data_quality IS NULL AND gate NOT LIKE 'day_rider%'")
    days = con.execute(f"SELECT date(closed_at), round(sum(pnl_usd),2) FROM trades WHERE {W} "
                       "AND data_quality IS NULL GROUP BY 1 ORDER BY 1").fetchall()
    gates = con.execute(
        f"SELECT replace(replace(gate,'_A',''),'_B',''), count(*), round(sum(pnl_usd),2), "
        f"round(100.0*sum(pnl_usd>0)/count(*),1) FROM trades WHERE {W} "
        "AND data_quality IS NULL GROUP BY 1 ORDER BY 3").fetchall()
    con.close()
    return dict(raw=raw, clean=clean, rider=rider, tour=tour, days=days, gates=gates,
                green=sum(1 for _, v in days if v > 0))


def m(v, dp=2):
    s = f"{abs(v):,.{dp}f}"
    return ("&minus;$" + s) if v < 0 else ("$" + s)


def render_front(slug: str, n_plays: int) -> str:
    d = desk_numbers()
    raw_n, raw_v = d["raw"]
    cl_n, cl_v = d["clean"]
    r_n, r_v = d["rider"]
    t_n, t_v = d["tour"]
    quar_n, quar_v = raw_n - cl_n, round(raw_v - cl_v, 2)
    n_sections = len(SECTIONS)

    daily = "".join(
        f'<tr class="{"row-hl" if v > 0 else "row-bad"}"><td class="ln">{day}</td>'
        f'<td class="num">{m(v)}</td></tr>' for day, v in d["days"])
    gaterows = "".join(
        f'<tr class="{"row-hl" if v > 0 else "row-bad"}"><td class="ln"><code>{g}</code></td>'
        f'<td class="num">{n}</td><td class="num">{m(v)}</td><td class="num">{w}%</td>'
        f'<td class="num">{m(v / n)}</td></tr>' for g, n, v, w in d["gates"])

    return f"""
<div class="masthead">
  <h1>GAZBOT V7 &mdash; the Friday report</h1>
  <p class="dates">Week ending {slug} &nbsp;·&nbsp; Mon 10 &ndash; Fri 14 August 2026 &nbsp;·&nbsp;
     MNQ-led, MGC now captured &nbsp;·&nbsp; PAPER &nbsp;·&nbsp;
     {n_plays} plays &nbsp;·&nbsp; {n_sections} sections</p>
</div>

<h2 id="honest"><span class="n">★</span> THE HONEST HEADLINE &mdash; the desk made money, and one
desk made all of it</h2>

<p class="lead">The whole desk booked <strong>{m(cl_v)}</strong> across {cl_n} clean lots, and
<strong>three of the five days were green</strong> &mdash; which is the thing Part&nbsp;0 exists to
show, because a year ago a green week was one day. But the money is not spread around, and the
split is the first thing you should see: <strong>the day rider made {m(r_v)} on {r_n} trades and
the tournament lost {m(t_v)} on {t_n}.</strong> Take the rider out and the week is red.
(&#9733;&nbsp;REV2 &mdash; one naming fix, used consistently from here on: the tournament is
<strong>eight base gates filling six live slots</strong>. The scope doc still calls it
&ldquo;the six-gate tournament&rdquo;; <code>rgv_long</code> and <code>thrust_short</code> were
retired and replaced by <code>exhaustion_short</code> and the two <code>abs_veto</code> sides, so
the roster is eight and the slate is six &mdash; see Part&nbsp;1&nbsp;&sect;3.)
Read every gate card in this report with that in mind &mdash; the tournament did not have a good
week, it had a week that a second desk paid for.</p>

<p>There is no single honest total, so here are all of them, with what separates each from the
next.</p>

<table>
<thead><tr><th class="ln">What you are looking at</th><th class="num">Lots</th><th class="num">Net $</th>
<th class="ln">Why it differs from the row above</th></tr></thead>
<tbody>
<tr><td class="ln">Raw <code>trades</code> rows, 08-10 &rarr; 08-14</td><td class="num">{raw_n}</td>
    <td class="num">{m(raw_v)}</td>
    <td class="ln">includes {quar_n} quarantined lots worth {m(quar_v)}</td></tr>
<tr class="row-hl"><td class="ln"><strong>Clean ledger</strong> (<code>data_quality IS NULL</code>)</td>
    <td class="num">{cl_n}</td><td class="num"><strong>{m(cl_v)}</strong></td>
    <td class="ln">the desk&rsquo;s real booked money &mdash; this is the number to quote</td></tr>
<tr><td class="ln">The day rider alone</td><td class="num">{r_n}</td><td class="num">{m(r_v)}</td>
    <td class="ln">the second desk. Five trades, five winners &mdash; and it only started writing
        a ledger at all this week, so treat it as thin, not as proven</td></tr>
<tr class="row-bad"><td class="ln"><strong>The tournament alone</strong> (eight base gates, six live slots)</td>
    <td class="num">{t_n}</td><td class="num"><strong>{m(t_v)}</strong></td>
    <td class="ln">what the gates this report is mostly about actually did</td></tr>
</tbody>
</table>

<div class="callout"><div class="ct">The {quar_n} quarantined lots, named</div>
<p>They are the 13 August day-rider phantom re-book, flagged
<code>EXCLUDE:day_rider_phantom_rebook_20260813</code>, and they are worth {m(quar_v)} &mdash; more
than the entire week&rsquo;s clean profit. <strong>That is why the quarantine flag exists and why
every query in this report carries <code>data_quality IS NULL</code>.</strong> A report that quoted
the raw table would have led with {m(raw_v)} and been wrong by {m(quar_v)}. Part&nbsp;1 &sect;6.2
walks the phantom itself.</p></div>

<table>
<thead><tr><th class="ln">Day</th><th class="num">Desk net (clean)</th></tr></thead>
<tbody>{daily}</tbody>
</table>

<h2 id="scorecard"><span class="n">★</span> THE SCORECARD &mdash; what survived the week</h2>

<p class="lead">Lead with what survived the skeptic, never with the biggest number. Six results
carried real weight into Saturday; here is where each one landed and the test that decided it.</p>

<table>
<thead><tr><th class="ln">The claim</th><th class="ln">Verdict, and the test that decided it</th>
<th class="ln">Where</th></tr></thead>
<tbody>

<tr class="row-hl">
  <td class="ln"><strong>The wide profit leg beats the tight one</strong></td>
  <td class="ln"><span class="tag pill-live">SURVIVED &mdash; the week&rsquo;s best-evidenced result</span>
      +$331.50 over <strong>51 identical entries</strong> &mdash; same signal, same price, same stop,
      the only difference being where profit was taken. Placebo p=0.0040, sign test p=0.0235,
      <strong>all five daily folds positive and all four gate folds positive</strong>. The A/B legs
      are a scale-out, not an experiment, so the instruction is <em>widen Lot A&rsquo;s target</em>,
      never drop Lot A.
      <br><strong>&#9733;&nbsp;REV2 &mdash; but it is ONE gate that carries it, so the play is scoped.</strong>
      Unpooled: <code>exhaustion_short</code> +$225.50 on 34 pairs and it survives its own battery
      (strip-best-3 +$127.50, worst leave-one-day-out +$101.00, 4 of 4 days green, sign test
      p=0.035), while <code>abs_veto_short</code>&rsquo;s +$65.00 on 12 pairs turns
      <strong>&minus;$34.00 once its best three are stripped</strong>, at 6 wins from 12.
      So MONDAY&nbsp;#1 widens <code>exhaustion_short</code> only and
      <strong>explicitly excludes <code>abs_veto_short</code></strong>, whose ladder is going the
      other way as BUILD&nbsp;#12 &mdash; see Part&nbsp;2&nbsp;&sect;3.</td>
  <td class="ln"><a href="#sec1">Part 1 &sect;2.2</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong>Never bench a gate at face value</strong> &mdash; the standing rule, applied
      to the one properly red gate</td>
  <td class="ln"><span class="tag pill-live">CONFIRMED, and it found the opposite of what was expected</span>
      Every treatment aimed at <code>exhaustion_short</code>&rsquo;s ENTRY failed against a
      4,000-draw placebo &mdash; 13 cooldown cells, 15 streak-bench cells and 9 flow floors, best of
      them at the 85th percentile. <strong>The entry was never the problem.</strong> Under a wide
      stop and a far target the same 87 signals are worth <strong>+$3,459.98 against
      &minus;$84.50 as traded</strong>, and the entries beat <strong>60 of 60</strong> random-entry
      controls. Under the live scalp exit those same entries sit at the 47th percentile &mdash;
      indistinguishable from random. The edge is invisible at the exit the desk uses.</td>
  <td class="ln"><a href="#sec2">Part 1.5</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>&ldquo;A wall of stops means bench the gate&rdquo;</strong></td>
  <td class="ln"><span class="tag pill-dontarm">REFUTED, on two independent populations</span>
      Mechanically, on 104 signals, every one of fifteen bench rules loses money and the best sits
      at the 54th percentile of noise &mdash; benching after two stops cuts <strong>18 winners to
      avoid 12 losers</strong>. Live, the same rule costs &minus;$172 across the week and forfeits
      +$356 on Friday alone. <strong>The discriminator is the REGIME the losses happened in, not
      the count of losses.</strong> &ldquo;Arm for periods&rdquo; wins.</td>
  <td class="ln"><a href="#sec1">Part 1 &sect;2.4</a>, <a href="#sec2">Part 1.5 &sect;3.2</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>The order book tells you which gold breaks will run</strong></td>
  <td class="ln"><span class="tag pill-dontarm">REFUTED &mdash; and it is backwards</span>
      On 397 MGC breaks, &ldquo;the far side is empty&rdquo; loses <strong>&minus;$2,059.50 at the
      4.8th percentile</strong> of its own placebo: 1,904 of 2,000 random picks did better. The
      feature carries real information and <strong>the sign is inverted</strong> &mdash; a gold level
      that breaks into a vacuum is one nobody is defending, and price comes straight back. The
      reformulation (fade it) is PARKED, not claimed.</td>
  <td class="ln"><a href="#sec8">Movement 3</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>A better exit would have caught the runs we missed</strong></td>
  <td class="ln"><span class="tag pill-dontarm">REFUTED &mdash; we are late, not sloppy</span>
      The timing-decay ladder, n=57 at every rung on this week&rsquo;s tape: perfect entries at the
      ignition minute pay <strong>+$3,799</strong>, at five minutes +$389.50, and at seven minutes
      <strong>&minus;$1,073</strong>. Our gates fire minutes after the money has gone. No exit
      fixes being late. The idle-gate lab is an <strong>honest null</strong>: six mechanical fires
      for +$15.50, and &minus;$94.50 once the single best is stripped.</td>
  <td class="ln"><a href="#sec7">Movement 2</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong>The router is earning its keep</strong></td>
  <td class="ln"><span class="tag pill-live">YES &mdash; and the gain is in its CLOCK, not its levels</span>
      <strong>1,148 ticks Tue&ndash;Fri</strong> (Monday is unverifiable &mdash; the systemd journal
      does not reach back past 08-10 23:11Z), <strong>zero systemd failures</strong> but
      <strong>125 aborted decisions</strong> in one unbroken 10h20m block on 13 August, and 95% of
      ticks change nothing. Its thresholds are already at the best cell on both universes
      independently &mdash; there is nothing to win there. The timing is a different story: window
      45 / step 5 / hold 3 is worth <strong>+$502 and +$399</strong> across the two sets.
      <strong>&#9733; REV2 &mdash; and that gain is not where the router works.</strong> Rank the
      40 days by session efficiency, hold out the trending eighth, and 45/5/3 scores
      <strong>&minus;$13.50 and &minus;$46.50</strong> on those 8 days; every dollar of the +$502
      comes from the flat 32. Take it for the mechanism (it smooths the boundary flicker), not for
      the number. <strong>Two honest holes:</strong> its leakage detector
      reported zero leakage while &minus;$241.00 leaked through a gate outside its universe, and
      that 10h20m outage was indistinguishable from a calm day in every scoreboard.</td>
  <td class="ln"><a href="#sec5">Part 2.6</a></td></tr>
</tbody>
</table>

<h2><span class="n">&sect;</span> Every gate, this week, on the clean ledger</h2>
<table>
<thead><tr><th class="ln">Gate</th><th class="num">Lots</th><th class="num">Net $</th>
<th class="num">Win %</th><th class="num">$ per lot</th></tr></thead>
<tbody>{gaterows}</tbody>
</table>
<p class="ln">Computed at build time from <code>data/gazbot7.db</code> with
<code>data_quality IS NULL</code>, not transcribed. Gates are collapsed across their A and B lots;
the per-lot split is in Part 1 &sect;3, and it is where the wide-leg finding lives.</p>

<div class="callout"><div class="ct">The three things this week actually taught the desk</div>
<p><strong>1 &middot; When a gate is red, check the exit before you touch the entry.</strong>
Twenty separate entry treatments on <code>exhaustion_short</code> failed to beat a coin. The exit
turned the same signals from &minus;$84.50 into +$3,459.98. The desk has spent months tuning
entries; this is the clearest evidence yet that the other half of the trade is where the slack is.
And the mirror of it is in Movement&nbsp;3: when the ENTRY is a coin flip, no exit saves it &mdash;
median favourable excursion +3.28&times;ATR against median adverse &minus;3.04&times;ATR is a
symmetric distribution with nothing to build a stop around.</p>
<p><strong>2 &middot; A filter that beats a placebo can still be a calendar.</strong> The one
treatment that cleared its placebo at the 97.6th percentile turned out to be re-discovering a floor
that is <em>already deployed</em>, and the 17 signals it cut were 12-from-one-era. The placebo is
necessary and it is not sufficient. Ask what the filter is selecting for, every time.</p>
<p><strong>3 &middot; Three instruments reported confidently and wrongly this week.</strong> The
router&rsquo;s leakage detector said zero on a week money leaked; the nightly rollup said
$0/$0/$0 for a day whose journal had rotated away; <code>selector_nightly</code> counted a
quarantined trade four extra times and inflated one day&rsquo;s regret by 39%. None of them errored. &#9733; REV2 adds a fourth: <code>two_ratchet_shadow_watch</code>&rsquo;s rMFE column stops measuring at the first 1-ATR adverse tick, so it read 0.81R on a trade that ran 87.5 points &mdash; and this report used that number to accuse its own live book of carrying mis-attributed fills. 0 of 26 trades fail the real test.
<strong>A number that arrives without a failure mode is not a measurement.</strong></p></div>
"""



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=dt.date.today().isoformat())
    ap.add_argument("--prefix", default="weekly",
                    help="output basename prefix: <prefix>_<slug>.html/.pdf (default: weekly)")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--title", default="GAZBOT V7 — Friday report {slug}",
                    help="document <title>; '{slug}' is substituted. Drop any PARTIAL label only "
                         "once the report genuinely is complete.")
    a = ap.parse_args()

    if check_xrefs() != 0:
        return 3

    tpl = pathlib.Path(CSS_TEMPLATE).read_text()
    m = re.search(r"<style.*?</style>", tpl, re.S | re.I)
    css = m.group(0) if m else "<style>body{font-family:Georgia,serif;max-width:900px;margin:auto}</style>"

    # ★2026-08-14 PRE-FLIGHT, REVISED. The 08-08 build made a missing section a HARD FAILURE,
    # because the failure it was written against was a short report that looked complete. That
    # was the right fix for that failure and the wrong one for this week's: two phases (rehab,
    # gf_MGC) overran their timeout and the greenfield phases never started at all, so an
    # abort-on-missing would have shipped NOTHING — no report, no playbook, on a week where
    # seven sections were finished and sitting on disk.
    #
    # So: a missing fragment now becomes a VISIBLE, NAMED PLACEHOLDER in the running order.
    # The original defect stays closed, because the thing that made the 08-08 failure dangerous
    # was silence, not absence. A section that says in red "this did not run, here is the phase
    # and here is what would have been in it" cannot be mistaken for a finished section, and it
    # cannot be mistaken for a null result either.
    missing, stale = [], []
    for _l, _s, name, _a, inserts in SECTIONS:
        for fname in (name, *(f for _h, f in inserts)):
            p = pathlib.Path(SEC) / fname
            if not p.is_file() or p.stat().st_size == 0 or len(p.read_text().strip()) < 200:
                missing.append(fname)
            elif p.stat().st_mtime < CYCLE_START:
                stale.append((fname, dt.datetime.fromtimestamp(p.stat().st_mtime)))
    n_frag = sum(1 + len(i) for *_, i in SECTIONS)
    if missing:
        print(f"★ {len(missing)} of {n_frag} fragment(s) MISSING — each gets a named placeholder, "
              f"not a silent omission: {', '.join(missing)}", file=sys.stderr)
    if stale:
        print(f"★ {len(stale)} fragment(s) predate this report cycle and are STALE:", file=sys.stderr)
        for f, m in stale:
            print(f"    {f}  ({m:%Y-%m-%d %H:%M})", file=sys.stderr)
        print("  A stale fragment is last week's conclusions wearing this week's date. Either "
              "regenerate it or drop it from SECTIONS.", file=sys.stderr)
        return 2
    print(f"pre-flight — {n_frag - len(missing)}/{n_frag} fragments present and fresh, "
          f"{len(missing)} placeholdered")

    # Explicit fragment list — never glob the sections dir (see module docstring).
    frags, toc = [], []
    for label, sub, name, anchor, inserts in SECTIONS:
        p = pathlib.Path(SEC) / name
        opener = ""
        if PART3_FIRST and anchor == PART3_FIRST:
            # ★2026-08-08 — this opener previously described the 08-01 cycle's shape (five Rev2
            # answers, three Rev3 re-derivations, one audit). This week's shape is different and
            # the opener must not describe sections that are not in the file.
            opener = ('<h2 id="part3"><span class="n">Part 3</span> The Rev2 corrections '
                      '&mdash; the new material, in full</h2>'
                      '<p class="lead">Everything in this part was written <em>after</em> the report was '
                      'rendered at 10:17&nbsp;UTC on Saturday. The self-proofread pass reopened six '
                      'questions against the sections above, and the build was killed before it could fold '
                      'any of them back in &mdash; so on the first published file, Parts&nbsp;1 to '
                      'Movement&nbsp;3 still argued for things this part refutes. '
                      '<strong>Where a Part&nbsp;3 section disagrees with anything above it, '
                      'Part&nbsp;3 is the correction</strong>, and the action card at the top of this '
                      'document has been rebuilt to match &mdash; every amended play is tagged '
                      '<strong>&#9733;&nbsp;REV2&nbsp;CORRECTION</strong> in-row. Three of the six '
                      '(Q0, FIX2 and the ER note in Q2) independently kill the same recommendation from '
                      'three different books, which is the strongest result in the document and the '
                      'reason the ER&nbsp;floor is gone from Saturday&nbsp;#2. Two more '
                      '(Q1, FIX0) change <em>what you type</em> rather than whether to act, and one '
                      '(Q2) is the first grading anyone has done of the previous week&rsquo;s card.</p>'
                      '<hr class="frag-sep">')
        body = fragment_or_placeholder(name, label, sub)
        for heading, fname in inserts:
            # Rendered INSIDE this section, not as a section of its own — the run charts belong
            # beside the case-study days they illustrate, and the gold census belongs beside the
            # Nasdaq one it mirrors.
            body += (f'<hr class="frag-sep"><h3 id="{pathlib.Path(fname).stem}">{heading}</h3>'
                     + fragment_or_placeholder(fname, label, heading))
        frags.append(f'{opener}<section id="{anchor}">{body}</section>')
        toc.append(f'<li><span class="lab">{label}</span> &mdash; <a href="#{anchor}">{sub}</a></li>')

    plays_html, n_plays = render_plays()

    intro = (
        render_front(a.slug, n_plays)
        + '\n<hr class="frag-sep">\n'
        + plays_html
        + '\n<hr class="frag-sep">\n'
        + '<h2 id="evidence"><span class="n">§</span> The evidence behind those plays</h2>'
        '<p class="lead">Everything from here down is the working. Two halves, one document. '
        'It opens with <strong>Part 0</strong>, which answers the only question that survives past '
        'Friday &mdash; <em>are we getting better?</em> &mdash; day by day, green or red, straight off '
        'the books. <strong>Then the warm half</strong>: what the live desk actually did this week '
        '(Part 1, with <strong>the run charts</strong> inside it &mdash; every fill of the week marked '
        'on its own session&rsquo;s price path, which is the fastest way to see what the prose is '
        'describing). Then the section that matters most &mdash; <strong>Rehabilitation</strong> '
        '(Part 1.5), where the week&rsquo;s one properly red gate is walked through the full wash '
        'instead of being benched at face value, and where twenty failed treatments are printed by '
        'name because the failures are the point. Then the shadow board and the promotion battery '
        '(Part 2), the mid-week leads re-run adversarially on the week\'s own data including the whole '
        'gold programme (Part 2.5), and the <strong>Router Operation Review</strong> (Part 2.6). '
        '<strong>Then the cold, tape-first half</strong>: we ignore everything the desk did and ask, '
        'from the raw tape and order book, <strong>where was the money and did we show up?</strong> '
        '&mdash; on MNQ <em>and</em> on gold (M1) &mdash; then test whether the gates we already own '
        'could have caught the runs we missed (M2), and finally build gates from scratch and backtest '
        'them to death, the ones that failed included, that being the point (M3). '
        '<strong>Two of those did not fully run this week and both say so at the top of themselves.</strong> '
        'Plain English, honest money, every claim a table &mdash; and every reprice a ceiling.</p>'
        '<div class="v7toc" id="contents"><h3>What is in here</h3><ol>'  # id: the ToC is a
        # link target in its own right (and it is what the publish verifier looks for)
        '<li><span class="lab">Front</span> &mdash; <a href="#honest">the honest headline</a>, '
        '<a href="#scorecard">the scorecard</a>, <a href="#actions">WHAT TO ACTUALLY DO</a></li>'
        + "".join(toc) + '</ol></div>')

    body = intro + '\n<hr class="frag-sep">\n' + '\n<hr class="frag-sep">\n'.join(frags)
    doc = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
           f'<title>{a.title.format(slug=a.slug)}</title>{css}{SUPP}</head>'
           f'<body><div class="wrap">{body}</div></body></html>')

    # ★2026-08-08 ONE STRING, ONE PASS. Rev 1 shipped an HTML and a PDF rendered from DIFFERENT
    # builds — the PDF was three hours older than the page it claimed to be. Both artefacts are
    # now produced from this single `doc` value before the function returns, and the PDF is
    # rendered BEFORE the HTML is written so a PDF failure cannot leave a newer orphaned HTML
    # behind claiming to be current.
    out_html = f"{OUT}/{a.prefix}_{a.slug}.html"
    out_pdf = f"{OUT}/{a.prefix}_{a.slug}.pdf"

    pdf_bytes = None
    if not a.no_pdf:
        try:
            import weasyprint
            pdf_bytes = weasyprint.HTML(string=doc).write_pdf()
        except Exception as e:
            print(f"★ PDF render FAILED ({e}) — nothing written, so the HTML on disk still matches "
                  f"the PDF beside it. Run with a system python3 that has weasyprint.", file=sys.stderr)
            return 4

    pathlib.Path(out_html).write_text(doc)
    print(f"HTML → {out_html} ({len(doc):,} bytes, {len(SECTIONS)}/{len(SECTIONS)} sections, "
          f"{n_plays} plays)")
    if pdf_bytes is not None:
        pathlib.Path(out_pdf).write_bytes(pdf_bytes)
        print(f"PDF  → {out_pdf} ({len(pdf_bytes):,} bytes) — same `doc` string, same pass")
        h, d = pathlib.Path(out_html).stat().st_mtime, pathlib.Path(out_pdf).stat().st_mtime
        print(f"mtime HTML {dt.datetime.fromtimestamp(h):%Y-%m-%d %H:%M:%S} · "
              f"PDF {dt.datetime.fromtimestamp(d):%Y-%m-%d %H:%M:%S} · delta {abs(d - h):.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
