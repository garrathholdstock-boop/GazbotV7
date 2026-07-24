export const meta = {
  name: 'friday-v7-maxdepth',
  description: 'Maximum-depth V7 Friday report — many agents, whole completed week, escalating greenfield hunt (full → top-25 → top-15), adversarial skeptic. Renders light HTML + PDF + Monday playbook.',
  phases: [
    { title: 'Census',     detail: 'freeze the completed-week run census (one snapshot for all)' },
    { title: 'Desks',      detail: 'live desk · shadow+promotion · mid-week musings (parallel)' },
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

// ── Phase 1 — freeze the census (ONE snapshot every other agent reads) ─────────────────────────
phase('Census')
const census = await agent(
  `Read ${SCOPE}. Run \`cd /home/alphabot/gazbot7 && PYTHONPATH=src .venv/bin/python scripts/run_census.py --days 7 --html ${SEC}/movement1_census.html\` on the COMPLETED week (Friday's session is closed now). This is THE frozen census snapshot every other agent uses — no re-running with a different window. Return: total runs, sat-out count, hindsight ceiling $, the cluster breakdown, and the ordered lists of the TOP-25 and TOP-15 sat-out runs by size (each: time, dir, move-pts). Also confirm the Movement-1 census HTML fragment was written.`,
  { phase: 'Census', schema: CENSUS_SCHEMA })
log(`census frozen: ${census?.runs} runs, ${census?.sat_out} sat out, $${census?.ceiling} ceiling`)

// ── Phase 2 — the desks + musings (parallel, many agents) ──────────────────────────────────────
phase('Desks')
await parallel([
  () => agent(`Read ${SCOPE} Part 1. Write the LIVE DESK section (this week's P&L of the 6-gate tournament, per-gate cards, the whippy trend/chop days, the STOP_UNFILLED self-heals, the direction-router trial, day-type splits). MUST include Friday 07-24 as the flagship live case study: THREE regime flips in one session (down → violent V-reversal up/chop → clean down), the router benching/unbenching the long-faders correctly on each leg, faders knife-caught at the turns (thrust_short −$127 spike-whipsaw on the down-leg, exhaustion_short −$78 on the V-bottom, rgv_short −$345 shorting the chop up-grind unfiltered then +$183 recovered on the down-trend). Pull it from the tournament trades + hour_watch. ${STYLE} Write to ${SEC}/part1_live.html`, { phase: 'Desks', label: 'part1:live' }),
  () => agent(`Read ${SCOPE} Part 2. Write the SHADOW DESK + PROMOTION section. Run scripts/abs_veto_robustness.py and present abs_veto_55s's full battery (the Monday promotion case, TWO-SIDED — both sides earn, promote two-sided not short-only) + the rgv_short REFRAME (regime-dependent, per-side-tune NOT relegate-a-direction — see the reframed Relegation view in Part 2) + the faders keep-with-router-guard + the new thrust_short_raw vs thrust_short_absveto55 shadow A/B. Honest caveats. ${STYLE} Write to ${SEC}/part2_shadow.html`, { phase: 'Desks', label: 'part2:shadow' }),
  () => agent(`Read ${SCOPE} Part 2.5. Write the MID-WEEK MUSINGS section, leading with the DIRECTION-ROUTER ARCHITECTURE interrogation: state the objective plainly, show the router's live costs (reaction-lag, sticky-exit, whipsaw), then RESEARCH + BUILD + BACKTEST the more-elegant alternatives (per-gate in-code guard / event-driven / continuous in-tournament gating) against it on the week's data. Verdict with the backtest behind it. ${STYLE} Write to ${SEC}/part25_musings.html`, { phase: 'Desks', label: 'part25:musings' }),
])

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
  `Assemble the full V7 report. Sections live in ${SEC}: part1_live, part2_shadow, part25_musings, movement1_census, movement2_idle_gates, movement3_greenfield. Extend scripts/friday_v7_build.py so it stitches ALL of these (Parts 1, 2, 2.5, then the 3 movements) into the light-theme shell in that order, then run it with system python3 to render the HTML + PDF into src/gazbot7/web_static/. Regenerate reports/friday_v7/plays.json from the actual findings (promote abs_veto_55s TWO-SIDED / rgv per-side-tune NOT relegate-a-direction — SHORT to tight-ext base, LONG router-only / keep+guard faders / rgv-confirm is regime-conditional (re-enable only when router reads chop?) / router-review / the greenfield verdict + any survivor) and build the Monday playbook via /home/alphabot/alphabot2/scripts/friday/build_playbook.py into web_static as monday_<date>.html. Verify all three outputs exist and every section is present, then report the file paths + word count. Do NOT publish a thin report.`,
  { phase: 'Assemble', label: 'assemble+render' })

return { census: census, greenfield_survivor: survivor, built: built }
