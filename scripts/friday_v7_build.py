#!/usr/bin/env python3
"""Assemble the FULL V7 Friday report → light-theme HTML + iPad PDF.

2026-08-08 REVISION 2 BUILD. The 2026-08-08 Rev 1 build was OOM-KILLED mid-run. What it left on
disk looked finished and was not: titled "Rev 1 — PARTIAL, not proofread", ending mid-sentence at
"That is Movement 3's job.", with no Movement 3, no Monday playbook, and a PDF that had been
rendered from an EARLIER copy of the HTML than the one beside it. Three defects made that possible
and all three are now closed:

  * PRE-FLIGHT. Every one of the nine section fragments is checked for existence, non-zero size
    and a minimum body length BEFORE a single byte is stitched. Any failure aborts and NAMES the
    offending files. A missing section used to WARN and build anyway — that is precisely how a
    short report ships looking complete. A named hard failure is always more useful.
  * ONE STRING, ONE PASS. The PDF is rendered from the same `doc` value as the HTML, in the same
    invocation, and is rendered BEFORE the HTML is written — so a PDF failure can never leave a
    newer orphaned HTML behind claiming to be current. Both mtimes are printed on success.
  * SELF-DESCRIBING PLAYS. The number/owner/revert behind each play, plus its evidence tier and
    kill criterion, now live ON the play in reports/friday_v7/plays.json instead of in a
    hand-maintained dict in this file. The action card and the Monday playbook read the same
    file, so they cannot drift. An empty plays.json is a hard failure.

Stitches every pre-baked section fragment into the proven light-theme shell, in the report's
canonical order, and renders a PDF via weasyprint (system python3):

  Front      WHAT TO ACTUALLY DO + honest headline + scorecard  (generated from plays.json)
  Part 1     live desk            part1_live.html
  Part 1.5   REHABILITATION       part1_5_rehab.html
  Part 2     shadow / promotion   part2_shadow.html
  Part 2.5   mid-week musings     part25_musings.html
  Part 2.6   ROUTER REVIEW        part2_6_router_review.html
  Part 2.7   THE DAY RIDER        day_rider.html
  M1         run census           movement1_census.html
  M2         idle-gate lab        movement2_idle_gates.html
  M3         greenfield lab       movement3_greenfield.html

Note on the section directory: one rehab dossier's filename contains a "/" which the writing
agent turned into a real DIRECTORY. Its content is already folded into part1_5_rehab.html, so this
script deliberately reads an EXPLICIT list of fragments and never globs the sections dir.

Build the plays first, then the report, then the playbook:
  python3 scripts/friday_v7_plays_0808.py
  python3 scripts/friday_v7_build.py --slug 2026-08-08
  python3 scripts/friday_v7_monday.py --slug 2026-08-08
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
PLAYBOOK_URL = "/v7/static/monday_2026-08-08.html"
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


# The full report spine, in order. (label, sub-title, fragment file, anchor)
SECTIONS = (
    ("Part 1", "The live desk — what the six-gate paper tournament actually did", "part1_live.html", "sec1"),
    ("Part 1.5", "Live-desk REHABILITATION — never bench a gate at face value", "part1_5_rehab.html", "sec2"),
    ("Part 2", "The shadow desk, the promotion battery &amp; the regime-flex exit lab", "part2_shadow.html", "sec3"),
    ("Part 2.5", "Mid-week musings — every lead from the desk chat, tested hard", "part25_musings.html", "sec4"),
    ("Part 2.6", "ROUTER OPERATION REVIEW — the desk's #1 lever, on the stand", "part2_6_router_review.html", "sec5"),
    ("Part 2.7", "THE DAY RIDER — the second desk, and how we make it work", "day_rider.html", "secdr"),
    ("Movement 1", "The census — the biggest runs on MNQ this week, and did we show up", "movement1_census.html", "sec6"),
    ("Movement 2", "The idle-gate lab — could the gates we own have caught them?", "movement2_idle_gates.html", "sec7"),
    ("Movement 3", "The greenfield lab — brand-new entries, and the chop-day scalp lab", "movement3_greenfield.html", "sec8"),
    # ★2026-08-08 REV2 FOLD-IN. These six were written by the self-proofread pass between 10:49
    # and 11:15 UTC and were NOT in the 10:17 build — the process was OOM-killed at 11:19 before
    # it could fold them in. Each one patches, withdraws or replaces material above it; the
    # matching card edits are in scripts/friday_v7_rev2_fold.py. Anchor p3q1 must stay FIRST:
    # PART3_FIRST keys the Part 3 opener off it.
    ("Part 3.1", "REV2 &middot; Q0 — the ER30 &ge; 0.35 floor on abs_veto_short: put it in the table and it dies in the table", "rev2_q0.html", "p3q1"),
    ("Part 3.2", "REV2 &middot; Q1 — is grind_long on or off on Monday? One population, one number", "rev2_q1.html", "p3q2"),
    ("Part 3.3", "REV2 &middot; Q2 — last Friday's card: did we do those things, and did they work?", "rev2_q2.html", "p3q3"),
    ("Part 3.4", "REV2 &middot; FIX0 — Saturday #3 is not a chandelier play, and as written it cannot be typed into any file the desk reads", "rev2_fix0.html", "p3f0"),
    ("Part 3.5", "REV2 &middot; FIX1 — abs_veto_long: resolving HOLD #1 against Part 2 &sect;4, &sect;5 and &sect;9", "rev2_fix1.html", "p3f1"),
    ("Part 3.6", "REV2 &middot; FIX2 — the ER30 floor through the 54-filter columns it never faced: it keeps 5 of 15 winners", "rev2_fix2.html", "p3f2"),
)

PART3_FIRST = "p3q1"

WINDOWS = (
    # ★2026-08-08 — these three windows are now ordered by EXECUTION LOGIC, not by the size of
    # each play's headline number. #1 and #2 on Saturday are the two the 22:00Z reactivate timer
    # decides for you if you do nothing.
    ("SATURDAY", "w-sat", "TONIGHT — this window shuts at the Sunday 22:00 UTC reopen",
     "Code and config changes that need a restart, <strong>in execution order, not in order of "
     "headline size</strong>. <strong>#1 and #2 are forced</strong>: "
     "<code>gazbot7-gate-reactivate.timer</code> arms every <code>=off</code> gate at 22:00 UTC "
     "Sunday, so for both of them &ldquo;decide later&rdquo; is not one of the available states. "
     "#3&ndash;#6 are safety and measurement, and they come before the two experiments at the "
     "bottom because those experiments cannot be judged without them."),
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
        f'{len(plays)} plays, five windows, in the order they need doing. Every play carries its '
        '<strong>evidence tier</strong> and its <strong>kill criterion</strong> — if a play has no way to '
        'be proven wrong it should not be on the card.</p>',
        # ★2026-08-08 REV2. Item 1 sold the ER30 floor and item 3 sold "ext 2.0 → 3.0"; Part 3
        # withdraws the first and replaces the second with a deletion. This callout is the most
        # prominent text in the document — leaving it stale would have contradicted the card
        # sitting directly beneath it.
        '<div class="callout"><div class="ct">The three that matter most '
        '<span class="tag pill-dontarm">REV2-CORRECTED</span></div>'
        '<p><strong>1 &middot; Sit out the chop (MONDAY&nbsp;#1).</strong> The largest number anywhere in '
        'this document, and it needs no code at all: chop-regime entries cost &minus;$5,483 over 17 days '
        'while everything else made +$1,482 &mdash; perfect avoidance turns &minus;$4,001 into +$1,482. '
        'A perfect chop filter beats every invention in this report by an order of magnitude, and the '
        'router already owns the lever. This is an architectural principle, not a play: '
        '<strong>the edge is refusing rubbish trades, not finding more of them.</strong></p>'
        '<p><strong>2 &middot; abs_veto_short: arm it by default &mdash; and <em>without</em> the ER30 '
        'floor (SATURDAY&nbsp;#1).</strong> This is the biggest single leak in the report and three '
        'independent sections found it. The gate was benched for 91% of the week while its shadow twin '
        'made +$928, and armed for the 9% in which it lost &minus;$559.00 on nine lots without a single '
        'winner. The signal is +$2,290.50 over 159 fires and 4-of-4 weeks green. The router had it '
        'backwards on both sides. <strong>The ER30&nbsp;&ge;&nbsp;0.35 arming floor this play originally '
        'carried is WITHDRAWN as refuted</strong> &mdash; it keeps 5 of 15 winners and discards $1,363 of '
        'profitable trades (<a href="#p3q1">Part&nbsp;3.1</a>, <a href="#p3f2">Part&nbsp;3.6</a>, '
        'corroborated independently in <a href="#p3q3">Part&nbsp;3.3</a>). Arm the gate, ship the '
        'BUILDING&nbsp;&times;&nbsp;US-SESSION veto, leave ER alone. &#9888; Judge the first 15 armed '
        'fires on the <em>armed book alone</em> &mdash; not blended with the shadow twin. On the live '
        'week this gate was <strong>0 for 8 at &minus;$523.50</strong>, the worst short gate on the desk; '
        'the entire case for arming it comes from the continuous book, so the 15-fire review is a hard '
        'gate and not a formality.</p>'
        '<p><strong>3 &middot; grind_long: revert the 08-01 floors (SATURDAY&nbsp;#2).</strong> '
        'ATR&nbsp;10&nbsp;&rarr;&nbsp;22, and <strong>delete</strong> the <code>ext_hi</code> key rather '
        'than pinning it to 3.0 &mdash; everything from 3.0 up scores identically, so a new literal just '
        're-fits the thing the revert is undoing (<a href="#p3q2">Part&nbsp;3.2</a>). One literal changes, '
        'one is removed. Quote the number with its shape attached: <strong>+$4,151</strong> is a delta over '
        '11 tick-honest sessions and 165 legs, of which <strong>21 runner events are the entire result</strong>. '
        '&#9888; The week&rsquo;s six live grind fills all fired at ATR&nbsp;&ge;&nbsp;22 and are silent on '
        'the revert &mdash; do not quote &minus;$172 as support for it. '
        '&#9888; And <code>grind_long</code> is not in <code>reactivate_gates.py::HOLD</code>, so the '
        '22:00&nbsp;UTC Sunday timer re-arms it either way: shipping the floor or adding a HOLD entry are '
        'the only two states available.</p></div>',
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
                f'<span class="why"><strong>Mechanism:</strong> {esc(p["mechanism"])}</span>'
                f'<span class="why"><strong>Why:</strong> {esc(p["rationale"])}</span>'
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
        '<p><strong>The fee is $1.50 per round trip.</strong> Every greenfield number in Movement 3 was '
        'originally priced at ~$5/RT and has been re-priced; the correction is exactly linear '
        '(net@1.50 = net@5.00 + 3.50 &times; n) so it <em>helps</em> everything, winners and losers alike. '
        'A loser the correction rescues was never killed by cost in the first place, and the one row where '
        'that happens is flagged in NOT-AN-ACTION #5.</p>'
        '<p><strong>Three method wounds are still open and they bound everything above.</strong> '
        'The shadow book leaks past its own stops on 44% of trades (median overshoot 0.56&times;ATR), so '
        'every shadow result that rewards cutting early is inflated &mdash; BUILD #3. '
        '<code>signal_journal.suppressed_by</code> is NULL in all 596 rows, so every claim about what a gate '
        '<em>would</em> have done unrouted is a reconstruction from the tape, not a measurement &mdash; '
        'BUILD #5. And microstructure sampling noise is large: on exhaustion_short the standard deviation '
        'across ten polling phases is $418 on a &minus;$880 mean. Anyone quoting a single run of that '
        'harness is quoting noise.</p></div>')
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


def render_front(slug: str, n_plays: int) -> str:
    return f"""
