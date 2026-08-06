---
name: friday-report-tables-not-charts
description: "Friday V7 report: stats as fact-tables, but RUN CHARTS (price path with entry/exit marked) are wanted and loved — operator 2026-08-01"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7ee8ed49-da74-4888-8564-7a26b4598a97
  modified: 2026-08-01T08:41:53.770Z
---

Two different things, and the distinction is the whole point:

- **Statistics → TABLES, not figures.** *"Tables are fine, no charts needed."* He reads this report for money-first verdicts he can act on Saturday; tables carry the numbers he checks. The old `≥15 charts` publish gate in `docs/FRIDAY_V7_REPORT_SCOPE.md` is **RETIRED** — and a proofreader must never flag "no charts" as a defect (the 07-31 proofread burned a gap-fill agent on exactly that).
- **★ RUN CHARTS → yes, and he loves them.** *"Charts are ok for the runs… I love seeing the chart and when we jumped and when we exited."* A price chart of the actual run / case-study session with **entry and exit marked on the path**. That's visual trade review, not decoration — it's how he checks whether the desk showed up in the right place.

**Why:** he judges entries and exits by eye against the move. A table says −$370; the chart says *we bought the top*. Different information.

**How to apply:** put run charts in Movement 1 (the biggest runs, marked caught / fought / sat-out), the Part-1 live-desk case-study days (every gate entry + exit on the day's path), and any greenfield candidate presented with trades. Build inline self-contained SVG from `capture.db` ticks + the REAL fills — never an external image, CDN or JS library (the report is a single self-contained HTML). Don't pad with anything else: MNQ-only at ~80pg with the substance intact is the target; the old ~296pg reports were bigger only because they covered ~10 contracts. Related: [[friday-report-judge-on-expectancy-not-winrate]], [[three-pass-adversarial-friday]], [[friday-report-runs-tonight-maxdepth]].
