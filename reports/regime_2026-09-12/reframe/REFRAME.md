# REFRAME THE PROBLEM ENTIRELY
### 2026-09-12 · Saturday · every number below is on disk in this directory

Brief: `ops/research_briefs/2026-09-12_reframe_the_problem_entirely.md` (+ its addendum).
Scripts and raw outputs `a1`–`a10` in this folder. Twelve things were tried; §9 lists them, the
discarded ones included. No service was touched, no gateway contacted (IBKR down for maintenance).

**Context, verified against the repo before anything else:** the desk has been **HALTED by human
decision since 2026-09-07 14:16Z** (`docs/STATE.md:9-23`, `desk_kill.json` active, `day_rider=off`,
all six gates off, venue flat and reconciled). `docs/STATE.md` is also **stale on P&L** — it carries
−$1,771.44 as of 09-04; `data/gazbot7.db` today reads **−$6,690.93** on the desk's own filter.

---

## 0. THE HONEST ANSWER, FIRST, IN PLAIN WORDS

**No. Trading MNQ intraday at ~19 trades a session with this account is not a winnable game — and
the reason is not that the edge is hard to find. It is that the edge, at the ceiling this desk's
own research says exists, cannot be distinguished from luck inside fourteen years.**

Arithmetic, not opinion (`a5_output.txt`):

| measured quantity | value | source |
|---|---|---|
| round-trip cost, MNQ | **1.25 pt = $2.50** | `a7_spread.txt` — median spread **0.50 pt ($1.00)** crossed once + `config.py:69 fee_rt=1.5` (0.75 pt). **Identical median in all four session buckets.** |
| gross edge ceiling, OHLCV signals | 1.05–1.50 pt | Mesfin (2026), established in the brief |
| per-trade dispersion, live gate roster | **33.2 pt (sd $66.39), n=667** | `gazbot7.db`, qty=1, `data_quality IS NULL` |
| trade rate | 19.4 / session | 872 booked trades / 45 sessions |

At a **1.50 pt** gross edge — the *top* of the ceiling — net edge is **+0.25 pt = $0.50/trade**
against a **$66** standard deviation. To show that at t=2 takes **70,525 trades = 14.4 years** at
this rate. At 1.05 and 1.25 pt expectancy is *negative* and no quantity of data helps.

The toll for playing, before any P&L at all:

| trades/session | friction per lot per year | % of a $30,000 account |
|---|---|---|
| **19.4 (actual)** | **$9,766** | **32.6 %** |
| 11 ("~11 signals/day") | $5,544 | 18.5 % |
| 1 | $504 | 1.7 % |

And the desk is not losing because it picks badly. Its clean, uncontaminated record says it picks
*slightly worse than nothing*: **−0.48 pt/trade gross of commission over 667 single-lot gate
trades**, 39.6 % win rate, avg win $62.26 / avg loss $44.85, median hold 3.0 minutes.

> ⚠ **Provenance of the "$30k" the brief and this report both use.** It is a **go-live target**
> from `docs/memory/golive-drop-mnq-mgc.md` (2026-06-14), **not a measured account balance** — no
> net-liquidation figure is persisted anywhere on disk. That memory's own conclusion was that
> **at $30k you should not trade MNQ live at all**: broker `whatIf` initial margins came back
> **MNQ $5,644, MGC $4,064, MES $2,895**, i.e. one of each is ~32 % of the account. The brief's
> premise "a $30k account trading MNQ" is, by this desk's own margin measurement, already a
> position the desk decided against.

**What is winnable with the same box, the same feeds and the same operator: a book whose unit of
decision is a DAY, held across the hours this desk refuses to hold, spread over several markets
instead of one.** §8 states it concretely enough to start on Monday, with the one thing that blocks
it. It is not a gold mine. It is positive-expectancy, which nothing intraday here currently is.

---

## 1. FRAMING A — **THE HOLDING PERIOD IS THE ONLY FREE VARIABLE** ★ rank 1 · verdict LIVE (as a constraint)

