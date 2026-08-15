#!/usr/bin/env python3
"""Rebuild reports/friday_v7/plays.json from THIS WEEK'S findings only (week ending 2026-08-14).

★ The file on disk was the 2026-08-09 build — 36 plays, all of them last week's conclusions.
Carrying it forward would have put a card at the front of this report that no section in this
report supports, which is the single most misleading thing a weekly can do. It is overwritten.

THE RULE APPLIED HERE: every play must trace to a verdict a section in THIS report actually
reached, and `section_ref` names that section and its disposition row. If a lead is only in a
prior week's report, it is not on this card. Where a play repeats a standing instruction the
desk already follows, it goes in HOLD or NOT-AN-ACTION — never re-proposed as new work.

Sources, all of them this week's fragments:
  part1_live.html            §11 disposition (12 rows)
  part1_5_rehab.html         §9 disposition (10 rows)   — built tonight from the rehab artifacts
  part2_shadow.html          §10 disposition (16 rows)
  part25_musings.html        disposition (10 rows)
  part2_6_router_review.html disposition (14 rows)
  movement2_idle_gates.html  disposition (13 rows)
  movement3_greenfield.html  §9 disposition (10 rows)   — built tonight from the gold hunt
"""
from __future__ import annotations

import json
import pathlib

OUT = "/home/alphabot/gazbot7/reports/friday_v7/plays.json"


def P(pid, window, rank, topic, tier, play, mechanism, section_ref, verification,
      mode, arms_when, exit_, kill, number, owner, revert, rationale="", money_gbp=0):
    """One play.

    `play` is WHAT TO DO, `mechanism` is HOW IT WORKS / what is broken, `section_ref` names the
    section AND the disposition row it comes from, and `verification` is the test that would
    prove it wrong. `rationale` is optional — where the mechanism already says why, a separate
    "Why:" line would just restate it, and the renderer omits empty fields rather than printing
    an empty label.
    """
    return dict(id=pid, window=window, rank=rank, topic=topic, tier=tier, play=play,
                mechanism=mechanism, rationale=rationale, section_ref=section_ref,
                verification=verification, suggested_mode=mode, arms_when=arms_when,
                exit=exit_, kill=kill, number=number, owner=owner, revert=revert,
                money_gbp=money_gbp)


