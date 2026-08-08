# Execution-Cost Autopsy — SCOPE (2026-07-25)

**Status:** SCOPED, NOT BUILT. Shadow/analysis only — touches no live service.

## Why this exists
The 2026 MNQ falsification study (arXiv 2605.04004) and our own 3-week null both say the
same thing: the **gross directional edge in bar/tape MNQ signals is ~0.07–1.50 pts/trade —
below the ~2-pt round-trip cost.** We have spent 100% of our effort on the *prediction* axis
(predict direction better) and 0% on the *cost* axis (trade the same signal cheaper). Every
gate fires **market orders** and pays the full spread + fee every round trip. If a material
share of the desk's bleed is cost drag rather than wrong direction, capturing part of the
spread flips marginal gates toward green — the north-star (green by end Aug) reachable
*without* a better predictor.

## The core question
Decompose realized desk P&L into **DIRECTION** vs **COST**, and quantify the ceiling
recoverable by passive/limit execution — with an HONEST fill model that cannot cheat.

## Method (four stages)

### 1. P&L waterfall (pure accounting — build first, no modelling risk)
For every live + shadow trade over the archive, decompose:
```
realized = signed_direction_move           (entry-mid → exit-mid, the alpha)
         − entry_half_spread               (we cross the spread on entry)
         − exit_half_spread                (and on exit)
         − fee_per_RT                       ($/round-trip)
```
Deliverable: a waterfall — **gross-direction → −spread → −fee → net** — as $ and as % of
gross. This alone tells us how much of the bleed is cost vs direction. Data: trade ledger
(gazbot7.db) + depth.db for the touch spread at each fill timestamp. **No fill model needed —
this stage is safe and decisive.**

### 2. Passive-entry counterfactual (the hard part — needs an honest fill model)
For each entry, model what a **passive limit at the near touch** would have captured instead
of paying the spread. The crux is the fill model, and it MUST model **adverse selection** —
a passive limit fills *preferentially when the market moves against you* (you get the fill
exactly when you're wrong). A naive "assume it fills at the touch" model produces a FAKE WIN
(same lesson as the run-retention rule). Two honest options:
- (a) **Conservative:** only count a passive fill if price later trades *through* the limit by
  ≥1 tick, and mark the entry at the limit price; if the gate's move never comes back to the
  touch, the passive order **misses the trade entirely** (count it as a no-fill, not a free entry).
- (b) **Queue-position sim** from depth.db: place at back of queue, fill only when cumulative
  traded volume at that price exceeds the queue ahead. More realistic, more work.
Deliverable: net-of-everything P&L under passive entry, **with the missed-trade and
adverse-selection costs fully charged.** Compare to the market-order baseline.

### 3. Microprice-timed entry
When a gate fires, instead of taking immediately, enter at a **microprice-favorable** moment
within a short window (Stoikov microprice = imbalance-adjusted fair value, better short-term
predictor than mid). Measure fill improvement in ticks. Cheap overlay on stage 1.

### 4. VPIN toxicity filter (execution avoidance)
Compute VPIN (volume-synchronized buy/sell imbalance) over the archive; block entries in the
top toxicity decile. Measure loser-removal vs winner-retention (**the retention rule applies —
a filter that removes losers by dropping winners is a fake win**). VPIN is a timing filter,
not alpha (Andersen–Bondarenko: no vol-prediction once trading-intensity controlled).

## Honest caveats / failure modes (read before building stage 2+)
- **Adverse selection is the whole game.** Passive fills are systematically toxic; any model
  that ignores it will manufacture a mirage. Stage 2 must charge missed-trades AND wrong-way fills.
- Paper account market-fills everything — passive execution is genuinely hard to validate in
  paper. Stage 1 (accounting) is trustworthy; stages 2–4 are model-dependent and must be
  reported with the fill-model assumptions stated explicitly.
- In-sample, one summer regime, MNQ. Spread on MNQ is usually 1 tick (0.25pt = $0.50) — so the
  recoverable spread ceiling per RT is bounded; stage 1 will size it exactly.

## Build order
1. Stage 1 waterfall (safe, decisive — do first; if cost is a small share of bleed, stop here).
2. Stage 4 VPIN filter (cheap, retention-checked).
3. Stage 3 microprice overlay.
4. Stage 2 passive-entry sim (only if stage 1 shows cost is a big share — highest modelling risk).

## Tools/data
- gazbot7.db (trade ledger), depth.db (touch spread + queue), archive_data.py (tick mid),
  run with `/home/alphabot/gazbot7/.venv/bin/python`. Read-only, uncommitted, no live service.
