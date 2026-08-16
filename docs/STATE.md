# GAZBOT V7 — STATE

> **The living snapshot: what the desk IS, right now.** Overwritten to stay current — no history by
> design. History lives in **`SESSIONS.md`**, architectural "why" in **`DECISIONS.md`**, and the
> instructions I read at session start in **`/root/CLAUDE.md`** (which is NOT a state file).
>
> **Never edit this file without a matching SESSIONS.md entry in the same breath.**
> **Re-SCAN code / systemd / health — never recall.** STATE is stale until proven fresh.
>
> **Rebuilt 2026-08-16** by scanning the running system. The previous STATE.md lived in the RETIRED
> V5 tree (`/home/alphabot/alphabot2/docs/`), stopped on **2026-07-30**, and described a different
> desk: one desk instead of three, 8 services instead of 36, `capture.db` at 1.9GB instead of 5.3GB.
>
> **Mode: PAPER** (IBKR account DUQ191770, `place_live=False`). Real money is a ladder rung, not the
> destination.

---

## 1. THE THREE DESKS — all PAPER, all sharing ONE netted IBKR account

| desk | unit | what it does | switch |
|---|---|---|---|
| **Tournament** | `gazbot7-tournament` (clientId 0) | the main book — 6 gates, multi-slot, dual-lot scale-out | `data/gate_switches.env` |
| **Day Rider** | `gazbot7-day-rider.timer` (clientId 4) | ONE trade/day off the 13:30 cash open, ATR trail, hard flat 20:40Z | `data/day_rider.env` → **`day_rider=on`** |
| **MGC Shadow** | `gazbot7-shadow-mgc` | gold, observe-only, own store `shadow_mgc.db` | n/a — touches nothing |

⚠ **THE ACCOUNT IS SHARED AND IBKR NETS BOTH DESKS INTO ONE NUMBER.** You cannot read your own
position from the venue. Nobody may act unless `venue == tournament + rider`. That invariant is
`deskrecon.py`, enforced every 30s — see §5.

★ **IBKR IS THE TRUTH.** Operator, 2026-08-13: *"never rely on our books. ever."* `entered`/`closed`
describe INTENT, not reality.

---

## 2. GATES — 6 live, 3 long / 3 short

Current `gate_switches.env` (⚠ router-owned, changes every 5 min — re-read it, never quote this):

    grind_long=off   capitulation_long=on   abs_veto_long=off
    rgv_short=off    exhaustion_short=on    abs_veto_short=on

- **`ER_FLOOR` is `{}`** — no gate has an ER floor. The deletion is pinned by `tests/test_deciders.py`.
- **`ATR_FLOOR`** = `grind_long: 22.0`, `capitulation_long: 10.0`. `ER_CEIL` is `{}`.
- **ASIA (00–07 UTC) IS BENCHED PERMANENTLY** — `no_open_asia=True`. NEW ENTRIES ONLY; every exit and
  flatten path is untouched. Shadow n=1840 at −$3.17/trade, the worst block on the desk.
- **`max_hold_minutes=120`** — the global force-flatten. Do NOT raise it; it is what limited the
  MD_STREAM incident to −$255.50.
- **nipc gates: DELETED** 2026-08-15 (operator: *"theyve never done anytjing"*).
- **`exhaustion_short` is router-managed** since 2026-08-15 (`direction_router.UP_OFF`).

## 3. EXITS — every gate is a dual-lot scale-out on ONE signal

    grind_long          A scalp 2.5R   B chandelier_lock 2.0
    capitulation_long   A scalp 1.5R   B chandelier 2.0
    abs_veto_long       A scalp 1.0R   B scalp 1.5R
    rgv_short           A scalp 1.5R   B chandelier 2.0
    exhaustion_short    A scalp 0.75R  B chandelier 2.0
    abs_veto_short      A scalp 1.5R   B scalp 2.5R

All `stop_atr_mult=1.0`, `atr_split=22.0`. **Verify via `scaleout_slots()`, NEVER source** — the
slate silently drops things and `grind_long` has two SlotSpecs in source.
**Quiet-tape clip is LIVE**: ATR<22 → both lots clip $40 / 1.75R floored $60.

## 4. SHADOW — 22 MNQ arms + 3 MGC (trimmed from 47 on 2026-08-15)

Judged on tick-repriced `real_pnl`, **never** `ceiling_pnl` (they have disagreed in SIGN on the same
512 trades). Retired arms are filtered at `default_slate()`'s return by `RETIRED_2026_08_15`;
definitions stay in source and registry numbers are permanent, so **re-arming is deleting one line**.

