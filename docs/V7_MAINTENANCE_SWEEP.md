# GAZBOT V7 — Maintenance Sweep (session-cron ritual)

**Status:** canonical re-arm reference. Written 2026-07-19. Replaces the **V5**
CLAUDE.md §8 "nine-cron" ritual for the V7 desk — that V5 set probes the masked
`:8090` broker + `alphabot.db` surfaces and would false-CRIT / bounce the shared
gateway. **Do NOT re-arm the V5 crons.** Re-arm the two below.

> **The model (unchanged from V5 §8).** The desk is maintained by *you* — this
> Claude Code session, on Garrath's Max plan — via self-scheduled `CronCreate`
> timers. Those crons are **session-only**: they die when the session/tmux
> restarts. **This file is the source of truth for rebuilding them.** On every
> fresh session start, after reading `docs/STATE.md`, re-arm from here.

---

## Re-arm procedure (on every session start)

1. `CronList`. If a job below already exists, leave it — do NOT duplicate.
2. If absent, `CronCreate` it (`recurring: true`). Box is **UTC**, so cron fields are UTC directly.
3. Confirm to Garrath you're back on shift with the posture line (see bottom).

**★ THE FULL STANDING SET IS NOW SIX CRONS (grown 2026-07-27/28) — re-arm ALL, not just the two below:**
| # | schedule (UTC) | job | verbatim prompt |
|---|---|---|---|
| A | `41 */3 * * 1-5` | FULL health sweep + heartbeat | Cron A below |
| B | `9 20-23 * * 0` | Sunday pre-open RAMP | Cron B below |
| C | `8 5-21 * * 1-5` | Adaptive hourly TAPE/GATE WATCH (`scripts/hour_watch.py`, tiered) | the standing hour-watch prompt (2-tier: routine line / `ATTENTION GAZ` escalate) |
| D | `43 22 * * 1-5` | Grind-exit shadow watchers (`two_ratchet_shadow_watch.py --ping` + `partial_shadow_watch.py`) | run both, ping only on a runner-clip; ⚠ note grind moved off pure-6.0 to the adaptive selector |
| E | `50 22 * * 1-5` | **Nightly router + selector performance review** (`router_nightly.py` + `selector_nightly.py`) | run both, write the dated ledgers, ping only if notable; feeds Friday part25 — see memory `nightly-router-selector-review` |
| F | `25 13 * * 1-5` | **US-open router check** (5 min before the 13:30 cash open) | run the router (apply the OPEN_WINDOW override), verify the 3 momentum gates are `on` + desk-ready, ping green/⚠ — the momentum gates MUST be armed to catch the opening run |
Crons C/D/E post-date this doc's original 2-cron ritual; if their verbatim prompts aren't to hand on a cold start, recover C from the hour_watch behaviour above, D from the grind-exit shadow scope, E from memory `nightly-router-selector-review` + the two scripts' `--help`/docstrings.

The heavy lifting lives in a **tested, read-only** collector — the cron prompts
are thin orchestration over it:

- **Collector:** `cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json`
  → `{overall: OK|WARN|CRIT, preflight_ok, sections:{services, core, capture,
  execution, position, killswitch, recording, shadow, storage}}`. Venue-truth-first;
  never second-guesses core's freshly-written health. Reads the shared
  `alphabot-gateway`, `core_health.json` preflight+freshness, capture 5s/250ms
  with the feed-break tell, execution wedge, the venue-truth **protection/naked**
  gate, killswitch headroom, recording (V7 has **no backfill path** — a
  reconstructed row is an anomaly), shadow repricer lag, storage/disk.
- **Notifier (tiered, quiet-hours in code):** `.venv/bin/python -c "from
  gazbot7.notify import notify; notify('<msg>', critical=<bool>)"`. `critical=True`
  always sends; `critical=False` (routine) self-suppresses 22:00–06:00 Paris.
- **Independent safety net:** `gazbot7-monitor.timer` (systemd, every 10 min) is
  the tight fills-based execution-wedge alarm and **survives session death** —
  the sweep crons are the broad curated layer on top, not the only guard.

**Doctrine: READ-ONLY + FLAG-AND-WAIT.** No auto-fix, no restarts, no DB writes.
V7 core self-heals (confirmed-naked→flatten, arm-time stop-confirm, vanished-close
reconstruct). Anything red → flag to Garrath; a broker/strategy/gateway restart
with an OPEN position is operator-decided and paired (STATE §3). This is stricter
than the V5 auto-fix allowlist by design — the go-live desk is watched, not
auto-touched.

---

## Cron A — FULL sweep (3-hourly)

**Schedule:** `41 */3 * * *` (every 3h at :41 UTC).

