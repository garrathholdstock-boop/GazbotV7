#!/usr/bin/env python3
"""FRIDAY REPORT — the PHASE MANIFEST (the DAG the tick driver walks).

Each phase is ONE short, self-contained headless-claude turn that writes ONE artifact.
No Workflow tool, no background tasks: the turn does its work inline and exits, which is
exactly what `claude -p` is good at. That is the whole point of the redesign — the old
driver held ONE session open for ~7h and every failure to date was "the driver went away",
never a bad analysis. Short idempotent units are why gazbot7-router-tick has never missed.

Contract for every phase:
  key       — stable id, also the state-file key
  artifact  — the file whose existence-and-freshness MEANS the phase is done
  deps      — phase keys that must be `done` first
  timeout_s — hard cap for the one claude turn
  prompt    — the turn. MUST end by writing `artifact`.

Adding/removing a phase is a data edit here; the driver needs no changes.
"""

GB = "/home/alphabot/gazbot7"
SEC = f"{GB}/reports/friday_v7/sections"
WEB = f"{GB}/src/gazbot7/web_static"
SCOPE = f"{GB}/docs/FRIDAY_V7_REPORT_SCOPE.md"

STYLE = (
    "Plain daily English written TO Garrath, money-first, NO maths-professor jargon, LOTS of clear-fact "
    "tables. Honest about thin-n / one-week / in-sample. Lead with what SURVIVED. Light-theme HTML FRAGMENT "
    "(a stitch-in, not a full page) using classes: h2>span.n, p.lead, div.card>h3, div.callout>div.ct, table "
    "with td.num/td.ln, tr.row-hl (green/caught) / tr.row-bad (red/fought), span.tag verdict pills. Every "
    "number from a REAL computation you actually ran — never invented."
)
SEGMENT = (
    "BACKTEST DISCIPLINE (operator, 2026-07-31 — governs EVERY backtest/sweep): the desk is REGIME-CONDITIONAL, "
    "so NEVER blanket one fixed gate/exit config across the whole tape — that averages the regimes a config should "
    "be ON with those it should be OFF/different and washes the edge out. (1) SEGMENT the tape by REGIME — "
    "dead-chop / normal-chop / in-between-building / clean-trend / violent-whipsaw, keyed on ATR level + ER + "
    "range-break (NOT the clock alone) — AND by TIME-OF-DAY (overnight/pre-open vs US session post-13:30 UTC). "
    "(2) Score each config ONLY on its HOME segments and report per-segment n / net / win% / $-per-trade — evaluate "
    "the POLICY (regime->config), never a static config sprayed across all tape; a blanket cross-tape number with no "
    "regime split is a BUG. (3) Every R-target and threshold is an operator GUESS, NOT a truth: SWEEP it per regime "
    "and PROVE the robust optimum (parameter plateau, strip-the-best-trades, leave-one-day-out, OOS leg), then report "
    "PROVEN Rs vs the guess. (4) Use as much tape as available so each regime bucket keeps a meaningful n."
)
# ★ Win-rate is NOT a kill criterion (operator, 2026-08-01): the live desk ran 39% win for the week and
#   +$625; Wed/Thu were ~40% and very profitable because the winners were big. Judge EXPECTANCY.
JUDGE = (
    "★ JUDGING RULE (operator, 2026-08-01): WIN-RATE IS NOT A KILL CRITERION. The live desk booked +$625 this week "
    "at a 39% win rate, and its two most profitable days ran ~40% — the winners were simply big. Judge every "
    "candidate on EXPECTANCY ($/trade net of costs) and ROBUSTNESS (placebo//shuffle test, strip-the-best-trades, "
    "leave-one-day-out, OOS leg, parameter plateau vs step), NEVER on win% alone. If you kill something, the cause "
    "of death must be one of those robustness tests, and you must SAY WHICH."
)
GRAVES = (
    "★ SHOW EVERYTHING (operator, standing rule): report EVERY attempt including the NULLs and the graves, each by "
    "name with its stats and a one-line cause of death. The honest failures ARE the deliverable — never quietly drop "
    "a killed candidate. A verdict with no visible working is worthless to him."
)
PRE = f"You are writing one section of the GAZBOT V7 Friday report. Repo {GB} (cd there; venv .venv). Read {SCOPE} for the mission. "