<div class="masthead">
  <h1>GAZBOT V7 &mdash; the Friday report</h1>
  <p class="dates">Week ending {slug} &nbsp;·&nbsp; Mon 3 &ndash; Fri 7 August 2026 &nbsp;·&nbsp;
     MNQ-only &nbsp;·&nbsp; PAPER &nbsp;·&nbsp;
     <strong>REVISION 2</strong>, rebuilt 2026-08-08 &nbsp;·&nbsp; {n_plays} plays &nbsp;·&nbsp;
     9 sections, complete</p>
</div>

<div class="rev3ptr"><strong>What Revision 2 is.</strong> Revision 1 was killed mid-build by the machine
running out of memory. It shipped titled &ldquo;PARTIAL, not proofread&rdquo;, ended mid-sentence at
&ldquo;That is Movement 3's job.&rdquo;, carried <strong>no Movement 3</strong> and <strong>no Monday
playbook</strong>, and its PDF had been rendered from an <em>earlier</em> copy of the HTML than the one on
disk &mdash; so the two artefacts disagreed with each other. Revision 2 replaces all of it. All nine
sections are stitched, the build now refuses to run at all if any section is missing or empty rather than
quietly emitting a short report, and the HTML and the PDF are rendered from one string in one pass so they
cannot diverge again.</div>

