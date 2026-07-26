export const meta = {
  name: 'friday-v7-maxdepth',
  description: 'Maximum-depth V7 Friday report — many agents, whole completed week, escalating greenfield hunt (full → top-25 → top-15), adversarial skeptic. Renders light HTML + PDF + Monday playbook.',
  phases: [
    { title: 'Census',     detail: 'freeze the completed-week run census (one snapshot for all)' },
    { title: 'Desks',      detail: 'live desk · shadow+promotion · mid-week musings (parallel)' },
    { title: 'Rehab',      detail: 'live-desk gate & exit REHABILITATION dossier — fix what bled, or show the honest trying (the #1 recurring section)' },
    { title: 'BigRuns',    detail: 'Movement 1 census section + Movement 2 idle-gate lab' },
    { title: 'Greenfield', detail: 'Movement 3 — the escalating hunt, per cluster, full→top25→top15' },
    { title: 'Skeptic',    detail: 'adversarially re-run every survivor from scratch' },
    { title: 'Assemble',   detail: 'stitch → light HTML + PDF + playbook, publish' },
  ],
}

const SCOPE = '/home/alphabot/gazbot7/docs/FRIDAY_V7_REPORT_SCOPE.md'
const SEC = '/home/alphabot/gazbot7/reports/friday_v7/sections'
const STYLE = 'Plain daily English written TO Garrath, money-first, NO maths-professor jargon, LOTS of clear-fact tables. Honest about thin-n / one-week / in-sample. Lead with what SURVIVED. Light-theme HTML FRAGMENT (a stitch-in, not a full page) using classes: h2>span.n, p.lead, div.card>h3, div.callout>div.ct, table with td.num/td.ln, tr.row-hl (green/caught) / tr.row-bad (red/fought), span.tag verdict pills. Every number from a REAL computation you actually ran — never invented.'
const CENSUS_SCHEMA = { type: 'object', required: ['runs', 'sat_out', 'ceiling', 'clusters', 'top25', 'top15'], properties: {
  runs: { type: 'integer' }, sat_out: { type: 'integer' }, ceiling: { type: 'number' },
  clusters: { type: 'object' }, top25: { type: 'array' }, top15: { type: 'array' } } }
const GF_SCHEMA = { type: 'object', required: ['survived', 'name', 'net', 'win_pct', 'graves', 'summary'], properties: {
  survived: { type: 'boolean' }, name: { type: 'string' }, net: { type: 'number' }, win_pct: { type: 'number' },
  big_moves_caught: { type: 'string' }, graves: { type: 'array' }, summary: { type: 'string' } } }
const VERDICT = { type: 'object', required: ['holds', 'why'], properties: { holds: { type: 'boolean' }, why: { type: 'string' } } }
const REHAB_SCHEMA = { type: 'object', required: ['targets'], properties: { targets: { type: 'array', items: {
  type: 'object', required: ['name', 'kind', 'symptom'], properties: {
    name: { type: 'string' }, kind: { type: 'string' }, symptom: { type: 'string' }, this_week_pnl: { type: 'number' } } } } } }

// ── Phase 1 — freeze the census (ONE snapshot every other agent reads) ─────────────────────────
phase('Census')
const census = await agent(
  `The census has ALREADY been frozen out-of-band (run_census.py is a multi-minute tick crunch that must NOT be re-run inside the workflow — re-running it is exactly what timed out and failed the previous attempt). Read the pre-computed summary JSON at ${SEC}/census_summary.json and return its fields (runs, sat_out, ceiling, clusters, top25, top15) EXACTLY as they appear, via StructuredOutput. Also \`ls\` ${SEC}/movement1_census.html to confirm the Movement-1 HTML fragment exists. Do NOT run run_census.py under any circumstances. If ${SEC}/census_summary.json is missing, \`ls ${SEC}\` and return what you find in the summary field — do not fabricate numbers.`,
  { phase: 'Census', schema: CENSUS_SCHEMA })
log(`census frozen: ${census?.runs} runs, ${census?.sat_out} sat out, $${census?.ceiling} ceiling`)