⚠ **EIGHT OF THE 22 ARE LOSING ON PURPOSE.** `capit_loose` (−$11,292) is the no-flip CONTROL;
`thrust_loose` is the un-vetoed BASE the abs_veto +$2,537.50 claim rests on and is hard-coded in
three shipped scripts; `chand_k35` IS the live exit. **Never rank controls, A/B halves, factorial
cells or slow-firing arms on their own P&L.**

MGC: `mgc_holebreak_fade_long/short` + `mgc_break_fade_nobook` (the control). ⚠ Its headline
+$1,387/+$1,261 are **depth-mid** numbers; the service folds **trade bars** and only 41% of the lab's
fires exist there — see `MGC_SHADOW_SCOPE.md` §8.

## 5. SAFETY — non-negotiable

| layer | what it guarantees |
|---|---|
| `deskrecon.py` / `gazbot7-desk-reconcile.timer` (30s) | `venue == tournament + rider`. Confirms on two reads, then stops BOTH desks. **Never re-arms** — `--release` is a human act. Also the inverse audit: a working STOP with no position. |
| `safety.own_flatten_verdict()` | every flatten is ownership-gated — the fix for the 08-06 shared-account cascade |
| `day_rider.cancel_own_stops()` | on all five close paths, clientId-filtered so it can never cancel the tournament's stops |
| `venue_first_ok()` | on every rider order path **except** the 20:40 hard flat (refusing to flatten because books disagree is worse than the bug) |
| native venue stop | 600pt on the rider = insurance, not a trading decision |

⚠ **STILL OPEN:** on `drift` the tournament skips its ENTIRE safety block (`multislot_core.py:610`) —
max-hold, naked auditor, re-protect and stop-breach all sit behind `!= "drift"`. The alarm disables
the fire brigade. `audit_age_s` stays GREEN throughout.

**STANDING OPERATOR RULE: NEVER HOLD OVERNIGHT. EVER.** Rider flat at **20:40 UTC, never 21:00** —
21:00 *is* the CME halt, so a flatten fired then has no market and no retry.

## 6. DATA

| where | what | note |
|---|---|---|
| `data/gazbot7.db` | 932K | the trade record from 2026-07-16 — the P&L truth |
| `data/capture.db` | **5.3G** | live tape, **5 TRADING days only**. ⚠ ATTACHing it silently sees 5 days |
| `data/depth.db` | **2.8G** | L2, 10 levels @250ms, MNQ+MGC. **Gold's book is ONLY here** — `capture.db.book` has no MGC |
| `data/shadow.db` / `shadow_mgc.db` | 6.2M / 100K | the two shadow books |
| `data/tape/` + `b2raw:gazbotv7/plain/` | Parquet, 07-16 → | **query via `gazbot7.lake.connect()`** |
| `gaz:v5archive/` | 4,934 trades / 21 tables | the V5 archive — 574 MNQ trades, largely unexamined |

★ **BACKBLAZE IS THE RECORD; the local disk is a CACHE.** Never conclude data does not exist without
checking B2 — V5's `alphabot.db` is **0 bytes locally** and its full history is on B2.
★ **THE INTERLOCK:** `prune_capture.py` may not delete a day `tape_mirror.py` has not exported AND
verified by row count.

## 7. REVERT SWITCHES

| to undo | do |
|---|---|
| any bench | edit `data/gate_switches.env` — blocks NEW entries only; opens still exit |
| the day rider | `data/day_rider.env` → `day_rider=off` |
| the Asia block | `RunConfig.no_open_asia=False` |
| the shadow trim | delete the name from `RETIRED_2026_08_15` |
| the MGC desk | `systemctl disable --now gazbot7-shadow-mgc` |
| the durable router | `systemctl disable --now gazbot7-router-tick.timer` |
| a stopped desk after a reconcile halt | `deskrecon.py --release` (**human only**) |

## 8. KNOWN-OPEN / PARKED

1. **The `drift` safety-block skip** (§5) — the oldest open item, from 08-06.
2. **MGC bar-source divergence** — production's forward number is unknown until the shadow accrues.
3. **`nipc_replay.py` runs nightly against a deleted gate** — not disabled because the same unit runs
   `claim_audit.py`. Split it.
4. **`gazbot7-open-hour-watch.timer` fires EVERY MINUTE** 07–13 and 14–19 Mon–Fri (~700/day). Verify
   that is intended.
5. **The Friday report has never completed fully unattended** — 4 Fridays. 08-16 fixes should make
   the 08-21 run the first; judge on the ARTIFACT, never the exit code.
6. **Credential expiry is the #1 fragility** — the operator declined a long-lived key, so
   `gazbot7-router-health.timer` IS the mitigation. If it pages: run `claude` on the box, `/login`.
