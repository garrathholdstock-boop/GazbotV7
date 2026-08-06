---
name: friday-report-judge-on-expectancy-not-winrate
description: Win-rate is NOT a kill criterion on this desk — judge candidates on expectancy + robustness (operator 2026-08-01)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7ee8ed49-da74-4888-8564-7a26b4598a97
  modified: 2026-08-01T08:40:39.747Z
---

**Never kill a signal on win-rate.** Operator, 2026-08-01: *"48% is fine. Wednesday and Thursday our win rate was 40% and we were very profitable. The winners were big."*

**Why:** the desk is built on low-win/big-winner mechanics. Week of 07-27→07-31: **+$625 at a 39% win rate** (80/206); grind won only 32% of its trades but its average winner (+$125) was over double its average loser (−$54). A win-rate filter would bench the desk's actual earners. The measure is **expectancy ($/trade net of costs)**, and the kill criterion is **robustness**: placebo/shuffle test, strip-the-best-trades, leave-one-day-out, OOS leg, parameter plateau-vs-step.

**How to apply:** when a greenfield/rehab candidate dies, the cause of death must name *which robustness test* killed it — never "low win rate". Good worked example from 07-31: FLOWTRAP had the *highest* win rate of the three clusters (48.1%, +$1,460) and was correctly buried on the **placebo test** (a shuffled flow series still booked +$234–598, p≈0.1) plus concentration (strip-top-5 → −$150); meanwhile NIPC survived the skeptic at **43.3%**. Encoded as the `JUDGE` rule in `scripts/friday/friday_phases.py`. Related: [[friday-report-tables-not-charts]], [[three-pass-adversarial-friday]].
