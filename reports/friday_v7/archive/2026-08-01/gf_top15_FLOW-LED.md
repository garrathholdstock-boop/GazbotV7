# Greenfield Hunt — FLOW-LED cluster (census level: top15)

**Verdict: GRAVE. No survivor.** Narrowing from top25 to the 3 biggest, cleanest-flow FLOW-LED
runs was supposed to surface a stronger footprint the marginal runs washed out. It surfaces the
*opposite*: at top15 the squeeze is even more brutal than at top25. To fire on all three big runs
you must loosen the trigger until it bleeds **−$5,099**; the only config that stops bleeding
(**−$681**) catches **0 of 3**. Two independent invented entries — flow-continuation and
flow-confirmed breakout — are underwater in every one of ~40 swept cells. Buried.

---

## 1. The target set — FLOW-LED ∩ top15

The census tagged **17** runs FLOW-LED (60s pre-run net aggressor flow |F|>50 **aligned** with a
≥1.5×ATR 15-min move). Of those, **3** fall inside the 15 biggest moves of the week (|move| ≥ 118pt):

| time UTC | dir | move | census 60s flow | note |
|---|---|---|---|---|
| 07-20 00:02 | UP | +133 | **+228** | thin hour |
| 07-23 06:58 | DN | −119 | **−340** | thin hour |
| 07-23 15:48 | UP | +118 | **+421** | afternoon |

