# Deep research on what actually works

*Brief written 2026-09-11 21:2xZ, relaunched 2026-09-12 after the parent session died 4 minutes in.*

You are a research analyst doing a literature and practitioner review for a solo futures desk. Today is 2026-09-11/12. Use WebSearch and WebFetch extensively — this is primarily a RESEARCH task, not a coding one.

⚠ WebFetch on academic PDFs often returns unparsed binary. When it does, it saves the file locally and tells you the path — then use the Read tool with the `pages` parameter to read it as images. This works well; use it.

THE SITUATION YOU ARE RESEARCHING FOR:
A solo operator trades Micro E-mini Nasdaq (MNQ) futures intraday, ~$30k account, 1-4 lots, flat overnight by rule. A full day of rigorous testing has established:
- DIRECTION is unpredictable from MNQ's own price/volume/order-book data at intraday horizons. Five independent methods all return ~0.50: break-then-join (24 cells, 0.469-0.506), order-book imbalance at leg starts (~0.000), a 150-cell volume-filtered grid (held-out: filter adds +0.001), a regime-detector across 22 configurations (50.0% win), and book thinning (lost to its own control out of sample).
- MAGNITUDE is strongly predictable: P(a 60pt move in the next hour) runs from 9% on quiet tape to 77% when ATR and volume are both high, day-clustered t=15.04 over 237 sessions, holding on 88% of individual sessions.
- ~430 exit configurations (targets $25-$300, cuts $50-$800, time exits, path-conditional cuts, no-stop variants) were tested across three chronological periods; 3 survived, which is what chance produces at that grid size.
- Mesfin (2026), "Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures" (arxiv.org/pdf/2605.04004), independently falsified 14 signal families on 947 days of MNQ and found a GROSS EDGE CEILING of ~1.05-1.50 points against ~2pt friction. Two signals passed (t=5.83, t=5.15), both using REGIME CLASSIFICATION with 60-75 minute holds.
- The desk's real friction is ~1.25 points ($1.50/contract commission plus a 0.50pt median spread crossed once).

YOUR RESEARCH QUESTIONS, in priority order:

1. GIVEN THAT MAGNITUDE IS FORECASTABLE AND DIRECTION IS NOT — what do practitioners and academics actually DO with that? The obvious answer is options (a straddle pays for magnitude regardless of sign), but the variance risk premium means implied vol is systematically ABOVE realised, so buying straddles is a structurally losing trade and selling them has unbounded risk unsuitable for $30k. Research this properly: is there a defensible retail-scale way to monetise a volatility forecast? Look into defined-risk structures, calendar/diagonal spreads, and whether micro-contract options on MNQ/NQ have usable liquidity. Report actual spreads and contract specs if you can find them.

2. WHAT ACTUALLY WORKS at retail scale in intraday futures, according to credible sources? Be sceptical — the retail education space is full of unsupported claims. Prioritise: academic papers with out-of-sample testing, practitioner writing that reports failures as well as successes, quant blogs with published code or data. Specifically hunt for evidence on: regime/state-classification approaches, order-flow and microstructure signals available to retail, cross-asset lead-lag, event/calendar-driven strategies, and execution-cost-aware strategy design.

3. THE DECAY QUESTION. McLean & Pontiff found published predictors lose ~26% out-of-sample and ~58% post-publication, and the famous Gao/Han/Li/Zhou intraday momentum result reportedly "disappears" out-of-sample. What survives publication? Is there a class of edge that is structurally resistant to being competed away (capacity-limited, operationally hard, requiring infrastructure retail lacks)?

4. IS MNQ THE WRONG INSTRUMENT? It is among the world's most liquid futures, which is exactly why the edge ceiling exists. Research whether less-efficient instruments are more tractable at this account size — other micro futures, less-traded contracts, different sessions — and what the trade-off is in spread cost and margin.

5. THE HONEST BASE RATE. What fraction of retail futures day traders are profitable, according to actual studies rather than marketing? There is real academic work on this (Brazilian day-trader studies, Taiwanese data, prop-firm pass rates). Report what it says.

RULES:
- Distinguish sharply between peer-reviewed/data-backed claims and marketing. Prop-firm blogs and course-sellers are not evidence.
- Quote specific numbers, sample sizes and dates where a source gives them.
- Where a claim is widely repeated but unsupported, say so explicitly.
- Cite every source with a URL.

DELIVERABLE: a well-organised research report answering all five questions, with sources. The operator is intelligent, has been at this for six months, has just had a day of negative results, and explicitly wants honesty over encouragement — but he is also NOT giving up and has asked for genuinely new directions. Give him the real state of knowledge, including any avenue that is genuinely open.

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
