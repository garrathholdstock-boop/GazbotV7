export const meta = {
  name: 'friday-v7-pressuretest',
  description: 'HARD adversarial pressure-test of the finished V7 Friday report — 5 diverse attack lenses, refute-by-default verification of every finding, then fix + re-render + completeness critic.',
  phases: [
    { title: 'Attack',    detail: '5 independent lenses attacking the published report — numbers, claims, contradictions, staleness, actionability' },
    { title: 'Verify',    detail: 'refute-by-default: each alleged defect independently re-checked against source data before it earns a fix' },
    { title: 'Fix',       detail: 'repair every CONFIRMED defect from real recomputation, re-render HTML+PDF' },
    { title: 'Certify',   detail: 'completeness critic — what is still unproven or unasked — then final verdict' },
  ],
}

// Runs AFTER the main build (Rev2) has landed. The built-in Phase-7 proofread grades completeness
// and readability; THIS workflow attacks the SUBSTANCE — does every number reconcile to source
// data, does every verdict follow from its own evidence, and does anything contradict anything else.
// Operator (2026-08-01): "make sure your proof read is thorough and pressure test."
const GB = '/home/alphabot/gazbot7'
const SCOPE = `${GB}/docs/FRIDAY_V7_REPORT_SCOPE.md`
const SEC = `${GB}/reports/friday_v7/sections`
const WEB = `${GB}/src/gazbot7/web_static`
const REPORT = `${WEB}/weekly_2026-07-31.html`

// Ground truth the report MUST reconcile to (from the live tournament DB + the frozen census).
const TRUTH = 'GROUND TRUTH for the completed week Mon 2026-07-27 -> Fri 2026-07-31 (Paris session-day books): desk net +$625 across 206 trades, 39% win (80/206); day nets Mon -226.5 / Tue -54.0 / Wed +638 / Thu +1172 / Fri -905; frozen census 73 runs, 53 sat out, $14,519 hindsight ceiling. Any figure in the report that contradicts these without explicitly explaining the different basis is a DEFECT. Recompute from data/gazbot7.db + reports/friday_v7/sections/census_summary.json — do NOT take the report\'s own numbers on trust.'
const RIGOUR = 'Be SPECIFIC and falsifiable: cite the section, quote the exact sentence/number, state what the data actually says, and show the query/computation you ran. A vague "this could be clearer" is NOT a finding — do not report style opinions, only substantive defects. If you cannot reproduce a defect from source data, do not report it.'

const FINDINGS = { type: 'object', required: ['findings'], properties: { findings: { type: 'array', items: {
  type: 'object', required: ['section', 'quote', 'defect', 'evidence', 'severity', 'fix'], properties: {
    section: { type: 'string' }, quote: { type: 'string' }, defect: { type: 'string' },
    evidence: { type: 'string', description: 'what the source data actually shows, + the computation run' },
    severity: { type: 'string', enum: ['critical', 'major', 'minor'] }, fix: { type: 'string' } } } } } }
const VERDICT = { type: 'object', required: ['confirmed', 'why'], properties: {
  confirmed: { type: 'boolean' }, why: { type: 'string' }, corrected_fix: { type: 'string' } } }
const CERT = { type: 'object', required: ['publish_ready', 'residual_gaps', 'summary'], properties: {
  publish_ready: { type: 'boolean' }, residual_gaps: { type: 'array' }, summary: { type: 'string' } } }

