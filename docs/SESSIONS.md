# GAZBOT V7 — SESSIONS

> **The changelog: what CHANGED, and what it was before.** Append-only, newest at the top. Every session that changed state gets a dated entry. This is the "how we got here" history — the current snapshot is **STATE.md**, the architectural "why" is **DECISIONS.md**.
>
> **Rule:** you never change STATE.md without adding an entry here in the same breath. An entry says: *what changed (A → B), why, and how to revert.*
>
> Older per-session detail (before 2026-07-12) lives in `docs/HANDOVER_1.md … HANDOVER_82.md` — this log starts at the go-live and supersedes the HANDOVER series going forward.
>
> **⚠ 2026-07-17: the live desk moved to GAZBOT V7 (`/home/alphabot/gazbot7`).** This `alphabot2` tree + its `alphabot.db` are now a RETIRED V5 research/history archive. Entries below 2026-07-17 are V5 history; V7 keeps its own changelog/docs under `gazbot7/`.

---

---

## ⚠ 2026-08-16 (Sun) — THIS LOG WAS DEAD FOR 17 DAYS. Backfill 07-31 → 08-16.

`STATE.md`/`SESSIONS.md`/`DECISIONS.md` were stranded in the RETIRED V5 tree
(`/home/alphabot/alphabot2/docs/`) while every change happened in `gazbot7/`. They stopped on
**2026-07-30** — the day the router was made permanent. Moved into `gazbot7/docs/` on 08-16 with a
pointer left behind. The entries below are a **condensed backfill** reconstructed from git, the
`SESSION_*.md` / `WEEKEND_*.md` docs and systemd; per-day detail lives in those docs, which are
authoritative where they disagree with this summary.

- **`docs/SESSION_2026-08-13.md`** — the day the books lied (2 incidents + the governing ruling)
- **`docs/SESSION_2026-08-15.md`** — the gold build, the audit, the shadow trim
- **`docs/WEEKEND_2026-08-01_CHANGES.md`**, **`docs/WEEKEND_2026-08-08_CHANGES.md`**
- **`docs/INCIDENT_2026-08-06_SHARED_ACCOUNT.md`**

---

## ⚠ 2026-08-18 (Tue) — CONFIG BOUNDARY: rider_w5 ran UNCAPPED, 08-17 13:25 → 08-18 17:49

**Do not pool rider_w5 data across this line.** Between those instants the arm ran with
`time_cap_s=0.0` — no clock — against a spec and a lab engine that both cap the hold at **120
minutes** (`gf_rider_engine.run_trades`, `i1 = min(n, i0 + cap_min * 12)`). Restored in `e95aca0`.

**The 10 trades in that window are VALID and were NOT voided.** Every one closed inside 60 minutes
(longest 60), so the 120-minute cap could not have altered a single entry, exit or dollar — each is
exactly what the correct config would have produced. Voiding faithful rows would be the opposite of
the operator's standing rule, *"do not book a loss caused by a system bug — LABEL, never adjust"*,
which cuts both ways. `data_quality` is deliberately left NULL on them: setting it makes honest P&L
filter them out, which is voiding by another name.

**What IS unusable from that window is the SAMPLE, not the trades:**
- One position at a time, and an uncapped trade holds until stop or target — so a slow trade blocks
  the session AND is not recorded until it closes. The set is conditioned on *closed quickly*: all
  10 are ≤60min, which reads as a property of the strategy and is partly a property of what survived
  to be written down.
- **At least one entry was lost outright.** On 08-18 the gate was TRUE on 32 minutes and produced
  ONE trade (against nine on 08-17); the inferred open position was cleared by the restart that
  deployed the fix and never produced a row.

→ **P&L of those 10 (−$288, −$28.80/tr, 2 wins) is trustworthy. Trade FREQUENCY, hold-time
distribution and anything per-session from that window are NOT.** Count trades toward the promotion
bar (+0.15R over 200 including a non-trending week) from **2026-08-18 17:49 onward**.

⚠ This is the SECOND constraint this arm shipped without — the 15-minute cooldown was the first
(restored 08-15, `05039e1`). Its own comment already said *"every number quoted for this leg came
from the CONSTRAINED version"*, and the other half was not checked at the same time.

## 2026-08-18 (Tue) — drift-persistence study queued for the halt (`gazbot7-driftlab`)

Operator: *"use our confirmation formula and go back 10 years of public MNQ data and see what % of
days once our thresholds are met how often does it stay in that direction"*, and *"do 10 years"*.

**Two constraints settled before building.** (1) **10 years of MNQ does not exist** — MNQ launched
2019-05-06. **NQ** carries the 10-year span (same index, same price, 1/10 notional), MNQ is pulled
over its own life as a cross-check that the two agree. (2) **10y cannot fit one halt** — IBKR paces
~60 historical reqs/10min and 1-min bars need one request per day (a larger `durationStr` returns a
SHORT result rather than an error — silent truncation that would read as thin days). ~2,500 requests
≈ 7h. So the job is **resumable**: one parquet per contract-month IS the checkpoint, it stops at a
50-min deadline and continues the next night. TradingView was ruled out — a charting front-end over
licensed CME feeds, no public bulk API, and scraping it breaches their ToS. Yahoo caps 1-min futures
at 7 days; Stooq is behind a JS proof-of-work wall.

**It shares the LIVE trading gateway**, so preflight refuses unless the desk is FLAT and the venue
HALTED — verified by test-firing the unit while the rider held a live SHORT (it declined). A refusal
exits **0, not red**: a unit sitting failed for behaving correctly is the alarm-outage pattern.
`MemoryMax=1G` on a 7.5GB box with three logged OOM kills — the desk wins any contention.

★ **Smoke-tested before queueing, and it found three bugs** — the Friday-report lesson that a job
judged only at run time dies unattended:
- `validate()` used an O(n²) correlated sqlite subquery; it **hung past 2 minutes** on one month of
  5s bars and would have wedged the job at 21:05. Now DuckDB `arg_max`.
- **This box has no `pyarrow`/`fastparquet`**, so `pandas.to_parquet` raises ImportError. Switched to
  DuckDB `COPY … (FORMAT parquet)` + read-back row count, the same mechanism `tape_mirror.py` uses.
- The confirmation scan ran to 21:00Z and reported **100% of days "confirmed"** — true and
  meaningless, since the rider cannot act after its **15:00Z entry cutoff**. Now bounded to it.

★ **The replay reproduces `drift.py`'s own number**, which is the check that it measures the right
thing: 24 of our sessions give **DRIFT_HELD 70.8%** against the docstring's **71% (22/31)**, median
confirmation at minute 10 — the docstring's stated sweep peak. It also separates two things the
docstring does not: **DRIFT_HELD** (close vs the 13:30 open, the 71% metric) from **ENTRY_PAID**
(close vs the price AT confirmation — what the rider, which enters there, actually lives). On the
same 24 sessions ENTRY_PAID to 20:40 is **66.7%**, ~4pp below the headline. Reported separately, by
year and by direction, because conflating them is how a study flatters itself.

Revert: `systemctl disable --now gazbot7-driftlab.timer`, delete the unit + the CLAUDE.md row.

## 2026-08-17 (Mon) — a false ATTENTION GAZ, and the desk day was never the UTC day

**07:08Z the hour-watch job told the operator to bench `exhaustion_short`** — "the only gate trading",
"net ~−$88 on the day", citing "its last 3 signals (18:41, 18:44, 19:43), all STOPs for −$133".
**The desk had taken ZERO trades that day.** Those were Friday 08-14's six A/B legs (−$133.5 exactly),
and at 07:08 the cited 18:41 had not yet happened. The operator caught it: *"but no ttades today"*.

The tape half WAS today's (day high 30326 ≈ its 30325), which is what made it convincing — a
mixed-source alert is worse than a wholly stale one. Its own wording gives up the mechanism:
*"its last 3 signals"* is an `ORDER BY closed_at DESC LIMIT`, no date floor, so a quiet morning walks
it back into the previous session. **Both tools its prompt sanctions reported the truth and were not
used** — `hour_watch.py` → `hour_trades: 0, day_net: 0, gates: [], escalate: false`; `desk_view.py` →
`DAY TOTAL +0.0`. The durable router read the SAME rows correctly the day before (*"residue, not a
wall"*) because its prompt carries a data contract and this one did not.

**NOT benched** — and not merely because the alert was wrong. By the time it was read the premise had
inverted: price 30263, **63pt below** the high, last 30-min net −35.75pt — the roll-over the fader
exists to catch had begun. And day-ER 0.07 / ATR 6pt is confirmed chop, where the standing rule is
*bench momentum, KEEP reversion* — `hour_watch.py` itself classes `exhaustion_short` as reversion.

→ **`ops/job_prompts/hour-watch.md`: a 6-point DATA CONTRACT at the top**, ahead of every step, per
the Friday-report lesson that a contract belongs in `PRE` so all phases inherit it. Trades come from
the two tools only · every query bounded by `paris_day_start_utc` · never `ORDER BY … LIMIT` · **zero
trades is a complete answer** · a dual-lot gate writes 2 rows per signal · never pair a live tape read
with another day's trades.

★ **The same class, worse, found next door.** `ops/job_prompts/nightly-review.md` scoped the day's
book with `date(closed_at)=date('now')` — the **UTC** day. The desk day is the PARIS day, 22:00Z →
22:00Z, and **22:00Z is the reopen**. So it misfiled every trade in the 22:00–24:00Z reopen window:
**41 trades / $368 across the book**, including 07-30's 8 trades / −$336, which IS the documented
reopen churn. Running at 22:43 it also swept in 43 minutes belonging to the next desk day.
Fixed to a derived two-ended Paris window (never a hardcoded +2h — that breaks at DST).
**VERIFIED against the desk's own record:** the corrected window returns 07-30 = **91 trades /
+$1,172.00**, exactly the "+$1,172 — best ever" in `router_badcall_ledger.md`; the old form said
**+$93.50**. A **$1,078 miss on one day** that had never looked odd.
⚠ My first attempt at the fix was WRONG — `-25h` produced a 48-hour window — and only running it
caught that. ⚠ DST 2026-10-25 moves the boundary to 23:00Z while the timer stays at 22:43 UTC; the
query stays correct, the TIMER needs revisiting. Logged in the prompt, not fudged.

Revert: `git revert <sha>`. Prompts only — no desk state changed, `exhaustion_short=on` throughout.

## 2026-08-16 (Sun) — GitHub was 18 days stale, and sweep called that healthy (`c58df56`)

**The find.** `refactor/three-service` was **207 commits / 18 days** ahead of origin; last push was
`d65596d` on 07-29. Local-only: the router made permanent, the 08-06 shared-account fixes, the whole
08-13 "the books lied" order-path rework, DECISION §362, BUILDs #3/#10/#12–#18. **B2 backs up
`gazbot7.db`, `shadow.db` and configs — NOT the source tree**, so on a 7.5GB box with three logged
OOM kills that was the desk one disk away from gone. Pushed (fast-forward, verified non-destructive:
remote had 0 commits we lacked, `merge-base --is-ancestor` clean).

**The instrument fault, which is the real entry.** `check_config_committed` asked *"is it
committed?"* and never *"did it leave the building?"* — it read `OK` green for all 18 days.
[[an-instrument-that-reports-healthy-about-something-it-does-not-check]], 8th instance.
→ sweep's config section now carries **`ahead_of_remote` / `upstream` / `unpushed_oldest_h`**, WARNs
once the OLDEST unpushed commit passes **24h**, and the OK line now NAMES both halves:
`live-behaviour files all committed · pushed @ <sha>`.
**No network call** — `@{u}` is the local remote-tracking ref, which git advances on push, so it
measures "committed here, never pushed from here" without a fetch (a network call in a check running
8×/day is a hang risk). Cannot see a push from another machine → over-reports, never under-reports.

★ **The red path was PROVEN on fixtures, and that caught a bug in the check itself:** the oldest-
commit age used the LAST LINE of `git log`, which is DAG order, not date order — one rebase or
amended date and an 18-day-old commit read as **2.0h** and the alarm stayed green. Now `min()`.
Fixtures: synced OK · 2h-unpushed OK · **18d-unpushed WARN** · no-upstream WARN · not-a-repo WARN.
Suite green (801), ruff clean. Revert: `git revert c58df56`.

**STATE.md §4 corrected in the same breath** (operator: *"its 34 mnq arms"*). It read "22 MNQ arms +
3 MGC", which merged two slates AND was stale the day it was written. Counted by CALLING both:
`default_slate()` = **34, all MNQ, zero MGC**; `mgc_slate()` = **3**, run by the separate
`gazbot7-shadow-mgc` into its own store, zero name overlap. 47→22 was the 08-15 trim; the 08-16 BUILD
commits then armed 9+ more. The "EIGHT of the 22 are losing on purpose" line was also a pre-builds
count — replaced with a VERIFIED FLOOR of nine named controls/live-mirrors plus the A/B and factorial
families, and explicitly labelled a floor rather than a census, because
[[a-control-is-supposed-to-lose]] began with a P&L sort putting the control top of a kill pile.

## 2026-08-16 (Sun) — the rider window was a phantom on every shadow arm (`be06ff1`)

Found while answering "is the rider armed for the whole US session or an hour and a half?" — a
question the code itself answered ambiguously, which is why it is worth an entry.

`ShadowVariant.rider_win_start_s / rider_win_end_s` defaulted to **13:00–14:45Z on ALL 34 arms**, but
only `_rider_entry` (`gate="clock_rider"`) ever reads them. `rider_w5` is `gate="board"` and trades
**13:00–20:00Z** via `hh_lo`/`hh_hi` in params — yet inspecting the arm showed `rider_win_end_s`
14:45, i.e. a 1h45m window on a gate that runs 7 hours. **CLAUDE.md trap #9** (a field carried but
read by nothing). The live danger was never the confusion: it is that "fixing" that arm's window by
editing the field it appears to carry would have been a **silent no-op**.

- `-1` now means UNSET. `__post_init__` fills the historical default for `clock_rider` and **RAISES**
  on any other gate, so the no-op edit is now a loud error.
- `_open_rider()` states the 14:45 cut explicitly at the definition site.
- **No behaviour change**, asserted via `default_slate()` not source: odr arms unchanged at
  13:00–14:45Z; `rider_w5` still 13–20 with `cooldown_min=15`. Full suite green (801).
- `gazbot7-shadow` restarted 12:35:30Z (it is long-running and does not pick up code).

Revert: `git revert be06ff1` + restart `gazbot7-shadow`.

~~⚠ Un-pushed~~ — **pushed**, see the entry above.

~~⚠ STATE.md §4 disagrees with the code~~ — **CORRECTED to 34**, see the entry above.

## 2026-08-16 (Sun) — project files restored; Friday report schedule made satisfiable

**Docs.** STATE.md rebuilt from the RUNNING system (the old one described one desk, 8 services and a
1.9GB capture.db; reality is three desks, 36 units, 5.3GB). SESSIONS/DECISIONS moved to
`gazbot7/docs/`. CLAUDE.md restored to instructional-only — it had absorbed desk state for weeks
because the real state files were stranded.

**Friday report (`c002f46`).** The 08-14 run built 5 of 17 sections and the tail died. Three causes:
- the `weekly_{WEEK}.html` doubled-brace filename (already fixed 08-15, verified today);
- **the schedule was never satisfiable and nothing checked it** — 17 body phases declaring **1,755m
  of timeouts against a 228m budget (7.7×)**. `rehab` took its full 90m cap (40% of the night),
  produced nothing, and starved the rest; `gf_MGC` got 13.2m of an intended 90 and also died;
- budget was first-come-first-served, so one phase could eat everything.
→ **PREFLIGHT** logs the ratio before committing · **FAIR SHARE** caps each phase at 1.6× the even
split (effective ~28m, not 240m) · **MIN_SLICE 20m** skips-and-logs rather than handing a useless
sliver · **ROTATION** runs 2 of 6 greenfield clusters per ISO week, dropped ones logged.
Revert: `git revert c002f46`.

## 2026-08-15 (Fri/Sat) — the gold desk, an audit, and the shadow trim → `SESSION_2026-08-15.md`

- **A GOLD ROUND TRIP CROSSES THE SPREAD ONCE, NOT TWICE.** `MGC_FEE_RT` 7.50 → **4.50**. The $7.50
  double-counted it, and I had used it to declare the **coil bouncer DEAD (−$454)** — at the true
  cost it is **+$8.42, breakeven**. The LAB never used the bad constant, so +$1,387/+$1,261 stand.
- **MGC SHADOW DESK LIVE** — `gazbot7-shadow-mgc`, own store, 3 arms incl. a no-book CONTROL.
  Separate store because `reprice_pending` uses ONE multiplier: sharing would price gold at $2/pt.
- **13 audit findings fixed.** Headline: the gate could NEVER have fired (`bar_lookback=60` vs a
  `look_min=60` needing 61). ⚠ #8 NOT closed — lab bars are depth-MID, production folds TRADE bars,
  only 41% of fires overlap.
- **SHADOW TRIMMED 47 → 22.** My first pass was a P&L sort and put `capit_loose` (−$11,292) top of
  the kill pile — it is the no-flip CONTROL. Revert: delete a name from `RETIRED_2026_08_15`.
- `exhaustion_short` → `direction_router.UP_OFF`; **nipc gates deleted**; `rider_w5` armed.

## 2026-08-13/14 (Wed/Thu) — the day the books lied → `SESSION_2026-08-13.md`

- **★★★ OPERATOR RULING: "ibkr is the truth ... never rely on our books. ever."** The rider sold **8
  lots it did not own** and booked **$1,551 of profit that never happened**; books said +$768.50,
  venue said −$25.50.
- Fixes: the `closed` guard, `venue_first_ok()` on every order path except the 20:40 hard flat,
  `CLOSED_ELSEWHERE`, `cancel_own_stops()` on all five close paths, the inverse audit.
- **`gazbot7-desk-reconcile.timer` (30s)** — the only thing that reconciles ACROSS both desks.
- **The durable router died for 10.5h on an expired OAuth token** while systemd said active →
  `gazbot7-router-health.timer`.
- **Backblaze is the record** → `data_inventory.py` + 4-hourly timer.
- Friday report rebuilt as **one phase, one process** (`serial_runner.py`).
- 08-14: rider fills gap closed, `book_vs_fills.py`, exit-price bug, alarm dedupe, MGC greenfield.

## 2026-08-05 → 08-12 — the second desk, the shared account, and the weekend rebuilds

- **DAY RIDER LIVE (PAPER) 08-05** — a SECOND desk, own clientId 4, `docs/DAY_RIDER.md`.
- **★ INCIDENT 08-06: THE ACCOUNT IS SHARED.** The rider flattened the ACCOUNT net without checking
  ownership → drift-halt with the whole safety block skipped → a leftover GTC stop opened a **naked
  short**. → `safety.own_flatten_verdict()`. ⚠ The `drift` safety-block skip is STILL OPEN.
- **ASIA (00-07 UTC) BENCHED PERMANENTLY** — `no_open_asia=True`, n=1840 at −$3.17/trade.
- **WEEKEND 08-08** — nine claims withdrawn; **NO GATE GETS AN ER FLOOR** (`ER_FLOOR = {}`);
  `abs_veto_short` exempt from the chop bench; run-state as a routing lever **WITHDRAWN**.
- **08-04: MD_STREAM IS MULTI-SYMBOL** — adding MGC made ATR read 1848 against a true 15 and opened
  live trades with $3,700 stops. Every consumer must filter on `body["symbol"]`.
- **WEEKEND 08-01** — quiet-tape clip live, `_base(slot)` fix, slate cut 28→18.

## 2026-07-31 → 08-04 — durability

Everything session-bound became systemd: router tick, router health, desk reconcile, the five
`claude-job@*` review jobs, the nightly supervisor, data inventory, the Friday report.
**Do NOT arm session crons** — they double-fire against the timers.


## 2026-07-30 (Thu) — later-3: ★★ DURABLE ROUTER SCHEDULER LIVE — the router now survives a Claude session ending.

The #1 fragility (everything session-bound) is fixed for the core tick. A systemd timer (`gazbot7-router-tick.timer`, every 5 min, User=root) runs `scripts/router_tick_durable.py`: a trusted wrapper gathers the desk state as TEXT, asks headless `claude -p` with NO tools (pure reasoning) for a JSON decision, then the wrapper applies it. FAIL-SAFE: any error / non-parse / invalid decision leaves `gate_switches.env` untouched (benching-only, PAPER, stops/safety untouched). Skips the 21:00–22:00 UTC CME maint halt; logs every run to `data/router_headless.log`.

- Why safe unsupervised: Claude has zero tool access in the durable tick (only reasons over text, returns a decision the trusted wrapper validates + applies); fail-safe defaults to no-change; benching a paper desk has bounded blast radius. Operator confirmed headless Claude has run this box for weeks.
- Verified: headless `claude -p` works; the full decision loop returned sound parseable JSON on live desk state (correctly held "dead chop, momentum already benched").
- The session 5-min cron was removed to avoid two writers on `gate_switches.env`; the durable systemd tick is now the sole routine ticker, the live session is oversight + the fast-event Monitor watcher.
- Revert/kill: disable the timer via systemctl → falls back to session/manual router; full revert = restore `gate_switches.env.pre-trial` + the mechanical direction-router timer.
- Remaining follow-ups: make the event watcher durable (own service invoking headless claude on an event); a daily 21:58 UTC all-6-open reset timer; the helper crons (ledger review / hourly watch / sweep) are still session-bound. Units under `/etc/systemd/system/gazbot7-router-tick.*`; manifest §0.

---

## 2026-07-30 (Thu) — later-2: ★ EVENT-DRIVEN ROUTER (Option B) LIVE + self-audit infra (bad-call ledger, session bootstrap).

Built the learning + always-watching layer on top of the permanent 5-min router:

- **Bad-call ledger** — `gazbot7/data/router_badcall_ledger.md`, a SCORED audit (GOOD/BAD/CHURN/NEUTRAL) of every switch decision, distinct from the raw tick log. Seeded with today's calls (GOOD 5 / BAD 2 / CHURN 1 / NEUTRAL 2). A ~4-hourly cron makes Claude read it + grade recent calls in $ (per-gate P&L or the gate's shadow-in-the-benched-window as the counterfactual). The systematic version of "document bad calls so I learn."
- **Session bootstrap** — `/root/CLAUDE.md` (loaded every session) + `gazbot7/data/router_crons_manifest.md` (verbatim cron prompts). A NEW session now re-arms the router tick + the event watcher, reads the ledger, verifies health. Pinned at the top of `MEMORY.md` too.
- **★ EVENT-DRIVEN ROUTER (Option B) — LIVE.** `gazbot7/scripts/router_watch.py` runs under a persistent `Monitor` (read-only, ~15s poll, debounced) and WAKES Claude in-chat on BREAK↑/↓ · REGIME→TREND/CHOP · WALL-OF-STOP · BLEED (drawdown from peak) · health-exceptions (⚠HALT/⚠NAKED/⚠FEED-STALE/⚠AUDIT-STALE). This is the fast layer on top of the 5-min heartbeat tick (kept as backstop). **Exception-texts-only:** the watcher wakes Claude in-chat, the operator is only Telegrammed on a real switch-change or critical exception. Operator gave licence to tune thresholds live (Telegram on change).
- **First-hour live tuning** (operator-authorised): regime detection got HYSTERESIS (was re-firing REGIME→CHOP on ER wobble near 0.10); FEED-STALE now suppressed during the 21:00–22:00 UTC CME maintenance halt (no ticks is normal then — was a false alarm); cooldowns added. Event→wake pipeline confirmed working end-to-end.