<h2 id="honest"><span class="n">★</span> THE HONEST HEADLINE &mdash; the desk lost money, and it is not
mysterious</h2>

<p class="lead">The tournament lost <strong>&minus;$772.50</strong> this week on 110 booked lots. The loss
is not spread around: the <strong>long book made +$345.50 and the short book lost &minus;$1,022.50</strong>,
and one gate &mdash; <strong>abs_veto_short</strong> &mdash; lost <strong>&minus;$559.00 on nine lots
without winning a single one</strong>. Take the shorts away and the week is green.</p>

<p>There is no single honest total, so here are all of them, with what separates each from the next.</p>

<table>
<thead><tr><th class="ln">What you are looking at</th><th class="num">Lots</th><th class="num">Net $</th>
<th class="ln">Why it differs from the row above</th></tr></thead>
<tbody>
<tr><td class="ln">Raw <code>trades</code> rows, 08-03 &rarr; 08-07</td><td class="num">112</td>
    <td class="num">&minus;1,028.00</td>
    <td class="ln">includes the two corrupt MD_STREAM lots</td></tr>
<tr class="row-hl"><td class="ln"><strong>Clean ledger</strong> (<code>data_quality IS NULL</code>)</td>
    <td class="num">110</td><td class="num"><strong>&minus;772.50</strong></td>
    <td class="ln">the desk's real booked money &mdash; this is the number to quote</td></tr>
