# PROJECT: $800 A DAY ON THE HOLDOUT

> **The bar, in his words:** *"success for 4 lot trades looks like consistent daily averages of $800
> plus. do not come back to me saying we are complete until this is achieved. you can ping me updates
> saying we are running at $350 a day average, we are up to $480 a day average etc. but success in
> this project is $800 a day."*

---

## 1. THE DEFINITION OF DONE

**$800/day average, at 4 lots, measured on HELD-OUT weeks.**

$800 ÷ (4 lots × $2.00/pt) = **100 points net a day.** For scale: his own two best days captured
185pt and 193pt of available leg movement, so the bar is roughly half a good day of his, sustained.
Reachable, and not trivially.

### ⚠⚠⚠ THE AMENDMENT THAT MAKES THE BAR MEAN ANYTHING
**It is measured ONLY on weeks the loop has never trained on and never reviewed.** A target plus a
"do not stop until you hit it" instruction is the exact pressure that manufactures a fake result,
and this desk has four of mine from 2026-10-02/03 alone:

| the fake result | what it actually was |
|---|---|
| 866 winners from 866 trades | read the leg's peak from the future |
| +$1,287/day, 98 winning sessions from 100 | the same, without the break |
| "the CLAIM call works, 9.1pt separation" | 668 calls that were 62 episodes |
| "+10.8pp, CI excludes zero, holdout agrees" | a window-boundary artefact; shift the start and it is +0.4pp |

Every one came from reaching for a number. So the number lives on data that cannot be reached for.

**HELD OUT PERMANENTLY — never trained, never reviewed:**
- **14-18 Sep** (deliberately: it holds his two best days, +$1,478 and +$1,546)
- **17-21 Aug**

**TRAIN POOL — 8 weeks, a different one each iteration:** 27 Jul · 3 Aug · 10 Aug · 24 Aug ·
31 Aug · 7 Sep · 21 Sep · 28 Sep.

### THE SECOND STOPPING CONDITION, IN THE OTHER DIRECTION
If **6 consecutive iterations** pass with no holdout improvement, that is a **result** and it gets
reported. "We could not get there, and here is the curve" is information he needs; grinding silently
is not. Silence must never be able to mean either success or failure.

---

### THE MILESTONE, WHICH IS NOT THE BAR
> *"if we can get it up to 5-600 this weekend thats a bloody good start for monday. then we keep
> improving on live paper trading."*

**$500-600/day on the holdout = a good weekend's work and a defensible Monday starting point.**
It is a MILESTONE, not success, and the two must never be reported as the same thing. $800 is the
bar; anything under it gets reported as a number with the word "running at", never "complete".
★ And the real path is longer than the weekend: this converges on live paper trading, where the
evidence accrues one session a day and cannot be re-run. The weekend's job is to arrive at Monday
with something worth putting in front of the tape, not to finish.

⚠ 2-3 weeks stay out for the FINAL FORWARD TEST and are never touched by any iteration — currently
2 (14-18 Sep, 17-21 Aug), which is the low end of what he asked for and is kept at 2 deliberately
because the loop is already running on that split and a holdout that changes mid-run makes the
curve meaningless.

## 2. THE PROGRESS PROTOCOL

Ping on:
- **a new best holdout daily average** ("running at $350/day", "up to $480/day")
- **the bar being cleared** — and only then may the word "complete" be used
- **6 flat iterations** — the negative result
- **anything that invalidates earlier work**, immediately, because every significant finding of
  2026-10-03 came from a premise being questioned rather than from more measurement

★★ AMENDED 2026-10-03 — HE LIFTED HIS OWN NO-PROGRESS-PINGS RULE FOR THIS PROJECT:
> *"can you ping me a quick 2 line progress each time agents come back and your fine tuning? maybe
> more than 2 lines. just so i dont get tempted to ask you all the time how its going!"*
So: **ping on every iteration completion and every agent return** — holdout average, the three
behavioural metrics against their bars, the trend against the previous iteration, and one line on
what changed. ⚠ CLAUDE.md's "FINAL DELIVERABLES ONLY: no progress pings; one message when done"
still governs **everything else on this desk**; it is lifted only here, and only because the
alternative is him asking every twenty minutes.