# The census is frozen out-of-band by the driver before any phase runs (multi-minute tick crunch;
# running it inside a schema'd agent is what timed out the very first attempt back on 07-24).
PHASES = [
    dict(key="part1_live", artifact=f"{SEC}/part1_live.html", deps=[], timeout_s=2700, prompt=PRE +
         f"Read {SCOPE} Part 1. Write the LIVE DESK section (this week's P&L of the 6-gate tournament, per-gate cards, "
         f"the whippy trend/chop days, the STOP_UNFILLED self-heals, the direction-router trial, day-type splits). "
         f"DISCOVER this week's story FRESH from the tournament trades + hour_watch + the router switch/trial logs — "
         f"assume NOTHING from any prior week (any week-specific episode named in the scope doc is a STALE prior-week "
         f"example, not this week's finding). Find the most instructive live session(s) of THIS week and write them up "
         f"as the flagship case study, every number computed from the data. {JUDGE} {STYLE} Write to {SEC}/part1_live.html"),

    dict(key="part2_shadow", artifact=f"{SEC}/part2_shadow.html", deps=[], timeout_s=3600, prompt=PRE +
         f"Read {SCOPE} Part 2. Write the SHADOW DESK + PROMOTION section, DISCOVERED FRESH from THIS week's data. Rank "
         f"the shadow board by honest real_pnl (all-time + this week) and let the promotion candidate(s) EMERGE from that "
         f"ranking. Run scripts/abs_veto_robustness.py and present its full battery (headline, per-day spread, regime split, "
         f"walk-forward halves, head-to-head vs un-vetoed thrust, BOTH sides) with honest caveats. Present Relegation using "
         f"the standing two-sided-gate PRINCIPLE (tune the SIDE, never relegate a DIRECTION) from fresh per-side numbers. "
         f"ALSO run `PYTHONPATH=src:scripts ./.venv/bin/python scripts/two_ratchet_shadow_watch.py` (NO --ping) and add a "
         f"two-ratchet runner-clip subsection from data/two_ratchet_shadow.json. ALSO run scripts/partial_shadow_watch.py "
         f"and add a 2R-partial smoothness subsection from data/partial_shadow.json (mean-vs-smoothness CHOICE, not pass/fail). "
         f"ALSO the REGIME-FLEX EXIT LAB: grade the LIVE exhaustion_short fade-scalp trial on ACTUAL fills, and PROVE the "
         f"operator's exit ladder per gate x rung (BIG-TREND ER>=0.50 / MED 0.30-0.50 / CHOP / STAY-OUT) by extending "
         f"scripts/adaptive_exit_bt.py over a grid of Lot-A x Lot-B R-combos AND chandelier. ★ The BIG-TREND rung has "
         f"historically been tiny-n — you MUST extend the window (full V5 archive + every available trend day) to finally "
         f"prove or refute it. DELIVERABLE: the per-rung R table = the deployable data/exit_overrides.json policy. "
         f"{SEGMENT} {JUDGE} {STYLE} Write to {SEC}/part2_shadow.html"),

    dict(key="part25_musings", artifact=f"{SEC}/part25_musings.html", deps=[], timeout_s=3600, prompt=PRE +
         f"Read {SCOPE} Part 2.5. ★ DE-DUP: the full router operation review is its OWN section (part2_6) — do NOT "
         f"duplicate it here. Make THIS section purely the fresh mid-week LEADS + their verdicts, discovered from the "
         f"router trial log, nightly rollups, hour_watch and the week's data. Treat the scope doc's '★ FLAGGED THIS WEEK' "
         f"items as STALE prior-week examples of the KIND of lead to test, never as this week's findings. Include the "
         f"standing GRIND lead: which enable-mechanism best captures grind's trend-day upside while killing its chop-churn "
         f"— (a) trend-day-only, (b) its own entry trend-confirmation/veto, or (c) the current ER-0.35 floor? ⚠ Judge on "
         f"LIVE/MANAGED grind, NOT the unmanaged grind_fast shadow, which is misleading. {SEGMENT} {JUDGE} {STYLE} "
         f"Write to {SEC}/part25_musings.html"),

    dict(key="part2_6_router", artifact=f"{SEC}/part2_6_router_review.html", deps=[], timeout_s=3600, prompt=PRE +
         f"Write the ROUTER OPERATION REVIEW — a BIG comprehensive weekly review of the Claude-run router (the desk's #1 "
         f"lever), its own headline section. Money-first, LOTS of tables. Cover ALL of: (1) THE WEEK'S DECISIONS + SCOREBOARD "
         f"from data/router_trial_log.txt + data/router_badcall_ledger.md — per day what it did, switch-change COUNT (thrash "
         f"check), scoreboard trend. (2) WHAT WORKS vs WHAT DOESN'T — which calls PAID vs ERRED, quantified in $. (3) NET "
         f"ROUTER VALUE — roll up every data/router_nightly/*.json + data/selector_nightly/*.json: blocked-losses-SAVED minus "
         f"winners-MISSED by regime; is it net-positive, over-benching, and WHERE leaking. (4) THRESHOLD TUNING — run "
         f"`PYTHONPATH=src ./.venv/bin/python scripts/router_study.py --days 40`: ER_TREND x NET_MIN sweep + timing sweep on "
         f"BOTH live-managed and full-historical sets; MODERATE anti-overfit recommendation, Saturday-deploy caveat. (5) THE "
         f"UNTRADEABLE-DAY METER REVIEW (src/gazbot7/untradeable.py) — score each day vs its ACTUAL P&L; which of the 3 meters "
         f"actually DISCRIMINATED; does the 65 STAY-OUT cutoff want tuning. (6) BENCH-DECISION REVIEW — grade the week's actual "
         f"benches. (7) DURABLE ROUTER + ARCHITECTURE — did the 5-min systemd tick manage correctly (no thrash); QUANTIFY the "
         f"actuation-lag $ cost this week. (8) VERDICT + SATURDAY RECOMMENDATIONS, each with its evidence. {SEGMENT} {JUDGE} "
         f"{STYLE} Write to {SEC}/part2_6_router_review.html"),

    dict(key="movement2_idle", artifact=f"{SEC}/movement2_idle_gates.html", deps=[], timeout_s=3600, prompt=PRE +
         f"Read {SCOPE} Movement 2. Using the frozen census at {SEC}/census_summary.json (do NOT re-run run_census.py — it is "
         f"a multi-minute tick crunch), fire ALL SIX live gates (deciders.py) mechanically + ungated at the sat-out runs, "
         f"in-direction, in the 10min before ignition, with tick-honest exits on this week's capture.db ticks. Per-gate "
         f"scoreboard: fires-on-sat-out-runs, honest $, why-it-misses (mechanism). Almost certainly an HONEST NULL — prove it. "
         f"{SEGMENT} {JUDGE} {GRAVES} {STYLE} Write to {SEC}/movement2_idle_gates.html"),

    dict(key="rehab", artifact=f"{SEC}/part1_5_rehab.html", deps=[], timeout_s=5400, prompt=PRE +
         f"The LIVE-DESK REHABILITATION dossier — the operator's #1 recurring section: 'never bench a gate or exit at face "
         f"value; if it's not working, HOW can it work — or at least show the honest trying.' STEP 1: from the live tournament "
         f"trades (data/gazbot7.db), shadow.db, hour_watch logs and the router switch history, identify EVERY rehab target for "
         f"the completed week (each live gate that was RED or underperformed; any EXIT mechanism worth improving; any gate the "
         f"router benched heavily) — most-bleeding first, MAX 6; if nothing was red still take the 2 weakest. STEP 2: for EACH "
         f"target run the FULL rehab discipline, tick-honest ($1.50/RT, $2/pt): (a) NORMALIZE malfunctions (system stops / naked "
         f"rides / STOP_UNFILLED — what would the loss have been if the stop had worked); (b) corrected-cost RECONSTRUCT the true "
         f"P&L; (c) ROOT-CAUSE — is the bleed the BASE config, the EXIT, or the SIGNAL; (d) find FILTERS that KEEP the winners "
         f"while cutting the bleed — a filter that 'wins' by dropping the target winners is a FAKE win, REJECT it and say so; "
         f"(e) ROBUSTNESS — strip-the-best, per-ISO-week, leave-one-day-out, cross-regime; (f) VERDICT: FIXED (exact config) / "
         f"REGIME-DEPENDENT / SHADOW / TRULY-RETIRE. Write each target's working to {SEC}/rehab_<name>.md — ★ sanitise the "
         f"filename: no '/' characters (a '/' in a target name silently creates a DIRECTORY and mangles the dossier). STEP 3: "
         f"write the flagship section — each target as a story (symptom -> normalization -> root-cause -> fixes TRIED with the "
         f"keep-the-winners test -> robustness -> verdict pill), leading with what got rehabilitated, then the honest GRAVES. "
         f"{SEGMENT} {JUDGE} {GRAVES} {STYLE} Write to {SEC}/part1_5_rehab.html"),

    # ── Greenfield: one phase per cluster, independent, so a wedge in one cannot cost the others ──
    *[dict(key=f"gf_{cl}", artifact=f"{SEC}/gf_full_{cl}.md", deps=[], timeout_s=5400, prompt=PRE +
        f"GREENFIELD HUNT — cluster '{cl}'. Read the frozen census {SEC}/census_summary.json (do NOT re-run run_census.py). "
        f"IGNORE the existing gates. INVENT a brand-new entry signal to catch these sat-out runs, with an exact mechanical spec "
        f"(trigger/direction/entry/stop/exit). BACKTEST it tick-honest on capture.db, net of ~$5/round-trip. ESCALATE if it "
        f"fails: hunt the full sat-out set, then the top-25 biggest runs, then the top-15 — narrowing may reveal a footprint the "
        f"marginal runs washed out. Report the size-threshold at which a footprint becomes tradeable, if any (that IS the "
        f"finding). ROBUSTNESS: placebo/shuffle test (shift the signal series, keep every other rule — if a FAKE signal books "
        f"most of the money, the real one is not the edge), parameter sweep (edge only as n collapses = curve-fit tell), "
        f"strip-the-3-best, long/short symmetry, leave-one-day-out, OOS leg, and big-moves-caught X/N. ★ ALSO interrogate the "
        f"CLUSTER LABEL itself before trusting it — check its base rate on all bars; a label that is true on most of the tape is "
        f"not a footprint, it is noise, and that finding outranks any signal you build on top of it. {JUDGE} {GRAVES} "
        f"{SEGMENT} Write your full working to {SEC}/gf_full_{cl}.md, ending with an explicit VERDICT line stating "
        f"whether it survived and, if not, WHICH robustness test killed it.")
      for cl in ("VACUUM", "FLOW-LED", "OPEN-NEWS")],

    dict(key="gf_chopscalp", artifact=f"{SEC}/gf_chopscalp.md", deps=[], timeout_s=5400, prompt=PRE +
         f"CHOP-DAY SCALP GREENFIELD — operator's explicit focus. The week's chop days BLED or broke even with the CURRENT "
         f"gates — but 'untradeable' is only true for THOSE gates. The trend days already carry most of the week's profit, so "
         f"the WIN here is to stop DONATING on chop days: a purpose-built scalp clearing +$200-300 on a chop day instead of "
         f"sitting out is a big weekly swing. Build a CHOP-TURN SCALP specialist: catch the oscillation TURNS and scalp TINY "
         f"(bank at ~0.5R/1R — sweep the exact R). ★ LEAD WITH L2 ORDER FLOW: the separator MUST be the book, not price — same "
         f"lineage as exhaustion_short, one of our best gates, which was BUILT from L2 footprints (footprint.py / "
         f"exhaustion_signal). A naive price-only turn-fade is a known COIN-FLIP that overtrades and bleeds fees. At the price "
         f"extreme require the FAR SIDE to be ABSORBING/DEPLETING (capture.db book table / depth.db, 10-deep) + footprint "
         f"aggressor-delta, PLUS a VWAP-FLAT 'is-it-actually-ranging' filter (never fade a sloping VWAP). Be FAR more selective "
         f"— a few high-quality turns/day, not hundreds; trade count is a fee tax. BACKTEST tick-honest on this week's chop days. "
         f"ROBUSTNESS: must hold on ALL the chop days (not one), placebo/shuffle, strip-the-best, param sweep, and check it does "
         f"not bleed the trend days. Report per-trade edge ($ and win%), projected chop-day P&L vs the +$200-300 bar. {JUDGE} "
         f"{GRAVES} {SEGMENT} Write to {SEC}/gf_chopscalp.md, ending with an explicit VERDICT line stating whether it "
         f"survived and, if not, WHICH robustness test killed it."),

    # ★ RUN CHARTS (operator 2026-08-01: "I love seeing the chart and when we jumped and when we
    #   exited"). Mechanical — charts every session day of the week + the biggest census runs, so it
    #   needs no narrative input and cannot be blocked by another phase.
    dict(key="run_charts", artifact=f"{SEC}/run_charts.html", deps=[], timeout_s=1800, prompt=PRE +
         f"Generate this week's RUN CHARTS with `scripts/friday/run_charts.py` (already built and validated — do NOT "
         f"rewrite its rendering or change its colours; the win/loss pair is CVD-validated). Build a spec JSON covering "
         f"(a) EACH session day of the completed week over the US session 13:00-21:00 UTC, titled with the day and its "
         f"actual net P&L and trade count, and (b) the 3-5 BIGGEST runs from {SEC}/census_summary.json, each windowed "
         f"~30min either side of the run so the move fills the chart, titled with the move size and whether the desk "
         f"CAUGHT / FOUGHT / SAT OUT. Give each chart a one-line `note` saying what it shows in plain English (e.g. "
         f"'the desk stopped trading after 16:00 — the router benched the book into the roll-over'). Then run: "
         f"`.venv/bin/python scripts/friday/run_charts.py --spec <spec>.json --fragment {SEC}/run_charts.html`. Verify "
         f"the fragment contains one <svg> per spec entry and that no chart came back as a 'no tick data' callout "
         f"(if one did, widen its window or fix the timestamps). These are inline self-contained SVG — never an external "
         f"image or JS library."),

    dict(key="movement3", artifact=f"{SEC}/movement3_greenfield.html", deps=["gf_VACUUM", "gf_FLOW-LED", "gf_OPEN-NEWS", "gf_chopscalp"],
         timeout_s=3600, prompt=PRE +
         f"Read EVERY {SEC}/gf_*.md from this week's hunts. ★ If {SEC}/movement3_greenfield.html already exists it is a STALE "
         f"PRIOR-WEEK file — OVERWRITE it completely and carry over none of its findings. Write the flagship Movement 3 section "
         f"as a detective story: the Family A/B split, the oracle proof that the runs are real money (so the problem is the "
         f"ENTRY), the GRAVES at each narrowing level, and either the SURVIVOR(s) with spec + backtest + robustness, or the "
         f"honest NULL naming the ONE stone still unturned for next week. Report the size-threshold at which a footprint becomes "
         f"tradeable, if any. ★ ALSO a headline CHOP-DAY SCALP LAB "
         f"subsection from gf_chopscalp.md: can we stop DONATING on chop days? {JUDGE} {GRAVES} {SEGMENT} {STYLE} "
         f"Write to {SEC}/movement3_greenfield.html"),

    dict(key="assemble", artifact=f"{WEB}/weekly_{{WEEK}}.html",
         deps=["part1_live", "part2_shadow", "part25_musings", "part2_6_router", "movement2_idle", "rehab", "movement3", "run_charts"],
         timeout_s=3600, prompt=PRE +
         f"Assemble the full V7 report for the completed week (outputs weekly_{{WEEK}}.html/.pdf + monday_{{WEEK}}.html). "
         f"Sections live in {SEC}: part1_live, part1_5_rehab, part2_shadow, part25_musings, part2_6_router_review, "
         f"movement1_census, movement2_idle_gates, movement3_greenfield, run_charts. Extend scripts/friday_v7_build.py so it stitches ALL of "
         f"them into the light-theme shell in that order (Rehabilitation is a headline live-desk section — right after the live "
         f"desk, not buried; the RUN CHARTS fragment goes INSIDE Part 1 with the case-study days, not in an appendix), then run it with system python3 to render HTML + PDF into {WEB}/. ★ A rehab dossier filename may "
         f"contain a '/' that became a DIRECTORY — make any rehab_*.md glob tolerant of that rather than choking. Regenerate "
         f"reports/friday_v7/plays.json from THIS week's findings only — each play must trace to a verdict a section actually "
         f"reached; the file on disk is a STALE prior-week one, overwrite it. Then build the Monday playbook via "
         f"/home/alphabot/alphabot2/scripts/friday/build_playbook.py as monday_{{WEEK}}.html. Verify all three outputs exist and "
         f"every section is present, then report file paths + word count + pdfinfo page count. Do NOT publish a thin report. "
         f"★ If a section fragment is MISSING because its phase failed, still assemble — insert a visible honest placeholder "
         f"naming the missing section rather than silently omitting it, and say so in your report."),

    dict(key="proofread", artifact=f"{SEC}/proofread.json", deps=["assemble"], timeout_s=3600, prompt=PRE +
         f"ADVERSARIAL PROOF-READER — read the just-built report as GARRATH will, and be HARD on it. Read the newest "
         f"{WEB}/weekly_*.html IN FULL, plus {SCOPE}. Grade: (1) MISSION — sticks to the V7 shadow-desk/regime mission, LEADS "
         f"with what SURVIVED, honest baselines, no gate benched at face value. (2) READS WELL — plain English to Garrath, "
         f"money-first, no jargon, lots of fact-tables. (3) THOROUGH — no thin/placeholder/TODO bits, every number a REAL "
         f"computation, every grave shown. (4) MAKES SENSE — no contradictions, shadow-vs-live reconciled, each verdict follows "
         f"its own numbers, and NO stale prior-week content survived the stitch (check dates and named findings). (5) UNANSWERED "
         f"QUESTIONS he WILL poke at — his tells: a shadow number without the live cross-check; thin-n stated as fact; 'so what "
         f"do I actually DO Monday'; a $ figure without its baseline; a gate called bad without a rehab attempt; an exit-ladder "
         f"rung left unproven; a 'why' not chased to root cause; a promotion call without the robustness battery. ★ Do NOT flag "
         f"win-rate as a defect on its own — the desk runs ~39% and is profitable; expectancy is the measure. Write STRICT JSON "
         f"to {SEC}/proofread.json: {{\"mission_ok\":bool,\"reads_ok\":bool,\"thorough_ok\":bool,\"sensible_ok\":bool,"
         f"\"issues\":[{{\"section\":str,\"problem\":str,\"fix\":str}}],\"unanswered\":[{{\"question\":str,\"how_to_answer\":str}}]}}"),

    dict(key="rev2", artifact=f"{SEC}/rev2_done.txt", deps=["proofread"], timeout_s=5400, prompt=PRE +
         f"REVISION 2. Read {SEC}/proofread.json. For EACH entry in `unanswered`, ANSWER it fully from REAL data (tick-honest, "
         f"regime-segmented) and for EACH entry in `issues`, FIX it — editing the SOURCE FRAGMENTS in {SEC} (never the built "
         f"HTML, which is re-rendered from them). Recompute anything numeric; never hand-wave a number. Then re-run "
         f"scripts/friday_v7_build.py with system python3 to re-render HTML+PDF, and re-run the publish gate "
         f"(scripts/publish_report.py) if present. {JUDGE} {STYLE} Finally write a Rev1->Rev2 changelog to "
         f"{SEC}/rev2_done.txt listing every question closed and every fix applied. If proofread.json listed nothing, write "
         f"'no changes required' to that file and stop."),

    dict(key="final", artifact=f"{SEC}/final_check.txt", deps=["rev2"], timeout_s=2700, prompt=PRE +
         f"FINAL CHECK — the wake-up standard. Re-read the published {WEB}/weekly_*.html end-to-end. Confirm MISSION / "
         f"READS-WELL / THOROUGH / MAKES-SENSE all pass, the proofread's questions are closed, every grave is visible, and no "
         f"stale prior-week content survived. Verify weekly_<date>.html + .pdf + monday_<date>.html all exist and report their "
         f"pdfinfo page count and word count. If any MATERIAL gap remains, fix it directly and re-render. Then PING the operator "
         f"via Telegram (`PYTHONPATH=src ./.venv/bin/python -c \"from gazbot7.notify import notify; notify('<msg>', "
         f"critical=True)\"`) with the /v7/reports link, a 3-line 'what SURVIVED' summary, and the page count. Write a one-page "
         f"summary of the final state to {SEC}/final_check.txt."),
]

PHASES_BY_KEY = {p["key"]: p for p in PHASES}


def resolve(phase, week):
    """Substitute the week stamp into artifact/prompt."""
    return dict(phase, artifact=phase["artifact"].replace("{WEEK}", week),
                prompt=phase["prompt"].replace("{WEEK}", week))
