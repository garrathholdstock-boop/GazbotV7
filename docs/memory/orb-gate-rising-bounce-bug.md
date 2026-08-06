---
name: orb-gate-rising-bounce-bug
description: ORB gate BUG found+fixed 2026-06-22 — shorted RISING bounces (price still below orb_low but recovering up on bounce-volume); fix adds net_atr direction + extension/capitulation guards (commit 61c51aec); ORB DISARMED in .env pending re-arm
metadata: 
  node_type: memory
  type: project
  originSessionId: 67c42436-f6c3-496d-ac98-2caeb1ac27ce
---

**The bug:** `_gate_orb` (alphabot/strategy/futures_entry.py) fired SHORT on a bare `current_price < orb_low AND rvol>=1.5` with NO direction-of-travel check. So a price that dropped below the opening-range low then RECOVERED UP (still below orb_low) on bounce-volume triggered a SHORT into a rising/green market. Funnel proof: MYM 19:14:59 `SHORT @52039, net_atr=+0.14 (rising), rvol=1.83 :: orb_short`. Live-bled −$51.50 (MNQ) / −$22.50 (MES) / −$13 (MYM) in 15 min. The `direction_is_bear` filter didn't save it — it only checks the downtrend CONTEXT (price < falling VWAP), not which way price is moving NOW, so it permits shorting bounces. LONG side had the mirror bug.

**The fix (commit 61c51aec, BUILT+TESTED, code live on disk but ORB disarmed):** 3 guards in `_gate_orb`, both directions:
1. `orb_min_thrust_atr=0.3` — net_atr must thrust IN the breakout direction (SHORT needs net_atr ≤ −0.3, LONG ≥ +0.3). Kills the green-bounce short.
2. `orb_max_vwap_ext_atr=3.5` (loosened from 2.5 on 2026-06-22, commit 41537b80) — veto a breakout already >this ATRs beyond VWAP (a climax). At 2.5 the cap vetoed ~55% of ORB (28/51 over 5d) for ~$0, near-silencing the gate; the net_atr gate is the real bug-killer (it removed −$84 of short-the-rise losers over 5d), so the cap was loosened to only catch true climaxes.
3. `orb_capitulation_rvol=3.0` — extreme RVOL while extended (>0.6× the ext cap) = blow-off/capitulation, veto.
New reasons: orb_{long,short}_{no_thrust,overextended,blowoff}. 6 new tests in test_live_gate_exact.py + existing ORB test updated (now needs net_atr thrust). Validated vs today's ORB trades: blocks the −$51.50 MNQ + the MYM bug short + a no-thrust −$5.50 long; keeps genuine down-thrust winners (+12.50/+7.50/+13.50).

**STATE: ORB DISABLED (2026-06-22 20:45)** — dropped from `FUT_ENTRY_GATES` (now `momentum,vwap_dip,vwap_pullback`). The gate-suite backtest (`scripts/gate_suite_backtest.py`) showed ORB is the worst gate (33-34% win, −$2,194/wk) and — investigated before acting — the sustained-trend filter that fixed momentum does NOT help ORB: both the sustained-trend subset (−$1,095) and the not-sustained subset (−$1,099) lose equally (the opening-range breakout produces false breakouts even in trending moments; a level-breakout can't be filtered like a strength-thrust). Loss dominated by US-INDEX (−$1,704, where ORB should work best — not the crypto/eurex mis-anchoring), shorts worse than longs. Disabling removed ~$2,500 of weekly backtest bleed (total −$3,373→−$873). The ORB FIX CODE stays in `_gate_orb` (inert), reversible = re-add `orb` to FUT_ENTRY_GATES. Revisit ORB on July trend data (maybe the 09:30-anchored breakout only works on genuine trend-days). Backup `.env.bak-orbdisable-*`.

**(prior) ORB RE-ARMED WITH THE FIX (2026-06-22 19:36)** — `.env FUT_ENTRY_GATES=vwap_dip,orb,vwap_pullback`, strategy daemon restarted (desk flat, clean). Live smoke test confirmed the bug case (short net_atr=+0.14) → `orb_short_no_thrust` (blocked) in the running daemon. WATCH the next ORB shorts to confirm the fix holds in production; if it still shorts a rising tape, disarm again (drop `orb` from FUT_ENTRY_GATES + restart). Backup `.env.bak-orbdisarm-*`. Related: the exhaustion/timing analysis ([[the earlier ORB exhaustion note]]) is subsumed — net_atr gate is the core fix, extension cap handles the climax case (e.g. the −$22.50 MES at the bottom, net_atr still −1.08 but stretched from VWAP).
