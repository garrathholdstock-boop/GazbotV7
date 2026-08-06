---
name: friday-report-full-pipeline-guarantee
description: "Friday report MUST be the full pipeline (4 workflows→build_report.py→hard gate), never a hand-written summary; operator's standing \"every week\" guarantee + the 3 hardenings"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d7443f59-d3b4-466f-b7e6-3903cacfd274
---

## ⚠ 2026-07-18 — HOW A FRESH/CRON SESSION FINDS THIS (operator: "the script at midnight needs to find this scope")
The entry point is **`docs/FRIDAY_SHADOW_REPORT_SCOPE.md`** — it now opens with a loud "★★★ FRIDAY MIDNIGHT — READ THIS FIRST" banner. Any Friday-report session (esp. the cron) must READ that file and produce to it — never hand-roll (I hand-rolled a 5-page summary 2026-07-18, operator: "is that report a joke?" / "what is this rubbish?"). CLAUDE.md §8 WEEKLY REPORT prompt now redirects to the scope doc as the first line. **V7 DATA:** the desk cut over to GAZBOT V7 2026-07-15 — the V5 pipeline reads `fut_shadow_sim_trades` (frozen at cut-over); for the current board use `scripts/friday/friday_shadow_v7_workflow.js` (reads `gazbot7/shadow.db` + the V5 2-week history + `bar_history`). Publish into `gazbot7/src/gazbot7/web_static/weekly_<date>.html`(+.pdf) so it shows at `/v7/reports` (the V7 reports page I built), AND the V5 `/reports` archive. Same spine/voice/gate — only the data source moved.

## ★★ APPROVED TEMPLATE — `docs/FRIDAY_SHADOW_REPORT_SCOPE.md` is the single source of truth
Operator 2026-07-11 blessed the **Rev-3** report ("that report is excellent… make it the template moving forward"). The canonical chapter shape lives in that doc, reconciled section-by-section to Rev-3 (`static/weekly_2026-07-10.html`) — do NOT reorder/drop chapters; edit the doc only when he asks; a report that doesn't match is a bug against that file. FIXED SPINE: §1 exec → per-contract **big runs & footprints** (FULL ATR census via `footprint_scorecard.py missed --top 100`, ~26 MNQ not 8; did we show up; L2 book where we have it; **how we grab it Monday**) → **through-lines** (how_we_grab_runs capstone · momentum confirmed-vs-loose + matrix · exit before/after at 2026-07-08 17:47 marker · live gates+knife-filter · **L2 order book first-look — MANDATORY** · OFF switch · greenfield · sizing) → **Your Mid-Week Musings** (OWN chapter, every lead→verdict) → **Winners** (per-sim) → **Bleeders** → **Small fry**. TWO workflows: `friday_shadow_workflow.js` (per-sim → manifest_shadow.json) + `friday_shadow_rev2_workflow.js` (leading chapters → manifest_shadow_rev2.json) → `build_report.py --mode shadow` (both manifests) → gate → `publish_report.py`. Playbook = `build_playbook.py` from `plays.json` → `static/monday_<slug>.html`, linked in the reports-tab body_md.
**STANDING PRINCIPLE — ★ momentum is TWO-SIDED, no fading.** Never a long-only momentum gate (this wk momentum SHORT +$1,435 > LONG +$1,006; on MES/MGC short was the only green side). "Shorts bled" = the FADE book's shorts (fighting up-moves), a different behaviour — kill FADING not shorting. Live prereq for momentum = re-enable shorts [[shorts-reenable-cluster]]. **L2 (`data/depth.db`, now 10-deep [[mnq-specialist-capture-experiment]]) MUST be used every week.**

