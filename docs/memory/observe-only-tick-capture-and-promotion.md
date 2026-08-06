---
name: observe-only-tick-capture-and-promotion
description: 2026-07-01 — enabled 250ms tick capture for the 4 observe-only shadows (M2K/MYM/MCL/MBT) + built promotion-candidates tool; found the observe-only bar-backtests were artifacts (sparse 5s → gappy paths); nothing desk-worthy
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a177229-b370-41db-bb71-2814d3a9582c
---

2026-07-01 (operator: "if we persist the 250ms bid/asks + 5s bars for m2k/mym/mcl/mbt can we then backtest all the gates on all of them... to see if anything is worthy of being put back on the desk"). DID:

**Step 1 — tick capture LIVE:** added M2K,MYM,MCL,MBT to `.env` QUOTE_FAST_SYMBOLS (was MNQ,MES,MGC) + restarted MD daemon → tick_recorder now captures **7 symbols at 250ms**. Spread now MEASURABLE (round-turn $): MCL ~$1.70, MBT ~$1.31, MYM ~$1.02, M2K ~$0.90. NOTE .env is gitignored (secrets) → the change is on the box, NOT in git; re-apply on a fresh .env. Forward-only (no history).

**Built `scripts/promotion_candidates.py`** (+ folded into the Friday report, commit a31f663d): every dormant gate × observe-only contract through the live spine + a SPREAD HAIRCUT from ticks.db; desk-worthy = positive-AFTER-spread + non-fluke (best trade <40% of net) + n≥8.

**KEY FINDING — the observe-only bar-backtests were ARTIFACTS.** The 5s bars for the observe-only contracts are SPARSE (~10% duty cycle) → the exit-spine path has gaps → pairing a funnel entry with a distant bar = garbage P&L (M2K "edge" came out at +$645k). Added a pairing guard (path within 120s + price-match 3%) to `mcl_momentum_sim._run_family`. After the guard: M2K/MYM/MBT can't be evaluated on the sparse bars at all; **the earlier +$20/+$22/+$34 numbers ([[mcl-different-beast-gate-sweep]] gate_edge_transfer_sim) were roll/gap artifacts, NOT real.** MCL (denser 5s) survives → **ALL gates NEGATIVE after spread** (persistence −$92, continuation −$85, reversion −$135). **NONE desk-worthy.**

**VERDICT:** nothing is worthy of the desk on current data. The bar-based observe-only backtest is UNRELIABLE (sparse 5s); the **dense 250ms tick path (now accruing) is the fix** — in a few weeks the spread-aware forward backtest via promotion_candidates + the Friday report will give a trustworthy read. Tools: scripts/promotion_candidates.py, gate_edge_transfer_sim.py, mcl_momentum_sim.py, mcl_orb_sweep.py. Ties to [[mcl-different-beast-gate-sweep]] (ORB +$34 also a fluke), [[golive-drop-mnq-mgc]], [[futures-contract-roll]].

**BUILT the weekly-backtest harness 2026-07-01 (P1+P2+P3, scope docs/OBSERVE_ONLY_WEEKLY_BACKTEST_SCOPE.md):**  — every gate (pullback/dip/persistence/continuation = funnel replay; peak_pullback = FRESH-crossing of the logged pullback feature; ORB = reconstructed, session-anchored) × M2K/MYM/MCL/MBT through the LIVE robust spine, at baseline + WIDE threshold sweeps (feature-filter for funnel gates, param grid for ORB/peak). Spread haircut from 250ms ticks, pairing guard (rejects sparse-bar corruption), fluke checks (concentration<40%, n∈[8,200] so always-in-market gates like raw peak_pullback can’t qualify, plateau/robustness). P2: replaced the promotion section in the Friday report (passive_chop_weekly_report.sh) with the harness — full scorecards+sweep grids archived, verdict+per-contract line to Telegram. P3:  writes baseline per-(contract,gate) net-after-spread to observe_backtest_history.jsonl (dedupe by ISO week) → consecutive-weeks-positive STREAK; a ≥2-week LEAD is the arm trigger. Commits 82cd54f8/4cb74a86/3db96b9d. Week-1 verdict: NONE desk-worthy. TODO P1.5: passive_chop + trend_donch shadow-sim are LIVE-3 only → extend the shadow strategies to the 4 (or reconstruct) so those 2 gates are covered too.
