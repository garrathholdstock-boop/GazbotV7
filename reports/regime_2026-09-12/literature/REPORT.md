# WHAT ACTUALLY WORKS — literature & practitioner review for GAZBOT V7
**2026-09-12 · lane: `reports/regime_2026-09-12/literature/`**
Artifacts: `NOTES.md` (every source, claim, grade, testability) · `straddle_replication_mnq.csv` ·
`fade_band10_hours.csv` · `noisearea_mnq_trades.csv`.
Every desk number below was re-derived from the repo or computed in this lane. Nothing is recalled.
Costs used: **MNQ $2.00/pt, `FEE_RT = 1.50`/RT (`src/gazbot7/bookrecon.py:43`) + 0.50pt spread crossed
once = 1.25 pt = $2.50/RT.** MGC $10/pt, `MGC_FEE_RT = 4.50` (`src/gazbot7/levelbreak.py:54`).

---

## 0. THE HEADLINE, BEFORE ANYTHING ELSE

I set out to answer five research questions and found that a sixth one invalidates the frame of the
other five. It is not a literature finding; it came out of this desk's own tape.

**The desk's detector cannot see an edge of the size anyone claims exists.**

Measured on 239 sessions of MNQ 1-minute RTH bars (`scratchpad/power.py`), the standard deviation of
the signed move is 29 pt over 5 minutes, 100 pt over an hour, 252 pt over a session. For a
**selective signal that fires once per session over 239 sessions**, the smallest per-trade edge
reaching t = 2 is:

| hold | sd | min detectable edge (t=2) | in $ | gross edge required (MDE + 1.25 pt friction) |
|---|---|---|---|---|
| 5 min | 29.3 pt | **3.79 pt** | $7.57 | 5.04 pt |
| 15 min | 51.3 pt | **6.63 pt** | $13.27 | 7.88 pt |
| 30 min | 69.9 pt | **9.04 pt** | $18.09 | 10.29 pt |
| 60 min | 100.1 pt | **12.95 pt** | $25.89 | 14.20 pt |
| 120 min | 141.2 pt | **18.27 pt** | $36.54 | 19.52 pt |
| to the close (390 min) | 251.6 pt | **32.55 pt** | $65.10 | 33.80 pt |

The largest gross edge anybody credibly claims in this instrument is **1.05–1.50 pt** (Mesfin's
ceiling across fourteen families) or **~2 bps ≈ 4.8 pt** (Zarattini's NQ figure). **The desk's
detection floor is 3.8–32.6 pt. The gap is between 2× and 20×.**

Equivalently: **t = Sharpe × √years.** Over a 239-session window only a **Sharpe ≥ 2.0** strategy
reaches t = 2. A Sharpe-1.0 strategy — an excellent outcome on $30k — is statistically
indistinguishable from zero here, and stays so for four years.

This has two edges and both cut.

1. **The nulls are uninformative, not confirmatory.** The five direction studies, the 430-config exit
   sweep, the 22-config regime detector, the 12 regime-transition cells with "every t below 1.0" —
   all are exactly what you get when a real edge of the claimed size is present and the instrument
   cannot resolve it. They do establish one true thing: **nothing LARGE is there.** That is worth
   knowing and it is all they establish.
2. **The positives are equally unbelievable at this n**, which is precisely what the shuffle and
   placebo controls kept demonstrating. The controls were right; they were right for a reason that
   generalises.

And there is a structural trap inside it. Friction as a share of the hold's sd **falls** with
duration (1.25/29.3 = 4.3% at 5 min → 0.5% at a full session) while the detection floor as a share
**rises** (1.46% → 12.94%). They cross at a **~15-minute hold**. Short holds are testable and
unprofitable; long holds are profitable and unverifiable. **With one year of data there is no hold
length at which this desk can both make money and prove it.**

The way out is not a better signal. It is **more independent observations** — more years, more
instruments, lower per-trade variance. With 16 years (3,824 trades) the floor drops to 0.95 pt at 5
min, 1.66 pt at 15 min, **3.24 pt at 60 min**. At 60 minutes, 3.24 + 1.25 = **4.49 pt gross required
vs Zarattini's ~4.8 pt claim** — the first configuration in which the published claims become
checkable at all. That is the prescription, and it costs a data subscription, not a new idea.

---

## 1. MAGNITUDE IS FORECASTABLE AND DIRECTION IS NOT — what can actually be done with that?

### 1a. The obvious answer is worse than it looks, and I can now say by how much

**Buying short-dated volatility is the most expensive way in the market to express a magnitude view,
and it is most expensive at exactly the horizon the desk forecasts.** Almeida, Freire & Hizmeri,
*0DTE Asset Pricing* (May 2025 draft, CBOE 1-minute SPXW bid/ask, **6 Jan 2012 – 18 Mar 2025, 1,815
dates**) — read in full — find that **every** 0DTE long-volatility structure loses on average: ATM
delta-hedged calls, simple straddles, delta-neutral straddles, at every time of day, significance
strongest 12:00–14:00 ET. The **annualised variance risk premium implied by 0DTEs is "up to four
times larger than what is observed for longer horizons"**, positive with bootstrap p = 0.000 at
every intraday timestamp. The one thing that did pay — stochastic-dominance mispricing — "is highly
profitable before 2022, but dissipates after the daily availability of 0DTEs."
https://www.fma.org/assets/docs/Derivatives2025/Almeida.pdf

The key logical point the desk must not skip: **"magnitude is predictable" and "magnitude is
predictable relative to what options cost" are different claims, and only the first is established.**
Implied volatility is already high when ATR and volume are high. The desk's model predicts realised
range from ATR and volume; so does the option market. Goyal & Saretto (JFE 2009) is the canonical
demonstration that a volatility forecast monetises only as a **relative-value signal against IV**,
never standalone. The desk captures no IV of any kind — `data/capture.db` holds MNQ and MGC bars,
quotes, ticks and book, and nothing else. **The incremental-to-IV regression has never been run and
cannot be run today.**

### 1b. I tested the futures route directly, and it is refuted

A linear instrument cannot pay |move|. The only futures route to a straddle is dynamic replication:
stop-and-reverse around a ±band. I ran it on 239 sessions / 1,654 RTH hours of MNQ 1-min, fills at
the **next minute's open** (v1 filled at the signal bar's close — a look-ahead — and was discarded),
friction 1.25 pt/RT, hours split by a causal magnitude state (prior-hour range tercile).

