# REHAB — `chandelier (runner give-back)` exit (tick-honest, regime-segmented)

**Date:** 2026-08-01 · **Analyst:** router/rehab pass · **Symbol:** MNQ · **Cost model:** $2/pt, $1.50/RT per lot
**What this rehabs:** the **profit exit**, not a gate — the loose-then-lock chandelier (`exit_chandelier_lock`,
`start_k=3.5, lock_r=6.0, lock_k=0.5`) that rides the tail on the desk's runner slots. Live it is the **biggest
gross winner** (CHANDELIER exit_reason = **+$4,774 / 63tr**) but it **leaks the tail**: the week's 4.2R-MFE grind
runner peaked ~$208 and banked **+$23** (~$185 given back), and across all managed-profit exits the desk banks only
**47% of peak**.
**Tape:** unified V5 archive + V7 capture 5s tape, **2026-07-05 22:00Z → 2026-07-31 21:00Z** (~19 sessions, ISO
weeks 27–31) for the replay sweep; live `gazbot7.db` (487 trades, 07-16→07-31) + `capture.db` ticks (≥07-23) for the
live reconstruction. **Cost verified:** all 487 live trades already carry `fees_usd=$1.50` and P&L at $2/pt — **no
cost correction needed** (unlike the V5 autopsies).
**Tools (reproducible):** `scripts/rehab_chand_recon.py` (live reconstruction/normalize), `scripts/rehab_chand_sweep.py`
(regime-segmented parameter sweep), `scripts/rehab_chand_live_reprice.py` (candidate configs on the actually-taken trades).

---

## TL;DR — VERDICT: **REGIME-DEPENDENT (FIXED per-regime)**

The give-back leak is the **EXIT × REGIME mismatch**, not the signal (the runs are real: grind MFE median ≈4.5R,
p90 ≈11R). The single wide lock (`lock_r=6.0`) is sprayed across **all** regimes. It is **robustly right on true
trend and robustly wrong everywhere else** — because the median MNQ runner peaks at **~4.5R, below the 6.0 lock, so
the firm lock never engages** and every off-trend runner rides the 3.5·ATR trail all the way back down.

