#!/usr/bin/env python3
"""Emit reports/friday_v7/plays.json for the 2026-08-08 Friday report.

Every field here is lifted from a section fragment in reports/friday_v7/sections/.
Nothing is recomputed and nothing is invented: where a section did not state a
number, the field says so rather than carrying a guess.

Schema per play (the build script and the Monday playbook both read this):
  id, window, rank, topic, play          — what to do
  mechanism, arms_when, exit             — the gate/mechanism, its arming regime, its exit
  tier                                   — LIVE / SHADOW / PARKED / REFUTED
  kill                                   — the kill criterion (or revival condition when PARKED)
  number, owner, revert                  — the number behind it, who owns it, how to undo it
  rationale, section_ref, verification, suggested_mode
"""
from __future__ import annotations

import json
import pathlib

OUT = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"

P: list[dict] = []


def add(**kw):
    P.append(kw)


# ─────────────────────────────────────────────────────────────────────────────
# SATURDAY — code + config, needs a restart, window shuts at the Sunday reopen
# ─────────────────────────────────────────────────────────────────────────────
add(
    id="grind-long-revert-atr22-ext30-0808", window="SATURDAY", rank=1,
    topic="grind_long: put the ATR floor back to 22 and the extension ceiling back to 3.0",
    play="Revert the 2026-08-01 change. ATR floor 10 → 22, ext ceiling 2.0 → 3.0. Two literals; no new "
         "mechanism, no new filter — this is undoing a change that was fitted on too short a tape.",
    mechanism="grind_long — trend-continuation gate, entry-side ATR floor and extension ceiling",
    arms_when="ATR1m ≥ 22 at signal, and price no more than 3.0 ATR extended from its anchor. Below "
              "ATR 22 the gate does not arm at all.",
    exit="Unchanged — the deployed two-lot ladder (Lot A fixed-R scalp, Lot B chandelier), plus the "
         "quiet-tape clip below ATR 22 (which the new floor makes almost unreachable).",
    tier="LIVE",
    kill="Fewer than 15 of 19 target-winners retained on fresh tape, or a negative $/leg over the "
         "next 40 live legs. Either one and the floor goes back to 10.",
    number="+$3,964 over 11 tick-honest sessions (07-24…08-07): +$1,930 on 744 legs becomes +$5,893 "
           "on 155 legs. This week alone −$288 → +$2,178. Keeps 19 of 19 target winners; positive in "
           "all four ISO weeks where the live config is negative in two; survives deleting its five "
           "best trades (+$3,593); 10 of 11 sessions green.",
    owner="Garrath — two literals in deciders.py + tournament restart",
    revert="Put 10 and 2.0 back. One line each, and the gate returns to exactly this week's behaviour.",
    rationale="grind_long did not look broken because it is a bad gate — it looked broken because of a "
              "bad ATR floor. The 08-01 change cut the floor to 10 and the gate started taking 744 legs "
              "to earn what 155 legs earn.",
    section_ref="Part 1.5 §1 (rehabilitation lead table)",
    verification="Re-score on the next 11 sessions and confirm the leg count stays near 155, not 744.",
    suggested_mode="live-paper",
)

add(
    id="absveto-short-arm-by-default-er035-0808", window="SATURDAY", rank=2,
    topic="abs_veto_short: arm it by default, and give it an ER30 ≥ 0.35 floor",
    play="Stop running abs_veto_short as a 22-minute discretionary window. Arm it by default, delete "
         "the two bad bench rules, add the one new entry veto from the rehab — and add the router's "
         "ER30 ≥ 0.35 arming floor, mirroring grind's. Do NOT apply that floor to abs_veto_long.",
    mechanism="abs_veto_short — thrust + 55-second absorption veto, short side",
    arms_when="Armed by default. Gated only by ER30 ≥ 0.35 on the trailing 30 minutes; below that "
              "band the gate does not arm.",
    exit="Unchanged deployed two-lot ladder. (The 55-second entry WAIT is a separate open question — "
         "see BUILD: shrink the wait, keep the test.)",
    tier="LIVE",
    kill="Review after 15 fires under the floor. If the ER ≥ 0.35 band goes negative over those 15, "
         "the floor is not the fix and the gate goes back to benched.",
    number="The signal is +$2,290.50 over 159 fires / 17 days / 4-of-4 weeks green / positive in all "
           "five regimes, and 53 of 54 filters tested LOSE to just letting it fire. Over the 96.7% of "
           "this week it was benched, the identically-configured twin made +$1,064.50. The router "
           "benched it 91% of the week while its shadow twin made +$928, and armed it for 9% during "
           "which it lost −$559.00 on nine lots without a single winner. The ER floor is +$61.20/trade "
           "above 0.35 (n=9) against negative in all three bands below (n=26), and blocks 2 of the "
           "week's 4 losing entries (−$274).",
    owner="Garrath — gate config + reactivate_gates.py + tournament restart",
    revert="Re-bench it in gate_switches.env. Fully reversible on any 5-minute tick; the ER floor "
           "fails safe because a floor can only ever reduce arming.",
    rationale="This is the single biggest leak in the report and both halves of it point the same way: "
              "the gate's SIGNAL is the strongest thing on the desk, and the desk's ARMING of it was "
              "backwards on both sides — benched through the good tape, armed into the bad.",
    section_ref="Part 1.5 §1 · Part 2 §3 · Part 2.6 §8 Saturday #1",
    verification="Track live fills against the shadow twin for 15 fires; they should stop diverging.",
    suggested_mode="live-paper",
)

add(
    id="chandelier-regime-key-width-0808", window="SATURDAY", rank=3,
    topic="chandelier: regime-key the width instead of running one number",
    play="Key the chandelier width on the regime at entry: ER30 ≥ 0.25 AND ATR ≥ 22 → Lot B runs a 6R "
         "chandelier. Everything else keeps today's width.",
    mechanism="chandelier / managed-profit exit path, Lot B",
    arms_when="Evaluated at entry, frozen for the life of the trade: ER30 ≥ 0.25 and ATR1m ≥ 22 is "
              "the wide cell. This is an EXIT selector, not an entry condition — it does not arm or "
              "bench any gate.",
    exit="Lot B chandelier at 6R in the wide cell; unchanged elsewhere. Lot A untouched.",
    tier="LIVE",
    kill="If the wide cell goes negative over 20 fresh sessions, or if the LOO minimum drops below "
         "zero on the next re-cut, revert to the single width.",
    number="+$3,049 over 20 sessions (07-15…08-07). Positive in 20 of 20 leave-one-day-out folds, "
           "minimum +$1,604. Better in all four ISO weeks. The delta survives 2pt of slippage. This "
           "week: −$1,073 → −$643.",
    owner="Garrath — exit_overrides.json + tournament restart",
    revert="Delete the key. The chandelier goes back to a single width immediately.",
    rationale="The chandelier looked like a threshold that had stopped being reached. It had actually "
              "been switched off in code. Regime-keying is what it should have had all along.",
    section_ref="Part 1.5 §1 (chandelier dossier)",
    verification="20 more sessions; re-run the LOO fold and confirm the minimum stays positive.",
    suggested_mode="live-paper",
)

add(
    id="exhaustion-short-exit-revert-8-12-120-0808", window="SATURDAY", rank=4,
    topic="exhaustion_short: put the exit back to the fixed 8pt / 12pt / 120s it had on 07-25",
    play="Revert the exit to the fixed 8pt / 12pt / 120s ladder. Note this is an EXIT fix on a gate "
         "whose ENTRY is parked — do both, do not confuse them.",
    mechanism="exhaustion_short — roll-over fader",
    arms_when="PARKED as an entry. The gate is sub-friction by about two dollars a lot; it does not "
              "get armed on this evidence. The exit revert is so that when it IS revived it is not "
              "revived onto a worse exit.",
    exit="Fixed 8pt / 12pt / 120s — the 07-25 ladder.",
    tier="PARKED",
    kill="Revival condition: the gate must clear friction — roughly +$2/lot of headroom — on a fresh "
         "sample before it is armed again. Until then the exit revert ships and the entry stays off.",
    number="+$604 over 6 dense-book days on identical entries, taken as the mean of 10 polling phases. "
           "All six fixed-point exits beat the incumbent. ⚠ the standard deviation across those ten "
           "polling phases is $418 on a −$880 mean — anyone quoting a single run of that harness is "
           "quoting noise.",
    owner="Garrath — exit_overrides.json + tournament restart",
    revert="Delete the key.",
    rationale="A two-year-old exit was replaced with a worse one. Reverting costs nothing and removes "
              "a confound from any future attempt to revive the gate.",
    section_ref="Part 1.5 §1 · Part 1.5 §6 (microstructure sampling noise)",
    verification="Re-run at 10 polling phases and quote the mean, never a single run.",
    suggested_mode="live-paper (exit only — entry stays parked)",
)

