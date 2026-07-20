# GAZBOT V7 — Risk-Bounded Sizing

**Status:** BUILT + **LIVE** 2026-07-20 (strategy since 14:18 UTC; both live gates
`risk_budget_usd=80`). Operator: *"build risk-bounded sizing first."*

---

## Why — the always-red solution

The big **never-green** losses aren't a fill or exit-signal problem — they're
**unbounded per-trade dollar risk**. The 1-ATR native stop is correct, but its
*dollar* size = `ATR × stop_atr_mult × value_per_point × qty`, which balloons with
volatility × size:

- **id68:** clean 2-lot fill, straight to a correct 1-ATR stop, but ATR was **31.4pt**
  → 1-ATR × $2 × 2 = **$126** of risk on one trade → −$130.
- **id67:** ATR 23.6 → $94 (2-lot), plus a paper fill artifact.

An exit *signal* cut can't fix this (proven — it clips recoverers; you can't tell an
always-red from a not-yet-green dip at cut time). The give-back can't either (never
green → never arms). **The lever is sizing**: cap the dollar risk so a volatile
entry takes fewer lots.

## The mechanism (`strategy._size_for`)

After the gate's intended qty (conviction 0/1/2 or flat), cap it:
```
per_lot = atr * stop_atr_mult * value_per_point
qty = min(intended, max(1, floor(risk_budget_usd / per_lot)))     # if budget>0 and atr>0
```
- **Floors at 1** when a gate fired — the cap never zeroes a fire (conviction's own
  0-rung still skips chop).
- **Never clips a winner** (unlike an exit cut) — it only changes *size at entry*.
- `risk_budget_usd = 0` → disabled (byte-identical to pre-change).

## Behaviour at `risk_budget_usd=80` (MNQ, $2/pt, 1-ATR stop)

| ATR at entry | per-lot risk | sized to |
|---|--:|--:|
| ≤ 20pt (normal — median MNQ ~13–16) | ≤ $40 | **2 lots** (full) |
| 21–39pt | $42–78 | **1 lot** |
| ≥ 40pt | ≥ $80 | 1 lot (floor) |

So normal-volatility trades keep full 2-lot size; only the volatile outliers size
down. Bounds every always-red at ~$60–80. id68 → 1 lot (−$63 not −$130); id67 →
1 lot (−$47 + a smaller artifact).

## Config
`risk_budget_usd` on `GateSpec` (per-gate) + `RunConfig` (legacy path). Set to
**80** on grind + rgv. **Tunable** — lower = tighter risk / more size-downs;
higher = looser. Revert = `risk_budget_usd=0` on the gates + restart strategy.

## Interaction
- **Orthogonal to conviction** (edge-based 0/1/2) — this is a *risk* overlay on top:
  conviction picks the edge size, the risk cap trims it for volatility.
- rgv's flat-2 edge was validated at 2 lots; the cap sizes it to 1 only on high-ATR
  entries (a deliberate risk trade-off the operator chose).

## Open / not covered
- **entry_atr is not stored on `trades`** (pre-existing) — so post-hoc "did the cap
  bind?" isn't directly joinable. Worth stamping entry_atr for full legibility (§3
  HARD RULE) — flagged, not done here.
- The **id67 paper-fill artifact** is a *separate* problem (capped marketable-limit)
  — parked pending the fill-throughput question.

## References
Analysis: session scratchpad `exitsim.py` (id67/id68 ATR + stop-dist), `flowsolve.py`
(the exit-cut null result). Seams: `strategy._size_for`/`_entry`, `deciders._atr`,
`GateSpec.stop_atr_mult`. Related: give-back (`GIVEBACK_EXIT_SCOPE.md`).
