---
name: force-kill-dormant-and-resweep
description: The live $80 force-kill is DORMANT on the whole micro desk (fired 0× / 1377 trades / 10d); per-contract tuned thresholds recover ~$178/10d zero-clip. Passive tick re-sweep due once ticks ≥ ~5 days (~2026-07-06).
metadata: 
  node_type: memory
  type: project
  originSessionId: f8d854cc-966e-4451-ac84-f55a2a72b8da
---

**Two linked findings (2026-06-30), study tools committed to main, NOTHING armed.**

**1. The live force-kill is effectively OFF on the micros.** At the live `.env` thresholds
(`FUT_FORCE_KILL_USD=80`, run_n 4, force_atr 1.5), force-kill fired **0× across all six micro
contracts** (MNQ/MES/MGC/MYM/MCL/M2K, 1377 live trades / 10d). The $80 floor is calibrated for big
positions; a micro's typical adverse move never reaches it. Ratchet-2 also barely fires. So the micro
desk effectively runs on R1 + 1-ATR stop + flat-clock alone — the "force killer" is dormant.

**2. A per-contract tuned force-kill recovers ~$178/10d, near zero-clip.** Best per contract (Δ vs the
inert $80 baseline, full live-spine replay on bar_history 5s paths):
- MNQ (desk's worst, −$2232/10d live): $28 / run 2 / 0.3ATR → +$80, **zero clip**
- MGC: $10 / 2 / 0.5ATR → +$70 (clip −32); MES: $10/2/0.75 → +$17; MCL/M2K/MYM: +$1–5
Direction is robust across ALL contracts: drop force-kill from $80 → **~$10–30/contract, run_n 2–3,
force_atr 0.3–0.75**. It only ever cuts confirmed adverse runs while underwater, so it can't clip
winners. RECOMMENDED next step = scope the live `.env` force-kill recalibration per-contract
(FLAG-AND-WAIT; touches sizing-adjacent config — operator arms). Exact $/ATR carry in-sample overfit
(~8–9d, mid fills); the magnitude direction does not.

**Tools (scripts/, observe-only):** `force_kill_per_contract_sweep.py` (live desk, 5s bars, 10d);
`passive_force_kill_sweep.py` (passive shadow, full live spine + force-kill sweep, tick-limited);
`passive_exit_rescue_sim.py` (passive, ratchet-1 exit family). Commits ddb09dce + ab9aa39c.

**RE-SWEEP DUE (~2026-07-06):** the PASSIVE force-kill sweep is tick-limited — tick capture began
2026-06-29 17:45, so the 06-30 run is one in-sample day. Re-run `passive_force_kill_sweep.py` once
data/ticks.db spans ~5 trading days to check the zero-clip $15–22/run3/0.75ATR cluster holds OOS.
The per-contract live-desk sweep is NOT tick-limited (uses 5s bars) and can re-run any time.

Context: passive is still a MIRAGE (realistically negative; exits redistribute, don't create edge —
see [[regime-detector-impossible-passive-pivot]]). Force-kill helps the loss tail but doesn't make
passive +EV. The live-desk per-contract recalibration is the real takeaway, independent of passive.