add(
    id="max-hold-keep-120-add-ceiling-0808", window="SATURDAY", rank=5,
    topic="MAX_HOLD: keep the 120 minutes, add a ceiling that survives a dead loop",
    play="Do not shorten MAX_HOLD — every attempt to is a fake win. Add the ceiling that still fires "
         "when the main loop has stopped cycling.",
    mechanism="MAX_HOLD — the 2-hour time-cap exit",
    arms_when="Always on. It is a safety cap, not a strategy.",
    exit="120 minutes, unchanged, plus an independent ceiling that does not depend on the main loop "
         "being alive.",
    tier="LIVE",
    kill="None — this is a safety net. If the ceiling ever fires spuriously, fix the ceiling, do not "
         "remove the cap.",
    number="+$461.50 on the archive. ⚠ MAX_HOLD has four fires in 21 days and every per-regime "
           "'optimum' in its sweep rests on one to four bound trades — the ceiling is justified by the "
           "failure mode, not by the P&L.",
    owner="Garrath — code + restart",
    revert="Remove the ceiling. Do NOT touch the 120 minutes: that cap is what limited the MD_STREAM "
           "incident to −$255.50.",
    rationale="MAX_HOLD looked like the worst exit on the desk and was the fire alarm being blamed for "
              "the fire. The real defect is that it can be skipped when the loop wedges.",
    section_ref="Part 1.5 §1 · Part 1.5 §5",
    verification="Kill the loop in a test and confirm the ceiling still flattens.",
    suggested_mode="live-paper",
)

add(
    id="day-rider-eff-floor-025-0808", window="SATURDAY", rank=6,
    topic="DAY RIDER: raise the efficiency floor 0.15 → 0.25",
    play="One constant in drift.py. This is the only day-rider change this week that touches the money.",
    mechanism="day_rider — drift detection from the 13:30 UTC cash open",
    arms_when="efficiency ≥ 0.25 (was 0.15) AND roundtrip ≥ 0.45, measured from the cash open. One "
              "entry per session, no entry after 15:00 UTC.",
    exit="Unchanged — the armed trail, hard flat 20:40 UTC. Do not tune it further (see HOLD).",
    tier="LIVE",
    kill="56 recorded sessions at the 0.25 floor, at 1 lot, with trade rows actually written. If "
         "$/trade drifts toward zero over that stretch it was three good days in June and July.",
    number="+$5,410 → +$8,819 over the same 38 sessions; +$142 → +$276 a trade; plateau across "
           "0.18–0.35; positive in 32 of 32 leave-one-day-out folds; consistent in and out of sample. "
           "It cuts time-to-answer from 10.5 months to 2.7.",
    owner="Garrath — one constant in drift.py",
    revert="Put 0.15 back. One number.",
    rationale="Not one of 114 exit rules touches the money on this strategy; the seven days that lost "
              "$1,000+ lost −$11,195 between them and the trail we shipped saves $0.00 on every one of "
              "them, because price never went our way at all. The entry is the whole lever.",
    section_ref="Part 2.7 (day rider) DR7 #1",
    verification="56 recorded sessions at 1 lot. If +$276/trade holds anywhere near that it clears t=2.",
    suggested_mode="live-paper",
)

add(
    id="day-rider-write-trade-rows-0808", window="SATURDAY", rank=7,
    topic="DAY RIDER: write the trade rows, and pass desk= at the same time",
    play="Add a record_trade call on entry and on exit. In the SAME change, pass desk= in web.py and "
         "core.py so the day-rider's P&L stops blending into the tournament's.",
    mechanism="day_rider persistence + P&L attribution",
    arms_when="N/A — infrastructure.",
    exit="N/A.",
    tier="LIVE",
    kill="None. Without this the strategy is unmeasurable.",
    number="The strategy has been live for 3 days and has produced 0 trade rows; we are flying on a "
           "journal file that gets overwritten every session. 3 of 4 P&L surfaces blend the two books "
           "— including core.py:406, the daily-loss kill switch. A day-rider loss counts against the "
           "tournament's headroom, so one bad afternoon on a strategy with a $1,059 daily standard "
           "deviation could halt eight gates that did nothing wrong.",
    owner="Garrath — code + restart",
    revert="N/A — it is additive instrumentation.",
    rationale="The two things protecting us today are accidents: the kill switches are set to 0, and "
              "the day-rider writes no rows. The moment either changes, this becomes live. Fix desk= "
              "at the same time as the write path, not after it.",
    section_ref="Part 2.7 DR7 #2 and #3",
    verification="Confirm rows appear with the right desk tag and that pnl.day() separates the books.",
    suggested_mode="live-paper",
)

add(
    id="day-rider-cut-to-1-lot-0808", window="SATURDAY", rank=8,
    topic="DAY RIDER: cut to 1 lot until 56 recorded sessions",
    play="Halve the size. It costs no information and it is the only thing standing between a bad "
         "afternoon and a hole in the desk.",
    mechanism="day_rider position sizing",
    arms_when="Same detection as above; only the size changes.",
    exit="Unchanged.",
    tier="LIVE",
    kill="Restore 2 lots only after 56 recorded sessions at the 0.25 floor come back near +$276/trade.",
    number="A day-rider lot carries 15× the swing of a tournament lot; its worst day is 64% of the "
           "desk's all-time loss. Halving size costs no information.",
    owner="Garrath — day_rider config",
    revert="Set it back to 2. One number.",
    rationale="38 sessions and one real live trade is not a validation. Size for the sample you have.",
    section_ref="Part 2.7 DR7 #4",
    verification="56 recorded sessions.",
    suggested_mode="live-paper",
)

# ─────────────────────────────────────────────────────────────────────────────
# MONDAY — switch-file / router config, reversible inside five minutes
# ─────────────────────────────────────────────────────────────────────────────
add(
    id="router-timing-window45-hold3-0808", window="MONDAY", rank=1,
    topic="Router timing: WINDOW 30 → 45, HOLD 2 → 3, STEP → 5. Leave the thresholds alone.",
    play="Change the timing only. ER_TREND stays 0.15 and NET_MIN stays 30 — both grids independently "
         "pick the incumbent and the surface around it is flat. Correct STEP to 5 to match the live tick.",
    mechanism="the direction router's regime-detection timing",
    arms_when="N/A — this changes how long the router looks back and how many marks it holds a "
              "decision for, not what it arms.",
    exit="N/A.",
    tier="LIVE",
    kill="Re-validate after the first week containing two or more clean-trend days. A stickier router "
         "is a chop optimisation. If it starts benching the aligned rider late, put HOLD back to 2 first.",
    number="+$502 on the live-managed set and +$399 on the full historical set. It is an interior peak "
           "on window, step, hold and ER — not a grid edge — and flat plateau on net. Survives LOO on "
           "both sets (+$574 / +$1,040), and both universes rank every cell identically.",
    owner="The durable router tick — config only",
    revert="Put 30 and 2 back. Reversible on any 5-minute tick.",
    rationale="The thresholds do not need touching. The timing does — and unusually for this desk it "
              "is an interior peak on four axes at once rather than the edge of a grid.",
    section_ref="Part 2.6 §8 Saturday #2",
    verification="Re-run after a two-clean-trend-day week; watch for late benches on aligned momentum.",
    suggested_mode="live-paper",
)

add(
    id="meter-stayout-45-and-no-preopen-0808", window="MONDAY", rank=2,
    topic="Untradeable meter: STAY-OUT cutoff 65 → 45, and no stay-out can trigger before 15:00Z",
    play="Two changes to one rule. Drop the cutoff to 45, and add an explicit clause that a reading "
         "taken before 15:00 UTC never triggers a stay-out.",
    mechanism="the untradeable meter, as a stay-out trigger",
    arms_when="Meter ≥ 45 AND the clock is at or past 15:00 UTC → stay out. Before 15:00Z the meter is "
              "advisory only.",
    exit="N/A — it blocks new entries only; opens still exit and stops are untouched.",
    tier="LIVE",
    kill="In-sample on n=10 days. If it stays out of a green day twice, the cutoff goes back up.",
    number="At 45 the meter catches 4 of 6 red days and 0 of 4 green days, worth +$1,418 against the "
           "current +$1,138, with 22 points of headroom above the worst green day. The current 65 "
           "cutoff catches 2 of 6. Before the US open the meter correlates +0.13 with the day's P&L — "
           "noise — and it read 92 on a +$638 day. Note the 45 deliberately declines the in-sample "
           "optimum of 30.",
    owner="The durable router tick",
    revert="One threshold, one clause. Reversible every 5 minutes.",
    rationale="The meter separates green from red days perfectly at end-of-day and is useless before "
              "the open. So use it at end-of-day and forbid it from speaking before 15:00Z.",
    section_ref="Part 2.6 §8 Saturday #3",
    verification="n=10 today. Re-grade at n=25 days before trusting the 45.",
    suggested_mode="live-paper",
)

add(
    id="fix-midnight-reopen-reversion-only-0808", window="MONDAY", rank=3,
    topic="Fix the midnight reopen: re-arm reversion gates only, make momentum earn its arm",
    play="Change reactivate_gates.py's default set so the 22:00 UTC reopen re-arms the reversion gates "
         "only. Momentum gates start benched and the router arms them on evidence. And move the "
         "21:00–22:00Z maintenance gap so the hour before the reopen is supervised.",
    mechanism="reactivate_gates.py — the Paris-midnight all-on",
    arms_when="At the 22:00 UTC reopen: reversion gates on, momentum gates off pending a real break "
              "with ER climbing AND vol expanding.",
    exit="N/A.",
    tier="LIVE",
    kill="If the reversion-only reopen costs a genuine overnight trend two weeks running, put the "
         "all-on back and solve it in the router instead.",
    number="32% of the week's switch changes are spent undoing the 22:00 all-on; it cost −$275 in one "
           "night on 07-31. The overnight block ran 8 trades this week for zero winners and −$578, and "
           "89 trades over 40 days for −$906 at a 31% win rate.",
    owner="Garrath / the durable router tick — reactivate_gates.py default set",
    revert="Restore the all-on default set. One list.",
    rationale="A third of the router's entire work-rate is spent undoing a policy that fires once a "
              "night into the worst block on the desk.",
    section_ref="Part 2.6 §8 Saturday #4 · Part 2.6 §7 (session blocks)",
    verification="Count switch changes in the 22:00–23:59Z block next week; it should collapse.",
    suggested_mode="live-paper",
)

