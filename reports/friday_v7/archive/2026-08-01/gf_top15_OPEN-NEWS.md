# Greenfield Hunt — OPEN-NEWS cluster (census level: top15)

**Verdict: GRAVE. No survivor. survived = false.** Narrowing from the full 19-run cluster to the
6 biggest OPEN-NEWS runs was meant to surface a stronger footprint the marginal runs washed out.
It surfaces a *mirage*: a news-window mean-reversion scalp that nets **+$791 (win 63%, both sides
nominally green)** — but it **fights the two biggest target runs** (−194, −178), catches only
**2 of 6**, rests on a **10-point target knife-edge** (t30 −$134 → t40 +$791), and is really a
buy-the-dip chop-scalp whose profit is orthogonal to the census gap. Buried.

---

## 1. The target set — OPEN-NEWS ∩ top15

OPEN/NEWS is the census cluster defined **purely by clock**: every ≥1.5×ATR 15-min run that starts
in **13:00–15:00 UTC** (US pre-open / 13:30 cash open / 14:00 data drop). 19 runs this week. Of
those, **6** fall inside the 15 biggest sat-out moves of the week (|move| ≥ 105pt):

| time UTC | dir | move | realized (tick) |
|---|---|---|---|
| 07-24 13:38 | DN | −194 | −176 |
| 07-23 14:40 | DN | −178 | −171 |
| 07-23 13:28 | UP | +166 | +161 |
| 07-23 14:59 | DN | −118 |  −92 |
| 07-22 14:55 | UP | +110 |  +91 |
| 07-20 14:40 | DN | −105 |  −78 |

Direction split **4 DN / 2 UP**, and three of the six cluster on a single trend day (07-23:
UP then DN then DN inside 90 minutes). Same two-sided-inside-one-hour shape the full cut showed —
narrowing did not make it directional.

Data: `data/capture.db` MNQ, 7.30M ticks, 07-19 22:00 → 07-24 21:00 UTC (all 6 runs covered).
Tick-honest replay (stop checked before target within a tick = conservative), $5/round-trip,
MNQ $2/pt. Tools in `scratchpad/`: `lib.py`, `engine.py`.

## 2. The premise dies in the forward study (before any sim)

Forward 15-min return conditioned on trailing displacement **D**, news-window only, 10s grid.
"cont%" = forward move shares D's sign:

| trailing D (L=60s) | n | fwd mean | cont% |
|---|---|---|---|
| D < −40 (strong down) |  89 | **−18.5** | 58% |
| D −40..−15 | 582 | −11.4 | 62% |
| D +15..+40 | 559 | −14.3 | 40% |
| D > +40 (strong up) |  69 | **−40.5** | 32% |

Every bucket's forward mean is **negative** — up-spikes and down-spikes both drift down. That is
not a signal, it is the **down-week drift** (07-23 was a strong down-trend day). "Fade up-spikes,
ride down-spikes" both reduce to *be short in the news window this week*, which is exactly the
direction-blind trap the desk has burned on before (ER band reads cleanliness, not direction).

## 3. Two invented entries, tick-honest, both fail

**Signal A — News-Window Momentum Continuation.** Active 13≤hUTC<15. Trailing displacement
D = px(t) − px(t−L). |D| ≥ TH → enter **WITH** D (long if up). Stop STOP, target TGT, 10-min cap,
2-min cooldown, single slot.
- 54-config sweep: **only 10 positive (19%)** — a coin-flip that mostly bleeds (worst −$1,728).
- Best L120/TH30/s40/t60 **+$624** but: SHORT $465 / LONG $158 (short-carried = down-week),
  day 07-21 **−$483**, **strip-3-best → +$278** (55% of it is 3 trades). Curve-fit fat-tail, not a base rate.

**Signal B — News-Window Impulse Fade** (the one that *looks* alive). Same trigger, enter
**AGAINST** D. 54-config sweep: **25 positive (46%)**, best L30/TH20/s40/t90 +$1,046.
Leading robust-looking cell **L30 / TH30 / STOP40 / TGT40**: net **+$791, n=54, win 63%**,
LONG $490 / SHORT $301 (both green), 4 of 5 days positive.

