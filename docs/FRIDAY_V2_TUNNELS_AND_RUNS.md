# FRIDAY REPORT — VERSION 2: TUNNELS AND RUNS

> **Scoped 2026-09-04 by operator instruction. First run: tonight, Fri 2026-09-04.**
> **V1 (`FRIDAY_V7_REPORT_SCOPE.md`) is FROZEN and still standing — this does not replace it.**
> V1 is the weekly desk review. **V2 is ONE QUESTION.** Do not merge them; a V1 phase must never be
> asked a V2 question, and V2 does not inherit V1's phase list.

---

## THE QUESTION, IN THE OPERATOR'S WORDS

> *"my new theory of tunnels and runs. compression and then run … all i want to know is how we can
> automatically pick the buy moment when the tape breaks out of the tunnel. and dont tell me it
> looks like every other spike. spikes come back down. the run runs up or down and continues. we
> basically need a floor and a ceiling on that current compression tunnel plus or minus 10%. when it
> breaks it we buy or sell. 10% might be 15% i dont know you tell me."*

**The deliverable is a RULE and a NUMBER, not a survey.** Specifically:
1. Can the break moment be picked **automatically**?
2. What is the buffer — 10%? 15%? of what? (Answer it; do not hand it back as a question.)
3. Does what follows **RUN**, or is it a spike that comes back?

---

## ★★★ WHY THIS IS NOT A RE-RUN OF THE TUNNEL WORK

The 2026-09-03 study concluded the break is worthless and **that conclusion stands on its own
terms** — direction 0.459/0.513/0.499 at ±1/1.5/2 ATR against a control of 0.494/0.498/0.497;
60-minute excursion 1.02x in ATR; 91% of breaks return inside the tunnel, median 3 minutes; and the
founding 1.75x claim was WITHDRAWN after nine hours in production.

**But every one of those numbers came from FIRST PASSAGE to a symmetric ±N ATR barrier — a stop and
a target.** It scores you out the moment the wobble touches the adverse barrier.

**The operator's framing has NO STOP.** There is no adverse barrier; you sit through the return. So:
- *"91% return inside the tunnel"* may be **irrelevant** rather than fatal — the old harness threw
  the runs away by stopping out on exactly the wobble he is saying to ignore.
- The statistic that matters is the **TERMINAL outcome under a time exit**, and the **drawdown you
  must tolerate** to reach it — not P(favourable barrier first).

⚠ **This is a genuinely different question, and the report must say so in those words** — so that a
future session does not read V2 as re-litigating a settled null, and does not read a V2 positive as
overturning the barrier result. **Both can be true at once.**

⚠ **AND THE PRIOR NULL IS NOT DISMISSED.** If the no-stop framing also comes back null, that is the
answer and it gets reported as the answer. [[never-kill-a-lead-that-has-a-glimmer]] cuts both ways:
every lead ends LIVE / SHADOW / PARKED / REFUTED, and "the operator likes it" is not a verdict.

---

## THE ONE CLUE ALREADY IN HAND, AND IT CUTS AGAINST INTUITION

The **highest** break-volume quartile had the **WORST** continuation (0.329 at ±1 ATR); MFE rose
across volume quartiles while MFE/MAE stayed ~1.0. **Heavy size at the edge looks like ABSORPTION,
not ignition** — the shape that killed AFC, which "fires LATE, buying exhaustion".
So *"it broke hard"* is probably the WRONG separator. The separator is more likely **what happened
to the resting book**: far side pulled and thin (ignition) vs hit and refilled (absorption).

Corroborated live on 2026-09-03 on the operator's own balance:
- **16:24Z close 0.75pt outside (0.08 ATR) — noise.** A close-outside rule fired and meant nothing.
- **16:25Z close 5.8pt outside (0.62 ATR) on 4,222 lots — the real one.**
**That is the buffer question, observed.** Hence: measure it, do not guess it.

---

## DATA — THE WHOLE LAKE (operator: *"use the whole data lake. we have heaps!!!"*)

| tier | what | span |
|---|---|---|
| **lake `1min`** — `gazbot7.lake.connect()` | the tunnel HMM's own tier | **MNQ 291 days** (2025-09-14→2026-08-18, 328,845 rows) · **MGC 320 days** (2025-07-27→2026-08-18, 357,692 rows) |
| lake `1day` / `1hour` | context | MNQ 483d / MGC 691d |
| `capture.db` bars 5s | bridges the lake to today | 07-15 → now (60-day retention) |
| **`depth.db` L2** | `depth_snap`, MNQ 5.46M / MGC 3.76M snapshots | **2026-08-07 → 2026-09-04, ~20 trading days — a PHYSICAL CEILING, not a choice** |
| `capture.db` ticks/quotes/book | aggressor + full book | **~5 trading days only** (per-table retention) |

