---
name: mgc-momentum-greenfield-null
description: "MGC greenfield momentum gate is a NULL — gold's runs are size-predictable but direction-unpredictable; 5 of 72 cells positive and the best strips to $16"
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-05T11:17:54.205Z
---

**2026-08-05.** Built a momentum gate for MGC from gold's own tape (not ported from MNQ), 2026-07-07..08-05, 11,858 min bars, 1.66M ticks, VPP $10.00/pt, sequential one-position-at-a-time, exits sequenced tick-by-tick. `scripts/mgc_run_census.py` + `scripts/mgc_momentum_gate.py`.

**The census is the useful half.** Gold produces 29 runs worth ≥$300 over 12 days (~2.4/day) — the raw material is real. Two features precede them, by effect size against ordinary tape:

```
ATR (pt)   2.86 vs 2.06   d=+0.80   REAL
ER30       0.232 vs 0.173 d=+0.43   REAL
|ext|, vwap_slope, net_atr_5        nothing
```

**Both survivors are MAGNITUDE features. Nothing calls the SIDE** — that is what kills it:

```
vwap_slope        54.9%  |  always SHORT 53.7%  → +1.2pp
new 15/30/60-min break 55.0/56.5/56.3%  → +1.9/+2.0/+1.4pp over best constant
```

Three independent direction signals all land ~2pp over a *constant* call. A consistent null, not three failed tunings.

**Backtest confirms it.** 2-lot exits (A fixed-R scalp, B wide chandelier) as requested: **5 of 72 cells positive**; best cell +$472/86 trades but **strip-best-1 = $16** — one trade is the entire result. The `always SHORT` control (−$532) BEAT the slope-directed gate (−$1,274): the direction feature is worse than no feature. Fee sensitivity $1.50→$5.00 barely moves it, so it loses on price, not cost.

**Why:** compare the base rates. On this tape "always SHORT" is right 53.7% of the time purely from 12 days of downward drift — any direction feature must clear THAT, not 50%. Checking against a coinflip instead of the best constant would have made vwap_slope look like a +4.9pp edge.

**Operator's ARM-THEN-CONFIRM proposal (delay like abs_veto) — also NULL.** `scripts/mgc_delay_confirm.py`. The wait is CHEAP (median move still available: 3.76 ATR at 0s → 3.70 at 30s → 3.66 at 60s, only −1 to −3%), so the objection "the delay eats the move" is wrong on gold. But the confirmed side is a coinflip: 48–50% across all 24 delay×commit cells, and the edge vs the best constant is **negative in every cell** (−0.5 to −8.3pp). ★ Why abs_veto works and this doesn't: abs_veto's 55s window VETOES a side the thrust already chose — it does not SELECT one, exactly like [[ofi-veto-grind-lead]]. A direction-blind arm gives the delay nothing to protect. Tested the veto form too (fixed direction + 30s veto): no rescue.

**Router-benching the gate does NOT rescue it either** (operator: "assume our router would be switching off this gate in non favourable chop"). `scripts/mgc_router_filtered.py`, using `untradeable.compute`'s own live blend computed CAUSALLY (session-open..entry, no look-ahead). The diagnostic leans the right way — winners meter 37.3 vs losers 45.3, roundtrip 0.54 vs 0.47, give-back 0.29 vs 0.38, all three correct sign — but **placebo-controlled it carries no information**: at the live thresholds the filtered result is beaten by 31–80% of same-size RANDOM removals. Sweeping all 14 cuts × 2 gates, best is "beaten by 7%" against ~4% expected from 28 looks, and z wanders around 0 with no monotone structure. ⚠ Underpowered: 80 trades / 10 days cannot distinguish a small real effect from none — it rules out an effect big enough to trade, not an effect.

★ METHOD: any "filter out the bad regime" claim MUST be placebo-controlled against removing the same NUMBER of trades at random. Removing 40% of trades looks brilliant whenever the removed 40% lost.

**★ THE L2 BOOK ALSO SAYS NO — and this one is WELL POWERED.** `scripts/mgc_book_direction.py`, 15 continuous days / 19,294 minutes of MGC 10-level depth, price reconstructed from the book mid. No book feature (L1 / L1-5 / L1-10 imbalance, or their 5-min deltas) calls the side: everything within ±3pp of the best constant, faded variants no better, and lopsided-book subsets no better. As a VETO on a fixed direction it adds +0.2 to +2.1pp. ★ On NON-OVERLAPPING windows the apparent +1.3/+2.1pp evaporates — the edge flips sign across 5 disjoint samples (+0.2, −0.2, −3.9, +3.7, +5.8; mean +1.1, sd 3.3) and 11 of 15 days are negative. **Overlapping forward windows inflated n 40×**: consecutive minutes share 39 of 40 forward minutes, so 18,594 "observations" are ~465 independent ones and 1 sd is 2.3pp, not 0.37pp. Unlike the 80-trade price studies this is well powered, so it is a real null, not an underpowered one.

★ SO GOLD IS CLOSED: price (predict / react / regime-filter) and book (select / veto) are the only two sources this desk has, and all five attacks are null. Re-opening MGC needs a source that is neither — event/session-time structure, or cross-asset (DXY, real yields) — not another sweep.

**★ DEPTH SLOTS: all THREE IBKR subscriptions are IN USE** — `depth-capture` = MNQ + MGC (10-level, 250ms), `md` = MNQ (5-level, 41ms book). There is no free slot; adding one means switching another off. I previously recorded the 3rd as unallocated — that was wrong. Also: `depth_snap` covers 07-18..08-03 where MGC ticks/bars do NOT exist, so the book is the only MGC price source through that window.