**(a) The idea.** Friction is a fixed toll paid once per decision. Edge is not fixed — it scales
with the size of the move you are trying to keep a piece of. Every study this desk has run tried to
raise the numerator. **The denominator is three hundred times more elastic.**

**(b) Evidence** — `a8_capture_ratio.txt`, 328,845 MNQ 1-min bars / 240 CME sessions.
*Break-even capture* = the fraction of the median available move a trade must keep to pay the broker:

| hold | median abs move | break-even capture, MNQ | MGC |
|---|---|---|---|
| 1 min | 3.50 pt | 35.7 % | 56.2 % |
| **3 min** ← gate roster's actual median hold | 6.00 pt | **20.8 %** | 32.1 % |
| 10 min | 11.25 pt | 11.1 % | 18.0 % |
| **46 min** ← day rider's actual median hold | 24.50 pt | **5.1 %** | 8.3 % |
| 60 min | 28.25 pt | 4.4 % | 7.3 % |
| 1 RTH day | 88.50 pt | **1.4 %** | 2.4 % |
| 1 CME day | 198.00 pt | **0.6 %** | 1.2 % |

The gate roster must keep **one point in five** of every move it catches, from an entry whose
direction its own five refutations score at 0.50. Move the identical coin-flip entry to a one-day
hold and the requirement falls to **one point in seventy**.

It also prices the instrument choice: at this desk's own cost constants (`levelbreak.py:54`
`MGC_FEE_RT = 4.50`, $10/pt) **MGC is ~1.6× more expensive than MNQ at every horizon.** Gold is the
worse contract here, not the diversifier it looks like.

**(c) Proper test.** None needed; it is measurement, not hypothesis. What needs testing is the
consequence — impose a minimum holding period as a hard slate constraint and re-score every gate.

**(d) Assessment. PROMISING AND FREE, and it is already whispering in the live record:** the gate
roster (median hold 3.0 min) is −0.48 pt/trade gross; the only part of the book with a positive
sign is the one holding 46 minutes. ⚠ The rider's *magnitude* is NOT a finding — see §7.
**Verdict: LIVE as a constraint.** Nothing enters a slate at a sub-10-minute median hold without
explicitly clearing this table.

---

## 2. FRAMING B — **THE DESK TRADES THE ONE WINDOW OF THE DAY WITH NO DRIFT AND HALF THE RISK** ★ rank 2 · verdict PARKED

**(a) The idea.** "Never hold overnight" is kept as a safety rule. Measured, it is a *position*: it
selects the slice of the 24-hour day where the index goes nowhere and shakes hardest.

**(b) Evidence.** Exchange clock (America/New_York; CME trade date 18:00→17:00), rolls neutralised.

> ⚠ **TWO OF MY OWN PASSES WERE WRONG AND ARE RECORDED AS WRONG.**
> **(i)** I first keyed the session off fixed *UTC* minutes. The CME day is 18:00–17:00 *local*, so
> 88 of 240 sessions started an hour later than my key assumed (`a1`/`a2`, superseded by `a3`).
> **(ii)** Worse: the lake picks its front month **per date by volume**, so a roll date books the
> whole carry basis as a one-minute price change. Nothing flags it and the two bars are one minute
> apart, so a time-gap filter does not catch it. `a10_output.txt`: **3 MNQ rolls worth +248.75,
> +232.25 and +654.00 points — and all three land inside the overnight window.** On MGC, 6 rolls
> worth +636.60 pt, one of them +496.00. **Every overnight number in my own first pass was inflated
> by its own contract rolls.** Everything below is roll-adjusted.

**MNQ, 240 sessions, 2025-09-15 → 2026-08-18. Roll-adjusted total +3,044.75 pt:**

| bucket | net pt (roll-adj) | % of all absolute movement | per-session t |
|---|---|---|---|
| ASIA 18:00–02:00 | +463.8 | 25.3 % | — |
| EU 02:00–09:30 | **+2,521.8** | 27.8 % | 1.20 |
| **US 09:30–16:00 ← the desk's window** | **−429.8** | **43.7 %** | **−0.11** |
| LATE 16:00–17:00 | +489.0 | 3.2 % | 0.48 |

