#!/usr/bin/env python3
"""MOVEMENT 1 — rebuild the census fragment from the FROZEN census stdout.

★ THE FAULT THIS CLOSES. `run_census.py --html` writes the Movement-1 fragment as a side effect
of running the census. This cycle the census was re-frozen on 2026-08-25 17:50-17:58 WITHOUT
`--html`, so `census_stdout.txt` / `census_summary.json` moved and `movement1_census.html` did
not. The report was one stitch away from carrying TWO different censuses:

    movement1_census.html  (08-22)  70 runs · 65 sat out · $9,986 ceiling
    census_summary.json    (08-25)  68 runs · 62 sat out · $9,610 ceiling

and all seven greenfield labs anchor on the second one — several of them open by reproducing it
row for row before they are allowed to disagree with anything. A reader comparing Movement 1's
table with Movement 3's "62 sat-out runs, $9,610" would have found the report contradicting
itself, with no way to tell which half was current.

Re-running `run_census.py` is a multi-minute tick crunch over the parquet lake and the whole
point of freezing the census is that nothing downstream re-runs it. So this renders the fragment
from the frozen STDOUT instead — the same rows, the same numbers, by construction, because it is
the same text the labs read. It emits the same markup `run_census.py --html` does, class for
class, so the light theme is unchanged.

Usage:
  python3 scripts/friday_v7_movement1_from_stdout.py            # both symbols
  python3 scripts/friday_v7_movement1_from_stdout.py --symbol MGC
"""
from __future__ import annotations

import argparse
import html as _h
import pathlib
import re
import sys

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
VPP_BY_SYMBOL = {"MNQ": 2.0, "MGC": 10.0}
BOOK_SRC = {"MNQ": "capture.db.book, 3 deep, 30s", "MGC": "depth.db.depth_snap, 3 deep, 30s"}

WHAT = {
    "VACUUM": "moved AGAINST the tape (a snap-back / stop-run)",
    "FLOW-LED": "aggressors drove it (a continuation)",
    "OPEN/NEWS": "the 13:00&ndash;15:00 UTC cash-open / data window",
    "VOL-EXPANSION": "amplitude broke out of a coil",
    "UNCLASS": "no clear tape tell (quiet ignition)",
}

# ★ The two labels below were interrogated to destruction by this week's greenfield phases and the
# census's own vocabulary did not survive it. The fragment says so INSIDE the cluster table rather
# than leaving the reader to find it 40,000 words later, because the table is where the wrong
# inference gets made.
LABEL_NOTE = {
    "VACUUM": "&#9733; <strong>this label is not a footprint</strong> &mdash; the flow event behind "
              "it fires on 20.4% of all tape and then splits it VACUUM/FLOW-LED on a 49.9% coin "
              "toss (Movement&nbsp;3, VACUUM &sect;2 and FLOW-LED)",
    "FLOW-LED": "&#9733; same coin toss as VACUUM &mdash; the split carries 0.33pp of directional "
                "information; the lift it does carry is a VOLUME lift wearing a flow costume",
    "UNCLASS": "&#9733; base rate 75.4% on all tape, lift <strong>0.82</strong> &mdash; this is "
               "<em>coverage</em>, not a finding. Movement&nbsp;3 recommends renaming it "
               "<code>UNTESTED</code>",
    "OPEN/NEWS": "&#9733; lift over the bare clock is <strong>0.921&times;</strong> &mdash; the two "
                 "footprint tests remove 41% of the window and keep the <em>less</em> run-dense half",
}

ROW = re.compile(
    r"^(?P<t>\d\d-\d\d \d\d:\d\d)\s+(?P<d>UP|DN)\s+(?P<mv>[+\-]?\d+)\s+(?P<ceil>\d+)\s+"
    r"(?P<us>sat out|caught|FOUGHT)\s+(?P<rest>.*)$")


def parse(txt: str) -> dict:
    lines = txt.split("\n")
    out: dict = {"rows": [], "clusters": {}, "gates": []}
    for ln in lines:
        m = re.match(r"^\[window\]\s+(\S+ \S+) \.\. (\S+ \S+) UTC", ln)
        if m:
            out["w0"], out["w1"] = m.group(1), m.group(2)
        m = re.search(r"RUN CENSUS —.*?(\d+) runs ≥ ([\d.]+)×ATR "
                      r"\(15-min move ≥ (\d+)pt; typical 15m range = (\d+)pt\)", ln)
        if m:
            out["n"], out["atr_k"] = int(m.group(1)), m.group(2)
            out["thr"], out["typ"] = int(m.group(3)), int(m.group(4))
        m = ROW.match(ln.rstrip())
        if m:
            rest = m.group("rest").split()
            # gate name may contain no spaces; trailing 5 fields are real$ flow amp book cluster
            gate = rest[0]
            tail = rest[1:]
            real, flow, amp, book, cluster = tail[-5], tail[-4], tail[-3], tail[-2], tail[-1]
            out["rows"].append(dict(t=m.group("t"), d=m.group("d"), mv=int(m.group("mv")),
                                    ceil=int(m.group("ceil")), us=m.group("us"), gate=gate,
                                    real=real, flow=flow, amp=amp, book=book, cluster=cluster))
        m = re.match(r"^\s+(\S+)\s+(\d+) runs$", ln)
        if m:
            out["clusters"][m.group(1)] = int(m.group(2))
        m = re.match(r"^\s+(CAUGHT|FOUGHT|SAT OUT)\s+(\d+) runs · ceiling \$\s*(\d+) · real \$\s*([+\-]?\d+)", ln)
        if m:
            key = m.group(1).replace(" ", "_").lower()
            out[key] = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
        m = re.match(r"^\s+(\S+)\s+\$\s*([+\-]?\d+)$", ln)
        if m and "runs" not in ln:
            out["gates"].append((m.group(1), int(m.group(2))))
    return out


