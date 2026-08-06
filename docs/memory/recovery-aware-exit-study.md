---
name: recovery-aware-exit-study
description: STUDY DONE 2026-06-21 (negative result) — recovery-aware exits do NOT beat the fixed 5-min flat-clock RED cut; keep the cut; tool scripts/recovery_exit_study.py + docs/RECOVERY_AWARE_EXIT_STUDY_SCOPE.md
metadata: 
  node_type: memory
  type: project
  originSessionId: 67c42436-f6c3-496d-ac98-2caeb1ac27ce
---

**Question:** the 5-min flat-clock RED cut ([[daytrade-flat-clock-20min]], 20→5 at ac6d3ac8) banks net-positive but is blunt — counterfactual showed ~34% of cut reds were green by 20min, ~64% touched green in-window. Can a recovery-aware rule beat both the 5-min cut AND the old 20-min hold?

**Verdict: NO — keep the fixed 5-min cut, it's near-optimal.** Causal backtest (`scripts/recovery_exit_study.py`, read-only on alphabot.db, 1m bars, no look-ahead) over the 166 5-min-era flat-clock futures reds:
- baseline 5-min cut: −$1478 (−$8.91 avg)
- `breakeven_else_20m` (exit flat if touches breakeven else 20m): **−$177 worse** despite improving 125/166 trades — the asymmetry kills it: breakeven-saves are small, the ~36% non-recoverers held to 20m drift much harder. **Extending non-recoverers to 20m is the killer** (the exact thing the 5-min cut fixed).
- `ride_while_improving` (cut on first 1m stall): **−$309 worse** (too twitchy, rides losers).
- `giveback_trail_25` (extend only a red that climbs back into PROFIT, then trail 25%): **+$61** — the lone non-losing rule, but ~$0.37/trade, inside the fee/noise band.

**Why it matters:** the "64% touch green" stat is *un-banked paper-green* — capturing it means holding the losers too, which costs more than it saves. This is a NEGATIVE result that forecloses the recurring "give reds room to recover" instinct with numbers. Don't ship a recovery-aware exit. At most shadow-watch `giveback_trail_25` if its edge widens on a bigger sample; re-run the script anytime (~instant). Committed main c5551a6a — read-only study, no behaviour change, no deploy.
