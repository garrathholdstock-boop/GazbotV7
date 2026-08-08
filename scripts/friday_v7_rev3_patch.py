#!/usr/bin/env python3
"""REV3 in-place corrections to the Friday-report section fragments.

Why this exists: the Rev2 fold-in reported success and landed 2 of 5 sections, leaving the
published report arguing with itself in ten places. This script applies the exact minimal fixes
listed in reports/friday_v7/sections/rev3_consistency_audit.html — AND the further corrections
from the three REV3 re-derivations (rev3_trendup_router / rev3_dead_floors / rev3_grind_exit),
which in three cases overturn what the audit itself prescribed.

Discipline, because silent partial success is the failure this revision exists to fix:
  * every replacement asserts its expected hit-count and the script ABORTS on any miss;
  * nothing is deleted — every superseded claim stays on the page with a visible correction
    attached, so the audit trail survives;
  * it is idempotent: the first run snapshots each fragment to <name>.rev2-orig and every
    later run restores from that snapshot before re-patching.

Run with system python3.  python3 scripts/friday_v7_rev3_patch.py
"""
from __future__ import annotations

import pathlib
import sys

SEC = pathlib.Path("/home/alphabot/gazbot7/reports/friday_v7/sections")

FILES = [
    "part1_live.html",
    "part1_5_rehab.html",
    "part2_shadow.html",
    "part25_musings.html",
    "part2_6_router_review.html",
    "movement3_greenfield.html",
]


def cor(title: str, body: str) -> str:
    """A visible REV3 correction block. Never replaces the original claim — sits beside it."""
    return (f'<div class="rev3"><div class="ct">&#9733; REV3 correction &mdash; 2026-08-01 &mdash; {title}</div>'
            f'{body}</div>')


def ptr(where: str) -> str:
    """Superseded-section pointer, dropped at the very top of a fragment."""
    return (f'<div class="rev3ptr"><strong>&#9654; Read this section with REV3 open.</strong> {where} '
            f'The corrections are marked inline in red where they bite, and the full working is in '
            f'<a href="#part3">Part 3 &mdash; the Rev2/Rev3 corrections</a>. '
            f'Nothing has been deleted: where a claim was overturned, the original is still printed '
            f'next to what replaced it.</div>')


# ----------------------------------------------------------------------------------
# The dead-floors callout, repeated verbatim in the three places that reason from a
# floor that has not executed since Wednesday.
# ----------------------------------------------------------------------------------
DEAD_FLOORS = cor(
    "every ER and ATR floor on this desk has been switched off since 2026-07-29",
    '<p><strong>Nothing below that leans on a live ER or ATR floor is describing the desk you own.</strong> '
    '<code>tournament.step()</code> hands the sub-slot tag (<code>grind_long_A</code>) to '
    '<code>er_blocks()</code>/<code>atr_blocks()</code>, but <code>ER_FLOOR</code>/<code>ATR_FLOOR</code> are '
    'keyed on base names, so the lookup never matches and every floor silently answers "don\'t block". '
    'Dead since the dual-slot cutover at <strong>2026-07-29 16:20:49 UTC</strong>; last suppression line '
    '07-29T13:29:04Z, zero since. Five gates affected. The <code>_base()</code> helper that fixes it already '
    'exists at <code>tournament.py:86</code> and is applied correctly three times elsewhere &mdash; just not '
    'at lines 139 and 142.</p>'
    '<p><strong>Size it honestly:</strong> the circulating "7,734 suppressions" is a raw log-line count and the '
    'check re-fires every ~1s tick. De-duplicated it is <strong>383 blocked signal episodes over 8 days</strong> '
    '(140 ER + 243 ATR) &mdash; about 48 a day, not thousands. Real, but 44&times; smaller than advertised.</p>'
    '<p><strong>And it changes the conclusion, not just the footnote.</strong> Grind did not fire 52 of 56 times '
    'below its floor because "ER filters are fake on this tape" &mdash; a claim about the market. It fired '
    'because <em>there was no floor</em> &mdash; a claim about our code. Those point at completely different '
    'fixes. Both ER floors were even committed ~18 hours <em>after</em> the bug, so neither has ever blocked a '
    'single trade in production. Full working, per-gate verdicts and the mandatory ship order: '
    '<a href="#p3floors">Part 3.6</a>.</p>')


PATCHES: list[tuple[str, str, str, int]] = []


def P(fname: str, old: str, new: str, count: int = 1) -> None:
    PATCHES.append((fname, old, new, count))


# ==================================================================================
# PART 1 — the live desk
# ==================================================================================
P("part1_live.html",
  "<h2><span class=\"n\">Part 1</span> The Live Desk — the week the router earned its keep</h2>",
  "<h2><span class=\"n\">Part 1</span> The Live Desk — the week the router earned its keep</h2>\n"
  + ptr("Three claims in here were overturned this weekend: exhaustion_short is <strong>not</strong> the "
        "week's earner once your hands come off it, grind's \"0.35 ER floor\" has never executed, and "
        "Thursday's +$1,172 record is a session-boundary artefact of nine hand-claims."))

# (a) the re-crowning, ninety words after the correction
P("part1_live.html",
  "+$316 for the week. It is the steadiest earner on the desk.",
  "+$316 for the week. <strong>&#9654; REV3: $372.5 of that +$316 was four trades you closed by hand.</strong> "
  "Automated it is <strong>&minus;$56 over 44 fires</strong> (see the callout above). It is the steadiest "
  "<em>thing</em> on the desk, not the biggest earner: 50% win, a median trade of essentially zero, and the "
  "smallest leave-one-day-out damage of any gate that traded in size.")

# (b) the card-table verdict cell
P("part1_live.html",
  '<td><span class="tag">SURVIVOR — steadiest</span></td>',
  '<td><span class="tag pill-dontarm">FLAT AUTOMATED (&minus;$56 / 44)</span> <span class="was">SURVIVOR '
  '&mdash; steadiest</span> &mdash; the +$316 includes 4 hand-claims</td>')

