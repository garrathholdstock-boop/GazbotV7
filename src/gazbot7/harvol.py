"""HAR volatility forecast — the one thing the literature sweep found that REPLICATES.

⛔⛔ THE CLAIM THIS MODULE WAS WRITTEN FOR IS REFUTED. DO NOT SWAP THIS IN FOR ATR14.

The literature sweep reported ATR14 at R^2 = -0.057 against HAR's 0.589 out of sample, called it the
best-replicated finding of the weekend, and FOUR independent agents hit it from different angles.
Re-derived by hand on the same NQ tape, 1,292 held-out sessions, HAR fitted on the first 60% and
never refitted:
      target            HAR R^2    ATR14 R^2 (best-scaled)    winner
      RV in levels        0.217            0.311              ATR14
      log RV              0.164            0.231              ATR14
      RV vs RAW ATR14 in POINTS           -1,018,474          <- the "-0.057" shape
★★★ THE -0.057 IS A UNITS ARTEFACT. ATR14 is in POINTS (median 3.8); realised volatility is a
FRACTION of price (median 0.00978). Comparing them without a scale is meaningless, and given ANY
scaling ATR14 is a perfectly good forecast which BEATS HAR in both spaces. The two forecasts
correlate 0.911 - they are the same signal. There was never a swap to make.
★★ AND THE LESSON IS ABOUT AGREEMENT, NOT ABOUT VOLATILITY: four agents converging is evidence only
if they did not inherit the same mistake. They all compared ATR14-in-points to RV-as-a-fraction, so
the fourfold "replication" replicated the error, which reads as confirmation and is worse than a
single unchecked claim. See [[agreement-is-not-independence]].

WHAT IS STILL TRUE: HAR is a legitimate volatility forecaster and beats a random walk in 4 of 5
held-out years. It is kept for that, as an INFORMATION tool. It is not an upgrade to anything live.

★★ THIS IS NOT AN ORDER-PATH CHANGE AND MUST NOT BECOME ONE HERE. It is exposed for INFORMATION -
the router's context, the tape reader, notifications. Swapping it into a live stop width is a
separate decision with its own test, because a better volatility forecast changes position risk
even when it changes nothing else.

THE MODEL. Corsi (2009): log(RV_t+1) = b0 + b1*log(RV_daily) + b2*log(RV_weekly) + b3*log(RV_monthly)
fitted by ordinary least squares. Daily realised volatility is the square root of the sum of squared
1-minute log returns in a session. Parameters are FIT ONCE on a frozen window and never refitted -
refitting on all the data relabels history with hindsight, which is the artefact sessionmap.py warns
about and which manufactured a z=4-6 finding here that did not exist in real time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ★ FROZEN 2026-09-13. Fit window = the NQ long tape's first 60% (2015-01-02 .. ~2021). Refitting
# these is a decision, not maintenance: change them and the forward record restarts at zero.
FROZEN = None          # populated by fit(); see scripts/har_fit.py which writes it back


def realised_vol(bars: pd.DataFrame, ts_col: str = "bar_ts", px_col: str = "close") -> pd.Series:
    """Daily realised volatility from intraday bars: sqrt of the sum of squared log returns."""
    d = bars.copy()
    d["day"] = pd.to_datetime(d[ts_col], unit="s", utc=True).dt.date
    d["r"] = np.log(d[px_col]).diff()
    rv = d.groupby("day").r.apply(lambda x: np.sqrt(np.nansum(x.values ** 2)))
    return rv[rv > 0]


def features(rv: pd.Series) -> pd.DataFrame:
    """The three HAR horizons, all STRICTLY PRIOR to the day being predicted."""
    l = np.log(rv)
    return pd.DataFrame({
        "d": l.shift(1),
        "w": l.rolling(5).mean().shift(1),
        "m": l.rolling(22).mean().shift(1),
        "y": l,
    }).dropna()


def fit(rv: pd.Series) -> dict:
    X = features(rv)
    A = np.column_stack([np.ones(len(X)), X.d, X.w, X.m])
    beta, *_ = np.linalg.lstsq(A, X.y.values, rcond=None)
    return {"b0": beta[0], "bd": beta[1], "bw": beta[2], "bm": beta[3], "n_fit": int(len(X))}


def predict(rv: pd.Series, coef: dict) -> pd.Series:
    X = features(rv)
    lp = coef["b0"] + coef["bd"]*X.d + coef["bw"]*X.w + coef["bm"]*X.m
    return np.exp(lp)


def r2(y, yhat) -> float:
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    ok = np.isfinite(y) & np.isfinite(yhat)
    y, yhat = y[ok], yhat[ok]
    return 1.0 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
