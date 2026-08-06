---
name: exits-are-exit-proof
description: "On the day-rider, 25 exit variants were tested and HOLDING to the flat beat every one — stops, give-back, progress, underwater and reactive rules all lose; only an armed trail helps"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 882eb15b-b9b1-4c08-9348-cd06bd148585
  modified: 2026-08-05T16:26:34.986Z
---

**2026-08-05, MNQ, 31 sessions.** Exhaustive exit search on the day-rider entry. **Holding to the 20:40 flat beat or matched every one of ~25 variants.** Do not re-derive.

```
HOLD to the flat            $13,257   (baseline, 81% green)
armed trail +150/100pt      $13,257 → the ONE improvement, +$2,320 over a plain hold
fixed 400pt target          within $33 of the trail
stops, 7 widths            ALL negative vs baseline; cost/benefit −$6,957 to −$11,572
give-back 25/35/50/65%     ~$0 (−$347 … −$26)
progress ("not running up") ≤ baseline at every T×X; best is −$27
underwater ("losing at T")  −$7,939 to −$9,578
reactive direction-change   best (2xATR reversal) −$3,115
```

**★ WHY STOPS CANNOT WORK HERE — the reason, not just the result.** Winner and loser drawdowns overlap almost completely: winner MAEs run 2…511pt, loser MAEs 66…778pt. **Eight winners drew more than 200pt and still won.** So a stop tight enough to cut losers kills more winners than it saves, and one wide enough to be safe never fires. A 400pt stop's worst day (−$1,603) is *worse* than running naked (−$1,531).

**★ WHY "IT ISN'T WORKING" EXITS CANNOT WORK EITHER.** RUNUP genuinely separates — winners median 355pt vs losers 101pt — but that is measured **at the close**. A winner ending 355pt ahead may be only 50pt ahead at 15:00, so cutting on low runup kills it mid-development. A real ex-post separator that is unusable ex-ante: the same wall the detection work hit, at the other end of the trade.

**★ THE TAIL IS THE PRICE OF THE STRATEGY.** The three worst days ran up only 187, 33 and 80pt before dying, so **no exit mechanism of any kind reaches them**. The −$2,220 day and the +$1,884 day are the same phenomenon. You can have 81% green and $428/day, or you can cut the tail, not both.

**★ AND THEREFORE DEFAULT-HOLD IS PROFIT-MAXIMISING, not merely cautious** — which is why the operator-approval exit defaults to HOLD when he does not reply. An auto-sell default would be worse on both risk and return.

★ METHOD: this is what an exhaustive, *converged* negative looks like — 25 variants, four structurally different families, all pointing the same way. Distinguish it from the premature nulls earlier the same day ([[mgc-momentum-greenfield-null]] method notes) where the operator was right to say "don't give up". See [[day-rider-live-paper]].
