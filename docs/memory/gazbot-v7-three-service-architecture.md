---
name: gazbot-v7-three-service-architecture
description: "GAZBOT V7 architecture + build state — ⚠ SUPERSEDED: gazbot7-tournament replaced core+strategy; those two are INTENTIONALLY inactive, never 'restore' them"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4bb24bdd-baec-4902-a48e-459a8d650566
  modified: 2026-08-04T11:37:52.936Z
---

**★★ READ THIS FIRST — 2026-08-04. THE "THREE SERVICES" BELOW ARE NO LONGER THE DESK.**
The 2026-07-21 cutover replaced `gazbot7-core` + `gazbot7-strategy` with **`gazbot7-tournament`** (the
multi-slot desk: decisions + execution + per-slot safety in one unit). core/strategy are the RETIRED
revert target and are **intentionally `inactive`** — that is the healthy state, not a fault.
`scripts/sweep.py` encodes this correctly (`_DESK_PRIMARY` vs `_DESK_LEGACY`).

⚠ **DO NOT START core/strategy to "fix" them.** Running them alongside the tournament gives you TWO
desks placing orders against one account. On 08-04 this stale memory made me raise a false alarm that
the desk was down when it was healthy — a session that had "fixed" it instead would have doubled the
order path. Live desk = md + tournament + shadow + web + tgbot (+ depth-capture as of 08-04).

2026-07-15 DECISION (operator-approved): GAZBOT V7 (`/home/alphabot/gazbot7`, MNQ-only paper desk) is being rebuilt from a single-process design into a **three-service split**, then the safety spine layered in. V5 (`alphabot2`) is RETIRED (broker+strategy masked). See [[golive-shadow-momentum-to-paper]] for the prior V5→paper history.

**Why the split (the key insight):** collapsing to one process was NEVER what fixes V5's reconciliation nightmare — **venue-truth-first is**. V5's phantom hell came from multiple *sources of truth* (in-memory book + DB + ledger + IBKR), not multiple processes. So separating services is safe IF boundaries pass *messages* (order intents, fill/position events, MD stream), not competing copies of state. The single-process design also gave up fault isolation, independent strategy deploys, and coupled capture to the desk lifecycle (stopping the desk stopped capture — bit us).

**The architecture:**
- **IB Gateway** = IBKR infra (docker, port 4002). Its own unit/lifecycle. Restarted RARELY + deliberately (feed break/wedge only), NEVER auto-chained to a code deploy (avoids re-sticking the reqRealTimeBars 5s farm). Core+MD are clients of it.
- **`gazbot7-core`** = "the broker" lives here (clientId 0 master + `reqAutoOpenOrders`): order engine, fills, position truth (read fresh from IBKR), **trade recording**, native stop + naked-auditor + reconcile + EOD flatten. Recording MUST stay with fills or §274 race returns. A core restart re-connects its client session to the still-running gateway + re-adopts position — does NOT restart the gateway.
- **`gazbot7-md`** = market-data (clientId 2): subscriptions + capture.db (the moat) AND publishes a LIVE STREAM (bars-as-they-close + tape + depth). Sole MD authority.
- **`gazbot7-strategy`** = reads the LIVE MD stream (not DB polling) for decisions + position from core; sends order INTENTS to core. NEVER touches IBKR. Restart freely to deploy. DB only for startup warmup / gap backfill. Staleness guard → stand down on stale stream.
- **Transport:** lightweight local pub/sub, leaning ZeroMQ PUB/SUB (MD stream + intent channel).

**Safety = venue-truth-first + one-choke-point.** Store is an append-only JOURNAL, not a 2nd position authority. Build plan = 10 subsystems (S1 zero-naked / S2 reconcile=boot-adopt+drift / S3 gateway-liveness / S4 EOD-flatten-from-systemd / S5 safe-exit / S6 in-proc pipeline heartbeat / S7 single-source P&L / S8 kill-switches incl max-daily-loss-$ / S9 slice+watchdog+notify / S10 DB hygiene+clientId-master). Deliberately NOT porting: venue_corrections, ledger-authoritative writes, force-resync, con_id de-phantoming, exit-clamps, W/R/J rule sprawl, 8-state FSM, RECONSTRUCTED_BACKFILL (§274 already designed out). Build order: order-choke+tick-rounding → orderStatus/error event wiring → protection mgr → reconcile → rest. All clean-room, tested, flags default dark, `place_live` off until operator go.

