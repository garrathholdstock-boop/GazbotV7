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

## ★★★ WEEKEND OF 2026-08-08 — READ `docs/WEEKEND_2026-08-08_CHANGES.md` BEFORE TOUCHING ANYTHING

**The theme of this weekend: almost everything that broke was an INSTRUMENT, not a strategy.** Four
instruments failed and no gate did — a journal recording half the config, a sweep never reading the flag
it was writing, a shadow board whose ceiling disagreed in SIGN with its own repricer, and a report that
argued for things its own proofread had refuted. Nine claims were withdrawn; the doc leads with them.

**The report is published and complete:** `weekly_2026-08-08.html` / `.pdf` (287pp) + the Monday
playbook, all served at `/static/` and top of `/api/reports`. It carries a **Part 3** (six REV2
sections) that the first build did not — the build was OOM-killed four minutes before folding them in,
so the 10:17 file argued for things its own proofread had already refuted.

**★ Three things the report overturned that this file used to assert.** All are corrected in place
below; do not act on the old versions:
1. **RUN STATE as a routing lever — WITHDRAWN** (see the router section). The +$10.34/tr cell inverts to
   −$1.83/tr on re-derivation.
2. **The ER30 ≥ 0.35 floor on `abs_veto_short` — REFUTED** by two independent derivations plus a third
   corroboration. It keeps 5 of 15 winners and bins $1,363 of profit. **No gate gets an ER floor**;
   `deciders.ER_FLOOR` is `{}` and the deletion is pinned by `tests/test_deciders.py`.
3. **`grind_long`'s `ext_hi` — DELETE it, do not pin 3.0.** Everything ≥3.0 scores identically.

**★ The card is ordered by EXECUTION LOGIC, not headline size** — `reports/friday_v7/plays.json`,
52 plays. Every play now carries **`status` / `shipped_ts` / `outcome`** (the play ledger) plus
`operator_pick` / `picked_ts`. **A pick is not a ship**: `status` stays `PROPOSED` until the change is
actually applied, and whoever applies it sets `status` + `shipped_ts` at that moment. This exists because
nothing graded last week's card and the audit took hours of archaeology.

**★ Operator calls of 08-08, already folded in — do not re-litigate:**
- **`grind_long` is EXEMPT from the `atr_split` 22→24 move** (SATURDAY #10). It keeps `atr_split: 22`;
  the other five non-NIPC rows take 24. Reason: SATURDAY #2 sets grind's entry floor to 22 and Q1 relied
  on the clip being *inert* at that floor; **19.3% of grind-eligible time sits in the 22–24 band**, and
  the clip caps Lot B at 1.75R/$60 — which truncates the 21 runner events that ARE grind's whole case.
  ⚠ FIX0's +$3,024 was measured with all six rows at 24, so **the shipped config is not the tested
  config** and the direction is unmeasured. Re-run the archive before quoting that number.
- **Router timing (WINDOW 45 / HOLD 3 / STEP 5) is DEFERRED one week**, not rejected. It confounds with
  the chop off-switch by the report's own admission — *"a stickier router is a chop optimisation."*
- **`abs_veto_short` carve-out from the chop bench** (see the router section).

**★ Cross-references on the card are ID-ANCHORED and the build ENFORCES it.** Plays used to point at each
other by position ("see MONDAY #4"); the re-rank rotted five of those silently. Every reference now
carries the target's id, `friday_v7_build.py::check_xrefs()` asserts each one resolves to the stated
window and rank, and **the build refuses to run if one does not**.

**★ SHIPPED 2026-08-08 (both on branch `refactor/three-service`):**
- **SATURDAY #2 `grind-long-revert-atr22-ext30-0808`** — live since **20:29:33Z**. `ATR_FLOOR["grind_long"]`
  10→22 and grind's `ext_hi` **deleted** (falls back to `gate_grind`'s 4.0 — *do not pin 3.0*). Verified
  at the resolved layer: `scaleout_slots()` shows `ext_hi` gone, and the floor is genuinely WIRED because
  `tournament.py:156` calls `atr_blocks(_base(slot), atr)` — the raw suffixed tag `grind_long_A` does
  **not** block, which was the 07-29 dead-floor bug. ⚠ NOT YET GRADED: first tradeable tape is the Sunday
  22:00Z reopen. Review on **20 admitted legs** and on whether 4R events appear near the expected 12.7%
  rate — **NOT on P&L**, and not on a fortnight without expansion days.
