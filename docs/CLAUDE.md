# CLAUDE.md — HOW I WORK ON THIS DESK (read first, every session)

> **This file is INSTRUCTIONAL. It says how to behave, not what the desk currently is.**
> State lives in `gazbot7/docs/STATE.md` · history in `SESSIONS.md` · the architectural why in
> `DECISIONS.md` · **the operator-model build queue he ticks off in
> `OPERATOR_MODEL_BUILD_QUEUE.md`**. **Rebuilt 2026-08-16** (§361) after it had absorbed desk state for weeks because
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
| `gazbot7-rider-peak-watch.service` | continuous | **THE OPERATOR'S EYES.** 1 Hz open-P&L on the rider off `MD_STREAM` tape. URGENT at **+$200** · a ping per **$50** new high · **give-back** $75 off the peak · **stall** at 3 min with no new high. Every message carries extension in ATR — descriptive, never predictive, and deliberately thresholdless. ⚠ READ-ONLY — no order path, and a test asserts it. The rider's own tick is once a MINUTE, which is why this exists |
| `gazbot7-daily-loss-limit.timer` | `*:0/2:40` | ★**NEW 2026-09-13 — THE $250 DAILY LOSS LIMIT, and it is the first RISK rule this desk has ever run.** Its case needs no edge: the single-lot book's losses are SINGLE-SESSION DOMINATED — worst day −$817 against a median losing day of −$242 (3.4×) and **the five worst days are 52% of all loss** — so a $250 limit takes it from +$35/day to **+$87/day** on 43 sessions. ⚠⚠ **THE LEVEL WAS SELECTED ON THOSE SAME 43 SESSIONS**, tighter looked monotonically better (which usually means "stop trading" is the optimum), so it is PRE-REGISTERED and FROZEN in `data/prereg_daily_loss_limit.json` for 60 sessions. Do not move it; a changed level restarts the count at zero. ★★★ **IT CAN ONLY EVER BENCH**: writes `off`, never `on`, places no order, closes no position, does not touch the rider or the 20:40Z hard exit — asserted against the SOURCE by `tests/test_daily_loss_limit.py`. **SELF-CLEARING** — `gate-reactivate` arms every `off` gate at 22:00Z, so a bench lasts exactly one session and needs no human release, deliberately unlike the cross-desk kill that once disarmed the desk it was protecting for four hours. ★ The session is the **22:00Z reopen**, never the calendar day: a midnight reset would clear the limit mid-session, the one moment it must not, and a test pins that boundary. Fire path verified against a faithful copy of the switch file: all six benched, no `on` written, all 33 comment lines preserved, idempotent on a second call |
| `gazbot7-equity-guard.timer` | `*:0/2:50` | ★**NEW 2026-09-26 — THE ACCOUNT READER, and the FIRST THING ON THIS DESK THAT EVER READ THE MONEY.** The audit found the desk reconciled LOTS every 30s and had **never once reconciled cash**: `ib_gateway.account_summary()` existed and was called by nothing, and a grep for NetLiquidation / ExcessLiquidity / reqPnL / realizedPNL returned that one unused wrapper. So there was no independent check that the dashboard's P&L equalled the money in the account, and **no margin monitoring of any kind** — while 4 MNQ lots is ~$246k of notional against a planned $30k. Reads NLV, excess liquidity, cash, margin and **IB's own realised + unrealised P&L** on a READ-ONLY clientId 11, appends to `data/equity_guard.jsonl`, and records the **IB-vs-our-clean-book divergence** every cycle. ⚠⚠⚠ **ITS LOSS LIMIT IS BUILT AND NOT ARMED.** The breach branch needs **LIVE mode AND** a configured `equity_loss_limit_usd`; on paper it reports *"WOULD HAVE FIRED"* and closes nothing. Operator, 2026-09-26: *"jusy dont switch on any kill seitches while paper trading. i want to be able to trade and learn."* ★ When it does act it writes `day_rider_claim.txt` — the file his own Claim button writes — so it has **no order path at all**, asserted against the source. ★★ Its limit is on **OPEN + REALISED**, which is the gap in the $250 rule: that one sums `trades.pnl_usd` from our own ledger and counts realised only, so an open −$2,000 never trips it. ⚠ **2 MINUTES, NOT ON THE 30s RECONCILER** even though the audit recommended that: the leading wedge hypothesis is IBKR pacing and the desk already opens ~5,000 connections a day — a margin tracker must never be what costs a claim |
| `gazbot7-book-recon.timer` | 21:34 | ★**NEW 2026-09-26 — DOES THE BOOK MATCH THE BROKER, asked daily and it PAGES.** `book_vs_fills` was good and ran **only inside `sweep.py`**, i.e. only as a headless Claude job, **Mon–Fri**, 3-hourly, as a **WARN that paged nobody** — so "is the P&L we reason from real?" depended on an LLM job choosing to mention it, and was never asked on a weekend at all. This is the check that caught 08-13's +$1,551 of profit from orders that sold 8 lots the desk did not own. Reuses sweep's own functions rather than reimplementing a reconciliation, and adds IB's realised P&L vs our clean book from the equity series. ⚠ **READ-ONLY, NO AUTHORITY** — a recording fault is not an order-path fault, so it pages and never benches, halts or flattens; labelling a bad number stays a human decision. ⚠ Runs EVERY day: a weekend is exactly when nobody is watching |
| `gazbot7-deadman.timer` | `*:0/5:25` | ★**NEW 2026-09-26 — THE OFF-BOX DEAD-MAN'S SWITCH, and ⛔ IT IS INERT UNTIL HE PASTES IN A URL.** Every other alarm here is **outbound from the machine being monitored**, so a hang, a full disk, a network drop or broken notify credentials all present identically: **nothing arrives** — and nothing arriving is indistinguishable from a quiet day. That has already cost twelve hours (08-21: `.notify_env` written `600 root:root` while every service runs as `alphabot`; five services mute while the rider crashed mid-flatten and the kill fired, sweep green throughout). It pings a hosted check carrying the desk's own verdict and hits `/fail` when the desk is SICK, so the off-box service escalates on a sick desk as well as a silent one. ⚠ The liveness half never depends on the verdict half — a switch that fails to ping because its own reporting broke would invert its purpose. ⚠ **Set `deadman_url` in `data/live_mode.json`**; until then it exits 0 and says so rather than pretending to protect |
| `gazbot7-tape-reader.timer` | `*:0/2:20` | ★**NEW 2026-09-12 — THE READER, PHASE 1.** The operator asked three times why the desk cannot watch the tape the way he does. It already does — the router, 290 graded calls — but the router is wired to **arm/bench**, the one lever that cannot make money, and is handed a dashboard rather than a day. This gets the WHOLE DAY (open, range and where price sits in it, VWAP stretch in ATR, six hours of 5-min structure, the real `drift.compute()` through its own `_minute_bars` pipeline, the position, every lot's distance to its rung) and judges ONE thing: the position in front of it — HOLD / CLAIM / CUT / ADD with a reason. ⚠⚠⚠ **READ-ONLY. IT WRITES EXACTLY ONE FILE — ITS OWN LOG.** `tests/test_tape_reader.py` asserts against the SOURCE that it names no request file, no switch file and no broker vocabulary. **Phase 2 (one lot, claim/cut ONLY, never add, via the existing file-request path) must be EARNED by the forward grading and is not authorised.** Grade with `scripts/tape_reader_grade.py` — CLAIM is GOOD only when banking beat holding, HOLD only when holding beat banking, so the ladder is the incumbent and must be BEATEN, not matched. ★ It states the SESSION before any price and ages every input: a shut venue and a dead feed produce the same silence, and the router read one as the other this very morning |
| `gazbot7-leg-watch.service` | continuous | ★**NEW 2026-09-15 — THE LEG WATCH, built to EXTEND HIS ATTENTION, not replace his judgement.** A leg opens when 8 min move ≥1×ATR and lives until price gives back **3×ATR** from its extreme — no fixed window, which is why it works where the first attempt failed (a 15-min efficiency window chopped his 2h40m morning leg into six fragments and reported a median leg of 8 minutes; the retrace rule gives 17/session, median **43min / 64pt**). ★★ **THE ESCALATION IS THE THROTTLE:** the first notice is SILENT, 30 and 45 min are quiet log lines, and only **60/90/120/180** page — reached by just 33%/16%/9%/5% of legs, so they fire ~2.7/1.5/0.85 a session. ★★★ **AFTER AN HOUR, OLDER LEGS HAVE LONGER LEFT** — median remaining goes 29→40→58→**98 min** at 60/90/120/180, and the chance of dying within 15 min FALLS from 32% to 13%. That Lindy effect is the whole content of the alert. ⚠ **DESCRIPTIVE, NEVER PREDICTIVE** — all four tape states measure 49-50% forward, and every message says so in its own text; a test asserts the sentence is there. ⚠ **Size gate `LEG_MIN_ATR=6.0`** (operator’s call 2026-09-15, ~4 fires/session, median 36min/41pt left) — without a size gate this fires ~10×/session and becomes wallpaper. `LEG_RETRACE_ATR` **is not a knob to tune**: the frozen `REFCLASS` table IS that parameter, so changing it invalidates every number in the message — re-derive with `scripts/leg_survival.py` first. ★ **IT ALSO OWNS THE TUNNEL BREAK NOW** (`LEG_TUNNEL_MIN=25`): a tunnel is **the absence of a leg**, so the break IS the leg opening — one definition, two states. `gazbot7-tunnel-watch` needs 25 min of **volatility-compressed** tape to arm and so could not fire at all on the noisy-but-directionless morning of 2026-09-15, which is why the operator got nothing when it broke. ⚠ **THE COILED SPRING IS REFUTED and the message says so**: legs after a 0-15min quiet stretch travel a median **70pt**, after 60min+ only **49pt** — a longer wait produces a SMALLER leg, so tunnel length is a RARITY filter (~1.5 breaks/session), never a size forecast. ⚠ READ-ONLY, no order path, `MemoryMax=400M` because tunnel-watch was OOM-killed 4× at 256M while systemd still read `active` |
| ~~`gazbot7-tunnel-watch.service`~~ | **RETIRED 2026-09-24** | ★**DISABLED, not deleted — `systemctl enable --now gazbot7-tunnel-watch` restores it.** It was **37% of his entire Telegram traffic** (3.7/day of ~10) and its own message said why it should go: *"NO EDGE MEASURED — a STATE CHANGE, not a forecast · next 60m runs 1.0× a normal minute · direction 0.46–0.51 vs 0.50 random (n=752)"*. Its founding 1.75× claim was **withdrawn** and re-derived at **1.02×**. It ran on the **VOLATILITY** axis — the axis the operator corrected three times (*a tunnel is not quiet, it is DIRECTIONLESS*) — and `leg_watch`'s `legbreak` already does the same job on **displacement**. ⚠ It was only still running because he once asked to see the transition; he asked for it to go on 2026-09-24. |
| `gazbot7-turn-watch.service` | continuous | ★★★**NEW 2026-09-28 — THE TURN CALL, built because he asked for one thing: "i just want a way to know reasonably that a turn has happened."** After a 23-entry session that lost **$1,882** — where 19 entries WITH the prevailing line made +$1,010 and **4 entries AGAINST it lost −$2,892**, three of them within minutes of a turn. ★★ **THE MEASUREMENT, 100 sessions, of the rule as shipped (it FLIPS direction at each confirmed turn):** a **15×ATR** retrace from the running extreme means the old direction did NOT come back within 2h **77%** of the time, firing **3.6×/session** — the same order as the **3.1 real legs a day** (median leg **298pt over 266min**). The curve: 4×ATR 32.4/day 42% · 7× 13.3 57% · 10× 7.3 66% · 12× 5.3 73% · **15× 3.6 77%** · 20× 2.0 84%. **15 is the knee** — 20× buys 84% but costs 160pt of a 298pt leg. ⚠⚠⚠ **ITS FIRST CUT CLAIMED "7×ATR, 70%, 2.3/day" AND ALL THREE NUMBERS WERE WRONG** — measured on a study that tracked retraces WITHOUT EVER FLIPPING DIRECTION, a rarer event than the detector implements. **The test asserting the CLAIMED RATE against real tape caught it** (23 fires on 09-28 against a claimed 2.3). ⚠ **Do not change `TURN_RETRACE_ATR` without a measured row in `turn_watch.RELIABILITY`** — a test fails if you do, because an alert asserting a number nobody measured at that setting is the tunnel_watch 1.75× failure again. ⚠⚠ **IT IS A DETECTION, NOT A FORECAST:** it says the move that WAS running has probably stopped and nothing about how far the new one goes; 23% of the time the old direction resumes and **every message says so**. ⚠ Leg AGE is reported, not used as a gate — age barely moves this number (67%→71%) but strongly affects pinpointing the top (a 2×ATR pullback is right 5% on a fresh leg, **21% on a four-hour-old one**). ★ **THE HOLD FRAME IS IN EVERY ALERT** because the alert exists to fix over-trading: his own book is **1–4h holds +$86/entry over 30** against **−$27/entry over 67 under 15min**, and his median hold is 21min against a 266min median leg. ⚠ CVD is context only and reads INVERTED — at a turn it is one-sided in the direction that is ENDING (4 of 26 turns had it already flipped), so it corroborates exhaustion, never confirms the new direction; and `aggressor` is in `ticks` (hot tier pruned to 5 days) **AND IN THE LAKE** — `tape_mirror` exports the full table with the column intact, **46 MNQ partitions from 2026-07-24, ~54M ticks**, more on B2. ⚠⚠ The earlier claim that "only ~6 days exist" was WRONG (read the pruner, stopped there); the operator caught it. CVD studies can use ~49 sessions, not 6. ⚠⚠⚠ READ-ONLY — no order path, no switch file, no request file, asserted against the SOURCE |
| `gazbot7-gateway-watch.service` · `gazbot7-breadth-watch.service` | continuous | ★**NEW 2026-09-18.** **GATEWAY WATCH** — IB Gateway leaks sockets in **CLOSE-WAIT** until the 50-slot accept queue fills; **connections already open keep working while every NEW one hangs**, so every health light stays green while the rider, watchdog and reconciler go blind. **25 episodes, 10 of the last 17 days, ~33 hours.** It samples every minute into `data/gateway_watch.jsonl` **with the running job list**, and restarts at **30 of 50 — on the climb, not the wedge**. ⚠⚠⚠ **FLAT ONLY, and an unreadable rider state counts as NOT flat** — not knowing is not the same as flat; it declines LOUDLY. 1h cooldown. ★ **RULED OUT with evidence, do not re-chase:** market-data subscriptions (L2 flowing 13.3M rows/day, zero 354/10089/10090) · a rogue client (97 is our own `depth_capture`, 81 the backfill) · connectivity loss (all 46 Error 1100s are the known 04:40 nightly reset) · a per-connection leak (CLOSE-WAIT is 0 after a restart under normal churn). **REMAINS:** 18 of 25 start 18:00–00:00Z where driftlab/backfill/overnight hammer historical data — **IBKR pacing violations**, supported by a paced 20-request pull leaving CLOSE-WAIT at 0. **STILL A HYPOTHESIS.** ⚠ The 08-21 −$2,149 (4,247 min held) WAS caused by a wedge — the rider could not flatten and 4 naked lots went through the halt into the weekend. · **BREADTH WATCH** — is the run broad? **ONE PERSISTENT connection** (clientId 16), never a poll: the desk already opens ~5,000 short-lived connections a day and adding churn to diagnose churn would be absurd. **US cash hours only**; outside them it reports UNAVAILABLE rather than building a reading from a stale close. ⚠ **A READING — no gate, no switch, no order path.** Pre-registered in `data/prereg_breadth.json`: **120 legs**, verdict on pt/min with non-overlapping day-clustered CIs, bands/names/window FROZEN. In-sample broad **2.05 pt/min [1.77, 2.37]** vs narrow **1.73 [1.50, 1.93]**, confound killed (survives within every duration band and on a size-neutral rate) — ⚠ but **three windows were searched**, so that is an UPPER BOUND on the forward effect |
| `gazbot7-step-away.service` | continuous (2s) | ★**NEW 2026-09-18 — THE STEP-AWAY GUARD.** Operator: *"if im watching it but then i need to go into a meeting. i arm those and then know it will take care of itself."* ★★ **THE MEASURED CASE FOR ARM-WHEN-AWAY, over his last 49 entries (MAE from the 5s tape):** armed ALWAYS = 20 fires, net **+$3,352** · armed while he is **WATCHING** (<90min) = net **+$95** — worthless, *and* it turns his +$819 of 09-16 and +$623 of 09-15 into −$200 apiece · armed while he is **AWAY** (≥90min) = net **+$3,257**. **The value is entirely in trades nobody was watching**, the same finding as the hold-time table (over-8h holds: 0 winners from 4, −$6,612). ★★★ **IT NEVER TOUCHES THE BROKER** — on breach it writes `day_rider_claim.txt`, **the same file his own Claim button writes**, and the rider executes it through its own ownership check via the existing inotify fast path (~0.02s). It therefore cannot open, size, reverse or add. ⚠ **ONE-SHOT**: disarms the instant it fires (a killer left armed fires again against the NEXT position) and at the **22:00Z reopen** (an arming forgotten on Friday must not flatten Monday's trade seconds after it opens — the `CLAIM_MAX_AGE_S` lesson). ⚠ **A STALE PRICE CANNOT TRIGGER IT** (`STALE_PX_S=90`): acting on a dead feed is how a guard becomes the hazard. ⚠ **ARMING NEEDS NO PIN, DISARMING DOES** — the PIN guards what ADDS risk, and friction as he walks into a meeting is friction that costs money. ⚠⚠ **THE $200 IS HIS NUMBER, NOT A FITTED OPTIMUM** — it is not pre-registered and must not be tuned |
| `gazbot7-macro-watch.timer` | `*:52` | ★**NEW 2026-09-18 — THE MACRO TRACKER** (operator: *"oil, dxy, 10 year and vix"*). ONE short-lived **READ-ONLY** IBKR connection (clientId **9**), disconnected in a `finally` — deliberately hourly and not per-minute because on 09-17 the gateway's accept queue filled and every NEW connection hung for 5.5h while the rider held 4 lots blind; **a context tracker must never be what costs a claim.** Fails quietly, pages only at a 6h/24h streak, `critical=False`. ★★ **WHAT EACH SERIES IS, because getting this wrong is the cost-constant class of error:** `OIL` = **front WTI FUTURE** (CLX6), *not* spot — FRED spot read 107.02 on 15-Sep while the front future read 95.24 on the 18th · `DXY` = the dollar index **FUTURE** (DXZ6); `Index("DXY")` has no security definition on this account · `TEN` = the **ZN NOTE FUTURE — A PRICE, INVERSE TO YIELD** · `VIX` = **DELAYED ~15 min**, needs `reqMarketDataType(3)`, and every record carries a `delayed` flag. ★★★ **MEASURED 2026-09-18 vs daily returns (MNQ n=406, MGC n=544, FRED history, zero-volume bars filtered): ALL FOUR CO-MOVE, NONE PREDICTS THE NEXT DAY.** VIX↔MNQ same-day **r=−0.669** · DXY↔MGC **r=−0.408** · 10y↔MGC −0.116 · **OIL is unrelated to both (−0.05 / −0.01) and has no next-day signal anywhere.** Next-day r spans −0.079…+0.077 against a 2σ threshold of ~0.09. **So these EXPLAIN the session, they do not forecast it** — the tracker is context for the Friday backdrop and must never be read as a signal |
| `gazbot7-event-calendar.timer` · `gazbot7-event-alert.timer` | 21:25 · `*:0/5:30` | ★**NEW 2026-09-18 — THE EVENT CALENDAR AND THE PRE-EVENT ALERT.** Built after 2026-09-16: he held LONG 4 through the FOMC decision, bought AGAIN at **T+52** while the slide still had until T+85 to run, and lost **$1,272 on one trade** — more than the day's −$833. ★★ **MEASURED ON OUR OWN 5s TAPE, 30-min release window:** MNQ FOMC **171pt/132pt (100th & 98th pct, 3.5× and 2.7× the median)**, CPI 205/272pt, NFP 218/220pt, against an ordinary median of 49–69pt; MGC's FOMC window was **6.6× its median and 2.8× its previous MAXIMUM** over 32 sessions. **6 windows tested, 6 in the top 5%** — and a day I MISLABELLED as an event (07-16; June CPI actually landed on the 14th) came back at the exact ordinary median, which is the accidental control. ⚠⚠ **IT SAYS WHEN, NEVER WHICH WAY** — his loss was a DIRECTION error and every direction study here is a coin; a test forbids the message carrying a side. ⚠⚠⚠ **AND IT IS NOT A SWITCH:** his event-day record is −$1,518 over 12 entries vs +$1,076 over 67 ordinary, but that is **5 days and the split was chosen after seeing it** — the page says so in its own text. ★ **Times are stored in EASTERN and converted at read time**; storing UTC bakes in a DST offset that is wrong half the year (US clocks change 1 Nov). ★★ **SOURCES, measured from this box:** federalreserve.gov 200 (scraped, with a hard **8-meetings-a-year invariant** that DISCARDS a bad parse) · api.nasdaq.com 200 (earnings, as they are published) · **bls.gov 403 under ANY User-Agent**, so CPI/NFP are **SEEDED, cannot self-renew, and `--check` pages BEFORE they run dry** — a calendar that quietly empties is this desk's signature failure. ⚠ The first parser shipped two bugs caught before it ever paged: it read "(Minutes: February 18)" as a MEETING, and a fixed 4,000-char slice cut 2026 off after April, **missing 28 Oct and 9 Dec — the next two meetings and the whole point of the file** |
| `gazbot7-capture-read-buy.path` · `-claim.path` | on write | ★**NEW 2026-09-14 — CAPTURE THE OPERATOR'S READ.** Fires on the same inotify event as the rider's own fast path and snapshots the WHOLE DAY's tape state at the instant he presses, into `data/operator_reads.jsonl`. ★★ **WHY THIS OUTRANKS ANOTHER GATE:** measured on the live record at SINGLE LOT, his manual entries are **+$78.27/trade over 28 trades at an 82% win rate** — level with the rider's automatic entries and **37× the automated gates' +$2.10**. Eleven months of studies and **119 calibrations** failed to reproduce his judgement because every one tried to reverse-engineer it from the OUTCOME; nobody ever recorded the INPUT. ⚠⚠ **IT MUST NEVER CONSUME THE REQUEST** — `day_rider` reads and clears `day_rider_buy/claim.txt`, and a second reader that disposed of one would silently EAT HIS PRESS. Read-only, writes only its own log, asserted against the SOURCE by `tests/test_capture_operator_read.py`. ★ **The label is grabbed in `ExecStartPre`, before the interpreter exists** — measured: the rider consumes the request in ~1.35s and Python takes ~1.7s to reach its first read, so the first live test captured `request: {}` and would have built a dataset of presses with no record of what was pressed. ⚠ `PathModified`, never `PathExists`. ★ **COLLECT FIRST, MODEL LATER: no fitting below 30 labelled presses** (`scripts/operator_reads_join.py` enforces the count and says so) — at n<30 any answer is a story about noise and would be the 120th calibration |
| `gazbot7-request-watch.timer` | `*:*:45` | ★**NEW 2026-09-17 — THE UNREAD-REQUEST ALARM. It watches THE PRESS, not the service.** On 2026-09-17 the gateway's accept queue filled at 00:40Z (`LISTEN 51/50`, sockets stuck in CLOSE-WAIT): **already-open connections kept working and every NEW one hung**, so the rider timed out **244 consecutive times, exited 0 every time, and wrote a FRESH HEARTBEAT every minute**. systemd green, sweep green, dashboard green — and the operator's Claim, pressed on a **+$262** position, sat unread for 27 min, **EXPIRED at `CLAIM_MAX_AGE_S`**, and he found it himself at **−$316**. Every instrument was asking *"is the rider alive?"* and getting a truthful yes; **nobody asked whether the BUTTON LANDED.** The rider DELETES a request when it consumes it, so **`exists and old` IS unread** — no heartbeat, no liveness proxy, nothing that can go stale in the wrong direction. Pages at **120s**, says whether the press can still be honoured or has already expired, and names the likely cause from `day_rider_state.json`. ⚠⚠ It also makes the **known-open BUY-while-holding bug** audible (`owns_position` :978 precedes `buy_requested()` :1017, so that press is never read). ⚠⚠⚠ **READ-ONLY — it never consumes, clears or rewrites a request**; a second reader that disposed of one would silently EAT THE PRESS. `tests/test_request_watch.py` asserts that against the SOURCE |
| `gazbot7-day-rider-claim.path` | on write | **CLAIM FAST PATH.** inotify on `day_rider_claim.txt` → runs the rider NOW (**0.02s**) instead of waiting up to **60s** for the `*:*:05` tick. ⚠ `PathModified` **not** `PathExists` — an orphaned flag lives 15 min and would loop the rider. The 60s tick is still the floor |
| `gazbot7-day-rider-buy.path` | on write | **ENTRY FAST PATH (2026-09-03).** The twin of the claim path, for the BUY/SELL button — it was left on the 60s tick when the exit was cut to 0.02s. inotify on `day_rider_buy.txt` → **measured 1.35s to a COMPLETED tick** (twice, written off the `:05` boundary so no timer tick could be mistaken for it). ⚠ `PathModified` **not** `PathExists` — `BUY_MAX_AGE_S` is 5 min and an unread request DOES sit that long. ⚠ **A BUY PRESSED WHILE THE RIDER HOLDS IS NEVER READ** — `owns_position` (:978) takes the branch before `buy_requested()` (:1017), so the request ages out in silence while the dashboard said "requested". Known-open, not fixed: the fix touches the rider's live path and was deferred out of a naked position |
| `gazbot7-tournament` · `gazbot7-md` · `gazbot7-shadow` · `gazbot7-shadow-mgc` · `gazbot7-web` · `gazbot7-tgbot` · `gazbot7-depth-capture` | continuous | the desks, the feed, the books, the page, phone control, L2 |

### Trading-day jobs
| unit | schedule | purpose |
|---|---|---|
| `gazbot7-day-rider.timer` | `*:*:05` | the SECOND desk — oneshot, picks up code each tick. ★**2026-09-17 IT NOW PAGES WHEN IT IS BLIND AND HOLDING, AT ANY HOUR.** It already alarmed on an unreachable venue but **only inside the flatten window** (`mod >= FLAT_UTC_MIN`) because its founding case was an overnight carry — so a 00:40–06:09Z outage holding 4 lots paged NOTHING while writing `venue_ok: false` + `ERROR (no action): TimeoutError` 244 times. **A position the rider cannot see is unmanaged at 01:00 exactly as much as at 20:50.** Streak-gated at **3/10/30/120 ticks** (~3 min / 10 / 30 / 2 h) so the first page lands while a claim is still LIVE, and the streak is **DURABLE** (`data/day_rider_blind.json`) because the rider is oneshot and an in-memory counter would never reach 2. ⚠ The reset sits on the line that **proves** the broker was reached (`out["venue_ok"] = True`), NOT beside a `save_state()` — step() has **twelve** of those and the ordinary riding branches return before the last one, so the first version of the reset was unreachable on every healthy tick |
| `gazbot7-day-rider-watchdog.timer` | `*:0/2:35` | rider liveness |
| `gazbot7-eod-flatten.timer` | Mon–Fri 16:53 + 16:57 **America/New_York** | ⚠ cancel from the OWNING clientId — `Error 10147` means *"not yours"*, **not** *"it is gone"* |
| `gazbot7-gate-reactivate.timer` | 00:00 **Europe/Paris** | **⚠ ARMS EVERY `=off` GATE.** A bench therefore lasts only until 22:00Z. `HOLD` is **EMPTY by operator policy** (08-01: *"every gate should re-enable for the midnight open. then the router manages"*) — so this is what re-arms a gate the router benched. Working as instructed |
| `gazbot7-open-hour-watch.timer` | Mon–Fri, every min 07–13 & 14–19 | open watch ⚠ ~700 fires/day — verify that is intended |
| `gazbot7-nightly-audit.timer` | 21:30 | `claim_audit.py` + `nipc_replay.py` ⚠ the nipc half is vestigial (gate deleted) |
| `gazbot7-nightly-supervisor.timer` | 21:40 | verify-and-repair: did timers actually FIRE, is the router deciding, is the mirror/prune interlock intact. Restarts only a unit that is enabled, down, **and while flat** — and it now reads `core_health.desk_flat` (tournament AND rider), never the tournament-scoped `flat` that called a live 4-lot position flat for 811 of 817 ticks. Deliberately not a reboot, and not at 22:00 (that is the reopen). ★2026-09-26 it also watches **every safety guard** (gateway-watch, step-away, web = his buttons, tgbot, the eyes) and the four safety TIMERS, and checks that **append-only files are writable by the service that appends** — a root-owned `equity_guard.jsonl` made the new account reader log PermissionError every 2 min while exiting 0, the third instance of the 08-21 `.notify_env` shape. ⚠⚠ **FAULTS page from here in real time; the CLEAN-night line does NOT** — it fires inside quiet hours and was suppressed every night. `gazbot7-overnight-allclear` below is what reports a clean night, and what notices this job's own death |
| `gazbot7-overnight-allclear.timer` | **06:05 Europe/Paris** | ★★★**NEW 2026-09-26 — "DID THE SUPERVISOR ACTUALLY RUN?", ASKED BY A DIFFERENT PROCESS.** The audit found `nightly-supervisor` spoke only on faults, so a clean night and a **DEAD** supervisor were identical silence — and nothing else on the box checks the thing that checks everything else. ⚠⚠ **THE OBVIOUS FIX WAS TRIED AND DID NOT WORK:** making it send unconditionally achieved nothing, because it fires 21:40 UTC = **23:40 Paris** (22:40 CET) and quiet hours are 22:00–06:00 Paris, so a correctly non-critical heartbeat was suppressed **every night of the year**. ★★★ **THE DESIGN ERROR WAS DEEPER THAN THE HOUR — A PROCESS CANNOT REPORT ITS OWN ABSENCE.** So this is a separate job on a separate timer at an hour OUTSIDE quiet hours: it reads `data/nightly_supervisor.json` and **pages CRITICAL if that verdict is missing or stale**, repeats faults, and otherwise sends ONE boring line. **Expect `✅ Last night verified clean …` each morning; a missing morning line is the signal.** ⚠ The rejected alternative was a quiet-hours exemption for heartbeats — it would have re-coupled the `critical`/`mark` flags the 09-24 split separated and bought a 23:40 buzz every night. **Scheduling beat a new exemption.** ⚠ Scheduled in **Europe/Paris, NOT UTC**: a UTC time drifts an hour at each DST change and falls back inside quiet hours for half the year — the same rule as the event calendar. ⚠ `Persistent=true`, because if the box was down at 06:05 the question "did last night run?" is MORE interesting, not less. ⚠ READ-ONLY: it opens one file for reading and sends one message — a test asserts via AST that it imports no `subprocess` and writes nothing |

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
| `gazbot7-capture-prune.timer` | 21:15 | prunes `capture.db` **PER TABLE, not to one number** — `book`/`quotes`/`ticks` 5 trading days, **`bars` 60** (`prune_capture.RETAIN`). ⚠ "capture keeps 5 days" is true of TICKS and false of BARS: measured 2026-09-02 bars run 07-15→today, 929,817 rows |
| `gazbot7-backup.timer` 03:30 · `gazbot7-cloud-backup-state.timer` `*:07` · `gazbot7-cloud-backup-tape.timer` 21:20 | | |
| `gazbot7-cl-worker.timer` `*:0/2` · `gazbot7-clip-revert.timer` 21:15 | | |

### TEMPORARY research jobs — delete the unit and this row when done
| unit | schedule | purpose |
|---|---|---|
| `gazbot7-overnight.timer` | 23:20 (blocks on the backfill) | **⏳ TEMPORARY (added 2026-08-18).** The research chain: **full-history census** (both contracts, at two run thresholds), **walk-forward across four periods**, then greenfield. ★ Every census passes **`--lake`** — `run_census.py` defaults to `capture.db`, which is PRUNED, so `--days 400` against it silently censuses only the hot tier — **60 trading days of bars, measured 49 on disk 2026-09-02** — and reports as though it covered 400. ★ Waits for the backfill because that is its INPUT. ★ Artifact-on-disk checkpointing; **judged on the artifact, never the exit code**. Output in `reports/overnight/`. **DELETE when the research is banked.** |
| `gazbot7-backfill-health.timer` | `*:12,42` (every 30 min) | **⏳ TEMPORARY (added 2026-08-18).** Watchdog for the backfill. ★ It checks **PRODUCTION, not liveness** — parquet count and log growth — because a process that is running and writing nothing is this desk's signature failure. Distinguishes a legitimate yield (a desk holds a position) from a STALL, restarts at most **twice**, then pages and stops rather than looping. Verdicts: WORKING / IDLE-OK / STALLED / DEAD / BLOCKED. **DELETE with the backfill job.** |
| `gazbot7-backfill.timer` | 22:05 (just after the reopen) | **⏳ TEMPORARY (added 2026-08-18).** Pulls every historical bar IBKR will serve for **MNQ + MGC** — CONTFUT long series plus every listed expiry, `includeExpired=True` — into `data/backfill/` as verified Parquet. **RESUMABLE** (an existing file is skipped) and it **YIELDS while any desk holds a position**, resuming when flat, so it never competes with trading for the shared gateway. 8h budget spanning the 00:00–07:00 Asia block, where the desk is already entry-blocked. ⚠ MEASURED CEILING: asking 15Y and 5Y return the SAME 482 daily bars — the limit is ENTITLEMENT, not runtime, so more hours buys nothing. **DELETE once `data/backfill/` stops growing between runs.** |
| `gazbot7-gap-log.timer` | `*:*:37` | **⏳ TEMPORARY (added 2026-09-24).** Logs every **PX/CVD GAP episode** into `data/gap_log.jsonl`. ★★★ **THE OPERATOR FOUND THE HOLE BY ASKING FOR EXAMPLES:** given the PX·CVD pair he produced **`65·10`** — a 55-point disagreement the **shipped rule ignores**, because bearish needs px≥85 and bullish needs px≤15, so the widest divergence of the four he named gets no colour at all. No test had caught it. ⚠ Pre-registered in `data/prereg_gap.json`: **300 episodes / 40 sessions**, verdict on **day-clustered** CIs, and it must beat **BOTH** the control **AND the incumbent** — matching the live rule is REFUTED, because replacing a shipped rule with an indistinguishable one is churn. ★ **THE THRESHOLD 35 IS INHERITED, NOT FITTED** — it is the minimum gap the incumbent already implies (85/50 and 15/50 are both 35), so no number was chosen by looking at data. **DO NOT TUNE IT**; a change restarts the count at zero. ⚠⚠ The unit is an **EPISODE, never a minute** — a gap persists for many minutes and counting them would score one divergence forty times. ⚠ **Warm-up 60min / 20pt range**, amended *before any outcome was examined* (the mechanism check deliberately printed no forward numbers): a "position in the range" is undefined while the range is near zero, and the first run produced `100·65` and `0·100` on a three-minute-old session. ~24 episodes/session. ⚠⚠⚠ READ-ONLY, writes two files, both its own. **DELETE at 300 episodes or 2026-12-31.** |
| `gazbot7-surge-log.timer` | Mon–Fri `*:*:17` | **⏳ TEMPORARY (added 2026-09-24).** Logs every surge (|1-min move| ≥ **12.5pt**) with its **PULSE** and **FLOW** into `data/surge_log.jsonl`. ⚠⚠⚠ **ITS FOUNDING JUSTIFICATION WAS WRONG (corrected 2026-09-30).** It shipped saying *"the question cannot be answered backwards — `aggressor` lives only in `capture.db.ticks`, kept 5 DAYS, there is no history and there never will be."* **FALSE.** `prune_capture` trims the HOT tier; `tape_mirror` has been exporting the full `ticks` table to the lake with `aggressor` intact the whole time — **46 MNQ partitions from 2026-07-24, ~54M ticks**, more on B2. The operator caught it: *"why are we pruning aggressor at 5 says? we have an endless data lake"*. I had read the pruner and stopped there. **So the surge question IS answerable backwards on ~49 sessions**, and the 40-session forward wait is no longer the only route — but the forward run is still the CLEAN test (the lake is where the idea was found), so it keeps running and its frozen parameters are untouched. A backward run on the lake is a SEPARATE, in-sample estimate and must be labelled as one. ⚠ Pre-registered in `data/prereg_surge.json`: **400 surges / 40 sessions**, verdict on median continuation with **day-clustered** CIs (minutes inside a session are not independent draws and a per-observation interval here is inflated ~10×). **DO NOT TUNE** the 12.5pt / 1.5× / 0.15 — a change restarts the count at zero. ⚠ The 2026-09-18→24 window is where the idea was FOUND (n=170: backed +5.25pt vs unbacked +0.50pt median over 5 min) and **its numbers are NOT a result**; first eligible session **2026-09-25**. ⚠⚠ The METERS ship regardless and are **DESCRIPTIVE** — this only tests the separate, stronger claim that "backed" also predicts continuation. READ-ONLY, writes one file. **DELETE at 400 surges or 2026-12-31.** |
| `gazbot7-prereg-thinning.timer` | Mon–Fri 21:10 | **⏳ TEMPORARY (added 2026-09-11).** Records ONE session into `data/prereg_book_thinning.json` — the PRE-REGISTERED test of whether ORDER-BOOK THINNING adds anything to `drift`. ★ Three arms every session: **A** drift alone (the control/incumbent), **B** thinning alone, **C** both. The hypothesis is C, and the verdict is **C must beat A** — if they are indistinguishable the thinning trigger is decoration and the answer is REFUTED even if both make money. ⚠ **DO NOT TUNE the 0.75 depth-ratio threshold, do not add a third feature, and do not read the interim** — n<60 sessions is not evidence by construction. ⚠ The 2026-08-14→09-11 window is where the effect was FOUND and its P&L is **not a result**; first eligible session is **2026-09-12**. Read-only, places no orders. **DELETE at 60 sessions or 2026-12-31, whichever first.** |
| `gazbot7-driftlab.timer` | 21:02 (inside the halt) | **⏳ TEMPORARY (added 2026-08-18).** 10y NQ+MNQ 1-min pull from IBKR → replays `drift.compute()` causally to answer "once the rider CONFIRMS, how often does the day stay that way?". **RESUMABLE** — one parquet per contract-month IS the checkpoint, so it stops at its 50-min deadline and continues the next night. Refuses to run unless the desk is FLAT and the venue HALTED (it shares the live gateway), and a refusal exits 0, not red. `MemoryMax=1G` — the desk wins any contention. **DELETE once `data/driftlab/_REPORT.txt` covers the full span.** |

**To add a job:** write the unit in `ops/systemd/`, the prompt in `ops/job_prompts/`, enable it, and
**add a row here**. A job nobody has listed is a job nobody checks.

### ★★★ PRESENCE — "was he even looking?" (`scripts/presence.py`, no timer, read on demand)
Operator, **2026-09-18**: *"im looking at it periodically during the work day when i have time. not
all day and reading every telegram."* **A telegram delivered is not a telegram read**, so an alert
he never saw is NOT a rejection — and that distinction decides whether the desk has negative
examples at all.
- **nginx already had this. No code change was needed** — it is the front door (443 → `:8087`) and
  logs every request, including the static reports and the phone. The build queue's plan to patch
  `web.py`'s no-op `log_message` would have recorded LESS and needed a restart that drops his tab.
- ⚠⚠⚠ **THE DEVICES ARE NOT INTERCHANGEABLE AND MUST NEVER BE MERGED BEFORE SESSIONISING.** Measured
  2026-09-18: **desktop 14,571 requests in 109 min = 134/MINUTE**, zero gaps over 30 min, ONE
  session — *that page polls, so a tab left open manufactures presence indefinitely*. **Phone: 3,550
  requests, TEN distinct sessions** across 02:25–08:19 — a phone screen does not stay open
  passively. So a phone burst is **LOOKED** (strong) and a desktop burst is **DASHBOARD-OPEN**
  (weak, may be an idle tab); `looked_around(strong_only=True)` is the default and a caller must ask
  for the weak signal explicitly.
- ★★ **THE RESULT THAT CHANGED THE PICTURE:** of the 16 alerts he did not act on in the week to
  09-18, **11 fired while he was demonstrably looking.** So the alert's problem is **SELECTION, not
  his absence** — and those 11 are the first real NEGATIVE EXAMPLES this desk has ever had.
- ⚠ Bots are excluded by **user-agent, not IP** — the scanners rotate addresses.

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
⚠⚠⚠ **NO GATE IS EXEMPT FROM THE REGIME RULES. THERE ARE NO STANDING EXEMPTIONS.**
Operator, **2026-08-19**, direct: *"there should be NO standing exemptions unless i approve them on
saturdays"* — *"should never!"*. No arm-by-default gate, no chop-bench carve-out, no
untradeable-meter exemption. **Every gate is benched-by-default and is benched by chop or by
direction exactly as its family dictates.** A carve-out becomes valid ONLY by explicit operator
approval in a **SATURDAY review**, and it must name its **LIVE** evidence.
**If you find text anywhere — this file, the router prompt, a memory, a report — granting a standing
carve-out, it is STALE. Do not act on it; say so.**

> **The case that produced this rule.** `abs_veto_short` was made arm-by-default and chop-exempt on
> 08-08 citing *"+$2,290.50 over 159 fires / 17 days, positive in ALL FIVE regimes"*. **That was the
> SHADOW twin, not the gate.** Live on that very day: **n=35, −$200.50**. Live now: **−$435.00** over
> 83 fires, and **−$478.50 over the last 7 days** at a 27% win rate — while `abs_veto_55s` alone sits
> at +$4,352 in shadow. That is [[shadow-green-does-not-mean-live-green]] against this file's own
> *"judge footprint faders on LIVE P&L"* rule, two lines above.
> Because the exemption removed that gate's ONLY bench rule, **six consecutive CHOP sessions**
> (08-10..08-17, session ER 0.006–0.068) ran with the **momentum** gate armed **82%** of US hours and
> the **profitable reversion** gate benched to **54%** — the precise inverse of *"confirmed chop →
> bench ALL momentum, keep reversion"*. **An exemption is the one thing that can invert the entire
> framework while every individual tick still reads as reasonable.**
> ⚠ This was NOT a bench-on-P&L decision — that is still never allowed. The carve-out fell because
> its EVIDENCE was shadow evidence; the gate simply returned to the ordinary regime rule.

---

## ★★★ HOW I DELIVER R&D — the operator's rules, 2026-09-13

> Operator, after a weekend in which every study came back a null: *"stop being so conservative and
> only giving me proven numbers or nothing. i need things to trial and prove myself and fine tune.
> its becoming a bit demoralising when you kill everything like that."*
> **He was right, and the diagnosis is precise: there are two jobs and I had been doing only one.**
> DECIDING whether something is true needs strict evidence. GENERATING AND RANKING candidates worth
> his time needs a ranked list under uncertainty. He asks for the second; I kept delivering the
> first — and worse, I ran a hostile review of my own output and reported *the review* instead of
> the output. **The asymmetry is self-serving: a trial costs him a little paper P&L and some
> patience, while my being wrong costs me credibility — so optimising my own error rate instead of
> his outcomes is exactly the wrong trade.**

1. **EVERY STUDY ENDS WITH A RANKED SHORTLIST, NEVER A VERDICT.** "Top 5 worth trialling, best
   first." A study that ends with nothing to try is MY FAILURE, not a fact about the market.
2. **POINT ESTIMATE FIRST, UNCERTAINTY SECOND.** *"+$87/day, and here is how confident"* — never
   *"spans zero, therefore nothing"*. The interval is a qualifier, not the headline.
3. **THREE OUTCOMES, NOT TWO.** **REFUTED** (measured negative, or its control beat it, or its
   mechanism is broken) · **PROMISING** (positive, unproven — *trial it*) · **PROVEN** (rare).
   Most honest results belong in the middle, and that is a useful place to be, not a failure.
4. **ONLY KILL ON EVIDENCE OF ABSENCE, NEVER ON ABSENCE OF EVIDENCE.** "Not proven" is a **PARK**,
   and parked things go to shadow, where they cost nothing but time.
5. **THE BAR SCALES WITH WHAT IS AT RISK.** Shadow: a mechanism and a non-negative signal. Paper:
   beats its own control. **Only real money gets the strict bar.** ⚠ The recurring failure is
   applying the top rung to every decision, which makes the desk trade nothing.
6. **HIS UNITS: $/day at a stated lot size.** Not points, not R², not Sharpe, not t-stats.
7. **NEVER RE-LITIGATE A TARGET OR CONSTRAINT HE DID NOT SET.** A number he quoted from a forum is
   not a yardstick, and turning it into one and then measuring against it repeatedly is corrosive.
8. **IF NOTHING PASSES MY BAR FOR A WEEK, THE BAR IS WRONG** — say so, and change it, rather than
   filing another null.

⚠ **NONE OF THIS WEAKENS THE METHOD TRAPS BELOW.** They protect against fooling ourselves and they
stay exactly as strict. The difference is WHAT HAPPENS TO A SURVIVOR: a result that fails the strict
bar is a SHADOW CANDIDATE, not a corpse. Rigour decides how much to risk; it does not decide whether
to look.

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
13. **A FILL PRICE THAT NEVER PRINTED IS NOT A MEASUREMENT.** The IBKR PAPER engine fills every lot
    beyond the first at **exactly 0.1% of price**, adverse, rounded to the tick — 21/21 multi-lot
    rider orders at 0.09897-0.09998%, invariant across sessions, sides and vol regimes. **Real
    slippage varies with liquidity; a constant does not.** $2,916.50 over 32 orders / 101 lots,
    which is MORE than the desk's entire booked loss, so **any P&L ranking that includes a multi-lot
    order is contaminated** — single-lot fills are clean. Rider ENTRIES are now marketable limits;
    ★★2026-09-15 **EXITS NO LONGER TAKE IT EITHER** — operator-authorised after a 4-lot claim he
    pressed at **−$115** booked **−$304.50**: 1 lot @ 29291.25 (real) + **3 @ 29262.00**, 29.25pt =
    0.0999%, against a six-minute low of 29274.75. **$175.50 of that loss is a price that never
    printed**, and `sweep.py`'s `fill_vs_book` caught it unprompted. The three MULTI-LOT closes
    (OPERATOR_SELL / MANUAL_CLAIM / TRAIL) go through **`place_exit()`** — a marketable limit that
    **ESCALATES TO MARKET** for whatever it has not filled in `RIDER_EXIT_LIMIT_WAIT_S`. ⚠ The
    escalation is the whole design: *"an exit that does not fill is unbounded risk"* was always the
    right objection, so the premise is removed rather than the rule. ⚠⚠ **THE 20:40Z HARD FLAT IS
    NOT ROUTED THROUGH IT** and must never be — an unconditional flatten may not acquire a fill
    condition, and `tests/test_day_rider_entry_limit.py` asserts that against the SOURCE.
    ⚠ **Single-lot exits are deliberately unchanged**: the fabrication only hits lots beyond the
    first. Before trusting a per-trade number, check whether its order filled in pieces. ⚠ It does NOT follow that the desk is profitable, and it is UNKNOWN whether a
    live account does this. STATE §1d, DECISIONS §365.
14. **A SIM NUMBER IS A REGISTRY ID, NEVER A POSITION.** When he says *"sim 55"* he is reading the
    **shadow dashboard**, which renders `sim_id` from `data/sim_registry.json`. Resolve it with
    `PYTHONPATH=src .venv/bin/python scripts/sim_registry.py --id 55` (`--match <fragment>` by name).
    **NEVER enumerate `default_slate()` and count** — the slate is 35 arms, the registry is 86, and
    counting positionally on 08-19 resolved "55" to `abs_veto_55s` (whose name merely *contains* 55)
    instead of `odr_c10_s30`, and produced a full analysis of the wrong arm. `web.sim_ids()` warns
    of exactly this: *"a positional fallback would silently invent a WRONG number."*
    IDs are permanent and never reissued; a retired sim keeps its number.

---

## OPERATOR RULES — standing, not negotiable

- **"IBKR IS THE TRUTH. NEVER RELY ON OUR BOOKS. EVER."** `entered`/`closed` describe INTENT.
  On a netted shared account **nobody may act unless `venue == the sum of EVERY desk's claim`**.
  **Two books vouching for each other is not reconciliation.**
- **"NEVER HOLD OVERNIGHT. EVER."** Rider flat at **20:40 UTC, never 21:00** — 21:00 *is* the CME
  halt, so a flatten fired then has no market and no retry.
- ⚠⚠⚠ **NEVER EXERCISE AN ORDER-PATH ENDPOINT AGAINST THE LIVE ACCOUNT.** On **2026-09-24** a test
  of the no-PIN flatten POSTed to `/api/control/dayrider-claim` and the rider flattened his live
  **SHORT 4 three seconds later** — trade 1019, **−$842.50**. It was the **third** time in one
  session a test touched a live position, and twice before it had been promised it would not happen
  again. **A promise is not a control**, so there is now a control: `web.py`'s `ORDER_PATHS` gate
  refuses `/api/control/claim`, `dayrider-buy` and `dayrider-claim` unless the request carries a
  same-origin dashboard `Referer` — which a browser always sends and a bare curl never does.
  ⚠ It is NOT security (a Referer is trivially forged); it makes the ACCIDENT impossible, which is
  the failure that actually happened. Anything legitimately acting without a browser writes the
  request FILE directly, as `step_away.py` does. **Test refusal paths only; to test a fill, use a
  sandboxed copy.**
- **Do not book a loss caused by a system bug** — *"i will keep the green book thanks"*.
  **LABEL, never adjust.** ★ Two prefixes, and they are not interchangeable: **`EXCLUDE:`** = GONE
  from every view · **`BADFILL:`** = SHOW IT, DO NOT COUNT IT (real trade, broken price — reaches
  the blotter, never a P&L, curve or gate ranking). On 08-21 a genuine round trip was marked
  `EXCLUDE:` and vanished, and the operator watched a trade happen and then could not find it.
  ⚠ The flag takes the WHOLE ROW, so flagging a partly-fabricated trade also removes the genuine
  part — say so rather than implying the flagged number was all fiction.
- **FINAL DELIVERABLES ONLY** — no progress pings; one message when done.
- ★★ **EVERY `critical=True` ALERT IS PREFIXED `🔴` BY `notify()` ITSELF** (2026-09-24). He gets
  ~10 Telegrams a day and 85% are informational; the four that can cost money total under one a
  day and were buried. ⚠ **Applied in ONE place, never at a call site** — a per-caller marker
  drifts the moment someone adds the 47th, and then the ABSENCE of a mark means nothing. ⚠ **Do
  not mark routine alerts:** if everything is marked, nothing is.
- ★★★ **THE PAPER/REAL BOUNDARY IS NOW IN THE CODE, AND THE KILL SWITCHES ARE OFF ON PURPOSE**
  (2026-09-26). `src/gazbot7/livemode.py` decides PAPER vs LIVE from the **ACCOUNT ID**, never a
  flag; `DUQ191770` is a hard-coded allowlist FLOOR so a missing config cannot take the paper desk
  down, and `live_accounts` is EMPTY so LIVE is unreachable until he adds one. Three things are
  **built and deliberately NOT armed** — the 600pt broker-side stop (`PLACE_VENUE_STOP`), the
  equity loss limit that can flatten, and the order-path account guard. His instruction:
  *"jusy dont switch on any kill seitches while paper trading. i want to be able to trade and
  learn."* ⚠⚠ **DO NOT ARM ANY OF THEM WITHOUT HIM SAYING SO**, and note `live_preflight()` refuses
  a live account until all five January requirements are configured — that refusal is a feature.
  ⚠ `data/live_mode.json` is gitignored; the tracked restore path is `ops/live_mode.example.json`.
- **Tournament changes are SATURDAYS ONLY.**
- **Warn before restarting `alphabot-dashboard`/web** — it drops the operator's tab.
- **Credential expiry is the #1 fragility** and he has declined a long-lived key (*"ill just relogin
  every now and then"*), so the alarm IS the mitigation. If it pages: run `claude`, `/login`.
- **NEVER KILL A LEAD THAT HAS A GLIMMER** — every lead ends LIVE / SHADOW / PARKED / REFUTED.

---

## ★★★ THE FRIDAY REPORT — Fri 22:07Z → Sat 05:15Z (= 07:15 Paris; he needs it by 08:00)

> ★★★ **REFOCUSED 2026-09-18 — IT HAS ONE SUBJECT NOW.** Operator: *"the friday report is now
> vastly different. it doesnt need everything it had. all it needs now is a deep analysis of my
> trades and to see if we can automate them."* **Body = `op_record` · `op_conditions` ·
> `automation_gap` · `run_charts`**, then the reserved tail. The other **nine** sections
> (tournament, shadow, musings, router review, idle gates, rehab, greenfield…) are **RETIRED, NOT
> DELETED** — `friday_phases.RETIRED_2026_09_18` keeps every prompt intact because years of method
> traps live in that prose; restoring one is a move back into `PHASES`, never a rewrite.
> ⚠⚠ **THE STALE-STITCH TRAP:** every retired section's HTML is STILL ON DISK from previous weeks,
> so `assemble` names them explicitly and refuses them — stitching one in would publish last
> month's tournament review as this week's work, and that staleness is invisible because the file
> exists and parses. A test asserts the refusal.
> ⚠⚠⚠ **THE FAILURE MODE OF THIS REPORT IS FITTING.** ~28 captured presses, **ZERO** records of him
> looking and NOT trading, and 119 failed exit calibrations. Every analytical phase carries the
> limits in its OWN prompt (a rule that lives only here is a rule the phase never sees), and tests
> assert they are there: **no fitting below 30 labelled presses — positives AND negatives** · **do
> not run a 120th calibration** · **group by ENTRY, not by trade row** (the rows are scale-out
> exits; counting them inflates n ~2.5×) · **never infer a NULL `entry_source`** · every section
> ends in a **RANKED SHORTLIST**, never a verdict.
> ★ Budget now fits: body 105 min against 228, tail 180 against its 200-min reserve.

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
