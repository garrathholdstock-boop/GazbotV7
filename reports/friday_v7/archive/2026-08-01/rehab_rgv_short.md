# GATE REHAB — `rgv_short` (reversal_grab / SHORT)

**Discipline:** full 6-step rehab, tick-honest ($2/pt, $1.50/RT), regime-SEGMENTED (never a
blanket cross-tape number — the operator's 2026-07-31 backtest rule). **Every attempt shown,
including the NULLs and graves.**

**Data used**
- Live actuals: `data/gazbot7.db` `trades` where `gate LIKE 'rgv_short%'` — 43 fires, 07-21 → 07-30.
- Tick-honest reconstruction: `data/capture.db` (MNQ 5s bars → 1-min signal + 250ms ticks). **Tick
  tape covers 07-23 22:00 → 07-31 21:00 UTC only** — reconstructions are for that window; earlier
  live trades are read from the ledger, not tick-repriceable.
- Shadow board: `data/shadow.db` `shadow_trades ⋈ shadow_real` (tick-honest `real_pnl`) — the 6
  reversal-short config variants (base vs filtered).
- Engines: the REAL `gate_reversal_grab` + real exit functions from `src/gazbot7/deciders.py`
  (scripts `scripts/rehab_rgv_short.py`, `scripts/rehab_rgv_short_seq.py`).

**Current LIVE config** (`slot_strategy._RGV_SHORT`, post-07-25 rehab):
`ext_min 1.5 · turn_atr 0.25 · flow_min None · atr_min 20 · fast_slope/fast_turn OFF`,
`base_size 2` (dual-slot scale-out A/B), `exit scalp 2R / 1-ATR stop`, `adaptive_exit ON`
(regime picks exit width at entry), router-managed (`UP_OFF = {rgv_short}` — benched on UP-bias days).

---

## Headline verdict (read first)

> **REGIME-DEPENDENT + DATA-STARVED → keep in SHADOW; do NOT re-arm standalone on current evidence.**
> On the honest tick tape rgv_short fires only **11 times** (single-position, first-to-fire) and is
> **net-negative at every exit config** (1.5R −$32 · 2R −$142 · 2.5R −$253 · chandelier −$190) and
> **fails every robustness cut** (strip-best-1 → −$242, strip-best-3 → −$402; the whole book leans on
> one +$80 day). The bleed is **NOT a malfunction, NOT the base config, NOT primarily the exit** — it
> is **regime/direction + data-starvation**: the signal has no *robust* edge in the regimes it can
> actually trade, and there are far too few clean fires to claim one. It is **not disproven — it is
> unproven.** Base config is already fine; flow filters make it worse. TRULY-RETIRE is NOT warranted;
> arming it live IS not warranted either. Shadow it and accumulate cross-regime n.

---

## Step 1 — NORMALIZE the malfunctions

Live book has **2 malfunction exits** out of 43 fires (−$235.5 combined, 57% of the −$416 headline):

| id | when (UTC) | reason | recorded | normalized | note |
|----|-----------|--------|---------:|-----------:|------|
| 114 | 07-21 00:30 | `MAX_HOLD` | −$171.0 | **exclude** | **Pre-rehab config** (07-21 = old `fast_turn` era, before the 07-25 fix) + a broken 2-hour overnight hold to the max-hold cap (no working scalp/stop exit). Not the current gate; not tick-repriceable (pre-tape). Remove from the current-config verdict. |
| 236 | 07-24 05:11 | `STOP_UNFILLED` | −$64.5 | **≈ −$56** | Known ContFuture resting-stop bug ([[stop-unfilled-contfuture-root-cause]]). But: exit filled 28595.25 vs entry 28579.5 = **15.75 pt adverse on 2 lots** — an overnight low-vol snap-back that filled ≈ at where the 1-ATR stop would have fired anyway. **Malfunction cost ≈ +$8 (negligible)** — the stop-unfill did NOT let it run away. |

**Normalization result:** removing the pre-rehab `MAX_HOLD` and fixing the `STOP_UNFILLED` to a working
stop moves the live book from **−$416 → ≈ −$237**. **The malfunctions are a minor part of the loss —
the bleed is real** (STOP 20× = −$1,254.5 vs TARGET 6× = +$733). No naked rides found in the rgv_short set.

## Step 2 — Corrected-cost RECONSTRUCT

Repricing every live fill at $2/pt − $1.50/RT reproduces the desk's recorded P&L within fee-rounding
(recorded −$416.0 vs price-reconstructed −$443.0; the gap is the desk logging a flat $1.50/trade vs
$1.50/contract on the 2-lots). **No hidden cost/slippage distortion** — the recorded book is honest.

Live P&L by exit reason (corrected-cost):

| reason | n | net |
|--------|--:|----:|
| STOP | 20 | **−$1,254.5** |
| TARGET | 6 | +$733.0 |
| GIVEBACK | 15 | +$341.0 |
| MAX_HOLD (malfn) | 1 | −$171.0 |
| STOP_UNFILLED (malfn) | 1 | −$64.5 |
| **total** | **43** | **−$416.0** |
| current-era, malfn-normalized | 41 | **≈ −$237** |

**This-week (≥07-27) = −$154.5 / 3 fires**, and neither was a clean home-regime loss:
`316` (07-27 19:01, aligned-DOWN **but building/trending** ER 0.38 → stopped, no pop to fade, −$47.5)
and `455`/`456` (07-30 22:07, the midnight-reset **counter-UP dual-slot** churn the router benched
within 15 min, −$107 — see ledger 21:58 UTC "reset-design cost").

## Step 3 — ROOT-CAUSE (base / exit / signal?)

Tick-honest, **single-position first-to-fire** (the realistic tournament: one position, re-arm only
after it exits) over 07-24 → 07-31, LIVE base:

| exit | fires | net | $/tr | win% |
|------|------:|----:|-----:|-----:|
| scalp 1.5R | 11 | −$32 | −$2.9 | 45% |
| scalp 2.0R (live) | 11 | −$142 | −$13.0 | 36% |
| scalp 2.5R | 11 | −$253 | −$23.0 | 27% |
| chandelier_lock | 11 | −$190 | −$17.3 | 27% |

- **Base config? NO.** The base-param sweep (ext_min × turn_atr × flow_min, home regimes only) shows
  no config rescues the home regime; the LIVE base (ext 1.5 / turn 0.25 / no-flow) is **among the best**
  of them. Tighter ext looked good on all-tape (ext 2.0 = +$672) but that number is the blanket-BUG
  (see graves) and collapses to a handful of fires single-position. **Not a base-tuning problem.**
- **Exit? SECONDARY.** Tighter is less-bad (1.5R −$32 vs 2R −$142 vs wide/chand worse). The fade does
  **not run** — widening to "ride" it (2.5R/3R/chandelier) makes it worse, so the live 2R + adaptive-wide
  is a mild aggravator, not the cause.
- **Signal / regime? YES — the root cause.** The signal has **no robust edge in the regimes it can
  actually trade.** By regime (scalp 2R, single-pos): `building` −$94 (n2, 0%w — a fader gets run over
  in a trend even when aligned), `normal-chop` −$69 (n7), `violent` −$79 (n1), `dead-chop` +$100 (n1,
  a single fire). By alignment: aligned-DOWN −$138 (n7), counter-UP −$4 (n4). **Even firing WITH the
  down-trend, it bleeds.**

**Root-cause verdict: REGIME/DIRECTION + DATA-STARVATION, not base, not exit, not malfunction.**
Live aggravators layered on top: **dual-slot (base_size 2)** doubles every chop stop, and the
**midnight-reset "all-6-on"** hands it counter-trend churn before the router can bench it (07-30).

## Step 4 — FILTERS that KEEP winners while cutting bleed

Tested each candidate; **a filter that "wins" only by dropping the target winners is a FAKE win —
rejected and shown as such.**

| filter | result | keep? |
|--------|--------|-------|
| **Bench `building`+`clean-trend`+`violent`** (fade only chop) | Removes −$94 building + the violent fires. Legit — a fader has no edge in a trend, and the violent "wins" are artifacts (see graves) in an un-tradeable high-ATR regime. | ✅ (regime discipline) but insufficient alone |
| **Aligned-DOWN only** (router's UP_OFF, sharpened) | aligned-DOWN scalp-2R = **−$138 (n7)**. Does NOT rescue. | ❌ REJECT as a fix |
| **Tight 1.0R scalp, home regimes** | home +$110 (n12, 58%w) — the **only** positive slice. But strip-best-1 on the full book → −$242; leans on 1-2 fires. | ⚠ MARGINAL, not a fix |
| **Flow-confirm (flow_min 25 / 50)** | Shadow tick-honest: raw +$184 **>** flow25 +$104; flow50 +$244 but mixed & outlier-driven; live-base home sweep: flow HURTS (flow25/50 mostly negative home). | ❌ REJECT (NULL — filtering does not earn it) |
| **turn_atr 0.5** (`rg_short_050`) | Shadow real −$16 (worst of the turn settings). | ❌ REJECT (NULL) |
| **1.5R target variant** (`rg_short_025_flow25_t15`) | Shadow real −$26 — the **worst** flow variant; the closest analogue to the live scalp. | ❌ REJECT (NULL) |

**No filter both keeps the winners AND turns the gate robustly positive.** The best honest slice
(tight-scalp × chop × aligned) is marginal and fragile.

## Step 5 — ROBUSTNESS (the gate fails these)

LIVE base, scalp 2R, single-position, 07-24 → 07-31:

- **Per-day:** 07-24 +$8 (n2) · 07-27 −$94 (n2) · 07-28 **+$80 (n1)** · 07-30 −$4 (n4) · 07-31 −$132 (n2). **Total −$142 / n11.**
- **Strip-the-best:** best-1 removed → **−$242** · best-3 removed → **−$402**. (A positive-looking book only via its 1-3 luckiest fires = not an edge.)
- **Leave-one-day-out:** remove 07-28 → **−$223** (the whole book leans on one +$80 single fire); remove 07-31 → −$10. Wild swings on 1 day = not robust.
- **Cross-regime / n:** **11 honest fires in the entire tick week.** Data-starved — no basis to certify any config.
- **Shadow (blanket, unsegmented — itself the operator's "BUG", shown for completeness):** raw +$184
  (n30), flow50 +$244 (n23), flow25 +$104, flow50_rth +$100, 050 −$16, flow25_t15 −$26 — **but these
  are cross-tape blanket numbers dominated by the same violent/aligned outliers; they do not survive
  segmentation and must not be read as an edge.**

## Step 6 — VERDICT

**REGIME-DEPENDENT + DATA-STARVED → SHADOW (do not re-arm standalone).**

- **Not FIXED:** no config is robustly positive on the tick tape; all fail strip-best / LODO.
- **Not TRULY-RETIRE:** the signal is *unproven*, not *disproven* — 11 fires is too few to condemn it,
  and the base is not the problem. Retiring it would be as unjustified as arming it.
- **Recommended posture:**
  1. **Keep `rgv_short` BENCHED in the live tournament** (leave `UP_OFF` router management on; do not
     restore as an armed standalone gate on this evidence).
  2. **Run `rg_short_025_raw` (base, no-flow, 2R) in SHADOW** to accumulate cross-regime n — it is the
     best base and the least data-starved variant. Re-evaluate Saturday when n grows / a 2nd regime lands.
  3. **If the operator insists on live:** single-lot only (**drop dual-slot base_size 2 → 1** — it just
     doubles chop stops), **tight 1.0–1.5R scalp** (wide/chandelier proven worse), **hard-bench
     building + clean-trend + violent + counter-UP**, and **no all-6 midnight reset** (that is where
     07-30's −$107 came from). Even then it is fragile — shadow is the honest call.

---

## ★ The TRYING — every attempt, including the NULLs and graves

Shown in full because the operator wants the honest failures, not a cherry-picked win.

- **GRAVE — the blanket "+$304 cross-tape" number.** v1 (`rehab_rgv_short.py`) re-fired the gate every
  minute even while a position was open, and reported a blanket +$304. **This is exactly the operator's
  "blanket = BUG."** Segmented, the +$304 was 4 `violent` US-open fires (+$380) — and single-position it
  **collapses to −$142.** Rejected.
- **GRAVE — the "aligned-DOWN + wide-exit = +$663" edge.** v1's aligned-DOWN subset at 3R/chandelier
  looked like a real continuation-fade edge (+$663 / +$618). It is an **artifact of stacked re-fires**:
  07-31 14:56, 14:57, 14:58 counted **three** +$154 fills on **one** violent US-open flush (ATR 39) that
  the live first-to-fire tournament takes **once**. De-duplicated (single-position), aligned-DOWN in the
  tradeable regimes is **negative**. Rejected — and it lived in the `violent` regime the router benches
  and the operator's own exhaustion trial proved scalps fail in (high-ATR 0.5R < 1-ATR stop, 07-31 13:52).
- **NULL — flow-confirm filter (flow_min 25/50).** The mirror of the abs_veto momentum filter. Raw base
  (+$184) beats flow25 (+$104); flow50's +$244 is outlier-driven and home-regime negative. Filtering does
  not earn the gate — consistent with the 2026-07-24 decision to drop the ER/absorption confirm
  (`CONFIRM_GATES = frozenset()`, deciders.py note: "blunt exposure cut, not a stabiliser").
- **NULL — turn_atr 0.5 (`rg_short_050`).** Shadow real −$16. The looser turn does not help.
- **NULL — 1.5R target (`rg_short_025_flow25_t15`).** Shadow real −$26, the worst flow variant — the
  closest analogue to the live scalp, confirming the exit is not where the fix lives.
- **NULL — widen to ride (2.5R / 3R / chandelier).** Single-position all worse than the tight scalp
  (2.5R −$253, chand −$190) — the fade does not run; there is no tail to capture.
- **NULL — base-param tightening (ext_min 2.0).** Looked +$672 all-tape (n11) but that is the blanket-BUG
  again; single-position it is a handful of fires and does not survive. The live ext 1.5 is not the problem.
- **NULL — alignment-only filter (aligned-DOWN).** −$138 (n7) — the router's UP_OFF is right to bench
  counter-UP, but aligned-DOWN alone is not an edge.
- **Aggravators identified (live, not backtest):** dual-slot `base_size 2` doubles every chop stop; the
  all-6 midnight reset feeds it counter-trend churn (−$107, 07-30) before the router benches it.

*Caveats: 1 week of tick tape, one summer regime, 11 honest fires — everything here is a LEAD, not a
law. The single most valuable next step is n, via shadow.*
