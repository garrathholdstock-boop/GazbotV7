---
name: rapid-walkforward-tool
description: Fast ad-hoc vectorized walk-forward over the futures funnel — run it any time instead of waiting for the nightly pipeline
metadata: 
  node_type: memory
  type: reference
  originSessionId: b341af3b-70a2-447b-81c6-5edf2d669ad6
---

A reusable VECTORIZED walk-forward tool (pandas/numpy — no new dep, no query engine, never writes
the DB) for rapid gate/symbol/side/date edge analysis. Built 2026-06-19 (commit `fe2ebedb`) when
the operator asked for a way to "do rapid walk forwards any time" without the 15-min nightly job.

**Run it (operator on Termius, or the agent in-session):**
```
uv run python scripts/rapid_walkforward.py --days 30                       # all live gates, both sides
uv run python scripts/rapid_walkforward.py --gate orb --side long --symbol MNQ --windows 5,10,20
uv run python scripts/rapid_walkforward.py --validate                      # correctness gate vs nightly
```
Output: per-(gate, side) × horizon table — n, mean/median signed return %, win%, mean MFE/MAE. ~3s
for 6,685 entries × 4 horizons. Horizons are in 5m bars (5/10/20/48 = 25min/50min/100min/4h).

**Module:** `alphabot/intelligence/rapid_walkforward.py` (`walk_forward()`, `summarize()`,
`validate()`). Forward-return semantics MATCH `fut_replay.replay_fut_funnel` EXACTLY (validated:
1462 rows × 13 horizons, max_abs_diff 0.0) — bars are 5m `bar_history` with `bar_ts > cycle_ts`,
exit = H-th forward bar's close. Live gate + stream-symbol resolution reuse `fut_replay` so the
cohort matches the nightly courtroom's. See [[courtroom-vs-live-signal-mismatch]].

**Why it exists / the bigger decision:** the `edge-nightly` 15-min timeout was NOT "SQLite is
slow" — it was a Python row-by-row replay loop (~150k–320k rows/night) + dead work. We deliberately
did NOT adopt DuckDB (over-engineering at 5GB / solo-maintained); the fix was (a) skip retired
crypto + bump the timeout to 3h, (b) this vectorized tool. DuckDB-over-Parquet stays the documented
escalation path ONLY if the data ever outgrows RAM (it won't at this scale).
