# GREENFIELD HUNT — census "full" · cluster VACUUM

**Question asked:** ignore every gate we own. Invent a brand-new entry signal, from scratch, that shows
up for the runs the census filed under **VACUUM**. Spec it mechanically, backtest it tick-honest on
`capture.db` net of ~$5 a round-trip, and try hard to kill it.

**Answer up front: no survivor.** Three separate inventions, 90+ parameter cells, and one properly
walk-forwarded regime policy. The best honest number is **n=91, net −$443, 33% win, −$4.87 a trade,
and it showed up for 1 of the 8 VACUUM runs.** Every "winner" in the grid was three trades wide. The
detail below is the whole hunt, including the two things that would revive it.

---

## 1. What VACUUM actually is, and the trap in the label

The census calls a run VACUUM when, in the 60 seconds *before* the run, the net aggressor flow was
abnormal (|z| ≥ 1 against its own trailing 2 hours) and pointed the **opposite** way to the move that
followed. Plain English: the tape was full of buyers, and then price fell 80 points. Somebody ate all
that buying and the floor gave way underneath it.

There were **8 such runs** in the census window. Seven were sat out, one (08-04 11:40) was caught by
`abs_veto_long_A` for −$48. Here they are with what the tape looked like in the minute before.

| # | Run start (UTC) | Dir | Move | $ 1-lot | Flow (60s) | flow-z | Price result that minute | Pre-run ATR |
|---|---|---|---|---|---|---|---|---|
| 1 | 08-03 08:15 | DN | −80 | 160 | +204 | +1.92 | **+1.0 pt** (effort, no result) | 15.5 |
| 2 | 08-04 11:40 | UP | +84 | 168 | −196 | −1.26 | −4.75 pt | 9.4 |
| 3 | 08-04 19:44 | DN | −78 | 156 | +1082 | +2.82 | +15.0 pt (buy climax) | 13.0 |
| 4 | 08-06 05:59 | DN | −74 | 148 | +107 | +1.49 | +3.75 pt | 10.9 |
| 5 | 08-06 11:06 | UP | +78 | 156 | −258 | −2.67 | −15.5 pt (sell climax) | 17.1 |
| 6 | 08-06 15:10 | DN | −94 | 188 | +1211 | +1.68 | +20.0 pt (buy climax) | 25.6 |
| 7 | 08-06 15:48 | DN | −106 | 212 | +820 | +1.32 | +11.5 pt (buy climax) | 22.2 |
| 8 | 08-07 19:44 | UP | +69 | 138 | −252 | −1.00 | +2.25 pt (absorption) | 11.5 |

Total hindsight ceiling on the eight: **$1,326**. Six are DOWN runs preceded by buying; two are UP runs
preceded by selling.

**★ The trap, stated before any backtest.** VACUUM is a *label applied after the fact*, not a footprint
you can see coming. Across the tick tape there are **1,451 minutes** where |flow-z| ≥ 1. Eight of them
preceded a big run. That is a base rate of **0.55%**. Any signal that keys only on the flow-divergence
tell will fire roughly 300 times a day to find one of these. That number framed the entire hunt, and
in the end it is the finding.

## 2. The data honestly stated — this is a 5-day study, and it cannot be made longer

| Table | Coverage | Rows |
|---|---|---|
| `bars` 5s MNQ | 2026-07-15 → 08-07 (**17 trading days**) | 283,341 |
| `ticks` (aggressor-tagged) | 2026-08-03 → 08-07 (**5 days**) | 6,761,816 |
| `quotes` | 08-03 → 08-08 | 8,234,098 |
| `book` (L2, 5 levels) | 08-03 → 08-08 | 82,340,733 |

VACUUM is *defined* by aggressor flow, and aggressor flow only exists for 5 days. I tried to buy the
other 12 days by rebuilding signed flow from 5s bars (close-location-value, and the tick-rule on bar
closes) and validating it against the real thing on the overlap:

