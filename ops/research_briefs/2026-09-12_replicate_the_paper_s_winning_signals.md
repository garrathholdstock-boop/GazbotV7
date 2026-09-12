# Replicate the paper's winning signals

*Brief written 2026-09-11 21:2xZ, relaunched 2026-09-12 after the parent session died 4 minutes in.*

You are a quantitative researcher on a solo futures desk ("GAZBOT V7"). Today is 2026-09-11/12 (overnight).

YOUR MISSION: attempt a faithful REPLICATION of the two signals that PASSED in Mesfin (2026), "Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study" (arxiv.org/pdf/2605.04004), on this desk's own MNQ data. Fetch the paper yourself for the details — WebFetch returns it as a PDF you can then Read with the `pages` parameter (WebFetch alone returns unparsed binary).

THE TWO SIGNALS, as described in the paper:

1. RTH CONFLUENCE SIGNAL (ATR-adaptive). Fires when three conditions hold simultaneously on a completed FIVE-MINUTE bar: (a) the GMM regime label equals Regime 1 ("Active Flow"); (b) the rolling 200-bar Markov transition probability to Regime 2 exceeds 0.15; (c) the rolling 50-bar volume z-score exceeds 0.5. Entry is on a 25-point ATR-scaled PULLBACK from the signal bar's close. Exit at bar 13 (65 minutes).
   Reported: 538 in-sample signals, +15.77 pts mean net at horizon 13, t=5.83, 61.0% win, walk-forward OOS t=3.11 on 196 trades, +11.82 pts OOS mean, permutation p<0.001.

2. LONDON SESSION SIGNAL B (R0 to R2 transition). Fires when a GMM regime classifier on FIFTEEN-MINUTE London-session bars (03:00-08:30 ET) detects a clean transition from Regime 0 ("Bearish Chop") to Regime 2 ("Bullish Drift") with NO Regime 1 contamination in the prior two bars. Entry is LONG at the next 15-minute bar's open. Exit 60 minutes later or at 08:30 ET, whichever comes first.
   Reported: 289 trades, +5.77 pts mean net, t=5.15, 64.7% win, profit factor 2.42, Sharpe 5.09, permutation p<0.001, parameter-sensitivity t=3.87-4.83 across variations. Critically: delaying entry by ONE BAR destroys it (t drops from +5.15 to -3.56).

DATA AND TOOLS:
REPO /home/alphabot/gazbot7 — `.venv/bin/python`, `PYTHONPATH=src`. DuckDB+pandas, read_only=True.
- data/backfill/MNQ_*_1min.parquet — the lake, ~240 CME sessions of 1-minute bars. Pick the front month PER DATE by volume (the files overlap across contract expiries and a naive union double-counts; there is also a documented dedup defect where 12 of 291 days carry the expiring contract with 118-289pt level errors).
- A working hand-rolled diagonal-covariance GMM (EM, numpy) already exists in scripts/bt_regime_transition.py — reuse it. THERE IS NO SKLEARN on this box.
- Aggregate 1-minute bars up to 5-min and 15-min yourself.

★ NOTE THE TIMEZONE CAREFULLY. The paper uses ET. This desk works in UTC. 03:00-08:30 ET is 08:00-13:30 UTC in summer (EDT, UTC-4) and 08:00-13:30 UTC differs in winter (EST, UTC-5) — the sample spans both, so handle the DST boundary explicitly rather than assuming a fixed offset. Getting this wrong would test a different session entirely. (A related DST bug on this desk mis-anchored 47.5% of the sessions in another study.)

METHOD RULES:
- Friction: the paper uses 2.0 points round-trip. ALSO report at this desk's measured cost — $1.50/contract commission (0.75pt) plus MNQ's median 0.50pt spread crossed once = ~1.25pt.
- Entry at the NEXT bar's open. Never a price inside the signal bar.
- Chronological TRAIN/VALIDATE/TEST split (40/30/30). Fit the GMM on TRAIN only, apply unchanged.
- Report all three periods separately for every result.
- Run the paper's own robustness checks: the 1-bar-delay test (should destroy Signal B if you have replicated it correctly — that is your strongest evidence of a faithful replication), and a permutation test.

WHAT MATTERS MOST: a faithful replication that FAILS is as valuable as one that succeeds — it would tell the operator whether the paper's positive controls survive on a different data vendor and a different sample period, or whether they were specific to that author's data. Note that the paper's sample is Dec 2021-Aug 2025 and this desk's lake covers roughly Sep 2025-Sep 2026, so this is a genuine out-of-sample period for both signals.

DELIVERABLE: for each signal — whether you could construct it, how closely your construction matches the description, the results across all three periods at both friction levels, the 1-bar-delay check, and a plain verdict on whether it replicates. Be explicit about every place you had to guess at an unstated detail. READ-ONLY on data; write scripts under /tmp.

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
