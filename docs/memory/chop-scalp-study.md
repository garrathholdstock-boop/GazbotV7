---
name: chop-scalp-study
description: "Operator's chop-scalp hypothesis SCOPED (study-first, NOT armed) — chop-gated multi-leg reversal shapes + ratchet-on-first-profit; needs rapid bars (Mon 06-22); revisit 2026-06-27"
metadata: 
  node_type: memory
  type: project
  originSessionId: b98efc3a-63db-4236-bd2a-69cc1a89a6f2
---

Operator idea (2026-06-20), SCOPED → `docs/CHOP_SCALP_STUDY_SCOPE.md`. **Study-first, NOT armed.**

**Hypothesis:** trade chop on PURPOSE instead of being chopped up. In recognised chop, enter on a **multi-leg reversal shape** (N down-legs → turn up = LONG; N up-legs → turn down = SHORT) and exit on **ratchet-on-first-profit (activation ≈0) + 25% give-back**. Directly targets the desk's #1 bleed (every day last week = never-green entries in the chop/lull — see [[nightly-self-analysis-and-tell-me-how]]).

**Operator's hard requirement:** NOT a toy 1-bar-up/1-bar-down — analyse the **week's ROLLERCOASTER** (the real multi-leg intraweek oscillation) on the rapid bars. Shape space = the 2–4 × 2–4 down/up burst-leg grid (and deeper).

**Maps to existing parts:** regime chop labeler + the BURST leg-shape family (`BurstSpec`/`build_burst_grid`/`mb_long`/`mb_short` — the down-up/up-down grid the courtroom already prosecutes) + `profit_ratchet` activation≈0 (gated on the ratchet re-arm fix `fix/ratchet-bar-seed`). Tie to [[edge-spectrum-pipeline]].

**Data dependency:** needs the **5s/250ms rapid bars** — the market-data plane P0 arms **Monday 2026-06-22**; a full week banks Mon→Fri. 1m is too coarse (a 06-19 ad-hoc 1m scan produced garbage gross/cost — the overfitting trap; that's WHY we use the courtroom, not eyeballed one-day scans).

**Method (no shortcuts):** edge-spectrum policy (chop-gate × reversal-shape grid × ratchet-first-profit) → nightly courtroom cost-adjusted walk-forward → confirm OOS → THEN arm (operator+courtroom gated). 

**Priors lean AGAINST (bar is high):** generic burst shapes came back ~edgeless live (+0.0096%/48%); `peak_dip` was the worst live long gate and `peak_pullback` was dropped from `FUT_ENTRY_GATES` for bleeding (see [[continuation-entry-status]]); cost cliff = net-positive only on big-notional (MNQ/DAX). The study must beat that, or we honestly don't trade it.

**CRUCIAL REFINEMENT (operator Q 2026-06-20, "what do HFT market-makers do in chop?"):** chop is the HFT
market-maker's PARADISE — they earn the spread on two-way flow and the range flattens their inventory; IN CALM
CHOP **the MMs ARE the mean-reversion** (they damp every tick in microseconds, as core business). So fading
calm chop = trying to out-revert the inventors of reverting, slower — likely WHY our chop scalp bleeds; the
premium is already swept tick-by-tick before our 5s bar prints. **Our space is NOT calm chop — it's STRESSED
chop:** moments a burst overwhelms MM inventory limits → they flinch (widen/pull back/stop damping) → range
breaks → price OVERSHOOTS → the slow snap-back as their capacity returns is ours (the thin/fragile-liquidity
moment OFI flags). So the hypothesis sharpens: NOT "fade every wiggle" — "fade the moments chop gets stressed
enough that the MMs blink," AND make the hard Information-vs-Exhaustion call (overshoot to fade vs genuine
breakout that buries you). Small-player angle: the MICROS get less HFT attention than full-size ES/NQ → more
residual left in our corner (but wider spreads = higher cost toll). Ties the pressure/footprint taxonomy in
docs/MONDAY_CLEAN_CAPTURE_SCOPE.md + [[strategy-layer-reframe]].