# (c) the gate x day grid closing line + the dead floor it reasons from
P("part1_live.html",
  "That is not a flaw — it's what the 0.35 ER floor is <em>for</em>, keeping it dormant unless the day really "
  "trends — but it does mean grind's +$184 for the week is one great day minus two poor ones, not a broad "
  "edge. Compare exhaustion's row: green four days out of five, never a monster but never a disaster until "
  "Friday's open. That row is why exhaustion is the survivor.</p>",
  "That is not a flaw — it's what the 0.35 ER floor <em>would</em> be for, keeping it dormant unless the day "
  "really trends — <strong>&#9654; REV3: except that floor has never executed once. It is keyed on "
  "<code>grind_long</code> while the live slots are called <code>grind_long_A</code>/<code>_B</code>, so it has "
  "been a no-op since 07-29 (<a href='#p3floors'>Part 3.6</a>).</strong> Either way grind's +$184 for the week is one great day minus "
  "two poor ones, not a broad edge. Compare exhaustion's row: green four days out of five, never a monster but "
  "never a disaster until Friday's open. <span class=\"was\">That row is why exhaustion is the survivor.</span> "
  "<strong>&#9654; REV3: that row is why exhaustion is the <em>steadiest</em> &mdash; read against the automated "
  "split above, unattended the row is flat.</strong></p>")

# (d) Case 1 Thursday — the four fade-claims
P("part1_live.html",
  "netting +$217 on the day — but that four-in-a-row is the exhaustion edge on full display: judge this gate "
  "on its live fades, not its fixed-target shadow.</p>",
  "netting +$217 on the day — but that four-in-a-row is the exhaustion edge on full display: judge this gate "
  "on its live fades, not its fixed-target shadow.</p>"
  + cor("those four fades were four hand-clicks, and the machine would have lost on them",
        "<p>All four were <code>MANUAL_CLAIM</code> exits &mdash; <strong>you</strong> closed them. Repriced on "
        "250&nbsp;ms tape under the exit config that was actually loaded at the time, the same four entries "
        "come out at <strong>&minus;$51.2</strong>, and three of the four were sitting on positions the tape "
        "later ran 49 to 98 points through the stop. So the router's best-graded offensive call of the week "
        "(Part 2.6 &sect;2 credits it +$372) is worth &minus;$51 to the machine. That is a $423 swing inside "
        "the router's own scorecard.</p>"))

# (e) the +$1,172 record, and the two day-tables that disagree
P("part1_live.html",
  "<strong>one best-ever day (+$1,172 on Thursday)</strong>",
  "<strong>one best-ever day (+$1,172 on Thursday)</strong> <strong>&#9654; REV3: +$1,172 on the Paris "
  "boundary; +$94 on the UTC day (Movement 3 books it that way), and &minus;$884.5 of it is automated &mdash; "
  "nine hand-claims are what made it a record.</strong>")

P("part1_live.html",
  "(Thursday's +$1,172 is the best single day the desk has ever booked)",
  "(Thursday's +$1,172 is the best single day the desk has ever booked <strong>on this boundary</strong> "
  "&mdash; Movement 3 books the same trades on the UTC calendar day and gets +$94; same week total, different "
  "day buckets)")

# ==================================================================================
# PART 1.5 — rehabilitation
# ==================================================================================
P("part1_5_rehab.html",
  "<h3>The scoreboard — read this first</h3>",
  ptr("The grind_long rehab's headline &pound;-figure was measured against a baseline that was never running. "
      "The honest before/after is <strong>+$1,552 &rarr; +$2,830</strong>, and the ATR floor should be "
      "<strong>10, not 12</strong>.")
  + "<h3>The scoreboard — read this first</h3>")

# summary-table baseline
P("part1_5_rehab.html",
  '<td>Two live floors were strangling it; it bought stretched tops</td><td class="num">−$284</td>'
  '<td class="num">+$2,830</td>',
  '<td>Two floors were configured against it (neither was executing); it bought stretched tops</td>'
  '<td class="num">+$1,552 <span class="was">−$284</span></td><td class="num">+$2,830</td>')

P("part1_5_rehab.html",
  "<p>Two live floors are actively destroying the gate. The <strong>ER ≥ 0.35 floor is backwards</strong>",
  DEAD_FLOORS
  + "<p>Two floors are <em>configured</em> against this gate — and <strong>neither has executed since "
    "07-29</strong>, so they cannot have destroyed anything this week; as written they are backwards and too "
    "tight, which is exactly why they must not be re-wired at their current values. The "
    "<strong>ER ≥ 0.35 floor is backwards</strong>")

