# REGIME → EXIT CHEAT-SHEET (GAZBOT V7)

> **What this is:** the map from a measurable tape regime to *which gates are armed* (`data/gate_switches.env`) and *which exit each uses* (`data/exit_overrides.json`). The desk is regime-conditional — we chop and change gates + exits by regime instead of freezing one config and sitting out.
>
> **★ THE R VALUES BELOW ARE OPERATOR PRIORS / GUESSES — NOT PROVEN.** The Lot-A/Lot-B scalp Rs (0.5/1.5, 1.5/2.5, 2.5/wide) are starting points. They MUST be swept and proven **per regime** by the Friday report (regime-segmented, never blanket — see [[backtest-per-regime-segment-not-blanket]]). Update this file with the PROVEN Rs as they're established; keep the "status" column honest.

## Read the tape on ATR + ER + range-break + time-of-day (never one signal alone)

| Regime | Measurable read | Gates armed | Exit config (`exit_overrides.json`) | Status |
|---|---|---|---|---|
| **1. Dead low-vol grind** | ATR <~10, day-ER <0.05, no thrust | none — **sit out** | — | ✅ validated (nothing works) |
| **2. Normal chop / range** | ATR ~11–18, ER <0.20, oscillating inside H/L, no break | faders (exhaustion, rgv, capitulation) | scalp `{"a_r":0.5,"b":1.5}` | ⚗ PRIOR — Rs unproven |
| **3. In-between / building** | ATR ~15–25, ER 0.20–0.35, directional lean, no clean break | momentum aligned (abs_veto/grind by day-bias) | scalp `{"a_r":1.5,"b":2.5}` | ⚗ PRIOR — Rs unproven |
| **4. Clean trend / big move** | ATR >~18, ER >0.35, range-break (esp. post-open) | momentum aligned | `{"a_r":2.5,"b":"wide"}` (ride 4R/6R) | ✅ validated (chandelier/runners); A-scalp R unproven |
| **5. Violent chop / whipsaw** | ATR >~20 **but** ER <0.20 (vol, no direction) | none / minimal — **sit out** | — | ✅ validated (reopen churn) |

**Time-of-day overlay:** overnight/pre-open (~21:00–13:30 UTC) → mostly regimes 1–2, big runners rare; US session (13:30–21:00 UTC) → regimes 3–4 (the runners) + afternoon roll-over back to regime 2.

## ★ 2026-08-02 — THE QUIET-TAPE CLIP IS LIVE, and it supersedes part of the table above

The desk no longer picks one static exit per gate. Each slot decides **at entry, on entry ATR**, and freezes that choice for the life of the position (re-evaluating mid-trade would let a widening tape move the target away from an already-green position — the exact give-back this closes):

| entry ATR | Lot A | Lot B |
|---|---|---|
| **< 22pt** (quiet) | **fixed $40** | **1.75R, floored at $60** — a clip, NOT a chandelier |
| **>= 22pt** | its normal R (unchanged) | its normal chandelier (unchanged) |

Live on grind_long, capitulation_long, exhaustion_short, abs_veto_long/short. **Off for nipc** (13:00–15:00 only, never sees quiet tape, has its own swept pair).

**The evidence** — live fills, 250ms ticks, $1.50/RT, strip-best-3 and leave-one-day-out on every cell:

| window | n | median ATR | best cell | wide chandelier |
|---|---|---|---|---|
| QUIET 22:00–13:30 | 97 | 17.4pt | **$40 clip +$360** (+$244 stripped, +$25 LODO-worst, top trade 11% of net) | **−$538** (−$1,232 stripped) |
| US 13:30–22:00 | 144 | 28.4pt | **wide +$2,611** (+$964 / +$416) · 3.5R +$2,022 (+$1,019 / +$645) | the best cell |

Round-trippers — reached ≥1R green then finished ≤0 — are **20.6% quiet vs 7.6% US**. The give-back is a quiet-tape problem, and a trail is the worst answer to it: on a 17pt ATR there is no room for one.

Keyed on **ATR, not the clock**, deliberately — a dead US afternoon should clip and a violent overnight should ride. Lot A is in **dollars** because a fixed $ auto-tightens as ATR rises inside the quiet band, and it beat every R cell there (1.0R −$32, 1.25R −$18, both failing stripped). `b_floor_usd` exists because 1.75R is only 20pt at ATR 11.4 — without it Lot B clipped *tighter* than Lot A, runner banking before scalp, on ~17% of MNQ minute bars.

**Not fully proven:** 22pt is a midpoint between the two medians, and Lot B's 1.75R/$60 are **inferred** — the grid swept single-lot exits, so the evidence says "B should clip, not trail", not that level. Only Lot A's $40 survived the full battery. 7 quiet / 6 US days, exact-fill ceiling, and a clip trades more often so pays slippage more often than the table shows.

## Exit config format (`data/exit_overrides.json`)
`{gate: {"a_r": <LotA scalp R>, "b": <number = LotB scalp R | "wide" = lock-chandelier | "tight" = k1.5 chandelier>}}` — gate absent from the file keeps its built-in default. Edit → restart tournament. Fail-safe: bad entry falls back to default.

Optional quiet-tape clip on any gate: `"atr_split": 22, "lo": {"a_usd": 40, "b_r": 1.75, "b_floor_usd": 60}`. Absent → today's behaviour exactly. A malformed `lo` drops **only** the split, never the gate's normal exits; a `b_floor_usd` at or below `a_usd` is rejected because it would re-open the inversion. Revert: delete the `lo` keys + restart.

⚠ **Never tune a scale-out gate by editing base `target_r`** — `scaleout_slots()` rewrites Lot A's target and turns Lot B into a chandelier, so the base value reaches **nothing**. This bit capitulation on 2026-08-01. Guarded by `tests/test_scaleout_slots.py`.

## The loop
measurable regime read → pick gates + exits from this sheet → **prove each config on its HOME regime tape** (Friday, regime-segmented) → update the Rs here with what's proven. Priors get replaced by evidence.