| grind, by regime (entry 30m ER) | incumbent `L3.5/6.0/0.5` IS→OOS | robust fix | fix IS→OOS | call |
|---|--:|---|--:|---|
| **TREND** (ER≥0.50) | **+52.2 → +46.9** /sig | keep wide `6.0` | — | **KEEP wide** (it's the edge) |
| **BUILD** (0.30–0.50) | +12.7 → **−9.5** /sig (overfit) | `L3.5/3.0/0.5` | +7.5 → **+4.6** | **lower lock_r → 3.0** |
| **CHOP** (ER<0.30) | +4.1 → **−1.2** /sig | *(none robust)* | — | **router benches** (defense) |

**Fix:** make the runner trail **regime-conditional** — `lock_r=6.0` only on aligned/true-trend entries (its proven
+$47/sig OOS edge), `lock_r=3.0` on build, bench momentum in confirmed chop. On the **actually-taken** live
chandelier/giveback trades this regime policy reconstructs **+$3,580 vs the incumbent's +$2,932 (+22%)** on the same
basis — the whole gain in chop/build, trend untouched. The mechanism to deliver it **already exists** (the
`adaptive_exit` regime selector + the `exit_overrides.json` control panel); it is simply **not wired into the
dual-slot Lot-B "wide" tail**, which is the one path still riding a regime-blind `lock_r=6.0`.

---

## 1. NORMALIZE — malfunctions in the live record

Two malfunction classes touch these trades; both are normalized OUT of the exit's attribution:

- **STOP_UNFILLED (26 trades, −$1,378 realized).** These are **entry-side native-stop failures** (mostly rgv/capit/
  abs_veto on 07-23), *not* chandelier profit exits. Had the 1-ATR stop filled they'd be **−$1,091** (−1·ATR each) →
  the malfunction cost ~**−$287** extra. `grind_long` carried 8 of them (−$220), but again on the STOP path, not the
  chandelier. **None distort the chandelier P&L** — the CHANDELIER/GIVEBACK reasons are clean fills.
- **No naked rides / STOP_UNFILLED inside the chandelier set.** The chandelier only ever exits in profit (the native
  1-ATR STP owns the downside), so a give-back is a *banked gain*, never a malfunction — the leak is a **tuning**
  problem, exactly as the symptom framed it ("not a bleed-stop").

**Live give-back leak, reconstructed on real ticks** (`rehab_chand_recon.py`, 144 managed-profit exits):
banked **+$7,106** of **+$15,193** peak = **47% capture**; **$8,088 left on the table.**

| exit | n | bank$ | peak$ | give-back$ | capture% | med peak-R |
|---|--:|--:|--:|--:|--:|--:|
| CHANDELIER | 63 | +4,774 | +8,542 | +3,769 | **56%** | 2.96 |
| GIVEBACK ($40) | 81 | +2,332 | +6,650 | +4,318 | **35%** | 1.37 |

Give-back by regime confirms **where** it leaks: **trend 81% capture (n=4)** vs **chop 46% / build 42%**. The wide
trail works on trend and bleeds off-trend. The **symptom trade reproduces exactly**: 07-27 18:54 `grind_long`,
ATR 25, **peak 4.20R / $208 → banked +$23 → gave back $185** (and its abs_veto twin at the same minute: 4.12R →
+$19). The top-12 give-back leaks are all runners peaking **2.4R–5.8R** (i.e. *below* the 6.0 lock) that banked
almost nothing.

---

## 2. CORRECTED-COST RECONSTRUCT

Cost model already correct in the live book ($1.50/RT, $2/pt), so the reconstruction is like-for-like. Repricing the
actual live chandelier/giveback trades (grind+thrust+absveto) on their real forward 5s path (`rehab_chand_live_reprice.py`),
same conservative stop-first engine for every config:

| config (reconstructed, same basis) | chop (n39) | build (n28) | trend (n4) | TOTAL |
|---|--:|--:|--:|--:|
| ACTUAL (live realized) | +2,646 | +1,026 | +655 | +4,326 |
| **INCUMBENT** `L3.5/6.0/0.5` | +1,616 | +815 | +501 | **+2,932** |
| **POLICY (regime-conditional)** | **+2,187** | **+892** | +501 | **+3,580** |
| flat `L3.5/3.0/0.5` | +2,187 | +892 | +463 | +3,541 |
| `L3.0/6.0/0.5 +gb1.0` (give-back overlay) | +1,416 | +635 | +128 | +2,179 |
| flat `fix2.5` | +2,070 | +1,122 | +258 | +3,450 |

(Reconstruction is conservative vs ACTUAL — 5s-bar closes + stop-first — so read the *relative* config ranking, not
the absolute level.) The **regime-conditional policy beats the incumbent by +$648 (+22%)**, concentrated in the
leaking regimes, trend left alone. The give-back **overlay is the worst** — it strangles the trend riders (see §4).

---

## 3. ROOT-CAUSE — base / exit / signal?

**It is the EXIT, conditioned on REGIME.** Evidence:

- **Not the signal (for grind).** Replayed grind MFE is real in every regime — median **4.5R**, p90 **~11R**. The
  runs happen; we just give them back. (Contrast thrust/absveto in chop, §5 — *that* is a signal problem.)
- **Not the base trail width per se.** `start_k=3.5` and `lock_k=0.5` are fine; the broken knob is **`lock_r=6.0`**.
  Median runner peaks ~4.5R **< 6.0**, so on >50% of runs the "firm lock" **never triggers** — the position rides
  the wide `3.5·ATR` trail and gives back ~3.5R ≈ the entire gain. `lock_r=6.0` only engages on the top ~15–20% of
  runs (the true-trend monsters), which is exactly the population it was fit to (07-26 in-sample sweep, one summer
  RANGE regime, ~a dozen big-ATR runs — flagged in `GRIND_CHANDELIER_DEPLOY_SCOPE.md`).
- **The deploy-scope caveat came true.** That doc warned the **4.5–5.0R band is a trough** ("runs peaking ~4.5R ride
  the wide trail and give it back before hard-locking"). Live, the *typical* runner lives in that trough.

---

## 4. FILTERS / PARAMS THAT KEEP THE WINNERS — the sweep (and the fakes, rejected)

`rehab_chand_sweep.py`: replayed **3,237** wide-chandelier-user momentum entries (grind 2,493 / thrust-absveto 744)
on the 19-session tape, repriced under **56 configs** (fixed-R; `start_k × lock_r × lock_k`; tightening chandelier;
lock+give-back overlays), **segmented by regime × time-of-day × ATR band**, native 1-ATR stop owns downside.

**`lock_r` is the lever, and its optimum is opposite by regime** (grind, $/sig, IS=capture / OOS=archive):

| config | BUILD IS→OOS | TREND IS→OOS |
|---|--:|--:|
| `L3.5/6.0/0.5` (incumbent, wide) | +12.7 → **−9.5** | **+52.2 → +46.9** |
| `L3.5/3.0/0.5` (lock earlier) | **+7.5 → +4.6** | +31.6 → +32.3 |
| `fix2.5` (no chandelier) | +4.0 → +4.0 | +28.8 → +20.7 |

→ **BUILD wants `lock_r≈3.0` (robust both legs); TREND wants `lock_r=6.0` (robust both legs).** The single wide
config is an **IS-overfit** in build (collapses −9.5 OOS). This *is* the operator's backtest-discipline point made
flesh: a blanket config **washes the two regimes together** and buries the fix.

### The TRYING — NULLs & graves (shown, not hidden)

1. **Give-back overlay on the wide trail (`+gb1.0/gb1.5`).** *Won the grind|BUILD in-sample cell* (+7.0/sig, the
   single best number there) → looked like the fix. **REJECTED:** fails OOS (`+gb1.5` build IS +6.1 → **OOS −0.8**),
   and it was the **worst** config on the actual live trades (+$2,179, §2) because a hard R-cap **also strangles the
   trend riders** (grind trend +52 → +25). A cell-fit fake.
2. **Blanket `lock_r=3.0` everywhere.** Robust in build/chop, but **a grave on trend** (grind trend OOS +32 vs the
   wide +47 → ~**−$15/sig per trend runner**). Rejected as a *blanket*; correct only *off-trend*. (This is precisely
   why a static cross-tape number is banned here.)
3. **Fixed R-target instead of chandelier (`fix2.5`).** Genuinely robust and *stable* in build (IS +4.0 = OOS +4.0)
   and a fine fallback — but **caps the tail on trend** (+21 OOS vs the wide +47). Good chop/build option, **grave on
   trend**. Not a global replacement.
4. **Tightening chandelier `k1.5` (T-configs).** Never best in any cell; the loose-then-lock mechanism dominates it.
   Retained only as the existing chop/counter branch of the live selector.
5. **The incumbent uniform `lock_r=6.0` itself (the thing rehabbed).** Validated on **trend only**; a grave in build
   (OOS −9.5) and chop (OOS −1.2). Keep it, but *scope it to trend*.
6. **thrust/absveto in CHOP — no exit rescues it.** Every config is −EV or fragile (incumbent IS −3.3/OOS −1.3;
   best `fix3.0` still −2.3 IS). **Honest NULL: you cannot fix a chop-momentum bleed with an exit** — it's the
   signal/regime → the router's job to bench. (Its BUILD cell *is* fixable: `L2.5/2.5/0.5` IS +8.3 / OOS +6.3,
   `fix2.5` IS +7.8 / OOS +6.6 — both robust; the incumbent wide there is fragile IS −0.8.)

**Not a fake win:** the fix **drops zero entries** — it re-tunes the trail on the same trades, banking the tail
earlier off-trend while *keeping every trend runner on the wide trail*. It directly rescues the symptom trade (07-27
4.2R: under `lock_r=3.0` the lock engages at 3.0R and trails 0.5·ATR → banks ~3.5R instead of giving back to +$23).

---

## 5. ROBUSTNESS

- **OOS (archive 07-06..15 vs capture 07-16..31):** the fix holds both legs — grind BUILD `L3.5/3.0/0.5` **+7.5/+4.6**,
  grind TREND wide **+52/+47**, thrust BUILD `fix2.5` **+7.8/+6.6**. The incumbent's build edge **does not** (+12.7/−9.5).
- **Per-ISO-week (W27–W31):** grind TREND wide green 3/4 weeks (carried by real trend weeks, as intended). grind
  BUILD fix green **4/4** weeks. grind CHOP is week-unstable for *every* config (W29 −$1,456, W31 +$3,476) → not a
  tuning target, a **benching** target.
- **Leave-one-day-out:** grind BUILD fix `loo_worst +6.0`; grind TREND wide `loo_worst +40`. Both survive dropping
  any single day. grind CHOP incumbent `loo_worst +0.5` (fragile, one day from red).
- **Strip-the-best-3:** grind TREND wide falls +52→+15 (tail-carried, expected for a runner exit — still positive);
  grind BUILD fix +7.0→+5.4 (broad, not tail-dependent). The give-back overlay's build win **evaporates** on strip
  → confirms it was tail/cell noise.
- **Cross-regime is the whole point:** every number above is reported on its **home segment**; there is deliberately
  **no blanket cross-tape figure** (it would average trend's +47 with chop's −1 and lie).

---

## 6. VERDICT & EXACT CONFIG

**VERDICT: REGIME-DEPENDENT — FIXED per regime.** The chandelier is not retired and not a bleed; it is the desk's
best tail-capture edge **when scoped to the regime it was built for**.

**Runner-trail policy (the proven Rs, vs the guess):**

| regime (entry 30m ER) | GUESS (deploy prior) | PROVEN | action |
|---|---|---|---|
| TREND ER≥0.50 | `lock_r=6.0` | **`lock_r=6.0`** (OOS +47) | **keep** the wide lock — do not touch |
| BUILD 0.30–0.50 | `lock_r=6.0` | **`lock_r=3.0`** (OOS +4.6) | **lower** the lock (or `fix2.5` fallback) |
| CHOP ER<0.30 | `lock_r=6.0` | *(no robust exit)* | **router benches**; if armed, `lock_r=3.0` to cap bleed |

**Where to wire it (precise).** The live `scaleout` slate's **dual-slot Lot-B "wide" tail is the only regime-blind
path left**: it builds a *static* `exit_chandelier_lock(3.5, 6.0, 0.5)` with `adaptive_exit=False`
(`slot_strategy.py:190-192`), so it rides `lock_r=6.0` in every regime. (The single-position roster already
regime-conditions correctly — `build_specs` sets `adaptive_exit=True`, and the selector only uses the wide lock in
`mode=="wide"`/aligned-trend, `slot_strategy.py:317-324`.) **Only `grind_long` is still exposed**: it's in `_BIG_RUN`
and absent from `exit_overrides.json`, so it defaults to Lot A@2.5R + **Lot B "wide"=lock_r 6.0**. (The operator
already pulled `abs_veto_long/short` off "wide" onto `b:2.5` on 07-31 — same instinct; this rehab shows *why* and
that the trend case argues for keeping a *regime-gated* wide, not a flat scalp.)

**Recommended change (one of):**
- **(cleanest)** Make Lot-B `"wide"` regime-aware: in `_manage`, when `spec.exit=="chandelier_lock"` on a Lot-B wide
  tail, read the entry regime (`self._exit_mode`, already computed) → `lock_r = 6.0 if mode=="wide" else 3.0`.
  Mirrors the existing `adaptive_exit` selector; keeps the wide edge on trend, kills the off-trend give-back.
- **(no-code, via the existing control panel)** Add `lock_r` to `exit_overrides.json` semantics, or set
  `grind_long` to `{"a_r":2.5, "b":"tight"}` when the router regime is not trend — but the code path (cleanest) is
  preferred so trend still gets the wide ride automatically.

**Expected effect:** on the taken trades, +~22% on the chandelier/giveback book (+$648 reconstructed) with the
trend riders untouched; forward, it removes the ~$185-per-runner give-back on the 4R off-trend runners that are the
bulk of the population, while preserving the +$47/sig trend edge that makes this exit worth keeping.

**Revert:** Lot-B `"wide"` → static `exit_chandelier_lock(3.5, 6.0, 0.5)` (current), or drop the `lock_r` override
from `exit_overrides.json`.

**Caveat (honest):** trend n is thin (grind trend n=30 replay / n=4 live) — the +47 OOS trend edge leans on real but
few big-ATR runs; the *build* fix (n=439 replay, robust 4/4 weeks + OOS) is the sturdier leg. Re-measure both after
the next clean-trend week before treating the trend number as more than a strong prior.
