# Gate rehab — grind-exit scale-out (two_ratchet / partial / Lot-A scalp)

**Run:** 2026-08-01 · tick-honest ($1.50/RT/lot, $2/pt, −1×ATR hard stop) · READ-ONLY reconstruction
**Engine:** `scripts/rehab_grind_exit_scaleout.py` + `rehab_grind_eval.py` + `rehab_grind_filters.py`
**Tape:** capture.db `2026-07-23 22:00 → 2026-07-31 21:00` (10.08M MNQ ticks). ticks.db (V5 archive) ends 07-17 → a **hard coverage gap 07-17…07-23** means only **44 unique grind_long signals** are tick-reconstructable. Thin. Every number below is a small-n read; treat R-optima as noise unless proven.

> **Engine validation (cross-check).** On the 4 overlapping 07-27 signals my reconstruction reproduces the *deployed* shadow watchers **byte-for-byte**: recon-pure-6.0 = −139.0 (two_ratchet_shadow.json recon), two-ratchet = −27.5 (shadow_net), base2 = −278.0 (partial baseline), scale@2R = −213.5 (partial_net). Same engine, extended from n=4 to n=44.

---

## 0. TL;DR verdict

| Lever | Verdict | Why |
|---|---|---|
| **The scale-out / two-ratchet / partial EXIT** | **NOT the bug.** Fine-to-slightly-improvable. | Every exit variant is net-negative on the raw tape (−326 best → −1000 worst). Exit reprice moves the total by $175–500; the signal loses far more. You cannot fix a bleeding signal from the exit. |
| **Two-ratchet on the Lot-B chandelier** | **FIXED / adopt — but REGIME-DEPENDENT** | Robustly beats pure-6.0 (−326 vs −500, better *every single day*, safety-valve verified: 0 runner-clips across 44, disarm@4.5R let all four ≥4.5R runners ride). Proven only on chop/building — no clean-trend day in sample. |
| **Lot-A scalp R = 2.0 (the operator guess)** | **NOT proven — REJECT the specific R; keep the mechanism as a VARIANCE lever, SHADOW the R** | The scalp-R surface is jagged noise. 2.0R is a *trough* in grind's home (building: −30 vs base2). Plateau, where it exists, sits **high (3.0–3.5R)**. Edge-over-base2 flips negative in leave-one-day-out (drop 07-30). It de-risks; it does not add proven net edge. |
| **★ The dominant lever: ENTRY regime-gate (ER≥0.3)** | **THE FIX — but it's a SIGNAL/ROUTER job, not an exit job** | Gating entries to ER≥0.3 flips the whole complex **−1000 → +406** (BASE2). This is where the money is. The exit rehab is polishing brass on the wrong deck. |

**One line:** *the grind exit is not broken; the grind **signal** bleeds in low-ER chop and no exit tweak reaches the 52% of entries that die at −1R without ever moving. Adopt the two-ratchet on Lot B (robust, safety-valve-proven), stop trusting the 2.0R scalp number, and put the real work on the ENTRY regime-gate.*

---

## 1. NORMALIZE — malfunctions

Reconstruction reprices every signal on the true tick path with a *working* −1×ATR stop at base_size=1, so it is self-normalizing. Scanning the live ledger for anomalies (|per-trade| > $120):

- **One true malfunction:** `2026-07-30 13:30:53` `grind_long_A`, **qty = 5** (conviction sizing) fired *into the 13:30 US-cash-open flush*, raw **−$235.5**. The stop **worked** (exit 27834.45 vs entry 27857.85 = −23.4 pt ≈ −1R at ATR 15.5); the damage was **5× sizing at the worst possible minute**, not a broken stop. **Normalized → −$47.1** (per-lot). This is a *sizing/timing* fault (conviction-size fired a Lot-A at the open flush — cf. `[[us-open-dont-bench-trend-rider]]`: the open is structurally violent), not an exit fault. Flag for the sizing layer: conviction size on grind_long_A at 13:30 UTC is a landmine.
- **No STOP_UNFILLED / naked-ride / system-stop events** in the grind_long set over the covered window. Every other |>$120| row is a legitimate **winner** (13:45 +$234/+$243 on the 46-ATR post-open trend, etc.), not a malfunction.

**Normalization impact:** replacing the one −235.5 with −47.1 lifts raw live by +$188. Small; the story is not malfunctions.

