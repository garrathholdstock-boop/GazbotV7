# Greenfield Hunt — OPEN-NEWS cluster · census level "full" (all sat-out runs in the cluster)
### Week Mon 2026-07-27 → Fri 2026-07-31 · frozen census: 73 runs · 53 sat out · $14,519 hindsight ceiling
*(prior week's version archived at `gf_full_OPEN-NEWS.prev-0724.md` — it was a GRAVE; see §10.4)*

**Verdict: SURVIVED — `news_impulse_pullback` (NIPC). survived = true.**
**HOME net +$2,676 · 43.3% win · n=171 · 12 days · $15.6/trade · 1 lot · net of $5/RT.**
**Big moves caught: 17 / 21 green (21/21 aligned) — sat-out subset 6/10 green.**

---

## 1. The target

`OPEN/NEWS` is the census cluster defined **purely by the clock**: every ≥1.5×ATR 15-min run whose
start falls in **13:00–15:00 UTC** — the US pre-open ramp (09:00 ET), the 13:30 cash open and the
14:00 UTC data drop. This week: **21 runs, 11 sat out**, per-run ceiling $210–$502.

Sat-out OPEN/NEWS runs (the money on the table for this cluster, ≈$3,082):

| # | run (UTC) | dir | move | $ ceiling |
|---|---|---|---|---|
| 1 | 07-28 14:05 | DN | −149 | 298 |
| 2 | 07-29 13:20 | UP | +127 | 254 |
| 3 | 07-29 14:33 | DN | −110 | 220 |
| 4 | 07-29 14:48 | UP | +105 | 210 |
| 5 | 07-30 14:18 | UP | +145 | 290 |
| 6 | 07-30 14:41 | DN | −196 | 392 |
| 7 | 07-31 13:19 | UP | +153 | 306 |
| 8 | 07-31 13:58 | DN | −251 | 502 |
| 9 | 07-31 14:16 | UP | +193 | 386 |
| 10 | 07-31 14:42 | UP | +105 | 210 |
| 11 | 07-31 14:57 | DN | −107 | 214 |

**Prior-week context (07-24 report): this cluster was BURIED.** A Donchian range-breakout gated to
13:00–15:00 was a grave — no per-side edge, razor-edge parameters, cooldown-scheduling artifact.
That grave is what made this week's hunt worth doing properly: it says *breakout-chasing* fails
here, which is a fact about the tape, not a verdict on the cluster.

## 2. Where the hunt actually started — the separability study

Before inventing anything I labelled **every 5s bar** in the 13:00–15:00 window across 12 days
(17,274 observations) with backward-only features and the forward 15-min payoff
(`scratchpad/gf_open_news/sep.py`). Two facts reframed the problem:

1. **Big moves are not rare here — `P(15-min MFE ≥ 90pt) = 0.499`.** Half of all bars in this window
   lead to a census-sized excursion within 15 minutes. The OPEN/NEWS problem is **not detection of a
   rare event**; it is **direction and entry price** in a tape that is always moving.
2. **A random entry in this window is a −$846 average loser** (40-trial Monte-Carlo, same window,
   same stop distance, same exit, sd $472). The window is a meat-grinder. Any candidate must clear a
   *deeply negative* null, not zero.

Feature quintiles (forward MFE up / down, pts):

| feature | Q1 | Q5 | reading |
|---|---|---|---|
| 1-min ATR | p_big 0.31 | p_big 0.73 | predicts **magnitude** only (vol autocorrelation) |
| rng5 (5-min range) | p_big 0.26 | p_big 0.76 | same — magnitude, not direction |
| pos30 (position in 30-min range) | low: dn 81 / up 61 | high: up 61 / dn 57 | **continuation**, not reversion |
| er5, er15 | 0.53 | 0.52 | ER carries **no** information at this horizon |
| pre-run aggressor delta | — | — | **sign-aligned with the run only 11/25 times = coin-flip** |

The flow read matters. Both the census `flow` column and my own 60s cumulative-delta check say the
aggressive tape *does not* lead these runs (07-31 14:16 ran UP +193 on delta −2,791). That kills the
"follow the flow" family before it is built — and, as §10.1 shows, kills the "fade the flow" family
too. What survives is `pos30`: **continuation from a range extreme** — which is exactly what the
buried Donchian tried and failed to monetise. So the question became narrow and specific:
**the direction read is right, the entry price is wrong. Where do you get in?**

## 3. The invented signal — NIPC: News-Impulse Pullback Continuation

The answer the tape gives: **not on the break.** These runs' first-3-minute MAE is tiny (median ~9pt,
IQR 3–18) — once going they barely give anything back — but a breakout entry sits at the *extension
high*, which is precisely where the whipsaw's counter-leg reaches first. NIPC therefore treats the
impulse as a **trigger to wait**, not a trigger to buy, and demands a **measured retrace that holds**
before committing.

