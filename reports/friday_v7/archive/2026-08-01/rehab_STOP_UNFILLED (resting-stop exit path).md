# REHAB — `STOP_UNFILLED` (resting-stop exit path)

**Target:** the exit-mechanism flagged as *"the single worst exit-mechanism bleed of the week"* — 4 stops
that never filled (abs_veto_long −89, abs_veto_short −106 = **−195 this week**), the known
**ContFuture "resting stop does not trigger"** defect (naked-stop / toothless-stop exposure).

**Discipline:** full rehab (normalize → reconstruct → root-cause → filters → robustness → verdict),
**tick-honest** ($2/pt MNQ, **$1.50/RT per contract**), on this week's `capture.db` + the archive.
Regime-segmented per the 2026-07-31 backtest rule — no blanket cross-tape number.

**Data:** live book `data/gazbot7.db` `trades` (16 Jul–31 Jul, 487 trades); tape `data/capture.db`
(5s bars 15 Jul→31 Jul; 250ms ticks 23 Jul 22:00→31 Jul 21:00 UTC — **all 4 this-week trades are
tick-covered**). ATR = 14-period on 1-min bars folded from 5s (matches `deciders._atr` / `agg.py`),
stop = **1.0 × ATR** (`stop_atr_mult=1.0`, all gates). Scripts: `scratchpad/rehab_stopunfill.py`,
`rehab_segment.py`, `rehab_robust.py`.

---

## ★ HEADLINE VERDICT — **FIXED (already deployed & verified in production)**

The `STOP_UNFILLED` exit path is **CLOSED**. The last `STOP_UNFILLED` in the entire book is trade
**325 @ 2026-07-28 08:02 UTC** — **32 minutes before** the guard-as-primary fix `d0218c6`
(2026-07-28 08:34 UTC) went live. Since that deploy: **103 clean `STOP` fills, ZERO `STOP_UNFILLED`.**
`STOP_UNFILLED` is retired as an exit reason.

| window | STOP_UNFILLED | clean STOP |
|---|---|---|
| before d0218c6 (≤07-28 08:34) | **26** (−1,377.5 recorded) | — |
| at/after d0218c6 | **0** | **103** |

