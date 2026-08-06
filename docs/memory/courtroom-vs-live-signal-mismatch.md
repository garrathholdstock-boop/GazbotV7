---
name: courtroom-vs-live-signal-mismatch
description: "The futures courtroom prosecutes footprint defendants, not the live momentum-burst signal — they measure different things"
metadata: 
  node_type: memory
  type: project
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

**Core defect (historical):** the futures courtroom (`fut_courtroom.py`) keyed its exit-family
cohorts to the momentum-burst SHADOW (`mb_long`/`mb_short` in `fut_edge_observations`) — a
never-traded shadow signal — NOT the LIVE entry gates the desk actually runs
(`FUT_ENTRY_GATES = vwap_dip, orb, vwap_pullback`). So those families prosecuted a population the
desk never trades.

**The fix foundation is now in place (2026-06-19):**
- Live trades carry `trades.entry_gate` (the §283 entry→gate stamp, migration 101, schema 101) — powers the live-trade gate scorecard.
- `fut_edge_observations` now carries `live_entry_gate` (migration 102, schema 102), populated by `fut_replay` from the funnel `action`+`reason` (reason prefix → gate: `vwap_dip`/`orb`/`pullback`→`vwap_pullback`; non-gate reasons like `above_vwap`/`peak_*`/`momentum_*`/`trend_continuation` → NULL).

**DONE + DEPLOYED:** the **flat-clock 2-axis (time×band) defendant** is re-pointed to
`live_entry_gate IS NOT NULL`, side from the funnel `action`, sliced per-gate + pooled (commit
`737a89d2`). Backfill tagged 5,692 live-gate entries (vwap_dip 3004 / orb 1601 / vwap_pullback 1087);
verdicts currently all ACCUMULATING (correct — data-starved on the right cohort).

**STILL PENDING the same re-point (follow-up):** `build_hold_grid`/`prosecute_hold_all` (hold-time),
`prosecute_burst_all` (burst), and `fut_exit_sweep.py` (the live exit-sentence applier) all still key
on `mb_*`. Re-point each onto `live_entry_gate` the same way. See [[futures-contract-roll]] for the
unrelated pre-existing `test_y_fut_sim1` roll failure.