- **SATURDAY #7 `commit-the-working-tree-0808`** — the tree is clean at `43f1cd4`. Four commits:
  live desk behaviour, tooling, the report, the day-rider holdings fix.
- **BUILD #2 `open-rider-to-shadow-0808`** — THE OPEN RIDER is in the shadow slate as a **2×2**:
  `odr_c5_s20` / `odr_c5_s30` / `odr_c10_s20` / `odr_c10_s30` (cadence 5 vs 10 min × stop 2.0 vs
  3.0 ×ATR). **Shadow only and not eligible for live** — promotion needs all four of: +0.15R over
  200 shadow trades *including a non-trending open week*, the 14:45Z cut, a real 2×ATR live stop
  path, and day-rider position isolation.
  ★ It needed a new gate kind — **`clock_rider`, the first shadow variant with no signal at all**
  (the clock is the trigger; direction = raw sign of the 15-min move, no deadband) — plus the
  shadow's **first time-based exit** (`TIME_CAP`, 45 min). Every other variant runs to a stop,
  target or chandelier. The tick repricer needed no change: its quote window ends at the sim's
  `exit_ts`, so a capped trade races stop-vs-target on honest ticks over exactly 45 minutes.
  ★ Why 2×2 rather than one arm — and the reason is now stronger than the one first given.
  **⚠ THE BACKTEST CANNOT RANK THESE CELLS.** Per-trade SD is ~$160, so on the 5 unseen days the SE
  on a cadence difference is **$39.78 against a $24.86 gap — t = +0.63**. The earlier claim that
  "cadence 10 beats 5 on the unseen days better than 2:1" does **not** survive its own error bars;
  every rank in that column is noise. And the marginals do **not compose**: cad10 × stop3.0 is the
  best all-days cell (+$82.88/tr) but only +$43.64 unseen, *below* cad10 × stop2.0. **The four
  shadow arms ARE the joint grid, run forward, precisely because the backtest cannot choose.**
  ★ Two things that WERE checked and held: 3.0×ATR is a real stop, not a clock exit (**34.5%** of
  its trades stop out vs 62.9% at 1.0×), and it is not directional drift (LONG +$1,475 / SHORT
  +$2,695, both positive). ⚠ 17 days contain no FOMC/CPI gap — the tail a 3×ATR stop is exposed to.
- **BUILD #3 `wide-stops-open-window-shadow-0808`** — the live-gate half is **REFUTED**. Wide stops do
  NOT transfer: in the open window the house 1.0× and 2.0× are a dead heat (+$30.76 vs +$30.41/tr,
  delta −$104, stable through strip-best-3, two days each way). **It splits by GATE, not by window** —
  grind prefers wide on both lots, `abs_veto` prefers tight in all four cells. Roster-wide stop
  widening is refuted twice over now. Third rung `sw_grind_A_k30`/`sw_grind_B_k30` added on grind ONLY.
  ★★ And **the ceiling lied**: on the identical 512 trades `ceiling_pnl` says wide is ahead +$311 while
  tick-repriced says behind −$364, **3 of 6 gates flipping sign**. Never conclude from `ceiling_pnl`.
- ⚠ `sw_grind_*` **no longer mirrors live** — it deliberately keeps `ext_hi: 2.0` so the stop-width
  experiment holds its entry population constant. Do not read those arms as "what live grind is doing".

**★ ALL SHADOW SIMS ARE NUMBERED** — 59 of them, allocated once and never reissued, so one can be named
in a word: `PYTHONPATH=src .venv/bin/python scripts/sim_registry.py [--stats|--id N|--match frag]`.
The Open Rider arms are **54–57**, the grind k30 rungs **58–59**.

## ★★ 2026-08-08 — THE BOX IS 7.5GB AND THE REPORT BUILD WILL OOM IT