def build(sym: str) -> str:
    src = pathlib.Path(SEC) / ("census_stdout.txt" if sym == "MNQ" else "census_stdout_MGC.txt")
    c = parse(src.read_text())
    vpp = VPP_BY_SYMBOL[sym]
    caught, ceil_caught, real_caught = c.get("caught", (0, 0, 0))
    fought, ceil_fought, real_fought = c.get("fought", (0, 0, 0))
    sat, ceil_sat, _ = c.get("sat_out", (0, 0, 0))
    conv = 100 * real_caught / ceil_caught if ceil_caught else 0

    h = [
        f'<h2><span class="n">M1</span> The biggest runs on {sym} this week &mdash; did we show up?</h2>',
        f'<p class="lead">Forget what the desk did this week &mdash; start from the raw tape. {sym} printed '
        f'<strong>{c["n"]} runs of {c["atr_k"]}&times;ATR or bigger</strong> between <strong>{c["w0"]}</strong> '
        f'and <strong>{c["w1"]} UTC</strong> (a 15-minute move of at least {c["thr"]} points, against a '
        f'typical 15-min range of {c["typ"]}). That is the whole tape, not a top-ten. '
        f'We <strong>caught {caught}</strong>, we were positioned <em>against</em> <strong>{fought}</strong>, '
        f'and we <strong>sat out {sat}</strong>. '
        + (f'<strong>We have no gate on {sym}</strong>, so all {sat} runs and <strong>${ceil_sat:,.0f}</strong> '
           'of hindsight ceiling were sat out by construction, not by a decision that went wrong. Nothing '
           'here is a bleed &mdash; it is an empty seat, and the question the next movements ask is what '
           'could sit in it.</p>' if caught == 0 else
           f'The runs we aligned with banked <strong>+${real_caught:,.0f}</strong> of honest money &mdash; but '
           f'that is only {conv:.0f}% of their ${ceil_caught:,.0f} hindsight ceiling, and the {sat} we sat out '
           f'left <strong>${ceil_sat:,.0f}</strong> on the table. The bleed is not the runs; it is the fading '
           'we do around them.</p>'),
        '<div class="rev3ptr"><strong>&#9733; THIS IS THE FROZEN CENSUS, RE-FROZEN 2026-08-25.</strong> '
        'Every number on this page and every number in Movement&nbsp;2 and Movement&nbsp;3 comes from the '
        f'same run of <code>run_census.py</code> &mdash; {c["n"]} runs, {sat} sat out, '
        f'${ceil_sat:,.0f} of sat-out ceiling. '
        + ('An earlier freeze of this fragment (2026-08-22) read <span class="was">70 runs / 65 sat out / '
           '$9,986</span> and is superseded; the seven greenfield labs each reproduce the table below row '
           'for row before they are allowed to disagree with anything, so the two could not both stand. '
           '⚠ Movement&nbsp;2\'s idle-gate replay was computed against the SUPERSEDED freeze and is '
           'banner-marked accordingly &mdash; its run list is 70/65, not this one.'
           if sym == "MNQ" else
           'The gold census was re-frozen in the same run as the Nasdaq one, so the two halves of '
           'Movement&nbsp;1 are the same vintage. The desk has never traded MGC, so nothing downstream '
           'of this table depends on a book.') + '</div>',
        '<div class="callout"><div class="ct">THE FULL CENSUS</div><p>Every qualifying run, in order. '
        f'<strong>Move</strong> is the swing in points; <strong>$ 1lot</strong> is that move on one {sym} lot '
        f'(${vpp:.0f}/pt) &mdash; the hindsight ceiling. <strong>real $</strong> is what a gate actually banked '
        'near it. <strong>Flow</strong> is net aggressor volume in the 60s before; <strong>amp</strong> is '
        'pre-run amplitude; <strong>book</strong> is the far-side L2 depth share (below 0.50 = the side price '
        f'ran toward was thin), read from <code>{BOOK_SRC[sym]}</code>. Green = we caught it, red = we '
        'fought it.</p></div>',
        '<table><tr><th>Time (UTC)</th><th>Dir</th><th>Move</th><th>$ 1lot</th><th>Us</th><th>Gate</th>'
        '<th>real $</th><th>Flow</th><th>Amp</th><th>Book</th><th>Cluster</th></tr>']
    for r in c["rows"]:
        rc = ' class="row-hl"' if r["us"] == "caught" else ' class="row-bad"' if r["us"] == "FOUGHT" else ''
        gg = "&mdash;" if r["gate"] in ("—", "-") else _h.escape(r["gate"])
        rv = r["real"] if r["us"] != "sat out" else ""
        h.append(f'<tr{rc}><td class="ln">{r["t"]}</td><td>{r["d"]}</td><td class="num">{r["mv"]:+d}</td>'
                 f'<td class="num">{r["ceil"]}</td><td>{r["us"]}</td><td>{gg}</td><td class="num">{rv}</td>'
                 f'<td class="num">{r["flow"]}</td><td class="num">{r["amp"]}</td>'
                 f'<td class="num">{r["book"]}</td><td>{_h.escape(r["cluster"])}</td></tr>')
    h.append('</table>')

    h.append('<div class="card"><h3>What the runs were &mdash; by cause, and what this week did to the '
             'vocabulary</h3><p>Each run gets a cause fingerprint from its pre-run tape. This used to be '
             'the map for where to hunt a new gate. <strong>This week three of the five labels were '
             'interrogated directly and did not survive it</strong> &mdash; the notes in the right-hand '
             'column are Movement&nbsp;3\'s findings, not decoration, and they are the reason no hunt '
             'should be scoped by a label again until the census is fixed.</p>'
             '<table><tr><th>Cluster</th><th>Runs</th><th>What it is</th><th>What Movement 3 found</th></tr>')
    for cl, n in sorted(c["clusters"].items(), key=lambda x: -x[1]):
        h.append(f'<tr><td>{cl}</td><td class="num">{n}</td><td>{WHAT.get(cl, "")}</td>'
                 f'<td>{LABEL_NOTE.get(cl, "not interrogated this week")}</td></tr>')
    h.append('</table></div>')

    h.append('<div class="callout"><div class="ct">HONEST MONEY &mdash; ceiling vs what we banked</div>'
             '<table><tr><th></th><th>Runs</th><th>Hindsight ceiling</th><th>What we really made</th></tr>'
             f'<tr class="row-hl"><td>Caught (aligned)</td><td class="num">{caught}</td>'
             f'<td class="num">${ceil_caught:,.0f}</td>'
             f'<td class="num">+${real_caught:,.0f}{"" if caught == 0 else f" &nbsp;({conv:.0f}%)"}</td></tr>'
             f'<tr class="row-bad"><td>Fought (against)</td><td class="num">{fought}</td>'
             f'<td class="num">${ceil_fought:,.0f}</td><td class="num">${real_fought:+,.0f}</td></tr>'
             f'<tr><td>Sat out</td><td class="num">{sat}</td><td class="num">${ceil_sat:,.0f}</td>'
             '<td class="num">$0 &larr; the money on the table</td></tr></table>'
             + ('<p>Every row is a sat-out row because there is no gate on this instrument to catch or '
                'fight anything. The ceiling is what one lot would have made on a perfect entry and a '
                'perfect exit, so treat it as the size of the seat, never as money forgone. The next two '
                'movements ask what could fill it.</p></div>' if caught == 0 else
                '<p>The runs made money and the fading gave it back; we convert a fraction of the ceiling '
                'and ignore the rest. <strong>&#9733; And read the ceiling column with Movement&nbsp;3\'s '
                'correction attached:</strong> the sat-out ceiling is a HINDSIGHT number. A <em>perfect</em> '
                'late boarder &mdash; one that fires inside every run at a median three minutes in and then '
                'exits at the exact top with no costs at all &mdash; reaches only <strong>53%</strong> of it, '
                'and a deployable one 20&ndash;24%. Thirteen per cent of the runs are finished before any '
                'honest trigger can see them.</p></div>'))

    if c["gates"]:
        h.append('<div class="card"><h3>Which book was near the runs</h3>'
                 '<table><tr><th>Gate / desk</th><th>real $ near the runs</th></tr>')
        for g, v in sorted(c["gates"], key=lambda x: x[1]):
            cls = ' class="row-bad"' if v < 0 else ' class="row-hl"' if v > 0 else ''
            h.append(f'<tr{cls}><td>{_h.escape(g)}</td><td class="num">${v:+,.0f}</td></tr>')
        h.append('</table><p>&#9733; The single biggest line here is <code>day_rider</code>, and it is '
                 'negative. The tournament was barely present at the week\'s runs at all; the rider was '
                 'present and on the wrong side twice. That is the census\'s own view of the week\'s '
                 'money, arrived at from the tape rather than from the books.</p></div>')
    return "\n".join(h)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None, choices=sorted(VPP_BY_SYMBOL))
    a = ap.parse_args()
    syms = [a.symbol] if a.symbol else ["MNQ", "MGC"]
    for sym in syms:
        out = pathlib.Path(SEC) / ("movement1_census.html" if sym == "MNQ"
                                   else "movement1_census_MGC.html")
        doc = build(sym)
        out.write_text(doc)
        print(f"{sym}: {out} ({len(doc):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
