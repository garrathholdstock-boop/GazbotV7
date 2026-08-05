# WEEKEND 2026-08-01 / 08-02 — what changed, and what got withdrawn

> **Read the withdrawals first.** Five headline recommendations went into this weekend and **one survived
> intact**. The pattern is the point: every number that was computed once and never re-derived turned out
> to be wrong or badly inflated. Nothing here should be trusted because it is written down — each item
> carries the test that survived and the caveat that did not.

---

## 1. WITHDRAWN — things that looked true on Friday and are not

| Claim | Verdict | What killed it |
|---|---|---|
| Router: "stop benching momentum in TREND_UP" = **+$1,615/wk** | **WITHDRAWN** | Reproduced the arithmetic (+$1,644), then broke it: a *temporal* double-count (same error the section caught on another axis) cuts it to +$767; strip best-5 → +$85; a 20,000-draw placebo says the TREND_UP label carries no information (ADX tag z=−0.16 p=0.56; regression tag z=−2.56, worse than random). 52% of it is two `grind_long` episodes on a day MNQ fell 702pt — bounce money on a DOWN day. |
| grind exit cell `{a_r 0.5, b 1.0}` | **WITHDRAWN** | −$1,127 *worse* than the loaded default on a sequential sim. The supporting MED-TREND cell inverts from +$10.3/tr to −$5.19/signal once run long-side-only on 250ms ticks. |
| grind entry fix = **£700/wk** | **WRONG BASELINE** | The replay applied floors that were dead on the live desk since 07-29. Honest before/after is **+$1,552 → +$2,830**, not −$284 → +$2,830. Also: use **ATR 10, not 12** — 12 is one notch the wrong side of a cliff, worth $941. |
| capitulation `require_flip=False` + 1.0R = **+$434 @ 78% win** | **WITHDRAWN, shipped then reverted** | "78% of bounces reach 1R" is an **MFE** stat used as a win rate — it ignores whether the stop came first. On this gate's own live entries: "reached 1R" = 14/14 = **100%**; actually hit +1R *before* −1R = **4/14 = 29%**. Breakeven at 1.0R/1.0×ATR is 50%. Corroborated by the byte-identical shadow twin (−$5,250 / 238 fires / 16.8%) and the live gate (−$122 / 24 / 37.5%). |
| NIPC = "+$2,676, the greenfield survivor" | **HELD, but 3.7× smaller** | Its acceptance replay used **$5/RT** — the real fee is **$1.50**. Corrected, the replay is +$820 / $5.2 per trade against the lab's ~$19, and days-green then matches the lab exactly (9/12). Armed live as an experiment with a kill review at n≥40 or 08-07. |
| Dead ER/ATR floors | **CONFIRMED** — the one that held | Independently reproduced three times by three different routes. Magnitude was overstated 44× though (7,734 raw log lines = 383 de-duplicated episodes). |

---

## 2. Live desk changes

**Router (`scripts/router_tick_durable.py`)**
- `PINNED` all-six → **`frozenset()`**. A full-roster pin made the change set permanently empty: **411 ticks across 07-31/08-01 applied nothing** while logging the healthy-looking "no change". Last real switch change had been 07-30 22:15.
- All-pinned **alarm** added, then rewritten — the first version was roster-size dependent and would *not* have caught the incident it was written for. Now a behavioural test: "the router named changes and every one was pin-suppressed".
- `SUPPRESSED-BY-PIN` log line so a dead router and an idle one can never print the same thing again.
- Standing guidance: rgv benched (and **re-armed nightly by policy**, so the router must re-bench it — that is housekeeping, not thrash); bench `abs_veto_short` in violent whipsaw; do *not* bench `abs_veto_long` merely for being momentum-in-chop (it is an overnight chop gate); keep the fader bench; do **not** widen into the refuted TREND_UP rule.

**Entry filters (`deciders.py`, `tournament.py`)**
- `ER_FLOOR = {}` — both deleted. Their blocked books were **+$2,923** and **+$640**; they were filtering out profit.
- `ATR_FLOOR` — grind 24 → **10**, `abs_veto_short` 16 **deleted** (not proven), capitulation 10 kept (the only floor that earns: blocked book −$459).
- `tournament.py:139/142` now pass **`_base(slot)`**. Under the scale-out slate every tag carries an `_A`/`_B` suffix while the floor dicts are keyed on base names, so **no floor had blocked anything since 07-29 16:20**. The audit found two more sites with the same bug (`ER_HOLD`, `CONFIRM_GATES`) — consequence: the momentum ER-hold shadow has recorded nothing since the cutover, so do not read its zero as a finding.

**Exits (`slot_strategy.py`, `data/exit_overrides.json`)**
- grind `+ ext_hi 2.0`; exhaustion → A 0.75R / B k1.5; abs_veto_long → A 1.0R / B 1.5R (its live cell was worst of eleven swept).
- capitulation **reverted** to `require_flip=True` / 2.0R, override cell removed.
- **★ The quiet-tape clip** — see `docs/REGIME_EXIT_CHEATSHEET.md`. ATR < 22 → both lots clip ($40 / 1.75R floored $60); ATR ≥ 22 unchanged. Decided at entry, frozen for the position.

