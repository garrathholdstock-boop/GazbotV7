export const meta = {
  name: 'friday-v7-finish',
  description: 'Finish the OOM-killed 2026-08-08 Friday report: chop-scalp greenfield, Movement 3, adversarial skeptic on the ODR survivor, a real Day Rider section, re-assemble + PDF + Monday playbook, proofread + Revision 2.',
  phases: [
    { title: 'Greenfield', detail: 'the chop-scalp hunt that died mid-run + Movement 3 synthesis' },
    { title: 'Skeptic',    detail: 'three independent lenses try to REFUTE the ODR survivor' },
    { title: 'DayRider',   detail: 'replace the hand-written stub with a real backtested whiteboard' },
    { title: 'Assemble',   detail: 'stitch every section -> HTML + PDF + Monday playbook (Rev 2)' },
    { title: 'Proofread',  detail: 'adversarial read as the operator -> gap-fill -> final render' },
  ],
}

const V7 = '/home/alphabot/gazbot7'
const SEC = `${V7}/reports/friday_v7/sections`
const SCOPE = `${V7}/docs/FRIDAY_V7_REPORT_SCOPE.md`

// ── Non-negotiable house rules. Every one of these has burned a previous report. ────────────────
const RULES = `
★★ HOUSE RULES — violating any of these invalidates your section. Read /root/CLAUDE.md first.
1. THE FEE IS $1.50 PER ROUND TRIP ($0.75/side). Never $5, never $2, never $1.50/side. Venue truth:
   all 487 closed trades carry fees_usd=1.50. ⚠ THE ORIGINAL GREENFIELD PROMPTS USED ~$5/RT — that is
   WRONG and every greenfield number you inherit must be RE-PRICED at $1.50 before you quote it. Note
   \`FEE, VPP = 5.0, 2.0\` and \`VPP, FEE = 2.0, 1.5\` look identical at a glance and are REVERSED.
2. MFE IS NOT A WIN RATE. "X% of trades reached N R" ignores whether the STOP came first. Compute the
   RACE: first-touch of target vs stop on the forward tick path. This exact error shipped a losing
   config live (capitulation 29% real vs 78% claimed).
3. QUERY HISTORY VIA \`gazbot7.lake.connect()\`, never by ATTACHing capture.db — capture.db holds only
   5 TRADING days and an old harness will silently see just that window. lake gives ticks/quotes/bars/
   book/depth over the full Parquet history.
4. DuckDB's \`/\` IS FLOAT DIVISION. \`(bar_ts/60)*60\` is a NO-OP, not a truncation to the minute — it
   silently reads 5s bars as 1m bars (ER 4x low, ATR 6x low). Use \`//\` or CAST(... AS BIGINT).
5. md_stream is MULTI-SYMBOL. Any bar/tick query MUST filter symbol='MNQ' explicitly.
6. FILTER \`data_quality IS NULL\` on every trade query — excluded rows (the MD_STREAM incident's
   -$255.50) must never reach a reported number.
7. MEMORY: this box has 7.7GB and a prior run was OOM-KILLED. lake.connect() is now capped at 2GB with
   disk spill. Do NOT raise it, do NOT materialise a multi-million-row query into pandas — aggregate
   in SQL and pull back only the result set.
8. NEVER INVENT A NUMBER. Every figure comes from a computation you actually ran. If you could not
   run it, say "not computed" — that is always acceptable and fabrication never is.
9. END EVERY LEAD AS LIVE / SHADOW / PARKED (with its revival condition) / REFUTED (with the test that
   killed it). Thin n is a SHADOW, never a kill. Never the word "grave".
`

const SEGMENT = `BACKTEST DISCIPLINE: the desk is REGIME-CONDITIONAL, so NEVER blanket one fixed config across the whole tape — that averages the regimes a config should be ON with those it should be OFF and washes the edge out. (1) SEGMENT by REGIME — dead-chop / normal-chop / in-between-building / clean-trend / violent-whipsaw, keyed on ATR level + ER + range-break (NOT the clock alone) — AND by TIME-OF-DAY (overnight/pre-open vs US session post-13:30 UTC). (2) Score each config ONLY on its HOME segments and report per-segment n / net / win% / $-per-trade. A blanket cross-tape number with no regime split is a BUG in this report. (3) Every R-target and threshold is an operator GUESS, not a truth: sweep it, prove a parameter PLATEAU (not a spike), strip-the-best-trades, leave-one-day-out, and an OOS leg. (4) Use as much tape as available so each bucket keeps a meaningful n.`

