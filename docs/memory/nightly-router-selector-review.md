---
name: nightly-router-selector-review
description: "2026-07-28 — nightly post-session router + exit-selector performance review (tools + weekday cron + Friday rollup); the cron is session-only, re-arm on fresh session"
metadata: 
  node_type: memory
  type: project
  originSessionId: 56db3271-178d-477c-8537-702242d72c01
---

**Nightly monitoring of the router + exit-selector (operator 2026-07-28: "monitor each night — was it optimal, did we block adequately, did we miss good trades — fold into Friday for a full-week review").** Two READ-ONLY tools + one weekday cron + a Friday rollup:

- **`scripts/router_nightly.py`** (writes `data/router_nightly/<date>.json`): reprices each `SUPPRESSED-OPEN` the router blocked (tick-honest scalp) → benched-and-lost = GOOD block, benched-and-won = MISSED; NET ROUTER VALUE = losses-saved − wins-missed; + LEAKAGE (managed-gate losers that fired while ON, by regime@entry). Parses the gazbot7-tournament journal (`SUPPRESSED-OPEN: <gate> <side> would open @<px> t=<ms>` — note t is MILLISECONDS). Initial 07-27: net −$81 (capitulation over-benched), leakage −$456 momentum-in-chop (the hole the [[direction-router-live]] momentum-chop veto now plugs).
- **`scripts/selector_nightly.py`** (writes `data/selector_nightly/<date>.json`): reprices each trade under all modes (wide/tight/mid/scalp), recomputes the mode the selector PICKED (`SlotStrategy._regime_mode`, no drift) → % optimal picks, REGRET ($ vs best-of-3), selector-vs-fixed. 07-27: 53% optimal, +$1342 regret, selector +$671 vs always-scalp (~tied always-wide on that trend day); worst = WIDE-in-violence whipsaws + TIGHT-on-runners ([[exit-selector-regime-live]]).
- **Cron** (`CronCreate`, `50 22 * * 1-5` = weekday 22:50 UTC, just after the 22:00 Paris-day roll → reviews the just-closed day): runs BOTH, reports in-session, Telegrams only if notable. **⚠ SESSION-ONLY (dies on session restart) — RE-ARM on a fresh session** (like the other maintenance crons).
- **Friday**: `friday_v7_maxdepth.workflow.js` `part25:musings` rolls up the week's dated ledgers (ROUTER net value/leakage trend + SELECTOR optimal%/regret trend + systematic patterns) → then `router_study.py` optimises off it. Scope: `FRIDAY_V7_REPORT_SCOPE.md` Part 2.5.

⚠ Both are tick-honest ESTIMATES — benched trades + non-chosen exit modes never actually ran. gazbot7 commits `1607e0b` (router), `4f38de8` (selector), `d1240d0` (Friday).