<tr><td class="ln">Tournament gates only</td><td class="num">108</td><td class="num">&minus;677.00</td>
    <td class="ln">strips the day-rider's cross-desk pair (&minus;$95.50), booked to the tournament by
        Thursday's flatten</td></tr>
<tr><td class="ln">Gate strategy, defects stripped</td><td class="num">104</td>
    <td class="num">&minus;607.00</td>
    <td class="ln">strips the ghost stop and the phantom close &mdash; &minus;$165.50 of the loss was three
        shared-account defects, not a strategy losing money</td></tr>
</tbody>
</table>

<div class="callout"><div class="ct">Read the week by volatility, not by direction</div>
<p>Every tape number below is recomputed from <code>capture.db</code> 5-second bars rolled up to one minute,
not read off a dashboard. <strong>The desk does not lose money on trend days. It loses money on
high-volatility days that go nowhere.</strong> Monday walked 482 points up in the US session at ER 0.171
&mdash; a genuinely good day to be long &mdash; and the desk lost $280 on it. Wednesday and Thursday, the
two days ATR doubled from 12 to 20 points and the tape finished where it started, took
<strong>&minus;$1,122</strong> out of the desk between them. Thursday travelled <strong>9,964 points over
the full session to finish eleven points up</strong> &mdash; ER 0.001, the flattest day in the record. With
n=5 sessions that is an observation, not a law &mdash; but it is the same shape the whole week keeps
making, and it is why the single largest number in this report is an <em>off switch</em>.</p></div>

<table>
<thead><tr><th class="ln">Day</th><th class="num">US net</th><th class="num">US path</th>
<th class="num">US ER</th><th class="num">US ATR</th><th class="ln">Read</th><th class="num">Lots</th>
<th class="num">Wins</th><th class="num">Desk net</th></tr></thead>
<tbody>
<tr><td class="ln">Mon 08-03</td><td class="num">+482</td><td class="num">2,815</td><td class="num">0.171</td>
    <td class="num">12.4</td><td class="ln">clean up-trend</td><td class="num">30</td><td class="num">8</td>
    <td class="num">&minus;280.00</td></tr>
<tr class="row-hl"><td class="ln">Tue 08-04</td><td class="num">+641</td><td class="num">2,799</td>
    <td class="num">0.229</td><td class="num">12.6</td><td class="ln">the week's cleanest trend</td>
    <td class="num">16</td><td class="num">10</td><td class="num">+330.50</td></tr>
