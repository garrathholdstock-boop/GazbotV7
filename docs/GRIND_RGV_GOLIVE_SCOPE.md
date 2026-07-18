# GRIND + RGV GO-LIVE SCOPE (2026-07-18, weekend build → Sunday-night go-live)

**Operator decision:** replace the live `thrust_loose` gate with **grind_fast** (vol-adaptive
chandelier exit + 0/1/2 Efficiency-Ratio conviction sizing) **+ rg_long_fast_v** (2R exit,
flat 2). All 3 gates (grind/thrust/rgv) keep running **shadow/observe-only**. PAPER desk.
Max 4 lots. Build over the weekend, robust + tested, arm Sunday night.

**Honest bounds (carry into go-live):** this is PAPER forward-validation on real fills, NOT
real-money-ready. Backtest numbers are optimistic 1m-ceiling (~60-70% on real fills) — expect
the paper book below the +$1,978 OOS. Watch it accumulate 100+ live trades before any real money.

---

## 1. THE ARCHITECTURE DECISION (shapes the whole build)

The live desk (`desk.py FuturesDesk`) today is **single-gate, single-position, single-size**:
`if flat → one gate decides entry; if in position → manage one exit`. Running grind AND rgv
concurrently on the SAME symbol (MNQ) means two positions sharing one broker net — which needs
**per-gate fill attribution on a shared net position** (grind long 2 + rgv long 2 = broker net
long 4; each gate must track & exit ITS own 2). That attribution layer is exactly the fragile
V-LEDGER area that has caused position-truth incidents (see memory `vledger-phase4-completion`,
`position-orphan-entry-atr-cascade`). It is buildable robustly, but it is the risk.

**Two designs:**

- **A — SINGLE-POSITION, TWO-GATE (RECOMMENDED, robust).** When flat, evaluate both gates;
  take whichever fires (grind trend / rgv chop). Tag the open position with its gate so the
  right exit + sizing apply. **No attribution problem, the existing one-position safety/tracker
  just works.** Cost: can't hold grind AND rgv at once → max 2 lots, not 4. But they fire in
  different regimes (OOS corr −0.23) so they rarely want a position at the same moment —
  captured P&L is ~the same. **"Robust" argues for this.**

- **B — CONCURRENT MULTI-POSITION (what was specced, 4 lots).** Two virtual positions on the
  shared MNQ net, per-gate attribution + per-gate stop/exit. Higher ceiling, materially more
  code + the attribution risk. Needs the careful virtual-position ledger done right.

**Recommendation: build A.** It gets grind + rgv trading the paper desk this weekend, robustly,
with the safety we already trust; if the paper book proves the edge, upgrade to B later. Open
question for the operator: **A (robust, max 2 lots) or B (concurrent, max 4)?**

---

## 2. COMPONENTS (each pure + unit-tested BEFORE any desk wiring)

1. **grind live gate** — `gate_grind(slope_min=0.4, fast_slope=True)`; exit = vol-adaptive
   chandelier (`chandelier_start_k(entry_atr)` → start_k) + native 1-ATR stop. (Already built +
   tested: `deciders.chandelier_start_k`, `exit_chandelier`.)
2. **ER conviction sizing** — `lots = 0 if ER<lo else 1 if ER<hi else 2`, ER = Kaufman
   efficiency ratio over the trailing 30×1m closes at entry. Thresholds FROZEN from the
   walk-forward (lo/hi ≈ 0.25/0.45), NOT re-tuned live. New pure fn + test. lots=0 → no trade.
3. **rgv live gate** — `gate_reversal_grab(side="LONG", ext_min=2.0, turn_atr=0.15,
   fast_slope=True, fast_turn=True, atr_min=13.0)`; exit = `exit_scalp(target_r=2.0,
   stop_atr_mult=1.0)` (2R). Flat 2 lots. (Gate + exit already exist.)
4. **thrust → shadow-only** — remove `thrust` from the live desk config; it stays in the shadow
   slate. (Config change.)

## 3. SAFETY (non-negotiable — zero-tolerance naked positions)
- Every position keeps the **native 1-ATR broker stop** (per-gate). Design A inherits it directly.
- Naked-position watchdog + arm-time stop-confirm + venue-audit loop must cover the live gate(s)
  exactly as today (memory `naked-position-from-silent-auditor-skip`).
- Kill-switches: daily-loss + streak caps still apply to the desk aggregate.
- Session-end flatten backstop covers all open gate-positions.
- Design B additionally: the per-gate virtual ledger must reconcile to the broker net every
  cycle, and a mismatch is a CRIT (naked/ghost detection per-gate).

## 4. TEST PLAN
- Unit tests: conviction-sizing fn, per-gate exit routing, gate selection when flat.
- **Replay dry-run** against captured 1m data (15-17 Jul): the live desk logic (paper, no
  submit) produces the same trades as the backtest for grind (conviction) + rgv → parity check.
- Safety smoke: naked-watchdog fires on a simulated unprotected position; session-flatten closes
  all gate-positions.
- Full `pytest` green; live-path smoke-import clean.

## 5. STAGED BUILD ORDER (weekend)
1. Pure components + tests (§2) — zero live-path risk. ← start here
2. Desk wiring for the chosen design (A or B) + tests.
3. Replay parity dry-run (paper, no submit).
4. Safety smoke.
5. Deploy Sunday **before** the session opens, `GAZBOT7_PLACE_LIVE=1`, verify flat+healthy +
   the go-live checklist, watch the first fills.

## 6. GO-LIVE CHECKLIST (Sunday night, before arming)
- [ ] full suite green; replay parity confirmed
- [ ] verify desk flat + healthy (`core_health.json`) before arming
- [ ] confirm live gate lineup = grind(conviction) + rgv; thrust shadow-only
- [ ] confirm broker short-cap matches max lots (memory: cap must match size)
- [ ] naked-watchdog + stop-confirm armed; kill-switches set
- [ ] first-hour watch (first fills reprice honestly; execution-integrity alarm live)
