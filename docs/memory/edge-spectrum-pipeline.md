---
name: edge-spectrum-pipeline
description: "The full-knob edge-hunting pipeline — capture → derive → DuckDB chop → courtroom confirm; how to run it, status, and the data-starvation caveat"
metadata: 
  node_type: memory
  type: project
  originSessionId: b341af3b-70a2-447b-81c6-5edf2d669ad6
---

The operator's "full capture across the spectrum, choppable, walk-forward the best regions" system
(built 2026-06-19). Design + status: `docs/EDGE_SPECTRUM_SCOPE.md`. Principle: **capture primitives,
derive every knob outcome at query time — never materialise the cartesian product.** Stack: DuckDB-
over-Parquet + vectorised numpy/pandas (this IS the DuckDB case — interactive multi-dim slicing of a
big columnar grid; distinct from the nightly-replay perf fix where DuckDB was correctly declined, see
[[rapid-walkforward-tool]]).

**The loop (each refreshes nightly via `nightly_edge`; all read-only on the trading DB → Parquet):**
```
uv run python scripts/edge_capture.py --validate     # Phase 1: live-gate entries + forward paths → Parquet
uv run python scripts/edge_outcomes.py               # Phase 2: hold×ratchet×stop policy grid → outcomes.parquet
uv run python scripts/edge_chop.py --by gate,side,ratchet_giveback --where "e.side='short'"  # Phase 3: DuckDB slice, ~0.05s
uv run python scripts/edge_courtroom.py              # Phase 4: walk-forward + deflation → CONFIRMED/ACCUMULATING/CONVICTED
```
Store: `data/edge_spectrum/{entries,paths,outcomes,policy_grid}.parquet`. Modules:
`alphabot/intelligence/edge_{capture,outcomes,chop,courtroom}.py`.

**Validated:** capture faithful to the nightly replay (6636/6636, max_abs_diff 0.0); ratchet derivation
mirrors live `profit_ratchet_exit` (0 disagreements); Phase-4 confirm machinery FIRES on synthetic
multi-session data (hold 1.0, beat_luck_p 0.005), reusing the tested `walk_forward`/`beat_luck_pvalue`/
`deflated_sharpe`/`benjamini_hochberg`.

**THE CAVEAT (don't forget):** the live-gate cohort is only ~3 session-dates deep, so Phase 4 returns
**ACCUMULATING everywhere** — correct/honest, NOT a bug. Nothing is tradeable until ~weeks of nightly
accumulation give walk-forward enough OOS sessions. Chop output is IN-SAMPLE exploration only; never
arm a cell straight off the chop (the §283 lock was consciously relaxed for combinations, replaced by
regions-not-points + purged-WF + family-deflation + OOS-survival + the CANDIDATE→CONFIRMED→ARMED ladder).

**5a (5s ratchet bars) DEPLOYED 2026-06-19** — MD daemon already got IBKR reqRealTimeBars (5s); now
persists `timeframe='5s'` to bar_history (14d retention, forward-only). For the ratchet-granularity
study. **5b/5c BUILT** (`capture_granularity_paths` + `ratchet_granularity_study`, `edge_outcomes.py
--granularity-study`): 1m/5s paths with a sub-minute CONTIGUITY GUARD (max_gap 120s — else a pre-feed
entry glues days-later 5s bars on; caught 2685 false coverages → 0). 5m-vs-1m ratchet×give-back compares
NOW; 5s accumulates as the feed banks. **Phase 6 DEPLOYED** — `operator_ui/trading_logic.py` →
`/trading-logic/summary` + the `🎚 TRADING LOGIC` INTEL subtab (live knobs · top regions · ratchet-granularity ·
courtroom verdicts); SIM+GATES subtabs retired (backend dormant). The tab also has a **daily-interrogation
UI** (TODAY/7D/30D window toggle, gate scorecard, give-back/hold/stop sweeps, best/worst regions, lazy
courtroom panel — `/trading-logic/summary?days=N` + `/trading-logic/courtroom`). **PENDING:** 5d (live 5s
ratchet wiring — exit-path, flag-and-wait). **Operator plan (2026-06-19): let data bank ~2 weeks, revisit
5d ~2026-07-03** once the spectrum + 5s feed have OOS depth and the courtroom can actually confirm. Per-entry threshold-superset capture (sweep gates LOOSER than
live) is a Phase-1b extension.

**CONSEC-LOSS COOLDOWN (2026-06-19, "learn to play chop"):** the 06-19 orb_long chop-out (95 flat-clock
cuts, 13% win, −$320) prompted a cooldown idea. Built as a knob/study `scripts/edge_cooldown.py`
(counterfactual + CHOP-vs-TREND lens — cooldown helps in chop, costs trending-day upside; today
3-loss/60min → +$123) + pure helper `alphabot/strategy/loss_cooldown.py` (tested 7/7) + `FUT_LOSS_COOLDOWN_*`
settings (default OFF; per-symbol scope = capacity-safe for the ~12-contract desk; gate-scope would starve
it). **DELIBERATELY NOT WIRED into the entry path** — flipping the flag does nothing yet; entry-path wiring
is flag-and-wait + courtroom-must-justify-first, deferred to arming time. Commit `2811333c`.

**PEAK_DIP + SCALP FOLDED INTO THE SPECTRUM (2026-06-19, commit `100d0fcb`):** peak_dip (the retired
dip-buy) is the operator's chop-scalp idea — buy the oversold dip + ratchet armed IMMEDIATELY (scalp the
bounce) + tight stop. Finding: gross-positive (~80% win) but cost-bound; net-positive only on BIG-notional
contracts (1m: MNQ; 5m: DAX — RESOLUTION-SENSITIVE, which is why 5s matters). NOT dip-depth (deeper dips =
falling knives, worse). Folded in: `edge_capture` captures peak_dip/peak_rip as SHADOW gates (is_live=False,
16,334 entries now); `edge_outcomes` has 12 SCALP policies (activation 0.0001 + tight give-back + tight
trail); courtroom prosecutes peak_dip (ACCUMULATING). Nightly auto-accrues. **Refinement TODO:** courtroom
pools per (gate,side) — the per-CONTRACT scalp edge (MNQ/DAX specifically) needs a per-contract courtroom
slice + finer bars (1m/5s) before it could ever arm. Paper logs $0 commission → cost is MODELLED ($0.50/side
+ tick slippage), so the net verdict is cost-assumption-sensitive — pin real micro cost before trusting it.
