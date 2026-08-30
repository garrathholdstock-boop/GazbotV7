# GAZBOT V7 — STATE

> **The living snapshot: what the desk IS, right now.** Overwritten to stay current — no history by
> design. History lives in **`SESSIONS.md`**, architectural "why" in **`DECISIONS.md`**, and the
> instructions I read at session start in **`/root/CLAUDE.md`** (which is NOT a state file).
>
> **Never edit this file without a matching SESSIONS.md entry in the same breath.**
> **Re-SCAN code / systemd / health — never recall.** STATE is stale until proven fresh.
>
> **Re-scanned 2026-08-30.** The tournament stand-down is LIFTED; the Friday report's structural
> faults were audited and four of them fixed. See SESSIONS §374-§377.
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
| **Tournament** | `gazbot7-tournament` (clientId 0) | ✅ **LIVE AGAIN 2026-08-26** — the 08-20 stand-down is LIFTED. The router holds full ARM and BENCH authority over all 6 gates and applies the regime rules. `HOLD = {rgv_short}` only. **NO GATE HAS SPECIAL STATUS** | `data/gate_switches.env` |
| **Day Rider** | `gazbot7-day-rider.timer` (clientId 4) | ONE automatic trade/day off the 13:30 cash open (entries stop 15:00Z), **4 lots, ladder $100/$200/$400/$600 = 50/100/200/300pt**, **NO STOP**, hard flat 20:40Z. ★ **MANUAL BUY/SELL is live across the WHOLE CME session** and bypasses the drift confirmation, the entry window and the once-per-session latch — but NOT `venue_first_ok()`, the booking path or the 20:40 flat. ⏳ `GAZBOT7_RIDER_CONFIRM_PERSIST=5` (drop-in): drift must hold the SAME direction for 5 consecutive ticks before an AUTOMATIC entry — operator experiment, not a measured edge | `data/day_rider.env` → **`day_rider=on`** |
| **MGC Shadow** | `gazbot7-shadow-mgc` | gold, observe-only, own store `shadow_mgc.db` | n/a — touches nothing |

⚠ **THE ACCOUNT IS SHARED AND IBKR NETS BOTH DESKS INTO ONE NUMBER.** You cannot read your own
position from the venue. Nobody may act unless `venue == tournament + rider`. That invariant is
`deskrecon.py`, enforced every 30s — see §5.

★ **IBKR IS THE TRUTH.** Operator, 2026-08-13: *"never rely on our books. ever."* `entered`/`closed`
describe INTENT, not reality.

---

## 1b. THE OPERATOR'S LOOP — the manual claim is the desk's best exit

**This is not a footnote. It is where the money came from.** 2026-08-19 booked **+$726 in 23 minutes
and all three exits were `MANUAL_CLAIM`** (rider +$544, abs_veto_short_B +$94, abs_veto_short_A +$88).
Across the rider's live history roughly half the trades are manual claims and they are the largest
winners, while eleven months of testing says every FIXED automated exit loses. Three studies on
2026-08-18 tried to reproduce the claims with a level — $100 to $600, ATR-scaled, two-lot — and all
of them lose. **He is not claiming at a dollar figure; he is reading an impulse exhausting.** The
desk's job is therefore to give him PRESENCE and INFORMATION, not to replace the judgement.

| piece | unit / file | what it gives him |
|---|---|---|
| **peak watch** | `gazbot7-rider-peak-watch.service` | 1 Hz open P&L off `MD_STREAM` `tape`. URGENT at **+$200**, ping per **$50** new high, **give-back** $75 off the peak, **stall** at 3 min with no new high. Every message carries extension in ATR. ⚠ READ-ONLY — no order path, asserted by test |
| **claim fast path** | `gazbot7-day-rider-claim.path` | the Claim button reaches the rider on the inotify write (**measured 0.02s**) instead of waiting for the `*:*:05` tick — which was **up to 60 SECONDS**. On 08-19 the tracked peak was 29458.75 and the claim filled 29470.75: 12pt = $48 |
| **the profit ladder** | `day_rider.TARGET_USD_PER_LOT` | ★2026-08-20 **4 lots, each banking its own figure: $100 / $200 / $400 / $600 = $1,300** if all four fill (50/100/200/300pt at $2/pt per lot). Reach rates over 231 sessions: **77.5% / 58.0% / 29.4% / ~15%**, so ~$300 is the common case and lots 3-4 are HIS to work |
| **five claim buttons** | `L1 L2 L3 L4` + `ALL` | one per lot plus flatten-all. ★ They are **ALSO KILL BUTTONS** — there is no stop, so they fire in profit or loss and the confirm dialog says so. The endpoint does not check P&L and must not. `ALL` is unchanged and remains the kill switch |
| **NO STOP** | `day_rider.PLACE_VENUE_STOP=False` | ⚠ **The 20:40Z hard flat is now the ONLY automatic protection.** Operator: *"i dont want any stop. leave them all naked."* Backed by the desk's own research — the stop *"costs $3,451 of expectancy AND has a WORSE worst-day (−$1,603) than running naked (−$1,531)"*. **EXPOSURE:** median worst-adverse day 160pt = **−$1,284**; worst of 231 sessions 1,084pt = **−$8,672** |
| **watch band** | `day_rider.WATCH_RT` | the entry notification says `rt 0.48 → WATCH — favourable band`, so he knows at 13:30 whether today is one of the ~26% the tape has historically paid |