⚠ **NEVER census `capture.db` alone** — it is pruned per table and a `--days 400` query against it
silently covers the hot tier while reporting as though it covered 400.
⚠ **Filter `symbol=` on EVERY query.** Folding MGC into an MNQ reader once made ATR read 1848
against a true 15 and opened live trades with $3,700 stops.

---

## METHOD — NON-NEGOTIABLE

- **Use the SHIPPED HMM. Do not refit.** `scripts/tunnel_watch.py`: MU=(1.636534, 2.682335),
  SD=(0.509254, 0.523180), A=((0.991211,0.008789),(0.008722,0.991278)), QUIET=0, on **log per-minute
  true range**. **FORWARD FILTER ONLY** — Viterbi/Baum-Welch re-label the past using the future,
  which is precisely the look-ahead that makes a backtest lie. Gold uses its own fit
  (`scripts/tunnel_fit_mgc.py`) — **2.5% of MGC minutes have a true range of exactly ZERO**.
- **Confirm on the CLOSE, and buffer it.** Buffer swept as **% of tunnel WIDTH** {0,5,10,15,20,25,30}
  AND in ATR multiples; report which parameterisation separates better.
- **★ RACE FROM THE END OF THE BREAK BAR.** Starting at the bar's own timestamp replays the decision
  minute — a look-ahead.
- **★★★ A CONTROL IS SUPPOSED TO LOSE.** Matched-hour control on every claim. Without it a positive
  number means nothing, and a P&L sort once put the no-flip control top of a kill pile.
- **OUT-OF-SAMPLE BY CONSTRUCTION.** Choose on the first 2/3 by time; report the last 1/3 untouched.
  **MGC is the independent replication** — a rule that works on one contract is probably fitted.
- **COSTS FROM THE MECHANISM.** MNQ **$1.50/RT** (never $5, never per side), **$2.00/point**.
  MGC **$10.00/point**; `MGC_FEE_RT = 4.50` mid-priced (crosses the 0.30pt spread ONCE = $3.00 +
  $1.50) or `1.50` where both legs are already crossed — **state which and why.** $7.50 taken from a
  report unchecked once killed a lead that was actually breakeven.
- **Never conclude from `ceiling_pnl`** — on identical trades it disagreed in SIGN with tick-repriced
  on 3 of 6 gates. **MFE is not a win rate.** **Report n everywhere; n<30 is not rankable.**
- **DuckDB `/` is FLOAT** — `(bar_ts/60)*60` is a silent no-op; use `bar_ts - (bar_ts % 60)`.

---

## SHAPE OF THE RUN — three phases, decided with the operator 2026-09-04

**A. CHARACTERISE** (full lake, MNQ + MGC): tunnels → buffered breaks → **terminal outcome with NO
STOP** at {15,30,60,120} min and to the flat; MFE and MAE-as-drawdown-tolerance; re-entry and whether
it still ended favourably. Then the **SEPARATOR**: what, measurable at or within ~2 min of the break,
picks the right tail — tunnel duration, width in ATR, edge touches, session block, break-bar volume
vs the tunnel's median minute, distance since the open, agreement with the day's net move.

**B. THE BOOK** (L2, ~20 days): does the resting book separate a run from a pop when the bars cannot?
Depletion vs absorption on the far side, imbalance and its change, spread behaviour, aggressor mix,
refill speed — each against a matched-hour non-break control. **Report the break COUNT and the power
first**; ~20 days yields few ≥25-minute tunnel breaks, and a confident number on n=12 is worse than
an honest "underpowered".

**C. SCORE THE LIVE RIG**: buy/sell the buffered break as the desk would actually trade it — 4 lots,
ladder $100/$200/$400/$600, **NO STOP**, 20:40Z hard flat, real fees. Phase A says whether the edge
exists; phase C says whether the current exits capture it. **Keeping them separate is the point** —
if C loses, A tells you whether the entry or the exit was at fault.

---

## HOW IT RUNS

The heavy analysis runs as **parallel agents in an interactive session** writing artifacts to
`reports/friday_v2/`, and the report assembles from those artifacts.
⚠ **NOT inside the Friday runner.** The box is 7.5GB and has taken three `global_oom` kills; V1's
serial runner deliberately has no `Workflow`/`Agent` in its allowlist because *"a sub-agent a phase
cannot spawn is memory it cannot consume"*. **Do not add agent fan-out to the V1 runner.**

**JUDGE ON THE ARTIFACT, NEVER THE EXIT CODE** — a V1 run once exited 0 having built nothing, and
another exited 0 with `artifact=MISSING` on a doubled brace.

---

## WHAT "DONE" LOOKS LIKE

A one-page answer at the top: **the buffer number, the entry rule, the measured terminal
distribution beside its control, and the verdict — LIVE / SHADOW / PARKED / REFUTED.**
Then the evidence. Then, explicitly: **what would refute this**, and **what could not be measured**.