Three `global_oom` kills in 12h, each a headless `claude` past 6.5GB: the report service at 04:46
(6.46GB), then two of the operator's own tmux sessions at 07:39 (6.76GB) and 11:19 (7.31GB). It presents
as "everything keeps exiting." Now guarded:
- `gazbot7-friday-report.service` → `MemoryHigh=3G` / `MemoryMax=4G` / `MemorySwapMax=1G`, so the cgroup
  OOMs **itself** instead of triggering a global OOM that picks a victim at random.
- `OOMScoreAdjust=-500` on core / tournament / md / strategy / day-rider / day-rider-watchdog, applied
  live via `/proc/<pid>/oom_score_adj` too (a drop-in only binds on restart, and restarting a live desk
  to install OOM protection is the wrong trade).
- ⚠ The cap converts a machine-wide outage into a single job failure; it does **not** make the job
  finish. The real fix is checkpointing — sections already land on disk one at a time, so a fresh process
  per movement would stay flat in memory. [[friday-report-oom-killed-not-crashed]]
- ⚠ `gazbot7-core` and `gazbot7-strategy` are `disabled` and have **never started** — vestigial units.
  The desk is `gazbot7-tournament`, which writes `core_health.json`. `sweep.py` reporting "all up ·
  restarts core: 0" for a unit that has never run is false comfort of the same shape as
  [[router-tick-trusts-a-stale-health-file]].

## ★★ WEEKEND OF 2026-08-01/02 — READ `docs/WEEKEND_2026-08-01_CHANGES.md` BEFORE TOUCHING ANYTHING

Five headline recommendations went into that weekend and **one survived intact**. The desk changed a lot:
8 gates now (nipc live at 1 lot), the **quiet-tape clip** on exits (ATR<22 → both lots clip $40 / 1.75R
floored $60; ATR≥22 unchanged — `docs/REGIME_EXIT_CHEATSHEET.md`), all ER floors deleted, the `_base(slot)`
floor-wiring bug fixed, shadow slate cut 28→18, and 12 scripts corrected off a wrong $5 fee.

**The three traps that bit repeatedly — check for them in any number you are given:**
1. **MFE is not a win rate.** "X% of trades reach N R" ignores whether the STOP came first. It inflated
   capitulation's win rate 29% → 78% and shipped a losing config live. Compute the *race*.
2. **The fee is $1.50/RT**, never $5 or $2 or $1.50/side. Grep every harness for its fee constant; note
   `FEE, VPP = 5.0, 2.0` and `VPP, FEE = 2.0, 1.5` look identical at a glance and are reversed.
3. **The scale-out slate silently drops things.** It has now killed the ER/ATR floors, the ER-hold shadow,
   the regime-3 exit selector, and any base `target_r`. Verify config via `scaleout_slots()`, never source.
   ★ 2026-08-08 worked example: `grind_long` has **two** SlotSpecs in source — `slot_strategy.py:116`
   (no `ext_hi`) and `:161` (`ext_hi: 2.0`). The live slate resolves to **:161**. Editing :116 would have
   been a silent no-op. `scaleout_slots()` settles it in one line; source does not.
4. **A pick is not a ship, and a shadow result is not a live result.** `plays.json` now separates
   `operator_pick` from `status`, and `fix-shadow-repricer-stop-detection-0808` (the shadow book leaks
   past its own stops on **44%** of trades, median overshoot 0.56×ATR) gates every study that ever
   concluded *"exit earlier"*. It does **not** gate results that exit LATER — the bias runs the other way.

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
4. **Verify the safety layer is alive:** `systemctl is-active gazbot7-desk-reconcile.timer` and
   `tail data/desk_reconcile_state.json` — it should read `venue … = tournament … + rider …` with
   `unaccounted +0` and `0 orphan(s)`. This is the only thing on the box that reconciles ACROSS both
   desks, and the only thing that watches orders as well as positions.
2. **Read, thoroughly:**
   - `/home/alphabot/gazbot7/data/router_badcall_ledger.md` — the scored audit of past bench calls. Internalise the ❌/⚠ patterns so you don't repeat them.
   - `tail -50 /home/alphabot/gazbot7/data/router_trial_log.txt` — the recent tick-by-tick state + last switch changes.
   - Auto-memory `MEMORY.md` (already loaded) — especially [[router-tune-trial]] (permanent, mechanism), [[us-open-dont-bench-trend-rider]], [[rearm-momentum-needs-er-climb-not-delta-blip]], [[exhaustion-short-live-fader-success]].
