---
name: nightly-self-analysis-and-tell-me-how
description: "Operator vision (2026-06-20) — cockpit \"TELL ME HOW\" prescriptions + a nightly Max-plan self-analysis cron that precomputes the fix-analysis; logical next step to SCOPE"
metadata: 
  node_type: memory
  type: project
  originSessionId: b98efc3a-63db-4236-bd2a-69cc1a89a6f2
---

Operator vision after the Day-Review cockpit (B1–B7) shipped. **SCOPED → `docs/NIGHTLY_SELF_ANALYSIS_SCOPE.md` (2026-06-20, unblocked by A1); not yet built.** 4 open questions there for the operator (problem taxonomy, rolling-window length, also-a-Telegram?, artifact store).

**The reveal-the-analysis deepening.** The QUALITY panel already states the diagnosis (e.g. filter→losses → "FIX ENTRIES · never-green 191 · −$2,103"). Each such highlighted line gets a concrete, evidence-backed prescription — *which gates, which session_phase, what specific change, what the courtroom says.* Diagnosis → prescription.

**UI model (operator refined 2026-06-20): NOT an on-demand "TELL ME HOW" trigger button — just a DISCLOSURE.** Because the nightly sweep already precomputed the analysis, the affordance is a small reveal/expand that unfolds the stored analysis **inline** (the same idiom as tapping a ledger row → trade dossier expands in place). Instant, no spinner, no per-click compute.

**The mechanism (operator's hard constraint): his Claude MAX 20 plan, NOT API credits.** The answer is YES and it's the same vehicle as the §8 maintenance sweeps — a self-scheduled `CronCreate` job runs **inside the Claude Code session on the Max plan** (not headless `claude -p`, not API). So:

> **Nightly, AFTER the walk-forwards / edge-nightly (21:05 etc.) finish:** Claudio sweeps all the data + the freshly-confirmed courtroom verdicts, writes a thorough "how to fix" analysis per highlighted trade-quality problem, and **persists it**. The cockpit "TELL ME HOW" then just *reads* the pre-computed analysis → instant + free per click; the heavy thinking ran once, overnight, on the subscription.

Architecture = **precompute-nightly-on-Max → store (an analysis artifact, e.g. a table/parquet keyed by problem) → surface-on-click in `/day`.**

**VOICE of the nightly analysis (operator 2026-06-20, hard requirement): speak like a brutal senior fund manager. Direct, no sugar-coating, prescriptive.** Not "the data suggests entries may be suboptimal in chop." Instead: *"Your desk is not set up to trade chop days like this. The afternoon lull bleeds you every time — 200 trades that never went green. Do one of: A) gate out us_midday entirely, B) tighten the entry to X, C) cut the flat-clock to N min. Stop trading the chop."* Lead with the verdict, name the fix as concrete A/B/C options, say what to STOP doing. Aligns with CLAUDE.md §7 (don't suck up, don't pad) — but harder-edged for this surface.

**Hard dependency:** the prescription is only trustworthy once **A1** lands (the courtroom must judge the LIVE signal, not the dead `mb_*` shadow — see [[courtroom-vs-live-signal-mismatch]]) and the courtroom is legible (C-track). So this sequences AFTER A1 + C. Ties to [[edge-spectrum-pipeline]] (the walk-forward/courtroom that produces the verdicts the analysis reads).

**Near-term cockpit UI pass (operator, same convo) — do as ONE change off main AFTER A1 lands:**
1. **Chart time axis** — the P&L arc + the per-trade dossier chart need timeframe labels along the bottom (currently none).
2. **Layout lift** — DESK CONFIG (the right rail, `cf` grid area next to scoreboard+arc) is static/low-value; **move TRADE QUALITY (top — it's the verdict) + TIMING into that right rail**, and demote DESK CONFIG to a compact bottom strip (keep it — armed-vs-dark/live-gates matters pre-live — unless operator says drop it).
3. Plus whatever else the operator writes after eyeballing `/day`.

Day-Review package + `/day` cockpit record: DECISIONS §289; scope docs `docs/ANALYTICS_PACKAGE_COMPLETION_SCOPE.md`, `docs/DAY_REVIEW_RICH_UI_SCOPE.md`.