**MGC, 272 sessions — it replicates on a different asset class:** US cash session **−456.2 pt
(−$4,562/lot)** against ASIA +212.3 (roll-adj) and EU +501.0, on a roll-adjusted total of +162.3.

Both instruments, independently: **the US cash session is where the contract falls, and where a
third to a half of all its movement happens.** The desk holds 27.9 % of the day's minutes and
43.7 % of its variance for a drift of **t = −0.11**.

**The overnight arm tested like a strategy** (buy 16:00 ET, sell 09:30 ET next trade date, friction
charged, day-block bootstrap of 5-session blocks × 20,000, sign-flip control):

| arm | n | net pt/session | sd | t | P1 / P2 / P3 | day-block 95 % CI ($/trade) |
|---|---|---|---|---|---|---|
| ONITE, as first computed | 239 | +19.65 | 234.5 | 1.30 | +31.1 / −3.5 / +31.5 | [−11.59, +94.06] |
| **ONITE, ROLL-CLEAN** | **236** | **+12.78** | — | **0.87** | — | — |
| INTRA (desk's window, long), roll-clean | 240 | **−0.59** | 247.5 | **−0.04** | −16.8 / +18.3 / −1.6 | [−61.45, +60.27] |
| HOLD24 | 239 | +15.78 | 344.4 | 0.71 | −3.5 / +41.0 / +9.8 | [−51.30, +108.16] |
| EUONLY | 239 | +8.08 | 144.1 | 0.87 | +3.4 / +10.6 / +10.3 | [−15.74, +44.33] |
| MGC ONITE, roll-clean | 265 | +2.87 ($28.67) | — | 0.74 | — | — |

**(d) Assessment — and this is where I refuse to give you the encouraging version.**
**The overnight arm FAILS the addendum's bar and fails it twice.** It clears zero at friction
(test a) and beats its sign-flipped control by 41.8 pt (test b), but its day-block CI **includes
zero** (test c fails) — and once its own contract rolls are removed, **a third of the arm's P&L
goes with them and t falls from 1.30 to 0.87.** Pairing MNQ with MGC does not rescue it: the two
overnight legs correlate **0.37**, so the pair's t is **1.31**, not 1.8 (`a4_output.txt`).
One year of data cannot separate a session premium from "the market went up in 2026."

**What IS established here, at high n and not weakly, is the negative half:** the desk's chosen
window has **no drift** (t = −0.11 over 240 sessions, replicated on gold) while carrying 43.7 % of
the variance. A directional strategy there must manufacture **100 %** of its return from timing
skill, because the tape contributes nothing. That is not a small finding — it means every intraday
study on this desk has been fishing in the one pool with no fish in it.

**Verdict: PARKED, with a named test** — §8 says exactly what would settle it, and why it cannot be
settled with the data this desk owns.

---

## 3. FRAMING C — **A LINEAR INSTRUMENT CANNOT HOLD A VARIANCE VIEW, AND THE DESK ALREADY RAN THAT EXPERIMENT 430 TIMES** ★ rank 3 · verdict REFUTED (futures) / MIS-SPECIFIED (options)

**(a) The idea.** The brief's central asymmetry — magnitude predictable (9 % → 77 %), sign not
(0.50 across five methods) — is a *volatility* view. A futures P&L is **linear** in displacement:
`P&L = q·(P_exit − P_entry)`. If `E[ΔP] = 0` then `E[P&L] = 0` for every `q`, however precisely you
know `E[|ΔP|]`. **A linear payoff cannot express a view on `|X|`.** There is exactly one way to get
convexity from a linear instrument — a *path-dependent rule* (stops, targets, trails, brackets) —
which synthesises optionality and pays for it in whipsaw plus one friction charge per re-entry.

**(b) Evidence.**
- **The desk has already run this experiment at industrial scale and it returned null: ~430 exit
  configurations across three chronological periods, 3 survivors — exactly what chance yields at
  that grid size** (established, brief). Those 430 configs *were* the convexity-manufacture
  experiment. That is the strongest single piece of evidence in this whole file, it has been on
  disk for weeks, and it was never read as a volatility result.
- The futures-only straddle (an OCO stop bracket) is dead before it is coded, from results already
  banked: break-then-join direction **0.469–0.506 over 24 cells / 239 sessions**
  ([[break-then-join-direction-is-a-coin]]); the tunnel study's founding excursion claim re-derived
  to **1.02× a matched control** ([[tunnel-structure-real-break-worthless]]). A bracket pays
  friction on the losing leg as well. **I deliberately did not re-run it** — it would have
  duplicated the tunnel study to reach a conclusion already banked.
- ★ **The options branch has a specification error nobody has stated in these words:** the magnitude
  forecast is built from **ATR and volume**, both public, both on every screen — which is precisely
  the information an option's implied volatility already contains. The forecast does not have to
  beat a coin; **it has to beat IV**, conditionally. The sibling literature lane reached the same
  place from the papers (`reports/regime_2026-09-12/literature/NOTES.md`): Almeida, Freire & Hizmeri
  (2025) find **all 0DTE strategies produce negative average returns** on 1,815 dates of SPXW
  bid/ask, with the variance risk premium **up to four times larger at the same-day horizon** — i.e.
  the horizon this desk forecasts is the single most expensive place in the market to buy vol.

**(d) Assessment. REFUTED for anything futures-only. The options branch is real but mis-specified
until it is scored against IV rather than against zero** — and on the current evidence the sign of
the premium is against the buyer.

---

## 4. FRAMING D — **THE EXECUTION-SIDE IDEAS ARE DEAD ON ARITHMETIC, NOT ON DIFFICULTY** ★ rank 4 · verdict REFUTED

**(a) The idea, from the brief:** "provide liquidity rather than take it", "capture the spread
instead of paying it".

**(b) Evidence** — `a7_spread.txt`, 131,730 sampled MNQ quotes from `capture.db`, 2026-09-06 →
2026-09-11 (the quotes table retains 5 trading days):

- Median MNQ spread is **0.50 pt = 2 ticks = $1.00**, not one tick. Only **17.3 %** of quotes are
  one tick wide. Mean 0.496, p90 0.75.
- **Median 0.50 pt in every session bucket** — Asia, Europe, US and the late hour alike. This is
  the measurement that validates the 1.25 pt constant the whole report rests on (0.50 crossed once
  + 0.75 commission), and it satisfies CLAUDE.md trap #2: the cost was re-derived from the
  mechanism rather than quoted.
- Median top-of-book depth: **4 contracts**.

A **perfect** market maker earns the full spread once per round turn: **$1.00 gross against $1.50
commission = −$0.50 per round turn**, before adverse selection, before queue position, and with a
median of 4 contracts at the touch so a retail resting order cannot see the front of its own queue.

**(d) Assessment. REFUTED — and this kill is independent of the one already on disk, which matters.**
The desk's existing kill ([[execution-cost-autopsy-stage1]], "passive-entry KILLED") **carries a
live retraction**: `STATE.md:170-171` says its "the desk bleeds DIRECTION not cost" conclusion
predates the fabricated-fill discovery and needs re-deriving. The arithmetic above does not depend
on that decomposition at all, so the conclusion survives the retraction. Two further constraints
already banked and worth not re-discovering: `regime-detector-impossible-passive-pivot` found the
passive edge to be **~100 % mirage** under realistic fills (adverse selection, not spread, is the
killer), and the OFI/Avellaneda-Stoikov route died at Phase 0 because **true tick-level L1 is not
capturable on IBKR retail** — `ticks.db` is a 250 ms poll of an L1 snapshot, not the event stream.

> **Footnote on the cost constant, for whoever inherits it.** `fills.commission` is **0.0 on all
> 1,802 rows** — IBKR paper reports no commission, so $1.50 is a constant applied downstream, never
> a broker figure. `reports/nightly/2026-09-11.md:15-17` cross-checked it against IB's own
> `realizedPNL` and found the desk's flat $1.50/lot is **~$0.28/lot conservative** (real ≈ $1.22),
> so true all-in is nearer **1.11 pt**. Every conclusion in this report is *stronger*, not weaker,
> at 1.11 pt — none of them flips. Also: the brief's addendum arithmetic ("1.25 pt = $1.50/RT + one
> 0.25 pt tick") does not add up; 0.75 + 0.25 = 1.00. The 1.25 figure needs the **0.50 pt median
> spread**, which is what `a7` measures.

---

## 5. FRAMING E — **THE OBJECTIVE IS WRONG: MINIMISE THE NUMBER OF DECISIONS, NOT THE LOSS PER TRADE** ★ rank 5 · verdict LIVE

**(a) The idea.** The desk optimises *per-trade* profit across ~19 decisions a session. Every number
in §0 says the binding constraint is the **count** of decisions: each costs a fixed $2.50 and
contributes a fixed $66 of noise. The objective should be *the fewest independent decisions that
still express the view*.

**(b) Evidence** — `a5_output.txt`:

| book | sd ÷ net edge | sessions to t=2 |
|---|---|---|
| gate roster at a hypothetical +0.25 pt net edge | 133× | 3,639 (14.4 yr) |
| MNQ overnight arm as measured | **11.9×** | 570 (2.3 yr) |

An **11× better edge-to-noise ratio** from doing one thing a day instead of nineteen. Note what that
does *not* say: **2.3 years is still not fast. There is no configuration of this desk in which an
edge is confirmed inside a quarter.** Any plan that requires knowing within three months whether it
works is a plan that cannot be executed here — and that has quietly been the shape of every Friday
cycle.

**(c) The human-in-the-loop corollary — the brief's direction 2, answered from this angle, with a
correction to the brief's own premise.**

The design *is* right in principle: machine enters and sizes, human only cuts. **But it is
unimplementable at 19 decisions a session**, because it needs the operator present and fast. The
desk already priced that: the Claim button's latency alone was worth **$48 a press** at up to 60 s
of delay ([[a-buttons-latency-is-part-of-its-price]]), which is why the inotify fast path exists.
At one decision per market per day the same human skill needs **no speed and no fast path at all**.
The slow book is not a different idea from the human-in-the-loop idea; **it is the only holding
period at which the human-in-the-loop idea can be built.**

> ⚠ **CORRECTION TO THE BRIEF.** The brief states the manual-exit asymmetry as established:
> "+$65.70/lot (n=80, t=2.28)". Verified tonight against the repo: **that result is not in the repo
> at all** — it exists only in a session transcript from 2026-09-11, with its scripts surviving in a
> scratchpad. More importantly, **40 of its 41 manual positions are exactly 4 lots**, i.e. the
> sample is ~100 % the multi-lot population that `STATE.md:167` and CLAUDE.md trap #13 say cannot
> be ranked; it is rescued by a *ceiling* price reconstruction whose own author wrote "truth is
> between −$2,742 and −$225". Its two component legs are individually insignificant (rider t=1.78,
> tournament t=1.52), the two halves are not even computed the same way (one booked, one
> de-fabricated), and its own verdict line reads *"REAL but SUPERSEDED… n=80 of 120 needed."*
> Meanwhile the **full-population** census of that exit reason is **`MANUAL_CLAIM` n=105, 189 lots,
> −$1,902.31 = −$10.07/lot.**
> **Treat "the operator's hand is the edge" as an open question, not a premise.** The *direction* of
> the argument above does not depend on it — it depends on the entries being no better than random,
> which is separately measured (41 % go his way first).

