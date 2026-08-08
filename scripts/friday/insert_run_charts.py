#!/usr/bin/env python3
"""Fold the RUN CHARTS fragment into Part 1, next to the case study each one illustrates.

The charts belong WITH the story ("Case 2 Wednesday — the clean two-way trend" should have
Wednesday's chart under it), not in an appendix. Matching is on the case-study HEADING TEXT,
never a byte offset, so this still works after Rev2 has rewritten the section.

IDEMPOTENT: re-running never double-inserts — a chart already present for a day is skipped.
Any chart with no matching case study is appended to the end of Part 1 rather than dropped.

  insert_run_charts.py [--charts run_charts.html] [--into part1_live.html] [--dry-run]
"""
import argparse, re, sys

SEC = "/home/alphabot/gazbot7/reports/friday_v7/sections"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def split_charts(frag):
    """Fragment -> [(day_or_None, html_block)] in document order."""
    blocks = re.findall(r'<div class="card">.*?</div>\s*(?=<div class="card">|$)', frag, re.S)
    if not blocks:                                   # fall back to one block per <svg>
        blocks = [m.group(0) for m in re.finditer(r"<svg.*?</svg>", frag, re.S)]
    out = []
    for b in blocks:
        title = re.search(r"<title>(.*?)</title>", b, re.S)
        t = title.group(1) if title else ""
        out.append((next((d for d in DAYS if d.lower() in t.lower()), None), b))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--charts", default=f"{SEC}/run_charts.html")
    ap.add_argument("--into", default=f"{SEC}/part1_live.html")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    frag = open(a.charts).read()
    doc = open(a.into).read()
    charts = split_charts(frag)
    if not charts:
        print("no charts found in fragment — nothing to do", file=sys.stderr)
        return 1

    inserted, skipped, orphans = [], [], []
    for day, block in charts:
        if block.strip() and block.strip()[:400] in doc:
            skipped.append(day or "?")
            continue
        if day and re.search(rf"<svg[^>]*aria-label=\"{day}", doc):
            skipped.append(day)
            continue
        # insert right after the case-study heading that names this day
        m = day and re.search(rf"(<h2[^>]*>(?:(?!</h2>).)*?{day}(?:(?!</h2>).)*?</h2>)", doc, re.S)
        if m:
            doc = doc[:m.end()] + "\n" + block + "\n" + doc[m.end():]
            inserted.append(day)
        else:
            orphans.append((day, block))

    for day, block in orphans:                        # never silently drop a chart
        doc = doc.rstrip() + "\n" + block + "\n"
        inserted.append(f"{day or '?'}(appended)")

    if a.dry_run:
        print(f"DRY RUN — would insert: {inserted or 'none'} | skip (already present): {skipped or 'none'}")
        return 0

    open(a.into, "w").write(doc)
    print(f"inserted: {inserted or 'none'} | skipped (already present): {skipped or 'none'}")
    print(f"{a.into} now has {len(re.findall(r'<svg', doc))} chart(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
