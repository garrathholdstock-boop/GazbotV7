# THE FRIDAY REPORT — V7 CANONICAL SCOPE (locked 2026-07-24)

> **★★★ IF YOU ARE THE FRIDAY-REPORT CRON (fresh Claude session, ~Fri 22:00 UTC / midnight Paris): THIS FILE IS THE REPORT SHAPE. ★★★**
> The desk is **GAZBOT V7 — MNQ-ONLY**. IGNORE the old 7-contract structure (MNQ/MES/MGC/M2K/MYM/MCL/MBT) in `FRIDAY_SHADOW_REPORT_SCOPE.md` / `FRIDAY_REPORT_MASTER.md` — those describe the RETIRED V5 desk. Build the shape below. Publish ONLY via `scripts/friday/publish_report.py` (the hard verify-gate). Data is V7: `gazbot7/data/capture.db` (bars/ticks/L1 quotes/L2 book) + `gazbot7/data/gazbot7.db` (trades) + `gazbot7/data/shadow.db` (the shadow board).

## Voice — NON-NEGOTIABLE (operator, standing)
Write **long, detailed, and in plain daily English — TO Garrath**, not maths-professor / geek talk (he's rejected the "technical nerd reading numbers" voice repeatedly). Numbers live INSIDE sentences ("it made $992 over 28 trades and beat its ceiling"), behaviour named in human words ("it bought the dip and the dip kept going"). **LOTS of tables with clear facts** — every claim is a table with n / net$ / win% / $-per-trade, never a bare assertion. Honest about thin-n / one-week / in-sample — a clean "no edge here" beats a hopeful tweak. LEAD with what SURVIVED the skeptic, never the biggest number.

## The report is the LABORATORY
Everything is **re-derived FRESH on the week's full data** — mid-week chats/studies are LEADS to test HARD, never findings to inherit. For every live knob/gate/exit ask **WHY** (what it was built to fix) and **WHAT ELSE** is out there (sweep the alternatives on the week's tick data, robustness-gated). Honest money only: score on tick-repriced `real_pnl`, never optimistic sim `pnl_usd`.

---

## STRUCTURE (front → deep-dive)

### PART 1 — THE LIVE DESK (this week)
Plain-English review of the live 6-gate paper tournament (rgv_long, grind_long, capitulation_long, thrust_short, rgv_short, exhaustion_short). The week's P&L (canonical, computed not guessed), a **per-gate card table** (net · N · win% · avg win/loss · exit-mix · best/worst trade), what actually happened (the whippy trend/chop days, the STOP_UNFILLED self-heals, the direction-router trial and how it behaved), and the day-type split (did a gate's P&L depend on trend vs chop?). Tool: `scripts/filter_check.py`, `scripts/hour_watch.py`, the tournament trades.

### PART 2 — THE SHADOW DESK & PROMOTION
The shadow board ranked by honest `real_pnl` (all-time + this week). **Best sims for promotion**, each with a robustness read (not just the top number):
- **★ abs_veto_55s** — the lead promotion candidate for Monday. Present the full robustness battery (`scripts/abs_veto_robustness.py`): headline, per-day spread, **regime split (chop vs trend)**, walk-forward halves, head-to-head vs un-vetoed thrust. Honest caveats (sample size, concentration).
- **Relegation view** — the live gates ranked; `rgv_short` the relegation candidate; the two long-faders (`rgv_long`/`capitulation_long`) = KEEP + direction-router guard (the router IS the fix). Each with WHY (which day-types / exit-reasons bled).
- The over-trading caveat baked in (shadow overstates — nominates; paper judges).

### PART 2.5 — MID-WEEK MUSINGS (every lead, tested HARD — its own chapter)
Each mid-week lead walked in plain English: the test and the honest verdict (HELD → where it landed / REFUTED → why). Nothing silently dropped. **★ FLAGGED THIS WEEK — interrogate the DIRECTION-ROUTER's architecture (operator, 2026-07-24):** we built a router on a **15-min timer** that replays the Paris-day regime from capture, flips `gate_switches.env`, and benches the counter-trend reversion faders (2-mark hysteresis). It works (backtest +$580 Mon–Thu, no negative day; live-validated overnight). But the report's job is to ask **is this the BEST way to achieve the objective, or is there a more ELEGANT one?**
- **OBJECTIVE (state it plainly):** stop a gate trading *against a proven trend* (the direction-blind ER bands fade a clean down-trend), reactively, without over-clipping the chop days the faders earn on.
- **WHAT WE BUILT + its costs (from live data):** a polling timer + switch-file. Known costs surfaced this week — **reaction lag** (can't bench until a trend is proven ~15-30min in; `rgv_short` −$64.5 fading a fresh up-move before the bench), **sticky-exit** (over-holds a trend through alternating chop — the fast_exit fix backtested +$0 so it's dormant), **whipsaw churn** on a fast-flipping day, and a **partial-bar-vs-replay** artifact between live runs and clean replays.
- **WHAT ELSE — research + BUILD + BACKTEST the alternatives** against the current router on the week's data: (a) **per-gate direction-guard IN-CODE** — a directional veto inside each fader's gate function (no long-fade when VWAP-slope/net-bias is down), per-tick, no polling lag, no switch-file, no separate service (the Saturday option-A end-state); (b) **event-driven flip** (bench on a confirmed regime-change event, not a 15-min poll); (c) **continuous in-tournament regime gating** (the tournament computes regime each tick and gates the open directly — no router service, no file at all); (d) tuning the timer granularity. For each: does it cut the reaction-lag / whipsaw the polling router can't, and does it keep the +$580? Verdict: keep the router as-is, or migrate to a more elegant mechanism — with the backtest to back it. This is a genuine architecture question the report should answer, not assert.