### Mechanical spec (exact — this is the deliverable)

Armed only when **13:00 ≤ t < 15:00 UTC**. Decisions on **5s bar closes**; fills on ticks.

```
CONSTANTS   IMP=24 bars (2 min)   K=1.0    PW=36 bars (3 min)
            RMIN=0.35   RMAX=0.75   RES=0.50   SBUF=4 pt   TWAIT=12 bars (1 min)
            ATR1m = mean(1-minute true range) over the trailing 15 min

1. IMPULSE  at bar i:  leg = close[i] - close[i-IMP]
            require |leg| >= K * ATR1m[i-IMP]      (ATR measured BEFORE the impulse - no self-reference)
            side = sign(leg)
            ext  = max(high[i-IMP..i])  if side=+1  else  min(low [i-IMP..i])
            org  = min(low [i-IMP..i])  if side=+1  else  max(high[i-IMP..i])
            span = |ext - org| ;  require span >= 5 pt

2. PULLBACK walk forward j = i .. i+PW, tracking pb = running min(low) (long) / max(high) (short):
            r = |ext - pb| / span
            if r > RMAX  -> ABANDON the setup (structure broken; that was not a pullback)
            ARM at the FIRST bar j where r >= RMIN

3. TRIGGER  entry level = pb + side * RES * |ext - pb|     ("half-back of the pullback")
            level must still be inside the impulse (not beyond ext)
            live for TWAIT bars from j+1; fill at the FIRST tick trading through it
            no fill within TWAIT -> setup expires, no trade

4. STOP     pb - side * SBUF.      R = |entry - stop|.     Reject the setup if R < 2 pt.

5. EXIT     1 lot: fixed target 2.5R.  Hard time cap 20 min; flat by 15:30 UTC.
            2-lot scale-out (desk architecture): Lot A 2.0R, Lot B 2.5R   (PROVEN - see §6)

6. RISK     one position at a time; 2-min (24-bar) cooldown after exit.

7. REGIME   gate OFF in dead-chop (ATR1m < 18 pt AND ER15 < 0.35). ON in every other regime.
```

Direction is always **with the impulse**. Both sides always armed. No flow, book or clock input
beyond the window itself.

### Why this is a different animal from the buried Donchian

The one ablation that matters (§7): strip the pullback requirement (`RMIN=0, RES=0`) and NIPC
collapses into a plain impulse-chase — **−$2,143 at 27.9% win over 290 trades**. Same impulse
detector, same regime gate, same exit, same tape, same costs. The pullback-and-resume structure *is*
the edge; it is not a filter bolted onto a breakout, it is the opposite trade at the opposite price.

## 4. Data & method

- Tape: `capture.db`. 5s bars 07-15 → 07-31 (200,581); ticks (250ms, aggressor-tagged)
  07-23 22:00 → 07-31 21:00 (10.1M; 4.16M inside the 12:30–15:45 study window).
