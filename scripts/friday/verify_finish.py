#!/usr/bin/env python3
"""Post-run gate for the 2026-08-29 completion of the 08-28 report. ARTIFACT, never the exit code.

The 08-28 run exited non-zero having published a real 1,250KB report — and the 08-21 run exited 0
having built 4 of 13. Neither exit code told the truth, so this reads what is on disk.

★ IT CAN ONLY IMPROVE THINGS. A partial backup is kept at reports/friday_v7/weekly_2026-08-28.partial-backup.html
  and this RESTORES it if the rebuild came out worse (fewer sections/tables) or missing — because
  --force overwrites the published report, and a completion run that ends up thinner than what it
  replaced is a regression, not a completion.
"""
import datetime as dt, os, re, sys

GB = "/home/alphabot/gazbot7"
REP = f"{GB}/src/gazbot7/web_static/weekly_2026-08-28.html"
BAK = f"{GB}/reports/friday_v7/weekly_2026-08-28.partial-backup.html"
SEC = f"{GB}/reports/friday_v7/sections"
CUT = dt.datetime(2026, 8, 29, 7, 0, tzinfo=dt.UTC).timestamp()
WANT = ["part1_live.html", "part1_6_day_rider.html", "part2_shadow.html", "part25_musings.html",
        "part2_6_router_review.html", "part1_5_rehab.html", "movement2_idle_gates.html",
        "gf_MGC.md", "gf_chopscalp.md", "movement3_greenfield.html", "run_charts.html"]


def page(m):
    try:
        sys.path.insert(0, f"{GB}/src")
        from gazbot7.notify import notify
        notify(m, critical=True)
    except Exception:
        pass


def stats(path):
    if not os.path.exists(path):
        return None
    h = open(path, encoding="utf-8", errors="replace").read()
    return {"h2": len(re.findall(r"<h2", h)), "tables": len(re.findall(r"<table", h)),
            "kb": os.path.getsize(path) // 1024}


def main() -> int:
    new, old = stats(REP), stats(BAK)
    if new is None:
        if old:
            os.replace(BAK, REP)
            page("⚠⚠ COMPLETION RUN produced NO report — the partial 08-28 report has been RESTORED. "
                 "Nothing lost, but the rebuild failed.")
        return 1
    if old and (new["h2"] < old["h2"] or new["tables"] < old["tables"] * 0.9):
        os.replace(BAK, REP)
        page(f"⚠⚠ COMPLETION RUN CAME OUT THINNER — {new['h2']}h2/{new['tables']}t vs the partial's "
             f"{old['h2']}h2/{old['tables']}t. The partial has been RESTORED. Investigate before re-running.")
        return 1
    fresh = [w for w in WANT if os.path.exists(f"{SEC}/{w}") and os.path.getmtime(f"{SEC}/{w}") >= CUT]
    tail = [t for t in ("proofread.json", "rev2_done.txt", "final_check.txt")
            if os.path.exists(f"{SEC}/{t}") and os.path.getmtime(f"{SEC}/{t}") >= CUT]
    ok = len(fresh) >= 9 and len(tail) == 3
    page(("✅ 08-28 REPORT COMPLETED — " if ok else "⚠ 08-28 report rebuilt but INCOMPLETE — ")
         + f"{new['h2']} sections · {new['tables']} tables · {new['kb']}KB · "
         + f"{len(fresh)}/{len(WANT)} sections rebuilt · tail {len(tail)}/3 "
         + f"({'assemble+proofread+rev2+final all fresh' if len(tail)==3 else 'TAIL SHORT'})"
         + (f"\nWas: {old['h2']}h2/{old['tables']}t/{old['kb']}KB" if old else ""))
    if ok and os.path.exists(BAK):
        os.remove(BAK)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
