# Literature & practitioner review — running notes
Started 2026-09-12. Agent lane: `literature/` (siblings: book/, leadlag/, replication/).

Desk cost constants VERIFIED IN REPO (not recalled):
- MNQ: `src/gazbot7/bookrecon.py:43` `FEE_RT = 1.50` ("venue truth over 487 fills"); `VPP` = 2.0 $/pt
  (`scripts/bt_regime_transition.py:29`). => commission = 0.75 pt. Plus 0.50pt median spread crossed
  once = **1.25 pt all-in round trip = $2.50/contract**.
- MGC: `src/gazbot7/levelbreak.py:54` `MGC_FEE_RT = 4.50` ($3.00 spread from MID + $1.50 comm);
  `src/gazbot7/shadow_mgc.py:86` `REPRICER_FEE_RT = 1.50` (commission only, harness already crossed).
  MGC $10/pt.

Format of each entry: SOURCE | URL | CLAIM (with n, dates, numbers) | EVIDENCE GRADE | TESTABLE HERE?

---
## Q1 — monetising a MAGNITUDE forecast

### [1] Almeida, Freire & Hizmeri (2025), "0DTE Asset Pricing" — PRIMARY, read in full from PDF
URL: https://www.fma.org/assets/docs/Derivatives2025/Almeida.pdf (draft 23 May 2025; also SSRN 4701401)
Data: CBOE 1-minute SPXW option bid/ask, **6 Jan 2012 – 18 Mar 2025, 1,815 dates** (~40% after
11 May 2022 when 0DTEs became daily).
CLAIMS (quoted):
- "All 0DTE strategies produce negative average returns" — ATM delta-hedged calls, simple straddles
  and delta-NEUTRAL straddles, at every time of day. Significance strongest 12:00–14:00 ET.
- "The (annualized) average variance risk premium implied by 0DTEs can be **up to four times larger**
  than what is observed for longer horizons." VRP mean positive with bootstrap p=0.000 at every
  intraday timestamp (2,500 reps).
- The one thing that DID pay — stochastic-dominance "mispricing" — "is highly profitable before 2022,
  but dissipates after the daily availability of 0DTEs" (i.e. it decayed exactly when retail arrived).
- Intraday pricing kernel is U-shaped: investors pay most for UPSIDE variance at 0DTE horizon.
GRADE: peer-review-track academic, huge sample, real bid/ask (not settlement marks).
TESTABLE HERE? The conclusion is directly dispositive and needs no test: **the short-dated
long-volatility trade is the most expensive way in the market to express a magnitude view.** The VRP
is LARGER at exactly the horizon (same-day) the desk forecasts. This kills "buy a straddle when the
magnitude model says big move" unless the desk's forecast beats IV *conditionally* — see [2].

### [2] Goyal & Saretto (2009), "Cross-section of option returns and volatility", JFE 94:310-326
URL: https://personal.utdallas.edu/~axs125732/CrossOptionsJFE.pdf
CLAIM: sorting on (12-month historical vol − 1-month ATM IV) and going long the high-spread decile
straddles / short the low produces large significant monthly returns. I.e. a volatility forecast is
monetisable ONLY as a RELATIVE-VALUE signal against IV, never as a standalone "I think it'll move".
GRADE: top-3 finance journal; but equity single names, monthly horizon, and later work attributes
much of it to illiquidity/bid-ask and to mean-reversion in IV, not to forecasting skill.
TESTABLE HERE? Only if we capture an IV series. We capture none today. Minimum viable version:
capture **VXN** (CBOE Nasdaq-100 vol index) or the ATM MNQ/NQ straddle mid once a minute and ask
whether the desk's ATR+volume magnitude model has INCREMENTAL predictive power for realised 1-hour
range *after controlling for IV*. Until that regression is run, "magnitude is predictable" and
"magnitude is predictable relative to what options cost" are different claims and only the first is
established.

