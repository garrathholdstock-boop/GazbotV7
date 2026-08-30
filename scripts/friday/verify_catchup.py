#!/usr/bin/env python3
"""Post-run gate for the 2026-08-25 catch-up build. JUDGE ON THE ARTIFACT, NEVER THE EXIT CODE.

The 08-21 run exited 0 having built 4 of 13 sections, so "rc=0" is worthless here. This checks the
report that actually landed on disk, and only then retires the older, thinner copy.

⚠ THE DUPLICATE. The previous run published `weekly_2026-08-22.html`; assemble writes
`weekly_2026-08-21.html` (the WEEK is the Friday). The dashboard sorts by the DATE IN THE FILENAME,
so leaving both means the THIN report sorts newest and is the one the operator opens. The old copy
is therefore removed — but ONLY once the new one passes, so a failed run never leaves him with no
report for the week at all.
"""
import datetime as dt
import os
import re
import sys

GB = "/home/alphabot/gazbot7"
WEB = f"{GB}/src/gazbot7/web_static"
NEW = f"{WEB}/weekly_2026-08-21.html"
OLD = f"{WEB}/weekly_2026-08-22.html"
SEC = f"{GB}/reports/friday_v7/sections"
GF = ["gf_MGC.md", "gf_full_RIDER_ALL.md", "gf_full_UNCLASS.md", "gf_full_OPEN-NEWS.md",
      "gf_full_VACUUM.md", "gf_full_FLOW-LED.md", "gf_chopscalp.md"]
CUT = dt.datetime(2026, 8, 25, 21, 0, tzinfo=dt.UTC).timestamp()


def page(msg: str) -> None:
    try:
        sys.path.insert(0, f"{GB}/src")
        from gazbot7.notify import notify
        notify(msg, critical=True)
    except Exception:
        pass


def main() -> int:
    problems, notes = [], []

    if not os.path.exists(NEW):
        page("⚠⚠ CATCH-UP REPORT: assemble produced NOTHING — weekly_2026-08-21.html is missing. "
             "The old weekly_2026-08-22.html has been LEFT IN PLACE.")
        return 1

    if os.path.getmtime(NEW) < CUT:
        problems.append("the report on disk is OLDER than tonight's run — assemble did not rewrite it")

    html = open(NEW, encoding="utf-8", errors="replace").read()
    h2 = len(re.findall(r"<h2", html))
    tables = len(re.findall(r"<table", html))
    if h2 < 10:
        problems.append(f"only {h2} h2 sections (expected >=10)")
    if tables < 60:
        problems.append(f"only {tables} tables (expected >=60)")
    if "{WEEK}" in html:
        problems.append("literal {WEEK} in the output — the doubled-brace bug is back")

    fresh_gf = [g for g in GF if os.path.exists(f"{SEC}/{g}") and os.path.getmtime(f"{SEC}/{g}") >= CUT]
    notes.append(f"{len(fresh_gf)}/{len(GF)} greenfield clusters rebuilt tonight: "
                 f"{', '.join(g.replace('gf_full_', '').replace('gf_', '').replace('.md', '') for g in fresh_gf) or 'NONE'}")
    if len(fresh_gf) < 4:
        problems.append(f"only {len(fresh_gf)} greenfield clusters are fresh — the point of this run")

    size = os.path.getsize(NEW) / 1024
    notes.append(f"{h2} sections · {tables} tables · {size:.0f}KB")

    if problems:
        page("⚠⚠ CATCH-UP REPORT LANDED BUT FAILED ITS CHECKS:\n  · " + "\n  · ".join(problems)
             + "\n" + "\n".join(notes)
             + f"\nBoth copies kept — open weekly_2026-08-21.html and judge it yourself.")
        return 1

    if os.path.exists(OLD):
        os.replace(OLD, f"{GB}/reports/friday_v7/superseded_weekly_2026-08-22.html")
        notes.append("retired the thin 08-22 copy (moved to reports/friday_v7/, not deleted)")
    page("✅ CATCH-UP REPORT BUILT AND VERIFIED — weekly_2026-08-21.html\n  " + "\n  ".join(notes)
         + "\nIt is the newest on the dashboard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