| state | n hours | n days | long-straddle replication | day-block 95% CI (5,000 reps) |
|---|---|---|---|---|
| LOW | 550 | 189 | −0.23 pt | [−6.14, +5.68] |
| MID | 555 | 218 | −5.00 pt | [−12.25, +2.11] |
| **HIGH** | 549 | 192 | **−15.64 pt = −$31.27/contract/hour** | **[−27.41, −3.74] — excludes zero** |

**Replicating a straddle in MNQ futures loses most on exactly the hours the magnitude model calls
biggest.** Mean |net hourly move| on HIGH hours is 88 pt: the payoff is there, the replication cannot
collect it.

Its mirror — the fade, short gamma — shows +16.17 pt/hr, t = 2.91, and it even splits chronologically
(+18.68 then +14.65). **It is not a finding.** A within-hour shuffle control (shuffle the minute
returns inside each hour: keeps volatility and |move|, destroys path order; 40 reps × 547 hours)
scores **12.31 pt** against the real **16.17 pt** — **76% of the apparent edge is reproduced by paths
with no predictability at all**, a gap of 1.1 control sd, failing clause (b) of the 2026-09-12 bar.
Its tail: 5th percentile −163 pt (−$327), worst single hour **−620 pt (−$1,241) on one lot**.

★ The useful way to read that control: the ~12 pt the shuffled path costs the long replication **is
the replication's own discretisation-plus-friction bill**. **Synthesising convexity in MNQ futures at
1-minute granularity costs about 12 points ($24) per hour on a high-volatility hour.** No magnitude
forecast of the size the desk has can pay that. **Convexity must be bought, not built** — and §1a
says the price of buying it peaks at the same-day horizon.

### 1c. The one avenue the evidence leaves open — and it is the inverse of the obvious one

If implied vol is systematically above realised, the trade is to **sell** it. Unbounded short vol is
unsuitable for $30k; defined-risk short structures are not. The best evidence found (Vilkov et al.,
0DTE strategy study with published code, 09/2016–01/2026, costs charged at **half the observed
bid-ask + 0.5 bp**) finds:
- **unconditional** 0DTE exposure: "most strategies showed weak or negative returns after costs", and
  "difficult to justify as a standing allocation";