const STYLE = `Plain daily English written TO Garrath, money-first, NO maths-professor jargon, LOTS of clear-fact tables. Honest about thin-n / one-week / in-sample. Lead with what SURVIVED. Light-theme HTML FRAGMENT (a stitch-in, not a full page) using classes: h2>span.n, p.lead, div.card>h3, div.callout>div.ct, table with td.num/td.ln, tr.row-hl (green/caught) / tr.row-bad (red/fought), span.tag verdict pills.`

// The one greenfield candidate that survived level=full before the OOM. Verbatim from the dead run's
// journal so the skeptics attack what was actually claimed, not a paraphrase of it.
const ODR = `THE OPEN RIDER (ODR) — 5-min cadence, direction = sign(last 15-min move), stop 2.0xATR1m, target 2R, 45-min cap, window 13:00-15:00 UTC. CLAIMED: net +$4,169, 48.1% win, 102 trades, on a 17-day tape, priced at the WRONG $5/RT. Claimed to participate in 62/78 OPEN/NEWS-window runs (79%), top-15 biggest 15/15, top-25 23/25. Its author's own finding: "OPEN/NEWS is not an event cluster — it is the clock", and 39% of all quarter-hours in the 13:00-15:00 window qualify as big runs vs 7% outside it. It deliberately uses NO threshold on the 15-min move (thresholding cost money: none +$4,142 vs thr-20 +$2,576 vs thr-50 +$1,366) and NO ER filter (skip-ER>=0.35 +$3,462 vs naked +$4,169).`

// ── Phase 1 — the chop-scalp hunt that was mid-flight when the OOM landed, then Movement 3 ──────
phase('Greenfield')

const chop = await agent(
  `${RULES}\n\nCHOP-DAY SCALP GREENFIELD — the operator's explicit focus, and the agent that was running when the previous build was OOM-killed. Re-run it from scratch.\n\n` +
  `THE PREMISE: the desk's big trend days already carry most of its profit via the trend gates. The WIN available here is to STOP DONATING on the chop days — "untradeable" is only true for the CURRENT gates. Identify this completed week's genuine chop sessions from the tape yourself (ATR + ER + roundtrip, not by reputation), then design and backtest a purpose-built CHOP SCALPER: a mean-reversion/range mechanism with an exact mechanical spec (trigger, direction, entry, stop, exit, cooldown, max-trades-per-session).\n\n` +
  `Be honest about the most likely outcome: the desk's own reversion book bleeds fading GRINDS, and 'low-vol grind = untradeable' is an established finding. If the answer is that chop days should simply be sat out, that is a VALUABLE result — prove it properly and land it as a clean NULL with the numbers, rather than manufacturing a marginal winner.\n\n` +
  `Deliverable: write ${SEC}/gf_chop_scalp.md — spec, per-session backtest table, robustness (parameter plateau, strip-best, leave-one-day-out), and a LIVE/SHADOW/PARKED/REFUTED verdict. ${SEGMENT}`,
  { phase: 'Greenfield', label: 'gf:chop-scalp' })

log('chop-scalp hunt complete — synthesising Movement 3')

// ── Phase 2 — three independent lenses attack ODR, in parallel with the M3 write-up starting ────
phase('Skeptic')