PLAYS = [
    # ══════════════════════════════════════ SATURDAY ══════════════════════════════════
    P("router-timing-45-5-3", "SATURDAY", 1,
      "Router timing: window 45 / step 5 / hold 3",
      "LIVE",
      "Change the direction router's regime window from 30 to 45 minutes, its step to 5 minutes and "
      "its confirmation hold to 3 ticks. One constant block in the router service; restart required.",
      "The 40-day threshold sweep found the gain is in the TIMING, not the thresholds. The ER and "
      "net levels are already at their best cell on both universes independently, so there is "
      "nothing to win there — but the window/step/hold cell is worth +$502 on the live managed set "
      "and +$399 on the full historical fader set, helping on 4 and 6 days respectively and hurting "
      "on 0 and 1.",
      "Part 2.6 §4 — the 40-day sweep, both sets; corroborated independently by the actuation-lag "
      "measurement in §7.",
      "Re-run the sweep on next week's tape and confirm the 45/5/3 cell is still the best or on a "
      "plateau with it. If it has moved, the surface is noise and this reverts.",
      "deploy", "Always — it is the router's own clock, not a gate.",
      "n/a — this is a routing constant, not a trade.",
      "Two consecutive weeks where 45/5/3 scores below the current 30/-/- on the nightly rollup.",
      "+$502 / +$399 across the two universes over 40 days; 4-and-6 days helped, 0-and-1 hurt.",
      "Garrath — router service constants", "Restore the previous window/step/hold and restart; "
      "sub-minute revert, no data migration."),

    P("exh-counter-trend-bench", "SATURDAY", 2,
      "Bench exhaustion_short against a proven counter-trend",
      "LIVE",
      "Add exhaustion_short to the router's managed set so it is benched when the router reads a "
      "trend running against it — the same treatment capitulation_long and rgv_short already get.",
      "exhaustion_short is currently OUTSIDE the router's managed universe, which is why the "
      "leakage detector reported zero leakage while this gate quietly bled. Fading a proven trend "
      "is exactly the failure mode the router was built for.",
      "Part 2.6 §4 and §3 (the leakage the detector cannot see); the gate's own week in Part 1 §3.",
      "n=26 over 30 days is not thin, but review the first 15 benched episodes against what the "
      "gate would have done unbenched before treating it as settled.",
      "deploy", "Router reads a trend opposed to the gate's direction.",
      "Unchanged — this changes whether it may enter, not how it leaves.",
      "Two weeks where the benched windows would have been net positive for the gate.",
      "n=26 / −$398.50 / −$15.33 per trade over 30 days; red on 7 of 8 days; survives strip-worst "
      "and leave-one-out. Separately, −$241.00 leaked through this gate unseen while the detector "
      "reported zero.",
      "Garrath — gate_switches.env + router managed set",
      "Remove from the managed set; the gate returns to always-armed immediately."),

    P("selector-nightly-data-quality", "SATURDAY", 3,
      "selector_nightly.py must respect data_quality",
      "LIVE",
      "Add the `data_quality IS NULL` predicate to scripts/selector_nightly.py so quarantined trades "
      "stop being scored. One WHERE clause.",
      "Quarantined rows are counted as real, and because the selector scores each trade against the "
      "best of three exits, one bad row is counted repeatedly.",
      "Part 2.5 Part C — a broken instrument underneath this report.",
      "Re-run the 13 August rollup after the fix and confirm regret drops from $748 to $458.",
      "deploy", "n/a — nightly job.", "n/a",
      "n/a — this is a correctness fix, not an experiment. It has no failure mode worth reverting.",
      "13 August regret inflated 39% ($748 → $458) by a single quarantined trade counted five "
      "times. It feeds this report's own selector numbers.",
      "Garrath — scripts/selector_nightly.py",
      "Revert the one-line predicate; the job re-runs nightly."),

    P("grind-counter-move-veto", "SATURDAY", 4,
      "grind_long: veto a long that is fighting a 30-minute fall",
      "SHADOW",
      "Add a directional veto inside grind_long's gate function: refuse the entry when the last 30 "
      "minutes have fallen more than 1×ATR. In-code, per-tick — no router, no switch file.",
      "The recurring finding is that the faders' problem is direction-blindness, and the router can "
      "only fix it on a 5-minute lag. A veto inside the gate has no lag at all.",
      "Part 2.5 Part B — the mechanism that does work, and it is a veto.",
      "It is a veto, so the fake-filter guard is the test that matters and it passes: it keeps "
      "10 of the 10 best trades. Confirm that again on the first 30 live fires.",
      "shadow-first", "Always armed; the veto only ever refuses.",
      "Unchanged.",
      "It drops any of the gate's three best trades in its first 30 live fires, or the plateau "
      "narrows to a single cell on next week's tape.",
      "+$2,407 → +$3,134 over 133 tick-honest fires, keeping 10/10 of the best trades, with a "
      "plateau across the whole tested range rather than one hot cell.",
      "Garrath — deciders.py grind_long",
      "Delete the veto clause; the gate returns to its current shape."),

    # ══════════════════════════════════════ MONDAY ═══════════════════════════════════
    P("widen-lot-a-target", "MONDAY", 1,
      "Widen Lot A's profit target — do not drop Lot A",
      "LIVE",
      "Move the tight leg's target out toward the wide leg's. The A/B legs are a scale-out on ONE "
      "signal with one stop, so 'B beat A' is an instruction to widen A, never to delete it.",
      "Both lots enter on the same signal at the same price with the same stop; the only difference "
      "is where they take profit. Over 50 identical entries the wide leg beat the tight one, which "
      "means the tight target is leaving money behind on trades we are already in.",
      "Part 1 §2.2 — the week's best-evidenced result, and §3 'By lot — the tight-leg problem in "
      "one table'.",
      "Placebo p=0.0040, sign test p=0.0235, all five daily folds positive and all four gate folds "
      "positive. Re-check after 30 fresh pairs.",
      "config", "Unchanged.",
      "Lot A target widened; Lot B unchanged.",
      "Two weeks where the tight leg beats the wide leg on the same entries.",
      "+$331.50 over 50 identical entries. Placebo p=0.0040, sign test p=0.0235, 5/5 daily folds "
      "and 4/4 gate folds positive — the cleanest statistical result in the report.",
      "Garrath — exit_overrides.json", "Restore the previous Lot A target; five-minute revert."),

    P("odr-stop-width-3atr", "MONDAY", 2,
      "Open Rider: stop at 3.0×ATR, not 2.0×",
      "SHADOW",
      "Widen the Open Rider's stop from twice ATR to three times.",
      "The house stop is too tight for the open. A 2×ATR stop is shaken out of rides that "
      "subsequently work, and the day rider's edge is in holding.",
      "Part 2 §5 — the secondary axis, stop width.",
      "+$8.19 vs −$15.08 per trade, wins on 4 of 5 days, and the replay agrees across 41 days. "
      "But the DAY effect is 2.2× the stop effect, so this is the smaller of the two levers.",
      "config", "Unchanged.", "Stop 3.0×ATR.",
      "It loses on 3 of the next 5 days, or the day effect swamps it again on a bigger sample.",
      "+$8.19/trade against −$15.08/trade at the current width; 4 of 5 days better; replay agrees "
      "over 41 sessions. Flagged SHADOW because the day effect is 2.2× larger than the stop effect.",
      "Garrath — day rider config", "Restore 2.0×ATR; immediate."),

    P("keep-both-abs-veto-sides", "MONDAY", 3,
      "Leave both abs_veto sides armed — tune the side, never relegate a direction",
      "LIVE",
      "No change. This is on the card because relegating the short side was proposed and refuted, "
      "and the 22:00Z timer will re-arm whatever you switch off anyway.",
      "A gate runs two-sided with independently-tuned per-side thresholds. A direction that loses "
      "in one regime is a tuning problem, not a defective direction.",
      "Part 2 §4 — relegation, and its disposition row 'Relegate the abs_veto SHORT direction: "
      "REFUTED'.",
      "The shadow book says short is the STRONGER side. If that inverts for three consecutive "
      "weeks, revisit the per-side thresholds — still not the direction.",
      "no-op", "Both sides, as now.", "Unchanged.",
      "n/a — this play is an instruction not to act.",
      "Shadow: short +$2,651 vs long +$1,371, and +$15.50 vs +$8.02 per trade. The side proposed "
      "for relegation is the better one.",
      "Garrath — gate_switches.env", "n/a — nothing changes."),

    # ══════════════════════════════════════ BUILD ════════════════════════════════════
    P("exh-wide-stop-exit-shadow", "BUILD", 1,
      "Shadow-slate the exhaustion_short wide-stop exit",
      "SHADOW",
      "Run the gate's live entries through a 1.5×ATR stop with a far target and a time cap, in the "
      "shadow book, alongside the live scalp exit. No live change.",
      "Every treatment aimed at this gate's ENTRY failed against a placebo — cooldowns, "
      "streak-benches and a tighter flow floor all lose to random. The entry is not the problem. "
      "Under a wide-stop exit the same entries beat 60 of 60 random-entry controls; under the live "
      "scalp exit they land at the 47th percentile, i.e. indistinguishable from firing at random. "
      "The edge is invisible at the exit the desk uses.",
      "Part 1.5 §7 — the exit sweep, its random-entry control and the day-by-day.",
      "Worst leave-one-day-out +$1,626.49, strip-best-3 +$2,046.14, 9 of 12 days green, and "
      "+$397.26 on this week's four testable days. Shadow it because the sweep never turns over "
      "(the best cell is at the grid boundary) and the repricer takes no slippage.",
      "shadow-first", "Same entries as the live gate — this changes only the exit.",
      "Stop 1.5×ATR, far target, 15-minute cap.",
      "The shadow arm fails to beat the live arm over 40 shadow trades, or its fills show the "
      "slippage the repricer assumed away.",
      "+$3,459.98 against −$84.50 live on the same 87 signals. Entry alpha $3,467.78 at the 100th "
      "percentile of 60 random-entry draws.",
      "Garrath — shadow slate", "Remove the slate; it never touched live money."),

    P("open-news-cluster-hunt", "BUILD", 2,
      "Run the OPEN/NEWS cluster greenfield hunt first next week",
      "PARKED",
      "Schedule the OPEN/NEWS greenfield hunt at the FRONT of the queue, ahead of any further gold "
      "work.",
      "It is the largest addressable block of missed runs and no gate on this desk has ever been "
      "built for it. It was scheduled this week, sat fifth in the queue, and the queue ran out.",
      "Movement 3 §8 and its disposition — 'MNQ OPEN/NEWS-cluster greenfield hunt: NOT RUN'.",
      "The hunt itself is the test. A null is an acceptable outcome; not running it is not.",
      "build", "n/a", "n/a",
      "n/a — this is a scheduling decision.",
      "22 of this week's 68 runs, roughly a third of an $8,024 single-lot ceiling, never hunted.",
      "Garrath — friday_phases.py phase order",
      "n/a — reordering a queue."),

    P("router-leakage-universe", "BUILD", 3,
      "Widen the router's leakage detector to every fader it could manage",
      "PARKED",
      "Extend the leakage detector's universe beyond capitulation_long and rgv_short so it can see "
      "losses on gates the router is not currently managing.",
      "A detector scoped to the gates that barely trade will report zero leakage on a week when "
      "money is leaking through a gate it was never pointed at. Zero leakage currently means an "
      "empty universe, not a clean week.",
      "Part 2.6 §3 — the leakage the detector cannot see.",
      "After the fix, re-run this week: it should report the −$241.00 it missed.",
      "build", "n/a — nightly instrument.", "n/a",
      "n/a — instrumentation.",
      "Reported zero leakage on all four visible days while −$241.00 leaked through a gate outside "
      "its universe.",
      "Garrath — scripts/router_nightly.py", "Restore the narrow universe."),

    P("dwell-time-spec", "BUILD", 4,
      "Specify a dwell time on the router's direction threshold",
      "SHADOW",
      "Design and shadow a minimum-dwell requirement before the router is allowed to flip direction, "
      "instead of flipping the moment the ±40pt threshold is crossed.",
      "Threshold hysteresis with no dwell lets the direction round-trip inside minutes when the "
      "measure is sitting on the line — the flip is decided by noise, not by a regime change.",
      "Part 1 §8.2 (churn) and Part 2.6's disposition row 'A dwell-time requirement: PARKED'.",
      "Score it on the week's actual flips: how many of the 36 would a dwell have suppressed, and "
      "what did those cost?",
      "shadow-first", "n/a — routing logic.", "n/a",
      "The churn measurement shows it cost real money and a dwell would not have caught it.",
      "36 flips this week, 78% of them produced no trade, 17 were under 30 minutes, and one round "
      "trip was decided by three points. ⚠ It cost $0 directly this week — this is a build because "
      "the mechanism is wrong, not because it is bleeding.",
      "Garrath — router direction rule", "Set dwell to zero."),

    P("mgc-shadow-slates", "BUILD", 5,
      "Put the two surviving gold gates in the shadow book",
      "SHADOW",
      "Shadow-slate the MGC day rider and the MGC coil bouncer. Neither goes live.",
      "Gold is a new instrument for this desk and both survived their own robustness checks, but "
      "neither has the sessions behind it to be judged.",
      "Part 2.5 Part A, findings 2 and 3, with their disposition rows.",
      "Day rider: 15 of 15 grid cells positive (+$552 to +$1,742) and it beats the best constant "
      "on both dollars and hit rate. Coil bouncer: n=154, median trade +$7.75, survives "
      "strip-best-day, beaten 0 of 12 by a same-count placebo.",
      "shadow-first", "Per each gate's own rule.", "Per each gate's own rule.",
      "Either fails to stay positive across 4 untouched weeks of shadow.",
      "MGC is $10.00 a point — every gold dollar here is already priced at the gold multiplier, "
      "not the Nasdaq one.",
      "Garrath — shadow slate", "Remove the slates."),

    P("signal-journal-block-reasons", "BUILD", 6,
      "Make signal_journal record WHY a signal was blocked",
      "PARKED",
      "Fix the write path so `suppressed_by` is actually populated.",
      "It is NULL in every row, so a blocked signal is indistinguishable from a taken one in the "
      "table. Every claim about what a gate WOULD have done unrouted is currently a reconstruction "
      "from the tape rather than a measurement.",
      "Part 1 §11 disposition — 'Signal journal block reasons: MEASUREMENT GAP'.",
      "After the fix, one day's journal should account for every bench with a named reason.",
      "build", "n/a", "n/a", "n/a — instrumentation.",
      "NULL in all 222 rows this week. It is the same defect class the scope flagged last week, "
      "which means it was reported and not fixed.",
      "Garrath — signal journal write path", "n/a — restoring a NULL column helps nobody."),

    P("odr-preregistered-classifier", "BUILD", 7,
      "Pre-register ONE Open Rider day feature and leave it alone for 60 sessions",
      "PARKED",
      "Fix ATR-14 ≥ 9.5pt measured at 13:00 as the single day filter, in advance, and do not touch "
      "it for 60 forward sessions.",
      "The eight-feature search was beaten by 40% of pure-noise searches once the placebo was made "
      "search-aware. The only way to learn anything is to stop searching and commit to one rule.",
      "Part 2 §5 — 'ODR causal day-classifier: REFUTED as searched' and 'pre-registered single "
      "feature: PARKED'.",
      "60 untouched forward sessions. That is the test; there is no shortcut.",
      "build", "13:00Z daily read.", "n/a",
      "Fails to separate over 60 sessions — at which point the day-classifier idea is done.",
      "Best of 272 searched rules was beaten by 40.0% of noise searches. The pre-registration is "
      "the only remaining route.",
      "Garrath — day rider config", "Remove the filter."),

    P("nightly-rollup-backfill", "BUILD", 8,
      "Fix the nightly rollup's journal dependency",
      "PARKED",
      "Stop the nightly rollup silently reporting $0/$0/$0 when the systemd journal has rotated "
      "past the day it is backfilling.",
      "A rollup that cannot distinguish 'no value' from 'no data' will report a clean day on a day "
      "it could not see.",
      "Part 2.6 §3 disposition — 'Monday 08-10 nightly rollup: MEASUREMENT GAP'.",
      "Re-run 08-10 after the fix and confirm it either produces numbers or refuses.",
      "build", "n/a", "n/a", "n/a — instrumentation.",
      "The journal does not reach past 2026-08-10 23:11Z, so the backfilled file reads $0/$0/$0 "
      "because there was nothing to read — not because nothing happened.",
      "Garrath — scripts/router_nightly.py", "n/a"),

    P("capitulation-switch-writer", "BUILD", 9,
      "Find the other writer to gate_switches.env",
      "PARKED",
      "Identify what is writing capitulation_long back to ON. The router wrote it OFF five times "
      "and ON never, and the file reads ON.",
      "Something outside the router is editing the switch file. Until it is named, no bench "
      "decision on this desk can be trusted to stick.",
      "Part 1 §11 disposition — 'capitulation_long arm/bench tug-of-war: PARKED — unexplained'.",
      "Watch the file's mtime against the router's own decision log for one session.",
      "build", "n/a", "n/a", "n/a — this is a diagnosis.",
      "$0 cost this week, which is luck rather than safety. The gate traded twice for −$48.00.",
      "Garrath — gate_switches.env writers", "n/a"),

    P("stop-rate-meter-weight", "BUILD", 10,
      "Shadow a heavier weight on the STOP-RATE meter",
      "SHADOW",
      "Re-weight the untradeable-day meter to lean more on stop rate, in shadow, before touching "
      "the live cutoff.",
      "Of the three meters feeding the untradeable score, stop rate is the best discriminator and "
      "carries the least weight.",
      "Part 2.6 §5 — 'which of the three meters actually did the work'.",
      "$559/day separation is the number to beat. It is also the meter most obviously downstream "
      "of the desk's own behaviour, so shadow before deploy.",
      "shadow-first", "n/a", "n/a",
      "The re-weighted meter fails to beat the current one over 20 sessions.",
      "$559/day separation, the best of the three, and the lightest-weighted.",
      "Garrath — untradeable meter weights", "Restore the current weights."),

    # ══════════════════════════════════════ HOLD ═════════════════════════════════════
    P("stop-fill-fix-holds", "HOLD", 1,
      "The stop-fill fix — leave it entirely alone",
      "LIVE",
      "Nothing. It works.",
      "Resting stops are now placed on a concrete future rather than the continuous contract, so "
      "IBKR actually fires them.",
      "Part 1 §2.1 — 'the stop bug is dead, and I can prove it'.",
      "62 of 62 stops filled this week; 393 trades and 17 days since the last STOP_UNFILLED.",
      "no-op", "n/a", "n/a", "A single STOP_UNFILLED reopens it immediately.",
      "62/62 stops filled. This also means no number in this report needs a malfunction "
      "adjustment — every dollar lost is a strategy dollar.",
      "Garrath", "n/a"),

    P("arm-for-periods", "HOLD", 2,
      "Arm for PERIODS, not runs — and never bench on a count of losses",
      "LIVE",
      "Keep arming as a permission window. Do not add a wall-of-stops bench rule.",
      "A losing streak tells you the last two trades went badly; it does not predict the next "
      "signal. The discriminator is the REGIME the losses happened in.",
      "Part 1 §2.4 (live money) and Part 1.5 §3.2 (the mechanical test on 104 signals).",
      "Two independent populations agree. Fifteen versions of the bench rule were tested on "
      "exhaustion_short and every one lost, the best sitting at the 54th percentile of noise.",
      "no-op", "n/a", "n/a",
      "A regime-conditioned bench rule — not a loss-counting one — beats always-armed over a "
      "month.",
      "Bench-on-2-stops costs −$172 across this week and forfeits +$356 on Friday alone. "
      "Mechanically it cuts 18 winners to avoid 12 losers.",
      "Garrath", "n/a"),

    P("grind-atr-floor-22", "HOLD", 3,
      "grind_long's ATR floor at 22 — already deployed, and now confirmed",
      "LIVE",
      "Nothing. This is the confirmation of the 08-08 revert, not a new proposal.",
      "The floor stands the gate down when there is not enough range to pay for the trade.",
      "Movement 2 — 'grind_long ATR floor 10 → 22 (the 08-08 revert): LIVE'.",
      "On run tape the floor blocks four trades that all lose. It is doing its job.",
      "no-op", "n/a", "n/a", "n/a", "Already live. Do not re-propose it.",
      "Garrath", "n/a"),

    P("abs-veto-55s-holds", "HOLD", 4,
      "abs_veto_55s stays two-sided — already promoted",
      "LIVE",
      "Nothing. Promoted two-sided on 25 July; the battery re-confirms it.",
      "thrust_loose plus a 55-second continuation confirm, on both sides.",
      "Part 2 §2 — the full promotion battery.",
      "16 of 21 days green, positive in both regimes, both walk-forward halves and both sides.",
      "no-op", "n/a", "n/a", "Three consecutive red weeks on either side.",
      "Already live. On the card only so nobody re-promotes it as new.",
      "Garrath", "n/a"),

    P("router-thresholds-hold", "HOLD", 5,
      "Router ER ≥ 0.15 / |net| ≥ 30 — nothing to gain, leave them",
      "LIVE",
      "Nothing. The timing change (SATURDAY) is where the gain is; these levels are already right.",
      "The thresholds decide when a regime is declared; the timing decides how fast.",
      "Part 2.6 §4 — 'ER≥0.15 / |net|≥30 thresholds: LIVE — HOLD'.",
      "Best cell on both universes independently, and net 20–40 is a $13 plateau.",
      "no-op", "n/a", "n/a", "n/a", "A $13 plateau. There is nothing here.",
      "Garrath", "n/a"),

    P("untradeable-cutoff-65", "HOLD", 6,
      "The untradeable meter's 65 cutoff — mid-plateau, leave it",
      "LIVE",
      "Nothing.",
      "The meter scores how untradeable a day looks and 65 is the line.",
      "Part 2.6 §5 — 'The untradeable meter, and its 65 cutoff: LIVE — HOLD'.",
      "Monotone across 22 days (−$651 / −$212 / +$7 per day) and 50–75 all score identically.",
      "no-op", "n/a", "n/a", "The monotonicity breaks on a fresh 20 sessions.",
      "Cutoff sits mid-plateau. Moving it is motion, not improvement.",
      "Garrath", "n/a"),

    P("grind-exit-ledgers-hold", "HOLD", 7,
      "The two grind-exit shadow ledgers — keep watching, do not conclude",
      "SHADOW",
      "Nothing. Both remain UNMEASURED and that is the honest state.",
      "The two-ratchet runner-clip watch and the 2R-partial smoothness ledger both need grind to "
      "trade before they can say anything.",
      "Part 2 §6 and §7.",
      "No grind trades since 5 August; zero clips on three pre-August runners; green-day % is zero "
      "for both arms over the five days grind traded, so 'bank early' wins trivially on an all-red "
      "sample. None of that is evidence either way.",
      "no-op", "n/a", "n/a", "n/a — they are already suspended pending data.",
      "⚠ The two-ratchet tool has a −$406 cross-check error of its own. Fix before trusting it.",
      "Garrath", "n/a"),

    P("router-health-check-hold", "HOLD", 8,
      "The router blackout alarm — shipped this week, leave it",
      "LIVE",
      "Nothing.",
      "router_health_check.py alarms on a three-tick ABORT streak.",
      "Part 2.6 §5 disposition — 'The 08-13 10h20m OAuth outage: FIXED — NOT AN ACTION'.",
      "Live since 15:31Z on 13 August. The next outage is the test.",
      "no-op", "n/a", "n/a", "An outage passes undetected.",
      "The outage it was built for ran 10h20m across 125 consecutive aborted ticks and was "
      "indistinguishable from a calm day in every scoreboard.",
      "Garrath", "n/a"),

    # ══════════════════════════════════ NOT-AN-ACTION ════════════════════════════════
    P("na-er-floor-entry", "NOT-AN-ACTION", 1,
      "An entry efficiency floor at 0.10",
      "PARKED",
      "Do not ship it.",
      "Refuse entries when tape efficiency is below 0.10.",
      "Part 1 §9.1 — 'PARKED, killed by leave-one-day-out'.",
      "Killed twice: Tuesday carries 89% of the gain, and the winners test keeps only 7 of 25.",
      "no-op", "n/a", "n/a",
      "Revive if: three or more weeks of data and it still separates, AND it stops discarding "
      "two-thirds of the winners.",
      "Keeps 7 of 25 winners. That is the fake-filter signature.",
      "Garrath", "n/a"),

    P("na-break-even-stop", "NOT-AN-ACTION", 2,
      "A break-even stop at +8 to +15pt",
      "PARKED",
      "Do not ship it.",
      "Move the stop to break-even once a trade is 8–15 points onside.",
      "Part 1 §9.2 — 'PARKED, killed by applying it to the winners too'.",
      "It 'saves' $826 when you only apply it to the losers and costs $435 when you apply it to "
      "every lot, which is the only honest way to apply it.",
      "no-op", "n/a", "n/a",
      "Revive if: re-specified so it cannot be evaluated on losers alone.",
      "−$435 applied honestly. The +$826 was an artefact of the test, not a result.",
      "Garrath", "n/a"),

    P("na-abs-veto-atr16", "NOT-AN-ACTION", 3,
      "Restoring abs_veto_short's ATR ≥ 16 floor",
      "REFUTED",
      "Do not restore it.",
      "An ATR floor beneath the short side of abs_veto.",
      "Part 2 §10 disposition.",
      "Named test: score the entries the floor would block. They are +$233.50 over 38 shadow "
      "trades — the floor blocks winners. The timing fitted; the mechanism did not.",
      "no-op", "n/a", "n/a", "n/a — the entries it blocks make money.",
      "+$233.50 of blocked entries. Only two gates on this desk carry an ATR floor and this is not "
      "one of them.",
      "Garrath", "n/a"),

    P("na-grind-er-floor", "NOT-AN-ACTION", 4,
      "A grind ER-0.35 floor as an arming mechanism",
      "REFUTED",
      "Do not ship it.",
      "Arm grind_long only above an efficiency of 0.35.",
      "Part 2.5 Part B.",
      "Three named tests, all failed: the fake-filter guard (it keeps 1 of the 10 best trades), "
      "strip-3 (−$1,044) and the placebo (beaten by 18 of 400 shuffles' worth of noise).",
      "no-op", "n/a", "n/a",
      "n/a — keeping 1 of the 10 best trades is not a threshold problem.",
      "ER filters keep coming back and keep failing the same way. This is the third time.",
      "Garrath", "n/a"),

    P("na-grind-trend-confirm", "NOT-AN-ACTION", 5,
      "grind entry trend-confirmation (require a 15-minute impulse our way)",
      "REFUTED",
      "Do not ship it.",
      "Require a confirming 15-minute impulse before grind may enter.",
      "Part 2.5 Part B.",
      "Named tests: placebo (beaten by 391 of 400) and strip-3 (−$1,862). It fails for a reason "
      "rather than by luck — grind buys weakness, so demanding confirmation removes the entry.",
      "no-op", "n/a", "n/a",
      "n/a — the mechanism contradicts what the gate is for.",
      "Beaten by 391 of 400 shuffles.",
      "Garrath", "n/a"),

    P("na-exh-entry-treatments", "NOT-AN-ACTION", 6,
      "Cooldowns, streak-benches and a tighter net_min on exhaustion_short",
      "REFUTED",
      "Do not ship any of the three.",
      "Three separate proposals to fix a red gate at the ENTRY.",
      "Part 1.5 §3, §4 and §6 — the full candidate board.",
      "Named test on all three: a 4,000-draw random-removal placebo. Thirteen cooldown cells and "
      "fifteen bench cells are all negative with a best of the 54th percentile. The net_min 'win' "
      "is a calendar artefact — the live floor is ALREADY 400, every higher floor is worse, the "
      "correlation between flow and outcome is r=0.059, and 12 of the 17 signals the winning floor "
      "cuts come from a single era.",
      "no-op", "n/a", "n/a",
      "n/a — the entry was never the problem. See BUILD #1 for what is.",
      "Not one of 20 treatments clears a 95th-percentile placebo. Best is 85th, and that one is the "
      "calendar artefact.",
      "Garrath", "n/a"),

    P("na-exit-fixes-thrust", "NOT-AN-ACTION", 7,
      "Exit tuning for the thrust family",
      "REFUTED",
      "Do not spend another night on it.",
      "Sweep the thrust family's exits to rescue it on chop days.",
      "Part 2 §8 disposition.",
      "Named test: all 58 policies span −$39.4 to −$40.6 per signal on SCALP-CHOP. The spread "
      "across every exit ever tried is about a dollar.",
      "no-op", "n/a", "n/a",
      "n/a — no exit rescues an un-vetoed thrust in chop. The veto is the fix and it is already "
      "live.",
      "58 policies, $1.20 of spread between the best and the worst.",
      "Garrath", "n/a"),

    P("na-router-cutoff-35", "NOT-AN-ACTION", 8,
      "Moving the untradeable cutoff to 35",
      "REFUTED",
      "Do not move it, even though leave-one-out picks 35 in 17 of 22 folds.",
      "Lower the untradeable cutoff so more days are refused.",
      "Part 2.6 §5 disposition.",
      "Named test: base-rate contamination. Post-15:00Z trading lost −$1,712 across all 22 days, so "
      "ANY rule that switches the desk off in the afternoon scores well — including rules with no "
      "information in them. The fold vote is measuring the time of day.",
      "no-op", "n/a", "n/a",
      "n/a — this is the most instructive kill in the report: a 17-of-22 fold majority that means "
      "nothing.",
      "−$1,712 of afternoon base rate masquerading as a cutoff result.",
      "Garrath", "n/a"),

    P("na-adaptive-exit-selector", "NOT-AN-ACTION", 9,
      "The adaptive exit selector",
      "PARKED",
      "Do not act on its picks.",
      "Choose the exit per trade from three candidates.",
      "Part 2.6 §5 disposition.",
      "It lost to fixed always-SCALP on 4 of 5 days and by $1,267 on the week, with 59% optimal "
      "picks.",
      "no-op", "n/a", "n/a",
      "Revive after the data_quality fix (SATURDAY #3) — its regret numbers are computed by the "
      "same job that was counting quarantined trades.",
      "−$1,267 on the week against doing the simplest possible thing.",
      "Garrath", "n/a"),

    P("na-mgc-depletion-break", "NOT-AN-ACTION", 10,
      "The MGC far-side-depletion BREAK gate",
      "REFUTED",
      "Do not build it. The interesting part is that it is backwards.",
      "Buy the gold break when the order book ahead of it is empty.",
      "Movement 3 §2 and §9.",
      "Named test: a 2,000-draw random-subset placebo on n=192. It loses −$2,059.50 at the 4.8th "
      "percentile — 1,904 of 2,000 random picks did BETTER. The feature carries real information "
      "and the sign is inverted: on gold, a level that breaks into a vacuum is one nobody is "
      "defending, and price comes straight back.",
      "no-op", "n/a", "n/a",
      "The FADE reformulation is PARKED and worth one night: build it as a fade with its own entry "
      "timing and stop and test on a held-out window. An inverted backtest is a hypothesis, not a "
      "result.",
      "−$2,059.50 at the 4.8th percentile. Also: no exit rescues it — median MFE +3.28 ATR against "
      "median MAE −3.04 ATR, with 80.4% going a full ATR against us first.",
      "Garrath", "n/a"),

    P("na-size-escalation-gold", "NOT-AN-ACTION", 11,
      "Narrowing the gold hunt to the biggest moves",
      "REFUTED",
      "Do not narrow further — it goes the wrong way.",
      "The standing escalation: if nothing works on the full census, hunt the top 25, then the top "
      "15.",
      "Movement 3 §4.",
      "Named test: re-running all 20 filters at each narrowing. The top-25 best cell is three "
      "prints (strip-3 −$212.50); at the top 15 every single rule is negative and the best loses "
      "−$54.00.",
      "no-op", "n/a", "n/a",
      "n/a for gold breaks. The escalation itself remains the right method — it is this population "
      "that has no footprint in its monsters.",
      "The footprint gets worse as the moves get bigger, which is the opposite of the premise.",
      "Garrath", "n/a"),

    P("na-better-exit-caught-misses", "NOT-AN-ACTION", 12,
      "“A better exit would have caught the runs we missed”",
      "REFUTED",
      "Stop proposing it.",
      "The recurring claim that the idle-gate null is an exit problem.",
      "Movement 2 — the timing-decay ladder.",
      "Named test: n=57 at every rung, tick-honest, on this week's tape. Perfect entries decay from "
      "+$3,799 at the ignition minute to −$1,073 seven minutes later. Our gates fire late; no exit "
      "fixes being late.",
      "no-op", "n/a", "n/a",
      "n/a — the finding is that we are late, not that we leave badly.",
      "+$66.60 per run at zero lead, +$6.80 at five minutes, −$18.80 at seven. Every minute of "
      "confirmation costs real money.",
      "Garrath", "n/a"),

    P("na-relegate-rgv-short", "NOT-AN-ACTION", 13,
      "Relegating any gate's short side",
      "REFUTED",
      "Never relegate a direction.",
      "The standing temptation to switch off whichever side lost this week.",
      "Part 2 §4, and the same finding in Part 1.",
      "The shadow book says the side proposed for relegation is the stronger one: +$2,651 against "
      "+$1,371, and +$15.50 against +$8.02 per trade.",
      "no-op", "n/a", "n/a",
      "n/a — a gate runs two-sided with independently-tuned per-side thresholds. Tune the side.",
      "This is on the card every week because it gets proposed every week.",
      "Garrath", "n/a"),
]


def main():
    ids = [p["id"] for p in PLAYS]
    assert len(ids) == len(set(ids)), "duplicate play id"
    for w in ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION"):
        ranks = sorted(p["rank"] for p in PLAYS if p["window"] == w)
        assert ranks == list(range(1, len(ranks) + 1)), f"{w} ranks are not 1..n: {ranks}"
    pathlib.Path(OUT).write_text(json.dumps(PLAYS, indent=1))
    print(f"wrote {OUT} — {len(PLAYS)} plays")
    for w in ("SATURDAY", "MONDAY", "BUILD", "HOLD", "NOT-AN-ACTION"):
        print(f"  {w:<14} {sum(1 for p in PLAYS if p['window'] == w)}")


if __name__ == "__main__":
    main()