// ── Phase 1 — five DIVERSE attack lenses (diversity beats redundancy) ──────────────────────────
phase('Attack')
const LENSES = [
  { key: 'numbers', prompt: `LENS 1 — NUMBERS RECONCILIATION. Read ${REPORT} IN FULL. Take EVERY headline dollar figure, count, win-rate and per-gate P&L in it and INDEPENDENTLY RECOMPUTE it from source (data/gazbot7.db tournament trades, shadow.db, data/capture.db, ${SEC}/census_summary.json) using DuckDB+pandas (never raw sqlite row-loops). Check: does the week total reconcile to the sum of its days? do the per-gate nets sum to the desk net? do Lot-A/Lot-B splits sum to their gate? is every win-rate consistent with its own N? are the shadow figures on the honest real_pnl basis? Flag EVERY figure that does not reconcile, and every figure you cannot trace to a computation at all. ${TRUTH} ${RIGOUR}` },
  { key: 'claims', prompt: `LENS 2 — CLAIM vs EVIDENCE. Read ${REPORT} IN FULL. For EVERY verdict, recommendation and causal claim ("X works", "the router earned its keep", "grind is a trend-day bet", any promote/relegate/deploy call), ask: does the number actually cited SUPPORT that claim, at that strength? Hunt specifically for — a thin-n result stated as established fact (n<30 presented without the caveat); a $ figure quoted with no baseline to compare against; a causal story asserted over what is only a correlation; a shadow number used as proof without its live cross-check; a promotion/relegation call made without the robustness battery behind it; a conclusion that survives only because one outlier day is in the sample. ${TRUTH} ${RIGOUR}` },
  { key: 'contradictions', prompt: `LENS 3 — INTERNAL CONTRADICTIONS. Read ${REPORT} IN FULL, holding all sections in mind at once. Find places where two parts of the report disagree: a gate called a winner in one section and a bleeder in another; live-vs-shadow numbers for the same gate that do not reconcile (and are not explicitly reconciled in the text); the rehab section's verdict contradicting the shadow section's ranking; the router review's bench-grading contradicting the live-desk narrative of the same episode; Monday plays that contradict a verdict the body reached; the same event described with different numbers in two places. Quote BOTH sides of every contradiction. ${TRUTH} ${RIGOUR}` },
  { key: 'staleness', prompt: `LENS 4 — STALE / FABRICATED CONTENT. This report was built by a RESUMED workflow after the original crashed, so prior-week content leaking through is a live risk. Read ${REPORT} IN FULL and hunt for: any finding, number, gate verdict, grave or Monday play that actually belongs to the 2026-07-24 report or earlier (compare against ${WEB}/v7_big_runs_2026-07-24.html and reports/friday_v7/plays.json's history); any example lifted from ${SCOPE}'s "FLAGGED THIS WEEK" section rather than discovered from THIS week's data; any date outside Mon 07-27 - Fri 07-31 presented as this week; any placeholder, "TODO", truncated table, empty section, or number that looks invented rather than computed (spot-check the suspicious ones against source data). ${TRUTH} ${RIGOUR}` },
  { key: 'actionability', prompt: `LENS 5 — SO WHAT DO I DO MONDAY. Read ${REPORT} IN FULL plus ${WEB}/monday_2026-07-31.html and reports/friday_v7/plays.json. Garrath's test is "what do I actually DO Monday". Check: does EVERY Monday play trace to a specific verdict the report body actually reached (name the section for each)? Is any play carried over from a prior week rather than derived from this week? Is any major finding in the body NOT converted into an action? Are the actions concrete enough to execute (exact gate, exact switch, exact config, exact threshold) rather than "consider tuning X"? Is the exit-ladder left as a guess where the report promised PROVEN R's — and is the BIG-TREND rung still unproven? Flag every gap between what the report LEARNED and what it TELLS HIM TO DO. ${TRUTH} ${RIGOUR}` },
]

// pipeline: each lens's findings go straight to verification as soon as that lens finishes.
const attacked = await pipeline(
  LENSES,
  (l) => agent(l.prompt, { label: `attack:${l.key}`, phase: 'Attack', schema: FINDINGS }),
  (res, l) => parallel(((res && res.findings) || []).map((f) => () =>
    agent(`ADVERSARIAL VERIFIER — default to CONFIRMED=FALSE. Another agent alleges a defect in the V7 Friday report. Your job is to REFUTE it; only confirm if you can independently reproduce it from source data.\n\nSECTION: ${f.section}\nQUOTED: "${f.quote}"\nALLEGED DEFECT: ${f.defect}\nTHEIR EVIDENCE: ${f.evidence}\n\nGo to the SOURCE (data/gazbot7.db, shadow.db, capture.db, ${SEC}/*, ${REPORT}) and check it yourself. Refute if: the quote is taken out of context, the report DOES caveat/reconcile it elsewhere, the alleged "correct" number is itself wrong, the figures use a different but legitimate basis (e.g. Paris session-day vs UTC, gross vs net of fees, live vs shadow), or the complaint is style not substance. Confirm ONLY a real defect a reader would be misled by. If confirmed but their proposed fix is wrong, give corrected_fix. ${TRUTH}`,
      { label: `verify:${l.key}:${(f.section || '').slice(0, 22)}`, phase: 'Verify', schema: VERDICT })
      .then((v) => ({ ...f, verdict: v })))),
)

