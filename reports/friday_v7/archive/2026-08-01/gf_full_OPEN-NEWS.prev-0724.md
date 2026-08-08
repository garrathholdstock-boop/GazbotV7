# Greenfield Hunt — OPEN-NEWS cluster (census "full")

**Verdict: GRAVE. No robust edge. survived = false.**

## The target
OPEN/NEWS is the census cluster defined **purely by clock**: every ≥1.5×ATR 15-min run that
starts in the **13:00–15:00 UTC** window — the US pre-open ramp (9:00 ET), the 13:30 cash open
(9:30 ET) and the 14:00 UTC / 10:00 ET data drop. **19 runs** this week (10 sat-out).
Ceiling per run $172–$434. Unlike VACUUM/FLOW-LED, this cluster has **no shared tape footprint**
— it is a time-of-day bucket. The natural mechanical bet for a news window is directional
**volatility expansion**, so the greenfield candidate is a range/opening-range breakout.

Tick coverage 07-19 22:00 → 07-24 21:00 UTC contains all 19 runs (39k–56k ticks per day in-window).

## Invented signal — "News-Window Range Breakout" (mechanical spec)
Active only when 13 ≤ hourUTC < 15. On each 5s bar close t:
- `hiL / loL` = highest high / lowest low of the prior **L** 5s bars (excl. current).
- **LONG**  when `close[t] > hiL + B`   · **SHORT** when `close[t] < loL − B`  (B = breakout buffer, pts)
- Entry: first tick after bar close. Exit variants tested:
  - **fixed**: hard stop STOP pts, target TGT pts.
  - **trail**: hard stop STOP; once profit ≥ ARM, chandelier-trail TRAIL pts from peak.
- Time-cap 15 min, single position, 15-min cooldown. Tick-honest replay (stop checked before
  target within a tick = conservative). Cost $5/RT, MNQ $2/pt.
- Also tested an **anchored ORB** variant: range = [13:30, 13:30+R min], breakout until 15:00.

Tools: `scratchpad/news_bt.py` · `trail.py` · `orb.py` · `sweep.py` · `razor.py` · `stress.py`.
DuckDB over capture.db, 7.3M ticks in numpy.

## Backtest — marginal, then it fails every stress test
- **Base** (fixed, L60/B2/STOP25/TGT60): n=28, **net −$286**, win 28%. Stops −$1045 vs targets +$690.
  A raw breakout is chopped by the window's whipsaw.
- **Fixed-target sweep** (108 configs): only **26 positive (24%)**, scattered spikes, best +$598 (n=25).
- **Trailing sweep** (72 configs): 39 positive (54%) — riding beats a fixed target. Best-looking:
  **A = L24/B5/STOP40/TRAIL20/ARM20: n=27, net +$570, win 85%, 0 losing days.**

## Robustness — every test kills it
Leading candidates: **A** (L24 B5 s40 t20 a20, +$570), **B** (L60 B0 s40 t30 a40, +$557),
**C** (L120 B0 s40 t30 a40, +$403).

1. **Long/short symmetry — the smoking gun.** Isolate each side on its own full trade set:
   - **A**: long-only **−$32** (n=22) · short-only **+$36** (n=24). *Both sides independently flat.*
   - **B**: long-only **−$663** · short-only **+$227**.  (shorts marginal, longs bleed)
   - **C**: long-only **+$144** · short-only **−$273**.  (longs marginal, shorts bleed)
   The winning side **flips** between B (shorts) and C (longs), and A has no side at all. There is
   **no directional edge** — the combined positives exist only because the single-slot 15-min cooldown,
   with both sides enabled, happens to skip each side's losers. A scheduling artifact, not a signal.

2. **Parameter razor-edge (curve-fit tell).** Fine buffer-B sweep at A's fixed L24/s40/t20/a20:
   B0 **+$22** · B2 **−$25** · B3 **−$278** · **B5 +$570** · B7 +$305 · B10 **−$181**.
   A 2-point nudge in the breakout buffer — on a tape swinging 100–200 pts — flips +$570 to −$278.
   The profit is a single knife-edge spike at B5 with negative neighbours on both sides.

3. **Strip-3-best.** B: +$557 → **+$116** (3 trades = 79% of the "edge"). C: +$403 → **+$2**
   (3 trades = 99.5%). The apparent profit is a handful of fat-tail catches, not a base rate.

4. **Big-moves-caught.** Best config (A) aligns-and-profits on **12/19** runs; most configs 8–10/19;
   the anchored ORB variant catches only **8/19**. The signal misses roughly half the very runs it
   was built for, and the half it "catches" is the cooldown-artifact half.

5. **Anchored ORB (different mechanism, same result).** 32 configs, only **9 positive (28%)**,
   best +$410 (n=22), long +$104 / short +$305 (asymmetric, 6-trade long sample), catches 8/19. Weaker.

## Cause of death
The OPEN/NEWS cluster is a **clock bucket, not a footprint** — 13:00–15:00 UTC is a two-sided
whipsaw where runs alternate direction inside the same hour (07-20: UP/DN/DN/UP/DN; 07-23:
DN/UP/DN/DN/DN). A breakout catches the first leg and is stopped/reversed by the next. There is no
real-time directional tell to separate the leg that runs from the leg that fakes. Every positive
config is a razor-edge parameter peak whose profit is a cooldown-scheduling accident that
evaporates on a 2-pt buffer nudge, on side-isolation (no side is independently +EV), or on removing
3 trades. A coin-flip that bleeds. Buried.

## Graves
- **news-window-range-breakout (trail)** — Donchian breakout gated to 13:00–15:00 UTC, chandelier ride.
  Best +$570/85%/27tr, but **long-only −$32 / short-only +$36** (no per-side edge); buffer razor
  B3 −$278 → B5 +$570 → B10 −$181; strip-3 guts kin configs 79–99%; catches 12/19.
  Death: no directional tell in a two-sided whipsaw; win = cooldown artifact on a curve-fit peak.
- **news-window-range-breakout (fixed-target)** — same trigger, hard stop/target. Base **−$286/28%**;
  only 24% of 108 configs positive, scattered. Death: raw breakout chopped, stops −$1045 vs tgts +$690.
- **news-window-ORB (anchored 13:30)** — first-R-min opening range, breakout till 15:00. Best +$410
  but 28% of configs positive, long +$104 / short +$305 asymmetric, catches only 8/19.
  Death: opening range gives no edge over the rolling Donchian; misses 11 of 19 runs.
