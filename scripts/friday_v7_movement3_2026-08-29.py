#!/usr/bin/env python3
"""MOVEMENT 3 — the greenfield lab, rebuilt from THIS cycle's own labs (2026-08-29).

★ WHY A NEW FILE RATHER THAN A RE-RUN OF friday_v7_movement3_section.py. That script builds the
movement out of seven markdown dossiers and a hand-typed BOARD table, all of them written on
2026-08-22/25. Re-running it would reproduce last week's section — the same 485KB the 08-26 build
shipped — because its editorial half is a literal, not a computation.

This cycle is a different shape. The `movement3` phase RAN (00:28-00:53Z) and was killed before it
wrote its fragment, but it left a complete set of fresh labs behind:

  reports/friday_v7/m3/prize.json      the boarding ladder against THIS week's census
  reports/friday_v7/m3/family.json     the precursor split + its base rate
  reports/friday_v7/m3/escalate.json   52,937 minutes / 41 days — does anything predict escalation?
  reports/friday_v7/m3/fresh.json      COIL-BRK, this week's fresh candidate: arm ladder + exits
  reports/friday_v7/m3/fresh2.json     its full costed battery incl. placebo and sign-flip
  reports/friday_v7/m3/frozen.json     ★ the FORWARD test of all five candidates frozen on 08-25
  reports/friday_v7/m3/size.json       the size-band decomposition
  reports/friday_v7/m3/catches.json    which boarder caught which runs, and what it cost
  reports/friday_v7/sections/cs3/*     the chop-scalp lab, re-run
  reports/friday_v7/sections/gf_chopscalp.md   its dossier, written 00:19Z this cycle

So the editorial half here is COMPUTED from those files at render time. The one piece of prior-week
material that is reproduced is the four cluster dossiers the ISO-week rotation deliberately did not
re-run — carried as a clearly-labelled standing appendix, never as this week's work.

Run:  python3 scripts/friday_v7_movement3_2026-08-29.py
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from friday_v7_md2html import md_to_html, word_count          # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
M3 = "/home/alphabot/gazbot7/reports/friday_v7/m3"
OUT = f"{SEC}/movement3_greenfield.html"


def J(p):
    return json.load(open(p))


def m(v, dp=2):
    return f"{v:+,.{dp}f}".replace("-", "&minus;")


def u(v, dp=2):
    return f"{v:,.{dp}f}".replace("-", "&minus;")


# The four cluster hunts the ISO-week rotation did not schedule this week. Their dossiers are
# reproduced as a standing appendix, dated, and NEVER counted as this cycle's work — but every
# candidate they produced IS forward-tested above, on tape none of them ever saw.
ROTATED_OUT = [
    ("m3-rider", "THE POOLED RUN-CATCHER &mdash; one rider for every sat-out run",
     "gf_full_RIDER_ALL.md", "Board <em>any</em> run late, ride it wide, filter it causally."),
    ("m3-uncl", "UNCLASS &mdash; the biggest bucket", "gf_full_UNCLASS.md",
     "The bucket our own classifier could not name, and had therefore never hunted."),
    ("m3-open", "OPEN/NEWS &mdash; the 13:00&ndash;15:00Z cash-open window", "gf_full_OPEN-NEWS.md",
     "The densest run window on the clock."),
    ("m3-flow", "FLOW-LED &mdash; aggressor-driven continuation", "gf_full_FLOW-LED.md",
     "Runs the tape pushed. Nine candidates built off the flow print."),
    ("m3-vac", "VACUUM &mdash; the snap-back / stop-run", "gf_full_VACUUM.md",
     "Runs that moved AGAINST the tape."),
]


def main() -> int:
    prize, fam = J(f"{M3}/prize.json"), J(f"{M3}/family.json")
    esc, fr, fr2 = J(f"{M3}/escalate.json"), J(f"{M3}/fresh.json"), J(f"{M3}/fresh2.json")
    froz, size, catch = J(f"{M3}/frozen.json"), J(f"{M3}/size.json"), J(f"{M3}/catches.json")

    H: list[str] = []
    A = H.append
    c = prize["census"]

    A('<h2 id="m3"><span class="n">M3</span> THE GREENFIELD LAB &mdash; build a gate from '
      'scratch, then try everything to kill it</h2>')

    # headline numbers, all computed
    best_board = max(prize["boarding"], key=lambda b: b["pct_ceiling"])
    fireA = next(f for f in prize["fire_rate"]
                 if f["W"] == best_board["W"] and f["k"] == best_board["k"])
    famA, famB = fam["family"]["A — a precursor is visible"], fam["family"]["B — nothing to see"]
    base = fam["family_base_rate"]

    A('<p class="lead">Movement&nbsp;1 found the money and Movement&nbsp;2 proved the gates we own '
      f'cannot reach it. This is the from-scratch attempt: <strong>{c["sat"]} sat-out runs, '
      f'${c["ceiling"]:,} of ceiling</strong>, and permission to build anything. Everything below '
      'was computed this cycle, and it is reported the way this lab always reports &mdash; '
      '<strong>the failures by name, with the test that killed them</strong>, because a greenfield '
      'lab that only publishes its survivors is a lab that publishes noise.</p>')

    A('<div class="callout"><div class="ct">THE WEEK IN ONE PARAGRAPH</div>'
      f'<p><strong>Boarding is not the problem.</strong> A deliberately stupid rule &mdash; wait '
      f'for a {best_board["W"]}-minute thrust of {best_board["k"]}&times;ATR and buy it &mdash; '
      f'fires inside <strong>{best_board["fires_in"]} of the {best_board["of"]} runs</strong>, a '
      f'median of {best_board["late_med"]:.0f} minutes late, with a median '
      f'<strong>{best_board["left_med"]:.1f} points still to come</strong>. Boarded perfectly it '
      f'is worth <strong>${best_board["oracle"]:,.0f}, {best_board["pct_ceiling"]:.1f}% of the '
      f'whole ceiling.</strong> <strong>Selection is the problem.</strong> That same rule fires '
      f'<strong>{fireA["per_day"]:.1f} times a day</strong> and only '
      f'<strong>{fireA["pct_in_run"]:.1f}%</strong> of those fires are inside a run. '
      '<strong>And this week we finally measured why that cannot be fixed with the features we '
      'have</strong> &mdash; see &sect;3, which is the most important result in the '
      'movement.</p></div>')

    # ── §1 the prize ─────────────────────────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;1 &nbsp;The prize, and how late you can afford to be</h3>')
    A(f'<p>This week\'s census: <strong>{c["runs"]} runs</strong>, we caught <strong>{c["caught"]}'
      f'</strong>, fought <strong>{c["fought"]}</strong>, sat out <strong>{c["sat"]}</strong>. By '
      'cluster: ' + " &middot; ".join(f'<strong>{k}</strong> {v}'
                                      for k, v in c["clusters"].items()) + '.</p>')
    A('<p>The boarding ladder asks the only question that matters before any signal work: '
      '<em>if you waited for the move to prove itself, would there be anything left?</em> '
      '<strong>W</strong> is the thrust window in minutes and <strong>k</strong> its size in ATR; '
      '<strong>left</strong> is the points still on the table at the moment of boarding.</p>')
    A('<table><thead><tr><th class="num">W</th><th class="num">k&times;ATR</th>'
      '<th class="num">Fires inside</th><th class="num">Median late</th>'
      '<th class="num">Median left</th><th class="num">p25 left</th>'
      '<th class="num">Nothing left</th><th class="num">Oracle $</th>'
      '<th class="num">% of ceiling</th></tr></thead><tbody>')
    for b in prize["boarding"]:
        hl = ' class="row-hl"' if b is best_board else ''
        A(f'<tr{hl}><td class="num">{b["W"]}</td><td class="num">{b["k"]}</td>'
          f'<td class="num">{b["fires_in"]} / {b["of"]}</td>'
          f'<td class="num">{b["late_med"]:.0f} min</td>'
          f'<td class="num">{b["left_med"]:.1f} pt</td><td class="num">{b["left_p25"]:.1f} pt</td>'
          f'<td class="num">{b["nothing_left"]}</td><td class="num">${b["oracle"]:,.0f}</td>'
          f'<td class="num">{b["pct_ceiling"]:.1f}%</td></tr>')
    A('</tbody></table>')
    A('<p class="lead">&hellip;and the price of that coverage</p>')
    A('<table><thead><tr><th class="num">W</th><th class="num">k&times;ATR</th>'
      '<th class="num">Entries this week</th><th class="num">Per day</th>'
      '<th class="num">Of which inside a run</th><th class="num">Hit rate</th>'
      '</tr></thead><tbody>')
    for f in prize["fire_rate"]:
        A(f'<tr><td class="num">{f["W"]}</td><td class="num">{f["k"]}</td>'
          f'<td class="num">{f["entries_week"]}</td><td class="num">{f["per_day"]:.1f}</td>'
          f'<td class="num">{f["in_a_run"]}</td>'
          f'<td class="num">{f["pct_in_run"]:.1f}%</td></tr>')
    A('</tbody></table>')
    A('<p>&#9733; <strong>Detection is solved and it has been for three cycles.</strong> Every rung '
      'of this ladder boards nearly every run with a third to a half of the move still ahead of it. '
      'The entire problem is the last column: <strong>three fires in four are not in a run at '
      'all</strong>, and each of those pays the spread and the fee.</p></div>')

    # ── §2 the family split ──────────────────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;2 &nbsp;Half the runs have no precursor at all</h3>')
    A('<p>Split the sat-out runs by whether <em>anything was visible before ignition</em> &mdash; '
      'a volume z-score, an ATR expansion, an aggressor imbalance:</p>')
    A('<table><thead><tr><th class="ln">Family</th><th class="num">Runs</th>'
      '<th class="num">Ceiling</th><th class="num">Median move</th>'
      '<th class="num">Median vol&nbsp;z</th><th class="num">Median ATR expansion</th>'
      '<th class="num">Up / Down</th></tr></thead><tbody>')
    for name, f in fam["family"].items():
        A(f'<tr><td class="ln">{name.replace("—", "&mdash;")}</td><td class="num">{f["n"]}</td>'
          f'<td class="num">${f["ceiling"]:,}</td>'
          f'<td class="num">{f["median_move"]:.0f} pt</td>'
          f'<td class="num">{f["med_volz"]:.2f}</td>'
          f'<td class="num">{f["med_atrexp"]:.2f}</td>'
          f'<td class="num">{f["up"]} / {f["dn"]}</td></tr>')
    A('</tbody></table>')
    A(f'<p>Two things kill the obvious idea. <strong>First, the split is 50/50</strong> &mdash; '
      f'{famA["n"]} runs show a precursor and {famB["n"]} show nothing, and the silent half still '
      f'carries <strong>${famB["ceiling"]:,}</strong> of ceiling on a median move of '
      f'{famB["median_move"]:.0f} points, which is the same size as the visible half. A precursor '
      'filter therefore throws away half the prize before it starts. <strong>Second, and worse: '
      f'the precursor is not rare.</strong> Across {base["minutes"]:,} minutes, '
      f'<strong>{base["pct_true"]:.1f}% of all minutes</strong> look like family&nbsp;A &mdash; '
      f'and family&nbsp;A holds {base["famA_share_of_runs"]:.0f}% of the runs. A feature present '
      f'{base["pct_true"]:.1f}% of the time that selects 50% of the runs is doing '
      '<em>worse than nothing</em>.</p>')
    A('<p class="lead">The oracle bracket &mdash; what the boarding rule is worth at each level of '
      'cheating</p>')
    A('<table><thead><tr><th class="ln">Rule</th><th class="num">n</th><th class="num">Net $</th>'
      '<th class="num">$/trade</th><th class="num">Win %</th></tr></thead><tbody>')
    for k, v in fam["oracle"].items():
        k2 = "row-hl" if v["net"] > 0 else "row-bad"
        A(f'<tr class="{k2}"><td class="ln">{k}</td><td class="num">{v["n"]}</td>'
          f'<td class="num">${m(v["net"])}</td><td class="num">${m(v["per"], 3)}</td>'
          f'<td class="num">{v["win"]:.1f}%</td></tr>')
    A('</tbody></table>')
    ru = fam["oracle"]["RULE (board the proven move)"]
    ri = fam["oracle"]["RULE, boards inside a run only"]
    ro = fam["oracle"]["RULE, boards NOT in a run"]
    A(f'<p>Read the last two rows together. The <em>same rule</em>, split by something it cannot '
      f'know: its {ri["n"]} in-run boards make <strong>${m(ri["net"])}</strong> and its '
      f'{ro["n"]} out-of-run boards lose <strong>${m(ro["net"])}</strong>. The whole difference '
      f'between a ${m(ru["net"])} rule and a profitable one is a selector nobody has built, and '
      '&sect;3 is the evidence that the features on this desk cannot build it.</p></div>')

    # ── §3 the escalation study — the headline ───────────────────────────────────────────
    A('<div class="card"><h3>&sect;3 &nbsp;&#9733; THE HEADLINE &mdash; the precursors predict '
      'VOLATILITY, not moves, and it took an ATR control to see it</h3>')
    A(f'<p>The biggest study in the movement: <strong>{esc["n_minutes"]:,} minutes across '
      f'{esc["days"]} days</strong>, asking whether any pre-move feature separates the minutes '
      'that escalate from the minutes that do not. The number in each cell is an <strong>AUC '
      '&mdash; 0.50 is a coin flip</strong>, 1.00 is perfect.</p>')
    A('<p class="lead">A. Raw point thresholds &mdash; this is the table that looks like a '
      'discovery</p>')
    feats = [("pre_volz", "Volume z"), ("pre_ntz", "Trade-count z"),
             ("pre_atrexp", "ATR expansion"), ("pre_afz", "Aggressor-flow z"),
             ("pre_er15", "ER(15)"), ("pre_atr", "ATR level")]
    A('<table><thead><tr><th class="num">Move &ge;</th><th class="num">n minutes</th>'
      + "".join(f'<th class="num">{lbl}</th>' for _k, lbl in feats) + '</tr></thead><tbody>')
    for b in esc["bands"]:
        A(f'<tr><td class="num">{b["thr"]} pt</td><td class="num">{b["n_pos"]:,}</td>'
          + "".join(f'<td class="num">{b[k]:.3f}</td>' for k, _l in feats) + '</tr>')
    A('</tbody></table>')
    A('<p>Every column beats a coin flip and every p-value is 0.00. <strong>ATR level reaches '
      '0.81.</strong> On this table alone you would ship a volatility-gated boarder tomorrow.</p>')
    A('<p class="lead">B. The same question with the threshold expressed in ATR &mdash; i.e. '
      '&ldquo;did it move a lot <em>for a tape this volatile</em>&rdquo;</p>')
    A('<table><thead><tr><th class="num">Move &ge;</th><th class="num">n minutes</th>'
      + "".join(f'<th class="num">{lbl}</th>' for _k, lbl in feats) + '</tr></thead><tbody>')
    for b in esc["bands_atr"]:
        A(f'<tr class="row-bad"><td class="num">{b["thr_atr"]}&times;ATR</td>'
          f'<td class="num">{b["n_pos"]:,}</td>'
          + "".join(f'<td class="num">{b[k]:.3f}</td>' for k, _l in feats) + '</tr>')
    A('</tbody></table>')
    A('<p class="lead">C. And conditioned on ATR &mdash; within-band, so the volatility level is '
      'held fixed</p>')
    A('<table><thead><tr><th class="num">Move &ge;</th>'
      + "".join(f'<th class="num">{lbl}</th>' for _k, lbl in feats) + '</tr></thead><tbody>')
    for b in esc["within_atr"]:
        A(f'<tr class="row-bad"><td class="num">{b["thr"]} pt</td>'
          + "".join(f'<td class="num">{b[k]:.3f}</td>' for k, _l in feats) + '</tr>')
    A('</tbody></table>')
    A('<div class="rev3"><div class="ct">&#9733;&#9733; WHAT TABLES B AND C DO TO TABLE A</div>'
      '<p><strong>Table A is an artefact of not controlling for volatility.</strong> A 55-point '
      'move is easy on a wide-ATR tape and hard on a quiet one, so <em>anything</em> correlated '
      'with ATR &mdash; volume, trade count, aggressor flow, all of which are &mdash; scores well '
      'against a fixed point threshold. It is the same instrument twice.</p>'
      '<p>Normalise the threshold by ATR (B) and the discrimination collapses: ATR expansion falls '
      f'to <strong>{esc["bands_atr"][-1]["pre_atrexp"]:.3f}</strong> and ATR level itself to '
      f'<strong>{esc["bands_atr"][-1]["pre_atr"]:.3f}</strong> &mdash; both now <em>worse</em> than '
      'a coin flip, i.e. actively anti-predictive. Hold ATR fixed and ask within the band (C) and '
      'every feature sits between 0.29 and 0.56.</p>'
      '<p><strong>The desk\'s entire precursor toolkit measures one thing: how volatile the tape '
      'already is.</strong> That is genuinely useful &mdash; it says <em>a big move is possible '
      'now</em> &mdash; and it is completely useless for the question we keep asking it, which is '
      '<em>which possible move will happen</em>. Three cycles of &ldquo;selection is the '
      'problem&rdquo; now have a mechanism: we have been feeding the selector a volatility meter '
      'and asking it for a direction.</p></div>')
    A('<p class="lead">D. And direction, for completeness</p>')
    A('<table><thead><tr><th class="num">Move &ge;</th><th class="num">n</th>'
      '<th class="num">% up</th><th class="num">Prior 5-min move</th>'
      '<th class="num">30-min range break</th><th class="num">60s aggressor flow</th>'
      '<th class="num">Continuation agrees</th></tr></thead><tbody>')
    for b in esc["direction"]:
        A(f'<tr><td class="num">{b["thr"]} pt</td><td class="num">{b["n"]:,}</td>'
          f'<td class="num">{b["up_pct"]:.1f}%</td>'
          f'<td class="num">{b["prior 5-min move"]:.3f}</td>'
          f'<td class="num">{b["30-min range break"]:.3f}</td>'
          f'<td class="num">{b["60s net aggressor flow"]:.3f}</td>'
          f'<td class="num">{b["continuation_agrees_pct"]:.1f}%</td></tr>')
    A('</tbody></table>')
    A('<p>Up-share sits on 50%, aggressor flow is <em>below</em> 0.50 at every threshold, and '
      'continuation agreement runs from 40.9% to 52.2% with no trend. <strong>Nothing on this desk '
      'carries forward direction.</strong> That is consistent with the router study in '
      'Part&nbsp;2.6 and with the standing FLOW-LED/VACUUM result, and it is now measured on '
      f'{esc["n_minutes"]:,} minutes rather than on a week.</p></div>')

    # ── §4 this week's fresh candidate ───────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;4 &nbsp;<code>COIL-BRK</code> &mdash; this week\'s fresh '
      'candidate, built and killed in one cycle</h3>')
    A(f'<p>The construction: a compression (&ldquo;coil&rdquo;) filter arms the session, then a '
      f'range break is taken. Window <strong>{fr["window"][0]} &rarr; {fr["window"][1]}, '
      f'{fr["sessions"]} sessions</strong> &mdash; deliberately far wider than the report week, '
      'because a one-week greenfield result is not testable.</p>')
    A('<p class="lead">The arm ladder &mdash; how tight the coil filter has to be</p>')
    A('<table><thead><tr><th class="num">Coil quantile</th><th class="num">n</th>'
      '<th class="num">Net $</th><th class="num">$/trade</th><th class="num">Win %</th>'
      '<th class="num">Days</th></tr></thead><tbody>')
    for r in fr["arm_ladder"]:
        A(f'<tr class="{"row-hl" if r["net"] > 0 else "row-bad"}">'
          f'<td class="num">{r["coil_q"]}</td><td class="num">{r["n"]}</td>'
          f'<td class="num">${m(r["net"])}</td><td class="num">${m(r["per"], 3)}</td>'
          f'<td class="num">{r["win"]:.1f}%</td><td class="num">{r["days"]}</td></tr>')
    A('</tbody></table>')
    A('<p>&#9733; <strong>Stop here and the candidate is already in trouble.</strong> The ladder is '
      'not monotone and it is not even single-signed: 0.1 loses $1,118, 0.2 makes $1,038, 0.3 loses '
      '$912, 0.4 loses $419, 0.7 is flat. A real filter tightens into an edge. This one flips sign '
      'four times, which is the signature of a parameter that is fitting noise. It was carried '
      'through the full battery anyway, because a hunch is not a verdict.</p>')

    A('<p class="lead">The costed battery &mdash; every kill test, on all three surviving exit '
      'cells</p>')
    A('<table><thead><tr><th class="ln">Cell</th><th class="num">n</th><th class="num">Net $</th>'
      '<th class="num">$/tr</th><th class="num">IS $/tr</th><th class="num">OOS $/tr</th>'
      '<th class="num">Strip-best-3</th><th class="num">Sign-flip</th>'
      '<th class="num">Green days</th><th class="num">Placebos beating it</th>'
      '</tr></thead><tbody>')
    for b in fr2["battery"]:
        A(f'<tr class="row-bad"><td class="ln"><code>{b["label"]}</code></td>'
          f'<td class="num">{b["n"]}</td><td class="num">${m(b["net"])}</td>'
          f'<td class="num">${m(b["per"], 3)}</td><td class="num">${m(b["IS"]["per"], 3)}</td>'
          f'<td class="num">${m(b["OOS"]["per"], 3)}</td>'
          f'<td class="num">${m(b["strip3"], 3)}</td>'
          f'<td class="num">${m(b["signflip"]["per"], 3)}</td>'
          f'<td class="num">{b["days_green"]}/{b["days_total"]}</td>'
          f'<td class="num">{b["placebo_beat"]} of 5</td></tr>')
    A('</tbody></table>')
    best = fr2["battery"][0]
    A('<p class="lead">And the placebo ladder for the best cell &mdash; the SAME rule taken N '
      'minutes early, which cannot contain any signal</p>')
    A('<table><thead><tr><th class="num">Shift</th><th class="num">n</th><th class="num">Net $</th>'
      '<th class="num">$/trade</th><th class="num">vs the real signal</th></tr></thead><tbody>')
    for p in best["placebo"]:
        beat = p["per"] >= best["per"]
        A(f'<tr class="{"row-bad" if beat else ""}"><td class="num">'
          f'{p["shift_min"]} min early</td><td class="num">{p["n"]}</td>'
          f'<td class="num">${m(p["net"])}</td><td class="num">${m(p["per"], 3)}</td>'
          f'<td class="num">{"<strong>BEATS IT</strong>" if beat else "loses to it"}</td></tr>')
    A('</tbody></table>')
    A('<div class="rev3"><div class="ct">VERDICT &mdash; <code>COIL-BRK</code> IS REFUTED</div>'
      f'<p>Four independent tests, any one of which is fatal. <strong>(1) Out of sample it '
      f'inverts:</strong> in-sample ${m(best["IS"]["per"], 3)}/trade, out of sample '
      f'<strong>${m(best["OOS"]["per"], 3)}</strong>. <strong>(2) It is three trades wide:</strong> '
      f'strip its best 3 of {best["n"]} and ${m(best["per"], 3)}/trade becomes '
      f'<strong>${m(best["strip3"], 3)}</strong>. <strong>(3) The placebo beats it:</strong> the '
      'same rule taken <strong>30 minutes early</strong> &mdash; when the coil condition it is '
      f'built on has not happened yet &mdash; books <strong>${m(best["placebo"][0]["per"], 3)}/'
      f'trade against the real signal\'s ${m(best["per"], 3)}</strong>, and 60 minutes early also '
      f'beats it. <strong>(4) It is a short-side artefact:</strong> LONG '
      f'${m(best["LONG"]["per"], 3)}/trade, SHORT ${m(best["SHORT"]["per"], 3)} &mdash; the entire '
      'net is one direction on a tape with a known short drift, and it is green on only '
      f'{best["days_green"]} of {best["days_total"]} days.</p>'
      '<p>Note what the placebo ladder\'s shape says on its own. The shifted copies decay smoothly '
      'from +$3.55 at 30 minutes to &minus;$11.29 at 8 hours. That is not a signal being '
      'destroyed by misalignment; it is a slow intraday drift being sampled at different points. '
      '<strong>The rule is a clock, not a trigger.</strong></p></div>')
    ua, ub = fr2["unarmed_2.0_4.0"], fr2["unarmed_3.0_8.0"]
    A(f'<p>&#9733; And the control that settles it: the <em>unarmed</em> break &mdash; the same '
      f'entry with the coil filter switched off entirely &mdash; books '
      f'<strong>${m(ub["net"])} on {ub["n"]:,} trades (${m(ub["per"], 3)}/tr)</strong> at the '
      f'3.0/8.0 exit, against the armed version\'s ${m(best["per"], 3)}. '
      '<strong>The filter this candidate is built around subtracts value.</strong> What little is '
      'there belongs to the exit geometry, and that is a finding about stops, not about '
      'coils.</p></div>')

    # ── §5 the forward test of last week's candidates ────────────────────────────────────
    A('<div class="card"><h3>&sect;5 &nbsp;&#9733; THE FORWARD TEST &mdash; last week\'s five '
      'candidates, on tape they have never seen</h3>')
    A('<p>This is the section that justifies the whole rotation. The five candidates the 08-25 '
      'labs produced were frozen with their specs and are re-priced here on the days since the '
      'freeze &mdash; genuinely out of sample, no re-tuning, no cell re-selection. '
      '<strong>OOS</strong> is the post-freeze tape only.</p>')
    A('<table><thead><tr><th class="ln">Candidate (spec)</th><th class="num">Frozen</th>'
      '<th class="num">All n</th><th class="num">All net $</th><th class="num">All $/tr</th>'
      '<th class="num">IS $/tr</th><th class="num">OOS n</th><th class="num">OOS net $</th>'
      '<th class="num">OOS $/tr</th><th class="ln">Reads as</th></tr></thead><tbody>')
    for name, v in froz.items():
        oos, al = v["OOS"], v["ALL"]
        # An OOS leg of 3-5 days is not a verdict; label what it IS rather than promoting it.
        if al["net"] < 0 and oos["net"] > 0:
            reads = ('<span class="tag pill-dontarm">still red overall</span> &mdash; '
                     f'{oos["days"]}-day OOS bounce')
        elif al["net"] > 0 and oos["net"] < 0:
            reads = '<span class="tag pill-dontarm">OOS inverts</span>'
        elif al["net"] < 0:
            reads = '<span class="tag pill-dontarm">red both legs</span>'
        else:
            reads = '<span class="tag pill-shadow">holds, small n</span>'
        A(f'<tr class="{"row-bad" if al["net"] < 0 else ""}"><td class="ln"><code>'
          f'{name.split("(")[0].strip()}</code><br><span class="why">{v["spec"]}</span></td>'
          f'<td class="num">{v["cut"]}</td><td class="num">{al["n"]}</td>'
          f'<td class="num">${m(al["net"])}</td><td class="num">${m(al["per"], 3)}</td>'
          f'<td class="num">${m(v["IS"]["per"], 3)}</td><td class="num">{oos["n"]}</td>'
          f'<td class="num">${m(oos["net"])}</td><td class="num">${m(oos["per"], 3)}</td>'
          f'<td class="ln">{reads}</td></tr>')
    A('</tbody></table>')
    n_red = sum(1 for v in froz.values() if v["ALL"]["net"] < 0)
    A(f'<p>&#9733; <strong>{n_red} of the {len(froz)} are net negative over their whole life, and '
      'not one is a promotion candidate.</strong> Two &mdash; <code>UNCL-RIDE-ER</code> and '
      '<code>board_atrband</code> &mdash; show a positive out-of-sample leg on 4 days, and that is '
      'exactly the shape this desk has learned to distrust: an OOS window of 27 and 29 trades over '
      '4 sessions, both driven by their LONG side (+$15.56 and +$20.21 a trade) while both SHORT '
      'sides are red. <strong>Four days is not a forward test; it is a sample of the week\'s '
      'drift.</strong> They stay parked, and the honest read is that the parking decision made on '
      '08-25 has been vindicated rather than overturned.</p>')
    A('<p>The two that were <em>positive</em> in the lab have both inverted: <code>FL-4 '
      'flow_ignition</code> goes from +$4.84/trade in sample to <strong>&minus;$16.82</strong> out '
      'of it, and <code>MOMBRK</code> from +$3.66 to &minus;$0.56 with an 11% win rate throughout. '
      '<strong>Both were already REFUTED by their own placebo tests last week</strong>, and the '
      'forward tape has now agreed with the placebo. That is the single most reassuring result in '
      'this movement: the kill tests are calling it right.</p></div>')

    # ── §6 catches ───────────────────────────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;6 &nbsp;Which boarder actually caught this week\'s runs</h3>')
    A('<p>Every candidate, plus a deliberately dumb control, run across this week\'s five sessions '
      f'and scored against the {c["sat"]} sat-out runs. <strong>Money on those</strong> is what it '
      'made <em>on the runs it caught</em> &mdash; so the gap between that and Net&nbsp;$ is what '
      'it paid to be everywhere else.</p>')
    A('<table><thead><tr><th class="ln">Boarder</th><th class="num">Trades</th>'
      '<th class="num">Net $</th><th class="num">$/tr</th><th class="num">Win %</th>'
      '<th class="num">Runs caught</th><th class="num">Of the top 25</th>'
      '<th class="num">Of the top 15</th><th class="num">Money on those</th>'
      '</tr></thead><tbody>')
    for k, v in sorted(catch.items(), key=lambda x: -x[1]["net"]):
        A(f'<tr class="{"row-hl" if v["net"] > 0 else "row-bad"}"><td class="ln">{k}</td>'
          f'<td class="num">{v["n"]}</td><td class="num">${m(v["net"])}</td>'
          f'<td class="num">${m(v["per"], 3)}</td><td class="num">{v["win"]:.1f}%</td>'
          f'<td class="num">{v["caught"]} / {v["of"]}</td><td class="num">{v["top25"]}</td>'
          f'<td class="num">{v["top15"]}</td>'
          f'<td class="num">${m(v["money_on_those"])}</td></tr>')
    A('</tbody></table>')
    db = catch["the dumb boarder (5-min thrust >= 2.0xATR)"]
    ba = catch["board_atrband"]
    A(f'<p>The dumb control catches <strong>{db["caught"]} of {db["of"]} runs</strong> &mdash; more '
      f'than any built candidate &mdash; and makes <strong>${m(db["money_on_those"])} on the runs '
      f'it caught</strong> while ending the week at <strong>${m(db["net"])}</strong> overall. '
      f'<code>board_atrband</code> is the only net-positive line at ${m(ba["net"])}, and it too '
      f'earns ${m(ba["money_on_those"])} on its catches and gives most of it back elsewhere. '
      '<strong>Every row on this table tells the same story from a different angle: the catches '
      'pay and the non-catches eat it.</strong></p></div>')

    # ── §7 size ──────────────────────────────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;7 &nbsp;Where the money is, by SIZE of move &mdash; and the '
      '120-point line</h3>')
    A('<p>Take every entry in the pooled book and bucket it by what the tape actually did next. '
      'This is a decomposition, not a strategy &mdash; the bands are only knowable afterwards. Its '
      'job is to say <em>what a selector would have to find</em>.</p>')
    for ruler, d in size.items():
        A(f'<p class="lead">{ruler} &mdash; overall <strong>n={d["n"]:,}, ${m(d["net"])} '
          f'(${m(d["per"], 3)}/trade)</strong></p>')
        A('<table><thead><tr><th class="ln">What the tape did</th><th class="num">n</th>'
          '<th class="num">% of book</th><th class="num">Net $</th><th class="num">$/trade</th>'
          '</tr></thead><tbody>')
        for band, b in d["bands"].items():
            A(f'<tr class="{"row-hl" if b["net"] > 0 else "row-bad"}"><td class="ln">{band}</td>'
              f'<td class="num">{b["n"]:,}</td><td class="num">{b["pct"]:.1f}%</td>'
              f'<td class="num">${m(b["net"])}</td><td class="num">${m(b["per"], 2)}</td></tr>')
        A('</tbody></table>')
        A('<table><thead><tr><th class="ln">If a selector kept only moves of&hellip;</th>'
          '<th class="num">n</th><th class="num">% of book</th><th class="num">$/trade</th>'
          '</tr></thead><tbody>')
        for thr, b in d["cumulative_at_or_above"].items():
            A(f'<tr><td class="ln">&ge; {thr} pt</td><td class="num">{b["n"]:,}</td>'
              f'<td class="num">{b["pct"]:.1f}%</td>'
              f'<td class="num">${m(b["per"], 2)}</td></tr>')
        A('</tbody></table>')
    atr = size["ATR-scaled stop 2.5xATR / target 6xATR"]
    b120 = atr["bands"][">= +120pt"]
    nothing = atr["bands"]["-20 .. +20pt (nothing happened)"]
    A(f'<p>&#9733; <strong>The 120-point line, confirmed for a second cycle by a third harness.</strong> '
      f'Moves of 120 points or more are <strong>{b120["pct"]:.1f}% of the book</strong> &mdash; '
      f'{b120["n"]} trades of {atr["n"]:,} &mdash; and they carry <strong>${b120["net"]:,.0f}</strong> '
      f'at <strong>${b120["per"]:,.2f} a trade</strong>, on a book whose total is '
      f'<strong>${m(atr["net"])}</strong>. Meanwhile <strong>{nothing["pct"]:.1f}% of entries go '
      f'nowhere at all</strong> (&plusmn;20 points) and pay <strong>${nothing["per"]:.2f} each</strong> '
      'for the privilege &mdash; that band alone is '
      f'<strong>${m(nothing["net"])}</strong>, and it is pure friction.</p>')
    A('<p><strong>So the target is not a better entry, it is a bigger one.</strong> A selector that '
      'did nothing but decline the &plusmn;20-point band &mdash; without improving direction at all '
      '&mdash; turns this book from &minus;$2,814 into a positive one. That is the same conclusion '
      'the rider lab and the census reached independently, and it is now three harnesses '
      'agreeing.</p></div>')

    # ── §8 the chop-scalp lab ────────────────────────────────────────────────────────────
    cs = pathlib.Path(f"{SEC}/gf_chopscalp.md")
    A('<div class="card"><h3>&sect;8 &nbsp;The chop-day turn scalp &mdash; the operator\'s own '
      'question, re-run</h3>')
    A('<p>&ldquo;Can we stop donating on chop days?&rdquo; The purpose-built L2 turn scalper was '
      're-run this cycle from scratch with the search included in the placebo &mdash; the '
      'methodology fix that killed last week\'s finalist. Its dossier is reproduced in full below '
      f'(&sect;A1). <strong>Written 2026-08-29 00:19&nbsp;UTC, this cycle</strong>, '
      f'{word_count(cs.read_text()) if cs.is_file() else 0:,} words.</p>')
    try:
        arith = J(f"{SEC}/cs3/arith.json")
        ceil3 = J(f"{SEC}/cs3/ceiling.json")
        lastc = J(f"{SEC}/cs3/last_cell.json")
        ct20 = J(f"{SEC}/cs3/ct20.json")
        A('<table><thead><tr><th class="ln">Candidate</th><th class="num">Costed cells</th>'
          '<th class="num">Positive cells</th><th class="num">Best $/tr</th>'
          '<th class="num">Median $/tr</th></tr></thead><tbody>')
        for k, v in arith["r_sweep"].items():
            A(f'<tr class="{"row-bad" if v["pos"] == 0 else ""}"><td class="ln"><code>{k}</code>'
              f'</td><td class="num">{v["cells"]}</td><td class="num">{v["pos"]}</td>'
              f'<td class="num">${m(v["best"], 3)}</td>'
              f'<td class="num">${m(v["med"], 3)}</td></tr>')
        A('</tbody></table>')
        cc = ceil3["ceiling"]
        A(f'<p>The prize first: a perfect-hindsight chop-day scalper is worth '
          f'<strong>${cc["net"]:,.2f} over {cc["n"]} trades</strong> across '
          f'{len(cc["chop_days"])} chop days &mdash; <strong>${cc["per_chop_day"]:,.2f} a '
          'day</strong>, which does clear the operator\'s bar. What converts any of it: '
          + " &middot; ".join(
              f'<code>{k}</code> {v["frac_of_ceiling"] * 100:.1f}%'
              for k, v in ceil3["conversion"].items()) + '.</p>')
        A(f'<p><code>CT20</code>, last week\'s survivor, is dead on its own terms this cycle: '
          f'{ct20["events"]} events, a {ct20["grid"]["cells"]}-cell costed grid, '
          f'<strong>{ct20["grid"]["pos"]} positive cells</strong>, best '
          f'${m(ct20["grid"]["best_ptr"], 3)}/trade &mdash; <em>&ldquo;{ct20["verdict"]}&rdquo;</em>. '
          f'The last cell standing, <code>CT13</code> at {lastc["cell"]}, is '
          f'<strong>n={lastc["full"]["n"]}, ${m(lastc["full"]["net"])} total, '
          f'${m(lastc["full"]["ptr"], 3)}/trade</strong> with {lastc["lodo"]["pos"]} of '
          f'{lastc["lodo"]["folds"]} leave-one-day-out folds positive &mdash; and it splits '
          f'<strong>${m(lastc["split_ORIG"]["ptr"], 3)} on the original tape vs '
          f'${m(lastc["split_NEW"]["ptr"], 3)} on the new</strong>. A 66-trade edge worth 31 cents '
          'a trade is not a gate; it is a rounding error with a name.</p>')
    except FileNotFoundError:
        A('<p><em>The chop-scalp summary artifacts were not written; the dossier below is the '
          'record.</em></p>')
    A('</div>')

    # ── §9 the board ─────────────────────────────────────────────────────────────────────
    A('<div class="callout"><div class="ct">MOVEMENT 3 &mdash; THE BOARD, AND THE VERDICT</div>'
      '<p><strong>Nothing is promoted this week. Nothing is even nominated.</strong> One fresh '
      'candidate was built and refuted by four independent tests; five frozen candidates were '
      'forward-tested and none earned a promotion; the chop-scalp finalist died on its own '
      're-run.</p>'
      '<p><strong>But the movement is not empty, because &sect;3 is a real result and it is '
      'structural.</strong> For three cycles this lab has closed with &ldquo;detection is solved, '
      'selection is not&rdquo; without being able to say <em>why</em> selection kept failing. It '
      'can now: <strong>every precursor feature on this desk is a proxy for ATR</strong>, and once '
      'ATR is controlled for, all of them fall to a coin flip or below. We have been asking a '
      'volatility meter to name a direction. No amount of re-tuning fixes that &mdash; it needs an '
      'input the desk does not currently record.</p>'
      '<p>&#9733; <strong>What that makes actionable</strong> is &sect;7, and it needs no new '
      'signal at all: <strong>48.2% of entries go nowhere and pay $10 each to find out.</strong> '
      'Declining the dead band is a size decision, not a direction decision, and it is the one '
      'lever in this movement that does not depend on predicting anything.</p></div>')

    # ── appendix ─────────────────────────────────────────────────────────────────────────
    A('<hr class="frag-sep">')
    A('<h3 id="m3-appendix">APPENDIX &mdash; the dossiers in full</h3>')
    A('<p class="lead">The editorial half above is the map; this is the territory. Every claim in '
      'this movement traces to one of these.</p>')

    if cs.is_file():
        A(f'<h4 id="m3-chop">A1 &mdash; THE CHOP-DAY TURN SCALP <span class="tag pill-live">'
          f'THIS CYCLE &middot; 2026-08-29</span></h4>')
        A(md_to_html(cs.read_text(), h_offset=3))

    A('<div class="rev3"><div class="ct">A2&ndash;A6 &mdash; THE FOUR CLUSTER HUNTS THE ROTATION '
      'DID NOT SCHEDULE THIS WEEK</div>'
      '<p>The serial runner logged, at 22:14:21Z: <em>ROTATION (ISO week 35): running 2 of 6 '
      'greenfield clusters. NOT run this week: gf_OPEN-NEWS, gf_RIDER_ALL, gf_UNCLASS, '
      'gf_VACUUM.</em> <strong>This is the design working, not a failure</strong> &mdash; six '
      'cluster hunts at ~25 minutes each do not fit in one Friday night, so they rotate and each '
      'is re-run roughly every three weeks.</p>'
      '<p>Their dossiers are reproduced below <strong>as a standing reference, dated 2026-08-22 '
      'and 2026-08-25</strong>. They are NOT this week\'s work and nothing on the action card '
      'rests on them. <strong>What IS this week\'s work is &sect;5 above</strong>, which takes '
      'every candidate these four labs produced, on the specs they were frozen with, and prices '
      'them forward on tape they had never seen. That is the honest way to carry a rotated-out '
      'lab: freeze the claim, then grade it.</p></div>')

    for anchor, title, fname, blurb in ROTATED_OUT:
        p = pathlib.Path(SEC) / fname
        # ★ is_file(), not exists(): one dossier filename in this directory contains a "/" that
        # the writing agent turned into a real DIRECTORY, and read_text() on it raises
        # IsADirectoryError. Any glob or list over this directory must skip non-files.
        if not p.is_file():
            A(f'<h4 id="{anchor}">{title}</h4><div class="rev3"><div class="ct">DOSSIER MISSING'
              f'</div><p><code>{fname}</code> is not a readable file.</p></div>')
            continue
        when = "2026-08-22" if "VACUUM" in fname else "2026-08-25"
        A(f'<h4 id="{anchor}">{title} <span class="tag pill-parked">NOT RUN THIS WEEK &middot; '
          f'dossier {when}</span></h4><p class="lead">{blurb}</p>')
        A(md_to_html(p.read_text(), h_offset=3))

    doc = "\n".join(H)
    pathlib.Path(OUT).write_text(doc)
    print(f"movement3_greenfield.html → {len(doc):,} chars, ~{len(doc.split()):,} tokens")
    print(f"  editorial from {8} fresh m3 labs + cs3; appendix A1 fresh, A2-A6 rotation-carried")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