add(
    id="chop-avoidance-is-the-biggest-number-0808", window="MONDAY", rank=4,
    topic="★ Sit out the chop blocks — this is the largest single number in the report",
    play="No new mechanism. The router already owns the lever: when the tape is in a chop block, "
         "bench the book. This is the biggest number anywhere in this report and it needs no code.",
    mechanism="the router's existing bench, applied to entry-regime chop",
    arms_when="Inverse: it BENCHES when the entry regime is chop. Re-arm on a real break with ER "
              "climbing AND vol expanding — vol expansion is the binding leg.",
    exit="N/A — benching blocks new entries only.",
    tier="LIVE",
    kill="If a month of chop-benching costs more in missed non-chop trades than it saves, the "
         "attribution is wrong and this goes back to the lab.",
    number="Live trades attributed to entry regime over 17 days: chop 336 trades −$5,483; non-chop 263 "
           "trades +$1,482. Perfect avoidance turns −$4,001 into +$1,482. A perfect chop filter beats "
           "every invention in this report by an order of magnitude.",
    owner="The durable router tick",
    revert="Reversible every 5 minutes.",
    rationale="Three independent sections landed on the same conclusion this week: the desk does not "
              "lose money on trend days, it loses money on high-volatility days that go nowhere. "
              "Wednesday and Thursday — the two days ATR doubled from 12 to 20 and the tape went "
              "nowhere — took −$1,122 out of the desk between them.",
    section_ref="Movement 3 (master ledger, chop lab) · Part 1 (day-by-day) · Part 2.5",
    verification="Attribute next week's trades to entry regime and re-cut the same table.",
    suggested_mode="live-paper",
)

add(
    id="vol-expansion-not-a-rearm-trigger-0808", window="MONDAY", rank=5,
    topic="Promote the vol-expansion caveat to a written rule",
    play="Write it into the tick prompt: expanding ATR alone, in ER < 0.15 chop with no range break, "
         "is NOT a re-arm trigger. Rule text only, no code.",
    mechanism="router re-arm policy",
    arms_when="Re-arm requires a real range break WITH ER climbing AND vol expanding. Vol expansion on "
              "its own is not enough.",
    exit="N/A.",
    tier="LIVE",
    kill="None — it is a fail-safe rule that can only reduce arming.",
    number="It fooled the desk at least three times this week alone: 08-06 08:15 and 08-06 11:05 (both "
           "decayed inside 15 minutes) and 08-07 13:50 (armed on an ATR reading that was wrong by 15 "
           "points).",
    owner="Garrath — prompt text",
    revert="Delete the sentence. Fail-safe either way.",
    rationale="Vol expansion is the binding leg for a re-arm, but only alongside ER and a break. On "
              "its own it is the most reliable way to get armed into chop.",
    section_ref="Part 2.6 §8 Saturday #7",
    verification="Count re-arms that decay inside 35 minutes next week.",
    suggested_mode="live-paper",
)

add(
    id="grade-the-bad-days-0808", window="MONDAY", rank=6,
    topic="Grade the bad days in the bad-call ledger",
    play="The ledger has zero entries for 08-03, 08-04 and 08-05. Backfill them, then keep grading "
         "every day, not just the ones that went well.",
    mechanism="router bad-call ledger discipline",
    arms_when="N/A.",
    exit="N/A.",
    tier="LIVE",
    kill="None — it is discipline, not code.",
    number="30 switch changes and −$947 of P&L are currently ungraded. The scoreboard samples the "
           "well-supervised days, which biases it favourably.",
    owner="Claude — the 4-hourly ledger review",
    revert="N/A.",
    rationale="A scoreboard that only scores the days somebody was watching is not a scoreboard.",
    section_ref="Part 2.6 §8 Saturday #8",
    verification="Ledger coverage should be 5 of 5 sessions next week.",
    suggested_mode="observe-only",
)

# ─────────────────────────────────────────────────────────────────────────────
# BUILD — nothing goes live this week
# ─────────────────────────────────────────────────────────────────────────────
add(
    id="open-rider-to-shadow-0808", window="BUILD", rank=1,
    topic="★ THE OPEN RIDER → the shadow book. Not live. Not this month.",
    play="Add the OPEN RIDER to the shadow slate at its published spec, with the 14:45 cut applied and "
         "cadence-3 struck from the language. It does NOT go live on 17 in-sample days, and the "
         "skeptic panel voted 2–1, not 3–0.",
    mechanism="OPEN RIDER — no trigger at all. The clock is the trigger: every 5 minutes in "
              "13:00–14:45 UTC, if flat, take a trade in the direction of the last 15 minutes' move.",
    arms_when="13:00–14:45 UTC only (right edge cut from 15:00). Five-minute cadence; re-entry blocked "
              "until the open trade closes. No threshold, no efficiency dial, no book reading.",
    exit="Stop 2.0 × ATR1m — twice the desk's house style, mean 54.6pt ≈ $109 of risk. Target 2R. "
         "Time cap 45 minutes, then out at market.",
    tier="SHADOW",
    kill="PROMOTE ONLY IF all four: +0.15R over 200 shadow trades including a non-trending open week; "
         "the 14:45 cut in place; a live 2×ATR stop path (scaleout_slots() forces stop_atr_mult=1.0 "
         "today); and position isolation from the day-rider. Fail any one and it stays in shadow.",
    number="36 days, n=236, +$7,433 at the correct $1.50/RT, 47.0% win, +$31.50 a trade, +0.288R. The "
           "number that matters: on 19 days of TRUE out-of-sample V5 tape it does +$3,526 / n=115 / "
           "+$30.66 a trade — a 5% degradation on tape no parameter was ever fitted on. 36/36 "
           "leave-one-day-out positive; reverse walk-forward picks the published cell #1 of 48 and all "
           "48 cells are holdout-positive; placebo z=+2.59, p=0.005. ⚠ the placebo mean is NOT zero — "
           "the wide-stop/2R shape is worth something on its own.",
    owner="Claude — shadow slate only",
    revert="Remove it from the shadow slate. It is explicitly never live this week.",
    rationale="Built as the control that was supposed to lose to the clever inventions, and it beat "
              "both of them. But one of three independent skeptics REFUTED it (see NOT-AN-ACTION), and "
              "two skeptics with different out-of-sample legs reached opposite verdicts on the same "
              "strategy. That is exactly why it is a shadow candidate and not a live one — and the "
              "honest way to resolve it is forward tape, not another backtest.",
    section_ref="Movement 3 §4–5 and the master ledger",
    verification="200 shadow trades including a non-trending open week.",
    suggested_mode="shadow",
)

add(
    id="orphan-stop-auditor-on-a-timer-0808", window="BUILD", rank=2,
    topic="★ Build the inverse auditor: does every live STOP have a slot?",
    play="Run the orphan sweep on a TIMER, not only at boot. The desk audits 'does every slot have a "
         "live stop?' and never asks the inverse — and it is the inverse that fires unattended.",
    mechanism="order/position reconciliation across the shared account",
    arms_when="N/A — safety infrastructure.",
    exit="N/A.",
    tier="LIVE",
    kill="None. This is the open gap from the 08-06 incident and two separate rehabs found it "
         "independently this week.",
    number="Two orphaned GTC stops opened a naked 2-lot short on 08-06 and it was booked to a gate "
           "that had been benched 38 minutes earlier. Separately, the two poisoned stops from 08-04 "
           "rested ~2,000pt away for three days. Until it exists, any gate's ledger can be "
           "contaminated by another gate's garbage — the nipc rehab would have started from a 6% hit "
           "rate on 16 trades instead of 0% on 14 if the order-id namespace had not been checked.",
    owner="Claude — build, then live-verify",
    revert="N/A — it is a read-only auditor plus an alarm.",
    rationale="Same class as the MD_STREAM bug: a SHARED resource consumed without checking the tag "
              "that says whose it is. There the stream was multi-symbol; here the account is "
              "multi-desk.",
    section_ref="Part 1.5 §5",
    verification="Plant an orphan stop in a test and confirm the timer alarms on it.",
    suggested_mode="observe-only then alarm",
)

add(
    id="fix-shadow-repricer-stop-detection-0808", window="BUILD", rank=3,
    topic="★ Fix the shadow repricer's stop detection — then re-run everything that concluded 'exit earlier'",
    play="The shadow book leaks past its own stops on 44% of trades. Fix the detection, then re-run "
         "every study that ever concluded 'exit earlier'.",
    mechanism="shadow repricer",
    arms_when="N/A — method fix.",
    exit="N/A.",
    tier="LIVE",
    kill="None. Until it lands, treat every shadow result that rewards cutting early as inflated.",
    number="Median overshoot 0.56 × ATR, maximum 32.32 × ATR, on a book that is 99% 1.0 × ATR stops. "
           "It is why the MFE-release rule looks brilliant in shadow and negative on live.",
    owner="Claude — repricer + re-run",
    revert="N/A.",
    rationale="This is a method fix that decides whether next Friday's exit numbers can be trusted at "
              "all. It sits in the same family as the standing rule that every shadow loss is a FLOOR.",
    section_ref="Part 1.5 §5",
    verification="Re-run the MFE-release rule and confirm shadow and live stop disagreeing.",
    suggested_mode="observe-only",
)

