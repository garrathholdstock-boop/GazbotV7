# Optimise regime transition strategy

*Brief written 2026-09-11 21:2xZ, relaunched 2026-09-12 after the parent session died 4 minutes in.*

You are a quantitative researcher on a solo futures desk ("GAZBOT V7"). Work independently and report a rigorous, honest result. Today is 2026-09-11/12 (overnight session).

REPO /home/alphabot/gazbot7 — `.venv/bin/python`, `PYTHONPATH=src`. DuckDB+pandas. DBs read_only=True. NO sklearn on this box (a hand-rolled diagonal-covariance GMM via EM is already written for you).

YOUR STARTING POINT — read and build on this file:
  scripts/bt_regime_transition.py
It fits a 3-state Gaussian mixture on DRIFT features (signed 4/8-bar move in ATR units, plus efficiency ratios) over 15-minute MNQ bars, labels states BULLISH/BEARISH/CHOP by their own statistics, enters on a clean state TRANSITION at the next bar's open, and exits on a FIXED HOLD with no target and no stop. Chronological TRAIN(40%)/VALIDATE(30%)/TEST(30%) split; the GMM is fitted on TRAIN ONLY and applied unchanged to the other two.

Current result (2pt friction): best cells are 60-min hold at -0.28 net and 90-min hold at +0.07 net, i.e. GROSS edge of roughly +1.7 to +2.1 points.

WHY THIS SHAPE: Mesfin (2026), "Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures", falsified 14 signal families on 947 days of MNQ and found a GROSS EDGE CEILING of ~1.05-1.50 points against ~2pt friction — every family failed. But two signals PASSED (t=5.83 and t=5.15, Sharpe 5.09) and both shared one property: REGIME CLASSIFICATION with 60-75 minute holds (12-15 bars) rather than single-bar prediction. His explanation: friction is paid once, so a persistent regime lets the edge accumulate above a fixed cost. Duration is the escape, not a better predictor.

★★★ YOUR FIRST TASK — THE FRICTION NUMBER IS WRONG FOR THIS DESK. Mesfin's 2.0 points is a conservative generic assumption. This desk's MEASURED costs are: $1.50 commission per contract per round turn (= 0.75 points at $2/pt), plus MNQ's median bid-ask spread of 0.50 points (verified on 6.65M quote records) crossed ONCE per round trip. So realistic friction is about 1.25 points, not 2.0. An L2 ladder walk on 18,692 captured depth snapshots showed a real 4-lot MNQ market order costs about $0.43 in impact — negligible. RE-RUN EVERYTHING AT REALISTIC FRICTION and report a sensitivity curve across 0.75 / 1.0 / 1.25 / 1.5 / 2.0 points so the operator can see exactly where it crosses zero.

THEN OPTIMISE, RIGOROUSLY:
1. Bar size: 5, 10, 15, 30 minutes. Mesfin's winners used 5-min and 15-min bars.
2. State count: 3, 4, 5. More states may isolate a cleaner drift regime.
3. Hold length: sweep 30 to 180 minutes.
4. Feature set: try adding/removing features. Candidates — signed drift in ATR units over several lookbacks, efficiency ratio, realised vol ratio (short/long), volume z-score, position in the session range. Report which features the states actually separate on.
5. Entry refinement: Mesfin's London Signal B required a CLEAN transition with no contamination by the target state in the prior 2 bars. His RTH Confluence added a Markov transition-probability threshold (rolling 200-bar P(move to target state) > 0.15) and a volume z filter, and entered on an ATR-scaled PULLBACK rather than at market. Test these.
6. Session restriction: his Signal B was London-session only (03:00-08:30 ET = 08:00-13:30 UTC). The CME day here runs 22:00Z-21:00Z. Test session sub-windows.
7. Exit: fixed time is the baseline. Also test exiting on the state REVERTING to chop, and a time cap combined with that.

METHOD RULES — THESE ARE NOT OPTIONAL:
- FIT ON TRAIN ONLY. The GMM must never see VALIDATE or TEST. Refitting on all data relabels history with hindsight; this desk once manufactured a z=4-6 finding exactly that way (see src/gazbot7/sessionmap.py's warning about Viterbi/smoothed labelling — 64% of "breaks" did not exist in real time).
- ENTRY IS THE NEXT BAR'S OPEN. Never a price inside the signal bar, never a level that already passed. Two separate analyses today produced spectacular results (t=8.99, $287/trade) purely from this error.
- REPORT ALL THREE PERIODS for every cell, never just the aggregate. Today's single most repeated failure was a rule positive on the whole sample and negative on TRAIN.
- COUNT YOUR CELLS. State how many configurations you tested and how many would be expected to pass by chance. ~430 exit configurations were tested today and 3 survived three-period checks — about what noise produces.
- A CONTROL IS SUPPOSED TO LOSE. Include a random-entry control with the same hold and friction, and a buy-and-hold control.

DELIVERABLE: the friction sensitivity curve, the optimisation results with all three periods shown, an explicit statement of how many cells you searched, and a plain verdict on whether ANY configuration clears realistic friction stably across all three periods. If nothing does, say so and report the best gross edge achieved and how far short it falls. An honest null is a real result here. READ-ONLY on all data; you may write new scripts under /tmp.

=== ADDENDUM 2026-09-12, WRITTEN AFTER YOUR PROMPT WAS FIRST DRAFTED — READ IT, IT CHANGES THE BRIEF ===
Your original launch died with its parent session at 21:25Z on 09-11, ~4 minutes in. Nothing you
wrote then survives; start clean. Two results landed after you were written:

1. `scripts/bt_regime_transition.py` now takes `--friction` and `--shuffle`. Re-run at THIS DESK'S
   measured cost (1.25pt = $1.50/RT + one 0.25pt tick crossed, NOT the paper's 2.0pt):
   9 of 12 cells turn positive (90m clean +0.82pt = +$1.64/trade; 60m clean +0.47pt).
2. ★ BUT THE CONTROL GAP IS FRICTION-INVARIANT. Real and shuffled both pay the same fee, so
   cutting friction moves BOTH by the same amount and cannot rescue a cell against its own
   control. Real beats the permuted-label control in 11 of 12 cells, but the control's spread is
   2-3pt, only ONE cell clears a single sd, and EVERY t-stat is below 1.0. The permutation
   control is also coarse: 3 states give only 5 non-identity label arrangements, and permuting
   moves CHOP onto a drift state, which changes the entry population too.

SO THE BAR FOR YOU IS: any cell you report must (a) beat zero at 1.25pt friction, (b) beat its own
shuffled twin by more than the control's spread, and (c) survive a DAY-BLOCK bootstrap CI that
excludes zero. A cell that only does (a) is not a finding. Build a better control than the 5-way
permutation if you can - block-bootstrap the label sequence, or randomise within session.

MEMORY: the box is 7.5GB with a history of global_oom kills that have taken down the desk itself.
Run anything heavy under `systemd-run --scope -q -p MemoryMax=900M --setenv=HOME=/root ...`,
process day-by-day rather than loading a year, and never hold two full tapes in memory at once.
FINAL REPORT: one written verdict - LIVE / SHADOW / PARKED / REFUTED - with the named test that
decided it, and the numbers behind it. Write your artifacts to reports/regime_2026-09-12/ so the
result survives your process. A result that exists only in your reply is a result we lose again.