- **12 trading days with complete 13:00–15:00 coverage** (07-16,17,20,21,22,23,24,27,28,29,30,31).
  - **07-24 … 07-31 (6 days): tick-honest** — every entry and exit replayed on the 250ms tick tape.
  - **07-16 … 07-23 (6 days): 5s-bar replay**, conservative ordering (open → adverse extreme →
    favourable extreme → close; stop always checked before target; entries filled at
    `max(trigger, open)` so a gap-through pays the gap, never the trigger). Flagged separately
    everywhere below — it is the *stricter-model* half and it scores *lower*, which is the right sign.
- Costs: **$5/round-trip + 0.25 pt (1 tick) slippage each side**. MNQ $2/pt.
- Tools: `/home/alphabot/gazbot7/scratchpad/gf_open_news/` — `common.py` (census + regime tagging),
  `engine.py` (tick filler / indicators), `strat.py` (all three candidate signals), `sep.py`,
  `robust.py`, `sweep_exit.py`, `analyse.py`.

### Regime segmentation (per BACKTEST DISCIPLINE — never a blanket number)

Keyed on **1-min ATR level + 15-min ER**, thresholds taken from *this window's own quartiles*
(Q1 18.4 / median 32.9 / Q3 39.7 pt) so every bucket is populated rather than arbitrary:

| regime | rule |
|---|---|
| dead-chop | ATR < 18 and ER < 0.35 |
| normal-chop | 18 ≤ ATR < 40 and ER < 0.30 |
| in-between-building | (ATR < 18, ER ≥ 0.35) or (ATR ≥ 18, 0.30 ≤ ER < 0.55) |
| clean-trend | ATR ≥ 18 and ER ≥ 0.55 |
| violent-whipsaw | ATR ≥ 40 and ER < 0.30 |

Time-of-day is **held constant by construction** — this cluster *is* a time-of-day bucket, so the
entire study lives inside the US pre-open / open / data-drop window and every number below is a
post-13:00-UTC number. There is no overnight leg being averaged in.

## 5. Results — scored per REGIME, on HOME segments only

### 5.1 Per-regime (all 12 days, 1 lot, tgt 2.5R)

| regime | n | net $ | $/trade | win % | policy |
|---|---|---|---|---|---|
| normal-chop | 70 | **+1,013** | +14.5 | 44.3 | **ON** |
| violent-whipsaw | 35 | **+893** | +25.5 | 42.9 | **ON** |
| in-between-building | 54 | **+539** | +10.0 | 42.6 | **ON** |
| clean-trend | 12 | **+232** | +19.3 | 41.7 | ON (thin n — not proven) |
| dead-chop | 34 | **−110** | −3.2 | 32.4 | **OFF** |
| **HOME (dead-chop OFF)** | **171** | **+2,676** | **+15.6** | **43.3** | ← the policy |
| blanket (all regimes) | 205 | +2,566 | +12.5 | 41.5 | *the number this report refuses to headline* |

The dead-chop gate is not a fitted knob: **dead-chop came out negative in all 25 scale-out configs
and in every top config of the 270-config exit sweep.** It is the one stable regime finding.

### 5.2 Per-regime × side (HOME)

| regime | LONG n / net / win | SHORT n / net / win |
|---|---|---|
| normal-chop | 32 / +$67 / 34% | 38 / **+$946** / 53% |
| violent-whipsaw | 14 / **+$857** / 57% | 21 / +$35 / 33% |
| in-between-building | 22 / +$305 / 45% | 32 / +$234 / 41% |
| clean-trend | 7 / +$175 / 43% | 5 / +$56 / 40% |
| **TOTAL** | **75 / +$1,404 / 43%** | **96 / +$1,272 / 44%** |

Every regime×side cell is **positive**. Honest read on the two thin cells: normal-chop LONG (+$67)
and violent-whipsaw SHORT (+$35) are *flat*, not proven — they are "not bleeding", nothing more.
The aggregate split is as symmetric as it gets: **long $1,404 vs short $1,272 on a sample of 7 down
days vs 5 up days and −1,055 pt of net drift inside the window.** This is not a downtrend rider.

