---
name: sims-on-tick-price
description: "Every sim/backtest EXIT must run on 250ms-tick price, never 1-min bars — 1-min overstates stops (the wick-stop illusion), proven repeatedly"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ed1c42ef-2406-4523-9fbd-a9a07df11ff2
---

Operator 2026-07-08 (emphatic): **"why don't you run sims on tick price? they always should be on tick price to be realistic."** He is right, and it's been proven repeatedly this week.

**Why:** a 1-min-bar exit SYSTEMATICALLY OVERSTATES stops — a wick that tags the 1-ATR stop and recovers within the minute still counts as a stop; at 250ms it never stops and the chandelier rides on. The effect is huge and one-directional:
- Momentum flow-exit: looked like it HELPED at 1-min (+2:1), HURT at tick.
- Momentum backtest: flipped RED → GREEN at tick (MNQ −$2,292 1-min → +$1,437 tick).
- Coil-break probe (2026-07-08): MGC +$16 (1-min) → **+$205** (tick); MNQ **−$136 (1-min) → −$32 (tick)** — the 1-min version falsely read "blows up on nasdaq" off a wick artifact.

**How to apply:** any sim / backtest / ad-hoc probe I run — computing the ENTRY signal on bars is fine, but the EXIT MUST be replayed on the 250ms tape via `replay_exit` (`_load_ticks` + `replay_exit`, `exit_fn=exit_ratchet` for momentum/breakout, `exit_desk` for reversion) from `scripts/passive_through_fill_backtest.py`. Aggressive entry fill = the touch (ask for a long) at the signal. NEVER present a 1-min-exit P&L as if realistic — not even for a quick curiosity check; it misleads one-directionally. The LIVE shadow desk (`shadow_real.db` `real_pnl`) is ALREADY tick-repriced — match that standard. See [[shadow-momentum-chandelier]] (the faithful-exit reprice) and [[three-pass-adversarial-friday]] (Friday lab tests everything tick-accurate).
