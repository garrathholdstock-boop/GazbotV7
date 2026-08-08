# Greenfield Hunt — FLOW-LED cluster (census level: full)

**Verdict: GRAVE. No survivor.** A flow-continuation entry catches 15/17 of the census's
FLOW-LED runs and *still* loses -$7,907 over the week. The cluster is a survivorship artifact.

---

## 1. What "FLOW-LED" is

From `scripts/run_census.py`, a run is tagged **FLOW-LED** when, in the 60s *before* the
15-min move, net aggressor flow was large (|flow| > 50 contracts) **and aligned** with the
move (buy flow → up run, sell flow → down run), outside the 13–15 UTC open window. The
census reads this as "aggressors drove it — a continuation." 17 runs qualified this week;
12 were sat out (money on the table). The greenfield brief: invent an entry to catch them.

The obvious mechanical read of that footprint is a **continuation** entry: when trailing
net aggressor flow crosses a threshold, enter *with* the flow.

## 2. The invented signal — Aggressor Flow Continuation (AFC)

Exact mechanical spec (the thing I backtested):

- **State**: `F = ` trailing `W`-second net signed aggressor volume (Σ buy size − Σ sell size),
  built from `capture.db` ticks bucketed to 1s.
- **Trigger LONG**: `F` crosses **up** through `+TH`. **Trigger SHORT**: `F` crosses **down** through `-TH`.
- **Direction**: with the flow (continuation).
- **Entry**: market, at the first real tick after the trigger second.
- **Stop**: `STOP` pts adverse from entry (hard).
- **Exit**: chandelier trail — arm at `+ARM` pts favorable, then trail `TRAIL` pts off the peak
  favorable excursion; hard time cap `CAP` s; otherwise market at cap.
- **One position at a time**; re-arm requires a fresh cross after the prior exit.
- Exits walked on **raw ticks** (tick-honest, per the sims-on-tick-price rule). Cost **$5/round-trip**, MNQ $2/pt.

Primary parameters: `W=60, TH=150, STOP=20, ARM=12, TRAIL=12, CAP=1200`.

Tools: `scratchpad/afc_bt.py` (sim), `scratchpad/afc_robust.py` (robustness). Source data
`data/capture.db` MNQ ticks 07-19 22:00 → 07-24 21:00 UTC (7.30M ticks).

## 3. The premise fails before any sim — forward-return study

Unconditional forward return conditioned on 60s net flow (whole tape, not the cherry-picked runs):

| 60s net flow | n | fwd 15m mean | %continued |
|---|---|---|---|
| > +300 (strong buy) | 24,364 | **−3.6 pt** | 47% |
| +150…+300 | 31,899 | −1.6 pt | 46% |
| −150…−300 (strong sell) | 35,205 | +0.2 pt | 48% |
| < −300 | 26,034 | +0.4 pt | 51% |

corr(60s flow, fwd 15m) = **−0.012**. Strong buy aggression leads a *slightly down* tape;
strong sell aggression a *slightly up* tape. **Flow leads mild reversion, not continuation.**
Tested at 120/300/600/900s horizons, at 10/15/30/60/120s flow windows, and with a
price-momentum alignment filter (flow AND price already moving the same way) — **every variant
gave %continued of 46–52% and mean forward ≤ 0.** There is no continuation edge to harvest.

## 4. Tick-honest backtest — primary spec

```
ALL:   n=1482  net=$-7907  win%=50  avg=$-5.3  med=$+0.5  best=$+153  worst=$-45
 LONG: n= 721  net=$-4146  win%=50
 SHORT:n= 761  net=$-3761  win%=50
 exits: stop 556 → -$25,020 | trail 910 → +$17,082 | time 16 → +$31
```

A literal coin flip (50% win) that bleeds. The trailing exit wins small and often
(910 trails, +$18.8 avg) but the 556 stop-outs at −$45 swamp it — the classic signature of a
**negative-EV entry that no exit can rescue.**

## 5. Robustness suite

**Parameter sweep (net$ / n) — every cell underwater, no positive island:**

```
 W\TH        80         120         150         200         300         450
   30   -9676/1794  -9686/1664 -10986/1570  -9478/1372  -4562/1009  -4732/684
   60  -10020/1628  -8057/1576  -7907/1482  -8090/1351  -6445/1041  -4876/740
  120   -5684/1373  -6890/1394  -7221/1363  -6834/1287  -6338/1068  -5895/778
  180   -5292/1218  -5660/1246  -5545/1248  -5104/1201  -4598/1018  -4934/771
```

The **least-bad** config across a 72-cell grid (W×TH×STOP) is W=60/TH=450/STOP=30 at
**−$2,947 (n=634)** — still a loss. This is *the opposite* of a curve-fit tell: there is no
positive peak that only survives at collapsed n. Raising TH (fewer, "cleaner" signals) and
widening STOP merely **loses less** — it asymptotes toward zero from below and never crosses.
The forward-return study explains why: the entry is negative-EV, so tuning the exit only
throttles the bleed.

**Strip-the-3-best-trades:** full −$7,907 → minus top-3 −$8,318. The three best trades are
only +$115/+$144/+$153; removing them barely moves it. The loss is **broad-based**, not a
fat-tail artifact — there is no concentration of edge to strip.

**Long/short symmetry:** LONG −$4,146 (50% win) vs SHORT −$3,761 (50% win). Symmetric bleed
both sides — it is the *signal* that has no edge, not a directional skew.

## 6. Big-moves-caught — the survivorship proof

AFC entries within [−120s, +300s] of each FLOW-LED run start, in the run's direction:

**Caught 15/17 FLOW-LED runs**, and on those exact entries it netted **+$664** (14 of 15 green).
The signal genuinely shows up for the runs the census flagged.

**That is the whole story.** The census defines FLOW-LED *by* flow having aligned with a big
move — so of course a flow trigger fires on them and wins there (+$664 on ~17 entries). But
sampled honestly across the entire week the same trigger fires **1,482 times** and the other
~1,465 firings lose **−$8,571**. The 17 "FLOW-LED" runs are the winners a hindsight filter
kept; the tape is full of identical flow surges that went nowhere or reversed. Narrowing to
the *biggest* runs makes it worse, not better: the strong-flow bucket (>300) has the most
negative forward return (−3.6 pt). No stronger footprint hides under the marginal runs.

## 7. Cause of death

> **Aggressor-flow-continuation is a survivorship illusion.** The FLOW-LED cluster is the set
> of runs where flow *retrospectively* aligned; forward, 60s net flow has ~zero correlation
> (−0.01) with the next 15 min and if anything leads mild reversion. A mechanical flow-with-it
> entry is a 50/50 coin flip that pays the $5 round-trip on every one of 1,482 firings.
> Every point in a 72-cell sweep loses; the bleed is broad-based; both sides bleed equally.
> −$7,907 for the week. **BURIED.**

The live tape's real flow edge, if any, is the *contrarian* one (fade exhausted aggression =
the VACUUM cluster) — out of scope here, flagged for that hunt.
