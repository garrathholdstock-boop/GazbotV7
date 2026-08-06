---
name: friday-grind-fast-deep-dive
description: 2026-07-17 operator — Friday report must DEEP-DIVE sim
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f130de1-fe42-4097-b16c-315bc9433aff
---

2026-07-17 operator directive (enthusiastic — verbatim gist): *"spend a bit of time analysing sim 22 today. we have never had a sim take so much advantage of runs. easily best momentum sim we've ever tested. analyse the shit out of it. i know it's only one day but today was volatile with big runs and it still did really really well. show me charts of the top 10 trades with the run and where we entered and where we exited nice and clear. i want to understand how this sim works. then we can put it into live if it survives."*

**Sim #22 = `grind_fast`** (board id #22, `_ID_ORDER`). Today (honest tick-repriced `real_pnl`): **51 trades, +$1,401.5, avg +$27.5, 26W/25L, best +$334.5, worst −$78.5** — the board's runaway leader.

**MANDATORY Friday deliverables for grind_fast:**
1. **Top-10-trades CHARTS — the centrepiece the operator asked for.** One clear chart per trade: the price RUN (5s bars, `capture.db` MNQ 5s — 14k+ bars/day) with the **entry marked** and the **exit marked**, so you can SEE the thrust/run captured and where the chandelier let go. Data join: `shadow_real ⋈ shadow_trades` on trade_id (entry_ts/exit_ts unix sec, entry_price/exit_price), `strategy='grind_fast'`. Today's top 10 (all CHANDELIER exits) as the anchor set:
   - 13:53 LONG 28589→28718 (+128.5pt, 11m) **+$334.5**
   - 15:42 LONG 28786→28890 (+104pt, 19m) **+$242.5**
   - 14:04 LONG 28718→28815 (+97.5pt, 8m) **+$209.5**
   - 08:13 SHORT 28679→28604 (−75pt, 5m) **+$160.5**
   - 16:32 LONG 28910→29002 (+92.3pt, 21m) **+$151.5**
   - 01:13 SHORT 29035→28988 (35m) **+$142.5** · 19:06 SHORT (12m) **+$134.5** · 13:36 SHORT (12m) **+$116.5** · 03:43 SHORT (22m) **+$114.5** · 17:36 SHORT (26m) **+$84.0**
2. **Explain HOW it works (the operator wants to understand it).** Mechanism: the **grind gate** (`gate_grind`, trend CONTINUATION) — enters WITH an established VWAP trend using the **fast short-window slope** (`slope_min 0.4`, `fast_slope=True`) while price rides with the trend but isn't exhausted (`ext_atr` band), catching sustained grinds the 5-bar `thrust` burst gate misses; **exit = the uncapped tightening chandelier** (rides the whole run, only tightens as the peak extends). That pairing = enter early on a real trend, ride it uncapped → the "takes advantage of runs" the operator saw. Show the anatomy: avg win vs avg loss, % of P&L from the top handful, both-sided (longs AND shorts ride).
3. **The cross-gate insight (connect to [[direction-regime-gate-enablement]]):** grind_fast's LONGS WON today (13:53/14:04/15:42/16:32 big long runs) while the live `thrust` LONGS bled (−$389). Same day, opposite long outcome → the **GATE/entry-timing is the difference** (continuation-with-slope vs late burst). This is a big clue and belongs in both investigations.
4. **Promotion verdict + path.** If it survives → candidate for LIVE. But gate it honestly (this is [[exit-architecture-scar-tissue]] / [[favourable-condition-gating-vision]] discipline): today was VOLATILE with big runs = a trend-continuation gate's BEST case. Must survive a **CHOP day** (where a fast-slope continuation gate can chase fakeouts and bleed) and multiple days before live. The shadow courtroom / forward OOS ladder decides, not one green day.

**★★ REAL-SAMPLE VERDICT — 2026-07-17 V5-archive replay (25 days, 06-15→07-17, MNQ 1m `bar_history`, ceiling pnl):** grind_fast is **−$7,895 over 25 days** — a NET LOSER. Today (+$1,131) was its SINGLE BEST day; it bleeds most days (−$1,010/−$1,191/−$1,264/−$1,249/−$1,192/−$1,017/−$853…). **⇒ grind_fast does NOT survive standalone — today FLATTERED it hard** (one-day recency bias; the replay caught it — why we backtest before live). Usable ONLY behind a day-type router ([[direction-regime-gate-enablement]]), NEVER standalone live. ⚠ ceiling pnl is optimistic → real is WORSE. The charts/mechanism work still stands (understand WHY it wins its green days), but the promotion verdict flipped to: NOT live standalone.

**HONEST CAVEATS (state them in the report):** (a) ONE day; (b) that day was grind's best-case regime; (c) real_pnl is honest (tick-repriced) so the number is trustworthy, the SAMPLE is the weakness. Report leads with what SURVIVED, never a naked one-day point estimate ([[three-pass-adversarial-friday]] §11.5).

Belongs in the Friday interrogation Shadow half. [[friday-report-full-pipeline-guarantee]]