// ── Phase 2 — the desks + musings (parallel, many agents) ──────────────────────────────────────
phase('Desks')
await parallel([
  () => agent(`Read ${SCOPE} Part 1. Write the LIVE DESK section (this week's P&L of the 6-gate tournament, per-gate cards, the whippy trend/chop days, the STOP_UNFILLED self-heals, the direction-router trial, day-type splits). MUST include Friday 07-24 as the flagship live case study: THREE regime flips in one session (down → violent V-reversal up/chop → clean down), the router benching/unbenching the long-faders correctly on each leg, faders knife-caught at the turns (thrust_short −$127 spike-whipsaw on the down-leg, exhaustion_short −$78 on the V-bottom, rgv_short −$345 shorting the chop up-grind unfiltered then +$183 recovered on the down-trend). Pull it from the tournament trades + hour_watch. ${STYLE} Write to ${SEC}/part1_live.html`, { phase: 'Desks', label: 'part1:live' }),
  () => agent(`Read ${SCOPE} Part 2. Write the SHADOW DESK + PROMOTION section. Run scripts/abs_veto_robustness.py and present abs_veto_55s's full battery (the Monday promotion case, TWO-SIDED — both sides earn, promote two-sided not short-only) + the rgv_short REFRAME (regime-dependent, per-side-tune NOT relegate-a-direction — see the reframed Relegation view in Part 2) + the faders keep-with-router-guard + the new thrust_short_raw vs thrust_short_absveto55 shadow A/B. ALSO run \`PYTHONPATH=src:scripts ./.venv/bin/python scripts/two_ratchet_shadow_watch.py\` (NO --ping — the report presents it; the daily cron owns live alerts) and add a "GRIND EXIT SHADOW — two-ratchet runner-clip watch" subsection: the two-ratchet (arm4.0/disarm4.5/b_k1.25, layered on the deployed pure-6.0 chandelier) was REJECTED in backtest (reverser $ inseparable from the runner-retrace zone; only ~$299 cleanly claimable in 2 trades; wk30 delta $0, strip-3 $0) but is SHADOWED to watch for the one thing the range archive can't produce — a RUNNER-CLIP on a real trend day (the 17 rMFE>=4R runners carry ~263% of grind's net). From data/two_ratchet_shadow.json present: cumulative shadow-two-ratchet net vs live pure-6.0 net, runner count, and EVERY runner-clip (date, rMFE_R, live$ vs shadow$, $ given up). Verdict: is the shadow beating pure, and did it clip any real runner this week? If a clip fired, that is the finding — the two-ratchet stays dead. If zero clips over a genuine trend week, that is EVIDENCE FOR reconsidering it. ALSO run \`PYTHONPATH=src:scripts ./.venv/bin/python scripts/partial_shadow_watch.py\` and add a "GRIND EXIT SHADOW — 2R-partial smoothness" subsection from data/partial_shadow.json: the 2R-partial (Lot A scalp-2R + Lot B pure-6.0 chandelier) is a VARIANCE lever, not a mean-raiser (backtest: daily-vol −29%, maxDD −24%, worst-day −34%, for a ~$665/3wk mean give-up concentrated in a couple of runner days). Present baseline (deployed 2-lot chandelier) vs partial: cumulative net + mean give-up, daily std, max drawdown, worst day, green-day/week %, and the two equity curves. Verdict = is the smoother ride worth the mean cost this week — the operator's mean-vs-smoothness CHOICE, NOT pass/fail. Honest caveats. ${STYLE} Write to ${SEC}/part2_shadow.html`, { phase: 'Desks', label: 'part2:shadow' }),
  () => agent(`Read ${SCOPE} Part 2.5. Write the MID-WEEK MUSINGS section, leading with the DIRECTION-ROUTER ARCHITECTURE interrogation: state the objective plainly, show the router's live costs (reaction-lag, sticky-exit, whipsaw), then RESEARCH + BUILD + BACKTEST the more-elegant alternatives (per-gate in-code guard / event-driven / continuous in-tournament gating) against it on the week's data. Verdict with the backtest behind it. THEN — the STANDING WEEKLY ROUTER OPTIMISATION (operator: "this has to be a Friday night study each week — pull it apart, all timings, threshold triggers, make it better"): run \`PYTHONPATH=src ./.venv/bin/python scripts/router_study.py --days 40\` and present, on BOTH the live-managed and full-historical fader sets: (a) IS IT BLOCKING ENOUGH LOSERS — the leakage table (BLOCKED losers vs counter-trend NEAR-MISS losers LEAKED because the trigger was too strict vs genuine CHOP losses the router can't help vs trend-following losses that are a gate/exit problem); (b) the THRESHOLD sweep (ER_TREND × NET_MIN) + the TIMING sweep (step / hold / window / fast_exit) + the joint-best config; (c) a deploy recommendation that RESISTS the grid-edge overfit tell — a MODERATE loosening if the gradient supports it (both sets agreeing), NOT the extreme — with the Saturday-deploy + re-validate-after-a-real-trend-week caveat. This section recurs every week. ${STYLE} Write to ${SEC}/part25_musings.html`, { phase: 'Desks', label: 'part25:musings' }),
])