### [3] Mesfin (2026), "Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures"
Local copy: reports/regime_2026-09-12/replication/mesfin_2026.pdf · arxiv.org/pdf/2605.04004
Data: 72,604 5-min MNQ RTH bars, Dec 2021–Aug 2025, **947 complete days**, NinjaTrader; plus 1,091
days MGC. Bar: OOS walk-forward t>=2.0, >=30 trades, positive net after **2.0pt** friction, stable
across years. **Fourteen families, nothing passed.**
Gross ceiling table (Table 11): ORB Long +4.82pt gross (t 1.50) · Asia ORB expansion +1.06 (t −0.90) ·
Gap-fill fade −1.31 · Gap-continuation short +16.52 (t 3.23) but **N=22** · Volume-spike momentum
−1.94 · VVG classifier reversal +3.37 (t 0.86) · MGC OU 5-min −0.19 (t −2.19).
★★ THREE ADVERSARIAL READINGS THIS DESK MUST NOT SKIP:
 (a) **Table 11's "T-Stat (Net)" column is just the gross t repeated.** ORB Long is listed 1.50 gross
     and 1.50 net after a 2.0pt deduction from a 4.82pt mean; that is arithmetically impossible
     (t should fall to ~0.88). Same for gap-continuation (3.23/3.23). The error runs in the
     CONSERVATIVE direction for the paper's null, but it means no number in that column is usable.
 (b) **The two "positive controls" are not this paper's results.** Quote: "Two signals from a
     separate research program are included here as positive controls... developed independently and
     are not the subject of this paper." RTH Confluence's headline **t=5.83 / +15.77pt is IN-SAMPLE
     (2022–2024, n=538)**; its walk-forward OOS is t=3.11, n=196, +11.82pt. London Signal B's t=5.15
     / +5.77pt / Sharpe **5.09** is reported with a permutation p<0.001 and NO out-of-sample split
     at all. A Sharpe of 5.09 on 289 retail futures trades is not a plausible surviving edge.
 (c) **London Signal B inverts to t=−3.56 on a ONE-BAR delay.** The paper reads this as timing
     sensitivity. The likelier mechanism is **look-ahead in the GMM labels**: the paper never says
     the GMM was fitted train-only. This desk's own `scripts/bt_regime_transition.py` docstring
     warns of exactly this ("Fitting on all the data would relabel history with hindsight... once
     manufactured a z=4-6 finding that did not exist in real time") and fits TRAIN-ONLY — and gets
     every t below 1.0. **The gap between the paper's t=5.15 and the desk's t<1.0 is what you would
     predict if the paper's labels are hindsight-fitted.** That is a testable proposition, below.
GRADE: unrefereed arXiv preprint, independent researcher, no code or data released, one visible
arithmetic error. Its NULL results are credible and match the desk's own five independent nulls. Its
POSITIVE results are the weakest part of the paper and are the only thing the desk built on.
★ The paper's OWN suggested extension is the desk's magnitude finding: "Testing it [VVG classifier]
as a volatility predictor rather than a direction predictor is worth investigating — if classifier
days reliably show higher realized variance, a volatility-based approach might capture that."

## Q3 — DECAY: what survives publication

### [4] McLean & Pontiff (2016), "Does Academic Research Destroy Stock Return Predictability?", J.Finance 71(1)
URL: https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365 · WP https://www.hec.ca/finance/Fichier/McLean.pdf
97 published cross-sectional predictors. **−26% out-of-sample, −58% post-publication**; the 32pp gap
is attributed to publication-informed trading. Decay is LARGER for predictors with higher in-sample
returns. Returns survive best in high-idiosyncratic-risk, LOW-LIQUIDITY stocks.
TESTABLE HERE? Not directly (equities, monthly). Usable as a PRIOR: haircut any in-sample number by
~half before believing it, and haircut the biggest in-sample winners hardest.

### [5] ★ Falck, Rej & Thesmar (CFM + MIT, 2021), "Why and how systematic strategies decay"
URL: https://arxiv.org/pdf/2105.01380 (arXiv:2105.01380) · Quant.Finance 2022
72 replicated anomalies. Sharpe decays **~one half** post-publication (replicates M&P).
★ THE RESULT THAT MATTERS FOR A SOLO DESK: they race arbitrage against overfitting as explanations.
 - publication date alone: univariate **R2 = 0.30** (each year adds **5 percentage points** of decay)
 - sensitivity to outliers (Broderick et al. 2020 drop-the-top-0.1% test): **R2 = 0.14**
 - **number of operations** to compute the signal (dummy: >2 ops): **R2 = 0.11**
 - combined overfitting vulnerability R2 = 0.15; **arbitrage vulnerability "weaker... marginal"**;
   "Removing the arbitrage variable diminishes the R2 only slightly."
CONCLUSION: **decay is mostly OVERFITTING, not competition.** The desk is not mainly losing edge to
faster players; it is mainly finding edge that was never there. That is good news — it is fixable by
method, and it is the desk's own [[shuffle-the-labels-not-just-the-periods]] lesson from outside.
TESTABLE HERE? YES, and cheaply — three imported tests, see RANKED LIST items V1–V3.

## Q5 — THE HONEST BASE RATE

### [6] Chague, De-Losso & Giovannetti (2019/2020), "Day Trading for a Living?"
URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101 (full text read)
Universe: **every individual** who started day trading Brazilian **equity-INDEX FUTURES** (B3, then
3rd largest such market in the world) 2013–2015 = **19,646 people**, followed through 2017. Net of
exchange + brokerage fees (but NOT taxes, platform or course costs — "our results overestimate day
trading profits").
- Persistence: 5.7% traded 1 day; 50.8% 2–50 days; 15.8% 51–100; 13.9% 101–200; 5.9% 201–300;
  **7.9% (1,551) more than 300 days**.
- Of the 1,551 who persisted >300 days: **97% lost money.** 47 were net positive. **17 (1.1%)** beat
  the Brazilian minimum wage (US$16/day); **8 (0.5%)** beat a bank teller's starting salary
  (US$54/day); best single trader averaged **US$310/day**.
- The 8 who beat a teller's salary did it with daily-P&L standard deviations of **US$632 to US$3,308**.
- ★ "The probability of an individual exhibiting a positive profit **monotonically decreases** with the
  number of days he or she trades... patterns like this are usually found in gambling activities."
  Panel regressions on the 1,551 persisters find **no evidence of learning** (gross or net).
GRADE: the single best base-rate study for this desk — same instrument class, whole-population data,
net of fees, no survivorship.

### [7] Barber, Lee, Liu & Odean — Taiwan day traders
"Do Day Traders Rationally Learn About Their Ability?" https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf
and "The cross-section of speculator skill: evidence from day trading", J.Fin.Markets 2014.
- **<1%** of individuals who day trade over a year are profitable net of fees.
- Day traders lost an average of **23.9 bp per day net of fees**; aggregate performance reliably
  negative in **14 of 15 years**.
- 74% of day-trading volume comes from traders with a history of losses.
- ★ THE OTHER HALF, which is the honest counterweight: **"less than 3% of active day traders on an
  average day" — the most experienced, previously profitable ones — "earn predictably positive net
  returns."** Skill is real, rare, and **persistent enough to be detected from past performance**.
  That is the only empirically supported route: measure your own out-of-sample record and let it,
  not a backtest, decide whether to scale.

## ★ DESK-DATA EXPERIMENT (run in this lane, not recalled) — can FUTURES pay for a magnitude forecast?
Scripts: scratchpad straddle_repl / straddle2 / straddle3. Artifacts:
`literature/straddle_replication_mnq.csv`, `literature/fade_band10_hours.csv`.
Data: `data/backfill/MNQ_*_1min.parquet`, front month by volume, 239 sessions 2025-09-15..2026-08-18,
1,654 RTH hours (13–19Z). Friction **1.25pt/RT** (desk-measured). Hours split by a CAUSAL magnitude
state = prior-hour range tercile (cuts 85.8 / 147.5 pt).

A linear instrument cannot pay |move|. The only futures route to a straddle is dynamic replication:
stop-and-reverse around a ±band from the hour's open. v1 filled at the signal bar's close (a
look-ahead); **v2/v3 fill at the NEXT minute's open.**

RESULT — long-straddle replication, band 10pt, 95% DAY-BLOCK bootstrap CI (5,000 reps, resampling
whole sessions):
| state | n hrs | n days | long-repl mean | day-block 95% CI |
|---|---|---|---|---|
| LOW  | 550 | 189 | −0.23 pt | [−6.14, +5.68] |
| MID  | 555 | 218 | −5.00 pt | [−12.25, +2.11] |
| **HIGH** | 549 | 192 | **−15.64 pt (−$31.27/contract/hour)** | **[−27.41, −3.74] excludes 0** |
Band 40 HIGH: −12.00pt, CI [−21.73, −2.26]. Band 20 HIGH: −10.76, CI [−21.28, −0.04].
**Replicating a straddle in MNQ futures loses MOST on exactly the hours the magnitude model calls
biggest.** Mean |net hourly move| on HIGH hours is 88pt — the payoff is there; the replication
cannot collect it.

THE MIRROR AND ITS CONTROL. The negative of that is a FADE (short gamma): HIGH state band 10 =
+16.17pt ($32.34/hr), t=2.91, and it splits chronologically (H1 +18.68 t=2.17 / H2 +14.65 t=2.02).
That looks like a lead. **It is not.** Within-hour SHUFFLE control (shuffle the minute returns inside
each hour — keeps volatility and |move|, destroys path order; 40 reps × 547 hours):
  real **16.17pt** · shuffled **12.31pt** (sd 3.40) · **real − control = 3.86pt = 1.1 control sd**.
**76% of the apparent fade "edge" is reproduced on paths with no predictability whatsoever.** It is a
payoff-geometry artefact of a short-gamma structure plus friction, not a forecast. It fails clause
(b) of the 2026-09-12 bar. Tail: p5 = −163pt (−$327) and the worst single hour is −620pt (−$1,241)
on ONE lot — short gamma on a $30k account.
★ THE USEFUL WAY TO READ THE CONTROL: the ~12pt the shuffled path loses to the long replication IS
the replication's own discretisation + friction cost. **The cost of synthesising convexity in MNQ
futures at 1-minute granularity is ~12 points ($24) per hour on a high-vol hour.** No magnitude
forecast of the size the desk has can pay that. **Convexity has to be BOUGHT, not built — and
[1] says the price of buying it is highest at exactly the same-day horizon the desk forecasts.**

## Q4 — is MNQ the wrong instrument? (computed from the desk's own backfill)
Script: scratchpad/costrange.py. RTH 13–19Z, front month by volume.
| | sessions | median RTH range | in $/contract | RT cost | **cost / median range** | median RTH volume |
|---|---|---|---|---|---|---|
| MNQ | 239 (2025-09-15..2026-08-18) | 335.5 pt | $671 | $2.50 (1.25pt) | **0.37 %** | 1,421,757 |
| MGC | 271 (2025-07-28..2026-08-28) | 55.3 pt | $553 | $4.50 (0.30pt spread + $1.50) | **0.81 %** | 138,540 |
**MNQ is 2.2× cheaper than MGC relative to its own daily opportunity.** "MNQ is too efficient, move
to a less-traded contract" has the cost side exactly backwards: a thinner contract must contain a
proportionally LARGER gross edge simply to break even. The desk already has the cheapest instrument
it trades. (We hold no data for MCL/M2K/MYM/MBT, so this cannot be extended to them without a new
backfill — named in the ranked list.)

## ★★★ THE POWER TABLE — the finding that reframes everything (desk data, `scratchpad/power.py`)
MNQ RTH 09:30–16:00 ET, 239 sessions, front month, signed move over each hold, friction 1.25pt.
**Minimum edge detectable at t=2 by a SELECTIVE signal firing once per session over 239 sessions:**
| hold | measured sd | min detectable edge | in $ | gross edge needed (MDE + friction) |
|---|---|---|---|---|
| 5 m | 29.3 pt | 3.79 pt | $7.57 | 5.04 pt |
| 15 m | 51.3 pt | 6.63 pt | $13.27 | 7.88 pt |
| 30 m | 69.9 pt | 9.04 pt | $18.09 | 10.29 pt |
| 60 m | 100.1 pt | 12.95 pt | $25.89 | 14.20 pt |
| 120 m | 141.2 pt | 18.27 pt | $36.54 | 19.52 pt |
| 390 m (to close) | 251.6 pt | 32.55 pt | $65.10 | 33.80 pt |
**The largest gross edge anyone credibly claims in MNQ is 1.05–1.50 pt (Mesfin's ceiling) or ~2 bps
≈ 4.8 pt (Zarattini's NQ figure). The desk's detection floor is 3.8–32.6 pt.** The gap is 2×–20×.
→ **Every one of the desk's five "direction is unpredictable" nulls, the 430-config exit sweep, the
22-config regime detector and the 12 regime-transition cells were produced by a detector that could
not have seen an edge of the size the literature says exists.** Those results are UNINFORMATIVE, not
confirmatory. (They are still correct about one thing: nothing LARGE is there.)
→ The same arithmetic forbids believing the positives: at this n, an apparent 11-16 pt result is
inside the noise, which is exactly what the shuffle and placebo controls kept showing.
★ THE TRADE-OFF, stated exactly. Friction as a share of the hold's sd FALLS with duration
(1.25/29.3 = 4.3% at 5 min → 0.5% at a full session) while the detection floor as a share RISES
(1.46% → 12.94%). They cross at a **~15-minute hold, where MDE (1.30 pt at full occupancy) equals
friction (1.25 pt)**. Short holds: testable, unprofitable. Long holds: profitable, unverifiable.
**With one year of data there is no hold length at which this desk can both profit and prove it.**
t = Sharpe × √years, so over 239 sessions only a **Sharpe ≥ 2.0** strategy reaches t=2. A Sharpe-1.0
strategy — a perfectly good outcome on $30k — is INDISTINGUISHABLE FROM ZERO in this window and
stays so for four years.
★ WITH 16 YEARS (3,824 trades) the floor drops to 0.95 pt (5m) / 1.66 pt (15m) / 3.24 pt (60m) /
8.14 pt (to close). At a 60-minute hold, 3.24 + 1.25 = **4.49 pt gross needed vs Zarattini's ~4.8 pt
claim** — i.e. the duration + data combination is the ONLY configuration in which the claims in the
literature become checkable at all. That is the prescription, and it costs a data subscription.

### [8] Zarattini, Aziz & Barbon (2025), "Beat the Market: An Effective Intraday Momentum Strategy for SPY"
URL: https://alexandria.unisg.ch/bitstreams/a99aba00-f967-49b3-aceb-f544dc386e0b/download (SFI WP 24-97)
Rules are fully specified (read from the PDF): move[t−i] = |Close[t−i,HH:MM]/Open[t−i,9:30] − 1|;
σ[t,HH:MM] = mean over previous **14** sessions; Upper = max(Open_t, Close_{t−1}) × (1+σ);
Lower = min(Open_t, Close_{t−1}) × (1−σ). Long above / short below; **decisions only at HH:00 and
HH:30**; exit at the close or reverse on the opposite boundary; band as trailing stop; vol-target
2%/day, leverage capped 4×. Costs $0.0035/share IBKR + **$0.001/share measured slippage** (their own
fill study, median lower).
Claim: SPY 2007–early 2024 total +1,985% net, **19.6% p.a., Sharpe 1.33**. ES/NQ version: 19.6% p.a.,
Sharpe 1.33; NQ leg **+2 bps/trade, win rate 36%, payoff 2.09, max DD 24%**.
★★ WHY THIS MATTERS MORE THAN ITS P&L: **its win rate is 36%.** Five of the desk's nulls measured
DIRECTIONAL HIT RATE and found ~0.50. A 36%-win / 2.09-payoff strategy has positive expectancy with
a hit rate FAR below 0.50. **Hit rate ≈ 0.50 does not refute a positive-expectancy trend strategy.**
That is the desk's own [[friday-report-judge-on-expectancy-not-winrate]] rule, and the five nulls
were all scored on the wrong statistic to reject this family.
★ Its entry threshold IS a magnitude model (a 14-day, time-of-day-conditioned average absolute move).
The desk's one solid finding is the input this strategy runs on.

### [8a] ★ I IMPLEMENTED IT on MNQ — `literature/noisearea_mnq_trades.csv`, `scratchpad/noisearea.py`
231 full RTH sessions (2025-09-15..2026-08-18), 1 lot, friction 1.25 pt/RT, fills at the NEXT
minute's open. **n = 131 trades. mean +11.77 pt ($23.54), t = 0.68, day-block 95% CI
[−23.19, +46.31].** Halves: +1.97 then +21.43. Longs +9.51 (win 0.559), shorts +14.21 (win 0.444,
payoff 1.49). **PLACEBO** (identical machinery, σ band borrowed from a random other session):
+7.65, +9.43, −1.73 — the real band sits INSIDE the placebo spread.
VERDICT: **NOT ESTABLISHED, AND NOT REFUTED — the test had no power.** Per-trade sd is **198.95 pt**;
detecting the observed 11.77 pt at t=1.96 needs **1,097 trades ≈ 7.6 years**; detecting Zarattini's
own ~4.8 pt needs **~6,600 trades ≈ 46 years** at this trade rate. This is the power table in one
concrete case.

## Q2 — what actually works at retail scale (sources, graded)

### [9] ★ Independent replication of Zarattini & Aziz (2023) ORB on QQQ — the model of an honest test
URL: https://github.com/giovannibrusco/zarattini-2023-orb-qqq
Jan 2016 – Feb 2023, QQQ 5-min + NQ futures, $25,000 start. Matched the paper's trade count
(**1,775 vs 1,795**) and Sharpe (**1.06 vs 1.12**) — then diverged on costs: the paper assumed "zero
slippage in fills" for **$138,639 net PnL**; with execution costs that collapsed to **$4,860
(2.7% CAGR)**. Break-even at **~2.2¢/share** entry slippage against a ~1¢ QQQ spread — "the edge
exists only within the spread itself." **76% of the filtered P&L came from 2022 alone**; the filter
lost money in 2017, 2020 and early 2023. Bootstrap Sharpe CI **[0.05, 1.41]** vs buy-and-hold
**[−0.03, 1.47]** — overlapping.
★ One positive survived: the cross-asset NQ confirmation filter, **$0.125/share t=2.05**, against a
**09:25 pre-market-bar placebo at $0.079/share t=1.27**. Cross-asset information was real; its P&L
was a volatility-regime artefact.
GRADE: the best practitioner source found — published code, placebo control, bootstrap CIs, reports
what failed.

### [10] Order-flow imbalance — what the famous R² actually is
Cont, Kukanov & Stoikov (2014), J.Fin.Econometrics 12(1):47–88 · https://arxiv.org/pdf/1011.6402
50 US stocks, NYSE TAQ. OFI explains mid-price changes **"with an average R² of 65%"**, R²≥50% for
44/50. ⚠ That regression is **CONTEMPORANEOUS** — OFI and the price move are the same event. It is
not a forecast, and the desk's own null (book imbalance at leg starts ≈ 0.000) is the expected
result, not a surprise.
Andersen & Bondarenko (2014), "VPIN and the flash crash", J.Fin.Markets — **"when controlling for
current volume and volatility... no evidence of incremental predictive power of VPIN for future
volatility"**; VPIN peaked AFTER the flash crash, not before; its apparent content is "a mechanical
relation with the underlying trading intensity." ELO's rejoinder disputes the framing.
★ THE IMPORTED RULE: **any microstructure signal must be tested INCREMENTALLY to contemporaneous
volume and volatility, or it is measuring trading intensity.** That test is the one the desk should
apply to its own magnitude model.
Cross-asset lead-lag price discovery is documented but decays at millisecond horizons (Hayashi–
Yoshida estimator studies); with no co-location it is out of reach as a timing signal. The QQQ/NQ
result above is the retail-horizon version and it is small and regime-concentrated.

### [11] Event/calendar magnitude — the most robust magnitude fact in the literature
"Volatility after Payrolls increases by 6 times, with GDP, CPI and FOMC the next most important,
with volatility increases of 3–4 times." (announcement-volatility literature, incl. Andersen,
Bollerslev, Diebold & Vega).
★ THIS IS AN AUDIT RISK FOR THE DESK'S OWN BEST RESULT: the magnitude model's high state may be
largely "a scheduled release happened." Testable today with a free macro calendar — see ranked list.

## Q1 (cont) — is there a defensible retail route to selling, not buying, volatility?
### [12] Vilkov et al., 0DTE strategy study — annotated paper + code
URL: https://github.com/vilkovgr/0dte-strategies/blob/main/docs/paper/paper-annotated.md
09/2016 – 01/2026. Seven families (straddles/strangles, iron flies/condors, risk reversals, bull
call, bear put, call/put ratio spreads). Costs charged: **half the observed bid-ask + 0.5bp**.
- UNCONDITIONAL: "most strategies showed weak or negative returns after costs."
- CONDITIONAL (with timing): put ratio spreads **gross Sharpe 1.18, net 0.93**; diversified
  equal-weight basket **net ~0.82**.
- 0DTE VRP "economic magnitude is small" at same-day horizons: median realised VRP 10:00 ET → expiry
  ≈ **0.0011% of underlying**. Expected shortfall **0.58–1.58% of underlying**; "worst-day outcomes
  severe."
- Verdict quoted: **"Unconditional 0DTE exposure is difficult to justify as a standing allocation
  once one accounts for realistic execution and downside capital usage."**
★ READ: premium selling pays only CONDITIONALLY — i.e. it needs exactly the kind of timing signal the
desk already has, but pointed at the QUIET tail. This is the single open avenue in Q1.
⚠ SPX/SPY, not MNQ. Different account, different margin, and the desk's flat-overnight rule.

### [13] MNQ OPTION LIQUIDITY — NOT ESTABLISHED
cmegroup.com timed out on WebFetch twice and returned empty to curl (blocked). No primary source for
options-on-MNQ-futures volume, open interest or quoted spread was obtained. Everything else found was
broker/prop marketing. **Do not assume MNQ options are tradable at retail size until the chain is
measured.** Named capture test in the ranked list. Databento DOES list CME options on NQ
(databento.com/catalog/cme/GLBX.MDP3/options/NQ), so the history is purchasable.

## Q5 (cont) — prop-firm pass rates: vendor data only
FPFX Tech's ~300,000-account dataset (cited by several aggregators, not peer reviewed): **14% pass a
challenge; 45% of those reach a payout; ~7% ever see a payout.** FTMO's own 2024 transparency report:
~10–15% pass both phases. **All of this is self-reported by firms that sell challenges. It is not
evidence at the standard of [6] or [7] and should not be used as a base rate.**

## Q3 (cont) — the decay case study that landed this year
### [14] ★ "The Disappearing Overnight Drift", NY Fed Liberty Street Economics, JULY 2026
URL: https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
Original: Boyarchenko, Larsen & Whelan, "The Overnight Drift", RFS 36(9):3502–3547 (2023) —
the **02:00–03:00 ET** hour in **S&P 500 E-mini futures** earned **3.7% per annum** over
**1998–2020 (5,691 trading days)**, "more than 60 percent of the contract's 5.9 percent annualized
return." Mechanism: dealer inventory from end-of-day order imbalances unwound at the European open.
UPDATE: over **January 2021 – December 2025 (1,245 trading days)** the same window "averaged close to
zero" and is "flat". Proposed cause: "the standard deviation of end-of-day RSV fell from 6.5 percent
to 2.9 percent—a compression of more than half", i.e. "algorithmic liquidity providers slicing flow
more finely and transmitting less residual inventory onto end-of-day counterparties."
★ This is the cleanest recent example of a real, mechanism-backed, 22-year edge going to zero — and
it went to zero because the MECHANISM changed, not because of crowding into the signal. Do not build
it. (The desk is flat overnight by operator rule in any case.)