⚠ **`PathModified`, NEVER `PathExists`.** `claim_requested()` documents an orphaned flag surviving up
to `CLAIM_MAX_AGE_S` = **15 minutes**; level-triggering would restart the rider in a tight loop for
that whole window against the shared gateway. Observed live: after a trigger with the rider closed,
the flag was still on disk.

⚠ **The 60s tick remains the FLOOR.** The path unit is a fast lane over a working road. If it is dead
the claim is picked up on the next tick exactly as before, and nothing in the trading path moved —
the web process still never places an order (2026-08-06: a button that reached the broker directly
halted the desk for 11 minutes).

★ **He watches only the first ~90 minutes after the open** — *"then it usually calms down"* — which
is already what `ENTRY_CUTOFF_MIN` encodes (13:30Z cash open → 15:00Z).

---

## 2. GATES — 6 live, 3 long / 3 short

⛔ **2026-08-20 — ALL SIX GATES ARE OFF AND THE TOURNAMENT TRADES NOTHING.** Operator: *"the only
thing that trades is day rider … turn all other gates off."*

    grind_long=off   capitulation_long=off   abs_veto_long=off
    rgv_short=off    exhaustion_short=off    abs_veto_short=off

Held off by TWO mechanisms, because one is not enough: `reactivate_gates.HOLD` covers the **whole
roster** (so the 22:00Z Paris-midnight reopen arms nothing) and `router_tick_durable.
TOURNAMENT_STOOD_DOWN` drops any change to `on`. The router keeps **full bench authority** — it can
still bench, it simply cannot arm. ⚠ NOT done with `PINNED`: a full-roster pin makes `valid`
permanently empty, which is the silent no-op that ran 411 ticks unnoticed, and it trips the PIN
ALARM every tick. **Revert:** `TOURNAMENT_STOOD_DOWN=False` + `HOLD=frozenset({"rgv_short"})`.

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

## 4. SHADOW — **34 MNQ arms** (`default_slate()`) + **3 MGC** on a SEPARATE desk (`mgc_slate()`)

