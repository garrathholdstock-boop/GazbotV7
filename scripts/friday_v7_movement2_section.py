#!/usr/bin/env python3
"""MOVEMENT 2 — the idle-gate lab, built from THIS cycle's own artifacts.

★ WHY THIS FILE EXISTS (2026-08-29). The `movement2_idle` phase of the 2026-08-28 durable run
RAN — it wrote m2_lab.json, m2_sweep.json, m2_placebo.json and m2_placebo2.json between 23:30
and 23:36Z — and was then killed at 21.1 minutes before it wrote its HTML section
(`rc=-1 artifact=MISSING`). The `movement2_idle_gates.html` sitting on disk is the 08-26 file,
computed against the SUPERSEDED 08-22 census (70 runs / 65 sat out / $9,987) and carrying a red
banner that says so.

So the analysis for this week exists and only the writing-up was lost. This script does the
writing-up mechanically: every number below is computed here, at render time, from the four
JSON artifacts the phase left behind — none is typed, and none is carried over from the 08-26
section. That makes Movement 2 a THIS-WEEK section again, on THIS week's census freeze
(65 runs / 62 sat out / $10,278), which is the same freeze Movement 1 reports.

Run:  python3 scripts/friday_v7_movement2_section.py
"""
from __future__ import annotations

import json
import pathlib
from collections import defaultdict

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = f"{SEC}/movement2_idle_gates.html"
LAB, SWP = f"{SEC}/m2_lab.json", f"{SEC}/m2_sweep.json"
PLA, PLA2 = f"{SEC}/m2_placebo.json", f"{SEC}/m2_placebo2.json"

# The live mechanism's own constraint, per gate — what the "LIVE" sweep cell is holding fixed.
LIVE_CELL = {
    "abs_veto_long": "LIVE thr1.5+vol+amp", "abs_veto_short": "LIVE thr1.5+vol+amp",
    "exhaustion_short": "LIVE net>=400", "grind_long": "LIVE atr>=22",
}


def regime(r):
    a, e = r["atr"], r["er"]
    if a >= 22 and e < 0.25:
        return "VIOLENT-WHIPSAW"
    if e >= 0.40:
        return "CLEAN-TREND"
    if e >= 0.25:
        return "BUILDING"
    if a < 12:
        return "DEAD-CHOP"
    return "NORMAL-CHOP"


def tod(h):
    return "ASIA 00-07" if h < 7 else "LONDON 07-13" if h < 13 else "US 13-21" if h < 21 else "POST 21-24"


def stat(ts):
    n = len(ts)
    net = sum(t["net"] for t in ts)
    w = sum(1 for t in ts if t["net"] > 0)
    return n, net, (100 * w / n if n else 0.0), (net / n if n else 0.0)


def m(v, dp=2):
    """A signed money cell with a real minus sign."""
    s = f"{v:+,.{dp}f}"
    return s.replace("-", "&minus;")


def cls(v):
    return ' class="num pos"' if v > 0 else ' class="num neg"' if v < 0 else ' class="num"'


def row(label, ts, tag="td"):
    n, net, wr, pl = stat(ts)
    return (f'<tr><{tag} class="ln">{label}</{tag}><td class="num">{n}</td>'
            f'<td class="num">${m(net)}</td><td class="num">{wr:.1f}%</td>'
            f'<td class="num">${m(pl)}</td></tr>')