# the LIVE-vs-RECOMMENDED comparison, with the corrected baseline and ATR 10
P("part1_5_rehab.html",
  '<thead><tr><th>Config (tick-honest, same tape)</th><th class="num">n</th><th class="num">net</th>'
  '<th class="num">win%</th><th class="num">strip top-3</th></tr></thead>\n<tbody>\n'
  '<tr class="row-bad"><td class="ln">LIVE (ER≥.35 &amp; ATR≥24)</td><td class="num">11</td>'
  '<td class="num">−$284</td><td class="num">18%</td><td class="num">−$1,161</td></tr>\n'
  '<tr class="row-hl"><td class="ln">RECOMMENDED (drop ER floor, ATR 24→12, ext_atr ≤ 2.0)</td>'
  '<td class="num">111</td><td class="num">+$2,830</td><td class="num">34%</td>'
  '<td class="num">+$1,172</td></tr>\n</tbody>',
  '<thead><tr><th>Config (tick-honest, same tape)</th><th class="num">n</th><th class="num">net</th>'
  '<th class="num">$/trade</th><th class="num">win%</th><th class="num">strip top-3</th></tr></thead>\n<tbody>\n'
  '<tr class="row-bad"><td class="ln">LIVE <em>as written</em> (ER≥.35 &amp; ATR≥24) — a config that was '
  'never actually running</td><td class="num">11</td><td class="num">−$284</td><td class="num">−$26</td>'
  '<td class="num">18%</td><td class="num">−$1,161</td></tr>\n'
  '<tr class="row-bad"><td class="ln"><strong>&#9654; REV3 — LIVE <em>as actually running</em></strong> '
  '(floors dead since 07-29, ext_atr uncapped)</td><td class="num">181</td>'
  '<td class="num"><strong>+$1,552</strong></td><td class="num">+$8.6</td><td class="num">34%</td>'
  '<td class="num">—</td></tr>\n'
  '<tr class="row-hl"><td class="ln">RECOMMENDED (drop ER floor, ATR 24→<span class="was">12</span> '
  '<strong>10</strong>, ext_atr ≤ 2.0)</td><td class="num">111</td><td class="num">+$2,830</td>'
  '<td class="num">+$25</td><td class="num">34%</td><td class="num">+$1,172</td></tr>\n</tbody>'
  + cor("read the n before you read the delta, and use ATR 10",
        '<p><strong>This is not the same eleven trades made profitable.</strong> The recommended config trades '
        'ten times as often — it is a different, ten-times-larger book (−$26/trade vs +$25/trade). And the '
        '"before" row is a counterfactual: the rehab replay <em>applied</em> the floors as config '
        '(<code>rehab_grind_long.py:124</code>, <code>:234</code>) while the live desk has had them switched '
        'off since 07-29. Measured against what was really running, the honest before/after is '
        '<strong>+$1,552 &rarr; +$2,830</strong>, not −$284 &rarr; +$2,830 — about 59% of the advertised '
        'delta is the removal of filters that were already de-facto removed.</p>'
        '<p><strong>Ship ATR 10, not 12.</strong> Re-derived fine on 8 days of tick-honest replay: 9/10/11 is a '
        'genuine plateau where the blocked book is robustly negative; at 12 the blocked book flips positive and '
        'stays positive all the way up. Twelve is one notch the wrong side of the cliff and costs $941 against '
        '10. On every measure — net, per-signal, win%, strip-best-3, worst leave-one-day-out and both '
        'out-of-sample halves — ATR 10 + ext_atr 2.0 beats ATR 12 + ext_atr 2.0.</p>'
        '<p><strong>And the money is not bankable.</strong> Grind is a high-count, low-margin book: the best '
        'config breaks even at a 1.64&times; loss multiplier and the desk\'s standing finding is that live '
        'losses run 1.1–3.1&times; modelled. That break-even sits <em>inside</em> the band. The ceiling buys '
        'resilience (at 1.5&times; losses: capped +$358 vs uncapped −$1,449), not dollars. Grind is being made '
        'less bad, not good — which is why the play card for this now carries &pound;0, not &pound;700.</p>'))

# rgv_short live-state check
P("part1_5_rehab.html",
  "<h3>5. rgv_short — back to the bench, honestly</h3>",
  "<h3>5. rgv_short — back to the bench, honestly</h3>"
  + cor("this verdict and the live desk disagree right now",
        "<p><strong>Live-state check, 08-01:</strong> <code>rgv_short=on</code> in "
        "<code>data/gate_switches.env</code> &mdash; verified in the file today. Every section of this report "
        "verdicts it SHADOW and Part 1 says the router \"correctly kept it in the dugout\", but it is armed. "
        "Bench it or change the verdict; do not leave both standing. This is the MONDAY&nbsp;#3 play.</p>"))

# ==================================================================================
# PART 2 — shadow / promotion / exit lab
# ==================================================================================
P("part2_shadow.html",
  "<h3>The shadow board, ranked on honest money</h3>",
  ptr("Four things in here were overturned: abs_veto was never a promotion (it shipped 07-25), the "
      "&quot;+$326 over 47&quot; figure is wrong, the BIG-TREND cell is n=24 not n=5, and the "
      "&quot;exit is not the lever&quot; instruction is wrong for the live abs_veto_long cell.")
  + "<h3>The shadow board, ranked on honest money</h3>"
  + cor("shadow runs 1 lot, the live scale-out runs 2 — never compare the raw dollars",
        "<p>Standing note for every shadow-vs-live comparison in this section: <strong>the shadow runs 1 lot; "
        "the live scale-out runs 2.</strong> No raw shadow-vs-live dollar comparison is valid without dividing "
        "the live number by <em>signals</em>, not lots. That single omission is what produced the "
        "$326-vs-$776 confusion below.</p>"))

P("part2_shadow.html",
  "live <code>abs_veto_long</code> made <strong>+$326 over 47 trades</strong> this week",
  "live <code>abs_veto_long</code> made <strong>+$59.5 over 59 lots (43 signals)</strong> this week "
  "<strong>&#9654; REV3: the folded-in correction printed <span class=\"was\">+$326 over 47 trades</span>, "
  "which is wrong by $266.5 and contradicts Part 1's own card table in this same document. Straight from "
  "<code>data/gazbot7.db</code> it is +$59.5 / 59 lots; no window produces $326/47.</strong>")

P("part2_shadow.html",
  "is the real Saturday job, and it is NOT yet done in this report.</p>",
  "is the real Saturday job. <strong>&#9654; REV3: it is now done.</strong> Of the $609.5 gap, "
  "<strong>82% is entry</strong> &mdash; 26 long signals the router had benched, worth +$397 in shadow &mdash; "
  "plus $107 of window mismatch and $273.5 of <code>STOP_UNFILLED</code>. Net of fees and that stop bug the "
  "live exit design is about <strong>+$67 ahead</strong> of the shadow. <strong>The bench cost the money, not "
  "the exit.</strong></p>")

P("part2_shadow.html",
  '<strong>Verdict: PROMOTE, and promote it TWO-SIDED. <span class="tag">promote 2-sided</span></strong>',
  '<strong>Verdict: ALREADY LIVE TWO-SIDED &mdash; RE-VALIDATED COLD. '
  '<span class="tag pill-null">no action</span></strong> '
  '<span class="was">Verdict: PROMOTE, and promote it TWO-SIDED.</span> '
  '<strong>&#9654; REV3: there is nothing to promote.</strong> <code>abs_veto_long</code> and '
  '<code>abs_veto_short</code> have both been armed since the 07-25 roster change &mdash; verified in '
  '<code>gate_switches.env</code> today. What the cold re-validation earns is confidence in a gate that is '
  'already running, plus exactly one config change: the long-side exit cell (below).')