| Proxy | corr vs true 60s flow | corr of the **z-scores** (what the signal uses) | sign agreement |
|---|---|---|---|
| volume × close-location | 0.188 | **0.066** | 50.7% |
| volume × sign(Δclose) | 0.213 | **0.176** | 54.0% |
| (control) bar volume vs tick volume | **0.960** | — | — |

Bar volume is faithful. The **sign is not recoverable** at 5-second granularity — 50.7% agreement is a
coin toss. So: **there is no out-of-sample leg available for any flow-based VACUUM signal in this
repo.** Everything below is 5 days, in-sample, and I have leaned on leave-one-day-out, both-halves,
strip-the-best and a placebo null in place of the OOS I cannot have. That constraint is itself an
actionable finding — see §8.

**★ And the elephant: MNQ went UP 1,300 points in those 5 days.** Unconditional 15-minute drift was
**+2.73 pt with P(up) = 53.9%**. Any long-biased signal prints money in this window and any short-biased
one bleeds, for reasons that have nothing to do with the signal. Every number below is checked against
that baseline.

## 3. Three inventions, each fully specified

All three share the same trigger family — an abnormal 60-second aggressor burst — and differ in *when*
they take the trade against it.

**Common arming condition (all three).** At the close of each minute *t*: `f60` = net aggressor volume
(buy size − sell size) over the trailing 60s; `fz` = z-score of `f60` against the same statistic over
the trailing 120 one-minute buckets. Arm when **|fz| ≥ T**. `aggr` = sign(fz) = the side that was
pressing. `atr15` = mean 1-minute true range over the last 15 minutes.

### Invention A — FLOW-TRAP (FT)
> *"The burst failed and gave back everything. The people who did it are underwater. Sell them."*
- **Trigger:** within W = 10 minutes of the burst, price trades back through the **open of the burst
  minute** (the burst is fully retraced).
- **Direction:** against `aggr` (short a buy burst, long a sell burst).
- **Entry:** market, at the close of the 5s bar that made the retrace.
- **Stop:** the burst's extreme + 2 ticks — a new high/low in the aggressors' direction voids the trap.
- **Exit:** target at RM × R; hard time cap 45 min; stop wins ties inside a bar.
- **Guards:** 0.25·ATR ≤ R ≤ 3·ATR; 10-minute cooldown between trades.

### Invention B — ABSORPTION-SHELF (AS)
> *"All that effort and price did not move. It was eaten. Take the other side now, not later."*
- Same arming, plus **|price result over the burst minute| < P × ATR** (P = 0.35) — effort without
  result. No retrace wait.
- **Entry:** market at the burst minute's close. **Stop:** the burst extreme + 2 ticks. Same exits.

### Invention C — VACUUM-BREAK (VB) ← *the primary candidate*
> *"Don't fade the climax and don't wait for a tidy retrace. Wait for the floor under the trapped side
> to break — that break is the vacuum."*
- **Trigger:** define the **shelf** = the opposite extreme of the burst minute's range (its low if
  aggressors were buying). Within W = 10 minutes, price trades **1 tick beyond the shelf**.
- **Direction:** against `aggr`. **Entry:** close of the breaking 5s bar.
- **Stop:** the burst extreme + 2 ticks, **capped at 2·ATR**. **Exit:** RM × R, 45-min cap, stop-first.

Costs everywhere: **MNQ 1 lot, $2/point, $5 per round trip**, stop assumed hit before target when a 5s
bar spans both. No limit-fill optimism — entries are at bar closes, i.e. already past the level.

## 4. Inventions A and B: dead on arrival