- **conditional** on a timing signal: put ratio spreads **gross Sharpe 1.18, net 0.93**; a
  diversified equal-weight basket **net ~0.82**;
- tails are real: expected shortfall **0.58–1.58% of underlying**.
https://github.com/vilkovgr/0dte-strategies/blob/main/docs/paper/paper-annotated.md

Premium selling pays **only conditionally** — it needs exactly the kind of state signal the desk
already has, pointed at the **quiet** tail. **The desk's magnitude model is more valuable at its 9%
end than its 77% end**, and the desk has been reading it the other way round.

Two hard caveats. (i) The vehicle is almost certainly SPX/SPY/QQQ, not MNQ options: **I could not
establish that options on Micro E-mini Nasdaq-100 futures have usable liquidity.** cmegroup.com timed
out twice on WebFetch and returned nothing to curl; every other source was broker or prop-firm
marketing. Do not assume they are tradable until the chain is measured. (ii) A short-premium book is
a different account, different margin, and sits awkwardly with "never hold overnight."

---

## 2. WHAT ACTUALLY WORKS AT RETAIL SCALE

### The one paper the desk is building on is weaker than the desk thinks
Mesfin (2026), *Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures* — 72,604 5-min
bars, **947 days**, Dec 2021–Aug 2025 — is credible **in its nulls**: fourteen families, nothing
passed, gross ceiling 0.07–1.50 pt against 2.0 pt assumed friction. Three things about its positives
must be on the record:

1. **Table 11's "T-Stat (Net)" column is the gross t repeated.** ORB Long is listed at 1.50 gross and
   1.50 net after deducting 2.0 pt from a 4.82 pt mean; t must fall to ≈0.88. Same shape for gap
   continuation (3.23/3.23). The error runs conservative for the paper's null, but no number in that
   column is usable.
2. **The two signals the desk's whole regime-transition programme rests on are not this paper's
   results.** Quote: *"Two signals from a separate research program are included here as positive
   controls... developed independently and are not the subject of this paper."* RTH Confluence's
   headline **t = 5.83 / +15.77 pt is IN-SAMPLE (2022–2024, n=538)**; walk-forward OOS is t = 3.11,
   n = 196. London Signal B's **t = 5.15, +5.77 pt, Sharpe 5.09, n = 289** has **no out-of-sample
   split at all.** A Sharpe of 5.09 on 289 retail futures trades is not a plausible surviving edge.
3. **London Signal B inverts to t = −3.56 on a one-bar delay.** The paper reads that as timing
   sensitivity. The likelier mechanism is **look-ahead in the GMM labels** — the paper never says the
   GMM was fitted train-only. `scripts/bt_regime_transition.py` warns of precisely this in its own
   docstring ("Fitting on all the data would relabel history with hindsight... once manufactured a
   z=4-6 finding that did not exist in real time") and fits train-only — and gets every t below 1.0.
   **The distance from the paper's t=5.15 to the desk's t<1.0 is what you would predict if the
   paper's labels are hindsight-fitted.** §0 says it could also be pure power. Both can be true.

★ And the paper's own suggested extension is the desk's one positive result: *"Testing it [the VVG
classifier] as a volatility predictor rather than a direction predictor is worth investigating — if
classifier days reliably show higher realized variance, a volatility-based approach might capture
that."*

### The strategy family with the best evidence, and the statistic the desk scored on the wrong axis
Zarattini, Aziz & Barbon (2025), *Beat the Market* (SFI WP 24-97) specifies its rules completely:
σ[t,HH:MM] = mean over the previous **14** sessions of |Close[HH:MM]/Open[9:30] − 1|;
Upper = max(Open_t, Close_{t−1})·(1+σ), Lower = min(Open_t, Close_{t−1})·(1−σ); long above / short
below; **decisions only at HH:00 and HH:30**; exit at the close or reverse at the opposite boundary;
band as trailing stop; 2%/day vol target capped at 4×. Costs: $0.0035/share IBKR plus **$0.001/share
measured from their own fills**. Claim: SPY 2007–early 2024, **+1,985% net, 19.6% p.a., Sharpe 1.33**;
NQ leg **+2 bps/trade, win rate 36%, payoff 2.09**.

★★ **Its win rate is 36%.** Five of the desk's null results measured **directional hit rate** and
found ~0.50. A 36%-win / 2.09-payoff strategy has positive expectancy with a hit rate far below 0.50.
**A hit rate of 0.50 does not refute a positive-expectancy trend strategy.** That is the desk's own
[[friday-report-judge-on-expectancy-not-winrate]] rule, and every one of the five nulls was scored on
the statistic that cannot reject this family.