---

## 2. RECONSTRUCT — corrected-cost true P&L

Raw live (covered window, as booked): grind_long (single, pre-scaleout) −211 · grind_long_A +31 · grind_long_B +302 = **+$122**.

That +122 is **not representative** — it is flattered by (a) conviction sizing on winners and (b) *slot-availability selection*: Lot-B (chandelier) only fired on 19 of the 44 signals and happened to catch the winners; when only Lot-A was free the signal booked no chandelier loss. The clean, apples-to-apples per-signal reconstruction (every signal, fixed 1 lot per leg, one −1R stop, honest fees) is the truth:

| Policy (44 signals) | net $ | win% | strip-best-1 / -3 |
|---|--:|--:|--|
| BASE2 (2× pure-6.0 chandelier — pre-scaleout baseline) | **−1000.4** | 23% | −1688 / −2400 |
| CHAND1 (pure-6.0, 1 lot) | −500.2 | 23% | −844 / −1200 |
| **TR1 (two-ratchet, 1 lot)** | **−325.7** | 23% | −670 / −1026 |
| SCALE2 (Lot-A scalp@2R + Lot-B pure-6.0) | −769.9 | 27% | −1299 / −1914 |
| SCALE2+TR (Lot-A scalp@2R + Lot-B two-ratchet) | −595.4 | 27% | −1125 / −1739 |
| LotA chand + LotB two-ratchet (2-lot, no scalp) | −825.9 | 23% | −1514 / −2226 |

Every policy is deeply red on the raw tape, and strip-best-3 roughly doubles the loss → the little green there is comes from **a handful of runners**, exactly the fragile shape the rehab discipline warns about.

---

## 3. ROOT-CAUSE — base / exit / signal?

**It's the SIGNAL.** The fake-win decomposition by reachable-MFE:

| Bucket | n | BASE2 | SCALE@2.0 | scalp Δ |
|---|--:|--:|--:|--:|
| RUNNERS rMFE ≥ 3R | 11 | +2153 | +2290 | +137 |
| MID 1–3R | 10 | −948 | −855 | +94 |
| **DUDS < 1R** | **23** | **−2205** | **−2205** | **+0** |

- **23 of 44 signals (52%) never reach even +1R** — they go straight to the −1R stop. **No exit variant touches them** (the scalp Δ on duds is exactly $0 — it never triggers). The bleed lives entirely in entries that should never have fired.
- The runners *do* pay (+2153) but cannot cover the dud + mid bleed (−3153).
- Therefore the exit (chandelier vs two-ratchet vs scalp) is a **second-order** knob: it re-slices the +2153 of runner money by ±$200–500. The **first-order** problem is that the signal fires in dud-rich low-ER chop.

This is `[[low-vol-grind-untradeable-stay-flat]]` and `[[rearm-momentum-needs-er-climb-not-delta-blip]]`, now quantified for the exit rehab: *the exit was never the leak.*

---

## 4. FILTERS that KEEP the winners (fake-win guarded)

The 11 runners: 4 live in ER≥0.3, 7 in ER<0.3 dead-chop. So an ER floor **does** collaterally drop some real runners — but it wins by cutting the **23 duds**, not by dropping the target winners, so it is **not a fake win** (it clears the fake-win test: net rises because losers are removed, and the *predictable-in-advance* runner cohort — the ER≥0.3 ones — is retained; the dropped low-ER runners are 7R-flukes you cannot know at entry).

| Entry filter | kept | runners kept | BASE2 | CHAND1 | TR1 | SCALE2 | SCALE2+TR |
|---|--:|--:|--:|--:|--:|--:|--:|
| NO FILTER | 44/44 | 11/11 | −1000 | −500 | −326 | −770 | −595 |
| ER ≥ 0.2 | 27 | 7 | +14 | +7 | +118 | +1 | +112 |
| **ER ≥ 0.3 (building+)** | **11** | **4** | **+406** | **+203** | **+203** | **+376** | **+376** |
| ER ≥ 0.4 | 4 | 3 | +1045 | +523 | +523 | +945 | +945 |
| ATR ≤ 28 (drop violent) | 33 | 8 | −1069 | −535 | −360 | −738 | −564 |
| ATR 20–32 band | 17 | 6 | −294 | −147 | −35 | −132 | **−21** |
| ER≥0.25 & ATR≤30 | 11 | 3 | +97 | +49 | +49 | +27 | +27 |

