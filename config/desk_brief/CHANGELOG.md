# Desk Brief changelog (newest first)

The Desk Brief is what Claude reads on every live decision. Layers: strategy.md (the operator's instruction), the DESK MECHANICS block
(generated from scripts/hybrid_robot.py constants - never hand-written), experience.md (dated lessons with their study), and the LIVE
STATE block (computed per call). Rules: docs/CLAUDE.md "THE DESK BRIEF IS GOSPEL".

Every change to strategy.md or experience.md: bump the version line below, say what changed and why, cite the study. A change of
instruction (anything that could change WHAT Claude does) is replay-tested on unseen days before it goes live; a factual correction
(something that was simply untrue) may go live directly with the operator's go.

VERSION: D4

## D4 - 2026-10-27 - time left and the missing stop stop being reasons to wait (operator, live session 10-27)
First live morning on D3: 49/49 WAIT 02:00-06:00Z through a ~130pt down MIL. Reasons quoted "445 minutes before the US open a marginal
entry is not worth taking", "495 minutes of US-session exposure with no stop". D3's "little time before the US open" WAIT reason and the
LIVE STATE line ("US cash open in N min: an entry ... rides the US session") were read backwards: a LARGE N was treated as risk.
Operator: "We need to change something ... Way too cautious." Changes: LIVE STATE says PLENTY of time (>= 120 min, typical winner ~2h,
E112) or LITTLE time left; strategy states hours left are the best time to enter and that the missing stop / later US session are never by
themselves reasons to wait; experience line clarified (SHORT time left matters). An instruction change put live on the operator's order
WITHOUT the replay test the rule above asks for; replay A/B to follow (E124).

## D3 - 2026-10-26 - fixes from the second independent audit (E119)
One meaning of MIL everywhere (the detector's leg; the page's legs are "swings"), MIL start time in LIVE STATE; no quota framing of claims
(nothing shown at 0, "1 claim taken ... stops after 2", explicit "cap reached: no entry can be traded"; "before 04:00Z: no entry can be
traded now"); the base rate stated literally at its measured +37.5 target with the net (+$3,100 over 100), as the previous setup's record;
experience counts reconciled (8 of 100; 11 across all test arms); "old" dropped from the progress reason; the stop line follows the
venue-stop switch; the page's own record acknowledges the open trade (brief arms only).

## D2 - 2026-10-26 - fixes from the independent audit of D1 (E119)
Mandatory audit fixes: removed the freeze-inducing payoff wording ("erases five to fifteen", "waiting is never wrong", "room to +37.5") and
added the desk's base rate (88/100 hit, 8 lost > $1k); replaced the falsified WAIT list (biggest/fastest push, long/stretched, end of leg)
with the two the record supports (old leg no longer progressing; little time before 13:30Z) and kept the operator's dislike of buying tops
as a wish, not a diagnostic; LIVE STATE now shows the REAL desk book (trades, open position, realised+open P&L) and the page shows the
real position/record in brief arms; EXIT's real effect (operator text) + HOLD/EXIT guidance; veto stated in UTC per date; page header in
UTC; experience line 1 corrected (6-267pt at 13:30Z, all but one did most damage after); MIL defined, detector direction framed as a
filter; target/win templated from the robot; cap follows the one-day release switch; flat time/window from code; ordinal bug removed.

## D1 - 2026-10-26 - first Desk Brief (E119)
Replaces sim_week_recursive.BRIEF_V2 (2026-10-07) for the desk-brief arm only. Corrects four facts BRIEF_V2 got wrong for the live desk
(Claude's EXIT does not close the real position; the real position is not flattened at 13:30Z but rides to 20:40Z; the target is +37.5
all-out, not "take $200-300 when it tires"; re-entries are capped at 2 claims per MIL), states the operator's current objective
(consistency first, avoid entering at the end of a leg), and adds the desk's experience from E112-E118. NOT live until audited,
replay-tested and approved.