| Invention | T | RM | n | net | $/trade | win% | Long | Short |
|---|---|---|---|---|---|---|---|---|
| FT | 1.5 | 1.5 | 220 | **−$1,492** | −6.78 | 36.4 | −$104 | −$1,387 |
| FT | 2.0 | 1.5 | 165 | **−$810** | −4.91 | 38.8 | +$187 | −$997 |
| FT | 2.5 | 1.5 | 111 | **−$692** | −6.24 | 33.3 | +$9 | −$702 |
| FT | 3.0 | 2.0 | 74 | **−$105** | −1.42 | 33.8 | +$136 | −$242 |
| AS | 1.5 | 1.5 | 210 | **−$1,191** | −5.67 | 37.6 | −$814 | −$376 |
| AS | 2.0 | 1.5 | 146 | **−$600** | −4.11 | 42.5 | −$302 | −$298 |
| AS | 3.0 | 1.5 | 54 | **−$451** | −8.36 | 37.0 | −$286 | −$165 |

**24 of 24 configs negative.** No cherry-picking required.

**And the reason, which is worth more than the P&L.** I stripped the stop and the target off FT
entirely and just asked what price does after the entry, cost-free:

| Horizon | mean move in our favour | win% | Long | Short | tape baseline |
|---|---|---|---|---|---|
| +5 min | −0.99 pt | 48.5 | +4.24 | −7.76 | +0.93 |
| +15 min | **+2.25 pt** | 52.1 | +7.27 | −4.22 | **+2.73 / 53.9%** |
| +30 min | +4.05 pt | 53.3 | +13.73 | −8.46 | **+5.34 / 55.5%** |

The signal's raw forward return is **below the tape's own unconditional drift at every horizon.** Its
information content is not small — it is *negative*. The long/short split is the drift and nothing else.
That is the cleanest kill in this document.

## 5. Invention C (VACUUM-BREAK): the one that looked alive, and the four tests that killed it

The full 77-cell sweep, net $ (rows = flow-z threshold T, columns = R-multiple target):

| T \ RM | 1.00 | 1.25 | 1.50 | 1.75 | 2.00 | 2.50 | 3.00 |
|---|---|---|---|---|---|---|---|
| 1.25 | −2429 | −2304 | −1853 | −1892 | −2198 | −2447 | −2107 |
| 1.50 | −1539 | −1331 | −2070 | −1868 | −1838 | −2856 | −2767 |
| 1.75 | −514 | −307 | −465 | −204 | −415 | −1762 | −1313 |
| 2.00 | −596 | +48 | −155 | +132 | −218 | −932 | −943 |
| 2.25 | −586 | +26 | +38 | +212 | +229 | −389 | −992 |
| 2.50 | −194 | +324 | +336 | +515 | +510 | −169 | −816 |
| 2.75 | −291 | −430 | −164 | +175 | +554 | −443 | −1069 |
| **3.00** | +145 | −14 | +262 | +576 | **+824** | −147 | −706 |
| 3.25 | +153 | −21 | +211 | +532 | +760 | −340 | −655 |
| 3.50 | −7 | −215 | +30 | +310 | +549 | −583 | −716 |
| 4.00 | +414 | +429 | +683 | +971 | +805 | −89 | −422 |

The corresponding trade counts fall from **250 → 47** top to bottom.

### TEST 1 — parameter sweep / n-collapse: **FAILED**
- **corr(net, −n) = +0.770.** The money appears in lock-step with the sample dying.
- 28 of 77 cells positive; **mean cell = −$468**. Positive cells' median n = 71; negative cells' median n = 133.
- It is not a plateau, it is a ridge with a cliff on both sides: at T=3.0, RM 1.75 → +$576, RM 2.00 →
  **+$824**, RM 2.50 → −$147, RM 3.00 → −$706. A knob you cannot be 0.5 wrong on is not a knob.

### TEST 2 — strip the 3 best trades: **FAILED**
Best cell VB T=3.0 / RM=2.0, n=70, net +$824, 44.3% win.

| | n | net | $/trade | win% |
|---|---|---|---|---|
| as found | 70 | **+$824** | +11.77 | 44.3 |
| strip best 1 | 69 | +$534 | +7.74 | 43.5 |
| strip best 2 | 68 | +$291 | +4.28 | 42.6 |
| **strip best 3** | 67 | **+$107** | **+1.59** | 41.8 |
| strip best 5 | 65 | **−$202** | −3.11 | 40.0 |