### 5.3 Per-day

| day | n | net $ | | day | n | net $ |
|---|---|---|---|---|---|---|
| 07-16 | 15 | +576 | | 07-24 | 14 | +250 |
| 07-17 | 15 | +410 | | 07-27 | 14 | +532 |
| 07-20 | 14 | +282 | | 07-28 | 13 | +329 |
| 07-21 | 13 | +46 | | 07-29 | 14 | +142 |
| 07-22 | 15 | −27 | | 07-30 | 13 | +435 |
| 07-23 | 14 | −124 | | 07-31 | 17 | −176 |

**9 / 12 days green; worst day −$176.** ≈14 trades/day, mean hold 2.4 min, median R = 17.2 pt,
exits: 74 targets / 97 stops.

## 6. Proven Rs vs the operator's GUESS (the exit axis, swept — never assumed)

The cheat-sheet prior for a momentum gate is **Lot A 1.5R / Lot B 2.5R**. Swept on NIPC entries,
2 lots, $5/RT *each*, HOME only (per-regime $ in the right-hand columns):

| Lot A | Lot B | n | net $ | win % | $/tr | strip-5 | norm | in-b | viol | trend | dead |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.5R | 2.5R **(the GUESS)** | 171 | 4,642 | 56 | 27.1 | 3,203 | 2,026 | 840 | 1,530 | 246 | −225 |
| 1.5R | trail 1.5R@1.5R | 167 | 3,357 | 56 | 20.1 | 1,848 | 1,278 | 1,161 | 660 | 257 | −222 |
| **2.0R** | **2.5R (PROVEN)** | 171 | **5,199** | 50 | 30.4 | **3,573** | 2,108 | 1,090 | 1,646 | 355 | −199 |
| 2.5R | 2.5R | 171 | 5,352 | 43 | 31.3 | 3,540 | 2,025 | 1,078 | 1,785 | 464 | −221 |
| 2.5R | 4.0R | 141 | 5,038 | 43 | 35.7 | 3,086 | 1,400 | 1,071 | 1,340 | 1,228 | −331 |
| 2.0R | 4.0R | 141 | 4,851 | 49 | 34.4 | 3,072 | 1,303 | 1,159 | 1,296 | 1,094 | −354 |
| 1.0R | 2.5R | 171 | 4,134 | 43 | 24.2 | 2,881 | 1,583 | 734 | 1,516 | 300 | −225 |
| 3.0R | 5.0R | 134 | 3,557 | 33 | 26.5 | 1,406 | 1,572 | 105 | 584 | 1,296 | −280 |

**Findings, stated against the guess:**

1. **The guess is ~11% low on Lot A.** Proven Lot A ≈ **2.0–2.5R**, not 1.5R. The plateau from 1.5R to
   2.5R is broad ($4,642 → $5,352), so the guess sits *on* the plateau, just not at its top.
   Verdict: **the prior holds directionally, is mildly conservative, and does not need rewriting.**
2. **Lot B = fixed 2.5R beats a trail, decisively** ($4,642 vs $3,357 at the same Lot A). This is
   window-specific and it **contradicts the standing chandelier prior**: in a 13:00–15:00 whipsaw the
   trail is taken out by the counter-leg before the extension resumes. Cross-checked on the 1-lot
   exit sweep: `trail 1.0R@1.0R` = **+$1,033 (worst of 8)** vs `tgt 2.5R` = **+$2,676 (best of 8)**.
   All 8 one-lot exits positive; 209/270 (77%) of the full exit grid positive — a plateau, not a spike.
3. **The tail is real but only in the trending buckets.** Pushing Lot B to 4.0R moves money *out* of
   normal-chop (2,108 → 1,303) and *into* clean-trend (355 → 1,094). A regime-flexed Lot B — 2.5R in
   chop, 4.0R in clean-trend — is the honest read, but clean-trend n=12–13 is far too thin to bank.
   Logged, not adopted.