const LENSES = [
  { key: 'duty-cycle', ask:
    `THE DUTY-CYCLE / PLACEBO ATTACK. ODR trades a fixed 2-hour window on a 5-min cadence with NO entry threshold — that is close to "always be positioned in the direction the tape just moved, during the open". So the null hypothesis is not "no edge", it is "the open moves a lot and any always-in strategy books the drift". BUILD THE CONTROLS: (a) random-direction entries on the identical cadence/window/stop/target, 2,000 draws, report where ODR's +$4,169 sits in that distribution; (b) an always-long and an always-short control over the same window; (c) shuffle the sign of the 15-min move while keeping timing identical. If ODR is not clearly outside the placebo distribution, it is REFUTED. Also check: is the net dominated by the sample's net drift? Report the window's cumulative MNQ drift over the same 17 days.` },
  { key: 'robustness', ask:
    `THE ROBUSTNESS ATTACK. 17 days is thin and the thresholds were chosen on the same tape they score on. Run: strip-best-day and strip-best-3-trades; leave-one-day-out on every day; split the tape into halves and score each independently; a true OOS leg on tape the design never saw (go back through the V5 archive via lake.connect for more 13:00-15:00 windows). Check the parameter surface is a PLATEAU not a SPIKE — sweep cadence (3/5/10 min), stop (1.5/2.0/2.5 ATR), target (1.5/2/3 R), cap (30/45/60 min) and window edges (13:00 vs 13:30 start, 15:00 vs 14:45 end). ⚠ The desk's own validated finding is that 13:30-14:45 is where expectancy lives (+$8.93/tr, n=562) — so test explicitly whether ODR is anything MORE than that already-known window effect. If it collapses to "the 13:30-14:45 window is good", say so plainly: that is not a new gate, it is a known fact wearing a new name.` },
  { key: 'execution', ask:
    `THE COST-AND-EXECUTION ATTACK. (a) RE-PRICE at the CORRECT $1.50/RT — the original ran at $5/RT, so the honest number should IMPROVE; state the corrected net and the trade count it rests on. (b) Then make it realistic: add STOP SLIPPAGE (the desk's measured stop-slippage leak is ~$1,200 across the book — derive this gate's share from real fills, do not assume exact-fill) and entry slippage on a market order into open volatility. (c) Verify the exits are a genuine RACE — first-touch of 2R target vs 2.0xATR stop on the forward TICK path, NOT an MFE count, and NOT 5s-bar resolution (5s bars showed an 87% flush-loss error; use 250ms). (d) 102 trades over 2 hours/day for 17 days means it is nearly always in the market during the open — check for OVERLAPPING positions the desk cannot actually hold (the exit-lab paired method swung $5,076 on exactly this), and re-run strictly SEQUENTIALLY, one position at a time, which is what the desk would really do. (e) Check it against the live desk's max_hold_minutes=120 cap and the ASIA/session guards — is it even runnable as a tournament gate?` },
]

const verdicts = await parallel(LENSES.map((L) => () => agent(
  `${RULES}\n\nADVERSARIAL SKEPTIC — your job is to REFUTE, not to appreciate. Default to refuted if uncertain.\n\nTHE CLAIM UNDER ATTACK:\n${ODR}\n\nYOUR LENS — ${L.key}:\n${L.ask}\n\nRe-derive from the raw tape yourself via gazbot7.lake.connect(); do NOT trust the original agent's numbers or re-use its scripts uncritically. Return {holds, why} where holds=false means REFUTED. In \`why\`, give the specific test and the number it produced — a verdict with no number is worthless. Also write your full working to ${SEC}/skeptic_odr_${L.key}.md.`,
  { phase: 'Skeptic', label: `skeptic:${L.key}`,
    schema: { type: 'object', required: ['holds', 'why'], properties: {
      holds: { type: 'boolean' }, why: { type: 'string' },
      corrected_net: { type: 'number' }, key_number: { type: 'string' } } } })))

const live = verdicts.filter(Boolean)
const upheld = live.filter((v) => v.holds).length
log(`skeptic: ${live.length - upheld}/${live.length} lenses REFUTED the ODR survivor`)

// Majority rule, stated explicitly in the section so the operator can see the vote, not just a label.
const odrSurvives = upheld >= 2

await agent(
  `${RULES}\n\nWrite the flagship MOVEMENT 3 — GREENFIELD section as a detective story.\n\n` +
  `SOURCES: read every ${SEC}/gf_*.md (gf_full_VACUUM.md, gf_full_FLOW-LED.md, gf_full_OPEN-NEWS.md, gf_chop_scalp.md) and every ${SEC}/skeptic_odr_*.md.\n\n` +
  `THE STORY: two of the three census clusters produced NO survivor at the full level — VACUUM-BREAK (-$443, 33%) and FLOW-BREAK IGNITION (whose author reported the assignment FAILED because "FLOW-LED" is only 2 of 67 census runs, i.e. the LABEL was the problem, not the tuning). The third, THE OPEN RIDER, survived its author's own ablations — and has now been put through three independent adversarial lenses.\n\n` +
  `★ THE SKEPTIC VOTE, which you must report in full and lead the ODR verdict with:\n${live.map((v, i) => `  - ${LENSES[i].key}: ${v.holds ? 'HOLDS' : 'REFUTED'} — ${v.why}`).join('\n')}\n` +
  `  Majority verdict: ODR ${odrSurvives ? 'SURVIVES the panel (>=2 of 3 upheld) — present it as a SHADOW candidate for incubation, never as a live promotion on 17 in-sample days' : 'is REFUTED by the panel (>=2 of 3 refuted) — land it as REFUTED or PARKED with the exact test that killed it and its revival condition'}.\n\n` +
  `★ BE EXPLICIT ABOUT THE FEE ERROR: every greenfield backtest in this Movement was originally priced at ~$5/RT when the real MNQ fee is $1.50/RT. State which numbers changed once corrected and by how much. A reader must not be able to confuse the two.\n\n` +
  `★ ALSO REQUIRED: the oracle proof that the sat-out runs are real money (so the problem is the ENTRY, not the exit), the per-cluster failure ledger with each lead PARKED (naming its revival condition) or REFUTED (naming the test), and the chop-scalp result. If the honest landing is a NULL, land on the NULL — a well-proven null is the second most valuable thing this report can produce.\n\n` +
  `${STYLE} Write to ${SEC}/movement3_greenfield.html`,
  { phase: 'Skeptic', label: 'M3:synthesis' })