add(
    id="shadow-db-data-quality-column-0808", window="BUILD", rank=4,
    topic="shadow.db needs the data_quality column gazbot7.db already has",
    play="Add it, and backfill the tape-consistency screen's strikes.",
    mechanism="shadow book data hygiene",
    arms_when="N/A.",
    exit="N/A.",
    tier="LIVE",
    kill="None.",
    number="The tape-consistency screen struck 166 of 7,639 shadow rows across 14 separate days. "
           "Nothing flags them. MD contamination in the shadow book is a 14-day condition, not one "
           "bad night.",
    owner="Claude — schema + backfill",
    revert="N/A.",
    rationale="The trade book learned this lesson in August. The shadow book has not.",
    section_ref="Part 1.5 §5",
    verification="Re-run the screen and confirm the 166 rows are now flagged and excluded.",
    suggested_mode="observe-only",
)

add(
    id="populate-signal-journal-suppressed-by-0808", window="BUILD", rank=5,
    topic="Populate signal_journal.suppressed_by — it is NULL in all 596 rows",
    play="Write the field. Until it is populated, every statement about which gate fires were "
         "suppressed and why is unsupported by the store.",
    mechanism="signal journal",
    arms_when="N/A.",
    exit="N/A.",
    tier="LIVE",
    kill="None.",
    number="NULL in all 596 rows. Everything in this week's dossiers about what a gate would have done "
           "unrouted is RECONSTRUCTED from the tape, not read from a log.",
    owner="Claude — one write path",
    revert="N/A.",
    rationale="It is the difference between a reconstruction and a measurement.",
    section_ref="Part 1.5 §5",
    verification="Confirm non-NULL rows appear and that they agree with a tape reconstruction.",
    suggested_mode="observe-only",
)

add(
    id="union-tick-sources-empty-day-must-raise-0808", window="BUILD", rank=6,
    topic="Union the two tick sources, and make an empty tick-day RAISE",
    play="Neither tick source covers the window on its own. Union them, and make a harness that finds "
         "zero ticks for a day raise instead of booking zero trades.",
    mechanism="tick data access layer",
    arms_when="N/A.",
    exit="N/A.",
    tier="LIVE",
    kill="None.",
    number="data/tape/ticks/MNQ/ is missing 2026-08-07 while capture.db has it; capture.db's ticks only "
           "reach back to 08-03. A harness reading only the archive silently loses the most recent "
           "session and books zero trades with no error — which is exactly what the shipped nipc "
           "replay is doing right now.",
    owner="Claude — lake layer + harness guard",
    revert="N/A.",
    rationale="A silent zero is the most expensive kind of bug this desk has: it looks like a result.",
    section_ref="Part 1.5 §5",
    verification="Point a harness at a day with no ticks and confirm it raises.",
    suggested_mode="observe-only",
)

add(
    id="stop-limit-fill-plausibility-0808", window="BUILD", rank=7,
    topic="Stop-limit orders are filling AT their limit, 20pt through their own trigger",
    play="Narrow the limit buffer to ~5 points or use a plain stop-market. Add a fill-plausibility "
         "check: if a stop fills more than N points through its trigger, alarm and reprice it against "
         "the tape before it is booked.",
    mechanism="stop order type + fill validation",
    arms_when="N/A.",
    exit="This IS the exit path — it is the stop itself.",
    tier="LIVE",
    kill="None.",
    number="2 lots this week, both the second lot of a pair, both within four minutes of the cash "
           "open. The other 54 stop fills have a median slippage of 0.00pt. One filled 10.25pt above "
           "the highest print in the window. Roughly $70/week of fake losses. Found independently by "
           "two rehabs.",
    owner="Claude — order type + validation",
    revert="Restore the wider buffer.",
    rationale="We caught this by hand. Nothing in the desk would have.",
    section_ref="Part 1.5 §5",
    verification="Zero fills more than N points through trigger over a month.",
    suggested_mode="observe-only then alarm",
)

add(
    id="reconstruct-rederive-entry-atr-0808", window="BUILD", rank=8,
    topic="On reconstruct(), re-derive the entry ATR from the tape",
    play="Refuse to adopt a slot whose persisted stop is more than a few ATR from entry. Re-derive the "
         "ATR from the tape instead of trusting the persisted value.",
    mechanism="slot reconstruction after a restart",
    arms_when="N/A.",
    exit="Protects the stop and target geometry of an adopted slot.",
    tier="LIVE",
    kill="None.",
    number="The 08-04 gold-bar leak was fixed in five minutes. Its consequence survived, because "
           "reconstruct() re-adopted two open slots with the 1,848pt ATR persisted — leaving the stop "
           "naked, both targets unreachable and the quiet clip disabled, for 115 minutes. Cost: "
           "$192.50 in one night.",
    owner="Claude — reconstruct() guard",
    revert="N/A.",
    rationale="A poisoned number survived a restart. Fixing the producer did not fix the consumer.",
    section_ref="Part 1.5 §5",
    verification="Restart with a poisoned persisted ATR and confirm the slot is refused.",
    suggested_mode="observe-only",
)

add(
    id="log-the-silent-return-paths-0808", window="BUILD", rank=9,
    topic="One log line: the desk cannot tell you why an approved entry never became an order",
    play="Add the log line to all three silent return paths.",
    mechanism="entry → order path",
    arms_when="N/A.",
    exit="N/A.",
    tier="LIVE",
    kill="None.",
    number="On 08-07 at 14:19:36 both lots logged 'confirmed → OPEN' and then nothing at all — no "
           "order, no signals row, no error. Three silent return paths, none of which logs. (For the "
           "record it saved us $174 that day, and that has NOT been credited back — you cannot bank a "
           "loss you avoided by accident.)",
    owner="Claude — one log line",
    revert="N/A.",
    rationale="Three silent return paths is three ways to lose a day and never know.",
    section_ref="Part 1.5 §5",
    verification="Force each path in a test and confirm it logs.",
    suggested_mode="observe-only",
)

add(
    id="fix-nightly-fader-repricing-0808", window="BUILD", rank=10,
    topic="Fix the nightly's fader repricing — stop scoring blocked fader signals at a fixed scalp-2R",
    play="Use the gate's own exit when repricing a blocked fader signal, not a fixed scalp-2R.",
    mechanism="the nightly router-value repricer",
    arms_when="N/A.",
    exit="N/A — it is a measurement of exits, not an exit.",
    tier="LIVE",
    kill="None — diagnostic only, no live behaviour changes.",
    number="The nightly says benching capitulation_long cost +$368 of winners; the shadow mirror says "
           "it avoided −$1,609. Both cannot be right and the fixed-scalp assumption is the suspect. "
           "The fader half of the router's '+$635 of missed winners' is probably the same artefact.",
    owner="Claude — nightly repricer",
    revert="N/A.",
    rationale="The router's own scoreboard is currently marking its best decisions as mistakes.",
    section_ref="Part 2.6 §8 Saturday #5",
    verification="Re-run and confirm the nightly and the shadow mirror stop contradicting each other.",
    suggested_mode="observe-only",
)

add(
    id="shrink-the-55s-wait-keep-the-test-0808", window="BUILD", rank=11,
    topic="abs_veto_short: keep the absorption test, shrink the 55-second wait",
    play="A specific, testable job: the veto is doing its job, the DELAY attached to it is not. Sweep "
         "the wait down and re-derive.",
    mechanism="abs_veto_short — the 55-second confirm clock, separate from the absorption test",
    arms_when="Same as the gate. This changes only how long it waits after the test passes.",
    exit="Unchanged.",
    tier="SHADOW",
    kill="If a shorter wait does not beat 55 seconds on a population that is not the run tape, leave "
         "it at 55. ⚠ this measurement is on n=2 surviving thrusts — it is a direction, not a "
         "measurement.",
    number="On run tape the wait costs $596.50 against the $169 the test saves. The absorption test "
           "blocked three raw fires, all three losers, saving $169. On the two thrusts that survived "
           "the test, waiting 55 seconds turned +$97 into −$71 and +$282.50 into −$146 — same signal, "
           "same bar, same exit, only the entry clock differs. Net effect on run tape: −$427.50.",
    owner="Claude — sweep then propose",
    revert="N/A — nothing ships this week.",
    rationale="It lines up with the single strongest finding in Movement 3: every minute of "
              "confirmation you wait for costs about $600 on run tape.",
    section_ref="Movement 2 (lead) · Movement 3 (oracle: lateness)",
    verification="Sweep the wait on a non-run population before proposing anything.",
    suggested_mode="shadow",
)

add(
    id="quiet-clip-regime-carveout-0808", window="BUILD", rank=12,
    topic="The quiet-tape clip is a chop tool doing chop work in the wrong place",
    play="Design and backtest a regime carve-out so the clip stops firing on run tape. Do not just "
         "delete it — it was proven on the whole book.",
    mechanism="quiet-tape clip (ATR < 22 → Lot A banks $40, Lot B banks $60 / 1.75R)",
    arms_when="Frozen at entry on ATR < 22. The carve-out would add a run/no-run condition on top.",
    exit="This IS an exit rule.",
    tier="SHADOW",
    kill="If the carve-out does not beat the blanket clip on the whole book — not just on run tape — "
         "it does not ship. Judging it only on the runs is judging it on exactly the trades it was "
         "designed to skip.",
    number="Live on 35 of the 53 testable runs and cost $1,202 on run tape. Identical entries: clip ON "
           "returns +$1,696.50, clip OFF returns +$2,898.50.",
    owner="Claude — backtest, then a Saturday",
    revert="N/A — nothing ships this week.",
    rationale="It is the right tool in the wrong regime, which is the same shape as the chandelier "
              "finding — and the chandelier's answer was to regime-key it, not remove it.",
    section_ref="Movement 2 (lead)",
    verification="Score the carve-out on the whole book, not the run subset.",
    suggested_mode="shadow",
)

