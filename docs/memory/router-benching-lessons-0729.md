---
name: router-benching-lessons-0729
description: "Actionable LESSONS from Claude running the day-bias benching trial live 2026-07-29 (best day ever, +$638). What worked, the two mistakes to NEVER repeat, and how a permanent router should bench. Read before controlling gate benching / building the day-bias router feature."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fdd18525-f007-4dbb-8d0e-f435f4d4eca8
---

**From the 2026-07-29 router-tune trial (Claude owned `gate_switches.env`, day-bias benching, PAPER). Best day ever +$638.5.** These are the dos/don'ts so the next Claudio — and the permanent router — don't repeat the mistakes.

**✅ WHAT WORKED — bench the REVERSION faders against a DIRECTIONAL day.** On a firmly-down day, holding `rg_long`/`capitulation_long` benched all day avoided a **−$1,700 shadow bloodbath** (`rg_long` −932, `capit` −770). That's the trial's whole thesis and it's real: *the value is DEFENSE — not bleeding on the wrong side*, not making money. **Why:** and be honest — the +$638 headline was mostly the shorts + the operator's abs_veto_short re-enable (the +$705 scale-out), NOT my benching creating profit.

**❌ MISTAKE #1 — NEVER lump MOMENTUM longs with REVERSION longs in the bench.** I benched grind_long/abs_veto_long (momentum) together with rg_long/capit (reversion) on the day-bias-DOWN. But the afternoon up-bounces were a MOMENTUM-long setup — grind_long fired ~1972× / abs_veto_long ~1074× SUPPRESSED, wanting the move, muzzled. Reversion longs bled the down-day (−932); momentum longs would have RIDDEN the bounces. **RULE: bench by MECHANISM, not by side. Reversion faders → bench against the day trend. Momentum/trend gates → keep on the ALIGNED side (they self-protect via veto_counter_regime / abs-veto anyway).**

**❌ MISTAKE #2 — NEVER re-enable on a marginal flicker on a CHOP day.** I re-enabled the momentum longs on a +40 UP print with day-ER 0.00 (a complete round-trip chop), and it reversed to −150 one tick later → I re-benched. Textbook whipsaw. It cost nothing (they didn't fire) but on a live-firing day it bleeds. **RULE: require a REAL trend to flip a bench — day-ER rising (>~0.12) AND net decisively past the threshold AND the shadow confirming — not a threshold-edge flicker on a zero-ER day.**

**✅ CONFIRMED — SHADOW-FIRST beats the mechanical bias threshold, every time.** I kept shorts ON during UP flickers because their shadow stayed green; kept longs OFF during FLAT prints because their shadow was red. Deferring to the shadow (the counterfactual) over rules (1)-(3) was right at every fork. **The day-bias is the PRIOR; the shadow is the TRIGGER.**

**⚠ THE LIMIT — it's a DIRECTIONAL-DAY tool, NOT a chop tool.** Today was net-directional-down so it shone. On the chop round-trips (−690→+49→−150, ×4) it THRASHED (the scale-out debut −$166 whipsaw, my momentum-long whipsaw). Don't read a good directional day as "it works everywhere." On a zero-ER round-trip, bench momentum (rule 2) and mostly sit still.

**❌ MISTAKE #3 — DON'T become the mechanical router you're replacing (07-30, operator caught this live).** On a day that ran +200pt in the morning then chopped for 10h (day-ER 0.05), I kept a MOMENTUM long (`abs_veto_long`) on because (a) rule-4 "never bench aligned+green" and (b) rule-2's chop test needs net<40, which CAN'T fire when net is +200 off a morning move. But the gate's "green" was a FOSSIL — a banked morning tail lot (+199) masking a live scalp lot bleeding in the chop (+90→−7). Operator pattern-matched "momentum + chop = off" in 5 seconds while I rules-lawyered the thresholds. **RULES: (1) DECOMPOSE a gate's green into stale-banked-tail vs live-scalp — a high-water-mark from a dead regime is NOT a reason to keep firing. (2) In a CONFIRMED chop (sustained low ER + range-bound, regardless of day-net), bench ALL momentum — rule-2's net<40 is a poor gate (a big morning move locks it out); use the REGIME read, not the net threshold. (3) The trial exists to beat the mechanical router with GLOBAL judgment — if you find yourself citing a threshold against the obvious regime read, you've become the thing you're replacing.** NB: this was JUDGMENT not scan-frequency — I had the data for 3-4 ticks at 15-min; more frequent scans wouldn't have fixed a decision-rule miss.

**VERDICT for the permanent router:** keep the day-bias veto for the **reversion faders on directional days, with a $-threshold** — NOT the momentum gates, NOT chop. In chop: only REVERSION gates on (their shadow goes green), ALL momentum off. [[router-tune-trial]] [[loser-router-analysis]] [[direction-router-live]] [[dual-slot-scaleout-live]]