3. **Verify desk health:** `cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json` — flat/healthy/not-halted, capture fresh, no wedge.

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
| `gazbot7-nightly-audit.timer` `21:30` | `claim_audit.py` + `nipc_replay.py`, inside the CME halt. |
| `gazbot7-gate-reactivate.timer` `22:00 = 00:00 Paris` | **⚠ arms EVERY `=off` gate.** A bench in `gate_switches.env` therefore only lasts until 22:00 — a longer hold must go in `reactivate_gates.py::HOLD` (currently `nipc_long`, `nipc_short`, `rgv_short`). |

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

## ★★★ 2026-08-06 INCIDENT — THE ACCOUNT IS SHARED. ONE FLATTEN CASCADED ALL DAY.

**07:08:01** tournament `abs_veto_long` bought 2 lots. **07:08:21** the DAY-RIDER sold them — its
hard-flat branch flattened the ACCOUNT net without checking whose position it was, while its own state
said `entered=false`. Both desks trade MNQ in **DUQ191770** and IBKR nets them into ONE number.

**The cascade, because nothing stayed local:** the tournament does not receive executions from another
clientId, so its book stayed +2 against a venue of 0 → reconcile DRIFT → **11 minutes halted with the
whole safety block skipped** (`multislot_core.py:610` gates max-hold, the naked auditor, re-protect and
stop-breach behind `!= "drift"`). `audit_age_s` stayed GREEN throughout — the loop was cycling, only the
work inside it was skipped. On restart it "exited" phantom longs into a real −1 short and booked two
mis-paired TARGET wins. Then at **13:47** a leftover GTC stop from that mess fired with no position
behind it, **opened a naked short**, and was booked as `nipc_short` — six and a half hours later.

**Fixed (`d0f5bbd`):** every day-rider flatten is ownership-gated (`safety.own_flatten_verdict`), the
watchdog too (it was passive only by luck — a disabled strategy still stamps a fresh heartbeat), and
`desk_view`/`recent_trades` now filter `data_quality IS NULL` so excluded rows cannot reach the ROUTER's
decision inputs (the convention existed only in the reporting layer).

**⚠ THE GAP THAT IS STILL OPEN:** the desk audits *"does every SLOT have a live stop?"* — it never asks
the inverse, *"does every live STOP have a slot?"* An order belonging to no slot is invisible to the
per-slot auditor, and that is exactly what fires unattended. **Check TWS for working stops with no
position behind them.** Same class as [[md-stream-multi-symbol-filter]]: a SHARED resource consumed
without checking the tag that says whose it is — there the stream was multi-symbol, here the account is
multi-desk.

**Also 08-06:** nipc hit the operator's **−$400** kill criterion exactly (n=47, 26% win) and was benched
at 13:09; it is in `reactivate_gates.py::HOLD` so the 22:00 reopen will not bring it back. Re-arming is a
fresh operator decision — the 08-05 regime filter had its first out-of-sample day and did NOT rescue the
short side (SHORT n=14 −$302.50 = 76% of the loss on 30% of the fills).

## ~~DURABILITY CAVEAT~~ — RESOLVED 2026-08-13

The old #1 fragility ("these crons are session-bound; keep the session alive and re-arm weekly") is
**gone**. Every standing job is a systemd timer; the session is optional. See the timer table above.

**★ The NEW #1 fragility is CREDENTIAL EXPIRY**, and the operator has declined a long-lived API key
(*"ill just relogin every now and then"*), so the alarm IS the mitigation, not a backstop to one. It
presents identically to a healthy desk — timer active, service exiting 0, sweep clean, log full of
"no change" — which is why `gazbot7-router-health.timer` exists. **If it pages, run `claude` on the
box and `/login`; nothing else is needed and no restart is required.**

## ★★★ DAY RIDER IS LIVE (PAPER) SINCE 2026-08-05 15:54 UTC — a SECOND desk, separate from the tournament

