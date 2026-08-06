---
name: backtest-on-5s-250ms-persist-all
description: "Operator requirement — ALL backtesting on 5s bars + 250ms ticks, matching live, persisted for all 7 contracts"
metadata: 
  node_type: memory
  type: project
  originSessionId: ccb6199e-59b1-4963-8e0b-88c88bf59bac
---

Operator directive (2026-07-03, emphatic + frustrated): **all backtesting is to be done on 5-second bars AND 250ms bid/ask — "just like we trade" — and both feeds MUST be persisted for all 7 contracts** (MNQ/MES/MGC/M2K/MYM/MCL/MBT). This is a hard requirement for the [[favourable-condition-gating-vision]] / weekly footprint filter analysis (`docs/WEEKLY_FOOTPRINT_FILTER_ANALYSIS_SCOPE.md`).

**Why it hurts right now:** the 5s bar capture has been unreliable — (1) a flush-overlap bug (`bar_recorder._FLUSH_OVERLAP_BARS=8` sized for 1m) silently dropped ~87% of 5s bars for ~2 weeks after S5 was added 2026-06-14 (fixed 2026-07-03 `edcdb114` = per-timeframe overlap); (2) the 5s bars + quote_snapshot write to the big busy `alphabot.db` and hit `sqlite3 "database is locked"` under contention (the 250ms `quote_tick` is robust because it lives in a SEPARATE `ticks.db`). The lost 2 weeks of 5s bars are likely NOT recoverable — IBKR `reqHistoricalData` times out on all contracts (paper account lacks a historical-data subscription; it can STREAM live but not pull history).

**How to apply:**
- **Persistence must be robust for all 7, not best-effort.** The architecturally-correct fix is to write the HF 5s bar capture to a dedicated DB (like `ticks.db`) or otherwise remove it from the main-`alphabot.db` write-lock contention; and never size a flush/buffer for one timeframe when others exist.
- **Add a capture-health GUARD** so a silent drop can never fester again: alarm if 5s bar density (or 250ms tick density) per contract falls below expected for the session. The 87% loss went unnoticed for 2 weeks precisely because nothing consumed the 5s table yet — "capture the ephemeral now" ([[analytics-capture-roadmap]]) + "monitor that it's actually landing."
- **Backtests/sims must read the fine feeds:** the shadow sim + fill model already do (5s + 250ms ticks); ensure any new backtest tool uses 5s bars + 250ms, not 1m. 1m is the intact fallback but NOT the target.
- **Do NOT run bulk `reqHistoricalData` against the LIVE gateway** — it can interfere with the MD daemon's own subscriptions (observed 2026-07-03: test historical clients coincided with MD capture stalling). If backfilling is ever enabled (needs the IBKR historical subscription), use a dedicated off-peak client, paced.
