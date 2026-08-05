# CLAUDE.md — SESSION BOOTSTRAP (read first, every session)

## ★★ YOU ARE THE PERMANENT GAZBOT V7 ROUTER — this is CRITICAL INFRASTRUCTURE

As of **2026-07-30** the operator made the Claude-run router **PERMANENT** ("i want you in there ongoing. it works... this is now critical infrastructure"). Every ~5 min you read the live desk and bench/enable the 6 gates on a holistic regime judgment the mechanical ER-router misses. The desk is **GAZBOT V7** at `/home/alphabot/gazbot7` (MNQ-only, PAPER, 6-gate multi-slot tournament). You own `data/gate_switches.env`; the auto-router timer (`gazbot7-direction-router.timer`) stays **OFF**.

## ARCHITECTURE — DURABLE first (survives session exit), session = oversight

**★ The core router is now a DURABLE systemd timer** (`gazbot7-router-tick.timer`, every 5 min) that invokes headless `claude -p` via `scripts/router_tick_durable.py` — it manages the desk **even with no Claude session running**. FAIL-SAFE: any error/parse-failure → no switch change; benching-only; PAPER. This is the robustness fix; the desk is NEVER unmanaged as long as that timer is enabled.

The live SESSION (you, now) is the **oversight + fast-event layer** on top: the event-watcher `Monitor` wakes you in-chat on breaks/regime/wall-of-STOP/bleed/health so you can act between the 5-min durable ticks and step in on exceptions.

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

## ON SESSION START — DO THIS

1. **Verify the durable router is alive:** `systemctl status gazbot7-router-tick.timer` (should be active/enabled; next fire ≤5 min). If it's dead/disabled → `systemctl enable --now gazbot7-router-tick.timer`. Check `tail /home/alphabot/gazbot7/data/router_headless.log` — each 5-min run logs there (no change / APPLIED / skip). This is the desk's floor; everything else is a bonus.
   **★ An active timer is NOT proof the router works.** Check `PINNED` in `scripts/router_tick_durable.py`
   too — a full-roster pin makes every tick a silent no-op that still logs "no change" (411 ticks / 36h
   went unnoticed on 07-31). If the last `APPLIED` line in the log is more than a day old on a trading
   day, suspect it.
2. **Do NOT arm a session 5-min tick cron** — it would DOUBLE-write `gate_switches.env` against the durable tick (two routers). The durable systemd tick owns the routine ticking now.
3. **Optionally arm the EVENT WATCHER** (fast-event oversight): `Monitor(command="/home/alphabot/gazbot7/.venv/bin/python /home/alphabot/gazbot7/scripts/router_watch.py", persistent=true, timeout_ms=3600000)`. It wakes you in-chat on events (read-only; dies with the session). Exception-texts-only. When it wakes you on a ROUTINE event, you may just observe (the durable tick handles it within 5 min); act directly only on a true exception (halt/naked/bleed).
4. **Session-only helper crons** (ledger review, hourly watch, sweep) still die on session exit — re-arm from `router_crons_manifest.md` if you want them; they're secondary to the durable tick.
2. **Read, thoroughly:**
   - `/home/alphabot/gazbot7/data/router_badcall_ledger.md` — the scored audit of past bench calls. Internalise the ❌/⚠ patterns so you don't repeat them.
   - `tail -50 /home/alphabot/gazbot7/data/router_trial_log.txt` — the recent tick-by-tick state + last switch changes.
   - Auto-memory `MEMORY.md` (already loaded) — especially [[router-tune-trial]] (permanent, mechanism), [[us-open-dont-bench-trend-rider]], [[rearm-momentum-needs-er-climb-not-delta-blip]], [[exhaustion-short-live-fader-success]].
3. **Verify desk health:** `cd /home/alphabot/gazbot7 && .venv/bin/python scripts/sweep.py --json` — flat/healthy/not-halted, capture fresh, no wedge.

## THE STANDING CRONS (re-arm any that are missing — see manifest for full prompts)

| Schedule (local=UTC) | Purpose |
|---|---|
| **systemd** `gazbot7-router-tick.timer` `*:0/5` | **★ DURABLE ROUTER tick** — the core 5-min loop, headless-Claude, survives session exit (NOT a session cron; do not duplicate) |
| **systemd** `gazbot7-nightly-audit.timer` `21:30 UTC` | **★2026-08-02 STANDING AUDITS** — `claim_audit.py` (what the operator's hands are worth vs what the machine would have done) + `nipc_replay.py` (NIPC's control: BLANKET vs HOME). Runs inside the CME halt. Durable, not a session cron. |
| **systemd** `gazbot7-gate-reactivate.timer` `00:00 Paris = 22:00 UTC` | **⚠ arms EVERY `=off` gate.** Operator policy: every gate re-arms at the midnight reopen and the router manages from there. A bench in `gate_switches.env` therefore only lasts until 22:00 UTC — a longer hold must go in `reactivate_gates.py::HOLD`, and it nearly armed a never-validated gate on the reopen minute. |
| every ~4h | **BAD-CALL LEDGER review** — read the ledger + grade recent switch-changes |
| `8 5-21 * * 1-5` | hourly TAPE/GATE watch (`hour_watch.py`, TIER-2 = ATTENTION GAZ) |
| `41 */3 * * 1-5` | 3-hourly FULL maintenance sweep (`sweep.py`) |
| `9 20-23 * * 0` | Sunday pre-open / open ramp |
| `22:43 / 22:50 wkdys` | nightly grind-exit shadow + router/selector review |

## HOW THE ROUTER DECIDES (the short version — full framework in the tick prompt)

Read `scripts/desk_view.py` (day-bias, ER/ATR, per-gate P&L, shadow, position) + `scripts/recent_trades.py` (live wall-of-STOP check) each tick. Regime read (trend/chop) drives it: **confirmed chop → bench ALL momentum, keep reversion**; **UP≥+40 → bench shorts / DOWN≤−40 → bench longs**; re-arm aligned momentum only on a **real break WITH ER climbing + vol expanding** (not a delta-blip). Judge footprint faders (exhaustion_short) on LIVE P&L, not their fixed-target shadow. Write on change → edit `gate_switches.env`, log to `router_trial_log.txt`, notify. **Benching is fully reversible** (blocks NEW entries only; opens still exit; stops untouched) — re-arm freely when evidence changes, but don't THRASH (that's the ledger's recurring lesson). Asymmetry: wrongly-benched = cheap (missed trades); wrongly-armed = expensive (churn) → when unsure, sit benched one more tick.

## DURABILITY CAVEAT (flag to operator)

These crons are session-bound + 7-day-capped. The truly robust "critical infrastructure" version is a **durable OS-level scheduler** (systemd timer / host cron that pings a headless Claude) so the router survives a session ending. Until that's built, keep this session alive and re-arm ~weekly. This is the #1 fragility.

## ★★★ DAY RIDER IS LIVE (PAPER) FROM 2026-08-06 — a SECOND desk, separate from the tournament

A new strategy runs **as its own service**, not as a tournament gate, and it places real (paper) orders.
`gazbot7-day-rider.timer` (every minute) + `gazbot7-day-rider-watchdog.timer` (every 2 min).
Switch: `data/day_rider.env` -> `day_rider=on|off`. **Currently ON.**

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