P("part2_shadow.html",
  "But of everything on the board, this is the one that has earned a live slot, and clipping it to short-only "
  "leaves roughly half its proven money on the floor.",
  "But of everything on the board, this is the one that has earned a live slot. "
  "<span class=\"was\">…and clipping it to short-only leaves roughly half its proven money on the floor.</span> "
  "<strong>&#9654; REV3: nothing has clipped it to short-only. That sentence was written against a roster that "
  "changed a week before this report.</strong>")

# LAB (a) — the exhaustion era mislabel
P("part2_shadow.html",
  "For honest comparison the prior era (07-27&ndash;07-31, A@2.5R + chandelier, 37 trades) netted +$365 with a "
  "healthy 11 targets / 10 chandeliers / 16 stops mix. Two signals cannot overturn that &mdash; let it run and "
  "re-grade with real n.",
  "<span class=\"was\">For honest comparison the prior era (07-27–07-31, A@2.5R + chandelier, 37 trades) "
  "netted +$365 with a healthy 11 targets / 10 chandeliers / 16 stops mix.</span> "
  "<strong>&#9654; REV3: the prior era was not the same machine, and that mislabel hides the whole causal "
  "story.</strong> Until Wed 07-29 19:10 UTC exhaustion ran a <strong>single slot on the regime-3 adaptive "
  "chandelier</strong>: 37 automated fills, +$365, PF 1.46, green on all 3 of its days. The scale-out slate "
  "that replaced it (A@2.5R + wide lock-chandelier) is <strong>&minus;$421 over 7 fills at 14% win</strong>. "
  "The gate did not break; its exit was swapped for a trend-riding one, and a fader does not get 2.5R in a "
  "whipsaw."
  + cor("the Rs can be graded even though the live trial cannot",
        "<p>A 64-entry 250&nbsp;ms sweep does grade them: the loaded <strong>0.5R Lot A is the worst scalp "
        "rung on the ladder</strong> (+$306); the plateau is 0.75–1.0R (+$510 / +$450); and Lot B's steadiest "
        "config by a distance is a <strong>k1.5 chandelier</strong> (+$502, the highest leave-one-day-out floor "
        "in the whole sweep at +$330, worst day −$25). That is the MONDAY&nbsp;#4 play.</p>"
        "<p><strong>But the sweep's real message is that no exit is robustly green in violent whipsaw</strong>, "
        "where this gate took 28 of its 62 entries — the k1.5 chandelier is the <em>worst</em> config in that "
        "bucket at −$202. Keeping it benched there is worth more than any R.</p>"
        "<p><strong>Method caveat added 08-01:</strong> this cell came from a per-signal sweep on overlapping "
        "entries — the same accounting that was just shown to swing grind's exit verdict by $5,076 "
        "(<a href='#p3grindexit'>Part 3.7</a>). Not refuted; re-run it under a sequential one-position-per-slot sim before trusting the "
        "size of the gain. Cheap to revert either way.</p>"))

# LAB (b) — BIG-TREND n
P("part2_shadow.html",
  '<td class="ln">BIG-TREND (5)</td><td class="ln">2.5 / wide-chandelier</td>'
  '<td class="ln">wideChand &times;2 (+$12.0) &mdash; n=5</td><td class="num"><span class="tag">UNTESTED</span></td>',
  '<td class="ln">BIG-TREND (<strong>24</strong> <span class="was">5</span>)</td>'
  '<td class="ln">2.5 / wide-chandelier</td>'
  '<td class="ln">wideChand &times;2 (+$12.0) &mdash; n=<strong>24</strong></td>'
  '<td class="num"><span class="tag">DIRECTION SUPPORTED</span> (bootstrap P=0.95, plateau 2.5–3.5R, both '
  'time-halves agree) &middot; <span class="tag pill-null">MAGNITUDE UNPROVEN</span> (strip-3 takes +$62 to '
  '+$10)</td>')

# LAB (b) — the archive refusal
P("part2_shadow.html",
  "I did <em>not</em> manufacture a BIG-TREND sample from the retired V5 archive: it is a different desk, "
  "contract era and gate set, and repricing V7 gate entries on it would be a fabricated comparison, not an "
  "honest one. The only honest tick tape available (V7 capture.db) spans 07-15 to 07-31 and simply does not "
  "contain a clean trend week for grind. That remains the #1 unturned stone &mdash; the RIDE rung must be "
  "proven on the next genuine trend week (live-forward or a matching-instrument archive), and until then "
  "grind's BIG-TREND exit is a guess wearing an n=5 hat.",
  "<span class=\"was\">I did not manufacture a BIG-TREND sample from the retired V5 archive: it is a different "
  "desk, contract era and gate set, and repricing V7 gate entries on it would be a fabricated comparison, not "
  "an honest one&hellip; grind's BIG-TREND exit is a guess wearing an n=5 hat.</span>"
  + cor("that refusal was false, and this lab had already used the archive",
        "<p><strong>Eleven of the 24 BIG-TREND entries already come from that pre-capture MNQ archive</strong> "
        "(<code>ticks.db</code>, 07-05&rarr;07-15). The lab tape starts 07-05, not 07-15. And the \"different "
        "contract era\" objection dies on the seam: last archive tick 29,623.00 at 15:35:29.973, first capture "
        "bar opens 29,622.75 at 15:35:30, r=0.9998 across 2,925 overlapping minutes. Same instrument, same "
        "front month. A report that invents a principled refusal for tape it silently consumed is worse off "
        "than one that never mentioned it.</p>"
        "<p><strong>What is genuinely missing is n, not honesty.</strong> The pre-registered grade needs 39 "
        "paired entries (from a paired sd of $247 on a $79.4 diff) and we have 24. Grade date Friday "
        "2026-08-21, hard backstop 09-11.</p>"
        "<p><strong>And this rung is LIVE today, not an unturned stone.</strong> "
        "<code>data/exit_overrides.json</code> keys only <code>exhaustion_short</code>, "
        "<code>abs_veto_long</code> and <code>abs_veto_short</code>. <code>grind_long</code> has no entry, so "
        "it inherits the built-in <code>_BIG_RUN</code> default, which <em>is</em> Lot A @ 2.5R + Lot B wide "
        "lock-chandelier. It is not a stone left unturned; it is an unhedged live position.</p>"))

