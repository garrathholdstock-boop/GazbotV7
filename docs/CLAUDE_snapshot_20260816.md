# CLAUDE.md — SESSION BOOTSTRAP (read first, every session)

## ★★ YOU ARE THE PERMANENT GAZBOT V7 ROUTER — this is CRITICAL INFRASTRUCTURE

As of **2026-07-30** the operator made the Claude-run router **PERMANENT** ("i want you in there ongoing. it works... this is now critical infrastructure"). Every ~5 min you read the live desk and bench/enable the 6 gates on a holistic regime judgment the mechanical ER-router misses. The desk is **GAZBOT V7** at `/home/alphabot/gazbot7` (MNQ-only, PAPER, 6-gate multi-slot tournament). You own `data/gate_switches.env`; the auto-router timer (`gazbot7-direction-router.timer`) stays **OFF**.

## ARCHITECTURE — DURABLE first (survives session exit), session = oversight

**★ The core router is now a DURABLE systemd timer** (`gazbot7-router-tick.timer`, every 5 min) that invokes headless `claude -p` via `scripts/router_tick_durable.py` — it manages the desk **even with no Claude session running**. FAIL-SAFE: any error/parse-failure → no switch change; benching-only; PAPER. This is the robustness fix; the desk is NEVER unmanaged as long as that timer is enabled.

The live SESSION (you, now) is the **oversight + fast-event layer** on top: the event-watcher `Monitor` wakes you in-chat on breaks/regime/wall-of-STOP/bleed/health so you can act between the 5-min durable ticks and step in on exceptions.

**★★2026-08-13 THE SESSION LAYER NO LONGER MATTERS.** Every standing job is a systemd timer now
(router tick, router health, desk reconcile, the five review jobs, the nightly supervisor) and the
event watcher has been a durable service since 08-11. **Do NOT arm session `CronCreate` crons** —
they would double-fire against the timers. `data/router_crons_manifest.md` is HISTORY, not a to-do
list; the prompts live in `ops/job_prompts/*.md`.

## ★★★ 2026-08-13 — **IBKR IS THE TRUTH.** READ `docs/SESSION_2026-08-13.md` BEFORE TOUCHING ANYTHING

> **Operator: "ibkr is the truth. this is something gazbot v5 got right. never rely on our books. ever."**

Said after the day-rider **sold 8 lots it did not own** and booked **$1,551 of profit that never
happened**. Our books said the day made +$835; IBKR's own executions said **−$25.50**.

**The bug in one line:** the rider's manage guard tested `entered` but not `closed`, and `net` is the
SHARED ACCOUNT NET — so when the tournament opened shorts, the rider re-entered the manage path on a
position it had already closed, re-priced a stale trail, and fired a real `MarketOrder(SELL,2)` every
minute for four minutes.

**The three rules that follow, and they are not optional:**
1. **Positions come from IBKR. A book is an annotation.** `entered`/`closed` describe INTENT, not
   reality. Any code deciding whether to place an order must reconcile against the venue first.