Still never ping: a training-week number AS PROGRESS. ⚠ A training figure is not
progress and reporting one as progress is the first step to believing it.

---

## 3. HOW SUCCESS IS SCORED — his method, not just P&L

All four, on the holdout:

| | bar | his own two best days |
|---|---|---|
| daily average | **≥ $800** | ~$1,500 |
| trades/day | 3–6 | 8 and 15 |
| side accuracy (on the dominant leg) | ≥ 0.75 | 7/8 and 13/15 |
| leg capture | ≥ 0.15 | 0.41 and 0.23 |

P&L alone would reward one lucky trade. ⚠ His trade counts run above the band on his best days —
the band comes from the other direction, the 23-entry day that lost $1,882.

---

## 4. WHAT IS KNOWN, SO NOTHING IS RE-DERIVED

**Settled and not to be retested**
- His entries are a **coin** on a symmetric race (+0.2pp side-matched, n=174). The money is in the
  asymmetric payoff — 4 lots, no stop, scale out — not in entry timing.
- He is a **continuation** trader joining a 15-min thrust (AUC 0.733 from presses, median +2.19 ATR
  from the book). He does not call turns.
- **Turn entries are a coin or negative** at every multiple, timeframe and target tested.
- `turn_watch` confirms **91-114 min late** with ~70% of the move gone, and locates a real turn 3.1%
  of the time against random's 9.4%. The fault is **confirmation lag**, not feature choice.
- **A bare stall is a coin** (three arms, independently).
- Hold-time gradient, clean fills, entry level: under-15min **−$47.89**, 15-60min **+$33.21**,
  1-4h **+$88.28**, over-4h **−$705.00**.

**The two interventions with real evidence, and both are vetoes**
- **Day veto:** no entry at ATR≥12 with ≥3 confirmed turns. All 19 such entries landed on losing
  days, −$176 each.
- **Against-the-line veto:** corroborated four independent ways (+$87 vs −$244 per entry).

**The single biggest lever found so far:** showing the model **the shape instead of the metrics**.
Monday went −$400 → **+$352** and 14 trades → 4 on that change alone.

---

## 5. THE OPEN LEAD — HIS CLAIM SIGNAL, AND I REMOVED THE MEASURE IT USES

> *"i always claimed when the cvd meter was at 100 and price was at 100 for a while together. you
> backtested that and it told me we were approaching exhaustion so i would claim when they both hit
> 100 for a while. more often than not it turned around. i would try backtesting that for your
> claims. not the new cvd % meter you built. the previous one based on 3 hour averages."*

**⚠⚠ THIS IS A DUAL PIN AND I HAVE NEVER TESTED IT.** What I measured on 2026-09-30 was a **LEFT**
pin on CVD alone — `cvd_pos` low — and found it a coin (+1.0pt/hr against a +1.8pt baseline). I then
rescaled the gauge away from that measure *because it pinned*. **He is telling me the pin is the
signal**, and specifically:

- **BOTH** gauges, not one: `px_pos` AND `cvd_pos`
- **at 100**, the top of their rolling ranges — not low
- **sustained** — "for a while together", not an instant
- and it is an **EXIT** signal, which is where every piece of measured evidence already points: his
  claim instinct beats his entry instinct (+19.9pp), his exits at a leg's end are his best cell
  (+$149/entry, 77%, n=30), and the hold-time gradient is the clearest edge in his book.

**It must be tested on the OLD meter** — session-cumulative CVD positioned within its **rolling
180-minute range**, which is what he was reading — not on the `press` % -of-volume gauge that
replaced it.

**And the verdict is an exit verdict, not a race:** given a position open, does claiming on the dual
pin beat holding? The incumbent is the 4-lot ladder, and matching it is refutation, not success.