// ── Phase 3 — the Day Rider section, properly. The current file is a hand-written stub. ─────────
phase('DayRider')

await agent(
  `${RULES}\n\nTHE DAY RIDER SECTION — a WHITEBOARD, not a scorecard.\n\n` +
  `⚠ ${SEC}/day_rider.html currently contains a HAND-WRITTEN PLACEHOLDER produced during the OOM recovery; it says so in its own text. REPLACE it entirely with a real, computed section.\n\n` +
  `★ THE OPERATOR'S FRAMING, verbatim and load-bearing: "today was never a good trade. but future ones could be good for 3 hours and then the tape changes. so maybe we have mechanisms to ride them for as long as we want and then take profit. i dont know the answer. it's a new thing... doesn't have to be full day. just one trade that rides the tape with no time limits and a longer vision."\n\n` +
  `SO THE QUESTION IS NOT "does the day-rider work" — it is: HOW DO YOU RIDE A MOVE FOR AS LONG AS IT LASTS AND THEN STOP? The current design answers with a clock (hard flat 20:40Z) plus a trail that only arms at +150pt.\n\n` +
  `WHAT THE SECTION MUST DO:\n` +
  `1. HONEST LEDGER — every day-rider trade to date, tick-honest, isolated from the tournament book via pnl.realized(..., desk="day_rider"). Get the exact realised numbers from the trade record; do NOT trust any summary. Include the 08-06 cross-desk flatten (-$95.50) and say plainly it was a BUG, not a trade. On 08-07 it went SHORT 2 @ 29567.25, detected 14:12Z on efficiency 0.183 / roundtrip 0.638, ran ~250pt offside, the trail NEVER armed (needs +150 in favour), and it rode to the clock — verify all of that against the record.\n` +
  `2. THE EXIT PROBLEM, QUANTIFIED. The prior 25-variant study concluded HOLDING beat every stop width and the armed trail was the only thing that helped (+$2,320) — but that was 31 IN-SAMPLE sessions with no big loser in the sample. RE-DERIVE it now including the losing tail. What does the DISTRIBUTION of a no-stop multi-hour hold actually look like — median vs worst decile? How often does a trade that is -250pt at 15:00 come back? That number decides everything.\n` +
  `3. THE OPERATOR'S ACTUAL IDEA — "ride as long as we want, then take profit". Design and BACKTEST mechanisms that END A RIDE ON EVIDENCE rather than a clock: (a) a trail that arms on R-multiple or ATR rather than a fixed +150pt — a threshold a losing trade can never reach is not a mechanism; (b) regime-change exit — efficiency/roundtrip decaying back below the ENTRY thresholds, or a run-state flip via gazbot7/runstate.py; (c) give-back-from-peak in R; (d) time-in-adverse-excursion. Score each on EVERY session and report days-green + worst-day, not just total.\n` +
  `4. ⚠ ATTACK, DO NOT ASSUME, the prior result "the exit is exit-proof, holding wins". It was derived when the sample had no big loser. It now has one. Does it survive? Check for the survivorship shape.\n` +
  `5. ENTRY QUALITY. It fired at efficiency 0.183, barely over its 0.15 floor, into a tape that reversed. Sweep the floor: does a higher bar cost too many detections? The CME-anchor test gave ZERO detections at 0.15, so the threshold is fragile in BOTH directions. Report detections-vs-edge.\n` +
  `6. SIZING AND ISOLATION. One day-rider trade can swing more than 20 tournament scalps. Recommend whether it should size differently, and confirm the two-book separation is reported everywhere the operator looks.\n\n` +
  `⚠ n IS TINY — one real trade. Do NOT dress a single loss as a refutation, and do NOT dress the in-sample study as validation. The deliverable is a DESIGN DISCUSSION with backtested options and an honest statement of what we cannot yet know. Name what would settle it and how many sessions that needs.\n\n` +
  `${SEGMENT} ${STYLE} Write to ${SEC}/day_rider.html`,
  { phase: 'DayRider', label: 'dayrider:whiteboard' })

