---
name: execution-cost-autopsy-stage1
description: "Stage-1 cost autopsy verdict — the desk bleeds to negative DIRECTION (~80%), not cost; execution polish can't save it. But stop-exit slippage is a real 33% leak, and real fee is $1.50/RT not $5."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9162c01b-c354-41a1-9fc3-162d48ae4678
---

**2026-07-25 — Execution-cost autopsy Stage 1 (P&L waterfall, `scripts/cost_waterfall.py`, reconciles to $0.00 vs live ledger).** Ran to answer: is the desk's bleed DIRECTION (unfixable by execution) or COST (fixable by passive/limit fills)? Scope = `EXECUTION_COST_AUTOPSY_SCOPE.md`.

Live V7 ledger 281 MNQ trades (07-16→07-24), net **−$3,673**. Waterfall: **gross-direction (mid→mid) −$993 naive / −$2,938 robust** · −spread $2,258 · −fee $422.

**DECISIVE: gross-direction is NEGATIVE.** ~80% of the bleed is direction, unfixable by execution. The passive-recoverable ceiling is only **$313 ($1.11/RT), entry-side just $154** — so **Stages 2–4 (passive-entry sim) KILLED, do not build.** You cannot execution-polish a negative-direction desk to green. Corroborates the run-catcher null + arXiv MNQ falsification + OFI null: the desk's problem was never friction, it's negative directional edge on this summer regime.

**Two real fall-outs:**
1. **STOP-EXIT SLIPPAGE ≈ $1,200 = 33% of the bleed** — stops fill 20–34pt THROUGH a mid that was fair 0.1s earlier (flush fills eating vanished liquidity). NOT direction-prediction, NOT passive-entry — a stop-placement/exit-execution problem. Connects to [[naked-position-from-silent-auditor-skip]] (toothless-stop / StopLimitOrder 20pt band) + [[giveback-exit-finding]]. Won't create edge but recovering half slows the bleed. ⚠ some stop slippage is irreducible in a flush; tighter stops trade slippage for whipsaw.
2. **Real fee = $1.50/RT, NOT the $5/RT our backtests assume** (3.3× overcharge on commission). **SCOPE of the error:** the greenfield run-catcher scripts (`afc_*.py`, `grave_*.py`, `full_afc.py`, `full_vacuum.py`) hard-code `FEE=5.0`; the LIVE-gate decision tools (`gate_backtest_tickhonest.py`, `footprint_backtest*.py`) already use the correct `FEE=1.5` — so NO live roster decision was corrupted, only greenfield research. Correction is exactly linear (`net@1.5 = net@5.0 + 3.5×n`): AFC −$27.9k→−$11.4k, trap-reclaim RAW −$2,935→−$674, none FLIP (all killed on fee-independent structural grounds: beta / 0-run-retention / negative buffer / down-week). ⚠ **RULE: don't just swap 5→1.5** — the $5 flat was partly proxying unmodeled stop slippage (~$7/RT beyond touch on the live desk); the correct fix is an ALL-IN cost = touch-cross spread + $1.50 commission + tick-honest stop-slippage, else stop-heavy gates look too good. Verified via re-run at FEE=1.5 ±stop-slippage.

⚠ Honest shadow gap: no shadow set has fill PRICES (`shadow_real_pnl` priceless, V7 `shadow_trades` empty, only the old optimistic `fut_shadow_sim_trades` has prices and its spread is corrupted/price-improving) — so the live ledger is the ONLY honest cost measurement. Small live n (281), one summer regime, MNQ.

**Three live threads left (in promise order):** (1) seconds-OFI confirm/veto as a fakeout FILTER on an already-earning momentum gate (thrust_short) — the one thing that sharpens rather than rescues; (2) stop-slippage reduction (runway, not edge); (3) reactive regime-gating, re-test in a trend week. Links [[run-catcher-null-all-microstructure]] [[desk-green-by-end-august-goal]] [[shadow-sim-understates-losses]].