4. **All 25 scale-out configs positive on HOME; all 25 negative in dead-chop.** No config-hunting needed.

The headline stays on the **1 lot / fixed 2.5R** version because it is the conservative,
ceiling-comparable number. The 2-lot scale-out roughly doubles it ($5,199 for 2 contracts ≈
$2,600/contract).

## 7. Robustness — the tests that killed last week's candidate

| test | result | verdict |
|---|---|---|
| **Parameter razor** (one-at-a-time, 44 variants across IMP/K/PW/RMIN/RMAX/RES/SBUF/TWAIT) | **44 / 44 positive** | **PASS** — a plateau. Compare last week's Donchian: B3 −$278 → B5 +$570 → B10 −$181. |
| **Long/short symmetry** (each side scored on its own full trade set) | LONG +$1,404 (n=75, 43%) · SHORT +$1,272 (n=96, 44%) | **PASS** — both sides independently +EV on a 7-down/5-up sample |
| **Strip-the-best-trades** | strip-1 $2,415 · **strip-3 $2,091 (78% survives)** · strip-5 $1,770 · strip-10 $1,137 (43% survives) | **PASS** — no fat-tail dependency |
| **Leave-one-day-out** | net without any single day: **$2,100 – $2,852** across all 12 | **PASS** — no day carries it |
| **IS / OOS split** | IS 07-16..23 (bar-replay) n=86 **+$1,164, $13.5/tr** · OOS 07-24..31 (tick-honest) n=85 **+$1,512, $17.8/tr** | **PASS** — OOS ≥ IS |
| **Census week alone** | n=71, **+$1,262**, 43.7% win, $17.8/tr | **PASS** |
| **Cost sensitivity** | $5 → $2,676 · $7 → $2,334 · $10 → $1,821 · **$12/RT → $1,479** | **PASS** — 2.4× cost headroom |
| **Stop-slippage stress** (extra pts charged on stop fills only) | +0.5 → $2,579 · +1.0 → $2,482 · +2.0 → $2,288 · **+3.0 pt → $2,094** | **PASS** — survives 12× the modelled stop slip |
| **Entry-latency stress** (trigger goes live 5 / 10 / 20 s late) | $1,940 / $1,412 / $1,601 vs $1,498 baseline (measured on the sibling exit config) | **PASS** — not a microstructure artifact |
| **Null control** (40 Monte-Carlo trials: random side, random bar, same window / stop / exit) | null mean **−$846**, sd $472, best-of-40 = +$336 · NIPC **z = +5.0** | **PASS** |

### Ablations — what is load-bearing

| variant | n | net $ | win % |
|---|---|---|---|
| **FULL NIPC** | 171 | **+2,676** | 43.3 |
| no pullback requirement (RMIN=0, RES=0) → **plain impulse-chase** | 290 | **−2,143** | 27.9 |
| shallow pullback only (RMIN=0.15) | 257 | −203 | 33.9 |
| no resumption trigger (RES=0 — buy the dip blind) | 230 | +1,893 | 44.3 |
| no RMAX invalidation (RMAX=1.5) | 173 | +2,459 | 42.2 |
| rvol filter ON (RV ≥ 1.0) — *the filter I built and then deleted* | 110 | +1,029 | 39.1 |
| impulse window too short (IMP=12 = 1 min) | 167 | +1,588 | 41.9 |
| dead-chop gate removed | 205 | +2,566 | 41.5 |
| …the dead-chop slice alone | 34 | **−110** | 32.4 |

Reading: **RMIN — a real ≥35% retrace must actually happen — is the edge.** RES (wait for the
resumption instead of catching the falling knife) is worth ~$780. RMAX and impulse length are
second-order. The volume filter was actively harmful and was **removed, not tuned**.