# LAB — the "exit is not the lever" bullet
P("part2_shadow.html",
  "<br>&bull; <strong>thrust, rgv and capitulation bleed in every regime no matter what exit you put on "
  "them.</strong> That is the headline finding: for these three, the exit is not the lever",
  "<br>&bull; <strong>the RAW, UN-VETOED versions of thrust, rgv and capitulation bleed in every regime no "
  "matter what exit you put on them.</strong> That is the headline finding: for <em>those</em> three, the exit "
  "is not the lever <strong>&#9654; REV3: note the population. This row is the raw un-vetoed thrust, and the "
  "report then applies the conclusion by name to <code>abs_veto</code>, which is a different, filtered book. "
  "That sample-switch inside one sentence is what produced the wrong instruction below.</strong>")

# LAB — the policy-table cell that instructs inaction
P("part2_shadow.html",
  '<tr><td class="ln">thrust / abs_veto</td><td class="ln" colspan="4">exit is not the lever &mdash; keep the '
  'abs_veto entry veto; manage via gate on/off, not exit style</td></tr>',
  '<tr><td class="ln">thrust / abs_veto</td><td class="ln" colspan="4">'
  '<span class="was">exit is not the lever — keep the abs_veto entry veto; manage via gate on/off, not exit '
  'style</span><br><strong>&#9654; REV3:</strong> the raw un-vetoed <em>thrust</em> cannot be rescued by an '
  'exit &mdash; but the LIVE <strong>abs_veto_long</strong> cell can, and it is the worst cell on the board. A '
  'tick-honest sweep of 81 long signals ranks the loaded <strong>A1.5/B2.5 last of eleven</strong> '
  '(+$13.6/sig, LODO-min +$4.7) against <strong>A1.0/B1.5</strong> (+$22.7, LODO-min +$16.8), on a broad '
  'plateau (0.75/1.5, 1.0/1.5, 1.0/2.0 all within $4). A second, independent sweep on 42 automated entries '
  'reached the same answer from different data. Worth ~+$390/week at the live rate of 43 long signals. '
  '<strong>Change <code>exit_overrides.json &rarr; abs_veto_long: {a_r 1.0, b 1.5}</code>. Leave '
  '<code>abs_veto_short</code> at 1.5/2.5</strong> &mdash; on that side the R choice is genuinely noise '
  '(+$15 to +$18 at every cell). No exit rescues abs_veto_short in violent whipsaw (−$20 to −$33 at every R '
  'from 0.5 to 6.0); only not trading it does.</td></tr>')

# LAB — policy table grind row + the missing MED-TREND prize
P("part2_shadow.html",
  '<tr><td class="ln">grind_long</td><td class="ln">wide-chandelier <em>(unproven, n=5)</em></td>'
  '<td class="ln">scalp 0.5 / 1.0</td><td class="ln">scalp 0.5 / 1.0</td>'
  '<td class="ln">FLAT (gate off)</td></tr>',
  '<tr><td class="ln">grind_long</td><td class="ln">wide-chandelier &mdash; <strong>LIVE TODAY by '
  'default</strong>, n=24, under pre-registered test to 2026-08-21 <span class="was">(unproven, n=5)</span>'
  '</td><td class="ln"><span class="was">scalp 0.5 / 1.0</span> <strong>&#9654; WITHDRAWN</strong></td>'
  '<td class="ln"><span class="was">scalp 0.5 / 1.0</span> <strong>&#9654; WITHDRAWN</strong></td>'
  '<td class="ln">FLAT (gate off)</td></tr>\n'
  '<tr class="row-bad"><td class="ln"><strong>&#9654; REV3 &mdash; grind_long, the honest answer</strong></td>'
  '<td class="ln" colspan="4">Swept properly: <strong>130 configurations on 3,064 tick-repriced entries over '
  '16 sessions, under a <em>sequential</em> one-position-per-slot sim</strong> (the paired same-entry method '
  'this lab used stacks overlapping entries and scored the loaded default at +$2,961; sequential scores the '
  'same config −$2,115 — a $5,076 swing from methodology alone). <strong>The {0.5, 1.0} cell above is '
  'WITHDRAWN</strong>: it is −$1,127 <em>worse</em> than what is loaded today and fails leave-one-day-out, '
  'strip-best-3, the bootstrap and the out-of-sample sign test. <strong>Not one exit setting makes this gate '
  'green</strong> — the best of 130 still loses $414. If you want the marginal move it is '
  '<code>{"a_r": 3.0, "b": "wide"}</code>, +$617 over 16 sessions ≈ +$10/session at the live fill rate, and it '
  'is damage control, not an edge. The real lever is arming, and it is 3–5&times; bigger. Full sweep: '
  '<a href="#p3grindexit">Part 3.7</a>.</td></tr>\n'
  '<tr class="row-hl"><td class="ln">grind_long &mdash; MED-TREND, n=326</td><td class="ln" colspan="4">'
  'The biggest evidenced exit gap on the desk and it needs no new tape: the live A2.5+WIDE default makes '
  '<strong>+$8.49/trade against TIGHT&times;2\'s +$17.60</strong> — a $9.11 &times; 326 gap. Better evidenced '
  'than the BIG-TREND question this section spends four hundred words on.</td></tr>')

P("part2_shadow.html",
  "and that abs_veto's dollars come from its entry veto, not its exit R's",
  "and that <span class=\"was\">abs_veto's dollars come from its entry veto, not its exit R's</span> "
  "<strong>&#9654; REV3: most of abs_veto's edge is the entry veto &mdash; but the long side's R's are still "
  "the worst cell swept (see the policy row above)</strong>")

# relegation view — exhaustion
P("part2_shadow.html",
  "LIVE exhaustion_short is the desk's cleanest fader (see the exit lab below).",
  "LIVE exhaustion_short is the desk's <strong>steadiest</strong> fader <span class=\"was\">cleanest "
  "fader</span> &mdash; though <strong>its live green is hand-claim dependent (&minus;$56 over 44 automated "
  "fires)</strong> (see the exit lab below).")

