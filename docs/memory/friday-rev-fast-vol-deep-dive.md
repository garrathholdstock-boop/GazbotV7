---
name: friday-rev-fast-vol-deep-dive
description: 2026-07-17 operator — Friday must deep-dive sim
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f130de1-fe42-4097-b16c-315bc9433aff
---

2026-07-17 operator (verbatim gist): *"i also want the report to dig deep on sim 23 — rev grab fast vol. we are hopeful that will be an excellent reversion sim for us. took some huge wins today but overall down for the day. do some deep analysis on it. i think it could be a great chop reversion gate."*

**Sim #23 = `rg_long_fast_v`** (board id #23). `reversal_grab` LONG-only + a VOLATILITY FLOOR: `{side:LONG, ext_min 2.0, turn_atr 0.15, fast_slope True, fast_turn True, atr_min 13.0}`, chandelier exit. Fades a stretch BELOW VWAP that's turning back up, only when ATR ≥ 13 (the vol floor cut low-ATR fizzles 28→~13 trades in the build backtest). It is a REVERSION/fade gate — the opposite family to grind_fast (trend continuation).

**Honest real_pnl so far (down both days, but big wins inside):**
- 07-16: −$88.5 (7 trades, 2W/5L, best +$106.5)
- 07-17: −$155.0 (28 trades, **6W/22L**, best **+$320.0**) — classic reversion shape: many small fade-losses, the occasional big reversal win.

**Why the operator is hopeful — and the KEY thesis (the day-type-router pairing):** today (07-17) TRENDED with big runs — that is a reversion gate's WORST regime (it fades runs and gets run over), yet it still printed a +$320 winner. On a CHOP day it should be in its element. This makes it the **mirror specialist of grind_fast (#22)**: grind = run-day, rev = chop-day. The pairing is already visible in n=2 (see [[direction-regime-gate-enablement]]): on the CHOP day 07-16, grind bled −$853 while rev only −$88; on the TREND day 07-17, grind +$1,131 while rev −$155. A day-type router that ran grind on 07-17 and rev (or nothing) on 07-16 avoids grind's −$853 chop bleed — THAT is the whole framework, with early evidence.

**MANDATORY Friday deliverables for rg_long_fast_v:**
1. **Isolate the winners** — chart the big reversal wins (e.g. today's +$320): the stretch below VWAP, the turn, entry, chandelier exit — same clear entry/exit treatment as the grind_fast top-10 ([[friday-grind-fast-deep-dive]]).
2. **Split its P&L by day-type** (trend vs chop, per the early-efficiency tell below) — the hypothesis is it's +EV on chop, −EV on trend. If true, it's a chop specialist to pair with grind, NOT a gate to run every day.
3. **The bleed autopsy** — the 22 losses today: are they fades into the trend (expected on a trend day, and the router would've stood it down) or genuine bad entries? Distinguish "wrong regime" from "wrong gate."
4. **Tuning path to +EV on chop** — long-only is a limit on a down-chop day; does a short mirror / a tighter vol band / a VWAP-slope veto (don't fade a trending tape) make it green on chop? This is the [[reversion-edge-quiet-tape-gate-tuner]] lesson (reversion dies fading into grinds — |slope| veto).

**★★ REAL-SAMPLE (2026-07-17 V5-archive replay, 25 days, ceiling pnl): rev = +$723 while grind = −$7,895.** rg_long_fast_v is the QUIET NET-GREEN gate — it validates the operator's hope more than grind's momentum thesis did. It was ~flat-to-green on the choppy days that DESTROYED grind. ⚠ ceiling optimistic → real likely ~breakeven, not clearly +EV yet — but it's the better standalone + the natural chop/floor component of the router ([[direction-regime-gate-enablement]]). Friday: reprice honestly + tune to clearly-green on chop (the |slope| veto so it stops fading trends).

**CAVEATS:** down both live days so far; the +EV-on-chop thesis is UNTESTED (needs an actual chop day where it's measured green). One clear chop day (07-16) it was −$88 (small, not green). Lead with what survives, not the hope. Belongs in the Friday Shadow half alongside [[friday-grind-fast-deep-dive]].
