# Mid-week lead — 2026-08-06 · RUN STATE is the desk's primary regime discriminator

**Status: promising, mechanically sound, IN-SAMPLE. Not validated.** Built and shipped Thursday night
(`2cd59e2`). This document is the lead for Part 2.5 of the Friday report — re-derive every number
adversarially before it is written up as a finding.

## The operator's challenge that started it

> *"i am not convinced we are tuned correctly. we are basically benched the whole time... monday you let
> a couple rip later in the us session and we banked a few hundred. since then, very little. today there
> were several sizeable runs and you declined to arm."*

## What was actually measured

26 sizeable runs found in Mon 08-03 → Thu 08-06 from **raw 5s bars** (30-min window, |net| >= 80pt,
ER >= 0.35, extended while ER >= 0.30). Then every trade of the week — **taken AND missed** — bucketed by
whether it sat inside an *aligned* run. The 31,502 `SUPPRESSED-OPEN` log lines collapse to **260 distinct
missed-entry opportunities** (same gate, >120s gap = new episode); each was **raced target-vs-stop,
first-touch**, stop = 1x ATR-at-entry, so this is a race and NOT an MFE count.

|                    | TAKEN                          | MISSED (raced @2R, 1 lot)          |
|--------------------|--------------------------------|------------------------------------|
| **in-run aligned** | n=34 · 50% win · **+$10.34/tr**| n=61 · **67% win** · **+$2,141**   |
| in-run counter     | n=4 · 0% win · −$20.38/tr      | n=16 · 6% win · −$643              |
| **chop / no run**  | n=51 · 16% win · **−$28.43/tr**| n=183 · 27% win · **−$1,517**      |

**One variable — is a run in progress and is the gate aligned — explains essentially all of the P&L.**
A ~$39/trade spread that dwarfs gate, side and time-of-day.

## The verdict on the operator's challenge

**Half right, and the half he was wrong about matters.**

- **Right:** the desk sat completely flat through **18 of the week's 26 runs**, blocking **$2,141 (1 lot) /
  $4,283 (2 lot)** of aligned signal.
- **Wrong about Thursday specifically:** the cost was **Mon +$773, Tue +$707, Wed +$679, Thu −$18.**
  Thursday's three declined runs would have LOST money. It was a 445pt roundtrip wearing a trend's clothes.
- **Also right to keep benching in chop:** the 183 chop + 16 counter signals the router blocked would have
  lost **~$2,160**. Benching is not too aggressive in aggregate — it is INDISCRIMINATE.
- **Tuesday is the proof of concept:** the only green day (+$330.50) is the only day the desk was armed
  through two big runs (+$248 and +$192).

## Separated out — NOT a router problem (Friday rehab)

**Four runs produced ZERO signals from any gate** — 08-04 16:42, 17:16, 18:40 and 08-05 07:06,
totalling **+345pt of movement**. Arming would have changed nothing. That is gate mechanics.
Related: grind is a continuation-ON-PULLBACK gate and emits nothing at high VWAP extension — on 08-06 at
+6.6 ATR it logged zero suppressed opens for 30+ minutes while an [ACT] watcher demanded it be armed
five times.

## What shipped

`gazbot7/runstate.py` + `scripts/run_detect.py`, injected into `router_tick_durable.py` ABOVE the
untradeable meter, with the instruction that **when run-state and the meter disagree, run-state wins**
(the meter is a DAY aggregate — on 08-06 it read 87/100 STAY-OUT during a +297pt run).
**It reports state only and never flips a switch** — the arm/bench call stays with Claude.

Replayed live over the same week (recomputed each minute, trailing bars only, no look-ahead):

    detector says ARM   n= 20   65% win   +$729  (+$36.5/trade)
    detector says FLAT  n=240   33% win   -$747  (-$3.1/trade)

## What the Friday report must attack

1. **IN-SAMPLE.** Thresholds derived from the very week they score on. Placebo-test them: shuffle the run
   labels, and re-derive on a duty-matched random arming schedule. If the edge does not survive, say so.
2. **IT IS LATE.** A trailing 30-min window confirms a run only once most of it has happened — it captured
   **20 of 61** aligned entries (~34%). Study the shorter-window trade-off: earlier entry vs false starts.
   Do NOT just shrink the window because it scores better in-sample.
3. **THE EXITS EAT MOST OF IT.** Actual in-run trades made **$10.34/tr** against the raced **$35/tr**.
   Live exits captured under a third. The $4,283 headline is NOT achievable as stated — realistic recovery
   is ~$1,200–1,500. The gap is an exit problem, not a routing one.
4. **Strip-best-day:** does the finding survive removing Tuesday?
5. **The asymmetry rule.** Standing guidance is "wrongly benched is cheap, wrongly armed is expensive."
   This week says that is right in chop and expensive in runs. Quantify the inversion rather than asserting it.