A new strategy runs **as its own service**, not as a tournament gate, and it places real (paper) orders.
`gazbot7-day-rider.timer` (every minute) + `gazbot7-day-rider-watchdog.timer` (every 2 min).
Switch: `data/day_rider.env` -> `day_rider=on|off`. **Currently ON.**
★ Deployed 08-05 at 15:54 UTC, i.e. AFTER that day's 15:00 entry cutoff — so it ticked and heartbeat
from 08-05 but its **first tradeable session is 2026-08-06**. Do not read an 08-05 no-entry as a miss.

```
DETECT  from the 13:30 UTC cash open: efficiency >=0.15 AND roundtrip >=0.45  (gazbot7/drift.py)
ENTER   2 lots, direction = sign of net. ONE entry per session. No entry after 15:00 UTC.
EXIT    trail 100pt, ARMED only once +150pt ahead. HARD FLAT 20:40 UTC.
ASK     a 2xATR reversal off the peak pages the operator 3x/15min -> DEFAULT IS HOLD.
```

**★ WHY IT IS NOT A GATE:** `multislot_core.py:372` force-flattens every position at
`max_hold_minutes=120`; this holds ~7h. Inside that cap it earns $7,047 and FAILS the battery; uncapped
$13,257 and passes 5/5. Do NOT "fix" this by raising the global cap — that cap is what limited the
MD_STREAM incident to −$255.50.

**★★ FLAT AT 20:40 UTC (22:40 Paris), NEVER 21:00.** 21:00 UTC *is* the CME halt — a flatten fired then
has no market and no retry. 20:40 leaves 20 minute-ticks of retry. Cost: $149 of $13,257; days-green
81%→84%. **STANDING OPERATOR RULE: NEVER HOLD OVERNIGHT. EVER.**

**★ THE ANCHOR IS THE CASH OPEN, and this was tested — do not re-litigate.** A 22:00 UTC (midnight
Paris/CME) anchor gives ZERO detections in 33 sessions: 15h40m of overnight chop makes the path ~25x
longer so efficiency collapses to 0.048 vs the 0.15 floor. Full numbers pinned in `drift.py`.

**★ SAFETY, since it inherits none of the tournament's:** heartbeat + an INDEPENDENT flatten-only
watchdog (clientId 5) that requires BOTH a fresh heartbeat AND `venue_ok` — a tick that could not reach
IBKR still stamps a heartbeat, and treating that as "managed" would recreate the naked-position bug.
600pt venue stop is last-resort insurance only (a 400pt stop costs $3,451 and *worsens* the worst day).
Restart-safe atomic state. Fail-closed everywhere; a garbled switch reads OFF.