**(d) Assessment. PROMISING, and the cheapest change on the list.** It costs nothing and it is the
only lever that improves both terms of the ratio at once.

---

## 6. FRAMING F — **WHAT THE DESK IS ACTUALLY GOOD AT, AND THE ONE THING WRONG WITH IT** ★ rank 6 · verdict LIVE — fix first

**(a) The idea.** The ten-agent audit valued the measurement estate at ~1000:1 against the data.
Measured today, **the measurement estate has a hole in it large enough to have swallowed the desk's
entire booked loss.**

**(b) Evidence** — `a5_output.txt`, `a6_output.txt`, `gazbot7.db`, 2026-07-16 → 2026-09-11:

| slice | n | lots | net P&L |
|---|---|---|---|
| ALL booked trades | 872 | 1,091 | **−$6,690.93** |
| qty = 1 (uncontaminated) | 712 | 712 | **+$1,835.26** |
| qty > 1 (**fabricated fill prices**) | 160 | 379 | **−$8,526.19** |

Every lot beyond the first on a multi-lot order is filled by the IBKR paper engine at a *constant*
0.1 % adverse price that never printed ([[paper-fills-fabricate-a-0-1-percent-adverse-price]];
21/21 rider orders at 0.09897–0.09998 %). **160 of 872 booked trades — 18 % of trades, 35 % of lots
— are not measurements.** The desk's headline P&L is a number about the simulator.