★ Note also what its entry threshold *is*: a 14-day, time-of-day-conditioned average absolute move.
**It is a magnitude model.** The desk's only solid finding is the input this strategy runs on.

**I implemented it on MNQ** (`noisearea_mnq_trades.csv`): 231 full RTH sessions, 1 lot, friction
1.25 pt, next-open fills. **n = 131 trades, mean +11.77 pt ($23.54), t = 0.68, day-block 95% CI
[−23.19, +46.31].** Halves +1.97 / +21.43. A **placebo** using the identical machinery with the σ band
borrowed from a random other session scored +7.65, +9.43, −1.73 — the real band sits inside the
placebo spread. **Verdict: not established and not refuted — the test had no power.** Per-trade
sd is **198.95 pt**; detecting the observed 11.77 pt needs **1,097 trades ≈ 7.6 years**, and
detecting the paper's own 4.8 pt needs **~6,600 trades ≈ 46 years** at this trade rate.

### The model of an honest practitioner test
https://github.com/giovannibrusco/zarattini-2023-orb-qqq — independent replication of the QQQ ORB
paper, Jan 2016–Feb 2023. Matched the paper's trade count (**1,775 vs 1,795**) and Sharpe (**1.06 vs
1.12**), then: the paper assumed "zero slippage in fills" for **$138,639**; with execution costs that
became **$4,860 (2.7% CAGR)**, break-even at **~2.2¢/share** against a ~1¢ spread — "the edge exists
only within the spread itself." **76% of the filtered P&L came from 2022 alone.** Bootstrap Sharpe CI
**[0.05, 1.41]** overlapping buy-and-hold **[−0.03, 1.47]**. One thing survived: a cross-asset NQ
confirmation filter at **$0.125/share, t = 2.05**, versus a **09:25 pre-market-bar placebo at
$0.079/share, t = 1.27**.

### Order flow and microstructure: know what the famous number is
Cont, Kukanov & Stoikov (JFE-conometrics 2014) — order-flow imbalance explains mid-price changes with
**average R² = 65%** — is a **contemporaneous** regression. OFI and the price move are the same event.
It is not a forecast, and the desk's ~0.000 result at leg starts is the expected outcome.
Andersen & Bondarenko on VPIN: **"when controlling for current volume and volatility... no evidence
of incremental predictive power"**; VPIN peaked *after* the flash crash. ★ The imported rule —
**every microstructure signal must be tested incrementally to contemporaneous volume and volatility,
or it is measuring trading intensity** — is also the test the desk owes its own magnitude model.
Cross-asset lead-lag price discovery is real but decays at millisecond horizons; without
co-location it is not a timing signal. The QQQ/NQ filter above is its retail-horizon form: small,
significant per trade, and regime-concentrated.

### Events and the calendar: the most robust magnitude fact there is
Announcement volatility multipliers — **payrolls ≈ 6×, GDP/CPI/FOMC ≈ 3–4×** — are the best-replicated
magnitude result in the literature. That is also an **audit risk for the desk's own best finding**:
the high-magnitude state may be substantially "a scheduled release happened." That is cheap to test
today and should be tested before anything is built on top of it.

---

## 3. THE DECAY QUESTION — and the answer is better news than it sounds

McLean & Pontiff (J.Finance 2016, 97 predictors): **−26% out-of-sample, −58% post-publication**;
decay is largest for the biggest in-sample winners; survival is best in low-liquidity, high-idio-risk
names.

But the more useful paper is **Falck, Rej & Thesmar (CFM + MIT, arXiv:2105.01380 → Quant. Finance
2022)**, which races the two explanations on 72 replicated anomalies (Sharpe halves post-publication,
replicating M&P):
- publication date alone: **R² = 0.30** — each year adds **5 percentage points** of decay;
- **sensitivity to outliers** (drop the top 0.1% of contributions, Broderick et al. 2020): **R² 0.14**;
- **number of operations** needed to compute the signal (>2): **R² 0.11**;
- combined overfitting vulnerability R² 0.15; **arbitrage vulnerability "marginal" — "removing the
  arbitrage variable diminishes the R² only slightly."**