add(
    id="grind-ext-hi-regime-conditional-0808", window="BUILD", rank=13,
    topic="grind_long's ext_hi ceiling: the highest-value knob in Movement 2, and it needs a proper re-derivation",
    play="Re-derive the extension ceiling regime-conditionally. Do NOT remove it on this evidence.",
    mechanism="grind_long extension ceiling ('don't buy what is already stretched')",
    arms_when="Today: ext ≤ 2.0 live, going to 3.0 on Saturday. The study would make it conditional on "
              "regime rather than a single number.",
    exit="Unchanged.",
    tier="SHADOW",
    kill="It stays as-is unless a regime-conditional version beats the flat ceiling on the WHOLE book. "
         "On a sat-out-run population it is being judged on exactly the trades it was designed to skip.",
    number="Ungated, grind fired at 7 of the 22 up-runs for +$742.50; mechanically it fired once, for "
           "−$130. The ceiling blocked six of its seven pre-run fires.",
    owner="Claude — regime-conditional backtest",
    revert="N/A — nothing ships this week beyond the Saturday 2.0 → 3.0 revert.",
    rationale="It is the single filter standing between the desk and these runs — but that is an "
              "argument for measuring it properly, not for deleting it.",
    section_ref="Movement 2 (lead)",
    verification="Whole-book scoring with an out-of-sample leg.",
    suggested_mode="shadow",
)

add(
    id="nipc-short-to-shadow-0808", window="BUILD", rank=14,
    topic="nipc_short → SHADOW. It is direction-beta wearing a state machine.",
    play="Move it to the shadow slate. It is not a wrong-rung problem, it is a direction bet.",
    mechanism="nipc_short",
    arms_when="Not armed. Shadow only.",
    exit="Shadow default.",
    tier="SHADOW",
    kill="Revive only if it clears its null on a sample where the direction bet is not doing the work "
         "— i.e. a flat or down week. Note it already hit the operator's −$400 kill criterion on 08-06 "
         "(n=47, 26% win) and sits in reactivate_gates.py::HOLD.",
    number="Every train-optimum in the nipc dossier is killed by its own out-of-sample leg. It looked "
           "like a wrong-rung problem and is a direction bet.",
    owner="Claude — shadow slate",
    revert="Remove from the shadow slate.",
    rationale="Re-arming it is a fresh operator decision, not a router decision.",
    section_ref="Part 1.5 §1 · CLAUDE.md 08-06 note",
    verification="A flat or down week.",
    suggested_mode="shadow",
)

add(
    id="flow-break-ignition-flow-trap-fade-shadow-0808", window="BUILD", rank=15,
    topic="FLOW-BREAK IGNITION and FLOW-TRAP FADE → shadow ×2 (check FADE for redundancy first)",
    play="Shadow both. ⚠ check FLOW-TRAP FADE against our existing abs_veto absorption work BEFORE "
         "shadowing what may be a duplicate.",
    mechanism="FLOW-BREAK IGNITION = sustained flow + a 30-minute range break. FLOW-TRAP FADE = "
              "aggressors lean hard and fail to move price.",
    arms_when="Both are flow-conditioned and therefore capped at 5 days of aggressor-tagged ticks — "
              "which is the real constraint on both.",
    exit="Shadow defaults.",
    tier="SHADOW",
    kill="PROMOTE IF: IGNITION keeps US-session $/trade above ~$40 at n ≥ 50 over 3 more weeks of "
         "ticks AND its out-of-sample leg stops being a coin flip. FADE holds ≥ $25/trade over n ≥ 80.",
    number="IGNITION +$1,967 on 39 trades, 56.4% win, 45 of 45 sweep cells green — but its "
           "out-of-sample half collapses to a coin flip. FADE +$2,024 on 44 trades, all five days "
           "green, leave-one-day-out flat as a board, and its OOS leg holds — the sturdier of the two. "
           "Both catch 0 of the 4 runs they were built for. Both are 5-day findings wearing a "
           "confident number.",
    owner="Claude — shadow slate",
    revert="Remove from the shadow slate.",
    rationale="Neither answers the assignment they came from, which is exactly why they are shadow "
              "and not live.",
    section_ref="Movement 3 §3 and master ledger",
    verification="3 more weeks of ticks.",
    suggested_mode="shadow",
)

add(
    id="dead-chop-fade-2000-shadow-0808", window="BUILD", rank=16,
    topic="DEAD-CHOP fade, 20:00–21:00 UTC → shadow",
    play="Shadow it. It should never be promoted on this sample.",
    mechanism="DEAD-CHOP fade — fade the band in the dead hour before the CME halt",
    arms_when="20:00–21:00 UTC only, ATR < 10.",
    exit="As specified in the lab's 20 costed cells.",
    tier="SHADOW",
    kill="Revival requires ALL THREE: (1) n ≥ 60 costed shadow trades, roughly 6–8 more weeks at ~1 "
         "trade a day; (2) the race stays at P ≥ 0.57 with z ≥ 2 on the FORWARD sample only; (3) the "
         "20-cell plateau still has ≥ 80% of cells positive and the ATR < 10 gate still separates. "
         "Clear all three and it earns a 1-lot promotion inside the 20:00–21:00 window only.",
    number="Race n=159, P=0.610, z=+2.78; all 20 costed cells positive. But only n=10 actual trades.",
    owner="Claude — shadow slate",
    revert="Remove from the shadow slate.",
    rationale="Thin n is a shadow, never a kill — and never a promotion either.",
    section_ref="Movement 3 (chop lab, master ledger)",
    verification="6–8 weeks to n ≥ 60.",
    suggested_mode="shadow",
)

add(
    id="wide-stops-open-window-shadow-0808", window="BUILD", rank=17,
    topic="Wide stops (≥ 2 × ATR1m) in the open window — and check the live gates, it costs nothing",
    play="Shadow the finding properly, and separately: check the desk's ~1-ATR house stop against the "
         "live gates in the open window. That check costs nothing and is the one thing in Movement 3 "
         "worth looking at this week.",
    mechanism="stop width, in the 13:00–14:45 UTC window",
    arms_when="Open window only. This is a stop-geometry finding, not an entry.",
    exit="Stop ≥ 2.0 × ATR1m instead of the house ~1.0.",
    tier="SHADOW",
    kill="Revive/confirm ONLY IF re-measured on a signal whose intercept is not zero — it has only "
         "ever been measured inside the OPEN RIDER, whose own intercept is −$23 (t=−0.22).",
    number="Three independent votes: the survivor's own 45-cell grid, the robustness skeptic's "
           "from-scratch rebuild, and the oracle all agree — every cell at a 1-ATR stop is "
           "flat-to-negative, all 27 cells at 2.0 × ATR or wider are positive. Mean stop 57.7pt "
           "against a mean 1-min ATR of 28.8pt. Even a perfect entry gets shaken out of 14 of 52 runs "
           "at 1 ATR against 0 of 52 at 2 ATR.",
    owner="Claude — shadow + a live-gate check",
    revert="N/A — nothing ships.",
    rationale="This is the most transferable thing in the whole greenfield movement, and it is about "
              "the gates we already own rather than a new one.",
    section_ref="Movement 3 §4–5 and master ledger",
    verification="Re-measure on a signal with a non-zero intercept.",
    suggested_mode="shadow",
)

add(
    id="census-cluster-labels-persist-3-0808", window="BUILD", rank=18,
    topic="The census cluster labels are reporting noise as structure — require persist ≥ 3",
    play="Either require persist ≥ 3 for a FLOW-LED / VACUUM label, or retire both back into one "
         "'flow event' bucket.",
    mechanism="Movement 1 census cluster labelling",
    arms_when="N/A — a labelling fix.",
    exit="N/A.",
    tier="REFUTED (as written)",
    kill="The labels as written are refuted: one minute of |z| ≥ 1 assigns the label, that minute "
         "reverses on the next bar, and an independent re-derivation disagrees with the label 3 times "
         "out of 4.",
    number="At the target runs the flow's run-length is one or two minutes and it reverses on the next "
           "bar. VACUUM fires on 1,451 minutes to find 8 runs — 0.55%, roughly 300 fires a day to "
           "find one. On 08-04 01:40 the flow is NEGATIVE at the start of a +128pt UP run that the "
           "census called FLOW-LED.",
    owner="Claude — two scripts",
    revert="Git revert.",
    rationale="Without it, next Friday's agent digs the same empty hole — two hunts already died in it "
              "this week.",
    section_ref="Movement 3 §3 and master ledger (census)",
    verification="Re-label the census and confirm the two clusters stop being two names for one coin.",
    suggested_mode="observe-only",
)