⚠ **Fragility:** all of this (router tick, watcher Monitor, review crons) is SESSION-BOUND — dies when this Claude session exits, + 7-day cron expiry. The real robustness fix is a durable OS-level scheduler (systemd/host cron pinging a headless Claude) — PENDING, flagged to operator as the #1 gap. REVERT the whole layer: TaskStop the Monitor + CronDelete the crons; the desk falls back to the mechanical auto-router via `gate_switches.env.pre-trial` + `gazbot7-direction-router.timer`.

---

## 2026-07-30 (Thu) — later: ★★ ROUTER MADE PERMANENT + BEST DAY EVER +$1,172 + exhaustion_short live-fader + new lessons + Claim button.

**Day closed a new best: +$1,172** (the +$586 in the earlier entry was a mid-afternoon snapshot). A ~+1,000pt up-day: strong US-open trend legs (grind rode +$234/+$197 targets, abs_veto +$294) → a long afternoon roll-over chop the router benched momentum through → an evening breakout to new day highs.

**★ THE ROUTER IS NOW PERMANENT.** Operator ended the trial framing — *"why would we wrap the trial. i want you in there ongoing. it works. i have heaps of claude credits i dont use because all the heavy building is done."* Actions: **cancelled the 21:55 UTC WRAP cron** (would have re-enabled the mechanical auto-router + deleted the tick), **re-armed the 5-min router tick** as an ongoing session-cron with the trial-wrap language dropped and the new lessons linked. Auto-router timer stays OFF indefinitely; Claude owns `gate_switches.env`. ⚠ Constraints: session-cron = dies if this Claude session exits + 7-day auto-expiry → **re-arm ~weekly** (check `CronList` if the desk goes quiet). REVERT = `cp gate_switches.env.pre-trial gate_switches.env` + `systemctl enable --now gazbot7-direction-router.timer`.