**Config that fixes it (LIVE, no action needed):**
- `99e3c11` (07-27 09:39) — rest protective stops on the **concrete front-month Future**, not the ContFuture (cut ~18%→~11%; did **not** kill it).
- `1cae80d` — place fillable **StopLimit** 20pt past trigger (kills IBKR-paper's toothless auto-limit; did **not** kill it).
- **`d0218c6` (07-28 08:34) — the one that worked:** `MultiSlotCore.note_price` runs `_check_stop_breach` **every tick (~2s, 2-tick spike guard)**, market-flattens **at** the stop and books **`STOP`**. Stops no longer depend on IBKR's trigger firing at all. Native StopLimit + 5s audit loop remain as backups.

The rehab below proves (a) the fix mechanically removes the bleed on real tape, and (b) **the "−195" headline is mostly mislabeled** — most of it is ordinary stop-loss the losing entries earn regardless of the exit bug.

---

## (1) NORMALIZE the malfunction — *"what would the loss have been if the stop had worked?"*

Every `STOP_UNFILLED` is a genuine stop-out: on the tape **all 26 trades' price actually touched the
1-ATR stop level** (`touched=True`). The bug is not "wrong level" — it's that IBKR's trigger didn't fire,
so a backstop flattened **late**, a few points past the stop. So "normalized" loss = fill exactly at the
1-ATR stop.

**Per-trade (tick-honest), all 26:**

| | realized (recorded) | perfect-stop (fill @1-ATR) | **defect TAX (excess)** |
|---|---|---|---|
| **ARCHIVE n=26** | **−1,389.5** | **−1,059.3** | **−330.2**  ($−12.70/trade) |
| **THIS-WEEK n=4** | **−195.0** | **−142.0** | **−53.0** |

This-week detail (all tick-covered; MAE = max adverse excursion during the naked window):

| id | gate | side | realized$ | perfect$ | tax$ | MAE | intended stop |
|---|---|---|---|---|---|---|---|
| 285 | abs_veto_short | S | −61.5 | −41.4 | −20.1 | 31.2pt | 20.0pt |
| 287 | abs_veto_long | L | −51.0 | −32.7 | −18.3 | 26.8pt | 15.6pt |
| 324 | abs_veto_long | L | −38.0 | −32.4 | −5.6 | 22.0pt | 15.4pt |
| 325 | abs_veto_short | S | −44.5 | −35.5 | −9.0 | 27.0pt | 17.0pt |

**Key normalize finding:** losses were **BOUNDED, not runaway** — MAE ran ~5–11pt past a ~15–20pt stop,
never a blowout (contrast the historical −$216 MAX_HOLD naked-ride, 87pt past stop, that killed a whole
`venue_audit_loop`). The guard caught every one within its window.

## (2) Corrected-cost RECONSTRUCT — the true P&L split

Of the headline **−195 this week**, only **−53 is the exit defect**; **−142 is the ordinary 1-ATR
stop-loss** these four losing entries would have taken *with a perfectly working stop*. Archive-wide:
of −1,389.5, only **−330.2 (24%)** is the defect; **−1,059.3 (76%)** is normal stop-loss.

> **The "single worst exit-mechanism bleed of the week" is mislabeled.** `STOP_UNFILLED` is not an
> exit *strategy* that lost money — it's a **STOP that fired late**. Three-quarters of the number is the
> signal being wrong-way in chop and correctly hitting its stop; only a quarter is the mechanism.

## (3) ROOT-CAUSE — base / exit / signal?

Split cleanly across the two layers:

- **EXIT-mechanism defect (the actual `STOP_UNFILLED` bug):** −53 this week / −330 archive.
  Cause = IBKR won't fire a resting stop's trigger (ContFuture, then paper-account flakiness even on the
  concrete Future). **Root-caused and FIXED** (`d0218c6`, per-tick tape stop). Not base config, not signal.
- **The other 76% (−1,059 archive) = SIGNAL / regime:** losing entries (chop grind_long, down-leg
  rgv_long/capitulation, counter-trend abs_veto) that hit a correct stop. This is the **router's** job
  (bench counter-trend/chop momentum) — it is **not** an exit-path problem and this rehab does not claim it.
- **BASE config (`stop_atr_mult=1.0`) is sound:** widening the stop only enlarges these losses (all
  touched); tightening raises stop-out frequency and still wouldn't address a trigger that doesn't fire.
  Not the lever.

## (4) FILTERS — keep the winners, cut the bleed (incl. the NULLs & the FAKE WIN, shown honestly)

**NULL / category error — "filter `STOP_UNFILLED` to keep its winners":** an exit *reason* has **no
winners** — every `STOP_UNFILLED` is a loss by construction. You cannot filter it to "keep winners." The
only real levers are (a) fix the mechanism [done], (b) cut the underlying entries — which is a **gate/router**
question, tested next.

**★ FAKE WIN — REJECTED — "bench abs_veto overnight" (where 3 of the 4 live):**
regime × time-of-day segmentation of the whole abs_veto family shows the overnight bucket that holds the
STOP_UNFILLED losers **also holds abs_veto's biggest winners of the archive**:

```
overnight abs_veto: n=36  net=−90.5   wins=12  losses=24
  winners a blanket overnight-bench would KILL (top):
    370 abs_veto_long_B  CHANDELIER  +342.0   (07-29)
    362 abs_veto_long_A  TARGET      +134.5
    386 abs_veto_long_A  TARGET      +101.5
    404 abs_veto_long_A  TARGET       +91.5   ... (+$1,003 of winners total)
  the STOP_UNFILLED losers it would (also) cut:
    283 −43.0 · 284 −35.5 · 285 −61.5 · 287 −51.0   (−$191, of which only ~$50 is the defect tax)
```
Dropping **+$1,003 of winners to save ~$50 of defect** is a textbook fake win. **REJECTED.** A
time/regime filter on the underlying gate is the wrong tool; the exit-mechanism fix (`d0218c6`) is the
right one — it removes the tax **without touching a single winner**.

**abs_veto family, per (time-of-day × regime)** — segmented, home-segment scoring (no blanket number):

| bucket | n | net$ | win% |
|---|---|---|---|
| US-session/trend | 14 | **+668.5** | 57 |
| pre-open/normal-chop | 8 | +423.0 | 62 |
| overnight/high-chop | 6 | +244.0 | 33 |
| overnight/normal-chop | 11 | +6.5 | 45 |
| overnight/building | 16 | −235.0 | 25 |
| US-session/building | 5 | −145.0 | 20 |
| pre-open/building | 4 | −148.5 | 0 |

abs_veto's edge is **US-session trend** (+668) and its bleed is the **"building"** (rising-ATR pre-break)
buckets — a **signal/router** targeting problem, orthogonal to the exit bug and owned by the live router.

## (5) ROBUSTNESS

**Guard-window on real ticks (the fix's mechanical proof)** — for the 7 tick-covered trades, replay a
flatten at `touch+2s` (post-fix per-tick path) vs `touch+10s` (old audit-loop window) vs the recorded late
flatten:

| | realized (old path) | @+10s (old guard) | **@+2s (d0218c6)** | perfect |
|---|---|---|---|---|
| tick-covered n=7 | −339.5 | −283.5 | **−253.0** | −268.0 |

- **d0218c6 gain (10s→2s) on real tape = +$30.5**; **@+2s residual vs a perfect stop = +$15** (i.e. the
  2s flatten actually beats "perfect" — noise bounces back inside 2s). **The tax is eliminated.**
- The recorded path (−339.5) is worse than even the 10s model — the pre-fix flatten sometimes took
  **longer** than 10s (5s audit × 2-streak + reconcile lag), and on 287/325 price kept running. This is
  exactly the variable leak d0218c6 removes.

**Per-ISO-week (tax is stable, not one-week):** W30 −277.2 over n=22 ($−12.6/tr) · W31 −53.0 over n=4 ($−13.2/tr).

**Strip-the-best:** remove the single worst-tax trade (id202 capitulation_long, −68.9) → tax still
−261.2 over n=25 ($−10.45/tr). Not an outlier artifact.

**Leave-one-day-out:** tax/trade stays −$7.3 … −$14.8 dropping any single day. No day drives it.

**Cross-regime:** the tax appears in trend gates (rgv down-legs), chop (grind_long) and momentum
(abs_veto) alike — it is **mechanism-driven, not regime-conditional**, so a single mechanism fix (not a
regime policy) is the correct treatment. ✔

## Graves & NULLs (the trying, shown — not hidden)

1. **GRAVE — trust IBKR's native trigger / add an ER-floor to the stop gate:** tried, reverted; the trigger simply doesn't fire on paper. (memory [[exhaustion-short-counter-veto]] pattern: ER floors fake.)
2. **GRAVE — concrete-Future stop (`99e3c11`):** correct and kept, but only 18%→11% — **did not kill it** (2 residual on 07-28). Honest partial.
3. **GRAVE — fillable StopLimit (`1cae80d`):** kills the toothless paper auto-limit, kept — but IBKR paper still wouldn't fire the trigger. Honest partial.
4. **NULL — filter the exit reason to "keep winners":** category error; no winners exist on a stop-out.
5. **FAKE WIN, REJECTED — "bench abs_veto overnight":** drops +$1,003 winners to save ~$50 defect (§4).
6. **NULL — widen/tighten the 1-ATR stop:** all trades touched the stop; widening enlarges the loss, tightening raises frequency; neither addresses a non-firing trigger.
7. **WINNER — guard-as-primary per-tick flatten (`d0218c6`):** the only attempt that drove new `STOP_UNFILLED` to **zero** (103/0 since) and, on tape, cuts the tax to ≤0.

## R-target / threshold note (backtest-discipline)

The Lot-A/Lot-B scalp-R cheat-sheet (faders 0.5/1.5, momentum 1.5/2.5, trend 2.5/wide) is a **profit-target**
sweep and belongs to the **gate rehabs** (abs_veto etc.), not to this **stop-exit-path** rehab — the R-target
never touches the `STOP_UNFILLED` path. The only in-play threshold here is the **guard cadence**
(`STOP_BREACH_FLATTEN_STREAK=2 × per-tick ≈ 2s`), which §5 measured directly on ticks and found at/below the
perfect-stop cost — i.e. already at its robust optimum (a 1-tick guard risks spike-flattening; ≥3 ticks
re-introduces the leak). No further sweep warranted.

---

## VERDICT — **FIXED**

- **Exact config (LIVE, deployed, verified):** `d0218c6` guard-as-primary per-tick (~2s) tape-stop that
  books `STOP`; on `99e3c11` (concrete Future) + `1cae80d` (fillable StopLimit). `stop_atr_mult=1.0`
  unchanged. `STOP_UNFILLED` retired.
- **Proof:** 26 STOP_UNFILLED all before the fix; **0 after; 103 clean STOP fills since.** Tick-replay
  shows the 2s path removes the tax (−253 vs −268 perfect on the covered set).
- **Marginal cost the bug ever carried:** ~**−330 archive / −53 this week** (the rest of the "−195" was
  ordinary stop-loss, a **signal/router** matter, not an exit defect).
- **No new action required on the exit path.** Standing watch: `sweep.py` CRITs on `audit_age_s>30`
  (dead-auditor guard) and the naked-position watchdog remain the backstops. Revert risk: `git revert
  d0218c6` re-introduces the leak — do not.
- The residual bleed to chase is **not here** — it's the underlying entries (abs_veto "building"-bucket,
  chop grind_long, down-leg rgv_long/capitulation), which is the **router/gate** rehabs' territory.