Three trades are 87% of the P&L. Five trades are all of it. (The three: 08-07 13:46 S +$290, 08-03 13:53
L +$243, 08-04 13:45 L +$184.) Every per-regime bucket is also negative after strip-3 — **all six of them**.

### TEST 3 — long/short symmetry: **FAILED**
| Side | n | net | $/trade | win% |
|---|---|---|---|---|
| Long | 38 | **+$950** | +25.01 | 52.6 |
| Short | 32 | **−$126** | −3.94 | 34.4 |

In a week MNQ rose 1,300 points. The **always-long control** — same 70 timestamps, same stop and target
geometry, but simply always long — makes **+$457**. So the signal's own contribution over "be long" is
**+$367**, which is smaller than the three trades strip-3 already removed. Note that six of the eight
VACUUM runs are *down* runs, i.e. the side of this signal that does not work.

### TEST 4 — the regime→config POLICY, scored walk-forward: **FAILED**
Per the desk's standing rule I never scored a blanket config. In-sample, each regime has a lovely best:

| Regime | best config in-sample | n | net | $/trade | median config in that regime |
|---|---|---|---|---|---|
| CLEAN-TREND | T2.5 / RM2.0 | 12 | +$676 | +56.37 | +$87 |
| VIOLENT-WHIPSAW | T3.0 / RM2.0 | 6 | +$372 | +62.00 | −$20 |
| NORMAL-CHOP | T2.5 / RM2.5 | 25 | +$219 | +8.78 | −$49 |
| QUIET-DRIFT | T2.5 / RM2.0 | 9 | +$111 | +12.30 | −$28 |
| DEAD-CHOP | T3.0 / RM2.0 | 7 | +$105 | +14.97 | −$9 |
| BUILDING | T3.0 / RM1.0 | 23 | +$58 | +2.51 | −$268 |

Then I picked each regime's config on **four days and traded it on the fifth**, rotating:

| held-out day | n | net |
|---|---|---|
| 2026-08-03 | 17 | +$532 |
| 2026-08-04 | 15 | −$167 |
| 2026-08-05 | 17 | −$229 |
| 2026-08-06 | 25 | −$714 |
| 2026-08-07 | 17 | +$134 |
| **TOTAL** | **91** | **−$443** |

**Walk-forward regime policy: n=91, net −$443, −$4.87/trade, 33.0% win, avg win +$67 / avg loss −$40,
long +$418 / short −$861, strip-3 −$1,109.** Exit mix: 60 stops, 26 targets, 5 time-outs.
The best static in-sample number was +$824 → **the config-selection tax is −$1,267.** Essentially the
whole headline was the act of choosing.

Per regime and per session, walk-forward:

| Regime | n | net | $/trade | win% |
|---|---|---|---|---|
| CLEAN-TREND | 14 | +$340 | +24.3 | 42.9 |
| VIOLENT-WHIPSAW | 7 | +$59 | +8.4 | 28.6 |
| DEAD-CHOP | 7 | +$14 | +2.0 | 57.1 |
| BUILDING | 22 | −$194 | −8.8 | 45.5 |
| QUIET-DRIFT | 6 | −$109 | −18.2 | 16.7 |
| NORMAL-CHOP | 35 | −$552 | −15.8 | 20.0 |

| Session | n | net | $/trade | win% |
|---|---|---|---|---|
| Overnight / pre-open (<13:00 UTC) | 60 | **−$698** | −11.6 | 31.7 |
| US session (13:00–21:00 UTC) | 31 | +$255 | +8.2 | 35.5 |

The only two regimes that survive the walk-forward are CLEAN-TREND (n=14) and VIOLENT-WHIPSAW (n=7),
and both go negative on strip-3. The bleed is concentrated in NORMAL-CHOP overnight — which is exactly
where six of the eight VACUUM runs live.

