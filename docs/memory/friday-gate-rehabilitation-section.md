---
name: friday-gate-rehabilitation-section
description: "Operator RULE (2026-07-25) — the weekly Friday live-desk report must NOT bench a gate at face value. For every red/underperforming gate, do the rgv-style root-cause: WHY isn't it working, HOW could it work (tune internals → filter → normalize malfunctions → robustness). Make it a BIG recurring section."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9162c01b-c354-41a1-9fc3-162d48ae4678
---

**Operator RULE (2026-07-25): never look at a gate's performance at face value and say 'it's no good, bench it'. If it's not working, the question is HOW can it work — dig into the mechanism.** This is the #1 job of the weekly live-desk (Friday) analysis, and it must be a BIG recurring section.

**Why:** face-value benching throws away gates that have a real edge hidden behind a fixable flaw. Proven the same day on rgv (both directions):
- **rgv_short** looked like a −$3,543 loser → the bleed was the BASE config (`fast_turn` firing on noise), not the signal. Fixed: +$778, robustness-passed. Face-value would have wrongly buried it.
- **rgv_long** looked like a −$691 loser (removed) → the fix was the EXIT (give-back was gutting its huge wins), not a filter. Revived to +$674 keeping all 7 huge wins.
- Both had **malfunction-inflated losses** (rgv_short 61% of the live loss was 2 stop/naked failures) that made them look worse than the signal.
- The "obvious" fix (restore the old ER filters) was itself a **FAKE filter** that would have destroyed both.

**How to apply — the "Gate Rehabilitation" section, per red/benched gate each week (the rgv treatment):**
1. **Normalize the malfunctions** — cap losers at a working stop (1-ATR + realistic slippage); separate execution failures from real −EV signal. Show raw vs capped.
2. **Reconstruct at the corrected cost** ($1.50 fee, tick-honest — NOT $5, NOT bar-close).
3. **Root-cause the base config** — is it the internal thresholds (e.g. a noise-firing knob), the exit (give-back gutting winners), or genuinely the signal? Tune internals per-side.
4. **Test filters that KEEP the winners** — ER/ATR/OFI; reject any "improvement" that wins by dropping the target/huge winners (the retention gate).
5. **Robustness-test** the fix (day-level spread, both-weeks, parameter plateau, June/OOS extension, drawdown) before trusting it.
6. **Verdict: fix-and-revive, or truly-retire** — only bench after the mechanism is understood and no config works, never at face value.

**★ WIRED 2026-07-26 (operator reinforced: "a WHOLE live-desk section on rehabbing things that don't work — or at least TRYING to!!").** Now a dedicated **`Rehab` phase** in `friday_v7_maxdepth.workflow.js` (scout targets → parallel per-target rehab dossiers running the 6-step discipline → flagship synthesis `part1_5_rehab.html`) + a headline **PART 1.5** in `FRIDAY_V7_REPORT_SCOPE.md`, placed right after the live desk, stitched by the Assemble agent. **Extended beyond GATES to EXITS** (the chandelier/two-ratchet/partial rehabs) and **mandates showing the TRYING — the NULLs/graves are the point** (regime-exit NULL, two-ratchet clip-mirage, the whole "capture MORE of grind's tail" question that closed across 5 angles). Feeds the two live grind-exit shadow ledgers (`data/two_ratchet_shadow.json`, `data/partial_shadow.json`). Ties [[friday-report-runs-tonight-maxdepth.md]] [[rgv-tuning-both-directions]] [[execution-cost-autopsy-stage1]] [[tournament-changes-saturday-only]] (rehabilitation findings feed the Saturday roster decision).