**Gates** — `rgv_short` benched (re-arms nightly, router re-benches). **`nipc_long`/`nipc_short` live** at 1 lot.

**`ER_TREND` 0.20 → 0.15**, kept — but the rationale was corrected: the fader-bench study that justified it measures `direction_router`'s timer, which is **disabled**. The only live consumer is `_regime_mode` via `veto_counter_regime`, i.e. **exhaustion_short only** — ~23% more counter-vetoes. Kept because that is the cheap direction, not because the cited benefit is reachable.

---

## 3. Shadow board

Retired **13** of 31 (slate 28 → 18). The board was −$7,505 and these carried −$8,122; the retained 16 are +$616. Retired on a *convicting number*, not P&L rank — see `RETIRED` in `shadow.py` for the per-variant reason.

**Protected despite looking retirable:** `thrust_loose` (the un-vetoed control the abs_veto **+$2,537.5** claim is measured against — retiring it would destroy the justification for a live gate), `capit_loose` (now the no-flip control), `chand_k35`, `thrust_short_raw`, `rg_short_025_raw`, `exhaustion_rev`, `rg_long_fast_v`, `abs_veto_60s`.

**Two not retired** despite the review recommending them: `capit_mid` and `capit_ride` were convicted for "testing the config the roster abandoned" — the roster **re-adopted** `require_flip=True` on 08-02, so their disqualifying reason evaporated.

**Added:** `capit_live_mirror` (live capitulation lost its twin in the revert). **NIPC's control is deliberately NOT a shadow variant** — `ShadowSim._entry` dispatches on `gate` with no `nipc` branch, so it would fall through to `e=None` and sit in the slate *never firing*; NIPC is also a tick state-machine, not a bar gate. Its control is the nightly `nipc_replay.py`, whose BLANKET (regime filter off) vs HOME lines are the comparison. A test now asserts every slate gate has a dispatch branch.

---

## 4. Cost model — 12 scripts corrected

**MNQ is $1.50 per round trip** ($0.75/side). Venue truth: all 487 closed trades carry `fees_usd = 1.50`.

`nipc_replay.py` (5.0), `ofi_confirm_veto.py` ($4 blanket), and **ten** `afc_*` / `grave_donchian` / `full_opennews` scripts (`FEE, VPP = 5.0, 2.0` — note the **reversed tuple order** versus the correct `VPP, FEE = 2.0, 1.5`, which is why a casual grep misses them). Any conclusion those produced before 08-02 was computed at the wrong fee and needs re-running before it is cited.

**Why it matters unevenly:** a fixed per-trade fee is a *regressive tax on thin-edge, high-frequency* ideas. At ~$5.7 gross/trade, $5 eats 87% of the edge and $1.50 eats 26%. The same wrong constant left grind's conclusion untouched and inverted NIPC's.

---

## 5. New standing instrumentation

- **`scripts/claim_audit.py`** — every `MANUAL_CLAIM` repriced against what its slot's exit would have done. Week of 07-27: hands worth **+$655** against today's config (+$862 against the config loaded at the time), banking a median **~80%** of what the trade offered, with **5 of 12** machine counterfactuals stopping out.
- **`scripts/giveback_grid.py`** — the round-tripper decomposition behind the quiet-tape clip.
- **`gazbot7-nightly-audit.timer`** — 21:30 UTC daily, inside the CME halt. Runs both the claim audit and the NIPC control so neither is Friday archaeology again.
- **`reactivate_gates.py`** gained (then released) a `HOLD` set. Standing policy per the operator: **every gate re-arms at the midnight reopen and the router manages from there.** The nightly job is still dangerous for a never-validated gate — if one ever ships benched pending review, hold it *there*, not in a comment; nothing reads comments.
- **census `cluster()`** — `|flow| > 50` fired on **66.6%** of bars, making FLOW-LED and VACUUM two names for one coin. Replaced with a z-score against a trailing 2 hours, `|z| >= 1`: now **22.0%**.

---

## 6. Not done, deliberately

- **Front-month stop fix (`99e3c11`) NOT merged.** The leak is closed: 26 STOP_UNFILLED all-time, last at 07-28T08:02, **32 minutes before** the tape-primary guard went live, zero since. And `multislot_core.py:489` says IBKR fails to fire a resting stop *"even on the concrete Future"* — the exact mechanism the branch implements. Keep the branch for a real-money cutover, where the native stop is primary.
- **Exit-lab sequential re-run** — the paired method stacks overlapping positions the desk cannot hold ($5,076 swing on identical tape). Two live exit cells still rest on it and are flagged in `plays.json`.
- **`reprice_pending()`** full-scans all trades every 30s, unbounded.
