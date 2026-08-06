---
name: vol-expansion-is-the-binding-leg
description: "The re-arm trio is break + ER-climb + VOL-EXPANSION, and vol is the leg that actually binds. A sustained ER climb on a compressed ATR (<~15) decays back to chop within ~20-35 min — it fooled two router ticks into arming in one session (2026-08-05), both times harmlessly, both times reverting on schedule."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 20d20fe8-b00d-478a-9a38-35782c5c05e3
  modified: 2026-08-06T11:21:19.249Z
---

**2026-08-05, two instances in one session, both 0-cost but both the same shape:**

- **20:00Z** — real structure (new session low 29602, 470pt range, net −198), last-hr ER 0.06→0.31. ATR 13→14; the tick's own word was "mild". Armed `abs_veto_short`. By **20:35** ER had decayed 0.33→0.23 and the tick benched it on its own carve-out. Never fired.
- **22:35Z** — fresh day high 29668, day-ER and last-hr ER 0.41 after climbing 0.08→0.28→0.37→0.41, roundtrip 0.80 one-way. **ATR 12pt.** Armed `grind_long`. By **22:55** ER had decayed 0.41→0.37→0.30→0.22→0.14 and 51% of the move was given back. Never fired.

- **2026-08-06 08:15Z** — `abs_veto_short` armed on "2.5-of-3, the half-point is weak vol expansion". **Benched 08:30**, break failed, price 58pt off the low. Never fired.
- **2026-08-06 11:05Z** — the strongest structure of the four: a decisive new day low 29380 (62pt through the prior low), day net −207, last-hr ER 0.41 sustained. ATR 10 on the router's measure. **Benched 11:20** — ER 0.38→0.25→0.21→0.15, price 86pt back off the low. Never fired. 15 minutes, the fastest decay yet.

**Four for four in ~15 hours, every one 0-cost, every one reverted inside 15–35 minutes.**

Both armings were defensible on break+ER and both reverted within 20–35 minutes. The common factor is the leg that was weak in each: **ATR was 10–14 against the ATR≥18 floor.**

**⚠ WHICH ATR — the desk has two and they disagree ~1.8x during exactly these conditions.**
`desk_view` (what the ROUTER reads) = mean per-minute range over a **trailing 60 min**, from 5s bars.
`router_watch` (the watcher) = same formula over a **trailing 14 min**, from raw ticks; its
`ATR_TREND_MIN` is also 18. At 11:07 on 08-06 they read **10 and 18** for the same instant. The
numbers in this memory are the ROUTER's 60-min measure. A 60-min trailing mean structurally lags a
fresh expansion, so it reports low ATR exactly when a break begins — which looks like the wrong
instrument for the job, and on 08-06 I nearly recommended changing it.
**Do not act on that yet.** The 11:05 case tested the two head-to-head — fast said arm (18≥18), slow
said don't (10<18), the break failed — but that is WEAK evidence, because a permanently-pessimistic
metric is trivially right on every failure. Judging the measures honestly needs their behaviour on
breaks that SUCCEEDED, not just the ones that died. Same selection trap as [[mfe-is-not-a-win-rate]].

**Why:** ER is a ratio — net displacement over path length. On a compressed tape a small directional drift produces a high ER cheaply, because the denominator is small. So low-ATR ER readings are structurally *easier* to print and structurally *less durable*: there is no vol to sustain the move, and it mean-reverts as soon as the drift stops. High ER on low ATR is therefore not a weak version of a trend, it is a different object. This is the exact MIRROR of the refinement banked on 07-31 from the other direction — elevated/expanding ATR alone in ER-0.08 chop is a whipsaw trap — and that entry said in terms: promote this to its own memory the first time it fools a tick into arming. It has now fooled two, in one session.

**Related structural artifact:** ER over any window straddling the 21:00–22:00 UTC CME halt is inflated, because the halt contributes zero path length. Every reopen prints a fake trend around 22:0x — on 08-05 the watcher fired REGIME→TREND ER(30m) 0.64 at 22:02 on ~2.5 minutes of actual tape. Discount any ER whose window has fewer minutes of ticks than the window claims.

**How to apply:** treat **vol expansion as necessary, not decorative** — do not arm aligned momentum on break+ER while ATR sits below ~18, however clean the ER and structure look. The cheap version of this rule: if the tick's own reason contains a hedge about ATR ("mild", "only Npt", "contracting"), that is the tell, and the correct action is to sit benched one more tick and let the ER prove it holds. The cost of waiting is a missed trade; the cost of arming is churn — and note both 08-05 cases cost $0 only because the gates found no setup, which is luck, not the rule working. Extends [[rearm-momentum-needs-er-climb-not-delta-blip]] (that one: ER must confirm delta; this one: vol must confirm ER). See also [[low-vol-grind-untradeable-stay-flat]], [[router-benching-lessons-0729]].