add(
    id="keep-archiving-ticks-0808", window="BUILD", rank=19,
    topic="★ The binding constraint on flow research is RETENTION, not ideas",
    play="Keep archiving ticks. This is an infrastructure action, not a research one — and it is the "
         "single highest-leverage thing on this list for next month's research.",
    mechanism="tick archive retention (capture.db 5 trading days → Parquet → B2)",
    arms_when="N/A.",
    exit="N/A.",
    tier="LIVE",
    kill="None.",
    number="Five days of aggressor-tagged ticks caps every flow finding this desk will ever have at "
           "n ≈ 40. Three more weeks would take FLOW-TRAP FADE from n=44 to n ≈ 180 and turn 'not "
           "obviously noise' into an answer. VACUUM work needs ~15 sessions against the 5 we have. And "
           "the bar-derived flow proxy is REFUTED — aggressor sign is genuinely absent from OHLCV, so "
           "there is no way to buy the missing days back.",
    owner="Nobody — it is already running. Do not let the mirror stop.",
    revert="N/A. ★ Remember the interlock: prune_capture.py may not delete a day tape_mirror.py has "
           "not exported AND verified by row count.",
    rationale="Growth you notice; a silent gap in the tape you do not.",
    section_ref="Movement 3 §2 and the take-aways",
    verification="Row-count verification on every mirrored day.",
    suggested_mode="observe-only",
)

# ─────────────────────────────────────────────────────────────────────────────
# HOLD — already right, the action is to NOT touch them
# ─────────────────────────────────────────────────────────────────────────────
add(
    id="hold-absveto-long-0808", window="HOLD", rank=1,
    topic="abs_veto_long — leave it completely alone. It is the one gate that survived.",
    play="No change. Do not add a filter, do not add an ER floor, do not touch its exit.",
    mechanism="abs_veto_long — thrust-continuation with a 55-second confirm",
    arms_when="Armed. It only fires when a burst is still going 55 seconds later, which is exactly the "
              "behaviour this week rewarded. ⚠ do NOT give it the ER30 ≥ 0.35 floor that abs_veto_short "
              "is getting — the long twin has the opposite profile.",
    exit="Lot A at 1.0R, Lot B at 1.5R, quiet-tape clip on both under ATR 22.",
    tier="LIVE",
    kill="If it goes negative on a month of fresh tape. Nothing shorter.",
    number="Sixteen entries, thirty-two lots, +$566.00 at a 62% strike rate, average winner +$47.60 "
           "against an average loser of −$32.20. Still positive if you delete ANY single day of the "
           "week (+$235.50 / +$635.00 / +$582.00 / +$245.50) and still +$363 if you delete its three "
           "best lots. On the ER bands the long twin is +$19.00/trade in the 0.15–0.25 band and "
           "−$0.90 above 0.35 — the mirror image of the short side.",
    owner="Nobody — this is a confirmation",
    revert="N/A.",
    rationale="It is the one number in Part 1 worth putting weight on. Everything else on the desk "
              "this week is thin, one-week, or explained by a software defect.",
    section_ref="Part 1 (lead) · Part 2.6 §8",
    verification="Standing.",
    suggested_mode="live-paper",
)

add(
    id="hold-do-not-build-event-driven-guard-0808", window="HOLD", rank=2,
    topic="★ Do NOT build the event-driven, zero-lag, per-gate regime guard",
    play="Do not build it. This is the most useful negative result in the router review and it is the "
         "exact thing that felt most obviously right.",
    mechanism="an in-code, per-gate regime guard evaluated at entry time instead of a 5-minute poll",
    arms_when="N/A — it would replace the poll.",
    exit="N/A.",
    tier="REFUTED",
    kill="Backtested and refuted: +$304 against the poll's +$682 on this week, +$267 against +$475 "
         "over 40 days, and it fails leave-one-day-out.",
    number="Zero trades opened in the five minutes before any bench decision all week — there is no "
           "reaction-lag leak to fix, and the theoretical ceiling on chasing it is ~$300. The "
           "hysteresis that makes the poll 'slow' is the thing earning the money.",
    owner="Nobody",
    revert="N/A.",
    rationale="Kept on the card with its autopsy so it is not re-proposed next quarter.",
    section_ref="Part 2.6 (the one thing that did not survive) · §8",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="hold-do-not-touch-er-trend-net-min-daybias-0808", window="HOLD", rank=3,
    topic="Do not touch ER_TREND, NET_MIN, or the day-bias ±40",
    play="Leave all three. Both grids independently pick the incumbent cell and the surface around it "
         "is flat.",
    mechanism="router thresholds",
    arms_when="ER_TREND 0.15, NET_MIN 30, day-bias ±40 — unchanged.",
    exit="N/A.",
    tier="LIVE",
    kill="None — the evidence is that there is nothing to find here.",
    number="ER 0.15 / net 30 came out top on BOTH test sets. On the day-bias there is no optimum at "
           "all: counter-day-bias trades lose $16–18 each at every threshold from 0 to 150, and "
           "raising it makes the aligned book worse.",
    owner="Nobody",
    revert="N/A.",
    rationale="A flat surface is a finding. Tuning into it is how you buy noise.",
    section_ref="Part 2.6 §8 (what I would not do)",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="hold-day-rider-exit-and-stops-0808", window="HOLD", rank=4,
    topic="DAY RIDER: leave the trail alone, add no stop below 600pt, and stop tuning the exit",
    play="Three non-actions on one strategy. The trail's shipped rationale is wrong but the rule is "
         "harmless and mildly positive — changing it again on a noise surface is churn.",
    mechanism="day_rider exit machinery",
    arms_when="N/A.",
    exit="The 4×/2× ATR armed trail, hard flat 20:40 UTC. Unchanged. 600pt venue stop is last-resort "
         "insurance only.",
    tier="LIVE",
    kill="None — the finding is that there is nothing here to optimise.",
    number="Every fixed stop from 75 to 400 points is worse than no stop at all; 150/200/250/300/400 "
           "all turn the strategy NEGATIVE, and winners routinely draw 250–490pt against them first. "
           "On the exit surface, Spearman between in-sample and out-of-sample rank across 114 rules is "
           "−0.30, and the best in-sample rule ranked 71st of 114 out of sample and lost to plain "
           "holding. The 4×ATR trail is a HARDER bar than the old +150pt on 30 of 38 days and rescues "
           "exactly zero extra days.",
    owner="Nobody",
    revert="N/A.",
    rationale="A negatively-correlated rank surface is the definition of a parameter you must not "
              "tune. And 'the exit is exit-proof' is now half wrong — holding beats every stop, but "
              "its whole edge is three days; strip them and $5,410 becomes $379. That is an argument "
              "about the ENTRY, which is what Saturday #6 changes.",
    section_ref="Part 2.7 DR7 #5, #9, #10",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="hold-asia-block-and-1330-1445-0808", window="HOLD", rank=5,
    topic="Keep the ASIA block, and keep the 13:30–14:45 window",
    play="No change to either. Both are standing findings that survived a full battery.",
    mechanism="session-time policy (RunConfig.no_open_asia, and the validated US window)",
    arms_when="No new entries 00:00–07:00 UTC. Exits and every flatten path untouched.",
    exit="Unchanged.",
    tier="LIVE",
    kill="None. Note Movement 3 independently re-confirmed the 14:45 right edge this week from a "
         "completely different direction — the OPEN RIDER's 14:45–15:00 slice is −$446 on the full "
         "tape and −$453 on the unseen leg alone.",
    number="ASIA shadow n=1840 at −$3.17/trade, the worst block on the desk. The 13:30–14:45 window is "
           "+$8.93/trade on n=562. ⚠ 'don't day-trade until the US open' was TESTED AND REFUTED — "
           "LONDON 07–13 is the desk's only positive block.",
    owner="Nobody — already in config",
    revert="no_open_asia=False.",
    rationale="Two independent re-confirmations of the 14:45 edge in one week is as good as this desk "
              "gets.",
    section_ref="Movement 3 §5 (lens 2) · standing config",
    verification="Standing.",
    suggested_mode="live-paper",
)

# ─────────────────────────────────────────────────────────────────────────────
# NOT-AN-ACTION — withdrawn / refuted, kept on the card with their autopsies
# ─────────────────────────────────────────────────────────────────────────────
add(
    id="not-run-state-as-a-routing-lever-0808", window="NOT-AN-ACTION", rank=1,
    topic="★ RUN STATE as a ROUTING lever — WITHDRAWN. It is an exit find wearing a router's coat.",
    play="Do not re-plumb the router around run state. The variable is real; the lever is not the one "
         "we were told.",
    mechanism="run-state detection (runstate.py / run_detect.py) used to arm and bench gates",
    arms_when="N/A — withdrawn as a routing rule.",
    exit="N/A — but see the number: the money is in the EXITS on the same entries.",
    tier="REFUTED (as a routing lever) / LIVE (as a variable)",
    kill="The headline cell does not reproduce. Same 89 Mon–Thu trades, re-derived from scratch: "
         "in-run aligned TAKEN goes from the lead doc's n=34 · 50% · +$10.34/tr to n=46 · 41% · "
         "−$1.83/tr. Armed inside an aligned run the desk made NOTHING — it lost $1.83 a lot. The "
         "34/4/51 split could not be reproduced under ANY run-span definition tried (merge gaps 0s, "
         "120s, 300s, 600s, 900s all give the identical 46/10/33).",
    number="What DOES reproduce is the missed side: in-run aligned MISSED n=96 · 59% · +$2,703, chop "
           "MISSED n=194 · 26% · −$2,089. The genuine spread is between the signals it BLOCKED "
           "(+$27/signal aligned) and the chop it TRADED (−$19/lot) — about $17–$46 a trade depending "
           "which pair you compare, not the flat $39 quoted. And the lever: arming more would have "
           "added roughly $170 this week, benching the 84 no-run trades would have saved $584, but "
           "re-pricing the EXITS on the exact same entries the desk already took — changing nothing "
           "about routing — turns the week from −$772 into +$1,493.",
    owner="Nobody — do not re-plumb the router",
    revert="N/A. Run state stays as a reported STATE that never flips a switch, which is what it "
           "already is.",
    rationale="It beat 4,000 placebo shuffles twice and held on twelve sessions it was never fitted "
              "on, so the variable survives. But the money is not where the lead said it was. Use "
              "these numbers, not those.",
    section_ref="Part 2.5 LEAD 1",
    verification="Re-derive on next week's tape before anyone quotes the $39.",
    suggested_mode="none",
)