<tr class="row-bad"><td class="ln">Wed 08-05</td><td class="num">&minus;367</td><td class="num">4,095</td>
    <td class="num">0.090</td><td class="num">20.1</td><td class="ln">whippy down &mdash; ATR doubled</td>
    <td class="num">29</td><td class="num">4</td><td class="num">&minus;817.00</td></tr>
<tr class="row-bad"><td class="ln">Thu 08-06</td><td class="num">+161</td><td class="num">4,253</td>
    <td class="num">0.038</td><td class="num">20.5</td><td class="ln">pure chop at high vol</td>
    <td class="num">14</td><td class="num">3</td><td class="num">&minus;305.00</td></tr>
<tr class="row-hl"><td class="ln">Fri 08-07</td><td class="num">+120</td><td class="num">3,676</td>
    <td class="num">0.033</td><td class="num">14.2</td><td class="ln">chop, but a real London run at 12:30</td>
    <td class="num">21</td><td class="num">12</td><td class="num">+299.00</td></tr>
</tbody>
</table>

<p>Read that table twice. <strong>The two cleanest trend days produced +$50.50 between them.</strong></p>

<h2 id="scorecard"><span class="n">★</span> THE SCORECARD &mdash; what survived the week, and what did not</h2>

<p class="lead">Six claims went into this week carrying real weight. Here is where each one ended up, with
the test that decided it. Read this before anything else in the report.</p>

<table>
<thead><tr><th class="ln">The claim</th><th class="ln">What it claimed</th>
<th class="ln">Verdict, and the test that decided it</th><th class="ln">Where</th></tr></thead>
<tbody>

<tr class="row-hl">
  <td class="ln"><strong>abs_veto_long is the one gate that works</strong></td>
  <td class="ln">The thrust + 55-second confirm earns its place</td>
  <td class="ln"><span class="tag pill-live">SURVIVED &mdash; the one number worth weight</span>
      16 entries, 32 lots, <strong>+$566.00 at 62%</strong>, average winner +$47.60 against an average loser
      of &minus;$32.20. Still positive if you delete <em>any</em> single day of the week, and still +$363 if
      you delete its three best lots. Everything else on the desk this week is thin, one-week, or explained
      by a software defect.</td>
  <td class="ln"><a href="#sec1">Part 1</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong>Never bench a gate at face value</strong></td>
  <td class="ln">The gates that bled are fixable, not broken</td>
  <td class="ln"><span class="tag pill-live">CONFIRMED &mdash; four of six rehabilitated</span>
      <strong>Not one of the six was broken in the way it looked broken from the roster.</strong> grind_long
      looked like a bad gate and was a bad ATR floor. abs_veto_short looked like a bleeder and was the
      strongest signal on the desk on a 3.3% leash. MAX_HOLD looked like the worst exit on the desk and was
      the fire alarm being blamed for the fire. exhaustion_short looked like an arming problem and is a
      friction problem. nipc_short looked like a wrong-rung problem and is a direction bet. The chandelier
      looked like a threshold that stopped being reached and had been switched off in code.</td>
  <td class="ln"><a href="#sec2">Part 1.5</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>RUN STATE is the primary discriminator</strong> &mdash; carried into the week as
      the desk's headline routing lead</td>
  <td class="ln">in-run aligned +$10.34/trade against chop &minus;$28.43/trade &mdash; a $39/trade spread
      that dwarfs gate, side and time-of-day</td>
  <td class="ln"><span class="tag pill-dontarm">WITHDRAWN AS A ROUTING LEVER</span> The variable is real
      &mdash; it beat 4,000 placebo shuffles twice and held on twelve unseen sessions. <strong>The headline
      cell is not.</strong> Re-derived from scratch on the same 89 trades, in-run-aligned TAKEN goes from
      n=34 &middot; 50% &middot; +$10.34/tr to <strong>n=46 &middot; 41% &middot; &minus;$1.83/tr</strong>,
      and the 34/4/51 split could not be reproduced under <em>any</em> run-span definition tried. Armed
      inside an aligned run the desk made nothing. And the lever is in the wrong place: arming more was
      worth ~$170 this week, but re-pricing the <em>exits</em> on the exact same entries &mdash; changing
      nothing about routing &mdash; turns the week from &minus;$772 into <strong>+$1,493</strong>.
      It is an exit find wearing a router's coat.</td>
  <td class="ln"><a href="#sec4">Part 2.5</a></td></tr>

