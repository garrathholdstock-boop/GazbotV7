---
name: golive-two-gate-grind-rgv
description: "2026-07-19 GO-LIVE — V7 live gate is now TWO-GATE grind_fast(conviction)+rg_long_fast_v(2R), PAPER, single-position; thrust→shadow"
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f130de1-fe42-4097-b16c-315bc9433aff
---

**2026-07-19 GO-LIVE (operator-directed, weekend build).** The live GAZBOT V7 MNQ desk gate flipped
from single **thrust_loose** → a **two-gate, single-position, first-to-fire lineup**:
- **grind_fast** — early-entry momentum (`gate_grind` slope_min 0.4 fast_slope), **ER 0/1/2 conviction
  sizing** (`sizing.py` efficiency_ratio/conviction_lots; chop→0/skip, marginal→1, clean trend→2, max 2),
  exit = **vol-adaptive chandelier** (`chandelier_start_k(entry_atr)`) + native 1-ATR stop.
- **rg_long_fast_v** — chop reversion (`gate_reversal_grab` LONG ext_min 2.0 fast atr_min 13), **flat 2**,
  exit = **2R** (`exit_scalp` target_r 2.0) + native 1-ATR stop.
thrust_loose → shadow slate only (all 3 gates now shadow-incubate too).

**Design A (single-position)** = robust: no per-gate attribution on the shared MNQ net; core's
one-position guard + native stop + naked-watchdog + session-flatten apply verbatim. Anti-correlated
gates rarely want a position at once → ~same P&L as concurrent, far lower risk.

**Code (gazbot7 `refactor/three-service`, `48af8d2`→`5a262a0`):** `config.py` GateSpec+`live_gates()`,
`strategy.py` `_pick_gate`/`_entry`(conviction)/`_manage`(per-gate exit routing)/`_active`, `sizing.py`.
Legacy single-gate path untouched (`gates=[]` default → thrust). 6 tests + full suite (290) + replay
parity (15-17 Jul: grind two-sided/chandelier/conviction, rgv long/2R, +$1,922 no-slippage). Armed
`systemctl restart gazbot7-strategy` 06:07 UTC (market closed, flat). Core untouched.

**⚠ HONEST BOUND: all validation is optimistic 1m-ceiling (walk-forward OOS pair +$1,978, Sharpe 3.48).
This is PAPER forward-validation on real fills, NOT real-money-ready.** Watch ~100+ live trades before
real money. First-hour watch (Globex open ~22:00 UTC 07-19): confirm 2-lot FILLS (IBKR paper account
size-limit unverifiable from here; reject is safe + exec-integrity CRITs), kill-switches OFF (paper
choice — native stop still caps each trade), fills reprice honest (expect below +$1,978).

**REVERT (disarm to thrust):** `strategy.py main()` → `RunConfig()` (empty gates) OR `git revert 5a262a0`,
then `systemctl restart gazbot7-strategy`. No core change made. Canonical live truth: alphabot2
`docs/STATE.md §1` (re-verify live, never recall — [[verify-desk-facts-never-guess]]). Research lineage:
[[shadow-board-as-regime-router]]. Next: forward-paper accumulates the honest sample.
