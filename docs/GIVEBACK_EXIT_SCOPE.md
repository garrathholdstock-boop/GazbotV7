# GAZBOT V7 — Dollar Give-Back Exit (the missing "ratchet 2")

**Status:** BUILT + **LIVE** 2026-07-20 (strategy since 13:10 UTC; both live gates
`giveback_enabled=True`, arm $50 / gb $40). Operator overrode the shadow-first rail
("build it and make it live") — ⚠ so it is live on the desk while validated only at
1-lot on shadow (2-lot depths proven on the live sim). Implemented in
`deciders.exit_giveback` + `strategy._manage`; +4 tests. The scope below is as-built.

---

## Why (the evidence)

Operator: *"I'm not happy taking the big losses when a trade goes wrong … we must
know a trade is cooked much before −$120–150."* An L2 study of every trade since
07-13 + a shadow-board forward-validation (170 trades, tick-repriced) found:

- The deep losers are **not cooked early** — they go **green (or oscillate), then
  reverse hard** (id53: +$85 green → −$150; id61: +$68 → −$122). A *static* earlier
  cut can't tell those from a dip that recovers (id57: −$60 → won), so it either
  clips winners or fires too late — the "too early last week" failure.
- The separator is a **profit give-back ratchet**: arm only *after* a trade goes
  favorable, then cut on a fixed $ retrace from the peak. Live sim: `arm +$50 /
  give-back $40` turned −$890 → −$2 over 61 trades (rescued id53 −150→+20, id61
  −122→+26), clipping only 5 winners for −$158.
- **Forward-validated on the shadow board:** +$471 vs actual, **all** of it from the
  went-green cohort (+$472); the never-green cohort is **untouched** (−$2,873 →
  −$2,873). V5 `ratchet2` nets similar (+$421) but by **gutting the winners**
  (+$841 vs +$3,490 actual on the green cohort = −$2,649 of upside scalped away) —
  rejected.

**V7 has no equivalent today** (verified): grind has one *wide* ATR chandelier
(≈3.5 ATR ≈ $130 give-back before it tightens); **rgv has no trail at all** (2R
target + 1-ATR stop). This give-back is the tight, early-arming second ratchet
stage V5's `FUT_RATCHET2_*` tried to be but mis-tuned ($2.50 arm → scalped).

## The hard constraint (operator, load-bearing)

**A give-back only helps a trade that goes green first.** It CANNOT touch a trade
that goes straight offside and never turns green — those are **stop territory**
(1-ATR native stop / adverse-cut), a separate lever. This exit targets *only* the
green-then-reverse losses — which is exactly where the −$120–150 losses live, but
it is **not** a blanket loss fix. Do not scope it as one.

## Design

### New pure decider — `deciders.exit_giveback`
```
def exit_giveback(pos, price, *, value_per_point, qty,
                  arm_usd=50.0, giveback_usd=40.0) -> str | None:
    """Once the position has been >= arm_usd favorable, cut if it gives back
    giveback_usd from its peak. Dollar-denominated (risk, not points) so it caps
    the loss the operator actually feels, and arms sooner in point-terms on
    bigger size. Reuses pos.peak_favorable (already tracked, in price points)."""
    peak_usd = pos.peak_favorable * value_per_point * qty
    if peak_usd < arm_usd:
        return None                       # never armed → never fires (the constraint)
    fav = (price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - price)
    fav_usd = fav * value_per_point * qty
    if peak_usd - fav_usd >= giveback_usd:
        return "GIVEBACK"
    return None
```
No new position state — `pos.peak_favorable` already exists (chandelier/adverse-cut
use it). Pure function, unit-testable like the other `exit_*`.

### Config knobs (`config.py`, per-gate `GateSpec` + `RunConfig`)
- `giveback_enabled: bool = False`  (default OFF)
- `giveback_arm_usd: float = 50.0`
- `giveback_usd: float = 40.0`
Per-gate override via `GateSpec.params` so rgv and grind can differ.

### Wiring (`strategy._manage`, the per-gate exit routing)
Add the give-back to the existing exit ladder (current order: chandelier/target →
adverse_cut → absorption). Slot give-back **before absorption** (it is the tighter,
earlier protective cut this whole study is about); **first reason to fire wins**:
- **rgv** (2R + stop, no trail): add give-back as its protective exit → a trade
  that gets +$50 toward its 2R target but reverses is banked instead of round-
  tripping to a stop-out. Give-back + 2R coexist (2R takes the full target; give-
  back catches the reversal short of it).
- **grind** (chandelier): add give-back *underneath* the chandelier (whichever
  fires first). The chandelier keeps riding true runners; the tight $ give-back
  catches the small-peak reversals the wide ATR trail misses. (Alternative:
  tighten the chandelier's `start_k` — but that also caps runners; adding the $
  give-back underneath is more surgical. Operator to choose — see open questions.)

### Analytics capture (CLAUDE.md §3 HARD RULE)
`exit_reason="GIVEBACK"` flows onto `trades.exit_reason` via the existing tracker
path (no new plumbing) → visible in recording, the sweep, and any exit-reason
cohorting. Add GIVEBACK to any exit-reason map/label the web/monitor surfaces use.

## Test plan (`tests/test_deciders.py` + `test_strategy.py`)
- arms only after `arm_usd` favorable; never fires if peak < arm (the constraint).
- fires at exactly `giveback_usd` retrace from peak; not before.
- dollar scaling: same $ thresholds → fewer points on a 2-lot than a 1-lot.
- SHORT symmetry.
- `_manage` precedence: give-back beats absorption when both would fire; 2R still
  wins when the target is hit first; a true runner still exits on chandelier, not
  give-back (no premature runner cap in the grind path).

## Rollout (safety rail — even though operator chose "wire it in")
1. Build behind `giveback_enabled=False`.
2. **Shadow variant first** — add `grind_fast_gb` / `rgv_gb` to the shadow slate to
   accumulate **2-lot** forward samples (the shadow board that validated this is
   1-lot, so it does NOT reproduce the −$120–150 magnitudes — the 2-lot deep-loss
   rescue is proven only on the live sim so far).
3. Paper-forward a few sessions, then operator go-live (flip `giveback_enabled`).

## Open questions for the operator
1. **Dollar-absolute vs per-lot?** `arm $50 / gb $40` is absolute (matches the
   dollar risk you care about; arms sooner on 2-lot). Per-lot (`$25/lot`) would
   make point-behaviour size-independent. Recommend **absolute** — the concern is
   dollar loss — but your call.
2. **grind: add give-back underneath, or tighten the chandelier?** Recommend add
   underneath (surgical; preserves the chandelier for true runners).
3. **Exact thresholds** — 50/40 is validated on ≤1 week / mixed 1–2 lot; treat as a
   starting point, confirm on the 2-lot shadow variant before arming.

## References
Live L2 study + forward-validation: this session (scratchpad `l2_triggers.py`,
`shadow_fv.py`). V5 `FUT_RATCHET2_*` (.env: arm 2.50 / lock 1.50 / give-frac 0.30 /
run_n 6) — rejected as a scalper. Seams: `deciders.py` `exit_chandelier`/
`exit_adverse_cut`/`exit_absorption`, `strategy._manage`, `Position.peak_favorable`.