<tr class="row-hl">
  <td class="ln"><strong>The router is earning its keep</strong></td>
  <td class="ln">The desk's #1 lever, on the stand</td>
  <td class="ln"><span class="tag pill-live">YES &mdash; its first clearly positive week</span>
      <strong>+$2,951</strong> of net value on its own nightly repricing, up from &minus;$1,216 the week
      before, and without thrashing: 1,393 ticks, 66 switch changes, 95.3% of ticks changed nothing. The
      independent check agrees &mdash; the two gates it kept benched had shadow twins losing $4,158 over
      exactly those windows. <strong>The desk still lost $953 on the router's own Paris-day basis, but it
      lost it through gates the router had ARMED, not gates it failed to bench.</strong></td>
  <td class="ln"><a href="#sec5">Part 2.6</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>The day-rider's exit is exit-proof &mdash; holding wins</strong></td>
  <td class="ln">25 exit variants tested, holding beat every one</td>
  <td class="ln"><span class="tag pill-dontarm">HALF WRONG</span> Re-run over 38 sessions scoring
      <strong>114</strong> ways of ending a ride on identical entries: holding still beats every stop, but
      <strong>its whole edge is three days</strong> &mdash; strip them and $5,410 becomes $379. The seven
      days that lost $1,000+ lost &minus;$11,195 between them and the trail we shipped last Friday saves
      <strong>exactly $0.00</strong> on every one, because price never went our way at all. The exit
      parameter surface is noise (Spearman &minus;0.30 between in- and out-of-sample rank). <strong>The
      entry is the lever</strong>: efficiency floor 0.15 &rarr; 0.25 takes the same 38 sessions from
      +$5,410 to +$8,819, 32 of 32 leave-one-out folds positive.</td>
  <td class="ln"><a href="#secdr">Part 2.7</a></td></tr>

<tr class="row-bad">
  <td class="ln"><strong>The greenfield lab will find us a new gate</strong></td>
  <td class="ln">$9,917 of hindsight money sat in 54 runs we sat out &mdash; go build something that
      catches them</td>
  <td class="ln"><span class="tag pill-shadow">ONE SURVIVOR, AND IT GOES TO SHADOW</span> Three hunts from
      a blank sheet; two came back with nothing. The OPEN RIDER &mdash; no trigger at all, just show up
      every five minutes in the open window facing the way the last fifteen minutes went, with a stop twice
      the house width &mdash; made money on 36 days including <strong>19 it was never fitted on</strong>
      (+$30.66/trade out of sample against +$32.29 in, a 5% degradation). Three independent skeptics were
      told to destroy it; <strong>the vote was 2&ndash;1, not 3&ndash;0</strong>. It goes to the shadow
      book. <strong>Nothing from this week's greenfield goes live &mdash; 17 in-sample days earns SHADOW at
      most.</strong></td>
  <td class="ln"><a href="#sec8">Movement 3</a></td></tr>
</tbody>
</table>