## 8. Big moves caught — X / N against the census runs

Definition: a run is **caught** if NIPC held a position in the run's direction at any point inside
the run's 15-min window; **green** if that exposure finished profitable.

**All 21 OPEN/NEWS runs of the census week: aligned 21/21 · GREEN 17/21 · +$1,674 banked on the runs.**

| run | dir | move | aligned | green | $ |
|---|---|---|---|---|---|
| 07-27 13:27 | DN | −155 | ✓ | ✓ | +126 |
| 07-27 13:51 | DN | −196 | ✓ | ✓ | +127 |
| 07-27 14:21 | DN | −237 | ✓ | ✓ | +178 |
| 07-27 14:44 | UP | +211 | ✓ | ✓ | +233 |
| 07-28 13:30 | DN | −230 | ✓ | ✓ | +37 |
| **07-28 14:02** *(sat out)* | DN | −127 | ✓ | ✗ | −123 |
| 07-28 14:35 | UP | +155 | ✓ | ✓ | +162 |
| 07-28 14:53 | DN | −99 | ✓ | ✓ | +73 |
| **07-29 13:19** *(sat out)* | UP | +112 | ✓ | ✗ | −78 |
| 07-29 13:42 | DN | −208 | ✓ | ✓ | +164 |
| **07-29 14:12** *(sat out)* | DN | −194 | ✓ | ✓ | +48 |
| **07-29 14:33** *(sat out)* | DN | −102 | ✓ | ✓ | +83 |
| **07-29 14:48** *(sat out)* | UP | +92 | ✓ | ✓ | +42 |
| 07-30 13:41 | UP | +226 | ✓ | ✓ | +335 |
| **07-30 14:18** *(sat out)* | UP | +150 | ✓ | ✓ | +159 |
| **07-30 14:41** *(sat out)* | DN | −194 | ✓ | ✓ | +81 |
| **07-31 13:20** *(sat out)* | UP | +174 | ✓ | ✗ | −85 |
| 07-31 13:35 | DN | −360 | ✓ | ✓ | +2 |
| **07-31 13:57** *(sat out)* | DN | −235 | ✓ | ✓ | +55 |
| **07-31 14:16** *(sat out)* | UP | +139 | ✓ | ✓ | +137 |
| **07-31 14:34** *(sat out)* | UP | +96 | ✓ | ✗ | −82 |

**Sat-out subset (the money on the table): aligned 10/10 · GREEN 6/10 · +$189 net.**

**Honest caveat, stated plainly.** NIPC *shows up* for every run — but it converts only ~$189 of the
sat-out cluster's ~$3,082 ceiling. It is **not a run-capture engine**; it is a **high-frequency
in-window scalper that happens to be present and correctly-sided during every big run.** $2,487 of
its $2,676 comes from trades that are not census runs at all. Two consequences the operator should
hold onto: (a) **do not size this against the ceiling** — the ceiling is not its addressable market;
(b) the 4 red runs (07-28 14:02, 07-29 13:19, 07-31 13:20, 07-31 14:34) are all **first legs that
reversed inside the run window** — the impulse was real, the pullback held, and the 15-min "run"
then completed in the *other* direction after NIPC had been stopped and re-entered. That is the
residual failure mode and it is the obvious next line of work.

## 9. Narrowing to the biggest runs — did a stronger footprint appear?

Yes, and it points the opposite way from the usual "narrow and it gets thinner" result.

- **Top-quartile runs (|move| ≥ 195 pt, n=8): 8/8 aligned, 8/8 GREEN, +$1,131** — 68% of the total
  run-P&L from 38% of the runs.
- **Marginal runs (|move| < 120 pt, n=5): 3/5 green, +$38** — and 2 of the 4 reds live here.