# ==================================================================================
# PART 2.5 — mid-week musings
# ==================================================================================
P("part25_musings.html",
  "<h3>2 · The GRIND lead (operator-flagged, Paris-31): should grind run only on a confirmed trend?</h3>",
  "<h3>2 · The GRIND lead (operator-flagged, Paris-31): should grind run only on a confirmed trend?</h3>"
  + DEAD_FLOORS)

P("part25_musings.html",
  "<b>ER filters are fake here</b> (consistent with the standing memory).",
  "<span class=\"was\"><b>ER filters are fake here</b> (consistent with the standing memory).</span> "
  "<strong>&#9654; REV3: this is the wrong conclusion from the right observation.</strong> Grind fired below "
  "its floor 52 of 56 times because <em>the floor was not running</em> — a bug in our code, not a fact about "
  "the market. (The standing memory does survive on its own evidence: re-derived on 8 days of tick-honest "
  "replay, grind's ER≥0.35 would have thrown away +$2,923 of profit to keep +$83, so the floor is still a "
  "leak. But that is a separate proof, and it says <strong>delete the floor</strong>, not \"ER is "
  "meaningless\".)")

# --- Part 2.5 §3 prints the same superseded router table as Part 2.6 §3 ---------------
P("part25_musings.html",
  '<tr class="row-hl"><td><b>Week</b></td><td class="num">—</td><td class="num"><b>$15,788</b></td>'
  '<td class="num"><b>$17,003</b></td><td class="num"><b>−$1,216</b></td>'
  '<td class="num"><b>−$1,083</b></td></tr>',
  '<tr class="row-hl"><td><b>Week</b></td><td class="num">—</td><td class="num"><b>$15,788</b></td>'
  '<td class="num"><b>$17,003</b></td>'
  '<td class="num"><b>&minus;$440 to &minus;$646</b> <span class="was">−$1,216</span><br>'
  '<span style="font-size:.85em">A/B merged; −$1,216 as originally double-counted. '
  '<strong>Do not quote this number.</strong></span></td>'
  '<td class="num"><b>&minus;$1,083 week</b><br><span style="font-size:.85em">(−$456 / −$398 / −$229 '
  'Mon–Wed, <b>$0 on both durable days</b>)</span></td></tr>')

P("part25_musings.html",
  "<p>Read honestly, the estimator says the router <b>over-benched</b> this week — it blocked more "
  "shadow-winners than losers-saved (net −$1,216), positive only on the clean trend day.",
  cor("the same &minus;$1,216 correction as Part 2.6 &sect;3 &mdash; and do not net these columns",
      "<p>The A and B legs of every dual slot are byte-identical in the nightly's own output because the "
      "repricer ignores the slot suffix, so <strong>every suppressed signal is counted twice</strong>. Merged, "
      "the week is 353&ndash;355 signals and net <strong>&minus;$440 to &minus;$646</strong>. A second "
      "double-count sits underneath it: the nightly de-dupes at 120 seconds and then prices every survivor as "
      "a full round trip even while the same gate is still in the previous one. Until both land, every "
      "&ldquo;router value&rdquo; number carries roughly 2&times; counting inflation. And the blended figure "
      "flips sign on which single day you drop (&minus;$804 dropping 07-30, +$230 dropping 07-29) &mdash; it "
      "supports no verdict at all. Score the halves separately: the <strong>fader bench is +$810 (n=25) and "
      "survives every independent regime tag</strong>; benching into chop does not (+$612 / +$187 / "
      "&minus;$382 across three tags). Working: <a href='#p3trendup'>Part 3.5</a>.</p>"
      "<p><strong>Do not net the columns.</strong> Leakage is the only realised-money column in this table; "
      "saved and missed are modelled counterfactuals on trades that never ran.</p>")
  + "<p><span class=\"was\">Read honestly, the estimator says the router over-benched this week — it blocked "
    "more shadow-winners than losers-saved (net −$1,216), positive only on the clean trend day.</span>")

# --- Part 2 LAB: the CRITICAL caveat still opens on n=5 -------------------------------
P("part2_shadow.html",
  "The two-week V7 tape was chop-dominated, so the BIG-TREND rung is tiny in every family (grind n=5, "
  "exhaustion/rgv n=15, capitulation n=8; thrust the only semi-real one at n=25 and it bled). The \"RIDE\" "
  "rung &mdash; grind 2.5&ndash;3.5R + wide lock-chandelier on a monster up-day &mdash; is effectively "
  "<strong>UNPROVEN</strong> (grind's BIG cell is 5 trades).",
  "The two-week V7 tape was chop-dominated, so the BIG-TREND rung is tiny in every family (grind "
  "<strong>n=24</strong> <span class=\"was\">n=5</span>, exhaustion/rgv n=15, capitulation n=8; thrust the "
  "only semi-real one at n=25 and it bled). The \"RIDE\" rung &mdash; grind 2.5&ndash;3.5R + wide "
  "lock-chandelier on a monster up-day &mdash; is <strong>DIRECTION SUPPORTED, MAGNITUDE UNPROVEN</strong> "
  "<span class=\"was\">effectively UNPROVEN (grind's BIG cell is 5 trades)</span>. "
  "<strong>&#9654; REV3: the cell is n=24, not 5. Five is the count of live grind_fast shadow entries in an "
  "ER&ge;0.50 minute; the ladder verdict was computed on a 24-entry tick-tape replay. The caveat quotes the "
  "live number inside a caveat about the replay number.</strong>")

# ==================================================================================
# PART 2.6 — router operation review
# ==================================================================================
P("part2_6_router_review.html",
  "<h2><span class=\"n\">2.6</span> Router Operation Review — the desk's #1 lever, on the stand</h2>",
  "<h2><span class=\"n\">2.6</span> Router Operation Review — the desk's #1 lever, on the stand</h2>\n"
  + ptr("The headline &minus;$1,216 is double-counted, the &quot;yes, as a defence&quot; verdict splits in "
        "two once the halves are scored separately, and &sect;4/&sect;8 lean on a grind floor that has never "
        "executed. There is also a live finding that outranks the whole section: <strong>all six gates are "
        "pinned ON right now, so the durable router cannot bench anything at all.</strong>"))

