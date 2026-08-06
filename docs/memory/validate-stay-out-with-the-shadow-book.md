---
name: validate-stay-out-with-the-shadow-book
description: "To test a stay-out call, sum today's shadow book — it is the clean counterfactual for the benched gates, and a real ER/ATR break can still be untradeable."
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-03T20:07:09.223Z
---

**The technique.** When the router benches everything and you want to know whether it was right, don't argue from the tape — **sum the shadow book for that day**. Those variants are the benched mechanisms running unmanaged at 1 lot, so their total is what arming would roughly have produced. It converts "should we be in?" from a judgement into a measurement.

2026-08-03 was the case that proved it. The day netted **+303pt on a 624pt range** and the untradeable meter read **37/TRADEABLE**, so being flat all day looked like a mistake. The shadow book: **18 of 19 variants red, −$2,586.50 total**. `grind_fast` −$896 on 72 fires, `capit_loose` −$456, `thrust_aligned` −$228; only `rg_long_fast_v` was green. Day Kaufman ER **0.04** — roughly 7,500pt of travel to deliver 303pt of net. A big net move assembled from a path nothing can hold a position through.

Treat the shadow total as a **floor**: shadow runs 1 lot against the live desk's 2, and live losses run 1.1–3.1× modelled ([[shadow-sim-understates-losses]]).

**★ A break can pass the ER/ATR test and still be untradeable.** My `er_expansion_watch.py` fired legitimately at 14:45 — ER30 ≥ 0.35 held ten consecutive minutes, ATR ~20, directional progress 0.72–0.84 — and I told the operator aligned longs were arguable. The shadow book says arming there would still have lost: `grind_fast` and `thrust_aligned` were bleeding straight through that window. So the trigger answers "is this a break", not "is this tradeable". It should print the day's shadow P&L alongside every fire so the signal arrives with its own counterexample.

**The meter has two blind spots**, both seen this day: (1) its roundtrip term is `|net|/range`, which reads *direction* where Kaufman ER reads *chop* — on a wide-range low-efficiency day it under-scores the danger (it called 47 and 56 on two CAUTION days that both lost, and 37 on this one); (2) it is day-cumulative, so late in a session it reports a tape that has already finished — at 19:36, ATR was 9pt and ER30 0.061 while the meter still said 37. The router overriding it is the judgement layer working, but that means the 40/40/20 blend is being carried rather than doing its job. Related: [[shadow-board-as-regime-router]], [[some-days-stay-out-fully-flat]], [[low-vol-grind-untradeable-stay-flat]].
