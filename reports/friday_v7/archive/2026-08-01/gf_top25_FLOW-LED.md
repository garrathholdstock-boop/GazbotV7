# Greenfield Hunt — FLOW-LED cluster (census level: top25)

**Verdict: GRAVE. No survivor.** Narrowing from the full FLOW-LED cluster to just the biggest
runs was supposed to reveal a stronger footprint that the marginal runs washed out. It does not.
The five top25 FLOW-LED runs carry *larger, cleaner* aligned aggressor flow than the marginal
ones — and forward that footprint is still a 48–52% coin flip. Every invented entry that catches
the runs bleeds; the one config that stops bleeding no longer catches them. Buried.

---

## 1. The target set — FLOW-LED ∩ top25

From `census_stdout.txt`, the census tagged **17** runs FLOW-LED (60s pre-run net aggressor
flow |F|>50 **aligned** with a ≥1.5×ATR 15-min move, outside the 13–15 UTC open window).
Of those, **5** fall in the top25 biggest moves of the week (cutoff |move| ≥ 105 pt):

| time UTC | dir | move | 60s flow | note |
|---|---|---|---|---|
| 07-20 00:02 | UP | +133 | **+228** | thin-hour |
| 07-21 00:16 | UP | +112 | **+321** | thin-hour |
| 07-23 06:58 | DN | −119 | **−340** | thin-hour |
| 07-23 15:48 | UP | +118 | **+421** | afternoon |
| 07-24 06:57 | UP | +107 | +63 | thin-hour, weak flow |