add(
    id="not-odr-as-a-tradeable-edge-0808", window="NOT-AN-ACTION", rank=2,
    topic="The OPEN RIDER as a tradeable EDGE — REFUTED by skeptic lens 1 (the dissent)",
    play="Printed in full, deliberately, because the panel voted 2–1 and this is the 1. The OPEN RIDER "
         "still goes to shadow — but nobody should read its headline as an edge.",
    mechanism="OPEN RIDER, viewed as an exposure rather than a signal",
    arms_when="N/A.",
    exit="N/A.",
    tier="REFUTED",
    kill="Three kills. (1) The intercept is zero: regress each day's P&L on that day's absolute "
         "13:00–15:00 travel over 34 days and the zero-drift day pays −$23 (t=−0.22) while the drift "
         "loading is $1.237/pt (t=+2.75). (2) The machinery is decorative: a control making ONE "
         "direction decision per day earns +$6,005 of the RIDER's +$6,810 over 34 days — 88% — so the "
         "whole 5-minute cadence is worth $3.31 a trade, less than the $1.23 it costs to cross the "
         "spread. (3) Out of sample it is inside the null: on 17 unseen V5 days it lands at the 83.2nd "
         "percentile of 2,000 random-direction placebos, p=0.168, against the 99.4th percentile "
         "(p=0.0065) on the fitted days.",
    number="Concentration: 8 of 34 days carry 82% of the net. Cumulative window drift over those 34 "
           "days is −1,389.5pt, so a single held SHORT lot books $2,728 with no strategy at all. What "
           "the lens concedes: the clock observation is real and stable ($1.237/pt holding at "
           "1.207/1.091 across both independent halves) and wide stops genuinely beat the house 1-ATR.",
    owner="Nobody",
    revert="N/A.",
    rationale="Two skeptics with DIFFERENT out-of-sample legs — 17 unseen days versus 19 — reached "
              "opposite verdicts on the same strategy. That is not a contradiction to paper over; it "
              "is the reason this is a shadow candidate, and the honest way to resolve it is forward "
              "tape, not another backtest.",
    section_ref="Movement 3 §5 lens 1",
    verification="Forward tape only.",
    suggested_mode="none",
)

add(
    id="not-odr-as-a-gate-or-beside-day-rider-0808", window="NOT-AN-ACTION", rank=3,
    topic="The OPEN RIDER as a tournament gate, or running beside the day-rider — REFUTED twice over",
    play="Even if it were an edge, it cannot be deployed as configured. Two independent blockers.",
    mechanism="ODR deployment path",
    arms_when="N/A.",
    exit="Its 2×ATR stop is the entire finding — and the live path will not give it one.",
    tier="REFUTED (as a gate) / PARKED (beside the day-rider, pending isolation)",
    kill="As a gate: scaleout_slots() forces stop_atr_mult=1.0 on every live path, and at that stop "
         "the same entries earn +$17.59 a trade — a 62% haircut at double the fill count — plus the "
         "quiet-tape clip fires on 34–41% of entries. Beside the day-rider: 49% of entries open inside "
         "the day-rider's live window, 2.6 direction flips a day, and 34% of colliding entries are "
         "OPPOSITE its direction rule, on a netted account.",
    number="REVIVE the day-rider-collision half IF: it gets its own account or per-strategy position "
           "isolation, AND the 'does every live STOP have a slot?' auditor is built (BUILD #2).",
    owner="Nobody",
    revert="N/A.",
    rationale="This is the 08-06 cascade waiting to happen again: the account is SHARED and IBKR nets "
              "two desks into one number.",
    section_ref="Movement 3 master ledger",
    verification="N/A until isolation exists.",
    suggested_mode="none",
)

add(
    id="not-coil-crack-and-exhaustion-fade-0808", window="NOT-AN-ACTION", rank=4,
    topic="COIL-CRACK and OPEN EXHAUSTION FADE — both REFUTED, and the fade is the more instructive one",
    play="Neither is reformulable. Both closed.",
    mechanism="COIL-CRACK = ignition out of a quiet 30 minutes. OPEN EXHAUSTION FADE = fade a straight "
              "30-minute line into the open.",
    arms_when="N/A.",
    exit="N/A.",
    tier="REFUTED",
    kill="COIL-CRACK, by direct ablation — the only test that decides a filter: WITH the efficiency "
         "gate +$2,049 / n=51; WITHOUT it +$2,238 / n=58. It costs money AND sample. The close-location "
         "confirm selected nothing at all (+$830 / +$830 / +$832 at three settings). EXHAUSTION FADE: "
         "51 configurations, every one negative or zero, and it caught 0 of 14 target runs. Both "
         "obvious reformulations — widen the stop to 3–4 ATR, delay entry 10 minutes — were tested and "
         "both fail, which CLOSES it.",
    number="The lesson is the fade: it has the strongest RAW signal found anywhere in Movement 3 — "
           "day-demeaned forward return +54.2pt at 65.8% win, both sides, monotone in the threshold — "
           "and it cannot be traded, because the median excursion AGAINST it is 4.76 ATR against 3.00 "
           "ATR in its favour. A 15-minute edge delivered only after a 4.8-ATR excursion against you "
           "is not an edge you own; it is an edge your stop pays for.",
    owner="Nobody",
    revert="N/A.",
    rationale="A filter that removes trades AND money has nothing to reformulate. And the beautiful "
              "monotone table that motivated COIL-CRACK is an artefact of overlapping 1-minute "
              "sampling — the same pseudo-replication trap that appears three times in this report.",
    section_ref="Movement 3 §4 and master ledger",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="not-vacuum-flow-led-absorption-0808", window="NOT-AN-ACTION", rank=5,
    topic="The whole VACUUM / FLOW-LED / ABSORPTION-SHELF family — one PARKED, the rest REFUTED",
    play="Do not revisit any of it until the tick archive is longer. The clusters they were built to "
         "exploit were never clusters.",
    mechanism="footprint entries built on aggressor flow and L2 depth",
    arms_when="N/A.",
    exit="N/A.",
    tier="REFUTED (FLOW-LED, ABSORPTION-SHELF, FLOW-TRAP, bar-derived flow proxy) / PARKED "
         "(VACUUM-BREAK, the raw sell-burst fade, and the L2 book reading)",
    kill="FLOW-LED, traded as the census's own rule: catch-rate and profitability move in OPPOSITE "
         "directions — every cell catching 2 of 4 targets loses $434–$1,302 over 111–129 trades. Not "
         "thin-n; a mechanism with the wrong sign. ABSORPTION-SHELF: 12 of 12 cells negative and "
         "losing on BOTH sides — not even a drift artefact, just wrong. FLOW-TRAP: the cost-free "
         "forward-return test — its raw 15-min return (+2.25pt, 52.1% up) is BELOW the tape's own "
         "unconditional drift (+2.73pt, 53.9%) at 5, 15 and 30 minutes. Its information content is not "
         "small, it is negative. VACUUM-BREAK: strip-the-best kills it (+$1,069 → +$342 at strip-3 → "
         "+$26 at strip-5 — five trades are the whole thing) and the walk-forwarded regime policy "
         "returns −$125 over 91 trades, a selection tax of $1,194.",
    number="⚠ THE FEE CORRECTION MATTERS HERE AND CHANGES NOTHING: every greenfield backtest in this "
           "Movement was originally priced at ~$5/RT against the true $1.50/RT. The correction is "
           "exactly linear (net@1.50 = net@5.00 + 3.50 × n) so it HELPS everything. One row flips "
           "sign — FLOW-TRAP T=3.0/RM=2.0 goes −$105 → +$154 on 74 trades — and it is flagged. A "
           "loser the correction rescues was never killed by cost in the first place. REVIVE VACUUM "
           "IF: (a) a down-trending or genuinely range-bound week arrives so the +1,300pt melt-up "
           "stops doing the work and the short side clears zero on its own, AND (b) n ≥ 200 "
           "walk-forward trades, needing ~15 sessions of aggressor-tagged ticks against the 5 we have. "
           "The one stone worth funding is the L2 book re-cut on QUEUE DEPLETION RATE rather than "
           "static average depth — the 82.3M-row book table at ~190 snapshots/second supports it.",
    owner="Nobody — keep archiving ticks instead",
    revert="N/A.",
    rationale="A label is not a signal. VACUUM fires on 1,451 minutes to find 8 runs (0.55%); FLOW-LED "
              "hangs on one minute of flow that reverses on the next bar. Both clusters produced no "
              "survivor because the cluster is not a real thing — and finding that out is worth more "
              "than a curve-fitted P&L would have been.",
    section_ref="Movement 3 §2–3 and master ledger",
    verification="~15 sessions of aggressor-tagged ticks.",
    suggested_mode="none",
)

