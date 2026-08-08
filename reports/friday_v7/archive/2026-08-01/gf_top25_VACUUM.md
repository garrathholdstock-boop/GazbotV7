# Greenfield Hunt — VACUUM cluster (census "top25")

**Verdict: GRAVE. Narrowing to the biggest runs did NOT reveal a cleaner footprint. survived = false.**

## The target
VACUUM = a ≥1.5×ATR 15-min run where net aggressor flow in the 60s *before* was heavy (|flow|>50)
but pointed **opposite** to the eventual move — price ran *against* the tape (trapped aggressors →
snap-back / stop-run). Reconstructed 20 VACUUM runs in the tick window (07-19 22:00 → 07-24 21:00 UTC).
Every one has the same sign law: **UP moves ⇐ negative pre-flow, DN moves ⇐ positive pre-flow.**
The census-"top25" hint says: hunt the biggest ones, the marginal ones may be washing out an edge.
The biggest VACUUM runs: +221, +143, −118, −103, +102, +98, +97, −96 pt.

Book only starts 07-21, so the signal is deliberately tape-only (ticks + 5s bars).

## Invented signal — "Trap-Reclaim Absorption Fade" (mechanical, brand-new)
Distinct from a blind flow-fade: it waits for a **reclaim confirmation** of the reversal ignition.
At each 5s bar close t:
- `nf` = signed aggressor flow over trailing `W_FLOW`s (buy +size / sell −size)
- `disp` = close[t] − close[t−W_FLOW]  (did price actually follow the flow?)
- **LONG**  when `nf ≤ −F` (sellers hammering) AND `disp ≥ −DISP` (price refused to fall) AND
  `close[t] ≥ recent-60s-high − RECLAIM` (price is reclaiming the highs → shorts trapped)
- **SHORT** mirror (buyers hammering, price refused to rise, reclaiming the lows)
- Entry: first tick after bar close. Stop `STOP` pt, target `TGT` pt, 15-min time-cap, `COOL`s cooldown.
- Tick-honest exit replay: every 250 ms tick scanned; stop-before-target within a tick = conservative.
  Cost **$5/round-trip**, MNQ **$2/pt**.

Tool: `scratchpad/bt.py` (+ `drive.py`, `robust.py`, `deep.py`). DuckDB over capture.db, ticks in numpy.

## Backtest — two forms, both dead

### Form A — the RUN-CATCHER (wide target, the config that is supposed to *ride* the run)
Best run-catcher **F300 / STOP40 / TGT70**: n=219, **net +$1244**, win 49%.
- **Strip-3-best:** +$1244 → **+$839** (a third of the "edge" is 3 fat tails).
- **Long/short — the smoking gun:** LONG-only **+$121** (a coin flip), SHORT-only **+$956**.
  Almost the entire figure is the short side.
- **It no-shows on the actual big runs.** Aligned P&L on the 8 biggest VACUUM runs (window −120..+600s):
  +221 → **0 trades**; −103 → **0 trades**; −118 → 1 *opposite* trade; the rest are +$10/+$135/−$7
  scalp fragments totalling ≈ **+$263**. The signal built to catch VACUUM runs does not fire in the
  run's direction when the biggest runs actually happen.
- **Razor-edge:** F120/T70 = **−$1734**, F200/T70 = +$1026, F300/T70 = +$1244; widen the target to
  ride more of the run (TGT100) and *every* F flips negative (F200T100 −$88, F300T100 −$656,
  F120T100 −$2705). There is no stable neighbourhood that captures a run.

### Form B — the only robust-looking positive is a REVERSION SCALP that does NOT catch runs
**F300 / STOP40 / TGT30**: n=274, net **+$2110**, win 62%, strip-3 +$1944. Stable on F (280→500 all
positive) and COOL. Looks like a winner — it is a mirage:
- **TGT30 < STOP40** → it exits at +30 pt. It captures 30 pt of a 200 pt run. **Big-caught 7/20, all
  fragments.** It structurally *cannot* do the job the task asks (catch the runs).
- **It is short beta, not a VACUUM edge.** SHORT-only **+$2454** vs LONG-only **+$324**. MNQ fell
  **1316 pt** over the week (29623 → 28307). A short-biased mean-reversion scalp prints in a down week
  by construction; flip the week and the +$2454 short side becomes the loser. This is the exact
  "reversion bleed fading into grinds / short-vol book" the desk has buried repeatedly.
- **The shape knobs sign-flip = curve-fit tell.** At fixed F300/S40/T30: RECLAIM 0→$234, **3→$3573**,
  6→$2110, 10→$718; W_FLOW 45→**−$1105**, 60→+$2110, 90→+$1902, **120→−$732**. The profit lives on a
  knife-edge of the two knobs that define the signal's *shape* — a 15 s / 3 pt nudge triples or
  reverses it. Only the "how-often" knobs (F, COOL) are stable, and those don't encode an edge.

## Parameter sweep (curve-fit razor test)
72 configs (F∈{80,120,150,200,300,450} × STOP∈{15,25,40} × TGT∈{30,45,70,100}): **32/72 positive**,
but neighbours flip violently (F120/S25/T45 −$1583 sits next to F120/S15/T100 +$1532). The positives
concentrate entirely where **TGT<STOP** (reversion scalps, short-beta) — i.e. exactly where the
signal stops being a run-catcher.

## Cause of death
At the moment each big VACUUM run begins, the tape looks **identical to every other absorption
moment** — heavy flow that gets trapped is indistinguishable in real time from heavy flow that keeps
going. Narrowing to the biggest runs made it *worse*, not better: the biggest runs (+221, −103) are
precisely the ones the signal fails to fire on. The only positive is a short-biased 30-pt reversion
scalp whose profit is (a) directional beta to a −1316 pt week and (b) perched on curve-fit knife-edges
of RECLAIM/W_FLOW. A coin-flip that bleeds when asked to actually catch a run. Buried.

## Big-moves-caught
Run-catcher (Form A): **8/20 nominal, ≈0 real rides** — 0 trades on the two biggest (+221, −103);
aligned P&L on the 8 biggest ≈ +$263 of scalp fragments, not run captures.

## Graves
- **trap-reclaim-runcatcher (F300/S40/T70)** — fade heavy 60s flow + micro-reclaim, wide target to
  ride the run. net +$1244/49%; strip-3 +$839; LONG-only +$121 (coin flip), edge all SHORT +$956;
  TGT→100 flips every F negative; **0 trades on the +221 & −103, ~$263 across the 8 biggest.**
  Death: does not fire at the biggest runs; positive only as short beta on a curve-fit peak.
- **trap-reclaim-scalp (F300/S40/T30)** — same trigger, 30-pt target. net +$2110/62%, robust on F/COOL
  but SHORT +$2454 / LONG +$324 = pure short beta to a −1316 pt week; RECLAIM 3→$3573 vs 6→$2110,
  W_FLOW 45→−$1105 vs 60→+$2110 = curve-fit knife-edge; captures 30 pt of 200 pt runs (7/20 fragments).
  Death: reversion-bleed short-vol book masquerading as an edge; does not catch VACUUM runs.
