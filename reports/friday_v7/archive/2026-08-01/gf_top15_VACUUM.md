# Greenfield Hunt — VACUUM cluster (census "top15")

**Verdict: GRAVE. Narrowing to the 15 biggest runs did NOT surface a stronger footprint. survived = false.**

## The target
VACUUM = a census run where, in the 60s *before* a ≥1.5×ATR 15-min move, net aggressor flow was
heavy (|flow|>50) but pointed **opposite** to the eventual move — price ran *against* the tape
(aggressors trapped/absorbed, then a snap-back / stop-run). The cluster has 18 runs this week;
**top15** drops only the 3 smallest (the +80/+80/+82 pt runs), so the target set is essentially the
whole cluster weighted to the big movers: 07-23 19:49 UP +217, 07-24 15:10 UP +146, 07-23 16:39 DN
−117, then a cluster of ~83–102 pt moves. Ceiling per run ~$160–$434.

Tick coverage 07-19 22:00 → 07-24 21:00 UTC contains all 18 runs. Signal is tape-only (book starts
07-21). Tools: `scratchpad/vac_lib.py`, `vac_engine.py`, `vac_sweep.py`, `vac_final.py` (reusing the
shared 7.3M-tick numpy arrays; DuckDB-derived). Tick-honest exit replay (stop checked before target
within a tick = conservative), cost $5/RT, MNQ $2/pt.

## Invented signal — "Trapped-Flow Reversal" (a NEW mechanism, not the full-census fade)
The full-census grave already proved that **fading heavy flow at the moment of heaviness** has no
edge — heavy absorbed flow looks identical to heavy flow that simply keeps going. So this hunt tries
a genuinely different mechanic: **wait for the absorption to fail before entering.**

At each 5s grid point t, over trailing window W:
- `nf` = net signed aggressor flow; `disp` = px[t] − px[t−W]; `hi/lo` = window extremes.
- **LONG-loaded** when `nf ≤ −F` (sellers hammering) AND `disp ≥ −H` (price refused to fall).
- **SHORT-loaded** when `nf ≥ +F` AND `disp ≤ +H` (price refused to rise).
- **TRIGGER (the new part):** do NOT fade immediately. Enter LONG only when price **breaks above the
  window high** (the sellers' ceiling gives way → trapped shorts covering); SHORT only on a **break
  below the window low**. This is meant to skip the "flow that kept going" cases.
- Stop STOP pts, target TGT pts, 10-min time-cap, cooldown CD. Direction = against the trapped flow.

## Backtest — it bleeds, and the trigger didn't save it
- **Base** (W60/F200/H6/STOP25/TGT45, trigger on): n=89, **net −$1040**, win 35%. (No-trigger pure
  fade is worse: n=416, −$2599.) The break-confirmation removes trades but not the bleed.
- **Broad sweep** 648 configs (W∈{45,60,90}, F∈{120,200,300,450}, H∈{4,8,15}, STOP∈{18,25,35},
  TGT∈{30,50,80}, CD∈{180,300}): only **48/648 positive (7%)**, and the whole positive region sits at
  the high-F, n-collapsed corner.

## Robustness — every test fails
Best config the sweep can find: **W60/F450/H8/STOP25/TGT80**, n=16, net **+$242**, win 44%.

1. **n-collapse tell (smoking gun).** Fine F-sweep at fixed STOP25/TGT80/W60:
   F100 −$995(n212) · F150 −$890(n129) · F200 −$878(n87) · F250 −$341(n54) · F300 −$222(n39) ·
   F350 −$202(n28) · **F400 +$10(n22) · F450 +$242(n16) · F500 +$206(n11) · F600 +$261(n10).**
   The signal is negative at every *tradeable* threshold and only turns positive once n falls into the
   teens. The edge **appears only as n collapses** — the textbook curve-fit tell. (H does nothing at
   F450: H4/H8/H15 are byte-identical because so few trades survive.)

2. **Strip-3-best.** The +$242 is **+$465 from 3 trades minus a pile of losers**. The 16 per-trade
   P&Ls: three +$155, one +$128, +$90, +$46, +$8, then **nine identical −$55 stops**. Remove the top 3
   and it flips to **−$224**. The entire "edge" is 3 lucky target hits.

3. **Long/short symmetry.** Isolated: long-only +$88 (n9), short-only +$153 (n7). Neither is a real
   per-side edge — each is a handful of trades resting on 1–2 target hits; there is no directional
   plateau, just small-n noise on both sides.

4. **Big-moves-caught: 1/15.** At the "best" config the signal catches a profitable aligned trade on
   exactly **one** of the 15 biggest VACUUM runs (the −87 at 07-20 16:49). At the higher-n F200 config
   it catches 3/15 but bleeds −$878. It misses the very runs it was built for — because the "break the
   window extreme" trigger fires late, after the snap-back is already spent, or fires on breaks that
   immediately reverse.

## Cause of death
Same verdict as the full census, and narrowing to the biggest runs did **not** wash a cleaner
footprint into view. The VACUUM footprint (heavy flow opposite to the eventual move) is real only in
hindsight; in real time, at the 60s-flow horizon, absorbed flow is **not separable from flow that
keeps running**, and the break-confirmation trigger cannot tell a genuine trapped-short cover from a
noise wick. Every tradeable parameterisation is −EV; the only positives are n=10–16 corner peaks
whose profit is 3 fat-tail target hits and which evaporate on a strip-3 or a threshold nudge. A
coin-flip that bleeds. Buried.

## Graves
- **trapped-flow-reversal (absorption-break fade, top15)** — fade heavy 60s aggressor flow, but only
  after price breaks the window extreme against that flow. Base W60/F200: **−$1040 / n89 / 35% win**.
  Best sweep peak +$242 but at n=16 only, negative at every tradeable F (F100–F350 all lose), strip-3
  → −$224, both sides small-n noise, **1/15 big moves caught**. Death: no real-time separation of
  absorbed flow from continuation flow; the only profit is an n-collapse curve-fit peak built from 3
  target hits.
