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
# ★★2026-08-13 THE DATA CONTRACT. Operator: "make sure friday night report takes advantage of all
# data for backtesting" and "make sure the census, greenfield and associated sections include mgc".
# Before this, PRE was one line and every phase discovered the data estate for itself — so three
# prompts said "backtest on capture.db", which silently caps a backtest at FIVE TRADING DAYS of
# ticks, and one specified a $5 round-trip fee against a true $1.50. Both are the kind of error that
# produces a confident, wrong, negative result: a marginal edge dies of a 3.3x fee on a week of tape
# and nobody sees why. Every phase now gets this, in front of its own instructions.
DATA = (
    "=== DATA CONTRACT — read before any query. Getting this wrong produces confident WRONG answers. "
    "(1) SYMBOLS: we capture BOTH MNQ (CME) and MGC (COMEX), L1 and L2. Never assume MNQ-only. "
    "(2) capture.db is a ROLLING WINDOW, not the archive: book/quotes/ticks = 5 TRADING DAYS, bars = 60. "
    "ATTACHing it for anything multi-week silently returns a fifth of the data with no error. "
    "(3) FOR HISTORY USE THE PARQUET LAKE: `from gazbot7.lake import connect` gives ticks/quotes/bars/"
    "book/depth from 2026-07-16 onward, local or straight off Backblaze. That is the correct source "
    "for every backtest longer than this week. "
    "(4) THE FEE IS $1.50 PER ROUND TRIP. Never $5, never $2, never $1.50/side. Grep any harness you "
    "reuse — `FEE, VPP = 5.0, 2.0` and `VPP, FEE = 2.0, 1.5` look identical at a glance and are reversed. "
    "(5) MNQ = $2.00/point, MGC = $10.00/point. Do NOT price MGC with the MNQ multiplier. "
    "(6) OLDER HISTORY EXISTS ON B2: `rclone copy gaz:v5archive/alphabot/<t>.parquet /tmp/v5/` — the "
    "retired V5 desk, incl. 574 MNQ trades, 3,012 us_futures_daytrade trades, fut_signal_funnel (143MB), "
    "fut_edge_observations, fut_regime_routing. Use it to EXTEND a sample; filter "
    "discipline='us_futures_daytrade' or symbol IN ('MNQ','MGC') — the rest is crypto/equities and is "
    "not our desk. "
    "(7) L2: MGC book lives in depth.db.depth_snap, NOT capture.db.book (IBKR allows only 3 depth "
    "subscriptions; capture.db.book is MNQ-only). capture.db.book is 41ms event-driven, depth.db is a "
    "250ms sample — book sees fleeting quotes depth.db cannot. === "
)

