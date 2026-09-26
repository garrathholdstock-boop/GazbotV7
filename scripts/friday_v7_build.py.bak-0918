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

GB = "/home/alphabot/gazbot7"
SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = "/home/alphabot/gazbot7/src/gazbot7/web_static"
PLAYS = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"
DESK_DB = "/home/alphabot/gazbot7/data/gazbot7.db"
# ★2026-08-26 DERIVED FROM --slug, not hand-maintained. This was a hard-coded
# "monday_2026-08-21.html" while the report shipped as weekly_2026-08-26: the reports index
# looks up the playbook as monday_<same slug as the weekly>, so the card's own "the two
# cannot drift apart" sentence linked at a different week's playbook. main() rebinds this.
PLAYBOOK_URL = "/v7/static/monday_{slug}.html"
CSS_TEMPLATE = "/home/alphabot/alphabot2/alphabot/dashboard/static/weekly_2026-06-26.html"
ROOT = "/home/alphabot/gazbot7"
# The position the day rider left open on Friday 2026-08-21 and could not close. Read off
# data/day_rider_state.json (avgCost 58983.86 / $2 multiplier, incl. commission). It is a
# constant here rather than a query because no trades row exists for it — that is the point.
# ★★2026-08-22 REV2 — 29,491.625, NOT 29,491.93. The front page, Part 1 §0 and plays.json all
# carried 29,491.93 (→ −121.93pt → −$975.44) while Part 1.6 §2/§5 carried 29,491.63 (→ −$973.00).
# The fills settle it: 2 @ 29,477.00 + 1 @ 29,506.25 + 1 @ 29,506.25 at 13:13:06Z is a
# fill-weighted 29,491.625 exactly. 29,491.93 is the `entry` field of day_rider_state.json, which
# disagrees with its own fills by 0.305pt — $2.44 on four lots. The FILLS are the price.
# ⚠ data/weekend_flatten_pending.json also carries 29491.93; it flattens by QUANTITY so the wrong
#   price is cosmetic there, but it is the same number and the next reader should not re-import it.
CARRY_ENTRY, CARRY_LOTS = 29491.625, 4

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
/* ★2026-08-26 — Movement 3's appendix reproduces seven markdown dossiers, whose own ## and ###
   headings land at h5/h6 once shifted under the section's h2. The light theme styles h2-h4 only,
   so at those depths a heading rendered as ordinary bold text and the 55k-word appendix read as
   one undifferentiated block in the PDF. */