**Decay is mostly overfitting, not competition.** The desk is not chiefly losing edge to faster
players; it is chiefly finding edge that was never there. That is fixable by method. It also yields
three free, importable gates (ranked V1–V3 below) and one prior: **prefer signals with few
operations.** A gate slate assembled from composed helpers is, by this measure, the high-decay class.

**What is structurally resistant?** Not anomalies — **risk premia**: payment for bearing something
other people will not. The variance risk premium is the largest one reachable at retail, and §1c is
the only place in this review where the evidence supports a standing position. Everything else that
survives does so by being capacity-limited or operationally awkward, and those are exactly the
properties a solo desk on a $30k account can actually possess.

**The case study that landed this year, and settles one idea before it starts.** The overnight drift
(Boyarchenko, Larsen & Whelan, RFS 36(9):3502–3547, 2023): the **02:00–03:00 ET** hour in ES futures
earned **3.7% p.a. over 1998–2020 (5,691 days)** — "more than 60 percent of the contract's 5.9 percent
annualized return." NY Fed Liberty Street Economics, **July 2026**: over **Jan 2021 – Dec 2025 (1,245
days)** the same window "averaged close to zero". Cause given: end-of-day residual imbalance
compressed, "the standard deviation of end-of-day RSV fell from 6.5 percent to 2.9 percent."
**A 22-year, mechanism-backed edge went to zero because the mechanism changed.** Do not build it.
(The desk is flat overnight by operator rule anyway.)

---

## 4. IS MNQ THE WRONG INSTRUMENT? — no, and the desk's own data says so

Computed from `data/backfill/` (`scratchpad/costrange.py`), RTH 13–19Z, front month by volume:

| | sessions | median RTH range | in $/contract | RT cost | **cost ÷ median range** | median RTH volume |
|---|---|---|---|---|---|---|
| **MNQ** | 239 (2025-09-15..2026-08-18) | 335.5 pt | $671 | $2.50 | **0.37%** | 1,421,757 |
| **MGC** | 271 (2025-07-28..2026-08-28) | 55.3 pt | $553 | $4.50 | **0.81%** | 138,540 |

**MNQ is 2.2× cheaper than MGC relative to its own daily opportunity.** "MNQ is too efficient, move to
something less traded" has the cost side backwards: a thinner contract must contain a proportionally
**larger** gross edge merely to break even. The efficiency that produces the edge ceiling is the same
property that makes the ceiling cheap to reach. The desk already trades the cheapest instrument it
has data for.

This does **not** say other instruments are pointless — it says **instrument-switching is not a
strategy**. Switch only when a *mechanism* is named first (e.g. the EIA inventory release structure in
MCL, a scheduled event with a known clock), and then test the mechanism, not the ticker. We hold no
data for MCL/M2K/MYM/MBT/ES, so nothing beyond MNQ and MGC can be tested without a new backfill.

---

## 5. THE HONEST BASE RATE