PRE = (f"You are writing one section of the GAZBOT V7 Friday report. Repo {GB} (cd there; venv .venv). "
       f"Read {SCOPE} for the mission. {DATA}")

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
         # ★★2026-08-14 OPERATOR: "open rider best shadow again. if we can figure out how to switch
         # it on and off could be a good one." Measured before the run so the phase starts from
         # facts: the premise is wrong but there IS a real finding underneath it.
         f"★★★ REQUIRED THIS WEEK — THE OPEN RIDER (odr_*) DAY-DETECTION PROBLEM, sims 54-57 "
         f"(ungated) and 60-63 (drift-gated). Operator: 'open rider best shadow again ... but i know "
         f"they bleed on other days. thats where im saying we need detection some how to block open "
         f"rider if conditions arent juicy.' HE IS RIGHT ON BOTH HALVES — verify it yourself from "
         f"shadow_real.real_pnl (NEVER ceiling_pnl) and then go after the detector:\n"
         f"  · ON ITS DAY IT OWNS THE BOARD. 2026-08-13: odr took ranks 1,2,3,4 of 44 sims, family "
         f"+$1,688 on 15 trades. 2026-08-14: ranks 1 and 2 of 49.\n"
         f"  · AND IT BLEEDS THE REST. By day: 08-10 -$1,076 · 08-11 +$59 · 08-12 -$1,148 · 08-13 "
         f"+$1,688 · 08-14 -$5. Two GREEN days (+$1,748 over 33 trades) against three RED "
         f"(-$2,229 over 73). Week total -$482 — the average HIDES the strategy completely.\n"
         f"  · ORACLE CEILING: trading only the green days is +$1,748/week, which clears the "
         f"operator's 'few hundred a week' bar several times over. It CHEATS (the labels are only "
         f"knowable afterwards) so it is an upper bound — but it says the prize is real and the whole "
         f"problem is DAY SELECTION, not entry or exit tuning.\n"
         f"  · ★ SO THE SECTION'S JOB IS: can a juicy day be called EARLY and CAUSALLY? Build the "
         f"classifier from information available BEFORE the session commits — opening range, ATR vs "
         f"its own norm, efficiency/roundtrip, overnight range, vol expansion. Placebo-control it "
         f"against skipping the same NUMBER of days at random; removing 60%% of days looks brilliant "
         f"whenever the removed 60%% lost. ⚠ n=5 DAYS. State the power limit honestly — 5 days cannot "
         f"separate a real day-classifier from noise, so the deliverable is the METHOD plus what "
         f"would prove it, not a shipped rule.\n"
         f"  · ★★ THIS IS THE SECOND PLACE THIS WEEK THE SAME SHAPE APPEARED. The MGC run-catcher "
         f"found an identical concentration (run-days pay, the rest bleed; oracle $83/wk on a trail "
         f"vs ~$346/wk on a wide stop) — see docs/MGC_LEADS_2026-08-14.md. TWO independent strategies "
         f"on TWO instruments both live or die on a minority of days. Ask explicitly whether ONE "
         f"day-classifier could serve both; that would be worth more than either gate.\n"
         f"  · Secondary axis, weaker: stop width. All arms, stop 2.0xATR = n=58 -$874 (-$15.08/tr) "
         f"vs 3.0xATR = n=48 +$393 (+$8.19/tr), and s30 beats s20 on 4 of the 5 days. Real, but the "
         f"DAY effect (+$1,688 vs -$1,148) dwarfs it — say so rather than leading with the tuning.\n"
         f"  · The on/off mechanism ALREADY EXISTS and has not fired yet: sims 60-63 are the "
         f"drift-GATED arms, live since 08-14 (ONE day), and on the overlapping period gated and "
         f"ungated are IDENTICAL (n=19, -$2 both) — the gate has not rejected a single entry. Report "
         f"that plainly and say what would prove it. ⚠ Never compare gated vs ungated on ALL-TIME "
         f"totals: the gated arms cover 1 day and the ungated 5, so that measures the calendar. "
         f"Every odr arm is flagged n<40, below this desk's threshold for a forward A/B to claim "
         f"anything, so NO promotion may follow from this week. "

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
         # ★★2026-08-14 GOLD IS A REQUIRED MUSING. Operator: "lets just leave these findings as
         # musings and leads for tonights report" then "put all this mgc work into tonights report".
         # gf_MGC CONSUMES this work as input; this section is where the READER meets it.
         f"★★ GOLD IS A REQUIRED SECTION THIS WEEK — read `docs/MGC_LEADS_2026-08-14.md` and write MGC "
         f"its own part, for a reader who has seen none of it. Lead with the two findings that changed "
         f"the picture. (1) GOLD'S RUNS ARE GRINDS, NOT THRUSTS: the week's top-5 runs have a median "
         f"efficiency of 0.23 and four of five last 2-12 HOURS, so a trailing exit gets shaken out of "
         f"them — the oracle ceiling moves from $83/wk on a 2.5xATR trail to ~$346/wk on a 5xATR stop "
         f"held 8h. THE EXIT WAS THE CAP, NOT THE FILTER, which inverts the order of the whole gold "
         f"problem: boarding was already solved (fires inside 5 of 5 runs, 20%% mark at a median 19min). "
         f"(2) The MGC DAY RIDER threshold grid is a PLATEAU — all 15 cells positive — and at "
         f"ER 0.09-0.12/RT 0.42 it fires on 8 of 16 days with the direction HOLDING to the 20:40 flat "
         f"87.5%% of the time, +$1,742 against the always_short control's +$1,502. Cover too the coil "
         f"bouncer (n=154, median trade +$7.75, placebo beaten 0/12, mirror control -$924) and the "
         f"London-open break fade (n=16, beaten 0/7 shifted anchors, but its median trade LOSES). "
         f"⚠ BE HONEST IN THE OPERATOR'S OWN TERMS: 16-18 gold sessions is thin; the PLATEAU is the "
         f"evidence and NOT the peak cell; everything is SHADOW-only; and the $346/wk is an ORACLE "
         f"upper bound built on labels only knowable afterwards. Explain that SIX earlier gold attacks "
         f"are already refuted, so the reader understands why these are different rather than another "
         f"sweep. Close with the cost of finding out: the missing ingredient is DAYS, not "
         f"configurations. "
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
         f"in-direction, in the 10min before ignition, with tick-honest exits. Use capture.db ONLY if you are strictly "
         f"within its 5-trading-day window; otherwise gazbot7.lake. Per-gate "
         f"scoreboard: fires-on-sat-out-runs, honest $, why-it-misses (mechanism). Almost certainly an HONEST NULL — prove it. "
         f"{SEGMENT} {JUDGE} {GRAVES} {STYLE} Write to {SEC}/movement2_idle_gates.html"),

    dict(key="rehab", artifact=f"{SEC}/part1_5_rehab.html", deps=[], timeout_s=5400, prompt=PRE +
         # ★★2026-08-14 OPERATOR-COMMISSIONED REHAB TARGET. "i also want a little study on exhaustion
         # short. it wins a lot and then can have a series of jumping into up wobbles ... see if any
         # rehab tuning can be done to reduce these bleeding periods ... maybe its the price of doing
         # business but we need to look into it." Then: "maybe more contracts 500 or 600. or maybe a
         # short veto to make sure its not a wobble."
         f"★★ REQUIRED REHAB TARGET #1 THIS WEEK — `exhaustion_short`, commissioned by the operator: "
         f"'it wins a lot and then can have a SERIES of jumping into up wobbles'. It is one of only two "
         f"gates currently armed, so this matters live. The diagnosis is already measured — START FROM "
         f"THESE NUMBERS and go deeper, do not re-derive them:\n"
         f"  · 144 live trades over 15 days, net -$127.00, win 48.6%%, median trade -$16.00.\n"
         f"  · STOPs n=74 = -$3,734.50. EVERYTHING ELSE n=70 = +$3,607.50. The gate earns +$3,608 on "
         f"its winners and the stops erase all of it. The bleed IS the stop book.\n"
         f"  · THE LOSSES ARE CLUSTERED, NOT RANDOM: 26 losing streaks, max 8 long, and streaks of >=3 "
         f"carry 51 of the 74 losses (69%%). 45 of 74 losses arrive WITHIN 15 MINUTES of the previous "
         f"trade. Worst days read WWLLLLLLLL (08-10, -$230) and LLLLWWLLWWLLLLWWLLLLLL (08-12, -$367.50). "
         f"It is re-firing into the SAME rising move, which is exactly the operator's 'wobble'.\n"
         f"★ TEST AT LEAST THESE FOUR, each on LIVE trades and each placebo-controlled against removing "
         f"the same NUMBER of trades at random (removing 40%% of trades looks brilliant whenever the "
         f"removed 40%% lost):\n"
         f"  (1) A RE-ENTRY COOLDOWN after a stop — the 45-of-74-inside-15min figure points straight at "
         f"it. Sweep the cooldown and report the whole curve, not the best cell.\n"
         f"  (2) A STREAK BREAKER — bench the gate after 2 (or N) consecutive stops, for a window or for "
         f"the session. Report what it costs in forgone winners, not only what it saves.\n"
         f"  (3) THE OPERATOR'S VETO IDEA — 'a short veto to make sure its not a wobble'. This is the "
         f"best-motivated of the four: on this desk VETO-shaped filters work where SELECTORS fail "
         f"(abs_veto's 55s wait IS the filter; the OFI delay-veto is the one surviving book cell). Model "
         f"it as a delay-and-re-test on a side the gate has ALREADY chosen — never as a direction "
         f"selector.\n"
         f"  (4) ★ THE OPERATOR'S TRIGGER-SIZE IDEA, and he clarified exactly what he means: "
         f"'my 500 or 600 was the amount of contracts that need to be bought instead of 400 which is "
         f"current trigger. was just an idea to test. if a different number helped.' That is "
         f"`FootprintCfg.net_min` in src/gazbot7/footprint.py:33 — the |20s net signed aggressor "
         f"volume| floor, currently 400.0 CONTRACTS. It is NOT a stop width and NOT position size.\n"
         f"     ★★ THE DATA FOR THIS ALREADY EXISTS AND IS WAITING — do not rebuild it. "
         f"`shadow.db.footprint_signal_net` was created on 2026-07-28 for precisely this tune ('so the "
         f"net_min threshold (400 vs 450 vs 500) can be tuned from real data'), and holds 428 fires "
         f"with their entry `net_signed`; join to `shadow_trades` on trade_id. Measured distribution "
         f"of |net_signed|: p25 444, p50 519, p75 667, p90 906 — so raising the floor to 500 cuts 46%% "
         f"of fires and 600 cuts 68%%. Sweep 400/450/500/550/600/700 and report the FULL CURVE plus "
         f"what each cut costs in forgone winners; a floor that removes two thirds of the book needs "
         f"to earn that.\n"
         f"     ⚠ METHOD, and this is the trap: `exhaustion_rev` in the shadow book runs the FIXED "
         f"8pt/12pt/120s exit, and a fixed-target shadow LIES ABOUT FADERS — this desk has a standing "
         f"rule to judge exhaustion_short on LIVE P&L only. So use footprint_signal_net to establish "
         f"WHICH fires each floor would CUT, then evaluate those on the LIVE trades / the live exit "
         f"reprice. Do NOT read the net_min answer straight off shadow P&L.\n"
         f"★ AND ANSWER THE OPERATOR'S ACTUAL QUESTION HONESTLY: he said 'maybe not, maybe its the price "
         f"of doing business'. If the wobble losses are inseparable from the winning fades — i.e. every "
         f"filter that removes them also removes the winners — SAY SO PLAINLY and show the evidence. A "
         f"clean 'this is the cost of the edge' is a real answer and a more useful one than a fitted "
         f"filter that will not survive next week. Judge on LIVE P&L, never the fixed-target shadow, "
         f"which lies about faders. "

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

    # ★2026-08-13 GOLD RUNS FIRST, ahead of the three MNQ clusters (operator: "move mgc ahead
    # of the mnq greenfield clusters"). The serial runner walks this list IN ORDER and drops
    # optional sections from the END when the body budget runs short — so declaration order IS
    # priority. Gold is the new line of enquiry; the MNQ clusters have had three weeks of
    # attention. If something must be cut this week it should not be the one nobody has run.
    # ★★2026-08-13 THE GOLD HUNT. Operator: "we want to find some gates that work for mgc. and put
    # them into shadow" and, sharpening it: "any gates for mgc long or short need to be created
    # FRESH. dont try and use any existing mnq gates on mgc. if we can end up with a momentum and
    # reversion setup for long and short for mgc after a few weeks would be amazing. all exit types
    # should be tested. scalp with tight Rs and wide chandys for big momentum runs. and also assume
    # the router keeps it turned off in chop."
    # MGC has been captured since 08-04 (L1 + L2, its own depth subscription) and nothing has ever
    # looked at it for entries. The existing six gates were FITTED TO MNQ — reusing them here is
    # not a shortcut, it is the known-dead path: [[mgc-momentum-greenfield-null]] already records
    # that gold's runs are SIZE-predictable but DIRECTION-unpredictable.
    # ⚠ MGC IS $10/POINT, five times MNQ. Price it wrong and gold looks unworthy on arithmetic alone.
    dict(key="gf_MGC", artifact=f"{SEC}/gf_MGC.md", deps=[], timeout_s=5400, prompt=PRE +
         f"GOLD GATE HUNT — MGC. A GREENFIELD build, not a port. This is the flagship new line of "
         f"enquiry: we have captured MGC L1 (ticks/quotes/bars) and L2 (depth.db.depth_snap, 10 levels) "
         f"since 2026-08-04 and have NEVER hunted an entry on it. "

         f"★★★ READ `docs/MGC_LEADS_2026-08-14.md` FIRST — it is a session's worth of gold work done "
         f"on 08-14 and it will save you most of the night. Headlines, so you cannot miss them even "
         f"if the file read fails:\n"
         f"  · SIX attacks are already REFUTED (momentum/direction, arm-then-confirm, router-filter, "
         f"L2 book, fader+clock, thrust-continuation). DO NOT re-derive them. 'Do not retry by tuning "
         f"thresholds.'\n"
         f"  · GOLD'S RUNS ARE GRINDS, NOT THRUSTS: top-5 median ER 0.23, four of five last 2-12 HOURS. "
         f"Boarding is SOLVED (fires inside 5 of 5 runs, 20% mark at a median 19min). A TRAIL is shaken "
         f"out of a grind — oracle ceiling $83/wk on a 2.5xATR trail vs ~$346/wk on a 5xATR stop held "
         f"8h. THE EXIT WAS THE CAP, NOT THE FILTER.\n"
         f"  · MGC DAY RIDER is the most promising shape: thresholds DERIVED from gold's own "
         f"distribution (ER 0.155 / RT 0.417 at MNQ's p65/p53 selectivity — they barely move, because "
         f"efficiency and roundtrip are dimensionless and normalise the 10x ATR difference away). "
         f"Sensitivity grid is a PLATEAU, all 15 cells positive; at ER 0.09-0.12/RT 0.42 it is 8/16 "
         f"days fired, 87.5% direction held, +$1,742 vs the always_short control's +$1,502.\n"
         f"  · Two standalone SHADOW gates exist: coil bouncer (n=154, median trade +$7.75, placebo "
         f"beaten 0/12, mirror control -$924) and London-open break FADE (n=16, beaten 0/7 shifted "
         f"anchors, but median trade loses).\n"
         f"  · ⚠ THREE TRAPS THAT BIT TODAY: (a) pandas `resample` labels a bar by its LEFT edge — "
         f"racing from `ts` replays the decision minute and cost one gate half its result "
         f"(+$906->+$470); enter at ts+60s, or from the tick that crosses a level. (b) "
         f"`drift.DriftRead.ok` means 'enough data', NOT 'fired' — gate on `confirmed`, and "
         f"`direction` is a STRING. (c) `lake.connect()` defaults to symbol='MNQ' — pass "
         f"symbol='MGC' or you will query zero rows and report a confident NULL.\n"
         f"  · PRIORITY TONIGHT: (1) build the CAUSAL day/condition filter for the run-catcher and "
         f"placebo it against discarding the same NUMBER of firings at random; (2) the 8h-12h "
         f"hold-time boundary; (3) the day rider as a 2x2. Anything new must clear the best CONSTANT "
         f"(always_short was 56.2% here), never a coinflip. Existing scripts to build ON, not redo: "
         f"mgc_run_catcher.py, mgc_day_rider_study.py, mgc_drift_thresholds.py, mgc_coil_bounce.py, "
         f"mgc_session_anchor.py. "

         f"★★ RULE 1 — EVERY GATE MUST BE INVENTED FRESH FOR GOLD. Do NOT port, clone, re-tune or "
         f"re-threshold ANY existing MNQ gate (grind, abs_veto, capitulation, exhaustion, rgv, nipc). "
         f"They were fitted to MNQ's microstructure and a re-tuned MNQ gate is a fitted MNQ gate wearing "
         f"a gold hat. Derive each signal from what GOLD's own tape does. You may reuse the desk's "
         f"MECHANICAL PLUMBING (Bar/Features, exit_scalp, exit_chandelier, the ShadowVariant contract) — "
         f"that is infrastructure, not a signal. "

         f"★★ RULE 2 — THE TARGET SHAPE IS A 2x2: {{MOMENTUM, REVERSION}} x {{LONG, SHORT}}. Four cells. "
         f"Hunt all four deliberately and report each one's verdict separately; do not let a strong long "
         f"stand in for a missing short. Gold is event-driven (US data, USD, COMEX/London session shape) "
         f"and its book is far THINNER than MNQ's, so absorption / depletion / level-reclaim mechanics "
         f"that wash out in MNQ depth may be visible here — that is the most promising unexplored angle. "
         f"⚠ Do NOT re-derive the known null: a directional momentum clone is a grave already dug. If "
         f"direction is unpredictable but SIZE is predictable, a VOLATILITY-shaped or breakout-either-way "
         f"entry may beat a directional one — test that explicitly. "

         f"★★ RULE 3 — TEST THE FULL EXIT MATRIX ON EVERY SURVIVING ENTRY, and report the grid. The "
         f"entry and the exit are separate questions and the desk has been burned assuming one implies "
         f"the other. At minimum: (a) TIGHT-R SCALP — sweep target_r across ~0.5/0.75/1.0/1.5/2.0 with a "
         f"matched stop; (b) WIDE CHANDELIER — sweep arm/trail multiples wide enough to ride a big gold "
         f"run rather than clip it; (c) the desk's dual-slot shape, Lot A scalp + Lot B chandelier, which "
         f"is what live MNQ actually runs; (d) a time-cap variant. State plainly which exit family each "
         f"entry NEEDS — a momentum entry that only pays with a wide chandelier is a different animal "
         f"from one that pays on a tight scalp, and the difference decides the slot config. "

         f"★★ RULE 4 — ASSUME THE ROUTER BENCHES IT WHERE IT SHOULD BE BENCHED. Do NOT score a candidate "
         f"blanket across all tape and kill it on the average. Every gate here will be routed: it only "
         f"has to work in the regime it is ARMED for, because the router turns it off elsewhere (in chop "
         f"for momentum, in trend for reversion, and so on). So for EACH cell state explicitly: the HOME "
         f"REGIME it needs, the ROUTER RULE that should arm/bench it (in the same vocabulary the MNQ "
         f"router uses — ER/ATR/structure/session), and its expectancy ON THAT HOME REGIME ONLY, with the "
         f"blanket number reported alongside as context, never as the verdict. If a gate is only viable "
         f"with a router condition we cannot yet measure, say so — that is a finding, not a failure. "

         f"★ DATA: use ALL available MGC tape via the Parquet lake (gazbot7.lake), not capture.db's 5-day "
         f"window. Read {SEC}/movement1_census_MGC.html — the frozen MGC run census — for what gold "
         f"actually did this week and which runs we sat out. MGC = $10.00/POINT. Fees $1.50/round-trip. "

         f"★ DELIVERABLE, and it is the point of the section: for EACH of the four cells give an exact "
         f"mechanical spec (trigger/direction/entry/stop/exit), the tick-honest backtest on its home "
         f"regime, the full robustness battery, the exit grid, and — for any survivor — a SHADOW-READY "
         f"block: the literal ShadowVariant(...) line for src/gazbot7/shadow.py named `mgc_<idea>_<side>`, "
         f"the gate kind it needs, whether ShadowSim._entry can express it or a new branch is required, "
         f"and the router rule that should govern it. The operator's stated goal is a momentum AND a "
         f"reversion setup, long AND short, proven over the coming WEEKS in shadow — so a thin-n "
         f"candidate is a SHADOW ARM, never a kill, and never a live promotion. "
         f"If a cell yields nothing, say so plainly and name the test that killed each attempt — an "
         f"honest gold null is a real result and stops us paying for the data twice. "
         f"{SEGMENT} {JUDGE} {GRAVES} Write your full working to {SEC}/gf_MGC.md, ending with a "
         f"PER-CELL VERDICT TABLE (momentum-long / momentum-short / reversion-long / reversion-short) "
         f"and every SHADOW-READY block."),
    # ── Greenfield: one phase per cluster, independent, so a wedge in one cannot cost the others ──
    *[dict(key=f"gf_{cl}", artifact=f"{SEC}/gf_full_{cl}.md", deps=[], timeout_s=5400, prompt=PRE +
        f"GREENFIELD HUNT — cluster '{cl}'. Read the frozen census {SEC}/census_summary.json (do NOT re-run run_census.py). "
        f"IGNORE the existing gates. INVENT a brand-new entry signal to catch these sat-out runs, with an exact mechanical spec "
        f"(trigger/direction/entry/stop/exit). BACKTEST it tick-honest over the FULL PARQUET LAKE "
        f"(gazbot7.lake, 2026-07-16 onward) — NOT capture.db, which is 5 trading days and would "
        f"silently shrink your sample. "
        f"Net of $1.50/round-trip — the TRUE venue fee. A previous version of this prompt said $5, "
        f"which would have killed any marginal edge on a fee 3.3x too high. ESCALATE if it "
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

    dict(key="movement3", artifact=f"{SEC}/movement3_greenfield.html", deps=["gf_VACUUM", "gf_FLOW-LED", "gf_OPEN-NEWS", "gf_chopscalp", "gf_MGC"],
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