// ── Phase 2.75 — REHABILITATION (the operator's #1 live-desk section) ───────────────────────────
// "Never bench a gate/exit at face value — if it's not working, HOW can it work. Or at least SHOW
//  the honest trying." Scout this week's rehab targets, run the full rehab discipline on each in
//  parallel (KEEP the winners), then a flagship section that leads with fixes + shows the graves.
phase('Rehab')
const rehabScout = await agent(
  `REHAB SCOUT (operator's standing rule: never bench at face value). From the live tournament trades (data/gazbot7.db), shadow.db, hour_watch logs, and the router switch history, identify EVERY rehabilitation target for the completed week: (a) each live gate that was RED or notably underperformed, (b) any EXIT mechanism worth improving (chandelier / give-back / the two grind-exit shadows), (c) any gate the router benched heavily. Return {targets:[{name, kind:'gate'|'exit', symptom, this_week_pnl}]}, most-bleeding first, MAX 6. If nothing was red, still return the 2 weakest — the rehab runs every week regardless.`,
  { phase: 'Rehab', schema: REHAB_SCHEMA })
const rTargets = (rehabScout?.targets || []).slice(0, 6)
log(`rehab targets: ${rTargets.map((t) => t.name).join(', ') || '(none flagged)'}`)
const rehabDossiers = await parallel((rTargets.length ? rTargets : [{ name: 'weakest_gate', kind: 'gate', symptom: 'weakest live P&L this week' }]).map((t) => () => agent(
  `REHABILITATE "${t.name}" (${t.kind}; symptom: ${t.symptom}; this-week P&L ${t.this_week_pnl}). Run the FULL rehab discipline, tick-honest ($1.50/RT, $2/pt), on this week's capture.db + the archive: (1) NORMALIZE malfunctions — system stops / naked rides / STOP_UNFILLED: what would the loss have been if the stop had worked? (2) corrected-cost RECONSTRUCT the true P&L; (3) ROOT-CAUSE — is the bleed the BASE config, the EXIT, or the SIGNAL? (4) find FILTERS that KEEP the winners while cutting the bleed — a filter that "wins" by dropping the target winners is a FAKE win, REJECT it and say so; (5) ROBUSTNESS — strip-the-best, per-ISO-week, leave-one-day-out, cross-regime; (6) VERDICT: FIXED (exact config) / REGIME-DEPENDENT / SHADOW / TRULY-RETIRE. ★ CRUCIAL — show the TRYING: every attempt INCLUDING the NULLs and graves (the operator wants the honest failures shown, not hidden — "or at least trying to"). Write the working to ${SEC}/rehab_${t.name}.md`,
  { phase: 'Rehab', label: `rehab:${t.name}` })))
log(`rehab dossiers: ${rehabDossiers.filter(Boolean).length}/${rTargets.length || 1}`)
await agent(
  `Write the flagship LIVE-DESK REHABILITATION section — the operator's #1 recurring section: "never bench a gate or exit at face value; if it's not working, HOW can it work — or at least show the honest trying." Read every ${SEC}/rehab_*.md plus the two live grind-exit shadow ledgers (data/two_ratchet_shadow.json = the two-ratchet runner-CLIP watch; data/partial_shadow.json = the 2R-partial smoothness watch). For EACH target, walk it as a story: symptom → malfunction-normalization → root-cause (base/exit/signal) → the fixes/filters TRIED with the KEEP-the-winners test → robustness → a verdict pill (FIXED / REGIME-DEPENDENT / SHADOW / TRULY-RETIRE). LEAD with what got rehabilitated and deployed; then show the honest GRAVES (e.g. the regime-conditional-exit NULL and the two-ratchet clip-mirage — the failures ARE the point, the desk earns trust by showing them). Money-first, clear-fact tables, honest thin-n / one-regime caveats. ${STYLE} Write to ${SEC}/part1_5_rehab.html`,
  { phase: 'Rehab', label: 'rehab:synthesis' })

// ── Phase 3 — Movement 2 idle-gate lab (M1 already written by the census agent) ────────────────
phase('BigRuns')
await agent(
  `Read ${SCOPE} Movement 2. Using the frozen census (${census?.sat_out} sat-out runs), fire ALL SIX live gates (deciders.py) mechanically + ungated at the sat-out runs, in-direction, in the 10min before ignition, with tick-honest exits on this week's capture.db ticks. Per-gate scoreboard: fires-on-sat-out-runs, honest $, why-it-misses (mechanism). Almost certainly an HONEST NULL — prove it. ${STYLE} Write to ${SEC}/movement2_idle_gates.html`,
  { phase: 'BigRuns', label: 'M2:idle-gates' })

