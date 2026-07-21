# Friday report — the TOURNAMENT section (scope, NOT built)

**Status:** SCOPED 2026-07-21. Add a **Tournament Scorecard** to the weekly Friday report so
the operator's **Saturday relegate/promote decision** has a proper written weekly analysis in
front of it — not just the live cockpit. Pairs with the standing rule *tournament changes
happen only on Saturdays after the Friday report* ([[tournament-changes-saturday-only]]).
Read-only view/report layer; never touches the trading path.

---

## 1. The Friday report as it stands (what we're adding into)

Canonical pipeline (`/home/alphabot/alphabot2/scripts/friday/`, RUNBOOK.md): a **5-step**,
multi-agent, adversarially-verified, ~150–300pg **HTML + iPad-PDF** report served at
`/static/weekly_<date>.html`, linked from `/reports`, published only through a **verify gate**
(`publish_report.py` → `verify_report.py` refuses a stub).

- **Steps:** (1) compute week context → (2) run workflows (`friday_*_workflow.js`, 7 agents +
  skeptic each) → section manifests → (3) hand-author the adjudicated exec summary → (4)
  `build_report.py --week … --manifest …` assembles + renders (stable ids, clickable TOC, PDF
  bookmarks, per-claim VERIFIED/REFUTED stamps) → (5) `publish_report.py` (gated).
- **FIXED 6-part spine** (operator-locked, "Revision 2 is where the report finishes"):
  §1 Settled Science · §2 The Tape (the guts — per-move participation verdict) · §3 Shadow Gates ·
  §4 New Investigations · §5 Infrastructure · §6 Unknown Unknowns. Two week-over-week metrics:
  Explained %, Unexplained count.
- **Standing chapters** (Capture / Greenfield / Passive) slot in via `build_report.py` and
  **skip gracefully if a lab didn't run — the structure never changes.** ← this is the hook.
- V7 workflows already exist and read `gazbot7/data/` (`friday_shadow_v7`, `friday_mnq_deep`,
  `friday_greenfield_v7`).