**Chague, De-Losso & Giovannetti, *Day Trading for a Living?* (SSRN 3423101)** is the right study for
this desk: **every** individual who began day trading **Brazilian equity-index futures** (B3, then the
world's third-largest such market) in 2013–2015 — **19,646 people** — followed to 2017, net of
exchange and brokerage fees, "our results overestimate day trading profits" because taxes, platform
and course costs are excluded.

- Persistence: 5.7% traded one day · 50.8% 2–50 days · 15.8% 51–100 · 13.9% 101–200 · 5.9% 201–300 ·
  **7.9% (1,551) more than 300 days.**
- Of the 1,551 persisters: **97% lost money.** 47 were net positive. **17 (1.1%)** beat the Brazilian
  minimum wage (US$16/day); **8 (0.5%)** beat a bank teller's starting salary (US$54/day); the best
  averaged US$310/day. Those 8 did it with daily-P&L standard deviations of **US$632 to US$3,308**.
- **"The probability of an individual exhibiting a positive profit monotonically decreases with the
  number of days he or she trades... patterns like this are usually found in gambling activities."**
  Panel regressions on the persisters find **no evidence of learning**, gross or net.

**Barber, Lee, Liu & Odean** on Taiwan: **<1%** of those who day trade over a year are profitable net
of fees; average **−23.9 bp per day**; aggregate performance reliably negative in **14 of 15 years**;
74% of day-trading volume comes from traders with a history of losses.

★ **And the counterweight, which is the only empirically supported route to being on the right side of
that number:** the same authors find that **"less than 3% of active day traders on an average day" —
the most experienced, previously profitable ones — "earn predictably positive net returns."** Skill
is real, it is rare, and it is **persistent enough to be detected from past performance.** Not from a
backtest. From a record.

Prop-firm pass rates (FPFX Tech ~300,000 accounts: 14% pass, 45% of those reach a payout, ~7% ever
paid; FTMO ~10–15%) are **vendor self-reports from companies that sell challenges** and should not be
used as a base rate at all.

★ A caveat in the desk's favour that honesty requires: these populations are unselected discretionary
retail with no reconciliation, no cost model and no controls. This desk has a venue-truth
reconciliation layer, a measured fee constant, a shuffle-control habit and a written ledger of its own
bad calls. That does not exempt it from the base rate. It does mean the base rate is measuring a
different activity.

---

## 6. VERDICTS — one line, the test that decided it, the number

| lead | verdict | the test that decided it |
|---|---|---|
| Buy short-dated volatility on a magnitude forecast | **REFUTED** | Almeida et al., 1,815 dates: every 0DTE long-vol structure negative at every time of day; annualised 0DTE VRP up to **4×** longer horizons |
| Synthesise a straddle from MNQ futures (band stop-and-reverse) | **REFUTED** | This lane: HIGH-magnitude hours **−15.64 pt/hr**, day-block CI [−27.41, −3.74]; replication cost ≈ **12 pt/hr** |
| The fade / short-gamma mirror of it | **REFUTED as an edge** | Within-hour shuffle control reproduces **76%** of it (16.17 vs 12.31, gap 1.1 control sd); worst hour −$1,241 on one lot |
| Overnight drift (02:00–03:00 ET) | **REFUTED** | NY Fed, July 2026: 3.7% p.a. over 1998–2020 → **"close to zero" since 2021**, mechanism gone |
| MNQ is the wrong instrument | **REFUTED on cost** | Desk data: cost ÷ median RTH range **0.37% MNQ vs 0.81% MGC** |
| Mesfin's two "passing" signals as evidence for regime classification | **REFUTED as evidence** | They are the paper's own declared positive controls, from another programme; one has no OOS split; the other's headline t is in-sample; a one-bar delay inverts it to t = −3.56 |
| Noise-area intraday momentum (Zarattini) on MNQ | **PARKED — untestable at current n** | This lane: n=131, +11.77 pt, t=0.68, CI [−23.19, +46.31], inside the placebo spread; needs **~6,600 trades** for the paper's own claim |
| The desk's regime-transition cells | **PARKED — same reason** | Every t < 1.0 is the expected result at this n whether or not an edge exists (§0) |
| Magnitude as a *threshold-setter* rather than a traded object | **SHADOW** | It is what Zarattini's band already is; testable on purchased history, see R3 |
| Selling defined-risk premium conditioned on the QUIET tail | **SHADOW — the one open avenue** | Conditional put ratio spreads **net Sharpe 0.93**; unconditional exposure "difficult to justify"; blocked today for lack of any IV data |

---

## 7. RANKED, CONCRETELY TESTABLE — for MNQ/MGC micros, one operator, ~$30k, paper today

Ranked by expected information gained per unit of effort. **R1 and R2 come before everything because
every item below them inherits their power.**

**R1 — BUY THE HISTORY. (highest value, lowest cleverness)**
*Do:* acquire ≥10 years (ideally 2010→) of 1-minute NQ/MNQ, ES/MES and GC/MGC from Databento
(GLBX.MDP3; Mesfin quotes **~$42/quarter** for MNQ tick — verify at purchase). Rebuild
`data/backfill/` from it.
*Test it settles:* re-run the desk's **existing** five nulls and the 12 regime-transition cells on
16 years. Pass = t ≥ 3 with a day-block CI excluding zero **and** beating its shuffled twin by more
than one control sd, on a **held-out final three years never touched during fitting**.
*Data needed:* purchase only. *Why first:* §0 — at 239 sessions the answer to every question is "we
cannot tell", and that will remain true however good the next idea is.

**R2 — RE-SCORE EVERY PAST NULL ON EXPECTANCY, NOT HIT RATE.**
*Do:* for each of the five direction studies, recompute **mean net P&L per trade with a day-block
bootstrap CI**, and the win/payoff pair — not P(correct).
*Test it settles:* whether "direction is unpredictable" was ever measured. A 36%-win / 2.09-payoff
strategy is profitable and scores 0.36 on the statistic the desk used.
*Data:* already on disk. *Cost:* hours. *Falsifiable:* if the expectancy CIs also straddle zero at
comparable width, the nulls stand — as "nothing large", nothing more.

**R3 — AUDIT THE MAGNITUDE FINDING AGAINST A CALENDAR AND AGAINST ITSELF.**
*Do:* (a) attach a free macro calendar (FOMC/CPI/NFP/GDP/PPI/claims) to the 239 sessions; re-fit the
magnitude model with an announcement dummy. (b) Apply the Andersen–Bondarenko test: does the model
add predictive power for future range **incrementally to contemporaneous volume and volatility**?
*Test it settles:* whether the desk's single positive result is a forecast or a restatement of "a
release happened" / "volume is high right now". Pass = the feature's coefficient survives both
controls with the t = 15.04 day-clustered statistic materially intact.
*Data:* on disk plus a public calendar. *Cost:* a day. **Run this before building anything on top of
the magnitude model.**

**R4 — NOISE-AREA, POOLED AND PRE-REGISTERED.** (needs R1)
*Do:* run the implementation already written (`scratchpad/noisearea.py`, rules verbatim from the
paper) on MNQ + ES + MGC × 16 years, pooled — ≈12,000 trades. Keep the random-band placebo.
*Test it settles:* pooled mean net > 0 with a day-block CI excluding zero, beating the placebo by
> 1 placebo sd, on the held-out final three years. **Pre-register the band (14 days), the decision
clock (HH:00/HH:30) and the exit before running. No tuning.**
*Data:* R1's purchase. *Why it ranks here:* it is the only published family whose rules are fully
specified, whose costs were measured rather than assumed, whose claimed win rate (36%) is consistent
with the desk's own direction nulls, and whose entry threshold is a magnitude model.

**R5 — VOL-TARGET THE POSITION SIZE. (free statistical power, no new edge required)**
*Do:* recompute the desk's existing trade log under equal-risk sizing (target a constant $ risk per
trade using the ATR at entry) instead of fixed lots; measure the change in **per-trade sd and t** on
the identical trade set.
*Test it settles:* how much of the desk's inability to measure itself is variance it chose. Zarattini
targets 2%/day capped at 4×; the desk trades 1–4 lots on rules that are not risk-normalised.
*Data:* on disk. *Cost:* hours. This raises t for any given edge and improves risk-adjusted return
simultaneously; it is the cheapest item on the list.