## ★ 2026-07-11 REFRAME — the Friday report is now the SHADOW DESK, not the live desk
Operator, furious: *"you are analysing the live desk… i cant believe this. the report last week showed us the live desk is shit. so we created the shadow desk with 32 sims. i want analysis of those. dont tell me about all the crappy trades on the live desk. i want to know how to refine the shadow sims to make money on Monday."* The live desk is SETTLED-BAD — it gets ONE line, never a dossier. **The subject is the ~32 shadow sims** (`fut_shadow_sim_trades` ⟷ `shadow_real.db::shadow_real_pnl` on trade_id ⟷ `fut_signal_funnel` on entry_sid=cycle_ts). Per sim: made money / bled on HONEST fills, WHY, and THE ONE refinement (rvol/atr_pct/slope/session/book gate) to make it pay Monday.
- **Pipeline:** `friday_shadow_workflow.js` (scout ranks all sims → one plain dossier per sim → skeptics re-run each Monday change) → `build_report.py --mode shadow` (data-driven spine: Winners→Bleeders→Small-fry, ordered by real_pnl) → gate → `publish_report.py`. This REPLACES the four live-desk workflows as the weekly (they're kept for reference only).
- **The finding shape (wk 6-10 Jul):** 8 sims green (all momentum/thrust; star `tw_mnq_thrust_cont` +$992, real BEAT ceiling), the rest bled (fade/passive/standdown; `passive_chop` −$4,249). Lean into thrust, bury faders.
- **VOICE is non-negotiable:** plain daily English like last week's Rev 2 — talk TO him, numbers inside sentences, name the behaviour in human words. NOT a technical nerd reading numbers. He rejected the nerd voice twice.
- entry_ts is UNIX SECONDS; week filter = `entry_ts >= strftime('%s', weekStart)`.

## (superseded context) The full-pipeline guarantee — still applies to assembly/gate
2026-07-11: I registered a **4-page, 2,300-word hand-written summary** on the /reports tab in place of the standing multi-section journal. Operator (sharp): *"its about 4 pages. its a joke?"* → *"rebuild it to full length exactly like last week. and make absolutely certain thats what i get every week."* → *"i want all the detail. everything in plain english."*

**Why:** the real report is produced by a PIPELINE, not by me writing prose. I bypassed it. The research (a 45-agent wide hunt) was full; the write-up was a summary. That is the failure — the deliverable is the journal, not an exec digest.

**How to apply — the ONLY sanctioned Friday path (see `scripts/friday/RUNBOOK.md` steps 1–5):**
1. Run the FOUR workflows via the Workflow tool with `args:{week:"YYYY-WW", dateLabel, weekStart:"YYYY-MM-DD"}` — `friday_{forensic,capture,greenfield,passive}_workflow.js` (abs paths under /home/alphabot/alphabot2). They write section HTML into `reports/friday/YYYY-WW/sections/` and RETURN a manifest.
2. Each completion notification's output file is a WRAPPER `{summary,result,...}`; the manifest is `json.loads(wrapper["result"])`. Save to `manifest.json` (forensic) / `manifest_capture.json` / `manifest_greenfield.json` / `manifest_passive.json`.
3. Author `exec_summary.html` from `exec_summary_TEMPLATE.html` — lead with what SURVIVED the skeptics, use the CANONICAL live P&L (compute it, don't guess — [[verify-desk-facts-never-guess]]), keep `{{VERDICT_TABLE}}`.
4. `python3 scripts/friday/build_report.py --week YYYY-WW --dates "…" --manifest <4 csv> --exec … --date-slug YYYY-MM-DD` → `static/weekly_<slug>.html` + `.pdf`.
5. Publish ONLY via `scripts/friday/publish_report.py` — it runs `verify_report.py` (the HARD GATE) and refuses to register unless ≥30 numbered sections + all 6 chapters + ≥45k words + ≥15 charts + PDF. A summary fails every check.

**Three hardenings shipped 2026-07-11 (all in the repo):**
- **`verify_report.py` + `publish_report.py`** — the gate; a thin report physically cannot reach the /reports tab.
- **Workflow args bug** — the runner delivered `args` as a JSON STRING, so every script fell through to a hardcoded default and built the WRONG WEEK off a 1970 baseline. Fixed: all 4 scripts now `JSON.parse` string-args AND **throw** if week/weekStart missing (no silent stale default). If a future run's manifest says the wrong week, this is the regression.
- **`build_report.py` numberer is marker-agnostic** — agents use varied section markers (`SS`, `07`, `P`); it now numbers any `<span class="n">` that isn't already `§N`, so no section is orphaned from the TOC.

The /reports tab reads the `reports` DB table + serves `static/weekly_<slug>.html`; last week's file predates the TOC feature so it fails the gate's TOC check — that's fine, only NEW pipeline output is gated. Related: [[three-pass-adversarial-friday]].
