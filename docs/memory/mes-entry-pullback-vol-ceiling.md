---
name: mes-entry-pullback-vol-ceiling
description: "2026-06-30 SCOPED — optimise MES entries = the vwap_pullback gate has a DORMANT vol ceiling; it earns at atr_pct 0.045-0.07 and bleeds above ~0.09 (n=229, monotonic, desk-wide)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a177229-b370-41db-bb71-2814d3a9582c
---

2026-06-30 investigation (operator: "optimise MES entries — tape moves like MNQ just less aggressive"). Findings:

1. **MES uses MNQ's EXACT entry config** — both route to `vwap_pullback,vwap_dip` (`_ENTRY_GATES_BY_KEY` identical for all) + the same `DEFAULT_ENTRY_PARAMS` (only crypto differs). NO per-contract entry-params override exists (unlike stops' `_BY_KEY` maps) → "tune MES" has no lever today; scaffold must be built.
2. **Operator's read confirmed**: MES 1m atr_pct ~0.04-0.06% vs MNQ ~0.08% (~half), SAME pullback edge shape.
3. **Robust signal (n=229 all-contract pullback, monotonic)**: gate earns ONLY at atr_pct [0.045,0.07) = +$255; breakeven below; bleeds above — [0.07,0.09) −$165, [0.09,0.12) −$193, [0.12,∞) −$347. **Skip pullback at atr_pct≥0.09 = removes 66 trades netting −$539** (35% win). Bleed shows on BOTH MNQ (n21 −$279) and MES (n5 −$210) → not one-contract noise.
4. **Why no ceiling fires**: `DEFAULT_ENTRY_PARAMS.atr_pct_max=6.0` (6%) is DORMANT (micro 1m atr_pct tops ~0.15%, like the old $80 force-kill never bit); AND atr_pct_min/max only gates the dip/momentum path — **`_gate_pullback` has NO vol band at all**.
5. **Mechanism (trustworthy, not just fit)**: a VWAP pullback in CALM tape mean-reverts; the same shape in a vol-expansion is a real breakdown you're buying → monotonic dose-response.

**FIX (scope `docs/MES_ENTRY_PULLBACK_VOL_CEILING_SCOPE.md`, flag-and-wait):** (1) PRIMARY desk-wide — add an atr_pct ceiling to `_gate_pullback` (~0.09 conservative, +~$540/10d; 0.07 aggressive shadow-first); (2) MES-specific — build `_ENTRY_PARAMS_BY_KEY` + `entry_params_for(key)` scaffold (mirrors [[mgc-pullback-clock-regression]]'s force-kill `_BY_KEY` pattern) so MES carries a tighter ceiling (~0.07) scaled to its lower vol. CAVEAT: 10d/one-regime + MES values 36-trade thin (set MES from the desk-wide curve, tune forward via the per-contract shadow panel). Same family as the exit studies but this is an ENTRY filter with a real mechanism → more armable. NOT built yet.