### TEST 5 — placebo null: **passed, and it does not matter**
Same 70 entry times, same stop/target geometry, **random direction**, 400 draws: mean −$344, sd $506.
The strategy's +$824 is **z = +2.31, one-sided p = 0.013**. Looks like a result — until you count the
grid: **77 cells × 0.013 ≈ 1.0 cell** expected to clear that bar by chance. I found exactly one. The
placebo is passing on the cell that was *selected for* passing it, so it carries no weight.

### TEST 6 — both halves and leave-one-day-out: **passed, weakly**
Both halves positive (08-03/04 +$423 on 25; 08-05 +$77 on 15; 08-06/07 +$325 on 30) and every LOO drop
stays positive (+$246 to +$1,077). This is the one place the candidate looked respectable — and it is
explained entirely by the fact that the long side works every day in a melt-up week. LOO does not
disturb a drift bias, so it cannot see this failure mode. Recorded, not credited.

## 6. Big moves caught — the number that actually settles it

Aligned direction, fired within ±15 minutes of the run start.

| Configuration | caught | net on the hits |
|---|---|---|
| **Walk-forward regime policy (the honest deployable answer)** | **1 / 8** | +$49 |
| VB T=3.0 / RM=2.0 (best static cell) | 1 / 8 | +$68 |
| VB T=2.0 / RM=1.5 (mid) | 2 / 8 | −$8 |
| VB T=1.5 / RM=1.5 (loosest; itself −$2,070) | 3 / 8 | +$48 |
| FT T=1.5 / RM=1.5 (loosest; itself −$1,492) | 4 / 8 | +$93 |
| **Union of all 20 policy configs — the most generous read possible** | **4 / 8** | — |

And the operator's specific hypothesis — *narrow to the biggest runs and a stronger footprint may
appear* — **runs the wrong way here.** Ranked by size, the three biggest VACUUM runs (08-06 15:48
−106pt, 08-06 15:10 −94pt, 08-04 11:40 +84pt) are missed by **every single configuration of all three
inventions.** The only run any honest config catches is 08-06 11:06 (+78pt, the second *smallest*). The
big ones are the two 15:0x buy-climaxes on 08-06 in a 22–26pt-ATR US session — the burst was enormous
(+1,211 and +820 contracts) and price kept going *up* for several more minutes before rolling, so the
shelf-break trigger arrived far too late and the retrace trigger never fired at all inside its 10-minute
window. Narrowing to the biggest runs does not sharpen the footprint; it removes the only hits.

## 7. Disposition table

