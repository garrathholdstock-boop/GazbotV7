---
name: shorts-arming-inversion
description: Futures shorts were armed at the gate but the SELL-to-open path was never built → every SHORT traded as a LONG. Shorts now DISARMED; do not re-arm without the full checklist.
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

2026-06-16 forensic — the desk's #1 CRITICAL bug. On 2026-06-15 shorts were "armed"
by adding both futures disciplines to `_LONG_SHORT_DISCIPLINES` (direction_policy.py),
so the gate emitted SHORT verdicts. But the **execution path was never taught to sell-to-open**:
both submitters (`make_submit_open_fn` in eurex_daytrade.py / us_futures_daytrade.py) build
a BUY-only bracket and never read `plan.is_short`; `EntryIntent` has no side field and
`broker_client.py:708` hardcodes `side=BUY`. Result: every emitted SHORT was placed as a
LONG bracket — **the desk traded the exact opposite of its signal** (72% of that day's entry
BUYs fired on a SHORT verdict; verified by cross-referencing `fut_signal_funnel.action` against
`orders.side` at the same second).

**Fixed (commit abd95ac5):** shorts DISARMED at the gate (`_LONG_SHORT_DISCIPLINES = frozenset()`
→ both disciplines LONG_ONLY) + a defence-in-depth RAISE guard in both submitters (a SHORT plan
raises instead of inverting). Locked by `tests/test_direction_inversion_safety.py`.

**DO NOT re-arm shorts** until the real SELL-to-open path exists. RE-ARM CHECKLIST (also in
direction_policy.py): (1) `EntryIntent` carries a side; (2) both submitters branch on `is_short`
(SELL parent, stop ABOVE / TP BELOW, LMT buffered DOWN); (3) the long-only RAISE guard is removed;
(4) reconcile/B5 are direction-policy-aware (reconcile.py still assumes long-only — forensic #6);
(5) tests prove a SHORT plan places a SELL-to-open with mirror-correct geometry. That build is
forensic item **#1b** (the proper fix); this is the safe #1a holding state.

Cross-cutting lesson: "shorts armed" was a half-wiring across THREE subsystems (gate ✓, submit ✗,
reconcile ✗) — one policy flag, three unsynchronized consumers. Related: [[estx50-fesx-short-tangle]].
Also note: the broker **kill switch** (blocks BUYs) is load-bearing while entries are paused; lift via
`POST /broker/resume`. Significant PRE-EXISTING test rot exists (gate rewrite 06-15, minimal-sizing
06-14, micros-only 06-16) — ~70 failing tests unrelated to the direction fix, to be cleaned per area.
