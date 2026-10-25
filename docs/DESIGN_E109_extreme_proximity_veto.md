# E109 — EXTREME-PROXIMITY VETO ON THE 10-YEAR LAKE (DESIGN, v0 — NOT RUN, NOT AUDITED)

> Written from scratch on 2026-10-25 because the earlier design was not in the repo (never committed; the old container is gone). It follows the operator's stated objective, not a recovered document. **Open assumptions are in section 11; confirm them before anything is run.**

## 1. Objective (operator, in his words, paraphrased)
There are no stops (Law 0e). Selectivity is the stop. The single biggest threat is the entry taken just before an MIL turn, which then sits for hours and loses ~$4,000. Find an entry filter that removes most of those, **even at the cost of chopping some winners**, so the desk gets consistency without the huge losses.

**Success is a smaller left tail and steadier days. It is not more $/day** (Law 0). A filter that raises $/day but keeps the tail has failed.

## 2. Question
Among the detector's entries over ten years, does *where in the range the entry is taken* separate the entries that become tail losses from the rest? If so, does vetoing the worst X% of positions cut the tail by more than it costs in winners?

## 3. Definitions (all causal — use only bars up to the entry minute)
- **Entry**: a confirmed detector turn with the leg robot's state rules (flat-only, 06:00Z–19:40Z window, same 05:00 Paris veto), produced by the **frozen detector v1** (K=11, ATR14; `scripts/mil_detector_fit.py`, `mil_labels.py`, `DETECTOR_SHA af0ace53e6dc9faa`). The detector is not retuned. The filter is the only thing that changes.
- **Forward extreme** of an entry: the extreme the trade is travelling *toward*. A LONG's forward extreme is the high; a SHORT's is the low. A with-leg entry near the forward extreme is "buying the top / selling the bottom" — the late-leg entry that precedes the turn.
- **Position p** (primary): `p = |entry − forward extreme| / (session high − session low so far)`. p = 0 means at the forward extreme; p = 1 means at the opposite one. Veto when **p ≤ x**, x ∈ {5%, 10%, 15%} (the operator's bands). Require the range so far ≥ 0.25·S (S = mean range of the prior 20 sessions) or the percentage is meaningless early in the session; below that, use rule P3.
- **Alternatives, same bands, declared now so none is added after seeing results:**
  - **P2** — same ratio against the trailing 360-minute range (not the session).
  - **P3** — absolute distance: veto if `|entry − forward extreme| ≤ x·S`.
  - **P4** — veto if the entry's leg already travelled ≥ y·S from its own start (leg maturity), y fixed on TUNE only.
- Points are expressed in today's points (S_ref scaling as in E52) so years are comparable.

## 4. Data and blocks
- Lake: `data/tape/bars/NQ/` (1-min, 2015-01-02 → 2025-07-25), loaded through `gazbot7.lake.connect()` as day partitions. MNQ backfill for the sealed block. **The lake is not in this container (`data/tape` absent); the run needs the VPS or a restored mirror.**
- Winter sessions open at 23:00Z, so the 19:40Z/20:40Z clocks mean something else outside EDT. Run the whole lake but report summer/EDT and winter/EST **separately**, and do not pool until both are shown.
- Blocks (as E52): TRAIN 2015–2020 (nothing is fitted here for a rule filter, so used only to *describe* the loss tail), TUNE 2021–22 (choose x and the variant), CONFIRM-A 2023-01 → 2024-08-11, CONFIRM-B 2024-08-12 → 2025-07-24, SEALED MNQ 2025-09-15 → 2026-03-08.
- **Honest status:** E52–E58 already looked at CONFIRM-A/B and SEALED with other cells, so those are **second looks**. No clean block exists for NQ. The only clean data is the live forward period (v1.02 shadows, from 2026-10-23). A pass here is **PROMISING**, never proven, and the forward shadow is the real test.

## 5. Exit model for scoring (held fixed, not part of the study)
Score each entry under the **live ladder** (arm H: 4 lots out at +25/+50/+75/+100 per-lot dollars = 12.5/25/37.5/50pt; hard flat 20:40Z; no stop), because that is what produces the $4,000 days. The same run is repeated with the E58 1-lot trailing lock as a robustness check only. Fills ideal plus 0.25pt adverse and $1.50/lot fee, as E52. Tail is therefore measured in **dollars at the live size**, and also in points so it survives the size.

## 6. Procedure
1. **Describe the tail first (counts before dollars, L10).** On all blocks: how many entries, how many reach the target, how many are "stuck" at 20:40Z, and the distribution of entry p. Define **tail entries** as the worst 5% of entries by dollars *and* every entry ≤ −$2,000 (live size). Report how many there are per block and what their p values are.
2. **Does p separate the tail?** Hit rate and mean/median P&L by p-bucket (0–5, 5–10, 10–15, 15–25, 25–50, 50–100%). Report the **share of tail entries that fall inside each band** vs the share of *all* entries that fall inside it (the lift). If tail entries are not over-represented near the forward extreme, the hypothesis fails here and the study stops.
3. **Apply the veto** at x = 5/10/15% for P1 (primary), then P2–P4 as secondary. Skipped entries leave the desk flat, so the next confirmed turn can be taken (flat-only is re-evaluated, not assumed).
4. **Report the trade-off table per x and per block**, always including the unfiltered baseline:
   - entries removed (% of all), tail entries removed (% of tail), **winners removed** and the dollars they would have made;
   - worst trade, worst day, 5th-percentile day, **days positive**, daily SD and CV (spread/mean), $/day, max drawdown;
   - the same split by year, EDT/EST, and by long/short.
5. **Controls (the filter must beat all three):**
   - **RANDOM veto**: remove the same fraction of entries at random (200 draws; report the 5th/95th percentile of tail reduction).
   - **FLIP-position**: veto the entries *farthest* from the forward extreme at the same rate. If that does as well, the filter is not finding anything.
   - **Time-of-day veto**: veto the same share by latest entry times (E55 found late entries stick more). A p-filter that is just a disguised late-entry filter is not new.
7. **Selection (frozen before CONFIRM opens):** choose x and the variant on TUNE only, from the table, by the Law 0 gate. Write the single chosen cell and one runner-up into a dated appendix, then open CONFIRM-A, CONFIRM-B, SEALED once each, labelled second looks.

## 7. Pass / fail rule (declared now)
**PASS (PROMISING)** only if the chosen cell, versus the unfiltered baseline on **each** of TUNE, CONFIRM-A and CONFIRM-B (and SEALED shown):
1. `bible.gate` holds: days positive, worst day and CV do **not** worsen, and $/day does not fall by more than a stated tolerance (see 11, decision 2);
2. the tail reduction beats the RANDOM-veto 95th percentile **and** the FLIP-position control;
3. at least **30 tail entries** exist per block and the count removed is reported (below that: "no decision", per the desk's own n≥30 rule);
4. the winners removed are reported in dollars and do not exceed an operator-set share (decision 3);
5. the direction holds in both EDT and EST sessions and for both long and short.

**FAIL** if p does not over-represent the tail near the forward extreme, or the veto does no better than RANDOM or FLIP. A fail is a result: it means entry location is *not* what separates the $4,000 days, and the next family is regime or leg-maturity, not more bands.

## 8. Known weaknesses of this design (stated up front for the audit)
- **The $4,000 losses may not be near the extreme at all.** The 10-16 miss and 10-23's 08:15 LONG (−267pt before it hit) were entries on a leg that later reversed deeper; whether they were near the session extreme is unmeasured. Step 2 tests exactly this before any veto is built.
- **Tail is rare.** If a block holds fewer than ~30 tail entries the result is unreadable; pool by block-type only after showing each.
- **Vetoing near the extreme can also remove the best trades** (breakouts into a trend that keeps going). Reported as winners removed; the operator's stated tolerance sets the pass bar.
- **Session-so-far range is noisy early in the session** and the extreme is only known in hindsight in its final form. Only the running extreme at entry time is used, which is what the live robot would know.
- **Optimistic fills and a survivor-style window** (flat-only, 06:00–19:40Z): same caveats as E52–E58.
- **Structure vs edge:** E58 showed FLIP is also positive under profit locks. The controls above are there to stop a structural gain being read as skill.
- **Live-vs-lake mismatch:** the lake is NQ bars; live is MNQ with Claude's v1.02 filter on top of the detector. The veto is tested on the detector's entries. Whether it adds anything on top of Claude's call is **not answered here** and needs the forward shadow.

## 9. Forward test (the only clean read)
If PROMISING, add it as a **no-press shadow** beside `v1.02-LOCKSHADOW` / `v1.02-PM-shadow` (same pattern, `tests/test_hybrid_shadow.py` style, AST-tested to never write `day_rider_buy.txt`): log would-be vetoes and what those entries then did. No live change until ≥30 would-be vetoes exist.

## 10. Deliverables
Declaration `reports/recursive_loop/E109_change.txt` (this file's section 3–7, frozen), code `reports/recursive_loop/E109_code/`, result `E109_result.txt/.json`, ledger line in `E57_ledger.txt` format. Robot, rider and account untouched.

## 11. Decisions the operator must confirm before a run (I assumed; I did not ask)
1. **What "the extremes" means.** Assumed: the extreme *ahead of the trade* (the high for a long, the low for a short) of the **session so far**, as a % of the session range. Alternatives P2–P4 are included, but if he means the extreme *behind* the trade (the turn point itself), the definition changes.
2. **How much $/day he will give up** for a smaller tail (a number, e.g. "up to 15%").
3. **How many winners he will accept chopped** (share of winning dollars).
4. **The tail definition.** Assumed: worst 5% of entries and anything ≤ −$2,000 at live size. He said ~$4,000; that may be the right line.
5. **Run on the detector alone, or on the v1.02 Claude-filtered entries?** The lake has no Claude calls, so this design is detector-only.
6. Whether to **include the winter (EST) sessions** or restrict to EDT.