## 4. Robustness — Signal B is a chop-scalp that fights the target runs

1. **Big-moves-caught — the disqualifier: 2/6.** Aligned-and-profitable on only the two smallest
   runs (13:28 +$75, 14:55 +$75); it is positioned **AGAINST** the two biggest (13:38 **−$85**,
   14:40 **−$85**) and no-trades the other two. The net-positive fade **fills none of the census
   gap** — it scalps chop elsewhere and gets run over by the actual big moves it was built to catch.

2. **Target knife-edge (curve-fit tell).** At L30/TH30/s40, sweeping TGT:
   t25 **−$719** · t30 **−$134** · **t40 +$791** · t50 +$814 · t60 +$438 · t80 +$448.
   A 10-point nudge in the target flips −$134 → +$791. The whole edge lives in a t40–50 scalp band.

3. **The winning side is buy-the-dip.** Per-side across the TH plateau: the profit is **LONG-carried**
   (fade down-spikes = buy dips: +$345…+$620); the SHORT side (fade up-spikes) is marginal and
   flips **negative at TH20 (−$186)**. Buying dips in a news window is *structurally anti-correlated*
   with catching a big down run — hence it fights the −194/−178.

4. **Trend-day failure.** Per-day P&L is positive on the four choppy news days but **−$240 on 07-23**,
   the one trend day — which is precisely where **3 of the 6 target runs** live. The mechanism earns
   by fading chop and loses exactly when a real run appears. (Continuation Signal A is the mirror:
   it catches the down runs 3/6 but is a 19%-positive coin-flip that bleeds on 07-21.)

5. **Parameter razor (broader).** TH: 15 −606 / 20 +349 / 25 +814 / 30 +791 / 35 +460 / 50 −275 —
   a plateau, but bounded by negative neighbours; cooldown jitters +324…+1,236. No stable ridge.

## 5. Cause of death

The OPEN/NEWS cluster is a **clock bucket, not a footprint**, and shrinking to the 6 biggest runs
does not change that — it just concentrates them on one trend day. The forward tape has **no
real-time directional tell**: every displacement bucket drifts the week's direction (down). The
only net-positive mechanic is a t40 mean-reversion **chop-scalp** whose gains come from fading small
wiggles on the quiet news days; it **fights the very runs the census flagged** (2/6 caught, both
biggest fought), is **LONG/buy-the-dip-carried** (the wrong side for the 4 down runs), sits on a
**10-pt target knife-edge**, and **loses on the one trend day that holds half the targets**.
Nominally green, structurally anti-correlated with the goal. A coin-flip dressed as a scalper. Buried.

## Graves

- **news-window-impulse-fade (Signal B)** — fade trailing displacement in 13:00–15:00 UTC, tight
  t40 reversion target. Best L30/TH30/s40/t40 **+$791 / 63% / 54tr, both sides green** — but
  **big-moves-caught 2/6** (fights 13:38 −$85 and 14:40 −$85, the two biggest), **TGT razor**
  t30 −$134 → t40 +$791, LONG/buy-the-dip-carried (SHORT −$186 at TH20), **−$240 on the 07-23
  trend day** where 3 targets live. Death: a chop-scalp orthogonal to (and anti-correlated with)
  the census gap; the "edge" is dip-buying that a real down run annihilates.
- **news-window-momentum-continuation (Signal A)** — enter WITH displacement. Only **10/54 configs
  positive (19%)**, best L120/TH30/s40/t60 **+$624** but short-carried (down-week drift), day
  07-21 **−$483**, **strip-3-best +$278** (55% from 3 trades), big-moves-caught 3/6 (down runs only,
  fights the 13:28 up run). Death: a coin-flip that catches this week's down-drift, not a signal;
  no continuation edge on the up side (cont% 32–40%).
