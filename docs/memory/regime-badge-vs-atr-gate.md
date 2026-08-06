---
name: regime-badge-vs-atr-gate
description: why a BULL regime badge can coexist with little trading — day-over-day gap vs intraday ATR measure different things
metadata: 
  node_type: memory
  type: reference
  originSessionId: 43122e6c-3e41-419a-882d-b53c02900156
---

The futures REGIME badge (US/EUREX/CRYPTO, in routes_futures_terminal.py) shows **day-over-day change anchored at the PRIOR SETTLEMENT** (US 16:00 ET, EUREX 17:30 CET, crypto 16:00 CT) — the same "futures +X% pre-open" number every source quotes. So a big badge number is usually dominated by the **overnight/weekend GAP**, not by live movement.

The ENTRY gate, in contrast, keys off **intraday ATR%** (5m) and the momentum burst. These measure different things, and they DIVERGE on a "gap-and-sit" day: the market gaps up overnight (badge reads BULL +1.3%) then grinds quietly at the elevated level (intraday ATR 0.03–0.09, well under the 0.10 floor). Result: **bullish-on-the-day but dead-quiet-right-now**, and the desk correctly takes few/no trades — `atr_too_low` dominates the funnel, NOT `no_momentum_burst`.

**How to answer the recurring "why no trades when it's so bullish?" question:** check the funnel reason split (atr_too_low vs no_momentum_burst) and the live ATR vs the floor. If ATR is sub-floor, the gate is correctly waiting — the bullishness is *stored in the gap*, not in live volatility. Intraday energy (and the trades) usually arrive WITH the cash open + first hour. Compounding factor: a steady grind up (↑↑↑↑) never makes the ↓↓↑↑ pullback the live burst needs — that's the [[continuation-entry-status]] blind spot.
