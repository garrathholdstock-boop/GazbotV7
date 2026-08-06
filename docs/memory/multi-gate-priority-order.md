---
name: multi-gate-priority-order
description: "futures entry = 4 bidirectional gates, first-fires-wins by FUT_ENTRY_GATES order; re-ordered by strength 06-17; dashboard shows which gate bought"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7f83ba46-9480-4d61-afc1-9ca55897e71f
---

Futures entry is NOT 6 independent gates — it's **4 bidirectional gates**, dispatched **first-fires-wins** by the ordered `FUT_ENTRY_GATES` list in `.env` (that list IS the priority system). Each gate returns long OR short depending on which side sets up (the short halves go live only when shorts arm — see [[shorts-reenable-cluster]]). **Momentum is OFF the active list** (MOM badges on the board are legacy holdings, not new entries).

**Strength ranking (operator-approved 2026-06-17), inverse of entry range-position — gates that buy LOW rank above gates that chase:**
1. `peak_pullback` (DIP/RIP) — 2-bar-confirmed dip off the rolling-20 high; best entry, VWAP-agnostic.
2. `vwap_dip` (VW DIP/VW RIP) — 3-ATR (long) / 5-ATR (short) VWAP reversion; 1 confirm; day-shape-conditional.
3. `orb` (ORB) — opening-range breakout + RVOL; strong only ~09:30–10:30 ET (momentum gate, enters high).
4. `vwap_pullback` (PB) — light-volume VWAP tag in a trend; weakest confirm; regime-fragile. Demoted from #2 to last.

**Live `.env` (06-17):** `FUT_ENTRY_GATES=peak_pullback,vwap_dip,orb,vwap_pullback` (gitignored; applies at next strategy restart). Dashboard colour scheme: DIP green / VW DIP blue / PB cyan / ORB purple / MOM orange / shorts red — DTT chip colours by the about-to-buy gate; Holdings shows a matching badge left of Δ ENTRY (attributed via `fut_signal_funnel` firing reason nearest the open).

**Proposed-but-NOT-built:** a strength-rated swap-out system (evict dead-weight holdings for a stronger signal) — staged AFTER shorts soak, shadow-mode first; hard veto on ratchet-armed/in-profit positions. Discussed 06-17, no code.