**Live state (2026-07-15):** desk DOWN. Naked SHORT 1 MNQ orphan at IBKR (from a crash-loop) still open + unprotected — operator to flatten via `/home/alphabot/gazbot7/flatten_mnq.py` (order-path denied to me). Gap-analysis artifact holds the build plan. Full V5→V7 audit findings (10 parallel audits) are the spec source.

**BUILD COMPLETE (2026-07-15):** the entire 23-gap plan is built + tested on branch `refactor/three-service` (8 commits, full suite 162 pass, main protected, NOT merged). Split (ipc/md/core/strategy + units) + S1 zero-naked (ticks.py rounding + coverage-from-IBKR-truth + naked auditor) + S2 reconcile/boot-adopt (open_position persists entry_atr; reconcile_verdict; venue_audit_loop) + S3 liveness (probe_alive + liveness_loop zombie guard + reconnect re-assert + reqAutoOpenOrders master + trading gate) + S4 session.py (Globex calendar) + eod_flatten timer + no-open/max-hold + S5 safe_flatten_verdict + exit-not-completing watchdog + S6 monitor.py (funnel→signals + core_health.json heartbeat + fills-not-submits) + S7 pnl.py single-source + S8 kill-switches (max_daily_loss/loss_streak) + S9 gazbot7.slice + notify.py (tiers+quiet-hours) + sdnotify watchdog + S10 maint.py (WAL checkpoint + VACUUM-INTO backup). Modules: ipc/md/core/strategy/session/eod_flatten/pnl/notify/sdnotify/maint/ticks + reused store/tracker/safety/engine/deciders/capture/ib_gateway/broker_adapter. Config gates via RunConfig + GAZBOT7_PLACE_LIVE env (systemd default 0). NOT porting confirmed (venue_corrections/ledger-authoritative/force-resync/con_id-dedup/W-R-J sprawl/8-state FSM/RECONSTRUCTED_BACKFILL). **★ LIVE 2026-07-15 ~19:45 UTC.** Units installed to /etc/systemd/system; gazbot7-{md,core,strategy,web} ALL ACTIVE under gazbot7.slice; core `GAZBOT7_PLACE_LIVE=1` (installed unit; repo default stays 0). Timers enabled: monitor(10min), eod-flatten(16:53+16:57 ET), backup(03:30 UTC). DRY-RUN proved plumbing first (bars/ticks/tape flowing, funnel blocked-intents). Then: archived old gazbot7.db (33 crash-loop trades) → backups/archive/*.pre-golive; started clean. Crash-loop orphan SHORT 1 flattened cleanly by core boot-adopt on live start (recorded ADOPT_FLATTEN −$449.81, IBKR net=0). Fixed en route: (1) adopt mis-book — boot-adopt now seeds the tracker (tracker.adopt) so the flatten fill closes cleanly not phantom-opens (acd964c); (2) core writes web-shaped status.json so /v7 feeds (8b748fa); (3) notify subprocess cwd=alphabot2 so TELEGRAM_TOKEN loads → CRITICAL alerts deliver; (4) pnl excludes ADOPT_FLATTEN cleanup from desk P&L (dashboard shows strategy P&L from $0). Desk opens first REAL strategy position on the next thrust — first live run of the order path (place/place_stop/fill routing), the true cutover test. Runs from branch `refactor/three-service` via editable install (NOT merged to main). Deferred: web /v7shadow dashboard; merge-to-main; V5 gazbot7.service monolith neutralized. WATCH: first live trade's order+stop-arm+recording; Telegram now live.