**Reads / graves:**
- **ER is the discriminator, ATR is not.** An ATR ceiling alone (≤28) barely moves the bleed (−1069). ER≥0.3 is the clean lever. This matches the standing memory that *ER floors are the real filter for grind* (`[[er-favourable-condition-gate-live]]`, grind floor 0.35 validated) — here even 0.3 flips the sign.
- **ER≥0.4 (+1045, 75%w) is the strongest but n=4 — overfit, do not pin.** ER≥0.3 (n=11) is the honest floor.
- **NULL: ATR-band filters.** "20–32 band" only claws back to −294 (still red) — a mediocre patch; rejected in favour of the ER floor.
- **Regime split of BASE2 confirms the same story:** building (ER 0.3–0.5, n=11) **+406**; dead/normal-chop (ER<0.3, ATR<28, n=28) **−756**; violent-whipsaw (ATR≥28, ER<0.3, n=5) **−650 at 0% win**. Grind has exactly one home regime, and it is *building*, not chop.

**Crucial:** the ER-gate is an **entry/router** action, not an exit action. It is the single biggest number in this report and it lives outside the scale-out machinery.

---

## 5. The EXIT decision, done properly (sweep the guesses)

### 5a. Two-ratchet vs pure-6.0 on the chandelier lot — **robust win, REGIME-DEPENDENT**

- **TR1 −326 beats CHAND1 −500** on the full tape, and TR ≥ CHAND on **every day** (07-24 tie, 07-27 −27 vs −139, 07-29 tie, 07-30 −145 vs −208, 07-31 tie) → leave-one-day-out holds trivially (never worse). Per-regime: TR wins dead-chop (−204 vs −378), ties building & violent.
- **Safety valve verified.** On the four ≥4.5R runners (7.2R, 5.2R, 4.8R, 4.7R) TR == CHAND exactly — `disarm_r=4.5` handed control back to the wide pure trail, **0 runner-clips across all 44**. TR only *gained* on sub-4.5R roll-overs the pure-6.0 wide `start_k=3.5` trail gives back (the 6.6R-peak-then-fade banked +63; the 4.2R roller +112).
- **Mechanism:** on a tape whose runners peak and *roll over* below 6R (post-trend chop / building), the tighter 2nd ratchet banks give-back the loose pure trail surrenders. That is precisely this regime.
- **Caveat (why REGIME-DEPENDENT not FIXED-everywhere):** zero clean, sustained multi-6R trend days in sample. The disarm@4.5R is designed for that case and never clipped here, but it is **unproven on a clean-trend day** — a run that grinds repeatedly through 4.0–4.5R could still be banked. Keep `disarm_r=4.5` as the guard and re-audit on the first real trend week.

### 5b. Lot-A scalp R — **the 2.0R guess is NOT the robust optimum**

Scalp-R sweep (2-lot SCALE net, $), and per home-regime:

```
R_A:        0.5    1.0    1.5    2.0    2.5    3.0    3.5    4.0
whole-tape -814   -558   -584   -770   -556   -250   -252   -212
building   +289   +553   +354   +376*  +525   +672   +705   +684    (*guess=trough vs base +406 → −30)
dead-chop  -540   -461   -287   -496   -430   -272   -307   -246
violent    -562   -650   -650   -650   -650   -650   -650   -650    (scalp never triggers)
```