**★ FADER + CLOCK — the 6th and final attack, also NULL.** `scripts/mgc_fader.py`, 15 continuous days of book mid. A fader needs no direction predictor (the extension picks the side), so this was genuinely untested. Results: **Hurst computed on OUR tape = 0.489** (2-15min 0.490, 15-60min 0.479, 60-240min 0.462) — a random walk, no exploitable memory either way. Reversion after extension ≥2 ATR = 50.7% overlapping, but on DISJOINT windows **+0.7pp mean, sd 2.9, against 1 sd of 4.1pp** — zero. 9 of 15 days above 50%. Time-of-day (motivated by research, not swept): 22 hour-cells placebo-tested, best is hour 11 at "beaten by 5%" — exactly what 22 looks produce by chance; the two hours research nominated (LDN/NY overlap, London PM fix) were beaten by 88% and 14%.

**★ THE STRUCTURAL REASON GOLD IS HARDER THAN MNQ — worth keeping even though the gates failed.** The one real asymmetry found: on identical entries, FADING beat CONTINUING by $932 (lot A: −$143 @ 53% win vs −$1,075 @ 46%). But gold's R is small in dollars — ATR 1.63pt × $10 = **$16.25 R** (MNQ: ~15-25pt × $2 = $30-50). So breakeven at $1.50/RT needs **54.6%** and we measured 53%. **A fixed fee is roughly twice as regressive on MGC as on MNQ because R is half the size** — see [[mnq-fee-is-150-per-round-trip]]. Gold needs an edge 4-6x larger than anything measured to clear the same cost.

⚠ WEB RESEARCH TRAP: a search returned "gold Hurst = 0.41, genuinely mean-reverting; all OU configs failed on MGC" attributed to arXiv 2605.04004. **That paper is MNQ-only, 2021-2025, and mentions neither MGC nor Hurst** — it was a search-engine synthesis. Always fetch the source. The paper's real transferable finding: 14 OHLCV momentum families all died on cost, but its two positive controls were **session-anchored** (London Session Signal B T=5.15; RTH Confluence T=5.83) — structure came from TIME, not price shape.

**★★ 2026-08-05 UPDATE — THE OPERATOR PUSHED AND IT CHANGED THE CONCLUSION. Gold is NOT dead; it is UNDERPOWERED.** "did you create a gate that would catch them once theyve started? each gate only needs to contribute a few hundred bucks a week when its turned on." Both points were right and neither had been tested. `scripts/mgc_thrust_continuation.py`, `scripts/mgc_absorption_veto.py`.

★ THE GAP I HAD LEFT: every earlier study PREDICTED a run or confirmed over 20-90 SECONDS. A thrust-continuation gate entering a move already minutes and ATRs underway was never built. Built now, and **it catches the runs**: fired during **22 of 22** big runs, median **3 minutes in**, with **76% of the move still available** (quartiles 71/76/86).

★ WHY IT STILL LOSES: it fires on everything else too, and the loss autopsy says the losers are indistinguishable — ATR d=+0.21, ER d=+0.12, thrust size d=+0.02, same median hour. **There is nothing in price to filter on.** Sweep: 6 of 36 cells positive, best +$262 ($87/wk) but **strip-best-DAY negative** (−$161); dies at $3 fee.

★ ABSORPTION VETO (operator's idea, right shape — veto a side the thrust already chose, not select one): **null**. Separation d=+0.04..+0.18, and the sign is BACKWARDS (winners had MORE far-side resting size, 0.528 vs 0.516). 12 veto cells, placebo 21-95%.

★★ **THE ORACLE DAY-FILTER WORKS AND IS THE ONE LIVE THREAD.** Given perfect foresight of which days contain a big run: **+$779 total, $487/wk, strip-best-day +$356** (survives!) vs −$517 on the days it would skip. 8 of 15 days had runs. It CHEATS, so it is an upper bound — but it proves the losses are concentrated on skip-days and the operator's "turn the gate off except on trending days" has real headroom. This is the FIRST thing in the whole gold investigation to survive a robustness test.

★ CAN A RUN-DAY BE CALLED EARLY? First-4h features lean the right way — ATR **d=+0.44**, range **d=+0.42**, ER d=−0.30 — but **n=15 days**. ⚠ This is a **POWER limit, not a null**: separating a real ~50/50 day-classifier from noise needs ~60-100 sessions. Depth capture banks ~1/day ⇒ **revisit ~Nov 2026**. Do NOT re-run the gate sweeps before then; the missing ingredient is DAYS, not configurations.

**Do not retry by tuning thresholds.** The entry screen works (it cuts 301 trades to 80 and cuts losses proportionally); the missing piece is direction, and no threshold supplies it. A genuinely different information source — the L2 book, or an event/session-time model — is the only honest next attempt. Gold's 41ms book is not captured yet (3rd IBKR depth slot unallocated).

Method notes that mattered: first pass used MNQ's 3-ATR run threshold and found 24.5 "runs"/day — at gold's ~1.6pt ATR that is ordinary tape, not runs; the fix was an absolute $300 floor. First pass also flagged separation from ratios of near-zero medians (−0.032 vs −0.078); effect size against the tape's SD is the right test. See [[mfe-is-not-a-win-rate]], [[friday-findings-need-adversarial-rederivation]], [[exit-lab-paired-method-overstates]].
