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

## Exit config format (`data/exit_overrides.json`)
`{gate: {"a_r": <LotA scalp R>, "b": <number = LotB scalp R | "wide" = lock-chandelier | "tight" = k1.5 chandelier>}}` — gate absent from the file keeps its built-in default. Edit → restart tournament. Fail-safe: bad entry falls back to default.

## The loop
measurable regime read → pick gates + exits from this sheet → **prove each config on its HOME regime tape** (Friday, regime-segmented) → update the Rs here with what's proven. Priors get replaced by evidence.