```
V7 maintenance sweep (FULL, 3-hourly) — you, this Claude Code session on Garrath's Max plan, set this timer to keep the LIVE GAZBOT V7 futures desk healthy. The live desk is V7 at /home/alphabot/gazbot7 (MNQ-only, PAPER, two-gate grind_fast + rg_long_fast_v, single-position first-to-fire). The V5 alphabot2 desk is RETIRED — do NOT probe :8090/:8092/:8000 or alphabot.db, and do NOT re-arm the old V5 nine-cron ritual.

RUN THE COLLECTOR: `cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json`. It is the tested, read-only, venue-truth-first V7 health readout — services (incl. the shared alphabot-gateway), core_health.json preflight+freshness, capture 5s/250ms freshness with the feed-break tell, execution wedge, position with the venue-truth protection gate, killswitch headroom, recording (V7 has NO backfill path — a reconstructed row is an anomaly), shadow repricer lag, storage/disk. Parse the JSON: `overall` (OK/WARN/CRIT), `preflight_ok`, each section's status+detail. (The tight fills-based execution wedge alarm also runs every 10min as the external gazbot7-monitor.timer — this sweep is the broad curated layer.)

READ-ONLY + FLAG-AND-WAIT. Do NOT auto-fix, restart, or write any DB. V7 core self-heals (confirmed-naked→flatten, arm-time stop-confirm, vanished-close reconstruct). Anything red → flag to Garrath, don't touch. A broker/strategy/gateway restart with an OPEN position must be operator-decided and paired (STATE §3).

ALERT via V7's tiered notifier: `cd /home/alphabot/gazbot7 && .venv/bin/python -c "from gazbot7.notify import notify; notify('<msg>', critical=True)"` (critical always sends; routine self-suppresses 22:00–06:00 Paris). Fire CRITICAL on: overall CRIT or preflight FAIL; a held-but-unverified/naked position (possible stopless — say CHECK IBKR / flatten); an execution wedge (submitted>0, fills=0, or rejects); a 5s-stale-while-ticks-live feed-break (gateway farm drop). Name the actual red section from its detail line.

HEARTBEAT (routine, `notify('<msg>', critical=False)`): in Paris waking hours send ONE tight human line — "hey Garrath — V7 desk <flat/holding>, <all green / N warns: what>, gate=grind+rgv PAPER". If the Paris hour is 6 (first fire after the quiet window), make it the overnight wrap (trades + P&L + any incident since 22:00 Paris). Quiet hours: notify() suppresses routine automatically, so just call it.

REPORT in-session: overall, any WARN/CRIT + what you alerted, held-for-your-OK items. Context: /home/alphabot/alphabot2/docs/STATE.md §0–8, /home/alphabot/gazbot7/docs/GAZBOT_V7_SCOPE.md.
```

---

## Cron B — Sunday pre-open / open RAMP (hourly into the Globex reopen)

**Schedule:** `9 20-23 * * 0` (Sun 20:09 / 21:09 / 22:09 / 23:09 UTC).
Globex reopen = **22:00 UTC = 00:00 Paris Monday**. Mandatory ping every run
(overrides quiet hours). Watches the desk arm + take the first fills of the week.

```
V7 Sunday PRE-OPEN / OPEN RAMP (hourly 20:00–23:00 UTC = 22:00 Paris Sun → 01:00 Paris Mon) — you set this timer to WATCH the LIVE GAZBOT V7 desk come alive into the Sunday CME/Globex reopen (22:00 UTC = 00:00 Paris Monday) and PING Garrath EVERY run. The live two-gate lineup is grind_fast (conviction-sized) + rg_long_fast_v (LONG-only 2R), single-position, PAPER. The go-live watch: confirm a 2-lot order actually FILLS (paper account size-limit is unverifiable ahead of time; a reject is SAFE and the execution monitor alarms on it), and kill-switches are OFF for paper (native 1-ATR stop still caps each trade).

RUN: `cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json`. Read `overall`, `preflight_ok`, and the services/core/capture/execution/position/recording sections. READ-ONLY + FLAG-AND-WAIT — no fixes, no restarts, no DB writes; V7 core self-heals, you watch + alert.

MANDATORY PING EVERY RUN (overrides quiet hours — use critical=True so it always sends): `cd /home/alphabot/gazbot7 && .venv/bin/python -c "from gazbot7.notify import notify; notify('<msg>', critical=True)"`. Compute hours-to-open (open = 22:00 UTC; `date -u` for now).
- BEFORE open (fires ~20/21 UTC): "hey Garrath — V7 Sunday pre-open watch, ~Nh to reopen (00:00 Paris). Desk <flat/healthy>, gateway <conn>, gazbot7 services green / <issue>, gate=grind+rgv PAPER armed."
- AT/AFTER open (fires ~22/23 UTC): "hey Garrath — V7 desk OPEN (reopened 00:00 Paris). <trading: N entries / M fills recording / still warming up>. First 2-lot fill: <confirmed / none yet / REJECTED — check>. <overall + any red>."
A genuine CRIT / degraded gateway / naked-position / execution wedge → say it plainly in the same ping (still critical=True).

REPORT in-session: readiness, is it trading post-open, the first-fill status, anything held for your OK. Context: /home/alphabot/alphabot2/docs/STATE.md §1-3 (the go-live), /home/alphabot/gazbot7/docs/GAZBOT_V7_SCOPE.md.
```

---

## Back-on-shift line (say this after re-arming)

> Claudio back on shift — V7 maintenance armed (FULL 3-hourly sweep via
> `gazbot7/scripts/sweep.py`, read-only + flag-and-wait, tiered Telegram; Sunday
> open-ramp hourly 20:00–23:00 UTC with a mandatory ping into the Globex reopen).
> The 10-min `gazbot7-monitor.timer` covers the execution wedge independently.
> Watching the desk.

## What is deliberately NOT here (vs V5 §8)

The V5 ritual had nine crons (LIGHT overlay, nightly self-analysis, weekly
interrogation report, Saturday test-cleanup, BEACON, cron-liveness). Those are
bound to V5 tables/endpoints (`desk_analysis`, `reports`, `/api/day|review`) and
the V5 test suite — **not ported**. Re-introduce a V7 equivalent only when the
matching V7 surface exists. The Friday shadow report has its own pipeline
(`scripts/friday/…`, memory `friday-shadow-workflow`), separate from this sweep.
