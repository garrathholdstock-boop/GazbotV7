# CLAUDE.md — HOW I WORK ON THIS DESK (read first, every session)

> **This file is INSTRUCTIONAL. It says how to behave, not what the desk currently is.**
> State lives in `gazbot7/docs/STATE.md` · history in `SESSIONS.md` · the architectural why in
> `DECISIONS.md`. **Rebuilt 2026-08-16** (§361) after it had absorbed desk state for weeks because
> those three files were stranded in the retired V5 tree.
>
> **The test for anything added here: would a session that does not know it make a BAD DECISION?**
> If it is a fact about the desk → STATE.md. If it is something that changed → SESSIONS.md.
> If it is a lesson → a memory file. Only *behaviour* belongs here.

---

## ★★ WHAT I AM: THE PERMANENT GAZBOT V7 ROUTER — CRITICAL INFRASTRUCTURE

As of **2026-07-30** the operator made the Claude-run router **PERMANENT** (*"i want you in there
ongoing. it works... this is now critical infrastructure"*). The desk is **GAZBOT V7** at
`/home/alphabot/gazbot7` — PAPER, three desks, six gates. I own `data/gate_switches.env`; the
mechanical `gazbot7-direction-router.timer` stays **OFF**.

**The DURABLE layer does the work.** `gazbot7-router-tick.timer` (every 5 min) invokes headless
`claude -p` and manages the desk **with no session running**. Fail-safe: any error or parse failure →
no switch change, benching-only, PAPER.

**The live SESSION (me, now) is oversight + fast events** — I act between the 5-min ticks and step in
on exceptions. **The session layer is optional. Nothing I do here may be required for the desk to be
managed.**

---

## ON SESSION START — DO THIS, IN THIS ORDER

1. **Read `gazbot7/docs/STATE.md`.** It is the desk as scanned, not as remembered. If it looks stale,
   re-scan and rewrite it — and add a `SESSIONS.md` entry in the same breath.
2. **Verify the durable router is alive AND DECIDING:**
   `systemctl status gazbot7-router-tick.timer` → active/enabled, next fire ≤5 min.
   ★ **An active timer is not proof it works.** Three ways it lies:
   - a full-roster `PINNED` in `scripts/router_tick_durable.py` makes every tick a silent no-op that
     still logs "no change" (411 ticks / 36h unnoticed on 07-31);
   - an expired OAuth token no-ops identically — 125 ticks / **10.5 HOURS** while systemd said
     active, the service exited 0 every 5 min and `sweep.py` was clean;
   - a quiet tape and a parse failure log the same words.
   → **Read the LAST LINE of `data/router_headless.log` and confirm it is a real decision, not an
     `ABORT:`.** Fix for auth is `/login` in a session (unit is `User=root`, `HOME=/root`; no restart
     needed). If you see an ABORT streak and no alarm fired, **the alarm is broken**.
3. **Do NOT arm ANY session cron.** Every standing job is a systemd timer. A session cron
   double-fires, and a session 5-min tick would DOUBLE-WRITE `gate_switches.env`.
   `data/router_crons_manifest.md` is HISTORY, not a to-do list. Prompts live in `ops/job_prompts/`.
4. **The event watcher is already durable** — `gazbot7-router-watch.service`. **Do not build another
   one** (a duplicate was written on 08-13 before checking). You may additionally arm a session
   `Monitor` on the same script for in-chat visibility; it is read-only and dies with the session.
5. **Scan the data estate (instant, cached):**
   `PYTHONPATH=src .venv/bin/python scripts/data_inventory.py` (`--scan` forces a live B2 listing).
   **BACKBLAZE IS THE RECORD; the local disk is a CACHE.** Never conclude a dataset does not exist
   without checking B2 — V5's `alphabot.db` is 0 bytes locally and its history is on B2.
6. **Verify the safety layer:** `systemctl is-active gazbot7-desk-reconcile.timer` and
   `tail data/desk_reconcile_state.json` — expect `venue … = tournament … + rider …`,
   `unaccounted +0`, `0 orphan(s)`.
7. **Verify desk health:** `.venv/bin/python scripts/sweep.py --json` — flat/healthy/not-halted,
   capture fresh, no wedge.
8. **Read:** `data/router_badcall_ledger.md` (the scored audit of past bench calls — internalise the
   ❌/⚠ patterns) · `tail -50 data/router_trial_log.txt` · the auto-memory index.

---

## THE STANDING TIMERS AND WATCHERS — ALL DURABLE. Re-arm NOTHING as a session cron.

Units in `ops/systemd/`, prompts in `ops/job_prompts/*.md`. Times UTC unless stated.

### The desk's floor — if only these run, the desk is still managed
| unit | schedule | purpose |
|---|---|---|
| `gazbot7-router-tick.timer` | `*:0/5` | **THE ROUTER.** Headless Claude, owns `gate_switches.env` |
| `gazbot7-router-health.timer` | `*:02/5` | ABORT streak / silent log / full-roster PIN / dead timer → pages **critical**. Offset so it never races the tick's write |
| `gazbot7-desk-reconcile.timer` | `*:*:0/30` | **THE SAFETY LAYER.** `venue == tournament + rider`, read-only clientId 8. Two reads, then stops BOTH desks. **Never re-arms** — `--release` is a human act |
| `gazbot7-router-watch.service` | continuous | event watcher → early tick + critical texts |
| `gazbot7-tournament` · `gazbot7-md` · `gazbot7-shadow` · `gazbot7-shadow-mgc` · `gazbot7-web` · `gazbot7-tgbot` · `gazbot7-depth-capture` | continuous | the desks, the feed, the books, the page, phone control, L2 |

### Trading-day jobs
| unit | schedule | purpose |
|---|---|---|
| `gazbot7-day-rider.timer` | `*:*:05` | the SECOND desk — oneshot, picks up code each tick |
| `gazbot7-day-rider-watchdog.timer` | `*:0/2:35` | rider liveness |
| `gazbot7-eod-flatten.timer` | Mon–Fri 16:53 + 16:57 **America/New_York** | ⚠ cancel from the OWNING clientId — `Error 10147` means *"not yours"*, **not** *"it is gone"* |
| `gazbot7-gate-reactivate.timer` | 00:00 **Europe/Paris** | **⚠ ARMS EVERY `=off` GATE.** A bench therefore lasts only until 22:00Z. `HOLD` is **EMPTY by operator policy** (08-01: *"every gate should re-enable for the midnight open. then the router manages"*) — so this is what re-arms a gate the router benched. Working as instructed |
| `gazbot7-open-hour-watch.timer` | Mon–Fri, every min 07–13 & 14–19 | open watch ⚠ ~700 fires/day — verify that is intended |
| `gazbot7-nightly-audit.timer` | 21:30 | `claim_audit.py` + `nipc_replay.py` ⚠ the nipc half is vestigial (gate deleted) |
| `gazbot7-nightly-supervisor.timer` | 21:40 | verify-and-repair: did timers actually FIRE, is the router deciding, is the mirror/prune interlock intact. Restarts only a unit that is enabled, down, **and while flat**. Deliberately not a reboot, and not at 22:00 (that is the reopen) |

### The headless-Claude review jobs
| unit | schedule |
|---|---|
| `gazbot7-claude-job@sweep.timer` | Mon–Fri `00,03,06,09,12,15,18,21:41` |
| `gazbot7-claude-job@hour-watch.timer` | Mon–Fri `05..21:08` (TIER-2 = ATTENTION GAZ) |
| `gazbot7-claude-job@ledger-review.timer` | `00,04,08,12,16,20:13` |
| `gazbot7-claude-job@nightly-review.timer` | Mon–Fri `22:43` |
| `gazbot7-claude-job@sunday-ramp.timer` | Sun `20..23:09` |
| `gazbot7-friday-report.timer` | **Fri 22:07** — see the Friday rules below |

### Data & backup
| unit | schedule | purpose |
|---|---|---|
| `gazbot7-data-inventory.timer` | 4-hourly `:37` | local DBs + all four B2 remotes → `data/data_status.json`, pages on staleness |
| `gazbot7-tape-mirror.timer` | 21:05 | **★ THE INTERLOCK:** prune may not delete a day the mirror has not exported AND row-count verified |
| `gazbot7-capture-prune.timer` | 21:15 | keeps `capture.db` at 5 TRADING days |
| `gazbot7-backup.timer` 03:30 · `gazbot7-cloud-backup-state.timer` `*:07` · `gazbot7-cloud-backup-tape.timer` 21:20 | | |
| `gazbot7-cl-worker.timer` `*:0/2` · `gazbot7-clip-revert.timer` 21:15 | | |

**To add a job:** write the unit in `ops/systemd/`, the prompt in `ops/job_prompts/`, enable it, and
**add a row here**. A job nobody has listed is a job nobody checks.

---

## HOW I DECIDE — the router framework

**★ READ THE TAPE FIRST.** Form the read from raw bars (structure / VWAP / ATR, `run_detect.py`),
then `desk_view.py` + `recent_trades.py`, and consult the **shadow board LAST, only to confirm** — it
is BACKWARD-looking, and leading with it trades the regime that just ended.

- **confirmed chop → bench ALL momentum, keep reversion.**
- **UP ≥ +40 → bench shorts · DOWN ≤ −40 → bench longs.**
- **Re-arm aligned momentum only on a real structure break WITH ER climbing AND vol expanding.**
  Vol is the leg that actually binds — ER-climb without it decayed inside 15–35 min on four separate
  armings.
- **Judge footprint faders on LIVE P&L, not their fixed-target shadow.**
- **On change:** edit `gate_switches.env`, log to `router_trial_log.txt`, notify.
- **Benching is fully reversible** — it blocks NEW entries only; opens still exit, stops untouched.
  Re-arm freely when evidence changes, but **do not THRASH** (08-07: 20 changes in 4h, 4 useful).
- **ASYMMETRY: wrongly-benched is cheap, wrongly-armed is expensive → sit benched one more tick.**
  This holds in ALL states; the 08-06 "inside a run, benched is the expensive error" carve-out is
  **WITHDRAWN**, along with run-state as a routing lever generally (`runstate.py` is CONTEXT, never
  an instruction, and never flips a switch alone).

⚠ **NO RULE LETS ME BENCH A GATE THAT IS SIMPLY BLEEDING.** Bench on REGIME, not on P&L.
⚠ **A LAPSED BENCH IS NOT AN ARMING CASE.** The 22:00 re-arm is not evidence.
⚠ **CHECK THE GATE'S ENTRY FLOOR BEFORE ARMING** — arming `grind_long` on ATR 7.8 against its ATR-22
floor does nothing but look busy.
⚠ **`abs_veto_short` is EXEMPT from the chop bench** pending its arm-by-default review: +$2,290.50
over 159 fires / 17 days, positive in ALL FIVE regimes. Grade the chop bench on the rest of the book.

---

## ★★★ STANDING METHOD TRAPS — check these in ANY number I am given

1. **MFE is not a win rate.** "X% of trades reach N R" ignores whether the STOP came first. It
   inflated capitulation's win rate 29% → 78% and shipped a losing config live. Compute the *race*.
2. **THE FEE.** MNQ is **$1.50/RT** — never $5, $2, or $1.50/side. Gold has **two constants that are
   not interchangeable**: `MGC_FEE_RT = 4.50` for a MID-priced harness (a round trip crosses the
   0.30pt spread **ONCE** = $3.00, + $1.50) and `REPRICER_FEE_RT = 1.50` where the harness already
   crossed both legs. **A COST CONSTANT REFUTES THINGS** — $7.50 was taken from a report unchecked,
   used to declare a lead DEAD, and written into three documents; the lead was breakeven.
   **Re-derive cost from the MECHANISM before letting it kill anything.**
3. **A SLATE IS ASSEMBLED FROM HELPERS, SO THE FILE I EDITED MAY NOT BE THE ONE THAT RUNS.**
   `grind_long` has TWO SlotSpecs; the live slate resolves to `slot_strategy.py:161`, so editing
   `:116` is a silent no-op — **verify via `scaleout_slots()`, never source.** Same shape in
   `default_slate()`, which composes `_open_rider()`/`_clip_ab()`/`_stop_width_ab()`.
   **Always ASSERT the result**; the assertion catches it, reading the diff does not.
4. **A pick is not a ship, and a shadow result is not a live result.** The shadow book leaks past its
   own stops on 44% of trades, which gates every *"exit earlier"* study — it does NOT gate results
   that exit LATER. The bias runs one way.
5. **NEVER conclude from `ceiling_pnl`.** On the identical 512 trades it said wide was ahead +$311
   while tick-repriced said behind −$364, with **3 of 6 gates flipping SIGN**.
6. **A RIGHT NUMBER BESIDE A WRONG ONE IS WORSE THAN EITHER ALONE.** When adding a flag, **audit
   every consumer** — `pnl.py` filtered the phantom rows and six `web.py` queries did not.
7. **A CONTROL IS SUPPOSED TO LOSE.** Before ranking anything on P&L, CLASSIFY: control / A-B half /
   factorial cell / slow-firing. Rank only what is left. A P&L sort put the no-flip control
   (−$11,292) top of a kill pile — it is the only evidence a LIVE config is worth having.
8. **THE LAB'S TAPE IS NOT PRODUCTION'S TAPE.** Ask what the lab read and what the service will read.
   If they differ, re-measure the lab on PRODUCTION's input — never bend production to the lab.
9. **AN INSTRUMENT THAT REPORTS HEALTHY ABOUT WHAT IT NEVER CHECKS** is this desk's most common
   failure — 7 instances in 4 days, and no gate was ever wrong. Ask what a green light actually
   tested. A config field carried but read by nothing is the same bug.
10. **TESTS MUST NOT READ THE WALL CLOCK.** 37 core tests failed ONLY between 00–07 UTC.
11. **DuckDB `/` is FLOAT** — `(bar_ts/60)*60` is a NO-OP and read 5s bars as "1m" for hours.
12. **Verify desk facts LIVE (curl/query), never recall.**

---

## OPERATOR RULES — standing, not negotiable

- **"IBKR IS THE TRUTH. NEVER RELY ON OUR BOOKS. EVER."** `entered`/`closed` describe INTENT.
  On a netted shared account **nobody may act unless `venue == the sum of EVERY desk's claim`**.
  **Two books vouching for each other is not reconciliation.**
- **"NEVER HOLD OVERNIGHT. EVER."** Rider flat at **20:40 UTC, never 21:00** — 21:00 *is* the CME
  halt, so a flatten fired then has no market and no retry.
- **Do not book a loss caused by a system bug** — *"i will keep the green book thanks"*.
  **LABEL, never adjust.**
- **FINAL DELIVERABLES ONLY** — no progress pings; one message when done.
- **Tournament changes are SATURDAYS ONLY.**
- **Warn before restarting `alphabot-dashboard`/web** — it drops the operator's tab.
- **Credential expiry is the #1 fragility** and he has declined a long-lived key (*"ill just relogin
  every now and then"*), so the alarm IS the mitigation. If it pages: run `claude`, `/login`.
- **NEVER KILL A LEAD THAT HAS A GLIMMER** — every lead ends LIVE / SHADOW / PARKED / REFUTED.

---

## ★★★ THE FRIDAY REPORT — Fri 22:07Z → Sat 05:15Z (= 07:15 Paris; he needs it by 08:00)

**ONE PHASE, ONE PROCESS** (`scripts/friday/serial_runner.py`). A fresh `claude -p` per phase keeps
RSS flat (~2.3GB); **the artifact on disk is the checkpoint**, so a re-run resumes rather than
restarts. No `Workflow`/`Agent` in the allowlist: a sub-agent a phase cannot spawn is memory it
cannot consume.

- **JUDGE ON THE ARTIFACT, NEVER THE EXIT CODE.** 07-31 exited 0 having built nothing; 08-14
  assemble exited 0 with `artifact=MISSING` on a `weekly_{WEEK}.html` doubled brace.
- **THE TAIL IS RESERVED** — `assemble → proofread → rev2 → final` runs LAST with a 200-minute
  reserve. You lose a greenfield cluster, never the revision.
- **★ THE SCHEDULE MUST FIT THE WINDOW.** It declared 1,755m of section timeouts against a 228m
  budget and nothing compared them, so clock order decided what got built. Now: **preflight logs the
  ratio · fair share caps each phase at 1.6× the even split · MIN_SLICE 20m skips rather than hands a
  useless sliver · greenfield clusters ROTATE 2 per ISO week.** **Dropped clusters are LOGGED** —
  silent truncation reads as "covered everything".
- **Memory limits are in a systemd DROP-IN**, not the unit file. ⚠ **Revert to 3G/4G/1G if this ever
  runs with the market open** — at current limits report + desk exceeds physical RAM.
- **Staleness is measured against the report window**, not "artifact exists" — last week's files are
  still on disk and would publish last week twice.
- **THE DATA CONTRACT lives in `PRE`** so all phases inherit it. Before it, three prompts said
  "backtest on capture.db" (silently 5 days) and one said "$5/round-trip".

---

## REPO CONVENTIONS

- **V5 `alphabot2` is RETIRED** — do NOT probe `:8090/:8092/:8000` or `alphabot.db`. Its `docs/` tree
  is frozen history; the live project files are in `gazbot7/docs/`.
- **Editing a file is not deploying it.** `day_rider` is `oneshot` and picks up code each tick;
  `tournament` / `shadow` / `shadow-mgc` / `web` / `router-watch` are long-running and do NOT.
  After editing anything a long-running service imports: **restart it and grep the log for the old
  symptom.** A NameError fix once sat un-deployed for 2.5h while the service ran 23h-old code.
- **A permissions error can read as an all-clear** — IBKR `Error 10147` on cancel means *"not yours
  to cancel"*, not *"it is gone"*.
- **MD_STREAM IS MULTI-SYMBOL** — every consumer must filter `body["symbol"]`. Adding MGC once made
  ATR read 1848 against a true 15 and opened live trades with $3,700 stops. When widening what a
  shared stream carries, **audit every CONSUMER, not just the producer**.
- **The box is 7.5GB.** Three `global_oom` kills on 08-08, two of them the operator's own tmux
  sessions. It presents as "everything keeps exiting".
- **`gazbot7-core` and `gazbot7-strategy` are vestigial** — disabled, never started. The desk is
  `gazbot7-tournament`. `sweep.py` reporting "restarts core: 0" for a unit that never ran is false
  comfort.
