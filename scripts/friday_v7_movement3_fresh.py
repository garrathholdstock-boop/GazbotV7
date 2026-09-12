#!/usr/bin/env python3
"""MOVEMENT 3 ADDENDUM — the three cluster hunts that finished AFTER the rest of the report.

★ WHY THIS EXISTS. The durable runner's own log for 2026-09-04 reads:

    HAVE part1_live  — skipping (artifact is the checkpoint)     ... x10
    START gf_MGC / gf_RIDER_ALL / gf_UNCLASS
    gf_UNCLASS: rc=0 24.5m   gf_MGC: rc=0 25.9m   gf_RIDER_ALL: rc=0 27.6m

Ten body sections were skipped because their artifacts were already on disk from the 08-28 cycle,
and THREE greenfield clusters ran fresh tonight against a newly frozen census. Those three
overwrote `gf_MGC.md`, `gf_full_RIDER_ALL.md` and `gf_full_UNCLASS.md` — but
`movement3_greenfield.html` was rendered on 2026-08-29 and has the OLD text of those same three
dossiers baked into it, together with an editorial board that summarises the old verdicts.

Re-running friday_v7_movement3_section.py would put tonight's appendix under last week's
editorial board, which is the precise failure that script's own docstring was written against —
a summary that contradicts the working beneath it. So the finished section is left frozen and
intact, and tonight's three dossiers are carried HERE, in full, under a banner that says exactly
how much newer they are and which of the older verdicts they overturn.

  gf_MGC.md             gold, and the contract-roll landmine under every prior gold study
  gf_full_RIDER_ALL.md  the pooled run-catcher, re-derived on 60 days
  gf_full_UNCLASS.md    the biggest bucket, and the death of the size-threshold hypothesis

Run:  python3 scripts/friday_v7_movement3_fresh.py
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from friday_v7_md2html import md_to_html, word_count          # noqa: E402

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = f"{SEC}/movement3_fresh_0904.html"

# (anchor, display title, file, what it hunted, what it OVERTURNS in the frozen section above)
LABS = [
    ("m3f-mgc", "GOLD &mdash; MGC, seventeen live shadow days, and the landmine under every "
     "prior gold study",
     "gf_MGC.md",
     "The second instrument, $10.00 a point, with the gold shadow book now graded on 225 "
     "tick-repriced live trades rather than on a model.",
     "The frozen board above grades gold <strong>SHADOW</strong> on the double-hole arm "
     "(n=200, +$16.52/tr). Tonight's hunt is a <strong>hard null on all four cells</strong> "
     "&mdash; six candidates, every one beaten by shorting one lot at a fixed time of day &mdash; "
     "and it finds that <strong>22% of the lake's gold year is the wrong contract</strong>, which "
     "puts last week's thirteen-months-of-gold conclusions out of commission."),
    ("m3f-rider", "THE POOLED RUN-CATCHER &mdash; re-derived on 60 days, and graded against its "
     "own live shadow arm",
     "gf_full_RIDER_ALL.md",
     "Ignore the cluster labels. Board any run late, ride it wide, filter it causally &mdash; "
     "the same hypothesis, on 904,075 five-second bars.",
     "The frozen board above PARKS the pooled rider on an out-of-sample leg worth +$14. Tonight's "
     "run reaches the same disposition by a harder road and adds the number that settles it: "
     "<code>rider_w5</code>, promoted to shadow last week on a +$19.29-per-trade backtest, has "
     "since booked <strong>108 live shadow trades at &minus;$25.95 each</strong> &mdash; a "
     "$45-a-trade swing between fit and forward."),
    ("m3f-uncl", "UNCLASS &mdash; the biggest bucket, and the death of the size-threshold "
     "hypothesis",
     "gf_full_UNCLASS.md",
     "The bucket the classifier could not name, ridden direction-agnostically and swept out to "
     "no stop at all.",
     "The frozen board above PARKS UNCLASS on the placebo test. Tonight's run spends the exact "
     "revival condition that PARK was granted &mdash; a board-time size predictor at r&nbsp;&ge;&nbsp;0.40 "
     "on &ge;300 runs &mdash; and it comes back <strong>r&nbsp;=&nbsp;0.15 on 4,830 boards</strong>. "
     "It also refutes this report's own <strong>size-threshold</strong> finding: measured in ATR "
     "units rather than points, every discriminator collapses to AUC&nbsp;&asymp;&nbsp;0.50."),
]


def build() -> str:
    labs = []
    for anchor, title, fname, what, overturns in LABS:
        p = pathlib.Path(SEC) / fname
        # ★ is_file(), never a bare glob: a dossier filename containing a "/" becomes a real
        # DIRECTORY on this box and read_text() raises IsADirectoryError on it.
        if not p.is_file() or not p.stat().st_size:
            labs.append((anchor, title, fname, what, overturns, None, None))
            continue
        md = p.read_text()
        labs.append((anchor, title, fname, what, overturns, md,
                     dt.datetime.fromtimestamp(p.stat().st_mtime, dt.UTC)))

    present = [x for x in labs if x[5]]
    missing = [x for x in labs if not x[5]]
    total_words = sum(len(x[5].split()) for x in present)
    newest = max((x[6] for x in present), default=None)

    h: list[str] = []
    h.append(
        '<div class="rev3"><div class="ct">&#9733;&#9733; THESE THREE HUNTS ARE NEWER THAN THE '
        'REST OF THIS REPORT &mdash; read them last, and let them win</div>'
        '<p>Everything above this box in Movement&nbsp;3 was rendered on <strong>2026-08-29</strong> '
        'from labs that ran against the census frozen on 2026-08-28. The three dossiers below ran '
        f'<strong>tonight</strong>, finishing at <strong>{newest:%Y-%m-%d %H:%M}&nbsp;UTC</strong>, '
        'against a census frozen at 21:12Z covering <strong>2026-08-30 22:00 &rarr; 2026-09-04 '
        '20:59&nbsp;UTC</strong> and against the parquet lake out to 2026-09-04. They are the same '
        'three questions asked again on more tape, and they are '
        f'<strong>{total_words:,} words</strong> of finished, tick-honest working.</p>'
        '<p><strong>Two of the three overturn a verdict printed above them, and one overturns a '
        'headline finding of this whole report.</strong> Each is named in its own header box '
        'below. Where a dossier here disagrees with the editorial board earlier in this movement, '
        '<em>this section wins</em> &mdash; not because it is louder, but because it is later '
        'evidence on strictly more data, which is the only reason a verdict should ever move.</p>'
        '<p><strong>They are carried here rather than folded into the section above on purpose.</strong> '
        'Rebuilding Movement&nbsp;3 from tonight\'s dossiers would have put tonight\'s appendix '
        'underneath last week\'s summary of it &mdash; a map that describes a different territory '
        'from the one printed beneath it. That failure has shipped on this desk before. A dated '
        'addendum cannot do it.</p></div>')

    if missing:
        h.append(
            '<div class="rev3"><div class="ct">&#9733; NOT EVERY DOSSIER ARRIVED</div><p>'
            + ', '.join(f'<code>{x[2]}</code>' for x in missing)
            + ' did not write a file tonight, so the hunt(s) named there are absent rather than '
              'null. Nobody looked; that is not the same as looking and finding nothing.</p></div>')

    # Contents, so the reader can see the three verdicts before 23k words of working.
    h.append('<div class="v7toc"><h3>Tonight&rsquo;s three, and what each one moved</h3><ol>'
             + "".join(f'<li><span class="lab"><a href="#{a}">{t}</a></span>'
                       f'<br><span class="sub">{ov}</span></li>'
                       for a, t, _f, _w, ov, md, _m in labs if md)
             + '</ol></div>')

    for anchor, title, fname, what, overturns, md, mt in labs:
        if not md:
            continue
        h.append(f'<h4 id="{anchor}">{title}</h4>')
        h.append(f'<p class="winsub">{what}</p>')
        h.append('<div class="rev3ptr"><strong>What this one moves:</strong> ' + overturns
                 + f' <em>Source: <code>{fname}</code>, written {mt:%Y-%m-%d %H:%M} UTC, '
                   f'{len(md.split()):,} words, reproduced in full and unedited below.</em></div>')
        h.append(md_to_html(md, h_offset=3))

    doc = "\n".join(h)
    return doc


if __name__ == "__main__":
    doc = build()
    pathlib.Path(OUT).write_text(doc)
    print(f"MOVEMENT 3 ADDENDUM → {OUT} ({len(doc):,} chars, {word_count(doc):,} words)")
