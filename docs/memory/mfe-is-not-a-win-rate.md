---
name: mfe-is-not-a-win-rate
description: "Reached X R" is a peak-excursion stat that ignores whether the stop came first — never use it as a win rate.
metadata:
  type: project
---

**Maximum favourable excursion answers "did price ever get there", not "did we win".** A trade can touch +1R and still stop out, because MFE ignores *ordering*. Treating one as the other inflates every number downstream.

This bit **twice on 2026-08-02**, in unrelated work:

1. **The capitulation rehab** justified flipping `require_flip` off and cutting to a 1.0R target with *"78% of bounces reach 1R vs ~40% reaching 2R."* Measured on that gate's own live entries against 250 ms ticks: "reached 1R" (MFE) = **14/14 = 100%**; actually hit **+1R before −1R** = **4/14 = 29%**. Breakeven at 1.0R target / 1.0×ATR stop is **50%**, so the config was structurally negative. Corroborated independently — the byte-identical shadow twin `capit_loose` is −$5,250 on 238 fires at 16.8% win, live gate −$122 on 24 at 37.5%. Nothing anywhere near 78%. It had already been shipped live; reverted same day.
2. **My own give-back grid** classified "round-trippers" using MFE over the full 120-min forward path instead of the actual holding period, counting peaks that occurred *after* the desk was already out. Round-trippers read **60%**; corrected to the hold window it was **20.6%** — which then reconciled with the independent study's 18.4%.

3. **A third time on 2026-08-03**, *after* this memory existed. Two `abs_veto_long` lots peaked at +34pt and stopped. I read the peak, saw it exceeded a corrected 29.1pt target, and told the operator the fix would have banked +$57. The race says otherwise: **−29.1pt came at minute 7, the +34pt peak at minute 11** — four minutes after we'd have been out. The real value of the fix was ~$61 of smaller stops, not a converted winner. Knowing the trap did not stop me walking into it, because I quoted the number before running the check.

**Why it's seductive:** MFE is trivially easy to compute from a price path (one `max()`), a real win rate needs a *race* — walk the path and see whether target or stop is touched first. The lazy version is always the bigger, happier number.

**★ The procedural rule, since knowing the principle demonstrably isn't enough:** never state a counterfactual P&L until the race has been *run*. Not "reached X so it would have banked" — walk the ticks, first-touch wins, print the minute each leg fired. If a claim starts "it got to +$N so...", that sentence is unfinished until there's a race behind it. Applies equally to my own analysis and to anything an agent hands me.

**How to apply:** any claim of the form "X% of trades reach N R" is a *ceiling*, never a win rate — challenge it on sight. Compute the race. And when measuring what a trade "gave back", bound MFE by the actual holding period; the forward path is only legitimate for a counterfactual exit that would still have been holding. Related: [[friday-findings-need-adversarial-rederivation]], [[exit-lab-paired-method-overstates]], [[shadow-sim-understates-losses]].