P("part2_6_router_review.html",
  "(3) the desk finished the week <b>net green +$625</b> even after eating that Friday.",
  "(3) the desk finished the week <b>+$625 as booked &mdash; but &minus;$598 with your hands off</b> "
  "(194 automated fills, 35.1% win, PF 0.91; $1,223 of the headline came from twelve trades you closed "
  "yourself &mdash; see Part 1).")

# §2 graded ledger — the +$372 that was four hand-clicks
P("part2_6_router_review.html",
  '<tr class="row-hl"><td class="ln">07-30 14:57 arm short-side fade book for the roll-over chop</td>'
  '<td><span class="tag">✅ GOOD</span></td><td class="num">+$372</td>'
  '<td>exhaustion_short went 4/4 live fading the roll-over — best offense of the day</td></tr>',
  '<tr class="row-hl"><td class="ln">07-30 14:57 arm short-side fade book for the roll-over chop</td>'
  '<td><span class="tag">✅ GOOD (regime read)</span> <span class="tag pill-dontarm">⚠ the $ credit is '
  'manual</span></td><td class="num">+$372 hand-claimed / <strong>&minus;$51 automated</strong></td>'
  '<td>exhaustion_short went 4/4 live fading the roll-over — <strong>but all four were MANUAL_CLAIM exits.</strong> '
  'Repriced on 250&nbsp;ms tape under the exit config actually loaded, the machine books &minus;$51.2 on the '
  'same four entries. The regime call was right; the money was your hand.</td></tr>')

# §2 CHURN row — reasons from the dead floor
P("part2_6_router_review.html",
  "<td>grind's 0.35 ER floor + abs_veto's veto meant most premature arms never fired — process error, not $ "
  "error</td>",
  "<td><span class=\"was\">grind's 0.35 ER floor + abs_veto's veto meant most premature arms never fired — "
  "process error, not $ error</span> <strong>&#9654; REV3: grind's 0.35 floor has never executed (<a href='#p3floors'>Part 3.6</a>), "
  "so it cannot have absorbed those arms. Only abs_veto's 55s veto was actually running. This CHURN is graded "
  "$0 on the strength of a filter that was not there.</strong></td>")

# §3 WEEK rows
P("part2_6_router_review.html",
  '<tr class="row-hl"><td class="ln"><b>WEEK</b></td><td>—</td><td class="num"><b>$15,788</b></td>'
  '<td class="num"><b>$17,003</b></td><td class="num"><b>−$1,216</b></td>'
  '<td class="num"><b>$0 (durable days)</b></td></tr>',
  '<tr class="row-hl"><td class="ln"><b>WEEK</b></td><td>—</td><td class="num"><b>$15,788</b></td>'
  '<td class="num"><b>$17,003</b></td><td class="num"><b>&minus;$440 to &minus;$646</b> '
  '<span class="was">−$1,216</span><br><span style="font-size:.85em">A/B merged; −$1,216 as originally '
  'double-counted. <strong>Do not quote this number</strong> — it flips sign on which single day you drop.'
  '</span></td><td class="num"><b>&minus;$1,083 week</b><br><span style="font-size:.85em">(−$456 / −$398 / '
  '−$229 Mon–Wed, <b>$0 on both durable days</b>)</span></td></tr>')

P("part2_6_router_review.html",
  "<p><b>Honest reading (this number is noisier than it looks):</b> the raw net is −$1,216, but two things "
  "inflate the \"missed\" column — the dual A/B slots double-count one signal, and the giant \"missed\" "
  "figures on 07-29 (−$1,717 value) are dominated by <b>grind_long shadow winning during brief benched windows "
  "on a trend day</b>.",
  "<span class=\"was\"><b>Honest reading (this number is noisier than it looks):</b> the raw net is −$1,216, "
  "but two things inflate the \"missed\" column — the dual A/B slots double-count one signal…</span>"
  + cor("&minus;$1,216 counts every suppressed signal twice, and the blended number supports no verdict at all",
        "<p><strong>The double-count is real and the report named it and then left it in the total anyway.</strong> "
        "The dual-slot A and B legs are byte-identical in the nightly's own JSON because "
        "<code>reprice_scalp()</code> ignores the slot suffix. Merge them and the week is <strong>353–355 "
        "signals, ~$8,700 saved, ~$9,200 missed, net &minus;$440 to &minus;$646</strong> (two independent "
        "re-derivations, $206 apart on $9.4k of gross). That recovers about $661 of pure bookkeeping.</p>"
        "<p><strong>There is a second double-count nobody caught until this weekend.</strong> "
        "<code>router_nightly.py</code> de-dupes suppressions at 120 seconds and then prices every survivor as "
        "a complete round trip — even when the same gate is still notionally in the previous one. A real gate "
        "holds one position at a time. Enforcing that halves the blocked book again. <strong>Until both fixes "
        "land, every \"router value\" number in this report carries roughly 2&times; counting "
        "inflation.</strong></p>"
        "<p><strong>Do not quote the blended figure at all.</strong> It flips sign on leave-one-day-out "
        "(&minus;$804 dropping 07-30, +$230 dropping 07-29), which means it supports no verdict in either "
        "direction. Score the halves separately — that is the &sect;8 verdict, corrected.</p>")
  + "<p><b>What the \"missed\" column is actually made of:</b> the giant figures on 07-29 (−$1,717 value) are "
    "dominated by <b>grind_long shadow winning during brief benched windows on a trend day</b>.")

# §4 — the dead floors again, and the unbaselined +$728
P("part2_6_router_review.html",
  "<h3>4 · Threshold tuning — the sweep</h3>",
  "<h3>4 · Threshold tuning — the sweep</h3>" + DEAD_FLOORS)

P("part2_6_router_review.html",
  "is validated separately (+$728 over 10d) — leave it.",
  "is validated separately (+$728 over 10d — <em>against what alternative? the counterfactual was never "
  "stated</em>) — leave it. <strong>&#9654; REV3: and see the dead-floors correction above &mdash; that "
  "threshold has not run since 07-29 16:20, so nothing in this week's tape tests it. Re-derived on 8 days of "
  "tick-honest replay it is the most expensive line of config on the desk: it keeps 8 signals worth +$83 and "
  "discards 173 worth +$2,923. The Saturday play deletes it.</strong>")