const confirmed = attacked.flat().filter(Boolean).filter((f) => f.verdict && f.verdict.confirmed)
const rejected = attacked.flat().filter(Boolean).length - confirmed.length
log(`pressure test: ${confirmed.length} defects CONFIRMED, ${rejected} refuted on independent re-check`)
const bySev = (s) => confirmed.filter((f) => f.severity === s).length
log(`  critical=${bySev('critical')} major=${bySev('major')} minor=${bySev('minor')}`)

// ── Phase 2 — repair every CONFIRMED defect, then re-render once ────────────────────────────────
phase('Fix')
if (confirmed.length) {
  await parallel(confirmed.map((f, i) => () => agent(
    `FIX a CONFIRMED defect in the V7 Friday report.\n\nSECTION: ${f.section}\nQUOTED: "${f.quote}"\nDEFECT: ${f.defect}\nEVIDENCE: ${f.evidence}\nFIX: ${f.verdict.corrected_fix || f.fix}\n\nEdit the SOURCE FRAGMENT in ${SEC} (part1_live / part1_5_rehab / part2_shadow / part25_musings / part2_6_router_review / movement1_census / movement2_idle_gates / movement3_greenfield) — NOT the built HTML, which gets re-rendered from these. Recompute anything numeric from real data; never hand-wave a number. Keep the house style: plain English to Garrath, money-first, clear-fact tables, honest caveats. Change ONLY what this defect requires — do not rewrite neighbouring content, and do not touch fragments this defect does not concern (other agents are editing those in parallel). Report exactly what you changed.`,
    { label: `fix:${f.severity}:${(f.section || '').slice(0, 22)}`, phase: 'Fix' })))
  await agent(
    `Re-render the V7 Friday report after the pressure-test fixes: re-run scripts/friday_v7_build.py with system python3 to rebuild ${WEB}/weekly_2026-07-31.html + .pdf from the corrected fragments in ${SEC}, re-run the publish gate (publish_report.py), and rebuild the Monday playbook if any play changed. Confirm all three outputs exist, are newer than the fixes, and that the fixes are actually visible in the rendered HTML (spot-check 3 of them by grepping the rendered file). Report word count + page count (pdfinfo).`,
    { label: 'rerender', phase: 'Fix' })
} else {
  log('no confirmed defects — skipping fix/re-render')
}

// ── Phase 3 — completeness critic + final certification ────────────────────────────────────────
phase('Certify')
const cert = await agent(
  `FINAL CERTIFICATION — the completeness critic. Re-read the published ${REPORT} end-to-end (post-fix) plus ${SCOPE}. This report survived a 5-lens adversarial pressure test in which ${confirmed.length} defect(s) were confirmed and repaired and ${rejected} alleged defects were refuted. Now ask the question the attack lenses could NOT: WHAT IS STILL MISSING? Specifically — a claim nobody verified because no lens happened to cover it; an analysis the scope doc promises that the report quietly did not deliver; a section that is present but THIN relative to its importance (esp. the exit-ladder BIG-TREND rung, the greenfield null, the router net-value); a question the data could have answered this week but nobody asked. Be honest — "publish_ready: true" means you would put your name on this going to the operator, not merely that it has no known errors. List every residual gap with its section, and give a 3-line "what SURVIVED this week" summary suitable for the Telegram ping. ${TRUTH}`,
  { label: 'certify', phase: 'Certify', schema: CERT })
log(`certification: publish_ready=${cert?.publish_ready} · ${(cert?.residual_gaps || []).length} residual gap(s)`)

return {
  confirmed_defects: confirmed.length, refuted: rejected,
  by_severity: { critical: bySev('critical'), major: bySev('major'), minor: bySev('minor') },
  defects: confirmed.map((f) => ({ section: f.section, severity: f.severity, defect: f.defect })),
  certification: cert,
}