**Hard rules to respect:** the spine is FIXED (don't reshape it); the report is the **laboratory**
(everything re-derived FRESH on the week's data — mid-week chat is LEADS only); every knob asks
**WHY + WHAT-ELSE**; only the verify gate publishes.

## 2. Why a tournament section now

The report's memory says the subject was the SHADOW SIMS, not the live desk — but that predates
the cutover. **The live desk is now the 6-gate paper tournament** (rgv-long, grind-long,
capitulation-long, thrust-short, rgv-short, exhaustion-short), and the *whole point* of the
tournament is a **weekly relegate-worst-2 / promote-from-shadow** decision the operator makes
**Saturday**. That decision currently has only the live cockpit (indicators) behind it. It needs
a written, data-computed, cross-regime weekly analysis — the report's natural job.

## 3. The proposed section — "TOURNAMENT SCORECARD" (data-computed, not agent-narrated)

A new **standing chapter** in `build_report.py` (like Capture/Greenfield/Passive — additive,
skips gracefully, does NOT reshape the 6-part spine). It is **computed from the DB** (reproducible,
honest) with a light narrative, NOT an agent's free-text — the numbers are the point.

Contents:
1. **Per-gate weekly card** (each of the 6 gates): net P&L (of fees) · N · win% · PF · avg win /
   avg loss · **exit-mix** (chandelier / 2R / giveback / stop / absorption / adverse / max-hold /
   stop-unfilled — from `trades.exit_reason`) · **best & worst trade**.
2. **Day-type breakdown** — split each gate's week by session **day-type** (trend vs chop vs
   mixed, classified from `capture.db` bars per Paris/session day: efficiency-ratio + range + ATR,
   the same read as the honest tape-read). The key question the Saturday decision needs: *is a
   gate's P&L regime-specific?* (e.g. grind-long earns on trend days, bleeds on chop) — a gate that
   only works in one regime is a candidate to keep-but-condition, not relegate.
3. **The entry funnel per gate** (from `signals`): submitted → filled through-rate + **nofill** +
   avg slippage — so a "quiet" gate is distinguished from a "not-filling" gate (a gate whose edge
   is real but that keeps missing fills is a *fill* problem, not a relegation).
4. **Relegation view** — gates ranked by a **rolling multi-week** score (NOT one week — one week is
   thin and over-fits), bottom-2 highlighted with the WHY (which day-types / exit-reasons bled).
5. **Shadow PROMOTION FEEDER** — the shadow board ranked by honest real_pnl (all-time + this week),
   mapped to gate family, with the **over-trading caveat baked in** (shadow overstates — it ignores
   the single-position constraint and enters at hindsight bar-closes; it NOMINATES, paper JUDGES).
   Reuse the live `/api/futures/promotion` logic.
6. **The Saturday brief** — a synthesis: the RECOMMENDED relegate-X / promote-Y, each with WHY +
   WHAT-ELSE (tested on the week's data, not asserted). Explicitly a **recommendation the operator
   decides Saturday** — never auto-applied (the tournament-changes-Saturday-only rule).

## 4. Where it sits in the spine

Two honest options (operator picks):
- **(a) A standing chapter "Tournament Ledger"** right after §2 The Tape — the live-desk performance
  is the natural continuation of the participation verdict (the gates ARE the participants now).
- **(b) A demarcated appendix "Saturday Decision Brief"** after the main body (like the Mid-week
  Addendum is demarcated) — keeps the fixed analytical spine untouched and frames it as the
  operational decision input it is.

Recommend **(b)** for cleanliness (spine stays pristine; the brief is clearly the Saturday input),
with the per-gate day-type/participation feeding §2's verdict where it fits.

## 5. THE framing decision (open — needs the operator)

Does the **tournament become the report's primary live-desk subject**, evolving the live-mode spine
to be per-gate? Or does the shadow board stay the analytical subject and the tournament ride as the
new operational-ledger chapter? Recommend the latter first (lower risk, respects the fixed spine),
revisit once the tournament has multi-week history.

## 6. Data sources (all read-only)
- `gazbot7/data/gazbot7.db` — `trades` (per-gate P&L / exit-mix / timestamps), `signals` (funnel).
- `gazbot7/data/capture.db` — `bars` (day-type classification per session day).
- `gazbot7/data/shadow.db` — `shadow_trades` + `shadow_real` (the promotion feeder).
- Reuse: `web.tournament_json` / `web.promotion_json` / `web.execution_json` logic + the tape-read
  day-type math — so the report and the cockpit agree by construction.

## 7. Implementation sketch (when built)
- A **data-prep script** `scripts/friday/tournament_scorecard.py` (runs on gazbot7 venv) queries the
  three DBs, classifies day-types, and emits a **self-contained HTML fragment** (the report's section
  format: `<h2><span class="n">…</span>…`, tables, one bars chart, `verdict` spans) + a small JSON of
  the numbers. Computed, deterministic, re-runnable — no agent needed for the ledger (agents can add a
  WHY narrative on top if wanted, skeptic-verified like the rest).
- `build_report.py` gains a standing chapter that includes the fragment if present, **skips gracefully**
  if absent (structure never changes).
- Cross-check parity: the scorecard's per-gate P&L must equal the cockpit's `tournament_json` for the
  week (a test), so the two never drift.

## 8. Phasing
- **P1** — `tournament_scorecard.py`: per-gate week card + exit-mix + day-type split (the core ledger).
- **P2** — the shadow promotion feeder + the entry funnel per gate.
- **P3** — the rolling multi-week relegation score + the Saturday brief synthesis.
- **P4** — wire into `build_report.py` as the standing chapter + the parity test + publish through the gate.

## 9. Honest caveats
- **One week is thin** — relegation must use a **rolling multi-week** score, not a single week, or it
  over-fits noise (and a gate can have a bad week on a hostile regime it's not built for). Day-type
  attribution is what saves this: judge a gate on ITS regime, not the week's mix.
- **Shadow overstates** — the feeder is a nomination list, never an auto-promote (baked-in caveat).
- **The section RECOMMENDS; the operator decides Saturday.** Never auto-relegate/promote from the report.
- Respect the report's discipline: **laboratory** (re-derive fresh), **verify gate** (no stub publishes),
  fixed spine (additive chapter only).

## References
Pipeline: `alphabot2/scripts/friday/{RUNBOOK.md,build_report.py,publish_report.py}`. Live logic to reuse:
`gazbot7/src/gazbot7/web.py` (`tournament_json`, `promotion_json`, `execution_json`). Rule:
[[tournament-changes-saturday-only]]. Report discipline memories: Friday = laboratory / scientific journal.