**R6 — ADOPT THREE STANDING ROBUSTNESS GATES (from Falck/Rej/Thesmar, R² 0.14 and 0.11 for OOS decay).**
*V1 — influence drop:* recompute every candidate after removing the **top 0.1% contributing trades**
(Broderick et al. 2020). *V2 — subset stability:* 100 random 10% deletions, report the **sd of the
statistic**. *V3 — complexity count:* count the operations needed to compute the signal; >2 is a
flag, not a veto.
*Test they settle:* whether a result depends on a handful of trades or on grooming. Reject on V1/V2;
weight the prior on V3. *Data:* on disk. *Cost:* one afternoon, then automatic forever.

**R7 — MEASURE MNQ OPTION LIQUIDITY INSTEAD OF ASSUMING IT.** (blocked until IBKR returns)
*Do:* capture the options-on-MNQ-futures chain at 1-minute for five sessions — bid, ask, sizes, open
interest — for the ATM and ±1σ strikes at the nearest two expiries.
*Test it settles:* effective half-spread as a fraction of the ATM straddle premium. **> ~5% → MNQ
options are not a vehicle**, and the volatility question moves to QQQ/SPX (different account,
different margin, and it collides with "never hold overnight").
*Data:* a 30-minute capture job once the gateway is back. No primary source for this exists on the
open web; I tried and failed.

**R8 — THE INCREMENTAL-TO-IV REGRESSION.** (the test that decides whether §1c is real)
*Do:* obtain an IV series — cheapest is **VXN** minute data; best is the **CME options-on-NQ history
(Databento GLBX.MDP3 options/NQ)**. Regress realised forward range on ATM IV **and** the desk's
ATR+volume feature.
*Test it settles:* does the desk's magnitude model know anything the option market does not? If the
feature's coefficient is zero after IV, **the entire volatility-monetisation avenue closes** and the
desk should stop thinking about options. If it is not zero, paper-trade **defined-risk** short
structures conditioned on the model's **quiet** tail — never undefined risk on $30k.
*Data:* not captured today. This is the highest-value thing the desk cannot currently test.

