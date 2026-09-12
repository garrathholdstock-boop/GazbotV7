#!/usr/bin/env python3
"""RE-SCORE THE DIRECTION NULLS ON EXPECTANCY, NOT HIT RATE.

★ THE OBJECTION (literature review, 2026-09-12). Zarattini's noise-area strategy wins 36% of the
  time with a 2.09 payoff — positive expectancy, sub-50% hit rate. Five of this desk's direction
  nulls were scored on HIT RATE and found ~0.50, then filed as coin flips. A 0.50 hit rate cannot
  reject a positive-expectancy rule if the payoff is asymmetric.

★★ BUT THE OBJECTION ONLY APPLIES TO SOME OF THEM, AND THAT IS THE FIRST FINDING. A measurement
  whose outcome is a SYMMETRIC RACE — does price reach +1 ATR or -1 ATR first — has no payoff
  asymmetry by construction: win and loss are the same size, so hit rate IS expectancy and 0.50 IS
  zero. The objection bites only where the metric was the SIGN of a forward move, because a sign
  discards magnitude and a skewed distribution can carry a positive mean at a 0.50 sign rate.
  So each null is classified before it is rescored.

⚠ MFE IS NOT A WIN RATE. mfe/mae alone cannot say which came first; only the recorded race columns
  can. Asymmetric cells are evaluated from the race outcomes, never from mfe > target.
"""
from __future__ import annotations
import glob, json
import duckdb, numpy as np, pandas as pd

GB = "/home/alphabot/gazbot7"


