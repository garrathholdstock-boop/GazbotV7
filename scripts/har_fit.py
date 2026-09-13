#!/usr/bin/env python3
"""Fit HAR on a frozen window and VERIFY the claimed R^2 out of sample, against ATR14."""
import sys; sys.path.insert(0, "/home/alphabot/gazbot7/src")
import duckdb, numpy as np, pandas as pd
from gazbot7.harvol import realised_vol, features, fit, predict, r2

GB = "/home/alphabot/gazbot7"
con = duckdb.connect()
b = con.execute(f"""select bar_ts, close, high, low from read_parquet(
  '{GB}/data/tape/bars/NQ/*.parquet') where timeframe='1min' order by bar_ts""").df()
rv = realised_vol(b)
print(f"realised vol: {len(rv)} sessions {rv.index.min()} .. {rv.index.max()}")
days = list(rv.index); cut = days[int(len(days)*0.60)]
tr, te = rv[rv.index <= cut], rv[rv.index > cut]
coef = fit(tr)
print(f"FIT on {len(tr)} sessions to {cut} (never refitted): "
      + " ".join(f"{k}={v:.4f}" for k, v in coef.items() if k != "n_fit"))

# ATR14 as the incumbent forecast, on the SAME target
d = b.copy(); d["day"] = pd.to_datetime(d.bar_ts, unit="s", utc=True).dt.date
tr_hl = d.groupby("day").apply(lambda x: np.maximum(x.high - x.low, .25).mean(), include_groups=False)
atr = tr_hl.rolling(14).mean().shift(1)
px = d.groupby("day").close.last()
atr_rel = (atr / px).dropna()                        # ATR14 as a fraction of price, comparable to RV

for lbl, sub in (("HELD OUT (last 40%)", te), ("full sample", rv)):
    X = features(sub); yhat = predict(sub, coef)
    idx = X.index
    har = r2(np.exp(X.y), yhat)
    a = atr_rel.reindex(idx).dropna()
    j = pd.DataFrame({"y": np.exp(X.y).reindex(a.index), "a": a}).dropna()
    # ATR14 needs a scale to be a forecast of RV at all; give it the best possible one (OLS on the
    # SAME data) — a deliberately generous handicap, so a loss here is not a scaling artefact.
    k = (j.y * j.a).sum() / (j.a ** 2).sum()
    atr_r2 = r2(j.y, k * j.a)
    print(f"\n{lbl}: n={len(idx)}")
    print(f"   HAR(1,5,22)        R^2 = {har:+.3f}")
    print(f"   ATR14 (best-scaled) R^2 = {atr_r2:+.3f}")
    print(f"   -> HAR beats ATR14 by {har-atr_r2:+.3f} of variance explained")

print("\nby held-out year:")
X = features(te); yhat = predict(te, coef)
yy = pd.DataFrame({"y": np.exp(X.y), "p": yhat}).dropna()
yy["yr"] = [d.year for d in yy.index]
for yr, g in yy.groupby("yr"):
    if len(g) < 60: continue
    rw = r2(g.y, g.y.shift(1).bfill())          # the random walk: tomorrow = today
    print(f"   {yr}: n={len(g):>4}  HAR {r2(g.y, g.p):+.3f}   random-walk {rw:+.3f}   "
          f"{'HAR WINS' if r2(g.y,g.p) > rw else 'rw wins'}")
print(f"\nFROZEN coefficients for src/gazbot7/harvol.py:\n  FROZEN = {coef}")