**R9 — CROSS-ASSET CONFIRMATION, WITH THE PLACEBO THAT KILLED IT ELSEWHERE.** (needs R1)
*Do:* does an ES/MES confirmation filter improve MNQ entry expectancy? Replicate the QQQ study's
design exactly: real filter vs a **time-shifted placebo series**, and a **per-year** P&L
decomposition.
*Test it settles:* the QQQ version was significant per trade (t = 2.05 vs placebo 1.27) but **76% of
its P&L came from one year**. Pass = significant per trade **and** positive in ≥ 4 of 6 years.
*Data:* needs ES/MES history — part of R1.

**R10 — NAME A MECHANISM BEFORE SWITCHING INSTRUMENTS.**
*Do:* if MCL is to be considered, state the mechanism first (EIA inventories, Wed 10:30 ET; a
scheduled clock, not a pattern), then test **that**, on purchased MCL history, against a matched-hour
control.
*Test it settles:* whether the event window has a magnitude structure large enough to clear MCL's
wider cost. *Data:* not held. §4 says the burden of proof is on the thinner contract.

### Explicitly NOT worth further effort
Straddle replication in futures · the fade mirror of it · the 02:00–03:00 ET overnight drift ·
citing Mesfin's positive controls as evidence · switching instruments without a named mechanism ·
tuning any existing gate on a 239-session sample (§0 says the result cannot be read).

---

## 8. WHAT WE CANNOT TEST WITH WHAT WE CAPTURE — stated plainly

`data/capture.db` contains bars, book, quotes and ticks for **MNQ and MGC only**
(`select symbol,count(*) from bars` → MNQ 694,335 / MGC 464,288). `data/backfill/` holds 1-min
parquet for the same two symbols and nothing else. Therefore:

1. **Anything involving implied volatility, option prices, the variance risk premium or a straddle's
   cost.** No IV, no VXN, no chain. This blocks R8 and everything in §1c. It is the single most
   valuable gap.
2. **Anything on another instrument** — ES/MES, MCL, M2K, MYM, MBT, QQQ, SPX. Blocks R9, R10, and
   pooling generally.
3. **Anything needing more than ~1 year of intraday history.** This is the binding constraint on
   every strategy question in this report, and it is the one that money fixes.
4. **Anything at queue-position or sub-second resolution.** `depth.db` holds L2 snapshots, not
   order-by-order queue data, and with no co-location the millisecond lead-lag literature is not
   reachable regardless of data.
5. **Whether a LIVE account behaves like the paper account.** The IBKR paper engine fabricates a
   0.1%-adverse fill on every lot beyond the first ($2,916.50 over 32 orders — more than the desk's
   entire booked loss). Until real fills exist, **every multi-lot P&L number on this desk is
   contaminated and single-lot numbers are the only clean ones.**
6. **Retail prop-firm base rates.** Vendor self-reports only; not verifiable at any standard.

---

## 9. THE SHORT VERSION, FOR A SATURDAY

Six months of work produced a set of nulls that are almost certainly correct about the absence of
anything **large**, and silent about the presence of anything **real** — because at 239 sessions the
desk's smallest detectable per-trade edge is 3.8 to 32.6 points and the biggest edge anyone claims is
1 to 5. That is not a failure of ideas. It is a failure of sample size, and it is the cheapest problem
on this list to fix.

The single most obvious trade — buy convexity because you can forecast magnitude — is closed twice
over: the option market charges its highest premium at precisely the horizon you forecast, and I
measured the futures workaround at −$31 per contract per hour on exactly the hours your model likes,
with a shuffle control that reproduced three-quarters of the mirror-image "edge" from paths that
contain no information at all.

What is genuinely open: your magnitude model may be more useful pointed at its quiet tail than its
loud one; a 36%-win trend strategy cannot be rejected by a 0.50 hit rate; and the decay literature
says your real adversary is your own overfitting, not somebody else's speed — which is the one
adversary a careful solo operator can actually beat.

97% of people who did this for 300 days lost money, and fewer than 3% of day traders earn predictably
positive net returns — but that 3% is **detectable from a record**, and a record is the one thing a
disciplined paper desk with venue-truth reconciliation is actually built to produce.
