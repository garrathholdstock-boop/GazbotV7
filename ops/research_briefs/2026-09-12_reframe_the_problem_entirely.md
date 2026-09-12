# Reframe the problem entirely

*Brief written 2026-09-11 21:2xZ, relaunched 2026-09-12 after the parent session died 4 minutes in.*

You are a senior quantitative strategist brought in to REFRAME a problem, not to run another parameter sweep. Today is 2026-09-11/12 (overnight). The operator's instruction was: "keep thinking outside the square and come up with something."

THE SITUATION — and everything below is established, so do NOT re-derive any of it:
A solo operator trades MNQ futures intraday, ~$30k, 1-4 lots, flat overnight by standing rule. One day of rigorous testing established:
- DIRECTION is unpredictable from MNQ's own data. Five methods, all ~0.50: break-then-join (24 cells, 0.469-0.506), book imbalance at leg starts (~0.000, 20% agreement), a 150-cell volume grid (held-out: the filter adds +0.001), a drift detector across 22 configurations (50.0% win exactly), book thinning (lost to its own control out-of-sample).
- MAGNITUDE is strongly predictable. P(60pt move in the next hour): 9% when ATR is low, 77% when ATR and volume are both high. Day-clustered t=15.04 over 237 sessions, holds on 88% of them. Volume adds ~3-12pp over ATR alone.
- ~430 exit configurations tested across three chronological periods; 3 survived, which is what chance yields at that grid size. Exits cannot fix a coin-flip entry: a symmetric outcome distribution has zero mean regardless of where you cut it.
- Mesfin (2026) independently falsified 14 OHLCV signal families on 947 days of MNQ: a GROSS EDGE CEILING of ~1.05-1.50 points against ~2pt friction, because "any price pattern visible to everyone that reliably predicts the next bar gets traded away." Two signals passed (t=5.83, 5.15) and both used REGIME CLASSIFICATION with 60-75 minute holds.
- The desk's real friction is ~1.25 points: $1.50/contract commission (0.75pt) plus a 0.50pt median spread crossed once.
- A regime-transition strategy built tonight reaches a gross edge of ~1.7-2.1 points — at the ceiling.

Other agents are already working on: optimising that regime strategy at realistic friction; replicating Mesfin's two winning signals; cross-instrument and session-handoff lead-lag; order-flow/OFI microstructure at regime transitions; and a literature review of what works at retail scale. DO NOT DUPLICATE THOSE.

YOUR JOB IS DIFFERENT. Question the frame itself. Some directions worth considering, but generate your own too:

1. IS "PREDICT DIRECTION, TAKE A POSITION" THE ONLY GAME? A forecastable magnitude with unforecastable sign is a VOLATILITY view, not a directional one. Options are the textbook answer and are being researched separately — but what else monetises variance? Think about: strategies whose P&L is a function of realised path rather than net displacement; execution-side edges (providing liquidity rather than taking it, given this desk pays the spread on every trade and its own data shows entries at the touch 66.7% of the time); capturing the spread instead of paying it.
2. THE ASYMMETRY THAT ACTUALLY EXISTS ON THIS DESK. Its own record shows the operator's MANUAL exits beat the machine by +$65.70/lot (n=80, t=2.28), and the mechanism was decomposed as pure LOSS-CUTTING (+$10,718 saved on positions the machine would have lost, -$2,663 given up on winners). Meanwhile his ENTRIES are worse than random (41% went his way first). Is there a design where the machine does entry and the human does nothing — or where the human's one demonstrated skill is isolated and the rest automated? Think about what a human-in-the-loop desk that is NOT "just buying and selling by hand" actually looks like.
3. IS THE OBJECTIVE WRONG? The desk targets per-trade profit on ~11 signals a day. What if the objective were capital preservation with occasional asymmetric bets, or a much lower trade frequency, or a completely different holding period (days rather than hours, given the "never hold overnight" rule is self-imposed and costs the entire overnight/gap return distribution)? Quantify what that rule costs, using the lake.
4. WHAT IS THIS DESK ACTUALLY GOOD AT? An independent ten-agent audit concluded its genuine assets are the measurement estate and research pipeline (valued ~1000:1 against the data itself), not any strategy. Is there a use for that which is not "trade MNQ intraday"?
5. THE UNCOMFORTABLE QUESTION, addressed honestly rather than avoided: is a ~$30k retail account trading one of the world's most liquid futures contracts a structurally winnable game at all? If the honest answer is no, what is the nearest adjacent game that IS winnable? Do not soften this, but do not be defeatist either — the operator has explicitly said he is not giving up and wants real directions.

DATA AND TOOLS: REPO /home/alphabot/gazbot7, `.venv/bin/python`, `PYTHONPATH=src`, DuckDB+pandas, read_only. data/backfill/*.parquet is the lake (MNQ + MGC, ~240 CME sessions of 1-min bars, front month per date by volume). data/capture.db has 5s bars/ticks/quotes (MULTI-SYMBOL, always filter). data/depth.db has L2 from 2026-08-14. data/gazbot7.db has the live trade record. You may compute things to support or kill an idea — a reframe backed by a number is worth ten that are not.

RULES: anything you test must be causal, must use a chronological train/test split, must clear ~1.25pt friction, and must report all periods. State how many things you tried. A control is supposed to lose.

DELIVERABLE: 3-6 genuinely DIFFERENT framings of the problem, each with (a) the idea stated precisely, (b) any evidence you could gather for or against it tonight, (c) what it would take to test it properly, and (d) an honest assessment of whether it is promising or merely novel. Rank them. The operator reads carefully, values honesty over encouragement, and has had a long day of nulls — give him something real to wake up to, whether that is a direction or a clear-eyed statement of what the game actually is.

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