### PART 3 — ★ HOW WE GRAB THE BIG RUNS (the closing deep-dive — the section the operator loves)
Cold and tape-first: **ignore what the desk did mid-week**; start from the raw L1/L2 tape and ask where the money was and whether we showed up. MNQ-only but **deep** (our tape + 58.9M-row L2 book). THREE MOVEMENTS:

**Movement 1 — the full runs census (the long table).** Tool: `scripts/run_census.py`. Every 15-min move ≥ **1.5× MNQ's typical range** — the FULL census, EVERY run, **never a top-N** (07-17 wrongly showed top-30 of 207 — do not repeat). Columns per run: `time · dir · move(pt) · $ 1-lot ceiling · us (caught/FOUGHT/sat) · GATE · real$ · flow (net aggressor) · pre-run amp% · L2 book (far-side depletion) · cause-cluster`. Then: the **cause-cluster taxonomy** (VACUUM / FLOW-LED / OPEN-NEWS / UNCLASS) with a per-cluster caught/fought/sat + ceiling-$ table; the **pre-run signal funnel** (rvol/atr%/vwap-dist/vwap-slope by cluster) with the honest-null callout when the tape doesn't lead; the **per-run L2 book read** (did depth telegraph the move?); and the **ceiling-vs-honest-money reconciliation** (caught N → +$X of $Y ceiling = conversion%; fought → wash; sat-out → $0 = the money on the table), tied to the actual gate.

**Movement 2 — the idle-gate lab.** Could the desk's EXISTING gates have caught the misses? Fire them mechanically on every run, all week: `rule→gate | trigger | exit`, a scoreboard (`fires · net$ · win% · $/fire · big-moves-caught X/N · verdict`), a cumulative-P&L curve, a why-each-loses paragraph, a `DON'T ARM`/`HONEST NULL` verdict. A null is a result.

**Movement 3 — the greenfield lab (invent gates from scratch, backtest to death).** The core. Start from the specific missed-run clusters. **Family A (catchable) vs Family B (uncatchable)** precursor split (dissect the 10 min before each run). The **"graves"** — every FAILED candidate shown by name with its losing stats and a one-line cause of death (the operator's favourite honesty device — show the failures). A mechanical `Component | Rule` spec per survivor (thrust/participation/entry/stop/exit/costs) + what was left out and why. Full backtest apparatus: the **parameter sweep** (edge only appearing as n collapses = curve-fit tell), a cumulative-P&L curve, the excursion "killer statistic," a 250ms **book-imbalance separation** table, a **day-by-day** table, and the robustness kills — **strip-the-3-best-trades**, **long/short symmetry**, **cost-stress**, and an **out-of-sample leg** (archive days / held-out window). Every invented gate carries a **`big-moves-caught: X/N`** column against the exact runs the census proved we missed (the "stitch" 07-17 dropped). Verdict pills `SHADOW`/`NULL`/`DON'T ARM` + a skeptic-caveat list, then a second adversarial re-run that downgrades even survivors. Never a premature green light. Backtest tools: `scripts/gate_backtest_tickhonest.py`, `scripts/footprint_backtest_duck.py` (tick+L2, DuckDB).

---

## Tooling (V7-native)
- `scripts/run_census.py` — Movement-1 census (V7 rebuild of the V5 `footprint_scorecard.py missed`, which was hardcoded to the retired alphabot.db/ticks.db).
- `scripts/gate_backtest_tickhonest.py` · `scripts/footprint_backtest_duck.py` — greenfield backtests, tick-honest + L2.
- `scripts/abs_veto_robustness.py` — the promotion battery.
- DuckDB + pandas for ALL analytics (the standing rule). Publish via `scripts/friday/publish_report.py` (hard gate: ≥20 sections, ≥25k words, ≥15 charts — a thin report is refused).

## Do-not-repeat (the 07-17 regression)
Full census not top-N · the 9+ columns incl. flow/amp/$-ceiling/book · the cluster taxonomy + pre-run funnel + per-run L2 read · ceiling-vs-real reconciliation · greenfield STARTED from the missed runs with a big-moves-caught column · full param sweep + cumulative curve + excursion + book-separation tables + OOS leg. This section is the last and biggest; it is where the report earns its keep.