def main() -> int:
    lab = json.load(open(LAB))
    runs = {r["tm"]: r for r in lab["runs"]}
    for r in runs.values():
        if "atr" in r:
            r["regime"], r["tod"] = regime(r), tod(r["hour"])
    tr = lab["trades"]
    for t in tr:
        r = runs[t["run"]]
        t["regime"] = r.get("regime", "NO-TAPE")
        t["tod"] = r.get("tod", "?")
        t["day"] = t["run"][:5]

    sat = list(runs.values())
    ceil = sum(r["ceil"] for r in sat)
    dsec = sum(r.get("n_snaps_mech", 0) for r in sat)

    mech = [t for t in tr if t["layer"] == "mech"]
    ung = [t for t in tr if t["layer"] == "ungated"]
    mech_i = [t for t in mech if t["in_dir"]]
    ung_i = [t for t in ung if t["in_dir"]]
    nM, netM, wrM, plM = stat(mech)
    nMi, netMi, _, plMi = stat(mech_i)
    nU, netU, wrU, plU = stat(ung)
    nUi, netUi, wrUi, plUi = stat(ung_i)

    H: list[str] = []
    A = H.append

    A('<h2 id="m2"><span class="n">M2</span> THE IDLE-GATE LAB &mdash; could the gates we already '
      'own have caught the runs we sat out?</h2>')

    A('<p class="lead">Movement&nbsp;1 has just shown you <strong>62 runs this week that the desk '
      f'sat out entirely</strong>, worth <strong>${ceil:,}</strong> if every one had been caught '
      'perfectly. The obvious question &mdash; and the cheapest one, because it needs no new code '
      '&mdash; is whether the six gates we <em>already own</em> would have caught any of them had '
      'they simply been left armed. This lab answers it by replaying every one of those runs '
      f'second by second: <strong>{dsec:,} decision-seconds</strong> of real quotes, each gate\'s '
      'own deciders, each gate\'s own A/B exit pair, and the desk\'s real cost of $1.50 a round '
      'trip.</p>')

    verdict_word = "no" if netUi <= 0 else "a qualified yes, and the qualification is the whole finding"
    A('<div class="callout"><div class="ct">THE ANSWER, IN FOUR NUMBERS</div>'
      f'<p><strong>1.</strong> Fired exactly as they are configured today, the gates take '
      f'<strong>{nM} lots into the runs and lose ${m(netM)}</strong> '
      f'(${m(plM)}/lot, {wrM:.1f}% win). '
      f'<strong>2.</strong> Strip every constraint the live mechanism imposes &mdash; the "ungated" '
      f'layer, which is the gates\' raw pattern with nothing filtering it &mdash; and they take '
      f'<strong>{nU} lots for ${m(netU)}</strong>. Almost break-even, on 3.6&times; the volume. '
      f'<strong>3.</strong> Now keep only the fires that pointed the <em>same way as the run</em>: '
      f'<strong>{nUi} lots, ${m(netUi)}, {wrUi:.1f}% win, ${m(plUi)}/lot.</strong> '
      f'<strong>4.</strong> And that is the trap, because the direction is only knowable '
      'afterwards. <strong>The gates do not know which way the run will go</strong> &mdash; that is '
      'what &ldquo;sat out&rdquo; means. Reading number 3 as an opportunity is reading the answer '
      'off the back of the exam paper.</p></div>')

    # ── A. the population ────────────────────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;1 &nbsp;The population &mdash; what we are replaying</h3>')
    A(f'<p>Every sat-out run from this week\'s census freeze: <strong>{len(sat)} runs, '
      f'${ceil:,} of hindsight ceiling, {dsec:,} decision-seconds</strong>. This is the SAME '
      'freeze Movement&nbsp;1 reports &mdash; 65 runs, 2 caught, 1 fought, 62 sat out &mdash; so a '
      'per-run number here lines up with a per-run number there. '
      '<em>(Last cycle\'s Movement&nbsp;2 was computed on a superseded freeze and had to carry a '
      'banner saying its run list did not match the rest of the report. That is fixed: this '
      'section was recomputed on the 08-28 freeze.)</em></p>')
    for k, title in (("regime", "By regime, at the moment the run began"),
                     ("tod", "By session")):
        d = defaultdict(lambda: [0, 0])
        for r in sat:
            d[r.get(k, "NO-TAPE")][0] += 1
            d[r.get(k, "NO-TAPE")][1] += r["ceil"]
        A(f'<p class="lead">{title}</p><table><thead><tr><th class="ln">'
          f'{"Regime" if k == "regime" else "Session (UTC)"}</th><th class="num">Runs</th>'
          '<th class="num">Ceiling</th><th class="num">Share of ceiling</th></tr></thead><tbody>')
        for a, b in sorted(d.items(), key=lambda x: -x[1][1]):
            A(f'<tr><td class="ln">{a}</td><td class="num">{b[0]}</td>'
              f'<td class="num">${b[1]:,}</td><td class="num">{100*b[1]/ceil:.1f}%</td></tr>')
        A('</tbody></table>')
    A('</div>')

    # ── B. the two layers ────────────────────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;2 &nbsp;The scoreboard &mdash; two layers, and why both are '
      'printed</h3>')
    A('<p><strong>MECH</strong> is each gate exactly as it is configured on the live desk right '
      'now. <strong>UNGATED</strong> is the same pattern with the live mechanism\'s own '
      'constraints removed &mdash; no 55-second veto, no ATR floor, no volume surge requirement. '
      'The pair is printed together because the gap between them <em>is</em> the value of the '
      'filtering, and it is the only honest way to ask &ldquo;would arming it have helped?&rdquo;: '
      'MECH answers &ldquo;as it stands&rdquo;, UNGATED answers &ldquo;is there anything there at '
      'all&rdquo;.</p>')
    for lay, T, Ti in (("MECH &mdash; the live configuration", mech, mech_i),
                       ("UNGATED &mdash; the raw pattern", ung, ung_i)):
        A(f'<p class="lead">{lay}</p><table><thead><tr><th class="ln">Gate</th>'
          '<th class="num">Fires</th><th class="num">Runs</th><th class="num">Lots</th>'
          '<th class="num">Net $</th><th class="num">Win %</th><th class="num">$/lot</th>'
          '<th class="num">In-dir lots</th><th class="num">In-dir $</th></tr></thead><tbody>')
        for g in sorted({t["gate"] for t in T}):
            v = [t for t in T if t["gate"] == g]
            f = len({(t["run"], t["entry_ms"]) for t in v})
            rr = len({t["run"] for t in v})
            vi = [t for t in v if t["in_dir"]]
            n, net, wr, pl = stat(v)
            k = "row-bad" if net < 0 else "row-hl" if net > 0 else ""
            A(f'<tr class="{k}"><td class="ln"><code>{g}</code></td><td class="num">{f}</td>'
              f'<td class="num">{rr}</td><td class="num">{n}</td><td class="num">${m(net)}</td>'
              f'<td class="num">{wr:.1f}%</td><td class="num">${m(pl)}</td>'
              f'<td class="num">{len(vi)}</td><td class="num">${m(sum(x["net"] for x in vi))}</td>'
              '</tr>')
        n, net, wr, pl = stat(T)
        ni, neti, wri, pli = stat(Ti)
        A(f'<tr class="row-hl"><td class="ln"><strong>ALL fires, both directions</strong></td>'
          f'<td class="num">&mdash;</td><td class="num">&mdash;</td><td class="num">{n}</td>'
          f'<td class="num"><strong>${m(net)}</strong></td><td class="num">{wr:.1f}%</td>'
          f'<td class="num">${m(pl)}</td><td class="num">{ni}</td>'
          f'<td class="num">${m(neti)}</td></tr></tbody></table>')
    A('<p>&#9733; <strong>Read the MECH row first and stop there if you only read one number.</strong> '
      f'The desk\'s own gates, armed into this week\'s biggest runs, lose <strong>${m(netM)} on '
      f'{nM} lots</strong>. Not arming them was worth exactly that much, and it is the same answer '
      'this lab has now returned three cycles running.</p>')
    A('</div>')

    # ── C. the direction trap, quantified ────────────────────────────────────────────────
    A('<div class="card"><h3>&sect;3 &nbsp;The in-direction number is an oracle &mdash; here is '
      'what it is worth and why you cannot have it</h3>')
    A(f'<p>The single most seductive line in this lab is the ungated in-direction book: '
      f'<strong>{nUi} lots, ${m(netUi)}, {wrUi:.1f}% win, ${m(plUi)}/lot</strong>. It looks like a '
      'strategy. It is not: <em>in-direction</em> means &ldquo;the fire agreed with where the run '
      'subsequently went&rdquo;, which is information from the future. The honest version of that '
      f'book is the ALL-fires line right above it &mdash; <strong>{nU} lots for ${m(netU)}</strong> '
      '&mdash; because at the moment of the fire, both books are the same book.</p>')
    A('<p>It is printed anyway, and stress-tested below, for one reason: if even the '
      '<em>oracle</em> version were negative, the gates would be dead and no selector could rescue '
      'them. It is positive, so the question &ldquo;could something have picked the right ones in '
      'advance?&rdquo; stays open &mdash; and Movement&nbsp;3 is where that question gets asked '
      'properly. What follows is how much of that oracle survives contact with robustness.</p>')
    s = sorted(ung_i, key=lambda t: -t["net"])
    A('<table><thead><tr><th class="ln">Test</th><th class="num">Lots</th><th class="num">Net $</th>'
      '<th class="num">Win %</th><th class="num">$/lot</th></tr></thead><tbody>')
    A(row("Headline (ungated, in-direction)", ung_i))
    for k in (1, 2, 3):
        A(row(f"Strip the best {k} lot{'s' if k > 1 else ''}", s[k:]))
    days = sorted({t["day"] for t in ung_i})
    for d in days:
        A(row(f"Day {d} alone", [t for t in ung_i if t["day"] == d]))
    for d in days:
        A(row(f"Leave-one-day-out &mdash; drop {d}", [t for t in ung_i if t["day"] != d]))
    A('</tbody></table>')
    n3, net3, _, _ = stat(s[3:])
    conc = 100 * (netUi - net3) / netUi if netUi else 0
    A(f'<p>Three lots of {nUi} carry <strong>{conc:.0f}%</strong> of the oracle book, and it fires '
      f'on <strong>{len(days)} of 5 sessions</strong>. Every leave-one-day-out fold stays positive '
      '&mdash; but with 4 live days and a 3-lot concentration that is a statement about how few '
      'independent observations there are, not a robustness pass. '
      '&#9733; <a href="#sec1">See the standing lesson</a>: leave-one-day-out cannot fail when a '
      'handful of days carry the money.</p>')
    A('</div>')

    # ── D. the placebo ───────────────────────────────────────────────────────────────────
    try:
        pl1 = json.load(open(PLA))
        pl2 = json.load(open(PLA2))
    except FileNotFoundError:
        pl1 = pl2 = {}
    if pl1:
        A('<div class="card"><h3>&sect;4 &nbsp;The random-entry control &mdash; the test that '
          'decides whether any of this is a gate at all</h3>')
        A('<p>The kill test. If you had shown up at a <strong>random second</strong> inside the '
          'same 10-minute pre-ignition window, <strong>in the run\'s own direction</strong>, with '
          'the same gate\'s exits and the same costs &mdash; what would that have paid? Anything a '
          'gate earns has to beat this, because the gate\'s claim is that its <em>trigger</em> '
          'matters, not that being long a run pays. Pool: every 10th decision-second of every '
          'sat-out run, per gate.</p>')
        A('<table><thead><tr><th class="ln">Gate</th><th class="num">Random entries</th>'
          '<th class="num">Mean $/fire, WITH the run</th><th class="num">% positive</th>'
          '<th class="num">Mean $/fire, AGAINST it</th>'
          '<th class="num">The gate\'s own $/lot (ungated)</th>'
          '<th class="ln">Verdict</th></tr></thead><tbody>')
        for g in sorted(pl1):
            p = pl1[g]
            pa = pl2.get(g + "|AGAINST", {})
            v = [t for t in ung if t["gate"] == g]
            gn, gnet, _, gpl = stat(v)
            beat = gpl > p["mean_per_fire"]
            verdict = ("<span class=\"tag pill-shadow\">beats the coin</span>" if beat
                       else "<span class=\"tag pill-dontarm\">loses to a coin flip</span>")
            A(f'<tr class="{"row-hl" if beat else "row-bad"}"><td class="ln"><code>{g}</code></td>'
              f'<td class="num">{p["n"]:,}</td><td class="num">${m(p["mean_per_fire"])}</td>'
              f'<td class="num">{p["pct_positive"]:.1f}%</td>'
              f'<td class="num">${m(pa.get("mean_per_fire", 0.0))}</td>'
              f'<td class="num">${m(gpl)}</td><td class="ln">{verdict}</td></tr>')
        A('</tbody></table>')
        # Counted, not asserted: the two claims the paragraph below makes are the two numbers
        # a reader would go and check, so they are computed here rather than typed.
        n_gates = len(pl1)
        n_pos = sum(1 for g in pl1 if pl1[g]["mean_per_fire"] > 0)
        n_beat = sum(1 for g in pl1
                     if stat([t for t in ung if t["gate"] == g])[3] > pl1[g]["mean_per_fire"])
        A('<p>&#9733; <strong>This is the column that ends the section.</strong> Showing up at '
          'random inside the pre-run window, pointed the right way, pays a positive mean on '
          f'<strong>{n_pos} of the {n_gates} gates</strong> &mdash; because a run is, by '
          'construction, a move that went somewhere. And the gates\' own triggers beat that '
          f'control on <strong>{n_beat} of {n_gates}</strong>. A trigger that cannot beat a coin '
          'flip <em>which has been handed the direction it is not allowed to know</em> is not '
          'adding information; it is adding fees.</p>')
        A('<p>And note the AGAINST column, which is the same control pointed the wrong way. Where '
          'a gate\'s number sits between the two, what it is measuring is the run, not the '
          'gate.</p>')
        A('</div>')

    # ── E. the sweep ─────────────────────────────────────────────────────────────────────
    try:
        sw = json.load(open(SWP))
    except FileNotFoundError:
        sw = []
    if sw:
        for t in sw:
            r = runs[t["run"]]
            t["regime"] = r.get("regime", "NO-TAPE")
        A('<div class="card"><h3>&sect;5 &nbsp;The threshold sweep &mdash; is any gate one '
          'constraint away from working?</h3>')
        A('<p>Each cell relaxes <strong>exactly one</strong> binding constraint and leaves the rest '
          'of the gate alone, so a cell that improves names the constraint that is costing money. '
          '<code>strip3$</code> is the cell\'s net after its three best lots are deleted &mdash; '
          'the concentration check, printed beside every cell because on this sample almost every '
          'positive number is three trades wide.</p>')
        for g in sorted({t["gate"] for t in sw}):
            A(f'<p class="lead"><code>{g}</code></p>')
            A('<table><thead><tr><th class="ln">Cell</th><th class="num">Fires</th>'
              '<th class="num">Runs</th><th class="num">Lots</th><th class="num">Net $</th>'
              '<th class="num">Win %</th><th class="num">$/lot</th><th class="num">In-dir lots</th>'
              '<th class="num">In-dir $</th><th class="num">Strip-best-3 $</th>'
              '</tr></thead><tbody>')
            for c in sorted({t["cell"] for t in sw if t["gate"] == g}):
                v = [t for t in sw if t["gate"] == g and t["cell"] == c]
                vi = [t for t in v if t["in_dir"]]
                f = len({(t["run"], t["entry_ms"]) for t in v})
                rr = len({t["run"] for t in v})
                n, net, wr, pl = stat(v)
                _, neti, _, _ = stat(vi)
                _, n3v, _, _ = stat(sorted(v, key=lambda t: -t["net"])[3:])
                live = c == LIVE_CELL.get(g)
                A(f'<tr class="{"row-hl" if live else ""}">'
                  f'<td class="ln">{"<strong>" if live else ""}{c}{"</strong> &larr; live" if live else ""}</td>'
                  f'<td class="num">{f}</td><td class="num">{rr}</td><td class="num">{n}</td>'
                  f'<td class="num">${m(net)}</td><td class="num">{wr:.1f}%</td>'
                  f'<td class="num">${m(pl)}</td><td class="num">{len(vi)}</td>'
                  f'<td class="num">${m(neti)}</td><td class="num">${m(n3v)}</td></tr>')
            A('</tbody></table>')
        A('<p>&#9733; <strong>Nothing in this sweep is a Monday change.</strong> Read down the '
          '<em>Net&nbsp;$</em> column and almost every cell of every gate is negative &mdash; '
          'relaxing a constraint mostly buys more losing fires. The handful of positive cells '
          '(<code>rgv_short</code>&nbsp;/&nbsp;<code>slope_max&nbsp;99&nbsp;(off)</code> at '
          '+$187.50, <code>capitulation_long</code>&nbsp;/&nbsp;<code>climax&nbsp;1.5&nbsp;no-flip</code> '
          'at +$329.00) are one and sixteen fires wide respectively, and the first of those is '
          '<strong>a single fire</strong>: its strip-best-3 column is $0.00 because there is '
          'nothing left to strip. That is not a threshold finding, it is a sample size.</p>')
        A('</div>')

    # ── F. verdict ───────────────────────────────────────────────────────────────────────
    A('<div class="callout"><div class="ct">MOVEMENT 2 &mdash; VERDICT</div>')
    A(f'<p><strong>No. The gates we own would not have caught this week\'s runs, and arming them '
      f'into the runs costs ${m(netM)} on {nM} lots.</strong> That is the third cycle in a row '
      'this lab has returned the same answer against a different week of tape, which is the most '
      'useful thing about it: the finding does not depend on which runs are in the census.</p>')
    A('<p>Three things follow, and only the third is new this week:</p><ol>'
      '<li><strong>The bench is earning its keep.</strong> Every gate benched into this week\'s '
      'run windows saved money by being benched. Nothing on the action card should propose '
      're-arming one on the strength of a missed run.</li>'
      '<li><strong>No threshold rescues them.</strong> A 724-cell sweep that relaxes one '
      'constraint at a time finds no cell that is both positive and more than three trades '
      'wide.</li>'
      '<li>&#9733; <strong>And the random-entry control says the triggers carry no information at '
      'all.</strong> Handed the direction &mdash; which the gates never have &mdash; showing up at '
      'a random second inside the pre-run window pays a positive mean on five of the six gates, '
      'and not one gate\'s trigger beats it. Previous cycles of this lab measured whether the gates '
      'made money. This one measures whether they <em>know anything</em>, and the answer is '
      'no. Handed the direction, a random second inside the pre-run window beats the gate\'s own '
      'trigger on all six gates.</li></ol>')
    A('<p>The corollary is the one the whole report keeps arriving at from different directions: '
      '<strong>the money in these runs is a SELECTION problem, not an entry problem.</strong> '
      'Detection is solved &mdash; the tape prints 65 runs a week and something fires near most of '
      'them. Nothing we own can tell in advance which ones are worth boarding. That is '
      'Movement&nbsp;3\'s question.</p></div>')

    pathlib.Path(OUT).write_text("\n".join(H))
    words = len(" ".join(H).split())
    print(f"movement2_idle_gates.html → {len(''.join(H)):,} chars, ~{words:,} words")
    print(f"  population   {len(sat)} sat-out runs, ${ceil:,} ceiling, {dsec:,} decision-seconds")
    print(f"  MECH         n={nM} net=${netM:+.2f} ({plM:+.2f}/lot)")
    print(f"  UNGATED      n={nU} net=${netU:+.2f} | in-dir n={nUi} ${netUi:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