# §5 — the meter "validated" on n=5
P("part2_6_router_review.html",
  "<p><b>The meter is validated.</b> Sort by score and you sort by P&amp;L almost perfectly:",
  "<p><b>The meter lines up perfectly on the only five days it has seen.</b> "
  "<span class=\"was\">The meter is validated.</span> <strong>&#9654; REV3: that is a promising start on "
  "<strong>n=5</strong>, not a validation. Re-score it weekly and do not let it size anything until it has a "
  "month.</strong> Sort by score and you sort by P&amp;L almost perfectly:")

# §8 verdict
P("part2_6_router_review.html",
  "<p class=\"lead\">Is the router earning its keep? <b>Yes — as a defense.</b> Zero real blocked-loss leakage "
  "on the days it ran durably, +$807 of shadow-confirmed defense on 07-30, a new untradeable-meter that called "
  "all five days correctly, and a durable tick that held flat through the worst day of the week without a "
  "session driving it. The desk finished <b>net green (+$625 over 206 trades)</b> through a week that "
  "contained a −$905 day.",
  "<p class=\"lead\"><b>Split verdict &mdash; and the two halves point opposite ways.</b> "
  "<span class=\"was\">Is the router earning its keep? Yes — as a defense.</span> "
  "<strong>The defence earns its keep on exactly one cut, and it is the one that survives everything: benching "
  "the FADERS is +$810 (n=25, non-overlap) and comes out identical under every independent regime tag anyone "
  "could throw at it.</strong> Benching into CHOP is <em>not</em> in that class &mdash; it scores +$612 under "
  "the router's own tag, +$187 under ADX(14) and &minus;$382 under a 60-minute regression tag, i.e. it only "
  "holds if you accept the router's own definition of chop. And the offence does not earn its keep: the "
  "\"stop benching momentum in TREND_UP, +$1,615/week\" finding was independently re-derived this weekend and "
  "is <strong>WITHDRAWN</strong> (<a href='#p3trendup'>Part 3.5</a>). Zero real blocked-loss leakage on the days it ran durably, +$807 "
  "of shadow-confirmed defence on 07-30, and a durable tick that held flat through the worst day of the week "
  "without a session driving it — those all stand. The desk finished <b>+$625 as booked, &minus;$598 with your "
  "hands off (see Part 1)</b> through a week that contained a −$905 day. "
  "<strong>&#9654; And the finding that outranks this entire section: as of 08-01 all six gates are PINNED in "
  "<code>router_tick_durable.py</code>, so the apply step's change set is permanently empty and the durable "
  "tick has benched nothing for 36 hours. The proven half of the machine is switched off. That is MONDAY "
  "play #1.</strong>")

P("part2_6_router_review.html",
  "<td>07-30 ~8&times; toggle CHURN; grind self-gates via its 0.35 floor</td>",
  "<td>07-30 ~8&times; toggle CHURN <span class=\"was\">; grind self-gates via its 0.35 floor</span> "
  "<strong>&#9654; REV3: clause deleted &mdash; grind does not self-gate. That floor has never executed "
  "(<a href='#p3floors'>Part 3.6</a>).</strong></td>")

# ==================================================================================
# MOVEMENT 3 — the session-boundary footnote
# ==================================================================================
P("movement3_greenfield.html",
  '<tr class="row-bad"><td>Fri 07-31</td><td class="ln">CHOP (mixed)</td><td class="num">27</td>'
  '<td class="num">&minus;$569</td>',
  '<tr class="row-bad"><td>Fri 07-31</td><td class="ln">CHOP (mixed)</td><td class="num">27</td>'
  '<td class="num">&minus;$569</td>')  # anchor only; the footnote goes after the table (below)


def main() -> int:
    # 1 · snapshot / restore so the script is safely re-runnable
    for name in FILES:
        p = SEC / name
        orig = SEC / (name + ".rev2-orig")
        if not p.is_file():
            print(f"FATAL — missing fragment {p}")
            return 2
        if orig.is_file():
            p.write_text(orig.read_text())
        else:
            orig.write_text(p.read_text())

    # 2 · apply, asserting every hit
    failures: list[str] = []
    applied = 0
    cache: dict[str, str] = {n: (SEC / n).read_text() for n in FILES}
    for fname, old, new, count in PATCHES:
        if old == new:
            continue
        s = cache[fname]
        got = s.count(old)
        if got != count:
            failures.append(f"{fname}: expected {count} hit(s), found {got} for: {old[:110]!r}")
            continue
        cache[fname] = s.replace(old, new, count)
        applied += 1

    # 3 · Movement 3 session-boundary footnote (appended right after the ledger table)
    m3 = cache["movement3_greenfield.html"]
    anchor = "<td class=\"num\">27.3</td>"
    if m3.count(anchor) == 1:
        i = m3.index(anchor)
        j = m3.index("</table>", i) + len("</table>")
        note = cor(
            "session-boundary note &mdash; this table and Part 1's day-by-day table are both right",
            "<p>This table books on the <strong>UTC calendar day</strong>; Part 1's day-by-day table books on "
            "the <strong>Paris session boundary</strong> the desk keeps its ledger on. Same trades, different "
            "day buckets &mdash; the week total is identical, the individual days are not. That is why Part 1 "
            "calls Thursday a +$1,172 record and this table prices the same Thursday at +$94. Add the "
            "hands-off cut and Thursday is the <em>worst</em> automated day of the week at &minus;$884.5 on 73 "
            "fills, turned green by nine hand-claims.</p>")
        cache["movement3_greenfield.html"] = m3[:j] + note + m3[j:]
        applied += 1
    else:
        failures.append(f"movement3_greenfield.html: ledger-table anchor found {m3.count(anchor)} times")

    if failures:
        print("★ ABORTED — no file written. Failed anchors:")
        for f in failures:
            print("   · " + f)
        return 1

    for name, text in cache.items():
        (SEC / name).write_text(text)
    print(f"REV3 in-place corrections applied: {applied} edits across {len(FILES)} fragments.")
    for name in FILES:
        print(f"   {name}: {len((SEC / name).read_text()):,} bytes "
              f"(was {len((SEC / (name + '.rev2-orig')).read_text()):,})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