**And the trap inside the trap, found tonight** (`a6_output.txt`): filtering to `qty=1` **does not
clean the rider.** Its 45 single-lot rows resolve to **only 20 distinct `opened_at` timestamps** —
ten pairs and five quads. They are *fragments of larger positions*, so they carry the same
fabricated prices and are not independent observations. **The "+$3,472 / +39.3 pt per trade" that
the rider shows under that filter is an artefact and I am not reporting it as a result.** n_eff=20.

What survives cleanly: the **667 single-lot gate trades, −$1,637 net, −$636.50 gross of commission,
−0.48 pt/trade.** That is the only honest performance number this desk owns, and it is negative
*before* costs.

**(d) Assessment. Not a framing — a blocking defect.** Five research threads ran tonight and some
will rank on P&L. Any ranking including a multi-lot order is contaminated (trap #13) — and, new
tonight, **any ranking that de-contaminates by filtering `qty=1` is still contaminated for the
rider.** The fix is to key on `opened_at` / order id, never on `qty`. **Verdict: LIVE — fix before
the next Friday report**, and re-state every live P&L number in the repo afterwards.

---

## 7. WHAT I AM *NOT* CLAIMING

- I am **not** claiming the overnight session has an edge. Roll-clean t = 0.87. §2.
- I am **not** claiming the rider is profitable. Its clean sample is n_eff = 20 and contaminated. §6.
- I am **not** claiming the operator's hand is the edge. That premise does not survive verification. §5.
- I am **not** claiming a slow diversified book will make money. I am claiming it is the only design
  on the table whose *signal-to-noise ratio is measurable at all*, which is a prerequisite, not a
  promise. Managed-futures books have run Sharpe ~0.3–0.5 live since 2010; that is the realistic
  ceiling, not a rescue.

---

## 8. THE NEAREST WINNABLE GAME, CONCRETELY, AND WHAT BLOCKS IT ON MONDAY

> **A small, diversified, slow futures book: one decision per market per day, held through the hours
> this desk currently refuses to hold, across 6–10 micro contracts instead of one.**

Why this, with the numbers already on the table:

1. **The horizon does the work.** §1: break-even capture falls from 20.8 % at a 3-minute hold to
   0.6 % at a one-day hold; friction falls from **32.6 % of the account per year to 1.7 %**. You
   stop needing an edge that does not exist.
2. **Account size does not change intraday economics at all.** In futures, friction *and* P&L both
   scale with lots, so the ratio in §0 is **invariant to capital**. More money would not fix the
   current desk. What capital buys is **breadth**.
3. **Breadth is the only lever never pulled.** Everything tried has raised the numerator on one
   market. n independent bets improve t by √n; this desk has n = 1. The measured MNQ/MGC overnight
   correlation of **0.37** shows how little *two* markets buy — which is the argument for eight.
4. **The operator's one plausible skill survives the move, and only survives the move.** §5(c).
5. ⚠ **But margin is the honest constraint, and it is tight.** This desk's own broker `whatIf`
   measurements (`golive-drop-mnq-mgc.md`): **MNQ $5,644 · MGC $4,064 · MES $2,895** initial. A
   $30k account carries roughly **6–8 one-lot micro positions fully margined, with no spare** — and
   MNQ itself is among the most expensive of them. A real version of this book starts at **4–5
   markets, one lot each, deliberately under-deployed**, and the memory's own advice — **prefer MES
   to MNQ** — should be taken.

### ★ THE BLOCKER, and it is neither ideas nor compute

`a9_data_ceiling.txt`, audited across all 29 daily parquets: **the longest daily series this desk
owns is 483 bars (1.9 years) for MNQ and 671 (2.6 years) for MGC, on CONTFUT continuations only.**
CLAUDE.md already records why — asking IBKR for 15Y and 5Y returns the *same* 482 daily bars; the
limit is **entitlement, not runtime**. A slow, diversified book needs 15–30 years across 8–12
markets to be tested **at all**. **Every long-horizon framing in this report is currently
untestable, and no quantity of agent-hours changes that.**

### MONDAY, IN ORDER

1. **Get the data.** Non-IBKR daily futures history — 8–12 liquid micro-tradeable markets (equity
   index, rates, metals, energy, FX), 20+ years, roll-adjusted. This is an afternoon's work and it
   unblocks everything above. Until it exists, stop commissioning long-horizon research.
2. **Fix the measurement hole** (§6): de-contaminate by order id, not `qty`. Re-state every live
   P&L number in the repo. Rank nothing on P&L until this is done.
3. **Impose the horizon constraint** (§1) on the slate: no gate below a 10-minute median hold
   without explicitly clearing the break-even-capture table.
4. **Then** score a slow book out-of-sample on the new history, and settle §2's overnight question
   on twenty years instead of one — **with rolls neutralised**, which §2 shows is worth a third of
   the answer.

### WHAT I AM NOT SAYING

Not "stop". The machinery here — the router, the reconciler, the capture estate, the adversarial
Friday cycle, the memory files that caught two of my own errors tonight before they reached you —
is genuinely good machinery **pointed at a problem its own instruments cannot resolve**. Point the
same machinery at one decision a day across eight markets and the instruments start working,
because the signal-to-noise ratio improves by an order of magnitude before anyone has a new idea.

---

## 9. EVERYTHING TRIED TONIGHT, INCLUDING WHAT FAILED

| # | thing | outcome |
|---|---|---|
| 1 | Horizon vs friction, MNQ + MGC, 11 horizons | kept — §1 |
| 2 | Clock decomposition on **UTC** minutes | **WRONG, discarded** — CME day is local; 88/240 sessions mis-keyed |
| 3 | Clock decomposition on the exchange clock, MNQ | kept — §2 |
| 4 | Same, MGC — independent replication | kept — replicates |
| 5 | ONITE / INTRA / HOLD24 / EUONLY + day-block bootstrap + sign-flip controls | kept, **fails addendum test (c)** |
| 6 | MNQ+MGC paired overnight book | kept, **negative**: ρ = 0.37, t unchanged at 1.31 |
| 7 | **Contract-roll contamination audit** | ★ **caught my own error** — 3 MNQ rolls (+1,135 pt), all inside the overnight window; ONITE t 1.30 → **0.87** |
| 8 | Detectability arithmetic on live per-trade sd | kept — §0, §5 |
| 9 | Spread measured from `capture.db` quotes, by session | kept — §4; **corrected my own 1-tick assumption to 2 ticks** |
| 10 | Liquidity-provision arithmetic | kept, REFUTED |
| 11 | Rider "single-lot" P&L | **discarded as an artefact** — 45 rows = 20 positions |
| 12 | Daily-history ceiling audit, all 29 daily parquets | kept — §8 blocker |
| 13 | Repo verification of six claims the brief treats as established | kept — **one (the +$65.70/lot) does not survive**, §5(c) |
| — | Futures-only OCO straddle backtest | **not run** — already dead by banked results (§3); running it would duplicate the tunnel study |