**CADENCE: revisit/discuss NEXT WEEKEND (Sat 2026-06-27)** after the week of rapid bars banks — analyse which reversal structures, in which chop windows, on which contracts, cleared cost OOS.

---
## NORTH STAR: the GATE CUBE (operator 2026-06-20) → `docs/GATE_CUBE_SCOPE.md`
The grid work is really building toward a **data-lake / OLAP cube**: every measurement on every cycle banked permanently, + a "pose ANY gate → instant walk-forward on data we already hold" interface. "Google a Swedish desk's gate, test it in seconds." DuckDB-over-Parquet (the cube engine) + `rapid_walkforward` (the kernel) already exist — gaps = (1) feature-COMPLETE lake (ORB/density/microstructure per cycle, not just VWAP/RVOL/ATR), (2) the gate-predicate→walk-forward interface (CLI→endpoint→a "test a gate" box on the PIN'd dashboard). Honesty: the cube gives INSTANT in-sample/quick-walk-forward ("would it have worked?"); the COURTROOM still confirms real edge over OOS folds. Build LAKE-FIRST; the entry-grid below is the cube's first content.

## THE GRID MUST INCLUDE ENTRIES — not just exits (operator 2026-06-20, emphatic — the big one)
The edge-spectrum grid today is **EXIT-ONLY** (348 policies: hold/flat-clock/trail/ratchet; `edge_outcomes.default_grid`). Operator: that's the wrong half — **"our gates let lots of shit entries in"** (matches the nightly verdict: ENTRIES every day). **The grid needs the ENTRY-GATE THRESHOLDS swept across their ranges** + ALL the granular measurements, so we can find the right cutoffs: VWAP-dist (~0.5→8.0), RVOL floors, ATR band, **ORB**, density/net_atr, + everything we capture. Full **ENTRIES × EXITS** grid; entries are the priority. Goal: "get in early at the bottom/top, ratchet sells at the right moment."
- **Data: mostly already banked** — `fut_signal_funnel` has per-cycle `vwap_dist_pct, atr_pct, rvol` across 1.34M cycles + `fut_edge_observations` forward returns → sweepable NOW (no recapture) for VWAP/RVOL/ATR. **Density / ORB / net_atr / the richer measurements need a capture addition.** With the rapid 5s/250ms bars (Mon) the entry-TIMING gets fine forward paths → prosecute the turn hard.
- **Scale discipline:** entry-cartesian × exit-cartesian explodes → STAGED: sweep entry thresholds → find the paying entry REGIONS → cross survivors with the exit grid → courtroom-confirm. (His "money sits in regions, trim the rest" applied to entries.)
- **Adaptive ratchet (operator):** start the give-back loose (~50–60%) and **tighten on a SMOOTH curve as profit climbs** — make that curve a swept knob in the grid (the `("linear",...)`/`("step",...)` ratchet specs already hint at it; widen + sweep). Pairs with ratchet-on-first-profit.

## DOSSIER GATE/REGIME "—" — a CAPTURE GAP, not a UI bug (operator 2026-06-20)
The `/day` trade dossier shows gate/regime as "—" for most trades. Diagnosed: NOT a render bug (it shows correctly when present, e.g. trade 3820=orb_long/bear). **`trades.entry_gate` is NULL on ~88% of recent trades**, and the live §284 stamp (`decision.reason→entry_gate`) NEVER records `vwap_dip` (the primary live gate) — only orb/pullback. BUT the funnel HAS it: `fut_edge_observations.live_entry_gate` carries vwap_dip/orb/vwap_pullback per cycle (joinable by `instrument_canonical`+`opened_at`≈`cycle_ts` — trades has NO con_id, use canonical+time). **FIX (not built — stopped):** (a) quick — reconstruct the gate from the funnel in the dossier/ledger when entry_gate NULL; (b) root — fix the live stamp so trades.entry_gate is reliably populated incl vwap_dip (going-forward; matters doubly for the entry-grid above).