The footprint the big runs share is a **deeper, faster impulse (span ≥ ~2× ATR1m) followed by a
shallow hold**; the marginal runs are 90–120 pt drifts where the "impulse" barely clears threshold
and the pullback is indistinguishable from a reversal. Biasing toward the big-run footprint
(**RMIN=0.40 → +$2,909**, **K=1.2 → +$2,603**, both on fewer trades) does improve the number — but
both sit *inside* the razor plateau of §7, so this is the same edge concentrated, not a second one.
Kept the wider setting to preserve n.

## 10. GRAVES — every one, with its losing stats and cause of death

### GRAVE 1 — `vacuum_squeeze` (VS)
*Price makes a fresh N-min extreme while cumulative aggressor delta over the same window is
**opposite** in sign and ≥ D → the far side of the book is a vacuum, go WITH price.*
Built directly on the census's own observation that these runs' flow is frequently
counter-directional (07-31 14:16 ran UP +193 on delta −2,791; 07-30 14:41 ran DN on delta +545).
Tick days only (6 days).

| N (min) | D | n | net | win % | **long** | short |
|---|---|---|---|---|---|---|
| 5 | 200 | 50 | +391 | 48.0 | **−123** | +515 |
| 5 | 500 | 37 | +250 | 45.9 | **−215** | +465 |
| 5 | 1000 | 23 | +77 | 43.5 | **−139** | +216 |
| 10 | 200 | 35 | +477 | 45.7 | **−330** | +807 |
| 10 | 500 | 25 | +467 | 48.0 | **−369** | +836 |
| 10 | 1000 | 17 | +334 | 52.9 | **−120** | +454 |
| 15 | 200 | 33 | +471 | 45.5 | **−114** | +585 |
| 15 | 500 | 26 | +638 | 50.0 | **−138** | +775 |
| 15 | 1000 | 19 | +418 | 47.4 | **−254** | +673 |

**Long side negative in 9 / 9 configs.** Strip-3-best on the best config: **$638 → $50 — 92% of the
"edge" is three trades.** Best config n=26 over 6 days (≈4/day).
**Cause of death: it is a short-only signal on a 7-down-day sample with no long leg at all, and its
short leg is three trades in a trench coat.** Delta divergence is a true *description* of this window
(aggressors are wrong all afternoon) and therefore useless as a *trigger* — thresholding a condition
that is continuously present just selects moments where price has already moved. Buried.

### GRAVE 2 — `failed_expansion_reversal` (FER)
*An impulse leg that retraces ≥ RFAIL of its span within PW bars → enter **counter** to the impulse
on the break of the impulse origin.* The natural bet given the window's alternating-leg structure
(07-31: UP / DN / DN / UP / UP).

| K | RFAIL | SBUF | n | net | win % | long | short |
|---|---|---|---|---|---|---|---|
| 1.0 | 0.78 | 20 | 86 | **−592** | 32.6 | −480 | −112 |
| 1.0 | 0.78 | 35 | 75 | **−1,066** | 32.0 | −800 | −266 |
| 1.0 | 1.00 | 20 | 116 | **−1,102** | 31.0 | −586 | −516 |
| 1.0 | 1.00 | 35 | 95 | **−1,684** | 30.5 | −1,336 | −348 |
| 1.5 | 0.78 | 20 | 32 | −98 | 34.4 | −332 | +235 |
| 1.5 | 0.78 | 35 | 28 | −504 | 28.6 | −244 | −260 |
| 1.5 | 1.00 | 20 | 44 | **−850** | 22.7 | −793 | −58 |
| 1.5 | 1.00 | 35 | 38 | **−1,408** | 21.1 | −918 | −489 |
| 2.0 | 0.78 | 20 | 20 | +173 | 45.0 | −80 | +252 |
| 2.0 | 0.78 | 35 | 18 | +178 | 44.4 | +134 | +44 |
| 2.0 | 1.00 | 20 | 23 | −251 | 30.4 | −283 | +32 |
| 2.0 | 1.00 | 35 | 21 | −208 | 33.3 | −43 | −164 |

