#!/usr/bin/env python3
"""MOVEMENT 3 — the greenfield lab, built from THIS cycle's seven finished hunts.

★★★ WHY THIS FILE WAS REWRITTEN (2026-08-26). The previous version of this script was written on
2026-08-21 against a cycle in which four of five greenfield phases never started, and it hard-coded
that provenance into a red box at the top of the section. By the time the report was assembled the
situation had reversed completely: the phases DID run, and six of the seven labs finished between
2026-08-25 21:36 and 23:39 — after `movement3_greenfield.html` had already been frozen at 00:48 on
08-22 from the one lab (VACUUM) that existed at the time.

So the stitched report was about to carry, in red, at the top of its biggest movement, the sentence
"the FLOW-LED, OPEN-NEWS, UNCLASS and RIDER_ALL cluster hunts did not run this cycle" — over roughly
54,000 words of finished, tick-honest working that had run, and whose verdicts CONTRADICT the
superseded section beneath it (the chop-scalp finalist, the gold trigger and the three forward tests
were all re-derived and all moved). A stale section is bad; a stale section wearing a red honesty
banner that says the opposite of the truth is worse, because it is the mechanism the reader trusts.

This version therefore reads the labs themselves. Every number below is TYPED FROM a named lab file
and carries its source in the row, so the next reader can check any line against the dossier that
produced it; and the dossiers are then reproduced IN FULL as the movement's appendix, converted
from their own markdown, so nothing is summarised away. The editorial half is the map; the appendix
is the territory.

  reports/friday_v7/sections/gf_full_RIDER_ALL.md   08-25 22:10   the pooled run-catcher
  reports/friday_v7/sections/gf_full_UNCLASS.md     08-25 22:34   the biggest bucket, 41 runs
  reports/friday_v7/sections/gf_full_OPEN-NEWS.md   08-25 22:58   the cash-open window
  reports/friday_v7/sections/gf_full_FLOW-LED.md    08-25 23:12   aggressor-led continuation
  reports/friday_v7/sections/gf_full_VACUUM.md      08-22 00:18   snap-back / stop-run
  reports/friday_v7/sections/gf_chopscalp.md        08-25 23:39   the L2-led chop-day turn scalp
  reports/friday_v7/sections/gf_MGC.md              08-25 21:36   gold

Run:  python3 scripts/friday_v7_movement3_section.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from friday_v7_md2html import md_to_html, word_count          # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = f"{SEC}/movement3_greenfield.html"

# (anchor, display title, file, one-line what-it-hunted)
LABS = [
    ("m3-rider", "THE POOLED RUN-CATCHER &mdash; one rider for every sat-out run",
     "gf_full_RIDER_ALL.md",
     "Ignore the labels. Board <em>any</em> run late, ride it wide, filter it causally."),
    ("m3-uncl", "UNCLASS &mdash; the biggest bucket, 41 of the 68 runs",
     "gf_full_UNCLASS.md",
     "The bucket our own classifier could not name, and had therefore never hunted."),
    ("m3-open", "OPEN/NEWS &mdash; the 13:00&ndash;15:00Z cash-open window",
     "gf_full_OPEN-NEWS.md",
     "The densest run window on the clock: 13 runs, $2,814 of ceiling."),
    ("m3-flow", "FLOW-LED &mdash; aggressor-driven continuation",
     "gf_full_FLOW-LED.md",
     "Runs the tape pushed. Nine candidates built off the flow print."),
    ("m3-vac", "VACUUM &mdash; the snap-back / stop-run",
     "gf_full_VACUUM.md",
     "Runs that moved AGAINST the tape, plus last week's shadow candidate forward-tested."),
    ("m3-chop", "THE CHOP-DAY TURN SCALP &mdash; the operator's own commission, L2-led",
     "gf_chopscalp.md",
     "&ldquo;Can we stop donating on chop days?&rdquo; &mdash; a purpose-built L2 turn scalper."),
    ("m3-mgc", "GOLD &mdash; MGC, and the shadow arm that went live and lost",
     "gf_MGC.md",
     "The second instrument, $10.00 a point, and the first live grade of last week's gold gate."),
]

# ── THE BOARD ────────────────────────────────────────────────────────────────────────────────
# (lab, what it built, headline in-sample, the named test that killed it, disposition, source §)
BOARD = [
    ("Pooled rider", "<code>board_atrband</code> &mdash; late board, 3.0&times;ATR stop, "
     "6.0&times;ATR target, ATR band 11&ndash;16",
     "passed every in-sample test, both placebos",
     "<strong>the out-of-sample leg</strong> &mdash; 1,289 trades over 236 untouched sessions for "
     "<strong>+$14 total</strong>; 95% CI &minus;0.204R to +0.246R",
     "PARKED", "RIDER_ALL &sect;4, &sect;10"),
    ("UNCLASS", "<code>UNCL-RIDE-ER</code> &mdash; late board + ER30&nbsp;&ge;&nbsp;0.40, "
     "10&times;ATR target",
     "n=196, +$6,211, +$31.69/tr, PF&nbsp;1.64",
     "<strong>the placebo/shuffle test</strong> &mdash; on 205 untouched sessions the real signal "
     "makes +$3.54/tr and the SAME rule taken 30 minutes early makes <strong>+$4.44</strong>",
     "PARKED", "UNCLASS &sect;6, &sect;13"),
    ("OPEN/NEWS", "<code>MOMBRK</code> (+$32.87/tr, n=52) and <code>PULSE-13h</code> "
     "(+$23.09/tr, n=95)",
     "the two biggest per-trade numbers in the movement",
     "<strong>strip-the-best and the placebo</strong> &mdash; MOMBRK's top 3 of 52 trades are "
     "88.5% of its net; PULSE's 30-minute-stale copy books <strong>+$23.95/tr, more than the real "
     "signal</strong>. And a gate containing <em>no signal at all</em> books +$47.29/tr in the "
     "same window",
     "REFUTED", "OPEN/NEWS &sect;9, &sect;15"),
    ("FLOW-LED", "nine candidates, <code>FL-1</code> &hellip; <code>FL-9</code>",
     "<code>FL-4 flow_ignition</code> reached +$12.18/tr",
     "<strong>the placebo/shuffle test</strong> &mdash; p&nbsp;=&nbsp;0.150, 6 of 40 time-shifted "
     "fake flow series matched or beat it, and the best fake (+$16.25/tr) beat the real signal "
     "outright",
     "REFUTED", "FLOW-LED &sect;4, VERDICT"),
    ("VACUUM", "<code>VAC-SNAP</code>, <code>VAC-CUMDIV</code>, <code>VAC-ABS</code>, "
     "<code>VAC-IGN-BRK</code>",
     "<code>VAC-IGN-BRK</code> +$911.55 over n=284",
     "<strong>the sign-flip control</strong> &mdash; fading the break earns +$3.08/tr against the "
     "signal's +$3.21, so both directions win. That is volatility harvesting, not edge",
     "REFUTED", "VACUUM &sect;3, VERDICT"),
    ("Chop scalp", "sixteen named candidates, 768 costed cells + a 1,080-cell finalist search",
     "<code>CT15</code> +$158 on 26 trades, +$6.08/tr, 77% win, IS <em>and</em> OOS positive, "
     "13/13 leave-one-day-out, strip-best-5 still +$4.07",
     "<strong>the placebo run WITH THE SEARCH INCLUDED</strong> &mdash; handed the same 1,080-cell "
     "grid, the null finds a better cell 85.3% of the time; matched fairly at n&nbsp;&ge;&nbsp;26, "
     "<strong>p&nbsp;=&nbsp;0.367</strong>",
     "REFUTED", "chopscalp &sect;9, VERDICT"),
    ("Gold (MGC)", "<code>mgc_hole_break_fade</code> &times;2 sides + double-hole; "
     "<code>mgc_wall_break_go</code> &times;2 sides",
     "double-hole arm n=200, +$3,304, +$16.52/tr, forward +$656, placebo 0/30",
     "<strong>nothing killed the research &mdash; the LIVE arm is losing on a different tape.</strong> "
     "The lab builds bars from the depth mid, the service builds them from trades, and the sign "
     "flips on that alone (+$3.06/tr vs &minus;$8.96/tr on the six days both cover)",
     "SHADOW", "MGC &sect;3, &sect;13"),
]

# ── EVERY GRAVE, BY NAME ─────────────────────────────────────────────────────────────────────
GRAVES = [
    ("board_atrband", "pooled rider", "the OOS leg", "+$14 over 1,289 trades / 236 sessions", "PARKED"),
    ("board_wide / board_holdcap / board_blanket", "pooled rider", "both-halves and the OOS sweep",
     "failed as built; the 42-cell OOS surface shows the exit was never the binding constraint", "PARKED"),
    ("board_chandelier", "pooled rider", "a backtest bug, then honesty",
     "the trail was broken; +$4,270 became &minus;$631 once fixed", "PARKED, not refuted"),
    ("board_book (L2 far-side depletion as selector)", "pooled rider", "correlation + placebo",
     "311 fires against 264M book rows, r = &minus;0.009, no monotone band, placebo p = 0.62", "REFUTED"),
    ("rider_w5 (LIVE shadow arm, shipped 08-15)", "pooled rider", "51 live forward trades",
     "&minus;$1,471, &minus;$28.84/tr against +$19.29 claimed; red in all four ATR buckets", "REFUTED &mdash; retire"),
    ("UNCL-RIDE-ER", "UNCLASS", "placebo/shuffle + OOS",
     "the 30-minute-early fake beats the real signal on 205 untouched sessions", "PARKED"),
    ("UNCL-RIDER-ASIA (last week's SHADOW pick)", "UNCLASS", "the forward OOS leg",
     "W31 &minus;$2.93, W32 &minus;$15.90, W33 &minus;$36.46, W34 &minus;$38.08 &mdash; four red weeks", "REFUTED"),
    ("the thin-volume / no-aggression mechanism", "UNCLASS", "the random-cut placebo",
     "p = 0.600 &mdash; the cut is worse than discarding the same number of fires by coin flip", "REFUTED"),
    ("the tight / trailing exit family", "UNCLASS", "the 1,350&ndash;1,683-trade year leg",
     "negative throughout; the 10&times;ATR target ridge holds across every stop width", "REFUTED for this shape"),
    ("the &ldquo;arm US 13&ndash;20Z&rdquo; rule", "UNCLASS", "the OOS leg",
     "+$107.79/tr in-sample (placebo p &lt; 0.001), &minus;$18.62/tr out of sample", "REFUTED before it shipped"),
    ("MOMBRK", "OPEN/NEWS", "strip-the-best + OOS",
     "top 3 of 52 trades = 88.5% of net; +$32.87/tr &rarr; +$4.02 stripped; &minus;$16.50/tr OOS", "REFUTED"),
    ("PULSE-13h", "OPEN/NEWS", "the placebo",
     "the 30-minute-stale copy books +$23.95/tr against the real signal's +$23.09", "REFUTED"),
    ("ORB30 &mdash; pre-open range break", "OPEN/NEWS", "strip-3", "&minus;$26.98/tr after strip-3", "REFUTED"),
    ("COILBRK &mdash; compression break", "OPEN/NEWS", "n",
     "one trade at the setting the theory wanted", "PARKED"),
    ("FADE1 &mdash; the exact mirror of PULSE", "OPEN/NEWS", "expectancy", "&minus;$13.05/tr", "REFUTED"),
    ("FL-1 flow_impulse_cont", "FLOW-LED", "the OOS leg", "did not survive the held-out sessions", "REFUTED"),
    ("FL-4 flow_ignition", "FLOW-LED", "the placebo/shuffle test",
     "p = 0.150; best fake +$16.25/tr beats the real +$12.18/tr; ablation +$39.43 IS &rarr; &minus;$11.71 OOS", "REFUTED"),
    ("FL-5 flow_absorb_fade", "FLOW-LED", "strip-the-3-best", "the headline is three trades", "REFUTED"),
    ("FL-8 flow_x_vol_cont", "FLOW-LED", "placebo AND strip-3", "beaten outright by its own placebo", "REFUTED"),
    ("FL-9 flow_lot", "FLOW-LED", "the parameter sweep", "no plateau &mdash; a spike, which is the curve-fit tell", "REFUTED"),
    ("FL-2, FL-3, FL-6, FL-7", "FLOW-LED", "the blanket screen",
     "negative expectancy; no regime cell rescued any of them", "REFUTED"),
    ("VAC-SNAP", "VACUUM", "strip-the-3-best + OOS",
     "+$370.64 (n=410) becomes &minus;$1,436 stripped; &minus;$18.02/tr out of sample", "REFUTED"),
    ("VAC-CUMDIV", "VACUUM", "every threshold", "negative at all of them", "REFUTED"),
    ("VAC-ABS (last week's shadow candidate)", "VACUUM", "the OOS leg",
     "+$1,319.21 / n=97 / +$13.60&nbsp;per&nbsp;trade forward, then &minus;$529.50 over 27 unseen trades; strip-5 &minus;$427",
     "REFUTED &mdash; retire, do not re-shadow"),
    ("VAC-IGN-BRK", "VACUUM", "the sign-flip control",
     "the fade earns +$3.08/tr against the signal's +$3.21 &mdash; both directions win", "REFUTED as a gate"),
    ("VAC-Z1 (the label, traded literally)", "VACUUM", "expectancy at scale",
     "&minus;$4,150.79 over 1,768 serial trades; &minus;$32,184 unconstrained", "REFUTED"),
    ("CT15 (the chop-turn finalist)", "chop scalp", "the placebo run WITH the search",
     "the null's own best cell averages +$8.42/tr and wins 85.3% of the time; matched p = 0.367", "REFUTED"),
    ("CT2_WALL (the operator's lead L2 hypothesis)", "chop scalp", "two independent drift tests",
     "worst of sixteen at &minus;$3.09/tr; the wall INVERTS the fade's +0.054pt drift to &minus;0.117pt", "REFUTED, sign inverted"),
    ("the VWAP-flat filter", "chop scalp", "48 cells", "$0.01/tr &mdash; inert, doing no work at all", "REFUTED"),
    ("mgc_straddle / breakout-either-way", "gold", "320 days",
     "all 8 compression cells negative, control negative, dies on one tick of slippage", "REFUTED"),
    ("last week's MGC router rule", "gold", "the forward walk AND the 320-day tape, independently",
     "it would bench the gate in NORMAL_CHOP &mdash; the regime currently paying best", "REFUTED as a rule"),
    ("cross-asset momentum confirm (gold with the Nasdaq)", "gold", "278 paired days",
     "&minus;$2.29/tr, and &minus;$9.15/tr on the book window; 1st percentile of its own placebo", "REFUTED"),
    ("the bare 60-min break trigger, standalone", "gold", "strip-best-10 and slippage",
     "direction is real on 320 days; the P&amp;L is not (&minus;$4,392 stripped, dies at 0.10pt)", "PARKED"),
]

# ── THE HARNESS BUGS THE LABS CAUGHT ON THEMSELVES ───────────────────────────────────────────
BUGS = [
    ("The trail that never trailed", "RIDER_ALL &sect;3",
     "The chandelier family survived every robustness test in the phase &mdash; until the trail was "
     "found to be broken. Corrected, <strong>+$4,270 becomes &minus;$631</strong>.",
     "It would have shipped. Every test we own passed it, because every test was reading the same "
     "wrong simulator."),
    ("A look-ahead of my own", "MGC &sect;7",
     "A volatility cell read <strong>+$71,608</strong> until it was noticed that it entered at the "
     "OPEN of the bar whose HIGH it had already used. Corrected, it reads <strong>&minus;$12,462</strong>.",
     "That number would otherwise have been the largest in this report."),
    ("Five shorts into one impulse", "VACUUM &sect;3",
     "The first pass let overlapping entries run concurrently. Five shorts into the single 2026-07-31 "
     "impulse were worth $3.9k of a $10.3k headline. Scored one position at a time &mdash; the only "
     "way a live gate can trade &mdash; <strong>VAC-IGN-BRK falls from +$10,316 / +$15.49 per trade to "
     "+$911.55 / +$3.21</strong>.",
     "Concurrency is not a backtest convenience; it is leverage the desk cannot take."),
    ("A slice is not a filter", "UNCLASS &sect;3",
     "Testing a filter by SLICING the trade list of an unfiltered rider gives +$28.33/tr. Running the "
     "identical filter INSIDE the simulation &mdash; where refusing a fire frees you to take the next "
     "one &mdash; gives <strong>+$5.68/tr, and n doubles</strong>.",
     "Wrong by a factor of five, and slicing is the natural way to test a filter."),
    ("A backward shift is an oracle, not a placebo", "OPEN/NEWS &sect;15",
     "A signal shifted BACKWARDS in time is a look-ahead oracle. Only FORWARD (stale) shifts are "
     "legitimate placebos. Run the wrong way, it produces a false KILL.",
     "Reported because it was run the wrong way first. The harness passed the leak-check: "
     "look-ahead earns 2.7&times; the real signal, as it should."),
    ("Leave-one-day-out cannot fail when k days carry the money", "OPEN/NEWS &sect;15",
     "MOMBRK passed <strong>21 of 21</strong> LODO folds while <strong>two of twenty-one days held "
     "97% of its P&amp;L</strong>.",
     "Always quote profitable-days-out-of-total beside a LODO result, and run leave-TWO-out when the "
     "day distribution is that skewed."),
    ("The lake grew a look-ahead landmine", "MGC &sect;1.2",
     "New <code>backfill_{1min,5mins,1hour,1day}.parquet</code> files now sit beside the daily 5s "
     "files. <strong>Any query without a <code>timeframe</code> filter inherits up to a full day of "
     "look-ahead, on every day.</strong>",
     "<code>gf_mgc_tape.load_l1()</code> is safe. <code>mgc_session_anchor.load()</code> is NOT. "
     "This is a FIX REQUIRED, not a note."),
]

# ── THE GOLD PER-CELL TABLE (MGC §13) ────────────────────────────────────────────────────────
MGC_CELLS = [
    ("REVERSION-LONG", "<code>mgc_hole_break_fade</code> &mdash; 60-min break DOWN into a liquidity hole &rarr; <strong>buy</strong>",
     "134", "+$1,853", "+$13.83", "+$488 (+$15.73)", "0/30 &#10004;", "&minus;$102.50 (n=7)",
     "SHADOW", "lead candidate, <strong>blocked on the bar-source fix</strong>"),
    ("REVERSION-SHORT", "<code>mgc_hole_break_fade</code> &mdash; 60-min break UP into a liquidity hole &rarr; <strong>sell</strong>",
     "154", "+$1,390", "+$9.03", "+$25 (<strong>+$0.65</strong>)", "0/30 &#10004;", "&minus;$153.50 (n=7)",
     "SHADOW", "same, plus a <strong>side-decay watch</strong>"),
    ("MOMENTUM-LONG", "<code>mgc_wall_break_go</code> &mdash; break UP through a defended level &rarr; buy",
     "101", "+$838", "+$8.30", "+$378 (+$9.44)", "<strong>29/30 &#10008;</strong>", "not deployed",
     "SHADOW, on probation", "2nd week failing the random-minute placebo"),
    ("MOMENTUM-SHORT", "<code>mgc_wall_break_go</code> &mdash; break DOWN through a defended level &rarr; sell",
     "88", "+$669", "+$7.61", "+$315 (+$9.56)", "<strong>29/30 &#10008;</strong>", "not deployed",
     "SHADOW, on probation", "same"),
    ("double-hole arm", "<code>mgc_hole_break_fade_dbl</code> &mdash; both reversion cells",
     "200", "+$3,304", "<strong>+$16.52</strong>", "+$656 (+$15.26)", "0/30 &#10004;", "not deployed",
     "SHADOW", "<strong>promote to a full arm</strong> &mdash; behind the bar-source fix"),
    ("volatility cell", "<code>mgc_straddle</code> &mdash; breakout either way out of a coil",
     "3,945", "&minus;$1,248", "&minus;$0.32", "&mdash;", "control also negative", "&mdash;",
     "REFUTED", "on 320 days. Last week's <em>reason</em> was wrong; the verdict was right"),
]

# ── THE AGGREGATE DISPOSITION TABLE ──────────────────────────────────────────────────────────
DISPO = [
    ("<strong>MGC shadow bar source</strong>", "BUILD REQUIRED",
     "The gating item for the whole gold line. Point the shadow's bar builder at the depth mid and keep "
     "the trade-bar arms as <code>*_tradebar</code> controls. The service already holds the "
     "<code>DepthFeed</code>. Nothing else on the gold line is worth doing first.", "MGC &sect;3, &sect;12.1"),
    ("<code>mgc_hole_break_fade</code> LONG + SHORT + double-hole", "SHADOW",
     "Survived the forward walk on the lab tape (+$512 / +$656, placebo 0/30, mirror and both constants "
     "negative, 3&ndash;4 ticks of slippage headroom). Losing in live shadow on production's tape "
     "(&minus;$256 over 14 trades) &mdash; that is the bar source, not the gate. Promote the double-hole "
     "arm to full status behind the fix.", "MGC &sect;14"),
    ("Cross-asset MNQ <strong>veto</strong> for gold", "SHADOW &mdash; new arm",
     "+$5.43/tr against +$1.72 blanket over 278 paired days, two-sided, placebo at the 97th/2.5th "
     "percentile. Does <em>not</em> reproduce on the 29-day book window (34th pctile). Needs a new "
     "<code>_entry</code> branch and an MNQ state feed. Settle it by running it alongside.", "MGC &sect;6"),
    ("<code>mgc_wall_break_go</code> LONG + SHORT", "SHADOW, on probation",
     "Forward-walked +$693, mirror negative, filter placebo 0/200 &mdash; but fails the random-minute "
     "placebo 29/30 for the SECOND week, and strip-best-10 is &minus;$192. Promote no further until "
     "n &ge; 150 with a passing random-minute placebo.", "MGC &sect;14"),
    ("<code>board_overnight</code> (21:00&ndash;07:00Z)", "SHADOW &mdash; an instrumented question",
     "Right sign in two independent samples (+0.444R and +0.224R), counter-trend leg negative in both, "
     "survives a full point of slippage. But its daytime and counter-trend controls REVERSE on the "
     "held-out sample and its placebo p is 0.097. &#9733; <strong>Shadow it to answer a question, not "
     "because we think it makes money</strong> &mdash; and it needs three code changes first (a wrapping "
     "clock window, an <code>atr_min</code> field, and ER10 rather than ER30).", "RIDER_ALL &sect;10, &sect;11"),
    ("<strong>BENCH 07:00&ndash;13:00Z for any late-boarding rider</strong>",
     "SHADOW &rarr; adopt as a router rule",
     "Red on all three independent legs (&minus;$29.38 / &minus;$20.04 / &minus;$2.43, the last on "
     "n=373). Cheap, fail-safe direction, no new instrument needed. The cleanest positive deliverable in "
     "the movement.", "UNCLASS &sect;11, &sect;13"),
    ("<strong>The violent-whipsaw bench</strong>", "MEASURE, then route",
     "The premise of the chop commission was wrong and the correction is worth more than the scalper. "
     "Across 18 days the tournament's loss is concentrated in <strong>violent-whipsaw</strong> blocks "
     "(&minus;$1,383.50 on 95 trades), NOT in plain chop (&minus;$403.00 on 58) &mdash; and on this "
     "week's two chop days the tournament took <strong>zero</strong> trades. A two-term router bench, "
     "worth roughly ten times the scalper it replaces.", "chopscalp &sect;2, &sect;13"),
    ("ER30 as a router ARM meter", "SHADOW as an instrumented question",
     "+$3.54 against &minus;$3.40 a trade on 3,238 untouched trades &mdash; the largest-n effect in the "
     "movement &mdash; but it REVERSES on the recent 11 sessions. Shadow the meter with its own control "
     "arm; do not arm a gate behind it.", "UNCLASS &sect;13"),
    ("<code>board_atrband</code>", "PARKED",
     "Revive only with a SELECTOR &mdash; something that predicts which board becomes a run. NOT more "
     "days: the power calculation says ~10,500 trades to separate it from zero.", "RIDER_ALL &sect;10"),
    ("<code>UNCL-RIDE-ER</code>", "PARKED",
     "Revive only with a board-time SIZE PREDICTOR expressed in ATRs (r &ge; 0.4 against eventual run "
     "size on &ge; 300 runs). More days will not fix it &mdash; 205 untouched sessions were already "
     "spent and the placebo won.", "UNCLASS &sect;13"),
    ("<code>mgc_coil_bounce</code>", "PARKED (updated)",
     "Last week killed it partly on the <strong>$7.50 cost error</strong>; at the corrected $4.50 the "
     "08-15 audit puts it at +$8.42 &mdash; breakeven rather than dead. Not re-derived this week. Revive "
     "by re-running it on the 29-day quote tape at the corrected cost.", "MGC &sect;14"),
    ("Lookback 90/120 min (gold)", "PARKED",
     "The year's monotone gradient does not survive the book gate. 45&ndash;180 min is a plateau; leave "
     "it at 60.", "MGC &sect;5.2"),
    ("<code>rider_w5</code> (live shadow arm)", "REFUTED &mdash; RETIRE THE ARM",
     "51 live forward trades at &minus;$28.84/tr, red in all four ATR buckets; 1,339 OOS trades at "
     "&minus;$5.43/tr with strip-3 at &minus;$9,293; &minus;$174 on the census week it was built for; "
     "and its in-sample +$1,936 collapses to +$282 on strip-best-3.", "RIDER_ALL &sect;5"),
    ("<code>UNCL-RIDER-ASIA</code>", "REFUTED &mdash; do not re-shadow",
     "Four consecutive red forward weeks. &#9733; And it was <strong>never actually shipped</strong> "
     "&mdash; there is no arm by that name anywhere in <code>shadow.db</code>, which nobody had "
     "noticed.", "UNCLASS &sect;9"),
    ("The <code>VACUUM</code> / <code>FLOW-LED</code> split", "REFUTED as a footprint &mdash; STOP SPLITTING",
     "The flow event fires on 20.4&ndash;20.6% of all tape and then splits it on a <strong>49.6&ndash;"
     "49.9% coin toss</strong> &mdash; 0.33 percentage points of directional information. The lift the "
     "flow event does carry is a MAGNITUDE lift and it is a volume proxy.", "FLOW-LED &sect;0, VACUUM &sect;2"),
    ("The <code>UNCLASS</code> label", "REFUTED as a footprint &mdash; RENAME",
     "Base rate 73.9% on the census week, 75.4% on the whole lake, lift <strong>0.82</strong>; its "
     "members sit ON the all-tape median for ATR, volume and efficiency. Rename it "
     "<code>UNTESTED</code> and report it as COVERAGE. Second independent measurement in two weeks.",
     "UNCLASS &sect;1, &sect;13"),
    ("The <code>OPEN/NEWS</code> label", "FIX &mdash; drop the footprint tests",
     "Its lift over the BARE CLOCK is <strong>0.921&times;</strong>: the flow and amplitude tests remove "
     "41% of the window and keep the <em>less</em> run-dense half. Either call it "
     "<code>US-OPEN-WINDOW</code> (3.09&times; lift on 8.87% of tape) or route the hunt through "
     "<code>VOL-EXPANSION</code> &mdash; 4.18&times; lift on 1.95% of tape, the sharpest cluster the "
     "census produces and the one it uses least.", "OPEN/NEWS &sect;1, &sect;15"),
    ("The census's flow-bucket PHASE", "FIX &mdash; this is a real bug",
     "21 of 68 labels change on bucket phase alone, and only 17 of 68 run timestamps are "
     "minute-aligned. Snap the window slide to the CLOCK, not to the array index.", "UNCLASS &sect;13"),
    ("The lake <code>bars</code> timeframe landmine", "FIX REQUIRED",
     "Backfill parquet at 1min/5mins/1hour/1day now sits beside the daily 5s files; any query without a "
     "<code>timeframe</code> filter inherits up to a full day of look-ahead on every day.", "MGC &sect;14"),
    ("L2 far-side depletion as a run selector", "REFUTED (two independent measurements)",
     "RIDER_ALL: 311 fires, 264M book rows, r = &minus;0.009, placebo p = 0.62. VACUUM: 49.44% "
     "&plusmn;2.52pp on unselected 55pt+ moves over 246.9M book rows, and 49.72% &plusmn;0.67pp on all "
     "21,249 book-minutes. <strong>Do not revive it at 30 days &mdash; the null is not n-limited.</strong>",
     "RIDER_ALL &sect;7, VACUUM &sect;6"),
    ("The far-side WALL as an absorption tell", "REFUTED, with the sign INVERTED",
     "The operator's core L2 hypothesis. Unfiltered chop turns drift +0.054pt in the fade's favour; "
     "requiring a wall &ge;1.5&times; turns that to &minus;0.117pt, and five-deep &ge;1.3&times; to "
     "&minus;0.374pt (t = &minus;1.72, quintile z = &minus;2.37). <strong>The wall is a TARGET, not "
     "absorption.</strong>", "chopscalp &sect;3"),
    ("The four run SHAPES (TURN / STEP-REPRICE / DRIFT-VOID / GRIND-CONT)", "SHIP TO THE CENSUS",
     "One <code>if</code> each, all computable at the run's start minute. Not a selector &mdash; "
     "vocabulary, to replace the three labels that just died.", "UNCLASS &sect;10"),
    ("The 41ms refill count", "KEEP &mdash; the one L2 term that ever helped",
     "The only book statistic in the chop lab that contributed anything. &#9733; And the 250ms "
     "<code>depth.db</code> sample <strong>cannot see it</strong> &mdash; it needs the 41ms "
     "<code>capture.db.book</code> feed, which is MNQ-only.", "chopscalp &sect;7, &sect;13"),
]

MONDAY = [
    ("Retire <code>rider_w5</code> from the shadow book.",
     "It is the only item here that costs nothing and is decided. 51 forward trades, "
     "&minus;$28.84 each, red in every ATR bucket including the one its own filter selects for. "
     "It has been running unwatched since 08-17 because nobody graded it.", "RIDER_ALL &sect;5"),
    ("Build the MGC depth-mid bar source, then let both gold arms run.",
     "This is the gating item for the entire gold programme and it is mechanical &mdash; the shadow "
     "service already holds the <code>DepthFeed</code> it needs. Keep the trade-bar arms alive as "
     "<code>*_tradebar</code> controls so the next reader can see the difference rather than take it "
     "on trust.", "MGC &sect;12.1"),
    ("Fix the census's flow-bucket phase, and rename two labels.",
     "21 of 68 labels move on bucket phase alone. Then <code>UNCLASS</code> &rarr; "
     "<code>UNTESTED</code> and <code>OPEN/NEWS</code> &rarr; <code>US-OPEN-WINDOW</code> with the two "
     "anti-predictive footprint tests deleted. Three labs reached this independently and it is the "
     "cheapest correction on the list.", "UNCLASS &sect;13, OPEN/NEWS &sect;15, FLOW-LED VERDICT"),
    ("Price the violent-whipsaw bench.",
     "The chop commission's premise was wrong &mdash; the tournament did not trade this week's chop "
     "days at all. Its money is lost in violent-whipsaw blocks, and a two-term bench there is worth "
     "roughly ten times the scalper that was commissioned to fix the wrong thing.", "chopscalp &sect;2"),
    ("Add <code>atr_min</code>, the wrapping clock window and an ER10 gate param to "
     "<code>ShadowVariant</code>.",
     "Three small changes, and they are a prerequisite for shadowing anything from this movement "
     "honestly. &#9733; This is exactly how <code>rider_w5</code> came to be quoted at +$19.29 while "
     "making &minus;$28.84: an arm shipped around a missing field records a DIFFERENT strategy under "
     "the same name.", "RIDER_ALL &sect;11"),
    ("Do NOT arm anything on MNQ out of this movement.",
     "Seven hunts, dozens of candidates, and not one MNQ LIVE candidate. That is the honest answer and "
     "it is stated plainly rather than dressed as a near-miss.", "the whole movement"),
]



def table(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    h = [f"<table{c}><tr>" + "".join(f"<th>{x}</th>" for x in headers) + "</tr>"]
    for r in rows:
        h.append("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>")
    h.append("</table>")
    return "".join(h)


def pill(v: str) -> str:
    head = v.split()[0].strip(",").upper()
    cls = {"LIVE": "pill-live", "SHADOW": "pill-shadow", "PARKED": "pill-parked",
           "REFUTED": "pill-dontarm", "BUILD": "pill-shadow", "FIX": "pill-dontarm",
           "MEASURE": "pill-shadow", "SHIP": "pill-live", "KEEP": "pill-live"}.get(head, "")
    return f'<span class="tag {cls}">{v}</span>'


def build() -> str:
    labs = {}
    for anchor, title, fname, what in LABS:
        p = pathlib.Path(SEC) / fname
        if not p.is_file():
            labs[fname] = None
            continue
        md = p.read_text()
        labs[fname] = dict(md=md, mtime=dt.datetime.fromtimestamp(p.stat().st_mtime, dt.UTC),
                           words=len(md.split()))
    present = [f for f, v in labs.items() if v]
    missing = [f for f, v in labs.items() if not v]

    h: list[str] = []
    h.append('<h2><span class="n">M3</span> The greenfield lab &mdash; seven hunts, every grave, '
             'and the two findings that outrank all of them</h2>')

    total_words = sum(v["words"] for v in labs.values() if v)
    newest = max((v["mtime"] for v in labs.values() if v), default=None)
    h.append(
        '<p class="lead">This is the cold half of the report at its coldest. We ignore everything the '
        'desk did, take the census\'s <strong>62 sat-out runs and $9,610 of hindsight ceiling</strong>, '
        'and try to build something from scratch that could have been in them. Seven separate hunts ran '
        'this cycle &mdash; one pooled rider across every run, one per cause-cluster, the chop-day scalp '
        'you commissioned, and gold &mdash; and between them they wrote '
        f'<strong>{total_words:,} words</strong> of tick-honest working, every one of which is '
        'reproduced in full in the appendix at the end of this movement.</p>')
    h.append(
        '<p class="lead"><strong>&#9733; The headline is a null, and I am going to say it in the first '
        'paragraph rather than the last: nothing from this movement is ready to trade on MNQ.</strong> '
        'Not one candidate out of seven hunts survived its own robustness battery. That is not a bad '
        'week — it is the batteries working, and three of the kills came from tests this desk only '
        'started running recently. What the movement <em>did</em> produce is worth more than another '
        'thin gate: two findings that reframe the whole hunt, four corrections to the census\'s own '
        'vocabulary, the first honest grade of the two arms we shipped last week (both dead), and seven '
        'harness bugs caught before they reached you rather than after.</p>')

    if missing:
        h.append('<div class="rev3"><div class="ct">&#9733; PART OF THIS MOVEMENT IS MISSING</div>'
                 f'<p>{len(missing)} of the {len(LABS)} lab dossiers were not on disk when this section '
                 f'was built: <code>{"</code>, <code>".join(missing)}</code>. Their hunts are absent '
                 'from every table below. Read that as <em>nobody looked</em>, never as <em>we looked '
                 'and found nothing</em>.</p></div>')

    # ── §0 THE BOARD ─────────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-board">1. The board &mdash; seven hunts, seven verdicts, in one table</h3>')
    h.append('<p>The best thing each hunt built, the number it reached before the battery, and the '
             '<strong>named test</strong> that killed it. Nothing on this table died of a hunch; every '
             'cause of death is a test you can re-run.</p>')
    h.append(table(
        ["Hunt", "What it built", "Best number reached", "The test that killed it", "Verdict", "Source"],
        [[f"<strong>{a}</strong>", b, f'<span class="num-cell">{c}</span>', d, pill(e),
          f"<span class='why'>{f}</span>"] for a, b, c, d, e, f in BOARD]))

    # ── §2 THE TWO FINDINGS ──────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-findings">2. The two findings that outrank every gate on that table</h3>')
    h.append(
        '<div class="card"><h3>&#9733; FINDING ONE &mdash; the tradeable threshold is about 120 points, '
        'and three labs reached it independently</h3>'
        '<p>This is the most durable result in the movement, and the reason it is durable is that '
        'nobody was looking for it. Three hunts, three different clusters, three different harnesses, '
        'three different authors &mdash; and the same number falls out of all of them.</p>'
        + table(["Lab", "How it was measured", "The number"], [
            ["OPEN/NEWS",
             "expectancy split by the run's eventual 30-minute follow-through",
             "+60&hellip;+120pt of follow-through still books <strong>&minus;$4.10/trade</strong>. "
             "Above 120pt: <strong>+$184.75/trade</strong>. Break-even hit rate 19.2%; the best arm "
             "delivered 30.8%"],
            ["VACUUM",
             "detector AUC against run size, lake-wide",
             "below <strong>|move| &asymp; 87pt</strong> three of four detectors are indistinguishable "
             "from noise; at and above it all four go significant &mdash; volume-z AUC 0.730, "
             "p = 0.0004, rising to <strong>AUC 0.867 on ATR for the 113 runs of 120pt+</strong>"],
            ["the census's own greenfield work",
             "a board rule conditioned on expected size",
             "boarding only fires whose move is <strong>&ge;120pt</strong> pays "
             "<strong>+$69.38/trade</strong> and passes the whole battery"]])
        + '<p><strong>What it means in plain English.</strong> The desk has been asking the wrong '
        'question. We keep hunting for a signal that says <em>a run is starting</em>, and we can '
        'already do that &mdash; the pooled rider gets inside <strong>62 of 62</strong> of the week\'s '
        'runs. What we cannot do is tell a 60-point run from a 160-point one at the moment we board, '
        'and below about 120 points a late board does not pay for its own stop. <strong>Hunt SIZE, not '
        'direction.</strong> That is a different study from any of the seven run this week, and it is '
        'the one I would commission next.</p></div>')
    h.append(
        '<div class="card"><h3>&#9733; FINDING TWO &mdash; detection is solved; selection is not; and '
        'the ceiling is not what the census says it is</h3>'
        '<p>Every hunt that boarded a run boarded it successfully. The pooled rider fires inside '
        '<strong>62 of 62</strong> sat-out runs at a median <strong>three minutes</strong> late with a '
        'median <strong>41 points still ahead</strong>. UNCLASS\'s rider gets inside 40 of its 41 at a '
        'median 3.3 minutes with 2.57 ATRs left. OPEN/NEWS separates &ge;200pt runs from ordinary tape '
        'at <strong>AUC 0.848</strong> on trade-count alone. Detection is not the problem and has not '
        'been for some time.</p>'
        '<p><strong>The problem is that the same trigger fires 34 times a day</strong>, and roughly one '
        'fire in twenty becomes a run. Direction carries almost nothing: AUC 0.55&ndash;0.65 at best, '
        'and a crude momentum rule agrees with the run 54.2% of the time against a 53.4% base rate. '
        'With-trend does beat counter-trend in every one of three out-of-sample exit configurations, by '
        '+0.06 to +0.11R &mdash; real, and about the size of the round trip.</p>'
        '<p>&#9733; <strong>And the $9,610 is not $9,610.</strong> This correction should follow the '
        'census number everywhere it is quoted from now on:</p>'
        + table(["Version of the ceiling", "MNQ, this week", "% of the headline"], [
            ["the census's hindsight number (perfect entry AND perfect exit)", "$9,610", "100%"],
            ["a <em>perfect</em> late boarder &mdash; fires inside every run at a median three minutes "
             "in, exits at the exact top, <strong>zero costs</strong>", "<strong>$5,094</strong>", "53%"],
            ["a deployable late boarder with a real stop and real costs",
             "<strong>$1,910&ndash;$2,286</strong>", "20&ndash;24%"],
            ["runs already finished before any honest trigger can see them",
             "13% of them", "&mdash;"]])
        + '<p>UNCLASS reaches the same shape on its own bucket: a $5,840 ceiling becomes $3,239 (55%) '
        'for a perfect exit and <strong>$1,592 (27%)</strong> for an honest late board with a real '
        'stop. So the honest size of the prize is roughly a fifth to a quarter of the number on the '
        'front of Movement&nbsp;1 &mdash; which is still real money, and is a very different target to '
        'aim a year of work at.</p></div>')

    # ── §3 CLOSING THE LOOP ──────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-loop">3. Closing the loop &mdash; the two arms we shipped last week, graded '
             'for the first time</h3>')
    h.append('<p>Last week\'s greenfield work produced two things that went into the shadow book. '
             'Nothing had graded either of them. Both hunts went back and did it, unprompted, and '
             '<strong>both arms are dead</strong> &mdash; one of them was never actually shipped, which '
             'is its own finding.</p>')
    h.append(table(
        ["Arm", "What it was quoted at", "What it actually did", "Verdict"], [
            ["<code>rider_w5</code><br><span class='why'>shipped into <code>shadow.db</code> "
             "2026-08-15 off last week's RIDER_ALL phase</span>",
             "<strong>+$4,841</strong>, +$19.29 a trade",
             "<strong>51 forward trades since 08-17: &minus;$1,471, &minus;$28.84 a trade</strong>, "
             "18% wins, red on 6 of 7 days and red in <em>all four</em> ATR buckets &mdash; worst in "
             "the 11&ndash;16 band its own filter selects for. Zero flagged rows: this is clean data, "
             "not a measurement artefact. Its in-sample +$1,936 collapses to +$282 on strip-best-3, and "
             "the +$19.29 it shipped on never had a strip test attached.",
             pill("REFUTED") + " retire the arm"],
            ["<code>UNCL-RIDER-ASIA</code><br><span class='why'>last week's SHADOW pick out of the "
             "UNCLASS phase</span>",
             "a promotion candidate",
             "Four consecutive red forward weeks: W31 &minus;$2.93, W32 &minus;$15.90, W33 "
             "&minus;$36.46, <strong>W34 &minus;$38.08</strong> &mdash; and the ATR floor added to "
             "explain the first two restored none of them. &#9733; <strong>Then the deeper finding: "
             "there is no arm by that name anywhere in <code>shadow.db</code>.</strong> All 82 "
             "strategies in the book were listed. It was never shipped, and nobody noticed for a week.",
             pill("REFUTED") + " do not re-shadow"]]))
    h.append('<p><strong>Read those two rows together, because they are the same lesson twice.</strong> '
             'A number that goes into the shadow book without a strip test and without anybody owning '
             'the grading is not evidence &mdash; it is a claim with a week\'s head start. Both arms '
             'were quoted from in-sample headlines; both are now refuted by forward data that cost '
             'nothing to collect and that nobody was collecting. <strong>The fix is not analytical, it '
             'is procedural: every arm shipped needs a named grading date, and every shipped number '
             'needs its strip-best figure printed beside it.</strong></p>')

    # ── §4 THE VOCABULARY ────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-labels">4. The census\'s own vocabulary did not survive the week</h3>')
    h.append('<p>The brief tells every cluster hunt to <strong>interrogate the label before building '
             'anything on top of it</strong>. Four did. Three of the five labels failed, and the '
             'failures are independent measurements by different authors on different tape. This '
             'matters more than any single gate, because <em>every</em> hunt this desk scopes by '
             'cluster inherits the error.</p>')
    h.append(table(
        ["Label", "What it is supposed to mean", "What it actually is", "Do this"], [
            ["<code>UNCLASS</code><br><span class='why'>41 of 68 runs &mdash; the biggest bucket</span>",
             "no clear tape tell (quiet ignition)",
             "Base rate <strong>73.9%</strong> on the census week and <strong>75.4%</strong> on the "
             "whole lake, lift <strong>0.82</strong> &mdash; i.e. a run is <em>less</em> likely to be "
             "UNCLASS than an arbitrary minute is. Its members sit ON the all-tape median for ATR, "
             "volume and efficiency.",
             "Rename it <code>UNTESTED</code> and report it as <strong>coverage</strong>, not as a "
             "finding. Second independent measurement in two weeks."],
            ["<code>VACUUM</code> / <code>FLOW-LED</code><br><span class='why'>9 and 4 runs</span>",
             "moved against the tape / aggressors drove it",
             "One population cut by its own outcome. The flow event fires on <strong>20.4&ndash;20.6% "
             "of every tape-minute we own</strong>, then splits it VACUUM 10.37% / FLOW-LED 10.21% on a "
             "<strong>49.6&ndash;49.9% coin toss</strong> &mdash; 0.33 percentage points of directional "
             "information. The census's apparent 15.7%-vs-10.2% excess is entirely a selection artefact "
             "of the keep-strongest run-picker (prior-5min agreement 48.66% unselected &rarr; 22.55% "
             "deduped). Whatever lift the flow event carries is a MAGNITUDE lift, and that lift is a "
             "volume proxy: flow-unusual with volume-ordinary gives 0.963&times; base (no lift at all); "
             "volume-unusual with flow-balanced gives 1.220&times;.",
             "<strong>Stop splitting the census on flow.</strong> This week's 4-vs-9 split is noise "
             "(expected 9.0 vs 9.6; P(&le;4 of 13) = 0.139)."],
            ["<code>OPEN/NEWS</code><br><span class='why'>13 runs</span>",
             "the 13:00&ndash;15:00Z cash-open / data window, footprint-confirmed",
             "A clock with an <strong>anti-predictive</strong> filter bolted on. The 08-15 fix correctly "
             "demoted it from checked-first to checked-last (100% &rarr; 58.7% of its own window) &mdash; "
             "but its lift over the <em>bare clock</em> is <strong>0.921&times;</strong>. The flow and "
             "amplitude tests remove 41% of the window and keep the <em>less</em> run-dense half. Same "
             "answer in the tick era (0.946&times;).",
             "Either drop the two footprint tests and call it <code>US-OPEN-WINDOW</code> "
             "(<strong>3.09&times;</strong> lift on 8.87% of tape), or route the hunt through "
             "<code>VOL-EXPANSION</code> &mdash; <strong>4.18&times; lift on 1.95% of tape</strong>, "
             "the sharpest cluster the census produces and the one it uses least."],
            ["the bucket <em>phase</em> itself",
             "a stable assignment",
             "<strong>21 of 68 labels change on bucket phase alone</strong>, and only 17 of 68 run "
             "timestamps are minute-aligned. The window slides on the array index rather than on the "
             "clock.",
             "<strong>A real bug. Fix it before the next census.</strong>"]]))
    h.append('<p>What replaces them is already written: UNCLASS\'s hunt proposes <strong>four run '
             'SHAPES</strong> &mdash; TURN, STEP-REPRICE, DRIFT-VOID and GRIND-CONT &mdash; each one '
             '<code>if</code> statement, all computable at the run\'s start minute. That is vocabulary, '
             'not a selector, and it is honest about being vocabulary.</p>')

    # ── §5 PER-LAB CARDS ─────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-labs">5. The seven hunts, one card each</h3>')
    h.append('<p>Each card is the shortest honest account of a hunt; the full dossier for every one of '
             'them is reproduced in the appendix at the end of this movement, sweep tables and all.</p>')
    for anchor, title, fname, what in LABS:
        v = labs.get(fname)
        if not v:
            h.append(f'<div class="rev3"><div class="ct">&#9733; MISSING</div><p><strong>{title}</strong> '
                     f'&mdash; <code>{fname}</code> is not on disk. {what}</p></div>')
            continue
        h.append(f'<div class="card"><h3>{title}</h3><p class="why">{what} &nbsp;&middot;&nbsp; '
                 f'<code>{fname}</code>, {v["words"]:,} words, written '
                 f'{v["mtime"]:%Y-%m-%d %H:%M} UTC &nbsp;&middot;&nbsp; '
                 f'<a href="#app-{anchor}">read it in full &rarr;</a></p>'
                 + LAB_CARD[fname] + '</div>')

    # ── §6 THE GRAVES ────────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-graves">6. Every grave, by name, with the test that killed it</h3>')
    h.append('<p>The operator\'s standing rule is that the failures are the deliverable, so here they '
             f'all are &mdash; <strong>{len(GRAVES)} named candidates and mechanisms</strong>, each with '
             'the specific test that killed it. A verdict with no visible working is worthless, and a '
             'grave with no named cause of death is a hunch.</p>')
    h.append(table(["Candidate", "Hunt", "Killed by", "The number", "Disposition"],
                   [[f"<code>{a}</code>", b, f"<strong>{c}</strong>", d, pill(e)]
                    for a, b, c, d, e in GRAVES]))
    h.append('<p><strong>&#9733; And note what is NOT on that list: nothing died of thin n alone.</strong> '
             'Thin n is a SHADOW or a PARK, never a refutation, and the standing scope says so. Every '
             'REFUTED row above carries a named test on a sample big enough to carry it &mdash; a '
             'placebo, a sign-flip control, a strip-the-best, or an out-of-sample leg.</p>')

    # ── §7 HARNESS BUGS ──────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-bugs">7. Seven things the labs caught in their own instruments</h3>')
    h.append('<p>Every one of these was found by the lab that would have benefited from not finding it, '
             'and reported anyway. Read this section as the reason to trust the nulls above.</p>')
    h.append(table(["What", "Where", "What happened", "Why it matters"],
                   [[f"<strong>{a}</strong>", f"<span class='why'>{b}</span>", c, d]
                    for a, b, c, d in BUGS]))

    # ── §8 GOLD ──────────────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-gold">8. Gold, in its own right &mdash; and the week\'s single most '
             'expensive lesson</h3>')
    h.append(
        '<p class="lead">Last Friday we shadowed a gold gate called <code>mgc_hole_break_fade</code>. It '
        'has been running live in the shadow book since Monday and <strong>it is losing money: '
        '&minus;$1,196 across 80 trades in seven days, every one of its three arms red.</strong> '
        'Replaying the same seven days in the lab gives <strong>+$512</strong>. That is not a small '
        'disagreement, and the answer turned out to be one fixable thing.</p>')
    h.append(
        '<div class="callout"><div class="ct">&#9733;&#9733;&#9733; THE GATE IS BEING FED THE WRONG '
        'TAPE</div>'
        '<p>The research builds its one-minute bars from the <strong>depth mid</strong> &mdash; the '
        'midpoint of the order book, which updates every 250&nbsp;milliseconds whether or not anything '
        'trades. The live service builds its bars from <strong>trades</strong>. Gold prints sparsely, so '
        'those are not the same series, and a sixty-minute high taken from one is not the sixty-minute '
        'high of the other. Hold absolutely everything else constant &mdash; same break rule, same book '
        'filter, same exit, same spread-honest race &mdash; and change only the input tape:</p>'
        + table(["the same rule, exit and race, on the six forward days both tapes cover", "n", "net",
                 "$/trade"],
                [["<strong>depth-mid bars</strong> (what the research measured)", "56",
                  "<strong>+$172</strong>", "<strong>+$3.06</strong>"],
                 ["<strong>trade bars</strong> (what the live service actually reads)", "53",
                  "<strong>&minus;$475</strong>", "<strong>&minus;$8.96</strong>"]])
        + '<p><strong>The sign flips on the bar source alone</strong>, and the trade-bar number is the '
        'one the live shadow independently produced. So this is not a mystery and it is not a research '
        'failure &mdash; it is a plumbing mismatch between the lab and production, and the fix is '
        'mechanical: the service already holds a <code>DepthFeed</code> connection to gold\'s book (it '
        'needs it for the liquidity filter anyway), so it already has the bid and the ask. It just needs '
        'to build its minute bar from their midpoint instead of from trades. <strong>Until that is done '
        'I would not promote a single gold cell, and I am not proposing one.</strong></p></div>')
    h.append('<h4>The per-cell verdicts &mdash; MGC, $10.00 a point, $1.50 the round trip</h4>')
    h.append(table(
        ["Cell", "Gate", "n (29d)", "net", "$/trade", "forward 7d", "placebo", "live shadow",
         "Verdict", "Note"],
        [[f"<strong>{a}</strong>", b, f'<span class="num-cell">{c}</span>', d, e, f, g, i,
          pill(j), k] for a, b, c, d, e, f, g, i, j, k in MGC_CELLS]))
    h.append(
        '<p><strong>The exit family every gold cell needs</strong> is the <strong>wide chandelier on a '
        'single lot</strong> &mdash; stop 3.0&nbsp;ATR, arm 2.0, trail 2.0, 480-minute backstop. Not '
        'the tight scalp (negative at 1R on both entries). Not the dual slot (Lot&nbsp;A is negative on '
        'gold and cancels Lot&nbsp;B, on both entries). Not a time cap (its headline numbers are a '
        'long-drift artefact). &#9733; <strong>That is the exact opposite of the live MNQ slot '
        'configuration, and it replicates on 29 days.</strong> Gold is not the Nasdaq with a different '
        'multiplier, and the standing rule that MGC gates must be invented fresh rather than ported is '
        'earning its keep.</p>')
    h.append(
        '<div class="card"><h3>Three more things gold produced this week</h3>'
        '<p><strong>1. A year of tape arrived.</strong> The lake gained <strong>320 trading days</strong> '
        'of MGC minute bars (2025-07-28 &rarr; 2026-08-19) against last week\'s twenty-nine. It kills '
        'last week\'s router rule outright &mdash; that rule would bench the gate in NORMAL_CHOP, which '
        'is the regime currently paying best &mdash; closes last week\'s one loose thread, and puts a '
        'much colder light on the bare trigger (direction is real on 320 days; the P&amp;L is not).</p>'
        '<p><strong>2. The unturned stone paid, and it is a VETO not a confirm.</strong> Gold against the '
        'Nasdaq on the same clock, over <strong>278 paired days</strong>: fading a gold break that the '
        'Nasdaq <em>agrees</em> with loses <strong>$10.52 a trade</strong> and sits at the 2.5th '
        'percentile of its own placebo. As an arm it reads +$5.43/tr against +$1.72 blanket. It does '
        '<em>not</em> reproduce on the 29-day book window (34th percentile), so it is a shadow arm with '
        'a question attached, not a promotion. The mirror &mdash; a cross-asset momentum <em>confirm</em> '
        '&mdash; is cleanly negative (&minus;$2.29/tr on the same 278 days), which is what a real '
        'asymmetry looks like.</p>'
        '<p><strong>3. A look-ahead in the lab\'s own harness, caught before it reached you.</strong> A '
        'volatility cell read <strong>+$71,608</strong> until the author noticed it was entering at the '
        'open of the bar whose high it had already used. Corrected: <strong>&minus;$12,462</strong>. '
        'That number would otherwise have been the biggest in this report.</p></div>')

    # ── §9 MONDAY ────────────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-monday">9. What this movement asks for on Monday</h3>')
    h.append('<p>Six items. <strong>None of them is &ldquo;arm a gate&rdquo;</strong>, and that is the '
             'honest output of seven hunts. Four are builds or fixes, one is a retirement, and one is a '
             'measurement.</p>')
    h.append(table(["Do this", "Why", "Source"],
                   [[f"<strong>{i+1}. {a}</strong>", b, f"<span class='why'>{c}</span>"]
                    for i, (a, b, c) in enumerate(MONDAY)]))

    # ── §10 DISPOSITION ──────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-dispo">10. Disposition &mdash; every lead this movement touched</h3>')
    h.append('<p>Four dispositions, one each. <strong>PARKED</strong> names the specific thing that '
             'would revive it; <strong>REFUTED</strong> names the test and why no reformulation saves '
             'it. Nothing here is a graveyard &mdash; a PARKED row is a lead with a stated price.</p>')
    h.append(table(["Lead", "Verdict", "Required note", "Source"],
                   [[f"{a}", pill(b), c, f"<span class='why'>{d}</span>"] for a, b, c, d in DISPO]))

    # ── §11 STONES ───────────────────────────────────────────────────────────────────────────
    h.append('<h3 id="m3-stones">11. The stones still unturned</h3>')
    h.append(table(["The stone", "Why it is the next one", "What it needs"], [
        ["<strong>Selection by expected SIZE at the board moment</strong>",
         "It is the direct consequence of both headline findings. Three labs independently found that "
         "the money starts at about 120 points of follow-through, and <em>not one</em> of the seven "
         "hunts tested a size predictor at the moment of boarding. Every hunt this week asked "
         "&ldquo;is a run starting?&rdquo; and we already know the answer is yes 34 times a day.",
         "<strong>No new data source.</strong> A different question asked of tape we already hold: a "
         "board-time predictor of eventual run size in ATR units, r &ge; 0.4 on &ge; 300 runs."],
        ["<strong>Is gold's BOOK as sparse as gold's TRADES?</strong>",
         "The bar-source finding says the depth mid is the better price series because gold prints "
         "sporadically. But the liquidity filter reads that same book &mdash; so if the book is also "
         "thin or stale in exactly the minutes where trades are absent, the &ldquo;empty far side&rdquo; "
         "the gate selects for may sometimes be an <em>absent feed</em> rather than an absent bid.",
         "Split the hole cell by tape activity (trades-per-minute in the minute before the break) and "
         "check the empty-book cell still pays in the <em>busiest</em> quartile. The cheapest possible "
         "test of the concern."],
        ["<strong>Is the ER meter's forward reversal a regime break or an artefact?</strong>",
         "ER30 as an arm meter is the largest-n effect in the movement &mdash; +$3.54 against "
         "&minus;$3.40 a trade on 3,238 untouched trades &mdash; and it reverses on the most recent "
         "eleven sessions. One of those two readings is noise and we do not know which.",
         "Free: shadow the meter with its own control arm and wait. The single cheapest open question "
         "in the movement."],
        ["<strong>A different book statistic</strong>",
         "Far-side depth share is refuted twice over and is not n-limited, so more days will not save "
         "it. But the chop lab found that the one L2 term that ever helped was the <strong>41ms refill "
         "count</strong> &mdash; a rate, not a level.",
         "The 250ms <code>depth.db</code> sample cannot see it; it needs the 41ms "
         "<code>capture.db.book</code> feed, which is MNQ-only and rolls off after five trading days. "
         "Mirror it to the lake first, or the study cannot be run at length."]]))

    # ── APPENDIX ─────────────────────────────────────────────────────────────────────────────
    h.append('<hr class="frag-sep">')
    h.append('<h3 id="m3-appendix">Appendix &mdash; the seven dossiers in full</h3>')
    h.append('<p class="lead">Everything above is a map. This is the territory: each hunt\'s complete '
             'working, as its author wrote it &mdash; every sweep table, every control, every grave, '
             'every caveat, including the ones that cut against the author\'s own numbers. Nothing has '
             'been summarised out. If a claim in the editorial half above looks too strong, the '
             'dossier it came from is here and it will say so itself.</p>')
    for anchor, title, fname, what in LABS:
        v = labs.get(fname)
        if not v:
            continue
        h.append(f'<hr class="frag-sep"><h4 id="app-{anchor}">{title}</h4>')
        h.append(f'<p class="why"><code>{fname}</code> &nbsp;&middot;&nbsp; {v["words"]:,} words '
                 f'&nbsp;&middot;&nbsp; written {v["mtime"]:%Y-%m-%d %H:%M} UTC</p>')
        h.append(md_to_html(v["md"], h_offset=3))

    doc = "\n".join(h)
    return doc


# The per-hunt card bodies. Kept beside the data rather than inline in build() so that a number
# and its neighbours stay legible as a block; every figure is from the dossier named in the key.
LAB_CARD = {
    "gf_full_RIDER_ALL.md":
        '<p><strong>What it did.</strong> Built the direction-agnostic run-catcher, boarded it late, '
        'swept the exit wider than this desk has ever run one, filtered it with a causal rule, and put '
        'the survivor through the whole battery. It passed <em>every</em> in-sample test we have, '
        'including two separate placebo controls.</p>'
        '<p><strong>Then it died at Step&nbsp;3, the causal filter, and the test that killed it was the '
        'out-of-sample leg: 1,289 trades over 236 untouched sessions for a total of +$14.</strong> Not '
        'a loss. Not a win. Nothing &mdash; the 95% confidence interval on its expectancy runs from '
        '&minus;0.204R to +0.246R, which is measuring zero with a wide ruler.</p>'
        '<p><strong>The second witness is the one to trust.</strong> <code>rider_w5</code>, the arm this '
        'phase shipped last week at a quoted +$19.29 a trade, has taken 51 live forward trades and sits '
        'at &minus;$28.84 a trade, red in every ATR bucket. Two independent measurements, same answer. '
        '&#9733; One thing survived to incubation: <code>board_overnight</code> (21:00&ndash;07:00Z) '
        'keeps its sign in two independent samples and survives a full point of slippage &mdash; but its '
        'daytime and counter-trend controls <em>reverse</em> on the held-out leg, so it is shadowed as a '
        'question, not as a candidate.</p>',
    "gf_full_UNCLASS.md":
        '<p><strong>What it did.</strong> The biggest bucket &mdash; 41 of the 68 runs &mdash; and one '
        'that had never been hunted, because our own classifier could not name it. It was BUILT (a late '
        'boarder that gets inside 40 of the 41 runs at a median 3.3 minutes late with 2.57 ATRs still '
        'ahead), RIDDEN (exit swept stop 1.0&ndash;4.0&times;ATR against target 2&ndash;16&times;ATR), '
        'FILTERED (eight causal cuts, each placebo-controlled against discarding the same NUMBER of '
        'fires at random) and ROUTED &mdash; the operator\'s order of work, in the operator\'s order.</p>'
        '<p><strong>And it still lost.</strong> Killed by the placebo/shuffle test and corroborated by '
        'the out-of-sample leg: on 205 untouched sessions the real signal makes +$3.54 a trade and the '
        'same rule taken <em>thirty minutes early</em> makes +$4.44. The family kill is stronger than '
        'the single cell &mdash; across 137 configurations with usable n on both independent legs, 13% '
        'are positive on both against a 12% chance rate.</p>'
        '<p>&#9733; <strong>Two keepers.</strong> The exit sweep found a genuine <strong>10&times;ATR '
        'target ridge that holds across every stop width</strong> &mdash; so the operator\'s wide-exit '
        'thesis is CONFIRMED on the target axis and REFUTED on the stop axis; the stop is not what '
        'shakes us out, because we are not being shaken out. And <strong>benching 07:00&ndash;13:00Z '
        'for any late-boarding rider replicates on all three independent legs</strong>, which makes it '
        'the cleanest positive deliverable in the movement.</p>',
    "gf_full_OPEN-NEWS.md":
        '<p><strong>What it did.</strong> Hunted the densest run window on the clock &mdash; and then '
        'built the control that killed the whole page.</p>'
        '<p><strong>The control is the finding.</strong> A gate containing <em>no signal at all</em> '
        '&mdash; &ldquo;enter at 13:05Z, direction = the sign of the last 15 minutes, stop 0.5&times;U, '
        'hold 30 minutes&rdquo; &mdash; books <strong>+$47.29 a trade over 26 trades</strong>, double '
        'the best gate the phase built. The identical rule twenty-five minutes later books '
        '&minus;$13.46. Everything on the page sits inside the noise band of that control, and the '
        'confidence intervals agree: t = 1.30 and 1.57, and <strong>561 trades &asymp; 79 trading '
        'days</strong> would be needed to resolve a $10/trade edge in this window. We have 27.</p>'
        '<p><strong>The two leaders died by name.</strong> MOMBRK (+$32.87/tr, n=52) on strip-the-best '
        '&mdash; its top 3 trades are 88.5% of the net &mdash; and on an OOS leg of &minus;$16.50/tr. '
        'PULSE-13h (+$23.09/tr, n=95) on the placebo: a copy of the signal delayed thirty minutes books '
        '<strong>more money than the real one</strong>.</p>',
    "gf_full_FLOW-LED.md":
        '<p><strong>What it did.</strong> Nine candidates off the flow print, every one of them dead, '
        'each with a different named cause &mdash; the blanket screen took four, the OOS leg took one, '
        'strip-the-3-best took two, the parameter sweep took one, and the last survivor '
        '<code>FL-4 flow_ignition</code> died on the placebo/shuffle test at p = 0.150, with the best '
        'of forty time-shifted <em>fake</em> flow series beating the real signal outright.</p>'
        '<p><strong>And there is no size at which it starts working.</strong> On the predictor side '
        'every flow-z bar from 1.0 to 4.0 is positive in-sample and negative out of sample. On the '
        'outcome side, flow agreement with the run runs 48.4&ndash;53.7% from 55pt to 200pt and never '
        'departs from a coin flip by as much as one sigma.</p>'
        '<p>&#9733; <strong>The finding that outranks all of it: the label is not a footprint.</strong> '
        'The <code>flow</code> column measures <em>how much</em> traded, not <em>who</em> was buying '
        '&mdash; flow unusual with volume ordinary gives 0.963&times; base (no lift); volume unusual '
        'with flow balanced gives 1.220&times;. The census should stop splitting runs into FLOW-LED and '
        'VACUUM; they are one population cut by its own outcome.</p>',
    "gf_full_VACUUM.md":
        '<p><strong>What it did.</strong> Four candidates invented, four graves, and &mdash; for the '
        'second Friday running &mdash; the cluster was killed by its own LABEL rather than by a '
        'backtest. This week the mechanism is identified rather than just the symptom: the census\'s '
        'apparent VACUUM excess (15.7% of runs against a 10.2% base) is <strong>entirely a selection '
        'artefact of the keep-strongest run-picker</strong>.</p>'
        '<p><strong>The kill that generalises is the sign-flip control.</strong> '
        '<code>VAC-IGN-BRK</code> looked like the phase\'s survivor at +$911.55 over 284 trades &mdash; '
        'until fading the break was found to earn +$3.08 a trade against the signal\'s +$3.21. '
        '<em>Both directions win.</em> That is volatility harvesting with a stop on it, not an edge, and '
        'no amount of n fixes it.</p>'
        '<p>&#9733; <strong>Two keepers.</strong> Last week\'s open stone is closed &mdash; the L2 '
        'far-side-depletion discriminator is REFUTED at 49.44%&nbsp;&plusmn;2.52pp over 246.9M book '
        'rows, and it is <em>not</em> n-limited, so do not revive it at 30 days. And the detection '
        'threshold is real: below |move| &asymp; 87pt three of four detectors are noise; at and above '
        'it, all four go significant.</p>',
    "gf_chopscalp.md":
        '<p><strong>What it did.</strong> The operator\'s own commission &mdash; a purpose-built '
        'chop-day turn scalper, led by the order book, same lineage as <code>exhaustion_short</code>. '
        'Raced tick by tick over 17 full-stack days: 20.7M trade ticks, <strong>261.9M forty-one-'
        'millisecond ten-deep book rows</strong>, 4.6M depth snapshots, 26.2M quote updates, sixteen '
        'named candidates and 1,848 costed parameter cells.</p>'
        '<p><strong>The lead hypothesis is refuted and it points the wrong way.</strong> Requiring the '
        'far side to be ABSORBING &mdash; a big resting wall the price must eat to continue &mdash; '
        'does not help the fade, it <em>hurts</em> it, in two independent tests. Unfiltered chop turns '
        'drift +0.054pt in the fade\'s favour; add &ldquo;wall &ge; 1.5&times;&rdquo; and that becomes '
        '&minus;0.117pt; five-deep &ge; 1.3&times; and it becomes &minus;0.374pt. <strong>The wall is '
        'not absorption at a range edge. It is a target.</strong></p>'
        '<p><strong>The finalist died to a test we should run more often.</strong> <code>CT15</code> '
        'passed everything &mdash; in-sample, out-of-sample, 13/13 leave-one-day-out, strip-best-5 '
        '&mdash; and on a single pre-registered cell its shuffle p is 0.017. But that cell came out of '
        'a 1,080-cell search, so the null was handed <em>the same search</em>: the null\'s own best '
        'cell averages +$8.42 a trade and beats the real one <strong>85.3% of the time</strong>.</p>'
        '<p>&#9733; <strong>And the premise needed correcting, which is worth more than the '
        'scalper.</strong> The desk did not donate on this week\'s chop days &mdash; the tournament took '
        '<strong>zero</strong> trades on 08-20 and 08-21. The week\'s &minus;$2,323 is '
        '<code>day_rider</code>\'s book. Across the whole 18-day window the tournament\'s loss is '
        'concentrated in <strong>violent-whipsaw</strong> (&minus;$1,383.50 on 95 trades), not plain '
        'chop (&minus;$403.00 on 58). That is a router bench to price, not a gate to build.</p>',
    "gf_MGC.md":
        '<p><strong>What it did.</strong> Graded last week\'s live gold shadow, found it losing, and '
        'ran the contradiction to ground &mdash; then opened thirteen months of gold tape and re-tested '
        'everything on it.</p>'
        '<p><strong>The headline is a plumbing fault, not a research failure.</strong> The lab builds '
        'its minute bars from the depth mid; the live service builds them from trades; gold prints '
        'sparsely, so those are different series and the sign of the gate flips between them. Full '
        'working and the numbers are in &sect;8 above.</p>'
        '<p>&#9733; <strong>Three more.</strong> A year of tape (320 trading days) arrived and killed '
        'last week\'s router rule outright. The unturned stone &mdash; gold against the Nasdaq &mdash; '
        'paid, as a <em>veto</em>, on 278 paired days. And the author caught a look-ahead in their own '
        'harness that read +$71,608 and corrected to &minus;$12,462.</p>',
}


def main() -> int:
    doc = build()
    pathlib.Path(OUT).write_text(doc)
    print(f"MOVEMENT 3 → {OUT} ({len(doc):,} bytes, {word_count(doc):,} words)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
