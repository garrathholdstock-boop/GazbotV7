---
name: abs-veto-live-promotion
description: "LIVE 2026-07-25 — abs_veto promoted to the paper tournament as two independently-switchable single-sided gates (abs_veto_long/short), replacing thrust_short + rgv_long. 55s veto is CODE in tournament.run()."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9162c01b-c354-41a1-9fc3-162d48ae4678
---

**2026-07-25 (Saturday roster change, operator-decided): promoted `abs_veto` to the LIVE V7 paper tournament as TWO independently-switchable single-sided gates** — `abs_veto_long` + `abs_veto_short` (both `kind="thrust"`, params thr=1.5/amp_floor=0.0004, scalp 2R/1ATR, `base_size=1`). Two separate gates (NOT one two-sided gate) so each side has its own on/off switch. **REMOVED** `thrust_short` (superseded) + `rgv_long` (worst performer, −$691 all-time / −$546 recent — evidence pick; capitulation_long was spared as the only all-time-green gate).

**New live roster (3 long / 3 short, single-position first-to-fire):** grind_long, capitulation_long, abs_veto_long · rgv_short, exhaustion_short, abs_veto_short. Startup line confirmed: `tournament LIVE — slots=[...abs_veto_long...abs_veto_short...]`. Restarted `gazbot7-tournament` 2026-07-25 13:42 UTC in the flat+market-closed window → live for the Sunday reopen. overall OK / preflight True / flat post-restart.

**The 55s veto is CODE, not config** (SlotSpec has no veto field; the roster's only delayed-entry path is the fader `CONFIRM_GATES` = OPPOSITE polarity). Implementation:
- `deciders.py`: `VETO_GATES={abs_veto_long,abs_veto_short}`, `VETO_SECS=55`, `VETO_MAX_SECS=75`, `VETO_FLOW_MIN=50.0`.
- `tournament.run()`: a `pending_veto` buffer right after the rgv-confirm loop — arm on an abs_veto thrust OPEN, wait 55s, enter ONLY if the thrust STILL fires this tick (re-emitted, slot flat) AND the window `[armed,now]` shows no absorption (`exit_absorption()` momentum polarity). **Default-VETO on any read failure / <5 ticks / thrust gone / tape-gap>75s** (never forces a bad fill). Faithfully mirrors the shadow `abs_veto_55s` end-decision (shadow.py `_step`).
- `base_size=1` = like-for-like vs the still-running shadow `abs_veto_55s` A/B (scale on live evidence, promotion-ladder).
- Tests: `tests/test_abs_veto_promotion.py` (roster + veto polarity + side-filter) + updated 4 roster-pin tests; full suite green.

**Operational:** each gate independently on/off via `data/gate_switches.env` (live re-read, no restart) or the `gazbot7-tgbot` phone bot. ⚠ abs_veto is **REGIME-DEPENDENT** ([[gates-two-sided-per-side-tuning]]): +EV in loud tape, bleeds in quiet chop; NOT direction-router managed (manual switching, like thrust was). Minor known no-op: `direction_router.py` DOWN_OFF still lists `rgv_long` (harmless — switch for a non-roster gate is ignored); optional cleanup later.

**★ PER-SIDE CHOP-FLOOR added + LIVE 2026-07-25 16:27 UTC** (same Saturday, flat/closed window; deciders.py ER_FLOOR/ATR_FLOOR; restart done, tests green, overall OK). Backtest (`scratchpad earning_floor/chop_floor/master_sweep.py`, engine-truth earning + validated-replay chop, $1.50 fee): the two sides want OPPOSITE floors — **LONG `abs_veto_long` ER≥0.20** (no ATR floor), **SHORT `abs_veto_short` ATR≥16pt** (NO ER floor — an ER floor craters short earning $822→$226). Kills the chop bleed −$958→−$68 for ~$265 earning sacrificed; full-window EV +$382→**+$1,007**, no negative ISO-week. Beats the inherited both-side ER0.20+ATR16 (+$836) by +$171 (by NOT ER-flooring short) and beats routing. Floor gates at the TRIGGER bar (step() er_blocks/atr_blocks) BEFORE the 55s veto. ⚠ in-sample, small per-side n, winner-DOLLAR retention only ~½ (trades loud-window upside for chop protection). REVERT: drop the two abs_veto keys from ER_FLOOR/ATR_FLOOR + restart.

**NEXT (operator "add ofi veto after"):** layer the seconds-OFI SHORT-side veto (OOS-survived; LONG was a fit) on top — needs live L2/OFI computation in the entry path, built + verified against the live feed before it goes on.

**REVERT:** restore the old `tournament_slots()` return block (re-add rgv_long + thrust_short, drop the two abs_veto specs) + remove the VETO constants/loop + restore gate_switches.env + `sudo systemctl restart gazbot7-tournament`. Links [[gates-two-sided-per-side-tuning]] [[run-catcher-null-all-microstructure]] [[tournament-changes-saturday-only]] [[promotion-ladder-sizing]].