// ── Phase 4 — assemble everything into the real deliverable ─────────────────────────────────────
phase('Assemble')

await agent(
  `${RULES}\n\nASSEMBLE THE FULL V7 FRIDAY REPORT for 2026-08-08.\n\n` +
  `Sections in ${SEC}, in this order: part1_live, part1_5_rehab, part2_shadow, part25_musings, part2_6_router_review, day_rider, movement1_census, movement2_idle_gates, movement3_greenfield.\n\n` +
  `⚠ THE PREVIOUS BUILD WAS OOM-KILLED and an orphaned process left behind a PARTIAL artefact titled "Rev 1 — PARTIAL, not proofread", which ends mid-sentence at "That is Movement 3's job." and has NO Movement 3, NO Monday playbook, and a PDF rendered from a DIFFERENT (earlier) version of the HTML than the one on disk. You are replacing all of that.\n\n` +
  `TASKS:\n` +
  `1. Use/extend ${V7}/scripts/friday_v7_build.py so it stitches ALL nine sections. Verify each file exists and is non-empty BEFORE stitching, and FAIL LOUDLY naming any missing one rather than silently emitting a short report — silent truncation is what produced the artefact you are replacing.\n` +
  `2. Render to ${V7}/src/gazbot7/web_static/weekly_2026-08-08.html and .pdf. ★ The HTML and the PDF must be rendered from the SAME content in the same pass — verify their mtimes afterwards and state them.\n` +
  `3. Title it "GAZBOT V7 — Friday report 2026-08-08 (Rev 2)". Remove the "PARTIAL, not proofread" label only once the report genuinely is complete.\n` +
  `4. Build the MONDAY PLAYBOOK -> ${V7}/src/gazbot7/web_static/monday_2026-08-08.html and populate ${V7}/reports/friday_v7/plays.json (it is currently an empty []). Each play: the gate/mechanism, the regime condition that arms it, the exit, the evidence tier (LIVE/SHADOW/PARKED), and the kill criterion. ⚠ NOTHING from this week's greenfield goes in as a LIVE play — 17 in-sample days earns SHADOW at most.\n` +
  `5. Check the wide census table does not overflow the PDF page (a fixed bug — do not regress it).\n` +
  `6. Confirm /api/reports on the local web app (127.0.0.1:8087) lists the report with its pdf and play fields populated.\n\n` +
  `Report back: every file written with its size and mtime, and any section that was missing.`,
  { phase: 'Assemble', label: 'assemble+render' })

// ── Phase 5 — read it as Garrath will, then fix what he would poke at ───────────────────────────
phase('Proofread')