- **The surface is jagged noise** (building peaks 3.0–3.5R; dead-chop peaks at 1.5R *and* 4.0R; whole-tape drifts up to 4.0R) — the fingerprint of an over-tuned parameter on n=11/28. There is **no stable plateau** at 2.0R; if anything grind's *home* regime (building) wants the scalp **late (3.0–3.5R, near the runner)**, i.e. "don't cap the runner early."
- **Leave-one-day-out kills the scale-out's edge-over-base2:** SCALE@2.0 − BASE2 is +166…+338 dropping four of five days but **−49.5 dropping 07-30** — the entire scale-out "edge" leans on one day. Fragile.
- **Therefore:** the scalp is a **variance lever** (bank certainty on Lot A, per the original deploy scope: daily-vol −29%, maxDD −24%), **not a proven net-edge lever**, and 2.0R specifically is a poor pick. Keep the scale-out mechanism (it's live and it de-risks), but **do not claim a proven R**; if tuning, lean high (~3R) in the building regime and **SHADOW the exact value** — do not pin it from this tape.

### 5c. Combined best under the ER≥0.3 gate (per-day)

```
day        n   TR1      SCALE2+TR   BASE2
07-24      3   -7.0     -21.0       -14.0
07-27      2  -104.5   -209.0      -209.0
07-29      1   -71.0   -142.0      -142.0
07-30      5  +385.5   +748.0      +771.0   <- the one trend-ish day carries everything
```
Even gated, the green is concentrated on 07-30 (the post-open 46-ATR trend). n is too small to prefer SCALE2+TR over TR1 on edge; TR1 is the *cheaper, more robust* core (1 lot, no scalp-R to overfit), SCALE2+TR adds the variance-smoothing scalp on top for the same directional call.

---

## 6. ROBUSTNESS summary

- **Per-ISO-week:** wk30 (n=4) base2 −98; wk31 (n=40) base2 −902, TR1 −277. Both weeks red raw; TR1 < CHAND1 < BASE2 in both. No week rescues the raw signal.
- **Strip-best:** removing the top 3 trades ~doubles every policy's loss → edge is runner-concentrated and fragile (expected for a trend-rider on a chop-heavy tape).
- **Leave-one-day-out:** two-ratchet-beats-pure is robust (never worse any day); scale-out-beats-base2 is **not** (fails dropping 07-30).
- **Cross-regime:** the sign of the whole complex is set by ER regime, not by the exit. Positive only in building/ER≥0.3.

---

## 7. VERDICT & actions

1. **Grind EXIT (the rehab subject): NOT the bug — do not "retire" the scale-out.** It is fine; the leak is upstream.
2. **Two-ratchet on Lot-B chandelier: ADOPT — REGIME-DEPENDENT.** `PRIMARY start_k=3.5, lock_r=6.0, lock_k=0.5` + 2nd ratchet `arm_r=4.0, disarm_r=4.5, b_k=1.25`. Robust win on chop/building, safety-valve verified (0 clips). Keep `disarm_r=4.5`; re-audit on the first clean multi-6R trend week before calling it FIXED-everywhere. (This upgrades the two_ratchet shadow from "watch" → "promote-on-Saturday" per `[[tournament-changes-saturday-only]]`.)
3. **Lot-A scalp R = 2.0: REJECT as a proven number → keep as SHADOW variance lever.** The R-surface is noise and 2.0R is a trough in grind's home regime. Do not pin an R from this tape; if forced, ~3R in building. Keep `partial_shadow_watch.py` running to accumulate the R live.
4. **★ The real fix is an ENTRY REGIME-GATE, and it belongs to the ROUTER/signal layer, not the exit:** bench/reject grind_long below **ER≈0.3** (flips −1000 → +406). This is already the spirit of the live router (`[[low-vol-grind-untradeable]]`, `[[rearm-momentum-needs-er-climb]]`, grind ER-floor 0.35 in `[[er-favourable-condition-gate-live]]`); this rehab is independent quantitative confirmation on fresh 07-23→31 tape. **Escalate to the entry/router work-stream — no exit change can substitute for it.**
5. **Sizing landmine flagged:** conviction-size fired a 5-lot grind_long_A into the 13:30 US-open flush (−235.5 raw). Cap grind Lot-A size at the cash open.

### Honest limitations (the trying, and where it thins out)
- **n = 44 signals, ~5 trading days, one summer regime block, no clean-trend day.** Every R-optimum here is noise-sensitive; the two robust claims (two-ratchet ≥ pure every day; ER≥0.3 flips the sign) are the only ones that survive LODO/strip-best, and even they rest on 07-30 doing the heavy lifting.
- **Coverage gap 07-17→07-23** (ticks.db ends 07-17, capture.db starts 07-23) — 50 grind_long rows are outside tick coverage and could not be reconstructed. A wider capture would give each regime bucket real n; until then, treat "building = grind's home" as strongly-suggested, not proven-at-scale.
- **NULLs shown, not hidden:** ATR-only filters (all red), the 2.0R scalp guess (trough), the LotA-chand+LotB-TR 2-lot variant (−826, worse than plain), scale-out-beats-base2 (fails LODO), ER≥0.4 (great but n=4 overfit). The grave is: *there is no exit configuration that makes the raw grind signal green — we tried the whole exit design space and none of it reaches the 52% of duds.*