Four of five are thin-liquidity overnight moves carrying very strong aligned flow (228–421 vs
the marginal cluster's 50–155). If a flow-continuation edge exists anywhere, it should be **here**,
in the biggest, cleanest-flow runs. That is the hypothesis this hunt tests.

Data: `data/capture.db` MNQ, 7.30M ticks, 07-19 22:00 → 07-24 21:00 UTC. Tick-honest exits,
$5/round-trip, MNQ $2/pt. Tools in scratchpad: `prep.py`, `fwd.py`, `engine.py`, `robust.py`, `survivor.py`.

## 2. The premise dies in the forward study (before any sim)

Forward return conditioned on 60s net flow, **thin-hours only** (the FLOW-LED domain), whole tape:

| 60s flow | n | fwd 15m mean | continued% |
|---|---|---|---|
| < −300 (strong sell) | 16,080 | **+4.6 pt** | 45% |
| +150…+300 | 28,710 | −1.2 pt | 46% |
| > +300 (strong buy) | 15,154 | +3.3 pt | 51% |

Signing the forward move *by flow direction* at multiple horizons (strong |F60|>200):
buy→flow gives +0.3…+2.6 pt, sell→flow gives **−0.8…−1.9 pt** (sell aggression is followed by
price drifting **up** = reversion). The positive raw means are just the week's mild up-drift, which
shows up under *both* buy and sell flow. **Continuation% sits at 48–52% across every window
(10–120s) and horizon (5–30 min), and flow-acceleration is 50–51%.** Strong aligned flow does not
predict continuation — not even for the big moves. There is no edge to harvest.

## 3. Signal A — Aggressor Flow Continuation (AFC), strong-flow / thin-hours

Spec: `F` = trailing W-sec net signed aggressor volume. Cross up through `+TH` → LONG (with flow);
cross down through `−TH` → SHORT. Entry market at next tick. Hard stop `STOP` pts. Chandelier:
arm at `+ARM`, trail `TRAIL` off peak. Time cap `CAP`. One position at a time. Thin-hours only.
Primary: `W=60, TH=250, STOP=20, ARM=12, TRAIL=12, CAP=1200`.

```
AFC W60/TH250:  n=851  net=$-5745  win%=47  avg=$-6.8  med=$-1.0  best=$118  worst=$-45
   LONG  n=411  net=$-2842  win%=46
   SHORT n=440  net=$-2902  win%=48
   exits: trail 522 | stop 313 | time 16
   big-moves-caught 4/5
```

A coin flip that pays the $5 round-trip 851 times.

## 4. Signal B — Range-Break Flow-Confirmed (RBFC)

A structurally *different* idea (not pure flow): price breaks the prior RB-second high/low **and**
60s flow confirms in the break direction → enter the breakout. Classic big-run catcher.

```
RBFC RB1800/TH150:  n=311  net=$-2848  win%=46  best=$144  worst=$-45
   LONG  n=145  net=$-1240  win%=48 | SHORT n=166  net=$-1608  win%=45
   big-moves-caught 2/5
```

Also underwater, and it catches fewer of the target runs. Breakouts in this tape mostly fail.

## 5. Robustness suite

**AFC parameter sweep (net$ / n), thin-hours — every cell underwater:**

```
 W\TH        150         250         350         500         750
   30  -8583/1154  -5170/761   -4107/481   -1630/266    -642/112
   60  -6357/1153  -5745/851   -2589/570   -2319/338    -870/150
  120  -6068/1123  -6518/912   -3740/684   -2870/433   -1742/241
  180  -5559/1056  -4875/906   -3774/716   -3610/486   -2004/280
```

The least-bad cell (W30/TH750) is **−$642 (n=112)** — and it gets there only by raising the
threshold until almost nothing fires. The loss **asymptotes toward zero from below and never
crosses positive.** This is the *opposite* of a curve-fit tell (no positive island that survives
only at collapsed n) — it is the signature of a negative-EV entry where tightening merely throttles
the bleed. Widening STOP does the same (−$6,582 → −$4,614 from STOP 10→40): loses less, never wins.

**RBFC sweep:** same — 16 cells, all red, least-bad −$1,577 (RB3600/TH250, n=169).

**Strip-the-3-best-trades:** AFC(best) −$642 → **−$1,026** after removing its top-3 (+$384 total);
RBFC(best) −$1,577 → **−$1,822**. Both get *worse* — the bleed is broad-based, there is no
concentrated fat-tail edge to strip.

**Long/short symmetry:** AFC(best) LONG −$320 / SHORT −$322; RBFC LONG −$548 / SHORT −$1,029.
Both sides bleed — it is the *signal* that has no edge, not a directional skew.

## 6. The survivorship proof (big-moves-caught, honestly)

At the config that actually catches the runs (AFC W60/TH250):

```
big-moves-caught 4/5:  07-20 00:02 +$36 · 07-21 00:16 +$75 · 07-23 06:58 MISS ·
                       07-23 15:48 +$43 · 07-24 06:57 +$58
ON-target entries  (±[-120s,+300s] of a run):  n=8    net=$ +212
OFF-target entries (everywhere else):          n=843  net=$-5956   <- the bleed
noise:signal = 843:8
```

The signal genuinely fires on 4 of the 5 big runs and wins +$212 on those 8 entries — because the
census *defined* the runs by flow having aligned with them. But sampled honestly, the identical
footprint fires **843 more times** and loses **−$5,956**. And here is the fatal squeeze: the
least-bad configs (W30/TH750, RBFC3600/250) catch **0/5 and 1/5** of the runs. To catch the runs
you must fire loosely and bleed heavily; to stop bleeding you fire so tightly you miss them. There
is no threshold that separates the 5 winners from the ~840 look-alikes — because forward there is
nothing separating them (§2).

## 7. Cause of death

> **The top25 narrowing did not surface a stronger footprint — it reconfirmed the survivorship
> illusion at higher flow magnitude.** The five biggest FLOW-LED runs carry the cleanest aligned
> flow of the cluster (228–421 contracts), yet forward that same strong flow is a 48–52% coin flip
> in thin hours; strong *sell* aggression is actually followed by up-drift (mild reversion). Two
> independent invented entries — flow-continuation and flow-confirmed breakout — bleed at every one
> of 40+ swept parameter cells; the loss only shrinks toward zero as the threshold starves the
> signal, never crossing positive; the bleed is broad-based (strip-3-best worsens it) and
> symmetric long/short. The catching config nets +$212 on 8 on-run entries and −$5,956 on 843
> off-run firings. **AFC (strong-flow) −$5,745 · RBFC (breakout) −$2,848 for the week. BURIED.**

Consistent with the full-cluster grave: FLOW-LED is a hindsight label for runs where flow happened
to align; the live flow edge, if any, is the *contrarian* one (fade exhausted aggression = VACUUM),
out of scope here.