const PROOF_SCHEMA = { type: 'object', required: ['mission_ok', 'reads_ok', 'thorough_ok', 'sensible_ok', 'issues', 'unanswered'], properties: {
  mission_ok: { type: 'boolean' }, reads_ok: { type: 'boolean' }, thorough_ok: { type: 'boolean' }, sensible_ok: { type: 'boolean' },
  issues: { type: 'array', items: { type: 'object', required: ['section', 'problem', 'fix'], properties: {
    section: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' } } } },
  unanswered: { type: 'array', items: { type: 'object', required: ['question', 'why_he_pokes', 'how_to_answer'], properties: {
    question: { type: 'string' }, why_he_pokes: { type: 'string' }, how_to_answer: { type: 'string' } } } } } }

const critique = await agent(
  `${RULES}\n\nADVERSARIAL PROOF-READER — read the just-built report as GARRATH will, and be HARD on it.\n\n` +
  `Read ${V7}/src/gazbot7/web_static/weekly_2026-08-08.html IN FULL, plus ${SCOPE} (the mission).\n\n` +
  `Grade five things: (1) MISSION — does it stick to the V7 regime/shadow-desk mission, LEAD with what SURVIVED the skeptic, use honest baselines, and rehabilitate rather than bench any gate at face value? (2) READS WELL — plain English to Garrath, money-first, no jargon, tables that carry the argument? (3) THOROUGH — every claim backed by a computation actually run? (4) SENSIBLE — do the recommendations follow from the evidence, and is anything recommended that is ALREADY LIVE? (5) HONEST — is thin-n / in-sample / one-week stated everywhere it applies?\n\n` +
  `★ HUNT SPECIFICALLY FOR THE FOUR RECURRING KILLERS: (a) an MFE stat used as a win rate; (b) any number priced at the wrong fee — $5 or $2 or $1.50/side instead of $1.50/RT; (c) a blanket cross-tape backtest with no regime split; (d) a config claimed as tuned via a base target_r that scaleout_slots() actually overwrites.\n\n` +
  `★ ALSO CHECK CONTINUITY, because this report was assembled in two pieces across an OOM: does Movement 3 actually exist and follow on from the sentence that introduces it? Are there dangling forward-references to sections that are not there? Is the Day Rider section the real computed one rather than the hand-written stub?\n\n` +
  `Return the structured verdict. In \`unanswered\`, list the questions Garrath will poke at that the report does not answer — be specific about why he pokes and how to answer it from real data.`,
  { phase: 'Proofread', schema: PROOF_SCHEMA, label: 'proofread:adversarial' })

log(`proofread: mission=${critique?.mission_ok} reads=${critique?.reads_ok} thorough=${critique?.thorough_ok} sensible=${critique?.sensible_ok} · ${(critique?.unanswered || []).length} unanswered · ${(critique?.issues || []).length} issues`)

// Cap the gap-fill fan-out: the point is to close the report, not to start a new research programme.
const gaps = [
  ...((critique?.unanswered) || []).slice(0, 3).map((g, i) => ({ slug: `q${i}`,
    task: `UNANSWERED QUESTION Garrath will poke at: "${g.question}" (he pokes because: ${g.why_he_pokes}). ANSWER it fully from the REAL data — ${g.how_to_answer}. Tick-honest and regime-segmented. ${SEGMENT}` })),
  ...((critique?.issues) || []).slice(0, 3).map((g, i) => ({ slug: `fix${i}`,
    task: `REPORT ISSUE in "${g.section}": ${g.problem}. FIX: ${g.fix}. Recompute or rewrite from real data as needed.` })),
]

if (gaps.length) {
  log(`gap-filling ${gaps.length} items (capped from ${(critique?.unanswered || []).length + (critique?.issues || []).length})`)
  await parallel(gaps.map((g) => () => agent(
    `${RULES}\n\n${g.task}\n\nProduce a tight, REPORT-READY block — plain English to Garrath plus a clear fact-table — that FULLY resolves this. Open with a one-line marker naming which report section it patches or extends. Write it to ${SEC}/rev2_${g.slug}.html`,
    { phase: 'Proofread', label: `rev2:${g.slug}` })))

  await agent(
    `${RULES}\n\nFOLD IN REVISION 2 and produce the FINAL deliverable.\n\n` +
    `Read every ${SEC}/rev2_*.html and merge each into the report section its marker line names — extending or correcting the existing text, never bolting an orphan appendix onto the end.\n\n` +
    `Then re-render BOTH ${V7}/src/gazbot7/web_static/weekly_2026-08-08.html AND .pdf from the merged content in a single pass, plus refresh monday_2026-08-08.html and plays.json if Revision 2 changed any recommendation.\n\n` +
    `FINAL CHECK before you finish, and report on each: (1) the HTML ends with a real conclusion, not mid-sentence; (2) Movement 3 is present and complete; (3) HTML and PDF mtimes match; (4) monday_2026-08-08.html exists and plays.json is non-empty; (5) /api/reports on 127.0.0.1:8087 lists it with pdf + play populated; (6) no section still carries a "PARTIAL" or "not proofread" marker.`,
    { phase: 'Proofread', label: 'rev2:merge+render' })
} else {
  log('proofread found no gaps — Rev 1 stands as final')
}

return {
  chop_scalp: chop ? 'done' : 'failed',
  skeptic_votes: live.map((v, i) => ({ lens: LENSES[i].key, holds: v.holds })),
  odr_survives: odrSurvives,
  proofread: { mission: critique?.mission_ok, reads: critique?.reads_ok, thorough: critique?.thorough_ok, sensible: critique?.sensible_ok },
  gaps_filled: gaps.length,
}