<div class="callout"><div class="ct">The three things this week actually taught the desk</div>
<p><strong>1 &middot; The arming is worth more than the exits, and the exits are worth more than the
entries.</strong> abs_veto_short's signal is +$2,290.50 over 159 fires and the desk had it benched for 91%
of the week; the same section shows re-pricing exits on entries we already took is worth +$2,265 of swing.
Every new gate invented from scratch this week is worth less than either.</p>
<p><strong>2 &middot; We are late, not wrong.</strong> Entered on the ignition minute with an honest racing
exit, the 52 sat-out runs pay <strong>+$6,846 &mdash; 71% of their hindsight ceiling</strong>. Turn up two
minutes later and it is +$6,041; five minutes, +$4,090; ten, +$944; fifteen,
<strong>&minus;$2,068</strong>. Every minute of confirmation costs about $600. That is why the idle-gate lab
is a null: our gates fire seven to eight minutes before the money.</p>
<p><strong>3 &middot; Our house stop is the wrong instrument for the open.</strong> Three independent routes
&mdash; a 45-cell grid, a from-scratch skeptic rebuild, and the oracle &mdash; agree that every cell at a
1-ATR stop is flat-to-negative and all 27 cells at 2.0&times;ATR or wider are positive. Even a perfect entry
is shaken out of 14 of 52 runs at 1 ATR, against 0 of 52 at 2 ATR. Checking that on the live gates costs
nothing.</p></div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=dt.date.today().isoformat())
    ap.add_argument("--prefix", default="weekly",
                    help="output basename prefix: <prefix>_<slug>.html/.pdf (default: weekly)")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--title", default="GAZBOT V7 — Friday report {slug} (Rev 2)",
                    help="document <title>; '{slug}' is substituted. Drop any PARTIAL label only "
                         "once the report genuinely is complete.")
    a = ap.parse_args()

    if check_xrefs() != 0:
        return 3

    tpl = pathlib.Path(CSS_TEMPLATE).read_text()
    m = re.search(r"<style.*?</style>", tpl, re.S | re.I)
    css = m.group(0) if m else "<style>body{font-family:Georgia,serif;max-width:900px;margin:auto}</style>"

    # ★2026-08-08 PRE-FLIGHT. Verify EVERY fragment exists and is non-empty BEFORE stitching
    # anything. The 08-07 build emitted a short report with no Movement 3 and no Monday playbook
    # because a missing section only WARNED; silent truncation is the exact failure this replaces.
    # A named hard failure is always more useful than a quietly short report.
    problems = []
    for _label, _sub, name, _anchor in SECTIONS:
        p = pathlib.Path(SEC) / name
        if not p.is_file():
            problems.append(f"MISSING   {name}")
        elif p.stat().st_size == 0:
            problems.append(f"EMPTY     {name} (0 bytes)")
        elif len(p.read_text().strip()) < 200:
            problems.append(f"TRUNCATED {name} ({p.stat().st_size} bytes — under the 200-char floor)")
    if problems:
        print("=" * 72, file=sys.stderr)
        print(f"FATAL — {len(problems)} of {len(SECTIONS)} sections are not fit to stitch:",
              file=sys.stderr)
        for q in problems:
            print("  " + q, file=sys.stderr)
        print("Nothing was written. Fix the sections above and re-run — a short report is worse\n"
              "than no report, because it looks finished.", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        return 2
    print(f"pre-flight OK — {len(SECTIONS)}/{len(SECTIONS)} sections present and non-empty")

    # Explicit fragment list — never glob the sections dir (see module docstring).
    frags, toc = [], []
    for label, sub, name, anchor in SECTIONS:
        p = pathlib.Path(SEC) / name
        opener = ""
        if anchor == PART3_FIRST:
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
        frags.append(f'{opener}<section id="{anchor}">{p.read_text()}</section>')
        toc.append(f'<li><span class="lab">{label}</span> &mdash; <a href="#{anchor}">{sub}</a></li>')

    plays_html, n_plays = render_plays()

    intro = (
        render_front(a.slug, n_plays)
        + '\n<hr class="frag-sep">\n'
        + plays_html
        + '\n<hr class="frag-sep">\n'
        + '<h2 id="evidence"><span class="n">§</span> The evidence behind those plays</h2>'
        '<p class="lead">Everything from here down is the working. Two halves, one document. '
        '<strong>The warm half</strong> is what the live paper tournament actually did this week '
        '(Part 1), then the section that matters most &mdash; <strong>Rehabilitation</strong> (Part 1.5), '
        'where every red gate and leaky exit is walked through the full six-step wash instead of being '
        'benched at face value. Then the shadow board and the promotion it did <em>not</em> earn (Part 2), '
        'the mid-week leads re-run adversarially on the week\'s own data (Part 2.5), the '
        '<strong>Router Operation Review</strong> (Part 2.6), and <strong>the Day Rider</strong> &mdash; the '
        'second desk, rebuilt from the raw tape over 38 sessions (Part 2.7). '
        '<strong>Then the cold, tape-first half</strong>: we ignore everything the desk did and ask, from the '
        'raw MNQ tape and order book, <strong>where was the money and did we show up?</strong> (M1) &mdash; '
        'then test whether the gates we already own could have caught the runs we missed (M2), and finally '
        'build brand-new gates from scratch and backtest them to death, the ones that failed included, that '
        'is the point (M3). Plain English, honest money, every claim a table &mdash; and every reprice a '
        'ceiling.</p>'
        '<div class="v7toc"><h3>What is in here</h3><ol>'
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
