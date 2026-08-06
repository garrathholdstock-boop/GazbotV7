---
name: shadow-board-as-regime-router
description: "⚠TITLE IS THE SUPERSEDED IDEA — READ THE REFRAME AT THE BOTTOM. Shadow-P&L-drives-live-on/off is 'trading the equity curve' and it FAILED: autocorr ≈0 for momentum, −0.16 for rgv (switching actively HURTS). Shadow's real jobs are INCUBATION + CORRELATION MONITORING, never regime detection. Read the tape first — [[read-the-tape-first-shadow-is-confirmation]]."
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f130de1-fe42-4097-b16c-315bc9433aff
  modified: 2026-08-06T15:20:36.589Z
---

> ⚠⚠ **2026-08-06 — THIS FILE'S TITLE AND OPENING ARE THE IDEA THAT WAS TESTED AND REJECTED.** The
> reframe at the very bottom supersedes everything above it, and it was already there — I read the
> title, acted on "shadow IS the regime router", and never reached the retraction. On 08-06 that put
> the desk SHORT at the low (shadow was green on shorts because the down-leg had just ended) and FLAT
> through a +297pt rally (shadow only flipped green on longs once the move was 297pt old). The shadow
> board is BACKWARD-LOOKING; using it to pick direction means trading the regime that just ended.
> **Read the tape and the chart FIRST; consult shadow LAST, only to confirm.**
> See [[read-the-tape-first-shadow-is-confirmation]].

**2026-07-18 operator insight (verbatim spark): "live grind is linked to shadow grind. maybe shadow becomes our regime router!!!"**

The unifying idea for the desk. We proved three things tonight on grind_fast: regime is UNPREDICTABLE at the open; feature-classifiers (15-min VWAP slope, [[regime-chop-veto-momentum]]) do NOT cleanly separate a gate's good days from its bad; but a gate's **own live shadow P&L directly measures whether its edge is present RIGHT NOW**. So the shadow board stops being a lab and becomes the live CONTROLLER: every gate runs in shadow (free/observe-only), and live capital follows whichever gates are currently earning in shadow — grind live-ON when grind's shadow is hot, OFF when it bleeds, re-armed when it recovers. Reactive, self-calibrating, per-gate. This is [[favourable-condition-gating-vision]] realized, and it supersedes the feature-based [[monday-shadow-build-queue]] regime router as the mechanism. Bigger than grind — it's the whole-desk router.

**Evidence built (grind_fast, 25-day V5 1m basis, optimistic ceiling — honest tick is worse):**
- grind standalone −$7,976; its 5 good days = +$4,986, the other 20 bleed. The whole game is a day-selector.
- Its good days are green-early / bad days red-early & STAY red (5/5 top green by 14:00; 0/11 big-bleed days ever green). So day-type IS readable from grind's own P&L, not from market features.
- Static −$300 intraday drawdown governor: −$7,976→−$1,306, keeps all 5 good days (never dips −$300 first), but pays ~$300 tuition × ~18 bad days.
- Static "shadow-probe overnight → live for RTH only": +$473–629 (first green) BUT forfeits front-loaded good-day money (06-23 made its entire +$1,284 pre-open, LOST in RTH).
- DYNAMIC shadow→live governor (trailing-W-hr shadow P&L, on/off thresholds, re-entry), swept W=1/2/3/4h: captures ~$3,800 of the $4,986 upside INCL 06-23's front-loaded money (2× the static rule) — but nets −$700 to −$1,800 because **re-entry CHURNS** (chop days string 2 quick wins, re-arm live, bleed, repeat). Concept right, predictor too noisy.

**BUILT + SWEPT (2026-07-18): `gazbot7/governor.py` (committed 7ddcbb8, 6 tests) — the shadow→live controller, 4 predictors (window/sticky/streak/slope), flip-count = churn metric, no look-ahead.** Swept across grind + both reversion gates. ★WINNER = **streak (arm live after 3 consecutive shadow WINS, disarm after 2 losses)** — the ONE predictor that's green on ALL THREE gates and improves every one:
- grind_fast (chandelier): −6,323 → **+722** (11% live)
- rg_long_fast (2R): +206 → **+502** (10% live)
- rg_long_fast_v (2R): +590 → **+941** (7% live) — the ★#23 chop-reversion gate, now genuinely +EV
- COMBINED book: −5,527 → **+2,165** (~$7,700 swing, green).

**★ Operator rule (2026-07-18): reversion gates need a fixed 2R exit (exit_scalp target_r=2.0, stop 1-ATR), NOT the chandelier — momentum rides, reversion takes 2R.** [[exit-architecture-scar-tissue]]. The 2R fix alone flipped rg_long_fast −11→+206.

**Why streak wins:** 3 straight shadow wins is a signal chop can't fake; keeps each gate OFF ~90% of the time, only commits when hot → no whipsaw. Naive trailing-P&L window CHURNS and loses on all three. Discipline beats sensitivity. Same predictor works momentum AND reversion = a real router, not a grind hack.

**Caveats: optimistic 1m ceiling (honest tick worse, ~breakeven-to-green); IN-SAMPLE (swept+picked winner); only 7-11% live = small live sample.** Per-side circuit breaker [[direction-regime-gate-enablement]] = same self-governor family.