These are the three largest-magnitude aligned-flow prints in the whole cluster (228–421 contracts
vs the marginal cluster's 50–155). If a flow-continuation edge lives anywhere, it lives here. This
hunt tests that hypothesis and it fails.

Data: `data/capture.db` MNQ, 7.30M ticks, 07-19 22:00 → 07-24 21:00 UTC. Tick-honest exits,
$5/round-trip, MNQ $2/pt. Tools in `scratchpad/`: `flowlib.py`, `fwd_flow.py`, `engine_flow.py`,
`hunt.py`, `hunt2.py`.

## 2. The premise dies in the forward study (before any sim)

Forward return conditioned on trailing net signed aggressor **flow**, 10s grid, whole tape and
thin-hours-only (the FLOW-LED domain). Continuation% = forward move shares flow's sign:

| flow bucket | domain | fwd 15m mean | continuation% |
|---|---|---|---|
| F < −200 (strong sell) | thin | **+2.2 pt (UP)** | 48% |
| F > +200 (strong buy) | thin | +1.4 pt | 49% |
| F < −200 | all | +0.1 pt | 50% |
| F > +200 | all | **−2.7 pt** | 47% |

**Continuation sits at 46–53% across every window (30/60/120s) × horizon (5/10/15min).** Strong
*sell* aggression is followed by price drifting **up** (+1.1…+3.4 pt) — mild reversion, not
continuation. Strong *buy* aggression fades slightly negative in the full tape. Aligned flow does
not predict the next move, not even at the magnitudes that produced these three runs. No edge to harvest.

## 3. Signal A — Flow-Continuation Entry (FCE) — primary invention

Spec: `F` = trailing `W`-sec net signed aggressor volume (buy size − sell size). When F **crosses
up** through `+TH` → **LONG** at next tick (ride the aggressors); crosses down through `−TH` →
**SHORT**. Hard stop `STOP` pts. Chandelier: arm at `+ARM` favorable, trail `TRAIL` off peak. Time
cap `CAP` sec, cooldown `CD`, one position. Thin-hours (the FLOW-LED domain).

```
FCE W60/TH250/s20/arm12/tr12 (base):  n=548 net=$-3118 win%=49 med=$-0.5 best=$+112 worst=$-45
   LONG n255 $-1634 · SHORT n293 $-1484 · exits trail341/stop192/time15
```

A coin flip that pays the $5 round-trip 548 times.

## 4. Signal B — Range-Break Flow-Confirmed (RBFC) — structurally different

Price breaks the prior `RB`-sec high/low **and** 60s flow confirms the break direction → enter the
breakout. A classic big-run catcher, independent of pure flow-crossing.

```
RBFC RB1800/THF100:  n=66 net=$-933 win%=41 med=$-13.5 best=$+59 worst=$-45  (catches 1/3)
```

Worse win-rate (36–41% across cells), also fully underwater. Breakouts in this tape mostly fail.

## 5. Robustness suite

**FCE parameter sweep (net$ / n), continuation, thin-hours — every one of 24 cells red:**

```
 W\TH      100        150        250        350        500        750
  30   -5876/874  -5009/745  -1650/470  -2414/308  -1296/168   -681/86
  60   -5099/885  -4722/788  -3118/548  -1731/377  -1758/227   -716/124
 120   -4032/843  -5030/816  -3995/638  -3230/485  -1986/304  -1647/168
 180   -4060/818  -2913/785  -2572/671  -2025/505  -3301/355  -1658/198
```

The least-bad cell (W30/TH750) is **−$681 (n=86)** — reached only by raising the threshold until
almost nothing fires. **The loss asymptotes toward zero from below and never crosses positive** —
the signature of a negative-EV entry where tightening throttles the bleed, the *opposite* of a
curve-fit tell (there is no positive island surviving only at collapsed n). STOP-width sweep does
the same (−$681→−$406→−$507 over STOP 20→30→40): loses less, never wins. All-hours: all red
(−$2,244…−$6,234). **Fade** variant (trade *against* flow): all red too (−$2,120…−$4,246) — it is
the flow *signal* that is dead, in both directions.

**Strip-the-3-best-trades:** FCE(best) −$681 → **−$968** after removing its top-3 (+$287). It gets
*worse* — the bleed is broad-based, no concentrated fat tail to strip.

**Long/short symmetry:** FCE(best) LONG −$368 (n42) / SHORT −$312 (n44). Both sides bleed; no
directional skew — the signal has no edge, either way.

**RBFC sweep:** RB900/1800/3600 × THF 50/100/150, every cell red, least-bad −$492 (RB3600/THF150,
n=39, 38% win).

## 6. The survivorship proof (big-moves-caught, honestly)

The fatal squeeze — you cannot both catch the runs and stop bleeding:

```
FCE W60/TH100 (loose):  catches 3/3   net=$-5099   ON n4 $+42 | OFF n879 $-5112
FCE W60/TH250 (base):   catches 1/3   net=$-3118   ON n1 $+6  | OFF n545 $-3114
FCE W30/TH750 (best):   catches 0/3   net=$ -681   ON n0 $+0  | OFF n86  $-681
RBFC RB1800/THF100:     catches 1/3   net=$ -933   ON n1 $-45 | OFF n65  $-888
```

Only at TH100 does the signal fire on all three runs — and even then the ON-target entries net a
trivial **+$42 across 4 trades** (one target, 07-20 00:02, actually **loses −$45**), while the
identical footprint fires **879 more times off-run and loses −$5,112**. noise:signal ≈ 220:1.
Tighten the threshold to kill that off-run bleed and you immediately stop catching the runs
(3/3 → 1/3 → 0/3). There is no threshold that separates the 3 winners from the ~880 look-alikes —
because forward (§2) there is nothing separating them.

## 7. Cause of death

> **The top15 narrowing did not reveal a stronger footprint — it sharpened the survivorship illusion
> to a knife-edge.** The three biggest FLOW-LED runs carry the cluster's cleanest aligned flow
> (228–421 contracts), yet forward that same strong flow is a 46–53% coin flip, and strong *sell*
> aggression is followed by *up*-drift (reversion, not continuation). Two independent invented
> entries — flow-continuation (FCE) and flow-confirmed breakout (RBFC) — bleed at every one of ~40
> swept cells; the loss only shrinks toward zero as the threshold starves the signal, never crossing
> positive; the bleed is broad-based (strip-3-best worsens it) and symmetric long/short. To catch
> all 3 runs you fire loose and lose **−$5,099** (ON +$42 / OFF −$5,112); to stop bleeding you fire
> so tight you catch **0/3**. **FCE −$5,099 (catch config) / −$681 (least-bad) · RBFC −$933 for the
> week. BURIED.**

Consistent with the top25 and full-cluster graves: FLOW-LED is a hindsight label for runs where
flow happened to align. The live flow edge, if any, is the *contrarian* one (fade exhausted
aggression = VACUUM), which is out of scope here.
