---
name: dual-slot-scaleout-live
description: "Dual-slot SCALE-OUT is the unified profit exit, LIVE on gazbot7 since 2026-07-29 (slate 'scaleout'). Each gate → 2 sub-slots that fire on ONE signal: Lot A fixed-R scalp (guaranteed floor) + Lot B chandelier (tail). First win: abs_veto_short A+B = +$768 in one trade."
metadata: 
  node_type: memory
  type: project
  originSessionId: fdd18525-f007-4dbb-8d0e-f435f4d4eca8
---

**LIVE 2026-07-29 (gazbot7 commit 5b0913b, slate `scaleout`, env-switchable).** The give-back fix: every gate's profit exit is now **Lot A + Lot B**, two independent 1-lot sub-slots (`<gate>_A`, `<gate>_B`) that BOTH fire on one signal. Lot A = fixed-R scalp (guaranteed floor, bank early); Lot B = chandelier (ride the fat tail). Native 1-ATR stop owns the loss; Lot B → breakeven after A banks.

**Config (operator):** BIG-RUN gates (grind_long, abs_veto_short, abs_veto_long, exhaustion_short) → **A@2.5R + B wide lock-chandelier** (start_k3.5/lock_r6/lock_k0.5). FADERS (rgv_short, capitulation_long) → **A@1.5R + B tight k1.5 chandelier**. `slot_strategy.scaleout_slots()` builds 12 sub-slots via `replace()` off `tournament_slots()` (one source of truth). `tournament._base()` strips `_A`/`_B` so base-name benching / the 55s abs-veto / the exhaustion 5s-confirm all apply to both lots. +7 tests.

**★ FIRST WIN (live proof): abs_veto_short A+B = +$768 in ONE trade** — Lot A banked the 2.5R floor **+$232**, Lot B rode the wide chandelier tail **+$536** (2.3× the floor). Neither lot alone gets that: pure-scalp misses the tail, pure-wide gives it back. (Debut fire was a −$166 whipsaw — exhaustion_short A+B both 1-ATR stopped on a chop up-tick; net across the 2 scale-out fires +$602. Small N, but the MECHANISM is proven on live fills.)

**Why it exists — the give-back research (2026-07-29):** exhaustion monsters peak fat-tailed (MFE median ~6R, tail to 60R); the wide lock-chandelier NEVER tightened (lock_r=6 unreachable) so a +$292 monster gave back to +$22. Sweeps proved **tightening the single trail LOSES money** (the tail dominates) — scale-out (bank a partial, ride the rest) is the web-consensus + data answer. ★ **BACKTEST EXITS ARE UNRELIABLE ON THIS DESK** — every tick-reprice of the exit overstated/understated live realized by 5-10× (validation failed both directions); the live desk exits worse (cadence/fills/other paths). Measure exits LIVE or via the honest shadow repricer, NEVER a fresh backtest. [[sims-on-tick-price]] [[shadow-sim-understates-losses]]

**★ MORE LIVE PROOF 2026-07-30 (operator: "resounding success"):** 5 dual-profit exits in one day — Lot A TARGET + Lot B CHANDELIER both green: +$163, +$111, +$146, +$72, **+$251** (abs_veto_long — A +77.5 scalp / B +174 tail; the long-side mirror of yesterday's abs_veto_short +$768). The design proven on BOTH sides now, momentum AND reversion (capitulation A+B +$72). Context: the [[router-trial-day2-findings-0730]] gate tuning (grind ER floor 0.35 / abs_veto no-floor) is what keeps momentum gates OUT of the chop so the scale-out only fires on real moves.

**Deploy/revert:** slate via `GAZBOT7_TOURNAMENT_SLATE=scaleout` (systemd drop-in `/etc/systemd/system/gazbot7-tournament.service.d/scaleout.conf`); revert = remove drop-in → `tournament` slate. Restart only when FLAT + ledger empty (see [[orphan-stop-phantom-incident]]). Dashboard shows _A/_B as separate holding cards (A banks → card closes → B keeps ticking — the operator's requested view). [[exhaustion-short-counter-veto]]