**★ FORWARD-VALIDATED VERDICT (2026-07-18, DECISIONS §345 in alphabot2 — the session-end truth):**
- **grind_fast good/bad DAYS are UNPREDICTABLE** — proven exhaustively (tape, day-character [most-directional day was a big LOSER], amplitude corr +0.06, 15-min regime, direction split [hindsight +$2,954 but reactive whipsaws −$1,960], cross-gate, 4-agent OOS hunt on trade-texture/geometry/cadence/ML → all CHANCE via permutation + duty-matched-random). Decisive: a slow-start green day dipping −$476 is geometrically identical to a red death-spiral at the decision point. **The fix is TOLERANCE not prediction** (operator).
- **grind KEPT (operator overruled my "park it"): gated by a PEAK-TRAIL −$300 day-latch** (stand down once P&L gives back $300 from the day's high) — keeps every ~$1,300 day in FULL (a winner never retraces $300 from peak), cuts every bleed day (−$1,239→−$43). Raw −$6,323 → +$1,244 in-sample; **frozen −$300 = −$54 (breakeven) on held-out last 12 days** (a RE-TUNED latch overfits to −$368 — freeze it, don't re-tune). Grind's value = TREND-DAY COVER for rgv (corr −0.62; its winners = rgv's worst days).
- **rg_long_fast_v = the +EV keeper**, 2R exit (operator: reversion needs 2R not chandelier) + flat −$400 latch: +$590 raw, walk-forward **OOS +$1,881** (survives, better than in-sample). Two-gate combined +$1,107 (frozen) / +$1,512 (walk-forward) OOS.
- **DESK MODEL:** stable of thin (~$1-1.3k/mo, operator: "stomachable per gate") COMPLEMENTARY forward-validated gates; shadow board routes; anti-correlation smooths. NEXT = a TREND-side gate that survives OOS to pair with rgv (report's exhaustion-reversal footprint / better momentum entry), then forward-paper, then operator go-live. **Method locked: eval vs DUTY-MATCHED RANDOM (not always-on); forward/walk-forward with prior-only params before promotion.**

Built: gazbot7 `governor.py` (7ddcbb8), `chandelier_start_k` (6376657), `router.py` (31ddf68/c7e04df), `scripts/forward_validate.py` (63b320c). Scratchpad experiments: peak_trail.py / tolerance_stack.py / portfolio.py / frozen_oos.py / rgv_deepdive.py / day_character.py / grind_mechanisms.py. NOTHING ARMED.

**EXHAUSTION-REVERSAL gate hunt (2026-07-18, agent-built on capture.db ticks+book, 3 days only):** the microstructure fade (rolling 20s net signed tape ≥250 one way + price moved ≤2pt + near-touch wall on hit side → FADE opposite; 8pt stop/12pt target/120s). **Verdict: real direction, SUB-COST, not significant on 3 days.** Spec (net≥250) = −$0.87/tr after $1 cost; tightening to **net≥400/move≤2pt/wall≥1.5** flips positive (+$1.24/tr, ~30/day, positive all 3 days) via a sensible mechanism, BUT every config's 95% CI straddles zero (t<2; per-trade SD ~$20 dwarfs the edge; 32 configs swept). **KEY: it GENUINELY DIVERSIFIES rgv** — 70% non-overlapping timing, TWO-SIDED vs rgv's long-only, hourly P&L corr −0.13. So it's the right KIND of second gate (a real diversifier, the property that matters) but unproven — needs the multi-week microstructure capture (only 3 days of L1 tape+L2 book exist in capture.db; depth.db has more L2 but no aggressor tape). PATH: incubate SHADOW/observe-only at net≥400/move≤2/wall≥1.5, accumulate ~15-20 days/300+ trades, re-decide on COMBINED equity with rgv. Bottleneck across the whole desk = SAMPLE SIZE. Agent scripts: scratchpad er_engine.py / er_task1-3.py.

**★★ REFRAME (2026-07-18, from web research + our own autocorrelation test — supersedes the on/off framing above):** Shadow-P&L-drives-live-ON/OFF is the named technique **"trading the equity curve"** and the serious evidence (Carver's random-data test, Davey, Chan, Clenow; López de Prado on overfitting/deflated-Sharpe) says binary on/off switching of individual strategies usually HURTS — **"an unmitigated disaster" for momentum** (negatively autocorrelated → you switch off into the recovery). **Confirmed on our data: lag-1 autocorrelation ≈ 0 for grind/thrust (momentum, switch useless), −0.16 for rgv (reversion, switch HURTS).** So:
- **DEMOTE the streak/dynamic governor** (`governor.py` timing predictors) — it's the weak "trade the equity curve" case; the autocorr says no timing edge exists to exploit.
- **KEEP the peak-trail latch but RE-LABEL it: a per-day MAX-LOSS CIRCUIT BREAKER** (caps the catastrophic tail, e.g. −$1,000 day → −$400) — the ONE use the literature endorses (Chan). It's why the latch beat duty-matched random (loss-capping, NOT hot-hand timing). Risk control, not alpha.
- **THE REAL EDGE = ANTI-CORRELATION** (thrust −0.19 / grind −0.62 vs rgv). "Diversification is the only free lunch." Run the complementary gates ALWAYS-ON, sized by risk/correlation; the anti-correlation smooths the book. Continuous risk-weighting > binary switches (Carver handcrafting).
- **Shadow board's real jobs = INCUBATION (100+-trade track record before go-live) + CORRELATION/RISK MONITORING**, not on/off routing. Before promoting: DEFLATE Sharpe for the ~6 variants screened; require 100+ trades not 17 days; keep the duty-matched-random benchmark (Build Alpha vs-random test).
- **Refined desk model:** 2+ anti-correlated gates (thrust trend + rgv chop) always-on + per-day max-loss circuit breaker each + risk-weighted; shadow = incubator + correlation monitor. Sources incl. qoppac.blogspot.com (Carver equity-curve + handcrafting), kjtradingsystems (Davey), epchan (Chan life/death of strategy). Full brief in this session's transcript.