| Lead | Verdict | The named test that decided it / what would revive it |
|---|---|---|
| **A. FLOW-TRAP (FT)** — fade a failed aggressor burst on the full retrace | **REFUTED** | Cost-free forward-return test: the entry's raw 15-min return (+2.25 pt, 52.1% up) is **below the tape's own unconditional drift** (+2.73 pt, 53.9% up) at every horizon 5/15/30 min. 12/12 configs negative, n up to 220. There is no exit rule that saves an entry with negative information content, so no reformulation of the exit is a path. |
| **B. ABSORPTION-SHELF (AS)** — fade an aggressor burst that produced no price result | **REFUTED** | 12/12 configs negative (−$1,191 at n=210 down to −$410 at n=54), and losing on **both sides** (L −$302 / S −$298 at T=2.0), so it is not even a drift artefact — it is just wrong. The "effort without result" split showed no separation in the base-rate study either (|fz|≥1 with near-zero result: 47.5% win at H15, the *worst* of the four result buckets). |
| **C. VACUUM-BREAK (VB)** — enter on the break of the shelf under the trapped side | **PARKED** | Killed as built by **strip-the-3-best** (+$824 → +$107; strip-5 → −$202) and by the **walk-forward regime policy** (−$443 over 91 trades, selection tax −$1,267). **REVIVE IF:** (a) we accumulate a **down-trending or genuinely range-bound week** so the +1,300pt drift stops doing the work — the short side must clear −$0/trade on its own, it is currently −$3.94; **and** (b) n ≥ 200 walk-forward trades, which needs **≈15 trading days of aggressor-tagged ticks** (we have 5). Both are free to wait for. Put it in the shadow book at **T=2.5, RM=1.75, US session only**, which is the only sub-plateau with adjacent cells all positive (+$324/+$336/+$515/+$510). |
| **D. Bar-derived flow proxy** (to extend VACUUM work onto the 17-day bar tape) | **REFUTED** | Validation against real tick flow on the 6,779-minute overlap: z-score correlation **0.066** (close-location) and **0.176** (tick-rule), sign agreement **50.7% / 54.0%**. Bar *volume* is faithful (r=0.96); the *sign* is unrecoverable at 5s granularity. No reformulation at bar resolution recovers a sign that is not in the data. |
| **E. Raw conditional "fade the sell-burst" (fz ≤ −1 → long)** | **PARKED** | The one genuinely large-n signal in the study: n=519, +8.91 pt at H15, 59.7% win, **+6.19 pt of excess over drift**. But its mirror (fz ≥ +1 → short) is **−1.00 pt of excess** and loses real money, and 519 overlapping 15-min windows in 4.7 days is perhaps 25 independent observations. **REVIVE IF:** the short mirror clears zero excess on a flat or down week. Until then it is "buy the dip in a melt-up" wearing a microstructure costume. |
| **F. Book/L2 "vacuum" reading** (thin far-side depth confirming the move) | **PARKED** | Tested as a filter on the fade: the intuitive version — trade the way the book leans — **loses** (n=772, −$0.88/trade at H15, 48.6% win) while trading *against* the book lean wins (n=679, +$3.36, 54.5%), which is the opposite of the mechanism and is again just the long side. **REVIVE IF:** re-cut on **queue depletion rate** (how fast a level is consumed) rather than static average depth — I only used mean L1–L5 size per minute, which cannot see a level being eaten and instantly replenished. That is a real unturned stone and the 82M-row `book` table supports it. |

**★ The one stone still unturned:** every version here measured the book as a *static average depth per
minute*. The actual "vacuum" claim is dynamic — **how fast the resting size at the touch disappears and
whether it comes back**. `capture.db` has 82.3M L2 rows at ~190 snapshots/second, which is enough to
build a queue-replenishment rate. That is the next attack and it is the only one I would fund.

## 8. What to take away

1. **VACUUM is a description, not a signal.** 1,451 qualifying flow-divergence minutes produced 8 big
   runs — 0.55%. The label tells you what happened; it does not tell you it is about to happen.
2. **The 5-day tick wall is the binding constraint on this whole cluster,** and it is fixable by
   nothing except time. If VACUUM work matters, the action is *keep capturing ticks* — at ~1.35M
   ticks/day we need roughly 15 sessions before any of this can carry a real out-of-sample leg.
3. **This week's +1,300 point melt-up is a P&L illusion generator.** Every apparently-good result in
   this study was the long side. The always-long control at the identical timestamps made +$457 of the
   winner's +$824. Any Friday-report number computed on 08-03→08-07 without a long/short split should
   be treated as suspect.
4. **The regime-policy discipline paid for itself here.** The blanket best config said +$824. The same
   idea, honestly walk-forwarded regime by regime, said −$443. That −$1,267 gap is what the discipline
   is for.

*Working: `/home/alphabot/gazbot7/scratchpad/gf_vac/` (`ft3.py` = FT/AS engine, `vb.py` = VACUUM-BREAK,
`battery.py` = robustness battery, `policy.py` / `final.py` = walk-forward policy + big-moves-caught,
`proxy.py` = bar-proxy validation). Data: `data/capture.db`, read-only, DuckDB.*