**Key findings today:**
- **exhaustion_short = a strong LIVE roll-over FADER** — armed as an operator trial in the afternoon roll-over chop (post-climax stall, buyer-absorbed drift): **4/4 winning lots, +$372.5**, operator claimed each via the Claim button. Its shadow `exhaustion_rev` was −$157 the SAME day → the fixed-8/12pt shadow **understates** the live gate (chandelier + Claim ride the fade body) → **judge footprint faders on LIVE P&L, not shadow.** Corrects the "marginal/relegation-watch" read. Memory [[exhaustion-short-live-fader-success]].
- **exhaustion `net_min=400` sweep (53 fires, `footprint_signal_net`⋈`shadow_trades`):** raising the floor above 400 HURTS (non-monotonic — 400–500 marginally +, the 500–800 middle band is the bleeder, 800+ small +). 400 stays as a floor; net-magnitude alone doesn't separate winners. Thin N — Friday deep-dive candidate (band-exclusion + collect more fires).
- **Two new router lessons banked:** [[us-open-dont-bench-trend-rider]] (the US cash open is structurally violent — don't bench the aligned trend-rider on open stop-outs when the day is cleanly trending; operator caught me benching grind at the 13:33 flush, re-armed it, grind rode +$234) and [[rearm-momentum-needs-er-climb-not-delta-blip]] (re-arm momentum out of chop only on a real break WITH ER climbing + vol expanding — a delta-blip + marginal range-top poke in ER~0 chop is the oscillation, not a resumption; operator caught a premature long-flip).
- **Full break→fail→re-break cycle proven live:** abs_veto (veto-gate) is the right gate for a *quiet* break — its 55s veto is 0-cost if the break fades (never fires into a fade), catches continuation if real. grind (churner, no veto) stays off unless ER≥0.35 sustains.
- **Claim-profit button LIVE** on `/v7/router` (PIN 9906) — PIN-guarded per-slot manual flatten via the safe `_flatten_slot` (idempotent, ledger-synced, cancels the stop). Proven in production (operator banked several floating-profit lots). Panel also reworked: holdings + chandelier moved to the TOP, prominent $ 6R-lock target on each chandelier card.

**Defensive-value measure** (operator asked "how much bleeding stopped"): trade-everything counterfactual (all shadow mechanisms unbenched) ≈ **+$153 breakeven** vs the routed desk **+$1,172**; the afternoon chop-bench alone avoided **−$398** of momentum churn (unbenched momentum shadows over that window). Honest: a chunk of the gap is trend offense + exits, not pure defense — the real test is still a no-trend chop-only day.

**Scheduled:** all-6-gates-open reset one-shot for the Paris-midnight (22:00 UTC) session open, then normal tuning resumes.

---

## 2026-07-30 (Thu) — ★★ Router trial DAY 2 — FIRST 2 GREEN DAYS IN A ROW EVER + momentum ER-floor tuning + `/v7/router` panel. (gazbot7 `9767c67`, `e58e1e0`.)

Router-tune trial extended (operator: "keep it going") to a **5-min cadence**, Claude managing the router by a holistic regime read. **First back-to-back green days ever: 07-29 +$638.5, 07-30 +$586.** A ~13-hour range-rotation (the day's bleed) kept momentum benched; the afternoon session-high breakout ran through abs_veto. The trial fed **real gate improvements**:
- **Momentum-long ER floors, backtested 10 days (`deciders.ER_FLOOR`, commit `9767c67`):** `grind_long` FLOOR **0.35 VALIDATED** — flips grind −$670→**+$58**/10d; REVERSES the 07-25 rehab that dropped grind's floor (trend-week vs rotation-day finding); the mid-ER band 0.20–0.35 (rotation legs that look trendy) was the killer (−$431 @18% today). `abs_veto_long` set to 0.25 by operator, but the same backtest **DISPROVED it (−$121)** — abs_veto's 55s absorption-veto IS the filter, so an ER floor removes its low-ER veto-caught winners (bimodal: wins <0.25 AND ≥0.35, loses only 0.25–0.35) → **RECOMMEND revert to no-floor** (or a mid-band exclusion, ≈+$460, a code build). Revert = edit ER_FLOOR + restart flat.
- **abs_veto (veto) = the reliable momentum gate; grind (no veto) churns** — even floor-gated, grind buys into resistance/stalls. 07-30 live: **abs_veto +$630 vs grind −$53**. Lesson: run momentum through abs_veto, keep grind mostly benched; grind needs a veto/absorption-check, not just an ER floor.
- **Built `/v7/router` dashboard panel** (`web.py router_json` + `web_static/router.html`, `e58e1e0` + brightness/Paris-time tweaks) — multi-clock regime (the "why chop at ER 0.30?" answer: 30-min leg-clock vs day-clock), per-gate on/off + auto-derived reason, shadow-family cross-check, timestamped activity stream (Paris time), 2-slot holdings. + `scripts/recent_trades.py` (live bleeding check: exit_reason wall-of-STOP). Dashboard-only restart.
- **Dual-slot scale-out proven REPEATEDLY** — 5 dual-profit exits (Lot A TARGET + Lot B CHANDELIER both green): +$163/+$111/+$146/+$72/+$251 (abs_veto_long, mirror of yesterday's abs_veto_short +$768).

Memories [[router-trial-day2-findings-0730]] [[er-favourable-condition-gate-live]] [[dual-slot-scaleout-live]]. ⚠ N-small/one-regime; the backtest is a reprice-by-removal LEAD → needs multi-regime validation + the abs_veto mid-band-exclusion build for the Friday report. Revert trial = `cp gate_switches.env.pre-trial gate_switches.env` + re-enable direction-router timer.

## 2026-07-29 (Wed) — ★★ DUAL-SLOT SCALE-OUT deployed live (+$768 first win) · router-tune trial · orphan-stop incident. (gazbot7 `5b0913b` + `d65596d`.)

Huge day. Full arc: a router-tune trial (Claude as intelligent router, benching on day-directional-bias) → a give-back investigation → the dual-slot scale-out build+deploy → an incident → the scale-out's first live win.

- **★★ DUAL-SLOT SCALE-OUT — LIVE (gazbot7 `5b0913b`, slate `scaleout`).** Every gate → TWO 1-lot sub-slots that fire on ONE signal: **Lot A** fixed-R scalp (guaranteed floor), **Lot B** chandelier (ride the tail). BIG-RUN gates (grind_long, abs_veto_short/long, exhaustion_short) A@2.5R + B wide lock-chandelier; FADERS (rgv_short, capitulation_long) A@1.5R + B tight k1.5. `slot_strategy.scaleout_slots()` (12 sub-slots via `replace()` off tournament_slots — one source of truth); `tournament._base()` strips `_A/_B` so benching/55s-veto/exh-confirm key on the base gate. Env-switchable (`GAZBOT7_TOURNAMENT_SLATE=scaleout`, systemd drop-ins on tournament+web). +7 tests. Dashboard shows _A/_B as separate holding cards (A banks → card closes → B keeps ticking). **★ FIRST WIN: abs_veto_short A+B = +$768 in one trade (A +232 floor + B +536 tail)** — the design proven live. Debut fire lost (exhaustion A+B −166 whipsaw). **Revert: slate back to `tournament` + restart.** Memory [[dual-slot-scaleout-live]].
- **★ The give-back research that produced it.** Exhaustion monsters are fat-tailed (MFE median ~6R, tail to 60R); the wide lock-chandelier never tightened (lock_r=6 unreachable) so a +$292 monster gave back to +$22. Sweeps proved **tightening the single trail LOSES money** (tail dominates) → scale-out is the web-consensus + data answer. ★★ **BACKTEST EXITS ARE UNRELIABLE ON THIS DESK** — every tick-reprice overstated/understated live by 5-10× (validation failed both ways); measure exits LIVE or via the honest shadow repricer, never a fresh backtest. Scripts: `peak_distribution.py`/`lotA_optimal_r.py`/`exhaustion_scaleout_analysis.py`/`exhaustion_giveback_sweep.py`/`exhaustion_scaleout_sim.py`.
- **★ Dashboard scoreboard fix (gazbot7 `d65596d`).** `tournament_json` roster was hardcoded to the 6-gate `tournament_slots()` — the live scaleout `_A/_B` sub-slots were invisible, so the scoreboard didn't add up (the +$768 win hidden, abs_veto_short showed only pre-deploy −135). Fix: roster follows the live slate + unions any gate that actually traded. Verified scoreboard +$638.5 == header +$638.5.
- **★ ORPHAN-STOP INCIDENT (recovered).** A leftover resting BUY-stop @27697 (no position) from a mid-day flatten-tangle survived restarts; an up-bounce triggered it → bought a phantom +1 long → drift-HALT. Cached book said flat (blind); venue truth = +1. Recovered clean: flatten (pre=1→post=0) → verify `slot_positions` ledger EMPTY + venue flat → restart → un-halted. ROOT GAP: **no orphan-order cleanup on boot** (bug to build). Lesson: a targeted order-CANCEL is safe (≠ eod_flatten) — don't over-hesitate. Memory [[orphan-stop-phantom-incident]].
- **Router-tune trial (operator-authorized, one-day):** Claude benched gates on day-directional-bias every 15 min (auto-router OFF). Verdict: the day-bias veto WORKS on directional days (kept the desk out of the long-book shadow bloodbath — capit −770/rg_long −557 avoided; desk green) but THRASHES on a zero-ER chop round-trip (this afternoon: −526→+49→−150, whipsawed benching). Key learning: split MOMENTUM longs from REVERSION longs in the bench (grind/abs_veto want an up-move; rg/capit bleed). WRAP cron (21:55 UTC) scores it + re-enables the auto-router. Trial log `data/router_trial_log.txt`.

## 2026-07-26 (Sun, later-2) — ROUTER STUDY tool built + wired as a weekly Friday section; finding: router is NOT blocking enough losers. (gazbot7 `747485d`.)

Operator: *"can we optimise the router? is it blocking enough [losers]? this has to be a Friday night study each week — pull it apart, all timings, threshold triggers, make it better."*

- **New `scripts/router_study.py`** (READ-ONLY): reuses the live `direction_router` signal via a fast replay **asserted identical** to `replay_marks` (no drift). On realised MNQ trades over `--days`: (a) **threshold sweep** ER_TREND×NET_MIN, (b) **timing sweep** step/hold/window/fast_exit + full-grid joint-best with per-day robustness, (c) **"blocking enough LOSERS?" leakage diagnostic** — classifies the managed faders' *allowed* losers into counter-trend NEAR-MISS (trigger too strict → lower it) / genuine CHOP (router can't help) / trend-following (gate-exit problem). Runs on both the live-managed {capitulation_long, rgv_short} and full-historical (+rgv_long, +exhaustion_short) fader sets.
- **Finding (40d, one summer RANGE regime):** the router was **NOT blocking enough** — it blocked only −$152 (live) / −$736 (hist) of counter-trend loss but **LEAKED −$641 / −$1,453** of counter-trend near-miss losers because the trigger (ER≥0.25, net≥40) was too strict → mild-but-real trends read as CHOP and the faders bled into them unblocked. **Both sets agreed the fix = LOOSEN the trigger.** The full-grid best pins EVERY knob to its loosest edge (ER0.15/net20/window45/step5/hold3, +$900 vs shipped) = a **grid-edge overfit tell** → NOT deployed.
- **★ DEPLOYED tonight (operator directive: "deploy your smooth recommendation now; we'll optimise again next weekend if the theories hold"), gazbot7 `1ffb086`:** the MODERATE, evidence-backed loosen — **`ER_TREND` 0.25→0.20, `NET_MIN` 40→30** in `direction_router.py` (ER0.20/net30 = +$116 hist / +$24 live at shipped timing, smooth gradient both sets agree). **STEP left at 15** deliberately — no isolated evidence step=10 helps at these thresholds, and STEP must stay aligned to the 15-min timer (a bare change would misalign the mark-grid); measure it next weekend. Stateless oneshot router picks up the new constants on the next timer fire; smoke-run clean (HOLD, market closed). Fixed the `fast_exit` fixture (was tuned to the 0.25/40 boundary → slow-recovery V-shape, still strict `down_fix < down_now`). Full suite 443 green. **Revert: `ER_TREND=0.25, NET_MIN=40.0` + (auto-applies next fire).** ⚠ one-regime; re-validate after a real TREND week.
- **Wired** as the STANDING WEEKLY ROUTER OPTIMISATION in `scripts/friday/friday_v7_maxdepth.workflow.js` (`part25:musings`, after the existing architecture interrogation). Prior related tools kept: `router_architecture_ab.py` (plumbing A/B), `router_arch_sweep.py` (step×hold). Also confirmed earlier this session: adding `exhaustion_short` to UP_OFF = $0 (0 up-trend fires, structural — see memory `router-exhaustion-short-null`).
- **Revert (whole session-2):** `git revert 1ffb086` (thresholds back to 0.25/40) + `747485d` (tool + Friday section).

## 2026-07-28 (Tue) — ★ GUARD-AS-PRIMARY (kills the residual STOP_UNFILLED) + nightly router/selector review tools + all crons re-armed. (gazbot7 `d0218c6`.)

- **★ GUARD-AS-PRIMARY — LIVE (gazbot7 `d0218c6`).** The concrete-Future fix (07-27) cut STOP_UNFILLED ~18%→~11% but 2 residual recurred (both abs_veto) — IBKR PAPER still intermittently won't fire a resting stop's trigger even on the concrete contract (verified: stop on `Future(conId=793356225)`, yet `PreSubmitted/whyHeld='trigger'` → cancelled after price crossed). So we STOPPED relying on it: `MultiSlotCore.note_price` runs `_check_stop_breach` EVERY tick (~1s), flattening AT the stop after a 2-tick spike-guard (~2s, was ~10s) and booking **`STOP`** (retires `STOP_UNFILLED`). Native `StopLimitOrder` stays a backup; 5s audit loop a 2nd backstop; `_flatten_slot._closing` latch = idempotent. Stop path now deterministic regardless of IBKR paper. +tests, suite 449, restart clean. Memory [[stop-unfilled-contfuture-root-cause]]. Revert `git revert d0218c6`+restart.
- **capitulation_long base_size 2→1 (gazbot7 `c67da44`, operator).** 07-28 a fast pre-open drop split its 2-lot stop (1 at the trigger, 1 −28pt deeper on a market fill) → −$147; capitulation is the gate most exposed to fast directional drops (fades a knife), so halve the exposure. Edge intact (require_flip). Revert: base_size 2 + restart.
- **★ ROUTER US-OPEN WINDOW OVERRIDE (gazbot7 `ed0b247`, LIVE).** Operator: ensure momentum gates aren't benched at the 15:30 Paris (13:30 UTC) US cash open — that's when the big directional RUNS happen. Added `OPEN_WINDOW_UTC=(13:15..14:00)` + `in_open_window()`; `run()` subtracts CHOP_OFF during it → momentum gates stay ON across the open even if the pre-open read chop (the 13:15 mark un-benches ~15 min early). Faders stay regime-managed. Paired CHECK CRON `2f659bf0` (weekday 13:25 UTC): runs router + verifies momentum on + desk-ready + pings. +3 tests, suite 451. Memory [[direction-router-live]]. Revert: drop the block. **The full standing cron set is now SIX** (V7_MAINTENANCE_SWEEP.md updated).
- **★ NIGHTLY ROUTER + SELECTOR REVIEW (gazbot7 `1607e0b`/`4f38de8`/`d1240d0`).** `scripts/router_nightly.py` (was-it-optimal / block-adequately / miss-good-trades — reprices each SUPPRESSED-OPEN + leakage) + `scripts/selector_nightly.py` (% optimal exit-mode picks + regret + selector-vs-fixed). Weekday 22:50 cron (SESSION-ONLY); folds into Friday `part25:musings`. Initial reviews: router 07-27 net −$81 (capitulation over-benched) + −$456 momentum-in-chop leakage (the veto now plugs); selector 07-27 53% optimal / +$1342 regret / +$671 vs always-scalp (wide-in-violence + tight-on-runners the misses). Memory [[nightly-router-selector-review]].
- **All 5 maintenance crons re-armed** (fresh 7-day clocks) — the Sunday RAMP had silently LAPSED (Globex reopen unwatched); restored. `V7_MAINTENANCE_SWEEP.md` updated to document the full 5-cron set (was 2) so a session restart re-arms all. gazbot7 `014a5a1`.
- **Overnight 07-27→28 GREEN +$141.5** (2/2 winners, both CHANDELIER); momentum-chop veto did its full cycle (benched in the 01:00 chop, released into the trend). Exit-selector printing green chandeliers (6/6 since live, +$217).

## 2026-07-27 (Mon) — STOP_UNFILLED root-caused + FIXED (concrete Future) · regime-3-exit selector LIVE · exit-selector + router-study tools. (gazbot7 `da98af0` + `4351279`.)

Long live-desk session. Three shipped changes + two research tools; all verified in production (paper).

- **★ STOP_UNFILLED root-caused + FIXED + VERIFIED (gazbot7 `99e3c11`→merged `4351279`).** Symptom: ~18% of stop-exits booked `STOP_UNFILLED` (4/4 overnight abs_veto ≈ −$200). Root cause (venue truth from the tournament journal): the desk rested its `StopLimitOrder`s on the continuous **ContFuture**, and IBKR intermittently never FIRES a resting stop's trigger on a continuous contract — the order sits `PreSubmitted/whyHeld='trigger'` with price 10s+ past the level, so the breach-guard market-flattens (=STOP_UNFILLED, bounded ≈1 ATR). §352 fillable-limit was intact; the trigger upstream never fired. **NOT abs_veto-specific, NOT the money leak** (the guard bounded every loss). Fix: rest stops on the concrete front-month **Future** (qualified off the ContFuture conId — same conId, positions/naked-audit reconcile; entries/exits stay ContFuture). `IBBrokerAdapter.stop_contract` + `tournament._build_live`. **VERIFY PASSED live** — a native stop triggered + Filled at the trigger; since deploy: 11 clean `STOP`, 0 new `STOP_UNFILLED`. Merged to live branch. Memory [[stop-unfilled-contfuture-root-cause]]. Revert: `git revert`.
- **★ REGIME-3-EXIT SELECTOR — LIVE roster-wide (gazbot7 `da98af0`).** Operator: "put it live into paper." Every gate picks its exit WIDTH by the router regime at entry (frozen for the trade): **aligned-trend → WIDE** lock-chandelier (start_k3.5/lock_r6/lock_k0.5) · **chop → TIGHT** k1.5 · **counter-trend → k2.0**; native 1-ATR STP owns the loss. `SlotSpec.adaptive_exit` (default False = per-gate revert), `_regime_mode(side,bars)` mirrors direction_router's ER/NET (no drift), stamped at OPEN. Backed by `scripts/exit_selector_sweep.py` (tick-honest, 260 entries 07-20..27): swept chandelier width tight→wide; per regime winners unambiguous (aligned→lock +$2382, chop→k1.5, counter→k2.0); **regime-only selector beats best fixed exit +$756 OOS / 6-of-7 LODO days**; per-gate×regime OVERFITS (−$512 OOS) → regime-only used. ⚠ aligned-wide magnitude leans on today's ONE trend day — forward-validate. +3 tests. Revert: adaptive_exit False + restart. Memory [[exit-selector-regime-live]].
- **★ ROUTER MOMENTUM-CHOP VETO — LIVE (gazbot7 `56ef119`).** Operator ("the router knows it's chop, it should bench the trend gates"): added `CHOP_OFF={grind_long, abs_veto_long, abs_veto_short}` — the router now benches the MOMENTUM gates in CHOP (symmetric to faders-off-in-trends). Validated on realised 07-20..27: momentum book −$757 in CHOP-regime@entry vs +$18 in TREND, robust (chop bled them 5/7 days; grind_long −$598 chop vs −$16 trend). Directly fixes today's −$195 grind/abs_veto chop bleed (analysis: all 8 of their losers fired in CHOP, 0 in a benchable trend — a chop problem, not directional). Deployed at the CME daily-halt so the router HELD on stale feed; applies on the overnight Globex reopen when it reads live chop. Memory [[direction-router-live]], [[regime-chop-veto-momentum]]. Revert: drop CHOP_OFF or disable the router timer.
- **★ Today (07-27) = the first real TREND day** (−563pt violent down-flush then violent chop). Live proof-points: the loosened router benched capitulation_long correctly on the down-leg + released it on the chop; the ContFuture stop-fix verified; the exit-selector's whole thesis (chandelier rides trend / scalp-tight banks chop) played out in one afternoon. exhaustion_short machine-gunned (no cooldown) — net-green on the trend, chewed in the chop; day ended ≈ −$56.
- Also: `scripts/exit_selector_backtest.py` (the first 2-way version), and the abs_veto exhaustion-chase finding flagged in the Friday scope (`c81f178`). Earlier same day: router loosen 0.25/40→0.20/30 (`1ffb086`, §357-adjacent) + `scripts/router_study.py` weekly tool wired to Friday (`747485d`).

## 2026-07-26 (Sun, deploy) — ✅ grind_long threshold-chandelier DEPLOYED to live paper (§356 executed). (gazbot7 `afe030c`.)

The scheduled Sunday deploy (operator-approved 07-25, deferred off Saturday night to dodge the IBKR-maintenance restart-hang). Executed `GRIND_CHANDELIER_DEPLOY_SCOPE.md` exactly, at the §356 fine-sweep config (lock_r **6.0**/lock_k **0.5**, NOT the older 4.0/0.75 — re-read the scope pre-deploy, no operator override present).

- **What changed (A → B):** `grind_long` exit `scalp` (target_r=2.0) → **`chandelier_lock` (start_k=3.5, lock_r=6.0, lock_k=0.5)**, give-back stays off, ATR≥24 + no-ER floors unchanged. **`abs_veto_long`/`abs_veto_short` untouched** (keep scalp-2R — no chandelier beats their fast-2R edge shape). All other gates unchanged.
- **Code:** new `deciders.exit_chandelier_lock` — holds a wide `start_k·ATR` trail until `peak_r ≥ lock_r`, then STEP-LOCKS to a firm `lock_k·ATR` trail; uncapped, profit-only (native 1-ATR STP owns losses). `slot_strategy.SlotSpec` gained `lock_r`/`lock_k` fields + import + a `_manage` branch. grind_long SlotSpec switched. +5 unit tests (loose-hold below lock_r, firm-lock past lock_r, loss-floor, dormant-before-green, short mirror). Full suite **443 green**, ruff clean.
- **Deploy:** §5 pre-deploy snapshot taken; confirmed flat + healthy + gateway active (market closed, 18:13 UTC, reopen 22:00) → `sudo systemctl restart gazbot7-tournament` — **clean, no hang, NRestarts=0**. Startup `slots=['grind_long','capitulation_long','abs_veto_long','rgv_short','exhaustion_short','abs_veto_short']`, healthy/flat/place_live true, auditor fresh. Verified deployed config live via `tournament_slots()`. Committed src/+tests only (not the dirty Friday-report artifacts), pushed `refactor/three-service` `5d0bf11..afe030c`. Operator pinged (Telegram, critical).
- **Why:** §356 — threshold-chandelier captures grind's trend tail (+$1,782 full / +$747 wk30, tail-cap 63%, whipsaw 16%, robust 15/15 LODO); the only exit that beats scalp-2R on grind. ⚠ in-sample, one summer RANGE regime, +$508-over-scalp leans on ~a dozen big-ATR runs → a bet on trend days. The `two_ratchet_shadow_watch.py` + `partial_shadow_watch.py` watchers (§356/§357) are the read-only eyes on it through the first real trend week.
- **Revert:** grind_long back to `exit="scalp", target_r=2.0, stop_atr_mult=1.0` + restart `gazbot7-tournament` (or `git revert afe030c`).

## 2026-07-26 (Sun, later) — "can we capture MORE of grind's tail?" — regime-exit NULL, 2R-partial shadowed, This-Week's-Gates one-pager in Reports tab (DECISIONS §357). (gazbot7 `892cdc5`.)

- **★ Regime-conditional exit = NULL:** no entry-observable label predicts the ≥4R tail — the live router's own trend rule AUC **0.494**, and ATR runs the WRONG way (ATR≥28 reaches 4R *less*, AUC 0.414, killing the "40-ATR = tail" prior). The lone +$248 combo never tightens + is a 2-day overfit (strip-2 → −$120). **This closes the "capture more" question:** the tail is unpredictable at the decision moment from every variable we capture (price-path ×3 + regime + AUC) — the ~37% give-back is the irreducible price of the loose trail. Do NOT deploy/shadow.
- **★ 2R-partial = REAL but a VARIANCE lever, not a mean-raiser** (the only surviving lever): base_size=2 → Lot A scalp-2R + Lot B chandelier. target_r=2.0 = daily-vol −29%, maxDD −24%, worst-day −34%, wk30 +$82, for a ~$665/3wk mean give-up (entirely the tail forfeit on the 17 runners, ~75% offset by reverser gains). A mean-vs-smoothness CHOICE, not a fix. **SHADOWED** (`scripts/partial_shadow_watch.py` → `data/partial_shadow.json`, combined daily cron 22:43 with the two-ratchet watch, wired into Friday Part 2). Validated 07-19..25.
- **★ "This Week's Gates" one-pager** in the dashboard Reports tab (`web_static/gates_2026-07-27.{html,pdf}`; `reports_json` recognizes the `gates_` prefix) — theme-aware HTML + 1-page landscape PDF, the 6-gate roster (type / how-it-works / trigger / anti-bleed filters / ~1-wk tested P&L). Cross-device reference via the dashboard.
- **★ OPERATOR DIRECTIVE (reinforced):** the Friday report needs a WHOLE dedicated live-desk **Rehabilitation** section on rehabbing gates/exits that don't work — *or at least the honest TRYING* (the NULLs like regime-exit/two-ratchet are graves worth showing). Extends the §355 rehab rule from per-gate bits to a headline section. → wired as a dedicated 'Rehab' phase in `friday_v7_maxdepth.workflow.js` + scope. REVERT: `git revert 892cdc5` + remove the Rehab phase.

## 2026-07-26 (Sun) — grind chandelier lock_r fine-sweep (→6.0), dashboard winner/loser/delta, two-ratchet exit rejected + shadowed (DECISIONS §356). (gazbot7 `73ae1f7`.)

- **★ lock_r fine-sweep → deploy 6.0/0.5 not 4.0/0.75:** swept lock_r{3–8}×lock_k on the tick-honest engine — best start_k=3.5/lock_r=6.0/lock_k=0.5 = **+$1,782 full / +$747 wk30** (+$156/+$200 vs the 4.0/0.75 incumbent), whipsaw 23%→16%, robust 15/15 leave-one-day-out. Operator's 4.5–5R hunch is a ~$460 TROUGH (peakers ride the wide trail and give it back). `GRIND_CHANDELIER_DEPLOY_SCOPE.md` + the 18:07 UTC one-shot deploy cron both updated to 6.0/0.5 (grind_long still deploys tonight, pure-6.0). REVERT: back to 4.0/0.75 in the scope + cron.
- **★ Dashboard winner/loser/delta** (`73ae1f7`, gazbot7-web restarted): the tournament scoreboard now shows week-to-date **W$ (avg winner) / L$ (avg loser) / Δ** per gate, with expectancy + W/L counts in the Δ tooltip (`web.tournament_json` + new `pnl.paris_week_start_utc`; app.html/js/css). The low-win-rate/big-winner lens for the chandelier (net = W·avg_win − L·avg_loss). Live data already shows the trap: grind Δ +$7 yet expectancy −$12.9/trade (2× more losers). +1 test. REVERT: `git revert 73ae1f7` (dashboard hunk) + restart gazbot7-web.
- **★ Two-ratchet exit REJECTED (3rd time) then SHADOWED:** operator's *"big chandelier + a 2nd mop-up ratchet for the 3.8s that turn back"* — studied on the 6.0 primary. Best zero-clip config (arm4.0/disarm4.5/b_k1.25) = +$422 but a MIRAGE (wk30 Δ $0, strip-3 $0, 3 trades/2 days, +$123 of it a hidden clip of the 07-17 3.9→0.93→4.2 wobbler that ran to 6.75R). ~$299 cleanly claimable = no better than the $350 at lock_r=4.0. → pure-6.0 ships tonight unchanged; two-ratchet NOT promoted. **SHADOWED** via `scripts/two_ratchet_shadow_watch.py` (read-only clip-watcher → `data/two_ratchet_shadow.json`, daily weekday cron 22:43 `--ping`) **wired into the Friday pipeline** (workflow Part 2 + `FRIDAY_V7_REPORT_SCOPE.md` Part 2) as the durable home. Validated on 07-19..25 (36 trades, 0 clips, rode a 6.99R runner clean). REVERT: remove the Part 2 additions + delete the watcher/cron.
- ⚠ all in-sample, one summer RANGE regime; the two-ratchet shadow watch is specifically for the first real TREND week (the one thing the range archive can't produce).

## 2026-07-25 (Sat) — ★ WHOLE-ROSTER GATE REHABILITATION + abs_veto promotion + exit root-cause (DECISIONS §355).

Operator rule that anchored the day: *"never bench a gate at face value — if it's not working, HOW can it work."* Applied to all 6 gates; 4-for-4 rehabilitatable.

- **★ abs_veto promoted; thrust_short + rgv_long OUT** (`eb57f64`): roster gained `abs_veto_long`/`abs_veto_short` (two-sided thrust + a 55s absorption-VETO implemented in `tournament.run()` `deciders.VETO_GATES`, base_size=1; per-side chop-floor LONG ER≥0.20 / SHORT ATR≥16), REPLACING `thrust_short` (superseded) + `rgv_long` (worst performer). Engine-truth +$1,340 both sides, reconciled 79/79 penny-exact vs the shadow engine. REVERT: restore the old `tournament_slots()` return block + remove the VETO code/constants.
- **★ Whole-roster rehab deployed** (`6f74a32`): **rgv_short** — fast_turn was firing on noise (−$3,543/505 junk trades) → fast_turn OFF + ATR floor 13→20 = **+$778, robustness-passed** (own `_RGV_SHORT`). **grind_long** — scalp-2R (beats chandelier on the range archive) + ATR 20→24 + DROP the fake ER floor + give-back off = **+$1,118**. **capitulation_long** — `require_flip=True` (wait for buyers to step in = the real edge; the LIVE `False` was fading the climax = −$1,173) + give-back off + DROP the bug-based ER ceiling = **+$683**. REVERT: per-gate in the SlotSpec/deciders.
- **★ rgv_long revived → then swapped for exhaustion:** revived live with a new in-gate net30-depth floor (`9f51631`; skip the LONG fade when the trailing-30-min move < −125pt — the only thing that marginally separates its falling-knives from its flush-bounces, AUC 0.64) → then **SWAPPED OUT for the rehabbed exhaustion_short** (`bc81958`; exhaustion is the more-robust revive — n=83, green in wk29 where rgv_long fails; uncorrelated edges). Roster back to **3L/3S**. rgv_long's `_RGV_LONG`+`net30_floor` kept in code for a possible shadow.
- **exhaustion_short revived** via a NEW `exit="fixed"` type (`deciders.exit_fixed`: fixed 8pt-stop/12pt-target = its original FootprintShadow design; the generic ATR-2R scalp was too wide for a snap-back fade), give-back off, ER ceiling dropped. Edge = FLOW-ABSORPTION, not the ask wall.
- **Two ER ceilings were BUG-BASED** (capitulation 0.10 + exhaustion 0.05, both from `scripts/footprint_backtest_duck.py`'s DuckDB float-division bug `ts/5000*5000`) → `ER_CEIL` now empty; ER-hold shadow moved to abs_veto_long. Tool flagged for a fix/re-derivation.
- **Exit architecture root-caused (analysis):** give-back (dollar ratchet) = misaligned ON/OFF + a qty-roulette DESIGN FLAW (dollar arm → point/ATR-scaled is the fix; it's a momentum tool). Chandelier = the momentum tail beyond 2R is real (52% of profit), tightening `start_k` is a TRAP, and the operator's threshold chandelier (loose to 4R then firm-lock 0.75) beats scalp-2R on grind **+$508**; abs_veto keeps scalp-2R. **grind chandelier QUEUED for Sunday** (`gazbot7/GRIND_CHANDELIER_DEPLOY_SCOPE.md`; one-shot cron).
- **★ Sat-night IBKR maintenance incident:** a restart hung on position sync (systemd timeout → crash-loop) — recovered via clean `stop` → ~15s wait → single `start`. **RULE: no restart-deploys on Saturday nights.** Weekend maintenance crons made weekday-only.
- **NEW LIVE ROSTER (3L/3S, all reconfigured):** `grind_long · capitulation_long · abs_veto_long` — `rgv_short · exhaustion_short · abs_veto_short`. Full suite green throughout; every change committed + pushed. ⚠ ALL in-sample, one summer RANGE regime, small-n on several — watch forward vs the still-running shadows.

## 2026-07-22 (later 2) — Stop-fix CONFIRMED live · dashboard freeze fix · capture.db retention.

- **★ Stop-fix CONFIRMED (§352 caveat cleared):** the fillable StopLimitOrder works end-to-end. A fresh `grind_long` stop echoed `lmtPrice` 20pt BELOW the trigger (our limit — IBKR kept it, not its toothless above-trigger one), and the 14:16-hour's 4 stops all exited as `STOP` (filled) with ZERO `STOP_UNFILLED`. The toothless-stop class is fixed, live-verified.
- **Dashboard freeze fixed** (`85b572c`): the single-threaded web server blocked on a slow `capture.db` query → the whole page froze (JS fetches never returned). Now `ThreadingHTTPServer` + 30s client timeout; handlers open per-request DB conns → thread-safe. 5 concurrent requests verified, web tests pass.
- **capture.db retention** (`4ec9f56`): 79M-row L2 `book` = 5.3GB unbounded (~0.75GB/day) → slow queries + disk 88%. `scripts/prune_capture.py` batched-deletes old rows (book 3d / quotes 5d / ticks 7d) with a per-batch WAL checkpoint (no disk spike) + drops leftover tmp tables → caps growth; nightly `gazbot7-capture-prune.timer` at 21:15 UTC (CME halt). `scripts/vacuum_capture.py` reclaims the file (guarded, in-place, harmless on busy) — one-time `gazbot7-capture-vacuum.timer` tonight 21:20. First prune: 38M rows in 43s, desk unaffected.
- **First green tape (14:16 UTC):** grind_long fired 5× on a real ATR≥23 up-trend (its big-trend-day role) — floors held it out of the chop, then let it trade the trend; stops filling normally.

**Revert:** web threading `git revert 85b572c`; retention `git revert 4ec9f56` + `systemctl disable --now gazbot7-capture-prune.timer gazbot7-capture-vacuum.timer`.

## 2026-07-22 (later) — Toothless-stop root cause + fillable-limit fix · momentum ATR floors · dashboard grid fix. (DECISIONS §352.)

**What shipped (gazbot7 `refactor/three-service`, deployed):**
- **Fillable stop-limits** (`broker_adapter.py`, `1cae80d`): root-caused the STOP_UNFILLED / toothless-stop class (the §351 −$216 ride + every STOP_UNFILLED) — we placed a plain STP (limit unset) and IBKR's PAPER account attaches its own limit ~1 ATR toward entry (≈ entry price) on the WRONG side → never fills on trigger. We ARE placing them (they rest live); the FILL was the failure. Now `StopLimitOrder` with our own limit 20pt PAST the trigger on the fill side → fills on trigger, bounded slippage, strictly better live too. Guard still backstops. ⚠ **live confirmation pending** (must see IBKR keep our limit). +4 tests. Operator "are we actually placing them?" — right to push; my earlier "IBKR quirk, nothing we can do" was asserted without verifying.
- **Momentum ATR floors + thrust_short ER** (`deciders.py`/`tournament.py`, `5e20efa`): tick-honest ER>=0.20 + ATR sweep (`scripts/momentum_atr_sweep.py`). `ATR_FLOOR`/`atr_blocks` in `step()`. thrust_short ER>=0.20+ATR>=16 = +$726/38tr (robust selective edge). grind_long ER>=0.20+ATR>=20 = fragile tail (breakeven-only) → **KEPT as the big-trend-day specialist** (early jump + chandelier ride), gated to where that pays. +tests.
- **Dashboard grid fix** (`web_static/app.css`, `e3b3920`): the grid referenced a non-existent `#p-gates` and left `#p-tourn`+`#p-exec` unplaced → clipped EXEC / truncated scoreboard / dead space. Now all 6 panels in a clean 4x2 grid (22/30/26/22), fill to 100vh.

**Framing correction (operator, standing):** filtering a gate to selective +EV IS the goal (the favourable-condition thesis), not a compromise — judge each gate by its P&L AS RUN. The bar is edge ROBUSTNESS (+EV across a range = keep; +EV only at a fragile extreme = prove on a 2nd regime). "Relegation candidate" = unproven, not trades-too-little. grind_long = KEEP; rgv_short = the lone relegation candidate.

**Full favourable-condition config now live:** grind_long ER>=0.20+ATR>=20 · thrust_short ER>=0.20+ATR>=16 · rgv_long BAND 0.10–0.40 · rgv_short BAND 0.30–0.40 (disabled) · capitulation_long CEIL 0.10 · exhaustion_short CEIL 0.05. **Revert:** empty the deciders dicts / `git revert` the commit + restart. Full suite + lint green throughout.

## 2026-07-22 — Audit-loop-death incident (−$216) + the silent-auditor HARDENING shipped.

**Incident (paper):** a `grind_long` LONG 1 opened 00:05 UTC rode **153min past the 120-min max-hold**, stop toothless (price 87pt past it), closing **−$216** (would've been ~−$27 at its stop). Root cause: `MultiSlotCore.venue_audit_loop` (the safety spine — naked-audit, drift-halt, max-hold, stop-breach) had **NO exception guard**, so an unhandled throw **silently killed the task** while the MAIN loop kept writing a green heartbeat. `sweep.py` read OK throughout (it trusts the main heartbeat). A coincidental IBKR disconnect (04:34, nightly reset, self-healed 04:36) was a red herring. Operator-authorised `restart gazbot7-tournament` → adopted the slot from the ledger, revived auditor fired the overdue MAX_HOLD → flat.

**Hardening shipped (A → B, deployed, tests+lint green, desk restarted flat):**
- `multislot_core.venue_audit_loop`: every cycle now **exception-GUARDED** — a throw logs + pages `AUDIT_LOOP_ERROR` (once per error-run) + **CONTINUES**, never kills the task. Stamps `_last_audit_ok_mono` each non-raising cycle.
- `write_heartbeat`: adds **`audit_age_s`** (age of the last completed audit cycle; None pre-start).
- `sweep.py check_core`: **CRITs + fails preflight** when `audit_age_s > 30` while live (`AUDIT_STALE_S=30`); OK detail now shows `audit Xs`. A dead/hung auditor is now VISIBLE, not hidden behind the main heartbeat.
- **★ AUTO-RESTART (no human)** — `tournament.py` run loop now gates the systemd `WATCHDOG=1` ping on `core.audit_stale()`: a stale auditor → WITHHOLD the ping → systemd (`WatchdogSec=90`, `Restart=on-failure`, already set) restarts the desk in ≤90s → re-adopts the open slot from the ledger → revived loop fires any overdue max-hold. A dead auditor SELF-HEALS in ~2min instead of riding a position all night (operator: "we can't have these things holding the desk up all night"). `audit_stale()` returns False when never-started so it can't boot-loop; verified stable (NRestarts=0, audit_age ~2-5s « 30s).
- +7 tests (guard survives + pages once, age stamps, heartbeat carries it, audit_stale None/fresh/stale gating; 3 sweep). Verified live: `audit_age_s: 4.3`, sweep `HEALTHY … audit Xs`.

**Why:** the [[naked-position-silent-auditor-skip]] class recurred in the multi-slot desk — a safety loop must publish its OWN liveness; a sibling heartbeat is not evidence it ran. **Revert:** `git revert` the multislot_core+sweep change + restart (loses the guard — not advised).

## 2026-07-21 (later 3) — Per-gate ER favourable-condition gate live on paper + the tick-honest lesson. (DECISIONS §350.)

**What shipped (live on `refactor/three-service`, desk restarted flat/healthy):** every tournament gate now only OPENs when the tape ER (Kaufman efficiency, 30-min off 1-min closes) suits its style. `deciders.ER_FLOOR`/`ER_CEIL`/`ER_BAND`/`efficiency_ratio`/`er_blocks` → applied in `tournament.step()` (drops an OPEN whose gate fails the ER test, logs `ER gate: <gate> OPEN suppressed`); **NEW opens only** — an open slot rides its managed exit.

**A → B (the important part — this shipped TWICE):**
- **First (WRONG):** thresholds from `scripts/gate_backtest.py` = BAR-CLOSE fills (optimistic, the wick-illusion the desk forbids). Deployed grind_long/thrust_short floor 0.20, rgv_long ceil 0.25, rgv_short ceil 0.10. Operator caught it: *"why did you do an unrealistic test for the live desk? and present me numbers to act on?"* — right.
- **Then (HONEST):** re-derived via `scripts/gate_backtest_tickhonest.py` (entry on the 1-min signal, exit repriced tick-by-tick with each gate's REAL exit) + a per-0.1-ER-band sweep. The bar-close numbers were illusory — grind_long "+$1,664 at floor 0.20" was −$1,228 on real ticks. **Final live config:** `grind_long` FLOOR 0.20 (loses every band → RELEGATION candidate, floor is damage-control) · `thrust_short` UNGATED (winners/losers interleaved, natural +$532 beats every cut) · `rgv_long` BAND 0.10–0.40 (mid-band edge; 0.25 ceiling had strangled it) · `rgv_short` BAND 0.30–0.40 but DISABLED via switch (single-band sliver → RELEGATION candidate) · `capitulation_long` CEIL 0.10 · `exhaustion_short` CEIL 0.05 (footprint duck, fixed-exit-derived).

**Why:** the [[favourable-condition-gating-vision]] made concrete — stop each gate bleeding in the regime that's wrong for its style. **⚠ coverage ~9 days (one summer regime) + 60-min hold cap — a LEAD, re-validate a 2nd regime; paper forward-validation, not real-money-proven.** New standing rules: live decisions off the TICK-honest backtest never bar-close; analytics/backtests all DuckDB-vectorized ([[duckdb-pandas-for-analytics]] memory).

**Tools added (all DuckDB):** `gate_backtest_tickhonest.py` (★ per-band + cumulative), `footprint_backtest_duck.py`, `live_er_sweep.py --days N --tournament-only`, `shadow_er_sweep.py --days N`, `er_threshold_scan.py`. Tests: +6 ER-gate tests (deciders + tournament.step), full suite green, lint clean.

**Revert:** empty `ER_FLOOR`/`ER_CEIL`/`ER_BAND` in `deciders.py` + `systemctl restart gazbot7-tournament` → gate inert (wiring stays).

## 2026-07-21 (later 2) — Operator-control + adaptive-monitoring layer + tournament cockpit. (DECISIONS §349.)

**What shipped (all live on `refactor/three-service`):**
- **Intraday per-gate off-switch** (`fafdfdb`): `data/gate_switches.env` (`<gate>=off`) — the tournament re-reads it LIVE each tick (cached on mtime+size, no restart). A disabled gate takes NO new entries; its open position still exits normally. `tournament.read_disabled()` filters OPEN intents. The only per-gate control (env LIVE/SLATE stay whole-desk/restart-only). +3 tests.
- **Telegram command bot** (`764b399`, `gazbot7-tgbot.service`, active): the receive side (desk already sends via notify). Operator texts `/off <gate>` `/on` `/gates` `/status` → writes the switch file. SAFE: only the authorized chat (alphabot2/.env TELEGRAM_CHAT) obeyed; the ONLY mutating command is gate on/off; no flatten/restart/roster. Stdlib long-poll, +10 tests. Works when the Claude session is offline.
- **Adaptive hourly watch** (`efe00e2`, `scripts/hour_watch.py`, cron `8 5-21 * * *` = 07–23 Paris): two-tier — routine one-liner, or a DIG-IN dissection headed **`ATTENTION GAZ`** when a trigger fires (heavy-action on the *active* desk / violent tape / big-swing / drastic). A disabled gate is excluded from triggers. Default read "info, no action"; recommend `/off` only on a fighting+bleeding+persisting pattern. Replaced the earlier one-liner-only sweep cron.
- **Dashboard TOURNAMENT OVERHAUL** (`7ff391b` + promotion feeder `dec429d`): TOURNEY tab = ranked 6-gate scoreboard (realized+open, 🔻relegation) + live-slots strip + header SAFETY pill (`/api/futures/tournament`); shadow PROMOTION FEEDER panel (over-trading caveat); dead V5 panels cut. **EXEC funnel restored** (`90aed10`): say→buy through-rate + slippage + misses (nofill/rejected) + per-gate — and fixed a latent unfilled-IOC wedge (`_pending` never cleared → gate silently stuck).
- **sweep.py cutover fix** (`c8ba704`): the 3-hourly maintenance sweep no longer false-CRITs — desk = `gazbot7-tournament` (core/strategy inactive = expected), position gate reads per-slot `core_health.protection` not the empty `open_position`. +6 tests. Sweeps now read genuinely green.
- **Operator action:** rgv_short **disabled 15:41** for the day (fighting an up-grind, day's worst −$207). Reverts on `/on rgv_short` or next session.

**Scoped NOT built:** Friday-report TOURNAMENT SECTION (`gazbot7/docs/FRIDAY_TOURNAMENT_SECTION_SCOPE.md`; `alphabot2/scripts/friday/tournament_scorecard.py` DRAFTED — not wired into build_report.py, not validated, has a known malformed f-string in the Saturday-brief render). The one open build.

**Revert:** off-switch = empty `gate_switches.env` / `git revert fafdfdb`; tgbot = `systemctl stop gazbot7-tgbot`; watch = session-only cron. Governance rules in [[tournament-changes-saturday-only]] + [[intraday-gate-disable-hourly-sweep]] (memory). Full suite green through the day.

## 2026-07-21 (later) — EXEC tab funnel restored + a latent unfilled-IOC wedge fixed.

**What (gazbot7 `90aed10`):** the EXEC tab was blank — the tournament never recorded signals (only the retired `core.py` did), so the signal→fill funnel had no denominator. Now the entry path logs to `signals`: `_open`→**submitted** (what we said to buy + intended ref), `_on_slot_opened`→**filled** (what we bought + fill price), `expire_pending_opens`→**nofill** (IOC submitted but never filled). Each is once-per-entry (the `_pending` guard dedups per-tick re-fires). **Bonus bug fixed:** an unfilled IOC left `_pending` latched forever → that gate silently wedged (could never re-open); `expire_pending_opens` (called each loop tick) now frees it after `entry_timeout_s` and logs the nofill. `execution_json` rebuilt: through-rate, per-entry slippage (ref→fill), failure reasons (nofill/rejected), per-gate breakdown, hourly trend; EXEC tab UI shows the funnel (submitted→filled→missed) + per-gate table. +6 tests, full suite green. **Revert:** `git revert 90aed10` + restart web/tournament. NB pre-cutover single-position signals (gate `grind`/`rgv`, no intended_price) remain in the table but are date-filtered out of today's funnel.

## 2026-07-21 — id114 stop-guard + footprint feed → the full 6-gate tournament.

**id114 forensic + stop guard (gazbot7 `551923b`):** a rgv_short lost −$171 on a MAX_HOLD (exit "MAX"). Root cause: the 1-ATR native stop was placed correctly (`BUY STP @ 28837.5`, a plain stop-market) but when it triggered, **IBKR's paper engine converted it to a stale unfillable limit** (`lmtPrice=28815.25`, below the trigger) — the stop stayed a LIVE resting order (so the naked auditor passed it) but never executed, and the short rode 84pt to the 120-min MAX_HOLD backstop. A real account fills that stop ~−$44 → the −$171 is a paper-sim artifact, not gate edge. **NEW guard:** `note_price()` feeds the tape print; `stop_breached()` flags a slot whose price ran past its stop trigger while still held; after `STOP_BREACH_FLATTEN_STREAK` audit cycles → force MKT flatten (reason `STOP_UNFILLED`) + page. Catches it in ~10s, not 120 min. +4 tests. **Only 1 MAX_HOLD ever** — the 47 STOP exits fill normally, so this is a rare paper hiccup, now backstopped faster.

**Footprint feed → 6-gate slate (gazbot7 `4c708fc`):** wired the last two gates. `footprint.footprint_summary()` rolls up the capitulation climax (`capitulation_tape`) + the exhaustion 20s net/move + L1 book from `capture.db`; the tournament computes it each tape tick (like the shadow loop — **live md service untouched**, lower risk than extending md) and passes it to `SlotStrategy.decide`, which routes to the `capitulation`/`exhaustion` gates (direction-gated). Added `capitulation_long` + `exhaustion_short` → slate is now **3 long / 3 short**: rgv-long, grind-long, capitulation-long | thrust-short, rgv-short, exhaustion-short. +9 tests; validated on the live capture.db; `gazbot7-tournament` restarted on a flat tick → all 6 slots live + healthy. Scope `gazbot7/docs/FOOTPRINT_GATES_TOURNAMENT_SCOPE.md`.

**Revert:** stop guard = revert `551923b`; footprint/6-gate = revert `4c708fc` (slate back to 4) or `GAZBOT7_TOURNAMENT_SLATE=grind2`. Full suite 371 green.

## 2026-07-20 (later 11) — Dashboard multi-slot cockpit (P1–P3) built + live.

**What (gazbot7 `b7c5b4e`):** the `:8087` cockpit read the single-position `status.json` and showed FLAT post-cutover. Now multi-slot aware: `web.py us_terminal_json` renders one holding per open slot (real gate, per-slot P&L, held-time, protected flag; legacy single-dict tolerated for revert); `multislot_core.write_heartbeat` carries per-slot `stop_price`/`opened_at`/`entry_atr`; `app.js renderHolding` = a card per slot (+ protected|NAKED badge) and the main chart overlays entry/stop for ALL slots; `app.css .slot-card`. Per-gate leaderboard already worked off `trades`. +7 tests (`test_web.py` + heartbeat); `gazbot7-web` restarted; tournament restarted on a flat tick to deploy the enriched heartbeat. **Verified live** (holdings + leaderboard rendering; 2-lot stops confirmed qty=2 = fully covered). **P4 deferred**; **backlog:** multi-slot core lacks the partial-fill `_on_increased` stop re-arm (latent half-naked if a 2-lot ever fills in two partials — not active today). **Revert:** `git revert b7c5b4e` + restart web. Scope `gazbot7/docs/DASHBOARD_MULTISLOT_UPGRADE_SCOPE.md`.

## 2026-07-20 (later 10) — ★ TOURNAMENT robustness settled + 2 pre-cutover safety layers built → GO-LIVE cutover to the multi-slot paper tournament. (DECISIONS §348.)

**What changed (A → B):**
- **Research → architecture decision.** Open question (is one netted paper account robust for N long+short gates, or need separate accounts / a per-slot sim?) → **ANSWERED: one netted paper account IS robust, with our per-slot ledger as the durable source of truth and venue-net as a coarse DRIFT tripwire.** IBKR nets per account (clientId segregates orders not positions); separate paper accounts impractical (~one per login); per-slot sim rejected (regresses to the optimistic shadow we're fleeing). The restart-with-offsetting-positions hole is closed by durable ledger, NOT a venue query (net 0 tells you nothing).
- **BUILT — durable ledger + restart reconstruction** (`store.py` new `slot_positions` + `slot_orders` tables; `multislot_core.py` `_register`/`_persist_slot`/`reconstruct`; `slotbook.py` `restore_slot`; `safety.py` `restore_stop`). Per-open-slot snapshot (side/qty/entry-VWAP/entry_atr/live-stop coid+price) + durable coid→gate map → a restart rebuilds per-slot positions and re-attaches each stop from OUR ledger (no duplicate place), then the audit loop reconciles vs venue net (DRIFT→halt+page). Fills `record_fill`'d before apply → cross-restart redelivery idempotent. **Latent bug fixed:** stop coids were never registered with the SlotBook → a native-stop fill was "unattributed" and the slot never closed; now attributes + records reason STOP. 8 tests.
- **BUILT — per-slot time-exits + wedge-breaker** (`multislot_core.py` `time_exit_check`/`over_max_hold`/`exit_watchdog_slot`, injectable clock; both wired into `venue_audit_loop`). Session-end flattens every open slot; per-slot max-hold cuts only the stale slot; a slot's stuck close escalates (page → re-fire cancel-then-resubmit → force reconnect). 7 tests. Full suite **353 green**, touched files ruff-clean.
- **GO-LIVE cutover.** Single-position grind+rgv desk (§346) → **multi-slot paper tournament**: N gates each holding their own 1 MNQ lot concurrently on the one paper account, per-gate P&L from the coid-attributed SlotBook. New `gazbot7-tournament.service` (decision+execution combined, clientId 7) replaces `gazbot7-core`+`gazbot7-strategy`; `gazbot7-md` stays up. First real-gateway run of the multi-slot order path; kill-switches OFF (paper); per-slot 1-ATR stop caps each lot ~$60–80.

**Why:** §347's pivot made PAPER the realistic judge; the one thing blocking a robust cutover was whether a netted account can carry restart-survivable per-gate P&L (yes, with the durable ledger) and the two deferred safety polish items (now built).

**Revert:** stop `gazbot7-tournament` + restart `gazbot7-core`+`gazbot7-strategy` → the §346 single-position desk is back (config untouched). Code reverts via `git revert` on `refactor/three-service`.

**Commits:** gazbot7 `refactor/three-service` (durable-ledger + time-exit/wedge-breaker + tournament unit); alphabot2 DECISIONS §348 / SESSIONS / STATE.

## 2026-07-20 (later 9) — BUILT the multi-slot paper-tournament core (3 modules, 18 tests). Not wired to a service.

**What (new modules, pure/fakes-tested, nothing live):** started the tournament build (operator: "keep going,
build the core"). Three modules on `refactor/three-service`:
- `slotbook.py` — per-gate position ledger over the NETTED venue: keeps logical per-slot truth, attributes
  every fill BY ORDER COID, carries `sum(signed slot qtys) == venue net` (else DRIFT). The hard case
  (grind-long +1 @ 29000 + grind-short −1 @ 29050 → venue net 0, both tracked/closed independently) is the
  first test. 7 tests.
- `slot_strategy.py` — per-slot decisions: grind-long vs grind-short as INDEPENDENT slots (a signal opens
  only its own direction's slot); each manages its own exit stack (chandelier/2R + give-back + risk-sizing);
  reuses the single-position deciders per slot. `grind_long_short_slots()` = the first pairing. 5 tests.
- `multislot_core.py` — execution: per-slot capped-marketable-limit-IOC entry (inherited) + own native 1-ATR
  stop (per-slot SafetyManager, N stops on the one contract) + trade recording + `reconcile()` drift-halt.
  6 tests against fakes.
Full suite **338 green**, ruff clean. Commits: `slotbook`, `slot_strategy`, `multislot_core`.
**REMAINING to run on paper:** (1) service wiring — a `run()` connecting the real gateway/md/fills + the
reconcile loop; (2) DEFERRED hardening — the async venue-audit loop (per-slot naked-auditor/adopt/wedge over
the netted book) before it ever fronts real money; (3) config + deploy. Operator tournament decisions
(N, relegation metric/window, promotion cadence) still pending — but the grind-long/short 2-slot first pairing
is self-contained and doesn't need them. NOT wired live; zero risk to the current desk.

---

## 2026-07-20 (later 8) — SCOPED the multi-slot paper tournament (shadow → paper realism pivot). Doc only.

**What (a scope doc, no code):** the shadow-vs-live grind audit (shadow +$460/day over live, opposite
sign — from ignoring single-position, idealized bar-close entries, and tape-opposing trades the live
refuses) drove an operator pivot: *"use paper trading as our shadow desk — shadow is far too optimistic
— put all the gates we like into paper."* Account solution (operator): *"lift max total contract holdings
to ~6, 1 per gate, 6 max gates concurrently; best from shadow promoted, worst couple from paper canned."*
Scoped in `gazbot7/docs/PAPER_TOURNAMENT_SCOPE.md`: an N-slot MULTI-POSITION paper tournament (replaces
single-position first-to-fire), shadow as cheap feeder → paper as the real-fill judge. **Central challenge
flagged:** per-gate attribution over a NETTED venue (IBKR nets MNQ per-account, not per-gate/clientId) —
reverses V7's single-position simplification and re-admits the V5 attribution class; every safety mechanism
hardened TODAY must go per-slot (today's bug-class ×N). Big core refactor → own build, phased rollout
(start 2 slots = grind+rgv). Operator decisions pending (attribution model A/B, relegation metric+window,
promotion cadence, N, sizing separation). NOT built.

**Prior day-latch assessment (also research):** the "when to trade grind" reactive latch was tested and
does NOT cleanly work — on the one drawdown-and-recover day (shadow 07-20: −$314 DD → +$46) it would have
HURT −$350 (missed the recovery); only 2/5 days tripped it and they disagree (live helped +$315, shadow
hurt −$350). Every grind-timing lever has now failed a test (drop/smooth/loosen tape, shadow-governor,
day-latch) → grind is a fat-tailed gate; the honest call is sizing/keep-or-cut, not timing. Feeds the
tournament (let paper rank it honestly).

---

## 2026-07-20 (later 7) — FIXED order-id sequence resetting on restart (orders-table corruption).

**What changed (A → B):** `OrderEngine._seq` was in-memory → **reset to 0 on every core restart**, re-minting
`v7-mnq-000001…` which collided with prior-session coids. The orders-table upsert-on-conflict updates
`limit_price`/`status` but keeps the old `order_type`/`created_at`, so a post-restart **LMT entry showed as
`MKT` with a stale 07-16 timestamp** (exactly what obscured the marketable-limit verification). **Fix:** seed
`_seq` from the max stored coid at startup (`_max_coid_seq`) so the sequence always continues forward. +1
test; full suite (313) green, ruff clean. Commit on `refactor/three-service`. **Deployed** core restart
15:47 UTC (flat-verified; seeds `_seq=50` → next `v7-mnq-000051`). **Blast radius:** orders-table integrity
only — live order mgmt was unaffected (in-memory `_orders`, trades keyed on unique venue exec-ids). Old
collided rows (000001/000002) remain historically corrupted; the fix prevents future collisions. Found via
the marketable-limit first-entry verification (which also **confirmed the capped LMT is working live** —
id78/id79 entries carried capped limit prices 28887.25/29013.75, filled at/better than the cap).

**Also this session (research, nothing armed):** proved the grind tape gate should be LEFT ALONE — dropping
it (−$648 vs −$536), smoothing it (−$630/−$647), and loosening it (flat) all fail; the tape gate blocks a
NET-LOSING class (the 25 tape-opposing shadow grind trades net −$67; the 14:46 +$171 was the survivorship
outlier). Shadow-as-governor confirmed unreliable (shadow grind +$46 vs live −$332 today, opposite sign;
shadow takes 2.5× the trades at +5–13pt better idealized entries). Grind's chop-day bleed is a *when-to-trade*
problem (a live-P&L day-latch), not an entry/tape one. Memory `giveback-exit-finding` + this entry.

---

## 2026-07-20 (later 6) — CAPPED MARKETABLE-LIMIT ENTRIES (IOC) built + LIVE — kill the blow-up fill.

**What changed (A → B):** entries went from **raw MARKET orders** → a **marketable LIMIT at
`ref_price ± entry_limit_buffer_pts` (3.0), tif=IOC**. Verified V7 entries were plain MKT (no
limit/tolerance anywhere — contra the operator's belief we ran a wide-tolerance marketable-limit; that
was V5). A market order accepts any fill, so id67's 2nd lot filled **29pt off a tight/deep book** on the
paper engine → −$156. IOC fills liquidity within the cap + cancels the rest (no resting order; blow-up
fill impossible). **CLOSES/FLATTENS stay MKT** (must fill). `strategy._emit_open` now carries the
decision `price`; `core._open` builds the LMT (ceil/floor to tick); `engine`/`broker_adapter` plumb
`tif`. **Wedge guard:** an IOC that fills nothing leaves no fill event → `core.expire_pending_open()`
(1s loop) cancels the remnant + clears `pending_open` after `entry_timeout_s`(3s) so the desk re-fires.
+5 tests; full suite (312) green, ruff clean. Backward-compatible (no `price` → MKT). Commit on
`refactor/three-service`. **Deployed** `systemctl restart gazbot7-core gazbot7-strategy` 14:31 UTC
(flat-verified; both NRestarts=0; new code loaded). ⚠ First LIVE use of LMT entries in V7 — the V5
07-15 entry tangle (MKT+STP_LMT recording break) is the scar; watching the first entries. **Rollback:**
`entry_limit_buffer_pts=0` + restart, or git revert. Scope `gazbot7/docs/CAPPED_MARKETABLE_LIMIT_ENTRIES.md`.

**Throughput note (operator's 40% concern):** last week's low throughput came from now-fixed bugs
(market-hours clock / qty under-count / 45s veto), NOT tight limits (there were none). A 3pt cap fills in
any normal book; a miss only on a >3pt gap in the ms latency (rare + safe — re-fires). Widen the buffer
if the miss-rate proves high.

---

## 2026-07-20 (later 5) — RISK-BOUNDED SIZING built + LIVE (the always-red solution); exit-signal cuts proven not to help.

**What changed (A → B):** `strategy._size_for` gained a **risk cap** — after the gate's conviction/flat qty,
cap it so the 1-ATR stop's dollar risk (`atr × stop_atr_mult × value_per_point × qty`) ≤ `risk_budget_usd`
(**$80** on both live gates). Volatile entries size DOWN (2→1); normal ATR keeps full 2 lots; floors at 1
(never zeroes a fire). `config.risk_budget_usd` on GateSpec + RunConfig. +1 test; suite (306) green. Commit
on `refactor/three-service`. **Deployed** `systemctl restart gazbot7-strategy` 14:18:54 UTC (flat-verified;
NRestarts=0; both gates `risk_budget=80`). Revert = `risk_budget_usd=0` + restart. Scope
`gazbot7/docs/RISK_BOUNDED_SIZING.md`.

**Why (the always-red investigation):** operator unhappy with big losses on wrong entries. L2 review found
the big never-green losses (id68 −$130, id67 −$156) are **correct 1-ATR stops made huge by qty × volatility**
(id68: ATR 31pt × $2 × 2 lots = $126), NOT a fill/exit-signal problem. **Exit-signal cuts PROVEN not to help**
— swept a real opposing-aggressor-flow cut on top of the give-back: best case +$14, mostly −$140 to −$230,
because any pre-green cut clips the dips that would've recovered (you can't tell an always-red from a
not-yet-green dip at cut time). The give-back works *because* it only acts after green. So the always-red
lever is **sizing**, not an exit. Also reviewed the V5 exits (operator: *"didn't you say there was adverse
flow before?"*): the **force loss-killer** (`force_kill_fires`/`trailing_adverse_run`, velocity/run-based) is
V5's adverse-flow exit and was NOT ported to V7 — but its $80 arm is past V7's tight 1-ATR stop and it only
catches clean velocity runs (1/6 never-green big losses), so not the fix either.

**Also corrected a mental-model mismatch:** operator believed entries use marketable-limit with wide
tolerance; the V7 code actually sends **plain MARKET orders** (`core.py:179 order_type="MKT"`, no limit
anywhere). That's how id67's 2nd lot filled 29pt off a tight/deep book (paper-engine garbage) → −$156. The
capped marketable-limit fix is scoped-in-discussion but **parked** pending the fill-throughput question (last
week's 40% throughput came from now-fixed bugs, not tight limits). Memory `giveback-exit-finding` covers the
exit-signal null result.

---

## 2026-07-20 (later 4) — dollar GIVE-BACK exit BUILT + made LIVE on grind + rgv.

**What changed (A → B):** built the scoped give-back and armed it — operator: *"build it and make it
live."* `deciders.exit_giveback` (pure, dollar-denominated, reuses `pos.peak_favorable`) + `strategy.
_manage` (checked under the profit exits, above absorption; qty from the core payload) + `config`
knobs (`giveback_enabled/arm_usd/usd` on GateSpec + RunConfig), **ENABLED on both live gates**
(grind, rgv; arm $50 / gb $40). +4 deciders tests; full suite (301) green, ruff clean. Commit on
`refactor/three-service`. **Deployed** `systemctl restart gazbot7-strategy` 13:10:50 UTC (flat-verified;
NRestarts=0; both gates confirmed `giveback_enabled`). ⚠ Operator **overrode the shadow-first rail** —
live while validated only at 1-lot on shadow (2-lot depths proven on the live sim). **Revert:**
`giveback_enabled=False` on the gates + restart strategy, or git revert. Next per operator: sharpen the
absorption cut for the never-green ("always red") losers. Memory `giveback-exit-finding`.

---

## 2026-07-20 (later 3) — L2 absorption-cut study → dollar GIVE-BACK exit scoped (the missing "ratchet 2"). Research only, nothing armed.

**What (research + a scope doc, no code/behaviour change).** Operator: *"I'm not happy taking the big
losses when a trade goes wrong … we must know a trade is cooked much before −$120–150."* Reviewed
today's + last week's losing trades against the **L2 depth capture** (`alphabot2/data/depth.db`, MNQ
10-level book, 251ms, 07-09→now) and forward-validated on the shadow board.

**Findings:**
- Deep losers are **green-then-reverse**, not cooked-early (id53 +$85→−$150; id61 +$68→−$122). L2 book
  imbalance does NOT warn (id61 died with positive book support). So a *static* earlier absorption cut
  can't separate them from dips that recover (id57 −$60→won) — that's the "too early last week" failure.
- The separator is a **profit give-back ratchet**: `arm +$50 / give-back $40`. Live sim: −$890 → −$2
  over 61 trades (rescued id53 −150→+20, id61 −122→+26), clipping only 5 winners −$158.
- **Forward-validated (shadow board, 170 trades, tick-repriced):** give-back +$471 vs actual, ALL from
  the went-green cohort; the never-green cohort **untouched** (operator's constraint — a give-back can
  only arm on a trade that goes green; never-green losses are STOP territory, a separate lever).
- **V5 ratchet2 rejected:** nets similar (+$421) but by **gutting winners** (+$841 vs +$3,490 actual on
  the green cohort = −$2,649 scalped away) — it arms at $2.50 and banks 70% of tiny peaks. "Wouldn't
  work" confirmed. Caveat: the shadow board is 1-LOT so it doesn't reproduce the −$120–150 depths (a
  2-lot phenomenon); the 2-lot rescue is proven only on the live sim.

**Deliverable:** `gazbot7/docs/GIVEBACK_EXIT_SCOPE.md` — `exit_giveback` pure decider (dollar-
denominated, reuses `pos.peak_favorable`), per-gate wiring (rgv has NO trail today → gets it; grind's
chandelier is ~3.5-ATR wide → give-back underneath), config knobs default OFF, tests, shadow-first
rollout. V7 has **no give-back/ratchet-2 today** (verified). NOT built. Memory: `giveback-exit-finding`.

**No revert needed** — analysis + one new doc; no code, config, or desk change.

---

## 2026-07-20 (later 2) — PARTIAL-FILL qty under-count FIXED + DEPLOYED — the ROOT cause of the stuck-position incident.

**What changed (A → B):** `core.on_fill` gained an `_on_increased` branch. **Before:** `_on_opened`
ran only on the flat→held transition (the first fill), so a multi-lot entry (rgv flat-2 / grind
conviction-2) that filled in **partials** left the extra lot(s) invisible to `self._qty`, the native
stop, and `open_position` — cached qty stuck at the first-fill size. **After:** a same-side fill that
grows the held qty syncs `self._qty` to venue-derived truth, **re-arms the stop to the full size**
(`SafetyManager.rearm` cancels the prior stop first — no stacking/oversell), and re-persists the row.

**Why (this was the incident's ROOT, upstream of the wedge-breaker):** tonight's rgv 2-lot entry
(01:32:05) filled as two partials 44ms apart → tracked qty 1 vs venue net 2 → permanent
`reconcile_verdict` **DRIFT** → the audit loop HALTED + `continue`d, skipping BOTH the naked-protection
check (the 2nd lot sat unprotected ~12 min) AND the time-exit check (max-hold could never fire). The
01:44 absorption cut then sold only `self._qty`=1 of 2 → left 1 lot that `_closing`+alarm-only wedged
for ~4h. This fix removes the drift, closes the naked-lot window, and sizes closes correctly from the
first fill. Recurs on every partial-filled 2-lot order, so it's a live safety fix for the go-live.
(The wedge-breaker handles the stuck-exit *symptom*; this removes the *cause*.)

**Build + verify:** `src/gazbot7/core.py` (`on_fill` add-detection + `_on_increased`),
`src/gazbot7/safety.py` (`rearm`), `tests/test_core.py` (+2: partial-entry grows qty+reprotects+no-drift;
rearm replaces at full qty). core/safety/tracker/integration green (67), ruff clean. Commit on
`refactor/three-service`.

**Deploy:** committed, then waited for a flat window (operator "deploy when flat"; desk was holding a
grind LONG). Background watcher fired at desk-flat 11:30:41 UTC → `systemctl restart gazbot7-core`
11:31:04 UTC. ⚠ A fresh entry opened in the ~11s flat-check→restart gap, so core booted into an
**adopt** — the boot-adopt re-armed + venue-verified the stop (LONG 1 @ 29043, stop 29030.5) within
~seconds (`protection.verified=true`); no naked window. `_on_increased`/`rearm` confirmed loaded,
healthy. **Lesson:** deploying during live market has a fill-race even after a flat-check; the
boot-adopt net covers it, but prefer a genuinely idle window. **Revert:** `git revert` the qty-fix
commit + restart core.

---

## 2026-07-20 (later) — EXIT WEDGE-BREAKER built + DEPLOYED to live core.

**What changed (A → B):** `core._exit_watchdog` went from **alarm-only** ("detect + page, don't
auto-thrash") → an **escalating in-loop self-heal**. When a close is in-flight and the position isn't
reducing, after `EXIT_STUCK_CYCLES` it: pages once → **re-fires the flatten** (force-cancels the
dangling close via a new `_closing_coid` handle + re-submits MKT at venue-truth qty via
`safe_flatten_verdict`) up to `EXIT_REFIRE_MAX=3` → `gw.force_reconnect()` → resets and retries.
Bounded, idempotent (cancel-before-resubmit, fires only what IBKR holds — no oversell/order-storm),
pages each step. **NOT a self-restart** (the V5 orphan scar). Directly closes the wedge that stuck
tonight's rgv LONG for 4h. `_close`/`_emergency_flatten` now record `_closing_coid`; wedge state
resets on flat (both `_on_closed` + `_clear_phantom`).

**Why:** operator directive "build the wedge-breaker" following the incident (this morning's SESSIONS
entry above). The scope (`gazbot7/docs/EXIT_WEDGE_BREAKER_SCOPE.md`) was operator-approved.

**Build + verify:** `src/gazbot7/core.py` (`_exit_watchdog` rewrite + `_refire_flatten` + constants +
state/reset), `tests/test_core.py` (+4: re-fire-submits, cap→reconnect, flat-guard-no-op,
no-order-storm). core+tracker+integration suites green, ruff clean. Commit on `refactor/three-service`.

**Deploy:** desk FLAT-verified → `systemctl restart gazbot7-core` 2026-07-20 08:47:34 UTC (lone core
restart, no §3 pairing). Healthy, place_live, reconnected, NRestarts=0, `EXIT_REFIRE_MAX` confirmed
loaded. **Revert:** `git revert` the wedge-breaker commit + restart core.

---

## 2026-07-20 — go-live night: gate-label bug FIXED+DEPLOYED (live core); a stuck-position incident flattened; wedge-breaker scoped.

**Incident (resolved).** A live rgv LONG (2 lots, opened 01:32:05 UTC) sat **held ~4h10m** — far
past `max_hold_minutes=120` — and never auto-flattened. It was **protected throughout** (native venue
stop live; ~breakeven then drifted to the stop), so no uncapped bleed, but genuinely wedged. Cause
(verified vs code+journal): a close initiated ~01:44 (absorption backstop) did NOT complete
(`Order Canceled` 202, then IBKR connectivity drop 1100→1102 at 04:28), so `core._closing` latched
`True`; while latched the audit loop diverts every cycle to `_exit_watchdog` (alarm-only) and never
reaches `_time_exit_check`, so max-hold/session-flat can't fire. Operator flatten
(`python -m gazbot7.eod_flatten`) completed the close at 06:09 (recorded as the latched
`ABSORPTION_CUT`, **−$141**); core reset to flat cleanly. Day close: **−$390.5 / 5 trades**. The
operator's "01:42 error" = core's one-shot `EXIT_NOT_COMPLETING` page.

**Gate-label bug FIXED + DEPLOYED.** All 4 of tonight's trades recorded `gate='thrust'` though the
desk correctly ran the two-gate go-live (signals table: grind×3, rgv×2). Cause: `TradeTracker` stamped
its static `self._gate` (`'thrust'` default) on every trade; the true gate rode the opening intent but
never reached `trades.gate`. **Fix (A→B):** the gate now rides the opening fill into the tracker,
stamped per round-trip (`o.gate or self._gate` fallback for adopt/flip). `tracker.py` (`_Open.gate` +
`apply(gate=)` + `_complete`), `core.py` (`_open` stashes `_pending_gate`, `on_fill` threads it),
+3 tests. 43 tracker+core tests pass, ruff clean. Commit `4f2a4bb` on `refactor/three-service`.
**Deployed** via `systemctl restart gazbot7-core` at 06:21:43 UTC (desk FLAT-verified first → lone
core restart, no §3 pairing needed; NRestarts=0, healthy, place_live, reconnected). Recording-only —
no execution change. Next trade records its real gate.

**Go-live health (first session).** Desk reopened clean at 22:00 UTC, ran the two-gate lineup live:
grind (conviction-sized, 3 trades @ 1 lot) + rgv (flat-2, incl. the 2-lot fill — the go-live 2-lot
watch item CONFIRMED). Exits/recording functioning; stops venue-verified on every hold. −$390.5 night
(optimistic-1m-ceiling reminder stands: paper forward-validation).

**Wedge-breaker SCOPED (not built).** New `gazbot7/docs/EXIT_WEDGE_BREAKER_SCOPE.md`: escalate
`_exit_watchdog` from alarm-only → an in-loop **re-fire the flatten** after N stuck cycles (force-cancel
dangling close + re-submit MKT, bounded/idempotent, then `force_reconnect` escalation, page each step) —
NOT a self-restart (V5 orphan scar). Operator sign-off required before build. Added to STATE §6.

**Revert:** gate fix → `git revert 4f2a4bb` + `systemctl restart gazbot7-core`. No config/.env change.

**Commits:** gazbot7 `refactor/three-service`: `4f2a4bb` (gate fix), plus this SESSIONS entry +
STATE §6 + the two scope/maintenance docs. Files: `src/gazbot7/{tracker,core}.py`,
`tests/test_tracker.py`, `docs/EXIT_WEDGE_BREAKER_SCOPE.md`.

---

## 2026-07-19 (later) — V7-CORRECT maintenance sweep armed; V5 nine-cron ritual retired for V7.

**What changed (A → B):** the session's maintenance timers went from **nothing armed** (fresh
session; the CLAUDE.md §8 V5 nine-cron ritual is obsolete under V7 — it probes the masked `:8090`
broker + `alphabot.db` and would false-CRIT / risk bouncing the shared gateway) → **two V7-correct
session crons** driving the existing tested collector `gazbot7/scripts/sweep.py` + tiered
`gazbot7/notify.py`. Operator asked (verbatim option) to "Build a V7 sweep".

**The two crons (session-only, `recurring:true`, box is UTC):**
- **FULL sweep** `41 */3 * * *` (every 3h) — runs `sweep.py --json`, curated heartbeat in Paris
  waking hours, CRITICAL alert on overall-CRIT / preflight-FAIL / naked-position / execution-wedge /
  feed-break. READ-ONLY + FLAG-AND-WAIT (no auto-fix, no restarts, no DB writes — stricter than V5
  by design; V7 core self-heals).
- **Sunday open RAMP** `9 20-23 * * 0` (hourly 20:09–23:09 UTC into the 22:00 UTC Globex reopen) —
  mandatory hourly ping; tonight it watches the two-gate go-live's first session (2-lot fill
  confirm, kill-switches-off-for-paper note).

**Why V7-shaped, not V5:** STATE §6 + the 2026-07-17 cutover entry flagged the V5 ritual as obsolete;
the collector `sweep.py` already reads the right V7 surfaces (services incl. shared `alphabot-gateway`,
`core_health.json` preflight/freshness, capture 5s/250ms feed-break tell, execution wedge, venue-truth
protection/naked gate, killswitch, recording w/ no-backfill anomaly, shadow repricer lag, storage).
The tight fills-based wedge alarm still runs independently as the external `gazbot7-monitor.timer`
(every 10min, survives session death).

**Persisted so it survives a restart:** new canonical doc **`gazbot7/docs/V7_MAINTENANCE_SWEEP.md`**
holds both verbatim prompts + the re-arm procedure + the back-on-shift line. STATE §6 now points at
it. (This is the V7 replacement for CLAUDE.md §8's re-arm source-of-truth; CLAUDE.md itself is still
V5-voiced — a fuller refresh is future work.)

**Revert:** `CronDelete 0e4029ea 7dc093e0` (or just end the session — crons are in-memory);
`rm gazbot7/docs/V7_MAINTENANCE_SWEEP.md` + `git checkout docs/STATE.md docs/SESSIONS.md` to undo
the docs. No runtime/desk change — pure maintenance + documentation.

**Files:** new `gazbot7/docs/V7_MAINTENANCE_SWEEP.md`; `docs/STATE.md` §6; this SESSIONS entry.
No code, no `.env`, no service change. Desk untouched (verified flat + healthy + `place_live=true`
via `sweep.py`, overall OK, at ~15:34 UTC).

---

## 2026-07-19 — ★ GO-LIVE: live gate flipped from thrust_loose → TWO-GATE (grind_fast conviction + rg_long_fast_v 2R). PAPER. thrust → shadow.

**What changed (A → B):** the live V7 desk gate went from single **thrust_loose** (size 1) → a
**two-gate, single-position lineup: grind_fast** (early-entry momentum, ER 0/1/2 conviction sizing,
vol-adaptive chandelier exit) **+ rg_long_fast_v** (chop reversion, flat 2, 2R exit), first-to-fire.
thrust_loose dropped from live → stays in the shadow slate (all 3 gates now shadow-incubate). PAPER
(`place_live=true`, IBKR paper account). Max 2 lots (design A single-position).

**Why:** weekend go-live decision (operator, verbatim across the session: *"we are using grind fast…
$1300 winning days need to be kept, turn off the shit"*, *"A, build it robustly"*, *"do the sunday-night
deploy… do it now"*). grind is the early-entry trend gate (enters 1.54× vs thrust's late 2.31×) and
the strongest cover of rgv (OOS corr −0.23…−0.48; its big trend days are rgv's worst). rgv is the
forward-validated +EV chop keeper (walk-forward OOS +$1,881, Sharpe ~3). Conviction sizing (Kaufman
Efficiency Ratio → 0/1/2 lots) turned grind flat-1-lot −$6,323 → walk-forward OOS +$1,162, the skipped
0-lot trades losing −$6,670 as a group. Pair walk-forward OOS +$1,978 (Sharpe 3.48). **All numbers are
optimistic 1m-ceiling — this arming is PAPER forward-validation on real fills, NOT real-money-ready.**

**Design A (single-position, first-to-fire) = robust:** no per-gate attribution on the shared MNQ net;
core's one-position guard + native 1-ATR stop + naked-watchdog + session-flatten all apply verbatim.
Two gates rarely want a position at the same instant (anti-correlated) so ~same P&L as concurrent, far
lower risk. Replay parity confirmed against 15-17 Jul: grind two-sided/chandelier-exit/conviction-sized,
rgv long/2R-target, total +$1,922 (no-slippage sanity, ~the backtest OOS).

**Build (gazbot7 `refactor/three-service`):** `config.py` GateSpec + `live_gates()`; `strategy.py`
two-gate `_pick_gate`/conviction `_entry`/per-gate `_manage` routing/`_active` (legacy single-gate path
untouched, `gates=[]` default); `sizing.py` (efficiency_ratio + conviction_lots); scope
`gazbot7/docs/GRIND_RGV_GOLIVE_SCOPE.md`. Commits `48af8d2`→`5a262a0`. 6 new tests + full suite (290)
green + replay parity. Also this session: exhaustion-reversal wired as observe-only shadow gate
(`footprint.py`, `c5fc7f9`); disk-full outage fixed (freed 18G); **rgv confirmed LONG-only** (two-sided
tested over the full 25d — SHORT −$1,271 raw, drags OOS +$1,881→+$978; reversion is asymmetric,
down-flushes revert / up-grinds don't); **V5 alerting layer RETIRED** (brain/janitor/dashboard/
market-data + ~17 timers disabled — Telegram noise gone; killed `alphabot-pipeline-reboot.timer`
that could bounce the shared V7 gateway; KEPT gateway + depth-capture; STATE §6 + commit `8345e339`).

**⚠ Watch at the Globex open (~22:00 UTC tonight) — first-hour:** (1) confirm a 2-lot order FILLS
(IBKR paper account size-limit unverifiable from here; a reject is safe + execution-integrity alarm
CRITs on it); (2) **kill-switches remain OFF** (paper-visibility choice — native 1-ATR stop still caps
each trade); (3) grind/rgv fills reprice honestly, expect paper P&L below the optimistic +$1,978.

**Revert (disarm):** in `strategy.py` `main()` set `RunConfig()` (empty `gates` → legacy thrust) OR
`git revert 5a262a0`, then `systemctl restart gazbot7-strategy`. No core change was made.

**Deploy:** `systemctl restart gazbot7-strategy` 2026-07-19 06:07 UTC (market closed, desk flat) →
clean start, NRestarts=0. Core untouched/healthy. Arms at the session open.

---

## 2026-07-18 — SHADOW-BOARD-AS-REGIME-ROUTER: built the shadow→live governor + damage-control, deep-dived grind_fast (kept, gated) + rg_long_fast_v (the +EV keeper), forward-validated. LIVE DESK UNTOUCHED — all V7 shadow research.

**What changed (A → B):** new `gazbot7/` research modules + tools (commits on `refactor/three-service`); **no live behaviour touched** (nothing armed). Started from the operator picking all 11 Monday-playbook actions as SHADOW; ended with a validated two-gate desk MODEL. Permanent decision recorded in `DECISIONS_V3_2.md §345`.

**Shipped (gazbot7, additive):**
- `router.py` (`31ddf68`+`c7e04df`) — per-contract regime router, shadow-first counterfactual; tuned so momentum runs ungated (its own trigger self-selects) and the router's real job is gating reversion. Counterfactual on the 2-day V7 board: +$1,830 → +$3,383 (NB the report's +$5,740 did NOT reproduce — flagged honestly).
- `chandelier_start_k` in `deciders.py` (`6376657`) — VOL-ADAPTIVE chandelier (trail width graded by entry ATR: tight 2.0 on high-ATR entries, wide 3.5 default). grind flat-3.5 −$7,975 → graded −$6,323 (+$1,653).
- `governor.py` (`7ddcbb8`, 6 tests) — the **shadow→live gate controller** (the operator's *"shadow becomes our regime router"* insight): live follows a gate's own recent shadow P&L; predictors window/sticky/streak/slope; **streak-win3 (arm after 3 consecutive shadow wins) is the best re-entry disciplinarian.** No look-ahead; flip-count = churn metric.
- `scripts/forward_validate.py` (`63b320c`) — walk-forward OOS harness, runnable on new captured days as they accumulate.

**The grind_fast interrogation (the session's centre of gravity).** grind is net −EV (−$6,323/25d) and its good/bad DAYS are un-predictable — proven exhaustively: tape/day-character (the MOST directional day was a big LOSER), amplitude (corr +0.06), 15-min regime, direction split (hindsight-real +$2,954 but reactive whipsaws to −$1,960), cross-gate, and a 4-agent OOS hunt on trade texture / equity geometry / cadence / ML combinations — all → **chance** (permutation tests + duty-matched-random baselines; the crucial finding: a slow-start green day dipping −$476 is geometrically identical to a red death-spiral at the decision point). **The fix was TOLERANCE, not prediction** (operator: *"there needs to be a tolerance built in, it can't predict perfection"*): the **peak-trail −$300 day-latch** stands grind down once it gives back $300 from the day's high — keeps every ~$1,300 day in full, cuts every bleed day to a small loss (−$1,239→−$43). Raw −$6,323 → **+$1,244** in-sample; **frozen −$300 = −$54 (breakeven) on the held-out last 12 days** (a re-tuned latch overfits to −$368 — don't re-tune it).

**rg_long_fast_v = the forward-validated +EV keeper.** LONG-only CHOP-reversion on the correct **2R exit** (operator rule: reversion needs 2R, not the chandelier): +$590/25d raw, +$988 on the 17 chop days, 15/25 green, +EV per-trade. Damage-controlled (flat −$400 latch) → in-sample +$1,201; **walk-forward OOS +$1,881 (better than in-sample) — it survives.** It is the MIRROR of grind (grind wants trend, rgv wants chop) → daily P&L corr **−0.62**; grind's big days cover rgv's worst days. Two-gate combined: +$1,107 OOS (frozen) / +$1,512 (walk-forward).

**The MODEL (DECISIONS §345):** the desk = a stable of thin (~$1–1.3k/mo), COMPLEMENTARY, forward-validated gates; the shadow board routes live capital to whichever is working; anti-correlation smooths the book; operator accepts the per-gate unit (*"$1300 per gate per month is stomachable"*). Next: a TREND-side gate that survives OOS to strengthen the pair with rgv (the report's exhaustion-reversal footprint / a better momentum entry). **Standing method locked: evaluate vs DUTY-MATCHED RANDOM (not always-on); forward/walk-forward with prior-only params before any promotion; sims stay on the known-optimistic 1m ceiling (~60-70% on real fills).**

**Revert:** no live change — all gazbot7 commits are additive research modules/tools; `git revert` any if unwanted. Memory: `shadow-board-as-regime-router`, `monday-shadow-build-queue`.

**Commits:** gazbot7 `refactor/three-service`: `31ddf68`, `c7e04df`, `6376657`, `7ddcbb8`, `63b320c` (+ the report/playbook chain `68b4b74`..`0691fa8` earlier this session). alphabot2: this SESSIONS entry + `DECISIONS_V3_2.md §345` + STATE §4/§6.

---

## 2026-07-17 — V5→V7 DOC CUTOVER: STATE.md refreshed to the live V7 desk; V5 retired to archive

**What changed (A → B):** `docs/STATE.md` rewritten from a V5 snapshot ("FLAT+HEALTHY / live-trading MNQ via `alphabot-broker`+`alphabot-strategy-daytrade`") **→ a V7 cutover pointer + verified V7 snapshot.** No code touched — documentation only. Operator directive this session: *"Refresh docs to V7."*

**Why:** STATE.md (last touched 07-15) still described the V5 desk as live, but verified live truth on 07-17 shows the desk has **migrated to GAZBOT V7** (`/home/alphabot/gazbot7`, the operator-approved clean-room rewrite): V5's `alphabot-broker` + `alphabot-strategy-daytrade` are **masked + inactive**; the running desk is `gazbot7-core/md/strategy/shadow/web`. `gazbot7/data/core_health.json` at 14:17 UTC = `place_live true, flat true, healthy true, protection.held false`. STATE was stale per Rule 4 — refreshed from code/health, not memory.

**Verified V7 state captured into STATE.md:** MNQ-only two-sided `thrust` (thr 1.5 / amp_floor 0.0004, 1m bars, 1s cadence, size 1); exit = native 1-ATR STP + tightening chandelier (k 3.5→0.5, tighten 0.75) + adverse-cut 1.5-ATR + absorption catastrophe backstop (min-loss $60); `entry_confirm_s=0` (45s veto killed live 07-17, `9c330b4`); kill-switches OFF for paper (go-live = daily 300 / streak 4); cutover via `GAZBOT7_PLACE_LIVE=1`; core clientId 7, md clientId 2 (read-only); ~23-variant shadow fleet on isolated `shadow.db`. V7 safety hardened same day (naked-position incident: `06349af` watchdog + `1d7e90f` arm-time stop-confirm + vanished-close reconstruct + `ba84f0d` repricer −€58k fix).

**⚠ CLAUDE.md §8 nine-cron maintenance ritual is now OBSOLETE for V7** — it probes the masked V5 `:8090` broker + V5 DB surfaces and would false-CRIT. Do NOT re-arm it verbatim. Obsolete/needs-V7-rework items flagged:
- FULL/LIGHT/RAMP **health sweeps** — probe `:8090`/`:8092`/`:8000` (V5 broker/MD/brain) + `data/alphabot.db` surfaces (P&L reconciliation, `fut_*` tables, capture_health on the V5 7-contract set). A V7 sweep must read `gazbot7` health/status + `gazbot7.db`/`capture.db` instead.
- **Nightly self-analysis** + **weekly interrogation report** crons — bound to V5 `desk_analysis`/`reports` tables + `/api/day|review` endpoints. (Friday report is separately reframed to the shadow-desk pipeline per memory `friday-shadow-workflow`.)
- **Saturday test-cleanup** — runs the V5 `alphabot2` suite; V7 has its own tests under `gazbot7/tests`.
- **BEACON + cron-liveness** — `alphabot-cron-liveness` is already FAILED; the whole session-cron mechanism needs re-pointing at V7 if wanted.

**Leftover V5 systemd timers still ACTIVE (flagged, NOT touched — needs operator call):** `alphabot-execution-monitor.timer` + `alphabot-pipeline-reboot.timer`. The reboot timer can `docker restart alphabot-gateway` (shared V7 infra) on a CRIT against the dead V5 broker — a false reboot would bounce V7.

**Revert:** `git checkout docs/STATE.md docs/SESSIONS.md` (documentation-only change; no runtime effect).

**Files:** `docs/STATE.md` (rewritten), `docs/SESSIONS.md` (this entry). Verified from: `gazbot7/src/gazbot7/config.py`, `gazbot7/data/core_health.json`+`status.json`, `gazbot7` systemd units, `systemctl is-active` (V5 broker/strategy = masked/inactive), `gazbot7` git log.

---

## 2026-07-15 (later) — CORRECTION: root-caused the 124 MNQ "bracket REJECTED" — it was NOT the MKT+native-trail (Error 328); it was the market-hours clock (70%) + wedge-window short-cap (30%)

**Correction to the record (no code change — investigation only).** While the desk was quiet, root-caused the 124 `bracket REJECTED` rows in `fut_entry_audit` that had been the leading explanation for the collapsed 07-15 through-rate (firing→trade 29%→9.6%→**2.7%**). The working assumption — carried into this session — was "we tried MKT buys with a native trailing stop, doesn't work (Error 328)." **The data refutes that for these 124.** Error 328 was the **07-14** incident (`b23c6224`, separately reverted); it explains **none** of the 07-15 rejections. The 124 (all 07-15) split into two unrelated causes:

- **87 (00h+01h, LONG) = `gate_market_open` rejected** — the desk was awake and firing clean overnight thrust signals, but the entry clock was set too narrow (`US_FUTURES` = 02:00–16:00 ET) so a guard vetoed every one as "CME market closed." **This — a mis-set trading window, not a plumbing fault — was 70% of the participation collapse.** Fixed the same day by the full-globex change (`ef2d24f3`, `US_FUTURES` → `17:00–16:00 CT`). ⚠ Proven in code, **NOT yet re-tested across a full overnight** — the next Globex night is the real confirmation.
- **37 (07h, SHORT) = `gate_sell_quantity_short_cap` rejected qty=2.0** — fired during the 07h wedge window. Read the gate logic directly (`risk.py:662-685`): it's `qty <= cap + held − working` with `cap=2` (correct `<=`, no off-by-one), so a 2-lot short on a **flat** book passes. The 07:28 rejects fired while positions were already open/working-sells in-flight (net-short cap legitimately reached) → mostly the guard working correctly amid the fill-stream chaos, not a live bug.

**The clincher: ZERO rejections of any kind after the 08:08 revert (`24a07d7d`) + restart, plus a clean real-time `fill` at 08:45.** Empirically both doors are open again in the running config.

**Honest caveat:** the broker bounced ~10× during the 07-15 wedge morning; can't fully rule out one brief stale-`cap=1` process among them. But the *current* broker (up since 08:55) enforces `cap=2` and the post-08:08 silence is the proof that matters.

**Net:** the 07-15 participation-killer was the too-narrow trading clock (fixed → globex) + wedge-window short-cap refusals (guard, mostly correct) — **not** MKT-vs-trail. No revert (docs/investigation only). Evidence: `fut_entry_audit` (124 rows, 07-15 00h/01h/07h), `alphabot-broker` journal (`gate_market_open` ×87, `gate_sell_quantity_short_cap` ×37), `risk.py:648-685`.

---

## 2026-07-15 — market-order tangle → reverted to marketable-limit + TRAIL (2% buffer); PIPELINE-HEALTH monitoring + auto-reboot; root cause = a wedged fill stream

**ROOT CAUSE of the day's mess:** the 04:37 IBKR Error-1100 **wedged the `execDetailsEvent` fill stream** → `OrderFilledV3` died → ~8h of every fill routing through the realtime-sync fallback → dropped closes → backfilled ~2min late as `RECONSTRUCTED_BACKFILL`, while EVERY existing check PASSED (the safety nets kept the outcome correct). Broker restarts didn't fix it (wedge was at the gateway); fixed by a **gateway reboot** (`docker restart alphabot-gateway` → broker → MD bounce → strategy). Verified `execDetailsEvent` re-subscribed.

**Market hours:** `US_FUTURES` window `02:00-16:00 ET` → **FULL globex** (`17:00-16:00 CT`, modelled on `CME_CRYPTO`) — `gate_market_open` was rejecting overnight entries as "CME market closed" (87 on 07-15) though the desk trades ~24h (ef2d24f3). Revert = restore the ET window.

**Entry:** an MKT + fixed-1-ATR-stop trial went live (accidentally, via a working-tree restart) then **REVERTED to marketable-limit + native TRAIL for ALL contracts** (24a07d7d) — the MKT+STP_LMT bracket didn't round-trip the broker recording/reconcile pipeline (executions unrecorded + STP_LMT unparseable on rehydrate → position-sync tangle + blind churn). Buffer **0.4%→2.0%** (operator "so wide it never blocks a fill"). Added a broker-truth **in-flight cap guard** (c45e6169). Back-end scope to make MKT work: `docs/MARKET_ORDER_BACKEND_SCOPE.md`.

**Monitoring (the "why didn't we know" fix):** `pipeline_health()` in the 10-min execution-monitor — DB backfill-dominance + journal fallback/`OrderFilledV3`-silent → CRIT Telegram (809c46bf). Plus **auto-gateway-reboot** behind `FUT_PIPELINE_AUTO_REBOOT_ENABLED` (root `alphabot-pipeline-reboot.timer`, 5-min; guards: confirmed CRIT + FLAT + 3h-cap; Telegram before+after) — **ARMED 2026-07-15** (0135bee6 + .env). Disarm = `.env false`. Gap analysis: `docs/PIPELINE_HEALTH_SWEEP_GAP_ANALYSIS.md`.

**P&L:** today's MNQ reconstructed from the fills to the true **−$885** (the tangle showed a corrupted −$3,960 realized); backfilled the missing 07:05→07:26 LONG round-trip (−$427, `scripts/sql/backfill_mnq_rt4_long_20260715.sql`, `agent_audit` 39815).

## 2026-07-14 (evening) — EXECUTION VISIBILITY caught a silently-DEAD desk (0 fills ~4h): short cap + Error 328 fixed; fill-based integrity alarm

The execution monitor (built earlier today) exposed within the hour that the LIVE desk had opened **ZERO positions since 15:54 (~4h)** — signals fired, none reached the market. Two stacked bugs + a monitor blind spot, all fixed. See DECISIONS §344.

**Short cap 1→2** (`alphabot/broker/risk.py::RiskLimits.max_futures_short_contracts`, commit `29c9d30c`). The 2-lot `MAX_CONTRACTS_PER_POSITION` bump (`ceb4cc89`, earlier today) left the broker short cap at 1, so every 2-lot SHORT was rejected by `gate_sell_quantity_short_cap` while 2-lot longs passed → desk silently long-only. Operator: *"if its the contracts go back to 1"* then *"go with your recommendation bump to 2"* → went with the bump. Enforced BROKER-side → needs a broker restart; deployed on a flat desk, broker reconnected HEALTHY. **Revert:** cap→1 (and `MAX_CONTRACTS_PER_POSITION`→1). **Invariant: the short cap must match the per-position lot cap.**

**Entry MKT → marketable-limit** (`us_futures_daytrade.py`, commit `b23c6224`). The full-market entry (LMT→MKT earlier today for guaranteed fills) is INCOMPATIBLE with the native trailing stop: IBKR **Error 328** ("trailing stop orders can be attached to limit or stop-limit orders only") → every bracket collapsed, no position at all (long OR short). This is the REAL cause of "0 fills since 15:54". Reverted to marketable-limit (0.4% through the market — aggressive, fills like a capped-slippage market order AND carries the native trail; IOC kept). Strategy restart; Error 328 confirmed gone. **Full-market would need a SOFTWARE trail, not the native one.**

**Integrity alarm — measure FILLS not submits** (`scripts/execution_monitor.py`, commit `267a9190`). The monitor stayed SILENT through all 4h because its through-rate counted SUBMITS as success (~100% while 0 filled). Added `_integrity_alarm`: CRITs on ACTUAL fills — any broker REJECT, or ≥3 submitted / 0 filled. Validated: CRIT on the broken window (6 submitted / 0 filled), silent on good + quiet windows. The 10-min `alphabot-execution-monitor.timer` now Telegrams within 10 min of execution breaking. Operator (VERBATIM): *"execution integrity has to be in your main sweeps. telegram me if i need to act."* Standing check in memory `execution-integrity-standing-check`.

**Verification PENDING:** the tape went quiet after each fix, so no live fill has confirmed the two entry fixes end-to-end yet (desk still 0 trades since 15:54). A one-shot watch is armed to Telegram Garrath the moment the first fill lands; definitive test = the Globex reopen / tomorrow.

## 2026-07-14 (Tue) — thrust_loose live · 1s cadence · execution monitor (Phase 1) · granularity investigation

**Live gate MNQ `thrust_cont` → `thrust_loose`** (thr 1.5 + no-expand). Honest tick-repriced shadow (`shadow_real`) had loose beating cont on EVERY overlapping day 07-10..07-14: +$5,823 real / 83% win / positive every single day / clean 3:1 tail (avg win +$80, avg loss −$25, worst −$46). Same logic that put cont live now points to loose. Three coordinated edits: `_THRUST_DECIDER_BY_SYM` MNQ→`tw_mnq_thrust_loose`, the gate-dispatch allowlist gains `thrust_loose`, `_ENTRY_GATES_BY_KEY` mnq→`(thrust_loose, orb_iso)`. `tw_mnq_thrust_cont` stays in the shadow fleet as the control. Deployed via strategy-daytrade restart on a flat desk; tests updated. Commit `e7fc0403`. **Revert:** restore the cont decider + gate tuple.

**Cadence 5s → 1s** (`_CADENCE_SECONDS`). Evaluate every second so entries fire on the freshest quote; signal bars stay 1m (thrust window unchanged — pure reaction speed). Commit `e821f5f6`. **Revert:** back to 5.

**Execution monitor — Phase 1** (operator: "great signals + terrible execution = no $; monitor every day; telegram if it dies"). We had NEVER checked whether signals actually reached the market. `scripts/execution_monitor.py` reconciles funnel(fires)→trades(opens)→executions(fills) into through-rate / adverse slippage / block-reasons for the live gate; persists to `fut_execution_health`; `alphabot-execution-monitor.timer` runs it every 10min (systemd, autonomous, survives a dead Claude session); Telegram ONLY on a CRIT (signals firing, ~none reaching market; 30-min cooldown); observe-only contracts never alarm; `/mnq` **EXEC** tab (`/api/futures/execution`). **Finding: MNQ through-rate last wk ~52% — half our signals were blocked** (already-held + cooldown — the limits loosened earlier today). Commit `9f4867e7`; units in `systemd/`. **Phase 1.5** — daily missed-signal would-be-P&L (`scripts/execution_missed_pnl.py` + `alphabot-execution-missed-pnl.timer` 22:15 UTC): sims each BLOCKED signal through the real exit stack on ticks (+ a sim-vs-actual calibration check); first run: today's 7 blocked signals would have LOST $103 — blocks protected us. Commit for Phase 1.5. **Phase 2 DONE** (`5bb1aa91`) — `plan_entry` takes an additive `_audit` dict (default None = no behaviour change) stamping the exact reason at every None-return; the driver logs every FIRED signal's outcome to `fut_entry_audit` (submitted / blocked-by-`<reason>` incl the session lockouts / observe_only + intended price). Best-effort throughout — a logging failure can never affect the entry path. Replaces the monitor's block inference with fact + gives true intended-price slippage. Tested (42 entry tests + synthetic + write round-trip), deployed on a flat desk.

**Granularity investigation (OPEN — for the Friday report, operator NOT closing it).** Tested whether faster bars beat the 1m gate for the thrust signal, every honest way: 5s time bars (noise wall ~1:10), volume bars (faithful sim +$1,914/7d but marginal, inferior to 1m), volume+efficiency-ratio (no crack), a 1m-trend filter that looked great (+$4,402) but was a **LOOK-AHEAD artifact** — the coarse 1m-bar close reads ~25s into the future; caught only when the operator insisted on testing the rolling version; the honest rolling/60s-smoothed trend does NOT discriminate winners from losers, and a rolling-1m-bar *substrate* is catastrophic (−$40k / 13.8k trades from over-firing a laggy smoothed signal). **Verdict: granularity cannot be lifted to beat the 1m gate for this signal — the edge lives in the discrete once-a-minute event structure.** Kept: volume bars ARE positive (not garbage); the **absorption cut is a real exit edge** (halved avg loss in the faithful sim). Scripts in scratchpad; full breakdown owed to Friday.

## 2026-07-14 (Tue) — execution limits loosened (operator): full-market entry + 4 throttles cut

After the audit of every gate between "signal fires" and "fill" (why the live desk took 27 thrust trades where
the sim took 189), the operator cut the execution throttles to let the gates actually participate:
- **FULL MARKET entry** (`entry_order_type` LMT→MKT, `entry_limit_price=None`) — guaranteed fill, no limit-miss
  (supersedes the marketable-limit+IOC; those go dormant, revert = MKT→LMT). Slippage now UNCAPPED on a spike;
  the 1.5-ATR adverse + absorption cuts are the net.
- **In-flight cooldown 300s → 10s** (`_INFLIGHT_COOLDOWN_S`) — the 5-min cooldown was sized for RESTING DAY
  limits; post-IOC/MKT an entry resolves in <1s, so 300s was locking a contract out for 5 min after any miss.
- **Reopen lockout OFF** (`FUT_REOPEN_LOCKOUT_ENABLED=false`) — same logic as the US-open lockout removed earlier;
  let the gates try the Globex-reopen runs. (Open lockout already off; **pre-open-flat KEPT ON** — operator wants
  flat into the US open: "too much risk holding into a hard gap".)
- **2 lots per position** (`MAX_CONTRACTS_PER_POSITION` 1→2) — IBKR nets, so this is 2 lots in ONE position, not
  2 brackets; still bounded by the €500/trade risk cap. Doubles per-trade exposure.

⚠ FOUR risk-increasing changes at once on the LIVE (paper) desk — the desk will now trade more, bigger, and fill
more aggressively; effect attribution will be muddy. 38 entry tests green; daemon restarted flat (NR=0). Reverts
are each one line (see the inline comments / .env flag).

**Commits:** futures_entry_driver.py + eurex_desk.py + us_futures_daytrade.py + STATE.md + SESSIONS.md (.env flag gitignored).

---

## 2026-07-14 (Tue) — IOC entry (kill stale-zombie fills) + US-open lockout REMOVED

**Trigger:** operator watched the **US-open down-flush** (MNQ 29812→29701, −111pt in 5min on 4-6× vol,
13:30-13:34 UTC) — *"why are we missing this big down run… and we just bought a long and got chopped… I
thought thrust was for sustained runs."* Two-bug forensic:

**Bug B (why we MISSED the flush): the US-open lockout.** thrust_cont fired SHORT correctly and repeatedly
through the flush (funnel 13:30:32-53, 13:31:35-13:32:00; sized every one) — but `FUT_OPEN_LOCKOUT_ENABLED`
(first 10min of the 09:30 ET open) **suppressed every submit**. The lockout dodges the opening whipsaw but
also blocks the cleanest directional opens. **Removed** per operator (`FUT_OPEN_LOCKOUT_ENABLED=false`) to see
if the gates can capture these runs. ⚠ the separate Globex-REOPEN lockout (30min) stays ON.

**Bug A (why we bought a LONG into the flush): a stale zombie entry order.** The 13:34 long had coid
`usfut-mnq-7df3c114` — **the SAME order as the 12:30 +220pt up-spike entry.** That BUY LMT @29717.5 never
filled on the spike (price ran past); the stop-coverage audit cancelled its stop/tp children but **left the
parent entry limit RESTING** (it was TIF=DAY). It sat for 4 minutes, and when the down-flush dragged price
back through 29717.5 it **finally filled — long, into a collapsing market** → instant absorption-cut. FIX: the
entry TIF is now **IOC** (`us_futures_daytrade.py` time_in_force DAY→IOC) — fill-now-or-cancel, so a missed
entry dies instead of resting to fill stale in the wrong regime. Complements the 0.4% marketable buffer
(fill aggressively now) — together = true fill-or-forget.

**Also: swept stale orders first (operator).** Broker `/orders` = 0 working, DB = 0 SUBMITTED entry parents —
venue + book both clean (the 13:34 zombie had already filled + closed). Nothing to cancel.

**The gates were RIGHT both times** (long the 12:30 up-spike, short the 13:34 down-flush) — we lost on
EXECUTION (stale limit, DAY TIF) + a GUARD (open lockout), not signal. 38 entry/lockout tests green; strategy
daemon restarted on a flat desk (NR=0, no lockout suppression).

**Revert:** entry TIF back to "DAY" (code) + `FUT_OPEN_LOCKOUT_ENABLED=true` (.env) + restart.

**Commits:** us_futures_daytrade.py (IOC) + STATE.md + SESSIONS.md. (.env lockout flag is gitignored — runtime.)

---

## 2026-07-14 (Tue) — MARKETABLE ENTRY widened 0.1% → 0.4% (stop missing explosive runs)

**What changed (A → B):** the FUT parent entry limit buffer **0.1% (fixed `_FUT_ENTRY_LMT_BUFFER=1.001`)
→ 0.4% (config knob `FUT_ENTRY_MARKETABLE_BUFFER_PCT=0.40`)**. The entry is a MARKETABLE limit priced this %
THROUGH the market (BUY above mid / SELL below) — now wide enough to fill like a capped market order on a
fast move. Applies to BOTH live gates (thrust_cont + orb_iso) and both sides. Made a live-tunable config knob
(reads `settings` at submit). Strategy daemon restarted on a flat desk; 48 entry/submitter tests green.

**Why (the smoking gun):** operator watched the **14:30 Paris +220pt vertical** (MNQ 29689→29910 in one minute,
10× volume) and asked "how did we not catch that?" Forensic: the gate fired a **perfect** thrust_cont LONG at
12:30:02 UTC at 29688 (net_atr 4.97) — signal was flawless. But the entry was a **limit BUY at 29717.5** that
stayed **SUBMITTED, never filled**: the price ran past 29717 during submit latency, so the limit rested BELOW a
fast market and never crossed back. 29s later the stop-coverage audit swept the orphan bracket. Net: perfect
signal, **ZERO fill**, desk flat through the whole run. Operator: "we can't be missing runs like this for a
tiny bit of slippage." The old 0.1% (~30pt on MNQ ≈ 2 ATR) was too tight to survive the latency; 0.4% (~120pt)
sits above the post-latency market so it fills, while still capping catastrophic slippage.

**Honest caveat:** this is deployed straight to the LIVE (paper) desk per operator ("we're in paper, make it
live now") — NOT shadow-proven first. It WILL slip up to 0.4% on the rare gap and occasionally buy nearer a
top; the 1.5-ATR adverse cut + absorption cut are the net for a bought-top that reverses. Watch the fill
quality over the next sessions — if normal-fire slippage creeps, tune the knob down. NB 0.4% is generous-%,
NOT the "2-3 ATR" first floated — 2-3 ATR ≈ the 0.1% that just missed, so it had to be wider.

**Revert:** set `FUT_ENTRY_MARKETABLE_BUFFER_PCT=0.10` (old behaviour) or lower + restart. Pure config, no code
revert needed.

**Commits:** config.py + us_futures_daytrade.py + STATE.md + SESSIONS.md.

---

## 2026-07-14 (Tue) — AMP-FLOOR A/B wired into the shadow fleet (3 MNQ thrust variants)

**What changed (A → B):** shadow fleet **20 → 23 sims.** Added `tw_mnq_thrust_floor04` (control, live 0.04),
`tw_mnq_thrust_floor03` (looser), `tw_mnq_thrust_floor00` (no floor) — all IDENTICAL to `tw_mnq_thrust_cont`
except the amplitude floor (parameterised via new `_amp_floor_blocks_at(fe, floor)` + `_mnq_thrust_at_floor`).
Registered in `shadow_strategies.STRATEGIES`; they inherit the default momentum exits (like the live thrust).
Strategy daemon restarted on a flat desk; 30 shadow tests green.

**Why:** operator forensic Q — *"is the amplitude floor making thrust jump in too late now?"* The analysis said
NO (entries right at the 0.04 floor had the HIGHEST mfe 4.71R; the live −$200 on 07-13 was chop/whipsaw —
15 immediate adverse cuts — not lateness), BUT the floor does reject ~40% of thrust signals that were still
mildly +EV. Verdict was **leaning, not confirmed** (114 shadow / 52 live, one chop day). So rather than touch
the live floor, we A/B it in shadow on HONEST fills and let the **Friday interrogation** arbitrate — the same
promotion discipline just reinstated on the veto.

**Data vs display split (important):** the SIM host (strategy daemon, restarted) now RECORDS all 3 variants
into `fut_shadow_sim_trades` — the A/B is collecting. But the DASHBOARD is a separate process (last started
07-13 21:10) so its in-memory `STRATEGIES` is stale → the /day shadow board still shows 20 until the dashboard
restarts. ⚠ `shadow_reconcile` will therefore report a transient **registered 23 vs shown 20** drift until the
dashboard is bounced — a known-benign consequence of this change, NOT a data fault. A dashboard restart drops
the operator's open /mnq tab, so it was deferred to operator convenience.

**Revert:** drop the 3 keys from `STRATEGIES` + restart. (The A/B is observe-only — nothing on the live desk
changed; the 0.04 floor stays live.)

**Commits:** shadow_strategies.py + STATE.md + SESSIONS.md.

---

## 2026-07-14 (Tue) — xconfirm_veto REMOVED from the live desk (back to thrust_cont + orb_iso)

**What changed (A → B):** `_ENTRY_GATES_BY_KEY["mnq"]` **("thrust_cont","orb_iso","xconfirm_veto") →
("thrust_cont","orb_iso")**. The live MNQ desk now fires on two gates, not three. Restarted
`alphabot-strategy-daytrade` on a flat desk (0 open); 13 gate/desk tests green; boot clean.

**Why:** operator — *"i was much too hasty with veto and i should stick with the Friday report process.
please remove it from the live desk and dashboard and we will just have thrust and orb."* `xconfirm_veto`
was promoted straight off sim 27 (2026-07-13) on a single good day (+$189.5/8tr honest) WITHOUT the
Friday-interrogation earn — exactly the promotion discipline the desk is supposed to hold to. It reverts to
being a SHADOW-only observation (`tw_xconfirm_veto`) and only re-arms if the Friday report earns it.

**Kept dormant (reversible):** the `_gate_xconfirm_veto` logic + `peer_net` plumbing in `futures_entry.py`/
`futures_entry_driver.py` stay in place (unused now); the `tw_xconfirm_veto` shadow sim keeps observing.

**Dashboard:** no restart needed — the /mnq armed-gate/DTT display is data-driven and already shows
thrust+orb only (no exposed live gate list named it; `_gate_distances` only ever drew thrust_cont/orb_iso
proximity). Today's earlier xconfirm_veto trades correctly remain in the historical gate-perf/blotter (they
did fire) and age out. (A dashboard restart would only sync its stale in-memory gate copy — cosmetic — and
would drop the operator's open tab, so skipped.)

**Revert:** add `"xconfirm_veto"` back to the mnq tuple in `_ENTRY_GATES_BY_KEY` + restart. But the operator's
intent is that it re-arms via the FRIDAY REPORT, not ad-hoc.

**Commits:** us_futures_desk.py gate tuple + STATE.md + SESSIONS.md.

---

## 2026-07-13 (Mon eve) — SHORTS RE-ARMED on the live desk (two-sided, all 3 MNQ gates) — reverses the morning disarm

**What changed (A → B):** `.env FUT_ENTRY_LONG_ONLY` **true → false**. The entry driver's `allows_short`
goes True → shorts flow two-sided through all 3 live MNQ gates (`thrust_cont` + `orb_iso` + `xconfirm_veto`).
Settings validated (`False`), strategy daemon restarted on a **flat desk** (0 open; a `gate_market_open`
"CME market closed" rejection confirms nothing fires until reopen — config armed for then). This UNDOES the
long-only disarm made ~2h earlier the same day.

**Why:** operator observed many of today's WINS were shorts and asked to re-arm. Verified the live tape first
(never guessed): today's shorts = **45 trades, 24 wins (53%), −$280 gross**; longs 15tr/12W(80%)/+$194. The
two squeeze monsters: **−$221 (06:53Z, exit=`MANUAL`** — a 1.6h hand-held that PREDATES the adverse cut, which
was only built 08:45Z `b6b755b7`, so it could never have been caught) and **−$127 (14:17Z, exit=`DAYTRADE_ADVERSE_CUT`**
— the cut fired and CAPPED it at ~1.5ATR; it was the worst adverse cut of the day, i.e. the floor, not a leak).
Re-arm rationale: (1) the desk's baseline design is two-sided momentum — this restores it; (2) the adverse-cut
(1.5ATR) + absorption cut are now LIVE and bound the tail (worst adverse today −$127, no runaways); (3) the
single worst loss was a MANUAL hold — unattended overnight there is no hand to hold it, so the adverse cut caps
that exact failure mode.

**Honest caveat (logged, not buried):** shorts still net **−$280 today WITH the caps live** — a grind, not a
catastrophe. Short momentum is +EV in honest shadow but individual squeeze losers remain unpredictable from
tape/book at entry (three independent honest negatives: give-back lock, pre-entry veto, tape+book forensic —
`SHORT_MOMENTUM_GATE_SCOPE.md §2b/§4b`). This re-arm trades the design-baseline two-sided book with the tail
now capped — not a proven per-trade short edge. Watch the dead-hours (04–07Z) shorts overnight.

**Also this session:** MNQ `/mnq` dashboard chart rebuilt — the hero panel is now a CSS grid (chart is a
guaranteed dominant row, so it can no longer collapse to the bottom when the ribbon/DTT populate; the ribbon
went single-row/no-wrap which was the squeeze cause), and the price line + **both axes** (5 price gridlines,
4 Paris-time ticks) + last-price pill now render in TRUE PIXEL-SPACE SVG (`viewBox` = host pixels) instead of a
stretched viewBox + fragile HTML overlays. Static-only (`?v=20260713e`), no dashboard restart.

**Revert:** `.env FUT_ENTRY_LONG_ONLY=true` + restart `alphabot-strategy-daytrade`.

**Commits:** docs-only (`.env` is gitignored — the substantive change is a runtime flag). STATE.md + SESSIONS.md
+ the `/mnq` static assets.

---

## 2026-07-13 (Mon) — SHORTS DISARMED on the live desk (long-only MNQ trial); shorts → shadow

**Why:** longs and shorts behave differently and can't share one mirrored gate. Live momentum-short was
asymmetric — MNQ shorts WON 61% but netted −$133 (win-small / lose-big squeeze tails: −$221/−$127/−$96),
while the honest shadow says short momentum IS +EV (`tw_mnq_thrust_cont` SHORT +$439/11tr, avg +$39.9). So
the live problem is uncontrolled SQUEEZE-TAIL risk, not absent edge — shorts go back to shadow to earn a
dedicated, non-mirrored gate.

**How (deliberately lighter than the documented disarm):** the note said `_LONG_SHORT_DISCIPLINES→frozenset()`
but that breaks 11 armed-state/plumbing pins and is a permanent statement. Instead added a reversible trial
flag `FUT_ENTRY_LONG_ONLY` (config) that the entry driver ANDs into `allows_short` (`futures_entry_driver.py`
run_open_sweep: `allows_short = eurex_desk.is_opted_in_live() and not settings.FUT_ENTRY_LONG_ONLY`). The
direction policy stays ARMED, so the short PLUMBING keeps its coverage and re-arm is one flag. Shorts still
run in shadow (they don't use the driver's `allows_short`). `.env FUT_ENTRY_LONG_ONLY=true`, restarted
(flat window, allows_short verified False). Re-arm = `false` + restart.

Also fixed 5 pre-existing test failures latent from the earlier MES/MGC benching (submitter/geometry/wire
tests build brackets on MES, which the observe-only gate now suppresses → monkeypatch-unbench for mechanics).
384 direction/short tests green. Next: `docs/SHORT_MOMENTUM_GATE_SCOPE.md` (a from-scratch short gate).

## 2026-07-13 (Mon) — Phase 3 (book-aware cut) RIPPED OUT — the evidence killed it; tape cut kept

Built a trade-by-trade evidence table (`book_vs_tape_vs_actual.py`, artifact published) over all 57 live
trades today, replaying the real tape: **ACTUAL −$161 · TAPE-cut-on-every-trade +$176 · BOOK-cut (Phase 3)
−$18.** The book gate was −$194 WORSE than tape — it suppressed good tape cuts because the absorption is
HIDDEN iceberg-refill (sold ~175 contracts/60s into a visible bid of ~4, price didn't move) that the top-10
depth SNAPSHOT cannot see. The tape directly measures flow-absorbed-no-price-move — it IS the right signal.
So Phase 3 was fully removed (config flags, params, `absorption_cut_fires(book_imbalance_dir)`,
`futures_runner._book_imbalance_dir`, desk wiring, tests). The **tape cut stays armed** and the **Phase 2
fast loop stays** (flag-off, now tape-only). 281 tests green; no restart (the flag was always off → live
behaviour unchanged). ⚠ Don't re-propose book-confirming the cut — aggregate L2 doesn't separate (same
finding that killed the pre-entry veto).

## 2026-07-13 (Mon) — absorption cut Phase 2 + 3 built (dedicated ~1s fast loop + book-aware), both flag-OFF

Operator: "finish the absorption cut phases." Clarified first that the cut is ALREADY live and executing —
the tape-based cut runs in the 5s exit spine and fired today (MNQ −$63.5). The phases are UPGRADES, built
flag-OFF so the live desk is byte-identical until armed:
- **Phase 3 — book-aware** (`FUT_ABSORPTION_CUT_USE_BOOK`, off): when armed + a fresh L2 book is present,
  the tape-absorbed signal must ALSO be confirmed by the directional top-5 book imbalance leaning against us
  (<= −`BOOK_IMB_MIN`); stale/absent book → tape-only (degrade-safe). Reuses the Phase-1 reader via
  `futures_runner._book_imbalance_dir`; new `absorption_cut_fires(book_imbalance_dir=...)` param.
- **Phase 2 — dedicated ~1s fast loop** (`FUT_ABSORPTION_CUT_FAST_LOOP_ENABLED`, off): a lean task spawned
  lazily from `step()` evaluates ONLY the cut via `FuturesRunner.evaluate_absorption_cut` (same reads + same
  pure signal, no state mutation) and cuts through the same `submit_market_exit` (resubmit-guard prevents a
  double-fire with the 5s spine, which stays the backstop). Interval `FUT_ABSORPTION_CUT_FAST_INTERVAL_S`=1s.

15 absorption pins + full runner/desk/strategy regression green (314). Committed `64cd8d69`. NOT restarted
(flags off → running desk unchanged). Also cancelled 10 orphan BUY-TRAIL cover-stops on the flat desk
(operator-authorised; verified flat first; broker open_orders 11→0). Revert: flags default off; delete the
Phase-2 loop + Phase-3 book param to fully undo.

## 2026-07-13 (Mon) — SIMPLIFY: 1-week MNQ-thrust-ONLY live desk + absorption cut ARMED (operator review)

**Why:** an evidence review with the operator (bad live week, wants to see green). The data was
decisive: shadow real_pnl `tw_mnq_thrust_cont` = **+$992/28tr (avg +$35.4)** dwarfs every other
contract/gate (MES thrust +$1.9/tr, MGC thrust thin), and shadow understates live losses — so MES/MGC
thrust bled live (07-13: MES −$94, MGC −$62; whole live desk −$258). MNQ's own bleed was dominated by
one −$221 manual outlier (a 97-min runner) — with a working safety net MNQ is green. Decision:
**concentrate the live desk on the one proven edge for a week; everything else runs in shadow.**

**Changes (all applied via a clean-flat-window strategy restart):**
- **Live desk = MNQ only.** `_ENTRY_GATES_BY_KEY["mnq"]` = `("thrust_cont", "orb_iso")` — both amp-floored
  0.04; the generic momentum gate stays OFF. thrust routes to `tw_mnq_thrust_cont` (shadow +$992/28tr); orb
  kept because MNQ orb_iso live is **+$47/7tr, 71% win** since go-live (operator: "orb mnq with floor had
  great edge" — confirmed; today's −$69/3tr was a thin patch inside a net-positive gate).
- **MES + MGC benched observe-only** via `OBSERVE_ONLY_CONTRACTS` (now `mes,mgc,m2k,mym,mcl,mbt`) — they keep
  evaluating thrust_cont into the funnel/shadow, submit suppressed (the consistent mechanism, NOT emptied
  gate tuples — those would silence the shadow too).
- **Absorption cut ARMED** — `.env FUT_ABSORPTION_CUT_ENABLED=true` (tape-based, 5s spine cadence for now;
  pre-empts the 1.5-ATR adverse-cut on absorbed flow while offside). The observe harness caught real
  would-cuts today (MNQ short, +621 net sold, price −5.25 against it).
- Considered + REVERTED mid-review: adding the floored `momentum_shadow` gate to MNQ (operator asked, then
  pulled back — "thrust only, i want to see green"). The `_gate_shadow_momentum` routing for it was reverted
  to keep the code clean; re-add path noted in the `_ENTRY_GATES_BY_KEY` comment.
- Tests: `test_per_contract_entry_routing.py` updated (MNQ thrust-only; only MNQ live-traded); 33 pins green.

**Revert to the 3-contract momentum desk:** drop `mes`,`mgc` from `OBSERVE_ONLY_CONTRACTS`; `mnq` →
`("thrust_cont","orb_iso")`; `FUT_ABSORPTION_CUT_ENABLED=false`; restart `alphabot-strategy-daytrade`.

## 2026-07-13 (Mon) — L2 book consumption Phase 1: reader + book features + observe (SCOPED then BUILT)

**Why:** operator pushed back on the tape-only absorption cut — *"is aggressor tape as useful as the
book? the desk needs to read L2 live."* Honest answer: no — tape is executed/backward-looking, the
book is resting/forward-looking, and absorption IS a book event. Scoped `docs/DESK_L2_BOOK_CONSUMPTION_SCOPE.md`,
then built Phase 1. Decisions locked: **no entry veto** (the pre-entry study showed book/tape don't
separate winners from losers before entry); **one consumer** = the book-aware absorption cut; **1s
cadence via a dedicated fast loop** (Option ②, leave the 5s runner alone — ratchets/chandelier don't
need speed, the reactive cut does); **M2K out** (no operator L2 entitlement) → scope MNQ/MES/MGC.

**Key unlock — consumption, not acquisition.** The live 10-level book ALREADY exists on the 3 traded
contracts: `alphabot-depth-capture` (clientId 97, `reqMktDepth`, isolated) writes `depth.db` — WAL,
~0.25s snapshots, ~1s fresh — the desk just doesn't read it. A latest-book read is 0.010ms.

**Built Phase 1 (PAPER, no decision wiring):**
- `alphabot/shared/book_features.py` — `BookSnapshot` + pure features (multi-level `depth_imbalance`,
  `microprice`/`microprice_tilt`, `opposing_wall` = biggest resting level on the side WE consume,
  `near_consumed_size`, `directional` orientation) + `read_latest_book()` — the single degrade-safe
  reader with a **2s STALENESS GUARD** (frozen/absent/corrupt book → None, can never force/block a trade).
- `tests/test_book_features.py` — 16 pins (math + staleness/missing/corrupt → None). Verified live
  on the real book (e.g. MES 92-lot bid wall 1.38 below mid — the thing tape cannot see).
- `scripts/absorption_observe.py` extended to log the FULL book vector per open position
  (`book_imb1/10`, `micro_tilt`, `opp_wall_size/dist`, `near_size`, `book_spread`, `book_age_s`) so
  labeled data accumulates now. Needed a `sys.path.insert` repo-root bootstrap to import `alphabot`
  when run as a script (alphabot isn't pip-installed). Running detached, read-only.

**Next:** Phase 2 = the dedicated ~1s reactive-cut loop on the existing tape cut (prove the plumbing);
Phase 3 = make it book-aware (`FUT_ABSORPTION_CUT_USE_BOOK`), observe, arm on evidence. **Revert:**
Phase 1 is pure/observe-only — nothing armed; delete the module + harness cols to undo.

## 2026-07-13 (Mon) — absorption cut (live, flag-OFF) + short-guard observe harness (microstructure forensic)

**What prompted it:** the go-live desk's first days netted ~$24 but the SHORT book bled — **7/7
longs won (+$272), 14/28 shorts lost (−$248)**. A deep forensic on the day's 9 adverse-cut/manual
losers (all SHORTS) across the full L2 book + aggressor tape, plus web research on how order-flow
practitioners use this data. Three findings drove the build:
1. **Absorption is a real EXIT signal** — simulating an absorption cut (heavy aggressor flow OUR
   WAY that fails to move price, while offside) on the 9 losers would have cut the **MNQ −$221 at
   20s for ~$0** and saved **~$308 (41%)**. Partial (fired on 3/9 — the flow-heavy squeezes; missed
   the thin drifts), but it caught the worst. Matches the literature: order-book imbalance leads
   price over SECONDS, so the book is an exit/timing tool, not a multi-minute entry predictor.
2. **L2 as an ENTRY veto does NOT work** — a full pre-entry feature battery (multi-window OFI, book
   imbalance L1/5/10, opposing-wall, spread, micro-price, pre-vol, intensity) did NOT separate
   winners from losers at the entry instant; the "best" veto thresholds were in-sample overfits on
   35 trades. So NO entry veto was built.
3. **The short bleed is regime, and my first hypothesis was FALSIFIED** — I expected losing shorts
   to fade an up-grind; instead nearly all shorts fired WITH the downtrend / below VWAP. The real
   tell: losing shorts were more OVER-EXTENDED (30m trend −0.50% vs −0.23%; ~2× climactic volume) —
   they chase an exhausted down-move into the bounce. But a static extension guard is regime-fragile
   (wins on a reversion day, bleeds on a trend-down day), so it is NOT armed — instrumented instead.

**Built (all PAPER, nothing armed):**
- **Absorption cut — a live exit mechanism, flag-OFF (`FUT_ABSORPTION_CUT_ENABLED=false`).** A new
  pure `absorption_cut_fires` in `futures_stop_logic.py`, placed in the spine BEFORE the adverse-cut
  so it pre-empts (cuts in seconds vs the −1.5 ATR excursion). Tape-only by necessity — **there is NO
  live L2 book in the running system** (`depth.db` is offline research capture only) — so the runner
  reads the aggressor tape (`ticks.db`) over a 60s window via a new `_recent_tape()` (mirrors
  `_recent_mids`, read-only, gated on the enable flag → no DB hit when off, degrade-safe to no-fire).
  Wired from settings in `stop_params_for`, PRESERVED under the archetype override (like the
  adverse-cut). Reason `DAYTRADE_ABSORPTION_CUT` registered STOP-family in `exit_reason_ev.py`.
  11 new pins in `tests/test_absorption_cut.py`; full stop-logic/runner/desk suite green (86).
  **DEFAULT OFF = byte-identical.** Arm = `FUT_ABSORPTION_CUT_ENABLED=true` (+ optional
  `FUT_ABSORPTION_CUT_FLOW_MIN`/`_WINDOW_S`) in .env + restart `alphabot-strategy-daytrade`.
- **Short-guard folded into the observe harness (`scripts/absorption_observe.py`, running, read-only).**
  Now also logs, per open position, the ENTRY-TIME context that tests the exhaustion hypothesis:
  `ext_vwap_pct` (vs trailing-90m VWAP), `trend30_pct`/`trend60_pct`, `pre_vol30`, `vol_ratio`
  (climactic proxy) — cached per position. Writes to its own gitignored `data/absorption_observe.db`.
  This proves BOTH the absorption exit AND the extension/exhaustion short-guard across regimes before
  either touches live trading.

**Revert:** absorption cut off by default (no revert needed). If armed → `FUT_ABSORPTION_CUT_ENABLED=false`
+ restart. The observe harness is read-only and takes no trading action; kill the process to stop it.

## 2026-07-13 (Mon) — naked-position safety spine: auto-protect shorts + alert + the root fix (3 commits)

**Incident that triggered it:** a live MGC SHORT went NAKED at entry (its bracket stop
cancelled ~5ms after the fill) and bled to −$110 with **no auto-remediation and no operator
page** — caught only because the operator watched the dashboard. Manually flattened (−$64).
Then a full root-cause + 3-layer fix (all PAPER, deployed via a broker restart on a clean flat window).

**Fix #1 — auto-protect a naked short (`d439a7f8`).** The re-attach was long-only (always a
SELL stop; a short crashed `OrderIntent` on the negative qty), so `reconcile` refused + paused.
But the stop EXECUTOR was already direction-aware (`_stp_side = SELL if qty>=0 else BUY`, abs qty).
The real gaps: the stop PRICE (`compute_atr_stop_price`) computed below-entry only, and the
reconcile gate. Now: `compute_atr_stop_price(is_short=…)` mirrors the stop ABOVE entry (verified
symmetric — long 4053.23 / short 4063.77 around 4058.5); `attach_stop` derives `is_short` from the
signed `position_qty`; and the naked-SHORT handler in `_handle_naked_flatten` RE-ATTACHES a BUY-cover
stop instead of pausing. A **resting** stop (not a market cover) is safe even on a false-positive
naked read — it only fills if price actually runs against the short, whereas a market BUY-cover off a
stale snapshot would buy into a possibly-covered short → a new naked LONG. Falls back to the old
pause ONLY if the re-attach placement fails.

**Fix #2 — page the operator (`d439a7f8`).** Any naked detection now fires an UNGATED
`send_panic_alert` Telegram (always sends, independent of `TELEGRAM_AUTO_ALERTS_ENABLED`), ONCE per
event (deduped on naked.key, cleared when the position clears), fire-and-forget so it never blocks
the re-attach. Before: it only `log.critical`'d + set a status flag → silent. Covers both the short
re-attach and the long auto-flatten.

**Fix #3 — the ROOT: why it went naked at all (`d28a3127`).** A parallel forensic trace (evidence-
matched to the DB order rows) found it: a prior OCO/bracket close ZEROES the position row rather than
deleting it; a subsequent SHORT re-entry (SELL-to-open) onto that `quantity=0` "zombie" matched NONE
of `apply_fill`'s branches and fell through to a raise → `on_fill_event` SWALLOWS it (force-close-race
branch) → the short is never booked → `compute_stale_bracket_children_on_flat` reads the symbol as
FLAT and cancels the bracket's LIVE trail ~5ms after the fill → NAKED at entry. Short-specific (the
BUY re-entry onto a zombie was already handled by Y156b; only SELL raised). Fix: mirror the BUY
re-open — route a SELL-to-open onto a zombie through `_open_new` (signs qty negative, enforces the
`allows_short` guard). Now the short is booked, so the sweep sees it OPEN and keeps the stop.

**Verify:** ~1000 tests pass across fill/positions/orders/shorts/bracket/stop-coverage/sizing —
incl. new: direction-aware stop-price symmetry, naked-short re-attaches-and-is-protected /
falls-back-to-pause-on-failure, SELL-onto-zombie-reopens-a-short (long-only still raises). No
regressions. Deployed on a flat window; broker HEALTHY, strategy reconnected, all services green.
STATE §3 rewritten as the 3-layer spine.

**Revert:** `git revert d28a3127 d439a7f8` (all three are additive guards; reverting restores the
pre-2026-07-13 behaviour — a naked short pauses + is left for the operator).

---

## 2026-07-13 (Mon) — trade-pings, adverse-cut ARMED live, backfill/funnel fixes + the MGC px=0 incident

A busy live-desk session (all PAPER). Chronological:

**1. Trade-pings — operator Telegram on each LIVE closed round-trip (`34f4182c`).** New
`broker/trade_ping.py`, hooked into `main.py::_persist_completed_trade`. Per closed trade:
symbol, side, net P&L, gate, hold + running Paris-day total. Gated by
`TELEGRAM_TRADE_PINGS_ENABLED` (armed in .env). LIVE desk only (shadows write to
`fut_shadow_sim_trades`, never `record_trade` → no flood). Net-of-fees matches the dashboard
(gross − flat $1.50/RT). Fire-and-forget; a notify hiccup can't touch persistence.
**Revert:** `TELEGRAM_TRADE_PINGS_ENABLED=false` + broker restart. *Known gap:* backfilled
closes (`RECONSTRUCTED_BACKFILL`) don't ping (the hook is the real-time path only).

**2. INCIDENT — MGC close shown as −$40,658 (px=0 VCORR), hand-repaired live.** My 05:47
broker restart landed ~9s into an MGC fill → the reconciler minted a synthetic `VCORR`
execution with **price=0.0** (`ledger_writer.py:315` falls through to 0.0 when IBKR avg_cost
is unavailable). The projector turned that into an entry=0 round-trip; `dropped_trade_backfill`
recorded a SHORT "sold at 0, covered at 4065.8" = a phantom −$40,658 that swamped the header.
Every backfill cycle re-derived it, clobbering point-fixes. **Durable live fix:** corrected the
VCORR execution `price 0.0→4067.3` (the real fill, from `fills`) + `trades` id 5891
`pnl_usd −40658→+15.0, entry_price 0→4067.3` (all snapshotted). Also the sibling casualties:
`positions.opened_at` rewritten ~10s late by the restart made the dashboard drop the MGC
holding card (its fills-VWAP filter `fill.filled_at >= opened_at` excluded the real fill) →
corrected opened_at to the true fill time. **Lesson:** never restart the broker within seconds
of a fill — gate on a genuinely clean flat window (no position AND no working order).

**3. Backfill px=0 guard — Layer B (`dd46d473`).** `find_dropped_trades` now repairs a px≤0
leg from the `fills` price (recomputing pnl) or REFUSES to insert (leaves it visibly MISSING —
safer than a phantom loss). Prevents recurrence of #2. 10 tests. Layer A (upstream VCORR
minting) scoped-not-built: `docs/BACKFILL_PX0_GUARD_SCOPE.md`.

**4. MNQ manual flatten (−$221) + orphan-TP cleanup.** A momentum MNQ short went wrong from
entry and meandered 88 min to −$215 (heading to its −$300 stop). Operator directed a manual
flatten → covered @ 29727 (−$221, `exit_reason=MANUAL`, real-time). 3 orphan MGC `_tp` orders
lingered (phantom — `ibkr_order_id=None`, never at IBKR, can't fill); the cancel 404'd, they
cleared themselves via reconcile.

**5. Adverse-cut — a FAILED-ENTRY fast cut, BUILT + ARMED LIVE (`b6b755b7`).** Motivated by #4
and the data: `DAYTRADE_FLAT_CLOCK` is the desk's #1 loss bucket (−$13.7k / 624 trades). New
`FUT_ADVERSE_CUT_ATR` (default 0=off, **armed .env=1.5**): a position ≥ N×entry_atr offside AND
never went meaningfully green (peak < 0.5 ATR) is cut at market (`DAYTRADE_ADVERSE_CUT`).
Orthogonal to the chandelier (can't clip a winner); SURVIVES the archetype override. Pure
`adverse_cut_fires()` in `futures_stop_logic`, spine call after profit-lock/before force-kill,
family→STOP, runner unchanged. 10 tests, 100 pass across stop-logic/desk, no regressions.
Worked example (the MNQ above): would've fired ~6 min in for −$41 vs −$221. **Revert:**
`FUT_ADVERSE_CUT_ATR=0` + strategy restart. *Live on unit-tests + logic, not a shadow
forward-test (operator call) — watch it doesn't cut dip-then-recover winners.*

**6. Funnel un-blind — thrust_cont was logging `_no_bars` (`f6d70436`).** Since go-live,
`fut_signal_funnel` recorded `thrust_cont_no_bars` every cycle: the funnel-capture call
(`futures_entry_driver.py:789`) omitted `bars`/`sym` while the LIVE entry call (`:343`) passed
them. **Diagnostics-only — no trade was ever suppressed;** the board was just blind to the real
thrust_cont verdict (and made an "MCL 0 firings" read misleading). Fixed by threading
`bars=bars, sym=key.upper()`. Verified live post-restart: 98 funnel rows, all real
`thrust_cont_no_entry`, 0 `_no_bars`. 5 tests.

**Net desk today:** +$331, 12/13 green (the manually-cut MNQ the only red). Two strategy
restarts (08:46 adverse-cut, 09:22 funnel fix) + earlier broker/dashboard restarts, all on
flat windows, all verified clean.

---

## 2026-07-13 (Mon) — fix: /futures cockpit rendered BLANK (two causes)

**Symptom (operator, overnight):** the `/futures` dashboard "shows nothing" on the
phone. Desk itself was fine (broker HEALTHY, first-night +$153.50, zero naked) — this
was **dashboard-display-only**. Root cause: `/api/futures/performance` hung 8–30s and
blew past the frontend fetch timeout → the panel never populated. TWO independent causes:

**Cause 1 — crypto shared-client poison (`broker_proxy.py`).** Crypto is retired
(`DAYTRADE_CRYPTO_ENABLED=false`) but `BrokerProxy` still probed the decommissioned
:8091 broker. That dead call raised `TransportError` → `_get_json` called
`_reset_client()`, which disposed the **shared** httpx client and poisoned the concurrent
:8090 IBKR calls (the ":8090 transport error ()" cascade). **Fix:** skip all crypto
probes when crypto is disabled (`base == self._crypto_url and not self._crypto_enabled →
return None`). No more shared-client poison.

**Cause 2 — uncached 3.3s gate leaderboard (`routes_futures_terminal.py`).**
`_gates_leaderboard` (the GATES column: top/bottom/long-short per day/week/all) costs
~3.3s per call — it rescans the whole `trades` table and re-resolves the entry gate for
every trade (`_batch_entry_gates`), **every request**. Under repeated cockpit polls the
calls serialised (measured 8s → 13s → 18s across 3 back-to-back hits). **Fix:** cache the
gate_block per Paris-day (`_GATE_BLOCK_CACHE`) with a 30s TTL + a single-flight
`asyncio.Lock` (concurrent misses don't all recompute). The cheap 0.01s recs/header/
rolling query stays LIVE, so the P&L header the operator watches is never stale.

**Verify:** warm hits **0.015s** (was 8–18s); 6 concurrent cold hits all **~5.2s flat**
(single-flight, no stacking to 30s); payload complete (today +153.5, 2885 trades, 4
today); no :8091 cascade in logs; `/futures` + `/terminal` + `/integrity` all 200.
Dashboard restarted (operator asleep — no live tab to drop).

**Why:** the cockpit is the operator's only window on the live go-live desk; a blank
dashboard during the first unattended nights is unacceptable. Commit `f568296a`.

**Revert:** `git revert f568296a` (both are pure dashboard-read changes; reverting
re-exposes the blank-cockpit hang, nothing trade-path). TTL knob: `_GATE_BLOCK_TTL_S`.

---

## 2026-07-12 (Sun) — fix: family_map product bug (DAYTRADE_PROFIT_LOCK)

**What changed (A → B):** the live exit_reason `DAYTRADE_PROFIT_LOCK` (14 trades, net
+$24) was absent from `intelligence/exit_reason_ev.EXIT_REASON_FAMILIES` → `family_for()`
returned UNKNOWN → the day-review/courtroom/exit-EV surfaces couldn't classify it. Added
it to **PROFIT_TARGET** (it banks a give-back off the peak — same family as the ratchets).
Fixed the CODE (map), not the test (the test correctly caught the gap). All 30 distinct
live exit_reasons now map (UNMAPPED: NONE). Brain restarted to reload the module (live).

**Why:** a real STATE §6 product bug (analytics-currency, CLAUDE.md §3 item-8). Commit `d8d5ea7c`.

**Verify:** `family_for('exit:DAYTRADE_PROFIT_LOCK')` → PROFIT_TARGET; test 16/16; brain
NR=0 + health 200. Dashboard picks it up on its next restart.

---

## 2026-07-12 (Sun) — go-live-drift test cleanup

**What changed (A → B):** fixed the tests left stale by the 2026-07-11 go-live (they
asserted the pre-go-live fade config). Verified each against the live config, not
fix-to-green. UPDATED: `test_per_contract_entry_routing` (rewritten to momentum:
thrust_cont + orb_iso on MNQ, flat-clock disabled under archetype), `test_drop_us_futures_desk`
(7 active contracts, MET/MSL sidelined), `test_profit_lock`/`test_force_kill` (wiring
tested in the archetype-off revert path + the go-live override pinned), `test_shadow_sim`
(dip_loose→dip_loose_absorption). MOVED to `_RETIRED/`: `test_per_contract_entry_tuning`,
`test_ratchet_atr_mult_per_contract`, `test_pullback_loose_shadow` (retired mechanisms).

**Why:** completes the go-live's test-update debt (CLAUDE.md §3 item-7 — a behaviour
change owns its test updates). Commit `6e5fae7c`.

**FLAGGED, not fixed:** `test_y214_phase2_equity_replay` (near_miss maturity-guard tested
with retired equity disciplines — data staleness, separate class); the DB-isolation flaky
tests (pre-existing, fail on parent); the 2 real product bugs (dropped-trade-backfill,
family_map). See STATE §6.

**Verify:** 65 passed, ruff clean. **Commits:** `6e5fae7c` + this doc update.

---

## 2026-07-12 (Sun) — §2 retirement cleanup, Phase 2 (the equity daytrade subsystem)

**What changed (A → B):** removed the entire equity/crypto DayTrade engine from the
live tree (scope `docs/RETIREMENT_DEADCODE_ARCHIVAL_SCOPE.md` Phase 2). It ran INERT on
the 100%-futures desk — the futures strategies self-manage entries+stops via
`FuturesRunner`/`FuturesBrokerAdapter` and compute regime inline; they never used
`DayTradeStrategyBase`, `DayTradeStopRunner`, or the daytrade gate caches. **Operator
directed: do it now, forensically, this weekend, fix Monday if it breaks (paper desk).**
Zero behaviour change.

- **Forensic map first:** 3 parallel audits established the subsystem boundary, the boot
  architecture (futures loader is standalone + already futures-only), and the shared-file
  seams — BEFORE any edit.
- **Pruned 3 MIXED seams in place** (they imported the subsystem): `_daemon_common.py`
  (removed the `daemon_name=="daytrade"` stop-runner + gate/regime/catalyst/direction
  loops + teardown), `shared/markets/registry.py` (removed the 8 equity profile builders,
  emptied `_REGISTRY_BUILDERS`), `signals/registry.py` (removed the daytrade gate
  registrations; swing engine stays).
- **Archived → `_RETIRED/`** (git mv): the `daytrade/` package (`_base`, `_base_types`,
  `_sizing`, `_daytrade_helpers`, `__init__`), `daytrade_stop_runner`, `signals/`
  `{daytrade_gate_adapter, gate_pipeline, gates, catalyst, regime, hkex/tse/korea/germany_gates,
  direction_refresh}`, `broker/daytrade_stops`.
- **Tests:** 68 triaged (63 moved, 5 pruned-in-place to keep live coverage) + 4 more
  fully-dead moved in the `9216e622` follow-up.

**Why:** §2 archival — inert dead-weight removal so the tree matches the 100%-futures
reality. Legibility + removes the hazard of dead equity code beside live futures paths.

**Verify:** 3 forensic audits; all 5 daemons import clean; collection clean; the surgical
files 87 passed; ruff clean. **LIVE SMOKE GREEN:** broker+MD+strategy+dashboard restarted,
NRestarts=0, broker HEALTHY+flat, `us_futures_daytrade_v1` engine running, IBKR feed
recording ticks, dashboard `/futures` 200.

**Deferred (bounded, desk unaffected):** 35 stale equity tests in 12 partial files need
surgical pruning (`docs/phase2_test_debt_followup.txt`); `config.py` dead pass-mark
constants (Stage A4, high-blast-radius/low-value); the `direction_snapshots` shadow dropped.
NB the desk's other ~13 failing test files are PRE-EXISTING go-live config-drift + STATE
§6 flags (confirmed via parent-commit diff) — not Phase 2.

**Revert:** `git revert 9216e622 c1d4c7e5` restores the whole subsystem + seams; restart
the strategy daemon.

**Commits:** `c1d4c7e5` (main), `9216e622` (test follow-up) + the doc updates.

---

## 2026-07-12 (Sun) — §2 retirement cleanup, Phase 1 (binance broker-proxy + WS source)

**What changed (A → B):** severed the two gated-dormant binance modules from the live
daemons, then archived them. Both were gated off (`DAYTRADE_CRYPTO_ENABLED` /
`MARKET_DATA_BINANCE_ENABLED`, both false), so the removed branches were already dead —
zero behaviour change.
- **Sever (in-place):** `strategy/_daemon_common.py` — dropped the `MultiBrokerProxy`
  import + the `if DAYTRADE_CRYPTO_ENABLED` build, collapsed to `daytrade_broker =
  ctx.ibkr_broker` (the else-branch that already ran). `market_data_daemon/daemon.py` —
  dropped the `BinanceWSSource` import, its gated instantiation, and its `start()`.
- **Archive → `_RETIRED/`:** `strategy/multi_broker_proxy.py`,
  `market_data_daemon/sources/binance_ws.py`.
- **Tests (9 dependents):** 6 pure-proxy/source + HKEX/TSE-integration moved wholesale;
  `test_drop_inc_orderstorm` trimmed (2 proxy tests out, 14 live order-storm guards kept);
  `y143`/`y129` left (string-only `binance_ws` in mock fixtures, no import — still green).

**Why:** §2 archival, Phase 1 (scope `docs/RETIREMENT_DEADCODE_ARCHIVAL_SCOPE.md`).
Inert dead-weight removal so the tree matches the 100%-futures reality.

**Verify:** all 5 daemons import clean; collection clean; trimmed test 14/14. market-data
+ strategy restarted clean (NRestarts=0, broker HEALTHY+flat, IBKR feed reconnected +
recording ticks). Kept the `CRYPTO/BINANCE` `.env` gates + config fields (Phase 2 strip).

**Revert:** `git revert 11ef03a3` (restores both modules + the daemon branches).

**Commits:** `11ef03a3` (code) + the doc updates. Scope Phase 1.

---

## 2026-07-12 (Sun) — §2 retirement cleanup, Phase 0 (dead-code archival)

**What changed (A → B):** first execution phase of the §2 dead-code archival (scope:
`docs/RETIREMENT_DEADCODE_ARCHIVAL_SCOPE.md`). Archived the dead §212 equity
short-edge/regime-capture cluster + `narrator` out of the live tree; cut 8 orphaned
`CRYPTO_*` `.env` keys.
- **Code (`d59e2f4f`):** `git mv → _RETIRED/` — `intelligence/{narrator,crypto_edge,short_edge,regime_context}.py`
  + tests `test_crypto_edge.py`, `test_regime_capture.py`. History preserved (pure renames).
- **`.env` (box-only, not in git):** removed `CRYPTO_STOP_KIND`, `CRYPTO_LIQUIDITY_FLOOR_ENABLED`,
  `CRYPTO_BTC_NOT_AGAINST_ENABLED`, `CRYPTO_TREND_HTF_ENABLED`, `CRYPTO_TREND_15M_EMA_ENABLED`,
  `CRYPTO_WS_PRICE_ENABLED`, `CRYPTO_BTC_NOT_AGAINST_TOLERANCE_PCT`, `DAYTRADE_CYCLE_SECONDS_CRYPTO`
  (all 0 live consumers). Backup: `/home/alphabot/backups/code/.env.bak-pre-phase0-*`.

**Why:** inert dead-weight removal so the tree matches the 100%-futures reality. Nothing
trades this code; zero behaviour change.

**Two deviations from scope (both verified):** ADDED `regime_context.py` (audit missed it;
same dead cluster); KEPT `binance_source.py` (deliberate Y52 loud-tombstone, a live test
asserts it). See the scope doc Phase 0 note.

**Verify:** all 5 daemons import clean; pytest collection clean (`testpaths=[tests]`
excludes `_RETIRED`); live router test 18/18; `.env` parses (futures gate True, crypto
False). No regressions — the 1 unrelated fail is the known STATE §6 `family_map`
`exit:DAYTRADE_PROFIT_LOCK` gap. No restart needed (orphaned keys).

**Revert:** `git revert d59e2f4f` (restores the modules) + restore the `.env` backup.

**Commits:** `d59e2f4f` (code) + the doc updates. Scope: `docs/RETIREMENT_DEADCODE_ARCHIVAL_SCOPE.md` Phase 0.

---

## 2026-07-12 (Sun) — DB VACUUM (maintenance; punch-list §1)

**What changed (A → B):** ran the deferred VACUUM on `data/alphabot.db` in a full
maintenance freeze (Sun, desk flat, ~8 h before the 22:00 UTC reopen). Froze all
writers — the 5 services **plus ~8 firing timers plus a still-running 1h+
`edge-drain` walk-forward** (the writer set is bigger than the old punch-list's
"5 writers") — `wal_checkpoint(TRUNCATE)` → `VACUUM` (52 s) → `wal_checkpoint
(TRUNCATE)` → restarted everything (broker→HEALTHY→MD→rest→timers). No trading
state, gate, exit, or flag changed — the desk is byte-for-byte what it was.

**Finding (the reason this is worth a note):** the punch-list's "reclaims 0.6–4 G"
was **stale**. The DB is now genuinely ~5.6 GiB of LIVE data (`freelist=0`,
`integrity_check: ok`, page_count 1,473,610 × 4096) — ticks + edge_observations +
the 20 shadow sims have grown to fill it since the 2026-06-13 crypto delete. File
stayed ~5.7 G; only ~1 G disk recovered (74%→72%, fragmentation/WAL). **Re-VACUUM
won't free meaningful space — the lever for disk pressure is now RETENTION, not
VACUUM.** Also corrects the backup-service note: VACUUM did NOT shrink the input,
so the `alphabot-backup` fix is now purely the compressor (`zstd`/`pigz`) or
`TimeoutStartSec` change.

**Verify:** all 7 core services active, no failed units, broker HEALTHY + flat
(0 pos / 0 orders), 17 timers armed, `quick_check: ok`, 4,837 trades intact.

**Ops note:** the user's `Bash(sudo systemctl stop alphabot-broker*)` deny rule
also matches `alphabot-broker-hygiene.timer` — both the broker service and that
timer needed the operator's hand to STOP (restart was auto-allowed for the bring-up).

**Revert:** n/a (maintenance — no config/code change). Docs only: punch-list §1
VACUUM item checked off.

**Commits:** none (docs-only: `FUTURES_DESK_PUNCHLIST.md` + this entry).

---

## 2026-07-11→12 (weekend) — ★ THE GO-LIVE

**Headline:** the desk stopped being a fade book and became a two-sided momentum desk. First time *what the desk trades* changed since the 100%-futures era began.

**What changed (A → B):**
- **Entries:** `vwap_pullback`/`vwap_dip` fade gates → **`thrust_cont`** (two-sided momentum) on all active contracts, `orb_iso` on MNQ.
- **Exit:** the 9-mechanism spine (flat-clock/force-kill/profit-lock/old ratchet) → **1-ATR native stop + tightening ATR chandelier** (`FUT_PURE_ARCHETYPE_EXITS_LIVE=true`).
- **Traded set:** MNQ/MES/MGC still the only live-traded contracts; M2K/MYM/MCL/MBT stay observe-only; **MET/MSL removed** from the universe.
- **Shorts:** unchanged (already armed) but now flow through the momentum gate = genuinely two-sided (no bear-tape constraint).
- **Shadow desk:** 36 → **20 sims** (chopped the whole reversion fade cohort; added `dip_loose_absorption` + `tw_mnq_thrust_loose`).

**Why:** the fade book was structurally −EV (every filtered-reversion variant bled, thesis forward-invalidated); momentum was the proven +EV archetype in shadow (parity-verified 0 drift). Operator flipped it EARLY (Sun ~09:40 UTC) rather than at the 22:00 reopen because he's asleep at midnight Paris — better flat + attended than firing unattended.

**Safety:** native 1-ATR IBKR stop preserved under the flag (verified both states); naked-position auto-flatten backstop armed. Open-monitor cron (`67578a3c`, 22:01–22:51 UTC) + morning-ping (`8503a62c`, 05:37 UTC) watch the unattended first trades.

**Also this weekend:** reversion book chop 36→18 (`1f9a4c78`); `dip_loose_absorption` MNQ 1-ATR/1.25R (`53f1faf6`/`f6893e10`); `tw_mnq_thrust_loose` (`75122ce4`); dashboard rehash + DTT redesign (`5514d1d8`); weekly test-cleanup schema pins (`b5bc129f`, 13 real flags left).

**Revert:** restore the fade tuples + `FUT_ENTRY_GATES=vwap_dip,vwap_pullback` + `FUT_PURE_ARCHETYPE_EXITS_LIVE=false` + restart.

**Commits:** `0a78379a` (go-live), `6af5c4dd` (sideline MET/MSL), `1f9a4c78`, `53f1faf6`, `f6893e10`, `75122ce4`, `5514d1d8`, `b5bc129f`. DECISIONS §342. HANDOVER_82.

---

<!-- FORMAT for future entries (newest at top):

## YYYY-MM-DD — <one-line headline>
**What changed (A → B):** <the before → after, per lever>
**Why:** <the reason / evidence>
**Revert:** <how to undo>
**Commits:** <shas> · DECISIONS §N (if architectural)

-->