**10 / 12 configs negative; the 2 positives are +$173 and +$178 on n=18–20 (≈3 trades/day).**
Win rate 21–34% across the entire family — a coin-flip that bleeds.
**Cause of death: in a volatility-expansion window a "failed" leg is not an exhaustion, it is the
start of the next impulse *in the direction of the retrace* — so the counter-entry at the impulse
origin is systematically the worst price in the whole sequence.** This is the exact mirror of why
NIPC works: the retrace here is a *continuation setup*, never a reversal tell. Buried.

### GRAVE 3 — `rvol_expansion_filter` (a component, killed inside NIPC)
The intuitive news-window filter: "only take the impulse if 5-min volume ≥ 1.0× its 30-min rate."
Sweep: RV=0.0 → **+$2,474 (n=244)** · 0.6 → +$2,470 · 0.8 → +$2,090 · **1.0 → +$1,498 (n=145)** ·
1.2 → +$1,544 · 1.4 → +$1,413. **Monotonically destructive**: it costs $976 and 40% of the sample.
**Cause of death: inside 13:00–15:00 UTC every bar is already a volume-expansion bar — RVOL has no
cross-section left to cut on, so the threshold simply drops the *early* (best-priced) impulses and
keeps the late ones.** Removed from the spec rather than tuned; a filter that costs money and sample
was fitting noise.

### GRAVE 4 (inherited, re-confirmed) — `news_window_range_breakout`
Last week's grave, re-run this week as the NIPC ablation: **impulse-chase with no pullback
requirement = −$2,143 at 27.9% win over 290 trades** (and −$203 at 33.9% if you allow a token 15%
pullback). Cause of death confirmed for a second week and now *explained*: the direction read
(continuation from a range extreme) was right all along; the entry price was wrong. Stays buried —
but it is the reason NIPC exists.

## 11. What I would do with this

1. **Shadow it, do not arm it.** n=171 over 12 days is one regime-fortnight. There is no cross-regime
   tape here: no FOMC week, no CPI shock, and — critically — barely any genuinely quiet news window
   (`dead-chop` is only 34 trades, and that is precisely the bucket the gate turns off). The desk's
   own promotion ladder says shadow → 1 lot, gated on 8–12 weeks and cross-regime evidence.
2. **The claim to re-test first is the EXIT, not the entry.** "Fixed 2.5R beats a trail in the news
   window" contradicts the standing chandelier prior and is worth ~$1,285 in the sweep. If that flips
   on fresh tape, the whole exit half of the spec flips with it.
3. **Do not size against the $14,519 ceiling.** NIPC converts $189 of the sat-out OPEN/NEWS money;
   its P&L is scalping revenue that is merely *correctly-sided* during the runs.
4. **Next build:** all 4 red runs are same-window reversals after a stop-out. A
   *second-entry-in-the-same-direction veto* (or an entry-count cap per impulse cluster) is the
   obvious repair and is a one-parameter change.
5. **Data gap to close:** tick coverage starts 07-23 22:00. Six of the twelve study days had to be
   run on 5s bars. Extending tick retention would let the whole study be tick-honest.

---

### Summary line
`news_impulse_pullback` (NIPC) — impulse ≥ 1.0×ATR1m in 2 min → wait for a 35–75% retrace → enter on
the half-back reclaim → stop at the pullback extreme → 2.5R target → dead-chop OFF → 13:00–15:00 UTC only.
**+$2,676 · 43.3% win · n=171 · 12 days · $15.6/trade · 17/21 big moves green (21/21 aligned).**
44/44 razor variants positive · both sides independently +EV · strip-10-best still +$1,137 · survives
$12/RT and +3 pt stop slip · OOS (tick-honest) beats IS (bar-replay) · z = +5.0 against a −$846 null.
**Graves: `vacuum_squeeze`, `failed_expansion_reversal`, `rvol_expansion_filter`, `news_window_range_breakout`.**
