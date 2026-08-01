export const meta = {
  name: 'friday-v7-resume',
  description: 'RESUME the 2026-07-31 V7 Friday report from Greenfield onward — Census/Desks/Rehab/BigRuns already on disk from the overnight run that died at 05:47.',
  phases: [
    { title: 'Greenfield', detail: 'Movement 3 — the escalating hunt, per cluster, full→top25→top15 + chop-scalp lab' },
    { title: 'Skeptic',    detail: 'adversarially re-run every survivor from scratch' },
    { title: 'Assemble',   detail: 'stitch → light HTML + PDF + playbook, publish (Rev1)' },
    { title: 'Proofread',  detail: 'adversarial read as the operator → gap-fill unanswered questions → Revision 2 → wake-up-standard final check' },
  ],
}

// ★ RESUME CONTEXT (2026-08-01): the durable Friday run fired on schedule, froze the census, and
// built Census + Desks + Rehab + BigRuns (all on disk in SEC, written 22:24–05:47). The driving
// session then exited, killing the build before Greenfield. This script picks up EXACTLY there.
// Sections already complete and NOT to be regenerated:
//   movement1_census.html · part1_live.html · part2_shadow.html · part25_musings.html
//   part2_6_router_review.html · part1_5_rehab.html (+ rehab_*.md) · movement2_idle_gates.html
const SCOPE = '/home/alphabot/gazbot7/docs/FRIDAY_V7_REPORT_SCOPE.md'
const SEC = '/home/alphabot/gazbot7/reports/friday_v7/sections'
const STYLE = 'Plain daily English written TO Garrath, money-first, NO maths-professor jargon, LOTS of clear-fact tables. Honest about thin-n / one-week / in-sample. Lead with what SURVIVED. Light-theme HTML FRAGMENT (a stitch-in, not a full page) using classes: h2>span.n, p.lead, div.card>h3, div.callout>div.ct, table with td.num/td.ln, tr.row-hl (green/caught) / tr.row-bad (red/fought), span.tag verdict pills. Every number from a REAL computation you actually ran — never invented.'
const SEGMENT = 'BACKTEST DISCIPLINE (operator, 2026-07-31 — governs EVERY backtest/sweep in this report): the desk is REGIME-CONDITIONAL, so NEVER blanket one fixed gate/exit config across the whole tape — that averages the regimes a config should be ON with those it should be OFF/different and washes the edge out (you would wrongly bury a real edge or accept a mediocre average). (1) SEGMENT the tape by REGIME — dead-chop / normal-chop / in-between-building / clean-trend / violent-whipsaw, keyed on ATR level + ER + range-break (NOT the clock alone; ATR carries the time-of-day effect) — AND by TIME-OF-DAY (overnight/pre-open vs US session post-13:30 UTC, where the big 4R/6R runners live). (2) Score each config ONLY on its HOME segments and report per-segment n / net / win% / $-per-trade — evaluate the POLICY (regime→config), never a static config sprayed across all tape; a blanket cross-tape number with no regime split is a BUG in this report. (3) Every R-target and threshold — INCLUDING the regime→exit cheat-sheet Lot-A/Lot-B scalp Rs (faders 0.5/1.5, momentum 1.5/2.5, trend 2.5/wide) — is an operator GUESS/PRIOR, NOT a truth: SWEEP it per regime and PROVE the robust optimum (parameter plateau, strip-the-best-trades, per-day / leave-one-day-out, OOS leg), then report the PROVEN Rs vs the guess and whether they hold. (4) Use as much tape as available so each regime bucket keeps a meaningful n.'
const GF_SCHEMA = { type: 'object', required: ['survived', 'name', 'net', 'win_pct', 'graves', 'summary'], properties: {
  survived: { type: 'boolean' }, name: { type: 'string' }, net: { type: 'number' }, win_pct: { type: 'number' },
  big_moves_caught: { type: 'string' }, graves: { type: 'array' }, summary: { type: 'string' } } }