**★★2026-08-13 — FOUR FIXES AFTER IT SOLD 8 LOTS IT DID NOT OWN.** Full account in
`docs/SESSION_2026-08-13.md`; all live and tested, but **none has traded yet** — 08-14's open is
their first real exercise.
- **the `closed` guard.** Section-2's manage block now tests `abs(net) > 1e-9 and entered and NOT
  closed`. `net` is the SHARED ACCOUNT NET, so without the last clause the tournament opening a
  position re-animated a rider trade that had already closed. Pinned by a test that also asserts the
  source line has not drifted.
- **`venue_first_ok()`** gates ENTRY / TRAIL / MANUAL_CLAIM / OPERATOR_SELL on the cross-desk
  invariant. ⚠ **NOT the 20:40 hard flat** — refusing to flatten because the books disagree turns a
  bookkeeping fault into an overnight position, which is strictly worse. A test pins that exemption.
- **`CLOSED_ELSEWHERE`.** Venue flat at the clock while our book still holds now books, latches and
  ALARMS. It used to fall through silently: **2 of 4 rider trades this week never reached the
  ledger** (backfilled as `CLOCK_FLAT_RECON`).
- **`cancel_own_stops()`** on all five close paths. The 600pt stop used to outlive every exit — one
  sat working for 2h against a flat account. **clientId-filtered: it must NEVER cancel the
  tournament's per-slot stops**, and that is the tested safety property, not an optimisation.
- ⚠ The trail readout used to print `need +150` (the `ARM_PT` fallback) while the rule armed at
  `4 × arm_atr` ≈ **131pt**. It overstated the distance to arming by ~19pt every time it was read.

**★ THE EXIT IS ESSENTIALLY EXIT-PROOF — 25 variants tested, holding to the flat beat every one.**
Stops (7 widths) all negative; give-back rules ~$0; progress/underwater exits worse; reactive
direction-change worse by $3,115+. Do not re-run these. The ONE thing that beat holding is the
armed trail (+$2,320), and a fixed 400pt target lands within $33 of it — so "take profit somehow"
is the robust finding, not the specific mechanism.

⚠ It is 31 in-sample sessions after ~60 configurations. Treat the first weeks as evidence, not proof.

## ★★ DATA & BACKUP ARCHITECTURE (2026-08-05) — read `docs/BACKUP_AND_ARCHIVE.md` before touching retention

**The tape no longer lives only in SQLite.** `capture.db` holds **5 TRADING days** (days with rows, so
weekends/holidays do not consume the window); everything older is **Parquet** — locally in `data/tape/`
and permanently in Backblaze B2. Same rows, same columns, **28x smaller**.

- **Query history via `gazbot7.lake.connect()`**, NOT by ATTACHing capture.db. It gives
  `ticks/quotes/bars/book/depth` views over local Parquet, or straight off B2 when local is absent.
  Measured: 11.2M rows aggregated in 12.1s over the network. Most existing harnesses still ATTACH
  capture.db and will silently see only 5 days — check before trusting an old script's window.
- **B2 is split by sensitivity.** Market tape is PLAINTEXT (`b2raw:gazbotv7/plain/`) so DuckDB can read
  it in place; the trade record (`gazbot7.db`, configs) is ENCRYPTED (`gaz:` crypt). Credentials live in
  `/root/.config/rclone/rclone.conf` and the operator's password manager — **never in git**.
- **★ THE INTERLOCK:** `prune_capture.py` may not delete a day `tape_mirror.py` has not exported AND
  verified by row count. If the mirror stops, the prune stops and capture.db grows. Growth you notice;
  a silent gap in the tape you do not.
- `data/exit_overrides.json` is now git-tracked and every desk startup journals its RESOLVED exit ladder
  to `config_journal.jsonl` — `scripts/config_at.py --at/--epochs/--diff`. Reconstructing a config epoch
  by hand is what made 07-31→08-02 unrecoverable.
- **★2026-08-08 THE JOURNAL NOW RECORDS THE ENTRY SIDE TOO.** It used to log the exit ladder only, on the
  reasoning that entry params were "already recorded by slot_strategy.py and git". Both halves were
  false — **git does not record an uncommitted tree, and source is not the resolved config.** Proven the
  same day: SATURDAY #2 changed a live entry floor (`ATR_FLOOR` 10→22, `ext_hi` deleted), the desk
  restarted, and the journal logged `changed_from_previous: false`. Rows now carry `entry` (per-slot
  params/sizing) + `gates` (the global `ATR_FLOOR`/`ER_FLOOR`/`ER_CEIL`/`ER_BAND` dicts) + `entry_hash`.
  Read with **`config_at.py --epochs --entry`**. `config_hash` keeps its exit-only meaning so every
  existing scan stays valid; pre-08-08 rows show `- (not recorded)`, which is *unknown*, not *unchanged*.
- **★2026-08-08 A DIRTY TREE NOW SHOWS UP IN THE SWEEP.** `sweep.py::check_config_committed()` WARNs if
  `exit_overrides.json` / `deciders.py` / `slot_strategy.py` / `multislot_core.py` are uncommitted. The
  journal had been stamping `exit_overrides_uncommitted: true` at every startup since 08-04 and **nothing
  consumed it** while five live behaviours existed only as working-tree edits. WARN not CRIT on purpose:
  a dirty tree is a bookkeeping failure, not an order-path failure, and a CRIT would train you to ignore
  a red sweep on a desk that is trading fine.
- ⚠ `scratchpad/` (807MB), `scratch/` and `*.pre-*` snapshots were **not** in `.gitignore` until 08-08.
  A "commit everything" would have put ~826MB into the repo. They are ignored now.

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