★ **TWO SLATES, TWO DESKS, ZERO OVERLAP — do not add them up.** `default_slate()` returns **34, ALL
MNQ, no MGC**; the gold arms are `mgc_slate()`, run by `gazbot7-shadow-mgc` into its own
`shadow_mgc.db` (§1). **Counted by CALLING both, 2026-08-16** — this line previously read "22 MNQ +
3 MGC", which merged two slates and was stale the day it was written: 47 was trimmed to 22 on 08-15,
then the 08-16 BUILD commits (`c9c233a`, `d8ffcde` — #10/#13/#14/#15/#16/#17/#18) armed 9+ more.
**Re-count with `default_slate()`, never from this line.**

Judged on tick-repriced `real_pnl`, **never** `ceiling_pnl` (they have disagreed in SIGN on the same
512 trades). Retired arms are filtered at `default_slate()`'s return by `RETIRED_2026_08_15`;
definitions stay in source and registry numbers are permanent, so **re-arming is deleting one line**.

⚠ **MOST OF THIS SLATE CANNOT BE RANKED ON ITS OWN P&L.** At least **nine** arms are controls or
live-mirror baselines: `capit_loose` (−$11,292, the no-flip CONTROL); `thrust_loose` (the un-vetoed
BASE the abs_veto +$2,537.50 claim rests on, hard-coded in three shipped scripts); `chand_k35` (IS
the live exit); `bank20_grindA_ctl`; `capit_live_mirror`; `capit_flip_live`; `cx_grindA_live`;
`cx_clip_brk_live`; `rung_grindA_med_live`. Most of the remainder are A/B halves or factorial cells —
`abs_veto_{50,55,60}s`, `sw_absS_{A,B}_k{10,20}`, `lad_absS_{A,B}`, the four PAIRED `odr_*`,
`thrust_short_{raw,absveto55}`, `cx_clip_brk_standdown`, `rung_grind{A_med_05,B_med_10}`.
**CLASSIFY control / A-B half / factorial cell / slow-firing BEFORE ranking anything.**
⚠ The old "EIGHT of the 22" was a pre-08-16-builds count and has **NOT** been re-derived. The list
above is a verified FLOOR, not a census — a P&L sort once put the control top of a kill pile.

MGC (`mgc_slate()`, n=3): `mgc_holebreak_fade_long/short` + `mgc_break_fade_nobook` (the control).
⚠ Its headline +$1,387/+$1,261 are **depth-mid** numbers; the service folds **trade bars** and only
41% of the lab's fires exist there — see `MGC_SHADOW_SCOPE.md` §8.

## 4b. WEEKENDS ARE OFF (2026-08-30)

`gazbot7-gate-reactivate` runs 00:00 Europe/Paris **every day** = 22:00Z, and on Friday that is one
hour AFTER the CME halt — so it used to arm gates into a shut venue. It now consults
`session.is_open()`, which draws the line exactly right (Fri 22:00Z and Sat 22:00Z are False; Sun
22:00Z is True because that instant IS the reopen), and **DISARMS** instead of arming while the
venue is shut. One timer, no second definition of "the weekend" to drift.

---

## 5. SAFETY — non-negotiable

| layer | what it guarantees |
|---|---|
| `deskrecon.py` / `gazbot7-desk-reconcile.timer` (30s) | `venue == tournament + rider`. Confirms on two reads, then stops BOTH desks. **Never re-arms** — `--release` is a human act. Also the inverse audit: a working STOP with no position. |
| `safety.own_flatten_verdict()` | every flatten is ownership-gated — the fix for the 08-06 shared-account cascade |
| `day_rider.cancel_own_stops()` | on all five close paths, clientId-filtered so it can never cancel the tournament's stops |
| `venue_first_ok()` | on every rider order path **except** the 20:40 hard flat (refusing to flatten because books disagree is worse than the bug) |
| ⛔ **NO rider stop** | **2026-08-20: `PLACE_VENUE_STOP=False`.** The 20:40Z hard flat is the ONLY automatic protection on the rider. Exposure: median worst-adverse day −$1,284, worst of 231 sessions −$8,672 |
| **alarm chain** | ★2026-08-20 moved INTO gazbot7 (`scripts/notify_operator.py`, stdlib-only, `data/.notify_env` 600). It used to run the RETIRED `alphabot2` tree — deleting that tree would have silenced every page while `notify()` returned True. Legacy path kept as fallback |
| ⚠ **kill-switches NOT enforced** | `max_daily_loss_usd` / `loss_streak_halt` live only in `core.py`, which has **never started**. `multislot_core` has zero references. `sweep` now says so out loud instead of printing "headroom OK". Both are 0 and the desk is PAPER — do not set one and believe it |
| **cross-desk kill survives the reopen** | ★2026-08-20 `reactivate_gates` refuses while `desk_kill.json` is active, and FAILS CLOSED if it is unreadable. Previously the kill expired for the tournament at 22:00Z while the rider stayed frozen |
| **watchdog blindness pages** | ★2026-08-20 the rider watchdog logged SKIP and exited 0 — 450 blind cycles, longest run 117 consecutive (3h54m) through the hard-flat window, nothing paged. Now pages at 5/30/120 |

⛔ **BY DECISION, NOT BY OMISSION (2026-08-16, DECISIONS §362):** on `drift` the tournament skips its
ENTIRE safety block — max-hold, naked auditor, re-protect, stop-breach and the exit watchdog. The
operator was asked directly and said **"no. dont act under drift. leave it."** Acting on a position
whose ownership is unknown, on a shared netted account, IS the 08-06 cascade.
**What changed on 08-16 is that it is no longer SILENT:** `safety_skipped_cycles` is published in
`core_health.json`, the desk alarms at cycles 1/12/60 naming each inactive protection, and `sweep`
CRITs while holding. `audit_age_s` only ever said the loop was turning — it read GREEN through the
whole 08-06 incident. **Do not "fix" the skip; a test fails if an order path appears in that branch.**

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

## 7b. THE FRIDAY REPORT — audited 2026-08-30, four structural faults closed

It had **never once finished unattended**. An audit (sonnet) found the cause was not any single
incident but four things that made success impossible or invisible:

| fault | why it never finished | fixed |
|---|---|---|
| the whole 08-29/30 fix set was **uncommitted** — last commit to `serial_runner.py` was 08-19 | a checkout or rebuild silently reverts every fix | committed + pushed (`0eed176`, `22ef7e6`) |
| `friday_report_durable.py` hardcoded `--deadline 05:15`, **overriding** the widened `05:55` | the extra 40m never took effect on the only path that runs weekly | argument removed; `serial_runner` owns its schedule |
| `TimeoutStartSec=28800` sized for a 22:07 start, timer moved to 21:05 | systemd SIGKILL at **05:05Z — 50 min INSIDE the 05:55 deadline**, no logging, no alert | `32400` → kill 06:05Z, 10m margin |
| **`final` has never succeeded** in any run on record — and it owned the operator's only "report ready" Telegram | the ping was the last line of a prompt that never reached its end, so he has never been told a report was ready | scope cut (reads `proofread.json`, spot-checks, 60m); **ping now fires deterministically from `serial_runner`, on failure too** |

**Schedule, as it now runs:** timer **21:05Z** (the halt is 21:00) → internal deadline **05:55Z** →
systemd kill 06:05Z. Body budget **305m**, tail reserve 225m.
**The body is a dependency-aware ROLLING POOL** (`--workers 4`), not waves: a phase starts the
instant a worker frees and gets its FULL declared timeout provided the phases queued behind it can
each still clear `MIN_SLICE`. Waves were a barrier that capped a 240m section at 76m while a 30m
section idled its worker. Capacity is now **4 × 305 = 1,220 agent-min against ~975m declared — it
fits**, and PREFLIGHT reports that ratio instead of the "5.9× over" it printed weekly while nothing
acted on it.
**Phases run in their own process group** and a timeout kills the GROUP — an orphaned 4.4GB
grandchild on 08-29 filled swap, drove memory pressure to 93% and most plausibly starved three
phases into producing nothing.

⚠ **STILL OPEN — audit item 9, the operator's call.** Even fixed, 13 deep-research phases plus a
4-stage serial tail may not be a reliable one-night job. The alternative is a two-night split
(Friday = body, Saturday morning = tail on a market-closed budget), which costs the 08:00 Paris
delivery. **Decision deferred until one clean Friday has run and been measured** — the 975m is
*declared* time, and declared timeouts on this desk have historically been aspirational.

---

## 8. KNOWN-OPEN / PARKED

1. ~~The `drift` safety-block skip~~ — **CLOSED 08-16.** Made visible and alarmed; acting under
   drift was put to the operator and **declined** (§5, DECISIONS §362). Not an open item.
2. **MGC bar-source divergence** — production's forward number is unknown until the shadow accrues.
3. **`nipc_replay.py` runs nightly against a deleted gate** — not disabled because the same unit runs
   `claim_audit.py`. Split it.
4. **`gazbot7-open-hour-watch.timer` fires EVERY MINUTE** 07–13 and 14–19 Mon–Fri (~700/day). Verify
   that is intended.
5. **The Friday report has never completed fully unattended** — 4 Fridays. 08-16 fixes should make
   the 08-21 run the first; judge on the ARTIFACT, never the exit code.
6. **`roundtrip < 0.50` is UNARMED and accruing no forward evidence.** The one finding that survived
   both halves of the 231-session study (+$69/day, PF 1.80, walk-forward both directions) is
   reporting-only in the entry notification. It works only with a claim+stop, never the live trail,
   and P>=0.22 once charged for the full 10-feature search. Recommended next step: shadow it.
   First out-of-sample instance 2026-08-19 (rt 0.48, +$544) — n=1.
7. **The web endpoint's claim message was corrected but `gazbot7-web` is NOT restarted** — it still
   serves "up to ~60s" until someone restarts it. ⚠ Warn the operator first; it drops his tab.
8. **Credential expiry is the #1 fragility** — the operator declined a long-lived key, so
   `gazbot7-router-health.timer` IS the mitigation. If it pages: run `claude` on the box, `/login`.