const VERDICT = { type: 'object', required: ['holds', 'why'], properties: { holds: { type: 'boolean' }, why: { type: 'string' } } }
const PROOF_SCHEMA = { type: 'object', required: ['mission_ok', 'reads_ok', 'thorough_ok', 'sensible_ok', 'issues', 'unanswered'], properties: {
  mission_ok: { type: 'boolean' }, reads_ok: { type: 'boolean' }, thorough_ok: { type: 'boolean' }, sensible_ok: { type: 'boolean' },
  issues: { type: 'array', items: { type: 'object', required: ['section', 'problem', 'fix'], properties: {
    section: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' } } } },
  unanswered: { type: 'array', items: { type: 'object', required: ['question', 'why_he_pokes', 'how_to_answer'], properties: {
    question: { type: 'string' }, why_he_pokes: { type: 'string' }, how_to_answer: { type: 'string' } } } } } }

// Frozen census, read from the completed run's journal (SEC/census_summary.json is the source of truth).
const CENSUS = { runs: 73, sat_out: 53, ceiling: 14519 }
log(`resuming from Greenfield · frozen census: ${CENSUS.runs} runs, ${CENSUS.sat_out} sat out, $${CENSUS.ceiling} ceiling`)

// ── Phase 4 — Movement 3: the ESCALATING greenfield hunt (DO NOT GIVE UP) ───────────────────────
phase('Greenfield')
const clusters = ['VACUUM', 'FLOW-LED', 'OPEN-NEWS']
let survivor = null
for (const level of ['full', 'top25', 'top15']) {
  log(`greenfield hunt — level=${level}`)
  const res = await parallel(clusters.map((cl) => () => agent(
    `GREENFIELD HUNT — census level "${level}" (full = all sat-out runs; top25 = the 25 biggest; top15 = the 15 biggest), cluster "${cl}". The frozen census for the COMPLETED week (Mon 2026-07-27 → Fri 2026-07-31) is at ${SEC}/census_summary.json — ${CENSUS.runs} runs, ${CENSUS.sat_out} sat out, $${CENSUS.ceiling} hindsight ceiling. Do NOT re-run run_census.py (multi-minute tick crunch). IGNORE the existing gates. INVENT a brand-new entry signal to catch these runs, with an exact mechanical spec (trigger/direction/entry/stop/exit). BACKTEST it tick-honest on capture.db, net of ~$5/round-trip. Robustness: parameter sweep (does the edge only appear as n collapses = curve-fit tell?), strip-the-3-best-trades, long/short symmetry, and a big-moves-caught X/N against these runs. Do NOT curve-fit a fake winner — if it's a coin-flip that bleeds, it's a GRAVE (report its losing stats + one-line cause of death). The operator wants EVERY grave shown. Narrowing to the biggest runs may reveal a stronger footprint the marginal runs washed out — hunt hard. ${SEGMENT} Return {survived, name, net, win_pct, big_moves_caught, graves[], summary}. Write your working to ${SEC}/gf_${level}_${cl}.md`,
    { phase: 'Greenfield', schema: GF_SCHEMA, label: `gf:${level}:${cl}` })))
  const winners = res.filter(Boolean).filter((r) => r.survived)
  log(`  level=${level}: ${winners.length}/${clusters.length} survived`)
  if (winners.length) { survivor = { level, winners: winners }; break }
}
// ★ CHOP-DAY SCALP greenfield (operator 2026-07-31): DON'T GIVE UP on the chop days
await agent(
  `CHOP-DAY SCALP GREENFIELD — operator's explicit focus. Mon 07-27, Tue 07-28 and Fri 07-31 were CHOP and BLED / broke even with the CURRENT gates — but "untradeable" is only true for THOSE gates; the big trend days (Wed 07-29 / Thu 07-30) already carry most of the week's profit via the trend gates + dual-chandelier, so the WIN here is to stop DONATING on the chop days: if a purpose-built scalp can clear +$200–300 on a chop day instead of sitting out, that's a big weekly swing. GET IN THE LAB and TRY to build a CHOP-TURN SCALP specialist for these 3 days: catch the oscillation TURNS — a VWAP-pullback / mean-reversion-at-the-range-extreme / exhaustion-of-a-leg entry (revive the old vwap_pullback archetype or similar) — enter ON the turn, and SCALP TINY: bank the moment it goes green at ~0.5R / 1R (sweep the exact R — whatever clears the ~$3 round-trip + a couple of bucks/trade). We do NOT need runners here; we need a high hit-rate that grinds small green through the rotation. ★ PREVIEW FINDING (2026-07-31, start from here): a naive price-only turn-fade (VWAP-extension + a reversal bar) is a COIN-FLIP — win-rates sit right ON each R's breakeven line (0.5R 58-65% vs 67% needed, 1R ~50%, 1.5R ~40%) and it OVERTRADES (~350-1500 trades/day) so fees bleed it −$1.6k to −$8k/3-days; selectivity cut the loss ~5x (trade count is everything — every marginal trade is a fee tax). So price-vs-VWAP alone can't predict the turn. The EDGE must come from turn QUALITY: hunt the L2 BOOK (far-side depletion / absorption at the extreme = the fade actually exhausting) + footprint, not price alone, and be FAR more selective (a few high-quality turns/day, not hundreds) to lift the win-rate ABOVE breakeven. ★ LEAD WITH L2 ORDER FLOW (operator direction): the separator MUST be the book, not price — and this is the SAME LINEAGE as exhaustion_short, one of our best gates, which was BUILT from L2 footprints (footprint.py / exhaustion_signal). At the price extreme, require the FAR SIDE to be ABSORBING / DEPLETING — the fade actually exhausting = a real turn — using the L2 book (capture.db book table / depth.db, 10-deep) + footprint aggressor-delta. ★ ALSO add a VWAP-FLAT "is-it-actually-ranging" filter: only fade when VWAP / the day is RANGING (flat), NEVER when VWAP is sloping into a trend leg (mean-reversion only pays in a range). Invent an EXACT mechanical spec (turn-trigger = stretch + L2-absorption-at-the-extreme + VWAP-flat-ranging / direction / entry / stop / scalp target), FAR more selective than the price-only preview (a few high-quality turns/day, not hundreds). BACKTEST tick-honest on the 3 chop days (capture.db ticks + L2 book far-side/absorption where useful). ROBUSTNESS: must hold on ALL THREE chop days (not one), strip-the-best-trades, param sweep (edge only as n collapses = curve-fit tell), AND check it doesn't bleed the trend days (Wed/Thu) — ideally it's regime-gated to fire only in chop. Report the per-trade edge ($ and win%), a projected chop-day P&L, and whether it clears the +$200–300/chop-day bar. Honest: chop turns may be unpredictable ([[run-catcher-null-all-microstructure]]) — but TRY HARD and show EVERY grave by name with its cause of death. Verdict: a deployable chop-scalp gate (SHADOW first), or an honest NULL naming the one stone unturned. ${SEGMENT} Write your working to ${SEC}/gf_chopscalp.md`,
  { phase: 'Greenfield', label: 'gf:chop-scalp' })
// synthesize Movement 3 from all graves across every level + any survivor
await agent(
  `Read every ${SEC}/gf_*.md you can find (the greenfield hunts at full / top25 / top15 + gf_chopscalp.md). ★ IMPORTANT: ${SEC}/movement3_greenfield.html currently on disk is a STALE 2026-07-24 file from LAST week — OVERWRITE it completely; do not carry over any of its findings, survivors or graves. Write the flagship Movement 3 section for the COMPLETED week (Mon 2026-07-27 → Fri 2026-07-31) as a detective story: the Family A/B split, the oracle proof that the runs are real money (so the problem is the ENTRY), the GRAVES at each narrowing level, and ${survivor ? `the SURVIVOR(s) at the ${survivor.level} level — present the mechanical spec + backtest + robustness, verdict SHADOW (never live)` : 'the honest NULL after the full→top25→top15 hunt all came up empty — name the ONE stone still unturned for next week'}. CRUCIAL: report the size-threshold at which a footprint becomes tradeable, if any (that IS the finding). ★ PLUS a HEADLINE "CHOP-DAY SCALP LAB" subsection from ${SEC}/gf_chopscalp.md (operator's explicit focus): the chop-turn-scalp built for the days that bled with current gates (Mon 07-27 / Tue 07-28 / Fri 07-31) — the mechanical spec tried, the per-trade edge ($ + win%), the projected chop-day P&L vs the +$200–300 "beats sitting out" bar, the survivor (SHADOW-first) or the honest NULL, and every grave by name. Frame it as: can we stop DONATING on chop days? ${SEGMENT} ${STYLE} Write to ${SEC}/movement3_greenfield.html`,
  { phase: 'Greenfield', label: 'M3:synthesis' })

// ── Phase 5 — adversarial skeptic on every survivor ────────────────────────────────────────────
phase('Skeptic')
if (survivor) {
  const verdicts = await parallel(survivor.winners.map((w) => () => agent(
    `SKEPTIC: adversarially try to REFUTE the greenfield survivor "${w.name}" (${w.summary}) from scratch on the week's data — different window split, strip its best trades, check it isn't one lucky day, re-price with harsher costs, and CHECK it survives in its HOME regime segment (not just blanket-averaged). Default to refuted=holds:false if uncertain. Return {holds, why}.`,
    { phase: 'Skeptic', schema: VERDICT, label: `skeptic:${w.name}` })))
  const killed = verdicts.filter(Boolean).filter((v) => !v.holds)
  log(`skeptic: ${killed.length}/${verdicts.length} survivors REFUTED on re-run`)
  if (killed.length) {
    await agent(`The skeptic REFUTED ${killed.length} greenfield survivor(s): ${killed.map((k) => k.why).join(' | ')}. Update ${SEC}/movement3_greenfield.html: downgrade the refuted candidate(s) to a GRAVE with the skeptic's reason, and if nothing survives the skeptic, land the section on the honest NULL. Keep the ${STYLE}`, { phase: 'Skeptic', label: 'M3:skeptic-fold' })
  }
}

// ── Phase 6 — assemble → light HTML + PDF + playbook, publish ───────────────────────────────────
phase('Assemble')
const built = await agent(
  `Assemble the full V7 report for the completed week ending Fri 2026-07-31 (so the outputs are weekly_2026-07-31.html/.pdf + monday_2026-07-31.html). Sections live in ${SEC}: part1_live, part1_5_rehab, part2_shadow, part25_musings, part2_6_router_review, movement1_census, movement2_idle_gates, movement3_greenfield. ★ NOTE — one rehab dossier's filename contains a "/" which the writing agent turned into a DIRECTORY: the file is at "${SEC}/rehab_grind-exit scale-out (two_ratchet / partial shadows).md" (i.e. a dir "rehab_grind-exit scale-out (two_ratchet " containing " partial shadows).md"). Its CONTENT is intact and is already reflected in part1_5_rehab.html — just don't let a glob over rehab_*.md choke on it. Extend scripts/friday_v7_build.py so it stitches ALL of these (Part 1 live desk, then Part 1.5 the REHABILITATION dossier, then Part 2 shadow/promotion, then Part 2.5 musings, then the ROUTER OPERATION REVIEW as its own headline section, then the 3 movements) into the light-theme shell in that order (the Rehabilitation section is a headline live-desk section — place it right after the live desk, not buried), then run it with system python3 to render the HTML + PDF into src/gazbot7/web_static/. Regenerate reports/friday_v7/plays.json from THIS week's actual findings — derive each play from a verdict a section above actually reached (live-desk, rehabilitation, shadow/promotion, musings/router-study, greenfield). ${'reports/friday_v7/plays.json currently on disk is a STALE 2026-07-24 file — overwrite it; do NOT carry over any prior week\'s plays'}; if a section didn't conclude something, it isn't a play. Then build the Monday playbook via /home/alphabot/alphabot2/scripts/friday/build_playbook.py into web_static as monday_2026-07-31.html. Verify all three outputs exist and every section is present, then report the file paths + word count. Do NOT publish a thin report.`,
  { phase: 'Assemble', label: 'assemble+render' })

// ── Phase 7 — PROOFREAD + REVISION 2 (operator-critical: must be GOOD on wake-up) ───────────────
phase('Proofread')
const critique = await agent(
  `ADVERSARIAL PROOF-READER — read the just-built report as GARRATH will, and be HARD on it. Find the newest src/gazbot7/web_static/weekly_*.html (Rev1, should be weekly_2026-07-31.html) and read it IN FULL, plus ${SCOPE} (the mission). Grade five things: (1) MISSION — sticks to the V7 shadow-desk / regime mission, LEADS with what SURVIVED the skeptic, honest baselines (never cherry-picked), no gate benched at face value (rehab shown)? (2) READS WELL — plain daily English written TO Garrath, money-first, NO maths-professor jargon, LOTS of clear fact-tables? (3) THOROUGH — every section complete, no thin / placeholder / "TODO" bits, every number a REAL computation? (4) MAKES SENSE — no contradictions, shadow-vs-live reconciled, each verdict follows its own numbers? ★ SPECIFICALLY check for STALE CONTENT leaking in from last week's 07-24 report (this build resumed from a crashed run, so a prior-week fragment surviving into the stitch is a REAL risk): every section must be about Mon 07-27 → Fri 07-31, and the week headline should reconcile to +$625 / 206 trades. (5) ★ UNANSWERED QUESTIONS Garrath WILL poke at — list EVERY loose end / obvious follow-up the report raises but doesn't close. His known tells: a shadow number without the live cross-check; a claim on thin-n stated as fact; "so what do I actually DO Monday"; a $ figure without its baseline; a gate called bad without the rehab attempt; the exit-ladder rungs left unproven (esp. BIG-TREND); a "why" not chased to root cause; a promotion/relegation call without the robustness battery. Be specific and cite the section. Return the structured critique.`,
  { phase: 'Proofread', schema: PROOF_SCHEMA })
log(`proofread: mission=${critique?.mission_ok} reads=${critique?.reads_ok} thorough=${critique?.thorough_ok} sensible=${critique?.sensible_ok} · ${(critique?.unanswered||[]).length} unanswered · ${(critique?.issues||[]).length} issues`)
const gaps = [
  ...((critique?.unanswered) || []).map((g, i) => ({ slug: `q${i}`, task: `UNANSWERED QUESTION Garrath will poke at: "${g.question}" (he pokes because: ${g.why_he_pokes}). ANSWER it fully from the REAL data — ${g.how_to_answer}. Tick-honest + regime-segmented. ${SEGMENT}` })),
  ...((critique?.issues) || []).map((g, i) => ({ slug: `fix${i}`, task: `REPORT ISSUE in "${g.section}": ${g.problem}. FIX: ${g.fix}. Recompute / rewrite from real data as needed.` })),
]
if (gaps.length) {
  await parallel(gaps.map((g) => () => agent(
    `${g.task}\n\nProduce a tight, REPORT-READY block — plain English to Garrath + a clear fact-table — that FULLY resolves this. Write it to ${SEC}/rev2_${g.slug}.html, opening with a one-line marker naming which report section it patches/extends.`,
    { phase: 'Proofread', label: `rev2:${g.slug}` })))
  await agent(
    `REVISION 2 — the report MUST be good for Garrath (this is a RESUMED build of the report that crashed overnight; he is waiting on it now). Fold EVERY ${SEC}/rev2_*.html answer/fix into the correct section, apply every proofread fix, then re-run scripts/friday_v7_build.py with system python3 to re-render HTML+PDF, and re-run the publish gate (publish_report.py). The Rev2 must stick to the mission, read clean, be thorough, and leave NO obvious unanswered question. Report the Rev1→Rev2 changelog.`,
    { phase: 'Proofread', label: 'revise:rev2' })
}
const finalx = await agent(
  `FINAL CHECK — the wake-up standard. Re-read the published report end-to-end: confirm MISSION / READS-WELL / THOROUGH / MAKES-SENSE all pass and the proofread's unanswered questions are now closed, and that NO stale 2026-07-24 content survived the resumed stitch. If any MATERIAL gap remains, fix it directly and re-render. Then confirm it is publish-ready and PING the operator via Telegram (\`PYTHONPATH=src ./.venv/bin/python -c "from gazbot7.notify import notify; notify('<msg>', critical=True)"\`) with the /v7/reports link + a 3-line "what SURVIVED" summary + "Rev2 · proofread · N questions closed · RESUMED build".`,
  { phase: 'Proofread', label: 'final-check' })

return { resumed_from: 'Greenfield', census: CENSUS, greenfield_survivor: survivor, built: built, critique: critique, final: finalx }
