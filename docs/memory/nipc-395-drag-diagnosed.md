---
name: nipc-395-drag-diagnosed
description: "NIPC's $395 live/replay drag is TRIGGER-TIMING divergence (59%) + one lost exit race (38%), NOT slippage and NOT signal selection; and n=16 makes it 2 trades"
metadata: 
  node_type: memory
  type: project
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-04T13:49:49.452Z
---

2026-08-04, operator: "diagnose the $395 drag". SOLVED — `scripts/nipc_drag_ladder.py`.

NIPC ran live on exactly ONE day (2026-08-03): 30 trades = 16 signals x 2 lots, **−$280**. Replaying the
SHIPPED `NipcTracker` on the same tape gives **+$204** blanket.

## The ladder — each rung is one real production difference (all reproduce exactly)
| rung | n | net | delta |
|---|---|---|---|
| acceptance headline (blanket, raw ticks, 1 lot @2.5R) | 16 | +225 | |
| + regime BLOCKED at detection (production) | 11 | +79 | **−146** |
| + 1s tape cadence (T_TAPE, not raw ticks) | 12 | +58 | −21 |
| + live lot ladder A@2.0R + B@2.5R (exit_overrides) | 12 | +115 | +56 |
| LIVE ACTUAL | 16 | **−280** | **−395 residual** |

## The −$395, attributed (sums exactly)
| cause | $ | note |
|---|---|---|
| **TRIGGER-TIMING divergence** | **−232** | live & replay resolve the SAME setup 66–112s apart, at very different prices. One case (13:45:52) is −$248 alone. |
| **one lost EXIT RACE** | **−150** | 14:47:12 — entries within 3s, live STOPPED where replay hit TARGET |
| signal-set difference | −21 | live-only 7 signals **+$21**, replay-only 3 **+$42** |

## ★ THREE PRIORS THIS KILLED
1. **NOT broker slippage.** That was my hypothesis. Median entry slip on genuinely same-fill pairs
   (entry within 5s) is **+2.25pt** (~$9/signal across 2 lots), ~$52 total, largely offset. Small.
2. **NOT bad signal selection.** The 7 signals live took that the replay never generated were net
   **POSITIVE (+$21)**. Live's extra fires are not the problem.
3. **NOT fixable by R or stop tuning.** Both dominant causes are TIMING, not geometry.

## ★★ THE METHOD TRAP — a 120s match tolerance invented "36pt of slippage"
My first pass paired live↔replay signals within 120s and reported a mean entry slip of +3.97pt with a
+36.62pt outlier, attributing −$235 to "entry slip". Wrong: those pairs were **66–112s apart**, i.e. NOT
the same fill at all — a different pullback resolution. Tightening to ≤5s showed the true same-fill
slippage is ~2.25pt median and moved −$232 into its correct bucket (trigger timing). **When pairing two
books, the match tolerance IS an assumption — state it and test it.** cf. [[mfe-is-not-a-win-rate]].

## ★★ AND n MAKES ALL OF IT PROVISIONAL
**Two signals carry ~$398 of the $395.** This is one day, 16 signals. It is not a stable "execution
drag" — it is a timing bug plus two bad breaks. Do not quote −$395 as a per-day expectation.

## Status / next
NIPC stays BENCHED (`nipc_long=off`/`nipc_short=off`, PINNED in the router, in
`reactivate_gates.py::HOLD`), but the REASON has changed from "unexplained drag" to "diagnosed
trigger-timing divergence". Fix before re-arming: why does the live 1s-cadence state machine resolve a
pullback 1–2 min away from the tick replay? That is a real bug class and it also explains the lost exit
race (live cannot see a target touched between 1s snapshots). Re-judging the GATE needs far more than 16
signals. Related: [[stop-width-ab-2x-live]] (same 1s-vs-tick cadence theme), [[sims-on-tick-price]].
