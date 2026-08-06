---
name: intelligent-routing-not-blanket-benching
description: "Operator wants DYNAMIC intelligent routing, not blanket benching — arming is half the job; being flat through a window is a cost, not safety"
metadata:
  type: feedback
---

2026-08-04, operator, after I proposed defaulting to aggressive morning benching:
**"i dont want blanket benching all the time. it needs to be intelligent. if you can watch like i watch
with the smarts you have and turn things back on when we want them we are gold!"**

And earlier the same day, on the discipline he IS building: "i am loving our stay out until theres a
little window to claim $400. i am getting more patient around it."

**Why:** those two are not in tension, and I initially collapsed them into "bench more". The patience is
about not FORCING trades in chop. It is NOT a mandate to sit out — the value he wants is a router that
spots the window and turns things ON fast, which is the harder half and the reason a Claude router
exists at all rather than a threshold.

**How to apply:**
- **Arming is half the job.** Bench on EVIDENCE OF HARM; arm on EVIDENCE OF OPPORTUNITY. Neither is a
  default state; both need justifying.
- **Being flat through a window is a COST, not safety.** On 08-04 the router correctly identified a real
  break at 13:35 and declined anyway ("one hour is not n"), leaving the aligned trend-rider off for 17
  minutes of the day's best move. The operator had to prompt me. That is the failure mode to avoid.
- **SEGREGATE BY REGIME, always.** A chop-morning aggregate is not evidence about a trend afternoon.
  "Its full-day book is red" is not a reason to stay benched — see [[us-open-dont-bench-trend-rider]].
- **The intelligent middle exists:** when unsure a break is real, arm the ALIGNED gate and leave
  counter-trend gates and no-veto churners off. Say the uncertainty in the reason.
- The asymmetry (wrongly-armed churns / wrongly-benched merely misses) still applies to CHURNERS and
  COUNTER-TREND gates. It is NOT a licence to sit out a confirmed aligned window.

**Fixed in code, not just noted:** `scripts/router_tick_durable.py` carried **19 bench directives vs 13
arm**, and its only arm clause began with the word "only" — structurally a benching machine with one
grudging exception. Added a prominent ARM-side section (now 25 vs 21) with three concrete arm triggers.
The prompt's balance is worth re-checking whenever guidance accretes, since every incident tends to add
a bench rule and never an arm rule.

Related: [[some-days-stay-out-fully-flat]] (the genuine stay-out days — violent roundtrip chop, every
shadow red), [[us-open-dont-bench-trend-rider]], [[router-benching-lessons-0729]].