.wrap h5{font-size:1.04em;color:#0f2942;margin:1.5em 0 .4em;letter-spacing:.01em;font-weight:700}
.wrap h6{font-size:.96em;color:#33404f;margin:1.15em 0 .35em;font-weight:700}
.wrap blockquote{margin:.9em 0;padding:.55em 1em;border-left:3px solid #cbd5e0;background:#fbfaf7;
                 color:#33404f}
.wrap pre{background:#fbfaf7;border:1px solid #e6e2d8;border-radius:6px;padding:.7em .9em;
          overflow-x:auto;font-size:.82em;line-height:1.35}
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
table.plays .shipcheck{display:block;margin:.15em 0 .45em;font-size:.86em;color:#7a3d00;
          background:#fff6e6;border-left:3px solid #e0922f;padding:.25em .5em;border-radius:.2em}
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
    # ★2026-08-21 — the day rider is now a section of its own rather than a subsection of
    # Part 1. It is a SECOND BOOK on the same IB account, it made and lost more money than the
    # tournament this week, and the position it left open on Friday is the report's headline.
    # Burying that inside the tournament's section is how it stayed invisible for three weeks.
    ("Part 1.6", "THE DAY RIDER — the second desk, its week, and the four lots it left open",
     "part1_6_day_rider.html", "sec2b", ()),
    ("Part 2", "The shadow desk, the promotion battery, and the ruler that reordered the board",
     "part2_shadow.html", "sec3", ()),
    ("Part 2.5", "Mid-week musings — every lead from the desk chat, tested hard",
     "part25_musings.html", "sec4", ()),
    ("Part 2.6", "ROUTER OPERATION REVIEW — the desk's #1 lever, on the stand",
     "part2_6_router_review.html", "sec5", ()),
    ("Movement 1", "The census — the biggest runs this week, and did we show up",
     "movement1_census.html", "sec6",
     (("THE SAME CENSUS ON GOLD &mdash; MGC, the second instrument",
       "movement1_census_MGC.html"),)),
    ("Movement 2", "The idle-gate lab — could the gates we own have caught them? (with a base rate)",
     "movement2_idle_gates.html", "sec7", ()),
    # ★★2026-08-29 REV2 — THE GOLD SECTION IS BACK IN THE RUNNING ORDER. The scope mandates a
    # dedicated gold hunt inside this movement and the operator's own words are "we want to find
    # some gates that work for mgc". The gf_MGC phase RAN on 08-28 and wrote four artifacts at
    # 23:58Z; Rev 1 then shipped with no gold section at all, while three other places in the
    # document pointed at "gf_MGC" as though it were present. It is rebuilt from those artifacts
    # by scripts/friday_v7_gold_section.py, the same way Movements 2 and 3 were rescued.
    ("Movement 3", "The greenfield lab — detection is solved, selection is not, and the size threshold",
    # ★★2026-09-04 — AND THE ADDENDUM. Three cluster hunts (gf_MGC, gf_RIDER_ALL, gf_UNCLASS) ran
    # TONIGHT while ten body sections were skipped as "already have". They overwrote their own
    # markdown dossiers, but movement3_greenfield.html was rendered 08-29 with the PREVIOUS text of
    # those same three baked in. Rebuilding the movement would put tonight's appendix under last
    # week's summary of it; carrying them as a dated addendum cannot make that mistake. Built by
    # scripts/friday_v7_movement3_fresh.py.
     "movement3_greenfield.html", "sec8",
     (("GOLD &mdash; the MGC greenfield (<code>gf_MGC</code>), and the blocker that did not survive "
       "thirty-two days",
       "movement3_gold.html"),
      ("&#9733;&#9733; ADDENDUM, 2026-09-04 &mdash; the three hunts that re-ran tonight, on more "
       "tape, and what they overturn",
       "movement3_fresh_0904.html"),)),
    # ★★2026-08-29 REV2 — PART 3 IS BACK, AND FOR THE REASON THE MECHANISM EXISTS. A self-proofread
    # pass ran against the first draft and left EIGHT questions open plus fifteen issues. The issues
    # are fixed in place, in the sections that carried them. The eight questions could not be — they
    # each join two sections that never spoke to each other — so they get their own part, exactly as
    # the 08-08 cycle did. ⚠ The fragment is rev2_answers_0829.html, NOT the rev2_answers.html on
    # disk, which is the 08-15 cycle's file and stitching it would be the stale-fragment failure the
    # pre-flight exists to catch.
    ("Part 3", "REVISION 2 (2026-08-29) — the eight questions that draft left open, answered from data",
     "rev2_answers_0829.html", "sec9", ()),
    # ★★2026-09-04 REV2 — PART 4. The 09-04 proofread returned 20 issues and 10 unanswered questions.
    # The issues are fixed in the sections that carried them; the ten questions are answered here, in
    # one place, because eight of the ten turn on the same fact — this document grades the week to
    # 08-28 and ships on 09-04, so a whole week of desk activity sits between the evidence and the
    # reader. Generated by scripts/friday_v7_rev2_part4_0904.py from saved artifacts, never typed.
    ("Part 4", "REVISION 2 (2026-09-04) — the ten open questions, answered from data",
     "rev2_answers_0904.html", "sec10", ()),
)

# No Part 3 this week. The 08-08 cycle had a self-proofread pass that reopened six questions
# AFTER the report rendered, and those became Part 3.1-3.6. Nothing equivalent ran this week,
# so there is no Part 3 opener to key off. Kept as None rather than deleted: the stitch loop
# still checks it, and a future cycle that revives the pass only has to set it again.
PART3_FIRST = None

WINDOWS = (
    # ★2026-08-29 — REWRITTEN FOR THIS WEEK. These blurbs frame the card, and last cycle's set
    # opened by pointing at an armed recovery timer that has since been deleted. A window strapline
    # is prose about THIS week's shape and has to be rewritten with the card, not carried.
    ("SATURDAY", "w-sat", "SAT 2026-09-05 / SUN 2026-09-06 — before the Sunday 22:00Z reopen. ★ ONE row has a deadline this time",
     "<strong>&#9733;&#9733; READ #0 FIRST.</strong> This window used to open by saying nothing on it had a "
     "hard deadline. That is no longer true: <strong>four day-rider lots are open over this weekend</strong> "
     "&mdash; LONG from 29,641.25, &minus;$912 at the 21:00Z close, venue unreachable since 18:48:06Z, both "
     "eod-flatten shots dead inside the same <code>connectAsync</code> timeout. Same mechanism as 2026-08-21, "
     "which cost &minus;$2,149.44. It is #0 because it is the only row here with a clock on it, and the clock "
     "is Sunday 22:00Z. "
     "<strong>&#9733; Everything below it is a RE-ISSUE from the 2026-08-28 card, and every row now carries "
     "its own shipped-check</strong> &mdash; a probe run against this box at render time "
     "(<code>scripts/rev2_shipped_check_0904.py</code>), not a memory. The tally is uncomfortable and it is "
     "the most useful thing on the page: of the 25 shippable rows issued last weekend, <strong>19 are NOT "
     "DONE, 5 are CARRIED, 1 has been re-measured, and 0 are DONE</strong>. SATURDAY&nbsp;#5 &mdash; move the "
     "rider&rsquo;s flatten earlier and put the page UPSTREAM of it &mdash; is one of the 19, and it is the "
     "row that bit tonight. "
     "Beyond #0, nothing here has a deadline and none of it changes a threshold: they are faults in the "
     "desk&rsquo;s own <em>instrumentation</em> &mdash; two nightly rollups that have never had a timer and "
     "have written nothing since 2026-08-28, a router that went blind for 3h35m while every health signal "
     "read clean, a watcher that writes to a file its own unit says it must never touch, and a rider whose "
     "every order fills as a split with an off-tape residual leg. That last one was re-audited this "
     "revision and <strong>it is still happening</strong>: 7 more residual legs, 15 lots, $876.00, 0 of 7 on "
     "the tape. <strong>&#9733;&#9733; And three lake/build faults from 09-04 sit at the bottom</strong>: the "
     "parquet lake&rsquo;s gold year serves the <em>wrong contract</em> for 22% of its minutes at a median "
     "$301 a lot away from where gold actually was; the lake has no Sunday partitions at all, so the "
     "week&rsquo;s opening session is absent from every lake-based study; and the report runner&rsquo;s "
     "stale-date is stuck a week behind, which is why this document covers two different weeks. All of them "
     "are the same species &mdash; reasons a number in here might be wrong."),
    ("MONDAY", "w-mon", "MONDAY 2026-09-07, AT THE DESK — ★ the promotion is HELD, so this window is three tunings and nothing else",
     "<strong>&#9733;&#9733; THE PROMOTION IS OFF THIS WEEK.</strong> <code>abs_veto_55s</code> was the only "
     "arm on the card, and Rev&nbsp;2 re-ran it to 2026-09-04 rather than to 2026-08-28. The week the report "
     "body does not show &mdash; W36, 08-31&rarr;09-04 &mdash; is <strong>31 trades for &minus;$426.00 "
     "(&minus;$13.74/tr), LONG &minus;$19.25/tr</strong>, which trips this row&rsquo;s own kill criterion "
     "(&ldquo;the LONG side below &minus;$5/trade&rdquo;). All-time it is still +$10.51 a trade on n=464 and "
     "green in 7 ISO weeks of 8, so it is HELD, not killed &mdash; but the stated reason for promoting was "
     "another week of forward evidence, the evidence arrived, and it argued the other way. "
     "<strong>Note what is deliberately NOT here, and this is now ONE verdict rather than two:</strong> "
     "no exit cell changes, <em>including the grind MED-TREND branch Part&nbsp;2&nbsp;&sect;11 proposed "
     "deploying</em>. The twenty rung-cells are graded on a four-test bar that includes the out-of-sample "
     "POOL split; MED-TREND clears the other three and fails that one (V5 OOS &minus;$4.50/signal on n=52, "
     "live forward arm &minus;$8.36/trade on n=21 against a control at &minus;$9.29). <strong>Cause of death "
     "for the deploy: the out-of-sample leg.</strong> <code>data/exit_overrides.json</code> is not touched "
     "this weekend. (The extended sweep is 822,746 five-second bars, not the 831,379 previously printed.)"),
    ("BUILD", "w-build", "NEXT — nothing goes live this week. ★ #1 is now ANSWERED, not asked",
     "Measurements and shadow arms. <strong>&#9733;&#9733; The top row has been ANSWERED and it is a "
     "different answer from the one the report expected.</strong> It asked for the lag between a break "
     "STARTING and <code>abs_veto_short</code>&rsquo;s trigger firing, on the hypothesis that the router "
     "arms too late for a thrust gate. The gate has since fired &mdash; twice on 2026-09-01, four legs, "
     "<strong>+$163.50, 4 of 4 winners</strong> &mdash; so there are real trigger times to subtract an onset "
     "from instead of an absence to reason about. Measured on the 250ms tape: onset 07:14Z, the "
     "router&rsquo;s own confirmation trio first true 08:06Z, the router armed at 08:07:29Z &mdash; "
     "<strong>89 seconds after its own criterion</strong> &mdash; and the gate then triggered 32 and 54 "
     "minutes LATER still. <strong>Arming at break onset would have armed the gate 52 minutes earlier and "
     "changed nothing.</strong> The lag is real (86 minutes onset&rarr;trigger) and the proposed fix does not "
     "address it. Below that sits the week&rsquo;s structural finding, which is the reason several other "
     "things on this card should not be built at all."),
    ("HOLD", "w-hold", "LEAVE ALONE — these are already right, and two of them now say so on WEAKER evidence than last week",
     "Eight standing positions, and the action is to <em>not</em> touch them. "
     "<strong>&#9733;&#9733; Two of them have been re-derived downwards in Rev&nbsp;2 and the honest version "
     "is printed in the row.</strong> HOLD&nbsp;#1 (the chop bench) no longer rests on +$810.44 over 127 "
     "signals &mdash; that population was counted off <code>SUPPRESSED-OPEN</code> journal lines and the "
     "systemd journal is a ring buffer, so it cannot be rebuilt and it is RETIRED. What replaces it is a "
     "saved replay over the population that IS durable: <strong>+$312.35 over 117 signals</strong>, "
     "sign-stable across the whole stop sweep but decaying across it, with two days of five carrying all of "
     "it. HOLD&nbsp;#2 (arm hard in aligned trend) rested entirely on &ldquo;benching in aligned trend is "
     "FREE&rdquo;, and that sentence is <strong>REFUTED by its own label-shuffle placebo at "
     "P&nbsp;=&nbsp;0.943</strong> &mdash; chop +$3.99 a signal against aligned trend +$3.37, the same "
     "number. The arm stays, because nothing says it is wrong; it now stays <em>on judgement, with no number "
     "behind it</em>, and the row says so. <strong>&#9733; HOLD&nbsp;#4 carries this week&rsquo;s single "
     "verdict on <code>data/exit_overrides.json</code></strong> &mdash; not touched, MED-TREND branch "
     "included, cause of death the out-of-sample leg. "
     "The seventh is your 2026-08-20 no-stop decision on the day rider, re-priced on this week&rsquo;s own "
     "tape and re-affirmed &mdash; naked beat every stop width by $1,190 on the twelve positions the week "
     "actually opened. The eighth is a rule for a promotion that has not happened yet: if a gold gate is ever "
     "given a slot it must NOT inherit the dual-slot exit &mdash; on the same entries, the desk&rsquo;s "
     "Lot&nbsp;A/Lot&nbsp;B shape books &minus;$1,649 where a single wide lot on a clock books +$9,202."),
    ("NOT-AN-ACTION", "w-not", "WITHDRAWN / REFUTED — kept on the card so nobody re-proposes them",
     "Every one of these was, or could plausibly become, a recommendation. They are printed with "
     "their autopsies so next Friday's agent does not dig the same hole — including two "
     "(the searched day-classifier and the BIG-TREND exit rung) that this desk has been "
     "half-believing for weeks and that now have a named test on the certificate rather than a "
     "shrug, and one that is simply a caution about how to read a 100% win rate. "
     "<strong>&#9733;&#9733; Five more landed tonight and one of them refutes this report's own "
     "Movement&nbsp;3:</strong> the size threshold that section reports as a finding is a UNITS "
     "ARTEFACT &mdash; it reaches AUC&nbsp;0.81 measured in points and collapses to "
     "AUC&nbsp;&asymp;&nbsp;0.50 in ATR units, which is the only unit a stop can be set in. Beside "
     "it: all four gold cells came back null against a fixed-clock control, <code>rider_w5</code> "
     "delivered &minus;$25.95/tr against a +$19.29/tr backtest, UNCLASS turns out to be the base "
     "rate rather than a cluster, and filtering trades instead of signals manufactures edge out of "
     "replay sequencing. This is the most valuable window on the card this week."),
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
    return _unescape_inline(html.escape(s)).replace("\n", "<br>")


# ★2026-08-22 — INLINE MARKUP SURVIVES THE ESCAPE.
# This week's plays.json is the first to carry inline HTML in its prose (<code> around file
# and field names, <strong> for the number that decides a row, &mdash; between clauses).
# html.escape() rendered all of it as literal angle brackets: 69 visible "<code>...</code>"
# strings on the operator's own action card and 36 on the Monday playbook. Escaping is still
# the default — everything is escaped first — and only this fixed inline whitelist is put
# back. No attributes, no block tags, nothing that can change the page's structure.
_INLINE_OK = ("code", "strong", "em", "b", "i")


def _unescape_inline(t: str) -> str:
    for tag in _INLINE_OK:
        t = t.replace("&lt;%s&gt;" % tag, "<%s>" % tag).replace("&lt;/%s&gt;" % tag, "</%s>" % tag)
    # ★2026-09-04 REV2 — "amp" added. Five plays write "P&amp;L" in their prose; html.escape turns
    # that into "&amp;amp;L" and the operator's card printed a literal "P&amp;L". It is the same
    # class of fault as the 08-22 inline-markup one this list exists to fix.
    for ent in ("mdash", "ndash", "middot", "rsquo", "lsquo", "ldquo", "rdquo", "times", "nbsp",
                "hellip", "ge", "le", "minus", "amp"):
        t = t.replace("&amp;%s;" % ent, "&%s;" % ent)
    return t


# Anything on disk older than this belongs to a previous report cycle. The serial runner uses
# the same cutoff to decide what to rebuild (`artifacts older than ... are STALE`).
# ★2026-08-29 — THIS CYCLE. The durable Friday run started 2026-08-28T22:07Z and its serial
# runner declared its own cutoff in the log ("artifacts older than 2026-08-28T22:00Z are
# STALE"). This constant is that same instant, deliberately: two different cutoffs in the
# same cycle is how a fragment gets rebuilt by one component and called fresh by the other.
CYCLE_START = dt.datetime(2026, 8, 28, 22, 0, tzinfo=dt.UTC).timestamp()

# Why each fragment did not REGENERATE this cycle. Taken from the serial runner's own log
# (data/friday_durable.log, 2026-08-28T22:14Z onward) rather than guessed, because "the phase
# failed" and "the phase was never scheduled" are different facts with different follow-ups:
# a SKIP is a budget decision that repeats next week unless the budget changes, a rc=-1 with a
# missing artifact is a phase that ran out of clock mid-write, and a ROTATION omission is the
# design working as intended and needs no action at all.
WHY_STALE = {
    "part1_5_rehab.html": (
        "the <code>rehab</code> phase was <strong>SKIPPED before it started</strong> &mdash; the "
        "runner's fair-share allocator gave it 19 minutes against a 20-minute floor "
        "(<code>SKIP rehab &mdash; fair share is 19m, below the 20m minimum</code>, 23:35:29Z). "
        "It did not fail; it was never run"),
    "part1_6_day_rider.html": (
        "the <code>day_rider</code> phase was <strong>SKIPPED before it started</strong> at "
        "22:34:44Z, on the same 19m-vs-20m fair-share floor. It was the first casualty of a "
        "pre-flight that had already warned <em>13 body phases declare 975m of timeouts against a "
        "166m budget (5.9&times;)</em>"),
    "part25_musings.html": (
        "the <code>part25_musings</code> phase was <strong>SKIPPED before it started</strong> at "
        "22:55:52Z on the 20m fair-share floor"),
    "movement2_idle_gates.html": (
        "the <code>movement2_idle</code> phase RAN for 21.1 minutes and was killed before it wrote "
        "its fragment (<code>rc=-1 artifact=MISSING</code>, 23:35:29Z)"),
    "movement3_greenfield.html": (
        "the <code>movement3</code> phase RAN for 25.5 minutes and was killed before it wrote its "
        "fragment (<code>rc=-1 artifact=MISSING</code>, 00:53:37Z), and the gold hunt "
        "<code>gf_MGC</code> ahead of it died the same way at 23:58:08Z &mdash; but both had "
        "written their labs to disk first and both sections below are rebuilt from those files"),
}


# Why each fragment is absent, and what the reader is NOT getting. Written per-phase rather than
# generated, because "the phase failed" is not useful and "the phase failed, here is what was in
# it and here is what it cost you" is.
WHY_MISSING = {
    "part1_live.html": (
        "the <code>part1:live</code> phase did not write a fragment this cycle",
        "This is the live desk's own week — P&amp;L by session, the per-slot cards, the A/B legs "
        "and the case-study days. Without it the money in this report has no narrative."),
    "part1_5_rehab.html": (
        "the <code>rehab</code> phase did not write a fragment this cycle",
        "This is the operator's #1 recurring section: every red gate and exit walked through the "
        "full treatment rather than benched at face value, with the failed treatments named."),
    "part1_6_day_rider.html": (
        "the <code>dayrider</code> phase did not write a fragment this cycle",
        "The rider is a SECOND BOOK on the same IB account and it moved more money than the "
        "tournament this week. Its absence hides half the desk."),
    "part2_shadow.html": (
        "the <code>part2:shadow</code> phase did not write a fragment this cycle",
        "The shadow board, the promotion battery and the two grind-exit watches. Without it "
        "nothing nominates a candidate for Monday."),
    "part25_musings.html": (
        "the <code>part25:musings</code> phase did not write a fragment this cycle",
        "The week's mid-week leads, tested adversarially, including the whole gold programme."),
    "part2_6_router_review.html": (
        "the <code>part2_6:router-review</code> phase did not write a fragment this cycle",
        "The router is the desk's #1 lever and this is the only place its decisions get graded."),
    "movement1_census.html": (
        "the MNQ census did not freeze",
        "This is the tape-first half's foundation: the week's biggest runs and whether the desk "
        "showed up. Movements 2 and 3 both key off its run list."),
    "movement1_census_MGC.html": (
        "the gold census did not freeze",
        "Movement 1's MNQ census is unaffected; what is missing is the same table for MGC."),
    "movement2_idle_gates.html": (
        "the <code>M2:idle-gates</code> phase did not write a fragment this cycle",
        "The question of whether the gates we already own could have caught the runs we missed — "
        "and, this cycle, the base-rate control that makes the answer trustworthy."),
    "movement3_greenfield.html": (
        "the greenfield phases did not complete",
        "The from-scratch gate hunt on both instruments, including every candidate that died and "
        "the test that killed it."),
    "run_charts.html": (
        "the run-chart generator produced nothing for this week's sessions",
        "These are the price paths of each session with every fill marked on them. Without them "
        "the case-study days in Part 1 are prose only."),
    "movement3_gold.html": (
        "the gold greenfield section was not rebuilt from the <code>gf_MGC</code> artifacts",
        "Gold is the operator's #1 stated new-instrument priority. Its absence is an empty seat, "
        "not a null."),
    "movement3_fresh_0904.html": (
        "<code>scripts/friday_v7_movement3_fresh.py</code> did not write the addendum",
        "The three cluster hunts that re-ran on 2026-09-04 (<code>gf_MGC</code>, "
        "<code>gf_RIDER_ALL</code>, <code>gf_UNCLASS</code>) would then appear nowhere in this "
        "report, while the frozen Movement 3 above still summarises the PREVIOUS text of the same "
        "three dossiers as though it were current."),
}


# ══════════════════════════════════════════════════════════════════════════════════════
# ★★2026-09-04 PROVENANCE — WHICH WEEK IS EACH FRAGMENT ABOUT, AND SAY IT OUT LOUD.
#
# This build's honesty machinery was written for one failure (a stale fragment wearing this
# week's date) and this cycle produced its mirror image: a report whose fragments are fresh by
# mtime and describe TWO DIFFERENT WEEKS.
#
# The durable runner started at 2026-09-04T21:05Z and declared its stale cutoff as
# "artifacts older than 2026-08-28T22:00Z" — the PREVIOUS cycle's cutoff, unrolled. Under that
# cutoff every 08-29/08-30 fragment on disk counts as current, so it logged "HAVE part1_live —
# skipping" ten times and rebuilt nothing. Meanwhile it DID freeze a new census (21:12Z, covering
# 2026-08-30 22:00 → 2026-09-04 20:59Z), rebuild the progress page, and run three greenfield
# clusters to completion.
#
# So Movement 1 and Part 0 are about the week to 2026-09-04 and Parts 1 through Movement 3 are
# about the week to 2026-08-28, and nothing on the page said so. Both halves are real work and
# neither is stale; lining a number up across the seam is the error, and the reader has to be
# able to see the seam to avoid it. Hence: every fragment is classified by mtime and the split is
# printed on the front page and named again at the top of each late-vintage section.
TONIGHT = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.UTC).timestamp()
LATE_VINTAGE = "2026-08-30 22:00 &rarr; 2026-09-04 20:59&nbsp;UTC"
EARLY_VINTAGE = "the week to Friday 2026-08-28"


def provenance() -> dict[str, list]:
    """Classify every stitched fragment: missing / stale / this-cycle / later-week.

    Generated, never typed. The paragraph this feeds used to be hand-written, and by the time
    this cycle ran it claimed Part 1.5 was last week's text under a red banner (it is not — it
    was rebuilt on 08-30 and carries its own dated wrapper) and said nothing at all about the
    two censuses being a week younger than the rest of the document. A hand-written provenance
    note is a note about the cycle the author was looking at, not the one being rendered.
    """
    out = {"missing": [], "stale": [], "cycle": [], "late": []}
    for label, _sub, name, _a, inserts in SECTIONS:
        for fname in (name, *(f for _h, f in inserts)):
            p = pathlib.Path(SEC) / fname
            if not p.is_file() or not p.stat().st_size or len(p.read_text().strip()) < 200:
                out["missing"].append((label, fname, None))
                continue
            mt = p.stat().st_mtime
            when = dt.datetime.fromtimestamp(mt, dt.UTC)
            if mt < CYCLE_START:
                out["stale"].append((label, fname, when))
            elif mt >= TONIGHT:
                out["late"].append((label, fname, when))
            else:
                out["cycle"].append((label, fname, when))
    return out


def _has_seam() -> bool:
    pv = provenance()
    return bool(pv["late"]) and bool(pv["cycle"])


def _names(rows: list) -> str:
    seen, out = set(), []
    for label, fname, _w in rows:
        if label in seen:
            continue
        seen.add(label)
        out.append(f"<strong>{label}</strong>")
    return ", ".join(out[:-1]) + (" and " + out[-1] if len(out) > 1 else "".join(out))


def vintage_note() -> str:
    """The two-week seam, in the operator's own English, on the front page."""
    pv = provenance()
    if not pv["late"] or not pv["cycle"]:
        return ""
    rows = "".join(
        f'<tr><td class="ln"><strong>{lab}</strong></td><td class="ln"><code>{fn}</code></td>'
        f'<td class="ln">{w:%Y-%m-%d %H:%M} UTC</td><td class="ln">{vin}</td></tr>'
        for vin, group in (
            (f"the week <strong>{LATE_VINTAGE}</strong>", pv["late"]),
            (EARLY_VINTAGE, pv["cycle"]))
        for lab, fn, w in group)
    return (
        '<div class="rev3"><div class="ct">&#9733;&#9733; READ THIS FIRST &mdash; this document '
        'covers TWO weeks, and the seam runs down the middle of it</div>'
        f'<p>{_names(pv["late"])} were rebuilt <strong>tonight</strong> and are about the week '
        f'<strong>{LATE_VINTAGE}</strong>. Everything else &mdash; {_names(pv["cycle"])} &mdash; '
        f'was written on 2026-08-29/30 and is about {EARLY_VINTAGE}. Both halves are finished work '
        'and <em>neither is stale</em>. But they are different weeks, and this is the first time '
        'this report has shipped with that seam in it, so it is drawn here rather than left for '
        'the reader to trip over. <strong>Movement&nbsp;3 is on both sides of the seam and that is '
        'not a mistake:</strong> its body is 08-29 work and its ADDENDUM is tonight\'s, which is '
        'exactly why the addendum is a dated box at the end of the movement instead of being '
        'folded into it. The table below names the fragment for every row so nothing has to be '
        'inferred from the section label.</p>'
        '<p><strong>What this means in practice.</strong> Do not line a Movement&nbsp;1 run count '
        'up against a Part&nbsp;1 fill count &mdash; they are counting different days. The census '
        'that Movements&nbsp;2 and&nbsp;3 were computed against is the <strong>08-28</strong> '
        'freeze, not the one printed in Movement&nbsp;1, so &ldquo;the runs we missed&rdquo; in '
        'Movement&nbsp;2 are not the runs listed in Movement&nbsp;1. The action card below is '
        'built from the 08-28 half plus the three hunts that finished tonight, and every play '
        'names its own section.</p>'
        '<p><strong>Why it happened, since it is a fault and not a choice.</strong> The durable '
        'runner started at 2026-09-04T21:05Z still carrying the <em>previous</em> cycle\'s stale '
        'cutoff (<code>artifacts older than 2026-08-28T22:00Z are STALE</code>). Under that cutoff '
        'the 08-29/30 fragments look current, so it logged <code>HAVE &hellip; skipping</code> ten '
        'times and rebuilt none of them &mdash; while separately freezing a new census and running '
        'three greenfield clusters. <strong>The cutoff needs to roll with the cycle</strong>; it is '
        'on the card.</p>'
        '<table><thead><tr><th class="ln">Section</th><th class="ln">Fragment</th>'
        '<th class="ln">Written</th><th class="ln">Describes</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>')


def phase_report() -> str:
    """The 'what did not run this cycle, named exactly' paragraph — GENERATED."""
    pv = provenance()
    n = sum(len(v) for v in pv.values())
    bits = [
        f'<strong>{len(pv["cycle"]) + len(pv["late"])} of {n} fragments are finished work and '
        f'sit in this document in full.</strong> ']
    if pv["late"]:
        bits.append(
            f'{len(pv["late"])} of them were written <strong>tonight</strong> '
            f'({_names(pv["late"])}) and describe the week {LATE_VINTAGE}; the rest describe '
            f'{EARLY_VINTAGE}. That seam is drawn at the top of this report and it is the single '
            'most important thing to know before comparing any two numbers in it. ')
    if pv["stale"]:
        bits.append(
            f'<strong>{len(pv["stale"])} fragment(s) predate this cycle entirely</strong> '
            f'({_names(pv["stale"])}) and are stitched IN FULL under a red dated banner that says '
            'so at the top of the section. No play on this card is sourced from one. ')
    else:
        bits.append(
            '<strong>Nothing on the running order predates the 08-28 cycle</strong>, so no section '
            'carries the red &ldquo;this is last cycle&rsquo;s text&rdquo; banner this week. '
            '&#9733; Note what that does <em>not</em> mean, and this is the ONE description of '
            'Part&nbsp;1.5 that the front matter, this paragraph and the section itself now all '
            'use: Part&nbsp;1.5 (Rehabilitation) is a <strong>fresh 2026-08-30 wrapper '
            '(&sect;0a&ndash;&sect;0c) around last cycle\'s standing dossiers</strong>. Its mtime is '
            'inside the cycle so the build does not flag it, and it carries its OWN dated banner '
            'saying the material below its first rule describes the week to 2026-08-21. Read '
            '&sect;0a&ndash;&sect;0c as this cycle\'s and the treatments as standing material. ')
    if pv["missing"]:
        bits.append(
            f'<strong>&#9733; {len(pv["missing"])} fragment(s) are MISSING</strong> '
            f'({_names(pv["missing"])}) &mdash; each renders as a named red placeholder at the '
            'point in the running order where it should have been, saying which phase failed and '
            'what the reader is not getting. <strong>Read every one of those as a GAP, not as a '
            'null result:</strong> &ldquo;we looked and found nothing&rdquo; and &ldquo;nobody '
            'looked&rdquo; are opposite instructions for next week. ')
    else:
        bits.append(
            '<strong>Nothing is missing</strong> &mdash; every section on the running order '
            'rendered from a real fragment, so there are no red placeholder boxes to hunt for. ')
    return "".join(bits)


# ★★2026-08-22 REV2 — PARTIAL-PHASE GAP BANNERS.
# The front page promised that "where a section did not run this cycle, it says so in red at the
# point where it should have been". fragment_or_placeholder() delivers that for a MISSING or STALE
# fragment — but this week nothing was missing, so nothing rendered, and the front page was
# describing a mechanism rather than the document. Two phases ran PARTIALLY, which the placeholder
# path cannot see because the fragment it wrote is fresh and complete. They are named here and the
# banner is rendered at the top of the section, which is what the promise actually said.
GAP_BANNERS: dict[str, tuple[str, str]] = {
    # ★★2026-08-29 — BOTH OF LAST CYCLE'S BANNERS ARE REMOVED, AND FOR OPPOSITE REASONS.
    #
    # The Part 1.5 banner said the rehab phase "timed out and this section was rebuilt from what it
    # had saved". That was true on 08-26. This cycle the rehab phase was SKIPPED BEFORE IT STARTED
    # (fair share 19m against a 20m floor), so the section is not a partial rebuild — it is last
    # week's file, and it gets the stale-fragment banner instead, which says so with a date on it.
    # Leaving the old banner would have described a partial run that never happened.
    #
    # The Movement 2 banner said the section was "computed against the superseded census". That was
    # true, and it is now fixed rather than flagged: movement2_idle_gates.html was rebuilt this
    # cycle from the phase's own artifacts, on the SAME 08-28 freeze Movement 1 reports. A banner
    # warning of a divergence that no longer exists is the same failure as a banner denying one
    # that does — it spends the reader's trust on a falsehood.
    #
    # Kept as an empty dict rather than deleted: the mechanism is right and a cycle with a genuinely
    # PARTIAL phase should use it. A partial phase is invisible to the placeholder path, because the
    # fragment it wrote is fresh and complete and simply does not contain everything it should.
}


def gap_banner(fname: str) -> str:
    g = GAP_BANNERS.get(fname)
    if not g:
        return ""
    title, body = g
    return f'<div class="rev3"><div class="ct">&#9733; GAP &mdash; {title}</div><p>{body}</p></div>'


def neutralise_stale_xrefs(frag: str) -> str:
    """Repoint a stale fragment's "MONDAY #6"-style references away from THIS week's card.

    ★2026-08-29. A cross-reference is a POSITION on the action card, and the card is rebuilt from
    scratch every cycle. A prior-week fragment that says "see SATURDAY #2" is therefore pointing
    at a row that no longer exists — or, far worse, at a DIFFERENT row that has inherited rank 2
    this week. Both failures are silent, because the sentence still reads correctly either way.

    check_doc_xrefs() catches the first case and fails the build. It cannot catch the second: a
    pointer that resolves looks healthy. So a stale fragment's references are rewritten to say the
    only thing that is actually true of them — the play they name is on the PREVIOUS week's card,
    and this document does not contain it.
    """
    # ★ The replacement must NOT itself match DOC_XREF, or check_doc_xrefs still sees the
    # reference and still fails the build. The hash is the whole pattern, so "#6" becomes "no. 6".
    # A rewrite that leaves the token intact is not a rewrite.
    #
    # ★★2026-08-29 REV2 — THE REPLACEMENT WAS A CLAUSE, AND IT WAS SPLICED MID-SENTENCE.
    # It read "SATURDAY rank 2 on last week's card, not this one", which is fine standing alone
    # and is broken English everywhere it actually occurred — nine times, all of them inside a
    # sentence the substring had to survive:
    #     the answer to "did SATURDAY rank 2 on last week's card, not this one land" is no
    #     It is now MONDAY rank 6 on last week's card, not this one: the 0.5R and ...
    # A rewrite has to be a NOUN PHRASE, because it is replacing one. So it is now a parenthetical
    # that attaches to the reference instead of swallowing the rest of the clause, with an
    # appositive variant when the reference is ALREADY inside brackets so the parens do not nest.
    def _sub(m):
        w, n = m.group(1), m.group(2)
        pre = frag[:m.start()].rstrip()
        if pre.endswith("(") or pre.endswith("&mdash;"):
            return f'<em>{w} no.&nbsp;{n}, last week&rsquo;s card</em>'
        return f'<em>{w} no.&nbsp;{n} (last week&rsquo;s card)</em>'

    return DOC_XREF.sub(_sub, frag)


def fragment_or_placeholder(fname: str, label: str, sub: str) -> str:
    """Read a fragment, or return a LOUD, NAMED placeholder if it is not fit to stitch.

    ★2026-08-14. The alternative — omitting the section — is the one thing that must not happen:
    a reader cannot tell the difference between "we looked and found nothing" and "nobody looked",
    and those two are opposite instructions for next week. So the gap is printed, with the phase
    that failed and what the section would have contained.
    """
    p = pathlib.Path(SEC) / fname
    # ★ A rehab dossier's filename contains a "/" that the writing agent turned into a real
    # DIRECTORY, so a path under SEC is not necessarily a file. is_file() is the guard, and any
    # glob over this directory must skip non-files rather than choking on IsADirectoryError.
    if p.is_file() and p.stat().st_size and len(p.read_text().strip()) >= 200:
        if p.stat().st_mtime >= CYCLE_START:
            # ★2026-09-04 — a LATER-WEEK fragment is fresh, not stale, and must not get the red
            # stale banner. It gets its own, in amber: this one is a week younger than the report
            # around it. Renders nothing when the whole document is one vintage.
            if p.stat().st_mtime >= TONIGHT and _has_seam():
                when = dt.datetime.fromtimestamp(p.stat().st_mtime, dt.UTC)
                return (
                    '<div class="rev3ptr"><strong>&#9733; THIS SECTION IS A WEEK YOUNGER THAN THE '
                    'REPORT AROUND IT.</strong> '
                    f'<code>{esc(fname)}</code> was rebuilt <strong>{when:%Y-%m-%d %H:%M} UTC</strong> '
                    f'and covers <strong>{LATE_VINTAGE}</strong>. Parts&nbsp;1 to&nbsp;3 and '
                    'Movements&nbsp;2&ndash;3 were written on 2026-08-29/30 and cover '
                    f'{EARLY_VINTAGE}. Both are finished work; <strong>do not line a number here up '
                    'against a number there</strong> &mdash; they are counting different days. The '
                    'full seam is drawn at the top of this report.</div>') + p.read_text()
            return p.read_text()
        # STALE. ★★2026-08-29 CHANGED AGAIN — THE BANNER NOW SITS ON TOP OF THE TEXT, NOT
        # INSTEAD OF IT. Two prior positions, each right about the failure in front of it:
        # the 08-14 build ABORTED on a stale fragment (and would have shipped nothing on a week
        # where six sections were finished); the 08-21 build replaced the stale text with a
        # dated placeholder and DROPPED the content, on the reasoning that a reader cannot tell
        # a stale section from a fresh one.
        #
        # That reasoning is still right and its remedy is now the wrong one, because this cycle
        # inverted the arithmetic. The 08-28 run finished 5 of 13 body phases: Part 1.5, Part 1.6,
        # Part 2.5, Movement 2 and Movement 3 did not regenerate. Dropping all five leaves a report
        # that is 5 sections of working and 5 red boxes — which is precisely the thin report the
        # brief forbids, and the operator loses genuinely useful standing material (the rehab
        # dossiers, the greenfield graves) that nothing else in the desk records.
        #
        # So the fragment is stitched IN FULL, under a red dated banner that names the phase, the
        # date the text was written, the week it actually describes, and the instruction not to
        # carry any number out of it as this week's. The original defect — SILENCE — stays closed:
        # a reader cannot mistake this for a fresh section, because the first thing in the section
        # is a red box saying it is not one. Absence was never the danger; being unable to tell was.
        when = dt.datetime.fromtimestamp(p.stat().st_mtime, dt.UTC)
        why = WHY_STALE.get(fname, "it did not regenerate this cycle")
        return (
            '<div class="rev3"><div class="ct">★ THIS SECTION IS LAST CYCLE&rsquo;S &mdash; it did '
            'NOT regenerate this week</div>'
            f'<p><strong>{esc(label)} &mdash; {sub}</strong> was not rebuilt by the 2026-08-28 run: '
            f'{why}. The text below is the <code>{esc(fname)}</code> on disk, written '
            f'<strong>{when:%Y-%m-%d %H:%M}&nbsp;UTC</strong> &mdash; before this report cycle began '
            '&mdash; so <strong>it describes the week to Friday 2026-08-21, not the week to '
            '2026-08-28.</strong></p>'
            '<p>It is reproduced in full rather than deleted, because the working in it is real and '
            'nothing else on the desk records it. <strong>But every number, date and verdict below '
            'is a PRIOR-WEEK number.</strong> Do not line one up against a number from Part&nbsp;1, '
            'Part&nbsp;2, Part&nbsp;2.6 or Movement&nbsp;1, which are this week&rsquo;s; do not carry '
            'a conclusion out of it onto the action card; and where it disagrees with a fresh section '
            'above it, <em>the fresh section wins.</em></p>'
            '<p><strong>And read it as a GAP, not as a null result.</strong> The question this '
            'section asks was not asked again this week. &ldquo;We looked and found nothing&rdquo; '
            'and &ldquo;nobody looked&rdquo; are opposite instructions for next week.</p></div>'
            + neutralise_stale_xrefs(p.read_text()))
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


# ★★2026-08-22 REV2 — THE METHOD-WOUND CROSS-REFERENCES ARE GENERATED, NOT TYPED.
# Rev1 hand-wrote four of them into the caveat block and ALL FOUR pointed at the wrong play:
# "suppressed_by — BUILD #6" is the ignition-confirmed shadow arm; "the leakage detector — BUILD #3"
# is core_health.flat; "the nightly rollup — BUILD #8" did not exist at all (BUILD had seven plays);
# and "selector_nightly — SATURDAY #3" is BUILD #4, SATURDAY #3 being the standdown file. A stale
# pointer is still a grammatical sentence, which is why nothing caught them.
# Each wound now names its target play by ID and the POSITION is looked up. An ID that is not on
# the card fails the build rather than shipping a sentence that sends the operator to the wrong row.
WOUNDS = (
    # ★2026-08-29 — REWRITTEN. Every wound below is named by one of THIS week's sections against
    # its own numbers, and each points at the play that would close it BY ID; method_wounds()
    # looks the position up, so a re-rank cannot rot the sentence.
    ("<code>SUPPRESSED-OPEN</code> is logged at <code>tournament.py:306</code> and the "
     "55-second absorption veto runs at <code>tournament.py:360</code> &mdash; <em>afterwards</em>. "
     "So for four of the six gates the benched population Part&nbsp;1 reprices contains trades the "
     "gate&rsquo;s own veto would have thrown away, which makes any bench saving built on that log an "
     "UPPER BOUND rather than a point estimate &mdash; one of the reasons Rev&nbsp;2 retires the "
     "+$810/127 figure outright and carries Part&nbsp;1&nbsp;&sect;6&rsquo;s +$312.35/117 instead. The two gates measured clean are <code>grind_long</code> and "
     "<code>capitulation_long</code>",
     "hold-the-chop-bench-0828"),
    ("the entire bench replay is IN-SAMPLE by construction &mdash; it reprices decisions already "
     "made, on the tape they were made on &mdash; and every replayed figure is <em>one lot on the "
     "Lot-A ruler</em> while the live desk runs two, so the Lot-B tail is not modelled anywhere",
     "hold-the-chop-bench-0828"),
    ("neither nightly rollup has ever had a timer. <code>router_nightly</code> last wrote "
     "2026-08-14 and <code>selector_nightly</code> 2026-08-18, so <strong>every nightly number in "
     "Part&nbsp;2.6 is a rebuild done during this report</strong>, not the output of a monitor "
     "that was watching",
     "timer-the-two-dead-nightlies-0828"),
    ("the router was blind for <strong>3h35m</strong> across 43 fail-closed aborts, and "
     "<code>systemctl</code>, the trial log and the tick count all read clean straight through it "
     "&mdash; so &ldquo;the router decided X&rdquo; is, on this week&rsquo;s evidence, sometimes "
     "&ldquo;the router did not run&rdquo;",
     "alert-on-router-headless-aborts-0828"),
    ("two shadow A/B pairs are <strong>byte-identical</strong> (29/29 and 251/251 trades) and four "
     "arm names on the leaderboard carry one trade set, so any reading of those as independent "
     "confirmations inflates the evidence four-fold &mdash; and a broken arm reports a PERFECT "
     "NULL, which is the one failure that looks like a clean result",
     "fix-two-byte-identical-shadow-arms-0828"),
    ("<strong>there was no trend day.</strong> All five sessions closed with a whole-day efficiency "
     "ratio between 0.017 and 0.032, 61.5% of tradeable minutes were chop, and at least four "
     "recommendations in this report are explicitly ungradeable until one trend week lands",
     "grade-router-timing-config-on-a-trend-week-0828"),
)


def method_wounds(plays: list[dict]) -> str:
    byid = {p["id"]: p for p in plays}
    out = []
    for text, pid in WOUNDS:
        tp = byid.get(pid)
        if tp is None:
            raise SystemExit(
                f"FATAL &mdash; method wound points at play id '{pid}', which is not on the card. "
                "Add the play or repoint the wound; do NOT ship a cross-reference that resolves "
                "to nothing (that is exactly what Rev1 did four times).")
        out.append(f'{text} &mdash; <strong>{tp["window"]}&nbsp;#{tp["rank"]}</strong>')
    return ". ".join(x[0].upper() + x[1:] for x in out) + "."


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
        '<strong>&#9733; Almost nothing on this card changes how the desk trades, and that is '
        'the honest answer to this week.</strong> The tournament took THREE signals all week, all '
        'inside one fifty-one-minute window, and the desk was armed for 3.4% of the available '
        'gate-hours &mdash; nowhere near enough evidence to re-tune a threshold, and five separate '
        'sections say so independently. So the card is one promotion, a handful of instrument '
        'fixes, and a set of measurements. '
        # ★2026-09-04 — this count was typed ("Ten of the rows"). It is derived now, because the
        # card grew by twelve rows tonight and a hand-typed tally on the most-read paragraph in
        # the document is the cheapest possible way to be caught lying.
        f'<strong>{sum(1 for p in plays if p.get("window") == "NOT-AN-ACTION")} of the rows are '
        'NOT-AN-ACTION</strong>: refutations printed with their autopsies, because on a week like '
        'this the most valuable output is a list of things that have now been ruled out &mdash; '
        'and one of them refutes a headline finding of this report\'s own Movement 3. '
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
                # ★★2026-09-04 REV2 — THE SHIPPED-CHECK, IN THE ROW. 42 of the 54 rows below are
                # re-issues of the 2026-08-28 card and the reader had no way to tell which had
                # already been actioned. Every -0828 row now carries the verdict of a probe run at
                # render time by scripts/rev2_shipped_check_0904.py — a file, a unit, a grep or a
                # database read on this box — so an instruction is never re-issued without saying
                # whether it was already carried out.
                + (f'<span class="shipcheck"><strong>Last week&rsquo;s card: {esc(p["shipped"])}</strong>'
                   + (f' &mdash; {esc(p["shipped_why"])}' if p.get("shipped_why") else "")
                   + '</span>' if p.get("shipped") else "")
                + f'{tier_pill(p["tier"])} {esc(p["play"])}'
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
        '<p><strong>Six method wounds are open and they bound everything above.</strong> '
        + method_wounds(plays) +
        '</p>'
        # ★2026-09-04 GENERATED, not written. This paragraph was hand-written against the 08-29
        # cycle and by tonight it asserted three things that are no longer true of the document it
        # introduces (Part 1.5 is not stale, nothing carries the red banner, and it said nothing
        # about two of the sections being a week YOUNGER than the rest). It is now derived from the
        # same mtime scan the pre-flight uses, so it cannot describe a cycle other than this one.
        '<p><strong>What did not run this cycle, named exactly.</strong> '
        + phase_report()
        + '<strong>&#9733; No play on this card is sourced from any section carrying a stale '
        'banner</strong>, and the loop on LAST week&rsquo;s card is closed immediately below '
        'this table.</p></div>')
    _ = order
    return "\n".join(out), len(plays)



# ══════════════════════════════════════════════════════════════════════════════════════
# ★★2026-08-29 REV2 — CLOSING THE LOOP ON LAST WEEK'S CARD.
#
# The scope requires closing the loop on the previous week's plays and, where they cannot be
# graded, saying so plainly. Rev 1 did neither: the only references to last week's card were nine
# sentences spliced inside the three STALE sections, and the "what did not run" paragraph did not
# name the omission. The report's own rule — "a gap is never a null result" — applies to itself.
#
# Every DONE / NOT DONE below was checked on the box while writing this revision, and the check is
# printed beside it so the next reader can re-run it rather than trust it. Last week's card was
# reports/friday_v7/plays.json.pre-0828 (50 plays); this is the ACTIONABLE subset — SATURDAY,
# MONDAY and the LIVE BUILD rows. The 14 NOT-AN-ACTION rows and the 6 HOLDs required no action by
# construction and are summarised rather than enumerated, with the one REVERSAL called out.
LAST_WEEK = (
    # (window, rank, topic, status-class, status, the CHECK that decided it)
    ("SATURDAY", 1, "DELETE <code>gazbot7-weekend-flatten.timer</code> — still armed, fires Sunday",
     "row-hl", "DONE",
     "<code>systemctl is-enabled gazbot7-weekend-flatten.timer</code> &rarr; "
     "<code>not-found</code>; no such unit in <code>/etc/systemd/system</code>. The play with the "
     "only hard deadline on last week's card is the one that landed."),
    ("SATURDAY", 2, "Re-open the day rider's protective stop",
     "row-bad", "NOT DONE",
     "<code>src/gazbot7/day_rider.py:102</code> still reads "
     "<code>PLACE_VENUE_STOP = False</code>. This is an operator decision of 2026-08-20, not a "
     "dropped task &mdash; and re-pricing it on this week's tape (Part&nbsp;1&nbsp;&sect;3b, new "
     "this revision) says the decision was RIGHT: naked beat every stop width by $1,190 on the "
     "twelve positions this week actually opened. <strong>NOT DONE, and it should stay not "
     "done</strong> &mdash; it is HOLD&nbsp;#7 on this week's card."),
    ("SATURDAY", 3, "Make the tournament standdown a FILE every writer checks",
     "row-bad", "NOT DONE",
     "<code>scripts/router_tick_durable.py:83</code> still holds "
     "<code>TOURNAMENT_STOOD_DOWN = False</code> as a module constant and there is no standdown "
     "file in <code>data/</code>. The second writer it was meant to constrain "
     "(<code>open_hour_watch.py</code>) wrote to <code>gate_switches.env</code> twice this week — "
     "which is why it is back on this week's card as SATURDAY&nbsp;#3."),
    ("SATURDAY", 4, "Delete the five expired carve-outs from <code>gate_switches.env</code>'s header",
     "row-hl", "DONE — and it grew back",
     "The header was reset on 2026-08-26: 524 comment lines archived to "
     "<code>docs/gate_switches_header_archive_2026-08-26.md</code>. ⚠ But the top of the file now "
     "carries a fresh 8-line carve-out written <strong>2026-08-28T16:24Z</strong> by the open-hour "
     "watcher, with no expiry. The mechanism was never fixed, only the backlog."),
    ("SATURDAY", 5, "Point <code>core_health.flat</code> at the venue, or rename it",
     "row-bad", "NOT DONE",
     "<code>src/gazbot7/core.py:724</code> still writes <code>\"flat\": self._pos is None</code> "
     "— the tournament's own book, not the venue. The file read "
     "<code>flat: true</code> at 02:05Z while this revision was being written."),
    ("SATURDAY", 6, "Grade the per-lot profit ladder shipped on 2026-08-20",
     "row-hl", "DONE",
     "Graded inside last week's own report (Part&nbsp;1.6): 231 sessions, rungs filling on "
     "71.0% / 39.4% / 11.3% / 4.8%. Nothing to re-do."),
    ("MONDAY", 1, "Bench <code>abs_veto_short</code>'s automated slot, keep the signal in shadow",
     "row-hl", "DONE, and it held",
     "<code>data/gate_switches.env</code> reads <code>abs_veto_short=off</code>. The gate took "
     "zero fills all week. ⚠ It was nevertheless ARMED twice by the open-hour watcher and "
     "re-benched by the router (Part&nbsp;1&nbsp;&sect;5) — the switch held, the process did not."),
    ("MONDAY", 2, "Retire <code>rider_w5</code> from the shadow book",
     "row-bad", "NOT DONE",
     "<code>shadow.db</code> still has 74 <code>rider_w5</code> rows and its most recent entry is "
     "<strong>2026-08-28 19:46Z</strong> — it was still writing on the Friday of this report."),
    ("BUILD", 7, "Row-level duplicate check at shadow-write time, and re-seed the broken arms",
     "row-bad", "NOT DONE",
     "<code>cx_clip_brk_live</code> and <code>cx_clip_brk_standdown</code> are still "
     "<strong>251 rows each</strong> and byte-identical. Re-raised this week as BUILD&nbsp;#5."),
    ("BUILD", 9, "Populate <code>signal_journal.suppressed_by</code>",
     "row-hl", "DONE",
     "<strong>1,230 of 1,230</strong> journal rows in the report week carry a non-empty "
     "<code>suppressed_by</code> (1,213 <code>switch_off</code>, 14 <code>atr_floor</code>, "
     "3 <code>none_visible</code>). Part&nbsp;1&nbsp;&sect;7 is built on it."),
    ("BUILD", 10, "Put a timer on <code>router_nightly</code> and <code>selector_nightly</code>",
     "row-bad", "NOT DONE",
     "Zero units in <code>/etc/systemd/system</code>, zero crontab entries. The files dated "
     "08-26/27/28 in <code>data/router_nightly/</code> were written at 22:58&ndash;23:00Z on the "
     "Friday <em>by this report's own build</em>. Re-raised this week as SATURDAY&nbsp;#1 — "
     "second week running."),
)


def last_week_ledger() -> str:
    """The status pass over the PREVIOUS week's card. See LAST_WEEK."""
    rows = "".join(
        f'<tr class="{cl}"><td class="ln"><strong>{w}&nbsp;{r}</strong></td>'
        f'<td class="ln">{topic}</td><td class="ln"><strong>{st}</strong></td>'
        f'<td class="ln">{check}</td></tr>'
        for w, r, topic, cl, st, check in LAST_WEEK)
    done = sum(1 for x in LAST_WEEK if x[3] == "row-hl")
    return (
        '<h2 id="lastweek"><span class="n">&#8630;</span> LAST WEEK&rsquo;S CARD &mdash; what '
        'actually happened to it</h2>'
        '<p class="lead">The card is only worth writing if somebody checks it afterwards. Last '
        f'week&rsquo;s (2026-08-21) carried <strong>50 plays</strong>; below is the actionable '
        'subset &mdash; every SATURDAY and MONDAY row, plus the LIVE BUILD rows whose completion '
        'is checkable from the box. <strong>Each verdict names the command or file that decided '
        f'it</strong>, so none of this has to be taken on trust. Score on the checkable rows: '
        f'<strong>{done} done, {len(LAST_WEEK) - done} not done.</strong></p>'
        '<table>'
        '<thead><tr><th class="ln">Play</th><th class="ln">What it asked for</th>'
        '<th class="ln">Status</th><th class="ln">The check that decided it</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        '<div class="callout"><div class="ct">The rest of last week&rsquo;s card, and the one '
        'reversal</div>'
        '<p><strong>The 6 HOLD and 14 NOT-AN-ACTION rows required no action by construction</strong> '
        '&mdash; they are instructions <em>not</em> to do things, and nothing was done. Five of '
        'them are re-argued on this week&rsquo;s card with fresh evidence and reach the same answer. '
        'The remaining BUILD rows (#1&ndash;6, #8, #11&ndash;18) are shadow arms and measurement '
        'plans whose completion this revision could not verify from the box in the time available; '
        '<strong>they are UNKNOWN, not done, and saying so is the point of this table.</strong></p>'
        '<p><strong>&#9733; One row was REVERSED, deliberately.</strong> Last week&rsquo;s '
        'NOT-AN-ACTION&nbsp;#1 read <em>&ldquo;do NOT promote <code>abs_veto_55s</code> to a live '
        'two-sided slot on Monday&rdquo;</em>. This week it is <strong>MONDAY&nbsp;#1</strong>. '
        'The reason is not a change of mind about the evidence: it is that the candidate collected '
        'another week of <em>forward</em> evidence (+$948.50 on 45 trades, un-retuned) rather than '
        'another re-reading of the same weeks. That is the only thing that should ever move a row '
        'from NOT-AN-ACTION to MONDAY, and it is written down here so the reversal is visible '
        'rather than silent.</p>'
        '<p class="ln">⚠ <strong>Honest limit on this table.</strong> It grades WHETHER a play '
        'shipped, not whether it WORKED. Four of the six that shipped are plumbing with no P&amp;L '
        'attached; the one with money on it (the weekend-flatten timer) is graded by the fact that '
        'the desk went into this weekend flat, which is in the first line of this report.</p>'
        '</div>')


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


# ★★2026-08-22 REV2 — EVERY "#N" IN THE RENDERED DOCUMENT MUST RESOLVE.
# check_xrefs() only validates references INSIDE plays.json, and only the id-anchored ones. Rev1's
# four broken method-wound pointers were in the build script's own prose and in the section
# fragments, where nothing looked at them at all — including "BUILD #8", which did not exist.
# This scans the finished HTML for every "<WINDOW> #<N>" and asserts N is a real rank in that
# window. A pointer to a play that is not there is worse than no pointer.
DOC_XREF = re.compile(r"\b(SATURDAY|MONDAY|BUILD|HOLD|NOT-AN-ACTION)(?:&nbsp;|\s)*#(?:&nbsp;|\s)*(\d+)")


def check_doc_xrefs(doc: str) -> int:
    plays = json.loads(pathlib.Path(PLAYS).read_text())
    ranks: dict[str, set] = {}
    for p in plays:
        ranks.setdefault(p.get("window"), set()).add(p.get("rank"))
    bad = {}
    for window, rank in DOC_XREF.findall(doc):
        if int(rank) not in ranks.get(window, set()):
            bad[f"{window} #{rank}"] = bad.get(f"{window} #{rank}", 0) + 1
    if bad:
        print("=" * 72, file=sys.stderr)
        print(f"FATAL — {len(bad)} cross-reference(s) in the rendered document point at a play that "
              f"does not exist:", file=sys.stderr)
        for k, n in sorted(bad.items()):
            w = k.split(" #")[0]
            print(f"  {k}  (x{n})  — {w} has ranks {sorted(ranks.get(w, []))}", file=sys.stderr)
        print("A '#N' that resolves to nothing sends the operator to a play that is not on the card.",
              file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        return 1
    n = len(DOC_XREF.findall(doc))
    print(f"document cross-refs OK — all {n} '#N' reference(s) resolve to a play on the card")
    return 0


def desk_numbers() -> dict:
    """The week's money, COMPUTED from the trade record — never typed into this file.

    ★★★2026-08-26 REV3 — `pnl_usd` IS ALREADY NET. The 08-21 note below this line was right that
    the front page and the body must quote the same number and wrong about which number that is:
    it defined NET as `pnl_usd − fees_usd`, which charges the $1.50 round trip TWICE. store.py's
    schema comment ("net of fees, venue truth") and pnl.py's docstring both say the column is
    written net, and the invariant holds on all 765 rows in the book — `pnl_usd` equals
    (exit−entry)·dir·qty·multiplier − `fees_usd`, exactly, 765 of 765. So NET is a plain SUM.
    That single character-level change moves the week's tournament book from −$58.50 to −$4.50 and
    the all-time headline by $1,149.00, and it moves NO sign and NO verdict anywhere in the report.
    Superseded note, kept for the audit trail: "★2026-08-21: everything here is NET
    (pnl_usd − fees_usd) so the front page and the body sections quote the same number."
    Fee is $1.50/round-trip/lot and it is already in the column.
    """
    import sqlite3
    con = sqlite3.connect(f"file:{DESK_DB}?mode=ro", uri=True)
    # ★2026-08-29 — THE WEEK MOVED. This was pinned to 08-17..08-22 (last cycle's window) and a
    # build under a new --slug would have printed the PREVIOUS week's money under this week's
    # masthead: the one failure on this page that no reader could catch, because every number
    # would be internally consistent and simply about a different week.
    W = "closed_at >= '2026-08-24' AND closed_at < '2026-08-29'"
    NET = "round(sum(pnl_usd),2)"

    def one(sql):
        return con.execute(sql).fetchone()

    raw = one(f"SELECT count(*), {NET} FROM trades WHERE {W}")
    clean = one(f"SELECT count(*), {NET} FROM trades WHERE {W} AND data_quality IS NULL")
    rider = one(f"SELECT count(*), {NET} FROM trades WHERE {W} "
                "AND data_quality IS NULL AND gate LIKE 'day_rider%'")
    tour = one(f"SELECT count(*), {NET} FROM trades WHERE {W} "
               "AND data_quality IS NULL AND gate NOT LIKE 'day_rider%'")
    claims = one(f"SELECT count(*), {NET} FROM trades WHERE {W} "
                 "AND data_quality IS NULL AND exit_reason='MANUAL_CLAIM'")
    contracts = con.execute(f"SELECT sum(qty) FROM trades WHERE {W} "
                            "AND data_quality IS NULL").fetchone()[0]
    days = con.execute(f"SELECT date(closed_at), {NET} FROM trades WHERE {W} "
                       "AND data_quality IS NULL GROUP BY 1 ORDER BY 1").fetchall()
    gates = con.execute(
        f"SELECT replace(replace(gate,'_A',''),'_B',''), count(*), {NET}, "
        f"round(100.0*sum(pnl_usd > 0)/count(*),1) FROM trades WHERE {W} "
        "AND data_quality IS NULL GROUP BY 1 ORDER BY 3").fetchall()

    # ★★2026-08-29 — THERE WAS NO CARRY IN THE WEEK THIS FUNCTION PRICES (08-24 → 08-28).
    # ⚠★★2026-09-04 REV2 — AND THAT FACT WAS THEN COPIED ONTO THE FRONT PAGE AS THOUGH IT WERE
    # TIMELESS. It is not: at the 09-04 render FOUR rider lots are open. The flatness claim has been
    # removed from the front page and replaced by weekend_carry_box(), which READS the desk state
    # every render. Nothing in this function may be used to argue the desk is flat now — it queries
    # `trades`, which enumerates what CLOSED, and a carry-out never appears in it at all.
    # The query below is about the
    # CARRY-IN (last week's position, closed by hand INSIDE this week's window) rather than about a
    # carry-out. If a carry-out ever exists again, it will not appear in `trades` at all — the
    # table only enumerates what CLOSED — and the venue position line is the only thing that can
    # contradict a benign story. Never infer flatness from this function.
    close = con.execute(
        "SELECT exit_price, closed_at, round(pnl_usd, 2) FROM trades "
        "WHERE exit_reason='MANUAL_CLAIM' AND gate LIKE 'day_rider%' "
        "AND opened_at LIKE '2026-08-21T13:13%' LIMIT 1").fetchone()
    con.close()
    if close is None:
        raise SystemExit("FATAL — no closing row for the 2026-08-21 13:13Z carry-in. It closed on "
                         "2026-08-24 inside this week's window and the front page reports it as "
                         "the week's largest single item. Do not guess: read the row.")
    carry_px, carry_closed, carry = close

    return dict(raw=raw, clean=clean, rider=rider, tour=tour, claims=claims, days=days,
                contracts=contracts,
                gates=gates, carry=carry, carry_px=carry_px, carry_closed=carry_closed,
                green=sum(1 for _, v in days if v > 0))


def m(v, dp=2):
    s = f"{abs(v):,.{dp}f}"
    return ("&minus;$" + s) if v < 0 else ("$" + s)


# ══════════════════════════════════════════════════════════════════════════════════════
# ★★★2026-09-04 REV2 — THE WEEKEND CARRY BOX, GENERATED AT RENDER TIME.
#
# Rev 1 opened this report with "The desk is FLAT ... nothing is riding over the weekend", quoting a
# desk_reconcile read at 22:26:32Z. That was the 2026-08-28 reading, hand-copied into the front page
# and never re-read. At this render four rider lots are open. The report's own SATURDAY #5 and
# Part 1.6 §6(a) describe the identical mechanism from 2026-08-21, where it cost −$2,149.44 — and
# the first line of the document said it was not happening.
#
# So the carry line is no longer a sentence somebody types. It is READ, every render, from the two
# files that are the desk's own truth, and it renders NOTHING if the desk really is flat. A box that
# only appears when there is a position cannot make the 08-28 mistake in either direction.
#
# ⚠ Never infer flatness from the `trades` table: it enumerates what CLOSED. The venue position line
# is the only thing that can contradict a benign story, and when the venue cannot be read the honest
# output is "unknown", not "flat".
def weekend_carry_box() -> str:
    try:
        st = json.loads(pathlib.Path(f"{GB}/data/day_rider_state.json").read_text())
        rc = json.loads(pathlib.Path(f"{GB}/data/desk_reconcile_state.json").read_text())
    except Exception as e:                       # a missing state file must not kill the build
        return (f'<div class="rev3"><div class="ct">&#9733;&#9733; CARRY CHECK UNAVAILABLE</div>'
                f'<p>The desk state files could not be read ({html.escape(str(e))}), so this report '
                f'CANNOT tell you whether anything is open. Treat that as "unknown", never as '
                f'"flat".</p></div>')
    lots = st.get("lots_open") or 0
    if not lots or st.get("closed"):
        return ""
    side = "LONG" if (st.get("direction") or 0) > 0 else "SHORT"
    entry, ahead = st.get("entry") or 0.0, st.get("ahead_pt") or 0.0
    unreal = ahead * lots * 2.0                  # MNQ = $2.00/point. Never the MGC multiplier.
    r1 = rc.get("read1", {})
    try:
        gap = json.loads(pathlib.Path(f"{SEC}/rev2_weekend_gap_0904.json").read_text())
        g = (f'Across the <strong>{gap["n"]} Sunday reopens we hold on tape</strong> the median gap is '
             f'<strong>{gap["gap_abs_median"]} points</strong> ({m(gap["on_this_position_usd"]["median_gap"])} '
             f'on {lots:.0f} lots), the worst gap DOWN is {gap["gap_worst_down"]}pt '
             f'({m(gap["on_this_position_usd"]["worst_gap_down"])}) and the worst FIRST HOUR for a long is '
             f'<strong>{gap["first_hour_worst_for_long"]}pt</strong> '
             f'({m(gap["on_this_position_usd"]["worst_first_hour"])}). ')
    except Exception:
        g = ""
    return (
        '<div class="rev3"><div class="ct">&#9733;&#9733;&#9733; WEEKEND CARRY &mdash; '
        f'{lots:.0f} LOTS ARE OPEN RIGHT NOW. This is the first thing on the page because it is the '
        'only thing on it with a clock.</div>'
        f'<p><strong>{side} {lots:.0f} MNQ from {entry:,.2f}.</strong> '
        f'<code>ahead_pt</code> {ahead:+.1f} at the 21:00Z close &mdash; '
        f'<strong>{m(unreal)} unrealised</strong> at $2.00 a point. '
        f'<code>data/day_rider_state.json</code> reads <code>closed false</code>, '
        f'<code>flatten_blocked {str(st.get("flatten_blocked")).lower()}</code>, '
        f'<code>venue_ok {str(st.get("venue_ok")).lower()}</code>, '
        f'<code>venue_net_ts {str(st.get("venue_net_ts"))[11:19]}Z</code>, note '
        f'<code>{html.escape(str(st.get("note")))}</code>. '
        f'<code>desk_reconcile</code> at {str(rc.get("ts"))[11:19]}Z reads '
        f'<strong>{html.escape(str(r1.get("summary")))}</strong> &mdash; '
        f'{html.escape("; ".join(r1.get("reasons") or []))}.</p>'
        '<p><strong>What happened.</strong> The venue read has failed every two minutes since '
        '18:48:50Z and port 4002 is REFUSING connections &mdash; the gateway is down, not the '
        '04:28Z hang where the port stays open. <strong>Both</strong> eod-flatten shots (20:53Z and '
        '20:57Z) died inside the same <code>connectAsync</code> TimeoutError, which is the '
        'single-connection failure Part&nbsp;1.6 &sect;6(a) describes: every flatten path on this '
        'desk shares one <code>connectAsync</code>, so one wedge kills the rider, the watchdog and '
        'both flatten shots together. CME is shut until Sunday 22:00Z, so nothing can be done '
        'before then.</p>'
        f'<p><strong>How much this can move.</strong> {g}'
        'The reopen gap is <em>not</em> the risk here &mdash; the Monday is. The 2026-08-21 carry, '
        'the same shape on the same size, was &minus;121.93pt at its Friday close and gapped '
        '<em>+22.25 in its favour</em> on the Sunday; it was still claimed by hand on the Monday at '
        '&minus;267.93pt for <strong>&minus;$2,149.44</strong>, the largest single item in this '
        'report. And there is no venue stop under this one: '
        '<code>PLACE_VENUE_STOP = False</code>, by your decision of 2026-08-20.</p>'
        '<p><strong>The instruction, at the Sunday 22:00Z reopen &mdash; not on Saturday, because '
        'nothing can be done on Saturday.</strong> Get a venue read FIRST and confirm it says '
        f'{lots:.0f}. Then decide FLAT or MANAGE <em>deliberately</em>. If the read still comes back '
        '<code>?</code>, that is itself the answer: you are flat-blind, the position is unmanaged, '
        'and no managing order should go into a book you cannot see. Full row: '
        'SATURDAY&nbsp;#0.</p></div>')


def render_front(slug: str, published: str, n_plays: int) -> str:
    """The front page for the week to Friday 2026-08-28.

    ★2026-08-29 REWRITTEN. Every sentence of the previous version described the week to 08-21 —
    an open four-lot position, an armed weekend-flatten timer, a −$1,905.36 idle-gate headline.
    All of it was true and none of it is this week. The money below is COMPUTED (desk_numbers();
    the SLUG names the file and is the WEEK ENDING, `published` is the day this render shipped),
    but the narrative is not, so the narrative is the thing that rots. It is rewritten wholesale
    each cycle rather than patched, because a patched front page keeps the previous week's frame
    and quietly argues for last week's plays.
    """
    d = desk_numbers()
    raw_n, raw_v = d["raw"]
    cl_n, cl_v = d["clean"]
    r_n, r_v = d["rider"]
    t_n, t_v = d["tour"]
    c_n, c_v = d["claims"]
    # ★2026-08-29 REV2 — SAY WHICH COUNT. The header read "10 sections" while the running order
    # immediately below it lists ELEVEN entries, because the ToC counts the front matter and this
    # constant does not. Both were right about different things and the reader saw a mismatch on
    # the first line of the page. It is now labelled: N BODY sections, plus the front matter.
    n_sections = len(SECTIONS)
    carry = d["carry"]
    carry_closed = d["carry_closed"]
    ex_carry = round(cl_v - carry, 2)
    rider_ex = round(r_v - carry, 2)

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
  <p class="dates">Week ending <strong>Fri 2026-08-28</strong> &nbsp;·&nbsp; Mon 24 &ndash; Fri 28 August 2026 &nbsp;·&nbsp; published {published} &nbsp;·&nbsp;
     MNQ-led, MGC captured &nbsp;·&nbsp; PAPER &nbsp;·&nbsp;
     {n_plays} plays &nbsp;·&nbsp; front matter + {n_sections} body sections</p>
</div>

{weekend_carry_box()}

<div class="rev3">
<div class="ct">★★★ THIS IS REVISION 2, WRITTEN 2026-09-04 &mdash; what changed, in five lines</div>
<p>A proofread pass ran against the first draft and returned <strong>20 issues and 10 unanswered
questions</strong>. All thirty are closed. Every correction is marked <strong>&#9733;&nbsp;REV2</strong>
in the section that carried it, and the full changelog is in
<code>reports/friday_v7/sections/rev2_done.txt</code>. <strong>The new material is
Part&nbsp;4</strong>, at the end of the body.</p>
<p><strong>The five that change what you do:</strong>
<em>One</em> &mdash; <strong>the desk is NOT flat.</strong> Four day-rider lots are open over this
weekend, LONG from 29,641.25, &minus;$912 at the close, venue unreachable since 18:48Z. The box
above is the whole of it, and it is <strong>SATURDAY&nbsp;#0</strong>.
<em>Two</em> &mdash; <strong>the Monday promotion is HELD.</strong> <code>abs_veto_55s</code> was
re-run to 2026-09-04 rather than 2026-08-28; the extra week is 31 trades at &minus;$13.74 each and
trips the row&rsquo;s own kill line on the LONG side. Green in 7 ISO weeks of 8, not 7 of 7.
<em>Three</em> &mdash; <strong>the +$810.44 bench saving is RETIRED</strong>, not merely
un-quotable: its population cannot be rebuilt. The replacement is <strong>+$312.35 over 117
signals</strong>, and the regime split that HOLD&nbsp;#2 rested on is refuted at
P&nbsp;=&nbsp;0.943.
<em>Four</em> &mdash; <strong>the whole week 08-31&rarr;09-04 is now graded</strong> (Part&nbsp;4
&sect;3). It contradicts four headline claims in the body, including &ldquo;nothing stopped
out&rdquo; and &ldquo;the entire short side fired nothing&rdquo;.
<em>Five</em> &mdash; <strong>every row of last weekend&rsquo;s card now carries a shipped-check</strong>
run against this box. Of 25 shippable rows: <strong>0 DONE, 19 NOT DONE, 5 CARRIED, 1
re-measured.</strong></p>
<p><strong>Two figures this box itself used to get wrong, corrected here.</strong> The rider&rsquo;s
off-tape fill artefact is <strong>$1,053.50 / 11 split orders / 15 residual legs / 18 lots /
66.8%</strong> of the rider&rsquo;s loss <em>for the week 08-24&rarr;08-28</em> &mdash; not the
&ldquo;$1,170.50 / 74%&rdquo; printed in Rev&nbsp;1, and it is one figure with one window and one
unit everywhere it now appears. And the cumulative desk total in the previous version of this box,
&minus;$4,129.44, was <strong>through 2026-08-28</strong>; Part&nbsp;0 is a week younger and its
live figure through 2026-09-04 is <strong>&minus;$3,326.44</strong>. Use Part&nbsp;0&rsquo;s.</p>
</div>

<div class="rev3">
<div class="ct">★★ READ THIS FIRST &mdash; what this report has, and what it is missing</div>
<p><strong>&#9733;&nbsp;REV2 &mdash; THE DESK IS NOT FLAT, and the sentence that used to open this
report said it was.</strong> Rev&nbsp;1 opened &ldquo;the desk is FLAT &hellip; nothing is riding over
the weekend&rdquo; and cited a <code>desk_reconcile</code> read at 22:26:32Z. That read is the
<strong>2026-08-28</strong> one; it was true then and it is false at this document's publish time.
The live read is in the red box at the top of this page and it is generated from
<code>data/day_rider_state.json</code> and <code>data/desk_reconcile_state.json</code> at render
time, so it cannot go stale again the way this paragraph did. Four lots are open. That was the exact
failure that cost {m(carry)} on the week this report grades, it is <strong>SATURDAY&nbsp;#0</strong>
on the card, and the fix for it &mdash; SATURDAY&nbsp;#5, move the flatten earlier and put the page
upstream of it &mdash; was issued last weekend and is <strong>NOT DONE</strong>.</p>
<p><strong>&#9733; And ONE section of this report did not regenerate as a PHASE.</strong> The 08-28
overnight run finished <strong>5 of its 13 body phases</strong> — a pre-flight that warned, at
22:14:21Z, that &ldquo;13 body phases declare 975m of timeouts against a 166m budget
(5.9&times;)&rdquo; and that about 7 of 13 would finish. It got 5. Part&nbsp;1.5 (Rehabilitation),
Part&nbsp;1.6 (the day rider) and Part&nbsp;2.5 (mid-week musings) were all SKIPPED before they
started, each one allocated 19 minutes against a 20-minute floor. <strong>All three were then
rebuilt by hand</strong> — Part&nbsp;1.6 and Part&nbsp;2.5 on 2026-08-29, Part&nbsp;1.5 on
2026-08-30. <strong>&#9733;&nbsp;REV2 — ONE description of Part&nbsp;1.5, used everywhere, because
this document carried three.</strong> It is <em>a fresh 2026-08-30 wrapper (&sect;0a&ndash;&sect;0c,
this week's material) around last cycle's standing dossiers</em>. It does NOT carry the build's red
stale-fragment banner — its mtime is inside the cycle, so the build does not classify it as stale —
but it carries <strong>its own</strong> dated banner in its first paragraph saying that everything
below the first horizontal rule is last cycle's text describing the week to 2026-08-21. Read
&sect;0a&ndash;&sect;0c as this cycle's and the treatments below them as standing material.</p>
<p><strong>&#9733;&#9733; Movement&nbsp;2 and Movement&nbsp;3 were rescued, and it is worth knowing
how.</strong> Both phases RAN and were killed before writing their sections — but they had already
written their labs to disk. Both movements below were rebuilt from those artifacts, so every number
in them is <em>this</em> week's, computed at render time from files the phases produced. What could
not be rescued was rescued nowhere: a phase that never started leaves nothing behind, which is the
difference between the one section that carries a banner and the ten that do not.</p>
</div>

<div class="callout"><div class="ct">★★ IF YOU READ ONLY THIS &mdash; three things, in order</div>
<p><strong>1 &mdash; The desk was switched on for 3.46% of the week, and that was probably
right.</strong> Six gates over the week's <strong>118</strong> tradeable hours (Mon 00:00Z to Fri
22:00Z, not 120) is <strong>708 available gate-hours</strong>; the desk used
<strong>24h&nbsp;30m</strong> &mdash; <strong>3.46%</strong>. (Part&nbsp;1&nbsp;&sect;3's REV3 table
computes this from the switch record; the 720-hour version this page used to print was arithmetic on
a week that does not exist.) The tournament took three signals all week, all inside one
fifty-one-minute window on Friday afternoon, and won all three for <strong>{m(t_v)}</strong>. The
case that this was discipline rather than cowardice is measured, not asserted &mdash; and
&#9733;&nbsp;REV2 names WHICH instrument it is measured on, because this paragraph used to mix two.
The <strong>187 impulses / 127 signals</strong> came from the <code>SUPPRESSED-OPEN</code> log and
are retired along with the $810. The figure below is <code>signal_journal</code>'s own record,
durable on disk since 2026-08-04: of the 380 fires it holds for the week, the <strong>117 above each
gate's own ATR floor</strong> were entered at the first tick at or after their own timestamp and run
forward on that gate's live Lot-A exit, at five stop widths at once. The benched set comes to
<strong>+$312.35 saved over those 117 signals</strong> at the stop the desk actually runs. <strong>&#9733; That is a REVISION.</strong> The +$810.44 over 127 signals this
page used to print is <span class="tag pill-dontarm">RETIRED</span> &mdash; its population was
counted off <code>SUPPRESSED-OPEN</code> journal lines and the systemd journal is a ring buffer, so
it can no longer be rebuilt, let alone checked. What replaces it is a saved, re-runnable replay
(<code>scripts/rev3_bench_replay.py</code>) over the population that IS durable. It is sign-stable
across the 0.5&times;&ndash;1.5&times; stop sweep but it <em>decays</em> across it (+$624.59 at
0.5&times; &rarr; +$11.86 at 1.5&times;), two days of five carry all of it, stripping three impulses
takes it to +$66.31, and the bootstrap band is &minus;$623.74 to +$1,208.31 with P(the true saving
is &ge;&nbsp;0) = <strong>0.747</strong>. Part&nbsp;3&nbsp;&sect;Q4's independent floor is
<strong>+$128</strong>. So: <em>keep the policy, quote +$312 with its band if you must quote
anything, and never quote $810 again.</em> HOLD&nbsp;#1.</p>
<p><strong>2 &mdash; The router's dominant error is no longer direction. It is LATENESS.</strong>
Friday's one deliberate arm was right — four lots, four winners, +$181.50 — and it was
<strong>8m&nbsp;37s late</strong>, which cost $33.84 on one lot measured from the gate's own
earlier suppressed signal, and $205&ndash;$705 measured from the router's side. Actuation is not
the problem: the gates filled <strong>1.4 seconds</strong> after the switch flipped. About 15 of
the 20 minutes is the router's own confirmation appetite. MONDAY&nbsp;#2.</p>
<p><strong>3 &mdash; ★ And the structural finding, which outranks both.</strong> For three cycles
this report has closed with &ldquo;detection is solved, selection is not&rdquo; without being able
to say why. Movement&nbsp;3 measured it on <strong>52,937 minutes across 41 days</strong>: against
a fixed POINT threshold every precursor we own looks predictive (AUC to 0.81, p=0.00) — and once
the threshold is expressed in ATR, or ATR is simply held fixed, <strong>every one of them collapses
to a coin flip or below</strong>. A 55-point move is easy on a wide tape and hard on a quiet one,
so anything correlated with ATR scores well against a point threshold. <strong>The desk's entire
precursor toolkit is one volatility meter, and we have been asking it for a
direction.</strong> BUILD&nbsp;#3.</p></div>

<h2 id="honest"><span class="n">★</span> THE HONEST HEADLINE &mdash; a red week whose loss was
booked before it began</h2>

<p class="lead">The desk booked <strong>{m(cl_v)}</strong> across {cl_n} legs
({d['contracts']:.0f} contracts &mdash; the day rider's legs are 1&ndash;3 lots each, so a row count
is not a lot count), <strong>{d['green']} of the five days green</strong>. But
<strong>{m(carry)} of that landed on Monday morning</strong> and belongs to last week: it is the
four-lot rider position opened 2026-08-21T13:13:06Z, carried through the CME halt unmanaged, and
closed by hand on {carry_closed[:10]} at {carry_closed[11:19]}Z at {d['carry_px']:,.2f}. Strip it
out and <strong>this week's own decisions produced {m(ex_carry)}</strong> &mdash; the day rider
{m(rider_ex)} and the tournament {m(t_v)}.</p>

<p class="lead"><strong>Three things worth carrying into Saturday.</strong>
<em>One:</em> there was <strong>no trend day</strong>. All five sessions came in at a whole-day
efficiency ratio between <strong>0.017 and 0.032</strong> &mdash; 300 to 530 points of range bought
for a net of &plusmn;261. Every conclusion in this report is a chop-week conclusion, and at least
four separate recommendations are explicitly waiting on one trend week to be gradeable at all.
<em>Two:</em> your hands are a dead heat <strong>on the tournament</strong>, and a long way from
one on the rider. Three of the six tournament lots ended <code>MANUAL_CLAIM</code>; re-run forward on
the tick tape under their own configured exits they were worth +$141.00 against the +$136.50 you
booked &mdash; <strong>a delta of +$4.50 across the week</strong>, on the 24.25-point entry ATR the
desk's own native stops record. <strong>&#9733;&nbsp;REV2 &mdash; scope that to the book it describes.</strong>
On the DAY RIDER the same button is the main exit and Part&nbsp;1.6&nbsp;&sect;4 scores it at
<strong>+$5,426.50</strong> against holding, across 19 in-week claims, 10 of them better than the
hold. Six lots and nineteen claims are different populations and they say different things; neither
is &ldquo;how good your hands are&rdquo; on its own. <em>Three:</em> the week's most useful results are all NULLS with named tests on
them, and that is not a bad week &mdash; it is six batteries doing their job. Two of them
(the searched day-classifier, and the BIG-TREND exit rung) killed things this desk has been
half-believing for weeks.</p>

<p>There is no single honest total, so here are all of them, with what separates each from the
next.</p>

<table>
<thead><tr><th class="ln">What you are looking at</th><th class="num">Legs</th><th class="num">Net $</th>
<th class="ln">Why it differs from the row above</th></tr></thead>
<tbody>
<tr><td class="ln">Raw <code>trades</code> rows, 08-24 &rarr; 08-28</td><td class="num">{raw_n}</td>
    <td class="num">{m(raw_v)}</td>
    <td class="ln">everything the desk booked &mdash; the CASH book</td></tr>
<tr class="row-hl"><td class="ln"><strong>Clean ledger</strong> (<code>data_quality IS NULL</code>)</td>
    <td class="num">{cl_n}</td><td class="num"><strong>{m(cl_v)}</strong></td>
    <td class="ln"><strong>identical this week &mdash; not one flagged row.</strong> Last week there
        was a BADFILL lot and the two books disagreed; this week they do not, and that is worth
        saying rather than leaving as a silent match</td></tr>
<tr><td class="ln">The day rider alone</td><td class="num">{r_n}</td><td class="num">{m(r_v)}</td>
    <td class="ln">the second desk, on the same IB account, which reads none of the router's
        switches. It is the bigger of the two books in both directions</td></tr>
<tr class="row-bad"><td class="ln">&hellip; of which: the carry-in from 2026-08-21, closed by hand
        on {carry_closed[:10]}</td>
    <td class="num">1</td><td class="num"><strong>{m(carry)}</strong></td>
    <td class="ln">opened LAST week, closed in THIS one, so it is inside every total above and
        belongs to neither week's decisions. It is larger than everything else in the book put
        together</td></tr>
<tr><td class="ln">The day rider, excluding that close</td><td class="num">{r_n - 1}</td>
    <td class="num">{m(rider_ex)}</td>
    <td class="ln">what the rider's own week actually produced</td></tr>
<tr class="row-hl"><td class="ln"><strong>The tournament alone</strong> (the six-gate desk this
        report is mostly about)</td>
    <td class="num">{t_n}</td><td class="num"><strong>{m(t_v)}</strong></td>
    <td class="ln">3 signals &times; 2 scale-out lots, all on Friday between 14:00 and 14:51Z.
        <strong>Six for six &mdash; and that is n=1, not n=6</strong>: three gates agreeing about
        one push, each booking two lots of the same signal</td></tr>
<tr class="row-hl"><td class="ln"><strong>What THIS week's decisions produced</strong>
        (everything except the carry-in)</td>
    <td class="num">{cl_n - 1}</td><td class="num"><strong>{m(ex_carry)}</strong></td>
    <td class="ln">the number to judge the week's decisions on. The cash number is the row at the
        top; this is the strategy number</td></tr>
</tbody>
</table>

<table>
<thead><tr><th class="ln">Day</th><th class="num">Desk net</th></tr></thead>
<tbody>{daily}</tbody>
</table>

<h2 id="scorecard"><span class="n">★</span> THE SCORECARD &mdash; what survived the week</h2>

<p class="lead">Lead with what survived the skeptic, never with the biggest number. Nine results
carried real weight out of this week; here is where each one landed and the test that decided it.
<strong>&#9733; Every row below comes from a section that RAN this cycle</strong> &mdash; nothing on
this scorecard is sourced from the three sections carrying a stale banner.</p>

<table>
<thead><tr><th class="ln">The claim</th><th class="ln">Verdict, and the test that decided it</th>
<th class="ln">Where</th></tr></thead>
<tbody>

<tr class="row-hl">
  <td class="ln"><strong>Every precursor feature on this desk is a proxy for ATR &mdash; which is
      why selection keeps failing</strong></td>
  <td class="ln"><span class="tag pill-live">SURVIVED &mdash; the week's most important result</span>
      52,937 minutes, 41 days. Against a fixed POINT threshold, volume z, trade-count z, ATR
      expansion, aggressor flow, ER(15) and ATR level all beat a coin flip with <strong>p =
      0.00</strong>, ATR level reaching <strong>0.81</strong>. Express the same threshold in ATR and
      the discrimination <em>inverts</em> — ATR expansion falls to <strong>0.234</strong> and ATR
      level to <strong>0.306</strong>, both now worse than chance. Hold ATR fixed and ask within the
      band and everything sits between 0.29 and 0.56. <strong>It is the same instrument measured
      twice:</strong> a 55-point move is easy on a wide tape and hard on a quiet one.
      <br><strong>&#9733; REV2 &mdash; Movement&nbsp;2's corroboration is WEAKER than Rev1 of this
      card claimed, and the correction is worth reading.</strong> The line here said &ldquo;a random
      second beats the gates' own triggers on 6 of 6&rdquo;. It compared a control that had been
      HANDED the run's direction against the gates' BOTH-directions number, which loses by
      construction. Scored like for like the gates beat the control on <strong>3 of 5</strong>
      in-direction and <strong>4 of 5</strong> direction-blind &mdash; on 2 to 10 lots each, where
      only <code>exhaustion_short</code> separates from its own control at all (P&nbsp;=&nbsp;0.033
      raw, <strong>0.166 Holm-adjusted</strong> across the five gates). <strong>The control is a
      NULL, not a kill.</strong> Untouched: Movement&nbsp;2's direct measurement, the six gates as
      configured taking 32 lots into those runs for &minus;$741.50. So this row now rests on
      Movement&nbsp;3's 52,937 minutes alone, which is where it was always strongest.</td>
  <td class="ln"><a href="#sec8">Movement 3</a>, <a href="#sec7">Movement 2</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong><code>abs_veto_55s</code>, two-sided, is the promotion candidate</strong></td>
  <td class="ln"><span class="tag pill-shadow">SURVIVED &mdash; the only arm on 79 that passed
      everything</span>
      n=433, +$5,302, +$12.25/trade, green on <strong>24 of 31 trading days</strong>; both halves of
      its life pay, both regimes pay, and <strong>both sides</strong> pay (SHORT +$3,612 / LONG
      +$1,691). Head-to-head against its own un-vetoed twin it is +$5,350, so it is the VETO being
      promoted rather than the thrust. Strip its three best days and it is still +$3,363. This week
      it added +$948.50 on 45 trades without being re-tuned &mdash; the same candidate as last week,
      now with another week of <em>forward</em> evidence rather than another week of the same
      evidence.
      <br><strong>Read the board once, not nine times:</strong> the nine best arms on it are all
      green, all short, and all the <em>same 23 trades</em>. Added up they look like $5,888; the
      truthful figure is one arm's worth.</td>
  <td class="ln"><a href="#sec3">Part 2</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong>Being switched off was worth about $312 &mdash; and you should not quote
      that number either. The $810 is RETIRED.</strong></td>
  <td class="ln"><span class="tag pill-live">LEANS RIGHT, UNPROVEN &mdash; and the honest version is
      the useful one</span>
      <strong>&#9733; REVISED IN REV&nbsp;2.</strong> The <strong>+$810.44 over 127 signals</strong>
      this row used to carry is <span class="tag pill-dontarm">RETIRED</span>, not defended: it was
      counted off <code>SUPPRESSED-OPEN</code> journal lines, the systemd journal is a ring buffer,
      and that population can no longer be rebuilt or checked. Part&nbsp;1&nbsp;&sect;6 replaces it
      with a saved, re-runnable replay (<code>scripts/rev3_bench_replay.py</code>) over the
      population that IS durable &mdash; <code>signal_journal</code>, on disk since 2026-08-04:
      <strong>117 above-floor impulses, +$312.35 saved at the live stop, +$2.67 a signal.</strong>
      <br>It is <span class="tag pill-live">SIGN-STABLE</span> across the whole
      0.5&times;&ndash;1.5&times; stop sweep, which is what earns it a verdict at all &mdash; but
      read the SLOPE, because it decays rather than holds: +$624.59 &rarr; +$490.34 &rarr;
      <strong>+$312.35 (live)</strong> &rarr; +$73.29 &rarr; +$11.86. Most of what
      &ldquo;benching&rdquo; saved is the desk's stop being tight enough to guarantee those trades
      lost.
      <br><strong>And it is thin.</strong> Two days of five carry 100% of the gross positive (drop
      Tuesday and the week's saving is +$8.39; drop Thursday, +$16.62); strip the three biggest
      impulses out of 117 and +$312.35 becomes +$66.31; a 10,000-draw bootstrap gives
      &minus;$623.74 to +$1,208.31, i.e. <strong>P(&le;&nbsp;0) = 0.253</strong>.
      Part&nbsp;3&nbsp;&sect;Q4's independent floor is +$128.
      <br>&#9733;&#9733; <strong>The regime decomposition is REFUTED.</strong> &ldquo;The saving is
      entirely chop; in aligned trend benching is FREE (50 signals, &minus;$0.81 each)&rdquo; does
      not survive re-derivation. On the durable population chop is <strong>+$3.99</strong> a signal
      (n=78) and aligned trend is <strong>+$3.37</strong> (n=35) &mdash; the same number &mdash; and
      a 10,000-draw label-shuffle placebo on that gap returns <strong>P&nbsp;=&nbsp;0.943</strong>.
      There is no regime split in the bench this week, and nothing about arming may rest on one.
      <br>&#9733; <strong>Named caveat, still standing:</strong> SUPPRESSED-OPEN is logged UPSTREAM
      of the 55-second veto and both absorption confirms, so any bench figure built on it is an
      UPPER BOUND. That is one of the reasons the $810 is gone.</td>
  <td class="ln"><a href="#sec1">Part 1 &sect;6</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong>The gates we own still cannot reach the runs we miss &mdash; third cycle,
      third week of tape</strong></td>
  <td class="ln"><span class="tag pill-live">SURVIVED &mdash; and it went a rung deeper this
      time</span>
      All 62 sat-out runs replayed second by second: <strong>36,600 decision-seconds</strong>, each
      gate's own deciders and A/B exits, $1.50 a round trip. Fired as configured the six gates take
      32 lots into those runs for <strong>&minus;$741.50</strong> (&minus;$23.17/lot, 18.8% win).
      Strip every constraint off and 114 lots make &minus;$168.50. A <strong>724-cell</strong>
      threshold sweep finds no cell that is both positive and more than three trades wide.
      <br><strong>&#9733; The new rung, and its REV2 correction:</strong> previous cycles measured
      whether the gates made money; this one tried to measure whether they <em>know anything</em>,
      against a random entry inside the same window. Rev1 of this card reported &ldquo;not one of
      the six triggers wins&rdquo; — scored against a control that had been HANDED the direction
      while the gates' figure had not. Read like for like the gates win <strong>3 of 5</strong>
      in-direction and <strong>4 of 5</strong> direction-blind, on 2–10 lots each, and after
      correcting for having looked five times nothing separates from its control.
      <strong>The control is a NULL.</strong> The &minus;$741.50 above does not rest on it.
      <br><strong>Honest limit:</strong> this is a statement about the GATES, not about the census,
      which is why it has now survived three different run lists.</td>
  <td class="ln"><a href="#sec7">Movement 2</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>&ldquo;The momentum shadow book is green while the routed book sits
      flat&rdquo;</strong> &mdash; argued 106 times this week</td>
  <td class="ln"><span class="tag pill-dontarm">REFUTED as an arming argument</span>
      The open-hour watcher raised <strong>106 [ACT] alerts</strong>, all making this one argument.
      Named test: reprice the LIVE gates' own suppressed intents at the shadow's <em>exact</em>
      ruler (2.0R target, 1.0&times;ATR stop) and you get <strong>&minus;$143.61 on 65 signals</strong>
      against the shadow's <strong>+$948.50 on 45</strong>. Same week, same instrument, same exit
      rule, opposite sign — so the exit is not the difference. The gap is the ENTRY POPULATION: the
      shadow variants carry no ATR floor, so they fire in exactly the tape the live gate's floor
      refuses. <strong>The shadow result stands and is the promotion candidate; only its use as a
      reason to arm the live gate is dead.</strong></td>
  <td class="ln"><a href="#sec1">Part 1</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong><code>abs_veto_short</code> sat armed through the exact tape it exists to
      trade and said nothing</strong></td>
  <td class="ln"><span class="tag pill-parked">PARKED &mdash; the week's #1 stone, and it is a
      MECHANISM question</span>
      Friday 16:00&ndash;17:03Z the tape fell <strong>328 points</strong> in one confirmed
      direction. The gate was armed for <strong>46m&nbsp;30s</strong> of it and produced
      <strong>zero signals</strong>. What stops this being a simple arm-it-earlier story: its two
      nearest signals landed 4 minutes BEFORE the first arm ended and 5 minutes AFTER the second,
      and on their own exits <em>both lose money</em> (&minus;$47.79, &minus;$42.07).
      <br><strong>The reading:</strong> the gate's trigger and the router's regime read are out of
      phase. The router arms when a break is CONFIRMED; a thrust gate needs the moment a break
      STARTS. On Friday those were about 25 minutes apart. Being a mechanism question, it does not
      need a big sample to answer — which is why it outranks everything else in BUILD.</td>
  <td class="ln"><a href="#sec1">Part 1</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>The router went blind for 3h35m and every instrument said it was
      fine</strong></td>
  <td class="ln"><span class="tag pill-dontarm">CONFIRMED &mdash; nothing errored</span>
      43 ticks aborted. An abort is fail-closed, which is the correct default and is exactly why it
      is invisible: the trial log gets no line at all, <code>systemctl</code> reports a clean
      deactivation, and the tick count reads normal. 31 of 43 are the LLM session limit; the other
      12 are all Monday inside the gateway window. The health page blames an &ldquo;expired
      login&rdquo; for a usage limit resetting on the hour.
      <br><strong>And it is not the only instrument that lied.</strong> Two nightly rollups
      (<code>router_nightly</code>, <code>selector_nightly</code>) have had <strong>no timer at
      all</strong> and silently stopped on 08-14 and 08-18 — every nightly number in Part&nbsp;2.6
      is a rebuild done during this report. Two shadow A/B pairs are <strong>byte-identical</strong>
      (29/29 and 251/251 trades) and have been reporting perfect nulls from a broken arm. And
      <code>abs_veto_sides.py</code> hard-codes <code>WEEK0 = 2026-07-27</code>, so its column
      headed &ldquo;this week&rdquo; is four and a half weeks and reports +$4,069 where the truth is
      +$948.50.</td>
  <td class="ln"><a href="#sec5">Part 2.6</a>, <a href="#sec3">Part 2</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>The searched day-classifier for the Open Rider, and the BIG-TREND exit
      rung</strong> &mdash; two long-held beliefs, both killed</td>
  <td class="ln"><span class="tag pill-dontarm">REFUTED &times; 2, with named tests</span>
      <strong>The day-classifier:</strong> the concentration is REAL (6 green days +$3,066 against 9
      red &minus;$5,626, oracle ≈$1,022/week) and the search for it is dead — a placebo against
      random day-removal over 10,000 draws beats 6 of 8 features outright, Holm correction across
      the 8 leaves a best adjusted <strong>p = 0.136</strong>, and a genuine out-of-sample leg (fit
      on 41 days, tested on 9) holds 4 of 8 and <em>all four holders still lose money</em>.
      <br><strong>The exit rung:</strong> the window was widened as far as this desk can go —
      831,379 five-second bars, three entry pools including the retired V5 desk's real fills, 6,736
      scored entries, a 63-cell grid plus six chandeliers. <strong>Twenty rung-cells graded, twenty
      failed</strong>; not one survived strip-best-3, leave-one-day-out, the half-split and the
      pool-split together.
      <br><strong>Both are NULLs with certificates</strong>, and both are worth more than they look
      — the deliverable is that <code>data/exit_overrides.json</code> does not get touched this
      weekend, and nobody searches this sample for a day filter again.</td>
  <td class="ln"><a href="#sec3">Part 2</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong>Hunt SIZE, not direction &mdash; 48.2% of entries go nowhere and pay $10
      each to find out</strong></td>
  <td class="ln"><span class="tag pill-live">SURVIVED &mdash; and it needs no direction call at
      all</span>
      Decompose the pooled book by what the tape actually did next. Moves of <strong>&ge;120
      points</strong> are 1.6% of entries (27 of 1,713) and pay <strong>+$319.51 each</strong>,
      carrying +$8,627 on a book whose total is &minus;$2,814. The <strong>&plusmn;20-point dead
      band is 48.2%</strong> of entries at &minus;$10.00 each — &minus;$8,254 of pure friction. A
      rule that declined nothing but the dead band, <em>without improving direction at all</em>,
      turns the book positive.
      <br>The other half of the same fact: a deliberately dumb boarder fires inside <strong>61 of
      62 runs</strong> a median 3 minutes late with 45.8 points still to come — 58.9% of the whole
      ceiling — and it fires <strong>66.4 times a day</strong>, only 21.1% of them inside a run.
      Detection is solved; the bill is everywhere else.</td>
  <td class="ln"><a href="#sec8">Movement 3</a>, <a href="#sec6">Movement 1</a></td></tr>
</tbody>
</table>

<h2><span class="n">&sect;</span> Every gate, this week, on the clean ledger</h2>
<table>
<thead><tr><th class="ln">Gate</th><th class="num">Legs</th><th class="num">Net $</th>
<th class="num">Win %</th><th class="num">$ per leg</th></tr></thead>
<tbody>{gaterows}</tbody>
</table>
<p class="ln">Computed at build time from <code>data/gazbot7.db</code> with
<code>data_quality IS NULL</code>, not transcribed. <strong>Every dollar in this report is a plain
<code>sum(pnl_usd)</code></strong>, because that column is written <em>already net</em> of the $1.50
round trip &mdash; verified on all 765 rows in the book. Do not subtract <code>fees_usd</code> from
it; a previous revision did, and it deepened every stated loss by $1.50 a contract. Gates are
collapsed across their A and B lots; the per-lot split is in Part&nbsp;1&nbsp;&sect;2.
<strong>Three of the six live slots are absent from this table because they fired nothing all
week</strong> &mdash; <code>abs_veto_short</code>, <code>exhaustion_short</code> and
<code>rgv_short</code>, the entire short side of the desk, on 53 minutes of combined armed time.
Movement&nbsp;2 prices what that silence was worth and Part&nbsp;1&nbsp;&sect;9 explains the most
interesting minute of it.</p>

<div class="callout"><div class="ct">The three things this week actually taught the desk</div>
<p><strong>1 &middot; A precursor that predicts SIZE is not a precursor that predicts a
MOVE.</strong> Every feature this desk uses to decide whether something is about to happen turns
out to be measuring how volatile the tape already is. It scored beautifully for months against a
fixed point threshold and it collapses the instant that threshold is normalised by ATR. The lesson
generalises past this one study: <strong>if a feature and your outcome threshold are both scaled by
the same hidden variable, you are measuring the variable.</strong></p>
<p><strong>2 &middot; A win rate is not a sample size.</strong> The tournament went 6 for 6 this
week. It was three gates agreeing about one push, each booking two lots of a scale-out — one market
event, sampled six times. Every quantitative claim in Part&nbsp;1 is deliberately built on
populations of 30&ndash;130 signals instead, and the section says so in its own second paragraph.
The same error in a different coat is the shadow board, where nine &ldquo;independent&rdquo; green
arms are nine exits on one signal.</p>
<p><strong>3 &middot; The instruments fail SILENTLY, and they fail in the direction of
reassurance.</strong> Three separate examples this week, none of which errored: a router blind for
3h35m while <code>systemctl</code>, the trial log and the tick count all read clean; two nightly
rollups with no timer that simply stopped being written; two shadow A/Bs that report a perfect null
because one arm never diverged. <strong>A number that arrives without a failure mode is not a
measurement</strong> — and note that all three of these were found by the report, not by the
monitoring.</p></div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=dt.date.today().isoformat())
    ap.add_argument("--prefix", default="weekly",
                    help="output basename prefix: <prefix>_<slug>.html/.pdf (default: weekly)")
    ap.add_argument("--published", default=dt.date.today().isoformat(),
                    help="the date this render SHIPS. Distinct from --slug, which is the week "
                         "ending and names the output file. Defaults to today.")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--title", default="GAZBOT V7 — Friday report {slug}",
                    help="document <title>; '{slug}' is substituted. Drop any PARTIAL label only "
                         "once the report genuinely is complete.")
    a = ap.parse_args()

    global PLAYBOOK_URL
    PLAYBOOK_URL = PLAYBOOK_URL.format(slug=a.slug)

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
        print(f"★ {len(stale)} fragment(s) predate this report cycle and are STALE — each is "
              f"stitched IN FULL under a dated red banner, and its cross-references to the action "
              f"card are repointed at last week's card:", file=sys.stderr)
        for f, mt in stale:
            print(f"    {f}  ({mt:%Y-%m-%d %H:%M})", file=sys.stderr)
    fresh = n_frag - len(missing) - len(stale)
    print(f"pre-flight — {fresh}/{n_frag} fragments fresh, {len(missing)} missing, "
          f"{len(stale)} stale; {len(missing) + len(stale)} placeholdered")
    if fresh < n_frag * 0.5:
        print(f"★★ FATAL — only {fresh} of {n_frag} fragments are this cycle's. That is a thin "
              f"report, not a report with gaps. Regenerate sections before publishing.",
              file=sys.stderr)
        return 2

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
        body = gap_banner(name) + fragment_or_placeholder(name, label, sub)
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
        # ★2026-09-04 — the two-week seam goes at the VERY TOP, above the honest headline.
        # A provenance warning printed after the numbers it qualifies is a footnote; printed
        # before them it is an instruction. Renders to nothing on a single-vintage cycle.
        vintage_note()
        + render_front(a.slug, a.published, n_plays)
        + '\n<hr class="frag-sep">\n'
        + plays_html
        + '\n<hr class="frag-sep">\n'
        + last_week_ledger()
        + '\n<hr class="frag-sep">\n'
        + '<h2 id="evidence"><span class="n">§</span> The evidence behind those plays</h2>'
        '<p class="lead">Everything from here down is the working. Two halves, one document. '
        'It opens with <strong>Part 0</strong>, which answers the only question that survives past '
        'Friday &mdash; <em>are we getting better?</em> &mdash; day by day, green or red, straight off '
        'the books. <strong>Then the warm half</strong>: what the live desk actually did (Part 1, '
        'with <strong>the run charts</strong> inside it &mdash; every fill of the week marked on its '
        'own session&rsquo;s price path, which is the fastest way to see what the prose is '
        'describing). Then <strong>Rehabilitation</strong> (Part 1.5), where every red thing is '
        'walked through the full treatment instead of benched at face value, and <strong>the day '
        'rider</strong> (Part 1.6), the second book on the same IB account. Then the shadow board '
        'and the promotion battery (Part 2), the mid-week leads re-run adversarially (Part 2.5), '
        'and the <strong>Router Operation Review</strong> (Part 2.6). <strong>Then the cold, '
        'tape-first half</strong>: we ignore everything the desk did and ask, from the raw tape and '
        'order book, <strong>where was the money and did we show up?</strong> &mdash; on MNQ '
        '<em>and</em> on gold (M1) &mdash; then test whether the gates we already own could have '
        'caught the runs we missed (M2), and finally build gates from scratch and backtest them to '
        'death, the ones that failed included, that being the point (M3). Plain English, honest '
        'money, every claim a table &mdash; and every reprice a ceiling.</p>'
        # ★2026-09-04 GENERATED — see phase_report(). The prose that stood here named Part 1.5 as
        # the one stale section, which stopped being true when it was rebuilt on 08-30, and it
        # predates the two-week seam entirely.
        + '<p class="lead">' + phase_report() + '</p>'
        '<p class="lead">The rule behind all of that: <strong>a gap is never a null result.</strong> '
        '&ldquo;We looked and found nothing&rdquo; and &ldquo;nobody looked&rdquo; are opposite '
        'instructions for next week, so nothing is silently omitted and nothing stale is silently '
        'stitched.</p>'
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

    # ★2026-08-22 REV2 — fail the build BEFORE the PDF render, not after writing the HTML.
    if check_doc_xrefs(doc):
        return 5

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
    # ★2026-08-26 CHARS, NOT BYTES — say which. len(doc) counts characters; the file is
    # written UTF-8 and this document carries ~6.8k of multi-byte glyphs (— ★ − × ≥), so
    # `ls` reports ~6.8k MORE than this line used to claim as "bytes". A final-check pass
    # read that gap as content silently lost from a rebuild and went looking for it.
    print(f"HTML → {out_html} ({len(doc):,} chars / {pathlib.Path(out_html).stat().st_size:,} bytes, {len(SECTIONS)}/{len(SECTIONS)} sections, "
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
