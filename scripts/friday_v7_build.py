#!/usr/bin/env python3
"""Assemble the pre-baked V7 Friday 'big runs' deep-dive (Part 3) → light-theme HTML + iPad PDF.

Stitches the three movement fragments (census / idle-gate lab / greenfield) into the proven
light-theme shell and renders a PDF via weasyprint (system python3). Standalone artifact the
operator reviews tonight; the same fragments drop into the full cron report. Run with system
python3 (weasyprint lives there), NOT the trading .venv.

  python3 scripts/friday_v7_build.py --slug 2026-07-24
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
OUT = "/home/alphabot/gazbot7/src/gazbot7/web_static"
CSS_TEMPLATE = "/home/alphabot/alphabot2/alphabot/dashboard/static/weekly_2026-06-26.html"

# supplemental CSS for classes the template may not define (section number pill + verdict tags)
SUPP = """<style>
.n{display:inline-block;min-width:1.6em;padding:0 .4em;margin-right:.4em;background:#0f2942;color:#fff;
   border-radius:.3em;font-size:.62em;vertical-align:middle;font-weight:700;letter-spacing:.02em}
.tag{display:inline-block;padding:.08em .5em;border-radius:.3em;font-size:.72em;font-weight:700;
     background:#eee;color:#0f2942;border:1px solid #cbd5e0}
.pill-shadow{background:#fff3d6;border-color:#e0b84a}.pill-null{background:#f0f0f0}
.pill-dontarm{background:#fbe3e0;border-color:#c0392b;color:#8a1c10}
.frag-sep{border:0;border-top:2px solid #e6e2d8;margin:2.4em 0}
/* PDF-only: force wide tables (esp. the 11-col census) to fit the page — screen HTML untouched.
   weasyprint renders as print media; table-layout:fixed + word-break guarantees no right-edge overflow. */
@media print{
  @page{size:A4;margin:1.2cm 1cm}
  .wrap{max-width:none;padding-left:12px;padding-right:12px}
  table{table-layout:fixed;width:100%;font-size:9px}
  th,td{padding:3px 4px !important;overflow-wrap:break-word;word-break:break-word;white-space:normal}
  pre,code{white-space:pre-wrap;word-break:break-word}
}
</style>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=dt.date.today().isoformat())
    a = ap.parse_args()

    tpl = pathlib.Path(CSS_TEMPLATE).read_text()
    m = re.search(r"<style.*?</style>", tpl, re.S | re.I)
    css = m.group(0) if m else "<style>body{font-family:Georgia,serif;max-width:900px;margin:auto}</style>"

    # Full report spine, in order: Part 1 (live) → Part 2 (shadow) → Part 2.5 (musings)
    # → the three greenfield movements (census / idle-gate lab / greenfield).
    SECTIONS = (
        "part1_live.html",
        "part2_shadow.html",
        "part25_musings.html",
        "movement1_census.html",
        "movement2_idle_gates.html",
        "movement3_greenfield.html",
    )
    frags = []
    missing = []
    for name in SECTIONS:
        p = pathlib.Path(SEC) / name
        if p.exists():
            frags.append(p.read_text())
        else:
            missing.append(name)
            frags.append(f'<div class="callout"><div class="ct">MISSING</div><p>{name} not generated yet.</p></div>')
    if missing:
        print("WARNING — missing sections: " + ", ".join(missing))

    intro = (
        '<h1>GAZBOT V7 &mdash; the Friday report</h1>'
        f'<p class="lead" style="font-size:1.05em">Full desk review, week ending {a.slug}. Two halves, one document. '
        '<strong>Part 1</strong> is the warm half &mdash; what the live six-gate paper tournament actually did this '
        'week, the direction-router on trial, and the shadow board that earned a promotion (Parts 1, 2 and 2.5). '
        '<strong>Then the cold, tape-first half</strong>: we ignore everything the desk did and ask, from the raw MNQ '
        'tape and order book, <strong>where was the money and did we show up?</strong> &mdash; then test whether the '
        'gates we already own could have caught the runs we missed, and finally build brand-new gates from scratch and '
        'backtest them to death, the ones that failed included (that is the point). Plain English, honest money, every '
        'claim a table.</p>')

    body = intro + '\n<hr class="frag-sep">\n' + '\n<hr class="frag-sep">\n'.join(frags)
    doc = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
           f'<title>GAZBOT V7 — Friday report {a.slug}</title>{css}{SUPP}</head>'
           f'<body><div class="wrap">{body}</div></body></html>')
    out_html = f"{OUT}/v7_big_runs_{a.slug}.html"
    pathlib.Path(out_html).write_text(doc)
    print(f"HTML → {out_html} ({len(doc)} bytes)")

    try:
        import weasyprint
        out_pdf = f"{OUT}/v7_big_runs_{a.slug}.pdf"
        weasyprint.HTML(string=doc).write_pdf(out_pdf)
        print(f"PDF  → {out_pdf}")
    except Exception as e:
        print(f"PDF render skipped ({e}) — run with system python3 that has weasyprint")


if __name__ == "__main__":
    main()