add(
    id="not-any-chop-scalp-0808", window="NOT-AN-ACTION", rank=6,
    topic="Any symmetric chop scalp, at any distance — REFUTED, and here is the bar for the next one",
    play="Do not build a chop scalper. The chop lab was priced correctly at $1.50/RT from the first "
         "line, so there is no fee excuse.",
    mechanism="CHOP-FADE (band fade) and CHOP-EDGE (failed-break fade)",
    arms_when="N/A.",
    exit="N/A.",
    tier="REFUTED",
    kill="Model-free first-touch RACE — not an MFE count: P(revert) = 0.4723 on n=4,249, z = −3.61. "
         "Negative BEFORE any cost. 450 frictionless cells: 34 positive at a median −$1.50 a trade. "
         "77% of random-direction placebos beat the best-of-grid (p = 0.770). CHOP-EDGE: 1 of 15 cells "
         "positive, strip-best-1 already negative, out-of-sample sign flip.",
    number="Maximum gross expectancy in EITHER direction is $1.49 a trade against a $2.24 friction "
           "floor, and the bias decays to 0.5006 by 1.5 ATR — so widening to amortise the fixed fee "
           "destroys the edge it was meant to pay for. ★ STANDING BAR: any future chop-scalper "
           "proposal must FIRST show P(revert first) > 0.5 on fresh tape.",
    owner="Nobody",
    revert="N/A.",
    rationale="The answer to chop is not a chop strategy. It is the off switch — see MONDAY #4, which "
              "is worth an order of magnitude more than any invention in this report.",
    section_ref="Movement 3 (chop lab) and master ledger",
    verification="P(revert first) > 0.5 on fresh tape, or it does not get built.",
    suggested_mode="none",
)

add(
    id="not-idle-gate-lab-as-arming-evidence-0808", window="NOT-AN-ACTION", rank=7,
    topic="The idle-gate lab is an HONEST NULL — do not use it to justify arming anything",
    play="Read it for the diagnosis, not for the P&L. Its three leads are already on this card as "
           "BUILD items; the lab itself arms nothing.",
    mechanism="firing the six live gates mechanically and ungated into the 53 testable sat-out runs",
    arms_when="N/A.",
    exit="Each gate's own deployed two-lot exit, repriced tick-by-tick.",
    tier="REFUTED (as arming evidence)",
    kill="Mechanically: −$474 on 7 fires across 53 testable runs. Ungated: +$997.50 on 19 fires — but "
         "strip the three best trades and that becomes +$62.50.",
    number="The useful part is WHY it is a null, with a number rather than a shrug: the money in these "
           "runs lives in the first ninety seconds after ignition, and our gates fire seven to eight "
           "minutes before it. Every gate we own either wants five minutes of history (abs_veto, "
           "grind) or wants the move to be over (rgv, capitulation, exhaustion). Being late by ninety "
           "seconds is nearly as bad as being wrong.",
    owner="Nobody",
    revert="N/A.",
    rationale="This corroborates the run-catcher NULL already banked on 22.6M ticks — run STARTS are "
              "unpredictable — and adds the complementary fact about latency. The unturned stone is "
              "the narrow band in between.",
    section_ref="Movement 2",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="not-two-ratchet-but-it-did-not-clip-0808", window="NOT-AN-ACTION", rank=8,
    topic="The two-ratchet stays dead — but it did NOT clip a runner, and that is evidence FOR reconsidering it",
    play="Keep it out. But record the correction: the reason we all believed it was killing runners is "
         "not true.",
    mechanism="two-ratchet partial exit",
    arms_when="N/A.",
    exit="This IS an exit rule.",
    tier="PARKED",
    kill="It still lost on the boring trades, which is why it stays out. REVIVE IF: it can be shown to "
         "win on the boring trades, since the runner-clipping objection is now withdrawn.",
    number="26 grind trades, 3 genuine ≥ 4R runners, ZERO clips. The rule says thin n is a shadow and "
           "a withdrawn objection is evidence for reconsidering — so it is reconsidered here, and it "
           "still fails on its own merits rather than on the myth.",
    owner="Nobody — keep it shadowing",
    revert="N/A.",
    rationale="Killing an idea for the wrong reason is how a desk loses an edge for a year. The "
              "objection is retracted; the verdict happens to survive anyway.",
    section_ref="Part 2 §4",
    verification="N/A.",
    suggested_mode="shadow",
)

add(
    id="not-the-exit-ladder-guess-0808", window="NOT-AN-ACTION", rank=9,
    topic="The 2026-07-31 exit-ladder guess — wrong in every cell it could be measured in",
    play="Stop using the hand-written ladder as a reference. The DIRECTION of the guess is right; the "
         "numbers on it are not.",
    mechanism="the operator's 07-31 per-gate exit ladder",
    arms_when="N/A.",
    exit="N/A — it IS an exit spec.",
    tier="REFUTED",
    kill="24 gate × rung cells measured, and the guess never ranked better than 3rd out of 53 "
         "policies in any of them.",
    number="The direction — ride trends, bank chop — survives and is exactly what the chandelier "
           "regime-key (SATURDAY #3) and the quiet-clip carve-out (BUILD #12) implement properly.",
    owner="Nobody",
    revert="N/A.",
    rationale="The instinct was right and the arithmetic was not, which is the most common shape on "
              "this desk.",
    section_ref="Part 2 §5",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="not-giveback-truly-retired-0808", window="NOT-AN-ACTION", rank=10,
    topic="GIVEBACK — TRULY-RETIRED",
    play="It is done. Do not re-propose it.",
    mechanism="give-back-from-peak exit on the tournament book",
    arms_when="N/A.",
    exit="N/A.",
    tier="REFUTED",
    kill="Retired in the rehab dossier after the full six-step wash. ⚠ note this is the TOURNAMENT's "
         "give-back. The DAY RIDER's give-back-33%-of-peak is a separate, live SHADOW item "
         "(92% days green, half the tail, ~$1,000 of the total) — do not confuse the two.",
    number="Not computed here beyond the dossier's verdict; the rehab section carries the working.",
    owner="Nobody",
    revert="N/A.",
    rationale="Named explicitly because the day-rider has a same-named mechanism that is NOT retired.",
    section_ref="Part 1.5 §1 · Part 2.7 DR7 #6",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="not-quote-4169-on-102-trades-0808", window="NOT-AN-ACTION", rank=11,
    topic="'+$4,169 on 102 trades' — PARKED as a quotable figure. Do not quote it.",
    play="If you see this number anywhere, it is wrong twice over. Quote the range instead.",
    mechanism="the OPEN RIDER headline figure",
    arms_when="N/A.",
    exit="N/A.",
    tier="PARKED",
    kill="The '102' is a different row of the report entirely (the thresholding comparison, +$4,142). "
         "The trade count is 129, confirmed independently by three harnesses.",
    number="Three independent harnesses give +$3,907 / +$4,620 / +$5,028 / +$5,139 at the correct fee "
           "on the same 17 days. ★ Quote 'about +$4.4k ± $0.9k on 95 verified trades'. A from-scratch "
           "harness lands 16% below the published headline — treat it as ±20%, never as a precise "
           "figure.",
    owner="Nobody",
    revert="N/A.",
    rationale="A precise-looking number that four harnesses disagree about by $1,200 is a range "
              "wearing a decimal point.",
    section_ref="Movement 3 §5 lenses 1 and 3",
    verification="N/A.",
    suggested_mode="none",
)

add(
    id="not-odr-cadence-3-and-right-edge-0808", window="NOT-AN-ACTION", rank=12,
    topic="ODR cadence-3 (PARTIALLY REFUTED) and the 14:45–15:00 right edge (REFUTED — cut it)",
    play="Strike cadence-3 from the language and cut the right edge. Both are corrections to the "
         "shadow spec, not to anything live.",
    mechanism="OPEN RIDER cadence and window edges",
    arms_when="13:00–14:45 UTC at a 5-minute cadence. Not 3 minutes. Not to 15:00.",
    exit="Unchanged.",
    tier="REFUTED",
    kill="Cadence: on unseen tape cadence-3 is positive in only 4 of 16 cells against 13/16 at 5 "
         "minutes and 15/16 at 10. The plateau is real in STOP WIDTH (27/27 positive at stop ≥ 2.0) "
         "and one-sided in cadence — slower works, faster does not. Right edge: 14:45–15:00 is −$446 "
         "across all days and −$453 on the unseen leg alone.",
    number="The chosen cell sits on the safe side of a cliff the author did not know was there. And "
           "the right-edge cut independently re-confirms the desk's own 14:45 boundary from a "
           "completely different direction.",
    owner="Nobody — spec correction only",
    revert="N/A.",
    rationale="Two corrections to a shadow candidate before it ever trades is the cheapest kind of "
              "correction there is.",
    section_ref="Movement 3 §5 lens 2 and master ledger",
    verification="N/A.",
    suggested_mode="none",
)


def main() -> int:
    seen = set()
    for p in P:
        if p["id"] in seen:
            raise SystemExit(f"duplicate play id: {p['id']}")
        seen.add(p["id"])
        for k in ("id", "window", "rank", "topic", "play", "mechanism", "arms_when", "exit",
                  "tier", "kill", "number", "owner", "revert", "rationale", "section_ref",
                  "verification", "suggested_mode"):
            if k not in p or not str(p[k]).strip():
                raise SystemExit(f"play {p['id']} is missing field {k}")
    pathlib.Path(OUT).write_text(json.dumps(P, indent=2, ensure_ascii=False) + "\n")
    by_win: dict[str, int] = {}
    for p in P:
        by_win[p["window"]] = by_win.get(p["window"], 0) + 1
    print(f"plays.json → {OUT}: {len(P)} plays")
    for w in ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION"):
        print(f"  {w:<14} {by_win.get(w, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