// ── Phase 4 — Movement 3: the ESCALATING greenfield hunt (DO NOT GIVE UP) ───────────────────────
phase('Greenfield')
const clusters = ['VACUUM', 'FLOW-LED', 'OPEN-NEWS']
let survivor = null
for (const level of ['full', 'top25', 'top15']) {
  log(`greenfield hunt — level=${level}`)
  const res = await parallel(clusters.map((cl) => () => agent(
    `GREENFIELD HUNT — census level "${level}" (full = all sat-out runs; top25 = the 25 biggest; top15 = the 15 biggest), cluster "${cl}". IGNORE the existing gates. INVENT a brand-new entry signal to catch these runs, with an exact mechanical spec (trigger/direction/entry/stop/exit). BACKTEST it tick-honest on capture.db, net of ~$5/round-trip. Robustness: parameter sweep (does the edge only appear as n collapses = curve-fit tell?), strip-the-3-best-trades, long/short symmetry, and a big-moves-caught X/N against these runs. Do NOT curve-fit a fake winner — if it's a coin-flip that bleeds, it's a GRAVE (report its losing stats + one-line cause of death). The operator wants EVERY grave shown. Narrowing to the biggest runs may reveal a stronger footprint the marginal runs washed out — hunt hard. Return {survived, name, net, win_pct, big_moves_caught, graves[], summary}. Write your working to ${SEC}/gf_${level}_${cl}.md`,
    { phase: 'Greenfield', schema: GF_SCHEMA, label: `gf:${level}:${cl}` })))
  const winners = res.filter(Boolean).filter((r) => r.survived)
  log(`  level=${level}: ${winners.length}/${clusters.length} survived`)
  if (winners.length) { survivor = { level, winners: winners }; break }
}
// synthesize Movement 3 from all graves across every level + any survivor
await agent(
  `Read every ${SEC}/gf_*.md you can find (the greenfield hunts at full / top25 / top15). Write the flagship Movement 3 section as a detective story: the Family A/B split, the oracle proof that the runs are real money (so the problem is the ENTRY), the GRAVES at each narrowing level, and ${survivor ? `the SURVIVOR(s) at the ${survivor.level} level — present the mechanical spec + backtest + robustness, verdict SHADOW (never live)` : 'the honest NULL after the full→top25→top15 hunt all came up empty — name the ONE stone still unturned (L2 book depletion) for next week'}. CRUCIAL: report the size-threshold at which a footprint becomes tradeable, if any (that IS the finding). ${STYLE} Write to ${SEC}/movement3_greenfield.html`,
  { phase: 'Greenfield', label: 'M3:synthesis' })

// ── Phase 5 — adversarial skeptic on every survivor ────────────────────────────────────────────
phase('Skeptic')
if (survivor) {
  const verdicts = await parallel(survivor.winners.map((w) => () => agent(
    `SKEPTIC: adversarially try to REFUTE the greenfield survivor "${w.name}" (${w.summary}) from scratch on the week's data — different window split, strip its best trades, check it isn't one lucky day, re-price with harsher costs. Default to refuted=holds:false if uncertain. Return {holds, why}.`,
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
  `Assemble the full V7 report. Sections live in ${SEC}: part1_live, part1_5_rehab, part2_shadow, part25_musings, movement1_census, movement2_idle_gates, movement3_greenfield. Extend scripts/friday_v7_build.py so it stitches ALL of these (Part 1 live desk, then Part 1.5 the REHABILITATION dossier, then Parts 2 + 2.5, then the 3 movements) into the light-theme shell in that order (the Rehabilitation section is a headline live-desk section — place it right after the live desk, not buried), then run it with system python3 to render the HTML + PDF into src/gazbot7/web_static/. Regenerate reports/friday_v7/plays.json from the actual findings (promote abs_veto_55s TWO-SIDED / rgv per-side-tune NOT relegate-a-direction — SHORT to tight-ext base, LONG router-only / keep+guard faders / rgv-confirm is regime-conditional (re-enable only when router reads chop?) / router-review / the greenfield verdict + any survivor) and build the Monday playbook via /home/alphabot/alphabot2/scripts/friday/build_playbook.py into web_static as monday_<date>.html. Verify all three outputs exist and every section is present, then report the file paths + word count. Do NOT publish a thin report.`,
  { phase: 'Assemble', label: 'assemble+render' })

return { census: census, greenfield_survivor: survivor, built: built }
