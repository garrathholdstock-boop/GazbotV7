#!/usr/bin/env python3
"""TUNNEL FIT — MGC. Does gold do tunnel · run · tunnel · run, and is a break worth anything?

★2026-09-03. Operator, watching the gold chart added to the dashboard the night before:
*"mgc shows a nice grind up since open ... i think we are on to something. we will trade between
the tunnels. just a few runs per day."*

This is the MEASUREMENT behind that. It mirrors the MNQ work in `scripts/tunnel_watch.py` exactly —
same feature, same model, same tests, same controls — with ONE thing deliberately not reused:

⚠⚠ THE MNQ PARAMETERS ARE NOT USED, AND MUST NEVER BE. They were fitted on log true range in MNQ
   POINTS (quiet mean 5.14pt, active 14.62pt). Gold's minute range is ~1.4pt. Scoring gold with
   them marks every minute ACTIVE, finds no tunnels, and returns a confident "gold has no
   structure" that is purely a units error — the same shape as the incident where MGC folded into
   an MNQ reader made ATR read 1848 against a true 15. Gold gets its own fit, from scratch.

METHOD, and why each piece is there
───────────────────────────────────
1. FRONT-MONTH CONTINUOUS SERIES. The backfill holds one file per expiry and they overlap by
   months. Splicing them naively double-counts minutes and mixes a thin back-month tape into the
   fit. For each UTC date the front contract is the one with the most VOLUME that date; a date's
   bars come only from it. At a roll the price jumps, so the true range across the seam is dropped
   rather than fed to the model as a 40-point minute.
2. FEATURE = log(Wilder true range), on real closes. Identical to production.
3. MODEL = 2-state Gaussian HMM fitted by Baum-Welch. Fitting offline is fine; USING it online must
   be forward-filter only, which is what tunnel_watch does and what the OOS check here does.
4. STABILITY. Refit on independent thirds. A structure that only exists in one window is a fit.
5. THE BREAK IS SCORED AGAINST A MATCHED-HOUR CONTROL. Gold's activity is strongly hour-of-day
   driven; comparing breaks to an all-hours average would credit the break with the London open.
6. ⚠ RACE FROM THE END OF THE BREAK MINUTE. Starting the forward race at the break bar's own
   timestamp replays the decision minute and is a look-ahead — the documented MGC lab error
   ("resample labels the left edge").
7. ⚠ FIRST PASSAGE, NOT MFE. "Reached N ATR" ignores whether the other side came first. That
   inflated a win rate 29% -> 78% on this desk once and shipped a losing config.
8. COST IS CARRIED: MGC round trip from mid is $4.50 = 0.45pt at $10/pt (MGC_VPP). Not $7.50 —
   a round trip crosses the 0.30pt spread ONCE.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
from datetime import datetime, timedelta, UTC

import duckdb

MGC_VPP = 10.0          # $ per point (levelbreak.MGC_VPP)
MGC_FEE_RT = 4.50       # $ per round trip from mid = 0.45pt
BACKFILL = "data/backfill"


def session_key(ts: int) -> str:
    """CME session 22:00Z -> 21:00Z; +2h puts one session on one date. Same rule as production."""
    return (datetime.fromtimestamp(ts, UTC) + timedelta(hours=2)).date().isoformat()


def front_month_minutes(verbose=True, symbol="MGC"):
    """One continuous 1-minute series, front contract only, with roll seams marked.

    Returns (bars, rolls) where bars is a list of dicts in time order and `rolls` is the set of
    minute timestamps that START a new contract (their true range is dropped).
    """
    con = duckdb.connect()
    files = sorted(glob.glob(f"{BACKFILL}/{symbol}_2*_1min.parquet"))
    # volume by (date, contract) → the front contract for each date
    rows = []
    for f in files:
        tag = os.path.basename(f).split("_")[1]
        rows.append(f"select '{tag}' as c, ts, open, high, low, close, volume from read_parquet('{f}')")
    con.execute("create table raw as " + " union all ".join(rows))
    con.execute("""create table front as
        select d, c from (
          select strftime(to_timestamp(ts), '%Y-%m-%d') as d, c, sum(volume) v,
                 row_number() over (partition by strftime(to_timestamp(ts), '%Y-%m-%d')
                                    order by sum(volume) desc, c desc) rn
          from raw group by 1, 2) where rn = 1""")
    df = con.execute("""
        select r.ts, r.high, r.low, r.close, r.volume, r.c
        from raw r join front f
          on f.d = strftime(to_timestamp(r.ts), '%Y-%m-%d') and f.c = r.c
        order by r.ts""").fetchall()
    bars, rolls, prev_c = [], set(), None
    for ts, hi, lo, cl, vol, c in df:
        if bars and ts == bars[-1]["m"]:      # same minute twice = a splice fault, not data
            continue
        if prev_c is not None and c != prev_c:
            rolls.add(int(ts))
        prev_c = c
        bars.append({"m": int(ts), "hi": float(hi), "lo": float(lo),
                     "close": float(cl), "vol": float(vol or 0), "c": c})
    if verbose:
        sess = {session_key(b["m"]) for b in bars}
        print(f"{symbol} front-month series: {len(bars):,} minutes · {len(sess)} sessions · "
              f"{datetime.fromtimestamp(bars[0]['m'], UTC).date()} -> "
              f"{datetime.fromtimestamp(bars[-1]['m'], UTC).date()} · {len(rolls)} roll seam(s)")
    return bars, rolls


TICK = 0.10             # MGC minimum price increment. Half a tick is the "did anything print" line.


def true_range(bars, rolls):
    """Wilder TR on real closes. A roll seam gets None — the gap is a bookkeeping jump, not range."""
    out, prev_close = [], None
    for b in bars:
        if b["m"] in rolls:
            out.append(None); prev_close = b["close"]; continue
        tr = b["hi"] - b["lo"]
        if prev_close is not None:
            tr = max(tr, abs(b["hi"] - prev_close), abs(b["lo"] - prev_close))
        out.append(max(tr, 1e-6))
        prev_close = b["close"]
    return out


def observations(trs):
    """log(TR), with UNOBSERVABLE minutes masked to NaN rather than pushed to zero.

    ★★ THIS IS THE FINDING THAT SHAPED THE FIT, AND IT IS SPECIFIC TO GOLD. 2.5% of MGC minutes
    (9,156 of 372,690) have a true range of EXACTLY ZERO — no trade printed, or one trade at the
    previous close. On a log scale zero is not "very small", it is minus infinity: floored to 1e-6
    those minutes land at logTR −13.8 while the entire real distribution lives between −2.5 and
    +4.5. A 2-state HMM handed that spike does the obvious thing and spends a whole state on it —
    the first fit here returned "quiet" = mean TR 0.03pt covering 2.5% of minutes and "active" =
    everything else, which is a detector for a DEAD TAPE, not for a compression.

    MNQ never showed this because MNQ prints every minute. Reusing the MNQ recipe unexamined would
    have produced a plausible, wrong model — the whole reason gold gets its own fit.

    Masked minutes are NOT dropped. Dropping them would splice unrelated minutes together and
    shorten every run that spans one. They are carried as missing observations: the state
    propagates through them by transition only, which is exactly what "no information" means.
    """
    import numpy as np
    out = []
    for t in trs:
        out.append(float("nan") if (t is None or t < TICK / 2) else math.log(t))
    return np.array(out, dtype=float)


# ── the model ────────────────────────────────────────────────────────────────
def _emissions(x, mu, sd):
    """Gaussian likelihood per state, with NaN minutes contributing NOTHING (likelihood 1 both
    states) so the chain propagates through them on the transition matrix alone."""
    import numpy as np
    x = np.asarray(x, dtype=float); mu = np.asarray(mu); sd = np.asarray(sd)
    z = (x[:, None] - mu) / sd
    B = np.exp(-0.5 * z * z) / (sd * np.sqrt(2 * np.pi)) + 1e-300
    B[np.isnan(x)] = 1.0
    return B


def _npdf(x, mu, sd):
    z = (x - mu) / sd
    return math.exp(-0.5 * z * z) / (sd * math.sqrt(2 * math.pi)) + 1e-300


def fit_hmm(x, iters=200, tol=1e-7):
    """Baum-Welch for a 2-state Gaussian HMM on x (already in LOG space).

    Returns (mu, sd, A, loglik). Vectorised with numpy — the pure-Python version of this loop is
    unusable at 372k points, and `test_fit_matches_the_reference_implementation` pins this against
    a slow, obviously-correct one on a small sample so the speed is not bought with a silent bug.

    ★ State 0 is forced to be QUIET (the lower mean) before returning. Baum-Welch has no notion of
      which state is which, so two refits can come back with the labels swapped — and a stability
      check that compares a swapped pair reads as a total failure of the model when nothing moved.
    """
    import numpy as np
    x = np.asarray(x, dtype=float)
    n = x.size
    q1, q3 = np.nanpercentile(x, [25, 75])
    mu = np.array([q1, q3])
    sd = np.array([max(1e-3, (q3 - q1) / 2)] * 2)
    A = np.array([[0.99, 0.01], [0.01, 0.99]])
    pi = np.array([0.5, 0.5])
    ll_prev = None
    ll = 0.0
    for _ in range(iters):
        B = _emissions(x, mu, sd)
        al = np.empty((n, 2)); sc = np.empty(n)
        al[0] = pi * B[0]; sc[0] = al[0].sum() or 1e-300; al[0] /= sc[0]
        for t in range(1, n):
            al[t] = (al[t - 1] @ A) * B[t]
            sc[t] = al[t].sum() or 1e-300
            al[t] /= sc[t]
        be = np.empty((n, 2)); be[-1] = 1.0
        for t in range(n - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / sc[t + 1]
        g = al * be
        g /= g.sum(axis=1, keepdims=True)
        # xi summed over t, vectorised: al[t] (outer) A*B[t+1]*be[t+1], normalised per t
        num = al[:-1, :, None] * A[None, :, :] * (B[1:] * be[1:])[:, None, :]
        num /= num.sum(axis=(1, 2), keepdims=True)
        A = num.sum(axis=0)
        A /= A.sum(axis=1, keepdims=True)
        obs = ~np.isnan(x)                    # masked minutes inform transitions, never the means
        go = g[obs]
        xo = x[obs][:, None]
        w = go.sum(axis=0)
        mu = (go * xo).sum(axis=0) / w
        var = (go * (xo - mu) ** 2).sum(axis=0) / w
        sd = np.maximum(1e-3, np.sqrt(var))
        pi = g[0]
        ll = float(np.log(sc).sum())
        if ll_prev is not None and abs(ll - ll_prev) < tol * max(1.0, abs(ll)):
            break
        ll_prev = ll
    if mu[0] > mu[1]:
        mu = mu[::-1].copy(); sd = sd[::-1].copy()
        A = A[::-1, ::-1].copy()
    return [float(v) for v in mu], [float(v) for v in sd], [[float(v) for v in r] for r in A], ll


def filter_quiet(x, mu, sd, A):
    """FORWARD pass only — P(quiet at t | data up to t). Causal, exactly like production.

    Deliberately NOT Viterbi or smoothing: those relabel the past using the future, which is the
    look-ahead that turns a measurement into a story. `tunnel_watch.filter_states` is this function.
    """
    import numpy as np
    x = np.asarray(x, dtype=float)
    mu = np.asarray(mu); sd = np.asarray(sd); A = np.asarray(A)
    B = _emissions(x, mu, sd)
    a = np.array([0.5, 0.5]) * B[0]
    a /= a.sum() or 1e-300
    out = np.empty(x.size)
    out[0] = a[0]
    for t in range(1, x.size):
        a = (a @ A) * B[t]
        a /= a.sum() or 1e-300
        out[t] = a[0]
    return out.tolist()


# ── the scale-free feature ───────────────────────────────────────────────────
def normalised(x, window=1380, min_periods=240):
    """log(TR) minus a CAUSAL trailing median of log(TR) — "how compressed is this minute against
    the tape's own recent normal", which is what a tunnel actually is.

    ★★ WHY GOLD NEEDS THIS AND MNQ APPEARED NOT TO. Fitted on RAW log TR, gold's two states move
    with the year: quiet ran 0.64pt in the first third of the sample, 1.72pt in the second, 1.30pt
    in the third, because gold's own volatility roughly doubled while it went 3350 -> 5000 -> 4400.
    A fixed-parameter raw model therefore ROTS — it would call an ordinary 2026 minute "active"
    using 2025 thresholds. On the normalised feature the same three independent thirds return
    quiet 0.73 / 0.77 / 0.75 x median and active 1.57 / 1.62 / 1.54 x, which is the same model
    three times. A parameter that has to be re-fitted to stay true is a parameter that will one day
    not be re-fitted.

    ⚠ CAUSAL BY CONSTRUCTION: the window is trailing and `.shift(1)` excludes the minute being
      scored. Including t in its own baseline is a look-ahead, and a small one is still a lie.
    """
    import numpy as np
    import pandas as pd
    s = pd.Series(np.asarray(x, dtype=float))
    base = s.rolling(window, min_periods=min_periods).median().shift(1)
    return (s - base).to_numpy()


# ── structure ────────────────────────────────────────────────────────────────
def tunnels_and_breaks(bars, trs, post, min_tunnel=25):
    """Walk the tape ONCE, causally, exactly as the live watcher does.

    Returns (tunnels, breaks). A tunnel is a contiguous run of P(quiet)>=0.5. A break is the first
    minute after an armed tunnel (>= min_tunnel long) where the tape is ACTIVE and price has traded
    outside the tunnel's own high/low.

    ⚠ ONE BREAK PER TUNNEL. The watcher disarms after it alerts; counting every subsequent minute
      outside the range would multiply the same event by its duration and inflate every rate here.
    """
    tunnels, breaks = [], []
    run_start = None
    armed = None
    for i, p in enumerate(post):
        quiet = (p is not None and p >= 0.5)
        if quiet:
            if run_start is None:
                run_start = i
            continue
        if run_start is not None:                      # a quiet run just ended
            seg = bars[run_start:i]
            if len(seg) >= 2:
                t = {"i0": run_start, "i1": i - 1, "n": len(seg),
                     "hi": max(b["hi"] for b in seg), "lo": min(b["lo"] for b in seg)}
                tunnels.append(t)
                if len(seg) >= min_tunnel:
                    armed = t
            run_start = None
        if armed is None:
            continue
        b = bars[i]
        up, dn = b["hi"] > armed["hi"], b["lo"] < armed["lo"]
        if not (up or dn):
            continue
        atr = _atr14(trs, i)
        breaks.append({"i": i, "side": "UP" if up and not dn else ("DOWN" if dn and not up else "BOTH"),
                       "tunnel_n": armed["n"], "width": armed["hi"] - armed["lo"],
                       "hi": armed["hi"], "lo": armed["lo"], "atr": atr, "m": b["m"]})
        armed = None
    return tunnels, breaks


def _atr14(trs, i):
    """Trailing 14-minute mean true range at bar i — the same ATR the watcher prints."""
    vals = [t for t in trs[max(0, i - 13):i + 1] if t is not None]
    return (sum(vals) / len(vals)) if vals else float("nan")


def race(bars, i0, atr, mults=(1.0, 1.5, 2.0), horizon=60, direction=1):
    """FIRST PASSAGE from the END of bar i0: which barrier is touched first, in ATR units.

    ⚠⚠ THE RACE, NOT THE MFE. "Reached N ATR" ignores whether the other side came first; that
       error inflated a win rate 29% -> 78% on this desk and shipped a losing config live.
    ⚠⚠ STARTS AT i0 + 1. Racing from bar i0's own high/low replays the very minute the decision was
       made with knowledge of how it ended — the documented "resample labels the left edge"
       look-ahead. One bar of slack is the difference between a measurement and a story.

    Returns {mult: +1 favourable first / -1 adverse first / 0 neither inside the horizon} plus the
    60-minute MFE and MAE in ATR.
    """
    if not atr or atr != atr:
        return None
    ref = bars[i0]["close"]
    out = {m: 0 for m in mults}
    hit = {m: False for m in mults}
    mfe = mae = 0.0
    for b in bars[i0 + 1:i0 + 1 + horizon]:
        up = (b["hi"] - ref) / atr
        dn = (b["lo"] - ref) / atr
        fav, adv = (up, -dn) if direction > 0 else (-dn, up)
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        for m in mults:
            if hit[m]:
                continue
            # both barriers inside one bar: unresolvable at this resolution, and calling it a win
            # is how a backtest flatters itself. Scored ADVERSE — the conservative reading.
            f, a = fav >= m, adv >= m
            if f and a:
                out[m] = -1; hit[m] = True
            elif f:
                out[m] = 1; hit[m] = True
            elif a:
                out[m] = -1; hit[m] = True
    return {"passage": out, "mfe": mfe, "mae": mae}
