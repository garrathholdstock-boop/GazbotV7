---
name: three-pass-adversarial-friday
description: The canonical Friday report = the "Conditioning & Opportunity Forensic Edition" (16-agent fleet + skeptic verification + PDF); tooling in scripts/friday/
metadata:
  node_type: memory
  type: project
  originSessionId: ccb6199e-59b1-4963-8e0b-88c88bf59bac
---

The weekly Friday report is the **"Conditioning & Opportunity — Forensic Edition"** (operator 2026-07-04: *"absolutely fantastic, save this as the Friday template"*). Doc: `docs/FRIDAY_REPORT_MASTER.md`; runbook + tooling: `scripts/friday/RUNBOOK.md`. Committed on branch `friday/forensic-template`. This EVOLVED FROM the earlier plain three-pass text pipeline (analyst→blind prosecutor→adjudicator) — that adversarial rigor now lives ON as the per-claim skeptic pass, but the deliverable is a deep charted PDF, not a text printout.

**What it is:** a ~150-page light-theme HTML report **+ an iPad PDF**, built by a **16-agent forensic fleet** run via the Workflow tool (`scripts/friday/friday_forensic_workflow.js`, parameterised by `{week, dateLabel, weekStart}`):
- 7 per-contract dossiers (MNQ/MES/MGC/M2K/MYM/MCL/MBT) — each with a **fertile-conditions map** ("make money when A ∧ B ∧ C → do X → £Y"), barren zones, named footprints, missed money, charts.
- 6 money-making strategy sims (ride-strength, air-pocket fade, time-of-day, exit overhaul, stand-down/off-switch, cross-contract).
- 3 playbooks (opportunity ledger, footprint playbook, deep charted loss autopsies via `scripts/loss_autopsy.py`).
- **Independent skeptic agents re-run every claim ≥ £250/wk**; each section stamped **VERIFIED / REFUTED / EXPLORATORY**.

**Pipeline (5 steps, from the main Claude session — see RUNBOOK):** capture-health check → run the workflow (writes `reports/friday/YYYY-WW/sections/*.html` + a manifest `{sections, verified}`) → **author the adjudicated exec summary** (`exec_summary_TEMPLATE.html` skeleton; the one judgement-heavy artifact; `{{VERDICT_TABLE}}` auto-injected) → `python3 scripts/friday/build_report.py --week ... --dates ... --manifest ... --exec ... --date-slug YYYY-MM-DD` (stamps sections, stitches, renders PDF) → register in the `/reports` tab (row `reports` table: kind='weekly', tags a JSON array not a plain string, body_md links `/static/weekly_<date>.html` + `.pdf`) + ping operator with the PDF link.

**PDF renderer:** weasyprint on **system python3** (`pip3 install --user --break-system-packages weasyprint`; apt libs `libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2` — installed on the box). The trading `.venv` is uv-managed with NO pip — don't try to install there.

**The honest discipline (lesson of edition #1):** on ONE week of ~150 trades, **9 of 10 big £ claims were cherry-picked / tiny-n / in-sample / "trade-less" artifacts** — only "stop fading violent moves / ride strength" survived independent re-run (and even that was ~70% one Monday trade → SHADOW not ARM). The report **leads with what SURVIVED, never the biggest number, and never cherry-picks the baseline** (the real week was ~−£185 all-in, not the −£1,100 first quoted — `RECON%`/`RECONCILED%` reconciliation rows had been excluded). Separate real **bugs** (orphan-clock age-anchor, MGC's missing atr_pct ceiling) from strategy claims — bugs are guaranteed money. Keep the ratchet (the profit engine). Anti-overfit spine C1–C9 still applies (thresholds are taxonomy constants, n<30 refuses, clock is a suspect, cross-contract coherence).

**⚠️ THE FRIDAY REPORT IS THE LABORATORY (operator 2026-07-07, emphatic).** Mid-week chats/studies are **LEADS, never findings** — thin-n, in-sample, one-day convenience samples. **Take NOTHING added mid-week as gospel.** Friday night is where extremely thorough backtesting + edge-hunting happens: **everything gets re-derived from scratch and challenged on the week's FULL data.** A lead reaches the report ONLY by surviving that Friday-night testing — never inherited from a chat, never "promoted." The operator flagging a mid-week lead as *interesting* = a request to test it HARD Friday, NOT to state it. (I once promoted the mid-week "contract-regime split" into `FRIDAY_REPORT_MASTER.md` §3 as a standing finding; operator REVERTED it — corrected in the RUNBOOK addendum header + REPORT INTEGRITY block, which now frame the addendum as the lab's input queue, not a promotion pipeline.)

**★ STANDING DIRECTIVE — exploring ALTERNATIVES to the existing IS the report's job (operator 2026-07-08).** *"The discipline we did to explore alternatives to existing is the exact job of the Friday report. Continue to ask WHY and WHAT ELSE is out there."* The report never merely DESCRIBES what the desk runs — for every live knob/gate/exit/archetype it asks (a) WHY is it this way (what was it built to fix), and (b) WHAT ELSE is out there — sweeps the alternatives on the week's tick data, robustness-gated, and follows the "why" to the root cause. The 2026-07-08 exit-architecture interrogation is the TEMPLATE (the 9-mechanism spine is scar tissue for bad entries; a two-line fixed exit beats it once entries are good; the root cause was the ENTRIES not the exits) — memory [[exit-architecture-scar-tissue]]. Recorded in `scripts/friday/RUNBOOK.md` standing-shape.

**Voice = plain daily English, money-first, no jargon** (operator hates "maths-professor" language; wants ~20 actionable next-week tunings but honesty caps it at what survives proof). See [[favourable-condition-gating-vision]], [[reversion-edge-quiet-tape-gate-tuner]], [[mes-entry-pullback-vol-ceiling]]. Reference edition: `reports/friday/2026-27/`.
