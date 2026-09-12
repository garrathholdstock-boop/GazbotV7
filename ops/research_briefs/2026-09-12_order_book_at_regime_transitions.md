# Order book at regime transitions

*Brief written 2026-09-11 21:2xZ, relaunched 2026-09-12 after the parent session died 4 minutes in.*

You are a market-microstructure researcher on a solo futures desk ("GAZBOT V7"). Today is 2026-09-11/12 (overnight).

CONTEXT — WHAT IS ALREADY KNOWN, so you do not repeat it:
This desk established today, across five independent methods, that DIRECTION is not predictable from MNQ's own bar data (~0.50 every time). Specifically on the ORDER BOOK, two things were measured and are settled:
- At the START of directional legs, 3-level book depth falls to 0.72x its matched-control level (54 vs 75, t=-12.45) and touch size to 0.79x. Liquidity WITHDRAWS before price moves. But SIGNED imbalance at those moments is ~0.000 with only ~20% agreeing with the leg's direction: THE BOOK SAYS WHEN, NOT WHICH WAY.
- DURING a move, depth/depth-trend/signed-imbalance/touch/spread all sit at 0.462-0.488 P(continue) across terciles, every CI including 0.500 — but on only 610 observations across 19 sessions, which is underpowered.
Do not re-derive those. Your job is the untested part.

YOUR MISSION: the order book AT REGIME TRANSITIONS, and book features this desk has never computed.

A promising new direction emerged tonight: Mesfin (2026) falsified 14 OHLCV signal families on MNQ (gross edge ceiling ~1.5pt vs ~2pt friction) but found two signals that PASSED at t=5.83/5.15, both using REGIME CLASSIFICATION with 60-75 minute holds. A regime-transition strategy has just been built here (scripts/bt_regime_transition.py): a 3-state Gaussian mixture on drift features over 15-min bars, labelling BULLISH/BEARISH/CHOP, entering on clean transitions. It currently produces a gross edge of ~1.7-2.1 points — at the documented ceiling.

The question you are answering: DOES THE ORDER BOOK ADD ANYTHING AT THOSE TRANSITION MOMENTS? The book is not "publicly observable OHLCV" — it is the one data source on this desk that is NOT in the competed-away category Mesfin describes.

DATA:
REPO /home/alphabot/gazbot7 — `.venv/bin/python`, `PYTHONPATH=src`. DuckDB+pandas, read_only=True. NO sklearn.
- data/depth.db — table depth_snap, columns symbol, ts_ms, bid1p/bid1s/ask1p/ask1s ... through at least level 3 (check the schema; levels may go deeper). MNQ and MGC, 2026-08-14 onward, ~5.4M rows MNQ.
  ⚠ HYGIENE, mandatory: ~9% of snapshots are CROSSED or LOCKED (ask1p <= bid1p) — filter them. And there is a documented 19.6-HOUR window where ask1p was FROZEN at 30151.75 across 200,708 consecutive snapshots; exclude any minute where ask1p takes only ONE distinct value.
- B2 has MORE book history than local disk: `rclone lsf b2raw:gazbotv7/plain/tape/book/MNQ/` lists daily parquet back to 2026-07-31, i.e. two weeks earlier than depth.db. Those files are LONG format (symbol, ts_ms, side, level, price, size) with level 0-INDEXED, so `level <= 2` there equals bid1+bid2+bid3 in the wide table. Pulling them roughly doubles your sample — worth doing.
- data/capture.db — bars (filter symbol!), ticks (symbol, ts_ms, price, size, aggressor), quotes (bid/ask/sizes).

FEATURES WORTH BUILDING THAT THIS DESK HAS NEVER COMPUTED:
1. ORDER FLOW IMBALANCE (OFI) — the Cont/Kukanov/Stoikov construction: changes in bid/ask depth at the touch, signed by whether the quote improved, worsened or held. This is a genuinely different object from static book imbalance and is the standard microstructure predictor. The desk has ONE prior hint here: an "OFI delay-VETO on grind" study found grind_long went -$172 to +$772 at a 15-second delay. That was never followed up.
2. TRADE-SIGN IMBALANCE from the ticks table's `aggressor` column — buy-initiated vs sell-initiated volume. Aggressive flow is a different signal from resting depth.
3. DEPTH SLOPE / book shape — how quickly size builds away from the touch, not just the total.
4. QUOTE INTENSITY — updates per second, cancel-to-trade behaviour if inferable.
5. Book features measured in the minutes BEFORE a regime transition versus matched controls.

METHOD RULES — MANDATORY:
- CAUSAL. Every feature uses only data strictly before the decision point. Do not straddle the event: an earlier study here measured book features in a +/-2 minute window around a pivot and could not separate "thin book let price move" from "the move consumed the book".
- MATCHED CONTROLS from the same sessions, never a global average — book depth is strongly session-dependent (overnight ~40, US hours ~80), so comparing to a day-median conflates time-of-day with signal.
- The sample is SMALL (21 local sessions, ~35 with B2). Say so, compute confidence intervals, and do not present an underpowered null as proof of absence. Equally, do not present a single quintile with negative neighbours as a finding — this desk killed four such "islands" today.
- DIRECTION IS THE PRIZE. Magnitude prediction is already solved (P(60pt move) 9% to 77% by ATR/volume). Only a directional result is worth anything.

DELIVERABLE: the features you built, what they show at regime transitions versus controls, whether ANY of them carries directional information, with CIs and an honest statement of statistical power. If the answer is "the book still says when, not which way", that is a clean and useful result — say it plainly. READ-ONLY on all data; write scripts under /tmp.

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