2. **On a netted shared account you cannot read your own position** — IBKR nets both desks into one
   number (`own_flatten_verdict()`'s docstring says exactly this). So "venue-first" means: **nobody
   may act unless venue == the sum of EVERY desk's claim.** An unaccounted lot means some book is
   lying and you do not know which. That invariant is `src/gazbot7/deskrecon.py`, enforced every 30s
   by `gazbot7-desk-reconcile.timer`, which can stop BOTH desks and never re-arms.
3. **Two books vouching for each other is not reconciliation.** `multislot_core._foreign_net()` still
   decides what is "not ours" by reading the day-rider's own state file. When that file was wrong,
   the whole chain was wrong.

**★ ALSO FIXED THE SAME DAY, all live:** the `closed` guard (+ regression test), a `CLOSED_ELSEWHERE`
branch (2 of 4 rider trades this week were **missing from the ledger entirely** and are backfilled),
`cancel_own_stops()` on all five close paths (a 600pt venue stop outlived its position by 2h — the
08-06 naked-short shape), the **inverse audit** in the reconciler ("does every STOP have a
position?"), and six `web.py` queries that had no `data_quality` filter.

**⚠ TWO TRAPS THIS DAY COST HOURS — check for them in anything you touch:**
- **Editing a file is not deploying it.** The `router_watch` NameError fix sat un-deployed for 2.5h
  while the service ran 23h-old code in memory. After editing anything a long-running service
  imports: **restart it and grep the log for the old symptom.** (`day_rider` is `oneshot` — it picks
  up code each tick. `tournament`/`shadow`/`web`/`router-watch` are long-running and do NOT.)
- **A permissions error can read as an all-clear.** `eod_flatten`'s cancel returned
  `Error 10147: not found` — IBKR saying *"not yours to cancel"* (clientId 6 vs the order's 4), not
  *"it is gone"*. It was reported as clean. Cancel from the OWNING clientId.

## ★★★ WHERE OUR DATA LIVES — **BACKBLAZE IS THE RECORD. THE LOCAL DISK IS A CACHE.**

> **Operator, 2026-08-13: "you need to look on backblaze. its all backed up there. you need to know
> this i dont need to remind you."**

Said after I surveyed the local disk, found V5's `alphabot.db` at **ZERO BYTES**, and told him there
was no V5 history. There is. **Never conclude data does not exist without checking B2.**

**★ RUN THIS AT SESSION START — it is instant (cached; the 4-hourly timer does the slow network scan):**
```
PYTHONPATH=src .venv/bin/python scripts/data_inventory.py          # cached, <1s
PYTHONPATH=src .venv/bin/python scripts/data_inventory.py --scan   # forces a live B2 listing
```
`gazbot7-data-inventory.timer` (4-hourly) pages **critical** if any source goes stale or a bucket
stops listing. Every backup job already existed; nothing was checking they still RUN — and a backup
that silently stopped looks exactly like one that works.

| where | what | notes |
|---|---|---|
| `data/gazbot7.db` | the V7 trade record, from **2026-07-16** | tiny (0.9MB); the P&L truth |
| `data/capture.db` | live tape, **5 TRADING days only** | 5.7GB. ⚠ ATTACHing this silently sees 5 days |
| `data/shadow.db` | shadow book (63 sims) | |
| `data/tape/` + `b2raw:gazbotv7/plain/` | Parquet tape, **07-16 →**, never pruned | **query via `gazbot7.lake.connect()`**, or DuckDB straight off B2 |
| `gaz:state/<ts>/` | hourly encrypted gazbot7.db + shadow.db + configs | 180 objects |
| **`gaz:v5archive/alphabot/*.parquet`** | **THE V5 ARCHIVE — 21 tables, ~440MB** | see below |
| `b2raw:AlphabotV2/monthly/` | full V5 SQLite dump, 183MB zst, 2026-05-01 | the deepest history we own |

**★★ THE V5 ARCHIVE IS A RICH, UNUSED RESEARCH SOURCE.** `gaz:v5archive` — 4,934 trades over 47
days (2026-05-23 → 07-15, net +$18,934) across 10 disciplines. Critically it contains **574 MNQ
trades (−$3,444)** and 3,012 `us_futures_daytrade` trades (+$13,485) — the same instruments we trade
now, **more than doubling our MNQ sample.** Also `fut_signal_funnel` (143MB), `fut_edge_observations`
(94MB), `fut_regime_routing`, `courtroom_verdicts`, `rejections` (6.3MB), `trade_postmortems`.
⚠ **Do NOT append V5 to the V7 green/red record** — it is 800+ symbols across crypto/ASX/TSE/HKEX and
its profit is mostly not the futures desk. Filter to `discipline='us_futures_daytrade'` or
`symbol='MNQ'` for anything comparable. Fetch: `rclone copy gaz:v5archive/alphabot/trades.parquet /tmp/v5/`

## ★★ WEEKEND 2026-08-08 → `docs/WEEKEND_2026-08-08_CHANGES.md` (read it before touching the report or the gates)

**The theme: almost everything that broke was an INSTRUMENT, not a strategy.** Four instruments
failed and no gate did. Nine claims were withdrawn; the doc leads with them.

Only the still-BINDING facts are kept here — the narrative, the withdrawn claims and the full
reasoning are in the doc:
- **NO GATE GETS AN ER FLOOR.** `deciders.ER_FLOOR` is `{}` and the deletion is pinned by
  `tests/test_deciders.py`. The old ER30 ≥ 0.35 floor on `abs_veto_short` was REFUTED three ways —
  it kept 5 of 15 winners and binned $1,363.
- **`grind_long` keeps `atr_split: 22`** while the other five non-NIPC rows take 24 (operator call).
  ⚠ FIX0's +$3,024 was measured with all six at 24, so **the shipped config is not the tested one**.
- **`grind_long` has NO `ext_hi`** — deleted, falls back to `gate_grind`'s 4.0. Do NOT pin 3.0;
  everything ≥3.0 scores identically. Live since 08-08 20:29Z and **graded on admitted legs, not P&L**.
- **`abs_veto_short` is EXEMPT from the chop bench** until its 15-fire arm-by-default review
  completes: +$2,290.50 over 159 fires / 17 days, positive in ALL FIVE regimes, and 53 of 54 filters
  tested LOSE to just letting it fire. Grade the chop bench on the non-carved-out book only.
- **`sw_grind_*` does NOT mirror live** — it keeps `ext_hi: 2.0` deliberately to hold the stop-width
  experiment's entry population constant. Never read those arms as "what live grind is doing".
- **NEVER conclude from `ceiling_pnl`.** On the identical 512 trades it said wide was ahead +$311
  while tick-repriced said behind −$364, with **3 of 6 gates flipping SIGN**.
- **Every shadow sim has a permanent number** — `scripts/sim_registry.py [--stats|--id N|--match X]`.
  Open Rider 54–57, grind k30 58–59, drift-gated Open Rider 60–63.

## ★★★ THE FRIDAY REPORT — rebuilt 2026-08-13. It had NEVER completed unattended.

Three consecutive Fridays, three different causes, zero REV2 reports without hand-finishing:
07-31 claude exited 0 after 28min having only DESCRIBED the plan · 08-07 rc=1 in 11min (the CLI began
requiring `--verbose` with stream-json) · 08-07 retry OOM-killed at 6.46GB, two manual continuations
died at 6.76 and 7.31GB, the last **four minutes before folding REV2 in**; finished BY HAND 13:55 Sat.

**★ ONE PHASE, ONE PROCESS** (`scripts/friday/serial_runner.py`). The old driver ran all 17 phases
inside ONE session so RSS only grew. A fresh `claude -p` per phase stays FLAT (~2.3GB observed), and
**the artifact on disk is the checkpoint** — a re-run resumes, it does not restart. No `Workflow` or
`Agent` in the allowlist: every sub-agent a phase cannot spawn is memory it cannot consume.
**Judge on the ARTIFACT, never the exit code** — 07-31 exited 0 having built nothing.

**★ THE TAIL IS RESERVED.** `assemble → proofread → rev2 → final` is serial, runs LAST, and is
therefore what always got lost. It now holds a **200-minute reserve** and optional sections are
dropped to protect it: you lose a greenfield cluster, never the revision.

| | |
|---|---|
| window | Fri 22:07Z → **Sat 05:15Z = 07:15 Paris** (operator needs it by 08:00; 06:30Z was 30 min LATE) |
| memory | `MemoryHigh=4.5G / MemoryMax=5.5G / MemorySwapMax=2G` **in a systemd DROP-IN, not the unit file** |
| preflight | auth checked in 20s at 22:07 and PAGES — an expired token is the 08-07 failure exactly |
| resume | `PYTHONPATH=src scripts/friday/serial_runner.py` — finished artifacts are skipped |

⚠ The old 4G+1G ceiling was **never survivable**: 5,120MB effective against a 7,310MB observed peak.
It protected the box and guaranteed the report died. 5.5G+2G = 7,680MB clears it; `MemoryHigh`
throttles into swap first so the job SLOWS instead of dying. **Revert to 3G/4G/1G if this ever runs
with the market open** — at these limits report + desk exceeds physical RAM.
⚠ Staleness is measured against the report window (most recent Friday 22:00Z). "Artifact exists" alone
is not a checkpoint — last week's files are still on disk and would publish last week twice.

**★★ THE DATA CONTRACT is in `PRE`, so all 17 phases inherit it** (`scripts/friday/friday_phases.py`):
both symbols · capture.db's 5-day window vs the lake · **$1.50/RT** · MNQ $2/pt vs **MGC $10/pt** · the
V5 archive on B2 · where MGC L2 lives. Before it, three prompts said "backtest on capture.db" (silently
5 days) and one said **"$5/round-trip"** — 3.3× the true fee, which does not look wrong, it just kills
marginal edges and reports a confident NULL.

**★★ GOLD IS THE NEW LINE OF ENQUIRY.** `run_census.py --symbol` now covers MGC (74 runs ≥1.5×ATR last
week vs MNQ's 72) and phase **`gf_MGC` runs 7th, AHEAD of the MNQ clusters** so it is not what gets cut.
Operator's brief, all four constraints pinned in the prompt: gates **INVENTED FRESH** (no porting or
re-tuning any of the six MNQ gates) · target is a **2×2 {momentum,reversion}×{long,short}** · the
**full exit matrix** (tight-R scalp, wide chandelier, dual-slot A+B, time cap) · and **assume the
router benches it** — score on its HOME regime and name the router rule, never blanket. Thin n is a
SHADOW ARM, never a kill and never a live promotion; the goal is proof over weeks in shadow.

⚠ `gazbot7-core` and `gazbot7-strategy` are `disabled` and have **NEVER started** — vestigial. The
desk is `gazbot7-tournament`. `sweep.py` reporting "restarts core: 0" for a unit that never ran is
false comfort. And the box is 7.5GB: three `global_oom` kills on 08-08, two of them the operator's own
tmux sessions. It presents as "everything keeps exiting."

## ★★ 2026-08-15 — THE SHADOW DESK WAS CUT 47 → 22, AND A THIRD DESK EXISTS (MGC)

**Operator: *"there are tons of shadow sims that lose all the time. trim the shadow desk down to the
best 20 first. kill the rest."*** Landed on **22**, deliberately — see the factorial note below.

**★ THE TRIM IS NOT A P&L SORT AND MUST NEVER BECOME ONE.** Definitions stay in source and are
filtered at `default_slate()`'s return by `RETIRED_2026_08_15`, beside the older `RETIRED` set.
Registry numbers are permanent and `shadow.db` history is untouched, so **re-arming is deleting one
line**. Eight of the 22 surviving slots hold arms that are LOSING on purpose:

| kept and losing | why it cannot be cut |
|---|---|
| `capit_loose` **−$11,292** | the NO-FLIP CONTROL — the only evidence `require_flip=True` is worth having |
| `thrust_loose` −$43/n=611 | the un-vetoed BASE the abs_veto +$2,537.50 claim rests on; **hard-coded in 3 shipped scripts** |
| `chand_k35` −$538 | **IS** the live desk exit; every exit study is measured against it |
| `thrust_short_raw` | the raw arm proving the 55s filter adds +$11.20/trade |
| `capit_live_mirror` −$2,839 | a LIVE gate's counterfactual — it is what would justify benching `capitulation_long` |

⚠ My first pass ranked all 47 on repriced P&L and put `capit_loose` top of the kill pile. The
PROTECTED list in `shadow.py` caught it. **Classify control / paired / factorial / slow-firing BEFORE
ranking, and rank only what is left** ([[a-control-is-supposed-to-lose]]).

**★ WHY 22 AND NOT 20.** I also cut the drift-GATED Open Rider pair. `test_shadow`'s own guard
refused it — *"an unpaired gated arm confounds the gate with whichever cadence or stop cell it sits
in"* — and was right: keeping `odr_c5/c10_s30` without their `_g` twins leaves a 2×2 that cannot
separate the DRIFT GATE from cadence, which is the live question. **Two slots for a working
factorial; a broken factorial is worth zero slots.** New interlock
`test_the_parametrisation_matches_the_LIVE_slate` fails if a future trim leaves armed arms unguarded.

**Retired on a REASON, never on P&L alone (25):** `grind_fast` (n=1,407 @ −$1.23) · `thrust_aligned`
(n=349, noise) · `capit_mid`/`capit_ride` (the 08-02 note kept them as valid TESTS; they reached n=40
and answered) · the whole rgv-short family **including its control**, since nothing was left to
control · `sw_grind_*` ×6 (stop width does not rescue grind — **answered**, not "it loses") ·
`sw_absL_*` ×4 (stalled at n=36-40) · the `cx_absLA`/`cx_absSB` pairs, cut together · the Open Rider
s20 axis ×4 (s30 beat it on all four paired comparisons).

### ★ THE MGC SHADOW DESK — a THIRD desk, own service + own store → `docs/MGC_SHADOW_SCOPE.md`

`gazbot7-shadow-mgc.service`, `symbol=MGC`, **$10.00/pt**, → `data/shadow_mgc.db`. Observe-only:
no account, no `gate_switches.env`, nothing the router reads. Three arms — `mgc_holebreak_fade_long`,
`mgc_holebreak_fade_short`, and `mgc_break_fade_nobook` (the no-book **CONTROL**, which is expected
to lose; without it the book cut cannot be attributed).

**Why a separate store and not a `symbol` column:** `reprice_pending` reprices every pending trade
with ONE multiplier, so two services on one store would price gold at MNQ's $2/pt intermittently — a
silent 5× race. A separate store makes it structurally impossible.

⚠ **TWO FEE CONSTANTS, NOT INTERCHANGEABLE.** `MGC_FEE_RT = 4.50` (mid-priced harnesses: $3.00
spread + $1.50 commission) · `REPRICER_FEE_RT = 1.50` (commission only — `repricer.py` already fills
at the far touch on both legs). **A round trip crosses the spread ONCE.** The old $7.50 double-counted
it, and I used that number to declare the coil bouncer DEAD; at the true cost it is **+$8.42,
breakeven** ([[mgc-session-anchor-fade-lead]]).

⚠⚠ **THE HEADLINE +$1,387 / +$1,261 IS NOT THIS SERVICE'S EXPECTATION.** The lab built its bars from
the **depth MID**; the service folds **md TRADE bars**, and only **41% of the lab's break fires exist
on production's tape at all**. Producing the trade-bar number honestly over weeks IS the service's
job — treat gold as unquantified until it has ([[the-labs-tape-is-not-productions-tape]],
`MGC_SHADOW_SCOPE.md` §8).


## ★★★ STANDING METHOD TRAPS — check for these in ANY number you are given

Discovered over the 08-01/02 weekend but they are **standing rules, not history**. Each has bitten
more than once. Full provenance in `docs/WEEKEND_2026-08-01_CHANGES.md`.

1. **MFE is not a win rate.** "X% of trades reach N R" ignores whether the STOP came first. It
   inflated capitulation's win rate 29% → 78% and shipped a losing config live. Compute the *race*.
2. **The fee is $1.50/RT on MNQ** — never $5, $2, or $1.50/side. Grep every harness's fee constant;
   note `FEE, VPP = 5.0, 2.0` and `VPP, FEE = 2.0, 1.5` look identical at a glance and are reversed.
   **★2026-08-15 GOLD HAS TWO, AND THEY ARE NOT INTERCHANGEABLE:** `MGC_FEE_RT = 4.50` for a harness
   that fills at the MID (a round trip crosses the 0.30pt spread **ONCE** = $3.00, + $1.50) and
   `REPRICER_FEE_RT = 1.50` where the harness already crossed both legs. **A COST CONSTANT REFUTES
   THINGS** — I took $7.50 from the report without checking the arithmetic, used it to declare the
   coil bouncer DEAD, and wrote that kill into three documents; it is **breakeven (+$8.42)**.
   Re-derive a cost from the MECHANISM (how many times do you cross?) before letting it kill a lead.
3. **A SLATE IS ASSEMBLED FROM HELPERS, SO THE FILE YOU EDITED MAY NOT BE THE ONE THAT RUNS.**
   The scale-out slate silently drops things — it has killed the ER/ATR floors, the ER-hold shadow,
   the regime-3 exit selector and any base `target_r`. **Verify config via `scaleout_slots()`, never
   source.** `grind_long` has TWO SlotSpecs in source; the live slate resolves to
   `slot_strategy.py:161`, so editing `:116` is a silent no-op. **★2026-08-15 the SHADOW slate is the
   same shape** — `default_slate()` composes `_open_rider()`, `_clip_ab()`, `_stop_width_ab()`, and I
   applied the trim filter to the last helper's `return` instead of `default_slate()`'s, cutting 10
   arms instead of 27. **Always assert the result** (`set(live) & set(retired) == {}`); the assertion
   caught it, reading the diff did not.
4. **A pick is not a ship, and a shadow result is not a live result.** Also: the shadow book leaks
   past its own stops on **44%** of trades (median overshoot 0.56×ATR), which gates every study
   concluding *"exit earlier"* — it does NOT gate results that exit LATER; the bias runs one way.
5. **★2026-08-13 A RIGHT NUMBER BESIDE A WRONG ONE IS WORSE THAN EITHER ALONE.** `pnl.py` filtered
   the phantom rows and six other `web.py` queries did not, so a correct header sat above a blotter
   and equity curve carrying $1,551 of trades that never happened, with nothing saying which to
   believe. When you add a flag, **audit every consumer** — that is now twice for this one field.

⚠ Desk changes from that weekend (8 gates, the quiet-tape clip, ER floors deleted, the `_base(slot)`
fix, slate cut 28→18) are in the doc. The **quiet-tape clip** is still live: ATR<22 → both lots clip
$40 / 1.75R floored $60; ATR≥22 unchanged — `docs/REGIME_EXIT_CHEATSHEET.md`.

## ON SESSION START — DO THIS

1. **Verify the durable router is alive:** `systemctl status gazbot7-router-tick.timer` (should be active/enabled; next fire ≤5 min). If it's dead/disabled → `systemctl enable --now gazbot7-router-tick.timer`. Check `tail /home/alphabot/gazbot7/data/router_headless.log` — each 5-min run logs there (no change / APPLIED / skip). This is the desk's floor; everything else is a bonus.
   **★ An active timer is NOT proof the router works.** Check `PINNED` in `scripts/router_tick_durable.py`
   too — a full-roster pin makes every tick a silent no-op that still logs "no change" (411 ticks / 36h
   went unnoticed on 07-31). If the last `APPLIED` line in the log is more than a day old on a trading
   day, suspect it.
   **★★2026-08-13 AND AN ACTIVE TIMER IS NOT PROOF IT IS DECIDING EITHER.** It no-opped 125 times
   in a row (02:40→13:00Z, **10.5 HOURS**) on an expired OAuth token while `systemctl` said active,
   the service exited `0/SUCCESS` every 5 min and `sweep.py` was clean — a parse failure logs "no
   change", and so does a quiet tape. **Read the LAST LINE of `router_headless.log` and confirm it is
   a real decision, not an `ABORT:`.** Fix is `/login` in a session (the unit is `User=root` /
   `HOME=/root`, so it picks the new token up with no restart). Now alarmed automatically by
   `gazbot7-router-health.timer` — if you see an ABORT streak and no alarm fired, the alarm is broken.
2. **Do NOT arm ANY session cron.** The durable timers own all of it now (tick, health, reconcile,
   the five review jobs, the supervisor). A session cron would double-fire — and a session 5-min tick
   would DOUBLE-WRITE `gate_switches.env` (two routers).
3. **The EVENT WATCHER is already durable** — `gazbot7-router-watch.service` (since 08-11) runs
   `router_watch_durable.py`, which wraps `router_watch.py`, texts critical health events and asks
   the tick to run early. **Do not build another one** (a duplicate was written on 08-13 before
   checking). You may *additionally* arm a session `Monitor` on the same script for in-chat
   visibility while you work; it is read-only and dies with the session.
4. **★★ SCAN THE DATA ESTATE (instant, cached):**
   `PYTHONPATH=src .venv/bin/python scripts/data_inventory.py` — local DBs + all four B2 remotes,
   with freshness. **BACKBLAZE IS THE RECORD; the local disk is a cache.** If it reports a fault or
   the cache is >6h old, run `--scan`. Never conclude a dataset does not exist without checking B2 —
   V5's `alphabot.db` is 0 bytes locally and its full history is on B2.
5. **Verify the safety layer is alive:** `systemctl is-active gazbot7-desk-reconcile.timer` and
   `tail data/desk_reconcile_state.json` — it should read `venue … = tournament … + rider …` with
   `unaccounted +0` and `0 orphan(s)`. This is the only thing on the box that reconciles ACROSS both
   desks, and the only thing that watches orders as well as positions.
6. **Read, thoroughly:**
   - `/home/alphabot/gazbot7/data/router_badcall_ledger.md` — the scored audit of past bench calls. Internalise the ❌/⚠ patterns so you don't repeat them.
   - `tail -50 /home/alphabot/gazbot7/data/router_trial_log.txt` — the recent tick-by-tick state + last switch changes.
   - Auto-memory `MEMORY.md` (already loaded) — especially [[router-tune-trial]] (permanent, mechanism), [[us-open-dont-bench-trend-rider]], [[rearm-momentum-needs-er-climb-not-delta-blip]], [[exhaustion-short-live-fader-success]].
7. **Verify desk health:** `cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json` — flat/healthy/not-halted, capture fresh, no wedge.

## THE STANDING TIMERS — ALL DURABLE (2026-08-13). No session crons. Do not re-arm any.

Every job below is systemd. Nothing here dies with a session, and adding a `CronCreate` twin would
double-fire. Prompts for the headless-Claude jobs live in `ops/job_prompts/*.md`; units in
`ops/systemd/`.

| Unit / schedule (UTC) | Purpose |
|---|---|
| `gazbot7-router-tick.timer` `*:0/5` | **★ DURABLE ROUTER tick** — the core 5-min loop, headless Claude. Owns `gate_switches.env`. |
| `gazbot7-router-health.timer` `*:02/5` | **★2026-08-13** ABORT streak / silent log / full-roster PIN / dead timer → pages critical. Built after the 10.5h OAuth outage; fires on the 3rd ABORT tick. Offset off the tick so it never races its write. |
| `gazbot7-desk-reconcile.timer` `*:*:0/30` | **★2026-08-13 THE SAFETY LAYER.** `venue == tournament + rider`, read-only on clientId 8. Confirms on two reads, then stops BOTH desks (kill file + bench all + rider off). Also the inverse audit: a working stop with no position. **Never re-arms** — `--release` is a human act. |
| `gazbot7-router-watch.service` (continuous) | event watcher → early tick + critical texts. Durable since 08-11. |
| `gazbot7-claude-job@sweep.timer` `*:41/3h Mon-Fri` | 3-hourly maintenance sweep |
| `gazbot7-claude-job@hour-watch.timer` `05..21:08 Mon-Fri` | hourly TAPE/GATE watch (TIER-2 = ATTENTION GAZ) |
| `gazbot7-claude-job@ledger-review.timer` `00,04,08,12,16,20:13` | BAD-CALL LEDGER review + grade recent switch changes |
| `gazbot7-claude-job@nightly-review.timer` `22:43 Mon-Fri` | grind-exit shadow + router/selector review, split by desk |
| `gazbot7-claude-job@sunday-ramp.timer` `Sun 20..23:09` | pre-open / reopen ramp |
| `gazbot7-nightly-supervisor.timer` `21:40` | **★2026-08-13** verify-and-repair. Checks timers actually FIRED (not merely active), the router is deciding, jobs have recent run records, and the mirror/prune interlock. Restarts only a unit that is enabled, down, **and while flat**. Deliberately NOT a reboot, and NOT at 22:00 (that is the reopen). |
| `gazbot7-data-inventory.timer` `4-hourly :37` | **★2026-08-13** local DBs + all four B2 remotes with freshness → `data/data_status.json`. Pages critical on staleness. The slow network scan lives here so a session start reads it instantly. |
| `gazbot7-friday-report.timer` `Fri 22:07` | the weekly report — serial runner, 8h cap, deadline 05:15Z. See the Friday section above. |
| `gazbot7-nightly-audit.timer` `21:30` | `claim_audit.py` + `nipc_replay.py`, inside the CME halt. **⚠2026-08-15 `nipc_replay.py` IS NOW VESTIGIAL** — the nipc gates are deleted, so it replays a gate that cannot fire (and it already had the [[nipc-replay-truncation-persists-unfixed]] bug). NOT disabled, because the same unit runs `claim_audit.py`, which is still wanted. Split or drop the nipc half when convenient. |
| `gazbot7-gate-reactivate.timer` `22:00 = 00:00 Paris` | **⚠ arms EVERY `=off` gate.** A bench in `gate_switches.env` therefore only lasts until 22:00. **★2026-08-15 `reactivate_gates.py::HOLD` IS NOW EMPTY** — by the operator's own 08-01 rule (*"every gate we have should re-enable for the midnight open. then the router manages"*). `rgv_short` was released to the router's standing guidance; the nipc gates were DELETED. So **nothing is exempt**, and this timer is the answer to "who keeps re-arming `capitulation_long`?" — the router wrote it OFF five times, this wrote it ON each night. Working as instructed, not a bug. |

## HOW THE ROUTER DECIDES (the short version — full framework in the tick prompt)

### ⛔ 2026-08-08 — RUN STATE AS A ROUTING LEVER IS **WITHDRAWN**. Do not route on it.

**The 08-06 claim below did NOT reproduce and is superseded by the Friday report of 2026-08-08
(NOT-AN-ACTION #1, `not-run-state-as-a-routing-lever-0808`).** Re-derived from scratch on the SAME 89
Mon–Thu trades, the headline cell inverts:

| in-run aligned, TAKEN | lead doc (08-06) | re-derivation (08-08) |
|---|---|---|
| | n=34 · 50% · **+$10.34/tr** | n=46 · 41% · **−$1.83/tr** |

Armed inside an aligned run the desk made **nothing** — it lost $1.83 a lot. The 34/4/51 split could not
be reproduced under **any** run-span definition tried (merge gaps 0s/120s/300s/600s/900s all give an
identical 46/10/33). The verdict: *an exit find wearing a router's coat.*

**What DOES survive, and it is not a routing lever:**
- The **missed** side reproduces — in-run aligned MISSED n=96 · 59% · +$2,703 vs chop MISSED n=194 · 26% · −$2,089.
- The real spread is between signals the router **BLOCKED** (+$27/signal aligned) and the chop it
  **TRADED** (−$19/lot) — about **$17–$46** a trade depending which pair you compare, **not** a flat $39.
- Arming more would have added ~$170 this week; benching the 84 no-run trades would have saved $584. But
  **re-pricing the EXITS on the exact same entries the desk already took — changing nothing about routing
  — turns the week from −$772 into +$1,493.** That is where the money is.

`runstate.py` still runs and is still injected. **Read it as context, not as an instruction**, and never
flip a switch on it alone. The exit application is BUILD work behind
`fix-shadow-repricer-stop-detection-0808`, not a router change.

⚠ The old text claimed "when RUN STATE and the untradeable meter disagree, RUN STATE WINS." **That rule
is withdrawn with the rest of it.** Neither instrument outranks the other on this evidence.

**★★ THE ASYMMETRY DOES NOT INVERT.** The 08-06 note said benched-inside-a-run was the expensive error;
that rested on the +$10.34 cell which is now −$1.83. **Treat the chop asymmetry below as the standing
rule in all states.**

Read `scripts/desk_view.py` + `scripts/recent_trades.py` each tick — but **form the read from the TAPE
first** (raw bars → structure/VWAP/ATR yourself, `run_detect.py`), and consult the shadow board **last,
only to confirm**: it is BACKWARD-looking and leading with it trades the regime that just ended
([[read-the-tape-first-shadow-is-confirmation]], [[go-find-the-price-yourself]]).
**★2026-08-15 `exhaustion_short` IS NOW ROUTER-MANAGED** — added to `direction_router.UP_OFF`
alongside `rgv_short`, so it benches in a PROVEN up-trend. It had been live and UNMANAGED for three
weeks as the desk's busiest gate (71 of 108 trades in the week to 08-14), of which 12 fired straight
into a confirmed TREND_UP for −$241.
Then: **confirmed chop → bench ALL momentum, keep reversion**; **UP≥+40 → bench shorts / DOWN≤−40 → bench
longs**; re-arm aligned momentum on a real break WITH ER climbing **+ vol expanding** — vol is the leg that
actually binds, and ER-climb without it decayed inside 15–35 min on four separate armings
([[vol-expansion-is-the-binding-leg]]). Judge footprint faders on LIVE P&L, not their fixed-target shadow.
Write on change → edit `gate_switches.env`, log to `router_trial_log.txt`, notify. **Benching is fully
reversible** (blocks NEW entries only; opens still exit; stops untouched) — re-arm freely when evidence
changes, but don't THRASH. Asymmetry: wrongly-benched = cheap, wrongly-armed = expensive → sit benched
one more tick. (The 08-06 "inside a run, benched is the expensive error" carve-out is **withdrawn** —
see above.)

**★★ 2026-08-08 CARVE-OUT — `abs_veto_short` is EXEMPT from the chop bench** until its 15-fire
arm-by-default review completes. It is the one gate with per-regime evidence contradicting a blanket
bench: +$2,290.50 over 159 fires / 17 days, **positive in ALL FIVE regimes** including chop, and 53 of 54
filters tested LOSE to just letting it fire. Benching it in chop costs money **and** biases the 15-fire
sample. Grade the chop bench on the non-carved-out book only.

## ★★ 2026-08-06 — THE ACCOUNT IS SHARED → `docs/INCIDENT_2026-08-06_SHARED_ACCOUNT.md`

The day-rider flattened the ACCOUNT net without checking whose position it was. Both desks trade MNQ
in **DUQ191770** and IBKR nets them into ONE number. Cascade: tournament book +2 vs a venue of 0 →
reconcile DRIFT → **11 minutes halted with the whole safety block skipped**, then a leftover GTC stop
fired with no position behind it and **opened a naked short**, booked 6h later as `nipc_short`.

**Still live from it:**
- Every flatten is ownership-gated (`safety.own_flatten_verdict`), the watchdog too.
- `desk_view`/`recent_trades` filter `data_quality IS NULL` so excluded rows cannot reach the ROUTER.
- **⚠ STILL OPEN: on `drift` the tournament skips its ENTIRE safety block** — max-hold, naked
  auditor, re-protect and stop-breach all sit behind `!= "drift"` (`multislot_core.py:610`). The
  alarm disables the fire brigade. `audit_age_s` stays GREEN throughout: the loop cycles, only the
  work inside it is skipped.
- **★2026-08-15 THE nipc GATES ARE DELETED** (operator: *"delete nipc gates theyve never done
  anytjing"*) — gone from the roster, the dashboard and the router boards. They had hit the −$400
  kill criterion (n=47, 26% win). `HOLD` is now empty; `rgv_short` lives in the router's standing
  guidance instead.

**★ The inverse-audit gap this incident named — "does every STOP have a position?" — was CLOSED on
08-13** by `desk_reconcile.orphan_stops()` (detection, 30s) and `day_rider.cancel_own_stops()` (cause).

## ~~DURABILITY CAVEAT~~ — RESOLVED 2026-08-13

The old #1 fragility ("these crons are session-bound; keep the session alive and re-arm weekly") is
**gone**. Every standing job is a systemd timer; the session is optional. See the timer table above.

**★ The NEW #1 fragility is CREDENTIAL EXPIRY**, and the operator has declined a long-lived API key
(*"ill just relogin every now and then"*), so the alarm IS the mitigation, not a backstop to one. It
presents identically to a healthy desk — timer active, service exiting 0, sweep clean, log full of
"no change" — which is why `gazbot7-router-health.timer` exists. **If it pages, run `claude` on the
box and `/login`; nothing else is needed and no restart is required.**

## ★★★ DAY RIDER — a SECOND desk (PAPER, live since 2026-08-05) → `docs/DAY_RIDER.md`

Its own service + timers, own IBKR clientId 4, **same account as the tournament**. Switch:
`data/day_rider.env` → `day_rider=on|off`. **Currently ON.**

```
DETECT  from the 13:30 UTC cash open: efficiency >=0.15 AND roundtrip >=0.45  (gazbot7/drift.py)
ENTER   2 lots, direction = sign of net. ONE entry per session. No entry after 15:00 UTC.
EXIT    ATR trail (arm 4xATR ahead, trail 2xATR off peak). HARD FLAT 20:40 UTC.
ASK     a 2xATR reversal off the peak pages the operator 3x/15min -> DEFAULT IS HOLD.
```

**The five things not to re-litigate** (all tested, numbers in the doc):
- **NOT a tournament gate** — `multislot_core.py:372` force-flattens at `max_hold_minutes=120` and
  this holds ~7h. Do NOT raise the global cap; that cap is what limited the MD_STREAM incident to −$255.50.
- **FLAT AT 20:40 UTC, NEVER 21:00** — 21:00 *is* the CME halt, so a flatten fired then has no market
  and no retry. **STANDING OPERATOR RULE: NEVER HOLD OVERNIGHT. EVER.**
- **The anchor is the CASH OPEN** — a 22:00 anchor gives ZERO detections in 33 sessions.
- **The exit is essentially exit-proof** — 25 variants tested, holding beat every one; only the armed
  trail improved on it. Don't re-run these.
- **600pt venue stop is insurance, not a trading decision** — a 400pt stop costs $3,451 and *worsens*
  the worst day.

**★★2026-08-13 — FOUR FIXES AFTER IT SOLD 8 LOTS IT DID NOT OWN** (`docs/SESSION_2026-08-13.md`).
All live and tested; **none has traded yet** — 08-14's open is their first exercise.
`closed` added to the manage guard · `venue_first_ok()` on every order path **except the 20:40 hard
flat** (refusing to flatten because the books disagree is strictly worse than the bug) ·
`CLOSED_ELSEWHERE` books-and-alarms instead of dropping the trade silently (**2 of 4 rider trades
this week never reached the ledger**) · `cancel_own_stops()` on all five close paths,
**clientId-filtered so it can never cancel the tournament's stops**.

⚠ 31 in-sample sessions after ~60 configurations. Treat the first weeks as evidence, not proof.

## ★★ DATA & BACKUP (2026-08-05) → `docs/BACKUP_AND_ARCHIVE.md` before touching retention

- **`capture.db` holds 5 TRADING days**; everything older is Parquet, local + Backblaze B2.
  **Query history via `gazbot7.lake.connect()`, NOT by ATTACHing capture.db** — most old harnesses
  ATTACH and will silently see only 5 days.
- **★ THE INTERLOCK:** `prune_capture.py` may not delete a day `tape_mirror.py` has not exported AND
  verified by row count. If the mirror stops, the prune stops and capture.db grows — growth you
  notice, a silent gap in the tape you do not.
- **Config epochs:** `scripts/config_at.py --at/--epochs/--diff`, and `--epochs --entry` for the
  entry side (added 08-08, after the journal was found recording only the exit ladder — a live
  `ATR_FLOOR` change logged `changed_from_previous: false`). Pre-08-08 rows show
  `- (not recorded)`, which is *unknown*, not *unchanged*.
- `sweep.py::check_config_committed()` WARNs on a dirty tree for the live-behaviour files. WARN not
  CRIT on purpose: a dirty tree is a bookkeeping failure, not an order-path failure.

## ★★ MD_STREAM IS MULTI-SYMBOL — every consumer MUST filter (2026-08-04 incident)

`md` publishes one bar per captured symbol on ONE stream, tagged `body["symbol"]`. Any consumer that
folds without checking the tag corrupts its features the moment a second symbol is captured. Adding MGC
made ATR read **1848 against a true 15 (122x)** and opened live trades with **$3,700 stops**. Fixed in
tournament/shadow/strategy and pinned by `tests/test_md_symbol_filter.py`.
**A config change in one file armed a latent bug in three others** — when widening what a shared stream
carries, audit every CONSUMER, not just the producer. Note every `capture.db` reader was already safe,
because SQL forces you to name the symbol; only the message bus left it optional.

## ★★ SESSION-TIME POLICY (2026-08-05)

**ASIA 00-07 UTC IS BENCHED PERMANENTLY** — `RunConfig.no_open_asia=True`, guard in
`multislot_core._open()`, window in `session.py::in_asia_block`. Shadow n=1840: **−$3.17/trade**, the
worst block on the desk. **NEW ENTRIES ONLY** — exits and every flatten path untouched. Revert:
`no_open_asia=False`. The day-rider is unaffected (13:38-20:40 only).

⚠ **"Don't day-trade MNQ until the US open" was TESTED AND REFUTED** — pre-open is −$1.75/trade vs the
US session's −$1.93. **LONDON (07-13) is the desk's ONLY positive block** (+$0.70/tr, n=1516); a
wait-for-the-US-open policy would bench the best window along with the worst.

The one time finding that survived the full battery: **13:30-14:45 is where expectancy lives**
(+$8.93/tr, n=562, strip-best-3 +$695, both halves positive, +3.27sd). The late session is NOT
reliably bad — three days carry its whole loss — so **do not bench it**.

## Other repo conventions
- V5 `alphabot2` desk is RETIRED — do NOT probe :8090/:8092/:8000 or `alphabot.db`.
- Verify desk facts LIVE (curl/query), never recall (memory [[verify-desk-facts-never-guess]]).
- Warn before restarting `alphabot-dashboard`/web (drops the operator's tab).