def boot_ci(x, n=10000, seed=5, groups=None):
    """★ DAY-CLUSTERED when groups are given. Overlapping 15- and 60-minute forward windows inside
    one session are nowhere near independent, so resampling MINUTES manufactures a confidence
    interval roughly an order of magnitude too tight — the same per-observation inflation measured
    on this desk's book data (t = -12.13 per observation against a CI spanning one). Resample DAYS."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    if groups is not None:
        x = pd.DataFrame({"x": x, "g": np.asarray(groups)}).groupby("g").x.mean().values
    idx = rng.integers(0, len(x), size=(n, len(x)))
    m = x[idx].mean(axis=1)
    # ★ RETURN THE POINT ESTIMATE THE INTERVAL IS ACTUALLY AROUND. Clustering resamples DAY MEANS,
    # so the statistic is the mean of daily means — equal weight per day — which is NOT the pooled
    # mean when days carry unequal counts. Printing the pooled mean beside a clustered CI produced
    # an interval that did not contain its own estimate (-0.152 against [-0.889, -0.496]).
    return float(x.mean()), np.percentile(m, 2.5), np.percentile(m, 97.5)


def tunnel_rescore():
    print("=" * 78)
    print("NULL 1+2 — THE TUNNEL BREAK / BREAK-THEN-JOIN DIRECTION")
    print("  original metric: P(price reaches +k ATR before -k ATR) = 0.459 / 0.513 / 0.499")
    print("  CLASSIFICATION: SYMMETRIC RACE. Win and loss are both k ATR, so hit rate IS")
    print("  expectancy and the payoff objection cannot apply. Shown here, not assumed:")
    for sym in ("MNQ", "MGC"):
        f = f"{GB}/reports/tunnel_mgc/race_{sym}.json"
        try:
            d = json.load(open(f))
        except FileNotFoundError:
            continue
        for arm in ("brk", "ctl"):
            df = pd.DataFrame(d[arm])
            if df.empty:
                continue
            print(f"\n  {sym} {arm:>4}  n={len(df)}")
            for k in ("p1.0", "p1.5", "p2.0"):
                if k not in df:
                    continue
                r = df[k].dropna()
                r = r[r != 0]
                if len(r) < 30:
                    continue
                hit = (r > 0).mean()
                kk = float(k[1:])
                # expectancy of the symmetric race, in ATR units: win +k, lose -k
                exp_atr = hit * kk - (1 - hit) * kk
                _e, lo, hi = boot_ci((r > 0).astype(float))
                print(f"     {k}: hit {hit:.4f} [{lo:.4f},{hi:.4f}]  ->  expectancy "
                      f"{exp_atr:+.4f} ATR  (payoff ratio 1.00 by construction)")
    print("\n  VERDICT: the objection does NOT rescue these. A symmetric race has no skew to hide.")


def long_tape_rescore():
    print("\n" + "=" * 78)
    print("NULL 3+4+5 — THE SIGN-BASED DIRECTION TESTS, RESCORED ON MAGNITUDE")
    print("  original metric: P(forward move agrees with the trigger) ~ 0.50")
    print("  CLASSIFICATION: SIGN-BASED. A sign discards magnitude, so this is exactly where a")
    print("  skewed payoff could hide. Re-measured on 10.5 YEARS of NQ (3.67M 1-min bars), with")
    print("  the mean signed move and the win/loss payoff ratio beside the hit rate.\n")
    con = duckdb.connect()
    df = con.execute(f"""
      select bar_ts ts, open, high, low, close, volume
      from read_parquet('{GB}/data/tape/bars/NQ/*.parquet') where timeframe='1min'
      order by bar_ts""").df()
    c = df.close.values
    n = len(c)
    atr = pd.Series(np.maximum(df.high.values - df.low.values, .25)).rolling(20, 5).mean().values
    vol = pd.Series(df.volume.values).rolling(60, 10).mean().values
    day = (df.ts.values // 86400)
    ret5 = np.zeros(n); ret5[5:] = c[5:] - c[:-5]
    # ★ .shift(1) IS NOT COSMETIC. rolling(60).max() INCLUDES the current bar, so "price breaks
    # out of the PRIOR 60 minutes" (a) peeks at the bar it is deciding on and (b) can essentially
    # never fire, because the current high is in its own maximum. Unshifted, this trigger produced
    # under 200 observations in 3.67M bars and vanished from the table silently — a look-ahead that
    # presents as an empty result rather than an error.
    hi60 = pd.Series(df.high.values).rolling(60).max().shift(1).values
    lo60 = pd.Series(df.low.values).rolling(60).min().shift(1).values
    atr_fast = pd.Series(np.maximum(df.high.values - df.low.values, .25)).rolling(10, 3).mean().shift(1).values

    trig = {
      "THRUST  (5-min move >= 1.5 ATR)": (np.abs(ret5) >= 1.5 * atr, np.sign(ret5)),
      "RANGE BREAK (out of prior 60m)": ((c > hi60) | (c < lo60), np.where(c > hi60, 1, -1)),
      "VOL EXPANSION (fast ATR >= 1.5x)": ((atr_fast >= 1.5 * atr) & (np.abs(ret5) > 0),
                                          np.sign(ret5)),
      "VOLUME SPIKE (>= 3x 60-min avg)": ((df.volume.values >= 3 * vol) & (np.abs(ret5) > 0),
                                          np.sign(ret5)),
    }
    for H in (15, 60):
        print(f"  ── horizon {H} minutes " + "─" * 46)
        print(f"{'trigger':<34}{'n':>8}{'hit':>8}{'mean pt':>10}{'95% CI':>20}"
              f"{'payoff':>8}")
        fwd = np.full(n, np.nan)
        ok = np.arange(n - H)
        same = day[ok] == day[ok + H]
        fwd[ok[same]] = c[ok[same] + H] - c[ok[same]]
        for name, (mask, side) in trig.items():
            m = mask & np.isfinite(fwd) & np.isfinite(atr) & (np.arange(n) > 60)
            if m.sum() < 200:
                continue
            r = side[m] * fwd[m]
            wins, losses = r[r > 0], r[r < 0]
            payoff = (wins.mean() / abs(losses.mean())) if len(losses) else np.nan
            est, lo, hi = boot_ci(r, groups=day[m])
            print(f"{name:<34}{m.sum():>8}{(r > 0).mean():>8.4f}{est:>10.3f}"
                  f"   [{lo:>6.3f},{hi:>6.3f}]{payoff:>8.2f}")
        # the control: same horizon, no trigger, direction from the same 5-min sign
        m = np.isfinite(fwd) & (np.abs(ret5) > 0) & (np.arange(n) > 60)
        r = np.sign(ret5[m]) * fwd[m]
        est, lo, hi = boot_ci(r, groups=day[m])
        print(f"{'CONTROL — every minute, same rule':<34}{m.sum():>8}{(r > 0).mean():>8.4f}"
              f"{est:>10.3f}   [{lo:>6.3f},{hi:>6.3f}]"
              f"{(r[r>0].mean()/abs(r[r<0].mean())):>8.2f}")
        print()


if __name__ == "__main__":
    tunnel_rescore()
    long_tape_rescore()
